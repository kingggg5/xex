"""Repair known R5 roof UVs into a separate Blender candidate.

Run after opening the intended source blend. This script changes UVMap only,
never saves the source, never exports GLBs and never regenerates textures.

Gable slope faces use metric U along the eave and V from eave to ridge.
Lathed roof sides use seam-consistent angular U and metric meridian V. A cone
cannot retain both constant horizontal texel density and continuous circular
courses: U converges toward its tip. The measured eave repeat is recorded.

Example (Blender arguments after --):
  --candidate assets/models/reference-city/r5/roof-uv-candidate.blend
  --stats planning/evidence/city-roof-uv-candidate.json

--self-test uses an in-memory fixture and writes no files. --dry-run inspects
the open scene without editing or saving it. Production mode requires both
separate candidate and stats paths; canonical generated files are refused.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[3]
CITY = ROOT / 'assets' / 'models' / 'reference-city' / 'r5'
ROOF_MATERIALS = {'roof_slate_blue', 'roof_slate_navy',
                  'roof_shingle_green', 'roof_tile_red'}
LATHE_NAMES = {'guild turret cap', 'windmill cap', 'gate blue tower cap',
               'gazebo blue pavilion roof', 'observatory entry lantern'}
GABLE_FACES = ((0, 2, 5, 3), (2, 1, 4, 5), (0, 1, 2),
               (3, 5, 4), (0, 3, 4, 1))
EPS = 1e-5


def plain_name(name):
    return re.sub(r'\.\d{3}$', '', name)


def material_tile(obj):
    if len(obj.data.materials) != 1:
        raise ValueError(f'{obj.name}: expected one roof material')
    mat = obj.data.materials[0]
    if mat is None or mat.name not in ROOF_MATERIALS:
        raise ValueError(f'{obj.name}: unexpected roof material')
    tile = float(mat.get('city_tile_m', 0.0))
    if not math.isfinite(tile) or tile <= 0:
        raise ValueError(f'{obj.name}: missing metric city_tile_m')
    return tile


def classify(obj):
    if obj.type != 'MESH' or not obj.data.materials:
        return None
    if obj.data.materials[0] is None or obj.data.materials[0].name not in ROOF_MATERIALS:
        return None
    name = plain_name(obj.name)
    if name.endswith(' roof skin'):
        return 'gable'
    if name.endswith((' spire roof', ' slate spire')) or name in LATHE_NAMES:
        return 'lathe'
    return None


def geometry_digest(objects):
    """All object transforms, topology, material ownership and vertex colors.

    UVs are deliberately excluded. No geometry, color, transform, hierarchy,
    modifier or material operation occurs anywhere in the repair functions.
    """
    h = hashlib.sha256()
    for obj in sorted(objects, key=lambda o: o.name):
        h.update(obj.name.encode('utf-8'))
        h.update((obj.parent.name if obj.parent else '').encode('utf-8'))
        h.update(struct.pack('<16d', *(x for row in obj.matrix_world for x in row)))
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        h.update(mesh.name.encode('utf-8'))
        h.update(struct.pack('<II', len(mesh.vertices), len(mesh.polygons)))
        coords = array('f', [0.0]) * (len(mesh.vertices) * 3)
        mesh.vertices.foreach_get('co', coords)
        h.update(coords.tobytes())
        for poly in mesh.polygons:
            h.update(struct.pack('<II', poly.material_index, len(poly.vertices)))
            h.update(array('I', poly.vertices).tobytes())
        for mat in mesh.materials:
            h.update((mat.name if mat else '').encode('utf-8'))
        for attr in mesh.color_attributes:
            h.update(f'{attr.name}:{attr.domain}:{attr.data_type}'.encode('utf-8'))
            colors = array('f', [0.0]) * (len(attr.data) * 4)
            attr.data.foreach_get('color', colors)
            h.update(colors.tobytes())
        h.update(repr([(m.name, m.type) for m in obj.modifiers]).encode('utf-8'))
    return h.hexdigest()


def uv_values(mesh):
    layer = mesh.uv_layers.get('UVMap')
    if layer is None:
        raise ValueError(f'{mesh.name}: existing UVMap required')
    return layer, [tuple(d.uv) for d in layer.data]


def uv_digest(mesh):
    layer = mesh.uv_layers.get('UVMap')
    if layer is None:
        raise ValueError(f'{mesh.name}: existing UVMap required')
    coords = array('f', [0.0]) * (len(layer.data) * 2)
    layer.data.foreach_get('uv', coords)
    return hashlib.sha256(coords.tobytes()).hexdigest()


def gable_plan(obj):
    mesh = obj.data
    if len(mesh.vertices) != 6 or tuple(tuple(p.vertices) for p in mesh.polygons) != GABLE_FACES:
        raise ValueError(f'{obj.name}: not the known six-vertex R5 gable')
    tile = material_tile(obj)
    pts = [obj.matrix_world @ v.co for v in mesh.vertices]
    out = []
    for face, eave, far_eave in ((0, 0, 3), (1, 1, 4)):
        origin = pts[eave]
        u = pts[far_eave] - origin
        v = pts[2] - origin
        if u.length < EPS or v.length < EPS or abs(u.normalized().dot(v.normalized())) > EPS:
            raise ValueError(f'{obj.name}: degenerate or sheared roof slope')
        ua, va = u.normalized(), v.normalized()
        assignments = []
        for li in mesh.polygons[face].loop_indices:
            vi = mesh.loops[li].vertex_index
            d = pts[vi] - origin
            assignments.append((li, (d.dot(ua) / tile, d.dot(va) / tile)))
        out.append({'polygon': face, 'assignments': assignments,
                    'eave_m': u.length, 'slope_m': v.length})
    return {'kind': 'gable', 'tile_m': tile, 'faces': out}


def lathe_plan(obj):
    mesh = obj.data
    tile = material_tile(obj)
    verts = [v.co.copy() for v in mesh.vertices]
    # citykit.lathe stores all profile vertices for segment 0, then segment 1.
    profile_count = next((i for i in range(1, len(verts))
                          if abs(verts[i].z - verts[0].z) < EPS), None)
    if profile_count is None or profile_count < 3 or len(verts) % profile_count:
        raise ValueError(f'{obj.name}: cannot identify citykit lathe profile')
    segments = len(verts) // profile_count
    if segments < 8:
        raise ValueError(f'{obj.name}: insufficient lathe segments')
    side_count = segments * (profile_count - 1)
    if len(mesh.polygons) < side_count:
        raise ValueError(f'{obj.name}: missing lathe side faces')
    expected = []
    for s in range(segments):
        s2 = (s + 1) % segments
        for i in range(profile_count - 1):
            expected.append((s * profile_count + i, s2 * profile_count + i,
                             s2 * profile_count + i + 1, s * profile_count + i + 1))
    if [tuple(p.vertices) for p in mesh.polygons[:side_count]] != expected:
        raise ValueError(f'{obj.name}: not known citykit lathe side topology')
    # Equal radial scale keeps each ring and meridian metrically consistent.
    basis = obj.matrix_world.to_3x3()
    axes = [basis @ Vector(v) for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    if min(a.length for a in axes) < EPS or abs(axes[0].length - axes[1].length) > EPS:
        raise ValueError(f'{obj.name}: nonuniform radial scale unsupported')
    if any(abs(axes[i].normalized().dot(axes[j].normalized())) > EPS
           for i, j in ((0, 1), (0, 2), (1, 2))):
        raise ValueError(f'{obj.name}: sheared lathe unsupported')
    points = [obj.matrix_world @ co for co in verts]
    slants = [0.0]
    vertical_folds = []
    for i in range(1, profile_count):
        if verts[i].z <= verts[i - 1].z:
            # The existing landmark spire profile folds down near its tip.
            # Preserve that geometry and measure its actual surface path.
            vertical_folds.append(i)
        slants.append(slants[-1] + (points[i] - points[i - 1]).length)
    for s in range(1, segments):
        for i in range(1, profile_count):
            distance = (points[s * profile_count + i] - points[s * profile_count + i - 1]).length
            if abs(distance - (slants[i] - slants[i - 1])) > EPS:
                raise ValueError(f'{obj.name}: unequal meridian lengths')
    perimeter = sum((points[s * profile_count] - points[((s + 1) % segments) * profile_count]).length
                    for s in range(segments))
    repeats = max(1, round(perimeter / tile))
    faces = []
    for pi, poly in enumerate(mesh.polygons[:side_count]):
        s = pi // (profile_count - 1)
        assignments = []
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            segment, level = divmod(vi, profile_count)
            unwrapped = segments if s == segments - 1 and segment == 0 else segment
            assignments.append((li, (unwrapped * repeats / segments, slants[level] / tile)))
        faces.append({'polygon': pi, 'assignments': assignments})
    return {'kind': 'lathe', 'tile_m': tile, 'faces': faces,
            'segments': segments, 'profile_count': profile_count,
            'angular_repeats': repeats, 'eave_perimeter_m': perimeter,
            'eave_tile_m': perimeter / repeats, 'meridian_m': slants[-1],
            'preserved_vertical_profile_folds': vertical_folds,
            'horizontal_density': 'converges toward tip; vertical density stays metric'}


def layout_roots_snapshot():
    layout = json.loads((ROOT / 'assets/blender/city_r5/layout.json').read_text(encoding='utf-8'))
    aliases = {'market': 'market_square', 'sw_well_gazebo': 'well_gazebo'}
    names, homes = [], []
    for landmark in layout['landmarks']:
        if landmark['kind'] == 'house_small_group':
            group = [f"kit_{landmark['id']}_{i}" for i in range(1, len(landmark['centers']) + 1)]
            names.extend(group)
            homes.extend(group)
        else:
            name = f"kit_{aliases.get(landmark['id'], landmark['id'])}"
            names.append(name)
            if landmark['kind'].startswith('house_'):
                homes.append(name)
    names.extend(['kit_plaza_fountain', 'kit_arcane_portal'])
    records = {}
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != 'EMPTY':
            raise RuntimeError(f'Missing authored layout root: {name}')
        records[name] = {'matrix_world': [list(row) for row in obj.matrix_world],
                         'child_meshes': sum(o.type == 'MESH' for o in obj.children_recursive)}
    if len(records) != 37 or len(homes) != 21:
        raise RuntimeError(f'Expected 37 layout roots and 21 home roots: {len(records)}/{len(homes)}')
    return {'root_count': len(records), 'home_count': len(homes), 'roots': records, 'homes': homes}


def plan_scene():
    bpy.context.view_layer.update()
    plans = []
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        kind = classify(obj)
        if kind is None:
            continue
        if obj.data.users != 1:
            raise ValueError(f'{obj.name}: shared mesh data must be resolved before UV repair')
        uv_values(obj.data)
        plan = gable_plan(obj) if kind == 'gable' else lathe_plan(obj)
        plans.append((obj, plan))
    if not plans:
        raise ValueError('No known unmerged R5 roof skins found')
    return plans


def apply_plans(plans):
    records = []
    for obj, plan in plans:
        layer, before = uv_values(obj.data)
        changed = set()
        for face in plan['faces']:
            for li, uv in face['assignments']:
                layer.data[li].uv = uv
                changed.add(li)
        for li, previous in enumerate(before):
            if li not in changed and tuple(layer.data[li].uv) != previous:
                raise RuntimeError(f'{obj.name}: non-roof-side UV unexpectedly changed')
        if any(not math.isfinite(x) for li in changed for x in layer.data[li].uv):
            raise RuntimeError(f'{obj.name}: nonfinite UV')
        error = 0.0
        if plan['kind'] == 'gable':
            for face in plan['faces']:
                loops = list(obj.data.polygons[face['polygon']].loop_indices)
                for j, li in enumerate(loops):
                    lj = loops[(j + 1) % len(loops)]
                    vi, vj = obj.data.loops[li].vertex_index, obj.data.loops[lj].vertex_index
                    length = (obj.matrix_world @ obj.data.vertices[vi].co - obj.matrix_world @ obj.data.vertices[vj].co).length
                    mapped = (layer.data[li].uv - layer.data[lj].uv).length * plan['tile_m']
                    error = max(error, abs(length - mapped))
            if error > 1e-4:
                raise RuntimeError(f'{obj.name}: metric UV edge error {error}')
        else:
            for face in plan['faces']:
                for li, expected in face['assignments']:
                    error = max(error, abs(layer.data[li].uv.y - expected[1]) * plan['tile_m'])
            if error > 1e-4:
                raise RuntimeError(f'{obj.name}: meridian UV error {error}')
        record = {k: v for k, v in plan.items() if k != 'faces'}
        record.update(name=obj.name, material=obj.data.materials[0].name,
                      polygons_modified=len(plan['faces']), loops_modified=len(changed),
                      texels_per_vertical_m=1024 / plan['tile_m'],
                      metric_error_m=error)
        records.append(record)
    return records


def make_fixture():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat = bpy.data.materials.new('roof_slate_blue')
    mat['city_tile_m'] = 2.2
    root = bpy.data.objects.new('fixture parent', None)
    bpy.context.scene.collection.objects.link(root)
    root.matrix_world = Matrix.Translation(Vector((20, -30, 8))) @ Matrix.Rotation(0.67, 4, 'Z')
    for i, scale in enumerate(((1, 1, 1), (1.7, 0.8, 1.3))):
        mesh = bpy.data.meshes.new(f'fixture gable {i}')
        mesh.from_pydata([(-5, -6, 2), (5, -6, 2), (0, -6, 7),
                          (-5, 6, 2), (5, 6, 2), (0, 6, 7)], [], GABLE_FACES)
        obj = bpy.data.objects.new(f'fixture {i} roof skin', mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.parent = root
        obj.scale = scale
        mesh.materials.append(mat)
        layer = mesh.uv_layers.new(name='UVMap')
        for datum in layer.data:
            datum.uv = (9.1, -2.3)
    profile = [(4, 0), (3.4, 1), (2.0, 5), (0.8, 9), (0, 12)]
    segments = 32
    verts = [(r * math.cos(s * math.tau / segments), r * math.sin(s * math.tau / segments), z)
             for s in range(segments) for r, z in profile]
    faces = [(s * len(profile) + i, ((s + 1) % segments) * len(profile) + i,
              ((s + 1) % segments) * len(profile) + i + 1, s * len(profile) + i + 1)
             for s in range(segments) for i in range(len(profile) - 1)]
    faces.append(tuple(s * len(profile) for s in reversed(range(segments))))
    mesh = bpy.data.meshes.new('fixture cone')
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new('fixture slate spire', mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = root
    obj.scale = (1.2, 1.2, 0.8)
    mesh.materials.append(mat)
    layer = mesh.uv_layers.new(name='UVMap')
    for datum in layer.data:
        datum.uv = (-3.8, 4.7)
    # A similarly textured sign must remain completely outside the selection.
    untouched = bpy.data.objects.new('fixture sign enamel face', mesh.copy())
    bpy.context.scene.collection.objects.link(untouched)
    bpy.context.view_layer.update()


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--stats', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if args.self_test:
        if args.candidate or args.stats:
            parser.error('--self-test writes no files; omit candidate/stats')
        make_fixture()
    elif args.dry_run:
        if args.candidate or args.stats:
            parser.error('--dry-run writes no files; omit candidate/stats')
    elif not args.candidate or not args.stats:
        parser.error('Production repair requires separate --candidate and --stats')
    source = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    source_hash = file_hash(source) if source else None
    if not args.self_test and not args.dry_run:
        canonical = {source, (CITY / 'reference_city.blend').resolve()}
        if args.candidate.resolve() in canonical or args.stats.resolve() in canonical:
            parser.error('Canonical/source writes are forbidden')
        if args.candidate.suffix != '.blend' or args.stats.suffix != '.json':
            parser.error('Candidate must be .blend and stats must be .json')
        if args.candidate.exists() or args.stats.exists():
            parser.error('Use fresh candidate and stats destinations')
        if source is None:
            parser.error('Open an authored source blend before production repair')
    plans = plan_scene()
    if args.dry_run:
        print(json.dumps({'roof_count': len(plans), 'gable_count': sum(p['kind'] == 'gable' for _, p in plans),
                          'lathe_count': sum(p['kind'] == 'lathe' for _, p in plans),
                          'names': [o.name for o, _ in plans]}, ensure_ascii=False))
        return
    before = geometry_digest(bpy.data.objects)
    roots_before = None if args.self_test else layout_roots_snapshot()
    counts_before = {'objects': len(bpy.context.scene.objects),
                     'meshes': sum(o.type == 'MESH' for o in bpy.context.scene.objects),
                     'materials': len(bpy.data.materials)}
    image_paths = {im.name: im.filepath for im in bpy.data.images if im.filepath}
    untouched = {o.name: uv_digest(o.data) for o in bpy.data.objects
                 if o.type == 'MESH' and not classify(o) and o.data.uv_layers.get('UVMap')}
    records = apply_plans(plans)
    after = geometry_digest(bpy.data.objects)
    if before != after:
        raise RuntimeError('Geometry, colors, transforms or material ownership changed')
    if roots_before is not None and layout_roots_snapshot() != roots_before:
        raise RuntimeError('Authored root placement or home count changed')
    for name, values in untouched.items():
        if uv_digest(bpy.data.objects[name].data) != values:
            raise RuntimeError(f'Non-roof UVs changed: {name}')
    receipt = {'schema': 'aetherfield.city-roof-uv-repair/1', 'fixture': args.self_test,
               'source': str(source) if source else None, 'source_sha256': source_hash,
               'geometry_sha256_before': before, 'geometry_sha256_after': after,
               'geometry_unchanged': True, 'source_saved': False, 'texture_files_changed': False,
               'roof_count': len(records), 'roofs': records,
               'counts_preserved': counts_before, 'layout_roots_preserved': roots_before,
               'image_filepaths': image_paths,
               'unselected_uv_meshes_preserved': len(untouched)}
    if not args.self_test:
        args.candidate.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.preferences.filepaths.save_version = 0
        # Candidate promotion must keep the master's authored //textures paths.
        bpy.ops.wm.save_as_mainfile(filepath=str(args.candidate.resolve()), check_existing=False,
                                   relative_remap=False, copy=True)
        if {im.name: im.filepath for im in bpy.data.images if im.filepath} != image_paths:
            raise RuntimeError('Candidate saving changed authored texture references')
        if file_hash(source) != source_hash:
            raise RuntimeError('Source changed during repair; do not promote the candidate')
        receipt['candidate'] = str(args.candidate.resolve())
        receipt['candidate_sha256'] = file_hash(args.candidate)
        args.stats.parent.mkdir(parents=True, exist_ok=True)
        args.stats.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
