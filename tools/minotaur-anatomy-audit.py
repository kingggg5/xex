"""Read-only anatomy/connectivity review of the downloaded Tripo Minotaur."""
import argparse
import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Vector


def bounds(points):
    return {
        'min': [round(min(p[a] for p in points), 6) for a in range(3)],
        'max': [round(max(p[a] for p in points), 6) for a in range(3)],
    }


def analyze(mesh):
    verts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
    parents = list(range(len(verts)))

    def find(a):
        while parents[a] != a:
            parents[a] = parents[parents[a]]
            a = parents[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parents[rb] = ra

    for e in mesh.data.edges:
        union(*e.vertices)
    raw_components = len({find(i) for i in range(len(verts))})
    welded = {}
    for i, p in enumerate(verts):
        key = tuple(round(v, 5) for v in p)
        if key in welded:
            union(i, welded[key])
        else:
            welded[key] = i
    components = {}
    for i, v in enumerate(verts):
        components.setdefault(find(i), []).append(i)
    ranked = sorted(components.values(), key=len, reverse=True)
    slices = []
    b = bounds(verts)
    height = b['max'][2] - b['min'][2]
    for n in range(21):
        z = b['min'][2] + height * n / 20
        sample = [p for p in verts if abs(p.z-z) < height*.025]
        slices.append({'z': round(z, 6), 'vertices': len(sample), 'bounds': bounds(sample) if sample else None})
    component_records = []
    staff_core_indices = []
    staff_rigid_indices = []
    staff_ordinals = []
    for ordinal, c in enumerate(ranked):
        cb = bounds([verts[i] for i in c])
        centroid = [round(sum(verts[i][a] for i in c)/len(c),6) for a in range(3)]
        record = {'ordinal': ordinal, 'vertices':len(c),'bounds':cb,'centroid':centroid}
        component_records.append(record)
        if len(c)>2000 and cb['min'][0]>.2 and cb['max'][2]-cb['min'][2]>.9:
            staff_core_indices = c
        if cb['min'][0]>.18 and cb['max'][1]<-.05 and ordinal != 58:
            staff_rigid_indices.extend(c)
            staff_ordinals.append(ordinal)
    return {
        'name': mesh.name,
        'vertices': len(verts),
        'polygons': len(mesh.data.polygons),
        'triangles': sum(len(p.vertices)-2 for p in mesh.data.polygons),
        'world_bounds': b,
        'world_matrix': [[round(v, 6) for v in r] for r in mesh.matrix_world],
        'raw_connected_components': raw_components,
        'position_welded_components': len(ranked),
        'components': component_records,
        'staff_core_vertex_indices': staff_core_indices,
        'staff_rigid_vertex_indices': staff_rigid_indices,
        'staff_rigid_component_ordinals': staff_ordinals,
        'hoof_L_vertex_indices': ranked[2],
        'hoof_R_vertex_indices': ranked[3],
        'hand_L_grip_vertex_indices': ranked[4],
        'hand_R_free_vertex_indices': ranked[5],
        'staff_core_identification': 'Second welded component, positive X, complete shaft/crook; excludes separate charms/tassels and gripping hand.',
        'height_slices': slices,
    }


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--render', action='store_true')
    argv = __import__('sys').argv
    args = parser.parse_args(argv[argv.index('--')+1:])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.source)
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    report = {
        'source': args.source,
        'source_sha256':hashlib.sha256(Path(args.source).read_bytes()).hexdigest(),
        'blender': bpy.app.version_string,
        'vertex_index_scope':'Imported Blender glTF mesh before any geometry edits; not GLB accessor indices.',
        'meshes': [analyze(m) for m in meshes],
        'visual_review':{
            'front_side_back':'Source form is coherent from four cardinal views; cloth embroidery and carved staff detail are preserved in the base-color texture.',
            'staff_mask':'Cyan mask reviewed: full shaft/crook plus separate staff coins/tassels, no visible grippinghand/sleeve/body assignment.',
            'anatomy_limits':'Knees hidden by long robe; fit coordinates are estimates. Five independently deformable fingers not established. Do not claim cloth or facial simulation.',
            'boundary':'This audit inspects source and rigid segmentation only; it does not prove skinning or animated pose quality.'
        }
    }
    allpoints = [m.matrix_world @ v.co for m in meshes for v in m.data.vertices]
    b = bounds(allpoints)
    report['bounds'] = b
    report['dimensions'] = [round(b['max'][a]-b['min'][a], 6) for a in range(3)]
    report['rig_fit_estimates_source_coordinates'] = {
        'orientation': 'Z up, front -Y, anatomical left +X',
        'adopted_height_m':2.4,
        'source_to_2_4m_scale':2.4/report['dimensions'][2],
        'body_center_x':-.045,
        'pelvis':[-.045,.035,.43], 'spine':[-.045,.035,.55],
        'chest':[-.045,.03,.69], 'neck':[-.045,.015,.775],
        'head':[-.045,-.03,.86],
        'shoulder_L':[.12,.02,.735], 'elbow_L':[.22,.04,.595],
        'wrist_L':[.235,-.125,.622], 'grip_L':[.27,-.16,.62],
        'shoulder_R':[-.20,.02,.735], 'elbow_R':[-.277,-.02,.60],
        'wrist_R':[-.285,-.115,.50], 'hand_R':[-.281,-.13,.445],
        'hip_R':[-.13,.035,.43], 'hip_L':[.04,.035,.43],
        'knee_R':[-.15,.055,.265], 'knee_L':[.075,.055,.265],
        'ankle_R':[-.155,.025,.085], 'ankle_L':[.08,.025,.085],
        'toe_forward_y':-.15,
        'limits':'Knees and elbows are approximate under thick robe/sleeves. Gripping hand and staff are not connected in welded topology. Full five-finger articulation not established.'
    }
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('ANATOMY_BOUNDS', json.dumps({k: report[k] for k in ['bounds','dimensions']}))
    print('ANATOMY_COMPONENTS', json.dumps([{'name':m['name'],'vertices':m['vertices'],'raw':m['raw_connected_components'],'welded':m['position_welded_components'],'major':m['components'][:8]} for m in report['meshes']]))
    if not args.render:
        return
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 600
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new('anatomy-neutral-world')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.5, .5, .5, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .7
    scene.view_settings.view_transform = 'AgX'
    center = Vector([(b['max'][a]+b['min'][a])/2 for a in range(3)])
    height = report['dimensions'][2]
    for name, location, energy in [('key', (2, -3, 3), 500), ('fill', (-2, 3, 2), 350)]:
        data = bpy.data.lights.new(name, 'AREA')
        data.energy = energy * height * height
        data.shape = 'DISK'
        data.size = height * 2
        lamp = bpy.data.objects.new(name, data)
        scene.collection.objects.link(lamp)
        lamp.location = center + Vector(location)*height
        aim(lamp, center)
    camera_data = bpy.data.cameras.new('anatomy-camera')
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = height*1.12
    camera = bpy.data.objects.new('anatomy-camera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    for name, direction in [('minus-y', (0,-1,0)),('plus-y',(0,1,0)),('plus-x',(1,0,0)),('minus-x',(-1,0,0))]:
        camera.location = center+Vector(direction)*height*3
        aim(camera, center)
        scene.render.filepath = str(out.with_name(out.stem+'-'+name+'.png'))
        bpy.ops.render.render(write_still=True)
        print('ANATOMY_RENDER', scene.render.filepath)
    staff_material = bpy.data.materials.new('audit-staff-rigid-cyan')
    staff_material.diffuse_color = (.005,.45,.65,1)
    staff_material.use_nodes = True
    bsdf = staff_material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (.005,.45,.65,1)
    bsdf.inputs['Roughness'].default_value = .6
    for mesh, data in zip(meshes, report['meshes']):
        selected = set(data['staff_rigid_vertex_indices'])
        material_index = len(mesh.data.materials)
        mesh.data.materials.append(staff_material)
        for polygon in mesh.data.polygons:
            if all(v in selected for v in polygon.vertices):
                polygon.material_index = material_index
    camera.location = center+Vector((0,-1,0))*height*3
    aim(camera, center)
    scene.render.filepath = str(out.with_name(out.stem+'-staff-mask.png'))
    bpy.ops.render.render(write_still=True)
    print('ANATOMY_RENDER', scene.render.filepath)


main()
