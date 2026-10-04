"""Export compact semantic support geometry from the authored R5 city.

Never saves the input scene. Output is a review candidate, not automatic admission.
Run Blender with --factory-startup --disable-autoexec --background <master>
--python this-file -- --output planning/city-traversal-v1.json --evidence ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / 'assets/models/reference-city/r5/reference_city.blend'
LAYOUT = ROOT / 'assets/blender/city_r5/layout.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime(point):
    return [round(float(point.x), 5), round(float(point.z), 5), round(176 + float(point.y), 5)]


def kind_for(obj):
    name = obj.name
    if name.startswith(('walk_', 'traversal / ')):
        return 'ramp'
    if name == 'terrain / grass ground': return 'ground'
    if name.startswith(('terrain / path ', 'terrain / avenue ', 'terrain / canal promenade ')) and ' curb' not in name: return 'path'
    if name.startswith('terrain / plaza pavers '): return 'plaza'
    if name == 'terrain / plaza mortar bed': return 'plaza_base'
    if name in ('terrain / castle terrace / top', 'terrain / wizard terrace / top'): return 'terrace'
    if name == 'terrain / wizard stairs': return 'stairs'
    if name.startswith(('castle grand stair tread', 'castle stair landing')): return 'stairs'
    if name.startswith('bridge dressed flagstone'): return 'bridge'
    if name == 'castle terrace paving': return 'castle_forecourt'
    return None


def object_bounds(obj):
    points = [runtime(obj.matrix_world @ Vector(c)) for c in obj.bound_box]
    return {'min': [min(p[i] for p in points) for i in range(3)], 'max': [max(p[i] for p in points) for i in range(3)]}


def surface_mesh(obj, kind):
    """Upward support faces only; trim bevels can never become walkable walls."""
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        world = [obj.matrix_world @ v.co for v in mesh.vertices]
        faces = []
        for tri in mesh.loop_triangles:
            a, b, c = [world[i] for i in tri.vertices]
            normal = (b - a).cross(c - a)
            if normal.length <= 1e-10:
                continue
            normal.normalize()
            # Grass and paths may be graded; roofs are excluded semantically.
            threshold = math.cos(math.radians(50)) if kind in ('ground', 'path', 'ramp') else .98
            # The authored wizard stair tops are clockwise; their Z normal is
            # negative. They are the only downward top-face exception. Side
            # faces remain excluded, and this does not admit roofs/ceilings.
            accepted = abs(normal.z) > threshold if obj.name == 'terrain / wizard stairs' else normal.z > threshold
            if accepted:
                faces.append(tuple(tri.vertices))
        used = sorted({v for face in faces for v in face})
        remap = {v: i for i, v in enumerate(used)}
        verts = [runtime(world[i]) for i in used]
        return verts, [[remap[v] for v in face] for face in faces]
    finally:
        evaluated.to_mesh_clear()


def tree_for(vertices, triangles):
    # Candidate arrays are engine X/Y/Z; Blender BVH still supports the same
    # geometry with its query axis set to negative Y.
    return BVHTree.FromPolygons([Vector(v) for v in vertices], triangles, all_triangles=True)


def hit_height(tree, x, z):
    hit, _, _, _ = tree.ray_cast(Vector((x, 100, z)), Vector((0, -1, 0)), 200)
    return None if hit is None else float(hit.y)


def compact_ground(obj):
    original_vertices, original_triangles = surface_mesh(obj, 'ground')
    samples = [(v[0], v[2], v[1]) for v in original_vertices]
    samples += [tuple(sum(original_vertices[i][axis] for i in tri) / 3 for axis in (0, 2, 1)) for tri in original_triangles[::3]]
    original_tree = tree_for(original_vertices, original_triangles)
    samples += [(x, z, hit_height(original_tree, x, z))
                for x, z in [(-20, 146), (0, 217), (44, 226), (80, 264), (10, 24)]]
    # Compare against the original interpolated surface at the exact witness,
    # avoiding boundary rays that already miss due to 5-decimal quantization.
    samples = [(x,z,hit_height(original_tree,x,z)) for x,z,_ in samples]
    samples = [(x,z,y) for x,z,y in samples if y is not None]
    trials = []
    for mode, value in (('DISSOLVE', .00001), ('COLLAPSE', .30), ('COLLAPSE', .50), ('COLLAPSE', .75), ('ORIGINAL', 1.0)):
        copy = obj.copy()
        copy.data = obj.data.copy()
        copy.parent = None
        copy.matrix_world = obj.matrix_world.copy()
        bpy.context.scene.collection.objects.link(copy)
        if mode != 'ORIGINAL':
            modifier = copy.modifiers.new('Traversal-only simplification', 'DECIMATE')
            modifier.decimate_type = mode
            if mode == 'DISSOLVE':
                modifier.angle_limit = value
                modifier.use_dissolve_boundaries = False
            else:
                modifier.ratio = value
                modifier.use_collapse_triangulate = True
        bpy.context.view_layer.update()
        vertices, triangles = surface_mesh(copy, 'ground')
        tree = tree_for(vertices, triangles)
        errors = []
        misses = 0
        # Boundary vertex ray casts can miss after rounding. Compare only
        # originally covered interior witnesses; misses are recorded separately.
        for x, z, y in samples:
            if y is None: continue
            candidate_y = hit_height(tree, x, z)
            if candidate_y is None:
                misses += 1
            else:
                errors.append(abs(candidate_y - y))
        max_error = max(errors, default=0)
        original_data = copy.data
        bpy.data.objects.remove(copy, do_unlink=True)
        bpy.data.meshes.remove(original_data)
        trials.append({'mode': mode, 'value': value, 'triangles': len(triangles), 'sample_count': len(samples),
                       'misses': misses, 'max_vertical_error_m': max_error})
        if max_error <= .025 and misses <= 12:
            return vertices, triangles, trials
    return original_vertices, original_triangles, trials


def convex_hull(points):
    pts = sorted(set((round(p[0], 5), round(p[2], 5)) for p in points))
    def turn(a, b, c): return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0: lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0: upper.pop()
        upper.append(p)
    return [list(p) for p in lower[:-1]+upper[:-1]]


def blocker_for(obj):
    name = obj.name
    if any(text in name for text in (' foundation plinth', ' masonry body', ' counter carcass')): return 'solid_structure'
    if ' tree trunk' in name: return 'tree_trunk'
    if name.startswith(('castle nave stone body', 'castle side wing body', 'castle rear cloister', 'observatory tapered tower', 'windmill plaster tower', 'windmill millers shed')): return 'solid_structure'
    if name.startswith(('town gate round tower', 'gate west pier', 'gate east pier', 'gate curtain wall block', 'gate arch lintel', 'gate lion plinth', 'gate guardian statue')): return 'solid_structure'
    if name.startswith(('bridge parapet panel', 'bridge pale coping', 'terrain / castle terrace / retaining wall', 'terrain / wizard terrace / retaining wall',
                        'castle stair stone handrail', 'terrain / wizard stairs cheek')): return 'wall'
    if name.startswith(('fountain octagonal plinth', 'portal eight-sided dais', 'garden stone planter', 'plaza curved bench', 'plaza bench')): return 'street_object'
    return None


def export_blockers():
    blockers = []
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        if obj.type != 'MESH': continue
        kind = blocker_for(obj)
        if not kind: continue
        # Retaining walls are many separated strips; one convex hull would fill
        # their terrace and stair opening. Step/slope tests guard those edges.
        if '/ retaining wall' in obj.name: continue
        bounds = object_bounds(obj)
        points = [runtime(obj.matrix_world @ v.co) for v in obj.data.vertices]
        if kind == 'tree_trunk':
            low = bounds['min'][1]
            points = [p for p in points if p[1] <= low + 1.5] or points
        polygon = convex_hull(points)
        if len(polygon) >= 3:
            blockers.append({'id': obj.name, 'kind': kind, 'polygon_xz': polygon,
                             'y_min': bounds['min'][1], 'y_max': bounds['max'][1]})
    # Water is excluded from support. These thin safety bands prevent stepping
    # on any coarse grass triangles that overlap the canal's cut edge.
    for index, (z0, z1) in enumerate(((16, 59.95), (68.05, 96.95), (107.05, 130.7))):
        blockers.append({'id': f'canal-water-{index}', 'kind': 'water_hazard',
                         'polygon_xz': [[-6.4,z0],[6.4,z0],[6.4,z1],[-6.4,z1]], 'y_min': -100, 'y_max': .35})
    return blockers


def query_height(surfaces, x, z):
    values = [(s['id'], hit_height(s['_tree'], x, z)) for s in surfaces]
    hits = [(sid, y) for sid, y in values if y is not None]
    return max(hits, key=lambda row: row[1]) if hits else None


def route_probe(surfaces, name, points):
    records = []
    for a, b in zip(points, points[1:]):
        distance = math.hypot(b[0]-a[0], b[1]-a[1])
        count = max(1, math.ceil(distance/.10))
        for k in range(count):
            t = k/count
            x, z = a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t
            hit = query_height(surfaces, x, z)
            records.append({'xz': [round(x,4),round(z,4)], 'y': round(hit[1],5) if hit else None, 'surface': hit[0] if hit else None})
    hit = query_height(surfaces, *points[-1])
    records.append({'xz': points[-1], 'y': round(hit[1],5) if hit else None, 'surface': hit[0] if hit else None})
    failures = []
    for prev, current in zip(records, records[1:]):
        if current['y'] is None: failures.append({'xz': current['xz'], 'reason': 'missing_support'})
        elif prev['y'] is not None and abs(current['y']-prev['y']) > .36:
            failures.append({'xz': current['xz'], 'reason': 'unreachable_step', 'height_delta_m': round(current['y']-prev['y'],5), 'surface': current['surface']})
    return {'id': name, 'points_xz': points, 'samples': len(records), 'start_y': records[0]['y'], 'end_y': records[-1]['y'],
            'max_adjacent_delta_m': max((abs(b['y']-a['y']) for a,b in zip(records,records[1:]) if a['y'] is not None and b['y'] is not None), default=0),
            'surface_height_pass': not failures, 'failures': failures[:30], 'missing_support_samples': sum(r['y'] is None for r in records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--source-sha256', default='386e6babf4c88a29d8380939f7844f1fe32e4437ded73441d6a920f901dcfd99',
                        help='Explicit expected immutable input hash, for a reviewed authored repair candidate.')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    source = Path(bpy.data.filepath).resolve()
    if not source.is_relative_to(ROOT) or source.suffix.lower() != '.blend':
        raise RuntimeError('Load a source .blend within the project; no assembly or source overwrite allowed.')
    source_hash = digest(source)
    if source_hash != args.source_sha256:
        raise RuntimeError('Input hash changed: re-audit and pass the exact expected source hash before export.')
    bpy.context.view_layer.update()
    relevant = [o for o in bpy.context.scene.objects if o.type == 'MESH' and kind_for(o)]
    roots = [o for o in bpy.context.scene.objects if o.type == 'EMPTY' and o.name.startswith('kit_')]
    record = {'source_path':source.relative_to(ROOT).as_posix(),'source_sha256': source_hash, 'source_saved': False, 'blender': bpy.app.version_string,
              'objects': [{'name': o.name, 'kind': kind_for(o), 'polygons': len(o.data.polygons), 'bounds': object_bounds(o), 'parent': o.parent.name if o.parent else None} for o in relevant],
              'roots': [{'name': o.name, 'position': runtime(o.matrix_world.translation)} for o in roots]}
    if args.inspect:
        Path(args.evidence).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'objects': len(relevant), 'faces': sum(len(o.data.polygons) for o in relevant), 'roots': len(roots)}))
        return
    surfaces = []
    simplification = []
    for obj in sorted(relevant, key=lambda o: o.name):
        kind = kind_for(obj)
        if kind == 'ground':
            vertices, triangles, simplification = compact_ground(obj)
        else:
            vertices, triangles = surface_mesh(obj, kind)
        if not triangles: continue
        surfaces.append({'id': obj.name, 'kind': kind, 'vertices': vertices, 'triangles': triangles,
                         'bounds': object_bounds(obj), '_tree': tree_for(vertices, triangles)})
    count = sum(len(s['triangles']) for s in surfaces)
    if count >= 50000: raise RuntimeError(f'Traversal geometry exceeds its 50k hard budget: {count}')
    paths = [
        ('grand-stairs-up', [[0,216],[0,245],[0,247]]),
        ('grand-stairs-down', [[0,247],[0,245],[0,216]]),
        ('castle-door-approach', [[0,244],[0,252],[0,258]]),
        ('wizard-stairs-up', [[-50.4,236.35],[-51,237.2],[-57.6,246.5],[-61,252]]),
        ('wizard-stairs-down', [[-61,252],[-57.6,246.5],[-51,237.2],[-50.4,236.35]]),
        ('canal-bridge-cross', [[-14,102],[14,102]]),
        ('ring-bridge-cross', [[-14,64],[14,64]]),
        ('windmill-approach', [[44,226],[80,264],[90,276]]),
        ('gate-east-promenade', [[10.1,24],[10.1,64],[10.1,102],[10.1,133.4],[18,144]])
    ]
    routes = [route_probe(surfaces, name, points) for name, points in paths]
    blockers = export_blockers()
    landmarks = []
    for name,x,z in [('fountain',0,176),('castle-front-terrace',0,247),('castle-door-plinth',0,254),('wizard-terrace',-61,252),('windmill-path-end',90,276),('town-gate-east-path',10.1,24)]:
        result = query_height(surfaces,x,z)
        landmarks.append({'id':name,'x':x,'z':z,'support_y':round(result[1],5) if result else None,'surface':result[0] if result else None})
    # Compare road interiors to the true authored grass, with no geometry edits.
    ground = next(s for s in surfaces if s['kind']=='ground')
    sunk = []
    for s in surfaces:
        if s['kind'] != 'path': continue
        witnesses = [(sum(s['vertices'][i][0] for i in tri)/3, sum(s['vertices'][i][2] for i in tri)/3, sum(s['vertices'][i][1] for i in tri)/3) for tri in s['triangles']]
        deltas = [(x,z,hit_height(ground['_tree'],x,z),y) for x,z,y in witnesses]
        bad = [(x,z,g,y) for x,z,g,y in deltas if g is not None and g-y > .015]
        if bad:
            worst = max(bad,key=lambda row:row[2]-row[3])
            sunk.append({'id':s['id'],'samples_below_grass':len(bad),'sample_count':len(witnesses),'max_penetration_m':round(worst[2]-worst[3],5),'worst_xz':[round(worst[0],5),round(worst[1],5)],'grass_y':round(worst[2],5),'path_y':round(worst[3],5)})
    for s in surfaces: del s['_tree']
    data = {'schema':'xexoria.city-traversal/1','status':'candidate-not-admitted','units':'metres',
            'coordinate_basis':'runtime=[BlenderX,BlenderZ,176+BlenderY]; glTF LH reflection then root Y=pi',
            'city_bounds':{'min_x':-124,'max_x':124,'min_z':8 if any(s['id'].startswith('traversal / city arrival ') for s in surfaces) else 14,'max_z':304},
            'source':{'master_path':source.relative_to(ROOT).as_posix(),'master_sha256':source_hash,'layout_path':LAYOUT.relative_to(ROOT).as_posix(),'layout_sha256':digest(LAYOUT)},
            'contract':{'max_step_m':.36,'max_slope_degrees':50,'feet_offset_m':.015,'query_epsilon_m':.00005,'max_movement_substep_m':.10,
                        'height_rule':'Highest upward support triangle containing XZ; reject motion if target exceeds current support by max_step_m. Query subdivisions of a movement segment to prevent tunnelling. No support returns null within authored city bounds. Outside city use existing zone surface.',
                        'collision_rule':'Player capsule radius expands polygon_xz; blocker active only when capsule vertical interval overlaps [y_min,y_max]. Blocked objects are sealed exterior structures, not enterable interiors.',
                        'slope_rule':'Use triangle slope <=max_slope_degrees; stairs are discrete support risers checked by max_step_m. Do not permit support teleport to a terrace.'},
            'surfaces':surfaces,'blockers':blockers,'landmarks':landmarks,
            'review':{'terrain_geometry_changed':False,'runtime_art_changed':False,'route_height_failures':[r['id'] for r in routes if not r['surface_height_pass']],
                      'known_limits':['Routes measure support heights only; consumer must also apply blockers.', 'Castle forecourt and bridge approaches have actual art ledges that require authored ramps.', 'Source ray audit does not establish real GPU visual quality.']}}
    output = Path(args.output).resolve()
    evidence = Path(args.evidence).resolve()
    protected = {MASTER.resolve(), source}
    if output in protected or evidence in protected: raise RuntimeError('Cannot overwrite source master.')
    output.write_text(json.dumps(data,separators=(',',':'))+'\n',encoding='utf-8')
    record.update({'created_utc':datetime.now(timezone.utc).isoformat(),'schema':data['schema'],'output':str(output),'output_sha256':digest(output),'output_bytes':output.stat().st_size,
                   'surface_count':len(surfaces),'triangle_count':count,'blocker_count':len(blockers),'ground_simplification':simplification,'landmarks':landmarks,'routes':routes,'sunk_paths':sunk})
    if digest(source) != source_hash: raise RuntimeError('Input master changed during read-only extraction.')
    evidence.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output_bytes':output.stat().st_size,'surface_count':len(surfaces),'triangles':count,'blockers':len(blockers),'routes_failed':data['review']['route_height_failures'],'sunk_paths':sunk,'ground_trials':simplification}))


if __name__ == '__main__':
    main()
