"""Prepared r02 gate-form hypothesis. Execute only in the assigned CPU window.

Reads the immutable r01 architecture and original decoded HLOD. No renders,
terrain rebuild, placement/collider writes, texture generation or source edits.
One exact Boolean per named recess; any topology/budget failure stops export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
R01 = ROOT / 'assets/models/reference-city/r5/arrival-hlod-r01'
OUT = ROOT / 'assets/models/reference-city/r5/arrival-hlod-r02'
BASE_SHA = '771fdf2bc450c3df2cc937f231176145d9d27bfae7772b616298a0dd063038b5'
R01_SHA = '8aaa42a1ab65900d25ba46845cf02c8cd9f77139ab3b7c1914f44a040c0dae1c'
ARCH_SHA = '40220a3a6efc8f6a47c921892fbb4220d5d359cba8be5f4baed3c4ff6815ed9a'
GATE_IDS = ('m5-p0-c193', 'm5-p0-c194', 'm5-p0-c195', 'm5-p0-c196')
WINGS = ('m5-p0-c193', 'm5-p0-c195')
TRI_LIMIT = 25000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_glb(path):
    raw = path.read_bytes()
    if struct.unpack_from('<III', raw) != (0x46546C67, 2, len(raw)):
        raise RuntimeError('Invalid decoded baseline GLB')
    document = binary = None
    cursor = 12
    while cursor < len(raw):
        size, kind = struct.unpack_from('<II', raw, cursor)
        payload = raw[cursor + 8:cursor + 8 + size]
        if kind == 0x4E4F534A:
            document = json.loads(payload)
        elif kind == 0x004E4942:
            binary = payload
        cursor += size + 8
    if document is None or binary is None:
        raise RuntimeError('Missing decoded baseline chunks')
    return document, binary


def component_points(document, binary, component):
    primitive = document['meshes'][component['mesh']]['primitives'][0]
    node = document['nodes'][component['node']]

    def rows(accessor_id):
        accessor = document['accessors'][accessor_id]
        view = document['bufferViews'][accessor['bufferView']]
        dims = {'SCALAR': 1, 'VEC3': 3}[accessor['type']]
        code = {5122: 'h', 5123: 'H'}[accessor['componentType']]
        width = 2
        stride = view.get('byteStride', width * dims)
        begin = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        return [struct.unpack_from('<' + code * dims, binary, begin + i * stride)
                for i in range(accessor['count'])]

    positions = rows(primitive['attributes']['POSITION'])
    indices = [row[0] for row in rows(primitive['indices'])]
    used = set(index for ordinal in component['triangleOrdinals']
               for index in indices[ordinal * 3:ordinal * 3 + 3])
    points = set()
    for index in used:
        point = [node['translation'][a] + positions[index][a] / 32767 * node['scale'][a]
                 for a in range(3)]
        points.add((point[0], -point[2], point[1]))
    return [Vector(point) for point in points]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(OUT))
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    output = Path(parser.parse_args(raw).out).resolve()
    if output != OUT.resolve():
        raise RuntimeError('Only the new r02 destination is owned')
    baseline = ROOT / 'apps/client/src/assets/models/env_reference_city_hlod.glb'
    r01_runtime = R01 / 'arrival-hlod-r01-runtime.glb'
    r01_architecture = R01 / 'architecture-only.glb'
    if (sha(baseline), sha(r01_runtime), sha(r01_architecture)) != (BASE_SHA, R01_SHA, ARCH_SHA):
        raise RuntimeError('Immutable source pin changed')
    outputs = [output / name for name in ('architecture-only.glb', 'architecture-source.blend', 'architecture-receipt.json')]
    if any(path.exists() for path in outputs):
        raise RuntimeError('Create-only r02 output already exists')
    inspection = json.loads((R01 / 'cpu-inspection.json').read_text())
    original_recipe = json.loads((R01 / 'architecture-receipt.json').read_text())
    components = {component['id']: component for component in inspection['components']}
    document, binary = read_glb(R01 / 'baseline-decoded-inspection.glb')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 6
    bpy.ops.import_scene.gltf(filepath=str(r01_architecture))
    imported = list(scene.objects)
    if any(obj.type != 'MESH' for obj in imported):
        raise RuntimeError('Unexpected non-mesh r01 architecture')
    for obj in imported:
        if obj.get('arrival_source_component') in WINGS:
            bpy.data.objects.remove(obj, do_unlink=True)
    preserved = [obj for obj in scene.objects]
    retained_ids = set(original_recipe['selected_ids']) - set(WINGS)
    if {obj.get('arrival_source_component') for obj in preserved} != retained_ids:
        raise RuntimeError('Retained six r01 component identities changed')
    for obj in preserved:
        # Bake importer axes without recentering or scaling world geometry.
        obj.data.transform(obj.matrix_world)
        obj.matrix_world = Matrix.Identity(4)
    material = bpy.data.materials.get('HLOD_Stone')
    if material is None:
        raise RuntimeError('Shared Stone material missing')
    created = []
    recesses = []

    def make_mesh(name, vertices, faces, origin, keep=True):
        data = bpy.data.meshes.new(name)
        data.from_pydata(vertices, [], faces)
        data.update()
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        data.materials.append(material)
        obj['arrival_source_component'] = origin
        obj['original_expression'] = 'battered chamfered gate pier / blind arched reveal'
        if keep:
            created.append(obj)
        return obj

    def closed_rings(name, rings, origin, keep=True):
        count = len(rings[0])
        if any(len(ring) != count for ring in rings):
            raise RuntimeError('Ring topology mismatch')
        vertices = [point for ring in rings for point in ring]
        faces = [tuple(reversed(range(count))), tuple(range((len(rings) - 1) * count, len(rings) * count))]
        for ring in range(len(rings) - 1):
            for index in range(count):
                following = (index + 1) % count
                faces.append((ring * count + index, ring * count + following,
                              (ring + 1) * count + following, (ring + 1) * count + index))
        return make_mesh(name, vertices, faces, origin, keep)

    def finish(obj, colors=True):
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        if any(not edge.is_manifold for edge in bm.edges):
            bm.free()
            raise RuntimeError(obj.name + ': non-manifold gate geometry; no retry')
        if any(face.calc_area() < 1e-9 for face in bm.faces):
            bm.free()
            raise RuntimeError(obj.name + ': degenerate gate geometry')
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        if mesh.validate(verbose=False, clean_customdata=False):
            raise RuntimeError(obj.name + ': geometry required repair')
        if not colors:
            return
        for attribute in list(mesh.color_attributes):
            mesh.color_attributes.remove(attribute)
        attribute = mesh.color_attributes.new(name='COLOR_0', type='FLOAT_COLOR', domain='CORNER')
        for polygon in mesh.polygons:
            color = (.92, .95, .97)
            if obj.get('arrival_arch_rim'):
                color = (.78, .82, .86)
            else:
                center = sum((mesh.vertices[index].co for index in polygon.vertices), Vector()) / len(polygon.vertices)
                for recess in recesses:
                    if recess['object'] != obj:
                        continue
                    local = center - recess['surface'](0, center.z)
                    offset = local.dot(recess['inward'])
                    horizontal = local.dot(recess['tangent'])
                    if (.025 < offset < recess['depth'] + .03 and
                            abs(horizontal) < recess['halfwidth'] + .03 and
                            recess['bottom'] - .03 < center.z < recess['top'] + .03):
                        color = (.36, .40, .44)
                        break
            for index in polygon.loop_indices:
                attribute.data[index].color = (*color, 1)
        mesh.color_attributes.active_color_index = mesh.color_attributes.find('COLOR_0')
        for uv in list(mesh.uv_layers):
            mesh.uv_layers.remove(uv)
        uv = mesh.uv_layers.new(name='UVMap')
        for polygon in mesh.polygons:
            axes = sorted(range(3), key=lambda axis: abs(polygon.normal[axis]))[:2]
            for index in polygon.loop_indices:
                point = mesh.vertices[mesh.loops[index].vertex_index].co
                uv.data[index].uv = (point[axes[0]] * .25, point[axes[1]] * .25)

    def arch(halfwidth, bottom, spring, segments=8):
        return [(-halfwidth, bottom), (halfwidth, bottom), (halfwidth, spring)] + [
            (math.cos(math.pi * index / segments) * halfwidth,
             spring + math.sin(math.pi * index / segments) * halfwidth)
            for index in range(1, segments + 1)]

    def cut_recess(obj, origin, label, surface, tangent, inward, halfwidth, bottom, spring, depth, rim_width):
        outline = arch(halfwidth, bottom, spring)
        rings = [[tuple(surface(u, z) + inward * distance) for u, z in outline]
                 for distance in (-.08, depth)]
        cutter = closed_rings(origin + ' ' + label + ' cutter', rings, origin, keep=False)
        finish(cutter, colors=False)
        modifier = obj.modifiers.new(name='One bounded ' + label + ' recess', type='BOOLEAN')
        modifier.operation = 'DIFFERENCE'
        modifier.solver = 'EXACT'
        modifier.object = cutter
        modifier.material_mode = 'INDEX'
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        baked = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
        if baked is None:
            raise RuntimeError('Boolean evaluation returned no mesh')
        old_mesh = obj.data
        obj.data = baked
        obj.modifiers.remove(modifier)
        bpy.data.objects.remove(cutter, do_unlink=True)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
        finish(obj, colors=False)
        # One continuous arch band, rather than per-brick or repeated shelves.
        outer = arch(halfwidth + rim_width, bottom - rim_width, spring)
        count = len(outline)
        if len(outer) != count:
            raise RuntimeError('Arch rim topology mismatch')
        vertices = [tuple(surface(u, z) + inward * distance)
                    for distance in (-.04, .035) for loop in (outer, outline) for u, z in loop]
        faces = []
        for index in range(count):
            following = (index + 1) % count
            faces.extend([(index, following, count + following, count + index),
                          (2 * count + index, 3 * count + index, 3 * count + following, 2 * count + following),
                          (index, 2 * count + index, 2 * count + following, following),
                          (count + index, count + following, 3 * count + following, 3 * count + index)])
        rim = make_mesh(origin + ' ' + label + ' single arch band', vertices, faces, origin)
        rim['arrival_arch_rim'] = True
        finish(rim)
        recesses.append({'object': obj, 'surface': surface, 'tangent': tangent, 'inward': inward,
                        'depth': depth, 'halfwidth': halfwidth, 'bottom': bottom, 'top': spring + halfwidth})

    for origin in GATE_IDS:
        component = components[origin]
        lo = component['boundsBlender']['min']
        hi = component['boundsBlender']['max']
        z0, z1 = lo[2], hi[2]
        if origin in WINGS:
            x0, y0 = lo[:2]
            x1, y1 = hi[:2]
            bevel = .45
            foot = [Vector(point) for point in [(x0 + bevel, y0, z0), (x1 - bevel, y0, z0),
                    (x1, y0 + bevel, z0), (x1, y1 - bevel, z0), (x1 - bevel, y1, z0),
                    (x0 + bevel, y1, z0), (x0, y1 - bevel, z0), (x0, y0 + bevel, z0)]]
            center = Vector(((x0 + x1) / 2, (y0 + y1) / 2, z0))
            top = [Vector((center.x + (point.x - center.x) * .935,
                           center.y + (point.y - center.y) * .88, z1)) for point in foot]
            lower_z = z0 + 1.0
            lower = [Vector((center.x + (point.x - center.x) * .985,
                             center.y + (point.y - center.y) * .96, lower_z)) for point in foot]
            rings = [foot, [Vector((point.x, point.y, z0 + .62)) for point in foot], lower, top]
            face_indices = [0, 6 if origin == WINGS[0] else 2]
            niche_sizes = [(1.55, z0 + 1.45, z0 + 4.3, .45, .23),
                           (.38, z0 + 1.6, z0 + 4.0, .30, .13)]
        else:
            points = component_points(document, binary, component)
            foot = sorted([point for point in points if abs(point.z - z0) < .003],
                          key=lambda point: math.atan2(point.y - (lo[1] + hi[1]) / 2,
                                                       point.x - (lo[0] + hi[0]) / 2))
            top = sorted([point for point in points if abs(point.z - z1) < .003],
                         key=lambda point: math.atan2(point.y - (lo[1] + hi[1]) / 2,
                                                      point.x - (lo[0] + hi[0]) / 2))
            if len(foot) != 10 or len(top) != 10:
                raise RuntimeError(origin + ': original ten-sided tower rings changed')
            center = sum(foot, Vector()) / len(foot)
            lower_z = z0 + 1.25
            lower = [Vector((center.x + (point.x - center.x) * .94,
                             center.y + (point.y - center.y) * .94, lower_z)) for point in foot]
            rings = [foot, [Vector((point.x, point.y, z0 + .65)) for point in foot], lower, top]
            front_index = min(range(10), key=lambda index: (foot[index].y + foot[(index + 1) % 10].y) / 2)
            face_indices = [front_index]
            niche_sizes = [(1.02, z0 + 1.75, z0 + 4.9, .50, .22)]
        body = closed_rings(origin + ' grounded battered pier', rings, origin)
        finish(body, colors=False)
        for index, params in zip(face_indices, niche_sizes):
            next_index = (index + 1) % len(foot)
            tangent = (lower[next_index] - lower[index]).normalized()
            inward = Vector((-tangent.y, tangent.x, 0))
            midpoint = (lower[index] + lower[next_index]) / 2
            if inward.dot(center - midpoint) < 0:
                inward = -inward
            # Map arch to the actual battered facet, maintaining fixed heights.
            def surface(u, z, index=index, next_index=next_index, tangent=tangent,
                        lower=lower, top=top, lower_z=lower_z, z1=z1):
                fraction = (z - lower_z) / (z1 - lower_z)
                a = lower[index].lerp(top[index], fraction)
                b = lower[next_index].lerp(top[next_index], fraction)
                point = (a + b) / 2 + tangent * u
                point.z = z
                return point
            halfwidth, bottom, spring, depth, rim_width = params
            for z in (bottom - rim_width, spring + halfwidth + rim_width):
                fraction = (z - lower_z) / (z1 - lower_z)
                width = (lower[index].lerp(top[index], fraction) - lower[next_index].lerp(top[next_index], fraction)).length
                if 2 * (halfwidth + rim_width) >= width - .04:
                    raise RuntimeError(origin + ': arch exceeds existing facet width')
            cut_recess(body, origin, 'front' if index == face_indices[0] else 'side',
                       surface, tangent, inward, halfwidth, bottom, spring, depth, rim_width)
        finish(body)

    bpy.context.view_layer.update()
    per_component = {}
    selected_ids = original_recipe['selected_ids'] + [origin for origin in GATE_IDS if origin not in WINGS]
    for origin in selected_ids:
        objects = [obj for obj in scene.objects if obj.get('arrival_source_component') == origin]
        points = [obj.matrix_world @ vertex.co for obj in objects for vertex in obj.data.vertices]
        if not points:
            raise RuntimeError(origin + ': output component missing')
        minimum = [min(point[axis] for point in points) for axis in range(3)]
        maximum = [max(point[axis] for point in points) for axis in range(3)]
        expected = components[origin]['boundsBlender']
        if max(abs(minimum[a] - expected['min'][a]) for a in range(3)) > .00015 or max(abs(maximum[a] - expected['max'][a]) for a in range(3)) > .00015:
            raise RuntimeError(origin + ': original component envelope changed')
        tris = sum(sum(len(polygon.vertices) - 2 for polygon in obj.data.polygons) for obj in objects)
        per_component[origin] = {'old_triangles': components[origin]['triangles'], 'new_triangles': tris,
                                 'bounds': {'min': minimum, 'max': maximum}, 'r01_form_retained': origin in retained_ids}
    removed = sum(components[origin]['triangles'] for origin in selected_ids)
    added = sum(value['new_triangles'] for value in per_component.values())
    total = 21400 - removed + added
    if total > TRI_LIMIT:
        raise RuntimeError('r02 exceeds25k triangle cap; no automatic decimation or retry')
    names = {slot.name for obj in scene.objects for slot in obj.data.materials if slot}
    if not names <= {source['name'] for source in inspection['materials']}:
        raise RuntimeError('Unexpected new material')
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.context.view_layer.objects.active = created[0]
    bpy.ops.export_scene.gltf(filepath=str(outputs[0]), export_format='GLB', use_selection=True,
                             export_yup=True, export_apply=True, export_materials='EXPORT',
                             export_vertex_color='ACTIVE', export_animations=False,
                             export_cameras=False, export_lights=False, export_extras=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(outputs[1]))
    if (sha(baseline), sha(r01_runtime), sha(r01_architecture)) != (BASE_SHA, R01_SHA, ARCH_SHA):
        raise RuntimeError('Protected source changed during export')
    receipt = {'schema': 'xexoria.arrival-architecture/2', 'status': 'CPU_FORM_ONLY_NATIVE_A_B_REQUIRED',
               'source_sha256': BASE_SHA, 'r01_runtime_sha256': R01_SHA, 'selected_ids': selected_ids,
               'new_gate_component_ids': list(GATE_IDS), 'removed_triangles': removed,
               'new_architecture_triangles': added, 'projected_triangles': total,
               'per_component': per_component, 'materials': 'existing8names;targetedCOLOR_0;noimages',
               'method': 'Four existing gate bodies: chamfered/battered wing piers and splayed ten-sided tower feet, closed shallow arch reveals with one continuous rim; six other r01 forms retained.',
               'limitations': ['Existing rectangular/cylindrical physical collision remains; visual facets are recessed inside the old envelope.',
                               'No far castle, ground palette, world scale, grass, roof or default adoption claim.',
                               'Exact Boolean cuts are bounded and topology-gated, with no retry/relaxed validation.'],
               'terrain_created_or_changed': 0, 'trees_created': 0, 'colliders_changed': 0,
               'renders': 0, 'threads': 6, 'glb_sha256': sha(outputs[0]), 'blender_version': bpy.app.version_string}
    outputs[2].write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'triangles': total, 'added': added,
                      'removed': removed, 'sha256': receipt['glb_sha256']}))


if __name__ == '__main__':
    main()
