"""Inventory the read-only R5 master; optionally export gate/plaza source GLBs.

Writes only the new district-candidates directory and its dedicated evidence
receipt. No assembly, decimation, master save, runtime packaging or publication.
The installed Blender's operator RNA is checked before exporting. Texture
references remain linked to the existing shared final PNGs, rather than embedding
every city's image in every district.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.kdtree import KDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CITY = ROOT / 'assets/models/reference-city/r5'
MASTER = CITY / 'reference_city.blend'
DESTINATION = CITY / 'district-candidates'
RECEIPT = ROOT / 'planning/evidence/city-district-candidate-20261001.json'
sys.path.insert(0, str(HERE / 'lib'))
sys.path.insert(0, str(HERE))
import citykit as ck  # noqa: E402
from export_runtime_r5 import refresh_texture_images  # noqa: E402
from repair_landmark_placements_r5 import specs  # noqa: E402

GRID_METRES = 80
RUNTIME_PREFIXES = ('anim_', 'fx_', 'emit_', 'light_')
PROTECTED = [MASTER, CITY / 'city-source.glb', CITY / 'city-runtime.glb',
             ROOT / 'apps/client/src/assets/models/env_reference_city.glb',
             ROOT / 'apps/client/src/assets/models/env_reference_city_hlod.glb']


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def shared_position(blender_point):
    return [float(blender_point[0]), float(blender_point[2]), 176 + float(blender_point[1])]


def district_id(point):
    return f'district-x{math.floor((point[0] + 120) / GRID_METRES)}-z{math.floor((point[2] - 16) / GRID_METRES)}'


def object_bounds(obj):
    points = [shared_position(obj.matrix_world @ Vector(corner)) for corner in obj.bound_box] if obj.type == 'MESH' else [shared_position(obj.matrix_world.translation)]
    return {'min': [min(p[axis] for p in points) for axis in range(3)],
            'max': [max(p[axis] for p in points) for axis in range(3)]}


def union_bounds(objects):
    bounds = [object_bounds(obj) for obj in objects]
    return {'min': [min(b['min'][axis] for b in bounds) for axis in range(3)],
            'max': [max(b['max'][axis] for b in bounds) for axis in range(3)]}


def triangles(objects):
    return sum(len(poly.vertices) - 2 for obj in objects if obj.type == 'MESH' for poly in obj.data.polygons)


def material_resources(objects, resource_lookup):
    materials = {mat.name: mat for obj in objects if obj.type == 'MESH' for mat in obj.data.materials if mat}
    ids = set()
    for mat in materials.values():
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    ids.add(resource_lookup[node.image.name]['id'])
    return sorted(materials), sorted(ids)


def read_glb(path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', raw)
    json_len, json_type = struct.unpack_from('<II', raw, 12)
    if magic != 0x46546C67 or version != 2 or length != len(raw) or json_type != 0x4E4F534A:
        raise RuntimeError(f'Invalid GLB header: {path}')
    document = json.loads(raw[20:20 + json_len].decode('utf-8').rstrip('\0 '))
    offset = 20 + json_len
    bin_length, bin_type = struct.unpack_from('<II', raw, offset)
    if bin_type != 0x004E4942:
        raise RuntimeError('Expected an uncompressed source GLB binary chunk.')
    return document, raw[offset + 8:offset + 8 + bin_length]


def externalize_images(path, resource_lookup):
    """Repack non-image views and retain original material texture bindings."""
    document, binary = read_glb(path)
    image_views = {image['bufferView'] for image in document.get('images', []) if 'bufferView' in image}
    bindings = []
    for image in document.get('images', []):
        name = image.get('name', '')
        resource = resource_lookup.get(name) or resource_lookup.get(Path(name).name)
        if resource is None:
            raise RuntimeError(f'No final shared source texture for exported image {name!r}.')
        source = ROOT / resource['path']
        image.pop('bufferView', None)
        image.pop('mimeType', None)
        image['uri'] = os.path.relpath(source, path.parent).replace('\\', '/')
        bindings.append({'image': name, 'resource_id': resource['id'], 'uri': image['uri']})
    repacked = bytearray()
    remap = {}
    kept = []
    for index, view in enumerate(document.get('bufferViews', [])):
        if index in image_views:
            continue
        while len(repacked) % 4:
            repacked.append(0)
        offset = view.get('byteOffset', 0)
        payload = binary[offset:offset + view['byteLength']]
        remap[index] = len(kept)
        kept.append({**view, 'byteOffset': len(repacked)})
        repacked.extend(payload)
    document['bufferViews'] = kept

    def remap_references(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'bufferView':
                    value[key] = remap[child]
                else:
                    remap_references(child)
        elif isinstance(value, list):
            for child in value:
                remap_references(child)

    remap_references(document)
    document['buffers'][0]['byteLength'] = len(repacked)
    encoded = json.dumps(document, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
    encoded += b' ' * (-len(encoded) % 4)
    repacked += b'\0' * (-len(repacked) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(repacked)
    path.write_bytes(struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(encoded), 0x4E4F534A) + encoded + struct.pack('<II', len(repacked), 0x004E4942) + repacked)
    count = sum(document['accessors'][primitive.get('indices', primitive['attributes']['POSITION'])]['count'] // 3
                for mesh in document['meshes'] for primitive in mesh['primitives'])
    resources = {row['resource_id']: next(resource for resource in resource_lookup.values() if resource['id'] == row['resource_id']) for row in bindings}
    return {'path': relative(path), 'sha256': sha256(path), 'bytes': path.stat().st_size,
            'triangles': count, 'meshes': len(document['meshes']), 'nodes': len(document['nodes']),
            'materials': len(document.get('materials', [])), 'images': len(document.get('images', [])),
            'embedded_images': 0, 'geometry_buffer_bytes': len(repacked),
            'resource_ids': sorted(resources), 'shared_image_bindings': bindings,
            'conservative_resident_bytes': len(repacked) * 2 + sum(r['rgba8_full_mip_bytes'] + r['bytes'] for r in resources.values())}


def verify_source_witnesses(path, objects):
    """Read exported world coordinates and UVs back for every owned static mesh."""
    document, binary = read_glb(path)
    samples = defaultdict(list)

    def accessor_values(index, width):
        accessor = document['accessors'][index]
        if accessor['componentType'] != 5126 or 'sparse' in accessor:
            raise RuntimeError('Witness readback expects uncompressed FLOAT attributes.')
        view = document['bufferViews'][accessor['bufferView']]
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        stride = view.get('byteStride', width * 4)
        return [struct.unpack_from('<' + 'f' * width, binary, offset + row * stride) for row in range(accessor['count'])]

    def visit(index, parent):
        node = document['nodes'][index]
        if 'matrix' in node:
            local = Matrix([[node['matrix'][column * 4 + row] for column in range(4)] for row in range(4)])
        else:
            rotation = node.get('rotation', [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get('translation', [0, 0, 0])),
                                       Quaternion((rotation[3], *rotation[:3])),
                                       Vector(node.get('scale', [1, 1, 1])))
        world = parent @ local
        if 'mesh' in node:
            for primitive in document['meshes'][node['mesh']]['primitives']:
                attributes = primitive['attributes']
                if not {'POSITION', 'NORMAL', 'TEXCOORD_0', 'COLOR_0'} <= set(attributes):
                    raise RuntimeError('Candidate omitted required source position/normal/UV0/COLOR_0 attributes.')
                material = document['materials'][primitive['material']]['name']
                positions = accessor_values(attributes['POSITION'], 3)
                uvs = accessor_values(attributes['TEXCOORD_0'], 2)
                samples[material].extend((world @ Vector(position), uv) for position, uv in zip(positions, uvs))
        for child in node.get('children', []):
            visit(child, world)

    for index in document['scenes'][document.get('scene', 0)]['nodes']:
        visit(index, Matrix.Identity(4))
    trees = {}
    for material, rows in samples.items():
        tree = KDTree(len(rows))
        for index, (point, _) in enumerate(rows):
            tree.insert(point, index)
        tree.balance()
        trees[material] = tree
    checked = 0
    default_uv_meshes = 0
    max_position_error = max_uv_error = 0
    for obj in objects:
        if obj.type != 'MESH' or obj.name.startswith(RUNTIME_PREFIXES):
            continue
        layer = obj.data.uv_layers.get('UVMap')
        if not layer:
            # The existing source exporter supplies default UV0 to untextured
            # details. Preserve authored UVs; check that default on copies only.
            default_uv_meshes += 1
        for polygon in [obj.data.polygons[0], obj.data.polygons[-1]]:
            loop = polygon.loop_indices[0]
            point = obj.matrix_world @ obj.data.vertices[obj.data.loops[loop].vertex_index].co
            expected_point = Vector((point.x, point.z, -point.y))
            uv = layer.data[loop].uv if layer else (0, 0)
            expected_uv = (uv[0], 1 - uv[1])
            material = obj.data.materials[polygon.material_index].name
            nearby = trees[material].find_range(expected_point, 0.001)
            if not nearby:
                raise RuntimeError(f'Candidate lost world-space witness: {obj.name}')
            matches = [(max(abs(samples[material][index][1][axis] - expected_uv[axis]) for axis in range(2)), distance)
                       for _, index, distance in nearby]
            uv_error, position_error = min(matches)
            if uv_error > 0.0001:
                raise RuntimeError(f'Candidate lost UV witness: {obj.name}: {uv_error}')
            checked += 1
            max_position_error = max(max_position_error, position_error)
            max_uv_error = max(max_uv_error, uv_error)
    return {'result': 'PASS', 'static_meshes_verified': checked // 2, 'world_position_uv_witnesses': checked,
            'max_world_position_error_m': max_position_error, 'max_uv_error': max_uv_error,
            'source_meshes_with_default_uv0': default_uv_meshes,
            'required_attributes_verified': ['POSITION', 'NORMAL', 'TEXCOORD_0', 'COLOR_0']}


def export_district(objects, cell_id, label, resource_lookup):
    collection = bpy.data.collections.new(f'District candidate {label}')
    bpy.context.scene.collection.children.link(collection)
    copies = []
    max_error = 0
    try:
        for obj in objects:
            copy = obj.copy()
            if obj.data:
                copy.data = obj.data.copy()
            world = obj.matrix_world.copy()
            copy.parent = None
            collection.objects.link(copy)
            copy.matrix_world = world
            copy['city_source_object'] = obj.name
            copy['city_district_id'] = cell_id
            if obj.name.startswith(RUNTIME_PREFIXES):
                copy.name = obj.name + '_candidate'
            copies.append(copy)
            max_error = max(max_error, max(abs(world[r][c] - copy.matrix_world[r][c]) for r in range(4) for c in range(4)))
            if 'Quaternius CC0 stall cart' in obj.name:
                ck.normalize_imported_gltf_prop_attributes(copy)
        bpy.context.view_layer.update()
        static = [obj for obj in copies if obj.type == 'MESH' and not obj.name.startswith(RUNTIME_PREFIXES)]
        hooks = [obj for obj in copies if obj.name.startswith(RUNTIME_PREFIXES)]
        merged, _ = ck.merge_by_material(static, f'Candidate {cell_id}')
        selection = merged + hooks
        path = DESTINATION / f'{label}.source-candidate.glb'
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selection:
            obj.select_set(True)
            obj['city_district_id'] = cell_id
        bpy.context.view_layer.objects.active = selection[0]
        bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True,
                                  export_yup=True, at_collection_center=False, export_apply=True,
                                  export_materials='EXPORT', export_image_format='AUTO',
                                  export_unused_images=False, export_unused_textures=False,
                                  export_vertex_color='MATERIAL', export_extras=True,
                                  export_animations=False, export_cameras=False, export_lights=False)
        report = externalize_images(path, resource_lookup)
        report.update({'label': label, 'cell_id': cell_id, 'source_static_meshes': len(static),
                       'source_hooks': len(hooks), 'static_material_groups': len(merged),
                       'max_copy_world_matrix_error': max_error, 'source_triangles': triangles(objects)})
        if report['triangles'] != report['source_triangles'] or max_error > 1e-4:
            raise RuntimeError(f'Candidate changed source triangle count or world placement: {report}')
        report['source_witness_readback'] = verify_source_witnesses(path, objects)
        return report
    finally:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-representatives', action='store_true', help='Export ONLY gate and plaza into new candidate paths.')
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(raw)
    if Path(bpy.data.filepath).resolve() != MASTER.resolve():
        raise RuntimeError('Load the current authored R5 master; no reconstruction is allowed.')
    operator_properties = bpy.ops.export_scene.gltf.get_rna_type().properties
    for name in ['use_selection', 'export_yup', 'at_collection_center', 'export_apply',
                 'export_unused_images', 'export_unused_textures', 'export_vertex_color', 'export_extras']:
        if name not in operator_properties:
            raise RuntimeError(f'Installed Blender exporter lacks required option {name}.')
    before_hashes = {relative(path): sha256(path) for path in PROTECTED}
    before_matrices = {obj.name: tuple(float(v) for row in obj.matrix_world for v in row) for obj in bpy.context.scene.objects}
    before_counts = {'objects': len(bpy.context.scene.objects), 'materials': len(bpy.data.materials), 'meshes': len(bpy.data.meshes)}
    texture_records = refresh_texture_images()
    resource_lookup = {}
    for row in texture_records:
        path = ROOT / row['path']
        digest = sha256(path)
        width, height = row['width'], row['height']
        mip_pixels = 0
        while True:
            mip_pixels += width * height
            if width == height == 1:
                break
            width, height = max(1, width // 2), max(1, height // 2)
        resource = {**row, 'id': f'r5-image-{digest}', 'sha256': digest,
                    'bytes': path.stat().st_size, 'rgba8_full_mip_bytes': mip_pixels * 4}
        resource_lookup[row['name']] = resource
        resource_lookup[path.name] = resource
        resource_lookup[path.stem] = resource
    layout = json.loads((HERE / 'layout.json').read_text(encoding='utf-8'))
    roots = {}
    root_records = []
    for name, identifier, _ in specs(layout):
        root = bpy.data.objects.get(f'kit_{name}')
        if root is None:
            raise RuntimeError(f'Current authored root missing: kit_{name}')
        stable_id = f'r5-root-{name}'
        owner = district_id(shared_position(root.matrix_world.translation))
        roots[root.name] = owner
        children = [obj for obj in root.children_recursive if obj.type == 'MESH']
        root_records.append({'id': stable_id, 'layout_id': identifier, 'name': root.name, 'district_id': owner,
                             'blender_position': list(root.matrix_world.translation),
                             'shared_position': shared_position(root.matrix_world.translation),
                             'rotation_z_radians': root.rotation_euler.z, 'bounds': union_bounds(children),
                             'static_meshes': sum(not obj.name.startswith(RUNTIME_PREFIXES) for obj in children),
                             'triangles': triangles(children)})
    if len(root_records) != 37:
        raise RuntimeError(f'Expected 37 authored roots, found {len(root_records)}.')
    presentation = bpy.data.collections.get('Presentation only')
    excluded = set(presentation.all_objects) if presentation else set()
    objects = [obj for obj in bpy.context.scene.objects if obj not in excluded and (obj.type == 'MESH' or obj.name.startswith(RUNTIME_PREFIXES))]
    ownership = defaultdict(list)
    large_parts = []
    for obj in objects:
        parent = obj.parent
        while parent and parent.name not in roots:
            parent = parent.parent
        bound = object_bounds(obj)
        width, depth = bound['max'][0] - bound['min'][0], bound['max'][2] - bound['min'][2]
        if parent:
            owner = roots[parent.name]
        elif width > GRID_METRES or depth > GRID_METRES:
            owner = 'city-wide-support'
            large_parts.append({'source_object': obj.name, 'owner': owner, 'bounds': bound, 'triangles': triangles([obj]),
                                'reason': 'Whole authored mesh exceeds a district; no triangle cutting or duplicated terrain.'})
        else:
            center = [(bound['min'][axis] + bound['max'][axis]) / 2 for axis in range(3)]
            owner = district_id(center)
        ownership[owner].append(obj)
    resources = {row['id']: row for row in resource_lookup.values()}
    cells = []
    for owner, owned in sorted(ownership.items()):
        bound = union_bounds(owned)
        materials, resource_ids = material_resources(owned, resource_lookup)
        static = [obj for obj in owned if obj.type == 'MESH' and not obj.name.startswith(RUNTIME_PREFIXES)]
        hooks = [obj for obj in owned if obj.name.startswith(RUNTIME_PREFIXES)]
        cells.append({'id': owner, 'bounds': {'minX': bound['min'][0], 'maxX': bound['max'][0], 'minZ': bound['min'][2], 'maxZ': bound['max'][2]},
                      'bounds_3d': bound, 'root_ids': sorted(row['id'] for row in root_records if row['district_id'] == owner),
                      'source_static_meshes': len(static), 'source_hooks': len(hooks), 'source_triangles': triangles(owned),
                      'material_ids': materials, 'resource_ids': resource_ids,
                      'source_object_names': sorted(obj.name for obj in owned),
                      'lods': {}, 'runtime_eligible': False,
                      'culling_limit': 'Use full owned geometry AABB; root/cell centre alone is insufficient for overhanging geometry.'})
    DESTINATION.mkdir(parents=True, exist_ok=True)
    exports = []
    if args.export_representatives:
        for label, root_name in [('gate', 'kit_town_gate'), ('plaza', 'kit_plaza_fountain')]:
            owner = roots[root_name]
            exports.append(export_district(ownership[owner], owner, label, resource_lookup))
    for export in exports:
        cell = next(row for row in cells if row['id'] == export['cell_id'])
        cell['lods']['near'] = {'path': export['path'], 'transferBytes': export['bytes'],
                                'residentBytes': export['conservative_resident_bytes'], 'candidateOnly': True,
                                'resourceIds': export['resource_ids']}
    after_matrices = {obj.name: tuple(float(v) for row in obj.matrix_world for v in row) for obj in bpy.context.scene.objects}
    max_matrix_error = max(abs(value - after_matrices[name][index]) for name, matrix in before_matrices.items() for index, value in enumerate(matrix))
    after_hashes = {relative(path): sha256(path) for path in PROTECTED}
    if before_hashes != after_hashes or max_matrix_error > 1e-4 or len(bpy.context.scene.objects) != before_counts['objects']:
        raise RuntimeError('The protected assets or original scene placement changed.')
    assigned = [obj.name for owned in ownership.values() for obj in owned]
    manifest = {
        'schema': 'aetherfield.city-district-source-candidate/1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'SOURCE_CANDIDATE_ONLY_NOT_RUNTIME_ADMITTED', 'source_master': {'path': relative(MASTER), 'sha256': before_hashes[relative(MASTER)]},
        'recipe': relative(Path(__file__).resolve()), 'recipe_sha256': sha256(Path(__file__).resolve()), 'layout_sha256': sha256(HERE / 'layout.json'),
        'blender_version': bpy.app.version_string,
        'coordinates': {'units': 'metres', 'blender_to_shared': ['Blender X', 'Blender Z', '176 + Blender Y'],
                        'glb_to_shared': ['glTF X', 'glTF Y', '176 - glTF Z'], 'scale': 1,
                        'grid_size_m': GRID_METRES, 'grid_origin_shared_xz': [-120, 16]},
        'ownership': {'rule': 'Each of 37 authored roots owns all descendants in one stable district. Other whole meshes use AABB-centre ownership. Unsliced meshes larger than 80 m belong exclusively to city-wide-support.',
                      'mesh_duplicates': len(assigned) - len(set(assigned)), 'unassigned_objects': len(objects) - len(assigned),
                      'source_meshes': sum(obj.type == 'MESH' for obj in objects), 'source_static_meshes': sum(obj.type == 'MESH' and not obj.name.startswith(RUNTIME_PREFIXES) for obj in objects),
                      'source_hooks': sum(obj.name.startswith(RUNTIME_PREFIXES) for obj in objects), 'source_triangles': triangles(objects),
                      'district_count': len(cells), 'authored_root_count': len(root_records)},
        'roots': root_records, 'cells': cells, 'large_parts': large_parts,
        'resources': sorted(resources.values(), key=lambda row: row['path']),
        'resource_policy': 'One shared resource ID per final PNG hash. Candidate GLBs retain texture bindings via relative source URIs and embed zero image payloads. Geometry is unique; shared image references across districts are intentional. Future runtime packaging must deduplicate KTX2 resources and retain material ownership, UV0/COLOR_0 and hashes.',
        'exports': exports,
        'residency_cost_model': 'Candidate residentBytes = 2 x exact uncompressed geometry buffer bytes + unique full RGBA8 mip bytes + source PNG bytes. Conservative planning estimate; engine overhead and transient decode peaks need measured admission. Existing compressed monolithic runtime transfer size is not decoded GPU memory.',
        'large_part_limit': 'city-wide-support contains unsliced terrain/cliff/canal meshes; it has no loadable candidate here. Keep current distant HLOD/ground fallback and collision independent. Before runtime admission, author seam-safe terrain pages or a separately budgeted support LOD. No near district may silently duplicate the global ground.',
        'verification': {'protected_hashes_before': before_hashes, 'protected_hashes_after': after_hashes,
                         'source_master_saved': False, 'source_scale_changed': False, 'max_original_world_matrix_error': max_matrix_error,
                         'source_scene_object_count_preserved': len(bpy.context.scene.objects) == before_counts['objects'],
                         'gpu_review_performed': False, 'runtime_admitted': False, 'mobile_fps_measured': False},
    }
    (DESTINATION / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    evidence = {key: manifest[key] for key in ['schema', 'created_utc', 'status', 'source_master', 'recipe', 'recipe_sha256', 'layout_sha256', 'blender_version', 'coordinates', 'ownership', 'exports', 'verification']}
    evidence['manifest_path'] = relative(DESTINATION / 'manifest.json')
    evidence['manifest_sha256'] = sha256(DESTINATION / 'manifest.json')
    RECEIPT.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print('DISTRICT_CANDIDATE_RESULT', json.dumps({'status': manifest['status'], 'ownership': manifest['ownership'],
                                                'exports': [{key: row[key] for key in ['label', 'bytes', 'triangles', 'materials', 'images', 'conservative_resident_bytes']} for row in exports],
                                                'receipt': relative(RECEIPT)}))


if __name__ == '__main__':
    main()
