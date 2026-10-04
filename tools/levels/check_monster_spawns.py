"""Validate the Sunmeadow v2 monster spawn proposal against the level layout and render an overlay.

Usage:
  python tools/levels/check_monster_spawns.py \
      --layout planning/levels/sunmeadow-v2-layout.json \
      --base planning/sunmeadow-compact-v1.json \
      --monsters planning/levels/sunmeadow-v2-monsters.json \
      --out planning/evidence/sunmeadow-v2-layout [--scratch <dir>]

Reads (never writes) the layout, compact candidate, monsters proposal, content/source/items.json and
content/source/zones.json. Writes <out>/monsters-plan.png (labelled PLAN) and <out>/monsters-checks.json.
The base plan is re-rendered at 10 px/m into --scratch with tools/levels/render_layout_plan.py so the
overlay is crisp; the layout's own plan.png and checks.json are not touched.

Other regions (e.g. Rimecrest):
  python tools/levels/check_monster_spawns.py --layout planning/levels/rimecrest-v1-layout.json \
      --base planning/levels/rimecrest-v1-base.json --monsters planning/levels/rimecrest-v1-monsters.json \
      --out planning/evidence/rimecrest-v1-layout
A minimal "xexoria.level-base.v1" base (props with collider radii, POIs) replaces the compact candidate; with no
compact rows the migration checks against compact v1 and zones.json are skipped. The monsters file may carry a
"checker_profile" (arena/spawn landmark ids, boss zone, quest-object POIs, check labels, plan render text) and
"proposed_items" (new drop ids). Without them every default is the Sunmeadow v2 behaviour, so Sunmeadow's
monsters-plan.png and monsters-checks.json are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_layout_plan as rlp  # noqa: E402  (seg_dist, poly_dist, rect_dist, densify)

PX = 10.0
MARGIN = 60
PANEL_W = 660
# Moved props: any layout landmark noted "existing prop <id>, moved from ..." relocates that compact v1 prop (the layout
# position is used for H5 prop clearance). Same rule as sm2_site.py and render_layout_plan.py.
MOVED_PROP_NOTE = re.compile(r"existing prop (\w+)")

seg_dist, poly_dist, rect_dist, densify = rlp.seg_dist, rlp.poly_dist, rlp.rect_dist, rlp.densify


# ---------------------------------------------------------------- geometry helpers
def point_in_poly(p, poly):
    x, z = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = x1 + (z - z1) * (x2 - x1) / (z2 - z1)
            if xi > x:
                inside = not inside
    return inside


def poly_area(poly):
    a = 0.0
    for i in range(len(poly)):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % len(poly)]
        a += x1 * z2 - x2 * z1
    return abs(a) / 2


def ring_dist(p, poly):
    closed = list(poly) + [poly[0]]
    return poly_dist(p, closed)


def circle_poly(c, r, n=48):
    return [(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def sample_poly(poly, step=0.5):
    """Edge samples plus an interior grid."""
    closed = list(poly) + [poly[0]]
    pts = densify(closed, step)
    xs = [q[0] for q in poly]; zs = [q[1] for q in poly]
    x = math.floor(min(xs))
    while x <= max(xs):
        z = math.floor(min(zs))
        while z <= max(zs):
            if point_in_poly((x, z), poly):
                pts.append((x, z))
            z += step
        x += step
    return pts


def signed_rect_dist(p, r):
    """rect_dist outside the rectangle, minus the penetration depth inside it (so 'clear of' tests can fail)."""
    x0, x1, z0, z1 = r
    if x0 <= p[0] <= x1 and z0 <= p[1] <= z1:
        return -min(p[0] - x0, x1 - p[0], p[1] - z0, z1 - p[1])
    return rect_dist(p, r)


def oriented_rect_dist(p, center, along, length, width):
    ux, uz = along; L = math.hypot(ux, uz); ux, uz = ux / L, uz / L
    dx, dz = p[0] - center[0], p[1] - center[1]
    a = dx * ux + dz * uz
    n = -dx * uz + dz * ux
    return math.hypot(max(abs(a) - length / 2, 0), max(abs(n) - width / 2, 0))


def signed_poly_dist(p, poly):
    """Distance to a polygon's boundary, negative inside."""
    d = ring_dist(p, poly)
    return -d if point_in_poly(p, poly) else d


# Check-name labels. The defaults are the Sunmeadow names; a monsters file can override them in
# checker_profile.labels (Rimecrest: relief, arrival apron, boss arena, spawn dais).
DEFAULT_LABELS = {"relief": "bluff", "apron": "gate apron", "apron_key": "gate_apron",
                  "ring_exclusion": "stone-circle exclusion", "ring": "stone ring", "ring_key": "stone_circle",
                  "boss_spawn": "altar"}
PRECIP_PHASES = (["rain"], ["snow"])  # weather-only rows (Rimecrest calls the shared weather slot snowfall)


def night_aggressive_only(r):
    """Day-passive / night-aggressive types: Sunmeadow's glade_wisp, or a roster entry flagged in its aggro block."""
    return r["id"] == "glade_wisp" or bool(r["aggro"].get("day_passive_night_aggressive"))


# ---------------------------------------------------------------- world model
class World:
    def __init__(self, lay, base, mon, items_ids):
        self.lay, self.mon = lay, mon
        self.rules = mon["rules"]
        # Region profile (opt-in). Sunmeadow has none, so every default below is the Sunmeadow v2 behaviour.
        self.prof = mon.get("checker_profile", {})
        self.labels = dict(DEFAULT_LABELS, **self.prof.get("labels", {}))
        self.items = items_ids
        self.proposed_items = {i["id"] for i in mon.get("proposed_items", [])}
        self.paths = {p["id"]: p for p in lay["paths"]}
        self.streams = [w for w in lay["water"] if w["kind"] == "stream"]
        self.pools = [w for w in lay["water"] if w["kind"] == "pool"]
        # Relief that blocks monsters: every rectangle footprint (Sunmeadow: inner_bluff only), every polygon footprint,
        # and polyline toe lines that the layout marks with path_clearance_m (visible colliders such as cliff toes).
        relief = lay["relief"]
        self.relief_rects = [tuple(r["footprint_xz"]) for r in relief if "footprint_xz" in r]
        self.relief_polys = [[tuple(q) for q in r["polygon_xz"]] for r in relief if "polygon_xz" in r]
        self.relief_lines = [([tuple(q) for q in r["polyline_xz"]], r.get("toe_half_width_m", 0.0))
                             for r in relief if "polyline_xz" in r and "path_clearance_m" in r]
        lm = {l["id"]: l for l in lay["landmarks"]}
        self.camps = [tuple(l["bounds_xz"]) for l in lay["landmarks"] if l.get("kind") == "camp" and "bounds_xz" in l]
        self.camp = self.camps[0] if self.camps else None
        self.bridges = lay.get("bridges", [])
        self.arena_id = self.prof.get("arena_landmark", "windstone_circle")
        self.spawn_id = self.prof.get("boss_spawn_landmark", "windstone_altar")
        self.boss_zone_id = self.prof.get("boss_zone", "windstone_circle")
        circ = lm[self.arena_id]
        self.circle_c, self.circle_r = tuple(circ["center_xz"]), circ["radius_m"]
        self.arena_r = circ["boss_arena_radius_m"]
        altar = lm[self.spawn_id]
        self.altar_c, self.altar_r = tuple(altar["position_xz"]), altar["radius_m"]
        self.clearings = {c["id"]: c for c in lay.get("clearings", [])}
        self.walk = lay["bounds_xz"]["walkable_hint"]
        # Water hazards come from the layout (city_canal_water_0 = zones.json city_traversal canal-water-0).
        water_kinds = self.prof.get("water_hazard_kinds", ["water"])
        self.water_rects = [(h["id"], tuple(h["bounds_xz"])) for h in lay.get("hazards", [])
                            if h.get("kind") in water_kinds and "bounds_xz" in h]
        self.water_polys = [(h["id"], [tuple(q) for q in h["polygon_xz"]]) for h in lay.get("hazards", [])
                            if h.get("kind") in water_kinds and "polygon_xz" in h]
        self.apron = self.rules["R6_gate_apron_xz"]
        if "candidate_zones_source" in base:  # Sunmeadow compact v1 candidate
            cz = base["candidate_zones_source"]["zones"][0]
            self.props = [(p["id"], (p["x"], p["z"]), max(p["collider_size"][0], p["collider_size"][2]) / 2) for p in cz["world_props"]]
            pois = {p["id"]: (p["x"], p["z"]) for p in cz["pois"]}
            compact_rows = base["dependencies"]["monsters"]
        else:  # minimal level base (xexoria.level-base.v1): colliding props with their collider radius, and POIs
            self.props = [(p["id"], tuple(p["position_xz"]), float(p.get("collider_radius_m", 0.0)))
                          for p in base["props"] if p.get("collides", True)]
            pois = {p["id"]: (p["x"], p["z"]) for p in base.get("pois", [])}
            compact_rows = []
        # Compact v1 props that the layout relocates: the layout landmark position wins (prop audit 2026-10-02).
        self.moved_props = {}
        for l in lm.values():
            mm = MOVED_PROP_NOTE.search(l.get("note", ""))
            if mm and isinstance(l.get("position_xz"), list):
                self.moved_props[mm.group(1)] = tuple(l["position_xz"])
        self.props = [(pid, self.moved_props.get(pid, c), r) for pid, c, r in self.props]
        if "old_sunmeadow_oak" in lm:
            # Layout landmarks with a physical footprint: positions from the layout (the lookout uses the compact v1 POI,
            # as the layout says); radii are assumptions, recorded in the receipt.
            self.props += [("old_sunmeadow_oak_trunk", tuple(lm["old_sunmeadow_oak"]["position_xz"]), 1.8),
                           ("ancient_pine_trunk", tuple(lm["ancient_pine"]["position_xz"]), 1.2),
                           ("gate_signpost", tuple(lm["gate_signpost"]["position_xz"]), 0.3),
                           ("lookout_tower", pois["lookout"], 2.5)]
        self.pois = pois
        self.windmarks = {k: pois[k] for k in self.prof.get("quest_object_pois", ("windmark_1", "windmark_2", "windmark_3"))}
        self.safe = {k: (tuple(v[0]), v[1]) for k, v in self.rules["R6_safe_points"].items()}
        self.compact = {m["source_index"]: m for m in compact_rows}
        self.compact_rows = len(self.compact)  # Sunmeadow: rows 0-12 migrate from compact v1
        self.roster = {r["id"]: r for r in mon["roster"]}
        self.zones = {z["id"]: z for z in mon["zones"]}

    # distances
    def water_edge(self, p):
        d_stream = min((poly_dist(p, s["points"]) - max(s["width_m"]) / 2 for s in self.streams), default=math.inf)
        d_pool = min((math.dist(p, w["center_xz"]) - w["radius_m"] for w in self.pools), default=math.inf)
        d_haz = min((signed_rect_dist(p, r) for _, r in self.water_rects), default=math.inf)
        d_hp = min((signed_poly_dist(p, poly) for _, poly in self.water_polys), default=math.inf)
        return min(d_stream, d_pool, d_haz, d_hp), d_stream

    def bridge_dist(self, p):
        return min((oriented_rect_dist(p, b["center_xz"], b["along_xz"], b["length_m"], b["deck_width_m"] + 0.6)
                    for b in self.bridges), default=math.inf)

    def relief_dist(self, p):
        d = min((rect_dist(p, r) for r in self.relief_rects), default=math.inf)
        d = min(d, min((signed_poly_dist(p, poly) for poly in self.relief_polys), default=math.inf))
        return min(d, min((poly_dist(p, line) - hw for line, hw in self.relief_lines), default=math.inf))

    def camp_dist(self, p):
        return min((rect_dist(p, c) for c in self.camps), default=math.inf)

    def path_metrics(self, p):
        out = {}
        for pid, pth in self.paths.items():
            d = poly_dist(p, pth["points"])
            out[pid] = (d, d - pth["width_m"] / 2)
        return out

    def nearest_prop(self, p):
        return min(((math.dist(p, c) - r, pid) for pid, c, r in self.props))

    def zone_spawn_shape(self, zone):
        if zone.get("spawn_polygon_xz") == "circle":
            c = zone["spawn_circle"]
            return circle_poly(c["center_xz"], c["radius_m"])
        return [tuple(q) for q in zone["spawn_polygon_xz"]]

    def zone_leash_shape(self, zone):
        if "leash_circle" in zone:
            c = zone["leash_circle"]
            return circle_poly(c["center_xz"], c["radius_m"])
        return [tuple(q) for q in zone["leash_polygon_xz"]]


def mode_for(world, enemy_id, phase):
    """Return (kind, aggro_m) where kind is 'passive', 'aggressive' or 'boss'."""
    r = world.roster[enemy_id]
    ag = r["aggro"]
    if r["tier"] == "boss":
        return "boss", 0.0
    if night_aggressive_only(r):
        return ("aggressive", ag["night_radius_m"]) if phase == "night" else ("passive", 0.0)
    if ag["mode"].startswith("passive"):
        return "passive", 0.0
    radius = max(ag.get("radius_m", 0.0), ag.get("night_radius_m", 0.0))
    return "aggressive", radius


# ---------------------------------------------------------------- checks
class Checker:
    def __init__(self, world):
        self.w = world
        self.results = []

    def add(self, row, what, value, limit, ok, hard=True):
        self.results.append({"row": row, "check": what, "value": None if value is None else round(value, 2),
                             "limit": limit, "pass": bool(ok), "hard": hard})

    # one point (home, night home, patrol vertex or sample)
    def point(self, row, tag, p, enemy, zone, phase, sample=False):
        w, R = self.w, self.w.rules
        r = w.roster[enemy]
        body = r["body_radius_m"]
        kind, aggro = mode_for(w, enemy, phase)
        amph = r["aggro"].get("amphibious", False)
        # H1 bridge
        if w.bridges:
            d = w.bridge_dist(p)
            self.add(row, f"{tag} H1 bridge clearance", d, f">= {R['R1_bridge_clear_m']}", d >= R["R1_bridge_clear_m"])
        # H2 paths
        s0 = r["tuning"].get("step0", {}).get("aggro")
        for pid, (dc, de) in w.path_metrics(p).items():
            hw = w.paths[pid]["width_m"] / 2
            if dc < 12 or not sample:
                self.add(row, f"{tag} H2 {pid} centre", dc, f">= {R['R2_path_centre_min_m']}", dc >= R["R2_path_centre_min_m"])
                self.add(row, f"{tag} H2b {pid} edge margin", de, f">= {R['R2b_path_edge_margin_m']}", de >= R["R2b_path_edge_margin_m"])
            # A path with "road_safe": false (boar_trail) is an intentional danger approach: H7/H7s skip it, H2 still applies.
            if not w.paths[pid].get("road_safe", True):
                continue
            # H7 road safety (edge-based): the aggro disc never overlaps the path surface.
            if kind == "aggressive" and (dc < hw + aggro + 6 or not sample):
                need = hw + aggro + R["R7_road_safe_margin_m"]
                self.add(row, f"{tag} H7 {pid} road-safe edge (aggro {aggro})", dc, f">= {round(need, 2)}", dc >= need)
            # H7s: same test for pseudo-passive types with their step-0 interim radius.
            if kind == "passive" and isinstance(s0, (int, float)) and (dc < hw + s0 + 6 or not sample):
                need = hw + s0 + R["R7_road_safe_margin_m"]
                self.add(row, f"{tag} H7s {pid} step-0 interim road-safe (aggro {s0})", dc, f">= {round(need, 2)}", dc >= need)
        # H3 walkable bounds
        x0, x1, z0, z1 = w.walk
        inb = x0 <= p[0] <= x1 and z0 <= p[1] <= z1
        self.add(row, f"{tag} H3 inside walkable_hint", None, str(w.walk), inb)
        # H4 water
        dw, dstream = w.water_edge(p)
        if amph:
            lo, hi = R["R4_amphibious_water_edge_m"]
            if sample:
                self.add(row, f"{tag} H4 amphibious water edge", dw, f">= {lo}", dw >= lo)
            else:
                self.add(row, f"{tag} H4 amphibious water edge", dw, f"{lo}..{hi}", lo <= dw <= hi)
        else:
            self.add(row, f"{tag} H4 water edge", dw, f">= {R['R4_land_water_edge_min_m']}", dw >= R["R4_land_water_edge_min_m"])
        # H5 hazards
        L = w.labels
        db = w.relief_dist(p)
        self.add(row, f"{tag} H5 {L['relief']}", db, f">= {R['R5_bluff_margin_m']}", db >= R["R5_bluff_margin_m"])
        if w.camps:
            dc = w.camp_dist(p)
            self.add(row, f"{tag} H5 camp", dc, f">= {R['R5_camp_margin_m']}", dc >= R["R5_camp_margin_m"])
        gap, pid = w.nearest_prop(p)
        need = body + R["R5_prop_gap_m"]
        self.add(row, f"{tag} H5 prop clearance ({pid})", gap, f">= {round(need, 2)}", gap >= need)
        dcirc = math.dist(p, w.circle_c)
        if kind == "boss":
            # The boss stands on the layout altar and its body stays inside the ring of stones.
            dalt = math.dist(p, w.altar_c)
            self.add(row, f"{tag} H5 boss on {L['boss_spawn']}", dalt, f"<= {w.altar_r}", dalt <= w.altar_r)
            need = w.circle_r - body - R["R5_boss_ring_margin_m"]
            self.add(row, f"{tag} H5 boss body inside {L['ring']}", dcirc, f"<= {round(need, 2)}", dcirc <= need)
        else:
            self.add(row, f"{tag} H5 {L['ring_exclusion']}", dcirc, f">= {R['R5_circle_regular_min_m']}", dcirc >= R["R5_circle_regular_min_m"])
        ax0, ax1, az0, az1 = w.apron
        in_apron = ax0 <= p[0] <= ax1 and az0 <= p[1] <= az1
        self.add(row, f"{tag} H6 outside {L['apron']}", None, str(w.apron), not in_apron)
        # H6 windmarks and safe points
        for wid, wp in w.windmarks.items():
            dwm = math.dist(p, wp)
            need = R["R6_windmark_passive_min_m"] if kind != "aggressive" else aggro + R["R6_windmark_aggressive_extra_m"]
            if dwm < need + 10 or not sample:
                self.add(row, f"{tag} H6 {wid}", dwm, f">= {need}", dwm >= need)
        for sid, (sp, sr) in w.safe.items():
            ds = math.dist(p, sp)
            need = sr + (aggro if kind == "aggressive" else 0.0)
            if ds < need + 10 or not sample:
                self.add(row, f"{tag} H6 safe {sid}", ds, f">= {need}", ds >= need)
        if kind == "aggressive":
            if w.camps:
                dcamp = w.camp_dist(p)
                self.add(row, f"{tag} H6 aggro clear of camp", dcamp, f">= {aggro + 1}", dcamp >= aggro + 1)
            dap = rect_dist(p, w.apron)
            self.add(row, f"{tag} H6 aggro clear of {L['apron']}", dap, f">= {aggro + 1}", dap >= aggro + 1)
        # zone containment
        if zone is not None:
            shape = w.zone_spawn_shape(zone)
            leash = w.zone_leash_shape(zone)
            if not sample:
                self.add(row, f"{tag} H3 inside spawn zone {zone['id']}", None, "inside", point_in_poly(p, shape))
            self.add(row, f"{tag} H9 inside leash zone {zone['id']}", None, "inside", point_in_poly(p, leash))
            # A zone tied to a round layout clearing (oak_wallow) keeps the whole body inside that clearing.
            cl = w.clearings.get(zone.get("clearing"))
            if cl and "radius_m" in cl:
                dcl = math.dist(p, cl["center_xz"]) + body
                self.add(row, f"{tag} H3 body inside layout clearing {cl['id']}", dcl, f"<= {cl['radius_m']}", dcl <= cl["radius_m"])

    def leash_polygon(self, zone):
        """H9: leash polygon is hazard-free and contains the spawn polygon."""
        w, R = self.w, self.w.rules
        zid = zone["id"]
        leash = w.zone_leash_shape(zone)
        spawn = w.zone_spawn_shape(zone)
        m = R["R9_leash_hazard_margin_m"]
        rows = [w.mon["spawn_rows"][i] for i in zone["rows"]]
        amph = any(w.roster[r["enemy"]]["aggro"].get("amphibious", False) for r in rows)
        boss = zone["id"] == w.boss_zone_id
        first_clearing = zone.get("clearing") in w.prof.get("sanctuary_clearings", ["windmark_hunt"])
        L = w.labels
        worst = {}
        for q in sample_poly(leash, 0.5):
            dw, _ = w.water_edge(q)
            vals = {
                "water": (dw, (0.0 if amph else m)),
                L["relief"]: (w.relief_dist(q), m),
                L["apron_key"]: (signed_rect_dist(q, w.apron), 0.0),
            }
            if w.bridges:
                vals["bridge"] = (w.bridge_dist(q), m)
            if w.camps:
                vals["camp"] = (w.camp_dist(q), m)
            if not boss:
                vals[L["ring_key"]] = (math.dist(q, w.circle_c) - w.circle_r, R.get("R9_ring_clear_m", 2.0))
            for sid, (sp, sr) in w.safe.items():
                vals[f"safe_{sid}"] = (math.dist(q, sp) - sr, 0.0)
            if first_clearing:
                for pid in R.get("R9_first_clearing_sanctuary_paths", ["gate_road", "camp_spur"]):
                    pth = w.paths[pid]
                    vals[f"road_sanctuary_{pid}"] = (poly_dist(q, pth["points"]) - pth["width_m"] / 2, 1.0)
            x0, x1, z0, z1 = w.walk
            vals["walkable_hint"] = (min(q[0] - x0, x1 - q[0], q[1] - z0, z1 - q[1]), 0.0)
            for k, (v, lim) in vals.items():
                if k not in worst or v - lim < worst[k][0] - worst[k][1]:
                    worst[k] = (v, lim)
        for k, (v, lim) in sorted(worst.items()):
            self.add(f"zone:{zid}", f"H9 leash polygon clear of {k}", v, f">= {lim}", v >= lim)
        inside = all(point_in_poly(q, leash) or ring_dist(q, leash) < 0.05 for q in densify(list(spawn) + [spawn[0]], 0.5))
        self.add(f"zone:{zid}", "H9 spawn polygon inside leash polygon", None, "inside", inside)
        if boss:
            # The arena and the altar are layout facts: the zone must use them, not its own copies.
            lc, sc = zone["leash_circle"], zone["spawn_circle"]
            da = math.dist(lc["center_xz"], w.circle_c)
            self.add(f"zone:{zid}", f"H5 arena = layout {w.arena_id} centre and boss_arena_radius_m", da,
                     f"centre {list(w.circle_c)}, r {w.arena_r}", da < 0.01 and abs(lc["radius_m"] - w.arena_r) < 0.01)
            ds = math.dist(sc["center_xz"], w.altar_c)
            self.add(f"zone:{zid}", f"H5 boss spawn circle centred on layout {w.spawn_id}", ds,
                     f"centre {list(w.altar_c)}, r <= {w.altar_r}", ds < 0.01 and sc["radius_m"] <= w.altar_r)


def chase_reach(world, row, enemy):
    """Step 0 (today's circle leash): reach = leash + chase_reach_extra. Report hazards and zone overflow."""
    r = world.roster[enemy]
    t = r["tuning"].get("step0", {})
    if not t.get("leash"):
        return None
    reach = t["leash"] + world.rules["chase_reach_extra_m"]
    p = tuple(row["home_xz"])
    amph = r["aggro"].get("amphibious", False)
    dw, _ = world.water_edge(p)
    haz = {world.labels["relief"]: world.relief_dist(p)}
    if not amph:
        haz["water"] = dw
    zone = world.zones[row["zone"]]
    leash = world.zone_leash_shape(zone)
    # how far the reach disc spills outside the zone leash polygon
    spill = 0.0
    for q in circle_poly(p, reach, 72):
        if not point_in_poly(q, leash):
            spill = max(spill, ring_dist(q, leash))
    worst = min(haz.items(), key=lambda kv: kv[1])
    return {"row": row["row"], "enemy": enemy, "step0_leash": t["leash"], "reach_m": reach,
            "nearest_hazard": worst[0], "hazard_clearance_m": round(worst[1], 2),
            "hazard_ok": worst[1] >= reach, "zone_spill_m": round(spill, 2)}


def roster_validation(ck, world):
    seen_kinds = set()
    for r in world.mon["roster"]:
        rid = r["id"]
        k = r["kind"]
        ck.add(f"roster:{rid}", "H11 kind unique and nonzero", k, "unique > 0", k > 0 and k not in seen_kinds)
        seen_kinds.add(k)
        hp = r["stats"]["hp"]["proposed"]
        ck.add(f"roster:{rid}", "H11 hp 1..65535 (u16)", hp, "1..65535", 0 < hp <= 65535)
        sp = r["stats"]["speed_m_s"]
        ck.add(f"roster:{rid}", "H11 speed 0.1..30", sp, "0.1..30", 0.1 <= sp <= 30)
        ck.add(f"roster:{rid}", "H11 exp <= 1e6", r["stats"]["exp"], "<= 1000000", r["stats"]["exp"] <= 1_000_000)
        for step in ("step0", "step1", "step2"):
            t = r["tuning"].get(step, {})
            if isinstance(t.get("aggro"), (int, float)) and isinstance(t.get("leash"), (int, float)):
                ok = 1.0 <= t["aggro"] <= 60.0 and t["aggro"] <= t["leash"] <= 200.0
                ck.add(f"roster:{rid}", f"H11 {step} aggro 1..60 and leash >= aggro", t["leash"], f">= {t['aggro']}", ok)
            if isinstance(t.get("respawn_s"), int):
                ck.add(f"roster:{rid}", f"H11 {step} respawn 1..3600", t["respawn_s"], "1..3600", 1 <= t["respawn_s"] <= 3600)
            for wv in t.get("respawn_window_s", []) or []:
                ck.add(f"roster:{rid}", f"H11 {step} respawn window <= 3600", wv, "1..3600", 1 <= wv <= 3600)
        for i, s in enumerate(r["skills"]):
            times = [s["windup_ms"], s["active_ms"], s["fade_ms"], s["recovery_ms"], s["cooldown_ms"]]
            ck.add(f"roster:{rid}", f"H11 {s['id']} timings multiple of 50 ms", None, "x % 50 == 0", all(t % 50 == 0 for t in times))
            ok = s["windup_ms"] >= 100 and s["active_ms"] > 0 and s["recovery_ms"] > 0 and s["cooldown_ms"] >= s["windup_ms"] + s["active_ms"]
            ck.add(f"roster:{rid}", f"H11 {s['id']} windup>=100, cooldown>=windup+active", s["cooldown_ms"], f">= {s['windup_ms'] + s['active_ms']}", ok)
            if i == 0:
                rad = s.get("radius_m", 0)
                ck.add(f"roster:{rid}", f"H11 {s['id']} splash radius 0.5..10", rad, "0.5..10", 0.5 <= rad <= 10 and s["damage"] > 0)
        for d in r["drops"]:
            if d["item"] in world.items or d["item"] not in world.proposed_items:
                ok = d["item"] in world.items and 1 <= d["chance_pct"] <= 100 and 1 <= d["min"] <= d["max"] <= 99
                ck.add(f"roster:{rid}", f"H11 drop {d['item']} valid existing id", d["chance_pct"], "item exists, 1..100 %, 1<=min<=max<=99", ok)
            else:  # a new item id defined in the monsters file's proposed_items (content work before deploy)
                ok = 1 <= d["chance_pct"] <= 100 and 1 <= d["min"] <= d["max"] <= 99
                ck.add(f"roster:{rid}", f"H11 drop {d['item']} valid proposed id", d["chance_pct"],
                       "item in proposed_items, 1..100 %, 1<=min<=max<=99", ok)
        for c in r["clips"]:
            ok = c["ms"] > 0 and c["ms"] % 50 == 0
            ck.add(f"roster:{rid}", f"H11 clip {c['name']} length", c["ms"], "> 0, x % 50 == 0", ok)
    for it in world.mon.get("proposed_items", []):
        ok = (it["id"] not in world.items and it.get("type") in ("material", "consumable", "box", "weapon", "armor", "quest")
              and 1 <= it.get("stack", 0) <= 99 and bool(it.get("name_key")) and bool(it.get("desc_key")))
        ck.add(f"item:{it['id']}", "H11 proposed item is a new id with type, stack 1..99 and name/desc keys", it.get("stack"),
               "new id, known type, 1..99", ok)


def migration_validation(ck, world, live_spawns):
    rows = world.mon["spawn_rows"]
    ck.add("migration", "H12 rows are contiguous 0..n-1", len(rows), "contiguous", [r["row"] for r in rows] == list(range(len(rows))))
    for i in range(world.compact_rows):
        r = rows[i]
        cm = world.compact[i]
        ck.add(f"row {i}", "H12 enemy id unchanged vs compact v1", None, cm["enemy"], r["enemy"] == cm["enemy"])
        ck.add(f"row {i}", "H12 compact_v1_xz matches source", None, str(cm["after_xz"]), list(r["compact_v1_xz"]) == list(cm["after_xz"]))
        lv = live_spawns[i]
        ck.add(f"row {i}", "H12 live enemy and xz match zones.json", None, f"{lv['enemy']} {lv['x']},{lv['z']}",
               r["enemy"] == lv["enemy"] and list(r["live_xz"]) == [lv["x"], lv["z"]])
    steps = [r["deploy_step"] for r in rows]
    ck.add("migration", "H12 deploy steps never decrease with row index", None, "monotonic", steps == sorted(steps))
    for i in range(world.compact_rows, len(rows)):
        ck.add(f"row {i}", "H12 appended rows are new", None, "status new", rows[i]["status"] == "new")
    total = len(rows)
    ck.add("migration", "H10 total rows <= wire cap", total, f"<= {world.rules['R10_wire_cap']}", total <= world.rules["R10_wire_cap"])
    ck.add("migration", "H10 total rows <= design target", total, f"<= {world.rules['R10_row_target_max']}", total <= world.rules["R10_row_target_max"])
    for z in world.mon["zones"]:
        for ri in z["rows"]:
            ck.add(f"zone:{z['id']}", f"H3 zone lists row {ri} that names it", None, z["id"], rows[ri]["zone"] == z["id"])
    named = sorted(i for z in world.mon["zones"] for i in z["rows"])
    ck.add("migration", "H3 every row belongs to exactly one zone", None, "partition", named == list(range(total)))


def spacing(ck, world):
    rows = world.mon["spawn_rows"]
    day = [(r["row"], tuple(r["home_xz"])) for r in rows if "night" not in r["phases"] or len(r["phases"]) > 1]
    night = []
    for r in rows:
        if "night" in r["phases"]:
            night.append((r["row"], tuple(r.get("night_home_xz", r["home_xz"]))))
    for label, pts in (("day+rain", day), ("night", night)):
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d = math.dist(pts[i][1], pts[j][1])
                if d < 4.0:
                    ck.add(f"rows {pts[i][0]}/{pts[j][0]}", f"H13 home spacing ({label})", d, ">= 2.5", d >= 2.5)


# ---------------------------------------------------------------- metrics
def zone_metrics(world):
    out = []
    rows = world.mon["spawn_rows"]
    for z in world.mon["zones"]:
        leash = world.zone_leash_shape(z)
        spawn = world.zone_spawn_shape(z)
        rr = [rows[i] for i in z["rows"]]
        day = [r for r in rr if any(ph in r["phases"] for ph in ("day", "twilight"))]
        rain = [r for r in rr if r["phases"] in PRECIP_PHASES]
        night = [r for r in rr if "night" in r["phases"] and "night_home_xz" not in r]
        night += [r for r in rows if r.get("night_zone") == z["id"]]
        cap = 0.0
        for r in day:
            ro = world.roster[r["enemy"]]
            resp = ro["tuning"].get("step0", {}).get("respawn_s") or ro["tuning"].get("step2", {}).get("respawn_s") or 60
            lvl = ro["level"]
            atk = 45 + 3 * (lvl - 1)
            dfn = ro["stats"]["def"]["proposed"] or 0
            ttk = math.ceil(ro["stats"]["hp"]["proposed"] / max(1, atk - dfn)) * 0.4
            cap += 60.0 / (resp + ttk + 2.0)
        out.append({"zone": z["id"], "level_band": z["level_band"], "spawn_area_m2": round(poly_area(spawn)),
                    "leash_area_m2": round(poly_area(leash)), "rows_day": len(day), "rows_night": len(night),
                    "rows_rain_extra": len(rain),
                    "density_per_100m2_day": round(100 * len(day) / max(1, poly_area(leash)), 2),
                    "kills_per_min_capacity_day": round(cap, 1),
                    "enemies": sorted({world.mon["spawn_rows"][i]["enemy"] for i in z["rows"]})})
    return out


def clock_phases():
    def daylight(h):
        alt = math.sin((h - 6) / 24 * math.pi * 2)
        t = max(0.0, min(1.0, (alt + 0.14) / 0.46))
        return t * t * (3 - 2 * t)
    hours = [i / 100 for i in range(2400)]
    day = sum(1 for h in hours if daylight(h) >= 0.5) / 100
    night = sum(1 for h in hours if daylight(h) < 0.15) / 100
    boss = sum(1 for h in hours if daylight(h) < 0.35) / 100
    k = 45.0 / 24.0
    return {"day_game_h": day, "night_game_h": night, "twilight_game_h": round(24 - day - night, 2),
            "day_real_min": round(day * k, 1), "night_real_min": round(night * k, 1),
            "twilight_real_min_total": round((24 - day - night) * k, 1), "boss_gate_real_min_per_cycle": round(boss * k, 1)}


# ---------------------------------------------------------------- rendering
BAND = {1: (70, 170, 80), 2: (70, 170, 80), 3: (225, 170, 40), 4: (225, 150, 40), 5: (225, 130, 40),
        6: (220, 90, 40), 7: (220, 90, 40), 9: (200, 40, 60), 10: (200, 40, 60), 11: (200, 40, 60)}
ICON = {"puddlekin": ("P", (127, 196, 216)), "mossling": ("M", (111, 156, 75)), "thistle_boar": ("B", (142, 91, 176)),
        "glade_wisp": ("W", (246, 201, 95)), "brookclaw": ("C", (63, 99, 152)), "turfback_matriarch": ("E", (232, 102, 42)),
        "galehorn": ("G", (217, 58, 58))}
DARK_ICON = ("brookclaw", "galehorn", "turfback_matriarch", "thistle_boar")
SHORT_MODE = {"puddlekin": "passive", "mossling": "passive + assist", "thistle_boar": "aggressive + assist",
              "glade_wisp": "day passive / night aggressive", "brookclaw": "ambush + looter, amphibious",
              "turfback_matriarch": "aggressive pack leader", "galehorn": "passive until provoked"}
# Top-left corner of each zone label (Babylon XZ). Chosen so labels sit on quiet ground.
LABEL_AT = {"hunt_meadow_west": (-15.5, -9.4), "hunt_meadow_east": (10.4, 9.4), "falls_meadow": (-44.0, -21.2),
            "bridgewater_banks": (-44.0, -43.2), "glade_southwest": (-18.0, -90.6), "glade_pine": (6.0, -96.6),
            "glade_east": (8.0, -60.2), "oak_wallow": (24.5, -88.6),
            "oak_roots": (31.0, -51.2)}
ARENA_LABEL_OFFSET = (-1.0, 5.8)  # windstone_circle label: (dx, dz above the arena's north rim) from the layout circle centre


def plan_cfg(world):
    """Render text and colours for regions other than Sunmeadow (checker_profile.plan); empty for Sunmeadow."""
    return world.prof.get("plan", {})


def band_col(world, lvl):
    bc = plan_cfg(world).get("band_colors", {})
    return tuple(bc[str(lvl)]) if str(lvl) in bc else BAND.get(lvl, (150, 150, 150))


def icon_for(world, enemy):
    if enemy in ICON:
        return ICON[enemy]
    pi = world.roster[enemy].get("plan_icon", {})
    return pi.get("letter", enemy[:1].upper()), tuple(pi.get("rgb", (150, 150, 150)))


def dark_icon(world, enemy):
    return enemy in DARK_ICON if enemy in ICON else bool(world.roster[enemy].get("plan_icon", {}).get("dark", False))


def short_mode(world, enemy):
    return SHORT_MODE[enemy] if enemy in SHORT_MODE else world.roster[enemy].get("plan_icon", {}).get("mode", world.roster[enemy]["aggro"]["mode"])


def render(world, base_png, out_png, summary, zones_metrics, steps):
    lay = world.lay
    x0, x1, z0, z1 = lay["bounds_xz"]["stage"]
    base = Image.open(base_png).convert("RGBA")
    W, H = base.size
    img = Image.new("RGBA", (W + PANEL_W, H), (246, 243, 232, 255))
    img.paste(base, (0, 0))
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov, "RGBA")
    try:
        f = ImageFont.truetype("arial.ttf", 14); fb = ImageFont.truetype("arialbd.ttf", 15)
        fbig = ImageFont.truetype("arialbd.ttf", 22); fs = ImageFont.truetype("arial.ttf", 12)
        ficon = ImageFont.truetype("arialbd.ttf", 13); fz = ImageFont.truetype("arialbd.ttf", 14)
    except OSError:
        f = fb = fbig = fs = ficon = fz = ImageFont.load_default()

    def P(x, z):
        return (MARGIN + (x - x0) * PX, MARGIN + 40 + (z1 - z) * PX)

    def boxed(xy, text, font, fg, bg=(255, 255, 255, 215), pad=3):
        l, t, r, b = d.textbbox(xy, text, font=font)
        d.rectangle([l - pad, t - pad, r + pad, b + pad], fill=bg)
        d.text(xy, text, fill=fg, font=font)

    def dashed_poly(poly, col, width=2):
        pts = densify(list(poly) + [poly[0]], 0.4)
        for k in range(0, len(pts) - 1):
            if (k // 3) % 2 == 0:
                d.line([P(*pts[k]), P(*pts[k + 1])], fill=col, width=width)

    def dashed_circle(c, r, col, width=1):
        n = max(24, int(r * 6))
        for k in range(n):
            if k % 2 == 0:
                a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
                d.line([P(c[0] + r * math.cos(a0), c[1] + r * math.sin(a0)),
                        P(c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))], fill=col, width=width)

    def crescent(cx, cy, r, col):
        size = int(2 * r + 4)
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse([2, 2, 2 + 2 * r, 2 + 2 * r], fill=255)
        md.ellipse([2 + 0.7 * r, 2 - 0.25 * r, 2 + 2.7 * r, 2 + 1.75 * r], fill=0)
        ov.paste(Image.new("RGBA", (size, size), col), (int(cx - r - 2), int(cy - r - 2)), mask)

    # safe areas
    ax0, ax1, az0, az1 = world.apron
    d.rectangle([P(ax0, az1), P(ax1, az0)], fill=(60, 170, 90, 45), outline=(40, 130, 60, 200), width=2)
    for sid, (sp, sr) in world.safe.items():
        d.ellipse([P(sp[0] - sr, sp[1] + sr), P(sp[0] + sr, sp[1] - sr)], fill=(60, 170, 90, 40), outline=(40, 130, 60, 200), width=2)
    for cx0, cx1, cz0, cz1 in world.camps:
        d.rectangle([P(cx0, cz1), P(cx1, cz0)], fill=(60, 170, 90, 40))
    for wid, wp in world.windmarks.items():
        d.polygon([P(wp[0], wp[1] + 0.9), P(wp[0] + 0.8, wp[1]), P(wp[0], wp[1] - 0.9), P(wp[0] - 0.8, wp[1])],
                  fill=(114, 213, 222, 255), outline=(20, 90, 110))
        d.text(P(wp[0] + 1.0, wp[1] + 0.9), wid.replace("windmark_", "wm"), fill=(20, 90, 110), font=fs)

    # zones
    for z in world.mon["zones"]:
        col = band_col(world, z["level_band"][0])
        spawn = world.zone_spawn_shape(z)
        leash = world.zone_leash_shape(z)
        d.polygon([P(*q) for q in spawn], fill=col + (60,), outline=col + (210,))
        dashed_poly(leash, col + (235,), width=2)

    rows = world.mon["spawn_rows"]
    # aggro discs (step-1 values) for aggressive monsters; wisps only where they stay at night
    for r in rows:
        ph = "night" if (night_aggressive_only(world.roster[r["enemy"]]) and "night_home_xz" not in r) else "day"
        kind, aggro = mode_for(world, r["enemy"], ph)
        if kind == "aggressive":
            dashed_circle(tuple(r["home_xz"]), aggro, (200, 60, 40, 150), 1)
        if "night_home_xz" in r:
            _, na = mode_for(world, r["enemy"], "night")
            dashed_circle(tuple(r["night_home_xz"]), na, (40, 60, 160, 150), 1)
    # migration from compact v1 (light)
    for r in rows[:world.compact_rows]:
        a, b = tuple(r["compact_v1_xz"]), tuple(r["home_xz"])
        if a != b:
            d.line([P(*a), P(*b)], fill=(90, 90, 90, 80), width=1)
            pa = P(*a)
            d.line([(pa[0] - 4, pa[1] - 4), (pa[0] + 4, pa[1] + 4)], fill=(70, 70, 70, 220), width=2)
            d.line([(pa[0] - 4, pa[1] + 4), (pa[0] + 4, pa[1] - 4)], fill=(70, 70, 70, 220), width=2)
            d.text((pa[0] + 5, pa[1] + 2), str(r["row"]), fill=(80, 80, 80, 230), font=fs)
    # patrols
    for r in rows:
        pt = r.get("patrol")
        if not pt:
            continue
        pts = [tuple(q) for q in pt["points"]]
        seq = pts + ([pts[0]] if pt["type"] == "loop" else [])
        for k in range(len(seq) - 1):
            a, b = P(*seq[k]), P(*seq[k + 1])
            d.line([a, b], fill=(255, 255, 255, 230), width=4)
            d.line([a, b], fill=(40, 40, 40, 230), width=2)
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            for s in (1, -1):
                d.line([(mx, my), (mx - 9 * math.cos(ang + s * 0.5), my - 9 * math.sin(ang + s * 0.5))], fill=(40, 40, 40, 235), width=2)
    # boss arena
    bz = world.zones[world.boss_zone_id]
    dashed_circle(tuple(bz["leash_circle"]["center_xz"]), bz["leash_circle"]["radius_m"], (200, 30, 50, 235), 3)
    (acx, acz), ar = world.altar_c, world.altar_r  # layout windstone_altar platform
    d.ellipse([P(acx - ar, acz + ar), P(acx + ar, acz - ar)], fill=(200, 30, 50, 60), outline=(200, 30, 50, 255), width=2)
    # homes
    for r in rows:
        letter, col = icon_for(world, r["enemy"])
        p = P(*r["home_xz"])
        tier = world.roster[r["enemy"]]["tier"]
        rad = 15 if tier == "boss" else 13 if tier == "elite" else 10
        if r["phases"] in PRECIP_PHASES:
            d.polygon([(p[0], p[1] - rad - 4), (p[0] + rad, p[1]), (p[0], p[1] + rad + 4), (p[0] - rad, p[1])], fill=col + (255,), outline=(20, 60, 120), width=2)
            fg = (20, 20, 20)
        elif r["phases"] == ["night"]:
            d.ellipse([p[0] - rad, p[1] - rad, p[0] + rad, p[1] + rad], fill=(40, 60, 140, 255), outline=col + (255,), width=3)
            fg = (255, 255, 255)
        else:
            d.ellipse([p[0] - rad, p[1] - rad, p[0] + rad, p[1] + rad], fill=col + (255,), outline=(20, 20, 20, 255), width=2)
            fg = (255, 255, 255) if dark_icon(world, r["enemy"]) else (20, 20, 20)
        tw = d.textlength(letter, font=ficon)
        d.text((p[0] - tw / 2, p[1] - 8), letter, fill=fg, font=ficon)
        d.text((p[0] + rad + 2, p[1] - rad - 2), str(r["row"]), fill=(20, 20, 20), font=fs)
        if "night_home_xz" in r:  # day home of a migrating wisp
            crescent(p[0] - rad - 9, p[1] + 7, 6, (40, 60, 140, 255))
            nb = P(*r["night_home_xz"])
            d.ellipse([nb[0] - 10, nb[1] - 10, nb[0] + 10, nb[1] + 10], fill=(40, 60, 140, 240), outline=(255, 255, 255, 255), width=2)
            crescent(nb[0], nb[1], 6, (246, 201, 95, 255))
            boxed((nb[0] + 13, nb[1] - 22), f"row {r['row']} night", fs, (30, 50, 120))
    # zone labels on top
    pc = plan_cfg(world)
    label_at = dict(LABEL_AT, **{k: tuple(v) for k, v in pc.get("label_at", {}).items()})
    for z in world.mon["zones"]:
        col = band_col(world, z["level_band"][0])
        lx, lz = label_at.get(z["id"], (min(q[0] for q in world.zone_spawn_shape(z)), min(q[1] for q in world.zone_spawn_shape(z))))
        txt = f"{z['id']}  L{z['level_band'][0]}-{z['level_band'][1]}"
        if z["id"] == world.boss_zone_id:
            txt += pc.get("arena_label", "  (Galehorn arena)")
            # Anchored to the layout circle: the label clears the arena's north rim.
            off = pc.get("arena_label_offset", ARENA_LABEL_OFFSET)
            lx, lz = world.circle_c[0] + off[0], world.circle_c[1] + world.arena_r + off[1]
        boxed(P(lx, lz), txt, fz, tuple(int(c * 0.5) for c in col) + (255,))
    boxed(P(ax0 + 0.6, az1 - 0.8), pc.get("apron_label", "gate apron: no spawns"), fs, (20, 90, 40))
    sl = pc.get("safe_label", {"text": "safe: Sella / regroup / entry", "at": [8.6, -19.5]})
    boxed(P(*sl["at"]), sl["text"], fs, (20, 90, 40))

    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, W, 50], fill=(246, 243, 232, 255))
    d.text((MARGIN, 12), pc.get("title", "PLAN + MONSTERS - sunmeadow v2 spawn proposal (Babylon XZ m, north up, 1 grid = 8 m) - DESIGN, not live"),
           fill=(0, 0, 0), font=fbig)

    # legend panel
    X = W + 18; Y = 20
    d.text((X, Y), "Roster", fill=(0, 0, 0), font=fbig); Y += 34
    legend_ids = list(ICON) if all(r["id"] in ICON for r in world.mon["roster"]) else [r["id"] for r in world.mon["roster"]]
    for mid in legend_ids:
        letter, col = icon_for(world, mid)
        r = world.roster[mid]
        d.ellipse([X, Y, X + 22, Y + 22], fill=col + (255,), outline=(20, 20, 20), width=2)
        tw = d.textlength(letter, font=ficon)
        d.text((X + 11 - tw / 2, Y + 3), letter, fill=(255, 255, 255) if dark_icon(world, mid) else (20, 20, 20), font=ficon)
        d.text((X + 32, Y + 2), f"{r['name']['en'].split(',')[0]}  L{r['level']} {r['tier']}", fill=(0, 0, 0), font=fb)
        d.text((X + 330, Y + 3), short_mode(world, mid), fill=(40, 40, 40), font=f)
        Y += 28
    Y += 10
    d.text((X, Y), "Markers", fill=(0, 0, 0), font=fbig); Y += 32
    items = [tuple(x) for x in pc["legend_markers"]] if "legend_markers" in pc else [
        ("filled zone", "spawn polygon (homes, patrols)"),
        ("dashed zone", "leash polygon = S1 chase limit"),
        ("red dashed ring", "aggro of aggressive monsters (step 1)"),
        ("blue dashed ring", "night aggro at a night home"),
        ("grey X + number", "compact v1 home of a migrated row"),
        ("dark line + arrow", "patrol (S1)"),
        ("crescent", "wisp moves to its night home (S4)"),
        ("dark-blue disc", "night-only row / night home"),
        ("diamond", "rain-only row (S4)"),
        ("crimson ring", f"Galehorn arena r {world.arena_r:g} m, altar r {world.altar_r:g} m"),
        ("green", "safe: gate apron, Sella, regroup, entry, camp"),
        ("cyan diamond", "windmarks (quest objects)"),
    ]
    for a, b in items:
        d.text((X, Y), a, fill=(0, 0, 0), font=fb)
        d.text((X + 170, Y), b, fill=(0, 0, 0), font=f)
        Y += 22
    Y += 10
    d.text((X, Y), pc.get("zones_header", "Zones (day rows / night / rain extra, per 100 m2)"), fill=(0, 0, 0), font=fb); Y += 26
    for zm in zones_metrics:
        col = band_col(world, zm["level_band"][0])
        d.rectangle([X, Y + 3, X + 14, Y + 15], fill=col + (200,))
        d.text((X + 22, Y), f"{zm['zone']}", fill=(0, 0, 0), font=f)
        d.text((X + 225, Y), f"L{zm['level_band'][0]}-{zm['level_band'][1]}", fill=(0, 0, 0), font=f)
        d.text((X + 290, Y), f"{zm['rows_day']} / {zm['rows_night']} / +{zm['rows_rain_extra']}", fill=(0, 0, 0), font=f)
        d.text((X + 400, Y), f"{zm['density_per_100m2_day']:.2f}", fill=(0, 0, 0), font=f)
        d.text((X + 460, Y), f"~{zm['kills_per_min_capacity_day']:.0f} kills/min", fill=(60, 60, 60), font=fs)
        Y += 21
    Y += 10
    d.text((X, Y), "Deploy steps (rows appended, ids stable)", fill=(0, 0, 0), font=fb); Y += 26
    for line in steps:
        d.text((X, Y), line, fill=(0, 0, 0), font=f); Y += 21
    Y += 10
    d.text((X, Y), "Checks", fill=(0, 0, 0), font=fb); Y += 26
    for line in summary:
        d.text((X, Y), line, fill=(0, 0, 0), font=f); Y += 21
    img.convert("RGB").save(out_png)



def compact_results(results):
    """Keep every non-sample check; reduce patrol samples to the worst one per (row, rule)."""
    out, worst = [], {}
    for c in results:
        if not str(c["check"]).startswith("patrol sample"):
            out.append(c)
            continue
        key = (c["row"], c["check"])
        prev = worst.get(key)
        if prev is None or (not c["pass"] and prev["pass"]) or (
                c["pass"] == prev["pass"] and c["value"] is not None and prev["value"] is not None
                and abs(c["value"]) < abs(prev["value"])):
            worst[key] = c
    return out + sorted(worst.values(), key=lambda c: (str(c["row"]), c["check"]))



def generic_assumptions(world):
    """Receipt notes for a region without a compact v1 base (computed from the layout and the base, never copied)."""
    L = world.lay
    out = [
        "streams: " + (", ".join(f"{s['id']} half-width {max(s['width_m']) / 2:g} m" for s in world.streams) or "none"),
        "pools (circles of water): " + (", ".join(f"{w['id']} r {w['radius_m']:g}" for w in world.pools) or "none"),
        "water hazards: " + (", ".join(hid for hid, _ in world.water_rects + world.water_polys) or "none")
        + " (polygons use a signed edge distance, negative inside)",
        f"relief blocking monsters: {len(world.relief_rects)} rectangles, {len(world.relief_polys)} polygons, "
        f"{len(world.relief_lines)} toe lines (layout relief with path_clearance_m)",
        f"props: {len(world.props)} colliding props from the level base with their collider_radius_m",
        f"boss arena from the layout: {world.arena_id} centre {list(world.circle_c)}, ring r {world.circle_r}, arena r {world.arena_r}; "
        f"boss spawn {world.spawn_id} {list(world.altar_c)} r {world.altar_r}",
        "camps: " + (", ".join(str(list(c)) for c in world.camps) or "none"),
        "quest objects (H6): " + (", ".join(world.windmarks) or "none"),
        "paths with road_safe false skip H7/H7s (intentional danger approach; H2 still applies): "
        + (", ".join(k for k, v in world.paths.items() if not v.get("road_safe", True)) or "none"),
        "aggressive aggro for checks = max(day, night) radius; day-passive/night-aggressive types use night_radius_m at night homes",
        "no compact v1 rows: every row is new (H12 migration checks against compact v1 and zones.json are skipped)",
        "kill capacity uses ATK 45 + 3/level, 0.4 s attacks, +2 s travel per kill (estimate only)",
    ]
    if L.get("surfaces"):
        out.append("walkable surfaces (not water): " + ", ".join(s["id"] for s in L["surfaces"]))
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default="planning/levels/sunmeadow-v2-layout.json")
    ap.add_argument("--base", default="planning/sunmeadow-compact-v1.json")
    ap.add_argument("--monsters", default="planning/levels/sunmeadow-v2-monsters.json")
    ap.add_argument("--items", default="content/source/items.json")
    ap.add_argument("--zones", default="content/source/zones.json")
    ap.add_argument("--out", default="planning/evidence/sunmeadow-v2-layout")
    ap.add_argument("--scratch", default=None)
    a = ap.parse_args()

    lay = json.loads(Path(a.layout).read_text(encoding="utf-8"))
    base = json.loads(Path(a.base).read_text(encoding="utf-8"))
    mon = json.loads(Path(a.monsters).read_text(encoding="utf-8"))
    items = {i["id"] for i in json.loads(Path(a.items).read_text(encoding="utf-8"))["items"]}
    world = World(lay, base, mon, items)
    # zones.json (live spawns) is only needed to migrate compact v1 rows (Sunmeadow); a new region has none.
    live = json.loads(Path(a.zones).read_text(encoding="utf-8"))["zones"][0]["monster_spawns"] if world.compact_rows else []
    ck = Checker(world)

    rows = mon["spawn_rows"]
    for r in rows:
        zone = world.zones[r["zone"]]
        day_phase = "night" if (night_aggressive_only(world.roster[r["enemy"]]) and "night_home_xz" not in r and "night" in r["phases"]) else "day"
        ck.point(r["row"], "home", tuple(r["home_xz"]), r["enemy"], zone, day_phase)
        if "night_home_xz" in r:
            ck.point(r["row"], "night home", tuple(r["night_home_xz"]), r["enemy"], world.zones[r["night_zone"]], "night")
        pt = r.get("patrol")
        if pt:
            pts = [tuple(q) for q in pt["points"]]
            for q in pts:
                ck.point(r["row"], "patrol vertex", q, r["enemy"], zone, day_phase)
            seq = pts + ([pts[0]] if pt["type"] == "loop" else [])
            for q in densify(seq, mon["rules"]["R8_patrol_sample_m"]):
                ck.point(r["row"], "patrol sample", q, r["enemy"], zone, day_phase, sample=True)
    for z in mon["zones"]:
        x0, x1, z0, z1 = world.walk
        sp = world.zone_spawn_shape(z)
        ck.add(f"zone:{z['id']}", "H3 spawn polygon inside walkable_hint", None, str(world.walk),
               all(x0 <= q[0] <= x1 and z0 <= q[1] <= z1 for q in sp))
        ck.leash_polygon(z)
    roster_validation(ck, world)
    migration_validation(ck, world, live)
    spacing(ck, world)

    # Before/after: the 13 compact v1 homes under the same rules (informational).
    before = Checker(world)
    for i in range(world.compact_rows):
        r = dict(rows[i]); p = tuple(r["compact_v1_xz"])
        before.point(i, "compact v1 home", p, r["enemy"], None, "day")
    before_fail = {}
    for c in before.results:
        if not c["pass"]:
            before_fail.setdefault(c["row"], []).append(f"{c['check']} = {c['value']} (limit {c['limit']})")

    reach = [x for x in (chase_reach(world, r, r["enemy"]) for r in rows if r["deploy_step"] == 0) if x]
    zones = zone_metrics(world)
    clock = clock_phases()

    hard = [c for c in ck.results if c["hard"]]
    failed = [c for c in hard if not c["pass"]]
    step_rows = {s: sum(1 for r in rows if r["deploy_step"] <= s) for s in (0, 1, 2)}
    summary = [
        f"{len(hard)} hard checks, {len(failed)} failed",
        f"spawn rows: step0 {step_rows[0]}, step1 {step_rows[1]}, step2 {step_rows[2]} (wire cap {world.rules['R10_wire_cap']})",
    ]
    if world.compact_rows:
        summary.append(f"compact v1 rows failing v2 rules: {len(before_fail)} of {world.compact_rows} (migrated)")
    summary += [
        f"step-0 chase reach over a hazard: {sum(1 for x in reach if not x['hazard_ok'])} of {len(reach)} rows",
        f"clock: day {clock['day_real_min']} min, night {clock['night_real_min']} min per 45-min cycle",
    ]

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    scratch = Path(a.scratch) if a.scratch else Path(tempfile.mkdtemp(prefix="monsters-plan-"))
    scratch.mkdir(parents=True, exist_ok=True)
    rlp.PX = PX
    argv = sys.argv
    sys.argv = ["render_layout_plan.py", a.layout, "--base", a.base, "--out", str(scratch)]
    try:
        rlp.main()
    finally:
        sys.argv = argv
    png = out / "monsters-plan.png"
    pc = plan_cfg(world)
    sl = pc.get("step_labels", ["step 0, content only", "step 1, S1 S2 S4", "step 2, S3 S5"])
    sn = pc.get("step_notes", ["moves + Brookclaw", "night/rain rows, zones", "Turfback elite, Galehorn boss"])
    steps = [f"{sl[0]}: rows 0-{step_rows[0] - 1} ({step_rows[0]}) - {sn[0]}",
             f"{sl[1]}: + rows {step_rows[0]}-{step_rows[1] - 1} ({step_rows[1]}) - {sn[1]}",
             f"{sl[2]}: + rows {step_rows[1]}-{step_rows[2] - 1} ({step_rows[2]}) - {sn[2]}"]
    render(world, scratch / "plan.png", png, summary, zones, steps)

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    used = [("layout", a.layout), ("base", a.base), ("monsters", a.monsters), ("items", a.items)]
    if world.compact_rows:
        used.append(("zones", a.zones))
    report = {
        "tool": "tools/levels/check_monster_spawns.py",
        "inputs": {k: {"path": v, "sha256": sha(v)} for k, v in used},
        "assumptions": generic_assumptions(world) if not world.compact_rows else ["stream half-width = max(width_m)/2 = 2.25 m",
                        "layout hazards of kind water are rectangles of water: " + ", ".join(
                            f"{hid} x {r[0]:g}..{r[1]:g} z {r[2]:g}..{r[3]:g}" for hid, r in world.water_rects),
                        "trunk radii: old oak 1.8 m, ancient pine 1.2 m, lookout tower 2.5 m, signpost 0.3 m "
                        "(positions from the layout landmarks; lookout from the compact v1 POI)",
                        f"windstone circle, arena and altar from the layout: centre {list(world.circle_c)} r {world.circle_r}, "
                        f"arena r {world.arena_r}, altar {list(world.altar_c)} r {world.altar_r}",
                        "prop radius = max(collider x, z)/2 from compact v1 world_props (already scaled); relocated props use "
                        "the layout position: " + ", ".join(f"{k} {list(v)}" for k, v in world.moved_props.items()),
                        "paths with road_safe false skip H7/H7s (intentional danger approach; H2 still applies): "
                        + (", ".join(k for k, v in world.paths.items() if not v.get("road_safe", True)) or "none"),
                        "aggressive aggro for checks = max(day, night) radius; wisps use 7 m at night homes and in the glade",
                        "kill capacity uses ATK 45 + 3/level, 0.4 s attacks, +2 s travel per kill (estimate only)"],
        "summary": summary,
        "plan_png": str(png), "plan_sha256": sha(png),
        "counts": {"hard_checks": len(hard), "failed": len(failed), "rows_by_step": step_rows},
        "failed": failed,
        "compact_v1_rows_failing_v2_rules": before_fail,
        "step0_chase_reach": reach,
        "zones": zones,
        "clock": clock,
        "checks": compact_results(ck.results),
        "checks_note": "patrol samples (every 0.5 m) are reduced to the worst sample per row and rule; every other check is listed",
    }
    (out / "monsters-checks.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"plan: {png}")
    for line in summary:
        print(line)
    for c in failed[:60]:
        print("  FAIL", c["row"], "|", c["check"], c["value"], c["limit"])


if __name__ == "__main__":
    main()
