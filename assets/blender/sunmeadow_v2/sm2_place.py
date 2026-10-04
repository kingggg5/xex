"""Placement of existing props, landmarks and rock clusters (pure Python, Babylon XZ)."""
from __future__ import annotations

import math
import random
import re

import sm2_geom as G
from sm2_site import Item, Site, PROP_PATH_GAP, WATER_GAP, STONE_TRAIL_GAP

TAU = math.tau

# Bluff tiers (shared by the mesh builder and the bluff-top accents).
BLUFF_TIERS = {
    'lower': dict(rect=None, y_base=-1.0, y_top=5.6, top_amp=0.35, seed=11,
                  inset={'x0': 0.15, 'x1': 0.95, 'z0': 0.85, 'z1': 0.7}),
    'upper': dict(rect=(-7.0, 11.5, -43.0, -31.8), y_base=4.6, y_top=9.75, top_amp=0.3, seed=23,
                  inset={'x0': 0.1, 'x1': 0.9, 'z0': 0.75, 'z1': 0.65}),
}
OVERHANG = dict(rect=(-8.4, -5.6, -42.0, -34.2), y_base=8.3, y_top=10.05, seed=31)


def bluff_top_y(site: Site, tier: str, x: float, z: float) -> float:
    t = BLUFF_TIERS[tier]
    x0, x1, z0, z1 = t['rect'] or site.bluff_rect
    edge = min(x - x0, x1 - x, z - z0, z1 - z)
    fall = 0.35 * (1 - G.smoothstep(0.0, 2.2, edge))
    return t['y_top'] + t['top_amp'] * (2 * G.fbm2(x / 4.2, z / 4.2, t['seed'], 3) - 1) - fall


def trunk_r_1m(species: str, h: float) -> float:
    if species.startswith('pine'):
        return round(0.034 * h + 0.02, 3)
    if species.startswith('broadleaf'):
        return round(0.038 * h + 0.02, 3)
    return 0.0


def canopy_r_for(species: str, h: float) -> float:
    if species.startswith('pine'):
        return round(0.23 * h, 2)
    if species.startswith('broadleaf'):
        return round(0.37 * h, 2)
    return round(0.75 * h, 2)


SPECIES = {
    # height range (m) and trunk-to-trunk spacing (m) for the proxy species
    'pine_L': dict(h=(11.0, 13.5), spacing=3.8),
    'pine_M': dict(h=(7.5, 9.5), spacing=3.0),
    'broadleaf_L': dict(h=(9.5, 11.5), spacing=4.6),
    'broadleaf_M': dict(h=(6.8, 8.4), spacing=3.6),
    'broadleaf_S': dict(h=(4.6, 5.8), spacing=2.8),
    'bush': dict(h=(0.9, 1.4), spacing=1.7),
    'bush_flowering': dict(h=(0.9, 1.3), spacing=1.7),
}


def add_tree(items, occ, iid, species, x, z, h, yaw, source, zone, base_y=0.0, collider=True, params=None):
    r1 = trunk_r_1m(species, h)
    it = Item(id=iid, category='tree', species=species, x=x, z=z, yaw=yaw, scale=1.0, base_y=base_y, height=h,
              radius=r1, canopy_r=canopy_r_for(species, h), params=params or {}, source=source, zone=zone,
              collider='capsule' if collider else None, collider_r=r1 + 0.05, collider_h=min(h, 4.0))
    items.append(it)
    occ.add(x, z, SPECIES.get(species, {}).get('spacing', 3.0) / 2, 'tree')
    return it


# ----------------------------------------------------------------------------
# Constraint helpers
# ----------------------------------------------------------------------------

class Rules:
    def __init__(self, site: Site):
        self.site = site
        self.keepouts: list[tuple[float, float, float, str]] = []   # (x, z, radius, tag)
        self.corridors: list[tuple[tuple, tuple, float, str]] = []  # (a, b, half width, tag)
        self.rects: list[tuple[float, float, float, float, str]] = []
        self.cliff_lines = [G.Polyline(r) for r in site.cliff_runs()]
        self.toe_line = G.Polyline(site.hill_toe())
        self.forest = G.Polyline(site.forest_line())

    def keep(self, x, z, r, tag, r_tall=None):
        self.keepouts.append((x, z, r, r if r_tall is None else r_tall, tag))

    def keep_rect(self, rect, tag, margin=0.0):
        x0, x1, z0, z1 = rect
        self.rects.append((x0 - margin, x1 + margin, z0 - margin, z1 + margin, tag))

    def corridor(self, a, b, hw, tag, low_too=False):
        self.corridors.append((tuple(a), tuple(b), hw, tag, low_too))

    def path_ok(self, p, r, gap=PROP_PATH_GAP, return_gap=None):
        s = self.site
        for pid, pf in s.paths.items():
            g = return_gap if (return_gap is not None and pid == 'east_return_path') else gap
            if pf.line.distance(p) - pf.hw - r < g:
                return False
        return True

    def water_ok(self, p, r, gap=WATER_GAP):
        return self.site.water_e(p) - r >= gap

    def frame_ok(self, p, r):
        """Inside the walkable frame: east of the cliff face, west of the hill toe, north of the palisade."""
        x, z = p
        for line in self.cliff_lines:          # cliffs run north -> south; east (left, side > 0) is inside
            d, ss, side = line.closest(p)
            if d < r + 0.8 or (side <= 0 and d < r + 12):
                return False
        if x < -53.5 and -64.5 < z < -53.5:    # the cliff gap corridor (stream exit)
            return False
        d, ss, side = self.toe_line.closest(p)  # toe runs north -> south; west (right, side < 0) is inside
        if d < r + 0.8 or side > 0:
            return False
        d, ss, side = self.forest.closest(p)    # forest line runs west -> east; north (left) is inside
        if d < r + 1.0 or side < 0:
            return False
        return True

    def keepout_ok(self, p, r, tall=True, ignore=(), ignore_prefix=()):
        def skip(tag):
            return tag in ignore or any(tag.startswith(px) for px in ignore_prefix)
        for (x, z, r_all, r_tall, tag) in self.keepouts:
            if skip(tag):
                continue
            if math.hypot(p[0] - x, p[1] - z) < (r_tall if tall else r_all) + r:
                return False
        for (x0, x1, z0, z1, tag) in self.rects:
            if not skip(tag) and x0 - r <= p[0] <= x1 + r and z0 - r <= p[1] <= z1 + r:
                return False
        for a, b, hw, tag, low_too in self.corridors:
            if skip(tag) or not (tall or low_too):
                continue
            if G.seg_closest(p, a, b)[0] < hw + r:
                return False
        return True

    def clearing_ok(self, p, r, margin=0.0):
        for c in self.site.clearings.values():
            if self.site.in_clearing(p, c, r + margin):
                return False
        return True

    def bluff_ok(self, p, r, margin=0.5):
        return not self.site.in_rect(p, self.site.bluff_rect, r + margin)


# ----------------------------------------------------------------------------
# Existing props (compact v1 "after" positions, zones.json yaw)
# ----------------------------------------------------------------------------

def place_existing(site: Site, items, occ):
    out = {}
    for p in site.existing_props:
        pid = p['id']
        x, z = float(p['after_xz'][0]), float(p['after_xz'][1])
        moved = None
        if pid in site.prop_moves:          # a layout landmark moves this prop (e.g. broken_cart out of the boss arena)
            mx, mz, lm_id = site.prop_moves[pid]
            moved = {'moved_from_xz': [x, z], 'moved_by_layout_landmark': lm_id}
            site.notes.append(f'{pid} moved by layout landmark {lm_id}: ({x:g},{z:g}) -> ({mx:g},{mz:g})')
            x, z = mx, mz
        yaw = float(site.zone_props.get(pid, {}).get('yaw', 0.0)) % TAU
        h = float(p['unchanged_height_m']) * float(p['unchanged_scale'])
        kind = p['kind']
        src = f'existing:{pid}'
        if kind.startswith('tree'):
            species = ('pine_L' if h >= 9.5 else 'pine_M') if 'pine' in pid else ('broadleaf_L' if h >= 9.0 else 'broadleaf_M')
            it = add_tree(items, occ, pid, species, x, z, h, yaw, src, 'existing')
            it.params['old_collider_size'] = p['unchanged_collider_size']
        elif kind == 'bush':
            it = Item(id=pid, category='bush', species='bush_existing', x=x, z=z, yaw=yaw, height=h, radius=0.75 * p['unchanged_scale'],
                      canopy_r=0.8 * p['unchanged_scale'], source=src, zone='existing', collider='capsule',
                      collider_r=0.65 * p['unchanged_scale'], collider_h=h,
                      params={'old_collider_size': p['unchanged_collider_size']})
            items.append(it)
            occ.add(x, z, 0.9, 'bush')
        elif kind == 'trail_marker':
            # The existing Windstone is the tall monolith outside the ring (4.8 m); footprint kept.
            it = Item(id=pid, category='stone', species='windstone', x=x, z=z, yaw=yaw, height=4.8, radius=0.75,
                      source=src, zone='windstone_monolith', collider='capsule', collider_r=0.78, collider_h=4.8,
                      params={'w': 1.5, 'd': 1.15, 'old_collider_size': p['unchanged_collider_size'], 'old_height_m': h})
            items.append(it)
            occ.add(x, z, 1.0, 'stone')
        elif kind == 'broken_cart':
            it = Item(id=pid, category='prop', species='broken_cart', x=x, z=z, yaw=yaw, height=1.4, radius=1.3,
                      source=src, zone='windstone_glade', collider='box', collider_size=(2.4, 1.6), collider_h=1.4,
                      params={'old_collider_size': p['unchanged_collider_size']})
            items.append(it)
            occ.add(x, z, 1.5, 'prop')
        elif kind == 'stone_pillar':
            s = float(p['unchanged_scale'])
            north = pid.endswith('_north')
            it = Item(id=pid, category='stone', species='gate_stone' if north else 'stone_post', x=x, z=z, yaw=yaw,
                      height=3.2 if north else h, radius=0.45 * s, source=src,
                      zone='windstone_circle' if north else 'south_gate', collider='capsule', collider_r=0.5 * s,
                      collider_h=3.2 if north else h,
                      params={'old_collider_size': p['unchanged_collider_size'], 'scale': s, 'old_height_m': h,
                              'role': 'circle gate stone flanking the trail entry' if north else 'south gate post',
                              'w': 1.0, 'd': 0.8})
            items.append(it)
            occ.add(x, z, 0.6, 'stone')
        else:
            raise ValueError(f'unhandled existing prop kind {kind}')
        if moved:
            it.params.update(moved)
            it.source = f"{src} (moved by layout landmark {moved['moved_by_layout_landmark']})"
        out[pid] = it
    return out


# ----------------------------------------------------------------------------
# Landmarks
# ----------------------------------------------------------------------------

def _trail_gap(site, p, r):
    """Distance from a footprint of radius r to the nearest path edge."""
    return min(pf.line.distance(p) - pf.hw - r for pf in site.paths.values())


def place_stone_circle(site: Site, items, occ, windstone: Item, gate_stones, altar_xz, altar_r):
    """Ring of 6: the two existing north posts are the gate stones; the other stones stand at the layout's
    stone_angles_deg (atan2(dz, dx) from the circle centre, degrees). Without that list, 4 stones spread by
    farthest-point choice over the ring angles that keep >= 1.5 m from every path edge and clear of the altar.
    Layout stones are never moved: a stone that breaks the trail-edge, altar or clash rule is reported in the notes."""
    lm = site.landmarks['windstone_circle']
    cx, cz = (float(v) for v in lm['center_xz'])
    R = float(lm['radius_m'])
    rs = 0.6

    def ang_of(x, z):
        return math.degrees(math.atan2(z - cz, x - cx)) % 360

    gate_angles = sorted(ang_of(g.x, g.z) for g in gate_stones)
    # The gate arc is the shorter arc between the two gate stones that contains the trail entry.
    g0, g1 = gate_angles
    pf = site.paths['southbound_trail']

    def in_gate_arc(t):
        return g0 < t < g1 if (g1 - g0) <= 180 else (t > g1 or t < g0)

    others = [(it.x, it.z, max(it.collider_r, it.radius)) for it in items
              if it.category in ('tree', 'bush', 'stone', 'prop') and math.hypot(it.x - cx, it.z - cz) < R + 3]
    allowed = []
    for t2 in range(0, 720):
        t = t2 / 2
        p = (cx + R * math.cos(math.radians(t)), cz + R * math.sin(math.radians(t)))
        if in_gate_arc(t):
            continue
        if _trail_gap(site, p, rs) < STONE_TRAIL_GAP + 0.05:
            continue
        if math.hypot(p[0] - altar_xz[0], p[1] - altar_xz[1]) < altar_r + rs + 0.6:
            continue
        if any(math.hypot(p[0] - x, p[1] - z) < r + rs + 0.5 for x, z, r in others):
            continue
        allowed.append(t)
    chosen = list(gate_angles)

    def angdist(a, b):
        d = abs(a - b) % 360
        return min(d, 360 - d)

    layout_angles = [float(a) % 360 for a in lm.get('stone_angles_deg', [])]
    if layout_angles:
        # gate stones are the existing posts; every other layout angle gets a new stone
        new = sorted(t for t in layout_angles if min(angdist(t, g) for g in gate_angles) > 1.5)
        for g in gate_angles:
            if min(angdist(g, t) for t in layout_angles) > 1.5:
                site.notes.append(f'STONE CIRCLE: existing gate stone at {g:.1f} deg is not in stone_angles_deg')
        if len(new) + len(gate_angles) != int(lm.get('stones', len(layout_angles))):
            site.notes.append(f'STONE CIRCLE: {len(new)} new + {len(gate_angles)} gate stones != stones {lm.get("stones")}')
    else:
        new = []
        for _ in range(4):
            best = max(allowed, key=lambda t: min(angdist(t, c) for c in chosen))
            chosen.append(best)
            new.append(best)
        new.sort()
    heights = [4.4, 3.4, 4.0, 3.0]
    rng = random.Random(G.stable_seed('stone_circle_v2'))
    out = []
    for i, t in enumerate(new):
        x, z = cx + R * math.cos(math.radians(t)), cz + R * math.sin(math.radians(t))
        h = heights[i % len(heights)]
        w, d = rng.uniform(1.0, 1.25), rng.uniform(0.66, 0.84)
        # keep the 1.5 m trail-edge gap by narrowing the stone, never by moving it off its layout angle
        w = min(w, max(0.8, 2 * (_trail_gap(site, (x, z), 0.0) - STONE_TRAIL_GAP - 0.02)))
        problems = []
        if _trail_gap(site, (x, z), 0.5 * w + 0.02) < STONE_TRAIL_GAP - 1e-6:
            problems.append(f'{_trail_gap(site, (x, z), 0.5 * w + 0.02):.2f} m from a path edge')
        if math.hypot(x - altar_xz[0], z - altar_xz[1]) < altar_r + rs + 0.6:
            problems.append('on the altar platform margin')
        if any(math.hypot(x - ox, z - oz) < r + rs + 0.5 for ox, oz, r in others):
            problems.append('clashes with a tree, bush, stone or prop')
        if problems:
            site.notes.append(f'STONE CIRCLE: stone at {t:.1f} deg ' + '; '.join(problems))
        it = Item(id=f'sm2_circle_stone_{i + 1}', category='stone', species='standing_stone', x=x, z=z,
                  yaw=G.yaw_to(x - cx, z - cz), height=h, radius=0.5 * w, source='landmark:windstone_circle',
                  zone='windstone_circle', collider='capsule', collider_r=0.5 * w + 0.02, collider_h=h,
                  params={'w': round(w, 3), 'd': round(d, 3), 'ring_angle_deg': round(t, 1), 'ring_radius_m': R,
                          'lean': rng.uniform(-0.06, 0.06),
                          'trail_edge_gap_m': round(_trail_gap(site, (x, z), 0.5 * w + 0.02), 2)})
        items.append(it)
        occ.add(x, z, 0.9, 'stone')
        out.append(it)
    for g in gate_stones:
        g.params['ring_angle_deg'] = round(ang_of(g.x, g.z), 1)
        g.params['ring_radius_m'] = round(math.hypot(g.x - cx, g.z - cz), 3)
        g.params['trail_edge_gap_m'] = round(_trail_gap(site, (g.x, g.z), g.collider_r), 2)
    windstone.params['ring_radius_m'] = round(math.hypot(windstone.x - cx, windstone.z - cz), 2)
    windstone.params['trail_edge_gap_m'] = round(_trail_gap(site, (windstone.x, windstone.z), windstone.collider_r), 2)
    spans = []
    if allowed:
        run = [allowed[0]]
        for t in allowed[1:]:
            if t - run[-1] > 0.6:
                spans.append((run[0], run[-1]))
                run = [t]
            else:
                run.append(t)
        spans.append((run[0], run[-1]))
    site.notes.append(f'stone circle centre ({cx},{cz}) r={R}: gate stones at {[round(a, 1) for a in gate_angles]} deg; '
                      f'allowed ring arcs {[(round(a), round(b)) for a, b in spans]}; new stones at {[round(t, 1) for t in new]} deg '
                      f'({"layout stone_angles_deg" if layout_angles else "farthest-point choice"}); trail-edge gaps '
                      f'{[it.params["trail_edge_gap_m"] for it in out]} m')
    return out


ALTAR_BLOCK_R = 0.8    # layout windstone_altar: only the central altar block (r 0.8) collides
ALTAR_BLOCK_H = 1.1


def place_altar(site: Site, items, occ):
    """Flush, walkable platform (radius_m, no collider; the boss stands on it) + central altar block, the only collider."""
    lm = site.landmarks['windstone_altar']
    x, z = (float(v) for v in lm['position_xz'])
    r = float(lm['radius_m'])
    rb = float(lm.get('block_radius_m', ALTAR_BLOCK_R))
    gap = _trail_gap(site, (x, z), r)
    pf = site.paths['southbound_trail']
    d, s, _ = pf.line.closest((x, z))
    tx, tz = pf.line.point_at(s)
    it = Item(id='sm2_windstone_altar', category='landmark', species='altar', x=x, z=z, yaw=G.yaw_to(tx - x, tz - z),
              height=ALTAR_BLOCK_H, radius=r, source='landmark:windstone_altar', zone='windstone_circle', collider='capsule',
              collider_r=rb, collider_h=ALTAR_BLOCK_H,
              params={'trail_edge_gap_m': round(gap, 2), 'platform_radius_m': r, 'platform_top_y': 0.04,
                      'platform': 'flush and walkable, no collider', 'block_radius_m': rb,
                      'role': 'Galehorn field-boss spawn and pacing point (the boss stands on the platform)'})
    items.append(it)
    occ.add(x, z, r + 0.2, 'altar')
    if gap < 1.0:
        site.notes.append(f'ALTAR within {gap:.2f} m of a path edge')
    return it


def _parse_contents(contents):
    out = {}
    for c in contents:
        m = re.match(r'\s*([a-z ]+?)\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]', c)
        if m:
            out[m.group(1).strip()] = (float(m.group(2)), float(m.group(3)))
        elif 'palisade' in c:
            m2 = re.search(r'x\s*=\s*(-?[\d.]+)', c)
            out['palisade'] = (float(m2.group(1)), None)
    return out


def place_camp(site: Site, items, occ):
    lm = site.landmarks['hunter_camp']
    c = _parse_contents(lm['contents'])
    bx0, bx1, bz0, bz1 = lm['bounds_xz']
    defs = {
        'cart': dict(species='cart', yaw=0.38, h=1.6, collider='box', size=(1.6, 3.0), r=1.7),
        'haystack': dict(species='haystack', yaw=0.0, h=1.6, collider='capsule', cr=1.2, r=1.2),
        'tent': dict(species='tent', yaw=0.52, h=2.5, collider='box', size=(3.0, 3.0), r=2.1),
        'crate stack': dict(species='crate_stack', yaw=0.2, h=1.8, collider='box', size=(2.1, 1.3), r=1.2),
        'campfire': dict(species='campfire', yaw=0.0, h=0.9, collider='capsule', cr=0.7, r=0.7),
        'weapon rack': dict(species='weapon_rack', yaw=G.yaw_to(-1, 0), h=1.7, collider='box', size=(1.7, 0.55), r=0.9),
    }
    out = {}
    for key, d in defs.items():
        x, z = c[key]
        iid = 'sm2_camp_' + key.replace(' ', '_')
        it = Item(id=iid, category='prop', species=d['species'], x=x, z=z, yaw=d['yaw'], height=d['h'], radius=d['r'],
                  source='landmark:hunter_camp', zone='hunter_camp', collider=d['collider'],
                  collider_r=d.get('cr', 0.0), collider_size=d.get('size', ()), collider_h=d['h'])
        items.append(it)
        occ.add(x, z, d['r'], 'camp')
        out[key] = it
    # Palisade segments along x = 31 with two walk-through gaps (camp backdrop, not a boundary).
    px = c['palisade'][0]
    segs = [(-15.6, -11.4), (-10.4, -6.9), (-5.9, -3.2)]
    for k, (z0, z1) in enumerate(segs):
        lean = (-1) ** k * 0.06
        a, b = (px + lean, z0), (px - lean, z1)
        it = Item(id=f'sm2_camp_palisade_{k + 1}', category='prop', species='palisade_run', x=(a[0] + b[0]) / 2,
                  z=(a[1] + b[1]) / 2, yaw=G.yaw_to(b[0] - a[0], b[1] - a[1]), height=2.4, radius=0.3,
                  source='landmark:hunter_camp', zone='hunter_camp', collider='box',
                  collider_size=(0.45, math.dist(a, b)), collider_h=2.4,
                  params={'a': a, 'b': b, 'log_h': (2.2, 2.6)})
        items.append(it)
        out[f'palisade_{k + 1}'] = it
    return out


def place_named_landmarks(site: Site, items, occ):
    """Signpost, watchtower (lookout POI), windmarks (POIs), hero oak + shrine + chest, ancient pine."""
    out = {}
    sx, sz = site.landmarks['gate_signpost']['position_xz']
    gr = min(site.paths.values(), key=lambda pf: pf.line.distance((sx, sz)))
    d, s, _ = gr.line.closest((sx, sz))
    tx, tz = gr.line.point_at(s)
    out['signpost'] = Item(id='sm2_gate_signpost', category='landmark', species='signpost', x=sx, z=sz,
                           yaw=G.yaw_to(tx - sx, tz - sz), height=2.7, radius=0.2, source='landmark:gate_signpost',
                           zone='gate', collider='capsule', collider_r=0.2, collider_h=2.7,
                           params={'text': 'Sunmeadow / Windstone Glade'})
    lx, lz = site.pois['lookout']
    out['watchtower'] = Item(id='sm2_lookout_watchtower', category='landmark', species='watchtower', x=lx, z=lz,
                             yaw=0.3, height=8.2, radius=1.9, source='landmark:lookout (POI lookout)',
                             zone='windmark_hunt', collider='posts', collider_r=0.2, collider_h=4.6,
                             params={'post_offset': 1.35, 'platform_y': 4.6})
    for wid in ('windmark_1', 'windmark_2', 'windmark_3'):
        wx, wz = site.pois[wid]
        rng = random.Random(G.stable_seed(wid))
        out[wid] = Item(id=f'sm2_{wid}', category='landmark', species='windmark', x=wx, z=wz,
                        yaw=rng.uniform(0, TAU), height=2.0, radius=0.45, source=f'landmark:windmarks (POI {wid})',
                        zone='windmark_hunt', collider='capsule', collider_r=0.45, collider_h=2.0,
                        params={'path_edge_gap_m': round(min(pf.line.distance((wx, wz)) - pf.hw for pf in site.paths.values()) - 0.45, 2)})
    ox, oz = site.landmarks['old_sunmeadow_oak']['position_xz']
    oh = float(site.landmarks['old_sunmeadow_oak']['height_m'])
    out['hero_oak'] = Item(id='sm2_old_sunmeadow_oak', category='tree', species='hero_oak', x=ox, z=oz, yaw=0.8,
                           height=oh, radius=0.82, canopy_r=6.6, source='landmark:old_sunmeadow_oak',
                           zone='east_oak_grove', collider='capsule', collider_r=0.87, collider_h=4.0)
    ax, az = site.landmarks['ancient_pine']['position_xz']
    ah = float(site.landmarks['ancient_pine']['height_m'])
    out['ancient_pine'] = Item(id='sm2_ancient_pine', category='tree', species='ancient_pine', x=ax, z=az, yaw=0.2,
                               height=ah, radius=0.6, canopy_r=4.4, source='landmark:ancient_pine',
                               zone='windstone_glade', collider='capsule', collider_r=0.65, collider_h=4.0)
    # Shrine + chest under the hero oak, on the path side, >= 1.0 m from the path edge.
    rp = site.paths['east_return_path']
    d, s, _ = rp.line.closest((ox, oz))
    px, pz = rp.line.point_at(s)
    base_ang = math.atan2(pz - oz, px - ox)
    placed = []
    for name, dist, foot, size, h in (('shrine', 2.05, 0.7, (1.0, 0.8), 1.45), ('chest', 2.0, 0.55, (0.95, 0.62), 0.7)):
        best = None
        for k in range(-18, 19):
            ang = base_ang + math.radians(10 * k)
            q = (ox + dist * math.cos(ang), oz + dist * math.sin(ang))
            gap = min(pf.line.distance(q) - pf.hw for pf in site.paths.values()) - foot
            if gap < 1.0:
                continue
            if any(math.hypot(q[0] - o.x, q[1] - o.z) < foot + o.radius + 0.5 for o in placed):
                continue
            score = abs(k) * 10 + (0 if gap < 2.2 else 5)
            if best is None or score < best[0]:
                best = (score, q, gap)
        if best is None:
            raise RuntimeError(f'no {name} position under the hero oak')
        _, (qx, qz), gap = best
        it = Item(id=f'sm2_oak_{name}', category='landmark', species=name, x=qx, z=qz,
                  yaw=G.yaw_to(px - qx, pz - qz), height=h, radius=foot, source='landmark:old_sunmeadow_oak',
                  zone='east_oak_grove', collider='box', collider_size=size, collider_h=h,
                  params={'path_edge_gap_m': round(gap, 2)})
        placed.append(it)
        out[name] = it
    for it in out.values():
        items.append(it)
        occ.add(it.x, it.z, max(it.radius, 0.6), it.category)
    return out


def place_bluff_top(site: Site, items):
    spots = [('pine', 14.2, -33.6, 6.2), ('pine', 14.9, -42.7, 5.4), ('broadleaf', 8.8, -44.7, 4.6),
             ('bush', 13.4, -38.3, 1.1), ('bush', 15.3, -36.7, 1.0), ('bush', 3.6, -44.8, 0.9), ('bush', -4.6, -44.7, 1.0)]
    out = []
    for k, (kind, x, z, h) in enumerate(spots):
        y = bluff_top_y(site, 'lower', x, z)
        if kind == 'bush':
            it = Item(id=f'sm2_bluff_top_bush_{k + 1}', category='bush', species='bush', x=x, z=z, yaw=k * 1.3, base_y=y,
                      height=h, radius=0.7, canopy_r=0.8, source='zone:bluff_top', zone='bluff_top')
        else:
            sp = 'pine_M' if kind == 'pine' else 'broadleaf_S'
            it = Item(id=f'sm2_bluff_top_{kind}_{k + 1}', category='tree', species=sp, x=x, z=z, yaw=k * 1.1, base_y=y,
                      height=h, radius=trunk_r_1m(sp, h), canopy_r=canopy_r_for(sp, h), source='zone:bluff_top',
                      zone='bluff_top')
        items.append(it)
        out.append(it)
    return out


# ----------------------------------------------------------------------------
# Rock clusters
# ----------------------------------------------------------------------------

def _rock(iid, x, z, size, rng, source, zone, base_y=0.0, collider=True, species='boulder'):
    sx = size * rng.uniform(0.85, 1.1)
    sy = size * rng.uniform(0.8, 1.0)
    sz = size * rng.uniform(0.5, 0.75)
    r = 0.5 * max(sx, sy)
    return Item(id=iid, category='rock', species=species, x=x, z=z, yaw=rng.uniform(0, TAU), base_y=base_y,
                height=round(sz * 0.62, 3), radius=round(r, 3), source=source, zone=zone,
                collider='capsule' if collider else None, collider_r=round(0.9 * r, 3), collider_h=round(sz * 0.62, 3),
                params={'size': [round(sx, 3), round(sy, 3), round(sz, 3)], 'seed': rng.randrange(1 << 30)})


def place_rocks(site: Site, items, occ, rules: Rules):
    out = []
    specs = site.rock_specs
    # Bluff base boulders: around the footprint, partly embedded, clear of the falls view and paths.
    rng = random.Random(G.stable_seed('bluff_base_boulders'))
    spec = specs['bluff_base_boulders']
    n = rng.randint(*spec['count'])
    x0, x1, z0, z1 = site.bluff_rect
    per = 2 * ((x1 - x0) + (z1 - z0))
    tries = 0
    k = 0
    while k < n and tries < 4000:
        tries += 1
        u = rng.uniform(0, per)
        size = rng.uniform(*spec['size_m'])
        r = 0.5 * size
        off = rng.uniform(-0.25, 0.75) * r
        if u < x1 - x0:
            p, nrm = (x0 + u, z1), (0, 1)
        elif u < (x1 - x0) + (z1 - z0):
            p, nrm = (x1, z1 - (u - (x1 - x0))), (1, 0)
        elif u < 2 * (x1 - x0) + (z1 - z0):
            p, nrm = (x1 - (u - (x1 - x0) - (z1 - z0)), z0), (0, -1)
        else:
            p, nrm = (x0, z0 + (u - 2 * (x1 - x0) - (z1 - z0))), (-1, 0)
        q = (p[0] + nrm[0] * off, p[1] + nrm[1] * off)
        if nrm == (-1, 0) and -44.5 < q[1] < -31.5:
            continue          # west face: keep the falls and pool readable from the trail
        if not rules.path_ok(q, r) or not rules.water_ok(q, r, 0.6):
            continue
        if not occ.clear_of(q[0], q[1], r, 0.3):
            continue
        if not rules.keepout_ok(q, r, tall=size > 1.2):
            continue
        it = _rock(f'sm2_bluff_boulder_{k + 1}', q[0], q[1], size, rng, 'rock_cluster:bluff_base_boulders', 'inner_bluff')
        it.params['embedded_in'] = 'inner_bluff'
        items.append(it)
        occ.add(q[0], q[1], r, 'rock')
        out.append(it)
        k += 1
    # Stream stones: in the water near the edges or on the wet bank inside the water-edge collider band.
    rng = random.Random(G.stable_seed('stream_stones'))
    spec = specs['stream_stones']
    n = rng.randint(*spec['count'])
    k, tries = 0, 0
    while k < n and tries < 4000:
        tries += 1
        s = rng.uniform(1.0, site.stream.length - 1.0)
        c = site.stream.point_at(s)
        t = site.stream.tangent_at(s)
        nrm = G.left_normal(t)
        side = rng.choice((-1, 1))
        size = rng.uniform(*spec['size_m'])
        r = 0.5 * size
        hw = site.stream_width_at(s) / 2
        e = rng.uniform(-0.9, 0.05) if size > 0.9 else rng.uniform(-0.35, 0.05)
        if e + r > 0.45:
            e = 0.45 - r
        q = (c[0] + nrm[0] * side * (hw + e), c[1] + nrm[1] * side * (hw + e))
        a, l = site.bridge_local(q)
        if abs(a) < 6.0 and abs(l) < 6.0:
            continue
        if q[0] < -63.0 or not occ.clear_of(q[0], q[1], r, 0.25):
            continue
        it = _rock(f'sm2_stream_stone_{k + 1}', q[0], q[1], size, rng, 'rock_cluster:stream_stones', 'stream',
                   base_y=site.ground_h(q), collider=False, species='stream_stone')
        it.params['water_edge_offset_m'] = round(e, 2)
        items.append(it)
        occ.add(q[0], q[1], r, 'rock')
        out.append(it)
        k += 1
    # Meadow painted rocks at the windmark_hunt edges.
    rng = random.Random(G.stable_seed('meadow_painted_rocks'))
    spec = specs['meadow_painted_rocks']
    n = rng.randint(*spec['count'])
    bx0, bx1, bz0, bz1 = site.clearings['windmark_hunt']['bounds_xz']
    k, tries = 0, 0
    while k < n and tries < 6000:
        tries += 1
        edge = rng.randrange(4)
        t = rng.random()
        inset = rng.uniform(-3.5, 2.0)
        if edge == 0:
            q = (G.lerp(bx0, bx1, t), bz1 + inset)
        elif edge == 1:
            q = (G.lerp(bx0, bx1, t), bz0 - inset)
        elif edge == 2:
            q = (bx0 - inset, G.lerp(bz0, bz1, t))
        else:
            q = (bx1 + inset, G.lerp(bz0, bz1, t))
        size = rng.uniform(*spec['size_m'])
        r = 0.5 * size
        if not rules.path_ok(q, r) or not rules.keepout_ok(q, r, tall=False):
            continue
        if not occ.clear_of(q[0], q[1], r, 3.0, ignore=()):
            continue
        it = _rock(f'sm2_painted_rock_{k + 1}', q[0], q[1], size, rng, 'rock_cluster:meadow_painted_rocks',
                   'windmark_hunt', species='painted_rock')
        items.append(it)
        occ.add(q[0], q[1], r, 'rock')
        out.append(it)
        k += 1
    # Cliff debris along the west cliffs, plus the two boulders that close the gap's south bank.
    rng = random.Random(G.stable_seed('cliff_debris'))
    spec = specs['cliff_debris']
    n = rng.randint(*spec['count'])
    seal = gap_seal_boulders(site, rng)
    for it in seal:
        items.append(it)
        occ.add(it.x, it.z, it.radius, 'rock')
        out.append(it)
    runs = [G.Polyline(r) for r in site.cliff_runs()]
    k, tries = len(seal), 0
    while k < n and tries < 6000:
        tries += 1
        run = runs[rng.randrange(len(runs))]
        s = rng.uniform(0, run.length)
        c = run.point_at(s)
        t = run.tangent_at(s)
        east = G.left_normal(t)
        size = rng.uniform(*spec['size_m'])
        r = 0.5 * size
        off = rng.uniform(-0.6, 0.55) * r
        q = (c[0] + east[0] * off, c[1] + east[1] * off)
        if q[1] > 21.0 or q[1] < -103.0:
            continue
        if not rules.water_ok(q, r, 1.0) or not rules.path_ok(q, r):
            continue
        if not occ.clear_of(q[0], q[1], r, 0.8):
            continue
        it = _rock(f'sm2_cliff_debris_{k + 1}', q[0], q[1], size, rng, 'rock_cluster:cliff_debris', 'west_cliffs')
        it.params['embedded_in'] = 'west_cliffs'
        items.append(it)
        occ.add(q[0], q[1], r, 'rock')
        out.append(it)
        k += 1
    return out


def gap_seal_boulders(site: Site, rng):
    """Two debris boulders on the stream's south bank in the cliff gap (the north bank strip is < 0.7 m wide)."""
    runs = site.cliff_runs()
    a, b = runs[0][-1], runs[1][0]          # gap mouth on the cliff face line
    line = G.Polyline([a, b])
    out = []
    # first boulder: centre where the bank clearance equals 0.3 m + radius, measured along the mouth line
    r1 = 1.55
    s_best = None
    for k in range(0, int(line.length * 100)):
        s = k / 100
        q = line.point_at(s)
        if site.water_e(q) >= 0.3 + r1 and s > line.length / 2:
            s_best = s
            break
    q = line.point_at(s_best)
    t = line.tangent_at(s_best)
    east = G.left_normal(t)
    q1 = (q[0] - east[0] * 0.35, q[1] - east[1] * 0.35)
    it1 = _rock('sm2_cliff_debris_gap_seal_1', q1[0], q1[1], 2 * r1, rng, 'rock_cluster:cliff_debris', 'west_cliffs')
    it1.collider_r = r1
    it1.params['role'] = 'closes the south bank of the cliff gap (stream exit)'
    q2 = (q1[0] - 1.9, q1[1] - 0.9)
    it2 = _rock('sm2_cliff_debris_gap_seal_2', q2[0], q2[1], 2.4, rng, 'rock_cluster:cliff_debris', 'west_cliffs')
    it2.params['role'] = 'backs the gap seal'
    out += [it1, it2]
    return out
