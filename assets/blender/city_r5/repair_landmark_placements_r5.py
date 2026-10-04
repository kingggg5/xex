"""Move only nine confirmed local landmark roots to their existing R5 layout.

Creates a separate candidate master and receipt. It never publishes the
candidate over the protected master, regenerates a kit, or modifies mesh data.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import shutil
import sys
from array import array
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MASTER = ROOT / 'assets/models/reference-city/r5/reference_city.blend'
LAYOUT = HERE / 'layout.json'
MOVED_ROOTS = ('magic_castle', 'grand_stairs', 'north_arcades', 'wizard_tower',
               'windmill', 'arcane_portal', 'town_gate', 'canal_bridge', 'ring_bridge')
UNCHANGED_MATERIALS = {'stone_wall_warm', 'stone_foundation', 'plaster_cream',
                       'plaza_flagstone', 'roof_slate_blue', 'roof_slate_navy',
                       'roof_tile_red', 'roof_shingle_green', 'cloth_red',
                       'cloth_blue', 'cloth_green', 'cloth_cream', 'marble_statue', 'MI_Trim_Metal'}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_digest():
    digest = hashlib.sha256()
    for obj in sorted((obj for obj in bpy.context.scene.objects if obj.type == 'MESH'), key=lambda obj: obj.name):
        mesh = obj.data
        digest.update(obj.name.encode('utf-8'))
        digest.update(json.dumps([mat.name if mat else None for mat in mesh.materials]).encode('utf-8'))
        for values, attribute, width, code in [(mesh.vertices, 'co', 3, 'f'),
                                                (mesh.loops, 'vertex_index', 1, 'i'),
                                                (mesh.polygons, 'material_index', 1, 'i')]:
            data = array(code, [0]) * (len(values) * width)
            values.foreach_get(attribute, data)
            digest.update(data.tobytes())
        for uv in mesh.uv_layers:
            digest.update(uv.name.encode('utf-8'))
            data = array('f', [0]) * (len(uv.data) * 2)
            uv.data.foreach_get('uv', data)
            digest.update(data.tobytes())
        for color in mesh.color_attributes:
            digest.update(f'{color.name}/{color.domain}/{color.data_type}'.encode('utf-8'))
            data = array('f', [0]) * (len(color.data) * 4)
            color.data.foreach_get('color', data)
            digest.update(data.tobytes())
    return digest.hexdigest()


def specs(layout):
    aliases = {'market': 'market_square', 'sw_well_gazebo': 'well_gazebo'}
    rows = []
    for landmark in layout['landmarks']:
        if landmark['kind'] == 'house_small_group':
            for index, center in enumerate(landmark['centers'], 1):
                spec = dict(landmark, center=center)
                rows.append((f"{landmark['id']}_{index}", landmark['id'], spec))
        else:
            rows.append((aliases.get(landmark['id'], landmark['id']), landmark['id'], landmark))
    rows.extend([('plaza_fountain', 'fountain', layout['fountain']),
                 ('arcane_portal', 'portal', layout['portal'])])
    return rows


def load_place_root():
    module = ast.parse((HERE / 'build_city_r5.py').read_text(encoding='utf-8'))
    fn = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'place_root')
    scope = {'math': math}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'build_city_r5.py', 'exec'), scope)
    return scope['place_root']


def root_record(root, identifier):
    meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    candidates = [obj for obj in meshes if obj.data.materials
                  and obj.data.materials[0].name in UNCHANGED_MATERIALS
                  and not obj.name.startswith(('anim_', 'fx_', 'emit_', 'light_'))]
    if not candidates:
        raise RuntimeError(f'No unchanged-material vertex witness for {root.name}')
    body = next((obj for obj in candidates if 'masonry body' in obj.name or 'nave stone body' in obj.name), candidates[0])
    face = next(poly for poly in body.data.polygons if poly.material_index == 0)
    witness = body.matrix_world @ body.data.vertices[face.vertices[0]].co
    return {'id': identifier, 'root': root.name, 'root_location': list(root.location),
            'world_location': list(root.matrix_world.translation),
            'rotation_z_radians': root.rotation_euler.z, 'meshes': len(meshes),
            'blender_bounds': {'min': [min(point[axis] for point in points) for axis in range(3)],
                               'max': [max(point[axis] for point in points) for axis in range(3)]},
            'vertex_witness_object': body.name, 'vertex_witness_material': body.data.materials[0].name,
            'gltf_vertex_witness': [witness.x, witness.z, -witness.y]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--stats', required=True)
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(raw)
    candidate = Path(args.candidate).resolve()
    output = Path(args.stats).resolve()
    cache = (ROOT / '.harness/.cache').resolve()
    if candidate.parent != cache or output.parent != cache or candidate.suffix != '.blend' or output.suffix != '.json':
        parser.error('Candidate .blend and stats .json must be separate files inside the workspace cache.')
    if Path(bpy.data.filepath).resolve() != MASTER.resolve():
        raise RuntimeError('Load the protected authored master before producing the candidate.')
    layout = json.loads(LAYOUT.read_text(encoding='utf-8'))
    original_hash = sha256(MASTER)
    backup = cache / f'reference-city-before-landmarks-{original_hash[:12]}.blend'
    if backup.exists():
        if sha256(backup) != original_hash:
            raise RuntimeError('Existing recovery copy does not match the protected master.')
    else:
        shutil.copy2(MASTER, backup)
    bpy.context.view_layer.update()
    before_geometry = geometry_digest()
    image_filepaths = {image.name: image.filepath for image in bpy.data.images if image.filepath}
    before_matrices = {obj.name: obj.matrix_world.copy() for obj in bpy.context.scene.objects}
    before_counts = {'objects': len(bpy.context.scene.objects), 'materials': len(bpy.data.materials),
                     'meshes': sum(obj.type == 'MESH' for obj in bpy.context.scene.objects),
                     'triangles': sum(len(poly.vertices) - 2 for obj in bpy.context.scene.objects
                                      if obj.type == 'MESH' for poly in obj.data.polygons)}
    before = [root_record(bpy.data.objects[f'kit_{name}'], identifier) for name, identifier, _ in specs(layout)]
    moved_objects = set()
    place_root = load_place_root()
    for name, _, spec in specs(layout):
        if name not in MOVED_ROOTS:
            continue
        root = bpy.data.objects[f'kit_{name}']
        moved_objects.add(root.name)
        moved_objects.update(obj.name for obj in root.children_recursive)
        place_root(root, spec, layout['levels'].get(spec.get('level', 'plaza'), 0.0))
    bpy.context.view_layer.update()
    unchanged_errors = [max(abs(before_matrices[obj.name][row][column] - obj.matrix_world[row][column])
                            for row in range(4) for column in range(4))
                        for obj in bpy.context.scene.objects if obj.name not in moved_objects]
    if max(unchanged_errors, default=0) > 1e-4 or geometry_digest() != before_geometry:
        raise RuntimeError('Geometry/art or an object outside the approved root scope changed.')
    after = [root_record(bpy.data.objects[f'kit_{name}'], identifier) for name, identifier, _ in specs(layout)]
    for name, _, spec in specs(layout):
        expected = SimpleNamespace()
        place_root(expected, spec, layout['levels'].get(spec.get('level', 'plaza'), 0.0))
        actual = bpy.data.objects[f'kit_{name}']
        if max(abs(a - b) for a, b in zip(actual.location, expected.location)) > 1e-4:
            raise RuntimeError(f'Root position does not match the authoritative layout: {actual.name}')
        if max(abs(math.atan2(math.sin(a - b), math.cos(a - b)))
               for a, b in zip(actual.rotation_euler, expected.rotation_euler)) > 1e-4:
            raise RuntimeError(f'Root rotation does not match the authoritative layout: {actual.name}')
    candidate.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    # This candidate will be moved back beside the canonical texture folder.
    # Keep the canonical master's relative image paths instead of remapping
    # them to the temporary cache directory during the candidate save.
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), relative_remap=False)
    if {image.name: image.filepath for image in bpy.data.images if image.filepath} != image_filepaths:
        raise RuntimeError('Candidate saving changed authored texture references.')
    if sha256(MASTER) != original_hash:
        raise RuntimeError('Protected master changed while saving the separate candidate.')
    report = {'schema': 'aetherfield.city-landmark-placement-repair/1',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'result': 'CANDIDATE_PASS',
              'original_master_sha256': original_hash, 'candidate_master_sha256': sha256(candidate),
              'master_recovery_copy': backup.relative_to(ROOT).as_posix(),
              'layout_sha256': sha256(LAYOUT), 'geometry_sha256': before_geometry,
              'image_filepaths': image_filepaths,
              'preserved_counts': before_counts, 'moved_roots': list(MOVED_ROOTS),
              'unchanged_object_max_matrix_error': max(unchanged_errors, default=0),
              'landmark_definition_count': len(layout['landmarks']) + 2,
              'all_layout_poses_match': True,
              'individual_root_count': len(after), 'before': before, 'after': after,
              'limitations': ['Raised castle, wizard and windmill art uses existing authored levels; gameplay ground and height collision are unchanged.']}
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in {'before', 'after', 'limitations', 'image_filepaths'}}))


if __name__ == '__main__':
    main()
