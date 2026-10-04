"""Stage 3 (Blender): export every asset of a kit through assets/blender/tools/export_helper.py.

  blender -b --factory-startup --python-exit-code 1 --python np_stage_export.py -- --kit rocks [--atlas a,b]

For each atlas .blend in the cache: one shared material per atlas (painted albedo sRGB, normal OpenGL, ORM),
then per asset: <id>_lod0/1/2.glb (profile per kit, budget class per asset), <id>_collider.glb (no material),
<id>_shadow.glb where the recipe asks for one. Images go to the shared helper texture folder
(assets/models/sunmeadow-props/source/textures, SHA-256 names). Writes <cache>/<kit>/export.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import np_lib as L  # noqa: E402

SRC = L.OUT_MODELS / "source"
TEX = SRC / "textures"
LOD_CLASS = {"prop": ("prop", "prop_lod1", "prop_lod1"), "building_module": ("building_module",) * 3,
             "bush_lod0": ("bush_lod0", "bush_lod1", "bush_lod1")}


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--atlas", default="")
    ap.add_argument("--only", default="")
    return ap.parse_args(L.args_after_dashdash())


def main():
    args = parse()
    kdir = L.CACHE / args.kit
    kj = json.loads((kdir / "kit.json").read_text(encoding="utf-8"))
    want = set(filter(None, args.atlas.split(",")))
    only = set(filter(None, args.only.split(",")))
    SRC.mkdir(parents=True, exist_ok=True)
    exp_path = kdir / "export.json"
    exp = json.loads(exp_path.read_text(encoding="utf-8")) if exp_path.exists() else {"kit": args.kit, "assets": {}}
    t_all = time.time()
    for atlas_id, at in kj["atlases"].items():
        if want and atlas_id not in want:
            continue
        bpy.ops.wm.open_mainfile(filepath=str(kdir / f"{atlas_id}.blend"))
        tex = kdir / "tex"
        alb, nrm, orm = (tex / f"{atlas_id}_{k}.png" for k in ("albedo", "normal", "orm"))
        mat_spec = at.get("material", {})
        mat = L.pbr_material(f"{atlas_id}_mat", alb, nrm, orm, alpha_clip=mat_spec.get("alpha_clip"),
                             vertex_color=mat_spec.get("vertex_color"),
                             double_sided=bool(mat_spec.get("double_sided", False)))
        profile = at.get("profile", "prop")
        for aid in at["members"]:
            if only and aid not in only:
                continue
            a = kj["assets"][aid]
            objs = {k: bpy.data.objects[n] for k, n in a["objects"].items()}
            classes = LOD_CLASS.get(a["budget_class"], (a["budget_class"],) * 3)
            rec = {"files": {}, "receipts": {}, "status": {}, "triangles": {}}
            inputs = [str(alb), str(nrm), str(orm)]
            for li, key in enumerate(("lod0", "lod1", "lod2")):
                ob = objs[key]
                ob.data.materials.clear()
                ob.data.materials.append(mat)
                path = SRC / f"{aid}_{key}.glb"
                r = L.export_lod(ob, path, profile=profile, budget_class=classes[li], texture_dir=TEX,
                                 asset_id=f"{aid}_{key}", inputs=inputs,
                                 double_sided=[mat.name] if mat_spec.get("double_sided") else (),
                                 vertex_color="MATERIAL" if mat_spec.get("vertex_color") else "NONE",
                                 notes=f"recipe {a['recipe']} seed {a['seed']}; atlas {atlas_id}")
                rec["files"][key] = path.name
                rec["receipts"][key] = path.with_suffix(".receipt.json").name
                rec["status"][key] = r.get("status")
                rec["triangles"][key] = L.tri_count(ob)
            for key in ("collider", "shadow"):
                if key not in objs:
                    continue
                ob = objs[key]
                ob.data.materials.clear()
                path = SRC / f"{aid}_{key}.glb"
                r = L.export_lod(ob, path, profile="prop", budget_class="prop", texture_dir=TEX,
                                 asset_id=f"{aid}_{key}", materials="NONE", vertex_color="NONE",
                                 notes=f"{key} proxy; recipe {a['recipe']} seed {a['seed']}")
                rec["files"][key] = path.name
                rec["receipts"][key] = path.with_suffix(".receipt.json").name
                rec["status"][key] = r.get("status")
                rec["triangles"][key] = L.tri_count(ob)
            rec["footprint_xz"] = L.footprint_xz(objs["collider"])
            rec["atlas"] = atlas_id
            rec["profile"] = profile
            rec["classes"] = classes
            exp["assets"][aid] = rec
            L.log(f"export {aid}: {rec['status']} tris {rec['triangles']}")
        L.write_json(exp_path, exp)
    L.log(f"STAGE EXPORT OK {time.time() - t_all:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
