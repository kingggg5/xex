"""Render a top-down plan of a level layout JSON and validate clearances.

Usage: python tools/levels/render_layout_plan.py planning/levels/sunmeadow-v2-layout.json \
         --base planning/sunmeadow-compact-v1.json --out planning/evidence/sunmeadow-v2-layout
Writes plan.png (labelled PLAN) and checks.json. Read-only for the inputs.

--base accepts the Sunmeadow compact v1 candidate (props found by id prefix "sunmeadow_") or a minimal
"xexoria.level-base.v1" file ({"props": [{"id", "kind", "position_xz", "collider_radius_m", "collides"}], "pois": [...]}),
e.g. planning/levels/rimecrest-v1-base.json. Every generalised feature is opt-in through layout fields that the
Sunmeadow layout does not use (several streams/pools/bridges, polygon hazards and relief, relief "path_clearance_m",
"arena_keep_clear_basis", "plan_options"), so Sunmeadow's plan.png and checks.json are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PX = 6.0          # pixels per metre
MARGIN = 60


def seg_dist(p, a, b):
    ax, az = a; bx, bz = b; px, pz = p
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / L2))
    cx, cz = ax + t * dx, az + t * dz
    return math.hypot(px - cx, pz - cz)


def poly_dist(p, pts):
    return min(seg_dist(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def seg_intersect(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        t = o1 / (o1 - o2)
        return (c[0] + t * (d[0] - c[0]), c[1] + t * (d[1] - c[1]))
    return None


def poly_poly_min(p1, p2):
    best = min(poly_dist(p, p2) for p in p1)
    return min(best, min(poly_dist(p, p1) for p in p2))


def rect_dist(p, r):
    x0, x1, z0, z1 = r
    dx = max(x0 - p[0], 0, p[0] - x1)
    dz = max(z0 - p[1], 0, p[1] - z1)
    return math.hypot(dx, dz)


def densify(pts, step=0.5):
    out = []
    for i in range(len(pts) - 1):
        (ax, az), (bx, bz) = pts[i], pts[i + 1]
        n = max(1, int(math.hypot(bx - ax, bz - az) / step))
        out += [(ax + (bx - ax) * k / n, az + (bz - az) * k / n) for k in range(n)]
    out.append(tuple(pts[-1]))
    return out


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


def signed_poly_dist(p, poly):
    """Distance to a closed polygon's boundary; negative inside (so 'clear of' tests can fail)."""
    d = poly_dist(p, list(poly) + [poly[0]])
    return -d if point_in_poly(p, poly) else d


BASE_SCHEMA_PREFIX = "xexoria.level-base."


def load_level_base(path):
    """Minimal level base (xexoria.level-base.v1) -> (points, radii, kinds, colliding ids); None for other files."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not (isinstance(data, dict) and str(data.get("schema", "")).startswith(BASE_SCHEMA_PREFIX)):
        return None
    pts, radii, kinds, colliding = {}, {}, {}, set()
    for p in data["props"]:
        pts[p["id"]] = (float(p["position_xz"][0]), float(p["position_xz"][1]))
        radii[p["id"]] = float(p.get("collider_radius_m", 0.0))
        kinds[p["id"]] = p.get("kind", "prop")
        if p.get("collides", True):
            colliding.add(p["id"])
    return pts, radii, kinds, colliding


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layout")
    ap.add_argument("--base")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    lay = json.loads(Path(args.layout).read_text(encoding="utf-8"))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    x0, x1, z0, z1 = lay["bounds_xz"]["stage"]
    W = int((x1 - x0) * PX) + 2 * MARGIN
    H = int((z1 - z0) * PX) + 2 * MARGIN + 40

    def P(x, z):
        return (MARGIN + (x - x0) * PX, MARGIN + 40 + (z1 - z) * PX)

    img = Image.new("RGB", (W, H), (236, 232, 214))
    d = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 13); big = ImageFont.truetype("arialbd.ttf", 18)
    except OSError:
        font = big = ImageFont.load_default()

    # Grid: 8 m minor, 64 m art cells.
    for gx in range(int(x0), int(x1) + 1, 8):
        d.line([P(gx, z0), P(gx, z1)], fill=(0, 0, 0, 22 if gx % 64 else 90), width=1 if gx % 64 else 2)
    for gz in range(int(z0) - int(z0) % 8, int(z1) + 1, 8):
        d.line([P(x0, gz), P(x1, gz)], fill=(0, 0, 0, 22 if gz % 64 else 90), width=1 if gz % 64 else 2)

    opts = lay.get("plan_options", {})  # opt-in drawing and checks; Sunmeadow has none

    # Ground surfaces (opt-in key "surfaces", e.g. a walkable ice shelf).
    for s in lay.get("surfaces", []):
        if "polygon_xz" in s:
            d.polygon([P(*q) for q in s["polygon_xz"]], fill=tuple(s.get("plan_rgba", (215, 232, 240, 150))), outline=(120, 160, 190, 200))

    # Vegetation zones.
    vcol = {"broadleaf_grove": (88, 150, 60, 70), "pine_stand": (40, 100, 60, 80), "flower_meadow": (240, 200, 90, 55),
            "snow_pine_stand": (40, 96, 78, 85), "frost_shrubs": (110, 150, 140, 60), "frozen_reeds": (190, 180, 130, 60),
            "hot_spring_moss": (80, 175, 110, 70), "keep_clear": (235, 150, 40, 26)}
    for v in lay["vegetation_zones"]:
        if "polygon_xz" in v:
            d.polygon([P(*q) for q in v["polygon_xz"]], fill=vcol.get(v["kind"], (120, 160, 90, 50)), outline=(40, 80, 40, 160))
            cx = sum(q[0] for q in v["polygon_xz"]) / len(v["polygon_xz"]); cz = sum(q[1] for q in v["polygon_xz"]) / len(v["polygon_xz"])
            d.text(P(cx - 8, cz), v["id"], fill=(30, 60, 30), font=font)

    # Relief.
    line_col = {"cliff_wall": (110, 90, 75), "rolling_hills": (120, 150, 90), "forest_wall": (30, 80, 50),
                "ridge_cliff": (95, 100, 120), "pressure_ridge": (120, 175, 210), "basalt_rim": (70, 62, 66),
                "ice_wall": (110, 170, 205), "mountain_wall": (105, 105, 118), "ruin_wall": (150, 140, 125)}
    for r in lay["relief"]:
        if "footprint_xz" in r:
            fx0, fx1, fz0, fz1 = r["footprint_xz"]
            d.rectangle([P(fx0, fz1), P(fx1, fz0)], fill=(150, 120, 90, 200), outline=(80, 60, 40), width=2)
            d.text(P(fx0 + 1, fz1 - 4), f"{r['id']} {r['height_m']} m", fill=(40, 25, 10), font=font)
        if "polygon_xz" in r:
            fill = tuple(r.get("plan_rgba", (150, 120, 90, 200)))
            d.polygon([P(*q) for q in r["polygon_xz"]], fill=fill, outline=(80, 60, 40))
            cx = sum(q[0] for q in r["polygon_xz"]) / len(r["polygon_xz"]); cz = sum(q[1] for q in r["polygon_xz"]) / len(r["polygon_xz"])
            d.text(P(cx - 6, cz + 1), f"{r['id']} {r['height_m']} m", fill=(40, 25, 10), font=font)
        if "polyline_xz" in r:
            col = line_col.get(r["kind"], (110, 100, 95))
            if "plan_width_m" in r:
                lw = max(2, int(r["plan_width_m"] * PX))
            else:
                lw = int(5 * PX) if r["kind"] != "forest_wall" else int(3 * PX)
            d.line([P(*q) for q in r["polyline_xz"]], fill=col, width=lw)
            q = r["polyline_xz"][len(r["polyline_xz"]) // 2]
            d.text(P(q[0] + 2, q[1]), r["id"], fill=(20, 20, 20), font=font)

    # Hazards (no-go water etc.): rectangles (bounds_xz) or polygons (polygon_xz).
    for hz in lay.get("hazards", []):
        if "polygon_xz" in hz:
            d.polygon([P(*q) for q in hz["polygon_xz"]], fill=(60, 120, 190, 120), outline=(30, 70, 140))
            cx = sum(q[0] for q in hz["polygon_xz"]) / len(hz["polygon_xz"]); cz = sum(q[1] for q in hz["polygon_xz"]) / len(hz["polygon_xz"])
            d.text(P(cx - 8, cz), hz["id"], fill=(20, 50, 110), font=font)
            continue
        hx0, hx1, hz0, hz1 = hz["bounds_xz"]
        d.rectangle([P(hx0, min(hz1, z1)), P(hx1, hz0)], fill=(60, 120, 190, 120), outline=(30, 70, 140), width=2)
        d.text(P(hx0, min(hz1, z1) - 1), hz["id"], fill=(20, 50, 110), font=font)

    # Clearings (circle when a radius is given).
    for c in lay["clearings"]:
        if "radius_m" in c:
            cx, cz = c["center_xz"]; r = c["radius_m"]
            d.ellipse([P(cx - r, cz + r), P(cx + r, cz - r)], outline=(200, 40, 40), width=3)
            d.text(P(cx - r, cz + r + 2.5), c["id"], fill=(170, 20, 20), font=big)
            continue
        bx0, bx1, bz0, bz1 = c["bounds_xz"]
        d.rectangle([P(bx0, bz1), P(bx1, bz0)], outline=(200, 40, 40), width=3)
        d.text(P(bx0 + 1, bz1 - 2), c["id"], fill=(170, 20, 20), font=big)

    # Water.
    for w in lay["water"]:
        if w["kind"] == "stream":
            wmax = max(w["width_m"])
            d.line([P(*q) for q in w["points"]], fill=(70, 140, 200, 230), width=int(wmax * PX), joint="curve")
        elif w["kind"] == "pool":
            cx, cz = w["center_xz"]; r = w["radius_m"]
            d.ellipse([P(cx - r, cz + r), P(cx + r, cz - r)], fill=(70, 140, 200, 230) if not w.get("hot") else (64, 196, 190, 235))
        elif w["kind"] == "waterfall":
            tx, tz = w["top_xz"]
            if w.get("frozen"):
                d.polygon([P(tx, tz + 1.6), P(tx + 1.6, tz), P(tx, tz - 1.6), P(tx - 1.6, tz)], fill=(225, 245, 255), outline=(40, 120, 180))
                d.text(P(tx + 2, tz + 1), w["id"], fill=(20, 70, 130), font=font)
            else:
                d.ellipse([P(tx - 1, tz + 1), P(tx + 1, tz - 1)], fill=(255, 255, 255), outline=(40, 90, 160), width=2)
        elif w["kind"] == "lake" and "outline_xz" in w:
            d.line([P(*q) for q in list(w["outline_xz"]) + [w["outline_xz"][0]]], fill=(40, 90, 160), width=2)

    # Paths.
    pcol = {"gate_road": (205, 170, 120), "southbound_trail": (190, 150, 100), "east_return_path": (175, 145, 105), "camp_spur": (180, 160, 120)}
    for p in lay["paths"]:
        col = tuple(p["plan_rgb"]) if "plan_rgb" in p else pcol.get(p["id"], (180, 150, 110))
        d.line([P(*q) for q in p["points"]], fill=col, width=max(2, int(p["width_m"] * PX)), joint="curve")

    # Bridge.
    for b in lay.get("bridges", []):
        cx, cz = b["center_xz"]; ux, uz = b["along_xz"]; L = math.hypot(ux, uz); ux, uz = ux / L, uz / L
        hl, hw = b["length_m"] / 2, b["deck_width_m"] / 2 + 0.3
        corners = [(cx + ux * hl + -uz * hw, cz + uz * hl + ux * hw), (cx + ux * hl - -uz * hw, cz + uz * hl - ux * hw),
                   (cx - ux * hl - -uz * hw, cz - uz * hl - ux * hw), (cx - ux * hl + -uz * hw, cz - uz * hl + ux * hw)]
        d.polygon([P(*q) for q in corners], fill=(120, 80, 45), outline=(60, 35, 15))

    # Base props and spawns (compact v1, or a minimal xexoria.level-base.v1 file).
    base_pts = {}
    base_r = {}  # collider radius per prop; empty for compact v1 (its checks use prop centres)
    if args.base:
        lb = load_level_base(args.base)
        if lb is None:
            raw = Path(args.base).read_text(encoding="utf-8")
            for m in re.finditer(r'"id"\s*:\s*"(sunmeadow_[^"]+)"[^{}]{0,200}?"(?:after_xz|position_xz|center_xz)"\s*:\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)', raw):
                base_pts[m.group(1)] = (float(m.group(2)), float(m.group(3)))
            # A layout landmark noted "existing prop <id>, moved from ..." moves that prop; the layout wins,
            # exactly as in the blockout builder (assets/blender/sunmeadow_v2/sm2_site.py).
            for l in lay["landmarks"]:
                mm = re.search(r"existing prop (\w+)", l.get("note", ""))
                if mm and mm.group(1) in base_pts and isinstance(l.get("position_xz"), list):
                    base_pts[mm.group(1)] = (float(l["position_xz"][0]), float(l["position_xz"][1]))
            for pid, (px, pz) in base_pts.items():
                col = (30, 90, 40) if ("pine" in pid or "oak" in pid) else (90, 120, 60) if "bush" in pid else (90, 90, 90)
                rr = 1.6 if ("pine" in pid or "oak" in pid) else 1.0
                d.ellipse([P(px - rr, pz + rr), P(px + rr, pz - rr)], fill=col)
        else:
            all_pts, radii, kinds, colliding = lb
            kcol = {"tree": (30, 90, 50), "rock": (110, 110, 120), "ice": (120, 180, 215), "ruin": (150, 135, 110),
                    "camp": (150, 95, 55), "stone": (125, 120, 105), "sign": (90, 60, 30), "gate": (90, 60, 30), "vent": (210, 150, 60)}
            for pid, (px, pz) in all_pts.items():
                rr = max(0.4, radii[pid])
                col = kcol.get(kinds[pid], (90, 90, 90))
                if pid in colliding:
                    d.ellipse([P(px - rr, pz + rr), P(px + rr, pz - rr)], fill=col + (235,), outline=(20, 20, 20, 160))
                else:
                    d.ellipse([P(px - rr, pz + rr), P(px + rr, pz - rr)], outline=col + (255,), width=2)
            base_pts = {pid: q for pid, q in all_pts.items() if pid in colliding}
            base_r = {pid: radii[pid] for pid in base_pts}

    # Landmarks.
    for l in lay["landmarks"]:
        pos = l.get("position_xz") or l.get("center_xz")
        if isinstance(pos, list):
            px, pz = pos
            if l["kind"] == "stone_circle_altar":
                r = l["radius_m"]
                d.ellipse([P(px - r, pz + r), P(px + r, pz - r)], outline=(110, 60, 160), width=3)
            if opts.get("draw_arenas") and l.get("boss_arena_radius_m"):
                ra, rk = l["boss_arena_radius_m"], l.get("arena_keep_clear_m", l["boss_arena_radius_m"])
                d.ellipse([P(px - ra, pz + ra), P(px + ra, pz - ra)], fill=(200, 30, 50, 28), outline=(200, 30, 50), width=3)
                d.ellipse([P(px - rk, pz + rk), P(px + rk, pz - rk)], outline=(200, 30, 50, 140), width=1)
            d.rectangle([P(px - 1.2, pz + 1.2), P(px + 1.2, pz - 1.2)], fill=(110, 60, 160))
            d.text(P(px + 1.8, pz + 1.0), l["id"], fill=(80, 30, 120), font=font)
        elif "bounds_xz" in l:
            bx0, bx1, bz0, bz1 = l["bounds_xz"]
            d.rectangle([P(bx0, bz1), P(bx1, bz0)], outline=(110, 60, 160), width=2)
            d.text(P(bx0, bz1 + 3.5), l["id"], fill=(80, 30, 120), font=font)
        wp = l.get("warp")
        if opts.get("draw_warps") and isinstance(wp, dict):
            wc = wp.get("center_xz") or pos
            if isinstance(wc, list):
                rr = wp.get("trigger_radius_m", 2.0)
                d.ellipse([P(wc[0] - rr, wc[1] + rr), P(wc[0] + rr, wc[1] - rr)], outline=(20, 160, 175), width=3)
                d.text(P(wc[0] + rr + 0.6, wc[1] - rr), wp["id"], fill=(10, 110, 120), font=font)

    for name, (ax, az) in lay["anchors"].items():
        d.ellipse([P(ax - 1, az + 1), P(ax + 1, az - 1)], fill=(0, 0, 0)); d.text(P(ax + 1.5, az + 1.5), name, fill=(0, 0, 0), font=font)

    if opts.get("draw_sightlines"):
        for s in lay.get("sightlines", []):
            if "from_xz" in s and "to_xz" in s:
                pts = densify([tuple(s["from_xz"]), tuple(s["to_xz"])], 1.5)
                for k in range(0, len(pts) - 1, 2):
                    d.line([P(*pts[k]), P(*pts[k + 1])], fill=(230, 120, 20, 200), width=2)

    d.text((MARGIN, 10), f"PLAN — {lay['region']} {lay['version']}  (1 grid = 8 m, bold = 64 m art cells, north up)", fill=(0, 0, 0), font=big)
    plan = out / "plan.png"; img.save(plan)

    # ---- Validation ----
    checks = []
    def add(name, value, limit, ok):
        checks.append({"check": name, "value_m": round(value, 2), "limit_m": limit, "pass": bool(ok)})

    paths = {p["id"]: p for p in lay["paths"]}
    streams = [w for w in lay["water"] if w["kind"] == "stream"]
    pools = [w for w in lay["water"] if w["kind"] == "pool"]
    bridges = lay.get("bridges", [])
    multi_stream = len(streams) > 1
    footprints = [r for r in lay["relief"] if "footprint_xz" in r]
    relief_polys = [r for r in lay["relief"] if "polygon_xz" in r]
    relief_lines = [r for r in lay["relief"] if "polyline_xz" in r and "path_clearance_m" in r]
    for pid, p in paths.items():
        dense = densify(p["points"])
        for stream in streams:
            sw = max(stream["width_m"]) / 2
            stag = f" [{stream['id']}]" if multi_stream else ""
            crossings = []
            for i in range(len(p["points"]) - 1):
                for j in range(len(stream["points"]) - 1):
                    x = seg_intersect(p["points"][i], p["points"][i + 1], stream["points"][j], stream["points"][j + 1])
                    if x: crossings.append(x)
            for x in crossings:
                dist = min((math.hypot(x[0] - b["center_xz"][0], x[1] - b["center_xz"][1]) for b in bridges), default=9999.0)
                add(f"{pid} crosses stream{stag} at ({x[0]:.1f},{x[1]:.1f}); distance to bridge centre", dist, 1.0, dist <= 1.0)
            if not crossings:
                gap = poly_poly_min(dense, densify(stream["points"])) - sw - p["width_m"] / 2
                add(f"{pid} edge to stream edge{stag} (no crossing)", gap, ">= 1.5", gap >= 1.5)
        for pool in pools:
            gp = poly_dist(tuple(pool["center_xz"]), p["points"]) - pool["radius_m"] - p["width_m"] / 2
            add(f"{pid} edge to {pool['id']} edge", gp, ">= 1.5", gp >= 1.5)
        for r in footprints:
            gb = min(rect_dist(q, r["footprint_xz"]) for q in dense) - p["width_m"] / 2
            add(f"{pid} edge to {r['id']} footprint", gb, ">= 1.0", gb >= 1.0)
        for r in relief_polys:
            gb = min(signed_poly_dist(q, r["polygon_xz"]) for q in dense) - p["width_m"] / 2
            lim = r.get("path_clearance_m", 1.0)
            add(f"{pid} edge to {r['id']} footprint", gb, f">= {lim}", gb >= lim)
        for r in relief_lines:
            gb = min(poly_dist(q, r["polyline_xz"]) for q in dense) - p["width_m"] / 2 - r.get("toe_half_width_m", 0.0)
            lim = r["path_clearance_m"]
            add(f"{pid} edge to {r['id']} toe line", gb, f">= {lim}", gb >= lim)
    # Opt-in: main routes keep a minimum width; every path stays inside the walkable hint.
    if "min_main_path_width_m" in opts:
        for pid, p in paths.items():
            if p.get("class") == "main":
                add(f"{pid} width (main route)", p["width_m"], f">= {opts['min_main_path_width_m']}", p["width_m"] >= opts["min_main_path_width_m"])
    if opts.get("check_paths_in_walkable"):
        wx0, wx1, wz0, wz1 = lay["bounds_xz"]["walkable_hint"]
        for pid, p in paths.items():
            m = min(min(q[0] - wx0, wx1 - q[0], q[1] - wz0, wz1 - q[1]) for q in densify(p["points"])) - p["width_m"] / 2
            add(f"{pid} edge inside walkable_hint", m, ">= 0", m >= 0)
    # Paths and landmarks must stay out of hazards (e.g. the city canal).
    for hz in lay.get("hazards", []):
        if "polygon_xz" in hz:
            def hdist(q, hz=hz):
                return signed_poly_dist(q, hz["polygon_xz"])
        else:
            def hdist(q, hz=hz):
                return rect_dist(q, hz["bounds_xz"])
        for pid, p in paths.items():
            gap = min(hdist(q) for q in densify(p["points"])) - p["width_m"] / 2
            add(f"{pid} edge to hazard {hz['id']}", gap, ">= 0.5", gap >= 0.5)
        for l in lay["landmarks"]:
            pos = l.get("position_xz") or l.get("center_xz")
            if isinstance(pos, list):
                g = hdist(tuple(pos))
                add(f"landmark {l['id']} to hazard {hz['id']}", g, ">= 1.0", g >= 1.0)
    # Altar must sit beside, never on, the trail.
    for l in lay["landmarks"]:
        if l.get("kind") == "altar":
            tp = paths.get(l.get("beside_path", "southbound_trail"))
            if tp is None:
                continue
            ga = poly_dist(tuple(l["position_xz"]), tp["points"]) - l["radius_m"] - tp["width_m"] / 2
            add(f"{l['id']} edge to {tp['id']} edge", ga, ">= 1.5", ga >= 1.5)
    # Bridge must span the stream: deck length > stream width + 2 m.
    for b in bridges:
        spanned = next((s for s in streams if s["id"] == b.get("spans")), streams[0] if streams else None)
        if spanned is None:
            continue
        sw = max(spanned["width_m"]) / 2
        btag = f" [{b['id']}]" if len(bridges) > 1 else ""
        add(f"bridge length minus stream width{btag}", b["length_m"] - 2 * sw, ">= 2.0", b["length_m"] - 2 * sw >= 2.0)
    # Props and spawn anchors must not stand in water or on path centre lines.
    prop_margin = lay.get("prop_path_margin_m", 1.0)
    for pid, q in base_pts.items():
        pr = base_r.get(pid, 0.0)
        if streams:
            dw = min(poly_dist(q, s["points"]) - max(s["width_m"]) / 2 for s in streams) - pr
            add(f"{pid} distance to stream edge", dw, ">= 0.3", dw >= 0.3)
        if base_r:  # level-base props carry collider radii: also keep them out of pools and water hazards
            dws = [math.dist(q, w["center_xz"]) - w["radius_m"] - pr for w in pools]
            dws += [(signed_poly_dist(q, h["polygon_xz"]) if "polygon_xz" in h else rect_dist(q, h["bounds_xz"])) - pr
                    for h in lay.get("hazards", []) if h.get("kind") == "water"]
            if dws:
                add(f"{pid} collider edge to pool/water-hazard edge", min(dws), ">= 0.3", min(dws) >= 0.3)
        for pth in paths.values():
            dp = poly_dist(q, pth["points"]) - pth["width_m"] / 2 - pr
            if dp < prop_margin:
                add(f"{pid} intrudes on {pth['id']}", dp, f">= {prop_margin}", False)
    # Boss arenas: no colliding prop inside arena_keep_clear_m, except the ring's own gate stones.
    for l in lay["landmarks"]:
        keep = l.get("arena_keep_clear_m")
        if keep:
            cx, cz = l["center_xz"]
            exempt = set(l.get("arena_keep_clear_exempt", []))
            edge_basis = l.get("arena_keep_clear_basis") == "collider_edge"
            for pid, q in base_pts.items():
                if pid in exempt or (pid.startswith("sunmeadow_stone_post_") and pid.endswith("_north")):
                    continue
                dc = math.hypot(q[0] - cx, q[1] - cz)
                if edge_basis:
                    de = dc - base_r.get(pid, 0.0)
                    if de < keep + 3.0:
                        add(f"{pid} collider edge to {l['id']} arena centre", de, f">= {keep}", de >= keep)
                elif dc < keep + 3.0:
                    add(f"{pid} distance to {l['id']} arena centre", dc, f">= {keep}", dc >= keep)
            if edge_basis:
                # Water and other no-go ground stays outside the keep-clear too (the fight never spills into it).
                for w in pools:
                    de = math.hypot(w["center_xz"][0] - cx, w["center_xz"][1] - cz) - w["radius_m"]
                    add(f"pool {w['id']} edge to {l['id']} arena centre", de, f">= {keep}", de >= keep)
                for h in lay.get("hazards", []):
                    de = signed_poly_dist((cx, cz), h["polygon_xz"]) if "polygon_xz" in h else rect_dist((cx, cz), h["bounds_xz"])
                    add(f"hazard {h['id']} edge to {l['id']} arena centre", de, f">= {keep}", de >= keep)
                for s in streams:
                    de = poly_dist((cx, cz), s["points"]) - max(s["width_m"]) / 2
                    add(f"stream {s['id']} edge to {l['id']} arena centre", de, f">= {keep}", de >= keep)
    # Opt-in: warp triggers never inside a boss arena (warp_network rule), except warps flagged interact_in_arena.
    if opts.get("check_warps_vs_arenas"):
        arenas = [l for l in lay["landmarks"] if l.get("boss_arena_radius_m")]
        for l in lay["landmarks"]:
            wp = l.get("warp")
            if not isinstance(wp, dict):
                continue
            wc = wp.get("center_xz") or l.get("position_xz") or l.get("center_xz")
            for a in arenas:
                de = math.dist(wc, a["center_xz"]) - wp.get("trigger_radius_m", 0.0)
                add(f"warp {wp['id']} trigger edge to {a['id']} arena centre", de, f">= {a['boss_arena_radius_m']}", de >= a["boss_arena_radius_m"])
    report = {"layout": args.layout, "plan_png": str(plan), "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
              "checks": checks, "failed": [c for c in checks if not c["pass"]]}
    (out / "checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"plan: {plan}")
    print(f"checks: {len(checks)}, failed: {len(report['failed'])}")
    for c in report["failed"]:
        print("  FAIL", c["check"], c["value_m"], c["limit_m"])


if __name__ == "__main__":
    main()
