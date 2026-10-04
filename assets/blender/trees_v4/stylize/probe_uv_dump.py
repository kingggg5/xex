"""Dump foliage UV triangles and island facts of chosen kit models (read-only probe, Route A step 2).

Usage:
  blender -b --factory-startup --python probe_uv_dump.py -- --src <kit glTF dir> --out <json> --models Pine_2,Pine_5
"""
import argparse
import json
import sys

import bpy
import numpy as np


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", required=True)
    a, _ = ap.parse_known_args(argv)
    return a


def main():
    a = parse()
    res = {}
    for name in a.models.split(","):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=f"{a.src}/{name}.gltf")
        ob = [o for o in bpy.data.objects if o.type == "MESH"][0]
        me = ob.data
        me.calc_loop_triangles()
        uv = me.uv_layers[0].uv
        tris = []
        for lt in me.loop_triangles:
            mat = me.materials[lt.material_index].name
            if not mat.startswith(("Leaves", "Leaf", "Flowers")):
                continue
            tris.append({"m": mat, "uv": [[round(uv[l].vector[0], 4), round(uv[l].vector[1], 4)] for l in lt.loops],
                         "co": [[round(c, 4) for c in me.vertices[v].co] for v in lt.vertices],
                         "n": [round(c, 3) for c in lt.normal]})
        res[name] = tris
        print("DUMPED", name, len(tris), flush=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh)
    print("WROTE", a.out)


main()
