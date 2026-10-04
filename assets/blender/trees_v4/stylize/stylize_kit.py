"""Route A step 2 (trees v4): stylize the 7 Quaternius CC0 picks in Blender 5.2.2, headless.

Art direction on a CC0 kit, not a generator. Every model is imported from the kit glTF into an empty
factory scene (an in-memory copy; the kit folder is never written), then:

  1. normalise   - uniform scale to the slot height (decision doc 4.1), pivot at the trunk's ground contact;
  2. shape       - crown-base lowering (piecewise Z map of the bare trunk), broadleaf crown widening to the
                   W/H target (cards move rigidly, limbs follow), conifer skirt narrowing, Pine_2 trunk +25 %,
                   root flare with buttress lobes (ring cuts + flare factor solved against the measured ratio),
                   extra clumps (copies of the tree's own clumps) / denser conifer tiers, inner-card culling;
  3. atlas       - every leaf card is re-mapped into a cell of the painted cluster atlas (Claude forge), with
                   the cluster's +V rotated to world up; conifer fronds keep their outline-matched UVs inside a
                   frond cell; the flowering bush gets red flower quads mapped to the blossom cell;
  4. COLOR_0     - foliage 0.55-0.70 inside/underside -> 1.0 top/outside, +/-4 % hue per clump; bark base
                   ramp lifted from 0.10 to >= 0.55;
  5. normals     - Data Transfer modifier (Face Corner Data -> Custom Normals, nearest face interpolated,
                   mix 0.9) from one ellipsoid proxy per clump (broadleaf, bush) or one cone per tier (conifer),
                   after every card has been turned to face outward;
  6. wind        - second UV map -> TEXCOORD_1: x = sway weight (0 at ground -> 1 at the tips),
                   y = per-clump phase (stored as 1 - phase in Blender because the exporter writes v as 1 - v);
  7. budgets     - bark decimated first (Collapse), then card counts; LOD1 = stronger bark decimation + the
                   outermost cards scaled up to keep coverage;
  8. export      - 2 materials "<species>_bark" (opaque) and "<species>_foliage" (MASK 0.45, double-sided),
                   through the shared export helper (assets/blender/tools/export_helper.py, profile "foliage",
                   budget classes tree_lod0/1 or bush_lod0/1): every glTF option explicit, re-import validation,
                   a receipt per GLB, images external and deduplicated in <out>/textures-shared/, no meshopt /
                   Draco (compression happens in apps/client/scripts/gltf-postprocess.mjs; see run_pass.py).
                   Migrated 2026-10-02 (C-P1-TREE, docs/reviews/2026-10-02-export-helper.md section 7.1).

Usage:
  blender -b --factory-startup --python-exit-code 1 --python stylize_kit.py -- --src <kit glTF dir>
      --atlas <png> --layout <layout.json> --bark-albedo <png> --bark-normal <png> --out <export dir>
      --report <json> [--models A,B] [--params <json file>] [--tag pass1]
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

# One glTF export path for every Blender builder (docs/reviews/2026-10-02-export-helper.md section 7.1).
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "assets" / "blender" / "tools"))
from export_helper import export_glb as xex_export_glb  # noqa: E402

PICKS = {
    "CommonTree_2": {"species": "qn_broadleaf_s", "kind": "broadleaf", "slot": "broadleaf S", "height": 5.5,
                     "trunk_min": 0.25},
    "CommonTree_5": {"species": "qn_broadleaf_m", "kind": "broadleaf", "slot": "broadleaf M", "height": 7.5,
                     "trunk_min": 0.32},
    "CommonTree_1": {"species": "qn_broadleaf_l", "kind": "broadleaf", "slot": "broadleaf L", "height": 9.5,
                     "trunk_min": 0.42},
    "Pine_2": {"species": "qn_conifer_m", "kind": "conifer", "slot": "conifer M", "height": 8.0, "trunk_min": 0.22},
    "Pine_5": {"species": "qn_conifer_l", "kind": "conifer", "slot": "conifer L", "height": 12.0, "trunk_min": 0.30},
    "Bush_Common_Flowers": {"species": "qn_bush_flowers", "kind": "bush", "slot": "bush", "height": 1.2},
    "Bush_Common": {"species": "qn_bush", "kind": "bush", "slot": "bush", "height": 1.2},
}
SPEC = {"broadleaf": {"crown_base": (2.2, 3.0), "wh": (0.8, 1.1), "flare": (1.8, 2.2), "lod0": (4000, 6000),
                      "lod1_max": 1600},
        "conifer": {"crown_base": (1.6, 2.4), "wh": (0.45, 0.6), "flare": (1.6, 1.6), "lod0": (2500, 5000),
                    "lod1_max": 1400},
        "bush": {"lod0": (300, 900), "lod1_max": 450}}
# per-model recipe (pass 1 defaults; --params overrides per model or under "_all")
RECIPE = {
    "CommonTree_2": dict(crown_base_to=None, wh_target=0.86, card_scale=1.12, add_clumps=2, clumps=6,
                         bark_ratio=0.62, flare=2.0, buttresses=5, delete_inner=0.0, lod1_bark=520),
    "CommonTree_5": dict(crown_base_to=2.8, wh_target=0.84, card_scale=1.10, add_clumps=3, clumps=7,
                         bark_ratio=1.0, flare=2.0, buttresses=5, delete_inner=0.0, lod1_bark=520),
    "CommonTree_1": dict(crown_base_to=2.6, wh_target=0.85, card_scale=1.08, add_clumps=2, clumps=8,
                         bark_ratio=0.58, flare=2.0, buttresses=6, delete_inner=0.10, lod1_bark=520),
    "Pine_2": dict(crown_base_to=None, narrow=0.84, trunk_scale=1.25, flare=1.6, buttresses=4, bark_ratio=0.6,
                   frond_dup=True, tiers=6, lod1_bark=420, remove_low_limbs=True),
    "Pine_5": dict(crown_base_to=2.2, narrow=0.86, trunk_scale=1.0, flare=1.6, buttresses=4, bark_ratio=1.0,
                   frond_dup=True, tiers=7, lod1_bark=380, remove_low_limbs=False),
    "Bush_Common_Flowers": dict(clumps=3, keep_cards=390, flower_quads=True, blossom_share=0.22),
    "Bush_Common": dict(clumps=3, keep_cards=330, flower_quads=False, blossom_share=0.0),
}
GLOBAL = dict(c0_min=0.55, c0_gamma=1.0, c0_w_out=0.45, c0_w_top=0.35, c0_w_h=0.20, hue_shift=0.04,
              normal_mix=0.9, alpha_cutoff=0.45, seed=11, bark_c0_min=0.55, roughness_foliage=0.9,
              roughness_bark=0.95, conifer_cells="C1_frond,C2_frond", card_tilt_deg=35.0)
BROAD_CELLS = ["B1_rosette", "B2_spray", "B3_dense", "B4_fan", "B6_loose"]
BUSH_CELLS = [("B5_bush", 0.6), ("B3_dense", 0.25), ("B1_rosette", 0.15)]
LOG = []


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.append(msg)
    print(msg, flush=True)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--atlas", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--bark-albedo", required=True)
    ap.add_argument("--bark-normal", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--models", default=",".join(PICKS))
    ap.add_argument("--params", default="")
    ap.add_argument("--tag", default="")
    a, _ = ap.parse_known_args(argv)
    return a


# ----------------------------------------------------------------------------------------------- helpers

def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / max(e1 - e0, 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def kmeans(X, k, rng, iters=60):
    X = np.asarray(X, np.float64)
    n = len(X)
    k = max(1, min(k, n))
    C = [X[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min(((X[:, None, :] - np.array(C)[None]) ** 2).sum(-1), axis=1)
        C.append(X[rng.choice(n, p=d2 / d2.sum())] if d2.sum() > 0 else X[rng.integers(n)])
    C = np.array(C)
    lab = np.zeros(n, int)
    for _ in range(iters):
        lab = np.argmin(((X[:, None] - C[None]) ** 2).sum(-1), axis=1)
        newC = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return lab, C


def mesh_co(me):
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def set_co(me, co):
    me.vertices.foreach_set("co", np.asarray(co, np.float32).ravel())
    me.update()


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def convex_hull_area(points):
    pts = sorted(set(map(tuple, np.round(points, 6))))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return 0.5 * abs(sum(hull[i][0] * hull[(i + 1) % len(hull)][1] - hull[(i + 1) % len(hull)][0] * hull[i][1]
                         for i in range(len(hull))))


def sections(me, heights, co=None):
    """Cross-sections of a bark mesh (same method as measure_kit.py): bisect, connected cut loops,
    convex-hull equivalent radius; the largest loop is the main stem."""
    bm = bmesh.new()
    bm.from_mesh(me)
    if co is not None:
        bm.verts.ensure_lookup_table()
        for v, c in zip(bm.verts, co):
            v.co = c
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    out = []
    for h in heights:
        res = bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), dist=1e-5,
                                     plane_co=(0, 0, h), plane_no=(0, 0, 1))
        cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        cut_set, seen, loops = set(cut), set(), []
        for e in cut:
            if e in seen:
                continue
            stack, comp = [e], []
            seen.add(e)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for v in cur.verts:
                    for e2 in v.link_edges:
                        if e2 in cut_set and e2 not in seen:
                            seen.add(e2)
                            stack.append(e2)
            pts = np.array([[v.co.x, v.co.y] for ed in comp for v in ed.verts])
            area = convex_hull_area(pts)
            if area > 0:
                loops.append({"r": math.sqrt(area / math.pi), "c": pts.mean(0), "n": len(comp)})
        loops.sort(key=lambda l: l["r"], reverse=True)
        m = loops[0] if loops else None
        out.append({"h": h, "loops": len(loops), "loops_r_over_5cm": sum(1 for l in loops if l["r"] >= 0.05),
                    "r": m["r"] if m else None, "c": m["c"].tolist() if m else None, "edges": m["n"] if m else 0})
    bm.free()
    return out


class TrunkModel:
    """Trunk centre and radius by height, from cross-sections (linear interpolation, clamped)."""

    def __init__(self, secs):
        good = [s for s in secs if s["r"]]
        self.h = np.array([s["h"] for s in good])
        self.r = np.array([s["r"] for s in good])
        self.c = np.array([s["c"] for s in good])

    def centre(self, z):
        z = np.asarray(z, np.float64)
        return np.stack([np.interp(z, self.h, self.c[:, 0]), np.interp(z, self.h, self.c[:, 1])], -1)

    def radius(self, z):
        return np.interp(np.asarray(z, np.float64), self.h, self.r)


def shape_metrics(bark_me, fol_co, height, kind):
    m = {}
    if bark_me is not None and len(bark_me.vertices):
        secs = sections(bark_me, [0.05, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0])
        by = {s["h"]: s for s in secs}
        r1, r0 = by[1.0]["r"], by[0.05]["r"]
        m["trunk_r_1m_m"] = round(r1, 3) if r1 else None
        m["trunk_r_ground_m"] = round(r0, 3) if r0 else None
        m["flare_ground_over_1m"] = round(r0 / r1, 2) if r0 and r1 else None
        m["first_split_m"] = next((s["h"] for s in secs if s["loops_r_over_5cm"] >= 2), None)
        m["ring_edges_at_0p25m"] = by[0.25]["edges"]
    if fol_co is not None and len(fol_co):
        ext = fol_co[:, :2].max(0) - fol_co[:, :2].min(0)
        m["crown_base_p5_m"] = round(float(np.percentile(fol_co[:, 2], 5)), 3)
        m["crown_top_m"] = round(float(fol_co[:, 2].max()), 3)
        m["crown_width_m"] = round(float(ext.mean()), 3)
        m["crown_width_over_height"] = round(float(ext.mean()) / height, 3)
    return m


def bm_islands(bm):
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    visited = np.zeros(len(bm.faces), bool)
    out = []
    for f in bm.faces:
        if visited[f.index]:
            continue
        stack, comp = [f], []
        visited[f.index] = True
        while stack:
            g = stack.pop()
            comp.append(g)
            for v in g.verts:
                for h in v.link_faces:
                    if not visited[h.index]:
                        visited[h.index] = True
                        stack.append(h)
        out.append(comp)
    return out


def island_verts(comp):
    return list({v for f in comp for v in f.verts})


def island_centroid(comp):
    vs = island_verts(comp)
    return np.mean([tuple(v.co) for v in vs], axis=0)


def island_normal(comp):
    n = Vector((0, 0, 0))
    for f in comp:
        n += f.normal * f.calc_area()
    return np.array(n.normalized()) if n.length > 1e-12 else np.array([0, 0, 1.0])


def island_area(comp):
    return sum(f.calc_area() for f in comp)


# ----------------------------------------------------------------------------------------------- import

def import_kit(src, name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(src, name + ".gltf"))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"{name}: expected one mesh object, got {len(meshes)}")
    ob = meshes[0]
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.data.transform(mw)
    ob.matrix_world = Matrix.Identity(4)
    for o in list(bpy.data.objects):
        if o != ob:
            bpy.data.objects.remove(o, do_unlink=True)
    return ob


def split_kinds(ob):
    me = ob.data
    kinds = []
    for m in me.materials:
        n = m.name if m else ""
        kinds.append("bark" if n.startswith("Bark") else ("flower" if n.startswith("Flowers") else "leaf"))
    parts = {}
    for want, label in ((("bark",), "bark"), (("leaf", "flower"), "foliage")):
        if not any(k in want for k in kinds):
            parts[label] = None
            continue
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if kinds[f.material_index] not in want], context="FACES")
        for f in bm.faces:
            f.material_index = 1 if kinds[f.material_index] == "flower" else 0
        nm = bpy.data.meshes.new(f"{ob.name}_{label}")
        bm.to_mesh(nm)
        bm.free()
        o = bpy.data.objects.new(nm.name, nm)
        bpy.context.scene.collection.objects.link(o)
        parts[label] = o
    src_mats = {k: [m.name for m, kk in zip(me.materials, kinds) if kk == k] for k in ("bark", "leaf", "flower")}
    bpy.data.objects.remove(ob, do_unlink=True)
    return parts, src_mats


def read_color(me):
    """Per-corner linear RGBA of the kit's colour attribute (or ones)."""
    n = len(me.loops)
    if not me.color_attributes:
        return np.ones((n, 4))
    attr = me.color_attributes[0]
    buf = np.empty((len(attr.data)) * 4, np.float32)
    attr.data.foreach_get("color", buf)
    buf = buf.reshape(-1, 4)
    if attr.domain == "POINT":
        vi = np.empty(n, np.int32)
        me.loops.foreach_get("vertex_index", vi)
        buf = buf[vi]
    return buf.astype(np.float64)


def write_color(me, rgba):
    for a in list(me.color_attributes):
        me.color_attributes.remove(a)
    attr = me.color_attributes.new("Color", "FLOAT_COLOR", "CORNER")
    attr.data.foreach_set("color", np.asarray(rgba, np.float32).ravel())
    me.color_attributes.active_color = attr
    try:
        me.color_attributes.render_color_index = 0
    except Exception:
        pass


def ensure_uv_names(me):
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    me.uv_layers[0].name = "UVMap"
    while len(me.uv_layers) > 1:
        me.uv_layers.remove(me.uv_layers[-1])


def write_wind(me, sway_loop, phase_loop):
    ensure_uv_names(me)
    uv = me.uv_layers.new(name="wind")
    arr = np.stack([np.clip(sway_loop, 0, 1), 1.0 - np.clip(phase_loop, 0, 0.999)], -1)
    uv.uv.foreach_set("vector", arr.astype(np.float32).ravel())
    me.uv_layers[0].active_render = True
    me.uv_layers.active_index = 0


def loop_vertex_index(me):
    vi = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", vi)
    return vi


def clear_custom_normals(ob):
    me = ob.data
    try:
        if "custom_normal" in me.attributes:
            me.attributes.remove(me.attributes["custom_normal"])
    except Exception:
        pass
    try:
        bpy.context.view_layer.objects.active = ob
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except Exception:
        pass
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    me.update()


def apply_modifier(ob, mod):
    bpy.context.view_layer.objects.active = ob
    with bpy.context.temp_override(object=ob, active_object=ob):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def decimate(ob, ratio):
    if ratio >= 0.999:
        return
    mod = ob.modifiers.new("decimate", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = float(ratio)
    mod.use_collapse_triangulate = True
    apply_modifier(ob, mod)


def triangulate(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(ob.data)
    bm.free()


def weld(ob, dist=1e-4):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bm.to_mesh(ob.data)
    bm.free()


# ----------------------------------------------------------------------------------------------- shape

def zmap(z, cb_from, cb_to, top):
    z = np.asarray(z, np.float64)
    if cb_to is None or cb_from is None or cb_from <= cb_to:
        return z
    low = z * (cb_to / cb_from)
    high = cb_to + (z - cb_from) * (top - cb_to) / (top - cb_from)
    return np.where(z <= cb_from, low, high)


def radial(p, F, c_xy, r0, z_a, z_b):
    """Radial widening/narrowing about c_xy beyond r0, ramped in over z_a..z_b."""
    p = np.array(p, np.float64, copy=True)
    d = p[..., :2] - c_xy
    r = np.linalg.norm(d, axis=-1)
    w = smoothstep(z_a, z_b, p[..., 2])
    rn = r + (F - 1.0) * np.maximum(0.0, r - r0) * w
    scale = np.where(r > 1e-9, rn / np.maximum(r, 1e-9), 1.0)
    p[..., :2] = c_xy + d * scale[..., None]
    return p


def flare_coords(co, trunk, K, n_lobes, theta0, h_f, lobe_amp=0.28):
    co = np.array(co, np.float64, copy=True)
    z = co[:, 2]
    c = trunk.centre(np.clip(z, 0.0, None))
    rt = trunk.radius(np.clip(z, 0.05, None))
    d = co[:, :2] - c
    r = np.linalg.norm(d, axis=1)
    g = np.where(z <= 0, 1.0, np.clip(1 - z / h_f, 0, 1) ** 2)
    th = np.arctan2(d[:, 1], d[:, 0])
    b = 1.0 + lobe_amp * np.cos(n_lobes * (th - theta0))
    m_r = 1.0 - smoothstep(1.4, 2.4, r / np.maximum(rt, 1e-3))
    k = 1.0 + (K - 1.0) * g * b * m_r
    co[:, :2] = c + d * k[:, None]
    return co


def add_rings(ob, trunk, heights):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    added = 0
    for h in heights:
        c = trunk.centre(h)
        rt = trunk.radius(max(h, 0.05))
        faces = []
        for f in bm.faces:
            zs = [v.co.z for v in f.verts]
            if min(zs) < h - 1e-4 and max(zs) > h + 1e-4:
                fc = f.calc_center_median()
                if math.hypot(fc.x - c[0], fc.y - c[1]) < 2.6 * rt:
                    faces.append(f)
        if not faces:
            continue
        edges = list({e for f in faces for e in f.edges})
        verts = list({v for f in faces for v in f.verts})
        n0 = len(bm.verts)
        bmesh.ops.bisect_plane(bm, geom=verts + edges + faces, dist=1e-5, plane_co=(0, 0, h), plane_no=(0, 0, 1))
        added += len(bm.verts) - n0
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(ob.data)
    bm.free()
    return added


def solve_flare(ob, trunk, target, n_lobes, theta0, h_f):
    me = ob.data
    co0 = mesh_co(me)
    lo, hi, best = 1.0, 3.5, None
    for _ in range(14):
        K = 0.5 * (lo + hi)
        co = flare_coords(co0, trunk, K, n_lobes, theta0, h_f)
        s = sections(me, [0.05, 1.0], co)
        if not s[0]["r"] or not s[1]["r"]:
            break
        ratio = s[0]["r"] / s[1]["r"]
        best = (K, ratio)
        if abs(ratio - target) < 0.01:
            break
        if ratio < target:
            lo = K
        else:
            hi = K
    if best is None:
        return None
    set_co(me, flare_coords(co0, trunk, best[0], n_lobes, theta0, h_f))
    return {"K": round(best[0], 4), "ratio": round(best[1], 3), "lobes": n_lobes, "h_f_m": h_f}


# ----------------------------------------------------------------------------------------------- materials

def socket(node, name, kind):
    for s in node.inputs:
        if s.name == name and s.type == kind:
            return s
    return node.inputs[name]


def out_socket(node, name, kind):
    for s in node.outputs:
        if s.name == name and s.type == kind:
            return s
    return node.outputs[name]


def make_material(name, albedo, normal=None, cutoff=None, double_sided=True, roughness=0.9):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = albedo
    tex.interpolation = "Linear"
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Color"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    socket(mix, "Factor", "VALUE").default_value = 1.0
    nt.links.new(tex.outputs["Color"], socket(mix, "A", "RGBA"))
    nt.links.new(vc.outputs["Color"], socket(mix, "B", "RGBA"))
    nt.links.new(out_socket(mix, "Result", "RGBA"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if normal is not None:
        ntex = nt.nodes.new("ShaderNodeTexImage")
        ntex.image = normal
        ntex.interpolation = "Linear"
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.space = "TANGENT"
        nmap.uv_map = "UVMap"
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    if cutoff is not None:
        lt = nt.nodes.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        nt.links.new(tex.outputs["Alpha"], lt.inputs[0])
        lt.inputs[1].default_value = cutoff
        sub = nt.nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[0].default_value = 1.0
        nt.links.new(lt.outputs["Value"], sub.inputs[1])
        nt.links.new(sub.outputs["Value"], bsdf.inputs["Alpha"])
    mat.use_backface_culling = not double_sided
    # The export helper decides double-sidedness by policy; this keeps the builder's choice (bark is
    # double-sided only when it has open edges, foliage cards always are).
    mat["xex_double_sided"] = bool(double_sided)
    return mat


def load_image(path, colorspace):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = colorspace
    img.alpha_mode = "STRAIGHT"
    return img


# ----------------------------------------------------------------------------------------------- atlas

def find_flowers(img, rect, rng):
    W, H = img.size
    px = np.empty(W * H * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H, W, 4)
    u0, v0, u1, v1 = rect
    c0, c1, r0, r1 = int(u0 * W), int(u1 * W), int(v0 * H), int(v1 * H)
    sub = px[r0:r1, c0:c1]
    R, G, B, A = sub[..., 0], sub[..., 1], sub[..., 2], sub[..., 3]
    centre = (A > 0.5) & (R > 0.75) & (G > 0.5) & (B < 0.45) & (G < R)
    ys, xs = np.nonzero(centre)
    if len(xs) < 30:
        return []
    lab, C = kmeans(np.stack([xs, ys], 1), 3, rng)
    petal = (A > 0.5) & (R > 0.45) & (G < 0.55 * R) & (B < 0.6 * R)
    py, pxs = np.nonzero(petal)
    P = np.stack([pxs, py], 1).astype(np.float64)
    out = []
    for j in range(len(C)):
        d = np.linalg.norm(P - C[j], axis=1)
        near = d[d < 70]
        rad = min(float(np.percentile(near, 60)) if len(near) > 20 else 28.0, 34.0)
        out.append({"u": (c0 + C[j][0] + 0.5) / W, "v": (r0 + C[j][1] + 0.5) / H, "half": 1.15 * rad / W,
                    "radius_px": round(rad, 1), "centre_px": [int(c0 + C[j][0]), int(r0 + C[j][1])]})
    return out


def best_orientation(P, ST):
    """P: 3 positions, ST: 3 normalised (s,t). Returns (k rotations, mirror) whose painted +t points most up."""
    n = np.cross(P[1] - P[0], P[2] - P[0])
    nn = np.linalg.norm(n)
    if nn < 1e-12:
        return 0, False, 0.0
    n = n / nn
    up = np.array([0, 0, 1.0]) - n * n[2]
    if np.linalg.norm(up) < 1e-6:
        return 0, False, 0.0
    up /= np.linalg.norm(up)
    best = (0, False, -9.0)
    for mirror in (False, True):
        for k in range(4):
            st = np.array([xform_st(s, t, k, mirror) for s, t in ST])
            E = np.array([[st[1, 0] - st[0, 0], st[2, 0] - st[0, 0]], [st[1, 1] - st[0, 1], st[2, 1] - st[0, 1]]])
            if abs(np.linalg.det(E)) < 1e-12:
                continue
            J = np.stack([P[1] - P[0], P[2] - P[0]], 1) @ np.linalg.inv(E)
            dt = J[:, 1]
            if np.linalg.norm(dt) < 1e-12:
                continue
            score = float(dt @ up / np.linalg.norm(dt))
            if score > best[2] + 1e-6:
                best = (k, mirror, score)
    return best


def xform_st(s, t, k, mirror):
    x, y = s - 0.5, t - 0.5
    if mirror:
        x = -x
    for _ in range(k):
        x, y = -y, x
    return x + 0.5, y + 0.5


# ----------------------------------------------------------------------------------------------- foliage

def process_foliage(fol_ob, cfg, rec, G, crown, trunk, layout, flowers_uv, rng, kind):
    """All topology/UV work on the foliage in one bmesh session. Returns per-vertex data for the next steps."""
    bm = bmesh.new()
    bm.from_mesh(fol_ob.data)
    info = {}
    uv_layer = bm.loops.layers.uv.active or bm.loops.layers.uv[0]
    if kind == "conifer":
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)   # frond pieces -> one island per frond
    # flowers -> recorded, removed
    flower_rec = []
    fl_faces = [f for f in bm.faces if f.material_index == 1]
    if fl_faces:
        bm_fl = bm.copy()
        bmesh.ops.delete(bm_fl, geom=[f for f in bm_fl.faces if f.material_index != 1], context="FACES")
        for comp in bm_islands(bm_fl):
            c = island_centroid(comp)
            nrm = island_normal(comp)
            vs = np.array([tuple(v.co) for v in island_verts(comp)])
            size = float(np.max(np.linalg.norm(vs - c, axis=1))) * 2
            flower_rec.append((c, nrm, size))
        bm_fl.free()
        bmesh.ops.delete(bm, geom=fl_faces, context="FACES")
    info["flowers_in_kit"] = len(flower_rec)
    top, cb_from, cb_to = crown["top"], crown["cb_from"], crown["cb_to"]
    # ---- shape
    if kind == "broadleaf":
        islands = bm_islands(bm)
        vlists = [island_verts(isl) for isl in islands]
        flat_v = [v for vs in vlists for v in vs]
        V = np.array([tuple(v.co) for v in flat_v])
        I = np.repeat(np.arange(len(vlists)), [len(vs) for vs in vlists])
        cents = np.zeros((len(vlists), 3))
        np.add.at(cents, I, V)
        cents /= np.bincount(I)[:, None]
        cents_z = cents.copy()
        cents_z[:, 2] = zmap(cents[:, 2], cb_from, cb_to, top)
        c_xy = crown["c_xy"]
        z_a, z_b = crown["w_za"], crown["w_zb"]

        def moved(F):
            c1 = radial(cents_z, F, c_xy, crown["r0"], z_a, z_b)
            return c1[I] + (V - cents[I]) * rec["card_scale"]
        lo, hi = 1.0, 3.0
        for _ in range(24):
            F = 0.5 * (lo + hi)
            pts = moved(F)
            ext = pts[:, :2].max(0) - pts[:, :2].min(0)
            if ext.mean() / cfg["height"] < rec["wh_target"]:
                lo = F
            else:
                hi = F
        F = 0.5 * (lo + hi)
        for v, p in zip(flat_v, moved(F)):
            v.co = Vector(p)
        info["widen_F"] = round(F, 4)
        crown["F"] = F
    elif kind == "conifer":
        co = np.array([tuple(v.co) for v in bm.verts])
        co[:, 2] = zmap(co[:, 2], cb_from, cb_to, top)
        co = radial(co, rec["narrow"], crown["axis_xy"], 0.25, 0.5, 1.3)
        for v, c in zip(bm.verts, co):
            v.co = Vector(c)
        crown["F"] = rec["narrow"]
    # ---- extra clumps (broadleaf) / denser tiers (conifer)
    dup_mark = set()
    if kind == "broadleaf" and rec["add_clumps"] > 0:
        islands = bm_islands(bm)
        cents = np.array([island_centroid(c) for c in islands])
        lab, C = kmeans(cents, 4, rng)
        cbe, tp = crown["cb_to_eff"], top
        cands = []
        rad_all = np.linalg.norm(cents[:, :2] - crown["c_xy"], axis=1)
        for f_z in (0.16, 0.30, 0.46):
            z = cbe + f_z * (tp - cbe)
            band = np.abs(cents[:, 2] - z) < 0.9
            R = float(np.percentile(rad_all[band], 70)) if band.sum() > 10 else float(np.percentile(rad_all, 60))
            for th in np.radians(np.arange(0, 360, 30) + rng.uniform(0, 30)):
                p = np.array([crown["c_xy"][0] + 0.85 * R * math.sin(th), crown["c_xy"][1] + 0.85 * R * math.cos(th), z])
                gap = float(np.min(np.linalg.norm(cents - p, axis=1)))
                cands.append((gap, p))
        cands.sort(key=lambda x: -x[0])
        picks = []
        for gap, p in cands:
            if all(np.linalg.norm(p - q) > 1.8 for q in picks):
                picks.append(p)
            if len(picks) >= rec["add_clumps"]:
                break
        added = []
        for p in picks:
            j = int(np.argmin(np.linalg.norm(C - p, axis=1)))
            src = [isl for isl, l in zip(islands, lab) if l == j]
            faces = [f for isl in src for f in isl]
            res = bmesh.ops.duplicate(bm, geom=faces)
            new_v = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
            new_f = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
            ang = rng.uniform(0.7, 2.4) * (1 if rng.random() < 0.5 else -1)
            sc = rng.uniform(0.78, 0.9)
            rot = Matrix.Rotation(ang, 3, "Z")
            for v in new_v:
                d = Vector(np.array(v.co) - C[j])
                v.co = Vector(p) + (rot @ d) * sc
            for f in new_f:
                dup_mark.add(f)
            added.append({"at_m": [round(float(x), 2) for x in p], "from_clump": j, "cards": len(src),
                          "rot_deg": round(math.degrees(ang), 1), "scale": round(sc, 3)})
        info["added_clumps"] = added
    if kind == "conifer" and rec.get("frond_dup"):
        islands = bm_islands(bm)
        n_fr = len(islands)
        per_tier = max(3.0, n_fr / rec["tiers"])
        base_ang = math.pi / per_tier
        ax = crown["axis_xy"]
        dup_faces = []
        for isl in islands:
            res = bmesh.ops.duplicate(bm, geom=isl)
            new_v = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
            new_f = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
            ang = base_ang * rng.uniform(0.75, 1.25) * (1 if rng.random() < 0.5 else -1)
            ca, sa = math.cos(ang), math.sin(ang)
            dz = -rng.uniform(0.08, 0.22)
            for v in new_v:
                x, y = v.co.x - ax[0], v.co.y - ax[1]
                x, y = ca * x - sa * y, sa * x + ca * y
                v.co = Vector((ax[0] + 0.94 * x, ax[1] + 0.94 * y, v.co.z + dz))
            dup_faces.extend(new_f)
        for f in dup_faces:
            dup_mark.add(f)
        info["fronds"] = n_fr
        info["fronds_duplicated"] = n_fr
        info["dup_rotation_deg_mean"] = round(math.degrees(base_ang), 1)
    # ---- clumps / tiers
    islands = bm_islands(bm)
    cents = np.array([island_centroid(c) for c in islands])

    def clump_fit(islands, cents):
        if kind == "conifer":
            lab, C = kmeans(cents[:, 2:3], rec["tiers"], rng)
            order = np.argsort(C[:, 0])
            remap = {int(o): i for i, o in enumerate(order)}
            lab = np.array([remap[int(l)] for l in lab])
            tiers = []
            for t in range(len(order)):
                vs = np.array([tuple(v.co) for isl, l in zip(islands, lab) if l == t for v in island_verts(isl)])
                cz = trunk.centre(np.clip(vs[:, 2], 0, None))
                rr = np.linalg.norm(vs[:, :2] - cz, axis=1)
                tiers.append({"z_lo": float(np.percentile(vs[:, 2], 4)), "z_hi": float(np.percentile(vs[:, 2], 96)),
                              "R": float(np.percentile(rr, 96)), "axis": trunk.centre(float(vs[:, 2].mean())).tolist(),
                              "n": int((lab == t).sum())})
            return lab, tiers
        lab, C = kmeans(cents, rec["clumps"], rng)
        cl = []
        for j in range(len(C)):
            vs = np.array([tuple(v.co) for isl, l in zip(islands, lab) if l == j for v in island_verts(isl)])
            c = vs.mean(0)
            rad = np.maximum(np.percentile(np.abs(vs - c), 92, axis=0) * 1.08, 0.18 if kind == "bush" else 0.45)
            cl.append({"c": c.tolist(), "r": rad.tolist(), "n": int((lab == j).sum())})
        return lab, cl
    lab, clumps = clump_fit(islands, cents)

    def ell_d(p, j):
        c, r = np.array(clumps[j]["c"]), np.array(clumps[j]["r"])
        return float(np.linalg.norm((p - c) / r))
    # ---- inner-card culling / card budget
    n_del = 0
    if kind != "conifer":
        depth = np.array([ell_d(c, l) for c, l in zip(cents, lab)])
        target = None
        if rec.get("delete_inner", 0) > 0:
            target = int(round(len(islands) * (1 - rec["delete_inner"])))
        if rec.get("keep_cards"):
            target = min(target or 10 ** 9, rec["keep_cards"])
        if target is not None and target < len(islands):
            order = np.argsort(depth)
            kill = set(order[: len(islands) - target].tolist())
            bmesh.ops.delete(bm, geom=[f for i in kill for f in islands[i]], context="FACES")
            n_del = len(kill)
            islands = bm_islands(bm)
            cents = np.array([island_centroid(c) for c in islands])
            lab, clumps = clump_fit(islands, cents)
    info["cards_deleted_inner"] = n_del
    # ---- decision doc 4.2 step 2: cards face outward from their clump proxy with a random tilt <= max_tilt
    #      (removes edge-on cards, which read as streaks / visible planes at 13 m)
    tilt = rec.get("card_tilt_deg", G.get("card_tilt_deg", 35.0))
    if kind != "conifer" and tilt is not None and tilt >= 0:
        dots_before, n_rot = [], 0
        for isl, l in zip(islands, lab):
            vs = island_verts(isl)
            c = np.mean([tuple(v.co) for v in vs], axis=0)
            n = island_normal(isl)
            cc, rr = np.array(clumps[l]["c"]), np.array(clumps[l]["r"])
            out = (c - cc) / (rr * rr)
            if np.linalg.norm(out) < 1e-9:
                continue
            out /= np.linalg.norm(out)
            dots_before.append(abs(float(n @ out)))
            ax = rng.normal(size=3)
            ax -= ax.dot(out) * out
            if np.linalg.norm(ax) < 1e-9:
                continue
            ax /= np.linalg.norm(ax)
            tgt = Matrix.Rotation(math.radians(rng.uniform(0.0, tilt)), 3, Vector(ax)) @ Vector(out)
            q = Vector(n).rotation_difference(tgt)
            cv = Vector(c)
            for v in vs:
                v.co = cv + q @ (v.co - cv)
            n_rot += 1
        bm.normal_update()
        info["cards_reoriented"] = {"count": n_rot, "max_tilt_deg": tilt,
                                    "mean_abs_dot_card_vs_outward_before": round(float(np.mean(dots_before)), 3)
                                    if dots_before else None}
    # ---- face every card outward (proxy-relative), so double-sided lighting never flips the clump normal
    flipped = 0
    for isl, l in zip(islands, lab):
        for f in isl:
            fc = np.array(f.calc_center_median())
            if kind == "conifer":
                t = clumps[l]
                out = np.array([fc[0] - t["axis"][0], fc[1] - t["axis"][1], 0.0])
                nrm = out / max(np.linalg.norm(out), 1e-9)
                h = max(t["z_hi"] - t["z_lo"], 0.3)
                ref = np.array([nrm[0], nrm[1], t["R"] / h])
            else:
                c, r = np.array(clumps[l]["c"]), np.array(clumps[l]["r"])
                ref = (fc - c) / (r * r)
            if np.dot(np.array(f.normal), ref) < 0:
                f.normal_flip()
                flipped += 1
    bm.normal_update()
    info["faces_flipped_outward"] = flipped
    # ---- UV remap into the atlas
    cells = layout["cells"]
    if kind == "conifer":
        names = [n.strip() for n in G["conifer_cells"].split(",")]
    elif kind == "bush":
        names = None
    else:
        names = BROAD_CELLS
    cell_use = {}
    prim = {}
    for idx, (isl, l) in enumerate(zip(islands, lab)):
        if kind == "conifer":
            name = names[int(rng.integers(len(names)))]
            u0, v0, u1, v1 = cells[name]["uv_rect"]
            for f in isl:
                for lp in f.loops:
                    u, v = lp[uv_layer].uv
                    lp[uv_layer].uv = (u0 + u * (u1 - u0), v0 + v * (v1 - v0))
        else:
            if kind == "bush":
                share = rec.get("blossom_share", 0.0)
                if share > 0 and rng.random() < share:
                    name = "BB_blossom"
                else:
                    bc = rec.get("bush_cells", BUSH_CELLS)
                    ws = np.array([w for _, w in bc], np.float64)
                    name = bc[int(rng.choice(len(bc), p=ws / ws.sum()))][0]
            else:
                if l not in prim:
                    prim[l] = names[len(prim) % len(names)]
                name = prim[l] if rng.random() < 0.55 else names[int(rng.integers(len(names)))]
            u0, v0, u1, v1 = cells[name]["uv_rect"]
            loops = [lp for f in isl for lp in f.loops]
            uvs = np.array([tuple(lp[uv_layer].uv) for lp in loops])
            bb0, bb1 = uvs.min(0), uvs.max(0)
            span = np.maximum(bb1 - bb0, 1e-6)
            f_loops = list(isl[0].loops)[:3]
            P = np.array([tuple(lp.vert.co) for lp in f_loops])
            ST = [tuple((np.array(tuple(lp[uv_layer].uv)) - bb0) / span) for lp in f_loops]
            k, mirror, _ = best_orientation(P, ST)
            for lp in loops:
                s, t = (np.array(tuple(lp[uv_layer].uv)) - bb0) / span
                s, t = xform_st(s, t, k, mirror)
                lp[uv_layer].uv = (u0 + s * (u1 - u0), v0 + t * (v1 - v0))
        cell_use[name] = cell_use.get(name, 0) + 1
    info["cell_use"] = cell_use
    # ---- flower quads (flowering bush): red blossoms of the atlas on the kit's flower positions
    n_fq = 0
    if rec.get("flower_quads") and flower_rec and flowers_uv:
        for c, nrm, size in flower_rec:
            n = Vector(nrm).normalized()
            up = Vector((0, 0, 1)) - n * n.z
            if up.length < 1e-4:
                up = Vector((0, 1, 0))
            up.normalize()
            rt = up.cross(n).normalized()       # right, so (rt, up, n) is right-handed
            a = 0.5 * size * 1.1
            ctr = Vector(c) + n * 0.015
            corners = [ctr - rt * a - up * a, ctr + rt * a - up * a, ctr + rt * a + up * a, ctr - rt * a + up * a]
            vs = [bm.verts.new(p) for p in corners]
            f1 = bm.faces.new((vs[0], vs[1], vs[2]))
            f2 = bm.faces.new((vs[0], vs[2], vs[3]))
            fl = flowers_uv[int(rng.integers(len(flowers_uv)))]
            hs = fl["half"]
            st = {vs[0]: (-1, -1), vs[1]: (1, -1), vs[2]: (1, 1), vs[3]: (-1, 1)}
            for f in (f1, f2):
                f.material_index = 0
                f.smooth = True
                for lp in f.loops:
                    sx, sy = st[lp.vert]
                    lp[uv_layer].uv = (fl["u"] + sx * hs, fl["v"] + sy * hs)
            n_fq += 1
        bm.normal_update()
    info["flower_quads"] = n_fq
    for f in bm.faces:
        f.material_index = 0
        f.smooth = True
    # ---- final per-vertex records
    islands = bm_islands(bm)
    bm.verts.index_update()
    nv = len(bm.verts)
    v_island = np.full(nv, -1, int)
    for i, isl in enumerate(islands):
        for v in island_verts(isl):
            v_island[v.index] = i
    cents = np.array([island_centroid(c) for c in islands])
    if kind == "conifer":
        tz = np.array([0.5 * (t["z_lo"] + t["z_hi"]) for t in clumps])
        isl_lab = np.array([int(np.argmin(np.abs(tz - c[2]))) for c in cents])
    else:
        cc = np.array([cl["c"] for cl in clumps])
        isl_lab = np.array([int(np.argmin([ell_d(c, j) for j in range(len(clumps))])) for c in cents])
        for j in range(len(clumps)):
            clumps[j]["n"] = int((isl_lab == j).sum())
    is_dup = np.zeros(len(islands), bool)
    for i, isl in enumerate(islands):
        is_dup[i] = any(f in dup_mark for f in isl)
    isl_area = np.array([island_area(isl) for isl in islands])
    bm.to_mesh(fol_ob.data)
    bm.free()
    info["cards_final"] = len(islands)
    return {"info": info, "clumps": clumps, "v_island": v_island, "isl_lab": isl_lab, "is_dup": is_dup,
            "isl_area": isl_area, "cents": cents}


def foliage_shading(fol_ob, data, crown, G, kind, rng):
    """COLOR_0 multiplier and the wind UV for the foliage; returns stats."""
    me = fol_ob.data
    co = mesh_co(me)
    vi = loop_vertex_index(me)
    lab_v = data["isl_lab"][data["v_island"]]
    clumps = data["clumps"]
    cb, top = crown["cb_final"], crown["top"]
    g = np.clip((co[:, 2] - cb) / max(top - cb, 1e-6), 0, 1)
    if kind == "conifer":
        o = np.zeros(len(co))
        u = np.zeros(len(co))
        for t, tier in enumerate(clumps):
            sel = lab_v == t
            if not sel.any():
                continue
            ax = np.array(tier["axis"])
            rr = np.linalg.norm(co[sel, :2] - ax, axis=1)
            o[sel] = np.clip(rr / max(tier["R"], 1e-6), 0, 1)
            u[sel] = np.clip((co[sel, 2] - tier["z_lo"]) / max(tier["z_hi"] - tier["z_lo"], 1e-6), 0, 1)
        s = 0.45 * smoothstep(0.25, 0.95, o) + 0.30 * u + 0.25 * g
        s = s / max(float(np.percentile(s, 99)), 1e-6)     # tier tips on the upper tiers reach 1.0
        top_n = u
    else:
        d = np.zeros(len(co))
        nz = np.zeros(len(co))
        for j, cl in enumerate(clumps):
            sel = lab_v == j
            if not sel.any():
                continue
            c, r = np.array(cl["c"]), np.array(cl["r"])
            q = (co[sel] - c) / r
            d[sel] = np.linalg.norm(q, axis=1)
            grad = (co[sel] - c) / (r * r)
            nz[sel] = grad[:, 2] / np.maximum(np.linalg.norm(grad, axis=1), 1e-9)
        o = smoothstep(0.35, 0.95, d)
        t = np.clip(0.5 + 0.5 * nz, 0, 1)
        s = G["c0_w_out"] * o + G["c0_w_top"] * t + G["c0_w_h"] * g
        top_n = t
    s = np.clip(s, 0, 1) ** G["c0_gamma"]
    if G.get("c0_lo") is not None and G.get("c0_hi") is not None:     # optional contrast remap (per model)
        s = smoothstep(G["c0_lo"], G["c0_hi"], s)
    v = G["c0_min"] + (1 - G["c0_min"]) * s
    hue = rng.uniform(-G["hue_shift"], G["hue_shift"], size=max(len(clumps), 1))
    h = hue[lab_v]
    rgb = np.stack([v * (1 + h), v, v * (1 - h)], -1)
    rgb /= np.maximum(rgb.max(1, keepdims=True), 1.0)
    rgba =np.concatenate([rgb, np.ones((len(co), 1))], 1)[vi]
    write_color(me, rgba)
    # wind: sway rises with height above a rigid lower trunk, plus a little with the distance from the axis
    z_flex = crown["z_flex"]
    sway = np.clip((co[:, 2] - z_flex) / max(top - z_flex, 1e-6), 0, 1) ** 1.5
    rr = np.linalg.norm(co[:, :2] - crown["axis_xy"], axis=1)
    sway = np.clip(sway + 0.18 * np.clip(rr / max(crown["half_width"], 1e-6), 0, 1) * (co[:, 2] > z_flex), 0, 1)
    phase_cl = np.array([(0.6180339887 * (j + 1) + G["seed"] * 0.137) % 1.0 for j in range(len(clumps))])
    phase = phase_cl[lab_v]
    write_wind(me, sway[vi], phase[vi])
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    return {"color0_lum_min": round(float(lum.min()), 3), "color0_lum_p10": round(float(np.percentile(lum, 10)), 3),
            "color0_lum_p50": round(float(np.percentile(lum, 50)), 3), "color0_lum_max": round(float(lum.max()), 3),
            "color0_inside_share_below_0p7": round(float((lum < 0.7).mean()), 3),
            "corr_color0_vs_top": round(float(np.corrcoef(lum, top_n)[0, 1]), 3) if lum.std() > 1e-6 else None,
            "hue_shift_per_clump": [round(float(x), 4) for x in hue],
            "wind_sway_min_max": [round(float(sway.min()), 3), round(float(sway.max()), 3)],
            "wind_phase_per_clump": [round(float(x), 4) for x in phase_cl]}


def proxy_normals(fol_ob, data, kind, mix):
    """Data Transfer modifier per clump/tier from an ellipsoid/cone proxy; returns verification stats."""
    me = fol_ob.data
    lab_v = data["isl_lab"][data["v_island"]]
    clumps = data["clumps"]
    proxies = []
    for j, cl in enumerate(clumps):
        vg = fol_ob.vertex_groups.new(name=f"clump_{j}")
        idx = np.nonzero(lab_v == j)[0].tolist()
        if not idx:
            continue
        vg.add(idx, 1.0, "REPLACE")
        if kind == "conifer":
            R = cl["R"] * 1.06
            z0 = cl["z_lo"] - 0.1
            h = max(cl["z_hi"] - cl["z_lo"], 0.4) + 0.45 * R
            bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=R, radius2=0.0, depth=h, end_fill_type="NOTHING",
                                            location=(cl["axis"][0], cl["axis"][1], z0 + h / 2))
        else:
            bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0, location=tuple(cl["c"]))
            bpy.context.object.scale = tuple(cl["r"])
        px = bpy.context.object
        px.name = f"proxy_{j}"
        px.data.polygons.foreach_set("use_smooth", np.ones(len(px.data.polygons), bool))
        px.data.update()
        proxies.append(px)
        mod = fol_ob.modifiers.new(f"dt_{j}", "DATA_TRANSFER")
        mod.object = px
        mod.use_object_transform = True
        mod.use_loop_data = True
        mod.data_types_loops = {"CUSTOM_NORMAL"}
        mod.loop_mapping = "POLYINTERP_NEAREST"
        mod.mix_mode = "REPLACE"
        mod.mix_factor = mix
        mod.vertex_group = vg.name
    for mod in list(fol_ob.modifiers):
        apply_modifier(fol_ob, mod)
    # verification against the analytic proxy normal
    co = mesh_co(me)
    vi = loop_vertex_index(me)
    cn = np.empty(len(me.loops) * 3, np.float32)
    me.corner_normals.foreach_get("vector", cn)
    cn = cn.reshape(-1, 3)
    ref = np.zeros((len(co), 3))
    for j, cl in enumerate(clumps):
        sel = lab_v == j
        if kind == "conifer":
            ax = np.array(cl["axis"])
            d = co[sel, :2] - ax
            d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            h = max(cl["z_hi"] - cl["z_lo"], 0.4) + 0.45 * cl["R"] * 1.06
            ref[sel] = np.concatenate([d, np.full((sel.sum(), 1), cl["R"] * 1.06 / h)], 1)
        else:
            c, r = np.array(cl["c"]), np.array(cl["r"])
            ref[sel] = (co[sel] - c) / (r * r)
    ref /= np.maximum(np.linalg.norm(ref, axis=1, keepdims=True), 1e-9)
    dots = (cn * ref[vi]).sum(1)
    fn = np.empty(len(me.polygons) * 3, np.float32)
    me.polygons.foreach_get("normal", fn)
    fn = fn.reshape(-1, 3)
    loop_face = np.empty(len(me.loops), np.int32)
    for p in me.polygons:
        loop_face[p.loop_start:p.loop_start + p.loop_total] = p.index
    dface = np.abs((cn * fn[loop_face]).sum(1))
    stats = {"method": "DataTransfer modifier, Face Corner Data -> Custom Normals, POLYINTERP_NEAREST, mix %.2f, "
                       "one %s proxy per %s" % (mix, "cone" if kind == "conifer" else "ellipsoid",
                                                 "tier" if kind == "conifer" else "clump"),
             "proxies": len(proxies), "mean_dot_with_proxy_normal": round(float(dots.mean()), 3),
             "share_dot_over_0p8": round(float((dots > 0.8).mean()), 3),
             "mean_abs_dot_with_face_normal": round(float(dface.mean()), 3)}
    for px in proxies:
        bpy.data.objects.remove(px, do_unlink=True)
    for vg in list(fol_ob.vertex_groups):
        fol_ob.vertex_groups.remove(vg)
    return stats


# ----------------------------------------------------------------------------------------------- bark

def bark_shading(bark_ob, crown, G, data, kind):
    me = bark_ob.data
    old = read_color(me)
    lum_old = old[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
    lo = G["bark_c0_min"]
    v = lo + (1 - lo) * np.clip((old[:, :3] - 0.10) / 0.90, 0, 1)
    rgba = np.concatenate([v, np.ones((len(v), 1))], 1)
    write_color(me, rgba)
    co = mesh_co(me)
    vi = loop_vertex_index(me)
    top, z_flex = crown["top"], crown["z_flex"]
    sway = np.clip((co[:, 2] - z_flex) / max(top - z_flex, 1e-6), 0, 1) ** 1.5
    phase = np.zeros(len(co))
    clumps = data["clumps"]
    if clumps:
        if kind == "conifer":
            cz = np.array([0.5 * (t["z_lo"] + t["z_hi"]) for t in clumps])
            j = np.argmin(np.abs(co[:, 2:3] - cz[None]), axis=1)
        else:
            cc = np.array([cl["c"] for cl in clumps])
            j = np.argmin(((co[:, None, :] - cc[None]) ** 2).sum(-1), axis=1)
        phase_cl = np.array([(0.6180339887 * (k + 1) + G["seed"] * 0.137) % 1.0 for k in range(len(clumps))])
        phase = np.where(co[:, 2] > crown["cb_final"] - 0.5, phase_cl[j], 0.0)
    write_wind(me, sway[vi], phase[vi])
    lum_new = v @ np.array([0.2126, 0.7152, 0.0722])
    return {"kit_color0_lum_min": round(float(lum_old.min()), 3), "color0_lum_min": round(float(lum_new.min()), 3),
            "color0_lum_mean": round(float(lum_new.mean()), 3),
            "wind_sway_at_1m_max": round(float(sway[co[:, 2] < 1.0].max()) if (co[:, 2] < 1.0).any() else 0.0, 4)}


def remove_low_limbs(bark_ob, trunk, cb):
    bm = bmesh.new()
    bm.from_mesh(bark_ob.data)
    isl = bm_islands(bm)
    isl.sort(key=len, reverse=True)
    removed = []
    for comp in isl[1:]:
        vs = np.array([tuple(v.co) for v in island_verts(comp)])
        c = trunk.centre(np.clip(vs[:, 2], 0, None))
        r = np.linalg.norm(vs[:, :2] - c, axis=1)
        if vs[:, 2].max() < 0.85 * cb and r.max() > 0.45:
            removed.append({"tris": len(comp), "z_max": round(float(vs[:, 2].max()), 2), "r_max": round(float(r.max()), 2)})
            bmesh.ops.delete(bm, geom=comp, context="FACES")
    bm.to_mesh(bark_ob.data)
    bm.free()
    return removed


# ----------------------------------------------------------------------------------------------- LOD1, export

def build_lod1(bark_ob, fol_ob, data, rec, kind, spec, top_h):
    out = {}
    b1 = None
    if bark_ob is not None:
        b1 = bark_ob.copy()
        b1.data = bark_ob.data.copy()
        b1.name = bark_ob.name + "_lod1"
        bpy.context.scene.collection.objects.link(b1)
        t0 = tri_count(b1.data)
        decimate(b1, min(1.0, rec["lod1_bark"] / max(t0, 1)))
        triangulate(b1)
        out["bark_tris"] = tri_count(b1.data)
    f1 = fol_ob.copy()
    f1.data = fol_ob.data.copy()
    f1.name = fol_ob.name + "_lod1"
    bpy.context.scene.collection.objects.link(f1)
    budget = spec["lod1_max"] - (out.get("bark_tris", 0)) - 30
    me = f1.data
    bm = bmesh.new()
    bm.from_mesh(me)
    isl = bm_islands(bm)
    bm.verts.index_update()
    # map new islands to the LOD0 island records through a vertex
    vmap = data["v_island"]
    rec_idx = [vmap[island_verts(c)[0].index] for c in isl]
    cents = data["cents"][rec_idx]
    dup = data["is_dup"][rec_idx]
    area = data["isl_area"][rec_idx]
    clumps = data["clumps"]
    lab = data["isl_lab"][rec_idx]
    if kind == "conifer":
        score = np.array([np.linalg.norm(c[:2] - np.array(clumps[l]["axis"])) / max(clumps[l]["R"], 1e-6)
                          for c, l in zip(cents, lab)])
    else:
        score = np.array([np.linalg.norm((c - np.array(clumps[l]["c"])) / np.array(clumps[l]["r"]))
                          for c, l in zip(cents, lab)])
    order = sorted(range(len(isl)), key=lambda i: (dup[i], -score[i]))
    keep, tris = [], 0
    for i in order:
        n = len(isl[i])
        if tris + n > budget:
            continue
        keep.append(i)
        tris += n
    keep_set = set(keep)
    kill = [f for i, c in enumerate(isl) if i not in keep_set for f in c]
    a_all = float(area.sum())
    a_keep = float(area[list(keep_set)].sum()) if keep else 1.0
    scale = float(np.clip(math.sqrt(a_all / max(a_keep, 1e-9)) * 0.92, 1.0, 1.45))
    for i in keep:
        vs = island_verts(isl[i])
        c = Vector(np.mean([tuple(v.co) for v in vs], axis=0))
        for v in vs:
            v.co = c + (v.co - c) * scale
        over = max(v.co.z for v in vs) - top_h
        if over > 0:          # keep the LOD1 silhouette inside the slot height (no pop at the LOD swap)
            for v in vs:
                v.co.z -= over
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(me)
    bm.free()
    out.update({"foliage_tris": tri_count(me), "cards_kept": len(keep), "cards_lod0": len(isl),
                "card_scale": round(scale, 3)})
    return b1, f1, out


COPYRIGHT = "CC0-1.0 Quaternius Stylized Nature MegaKit (Standard); stylized for Xexoria (Route A step 2)"
# One image folder for every species. Not "textures", which holds the source PNGs the materials load.
SHARED_TEXTURES = "textures-shared"


def export_lod(ob, path, budget_class, a, notes):
    """One LOD through the shared export helper (profile "foliage"); raises when its validation fails."""
    return xex_export_glb([ob], path, "foliage", budget_class=budget_class,
                          texture_dir=Path(a.out) / SHARED_TEXTURES, copyright_text=COPYRIGHT,
                          inputs=[a.atlas, a.bark_albedo, a.bark_normal], notes=notes)


def join(obs, name):
    obs = [o for o in obs if o is not None]
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    if len(obs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


# ----------------------------------------------------------------------------------------------- main

def stylize(model, a, layout, G, recipe, images, flowers_uv):
    t0 = time.time()
    cfg = PICKS[model]
    rec = recipe[model]
    kind, H, species = cfg["kind"], cfg["height"], cfg["species"]
    rng = np.random.default_rng(G["seed"] + sum(map(ord, model)))
    ob = import_kit(a.src, model)
    kit_tris = tri_count(ob.data)
    parts, src_mats = split_kinds(ob)
    bark, fol = parts["bark"], parts["foliage"]
    res = {"model": model, "species": species, "kind": kind, "slot": cfg["slot"], "height_m": H,
           "kit_materials": src_mats, "kit_triangles": kit_tris, "recipe": rec, "steps": {}}
    # --- normalise: uniform scale to the slot height, pivot at the ground contact
    allz = np.concatenate([mesh_co(o.data)[:, 2] for o in (bark, fol) if o is not None])
    s = H / float(allz.max())
    for o in (bark, fol):
        if o is not None:
            o.data.transform(Matrix.Scale(s, 4))
    if bark is not None:
        weld(bark)
        sec0 = sections(bark.data, [0.05])
        cxy = np.array(sec0[0]["c"]) if sec0[0]["c"] else np.zeros(2)
    else:
        fc = mesh_co(fol.data)
        cxy = (fc[:, :2].max(0) + fc[:, :2].min(0)) / 2
    for o in (bark, fol):
        if o is not None:
            o.data.transform(Matrix.Translation((-cxy[0], -cxy[1], 0.0)))
    res["steps"]["normalise"] = {"scale": round(s, 5), "pivot_shift_xy_m": [round(float(-v), 4) for v in cxy],
                                 "ground": "z = 0 at the kit ground plane (object origin); buried skirt kept"}
    fol_co = mesh_co(fol.data)
    leaf_only = fol_co
    res["before"] = shape_metrics(bark.data if bark else None, leaf_only, H, kind)
    res["before"]["triangles"] = kit_tris
    # --- crown frame
    cb_from = res["before"].get("crown_base_p5_m")
    cb_to = rec.get("crown_base_to")
    crown = {"top": H, "cb_from": cb_from, "cb_to": cb_to if (cb_to and cb_from and cb_from > cb_to) else None}
    crown["cb_to_eff"] = crown["cb_to"] if crown["cb_to"] else cb_from
    zf = zmap(fol_co[:, 2], crown["cb_from"], crown["cb_to"], H)
    fol_tmp = fol_co.copy()
    fol_tmp[:, 2] = zf
    crown["c_xy"] = (fol_tmp[:, :2].max(0) + fol_tmp[:, :2].min(0)) / 2
    half_w = float((fol_tmp[:, :2].max(0) - fol_tmp[:, :2].min(0)).mean() / 2)
    crown["r0"] = 0.3 if kind == "broadleaf" else 0.25
    crown["w_za"] = crown["cb_to_eff"] - 0.6
    crown["w_zb"] = crown["cb_to_eff"] + 0.9
    trunk = None
    if bark is not None:
        trunk = TrunkModel(sections(bark.data, [0.05, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]))
        crown["axis_xy"] = trunk.centre(min(crown["cb_to_eff"], 3.0))
    else:
        crown["axis_xy"] = crown["c_xy"]
    crown["z_flex"] = 0.45 * crown["cb_to_eff"] if kind != "bush" else 0.12
    # --- bark shape
    if bark is not None:
        steps = {}
        if rec.get("remove_low_limbs"):
            steps["removed_low_limbs"] = remove_low_limbs(bark, trunk, cb_from)
        co = mesh_co(bark.data)
        co[:, 2] = zmap(co[:, 2], crown["cb_from"], crown["cb_to"], H)
        if kind == "broadleaf":
            pass   # widening applied after the foliage solve (same F)
        elif kind == "conifer":
            co = radial(co, rec["narrow"], crown["axis_xy"], 0.25, 0.5, 1.3)
        set_co(bark.data, co)
        if crown["cb_to"]:
            steps["crown_base_zmap"] = {"from_m": round(cb_from, 3), "to_m": cb_to,
                                        "trunk_z_scale": round(cb_to / cb_from, 4),
                                        "crown_z_scale": round((H - cb_to) / (H - cb_from), 4)}
        res["steps"]["bark_shape"] = steps
    # --- foliage (topology, shape, UVs)
    data = process_foliage(fol, cfg, rec, G, crown, trunk, layout, flowers_uv, rng, kind)
    res["steps"]["foliage"] = data["info"]
    if bark is not None:
        co = mesh_co(bark.data)
        if kind == "broadleaf":
            co = radial(co, crown["F"], crown["c_xy"], crown["r0"], crown["w_za"], crown["w_zb"])
            set_co(bark.data, co)
        trunk2 = TrunkModel(sections(bark.data, [0.05, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]))
        if rec.get("trunk_scale", 1.0) > 1.0:
            co = mesh_co(bark.data)
            z = co[:, 2]
            c = trunk2.centre(np.clip(z, 0, None))
            rt = trunk2.radius(np.clip(z, 0.05, None))
            d = co[:, :2] - c
            r = np.linalg.norm(d, axis=1)
            m_r = 1.0 - smoothstep(1.5, 2.5, r / np.maximum(rt, 1e-3))
            m_z = 1.0 - smoothstep(crown["cb_to_eff"], crown["cb_to_eff"] + 2.5, z)
            k = 1.0 + (rec["trunk_scale"] - 1.0) * m_r * m_z
            co[:, :2] = c + d * k[:, None]
            set_co(bark.data, co)
            res["steps"]["trunk_thicken"] = {"factor": rec["trunk_scale"], "full_below_m": round(crown["cb_to_eff"], 2),
                                             "fades_out_by_m": round(crown["cb_to_eff"] + 2.5, 2)}
            trunk2 = TrunkModel(sections(bark.data, [0.05, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]))
        # bark budget first (decision: decimate the bark before anything else), then the flare on the result
        t_b0 = tri_count(bark.data)
        clear_custom_normals(bark)
        decimate(bark, rec.get("bark_ratio", 1.0))
        triangulate(bark)
        weld(bark)
        res["steps"]["bark_decimate"] = {"ratio": rec.get("bark_ratio", 1.0), "tris_before": t_b0,
                                         "tris_after": tri_count(bark.data)}
        trunk2 = TrunkModel(sections(bark.data, [0.05, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]))
        rings = add_rings(bark, trunk2, [0.1, 0.22, 0.36, 0.52, 0.7])
        theta0 = float(rng.uniform(0, 2 * math.pi))
        fl = solve_flare(bark, trunk2, rec["flare"], rec["buttresses"], theta0, 0.7 if kind == "broadleaf" else 0.6)
        res["steps"]["root_flare"] = dict(fl or {}, rings_added_verts=rings, target=rec["flare"],
                                          tris_after=tri_count(bark.data))
    # --- final height correction (rigid moves can push a card above the slot height)
    allz = np.concatenate([mesh_co(o.data)[:, 2] for o in (bark, fol) if o is not None])
    s2 = H / float(allz.max())
    if abs(s2 - 1) > 1e-4:
        for o in (bark, fol):
            if o is not None:
                o.data.transform(Matrix.Scale(s2, 4))
        for cl in data["clumps"]:
            if kind == "conifer":
                for k in ("z_lo", "z_hi", "R"):
                    cl[k] *= s2
                cl["axis"] = [x * s2 for x in cl["axis"]]
            else:
                cl["c"] = [x * s2 for x in cl["c"]]
                cl["r"] = [x * s2 for x in cl["r"]]
        data["cents"] = data["cents"] * s2
    res["steps"]["height_correction_scale"] = round(s2, 5)
    fol_co = mesh_co(fol.data)
    crown["cb_final"] = float(np.percentile(fol_co[:, 2], 5))
    crown["half_width"] = float((fol_co[:, :2].max(0) - fol_co[:, :2].min(0)).mean() / 2)
    crown["z_flex"] = 0.45 * crown["cb_final"] if kind != "bush" else 0.12
    # --- bark normals, COLOR_0, wind
    if bark is not None:
        clear_custom_normals(bark)
        res["steps"]["bark_has_custom_normals_after_clear"] = bool(getattr(bark.data, "has_custom_normals", False))
        res["steps"]["bark_shading"] = bark_shading(bark, crown, G, data, kind)
        me = bark.data
        boundary = sum(1 for e in bmesh_boundary_edges(me))
        res["steps"]["bark_open_edges"] = boundary
    # --- foliage shading + normals
    Gm = dict(G, **{k: v for k, v in rec.items() if k.startswith("c0_")})     # per-model COLOR_0 overrides
    res["steps"]["foliage_shading"] = foliage_shading(fol, data, crown, Gm, kind, rng)
    res["steps"]["foliage_shading"]["c0_params"] = {k: Gm[k] for k in Gm if k.startswith("c0_")}
    res["steps"]["foliage_normals"] = proxy_normals(fol, data, kind, G["normal_mix"])
    # --- clumps summary
    if kind == "conifer":
        res["clumps"] = [{"tier": i, "z_lo": round(t["z_lo"], 2), "z_hi": round(t["z_hi"], 2), "R": round(t["R"], 2),
                          "fronds": t["n"]} for i, t in enumerate(data["clumps"])]
    else:
        res["clumps"] = [{"c": [round(x, 2) for x in cl["c"]], "r": [round(x, 2) for x in cl["r"]], "cards": cl["n"]}
                         for cl in data["clumps"]]
    # --- materials
    double_bark = res["steps"].get("bark_open_edges", 0) > 0
    mats = {}
    if bark is not None:
        mats["bark"] = make_material(f"{species}_bark", images["bark_albedo"], images["bark_normal"], None,
                                     double_sided=double_bark, roughness=G["roughness_bark"])
        bark.data.materials.clear()
        bark.data.materials.append(mats["bark"])
    mats["foliage"] = make_material(f"{species}_foliage", images["atlas"], None, G["alpha_cutoff"], True,
                                    G["roughness_foliage"])
    fol.data.materials.clear()
    fol.data.materials.append(mats["foliage"])
    # --- metrics after (LOD0)
    res["after"] = shape_metrics(bark.data if bark else None, mesh_co(fol.data), H, kind)
    res["after"]["bark_tris"] = tri_count(bark.data) if bark else 0
    res["after"]["foliage_tris"] = tri_count(fol.data)
    res["after"]["triangles"] = res["after"]["bark_tris"] + res["after"]["foliage_tris"]
    res["after"]["cards"] = data["info"]["cards_final"]
    res["after"]["clumps_or_tiers"] = len(data["clumps"])
    spec = SPEC[kind]
    # --- LOD1 (before join; uses the LOD0 objects)
    b1, f1, lod1 = build_lod1(bark, fol, data, rec if kind != "bush" else dict(rec, lod1_bark=0), kind, spec, H)
    res["lod1"] = lod1
    os.makedirs(a.out, exist_ok=True)
    lod0 = join([bark, fol], f"{species}_lod0")
    lod1_ob = join([b1, f1], f"{species}_lod1")
    for o, lvl in ((lod0, 0), (lod1_ob, 1)):
        o["asset_id"] = species
        o["lod"] = lvl
        o["source_model"] = f"Quaternius Stylized Nature MegaKit (Standard) / glTF / {model}.gltf"
        o["licence"] = "CC0-1.0"
    p0 = os.path.join(a.out, f"{species}_lod0.glb")
    p1 = os.path.join(a.out, f"{species}_lod1.glb")
    cls = "bush" if kind == "bush" else "tree"  # budget classes tree_lod0/1, bush_lod0/1 (tools/asset-budgets.json)
    r0 = export_lod(lod0, p0, f"{cls}_lod0", a, f"trees_v4 stylize {a.tag} {model} LOD0")
    r1 = export_lod(lod1_ob, p1, f"{cls}_lod1", a, f"trees_v4 stylize {a.tag} {model} LOD1")
    res["export"] = {"lod0": p0, "lod1": p1, "lod0_bytes": os.path.getsize(p0), "lod1_bytes": os.path.getsize(p1),
                     "lod0_tris": tri_count(lod0.data), "lod1_tris": tri_count(lod1_ob.data),
                     "export_helper": {"receipts": [r0["receipt"], r1["receipt"]], "status": [r0["status"], r1["status"]],
                                       "budget_classes": [r0["budget_class"], r1["budget_class"]],
                                       "texture_dir": r0["texture_dir"],
                                       "images": [{k: i[k] for k in ("file", "sha256", "dedup")} for i in r0["images"]],
                                       "warnings": r0["warnings"] + r1["warnings"]},
                     "gltf_options": r0["exporter_options"],
                     "materials": [m.name for m in lod0.data.materials],
                     "bark_double_sided": double_bark}
    a_spec = res["after"]
    checks = {"lod0_in_budget": spec["lod0"][0] <= res["export"]["lod0_tris"] <= spec["lod0"][1],
              "lod1_in_budget": res["export"]["lod1_tris"] <= spec["lod1_max"]}
    if kind != "bush":
        lo, hi = spec["crown_base"]
        checks["crown_base_in_spec"] = a_spec.get("crown_base_p5_m", 99) <= hi
        lo, hi = spec["wh"]
        checks["crown_wh_in_spec"] = lo <= a_spec.get("crown_width_over_height", 0) <= hi
        checks["flare_in_spec"] = (a_spec.get("flare_ground_over_1m") or 0) >= spec["flare"][0] - 0.02
        checks["trunk_r_1m_ok"] = (a_spec.get("trunk_r_1m_m") or 0) >= cfg["trunk_min"] - 0.005
    checks["bark_color0_min_ok"] = (res["steps"].get("bark_shading", {}).get("color0_lum_min", 1.0) >= 0.549)
    res["checks"] = checks
    res["seconds"] = round(time.time() - t0, 1)
    log("STYLIZED", model, species, json.dumps({"lod0": res["export"]["lod0_tris"], "lod1": res["export"]["lod1_tris"],
                                                 "before": res["before"], "after": res["after"], "checks": checks}))
    return res


def bmesh_boundary_edges(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    out = [e for e in bm.edges if e.is_boundary]
    n = len(out)
    bm.free()
    return range(n)


def main():
    a = parse()
    G = dict(GLOBAL)
    recipe = {k: dict(v) for k, v in RECIPE.items()}
    if a.params:
        p = json.load(open(a.params, encoding="utf-8"))
        G.update(p.get("_global", {}))
        for m, over in p.items():
            if m in recipe:
                recipe[m].update(over)
        for m in recipe:
            recipe[m].update(p.get("_all", {}))
    layout = json.load(open(a.layout, encoding="utf-8-sig"))
    report = {"label": "STYLIZE (Blender headless, kit imported read-only; outputs are new files)",
              "tag": a.tag, "blender": bpy.app.version_string, "inputs": vars(a), "global": G, "models": {}}
    t_all = time.time()
    for model in [m for m in a.models.split(",") if m]:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        images = {"atlas": load_image(a.atlas, "sRGB"), "bark_albedo": load_image(a.bark_albedo, "sRGB"),
                  "bark_normal": load_image(a.bark_normal, "Non-Color")}
        rng = np.random.default_rng(G["seed"])
        flowers_uv = find_flowers(images["atlas"], layout["cells"]["BB_blossom"]["uv_rect"], rng)
        report["blossom_flowers_uv"] = flowers_uv
        try:
            # import_kit resets the scene: keep the images by re-loading after import
            res = stylize_wrapper(model, a, layout, G, recipe, flowers_uv)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            report["models"][model] = {"error": repr(exc)}
            raise
        report["models"][model] = res
    report["seconds_total"] = round(time.time() - t_all, 1)
    report["log"] = LOG[-400:]
    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    with open(a.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("WROTE", a.report)


def stylize_wrapper(model, a, layout, G, recipe, flowers_uv):
    # import_kit() calls read_factory_settings, so the images are loaded lazily, after the import
    images = {}

    def lazy_images():
        if not images:
            images["atlas"] = load_image(a.atlas, "sRGB")
            images["bark_albedo"] = load_image(a.bark_albedo, "sRGB")
            images["bark_normal"] = load_image(a.bark_normal, "Non-Color")
        return images

    class Lazy(dict):
        def __getitem__(self, k):
            return lazy_images()[k]
    return stylize(model, a, layout, G, recipe, Lazy(), flowers_uv)


main()
