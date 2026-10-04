"""Sunken Temple of Aurel — D2 blockout (Claude level lane, 2026-10-01).

Builds the metric layout from docs/levels/sunken-temple-of-aurel.md with the
texture-forge material library, renders BLENDER REVIEW shots from the game's
own camera framing (ArcRotateCamera radius 13, beta 1.18 rad, vertical FOV
1.02 rad, target 1.65 m above the feet) and exports a GLB plus a layout JSON.

Run from the repo root:
  blender -b --factory-startup --python assets/blender/dungeons/sunken_temple/build_blockout_d2.py -- \
      [--out assets/models/dungeons/sunken-temple/d2-blockout] [--shots planning/evidence/sunken-temple-d2]
      [--samples 64] [--no-render] [--no-export]
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[4]
FORGE = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'textures-forge-r6'
LIVE = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'textures'
TILES = {'grass_ground': 6.0, 'plaza_flagstone': 4.0, 'stone_wall_warm': 2.4, 'stone_foundation': 2.4, 'stone_trim_carved': 1.6,
         'stone_accent_bluegrey': 2.0, 'paver_surface': 2.0, 'cliff_rock': 9.0, 'cobble_path': 2.6}
RNG = random.Random(20261001)
STEP_RISE = 0.16
WALL_H = 7.0
WALL_T = 1.2


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    a = {'out': 'assets/models/dungeons/sunken-temple/d2-blockout', 'shots': 'planning/evidence/sunken-temple-d2',
         'samples': 64, 'render': True, 'export': True, 'device': 'gpu'}
    i = 0
    while i < len(argv):
        key = argv[i].lstrip('-')
        if key == 'no-render':
            a['render'] = False; i += 1
        elif key == 'no-export':
            a['export'] = False; i += 1
        else:
            a[key] = int(argv[i + 1]) if key == 'samples' else argv[i + 1]; i += 2
    a['device'] = str(a['device']).lower()
    for key in ('out', 'shots'):
        p = Path(a[key]); a[key] = p if p.is_absolute() else ROOT / p
    return a


# ----------------------------------------------------------------------------
# Materials (UVs carry metres / tile, so no mapping node is needed for glTF)
# ----------------------------------------------------------------------------

def texture_material(name: str) -> bpy.types.Material:
    folder = FORGE if (FORGE / f'{name}_albedo.png').exists() else LIVE
    mat = bpy.data.materials.new(name)
    mat['tile_m'] = TILES[name]
    mat['texture_source'] = folder.name
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']

    def tex(kind: str, non_color: bool):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(folder / f'{name}_{kind}.png'), check_existing=True)
        node.image.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
        return node

    albedo, normal, orm = tex('albedo', False), tex('normal', True), tex('orm', True)
    links.new(albedo.outputs['Color'], bsdf.inputs['Base Color'])
    split = nodes.new('ShaderNodeSeparateColor')
    links.new(orm.outputs['Color'], split.inputs['Color'])
    links.new(split.outputs['Green'], bsdf.inputs['Roughness'])
    links.new(split.outputs['Blue'], bsdf.inputs['Metallic'])
    nmap = nodes.new('ShaderNodeNormalMap')
    links.new(normal.outputs['Color'], nmap.inputs['Color'])
    links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def flat_material(name: str, color: str, rough=0.5, metal=0.0, emission: str | None = None, strength=0.0,
                  alpha=1.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    rgb = tuple(int(color.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
    bsdf.inputs['Base Color'].default_value = (*[c ** 2.2 for c in rgb], 1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if emission:
        e = tuple(int(emission.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
        bsdf.inputs['Emission Color'].default_value = (*[c ** 2.2 for c in e], 1)
        bsdf.inputs['Emission Strength'].default_value = strength
    if alpha < 1:
        bsdf.inputs['Alpha'].default_value = alpha
    return mat


# ----------------------------------------------------------------------------
# Geometry
# ----------------------------------------------------------------------------

LEVEL: list[bpy.types.Object] = []
WITNESS: list[bpy.types.Object] = []


def link(obj: bpy.types.Object, export=True) -> bpy.types.Object:
    bpy.context.scene.collection.objects.link(obj)
    (LEVEL if export else WITNESS).append(obj)
    return obj


def world_uv(obj: bpy.types.Object) -> None:
    """Box-project world metres / material tile into UVs (same convention as the R5 city uv_box)."""
    mat = obj.data.materials[0] if obj.data.materials else None
    tile = float(mat.get('tile_m', 2.0)) if mat else 2.0
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.verify()
    mw = obj.matrix_world
    rot = mw.to_3x3()
    for face in bm.faces:
        n = (rot @ face.normal).normalized()
        axis = max(range(3), key=lambda i: abs(n[i]))
        for loop in face.loops:
            p = mw @ loop.vert.co
            if axis == 2:
                u, v = p.x, p.y
            elif axis == 0:
                u, v = (p.y if n.x > 0 else -p.y), p.z
            else:
                u, v = (-p.x if n.y > 0 else p.x), p.z
            loop[uv].uv = (u / tile, v / tile)
    bm.to_mesh(obj.data)
    bm.free()


def mesh_object(name: str, bm: bmesh.types.BMesh, mat, smooth=False, export=True) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    mesh.materials.append(mat)
    obj = link(bpy.data.objects.new(name, mesh), export)
    if mat.get('tile_m'):
        world_uv(obj)
    return obj


def box(name, x0, y0, z0, x1, y1, z1, mat, export=True) -> bpy.types.Object:
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 if v.co.x < 0 else x1
        v.co.y = y0 if v.co.y < 0 else y1
        v.co.z = z0 if v.co.z < 0 else z1
    return mesh_object(name, bm, mat, export=export)


def cylinder(name, x, y, z0, z1, r, mat, segments=16, r_top=None, smooth=True) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r if r_top is None else r_top,
                          depth=z1 - z0)
    bmesh.ops.translate(bm, vec=(x, y, (z0 + z1) / 2), verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=smooth)


def layered_wall(name, x0, y0, x1, y1, z0, mats, height=WALL_H, openings=()):
    """Axis-aligned wall from (x0,y0) to (x1,y1) with a foundation course, body and cornice.
    openings: (start, end, open_height) measured along the wall's long axis."""
    along_x = abs(x1 - x0) >= abs(y1 - y0)
    a0, a1 = (min(x0, x1), max(x0, x1)) if along_x else (min(y0, y1), max(y0, y1))
    c = y0 if along_x else x0
    # Junctions overlap by design; a few-mm deterministic offset keeps faces from ever being coplanar
    # (coplanar overlaps render black in Cycles and z-fight in Babylon).
    eps = 0.006 + (sum(map(ord, name)) % 13) * 0.0011
    c += eps if c >= 0 else -eps
    a0, a1 = a0 - 0.017, a1 + 0.017
    spans, cursor = [], a0
    for o0, o1, oh in sorted(openings):
        if o0 > cursor:
            spans.append((cursor, o0, None))
        spans.append((o0, o1, oh))
        cursor = o1
    if cursor < a1:
        spans.append((cursor, a1, None))

    def piece(tag, s0, s1, zz0, zz1, half, mat):
        if along_x:
            box(f'{name}-{tag}', s0, c - half, zz0, s1, c + half, zz1, mat)
        else:
            box(f'{name}-{tag}', c - half, s0, zz0, c + half, s1, zz1, mat)

    for k, (s0, s1, oh) in enumerate(spans):
        if oh is None:
            piece(f'base{k}', s0, s1, z0, z0 + 0.8, WALL_T / 2 + 0.1, mats['base'])
            piece(f'body{k}', s0, s1, z0 + 0.8, z0 + height - 0.35, WALL_T / 2, mats['wall'])
        else:
            piece(f'lintel{k}', s0, s1, z0 + oh, z0 + height - 0.35, WALL_T / 2, mats['wall'])
            piece(f'jamb{k}a', s0 - 0.25, s0 + 0.08, z0, z0 + oh, WALL_T / 2 + 0.12, mats['trim'])
            piece(f'jamb{k}b', s1 - 0.08, s1 + 0.25, z0, z0 + oh, WALL_T / 2 + 0.12, mats['trim'])
        piece(f'cornice{k}', s0, s1, z0 + height - 0.35, z0 + height, WALL_T / 2 + 0.15, mats['trim'])


def stairs(name, x0, x1, y0, y1, z_top, z_bottom, mat):
    """Descending stair along +Y from z_top at y0 to z_bottom at y1 (solid steps, riser STEP_RISE)."""
    n = max(1, round((z_top - z_bottom) / STEP_RISE))
    tread = (y1 - y0) / n
    for i in range(n):
        top = z_top - STEP_RISE * (i + 1)
        box(f'{name}-step{i:02d}', x0, y0 + tread * i, z_bottom - 0.6, x1, y0 + tread * (i + 1), top, mat)
    return {'kind': 'stairs', 'x': [x0, x1], 'y': [y0, y1], 'z': [z_top, z_bottom], 'risers': n,
            'tread_m': round(tread, 3), 'rise_m': STEP_RISE}


def ramp(name, x0, x1, y0, y1, z_top, z_bottom, mat):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 if v.co.x < 0 else x1
        at_start = v.co.y < 0
        v.co.y = y0 if at_start else y1
        surface = z_top if at_start else z_bottom
        v.co.z = (z_bottom - 0.6) if v.co.z < 0 else surface
    mesh_object(name, bm, mat)
    return {'kind': 'ramp', 'x': [x0, x1], 'y': [y0, y1], 'z': [z_top, z_bottom],
            'slope_deg': round(math.degrees(math.atan2(z_top - z_bottom, abs(y1 - y0))), 1)}


def ring(name, cx, cy, r_in, r_out, z0, z1, mat, a0=0.0, a1=math.tau, segments=48):
    bm = bmesh.new()
    count = max(2, int(segments * (a1 - a0) / math.tau))
    rings = []
    for k in range(count + 1):
        a = a0 + (a1 - a0) * k / count
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((cx + ca * r, cy + sa * r, z)) for r, z in
                      ((r_in, z0), (r_out, z0), (r_out, z1), (r_in, z1))])
    for k in range(count):
        a, b = rings[k], rings[k + 1]
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if abs(a1 - a0 - math.tau) > 1e-6:
        bm.faces.new(tuple(reversed(rings[0])))
        bm.faces.new(tuple(rings[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_object(name, bm, mat, smooth=False)


def boulder(name, x, y, z, size, mat):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    sx, sy, sz = size * RNG.uniform(0.8, 1.3), size * RNG.uniform(0.7, 1.1), size * RNG.uniform(0.45, 0.8)
    for v in bm.verts:
        jitter = 1 + RNG.uniform(-0.12, 0.12)
        v.co.x *= sx * jitter; v.co.y *= sy * jitter; v.co.z *= sz * jitter
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(RNG.uniform(0, math.tau), 3, 'Z'), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(x, y, z + sz * 0.45), verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=False)


def pillar(name, x, y, z0, height, mats, radius=0.75):
    box(f'{name}-plinth', x - radius - 0.25, y - radius - 0.25, z0, x + radius + 0.25, y + radius + 0.25, z0 + 0.6, mats['base'])
    cylinder(f'{name}-shaft', x, y, z0 + 0.6, z0 + height - 0.7, radius, mats['trim'], segments=12)
    box(f'{name}-capital', x - radius - 0.3, y - radius - 0.3, z0 + height - 0.7, x + radius + 0.3, y + radius + 0.3, z0 + height, mats['trim'])


def witness(name, x, y, z) -> None:
    """1.8 m player scale witness (render only, never exported)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=0.35)
    for v in bm.verts:
        v.co.z = v.co.z + (1.45 if v.co.z > 0 else 0.35)
    bmesh.ops.translate(bm, vec=(x, y, z), verts=bm.verts)
    mesh_object(name, bm, MATS['witness'], smooth=True, export=False)


# ----------------------------------------------------------------------------
# Layout (see docs/levels/sunken-temple-of-aurel.md)
# ----------------------------------------------------------------------------

MATS: dict[str, bpy.types.Material] = {}


def build_level() -> dict:
    m = MATS
    stone = {'base': m['accent'], 'wall': m['wall'], 'trim': m['trim']}
    sanctum = {'base': m['base'], 'wall': m['accent'], 'trim': m['trim']}
    traversal: list[dict] = []

    # 1 Entrance hall
    box('hall-floor', -8, -16, -0.6, 8, 8, 0.0, m['floor'])
    layered_wall('hall-south', -9.2, -16.6, 9.2, -16.6, 0.0, stone)
    layered_wall('hall-west', -8.6, -16, -8.6, 8, 0.0, stone)
    layered_wall('hall-east', 8.6, -16, 8.6, 8, 0.0, stone)
    layered_wall('hall-north', -9.2, 8.6, 9.2, 8.6, 0.0, stone, openings=[(-3, 3, 4.6)])
    cylinder('portal-dais-1', 0, -12.5, 0.0, 0.16, 2.4, m['trim'], segments=32)
    cylinder('portal-dais-2', 0, -12.5, 0.16, 0.32, 2.0, m['trim'], segments=32)
    ring('portal-arch', 0, -12.5, 1.55, 1.85, 0.32, 0.62, m['bronze'], segments=40)
    portal = cylinder('portal-veil', 0, -12.5, 0.33, 0.36, 1.55, m['portal'], segments=40, smooth=False)
    portal['role'] = 'return_portal'
    for sx in (-6.5, 6.5):
        cylinder(f'brazier-{sx:+.0f}', sx, 5.5, 0.0, 1.1, 0.45, m['bronze'], segments=10)
    traversal.append({'kind': 'floor', 'room': 'entrance_hall', 'x': [-8, 8], 'y': [-16, 8], 'z': 0.0})

    # 2 Descent stair
    box('stair1-landing', -3, 8, -0.6, 3, 8.8, 0.0, m['path'])
    traversal.append(stairs('stair1', -3, 3, 8.8, 15.2, 0.0, -3.2, m['path']))
    layered_wall('stair1-west', -3.6, 8, -3.6, 16, -3.2, stone, height=WALL_H + 3.2)
    layered_wall('stair1-east', 3.6, 8, 3.6, 16, -3.2, stone, height=WALL_H + 3.2)
    box('stair1-foot', -3, 15.2, -3.8, 3, 16, -3.2, m['path'])

    # 3 Flooded colonnade
    box('colonnade-walkway', -6, 16, -3.8, 6, 48, -3.2, m['floor'])
    for side, (x0, x1) in (('west', (-12, -6)), ('east', (6, 12))):
        box(f'channel-{side}-bed', x0, 16, -4.2, x1, 48, -3.6, m['base'])
        box(f'channel-{side}-water', x0, 16, -3.34, x1, 48, -3.3, m['water'])
        box(f'channel-{side}-curb', (x1 - 0.3) if side == 'west' else x0, 16, -3.6, x1 if side == 'west' else (x0 + 0.3), 48, -3.1, m['trim'])
    layered_wall('colonnade-south', -12.6, 15.4, -3, 15.4, -3.2, stone)
    layered_wall('colonnade-south-b', 3, 15.4, 12.6, 15.4, -3.2, stone)
    layered_wall('colonnade-west', -12.6, 16, -12.6, 48, -3.6, stone, height=WALL_H + 0.4)
    layered_wall('colonnade-east', 12.6, 16, 12.6, 48, -3.6, stone, height=WALL_H + 0.4)
    layered_wall('colonnade-north', -12.6, 48.6, 12.6, 48.6, -3.2, stone, openings=[(-3, 3, 4.6)])
    for k in range(5):
        y = 20 + 6.4 * k
        for x in (-6, 6):
            pillar(f'colonnade-pillar-{k}-{x:+.0f}', x, y, -3.2, 6.2, stone)
    traversal += [{'kind': 'floor', 'room': 'colonnade_walkway', 'x': [-6, 6], 'y': [16, 48], 'z': -3.2},
                  {'kind': 'wading', 'room': 'colonnade_channels', 'x': [[-12, -6], [6, 12]], 'y': [16, 48], 'z': -3.6,
                   'water_surface': -3.3}]

    # 4 Corridor
    box('corridor2-floor', -3, 48, -3.8, 3, 56, -3.2, m['path'])
    layered_wall('corridor2-west', -3.6, 48.6, -3.6, 56, -3.2, stone)
    layered_wall('corridor2-east', 3.6, 48.6, 3.6, 56, -3.2, stone)
    traversal.append({'kind': 'floor', 'room': 'corridor_2', 'x': [-3, 3], 'y': [48, 56], 'z': -3.2})

    # 5 Gate of the Sun
    box('gate-floor', -8, 56, -3.8, 8, 72, -3.2, m['floor'])
    layered_wall('gate-south', -9.2, 55.4, -3, 55.4, -3.2, stone)
    layered_wall('gate-south-b', 3, 55.4, 9.2, 55.4, -3.2, stone)
    layered_wall('gate-west', -8.6, 56, -8.6, 72, -3.2, stone)
    layered_wall('gate-east', 8.6, 56, 8.6, 72, -3.2, stone)
    layered_wall('gate-north', -9.2, 72.6, 9.2, 72.6, -3.2, stone, openings=[(-2.5, 2.5, 4.8)])
    for k, (px, py) in enumerate(((-5, 64), (5, 64), (0, 69))):
        cylinder(f'mirror-pedestal-{k}', px, py, -3.2, -2.1, 0.6, m['trim'], segments=12)
        disc = cylinder(f'mirror-{k}', px, py, -2.1, -2.0, 0.45, m['bronze'], segments=24)
        disc['role'] = 'puzzle_pedestal'
    for side in (-1, 1):
        door = box(f'sun-gate-leaf-{side:+d}', side * 2.5, 72.35, -3.2, side * 0.02, 72.85, 1.6, m['bronze'])
        door['role'] = 'puzzle_gate'
    traversal.append({'kind': 'floor', 'room': 'gate_of_the_sun', 'x': [-8, 8], 'y': [56, 72], 'z': -3.2})

    # 6 Ramp to the dome
    traversal.append(ramp('dome-ramp', -3, 3, 72.6, 84, -3.2, -6.4, m['path']))
    layered_wall('dome-ramp-west', -3.6, 73.2, -3.6, 86.4, -6.4, stone, height=WALL_H + 3.2)
    layered_wall('dome-ramp-east', 3.6, 73.2, 3.6, 86.4, -6.4, stone, height=WALL_H + 3.2)
    box('dome-ramp-foot', -3, 84, -7.0, 3, 87, -6.4, m['path'])

    # 7 Collapsed dome (centre 0,100; r = 14)
    cylinder('dome-floor', 0, 100, -7.0, -6.4, 14.0, m['floor'], segments=64, smooth=False)
    entry_gap, exit_gap = math.radians(14), math.radians(14)
    south, north = -math.pi / 2, math.pi / 2
    for k, (a0, a1) in enumerate(((south + entry_gap, north - exit_gap), (north + exit_gap, south + math.tau - entry_gap))):
        ring(f'dome-ledge-{k}', 0, 100, 10.6, 14.0, -6.4, -4.0, m['base'], a0 + 0.5, a1 - 0.5)
        steps = 12
        for s in range(steps):
            a_mid = a0 + (a1 - a0) * s / steps
            height = 8.5 + RNG.uniform(-3.5, 2.5)
            ring(f'dome-wall-{k}-{s:02d}', 0, 100, 14.0, 15.2, -6.4, -6.4 + height, m['wall'], a_mid, a0 + (a1 - a0) * (s + 1) / steps, segments=96)
    for k, sign in enumerate((-1, 1)):
        traversal.append(ramp(f'dome-ledge-ramp-{k}', sign * 9.4 - 1.6, sign * 9.4 + 1.6, 93.0, 102.6, -4.0, -6.4, m['path']))
    for b in range(9):
        a = RNG.uniform(0, math.tau)
        r = RNG.uniform(3.5, 9.0)
        boulder(f'dome-rubble-{b}', math.cos(a) * r, 100 + math.sin(a) * r, -6.4, RNG.uniform(0.8, 1.9), m['rock'])
    ring('dome-fallen-rib', 2.5, 101, 5.0, 5.8, -6.4, -5.6, m['trim'], 0.3, 1.6, segments=48)
    traversal += [{'kind': 'floor', 'room': 'collapsed_dome', 'circle': [0, 100, 14.0], 'z': -6.4},
                  {'kind': 'ledge', 'room': 'collapsed_dome', 'annulus': [0, 100, 10.6, 14.0], 'z': -4.0}]

    # 8 Sanctum stair
    box('stair2-landing', -3, 113.6, -7.0, 3, 114.4, -6.4, m['path'])
    traversal.append(stairs('stair2', -3, 3, 114.4, 122.4, -6.4, -8.0, m['path']))
    layered_wall('stair2-west', -3.6, 114.2, -3.6, 124, -8.0, stone, height=WALL_H + 1.6)
    layered_wall('stair2-east', 3.6, 114.2, 3.6, 124, -8.0, stone, height=WALL_H + 1.6)
    box('stair2-foot', -3, 122.4, -8.6, 3, 124, -8.0, m['path'])

    # 9 Sanctum (boss)
    box('sanctum-floor', -13, 124, -8.6, 13, 156, -8.0, m['floor'])
    for side, (x0, x1) in (('west', (-16, -13)), ('east', (13, 16))):
        box(f'sanctum-pool-{side}-bed', x0, 124, -9.2, x1, 156, -8.6, m['base'])
        box(f'sanctum-pool-{side}-water', x0, 124, -8.22, x1, 156, -8.18, m['water'])
    layered_wall('sanctum-south', -16.6, 123.4, -3, 123.4, -8.0, sanctum, height=9.0)
    layered_wall('sanctum-south-b', 3, 123.4, 16.6, 123.4, -8.0, sanctum, height=9.0)
    layered_wall('sanctum-west', -16.6, 124, -16.6, 156, -8.6, sanctum, height=9.6)
    layered_wall('sanctum-east', 16.6, 124, 16.6, 156, -8.6, sanctum, height=9.6)
    layered_wall('sanctum-north', -16.6, 156.6, 16.6, 156.6, -8.0, sanctum, height=9.0, openings=[(-3, 3, 4.6)])
    for k, radius in enumerate((4.0, 3.6, 3.2)):
        cylinder(f'dais-{k}', 0, 140, -8.0 + STEP_RISE * k, -8.0 + STEP_RISE * (k + 1), radius, m['accent_trim'] if k == 2 else m['trim'], segments=48, smooth=False)
    for x in (-8, 8):
        for y in (132, 148):
            pillar(f'sanctum-pillar-{x:+d}-{y}', x, y, -8.0, 8.2, sanctum, radius=0.95)
    traversal += [{'kind': 'floor', 'room': 'sanctum', 'x': [-13, 13], 'y': [124, 156], 'z': -8.0},
                  {'kind': 'dais', 'room': 'sanctum', 'circle': [0, 140, 4.0], 'z': -8.0 + 3 * STEP_RISE}]

    # 10 Reward alcove
    box('alcove-floor', -4, 156, -8.6, 4, 164, -8.0, m['floor'])
    layered_wall('alcove-west', -4.6, 157.2, -4.6, 164, -8.0, sanctum)
    layered_wall('alcove-east', 4.6, 157.2, 4.6, 164, -8.0, sanctum)
    layered_wall('alcove-north', -5.2, 164.6, 5.2, 164.6, -8.0, sanctum)
    chest = box('reward-chest', -0.8, 159.4, -8.0, 0.8, 160.4, -7.1, m['bronze'])
    chest['role'] = 'reward_chest'
    ring('return-arch', 0, 162.6, 1.25, 1.5, -8.0, -7.7, m['bronze'], segments=40)
    exit_portal = cylinder('return-veil', 0, 162.6, -7.99, -7.95, 1.25, m['portal'], segments=40, smooth=False)
    exit_portal['role'] = 'exit_portal'
    traversal.append({'kind': 'floor', 'room': 'reward_alcove', 'x': [-4, 4], 'y': [156, 164], 'z': -8.0})

    # Ravine: the temple sits below the meadow line, so the camera always reads "sunken".
    box('ravine-floor', -18, -26, -12, 18, 172, -9.6, m['rock'])
    for side in (-1, 1):
        y = -26.0
        while y < 172:
            length = RNG.uniform(6, 12)
            inner = 18 + RNG.uniform(-1.2, 1.8)
            top = RNG.uniform(5.0, 9.5)
            x0, x1 = sorted((side * inner, side * (inner + 9)))
            box(f'ravine-{side:+d}-{y:.0f}', x0, y, -10, x1, min(172, y + length), top, m['rock'])
            box(f'ravine-lip-{side:+d}-{y:.0f}', x0, y, top, x1, min(172, y + length), top + 0.35, m['grass'])
            y += length
    for name, (y0, y1) in (('ravine-south', (-34, -26)), ('ravine-north', (172, 180))):
        box(name, -27, y0, -10, 27, y1, 8.0, m['rock'])
        box(f'{name}-lip', -27, y0, 8.0, 27, y1, 8.35, m['grass'])
    for k in range(14):
        boulder(f'ravine-rock-{k}', RNG.choice((-1, 1)) * RNG.uniform(14.5, 17.0), RNG.uniform(-12, 168), -9.6,
                RNG.uniform(1.4, 3.0), m['rock'])
    return {'traversal': traversal}


# ----------------------------------------------------------------------------
# Lighting, cameras, renders, export
# ----------------------------------------------------------------------------

def setup_scene(samples: int, device: str = 'gpu') -> None:
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    try:
        if device == 'cpu':
            raise RuntimeError('CPU requested: keep the shared GPU free for live Babylon reviews')
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'CUDA'; prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == 'CUDA'
        scene.cycles.device = 'GPU'
    except Exception:
        scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = 'AgX'
    for look in ('AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    world = bpy.data.worlds.new('sky'); world.use_nodes = True
    nodes = world.node_tree.nodes
    sky = nodes.new('ShaderNodeTexSky')
    try:
        sky.sun_elevation = math.radians(52); sky.sun_rotation = math.radians(115)
    except Exception:
        pass
    world.node_tree.links.new(sky.outputs['Color'], nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value = 0.14
    scene.world = world
    sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 2.6; sun.angle = math.radians(1.5)
    scene.view_settings.exposure = -0.35
    sun.color = (1.0, 0.94, 0.84)
    obj = bpy.data.objects.new('sun', sun); obj.rotation_euler = (math.radians(38), math.radians(8), math.radians(115))
    scene.collection.objects.link(obj)
    for k, (x, y, z, color, power) in enumerate(((-6.5, 5.5, 1.6, (1, .55, .25), 260), (6.5, 5.5, 1.6, (1, .55, .25), 260),
                                                 (0, 140, -5.0, (.55, .7, 1), 600), (0, 64, -1.2, (1, .8, .5), 220))):
        light = bpy.data.lights.new(f'fill-{k}', 'POINT'); light.energy = power; light.color = color; light.shadow_soft_size = 0.6
        lo = bpy.data.objects.new(f'fill-{k}', light); lo.location = (x, y, z); scene.collection.objects.link(lo)


def game_camera(name, feet, yaw_deg, radius=13.0, beta=1.18, fov=1.02):
    """Blender camera matching the game's ArcRotateCamera framing around a player standing at feet."""
    target = Vector((feet[0], feet[1], feet[2] + 1.65))
    yaw = math.radians(yaw_deg)
    forward = Vector((math.sin(yaw), math.cos(yaw), 0))
    position = target - forward * (radius * math.sin(beta)) + Vector((0, 0, radius * math.cos(beta)))
    # WoW-style camera collision: pull the camera in front of the first wall between it and the player.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    offset = position - target
    hit, location, *_ = bpy.context.scene.ray_cast(depsgraph, target, offset.normalized(), distance=offset.length)
    collided = bool(hit)
    if hit:
        position = target + offset.normalized() * max(2.5, (location - target).length - 0.4)
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    cam['camera_collision'] = collided
    cam['boom_m'] = round((position - target).length, 2)
    cam.data.sensor_fit = 'VERTICAL'
    cam.data.angle_y = fov
    cam.location = position
    direction = target - position
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.collection.objects.link(cam)
    return cam


SHOTS = [
    ('hall', (0, -3.5, 0.0), 0), ('colonnade', (0, 23, -3.2), 0), ('gate', (0, 60.5, -3.2), 0),
    ('dome', (0, 91, -6.4), 0), ('dome-ledge', (-10.5, 104, -4.0), 120), ('sanctum', (0, 129, -8.0), 0),
]


def main() -> None:
    a = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for key, name in (('floor', 'plaza_flagstone'), ('wall', 'stone_wall_warm'), ('base', 'stone_foundation'),
                      ('trim', 'stone_trim_carved'), ('accent', 'stone_accent_bluegrey'), ('path', 'paver_surface'),
                      ('rock', 'cliff_rock'), ('grass', 'grass_ground')):
        MATS[key] = texture_material(name)
    MATS['accent_trim'] = MATS['accent']
    MATS['bronze'] = flat_material('bronze', '#8a6a3a', rough=0.38, metal=0.85)
    MATS['water'] = flat_material('water', '#1f4d55', rough=0.04, alpha=0.82)
    MATS['portal'] = flat_material('portal-veil', '#3a6fd8', rough=0.3, emission='#6fa8ff', strength=3.0, alpha=0.85)
    MATS['witness'] = flat_material('scale-witness-1.8m', '#c0392b', rough=0.6)
    layout = build_level()
    a['out'].mkdir(parents=True, exist_ok=True)
    a['shots'].mkdir(parents=True, exist_ok=True)
    setup_scene(a['samples'], a['device'])
    shots = []
    if a['render']:
        player_cams = [(name, game_camera(f'cam-{name}', feet, yaw)) for name, feet, yaw in SHOTS]
        for name, feet, yaw in SHOTS:
            witness(f'witness-{name}', *feet)
        overview = bpy.data.objects.new('overview', bpy.data.cameras.new('overview'))
        overview.location = (58, -42, 74)
        overview.data.lens = 24
        overview.rotation_euler = (Vector((0, 78, -6)) - overview.location).to_track_quat('-Z', 'Y').to_euler()
        bpy.context.scene.collection.objects.link(overview)
        cams = [('overview', overview)] + player_cams
        collision = {name: {'collided': bool(cam.get('camera_collision')), 'boom_m': cam.get('boom_m')} for name, cam in player_cams}
        print('CAMERA_COLLISION', collision)
        for name, cam in cams:
            scene = bpy.context.scene
            scene.camera = cam
            scene.render.filepath = str(a['shots'] / f'sunken-temple-d2-{name}.png')
            bpy.ops.render.render(write_still=True)
            shots.append(Path(scene.render.filepath).relative_to(ROOT).as_posix())
            print('SHOT', scene.render.filepath)
    record_extra = {'camera_collision_by_shot': collision} if a['render'] else {}
    record = {'schema': 'xexoria.dungeon-blockout/1', 'dungeon': 'sunken_temple_of_aurel', 'milestone': 'D2-blockout',
              'units': 'metres, Blender Z-up; glTF export converts to +Y up', 'player_height_m': 1.8,
              'spawn': {'x': 0.0, 'y': -3.5, 'z': 0.0, 'facing_deg': 0},
              'return_portal': {'x': 0.0, 'y': -12.5, 'z': 0.32}, 'exit_portal': {'x': 0.0, 'y': 162.6, 'z': -8.0},
              'traversal': layout['traversal'], 'shots': shots, 'status': 'BLENDER REVIEW only; no Babylon capture yet', **record_extra}
    if a['export']:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in LEVEL:
            obj.select_set(True)
        glb = a['out'] / 'sunken-temple-blockout-d2.glb'
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True, export_apply=True,
                                  export_yup=True, export_cameras=False, export_lights=False)
        record['glb'] = {'path': glb.relative_to(ROOT).as_posix(), 'bytes': glb.stat().st_size,
                         'sha256': hashlib.sha256(glb.read_bytes()).hexdigest(), 'objects': len(LEVEL)}
    (a['out'] / 'layout-d2.json').write_text(json.dumps(record, indent=2) + '\n')
    print('LAYOUT', a['out'] / 'layout-d2.json', 'objects', len(LEVEL))


if __name__ == '__main__':
    main()
