"""CPU-only pose audit of the actual map-free clip export; never render or modify inputs."""
import argparse
import json
import math
import sys
from pathlib import Path
sys.dont_write_bytecode=True
import bpy
import numpy as np
from mathutils import Matrix
P=argparse.ArgumentParser();P.add_argument('--input',type=Path,required=True);P.add_argument('--report',type=Path,required=True)
a=P.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=30
bpy.ops.import_scene.gltf(filepath=str(a.input),merge_vertices=False,import_shading='NORMALS',bone_heuristic='BLENDER',guess_original_bind_pose=True)
arm=next(o for o in scene.objects if o.type=='ARMATURE')
mesh=next(o for o in scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers))
assert len(arm.data.bones)==47 and len(bpy.data.actions)==14
arm.animation_data_create();arm.animation_data.action=None
for bone in arm.pose.bones:bone.matrix_basis=Matrix.Identity(4)
scene.frame_set(0);bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
def positions():
    ev=mesh.evaluated_get(dg);data=ev.to_mesh();p=np.array([tuple(ev.matrix_world@v.co) for v in data.vertices]);ev.to_mesh_clear();return p
rest=positions();edges=np.array([tuple(e.vertices) for e in mesh.data.edges],dtype=np.int32)
lengths=np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]],axis=1);valid=lengths>.002
rows=[]
for action in bpy.data.actions:
    arm.animation_data.action=action;arm.animation_data.action_slot=action.slots[0]
    f0,f1=action.frame_range;times=np.linspace(float(f0),float(f1),17)
    if action.name=='swordsman.skill_arc':times=np.unique(np.append(times,7.5))
    if action.name=='swordsman.skill_nova':times=np.unique(np.append(times,4.5))
    samples=[];roots=[]
    for frame in times:
        scene.frame_set(int(math.floor(frame)),subframe=frame-math.floor(frame));bpy.context.view_layer.update();p=positions()
        ratio=np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)[valid]/lengths[valid]
        root=arm.matrix_world@arm.pose.bones['root'].matrix.translation;roots.append(list(root))
        samples.append({'frame':float(frame),'time_s':float(frame/30),'floor_min_m':float(p[:,2].min()),'height_max_m':float(p[:,2].max()),
                        'edge_stretch_p99':float(np.quantile(ratio,.99)),'edges_above2x':int((ratio>2).sum()),
                        'right_socket_world':list(arm.matrix_world@arm.pose.bones['socket_weapon_R'].matrix.translation)})
    roots=np.array(roots);drift=roots.max(0)-roots.min(0);assert float(np.max(drift))<1e-6
    rows.append({'clip':action.name,'frames':[float(f0),float(f1)],'duration_s':float((f1-f0)/30),'root_xyz_drift_m':drift.tolist(),
                 'samples':samples,'native_visual':'UNVERIFIED'})
result={'schema':'xexoria.hero01-exported-pose-audit/1','status':'ACTUAL_EXPORT_CPU_AUDIT_COMPLETE_NATIVE_REVIEW_REQUIRED',
        'input':str(a.input),'joint_count':47,'clip_count':14,'maps_loaded':len(bpy.data.images),'rows':rows,
        'limits':['Plate/cloth stretch, death support and sword grip need native review. No render, GPU or gameplay approval.']}
a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps([{'clip':r['clip'],'duration':r['duration_s'],'min_floor':min(s['floor_min_m'] for s in r['samples']),
                  'max_stretch_p99':max(s['edge_stretch_p99'] for s in r['samples']),'end_height':r['samples'][-1]['height_max_m']} for r in rows]))
