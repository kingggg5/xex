"""Fit Blender's bundled Rigify to the approved Tripo Minotaur; no provider calls.

Source stays immutable. Rigify generates IK/FK, Blender heat weights establish
the body skin, and reviewed part masks keep the staff and hooves rigid.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Quaternion, Vector

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
parser.add_argument('--anatomy', required=True, type=Path)
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
args.out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(args.source.resolve()))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
assert len(meshes) == 1, 'Part policy requires one inspected source mesh'
body = meshes[0]
body.name = 'Minotaur_BovineShaman'
world = body.matrix_world.copy()
p = np.array([tuple(world @ v.co) for v in body.data.vertices])
lo, hi = p.min(axis=0), p.max(axis=0)
center = np.array([(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]])
factor = 2.4/(hi[2]-lo[2])
p = (p-center)*factor
body.parent = None
body.matrix_world = Matrix.Identity(4)
for v,co in zip(body.data.vertices,p): v.co = co
body.data.update()
body.data.calc_loop_triangles()
source_triangles = len(body.data.loop_triangles)
anatomy=json.loads(args.anatomy.read_text(encoding='utf-8'))['meshes'][0]
for poly in body.data.polygons: poly.use_smooth = True
# Rough cloth/wood response; source supplies only base color, not PBR data maps.
for mat in body.data.materials:
    for n in mat.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            n.inputs['Metallic'].default_value = 0
            n.inputs['Roughness'].default_value = .73

bpy.ops.preferences.addon_enable(module='rigify')
bpy.ops.object.armature_basic_human_metarig_add()
meta = bpy.context.object
meta.name = 'Minotaur_Fitted_Metarig'
bpy.ops.object.mode_set(mode='EDIT')
eb = meta.data.edit_bones
for name in ('breast.L','breast.R','pelvis.L','pelvis.R'): eb.remove(eb[name])
# Coordinates are in metres, Blender Z-up; front is -Y.
cx=-.045*factor
spine = [(cx,.084,1.03),(cx,.084,1.25),(cx,.074,1.47),(cx,.072,1.66),
         (cx,.036,1.86),(cx,-.030,1.975),(cx,-.072,2.065),(cx,-.072,2.27)]
for i in range(7):
    name = 'spine' if i == 0 else f'spine.{i:03}'
    eb[name].head, eb[name].tail = spine[i], spine[i+1]
for side,s in [('L',1),('R',-1)]:
    shoulder = (.12*factor,.02*factor,.735*factor) if side=='L' else (-.20*factor,.02*factor,.735*factor)
    elbow = (.22*factor,.04*factor,.595*factor) if side=='L' else (-.277*factor,-.02*factor,.60*factor)
    wrist = (.235*factor,-.125*factor,.622*factor) if side=='L' else (-.285*factor,-.115*factor,.50*factor)
    handend = (.27*factor,-.16*factor,.62*factor) if side=='L' else (-.281*factor,-.13*factor,.445*factor)
    hx, kx, ax = (.04,.075,.08) if side=='L' else (-.13,-.15,-.155)
    points = {'shoulder':((cx+s*.12,.07,1.765),shoulder),
              'upper_arm':(shoulder,elbow),'forearm':(elbow,wrist),'hand':(wrist,handend),
              'thigh':((hx*factor,.035*factor,.43*factor),(kx*factor,.055*factor,.265*factor)),
              'shin':((kx*factor,.055*factor,.265*factor),(ax*factor,.025*factor,.085*factor)),
              'foot':((ax*factor,.025*factor,.085*factor),(ax*factor,-.115*factor,.04*factor)),
              'toe':((ax*factor,-.115*factor,.04*factor),(ax*factor,-.165*factor,.04*factor)),
              'heel.02':((ax*factor-.08,.16,.03),(ax*factor+.08,.16,.03))}
    for name,(a,b) in points.items(): eb[f'{name}.{side}'].head, eb[f'{name}.{side}'].tail = a,b
extras = []
for index in range(6):
    angle = index*math.tau/6
    x,y = .31*math.sin(angle), -.27*math.cos(angle)
    name = f'robe_{index:02}'
    b = eb.new(name)
    b.head,b.tail = (cx+x,.084+y,1.05),(cx+x*1.45,.084+y*1.45,.38)
    b.parent = eb['spine']
    extras.append(name)
b = eb.new('staff.L')
b.head,b.tail = (.27*factor,-.16*factor,.62*factor),(.27*factor,-.16*factor,.62*factor+.25)
b.parent = eb['hand.L']
extras.append('staff.L')
for name,a,bpt,parent in [('beard',(cx,-.34,1.95),(cx,-.39,1.62),'spine.006'),
                          ('beard_tip',(cx,-.39,1.62),(cx,-.37,1.40),'beard')]:
    b = eb.new(name); b.head,b.tail,b.parent = a,bpt,eb[parent]; extras.append(name)
bpy.ops.object.mode_set(mode='OBJECT')
for name in extras:
    meta.pose.bones[name].rigify_type = 'basic.super_copy'
    meta.pose.bones[name].rigify_parameters.make_deform = True
for name in ('upper_arm.L','upper_arm.R','thigh.L','thigh.R'):
    meta.pose.bones[name].rigify_parameters.segments = 1
bpy.context.view_layer.objects.active = meta
bpy.ops.pose.rigify_generate()
rig = bpy.context.object
rig.name = 'Minotaur_Rigify'
for side in ('L','R'):
    rig.pose.bones[f'upper_arm_parent.{side}']['IK_FK'] = 1.0
    rig.pose.bones[f'thigh_parent.{side}']['IK_Stretch'] = 0.0
    rig.pose.bones[f'upper_arm_parent.{side}']['IK_Stretch'] = 0.0
# Existing Blender heat weighting on a welded proxy; source UV seams stay intact.
proxy=body.copy();proxy.data=body.data.copy();proxy.name='WeightTransfer_Cage'
bpy.context.scene.collection.objects.link(proxy)
bpy.ops.object.select_all(action='DESELECT');proxy.select_set(True)
bpy.context.view_layer.objects.active=proxy
staff_index_set=set(anatomy['staff_rigid_vertex_indices'])
bm=bmesh.new();bm.from_mesh(proxy.data);bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.index in staff_index_set],context='VERTS')
bm.to_mesh(proxy.data);bm.free();proxy.data.update()
# Native voxel remesh closes intersecting generated surfaces for bone heat.
# It is a disposable weighting surface only; final source mesh/UVs are unchanged.
proxy.data.remesh_voxel_size=.025
bpy.ops.object.voxel_remesh()
print('CAGE_VERTICES',len(proxy.data.vertices))
smooth=proxy.modifiers.new('WeightCageSmooth','SMOOTH');smooth.factor=1.;smooth.iterations=3
bpy.ops.object.modifier_apply(modifier=smooth.name)
extra_bones=[rig.data.bones['DEF-'+n] for n in extras]
for b in extra_bones:b.use_deform=False
bpy.ops.object.select_all(action='DESELECT')
proxy.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
heat_weighted=sum(bool(v.groups) for v in proxy.data.vertices)
assert heat_weighted>.8*len(proxy.data.vertices), f'Heat cage coverage too low: {heat_weighted}/{len(proxy.data.vertices)}'
for b in extra_bones:b.use_deform=True
bpy.ops.object.select_all(action='DESELECT');body.select_set(True)
bpy.context.view_layer.objects.active=body
for g in proxy.vertex_groups:body.vertex_groups.new(name=g.name)
transfer=body.modifiers.new('NativeWeightTransfer','DATA_TRANSFER');transfer.object=proxy
transfer.use_vert_data=True;transfer.data_types_verts={'VGROUP_WEIGHTS'}
transfer.vert_mapping='POLYINTERP_NEAREST';transfer.layers_vgroup_select_src='ALL';transfer.layers_vgroup_select_dst='NAME'
bpy.ops.object.modifier_apply(modifier=transfer.name)
bpy.data.objects.remove(proxy,do_unlink=True)
body.parent=rig
armod=body.modifiers.new('Minotaur_Skin','ARMATURE');armod.object=rig
armod.use_deform_preserve_volume = False  # Match glTF linear blend skinning.
def group(name):
    return body.vertex_groups.get(name) or body.vertex_groups.new(name=name)
def weights(index, values):
    for g in list(body.data.vertices[index].groups): body.vertex_groups[g.group].remove([index])
    values = sorted([(n,max(0,float(w))) for n,w in values.items() if w > 1e-7], key=lambda t:-t[1])[:4]
    total = sum(w for _,w in values)
    assert total>0
    for n,w in values: group(n).add([index],w/total,'REPLACE')

# Initial masks will be replaced with audited connected-part boundaries if needed.
staff_core=set(anatomy['staff_rigid_vertex_indices'])
hoof_exact={'L':set(anatomy['hoof_L_vertex_indices']),'R':set(anatomy['hoof_R_vertex_indices'])}
hand_exact={'L':set(anatomy['hand_L_grip_vertex_indices']),'R':set(anatomy['hand_R_free_vertex_indices'])}
components=anatomy['components']
staff_ids=[]; hoof_ids={'L':[],'R':[]}; robe_ids=[]
fallback_count=0
for i,(x,y,z) in enumerate(p):
    staff = i in staff_core
    if staff:
        weights(i,{'DEF-staff.L':1}); staff_ids.append(i)
    elif i in hand_exact['L'] or i in hand_exact['R']:
        side='L' if i in hand_exact['L'] else 'R'
        weights(i,{f'DEF-hand.{side}':1})
    elif z > 1.98:
        weights(i,{'DEF-spine.006':1})
    elif i in hoof_exact['L'] or i in hoof_exact['R']:
        side = 'L' if i in hoof_exact['L'] else 'R'
        weights(i,{f'DEF-foot.{side}':1}); hoof_ids[side].append(i)
    elif .32 <= z < 1.07 and abs(x-cx) < .60:
        angle = math.atan2((x-cx)/.31,-(y-.084)/.27) % math.tau
        sector = angle/math.tau*6
        a = int(math.floor(sector))%6; b=(a+1)%6; t=sector-math.floor(sector)
        blend = max(0,min(1,(1.07-z)/.24))
        weights(i,{f'DEF-robe_{a:02}':blend*(1-t), f'DEF-robe_{b:02}':blend*t,'DEF-spine':1-blend})
        robe_ids.append(i)
    elif 1.47 < z < 1.95 and abs(x-cx)<.19 and y < -.31:
        t=max(0,min(1,(1.72-z)/.22))
        weights(i,{'DEF-beard':1-t,'DEF-beard_tip':t})
    else:
        values={body.vertex_groups[g.group].name:g.weight for g in body.data.vertices[i].groups
                if rig.data.bones.get(body.vertex_groups[g.group].name) and rig.data.bones[body.vertex_groups[g.group].name].use_deform}
        if not values:
            fallback_count+=1
            bone = min((b for b in rig.data.bones if b.use_deform),key=lambda b:(Vector((x,y,z))-b.head_local).length)
            values={bone.name:1}
        weights(i,values)
for name,ids in [('QA_staff_rigid',staff_ids),('QA_robe',robe_ids),('QA_hoof.L',hoof_ids['L']),('QA_hoof.R',hoof_ids['R'])]:
    # QA metadata stays outside vertex groups so it cannot pollute exported weights.
    body[name]=ids
rig['asset_source_sha256']=hashlib.sha256(args.source.read_bytes()).hexdigest()
rig['motion_kind']='In-place authored clips; no mocap or simulated cloth'
rig['front_axis']='Blender -Y / glTF +Z'
meta.hide_render=True; meta.hide_set(True)
for obj in bpy.data.objects:
    if obj.name.startswith('WGT-'): obj.hide_render=True
scene=bpy.context.scene
scene.render.fps=30
scene.frame_start=0

def reset():
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
        pb.rotation_mode = 'QUATERNION'
def world_rot(name,rot):
    pb=rig.pose.bones[name]
    # Local delta matching a world-space axis at bind pose.
    basis=pb.bone.matrix_local.to_quaternion()
    q=Quaternion((1,0,0),rot[0]) @ Quaternion((0,1,0),rot[1]) @ Quaternion((0,0,1),rot[2])
    pb.rotation_quaternion = basis.inverted() @ q @ basis
def world_offset(name,offset):
    pb=rig.pose.bones[name]
    pb.location=pb.bone.matrix_local.to_3x3().inverted() @ Vector(offset)
def pulse(t,points):
    for (ta,a),(tb,b) in zip(points,points[1:]):
        if ta<=t<=tb:
            u=(t-ta)/(tb-ta); u=u*u*(3-2*u); return a+(b-a)*u
    return points[-1][1] if t>points[-1][0] else points[0][1]

clips={'Idle':(120,True),'Walk':(48,True),'Run':(32,True),'Talk':(90,True),
       'StaffCast':(75,False),'StaffStrike':(51,False),'HitReact':(24,False),'Death':(90,False)}
actions=[]
for name,(last,loop) in clips.items():
    rig.animation_data_create(); rig.animation_data.action=None
    reset()
    action=bpy.data.actions.new(name); rig.animation_data.action=action
    for frame in range(last+1):
        reset(); t=frame/last; cyc=math.tau*t
        breath=math.sin(cyc)
        world_rot('chest',(.012*breath,0,.009*breath))
        world_rot('head',(.014*breath,0,.018*breath))
        world_rot('beard',(.02*math.sin(cyc-.4),0,0))
        world_rot('beard_tip',(.025*math.sin(cyc-.7),0,0))
        if name in ('Walk','Run'):
            run=name=='Run'; stride=.24 if run else .17; lift=.15 if run else .09
            world_offset('torso',(0,0,.012 if not run else .028))
            world_rot('chest',(.055 if run else .012,0,.025*math.sin(cyc)))
            for side,phase in [('L',0),('R',math.pi)]:
                a=(cyc+phase)%math.tau
                # Contact half: flat hooves travel backward relative to character.
                if a<math.pi:
                    dy=-stride+2*stride*a/math.pi; dz=0
                else:
                    u=(a-math.pi)/math.pi
                    dy=stride*math.cos(math.pi*u); dz=lift*math.sin(math.pi*u)**2
                world_offset(f'foot_ik.{side}',(0,dy,dz))
                world_rot(f'upper_arm_fk.{side}',(.065*math.sin(a),0,0))
            for k in range(6):
                world_rot(f'robe_{k:02}',(.045*math.sin(cyc-k*.6),.018*math.sin(cyc),0))
            # Lifting the staff prevents its source-ground contact from dragging.
            world_rot('upper_arm_fk.L',(-.10+.028*math.sin(cyc),0,0))
            world_rot('forearm_fk.L',(-.04,0,0))
        elif name=='Talk':
            gesture=.12*math.sin(cyc)
            world_rot('upper_arm_fk.R',(-gesture,0,-.10*math.sin(cyc)))
            world_rot('forearm_fk.R',(-.14*(1-math.cos(cyc)),0,0))
            world_rot('head',(.04*math.sin(cyc),0,.075*math.sin(cyc)))
        elif name=='StaffCast':
            g=pulse(t,[(0,0),(.25,1),(.65,1),(1,0)])
            world_rot('upper_arm_fk.R',(-.40*g,0,-.32*g))
            world_rot('forearm_fk.R',(-.62*g,0,0))
            world_rot('upper_arm_fk.L',(-.18*g,0,.09*g))
            world_rot('head',(-.08*g,0,0))
            world_rot('chest',(-.035*g,0,0))
        elif name=='StaffStrike':
            g=pulse(t,[(0,0),(.32,-1),(.53,1),(.68,.65),(1,0)])
            raise_staff=pulse(t,[(0,0),(.22,1),(.6,1),(1,0)])
            world_rot('upper_arm_fk.L',(-.20*raise_staff,0,-.38*g))
            world_rot('forearm_fk.L',(-.12*raise_staff,0,-.08*g))
            world_rot('chest',(.035*g,0,-.16*g))
            world_rot('head',(.025,0,-.08*g))
            world_rot('upper_arm_fk.R',(-.18*raise_staff,0,-.08*g))
        elif name=='HitReact':
            g=pulse(t,[(0,0),(.25,1),(1,0)])
            world_rot('chest',(-.16*g,0,.10*g))
            world_rot('head',(-.12*g,0,-.06*g))
            world_rot('upper_arm_fk.L',(-.08*g,0,0))
            world_offset('torso',(0,.035*g,0))
        elif name=='Death':
            g=pulse(t,[(0,0),(.2,.15),(.70,1),(1,1)])
            # Entire skeleton falls sideways; preserved height keeps horns above floor.
            angle=-1.50*g
            world_rot('root',(.08*g,angle,0))
            world_offset('root',(.30*g,0,.03*g))
            world_rot('upper_arm_fk.R',(.18*g,-.65*g,.18*g))
            world_rot('upper_arm_fk.L',(-.12*g,0,.13*g))
            world_rot('head',(.04*g,0,.06*g))
            # Keep the whole skinned surface above the floor through the fall.
            bpy.context.view_layer.update()
            ev=body.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
            floor=min(v.co.z for v in m.vertices);ev.to_mesh_clear()
            if floor<0:
                world_offset('root',(.30*g,0,.03*g-floor+.001))
            # Release the rigid staff beside the fallen body, instead of holding
            # it suspended above the corpse. This is authored motion, not physics.
            release=pulse(t,[(0,0),(.32,0),(.76,1),(1,1)])
            if release>0:
                bpy.context.view_layer.update()
                pb=rig.pose.bones['staff.L'];held=pb.matrix.copy()
                rest_matrix=pb.bone.matrix_local
                rotation=Quaternion((0,1,0),-math.pi/2)
                rel=[rotation @ (Vector(tuple(p[i]))-rest_matrix.translation) for i in staff_ids]
                target_z=-min(v.z for v in rel)+.015
                target=Vector((-.8,-.78,target_z))
                loc=held.translation.lerp(target,release)
                orient=held.to_quaternion().slerp(rotation @ rest_matrix.to_quaternion(),release)
                pb.matrix=Matrix.LocRotScale(loc,orient,Vector((1,1,1)))
        for pb in rig.pose.bones:
            if not pb.name.startswith(('ORG-','MCH-','DEF-','VIS_')):
                pb.keyframe_insert('location',frame=frame,group=pb.name)
                pb.keyframe_insert('rotation_quaternion',frame=frame,group=pb.name)
                pb.keyframe_insert('scale',frame=frame,group=pb.name)
    action.use_fake_user=True; actions.append(action)
    action['loop']=loop; action['fps']=30
rig.animation_data.action=None
reset(); scene.frame_end=120; scene.frame_set(0)
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str((args.out/'minotaur_rig.blend').resolve()))
record={'source':str(args.source.resolve()),'source_sha256':rig['asset_source_sha256'],
        'blender':bpy.app.version_string,'rig_engine':'bundled Rigify basic_human',
        'height_m':2.4,'source_triangles':source_triangles,'vertices':len(p),
        'bones':len(rig.data.bones),'deform_bones':sum(b.use_deform for b in rig.data.bones),
        'heat_cage_weighted_vertices':heat_weighted,'nearest_bone_fallback_vertices':fallback_count,
        'staff_mask_vertices':len(staff_ids),'robe_mask_vertices':len(robe_ids),
        'hoof_mask_vertices':{s:len(v) for s,v in hoof_ids.items()},
        'actions':[{'name':n,'frames':l+1,'seconds':l/30,'loop':loop} for n,(l,loop) in clips.items()],
        'limitations':['No facial or individual finger rig','Authored secondary motion, not cloth simulation',
                      'Source has base-color only; no normal or metallic-roughness maps',
                      'Candidate requires frame-by-frame and imported GLB review']}
(args.out/'rig-build.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('MINOTAUR_BUILD '+json.dumps(record))
