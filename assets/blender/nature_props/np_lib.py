"""Shared Blender helpers for the Sunmeadow prop library (nature_props).

Blender 5.2, headless. Everything here is deterministic for a given recipe seed. Units are metres, Blender Z up;
glTF/Babylon local = (x, z, -y) of Blender (asset front = Blender -Y = glTF +Z).

Sections
  paths / scene        REPO, reset(), collection helpers
  mesh <-> numpy        verts, edges, normals, mesh_from_arrays, apply_modifiers, remesh, decimate_to
  shaping               taubin(), chip_flatten()
  hulls                 convex_hull_object(), cut_hull()
  uv                    smart_project(), uv_islands(), shrink_islands(), pack_atlas()
  bake                  BakeJob: data maps (normal TS/OS, AO, emitted attributes) into float images -> .npz
  materials             pbr_material() (albedo sRGB, normal OpenGL, ORM: R=AO G=rough B=metal)
  export                export_lod() through assets/blender/tools/export_helper.py
  checks                mesh_report() (tris, manifold, zero-area, bounds, pivot)
  colliders             collider_hull(), footprint_xz()
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))


import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TOOLS = REPO / "assets" / "blender" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import np_noise as NZ  # noqa: E402

OUT_MODELS = REPO / "assets" / "models" / "sunmeadow-props"
EVIDENCE = REPO / "planning" / "evidence" / "sunmeadow-props-20261002"
CACHE = Path(os.environ.get("NP_CACHE", str(_XEXORIA_AGENT_OUTPUT / '20261002-sunmeadow-props/cache')))
LIB_VERSION = "nature_props/1.0"


def log(*a):
    print("[np]", *a, flush=True)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------------------------- scene

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    return sc


def link(obj, coll_name="NP"):
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        coll = bpy.data.collections.new(coll_name)
        bpy.context.scene.collection.children.link(coll)
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    return obj


def delete(objs):
    for o in list(objs):
        me = o.data if o.type == "MESH" else None
        bpy.data.objects.remove(o, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def set_active(obj, select_only=True):
    if select_only:
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# ----------------------------------------------------------------------------------------------- mesh <-> numpy

def verts(me) -> np.ndarray:
    a = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", a)
    return a.reshape(-1, 3).astype(np.float64)


def set_verts(me, v):
    me.vertices.foreach_set("co", np.asarray(v, dtype=np.float32).ravel())
    me.update()


def edges(me) -> np.ndarray:
    a = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", a)
    return a.reshape(-1, 2)


def vnormals(me) -> np.ndarray:
    a = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertex_normals.foreach_get("vector", a)
    return a.reshape(-1, 3).astype(np.float64)


def tri_count(obj) -> int:
    me = obj.data
    n = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_total", n)
    return int((n - 2).sum())


def faces_list(me):
    n = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_total", n)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    out, i = [], 0
    for k in n:
        out.append(lv[i:i + k].tolist())
        i += k
    return out


def mesh_from_arrays(name, v, faces, coll="NP"):
    """faces: list of index lists, or an (F, k) int array."""
    me = bpy.data.meshes.new(name)
    v = np.asarray(v, dtype=np.float64)
    if isinstance(faces, np.ndarray):
        faces = faces.tolist()
    me.from_pydata(v.tolist(), [], faces)
    me.validate(clean_customdata=False)
    me.update()
    ob = bpy.data.objects.new(name, me)
    link(ob, coll)
    return ob


def tris_to_object(name, v, tris, coll="NP"):
    return mesh_from_arrays(name, v, np.asarray(tris, dtype=np.int64), coll)


def apply_modifiers(obj):
    """Bake the modifier stack into the mesh data (no operators, works headless)."""
    if not obj.modifiers:
        return obj
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def remesh(obj, voxel, adaptivity=0.0):
    m = obj.modifiers.new("np_remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = float(voxel)
    m.adaptivity = float(adaptivity)
    m.use_smooth_shade = True
    return apply_modifiers(obj)


def triangulate(obj):
    m = obj.modifiers.new("np_tri", "TRIANGULATE")
    m.quad_method = "BEAUTY"
    m.ngon_method = "BEAUTY"
    m.keep_custom_normals = True
    return apply_modifiers(obj)


def copy_object(obj, name, coll="NP"):
    ob = obj.copy()
    ob.data = obj.data.copy()
    ob.name = name
    ob.data.name = name
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    link(ob, coll)
    return ob


def decimate_to(obj, target_tris, name=None, tol=0.04, max_iter=7, planar=False):
    """Copy of obj decimated (collapse) to about target_tris triangles. Returns the new object."""
    src_tris = tri_count(obj)
    name = name or obj.name + "_dec"
    if src_tris <= target_tris:
        ob = copy_object(obj, name)
        return triangulate(ob)
    lo, hi = 0.0, 1.0
    ratio = target_tris / max(src_tris, 1)
    best = None
    for _ in range(max_iter):
        ob = copy_object(obj, name)
        m = ob.modifiers.new("np_dec", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = max(1e-4, min(1.0, ratio))
        m.use_collapse_triangulate = True
        m.use_symmetry = False
        apply_modifiers(ob)
        triangulate(ob)
        t = tri_count(ob)
        if best is not None:
            delete([best[1]])
        best = (t, ob)
        if abs(t - target_tris) <= tol * target_tris:
            break
        # proportional correction, bounded by the bracket
        if t > target_tris:
            hi = ratio
        else:
            lo = ratio
        new = ratio * target_tris / max(t, 1)
        ratio = new if lo < new < hi else (lo + hi) / 2
    ob = best[1]
    ob.name = name
    return ob


def set_smooth(obj, smooth=True):
    me = obj.data
    me.polygons.foreach_set("use_smooth", np.full(len(me.polygons), smooth, dtype=bool))
    me.update()


def weighted_normals(obj, keep_sharp=True, weight=50):
    m = obj.modifiers.new("np_wn", "WEIGHTED_NORMAL")
    m.mode = "FACE_AREA"
    m.weight = weight
    m.keep_sharp = keep_sharp
    return apply_modifiers(obj)


def bevel(obj, width, segments=1, angle_deg=40.0, harden=True, clamp=True, limit="ANGLE"):
    m = obj.modifiers.new("np_bevel", "BEVEL")
    m.width = float(width)
    m.segments = int(segments)
    m.limit_method = limit
    if limit == "ANGLE":
        m.angle_limit = math.radians(angle_deg)
    m.use_clamp_overlap = clamp
    m.harden_normals = harden
    m.miter_outer = "MITER_ARC"
    m.profile = 0.5
    return apply_modifiers(obj)


def join(objs, name):
    objs = [o for o in objs if o is not None]
    base = objs[0]
    if len(objs) > 1:
        with bpy.context.temp_override(active_object=base, selected_editable_objects=objs, selected_objects=objs):
            bpy.ops.object.join()
    base.name = name
    base.data.name = name
    return base


def apply_transform(obj):
    me = obj.data
    me.transform(obj.matrix_world)
    obj.matrix_world = obj.matrix_world.__class__.Identity(4)
    me.update()


# ----------------------------------------------------------------------------------------------- shaping

def taubin(v, e, iters=4, lam=0.5, mu=-0.53, weights=None):
    """Uniform-Laplacian Taubin smoothing (shrink-free). weights: per-vertex 0..1 multiplier (0 = pinned)."""
    n = len(v)
    e0, e1 = e[:, 0], e[:, 1]
    deg = np.bincount(e0, minlength=n) + np.bincount(e1, minlength=n)
    deg = np.maximum(deg, 1).astype(np.float64)
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=np.float64)
    v = v.copy()
    for _ in range(iters):
        for f in (lam, mu):
            acc = np.empty_like(v)
            for k in range(3):
                acc[:, k] = np.bincount(e0, weights=v[e1, k], minlength=n) + np.bincount(e1, weights=v[e0, k], minlength=n)
            lap = acc / deg[:, None] - v
            v = v + (f * w)[:, None] * lap
    return v


def vertex_curvature(v, e, nrm, smooth_iters=6):
    """Signed umbrella curvature along the normal (+ convex, - concave), in 1/m, smoothed over the mesh."""
    n = len(v)
    e0, e1 = e[:, 0], e[:, 1]
    deg = np.maximum(np.bincount(e0, minlength=n) + np.bincount(e1, minlength=n), 1).astype(np.float64)
    acc = np.empty_like(v)
    for k in range(3):
        acc[:, k] = np.bincount(e0, weights=v[e1, k], minlength=n) + np.bincount(e1, weights=v[e0, k], minlength=n)
    lap = acc / deg[:, None] - v
    elen = np.linalg.norm(v[e0] - v[e1], axis=1)
    mean_len = (np.bincount(e0, weights=elen, minlength=n) + np.bincount(e1, weights=elen, minlength=n)) / deg
    k = -np.einsum("ij,ij->i", lap, nrm) / np.maximum(mean_len ** 2, 1e-10)
    for _ in range(smooth_iters):
        s = (np.bincount(e0, weights=k[e1], minlength=n) + np.bincount(e1, weights=k[e0], minlength=n)) / deg
        k = 0.5 * k + 0.5 * s
    return k


def chip_flatten(v, nrm, rng, count, radius, depth, tilt_deg=25.0, region=None):
    """Planar 'knapped' chips: pick surface points, tilt the local normal, move every vertex that lies beyond the
    chip plane (inside a falloff radius) onto it. Crisp creases where the surface crosses the plane."""
    v = v.copy()
    n = len(v)
    cand = np.arange(n) if region is None else np.nonzero(region)[0]
    if len(cand) == 0 or count <= 0:
        return v
    picks = rng.choice(cand, size=min(count, len(cand)), replace=False)
    for idx in picks:
        c = v[idx]
        nn = nrm[idx]
        # random tilt
        t = rng.normal(0, 1, 3)
        t -= nn * np.dot(t, nn)
        t /= np.linalg.norm(t) + 1e-12
        ang = math.radians(rng.uniform(0, tilt_deg))
        pn = nn * math.cos(ang) + t * math.sin(ang)
        r = radius * rng.uniform(0.6, 1.4)
        d = depth * rng.uniform(0.5, 1.5)
        p0 = c - pn * d
        dist = np.linalg.norm(v - c, axis=1)
        inside = dist < r
        if not inside.any():
            continue
        s = (v[inside] - p0) @ pn
        beyond = s > 0
        if not beyond.any():
            continue
        fall = 1.0 - NZ.smoothstep(0.75 * r, r, dist[inside][beyond])
        sub = v[inside]
        sub[beyond] -= (s[beyond] * fall)[:, None] * pn
        v[inside] = sub
    return v


# ----------------------------------------------------------------------------------------------- hulls

def convex_hull_object(name, pts, coll="NP"):
    bm = bmesh.new()
    for p in pts:
        bm.verts.new(Vector(p))
    res = bmesh.ops.convex_hull(bm, input=bm.verts[:], use_existing_faces=False)
    # interior/unused verts: a vert can be listed in both outputs (bmesh.ops.delete refuses duplicates), and any
    # vert left without faces would make the hull non-manifold -> delete every face-less vert exactly once
    bm.verts.index_update()
    kill = {}
    for g in res.get("geom_interior", []) + res.get("geom_unused", []):
        if isinstance(g, bmesh.types.BMVert):
            kill[g.index] = g
    for v in bm.verts:
        if not v.link_faces:
            kill[v.index] = v
    if kill:
        bmesh.ops.delete(bm, geom=list(kill.values()), context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob, coll)
    return ob


def hull_points_cut(pts, planes):
    """Convex polytope = hull(pts) intersected with half-spaces {x: (x - co).no <= 0}. Returns vertex points."""
    bm = bmesh.new()
    for p in pts:
        bm.verts.new(Vector(p))
    bmesh.ops.convex_hull(bm, input=bm.verts[:], use_existing_faces=False)
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=Vector(co), plane_no=Vector(no),
                               clear_outer=True, clear_inner=False)
        if len(bm.verts) < 4:
            break
        keep = [v.co.copy() for v in bm.verts]
        bm.clear()
        for p in keep:
            bm.verts.new(p)
        bmesh.ops.convex_hull(bm, input=bm.verts[:], use_existing_faces=False)
    out = np.array([v.co[:] for v in bm.verts], dtype=np.float64)
    bm.free()
    return out


def support(pts, d):
    return float((pts @ d).max())


# ----------------------------------------------------------------------------------------------- uv

def smart_project(objs, angle_deg=66.0, margin=0.004):
    for o in objs:
        if not o.data.uv_layers:
            o.data.uv_layers.new(name="UVMap")
    set_active(objs[0])
    for o in objs:
        o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle_deg), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def uv_islands(bm, uvl, eps=1e-5):
    parent = list(range(len(bm.faces)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    bm.faces.ensure_lookup_table()
    for e in bm.edges:
        lf = e.link_loops
        if len(lf) != 2:
            continue
        l1, l2 = lf[0], lf[1]
        a1, b1 = l1[uvl].uv, l1.link_loop_next[uvl].uv
        a2, b2 = l2[uvl].uv, l2.link_loop_next[uvl].uv
        if (a1 - b2).length < eps and (b1 - a2).length < eps:
            r1, r2 = find(l1.face.index), find(l2.face.index)
            if r1 != r2:
                parent[r1] = r2
    groups = {}
    for f in bm.faces:
        groups.setdefault(find(f.index), []).append(f)
    return list(groups.values())


def shrink_islands(obj, predicate, factor):
    """Scale UV islands whose faces satisfy predicate(mean_normal, mean_center) by factor about their centre."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    n_shrunk = 0
    for isl in uv_islands(bm, uvl):
        area = sum(f.calc_area() for f in isl) + 1e-12
        nrm = sum((f.normal * f.calc_area() for f in isl), Vector()) / area
        cen = sum((f.calc_center_median() * f.calc_area() for f in isl), Vector()) / area
        if predicate(nrm, cen):
            loops = [l for f in isl for l in f.loops]
            c = sum((l[uvl].uv for l in loops), Vector((0, 0))) / len(loops)
            for l in loops:
                l[uvl].uv = c + (l[uvl].uv - c) * factor
            n_shrunk += 1
    bm.to_mesh(me)
    bm.free()
    return n_shrunk


def pack_atlas(objs, margin=0.006, rotate=True, average=True):
    """Average island texel density across objs and pack all islands of all objs into 0..1."""
    set_active(objs[0])
    for o in objs:
        o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action="SELECT")
    if average:
        bpy.ops.uv.average_islands_scale()
    try:
        bpy.ops.uv.pack_islands(rotate=rotate, scale=True, margin_method="FRACTION", margin=margin,
                                shape_method="CONCAVE")
    except TypeError:
        bpy.ops.uv.pack_islands(rotate=rotate, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def uv_array(obj, layer=None):
    me = obj.data
    uvl = me.uv_layers[layer] if layer else me.uv_layers.active
    a = np.empty(len(me.loops) * 2, dtype=np.float32)
    uvl.data.foreach_get("uv", a)
    return a.reshape(-1, 2)


def set_uv_array(obj, uv, layer=None):
    me = obj.data
    uvl = me.uv_layers[layer] if layer else me.uv_layers.active
    uvl.data.foreach_set("uv", np.asarray(uv, dtype=np.float32).ravel())


def uv_remap_rect(obj, rect, layer=None):
    """Map 0..1 UVs into rect = (u0, v0, w, h) of the atlas."""
    uv = uv_array(obj, layer)
    u0, v0, w, h = rect
    uv = np.stack([u0 + uv[:, 0] * w, v0 + uv[:, 1] * h], axis=1)
    set_uv_array(obj, uv, layer)


def texel_density(obj, atlas_px, layer=None):
    """px per metre: sqrt(uv area * px^2 / 3D area) over faces (excluding degenerate)."""
    me = obj.data
    uv = uv_array(obj, layer)
    v = verts(me)
    lt = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_total", lt)
    ls = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    a3 = a2 = 0.0
    for s, t in zip(ls, lt):
        idx = np.arange(s, s + t)
        p = v[lv[idx]]
        q = uv[idx]
        for k in range(1, t - 1):
            a3 += 0.5 * np.linalg.norm(np.cross(p[k] - p[0], p[k + 1] - p[0]))
            d1, d2 = q[k] - q[0], q[k + 1] - q[0]
            a2 += 0.5 * abs(d1[0] * d2[1] - d1[1] * d2[0])
    return float(math.sqrt(a2 * atlas_px * atlas_px / max(a3, 1e-12)))


# ----------------------------------------------------------------------------------------------- attributes

def set_point_color(obj, name, rgba):
    me = obj.data
    if name in me.color_attributes:
        me.color_attributes.remove(me.color_attributes[name])
    at = me.color_attributes.new(name=name, type="FLOAT_COLOR", domain="POINT")
    at.data.foreach_set("color", np.asarray(rgba, dtype=np.float32).ravel())
    return at


def set_corner_color_byte(obj, name, rgb_per_vertex, make_active=True):
    """Byte colour attribute on face corners from a per-vertex RGB array (0..1)."""
    me = obj.data
    if name in me.color_attributes:
        me.color_attributes.remove(me.color_attributes[name])
    at = me.color_attributes.new(name=name, type="BYTE_COLOR", domain="CORNER")
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    rgb = np.asarray(rgb_per_vertex, dtype=np.float32)[lv]
    rgba = np.concatenate([rgb, np.ones((len(rgb), 1), np.float32)], axis=1)
    at.data.foreach_set("color", rgba.ravel())
    if make_active:
        me.color_attributes.active_color = at
        try:
            me.color_attributes.render_color_index = me.color_attributes.find(name)
        except Exception:
            pass
    return at


# ----------------------------------------------------------------------------------------------- bake

def setup_cycles(samples=16, threads=6):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.threads_mode = "FIXED"
    sc.render.threads = threads
    return sc


def float_image(name, size, color=(0, 0, 0, 0)):
    if name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[name])
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    px = np.empty(size * size * 4, dtype=np.float32)
    px.reshape(-1, 4)[:] = color
    img.pixels.foreach_set(px)
    return img


def image_array(img) -> np.ndarray:
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)[::-1].copy()  # top row first (PNG orientation)


def emit_material(name, attr_name):
    """Emission = colour attribute (bake EMIT)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_type = "GEOMETRY"
    at.attribute_name = attr_name
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def diffuse_material(name, rgb=(0.8, 0.8, 0.8)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    return mat


def bake_target_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "bake_target"
    nt.nodes.active = tex
    return mat


def hide_from_rays(obj):
    for attr in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter", "visible_shadow"):
        if hasattr(obj, attr):
            setattr(obj, attr, False)


def bake_selected_to_active(low, highs, img, bake_type, *, cage=0.04, max_dist=0.12, margin=12, samples=4,
                            normal_space="TANGENT", high_material=None, margin_type="EXTEND"):
    """Bake highs -> low into img (low's single material must be the bake target material)."""
    sc = bpy.context.scene
    sc.cycles.samples = samples
    mat = low.data.materials[0]
    node = mat.node_tree.nodes["bake_target"]
    node.image = img
    mat.node_tree.nodes.active = node
    saved = []
    if high_material is not None:
        for h in highs:
            saved.append([s.material for s in h.material_slots])
            h.data.materials.clear()
            h.data.materials.append(high_material)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for h in highs:
        h.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    t0 = time.time()
    kw = dict(type=bake_type, use_selected_to_active=True, cage_extrusion=cage, max_ray_distance=max_dist,
              margin=margin, margin_type=margin_type, use_clear=False, target="IMAGE_TEXTURES")
    if bake_type == "NORMAL":
        kw.update(normal_space=normal_space, normal_r="POS_X", normal_g="POS_Y", normal_b="POS_Z")
    bpy.ops.object.bake(**kw)
    if high_material is not None:
        for h, mats in zip(highs, saved):
            h.data.materials.clear()
            for m in mats:
                h.data.materials.append(m)
    log(f"bake {bake_type} {img.name} {img.size[0]}px {time.time() - t0:.1f}s")
    return img


# ----------------------------------------------------------------------------------------------- materials

def _occlusion_group():
    name = "glTF Material Output"
    g = bpy.data.node_groups.get(name)
    if g is None:
        g = bpy.data.node_groups.new(name, "ShaderNodeTree")
    # Blender 5.2's importer unconditionally resolves these official settings
    # sockets during scratch re-import, even when the extensions are absent.
    # Add missing inputs to old groups without changing existing connections.
    # Source: installed io_scene_gltf2/blender/com/material_helpers.py.
    expected = {"Occlusion": 1.0, "Thickness": 0.0, "Dispersion": 0.0,
                "Iridescence Factor": 0.0, "Iridescence Thickness Minimum": 100.0}
    have = {s.name for s in g.interface.items_tree if s.item_type == "SOCKET" and s.in_out == "INPUT"}
    for socket_name, default in expected.items():
        if socket_name not in have:
            socket = g.interface.new_socket(socket_name, in_out="INPUT", socket_type="NodeSocketFloat")
            socket.default_value = default
    return g


def load_image(path, colorspace):
    path = str(path)
    for img in bpy.data.images:
        if img.filepath and os.path.normcase(bpy.path.abspath(img.filepath)) == os.path.normcase(path):
            img.colorspace_settings.name = colorspace
            return img
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = colorspace
    return img


def pbr_material(name, albedo, normal=None, orm=None, *, alpha_clip=None, vertex_color=None, double_sided=False,
                 normal_strength=1.0):
    """glTF-exportable material. albedo/normal/orm are PNG paths. alpha_clip=cutoff makes alphaMode MASK.
    vertex_color='Col' multiplies that colour attribute into the base colour (COLOR_0)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    out = nodes.get("Material Output")
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    ta = nodes.new("ShaderNodeTexImage")
    ta.image = load_image(albedo, "sRGB")
    ta.interpolation = "Linear"
    links.new(uv.outputs["UV"], ta.inputs["Vector"])
    col = ta.outputs["Color"]
    if vertex_color:
        vc = nodes.new("ShaderNodeVertexColor")
        vc.layer_name = vertex_color
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        links.new(col, mix.inputs["A"])
        links.new(vc.outputs["Color"], mix.inputs["B"])
        col = mix.outputs["Result"]
    links.new(col, bsdf.inputs["Base Color"])
    if alpha_clip is not None:
        lt = nodes.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        lt.inputs[1].default_value = float(alpha_clip)
        sub = nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[0].default_value = 1.0
        links.new(ta.outputs["Alpha"], lt.inputs[0])
        links.new(lt.outputs["Value"], sub.inputs[1])
        links.new(sub.outputs["Value"], bsdf.inputs["Alpha"])
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            pass
    if normal:
        tn = nodes.new("ShaderNodeTexImage")
        tn.image = load_image(normal, "Non-Color")
        links.new(uv.outputs["UV"], tn.inputs["Vector"])
        nm = nodes.new("ShaderNodeNormalMap")
        nm.space = "TANGENT"
        nm.uv_map = "UVMap"
        nm.inputs["Strength"].default_value = normal_strength
        links.new(tn.outputs["Color"], nm.inputs["Color"])
        links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if orm:
        to = nodes.new("ShaderNodeTexImage")
        to.image = load_image(orm, "Non-Color")
        links.new(uv.outputs["UV"], to.inputs["Vector"])
        sep = nodes.new("ShaderNodeSeparateColor")
        links.new(to.outputs["Color"], sep.inputs["Color"])
        links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        grp = nodes.new("ShaderNodeGroup")
        grp.node_tree = _occlusion_group()
        links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.85
        bsdf.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = not double_sided
    mat["xex_double_sided"] = bool(double_sided)
    return mat


# ----------------------------------------------------------------------------------------------- checks

def mesh_report(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    # connected parts
    seen, parts = set(), 0
    for v in bm.verts:
        if v.index in seen:
            continue
        parts += 1
        stack = [v]
        seen.add(v.index)
        while stack:
            x = stack.pop()
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
    bm.free()
    v = verts(me) @ np.array(obj.matrix_world)[:3, :3].T + np.array(obj.matrix_world)[:3, 3]
    return {"triangles": tri_count(obj), "vertices": len(me.vertices), "non_manifold_edges": non_manifold,
            "boundary_edges": boundary, "zero_area_faces": zero, "loose_verts": loose, "parts": parts,
            "bounds_min": [round(float(x), 4) for x in v.min(0)], "bounds_max": [round(float(x), 4) for x in v.max(0)]}


def coplanar_overlaps(obj, tol_d=0.0015, tol_n=0.9995, max_report=20):
    """Pairs of triangles from different connected parts that lie in the same plane and overlap (z-fight risk)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.faces.ensure_lookup_table()
    # part id per vertex
    part = {}
    pid = 0
    for v in bm.verts:
        if v.index in part:
            continue
        stack = [v]
        part[v.index] = pid
        while stack:
            x = stack.pop()
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in part:
                    part[o.index] = pid
                    stack.append(o)
        pid += 1
    if pid < 2:
        bm.free()
        return []
    tris = [(f.normal.copy(), f.calc_center_median(), [l.vert.co.copy() for l in f.loops], part[f.verts[0].index])
            for f in bm.faces if f.calc_area() > 1e-8]
    bm.free()
    # bucket by quantised plane
    buckets = {}
    for i, (n, c, pts, p) in enumerate(tris):
        key = (round(n.x, 2), round(n.y, 2), round(n.z, 2), round(n.dot(c) / 0.01))
        buckets.setdefault(key, []).append(i)
    found = []
    for idx in buckets.values():
        if len(idx) < 2:
            continue
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if tris[i][3] == tris[j][3]:
                    continue
                ni, nj = tris[i][0], tris[j][0]
                if abs(ni.dot(nj)) < tol_n or abs(ni.dot(tris[j][1]) - ni.dot(tris[i][1])) > tol_d:
                    continue
                if _tri_overlap_2d(tris[i][2], tris[j][2], ni):
                    found.append((i, j))
                    if len(found) >= max_report:
                        return found
    return found


def _tri_overlap_2d(t1, t2, n):
    ax = max(range(3), key=lambda k: abs(n[k]))
    i1, i2 = [k for k in range(3) if k != ax]
    A = [(p[i1], p[i2]) for p in t1]
    B = [(p[i1], p[i2]) for p in t2]

    def axes(T):
        return [(-(T[(k + 1) % 3][1] - T[k][1]), T[(k + 1) % 3][0] - T[k][0]) for k in range(3)]

    for ax2 in axes(A) + axes(B):
        pa = [ax2[0] * p[0] + ax2[1] * p[1] for p in A]
        pb = [ax2[0] * p[0] + ax2[1] * p[1] for p in B]
        if max(pa) <= min(pb) + 1e-6 or max(pb) <= min(pa) + 1e-6:
            return False
    return True


# ----------------------------------------------------------------------------------------------- colliders

def hull2d(pts):
    pts = sorted(set(map(tuple, np.round(np.asarray(pts, dtype=np.float64), 5))))
    if len(pts) < 3:
        return [list(p) for p in pts]

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
    return [list(p) for p in lower[:-1] + upper[:-1]]


def simplify_hull2d(poly, max_pts=12):
    """Greedy removal of the vertex whose removal adds the least area while staying conservative (outward):
    the result is the hull of a subset, then pushed out so it still contains the original."""
    poly = [np.array(p, dtype=np.float64) for p in poly]
    while len(poly) > max_pts:
        best, bi = None, None
        for i in range(len(poly)):
            a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
            area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) * 0.5
            if best is None or area < best:
                best, bi = area, i
        poly.pop(bi)
    P = np.array(poly)
    return P


def blender_to_gltf(v):
    v = np.asarray(v, dtype=np.float64)
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1)


def footprint_xz(obj, max_pts=12, y_max=None):
    """Conservative convex footprint in glTF local XZ (CCW seen from +Y), from all vertices (or those below y_max)."""
    v = verts(obj.data)
    if y_max is not None:
        sel = v[:, 2] <= y_max
        if sel.sum() >= 3:
            v = v[sel]
    g = blender_to_gltf(v)
    hull = hull2d(g[:, [0, 2]])
    P = simplify_hull2d(hull, max_pts)
    # push out so every original point is inside
    c = P.mean(0)
    pts = g[:, [0, 2]]
    for _ in range(3):
        worst = 0.0
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            e = b - a
            nrm = np.array([e[1], -e[0]])
            nrm /= np.linalg.norm(nrm) + 1e-12
            if np.dot(nrm, c - a) > 0:
                nrm = -nrm
            d = (pts - a) @ nrm
            worst = max(worst, float(d.max()))
        if worst <= 1e-4:
            break
        P = c + (P - c) * (1.0 + (worst + 0.002) / max(np.linalg.norm(P - c, axis=1).min(), 0.05))
    # CCW in the x/z plane as seen from +Y (x right, z toward viewer): use standard signed area on (x, -z)
    area = 0.0
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        area += a[0] * b[1] - b[0] * a[1]
    if area < 0:
        P = P[::-1]
    return [[round(float(x), 4), round(float(z), 4)] for x, z in P]


def collider_hull(obj, name, max_tris=64):
    """Convex hull proxy of obj (decimated to <= max_tris), closed and manifold."""
    v = verts(obj.data)
    h = convex_hull_object(name, v)
    if tri_count(h) > max_tris:
        d = decimate_to(h, max_tris, name=name + "_d")
        delete([h])
        h = convex_hull_object(name, verts(d.data))
        delete([d])
    triangulate(h)
    h.name = name
    return h


def box_object(name, size, center=(0, 0, 0)):
    sx, sy, sz = size
    cx, cy, cz = center
    v = np.array([[cx + x * sx / 2, cy + y * sy / 2, cz + z * sz / 2] for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)])
    f = [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    return mesh_from_arrays(name, v, f)


# ----------------------------------------------------------------------------------------------- export

def export_lod(obj, path, *, profile="prop", budget_class="prop", texture_dir=None, asset_id=None, notes=None,
               vertex_color="MATERIAL", materials="EXPORT", double_sided=(), inputs=None, copyright_text=None):
    from export_helper import export_glb
    loc = obj.location.copy()
    obj.location = (0, 0, 0)
    try:
        rec = export_glb([obj], Path(path), profile, receipt_path=Path(path).with_suffix(".receipt.json"),
                         texture_dir=texture_dir, asset_id=asset_id or Path(path).stem, budget_class=budget_class,
                         materials=materials, vertex_color=vertex_color, double_sided_materials=tuple(double_sided),
                         copyright_text=copyright_text or "Xexoria original procedural asset (nature_props); "
                         "no third-party content", inputs=inputs, notes=notes, reimport="scratch")
    finally:
        obj.location = loc
    return rec


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def args_after_dashdash():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
