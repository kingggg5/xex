
# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[5]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import bpy,json,sys,hashlib,math,re
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path(str(_XEXORIA_REPO));E=ROOT/'planning/evidence/blueprint-p0-20261003/cc0/sheep-v1';OUT=ROOT/'assets/models/blueprint-cc0/candidates/sheep-v1/r03'
sys.path.insert(0,str(ROOT/'assets/blender/tools'));from export_helper import export_glb
SOURCE=Path(str(_XEXORIA_ASSET_SOURCE / 'sources/cc0/quaternius-farm-animal-2018-author-mirror/original-extracted/Farm Animals by @Quaternius/Blends/Sheep.blend'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
SOURCE_SHA='d4f137f393e5b3e5ba28af0977efbaef6e0ba7a6682e35b35f868f5caff47c7e'
if sha(SOURCE)!=SOURCE_SHA:raise RuntimeError('Immutable source changed')
OUT.mkdir(parents=True,exist_ok=True);(OUT/'source').mkdir(exist_ok=True)
scene=bpy.context.scene;scene.render.threads_mode='FIXED';scene.render.threads=6;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE');mesh=next(o for o in bpy.data.objects if o.type=='MESH')
actions=sorted(bpy.data.actions,key=lambda a:a.name);clip_ranges={a.name:list(a.frame_range) for a in actions}
def points():
 bpy.context.view_layer.update();ob=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get());return [ob.matrix_world@v.co for v in ob.data.vertices]
def pose(action,frame):
 arm.animation_data.action=action
 if action.slots:arm.animation_data.action_slot=action.slots[0]
 scene.frame_set(int(frame));return points()
# Preserve and compare source deformed world vertices while baking only the mesh
# object basis. Bone positions/weights/IK and all source action curves stay intact.
tracks=arm.animation_data.nla_tracks
for t in tracks:t.mute=True
samples={}
for action in actions:
 for frame in sorted(set([action.frame_range[0],sum(action.frame_range)/2,action.frame_range[1]])):
  samples[(action.name,int(frame))]=pose(action,frame)
arm.data.pose_position='REST';bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT');mesh.select_set(True);bpy.context.view_layer.objects.active=mesh
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
arm.data.pose_position='POSE'
delta=0
for (name,frame),before in samples.items():
 after=pose(bpy.data.actions[name],frame);delta=max(delta,max((a-b).length for a,b in zip(before,after)))
if delta>1e-5:raise RuntimeError('Source pose changed while baking meshbasis '+str(delta))
arm.data.pose_position='REST';bpy.context.view_layer.update();rest=points();mn=[min(v[i] for v in rest) for i in range(3)];mx=[max(v[i] for v in rest) for i in range(3)]
scale=1/(mx[2]-mn[2]);centre=[(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,mn[2]]
carrier=bpy.data.objects.new('blueprint_sheep_metre_root',None);scene.collection.objects.link(carrier);carrier.scale=(scale,scale,scale);carrier.location=tuple(-v*scale for v in centre);arm.parent=carrier;arm.matrix_parent_inverse=Matrix.Identity(4)
bpy.context.view_layer.update()
# glTF skinned mesh world transforms must be identity. Bake the common metre
# transform into mesh coordinates and keep it on the rig hierarchy; IBM then
# expresses the same transformed bind pose. This is tested against source clips.
mesh.parent=None;mesh.matrix_parent_inverse=Matrix.Identity(4);mesh.matrix_world=Matrix.Identity(4);mesh.data.transform(carrier.matrix_world);mesh.data.update()
carrier['licence']='CC0';carrier['sourceSha256']=SOURCE_SHA;carrier['targetHeightM']=1.;carrier['sourceAuthor']='Quaternius2018'
arm.data.pose_position='POSE';norm_delta=0
for (name,frame),before in samples.items():
 after=pose(bpy.data.actions[name],frame);expected=[(v-Vector(centre))*scale for v in before];norm_delta=max(norm_delta,max((a-b).length for a,b in zip(expected,after)))
if norm_delta>1e-5:raise RuntimeError('Animation unit normalization failed '+str(norm_delta))
def linear(rgb):return [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
materials=[];face_material_indices=[p.material_index for p in mesh.data.polygons]
for old in mesh.data.materials:
 name='sheep_wool_ivory' if old.name=='White' else 'sheep_face_hooves_brown'
 rgb=[int(('E6DDC9' if old.name=='White' else '665341')[i:i+2],16)/255 for i in [0,2,4]]
 m=bpy.data.materials.new(name);m.use_nodes=True;bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*linear(rgb),1);bs.inputs['Metallic'].default_value=0;bs.inputs['Roughness'].default_value=.97 if old.name=='White' else .94;bs.inputs['Emission Strength'].default_value=0;m.diffuse_color=(*linear(rgb),1);materials.append(m)
mesh.data.materials.clear()
for m in materials:mesh.data.materials.append(m)
for p,index in zip(mesh.data.polygons,face_material_indices):p.material_index=index
dead_curves=[]
for a in actions:
 for layer in a.layers:
  for strip in layer.strips:
   for bag in strip.channelbags:
    for curve in list(bag.fcurves):
     target=re.search(r'pose\.bones\["([^"]+)"\]',curve.data_path)
     if target and target.group(1) not in arm.pose.bones:
      dead_curves.append({'action':a.name,'path':curve.data_path,'component':curve.array_index,'keyframes':len(curve.keyframe_points)})
      bag.fcurves.remove(curve)
for t in list(tracks):tracks.remove(t)
arm.animation_data.action=None
for a in actions:
 a.use_fake_user=True;t=arm.animation_data.nla_tracks.new();t.name=a.name;s=t.strips.new(a.name,int(a.frame_range[0]),a);s.action_frame_start=a.frame_range[0];s.action_frame_end=a.frame_range[1];t.mute=True
arm.data.pose_position='REST';scene.frame_set(0);bpy.context.view_layer.update()
base=mesh.data.copy();ratios=[1,.70,.40];receipts=[]
for lod,ratio in enumerate(ratios):
 mesh.data=base.copy();mesh.name=f'blueprint_cc0_sheep_lod{lod}'
 if ratio<1:
  bpy.ops.object.select_all(action='DESELECT');mesh.select_set(True);bpy.context.view_layer.objects.active=mesh
  d=mesh.modifiers.new('bounded source LOD collapse','DECIMATE');d.ratio=ratio;d.use_collapse_triangulate=True;mesh.modifiers.move(len(mesh.modifiers)-1,0);bpy.ops.object.modifier_apply(modifier=d.name)
 mesh.data.calc_loop_triangles();tris=len(mesh.data.loop_triangles)
 arm.data.pose_position='POSE';arm.animation_data.action=None;scene.frame_set(0)
 path=OUT/'source'/f'blueprint_cc0_sheep_lod{lod}.glb'
 receipt=export_glb([carrier,arm,mesh],path,'character_skinned',receipt_path=OUT/'source'/f'lod{lod}-export-receipt.json',asset_id=f'blueprint_cc0_sheep_lod{lod}',budget_class=f'hero_lod{lod}',vertex_color='NONE',tangents=False,single_sided_materials=[m.name for m in materials],inputs=[SOURCE],copyright_text='Farm Animals Pack by Quaternius2018, CC0 1.0; OpenGameArt author mirror. Xexoria metre/material/LOD derivative.',notes='No sourcegeometry invention;612tri licensed sheep,24bone native rig/IK baked clips; matte nonmetal; sourceimmutable; root owns6instance placement/native admission.')
 receipts.append({'lod':lod,'triangles':tris,'status':receipt['status'],'file':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':sha(path)})
 arm.data.pose_position='REST'
mesh.data=base.copy();mesh.name='blueprint_cc0_sheep_normalized_source';arm.data.pose_position='POSE';arm.animation_data.action=bpy.data.actions['Idle'];arm.animation_data.action_slot=bpy.data.actions['Idle'].slots[0];scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'source'/'sheep_metre_candidate_v1.blend'))
if sha(SOURCE)!=SOURCE_SHA:raise RuntimeError('Immutable source modified')
report={'schema':'xexoria.cc0-sheep-build/1','sourceSha256':SOURCE_SHA,'source_immutable':True,'blender':bpy.app.version_string,'fps':scene.render.fps,'source_rest_bounds':{'min':mn,'max':mx},'metre_scale':scale,'centre_foot_offset':centre,'mesh_basis_pose_max_error_m':delta,'normalized_clip_pose_max_error_m':norm_delta,'clips':clip_ranges,'bones':len(arm.data.bones),'rig_and_valid_clip_motion_original':True,'removed_dead_target_curves':dead_curves,'outputs':receipts,'native_admission':'UNVERIFIED','six_instance_contract':'Share mesh/material/clip data; clone24joint skeleton peranimal if independently phased. Never bake skinned runtime into static dressing without declaring lost animation. Root owns metre anchors/no new AI movement.'}
(E/'build-receipt.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
