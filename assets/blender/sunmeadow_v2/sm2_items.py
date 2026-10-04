"""Proxy meshes for placed items (trees, rocks, stones, camp kit, landmarks, decor) and render-only context."""
from __future__ import annotations

import math
import random

import sm2_geom as G
from sm2_geom import bl
from sm2_meshes import SceneAcc, disc_mesh
from sm2_site import Item, Site, cell_of

TAU = math.tau


def merge(*parts):
    v, f = [], []
    for pv, pf in parts:
        base = len(v)
        v += pv
        f += [tuple(i + base for i in ff) for ff in pf]
    return v, f


def moved(vf, dx=0.0, dy=0.0, dz=0.0, rot=0.0, scale=(1, 1, 1)):
    v, f = vf
    return G.transform(v, rot=rot, scale=scale, offset=(dx, dy, dz)), f


def ring_prism(rings, seg=8, phase=0.0, top=True, lean=(0.0, 0.0)):
    """Stack of horizontal rings: rings = [(z, rx, ry)], local frame; returns a closed-top prism."""
    v, f = [], []
    for (z, rx, ry) in rings:
        for k in range(seg):
            a = phase + TAU * k / seg
            v.append((rx * math.cos(a) + lean[0] * z, ry * math.sin(a) + lean[1] * z, z))
    for r in range(len(rings) - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            f.append((r * seg + k, r * seg + k2, (r + 1) * seg + k2, (r + 1) * seg + k))
    if top:
        c = len(v)
        z, rx, ry = rings[-1]
        v.append((lean[0] * z, lean[1] * z, z + 0.04))
        last = (len(rings) - 1) * seg
        for k in range(seg):
            f.append((c, last + k, last + (k + 1) % seg))
    return v, f


# ----------------------------------------------------------------------------
# Vegetation proxies
# ----------------------------------------------------------------------------

def tree_pine(it: Item, S: SceneAcc, layer='veg', cell=None):
    h, r1 = it.height, max(it.radius, 0.12)
    cr = it.canopy_r
    rng = random.Random(G.stable_seed(it.id))
    trunk = G.cone_mesh(r1 * 1.15, r1 * 0.45, -0.2, h * 0.9, 8, bottom=False, top=False)
    base = h * rng.uniform(0.16, 0.22)
    cones = []
    tiers = [(base, h * 0.62, cr), (h * 0.38, h * 0.86, cr * 0.72), (h * 0.62, h, cr * 0.46)]
    for z0, z1, rr in tiers:
        cones.append(G.cone_mesh(rr * rng.uniform(0.93, 1.07), 0.0, z0, z1, 10, bottom=True, phase=rng.uniform(0, 1)))
    cell = cell or it.cell
    S.add_local(cell, layer, 'trunk', trunk, it.x, it.z, it.yaw, it.base_y)
    S.add_local(cell, layer, 'pine', merge(*cones), it.x, it.z, it.yaw, it.base_y)


def tree_broadleaf(it: Item, S: SceneAcc, layer='veg', mat=None, cell=None):
    h, r1 = it.height, max(it.radius, 0.12)
    cr = it.canopy_r
    rng = random.Random(G.stable_seed(it.id))
    crown_base = h * 0.42
    trunk = G.cone_mesh(r1 * 1.2, r1 * 0.62, -0.2, h * 0.62, 8, bottom=False, top=False)
    main_r = cr * 0.82
    cz = h - main_r * 0.85
    parts = [moved(G.lumpy_sphere(2, main_r, rng.randrange(1 << 20), 0.16, 0.86), 0, 0, cz)]
    for k in range(rng.randint(2, 3)):
        a = rng.uniform(0, TAU)
        rr = cr * rng.uniform(0.45, 0.6)
        parts.append(moved(G.lumpy_sphere(1, rr, rng.randrange(1 << 20), 0.18, 0.85),
                           math.cos(a) * cr * 0.55, math.sin(a) * cr * 0.55, cz - main_r * rng.uniform(0.15, 0.4)))
    cell = cell or it.cell
    S.add_local(cell, layer, 'trunk', trunk, it.x, it.z, it.yaw, it.base_y)
    canopy_mat = mat or (it.species if it.species.startswith('broadleaf') else 'broadleaf_M')
    S.add_local(cell, layer, canopy_mat, merge(*parts), it.x, it.z, it.yaw, it.base_y)


def bush(it: Item, S: SceneAcc, layer='veg'):
    rng = random.Random(G.stable_seed(it.id))
    r = it.canopy_r
    parts = []
    for k in range(rng.randint(3, 5)):
        a = rng.uniform(0, TAU)
        d = r * rng.uniform(0.0, 0.5)
        rr = r * rng.uniform(0.45, 0.7)
        parts.append(moved(G.lumpy_sphere(1, rr, rng.randrange(1 << 20), 0.2, 0.85),
                           math.cos(a) * d, math.sin(a) * d, max(rr * 0.6, it.height - rr * 0.95)))
    if it.collider and it.collider_r > 0:
        # Ground lobe: the foliage must fill the collider at body height (0.2-1.0 m); pass-1 collider check found the
        # raised lobes left the existing bush collider 0.43 m wider than anything visible.
        rb = math.sqrt(it.collider_r ** 2 + 0.23) / 0.95 + 0.02
        parts.append(moved(G.icosphere(2), 0.0, 0.0, 0.6, scale=(rb, rb, rb * 0.85)))
    mat = 'bush_flowering' if it.species == 'bush_flowering' else 'bush'
    S.add_local(it.cell, layer, mat, merge(*parts), it.x, it.z, it.yaw, it.base_y)
    if it.species == 'bush_flowering':
        dots = []
        for k in range(10):
            a = rng.uniform(0, TAU)
            dots.append(moved(G.icosphere(0), math.cos(a) * r * 0.75, math.sin(a) * r * 0.75,
                              it.height * rng.uniform(0.55, 0.95), scale=(0.09, 0.09, 0.09)))
        S.add_local(it.cell, layer, 'flower_pink', merge(*dots), it.x, it.z, it.yaw, it.base_y)


def hero_oak(it: Item, S: SceneAcc):
    rng = random.Random(G.stable_seed(it.id))
    h = it.height
    trunk = ring_prism([(-0.3, 1.35, 1.25), (0.0, 1.3, 1.2), (0.6, 0.98, 0.95), (1.0, 0.86, 0.84), (3.0, 0.74, 0.72),
                        (5.5, 0.6, 0.58), (7.6, 0.44, 0.42)], seg=12, top=True)
    branches = []
    for k in range(5):
        a = TAU * k / 5 + rng.uniform(-0.3, 0.3)
        L = rng.uniform(3.2, 4.4)
        b = G.cone_mesh(0.34, 0.16, 0.0, L, 7, bottom=False)
        tilt = math.radians(rng.uniform(38, 55))
        bv = [(x, y * math.cos(tilt) - z * math.sin(tilt), y * math.sin(tilt) + z * math.cos(tilt)) for (x, y, z) in b[0]]
        branches.append(moved((bv, b[1]), 0, 0, rng.uniform(4.6, 6.4), rot=a))
    canopy = []
    for k in range(7):
        a = TAU * k / 7 + rng.uniform(-0.2, 0.2)
        d = 0.0 if k == 0 else it.canopy_r * rng.uniform(0.5, 0.62)
        rr = 3.9 if k == 0 else rng.uniform(2.6, 3.3)
        zc = (h - 3.4) if k == 0 else rng.uniform(8.3, 10.3)
        canopy.append(moved(G.lumpy_sphere(2, rr, rng.randrange(1 << 20), 0.15, 0.82), math.cos(a) * d, math.sin(a) * d, zc))
    S.add_local(it.cell, 'veg', 'trunk_hero', merge(trunk, *branches), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'veg', 'hero_canopy', merge(*canopy), it.x, it.z, it.yaw)


def ancient_pine(it: Item, S: SceneAcc):
    rng = random.Random(G.stable_seed(it.id))
    h = it.height
    trunk = ring_prism([(-0.3, 0.95, 0.95), (0.0, 0.9, 0.9), (1.0, 0.62, 0.62), (6.0, 0.48, 0.48), (12.0, 0.33, 0.33),
                        (h - 1.0, 0.16, 0.16)], seg=10)
    cones = []
    for k, (z0, z1, rr) in enumerate([(4.2, 9.6, 4.4), (7.6, 12.6, 3.5), (10.4, 15.0, 2.6), (12.8, 16.8, 1.8),
                                      (15.0, h, 1.0)]):
        cones.append(G.cone_mesh(rr * rng.uniform(0.95, 1.05), 0.0, z0, z1, 12, bottom=True, phase=rng.uniform(0, 1)))
    S.add_local(it.cell, 'veg', 'trunk_hero', trunk, it.x, it.z, it.yaw)
    S.add_local(it.cell, 'veg', 'pine_ancient', merge(*cones), it.x, it.z, it.yaw)


def flower_patch(it: Item, S: SceneAcc):
    rng = random.Random(it.params.get('seed', G.stable_seed(it.id)))
    parts = []
    for k in range(it.params.get('count', 9)):
        a = rng.uniform(0, TAU)
        d = it.radius * math.sqrt(rng.random())
        hh = rng.uniform(0.2, 0.36)
        parts.append(moved(G.cone_mesh(0.07, 0.11, 0.0, hh, 5, bottom=False, top=True), math.cos(a) * d, math.sin(a) * d, -0.02))
    S.add_local(it.cell, 'veg', f"flower_{it.params.get('colour', 'yellow')}", merge(*parts), it.x, it.z, it.yaw, it.base_y)


def reed_clump(it: Item, S: SceneAcc):
    rng = random.Random(it.params.get('seed', G.stable_seed(it.id)))
    parts = []
    for k in range(it.params.get('count', 7)):
        a = rng.uniform(0, TAU)
        d = 0.32 * math.sqrt(rng.random())
        hh = it.height * rng.uniform(0.75, 1.1)
        c = G.cone_mesh(0.035, 0.0, -0.05, hh, 5, bottom=False)
        lean = rng.uniform(-0.12, 0.12)
        cv = [(x + lean * z, y, z) for (x, y, z) in c[0]]
        parts.append(moved((cv, c[1]), math.cos(a) * d, math.sin(a) * d, 0, rot=a))
    S.add_local(it.cell, 'veg', 'reed', merge(*parts), it.x, it.z, it.yaw, it.base_y)


def fern(it: Item, S: SceneAcc):
    rng = random.Random(G.stable_seed(it.id))
    v, f = [], []
    for k in range(6):
        a = TAU * k / 6 + rng.uniform(-0.2, 0.2)
        L = it.height * rng.uniform(0.9, 1.25)
        tip = (math.cos(a) * L, math.sin(a) * L, it.height * 0.55)
        side = (-math.sin(a) * 0.12, math.cos(a) * 0.12)
        base = len(v)
        v += [(0, 0, 0.02), (tip[0] * 0.45 + side[0], tip[1] * 0.45 + side[1], it.height * 0.45), tip,
              (tip[0] * 0.45 - side[0], tip[1] * 0.45 - side[1], it.height * 0.45)]
        f += [(base, base + 1, base + 2, base + 3), (base, base + 3, base + 2, base + 1)]
    S.add_local(it.cell, 'veg', 'fern', (v, f), it.x, it.z, it.yaw, it.base_y)


def mushrooms(it: Item, S: SceneAcc):
    rng = random.Random(G.stable_seed(it.id))
    stems, caps = [], []
    for k in range(rng.randint(3, 5)):
        a = rng.uniform(0, TAU)
        d = rng.uniform(0.0, 0.28)
        hh = it.height * rng.uniform(0.5, 1.0)
        r = rng.uniform(0.07, 0.15)
        stems.append(moved(G.cone_mesh(r * 0.35, r * 0.3, 0.0, hh, 6, bottom=False, top=False), math.cos(a) * d, math.sin(a) * d))
        caps.append(moved(G.cone_mesh(r, 0.0, hh, hh + r * 0.8, 8, bottom=True), math.cos(a) * d, math.sin(a) * d))
    S.add_local(it.cell, 'veg', 'mushroom_stem', merge(*stems), it.x, it.z, it.yaw, it.base_y)
    S.add_local(it.cell, 'veg', 'mushroom_glow' if it.params.get('glow') else 'mushroom_cap', merge(*caps), it.x, it.z,
                it.yaw, it.base_y)


# ----------------------------------------------------------------------------
# Rocks and stones
# ----------------------------------------------------------------------------

def boulder(it: Item, S: SceneAcc):
    sx, sy, sz = it.params['size']
    seed = it.params.get('seed', G.stable_seed(it.id))
    v, f = G.lumpy_sphere(2 if max(sx, sy) > 1.4 else 1, 0.5, seed, 0.22, 1.0)
    v = [(x * sx, y * sy, z * sz) for (x, y, z) in v]
    mat = {'painted_rock': 'rock_painted', 'stream_stone': 'rock_stream'}.get(it.species, 'rock_boulder')
    layer = 'rock'
    S.add_local(it.cell, layer, mat, (v, f), it.x, it.z, it.yaw, it.base_y + sz * 0.12)


def standing_stone(it: Item, S: SceneAcc, mat='stone_circle'):
    w, d = it.params.get('w', 1.1), it.params.get('d', 0.75)
    h = it.height
    lean = it.params.get('lean', 0.0)
    rng = random.Random(G.stable_seed(it.id))
    rings = [(-0.4, w * 0.56, d * 0.56), (0.0, w * 0.55, d * 0.55), (h * 0.35, w * 0.5, d * 0.52),
             (h * 0.75, w * 0.42, d * 0.45), (h - 0.18, w * 0.33, d * 0.38)]
    rings = [(z, rx * rng.uniform(0.95, 1.05), ry * rng.uniform(0.95, 1.05)) for z, rx, ry in rings]
    S.add_local(it.cell, 'landmark', mat, ring_prism(rings, seg=8, phase=math.pi / 8, lean=(lean, 0.0)), it.x, it.z,
                it.yaw, it.base_y)


def stone_post(it: Item, S: SceneAcc):
    s = it.params.get('scale', 1.0)
    h = it.height
    parts = [G.box_mesh(1.0 * s, 1.0 * s, -0.3, 0.3), G.box_mesh(0.74 * s, 0.74 * s, 0.3, h - 0.32, taper=0.9),
             G.box_mesh(0.92 * s, 0.92 * s, h - 0.32, h - 0.14), G.box_mesh(0.62 * s, 0.62 * s, h - 0.14, h)]
    S.add_local(it.cell, 'landmark', 'stone_post', merge(*parts), it.x, it.z, it.yaw, it.base_y)


def windmark(it: Item, S: SceneAcc):
    rng = random.Random(G.stable_seed(it.id))
    rings = []
    for k, f in enumerate((0.0, 0.18, 0.4, 0.62, 0.82, 1.0)):
        waist = 1.0 - 0.28 * math.sin(math.pi * f)
        rings.append((f * 1.9 - (0.3 if k == 0 else 0.0), 0.42 * waist * (1 - 0.35 * f), 0.3 * waist * (1 - 0.2 * f)))
    v, f = ring_prism(rings, seg=8)
    tw = []
    for (x, y, z) in v:
        a = 0.45 * max(0.0, z) / 1.9
        tw.append((x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a), z))
    S.add_local(it.cell, 'landmark', 'windmark_stone', (tw, f), it.x, it.z, it.yaw)
    pole = moved(G.cone_mesh(0.05, 0.04, 0.0, 2.75, 6, bottom=False), 0.55, 0.0)
    S.add_local(it.cell, 'landmark', 'timber', pole, it.x, it.z, it.yaw)
    for k, (mat, z0) in enumerate((('cloth_red', 2.6), ('cloth_yellow', 2.25))):
        L = 1.0 - 0.15 * k
        sv = [(0.55, 0.0, z0), (0.55, 0.0, z0 - 0.22), (0.55 + L, 0.12, z0 - 0.3), (0.55 + L, 0.12, z0 - 0.12)]
        S.add_local(it.cell, 'landmark', mat, (sv, [(0, 1, 2, 3), (0, 3, 2, 1)]), it.x, it.z, it.yaw)


# ----------------------------------------------------------------------------
# Camp kit and props
# ----------------------------------------------------------------------------

def wheel(r, t):
    v, f = G.cone_mesh(r, r, -t / 2, t / 2, 12, bottom=True, top=True)
    # rotate so the axle runs along local u (x)
    return [(z, y, x) for (x, y, z) in v], [tuple(reversed(ff)) for ff in f]


def cart(it: Item, S: SceneAcc, broken=False):
    """Cart: body + side boards + two wheels + shafts, all inside the collider (3.0 x 1.6 m; broken 2.4 x 1.6)."""
    total = 3.0 if not broken else 2.4
    W = 1.3
    body_l = total * 0.7
    v0 = -total / 2
    parts_t = [moved(G.box_mesh(W, body_l, 0.55, 0.72), 0, v0 + body_l / 2)]
    for side in (-1, 1):
        parts_t.append(moved(G.box_mesh(0.07, body_l, 0.72, 1.55 if not broken else 1.1), side * (W / 2 - 0.035), v0 + body_l / 2))
    parts_t.append(moved(G.box_mesh(W, 0.07, 0.72, 1.45 if not broken else 1.0), 0, v0 + 0.035))
    shafts = [moved(G.box_mesh(0.07, total - body_l, 0.44, 0.52), side * 0.42, v0 + body_l + (total - body_l) / 2) for side in (-1, 1)]
    wheels = [moved(wheel(0.58, 0.11), side * (W / 2 + 0.08), v0 + body_l * 0.45, 0.58) for side in (-1, 1)]
    if broken:
        # Collapsed on its axle: the bed rests on the ground (bed 0.05-0.3 m, boards to 0.95 m), a wheel lies flat and
        # spilled cargo fills the shaft end, so the 2.4 x 1.6 m collider sits on visible wood at body height
        # (pass-1 collider check: the raised bed left 1.8 m of the footprint visually empty at 0.2 m).
        parts_t = [moved(G.box_mesh(W, body_l, 0.05, 0.3), 0, v0 + body_l / 2)]
        for side in (-1, 1):
            parts_t.append(moved(G.box_mesh(0.07, body_l, 0.3, 0.95 if side > 0 else 0.62), side * (W / 2 - 0.035), v0 + body_l / 2))
        parts_t.append(moved(G.box_mesh(W, 0.07, 0.3, 0.85), 0, v0 + 0.035))
        parts_t = [([(x, y, z + 0.12 * x) for (x, y, z) in v], f) for v, f in parts_t]
        shafts = [moved(G.box_mesh(0.07, total - body_l, 0.0, 0.1), side * 0.42, v0 + body_l + (total - body_l) / 2) for side in (-1, 1)]
        wheels = [moved(wheel(0.58, 0.11), W / 2 + 0.08, v0 + body_l * 0.45, 0.58),
                  moved(G.cone_mesh(0.58, 0.58, 0.0, 0.11, 12), -W / 2 + 0.1, v0 + body_l + 0.15)]
        rng = random.Random(G.stable_seed(it.id))
        cargo = [moved(G.box_mesh(0.62, 0.62, 0.0, 0.55), 0.25, v0 + body_l + 0.38, 0, rot=0.3),
                 moved(G.lumpy_sphere(1, 0.36, rng.randrange(1 << 20), 0.15, 0.75), -0.3, v0 + body_l + 0.42, 0.24),
                 moved(G.lumpy_sphere(1, 0.32, rng.randrange(1 << 20), 0.15, 0.75), -0.25, v0 + 0.55, 0.5)]
        # The existing collider is 2.4 m along local X (compact v1 collider_size [2.4, 1.4, 1.6]); this builder lays
        # the cart along local y, so turn the broken cart 90 degrees to sit inside its server collider.
        r90 = lambda m: ([(y, -x, z) for (x, y, z) in m[0]], m[1])   # noqa: E731  proper rotation, winding kept
        S.add_local(it.cell, 'prop', 'crate', r90(cargo[0]), it.x, it.z, it.yaw)
        S.add_local(it.cell, 'prop', 'cloth', r90(merge(cargo[1], cargo[2])), it.x, it.z, it.yaw)
        S.add_local(it.cell, 'prop', 'timber', r90(merge(*parts_t, *shafts)), it.x, it.z, it.yaw)
        S.add_local(it.cell, 'prop', 'timber_dark', r90(merge(*wheels)), it.x, it.z, it.yaw)
        return
    S.add_local(it.cell, 'prop', 'timber', merge(*parts_t, *shafts), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'prop', 'timber_dark', merge(*wheels), it.x, it.z, it.yaw)
    if not broken:
        rng = random.Random(G.stable_seed(it.id))
        load = [moved(G.lumpy_sphere(1, 0.34, rng.randrange(1 << 20), 0.15, 0.8), rng.uniform(-0.3, 0.3),
                      v0 + rng.uniform(0.4, body_l - 0.4), 1.0) for k in range(3)]
        S.add_local(it.cell, 'prop', 'cloth', merge(*load), it.x, it.z, it.yaw)


def haystack(it: Item, S: SceneAcc):
    rings = [(-0.1, 1.2, 1.2), (0.0, 1.2, 1.2), (0.85, 1.15, 1.15), (1.25, 0.85, 0.85), (1.5, 0.45, 0.45), (1.6, 0.12, 0.12)]
    S.add_local(it.cell, 'prop', 'hay', ring_prism(rings, seg=14), it.x, it.z, it.yaw)


def tent(it: Item, S: SceneAcc):
    W, L, H = 3.0, 3.0, 2.5
    v = [(-W / 2, -L / 2, 0.0), (W / 2, -L / 2, 0.0), (W / 2, L / 2, 0.0), (-W / 2, L / 2, 0.0), (0, -L / 2, H), (0, L / 2, H)]
    f = [(0, 4, 5, 3), (1, 2, 5, 4), (0, 1, 4), (2, 3, 5)]
    S.add_local(it.cell, 'prop', 'cloth', (v, f), it.x, it.z, it.yaw)
    poles = [moved(G.cone_mesh(0.05, 0.05, 0, H + 0.25, 6, bottom=False), 0, s * (L / 2 + 0.05), 0) for s in (-1, 1)]
    ridge = moved(G.box_mesh(0.07, L + 0.3, H - 0.04, H + 0.04), 0, 0, 0)
    S.add_local(it.cell, 'prop', 'timber', merge(*poles, ridge), it.x, it.z, it.yaw)


def campfire(it: Item, S: SceneAcc):
    rng = random.Random(G.stable_seed(it.id))
    stones = []
    # Ring stones 0.27 m tall reaching the 0.7 m collider edge (pass-1: 0.155 m stones sat under the 0.2 m probe).
    for k in range(10):
        a = TAU * k / 10
        stones.append(moved(G.lumpy_sphere(1, 0.19, rng.randrange(1 << 20), 0.15, 0.9), math.cos(a) * 0.53, math.sin(a) * 0.53, 0.1))
    logs = []
    for k in range(4):
        a = TAU * k / 4 + 0.4
        lg = G.cone_mesh(0.07, 0.07, -0.4, 0.4, 6)
        lv = [(z, y, x) for (x, y, z) in lg[0]]
        lf = [tuple(reversed(ff)) for ff in lg[1]]
        logs.append(moved((lv, lf), math.cos(a) * 0.1, math.sin(a) * 0.1, 0.12, rot=a))
    S.add_local(it.cell, 'prop', 'stone_dark', merge(*stones), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'prop', 'timber_dark', merge(*logs), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'prop', 'fire', G.cone_mesh(0.26, 0.0, 0.1, 0.78, 7), it.x, it.z, it.yaw)


def crate_stack(it: Item, S: SceneAcc):
    parts = [moved(G.box_mesh(0.9, 0.9, 0.0, 0.9), -0.5, 0.0), moved(G.box_mesh(0.85, 0.85, 0.0, 0.85), 0.48, 0.05, 0, rot=0.12),
             moved(G.box_mesh(0.8, 0.8, 0.9, 1.7), -0.45, 0.02, 0, rot=-0.1)]
    S.add_local(it.cell, 'prop', 'crate', merge(*parts), it.x, it.z, it.yaw)


def weapon_rack(it: Item, S: SceneAcc):
    parts = [moved(G.box_mesh(0.1, 0.1, 0.0, 1.7), s * 0.78, 0.0) for s in (-1, 1)]
    parts += [G.box_mesh(1.7, 0.08, 1.38, 1.46), G.box_mesh(1.7, 0.08, 0.5, 0.58)]
    # Base sledge + back boards so the 1.7 x 0.55 m collider sits on visible timber at 0.2 m and 1.0 m (pass-1 check).
    parts += [G.box_mesh(1.7, 0.5, 0.0, 0.26), G.box_mesh(1.62, 0.06, 0.62, 1.36)]
    weapons = []
    for k in range(4):
        x = -0.55 + 0.37 * k
        weapons.append(moved(G.cone_mesh(0.025, 0.02, 0.0, 1.95, 5, bottom=False), x, 0.12, 0.0))
        weapons.append(moved(G.cone_mesh(0.05, 0.0, 1.95, 2.2, 4, bottom=False), x, 0.12, 0.0))
    S.add_local(it.cell, 'prop', 'timber', merge(*parts), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'prop', 'iron', merge(*weapons), it.x, it.z, it.yaw)


def palisade_item(it: Item, S: SceneAcc):
    from sm2_relief import palisade_run
    palisade_run(S, it.params['a'], it.params['b'], it.params['log_h'], G.stable_seed(it.id), layer='prop', rails_side=1)


# ----------------------------------------------------------------------------
# Landmarks
# ----------------------------------------------------------------------------

def signpost(it: Item, S: SceneAcc):
    parts = [G.box_mesh(0.15, 0.15, -0.2, 2.7), moved(G.box_mesh(0.24, 0.24, 2.7, 2.82), 0, 0, 0)]
    boards = [moved(G.box_mesh(1.35, 0.05, 2.12, 2.42), 0.55, 0.09, 0, rot=0.0),
              moved(G.box_mesh(1.25, 0.05, 1.72, 2.0), -0.5, 0.09, 0, rot=0.35)]
    S.add_local(it.cell, 'landmark', 'timber', merge(*parts), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'landmark', 'timber_light', merge(*boards), it.x, it.z, it.yaw)


def watchtower(it: Item, S: SceneAcc):
    o = it.params['post_offset']
    py = it.params['platform_y']
    corners = [(-o, -o), (o, -o), (o, o), (-o, o)]
    posts = [moved(G.cone_mesh(0.17, 0.15, -0.2, 7.0, 8, bottom=False), x, y) for x, y in corners]
    braces = []
    for k in range(4):
        (x0, y0), (x1, y1) = corners[k], corners[(k + 1) % 4]
        L = math.hypot(x1 - x0, y1 - y0)
        ang = math.atan2(y1 - y0, x1 - x0)
        for (za, zb) in ((0.5, py - 0.3), (py - 0.3, 0.5)):
            dz = zb - za
            Ld = math.hypot(L, dz)
            b = G.box_mesh(Ld, 0.08, -0.05, 0.05)
            tilt = math.atan2(dz, L)
            bv = [(x * math.cos(tilt), y, x * math.sin(tilt) + z) for (x, y, z) in b[0]]
            braces.append(moved((bv, b[1]), (x0 + x1) / 2, (y0 + y1) / 2, (za + zb) / 2, rot=ang))
    platform = G.box_mesh(2 * o + 0.6, 2 * o + 0.6, py - 0.2, py)
    rails = []
    for k in range(4):
        (x0, y0), (x1, y1) = corners[k], corners[(k + 1) % 4]
        ang = math.atan2(y1 - y0, x1 - x0)
        rails.append(moved(G.box_mesh(2 * o + 0.5, 0.08, py + 0.95, py + 1.05), (x0 + x1) / 2 * 1.08, (y0 + y1) / 2 * 1.08, 0, rot=ang))
    roof = ([(-o - 0.6, -o - 0.6, 6.9), (o + 0.6, -o - 0.6, 6.9), (o + 0.6, o + 0.6, 6.9), (-o - 0.6, o + 0.6, 6.9),
             (0.0, 0.0, 8.3)], [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 3, 2, 1)])
    ladder = [moved(G.box_mesh(0.07, 0.07, 0.0, py), o + 0.35, s * 0.3) for s in (-1, 1)]
    ladder += [moved(G.box_mesh(0.07, 0.6, z - 0.03, z + 0.03), o + 0.35, 0.0) for z in [0.4 + 0.42 * k for k in range(10)]]
    S.add_local(it.cell, 'landmark', 'timber', merge(*posts, *braces, *ladder), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'landmark', 'timber_light', merge(platform, *rails), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'landmark', 'roof', roof, it.x, it.z, it.yaw)


def altar(it: Item, S: SceneAcc):
    """Flush carved platform (walkable, no collider) with the dormant portal ring inlaid in it (VFX lane later) and the
    central altar block, which stays inside its collider (block_radius_m) so no visible stone sits outside it."""
    r = it.radius
    rb = float(it.params.get('block_radius_m', 0.8))
    top = float(it.params.get('platform_top_y', 0.04))
    plate = G.cone_mesh(r, r, -0.06, top, 32, bottom=False)
    seg, ri, ro, y = 32, 1.35, 1.65, top + 0.006
    v, f = [], []
    for k in range(seg):
        a = TAU * k / seg
        v += [(ri * math.cos(a), ri * math.sin(a), y), (ro * math.cos(a), ro * math.sin(a), y)]
        k2 = (k + 1) % seg
        f.append((2 * k, 2 * k + 1, 2 * k2 + 1, 2 * k2))
    block = merge(G.cone_mesh(rb - 0.04, rb - 0.13, top - 0.02, it.height - 0.12, 12, bottom=False, top=False),
                  G.cone_mesh(rb - 0.06, rb - 0.06, it.height - 0.12, it.height, 12))
    S.add_local(it.cell, 'landmark', 'stone_light', plate, it.x, it.z, it.yaw)
    S.add_local(it.cell, 'landmark', 'stone_circle', (v, f), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'landmark', 'stone_carved', block, it.x, it.z, it.yaw)


def shrine(it: Item, S: SceneAcc):
    parts = [G.box_mesh(1.0, 0.8, -0.1, 0.25), G.box_mesh(0.78, 0.6, 0.25, 1.05), G.box_mesh(1.1, 0.9, 1.05, 1.18),
             moved(G.box_mesh(0.5, 0.4, 1.18, 1.45, taper=0.6), 0, 0)]
    S.add_local(it.cell, 'landmark', 'stone_carved', merge(*parts), it.x, it.z, it.yaw)


def chest(it: Item, S: SceneAcc):
    body = G.box_mesh(0.95, 0.62, 0.0, 0.48)
    lid = G.box_mesh(0.99, 0.66, 0.48, 0.7, taper=0.9)
    bands = [moved(G.box_mesh(0.06, 0.68, 0.0, 0.72), x, 0) for x in (-0.3, 0.3)]
    S.add_local(it.cell, 'landmark', 'chest', merge(body, lid), it.x, it.z, it.yaw)
    S.add_local(it.cell, 'landmark', 'iron', merge(*bands), it.x, it.z, it.yaw)


DISPATCH = {
    'pine_L': tree_pine, 'pine_M': tree_pine, 'broadleaf_L': tree_broadleaf, 'broadleaf_M': tree_broadleaf,
    'broadleaf_S': tree_broadleaf, 'bush': bush, 'bush_flowering': bush, 'bush_existing': bush,
    'hero_oak': hero_oak, 'ancient_pine': ancient_pine, 'flower_patch': flower_patch, 'reed_clump': reed_clump,
    'fern': fern, 'mushroom_cluster': mushrooms, 'boulder': boulder, 'painted_rock': boulder, 'stream_stone': boulder,
    'standing_stone': standing_stone, 'gate_stone': lambda it, S: standing_stone(it, S, 'stone_circle'),
    'windstone': lambda it, S: standing_stone(it, S, 'windstone'), 'stone_post': stone_post, 'windmark': windmark,
    'cart': cart, 'broken_cart': lambda it, S: cart(it, S, broken=True), 'haystack': haystack, 'tent': tent,
    'campfire': campfire, 'crate_stack': crate_stack, 'weapon_rack': weapon_rack, 'palisade_run': palisade_item,
    'signpost': signpost, 'watchtower': watchtower, 'altar': altar, 'shrine': shrine, 'chest': chest,
}


def build_items_meshes(items, S: SceneAcc):
    missing = set()
    for it in items:
        fn = DISPATCH.get(it.species)
        if fn is None:
            missing.add(it.species)
            continue
        if it.zone == 'bluff_top' and it.category == 'tree':
            (tree_pine if it.species.startswith('pine') else tree_broadleaf)(it, S)
            continue
        fn(it, S)
    if missing:
        raise RuntimeError(f'no proxy builder for {sorted(missing)}')


# ----------------------------------------------------------------------------
# Render-only context, witnesses, annotations
# ----------------------------------------------------------------------------

def extrude_polygon(poly_xz, y0, y1):
    """Closed prism (Blender space) from a Babylon convex/simple polygon."""
    pts = G.ccw(poly_xz)
    n = len(pts)
    v = [bl(x, z, y0) for x, z in pts] + [bl(x, z, y1) for x, z in pts]
    f = []
    for k in range(n):
        k2 = (k + 1) % n
        f.append((k, k2, n + k2, n + k))
    tris = G.ear_clip(pts)
    f += [(n + a, n + b, n + c) for a, b, c in tris]
    f += [(c, b, a) for a, b, c in tris]
    return v, f


def build_context(site: Site, S: SceneAcc):
    # City gate geometry from the live city traversal blockers (render-only; owned by the city lane).
    for b in site.city_blockers:
        if b['kind'] == 'water_hazard':
            continue
        y0, y1 = max(-0.5, b['y_min']), min(b['y_max'], 22.0)
        v, f = extrude_polygon([tuple(q) for q in b['polygon_xz']], y0, y1)
        S.add('none', 'context', 'context_city', v, f)
    for (x0, x1, z0, z1) in site.canal_rects():
        v, f = extrude_polygon([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], -0.9, -0.45)
        S.add('none', 'context', 'context_water', v, f)
        for xe in (x0 - 0.35, x1):
            v, f = extrude_polygon([(xe, z0 - 0.35), (xe + 0.35, z0 - 0.35), (xe + 0.35, z1), (xe, z1)], -0.9, 0.12)
            S.add('none', 'context', 'context_city', v, f)
        v, f = extrude_polygon([(x0 - 0.35, z0 - 0.35), (x1 + 0.35, z0 - 0.35), (x1 + 0.35, z0), (x0 - 0.35, z0)], -0.9, 0.12)
        S.add('none', 'context', 'context_city', v, f)
    for sx in (-1, 1):   # arrival ramps (live city surfaces), shown as paving strips
        x0, x1 = (6.85, 13.35) if sx > 0 else (-13.35, -6.85)
        v, f = extrude_polygon([(x0, 8.0), (x1, 8.0), (x1, 60.0), (x0, 60.0)], -0.05, 0.022)
        S.add('none', 'context', 'context_paving', v, f)
    # Ground beyond the art cells (rings of flat ground) + the stream outlet patch beyond x = -64.
    rects = [(-230, -6.75, 24, 170), (6.75, 230, 24, 170), (-6.75, 6.75, 60, 170), (-230, 230, -260, -128), (-230, -86, -128, 24), (-86, -64, -128, -70), (-86, -64, -50, 24),
             (64, 230, -128, 24)]
    for (x0, x1, z0, z1) in rects:
        v = [bl(x0, z0, -0.02), bl(x1, z0, -0.02), bl(x1, z1, -0.02), bl(x0, z1, -0.02)]
        S.add('none', 'context', 'context_ground', v, [(0, 1, 2, 3)])
    xs = [-86 + 0.5 * i for i in range(45)]
    zs = [-70 + 0.5 * j for j in range(41)]
    verts = [bl(x, z, site.ground_h((x, z), extended=True)) for z in zs for x in xs]
    faces = [(j * 45 + i, j * 45 + i + 1, (j + 1) * 45 + i + 1, (j + 1) * 45 + i) for j in range(40) for i in range(44)]
    S.add('none', 'context', 'context_ground', verts, faces)
    # Forest belt south of the art cells (render-only depth behind the south wall).
    rng = random.Random(G.stable_seed('context_forest'))
    pts = G.poisson_in_polygon([(-60, -126), (52, -126), (52, -160), (-60, -160)], 3.4, rng)
    for k, p in enumerate(pts):
        h = rng.uniform(9, 14)
        it = Item(id=f'ctx_pine_{k}', category='tree', species='pine_L', x=p[0], z=p[1], yaw=rng.uniform(0, TAU), height=h,
                  radius=0.3, canopy_r=0.23 * h)
        tree_pine(it, S, layer='context', cell='none')


def witness_mesh():
    body = G.cone_mesh(0.2, 0.17, 0.0, 1.46, 10)
    head = moved(G.icosphere(1), 0, 0, 1.64, scale=(0.15, 0.15, 0.16))
    arms = moved(G.box_mesh(0.62, 0.12, 1.15, 1.32), 0, 0, 0)
    return merge(body, head, arms)


def build_annotations(site: Site, S: SceneAcc):
    for (enemy, x, z, cl) in site.spawns:
        S.add_local('none', 'annotation', 'mark_spawn', disc_mesh(0.7, 10), x, z, 0.0, 0.05)
    for (x, z, br, row, enemy) in site.monster_homes:
        S.add_local('none', 'annotation', 'mark_home', disc_mesh(0.45, 8), x, z, 0.0, 0.06)
    for pid, (x, z) in site.pois.items():
        S.add_local('none', 'annotation', 'mark_poi', disc_mesh(0.8, 12), x, z, 0.0, 0.07)
