"""Export a full R5 source candidate from the authored master without saving it.

Use mandatory separate candidate and measurement paths. This is the source-only
repair route; it neither runs the city assembler nor decimates the authored art.
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
from export_runtime_r5 import refresh_texture_images  # noqa: E402

CITY_DIR = ROOT / 'assets/models/reference-city/r5'
MASTER = CITY_DIR / 'reference_city.blend'
SOURCE = CITY_DIR / 'city-source.glb'
RUNTIME = CITY_DIR / 'city-runtime.glb'
RUNTIME_PREFIXES = ('anim_', 'fx_', 'emit_', 'light_')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--stats', required=True)
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(raw)
    args.candidate = Path(args.candidate).expanduser().resolve()
    args.stats = Path(args.stats).expanduser().resolve()
    protected = {MASTER.resolve(), SOURCE.resolve(), RUNTIME.resolve()}
    if args.candidate in protected or args.stats in protected:
        parser.error('Candidate and stats must not overwrite the master, source, or runtime.')
    if args.candidate == args.stats or args.candidate.suffix.lower() != '.glb' or args.stats.suffix.lower() != '.json':
        parser.error('Use separate explicit .glb candidate and .json stats paths.')
    return args


def main():
    args = parse_args()
    if Path(bpy.data.filepath).resolve() != MASTER.resolve():
        raise RuntimeError(f'Load the authored R5 master before exporting: {MASTER}')
    master_before = sha256(MASTER)
    source_before = sha256(SOURCE)
    # Use the same final PNG reload as the runtime exporter. This prevents a
    # saved Blender image cache from exporting stale foundry maps after a
    # material-only revision, without saving or changing the source master.
    texture_records = refresh_texture_images()
    presentation = bpy.data.collections.get('Presentation only')
    excluded = set(presentation.all_objects) if presentation else set()
    scene_objects = [obj for obj in bpy.context.scene.objects if obj not in excluded]
    meshes = [obj for obj in scene_objects if obj.type == 'MESH']
    hooks = [obj for obj in scene_objects if obj.name.startswith(RUNTIME_PREFIXES)]
    static = [obj for obj in meshes if not obj.name.startswith(RUNTIME_PREFIXES)]
    featured_cart = bpy.data.objects.get('market stall 1-1 Quaternius CC0 stall cart')
    if featured_cart is None or featured_cart.type != 'MESH':
        raise RuntimeError('The authored master is missing its existing CC0 market cart.')
    ck.normalize_imported_gltf_prop_attributes(featured_cart)
    bpy.context.view_layer.update()
    before = {obj.name: obj.matrix_world.copy() for obj in static}
    detached = 0
    for obj in static:
        if obj.parent and obj.parent.type == 'EMPTY':
            world_matrix = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = world_matrix
            detached += 1
    bpy.context.view_layer.update()
    max_error = max(abs(before[obj.name][row][column] - obj.matrix_world[row][column])
                    for obj in static for row in range(4) for column in range(4))
    if max_error > 1e-4:
        raise RuntimeError(f'Static world placement changed during detachment: {max_error}')
    source_triangles = ck.triangle_count(meshes)
    merged, _ = ck.merge_by_material(static, 'City')
    if len(merged) != 43 or len(hooks) != 34:
        raise RuntimeError(f'Unexpected export selection: {len(merged)} material groups, {len(hooks)} hooks.')
    args.candidate.parent.mkdir(parents=True, exist_ok=True)
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    ck.export_glb(merged + hooks, args.candidate)
    with args.candidate.open('rb') as stream:
        header = stream.read(20)
        if header[:4] != b'glTF' or struct.unpack_from('<I', header, 4)[0] != 2:
            raise RuntimeError('The exported source candidate is not a GLB 2.0 file.')
        json_length = struct.unpack_from('<I', header, 12)[0]
        document = json.loads(stream.read(json_length).decode('utf-8').rstrip('\0 '))
    triangles = sum(document['accessors'][primitive.get('indices', primitive['attributes']['POSITION'])]['count'] // 3
                    for mesh in document['meshes'] for primitive in mesh['primitives'])
    if triangles != source_triangles:
        raise RuntimeError(f'Full source triangle count changed: {triangles} != {source_triangles}')
    if sha256(MASTER) != master_before or sha256(SOURCE) != source_before:
        raise RuntimeError('The protected master or original generated source changed during candidate export.')
    report = {
        'schema': 'aetherfield.city-source-transform-repair/1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'master_sha256': master_before, 'original_source_sha256': source_before,
        'source_master_saved': False, 'original_source_overwritten': False,
        'static_meshes_checked': len(static), 'detached_meshes': detached,
        'max_world_matrix_error': max_error,
        'texture_images_refreshed': texture_records,
        'candidate': {'sha256': sha256(args.candidate), 'bytes': args.candidate.stat().st_size,
                      'triangles': triangles, 'meshes': len(document['meshes']),
                      'materials': len(document['materials']), 'images': len(document.get('images', [])),
                      'static_material_groups': len(merged), 'runtime_hooks': len(hooks)},
    }
    args.stats.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
