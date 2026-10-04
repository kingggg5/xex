"""Colliders for the Sunmeadow v2 blockout (Babylon coordinates), plus walk-reachability pruning.

Shapes
  box:     center [x, y, z], size [sx, sy, sz], yaw (rad). size[0] runs along local X = (cos a, -sin a) in XZ,
           size[2] along local Z = (sin a, cos a).  polygon_xz is the exact convex footprint (CCW).
  capsule: vertical; center [x, y, z], radius, size [2r, h, 2r]. polygon_xz is a circumscribed 12-gon.
Every collider names the visible object it sits on (`visual`). Blocker kinds match the server's
grounded_city BlockerInput kinds: solid_structure | tree_trunk | wall | street_object | water_hazard.
"""
from __future__ import annotations

import math

import sm2_geom as G
from sm2_site import Site, WATER_EDGE_BAND, cell_of

PLAYER_R = 0.35


class Colliders:
    def __init__(self, site: Site):
        self.site = site
        self.items: list[dict] = []
        self.existing: list[dict] = []
        self.pruned: list[str] = []

    # ------------------------------------------------------------------ constructors
    def box(self, cid, kind, category, cx, cz, sx, sz, yaw, y0, y1, visual, note='', target=None, poly=None):
        polygon = poly or G.obb_corners(cx, cz, sx, sz, yaw)
        d = {'id': cid, 'kind': kind, 'category': category, 'shape': 'box',
             'center': [G.r6(cx), G.r6((y0 + y1) / 2), G.r6(cz)], 'size': [G.r6(sx), G.r6(y1 - y0), G.r6(sz)],
             'yaw': G.r6(yaw % math.tau), 'polygon_xz': [[G.r6(x), G.r6(z)] for x, z in G.ccw(polygon)],
             'y_min': G.r6(y0), 'y_max': G.r6(y1), 'visual': visual, 'cell': cell_of(cx, cz)}
        if note:
            d['note'] = note
        (target if target is not None else self.items).append(d)
        return d

    def capsule(self, cid, kind, category, cx, cz, r, y0, y1, visual, note=''):
        d = {'id': cid, 'kind': kind, 'category': category, 'shape': 'capsule',
             'center': [G.r6(cx), G.r6((y0 + y1) / 2), G.r6(cz)], 'radius': G.r6(r),
             'size': [G.r6(2 * r), G.r6(y1 - y0), G.r6(2 * r)], 'yaw': 0.0,
             'polygon_xz': [[G.r6(x), G.r6(z)] for x, z in G.circle_polygon(cx, cz, r, 12)],
             'y_min': G.r6(y0), 'y_max': G.r6(y1), 'visual': visual, 'cell': cell_of(cx, cz)}
        if note:
            d['note'] = note
        self.items.append(d)
        return d

    # ------------------------------------------------------------------ geometry queries
    @staticmethod
    def signed_distance(c, p) -> float:
        if c['shape'] == 'capsule':
            return math.hypot(p[0] - c['center'][0], p[1] - c['center'][2]) - c['radius']
        if 'trapezoid' in c or c['shape'] == 'polygon':
            poly = c['polygon_xz']
            inside = G.point_in_polygon(p, poly)
            d = G.polygon_edge_distance(p, poly)
            return -d if inside else d
        return G.obb_distance(p, c['center'][0], c['center'][2], c['size'][0], c['size'][2], c['yaw'])

    @staticmethod
    def bbox(c):
        xs = [q[0] for q in c['polygon_xz']]
        zs = [q[1] for q in c['polygon_xz']]
        return min(xs), max(xs), min(zs), max(zs)


def _segment_box(cols, cid, kind, category, a, b, off0, off1, ext_a, ext_b, y0, y1, visual, note=''):
    u = G.norm(G.sub(b, a))
    a2 = G.sub(a, G.mul(u, ext_a))
    b2 = G.add(b, G.mul(u, ext_b))
    cx, cz, sx, sz, yaw = G.obb_from_segment(a2, b2, off0, off1)
    return cols.box(cid, kind, category, cx, cz, sx, sz, yaw, y0, y1, visual, note)


def relief_colliders(site: Site, cols: Colliders, cliff_heights=None):
    x0, x1, z0, z1 = site.bluff_rect
    cols.box('sunmeadow_compact_inner_bluff', 'solid_structure', 'relief', (x0 + x1) / 2, (z0 + z1) / 2, x1 - x0,
             z1 - z0, 0.0, 0.0, float(site.relief['inner_bluff']['height_m']), 'sm2_inner_bluff',
             note='same footprint and id as compact v1; visual base sits on this footprint')
    # West cliffs: face line runs north -> south, the rock is on the right (west), 6 m deep.
    for ri, run in enumerate(site.cliff_runs()):
        for k, (a, b) in enumerate(zip(run, run[1:])):
            first, last = k == 0, k == len(run) - 2
            gap_end_a = ri == 1 and first
            gap_end_b = ri == 0 and last
            _segment_box(cols, f'sm2_west_cliff_{ri + 1}_{k + 1}', 'wall', 'relief', a, b, -6.0, 0.0,
                         0.0 if gap_end_a else 0.6, 0.0 if gap_end_b else 0.6, 0.0, 8.0, 'sm2_west_cliffs',
                         note='face at the cliff toe line; gap at z -55..-63 left open for the stream')
    # East hills: toe line runs north -> south, the hill is on the left (east), 4 m deep from the toe.
    toe = site.hill_toe()
    for k, (a, b) in enumerate(zip(toe, toe[1:])):
        _segment_box(cols, f'sm2_east_hill_toe_{k + 1}', 'wall', 'relief', a, b, 0.0, 4.0, 0.6, 0.6, 0.0, 3.0,
                     'sm2_east_hills', note='hill toe line; visible slope starts here')
    # South palisade runs + closed gate.
    for name, (a, b) in site.palisade_runs().items():
        ext_a = 0.3 if name == 'palisade_wing_east' else 0.5
        ext_b = 0.3 if name == 'palisade_wing_west' else 0.5
        _segment_box(cols, f'sm2_{name}', 'wall', 'relief', a, b, -0.225, 0.225, ext_a, ext_b, 0.0, 2.6,
                     f'sm2_{name}', note='palisade log row')
    (wx, wz), (ex, ez) = site.gate_posts()
    cols.box('sm2_south_gate_leaves', 'wall', 'relief', (wx + ex) / 2, (wz + ez) / 2, (ex - wx) - 0.4, 0.36, 0.0,
             0.0, 2.4, 'sm2_south_gate', note='closed gate between the existing stone posts (+-6.4,-99)')


def water_colliders(site: Site, cols: Colliders):
    """Water-edge bands (0.2 m into the water to 0.5 m up the bank) along both stream edges and the pool."""
    lo, hi = WATER_EDGE_BAND
    line = site.stream
    pts = line.pts
    n_seg = len(pts) - 1
    count = 0
    for i in range(n_seg):
        a, b = pts[i], pts[i + 1]
        seg_len = math.dist(a, b)
        u = G.norm(G.sub(b, a))
        nrm = G.left_normal(u)
        # joint extension on both ends (fills the outer wedge at bends)
        ext = []
        for j in (i, i + 1):
            if 0 < j < len(pts) - 1:
                u1, u2 = G.norm(G.sub(pts[j], pts[j - 1])), G.norm(G.sub(pts[j + 1], pts[j]))
                phi = math.acos(max(-1.0, min(1.0, G.dot(u1, u2))))
                hw = site.stream_width_at(line.cum[j]) / 2
                ext.append((hw + hi) * math.tan(phi / 2) + 0.1)
            else:
                ext.append(0.0)
        near_bridge = min(G.seg_closest(site.bridge_c, a, b)[0], 1e9) < 9.0
        piece = 0.45 if near_bridge else 3.0
        n = max(1, int(math.ceil(seg_len / piece)))
        for k in range(n):
            t0, t1 = k / n, (k + 1) / n
            s0, s1 = line.cum[i] + seg_len * t0, line.cum[i] + seg_len * t1
            pa = (G.lerp(a[0], b[0], t0), G.lerp(a[1], b[1], t0))
            pb = (G.lerp(a[0], b[0], t1), G.lerp(a[1], b[1], t1))
            ea = ext[0] if k == 0 else 0.0
            eb = ext[1] if k == n - 1 else 0.0
            pa2, pb2 = G.sub(pa, G.mul(u, ea)), G.add(pb, G.mul(u, eb))
            hw0, hw1 = site.stream_width_at(s0) / 2, site.stream_width_at(s1) / 2
            for side, tag in ((1, 'L'), (-1, 'R')):
                corners = [G.add(pa2, G.mul(nrm, side * (hw0 + lo))), G.add(pb2, G.mul(nrm, side * (hw1 + lo))),
                           G.add(pb2, G.mul(nrm, side * (hw1 + hi))), G.add(pa2, G.mul(nrm, side * (hw0 + hi)))]
                cxz = (sum(q[0] for q in corners) / 4, sum(q[1] for q in corners) / 4)
                if all(site.pool_e(q) < -0.2 for q in corners):
                    continue          # inside the pool water: unreachable
                aa, ll = site.bridge_local(cxz)
                if abs(aa) <= site.bridge_hl + 0.05 and abs(ll) <= site.bridge_hw - 0.15 + 0.25:
                    continue          # under the walkable deck (rails close the sides)
                if cxz[0] < site.stage[0] - 0.5:
                    continue
                count += 1
                hwm = (hw0 + hw1) / 2
                cx, cz, sx, sz, yaw = G.obb_from_segment(pa2, pb2, side * (hwm + lo), side * (hwm + hi))
                d = cols.box(f'sm2_stream_edge_{tag}_{i + 1}_{k + 1:02d}', 'water_hazard', 'water', cx, cz, sx, sz, yaw,
                             -0.35, 1.2, 'sm2_sunmeadow_stream', poly=corners,
                             note='stream edge band: 0.2 m into the water to 0.5 m up the bank')
                d['trapezoid'] = True
    # Pool ring (skip the stream mouth).
    px, pz, pr = site.pool
    n = 18
    for k in range(n):
        a0, a1 = math.tau * k / n, math.tau * (k + 1) / n
        r0, r1 = pr + lo, pr + hi
        corners = [(px + r0 * math.cos(a0), pz + r0 * math.sin(a0)), (px + r0 * math.cos(a1), pz + r0 * math.sin(a1)),
                   (px + r1 / math.cos(math.pi / n) * math.cos(a1), pz + r1 / math.cos(math.pi / n) * math.sin(a1)),
                   (px + r1 / math.cos(math.pi / n) * math.cos(a0), pz + r1 / math.cos(math.pi / n) * math.sin(a0))]
        cxz = (sum(q[0] for q in corners) / 4, sum(q[1] for q in corners) / 4)
        if site.stream_e(cxz) < -0.25:
            continue
        am = (a0 + a1) / 2
        rm = (r0 + r1) / 2
        tangent = (-math.sin(am), math.cos(am))
        cols_d = cols.box(f'sm2_pool_edge_{k + 1:02d}', 'water_hazard', 'water', px + rm * math.cos(am),
                          pz + rm * math.sin(am), r1 - r0, 2 * r1 * math.tan(math.pi / n), math.atan2(tangent[0], tangent[1]),
                          -0.35, 1.2, 'sm2_falls_pool', poly=corners, note='pool edge band')
        cols_d['trapezoid'] = True
    # Bridge rails: the only bridge colliders (deck is walkable).
    c, u, nrm = site.bridge_c, site.bridge_u, site.bridge_n
    yaw = math.atan2(u[0], u[1])
    for side, tag in ((1, 'north'), (-1, 'south')):
        cx, cz = c[0] + nrm[0] * side * 1.95, c[1] + nrm[1] * side * 1.95
        cols.box(f'sm2_bridge_rail_{tag}', 'wall', 'bridge', cx, cz, 0.4, 2 * site.bridge_hl + 0.6, yaw, 0.0, 1.1,
                 'sm2_stream_bridge', note='rope-and-post rail + corner abutment stones; deck stays walkable')
    return count


def item_colliders(site: Site, cols: Colliders, items):
    kinds = {'tree': ('tree_trunk', 'trunk'), 'stone': ('solid_structure', 'stone'), 'rock': ('solid_structure', 'rock'),
             'bush': ('street_object', 'bush_existing'), 'prop': ('street_object', 'camp'),
             'landmark': ('street_object', 'landmark')}
    for it in items:
        if not it.collider:
            continue
        kind, category = kinds[it.category]
        if it.zone == 'hunter_camp':
            category = 'camp'
        if it.species == 'broken_cart':
            category = 'prop'
        if it.collider == 'capsule':
            cols.capsule(f'col_{it.id}', kind, category, it.x, it.z, it.collider_r, it.base_y, it.base_y + it.collider_h,
                         it.id)
        elif it.collider == 'box':
            sx, sz = it.collider_size
            cols.box(f'col_{it.id}', kind, category, it.x, it.z, sx, sz, it.yaw, it.base_y, it.base_y + it.collider_h, it.id)
        elif it.collider == 'posts':
            off = it.params['post_offset']
            for k, (px, pz) in enumerate(((-off, -off), (off, -off), (off, off), (-off, off))):
                wx = it.x + px * math.cos(it.yaw) + pz * math.sin(it.yaw)
                wz = it.z - px * math.sin(it.yaw) + pz * math.cos(it.yaw)
                cols.capsule(f'col_{it.id}_post_{k + 1}', kind, category, wx, wz, it.collider_r, 0.0, it.collider_h, it.id,
                             note='tower post; the space under the platform stays walkable')


def existing_context(site: Site, cols: Colliders):
    """Existing blockers inside the stage that this blockout must respect but does not own (not exported).

    The layout's hazard (city canal) and the live city-traversal blockers at the gate replace compact v1's two
    town-gate wing boxes, which would cut across the live arrival ramps (x +-6.85..13.35)."""
    for h in site.hazards:
        x0, x1, z0, z1 = (float(v) for v in h['bounds_xz'])
        d = cols.box(h['id'], 'water_hazard', 'existing_city_hazard', (x0 + x1) / 2, (z0 + z1) / 2, x1 - x0, z1 - z0, 0.0,
                     -100.0, 0.35, 'city canal water (live city, canal-water-0)', target=cols.existing,
                     note=h.get('source', 'layout hazard'))
        d['shape'] = 'polygon'
    for b in site.city_blockers:
        if b['kind'] == 'water_hazard' or b['y_min'] >= 1.8 or b['y_max'] <= 0.0:
            continue
        poly = [tuple(q) for q in b['polygon_xz']]
        xs, zs = [q[0] for q in poly], [q[1] for q in poly]
        d = {'id': f"city:{b['id']}", 'kind': b['kind'], 'category': 'existing_city', 'shape': 'polygon',
             'center': [G.r6((min(xs) + max(xs)) / 2), G.r6((b['y_min'] + b['y_max']) / 2), G.r6((min(zs) + max(zs)) / 2)],
             'size': [G.r6(max(xs) - min(xs)), G.r6(b['y_max'] - b['y_min']), G.r6(max(zs) - min(zs))], 'yaw': 0.0,
             'polygon_xz': [[G.r6(x), G.r6(z)] for x, z in G.ccw(poly)], 'y_min': b['y_min'], 'y_max': b['y_max'],
             'visual': f"live city: {b['id']}", 'cell': cell_of((min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2),
             'note': 'live city traversal blocker (content/source/zones.json), city lane'}
        cols.existing.append(d)


def rasterize(site: Site, colliders, res=0.1, bounds=None):
    x0, x1, z0, z1 = bounds or (site.stage[0], site.stage[1], site.stage[2], site.stage[3])
    ras = G.Raster(x0, x1, z0, z1, res)
    for c in colliders:
        ras.block_shape(Colliders.bbox(c), lambda p, c=c: Colliders.signed_distance(c, p), PLAYER_R)
    return ras


def build_colliders(site: Site, items, prune=True):
    cols = Colliders(site)
    relief_colliders(site, cols)
    n_water = water_colliders(site, cols)
    existing_context(site, cols)
    base = list(cols.items) + list(cols.existing)
    item_colliders(site, cols, items)
    reach = None
    if prune:
        ras = rasterize(site, base, 0.2)
        start = site.anchors['trail_start']
        reach = ras.flood(start)
        keep = []
        for c in cols.items:
            if c['category'] in ('relief', 'water', 'bridge'):
                keep.append(c)
                continue
            r = c.get('radius') or max(c['size'][0], c['size'][2]) / 2
            cx, cz = c['center'][0], c['center'][2]
            hit = False
            for k in range(16):
                a = math.tau * k / 16
                for rr in (r + 0.45, r + 0.9):
                    idx = ras.index(cx + rr * math.cos(a), cz + rr * math.sin(a))
                    if idx is not None and reach[idx[1] * ras.nx + idx[0]]:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                keep.append(c)
            else:
                cols.pruned.append(c['id'])
        cols.items = keep
        pruned_visuals = {cid[4:] for cid in cols.pruned if cid.startswith('col_')}
        for it in items:
            if it.id in pruned_visuals:
                it.params['collider_pruned'] = 'unreachable (behind the frame or on the bluff)'
    ids = [c['id'] for c in cols.items + cols.existing]
    if len(ids) != len(set(ids)):
        raise RuntimeError('duplicate collider ids')
    return cols, n_water
