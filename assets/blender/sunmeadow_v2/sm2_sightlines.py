"""Quantitative sightline check for the Sunmeadow v2 blockout (Blender 5.2, ray casts in the built scene).

For each layout sightline, rays go from eye-height points (1.65 m) and from the locked game camera (ArcRotate 13 m,
beta 1.18, collision-shortened like the renders) to sample points on the target. A sample counts as visible when
the first surface hit carries the target's own material (unique per landmark), or when nothing is hit before the
sample. Vegetation, rock and relief all occlude, as they would in game; witnesses, colliders and annotations do not.
"""
from __future__ import annotations

import math
import re

import bpy
from mathutils import Vector

import sm2_geom as G

SKIP_PREFIX = ('COL_', 'W_')


def _first_hit(dg, origin_b, target_b, extra=0.6):
    scene = bpy.context.scene
    o = Vector(G.bl(origin_b[0], origin_b[2], origin_b[1]))
    t = Vector(G.bl(target_b[0], target_b[2], target_b[1]))
    d = t - o
    dist = d.length
    d.normalize()
    travelled = 0.0
    for _ in range(16):
        hit, loc, nrm, idx, ob, mtx = scene.ray_cast(dg, o, d, distance=max(0.01, dist + extra - travelled))
        if not hit:
            return None, dist
        if ob is not None and (ob.get('layer') in ('annotation', 'witness') or ob.name.startswith(SKIP_PREFIX)):
            step = (loc - o).length + 0.01
            o = loc + d * 0.01
            travelled += step
            continue
        mat = ob.active_material.name if ob is not None and ob.active_material else None
        hb = (-loc.x, loc.z, -loc.y)
        return (mat, hb, travelled + (loc - o).length), dist
    return None, dist


def _visible(dg, origin, target, accept):
    h, dist = _first_hit(dg, origin, target)
    if h is None:
        return True, 'open'
    mat, hb, hd = h
    if accept(mat, hb):
        return True, mat
    if hd >= dist - 0.05:
        return True, 'beyond'
    return False, mat


def _sweep_points(dg, origin, pts, accept):
    vis, blockers = [], {}
    for p in pts:
        ok, what = _visible(dg, origin, p, accept)
        vis.append(ok)
        if not ok:
            blockers[what] = blockers.get(what, 0) + 1
    return vis, blockers


def _top_run(vis, ys):
    """Length of the contiguous visible run that ends at the top sample."""
    run_low = None
    for ok, y in sorted(zip(vis, ys), key=lambda q: -q[1]):
        if not ok:
            break
        run_low = y
    return 0.0 if run_low is None else round(max(ys) - run_low + (ys[1] - ys[0] if len(ys) > 1 else 0.0), 2)


def _xz(p):
    return f'{p[0]:g}_{p[1]:g}'


def _key(n, s):
    """Result key from the layout sightline: '1_city_exit_ramps_to_ancient_pine', '3_glade_to_inner_bluff', ..."""
    slug = re.sub(r'\W+', '_', s['from'].split('(')[0].split('[')[0].strip().lower()).strip('_')
    return f"{n}_{slug}_to_{s['to']}"


def _tag(frm):
    """Short origin tag: 'city_exit_ramp_west' -> 'west_ramp'; 'glade [-12,-60]' -> 'glade'."""
    words = frm.split('[')[0].strip().replace(' ', '_').split('_')
    if len(words) > 2 and words[-1] in ('west', 'east', 'north', 'south'):
        return f'{words[-1]}_{words[-2]}'
    return '_'.join(words)


def sightline_check(site, items, game_camera_fn, log):
    dg = bpy.context.evaluated_depsgraph_get()
    by_id = {it.id: it for it in items}
    pine = next(it for it in items if it.species == 'ancient_pine')
    oak = next(it for it in items if it.species == 'hero_oak')
    stones = [it for it in items if it.zone in ('windstone_circle', 'windstone_monolith') and it.category in ('stone', 'landmark')
              and it.species != 'altar']      # the altar block is sampled once below (its platform is flush)
    sl = {s['to']: s for s in site.sightline_points()}
    cams = {}

    def cam_pos(tag, feet, aim_xz):
        yaw = G.yaw_to(aim_xz[0] - feet[0], aim_xz[1] - feet[1])
        cam, m = game_camera_fn(f'slc_{tag}', feet, yaw, dg)
        cams[tag] = m
        p = cam.location
        return (-p.x, p.z, -p.y)

    out = {}
    # 1. layout origin (city exit ramps, game camera) -> ancient pine (lure over the bluff; the glade stays hidden)
    ys = [0.5 * k for k in range(1, int(pine.height / 0.5) + 1)]
    pine_pts = [(pine.x, y, pine.z) for y in ys]
    acc_pine = lambda m, hb: m in ('pine_ancient',) or (m == 'trunk' and math.hypot(hb[0] - pine.x, hb[2] - pine.z) < 1.2)  # noqa: E731
    glade_pts, glade_names = [], []
    for st in stones:
        for y in (1.2, max(1.3, st.height - 0.25)):
            glade_pts.append((st.x, y, st.z))
            glade_names.append(st.id)
    altar = by_id.get('sm2_windstone_altar')
    if altar:
        glade_pts.append((altar.x, 0.6, altar.z))
        glade_names.append(altar.id)
    acc_glade = lambda m, hb: m in ('stone_circle', 'windstone', 'stone_carved', 'stone_light', 'stone_post')  # noqa: E731
    s1 = sl['ancient_pine']
    # layout origin(s) first (the city exit ramps, worded for the game camera), then context views further in
    origins = {}
    for fid, fxz in s1['from_points']:
        t = _tag(fid)
        origins[f'{t}_cam_{_xz(fxz)}'] = cam_pos(f'{t}_cam', tuple(fxz), (pine.x, pine.z))
        origins[f'{t}_eye_{_xz(fxz)}'] = (fxz[0], 1.65, fxz[1])
    g = site.anchors['city_gate']
    origins.update({f'gate_eye_{_xz(g)} (city gate)': (g[0], 1.65, g[1]),
                    'gate_road_cam_-8_9': cam_pos('gate_road', (-8.0, 9.0), (pine.x, pine.z)),
                    'hunt_centre_cam_0_5': cam_pos('hunt_centre', (0.0, 5.0), (pine.x, pine.z))})
    r1 = {}
    for name, o in origins.items():
        vis, bl = _sweep_points(dg, o, pine_pts, acc_pine)
        gvis, gbl = _sweep_points(dg, o, glade_pts, acc_glade)
        r1[name] = {'origin_babylon_xyz': [round(v, 2) for v in o],
                    'pine_samples_visible': f'{sum(vis)}/{len(vis)}',
                    'pine_visible_top_m': _top_run(vis, ys),
                    'pine_lowest_visible_y_m': min((y for v, y in zip(vis, ys) if v), default=None),
                    'pine_blocked_by': bl,
                    'glade_stone_samples_visible': f'{sum(gvis)}/{len(gvis)}',
                    'glade_visible_ids': sorted({n for v, n in zip(gvis, glade_names) if v})}
    out[_key(1, s1)] = {'from': s1['from'], 'intent': s1['intent'], 'target': f'ancient pine {pine.height} m at ({pine.x},{pine.z})',
                        'samples': 'pine axis every 0.5 m; glade = circle stones (1.2 m + top) and altar block',
                        'views': r1}
    # 2. trail (layout origin) -> bluff falls (reveal)
    s2 = sl['bluff_falls']
    fx, fz = site.falls['top_xz']
    top_y, bot_y = float(site.falls['top_y']), float(site.falls['bottom_y'])
    fys = [bot_y + 0.25 + 0.5 * k for k in range(int((top_y - bot_y) / 0.5))]
    falls_pts = [(fx - 0.35, y, fz + dz) for y in fys for dz in (-0.45, 0.0, 0.45)]
    px, pz, pr = site.pool
    pool_pts = [(px + 0.6 * pr * math.cos(a), site.water_y + 0.03, pz + 0.6 * pr * math.sin(a)) for a in [k * math.tau / 8 for k in range(8)]]
    acc_falls = lambda m, hb: m in ('waterfall', 'foam')  # noqa: E731
    acc_pool = lambda m, hb: m in ('water', 'foam', 'waterfall') and math.hypot(hb[0] - px, hb[2] - pz) < pr + 0.8  # noqa: E731
    f2 = s2['from_xz']
    t2 = _tag(s2['from'])
    origins = {f'{t2}_eye_{_xz(f2)}': (f2[0], 1.65, f2[1]),
               f'{t2}_cam_{_xz(f2)}': cam_pos(f'{t2}_{_xz(f2)}', tuple(f2), (fx, fz)),
               'trail_cam_-12_-28 (before the reveal)': cam_pos('trail_m12_m28', (-12.0, -28.0), (fx, fz)),
               'trail_cam_-18_-46 (after)': cam_pos('trail_m18_m46', (-18.0, -46.0), (fx, fz))}
    r2 = {}
    for name, o in origins.items():
        vis, bl = _sweep_points(dg, o, falls_pts, acc_falls)
        pvis, pbl = _sweep_points(dg, o, pool_pts, acc_pool)
        r2[name] = {'origin_babylon_xyz': [round(v, 2) for v in o], 'falls_visible_share': round(sum(vis) / len(vis), 2),
                    'falls_blocked_by': bl, 'pool_visible_share': round(sum(pvis) / len(pvis), 2), 'pool_blocked_by': pbl}
    out[_key(2, s2)] = {'from': s2['from'], 'intent': s2['intent'],
                        'samples': f'{len(falls_pts)} falls-sheet points, 8 pool points', 'views': r2}
    # 3. glade -> inner bluff (+ falls) look back home
    s3 = sl['inner_bluff']
    x0, x1, z0, z1 = site.bluff_rect
    bh = float(site.relief['inner_bluff']['height_m'])
    bluff_pts = [(x0 + (x1 - x0) * k / 12, yy, z0 - 0.4) for k in range(13) for yy in (bh * 0.45, bh - 0.6)]
    bluff_mats = ('rock_bluff', 'moss_top', 'rock_boulder')
    acc_bluff = lambda m, hb: m in bluff_mats or (x0 - 1 <= hb[0] <= x1 + 1 and z0 - 1 <= hb[2] <= z1 + 1 and hb[1] > 4.0)  # noqa: E731
    f3 = s3['from_xz']
    t3 = _tag(s3['from'])
    bc = ((x0 + x1) / 2, (z0 + z1) / 2)
    cc = tuple(site.landmarks['windstone_circle']['center_xz'])
    origins = {f'{t3}_eye_{_xz(f3)}': (f3[0], 1.65, f3[1]),
               f'{t3}_cam_{_xz(f3)}': cam_pos(f'{t3}_{_xz(f3)}', tuple(f3), bc),
               f'{t3}_cam_{_xz(f3)}_aim_falls': cam_pos(f'{t3}_{_xz(f3)}_falls', tuple(f3), (fx, fz)),
               f'circle_eye_{_xz(cc)} (circle centre)': (cc[0], 1.65, cc[1]),
               f'circle_cam_{_xz(cc)} (circle centre)': cam_pos('circle_centre', cc, bc)}
    r3 = {}
    for name, o in origins.items():
        vis, bl = _sweep_points(dg, o, bluff_pts, acc_bluff)
        fvis, fbl = _sweep_points(dg, o, falls_pts, acc_falls)
        r3[name] = {'origin_babylon_xyz': [round(v, 2) for v in o], 'bluff_south_face_visible_share': round(sum(vis) / len(vis), 2),
                    'bluff_blocked_by': bl, 'falls_visible_share': round(sum(fvis) / len(fvis), 2), 'falls_blocked_by': fbl}
    out[_key(3, s3)] = {'from': s3['from'], 'intent': s3['intent'],
                        'samples': f'{len(bluff_pts)} bluff south-face points; falls as in 2', 'views': r3}
    # 4. east return path (layout origin) -> old sunmeadow oak (discovery)
    s4 = sl['old_sunmeadow_oak']
    oys = [1.5, 3.0] + [4.0 + 0.5 * k for k in range(int((oak.height - 4.0) / 0.5) + 1)]
    oak_pts = [(oak.x, y, oak.z) for y in oys]
    acc_oak = lambda m, hb: m in ('hero_canopy', 'trunk_hero')  # noqa: E731
    f4 = s4['from_xz']
    origins = {f'path_eye_{_xz(f4)}': (f4[0], 1.65, f4[1]),
               f'path_cam_{_xz(f4)}': cam_pos(f'path_{_xz(f4)}', tuple(f4), (oak.x, oak.z))}
    for q, note in (((28.0, -42.0), 'oak bend'), ((18.0, -60.0), 'loop start'), ((26.0, -30.0), 'from the north')):
        if math.dist(q, f4) > 1.0:
            origins[f'path_cam_{_xz(q)} ({note})'] = cam_pos(f'path_{_xz(q)}', q, (oak.x, oak.z))
    r4 = {}
    for name, o in origins.items():
        vis, bl = _sweep_points(dg, o, oak_pts, acc_oak)
        r4[name] = {'origin_babylon_xyz': [round(v, 2) for v in o], 'distance_to_oak_m': round(math.hypot(o[0] - oak.x, o[2] - oak.z), 1),
                    'oak_samples_visible': f'{sum(vis)}/{len(vis)}', 'oak_blocked_by': bl}
    out[_key(4, s4)] = {'from': s4['from'], 'intent': s4['intent'], 'samples': 'oak axis 1.5 m, 3 m and every 0.5 m from 4 m',
                        'views': r4}
    for k, v in out.items():
        log(f'SIGHTLINE {k}: ' + '; '.join(f"{n}: " + ', '.join(f'{a}={b}' for a, b in r.items()
                                                                   if a not in ('origin_babylon_xyz',) and not a.endswith('blocked_by'))
                                           for n, r in v['views'].items()))
    for ob in [o for o in bpy.data.objects if o.name.startswith('slc_')]:
        bpy.data.objects.remove(ob, do_unlink=True)
    return {'method': __doc__.strip(), 'cameras': cams, 'sightlines': out}
