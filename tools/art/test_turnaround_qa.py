"""Tests for tools/art/turnaround_qa.py using synthetic turnarounds drawn in the test.

Run:  python -m unittest tools/art/test_turnaround_qa.py -v      (or: python -m pytest tools/art -q)

Every image is generated here (no fixtures on disk). The synthetic character is an A-pose figure on
a 2048 px canvas at 80 % height; the left view is a profile facing image-left and the right view is
its exact mirror, so a clean set must PASS and each defect must flip exactly the check it targets.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import turnaround_qa as tq  # noqa: E402

CANVAS = 2048
H_SUBJ = 0.80 * CANVAS
BASE = (CANVAS + H_SUBJ) / 2.0
SKIN, CLOTH, BELT, BOOT, HAIR, TRIM = (222, 170, 130), (60, 90, 170), (120, 80, 40), (70, 50, 40), (150, 90, 40), (210, 170, 60)
FAST = {"analysis_max_side": 512}


def draw_figure(draw, view, cx, base_y, height, staff=False, cape=False):
    """A simple A-pose character in body units (feet at v=0, crown at v=1). Profiles face image-left."""
    X = lambda u: cx + u * height  # noqa: E731
    Y = lambda v: base_y - v * height  # noqa: E731

    def ell(u0, v0, u1, v1, fill):
        draw.ellipse([X(u0), Y(v1), X(u1), Y(v0)], fill=fill)

    def rect(u0, v0, u1, v1, fill):
        draw.rectangle([X(u0), Y(v1), X(u1), Y(v0)], fill=fill)

    def poly(pts, fill):
        draw.polygon([(X(u), Y(v)) for u, v in pts], fill=fill)

    def limb(a, b, half, fill):
        (sx, sy), (hx, hy) = a, b
        dx, dy = hx - sx, hy - sy
        n = math.hypot(dx, dy)
        nx, ny = -dy / n * half, dx / n * half
        poly([(sx + nx, sy + ny), (hx + nx, hy + ny), (hx - nx, hy - ny), (sx - nx, sy - ny)], fill)

    if view in ("front", "back"):
        if cape:
            poly([(-0.14, 0.80), (0.14, 0.80), (0.30, 0.08), (-0.30, 0.08)], (120, 30, 40))
        rect(-0.10, 0.04, -0.012, 0.50, CLOTH)
        rect(0.012, 0.04, 0.10, 0.50, CLOTH)
        rect(-0.115, 0.0, -0.008, 0.05, BOOT)
        rect(0.008, 0.0, 0.115, 0.05, BOOT)
        poly([(-0.13, 0.80), (0.13, 0.80), (0.11, 0.48), (-0.11, 0.48)], CLOTH)
        rect(-0.115, 0.48, 0.115, 0.53, BELT)
        for sgn in (-1, 1):
            shoulder, hand = (0.13 * sgn, 0.79), (0.32 * sgn, 0.50)
            limb(shoulder, hand, 0.0325, SKIN)
            ell(hand[0] - 0.04, hand[1] - 0.05, hand[0] + 0.04, hand[1] + 0.03, SKIN)
            ell(shoulder[0] - 0.06, shoulder[1] - 0.05, shoulder[0] + 0.06, shoulder[1] + 0.04, TRIM)
        rect(-0.03, 0.78, 0.03, 0.85, SKIN)
        ell(-0.075, 0.83, 0.075, 1.0, HAIR if view == "back" else SKIN)
        if view == "front":
            ell(-0.075, 0.94, 0.075, 1.0, HAIR)
        if staff:
            sx = 0.32 if view == "front" else -0.32
            rect(sx - 0.006, 0.02, sx + 0.006, 0.95, TRIM)
    else:  # profile facing image-left
        if cape:
            poly([(0.05, 0.80), (0.10, 0.80), (0.34, 0.08), (0.04, 0.08)], (120, 30, 40))
        rect(-0.02, 0.04, 0.07, 0.50, CLOTH)
        rect(-0.07, 0.04, 0.02, 0.50, CLOTH)
        rect(-0.13, 0.0, 0.05, 0.05, BOOT)
        poly([(-0.09, 0.80), (0.07, 0.80), (0.06, 0.48), (-0.07, 0.48)], CLOTH)
        rect(-0.075, 0.48, 0.065, 0.53, BELT)
        limb((0.0, 0.79), (-0.04, 0.50), 0.0325, SKIN)
        ell(-0.08, 0.45, 0.0, 0.53, SKIN)
        ell(-0.06, 0.74, 0.06, 0.83, TRIM)
        rect(-0.02, 0.78, 0.03, 0.85, SKIN)
        ell(-0.085, 0.83, 0.06, 1.0, SKIN)
        ell(-0.04, 0.86, 0.07, 1.0, HAIR)
        poly([(-0.084, 0.925), (-0.105, 0.90), (-0.08, 0.885)], SKIN)
        if staff:
            rect(-0.046, 0.02, -0.034, 0.95, TRIM)


def make_view(view, *, scale=1.0, base_shift=0.0, cx_shift=0.0, staff=False, cape=False, alpha=False,
              bg=(255, 255, 255), background=None, shadow=False, canvas=CANVAS):
    """Render one view. 'right' is the mirror image of the 'left' profile (cape draws only where asked)."""
    h = H_SUBJ * scale * canvas / CANVAS
    base_y = (canvas + H_SUBJ * canvas / CANVAS) / 2.0 + base_shift * h
    profile = view in ("left", "right")
    if alpha:
        im = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    elif background is not None:
        im = Image.fromarray(background).convert("RGB")
    else:
        im = Image.new("RGB", (canvas, canvas), bg)
    if shadow and not alpha:
        arr = np.asarray(im).astype(np.float32)
        yy, xx = np.mgrid[0:canvas, 0:canvas]
        g = np.exp(-(((xx - canvas / 2.0) / (0.22 * h)) ** 2) - (((yy - base_y) / (0.025 * h)) ** 2))
        arr *= (1.0 - 0.16 * g)[..., None]
        im = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    draw_figure(d, "left" if profile else view, canvas / 2.0 + cx_shift * canvas, base_y, h, staff=staff, cape=cape)
    if view == "right":
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    return im


def write_set(folder: Path, overrides=None, **common):
    folder.mkdir(parents=True, exist_ok=True)
    overrides = overrides or {}
    for view in ("front", "back", "left", "right"):
        kw = dict(common)
        kw.update(overrides.get(view, {}))
        img = overrides.get(view, {}).get("image")
        if img is None:
            kw.pop("image", None)
            img = make_view(view, **kw)
        img.save(folder / f"{view}.png")
    return folder


def run_qa(folder, extra_cfg=None, **kw):
    cfg = tq.load_config()
    cfg = tq._deep_merge(cfg, FAST)
    if extra_cfg:
        cfg = tq._deep_merge(cfg, extra_cfg)
    inset = tq.discover(str(folder), [], kw.get("order"), kw.get("sheet_order"), None, cfg)
    vds, checks, verdict = tq.analyse(inset, cfg, kw.get("kind", "character"), kw.get("asymmetric", False))
    return inset, vds, checks, verdict


def status_of(checks, cid, scope=None):
    out = [c["status"] for c in checks if c["id"] == cid and (scope is None or c["scope"] == scope)]
    return tq.worst(out) if out else None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tqa_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPassSet(Base):
    def test_clean_set_passes_and_preps(self):
        src = write_set(self.tmp / "pass")
        _, vds, checks, verdict = run_qa(src)
        fails = [(c["id"], c["scope"], c["detail"]) for c in checks if c["status"] == "FAIL"]
        self.assertEqual(verdict, "PASS", fails)
        for cid in ("height", "baseline", "width_front_back", "width_left_right", "mirror_left_right",
                    "mirror_front_back", "background", "margins", "thin_parts", "components", "shadow", "view_count"):
            self.assertEqual(status_of(checks, cid), "PASS", cid)
        lr = next(c for c in checks if c["id"] == "mirror_left_right")
        self.assertGreater(lr["value"]["iou"], 0.97)
        # end to end through the CLI, with --prep
        out, prep = self.tmp / "out", self.tmp / "prep"
        code = tq.run([str(src), "--out", str(out), "--prep", str(prep), "--quiet", "--config", str(self._fast_cfg())])
        self.assertEqual(code, 0)
        for name in ("report.json", "contact.png", "regen_notes.md"):
            self.assertTrue((out / name).is_file(), name)
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "PASS")
        for c in report["checks"]:
            self.assertIn(c["status"], ("PASS", "WARN", "FAIL", "SKIP"))
            self.assertIn("value", c)
            self.assertIn("threshold", c)
        receipt = json.loads((prep / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["credit_guard"]["qa_gate"], "PASS")
        self.assertFalse(receipt["credit_guard"]["eligible_for_tripo"])  # design review still PENDING
        self.assertIsNone(receipt["tripo"]["job_id"])
        prep2 = self.tmp / "prep2"
        tq.run([str(src), "--out", str(self.tmp / "out2"), "--prep", str(prep2), "--quiet", "--config",
                str(self._fast_cfg()), "--design-review", "PASS", "--reviewer", "test"])
        receipt2 = json.loads((prep2 / "receipt.json").read_text(encoding="utf-8"))
        self.assertTrue(receipt2["credit_guard"]["eligible_for_tripo"])
        self.assertEqual(receipt2["credit_guard"]["design_review"]["by"], "test")
        heights, bases, centres = [], [], []
        for view in ("front", "back", "left", "right"):
            p = prep / f"{view}.png"
            self.assertEqual(receipt["views"][view]["output_sha256"], tq.sha256_file(p))
            self.assertEqual(receipt["views"][view]["source_sha256"], tq.sha256_file(src / f"{view}.png"))
            im = np.asarray(Image.open(p).convert("RGB")).astype(int)
            self.assertEqual(im.shape[:2], (CANVAS, CANVAS))
            fg = (255 - im).sum(-1) > 40
            ys, xs = np.nonzero(fg.any(1))[0], np.nonzero(fg.any(0))[0]
            heights.append(ys[-1] - ys[0] + 1)
            bases.append(ys[-1])
            centres.append((xs[0] + xs[-1]) / 2.0)
        self.assertLess(max(heights) - min(heights), 0.006 * CANVAS)
        self.assertLess(max(abs(b - receipt["transform"]["baseline_y"]) for b in bases), 4)
        self.assertLess(max(abs(c - CANVAS / 2.0) for c in centres), 4)

    def test_transparent_set_passes(self):
        src = write_set(self.tmp / "alpha", alpha=True)
        _, vds, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "PASS", [c for c in checks if c["status"] == "FAIL"])
        self.assertTrue(all(vd.has_alpha for vd in vds.values()))
        self.assertEqual(status_of(checks, "background"), "PASS")

    def _fast_cfg(self) -> Path:
        p = self.tmp / "fast.json"
        p.write_text(json.dumps(FAST), encoding="utf-8")
        return p


class TestDefects(Base):
    def test_height_mismatch(self):
        src = write_set(self.tmp / "h", overrides={"back": {"scale": 0.92}})
        _, _, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "height"), "FAIL")
        c = next(c for c in checks if c["id"] == "height")
        self.assertEqual(c["note"]["worst"], "back")
        notes = tq.build_notes("h", checks, {}, verdict, 1, tq.load_config(), "character", tq.InputSet("folder", ""))
        self.assertIn("back view is 8.0 % shorter than the front view", notes)
        self.assertIn("Keep the same scale and baseline", notes)

    def test_cropping(self):
        src = write_set(self.tmp / "crop", overrides={"front": {"base_shift": 0.15}})  # feet pushed below the frame
        _, _, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "margins", "view:front"), "FAIL")
        self.assertEqual(status_of(checks, "margins", "view:back"), "PASS")

    def test_shifted_baseline(self):
        src = write_set(self.tmp / "base", overrides={"back": {"base_shift": -0.06}})  # back view drawn 6 % higher
        _, _, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "baseline"), "FAIL")
        self.assertEqual(status_of(checks, "height"), "PASS")
        c = next(c for c in checks if c["id"] == "baseline")
        self.assertEqual(c["note"]["worst"], "back")

    def test_mirror_mismatch(self):
        src = write_set(self.tmp / "mir", overrides={"right": {"cape": True}})  # cape only in the right profile
        _, _, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "mirror_left_right"), "FAIL")
        self.assertEqual(status_of(checks, "mirror_front_back"), "PASS")
        c = next(c for c in checks if c["id"] == "mirror_left_right")
        self.assertGreater(c["value"]["only_right_frac"], c["value"]["only_left_frac"])
        # declared asymmetry relaxes the left/right FAIL to WARN, per the F6 rule
        _, _, checks2, _ = run_qa(src, asymmetric=True)
        self.assertEqual(status_of(checks2, "mirror_left_right"), "WARN")

    def test_back_view_hallucination(self):
        src = write_set(self.tmp / "fb", overrides={"back": {"cape": True}})  # back shows a cape the front lacks
        _, _, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "mirror_front_back"), "FAIL")

    def test_non_uniform_background(self):
        rng = np.random.default_rng(7)
        noise = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
        busy = np.asarray(Image.fromarray(noise).resize((CANVAS, CANVAS), Image.NEAREST))
        src = write_set(self.tmp / "bg", overrides={"front": {"background": busy}})
        _, _, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "background", "view:front"), "FAIL")
        self.assertEqual(status_of(checks, "background", "view:back"), "PASS")

    def test_thin_part(self):
        src = write_set(self.tmp / "thin", staff=True)  # 0.012 x height staff, about 20 px at 2048
        _, vds, checks, verdict = run_qa(src)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "thin_parts", "view:front"), "FAIL")
        self.assertGreater(vds["front"].metrics["thin"]["area_frac"], 0.02)
        clean = write_set(self.tmp / "thin_ok")
        _, vds2, checks2, _ = run_qa(clean)
        self.assertEqual(status_of(checks2, "thin_parts"), "PASS")


class TestHeuristics(Base):
    def test_contact_shadow_is_separated(self):
        src = write_set(self.tmp / "sh", shadow=True, bg=(200, 200, 204))
        _, vds, checks, verdict = run_qa(src)
        self.assertEqual(status_of(checks, "shadow", "view:front"), "WARN")
        self.assertEqual(status_of(checks, "baseline"), "PASS")
        self.assertEqual(status_of(checks, "height"), "PASS")
        vd = vds["front"]
        true_base = BASE / CANVAS
        self.assertAlmostEqual(vd.metrics["baseline_frac"], true_base, delta=0.006)  # shadow not in the silhouette
        self.assertEqual(verdict, "PASS", [c for c in checks if c["status"] == "FAIL"])

    def test_sheet_autosplit(self):
        views = [make_view(v, canvas=1300) for v in ("front", "left", "back", "right")]
        sheet = Image.new("RGB", (4 * 1150, 1300), (255, 255, 255))
        for i, im in enumerate(views):
            sheet.paste(im.crop((75, 0, 1225, 1300)), (i * 1150, 0))
        path = self.tmp / "sheet.png"
        sheet.save(path)
        inset, vds, checks, verdict = run_qa(path, sheet_order="front,left,back,right")
        self.assertEqual(inset.mode, "sheet")
        self.assertEqual(sorted(inset.views), ["back", "front", "left", "right"])
        self.assertEqual(status_of(checks, "mirror_left_right"), "PASS")
        self.assertEqual(status_of(checks, "height"), "PASS")
        self.assertEqual(verdict, "PASS", [c for c in checks if c["status"] == "FAIL"])

    def test_not_a_turnaround(self):
        folder = self.tmp / "misc"
        folder.mkdir()
        Image.new("RGB", (300, 200), (10, 120, 30)).save(folder / "button_a.png")
        Image.new("RGB", (300, 200), (200, 20, 30)).save(folder / "button_b.png")
        _, vds, checks, verdict = run_qa(folder)
        self.assertEqual(verdict, "REGEN")
        self.assertEqual(status_of(checks, "view_count"), "FAIL")
        out = self.tmp / "out"
        code = tq.run([str(folder), "--out", str(out), "--quiet"])
        self.assertEqual(code, 2)
        self.assertTrue((out / "contact.png").is_file())
        self.assertIn("Missing view(s)", (out / "regen_notes.md").read_text(encoding="utf-8"))

    def test_three_quarter_views_as_profiles(self):
        wide = make_view("front")  # mirrors perfectly, but is no profile
        src = write_set(self.tmp / "q34", overrides={"left": {"image": wide}, "right": {"image": wide}})
        _, _, checks, _ = run_qa(src)
        self.assertEqual(status_of(checks, "mirror_left_right"), "PASS")
        self.assertEqual(status_of(checks, "profile_plausibility"), "WARN")

    def test_palette_match_and_drift(self):
        def palette(colours):
            pal = Image.new("RGB", (900, 140), (255, 255, 255))
            d = ImageDraw.Draw(pal)
            for i, c in enumerate(colours):
                d.rectangle([10 + i * 140, 10, 130 + i * 140, 130], fill=c)
            return pal

        good = write_set(self.tmp / "pal_ok")
        palette([SKIN, CLOTH, BELT, BOOT, HAIR, TRIM]).save(good / "palette.png")
        _, _, checks, _ = run_qa(good)
        self.assertEqual(status_of(checks, "palette"), "PASS")
        bad = write_set(self.tmp / "pal_bad")
        palette([(40, 200, 90), (230, 60, 160), (250, 240, 40), (20, 220, 230), (130, 30, 200), (255, 120, 0)]).save(
            bad / "palette.png")
        _, _, checks2, verdict2 = run_qa(bad)
        self.assertEqual(status_of(checks2, "palette"), "FAIL")
        self.assertEqual(verdict2, "REGEN")

    def test_prep_refuses_regen_unless_forced(self):
        src = write_set(self.tmp / "h", overrides={"back": {"scale": 0.92}})
        prep = self.tmp / "prep"
        fast = self.tmp / "fast.json"
        fast.write_text(json.dumps(FAST), encoding="utf-8")
        code = tq.run([str(src), "--out", str(self.tmp / "o1"), "--prep", str(prep), "--quiet", "--config", str(fast)])
        self.assertEqual(code, 2)
        self.assertFalse(prep.exists())
        code = tq.run([str(src), "--out", str(self.tmp / "o2"), "--prep", str(prep), "--force", "--quiet",
                       "--config", str(fast)])
        self.assertEqual(code, 2)
        receipt = json.loads((prep / "receipt.json").read_text(encoding="utf-8"))
        self.assertFalse(receipt["credit_guard"]["eligible_for_tripo"])
        self.assertTrue(receipt["qa"]["forced"])


class TestPrimitives(unittest.TestCase):
    def test_ciede2000_reference_pairs(self):
        # Sharma, Wu and Dalal (2005) test data
        pairs = [((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
                 ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
                 ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
                 ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0009), 7.1792),
                 ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
                 ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644)]
        for a, b, expected in pairs:
            self.assertAlmostEqual(float(tq.delta_e2000(np.array(a), np.array(b))), expected, places=3)

    def test_disk_morphology_matches_brute_force(self):
        rng = np.random.default_rng(3)
        m = rng.random((50, 61)) > 0.5
        for r in (1.0, 2.5, 4.2):
            ri = int(math.floor(r))
            ys, xs = np.mgrid[-ri:ri + 1, -ri:ri + 1]
            disk = (ys ** 2 + xs ** 2) <= r * r
            pad = np.pad(m, ri, constant_values=False)
            er, di = np.ones_like(m), np.zeros_like(m)
            for dy, dx in zip(ys[disk], xs[disk]):
                sh = pad[ri + dy:ri + dy + m.shape[0], ri + dx:ri + dx + m.shape[1]]
                er &= sh
                di |= sh
            np.testing.assert_array_equal(tq.erode_disk(m, r), er & m)
            np.testing.assert_array_equal(tq.dilate_disk(m, r), di)

    def test_label_counts_components(self):
        m = np.zeros((40, 40), bool)
        m[2:10, 2:10] = True
        m[20:30, 5:8] = True
        m[10, 10] = True  # diagonal touch joins the first square (8-connectivity)
        lab, areas, boxes = tq.label(m)
        self.assertEqual(len(areas), 2)
        self.assertEqual(sorted(areas.tolist()), [30, 65])

    def test_config_file_matches_defaults(self):
        on_disk = json.loads(tq.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, json.loads(json.dumps(tq.DEFAULT_CONFIG)))

    def test_role_names(self):
        self.assertEqual(tq.role_of("front.png"), "front")
        self.assertEqual(tq.role_of("mossling_back_v2.webp"), "back")
        self.assertEqual(tq.role_of("Hero34.png"), "hero34")
        self.assertEqual(tq.role_of("palette.png"), "palette")
        self.assertEqual(tq.role_of("front_left.png"), "ambiguous")
        self.assertIsNone(tq.role_of("ChatGPT Image Oct 1, 2026, 01_13_38 PM.png"))


if __name__ == "__main__":
    unittest.main()
