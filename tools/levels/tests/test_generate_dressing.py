"""Determinism + exclusion tests for tools/levels/generate_dressing.py (lane C-MAP-V3).

Run: python -m unittest discover -s tools/levels/tests -v
"""
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import generate_dressing as g  # noqa: E402
from check_features import ARENA, WARPS, poly_dist  # noqa: E402


class DressingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t1 = g.dumps(g.generate(g.DEFAULT_SEED))
        cls.doc = json.loads(cls.t1)

    def test_two_runs_byte_identical(self):
        t2 = g.dumps(g.generate(g.DEFAULT_SEED))
        self.assertEqual(hashlib.sha256(self.t1.encode()).hexdigest(), hashlib.sha256(t2.encode()).hexdigest())

    def test_file_on_disk_matches(self):
        self.assertEqual(g.OUT.read_text(encoding="utf-8"), self.t1)

    def test_seed_changes_output(self):
        self.assertNotEqual(g.dumps(g.generate(g.DEFAULT_SEED + 1)), self.t1)

    def test_manifest_fields(self):
        self.assertEqual(self.doc["recipe"], g.RECIPE)
        self.assertEqual(self.doc["seed"], g.DEFAULT_SEED)
        ids = [e["id"] for e in self.doc["entries"]]
        self.assertEqual(len(ids), len(set(ids)))
        for e in self.doc["entries"]:
            self.assertEqual(e["y"], 0.0)
            self.assertIn(e["collider"], ("none", "soft", "solid"))

    def test_arena_and_warps_clear(self):
        (ac, ar, aedge) = ARENA
        for e in self.doc["entries"]:
            d = math.hypot(e["x"] - ac[0], e["z"] - ac[1]) - e["footprint_r"]
            if e["collider"] != "none":
                self.assertGreaterEqual(d, aedge, e["id"])
            for wc, wr in WARPS.values():
                self.assertGreater(math.hypot(e["x"] - wc[0], e["z"] - wc[1]), wr, e["id"])

    def test_nothing_solid_on_walk_lines(self):
        L = json.loads(g.LAYOUT.read_text(encoding="utf-8"))
        lines = [([tuple(q) for q in w["points"]], w["width_m"]) for w in L["walk_network"]["items"] if "points" in w]
        for e in self.doc["entries"]:
            if e["collider"] == "none":
                continue
            for pts, w in lines:
                self.assertGreaterEqual(poly_dist((e["x"], e["z"]), pts) - w / 2, e["footprint_r"] + 0.99, e["id"])

    def test_cell_budget(self):
        for cell, s in self.doc["stats"]["per_cell"].items():
            self.assertLessEqual(s["tris_lod0_est"], 40000, cell)

    def test_aquatic_counts(self):
        pc = self.doc["stats"]["per_class"]
        self.assertTrue(30 <= pc["lily_pad"] <= 45)
        self.assertTrue(10 <= pc["lotus"] <= 14)
        self.assertNotIn("tree", " ".join(pc))


if __name__ == "__main__":
    unittest.main()
