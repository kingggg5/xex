"""Probe the leaf-card / bark structure of the 7 Route A picks (read-only on the kit).

Route A step 2 (stylization) groundwork. Imports each kit glTF into an empty factory scene (in-memory copy;
nothing is saved) and records, per material: polygon sides, islands (cards), per-card UV bounds, card size,
the world direction of the card's +V texture axis, and bark island sizes and texel density. The stylize
script relies on these facts (e.g. "every leaf card maps the full 0-1 UV square").

Usage:
  blender -b --factory-startup --python probe_cards.py -- --src <kit glTF dir> --out <json> [--models A,B]
"""
import argparse
import json
import math
import sys

import bpy
import numpy as np

PICKS = ["CommonTree_2", "CommonTree_5", "CommonTree_1", "Pine_2", "Pine_5", "Bush_Common_Flowers", "Bush_Common"]
FOLIAGE = ("Leaves", "Leaf", "Flowers")


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default=",".join(PICKS))
    a, _ = ap.parse_known_args(argv)
    return a


def arr(coll, attr, n, w, dt=np.float32):
    a = np.empty(n * w, dtype=dt)
    coll.foreach_get(attr, a)
    return a.reshape(n, w) if w > 1 else a


def islands(poly_verts):
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for vs in poly_verts:
        r0 = find(vs[0])
        for v in vs[1:]:
            r = find(v)
            if r != r0:
                parent[r] = r0
    groups = {}
    for pi, vs in enumerate(poly_verts):
        groups.setdefault(find(vs[0]), []).append(pi)
    return list(groups.values())


def probe(src, name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=f"{src}/{name}.gltf")
    ob = [o for o in bpy.data.objects if o.type == "MESH"][0]
    me = ob.data
    nv, nl, npoly = len(me.vertices), len(me.loops), len(me.polygons)
    co = arr(me.vertices, "co", nv, 3)
    lstart = arr(me.polygons, "loop_start", npoly, 1, np.int32)
    ltot = arr(me.polygons, "loop_total", npoly, 1, np.int32)
    pmat = arr(me.polygons, "material_index", npoly, 1, np.int32)
    cvert = arr(me.attributes[".corner_vert"].data, "value", nl, 1, np.int32)
    uv = arr(me.uv_layers[0].uv, "vector", nl, 2)
    out = {"model": name, "object": ob.name, "vertices": nv, "polygons": npoly,
           "materials": [m.name for m in me.materials],
           "images": {m.name: [n.image.name + f" {tuple(n.image.size)}" for n in m.node_tree.nodes
                               if n.bl_idname == "ShaderNodeTexImage" and n.image] for m in me.materials},
           "per_material": {}}
    for mi, mat in enumerate(me.materials):
        psel = np.nonzero(pmat == mi)[0]
        pv = [list(cvert[lstart[p]:lstart[p] + ltot[p]]) for p in psel]
        groups = islands(pv)
        sides = np.unique(ltot[psel], return_counts=True)
        info = {"polygons": int(len(psel)), "sides": {str(int(k)): int(v) for k, v in zip(*sides)},
                "islands": len(groups)}
        uvb, sizes, tris, updots, cents = [], [], [], [], []
        for g in groups:
            polys = psel[g]
            loops = np.concatenate([np.arange(lstart[p], lstart[p] + ltot[p]) for p in polys])
            u = uv[loops]
            uvb.append([float(u[:, 0].min()), float(u[:, 1].min()), float(u[:, 0].max()), float(u[:, 1].max())])
            vs = np.unique(cvert[loops])
            p = co[vs]
            ext = p.max(0) - p.min(0)
            sizes.append(float(np.linalg.norm(ext)))
            tris.append(int(sum(ltot[q] - 2 for q in polys)))
            cents.append(p.mean(0).tolist())
            # world direction of +V across the island (least squares: P = P0 + du*a + dv*b)
            lv = cvert[loops]
            A = np.c_[np.ones(len(loops)), u - u.mean(0)]
            try:
                sol, *_ = np.linalg.lstsq(A, co[lv], rcond=None)
                b = sol[2]
                nb = np.linalg.norm(b)
                updots.append(float(b[2] / nb) if nb > 1e-9 else 0.0)
            except Exception:
                updots.append(0.0)
        uvb = np.array(uvb)
        info["island_uv_bounds_summary"] = {
            "u0_p5_p50_p95": np.percentile(uvb[:, 0], [5, 50, 95]).round(3).tolist(),
            "v0_p5_p50_p95": np.percentile(uvb[:, 1], [5, 50, 95]).round(3).tolist(),
            "u1_p5_p50_p95": np.percentile(uvb[:, 2], [5, 50, 95]).round(3).tolist(),
            "v1_p5_p50_p95": np.percentile(uvb[:, 3], [5, 50, 95]).round(3).tolist(),
            "share_full_square": float(np.mean((uvb[:, 0] < 0.02) & (uvb[:, 1] < 0.02) & (uvb[:, 2] > 0.98) & (uvb[:, 3] > 0.98))),
        }
        info["island_size_m_p10_p50_p90"] = np.percentile(sizes, [10, 50, 90]).round(3).tolist()
        info["tris_per_island"] = {str(k): int(v) for k, v in zip(*np.unique(tris, return_counts=True))}
        info["v_axis_world_up_dot_p10_p50_p90"] = np.percentile(updots, [10, 50, 90]).round(3).tolist()
        info["share_v_axis_pointing_down"] = float(np.mean(np.array(updots) < 0))
        c = np.array(cents)
        info["island_centroid_z_hist"] = np.histogram(c[:, 2], bins=12)[0].tolist()
        info["island_centroid_z_edges"] = np.round(np.histogram(c[:, 2], bins=12)[1], 3).tolist()
        if not mat.name.startswith(FOLIAGE):
            # texel density: sqrt(uv area * px^2 / world area)
            img = next((n.image for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage" and n.image
                        and "Normal" not in n.image.name), None)
            ua, wa = 0.0, 0.0
            for p in psel[:4000]:
                idx = np.arange(lstart[p], lstart[p] + ltot[p])
                pu = uv[idx]
                pw = co[cvert[idx]]
                for k in range(1, len(idx) - 1):
                    ua += abs(np.cross(pu[k] - pu[0], pu[k + 1] - pu[0])) / 2
                    wa += np.linalg.norm(np.cross(pw[k] - pw[0], pw[k + 1] - pw[0])) / 2
            if img is not None and wa > 0:
                info["texel_density_px_per_m_imported"] = round(math.sqrt(ua * img.size[0] * img.size[1] / wa), 1)
            big = sorted(((len(g), np.ptp(co[np.unique(np.concatenate([cvert[lstart[p]:lstart[p] + ltot[p]] for p in psel[g]]))], axis=0).round(3).tolist())
                          for g in groups), key=lambda t: -t[0])[:8]
            info["largest_islands_polys_and_extent_m"] = big
        out["per_material"][mat.name] = info
    ca = me.color_attributes
    out["color_attributes"] = [(c.name, c.domain, c.data_type) for c in ca]
    out["bounds"] = [co.min(0).round(4).tolist(), co.max(0).round(4).tolist()]
    return out


def main():
    a = parse()
    res = {"label": "PROBE (Blender headless import, read-only)", "blender": bpy.app.version_string, "models": {}}
    for m in a.models.split(","):
        res["models"][m] = probe(a.src, m)
        print("PROBED", m, flush=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print("WROTE", a.out)


main()
