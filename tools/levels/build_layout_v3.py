"""Authoring script: Sunmeadow v2 layout -> v3-features + sunmeadow-v3-feature-assets.json (lane C-MAP-V3, 2026-10-03).

Reads the archived v2 layout (planning/evidence/sunmeadow-v3-features/before/...) and writes
planning/levels/sunmeadow-v2-layout.json with version "v3-features". Every v2 id is kept.
Do NOT re-run over a hand-edited layout: it always starts from the archived v2 file.
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "planning/evidence/sunmeadow-v3-features/before/sunmeadow-v2-layout.v2-claude-20261002.json"
DST = ROOT / "planning/levels/sunmeadow-v2-layout.json"
ASSETS = ROOT / "planning/levels/sunmeadow-v3-feature-assets.json"
MON_SRC = ROOT / "planning/evidence/sunmeadow-v3-features/before/sunmeadow-v2-monsters.r3.json"
MON_DST = ROOT / "planning/levels/sunmeadow-v2-monsters.json"
ZONES = ROOT / "content/source/zones.json"

# Design-home proposals (C4: aggro discs >= 3 m clear of the 48 spawn slots). Fields only; home_xz is unchanged.
PROPOSALS = {
    4: ([-14.5, -3.5], "C4: step0 aggro 3 m disc came 1.24 m from spawn slot (-3,-3); proposal 8.6 m clear; "
                       "windmark_1 5.15 m (H6 >= 5), row 3 2.7 m (H13 >= 2.5), inside hunt_meadow_west"),
    29: ([-14.5, -8.3], "C4: rain puddlekin disc overlapped spawn slot (-3,-7.5) (-1.09 m); proposal 8.5 m clear; "
                        "windmark_1 5.05 m; mere_spur 6.4 m"),
    9: ([13.0, -0.6], "C4: night (step1) aggro 7 m disc came 1.22 m from spawn slot (3,-3); proposal 3.28 m clear; "
                      "windmark_2 5.6 m; rows 5/30 2.9/2.8 m; croft calm margin 19.8 m"),
}


def r3(v):
    return round(float(v), 3)


def P(pts):
    return [[r3(x), r3(z)] for x, z in pts]


def ellipse_arc(c, rx, rz, a0_deg, a1_deg, n):
    out = []
    for k in range(n + 1):
        a = math.radians(a0_deg + (a1_deg - a0_deg) * k / n)
        out.append((c[0] + rx * math.cos(a), c[1] + rz * math.sin(a)))
    return out


def rect(x0, x1, z0, z1):
    return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]


def main():
    L = json.loads(SRC.read_text(encoding="utf-8"))
    v2 = copy.deepcopy(L)
    L["version"] = "v3-features"
    L["status"] = ("DESIGN — Claude level design (map lane). v3-features adds the owner's 2026-10-02 21:05 feature request "
                   "(Waterfall Grotto, Lotus Mere, Brightwater Cove, Sunmeadow Croft, procedural dressing rules, ambient "
                   "wildlife zones, night light anchors) on top of v2. Source of truth for the Blender blockout and for "
                   "tools/levels/generate_dressing.py. Not live content.")
    L["previous_version"] = {"version": v2["version"],
                             "archived_copy": "planning/evidence/sunmeadow-v3-features/before/sunmeadow-v2-layout.v2-claude-20261002.json",
                             "sha256": "d69582c4a39e2bce9f34950eef16b0538c88df08d75b6dd7b764496309728372"}

    # ------------------------------------------------------------------ support model (server facts)
    L["support_model"] = {
        "source": "content/source/zones.json zone 1 city_traversal (read-only) + apps/server/src/grounded_city.rs height_at()",
        "city_bounds_xz": [-124, 124, 8, 304],
        "rule": "outside city_bounds the server support is flat Y=0; inside (z >= 8) only authored city surfaces support a capsule "
                "(missing support inside the city is a gap). In the stage that leaves the exit ramps (x +-6.85..13.35, z 8..24) "
                "and the city grass apron (z >= ~16) supported, and a SUPPORT GAP BAND z 8..~16 outside the ramps.",
        "gap_band_xz": [[-46.5, -13.35, 8.0, 16.0], [13.35, 46.5, 8.0, 16.0]],
        "design_rule": "every walkable v3 feature part keeps the capsule centre at z < 8.0; buildings, ruins, water and dense "
                       "vegetation may sit in the gap band so the boundary is a visible blocker, never an invisible wall",
        "found": "2026-10-02 v3 pass: the v2 clearings drawn north of z 8 (windmark_hunt to z 21, the groves to z 20-22, the "
                 "lookout POI (-16,18) on the city apron, windmark_3 (-4,14) in the gap) are not supported off the ramps; "
                 "flagged to root in planning/evidence/sunmeadow-v3-features/codex-requests.md (R-SUP-1)",
    }
    L["invariants"]["support"] = "see support_model: z >= 8 is city-owned support"

    # ------------------------------------------------------------------ path classes + new paths
    classes = {"gate_road": "main", "southbound_trail": "main", "gate_road_east": "branch", "boar_trail": "spur",
               "east_return_path": "spur", "camp_spur": "spur"}
    for p in L["paths"]:
        p["class"] = classes[p["id"]]
    trail = next(p for p in L["paths"] if p["id"] == "southbound_trail")
    trail["width_m"] = 4.0
    trail["note"] = trail["note"] + "; widened 3.8 -> 4.0 m in v3 (main routes >= 4 m, brief 2026-10-02)"
    east = next(p for p in L["paths"] if p["id"] == "gate_road_east")
    east["width_m"] = 4.0
    east["class"] = "main"
    east["note"] = east["note"] + "; widened 3.6 -> 4.0 m in v3 (main routes >= 4 m)"

    L["paths"] += [
        {"id": "mere_spur", "class": "spur", "width_m": 2.5, "surface": "grass-worn footpath with stepping flags near the mere",
         "note": "v3: west spur from the Sella crossroads on gate_road to the Lotus Mere boardwalk landing; runs between the "
                 "hunt_meadow_west leash (z >= -10.5) and the falls_meadow leash (z <= -26)",
         "points": P([(1.357, -14.5), (-8.0, -15.4), (-18.0, -14.4), (-26.5, -11.0), (-31.8, -6.6), (-34.9, -1.6),
                      (-36.2, 4.55)])},
        {"id": "cove_path", "class": "spur", "width_m": 3.0, "surface": "sandy dirt path with pebble edges",
         "note": "v3: from the southbound trail just south of the bridge, west along the stream's south bank (pine-stand "
                 "edge), down to the Brightwater Cove beach",
         "points": P([(-10.0, -54.0), (-18.5, -58.7), (-30.0, -60.3), (-38.0, -62.1), (-42.4, -65.6), (-43.4, -69.4)])},
        {"id": "croft_lane", "class": "spur", "width_m": 2.5, "surface": "trampled grass lane",
         "note": "v3: hunter camp north edge -> Sunmeadow Croft yard (the camp spur carries it on to the gate road)",
         "points": P([(26.5, -3.2), (29.6, -0.4), (32.4, 2.4), (34.6, 1.8)])},
        {"id": "croft_south_lane", "class": "spur", "width_m": 2.5, "surface": "sheep-trodden lane",
         "note": "v3: croft yard (west of the pen) -> past the pen gate -> east return path; closes the croft loop back "
                 "toward the trail start (M2: re-routed west of the pen so it starts in the yard, pen wall clear 0.5 m)",
         "points": P([(33.0, 0.8), (31.6, -6.0), (31.8, -14.0), (34.4, -18.6), (30.0, -24.4), (24.4, -28.85)])},
    ]

    # ------------------------------------------------------------------ bridge: deck follows the 4.0 m trail
    br = L["bridges"][0]
    br["deck_width_m"] = 4.2
    br["note"] = "v3: deck widened 3.8 -> 4.2 m to carry the 4.0 m trail; rails stay outside the trail edge"

    # ------------------------------------------------------------------ water: A1 / A2 (water spec 2026-10-02 section 3)
    falls = next(w for w in L["water"] if w["id"] == "bluff_falls")
    falls.update({"target": "falls_pool", "exit_velocity_m_s": 1.5, "landing_xz": [-9.3, -38.0],
                  "lip_xz": [-7.0, -38.0],
                  "note_v3": "lip on the bluff overhang at x -7; the sheet lands ~2.3 m inside the A1 pool rim; the grotto "
                             "falls ledge (x -7..-4) passes behind the curtain"})
    pool = next(w for w in L["water"] if w["id"] == "falls_pool")
    pool.update({"center_xz": [-9.6, -38.0], "radius_m": 2.6,
                 "amendment": "A1 (water spec section 3): v2 (-10.5,-38) r 2.5 -> (-9.6,-38) r 2.6 so the east rim meets "
                              "the bluff toe at x -7.0 (no dry sliver behind the falls); trail clearance 2.8 -> 3.42 m",
                 "outlet_xz": [-10.19, -40.53], "inflow": "bluff_falls", "outflow": "sunmeadow_stream"})
    st = next(w for w in L["water"] if w["id"] == "sunmeadow_stream")
    st["points"] = st["points"] + [[-68.5, -63.5], [-70.5, -69.0]]
    st["amendment"] = ("A2 (water spec section 3): polyline extended through the west cliff gap with P8 (-68.5,-63.5) and "
                       "P9 (-70.5,-69.0); two exit cascades; the water ends under the stream_end_spur_rock boulder mass at P9")
    st["flow_direction"] = "points[0] -> points[-1] (pool outlet -> bridge -> west cliff gap -> cascades -> P9)"
    st["centreline_keys"] = [
        {"key": "O_outlet", "xz": [-10.19, -40.53], "s_m": 0.0, "width_m": 3.0, "depth_m": 0.40, "speed_m_s": 0.80},
        {"key": "P1", "xz": [-11.0, -44.0], "s_m": 3.56, "width_m": 3.2, "depth_m": 0.65, "speed_m_s": 0.55},
        {"key": "P2_bridge", "xz": [-14.0, -49.5], "s_m": 9.83, "width_m": 3.6, "depth_m": 0.65, "speed_m_s": 0.60},
        {"key": "P3", "xz": [-20.0, -52.5], "s_m": 16.53, "width_m": 3.8, "depth_m": 0.65, "speed_m_s": 0.55},
        {"key": "P4", "xz": [-30.0, -54.0], "s_m": 26.65, "width_m": 4.3, "depth_m": 0.65, "speed_m_s": 0.45},
        {"key": "P5", "xz": [-42.0, -54.0], "s_m": 38.65, "width_m": 4.5, "depth_m": 0.65, "speed_m_s": 0.45},
        {"key": "P6", "xz": [-52.0, -57.0], "s_m": 49.09, "width_m": 4.2, "depth_m": 0.65, "speed_m_s": 0.55},
        {"key": "gap", "xz": [-56.0, -58.0], "s_m": 53.2, "width_m": 3.8, "depth_m": 0.50, "speed_m_s": 0.70},
        {"key": "cascade_1", "xz": [-60.6, -59.2], "s_m": 58.0, "width_m": 3.4, "depth_m": 0.55, "speed_m_s": 1.10},
        {"key": "P8_cascade_2", "xz": [-68.5, -63.5], "s_m": 67.16, "width_m": 3.0, "depth_m": 0.55, "speed_m_s": 1.10},
        {"key": "P9_end", "xz": [-70.5, -69.0], "s_m": 73.01, "width_m": 2.6, "depth_m": 0.40, "speed_m_s": 0.55},
    ]
    st["width_rule"] = ("smoothstep between keys + 0.12 sin(2 pi s/9.3+0.7) + 0.08 sin(2 pi s/5.1+2.1); variation 0 within "
                        "3 m of the bridge (s 6.8-12.8), for s 16-24 and within 2 m of each cascade lip")
    st["surface_y_by_s"] = [[0.0, -0.35], [58.0, -0.35], [58.0, -0.85], [67.16, -0.85], [67.16, -1.45], [73.01, -1.45]]
    st["cascades"] = [
        {"id": "stream_cascade_1", "lip_xz": [-60.6, -59.2], "s_m": 58.0, "from_y": -0.35, "to_y": -0.85, "width_m": 3.4,
         "note": "first exit step just past the cliff gap; visible from the walkable west edge through the gap"},
        {"id": "stream_cascade_2", "lip_xz": [-68.5, -63.5], "s_m": 67.16, "from_y": -0.85, "to_y": -1.45, "width_m": 3.0,
         "note": "second step; water then ends at P9 under stream_end_spur_rock (no visible water end, spec section 10)"},
    ]
    st["end"] = {"xz": [-70.5, -69.0], "hidden_by": "stream_end_spur_rock", "rule": "zero visible water-end vertices"}
    st["note_v3"] = ("v3: the stream keeps its own channel to the end; Brightwater Cove lies just south of the stream mouth, "
                     "separated from the cascades by the estuary headland (reeds, rocks) so the two water levels never touch")
    L["water"].append({"id": "grotto_moon_pool", "kind": "pool", "center_xz": [7.4, -41.7], "radius_m": 1.3,
                       "surface_y": -0.12, "bed_y": -0.45, "still": True,
                       "note": "v3: decorative still pool in the Waterfall Grotto chamber (mirror water, no flow, no glow)"})

    # ------------------------------------------------------------------ feature geometry
    # Grotto: bluff solid region = footprint minus (ledge notch, tunnel, chamber)
    ch_c, ch_rx, ch_rz = (6.25, -39.0), 6.0, 5.0
    a_join = math.degrees(math.atan2((-36.75 - ch_c[1]) / ch_rz, (0.892 - ch_c[0]) / ch_rx))  # ~153.2 deg
    arc = ellipse_arc(ch_c, ch_rx, ch_rz, a_join, -a_join, 30)  # north -> east -> south, clockwise
    bluff_solid = ([(-4.0, -46.0), (17.0, -46.0), (17.0, -30.0), (-7.0, -30.0), (-7.0, -35.5), (-4.0, -35.5),
                    (-4.0, -36.75)] + arc + [(-4.0, -41.25)])
    chamber = ellipse_arc(ch_c, ch_rx, ch_rz, 0, 360, 36)[:-1]

    # Mere geometry
    mere_north = [(-52.75, 7.6), (-52.2, 10.6), (-49.0, 11.3), (-45.0, 11.0), (-41.6, 9.8), (-39.6, 7.9), (-38.9, 5.8),
                  (-43.6, 5.8), (-43.6, 6.0), (-46.6, 6.0), (-46.6, 7.6)]
    mere_south = [(-38.9, 3.3), (-38.6, 1.5), (-39.1, -1.2), (-40.6, -3.0), (-43.4, -4.1), (-46.6, -4.4), (-49.8, -3.7),
                  (-52.3, -2.1), (-53.95, -0.3), (-53.73, 1.6), (-49.5, 1.5), (-47.3, 2.0), (-46.6, 3.0), (-43.6, 3.0),
                  (-43.6, 3.3)]
    mere_outline = [(-53.95, -0.3), (-53.73, 1.6), (-53.33, 4.0), (-52.75, 7.6), (-52.2, 10.6), (-49.0, 11.3),
                    (-45.0, 11.0), (-41.6, 9.8), (-39.6, 7.9), (-38.9, 5.8), (-38.9, 3.3), (-38.6, 1.5), (-39.1, -1.2),
                    (-40.6, -3.0), (-43.4, -4.1), (-46.6, -4.4), (-49.8, -3.7), (-52.3, -2.1)]
    terrace = [(-53.73, 1.6), (-49.5, 1.5), (-47.3, 2.0), (-46.6, 3.0), (-46.6, 7.6), (-52.75, 7.6), (-53.33, 4.0)]

    # Cove geometry (lake with the pier notch; beach band)
    pier_n, pier_s = -73.0, -75.5          # walkway deck edges (2.5 m)
    plat = (-62.0, -58.0, -76.25, -72.25)  # end platform 4 x 4
    # v3 M1 (05:50): the lake's north shore stops at z ~-67 so the A2 stream tail (cascades at z -59.2 / -63.5, end at
    # P9 -69 under the spur rock, x <= -60) keeps its own channel; the estuary headland (z -59..-67) separates them.
    cove_lake = [(-64.0, -69.6), (-60.5, -68.1), (-56.0, -67.2), (-51.5, -67.0), (-47.6, -68.0), (-48.5, -71.0), (-48.8, pier_n), (-58.0, pier_n), (-58.0, plat[3]),
                 (plat[0], plat[3]), (plat[0], plat[2]), (-58.0, plat[2]), (-58.0, pier_s), (-49.0, pier_s),
                 (-49.1, -78.0), (-48.7, -81.5), (-47.9, -84.6), (-48.6, -88.0), (-51.0, -91.0), (-55.0, -92.6),
                 (-64.0, -93.2)]
    cove_beach = [(-45.6, -66.6), (-47.6, -68.0), (-48.5, -71.0), (-48.8, pier_n), (-49.0, pier_s), (-49.1, -78.0),
                  (-48.7, -81.5), (-47.9, -84.6), (-48.6, -88.0), (-46.2, -89.6), (-41.0, -89.4), (-38.0, -86.2),
                  (-37.2, -80.0), (-37.4, -74.0), (-38.4, -69.6), (-41.2, -67.2)]

    # Croft geometry
    pen = (34.0, 43.0, -14.2, -2.2)        # stone-wall pen 9 x 12 (gate on the south wall)

    F = []
    # ========================= 1. Waterfall Grotto
    F.append({
        "id": "waterfall_grotto",
        "name": {"en": "Waterfall Grotto", "th": "ถ้ำหลังม่านน้ำตก"},
        "purpose": "discovery: a hidden roofless chamber behind the falls; grotto_chest + Sunwell crystal lore; quiet rest",
        "landmark": "the cave mouth behind the waterfall curtain, then the blue crystal cluster under the light shaft",
        "route": {"in": "southbound_trail (south of the bridge) -> grotto approach walkway -> falls ledge behind the "
                        "curtain -> tunnel -> chamber", "out": "same way back (dead-end discovery, 25 m from the trail)"},
        "calm": {"radius_m": 10, "core": "carve (notch + tunnel + chamber) and the approach's last 3 m"},
        "carve": {
            "ledge_notch_polygon_xz": P(rect(-7.0, -4.0, -46.0, -35.5)),
            "rock_lip_polygon_xz": P(rect(-7.4, -6.6, -46.0, -35.5)),
            "rock_lip_height_m": 0.8,
            "ledge_clear_width_m": 2.6,
            "overhang": "the bluff face above y 5.0 stays at x -7 (overhang lip over the ledge); bluff_falls pours from it at "
                        "(-7,-38), y 7.5, and drops in front of the ledge into falls_pool: the ledge passes behind the curtain",
            "mouth": {"center_xz": [-4.0, -39.0], "width_m": 4.5, "height_m": 5.0, "facing": "west",
                      "yaw_rad": 4.712},
            "tunnel_polygon_xz": P(rect(-4.0, 0.892, -41.25, -36.75)),
            "tunnel_roof_y_m": 5.0,
            "tunnel_length_m": 4.892,
            "chamber": {"center_xz": [6.25, -39.0], "semi_axes_m": [6.0, 5.0], "open_to_sky": True,
                        "polygon_xz": P(chamber), "mean_radius_m": 5.5,
                        "rim": "lower bluff tier around the chamber; mossy ledges at 3.5 and 6 m stepping to the 10 m top"},
        },
        "colliders": [
            {"id": "inner_bluff_solid_v3", "shape": "polygon", "polygon_xz": P(bluff_solid), "y": [0, 10],
             "replaces": "inner_bluff footprint box (sunmeadow_compact_inner_bluff 24x16x10) in the server collider set",
             "note": "the bluff collider with the falls ledge, tunnel and chamber carved out (one simple polygon)"},
            {"id": "grotto_rock_lip", "shape": "polygon", "polygon_xz": P(rect(-7.4, -6.6, -46.0, -35.5)), "y": [0, 0.8]},
            {"id": "grotto_crystal_cluster", "shape": "circle", "center_xz": [10.2, -36.1], "radius_m": 0.9, "y": [0, 2.6]},
            {"id": "grotto_chest", "shape": "box", "center_xz": [11.3, -39.4], "size_m": [0.7, 1.1], "yaw_rad": 4.712,
             "y": [0, 0.8]},
        ],
        "water_hazards": ["grotto_moon_pool (water entry, r 1.3)", "falls_pool and sunmeadow_stream (v2) beyond the lip"],
        "walkways": [
            {"id": "grotto_approach", "width_m": 2.5, "surface": "wet stone and moss", "points": P([(-7.5, -55.75),
                                                                                                   (-5.3, -46.6)])},
            {"id": "grotto_falls_ledge", "width_m": 2.5, "clear_width_m": 2.6, "surface": "wet flagstone ledge",
             "points": P([(-5.3, -46.6), (-5.3, -40.4), (-4.2, -39.0)])},
            {"id": "grotto_tunnel", "width_m": 4.5, "roofed": True, "points": P([(-4.2, -39.0), (0.892, -39.0)])},
            {"id": "grotto_chamber_floor", "width_m": 4.0, "points": P([(0.892, -39.0), (6.25, -39.0), (9.6, -39.3)])},
        ],
        "pois": [
            {"id": "grotto_entrance", "kind": "discovery_marker", "position_xz": [-5.3, -44.0]},
            {"id": "grotto_chest", "kind": "discovery_chest", "position_xz": [11.3, -39.4], "interact_radius_m": 1.8,
             "stand_xz": [9.6, -39.3]},
            {"id": "grotto_sunwell_crystal", "kind": "lore_object", "position_xz": [10.2, -36.1], "stand_xz": [8.8, -37.4]},
        ],
        "hero_dressing": [
            {"id": "grotto_light_shaft", "kind": "light_shaft_card", "position_xz": [6.0, -38.8], "radius_m": 2.2,
             "note": "god-ray card from the open roof onto the floor; warm noon, cool moon at night; never clips to white"},
            {"id": "grotto_crystal_cluster", "kind": "crystal_cluster_blue", "position_xz": [10.2, -36.1], "height_m": 2.6,
             "glow": "emissive blue core <= 0.8 linear, no bloom clip"},
            {"id": "grotto_moon_pool", "kind": "still_pool", "position_xz": [7.4, -41.7], "radius_m": 1.3},
            {"id": "grotto_chest", "kind": "chest_old", "position_xz": [11.3, -39.4], "yaw_rad": 4.712},
            {"id": "grotto_mouth_arch", "kind": "cave_mouth_arch", "position_xz": [-4.0, -39.0], "yaw_rad": 4.712,
             "size_m": [4.5, 5.0]},
        ],
        "camera": {"policy_required": "camera collision (root request R-CAM-1)",
                   "why": "a 13 m boom at 22.4 deg rises only to 6.6 m within its 12 m reach; any rock above that line "
                          "inside 12 m occludes. The 10 m bluff surrounds the chamber within 12 m in every direction, so no "
                          "chamber inside the bluff can reach 0 % free-boom occlusion; see check_features camera_boom"},
    })
    # ========================= 2. Lotus Mere
    F.append({
        "id": "lotus_mere",
        "name": {"en": "Lotus Mere", "th": "บึงบัวศาลเก่า"},
        "purpose": "rest + discovery: a still lotus pond under the west cliffs; boardwalk to a drowned-shrine terrace "
                   "(shrine stone blessing), bench, light shafts; koi, frogs, dragonflies, fireflies at night",
        "landmark": "the shrine terrace with broken columns and a stair fragment against the mossy cliff",
        "route": {"in": "gate_road at the Sella crossroads -> mere_spur (40 m) -> boardwalk -> viewing platform -> "
                        "shrine terrace", "out": "back along the boardwalk and the spur (or south across the meadow)"},
        "calm": {"radius_m": 20, "core": "pond outline incl. terrace, decks and the bench"},
        "geometry": {"pond_outline_polygon_xz": P(mere_outline), "terrace_polygon_xz": P(terrace),
                     "size_m": [15.4, 15.7], "water_surface_y": -0.3, "bed_y": -0.9,
                     "still_water": True},
        "decks": [
            {"id": "lotus_boardwalk", "kind": "boardwalk", "polygon_xz": P(rect(-43.6, -37.4, 3.3, 5.8)),
             "deck_y_m": 0.05, "width_m": 2.5, "clear_width_m": 2.22, "length_m": 6.2,
             "note": "v3 M2: widened 1.9 -> 2.5 m (every feature route >= 2.5 m; it is the only way to the shrine terrace)",
             "landing_xz": [-37.4, 4.55], "posts": {"spacing_m": 1.5, "radius_m": 0.08, "edge_offsets_m": [0.06, 0.06]},
             "rails": {"height_m": 0.9, "thickness_m": 0.08, "collider": True}},
            {"id": "lotus_viewing_platform", "kind": "platform", "polygon_xz": P(rect(-46.6, -43.6, 3.0, 6.0)),
             "deck_y_m": 0.08, "size_m": [3.0, 3.0], "rails": {"sides": ["north", "south"], "height_m": 0.9,
                                                                  "collider": True}},
        ],
        "colliders": [
            {"id": "lotus_shrine_stone", "shape": "circle", "center_xz": [-49.8, 4.9], "radius_m": 0.55, "y": [0, 1.7]},
            {"id": "lotus_column_tall", "shape": "circle", "center_xz": [-51.7, 6.6], "radius_m": 0.45, "y": [0, 3.4]},
            {"id": "lotus_column_short", "shape": "circle", "center_xz": [-48.9, 6.9], "radius_m": 0.42, "y": [0, 1.3]},
            {"id": "lotus_column_fallen", "shape": "box", "center_xz": [-51.9, 2.7], "size_m": [1.7, 0.75],
             "yaw_rad": 0.35, "y": [0, 0.75]},
            {"id": "lotus_stair_fragment", "shape": "box", "center_xz": [-52.6, 5.0], "size_m": [1.4, 2.4],
             "yaw_rad": 1.4, "y": [0, 1.2]},
            {"id": "lotus_bench", "shape": "box", "center_xz": [-37.6, -4.6], "size_m": [1.8, 0.5], "yaw_rad": 0.6,
             "y": [0, 0.5]},
        ],
        "water_hazards": [
            {"id": "lotus_mere_water_north", "polygon_xz": P(mere_north)},
            {"id": "lotus_mere_water_south", "polygon_xz": P(mere_south)},
        ],
        "pois": [
            {"id": "lotus_shrine", "kind": "rest_shrine", "position_xz": [-49.8, 4.9], "stand_xz": [-48.2, 4.6],
             "interact_radius_m": 2.0, "note": "shrine stone blessing (future rest buff); Thai/English plaque"},
            {"id": "lotus_viewing_platform", "kind": "viewpoint", "position_xz": [-45.1, 4.5]},
            {"id": "lotus_bench", "kind": "rest_bench", "position_xz": [-37.6, -4.6], "stand_xz": [-36.9, -5.4],
             "note": "M2: moved beside the mere_spur so the bench is on the route (was (-43.2,-6.7), 9 m off any path)"},
        ],
        "hero_dressing": [
            {"id": "lotus_light_shaft_1", "kind": "light_shaft_card", "position_xz": [-47.6, 0.2], "radius_m": 1.8},
            {"id": "lotus_light_shaft_2", "kind": "light_shaft_card", "position_xz": [-43.2, 8.2], "radius_m": 1.6},
            {"id": "lotus_light_shaft_3", "kind": "light_shaft_card", "position_xz": [-50.6, 5.6], "radius_m": 1.4},
            {"id": "lotus_cliff_spring", "kind": "spring_trickle", "position_xz": [-52.4, 9.6],
             "note": "thin trickle down the cliff feeding the mere (falls lane, mist <= 0.3 alpha)"},
        ],
        "aquatic_rules": {"lily_pads": [30, 45], "lotus_flowers": [10, 14], "lotus_colours": ["pink", "white"],
                          "rule_ids": ["mere_lily_pads", "mere_lotus"]},
    })
    # ========================= 3. Brightwater Cove
    F.append({
        "id": "brightwater_cove",
        "name": {"en": "Brightwater Cove", "th": "อ่าวน้ำใส"},
        "purpose": "rest + future fishing: white-sand beach where the stream meets the lake; pier to cove_fishing_spot",
        "landmark": "the long timber pier on posts over turquoise shallows",
        "route": {"in": "southbound_trail just south of the bridge -> cove_path (38 m) along the stream's south bank -> "
                        "beach -> pier", "out": "back along the cove_path (the lake is a hazard, the cliffs frame N and S)"},
        "calm": {"radius_m": 12, "core": "beach band + pier + platform"},
        "placement_change": "brief window z -40..-64 moved south to z -55..-93: the beach at z -66..-90 keeps the cove's "
                            "12 m calm ring (+ aggro) clear of the four bridgewater_banks brookclaws (z -48.5..-48.9) "
                            "without moving any monster row; the stream mouth (z -55..-67) becomes the reedy estuary "
                            "headland between the A2 stream tail and the lake (the lake surface -0.35 never meets the "
                            "cascade levels -0.85 / -1.45)",
        "estuary_headland": {"polygon_xz": P([(-47.2, -58.6), (-47.6, -66.0), (-51.5, -66.4), (-56.0, -66.6),
                                              (-60.5, -67.4), (-64.0, -68.8), (-64.0, -63.4), (-60.0, -61.6),
                                              (-56.0, -60.6), (-52.0, -60.0)]),
                             "kind": "reeds_rocks_bank", "walkable": False,
                             "note": "reed beds, wet rocks and driftwood between the stream's south bank and the lake; "
                                     "beyond the walkable hint (x < -46); dressing zone cove_estuary_reeds"},
        "carve": {"west_cliffs_gap_between_z": [-55, -93],
                  "headlands": {"north": [-55.5, -55.0], "south": [-57.6, -93.0]},
                  "note": "cliff runs end at z -55 and resume at z -93; the cove opens west to the horizon"},
        "geometry": {"beach_polygon_xz": P(cove_beach), "beach_width_m": [8.0, 12.0], "water_surface_y": -0.35,
                     "shallow_band_m": 6.0, "deep_beyond_m": 6.0,
                     "lake_extends": "to the stage edge x -64 and beyond as a render-only far plane"},
        "decks": [
            {"id": "brightwater_pier", "kind": "pier", "polygon_xz": P(rect(-58.0, -45.0, pier_s, pier_n)),
             "deck_y_m": 0.35, "width_m": 2.5, "clear_width_m": 2.5, "length_m": 17.0, "landing_xz": [-45.0, -74.25],
             "posts": {"spacing_m": 2.0, "radius_m": 0.13, "outside_deck_m": 0.15, "height_above_deck_m": 0.8},
             "rails": None},
            {"id": "brightwater_pier_platform", "kind": "platform", "polygon_xz": P(rect(*plat)), "deck_y_m": 0.35,
             "size_m": [4.0, 4.0], "posts": {"corners_and_mid_edges": True, "radius_m": 0.15}},
        ],
        "colliders": [
            {"id": "cove_rowboat", "shape": "box", "center_xz": [-42.6, -83.4], "size_m": [1.3, 3.4], "yaw_rad": 2.2,
             "y": [0, 0.9]},
            {"id": "cove_driftwood_1", "shape": "capsule", "center_xz": [-40.0, -71.2], "length_m": 3.2, "radius_m": 0.25,
             "yaw_rad": 1.0, "y": [0, 0.5]},
            {"id": "cove_driftwood_2", "shape": "capsule", "center_xz": [-45.3, -87.0], "length_m": 2.6, "radius_m": 0.22,
             "yaw_rad": 2.6, "y": [0, 0.45]},
        ],
        "water_hazards": [{"id": "brightwater_cove_lake", "polygon_xz": P(cove_lake)}],
        "pois": [
            {"id": "cove_fishing_spot", "kind": "fishing_spot", "position_xz": [-60.6, -74.25], "radius_m": 1.6,
             "note": "future fishing system; interact while standing on the platform"},
            {"id": "cove_beach_rest", "kind": "rest_spot", "position_xz": [-41.5, -79.0]},
        ],
        "hero_dressing": [
            {"id": "cove_foam_line", "kind": "foam_line", "along": "brightwater_cove_lake shoreline inside the beach",
             "note": "white contact foam band 0.4-0.8 m, scrolling with the swell; second faint line 3-4 m out"},
            {"id": "cove_far_water", "kind": "far_water_plane", "x_range": [-160, -64], "z_range": [-110, -73],
             "surface_y": -0.35, "note": "render-only; north edge z -73 tucks under stream_end_spur_rock so it never "
                                         "meets the A2 stream tail"},
            {"id": "stream_end_spur_rock", "kind": "spur_boulder_mass", "center_xz": [-70.5, -69.8], "radius_m": 3.4,
             "height_m": [3.0, 5.0], "note": "A2: hides the stream end at P9 and the far-plane north edge; props-stone hero"},
        ],
    })
    # ========================= 4. Sunmeadow Croft
    F.append({
        "id": "sunmeadow_croft",
        "name": {"en": "Sunmeadow Croft", "th": "ฟาร์มคนเลี้ยงแกะ"},
        "purpose": "quest + rest: the shepherd's hamlet behind the hunter camp (croft_shepherd NPC slot, sheep pen, well, "
                   "campfire); lived-in landmark seen from the east exit ramp",
        "landmark": "the dome stone hut with its mossy roof, facing the yard",
        "placement_change": "brief said north of the hunter camp; the yard sits there (z -1..7.8, x >= 33.8) and the hut sits "
                            "in the support gap band (z 8.4..14.4) as a visible blocker; x >= 33.8 keeps the 15 m calm ring "
                            "(+3 m step-0 aggro) clear of every hunt_meadow_east home",
        "route": {"in": "gate_road -> camp_spur -> hunter camp -> croft_lane", "out": "croft_south_lane -> east_return_path "
                  "-> trail start (loop)"},
        "calm": {"radius_m": 15, "core": "croft bounds (yard, pen, hut)"},
        "bounds_xz": [33.8, 45.8, -15.0, 15.0],
        "buildings": [
            {"id": "croft_dome_hut", "kind": "dome_stone_hut", "center_xz": [38.6, 11.4], "diameter_m": 6.0,
             "door": {"facing": "south", "yaw_rad": 3.1416, "closed": True, "at_xz": [38.6, 8.4]},
             "roof": "mossy turf dome with a smoke hole"},
            {"id": "croft_sheep_pen", "kind": "stone_wall_pen", "bounds_xz": list(pen), "size_m": [9.0, 12.0],
             "wall": {"thickness_m": 0.6, "height_m": 1.1}, "gate": {"wall": "south", "center_xz": [38.5, -14.2],
                                                                     "width_m": 2.2, "closed": True},
             "sheep": 5},
            {"id": "croft_well", "kind": "covered_well", "center_xz": [35.6, 4.6], "diameter_m": 2.0, "roof": True},
        ],
        "colliders": [
            {"id": "croft_dome_hut", "shape": "circle", "center_xz": [38.6, 11.4], "radius_m": 3.0, "y": [0, 4.2]},
            {"id": "croft_well", "shape": "circle", "center_xz": [35.6, 4.6], "radius_m": 1.0, "y": [0, 2.6]},
            {"id": "croft_pen_wall_north", "shape": "box", "center_xz": [38.5, -2.5], "size_m": [9.0, 0.6], "y": [0, 1.1]},
            {"id": "croft_pen_wall_west", "shape": "box", "center_xz": [34.3, -8.2], "size_m": [0.6, 12.0], "y": [0, 1.1]},
            {"id": "croft_pen_wall_east", "shape": "box", "center_xz": [42.7, -8.2], "size_m": [0.6, 12.0], "y": [0, 1.1]},
            {"id": "croft_pen_wall_south_w", "shape": "box", "center_xz": [35.75, -13.9], "size_m": [3.5, 0.6], "y": [0, 1.1]},
            {"id": "croft_pen_wall_south_e", "shape": "box", "center_xz": [41.25, -13.9], "size_m": [3.5, 0.6], "y": [0, 1.1]},
            {"id": "croft_pen_gate", "shape": "box", "center_xz": [38.5, -13.9], "size_m": [2.2, 0.3], "y": [0, 1.0]},
            {"id": "croft_campfire", "shape": "circle", "center_xz": [40.4, 2.6], "radius_m": 0.6, "y": [0, 0.4]},
            {"id": "croft_log_seat_1", "shape": "box", "center_xz": [42.05, 3.55], "size_m": [1.2, 0.45], "yaw_rad": 2.09,
             "y": [0, 0.45]},
            {"id": "croft_log_seat_2", "shape": "box", "center_xz": [38.75, 3.55], "size_m": [1.2, 0.45], "yaw_rad": 1.05,
             "y": [0, 0.45]},
            {"id": "croft_log_seat_3", "shape": "box", "center_xz": [40.4, 0.7], "size_m": [1.2, 0.45], "yaw_rad": 0.0,
             "y": [0, 0.45]},
            {"id": "croft_woodpile", "shape": "box", "center_xz": [44.7, 4.0], "size_m": [0.9, 1.7], "y": [0, 1.2]},
            {"id": "croft_skep_shelf", "shape": "box", "center_xz": [43.4, 7.0], "size_m": [2.8, 0.7], "y": [0, 1.1]},
            {"id": "croft_veg_fence", "shape": "box", "center_xz": [44.6, -4.6], "size_m": [1.6, 3.6], "y": [0, 0.7]},
        ],
        "water_hazards": [],
        "pois": [
            {"id": "croft_shepherd", "kind": "npc_slot", "position_xz": [37.9, 6.4], "facing_yaw_rad": 3.6,
             "note": "NPC slot only; dialogue and quests are root's"},
            {"id": "croft_yard", "kind": "rest_spot", "position_xz": [39.6, 5.4]},
        ],
        "hero_dressing": [
            {"id": "croft_hay_skeps", "kind": "hay_skep", "count": 3, "on": "croft_skep_shelf",
             "positions_xz": [[42.5, 7.0], [43.4, 7.0], [44.3, 7.0]]},
            {"id": "croft_spit", "kind": "campfire_spit", "position_xz": [40.4, 2.6]},
            {"id": "croft_veg_patch", "kind": "vegetable_patch", "polygon_xz": P(rect(43.8, 45.4, -6.4, -2.8))},
            {"id": "croft_back_wall", "kind": "drystone_wall_low", "polyline_xz": P([(33.9, 8.3), (35.4, 8.6)]),
             "note": "short wall stub linking the hut to the gap-band hedge screen"},
            {"id": "croft_washing_line", "kind": "washing_line", "polyline_xz": P([(41.9, 8.8), (45.2, 9.6)])},
        ],
    })
    L["features"] = F

    # ------------------------------------------------------------------ hazards (polygon water) for the existing tools
    for f in F:
        for hz in f.get("water_hazards", []):
            if isinstance(hz, dict):
                L["hazards"].append({"id": hz["id"], "kind": "water", "polygon_xz": hz["polygon_xz"],
                                     "source": f"v3 feature {f['id']}"})

    # ------------------------------------------------------------------ relief changes
    for r in L["relief"]:
        if r["id"] == "inner_bluff":
            r["note"] = r["note"] + ("; v3: Waterfall Grotto carved in (falls ledge behind the curtain, 4.9 m tunnel, "
                                     "open-sky chamber); footprint_xz kept as the visual mass for v2 tools; the server "
                                     "collider becomes features[waterfall_grotto].colliders inner_bluff_solid_v3")
            r["grotto"] = "features[waterfall_grotto]"
        if r["id"] == "west_cliffs":
            r["gap"] = {"between_z": [-55, -93], "reason": "stream exit + Brightwater Cove carve (v3)",
                        "v2_between_z": [-55, -63]}
            r["note_v3"] = ("v3: the cliff runs end at z -55 and resume at z -93 (cove opening west to the horizon); the "
                            "polyline points inside the gap are dropped by the blockout run splitter; plan renders draw the "
                            "cove over the line")

    # ------------------------------------------------------------------ vegetation zone trims
    for v in L["vegetation_zones"]:
        if v["id"] == "west_pine_stand":
            v["polygon_xz"] = P([(-36.0, -60.6), (-24.0, -58.0), (-20.0, -100.0), (-50.0, -102.0), (-50.0, -93.5),
                                 (-38.0, -91.0), (-35.4, -86.0), (-34.8, -68.0)])
            v["note_v3"] = "trimmed for Brightwater Cove (beach + estuary) and its view corridor; v2 polygon in the archive"
        if v["id"] == "west_meadow_grove":
            v["polygon_xz"] = P([(-38.0, 20.0), (-20.0, 20.0), (-18.0, -18.0), (-44.0, -22.0), (-44.0, -6.5),
                                 (-36.5, -6.0), (-35.6, 9.0)])
            v["note_v3"] = "trimmed east of the Lotus Mere; the mere glade (pond, terrace, bench) keeps its own rules"
        if v["id"] == "east_meadow_grove":
            v["polygon_xz"] = P([(22.0, 22.0), (33.0, 22.0), (33.0, 13.8), (22.0, 9.2)])
            v["note_v3"] = ("trimmed west of the Sunmeadow Croft (croft bounds x 33.8..45.8) and south of the line spawn -> "
                            "croft hut (sightline sl7): the grove now frames the croft from the gap band (z >= 9)")

    # ------------------------------------------------------------------ landmarks (drawn + hazard-checked by v2 tools)
    L["landmarks"] += [
        {"id": "sunmeadow_croft", "kind": "camp", "subkind": "hamlet", "bounds_xz": [33.8, 45.8, -15.0, 15.0],
         "note": "v3 feature sunmeadow_croft (kind camp so the monster checker applies camp margins too)"},
        {"id": "grotto_chest", "kind": "discovery_chest", "position_xz": [11.3, -39.4],
         "note": "v3 feature waterfall_grotto: chest in the open-sky chamber"},
        {"id": "lotus_shrine", "kind": "rest_shrine", "position_xz": [-49.8, 4.9],
         "note": "v3 feature lotus_mere: shrine stone on the cliff-foot terrace"},
        {"id": "cove_fishing_spot", "kind": "fishing_spot", "position_xz": [-60.6, -74.25],
         "note": "v3 feature brightwater_cove: pier end platform (future fishing)"},
        {"id": "croft_shepherd", "kind": "npc_slot", "position_xz": [37.9, 6.4],
         "note": "v3 feature sunmeadow_croft: NPC slot"},
    ]

    # ------------------------------------------------------------------ sightlines (v3 reveals)
    L["sightlines"] += [
        {"id": "sl5_cove_from_bridge", "from": "stream_bridge deck (-13.0,-51.0), game camera", "from_xz": [-13.0, -51.0],
         "to": "brightwater_cove (lake + pier)", "to_xz": [-58.0, -74.25],
         "intent": "v3 reveal: from the bridge the stream leads the eye west-south-west to the cove's turquoise water and "
                   "the pier; the pine stand keeps a low view corridor (dressing rule sightline_corridors)",
         "corridor_polygon_xz": P([(-12.5, -49.2), (-14.5, -53.5), (-30.0, -62.5), (-46.5, -79.0), (-60.0, -78.5),
                                   (-60.0, -69.5), (-48.0, -64.5), (-30.0, -57.4)])},
        {"id": "sl6_mere_glimpse_from_gate_road", "from": "gate_road just south of the west ramp (-6.6,6.6), game camera",
         "from_xz": [-6.6, 6.6], "to": "lotus_mere (light shafts, shrine terrace)", "to_xz": [-46.0, 4.0],
         "intent": "v3 reveal: leaving the city the player glimpses the mere's light shafts and the cliff shrine across "
                   "the hunt meadow, through a low gap in the west meadow grove",
         "corridor_polygon_xz": P([(-8.6, 8.0), (-7.6, 4.4), (-20.0, 1.4), (-36.6, 0.6), (-38.6, 7.9), (-20.0, 7.9)])},
    ]

    # ------------------------------------------------------------------ light anchors (night, Claude lighting lane)
    L["sightlines"].append(
        {"id": "sl7_croft_from_spawn", "from": "player spawn slots (0,-3), game camera", "from_xz": [0.0, -3.0],
         "to": "sunmeadow_croft dome hut + chimney smoke", "to_xz": [38.6, 11.4],
         "intent": "v3: the lived-in croft reads from the spawn across the camp meadow (east meadow grove trimmed to z >= 9)",
         "corridor_polygon_xz": P([(2.0, -3.6), (36.0, 8.6), (38.6, 14.4), (2.0, -1.0)])})
    L["light_anchors"] = {
        "note": "night light anchors for the lighting lane; warm 2200-2600 K pools, never clip to white; the VFX lane adds "
                "flame/flicker; positions are explicit hero anchors, gate-road posts are generated by the dressing rule "
                "gate_road_lantern_posts",
        "explicit": [
            {"id": "croft_door_lantern", "kind": "hanging_lantern", "position_xz": [40.9, 8.0], "y_m": 2.2,
             "radius_m": 6.0, "intensity": 0.9, "kelvin": 2300},
            {"id": "croft_well_lantern", "kind": "hanging_lantern", "position_xz": [35.6, 4.6], "y_m": 2.3,
             "radius_m": 5.0, "intensity": 0.7, "kelvin": 2400},
            {"id": "croft_pen_gate_lantern", "kind": "post_lantern", "position_xz": [36.7, -15.3], "y_m": 1.9,
             "radius_m": 5.0, "intensity": 0.6, "kelvin": 2400},
            {"id": "croft_campfire", "kind": "fire", "position_xz": [40.4, 2.6], "y_m": 0.5, "radius_m": 7.0,
             "intensity": 1.0, "kelvin": 2000, "flicker": True},
            {"id": "lotus_shrine_candles", "kind": "shrine_candles", "position_xz": [-49.8, 4.9], "y_m": 1.1,
             "radius_m": 3.5, "intensity": 0.45, "kelvin": 2600},
            {"id": "cove_pier_lantern", "kind": "post_lantern", "position_xz": [-58.3, -72.0], "y_m": 1.6,
             "radius_m": 5.5, "intensity": 0.6, "kelvin": 2500},
            {"id": "grotto_crystal_glow", "kind": "crystal", "position_xz": [10.2, -36.1], "y_m": 1.2, "radius_m": 4.0,
             "intensity": 0.5, "kelvin": 9000, "color": "#6fb6ff"},
        ],
        "generated_rule": "gate_road_lantern_posts",
    }
    # ------------------------------------------------------------------ feature water bodies (single source for the water lane)
    L["water"] += [
        {"id": "lotus_mere_pond", "kind": "lake", "feature": "lotus_mere", "outline_xz": P(mere_outline),
         "surface_y": -0.3, "bed_y": -0.9, "still": True, "inflow": "lotus_cliff_spring (thin trickle at (-52.4,9.6))",
         "outflow": None, "palette": "clear green-teal shallows, darker teal over the deep centre; lily/lotus cover 25-35 %",
         "walk_hazards": ["lotus_mere_water_north", "lotus_mere_water_south"],
         "note": "v3: the boardwalk (x -43.6..-37.4) and the viewing platform split the hazard into north/south parts; the "
                 "water surface itself is one continuous body under the decks"},
        {"id": "brightwater_cove_lake", "kind": "lake", "feature": "brightwater_cove", "outline_xz": P(cove_lake),
         "surface_y": -0.35, "bed_y": -1.6, "still": False, "swell": {"amplitude_m": 0.04, "period_s": 5.5},
         "shallow_band_m": 6.0, "foam_line": "cove_foam_line", "far_plane": "cove_far_water",
         "palette": "turquoise shallows over white sand, deep blue beyond 6 m",
         "note": "v3: separate from the A2 stream tail (estuary headland between); pier notch cut out of the outline"},
    ]

    # ------------------------------------------------------------------ calm zones (no monster aggro inside)
    def bounds_rect(b):
        return P(rect(b[0], b[1], b[2], b[3]))
    L["calm_zones"] = {
        "rule": ("a calm zone is a circle (center_xz, radius_m). No monster home, patrol line or aggro disc may enter it: "
                 "dist(home or patrol, center) >= radius_m + aggro, with the deployed step0 aggro AND the planned "
                 "step1/step2 aggro where numeric (glade_wisp night 7 m). Server: spawn suppression + no aggro acquire "
                 "inside (codex-requests R-CALM-1). Ambient wildlife only. Checked by tools/levels/check_features.py"),
        "zones": [
            {"id": "calm_lotus_mere", "feature": "lotus_mere", "center_xz": [-46.4, 3.5], "radius_m": 20,
             "covers": "pond, terrace, boardwalk, platform, bench"},
            {"id": "calm_sunmeadow_croft", "feature": "sunmeadow_croft", "center_xz": [39.8, 0.0], "radius_m": 15,
             "covers": "yard, hut, well, campfire, pen (south wall at the rim)"},
            {"id": "calm_brightwater_cove", "feature": "brightwater_cove", "center_xz": [-50.0, -76.5], "radius_m": 12,
             "covers": "pier, landing, central beach (beach ends z -66.6 / -89.6 lie just outside)"},
            {"id": "calm_waterfall_grotto", "feature": "waterfall_grotto", "center_xz": [3.0, -39.5], "radius_m": 10,
             "covers": "falls ledge, tunnel, chamber, chest"},
        ],
    }

    # ------------------------------------------------------------------ ambient wildlife zones (wildlife lane input)
    L["ambient_zones"] = {
        "rule": ("ambient creatures are client-only, not pickable, no colliders, never block clicks or telegraph decals; "
                 "ground species flee from a player within flee_m and return after 6-10 s; counts are per graphics tier "
                 "High (Low = 0.4x rounded down, min 1 for hero species; Medium = 0.7x)"),
        "phases_source": "world-environment-state sampleEnvironment daylight: day >= 0.50, twilight 0.15-0.50, night < 0.15",
        "zones": [
            {"id": "az_mere", "group": "mere", "feature": "lotus_mere",
             "area": {"polygon_xz": P(mere_outline)},
             "species": [
                 {"species": "koi", "count": [5, 7], "habitat": "open water >= 0.6 m from the rim and the decks",
                  "y_m": [-0.45, -0.32], "phases": ["day", "twilight", "night"], "colours": ["orange-white", "gold"]},
                 {"species": "frog", "count": [3, 5], "habitat": "lily pads and the shore band 0-1.2 m outside the rim",
                  "flee_m": 2.5, "phases": ["day", "twilight", "night"], "audio": "croak chorus twilight+night"},
                 {"species": "dragonfly", "count": [4, 6], "habitat": "over water and reeds", "y_m": [0.4, 1.8],
                  "phases": ["day"]},
             ]},
            {"id": "az_cove", "group": "cove", "feature": "brightwater_cove",
             "area": {"polygon_xz": P(cove_lake)},
             "species": [
                 {"species": "duck", "count": [3, 5], "habitat": "lake surface within 14 m of the beach, >= 2 m from the pier",
                  "phases": ["day", "twilight"], "flee_m": 4.0},
                 {"species": "heron", "count": [1, 1], "habitat": "shallows anchor", "anchor_xz": [-50.4, -82.2],
                  "phases": ["day", "twilight"], "flee_m": 6.0, "note": "fly-off to the far shore when approached"},
                 {"species": "fish_jump", "count": [4, 6], "habitat": "lake >= 6 m from the shore and >= 3 m from the pier",
                  "phases": ["day", "twilight", "night"], "interval_s": [6, 14]},
             ]},
            {"id": "az_croft", "group": "croft", "feature": "sunmeadow_croft",
             "area": {"polygon_xz": bounds_rect([33.8, 45.8, -15.0, 8.0])},
             "species": [
                 {"species": "sheep", "count": [5, 5], "habitat": "inside croft_sheep_pen inset 0.8 m",
                  "area_polygon_xz": P(rect(34.9, 41.9, -13.4, -3.0)), "phases": ["day", "twilight", "night"],
                  "note": "night: lie down near the north wall"},
                 {"species": "bee", "count": [6, 10], "habitat": "within 3 m of croft_skep_shelf and over croft_veg_patch",
                  "centers_xz": [[43.4, 7.0], [44.6, -4.6]], "radius_m": 3.0, "y_m": [0.4, 1.6], "phases": ["day"]},
             ]},
            {"id": "az_meadow", "group": "meadow", "feature": None,
             "area": {"polygons_xz": [L["vegetation_zones"][[v["id"] for v in L["vegetation_zones"]].index("hunt_flowers")]["polygon_xz"],
                                      P([(-44, -24), (-23, -24), (-22, -32), (-23, -44.5), (-44, -44.5)])]},
             "species": [
                 {"species": "butterfly", "count": [10, 14], "habitat": "over the wildflower meadows (dressing wildflower_meadows)",
                  "y_m": [0.3, 1.8], "phases": ["day"], "colours": ["yellow", "white", "pale blue"]},
                 {"species": "songbird", "count": [3, 6], "habitat": "perch anchors + short hops; fly-over loops y 12-20 m",
                  "perches_xz": [[15, 11], [-9.5, -60], [24, -8], [38.6, 11.4]], "phases": ["day", "twilight"],
                  "flee_m": 3.0},
             ]},
            {"id": "az_night", "group": "night", "feature": None,
             "areas": [
                 {"id": "fireflies_mere", "polygon_xz": P(mere_outline), "buffer_m": 4.0, "count": [14, 20]},
                 {"id": "fireflies_stream", "along": "sunmeadow_stream s 0-50", "band_m": 3.0, "count": [12, 18]},
                 {"id": "fireflies_croft", "polygon_xz": bounds_rect([33.8, 45.8, -15.0, 8.0]), "count": [6, 10]},
                 {"id": "fireflies_glade_edge", "ring": {"center_xz": [0, -68], "r_m": [12.5, 16.0]}, "count": [8, 12],
                  "note": "outside the arena keep-clear (12 m)"},
             ],
             "species": [{"species": "firefly", "y_m": [0.3, 2.2], "phases": ["night"], "fade": "in over twilight",
                          "emissive": "warm yellow-green, <= 0.9 linear, no bloom clip"}]},
        ],
    }

    # ------------------------------------------------------------------ dressing zones (input for generate_dressing.py)
    L["dressing_zones"] = {
        "rule": "seeded procedural dressing (M3); landmarks stay explicit anchors; trees are NOT scattered here (trees lane "
                "reads forest_edges as a mask only)",
        "forest_edges": [
            {"id": "fe_west_meadow_grove", "zone": "west_meadow_grove", "band_m": [0, 6], "side": "inside the zone polygon",
             "polyline_xz": P([(-20.0, 20.0), (-18.0, -18.0), (-44.0, -22.0)])},
            {"id": "fe_east_meadow_grove", "zone": "east_meadow_grove", "band_m": [0, 6], "side": "inside the zone polygon",
             "polyline_xz": P([(22.0, 22.0), (22.0, 2.0), (31.0, -1.0)])},
            {"id": "fe_west_pine_stand", "zone": "west_pine_stand", "band_m": [0, 6], "side": "inside the zone polygon",
             "polyline_xz": P([(-36.0, -60.6), (-24.0, -58.0), (-20.0, -100.0)])},
            {"id": "fe_east_oak_grove", "zone": "east_oak_grove", "band_m": [0, 6], "side": "inside the zone polygon",
             "polyline_xz": P([(42.0, -34.0), (20.0, -34.0), (20.0, -100.0)])},
        ],
        "rock_clusters": [
            {"id": "grotto_rim_rocks", "around": "waterfall_grotto chamber rim", "count": [6, 9], "size_m": [0.6, 2.0],
             "note": "on the chamber floor edge (<= 1.2 m from the wall), mossy; never on the floor walk line"},
            {"id": "mere_cliff_foot", "polyline_xz": P([(-54.4, -4.0), (-54.0, 0.0), (-53.2, 6.0), (-52.4, 12.0)]),
             "count": [5, 8], "size_m": [0.8, 2.6]},
            {"id": "cove_headland_rocks", "polygon": "brightwater_cove.estuary_headland", "count": [5, 8],
             "size_m": [0.6, 2.4]},
            {"id": "cove_south_headland", "center_xz": [-46.5, -91.5], "radius_m": 4.0, "count": [4, 6],
             "size_m": [1.0, 3.2]},
            {"id": "croft_field_stones", "center_xz": [30.5, -20.5], "radius_m": 4.0, "count": [3, 5],
             "size_m": [0.4, 1.2], "note": "cleared field stones piled at the croft_south_lane bend"},
            {"id": "falls_meadow_scatter", "polygon_xz": P([(-44, -24), (-23, -24), (-22, -32), (-23, -44.5), (-44, -44.5)]),
             "count": [4, 7], "size_m": [0.5, 1.8], "note": "keep the monster homes' scatter_keep_clear"},
        ],
        "wildflower_meadows": [
            {"id": "wf_hunt_flowers", "zone": "hunt_flowers", "density": "high", "palette": ["yellow", "white", "pink"]},
            {"id": "wf_falls_meadow", "polygon_xz": P([(-44, -24), (-23, -24), (-22, -32), (-23, -44.5), (-44, -44.5)]),
             "density": "medium", "palette": ["white", "pale blue", "yellow"]},
            {"id": "wf_croft_meadow", "polygon_xz": P([(26.0, -30.0), (45.0, -30.0), (45.0, -15.6), (33.8, -15.6),
                                                       (26.0, -22.0)]), "density": "medium",
             "palette": ["yellow", "white", "purple clover"]},
            {"id": "wf_mere_glade", "around": "lotus_mere_pond outline", "band_m": [1.5, 7.0], "density": "medium",
             "palette": ["white", "pink", "blue forget-me-not"]},
            {"id": "wf_glade_edge", "zone": "glade_edge", "ring": {"center_xz": [0, -68], "r_m": [11.5, 13.0]},
             "density": "medium", "note": "v2 rule: flowers only (<= 0.35 m, no glow) inside 11 m"},
        ],
        "mushroom_rings": [
            {"id": "mr_pine_1", "center_xz": [-36.0, -78.0], "radius_m": 1.6, "count": [9, 13], "glow": "night faint"},
            {"id": "mr_pine_2", "center_xz": [-30.5, -70.5], "radius_m": 1.3, "count": [7, 10], "glow": None},
            {"id": "mr_oak", "center_xz": [30.0, -56.0], "radius_m": 1.5, "count": [8, 12], "glow": "night faint"},
            {"id": "mr_west_grove", "center_xz": [-32.0, -14.5], "radius_m": 1.2, "count": [6, 9], "glow": None},
        ],
        "fallen_logs": [
            {"id": "fl_pine_stand", "zone": "west_pine_stand", "count": [4, 6], "length_m": [3.0, 6.0]},
            {"id": "fl_oak_grove", "zone": "east_oak_grove", "count": [3, 5], "length_m": [3.0, 5.5]},
            {"id": "fl_west_grove", "zone": "west_meadow_grove", "count": [2, 3], "length_m": [2.5, 4.5]},
            {"id": "fl_falls_meadow_edge", "polyline_xz": P([(-44.0, -24.5), (-44.0, -44.0)]), "count": [1, 2],
             "length_m": [3.0, 4.5]},
        ],
        "shore_reeds": [
            {"id": "reeds_mere", "around": "lotus_mere_pond outline", "band_m": [-0.8, 1.0], "coverage": 0.35,
             "skip": "boardwalk, viewing platform and terrace edges (+0.6 m)"},
            {"id": "reeds_stream", "zone": "stream_reeds", "band_m": [-0.4, 1.2], "coverage": 0.3,
             "skip": "bridge approach 3 m, the trail and the grotto approach"},
            {"id": "cove_estuary_reeds", "polygon": "brightwater_cove.estuary_headland", "coverage": 0.5},
        ],
        "aquatic": [
            {"id": "mere_lily_pads", "water": "lotus_mere_pond", "count": [30, 45], "rule": "clustered 3-7, >= 0.5 m from decks"},
            {"id": "mere_lotus", "water": "lotus_mere_pond", "count": [10, 14], "rule": "on lily clusters; pink 70 %, white 30 %"},
            {"id": "cove_driftwood", "water": "brightwater_cove beach band", "count": [3, 5], "rule": "on sand, plus the two "
             "explicit cove_driftwood colliders"},
        ],
    }

    # ------------------------------------------------------------------ anchor index (every explicit anchor, one list)
    idx = []
    def add(aid, kind, xz, src, **kw):
        e = {"id": aid, "kind": kind, "xz": [r3(xz[0]), r3(xz[1])], "source": src}
        e.update(kw)
        idx.append(e)
    for k, v in L["anchors"].items():
        add(k, "layout_anchor", v, "anchors")
    add("player_spawn", "spawn", [0, -3], "spawn slots x {-3,-1,1,3}, z -3-1.5*row, rows 0-11")
    add("warp_windstone_portal", "warp", [0, -68], "landmarks.windstone_circle.warp", radius_m=1.8)
    add("warp_sunmeadow_south", "warp", [0, -101], "south gate warp", radius_m=3.0)
    add("windstone_arena", "arena", [0, -68], "arena keep-clear", radius_m=12)
    add("hunter_camp", "camp", [25, -9.5], "landmarks.hunter_camp bounds centre")
    add("falls_lip", "water", falls["lip_xz"], "water.bluff_falls")
    add("falls_landing", "water", falls["landing_xz"], "water.bluff_falls")
    add("falls_pool", "water", pool["center_xz"], "water.falls_pool (A1)", radius_m=2.6)
    add("stream_outlet", "water", pool["outlet_xz"], "water.falls_pool")
    for c in st["cascades"]:
        add(c["id"], "water", c["lip_xz"], "water.sunmeadow_stream (A2)")
    add("stream_end_p9", "water", st["end"]["xz"], "water.sunmeadow_stream (A2)")
    for f in F:
        add(f["id"], "feature", _feature_center(f), f"features.{f['id']}")
        for p in f.get("pois", []):
            add(p["id"], p["kind"], p["position_xz"], f"features.{f['id']}.pois")
        for b in f.get("buildings", []):
            add(b["id"], b["kind"], b["center_xz"] if "center_xz" in b else
                [(b["bounds_xz"][0] + b["bounds_xz"][1]) / 2, (b["bounds_xz"][2] + b["bounds_xz"][3]) / 2],
                f"features.{f['id']}.buildings")
        for h in f.get("hero_dressing", []):
            if "position_xz" in h:
                add(h["id"], h["kind"], h["position_xz"], f"features.{f['id']}.hero_dressing")
            elif "center_xz" in h:
                add(h["id"], h["kind"], h["center_xz"], f"features.{f['id']}.hero_dressing")
        for d in f.get("decks", []):
            if "landing_xz" in d:
                add(d["id"] + "_landing", "deck_landing", d["landing_xz"], f"features.{f['id']}.decks")
    for la in L["light_anchors"]["explicit"]:
        add(la["id"], "light_" + la["kind"], la["position_xz"], "light_anchors")
    seen = set()
    L["anchor_index"] = [e for e in idx if not (e["id"], e["kind"]) in seen and not seen.add((e["id"], e["kind"]))]

    # ------------------------------------------------------------------ walk network index (paths + feature walkways + decks)
    walk = [{"id": p["id"], "class": p.get("class", "spur"), "width_m": p["width_m"], "points": p["points"],
             "source": "paths"} for p in L["paths"]]
    for f in F:
        for w in f.get("walkways", []):
            walk.append({"id": w["id"], "class": "feature_walkway", "width_m": w["width_m"], "points": w["points"],
                         "source": f"features.{f['id']}.walkways"})
        for d in f.get("decks", []):
            walk.append({"id": d["id"], "class": "deck", "polygon_xz": d["polygon_xz"],
                         "source": f"features.{f['id']}.decks"})
    plazas = [
        ("hunter_camp_yard", rect(19.0, 31.0, -16.0, -3.0), "landmarks.hunter_camp bounds"),
        ("croft_yard", rect(33.8, 45.8, -2.2, 8.3), "features.sunmeadow_croft (north of the pen wall)"),
        ("cove_beach", cove_beach, "features.brightwater_cove.geometry.beach_polygon_xz"),
        ("mere_terrace", terrace, "features.lotus_mere.geometry.terrace_polygon_xz"),
        ("grotto_chamber", chamber, "features.waterfall_grotto.carve.chamber"),
    ]
    for pid, poly, src in plazas:
        walk.append({"id": pid, "class": "plaza", "polygon_xz": P(poly), "source": src})
    L["walk_network"] = {"rule": "every walk line, deck and walkable plaza; grass/dressing exclusions use width/2 + 1 m "
                                 "on lines and +0.5 m on decks; plazas get the 'feature' density mask", "items": walk}

    DST.write_text(json.dumps(L, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", DST)
    write_assets(L)
    write_monsters()


def write_monsters():
    """live_xz <- zones.json zone 1 (read-only, Codex-owned); proposed_home_xz_v3 for the C4 conflicts. Nothing else."""
    M = json.loads(MON_SRC.read_text(encoding="utf-8"))
    zd = json.loads(ZONES.read_text(encoding="utf-8"))
    zs = zd if isinstance(zd, list) else zd.get("zones", [])
    live = next(z for z in zs if z.get("id") == 1)["monster_spawns"]
    changes = []
    for s in M["spawn_rows"]:
        r = s["row"]
        if r < len(live):
            sp = live[r]
            assert sp["enemy"] == s["enemy"], (r, sp, s["enemy"])
            new = [sp["x"], sp["z"]]
            if s.get("live_xz") != new:
                changes.append({"row": r, "enemy": s["enemy"], "from": s.get("live_xz"), "to": new})
                s["live_xz"] = new
        if r in PROPOSALS:
            s["proposed_home_xz_v3"] = PROPOSALS[r][0]
            s["proposed_home_reason_v3"] = PROPOSALS[r][1]
    M["live_sync_v3"] = {"date": "2026-10-03", "source": "content/source/zones.json zone 1 monster_spawns (read-only)",
                         "changes": changes,
                         "note": "live_xz mirrors what is live (A33 + the Claude follow-up wisp (-15,-2) / boar (13,6) "
                                 "and root's puddlekin row 0 (15,-1.5)); intended == live for rows 0-12, so there is no "
                                 "open live mismatch. proposed_home_xz_v3 = design-home proposals from "
                                 "tools/levels/check_features.py C4 (spawn slots), for Claude main / root to adopt"}
    MON_DST.write_text(json.dumps(M, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", MON_DST, "live_xz changes:", len(changes))


def _feature_center(f):
    if f["id"] == "waterfall_grotto":
        return [6.25, -39.0]
    if f["id"] == "lotus_mere":
        return [-46.4, 3.5]
    if f["id"] == "brightwater_cove":
        return [-47.0, -77.0]
    if f["id"] == "sunmeadow_croft":
        return [39.8, 0.0]
    raise KeyError(f["id"])


def write_assets(L):
    """planning/levels/sunmeadow-v3-feature-assets.json: per feature, asset ids, counts, size ranges, building lane."""
    def a(aid, lane, count, size_m, note="", collider="none", lod=True):
        return {"asset_id": aid, "lane": lane, "count": count, "size_m": size_m, "collider": collider,
                "needs_lods": lod, "note": note}
    feats = {
        "waterfall_grotto": [
            a("grotto_cave_mouth_arch", "props-stone", 1, [4.5, 5.0, 3.0], "mouth 4.5 w x 5.0 h, overhang lip; mossy sandstone", "solid"),
            a("grotto_tunnel_shell", "props-stone", 1, [4.9, 5.0, 4.5], "roofed tunnel walls, 4.5 m clear, <= 5 m long", "solid"),
            a("grotto_chamber_wall_kit", "props-stone", [5, 7], [2.0, 6.0], "rim pieces around the 12 x 10 m open-sky chamber; ledges at 3.5 / 6 m", "solid"),
            a("grotto_crystal_cluster_blue", "props-stone", 1, [1.8, 2.6], "hero crystal, emissive core <= 0.8", "solid"),
            a("grotto_crystal_small", "props-stone", [6, 10], [0.3, 0.9], "satellite crystals on the rim"),
            a("grotto_chest_old", "props-craft", 1, [1.1, 0.7, 0.8], "grotto_chest anchor", "solid"),
            a("grotto_rim_rock", "props-stone", [6, 9], [0.6, 2.0], "dressing grotto_rim_rocks", "soft"),
            a("grotto_light_shaft_card", "water", 1, [2.2, 8.0], "god-ray card (VFX-ish, water/FX lane)"),
            a("grotto_moon_pool", "water", 1, [2.6, 2.6], "still mirror pool r 1.3"),
            a("grotto_moss_carpet", "grass", 1, [12.0, 10.0], "moss + fern ground cover on the chamber floor edges"),
        ],
        "lotus_mere": [
            a("mere_shrine_stone", "props-stone", 1, [1.1, 1.7], "rest shrine with plaque", "solid"),
            a("mere_column_tall", "props-stone", 1, [0.9, 3.4], "broken column", "solid"),
            a("mere_column_short", "props-stone", 1, [0.85, 1.3], "", "solid"),
            a("mere_column_fallen", "props-stone", 1, [1.7, 0.75], "", "solid"),
            a("mere_stair_fragment", "props-stone", 1, [2.4, 1.4, 1.2], "", "solid"),
            a("mere_terrace_flagstones", "props-stone", 1, [7.0, 6.0], "terrace floor tiles (decal-like slabs)"),
            a("mere_cliff_foot_rock", "props-stone", [5, 8], [0.8, 2.6], "dressing mere_cliff_foot", "soft"),
            a("mere_boardwalk", "props-craft", 1, [6.2, 1.9], "timber boardwalk, posts 1.5 m, rails 0.9 m", "solid"),
            a("mere_viewing_platform", "props-craft", 1, [3.0, 3.0], "rails north/south", "solid"),
            a("mere_bench", "props-craft", 1, [1.8, 0.5, 0.5], "", "solid"),
            a("lily_pad", "props-craft", [30, 45], [0.35, 0.9], "3 variants, clustered 3-7"),
            a("lotus_flower", "props-craft", [10, 14], [0.25, 0.45], "pink 70 % / white 30 %, on pads"),
            a("reed_clump", "props-craft", [14, 22], [0.6, 1.6], "dressing reeds_mere", "none"),
            a("mere_spring_trickle", "water", 1, [0.6, 9.0], "thin cliff trickle into the mere"),
            a("lotus_mere_pond", "water", 1, [15.4, 15.7], "still pond surface"),
            a("mere_light_shaft_card", "water", 3, [1.4, 6.0], "light shafts"),
            a("mere_glade_flowers", "grass", 1, None, "wf_mere_glade band"),
            a("mere_ambient_set", "wildlife", 1, None, "koi 5-7, frogs 3-5, dragonflies 4-6, fireflies 14-20"),
        ],
        "brightwater_cove": [
            a("cove_pier_17m", "props-craft", 1, [17.0, 2.5], "deck y 0.35, posts every 2 m, no rails", "solid"),
            a("cove_pier_platform", "props-craft", 1, [4.0, 4.0], "end platform with the fishing spot", "solid"),
            a("cove_rowboat", "props-craft", 1, [3.4, 1.3, 0.9], "beached", "solid"),
            a("cove_driftwood", "props-craft", [5, 7], [1.5, 3.2], "2 explicit colliders + 3-5 dressing", "soft"),
            a("cove_pier_lantern_post", "props-craft", 1, [0.3, 1.6], "light anchor cove_pier_lantern"),
            a("cove_fishing_props", "props-craft", 1, [1.2, 0.8], "rod rack, bucket, net"),
            a("cove_headland_rock", "props-stone", [5, 8], [0.6, 2.4], "dressing cove_headland_rocks", "soft"),
            a("cove_south_headland_rock", "props-stone", [4, 6], [1.0, 3.2], "", "solid"),
            a("stream_end_spur_rock", "props-stone", 1, [6.8, 5.0], "A2 hero boulder mass hiding P9", "solid"),
            a("west_cliff_run_end_caps", "props-stone", 2, [6.0, 14.0], "cliff run ends at z -55 and -93"),
            a("brightwater_cove_lake", "water", 1, [17.0, 26.0], "lake + foam line + far plane"),
            a("stream_exit_cascades", "water", 2, [3.4, 0.6], "A2 cascade sheets"),
            a("cove_sand_beach", "grass", 1, [10.0, 23.0], "sand ground material + beach grass tufts at the back edge"),
            a("cove_estuary_reeds", "props-craft", [20, 30], [0.6, 1.8], "reed beds on the headland"),
            a("cove_ambient_set", "wildlife", 1, None, "ducks 3-5, heron 1, fish jumps 4-6"),
        ],
        "sunmeadow_croft": [
            a("croft_dome_hut", "props-craft", 1, [6.0, 6.0, 4.2], "dome stone hut, mossy turf roof, smoke hole", "solid"),
            a("croft_sheep_pen_wall", "props-stone", 6, [3.5, 0.6, 1.1], "drystone wall pieces (N, W, E, 2x S)", "solid"),
            a("croft_pen_gate", "props-craft", 1, [2.2, 0.3, 1.0], "", "solid"),
            a("croft_covered_well", "props-craft", 1, [2.0, 2.6], "", "solid"),
            a("hay_skep", "props-craft", 3, [0.5, 0.6], "on croft_skep_shelf"),
            a("croft_skep_shelf", "props-craft", 1, [2.8, 0.7, 1.1], "", "solid"),
            a("croft_campfire_spit", "props-craft", 1, [1.2, 1.0], "", "solid"),
            a("croft_log_seat", "props-craft", 3, [1.2, 0.45], "", "solid"),
            a("croft_woodpile", "props-craft", 1, [1.7, 0.9, 1.2], "", "solid"),
            a("croft_veg_patch_fence", "props-craft", 1, [3.6, 1.6, 0.7], "", "solid"),
            a("croft_washing_line", "props-craft", 1, [3.4, 1.8], ""),
            a("croft_back_wall_stub", "props-stone", 1, [1.6, 0.5, 0.8], "", "solid"),
            a("croft_lanterns", "props-craft", 3, [0.3, 2.2], "door, well, pen gate"),
            a("croft_field_stone", "props-stone", [3, 5], [0.4, 1.2], "dressing croft_field_stones", "soft"),
            a("croft_meadow_grass", "grass", 1, None, "wf_croft_meadow + trampled yard"),
            a("croft_ambient_set", "wildlife", 1, None, "sheep 5 (pen), bees 6-10"),
        ],
        "shared_dressing": [
            a("rock_S", "props-stone", None, [0.3, 0.8], "generated (M3)", "none"),
            a("rock_M", "props-stone", None, [0.8, 1.6], "generated (M3)", "soft"),
            a("rock_L", "props-stone", None, [1.6, 3.0], "generated (M3)", "solid"),
            a("boulder", "props-stone", None, [3.0, 4.5], "generated (M3)", "solid"),
            a("stepping_stone", "props-stone", None, [0.6, 1.0], "stream / mere edges (M3)", "none"),
            a("cliff_piece", "props-stone", None, [4.0, 14.0], "west cliffs + bluff (M3)", "solid"),
            a("bush_round", "props-craft", None, [0.8, 1.8], "generated (M3), flora family", "soft"),
            a("mushroom_ring_set", "props-craft", None, [0.08, 0.3], "4 rings (M3)", "none"),
            a("fallen_log", "props-craft", None, [2.5, 6.0], "generated (M3)", "soft"),
            a("hay_bale_small", "props-craft", None, [0.8, 1.2], "croft + camp (M3)", "soft"),
            a("fence_run_post_rail", "props-craft", None, [2.0, 1.0], "croft + camp edges (M3)", "solid"),
            a("wildflower_patches", "grass", None, None, "wildflower_meadows (M3 masks)"),
            a("meadow_ambient_set", "wildlife", 1, None, "butterflies 10-14, songbirds 3-6, fireflies at night"),
        ],
        "trees": [
            a("forest_edge_mask", "trees", 1, None, "trees lane only: dressing_zones.forest_edges + vegetation_zones; "
              "this lane places no trees (CC0 kit or approved generator only)"),
        ],
    }
    out = {
        "schema": "xexoria.feature-assets/1",
        "region": "sunmeadow",
        "layout": "planning/levels/sunmeadow-v2-layout.json (version v3-features)",
        "generated_by": "tools/levels/build_layout_v3.py",
        "lanes": {"props-stone": "rocks, cliffs, grotto, ruins, stone walls",
                  "props-craft": "lotus, lily, reeds, pier, croft, cove props, flora",
                  "water": "every water surface, falls, cascades, light-shaft cards",
                  "grass": "ground cover, sand, moss, wildflower masks",
                  "wildlife": "ambient creatures from layout.ambient_zones",
                  "trees": "masks only"},
        "size_m_convention": "[width, height] or [length, width, height] in metres; null = mask/area asset",
        "count_convention": "int or [min, max]; null = generated by tools/levels/generate_dressing.py (M3)",
        "art": "stylised hand-painted, chunky silhouettes, painted AO; judge at the 13 m camera beside a 1.8 m witness",
        "features": feats,
    }
    ASSETS.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", ASSETS)


if __name__ == "__main__":
    main()
