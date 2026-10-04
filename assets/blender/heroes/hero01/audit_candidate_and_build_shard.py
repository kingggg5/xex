"""Inspect actual delivered H01 GLBs in fresh Blender scenes, then author an original VFX shard."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
sys.dont_write_bytecode = True
import bpy
import numpy as np
from mathutils import Matrix

p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
p.add_argument('--evidence', type=Path, required=True)
p.add_argument('--audit-only', action='store_true')
args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.out.mkdir(parents=True, exist_ok=True)
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

results = []
for lod in range(3):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.fps = 30
    src = args.out / f'hero01_swordsman_lod{lod}.glb'
    bpy.ops.import_scene.gltf(filepath=str(src), merge_vertices=False, import_shading='NORMALS',
                              bone_heuristic='BLENDER', guess_original_bind_pose=True)
    meshes = [o for o in scn.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers)]
    assert len(meshes) == 1, 'Expected one skinned mesh in delivered candidate'
    obj = meshes[0]
    arm = next(o for o in scn.objects if o.type == 'ARMATURE')
    assert len(arm.data.bones) == 47, 'Exported/imported joint count mismatch'
    obj.data.calc_loop_triangles()
    influences = [len(v.groups) for v in obj.data.vertices]
    sums = [sum(g.weight for g in v.groups) for v in obj.data.vertices]
    assert max(influences) <= 4
    assert max(abs(v - 1) for v in sums) < 1e-5
    arm.animation_data_create()
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    scn.frame_set(0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    def points():
        evaluated = obj.evaluated_get(dg)
        mesh = evaluated.to_mesh()
        co = np.array([tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices])
        evaluated.to_mesh_clear()
        return co
    rest = points()
    edges = np.array([tuple(e.vertices) for e in obj.data.edges], dtype=np.int32)
    lens = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    valid = lens > .002
    entry = {'lod': lod, 'file': str(src), 'sha256': sha(src), 'triangles': len(obj.data.loop_triangles),
             'joints': len(arm.data.bones), 'max_influences': max(influences),
             'max_weight_sum_error': max(abs(v - 1) for v in sums),
             'rest_bounds_min': rest.min(0).tolist(), 'rest_bounds_max': rest.max(0).tolist(),
             'uv_layers': len(obj.data.uv_layers), 'materials': len(obj.data.materials), 'clips': {}}
    for action in list(bpy.data.actions):
        arm.animation_data.action = action
        if action.slots:
            arm.animation_data.action_slot = action.slots[0]
        f0, f1 = action.frame_range
        samples = []
        root_positions = []
        for frame in sorted(set(float(v) for v in np.linspace(f0, f1, 13))):
            scn.frame_set(int(math.floor(frame)), subframe=frame - math.floor(frame))
            bpy.context.view_layer.update()
            co = points()
            lengths = np.linalg.norm(co[edges[:, 0]] - co[edges[:, 1]], axis=1)
            ratio = np.divide(lengths, lens, out=np.zeros_like(lengths), where=lens > 1e-9)
            worst = np.argsort(np.where(valid, ratio, 0))[-8:][::-1]
            root = arm.matrix_world @ arm.pose.bones['root'].matrix.translation
            root_positions.append(list(root))
            samples.append({'frame': frame, 'floor_min_m': float(co[:, 2].min()), 'floor_max_m': float(co[:, 2].max()),
                            'edge_stretch_p99': float(np.quantile(ratio[valid], .99)),
                            'edges_over_2x': int(np.sum(ratio[valid] > 2)),
                            'worst_edges': [{'ratio': float(ratio[i]), 'bind_center': ((rest[edges[i,0]] + rest[edges[i,1]]) / 2).tolist(),
                                             'deformed_center': ((co[edges[i,0]] + co[edges[i,1]]) / 2).tolist(),
                                             'bind_length_m': float(lens[i])} for i in worst]})
        rp = np.array(root_positions)
        entry['clips'][action.name] = {'range_frames_at30fps': [float(f0), float(f1)],
                                       'duration_s': float((f1-f0)/30), 'samples': samples,
                                       'root_xyz_drift_m': (rp.max(0) - rp.min(0)).tolist()}
    results.append(entry)
save(args.evidence, {'schema': 'xexoria.hero01-runtime-reimport/1', 'status': 'TECHNICAL_REIMPORT_PASS_VISUAL_UNVERIFIED',
                    'blender': bpy.app.version_string, 'inputs': results,
                    'limits': 'CPU numeric deformation inspection only. Root must assess native rendered poses, sword grip and world-space foot movement.'})
print('H01_REIMPORT', json.dumps([{'lod': r['lod'], 'tris': r['triangles'], 'joints': r['joints'],
                                 'clips': list(r['clips']), 'min_floor': min((s['floor_min_m'] for c in r['clips'].values() for s in c['samples']), default=float(r['rest_bounds_min'][2]))}
                                for r in results]), flush=True)
if args.audit_only:
    sys.exit(0)

# New authored crystal geometry; no provider source or VFX-kit clone.
shard_path = args.out / 'vfx_crystal_shard.glb'
assert not shard_path.exists(), 'Original shard output is immutable; choose a new revision rather than overwriting'
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new('vfx_crystal_shard_geometry')
verts = [(0, 0, 0), (-.06, .22, 0), (0, .22, .025), (.06, .22, 0), (0, .22, -.025), (0, .60, 0)]
faces = [(0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 1, 4), (5, 1, 2), (5, 2, 3), (5, 3, 4), (5, 4, 1)]
mesh.from_pydata(verts, [], faces)
mesh.update()
uv = mesh.uv_layers.new(name='UVMap')
for poly in mesh.polygons:
    poly.use_smooth = False
    for loop in poly.loop_indices:
        co = mesh.vertices[mesh.loops[loop].vertex_index].co
        uv.data[loop].uv = (co.x/.12+.5, co.y/.60)
obj = bpy.data.objects.new('vfx_crystal_shard', mesh)
bpy.context.scene.collection.objects.link(obj)
material = bpy.data.materials.new('vfx_crystal_shard_original')
material.use_nodes = True
bsdf = material.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (.08, .5, .8, 1)
bsdf.inputs['Metallic'].default_value = .10
bsdf.inputs['Roughness'].default_value = .25
bsdf.inputs['Emission Color'].default_value = (.01, .04, .12, 1)
bsdf.inputs['Emission Strength'].default_value = .30
mesh.materials.append(material)
obj['provenance'] = 'Original authored 6vertex8triangle faceted crystal; no provider or source clone'
obj['axis_contract'] = 'glTF/Babylon local+Y length; pivot at crystal base'
# Authoring Blender axes are converted on export: rotate mesh coordinates so exported long axis is+Y.
for v in mesh.vertices:
    x, y, z = v.co
    v.co = (x, -z, y)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.gltf(filepath=str(shard_path), export_format='GLB', use_selection=True,
                          export_materials='EXPORT', export_animations=False, export_extras=True,
                          export_cameras=False, export_lights=False)
receipt = {'schema': 'xexoria.original-crystal-shard/1', 'status': 'ORIGINAL_LOCAL_MESH_UV0_VERIFIED_NATIVE_VISUAL_DRAFT',
           'file': str(shard_path), 'bytes': shard_path.stat().st_size, 'sha256': sha(shard_path),
           'authorship': 'Original six vertices/eight triangles created by this bpy recipe; no Tripo or VFX source copied.',
           'triangles': 8, 'height_m': .60, 'width_m': .12, 'thickness_m': .05,
           'long_axis': 'glTF/Babylon local+Y', 'pivot': 'base at(0,0,0)', 'uv0': True,
           'material': 'Original blue PBR surface; parent VFX lane controls pooled runtime material.',
           'immutable': True, 'visual_gameplay_device': 'UNVERIFIED: root owns native VFX review'}
save(args.out / 'vfx_crystal_shard.receipt.json', receipt)
print('CRYSTAL_SHARD', json.dumps(receipt), flush=True)
