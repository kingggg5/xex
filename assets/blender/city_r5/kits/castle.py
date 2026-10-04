"""R5 original Magic Castle, ceremonial stairs and north-rim arcades."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import citykit as ck  # noqa: E402
import buildings as bld  # noqa: E402
import landmarks as lmkit  # noqa: E402

STONE, TRIM, FOUNDATION = 'stone_wall_warm', 'stone_trim_carved', 'stone_foundation'
PLASTER, WOOD, GOLD = 'plaster_cream', 'timber_dark', 'metal_gold'
BLUE_ROOF, NAVY_ROOF = 'roof_slate_blue', 'roof_slate_navy'
BLUE_GLASS, VIOLET = 'glass_window_blue', 'magic_purple'


def _root(name, col):
    obj = bpy.data.objects.new(f'kit_{name}', None)
    obj.empty_display_type = 'PLAIN_AXES'
    col.objects.link(obj)
    return obj


def _box(root, name, center, size, mat, bevel=0.055, seed=0, rot_z=0.0):
    obj = ck.box(name, center, size, mat, rot_z=rot_z)
    if bevel:
        ck.bevel(obj, min(bevel, min(size) * 0.16), segments=2, angle_deg=34)
    ck.uv_box(obj)
    ck.vertex_paint(obj, seed=seed, ground_z=0.02, cavity=0.32, edge=0.16, jitter=0.026)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _lathe(root, name, profile, mat, center=(0, 0, 0), segments=48):
    obj = ck.lathe(name, profile, segments=segments, material=mat, center=center)
    ck.uv_box(obj)
    ck.vertex_paint(obj, seed=len(name), ground_z=0.02, cavity=0.25, edge=0.13, jitter=0.025)
    obj.parent = root
    obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _beam(root, name, start, end, width, mat, depth=None):
    return bld._beam(root, name, start, end, width, mat, depth=depth)


def _arch_band(root, name, cx, y, spring_z, radius, thickness, mat, segments=16):
    # Stone voussoirs around a pointed arch; the crown is peaked rather than
    # circular to keep the gothic silhouette from reading as a flat box.
    for i in range(segments):
        a0 = math.pi * (i / segments)
        a1 = math.pi * ((i + 1) / segments)
        p0 = (cx + radius * math.cos(a0), y, spring_z + radius * math.sin(a0))
        p1 = (cx + radius * math.cos(a1), y, spring_z + radius * math.sin(a1))
        _beam(root, f'{name} carved arch stone', p0, p1, thickness, mat, depth=thickness * 1.25)


def _window(root, x, y, z, height=5.0, width=1.55):
    # Deep stone reveal, blue stained lancet and gold mullion network.
    _box(root, 'castle window reveal', (x, y, z), (width + 0.78, 0.48, height + 0.8), TRIM, 0.085)
    _box(root, 'castle window shadow', (x, y - 0.28, z), (width + 0.16, 0.10, height + 0.14), FOUNDATION, 0.03)
    _box(root, 'castle stained glass', (x, y - 0.36, z), (width, 0.07, height), BLUE_GLASS, 0.02)
    _box(root, 'castle gold mullion', (x, y - 0.43, z), (0.13, 0.05, height), GOLD, 0.01)
    for yy in (-1.2, 0.0, 1.2):
        if abs(yy) < height * 0.47:
            _box(root, 'castle window lead', (x, y - 0.43, z + yy), (width, 0.05, 0.10), GOLD, 0.01)


def _banner(root, name, x, y, z, w=2.8, h=7.4):
    verts = [(x - w * 0.5, y, z), (x + w * 0.5, y, z),
             (x + w * 0.5, y - 0.12, z - h), (x, y - 0.12, z - h + 0.55), (x - w * 0.5, y, z - h)]
    mesh = ck.new_object(name, verts, [(0, 1, 2, 3, 4), (4, 3, 2, 1, 0)], 'banner_emblem')
    ck.uv_unit(mesh); ck.vertex_paint(mesh, ground_z=None, jitter=0.0)
    mesh.parent = root; mesh.matrix_parent_inverse = Matrix.Identity(4)
    _beam(root, f'{name} gilded staff', (x - w * 0.62, y, z + 0.12),
          (x + w * 0.62, y, z + 0.12), 0.17, GOLD)
    _box(root, f'{name} house sigil', (x, y - 0.21, z - h * 0.50), (0.68, 0.08, 0.76), GOLD, 0.12)


def _tower(root, name, x, y, height, radius, *, roof=BLUE_ROOF, banners=True):
    body_h = height * 0.72
    _lathe(root, f'{name} rounded ashlar body', [(radius * 0.78, 0), (radius, 0.9),
        (radius * 0.98, body_h * 0.30), (radius * 0.84, body_h * 0.74),
        (radius * 0.66, body_h), (0, body_h)], STONE, (x, y, 0), 48)
    for z in (0.7, body_h * 0.33, body_h * 0.68, body_h - 0.35):
        rr = radius * (0.99 - 0.30 * z / body_h)
        _lathe(root, f'{name} carved belt', [(rr, z), (rr * 1.12, z + 0.24), (rr, z + 0.52)], TRIM,
               (x, y, 0), 48)
    for side in range(8):
        a = side * math.tau / 8 - math.pi / 2
        rr = radius * 0.84
        px, py = x + rr * math.cos(a), y + rr * math.sin(a)
        z = body_h * 0.57
        obj = ck.box(f'{name} lancet', (px, py, z), (0.85, 0.14, 3.6), BLUE_GLASS, rot_z=a + math.pi / 2)
        ck.uv_box(obj); ck.vertex_paint(obj, ground_z=None, seed=side, jitter=0.0)
        obj.parent = root; obj.matrix_parent_inverse = Matrix.Identity(4)
    _lathe(root, f'{name} spire roof', [(radius * 1.25, body_h), (radius * 1.12, body_h + 0.9),
        (radius * 0.82, height * 0.93), (radius * 0.38, height * 1.30), (0, height * 1.48)],
        roof, (x, y, 0), 48)
    _lathe(root, f'{name} finial', [(radius * 0.18, height * 1.38), (radius * 0.10, height * 1.50),
        (0, height * 1.68)], GOLD, (x, y, 0), 20)
    for i in range(8):
        a = i * math.tau / 8
        _box(root, f'{name} parapet merlon', (x + radius * math.cos(a), y + radius * math.sin(a), body_h + 0.45),
             (0.88, 0.88, 0.94), TRIM, 0.04, seed=i)
    if banners:
        _banner(root, f'{name} royal banner', x, y - radius - 0.18, body_h * 0.74,
                w=max(1.8, radius * 0.92), h=max(4.6, height * 0.34))


def build_castle(lm: dict, col):
    root = _root('magic_castle', col)
    w, d = lm.get('footprint', (64, 36))
    # Assembled root receives the +9 m terrace level from layout.json; all
    # authored parts begin at local z=0 so they stand on that terrace.
    base_z = 0.0
    # Layered terrace and stepped retaining wall; central nave, lateral halls,
    # and rear cloister are separate masses so the silhouette stays readable.
    _box(root, 'castle lower plinth', (0, 0, base_z + 0.75), (w + 10, d + 11, 1.5), FOUNDATION, 0.12)
    _box(root, 'castle plinth moulding', (0, 0, base_z + 1.65), (w + 7, d + 8, 0.5), TRIM, 0.09)
    _box(root, 'castle terrace paving', (0, 0, base_z + 2.05), (w + 5, d + 6, 0.42), 'plaza_flagstone', 0.06)
    # Main hall is set on the north half, with the monumental doorway on its south face.
    hall_y = 3.0
    _box(root, 'castle nave stone body', (0, hall_y, base_z + 17.0), (39, 29, 29), STONE, 0.12)
    _box(root, 'castle broad belt course', (0, hall_y - 14.72, base_z + 10.0), (39.8, 0.55, 0.85), TRIM, 0.09)
    _box(root, 'castle upper cornice', (0, hall_y, base_z + 31.9), (41, 31, 1.2), TRIM, 0.12)
    bld._gable_roof(root, 'castle central nave slate', 43.0, 34.0, base_z + 32.5, 14.5, NAVY_ROOF, dormers=4, seed=610)
    for side in (-1, 1):
        wing_x = side * 27
        _box(root, 'castle side wing body', (wing_x, hall_y + 1.0, base_z + 11.7), (18, 36, 21), STONE, 0.11)
        bld._gable_roof(root, 'castle side wing roof', 21.0, 39.0, base_z + 22.3, 9.0,
                        BLUE_ROOF, x0=wing_x, y0=hall_y + 1.0, dormers=2, seed=620 + side)
        _box(root, 'castle wing foundation', (wing_x, hall_y, base_z + 1.1), (20, 39, 1.8), FOUNDATION, 0.10)
        # Buttresses rise all the way from the terrace to the upper parapet.
        for y in (-10, 1, 12):
            _beam(root, 'castle wing buttress', (wing_x + side * 8.4, y, base_z + 2.4),
                  (wing_x + side * 6.1, y, base_z + 30), 0.95, TRIM, depth=0.82)
            _box(root, 'castle buttress capital', (wing_x + side * 6.0, y, base_z + 30.5),
                 (2.3, 2.1, 0.65), GOLD, 0.08)
        for z in (base_z + 8.4, base_z + 18.5):
            for xoff in (-5.7, 0, 5.7):
                _window(root, wing_x + xoff, -15.1, z, 4.8, 1.48)
        # Eight peripheral spires bring the varied skyline from the concept sheet.
        _tower(root, 'castle outer round tower', wing_x, hall_y - 13.0, 31, 4.8,
               roof=BLUE_ROOF, banners=True)
        _tower(root, 'castle rear slim tower', wing_x, hall_y + 15.0, 28, 3.6,
               roof=NAVY_ROOF, banners=False)
        _tower(root, 'castle front slim tower', wing_x * 0.60, -15.5, 24, 3.1,
               roof=BLUE_ROOF, banners=True)
    _box(root, 'castle rear cloister', (0, 17, base_z + 7.8), (34, 8, 15.6), FOUNDATION, 0.1)
    # South facade: portal reveal, 11 m high original pointed arch, rose tracery,
    # six stained lancets, paired standards and a bronze relief above the door.
    front_y = hall_y - 14.7
    _box(root, 'castle portal deep recess', (0, front_y - 0.34, base_z + 7.0), (12.0, 0.42, 13.8), FOUNDATION, 0.08)
    _box(root, 'castle violet portal core', (0, front_y - 0.61, base_z + 6.5), (8.0, 0.12, 11.5), VIOLET, 0.04)
    for side in (-1, 1):
        _box(root, 'castle portal jamb', (side * 5.25, front_y - 0.66, base_z + 7.2), (1.2, 1.0, 14.2), TRIM, 0.08)
        _arch_band(root, 'castle pointed portal', 0, front_y - 0.77, base_z + 12.3, 5.7, 0.82, TRIM, 24)
        _banner(root, 'castle nave standard', side * 11.0, front_y - 0.55, base_z + 28.0, 3.2, 9.0)
    _box(root, 'castle rose window surround', (0, front_y - 0.34, base_z + 25.3), (9.0, 0.62, 9.0), FOUNDATION, 0.10)
    _lathe(root, 'castle rose window glass', [(0, 0), (4.0, 0.0)], BLUE_GLASS,
           (0, front_y - 0.72, base_z + 25.3), 32)
    # Gold tracery radiates from a central sunstone; lines remain distinct at distance.
    for i in range(16):
        a = math.tau * i / 16
        _beam(root, 'castle rose window spoke', (0, front_y - 0.80, base_z + 25.3),
              (3.8 * math.cos(a), front_y - 0.80, base_z + 25.3 + 3.8 * math.sin(a)), 0.16, GOLD)
    for radius in (2.0, 3.1, 4.0):
        _lathe(root, 'castle rose window brass ring', [(radius - 0.12, 0), (radius + 0.12, 0.04)], GOLD,
               (0, front_y - 0.82, base_z + 25.3), 64)
    for x in (-15.5, -9.8, 9.8, 15.5):
        _window(root, x, front_y - 0.35, base_z + 20.5, 7.2, 1.55)
        _window(root, x, front_y - 0.35, base_z + 9.8, 6.4, 1.62)
    for side in (-1, 1):
        for i in range(4):
            x = side * (5.8 + i * 1.9)
            _beam(root, 'castle facade buttress', (x, front_y - 0.48, base_z + 2.2),
                  (x * 0.96, front_y - 0.48, base_z + 29.5), 0.74, TRIM, depth=0.58)
    # Central high spire: terrace level 9 + local tip 63 = 72 m.
    lmkit._spire(root, 'magic castle central spire', 0, 7.0, 27.0, 34.0, 4.1,
                 mat=NAVY_ROOF, windows=5)
    # A quartet of smaller roof spires and needle finials breaks the nave ridge.
    for x, y, h, r in [(-12, -1, 24, 2.4), (12, -1, 24, 2.4), (-12, 12, 21, 2.2), (12, 12, 21, 2.2)]:
        lmkit._spire(root, 'castle nave corner spire', x, y, base_z + 31.5, h, r,
                     mat=BLUE_ROOF, windows=2)
    return root


def build_grand_stairs(lm: dict, col):
    root = _root('grand_stairs', col)
    p0, p1 = lm['from'], lm['to']
    start = min(p0[1], p1[1])
    length = abs(p1[1] - p0[1])
    rise = float(lm.get('rise', 9.0))
    width = float(lm.get('width', 16.0))
    # Root is placed at the midpoint of `from`/`to`; build each flight around
    # that local origin and leave broad landings at +/−6 m.
    y_mid = (p0[1] + p1[1]) * 0.5
    cursor = start - y_mid
    flights = 3
    run_per_flight = length / flights
    steps = 20
    for flight in range(flights):
        local_start = cursor + flight * run_per_flight
        base_z = flight * rise / flights
        for i in range(steps):
            t = (i + 1) / steps
            y = local_start + t * run_per_flight
            z = base_z + t * rise / flights
            _box(root, 'castle grand stair tread', (0, y, z - 0.11),
                 (width + 1.2, run_per_flight / steps + 0.08, 0.24), 'stone_trim_carved', 0.045, seed=flight * steps + i)
        if flight < flights - 1:
            y = local_start + run_per_flight
            z = (flight + 1) * rise / flights
            _box(root, 'castle stair landing', (0, y, z - 0.20), (width + 5.0, 4.8, 0.42), 'plaza_flagstone', 0.08)
        # Heavy handrails, balusters and lamp pylons at both edges of each flight.
        for side in (-1, 1):
            x = side * (width * 0.5 + 0.85)
            _beam(root, 'castle stair stone handrail', (x, local_start, base_z + 0.8),
                  (x, local_start + run_per_flight, base_z + rise / flights + 0.8), 0.65, TRIM, depth=0.58)
            for i in range(9):
                t = i / 8
                y = local_start + t * run_per_flight
                z = base_z + t * rise / flights + 0.27
                _lathe(root, 'castle stair baluster', [(0.17, 0), (0.24, 0.2), (0.14, 0.44), (0.22, 0.68)],
                       TRIM, (x, y, z), 12)
            for y in (local_start + 1.0, local_start + run_per_flight - 1.0):
                _lathe(root, 'castle stair lamp foot', [(0.65, 0), (0.8, 0.4), (0.52, 0.82)], FOUNDATION,
                       (x, y, base_z + rise / flights * ((y - local_start) / run_per_flight)), 24)
                _lathe(root, 'castle stair lamp crystal', [(0, 0), (0.38, 0.25), (0.28, 1.2), (0, 1.55)],
                       'magic_blue', (x, y, base_z + 1.0), 16)
    return root


def build_north_arcades(lm: dict, col):
    root = _root('north_arcades', col)
    spans = lm.get('spans', [])
    xs = [p[0] for span in spans for p in span]
    x_center = (min(xs) + max(xs)) * 0.5 if xs else 0.0
    # The assembler positions the root at the mean of the spans; subtract it to
    # keep the authored world coordinates controlled by layout.json.
    y_center = sum(p[1] for span in spans for p in span) / max(1, len(spans) * 2)
    height = 7.0
    for span_index, span in enumerate(spans):
        a, b = span
        lo, hi = sorted((a[0] - x_center, b[0] - x_center))
        count = max(2, int((hi - lo) / 8.0))
        spacing = (hi - lo) / count
        for i in range(count + 1):
            x = lo + i * spacing
            _box(root, 'north arcade square pier', (x, 0, height * 0.5), (1.65, 2.2, height), STONE, 0.09, seed=i)
            _box(root, 'north arcade capital', (x, 0, height - 0.2), (2.35, 2.9, 0.55), TRIM, 0.06, seed=i)
        for i in range(count):
            x0, x1 = lo + i * spacing, lo + (i + 1) * spacing
            spring = 4.5
            radius = (x1 - x0) * 0.5
            _beam(root, 'north arcade arch impost', (x0, -0.05, spring), (x1, -0.05, spring), 0.42, TRIM)
            for half in (-1, 1):
                for seg in range(9):
                    t0, t1 = seg / 9, (seg + 1) / 9
                    xx0 = (x0 + x1) * 0.5 + half * radius * math.cos(math.pi * 0.5 * t0)
                    zz0 = spring + radius * math.sin(math.pi * 0.5 * t0)
                    xx1 = (x0 + x1) * 0.5 + half * radius * math.cos(math.pi * 0.5 * t1)
                    zz1 = spring + radius * math.sin(math.pi * 0.5 * t1)
                    _beam(root, 'north arcade carved arch', (xx0, 0, zz0), (xx1, 0, zz1), 0.36, TRIM, depth=2.2)
        # Capstones, gold finials and a pair of sheltered water pools behind each arcade.
        _box(root, f'north arcade roof cap {span_index}', ((lo + hi) * 0.5, 0, height + 0.42),
             (hi - lo + 3.0, 3.3, 0.68), FOUNDATION, 0.07, seed=span_index)
        for x in (lo + 1.0, hi - 1.0):
            lmkit._spire(root, 'north arcade corner finial', x, 0, height + 0.75, 5.0, 0.65,
                         mat=BLUE_ROOF, windows=0)
    # y is local 0, after place_root the entire arcaded rim sits at layout y.
    return root

