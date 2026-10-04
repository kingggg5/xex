"""Approved guardian form candidate. No renders, texture bakes or canonical writes.

Uses only MakeHuman's pinned CC0 graphical data; no MakeHuman program code.
Blender-native skin weighting poses the adult anatomy before static baking.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix, Quaternion

P = argparse.ArgumentParser()
P.add_argument('--root', required=True, type=Path)
A = P.parse_args(sys.argv[sys.argv.index('--')+1:])
ROOT = A.root.resolve()
OUT = ROOT/'assets/models/reference-city/r5/art-candidates/fountain-guardian-v1'
SOURCE = OUT/'source'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
SCENE = bpy.context.scene
SCENE.unit_settings.system = 'METRIC'
SCENE.unit_settings.scale_length = 1
COL = bpy.data.collections.new('Guardian_v1_editable_form')
SCENE.collection.children.link(COL)
PARTS = []
WINDING_REPAIRS = []
UV_CAP_REPAIRS = []
PI = math.pi


def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_material(name, color, metallic=0, roughness=.55):
    # Placeholder slots only. Claude owns authored texture/material finishing.
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metallic
    p.inputs['Roughness'].default_value=roughness
    return m


MARBLE=make_material('marble_statue',(.72,.70,.65),0,.6)
GOLD=make_material('metal_gold',(.56,.35,.12),.75,.32)
BLUE=make_material('magic_blue',(.06,.33,.68),.05,.28)


def mesh_object(name, verts, faces, uv, material=MARBLE):
    mesh=bpy.data.meshes.new(name+'-geometry')
    mesh.from_pydata(verts,[],faces);mesh.update()
    bm=bmesh.new();bm.from_mesh(mesh)
    if bm.faces and all(edge.is_manifold for edge in bm.edges) and bm.calc_volume(signed=True)<-1e-9:
        bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(mesh)
        WINDING_REPAIRS.append(name)
    bm.free()
    if not mesh.uv_layers:mesh.uv_layers.new(name='UVMap')
    layer=mesh.uv_layers.active
    for polygon in mesh.polygons:
        polygon.use_smooth=True
        for loop_index in polygon.loop_indices:
            layer.data[loop_index].uv=uv[mesh.loops[loop_index].vertex_index]
    ob=bpy.data.objects.new(name,mesh);COL.objects.link(ob)
    mesh.materials.append(material);PARTS.append(ob)
    return ob


def apply_modifier(ob, modifier):
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True)
    bpy.context.view_layer.objects.active=ob
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def repair_flat_uv_caps(ob):
    """Planar charts for closed tips/solidify edges with zero-area inherited UVs."""
    uv=ob.data.uv_layers.active
    if not uv:return
    repaired=0
    for polygon in ob.data.polygons:
        loops=list(polygon.loop_indices)
        points=[uv.data[i].uv.copy() for i in loops]
        area=abs(sum(a.x*b.y-b.x*a.y for a,b in zip(points,points[1:]+points[:1])))*.5
        if area>1e-12 or polygon.area<1e-10:continue
        v=[ob.data.vertices[ob.data.loops[i].vertex_index].co.copy() for i in loops]
        tangent=(v[1]-v[0]).normalized();bitangent=polygon.normal.cross(tangent).normalized()
        coords=[((p-v[0]).dot(tangent),(p-v[0]).dot(bitangent)) for p in v]
        lo=[min(p[a] for p in coords) for a in range(2)];hi=[max(p[a] for p in coords) for a in range(2)]
        if min(hi[a]-lo[a] for a in range(2))<1e-9:continue
        for i,p in zip(loops,coords):uv.data[i].uv=((p[0]-lo[0])/(hi[0]-lo[0]),(p[1]-lo[1])/(hi[1]-lo[1]))
        repaired+=1
    if repaired:UV_CAP_REPAIRS.append({'mesh':ob.name,'polygons':repaired})


def tube(name, points, radii, material=MARBLE, segments=8):
    v=[];f=[];uv=[];dist=[0.]
    points=[Vector(p) for p in points]
    for a,b in zip(points,points[1:]):dist.append(dist[-1]+(b-a).length)
    for j,center in enumerate(points):
        tangent=points[min(j+1,len(points)-1)]-points[max(0,j-1)]
        tangent.normalize();axis=Vector((0,1,0))
        if abs(tangent.dot(axis))>.95:axis=Vector((1,0,0))
        side=tangent.cross(axis).normalized();up=tangent.cross(side).normalized()
        radius=radii[j] if isinstance(radii,list) else radii
        rx,ry=radius if isinstance(radius,(tuple,list)) else (radius,radius)
        for k in range(segments):
            angle=2*PI*k/segments
            v.append(tuple(center+side*math.cos(angle)*rx+up*math.sin(angle)*ry))
            uv.append((k/segments,dist[j]/max(.01,dist[-1])))
    for j in range(len(points)-1):
        for k in range(segments):
            a=j*segments+k;b=j*segments+(k+1)%segments
            f.append((a,b,b+segments,a+segments))
    f.extend([tuple(range(segments-1,-1,-1)),tuple((len(points)-1)*segments+k for k in range(segments))])
    return mesh_object(name,v,f,uv,material)


def bezier(a,b,c,d,t):
    return (1-t)**3*Vector(a)+3*(1-t)**2*t*Vector(b)+3*(1-t)*t*t*Vector(c)+t**3*Vector(d)


def feather(name, controls, width, thickness, sections=10, sides=8):
    verts=[];faces=[];uv=[]
    for j in range(sections+1):
        t=j/sections;center=bezier(*controls,t)
        previous=bezier(*controls,max(0,t-.001));nxt=bezier(*controls,min(1,t+.001))
        direction=nxt-previous;direction.normalize()
        side=Vector((-direction.z,0,direction.x)).normalized()
        envelope=max(.015,math.sin(PI*t)**.63)*(.78+.22*t)
        half=width*.5*envelope
        # Lenticular section gives real thickness and a curved front keel.
        for k in range(sides):
            angle=k/sides*2*PI
            bulge=thickness*.5*envelope*math.cos(angle)
            point=center+side*(half*math.sin(angle))+Vector((0,bulge,0))
            verts.append(tuple(point));uv.append((k/sides,t))
    for j in range(sections):
        for k in range(sides):
            a=j*sides+k;b=j*sides+(k+1)%sides
            faces.append((a,b,b+sides,a+sides))
    faces.extend([tuple(range(sides-1,-1,-1)),tuple(sections*sides+k for k in range(sides))])
    ob=mesh_object(name,verts,faces,uv)
    ob['feather_controls']=[list(p) for p in controls]
    ob['feather_identity']='Curved feather with closed lenticular volume, shared UV scale and tapered edge.'
    return ob


def parse_human():
    positions=[];texcoords=[];faces=[];groups={};group=''
    for line in (SOURCE/'base.obj').read_text(encoding='utf8').splitlines():
        words=line.split()
        if not words:continue
        if words[0]=='v':positions.append(list(map(float,words[1:4])))
        elif words[0]=='vt':texcoords.append(tuple(map(float,words[1:3])))
        elif words[0]=='g':group=words[1]
        elif words[0]=='f':
            row=[]
            for word in words[1:]:
                ids=word.split('/');row.append((int(ids[0])-1,int(ids[1])-1))
            faces.append((group,row));groups.setdefault(group,set()).update(i for i,_ in row)
    positions=np.asarray(positions,dtype=np.float64)
    for line in (SOURCE/'caucasian-female-young.target').read_text().splitlines():
        if not line or line.startswith('#'):continue
        i,x,y,z=line.split();positions[int(i)]+=np.array([float(x),float(y),float(z)])
    body=positions[list(groups['body'])]
    scale=6.5/(body[:,1].max()-body[:,1].min());floor=body[:,1].min()
    p=np.column_stack([positions[:,0]*scale,-positions[:,2]*scale,(positions[:,1]-floor)*scale+.18])
    joints={name:Vector(p[list(ids)].mean(0)) for name,ids in groups.items() if name.startswith('joint-')}
    old_ids=sorted(groups['body']);remap={old:new for new,old in enumerate(old_ids)}
    mesh=bpy.data.meshes.new('CC0_adult_guardian_anatomy')
    body_faces=[row for name,row in faces if name=='body']
    mesh.from_pydata(p[old_ids].tolist(),[],[[remap[i] for i,_ in row] for row in body_faces]);mesh.update()
    layer=mesh.uv_layers.new(name='UVMap')
    for poly,row in zip(mesh.polygons,body_faces):
        poly.use_smooth=True
        for loop,(_,vt) in zip(poly.loop_indices,row):layer.data[loop].uv=texcoords[vt]
    ob=bpy.data.objects.new('guardian_anatomy_cc0',mesh);COL.objects.link(ob);mesh.materials.append(MARBLE);PARTS.append(ob)
    return ob,p,joints,old_ids,groups


body,source_points,joints,old_ids,source_groups=parse_human()
before=np.array([tuple(v.co) for v in body.data.vertices])
arm=bpy.data.armatures.new('Guardian_authoring_pose')
rig=bpy.data.objects.new('Guardian_authoring_pose',arm);COL.objects.link(rig)
bpy.context.view_layer.objects.active=rig;rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
def bone(name,head,tail,parent=None):
    b=arm.edit_bones.new(name);b.head=head;b.tail=tail
    if parent:b.parent=arm.edit_bones[parent]
    return b

bone('torso',joints['joint-pelvis'],joints['joint-neck'])
bone('head',joints['joint-neck'],joints['joint-head-2'],'torso')
finger_names=[]
for side,letter in [(1,'l'),(-1,'r')]:
    bone('upper_arm.'+letter,joints['joint-'+letter+'-shoulder'],joints['joint-'+letter+'-elbow'],'torso')
    bone('forearm.'+letter,joints['joint-'+letter+'-elbow'],joints['joint-'+letter+'-hand'],'upper_arm.'+letter)
    bone('hand.'+letter,joints['joint-'+letter+'-hand'],joints['joint-'+letter+'-finger-3-1'],'forearm.'+letter)
    for digit in range(1,6):
        chain=[joints[k] for n in range(1,5) if (k:='joint-'+letter+'-finger-'+str(digit)+'-'+str(n)) in joints]
        for segment in range(len(chain)-1):
            name=f'finger{digit}_{segment}.{letter}'
            bone(name,chain[segment],chain[segment+1],f'finger{digit}_{segment-1}.{letter}' if segment else 'hand.'+letter)
            finger_names.append(name)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT');body.select_set(True);rig.select_set(True)
bpy.context.view_layer.objects.active=rig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
unweighted=sum(not any(g.weight>1e-7 for g in v.groups) for v in body.data.vertices)
if unweighted:raise RuntimeError(f'Native heat weights failed on {unweighted} anatomy vertices; no nearest-bone fallback allowed.')

def aim_pose(name,head,direction):
    pb=rig.pose.bones[name]
    pb.matrix=Matrix.Translation(Vector(head))@Vector(direction).to_track_quat('Y','Z').to_matrix().to_4x4()
    bpy.context.view_layer.update()

head_pivot=joints['joint-neck'].copy()
head_rotation=Quaternion((1,0,0),math.radians(-14))
rig.pose.bones['head'].matrix=Matrix.Translation(head_pivot)@head_rotation.to_matrix().to_4x4()@Matrix.Translation(-head_pivot)@arm.bones['head'].matrix_local
bpy.context.view_layer.update()
hand_centers={}
for sign,letter in [(1,'l'),(-1,'r')]:
    shoulder=joints['joint-'+letter+'-shoulder']
    upper_direction=Vector((sign*.35,-.10,.87)).normalized()
    elbow=shoulder+upper_direction*arm.bones['upper_arm.'+letter].length
    aim_pose('upper_arm.'+letter,shoulder,upper_direction)
    fore_direction=Vector((-sign*.28,-.09,.83)).normalized()
    wrist=elbow+fore_direction*arm.bones['forearm.'+letter].length
    aim_pose('forearm.'+letter,elbow,fore_direction)
    hand_direction=Vector((-sign*.095,-.025,.36)).normalized()
    aim_pose('hand.'+letter,wrist,hand_direction)
    for name in finger_names:
        if name.endswith('.'+letter):
            pb=rig.pose.bones[name];pb.rotation_mode='XYZ'
            pb.rotation_euler.x=math.radians(10 if 'finger1_' in name else 17)
    bpy.context.view_layer.update()
    hand_centers[letter]=tuple(wrist+hand_direction*.22)

POSED=bpy.data.meshes.new_from_object(body.evaluated_get(bpy.context.evaluated_depsgraph_get()),depsgraph=bpy.context.evaluated_depsgraph_get())
body.modifiers.clear();body.parent=None;body.data=POSED
body.matrix_world=Matrix.Identity(4)
bpy.data.objects.remove(rig,do_unlink=True)

# Discard body surfaces fully covered by the dress. Keep actual adult face,
# shoulders, arms/hands and one naturally modeled foot, rather than primitives.
bm=bmesh.new();bm.from_mesh(body.data);bm.verts.ensure_lookup_table();bm.faces.ensure_lookup_table()
remove=[]
for face in bm.faces:
    orig=before[[v.index for v in face.verts]].mean(0)
    head=orig[2]>4.99 and abs(orig[0])<.90
    arms=abs(orig[0])>.56 and orig[2]>3.64 and orig[2]<5.60
    visible_foot=orig[0]>.25 and orig[2]<.51
    if not(head or arms or visible_foot):remove.append(face)
bmesh.ops.delete(bm,geom=remove,context='FACES')
loose=[v for v in bm.verts if not v.link_faces]
if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
bm.to_mesh(body.data);bm.free();body.data.update()
protect=body.vertex_groups.new(name='protect_face')
face_indices=[v.index for v in body.data.vertices if v.co.z>5.5 and v.co.z<6.9 and abs(v.co.x)<.62]
protect.add(face_indices,1.0,'REPLACE')
mod=body.modifiers.new('anatomy_game_form_reduction','DECIMATE');mod.ratio=.55;mod.vertex_group='protect_face';mod.vertex_group_factor=20
apply_modifier(body,mod)
body['source']='Pinned MakeHuman CC0 base + bundled adult female target; native Blender heat pose baked.'
body['finger_count_per_hand']=5


def tilted(point):return tuple(head_pivot+head_rotation@(Vector(point)-head_pivot))

for letter in ['l','r']:
    point=source_points[list(source_groups['helper-'+letter+'-eye'])].mean(0)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=.059,location=tilted(point))
    eye=bpy.context.object;eye.name='guardian_eye.'+letter
    for c in list(eye.users_collection):c.objects.unlink(eye)
    COL.objects.link(eye);eye.data.materials.append(MARBLE);PARTS.append(eye)
    for p in eye.data.polygons:p.use_smooth=True

# Close-fitted scalp shell; facial anatomy remains the CC0 anatomical mesh.
v=[];f=[];uv=[]
for row in range(8):
    t=row/7
    for col in range(32):
        theta=2*PI*col/32
        back=(math.sin(theta)+1)/2
        phi=.03+t*(1.0+back*.68)
        point=(.475*math.sin(phi)*math.cos(theta),-.15+.40*math.sin(phi)*math.sin(theta),6.19+.57*math.cos(phi))
        v.append(tilted(point));uv.append((col/32,t))
for row in range(7):
    for col in range(32):
        a=row*32+col;b=row*32+(col+1)%32;f.append((a,a+32,b+32,b))
mesh_object('guardian_hair_scalp',v,f,uv)
for sign in [-1,1]:
    for lock in range(7):
        phase=lock/6
        controls=[(sign*(.06+.20*phase),-.32+.15*phase,6.74),
                  (sign*(.54+.04*phase),-.34+.17*phase,6.57),
                  (sign*(.42+.13*phase),-.02+.26*phase,5.75),
                  (sign*(.51+.10*math.sin(lock)),.10+.15*phase,5.36+.08*lock)]
        points=[tilted(bezier(*controls,t/11)) for t in range(12)]
        radii=[(.075*max(.13,math.sin(PI*(t/11)*.92)**.6),.055*max(.13,math.sin(PI*(t/11)*.92)**.6)) for t in range(12)]
        tube(f'guardian_hair_lock_{sign}_{lock}',points,radii,segments=6)

# Variable elliptical dress with ten broad spiral folds and shaped neckline.
v=[];f=[];uv=[];rings=31;sectors=64
profile=[(.18,1.14,.72),(.7,1.09,.66),(1.5,1.00,.61),(2.5,.88,.54),(3.5,.72,.44),(3.95,.55,.36),(4.5,.71,.44),(5.0,.74,.38),(5.37,.79,.34)]
def dress_radius(z):
    for a,b in zip(profile,profile[1:]):
        if a[0]<=z<=b[0]:
            t=(z-a[0])/(b[0]-a[0]);return(a[1]*(1-t)+b[1]*t,a[2]*(1-t)+b[2]*t)
    return profile[-1][1:]
for row in range(rings):
    t=row/(rings-1);z=.18+t*5.19;rx,ry=dress_radius(z)
    for col in range(sectors):
        theta=col/sectors*2*PI
        broad=.11*math.sin(theta*10+z*.52)*(.30+.70*(1-t)**.5)
        secondary=.018*math.sin(theta*20-z*.9)*(1-t)
        front=max(0,-math.sin(theta))
        neckline=.31*front**12*max(0,(t-.86)/.14)
        x=(rx+broad+secondary)*math.cos(theta)
        y=(ry+broad*.7+secondary)*math.sin(theta)
        v.append((x,y,z-neckline));uv.append((col/sectors,t))
for row in range(rings-1):
    for col in range(sectors):
        a=row*sectors+col;b=row*sectors+(col+1)%sectors;f.append((a,b,b+sectors,a+sectors))
dress=mesh_object('guardian_carved_robe_main',v,f,uv)
solid=dress.modifiers.new('plausible_cloth_edge_thickness','SOLIDIFY');solid.thickness=.027;apply_modifier(dress,solid)


def cloth_panel(name, controls, width, phase):
    verts=[];faces=[];uv=[];sections=24;across=10
    for row in range(sections+1):
        t=row/sections;center=bezier(*controls,t)
        tangent=(bezier(*controls,min(1,t+.002))-bezier(*controls,max(0,t-.002))).normalized()
        side=Vector((tangent.z,0,-tangent.x)).normalized()
        half=width*(.36+.30*math.sin(PI*t))
        for col in range(across+1):
            q=col/across*2-1
            # Broad transverse curl, not a flat plate or cylinder.
            depth=.17*math.sin(q*PI*2.1+phase+t*2.6)+.12*q*q
            point=center+side*(q*half)+Vector((0,depth,0))
            verts.append(tuple(point));uv.append((col/across,t))
    for row in range(sections):
        for col in range(across):
            a=row*(across+1)+col;faces.append((a,a+1,a+across+2,a+across+1))
    ob=mesh_object(name,verts,faces,uv)
    solid=ob.modifiers.new('sculpted_panel_thickness','SOLIDIFY');solid.thickness=.024;apply_modifier(ob,solid)
    return ob

cloth_panel('guardian_mantle_left',[(-.65,.10,5.35),(-1.35,-.05,4.50),(-1.78,-.32,3.30),(-1.32,-.35,2.12)],.67,.7)
cloth_panel('guardian_mantle_right',[(.65,.10,5.35),(1.25,-.03,4.6),(1.38,-.24,3.20),(2.78,-.23,2.02)],.86,1.2)
cloth_panel('guardian_robe_wind_sweep',[(.58,-.16,3.60),(1.28,-.13,2.85),(2.40,-.11,2.28),(2.44,-.18,1.12)],1.14,.3)
cloth_panel('guardian_front_fold_left',[(-.28,-.4,3.92),(-.68,-.57,2.68),(-.91,-.68,1.39),(-.46,-.75,.24)],.64,.1)
cloth_panel('guardian_front_fold_right',[(.27,-.4,3.92),(.50,-.61,2.51),(.61,-.76,1.19),(.27,-.77,.20)],.59,1.4)

# Paired wings: curved structural shoulder, broad primary/secondary feathers,
# short overlapping coverts. Each feather has a closed volume and distinct tip.
tips=[(7.46,8.67),(7.67,7.92),(7.56,7.20),(7.13,6.53),(6.72,5.90),
      (6.11,5.28),(5.50,4.68),(4.83,4.20),(4.12,3.88),(3.43,3.73)]
feather_counts={'primary':0,'secondary':0,'coverts':0}
for sign,label in [(-1,'right'),(1,'left')]:
    # A closed, gently domed anatomical backing attaches the layered roots.
    # Outer feather tips remain separate, preserving open silhouette gaps.
    outline=[(.52,4.70),(.91,5.59),(1.52,6.44),(2.28,6.80),(3.19,6.46),
             (4.18,5.80),(3.63,4.97),(2.48,4.14),(1.23,4.03),(.67,4.44)]
    def boundary(t):
        position=t*len(outline);i=int(position)%len(outline);q=position%1
        a=Vector(outline[(i-1)%len(outline)]);b=Vector(outline[i]);c=Vector(outline[(i+1)%len(outline)]);d=Vector(outline[(i+2)%len(outline)])
        return .5*((2*b)+(-a+c)*q+(2*a-5*b+4*c-d)*q*q+(-a+3*b-3*c+d)*q*q*q)
    verts=[];faces=[];uv=[];around=24;radial=2;count=1+radial*around
    for back in [False,True]:
        offset=len(verts);verts.append((sign*2.12,.59+(.14 if back else 0),5.42));uv.append((.5,.5))
        for row in range(1,radial+1):
            fraction=row/radial
            for col in range(around):
                edge=boundary(col/around);x=2.12+(edge.x-2.12)*fraction;z=5.42+(edge.y-5.42)*fraction
                y=.59+.06*fraction*fraction+(.14 if back else 0)
                verts.append((sign*x,y,z));uv.append(((x-.5)/3.7,(z-4)/2.9))
        for col in range(around):
            a=offset+1+col;b=offset+1+(col+1)%around
            faces.append((offset,b,a) if back else (offset,a,b))
        for row in range(radial-1):
            for col in range(around):
                a=offset+1+row*around+col;b=offset+1+row*around+(col+1)%around
                faces.append((a+around,b+around,b,a) if back else (a,b,b+around,a+around))
    for col in range(around):
        a=1+(radial-1)*around+col;b=1+(radial-1)*around+(col+1)%around
        faces.append((a,a+count,b+count,b))
    mesh_object('guardian_wing_'+label+'_anatomical_core',verts,faces,uv)
    shoulder_controls=[(sign*.54,.46,4.87),(sign*1.02,.61,5.10),(sign*1.46,.63,6.07),(sign*2.52,.60,6.58)]
    tube('guardian_wing_'+label+'_structural_root',[bezier(*shoulder_controls,n/15) for n in range(16)],
         [(.26*(1-.35*n/15),.20*(1-.30*n/15)) for n in range(16)],segments=8)
    for index,(tx,tz) in enumerate(tips):
        frac=index/(len(tips)-1)
        root=(sign*(2.31-.78*frac),.56,6.44-1.43*frac)
        controls=[root,(sign*(3.80-1.19*frac),.66,6.61-1.63*frac),
                  (sign*(tx-.57),.68,tz-.47+frac*.12),(sign*tx,.56,tz)]
        feather('guardian_wing_'+label+f'_primary_{index:02d}',controls,1.12-.22*frac,.15,sections=9,sides=8)
        feather_counts['primary']+=1
    for index in range(8):
        frac=index/7
        root=(sign*(1.47-.12*frac),.38,6.10-1.62*frac)
        tip=(sign*(4.30-1.35*frac),.29,6.77-2.54*frac)
        controls=[root,(sign*2.34,.34,root[2]+.33),(sign*(abs(tip[0])-.42),.31,tip[2]+.13),tip]
        feather('guardian_wing_'+label+f'_secondary_{index:02d}',controls,.86-.16*frac,.14,sections=7,sides=8)
        feather_counts['secondary']+=1
    for row in range(2):
        for index in range(10):
            frac=index/9
            x=1.16+frac*1.45+row*.38;z=5.38+frac*1.27-row*.20
            root=(sign*x,.19-row*.045,z)
            tip=(sign*(x+.73),.10-row*.045,z-.36-.26*frac)
            controls=[root,(sign*(x+.19),.12-row*.045,z+.03),(sign*(x+.60),.08-row*.045,z-.17),tip]
            feather('guardian_wing_'+label+f'_covert_{row}_{index:02d}',controls,.43,.105,sections=5,sides=6)
            feather_counts['coverts']+=1

# Modest carved base, intentionally integrated into the candidate envelope.
bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=1.24,depth=.18,location=(0,0,.09))
base=bpy.context.object;base.name='guardian_mounting_plinth';base.data.materials.append(MARBLE);PARTS.append(base)
for c in list(base.users_collection):c.objects.unlink(base)
COL.objects.link(base)

def gold_path(name, points, radius=.038):return tube(name,points,radius,GOLD,segments=6)

gold_path('guardian_bodice_center_trim',[(0,-.48,5.03),(0,-.51,4.68),(0,-.50,4.28),(0,-.42,3.98)],.045)
for sign in [-1,1]:
    gold_path(f'guardian_bodice_outer_trim_{sign}',[(0,-.46,5.09),(sign*.35,-.51,4.97),(sign*.58,-.39,4.71),(sign*.40,-.40,4.35),(sign*.16,-.41,4.06)],.041)
    gold_path(f'guardian_robe_vertical_trim_{sign}',[(sign*.13,-.45,3.97),(sign*.24,-.58,3.03),(sign*.25,-.70,2.00),(sign*.30,-.75,.45)],.037)
    wrist=Vector(hand_centers['l' if sign>0 else 'r'])
    gold_path(f'guardian_cuff_{sign}',[(wrist.x+sign*.13,wrist.y-.02,wrist.z-.15),(wrist.x,wrist.y-.14,wrist.z-.17),(wrist.x-sign*.13,wrist.y-.02,wrist.z-.15)],.055)

def diamond(name, center, width, low, high, material):
    cx,cy,cz=center
    verts=[(cx,cy,low),(cx,cy,high),(cx-width,cy,cz),(cx,cy-width*.43,cz),(cx+width,cy,cz),(cx,cy+width*.43,cz)]
    faces=[(0,2,3),(0,3,4),(0,4,5),(0,5,2),(1,3,2),(1,4,3),(1,5,4),(1,2,5)]
    ob=mesh_object(name,verts,faces,[(0,.5),(1,.5),(.5,0),(.5,.3),(.5,1),(.5,.7)],material)
    for p in ob.data.polygons:p.use_smooth=False
    return ob

crystal=diamond('guardian_magic_crystal',(0,-.31,8.43),.79,7.47,9.5,BLUE)
for sign in [-1,1]:
    grip=Vector(hand_centers['l' if sign>0 else 'r'])
    gold_path(f'guardian_crystal_cradle_{sign}',[tuple(grip),(sign*.65,-.31,7.55),(sign*.81,-.31,8.00),(sign*.82,-.31,8.43)],.060)
    gold_path(f'guardian_crystal_lower_cage_{sign}',[(0,-.66,7.37),(sign*.35,-.60,7.72),(sign*.62,-.53,8.06)],.048)
    diamond(f'guardian_crystal_cage_finial_{sign}',(sign*.82,-.31,8.48),.10,8.31,8.83,GOLD)
diamond('guardian_bodice_blue_inlay',(0,-.525,4.62),.155,4.38,4.86,BLUE)
diamond('guardian_waist_blue_inlay',(0,-.455,4.03),.115,3.84,4.20,BLUE)
diamond('guardian_robe_blue_inlay',(0,-.66,2.78),.12,2.58,3.00,BLUE)

# Preserve animation/water identities as a handoff contract without touching
# the existing fountain's live hook objects or water package.
root=bpy.data.objects.new('fountain_guardian_candidate_root',None);COL.objects.link(root)
root['mount_world_xyz']=[0,7.4,176]
root['approved_reference_sha256']=hash_file(ROOT/'docs/ui/concepts/fountain-guardian-v1-20261001.png')
root['preserved_existing_fountain_hooks']=['anim_crystal_fountain','emit_fountain_spray']
root['material_finish_owner']='Claude'
root['candidate_only']=True
for ob in PARTS:ob.parent=root
hook=bpy.data.objects.new('anim_crystal_fountain',None);COL.objects.link(hook);hook.parent=root;hook.location=(0,-.31,8.43)
hook['existing_hook_contract']='Crystal center; root preservesname, existing fountain runtime owner decides integration.'
for vertex in crystal.data.vertices:vertex.co-=hook.location
crystal.parent=hook
crystal.location=(0,0,0)
bpy.context.view_layer.update()


def inspect_objects(objects):
    allpoints=[];records=[]
    for ob in objects:
        if ob.type!='MESH':continue
        pts=[ob.matrix_world@v.co for v in ob.data.vertices];allpoints.extend(pts)
        uv=ob.data.uv_layers.active
        nonfinite=sum(not all(math.isfinite(c) for c in p) for p in pts)
        uv_bad=sum(not all(math.isfinite(c) for c in loop.uv) for loop in uv.data) if uv else len(ob.data.loops)
        records.append({'name':ob.name,'vertices':len(ob.data.vertices),'triangles':sum(len(p.vertices)-2 for p in ob.data.polygons),
                        'materials':[m.name for m in ob.data.materials],'uv_layers':len(ob.data.uv_layers),'nonfinite':nonfinite,'invalid_uv':uv_bad})
    lo=[min(p[i] for p in allpoints) for i in range(3)];hi=[max(p[i] for p in allpoints) for i in range(3)]
    return {'bounds_blender_xyz':{'min':lo,'max':hi},'dimensions_xyz':[hi[i]-lo[i] for i in range(3)],'triangles':sum(r['triangles'] for r in records),'meshes':records}

SCENE.view_settings.view_transform='AgX'
bpy.context.view_layer.update()
for ob in PARTS:repair_flat_uv_caps(ob)
editable=inspect_objects(PARTS)
SCENE['no_render_performed']=True
SCENE['candidate_contract']='Geometry/UV/form only. Claude owns textures and Blender rendering. Native Babylon captures still required.'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'fountain_guardian_v1.blend'))

# Runtime copies are merged by slot for bounded draw units; editable source
# retains component names. Geometry reduction never edits the source .blend.
runtime=bpy.data.collections.new('Guardian_runtime_candidates');SCENE.collection.children.link(runtime)
for ob in PARTS:ob.hide_set(True)
lod_records=[]
for lod,target_triangles in [(0,17500),(1,6000),(2,2200)]:
    copies=[]
    for ob in PARTS:
        clone=ob.copy();clone.data=ob.data.copy();runtime.objects.link(clone)
        clone.parent=None;clone.matrix_world=ob.matrix_world.copy();clone.hide_set(False)
        clone['guardian_component']=ob.name
        if lod==0:
            name=ob.name
            if name=='guardian_anatomy_cc0':ratio=.68
            elif 'primary_' in name or 'secondary_' in name or '_covert_' in name:ratio=.80
            elif 'robe_' in name or 'mantle_' in name:ratio=.13
            elif 'hair_' in name:ratio=.35
            elif 'structural_root' in name or 'anatomical_core' in name or 'mounting_plinth' in name:ratio=.50
            elif ob.data.materials[0]==GOLD:ratio=.50
            else:ratio=1.0
            if ratio<1:
                dec=clone.modifiers.new('component_form_budget','DECIMATE');dec.ratio=ratio
                apply_modifier(clone,dec)
        clone.data.validate(clean_customdata=False)
        copies.append(clone)
    groups=[]
    crystal_copy=next(ob for ob in copies if ob['guardian_component']=='guardian_magic_crystal')
    crystal_world=crystal_copy.matrix_world.copy()
    crystal_copy.parent=hook;crystal_copy.matrix_world=crystal_world
    material_members=[(material,[ob for ob in copies if ob.data.materials[0]==material and ob is not crystal_copy]) for material in [MARBLE,GOLD,BLUE]]
    for material,members in material_members:
        bpy.ops.object.select_all(action='DESELECT')
        for ob in members:ob.select_set(True)
        bpy.context.view_layer.objects.active=members[0];bpy.ops.object.join()
        joined=members[0];joined.name=f'guardian_lod{lod}_{material.name}'
        groups.append(joined)
    crystal_copy.name=f'guardian_lod{lod}_crystal_animated_hook'
    groups.append(crystal_copy)
    current=sum(sum(len(p.vertices)-2 for p in ob.data.polygons) for ob in groups)
    if current>target_triangles:
        ratio=target_triangles/current
        for ob in groups:
            if ob.data.materials[0]==BLUE:continue
            dec=ob.modifiers.new('runtime_form_budget','DECIMATE');dec.ratio=ratio
            apply_modifier(ob,dec)
    for ob in groups:
        ob.data.validate(clean_customdata=False)
        repair_flat_uv_caps(ob)
    bpy.ops.object.select_all(action='DESELECT')
    for ob in groups:ob.select_set(True)
    hook.select_set(True)
    bpy.context.view_layer.objects.active=groups[0]
    path=OUT/f'fountain_guardian_lod{lod}.glb'
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,
        export_animations=False,export_skins=False,export_morph=False,export_extras=True)
    review=inspect_objects(groups)
    review.update({'lod':lod,'path':path.name,'sha256':hash_file(path),'bytes':path.stat().st_size})
    lod_records.append(review)
    for ob in groups:bpy.data.objects.remove(ob,do_unlink=True)

manifest={'schema':1,'status':'FORM_CANDIDATE_REQUIRES_CLAUDE_RENDER_AND_NATIVE_BABYLON_REVIEW',
    'asset':'fountain_guardian_v1','approved_image':'docs/ui/concepts/fountain-guardian-v1-20261001.png',
    'approved_image_sha256':root['approved_reference_sha256'],'mount_world_xyz':[0,7.4,176],
    'units':'metres','front':'Blender -Y / exported glTF +Z','source_geometry_license':'CC0-1.0',
    'source_repository':'https://github.com/makehumancommunity/makehuman','source_commit':(SOURCE/'makehuman-commit.txt').read_text().strip(),
    'source_license_urls':['https://static.makehumancommunity.org/about/license.html','https://github.com/makehumancommunity/makehuman/blob/master/LICENSE.md'],
    'source_files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':hash_file(p)} for p in sorted(SOURCE.iterdir()) if p.is_file()],
    'authoring_pose':'Native Blender ARMATURE_AUTO heat succeeded, then posed adult face/arms/five-finger hands baked to static geometry.',
    'unweighted_native_anatomy_vertices':unweighted,'hand_centers':hand_centers,'feather_counts':feather_counts,
    'closed_component_winding_repairs':WINDING_REPAIRS,
    'zero_area_cap_uv_repairs':UV_CAP_REPAIRS,
    'stable_material_slots':['marble_statue','metal_gold','magic_blue'],'material_status':'Flat placeholder slots only; no map-wide textures/material changes or texture baking.',
    'preserved_hook_contract':{'anim_crystal_fountain':{'local_xyz':[0,-.31,8.43]},'emit_fountain_spray':'Existing fountain emitter remains unchanged; candidate does not replace water or runtime behavior.'},
    'editable':{'path':'fountain_guardian_v1.blend','sha256':hash_file(OUT/'fountain_guardian_v1.blend'),**editable},'lods':lod_records,
    'checks':{'no_blender_renders':True,'no_source_city_changes':True,'no_paid_jobs_or_installs':True},
    'known_gaps':['No native GPU/Blender render judged yet; anatomy and wing silhouette need reference-side/close/player review.',
                  'Cloth is authored sculpture, not simulated fabric; hair locks and feather junctions need visual critique.',
                  'Hand/grip and gold cage contact must be verified in close captures; five-finger source does not guarantee a natural final grasp.',
                  'UV charts reuse modular feather coordinates intentionally; Claude must maintain material scale and inspect seams.',
                  'Runtime packages are focal candidates, not merged into city or activated in game; no AAA claim from triangle count.']}
(OUT/'asset-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
(ROOT/'planning/evidence/fountain-guardian-form-20261001.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('GUARDIAN_FORM_RESULT',json.dumps({'editable_triangles':editable['triangles'],'dimensions':editable['dimensions_xyz'],'native_heat_unweighted':unweighted,'feather_counts':feather_counts,'lods':[{'lod':r['lod'],'triangles':r['triangles'],'bytes':r['bytes']} for r in lod_records]}))

reimports=[]
for record in lod_records:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(OUT/record['path']))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    result=inspect_objects(meshes)
    result.update({'lod':record['lod'],'mesh_count':len(meshes),'source_sha256':record['sha256'],
                   'triangle_count_matches':result['triangles']==record['triangles'],
                   'material_slots':sorted({m.name for o in meshes for m in o.data.materials if m})})
    reimports.append(result)
manifest['reimport_validation']=reimports
manifest['checks']['reimports_finite_and_uv_valid']=all(all(r['nonfinite']==0 and r['invalid_uv']==0 and r['uv_layers']>0 for r in run['meshes']) for run in reimports)
manifest['checks']['reimport_triangle_counts_match']=all(r['triangle_count_matches'] for r in reimports)
(OUT/'asset-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
(ROOT/'planning/evidence/fountain-guardian-form-20261001.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('GUARDIAN_REIMPORT_PASS',json.dumps(manifest['checks']))
