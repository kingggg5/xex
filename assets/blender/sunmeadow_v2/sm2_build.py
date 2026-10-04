"""Pure-Python build of the Sunmeadow v2 blockout model: items, colliders, meshes, instances.json, colliders.json.

Run standalone (system Python) to validate without Blender:
  python assets/blender/sunmeadow_v2/sm2_build.py --out assets/models/sunmeadow-v2/blockout
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sm2_geom as G  # noqa: E402
from sm2_colliders import build_colliders  # noqa: E402
from sm2_items import build_annotations, build_context, build_items_meshes  # noqa: E402
from sm2_meshes import BUDGET_LAYERS, SceneAcc, build_decals, build_ground, build_paths, build_water  # noqa: E402
from sm2_relief import build_bluff, build_bridge, build_cliffs, build_hills, build_south_wall  # noqa: E402
from sm2_scatter import build_items  # noqa: E402
from sm2_site import ROOT, Site  # noqa: E402

TRI_BUDGET = 120000
DRAW_BUDGET = 40


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instance_record(it):
    d = {'id': it.id, 'category': it.category, 'species': it.species, 'position_xz': [G.r6(it.x), G.r6(it.z)],
         'base_y': G.r6(it.base_y), 'yaw': G.r6(it.yaw % math.tau), 'scale': 1.0, 'height_m': G.r6(it.height),
         'cell': it.cell, 'zone': it.zone, 'source': it.source}
    if it.category == 'tree':
        d['trunk_radius_1m'] = G.r6(it.radius)
        d['canopy_radius_m'] = G.r6(it.canopy_r)
    elif it.radius:
        d['footprint_radius_m'] = G.r6(it.radius)
    if it.collider and not it.params.get('collider_pruned'):
        d['collider_id'] = f'col_{it.id}'
    for k, v in it.params.items():
        if k in ('seed',):
            continue
        d.setdefault('params', {})[k] = v if not isinstance(v, float) else round(v, 4)
    return d


def build_all(log=print):
    t0 = time.time()
    timings = {}
    site = Site()
    items, rules, groups = build_items(site)
    timings['placement_s'] = round(time.time() - t0, 2)
    t1 = time.time()
    cols, n_water = build_colliders(site, items, prune=True)
    timings['colliders_s'] = round(time.time() - t1, 2)
    t2 = time.time()
    S = SceneAcc()
    build_ground(site, S)
    build_decals(site, S)
    build_paths(site, S)
    build_water(site, S)
    build_bluff(site, S)
    build_cliffs(site, S)
    build_hills(site, S)
    build_south_wall(site, S)
    build_bridge(site, S)
    build_items_meshes(items, S)
    build_context(site, S)
    build_annotations(site, S)
    timings['meshes_s'] = round(time.time() - t2, 2)
    cells = sorted({c for (c, l, m) in S.acc if c != 'none'})
    per_cell = {}
    for c in cells:
        keys = [k for k in S.acc if k[0] == c]
        struct = sum(S.acc[k].triangles for k in keys if k[1] in BUDGET_LAYERS)
        veg = sum(S.acc[k].triangles for k in keys if k[1] == 'veg')
        mats_struct = {k[2] for k in keys if k[1] in BUDGET_LAYERS}
        mats_veg = {k[2] for k in keys if k[1] == 'veg'}
        per_cell[c] = {'triangles_lod0_excl_vegetation': struct, 'vegetation_proxy_triangles': veg,
                       'draw_calls_structure': len(mats_struct), 'draw_calls_vegetation': len(mats_veg),
                       'budget_triangles': TRI_BUDGET, 'within_budget': struct <= TRI_BUDGET,
                       'by_layer': {l: sum(S.acc[k].triangles for k in keys if k[1] == l)
                                    for l in sorted({k[1] for k in keys})}}
    log(f'BUILD placement={timings["placement_s"]}s colliders={timings["colliders_s"]}s meshes={timings["meshes_s"]}s '
        f'items={len(items)} colliders={len(cols.items)} pruned={len(cols.pruned)} water_bands={n_water}')
    return {'site': site, 'items': items, 'rules': rules, 'groups': groups, 'cols': cols, 'scene': S,
            'per_cell': per_cell, 'timings': timings}


def write_jsons(res, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    site, items, cols = res['site'], res['items'], res['cols']
    meta = {'layout': {'path': site.layout_path.relative_to(ROOT).as_posix(), 'sha256': sha(site.layout_path)},
            'compact': {'path': site.compact_path.relative_to(ROOT).as_posix(), 'sha256': sha(site.compact_path)},
            'monsters': {'path': 'planning/levels/sunmeadow-v2-monsters.json', 'sha256': site.monsters_sha},
            'axes': 'Babylon XZ (+x east, +z north, +y up). Blender build uses x=-bx, y=-bz, z=by.',
            'yaw': 'radians, atan2(dx, dz): 0 faces +Z, pi/2 faces +X; normalised to [0, 2pi)'}
    inst = {'schema': 'xexoria.sunmeadow-v2.blockout-instances/1', 'status': 'BLOCKOUT proxies (replace with final art)',
            **meta, 'count': len(items),
            'counts_by_category': {c: sum(1 for it in items if it.category == c) for c in sorted({it.category for it in items})},
            'instances': [instance_record(it) for it in items]}
    (out / 'instances.json').write_text(json.dumps(inst, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    for c in cols.items:
        c.pop('trapezoid', None)
    col = {'schema': 'xexoria.sunmeadow-v2.blockout-colliders/1', **meta,
           'shapes': {'box': 'center [x,y,z], size [sx,sy,sz], yaw; size[0] along local X=(cos a,-sin a), size[2] along local Z=(sin a,cos a)',
                      'capsule': 'vertical; center [x,y,z], radius, size [2r,h,2r]'},
           'polygon_xz': 'exact convex footprint (CCW) for boxes and water bands; circumscribed 12-gon for capsules; maps to grounded_city BlockerInput',
           'player': {'radius_m': 0.35, 'height_m': 1.8},
           'count': len(cols.items), 'server_static_collider_limit': 512,
           'counts_by_category': {c: sum(1 for d in cols.items if d['category'] == c) for c in sorted({d['category'] for d in cols.items})},
           'pruned_unreachable': cols.pruned,
           'colliders': cols.items,
           'existing_preserved': cols.existing}
    (out / 'colliders.json').write_text(json.dumps(col, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return out / 'instances.json', out / 'colliders.json'


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='assets/models/sunmeadow-v2/blockout')
    a = ap.parse_args()
    res = build_all()
    out = Path(a.out)
    out = out if out.is_absolute() else ROOT / out
    paths = write_jsons(res, out)
    for c, d in res['per_cell'].items():
        print(c, json.dumps({k: v for k, v in d.items() if k != 'by_layer'}), d['by_layer'])
    for n in res['site'].notes:
        print('NOTE', n)
    print('wrote', *paths)
