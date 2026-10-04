"""Terrain spec §8.4 test 6: §3.5 mask validations on fixtures, the per-cell encodings, border identity, and
check_terrain_textures.py --self-test. Run: python tools/terrain/test_terrain_masks.py (also run by the client suite,
tests/terrain-masks-python.test.mjs)."""
from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'assets' / 'blender' / 'sunmeadow_v2' / 'terrain'))
import build_terrain_masks as B  # noqa: E402
import terrain_png as TP  # noqa: E402
import terrain_spec as TS  # noqa: E402


def fixture_site() -> B.Site:
    """Two cells sharing x = 0: a rutted gate road and a trail cross the border, a stream with a bridge, one hill
    collider with its toe, stones and a combat clearing."""
    site = B.Site('fixture')
    site.paths = [dict(id='gate_road', cls='gate_road', width=4.6, pts=[(-30.0, -10.0), (-4.0, -20.0), (20.0, -24.0), (40.0, -30.0)]),
                  dict(id='southbound_trail', cls='southbound_trail', width=3.8, pts=[(-4.0, -20.0), (-6.0, -40.0), (4.0, -58.0)])]
    site.water = [dict(kind='stream', pts=[(-60.0, -48.0), (-20.0, -46.0), (10.0, -45.0), (60.0, -50.0)], widths=(3.0, 4.0))]
    site.bridges = [dict(centre=(-5.6, -45.6), along=(0.0, 1.0), length=6.0)]
    site.hills = [(30.0, -12.0, 9.0, 4.0)]
    ring = [(30.0 + 8.0 * math.cos(a), -12.0 + 8.0 * math.sin(a)) for a in np.linspace(0, math.tau, 24, endpoint=False)]
    site.relief = [dict(id='fixture_hill', kind='hill', poly=ring)]
    site.stones = [(-40.0, -20.0, 0.6)]
    site.trunks = [(-50.0, -30.0, 0.3)]
    site.canopies = [(-50.0, -30.0, 3.0)]
    site.clearings = [('windmark_hunt', -50.0, -30.0, -25.0, -5.0)]
    site.cells = [dict(id='fixture_c7_r7', bounds=(-64.0, 0.0, -64.0, 0.0)), dict(id='fixture_c8_r7', bounds=(0.0, 64.0, -64.0, 0.0))]
    return site


class Encodings(unittest.TestCase):
    def test_quantise_sums_exactly_and_mud_is_derived(self):
        rng = np.random.default_rng(3)
        w = rng.random((257, 257, 4)) ** 2
        w /= w.sum(-1, keepdims=True)
        rgb = B.quantise(w)
        mud = 255 - rgb.astype(np.int32).sum(-1)
        self.assertTrue((mud >= 0).all())
        self.assertLess(float(np.abs(mud / 255 - w[..., 3]).max()), 1.0 / 255 + 1e-9)

    def test_sdf_and_rut_round_trip(self):
        sdf = np.linspace(-2, 4, 1001)
        rut = np.linspace(-3, 3, 1001)
        rut[::7] = np.nan
        data = B.encode_data(sdf[None], rut[None], np.full((1, 1001), 0.5))[0]
        dec = data[:, 0] / 255 * TS.SDF_RANGE_M + TS.SDF_MIN_M
        self.assertLessEqual(float(np.abs(dec - sdf).max()), 0.0118)
        self.assertTrue((data[::7, 1] == TS.RUT_SENTINEL).all())
        valid = ~np.isnan(rut)
        rdec = data[valid, 1] / 254 * TS.RUT_RANGE_M + TS.RUT_MIN_M
        self.assertLessEqual(float(np.abs(rdec - rut[valid]).max()), 0.0119)
        self.assertEqual(TS.decode_rut(255), None)
        self.assertAlmostEqual(TS.decode_sdf(TS.encode_sdf(0.5)), 0.5, delta=0.0118)

    def test_png_is_rgb8_without_colour_chunks_and_reads_back(self):
        arr = np.random.default_rng(1).integers(0, 256, (33, 47, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'x.png'
            TP.write_png(p, arr)
            self.assertEqual(TP.chunks(p), ['IHDR', 'IDAT', 'IEND'])
            self.assertTrue(np.array_equal(TP.read_png(p), arr))

    def test_normal_cdf(self):
        for z in (-3.0, -1.2, -0.3, 0.0, 0.4, 1.7, 3.2):
            self.assertAlmostEqual(float(B.normal_cdf(np.array([z]))[0]), 0.5 * (1 + math.erf(z / math.sqrt(2))), places=6)


class Grid(unittest.TestCase):
    def test_corner_aligned_grid_row0_north(self):
        X, Z = B.cell_grid((-64.0, 0.0, -64.0, 0.0), 256)
        inner_x, inner_z = X[1:-1, 1:-1], Z[1:-1, 1:-1]
        self.assertEqual(inner_x.shape, (257, 257))
        self.assertEqual(inner_x[0, 0], -64.0)
        self.assertEqual(inner_x[0, -1], 0.0)
        self.assertEqual(inner_z[0, 0], 0.0)      # row 0 = north (z = maxZ)
        self.assertEqual(inner_z[-1, 0], -64.0)

    def test_cell_ids(self):
        self.assertEqual(TS.cell_id(-64, -128), 'sunmeadow_c7_r6')
        self.assertEqual(TS.cell_bounds('sunmeadow_c8_r6'), (0.0, 64.0, -128.0, -64.0))


class Validations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = fixture_site()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = B.build(cls.site, Path(cls.tmp.name), [], False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_eight_validations_pass_on_the_fixture(self):
        for cid, rec in self.result['cells'].items():
            failed = [c for c in rec['checks'] if not c['pass_']]
            self.assertEqual(failed, [], cid)
            names = {c['check'].split(' ')[0] for c in rec['checks']}
            self.assertTrue({'1', '2', '8'} <= names, names)
        all_checks = {c['check'].split(' ')[0] for rec in self.result['cells'].values() for c in rec['checks']}
        self.assertTrue({'1', '2', '3', '4a', '4b', '6', '7', '8'} <= all_checks, all_checks)

    def test_shared_border_is_bit_identical(self):
        s = self.result['summary']
        self.assertTrue(s['borders_pass'])
        self.assertEqual(len(s['border_checks']), 1)

    def test_validator_catches_dirt_at_the_waterline_and_missing_bank_mud(self):
        cell = self.site.cells[0]
        X, Z = B.cell_grid(cell['bounds'], 256)
        F = B.compute(self.site, X, Z, B.authored_sides(self.site, cell))
        inner = (slice(1, -1), slice(1, -1))
        Fi = {k: (v[inner] if isinstance(v, np.ndarray) and v.shape[:2] == X.shape else v) for k, v in F.items()}
        splat = B.quantise(F['w'][inner])
        data = B.encode_data(F['sdf'][inner], F['rut'][inner], F['ao'][inner])
        bad = splat.copy()
        bank = (Fi['d_water'] >= 0) & (Fi['d_water'] < 1.0) & ~Fi['bridge_zone']
        bad[bank] = (0, 0, 255)    # all dirt, no mud on the bank
        checks = {c['check'].split(' ')[0]: c for c in B.validate(self.site, cell, Fi, bad, data, X[inner], Z[inner])}
        self.assertFalse(checks['3']['pass_'])
        self.assertFalse(checks['4a']['pass_'])
        sum_bad = splat.astype(np.int32).copy()
        sum_bad[0, 0] = (200, 100, 0)  # R+G+B > 255
        checks = {c['check'].split(' ')[0]: c for c in B.validate(self.site, cell, Fi, sum_bad.astype(np.uint16), data, X[inner], Z[inner])}
        self.assertFalse(checks['1']['pass_'])


class TextureChecker(unittest.TestCase):
    def test_check_terrain_textures_self_test(self):
        run = subprocess.run([sys.executable, str(ROOT / 'tools' / 'terrain' / 'check_terrain_textures.py'), '--self-test'],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=1)
