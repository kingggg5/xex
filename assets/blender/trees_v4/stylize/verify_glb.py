"""Verify the exported stylized GLBs by reading them back (Route A step 2, trees v4). System Python + numpy.

Parses the GLB container directly (JSON chunk + BIN chunk), so the check is independent of Blender:
triangles per primitive, bounds and pivot (glTF Y-up: ground = y 0), COLOR_0 type and range per material,
TEXCOORD_1 wind data (x = sway 0..1 rising with height, y = phase), custom normals (foliage normals bent away
from the flat card normal), materials (alphaMode MASK 0.45, doubleSided), images, and the extension list
(no KHR_meshopt_compression, no Draco).

Images: embedded (bufferView) or external (uri, written by the export helper into the shared
textures-shared/ folder; 2026-10-02 migration). External images must exist next to the GLB.
Accessors are read directly, so this runs on the helper GLBs, before the meshopt post-process.

Usage:
  python verify_glb.py --dir <export dir> --species a,b,c --out <json>
"""
import argparse
import hashlib
import json
import os
import struct
from urllib.parse import unquote

import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
BUDGET = {"broadleaf": ((4000, 6000), 1600), "conifer": ((2500, 5000), 1400), "bush": ((300, 900), 450)}


def read_glb(path):
    data = open(path, "rb").read()
    magic, ver, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and ver == 2, "not a GLB v2"
    off, js, bin_ = 12, None, None
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            bin_ = chunk
        off += 8 + clen
    return js, bin_


def accessor(js, bin_, idx):
    a = js["accessors"][idx]
    bv = js["bufferViews"][a["bufferView"]]
    dt = CT[a["componentType"]]
    n = NC[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    item = np.dtype(dt).itemsize * n
    if stride and stride != item:
        raw = np.frombuffer(bin_, np.uint8, count=stride * a["count"], offset=start).reshape(a["count"], stride)
        arr = raw[:, :item].copy().view(dt).reshape(a["count"], n)
    else:
        arr = np.frombuffer(bin_, dt, count=a["count"] * n, offset=start).reshape(a["count"], n)
    arr = arr.astype(np.float64)
    if a.get("normalized"):
        arr /= float(np.iinfo(dt).max)
    return arr, a


def image_record(js, image, glb_dir):
    """Size of an embedded (bufferView) or external (uri relative to the GLB) image."""
    rec = {"name": image.get("name"), "mimeType": image.get("mimeType")}
    if "bufferView" in image:
        rec.update(storage="embedded", bytes=js["bufferViews"][image["bufferView"]]["byteLength"])
        return rec
    uri = image.get("uri", "")
    if uri.startswith("data:"):
        rec.update(storage="data-uri", bytes=len(uri))
        return rec
    target = os.path.normpath(os.path.join(glb_dir, unquote(uri)))
    exists = os.path.isfile(target)
    rec.update(storage="external", uri=uri, exists=exists, bytes=os.path.getsize(target) if exists else None,
               sha256=hashlib.sha256(open(target, "rb").read()).hexdigest() if exists else None)
    return rec


def check(path, kind, lod):
    js, bin_ = read_glb(path)
    glb_dir = os.path.dirname(os.path.abspath(path))
    out = {"file": os.path.basename(path), "bytes": os.path.getsize(path),
           "generator": js.get("asset", {}).get("generator"), "copyright": js.get("asset", {}).get("copyright"),
           "extensionsUsed": js.get("extensionsUsed", []), "extensionsRequired": js.get("extensionsRequired", []),
           "nodes": [{"name": n.get("name"), "translation": n.get("translation"), "rotation": n.get("rotation"),
                      "scale": n.get("scale"), "extras": n.get("extras")} for n in js.get("nodes", [])],
           "images": [image_record(js, i, glb_dir) for i in js.get("images", [])],
           "materials": [], "primitives": []}
    for m in js.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        out["materials"].append({"name": m.get("name"), "alphaMode": m.get("alphaMode", "OPAQUE"),
                                 "alphaCutoff": m.get("alphaCutoff"), "doubleSided": m.get("doubleSided", False),
                                 "baseColorTexture": "baseColorTexture" in pbr, "normalTexture": "normalTexture" in m,
                                 "roughnessFactor": pbr.get("roughnessFactor"), "metallicFactor": pbr.get("metallicFactor")})
    tris_total = 0
    all_pos = []
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            attrs = prim["attributes"]
            pos, pa = accessor(js, bin_, attrs["POSITION"])
            idx, _ = accessor(js, bin_, prim["indices"])
            idx = idx.astype(np.int64).ravel()
            tris = len(idx) // 3
            tris_total += tris
            all_pos.append(pos)
            mat = js["materials"][prim["material"]]["name"] if "material" in prim else None
            p = {"material": mat, "triangles": tris, "vertices": len(pos), "attributes": sorted(attrs.keys()),
                 "mode": prim.get("mode", 4)}
            if "COLOR_0" in attrs:
                col, ca = accessor(js, bin_, attrs["COLOR_0"])
                lum = col[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
                p["COLOR_0"] = {"type": ca["type"], "componentType": ca["componentType"],
                                "lum_min": round(float(lum.min()), 3), "lum_p10": round(float(np.percentile(lum, 10)), 3),
                                "lum_p50": round(float(np.percentile(lum, 50)), 3), "lum_max": round(float(lum.max()), 3)}
            if "TEXCOORD_1" in attrs:
                w, _ = accessor(js, bin_, attrs["TEXCOORD_1"])
                y = pos[:, 1]
                low = y < 1.0
                p["TEXCOORD_1"] = {"x_sway_min": round(float(w[:, 0].min()), 3), "x_sway_max": round(float(w[:, 0].max()), 3),
                                   "x_sway_max_below_1m": round(float(w[low, 0].max()), 3) if low.any() else None,
                                   "corr_sway_vs_height": round(float(np.corrcoef(w[:, 0], y)[0, 1]), 3)
                                   if w[:, 0].std() > 1e-6 else None,
                                   "y_phase_unique": int(len(np.unique(np.round(w[:, 1], 4)))),
                                   "y_phase_min_max": [round(float(w[:, 1].min()), 3), round(float(w[:, 1].max()), 3)]}
            if "NORMAL" in attrs and prim.get("mode", 4) == 4:
                nrm, _ = accessor(js, bin_, attrs["NORMAL"])
                t = idx.reshape(-1, 3)
                fn = np.cross(pos[t[:, 1]] - pos[t[:, 0]], pos[t[:, 2]] - pos[t[:, 0]])
                fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
                dots = np.abs(np.einsum("ij,ij->i", np.repeat(fn, 3, axis=0), nrm[t.ravel()]))
                p["NORMAL"] = {"unit_length_mean": round(float(np.linalg.norm(nrm, axis=1).mean()), 4),
                               "mean_abs_dot_with_face_normal": round(float(dots.mean()), 3),
                               "custom_normals_bent": bool(dots.mean() < 0.85)}
            out["primitives"].append(p)
    pos = np.concatenate(all_pos)
    out["triangles"] = tris_total
    out["bounds_min_xyz_gltf"] = [round(float(v), 3) for v in pos.min(0)]
    out["bounds_max_xyz_gltf"] = [round(float(v), 3) for v in pos.max(0)]
    out["height_m"] = round(float(pos[:, 1].max()), 3)
    near = pos[np.abs(pos[:, 1]) < 0.15]
    out["ground_contact_centre_xz"] = [round(float(v), 3) for v in near[:, [0, 2]].mean(0)] if len(near) else None
    (lo, hi), lod1_max = BUDGET[kind]
    fol = [p for p in out["primitives"] if (p["material"] or "").endswith("_foliage")]
    bark = [p for p in out["primitives"] if (p["material"] or "").endswith("_bark")]
    mats = {m["name"]: m for m in out["materials"]}
    ok = {
        "budget": (lo <= tris_total <= hi) if lod == 0 else tris_total <= lod1_max,
        "materials_named": all(m["name"].endswith(("_bark", "_foliage")) for m in out["materials"])
        and len(out["materials"]) == (1 if kind == "bush" else 2),
        "foliage_mask_0p45_double_sided": all(mats[p["material"]]["alphaMode"] == "MASK"
                                              and abs((mats[p["material"]]["alphaCutoff"] or 0) - 0.45) < 1e-6
                                              and mats[p["material"]]["doubleSided"] for p in fol),
        "bark_opaque": all(mats[p["material"]]["alphaMode"] == "OPAQUE" for p in bark),
        "color0_vec3_everywhere": all(p.get("COLOR_0", {}).get("type") == "VEC3" for p in out["primitives"]),
        "foliage_color0_0p55_to_1": all(0.54 <= p["COLOR_0"]["lum_min"] <= 0.72 and p["COLOR_0"]["lum_max"] >= 0.95
                                        for p in fol if "COLOR_0" in p),
        "bark_color0_min_ge_0p55": all(p["COLOR_0"]["lum_min"] >= 0.549 for p in bark if "COLOR_0" in p),
        "texcoord1_everywhere": all("TEXCOORD_1" in p["attributes"] for p in out["primitives"]),
        "wind_rises_with_height": all((p["TEXCOORD_1"]["corr_sway_vs_height"] or 0) > 0.5 for p in out["primitives"]
                                      if "TEXCOORD_1" in p),
        "trunk_base_rigid": all((p["TEXCOORD_1"]["x_sway_max_below_1m"] or 0) <= 0.02 for p in bark
                                if "TEXCOORD_1" in p),
        "foliage_custom_normals": all(p.get("NORMAL", {}).get("custom_normals_bent") for p in fol),
        "pivot_at_ground": abs(out["bounds_min_xyz_gltf"][1]) < 0.45 and all(
            (n["translation"] is None or max(abs(v) for v in n["translation"]) < 1e-4) for n in out["nodes"]),
        "no_meshopt_or_draco": not any(e in ("KHR_meshopt_compression", "EXT_meshopt_compression",
                                             "KHR_draco_mesh_compression") for e in out["extensionsUsed"]),
        "images_resolve": all(i["storage"] != "external" or i["exists"] for i in out["images"]),
    }
    out["checks"] = ok
    out["all_ok"] = all(ok.values())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--species", required=True, help="comma list of species:kind")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = {"label": "GLB READ-BACK (system Python parser, independent of Blender)", "files": {}}
    for item in a.species.split(","):
        sp, kind = item.split(":")
        for lod in (0, 1):
            p = os.path.join(a.dir, f"{sp}_lod{lod}.glb")
            res["files"][f"{sp}_lod{lod}"] = check(p, kind, lod)
    res["all_ok"] = all(v["all_ok"] for v in res["files"].values())
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    for k, v in res["files"].items():
        bad = [c for c, ok in v["checks"].items() if not ok]
        print(f"{k:28s} tris {v['triangles']:5d} h {v['height_m']:6.2f} bytes {v['bytes']:8d} "
              f"{'OK' if v['all_ok'] else 'FAIL ' + ','.join(bad)}")


if __name__ == "__main__":
    main()
