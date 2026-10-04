"""Boss-arena and prop-move checks for the Sunmeadow v2 blockout (pure Python + numpy, Babylon XZ).

Checks the exported blockout (instances.json, colliders.json, cell GLBs) against the layout JSON:
  1. moved props: every layout landmark noted "existing prop <id>, moved from ..." -> the instance and its collider
     sit at the landmark position_xz, and nothing of it is left at the compact v1 position (instances, colliders and
     GLB vertices of its material). With --before (a copy of the previous pass) the old pass is probed the same way;
  2. arena keep-clear (layout windstone_circle.arena_keep_clear_m): no collider within 12 m of the circle centre except
     the ring's own stones and the altar block. Two measures: the collider footprint (exact circle for capsules,
     polygon for boxes) and the collider centre (the method of tools/levels/render_layout_plan.py);
  3. ground cover inside boss_arena_radius_m: flowers only (<= 0.35 m, no glow); glowing mushrooms at r >= 11.5 m.
     Instance level and GLB vertex level (exported geometry);
  4. nothing on paths: every instance footprint vs every path edge (layout: props >= 1.0 m from path edges);
  5. moved props vs the v2 monster homes and patrols (body radius);
  6. diff against the previous pass (instances added / removed / moved).

  python assets/blender/sunmeadow_v2/arena_check.py --out planning/evidence/sunmeadow-v2-blockout/pass5/arena_check_pass5.json \
      [--before <dir with the previous pass's instances.json, colliders.json and GLBs>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sm2_geom as G  # noqa: E402
from sm2_site import ROOT, Site  # noqa: E402

FLOWER_MAX_H = 0.35
MUSHROOM_BAND = (11.5, 13.0)       # sm2_scatter.scatter_glade_edge
CANOPY_MATS = ('pine', 'pine_ancient', 'broadleaf_L', 'broadleaf_M', 'broadleaf_S', 'hero_canopy')
PROBE = {'bush': 0.35, 'trunk': 0.5}   # vertex probe radius around a prop centre, by material


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


# ----------------------------------------------------------------------------- GLB vertices
def _node_matrix(n):
    if 'matrix' in n:
        return np.array(n['matrix'], dtype=float).reshape(4, 4).T
    t = n.get('translation', [0, 0, 0])
    x, y, z, w = n.get('rotation', [0, 0, 0, 1])
    s = n.get('scale', [1, 1, 1])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.array(s)[None, :]
    m[:3, 3] = t
    return m


def glb_vertices(path: Path):
    """[(layer, material, node_name, (N,3) Babylon XYZ)] for every mesh primitive of a cell GLB.

    Blender (x, y, z) = Babylon (-x, -z, y) and the glTF exporter writes Y-up (x, z, -y), so glTF (x, y, z) = Babylon
    (-x, y, z)."""
    data = path.read_bytes()
    jlen, _ = struct.unpack_from('<II', data, 12)
    gltf = json.loads(data[20:20 + jlen].decode('utf-8'))
    off = 20 + jlen
    blen, _ = struct.unpack_from('<II', data, off)
    binc = data[off + 8:off + 8 + blen]
    mats = [m.get('name', '') for m in gltf.get('materials', [])]
    out = []

    def positions(acc_i):
        acc = gltf['accessors'][acc_i]
        bv = gltf['bufferViews'][acc['bufferView']]
        start = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
        stride = bv.get('byteStride', 12)
        n = acc['count']
        raw = np.frombuffer(binc, dtype=np.uint8, count=stride * (n - 1) + 12, offset=start)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(n, 12), strides=(stride, 1))
        return np.frombuffer(rows.tobytes(), dtype='<f4').reshape(n, 3).astype(float)

    def walk(ni, parent):
        n = gltf['nodes'][ni]
        m = parent @ _node_matrix(n)
        if 'mesh' in n:
            ex = n.get('extras', {})
            name = n.get('name', '')
            layer = ex.get('layer') or (name.split('__')[1] if name.count('__') >= 2 else '')
            for p in gltf['meshes'][n['mesh']]['primitives']:
                v = positions(p['attributes']['POSITION'])
                w = (m @ np.c_[v, np.ones(len(v))].T).T[:, :3]
                bab = np.c_[-w[:, 0], w[:, 1], w[:, 2]]
                out.append((layer, mats[p['material']] if 'material' in p else '', name, bab))
        for c in n.get('children', []):
            walk(c, m)

    for root in gltf['scenes'][gltf.get('scene', 0)]['nodes']:
        walk(root, np.eye(4))
    return out


def load_glbs(glb_dir: Path):
    prims, files = [], []
    for p in sorted(glb_dir.glob('sunmeadow_v2_c*_r*.glb')):
        prims += glb_vertices(p)
        files.append({'path': rel(p), 'sha256': sha(p)})
    return prims, files


def count_near(prims, material, xz, r):
    n = 0
    for layer, mat, name, v in prims:
        if mat != material:
            continue
        d = np.hypot(v[:, 0] - xz[0], v[:, 2] - xz[1])
        n += int((d <= r).sum())
    return n


# ----------------------------------------------------------------------------- collider geometry
def collider_centre_xz(c):
    return (c['center'][0], c['center'][2])


def collider_edge_distance(c, p):
    """Distance from point p to the collider footprint (0 when p is inside). Capsules: exact circle; boxes and
    polygons: polygon_xz."""
    if c['shape'] == 'capsule':
        return max(0.0, math.hypot(p[0] - c['center'][0], p[1] - c['center'][2]) - c['radius'])
    poly = [tuple(q) for q in c['polygon_xz']]
    return 0.0 if G.point_in_polygon(p, poly) else G.polygon_edge_distance(p, poly)


def polygon_edge_distance_any(c, p):
    poly = [tuple(q) for q in c['polygon_xz']]
    return 0.0 if G.point_in_polygon(p, poly) else G.polygon_edge_distance(p, poly)


# ----------------------------------------------------------------------------- checks
def moved_props(site, inst, cols, prims, before):
    by_id = {i['id']: i for i in inst['instances']}
    col_by_id = {c['id']: c for c in cols['colliders'] + cols.get('existing_preserved', [])}
    compact = {p['id']: p for p in site.existing_props}
    b_inst = {i['id']: i for i in before['instances']['instances']} if before else {}
    b_cols = {c['id']: c for c in before['colliders']['colliders']} if before else {}
    rows = []
    for pid, (nx, nz, lm_id) in sorted(site.prop_moves.items()):
        cp = compact.get(pid)
        ox, oz = (float(cp['after_xz'][0]), float(cp['after_xz'][1])) if cp else (None, None)
        it = by_id.get(pid)
        c = col_by_id.get(f'col_{pid}')
        species = it['species'] if it else None
        mats = ['bush'] if species and species.startswith('bush') else (['trunk'] if it and it['category'] == 'tree' else [])
        r = {'prop': pid, 'layout_landmark': lm_id, 'layout_xz': [nx, nz], 'compact_v1_xz': [ox, oz],
             'move_m': round(math.hypot(nx - ox, nz - oz), 3) if cp else None,
             'centre_distance_to_arena_m': {'old': round(math.hypot(ox - site.arena_c[0], oz - site.arena_c[1]), 2) if cp else None,
                                            'new': round(math.hypot(nx - site.arena_c[0], nz - site.arena_c[1]), 2)}}
        r['instance_xz'] = it['position_xz'] if it else None
        r['instance_at_layout_xz'] = bool(it) and math.hypot(it['position_xz'][0] - nx, it['position_xz'][1] - nz) < 1e-3
        pr = (it or {}).get('params', {})
        r['instance_records_move'] = bool(it) and pr.get('moved_by_layout_landmark') == lm_id and \
            pr.get('moved_from_xz') == [ox, oz]
        r['collider_id'] = c['id'] if c else None
        r['collider_shape'] = c['shape'] if c else None
        r['collider_radius_m'] = c.get('radius') if c else None
        r['collider_xz'] = list(collider_centre_xz(c)) if c else None
        r['collider_at_layout_xz'] = bool(c) and math.hypot(c['center'][0] - nx, c['center'][2] - nz) < 1e-3
        stale = [cc['id'] for cc in col_by_id.values() if cp and cc['id'] != (c or {}).get('id')
                 and math.hypot(cc['center'][0] - ox, cc['center'][2] - oz) < 0.05]
        r['colliders_left_at_old_xz'] = stale
        r['glb_vertices'] = {m: {'probe_r_m': PROBE[m], 'at_new': count_near(prims, m, (nx, nz), PROBE[m]),
                                 'at_old': count_near(prims, m, (ox, oz), PROBE[m])} for m in mats}
        if before:
            bi, bc = b_inst.get(pid), b_cols.get(f'col_{pid}')
            r['before'] = {'instance_xz': bi['position_xz'] if bi else None,
                           'collider_xz': list(collider_centre_xz(bc)) if bc else None,
                           'glb_vertices': {m: {'at_new': count_near(before['prims'], m, (nx, nz), PROBE[m]),
                                                'at_old': count_near(before['prims'], m, (ox, oz), PROBE[m])} for m in mats}}
            r['collider_moved_m'] = round(math.dist(r['before']['collider_xz'], r['collider_xz']), 3) \
                if r['collider_xz'] and r['before']['collider_xz'] else None
        glb_ok = all(v['at_new'] > 0 and v['at_old'] == 0 for v in r['glb_vertices'].values())
        r['pass'] = bool(r['instance_at_layout_xz'] and r['instance_records_move'] and r['collider_at_layout_xz']
                         and not stale and glb_ok)
        rows.append(r)
    return {'props': rows, 'count': len(rows), 'pass': all(x['pass'] for x in rows)}


def arena_keep_clear(site, inst, cols):
    cx, cz = site.arena_c
    keep, arena = site.keep_r, site.arena_r
    exempt_items = {i['id'] for i in inst['instances']
                    if (i['zone'] == 'windstone_circle' and i['category'] == 'stone') or i['species'] == 'altar'}
    exempt = {f'col_{i}' for i in exempt_items}
    rows = []
    for c in cols['colliders'] + cols.get('existing_preserved', []):
        dc = math.hypot(c['center'][0] - cx, c['center'][2] - cz)
        de = collider_edge_distance(c, (cx, cz))
        if de > keep + 4.0:
            continue
        rows.append({'collider': c['id'], 'category': c['category'], 'shape': c['shape'], 'visual': c.get('visual'),
                     'radius_m': c.get('radius'), 'centre_m': round(dc, 3), 'footprint_edge_m': round(de, 3),
                     'polygon_edge_m': round(polygon_edge_distance_any(c, (cx, cz)), 3),
                     'exempt': c['id'] in exempt,
                     'exempt_reason': ('ring stone' if 'stone' in c['id'] else 'altar block') if c['id'] in exempt else None})
    rows.sort(key=lambda r: r['footprint_edge_m'])
    non = [r for r in rows if not r['exempt']]
    in_keep_fp = [dict(r, intrusion_m=round(keep - r['footprint_edge_m'], 3)) for r in non if r['footprint_edge_m'] < keep]
    in_keep_c = [r for r in non if r['centre_m'] < keep]
    in_arena = [r for r in non if r['footprint_edge_m'] < arena]
    return {'centre_xz': [cx, cz], 'arena_radius_m': arena, 'keep_clear_m': keep,
            'exempt_ids': sorted(exempt), 'exempt_found': [r for r in rows if r['exempt']],
            'non_exempt_nearest': non[:8],
            'non_exempt_within_keep_clear_by_footprint': in_keep_fp,
            'non_exempt_within_keep_clear_by_centre': in_keep_c,
            'non_exempt_within_arena_by_footprint': in_arena,
            'pass_centre_rule (layout checker method)': not in_keep_c,
            'pass_footprint_rule': not in_keep_fp,
            'pass_arena_radius_by_footprint': not in_arena}


def ground_cover(site, inst, prims):
    cx, cz = site.arena_c
    arena = site.arena_r
    items = []
    for i in inst['instances']:
        x, z = i['position_xz']
        r = math.hypot(x - cx, z - cz)
        foot = i.get('footprint_radius_m') or i.get('trunk_radius_1m') or 0.0
        items.append((i, r, foot))
    exempt_species = ('gate_stone', 'standing_stone', 'altar')
    inside = [(i, r, f) for i, r, f in items if r - f < arena]
    bad_inside = [{'id': i['id'], 'category': i['category'], 'species': i['species'], 'r_m': round(r, 2), 'footprint_m': f}
                  for i, r, f in inside if i['category'] != 'flower' and i['species'] not in exempt_species]
    flowers = [(i, r, f) for i, r, f in inside if i['category'] == 'flower']
    glow = [(i, r) for i, r, f in items if i['category'] == 'mushroom' and i.get('params', {}).get('glow')]
    glade_glow = [(i, r) for i, r in glow if i['zone'] == 'glade_edge']
    mush_inside = [{'id': i['id'], 'r_m': round(r, 2)} for i, r, f in items if i['category'] == 'mushroom' and r - f < arena]
    out_band = [{'id': i['id'], 'r_m': round(r, 3)} for i, r in glade_glow if not (MUSHROOM_BAND[0] - 1e-6 <= r <= MUSHROOM_BAND[1] + 1e-6)]
    glade_flowers = [(i, r) for i, r, f in items if i['zone'] == 'glade_edge' and i['category'] == 'flower']
    # GLB vertex level inside the arena disc
    by_mat = {}
    glow_min_r = None
    for layer, mat, name, v in prims:
        d = np.hypot(v[:, 0] - cx, v[:, 2] - cz)
        if mat == 'mushroom_glow' and len(d):
            m = float(d.min())
            glow_min_r = m if glow_min_r is None else min(glow_min_r, m)
        sel = d < arena
        if not sel.any():
            continue
        key = f'{layer}/{mat}'
        e = by_mat.setdefault(key, {'layer': layer, 'material': mat, 'vertices': 0, 'y_min': 1e9, 'y_max': -1e9, 'r_min': 1e9})
        e['vertices'] += int(sel.sum())
        e['y_min'] = min(e['y_min'], float(v[sel, 1].min()))
        e['y_max'] = max(e['y_max'], float(v[sel, 1].max()))
        e['r_min'] = min(e['r_min'], float(d[sel].min()))
    for e in by_mat.values():
        for k in ('y_min', 'y_max', 'r_min'):
            e[k] = round(e[k], 3)
    flower_mats = [e for e in by_mat.values() if e['material'].startswith('flower_')]
    flower_y_max = max((e['y_max'] for e in flower_mats), default=None)
    canopy = [e for e in by_mat.values() if e['material'] in CANOPY_MATS]
    # every other vegetation vertex inside the disc is ground cover (canopies are listed separately with their height)
    veg_ground = [e for e in by_mat.values() if e['layer'] == 'veg' and not e['material'].startswith('flower_')
                  and e['material'] not in CANOPY_MATS]
    glb_glow_inside = [e for e in by_mat.values() if e['material'] == 'mushroom_glow']
    return {
        'arena_radius_m': arena,
        'instances_inside_arena_by_footprint': {
            'flowers': len(flowers),
            'flower_height_m_max': max((i['height_m'] for i, r, f in flowers), default=None),
            'flower_patch_radius_m': [min((f for i, r, f in flowers), default=None), max((f for i, r, f in flowers), default=None)],
            'flower_centres_r_m': [round(min((r for i, r, f in flowers), default=0), 2), round(max((r for i, r, f in flowers), default=0), 2)],
            'exempt_structures': sorted(i['id'] for i, r, f in inside if i['species'] in exempt_species),
            'non_flower_items': bad_inside},
        'glade_edge': {'flowers': len(glade_flowers),
                       'flower_r_m': [round(min(r for i, r in glade_flowers), 3), round(max(r for i, r in glade_flowers), 3)] if glade_flowers else None,
                       'glow_mushrooms': len(glade_glow),
                       'glow_mushroom_r_m': [round(min(r for i, r in glade_glow), 3), round(max(r for i, r in glade_glow), 3)] if glade_glow else None,
                       'glow_mushroom_r_list_m': sorted(round(r, 2) for i, r in glade_glow),
                       'outside_band': out_band},
        'glow_mushrooms_total': len(glow),
        'mushrooms_inside_arena': mush_inside,
        'glb_inside_arena_by_material': sorted(by_mat.values(), key=lambda e: (e['layer'], e['material'])),
        'glb_flower_y_max_m': flower_y_max,
        'glb_mushroom_glow_min_r_m': round(glow_min_r, 3) if glow_min_r is not None else None,
        'glb_mushroom_glow_vertices_inside_arena': sum(e['vertices'] for e in glb_glow_inside),
        'glb_canopy_overhang': canopy,
        'glb_non_flower_ground_veg': veg_ground,
        'emissive_note': 'mushroom_glow is a cyan material tag in the blockout (sm2_materials.EMISSIVE has no entry); '
                         'flowers have no emission',
        'pass_flowers_only': not bad_inside and not veg_ground and not glb_glow_inside and not mush_inside,
        'pass_flower_height': flower_y_max is None or flower_y_max <= FLOWER_MAX_H,
        'pass_glow_mushrooms_r': not out_band and bool(glade_glow) and (glow_min_r or 0) > arena,
    }


def paths_clear(site, inst):
    rows, on_path, near = [], [], []
    for i in inst['instances']:
        x, z = i['position_xz']
        foot = i.get('trunk_radius_1m') if i['category'] == 'tree' else i.get('footprint_radius_m', 0.0)
        foot = foot or 0.0
        best = (1e9, None)
        for pid, pf in site.paths.items():
            g = pf.line.distance((x, z)) - pf.hw - foot
            if g < best[0]:
                best = (g, pid)
        rec = {'id': i['id'], 'category': i['category'], 'species': i['species'], 'zone': i['zone'],
               'collider': bool(i.get('collider_id')), 'gap_m': round(best[0], 3), 'path': best[1]}
        rows.append(rec)
        if best[0] < 0:
            on_path.append(rec)
        elif best[0] < 1.0 and rec['collider']:
            near.append(rec)
    by_cat = {}
    for r in rows:
        c = by_cat.setdefault(r['category'], {'n': 0, 'min_gap_m': 1e9, 'nearest': None})
        c['n'] += 1
        if r['gap_m'] < c['min_gap_m']:
            c['min_gap_m'], c['nearest'] = r['gap_m'], f"{r['id']} ({r['path']})"
    return {'method': 'footprint (trunk radius for trees, footprint_radius_m otherwise) vs every JSON path edge',
            'instances': len(rows), 'on_a_path': on_path, 'colliding_within_1m_of_a_path_edge': near,
            'min_gap_by_category': by_cat, 'pass': not on_path}


def monster_clearance(site, cols):
    col_by_id = {c['id']: c for c in cols['colliders']}
    out = []
    for pid in sorted(site.prop_moves):
        c = col_by_id.get(f'col_{pid}')
        if not c:
            continue
        p = collider_centre_xz(c)
        homes = sorted(((collider_edge_distance(c, (x, z)) - br, row, enemy, [x, z]) for (x, z, br, row, enemy) in site.monster_homes))
        pats = []
        cr = c.get('radius') or max(c['size'][0], c['size'][2]) / 2
        for (a, b, row) in site.monster_patrols:
            pats.append((G.seg_closest(p, a, b)[0] - cr, row))
        pats.sort()
        out.append({'prop': pid, 'nearest_home': {'body_clearance_m': round(homes[0][0], 2), 'row': homes[0][1],
                                                  'enemy': homes[0][2], 'home_xz': homes[0][3]} if homes else None,
                    'nearest_patrol': {'edge_to_segment_m': round(pats[0][0], 2), 'row': pats[0][1]} if pats else None})
    return {'note': 'tools/levels/check_monster_spawns.py MOVED_PROPS lists only sunmeadow_broken_cart; this re-checks the '
                    'layout prop moves against the v2 homes (body radius) and patrol segments',
            'props': out,
            'pass': all((r['nearest_home'] is None or r['nearest_home']['body_clearance_m'] >= 0.0)
                        and (r['nearest_patrol'] is None or r['nearest_patrol']['edge_to_segment_m'] >= 0.0) for r in out)}


def diff_instances(inst, before_inst):
    a = {i['id']: i for i in before_inst['instances']}
    b = {i['id']: i for i in inst['instances']}
    added, removed = sorted(set(b) - set(a)), sorted(set(a) - set(b))
    moved = []
    for k in sorted(set(a) & set(b)):
        pa, pb = a[k]['position_xz'], b[k]['position_xz']
        dd = math.dist(pa, pb)
        other = {f for f in ('species', 'height_m', 'yaw', 'zone') if a[k].get(f) != b[k].get(f)}
        if dd > 0.01 or other:
            moved.append({'id': k, 'zone': b[k]['zone'], 'from': pa, 'to': pb, 'moved_m': round(dd, 3), 'changed': sorted(other)})
    zones = {}
    for k in added + removed + [m['id'] for m in moved]:
        z = (b.get(k) or a.get(k))['zone']
        zones[z] = zones.get(z, 0) + 1
    return {'before_count': len(a), 'after_count': len(b), 'added': added, 'removed': removed,
            'changed': moved, 'changed_ids_by_zone': zones,
            'counts_by_category_before': before_inst.get('counts_by_category'),
            'counts_by_category_after': inst.get('counts_by_category')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--instances', default='assets/models/sunmeadow-v2/blockout/instances.json')
    ap.add_argument('--colliders', default='assets/models/sunmeadow-v2/blockout/colliders.json')
    ap.add_argument('--glb-dir', default='assets/models/sunmeadow-v2/blockout')
    ap.add_argument('--before', default=None, help='directory with the previous pass outputs (instances.json, colliders.json, GLBs)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    t0 = time.time()

    def P(s):
        p = Path(s)
        return p if p.is_absolute() else ROOT / p

    site = Site()
    circ = site.landmarks['windstone_circle']
    site.arena_c = tuple(float(v) for v in circ['center_xz'])
    site.arena_r = float(circ['boss_arena_radius_m'])
    site.keep_r = float(circ.get('arena_keep_clear_m', circ['boss_arena_radius_m']))
    ip, cp, gd = P(a.instances), P(a.colliders), P(a.glb_dir)
    inst = json.loads(ip.read_text(encoding='utf-8'))
    cols = json.loads(cp.read_text(encoding='utf-8'))
    prims, glbs = load_glbs(gd)
    before = None
    if a.before:
        bd = P(a.before)
        before = {'instances': json.loads((bd / 'instances.json').read_text(encoding='utf-8')),
                  'colliders': json.loads((bd / 'colliders.json').read_text(encoding='utf-8'))}
        before['prims'], before['glbs'] = load_glbs(bd)
    # GLB coordinate sanity: unique landmark materials must sit on their layout positions.
    sanity = {}
    for mat, lid in (('hero_canopy', 'old_sunmeadow_oak'), ('pine_ancient', 'ancient_pine')):
        vs = [v for layer, m, n, v in prims if m == mat]
        if vs:
            v = np.vstack(vs)
            c = (float(v[:, 0].mean()), float(v[:, 2].mean()))
            lx, lz = site.landmarks[lid]['position_xz']
            sanity[mat] = {'centroid_xz': [round(c[0], 2), round(c[1], 2)], 'layout_xz': [lx, lz],
                           'offset_m': round(math.hypot(c[0] - lx, c[1] - lz), 2)}
    res = {'schema': 'xexoria.sunmeadow-v2.arena-check/1',
           'inputs': {'layout': {'path': rel(site.layout_path), 'sha256': sha(site.layout_path)},
                      'instances': {'path': rel(ip), 'sha256': sha(ip)}, 'colliders': {'path': rel(cp), 'sha256': sha(cp)},
                      'glbs': glbs, 'before': rel(P(a.before)) if a.before else None},
           'glb_axis_sanity (glTF x,y,z = Babylon -x,y,z)': sanity,
           'arena_rule': circ.get('arena_rule')}
    res['moved_props'] = moved_props(site, inst, cols, prims, before)
    res['arena_keep_clear'] = arena_keep_clear(site, inst, cols)
    res['ground_cover'] = ground_cover(site, inst, prims)
    res['paths'] = paths_clear(site, inst)
    res['monster_clearance_of_moved_props'] = monster_clearance(site, cols)
    if before:
        res['diff_vs_before'] = diff_instances(inst, before['instances'])
    k, g = res['arena_keep_clear'], res['ground_cover']
    res['summary'] = {
        'moved_props_pass': res['moved_props']['pass'],
        'moved_props': {r['prop']: {'xz': r['instance_xz'], 'collider_xz': r['collider_xz'],
                                    'collider_moved_m': r.get('collider_moved_m'), 'pass': r['pass']} for r in res['moved_props']['props']},
        'keep_clear_pass_centre_rule': k['pass_centre_rule (layout checker method)'],
        'keep_clear_pass_footprint_rule': k['pass_footprint_rule'],
        'keep_clear_footprint_intrusions': [(r['collider'], r['centre_m'], r['footprint_edge_m'], r['intrusion_m'])
                                            for r in k['non_exempt_within_keep_clear_by_footprint']],
        'arena_11m_pass_by_footprint': k['pass_arena_radius_by_footprint'],
        'exempt_within_keep_clear': len(k['exempt_found']),
        'glow_mushrooms_glade_edge': g['glade_edge']['glow_mushrooms'],
        'glow_mushroom_r_m': g['glade_edge']['glow_mushroom_r_m'],
        'glb_mushroom_glow_min_r_m': g['glb_mushroom_glow_min_r_m'],
        'glow_mushrooms_pass': g['pass_glow_mushrooms_r'],
        'flowers_inside_arena': g['instances_inside_arena_by_footprint']['flowers'],
        'glb_flower_y_max_m': g['glb_flower_y_max_m'],
        'flowers_only_pass': g['pass_flowers_only'], 'flower_height_pass': g['pass_flower_height'],
        'items_on_paths': len(res['paths']['on_a_path']),
        'colliding_items_within_1m_of_path_edge': len(res['paths']['colliding_within_1m_of_a_path_edge']),
        'paths_pass': res['paths']['pass'],
        'moved_props_monster_clearance_pass': res['monster_clearance_of_moved_props']['pass'],
    }
    res['elapsed_s'] = round(time.time() - t0, 1)
    out = P(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(res['summary'], indent=1))
    print('wrote', out)


if __name__ == '__main__':
    main()
