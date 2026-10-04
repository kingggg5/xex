"""Seeded procedural dressing for Sunmeadow v3 (lane C-MAP-V3, 2026-10-03).

  python tools/levels/generate_dressing.py            # writes planning/levels/sunmeadow-v3-dressing.json
  python tools/levels/generate_dressing.py --verify   # regenerates twice in memory and proves byte-identical output
                                                      # (and identical to the file on disk)
  python tools/levels/generate_dressing.py --seed 7 --out <path>

Recipe `sunmeadow-dressing/1`. Determinism rules: integer hashing only (splitmix64 of (seed, rule, k)); no `random`
module; every iteration runs over lists in authored order; the output is sorted by an integer key (cell, class index,
rule index, k); floats are rounded to 3 decimals before writing. Landmarks stay explicit anchors in the layout. Trees are
NOT scattered here: the `forest_edge` mask is exported for the trees lane.

Each entry: id, asset_id, variant, class, x, y (always 0), z, yaw, scale, collider (none | soft | solid), footprint_r,
cell, mask, rule.
  collider none  = no collision (flowers, reeds, pebbles, lily pads)
  collider soft  = client camera/foot avoidance only; NOT a server collider (no invisible walls)
  collider solid = server collider request (circle r = footprint_r, y 0..height) -> codex-requests R-COL-1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_features import (ARENA, SPAWN_SLOTS, WARPS, pip, poly_dist, poly_sdist, ring_dist,  # noqa: E402
                            shape_outline)

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "planning/levels/sunmeadow-v2-layout.json"
MONSTERS = ROOT / "planning/levels/sunmeadow-v2-monsters.json"
BASE = ROOT / "planning/sunmeadow-compact-v1.json"
OUT = ROOT / "planning/levels/sunmeadow-v3-dressing.json"
RECIPE = "sunmeadow-dressing/1"
DEFAULT_SEED = 20261003
CELL = 64

MASK64 = (1 << 64) - 1

# class -> (asset_id, variants, collider, tris_lod0, shadow)
CLASSES = {
    "rock_S": ("rock_S", 4, "none", 120, False),
    "rock_M": ("rock_M", 4, "soft", 300, True),
    "rock_L": ("rock_L", 3, "solid", 600, True),
    "boulder": ("boulder", 3, "solid", 900, True),
    "stepping_stone": ("stepping_stone", 3, "none", 80, False),
    "cliff_piece": ("cliff_piece", 4, "solid", 1500, True),
    "bush": ("bush_round", 3, "soft", 400, True),
    "mushroom": ("mushroom_ring_set", 3, "none", 40, False),
    "fallen_log": ("fallen_log", 3, "soft", 500, True),
    "reeds": ("reed_clump", 3, "none", 60, False),
    "lily_pad": ("lily_pad", 3, "none", 16, False),
    "lotus": ("lotus_flower", 2, "none", 120, False),
    "driftwood": ("cove_driftwood", 3, "soft", 200, False),
    "hay_skep": ("hay_skep", 1, "none", 200, False),
    "hay_bale": ("hay_bale_small", 2, "soft", 150, True),
    "fence_run": ("fence_run_post_rail", 2, "solid", 160, True),
    "crate_barrel": ("cove_fishing_props", 3, "soft", 350, True),
}
CLASS_ORDER = list(CLASSES)


# ----------------------------------------------------------------------------------------------- integer hashing
def splitmix(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
    return x ^ (x >> 31)


def rule_key(name):
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "little")


class H:
    """Counter-based integer stream: value k of rule r under seed s = splitmix(s ^ rk ^ splitmix(k))."""
    def __init__(self, seed, rule):
        self.base = splitmix((seed & MASK64) ^ rule_key(rule))
        self.k = 0

    def u(self):
        self.k += 1
        return (splitmix(self.base ^ splitmix(self.k)) >> 11) / float(1 << 53)

    def rng(self, a, b):
        return a + (b - a) * self.u()

    def int(self, a, b):  # inclusive
        return a + int(self.u() * (b - a + 1)) if b > a else a


# ----------------------------------------------------------------------------------------------- world
class World:
    def __init__(self, L, M, base_raw):
        self.L = L
        self.walk_lines = [([tuple(q) for q in w["points"]], w["width_m"], w["id"]) for w in L["walk_network"]["items"]
                           if "points" in w]
        self.decks = [[tuple(q) for q in w["polygon_xz"]] for w in L["walk_network"]["items"] if w["class"] == "deck"]
        self.plazas = [([tuple(q) for q in w["polygon_xz"]], w["id"]) for w in L["walk_network"]["items"]
                       if w["class"] == "plaza"]
        self.solids = []
        for f in L["features"]:
            for c in f.get("colliders", []):
                self.solids.append(shape_outline(c))
            for b in f.get("buildings", []):
                if "center_xz" in b and "diameter_m" in b:
                    self.solids.append(shape_outline({"shape": "circle", "center_xz": b["center_xz"],
                                                      "radius_m": b["diameter_m"] / 2}))
        self.water_polys = [[tuple(q) for q in h["polygon_xz"]] for h in L["hazards"] if "polygon_xz" in h]
        self.water_rects = [h["bounds_xz"] for h in L["hazards"] if "bounds_xz" in h]
        st = next(w for w in L["water"] if w["id"] == "sunmeadow_stream")
        self.stream = [tuple(q) for q in st["points"]]
        self.stream_w = 4.5
        self.pools = [(tuple(w["center_xz"]), w["radius_m"]) for w in L["water"] if w["kind"] == "pool"]
        bl = next(r for r in L["relief"] if r["id"] == "inner_bluff")["footprint_xz"]
        self.bluff = [(bl[0], bl[2]), (bl[1], bl[2]), (bl[1], bl[3]), (bl[0], bl[3])]
        self.cliff = [tuple(q) for q in next(r for r in L["relief"] if r["id"] == "west_cliffs")["polyline_xz"]]
        self.cliff_gap = next(r for r in L["relief"] if r["id"] == "west_cliffs")["gap"]["between_z"]
        self.hills = [tuple(q) for q in next(r for r in L["relief"] if r["id"] == "east_hills")["polyline_xz"]]
        self.homes = []
        for s in M["spawn_rows"]:
            for key in ("home_xz", "proposed_home_xz_v3", "live_xz"):
                if s.get(key):
                    self.homes.append(tuple(s[key]))
        self.patrols = [[tuple(q) for q in s["patrol"]["points"]] + [tuple(s["patrol"]["points"][0])]
                        for s in M["spawn_rows"] if s.get("patrol")]
        self.marks = []  # explicit landmark points (+ radius)
        for l in L["landmarks"]:
            if isinstance(l.get("position_xz"), list):
                self.marks.append((tuple(l["position_xz"]), 2.0))
            if "bounds_xz" in l:
                b = l["bounds_xz"]
                self.plazas.append(([(b[0], b[2]), (b[1], b[2]), (b[1], b[3]), (b[0], b[3])], l["id"]))
        self.marks.append(((-4.0, -70.0), 3.0))  # windstone altar
        self.base_props = []
        import re
        for m in re.finditer(r'"id"\s*:\s*"(sunmeadow_[^"]+)"[^{}]{0,200}?"(?:after_xz|position_xz|center_xz)"\s*:\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)', base_raw):
            pid = m.group(1)
            rr = 1.8 if ("pine" in pid or "oak" in pid or "tree" in pid) else 1.0
            self.base_props.append(((float(m.group(2)), float(m.group(3))), rr))
        self.veg = {v["id"]: [tuple(q) for q in v["polygon_xz"]] for v in L["vegetation_zones"] if "polygon_xz" in v}
        self.stage = L["bounds_xz"]["stage"]

    # distance helpers
    def walk_clear(self, p):
        """Min over lines of (distance to centreline - half width); decks/plazas: signed distance."""
        d = min(poly_dist(p, pts) - w / 2 for pts, w, _ in self.walk_lines)
        for poly in self.decks:
            d = min(d, poly_sdist(p, poly))
        return d

    def in_plaza(self, p):
        return any(pip(p, poly) for poly, _ in self.plazas)

    def water_dist(self, p):
        """Signed: negative inside any water."""
        d = poly_dist(p, self.stream) - self.stream_w / 2
        for c, r in self.pools:
            d = min(d, math.hypot(p[0] - c[0], p[1] - c[1]) - r)
        for poly in self.water_polys:
            d = min(d, poly_sdist(p, poly))
        for b in self.water_rects:
            if b[0] <= p[0] <= b[1] and b[2] <= p[1] <= b[3]:
                d = min(d, -0.1)
        return d

    def solid_dist(self, p):
        d = math.inf
        for poly in self.solids:
            d = min(d, poly_sdist(p, poly))
        return d


# ----------------------------------------------------------------------------------------------- exclusion
def base_excluded(W, p, r, cls):
    """Shared exclusion buffers. Returns a reason string or None."""
    x, z = p
    s = W.stage
    if not (s[0] + r <= x <= s[1] - r and s[2] + r <= z <= s[3] - r):
        return "stage"
    if z >= 8.0 - r:
        return "city_owned"  # support_model: z >= 8 is city-owned
    collider = CLASSES[cls][2]
    path_buf = 1.0 if cls not in ("stepping_stone",) else -99
    if W.walk_clear(p) < r + path_buf:
        return "walk"
    if W.in_plaza(p) and cls not in ("hay_skep", "hay_bale", "crate_barrel", "driftwood"):
        return "plaza"
    for sx, sz in SPAWN_SLOTS:
        if abs(x - sx) <= 1.5 + r and abs(z - sz) <= 1.5 + r:
            return "spawn_slot"
    (ac, ar, aedge) = ARENA
    da = math.hypot(x - ac[0], z - ac[1])
    if da < ar + 0.5 + r:
        return "arena"
    for wid, (wc, wr) in WARPS.items():
        if math.hypot(x - wc[0], z - wc[1]) < wr + 1.5 + r:
            return "warp"
    if W.solid_dist(p) < r + 0.8:
        return "feature_footprint"
    for m, mr in W.marks:
        if math.hypot(x - m[0], z - m[1]) < mr + r:
            return "landmark"
    for b, br in W.base_props:
        if math.hypot(x - b[0], z - b[1]) < br + r + 0.3:
            return "base_prop"
    if collider != "none":
        for h in W.homes:
            if math.hypot(x - h[0], z - h[1]) < 1.6 + r:  # scatter_keep_clear: body r + 1.0
                return "monster_home"
        for pl in W.patrols:
            if poly_dist(p, pl) < 1.2 + r:
                return "patrol"
        for seam in (-64.0, 0.0, 64.0):
            if abs(x - seam) < r + 0.25:
                return "seam_x"
        for seam in (0.0, -64.0, -128.0):
            if abs(z - seam) < r + 0.25:
                return "seam_z"
    if pip(p, W.bluff) and cls not in ("cliff_piece",):
        return "bluff"
    return None


def masks_at(W, p):
    m = []
    if W.water_dist(p) < 3.0:
        m.append("shore")
    for fe in W.L["dressing_zones"]["forest_edges"]:
        if pip(p, W.veg[fe["zone"]]) and poly_dist(p, [tuple(q) for q in fe["polyline_xz"]]) <= fe["band_m"][1]:
            m.append("forest_edge")
            break
    if W.in_plaza(p):
        m.append("feature")
    if not m:
        m.append("meadow")
    return m


# ----------------------------------------------------------------------------------------------- generator
class Gen:
    def __init__(self, W, seed):
        self.W = W; self.seed = seed; self.entries = []; self.rejects = {}

    def taken(self, p, r, gap=0.3):
        for e in self.entries:
            if e["collider"] == "none" and r < 0.5:
                continue
            if math.hypot(p[0] - e["_x"], p[1] - e["_z"]) < r + e["_r"] + gap:
                return True
        return False

    def put(self, cls, rule, k, p, r, yaw, scale, h, check=True, mask=None, extra=None):
        if check:
            why = base_excluded(self.W, p, r, cls)
            if why:
                self.rejects[why] = self.rejects.get(why, 0) + 1
                return False
            if self.taken(p, r, 0.3 if CLASSES[cls][2] != "none" else 0.05):
                self.rejects["overlap"] = self.rejects.get("overlap", 0) + 1
                return False
        asset, nvar, collider, tris, shadow = CLASSES[cls]
        e = {"_x": p[0], "_z": p[1], "_r": r, "_key": (CLASS_ORDER.index(cls), rule, k),
             "asset_id": asset, "variant": h.int(0, nvar - 1), "class": cls,
             "x": round(p[0], 3), "y": 0.0, "z": round(p[1], 3), "yaw": round(yaw % (2 * math.pi), 3),
             "scale": round(scale, 3), "collider": collider, "footprint_r": round(r, 3),
             "cell": f"{math.floor(p[0] / CELL)},{math.floor(p[1] / CELL)}",
             "mask": mask or masks_at(self.W, p)[0], "rule": rule, "shadow": shadow}
        if extra:
            e.update(extra)
        self.entries.append(e)
        return True

    # poisson-disk dart throwing inside a polygon (deterministic candidate stream)
    def poisson(self, cls, rule, poly, count, min_d, r_rng, scale_rng, accept=None, tries=40):
        h = H(self.seed, rule)
        xs = [q[0] for q in poly]; zs = [q[1] for q in poly]
        placed = []; k = 0
        for t in range(count * tries):
            if len(placed) >= count:
                break
            p = (h.rng(min(xs), max(xs)), h.rng(min(zs), max(zs)))
            r = h.rng(*r_rng); yaw = h.rng(0, 2 * math.pi); sc = h.rng(*scale_rng)
            if not pip(p, poly):
                continue
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) < min_d for q in placed):
                continue
            if accept and not accept(p):
                continue
            k += 1
            if self.put(cls, rule, k, p, r, yaw, sc, h):
                placed.append(p)
        return placed

    def cluster(self, cls, rule, center, radius, count, r_rng, scale_rng, accept=None, tries=30):
        h = H(self.seed, rule)
        placed = []; k = 0
        for t in range(count * tries):
            if len(placed) >= count:
                break
            a = h.rng(0, 2 * math.pi); d = radius * math.sqrt(h.u())
            p = (center[0] + d * math.cos(a), center[1] + d * math.sin(a))
            r = h.rng(*r_rng); yaw = h.rng(0, 2 * math.pi); sc = h.rng(*scale_rng)
            if accept and not accept(p):
                continue
            k += 1
            if self.put(cls, rule, k, p, r, yaw, sc, h):
                placed.append(p)
        return placed

    def along(self, cls, rule, pts, spacing, offset_rng, r_rng, scale_rng, accept=None, jitter=0.35):
        h = H(self.seed, rule)
        k = 0; out = []
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L == 0:
                continue
            tx, tz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            nx, nz = -tz, tx
            s = h.rng(0, spacing)
            while s < L:
                off = h.rng(*offset_rng)
                p = (a[0] + tx * s + nx * off, a[1] + tz * s + nz * off)
                r = h.rng(*r_rng); sc = h.rng(*scale_rng)
                yaw = math.atan2(tx, tz) + h.rng(-jitter, jitter)
                s += spacing * h.rng(0.75, 1.25)
                if accept and not accept(p):
                    continue
                k += 1
                if self.put(cls, rule, k, p, r, yaw, sc, h):
                    out.append(p)
        return out


def generate(seed=DEFAULT_SEED, layout=LAYOUT, monsters=MONSTERS, base=BASE, blueprint=True):
    L = json.loads(Path(layout).read_text(encoding="utf-8"))
    M = json.loads(Path(monsters).read_text(encoding="utf-8"))
    W = World(L, M, Path(base).read_text(encoding="utf-8"))
    G = Gen(W, seed)
    DZ = L["dressing_zones"]
    F = {f["id"]: f for f in L["features"]}
    dry = lambda p: W.water_dist(p) > 0.6  # noqa: E731

    # --- cliff pieces along the west cliffs (outside the gap), toe boulders along the bluff
    cl = [q for q in W.cliff]
    gz0, gz1 = W.cliff_gap[1], W.cliff_gap[0]  # [-55, -93] -> lo -93, hi -55
    def out_of_gap(p):
        return not (min(gz0, gz1) - 1.0 <= p[1] <= max(gz0, gz1) + 1.0)
    G.along("cliff_piece", "cliff_west", cl, 7.5, (-3.0, -1.0), (2.2, 3.2), (0.9, 1.3),
            accept=lambda p: out_of_gap(p) and p[0] < -49.0)
    bl = W.bluff
    ring = [(bl[0][0] - 2.0, bl[0][1] - 2.0), (bl[1][0] + 2.0, bl[1][1] - 2.0), (bl[2][0] + 2.0, bl[2][1] + 2.0),
            (bl[3][0] - 2.0, bl[3][1] + 2.0), (bl[0][0] - 2.0, bl[0][1] - 2.0)]
    G.along("boulder", "bluff_base_boulders", ring, 6.5, (-0.6, 0.6), (1.0, 1.6), (0.8, 1.3),
            accept=lambda p: dry(p) and not (p[0] < -6.0 and -47.0 < p[1] < -34.0))
    G.along("boulder", "cliff_debris", cl, 9.0, (2.0, 4.5), (0.9, 1.6), (0.8, 1.2),
            accept=lambda p: out_of_gap(p) and dry(p))

    # --- authored rock clusters (dressing_zones.rock_clusters)
    for rc in DZ["rock_clusters"]:
        cid = rc["id"]; n = rc["count"][1]; smin, smax = rc["size_m"]
        if cid == "grotto_rim_rocks":
            ch = F["waterfall_grotto"]["carve"]["chamber"]; c = ch["center_xz"]
            h = H(seed, cid); k = 0
            for i in range(n):
                a = 2 * math.pi * (i + h.rng(0.1, 0.9)) / n
                p = (c[0] + 5.2 * math.cos(a), c[1] + 4.2 * math.sin(a))
                if abs(math.sin(a)) < 0.45 and math.cos(a) < 0:
                    continue  # tunnel mouth (west)
                if abs(p[1] - c[1]) < 2.4 and p[0] > c[0]:
                    continue  # chamber floor walk line toward the chest
                r = h.rng(0.35, 0.6)
                if W.walk_clear(p) < r + 1.0:
                    continue  # keep the tunnel and chamber walk band + 1 m clear
                k += 1
                G.put("rock_M", cid, k, p, r, h.rng(0, 6.283), h.rng(0.8, 1.2), h, check=False, mask="feature")
        elif "polyline_xz" in rc:
            G.along("rock_M", cid, [tuple(q) for q in rc["polyline_xz"]], 3.0, (0.5, 2.0), (smin / 2, min(1.0, smax / 2)),
                    (0.8, 1.3), accept=lambda p: True)
        elif "polygon" in rc:
            poly = [tuple(q) for q in F["brightwater_cove"]["estuary_headland"]["polygon_xz"]]
            G.poisson("rock_M", cid, poly, n, 2.0, (0.4, 0.9), (0.8, 1.3))
        elif "polygon_xz" in rc:
            G.poisson("rock_M", cid, [tuple(q) for q in rc["polygon_xz"]], n, 4.0, (0.4, 0.8), (0.8, 1.2), accept=dry)
        elif "center_xz" in rc:
            cls = "rock_L" if smax >= 3.0 else "rock_M"
            G.cluster(cls, cid, tuple(rc["center_xz"]), rc["radius_m"], n, (smin / 2, min(1.4, smax / 2)), (0.8, 1.2),
                      accept=dry)

    # --- v2 rock clusters: stream stones (mossy, partly submerged) and meadow painted rocks
    G.along("rock_M", "stream_stones", W.stream[:8], 3.2, (-3.2, 3.2), (0.3, 0.7), (0.8, 1.2),
            accept=lambda p: -1.2 < W.water_dist(p) < 1.6)
    hunt = [(-14, 7.5), (15, 7.5), (15, -9), (-14, -9)]
    G.poisson("rock_M", "meadow_painted_rocks", hunt, 8, 6.0, (0.35, 0.8), (0.8, 1.2), accept=dry)

    # --- small rocks by mask (meadow / forest edge / shore), grounded pebble groups
    G.poisson("rock_S", "rock_S_meadow", [(-46, 8), (44, 8), (44, -104), (-46, -104)], 70, 5.0, (0.15, 0.4),
              (0.8, 1.3), accept=lambda p: dry(p) and "meadow" in masks_at(W, p))
    G.poisson("rock_S", "rock_S_shore", [(-56, 8), (44, 8), (44, -104), (-56, -104)], 34, 2.5, (0.15, 0.35),
              (0.8, 1.2), accept=lambda p: 0.3 < W.water_dist(p) < 2.5)

    # --- forest edges: bushes + a few rock_L anchors (never trees)
    for fe in DZ["forest_edges"]:
        zone = W.veg[fe["zone"]]; edge = [tuple(q) for q in fe["polyline_xz"]]
        inband = lambda p, zone=zone, edge=edge: pip(p, zone) and poly_dist(p, edge) <= fe["band_m"][1]  # noqa: E731
        G.poisson("bush", f"bush_{fe['id']}", zone, 18, 3.2, (0.6, 1.0), (0.8, 1.3), accept=lambda p, f=inband: f(p) and dry(p))
        G.poisson("rock_L", f"rockL_{fe['id']}", zone, 3, 14.0, (0.9, 1.4), (0.8, 1.2), accept=lambda p, f=inband: f(p) and dry(p))

    # --- mushroom rings
    for mr in DZ["mushroom_rings"]:
        h = H(seed, mr["id"]); c = mr["center_xz"]; n = h.int(mr["count"][0], mr["count"][1])
        for i in range(n):
            a = 2 * math.pi * i / n + h.rng(-0.12, 0.12); rr = mr["radius_m"] * h.rng(0.9, 1.1)
            p = (c[0] + rr * math.cos(a), c[1] + rr * math.sin(a))
            G.put("mushroom", mr["id"], i + 1, p, 0.12, h.rng(0, 6.283), h.rng(0.7, 1.3), h,
                  extra={"glow": mr.get("glow")})

    # --- fallen logs
    for fl in DZ["fallen_logs"]:
        n = fl["count"][1]
        if "zone" in fl:
            G.poisson("fallen_log", fl["id"], W.veg[fl["zone"]], n, 10.0, (1.4, 2.4), (0.8, 1.2),
                      accept=lambda p: dry(p) and W.walk_clear(p) > 3.5)
        else:
            G.along("fallen_log", fl["id"], [tuple(q) for q in fl["polyline_xz"]], 9.0, (-1.5, 1.5), (1.4, 2.0),
                    (0.8, 1.1))

    # --- shore reeds: mere rim, stream banks, cove estuary
    mere = [tuple(q) for q in L["water"][[w["id"] for w in L["water"]].index("lotus_mere_pond")]["outline_xz"]]
    G.along("reeds", "reeds_mere", mere + [mere[0]], 1.4, (-0.6, 0.9), (0.25, 0.35), (0.8, 1.3),
            accept=lambda p: W.walk_clear(p) > 0.6)
    for side, offs in (("n", (2.0, 3.3)), ("s", (-3.3, -2.0))):
        G.along("reeds", f"reeds_stream_{side}", W.stream[:8], 2.3, offs, (0.25, 0.35), (0.8, 1.3),
                accept=lambda p: W.walk_clear(p) > 1.0 and math.hypot(p[0] + 14.3, p[1] + 49.7) > 5.0)
    G.poisson("reeds", "cove_estuary_reeds", [tuple(q) for q in F["brightwater_cove"]["estuary_headland"]["polygon_xz"]],
              30, 1.2, (0.25, 0.35), (0.9, 1.4))

    # --- aquatic: lily pads (clustered) + lotus on clusters (in water: own exclusion, no base check)
    pond = [tuple(q) for q in F["lotus_mere"]["geometry"]["pond_outline_polygon_xz"]]
    decks = [[tuple(q) for q in d["polygon_xz"]] for d in F["lotus_mere"]["decks"]]
    terrace = [tuple(q) for q in F["lotus_mere"]["geometry"]["terrace_polygon_xz"]]
    def wet_ok(p, r):
        return (poly_sdist(p, pond) <= -(0.4 + r) and all(poly_sdist(p, d) >= 0.5 + r for d in decks)
                and poly_sdist(p, terrace) >= 0.4 + r)
    h = H(seed, "mere_lily_pads"); n_lily = h.int(30, 45); n_clusters = h.int(7, 9)
    centers = []; t = 0
    while len(centers) < n_clusters and t < 400:
        t += 1
        p = (h.rng(-54.0, -38.6), h.rng(-4.4, 11.3))
        if wet_ok(p, 1.0) and all(math.hypot(p[0] - c[0], p[1] - c[1]) > 3.0 for c in centers):
            centers.append(p)
    k = 0; lily_pts = []; t = 0
    while k < n_lily and t < 2000:
        t += 1
        c = centers[t % len(centers)]
        a = h.rng(0, 6.283); d = 1.3 * math.sqrt(h.u()); r = h.rng(0.18, 0.45)
        p = (c[0] + d * math.cos(a), c[1] + d * math.sin(a))
        if not wet_ok(p, r) or any(math.hypot(p[0] - q[0], p[1] - q[1]) < r + q[2] for q in lily_pts):
            continue
        k += 1; lily_pts.append((p[0], p[1], r))
        G.put("lily_pad", "mere_lily_pads", k, p, r, h.rng(0, 6.283), r / 0.3, h, check=False, mask="shore",
              extra={"y_offset": -0.3})
    h2 = H(seed, "mere_lotus"); n_lotus = h2.int(10, 14)
    order = sorted(range(len(lily_pts)), key=lambda i: (splitmix(seed ^ i) & 0xFFFFFFFF, i))
    for j, i in enumerate(order[:n_lotus]):
        x, z, r = lily_pts[i]
        G.put("lotus", "mere_lotus", j + 1, (x, z), 0.2, h2.rng(0, 6.283), h2.rng(0.85, 1.15), h2, check=False,
              mask="shore", extra={"y_offset": -0.3, "colour": "pink" if h2.u() < 0.7 else "white"})

    # --- stepping flags on the last 9 m of the mere spur (path inlay, collider none, flush)
    sp = next(w for w in L["paths"] if w["id"] == "mere_spur")["points"]
    a, b = sp[-2], sp[-1]
    Ls = math.hypot(b[0] - a[0], b[1] - a[1]); tx, tz = (b[0] - a[0]) / Ls, (b[1] - a[1]) / Ls
    h = H(seed, "mere_stepping_flags")
    for i in range(int(min(Ls, 9.0) / 0.9)):
        s = Ls - 0.6 - 0.9 * i; side = 0.35 if i % 2 else -0.35
        p = (a[0] + tx * s - tz * side, a[1] + tz * s + tx * side)
        G.put("stepping_stone", "mere_stepping_flags", i + 1, p, 0.35, math.atan2(tx, tz) + h.rng(-0.3, 0.3),
              h.rng(0.85, 1.15), h, check=False, mask="feature")

    # --- cove: driftwood on the sand, working clusters at the pier landing (reference R09/R12)
    beach = [tuple(q) for q in F["brightwater_cove"]["geometry"]["beach_polygon_xz"]]
    cove_path = [tuple(q) for q in next(w for w in L["paths"] if w["id"] == "cove_path")["points"]]
    for i, c in enumerate([(-46.6, -77.6), (-38.6, -78.0), (-38.4, -83.0)]):
        h = H(seed, f"cove_working_{i}")
        G.put("crate_barrel", "cove_working_clusters", i + 1, c, 0.8, h.rng(0, 6.283), h.rng(0.9, 1.1), h,
              check=True)
    G.poisson("driftwood", "cove_driftwood", beach, 4, 4.0, (0.7, 1.1), (0.8, 1.2),
              accept=lambda p: poly_dist(p, cove_path) > 3.0)

    # --- croft: hay skeps on the shelf (from the explicit anchors), hay bales, a field fence
    for i, q in enumerate(F["sunmeadow_croft"]["hero_dressing"][0]["positions_xz"]):
        h = H(seed, f"croft_skep_{i}")
        G.put("hay_skep", "croft_hay_skeps", i + 1, tuple(q), 0.3, math.pi + h.rng(-0.2, 0.2), h.rng(0.95, 1.05), h,
              check=False, mask="feature", extra={"y_offset": 1.1, "on": "croft_skep_shelf"})
    for i, c in enumerate([(44.6, 1.4), (37.6, 0.9), (22.0, -4.6)]):
        h = H(seed, f"hay_bale_{i}")
        G.put("hay_bale", "hay_bales", i + 1, c, 0.6, h.rng(0, 6.283), h.rng(0.9, 1.1), h)
    h = H(seed, "croft_field_fence")
    for i in range(7):  # 2 m post-and-rail sections along the croft meadow's east edge (hill toe behind it)
        p = (44.6, -17.0 - 2.0 * i)
        why = base_excluded(W, p, 0.95, "fence_run")
        if why:
            G.rejects[why] = G.rejects.get(why, 0) + 1
            continue
        G.put("fence_run", "croft_field_fence", i + 1, p, 0.95, 0.0 + h.rng(-0.03, 0.03), 1.0, h, check=False,
              mask="meadow", extra={"length_m": 2.0})

    # --- finish: stable integer order, ids, stats
    ents = sorted(G.entries, key=lambda e: (e["cell"], e["_key"]))
    out_entries = []
    per_class_n = {}
    for e in ents:
        per_class_n[e["class"]] = per_class_n.get(e["class"], 0) + 1
        e2 = {"id": f"dr_{e['class']}_{per_class_n[e['class']]:03d}"}
        for k_ in ("asset_id", "variant", "class", "x", "y", "z", "yaw", "scale", "collider", "footprint_r", "cell",
                   "mask", "rule", "shadow"):
            e2[k_] = e[k_]
        for k_ in ("y_offset", "glow", "colour", "on", "length_m"):
            if k_ in e:
                e2[k_] = e[k_]
        out_entries.append(e2)
    stats = {}
    for e in out_entries:
        c = stats.setdefault(e["cell"], {"counts": {}, "tris_lod0_est": 0, "solid": 0, "shadow_casters": 0})
        c["counts"][e["class"]] = c["counts"].get(e["class"], 0) + 1
        c["tris_lod0_est"] += CLASSES[e["class"]][3]
        c["solid"] += e["collider"] == "solid"
        c["shadow_casters"] += bool(e["shadow"])
    for c in stats.values():
        c["counts"] = dict(sorted(c["counts"].items()))
        c["within_budget"] = c["tris_lod0_est"] <= 40000
    doc = {
        "schema": "xexoria.dressing/1",
        "region": "sunmeadow",
        "recipe": RECIPE,
        "seed": seed,
        "params": {"layout": "planning/levels/sunmeadow-v2-layout.json", "layout_version": L["version"],
                   "monsters": "planning/levels/sunmeadow-v2-monsters.json", "cell_m": CELL},
        "generator": "tools/levels/generate_dressing.py",
        "coords": "Babylon world XZ metres, y = 0 support (y_offset only for floating/stacked items)",
        "collider_classes": {"none": "no collision", "soft": "client-only avoidance; never a server collider",
                             "solid": "server collider request: circle r = footprint_r (codex-requests R-COL-1)"},
        "masks": {"meadow": "open land outside the other masks", "forest_edge": "dressing_zones.forest_edges bands "
                  "(also the trees-lane mask)", "shore": "within 3 m of any water edge", "feature": "walk plazas and "
                  "feature areas (curated, low density)"},
        "forest_edge_mask": DZ["forest_edges"],
        "exclusions": ["walk lines +1 m (decks/plazas signed)", "spawn slots +1.5 m", "arena 12.5 m", "warps +1.5 m",
                       "feature colliders/buildings +0.8 m", "landmarks + base props", "monster homes 1.6 m and patrols "
                       "1.2 m (soft/solid)", "64 m cell seams (soft/solid)", "city-owned z >= 8", "inner bluff mass"],
        "budget": {"triangles_lod0_per_cell_layout": L["budgets_per_64m_cell"]["triangles_lod0_excluding_vegetation"],
                   "existing_cell_peak": 30811, "dressing_target_per_cell": 40000,
                   "basis": "120k layout budget - terrain spec 7.4 maxima (ground 12k + hills 8k + rock 16k + decals 4k) - "
                            "feature hero props ~25k - water ~5k = ~55k; dressing <= 40k keeps ~15k slack"},
        "stats": {"total": len(out_entries), "per_class": dict(sorted(per_class_n.items())),
                  "per_cell": dict(sorted(stats.items())), "rejects": dict(sorted(G.rejects.items()))},
        "entries": out_entries,
    }
    return add_blueprint_p0(doc, L, seed) if blueprint else doc


def add_blueprint_p0(doc, layout, seed):
    """Explicit authored anchors; independent per-item integer streams only."""
    source = ROOT / 'planning/levels/sunmeadow-blueprint-v1.json'
    bp = json.loads(source.read_text(encoding='utf-8'))
    wanted = ['R1','R2','R4','R5','R6','S1','S2','F1','F5','T1','P1','P2','PL1','C2','C3','ST1','ST2','ST3','ST4','L1']
    items = {i['id']: i for i in bp['items'] if i.get('pr') == 'P0'}
    if set(items) != set(wanted): raise ValueError('Blueprint P0 set changed; review exact owner scope')
    entries, coverage, colliders = [], [], []
    def height(x,z):
        poly=items['T1']['poly']; c=(30,-94)
        if not pip((x,z),poly): return 0.0
        ratios=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            dx,dz=b[0]-a[0],b[1]-a[1];den=dx*(a[1]-c[1])-dz*(a[0]-c[0]);ratios.append((dx*(z-c[1])-dz*(x-c[0]))/den)
        r=max(0,max(ratios));rings=[(1,0),(.76,2.1),(.43,4.3),(.12,5.7),(0,6)]
        for (outer,hy),(inner,iy) in zip(rings,rings[1:]):
            if r>=inner:return round(hy+(iy-hy)*(outer-r)/(outer-inner),3)
        return 6.0
    def add(item, asset, dx=0, dz=0, h=None, size=None, yaw=None, r=.5, solid=True, base=0, standin=False, **extra):
        anchor=items[item].get('xz',items[item].get('line',items[item].get('poly'))[0] if not items[item].get('xz') else None)
        rng=H(seed,'blueprint:'+item+':'+str(sum(e['blueprint_id']==item for e in entries)))
        x,z=round(anchor[0]+dx,3),round(anchor[1]+dz,3)
        e={'id':f'bp_{item}_{sum(e["blueprint_id"]==item for e in entries):03d}','blueprint_id':item,'asset_id':asset,
           'class':'blueprint','variant':1,'x':x,'y':0.0,'z':z,'yaw':round(yaw if yaw is not None else rng.rng(0,math.tau),4),
           'scale':1.0,'collider':'solid' if solid else 'none','footprint_r':r,'cell':f'{math.floor(x/64)},{math.floor(z/64)}',
           'landmark':True,'shadow':True,'rule':'blueprint_p0','mask':'explicit','visual_base_y':round(base,3),'standin':standin,**extra}
        if h is not None:e['target_height']=h
        if size is not None:e['target_size_xyz']=size
        entries.append(e)
        if solid:
            c={'id':e['id'],'blueprint_id':item,'shape':'box' if size else 'circle','center_xz':[x,z],'radius_m':r,'support_y':0,'visual_base_y':base,'admission':'UNVERIFIED'}
            if size:c.update({'size_xz':[size[0],size[2]],'yaw':e['yaw'],'height_m':size[1]})
            colliders.append(c)
    # Rock gardens retain a hero, intermediate forms and small edge accents.
    add('R1','sm_boulder_03',h=3,r=1.7)
    for dx,dz,h in [(-2.4,-.4,1.2),(2.1,-.8,1.5),(-1,2.8,1),(2.8,2.3,1.3)]:add('R1','sm_medium_06',dx,dz,h,r=.8)
    for k in range(6):
        dx,dz=(math.cos(k*1.047)*4.1,math.sin(k*1.047)*3.6) if k<4 else ((-2.05 if k==4 else 2.05),.7)
        add('R1','sm_small_03',dx,dz,.45,r=.3,solid=False)
    for dx,dz,h in [(0,0,3.7),(1.9,2.2,2.7),(-1.8,-2.1,2)]:add('R2','sm_boulder_04',dx,dz,h,r=1.7)
    for k in range(5):add('R2','sm_pebbles_02',2.8+k*.2,-2.5+k*.9,.25,r=.4,solid=False)
    add('R4','sm_cliff_corner_05',h=6,size=[3.4,6,2.7],r=2,base=-1.2)
    add('R4','sm_cliff_wall_03',5,-7,4.7,size=[2.8,4.7,2.3],r=1.8,base=-1.2)
    for dx,dz,h in [(-1.7,0,2.5),(0,0,3.2),(1.7,.6,4)]:add('R5','sm_boulder_03',dx,dz,h,size=[1.5,h,1.2],r=.95)
    for k in range(6):add('R5','sm_lotus_open',math.cos(k)*3,math.sin(k)*3,.25,r=.2,solid=False)
    add('R6','sm_cliff_corner_05',h=4.8,size=[5.2,4.8,3.4],r=3.1,base=height(36,-97))
    add('R6','sm_cliff_cap_06',-1.9,1.2,size=[4,1.3,3],r=2.5,base=height(34.1,-95.8)+2.3)
    for sid in ['S1','S2']:
        add(sid,'sm_ruin_slab_01',size=[2.3,1.2,2.3],yaw=0,r=1.6)
        add(sid,'blueprint_cc0_guardian',h=6,yaw=math.pi,r=1.6,base=1.2,standin=True)
    for fid,asset,rail_height in [('F1','sm_croft_fence',1.15),('F5','blueprint_hunter_stakes',1.5)]:
        line=items[fid]['line']; origin=line[0]
        for a,b in zip(line,line[1:]):
            dx,dz=b[0]-a[0],b[1]-a[1]; count=math.ceil(math.hypot(dx,dz)/2.5)
            for k in range(count):
                t=(k+.5)/count;add(fid,asset,a[0]+t*dx-origin[0],a[1]+t*dz-origin[1],size=[math.hypot(dx,dz)/count,rail_height,.22],yaw=math.atan2(-dz,dx),r=.35)
        if fid=='F1':
            for k in range(6):add(fid,'blueprint_cc0_sheep',3+(k%3)*2, -3-(k//3)*3,h=.9,r=.5,solid=False,standin=True)
    # A true shaped terrain mesh (not a proxy); server remains flat and the ring is a root admission request.
    poly=items['T1']['poly']; centre=[30,-94]; positions=[]; colours=[];indices=[]
    for ratio,y in [(1,0),(.76,2.1),(.43,4.3),(.12,5.7)]:
        for x,z in poly:positions.extend([centre[0]+(x-centre[0])*ratio,y,centre[1]+(z-centre[1])*ratio]);colours.extend([.64,.71,.28,1] if y<3 else [.71,.6,.31,1])
    positions.extend([*centre[:1],6,centre[1]]);colours.extend([.71,.6,.31,1])
    n=len(poly)
    for ring in range(3):
        for k in range(n):a=ring*n+k;b=ring*n+(k+1)%n;c=(ring+1)*n+k;d=(ring+1)*n+(k+1)%n;indices.extend([a,c,b,b,c,d])
    for k in range(n):indices.extend([3*n+k,4*n,3*n+(k+1)%n])
    for a,b in zip(poly,poly[1:]+poly[:1]):
        count=math.ceil(math.dist(a,b)/3)
        for k in range(count):t=(k+.5)/count;add('T1','sm_boulder_04',a[0]+(b[0]-a[0])*t-poly[0][0],a[1]+(b[1]-a[1])*t-poly[0][1],size=[3.5,1.4,2.1],yaw=math.atan2(b[0]-a[0],b[1]-a[1]),r=1.65)
    # Only this secondary ring rock overlaps the live Mossling home. Embed it into the authored slope.
    moved=next(e for e in entries if e['id']=='bp_T1_035')
    moved.update(x=17.5,z=-90,visual_base_y=round(height(17.5,-90)-.25,3),cell='0,-2')
    moved_collider=next(c for c in colliders if c['id']==moved['id'])
    moved_collider.update(center_xz=[moved['x'],moved['z']],visual_base_y=moved['visual_base_y'])
    water=[]
    for key,c,rx,rz in [('P1a',[33,-78],1.6,.85),('P1b',[30.8,-77.1],1.2,.75),('P1c',[35.1,-79],1.35,.7),('P2',[22,-56],3.5,2)]:
        outline=[[round(c[0]+rx*math.cos(k*math.tau/12),3),round(c[1]+rz*math.sin(k*math.tau/12),3)] for k in range(12)]
        water.append({'id':'blueprint_'+key,'blueprint_id':'P1' if key.startswith('P1') else 'P2','kind':'pond','center_xz':c,'outline_xz':outline,'surface_y':-.03,'bed_y':-.21 if key.startswith('P1') else -.42,'shallow_band_m':.5,'bank_width_m':.6,'still':True,'mud':key.startswith('P1'),'physical_support_y':0,'admission':'UNVERIFIED'})
    for k in range(5):add('P2','sm_stepstone_03',(k-2)*1.25,0,size=[.9,.18,.65],yaw=.2*k,r=.55,solid=False,base=-.18)
    for k in range(8):a=k*math.tau/8;add('P2','sm_reeds_02',3.65*math.cos(a),2.15*math.sin(a),h=.8,r=.25,solid=False)
    for k in range(10):
        a=k*2.399;dx,dz=(math.cos(a)*5.2,math.sin(a)*4.2) if k<8 else (-5-(k-8)*2,1.8)
        add('PL1','blueprint_cc0_palm',dx,dz,h=7,yaw=math.atan2(-18-dx,-5-dz),r=.65,standin=True,pitch=math.radians(5+k%3*5))
    for cid in ['C2','C3']:
        add(cid,'blueprint_cc0_cart',size=[2.5,1.8,3.2],yaw=math.pi*.55,r=1.65,standin=True)
        add(cid,'sm_market_goods_jars' if cid=='C2' else 'sm_croft_skep_2',.3,.2,h=1.0,r=.6,base=.8,solid=False)
        add(cid,'sm_market_goods_apples' if cid=='C2' else 'sm_croft_firewood',1.6,.9,h=.6,r=.5,solid=False)
    add('ST1','blueprint_cc0_windmill',h=11,yaw=math.pi,r=3.5,standin=True)
    for asset,dx,dz,yaw in [('sm_market_stall_a',0,0,.05),('sm_market_stall_b',-3.6,1.8,.55),('sm_market_stall_c',1.8,3.6,-.55)]:add('ST2',asset,dx,dz,h=2.9,yaw=yaw,r=1.9)
    for k in range(3):add('ST2',['sm_market_goods_apples','sm_market_goods_bread','sm_market_goods_carrots'][k],-2+k*1.5,-1.5,h=.55,r=.4,solid=False)
    for dx,dz,yaw in [(-1.8,0,.1),(1.3,-2,1.0)]:add('ST3','blueprint_cc0_tent',dx,dz,h=2.5,yaw=yaw,r=1.5,standin=True)
    add('ST3','sm_cove_rod_rack',0,-3,h=1.8,r=.7)
    add('ST3','sm_croft_campfire',-.8,-2,h=.5,r=.6,solid=False)
    base=height(31,-95)
    for dx,dz,asset,h in [(-1.9,-1.9,'sm_cliff_corner_04',8),(1.9,-1.9,'sm_column_broken',5.3),(-1.9,1.9,'sm_column_intact',6.5),(1.9,1.9,'sm_ruin_arch_fragment',5.8)]:add('ST4',asset,dx,dz,size=[1.6,h,1.2],yaw=0,r=.9,base=height(31+dx,-95+dz))
    add('ST4','sm_brazier_cresset',0,0,h=.75,r=.4,solid=False,base=base)
    add('L1','sm_brazier_pillar',size=[.35,2.5,.35],yaw=0,r=.3,solid=False,night_lantern=True)
    for k,(x,z) in enumerate([(-5,0),(5,-40),(-4,-60),(6,-81),(9,-99),(21,1),(33,-13)]):add('L1','sm_brazier_pillar',x-3,z+20,size=[.35,2.5,.35],yaw=0,r=.3,solid=False,night_lantern=True)
    baseline=doc['entries'];filtered=[]
    for e in baseline:
        overlap=any(math.hypot(e['x']-p['x'],e['z']-p['z']) < e['footprint_r']+p['footprint_r']+.25 for p in entries if p['collider']=='solid')
        overlap=overlap or pip((e['x'],e['z']),poly) or any(pip((e['x'],e['z']),w['outline_xz']) for w in water)
        if not overlap:filtered.append(e)
    for key in wanted:coverage.append({'id':key,'pr':'P0','anchor':items[key].get('xz',items[key].get('line',items[key].get('poly'))[0] if not items[key].get('xz') else None),'entries':[e['id'] for e in entries if e['blueprint_id']==key],'assets':sorted(set(e['asset_id'] for e in entries if e['blueprint_id']==key)),'remaining_components':{'P1':['hoof-print detail and gameplay splash events'],'P2':['dragonflies'],'F1':['sheep depend on licensed vendor manifest'],'S1':['F25 original winged guardian final swap'],'S2':['F25 original winged guardian final swap'],'ST1':['turning sails requires separable vendor motion metadata'],'ST3':['drying pelts/weapon rack semantics use rod-rack stand-in'],'ST4':['banner remnant']}.get(key,[])})
    doc['baseline_entries']=baseline;doc['entries']=filtered+entries
    doc['blueprint']={'schema':'xexoria.blueprint-p0-dressing/1','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'items':coverage,'removed_scatter':len(baseline)-len(filtered),'water_bodies':water,'mound':{'id':'T1','polygon_xz':poly,'centre_xz':centre,'max_height_m':6,'positions':positions,'indices':indices,'colours':colours,'physical_support_y':0,'walkable':False},'collider_requests':colliders,'admission':'UNVERIFIED root required'}
    doc['stats']['baseline_total']=len(baseline);doc['stats']['blueprint_entries']=len(entries);doc['stats']['total']=len(doc['entries'])
    return doc


def dumps(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=False) + "\n"


def generate_p1(seed=DEFAULT_SEED):
    """Versioned opt-in reuse slice. Never regenerate or write the frozen P0 dataset."""
    doc=json.loads(OUT.read_text(encoding='utf-8'))
    bp=json.loads((ROOT/'planning/levels/sunmeadow-blueprint-v1.json').read_text(encoding='utf-8'))
    plan=json.loads((ROOT/'planning/evidence/blueprint-p0-20261003/wave-next-plan.json').read_text(encoding='utf-8'))
    wanted=['R3','R7','R8','S3','S4','S5','F2','F3','F4','T2','T3','P3','C4','C5','ST5','ST6','ST7','ST8','L2','N1']
    items={i['id']:i for i in bp['items'] if i.get('pr')=='P1'}
    if set(items)!=set(wanted):raise ValueError('Exact P1 authority changed')
    L=json.loads(LAYOUT.read_text(encoding='utf-8'));M=json.loads(MONSTERS.read_text(encoding='utf-8'))
    W=World(L,M,BASE.read_text(encoding='utf-8'));entries=[];colliders=[];rejected=[];mounds=[]
    frozen=doc['entries'];m=doc['blueprint']['mound'];centre=m['centre_xz']
    def mound_y(x,z):
        poly=m['polygon_xz']
        if not pip((x,z),poly):return 0
        r=max(( (b[0]-a[0])*(z-centre[1])-(b[1]-a[1])*(x-centre[0]))/((b[0]-a[0])*(a[1]-centre[1])-(b[1]-a[1])*(a[0]-centre[0])) for a,b in zip(poly,poly[1:]+poly[:1]))
        rings=[(1,0),(.76,2.1),(.43,4.3),(.12,5.7),(0,6)]
        for (outer,h),(inner,ih) in zip(rings,rings[1:]):
            if r>=inner:return h+(ih-h)*(outer-r)/(outer-inner)
        return 6
    def clear(x,z,r):
        if W.walk_clear((x,z))<r+.5:return 'walk_clearance'
        if math.hypot(x,z+68)<12+r+.5:return 'arena_keepclear'
        if any(math.hypot(x-h[0],z-h[1])<r+1.6 for h in W.homes):return 'live_home'
        if any(math.hypot(x-e['x'],z-e['z'])<r+e['footprint_r']+.15 for e in frozen if e.get('blueprint_id') and e['collider']=='solid'):return 'P0_footprint'
        return None
    def add(item,asset,x=None,z=None,h=None,size=None,yaw=0,r=.5,solid=True,base=0,absolute=False,standin=False,primary=False,**extra):
        anchor=items[item].get('xz',items[item].get('line',items[item].get('poly'))[0] if not items[item].get('xz') else None)
        x,z=(anchor if x is None else [x,z]);x,z=round(x,3),round(z,3)
        if size:r=max(r,round(math.hypot(size[0]/2,size[2]/2),3))
        why=clear(x,z,r) if solid and not primary else None
        if why:rejected.append({'item':item,'asset':asset,'xz':[x,z],'reason':why});return
        eid=f'bp1_{item}_{sum(e["blueprint_id"]==item for e in entries):03d}'
        e={'id':eid,'blueprint_id':item,'blueprint_wave':'P1','asset_id':asset,'class':'blueprint','variant':1,'x':x,'y':0,'z':z,'yaw':round(yaw,4),'scale':1,'collider':'solid' if solid else 'none','footprint_r':r,'cell':f'{math.floor(x/64)},{math.floor(z/64)}','landmark':True,'shadow':True,'rule':'blueprint_p1','mask':'explicit','visual_base_y':round(base,3),'standin':standin,**extra}
        if absolute:e['visual_absolute_base_y']=round(base,3)
        if h is not None:e['target_height']=h
        if size is not None:e['target_size_xyz']=size
        entries.append(e)
        if solid:
            rolled=abs(e.get('roll',0));sx=size[0]*abs(math.cos(rolled))+size[1]*abs(math.sin(rolled)) if size else None;hy=size[1]*abs(math.cos(rolled))+size[0]*abs(math.sin(rolled)) if size else h
            colliders.append({'id':eid,'blueprint_id':item,'shape':'box' if size else 'circle','center_xz':[x,z],'radius_m':r,'size_xz':[round(sx,3),size[2]] if size else None,'yaw':e['yaw'],'height_m':round(hy,3) if hy is not None else None,'support_y':0,'visual_base_y':base,'visual_absolute_base_y':base if absolute else None,'admission':'UNVERIFIED_ROOT'})
    add('R3','sm_boulder_01',h=2.4,r=1.4,primary=True)
    for z in [-24,-31,-38,-45]:
        if z!=-31:add('R3','sm_medium_03',-49.8,z,h=1.3,r=.8)
        add('R3','sm_ruin_slab_01',-47.9,z+.8,size=[1.7,.3,1.2],r=.8)
    for x,z in [(40,-34),(41,-54)]:
        add('R7','sm_cliff_corner_04',x,z,size=[3.3,3.5,2.7],r=1.7,base=-1.2,primary=True)
        add('R7','sm_cliff_cap_06',x-1,z+.6,size=[2.3,.7,2.2],r=1.1,base=1.3)
    for cx,cz in [(-24,-99),(22,-100)]:
        add('R8','sm_boulder_02',cx,cz,h=2.4,r=1.4,base=mound_y(cx,cz)-.35 if cx>0 else -.25,absolute=cx>0,primary=True)
        for k in range(4):
            x,z=cx+math.cos(k*1.57)*2.4,cz+math.sin(k*1.57)*2.2
            add('R8','sm_medium_04' if k<2 else 'sm_small_03',x,z,h=.9 if k<2 else .45,r=.55 if k<2 else .25,solid=k<2,base=max(0,mound_y(x,z)-.2) if cx>0 else -.1,absolute=cx>0)
    for sid,height in [('S3',4),('S4',2.4)]:
        add(sid,'sm_ruin_slab_02',size=[1.5,.35,1.5],r=.9,primary=True)
        add(sid,'blueprint_cc0_guardian',h=height,r=1.0,base=.35,standin=True,primary=True)
    for k in range(5):add('S5','sm_lotus_open',-26+math.cos(k*1.257)*3,-31+math.sin(k*1.257)*2.5,h=.3,r=.2,solid=False)
    for key,height,gap in [('F2',.85,False),('F3',1.0,True),('F4',.85,True)]:
        line=items[key]['line']
        for si,(a,b) in enumerate(zip(line,line[1:])):
            length=math.dist(a,b);count=math.ceil(length/2.5)
            for k in range(count):
                if gap and k%2==1:continue
                t=(k+.5)/count;x,z=a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t
                add(key,'sm_croft_fence',x,z,size=[length/count*.85,height,.16],yaw=math.atan2(-(b[1]-a[1]),b[0]-a[0]),r=.25,solid=key!='F3',roll=.15 if key=='F4' else 0)
    for x in [20,22,24]:
        for z in [4,5.5]:add('F2','sm_market_goods_carrots',x,z,h=.24,r=.25,solid=False,standin=True)
    def mound(item,suffix,poly,height):
        if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))>0:poly=[poly[0]]+poly[:0:-1]
        c=[sum(p[0] for p in poly)/len(poly),sum(p[1] for p in poly)/len(poly)];pos=[];idx=[];colors=[];n=len(poly)
        for ratio,y in [(1,0),(.55,height*.7)]:
            for x,z in poly:pos.extend([c[0]+(x-c[0])*ratio,y,c[1]+(z-c[1])*ratio]);colors.extend([.64,.71,.28,1] if item=='T2' else [.85,.725,.51,1])
        pos.extend([c[0],height,c[1]]);colors.extend([.64,.71,.28,1] if item=='T2' else [.85,.725,.51,1])
        for k in range(n):a=k;b=(k+1)%n;cc=n+k;d=n+(k+1)%n;idx.extend([a,cc,b,b,cc,d,n+k,2*n,n+(k+1)%n])
        mounds.append({'id':item+'_'+suffix,'blueprint_id':item,'polygon_xz':poly,'positions':pos,'indices':idx,'colours':colors,'centre_xz':c,'max_height_m':height,'physical_support_y':0,'walkable':False,'closure_required':True,'admission':'DEPENDENCY_ROOT_TERRAIN'})
    # Closed low lobes selected from the authored region; path bands are cut out, never raised.
    for suffix,poly in [('west',items['T2']['poly']),('east',[[20,-40],[40,-40],[40,-58],[20,-58]])]:
        count=0
        for x in range(math.ceil(min(p[0] for p in poly))+3,math.floor(max(p[0] for p in poly))-2,6):
            for z in range(math.ceil(min(p[1] for p in poly))+3,math.floor(max(p[1] for p in poly))-2,6):
                outline=[[x+2.4*math.cos(k*math.tau/8),z+2.4*math.sin(k*math.tau/8)] for k in range(8)]
                if count<5 and all(pip(p,poly) and W.walk_clear(p)>.6 for p in outline) and clear(x,z,2.4) is None:
                    mound('T2',suffix+str(count),outline,.55);count+=1
    mound('T3','dune',items['T3']['poly'],1.35)
    for k in range(4):add('T3','sm_cove_driftwood_1',-35+(-1 if k%2 else 1),-74-k*3,h=.3,r=.3,solid=False,base=.6,absolute=True)
    add('C4','blueprint_cc0_cart',size=[2.3,1.6,2.9],yaw=.6,r=1.5,standin=True,primary=True)
    add('C4','sm_cove_rod_rack',21.6,-14.8,h=1.6,r=.55,standin=True)
    add('C5','blueprint_cc0_cart',size=[2.5,1.8,3],yaw=.9,roll=math.pi/2,r=1.7,standin=True,primary=True)
    for k in range(4):add('C5','sm_market_goods_apples',8.5+k*.8,-88.2+(k%2)*.8,h=.35,r=.3,solid=False)
    # Stone modules span a4m opening; leg compounds stay separate from the non-solid crown.
    for x in [-3.5,1.5]:add('ST5','sm_column_broken',x,-30,size=[.8,4.2,.8],r=.6,primary=True)
    add('ST5','sm_ruin_arch_fragment',-1,-30,size=[5.8,2.0,.8],base=3.4,r=.5,solid=False,standin=True)
    add('ST6','sm_croft_trough',size=[3.6,.65,.9],r=1.8,standin=True,primary=True)
    for k in range(3):add('ST6','sm_croft_skep_1' if k%2 else 'sm_croft_skep_2',44+k,-6,h=.8,r=.5,base=.65,solid=False)
    add('ST7','sm_croft_hut',size=[4.3,3.0,4.3],r=2.4,base=.8,standin=True,primary=True)
    for dx,dz in [(-1.6,-1.6),(1.6,-1.6),(-1.6,1.6),(1.6,1.6)]:add('ST7','sm_pier_bollard',-36+dx,-92+dz,size=[.23,.8,.23],r=.2,primary=True)
    add('ST7','sm_cove_rowboat',-40,-92,size=[1.5,.55,3.3],yaw=.8,r=.8,solid=False)
    add('ST7','sm_cove_sailing_skiff',-40,-96,h=4.2,yaw=1.1,r=.9,solid=False)
    add('ST7','sm_cove_rod_rack',-34.6,-94,h=1.4,r=.5)
    add('ST8','sm_croft_well',size=[1.3,1.8,1.3],r=.6,standin=True,solid=False,primary=True)
    for x,z in [items['L2']['xz'],[4,-54]]:add('L2','sm_brazier_cresset',x,z,h=1.8,r=.55,primary=True,night_lantern=True)
    fixed=[e for e in frozen if e.get('blueprint_id')]
    scatter=[e for e in frozen if not e.get('blueprint_id')]
    kept=[]
    for e in scatter:
        if any(math.hypot(e['x']-p['x'],e['z']-p['z'])<e['footprint_r']+p['footprint_r']+.25 for p in entries if p['collider']=='solid') or any(pip((e['x'],e['z']),m['polygon_xz']) for m in mounds):continue
        kept.append(e)
    coverage=[]
    for key in wanted:
        i=items[key];p=next(p for p in plan['items'] if p['id']==key);ee=[e for e in entries if e['blueprint_id']==key]
        status='DEPENDENCY_ROOT_TERRAIN' if key in ['P3','N1'] else 'MISSING_HERO_ASSET' if key=='S5' else 'VISUAL_CLOSED_ROOT_ADMISSION_PENDING' if key in ['T2','T3'] else 'REUSE_CORE_PARTIAL'
        coverage.append({'id':key,'pr':'P1','anchor':i.get('xz',i.get('line',i.get('poly'))[0] if not i.get('xz') else None),'status':status,'entries':[e['id'] for e in ee],'assets':sorted(set(e['asset_id'] for e in ee)),'remaining_components':p['missing_components']+(['Exactadditionalnamedanchors/signposts awaitroot'] if key=='ST8' else []),'declared_standins':sorted(set(e['asset_id'] for e in ee if e['standin']))})
    doc['entries']=kept+fixed+entries;doc['blueprint']['items']+=coverage;doc['blueprint']['collider_requests']+=colliders;doc['blueprint']['extra_mounds']=mounds
    doc['p1']={'schema':'xexoria.blueprint-p1-dressing/1','seed':seed,'p0_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'items':coverage,'rejected_secondary_placements':rejected,'removed_p0_scatter':len(scatter)-len(kept),'new_entries':len(entries),'source_contracts':{'mounds':mounds,'collider_requests':colliders,'held':['P3','N1'],'physical_height':'UNVERIFIED_ROOT closedv1 visual only'},'admission':'UNVERIFIED_ROOT'}
    doc['stats']['total']=len(doc['entries']);doc['stats']['p1_entries']=len(entries)
    return doc


def generate_p2(seed=DEFAULT_SEED):
    """Four-item main-map polish overlay; immutable P0/P1 inputs remain untouched."""
    source=ROOT/'planning/levels/sunmeadow-v3-dressing-p1.json'
    doc=json.loads(source.read_text(encoding='utf-8'))
    bp=json.loads((ROOT/'planning/levels/sunmeadow-blueprint-v1.json').read_text(encoding='utf-8'))
    items={i['id']:i for i in bp['items'] if i.get('pr')=='P2'}
    if set(items)!={'S6','F6','P4','L3'}:raise ValueError('ExactfourP2authority changed')
    entries=[];colliders=[]
    def add(item,asset,x,z,h=None,size=None,yaw=0,r=.3,solid=False,base=0,standin=False,**extra):
        eid=f'bp2_{item}_{sum(e["blueprint_id"]==item for e in entries):03d}'
        e={'id':eid,'blueprint_id':item,'blueprint_wave':'P2','asset_id':asset,'class':'blueprint','variant':1,'x':x,'y':0,'z':z,'yaw':yaw,'scale':1,'collider':'solid' if solid else 'none','footprint_r':r,'cell':f'{math.floor(x/64)},{math.floor(z/64)}','landmark':True,'shadow':True,'rule':'blueprint_p2','mask':'explicit','visual_base_y':base,'standin':standin,**extra}
        if h is not None:e['target_height']=h
        if size is not None:e['target_size_xyz']=size
        entries.append(e)
        if solid:colliders.append({'id':eid,'blueprint_id':item,'shape':'circle','center_xz':[x,z],'radius_m':r,'height_m':h if h else size[1],'support_y':0,'visual_base_y':base,'admission':'UNVERIFIED_ROOT','note':'Statuecore/plinthonly; wingsnotfullfootprint'})
    for x in [-6,6]:
        add('S6','sm_ruin_slab_02',x,-96,size=[1.3,.3,1.3],r=.95,solid=True)
        add('S6','blueprint_cc0_guardian',x,-96,h=3.5,r=.95,solid=True,base=.3,standin=True)
        add('S6','sm_brazier_cresset',x,-94.6,h=.9,r=.3,night_lantern=True)
    for x in [-6,6]:
        for k in range(4):add('F6','sm_croft_fence',x,round(-84-(k+.5)*9/4,3),size=[2.1,1.05,.16],yaw=math.pi/2,r=.3)
    for x,z in [(-42,-84),(-41.2,-83.7),(-41.5,-84.8)]:add('L3','blueprint_tiki_torch',x,z,h=2.2,r=.2,night_lantern=True)
    bodies=[]
    for key,c,rx,rz in [('P4a',[-14,-27],1.2,.65),('P4b',[-15.4,-25.5],.85,.45),('P4c',[-15.5,-28.6],.7,.38)]:
        outline=[[round(c[0]+rx*math.cos(k*math.tau/16),4),round(c[1]+rz*math.sin(k*math.tau/16),4)] for k in range(16)]
        bodies.append({'id':'blueprint_'+key,'blueprint_id':'P4','kind':'rain_puddle','center_xz':c,'outline_xz':outline,'surface_y':.012,'depth_m':.018,'physical_support_y':0,'rain_only':True,'requires_ground_y':0,'collider':'none','host_cut':False,'clock':'readWeatherFrame only','admission':'VISUAL_GROUND_CHECK_REQUIRED'})
    coverage=[]
    gaps={'S6':['GuardianCC0stand-in; dedicatedsentineldesignmissing','AnchoredflameVFX notadded'],'F6':[],'L3':['TorchflameVFX notadded; bodyandboundednightlightonly'],'P4':['GroundY0required; rain-onlyshader/skygradientreflection, no scene-reflectionpass or gameplaywaterhazard']}
    for key in ['S6','F6','P4','L3']:
        i=items[key];ee=[e for e in entries if e['blueprint_id']==key]
        coverage.append({'id':key,'pr':'P2','anchor':i.get('xz',i.get('line',[None])[0]),'status':'WEATHER_CONDITIONAL' if key=='P4' else 'REUSE_CORE_PARTIAL','entries':[e['id'] for e in ee],'assets':sorted(set(e['asset_id'] for e in ee)),'declared_standins':sorted(set(e['asset_id'] for e in ee if e['standin'])),'remaining_components':gaps[key]})
    frozen=doc['entries'];fixed=[e for e in frozen if e.get('blueprint_id')];scatter=[e for e in frozen if not e.get('blueprint_id')]
    kept=[e for e in scatter if not any(math.hypot(e['x']-p['x'],e['z']-p['z'])<e['footprint_r']+p['footprint_r']+.25 for p in entries if p['collider']=='solid')]
    doc['entries']=kept+fixed+entries;doc['blueprint']['items']+=coverage;doc['blueprint']['water_bodies']+=bodies;doc['blueprint']['collider_requests']+=colliders
    doc['p2']={'schema':'xexoria.blueprint-p2-dressing/1','seed':seed,'p1_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'p0_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'items':coverage,'rain_bodies':bodies,'new_entries':len(entries),'removed_scatter':len(scatter)-len(kept),'collider_requests':colliders,'admission':'UNVERIFIED_ROOT','resources':'No paidprovider/newregion; nearest8ownedactive lights remainsmandatory'}
    doc['stats']['total']=len(doc['entries']);doc['stats']['p2_entries']=len(entries)
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=None)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--blueprint-wave", choices=['P0','off','p1','p2'], default='P0')
    a = ap.parse_args(argv)
    a.out=a.out or str(ROOT/f'planning/levels/sunmeadow-v3-dressing-{a.blueprint_wave}.json' if a.blueprint_wave in ['p1','p2'] else OUT)
    make=lambda:generate_p2(a.seed) if a.blueprint_wave=='p2' else generate_p1(a.seed) if a.blueprint_wave=='p1' else generate(a.seed,blueprint=a.blueprint_wave!='off')
    t1 = dumps(make())
    if a.verify:
        t2 = dumps(make())
        h1 = hashlib.sha256(t1.encode()).hexdigest(); h2 = hashlib.sha256(t2.encode()).hexdigest()
        disk = Path(a.out).read_bytes() if Path(a.out).exists() else b""
        h3 = hashlib.sha256(disk).hexdigest()
        print(f"run1 {h1}\nrun2 {h2}\ndisk {h3}")
        ok = h1 == h2 == h3
        print("VERIFY", "PASS byte-identical" if ok else "FAIL")
        return 0 if ok else 1
    Path(a.out).write_text(t1, encoding="utf-8", newline="\n")
    doc = json.loads(t1)
    print("wrote", a.out, "entries", doc["stats"]["total"], "sha256", hashlib.sha256(t1.encode()).hexdigest())
    print("per class", doc["stats"]["per_class"])
    for c, s in doc["stats"]["per_cell"].items():
        print(f"  cell {c}: {sum(s['counts'].values())} items, tris {s['tris_lod0_est']}, solid {s['solid']}")
    print("rejects", doc["stats"]["rejects"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
