"""Build a silhouette-led meadow HLOD from the preserved R5 layout.

It uses a few broad terrain meshes plus original-expression proxies for the
castle, gate, towers, shops and homes. It never saves or overwrites the R5
master, source GLB, or full runtime GLB.
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
sys.path.insert(0, str(HERE))
import citykit as ck  # noqa: E402
import build_meadow_hlod_r5 as proxy  # noqa: E402

MASTER = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'reference_city.blend'
FULL_SOURCE = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'city-source.glb'
FULL_RUNTIME = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'city-runtime.glb'
LAYOUT_PATH = HERE / 'layout.json'
PRESENTATION_COLLECTION = 'Presentation only'
TRIANGLE_LIMIT = 25_000
BYTE_LIMIT = 4 * 1024 * 1024
HLOD_COLLECTION = 'Meadow HLOD proxy'


def parse_args():
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--stats', required=True)
    parser.add_argument('--limit-triangles', type=int, default=TRIANGLE_LIMIT)
    args = parser.parse_args(raw)
    args.candidate = Path(args.candidate).expanduser().resolve()
    args.stats = Path(args.stats).expanduser().resolve()
    if args.candidate == args.stats or args.candidate.suffix.lower() != '.glb' or args.stats.suffix.lower() != '.json':
        parser.error('Use different explicit .glb candidate and .json stats paths.')
    if args.limit_triangles < 1 or args.limit_triangles > TRIANGLE_LIMIT:
        parser.error(f'--limit-triangles must be in [1, {TRIANGLE_LIMIT}].')
    if args.candidate in {MASTER.resolve(), FULL_SOURCE.resolve(), FULL_RUNTIME.resolve()}:
        parser.error('The HLOD candidate may not overwrite any full R5 source asset.')
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
        json_length, chunk_type = struct.unpack('<II', chunk_header)
        if chunk_type != 0x4E4F534A:
            raise RuntimeError('HLOD GLB first chunk is not JSON.')
        document = json.loads(stream.read(json_length).decode('utf-8').rstrip('\0 '))
    triangles = 0
    accessors = document.get('accessors', [])
    for mesh in document.get('meshes', []):
        for primitive in mesh.get('primitives', []):
            if primitive.get('mode', 4) != 4:
                continue
            accessor = primitive.get('indices', primitive.get('attributes', {}).get('POSITION'))
            triangles += accessors[accessor]['count'] // 3
    return triangles, len(document.get('materials', [])), len(document.get('images', []))


def copied_terrain(source, collection, materials, ratio):
    obj = source.copy()
    obj.data = source.data.copy()
    collection.objects.link(obj)
    world_matrix = source.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world_matrix
    obj.name = 'HLOD source ' + source.name
    material_name = source.data.materials[0].name if source.data.materials else 'stone_wall_warm'
    key = proxy.make_palette_key(material_name)
    obj.data.materials.clear()
    obj.data.materials.append(materials[key])
    for poly in obj.data.polygons:
        poly.material_index = 0
    for layer in list(obj.data.uv_layers):
        obj.data.uv_layers.remove(layer)
    for attribute in list(obj.data.color_attributes):
        obj.data.color_attributes.remove(attribute)
    source_tris = triangle_count(obj)
    if ratio < 1.0 and source_tris > 3:
        modifier = obj.modifiers.new(name='HLOD terrain reduction', type='DECIMATE')
        modifier.decimate_type = 'COLLAPSE'
        modifier.ratio = ratio
        depsgraph = bpy.context.evaluated_depsgraph_get()
        baked = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
        if baked is None:
            raise RuntimeError(f'Could not simplify HLOD terrain source {source.name}.')
        obj.data = baked
        for remaining in list(obj.modifiers):
            obj.modifiers.remove(remaining)
    obj.data.validate(verbose=False, clean_customdata=True)
    return obj, source_tris, triangle_count(obj), key


def main():
    args = parse_args()
    if Path(bpy.data.filepath).resolve() != MASTER.resolve():
        raise RuntimeError(f'Load the preserved R5 master before exporting: {MASTER}')
    if not MASTER.is_file() or not FULL_SOURCE.is_file() or not FULL_RUNTIME.is_file():
        raise FileNotFoundError('The protected R5 master, source, and full runtime must exist.')
    source_hashes = {'master': sha256(MASTER), 'source': sha256(FULL_SOURCE), 'full_runtime': sha256(FULL_RUNTIME)}
    layout = json.loads(LAYOUT_PATH.read_text(encoding='utf-8'))
    args.candidate.parent.mkdir(parents=True, exist_ok=True)
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    pending = args.candidate.with_name(args.candidate.stem + '.pending' + args.candidate.suffix)
    pending.unlink(missing_ok=True)

    palette = proxy.make_palette_materials()
    hlod_collection = bpy.data.collections.new(HLOD_COLLECTION)
    bpy.context.scene.collection.children.link(hlod_collection)
    terrain_collection = bpy.data.collections.get('terrain')
    if terrain_collection is None:
        raise RuntimeError('The R5 master has no terrain collection.')
    terrain_ratios = dict(proxy.TERRAIN_RATIOS)
    # The detailed paver mesh contains many tiny stones; replace it with a
    # clean circular plaza proxy and rings below instead of collapsing it.
    for name in list(terrain_ratios):
        if name.startswith('terrain / plaza pavers '):
            terrain_ratios.pop(name)
    terrain_names = set(terrain_ratios)
    terrain_ratios.update({
        'terrain / path south_ring_road': 0.85,
        'terrain / path west_loop': 0.85,
        'terrain / path east_loop': 0.85,
        'terrain / path wizard_path': 0.85,
        'terrain / path windmill_path': 0.85,
        'terrain / wizard stairs': 0.65,
        'terrain / wizard terrace / top': 0.70,
        'terrain / castle terrace / top': 0.70,
        'terrain / castle terrace / retaining wall': 0.75,
        'terrain / wizard terrace / retaining wall': 0.75,
        'terrain / canal promenade -1': 0.75,
        'terrain / canal promenade +1': 0.75,
    })
    terrain_names.update(terrain_ratios)
    terrain_names.update(obj.name for obj in terrain_collection.objects
                         if obj.name.startswith(('terrain / avenue ', 'terrain / path ')))
    for obj in terrain_collection.objects:
        if obj.name in terrain_names:
            terrain_ratios.setdefault(obj.name, 0.90)

    terrain_stats = []
    for source_obj in terrain_collection.objects:
        if source_obj.type != 'MESH' or source_obj.name not in terrain_names:
            continue
        hlod_obj, source_tris, output_tris, material = copied_terrain(
            source_obj, hlod_collection, palette, terrain_ratios[source_obj.name])
        terrain_stats.append({
            'source': source_obj.name,
            'material': material,
            'source_triangles': source_tris,
            'hlod_triangles': output_tris,
            'ratio': terrain_ratios[source_obj.name],
        })
    if not terrain_stats:
        raise RuntimeError('No terrain meshes matched the meadow HLOD set.')

    proxies = proxy.add_proxies(layout, hlod_collection)
    # Fill large water cutouts with broad, stable surfaces so the island proxy
    # does not show the sky through pools/canal at the meadow camera distance.
    water = layout['water']
    canal_points = water['canal']['path']
    canal_start, canal_end = canal_points[0], canal_points[-1]
    canal_length = abs(canal_start[1] - canal_end[1])
    canal_center_y = (canal_start[1] + canal_end[1]) * 0.5
    proxies.append(proxy.make_box('HLOD canal water', (0, canal_center_y, -0.82),
                                  (water['canal']['width'], canal_length, 0.10),
                                  'HLOD_Water', hlod_collection))
    for pool in water['pools']:
        px, py = pool['center']
        pw, pd = pool['size']
        proxies.append(proxy.make_box(f"HLOD water pool {pool['id']}", (px, py, -0.85),
                                      (pw, pd, 0.10), 'HLOD_Water', hlod_collection))
    proxies.append(proxy.make_frustum('HLOD plaza stone disk', (0, 0, -0.15), 42, 42, 0.15,
                                      'HLOD_Stone', hlod_collection, 32))
    proxies.append(proxy.make_ring('HLOD plaza inner ring', (0, 0, 0.05), 18, 0.34,
                                   'HLOD_Accent', hlod_collection, 32, 4))
    proxy_count = len(proxies)
    proxy_triangles = sum(triangle_count(obj) for obj in proxies)
    objects = [obj for obj in hlod_collection.objects if obj.type == 'MESH']
    palette_groups = {name: [] for name in proxy.PALETTE}
    for obj in objects:
        if not obj.data.materials:
            raise RuntimeError(f'HLOD object {obj.name} has no material.')
        palette_name = obj.data.materials[0].name
        if palette_name not in palette_groups:
            raise RuntimeError(f'HLOD object {obj.name} uses unbounded material {palette_name}.')
        palette_groups[palette_name].append(obj)
    merged = [ck.join(group, f'Meadow HLOD / {name}')
              for name, group in palette_groups.items() if group]
    for obj in merged:
        for uv_layer in list(obj.data.uv_layers):
            obj.data.uv_layers.remove(uv_layer)
        for attribute in list(obj.data.color_attributes):
            obj.data.color_attributes.remove(attribute)
        obj.data.validate(verbose=False, clean_customdata=True)
    bpy.context.view_layer.update()

    estimated_triangles = sum(triangle_count(obj) for obj in merged)
    if estimated_triangles > args.limit_triangles:
        raise RuntimeError(f'Authored proxy HLOD exceeds cap: {estimated_triangles:,} > {args.limit_triangles:,}.')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in merged:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = merged[0]
    bpy.ops.export_scene.gltf(
        filepath=str(pending), export_format='GLB', use_selection=True,
        export_yup=True, export_apply=True, export_materials='EXPORT',
        export_vertex_color='NONE', export_animations=False, export_cameras=False,
        export_lights=False, export_extras=False,
    )
    exported_triangles, exported_materials, exported_images = glb_stats(pending)
    if exported_triangles > args.limit_triangles or exported_materials > len(proxy.PALETTE):
        pending.unlink(missing_ok=True)
        raise RuntimeError(
            f'HLOD cap failed: {exported_triangles:,} triangles/{args.limit_triangles:,}, '
            f'{exported_materials} materials/{len(proxy.PALETTE)}.'
        )
    if exported_images != 0:
        pending.unlink(missing_ok=True)
        raise RuntimeError(f'Proxy HLOD must have no texture images; found {exported_images}.')
    if pending.stat().st_size > BYTE_LIMIT:
        pending.unlink(missing_ok=True)
        raise RuntimeError(f'Uncompressed proxy HLOD already exceeds {BYTE_LIMIT:,} bytes.')
    for name, original in (('master', MASTER), ('source', FULL_SOURCE), ('full_runtime', FULL_RUNTIME)):
        if sha256(original) != source_hashes[name]:
            pending.unlink(missing_ok=True)
            raise RuntimeError(f'Protected R5 {name} changed during HLOD export.')
    pending.replace(args.candidate)

    material_stats = {}
    for obj in merged:
        material_stats[obj.data.materials[0].name] = triangle_count(obj)
    report = {
        'schema': 'aetherfield.meadow-city-hlod/2',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source': {
            'master_sha256': source_hashes['master'],
            'city_source_sha256': source_hashes['source'],
            'city_runtime_sha256': source_hashes['full_runtime'],
            'terrain_meshes': terrain_stats,
            'proxy_mesh_count': proxy_count,
            'proxy_triangle_count': proxy_triangles,
        },
        'candidate': {
            'path': str(args.candidate), 'sha256': sha256(args.candidate),
            'bytes': args.candidate.stat().st_size, 'triangles': exported_triangles,
            'materials': exported_materials, 'embedded_images': exported_images,
            'material_triangles': material_stats,
            'triangle_limit': args.limit_triangles, 'byte_limit': BYTE_LIMIT,
            'palette': {name: color for name, (color, _) in proxy.PALETTE.items()},
            'method': 'source island terrain plus original-expression low-poly town silhouettes; no city-wide collapse',
        },
        'preserved_sources': True,
    }
    temp_stats = args.stats.with_name(args.stats.name + '.pending')
    temp_stats.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    temp_stats.replace(args.stats)
    print(json.dumps({
        'result': 'ok', 'triangles': exported_triangles, 'materials': exported_materials,
        'images': exported_images, 'bytes': args.candidate.stat().st_size,
        'candidate_sha256': sha256(args.candidate), 'terrain_meshes': len(terrain_stats),
        'proxy_meshes': proxy_count, 'candidate': str(args.candidate), 'stats': str(args.stats),
    }, indent=2))


if __name__ == '__main__':
    main()
