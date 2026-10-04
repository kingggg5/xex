"""Repair R5 side-window orientation in an isolated candidate; never rebuild the city.

Run against the canonical master using --inspect first. Candidate saving keeps
the authored //textures paths for later promotion beside the canonical maps.
Only rigid window object transforms change; mesh data, UVs and materials stay.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CITY = ROOT / 'assets/models/reference-city/r5'
MASTER = CITY / 'reference_city.blend'
EXPECTED_MASTER_SHA256 = '386e6babf4c88a29d8380939f7844f1fe32e4437ded73441d6a920f901dcfd99'
CANDIDATE_DIR = CITY / 'window-repair-candidate'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'lib'))
import citykit as ck
import repair_landmark_placements_r5 as geometry_checks
import export_source_r5 as source_exporter
from export_runtime_r5 import refresh_texture_images

WINDOW_NAME = re.compile(r'^(.* side window \d+-\d+) (.+)$')
PARTS = {'stone reveal', 'dark inset', 'glass', 'vertical mullion', 'horizontal mullion', 'sill', 'shutter', 'shutter strap'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix_error(left, right):
    return max(abs(left[row][column] - right[row][column]) for row in range(4) for column in range(4))


def local_matrix(obj):
    if not obj.parent:
        raise RuntimeError(f'Window part lost its authored parent: {obj.name}')
    return obj.parent.matrix_world.inverted() @ obj.matrix_world


def root_snapshot():
    return {obj.name: [[float(value) for value in row] for row in obj.matrix_world]
            for obj in bpy.context.scene.objects if obj.name.startswith('kit_') and obj.type == 'EMPTY'}


def glass_normal(obj):
    faces = [face for face in obj.data.polygons if face.normal.dot(Vector((0, -1, 0))) > 0.99]
    if not faces:
        raise RuntimeError(f'No authored front face found on glass: {obj.name}')
    face = max(faces, key=lambda value: value.area)
    return (local_matrix(obj).to_3x3().inverted().transposed() @ face.normal).normalized()


def find_groups():
    groups = defaultdict(list)
    for obj in bpy.context.scene.objects:
        match = WINDOW_NAME.match(obj.name)
        if obj.type != 'MESH' or not match:
            continue
        part = re.sub(r'\.\d+$', '', match.group(2))
        if part not in PARTS:
            raise RuntimeError(f'Unexpected side-window component: {obj.name}')
        center = local_matrix(obj).translation
        side = 1 if center.x > 0 else -1
        groups[(obj.parent.name, match.group(1), side)].append((obj, part))
    if not groups:
        raise RuntimeError('No named side-window assemblies found in the saved master.')
    records = []
    for (root_name, window, side), members in sorted(groups.items()):
        counts = Counter(part for _, part in members)
        expected = Counter({name: 1 for name in PARTS - {'shutter', 'shutter strap'}})
        if counts['shutter']:
            expected.update({'shutter': 2, 'shutter strap': 6})
        if counts != expected:
            raise RuntimeError(f'Incomplete assembly {root_name}/{window}/{side}: {dict(counts)}')
        reveal = next(obj for obj, part in members if part == 'stone reveal')
        glass = next(obj for obj, part in members if part == 'glass')
        # _window() places the reveal at (x, y - 0.04, z).
        anchor = local_matrix(reveal).translation + Vector((0, 0.04, 0))
        normal = glass_normal(glass)
        records.append({'root_name': root_name, 'window': window, 'side': side,
                        'members': members, 'anchor': anchor, 'glass': glass,
                        'before_normal': list(normal), 'before_outward_dot': normal.dot(Vector((side, 0, 0)))})
    return records


def material_inspection():
    result = []
    for name in ['glass_window_warm', 'glass_window_blue']:
        material = bpy.data.materials.get(name)
        if material is None or not material.node_tree:
            raise RuntimeError(f'Expected saved window material {name}')
        shader = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
        result.append({'name': name, 'base_color': list(shader.inputs['Base Color'].default_value),
                       'emission_color': list(shader.inputs['Emission Color'].default_value),
                       'emission_strength': shader.inputs['Emission Strength'].default_value,
                       'roughness': shader.inputs['Roughness'].default_value,
                       'emission_linked': shader.inputs['Emission Color'].is_linked,
                       'material_changed': False})
    return result


def serial_record(record):
    return {key: value for key, value in record.items() if key not in {'members', 'glass', 'anchor'}} | {
        'anchor': list(record['anchor']), 'components': [obj.name for obj, _ in record['members']]}


def render_review(root, variant, output_dir):
    objects = [obj for obj in root.children_recursive if obj.type == 'MESH']
    keep = set(objects)
    old_visibility = {obj.name: obj.hide_render for obj in bpy.context.scene.objects}
    old_scene = bpy.context.scene
    for obj in old_scene.objects:
        if obj.type == 'MESH' and obj not in keep:
            obj.hide_render = True
    ck.render_settings(res=(1024, 768), samples=16, threads=4)
    old_scene.cycles.use_denoising = True
    paths = []
    for label, local_direction in [('front', Vector((0, -1, 0))), ('side', Vector((1, 0, 0)))]:
        world_direction = (root.matrix_world.to_3x3() @ local_direction).normalized()
        azimuth = math.degrees(math.atan2(world_direction.x, -world_direction.y))
        ck.frame_camera(objects, azimuth_deg=azimuth, elevation_deg=14, lens=55,
                        margin=1.05, name='Window candidate matched review')
        destination = output_dir / f'city-windows-{root.name}-{label}-{variant}-20261001.png'
        ck.render(destination)
        paths.append(str(destination))
    for name, hidden in old_visibility.items():
        if bpy.data.objects.get(name):
            bpy.data.objects[name].hide_render = hidden
    return paths


def verify_saved_candidate():
    receipt = json.loads((ROOT / 'planning/evidence/city-windows-20261001-candidate.json').read_text(encoding='utf-8'))
    candidate = Path(bpy.data.filepath).resolve()
    if candidate != Path(receipt['candidate']).resolve() or sha256(candidate) != receipt['candidate_sha256']:
        raise RuntimeError('Load the exact saved candidate whose hash is recorded in the receipt.')
    if sha256(MASTER) != receipt['source_sha256']:
        raise RuntimeError('Canonical master changed before candidate readback verification.')
    bpy.context.view_layer.update()
    if geometry_checks.geometry_digest() != receipt['geometry_sha256_after']:
        raise RuntimeError('Saved candidate geometry, UVs, colors or material ownership changed.')
    if root_snapshot() != receipt['root_transforms_preserved']:
        raise RuntimeError('Saved candidate root transforms differ from the source.')
    if {image.name: image.filepath for image in bpy.data.images} != receipt['image_filepaths_preserved']:
        raise RuntimeError('Saved candidate texture references changed.')
    groups = find_groups()
    if len(groups) != receipt['window_assemblies']:
        raise RuntimeError('Saved candidate side-window assembly count changed.')
    for record in groups:
        if glass_normal(record['glass']).dot(Vector((record['side'], 0, 0))) < 0.9999:
            raise RuntimeError('Saved candidate glass orientation is not outward.')
    candidate_matrices = {obj.name: obj.matrix_world.copy() for obj in bpy.context.scene.objects}
    transformed = {name for window in receipt['windows'] for name in window['components']}
    bpy.ops.wm.open_mainfile(filepath=str(MASTER), load_ui=False, use_scripts=False)
    bpy.context.view_layer.update()
    max_window_error = 0.0
    for window in receipt['windows']:
        root = bpy.data.objects[window['root_name']]
        anchor = Vector(window['anchor'])
        pivot = Matrix.Translation(anchor) @ Matrix.Rotation(window['side'] * math.pi / 2, 4, 'Z') @ Matrix.Translation(-anchor)
        for name in window['components']:
            expected = root.matrix_world @ pivot @ root.matrix_world.inverted() @ bpy.data.objects[name].matrix_world
            max_window_error = max(max_window_error, matrix_error(expected, candidate_matrices[name]))
    max_unselected_error = max(matrix_error(obj.matrix_world, candidate_matrices[obj.name])
                               for obj in bpy.context.scene.objects if obj.name not in transformed)
    if max_window_error > 5e-5 or max_unselected_error > 1e-5:
        raise RuntimeError(f'Saved transform readback failed: windows={max_window_error}, others={max_unselected_error}')
    if geometry_checks.geometry_digest() != receipt['geometry_sha256_before'] or sha256(MASTER) != receipt['source_sha256']:
        raise RuntimeError('Original source verification failed after readonly comparison.')
    result = {'schema': 'aetherfield.city-side-window-readback/1', 'result': 'PASS',
              'source_sha256': receipt['source_sha256'], 'candidate_sha256': receipt['candidate_sha256'],
              'window_assemblies_verified': len(groups), 'window_parts_verified': len(transformed),
              'root_matrices_verified': len(receipt['root_transforms_preserved']),
              'unselected_objects_verified': len(candidate_matrices) - len(transformed),
              'max_saved_window_world_matrix_error': max_window_error,
              'max_unselected_world_matrix_error': max_unselected_error,
              'geometry_uv_colors_materials_unchanged': True, 'texture_filepaths_unchanged': True,
              'canonical_source_saved': False}
    (ROOT / 'planning/evidence/city-windows-20261001-readback.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


def export_runtime_candidate():
    import export_runtime_r5 as runtime_exporter
    receipt = json.loads((ROOT / 'planning/evidence/city-windows-20261001-candidate.json').read_text(encoding='utf-8'))
    candidate = Path(bpy.data.filepath).resolve()
    if candidate != Path(receipt['candidate']).resolve() or sha256(candidate) != receipt['candidate_sha256']:
        raise RuntimeError('Runtime export requires the exact separately verified window candidate.')
    if sha256(MASTER) != receipt['source_sha256']:
        raise RuntimeError('Canonical master changed before candidate runtime export.')
    bpy.context.view_layer.update()
    if geometry_checks.geometry_digest() != receipt['geometry_sha256_after']:
        raise RuntimeError('Candidate data no longer matches its verified mesh/UV/material digest.')
    original_input = runtime_exporter.MASTER
    original_texture_reload = runtime_exporter.refresh_texture_images
    original_argv = sys.argv[:]
    output = CANDIDATE_DIR / 'city-runtime.glb'
    stats = CANDIDATE_DIR / 'city-runtime.stats.json'
    try:
        # Bind the existing strict input guard to this explicitly verified input.
        # All ratios, canonical source guards, material counts and budget remain.
        runtime_exporter.MASTER = candidate
        def reload_candidate_textures():
            # Same strict source maps and dimension checks as the existing
            # exporter; absolute in-memory paths resolve nested candidates.
            used = {node.image.name: node.image for material in bpy.data.materials
                    if material.use_nodes and material.node_tree
                    for node in material.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image}
            records = []
            for image in used.values():
                name = image.name
                if not name.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.exr')):
                    name = image.filepath.replace('\\', '/').rsplit('/', 1)[-1]
                base = runtime_exporter.QUATERNIUS_TEXTURES if name in runtime_exporter.QUATERNIUS_TEXTURE_NAMES else runtime_exporter.TEXTURES
                source = base / name
                if not source.is_file():
                    raise RuntimeError(f'Candidate texture source missing: {source}')
                image.filepath = str(source.resolve())
                image.reload()
                if image.size[0] <= 0 or image.size[1] <= 0:
                    raise RuntimeError(f'Candidate texture failed to load: {source}')
                records.append({'name': image.name, 'path': source.relative_to(ROOT).as_posix(),
                                'width': int(image.size[0]), 'height': int(image.size[1])})
            return records
        runtime_exporter.refresh_texture_images = reload_candidate_textures
        sys.argv = [sys.argv[0], '--', '--candidate', str(output), '--stats', str(stats), '--limit', '900000']
        runtime_exporter.main()
    finally:
        runtime_exporter.MASTER = original_input
        runtime_exporter.refresh_texture_images = original_texture_reload
        sys.argv = original_argv
    result = json.loads(stats.read_text(encoding='utf-8'))
    if result['candidate']['glb_accessor_triangles'] != 892348:
        raise RuntimeError(f'Runtime triangle count differs from preserved profile: {result["candidate"]["glb_accessor_triangles"]}')
    if sha256(MASTER) != receipt['source_sha256'] or sha256(candidate) != receipt['candidate_sha256']:
        raise RuntimeError('A protected master changed during runtime export.')
    result['canonical_master_sha256_preserved'] = receipt['source_sha256']
    result['window_repair_candidate_sha256_verified'] = receipt['candidate_sha256']
    (ROOT / 'planning/evidence/city-windows-20261001-runtime.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': 'PASS', 'candidate': result['candidate'], 'ratios': result['decimation_profile']['ratios']}), flush=True)


def generator_check():
    source = HERE / 'kits/buildings.py'
    baseline = CANDIDATE_DIR / 'buildings.before-window-yaw.py'
    before_text, after_text = baseline.read_text(encoding='utf-8'), source.read_text(encoding='utf-8')
    old_ast, new_ast = ast.parse(before_text), ast.parse(after_text)
    old_functions = {node.name: node for node in old_ast.body if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: node for node in new_ast.body if isinstance(node, ast.FunctionDef)}
    untouched = set(old_functions) - {'_window', '_building_shell'}
    if set(old_functions) != set(new_functions) or any(ast.dump(old_functions[name]) != ast.dump(new_functions[name]) for name in untouched):
        raise RuntimeError('Generator repair changed unrelated function definitions.')
    old_shell, new_shell = old_functions['_building_shell'], new_functions['_building_shell']
    old_side_calls = [node for node in ast.walk(old_shell) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_window' and any(isinstance(piece, ast.Constant) and ' side window ' in str(piece.value) for argument in node.args for piece in ast.walk(argument))]
    new_side_calls = [node for node in ast.walk(new_shell) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_window' and any(isinstance(piece, ast.Constant) and ' side window ' in str(piece.value) for argument in node.args for piece in ast.walk(argument))]
    if len(old_side_calls) != 1 or len(new_side_calls) != 1:
        raise RuntimeError('Expected one shared side-window generator call site.')
    old_side_calls[0].keywords.append(next(keyword for keyword in new_side_calls[0].keywords if keyword.arg == 'yaw'))
    if ast.dump(old_shell) != ast.dump(new_shell):
        raise RuntimeError('Building shell changed beyond its single side-window yaw argument.')
    rows = []

    def run_fixture(function_node, yaw=None, shutter=True, seed=0):
        created = []
        def box_stub(root, name, center, size, material, bevel=0.035, **kwargs):
            obj = SimpleNamespace(name=name, matrix_basis=Matrix.Translation(Vector(center)),
                                  construction={'center': list(center), 'size': list(size), 'material': material, 'bevel': bevel, 'kwargs': kwargs})
            created.append(obj)
            return obj
        scope = {'_box': box_stub, 'TRIM': 'stone_trim_carved', 'WOOD': 'timber_dark', 'GLASS': 'glass_window_warm', 'BLUE_GLASS': 'glass_window_blue', 'GOLD': 'metal_gold', 'IRON': 'metal_iron', 'Matrix': Matrix, 'Vector': Vector}
        exec(compile(ast.Module(body=[function_node], type_ignores=[]), str(source), 'exec'), scope)
        kwargs = {'w': 1.1, 'h': 1.55, 'shutter': shutter, 'seed': seed}
        if yaw is not None:
            kwargs['yaw'] = yaw
        returned = scope['_window'](None, 'fixture window', 8.12, -2.2, 3.3, **kwargs)
        if returned is not None:
            raise RuntimeError('Window helper changed its existing return behavior.')
        return created

    for shutter in [False, True]:
        for seed in [0, 1]:
            original = run_fixture(old_functions['_window'], shutter=shutter, seed=seed)
            default = run_fixture(new_functions['_window'], shutter=shutter, seed=seed)
            if len(original) != len(default) or any(left.construction != right.construction or matrix_error(left.matrix_basis, right.matrix_basis) > 1e-6 for left, right in zip(original, default)):
                raise RuntimeError('Default front-window construction or pose changed.')
            for side in [-1, 1]:
                turned = run_fixture(new_functions['_window'], side * math.pi / 2, shutter=shutter, seed=seed)
                anchor = Vector((8.12, -2.2, 3.3))
                pivot = Matrix.Translation(anchor) @ Matrix.Rotation(side * math.pi / 2, 4, 'Z') @ Matrix.Translation(-anchor)
                if any(left.construction != right.construction or matrix_error(pivot @ left.matrix_basis, right.matrix_basis) > 1e-6 for left, right in zip(original, turned)):
                    raise RuntimeError('A shutter/frame/glass part did not turn with its full assembly.')
                rows.append({'shutters': shutter, 'seed': seed, 'side': side, 'parts_verified': len(turned), 'front_default_preserved': True})
    result = {'result': 'PASS', 'before_sha256': sha256(baseline), 'after_sha256': sha256(source),
              'before_hash_method': 'Exact previous owned sections reconstructed from the source read; no pre-mutation filesystem digest was captured.',
              'before_snapshot': str(baseline), 'unrelated_function_definitions_unchanged': len(untouched),
              'building_shell_only_side_yaw_added': True, 'fixture_cases': rows}
    (ROOT / 'planning/evidence/city-windows-20261001-generator.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--export-runtime', action='store_true')
    parser.add_argument('--generator-check', action='store_true')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--house', default='kit_armory_house')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if args.generator_check:
        generator_check()
        return
    if args.export_runtime:
        export_runtime_candidate()
        return
    if args.verify:
        verify_saved_candidate()
        return
    if Path(bpy.data.filepath).resolve() != MASTER.resolve():
        raise RuntimeError('Load the exact canonical authored city master; rebuilding is forbidden.')
    before_hash = sha256(MASTER)
    if before_hash != EXPECTED_MASTER_SHA256:
        raise RuntimeError(f'Canonical master changed; investigate before repairing: {before_hash}')
    bpy.context.view_layer.update()
    groups = find_groups()
    material_records = material_inspection()
    report = {'schema': 'aetherfield.city-side-window-repair/1', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'source': str(MASTER), 'source_sha256': before_hash, 'source_saved': False,
              'window_assemblies': len(groups), 'window_parts': sum(len(record['members']) for record in groups),
              'building_roots': sorted({record['root_name'] for record in groups}),
              'materials_inspected_unchanged': material_records,
              'windows': [serial_record(record) for record in groups]}
    evidence = ROOT / 'planning/evidence/city-windows-20261001-inspection.json'
    if args.inspect:
        report['status'] = 'INSPECTED_CANONICAL_READONLY'
        evidence.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: value for key, value in report.items() if key != 'windows'}), flush=True)
        return
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    candidate = CANDIDATE_DIR / 'reference_city_side_windows.blend'
    if candidate.exists():
        raise RuntimeError('Candidate already exists; use inspection or preserve it before another repair.')
    roots_before = root_snapshot()
    object_matrices_before = {obj.name: obj.matrix_world.copy() for obj in bpy.context.scene.objects}
    image_paths_before = {image.name: image.filepath for image in bpy.data.images}
    geometry_before = geometry_checks.geometry_digest()
    counts_before = {'objects': len(bpy.context.scene.objects), 'meshes': sum(obj.type == 'MESH' for obj in bpy.context.scene.objects),
                     'materials': len(bpy.data.materials), 'triangles': ck.triangle_count([obj for obj in bpy.context.scene.objects if obj.type == 'MESH'])}
    transformed = set()
    for record in groups:
        if abs(record['before_outward_dot']) > 1e-4:
            raise RuntimeError(f'Window orientation is not the uncorrected source case: {record["window"]}')
        root = bpy.data.objects[record['root_name']]
        pivot = Matrix.Translation(record['anchor']) @ Matrix.Rotation(record['side'] * math.pi / 2, 4, 'Z') @ Matrix.Translation(-record['anchor'])
        for obj, part in record['members']:
            before_local = local_matrix(obj)
            obj.matrix_world = root.matrix_world @ pivot @ before_local
            transformed.add(obj.name)
        bpy.context.view_layer.update()
        normal = glass_normal(record['glass'])
        outward = normal.dot(Vector((record['side'], 0, 0)))
        if outward < 0.9999:
            raise RuntimeError(f'Glass fails outward orientation: {record["window"]}/{record["side"]}/{outward}')
        glass_position = local_matrix(record['glass']).translation
        gap = record['side'] * (glass_position.x - record['anchor'].x)
        if abs(gap - 0.25) > 1e-4 or abs(glass_position.z - record['anchor'].z) > 1e-4:
            raise RuntimeError(f'Glass depth or height changed incorrectly: {record["window"]}')
        record.update({'after_normal': list(normal), 'after_outward_dot': outward,
                       'outward_glass_offset_m': gap, 'rotation_z_degrees': record['side'] * 90})
    geometry_after = geometry_checks.geometry_digest()
    if geometry_before != geometry_after:
        raise RuntimeError('Repair changed mesh positions, UVs, colors, material ownership or topology.')
    if root_snapshot() != roots_before:
        raise RuntimeError('An authored building/landmark root moved.')
    max_unselected_error = max(matrix_error(object_matrices_before[obj.name], obj.matrix_world)
                               for obj in bpy.context.scene.objects if obj.name not in transformed)
    if max_unselected_error > 1e-5:
        raise RuntimeError(f'Unselected object placement changed: {max_unselected_error}')
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False, relative_remap=False, copy=True)
    if image_paths_before != {image.name: image.filepath for image in bpy.data.images}:
        raise RuntimeError('Candidate save changed authored texture references.')
    report.update({'status': 'CANDIDATE_STRUCTURAL_PASS_PENDING_PARENT_REVIEW', 'candidate': str(candidate),
                   'candidate_sha256': sha256(candidate), 'geometry_sha256_before': geometry_before,
                   'geometry_sha256_after': geometry_after, 'geometry_uv_colors_materials_unchanged': True,
                   'counts_preserved': counts_before, 'root_transforms_preserved': roots_before,
                   'unselected_object_max_world_matrix_error': max_unselected_error,
                   'image_filepaths_preserved': image_paths_before, 'modified_object_count': len(transformed),
                   'windows': [serial_record(record) for record in groups],
                   'limitations': ['Orientation repair only; emission is inspected and preserved.',
                                   'Candidate keeps canonical //textures paths for promotion beside the source maps.',
                                   'Blender review does not establish Babylon.js GPU quality.']})
    if args.render:
        review_house = bpy.data.objects.get(args.house)
        if not review_house:
            raise RuntimeError(f'Review house missing: {args.house}')
        refresh_texture_images()
        # Restore original transforms for the matched baseline in memory only.
        fixed_matrices = {name: bpy.data.objects[name].matrix_world.copy() for name in transformed}
        for name in transformed:
            bpy.data.objects[name].matrix_world = object_matrices_before[name]
        bpy.context.view_layer.update()
        before_renders = render_review(review_house, 'before', CANDIDATE_DIR)
        for name, matrix in fixed_matrices.items():
            bpy.data.objects[name].matrix_world = matrix
        bpy.context.view_layer.update()
        after_renders = render_review(review_house, 'after', CANDIDATE_DIR)
        report['matched_renders'] = {'before': before_renders, 'after': after_renders}
    if args.export:
        if Path(bpy.data.filepath).resolve() != MASTER.resolve():
            raise RuntimeError('Source export guard requires original in-memory filepath.')
        original_argv = sys.argv[:]
        export_stats = CANDIDATE_DIR / 'city-source-window-candidate.stats.json'
        export_path = CANDIDATE_DIR / 'city-source-window-candidate.glb'
        try:
            sys.argv = [sys.argv[0], '--', '--candidate', str(export_path), '--stats', str(export_stats)]
            source_exporter.main()
        finally:
            sys.argv = original_argv
        report['glb_export'] = json.loads(export_stats.read_text(encoding='utf-8'))
    if sha256(MASTER) != before_hash:
        raise RuntimeError('Protected canonical master changed during candidate repair.')
    evidence = ROOT / 'planning/evidence/city-windows-20261001-candidate.json'
    evidence.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in {'windows', 'root_transforms_preserved', 'image_filepaths_preserved', 'glb_export'}}), flush=True)


if __name__ == '__main__':
    main()
