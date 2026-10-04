"""Rock kit spec (P1): 10 boulders, 5 cliff chunks, 18 stream stones, 2 pebble clusters.

Every variant is (recipe id, seed, params). Seeds come from a handful of family seeds:
  boulders  2026100201 + k     cliffs  2026100301 + k     stream stones 20261002 + k (water spec section 4.5 seed)
  pebbles   2026100401 + k
Sizes follow the brief (boulders 0.8-2.5 m, cliff chunks 3-6 m) and docs/reviews/2026-10-02-map-water-spec.md 4.5
(stream stones: 11 bank 0.4-1.0 m emerged 0.05-0.35 m, 4 submerged 0.5-1.2 m top 0.08-0.20 m under water,
3 emerged boulders 0.9-1.6 m top <= +0.6 m above water).
"""
from __future__ import annotations

import numpy as np

KIT = "rocks"
B0, C0, S0, P0 = 2026100201, 2026100301, 20261002, 2026100401

# paint presets consumed by np_paint.py (per asset)
WARM = "sun_stone"
RIVER = "river_stone"
CLIFF = "cliff_stone"

ATLASES = [
    {"id": "sm_rock_a", "albedo_px": 1024, "data_px": 1024, "ao_distance": 0.45, "palette": WARM,
     "budget_class": "prop"},
    {"id": "sm_rock_b", "albedo_px": 1024, "data_px": 1024, "ao_distance": 0.45, "palette": WARM,
     "budget_class": "prop"},
    {"id": "sm_cliff_a", "albedo_px": 2048, "data_px": 1024, "ao_distance": 1.1, "palette": CLIFF,
     "budget_class": "building_module"},
    {"id": "sm_cliff_b", "albedo_px": 2048, "data_px": 1024, "ao_distance": 1.1, "palette": CLIFF,
     "budget_class": "building_module"},
    {"id": "sm_stone_river", "albedo_px": 1024, "data_px": 1024, "ao_distance": 0.25, "palette": RIVER,
     "budget_class": "prop"},
]


def _boulder(k, name, size, atlas, tris, paint, **p):
    return {"id": f"sm_boulder_{k:02d}", "name": name, "kit": KIT, "group": "boulder", "priority": "P1",
            "recipe": "rock.boulder/1", "seed": B0 + k, "params": dict(size=size, **p), "atlas": atlas,
            "lod0_tris": tris, "budget_class": "prop", "paint": paint,
            "collider": {"shape": "convex", "kind": "solid_structure", "blocking": True}}


def _cliff(k, name, size, atlas, tris, paint, **p):
    return {"id": f"sm_cliff_{k:02d}", "name": name, "kit": KIT, "group": "cliff_chunk", "priority": "P1",
            "recipe": "rock.cliff/1", "seed": C0 + k, "params": dict(size=size, **p), "atlas": atlas,
            "lod0_tris": tris, "budget_class": "building_module", "paint": paint, "shadow_proxy": True,
            "collider": {"shape": "convex", "kind": "solid_structure", "blocking": True}}


def assets():
    A = []
    # ---- hero boulders (atlas a) ----
    A.append(_boulder(1, "anvil (landmark seat)", [2.5, 1.9, 1.35], "sm_rock_a", 1400,
                      {"moss": 0.22, "lichen": 0.5, "hero": True},
                      blobs=[{"c": [0, 0, 0], "r": [1, 1, 1]}, {"c": [-0.35, 0.25, 0.25], "r": [0.6, 0.65, 0.7]}],
                      cuts=13, flat_top=0.55, top_level=0.82, chips=30))
    A.append(_boulder(2, "leaning tooth", [1.25, 1.05, 1.95], "sm_rock_a", 1150,
                      {"moss": 0.16, "lichen": 0.6, "hero": True}, lean_deg=8.0, cuts=11, top_bias=0.25, chips=26))
    A.append(_boulder(3, "split boulder", [1.65, 1.35, 1.1], "sm_rock_a", 1050,
                      {"moss": 0.2, "lichen": 0.4, "hero": True}, crack=0.85, crack_scale=0.75, crack_depth=0.022,
                      crack_width=0.07, cuts=10, chips=22))
    A.append(_boulder(4, "small chunk", [0.85, 0.75, 0.6], "sm_rock_a", 560,
                      {"moss": 0.15, "lichen": 0.3, "hero": True}, cuts=9, chips=14, chip_radius=0.16))
    A.append(_boulder(9, "standing shard", [0.95, 0.62, 1.35], "sm_rock_a", 820,
                      {"moss": 0.12, "lichen": 0.5}, cuts=12, top_bias=0.2, lean_deg=-5.0, chips=20))
    # ---- mossy variants and fillers (atlas b) ----
    A.append(_boulder(5, "mossy slab", [2.1, 1.6, 0.85], "sm_rock_b", 1150,
                      {"moss": 0.78, "lichen": 0.3, "mossy": True}, flat_top=0.45, top_level=0.78, chips=18,
                      round_bias=0.3))
    A.append(_boulder(6, "mossy dome", [1.4, 1.25, 1.0], "sm_rock_b", 900,
                      {"moss": 0.72, "lichen": 0.25, "mossy": True}, cuts=8, chips=10, round_bias=0.6))
    A.append(_boulder(7, "mossy fused pair", [1.85, 1.2, 1.15], "sm_rock_b", 1100,
                      {"moss": 0.66, "lichen": 0.3, "mossy": True},
                      blobs=[{"c": [-0.38, 0, 0], "r": [0.66, 0.95, 1.0]}, {"c": [0.45, 0.05, -0.18], "r": [0.58, 0.85, 0.78]}],
                      cuts=9, chips=14, round_bias=0.35))
    A.append(_boulder(8, "flat step stone", [1.2, 0.95, 0.42], "sm_rock_b", 620,
                      {"moss": 0.3, "lichen": 0.35}, flat_top=0.7, top_level=0.72, cuts=8, chips=10))
    A.append(_boulder(10, "rubble block", [1.1, 0.95, 0.72], "sm_rock_b", 700,
                      {"moss": 0.28, "lichen": 0.45}, cuts=12, chips=18))
    # ---- cliff chunks (atlas cliff_a / cliff_b) ----
    A.append(_cliff(1, "tall strata block", [3.2, 2.4, 5.0], "sm_cliff_a", 3400, {"moss": 0.45, "grass_top": True}))
    A.append(_cliff(2, "wide ledge", [6.0, 3.0, 3.0], "sm_cliff_a", 3800, {"moss": 0.5, "grass_top": True},
                    blobs=[{"c": [0, 0, -0.3], "r": [1.0, 1.0, 0.75]}, {"c": [-0.25, 0.05, 0.35], "r": [0.6, 0.85, 0.7]}]))
    A.append(_cliff(3, "corner buttress", [4.0, 3.6, 3.8], "sm_cliff_a", 3600, {"moss": 0.4, "grass_top": True},
                    blobs=[{"c": [0, 0, -0.3], "r": [1.0, 1.0, 0.75]}, {"c": [0.2, -0.2, 0.35], "r": [0.7, 0.7, 0.7]},
                           {"c": [-0.45, 0.35, -0.2], "r": [0.5, 0.55, 0.6]}]))
    A.append(_cliff(4, "face slab", [4.5, 1.9, 4.2], "sm_cliff_b", 3200, {"moss": 0.35, "grass_top": True},
                    back_flat=0.25))
    A.append(_cliff(5, "toe block", [3.5, 2.6, 1.8], "sm_cliff_b", 2600, {"moss": 0.55, "grass_top": False},
                    blobs=[{"c": [0, 0, 0], "r": [1, 1, 1]}], flat_top=0.35, strata=0.008))
    # ---- stream stones (18, water spec 4.5) ----
    rng = np.random.default_rng(S0)
    k = 0
    for i in range(11):   # bank stones 0.4-1.0 m
        s = float(np.round(0.4 + 0.6 * (i / 10.0) ** 1.1 + rng.uniform(-0.03, 0.03), 3))
        flat = float(np.round(rng.uniform(0.48, 0.66), 3))
        k += 1
        A.append(_stone(k, "bank", [s, s * float(np.round(rng.uniform(0.72, 0.92), 3)), s * flat], seed=S0 + k,
                        emerged=float(np.round(rng.uniform(0.05, 0.35), 3)), rng=rng))
    for i in range(4):    # submerged 0.5-1.2 m, flat
        s = [0.5, 0.75, 0.95, 1.2][i]
        k += 1
        A.append(_stone(k, "submerged", [s, s * float(np.round(rng.uniform(0.7, 0.85), 3)), s * 0.32], seed=S0 + k,
                        emerged=-float(np.round(rng.uniform(0.08, 0.20), 3)), rng=rng))
    for i in range(3):    # emerged boulders 0.9-1.6 m
        s = [0.95, 1.25, 1.6][i]
        k += 1
        A.append(_stone(k, "emerged_boulder", [s, s * 0.82, s * 0.62], seed=S0 + k,
                        emerged=float(np.round(min(0.6, s * 0.62 * 0.7), 3)), rng=rng))
    # ---- pebble clusters ----
    for j in range(2):
        A.append({"id": f"sm_pebbles_{j + 1:02d}", "name": "pebble cluster", "kit": KIT, "group": "pebbles",
                  "priority": "P1", "recipe": "rock.pebbles/1", "seed": P0 + j,
                  "params": {"count": 7 + j, "radius": 0.30 + 0.06 * j}, "atlas": "sm_stone_river",
                  "lod0_tris": 290, "budget_class": "prop", "paint": {"moss": 0.05, "dry": True},
                  "collider": {"shape": "none_walkable", "kind": "decor", "blocking": False}})
    return A


def _stone(k, group, size, seed, emerged, rng):
    w, d, h = size
    tris = int(np.clip(260 + 520 * (max(w, d) - 0.4) / 1.2, 220, 900))
    # waterline height above the pivot (pivot = bottom contact); emerged > 0 means the top is above water
    water_level = float(np.round(h - emerged, 3))
    return {"id": f"sm_stream_stone_{k:02d}", "name": f"stream stone ({group})", "kit": KIT, "group": f"stream_{group}",
            "priority": "P1", "recipe": "rock.river/1", "seed": seed,
            "params": {"size": [float(np.round(x, 3)) for x in size], "embed": 0.14 if group != "submerged" else 0.2},
            "atlas": "sm_stone_river", "lod0_tris": tris, "budget_class": "prop",
            "paint": {"moss": 0.0, "water_level_m": water_level, "wet": True},
            "placement": {"intended_emerged_m": emerged, "water_level_above_pivot_m": water_level},
            "collider": {"shape": "convex", "kind": "water_hazard_decor", "blocking": False}}
