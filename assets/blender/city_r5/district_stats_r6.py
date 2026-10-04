"""Triangles per district for a city master (source, and runtime estimate after the R5 decimation profile).

  blender -b --factory-startup --disable-autoexec <file.blend> --python assets/blender/city_r5/district_stats_r6.py -- --out <json>
Districts are classified by mesh centroid (layout/Blender XY). Runtime estimate applies the
export_runtime_r5 DEFAULT_RATIOS (0.8 on stone_trim_carved, timber_dark, metal_iron, metal_gold,
wood_planks_light); the exported GLB total is the authoritative number.
"""
import argparse
import json
import math
import sys
from collections import defaultdict

import bpy
import numpy as np

RATIOS = {'stone_trim_carved': 0.8, 'timber_dark': 0.8, 'metal_iron': 0.8, 'metal_gold': 0.8, 'wood_planks_light': 0.8}


def district(x, y, z):
    if z < -3:
        return 'island underside and cliffs'
    if y >= 40 and abs(x) <= 82:
        return 'castle approach and terrace'
    if math.hypot(x, y) <= 43.5:
        return 'fountain plaza'
    if abs(x) <= 26 and y <= -40:
        return 'gate and canal'
    if x >= 42 and -48 <= y <= 4:
        return 'market'
    if x <= -40 and -100 <= y <= 6:
        return 'craftsmen west'
    return 'residential and gardens'


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    src = defaultdict(int)
    run = defaultdict(float)
    objs = defaultdict(int)
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or o.name.startswith(('presentation ', 'cam ')):
            continue
        me = o.data
        if not len(me.vertices):
            continue
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        m = np.array(o.matrix_world)
        c = (co @ m[:3, :3].T + m[:3, 3]).mean(axis=0)
        t = sum(len(p.vertices) - 2 for p in me.polygons)
        d = 'terrain (shared ground, all districts)' if o.name.startswith(('terrain / grass ground', 'terrain / cliff')) else district(*c)
        src[d] += t
        mat = me.materials[0].name if me.materials else ''
        run[d] += t * RATIOS.get(mat, 1.0)
        objs[d] += 1
    out = {'file': bpy.data.filepath, 'districts': {k: {'objects': objs[k], 'source_triangles': src[k], 'runtime_estimate': int(run[k])}
                                                   for k in sorted(src, key=lambda k: -src[k])},
           'total_source': sum(src.values()), 'total_runtime_estimate': int(sum(run.values()))}
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out))


if __name__ == '__main__':
    main()
