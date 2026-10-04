"""2D walk check for the Sunmeadow v2 blockout (pure Python).

Sweeps a 0.35 m capsule along every JSON path polyline at 0.25 m spacing against colliders.json, then checks
that the bridge deck is walkable, that water blocks, that the stage frame does not leak, and that POIs and
spawn homes are not inside colliders.

  python assets/blender/sunmeadow_v2/walk_check.py \
      --colliders assets/models/sunmeadow-v2/blockout/colliders.json \
      --out planning/evidence/sunmeadow-v2-blockout/walk_check.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sm2_geom as G  # noqa: E402
from sm2_site import ROOT, Site  # noqa: E402

R = 0.35
H = 1.8
STEP = 0.25


class Shape:
    def __init__(self, c):
        self.c = c
        self.id = c['id']
        self.cat = c['category']
        self.capsule = c['shape'] == 'capsule'
        if self.capsule:
            self.cx, self.cz, self.r = c['center'][0], c['center'][2], c['radius']
            self.bb = (self.cx - self.r, self.cx + self.r, self.cz - self.r, self.cz + self.r)
        else:
            self.poly = [tuple(q) for q in c['polygon_xz']]
            xs, zs = [q[0] for q in self.poly], [q[1] for q in self.poly]
            self.bb = (min(xs), max(xs), min(zs), max(zs))
        self.blocks = c['y_min'] < H and c['y_max'] > 0.0

    def sd(self, p):
        if self.capsule:
            return math.hypot(p[0] - self.cx, p[1] - self.cz) - self.r
        d = G.polygon_edge_distance(p, self.poly)
        return -d if G.point_in_polygon(p, self.poly) else d

    def near(self, p, margin):
        x0, x1, z0, z1 = self.bb
        return x0 - margin <= p[0] <= x1 + margin and z0 - margin <= p[1] <= z1 + margin


def sweep(site, shapes, gate_ids):
    out = {}
    for pid, pf in site.paths.items():
        line = pf.line
        n = int(math.ceil(line.length / STEP))
        best = (1e9, None, None)
        hits = []
        for k in range(n + 1):
            s = min(line.length, k * STEP)
            p = line.point_at(s)
            for sh in shapes:
                if not sh.blocks or not sh.near(p, 8.0):
                    continue
                clr = sh.sd(p) - R
                if clr < best[0]:
                    best = (clr, sh.id, round(s, 2))
                if clr < 0:
                    hits.append({'s_m': round(s, 2), 'xz': [round(p[0], 2), round(p[1], 2)], 'collider': sh.id,
                                 'category': sh.cat, 'penetration_m': round(-clr, 3),
                                 'expected': sh.id in gate_ids})
        runs = []
        for h in hits:
            if runs and runs[-1]['collider'] == h['collider'] and h['s_m'] - runs[-1]['s_to'] <= STEP + 1e-6:
                runs[-1]['s_to'] = h['s_m']
                runs[-1]['max_penetration_m'] = max(runs[-1]['max_penetration_m'], h['penetration_m'])
                runs[-1]['samples'] += 1
            else:
                runs.append({'collider': h['collider'], 'category': h['category'], 's_from': h['s_m'], 's_to': h['s_m'],
                             'xz_from': h['xz'], 'max_penetration_m': h['penetration_m'], 'samples': 1,
                             'expected': h['expected']})
        unexpected = [r for r in runs if not r['expected']]
        # minimum clearance excluding expected (by-design) blockers such as the closed south gate
        best_open = (1e9, None, None)
        for k in range(n + 1):
            s = min(line.length, k * STEP)
            p = line.point_at(s)
            for sh in shapes:
                if not sh.blocks or sh.id in gate_ids or not sh.near(p, 8.0):
                    continue
                clr = sh.sd(p) - R
                if clr < best_open[0]:
                    best_open = (clr, sh.id, round(s, 2))
        out[pid] = {'length_m': round(line.length, 2), 'samples': n + 1, 'width_m': pf.width,
                    'min_clearance_m': round(best[0], 3), 'closest_collider': best[1], 'at_s_m': best[2],
                    'min_clearance_excluding_by_design_m': round(best_open[0], 3), 'closest_excluding_by_design': best_open[1],
                    'hit_runs': runs, 'unexpected_hit_runs': len(unexpected), 'pass': not unexpected}
    return out


def bridge_check(site, shapes):
    pf = site.paths['southbound_trail']
    on, clrs = 0, []
    for (p, s) in pf.line.sample(STEP):
        if site.on_deck(p, 0.0):
            on += 1
            m = min(sh.sd(p) - R for sh in shapes if sh.blocks and sh.near(p, 6.0))
            clrs.append(m)
    water_under = sum(1 for (p, s) in pf.line.sample(STEP) if site.on_deck(p, 0.0) and site.water_e(p) < 0)
    return {'deck_samples': on, 'deck_samples_over_water': water_under,
            'min_clearance_on_deck_m': round(min(clrs), 3) if clrs else None,
            'deck_walkable': bool(clrs) and min(clrs) >= 0.0}


def water_transects(site, shapes):
    """Walk straight across the stream from bank to bank at stations away from the bridge: must be blocked."""
    water = [sh for sh in shapes if sh.cat == 'water']
    results = []
    L = site.stream.length
    s = 3.0
    while s < L - 1.0:
        c = site.stream.point_at(s)
        nrm = G.left_normal(site.stream.tangent_at(s))
        hw = site.stream_width_at(s) / 2
        a, l = site.bridge_local(c)
        if abs(a) < 5.5 and abs(l) < 5.5:
            s += 4.0
            continue
        blocked_sides = []
        for side in (1, -1):
            start = G.add(c, G.mul(nrm, side * (hw + 2.2)))
            blocked = False
            for k in range(0, 60):
                t = k * 0.05
                p = G.add(start, G.mul(nrm, -side * t))       # walk toward the centreline
                if site.stream_e(p) < -0.3:
                    break                                     # reached the open water interior: not blocked
                if any(sh.near(p, 1.0) and sh.sd(p) < R for sh in water):
                    blocked = True
                    break
            blocked_sides.append(blocked)
        results.append({'s_m': round(s, 1), 'xz': [round(c[0], 2), round(c[1], 2)], 'blocked_both_banks': all(blocked_sides)})
        s += 4.0
    return {'transects': len(results), 'blocked': sum(r['blocked_both_banks'] for r in results),
            'failed': [r for r in results if not r['blocked_both_banks']], 'pass': all(r['blocked_both_banks'] for r in results)}


def flood(site, shapes, res=0.1):
    x0, x1, z0, z1 = site.stage
    ras = G.Raster(x0, x1, z0, z1, res)
    for sh in shapes:
        if sh.blocks:
            ras.block_shape(sh.bb, sh.sd, R)
    start = site.anchors['trail_start']
    reach = ras.flood(start)
    nx, nz = ras.nx, ras.nz
    allowed_exit = [(-11.6, -6.4), (6.4, 11.6)]          # live city arrival ramps between the canal and the towers
    boundary, exits = [], 0
    for i in range(nx):
        for j in (0, nz - 1):
            if reach[j * nx + i]:
                p = ras.centre(i, j)
                if j == nz - 1 and any(a <= p[0] <= b for a, b in allowed_exit):
                    exits += 1
                else:
                    boundary.append(p)
    for j in range(nz):
        for i in (0, nx - 1):
            if reach[j * nx + i]:
                boundary.append(ras.centre(i, j))
    wet, bluff = 0, 0
    bx0, bx1, bz0, bz1 = site.bluff_rect
    for j in range(nz):
        z = z0 + (j + 0.5) * res
        for i in range(nx):
            if not reach[j * nx + i]:
                continue
            x = x0 + (i + 0.5) * res
            if -66 < x < -4 and -66 < z < -32 and site.water_e((x, z)) < -0.25 and not site.on_deck((x, z)):
                wet += 1
            if bx0 < x < bx1 and bz0 < z < bz1:
                bluff += 1

    # City canal hazard (live canal-water-0): no reachable capsule centre inside its rectangle.
    canal = 0
    for (cx0, cx1, cz0, cz1) in site.canal_rects():
        for j in range(nz):
            z = z0 + (j + 0.5) * res
            if not (cz0 <= z <= cz1):
                continue
            for i in range(nx):
                x = x0 + (i + 0.5) * res
                if cx0 <= x <= cx1 and reach[j * nx + i]:
                    canal += 1

    def approach_m(p, rmax=3.0):
        """Distance from p to the nearest reachable capsule centre (None if none within rmax)."""
        best = None
        n = int(rmax / res) + 1
        c = ras.index(p[0], p[1])
        if c is None:
            return None
        for dj in range(-n, n + 1):
            for di in range(-n, n + 1):
                i, j = c[0] + di, c[1] + dj
                if 0 <= i < nx and 0 <= j < nz and reach[j * nx + i]:
                    q = ras.centre(i, j)
                    d = math.hypot(q[0] - p[0], q[1] - p[1])
                    if d <= rmax and (best is None or d < best):
                        best = d
        return round(best, 2) if best is not None else None

    anchors = {k: approach_m(v) for k, v in site.anchors.items()}
    pois = {k: approach_m(v) for k, v in site.pois.items()}
    return {'resolution_m': res, 'reachable_area_m2': round(sum(reach) * res * res, 1),
            'city_ramp_exit_cells': exits, 'leaks_at_stage_edge': len(boundary),
            'leak_points_sample': [[round(p[0], 1), round(p[1], 1)] for p in boundary[:20]],
            'reachable_water_interior_cells': wet, 'reachable_bluff_cells': bluff, 'reachable_canal_cells': canal,
            'approach_m_note': 'distance from the point to the nearest reachable capsule centre (0 = standing on it); '
                               'object-anchored POIs (windmarks, windstone) are approached at the object',
            'anchors_approach_m': anchors, 'pois_approach_m': pois,
            'pois_all_approachable_within_2_5m': all(v is not None and v <= 2.5 for v in pois.values() if v is not None)
                                                 and all(pois[k] is not None for k in pois if k != 'city_gate'),
            'pass': not boundary and wet == 0 and bluff == 0 and canal == 0}


BY_DESIGN_POINTS = {
    'poi:windmark_1': ('col_sm2_windmark_1', 'the POI is the windmark stone itself; players interact at the stone'),
    'poi:windmark_2': ('col_sm2_windmark_2', 'the POI is the windmark stone itself; players interact at the stone'),
    'poi:windmark_3': ('col_sm2_windmark_3', 'the POI is the windmark stone itself; players interact at the stone'),
    'poi:south_trail_marker': ('col_sunmeadow_windstone', 'the POI is the existing sunmeadow_windstone monolith'),
    'poi:city_gate': ('city_canal_water_0', 'city-side anchor beyond the live canal; players arrive by the ramps'),
}


def point_clearances(site, shapes):
    pts = [('poi:' + k, v) for k, v in site.pois.items()]
    pts += [(f'compact_spawn:{k}:{e}', (x, z)) for k, (e, x, z, c) in enumerate(site.spawns)]
    pts += [(f'v2_home:row{row}:{e}', (x, z), br) for (x, z, br, row, e) in site.monster_homes]
    out, bad, by_design, legacy = [], [], [], []
    for rec_in in pts:
        name, p = rec_in[0], rec_in[1]
        body = rec_in[2] if len(rec_in) > 2 else None
        best = (1e9, None)
        for sh in shapes:
            if sh.blocks and sh.near(p, 6.0):
                d = sh.sd(p)
                if d < best[0]:
                    best = (d, sh.id)
        rec = {'point': name, 'xz': [p[0], p[1]], 'clearance_to_nearest_collider_m': round(best[0] - R, 3) if best[1] else None,
               'nearest': best[1]}
        if body is not None and best[1]:
            rec['monster_body_radius_m'] = body
            rec['body_clearance_m'] = round(best[0] - body, 3)
        out.append(rec)
        if best[1] and best[0] - R < 0:
            exp = BY_DESIGN_POINTS.get(name)
            if exp and exp[0] == best[1]:
                by_design.append(dict(rec, reason=exp[1]))
            elif name.startswith('compact_spawn:'):
                legacy.append(dict(rec, reason='compact v1 after_xz; the v2 monster plan supplies the authoritative homes'))
            else:
                bad.append(rec)
    return {'points': len(out), 'inside_or_touching_collider': bad, 'by_design_object_anchors': by_design,
            'legacy_compact_v1_conflicts': legacy, 'pass': not bad, 'all': out}


def corridor_intrusions(site, shapes, gate_ids):
    """Colliders reaching inside a path's walk corridor (centreline +- half-width)."""
    found = {}
    rails = [sh for sh in shapes if sh.cat == 'bridge']
    for pid, pf in site.paths.items():
        for (p, s) in pf.line.sample(0.5):
            hw = pf.hw
            if site.on_deck(p, 0.0) and rails:
                # on the bridge the walk corridor ends at the rails' inner face (anything beyond is outside the deck)
                hw = min(hw, min(r.sd(p) for r in rails))
            for sh in shapes:
                if not sh.blocks or sh.id in gate_ids or sh.cat == 'bridge' or not sh.near(p, pf.hw + 2):
                    continue
                d = sh.sd(p)
                if d < hw:
                    key = (pid, sh.id)
                    depth = hw - d
                    if key not in found or depth > found[key]['intrusion_m']:
                        found[key] = {'path': pid, 'collider': sh.id, 'category': sh.cat, 'intrusion_m': round(depth, 3),
                                      'at_xz': [round(p[0], 2), round(p[1], 2)]}
    return sorted(found.values(), key=lambda r: -r['intrusion_m'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--colliders', default='assets/models/sunmeadow-v2/blockout/colliders.json')
    ap.add_argument('--out', default='planning/evidence/sunmeadow-v2-blockout/walk_check.json')
    a = ap.parse_args()
    t0 = time.time()
    cpath = Path(a.colliders)
    cpath = cpath if cpath.is_absolute() else ROOT / cpath
    data = json.loads(cpath.read_text(encoding='utf-8'))
    site = Site()
    shapes = [Shape(c) for c in data['colliders']] + [Shape(c) for c in data.get('existing_preserved', [])]
    gate_ids = {'sm2_south_gate_leaves'}
    try:
        cref = cpath.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        cref = str(cpath)
    res = {'schema': 'xexoria.sunmeadow-v2.walk-check/1', 'colliders_json': cref,
           'colliders_sha256': __import__('hashlib').sha256(cpath.read_bytes()).hexdigest(),
           'capsule_radius_m': R, 'capsule_height_m': H, 'sample_step_m': STEP,
           'note': 'centreline sweep of every JSON path polyline; distances use exact collider footprints '
                   '(polygon_xz for boxes and water bands, circles for capsules)'}
    res['paths'] = sweep(site, shapes, gate_ids)
    res['bridge'] = bridge_check(site, shapes)
    res['water_block'] = water_transects(site, shapes)
    res['flood_fill'] = flood(site, shapes)
    res['point_clearance'] = point_clearances(site, shapes)
    res['path_corridor_intrusions'] = corridor_intrusions(site, shapes, gate_ids)
    res['summary'] = {
        'min_clearance_by_path_m': {k: v['min_clearance_excluding_by_design_m'] for k, v in res['paths'].items()},
        'unexpected_hits': sum(v['unexpected_hit_runs'] for v in res['paths'].values()),
        'by_design_hits': [dict(path=k, **r) for k, v in res['paths'].items() for r in v['hit_runs'] if r['expected']],
        'deck_walkable': res['bridge']['deck_walkable'], 'water_blocks': res['water_block']['pass'],
        'stream_and_pool_interior_unreachable': res['flood_fill']['reachable_water_interior_cells'] == 0,
        'canal_blocks': res['flood_fill']['reachable_canal_cells'] == 0,
        'bluff_blocks': res['flood_fill']['reachable_bluff_cells'] == 0,
        'frame_sealed': res['flood_fill']['leaks_at_stage_edge'] == 0, 'flood_fill_pass': res['flood_fill']['pass'],
        'points_clear': res['point_clearance']['pass'],
        'points_inside_colliders': [r['point'] for r in res['point_clearance']['inside_or_touching_collider']],
        'legacy_v1_points_inside_colliders': [r['point'] for r in res['point_clearance']['legacy_compact_v1_conflicts']],
        'corridor_intrusions': len(res['path_corridor_intrusions'])}
    res['elapsed_s'] = round(time.time() - t0, 1)
    out = Path(a.out)
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(res['summary'], indent=1))
    print('wrote', out)


if __name__ == '__main__':
    main()
