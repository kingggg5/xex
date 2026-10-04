"""Vegetation and small-decor scatter for the Sunmeadow v2 blockout (pure Python, Babylon XZ).

Clusters come from a seeded Poisson-disc of cluster centres, 3-6 members per cluster, open gap discs per
zone, and spacing checks against everything already placed, so nothing lines up in rows.
"""
from __future__ import annotations

import math
import random

import sm2_geom as G
from sm2_place import (SPECIES, Rules, add_tree, place_altar, place_bluff_top, place_camp, place_existing,
                       place_named_landmarks, place_rocks, place_stone_circle)
from sm2_site import Item, Site

TAU = math.tau
STAGE_MARGIN = 1.0


def pick(mix: dict, rng: random.Random) -> str:
    total = sum(mix.values())
    r = rng.random() * total
    acc = 0.0
    for k, w in mix.items():
        acc += w
        if r <= acc:
            return k
    return k


def foot_radius(species: str, h: float) -> float:
    from sm2_place import trunk_r_1m
    if species.startswith('bush'):
        return 0.8
    return trunk_r_1m(species, h)


def setup_rules(site: Site, rules: Rules, marks: dict, altar: Item):
    for it in marks.values():
        r_all = {'signpost': 1.5, 'watchtower': 3.2, 'windmark': 2.5, 'hero_oak': 3.0, 'ancient_pine': 2.0,
                 'shrine': 1.2, 'chest': 1.2}.get(it.species, 1.5)
        r_tall = {'hero_oak': 7.6, 'ancient_pine': 5.0, 'watchtower': 3.6}.get(it.species, r_all)
        rules.keep(it.x, it.z, r_all, it.id, r_tall)
    for pid, (x, z) in site.pois.items():
        rules.keep(x, z, 3.0 if pid == 'sella' else 2.0, f'poi:{pid}')
    for k, (enemy, x, z, cl) in enumerate(site.spawns):
        rules.keep(x, z, 2.0, f'spawn:{k}')
    # v2 monster plan: body radius + 1.0 m around every home, 1.2 m either side of every patrol segment.
    for (x, z, br, row, enemy) in site.monster_homes:
        rules.keep(x, z, br + 1.0, f'spawn:home{row}')
    for (a, b, row) in site.monster_patrols:
        rules.corridor(a, b, 1.2, f'spawn:patrol{row}', low_too=True)
    for (x, z, r, zone) in site.monster_keep:
        rules.keep(x, z, r, f'monster_keep:{zone}')
    circle = site.landmarks['windstone_circle']
    cx, cz = circle['center_xz']
    arena = float(circle.get('boss_arena_radius_m', 10.0))
    rules.keep(cx, cz, float(circle['radius_m']) + 1.4, 'windstone_circle', arena)
    rules.keep(altar.x, altar.z, altar.radius + 0.7, altar.id)
    for kc in site.zones['east_oak_grove'].get('keep_clear', []):
        kx, kz = kc['center_xz']
        r = float(kc['radius_m'])
        # Hero oak: the JSON keeps 5 m clear; tall trees get 7 m so the 6.6 m canopy reads on its own.
        rules.keep(kx, kz, r, f"keep_clear:{kc['id']}", max(r, 7.0) if kc['id'] == 'old_sunmeadow_oak' else r)
    for k, rect in enumerate(site.canal_rects()):
        rules.keep_rect(rect, f'hazard:canal{k}', 0.5)
    # City arrival porch: the live ramps (x +-6.85..13.35, z 8..24) and the canal outflow stay clear of scatter.
    rules.keep_rect((-16.3, 16.3, 8.0, 24.0), 'gate_apron')
    for sx in (-1, 1):
        rules.keep_rect(tuple(sorted((sx * 6.85, sx * 13.35))) + (8.0, 24.0), f'city_ramp{sx:+d}', 0.3)
    rules.keep(site.bridge_c[0], site.bridge_c[1], 6.5, 'stream_bridge')
    rules.keep_rect(site.landmarks['hunter_camp']['bounds_xz'], 'hunter_camp', 1.5)
    rules.keep_rect((-10.5, 10.5, -106.0, -94.5), 'south_gate')
    rules.corridor((-18.0, -40.0), (-7.6, -38.0), 1.5, 'falls_view')
    rules.corridor((28.0, -42.0), (32.0, -44.0), 2.0, 'oak_view')
    rules.corridor((24.0, -52.0), (31.0, -45.0), 2.0, 'oak_approach')


def _base_ok(site: Site, rules: Rules, p, foot, tall, path_gap=1.0, return_gap=None, in_clearings=False):
    x0, x1, z0, z1 = site.stage
    if not (x0 + STAGE_MARGIN <= p[0] <= x1 - STAGE_MARGIN and z0 + STAGE_MARGIN <= p[1] <= z1 - STAGE_MARGIN):
        return False
    if not rules.frame_ok(p, foot):
        return False
    if not rules.path_ok(p, foot, path_gap, return_gap):
        return False
    if not rules.water_ok(p, foot):
        return False
    if not rules.bluff_ok(p, foot, 0.6):
        return False
    if not in_clearings and not rules.clearing_ok(p, foot, 0.0):
        return False
    return rules.keepout_ok(p, foot, tall=tall)


def scatter_clusters(site, rules, occ, items, zone_id, members=(3, 6), gaps=(2, 3), r_cluster=10.5, member_r=4.6,
                     return_gap=None):
    zone = site.zones[zone_id]
    poly = [tuple(map(float, q)) for q in zone['polygon_xz']]
    mix = zone['mix']
    rng = random.Random(G.stable_seed(zone_id))
    gap_candidates = G.poisson_in_polygon(poly, 12.0, rng)
    rng.shuffle(gap_candidates)
    gap_discs = [(q[0], q[1], rng.uniform(5.0, 6.5)) for q in gap_candidates[:rng.randint(*gaps)]]

    def outside_gaps(p, pad=0.0):
        return all(math.hypot(p[0] - gx, p[1] - gz) > gr + pad for gx, gz, gr in gap_discs)

    centres = G.poisson_in_polygon(poly, r_cluster, rng, accept=lambda p: outside_gaps(p, 2.5))
    placed, clusters = [], []
    kept = 0
    for ci, c in enumerate(centres):
        n = rng.randint(*members)
        pending, tries = [], 0
        while len(pending) < n and tries < 90:
            tries += 1
            species = pick(mix, rng)
            ang = rng.uniform(0, TAU)
            rr = member_r * (math.sqrt(rng.random()) if not species.startswith('bush') else rng.uniform(0.55, 1.05))
            p = (c[0] + rr * math.cos(ang), c[1] + rr * math.sin(ang))
            if not G.point_in_polygon(p, poly) or not outside_gaps(p):
                continue
            h = rng.uniform(*SPECIES[species]['h'])
            foot = foot_radius(species, h)
            tall = not species.startswith('bush')
            if not _base_ok(site, rules, p, foot, tall, return_gap=return_gap):
                continue
            half = SPECIES[species]['spacing'] / 2
            if not occ.clear_of(p[0], p[1], half):
                continue
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) < half + qh for (q, qh, *_rest) in pending):
                continue
            pending.append((p, half, species, h, rng.uniform(0, TAU)))
        if len(pending) < members[0]:
            clusters.append(0)
            continue          # never leave a 1-2 tree fragment: a cluster is 3+ or nothing
        kept += 1
        for mi, (p, half, species, h, yaw) in enumerate(pending):
            iid = f'sm2_{zone_id}_{kept:02d}_{mi + 1}'
            if not species.startswith('bush'):
                it = add_tree(items, occ, iid, species, p[0], p[1], h, yaw, f'scatter:{zone_id}', zone_id)
            else:
                it = Item(id=iid, category='bush', species=species, x=p[0], z=p[1], yaw=yaw, height=h,
                          radius=0.8, canopy_r=0.85, source=f'scatter:{zone_id}', zone=zone_id)
                items.append(it)
                occ.add(p[0], p[1], half, 'bush')
            it.params['cluster'] = kept
            placed.append(it)
        clusters.append(len(pending))
    site.notes.append(f'{zone_id}: {len(centres)} clusters, members {clusters}, gaps '
                      f'{[(round(g[0], 1), round(g[1], 1), round(g[2], 1)) for g in gap_discs]}')
    return placed, gap_discs


def scatter_pine_stand(site, rules, occ, items, existing):
    zone_id = 'west_pine_stand'
    zone = site.zones[zone_id]
    poly = [tuple(map(float, q)) for q in zone['polygon_xz']]
    mix = zone['mix']
    rng = random.Random(G.stable_seed(zone_id))
    seeds = [(it.x, it.z) for it in existing.values() if it.category == 'tree' and G.point_in_polygon((it.x, it.z), poly)]
    gap_candidates = G.poisson_in_polygon(poly, 11.0, rng)
    rng.shuffle(gap_candidates)
    gap_discs = [(q[0], q[1], rng.uniform(3.8, 4.8)) for q in gap_candidates[:2]]
    pts = G.poisson_in_polygon(poly, 3.4, rng, seeds=seeds,
                               accept=lambda p: all(math.hypot(p[0] - gx, p[1] - gz) > gr for gx, gz, gr in gap_discs))
    placed = []
    for k, p in enumerate(pts):
        species = pick(mix, rng)
        h = rng.uniform(*SPECIES[species]['h'])
        foot = foot_radius(species, h)
        tall = not species.startswith('bush')
        if not _base_ok(site, rules, p, foot, tall):
            continue
        if not occ.clear_of(p[0], p[1], (SPECIES[species]['spacing'] / 2) * 0.85):
            continue
        iid = f'sm2_{zone_id}_{k + 1:03d}'
        if tall:
            it = add_tree(items, occ, iid, species, p[0], p[1], h, rng.uniform(0, TAU), f'scatter:{zone_id}', zone_id)
        else:
            it = Item(id=iid, category='bush', species='bush', x=p[0], z=p[1], yaw=rng.uniform(0, TAU), height=h,
                      radius=0.8, canopy_r=0.85, source=f'scatter:{zone_id}', zone=zone_id)
            items.append(it)
            occ.add(p[0], p[1], 0.85, 'bush')
        placed.append(it)
    # Understory: mushrooms and ferns between the trunks (visual only).
    n_fern, n_mush = 0, 0
    for k in range(260):
        if n_fern >= 26 and n_mush >= 18:
            break
        p = (rng.uniform(-50, -20), rng.uniform(-102, -58))
        if not G.point_in_polygon(p, poly) or not _base_ok(site, rules, p, 0.3, False):
            continue
        if not occ.clear_of(p[0], p[1], 0.35, 0.2):
            continue
        if n_fern < 26 and (k % 3 or n_mush >= 18):
            n_fern += 1
            it = Item(id=f'sm2_pine_understory_fern_{n_fern:02d}', category='fern', species='fern', x=p[0], z=p[1],
                      yaw=rng.uniform(0, TAU), height=rng.uniform(0.5, 0.8), radius=0.45, source='zone:west_pine_stand understory',
                      zone=zone_id)
        else:
            n_mush += 1
            it = Item(id=f'sm2_pine_understory_mushroom_{n_mush:02d}', category='mushroom', species='mushroom_cluster',
                      x=p[0], z=p[1], yaw=rng.uniform(0, TAU), height=rng.uniform(0.25, 0.45), radius=0.3,
                      source='zone:west_pine_stand understory', zone=zone_id, params={'glow': False})
        items.append(it)
        occ.add(p[0], p[1], 0.3, 'decor')
    site.notes.append(f'{zone_id}: {len(placed)} new trees/bushes around {len(seeds)} existing pine IDs, gaps '
                      f'{[(round(g[0], 1), round(g[1], 1), round(g[2], 1)) for g in gap_discs]}')
    return placed


def scatter_forest_wall(site, rules, items):
    """Dense pines behind the south palisade (visual frame, unreachable, no colliders)."""
    rng = random.Random(G.stable_seed('south_forest_wall'))
    line = G.Polyline(site.forest_line())
    poly = [(-58.0, -105.0), (-8.0, -103.0), (8.0, -103.0), (48.0, -105.0), (48.0, -125.0), (-58.0, -125.0)]
    pts = G.poisson_in_polygon(poly, 2.9, rng)
    placed = []
    for k, p in enumerate(pts):
        d, s, side = line.closest(p)
        if side > 0 or d < 1.9:
            continue
        if abs(p[0]) < 5.2 and p[1] > -121:
            continue       # future starter_to_south_loop corridor behind the closed gate
        bad = False
        for cl in rules.cliff_lines:
            dd, ss, sd = cl.closest(p)
            if sd <= 0 or dd < 1.2:
                bad = True
        dd, ss, sd = rules.toe_line.closest(p)
        if sd > 0 or dd < 1.2:
            bad = True
        if bad:
            continue
        species = 'pine_L' if rng.random() < 0.55 else 'pine_M'
        h = rng.uniform(10.5, 14.0) if species == 'pine_L' else rng.uniform(8.0, 10.0)
        from sm2_place import canopy_r_for, trunk_r_1m
        it = Item(id=f'sm2_forest_wall_pine_{k + 1:03d}', category='tree', species=species, x=p[0], z=p[1],
                  yaw=rng.uniform(0, TAU), height=h, radius=trunk_r_1m(species, h), canopy_r=canopy_r_for(species, h),
                  source='relief:south_forest_wall', zone='south_forest_wall')
        items.append(it)
        placed.append(it)
    return placed


def scatter_flowers(site, rules, occ, items):
    zone = site.zones['hunt_flowers']
    poly = [tuple(map(float, q)) for q in zone['polygon_xz']]
    rng = random.Random(G.stable_seed('hunt_flowers'))
    centres = G.poisson_in_polygon(poly, 3.3, rng)
    out = []
    for k, c in enumerate(centres):
        r = rng.uniform(0.6, 1.35)
        if not rules.path_ok(c, r, 1.5):
            continue
        if not rules.keepout_ok(c, r * 0.6, tall=False, ignore=('gate_apron',), ignore_prefix=('spawn:',)):
            continue
        colour = pick({'yellow': 0.45, 'white': 0.3, 'pink': 0.25}, rng)
        it = Item(id=f'sm2_hunt_flowers_{k + 1:02d}', category='flower', species='flower_patch', x=c[0], z=c[1],
                  yaw=rng.uniform(0, TAU), height=0.32, radius=r, source='zone:hunt_flowers', zone='hunt_flowers',
                  params={'colour': colour, 'count': rng.randint(6, 11), 'seed': rng.randrange(1 << 30)})
        items.append(it)
        out.append(it)
    return out


def scatter_reeds(site, rules, occ, items):
    rng = random.Random(G.stable_seed('stream_reeds'))
    out = []
    s = 1.5
    k = 0
    stations = []
    while s < site.stream.length - 0.8:
        s += rng.uniform(1.0, 2.2)
        for side in (-1, 1):
            if rng.random() < 0.62:
                stations.append((s + rng.uniform(-0.4, 0.4), side))
    for s, side in stations:
        if rng.random() < 0.18:
            continue      # open stretches between reed beds
        c = site.stream.point_at(s)
        nrm = G.left_normal(site.stream.tangent_at(s))
        hw = site.stream_width_at(s) / 2
        e = rng.uniform(0.08, 0.75)
        q = (c[0] + nrm[0] * side * (hw + e), c[1] + nrm[1] * side * (hw + e))
        if site.pool_e(q) < 0.1:
            continue
        a, l = site.bridge_local(q)
        if abs(a) < 6.8 and abs(l) < 6.0:
            continue      # never on the bridge approach
        if q[0] < -63.2 or not rules.path_ok(q, 0.4) or not rules.bluff_ok(q, 0.4, 0.2):
            continue
        if not occ.clear_of(q[0], q[1], 0.35, 0.1):
            continue
        kind = pick({'reeds': 0.6, 'fern': 0.25, 'blue_flowers': 0.15}, rng)
        k += 1
        it = Item(id=f'sm2_stream_reeds_{k:02d}', category='reed' if kind == 'reeds' else ('fern' if kind == 'fern' else 'flower'),
                  species={'reeds': 'reed_clump', 'fern': 'fern', 'blue_flowers': 'flower_patch'}[kind], x=q[0], z=q[1],
                  yaw=rng.uniform(0, TAU), base_y=site.ground_h(q), height=rng.uniform(0.9, 1.45) if kind == 'reeds' else 0.6,
                  radius=0.45, source='zone:stream_reeds', zone='stream_reeds',
                  params={'colour': 'blue', 'count': rng.randint(5, 9), 'seed': rng.randrange(1 << 30), 'bank_offset_m': round(e, 2)})
        items.append(it)
        occ.add(q[0], q[1], 0.35, 'decor')
        out.append(it)
    # A few around the west half of the pool (the east half meets the bluff and the falls).
    px, pz, pr = site.pool
    for j, ang in enumerate((115, 160, 205, 245)):
        a = math.radians(ang + rng.uniform(-8, 8))
        q = (px + (pr + 0.45) * math.cos(a), pz + (pr + 0.45) * math.sin(a))
        if not rules.path_ok(q, 0.4):
            continue
        it = Item(id=f'sm2_pool_reeds_{j + 1}', category='reed', species='reed_clump', x=q[0], z=q[1], yaw=a,
                  base_y=site.ground_h(q), height=rng.uniform(0.9, 1.3), radius=0.4, source='zone:stream_reeds',
                  zone='stream_reeds', params={'count': rng.randint(5, 8), 'seed': rng.randrange(1 << 30)})
        items.append(it)
        out.append(it)
    return out


def scatter_glade_edge(site, rules, occ, items):
    cx, cz = site.landmarks['windstone_circle']['center_xz']
    rng = random.Random(G.stable_seed('glade_edge'))
    out = []
    k = 0
    for t in range(400):
        if k >= 26:
            break
        a = rng.uniform(0, TAU)
        # Odd k = glowing mushrooms, kept outside the 11 m boss arena (layout arena_rule); flowers (0.3 m) stay inside.
        mushroom = (k + 1) % 2 == 1
        r = rng.uniform(11.5, 13.0) if mushroom else rng.uniform(8.3, 10.8)
        q = (cx + r * math.cos(a), cz + r * math.sin(a))
        if not rules.path_ok(q, 0.5) or not occ.clear_of(q[0], q[1], 0.45, 0.4):
            continue
        k += 1
        if mushroom:
            it = Item(id=f'sm2_glade_edge_mushrooms_{k:02d}', category='mushroom', species='mushroom_cluster', x=q[0], z=q[1],
                      yaw=a, height=rng.uniform(0.3, 0.55), radius=0.35, source='zone:glade_edge', zone='glade_edge',
                      params={'glow': True})
        else:
            it = Item(id=f'sm2_glade_edge_flowers_{k:02d}', category='flower', species='flower_patch', x=q[0], z=q[1],
                      yaw=a, height=0.3, radius=rng.uniform(0.6, 1.1), source='zone:glade_edge', zone='glade_edge',
                      params={'colour': pick({'white': 0.5, 'pink': 0.3, 'yellow': 0.2}, rng), 'count': rng.randint(6, 10),
                              'seed': rng.randrange(1 << 30)})
        items.append(it)
        occ.add(q[0], q[1], 0.4, 'decor')
        out.append(it)
    return out


def build_items(site: Site):
    """Run every placement pass in a fixed order; returns (items, rules, groups)."""
    items: list[Item] = []
    occ = G.SpatialHash(4.0)
    rules = Rules(site)
    existing = place_existing(site, items, occ)
    marks = place_named_landmarks(site, items, occ)
    altar = place_altar(site, items, occ)
    gate_stones = [existing['sunmeadow_stone_post_west_north'], existing['sunmeadow_stone_post_east_north']]
    stones = place_stone_circle(site, items, occ, existing['sunmeadow_windstone'], gate_stones, (altar.x, altar.z),
                                altar.radius)
    camp = place_camp(site, items, occ)
    setup_rules(site, rules, marks, altar)
    bluff_top = place_bluff_top(site, items)
    rocks = place_rocks(site, items, occ, rules)
    groups = {'existing': existing, 'landmarks': marks, 'stones': stones, 'altar': altar, 'camp': camp,
              'bluff_top': bluff_top, 'rocks': rocks}
    groups['west_meadow_grove'], _ = scatter_clusters(site, rules, occ, items, 'west_meadow_grove', (3, 6), (2, 3), 10.5, 4.6)
    groups['east_meadow_grove'], _ = scatter_clusters(site, rules, occ, items, 'east_meadow_grove', (3, 5), (1, 2), 9.0, 4.0)
    groups['east_oak_grove'], _ = scatter_clusters(site, rules, occ, items, 'east_oak_grove', (3, 6), (2, 3), 10.5, 4.8,
                                                   return_gap=1.5)
    groups['west_pine_stand'] = scatter_pine_stand(site, rules, occ, items, existing)
    groups['forest_wall'] = scatter_forest_wall(site, rules, items)
    groups['hunt_flowers'] = scatter_flowers(site, rules, occ, items)
    groups['stream_reeds'] = scatter_reeds(site, rules, occ, items)
    groups['glade_edge'] = scatter_glade_edge(site, rules, occ, items)
    ids = [it.id for it in items]
    if len(ids) != len(set(ids)):
        raise RuntimeError('duplicate item ids')
    return items, rules, groups
