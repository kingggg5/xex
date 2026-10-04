"""Stage 1 (Blender): build a kit from its recipes, unwrap and pack atlases, bake data maps, make LOD1/LOD2,
colliders and shadow proxies, and save one .blend per atlas plus kit.json and <atlas>_maps.npz in the cache.

  blender -b --factory-startup --python-exit-code 1 --python np_stage_bake.py -- --kit rocks [--atlas a,b]
          [--threads 6] [--ao-samples 64] [--only id1,id2]

Data maps per atlas (float, top row first): nrm_ts (tangent normal, OpenGL, 0..1), nrm_os (object/world normal,
-1..1), ao (0..1), pos (asset-local position, decoded to metres), aux (R asset index+1 / 256, G fine convexity,
B broad convexity, both 0.5 + 0.5 tanh(k / kappa)), plus UV triangles for exact coverage. The painter
(np_paint.py, system Python) turns these into albedo / normal / ORM PNGs.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
import time
import traceback
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import np_lib as L  # noqa: E402

POS_MIN = np.array([-4.0, -4.0, -1.5])
POS_SPAN = np.array([8.0, 8.0, 9.0])
KAPPA_FINE, KAPPA_BROAD = 25.0, 8.0


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--atlas", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--ao-samples", type=int, default=64)
    return ap.parse_args(L.args_after_dashdash())


def high_attrs(high, idx):
    me = high.data
    v, e, n = L.verts(me), L.edges(me), L.vnormals(me)
    kf = L.vertex_curvature(v, e, n, smooth_iters=2)
    kb = L.vertex_curvature(v, e, n, smooth_iters=24)
    pos01 = (v - POS_MIN) / POS_SPAN
    ones = np.ones((len(v), 1))
    L.set_point_color(high, "np_pos", np.concatenate([pos01, ones], 1))
    aux = np.stack([np.full(len(v), (idx + 1) / 256.0), 0.5 + 0.5 * np.tanh(kf / KAPPA_FINE),
                    0.5 + 0.5 * np.tanh(kb / KAPPA_BROAD), np.ones(len(v))], 1)
    L.set_point_color(high, "np_aux", aux)
    return {"k_fine_p05_p95": [round(float(np.percentile(kf, 5)), 2), round(float(np.percentile(kf, 95)), 2)],
            "k_broad_p05_p95": [round(float(np.percentile(kb, 5)), 2), round(float(np.percentile(kb, 95)), 2)]}


def uv_tris(obj):
    me = obj.data
    uv = L.uv_array(obj)
    out = []
    for p in me.polygons:
        idx = list(p.loop_indices)
        for k in range(1, len(idx) - 1):
            out.append([uv[idx[0]], uv[idx[k]], uv[idx[k + 1]]])
    return np.array(out, dtype=np.float32).reshape(-1, 3, 2)


def bake_atlas(atlas, members, highs, lods, ao_samples):
    px = int(atlas["data_px"])
    gap = 3.5 if atlas["budget_class"] == "building_module" else 1.6
    offs, x = [], 0.0
    for s in members:
        w = float(s["_info"]["size_m"][0])
        offs.append(x + w / 2)
        x += w + gap
    low_copies = []
    for lod, ox in zip(lods, offs):
        c = L.copy_object(lod, lod.name + "_bk")
        c.location = (ox, 0, 0)
        low_copies.append(c)
    for c in low_copies:
        L.apply_transform(c)
    bake_low = L.join(low_copies, f"{atlas['id']}__bakelow")
    bake_low.data.materials.clear()
    bake_low.data.materials.append(L.bake_target_material("np_bake_target"))
    L.hide_from_rays(bake_low)
    for h, ox in zip(highs, offs):
        h.location = (ox, 0, 0)
        if not h.data.materials:
            h.data.materials.append(L.diffuse_material("np_high_grey"))
    ground = L.box_object("np_ground", (x + 20, 30, 0.02), (x / 2, 0, -0.01))
    ground.data.materials.append(L.diffuse_material("np_ground_grey", (0.5, 0.5, 0.5)))
    Lmed = float(np.median([max(s["_info"]["size_m"]) for s in members]))
    cage, dist = 0.025 * Lmed + 0.01, 0.07 * Lmed + 0.03
    world = bpy.data.worlds.new("np_world")
    bpy.context.scene.world = world
    world.light_settings.distance = float(atlas["ao_distance"])
    imgs = {k: L.float_image(f"{atlas['id']}_{k}", px) for k in ("nrm_ts", "nrm_os", "ao", "pos", "aux")}
    t0 = time.time()
    L.bake_selected_to_active(bake_low, highs, imgs["nrm_ts"], "NORMAL", cage=cage, max_dist=dist, samples=4,
                              normal_space="TANGENT")
    L.bake_selected_to_active(bake_low, highs, imgs["nrm_os"], "NORMAL", cage=cage, max_dist=dist, samples=4,
                              normal_space="OBJECT")
    L.bake_selected_to_active(bake_low, highs, imgs["ao"], "AO", cage=cage, max_dist=dist, samples=ao_samples)
    L.bake_selected_to_active(bake_low, highs, imgs["pos"], "EMIT", cage=cage, max_dist=dist, samples=4,
                              high_material=L.emit_material("np_emit_pos", "np_pos"))
    L.bake_selected_to_active(bake_low, highs, imgs["aux"], "EMIT", cage=cage, max_dist=dist, samples=1,
                              high_material=L.emit_material("np_emit_aux", "np_aux"))
    maps = {}
    a = L.image_array(imgs["nrm_ts"])
    maps["nrm_ts"] = a[..., :3].astype(np.float16)
    a = L.image_array(imgs["nrm_os"])
    maps["nrm_os"] = (a[..., :3] * 2.0 - 1.0).astype(np.float16)
    maps["ao"] = L.image_array(imgs["ao"])[..., 0].astype(np.float16)
    a = L.image_array(imgs["pos"])
    maps["pos"] = (a[..., :3] * POS_SPAN + POS_MIN).astype(np.float32)
    maps["pos_alpha"] = a[..., 3].astype(np.float16)
    maps["aux"] = L.image_array(imgs["aux"])[..., :3].astype(np.float16)
    tris, owner = [], []
    for i, lod in enumerate(lods):
        t = uv_tris(lod)
        tris.append(t)
        owner.append(np.full(len(t), i + 1, dtype=np.int16))
    maps["uv_tris"] = np.concatenate(tris)
    maps["uv_owner"] = np.concatenate(owner)
    L.delete([bake_low, ground])
    for h in highs:
        h.location = (0, 0, 0)
    for img in imgs.values():
        bpy.data.images.remove(img)
    return maps, {"cage_m": round(cage, 4), "max_ray_m": round(dist, 4), "bake_s": round(time.time() - t0, 1),
                  "ao_samples": ao_samples, "ao_distance_m": atlas["ao_distance"]}


def shadow_proxy(lod0, tris, name, shrink=0.015):
    sp = L.decimate_to(lod0, tris, name=name)
    me = sp.data
    v, n = L.verts(me), L.vnormals(me)
    L.set_verts(me, v - n * shrink)
    for uvl in list(me.uv_layers):
        me.uv_layers.remove(uvl)
    sp.data.materials.clear()
    return sp


def main():
    args = parse()
    kit = importlib.import_module("kit_" + args.kit)
    out = Path(args.out) if args.out else L.CACHE / args.kit
    out.mkdir(parents=True, exist_ok=True)
    kit_json_path = out / "kit.json"
    kit_json = json.loads(kit_json_path.read_text(encoding="utf-8")) if kit_json_path.exists() else {
        "kit": kit.KIT, "assets": {}, "atlases": {}}
    kit_json.update({"kit": kit.KIT, "lib": L.LIB_VERSION, "blender": bpy.app.version_string,
                     "pos_min": POS_MIN.tolist(), "pos_span": POS_SPAN.tolist(),
                     "kappa_fine": KAPPA_FINE, "kappa_broad": KAPPA_BROAD})
    specs = kit.assets()
    only = set(filter(None, args.only.split(",")))
    want_atlas = set(filter(None, args.atlas.split(",")))
    builder = getattr(kit, "build_pair", None)
    t_all = time.time()
    for atlas in kit.ATLASES:
        if want_atlas and atlas["id"] not in want_atlas:
            continue
        members = [s for s in specs if s["atlas"] == atlas["id"] and (not only or s["id"] in only)]
        if not members:
            continue
        L.reset()
        L.setup_cycles(samples=4, threads=args.threads)
        highs, lods = [], []
        for idx, s in enumerate(members):
            t0 = time.time()
            if builder is not None:
                high, lod0, info, P = builder(s)
            else:
                import np_rock as R
                high, info, P = R.build_high(s)
                lod0 = L.decimate_to(high, int(s["lod0_tris"]), name=s["id"] + "__lod0")
                L.set_smooth(lod0)
            s["_info"], s["_params"] = info, P
            s["_curv"] = high_attrs(high, idx)
            highs.append(high)
            lods.append(lod0)
            L.log(f"{s['id']}: high {L.tri_count(high)} tris, lod0 {L.tri_count(lod0)} tris, {time.time() - t0:.1f}s")
        # ---- UVs: smart project, shrink buried/downward islands, pack all members into one atlas
        L.smart_project(lods, angle_deg=62.0, margin=0.003)
        for s, lod in zip(members, lods):
            h = float(s["_info"]["size_m"][2])
            n = L.shrink_islands(lod, lambda nrm, cen, h=h: nrm.z < -0.55 and cen.z < 0.12 * h + 0.02, 0.18)
            s["_shrunk_islands"] = n
        L.pack_atlas(lods, margin=0.007)
        maps, bake_info = bake_atlas(atlas, members, highs, lods, args.ao_samples)
        np.savez_compressed(out / f"{atlas['id']}_maps.npz", **maps)
        L.delete(highs)
        # ---- LOD1/LOD2, collider, shadow proxy, reports
        entries = []
        for s, lod0 in zip(members, lods):
            t = L.tri_count(lod0)
            lod1 = L.decimate_to(lod0, max(int(round(t * 0.5)), 12), name=s["id"] + "__lod1")
            lod2 = L.decimate_to(lod0, max(int(round(t * 0.22)), 8), name=s["id"] + "__lod2")
            for o in (lod1, lod2):
                L.set_smooth(o)
            col = L.collider_hull(lod0, s["id"] + "__collider", max_tris=48 if t < 2000 else 64)
            objs = {"lod0": lod0, "lod1": lod1, "lod2": lod2, "collider": col}
            if s.get("shadow_proxy"):
                objs["shadow"] = shadow_proxy(lod0, max(int(t * 0.12), 120), s["id"] + "__shadow")
            rep = {k: L.mesh_report(o) for k, o in objs.items()}
            rep["texel_density_px_m_albedo"] = round(L.texel_density(lod0, atlas["albedo_px"]), 1)
            entry = {k: v for k, v in s.items() if not k.startswith("_")}
            entry.update({"params_resolved": s["_params"], "info": s["_info"], "curvature": s["_curv"],
                          "shrunk_islands": s["_shrunk_islands"], "objects": {k: o.name for k, o in objs.items()},
                          "mesh": rep, "atlas_index": members.index(s) + 1, "blend": f"{atlas['id']}.blend"})
            kit_json["assets"][s["id"]] = entry
            entries.append(s["id"])
            L.log(f"{s['id']}: lods {rep['lod0']['triangles']}/{rep['lod1']['triangles']}/{rep['lod2']['triangles']}"
                  f" nm={rep['lod0']['non_manifold_edges']} td={rep['texel_density_px_m_albedo']}")
        kit_json["atlases"][atlas["id"]] = dict(atlas, members=entries, bake=bake_info,
                                                maps=f"{atlas['id']}_maps.npz")
        bpy.ops.wm.save_as_mainfile(filepath=str(out / f"{atlas['id']}.blend"), compress=True)
        L.write_json(kit_json_path, kit_json)
        L.log(f"atlas {atlas['id']} done ({len(members)} assets) total {time.time() - t_all:.1f}s")
    L.log("STAGE BAKE OK")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
