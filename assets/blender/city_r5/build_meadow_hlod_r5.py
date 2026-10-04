"""Reusable mesh, palette, and original-expression proxy helpers for R5 HLOD.

Import from ``build_meadow_hlod_proxy_r5.py``. This module creates no assets
and performs no file writes at import time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'lib'))
import citykit as ck  # noqa: E402

MASTER = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'reference_city.blend'
FULL_SOURCE = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'city-source.glb'
FULL_RUNTIME = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'city-runtime.glb'
LAYOUT_PATH = HERE / 'layout.json'
PRESENTATION_COLLECTION = 'Presentation only'
RUNTIME_PREFIXES = ('anim_', 'fx_', 'emit_', 'light_')
TRIANGLE_LIMIT = 25_000
BYTE_LIMIT = 4 * 1024 * 1024

PALETTE = {
    'HLOD_Ground': ((0.34, 0.52, 0.20, 1.0), 0.95),
    'HLOD_Cliff': ((0.28, 0.20, 0.14, 1.0), 0.92),
    'HLOD_Stone': ((0.65, 0.55, 0.42, 1.0), 0.88),
    'HLOD_RoofBlue': ((0.075, 0.16, 0.39, 1.0), 0.82),
    'HLOD_RoofWarm': ((0.56, 0.23, 0.14, 1.0), 0.86),
    'HLOD_Wood': ((0.22, 0.13, 0.07, 1.0), 0.90),
    'HLOD_Water': ((0.045, 0.42, 0.67, 1.0), 0.28),
    'HLOD_Accent': ((0.78, 0.49, 0.12, 1.0), 0.52),
}

TERRAIN_RATIOS = {
    'terrain / grass ground': 0.32,
    'terrain / cliff rock': 0.42,
    'terrain / cliff soil band': 0.55,
    'terrain / cliff grass lip': 0.60,
    'terrain / cliff underside cap': 0.70,
    'terrain / castle terrace / top': 0.60,
    'terrain / wizard terrace / top': 0.65,
    'terrain / castle terrace / retaining wall': 0.55,
    'terrain / wizard terrace / retaining wall': 0.55,
    'terrain / plaza pavers paver_surface': 0.12,
    'terrain / plaza pavers stone_accent_bluegrey': 0.12,
    'terrain / plaza pavers stone_trim_carved': 0.20,
}


def parse_args():
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, help='Explicit temporary HLOD GLB output.')
    parser.add_argument('--stats', required=True, help='Explicit JSON budget receipt output.')
    parser.add_argument('--limit-triangles', type=int, default=TRIANGLE_LIMIT)
    args = parser.parse_args(raw)
    args.candidate = Path(args.candidate).expanduser().resolve()
    args.stats = Path(args.stats).expanduser().resolve()
    if args.candidate == args.stats:
        parser.error('--candidate and --stats must be different paths.')
    if args.candidate.suffix.lower() != '.glb' or args.stats.suffix.lower() != '.json':
        parser.error('--candidate must end in .glb and --stats must end in .json.')
    if args.limit_triangles < 1 or args.limit_triangles > TRIANGLE_LIMIT:
        parser.error(f'--limit-triangles must be in [1, {TRIANGLE_LIMIT}].')
    protected = {MASTER.resolve(), FULL_SOURCE.resolve(), FULL_RUNTIME.resolve()}
    if args.candidate in protected or args.stats in protected:
        parser.error('HLOD outputs may not overwrite the R5 master, source, or full runtime GLB.')
    return args


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def triangle_count(obj, depsgraph=None) -> int:
    if depsgraph is None:
        return sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return sum(len(poly.vertices) - 2 for poly in mesh.polygons)
    finally:
        evaluated.to_mesh_clear()


def glb_stats(path: Path) -> tuple[int, int, int]:
    with path.open('rb') as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise RuntimeError('HLOD GLB is truncated before its header.')
        magic, version, declared_size = struct.unpack('<III', header)
        if magic != 0x46546C67 or version != 2 or declared_size != path.stat().st_size:
            raise RuntimeError('HLOD GLB header/version/length is invalid.')
        chunk_header = stream.read(8)
        if len(chunk_header) != 8:
            raise RuntimeError('HLOD GLB is missing its JSON chunk.')
        json_length, chunk_type = struct.unpack('<II', chunk_header)
        if chunk_type != 0x4E4F534A:
            raise RuntimeError('HLOD GLB first chunk is not JSON.')
        document = json.loads(stream.read(json_length).decode('utf-8').rstrip('\0 '))
    accessors = document.get('accessors', [])
    triangles = 0
    for mesh in document.get('meshes', []):
        for primitive in mesh.get('primitives', []):
            if primitive.get('mode', 4) != 4:
                continue
            index_accessor = primitive.get('indices')
            count = (accessors[index_accessor]['count'] if index_accessor is not None else
                     accessors[primitive['attributes']['POSITION']]['count'])
            triangles += count // 3
    return triangles, len(document.get('materials', [])), len(document.get('images', []))


def make_palette_materials():
    materials = {}
    for name, (color, roughness) in PALETTE.items():
        material = bpy.data.materials.new(name)
        material.diffuse_color = color
        if material.node_tree is None:
            material.use_nodes = True
        shader = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if shader is None:
            shader = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            output = next((node for node in material.node_tree.nodes if node.type == 'OUTPUT_MATERIAL'), None)
            if output is None:
                output = material.node_tree.nodes.new('ShaderNodeOutputMaterial')
            material.node_tree.links.new(shader.outputs['BSDF'], output.inputs['Surface'])
        shader.inputs['Base Color'].default_value = color
        shader.inputs['Roughness'].default_value = roughness
        shader.inputs['Metallic'].default_value = 0.12 if name == 'HLOD_Accent' else 0.0
        return_material_nodes = material.node_tree.nodes
        for node in list(return_material_nodes):
            if node.type == 'TEX_IMAGE' or node.type == 'VERTEX_COLOR':
                return_material_nodes.remove(node)
        materials[name] = material
    return materials


def new_mesh(name, vertices, faces, material, collection):
    if isinstance(material, str):
        material = bpy.data.materials.get(material)
    if material is None:
        raise RuntimeError(f'HLOD material for {name} is missing.')
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def make_box(name, center, size, material, collection, rotation_y=0.0):
    width, depth, height = size
    w, d, h = width * 0.5, depth * 0.5, height * 0.5
    local = [(-w, -d, -h), (w, -d, -h), (w, d, -h), (-w, d, -h),
             (-w, -d, h), (w, -d, h), (w, d, h), (-w, d, h)]
    import math
    c, s = math.cos(rotation_y), math.sin(rotation_y)
    cx, cy, cz = center
    vertices = [(cx + x * c + z * s, cy + y, cz - x * s + z * c) for x, y, z in local]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    obj = new_mesh(name, vertices, faces, material, collection)
    obj['is_hlod_proxy'] = True
    return obj


def make_gable(name, center, width, depth, height, material, collection):
    cx, cy, base_z = center
    w, d = width * 0.5, depth * 0.5
    vertices = [(-w, -d, 0), (w, -d, 0), (w, d, 0), (-w, d, 0), (-w, 0, height), (w, 0, height)]
    faces = [(0, 3, 2, 1), (0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5)]
    vertices = [(cx + x, cy + y, base_z + z) for x, y, z in vertices]
    return new_mesh(name, vertices, faces, material, collection)


def make_frustum(name, center, bottom_radius, top_radius, height, material, collection, segments=10):
    import math
    cx, cy, base_z = center
    vertices = []
    for index in range(segments):
        angle = math.tau * index / segments
        vertices.append((cx + math.cos(angle) * bottom_radius, cy + math.sin(angle) * bottom_radius, base_z))
    faces = [tuple(reversed(range(segments)))]
    if top_radius <= 1e-6:
        apex = len(vertices)
        vertices.append((cx, cy, base_z + height))
        for index in range(segments):
            nxt = (index + 1) % segments
            faces.append((index, nxt, apex))
    else:
        for index in range(segments):
            angle = math.tau * index / segments
            vertices.append((cx + math.cos(angle) * top_radius, cy + math.sin(angle) * top_radius, base_z + height))
        faces.append(tuple(range(segments, segments * 2)))
        for index in range(segments):
            nxt = (index + 1) % segments
            faces.append((index, nxt, segments + nxt, segments + index))
    return new_mesh(name, vertices, faces, material, collection)


def make_ring(name, center, radius, minor_radius, material, collection, major_segments=20, minor_segments=4):
    import math
    cx, cy, cz = center
    vertices, faces = [], []
    for major in range(major_segments):
        theta = math.tau * major / major_segments
        for minor in range(minor_segments):
            phi = math.tau * minor / minor_segments
            r = radius + minor_radius * math.cos(phi)
            vertices.append((cx + r * math.cos(theta), cy + r * math.sin(theta), cz + minor_radius * math.sin(phi)))
    for major in range(major_segments):
        for minor in range(minor_segments):
            a = major * minor_segments + minor
            b = major * minor_segments + (minor + 1) % minor_segments
            c = ((major + 1) % major_segments) * minor_segments + (minor + 1) % minor_segments
            d = ((major + 1) % major_segments) * minor_segments + minor
            faces.append((a, b, c, d))
    return new_mesh(name, vertices, faces, material, collection)


def make_palette_key(source_material):
    name = source_material.lower()
    if name in {'grass_ground'} or name.startswith(('foliage_', 'flower_')):
        return 'HLOD_Ground'
    if name in {'cliff_rock', 'dirt_path'}:
        return 'HLOD_Cliff'
    if name.startswith('roof_slate_'):
        return 'HLOD_RoofBlue'
    if name in {'roof_tile_red', 'roof_shingle_green'}:
        return 'HLOD_RoofWarm'
    if name in {'timber_dark', 'wood_planks_light'}:
        return 'HLOD_Wood'
    if name in {'water', 'water_foam', 'magic_blue'}:
        return 'HLOD_Water'
    if name.startswith(('magic_', 'metal_', 'glass_window_', 'cloth_')) or name in {'banner_emblem', 'marble_statue'}:
        return 'HLOD_Accent'
    if name.startswith('stone_') or name in {'paver_surface', 'plaza_flagstone', 'plaster_cream', 'cobble_path'}:
        return 'HLOD_Stone'
    return 'HLOD_Stone'


def add_proxy_building(collection, material, roof_material, center, footprint, stories=2, name='HLOD house'):
    x, y = center
    width, depth = footprint
    wall_height = 3.6 * stories
    base_z = 0.0
    make_box(f'{name} walls', (x, y, base_z + wall_height * 0.5), (width, depth, wall_height), material, collection)
    make_gable(f'{name} roof', (x, y, base_z + wall_height), width + 1.2, depth + 1.2, max(3.2, depth * 0.42), roof_material, collection)
    make_box(f'{name} door', (x, y - depth * 0.5 - 0.03, base_z + 1.4), (1.6, 0.16, 2.8), 'HLOD_Wood', collection)
    if stories >= 2:
        chimney_h = max(3.5, stories * 2.0)
        make_box(f'{name} chimney', (x + width * 0.30, y + depth * 0.2, wall_height + chimney_h * 0.5),
                 (1.8, 1.8, chimney_h), 'HLOD_Stone', collection)


def add_tree(collection, x, y, scale=1.0, suffix=''):
    make_frustum(f'HLOD tree trunk {suffix}', (x, y, 0), 0.38 * scale, 0.25 * scale, 4.2 * scale, 'HLOD_Wood', collection, 7)
    make_frustum(f'HLOD tree canopy lower {suffix}', (x, y, 2.8 * scale), 3.2 * scale, 0.15 * scale, 5.6 * scale, 'HLOD_Ground', collection, 7)
    make_frustum(f'HLOD tree canopy upper {suffix}', (x, y, 6.2 * scale), 2.3 * scale, 0.0, 4.4 * scale, 'HLOD_Ground', collection, 7)


def add_proxies(layout, collection):
    proxies = []
    def add(obj):
        proxies.append(obj)
        return obj

    levels = layout['levels']
    by_id = {landmark['id']: landmark for landmark in layout['landmarks']}
    castle = by_id['magic_castle']
    cx, cy = castle['center']
    base_z = levels[castle['level']]
    # Strong massing and a multi-spire silhouette remain readable from the field.
    add(make_box('HLOD castle plinth', (cx, cy, base_z + 1.0), (70, 42, 2), 'HLOD_Stone', collection))
    add(make_box('HLOD castle keep', (cx, cy + 2, base_z + 19), (32, 25, 34), 'HLOD_Stone', collection))
    add(make_gable('HLOD castle main roof', (cx, cy + 2, base_z + 36), 38, 29, 12, 'HLOD_RoofBlue', collection))
    for side in (-1, 1):
        add(make_box(f'HLOD castle wing {side}', (cx + side * 23, cy + 1, base_z + 12), (17, 34, 20), 'HLOD_Stone', collection))
        add(make_gable(f'HLOD castle wing roof {side}', (cx + side * 23, cy + 1, base_z + 22), 19, 36, 8, 'HLOD_RoofBlue', collection))
        for fore_aft in (-1, 1):
            tx, ty = cx + side * 28, cy + fore_aft * 13
            add(make_frustum(f'HLOD castle round tower {side}-{fore_aft}', (tx, ty, base_z), 4.6, 3.8, 33, 'HLOD_Stone', collection, 10))
            add(make_frustum(f'HLOD castle tower roof {side}-{fore_aft}', (tx, ty, base_z + 33), 5.2, 0.0, 14, 'HLOD_RoofBlue', collection, 10))
            add(make_frustum(f'HLOD castle finial {side}-{fore_aft}', (tx, ty, base_z + 47), 0.55, 0.0, 3.8, 'HLOD_Accent', collection, 6))
    add(make_frustum('HLOD castle central spire shaft', (cx, cy + 2, base_z + 42), 4.0, 3.0, 19, 'HLOD_Stone', collection, 10))
    add(make_frustum('HLOD castle central spire roof', (cx, cy + 2, base_z + 61), 4.4, 0.0, 20, 'HLOD_RoofBlue', collection, 10))
    add(make_frustum('HLOD castle central finial', (cx, cy + 2, base_z + 81), 0.65, 0.0, 4.2, 'HLOD_Accent', collection, 6))
    add(make_box('HLOD castle portal glow', (0, 77.0, base_z + 13), (8.0, 0.45, 12.0), 'HLOD_Water', collection))
    # A recognizable city gate with the same 15 m visual opening as gameplay collision.
    gate = by_id['town_gate']
    gx, gy = gate['center']
    gz = levels[gate['level']]
    for side in (-1, 1):
        add(make_box(f'HLOD gate wing {side}', (gx + side * 11.25, gy, gz + 6.5), (7.5, 2.5, 13), 'HLOD_Stone', collection))
        add(make_frustum(f'HLOD gate tower {side}', (gx + side * 16, gy, gz), 5.0, 4.0, 17, 'HLOD_Stone', collection, 10))
        add(make_frustum(f'HLOD gate roof {side}', (gx + side * 16, gy, gz + 17), 5.5, 0.0, 9, 'HLOD_RoofBlue', collection, 10))
        add(make_box(f'HLOD gate banner {side}', (gx + side * 16, gy - 2.75, gz + 10), (3.0, 0.2, 5.5), 'HLOD_Accent', collection))
    add(make_box('HLOD gate lintel', (gx, gy, gz + 13.0), (15.0, 2.5, 3.0), 'HLOD_Stone', collection))
    # Wizard tower with floating rings.
    wizard = by_id['wizard_tower']
    wx, wy = wizard['center']
    wz = levels[wizard['level']]
    add(make_frustum('HLOD wizard tower', (wx, wy, wz), 8.0, 5.2, 58, 'HLOD_Stone', collection, 12))
    add(make_frustum('HLOD wizard blue spire', (wx, wy, wz + 58), 7.0, 0.0, 16, 'HLOD_RoofBlue', collection, 12))
    for index, ring in enumerate(wizard['rings']):
        add(make_ring(f'HLOD wizard ring {index}', (wx, wy, wz + ring['height']), ring['radius'], 0.38, 'HLOD_Water', collection, 24, 4))
    # Windmill tower and crossing sail beams.
    windmill = by_id['windmill']
    mx, my = windmill['center']
    mz = levels[windmill['level']]
    add(make_frustum('HLOD windmill tower', (mx, my, mz), 6.0, 4.8, 14, 'HLOD_Stone', collection, 10))
    add(make_frustum('HLOD windmill cap', (mx, my, mz + 14), 5.5, 0.0, 6, 'HLOD_RoofWarm', collection, 10))
    for angle in (0.0, 0.785398, 1.570796, 2.356194):
        add(make_box(f'HLOD windmill sail {angle}', (mx, my - 5.2, mz + 12), (1.1, 0.55, 12), 'HLOD_Wood', collection, rotation_y=angle))
    # Plaza focal silhouettes.
    add(make_frustum('HLOD fountain base', (0, 0, 0), 12.5, 11.0, 2.4, 'HLOD_Stone', collection, 16))
    add(make_frustum('HLOD fountain upper bowl', (0, 0, 2.3), 6.0, 4.4, 2.4, 'HLOD_Water', collection, 14))
    add(make_frustum('HLOD fountain crystal stem', (0, 0, 4.5), 1.4, 1.0, 7.0, 'HLOD_Accent', collection, 8))
    portal = layout['portal']['center']
    add(make_frustum('HLOD portal dais', (portal[0], portal[1], 0), 8.0, 7.0, 1.2, 'HLOD_Stone', collection, 10))
    add(make_frustum('HLOD portal column', (portal[0], portal[1], 1.0), 1.4, 0.35, 12, 'HLOD_Water', collection, 8))

    # Signature shops and repeated residential rows form a readable town mass.
    shop_specs = [
        ('blacksmith', 'HLOD_RoofWarm', 2),
        ('armory_house', 'HLOD_RoofBlue', 2),
        ('guild_hall', 'HLOD_RoofBlue', 3),
        ('tavern', 'HLOD_RoofWarm', 2),
        ('potion_shop', 'HLOD_Ground', 2),
    ]
    for identifier, roof_material, stories in shop_specs:
        item = by_id[identifier]
        add_proxy_building(collection, 'HLOD_Stone', roof_material, item['center'], item['footprint'], stories, f'HLOD {identifier}')
    roof_cycle = ('HLOD_RoofBlue', 'HLOD_RoofWarm', 'HLOD_Ground', 'HLOD_RoofBlue')
    house_index = 0
    for landmark in layout['landmarks']:
        if landmark.get('kind') != 'house_small_group':
            continue
        footprint = landmark.get('footprint', [11, 9])
        ground_z = levels.get(landmark.get('level', 'plaza'), 0.0)
        for center in landmark.get('centers', []):
            roof_material = roof_cycle[house_index % len(roof_cycle)]
            add_proxy_building(collection, 'HLOD_Stone', roof_material, center, footprint, 2, f'HLOD home {house_index}')
            house_index += 1

    market = by_id['market']
    for row_index, row in enumerate(market['stall_rows']):
        start, end = row
        stalls = int(market['stalls_per_row'])
        for stall_index in range(stalls):
            t = (stall_index + 0.5) / stalls
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            canopy = ('HLOD_RoofWarm', 'HLOD_RoofBlue', 'HLOD_Accent', 'HLOD_Ground')[(row_index + stall_index) % 4]
            for dx in (-1.45, 1.45):
                for dy in (-1.15, 1.15):
                    add(make_box(f'HLOD stall pole {row_index}-{stall_index}-{dx}-{dy}', (x + dx, y + dy, 1.6),
                                 (0.18, 0.18, 3.2), 'HLOD_Wood', collection))
            add(make_gable(f'HLOD stall canopy {row_index}-{stall_index}', (x, y, 3.0), 3.8, 3.2, 1.0, canopy, collection))
            add(make_box(f'HLOD stall counter {row_index}-{stall_index}', (x, y - 1.3, 0.75),
                         (3.4, 0.85, 1.5), 'HLOD_Wood', collection))

    # A tree belt echoes the town's road/river edges at skyline distance.
    tree_spots = [(-105, y) for y in (-118, -76, -34, 8, 50, 92)]
    tree_spots += [(105, y) for y in (-118, -76, -34, 8, 50, 92)]
    tree_spots += [(x, 118) for x in (-82, -42, 0, 42, 82)]
    for index, (x, y) in enumerate(tree_spots):
        add_tree(collection, x, y, 0.9 + (index % 4) * 0.12, f'{index}')
    return proxies
