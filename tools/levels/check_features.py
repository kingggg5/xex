"""Sunmeadow v3 feature playability checks (lane C-MAP-V3, 2026-10-03).

Usage:
  python tools/levels/check_features.py [--layout planning/levels/sunmeadow-v2-layout.json]
         [--monsters planning/levels/sunmeadow-v2-monsters.json] [--zones content/source/zones.json]
         [--enemies content/source/enemies.json] [--dressing planning/levels/sunmeadow-v3-dressing.json]
         [--out planning/evidence/sunmeadow-v3-features/checks]

Prints one PASS/FAIL line per check and writes <out>/features-checks.json and <out>/features-plan.png
(a PLAN image: walk network, colliders, calm zones, aggro discs, spawn slots, sightlines).

Checks (brief 04-layout-v3 M2):
  C1 reachability from spawn along walk lines >= 2.5 m (main trails >= 4 m), every feature + every POI stand
  C2 no feature footprint (collider/building) on a walk line
  C3 calm zones hold no monster aggro disc (design homes, proposed homes and live zones.json positions)
  C4 aggro discs >= 3 m clear of the first 48 player spawn slots
  C5 arena keep-clear (12 m, collider edges >= 11.5 m) and warps unchanged
  C6 grotto dimensions
  C7 pier reachable + fishing spot on the platform
  C8 spawn sightline to >= 2 features
  C9 c7/c8 cell bounds and the Z = -64 seam
Exit code 1 when any HARD check fails. Monster rows are judged three ways: `design` (home_xz), `design+proposals`
(proposed_home_xz_v3 where present) and `live` (zones.json + enemies.json). Hard = design+proposals and live.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SPAWN_SLOTS = [(x, -3.0 - 1.5 * row) for row in range(12) for x in (-3.0, -1.0, 1.0, 3.0)]
SPAWN_EYE = (0.0, -3.0)
ARENA = ((0.0, -68.0), 12.0, 11.5)
WARPS = {"warp_windstone_portal": ((0.0, -68.0), 1.8), "warp_sunmeadow_south": ((0.0, -101.0), 3.0)}
CELL = 64.0
PLAYER_R = 0.35


# ----------------------------------------------------------------------------------------------- geometry
def seg_dist(p, a, b):
    ax, az = a; bx, bz = b; px, pz = p
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / L2))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz)), t


def poly_dist(p, pts):
    """Distance from p to an open polyline."""
    if len(pts) == 1:
        return math.hypot(p[0] - pts[0][0], p[1] - pts[0][1])
    return min(seg_dist(p, pts[i], pts[i + 1])[0] for i in range(len(pts) - 1))


def poly_dist_interior(p, pts):
    """Distance to a polyline ignoring the two terminal end caps (projection must not clamp at the ends)."""
    best = math.inf
    n = len(pts)
    for i in range(n - 1):
        d, t = seg_dist(p, pts[i], pts[i + 1])
        if (i == 0 and t <= 0.0) or (i == n - 2 and t >= 1.0):
            continue
        best = min(best, d)
    return best


def pip(p, poly):
    x, z = p; inside = False; n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]; x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = x1 + (z - z1) * (x2 - x1) / (z2 - z1)
            if x < xi:
                inside = not inside
    return inside


def ring_dist(p, poly):
    return min(seg_dist(p, poly[i], poly[(i + 1) % len(poly)])[0] for i in range(len(poly)))


def poly_sdist(p, poly):
    """Signed distance: negative inside."""
    d = ring_dist(p, poly)
    return -d if pip(p, poly) else d


def segs_intersect(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def polyline_poly_dist(pts, poly):
    """Min distance between a polyline and a polygon (0 when they touch or overlap)."""
    for q in pts:
        if pip(q, poly):
            return 0.0
    for i in range(len(pts) - 1):
        for j in range(len(poly)):
            if segs_intersect(pts[i], pts[i + 1], poly[j], poly[(j + 1) % len(poly)]):
                return 0.0
    d = min(ring_dist(q, poly) for q in pts)
    d = min(d, min(poly_dist(q, pts) for q in poly))
    return d


def polyline_dist(a, b):
    for i in range(len(a) - 1):
        for j in range(len(b) - 1):
            if segs_intersect(a[i], a[i + 1], b[j], b[j + 1]):
                return 0.0
    return min(min(poly_dist(q, b) for q in a), min(poly_dist(q, a) for q in b))


def resample(pts, step=0.25):
    out = [tuple(pts[0])]
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(math.ceil(L / step)))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


def rect_poly(x0, x1, z0, z1):
    return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]


def shape_outline(c):
    """Collider dict -> polygon (list of xz). Box yaw follows Babylon: local +x -> (cos y, -sin y)."""
    sh = c.get("shape")
    if sh == "polygon":
        return [tuple(q) for q in c["polygon_xz"]]
    cx, cz = c["center_xz"]
    if sh == "circle":
        r = c["radius_m"]
        return [(cx + r * math.cos(2 * math.pi * k / 24), cz + r * math.sin(2 * math.pi * k / 24)) for k in range(24)]
    yaw = float(c.get("yaw_rad", 0.0)); cy, sy = math.cos(yaw), math.sin(yaw)
    if sh == "box":
        hx, hz = c["size_m"][0] / 2, c["size_m"][1] / 2
        loc = [(-hx, -hz), (hx, -hz), (hx, hz), (-hx, hz)]
    elif sh == "capsule":
        hl, r = c["length_m"] / 2, c["radius_m"]
        loc = [(-hl - r, -r), (hl + r, -r), (hl + r, r), (-hl - r, r)]
    else:
        raise ValueError(sh)
    return [(cx + lx * cy + lz * sy, cz - lx * sy + lz * cy) for lx, lz in loc]


# ----------------------------------------------------------------------------------------------- inputs
def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def aggro_values(roster_entry):
    """Deployed step0 aggro + planned numeric aggro (step1 night_aggro, step2 aggro). Missing step0 -> not deployed."""
    t = roster_entry.get("tuning", {})
    vals = []
    s0 = t.get("step0", {})
    if isinstance(s0.get("aggro"), (int, float)):
        vals.append(("step0", float(s0["aggro"])))
    s1 = t.get("step1", {})
    if isinstance(s1.get("night_aggro"), (int, float)):
        vals.append(("step1_night", float(s1["night_aggro"])))
    if isinstance(s1.get("aggro"), (int, float)):
        vals.append(("step1", float(s1["aggro"])))
    s2 = t.get("step2", {})
    if isinstance(s2.get("aggro"), (int, float)):
        vals.append(("step2", float(s2["aggro"])))
    return vals


def monster_sets(M, zones_live, enemies):
    roster = {r["id"]: r for r in M["roster"]}
    design, proposed, live = [], [], []
    for s in M["spawn_rows"]:
        aggs = aggro_values(roster[s["enemy"]])
        patrol = [tuple(q) for q in s["patrol"]["points"]] if s.get("patrol") else None
        if s["enemy"] == "galehorn":
            continue  # boss: arena-leashed, checked by C5 (arena) and the monster checker
        for tag, a in aggs:
            design.append({"row": s["row"], "enemy": s["enemy"], "xz": tuple(s["home_xz"]), "aggro": a, "tag": tag,
                           "patrol": patrol, "phases": s.get("phases")})
            ph = tuple(s.get("proposed_home_xz_v3") or s["home_xz"])
            proposed.append({"row": s["row"], "enemy": s["enemy"], "xz": ph, "aggro": a, "tag": tag,
                             "patrol": patrol, "phases": s.get("phases"), "moved": "proposed_home_xz_v3" in s})
    eg = {e["id"]: e for e in enemies}
    for i, sp in enumerate(zones_live):
        a = float(eg[sp["enemy"]]["aggro"])
        live.append({"row": i, "enemy": sp["enemy"], "xz": (float(sp["x"]), float(sp["z"])), "aggro": a, "tag": "live",
                     "patrol": None, "phases": None})
    return design, proposed, live


def live_spawns(zones_doc):
    zs = zones_doc if isinstance(zones_doc, list) else zones_doc.get("zones", [])
    for z in zs:
        if z.get("id") == 1:
            return z.get("monster_spawns", [])
    return []


# ----------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default=str(ROOT / "planning/levels/sunmeadow-v2-layout.json"))
    ap.add_argument("--monsters", default=str(ROOT / "planning/levels/sunmeadow-v2-monsters.json"))
    ap.add_argument("--zones", default=str(ROOT / "content/source/zones.json"))
    ap.add_argument("--enemies", default=str(ROOT / "content/source/enemies.json"))
    ap.add_argument("--dressing", default=str(ROOT / "planning/levels/sunmeadow-v3-dressing.json"))
    ap.add_argument("--out", default=str(ROOT / "planning/evidence/sunmeadow-v3-features/checks"))
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args(argv)

    L = load(args.layout); M = load(args.monsters)
    ed = load(args.enemies); enemies = ed if isinstance(ed, list) else ed.get("enemies", [])
    zl = live_spawns(load(args.zones))
    dressing = load(args.dressing) if Path(args.dressing).exists() else None
    F = {f["id"]: f for f in L["features"]}
    checks = []

    def add(cid, name, ok, value=None, limit=None, hard=True, info=None):
        checks.append({"id": cid, "check": name, "pass": bool(ok), "hard": hard,
                       "value": (round(value, 3) if isinstance(value, float) else value), "limit": limit,
                       **({"info": info} if info else {})})

    # ------------------------------------------------------------ walk network + solids
    walk = L["walk_network"]["items"]
    lines = [w for w in walk if "points" in w]
    decks = [w for w in walk if w["class"] == "deck"]
    solids = []  # (id, feature, polygon, kind)
    for f in L["features"]:
        for c in f.get("colliders", []):
            solids.append((c["id"], f["id"], shape_outline(c), "collider"))
    waters = [(h["id"], [tuple(q) for q in h["polygon_xz"]]) for h in L["hazards"] if "polygon_xz" in h]
    pools = [(w["id"], tuple(w["center_xz"]), w["radius_m"]) for w in L["water"] if w["kind"] == "pool"]

    # C1 widths
    for w in lines:
        lim = 4.0 if w["class"] == "main" else 2.5
        add("C1w", f"walk line {w['id']} ({w['class']}) width", w["width_m"] >= lim - 1e-9, float(w["width_m"]), f">= {lim}")
    for d in decks:
        poly = [tuple(q) for q in d["polygon_xz"]]
        xs = [q[0] for q in poly]; zs = [q[1] for q in poly]
        wmin = min(max(xs) - min(xs), max(zs) - min(zs))
        add("C1w", f"deck {d['id']} narrow side", wmin >= 2.5 - 1e-9, float(wmin), ">= 2.5")

    # C1 graph
    def item_geo(w):
        return ("line", [tuple(q) for q in w["points"]], w["width_m"]) if "points" in w else \
               ("poly", [tuple(q) for q in w["polygon_xz"]], None)

    def touch(a, b):
        ka, ga, wa = item_geo(a); kb, gb, wb = item_geo(b)
        if ka == "line" and kb == "line":
            return polyline_dist(ga, gb) <= max(wa, wb) / 2 + 0.05
        if ka == "line" and kb == "poly":
            return polyline_poly_dist(ga, gb) <= wa / 2 + 0.05
        if ka == "poly" and kb == "line":
            return polyline_poly_dist(gb, ga) <= wb / 2 + 0.05
        return polyline_poly_dist(ga + [ga[0]], gb) <= 0.05

    n = len(walk)
    adj = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if touch(walk[i], walk[j]):
                adj[i].add(j); adj[j].add(i)
    start = [i for i, w in enumerate(walk) if "points" in w and poly_dist(SPAWN_EYE, [tuple(q) for q in w["points"]]) <= w["width_m"] / 2 + 0.5]
    add("C1", "spawn (0,-3) sits on a walk line", bool(start), [walk[i]["id"] for i in start])
    seen = set(start); stack = list(start)
    while stack:
        i = stack.pop()
        for j in sorted(adj[i]):
            if j not in seen:
                seen.add(j); stack.append(j)
    reached = [walk[i] for i in sorted(seen)]
    reached_ids = [w["id"] for w in reached]
    unreached = [w["id"] for i, w in enumerate(walk) if i not in seen]
    add("C1", "every walk line and deck connects to spawn", not unreached, len(reached), f"{len(walk)} items",
        info={"unreached": unreached})

    def near_reached(p, slack):
        best = math.inf; via = None
        for w in reached:
            k, g, wd = item_geo(w)
            d = (poly_dist(p, g) - wd / 2) if k == "line" else max(0.0, poly_sdist(p, g))
            if d < best:
                best, via = d, w["id"]
        return best, via

    def blocked(a, b):
        for sid, fid, poly, _ in solids:
            for i in range(len(poly)):
                if segs_intersect(a, b, poly[i], poly[(i + 1) % len(poly)]):
                    return sid
        for hid, poly in waters:
            for i in range(len(poly)):
                if segs_intersect(a, b, poly[i], poly[(i + 1) % len(poly)]):
                    return hid
        return None

    feat_area = {
        "waterfall_grotto": rect_poly(-7.0, 12.25, -46.0, -34.0),
        "lotus_mere": [tuple(q) for q in F["lotus_mere"]["geometry"]["pond_outline_polygon_xz"]],
        "brightwater_cove": [tuple(q) for q in F["brightwater_cove"]["geometry"]["beach_polygon_xz"]],
        "sunmeadow_croft": rect_poly(*F["sunmeadow_croft"]["bounds_xz"]),
    }
    for fid, area in feat_area.items():
        hit = [w["id"] for w in reached if (polyline_poly_dist(item_geo(w)[1], area) <= (item_geo(w)[2] or 0) / 2 + 0.05
                                            if item_geo(w)[0] == "line" else polyline_poly_dist(item_geo(w)[1] + [item_geo(w)[1][0]], area) <= 0.05)]
        add("C1", f"feature {fid} reachable from spawn", bool(hit), hit[:4])
        for p in F[fid].get("pois", []):
            stand = tuple(p.get("stand_xz") or p["position_xz"])
            d, via = near_reached(stand, 0)
            ok = d <= 3.0
            add("C1p", f"POI {p['id']} stand point within 3 m of a reached walk item", ok, float(max(d, 0.0)), "<= 3.0",
                info={"via": via})

    # C2 footprints vs walk lines (interior of the line band; terminal end caps are stand points)
    for sid, fid, poly, _ in solids:
        dense = resample(poly + [poly[0]], 0.2)
        for w in lines:
            pts = [tuple(q) for q in w["points"]]
            d = min(poly_dist_interior(q, pts) for q in dense)
            inside = any(pip(q, poly) for q in resample(pts, 0.25)[1:-1])
            if d < w["width_m"] / 2 - 0.02 or inside:
                add("C2", f"{sid} clear of walk line {w['id']}", False, float(d - w['width_m'] / 2), ">= 0 (band edge)")
                break
        else:
            add("C2", f"{sid} clear of every walk line band", True)
    for f in L["features"]:
        for b in f.get("buildings", []):
            if "center_xz" in b and "diameter_m" in b:
                c = tuple(b["center_xz"]); r = b["diameter_m"] / 2
                d = min(poly_dist(c, [tuple(q) for q in w["points"]]) - w["width_m"] / 2 - r for w in lines)
                add("C2", f"building {b['id']} clear of walk lines", d >= 0.0, float(d), ">= 0")

    # C3 calm zones
    design, proposed, live = monster_sets(M, zl, enemies)
    calm = L["calm_zones"]["zones"]
    calm_rows = []
    for z in calm:
        c = tuple(z["center_xz"]); R = z["radius_m"]
        for label, ms, hard in (("design", design, False), ("design+proposals", proposed, True), ("live", live, True)):
            worst = None
            for m in ms:
                pts = [m["xz"]] + (m["patrol"] or [])
                d = min(math.hypot(p[0] - c[0], p[1] - c[1]) for p in pts)
                margin = d - R - m["aggro"]
                if worst is None or margin < worst[0]:
                    worst = (margin, m["row"], m["enemy"], m["tag"], m["xz"])
                if margin < 0:
                    calm_rows.append({"zone": z["id"], "set": label, "row": m["row"], "enemy": m["enemy"], "tag": m["tag"],
                                      "xz": m["xz"], "margin_m": round(margin, 2)})
            add("C3", f"{z['id']} (r {R}) holds no aggro disc [{label}]", worst[0] >= 0, float(worst[0]), ">= 0",
                hard=hard, info={"closest_row": worst[1], "enemy": worst[2], "aggro_tag": worst[3], "xz": worst[4]})

    # C4 spawn slots
    slot_rows = []
    for label, ms, hard in (("design", design, False), ("design+proposals", proposed, True), ("live", live, True)):
        worst = None
        for m in ms:
            d = min(math.hypot(m["xz"][0] - sx, m["xz"][1] - sz) for sx, sz in SPAWN_SLOTS)
            margin = d - m["aggro"]
            if margin < 3.0:
                slot_rows.append({"set": label, "row": m["row"], "enemy": m["enemy"], "tag": m["tag"], "xz": m["xz"],
                                  "clear_m": round(margin, 2)})
            if worst is None or margin < worst[0]:
                worst = (margin, m["row"], m["enemy"], m["tag"])
        add("C4", f"aggro discs >= 3 m clear of the 48 spawn slots [{label}]", worst[0] >= 3.0, float(worst[0]), ">= 3.0",
            hard=hard, info={"closest_row": worst[1], "enemy": worst[2], "aggro_tag": worst[3]})

    # C5 arena + warps
    (ac, ar, aedge) = ARENA
    def arena_edge(poly):
        return min(math.hypot(q[0] - ac[0], q[1] - ac[1]) for q in resample(poly + [poly[0]], 0.2))
    worst = min((arena_edge(poly), sid) for sid, fid, poly, _ in solids)
    add("C5", "feature collider edges >= 11.5 m from the arena centre", worst[0] >= aedge, float(worst[0]), f">= {aedge}",
        info={"closest": worst[1]})
    if dressing:
        sol = [e for e in dressing["entries"] if e["collider"] == "solid"]
        dmin = min((math.hypot(e["x"] - ac[0], e["z"] - ac[1]) - e["footprint_r"], e["id"]) for e in sol) if sol else (99.0, None)
        add("C5", "dressing solid edges >= 11.5 m from the arena centre", dmin[0] >= aedge, float(dmin[0]), f">= {aedge}",
            info={"closest": dmin[1]})
    circ = next(l for l in L["landmarks"] if l["id"] == "windstone_circle")
    add("C5", "arena keep-clear 12 m at (0,-68)", circ["center_xz"] == [0, -68] and circ["arena_keep_clear_m"] == 12, circ["arena_keep_clear_m"], 12)
    wp = circ["warp"]; sg = next(l for l in L["landmarks"] if l["id"] == "south_gate")
    add("C5", "warp_windstone_portal r 1.8 at (0,-68)", wp["id"] == "warp_windstone_portal" and wp["center_xz"] == [0, -68] and wp["trigger_radius_m"] == 1.8, [wp["center_xz"], wp["trigger_radius_m"]])
    add("C5", "warp_sunmeadow_south r 3.0 at (0,-101)", sg["warp"]["id"] == "warp_sunmeadow_south" and sg["position_xz"] == [0, -101] and sg["warp"]["trigger_radius_m"] == 3.0, [sg["position_xz"], sg["warp"]["trigger_radius_m"]])
    for wid, (wc, wr) in WARPS.items():
        dmin = min((arena_edge(poly) if False else min(math.hypot(q[0] - wc[0], q[1] - wc[1]) for q in poly), sid) for sid, fid, poly, _ in solids)
        add("C5", f"no feature collider inside {wid} trigger (+1 m)", dmin[0] >= wr + 1.0, float(dmin[0]), f">= {wr + 1.0}")
    for sx, sz in [(0.0, -101.0)]:
        pass

    # C6 grotto
    g = F["waterfall_grotto"]["carve"]
    add("C6", "grotto mouth 4.5 m wide", abs(g["mouth"]["width_m"] - 4.5) < 0.05, g["mouth"]["width_m"], 4.5)
    add("C6", "grotto mouth 5.0 m high", abs(g["mouth"]["height_m"] - 5.0) < 0.05, g["mouth"]["height_m"], 5.0)
    tp = g["tunnel_polygon_xz"]; tl = max(q[0] for q in tp) - min(q[0] for q in tp)
    add("C6", "grotto tunnel length <= 5 m", tl <= 5.0 + 1e-9, float(tl), "<= 5.0")
    tw = max(q[1] for q in tp) - min(q[1] for q in tp)
    add("C6", "grotto tunnel clear width = mouth width", abs(tw - 4.5) < 0.05, float(tw), 4.5)
    ch = g["chamber"]; cpoly = [tuple(q) for q in ch["polygon_xz"]]
    rmean = sum(math.hypot(q[0] - ch["center_xz"][0], q[1] - ch["center_xz"][1]) for q in cpoly) / len(cpoly)
    add("C6", "grotto chamber mean radius ~6 m (5.0-6.5)", 5.0 <= rmean <= 6.5, float(rmean), "5.0..6.5")
    add("C6", "grotto chamber open to sky", ch.get("open_to_sky") is True, ch.get("open_to_sky"), True)
    chest = next(p for p in F["waterfall_grotto"]["pois"] if p["id"] == "grotto_chest")
    add("C6", "grotto_chest inside the chamber (>= 0.5 m from the wall)", poly_sdist(tuple(chest["position_xz"]), cpoly) <= -0.5,
        float(-poly_sdist(tuple(chest["position_xz"]), cpoly)), ">= 0.5")
    tun_end = max(q[0] for q in tp)
    add("C6", "tunnel opens into the chamber", abs(poly_sdist((tun_end, ch["center_xz"][1]), cpoly)) < 0.2 or pip((tun_end + 0.1, ch["center_xz"][1]), cpoly), tun_end)

    # C7 pier
    pier = next(d for d in F["brightwater_cove"]["decks"] if d["id"] == "brightwater_pier")
    plat = next(d for d in F["brightwater_cove"]["decks"] if d["id"] == "brightwater_pier_platform")
    add("C7", "pier length >= 16 m", pier["length_m"] >= 16, pier["length_m"], ">= 16")
    add("C7", "pier reachable from spawn", "brightwater_pier" in reached_ids and "brightwater_pier_platform" in reached_ids,
        [i for i in reached_ids if "pier" in i])
    fs = next(p for p in F["brightwater_cove"]["pois"] if p["id"] == "cove_fishing_spot")
    add("C7", "cove_fishing_spot on the pier platform", pip(tuple(fs["position_xz"]), [tuple(q) for q in plat["polygon_xz"]]), fs["position_xz"])
    lake = next(h for h in L["hazards"] if h["id"] == "brightwater_cove_lake")
    px = [q[0] for q in pier["polygon_xz"]]; pz = [q[1] for q in pier["polygon_xz"]]
    pier_pts = resample(rect_poly(min(px) + 0.1, max(px) - 0.1, min(pz) + 0.1, max(pz) - 0.1) +
                        [(min(px) + 0.1, min(pz) + 0.1)], 0.25)
    wet = sum(1 for q in pier_pts if pip(q, [tuple(v) for v in lake["polygon_xz"]]))
    add("C7", "pier deck outline is not inside the lake hazard (deck notch)", wet == 0, wet, 0)

    # C8 sightlines
    vegs = [(v["id"], [tuple(q) for q in v["polygon_xz"]]) for v in L["vegetation_zones"]
            if "polygon_xz" in v and v["kind"] in ("broadleaf_grove", "pine_stand")]
    corridors = [[tuple(q) for q in s["corridor_polygon_xz"]] for s in L["sightlines"] if "corridor_polygon_xz" in s]
    bluff = rect_poly(*next(r for r in L["relief"] if r["id"] == "inner_bluff")["footprint_xz"])
    targets = {"waterfall_grotto": ((-7.0, -38.0), "falls lip on the bluff face (grotto behind the curtain)"),
               "lotus_mere": ((-43.2, 8.2), "light shaft 2"),
               "brightwater_cove": ((-52.0, -74.25), "pier"),
               "sunmeadow_croft": ((38.6, 11.4), "dome hut")}
    visible = []
    sl_info = {}
    for fid, (t, what) in targets.items():
        pts = resample([SPAWN_EYE, t], 0.5)
        dist = math.hypot(t[0] - SPAWN_EYE[0], t[1] - SPAWN_EYE[1])
        veg_len = 0.0; why = []
        for vid, poly in vegs:
            k = sum(1 for q in pts if pip(q, poly) and not any(pip(q, c) for c in corridors))
            if k:
                veg_len += 0.5 * k; why.append(f"{vid} {0.5 * k:.1f} m")
        bl = sum(1 for q in pts[:-2] if pip(q, bluff)) * 0.5
        if bl > 0.5:
            why.append(f"inner_bluff {bl:.1f} m")
        cliff = next(r for r in L["relief"] if r["id"] == "west_cliffs")["polyline_xz"]
        ok = dist <= 75.0 and veg_len <= 6.0 and bl <= 0.5
        if dist > 75:
            why.append(f"range {dist:.0f} m > 75")
        sl_info[fid] = {"target_xz": t, "what": what, "distance_m": round(dist, 1), "blocked_by": why, "visible": ok}
        if ok:
            visible.append(fid)
    add("C8", "spawn (0,-3) has a sightline to >= 2 features", len(visible) >= 2, len(visible), ">= 2",
        info=sl_info)

    # C9 cells / seam
    def cells_of(poly):
        cs = set()
        for q in poly:
            cs.add((math.floor(q[0] / CELL), math.floor(q[1] / CELL)))
        return cs
    for sid, fid, poly, _ in solids:
        if sid == "inner_bluff_solid_v3":
            add("C9", f"{sid} straddles x=0 like the v2 inner_bluff footprint (known, v2)", True, sorted(cells_of(poly)), hard=False)
            continue
        cs = cells_of(poly)
        add("C9", f"{sid} inside one 64 m art cell", len(cs) == 1, sorted(cs))
    seam_hits = [sid for sid, fid, poly, _ in solids if min(abs(q[1] + 64.0) for q in resample(poly + [poly[0]], 0.2)) < 0.5
                 or (min(q[1] for q in poly) < -64.0 < max(q[1] for q in poly))]
    add("C9", "no feature collider within 0.5 m of or across the Z=-64 seam", not seam_hits, seam_hits)
    c7 = rect_poly(-64, 0, -128, -64); c8 = rect_poly(0, 64, -128, -64)
    cove_cols = [s for s in solids if s[1] == "brightwater_cove"]
    add("C9", "Brightwater Cove colliders lie inside c7 [-64,0,-128,-64]",
        all(all(pip(q, c7) for q in poly) for _, _, poly, _ in cove_cols), [s[0] for s in cove_cols])
    stage = L["bounds_xz"]["stage"]
    out_stage = [sid for sid, fid, poly, _ in solids if any(not (stage[0] <= q[0] <= stage[1] and stage[2] <= q[1] <= stage[3]) for q in poly)]
    add("C9", "feature colliders inside the stage bounds", not out_stage, out_stage)

    # ------------------------------------------------------------ report
    hard_fail = [c for c in checks if c["hard"] and not c["pass"]]
    soft_fail = [c for c in checks if not c["hard"] and not c["pass"]]
    for c in checks:
        tag = "PASS" if c["pass"] else ("FAIL" if c["hard"] else "WARN")
        v = "" if c["value"] is None else f" value={c['value']}"
        lim = "" if c["limit"] is None else f" limit={c['limit']}"
        print(f"{tag} {c['id']} {c['check']}{v}{lim}")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rep = {"tool": "tools/levels/check_features.py", "layout": str(Path(args.layout).name), "layout_version": L["version"],
           "summary": f"{len(checks)} checks, {len(hard_fail)} hard failed, {len(soft_fail)} soft (design-only) warnings",
           "calm_conflicts": calm_rows, "spawn_slot_conflicts": slot_rows, "sightlines_from_spawn": sl_info,
           "reached_walk_items": reached_ids, "checks": checks}
    (out / "features-checks.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not args.no_png:
        render_png(L, out / "features-plan.png", design, proposed, live, sl_info, dressing)
    print(rep["summary"])
    return 1 if hard_fail else 0


def render_png(L, path, design, proposed, live, sl_info, dressing):
    from PIL import Image, ImageDraw, ImageFont
    x0, x1, z0, z1 = -76, 64, -112, 26
    PX = 7
    W, H = int((x1 - x0) * PX), int((z1 - z0) * PX) + 40
    img = Image.new("RGB", (W, H), (238, 234, 218)); d = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 12); big = ImageFont.truetype("arialbd.ttf", 16)
    except OSError:
        font = big = ImageFont.load_default()
    def P(x, z):
        return ((x - x0) * PX, 40 + (z1 - z) * PX)
    for gx in range(-64, 65, 8):
        d.line([P(gx, z0), P(gx, z1)], fill=(0, 0, 0, 90 if gx % 64 == 0 else 20), width=2 if gx % 64 == 0 else 1)
    for gz in range(-112, 25, 8):
        d.line([P(x0, gz), P(x1, gz)], fill=(0, 0, 0, 90 if gz % 64 == 0 else 20), width=2 if gz % 64 == 0 else 1)
    for v in L["vegetation_zones"]:
        if "polygon_xz" in v:
            d.polygon([P(*q) for q in v["polygon_xz"]], fill=(80, 140, 60, 50))
    r = next(r for r in L["relief"] if r["id"] == "west_cliffs")
    d.line([P(*q) for q in r["polyline_xz"]], fill=(110, 90, 75, 120), width=10)
    for f in L["features"]:
        for c in f.get("colliders", []):
            d.polygon([P(*q) for q in shape_outline(c)], fill=(130, 100, 80, 200), outline=(60, 40, 20))
    for w in L["water"]:
        if w["kind"] == "stream":
            d.line([P(*q) for q in w["points"]], fill=(60, 130, 200, 230), width=int(4 * PX), joint="curve")
        elif w["kind"] == "pool":
            cx, cz = w["center_xz"]; rr = w["radius_m"]
            d.ellipse([P(cx - rr, cz + rr), P(cx + rr, cz - rr)], fill=(60, 130, 200, 230))
        elif w["kind"] == "lake":
            d.polygon([P(*q) for q in w["outline_xz"]], fill=(60, 140, 205, 200), outline=(30, 70, 140))
    for w in L["walk_network"]["items"]:
        if "points" in w:
            col = (200, 160, 100, 230) if w["class"] in ("main", "branch") else (170, 130, 80, 230)
            d.line([P(*q) for q in w["points"]], fill=col, width=max(2, int(w["width_m"] * PX)), joint="curve")
        else:
            fill = (150, 100, 50, 240) if w["class"] == "deck" else (220, 200, 150, 90)
            d.polygon([P(*q) for q in w["polygon_xz"]], fill=fill, outline=(80, 50, 20))
    if dressing:
        for e in dressing["entries"]:
            col = {"solid": (90, 70, 60, 230), "soft": (110, 140, 70, 200), "none": (140, 170, 100, 150)}[e["collider"]]
            rr = max(0.25, e["footprint_r"])
            d.ellipse([P(e["x"] - rr, e["z"] + rr), P(e["x"] + rr, e["z"] - rr)], fill=col)
    for z in L["calm_zones"]["zones"]:
        cx, cz = z["center_xz"]; R = z["radius_m"]
        d.ellipse([P(cx - R, cz + R), P(cx + R, cz - R)], outline=(40, 160, 90, 255), width=3)
        d.text(P(cx - R, cz + R + 2), z["id"], fill=(20, 110, 60), font=font)
    for m in proposed:
        if m["tag"] in ("step0",):
            cx, cz = m["xz"]; a = m["aggro"]
            d.ellipse([P(cx - a, cz + a), P(cx + a, cz - a)], outline=(210, 60, 40, 200), width=2)
    for m in live:
        cx, cz = m["xz"]; a = m["aggro"]
        d.ellipse([P(cx - a, cz + a), P(cx + a, cz - a)], outline=(150, 40, 160, 160), width=1)
    for sx, sz in SPAWN_SLOTS:
        d.rectangle([P(sx - 0.4, sz + 0.4), P(sx + 0.4, sz - 0.4)], fill=(30, 30, 30))
    for fid, s in sl_info.items():
        d.line([P(*SPAWN_EYE), P(*s["target_xz"])], fill=(30, 120, 220, 200) if s["visible"] else (220, 40, 40, 120), width=2)
    for a in L["anchor_index"]:
        if a["kind"] in ("feature", "warp", "arena", "fishing_spot", "discovery_chest", "npc_slot", "rest_shrine"):
            x, z = a["xz"]
            d.ellipse([P(x - 0.8, z + 0.8), P(x + 0.8, z - 0.8)], fill=(250, 220, 60), outline=(40, 40, 40))
            d.text(P(x + 1, z + 1), a["id"], fill=(20, 20, 20), font=font)
    d.text((10, 10), "PLAN - Sunmeadow v3-features: walk network, colliders, calm zones (green), step0 aggro (red, design+"
           "proposals), live aggro (purple), spawn slots, sightlines from spawn (blue = visible)", fill=(0, 0, 0), font=big)
    img.save(path)


if __name__ == "__main__":
    sys.exit(main())
