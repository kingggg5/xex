"""Append H01 presentation clips to the immutable fitted rig; export lean, map-free candidates.

Existing five actions and all geometry/weights/rest bones remain intact. No game balance or source writes.
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import argparse
import hashlib
import json
import math
import shutil
import gc
import sys
from pathlib import Path
sys.dont_write_bytecode = True
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'assets/blender/heroes/hero02'))
import h02_animlib as A
import h02_xs1 as X
P = argparse.ArgumentParser()
P.add_argument('--out', required=True, type=Path)
P.add_argument('--evidence', required=True, type=Path)
args = P.parse_args(sys.argv[sys.argv.index('--')+1:])
SOURCE = Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-hero01-rig-r01'))
BLEND = SOURCE / 'hero01_swordsman_r01.blend'
EXPECTED_BLEND = '3532c3d7d629ef7a9a9f5a4375d23b70e2ab797e0776d70846c09e723b665a84'
UAL = ROOT / 'assets/models/heroes/hero02/source/third-party/ual1-standard-2025-06-10'
JEV = Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-heroes-continuation-r02/jev-intake-receipt.json'))
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, value):
    Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def resource_gate():
    if shutil.disk_usage(args.out.parent).free < 100_000_000:
        raise RuntimeError('FreeC below100MB; stop without source mutation')
assert sha(BLEND) == EXPECTED_BLEND, 'Immutable fitted blend digest mismatch'
assert sha(UAL/'AnimationLibrary_Godot_Standard.gltf') == '0ff075c7ad6855c5c2c37a171592ee8f0d6ab2f58259e2be77a9b63dd8027765'
args.out.mkdir(parents=True,exist_ok=True)
args.evidence.parent.mkdir(parents=True,exist_ok=True)
resource_gate()
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scn=bpy.context.scene
scn.render.fps=30
scn.render.fps_base=1
arm=bpy.data.objects['hero01_XS1']
lods={i:bpy.data.objects[f'hero01_swordsman_lod{i}'] for i in range(3)}
for mesh in lods.values():mesh.data.materials.clear()
for material in list(bpy.data.materials):bpy.data.materials.remove(material,do_unlink=True)
for image in list(bpy.data.images):bpy.data.images.remove(image,do_unlink=True)
gc.collect()
JOINTS=list(X.CORE)+['tabard.F.01','tabard.F.02','tabard.B.01','tabard.B.02']
assert len(arm.data.bones)==47 and set(arm.data.bones.keys())==set(JOINTS)
legacy_names=['base.idle','base.walk','base.run','blade_1h.attack_1','blade_1h.attack_2']
def action_hash(action):
    data=[]
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    data.append((fc.data_path,fc.array_index,[(tuple(k.co),k.interpolation) for k in fc.keyframe_points]))
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
legacy_hashes={n:action_hash(bpy.data.actions[n]) for n in legacy_names}
legacy_ranges={n:list(bpy.data.actions[n].frame_range) for n in legacy_names}
rest_bones={b.name:{'parent':b.parent.name if b.parent else None,'matrix':list(sum([list(row) for row in b.matrix_local],[]))} for b in arm.data.bones}
sk=A.Skeleton(arm)

print('H01_CLIPS_STAGE import_verified_UAL',flush=True)
before=set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(UAL/'AnimationLibrary_Godot_Standard.gltf'),bone_heuristic='BLENDER',guess_original_bind_pose=True)
ual_objects=[o for o in bpy.data.objects if o not in before]
ual_arm=next(o for o in ual_objects if o.type=='ARMATURE')
def ual_action(name):
    return next(a for a in bpy.data.actions if a.name==name or a.name.split('|')[-1]==name)
ual_names=[b.name for b in ual_arm.data.bones]
idle=ual_action('Idle_Loop')
reference=A.SourceClip(ual_arm,idle,[float(idle.frame_range[0])],ual_names).frames[0]
hip_scale=sk.rest['thigh.L'].translation.z/(ual_arm.matrix_world@ual_arm.data.bones['DEF-thigh.L'].head_local).z
plan=json.loads((ROOT/'planning/assets/hero-skills.json').read_text(encoding='utf-8'))
skills=[s for s in plan['skills'] if s.get('hero')=='h01' and s.get('slot',0)>0]
assert len(skills)==6
clip_meta={n:{'preserved':True,'range_frames':legacy_ranges[n],'fps':30,'action_hash':legacy_hashes[n],
              'release_ms':100 if n.startswith('blade_1h') else None} for n in legacy_names}
new_frames={}

def matched_source(name,times,duration):
    action=ual_action(name)
    f0,f1=action.frame_range
    src_times=[float(f0+(f1-f0)*min(1,t/duration)) for t in times]
    source=A.SourceClip(ual_arm,action,src_times,ual_names)
    for bone in list(source.rest):
        if bone in reference:
            q,p=reference[bone]
            source.rest[bone]=(q.copy(),p.copy(),(q@Vector((0,1,0))).normalized())
    return A.retarget(sk,source,X.UAL_POSE,'DEF-hips',hip_scale,in_place=True,
                      delta_bones=tuple(X.UAL_POSE.values()))
def smooth(t):
    t=max(0,min(1,t));return t*t*(3-2*t)
def curve(t,keys):
    if t<=keys[0][0]:return keys[0][1]
    for (ta,a),(tb,b) in zip(keys,keys[1:]):
        if t<=tb:
            w=smooth((t-ta)/max(1e-6,tb-ta))
            if isinstance(a,(tuple,list,Vector)):return Vector(a).lerp(Vector(b),w)
            return a+(b-a)*w
    return keys[-1][1]
def grip(pose):
    for side in ('L','R'):
        pose[f'grip.01.{side}']=A.q_axis((1,0,0),30)
        pose[f'grip.02.{side}']=A.q_axis((1,0,0),35)
        pose[f'upper_arm_twist.{side}']=Quaternion()
        pose[f'forearm_twist.{side}']=Quaternion()
        pose[f'pauldron.{side}']=Quaternion()
def planted(pose,hips):
    hips.x=hips.y=0
    pose['hips']=Quaternion()
    for side in ('L','R'):
        foot=f'foot.{side}';target=sk.rest[foot].translation
        sk.ik2(pose,hips,f'thigh.{side}',f'shin.{side}',foot,target,Vector((target.x,-.6,.5)))
        sk.set_world(pose,hips,foot,sk.rest[foot].to_quaternion())
        toe=f'toe.{side}';sk.set_world(pose,hips,toe,sk.rest[toe].to_quaternion())
def hand_target(pose,hips,side,target):
    sk.ik2(pose,hips,f'upper_arm.{side}',f'forearm.{side}',f'hand.{side}',Vector(target),
           Vector((-.9 if side=='R' else .9,-.4,1.5)))
def sword_axis(pose,hips,direction,weight=1):
    name='socket_weapon_R';M=sk.fk(pose,hips);q=M[name].to_quaternion()
    delta=A.rot_between(q@Vector((0,1,0)),Vector(direction))
    sk.set_world(pose,hips,name,Quaternion().slerp(delta,weight)@q)
def write_timed(name,frames,times,events,loop=False):
    action=A.write_action(arm,name,frames,JOINTS,fps=30,loop=loop)
    # Preserve half-frame times exactly. No sampling-rate relabelling.
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for key,t in zip(fc.keyframe_points,times):key.co.x=t*30
                    fc.update()
    action.frame_start=0;action.frame_end=times[-1]*30
    action['xex_events']=json.dumps(events)
    action['xex_fps']=30
    action['xex_presentation_only']=True
    return action

restR=sk.rest['hand.R'].translation.copy();restL=sk.rest['hand.L'].translation.copy()
for row in skills:
    timing=row['timing'];name=timing['clip'];duration=timing['clip_frames']/30
    release=(timing.get('release_frame_exact',timing['release_frame']))/30
    events=[{**e,'frame_exact':e['t_ms']*.03} for e in timing['events']]
    times=sorted(set([i/60 for i in range(timing['clip_frames']*2+1)]+[release]+[e['t_ms']/1000 for e in events]))
    times=[t for t in times if t<=duration+1e-9]
    if name.endswith('skill_arc'):
        source_name='Sword_Attack';frames=matched_source(source_name,times,duration)
    elif name.endswith('skill_rush'):
        source_name='Sprint_Loop';frames=matched_source(source_name,times,duration)
    else:
        source_name='AUTHORED_FITTED_IK';frames=[({},Vector()) for _ in times]
    for (pose,hips),t in zip(frames,times):
        grip(pose)
        if name.endswith('skill_arc'):
            for bone,q in list(pose.items()):
                if bone.startswith(('shoulder','upper_arm','forearm','chest','upper_chest')):pose[bone]=Quaternion().slerp(q,.85)
            yaw=curve(t,[(0,0),(release*.65,-18),(release,22),(release+.10,27),(duration,0)])
            sk.rotate_world(pose,hips,'chest',(0,0,1),yaw)
            hips.z=-.03*math.sin(math.pi*min(1,t/duration));planted(pose,hips)
        elif name.endswith('skill_nova'):
            crouch=curve(t,[(0,0),(.15,-.09),(release,-.09),(.33,-.025),(duration,0)])
            hips.z=crouch;planted(pose,hips)
            sk.rotate_world(pose,hips,'chest',(1,0,0),curve(t,[(0,0),(.15,4),(release,8),(duration,0)]))
            right=curve(t,[(0,restR),(.12,(-.18,-.32,1.48)),(release,(-.14,-.40,1.03)),(.32,(-.14,-.40,1.03)),(duration,restR)])
            left=curve(t,[(0,restL),(.12,(.22,-.24,1.32)),(release,(.22,-.31,1.13)),(duration,restL)])
            hand_target(pose,hips,'R',right);hand_target(pose,hips,'L',left)
            sword_axis(pose,hips,(0,-.20,-1),smooth(t/.15)*(1-smooth((t-.33)/max(.01,duration-.33))))
        elif name.endswith('skill_ironfall'):
            hips.z=curve(t,[(0,0),(release*.6,-.045),(release,-.09),(duration,0)]);planted(pose,hips)
            right=curve(t,[(0,restR),(release*.65,(-.13,-.12,1.96)),(release*.90,(-.13,-.12,1.96)),(release,(-.10,-.55,1.04)),(release+.10,(-.10,-.55,1.04)),(duration,restR)])
            left=curve(t,[(0,restL),(release*.65,(.09,-.12,1.87)),(release*.90,(.09,-.12,1.87)),(release,(.10,-.52,1.03)),(duration,restL)])
            sk.rotate_world(pose,hips,'chest',(1,0,0),curve(t,[(0,0),(release*.8,-4),(release,9),(duration,0)]))
            hand_target(pose,hips,'R',right);hand_target(pose,hips,'L',left)
            sword_axis(pose,hips,curve(t,[(0,(0,0,1)),(release*.8,(0,.05,1)),(release,(0,-.75,-.65)),(duration,(0,0,1))]))
        elif name.endswith('skill_rush'):
            amount=curve(t,[(0,0),(release,1),(.53,1),(duration,0)])
            for bone,q in list(pose.items()):pose[bone]=Quaternion().slerp(q,amount)
            hips.z*=amount;hips.x=hips.y=0
            sk.rotate_world(pose,hips,'chest',(1,0,0),14*amount)
            hand_target(pose,hips,'L',restL.lerp(Vector((.22,-.38,1.46)),amount))
            hand_target(pose,hips,'R',restR.lerp(Vector((-.45,-.10,1.30)),amount))
            for side in ('L','R'):
                foot=f'foot.{side}';M=sk.fk(pose,hips);target=M[foot].translation
                target.z=max(target.z,sk.rest[foot].translation.z)
                sk.ik2(pose,hips,f'thigh.{side}',f'shin.{side}',foot,target,Vector((target.x,-.6,.5)))
                sk.set_world(pose,hips,foot,sk.rest[foot].to_quaternion())
        elif name.endswith('skill_ward'):
            hips.z=curve(t,[(0,0),(release,-.055),(.45,-.055),(duration,0)]);planted(pose,hips)
            right=curve(t,[(0,restR),(.18,(-.13,-.22,1.52)),(release,(-.12,-.29,1.24)),(.48,(-.12,-.29,1.24)),(duration,restR)])
            left=curve(t,[(0,restL),(.18,(.12,-.22,1.45)),(release,(.09,-.29,1.23)),(.48,(.09,-.29,1.23)),(duration,restL)])
            hand_target(pose,hips,'R',right);hand_target(pose,hips,'L',left)
            sword_axis(pose,hips,(0,0,-1),smooth(t/release)*(1-smooth((t-.5)/max(.01,duration-.5))))
        elif name.endswith('skill_stormfall'):
            height=curve(t,[(0,0),(.30,-.12),(.47,.24),(release,.02),(.70,-.12),(.93,-.04),(duration,0)])
            hips.z=height
            if t<.30 or t>=.70:planted(pose,hips)
            else:
                for side in ('L','R'):
                    pose[f'thigh.{side}']=A.q_axis((1,0,0),-18)
                    pose[f'shin.{side}']=A.q_axis((1,0,0),25)
            right=curve(t,[(0,restR),(.25,(-.18,-.05,1.88)),(.50,(-.12,-.04,1.98)),(release,(-.10,-.54,1.08)),(.80,(-.10,-.54,1.08)),(duration,restR)])
            left=curve(t,[(0,restL),(.25,(.10,-.08,1.81)),(.50,(.09,-.04,1.89)),(release,(.10,-.50,1.05)),(duration,restL)])
            sk.rotate_world(pose,hips,'chest',(1,0,0),curve(t,[(0,0),(.30,-5),(.50,-5),(release,13),(.85,8),(duration,0)]))
            hand_target(pose,hips,'R',right+Vector((0,0,max(0,height))));hand_target(pose,hips,'L',left+Vector((0,0,max(0,height))))
            sword_axis(pose,hips,curve(t,[(0,(0,0,1)),(.50,(0,.1,1)),(release,(0,-.75,-.65)),(duration,(0,0,1))]))
    write_timed(name,frames,times,events)
    new_frames[name]=(frames,times)
    clip_meta[name]={'ability':row['id'],'source':source_name,'fps':30,'canonical_frames':timing['clip_frames'],
                     'duration_s':duration,'declared_clip_ms':timing['clip_ms'],'release_s':release,'release_frame_exact':release*30,
                     'events':events,'timing_note':'Canonical30fps frame times; rounded design ms differ by<=0.333ms except explicit250ms half-frame.',
                     'choreography':row['summary'],'gameplay_activation':False}

for name,source_name,duration in [('base.hit_light','Hit_Chest',.3),('base.dodge','AUTHORED_EVADE',.4),('base.death','Death01',2.4)]:
    times=[i/60 for i in range(int(round(duration*60))+1)]
    frames=matched_source(source_name,times,duration) if source_name!='AUTHORED_EVADE' else [({},Vector()) for _ in times]
    for (pose,hips),t in zip(frames,times):
        if name=='base.hit_light':
            for bone,q in list(pose.items()):
                pose[bone]=Quaternion().slerp(q,.55)
            hips.z=0;planted(pose,hips)
        elif name=='base.dodge':
            amount=curve(t,[(0,0),(.10,1),(.24,1),(duration,0)])
            hips.z=-.13*amount;planted(pose,hips)
            sk.rotate_world(pose,hips,'chest',(0,1,0),18*amount)
            sk.rotate_world(pose,hips,'head',(0,1,0),-8*amount)
            hand_target(pose,hips,'L',restL.lerp(Vector((.20,-.26,1.40)),amount))
            hand_target(pose,hips,'R',restR.lerp(Vector((-.43,-.16,1.27)),amount))
        else:
            # Full per-hero retarget; ground support is measured below, not a copied unrelated rest key.
            hips.x=hips.y=0
        grip(pose)
    events=[{'id':'whoosh','t_ms':0,'frame_exact':0},{'id':'foot_l','t_ms':233,'frame_exact':6.99}] if name=='base.dodge' else []
    write_timed(name,frames,times,events)
    new_frames[name]=(frames,times)
    clip_meta[name]={'source':source_name,'licence':'CC0-1.0' if source_name!='AUTHORED_EVADE' else 'Original authored animation',
                     'fps':30,'duration_s':duration,'events':events,'gameplay_activation':False}

for obj in ual_objects:bpy.data.objects.remove(obj,do_unlink=True)
for action in list(bpy.data.actions):
    if action.name not in clip_meta:bpy.data.actions.remove(action)
assert len(clip_meta)==14
assert all(action_hash(bpy.data.actions[n])==legacy_hashes[n] for n in legacy_names)

print('H01_CLIPS_STAGE grounded_pose_audit',flush=True)
obj=lods[0];obj.hide_set(False)
dg=bpy.context.evaluated_depsgraph_get()
edges=np.array([tuple(e.vertices) for e in obj.data.edges],dtype=np.int32)
bind=np.array([tuple(v.co) for v in obj.data.vertices]);lengths=np.linalg.norm(bind[edges[:,0]]-bind[edges[:,1]],axis=1);valid=lengths>.002
def evaluate_points(action,time):
    arm.animation_data.action=action;arm.animation_data.action_slot=action.slots[0]
    frame=time*30;scn.frame_set(int(math.floor(frame)),subframe=frame-math.floor(frame));bpy.context.view_layer.update()
    ev=obj.evaluated_get(dg);me=ev.to_mesh();p=np.array([tuple(ev.matrix_world@v.co) for v in me.vertices]);ev.to_mesh_clear();return p
audits={}
for name,(frames,times) in new_frames.items():
    action=bpy.data.actions[name]
    lows=[]
    for time in times:lows.append(float(evaluate_points(action,time)[:,2].min()))
    if name=='base.death':
        # Contact constraint keeps the collapsing body on the ground, root XY remains unchanged.
        for i,((pose,hips),low) in enumerate(zip(frames,lows)):
            if i==0:continue
            M=sk.fk(pose,hips);desired=M['hips'].translation+Vector((0,0,-low))
            frames[i]=(pose,sk.hips_loc_for_world(M,desired))
        action=write_timed(name,frames,times,clip_meta[name]['events'])
        clip_meta[name]['grounding']='Per-sample body-support correction; physical settling and collision need native review.'
    elif min(lows)<0 and -min(lows)<=.035:
        offset=-min(lows)
        for i,(pose,hips) in enumerate(frames):
            M=sk.fk(pose,hips);frames[i]=(pose,sk.hips_loc_for_world(M,M['hips'].translation+Vector((0,0,offset))))
        action=write_timed(name,frames,times,clip_meta[name]['events'])
        clip_meta[name]['floor_correction_m']=offset
    samples=[]
    for time in sorted(set([times[0],times[-1]]+[times[int(i)] for i in np.linspace(0,len(times)-1,13)])):
        p=evaluate_points(action,time);ratio=np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)[valid]/lengths[valid]
        root=arm.matrix_world@arm.pose.bones['root'].matrix.translation
        samples.append({'time_s':time,'min_z_m':float(p[:,2].min()),'max_z_m':float(p[:,2].max()),
                        'stretch_p99':float(np.quantile(ratio,.99)),'edges_over_2x':int((ratio>2).sum()),'root_xyz':list(root)})
    audits[name]={'before_floor_min_m':min(lows),'samples':samples,'visual':'UNVERIFIED'}
    clip_meta[name]['sampled_deformation']=audits[name]

arm.animation_data.action=None
for pb in arm.pose.bones:pb.matrix_basis=Matrix.Identity(4)
scn.frame_set(0);bpy.context.view_layer.update()
markers=[o for o in scn.objects if o.type=='EMPTY' and o.parent is arm]
outputs=[]
for lod,mesh in lods.items():
    resource_gate();mesh.hide_set(False)
    bpy.ops.object.select_all(action='DESELECT')
    for selected in [mesh,arm]+(markers if lod==0 else []):selected.select_set(True)
    bpy.context.view_layer.objects.active=arm
    output=args.out/f'hero01_swordsman_lod{lod}.geometry-clips.glb'
    bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',use_selection=True,export_materials='NONE',
     export_texcoords=True,export_normals=True,export_animations=lod==0,export_animation_mode='ACTIONS',
     export_frame_range=False,export_frame_step=1,export_force_sampling=False,export_skins=True,export_influence_nb=4,
     export_all_influences=False,export_reset_pose_bones=True,export_anim_slide_to_zero=True,export_cameras=False,export_lights=False,export_extras=True)
    mesh.data.calc_loop_triangles()
    outputs.append({'lod':lod,'path':str(output),'bytes':output.stat().st_size,'sha256':sha(output),'triangles':len(mesh.data.loop_triangles),'maps':0})
    mesh.hide_set(True)
assert all(action_hash(bpy.data.actions[n])==legacy_hashes[n] for n in legacy_names)
rig_blend=args.out/'hero01_animation_r02.rig-only.blend'
if shutil.disk_usage(args.out).free>150_000_000:
    for image in list(bpy.data.images):bpy.data.images.remove(image,do_unlink=True)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(rig_blend),compress=True)
assert sha(BLEND)==EXPECTED_BLEND
receipt={'schema':'xexoria.hero01-clips-continuation/1','status':'ANIMATION_CANDIDATE_NATIVE_REVIEW_REQUIRED',
 'source_blend':{'path':str(BLEND),'sha256':EXPECTED_BLEND,'unchanged':True},'planning_sha256':sha(ROOT/'planning/assets/hero-skills.json'),
 'source_rig':'r06 fitted XS1 core43 + tabard4; idle-reference UAL transfer','joints':JOINTS,'joint_rest_and_parent_signature':rest_bones,
 'legacy_actions_preserved':legacy_hashes,'outputs':outputs,'clips':clip_meta,'deformation':audits,
 'rig_only_blend':{'path':str(rig_blend),'bytes':rig_blend.stat().st_size,'sha256':sha(rig_blend)} if rig_blend.exists() else None,
 'shared_maps':'Reuse originalr01/r02 pack material/maps; map-free GLBs intentionally carry no material/image copies.',
 'jev':{'status':'USED_VERIFIED','receipt':str(JEV),'sha256':sha(JEV)},
 'remaining_defects':['Actual sword hilt/tip grip/contact is unverified until root weapon integration.',
 'Root/player movement, gait speed, class damage and balance are not activated here.',
 'Plate/cloth stretching and death support need native visual review; numeric checks do not approve art.',
 'Stormfall authored leap is visual hips motion with root motion off; server remains movement authority.']}
save(args.evidence,receipt)
print('H01_CLIPS_OUTPUT',json.dumps({'outputs':outputs,'clips':list(clip_meta),'source_unchanged':True}),flush=True)
