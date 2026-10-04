"""R5 original architecture kit: readable silhouettes and dressed facades.

All dimensions come from layout.json. The reusable timber/stone construction
is original to Aetherfield; it uses no Ragnarok meshes, textures, names or UI.
Every building is aligned with its front at local -Y so the assembler can
rotate the root toward its authored face target.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import citykit as ck  # noqa: E402

STONE = 'stone_wall_warm'
TRIM = 'stone_trim_carved'
FOUNDATION = 'stone_foundation'
PLASTER = 'plaster_cream'
WOOD = 'timber_dark'
WOOD_LIGHT = 'wood_planks_light'
IRON = 'metal_iron'
GOLD = 'metal_gold'
GLASS = 'glass_window_warm'
BLUE_GLASS = 'glass_window_blue'
BLUE_ROOF = 'roof_slate_blue'
NAVY_ROOF = 'roof_slate_navy'
GREEN_ROOF = 'roof_shingle_green'
RED_ROOF = 'roof_tile_red'

QUATERNIUS_STALL_CART = (
    Path(__file__).resolve().parents[4]
    / 'assets' / 'third-party' / 'quaternius-fantasy-props-megakit'
    / 'standard' / 'stall-cart' / 'glTF' / 'Stall_Cart_Empty.gltf'
)
ROOF = BLUE_ROOF
ROOFS = (BLUE_ROOF, RED_ROOF, GREEN_ROOF, NAVY_ROOF)


def _root(name: str, col):
    obj = bpy.data.objects.new(f'kit_{name}', None)
    obj.empty_display_type = 'PLAIN_AXES'
    col.objects.link(obj)
    return obj


def _own(obj, root, *, bevel=0.0, uv='box', tint=(1.0, 1.0, 1.0), seed=0, ground=True):
    if bevel:
        ck.bevel(obj, width=bevel, segments=2, angle_deg=32)
    if uv == 'beam':
        ck.uv_beam(obj, tile_m=2.0)
    elif uv == 'unit':
        ck.uv_unit(obj)
    else:
        ck.uv_box(obj)
    ck.vertex_paint(obj, tint=tint, ground_z=0.02 if ground else None, seed=seed,
                    cavity=0.28, edge=0.14, jitter=0.035)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _box(root, name, center, size, mat, bevel=0.035, *, tint=(1.0, 1.0, 1.0), seed=0, rot_z=0.0):
    return _own(ck.box(name, center, size, mat, rot_z=rot_z), root,
                bevel=bevel, tint=tint, seed=seed)


def _mesh(root, name, verts, faces, mat, *, uv='box', tint=(1.0, 1.0, 1.0), seed=0):
    return _own(ck.new_object(name, verts, faces, mat), root, uv=uv, tint=tint, seed=seed)


def _beam(root, name, a, b, width, mat, depth=None, seed=0):
    """Build a square/rectangular beam between 3D points with real chamfers."""
    a, b = Vector(a), Vector(b)
    axis = b - a
    length = axis.length
    if length < 1e-5:
        return None
    axis.normalize()
    up = Vector((0, 0, 1))
    side = axis.cross(up)
    if side.length < 1e-5:
        side = Vector((1, 0, 0))
    side.normalize()
    normal = axis.cross(side).normalized()
    dy = width if depth is None else depth
    u, v = side * width * 0.5, normal * dy * 0.5
    verts = []
    for p in (a, b):
        verts.extend([tuple(p - u - v), tuple(p + u - v), tuple(p + u + v), tuple(p - u + v)])
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    obj = _mesh(root, name, verts, faces, mat, uv='beam', seed=seed)
    if width >= 0.11 and dy >= 0.11:
        ck.bevel(obj, width=min(0.035, width * 0.13, dy * 0.13), segments=2, angle_deg=32)
    return obj


def _gable_roof(root, name, width, depth, eave_z, rise, mat, *, x0=0.0, y0=0.0, dormers=0, seed=0):
    x1, x2 = x0 - width * 0.5, x0 + width * 0.5
    yf, yb = y0 - depth * 0.5, y0 + depth * 0.5
    peak = eave_z + rise
    verts = [(x1, yf, eave_z), (x2, yf, eave_z), (x0, yf, peak),
             (x1, yb, eave_z), (x2, yb, eave_z), (x0, yb, peak)]
    faces = [(0, 2, 5, 3), (2, 1, 4, 5), (0, 1, 2), (3, 5, 4), (0, 3, 4, 1)]
    obj = _mesh(root, f'{name} roof skin', verts, faces, mat, seed=seed)
    # Long eaves and ridge carry carved caps; gable verges catch a bright edge.
    _beam(root, f'{name} ridge cap', (x0, yf - 0.12, peak + 0.10), (x0, yb + 0.12, peak + 0.10), 0.24, TRIM, seed=seed + 1)
    for y in (yf - 0.10, yb + 0.10):
        _beam(root, f'{name} eave', (x1 - 0.35, y, eave_z), (x2 + 0.35, y, eave_z), 0.26, WOOD, seed=seed + 2)
        for side in (-1, 1):
            _beam(root, f'{name} gable verge', (x0, y, peak + 0.05),
                  (x0 + side * (width * 0.5 + 0.32), y, eave_z - 0.05), 0.20, TRIM, seed=seed + 3)
    # Six small raised bands catch grazing light across both slate slopes.
    for row in range(1, 6):
        t = row / 6.0
        z = peak - rise * t + 0.045
        half = width * 0.5 * t
        for side in (-1, 1):
            _beam(root, f'{name} slate course', (x0 + side * half, yf + 0.10, z),
                  (x0 + side * half, yb - 0.10, z), 0.045, mat, depth=0.04, seed=seed + row)
    if dormers and width > 11:
        for i in range(dormers):
            x = x0 + (i - (dormers - 1) * 0.5) * min(4.8, width / (dormers + 1))
            y = y0 - depth * 0.23
            z = peak - rise * 0.42
            _box(root, f'{name} dormer cheek', (x, y - 0.20, z + 0.85), (1.8, 0.52, 1.7), PLASTER, 0.045, seed=seed + i)
            _gable_roof(root, f'{name} dormer', 2.0, 1.45, z + 1.35, 0.82, mat, x0=x, y0=y - 0.26, seed=seed + 9 + i)
            _box(root, f'{name} dormer glass', (x, y - 0.49, z + 1.0), (0.74, 0.075, 0.86), BLUE_GLASS, 0.02)
    return obj


def _gable_panel(root, name, width, base_y, base_z, rise, mat=PLASTER):
    verts = [(-width * 0.5, base_y, base_z), (width * 0.5, base_y, base_z), (0, base_y, base_z + rise)]
    return _mesh(root, name, verts, [(0, 1, 2)], mat)


def _window(root, name, x, y, z, w=1.32, h=1.78, shutter=True, tint=(1.0, 1.0, 1.0), seed=0, yaw=0.0):
    """Build a complete front-facing window, then turn its whole assembly if needed."""
    parts = []

    def part(*args, **kwargs):
        obj = _box(root, *args, **kwargs)
        parts.append(obj)
        return obj

    part(f'{name} stone reveal', (x, y - 0.04, z), (w + 0.44, 0.24, h + 0.42), TRIM, 0.07, seed=seed)
    part(f'{name} dark inset', (x, y - 0.18, z), (w + 0.08, 0.09, h + 0.08), WOOD, 0.03, seed=seed + 1)
    part(f'{name} glass', (x, y - 0.25, z), (w, 0.065, h), GLASS if seed % 3 else BLUE_GLASS, 0.02, seed=seed + 2)
    part(f'{name} vertical mullion', (x, y - 0.31, z), (0.10, 0.05, h), GOLD, 0.01, seed=seed + 3)
    part(f'{name} horizontal mullion', (x, y - 0.31, z), (w, 0.05, 0.095), GOLD, 0.01, seed=seed + 4)
    part(f'{name} sill', (x, y - 0.25, z - h * 0.58), (w + 0.55, 0.42, 0.15), TRIM, 0.035, seed=seed + 5)
    if shutter:
        for side in (-1, 1):
            part(f'{name} shutter', (x + side * (w * 0.5 + 0.18), y - 0.22, z),
                 (0.33, 0.14, h * 0.92), WOOD, 0.025, tint=tint, seed=seed + side + 8)
            for zz in (-0.52, 0, 0.52):
                part(f'{name} shutter strap', (x + side * (w * 0.5 + 0.18), y - 0.305, z + zz),
                     (0.32, 0.035, 0.065), IRON, 0.009, seed=seed + 12)
    if yaw:
        anchor = Vector((x, y, z))
        pivot = Matrix.Translation(anchor) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Translation(-anchor)
        for obj in parts:
            obj.matrix_basis = pivot @ obj.matrix_basis


def _door(root, name, y, width=1.9, height=3.1):
    cz = height * 0.5 + 0.1
    _box(root, f'{name} carved surround', (0, y - 0.06, cz), (width + 0.72, 0.45, height + 0.6), TRIM, 0.08)
    _box(root, f'{name} shadow recess', (0, y - 0.30, cz), (width + 0.10, 0.16, height + 0.06), FOUNDATION, 0.035)
    _box(root, f'{name} oak door', (0, y - 0.42, cz), (width, 0.16, height), WOOD, 0.045)
    for i in range(5):
        x = (i - 2) * (width - 0.22) / 4
        _box(root, f'{name} inset panel', (x, y - 0.515, cz + 0.05), (0.28, 0.035, height - 0.52), WOOD_LIGHT, 0.016)
    for side in (-1, 1):
        _box(root, f'{name} hinge strap', (side * (width * 0.36), y - 0.55, cz - 0.36), (0.42, 0.05, 0.10), IRON, 0.018)
        _box(root, f'{name} hinge pin', (side * (width * 0.39), y - 0.57, cz + 0.42), (0.10, 0.06, 0.16), GOLD, 0.02)
    _box(root, f'{name} brass handle', (width * 0.31, y - 0.57, cz + 0.10), (0.12, 0.08, 0.18), GOLD, 0.04)
    for step in range(3):
        _box(root, f'{name} entrance step', (0, y - 0.70 - step * 0.50, 0.22 + step * 0.18),
             (width + 1.8 + step * 0.5, 0.66, 0.30), TRIM, 0.055)


def _awnings(root, name, width, y, z, palette=("cloth_blue", "cloth_cream"), depth=2.8):
    n = max(5, int(width / 1.35))
    for i in range(n):
        x0 = -width * 0.5 + width * i / n
        x1 = -width * 0.5 + width * (i + 1) / n
        verts = [(x0, y, z), (x1, y, z), (x1, y - depth, z - 0.78), (x0, y - depth, z - 0.78),
                 (x0, y - depth - 0.40, z - 1.05), (x1, y - depth - 0.40, z - 1.05)]
        _mesh(root, f'{name} striped canvas {i + 1}', verts,
              [(0, 1, 2, 3), (3, 2, 5, 4)], palette[i % len(palette)], uv='unit', seed=100 + i)
    for side in (-1, 1):
        x = side * (width * 0.5 - 0.35)
        _beam(root, f'{name} canopy pole', (x, y - depth - 0.23, 0.15),
              (x, y - depth - 0.23, z - 0.95), 0.13, WOOD)
        _beam(root, f'{name} canopy tie', (x, y, z), (x, y - depth, z - 0.78), 0.10, WOOD)


def _sign(root, name, y, z, width=2.5, tint=BLUE_ROOF):
    _beam(root, f'{name} hanging bracket', (-0.48, y + 0.12, z + 0.42), (0.48, y + 0.12, z + 0.42), 0.14, GOLD)
    _box(root, f'{name} sign frame', (0, y - 0.05, z), (width, 0.22, 0.92), WOOD, 0.07)
    _box(root, f'{name} enamel face', (0, y - 0.18, z), (width - 0.28, 0.06, 0.64), tint, 0.035)
    _box(root, f'{name} gold crest', (0, y - 0.23, z), (0.22, 0.045, 0.34), GOLD, 0.02)
    for side in (-1, 1):
        _beam(root, f'{name} suspension chain', (side * 0.42, y, z + 0.48),
              (side * 0.42, y, z + 1.25), 0.045, IRON, depth=0.045)


def _chimney(root, name, x, y, z, height=6.0, glow=False):
    _box(root, f'{name} brick stack', (x, y, z + height * 0.5), (1.35, 1.4, height), STONE, 0.07)
    for i in range(max(3, int(height / 1.0))):
        zz = z + 0.55 + i * (height - 0.5) / max(3, int(height / 1.0))
        _box(root, f'{name} mortar band', (x, y - 0.73, zz), (1.30, 0.07, 0.05), TRIM, 0.01, seed=i)
    _box(root, f'{name} crown cap', (x, y, z + height + 0.12), (1.85, 1.88, 0.28), TRIM, 0.055)
    if glow:
        _box(root, f'{name} firebox glow', (x, y - 0.76, z + 1.45), (0.56, 0.08, 0.72), 'fire_glow', 0.02)
        emitter = bpy.data.objects.new('emit_forge_sparks', None)
        emitter.empty_display_type = 'SPHERE'
        emitter.location = (x, y - 0.9, z + 1.6)
        (root.users_collection[0] if root.users_collection else bpy.context.scene.collection).objects.link(emitter)
        emitter.parent = root
        emitter.matrix_parent_inverse = Matrix.Identity(4)


def _barrel(root, name, x, y, z, radius=0.56, height=1.1, seed=0):
    profile = [(radius * 0.78, 0), (radius * 0.94, height * 0.18), (radius, height * 0.5),
               (radius * 0.95, height * 0.82), (radius * 0.78, height), (0.0, height)]
    obj = _own(ck.lathe(name, profile, segments=16, material=WOOD, col=None, center=(x, y, z)), root,
               uv='box', seed=seed)
    for zz in (height * 0.18, height * 0.80):
        hoop = ck.lathe(f'{name} iron hoop', [(radius * 0.95, zz), (radius * 1.02, zz + 0.07)],
                        segments=20, material=IRON, center=(x, y, z))
        _own(hoop, root, seed=seed + 1)
    for plank in range(6):
        a = math.tau * plank / 6
        _box(root, f'{name} stave seam', (x + radius * math.cos(a), y + radius * math.sin(a), z + height * 0.5),
             (0.035, 0.035, height * 0.68), WOOD_LIGHT, 0.008, rot_z=a, seed=seed + plank)
    return obj


def _building_shell(root, name, w, d, stories, *, wall=PLASTER, roof=BLUE_ROOF, seed=0, dormers=1,
                    timber=True, body_h=None):
    story_h = 4.25
    body_h = float(body_h or stories * story_h)
    front = -d * 0.5
    _box(root, f'{name} foundation plinth', (0, 0, 0.52), (w + 2.2, d + 2.2, 1.04), FOUNDATION, 0.12, seed=seed)
    _box(root, f'{name} dressed plinth course', (0, 0, 1.18), (w + 1.0, d + 1.0, 0.36), TRIM, 0.08, seed=seed + 1)
    _box(root, f'{name} masonry body', (0, 0, 1.22 + body_h * 0.5), (w, d, body_h), wall, 0.075, seed=seed + 2)
    # Exposed timber frame with small carved knees at every jettied floor.
    if timber:
        for z in [1.45] + [1.25 + story_h * i for i in range(1, stories + 1)]:
            if z > body_h + 1.22:
                continue
            _box(root, f'{name} front sill beam', (0, front - 0.12, z), (w + 0.3, 0.26, 0.22), WOOD, 0.035, seed=seed + int(z * 11))
        for x in [-w * 0.5 + 0.12, 0, w * 0.5 - 0.12]:
            _box(root, f'{name} front upright', (x, front - 0.13, 1.2 + body_h * 0.5), (0.22, 0.28, body_h), WOOD, 0.035, seed=seed + int((x + w) * 4))
        for x in (-w * 0.5 + 0.12, w * 0.5 - 0.12):
            for y in (-d * 0.5 + 0.12, d * 0.5 - 0.12):
                _box(root, f'{name} corner post', (x, y, 1.18 + body_h * 0.5), (0.34, 0.34, body_h + 0.15), WOOD, 0.055, seed=seed + 7)
                _box(root, f'{name} post capital', (x, y, body_h + 1.24), (0.62, 0.62, 0.24), TRIM, 0.045, seed=seed + 8)
        for side in (-1, 1):
            _box(root, f'{name} side plate', (side * (w * 0.5 + 0.02), 0, 1.18 + body_h * 0.52), (0.20, d + 0.24, 0.20), WOOD, 0.03, seed=seed + 9)
    # Deep-set windows and shutters across both the street front and visible ends.
    floors = max(1, stories)
    front_y = front - 0.11
    count = max(2, int(w // 5))
    for floor in range(floors):
        z = 3.3 + floor * story_h
        if z + 1.4 > body_h + 1.2:
            continue
        xs = [(i - (count - 1) * 0.5) * min(4.5, (w - 4.5) / max(1, count - 1)) for i in range(count)]
        for i, x in enumerate(xs):
            _window(root, f'{name} front window {floor + 1}-{i + 1}', x, front_y, z,
                    w=1.40 if w > 14 else 1.12, h=1.68 if floor else 1.48,
                    shutter=(i % 2 == 0), seed=seed + floor * 19 + i)
        for side in (-1, 1):
            x = side * (w * 0.5 + 0.12)
            for yi in range(max(1, int(d // 6))):
                y = (yi - (max(1, int(d // 6)) - 1) * 0.5) * min(4.4, d / max(1, int(d // 6)))
                _window(root, f'{name} side window {floor + 1}-{yi + 1}', x, y,
                        z, w=1.10, h=1.55, shutter=(yi == 0), seed=seed + 70 + floor * 7 + yi,
                        yaw=side * math.pi / 2)
    _door(root, f'{name} entrance', front - 0.05, width=2.15 if w > 12 else 1.72,
          height=3.05 if stories > 1 else 2.75)
    _gable_panel(root, f'{name} front plaster gable', w, front - 0.035, body_h + 1.18, 3.3, wall)
    for side in (-1, 1):
        _beam(root, f'{name} gable barge', (0, front - 0.12, body_h + 4.6),
              (side * (w * 0.5 + 0.36), front - 0.12, body_h + 1.18), 0.22, WOOD, seed=seed + 90)
        _beam(root, f'{name} gable diagonal brace', (side * w * 0.37, front - 0.16, body_h + 1.3),
              (side * 0.06, front - 0.16, body_h + 3.0), 0.16, WOOD, seed=seed + 91)
    _gable_roof(root, name, w + 1.8, d + 1.8, body_h + 1.32, 3.8 + min(1.2, w * 0.035),
                roof, dormers=dormers, seed=seed + 100)
    _chimney(root, f'{name} chimney', w * 0.29, d * 0.20, body_h + 2.35, height=3.7)
    _sign(root, f'{name} shop sign', front - 0.22, body_h + 0.25, width=min(3.5, w * 0.32))
    return front, body_h


def _shopfront_dressing(root, name, w, d, body_h, *, awning=('cloth_blue', 'cloth_cream'), goods=()):
    front = -d * 0.5
    _awnings(root, f'{name} awning', min(w - 1.4, 10.0), front - 0.08, 4.65, awning,
             depth=min(3.2, d * 0.30))
    for i, item in enumerate(goods):
        x = (i - (len(goods) - 1) * 0.5) * 1.35
        _box(root, f'{name} front counter {i + 1}', (x, front - d * 0.33, 1.5), (1.45, 1.05, 1.05), WOOD, 0.055, seed=i)
        _box(root, f'{name} goods crate {i + 1}', (x, front - d * 0.33, 2.16), (1.05, 0.66, 0.20), TRIM, 0.025, seed=i + 1)
        if item == 'potion':
            _bottle(root, f'{name} display vial {i + 1}', x, front - d * 0.33, 2.28, ["magic_green", "magic_blue", "magic_purple"][i % 3])
        else:
            _box(root, f'{name} display bundle {i + 1}', (x, front - d * 0.33, 2.43), (0.58, 0.52, 0.36), item, 0.07, seed=i)
    _sign(root, f'{name} street crest', front - 0.3, 5.5, width=min(3.0, w * 0.32))


def _bottle(root, name, x, y, z, color):
    obj = ck.lathe(name, [(0.0, 0.0), (0.28, 0.0), (0.34, 0.22), (0.31, 0.55),
                          (0.16, 0.72), (0.12, 0.95), (0.0, 0.95)],
                   segments=12, material=color, center=(x, y, z))
    _own(obj, root)
    ck.lathe(f'{name} stopper', [(0.13, 0.90), (0.16, 0.96), (0.13, 1.08), (0, 1.08)],
             segments=10, material=GOLD, center=(x, y, z))


def build_house(lm: dict, col, seed=1):
    rng = random.Random(seed)
    name = lm.get('id', 'house')
    root = _root(name, col)
    w, d = lm.get('footprint', [12, 10])
    stories = int(lm.get('stories', 2))
    roof_mat = lm.get('roof_material', ROOFS[seed % len(ROOFS)])
    wall = STONE if lm.get('wall_style') == 'stone' else PLASTER
    _, body_h = _building_shell(root, name, float(w), float(d), stories, wall=wall,
                                roof=roof_mat, seed=seed, dormers=max(1, stories))
    if name == 'armory_house' or lm.get('role') == 'armory':
        _shopfront_dressing(root, name, w, d, body_h, awning=('cloth_red', 'cloth_cream'), goods=('metal_iron', 'metal_gold'))
        _weapon_rack(root, name, -w * 0.5 + 1.2, -d * 0.3, 0.1)
    else:
        _barrel(root, f'{name} front barrel', -w * 0.58, -d * 0.68, 0.0, seed=seed)
        _barrel(root, f'{name} herb keg', w * 0.58, -d * 0.66, 0.0, radius=0.42, height=0.86, seed=seed + 1)
    return root


def _weapon_rack(root, name, x, y, z):
    _box(root, f'{name} weapon display', (x, y, 2.0), (2.5, 0.45, 2.5), WOOD, 0.05)
    for xx in (-0.9, 0, 0.9):
        _beam(root, f'{name} rack sword blade', (x + xx, y - 0.30, 1.15), (x + xx, y - 0.30, 3.0), 0.11, TRIM, depth=0.08)
        _beam(root, f'{name} rack sword guard', (x + xx - 0.30, y - 0.32, 1.75), (x + xx + 0.30, y - 0.32, 1.75), 0.12, GOLD)


def build_blacksmith(lm: dict, col):
    root = _root('blacksmith', col)
    w, d = lm.get('footprint', [26, 20])
    _, body_h = _building_shell(root, 'blacksmith forge hall', w, d, int(lm.get('stories', 2)),
                                wall=STONE, roof=RED_ROOF, seed=810, dormers=2)
    _shopfront_dressing(root, 'blacksmith', w, d, body_h,
                        awning=('cloth_blue', 'cloth_cream'), goods=('metal_iron', 'metal_gold', 'metal_iron'))
    front = -d * 0.5
    # Hot open forge bay with an actual hearth, bellows, quench trough and anvil.
    _box(root, 'blacksmith open forge arch', (-w * 0.31, front - 0.42, 2.45), (5.7, 0.75, 4.2), FOUNDATION, 0.09)
    _box(root, 'blacksmith forge mouth', (-w * 0.31, front - 0.84, 2.25), (3.0, 0.12, 2.7), IRON, 0.035)
    _box(root, 'blacksmith fire core', (-w * 0.31, front - 0.93, 2.2), (1.75, 0.08, 1.38), 'fire_glow', 0.02)
    _chimney(root, 'blacksmith great chimney', -w * 0.30, 0.5, body_h + 4.0, height=12.0, glow=True)
    _box(root, 'blacksmith work anvil foot', (w * 0.04, front - 1.45, 0.62), (1.25, 1.4, 1.15), FOUNDATION, 0.10)
    _box(root, 'blacksmith anvil', (w * 0.04, front - 1.45, 1.38), (2.4, 1.0, 0.48), IRON, 0.13)
    for x in (w * 0.27, w * 0.39):
        _weapon_rack(root, 'blacksmith rack', x, front - 0.85, 0.0)
    _box(root, 'blacksmith water quench trough', (w * 0.30, -d * 0.16, 0.60), (4.8, 2.0, 0.8), WOOD, 0.12)
    _box(root, 'blacksmith quench water', (w * 0.30, -d * 0.16, 1.03), (4.2, 1.46, 0.08), 'water', 0.02)
    for i in range(3):
        _barrel(root, f'blacksmith coal barrel {i + 1}', -w * 0.45 + i * 1.2, -d * 0.18, 0.0, radius=0.50, height=0.95, seed=i)
    return root


def build_guild_hall(lm: dict, col):
    root = _root('guild_hall', col)
    w, d = lm.get('footprint', [30, 22])
    _, body_h = _building_shell(root, 'guild civic hall', w, d, int(lm.get('stories', 3)),
                                wall=PLASTER, roof=NAVY_ROOF, seed=911, dormers=3, body_h=15.0)
    # Two intersecting gables, stepped corner turret and a broad balcony.
    wing = bpy.data.objects.new('guild cross gable pivot', None)
    col.objects.link(wing)
    wing.parent = root
    wing.matrix_parent_inverse = Matrix.Identity(4)
    wing.rotation_euler.z = math.radians(90)
    _gable_roof(wing, 'guild cross wing', d * 0.72, w * 0.68, body_h + 1.4, 5.1, BLUE_ROOF, dormers=2, seed=927)
    _box(root, 'guild balcony slab', (0, -d * 0.5 - 1.15, 9.6), (w * 0.74, 2.4, 0.48), TRIM, 0.08)
    _box(root, 'guild balcony rail cap', (0, -d * 0.5 - 2.18, 10.65), (w * 0.74, 0.18, 0.16), WOOD, 0.04)
    for i in range(13):
        x = -w * 0.37 + i * w * 0.74 / 12
        _box(root, 'guild balcony baluster', (x, -d * 0.5 - 2.18, 10.1), (0.12, 0.12, 1.0), TRIM, 0.025, seed=i)
    for side in (-1, 1):
        _box(root, 'guild hall standard pole', (side * (w * 0.34), -d * 0.5 - 2.3, 13.0), (0.18, 0.18, 7.0), GOLD, 0.025)
        _banner(root, 'guild blue standard', side * (w * 0.34), -d * 0.5 - 2.42, 15.6, 2.2, 5.4)
    tx, ty = w * 0.40, d * 0.30
    _own(ck.lathe('guild corner turret', [(2.0, 0), (2.0, 13), (2.2, 13.4), (2.0, 13.8)],
                  segments=32, material=STONE, center=(tx, ty, 0)), root)
    _conical_roof(root, 'guild turret cap', tx, ty, 13.8, 2.2, 5.8, ROOF)
    for i in range(4):
        z = 4.0 + i * 2.5
        _window(root, f'guild turret lancet {i + 1}', tx, ty - 2.01, z, w=0.58, h=1.55, shutter=False, seed=i + 30)
    for x in (-w * 0.30, w * 0.30):
        _barrel(root, 'guild notice-post drum', x, -d * 0.73, 0, radius=0.66, height=1.4)
    return root


def _banner(root, name, x, y, z, width, height):
    verts = [(x - width * 0.5, y, z), (x + width * 0.5, y, z),
             (x + width * 0.5, y - 0.14, z - height), (x, y - 0.14, z - height + 0.45),
             (x - width * 0.5, y, z - height)]
    _mesh(root, name, verts, [(0, 1, 2, 3, 4)], 'banner_emblem', uv='unit')
    _beam(root, f'{name} top staff', (x - width * 0.65, y, z + 0.14), (x + width * 0.65, y, z + 0.14), 0.13, GOLD)
    _box(root, f'{name} sun crest', (x, y - 0.22, z - height * 0.48), (0.62, 0.08, 0.70), GOLD, 0.13)


def _conical_roof(root, name, x, y, z, radius, height, mat):
    obj = ck.lathe(name, [(radius * 1.10, 0), (radius, height * 0.12), (radius * 0.75, height * 0.42),
                          (radius * 0.48, height * 0.68), (radius * 0.23, height * 0.88), (0, height)],
                   segments=32, material=mat, center=(x, y, z))
    _own(obj, root)
    ck.lathe(f'{name} copper finial', [(0.28, height - 0.20), (0.12, height), (0.0, height + 1.45)],
             segments=16, material=GOLD, center=(x, y, z))


def build_tavern(lm: dict, col):
    root = _root('tavern', col)
    w, d = lm.get('footprint', [20, 16])
    _, body_h = _building_shell(root, 'tavern', w, d, int(lm.get('stories', 2)),
                                wall=PLASTER, roof=RED_ROOF, seed=650, dormers=2, body_h=11.0)
    _shopfront_dressing(root, 'tavern', w, d, body_h, awning=('cloth_cream', 'cloth_red'))
    _barrel(root, 'tavern cask A', -w * 0.70, -d * 0.56, 0, radius=0.72, height=1.35, seed=1)
    _barrel(root, 'tavern cask B', w * 0.68, -d * 0.60, 0, radius=0.60, height=1.18, seed=2)
    _table(root, 'tavern street table', -w * 0.36, -d * 0.9, 0.0)
    _table(root, 'tavern street table', w * 0.40, -d * 0.92, 0.0)
    _sign(root, 'tavern hanging sign', -d * 0.60, 6.4, width=3.3, tint=RED_ROOF)
    return root


def _table(root, name, x, y, z):
    _box(root, f'{name} top', (x, y, z + 1.0), (2.0, 1.65, 0.18), WOOD_LIGHT, 0.055)
    for dx in (-0.72, 0.72):
        for dy in (-0.5, 0.5):
            _box(root, f'{name} leg', (x + dx, y + dy, z + 0.48), (0.14, 0.14, 0.98), WOOD, 0.025)
    _box(root, f'{name} bench', (x, y - 1.2, z + 0.48), (2.2, 0.35, 0.18), WOOD, 0.035)


def build_potion_shop(lm: dict, col):
    root = _root('potion_shop', col)
    w, d = lm.get('footprint', [16, 14])
    _, body_h = _building_shell(root, 'apothecary', w, d, int(lm.get('stories', 2)),
                                wall=PLASTER, roof=GREEN_ROOF, seed=1276, dormers=2)
    _shopfront_dressing(root, 'apothecary', w, d, body_h,
                        awning=('cloth_green', 'cloth_cream'), goods=('potion', 'potion', 'potion'))
    # Herb-drying rails and racks of coloured stoppered glass catch the sun.
    front = -d * 0.5
    for row in range(3):
        y = -d * 0.16 + row * 1.15
        _beam(root, 'herb drying rail', (w * 0.55, y, 2.2 + row * 0.62),
              (w * 0.92, y, 2.2 + row * 0.62), 0.11, WOOD)
        for i in range(4):
            x = w * 0.59 + i * 0.62
            _beam(root, 'hanging herb stem', (x, y, 2.1 + row * 0.62), (x, y, 1.45 + row * 0.62), 0.08, 'grass_ground')
            _box(root, 'tied herb bundle', (x, y - 0.03, 1.70 + row * 0.62), (0.28, 0.18, 0.62), 'grass_ground', 0.06, seed=i + row)
    _chimney(root, 'alchemist flue', -w * 0.35, d * 0.2, body_h + 2.3, height=5.3)
    _own(ck.lathe('apothecary green alembic', [(0.65, 0), (0.85, 0.35), (0.82, 1.35), (0.40, 1.7),
                                               (0.36, 2.8), (0.08, 3.6), (0, 3.6)],
                  segments=24, material='magic_green', center=(w * 0.43, d * 0.16, 1.1)), root)
    _box(root, 'apothecary glasshouse planter', (w * 0.67, -d * 0.55, 0.72), (2.5, 2.2, 1.35), FOUNDATION, 0.08)
    for i in range(7):
        x = w * 0.45 + i * 0.62
        _box(root, 'greenhouse glass shard', (x, -d * 0.58, 1.53), (0.42, 0.075, 1.18), BLUE_GLASS, 0.025)
    return root


def build_gazebo(lm: dict, col):
    root = _root('well_gazebo', col)
    w, d = lm.get('footprint', [7, 7])
    cx, cy = 0.0, 0.0
    _own(ck.lathe('gazebo octagonal dais', [(5.3, 0), (5.5, 0.4), (5.1, 0.7), (0, 0.7)],
                  segments=8, material=TRIM, center=(cx, cy, 0)), root)
    radius = min(w, d) * 0.55
    for i in range(8):
        a = math.tau * i / 8
        x, y = radius * math.cos(a), radius * math.sin(a)
        _own(ck.lathe('gazebo carved column', [(0.52, 0), (0.38, 0.4), (0.35, 4.5), (0.53, 4.9), (0.7, 5.1)],
                      segments=24, material=STONE, center=(x, y, 0.7)), root)
        _own(ck.lathe('gazebo capital', [(0.48, 0), (0.62, 0.12), (0.42, 0.24)],
                      segments=24, material=GOLD, center=(x, y, 5.45)), root)
    for i in range(8):
        a = math.tau * i / 8
        b = math.tau * (i + 1) / 8
        _beam(root, 'gazebo ring beam', (radius * math.cos(a), radius * math.sin(a), 5.75),
              (radius * math.cos(b), radius * math.sin(b), 5.75), 0.4, WOOD)
    _own(ck.lathe('gazebo blue pavilion roof', [(radius + 0.7, 0), (radius * 0.78, 1.8),
                                                 (radius * 0.45, 3.5), (0, 5.0)],
                  segments=8, material=BLUE_ROOF, center=(cx, cy, 5.9)), root)
    _own(ck.lathe('gazebo roof finial', [(0.30, 0), (0.12, 0.8), (0, 1.6)],
                  segments=16, material=GOLD, center=(cx, cy, 10.8)), root)
    _own(ck.lathe('gazebo well basin', [(1.5, 0), (1.5, 0.8), (1.15, 0.95), (1.05, 0.1)],
                  segments=40, material=TRIM, center=(0, 0, 0.65)), root)
    _own(ck.lathe('gazebo well water', [(0, 0), (1.03, 0)], segments=40,
                  material='water', center=(0, 0, 1.52)), root)
    return root


def build_market(lm: dict, col):
    root = _root('market_square', col)
    center = Vector(lm.get('center', (0, 0)))
    palette = [('cloth_red', 'cloth_cream'), ('cloth_blue', 'cloth_cream'),
               ('cloth_green', 'cloth_cream'), ('cloth_blue', 'cloth_red')]
    featured_cart = lm.get('featured_cart_stall', {})
    for row_index, row in enumerate(lm.get('stall_rows', [])):
        a, b = (Vector(p) for p in row)
        count = int(lm.get('stalls_per_row', 4))
        direction = (b - a).normalized()
        for i in range(count):
            p = a.lerp(b, (i + 0.5) / count) - center
            name = f'market stall {row_index + 1}-{i + 1}'
            yaw = math.atan2(direction.y, direction.x) - math.pi * 0.5
            if featured_cart.get('slot') == f'{row_index + 1}-{i + 1}':
                _import_quaternius_stall_cart(
                    root, col, name, p.x, p.y, yaw, float(featured_cart.get('scale', 2.0)),
                )
            else:
                _market_stall(root, name, p.x, p.y, yaw,
                              palette[(i + row_index) % len(palette)], row_index * 7 + i)
    return root


def _import_quaternius_stall_cart(root, col, name, x, y, yaw, scale):
    """Replace one procedural stall with the source-tracked Quaternius CC0 cart."""
    if not QUATERNIUS_STALL_CART.is_file():
        raise FileNotFoundError(f'Missing licensed market-stall source: {QUATERNIUS_STALL_CART}')

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(
        filepath=str(QUATERNIUS_STALL_CART),
        import_pack_images=True,
        import_select_created_objects=True,
    )
    imported = [obj for obj in bpy.data.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == 'MESH']
    if len(meshes) != 1:
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        raise RuntimeError(
            f'Expected one mesh in {QUATERNIUS_STALL_CART.name}; received {len(meshes)}.'
        )

    cart = meshes[0]
    for obj in imported:
        if obj is not cart:
            bpy.data.objects.remove(obj, do_unlink=True)
    ck.normalize_imported_gltf_prop_attributes(cart)
    for old_collection in list(cart.users_collection):
        old_collection.objects.unlink(cart)
    col.objects.link(cart)
    cart.name = f'{name} Quaternius CC0 stall cart'
    cart.parent = root
    cart.matrix_parent_inverse = Matrix.Identity(4)
    cart.location = (x, y, 0)
    cart.rotation_euler.z = yaw
    cart.scale = (scale, scale, scale)
    if not cart.data.materials:
        raise RuntimeError(f'{cart.name} imported without its PBR materials.')
    return cart


def _market_stall(root, name, x, y, yaw, colors, seed):
    # Put the stall in its own transformed child so the street layout stays in
    # JSON while the counter still faces the aisle consistently.
    stall = bpy.data.objects.new(name + ' pivot', None)
    stall.empty_display_type = 'PLAIN_AXES'
    stall.location = (x, y, 0)
    stall.rotation_euler.z = yaw
    stall.parent = root
    stall.matrix_parent_inverse = Matrix.Identity(4)
    _box(stall, f'{name} counter carcass', (0, 0, 1.13), (8.0, 4.1, 1.65), WOOD, 0.09, seed=seed)
    _box(stall, f'{name} counter stone lip', (0, -0.12, 2.0), (8.3, 4.38, 0.25), TRIM, 0.055, seed=seed + 1)
    # Panelled front with carved brass brackets and lattice shelves.
    for i in range(7):
        px = -3.38 + i * 1.12
        _box(stall, f'{name} counter panel', (px, -2.12, 1.05), (0.86, 0.10, 1.1), WOOD_LIGHT, 0.04, seed=seed + i)
        _box(stall, f'{name} panel peg', (px, -2.20, 1.42), (0.06, 0.05, 0.58), GOLD, 0.02, seed=seed + i)
    for px in (-3.6, 3.6):
        for py in (-1.75, 1.75):
            _box(stall, f'{name} canopy post', (px, py, 3.5), (0.22, 0.22, 4.0), WOOD, 0.035, seed=seed)
    # Crown roof is made of separate cloth strips so alternating colours remain
    # crisp under the warm key light and texture compression.
    n = 12
    for i in range(n):
        x0, x1 = -4.05 + i * 8.1 / n, -4.05 + (i + 1) * 8.1 / n
        verts = [(x0, -2.25, 4.72), (x1, -2.25, 4.72), (x1, 2.25, 4.72), (x0, 2.25, 4.72),
                 (x0, 2.70, 4.25), (x1, 2.70, 4.25)]
        _mesh(stall, f'{name} canopy stripe {i + 1}', verts, [(0, 1, 2, 3), (3, 2, 5, 4)],
              colors[i % len(colors)], uv='unit', seed=seed + i)
    for i in range(5):
        px = -3.2 + i * 1.6
        _box(stall, f'{name} produce bin', (px, -0.70, 2.25), (1.2, 1.55, 0.42), FOUNDATION, 0.04, seed=i)
        for j in range(3):
            colr = ('magic_green', 'roof_tile_red', 'metal_gold')[(i + j) % 3]
            obj = ck.lathe(f'{name} produce {i}-{j}', [(0.34, 0), (0.39, 0.14), (0.28, 0.44), (0, 0.44)],
                           segments=10, material=colr, center=(px - 0.3 + j * 0.30, -0.8, 2.48))
            _own(obj, stall, seed=seed + j)
    _sign(stall, f'{name} hanging crest', -2.4, 4.3, width=2.5)


def _banner_placeholder():
    return None


def build_townhouse_cluster(layout: dict, col):
    """Optional explicit helper for tools; assembler normally expands groups."""
    roots = []
    for i, center in enumerate(layout.get('centers', [])):
        spec = dict(layout, center=center, id=f"{layout.get('id', 'house')}_{i + 1}")
        roots.append(build_house(spec, col, 100 + i))
    return roots

