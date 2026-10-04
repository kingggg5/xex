"""Measure the Quaternius Stylized Nature MegaKit (Standard, CC0) tree set.

Route A step 1 (trees v4), Claude lane. Read-only on the kit: every model is
imported alone into an empty factory scene; nothing is saved back.

For each model it records, as imported (glTF Y-up -> Blender Z-up, metres):
  triangles after triangulation (total and per material), mesh/material counts,
  texture files and pixel sizes, bounds/height, pivot (origin and min z),
  UV maps, vertex colours (COLOR_0 stats and height profile), normals
  (custom or not, how far they bend away from the flat card normal, how far
  they point outward from the crown centre), leaf-card islands and sizes.
It also records shape metrics at the decision-doc target height (section 4.1):
  trunk radius at 1 m, radius at ground and flare ratio, crown base, crown
  width / height, so the selection can be tied to the section 4.4 fail list.

Usage:
  blender -b --factory-startup --python measure_kit.py -- \
      --src <kit glTF dir> --out <measure.json> [--models A,B,...]
"""
import argparse
import json
import math
import os
import sys
import time

import bpy
import numpy as np

KIT_MODELS = ([f"CommonTree_{i}" for i in range(1, 6)] + [f"Pine_{i}" for i in range(1, 6)]
              + [f"TwistedTree_{i}" for i in range(1, 6)] + [f"DeadTree_{i}" for i in range(1, 6)]
              + ["Bush_Common", "Bush_Common_Flowers"])

# Target heights (decision doc 4.1). Twisted = landmark at broadleaf L; Dead = nominal M (later biomes).
TARGETS = {"CommonTree": ("broadleaf", 7.5), "Pine": ("conifer", 8.0), "Bush": ("bush", 1.2),
           "TwistedTree": ("landmark", 9.5), "DeadTree": ("dead", 7.5)}
SPEC = {
    "broadleaf": {"trunk_r_1m": [0.25, 0.42], "trunk_r_1m_M": 0.32, "flare_ratio": [1.8, 2.2],
                  "crown_base": [2.2, 3.0], "crown_width_ratio": [0.8, 1.1], "tris_lod0": [4000, 6000]},
    "conifer": {"trunk_r_1m": [0.22, 0.30], "trunk_r_1m_M": 0.22, "flare_ratio": [1.6, 1.6],
                "crown_base": [1.6, 2.4], "crown_width_ratio": [0.45, 0.6], "tris_lod0": [2500, 5000]},
    "bush": {"tris_lod0": [300, 900]},
    "landmark": {"trunk_r_1m": [0.42, 0.42], "flare_ratio": [1.8, 2.2], "crown_base": [2.2, 3.0],
                 "crown_width_ratio": [0.8, 1.1], "tris_lod0": [0, 9000]},
    "dead": {},
}


def family(name):
    for key in TARGETS:
        if name.startswith(key):
            return key
    return None


def args_after_dashes():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default=",".join(KIT_MODELS))
    return ap.parse_args(argv)


def get_array(collection, attr, count, width, dtype=np.float32):
    arr = np.empty(count * width, dtype=dtype)
    collection.foreach_get(attr, arr)
    return arr.reshape(count, width) if width > 1 else arr


def corner_vertex_indices(me):
    n = len(me.loops)
    try:
        return get_array(me.loops, "vertex_index", n, 1, np.int32)
    except Exception:
        attr = me.attributes[".corner_vert"]
        return get_array(attr.data, "value", n, 1, np.int32)


def convex_hull_area(points):
    pts = sorted(set(map(tuple, np.round(points, 5))))
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
    area = 0.0
    for i in range(len(hull)):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % len(hull)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def lobes(xy, z, centre, z0, z1, ref_r):
    sel = (z >= z0) & (z <= z1)
    pts = xy[sel] - np.asarray(centre)
    if len(pts) < 8:
        return None
    ang = np.arctan2(pts[:, 1], pts[:, 0])
    rad = np.linalg.norm(pts, axis=1)
    bins = 24
    prof = np.zeros(bins)
    for a, r in zip(ang, rad):
        b = int((a + math.pi) / (2 * math.pi) * bins) % bins
        prof[b] = max(prof[b], r)
    med = float(np.median(prof[prof > 0])) if np.any(prof > 0) else 0.0
    peaks = 0
    for i in range(bins):
        if prof[i] > 1.15 * med and prof[i] >= prof[(i - 1) % bins] and prof[i] >= prof[(i + 1) % bins] and prof[i] > 1.3 * ref_r:
            peaks += 1
    return {"lobe_peaks_est": peaks, "profile_median_r": round(med, 3), "profile_max_r": round(float(prof.max()), 3)}


def bark_sections(meshes, foliage_names, ground_z, base_xy, s, heights):
    """True cross-sections of the bark mesh at the given heights above the ground plane (target scale).

    Bark faces are copied into a bmesh, welded (glTF split vertices), scaled to the target height
    and cut with bmesh.ops.bisect_plane. Each connected loop of cut edges is one stem or limb;
    its convex-hull area gives an equivalent radius.
    """
    import bmesh
    from mathutils import Matrix
    bm = bmesh.new()
    for ob in meshes:
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        tmp.transform(ob.matrix_world)
        foliage_idx = {i for i, m in enumerate(ob.data.materials) if m and m.name.startswith(foliage_names)}
        bmesh.ops.delete(tmp, geom=[f for f in tmp.faces if f.material_index in foliage_idx], context="FACES")
        me_tmp = bpy.data.meshes.new("tmp_bark")
        tmp.to_mesh(me_tmp)
        tmp.free()
        bm.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    if not bm.faces:
        bm.free()
        return None
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    m = Matrix.Translation((-base_xy[0] * s, -base_xy[1] * s, -ground_z * s)) @ Matrix.Scale(s, 4)
    bm.transform(m)
    out = []
    for h in heights:
        res = bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                                     dist=1e-5, plane_co=(0, 0, h), plane_no=(0, 0, 1))
        cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        cut_set = set(cut_edges)
        seen = set()
        loops = []
        for e in cut_edges:
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
            if area <= 0:
                continue
            c = pts.mean(axis=0)
            loops.append({"r_equiv": math.sqrt(area / math.pi), "centre": c, "closed": all(
                sum(1 for e2 in v.link_edges if e2 in cut_set) == 2 for ed in comp for v in ed.verts)})
        loops.sort(key=lambda l: l["r_equiv"], reverse=True)
        main = loops[0] if loops else None
        out.append({"height_m": h, "loops": len(loops),
                    "loops_r_over_5cm": sum(1 for l in loops if l["r_equiv"] >= 0.05),
                    "main_r_m": round(main["r_equiv"], 3) if main else None,
                    "main_centre_xy_m": [round(float(v), 3) for v in main["centre"]] if main else None,
                    "main_closed": main["closed"] if main else None,
                    "other_r_m": [round(l["r_equiv"], 3) for l in loops[1:6]]})
    bm.free()
    return out


def measure_model(src_dir, name):
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = os.path.join(src_dir, name + ".gltf")
    bpy.ops.import_scene.gltf(filepath=path)
    gltf = json.load(open(path, encoding="utf-8"))
    meshes = [ob for ob in bpy.data.objects if ob.type == "MESH"]
    out = {"file": name + ".gltf", "objects": [], "gltf_materials": [], "textures": []}
    for m in gltf.get("materials", []):
        out["gltf_materials"].append({k: m.get(k) for k in ("name", "alphaMode", "alphaCutoff", "doubleSided")} |
                                     {"has_normalTexture": "normalTexture" in m,
                                      "metallicFactor": m.get("pbrMetallicRoughness", {}).get("metallicFactor"),
                                      "roughnessFactor": m.get("pbrMetallicRoughness", {}).get("roughnessFactor", 1.0)})
    all_world = []
    per_mat = {}
    foliage_names = ("Leaves", "Leaf", "Flowers")
    tri_total = 0
    mat_names = set()
    for ob in meshes:
        me = ob.data
        me.calc_loop_triangles()
        n_v, n_l, n_p, n_t = len(me.vertices), len(me.loops), len(me.polygons), len(me.loop_triangles)
        tri_total += n_t
        co = get_array(me.vertices, "co", n_v, 3)
        mw = np.array(ob.matrix_world, dtype=np.float64)
        world = co @ mw[:3, :3].T + mw[:3, 3]
        all_world.append(world)
        tri_mat = get_array(me.loop_triangles, "material_index", n_t, 1, np.int32)
        poly_mat = get_array(me.polygons, "material_index", n_p, 1, np.int32)
        loop_start = get_array(me.polygons, "loop_start", n_p, 1, np.int32)
        loop_total = get_array(me.polygons, "loop_total", n_p, 1, np.int32)
        poly_normal = get_array(me.polygons, "normal", n_p, 3)
        corner_vert = corner_vertex_indices(me)
        corner_normal = get_array(me.corner_normals, "vector", n_l, 3)
        corner_poly = np.repeat(np.arange(n_p), loop_total)
        color = None
        ca = me.color_attributes.active_color or (me.color_attributes[0] if len(me.color_attributes) else None)
        if ca is not None and ca.domain == "CORNER":
            color = get_array(ca.data, "color", n_l, 4)
        ob_entry = {"name": ob.name, "mesh": me.name, "vertices": n_v, "corners": n_l, "polygons": n_p,
                    "triangles": n_t, "location": [round(v, 4) for v in ob.location],
                    "rotation_euler": [round(v, 4) for v in ob.rotation_euler], "scale": [round(v, 4) for v in ob.scale],
                    "uv_maps": [uv.name for uv in me.uv_layers],
                    "color_attributes": [{"name": c.name, "domain": c.domain, "data_type": c.data_type} for c in me.color_attributes],
                    "has_custom_normals": bool(me.has_custom_normals),
                    "polygon_sides": {str(k): int(v) for k, v in zip(*np.unique(loop_total, return_counts=True))},
                    "material_slots": [m.name if m else None for m in me.materials]}
        out["objects"].append(ob_entry)
        for slot, mat in enumerate(me.materials):
            if mat is None:
                continue
            mat_names.add(mat.name)
            entry = per_mat.setdefault(mat.name, {"triangles": 0, "polygons": 0, "kind": "foliage" if mat.name.startswith(foliage_names) else "bark",
                                                  "_world": [], "_corner_world": [], "_corner_normal": [], "_face_normal": [],
                                                  "_color": [], "_islands": 0, "_island_diag": []})
            entry["triangles"] += int((tri_mat == slot).sum())
            psel = np.nonzero(poly_mat == slot)[0]
            entry["polygons"] += int(len(psel))
            csel = np.isin(corner_poly, psel)
            vidx = corner_vert[csel]
            nm = np.array(ob.matrix_world.to_3x3().inverted().transposed(), dtype=np.float64)
            entry["_corner_world"].append(world[vidx])
            cn = corner_normal[csel] @ nm.T
            cn /= np.maximum(np.linalg.norm(cn, axis=1, keepdims=True), 1e-9)
            entry["_corner_normal"].append(cn)
            fn = poly_normal[corner_poly[csel]] @ nm.T
            fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
            entry["_face_normal"].append(fn)
            if color is not None:
                entry["_color"].append(color[csel])
            used_v = np.unique(vidx)
            entry["_world"].append(world[used_v])
            # islands (connected components over polygons of this material)
            parent = {int(v): int(v) for v in used_v}

            def find(a):
                while parent[a] != a:
                    parent[a] = parent[parent[a]]
                    a = parent[a]
                return a
            for p in psel:
                s, t = loop_start[p], loop_total[p]
                vs = corner_vert[s:s + t]
                r0 = find(int(vs[0]))
                for v in vs[1:]:
                    r = find(int(v))
                    if r != r0:
                        parent[r] = r0
            groups = {}
            for v in used_v:
                groups.setdefault(find(int(v)), []).append(int(v))
            entry["_islands"] += len(groups)
            if entry["kind"] == "foliage":
                for g in groups.values():
                    pts = world[g]
                    ext = pts.max(axis=0) - pts.min(axis=0)
                    entry["_island_diag"].append(float(np.linalg.norm(ext)))
    world = np.concatenate(all_world)
    bmin, bmax = world.min(axis=0), world.max(axis=0)
    dims = bmax - bmin
    height = float(dims[2])
    # The kit's ground plane is the object origin (z = 0). Every model also carries a short skirt of
    # geometry below the origin (buried trunk base / lowest cards) so it sits into uneven terrain.
    ground_z = float(meshes[0].matrix_world.translation.z) if meshes else 0.0
    visible_h = float(bmax[2]) - ground_z
    fam = family(name)
    kind, target_h = TARGETS[fam]
    s = target_h / visible_h if visible_h > 0 else 1.0
    # textures from the imported node trees
    seen = set()
    for mat in bpy.data.materials:
        if mat.node_tree is None:
            continue
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage" and node.image and node.image.name not in seen:
                seen.add(node.image.name)
                img = node.image
                to = [(l.to_node.bl_idname, l.to_socket.name) for l in mat.node_tree.links if l.from_node == node]
                uri = next((i.get("uri") for i in gltf.get("images", []) if i.get("name") == img.name), None)
                out["textures"].append({"image": img.name, "file": uri, "size_px": list(img.size),
                                        "colorspace": img.colorspace_settings.name, "channels": img.channels,
                                        "is_float": img.is_float, "used_by_material": mat.name, "feeds": to})
    # per-material summaries
    mats_out = {}
    base_z = ground_z
    for mname, e in per_mat.items():
        cw = np.concatenate(e["_corner_world"]) if e["_corner_world"] else np.zeros((0, 3))
        cn = np.concatenate(e["_corner_normal"]) if e["_corner_normal"] else np.zeros((0, 3))
        fnm = np.concatenate(e["_face_normal"]) if e["_face_normal"] else np.zeros((0, 3))
        wv = np.concatenate(e["_world"]) if e["_world"] else np.zeros((0, 3))
        d = {"kind": e["kind"], "triangles": e["triangles"], "polygons": e["polygons"], "islands": e["_islands"]}
        if len(cw):
            centre = (wv.max(axis=0) + wv.min(axis=0)) / 2.0
            radial = cw - centre
            radial /= np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1e-9)
            dot_radial = (cn * radial).sum(axis=1)
            dot_face = np.abs((cn * fnm).sum(axis=1))
            d["normals"] = {"mean_abs_dot_with_face_normal": round(float(dot_face.mean()), 3),
                            "share_bent_over_25deg": round(float((dot_face < math.cos(math.radians(25))).mean()), 3),
                            "mean_dot_with_outward_radial": round(float(dot_radial.mean()), 3),
                            "share_outward_dot_over_0_5": round(float((dot_radial > 0.5).mean()), 3)}
            zs = (cw[:, 2] - base_z) * s
            if e["_color"]:
                col = np.concatenate(e["_color"])
                lum = col[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
                prof = []
                for b in range(10):
                    lo, hi = target_h * b / 10, target_h * (b + 1) / 10
                    sel = (zs >= lo) & (zs < hi + (1e-6 if b == 9 else 0))
                    prof.append(round(float(lum[sel].mean()), 3) if sel.any() else None)
                corr = float(np.corrcoef(zs, lum)[0, 1]) if lum.std() > 1e-6 and zs.std() > 1e-6 else None
                d["color_0"] = {"linear_rgb_min": [round(float(v), 3) for v in col[:, :3].min(axis=0)],
                                "linear_rgb_max": [round(float(v), 3) for v in col[:, :3].max(axis=0)],
                                "linear_rgb_mean": [round(float(v), 3) for v in col[:, :3].mean(axis=0)],
                                "alpha_min": round(float(col[:, 3].min()), 3),
                                "is_constant_white": bool(np.allclose(col[:, :3], 1.0, atol=1e-3)),
                                "share_lum_below_0_5": round(float((lum < 0.5).mean()), 3),
                                "corr_lum_vs_height": None if corr is None else round(corr, 3),
                                "mean_lum_by_height_decile_at_target": prof}
        if e["kind"] == "foliage" and e["_island_diag"]:
            diag = np.array(e["_island_diag"]) * s
            d["cards_at_target_scale"] = {"count": len(diag), "diag_m_median": round(float(np.median(diag)), 3),
                                          "diag_m_p10": round(float(np.percentile(diag, 10)), 3),
                                          "diag_m_p90": round(float(np.percentile(diag, 90)), 3)}
        mats_out[mname] = d
    # shape metrics at the target height
    bark_pts = np.concatenate([np.concatenate(e["_world"]) for e in per_mat.values() if e["kind"] == "bark" and e["_world"]]) \
        if any(e["kind"] == "bark" for e in per_mat.values()) else np.zeros((0, 3))
    leaf_pts = np.concatenate([np.concatenate(e["_world"]) for e in per_mat.values() if e["kind"] == "foliage" and e["_world"]]) \
        if any(e["kind"] == "foliage" for e in per_mat.values()) else np.zeros((0, 3))
    shape = {"kind": kind, "target_height_m": target_h, "ground_plane": "object origin z (kit convention)",
             "visible_height_imported_m": round(visible_h, 4),
             "buried_depth_below_origin_m": round(ground_z - float(bmin[2]), 4),
             "scale_to_target": round(s, 4)}
    near_ground = np.abs(world[:, 2] - ground_z) <= 0.03 * visible_h
    base_xy = world[near_ground][:, :2].mean(axis=0) if near_ground.any() else np.zeros(2)
    shape["ground_contact_centre_offset_from_origin_m_imported"] = [round(float(v), 4) for v in base_xy]
    if len(bark_pts):
        heights = [0.05, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
        secs = bark_sections(meshes, foliage_names, ground_z, base_xy, s, heights)
        shape["bark_sections_at_target"] = secs
        by_h = {sec["height_m"]: sec for sec in secs or []}
        r1 = (by_h.get(1.0) or {}).get("main_r_m")
        r0 = (by_h.get(0.05) or {}).get("main_r_m")
        shape["trunk_radius_1m_m"] = r1
        shape["trunk_radius_ground_m"] = r0
        shape["flare_ratio_ground_over_1m"] = round(r0 / r1, 2) if r0 and r1 else None
        # first height where the trunk splits into several limbs of >= 5 cm radius
        split = next((sec["height_m"] for sec in secs or [] if sec["loops_r_over_5cm"] >= 2), None)
        shape["first_split_height_m"] = split
        z = (bark_pts[:, 2] - base_z) * s
        xy = (bark_pts[:, :2] - base_xy) * s
        centre = (by_h.get(1.0) or {}).get("main_centre_xy_m")
        if centre and r1:
            shape["flare_lobes"] = lobes(xy, z, centre, 0.0, 0.2, r1)
    if len(leaf_pts):
        zl = (leaf_pts[:, 2] - base_z) * s
        xyl = (leaf_pts[:, :2] - base_xy) * s
        ext = xyl.max(axis=0) - xyl.min(axis=0)
        shape["crown_base_m_p1"] = round(float(np.percentile(zl, 1)), 3)
        shape["crown_base_m_p5"] = round(float(np.percentile(zl, 5)), 3)
        shape["crown_lowest_m"] = round(float(zl.min()), 3)
        shape["crown_top_m"] = round(float(zl.max()), 3)
        shape["crown_extent_xy_m"] = [round(float(v), 3) for v in ext]
        shape["crown_width_m"] = round(float(ext.mean()), 3)
        shape["crown_width_over_height"] = round(float(ext.mean()) / target_h, 3)
        shape["crown_centre_offset_xy_m"] = [round(float(v), 3) for v in (xyl.max(axis=0) + xyl.min(axis=0)) / 2]
    spec = SPEC.get(kind, {})
    checks = {}
    if "tris_lod0" in spec:
        lo, hi = spec["tris_lod0"]
        checks["triangles_within_lod0_budget"] = bool(lo <= tri_total <= hi)
    if "trunk_r_1m" in spec and shape.get("trunk_radius_1m_m") is not None:
        checks["trunk_radius_1m_vs_spec_min"] = round(shape["trunk_radius_1m_m"] / spec["trunk_r_1m"][0], 2)
    if "flare_ratio" in spec and shape.get("flare_ratio_ground_over_1m") is not None:
        checks["flare_meets_spec_min"] = bool(shape["flare_ratio_ground_over_1m"] >= spec["flare_ratio"][0])
    if "crown_base" in spec and "crown_base_m_p5" in shape:
        lo, hi = spec["crown_base"]
        checks["crown_base_in_spec"] = bool(lo <= shape["crown_base_m_p5"] <= hi)
    if "crown_width_ratio" in spec and "crown_width_over_height" in shape:
        lo, hi = spec["crown_width_ratio"]
        checks["crown_width_ratio_in_spec"] = bool(lo <= shape["crown_width_over_height"] <= hi)
    out.update({
        "family": fam, "kind": kind,
        "triangles_total": tri_total,
        "mesh_objects": len(meshes),
        "materials": sorted(mat_names),
        "material_count": len(mat_names),
        "per_material": mats_out,
        "bounds_imported_m": {"min": [round(float(v), 4) for v in bmin], "max": [round(float(v), 4) for v in bmax],
                              "size": [round(float(v), 4) for v in dims]},
        "height_imported_m": round(height, 4),
        "height_above_origin_imported_m": round(visible_h, 4),
        "pivot": {"origin_world": [round(v, 4) for v in meshes[0].matrix_world.translation] if meshes else None,
                  "min_z_m": round(float(bmin[2]), 4),
                  "lowest_vertex_at_origin": bool(abs(float(bmin[2]) - ground_z) < 0.01),
                  "note": "origin is the ground plane; geometry continues below it by buried_depth_below_origin_m"},
        "shape_at_target": shape,
        "spec_checks_at_target": checks,
        "seconds": round(time.time() - t0, 2),
    })
    return out


def main():
    args = args_after_dashes()
    t0 = time.time()
    import addon_utils
    gltf_ver = None
    for mod in addon_utils.modules():
        if mod.__name__.endswith("io_scene_gltf2"):
            gltf_ver = ".".join(map(str, mod.bl_info.get("version", ())))
    result = {"label": "MEASUREMENT (Blender headless import; no renders)",
              "generated_ict": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
              "blender": bpy.app.version_string, "gltf_importer": gltf_ver,
              "importer_options": "defaults (merge_vertices=False, import_shading=NORMALS)",
              "source_dir": args.src,
              "units": "metres; Blender Z-up after the importer's Y-up conversion",
              "triangles_method": "Mesh.calc_loop_triangles() after import (equals triangulation)",
              "target_heights_m": {k: v[1] for k, v in TARGETS.items()},
              "spec_reference": "docs/reviews/2026-10-02-trees-free-assets-decision.md sections 4.1 and 4.3",
              "models": {}}
    for name in args.models.split(","):
        print("MEASURE", name, flush=True)
        result["models"][name] = measure_model(args.src, name)
        print("MEASURED", name, result["models"][name]["triangles_total"], result["models"][name]["height_imported_m"], flush=True)
    result["seconds_total"] = round(time.time() - t0, 1)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    print("WROTE", args.out)


main()
