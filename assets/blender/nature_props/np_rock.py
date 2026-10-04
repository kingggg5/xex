"""Procedural rock recipes for the Sunmeadow prop library (owner direction 2026-10-02 21:35: "try to make procedural").

Recipes (seeded, parametric; LOD0-2 and the collider come from the same recipe run):
  rock.boulder/1   faceted hull union -> coarse remesh -> large lumps -> fine remesh -> knapped chips -> cracks
                   -> optional strata / flat top -> fine pits -> soften -> embed cut -> exact bbox
  rock.cliff/1     boulder recipe with stacked blobs, vertical cut bias, strata ledges, vertical joints, flat top
  rock.river/1     water-worn stone: few shallow cuts, heavy smoothing, low detail, flat bottom
  rock.pebbles/1   cluster of 5-9 river pebbles on a patch (one mesh, several closed parts)

High-poly = recipe output (for bakes only). LOD0 = QEM decimation of the high to the budget; LOD1/LOD2 decimate
LOD0 (UVs kept). CC0 kit rocks (rubberduck, Quaternius) are references only; no kit mesh is used.
"""
from __future__ import annotations

import math

import numpy as np

import np_lib as L
import np_noise as NZ

RECIPES = {"rock.boulder/1", "rock.cliff/1", "rock.river/1", "rock.pebbles/1"}

DEFAULTS = {
    "rock.boulder/1": dict(embed=0.10, blobs=[{"c": [0, 0, 0], "r": [1, 1, 1]}], hull_points=26, hull_jitter=0.16,
                           cuts=11, cut_depth=[0.04, 0.20], top_bias=0.35, lump_amp=0.035, lump_scale=0.55,
                           chips=24, chip_radius=0.13, chip_depth=0.018, chip_tilt=28.0, crack=0.35,
                           crack_scale=0.42, crack_depth=0.010, crack_width=0.05, strata=0.0, strata_spacing=0.35,
                           strata_warp=0.25, flat_top=0.0, top_level=0.86, lean_deg=0.0, detail_amp=0.0035,
                           pit_amp=0.004, smooth_coarse=3, smooth_final=1, round_bias=0.0, back_flat=0.0),
    "rock.cliff/1": dict(embed=0.06, blobs=[{"c": [0, 0, -0.35], "r": [1.0, 1.0, 0.7]},
                                            {"c": [0.08, 0.05, 0.38], "r": [0.82, 0.86, 0.66]}],
                         hull_points=30, hull_jitter=0.10, cuts=16, cut_depth=[0.03, 0.16], top_bias=0.18,
                         lump_amp=0.025, lump_scale=1.2, chips=34, chip_radius=0.08, chip_depth=0.012,
                         chip_tilt=22.0, crack=0.55, crack_scale=0.9, crack_depth=0.010, crack_width=0.04,
                         strata=0.012, strata_spacing=0.55, strata_warp=0.18, flat_top=0.55, top_level=0.9,
                         lean_deg=0.0, detail_amp=0.0025, pit_amp=0.003, smooth_coarse=2, smooth_final=1,
                         round_bias=0.0, back_flat=0.0),
    "rock.river/1": dict(embed=0.16, hull_points=22, hull_jitter=0.12, cuts=3, cut_depth=[0.02, 0.10], top_bias=0.5,
                         lump_amp=0.03, lump_scale=0.6, smooth_coarse=14, detail_amp=0.0015, pit_amp=0.0025,
                         flat_top=0.0, top_level=0.9),
    "rock.pebbles/1": dict(count=7, radius=0.32, size=[0.06, 0.22], flat=[0.45, 0.75], embed=0.30),
}


def params(recipe, p):
    out = dict(DEFAULTS[recipe])
    out.update(p)
    return out


def _sample_dir(rng, top_bias, vertical=False):
    if rng.random() < top_bias:
        z = rng.uniform(0.55, 1.0)
    else:
        z = rng.uniform(-0.25, 0.30) if vertical else rng.uniform(-0.25, 0.55)
    phi = rng.uniform(0, 2 * math.pi)
    r = math.sqrt(max(0.0, 1 - z * z))
    return np.array([r * math.cos(phi), r * math.sin(phi), z])


def _vox(Lmax, div, lo, hi):
    return float(min(max(Lmax / div, lo), hi))


def _fit_bbox(v, w, d, h, embed):
    mn, mx = v.min(0), v.max(0)
    c = (mn + mx) / 2
    out = v.copy()
    out[:, 0] = (v[:, 0] - c[0]) * (w / max(mx[0] - mn[0], 1e-6))
    out[:, 1] = (v[:, 1] - c[1]) * (d / max(mx[1] - mn[1], 1e-6))
    out[:, 2] = -embed + (v[:, 2] - mn[2]) * ((h + embed) / max(mx[2] - mn[2], 1e-6))
    return out


def _refresh(ob):
    me = ob.data
    me.update()
    return L.verts(me), L.edges(me), L.vnormals(me)


def boulder_high(name, seed, P, cliff=False):
    """High-poly rock (closed, manifold voxel surface). Returns (object, info)."""
    rng = np.random.default_rng(seed)
    w, d, h = (float(x) for x in P["size"])
    Lmax = max(w, d, h)
    embed = P["embed"] * h
    zc = (h - embed) / 2.0
    hz = (h + embed) / 2.0
    parts = []
    for bi, b in enumerate(P["blobs"]):
        R = np.array([w / 2 * b["r"][0], d / 2 * b["r"][1], hz * b["r"][2]])
        C = np.array([w / 2 * b["c"][0], d / 2 * b["c"][1], zc + hz * b["c"][2]])
        dirs = NZ.fibonacci_sphere(int(P["hull_points"]), rng, 0.10)
        rad = 1.0 + rng.uniform(-P["hull_jitter"], P["hull_jitter"], (len(dirs), 1))
        pts = C + dirs * R * rad
        planes = []
        for k in range(int(P["cuts"])):
            dn = _sample_dir(rng, P["top_bias"], vertical=cliff)
            s = L.support(pts - C, dn)
            depth = rng.uniform(*P["cut_depth"])
            planes.append((C + dn * s * (1.0 - depth), dn))
        if P.get("back_flat", 0) > 0:
            planes.append((C + np.array([0, R[1] * (1 - P["back_flat"]), 0]), np.array([0, 1.0, 0])))
        if P.get("front_flat", 0) > 0:
            planes.append((C + np.array([0, -R[1] * (1 - P["front_flat"]), 0]), np.array([0, -1.0, 0])))
        if P.get("planar_only", False) and P.get("flat_top", 0) >= .4:
            planes.append((np.array([0, 0, P["top_level"] * h]), np.array([0, 0, 1.0])))
        planes.append((np.array([0, 0, -embed]), np.array([0, 0, -1.0])))
        hp = L.hull_points_cut(pts, planes)
        parts.append(L.convex_hull_object(f"{name}_blob{bi}", hp))
    ob = L.join(parts, name) if len(parts) > 1 else parts[0]
    ob.name = name
    if P.get("planar_only", False):
        if len(parts) != 1:
            raise ValueError("planar_only requires one closed clipped hull")
        L.set_verts(ob.data, _fit_bbox(L.verts(ob.data), w, d, h, embed))
        L.set_smooth(ob, False)
        return ob, {"embed_m": round(embed, 4), "size_m": [w, d, h],
                    "construction": "seeded clipped convex planes; no micro-noise remesh"}
    # coarse union + soften
    L.remesh(ob, _vox(Lmax, 55, 0.012, 0.06))
    v, e, n = _refresh(ob)
    v = L.taubin(v, e, iters=int(P["smooth_coarse"]))
    # large lumps along the normal
    v = v + n * (P["lump_amp"] * Lmax) * NZ.fbm3(v / P["lump_scale"], seed + 11, 3)[:, None]
    if P.get("lean_deg", 0):
        a = math.radians(P["lean_deg"])
        v[:, 0] += np.tan(a) * np.clip(v[:, 2], 0, None) * 0.9
    L.set_verts(ob.data, v)
    # fine remesh
    L.remesh(ob, _vox(Lmax, 170, 0.008, 0.024))
    v, e, n = _refresh(ob)
    if P.get("round_bias", 0) > 0:
        v = L.taubin(v, e, iters=int(4 + 10 * P["round_bias"]))
        L.set_verts(ob.data, v)
        v, e, n = _refresh(ob)
    # knapped chips on sides/top (not the buried band)
    region = v[:, 2] > 0.05 * h
    v = L.chip_flatten(v, n, rng, int(P["chips"]), P["chip_radius"] * Lmax, P["chip_depth"] * Lmax,
                       P["chip_tilt"], region)
    L.set_verts(ob.data, v)
    v, e, n = _refresh(ob)
    # cracks along cell borders, masked by noise (vertical joints for cliffs)
    if P["crack"] > 0:
        sc = np.array([1.0, 1.0, 2.6 if cliff else 1.0]) * P["crack_scale"]
        f1, f2, cid = NZ.worley3(v / sc, seed + 23, 0.9)
        edge = f2 - f1
        groove = 1.0 - NZ.smoothstep(0.0, P["crack_width"] / P["crack_scale"], edge)
        mask = NZ.smoothstep(1.0 - P["crack"], 1.0 - P["crack"] + 0.25,
                             0.5 + 0.5 * NZ.fbm3(v / (Lmax * 0.6), seed + 29, 2))
        mask *= NZ.smoothstep(0.0, 0.12 * h, v[:, 2])
        v = v - n * (groove * mask * P["crack_depth"] * Lmax)[:, None]
    # strata ledges (horizontal component only)
    if P.get("strata", 0) > 0:
        zz = v[:, 2] + P["strata_warp"] * P["strata_spacing"] * NZ.fbm3(v / 1.4, seed + 31, 2)
        band = np.mod(zz / P["strata_spacing"], 1.0)
        prof = NZ.smoothstep(0.0, 0.22, band) * (1.0 - 0.35 * NZ.smoothstep(0.6, 1.0, band))
        horiz = np.sqrt(np.clip(1.0 - n[:, 2] ** 2, 0, 1))
        v = v - n * ((1.0 - prof) * horiz * P["strata"] * Lmax)[:, None]
    # flat top
    if P.get("flat_top", 0) > 0:
        zt = P["top_level"] * h + 0.015 * Lmax * NZ.fbm3(v / 0.9, seed + 37, 2)
        sel = v[:, 2] > zt
        v[sel, 2] = zt[sel] + (v[sel, 2] - zt[sel]) * (1.0 - P["flat_top"])
    # fine detail and pits (normal map only)
    v = v + n * (P["detail_amp"] * Lmax * NZ.fbm3(v / 0.085, seed + 41, 3))[:, None]
    if P.get("pit_amp", 0) > 0:
        f1, f2, _ = NZ.worley3(v / 0.05, seed + 43, 0.8)
        pits = 1.0 - NZ.smoothstep(0.0, 0.32, f1)
        pm = NZ.smoothstep(0.1, 0.5, NZ.fbm3(v / 0.4, seed + 47, 2))
        v = v - n * (pits * pm * P["pit_amp"] * Lmax)[:, None]
    L.set_verts(ob.data, v)
    v, e, n = _refresh(ob)
    v = L.taubin(v, e, iters=int(P["smooth_final"]), lam=0.33, mu=-0.34)
    v[:, 2] = np.maximum(v[:, 2], v[:, 2].min() + 0.0)  # keep
    v = _fit_bbox(v, w, d, h, embed)
    v[:, 2] = np.maximum(v[:, 2], -embed)
    L.set_verts(ob.data, v)
    L.set_smooth(ob)
    return ob, {"embed_m": round(embed, 4), "size_m": [w, d, h]}


def river_high(name, seed, P):
    rng = np.random.default_rng(seed)
    w, d, h = (float(x) for x in P["size"])
    Lmax = max(w, d, h)
    embed = P["embed"] * h
    hz = (h + embed) / 2
    C = np.array([0, 0, (h - embed) / 2])
    R = np.array([w / 2, d / 2, hz])
    dirs = NZ.fibonacci_sphere(int(P["hull_points"]), rng, 0.12)
    pts = C + dirs * R * (1.0 + rng.uniform(-P["hull_jitter"], P["hull_jitter"], (len(dirs), 1)))
    planes = []
    for k in range(int(P["cuts"])):
        dn = _sample_dir(rng, P["top_bias"])
        s = L.support(pts - C, dn)
        planes.append((C + dn * s * (1 - rng.uniform(*P["cut_depth"])), dn))
    planes.append((np.array([0, 0, -embed]), np.array([0, 0, -1.0])))
    ob = L.convex_hull_object(name, L.hull_points_cut(pts, planes))
    L.remesh(ob, _vox(Lmax, 60, 0.006, 0.03))
    v, e, n = _refresh(ob)
    v = L.taubin(v, e, iters=int(P["smooth_coarse"]))
    v = v + n * (P["lump_amp"] * Lmax) * NZ.fbm3(v / P["lump_scale"], seed + 11, 3)[:, None]
    L.set_verts(ob.data, v)
    L.remesh(ob, _vox(Lmax, 150, 0.004, 0.02))
    v, e, n = _refresh(ob)
    v = L.taubin(v, e, iters=3)
    v = v + n * (P["detail_amp"] * Lmax * NZ.fbm3(v / 0.06, seed + 41, 3))[:, None]
    f1, f2, _ = NZ.worley3(v / 0.035, seed + 43, 0.8)
    pits = 1.0 - NZ.smoothstep(0.0, 0.3, f1)
    pm = NZ.smoothstep(0.2, 0.6, NZ.fbm3(v / 0.3, seed + 47, 2))
    v = v - n * (pits * pm * P["pit_amp"] * Lmax)[:, None]
    v = _fit_bbox(v, w, d, h, embed)
    v[:, 2] = np.maximum(v[:, 2], -embed)
    L.set_verts(ob.data, v)
    L.set_smooth(ob)
    return ob, {"embed_m": round(embed, 4), "size_m": [w, d, h]}


def pebbles_high(name, seed, P):
    rng = np.random.default_rng(seed)
    parts = []
    placed = []
    for i in range(int(P["count"])):
        s = rng.uniform(*P["size"])
        for _try in range(30):
            ang = rng.uniform(0, 2 * math.pi)
            r = P["radius"] * math.sqrt(rng.uniform(0, 1))
            c = np.array([r * math.cos(ang), r * math.sin(ang)])
            if all(np.linalg.norm(c - q) > 0.5 * (s + qs) for q, qs in placed):
                break
        placed.append((c, s))
        flat = rng.uniform(*P["flat"])
        sub = dict(DEFAULTS["rock.river/1"])
        sub.update(size=[s, s * rng.uniform(0.7, 0.95), s * flat], embed=P["embed"], smooth_coarse=10)
        ob, _ = river_high(f"{name}_p{i}", seed * 31 + i, sub)
        v = L.verts(ob.data)
        a = rng.uniform(0, 2 * math.pi)
        rot = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
        v = v @ rot.T + np.array([c[0], c[1], 0])
        L.set_verts(ob.data, v)
        parts.append(ob)
    ob = L.join(parts, name)
    L.set_smooth(ob)
    v = L.verts(ob.data)
    mn, mx = v.min(0), v.max(0)
    return ob, {"embed_m": round(float(-mn[2]), 4), "size_m": [float(mx[0] - mn[0]), float(mx[1] - mn[1]), float(mx[2])]}


def build_high(spec):
    recipe = spec["recipe"]
    P = params(recipe, spec["params"])
    name = spec["id"] + "__high"
    if recipe == "rock.boulder/1":
        return boulder_high(name, spec["seed"], P, cliff=False) + (P,)
    if recipe == "rock.cliff/1":
        return boulder_high(name, spec["seed"], P, cliff=True) + (P,)
    if recipe == "rock.river/1":
        return river_high(name, spec["seed"], P) + (P,)
    if recipe == "rock.pebbles/1":
        return pebbles_high(name, spec["seed"], P) + (P,)
    raise ValueError(recipe)
