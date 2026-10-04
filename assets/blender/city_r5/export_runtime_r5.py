"""Create a decimated R5 runtime candidate from the preserved full Blender master.

This script never saves the master and refuses the source GLB path. Candidate
and stats destinations are mandatory so experiments cannot replace source art.

Example (Blender 5.2, from repo root):
  blender --background assets/models/reference-city/r5/reference_city.blend \
    --python-exit-code 1 --python assets/blender/city_r5/export_runtime_r5.py -- \
    --candidate target/r5-runtime/city-runtime-candidate.glb \
    --stats target/r5-runtime/city-runtime-candidate.stats.json
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
FULL_GLB = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'city-source.glb'
TEXTURES = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'textures'
QUATERNIUS_TEXTURES = (ROOT / 'assets' / 'third-party' / 'quaternius-fantasy-props-megakit'
                       / 'standard' / 'stall-cart' / 'glTF')
QUATERNIUS_TEXTURE_NAMES = {
    'T_Trim_Metal_BaseColor.png', 'T_Trim_Metal_Normal.png', 'T_Trim_Metal_ORM.png',
    'T_Trim_Furniture_BaseColor.png', 'T_Trim_Furniture_Normal.png', 'T_Trim_Furniture_ORM.png',
    'T_Trim_Cloth_BaseColor.png', 'T_Trim_Cloth_Normal.png', 'T_Trim_Cloth_ORM.png',
}
RUNTIME_PREFIXES = ('anim_', 'fx_', 'emit_', 'light_')
TARGET_TRIANGLES = 900_000
EXPECTED_STATIC_MATERIAL_GROUPS = 43  # 42 authored groups + Quaternius' featured stall-cart bucket.
EXPECTED_RUNTIME_HOOKS = 34

# These material groups carry high-density authored microgeometry. Major
# building, castle, terrain, roof and landmark silhouette groups are excluded.
DEFAULT_RATIOS = {
    'stone_trim_carved': 0.80,
    'timber_dark': 0.80,
    'metal_iron': 0.80,
    'metal_gold': 0.80,
    'wood_planks_light': 0.80,
}


def parse_args():
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, help='Explicit output path for the runtime GLB candidate.')
    parser.add_argument('--stats', required=True, help='Explicit output path for the JSON measurement report.')
    parser.add_argument('--ratio-profile', help='Optional JSON object mapping eligible material names to ratios.')
    parser.add_argument('--limit', type=int, default=TARGET_TRIANGLES, help='Maximum exported triangle count (default: 900000).')
    args = parser.parse_args(raw)
    args.candidate = Path(args.candidate).expanduser().resolve()
    args.stats = Path(args.stats).expanduser().resolve()
    if args.candidate == args.stats:
        parser.error('--candidate and --stats must be different paths.')
    protected = {MASTER.resolve(), FULL_GLB.resolve()}
    if args.candidate in protected or args.stats in protected:
        parser.error('Candidate and stats paths may not overwrite the full master or full source GLB.')
    if args.candidate.suffix.lower() != '.glb':
        parser.error('--candidate must end in .glb.')
    if args.stats.suffix.lower() != '.json':
        parser.error('--stats must end in .json.')
    profile = dict(DEFAULT_RATIOS)
    if args.ratio_profile:
        supplied = json.loads(Path(args.ratio_profile).expanduser().read_text(encoding='utf-8'))
        if not isinstance(supplied, dict):
            parser.error('--ratio-profile must contain a JSON object.')
        unknown = set(supplied) - set(DEFAULT_RATIOS)
        if unknown:
            parser.error(f'Ratio profile contains protected/unsupported materials: {sorted(unknown)}')
        profile.update({str(key): float(value) for key, value in supplied.items()})
    invalid = {name: value for name, value in profile.items() if not 0.0 < value <= 1.0}
    if invalid:
        parser.error(f'All Decimate ratios must be in (0, 1]: {invalid}')
    args.ratios = profile
    return args


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def object_triangles(obj, depsgraph=None) -> int:
    if depsgraph is None:
        return sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return sum(len(poly.vertices) - 2 for poly in mesh.polygons)
    finally:
        evaluated.to_mesh_clear()


def first_material_name(obj) -> str:
    if not obj.data.materials:
        raise RuntimeError(f'Export mesh {obj.name!r} has no material.')
    return obj.data.materials[0].name


def refresh_texture_images():
    """Reload final foundry maps in memory without saving the source master."""
    used = {}
    for material in bpy.data.materials:
        if not material.use_nodes or material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                used[node.image.name] = node.image
    records = []
    missing = []
    for image in used.values():
        name = image.name
        if not name.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.exr')):
            name = image.filepath.replace('\\', '/').rsplit('/', 1)[-1]
        third_party = name in QUATERNIUS_TEXTURE_NAMES
        source = (QUATERNIUS_TEXTURES if third_party else TEXTURES) / name
        if not source.is_file():
            missing.append({'image': image.name, 'expected': str(source)})
            continue
        image.filepath = (bpy.path.relpath(str(source)) if third_party else f'//textures/{name}')
        image.reload()
        if image.size[0] <= 0 or image.size[1] <= 0:
            raise RuntimeError(f'Could not load final R5 texture {source}.')
        records.append({'name': image.name, 'path': source.relative_to(ROOT).as_posix(),
                        'width': int(image.size[0]), 'height': int(image.size[1])})
    if missing:
        raise RuntimeError('Missing final R5 texture maps: ' + json.dumps(missing))
    return records


def glb_triangle_count(path: Path) -> tuple[int, int, int]:
    """Return (triangle count, mesh count, node count) from GLB JSON accessors."""
    with path.open('rb') as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise RuntimeError('Candidate GLB is truncated before its header.')
        magic, version, declared_size = struct.unpack('<III', header)
        if magic != 0x46546C67 or version != 2 or declared_size != path.stat().st_size:
            raise RuntimeError('Candidate GLB header/version/length is invalid.')
        chunk_header = stream.read(8)
        if len(chunk_header) != 8:
            raise RuntimeError('Candidate GLB is missing its JSON chunk.')
        json_length, chunk_type = struct.unpack('<II', chunk_header)
        if chunk_type != 0x4E4F534A:
            raise RuntimeError('Candidate GLB first chunk is not JSON.')
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
    return triangles, len(document.get('meshes', [])), len(document.get('nodes', []))


def group_triangles(objects, *, evaluated=False) -> dict[str, int]:
    depsgraph = bpy.context.evaluated_depsgraph_get() if evaluated else None
    grouped = {}
    for obj in objects:
        grouped[first_material_name(obj)] = grouped.get(first_material_name(obj), 0) + object_triangles(obj, depsgraph)
    return dict(sorted(grouped.items()))


def atomic_write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.pending')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    args = parse_args()
    if Path(bpy.data.filepath).resolve() != MASTER.resolve():
        raise RuntimeError(f'Load the preserved full master before running this exporter: {MASTER}')
    if not MASTER.is_file() or not TEXTURES.is_dir():
        raise FileNotFoundError('Full R5 master or finalized texture folder is missing.')
    master_hash_before = file_sha256(MASTER)
    full_glb_hash_before = file_sha256(FULL_GLB)
    args.candidate.parent.mkdir(parents=True, exist_ok=True)
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    # Keep .glb as the final suffix: Blender's glTF exporter appends .glb if a
    # temporary name ends in another extension.
    candidate_tmp = args.candidate.with_name(args.candidate.stem + '.pending' + args.candidate.suffix)
    if candidate_tmp.exists():
        candidate_tmp.unlink()

    texture_records = refresh_texture_images()
    presentation = bpy.data.collections.get('Presentation only')
    presentation_objects = set(presentation.all_objects) if presentation else set()
    scene_objects = [obj for obj in bpy.context.scene.objects if obj not in presentation_objects]
    meshes = [obj for obj in scene_objects if obj.type == 'MESH']
    hooks = [obj for obj in scene_objects if obj.name.startswith(RUNTIME_PREFIXES)]
    static = [obj for obj in meshes if not obj.name.startswith(RUNTIME_PREFIXES)]
    source_by_material = group_triangles(static)
    hook_triangles = sum(object_triangles(obj) for obj in hooks if obj.type == 'MESH')
    source_total = sum(source_by_material.values()) + hook_triangles

    featured_cart = bpy.data.objects.get('market stall 1-1 Quaternius CC0 stall cart')
    expected_cart_materials = {'MI_Trim_Metal', 'MI_Trim_Furniture', 'MI_Banner'}
    if featured_cart is None or featured_cart.type != 'MESH':
        raise RuntimeError('The source master is missing the selected Quaternius CC0 stall cart.')
    ck.normalize_imported_gltf_prop_attributes(featured_cart)
    cart_materials = {mat.name for mat in featured_cart.data.materials if mat}
    if not expected_cart_materials.issubset(cart_materials):
        raise RuntimeError(f'Featured Quaternius cart lost PBR materials: {sorted(expected_cart_materials - cart_materials)}')

    # Match the production source exporter: detach static meshes from helper
    # empties while preserving their world transforms. Runtime hook parents stay.
    bpy.context.view_layer.update()
    for obj in static:
        if obj.parent and obj.parent.type == 'EMPTY':
            world_matrix = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = world_matrix
    bpy.context.view_layer.update()

    merged, _ = ck.merge_by_material(static, 'City')
    if len(merged) != EXPECTED_STATIC_MATERIAL_GROUPS or len(hooks) != EXPECTED_RUNTIME_HOOKS:
        raise RuntimeError(f'Full source selection guard failed: {len(merged)} static material groups, {len(hooks)} hooks.')
    merged_by_material = {first_material_name(obj): obj for obj in merged}
    if set(args.ratios) - set(merged_by_material):
        raise RuntimeError(f'Configured decimation materials were not found: {sorted(set(args.ratios) - set(merged_by_material))}')

    for material_name, ratio in args.ratios.items():
        obj = merged_by_material[material_name]
        modifier = obj.modifiers.new(name=f'Runtime Decimate {material_name}', type='DECIMATE')
        modifier.decimate_type = 'COLLAPSE'
        modifier.ratio = ratio

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    material_stats = {}
    static_after_by_material = {}
    for obj in merged:
        material_name = first_material_name(obj)
        before = source_by_material.get(material_name, 0)
        after = object_triangles(obj, depsgraph)
        static_after_by_material[material_name] = after
        ratio = args.ratios.get(material_name)
        material_stats[material_name] = {
            'source_triangles_before_merge': before,
            'merged_triangles_before_decimation': object_triangles(obj),
            'evaluated_triangles_after': after,
            'decimate_ratio': ratio,
            'reduction_triangles': object_triangles(obj) - after,
            'reduction_percent': round(100.0 * (object_triangles(obj) - after) / max(object_triangles(obj), 1), 3),
            'treatment': 'Decimate collapse' if ratio is not None else 'unchanged',
        }
    estimated_total = sum(static_after_by_material.values()) + hook_triangles
    if estimated_total > args.limit:
        raise RuntimeError(
            f'Decimation profile yields {estimated_total:,} estimated triangles, above {args.limit:,}; '
            'candidate will not be published. Try a lower ratio only on the listed detail groups.'
        )

    export_objects = merged + hooks
    ck.export_glb(export_objects, candidate_tmp)
    exported_triangles, exported_meshes, exported_nodes = glb_triangle_count(candidate_tmp)
    if exported_triangles > args.limit:
        candidate_tmp.unlink(missing_ok=True)
        raise RuntimeError(f'GLB accessor count is {exported_triangles:,}, above the {args.limit:,} triangle limit.')
    if exported_triangles != estimated_total:
        candidate_tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f'Evaluated-mesh estimate {estimated_total:,} differs from exported GLB accessor count '
            f'{exported_triangles:,}; candidate not published.'
        )
    if file_sha256(MASTER) != master_hash_before or file_sha256(FULL_GLB) != full_glb_hash_before:
        candidate_tmp.unlink(missing_ok=True)
        raise RuntimeError('Protected source master or full source GLB changed during export; candidate not published.')
    candidate_tmp.replace(args.candidate)

    hook_mesh_triangles = sum(object_triangles(obj, depsgraph) for obj in hooks if obj.type == 'MESH')
    report = {
        'schema': 'aetherfield.runtime-city-budget/1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_master': {
            'path': MASTER.relative_to(ROOT).as_posix(),
            'sha256': master_hash_before,
            'bytes': MASTER.stat().st_size,
            'scene_meshes_excluding_presentation': len(meshes),
            'source_static_triangles': sum(source_by_material.values()),
            'source_hook_mesh_triangles': hook_triangles,
            'source_total_triangles': source_total,
        },
        'candidate': {
            'path': str(args.candidate),
            'sha256': file_sha256(args.candidate),
            'bytes': args.candidate.stat().st_size,
            'glb_accessor_triangles': exported_triangles,
            'mesh_primitives': exported_meshes,
            'nodes': exported_nodes,
            'limit_triangles': args.limit,
            'static_material_groups': len(merged),
            'runtime_hooks': len(hooks),
            'runtime_hook_meshes': sum(obj.type == 'MESH' for obj in hooks),
            'runtime_hook_mesh_triangles': hook_mesh_triangles,
        },
        'decimation_profile': {
            'ratios': args.ratios,
            'material_groups': material_stats,
            'static_triangles_before': sum(source_by_material.values()),
            'static_triangles_after': sum(static_after_by_material.values()),
            'total_triangles_after': estimated_total,
            'visual_tradeoffs': [
                'Only carved trim and timber/iron/gold microdetail material groups are simplified.',
                'Castle and building massing, terrain, roofs, major props, landmarks, textures, and runtime hooks are unchanged.',
                'Fine grooves, narrow bevels, and tiny hardware may look smoother at close range; confirm in a close-up runtime capture.',
            ],
        },
        'texture_images_refreshed_in_memory': texture_records,
        'source_master_saved': False,
        'full_source_glb_overwritten': False,
        'full_source_glb_sha256_preserved': full_glb_hash_before,
    }
    atomic_write_json(args.stats, report)
    print(json.dumps({
        'result': 'ok',
        'source_triangles': source_total,
        'candidate_triangles': exported_triangles,
        'candidate_bytes': args.candidate.stat().st_size,
        'mesh_primitives': exported_meshes,
        'hooks': len(hooks),
        'ratios': args.ratios,
        'candidate': str(args.candidate),
        'stats': str(args.stats),
    }, indent=2))


if __name__ == '__main__':
    main()
