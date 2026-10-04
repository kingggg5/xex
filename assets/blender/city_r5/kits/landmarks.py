"""R5 signature landmarks: observatory, windmill, fountain, portal, gate, bridges."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import citykit as ck  # noqa: E402
import buildings as bld  # noqa: E402

STONE, TRIM, FOUNDATION = 'stone_wall_warm', 'stone_trim_carved', 'stone_foundation'
PLASTER = 'plaster_cream'
BLUE_ROOF, NAVY_ROOF = 'roof_slate_blue', 'roof_slate_navy'
RED_ROOF = 'roof_tile_red'
WOOD, IRON, GOLD = 'timber_dark', 'metal_iron', 'metal_gold'
BLUE = 'magic_blue'


def _root(name, col):
    obj = bpy.data.objects.new(f'kit_{name}', None)
    obj.empty_display_type = 'PLAIN_AXES'
    col.objects.link(obj)
    return obj


def _box(root, name, center, size, mat, bevel=0.04, seed=0, rot_z=0.0):
    obj = ck.box(name, center, size, mat, rot_z=rot_z)
    if bevel:
        ck.bevel(obj, min(bevel, min(size) * 0.18), segments=2, angle_deg=34)
    ck.uv_box(obj)
    ck.vertex_paint(obj, seed=seed, ground_z=0.02, cavity=0.3, edge=0.16, jitter=0.025)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _lathe(root, name, profile, material, center=(0, 0, 0), segments=32):
    obj = ck.lathe(name, profile, segments=segments, material=material, center=center)
    ck.uv_box(obj)
    ck.vertex_paint(obj, seed=len(name), ground_z=0.02, cavity=0.22, edge=0.10, jitter=0.025)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _beam(root, name, a, b, width, mat, depth=None):
    return bld._beam(root, name, a, b, width, mat, depth=depth)


def _hook(root, name, loc=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = 'SPHERE'
    obj.location = loc
    (root.users_collection[0] if root.users_collection else bpy.context.scene.collection).objects.link(obj)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _ring_profile(radius, z, tube=0.24):
    return [(radius - tube, z), (radius + tube, z),
            (radius + tube, z + tube * 1.4), (radius - tube, z + tube * 1.4)]


def _spire(root, name, x, y, base_z, height, radius, *, mat=BLUE_ROOF, windows=5):
    # Tapered buttressed tower, several carved stone belts, and a long slate cap.
    shaft_top = height * 0.72
    _lathe(root, f'{name} ashlar shaft', [(radius * 0.78, 0), (radius, 0.7), (radius * 0.92, 2.1),
            (radius * 0.72, shaft_top * 0.48), (radius * 0.58, shaft_top * 0.77),
            (radius * 0.48, shaft_top), (0, shaft_top)], STONE, (x, y, base_z), 40)
    for z, rr in [(0.52, radius * 1.08), (2.15, radius * 0.99),
                  (shaft_top * 0.50, radius * 0.75), (shaft_top, radius * 0.56)]:
        _lathe(root, f'{name} moulded course', [(rr * 0.94, z), (rr, z + 0.25), (rr * 0.94, z + 0.52)], TRIM,
               (x, y, base_z), 40)
    # Carved vertical buttresses visually connect the foot to the upper gallery.
    for i in range(8):
        a = math.tau * i / 8
        xx, yy = x + radius * 0.78 * math.cos(a), y + radius * 0.78 * math.sin(a)
        _beam(root, f'{name} flying buttress', (xx, yy, base_z + 1.0),
              (x + radius * 0.52 * math.cos(a), y + radius * 0.52 * math.sin(a), base_z + shaft_top - 0.5),
              0.42, TRIM, depth=0.55)
    for i in range(windows):
        z = base_z + 3.2 + i * max(4.0, (shaft_top - 7.0) / max(1, windows - 1))
        rr = radius * (0.91 - 0.40 * min(1.0, z / max(shaft_top, 1.0)))
        for side in range(4):
            a = side * math.pi * 0.5 - math.pi * 0.5
            xx, yy = x + rr * math.cos(a), y + rr * math.sin(a)
            obj = ck.box(f'{name} lancet window', (xx, yy, z), (0.74, 0.18, 2.55),
                         'glass_window_blue', rot_z=a + math.pi * 0.5)
            ck.uv_box(obj)
            ck.vertex_paint(obj, seed=i + side, ground_z=None, jitter=0.0)
            obj.parent = root
            obj.matrix_parent_inverse = Matrix.Identity(4)
    _lathe(root, f'{name} slate spire', [(radius * 1.30, base_z + shaft_top),
            (radius * 1.12, base_z + shaft_top + height * 0.05),
            (radius * 0.78, base_z + shaft_top + height * 0.28),
            (radius * 0.42, base_z + shaft_top + height * 0.53),
            (radius * 0.12, base_z + height * 0.97), (0, base_z + height)], mat, (x, y, 0), 40)
    _lathe(root, f'{name} gold finial', [(radius * 0.18, base_z + height - 0.45),
            (radius * 0.12, base_z + height + 0.2), (0, base_z + height + 1.8)], GOLD, (x, y, 0), 20)


def build_wizard_tower(lm: dict, col):
    root = _root('wizard_tower', col)
    base_r = float(lm.get('base_radius', 8.0))
    height = float(lm.get('height', 62.0))
    _lathe(root, 'observatory tapered tower', [(base_r * 0.72, 0), (base_r, 1.5), (base_r * 0.92, 6),
            (base_r * 0.73, 18), (base_r * 0.61, 32), (base_r * 0.45, 47),
            (base_r * 0.36, height), (0, height)], STONE, segments=64)
    for i in range(6):
        z = 4.0 + i * 9.0
        radius = base_r * (0.93 - i * 0.085)
        _lathe(root, 'wizard tower decorative belt', [(radius, z), (radius * 1.05, z + 0.30), (radius, z + 0.65)],
               TRIM, segments=48)
    # Deeply inset violet lancets, gold mullions, carved sills and tiny finials.
    for floor, z in enumerate((8, 16, 25, 34, 43, 52)):
        r = base_r * (0.87 - floor * 0.074)
        for side in range(8):
            a = side * math.tau / 8 - math.pi / 2
            x, y = r * math.cos(a), r * math.sin(a)
            obj = ck.box('wizard purple lancet', (x, y, z), (0.88, 0.16, 3.8),
                         'magic_purple', rot_z=a + math.pi / 2)
            ck.uv_box(obj)
            ck.vertex_paint(obj, ground_z=None, seed=side + floor, jitter=0.0)
            obj.parent = root
            obj.matrix_parent_inverse = Matrix.Identity(4)
            _beam(root, 'wizard gold window tracery', (x - 0.48 * math.cos(a), y - 0.48 * math.sin(a), z),
                  (x + 0.48 * math.cos(a), y + 0.48 * math.sin(a), z), 0.075, GOLD)
    # The two runic rings are independent named nodes for later client animation.
    for index, ring_spec in enumerate(lm.get('rings', []), 1):
        radius, z = float(ring_spec['radius']), float(ring_spec['height'])
        pivot = _hook(root, f'anim_wizard_ring_{index}', (0, 0, z))
        _lathe(pivot, f'wizard rune ring {index}', _ring_profile(radius, 0.0, 0.30), GOLD, segments=72)
        for rune in range(16):
            a = math.tau * rune / 16
            _lathe(pivot, f'wizard ring rune crystal {index}-{rune}', [(0.0, 0.0), (0.34, 0.0),
                    (0.0, 0.72)], 'magic_purple', (radius * math.cos(a), radius * math.sin(a), 0.12), 8)
    _spire(root, 'observatory crown', 0, 0, height * 0.68, float(lm.get('spire_tip', 78)) - height * 0.68,
           base_r * 0.56, mat=NAVY_ROOF, windows=1)
    # Front stair/gatehouse and two lamp pylons establish character scale.
    for i in range(7):
        z = 0.18 + i * 0.22
        _box(root, 'wizard gate stair', (0, -base_r - 1.1 - i * 0.82, z), (7.2 + i * 0.5, 0.86, 0.34 + i * 0.04), TRIM, 0.035)
    for side in (-1, 1):
        bld._conical_roof(root, 'observatory entry lantern', side * (base_r + 3.3), -base_r - 1.1, 0.4, 1.0, 4.8, BLUE_ROOF)
    return root


def build_windmill(lm: dict, col):
    root = _root('windmill', col)
    radius = float(lm.get('base_radius', 6.0))
    height = float(lm.get('height', 17.0))
    _lathe(root, 'windmill plaster tower', [(radius * 0.8, 0), (radius, 1.2), (radius * 0.92, 4),
            (radius * 0.78, 9), (radius * 0.61, height - 2.0), (radius * 0.68, height), (0, height)],
           PLASTER, segments=48)
    for z in (0.8, 5.0, 10.0, height - 1.5):
        rr = radius * (0.96 - 0.014 * z)
        _lathe(root, 'windmill stone course', [(rr, z), (rr * 1.08, z + 0.22), (rr, z + 0.42)], TRIM, segments=48)
    _lathe(root, 'windmill cap', [(radius * 1.08, height), (radius * 0.98, height + 0.6),
            (radius * 0.74, height + 2.3), (radius * 0.4, height + 4.2), (0, height + 5.0)], BLUE_ROOF, segments=48)
    for level in (4.8, 9.0, 13.0):
        r = radius * (0.84 - (level / height) * 0.22)
        for i in range(8):
            a = i * math.tau / 8
            x, y = r * math.cos(a), r * math.sin(a)
            obj = ck.box('windmill light window', (x, y, level), (0.92, 0.14, 1.7),
                         'glass_window_warm', rot_z=a + math.pi / 2)
            ck.uv_box(obj); ck.vertex_paint(obj, ground_z=None, seed=i + int(level), jitter=0.0)
            obj.parent = root; obj.matrix_parent_inverse = Matrix.Identity(4)
    # Sail pivot is a separate animated node; all four lattice blades are mesh geometry.
    pivot = _hook(root, 'anim_windmill_sails', (0, -radius - 0.34, height - 2.2))
    sail_r = float(lm.get('sail_radius', 12.0))
    _lathe(pivot, 'windmill carved hub', [(0, 0), (1.25, 0), (1.35, 0.6), (0, 0.6)], GOLD,
           center=(0, 0, 0), segments=32)
    for i in range(4):
        a = i * math.pi / 2
        direction = (math.cos(a), 0, math.sin(a))
        end = (direction[0] * sail_r, 0, direction[2] * sail_r)
        _beam(pivot, f'windmill sail spar {i + 1}', (0, 0, 0.26), end, 0.42, WOOD, depth=0.34)
        for j in range(1, 5):
            t = j / 5.0
            xx, zz = direction[0] * sail_r * t, direction[2] * sail_r * t
            width = 0.7 + 1.0 * t
            _beam(pivot, f'windmill lattice crossbar {i + 1}-{j}',
                  (xx - width, 0.02, zz), (xx + width, 0.02, zz), 0.11, TRIM, depth=0.10)
        side = -1 if a in (0, math.pi) else 1
        _beam(pivot, f'windmill canvas frame {i + 1}',
              (direction[0] * sail_r * 0.30, -0.035, direction[2] * sail_r * 0.30),
              (direction[0] * sail_r * 0.82, -0.035, direction[2] * sail_r * 0.82),
              1.0 + 0.5 * abs(direction[0]), 'cloth_cream', depth=0.045)
    # Small attached flour shed and fenced patch, all authored relative to tower.
    _box(root, 'windmill millers shed', (radius + 5.2, -1.0, 2.0), (7.0, 7.0, 4.0), PLASTER, 0.08)
    bld._gable_roof(root, 'windmill shed roof', 8.0, 8.0, 4.0, 2.5, RED_ROOF)
    for side in (-1, 1):
        _beam(root, 'windmill garden fence', (side * 13, -10, 0.65), (side * 13, 11, 0.65), 0.13, WOOD)
    return root


def build_fountain(layout: dict, col):
    root = _root('plaza_fountain', col)
    plinth = float(layout.get('plinth_radius', 14.0))
    basin = float(layout.get('basin_radius', 11.5))
    _lathe(root, 'fountain octagonal plinth', [(plinth, 0), (plinth, 0.75), (plinth - 0.65, 1.0)],
           FOUNDATION, segments=8)
    _lathe(root, 'fountain carved lower basin', [(basin * 0.72, 0.95), (basin, 1.2), (basin, 2.35),
            (basin * 0.91, 2.60), (basin * 0.76, 2.50), (basin * 0.70, 1.35)], TRIM, segments=64)
    _lathe(root, 'fountain blue water', [(0, 2.15), (basin * 0.74, 2.15)], 'water', segments=64)
    _lathe(root, 'fountain mosaic inner lip', _ring_profile(basin * 0.92, 2.38, 0.17), GOLD, segments=64)
    tier2 = float(layout.get('tier2_radius', 6.0))
    _lathe(root, 'fountain second bowl', [(tier2 * 0.76, 3.2), (tier2, 3.45), (tier2, 4.4),
            (tier2 * 0.86, 4.65), (tier2 * 0.72, 4.45)], STONE, segments=56)
    _lathe(root, 'fountain second water', [(0, 4.24), (tier2 * 0.72, 4.24)], 'water', segments=56)
    tier3 = float(layout.get('tier3_radius', 3.0))
    _lathe(root, 'fountain upper chalice', [(tier3 * 0.68, 6.0), (tier3, 6.25), (tier3, 7.0),
            (tier3 * 0.8, 7.24), (tier3 * 0.62, 7.0)], TRIM, segments=48)
    _lathe(root, 'fountain upper water', [(0, 6.90), (tier3 * 0.62, 6.90)], BLUE, segments=48)
    _lathe(root, 'fountain central stem', [(1.3, 2.3), (1.05, 3.6), (0.9, 4.5),
            (0.70, 5.3), (0.58, 7.3), (0.75, 8.0)], TRIM, segments=40)
    # Original crowned guardian statue: shaped robe, anatomy, layered wings and hands.
    _lathe(root, 'fountain guardian robe', [(0.85, 7.4), (1.35, 8.0), (1.05, 10.3),
            (0.72, 12.2), (0.35, 12.8), (0.0, 13.2)], 'marble_statue', center=(0, 0, 0), segments=32)
    _lathe(root, 'fountain guardian head', [(0.0, 12.6), (0.60, 12.6), (0.70, 13.2),
            (0.54, 13.9), (0.0, 14.1)], 'marble_statue', segments=32)
    for side in (-1, 1):
        _beam(root, 'fountain guardian raised arm', (side * 0.85, 0, 10.5),
              (side * 1.80, -0.08, 14.6), 0.55, 'marble_statue', depth=0.52)
        _lathe(root, 'fountain guardian palm', [(0, 0), (0.42, 0.0), (0.46, 0.28), (0.0, 0.28)],
               'marble_statue', (side * 1.95, -0.08, 14.2), 20)
        for feather in range(8):
            _beam(root, 'fountain guardian wing feather',
                  (side * 0.95, 0.25, 10.2 + feather * 0.28),
                  (side * (3.0 + feather * 0.88), 0.28, 15.4 - feather * 0.50),
                  0.28, 'marble_statue', depth=0.36)
        _beam(root, 'fountain feather ridge', (side * 0.85, 0.18, 10.3), (side * 8.2, 0.18, 11.4),
              0.34, TRIM)
    _lathe(root, 'fountain guardian crown crystal', [(0.0, 14.0), (0.60, 14.0), (0, 17.0)], BLUE,
           segments=8)
    # Four shallow jets fall into the basin as future runtime-linked water FX.
    for i in range(12):
        a = i * math.tau / 12
        x, y = 4.5 * math.cos(a), 4.5 * math.sin(a)
        _beam(root, 'fountain arcing water jet', (0, 0, 7.1), (x, y, 3.0), 0.10, 'water_foam', depth=0.08)
    _hook(root, 'emit_fountain_spray', (0, 0, 8.0))
    _hook(root, 'anim_crystal_fountain', (0, 0, 14.0))
    return root


def build_portal(layout: dict, col):
    root = _root('arcane_portal', col)
    r = float(layout.get('dais_radius', 8.5))
    _lathe(root, 'portal eight-sided dais', [(r, 0), (r, 0.50), (r - 0.55, 0.80)], FOUNDATION, segments=8)
    _lathe(root, 'portal blue stone inlay', [(r * 0.84, 0.80), (r * 0.84, 0.88)], BLUE_ROOF, segments=64)
    _lathe(root, 'portal glass disc', [(0, 0.89), (r * 0.73, 0.89)], 'magic_blue', segments=64)
    for ring_index, radius in enumerate((r * 0.32, r * 0.50, float(layout.get('rune_radius', 6.5))), 1):
        pivot = _hook(root, 'anim_portal_disc' if ring_index == 1 else f'anim_portal_rune_{ring_index}', (0, 0, 0.96 + 0.03 * ring_index))
        _lathe(pivot, f'portal luminous rune ring {ring_index}', _ring_profile(radius, 0.0, 0.09), BLUE, segments=80)
        for i in range(16):
            a = math.tau * i / 16
            _box(pivot, 'portal radial glyph', (radius * math.cos(a), radius * math.sin(a), 0.10),
                 (0.18, 0.68, 0.08), 'magic_blue', 0.015, rot_z=a)
    # Three runic pylons and crystal prisms frame the portal without blocking it.
    for i, a in enumerate((math.pi * 0.5, math.pi * 1.5, math.pi), 1):
        x, y = (r - 1.3) * math.cos(a), (r - 1.3) * math.sin(a)
        bld._conical_roof(root, f'portal rune pylon {i}', x, y, 0.82, 0.72, 3.6, TRIM)
        _lathe(root, f'portal floating shard {i}', [(0, 0), (0.38, 0.7), (0, 1.75)], BLUE,
               (x, y, 4.6), 8)
    _lathe(root, 'portal vertical light column', [(1.2, 0), (1.45, 0.25), (0.9, 9.0),
            (0.4, 17.5), (0.0, 20.0)], BLUE, (0, 0, 0.9), 24)
    _hook(root, 'fx_portal_beam', (0, 0, 4.0))
    _hook(root, 'light_portal', (0, 0, 7.5))
    return root


def build_town_gate(lm: dict, col):
    root = _root('town_gate', col)
    # Keep at least a 15 m clear span between the inner faces of the stone
    # piers. The gate is permanently open: no shadow card, portcullis slab, or
    # bars should occlude the road and canal beyond it.
    width = max(30.0, float(lm.get('width', 30.0)))
    half = width * 0.5
    # Broad gatehouse, two keeps and lower stepped curtain wings; the centre stays open.
    for side in (-1, 1):
        x = side * (half + 2.0)
        _lathe(root, 'town gate round tower', [(4.8, 0), (5.5, 1.4), (5.2, 7.5), (4.5, 14.0),
                (3.8, 18.0), (0, 18.0)], STONE, (x, 0, 0), 48)
        for z in (1.0, 8.0, 14.0, 17.5):
            rr = 5.0 if z < 15 else 4.2
            _lathe(root, 'gate carved tower ring', [(rr, z), (rr * 1.08, z + 0.4), (rr, z + 0.8)], TRIM,
                   (x, 0, 0), 48)
        _lathe(root, 'gate blue tower cap', [(4.6, 18.0), (4.0, 19.5), (2.5, 24.5), (0.0, 28.0)],
               BLUE_ROOF, (x, 0, 0), 40)
        for i in range(8):
            a = i * math.tau / 8
            xx, yy = x + 4.6 * math.cos(a), 4.6 * math.sin(a)
            obj = ck.box('gate tower lancet', (xx, yy, 9.0), (0.82, 0.16, 3.6),
                         'glass_window_blue', rot_z=a + math.pi * 0.5)
            ck.uv_box(obj); ck.vertex_paint(obj, ground_z=None, jitter=0.0)
            obj.parent = root; obj.matrix_parent_inverse = Matrix.Identity(4)
        for seg in range(3):
            x0 = side * (half + 7 + seg * 14)
            _box(root, 'gate curtain wall block', (x0, 0, 7.0 - seg * 0.65), (14.0, 3.4, 14.0 - seg * 1.3), STONE, 0.12, seed=seg)
            for crenel in range(5):
                cx = x0 + side * (-6.0 + crenel * 3.0)
                _box(root, 'gate curtain merlon', (cx, 0, 14.5 - seg * 0.65), (1.7, 3.8, 1.5), TRIM, 0.06, seed=crenel)
        # Rich banners on the gate towers and a lantern over the entry road.
        bld._banner(root, 'town gate royal standard', side * (half + 1.0), -2.45, 16.0, 3.0, 8.0)
    # Central stone arch with deep reveal. The pier placement leaves exactly
    # width / 2 metres between their inner faces (15 m at the minimum width).
    _box(root, 'gate west pier', (-half * 0.5 - 2.4, 0, 9.0), (4.8, 6.0, 18.0), TRIM, 0.1)
    _box(root, 'gate east pier', (half * 0.5 + 2.4, 0, 9.0), (4.8, 6.0, 18.0), TRIM, 0.1)
    _box(root, 'gate arch lintel', (0, 0, 18.2), (width + 10.0, 6.4, 4.0), STONE, 0.14)
    for side in (-1, 1):
        _box(root, 'gate lion plinth', (side * (half + 8), -5.0, 2.0), (5.0, 4.0, 4.0), FOUNDATION, 0.12)
        _lathe(root, 'gate guardian statue', [(0, 0), (1.2, 0.3), (1.4, 2.5), (0.7, 3.3), (0, 4.0)],
               'marble_statue', (side * (half + 8), -5.0, 4.0), 24)
    _hook(root, 'light_castle_door', (0, -4.8, 11.0))
    return root


def build_bridge(lm: dict, col):
    root = _root(lm.get('id', 'bridge'), col)
    length = float(lm.get('length', 18.0))
    width = float(lm.get('width', 8.0))
    count = 16
    # Arch rises 2.2 m at midspan; a tiled wedge deck follows it over the canal.
    for i in range(count):
        t = (i + 0.5) / count
        x = (t - 0.5) * length
        rise = 2.4 * math.sin(math.pi * t)
        _box(root, 'bridge dressed flagstone', (x, 0, 0.35 + rise), (length / count + 0.12, width, 0.68),
             'plaza_flagstone', 0.04, seed=i)
        for side in (-1, 1):
            y = side * width * 0.5
            _box(root, 'bridge parapet panel', (x, y, 1.3 + rise), (length / count + 0.10, 0.60, 1.7), STONE, 0.06, seed=i)
            _box(root, 'bridge pale coping', (x, y, 2.2 + rise), (length / count + 0.20, 0.78, 0.22), TRIM, 0.035, seed=i)
    for side in (-1, 1):
        for x in (-length * 0.42, 0, length * 0.42):
            _lathe(root, 'bridge lamp pedestal', [(0.55, 0), (0.7, 0.4), (0.45, 0.8)], TRIM,
                   (x, side * (width * 0.50), 2.5 + 2.4 * math.sin(math.pi * (x / length + 0.5))), 16)
            bld._conical_roof(root, 'bridge blue lamp finial', x, side * (width * 0.50), 3.25,
                              0.38, 1.1, BLUE_ROOF)
    # Repeating voussoirs make the silhouette read as a masonry arch from below.
    for i in range(13):
        t = i / 12.0
        x = (t - 0.5) * length * 0.82
        z = -1.2 + 3.0 * math.sin(math.pi * t)
        _box(root, 'bridge arch voussoir', (x, 0, z), (1.5, width * 0.76, 1.05), TRIM, 0.09, seed=i)
    return root

