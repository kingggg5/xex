"""Map dressing audit for a city master: duplicates, empty filler, landmark sight lines,
route obstructions. Read-only (never saves the loaded .blend).

  blender -b --factory-startup --disable-autoexec <file.blend> --python-exit-code 1 \
    --python assets/blender/city_r5/audit_map_r6.py -- --out <audit.json> [--layout <layout.json>]

Coordinates in the report are RUNTIME (x, y, z) = (Blender x, Blender z, 176 + Blender y).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def rt(v):
    return [round(float(v[0]), 2), round(float(v[2]), 2), round(176.0 + float(v[1]), 2)]


def mesh_world(o):
    me = o.data
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    m = np.array(o.matrix_world)
    return co @ m[:3, :3].T + m[:3, 3]


def descendants(o):
    out, st = [], [o]
    while st:
        x = st.pop()
        out.append(x)
        st.extend(x.children)
    return out


def module_signature(root):
    """Hash of the kit's local geometry (vertex counts + materials per part name stem)."""
    h = hashlib.sha256()
    rows = []
    for d in descendants(root):
        if d.type != 'MESH':
            continue
        stem = re.sub(r'\.\d{3}$', '', d.name).replace(root.name.replace('kit_', ''), '<id>')
        rows.append((stem, len(d.data.vertices), len(d.data.polygons)))
    for r in sorted(rows):
        h.update(repr(r).encode())
    return h.hexdigest()[:16], len(rows)


def roof_material(root):
    for d in descendants(root):
        if d.type == 'MESH' and d.data.materials and d.data.materials[0].name.startswith('roof_') and ' roof' in d.name:
            return d.data.materials[0].name
    for d in descendants(root):
        if d.type == 'MESH' and d.data.materials and d.data.materials[0].name.startswith('roof_'):
            return d.data.materials[0].name
    return None


def scene_bvh(filter_fn):
    verts, polys, owner = [], [], []
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or not filter_fn(o):
            continue
        w = mesh_world(o)
        base = len(verts)
        verts.extend(map(tuple, w))
        for p in o.data.polygons:
            polys.append(tuple(base + i for i in p.vertices))
            owner.append(o.name)
    return BVHTree.FromPolygons(verts, polys), owner


SKIP = re.compile(r'^(fx_|emit_|light_|presentation |review |witness )')


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--layout', default=str(ROOT / 'assets/blender/city_r5/layout.json'))
    a = ap.parse_args(argv)
    layout = json.loads(Path(a.layout).read_text(encoding='utf-8'))
    report = {'schema': 'xexoria.city-map-audit/1', 'file': bpy.data.filepath, 'units': 'metres, runtime coordinates'}

    # ---------------- houses and modules ---------------------------------
    roots = [o for o in bpy.context.scene.objects if o.type == 'EMPTY' and o.parent is None and o.name.startswith('kit_')]
    houses = []
    for r in roots:
        sig, parts = module_signature(r)
        tris = sum(sum(len(p.vertices) - 2 for p in d.data.polygons) for d in descendants(r) if d.type == 'MESH')
        yaw = math.degrees(r.matrix_world.to_euler().z) % 360
        # runtime facing: the kit front is local -Y; world front direction = R * (0,-1)
        fx, fy = math.sin(math.radians(yaw)), -math.cos(math.radians(yaw))
        heading = math.degrees(math.atan2(fx, fy)) % 360  # runtime atan2(dx, dz), 0 = +Z
        houses.append({'root': r.name, 'signature': sig, 'parts': parts, 'triangles': tris, 'at': rt(r.matrix_world.translation),
                       'front_heading_deg': round(heading, 1), 'roof': roof_material(r)})
    sig_count = Counter(h['signature'] for h in houses)
    for h in houses:
        h['copies_of_module'] = sig_count[h['signature']]
    dup = [h for h in houses if h['copies_of_module'] > 1]
    same_variant = Counter((h['signature'], h['roof']) for h in dup)
    near_pairs = []
    for i, h in enumerate(dup):
        for g in dup[i + 1:]:
            if h['signature'] != g['signature']:
                continue
            d = math.hypot(h['at'][0] - g['at'][0], h['at'][2] - g['at'][2])
            if d <= 40:
                near_pairs.append({'a': h['root'], 'b': g['root'], 'distance_m': round(d, 1), 'same_roof': h['roof'] == g['roof'],
                                   'heading_delta_deg': round(abs((h['front_heading_deg'] - g['front_heading_deg'] + 180) % 360 - 180), 1)})
    report['houses'] = {'kits': houses, 'module_copies': {k: v for k, v in sig_count.items() if v > 1},
                        'same_module_and_roof': {f'{k[0]}/{k[1]}': v for k, v in same_variant.items()},
                        'same_module_pairs_within_40m': sorted(near_pairs, key=lambda r: r['distance_m']),
                        'duplicated_module_triangles': sum(h['triangles'] for h in dup)}

    # ---------------- repeated prop families --------------------------------
    fam = Counter()
    fam_tris = Counter()
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or SKIP.search(o.name):
            continue
        stem = re.sub(r'\.\d{3}$', '', o.name)
        stem = re.sub(r'^(nw|west|east)_residential_rows_\d|^se_cottages_\d', '<house>', stem)
        stem = re.sub(r'\d+', '#', stem)
        fam[stem] += 1
        fam_tris[stem] += sum(len(p.vertices) - 2 for p in o.data.polygons)
    report['repeated_families'] = [{'family': k, 'count': v, 'triangles': fam_tris[k]} for k, v in fam.most_common(60)]

    # ---------------- occupancy grid: empty filler --------------------------
    tree, owner = scene_bvh(lambda o: not SKIP.search(o.name) and 'cliff underside' not in o.name and 'stalactite' not in o.name)
    isl = layout['island']
    step = 4.0
    xs = np.arange(isl['x_min'] + 2, isl['x_max'] - 1, step)
    ys = np.arange(isl['y_min'] + 2, isl['y_max'] - 1, step)
    grid = {}
    props = []  # dressing / structure hits
    for x in xs:
        for y in ys:
            hit = tree.ray_cast(Vector((float(x), float(y), 200.0)), Vector((0, 0, -1)), 400.0)
            if hit[0] is None:
                continue
            n = owner[hit[2]]
            if n == 'terrain / grass ground' or n.startswith('terrain / castle terrace / top') or n.startswith('terrain / wizard terrace / top') or n == 'terrain / cliff grass lip':
                kind = 'grass'
            elif n.startswith(('terrain / plaza', 'terrain / avenue', 'terrain / path', 'terrain / canal promenade', 'traversal / ', 'castle terrace paving', 'castle grand stair', 'bridge dressed')):
                kind = 'paved'
            elif n.startswith(('terrain / canal', 'terrain / channel', 'terrain / pool', 'fountain blue water', 'fx_water')):
                kind = 'water'
            elif n.startswith('terrain / '):
                kind = 'terrain_structure'
            else:
                kind = 'object'
                props.append((float(x), float(y)))
            grid[(round(float(x), 1), round(float(y), 1))] = (kind, n)
    kinds = Counter(k for k, _ in grid.values())
    # small dressing (benches, planters, drifts, lamps, crates) is easily missed by a 4 m ray grid:
    # add the XY centroid of every non-terrain mesh whose footprint is under 8 m
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or SKIP.search(o.name) or o.name.startswith(('terrain / ', 'traversal / ')) or not len(o.data.vertices):
            continue
        w = mesh_world(o)
        lo, hi = w.min(axis=0), w.max(axis=0)
        if max(hi[0] - lo[0], hi[1] - lo[1]) < 8.0 and lo[2] > -5:
            props.append((float((lo[0] + hi[0]) * 0.5), float((lo[1] + hi[1]) * 0.5)))
    obj_pts = np.array(props) if props else np.zeros((0, 2))
    empty = []
    for (x, y), (k, _n) in grid.items():
        if k != 'grass':
            continue
        if len(obj_pts):
            d = np.min(np.hypot(obj_pts[:, 0] - x, obj_pts[:, 1] - y))
        else:
            d = 1e9
        if d >= 10.0:
            empty.append((x, y))
    # connected patches of empty grass
    es = set(empty)
    seen = set()
    patches = []
    for c in empty:
        if c in seen:
            continue
        stack, cells = [c], []
        seen.add(c)
        while stack:
            p = stack.pop()
            cells.append(p)
            for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step)):
                q = (round(p[0] + dx, 1), round(p[1] + dy, 1))
                if q in es and q not in seen:
                    seen.add(q)
                    stack.append(q)
        cx = sum(p[0] for p in cells) / len(cells)
        cy = sum(p[1] for p in cells) / len(cells)
        patches.append({'cells': len(cells), 'area_m2': len(cells) * step * step, 'centre_runtime': [round(cx, 1), 0, round(176 + cy, 1)],
                        'bbox_runtime': [round(min(p[0] for p in cells), 1), round(176 + min(p[1] for p in cells), 1),
                                         round(max(p[0] for p in cells), 1), round(176 + max(p[1] for p in cells), 1)]})
    patches.sort(key=lambda r: -r['area_m2'])
    report['occupancy'] = {'cell_m': step, 'cells': len(grid), 'by_kind_m2': {k: v * step * step for k, v in kinds.items()},
                           'empty_grass_rule': 'grass cell whose centre is >= 10 m from any dressing/building ray hit or small-object centroid',
                           'empty_grass_m2': len(empty) * step * step, 'empty_patches': patches[:20]}

    # ---------------- landmark sight lines ------------------------------------
    # Each landmark is its kit; the target is a point 1 m under the kit's highest
    # vertex. A ray counts as visible when its first hit belongs to that kit.
    kit_of = {}
    for r in roots:
        for d in descendants(r):
            kit_of[d.name] = r.name
    lm_kits = {'castle_main_spire': 'kit_magic_castle', 'wizard_spire': 'kit_wizard_tower', 'windmill_cap': 'kit_windmill',
               'fountain_statue': 'kit_plaza_fountain', 'portal': 'kit_arcane_portal', 'gate_towers': 'kit_town_gate',
               'market': 'kit_market_square'}
    landmarks = {}
    for lm, kit in lm_kits.items():
        r = bpy.data.objects.get(kit)
        if r is None:
            continue
        best = None
        for d in descendants(r):
            if d.type != 'MESH' or not len(d.data.vertices) or SKIP.search(d.name):
                continue
            w = mesh_world(d)
            i = int(np.argmax(w[:, 2]))
            if best is None or w[i, 2] > best[2]:
                best = w[i]
        if best is not None:
            landmarks[lm] = (float(best[0]), float(best[1]), float(best[2]) - 1.0)
    viewpoints = {
        'gate_arrival': (10.1, -160.0), 'canal_bridge': (0.0, -74.0), 'south_plaza': (0.0, -30.0),
        'east_avenue_end': (48.0, -18.0), 'west_avenue_end': (-58.0, -8.0), 'east_loop_mid': (75.0, -25.0),
        'castle_stairs_foot': (0.0, 40.0), 'nw_avenue_end': (-48.0, 58.0), 'ne_avenue_end': (44.0, 50.0),
        'sw_avenue_end': (-62.0, -52.0), 'se_avenue_end': (70.0, -54.0), 'ring_road_sw': (-60.0, -104.0),
        'ring_road_se': (60.0, -104.0),
    }
    gtree, gowner = scene_bvh(lambda o: o.name.startswith(('terrain / ', 'traversal / ', 'castle terrace paving', 'bridge dressed')) and ' curb' not in o.name)
    sight = []
    for vp, (vx, vy) in viewpoints.items():
        g = gtree.ray_cast(Vector((vx, vy, 200.0)), Vector((0, 0, -1)), 400.0)
        gz = g[0].z if g[0] is not None else 0.0
        eye = Vector((vx, vy, gz + 1.65))
        row = {'viewpoint': vp, 'at': rt((vx, vy, gz)), 'targets': {}}
        for lm, (lx, ly, lz) in landmarks.items():
            tgt = Vector((lx, ly, lz))
            d = (tgt - eye)
            flat = Vector((d.x, d.y, 0.0))
            if flat.length < 1e-3:
                continue
            flat.normalize()
            cam = eye - flat * (13 * math.cos(math.radians(22.4))) + Vector((0, 0, 13 * math.sin(math.radians(22.4))))
            res = {}
            for label, origin in (('eye', eye), ('camera', cam)):
                ray = tgt - origin
                hit = tree.ray_cast(origin, ray.normalized(), ray.length + 0.5)
                if hit[0] is None or kit_of.get(owner[hit[2]]) == lm_kits[lm]:
                    res[label] = 'visible'
                else:
                    res[label] = f'blocked by {owner[hit[2]]} at {round((hit[0] - origin).length, 1)} m'
            res['distance_m'] = round((tgt - eye).length, 1)
            row['targets'][lm] = res
        sight.append(row)
    report['sight_lines'] = sight
    report['sight_summary'] = {lm: sum(1 for r in sight if lm in r['targets'] and r['targets'][lm]['camera'] == 'visible')
                               for lm in landmarks}
    report['viewpoint_count'] = len(viewpoints)

    # ---------------- ring props against avenue axes ----------------------------
    av = layout['plaza']['avenues']
    rows = []
    stems = ('garden stone planter', 'city lamp stone foot', 'plaza bench stone leg')
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or not o.name.startswith(stems):
            continue
        w = mesh_world(o)
        c = w.mean(axis=0)
        r = math.hypot(c[0], c[1])
        if r > 45:
            continue
        best = None
        for a_ in av:
            tx, ty = a_['to']
            L = math.hypot(tx, ty)
            ux, uy = tx / L, ty / L
            along = c[0] * ux + c[1] * uy
            if along < 0:
                continue
            lateral = abs(-c[0] * uy + c[1] * ux)
            clearance = lateral - a_['width'] * 0.5
            if best is None or clearance < best[1]:
                best = (a_['id'], clearance, lateral)
        rows.append({'object': o.name, 'at': rt(c), 'radius_m': round(r, 2), 'nearest_avenue': best[0],
                     'lateral_from_axis_m': round(best[2], 2), 'inside_avenue_band': bool(best[1] < 0)})
    report['ring_props_vs_avenues'] = rows
    report['ring_props_inside_avenue_bands'] = sum(1 for r in rows if r['inside_avenue_band'])
    # ---------------- authored paths running into buildings --------------------
    solid = re.compile(r' (foundation plinth|masonry body)$|^(castle nave stone body|castle side wing body|observatory tapered tower|windmill plaster tower)')
    btree, bowner = scene_bvh(lambda o: bool(solid.search(re.sub(r'\.\d{3}$', '', o.name))))
    hits = []
    lines = [(p_['id'], p_['points'], p_['width']) for p_ in layout.get('paths', [])]
    lines += [(f"avenue {a_['id']}", [[0, 0], a_['to']], a_['width']) for a_ in layout['plaza']['avenues']]
    for pid, pts, width in lines:
        blocked = defaultdict(int)
        where = {}
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(L / 1.0))
            for k in range(n + 1):
                t = k / n
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                if math.hypot(x, y) < 44 and pid.startswith('avenue'):
                    continue  # the plaza disc itself
                hit = btree.ray_cast(Vector((x, y, 60.0)), Vector((0, 0, -1)), 80.0)
                if hit[0] is not None:
                    name = bowner[hit[2]]
                    blocked[name] += 1
                    where.setdefault(name, rt((x, y, hit[0].z)))
        for name, count in blocked.items():
            hits.append({'path': pid, 'width_m': width, 'building_part': name, 'centreline_metres_inside': count, 'first_at': where[name]})
    report['paths_into_buildings'] = hits

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'houses': len(houses), 'dup_modules': report['houses']['module_copies'], 'empty_grass_m2': report['occupancy']['empty_grass_m2'],
                      'sight_summary': report['sight_summary'], 'ring_inside': report['ring_props_inside_avenue_bands'], 'paths_into_buildings': len(report['paths_into_buildings'])}))


if __name__ == '__main__':
    main()
