"""Readback check of every decoded runtime model's full world transform."""
from pathlib import Path
import json
import sys
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import np_lib as L
from np_stone_build import EVID,CACHE,OUT
from np_stone_specs import assets

rows=[]
for spec in assets():
    aid=spec["id"];source=json.loads((EVID/"receipts"/f"{aid}.json").read_text(encoding="utf8"))
    expected=source["mesh"]["lod0"]
    L.reset();path=CACHE/"decoded-review"/f"{aid}_lod0.review.glb"
    bpy.ops.import_scene.gltf(filepath=str(path));bpy.context.view_layer.update()
    points=[]
    for ob in bpy.data.objects:
        if ob.type=="MESH":
            matrix=np.asarray(ob.matrix_world)
            points.append(L.verts(ob.data)@matrix[:3,:3].T+matrix[:3,3])
    p=np.concatenate(points);mn,mx=p.min(0),p.max(0)
    dev=max(float(np.abs(mn-expected["bounds_min"]).max()),float(np.abs(mx-expected["bounds_max"]).max()))
    tol=max(.0015,float(np.ptp(p,axis=0).max())/4096)
    rows.append({"id":aid,"pass":dev<=tol,"max_deviation_m":dev,"tolerance_m":tol,
                 "source_bounds_min":expected["bounds_min"],"source_bounds_max":expected["bounds_max"],
                 "decoded_bounds_min":mn.tolist(),"decoded_bounds_max":mx.tolist(),
                 "runtime_sha256":L.sha256_file(OUT/"runtime"/f"{aid}_lod0.glb"),
                 "decoded_sha256":L.sha256_file(path)})
L.write_json(EVID/"runtime-world-bounds.json",{"pass":all(r["pass"] for r in rows),"assets":rows,
                                           "note":"Full imported matrix_world, including meshopt quantization-node offsets, compared with source Blender bounds"})
if not all(r["pass"] for r in rows):raise ValueError([r for r in rows if not r["pass"]])
L.log(f"STONE RUNTIME BOUNDS PASS {len(rows)} assets; max {max(r['max_deviation_m'] for r in rows):.6f}m")
