"""Local Blender motion checks and deterministic neutral camera renders."""
import argparse,json,math,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector,Matrix
p=argparse.ArgumentParser();p.add_argument('--blend',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--render',action='store_true');p.add_argument('--shots',default='')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.blend.resolve()))
rig=bpy.data.objects['Minotaur_Rigify'];body=bpy.data.objects['Minotaur_BovineShaman'];scene=bpy.context.scene
rig.animation_data.use_nla=False
staff=list(body.get('QA_staff_rigid',[]));hoof={s:list(body.get('QA_hoof.'+s,[])) for s in ('L','R')}
rest=np.array([tuple(v.co) for v in body.data.vertices]);checks=[]
deform={b.name for b in rig.data.bones if b.use_deform}
weights={'unweighted':0,'max_influences':0,'max_sum_error':0,'groups_used':{}}
for v in body.data.vertices:
    groups=[g for g in v.groups if body.vertex_groups[g.group].name in deform and g.weight>1e-7]
    weights['unweighted']+=len(groups)==0;weights['max_influences']=max(weights['max_influences'],len(groups))
    weights['max_sum_error']=max(weights['max_sum_error'],abs(sum(g.weight for g in groups)-1))
    for g in groups:
        name=body.vertex_groups[g.group].name;weights['groups_used'][name]=weights['groups_used'].get(name,0)+1
def activate(action):
    rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
def sample(frame):
    scene.frame_set(frame);bpy.context.view_layer.update();ev=body.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh()
    points=np.array([tuple(body.matrix_world@v.co) for v in me.vertices]);ev.to_mesh_clear();return points
for action in bpy.data.actions:
    activate(action);first,last=map(int,action.frame_range);lows=[];staff_error=0;finite=True;poses=[]
    ids=staff[::max(1,len(staff)//32)]
    reference=np.linalg.norm(rest[ids][:,None]-rest[ids][None,:],axis=2)
    for frame in range(first,last+1):
        pts=sample(frame);finite &= bool(np.isfinite(pts).all());lows.append(float(pts[:,2].min()))
        dist=np.linalg.norm(pts[ids][:,None]-pts[ids][None,:],axis=2)
        staff_error=max(staff_error,float(np.abs(dist-reference).max()))
        if frame in (first,(first+last)//2,last):poses.append(pts)
    start,end=sample(first),sample(last)
    checks.append({'clip':action.name,'frames':last-first+1,'finite':finite,
                   'min_surface_z':min(lows),'max_staff_distance_error_m':staff_error,
                   'loop':bool(action.get('loop',False)),'loop_endpoint_delta_m':float(np.abs(start-end).max()),
                   'max_vertex_motion_m':float(np.abs(poses[0]-poses[1]).max())})
record={'blender':bpy.app.version_string,'weights':weights,'clips':checks,'limits':'Local linear skin/vertex/floor check, not facial, self-collision, GPU, or mocap quality certification.'}
(a.out/'motion-check.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('MOTION_CHECK',json.dumps(record))
if not a.render:sys.exit(0)
scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True
scene.render.resolution_x=720;scene.render.resolution_y=860;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.world=bpy.data.worlds.new('ReviewWorld');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.16,.18,.22,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.65
scene.view_settings.view_transform='AgX'
for name,loc,power,size in [('Key',(-3,-4,5),650,4),('Fill',(4,-1,3),400,3),('Rim',(0,3,4),500,3)]:
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
    ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob);ob.location=loc;ob.rotation_euler=(Vector((0,0,1.1))-ob.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=100,location=(0,0,-.007));ground=bpy.context.object;ground.name='ReviewGround'
mat=bpy.data.materials.new('Ground');mat.diffuse_color=(.12,.14,.18,1);ground.data.materials.append(mat)
cd=bpy.data.cameras.new('ReviewCamera');cd.type='ORTHO';cd.ortho_scale=3.1
cam=bpy.data.objects.new('ReviewCamera',cd);scene.collection.objects.link(cam);scene.camera=cam
shots=[('Idle',0,'front',(0,-7,1.40),(0,0,1.2),3.1),('Idle',0,'side',(7,0,1.4),(0,0,1.2),3.1),
       ('Idle',0,'close',(.7,-4,2.4),(-.1,-.10,1.9),1.45),('Walk',12,'player',(3,-5,3.6),(0,0,1.15),3.4),
       ('Walk',36,'stride',(0,-7,1.4),(0,0,1.2),3.1),('StaffCast',36,'cast',(3,-5,2.1),(0,0,1.2),3.1),
       ('StaffStrike',27,'strike',(2,-5,2.0),(0,0,1.2),3.5),('Death',90,'death',(3,-5,3),(0,0,1.0),3.7),
       ('Death',45,'death-mid',(3,-5,3),(0,0,1.0),3.7)]
for clip,frame,label,loc,target,scale in shots:
    if a.shots and label not in a.shots.split(','):continue
    activate(bpy.data.actions[clip]);scene.frame_set(frame);cd.ortho_scale=scale
    if label.startswith('death'):
        points=sample(frame);center=(points.min(axis=0)+points.max(axis=0))/2
        target=tuple(center);loc=tuple(center+np.array([3,-5,3]))
        cd.ortho_scale=max(3.3,float((points.max(axis=0)-points.min(axis=0)).max())*1.3)
    cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str((a.out/f'{label}.png').resolve());bpy.ops.render.render(write_still=True)
print('REVIEW_RENDER_DONE')
