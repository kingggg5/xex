"""Unit tests for the capture analysis code (no browser, no GPU).

python -m unittest discover -s tools/capture -p "test_*.py"
"""
from __future__ import annotations

import unittest

import numpy as np

from compare import DEFAULTS, perf_block, pixel_metrics, ssim_luma, visual_verdict
from imaging import delta_e2000, mask_shape, srgb_to_lab
from refmatch import emd, palette_match


class ShapeTests(unittest.TestCase):
    def test_seeded_z_fight_is_scattered(self):
        rng = np.random.default_rng(1)
        mask = rng.random((270, 480)) < 0.02  # salt-and-pepper flicker, like z-fighting or alias shimmer
        self.assertEqual(mask_shape(mask)["kind"], "scattered")

    def test_seeded_culling_flip_is_one_solid_run(self):
        mask = np.zeros((270, 480), dtype=bool)
        mask[60:140, 200:320] = True  # one object appears or disappears
        shape = mask_shape(mask)
        self.assertEqual(shape["kind"], "solid")
        self.assertEqual(shape["hotspots"][0], {"x": 200, "y": 60, "w": 120, "h": 80, "pixels": 9600})

    def test_tie_flip_and_none(self):
        mask = np.zeros((100, 100), dtype=bool)
        self.assertEqual(mask_shape(mask)["kind"], "none")
        mask[10, 10:20] = True
        self.assertEqual(mask_shape(mask)["kind"], "tie-flip")


class CompareTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(2)
        self.image = rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)

    def test_identical_images(self):
        metrics, _ = pixel_metrics(self.image, self.image.copy(), DEFAULTS)
        self.assertEqual(metrics["maxDelta"], 0)
        self.assertAlmostEqual(metrics["ssim"], 1.0, places=6)
        self.assertIsNone(metrics["psnr"])
        self.assertEqual(visual_verdict(metrics, None, DEFAULTS), "identical")

    def test_region_change_is_changed_and_located(self):
        after = self.image.copy()
        after[20:80, 40:160] = 255
        metrics, _ = pixel_metrics(self.image, after, DEFAULTS)
        self.assertGreater(metrics["changedPct"], 5)
        self.assertEqual(metrics["shape"]["kind"], "solid")
        self.assertEqual(visual_verdict(metrics, None, DEFAULTS), "changed")
        self.assertLess(ssim_luma(self.image, after), 0.98)

    def test_noise_floor_raises_the_same_threshold(self):
        metrics = {"maxDelta": 30, "changedPct": 0.9, "ssim": 0.993}
        self.assertNotEqual(visual_verdict(metrics, None, DEFAULTS), "within noise")
        self.assertEqual(visual_verdict(metrics, {"changedPct": 0.7, "ssim": 0.994}, DEFAULTS), "within noise")

    def test_p95_rule(self):
        before = {"frameP95": 10.0}
        self.assertTrue(perf_block(before, {"frameP95": 11.2}, None, DEFAULTS)["flagged"])     # +1.2 ms
        self.assertTrue(perf_block({"frameP95": 5.0}, {"frameP95": 5.6}, None, DEFAULTS)["flagged"])  # +12 %
        self.assertFalse(perf_block(before, {"frameP95": 10.9}, None, DEFAULTS)["flagged"])    # +0.9 ms, 9 %
        self.assertFalse(perf_block(before, {"frameP95": 11.2}, {"frameP95": 0.5}, DEFAULTS)["flagged"])  # 0.7 beyond noise
        self.assertFalse(perf_block(before, {"frameP95": 7.0}, None, DEFAULTS)["flagged"])     # faster


class ColourTests(unittest.TestCase):
    def test_ciede2000_reference_pairs(self):
        # Sharma, Wu & Dalal (2005) test data, pairs 1 and 17.
        self.assertAlmostEqual(float(delta_e2000(np.array([50, 2.6772, -79.7751]), np.array([50, 0, -82.7485]))), 2.0425, places=3)
        self.assertAlmostEqual(float(delta_e2000(np.array([50, 2.5, 0]), np.array([73, 25, -18]))), 27.1492, places=3)

    def test_lab_white_and_black(self):
        lab = srgb_to_lab(np.array([[255, 255, 255], [0, 0, 0]], dtype=np.uint8))
        self.assertAlmostEqual(float(lab[0, 0]), 100.0, places=2)
        self.assertAlmostEqual(float(lab[1, 0]), 0.0, places=4)

    def test_emd_bounds(self):
        dark, bright = [1.0] + [0.0] * 63, [0.0] * 63 + [1.0]
        self.assertAlmostEqual(emd(dark, dark), 0.0)
        self.assertAlmostEqual(emd(dark, bright), 63 / 64, places=6)

    def test_palette_match_identity(self):
        palette = [{"lab": [50, 10, 10], "hex": "#000000", "share": 0.5}, {"lab": [80, -20, 30], "hex": "#ffffff", "share": 0.5}]
        result = palette_match(palette, list(reversed(palette)))
        self.assertAlmostEqual(result["weightedMean"], 0.0)


if __name__ == "__main__":
    unittest.main()
