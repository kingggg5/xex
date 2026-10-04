"""R5 tree belts, flowering groves, plaza planters, lamps and benches."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import citykit as ck  # noqa: E402
import buildings as bld  # noqa: E402


def _root(col):
    root = bpy.data.objects.new('kit_city_vegetation', None)
    root.empty_display_type = 'PLAIN_AXES'
    col.objects.link(root)
    return root


def _material_library():
    palette = {
        'foliage_deep': (0.105, 0.26, 0.075),
        'foliage_mid': (0.16, 0.36, 0.09),
        'foliage_sun': (0.29, 0.48, 0.11),
        'foliage_blossom': (0.72, 0.30, 0.48),
        'foliage_autumn': (0.69, 0.35, 0.10),
        'flower_ivory': (0.92, 0.86, 0.67),
        'flower_lilac': (0.46, 0.25, 0.72),
        'flower_gold': (0.94, 0.60, 0.12),
    }
    for name, color in palette.items():
        if name not in ck.MATERIALS:
            ck.define_material(name, tile=1.0, color=color, rough=0.88)


def _attach(obj, root, seed=0, *, tint=(1.0, 1.0, 1.0), bevel=0.0):
    if bevel:
        ck.bevel(obj, bevel, segments=2, angle_deg=35)
    ck.uv_box(obj)
    ck.vertex_paint(obj, tint=tint, seed=seed, ground_z=0.02, cavity=0.20, edge=0.12, jitter=0.04)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _box(root, name, center, size, mat, seed=0, bevel=0.035, rot_z=0.0):
    return _attach(ck.box(name, center, size, mat, rot_z=rot_z), root, seed, bevel=bevel)


def _beam(root, name, start, end, width, mat, depth=None, seed=0):
    return bld._beam(root, name, start, end, width, mat, depth=depth, seed=seed)


def _lathe(root, name, profile, mat, center=(0, 0, 0), segments=16, seed=0):
    obj = ck.lathe(name, profile, segments=segments, material=mat, center=center)
    return _attach(obj, root, seed)


def _smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _ground_height(x, y):
    s = (x - 30.0) * 0.57 + (y - 25.0) * 0.82
    region = _smoothstep(24.0, 40.0, x) * _smoothstep(14.0, 32.0, y)
    plaza = _smoothstep(44.0, 54.0, math.hypot(x, y))
    ridge = 8.0 * _smoothstep(20.0, 95.0, s) * region * plaza
    windmill_hill = 8.0 * (1.0 - _smoothstep(11.0, 26.0, math.hypot(x - 94.0, y - 108.0)))
    return max(ridge, windmill_hill)


def _tree(root, x, y, kind, size, seed):
    rng = random.Random(seed)
    z = _ground_height(x, y)
    trunk_h = size * rng.uniform(1.4, 1.8)
    trunk_r = size * 0.115
    _lathe(root, f'{kind} tree trunk', [(trunk_r * 0.72, 0), (trunk_r, trunk_h * 0.22),
            (trunk_r * 0.75, trunk_h * 0.72), (trunk_r * 0.42, trunk_h)],
           'timber_dark', (x, y, z), 10, seed)
    branch_mat = 'timber_dark'
    crown_z = z + trunk_h * 0.84
    for i in range(4):
        a = i * math.tau / 4 + rng.uniform(-0.18, 0.18)
        length = size * rng.uniform(0.50, 0.88)
        _beam(root, f'{kind} tree branch', (x, y, z + trunk_h * 0.48),
              (x + math.cos(a) * length, y + math.sin(a) * length, crown_z + size * 0.35),
              max(0.16, trunk_r * 1.15), branch_mat, seed=seed + i)
    colors = {
        'oak': ('foliage_deep', 'foliage_mid', 'foliage_sun'),
        'blossom': ('foliage_mid', 'foliage_blossom', 'flower_ivory'),
        'autumn': ('foliage_mid', 'foliage_autumn', 'flower_gold'),
        'pine': ('foliage_deep', 'foliage_mid', 'foliage_deep'),
    }[kind]
    if kind == 'pine':
        for tier in range(5):
            tier_z = z + trunk_h * 0.62 + tier * size * 0.68
            rr = size * (0.85 - tier * 0.12)
            _lathe(root, f'pine tier {tier + 1}', [(rr, 0), (rr * 0.68, size * 0.90), (0, size * 1.55)],
                   colors[tier % len(colors)], (x, y, tier_z), 9, seed + tier)
    else:
        for i in range(8):
            a = i * 2.399963 + rng.uniform(-0.28, 0.28)
            radial = size * rng.uniform(0.12, 0.64)
            cz = crown_z + size * rng.uniform(0.0, 1.1)
            radius = size * rng.uniform(0.45, 0.67)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius,
                location=(x + math.cos(a) * radial, y + math.sin(a) * radial, cz))
            leaf = bpy.context.object
            leaf.name = f'{kind} tree canopy cluster'
            leaf.scale = (1.0, rng.uniform(0.78, 1.06), rng.uniform(0.82, 1.12))
            leaf.data.materials.append(ck.get_material(colors[i % len(colors)]))
            for poly in leaf.data.polygons:
                poly.use_smooth = False
            _attach(leaf, root, seed + i, tint=(rng.uniform(0.91, 1.08), 1.0, rng.uniform(0.90, 1.07)))
            if kind == 'blossom':
                for flower_i in range(3):
                    aa = a + flower_i * math.tau / 3
                    ox, oy = math.cos(aa) * radius * 0.52, math.sin(aa) * radius * 0.52
                    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.22 * size / 4.0,
                        location=(x + math.cos(a) * radial + ox, y + math.sin(a) * radial + oy, cz + radius * 0.12))
                    petal = bpy.context.object
                    petal.name = 'blossom canopy flower cluster'
                    petal.data.materials.append(ck.get_material(colors[2]))
                    _attach(petal, root, seed + flower_i + 8)
    return (x, y, z)


def _flower_bed(root, cx, cy, radius, seed):
    rng = random.Random(seed)
    _lathe(root, 'garden stone planter', [(radius * 0.84, 0), (radius, 0.28),
           (radius * 0.92, 0.50), (radius * 0.78, 0.50)], 'stone_trim_carved',
           (cx, cy, 0.0), 12, seed)
    _lathe(root, 'garden dark soil', [(0, 0), (radius * 0.75, 0)], 'timber_dark',
           (cx, cy, 0.48), 20, seed)
    flowers = ('flower_ivory', 'flower_lilac', 'flower_gold')
    for i in range(16):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(0.1, radius * 0.72)
        z = 0.58 + rng.uniform(0.15, 0.55)
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
        _lathe(root, 'garden leafy stem', [(0.10, 0), (0.08, 0.24), (0.035, 0.60)],
               'foliage_mid', (x, y, z), 7, seed + i)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.15,
            location=(x, y, z + 0.60))
        flower = bpy.context.object
        flower.name = 'garden blossom'
        flower.data.materials.append(ck.get_material(flowers[i % len(flowers)]))
        _attach(flower, root, seed + i + 20)


def _lamp(root, x, y, z, seed):
    _lathe(root, 'city lamp stone foot', [(0.44, 0), (0.58, 0.22), (0.40, 0.50)],
           'stone_trim_carved', (x, y, z), 12, seed)
    _lathe(root, 'city lamp iron column', [(0.16, 0), (0.12, 2.5), (0.22, 2.75)],
           'metal_gold', (x, y, z + 0.48), 12, seed)
    _lathe(root, 'city lamp crystal', [(0.0, 0), (0.32, 0.10), (0.26, 1.0), (0.0, 1.24)],
           'magic_blue', (x, y, z + 2.9), 8, seed)
    _lathe(root, 'city lamp crown', [(0.44, 0), (0.50, 0.20), (0.0, 0.65)],
           'roof_slate_blue', (x, y, z + 3.95), 8, seed)


def _bench(root, x, y, angle, seed):
    x0, y0 = x, y
    for i in range(4):
        bld._box(root, 'plaza bench oak slat', (x0, y0, 0.78 + i * 0.12), (3.2, 0.24, 0.12),
                 'wood_planks_light', 0.025, seed=seed + i, rot_z=angle)
    for side in (-1, 1):
        xx, yy = x0 + side * 1.15 * math.cos(angle), y0 + side * 1.15 * math.sin(angle)
        bld._box(root, 'plaza bench stone leg', (xx, yy, 0.42), (0.38, 0.48, 0.8),
                 'stone_trim_carved', 0.06, seed=seed, rot_z=angle)
        bld._box(root, 'plaza bench carved arm', (xx, yy, 1.35), (0.38, 0.48, 0.24),
                 'stone_trim_carved', 0.04, seed=seed, rot_z=angle)


def build_vegetation(layout: dict, col):
    _material_library()
    root = _root(col)
    seed = random.Random(99831)
    island = layout['island']
    xl, xr = island['x_min'] + 11, island['x_max'] - 11
    yb, yt = island['y_min'] + 11, island['y_max'] - 11
    occupied = []
    for lm in layout['landmarks']:
        if lm.get('kind') in ('castle', 'stairs', 'arcade', 'bridge_arched', 'gate'):
            continue
        if 'center' in lm:
            w, d = lm.get('footprint', [14, 12])
            occupied.append((lm['center'][0], lm['center'][1], max(w, d) * 0.5 + 8.0))
        for center in lm.get('centers', []):
            occupied.append((center[0], center[1], 11.0))
    candidates = []
    spacing = float(layout['vegetation']['perimeter_belt'].get('spacing_m', 7.5))
    # A staggered rounded-rectangle tree belt frames the town and hides cliff seams.
    y = yb
    while y <= yt:
        for side in (-1, 1):
            candidates.append((side * (xr - seed.uniform(0, 5)), y + seed.uniform(-3, 3), 'oak'))
        y += spacing * 1.55
    x = xl
    while x <= xr:
        for side in (-1, 1):
            candidates.append((x + seed.uniform(-3, 3), side * (yt - seed.uniform(0, 4)) if side > 0 else yb + seed.uniform(0, 4),
                               'blossom' if seed.random() < 0.24 else 'oak'))
        x += spacing * 1.55
    # Data-driven groves bring pink blossom and amber foliage into distinct
    # neighborhoods; placement is seeded and avoids the authored building pads.
    for grove in layout['vegetation'].get('groves', []):
        cx, cy = grove['center']
        for _ in range(int(grove['count'])):
            a = seed.uniform(0, math.tau)
            r = math.sqrt(seed.random()) * float(grove['radius'])
            kind = seed.choices(['oak', 'pine', 'blossom', 'autumn'], [0.44, 0.26, 0.18, 0.12])[0]
            candidates.append((cx + math.cos(a) * r, cy + math.sin(a) * r, kind))
    accepted = []
    for x, y, kind in candidates:
        if not (xl <= x <= xr and yb <= y <= yt):
            continue
        if math.hypot(x, y) < 32.0:
            continue
        if any(math.hypot(x - bx, y - by) < radius for bx, by, radius in occupied):
            continue
        if any(math.hypot(x - px, y - py) < 8.3 for px, py, _ in accepted):
            continue
        accepted.append((x, y, kind))
    for i, (x, y, kind) in enumerate(accepted):
        _tree(root, x, y, kind, seed.uniform(3.4, 5.0), 1000 + i)
    # The plaza ring is populated with large stone pots, 12 blue lamps, and
    # curved benches at 30 m: legible at a distance and practical street scale.
    plaza = layout['plaza']
    for i in range(int(plaza.get('planter_count', 12))):
        a = i * math.tau / int(plaza.get('planter_count', 12))
        r = float(plaza.get('planter_ring_radius', 17.5))
        _flower_bed(root, r * math.cos(a), r * math.sin(a), 2.0, 2000 + i)
    for i in range(int(plaza.get('lamp_count', 12))):
        a = i * math.tau / int(plaza.get('lamp_count', 12)) + math.pi / 12
        r = float(plaza.get('lamp_ring_radius', 24.0))
        _lamp(root, r * math.cos(a), r * math.sin(a), 0.0, 3000 + i)
    for i in range(12):
        a = i * math.tau / 12
        r = float(plaza.get('bench_ring_radius', 30.0))
        _bench(root, r * math.cos(a), r * math.sin(a), a + math.pi / 2, 4000 + i)
    print(f'vegetation: {len(accepted)} trees, 12 planters, 12 lamps, 12 benches', flush=True)
    return root

