"""Read-only S04 identities from the selected city source and its exact master.

Writes JSON evidence only; no source saves, exports, renders or materials edits.
"""
import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from mathutils.kdtree import KDTree

P=argparse.ArgumentParser()
P.add_argument('--root',required=True,type=Path)
P.add_argument('--output',required=True,type=Path)
A=P.parse_args(sys.argv[sys.argv.index('--')+1:])
ROOT=A.root.resolve();ACTIVE=ROOT/'assets/models/reference-city/r5/active-revision.json'
active=json.loads(ACTIVE.read_text(encoding='utf8'))
source_record=active['files']['city-source.glb']
master_record=next(record for name,record in active['files'].items() if name.endswith('.blend'))
SOURCE=ROOT/source_record['path'];MASTER=ROOT/master_record['path']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

source_hash=sha(SOURCE);master_hash=sha(MASTER)
if source_hash!=source_record['sha256'] or master_hash!=master_record['sha256']:
    raise RuntimeError('Selected source/master hash mismatch; refuse mixed-revision audit.')
blob=SOURCE.read_bytes();json_length=struct.unpack_from('<I',blob,12)[0]
doc=json.loads(blob[20:20+json_length]);binary=memoryview(blob)[28+json_length:]
parents={child:i for i,node in enumerate(doc['nodes']) for child in node.get('children',[])}

def node_matrix(node):
    if 'matrix' in node:return np.array(node['matrix']).reshape(4,4).T
    t=node.get('translation',[0,0,0]);s=node.get('scale',[1,1,1]);q=node.get('rotation',[0,0,0,1])
    return np.array(Matrix.LocRotScale(Vector(t),Quaternion((q[3],q[0],q[1],q[2])),Vector(s)))

def read_positions(index):
    accessor=doc['accessors'][index];view=doc['bufferViews'][accessor['bufferView']]
    if accessor['componentType']!=5126 or accessor.get('sparse') or view.get('extensions'):
        raise RuntimeError('Source witness expects uncompressed FLOAT positions.')
    offset=view.get('byteOffset',0)+accessor.get('byteOffset',0);stride=view.get('byteStride',12)
    return np.ndarray((accessor['count'],3),dtype='<f4',buffer=binary,offset=offset,strides=(stride,4)).copy()

material_points={};source_nodes=[]
for index,node in enumerate(doc['nodes']):
    if 'mesh' not in node:continue
    transform=node_matrix(node);parent=parents.get(index)
    while parent is not None:
        transform=node_matrix(doc['nodes'][parent])@transform;parent=parents.get(parent)
    for primitive_index,primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
        material=doc['materials'][primitive['material']]['name'];points=read_positions(primitive['attributes']['POSITION'])
        world=(np.column_stack((points,np.ones(len(points))))@transform.T)[:,:3]
        material_points.setdefault(material,[]).append(world)
        source_nodes.append({'node_index':index,'node_name':node.get('name'),'mesh_index':node['mesh'],
                             'mesh_name':doc['meshes'][node['mesh']].get('name'),'primitive':primitive_index,'material':material})
trees={}
def material_tree(name):
    if name not in trees:
        points=np.concatenate(material_points[name]);tree=KDTree(len(points))
        for i,p in enumerate(points):tree.insert(Vector(p),i)
        tree.balance();trees[name]=tree
    return trees[name]

bpy.ops.wm.open_mainfile(filepath=str(MASTER))
dg=bpy.context.evaluated_depsgraph_get()
fountain_root=bpy.data.objects.get('kit_plaza_fountain')
if fountain_root is None:raise RuntimeError('Selected master has no exact kit_plaza_fountain root.')

def ancestry(ob):
    path=[]
    while ob is not None:path.append(ob.name);ob=ob.parent
    return path

def runtime_point(p):return np.array((p.x,p.z,176+p.y))
def gltf_point(p):return Vector((p.x,p.z,-p.y))
volumes=[{'id':'lower','radius':8.0,'y_min':1.35,'water_y':2.20},
         {'id':'middle','radius':4.25,'y_min':3.20,'water_y':4.29},
         {'id':'upper','radius':1.80,'y_min':6.00,'water_y':6.95}]

def segment_circle(a,b,radius):
    a=np.array((a[0],a[2]-176));b=np.array((b[0],b[2]-176));d=b-a
    q=0 if d@d<1e-12 else max(0,min(1,-(a@d)/(d@d)))
    return np.linalg.norm(a+q*d)<=radius

def wet_intersections(points,triangles):
    def clip_height(poly,height,above):
        result=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            inside_a=a[1]>=height-1e-7 if above else a[1]<=height+1e-7
            inside_b=b[1]>=height-1e-7 if above else b[1]<=height+1e-7
            if inside_a:result.append(a)
            if inside_a!=inside_b and abs(b[1]-a[1])>1e-12:
                result.append(a+(b-a)*((height-a[1])/(b[1]-a[1])))
        return result
    hits={}
    for volume in volumes:
        count=0;low=volume['y_min'];high=volume['water_y']+.03;r=volume['radius']
        for triangle in triangles:
            v=points[list(triangle)]
            if v[:,1].max()<low or v[:,1].min()>high:continue
            poly=clip_height(clip_height(list(v),low,True),high,False)
            if not poly:continue
            found=any(math.hypot(p[0],p[2]-176)<r for p in poly)
            if not found:found=any(segment_circle(a,b,r) for a,b in zip(poly,poly[1:]+poly[:1]))
            if not found and len(poly)>=3:
                plane=[np.array((p[0],p[2]-176)) for p in poly]
                crosses=[a[0]*b[1]-a[1]*b[0] for a,b in zip(plane,plane[1:]+plane[:1])]
                area=abs(sum(crosses))*.5
                found=area>1e-9 and (all(c>=-1e-8 for c in crosses) or all(c<=1e-8 for c in crosses))
            if found:count+=1
        if count:hits[volume['id']]=count
    return hits

def classify(name,in_fountain):
    if name.startswith('fountain guardian crown crystal'):
        return 'KEEP','Existing crystal retained by the requested source contract; prevent duplicate candidate crystal in a body-only DEV swap.'
    if name.startswith('fountain guardian ') or name.startswith('fountain feather ridge'):
        return 'REWORK','Exact legacy guardian body/arm/palm/wing component, eligible for isolated body-only replacement after review.'
    if name.startswith('fountain arcing water jet'):
        return 'REWORK','Authored static jet reference; inspect duplication against live jets and alter visibility only by exact identity if live ownership is confirmed.'
    if name in {'fountain central stem','fountain octagonal plinth'}:
        return 'KEEP','Named load-bearing support: supports upper bowls/statue; darkness or wet-volume overlap alone is not grounds for removal.'
    if name.startswith(('fountain carved lower basin','fountain second bowl','fountain upper chalice','fountain mosaic inner lip')):
        return 'KEEP','Named basin shell/annular rim; inspect wall/floor/cap topology independently of water shading.'
    if name in {'fountain blue water','fountain second water','fountain upper water'}:
        return 'KEEP','Source water reference/contract; runtime owner must select one visible representation per pool.'
    if name.startswith(('anim_crystal_fountain','emit_fountain_spray')):
        return 'KEEP','Stable existing animation/emitter hook; do not remove with static guardian geometry.'
    if in_fountain:return 'INVESTIGATE','Named fountain child not covered by the known component contract; native object-ID/solo view required before modification.'
    return 'INVESTIGATE','Non-fountain named source geometry genuinely intersects an interior water/support slab; verify assembly/placement and purpose, not color.'

rows=[]
for ob in bpy.context.scene.objects:
    chain=ancestry(ob);in_fountain=fountain_root.name in chain
    if ob.type!='MESH':
        if in_fountain and ob.name.startswith(('anim_','emit_','fx_')):
            decision,reason=classify(ob.name,True)
            rows.append({'source_object_id':ob.name,'type':ob.type,'ancestry':chain,
                         'origin_runtime_xyz':runtime_point(ob.matrix_world.translation).tolist(),'decision':decision,'reason':reason})
        continue
    corners=np.array([runtime_point(ob.matrix_world@Vector(c)) for c in ob.bound_box])
    lo=corners.min(0);hi=corners.max(0)
    overlaps=lo[0]<=8.1 and hi[0]>=-8.1 and lo[2]<=184.1 and hi[2]>=167.9 and lo[1]<=7.0 and hi[1]>=1.35
    if not(in_fountain or overlaps):continue
    ev=ob.evaluated_get(dg);mesh=ev.to_mesh();mesh.calc_loop_triangles()
    world=[ob.matrix_world@v.co for v in mesh.vertices];points=np.array([runtime_point(p) for p in world])
    triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
    hits=wet_intersections(points,triangles) if overlaps else {}
    if not in_fountain and not hits:ev.to_mesh_clear();continue
    materials=[m.name for m in mesh.materials if m]
    decision,reason=classify(ob.name,in_fountain)
    witnessed=[]
    for material in materials:
        if material not in material_points:continue
        tree=material_tree(material)
        sample_ids=sorted({0,len(world)//3,len(world)*2//3,len(world)-1})
        errors=[tree.find(gltf_point(world[i]))[2] for i in sample_ids]
        witnessed.append({'material':material,'sample_count':len(errors),'max_vertex_gap_m':max(errors),'all_samples_match_0_1mm':max(errors)<.0001})
    caps=[]
    for polygon in mesh.polygons:
        if len(polygon.vertices)<16:continue
        p=points[list(polygon.vertices)]
        if p[:,1].max()-p[:,1].min()<1e-5:
            caps.append({'polygon_index':polygon.index,'vertices':len(polygon.vertices),'y':float(p[:,1].mean()),
                         'radius_min_vertex_m':float(np.hypot(p[:,0],p[:,2]-176).min()),'radius_max_vertex_m':float(np.hypot(p[:,0],p[:,2]-176).max())})
    rows.append({'source_object_id':ob.name,'type':ob.type,'ancestry':chain,'collections':[c.name for c in ob.users_collection],
                 'bounds_runtime_xyz':{'min':points.min(0).tolist(),'max':points.max(0).tolist()},
                 'triangles':len(triangles),'materials':materials,'wet_interior_intersections':hits,'large_horizontal_ngons':caps,
                 'selected_glb_sample_witnesses':witnessed,'decision':decision,'reason':reason})
    ev.to_mesh_clear()

rows.sort(key=lambda r:r['source_object_id'])
bridge_assemblies=[]
for finial in sorted((o for o in bpy.context.scene.objects if o.name.startswith('bridge blue lamp finial copper finial')),key=lambda o:o.name):
    suffix=finial.name[len('bridge blue lamp finial copper finial'):]
    roof=bpy.data.objects.get('bridge blue lamp finial'+suffix)
    pedestal=bpy.data.objects.get('bridge lamp pedestal'+suffix)
    if roof is None or pedestal is None or roof.parent is None or roof.parent!=pedestal.parent:
        bridge_assemblies.append({'finial_id':finial.name,'status':'UNPROVEN_ASSEMBLY','reason':'Exact counterpart/root checks failed.'});continue
    owner=roof.parent
    fp=np.array([tuple(v.co) for v in finial.data.vertices]);rp=np.array([tuple(v.co) for v in roof.data.vertices]);pp=np.array([tuple(v.co) for v in pedestal.data.vertices])
    local_center=rp[:,:2].mean(0)
    implied_rise=float(pp[:,2].min()-2.5)
    corrected_local=Matrix.Translation((0,0,implied_rise))@finial.matrix_basis
    expected_finial_matrix=owner.matrix_world@corrected_local
    expected_roof_matrix=owner.matrix_world@Matrix.Translation((0,0,implied_rise))@roof.matrix_basis
    expected_finial=np.array([runtime_point(expected_finial_matrix@Vector(v)) for v in fp])
    expected_roof=np.array([runtime_point(expected_roof_matrix@Vector(v)) for v in rp])
    pedestal_world=np.array([runtime_point(pedestal.matrix_world@Vector(v)) for v in pp])
    bridge_assemblies.append({'status':'PROVEN_CONSTRUCTION_PAIR','finial_id':finial.name,'roof_id':roof.name,'pedestal_id':pedestal.name,
        'owner_root_id':owner.name,'current_finial_parent':finial.parent.name if finial.parent else None,
        'authored_local_xy':local_center.tolist(),'arch_rise_from_pedestal_m':implied_rise,
        'pedestal_current_bounds_runtime':{'min':pedestal_world.min(0).tolist(),'max':pedestal_world.max(0).tolist()},
        'expected_roof_bounds_runtime':{'min':expected_roof.min(0).tolist(),'max':expected_roof.max(0).tolist()},
        'expected_finial_bounds_runtime':{'min':expected_finial.min(0).tolist(),'max':expected_finial.max(0).tolist()},
        'expected_finial_matrix_blender':[list(row) for row in expected_finial_matrix],
        'expected_roof_matrix_blender':[list(row) for row in expected_roof_matrix],
        'repair_contract':'Preserve all three exact IDs. Pedestal stays put; raise roof by the already authored pedestal arch rise, parent finial to the same root with identity parent inverse and matching local rise. Do not preserve its erroneous orphan world placement.',
        'construction_evidence':['assets/blender/city_r5/kits/buildings.py:419-425 (_conical_roof owns roof but not finial)',
                                 'assets/blender/city_r5/kits/landmarks.py:340-345 (pedestal includes arch rise; roof input uses fixed3.25)']})
by_finial={row['finial_id']:row for row in bridge_assemblies if row['status']=='PROVEN_CONSTRUCTION_PAIR'}
for row in rows:
    assembly=by_finial.get(row['source_object_id'])
    if assembly:
        row['decision']='REWORK'
        row['reason']='Proved bridge-lamp assembly defect: orphan finial misses its root transform and roof/finial miss the pedestal arch rise. Preserve and restore the complete exact assembly contract, not delete by appearance.'
        row['proved_assembly_ids']=[assembly['pedestal_id'],assembly['roof_id'],assembly['finial_id']]
        row['expected_owner_root_id']=assembly['owner_root_id']
guardian_remove=[r['source_object_id'] for r in rows if r['source_object_id'].startswith('fountain guardian ') and not r['source_object_id'].startswith('fountain guardian crown crystal') or r['source_object_id'].startswith('fountain feather ridge')]
protected=[r['source_object_id'] for r in rows if r['decision']=='KEEP']
non_fountain=[r for r in rows if fountain_root.name not in r['ancestry'] and r.get('wet_interior_intersections')]
immutable=sha(SOURCE)==source_hash and sha(MASTER)==master_hash
report={'schema':'xexoria.fountain-source-identities/1','active_revision':active['revision'],
        'selected_source':{'path':source_record['path'],'sha256':source_hash},'selected_master':{'path':master_record['path'],'sha256':master_hash},
        'coordinate_basis':'runtime=[BlenderX,BlenderZ,176+BlenderY]; source glTF=[BlenderX,BlenderZ,-BlenderY]',
        'source_identity_limit':'GLB has merged material buckets and does not preserve every original object ID. Exact removal must use selected editable master IDs or a separate per-ID DEV export; do not remove an entire City/material bucket.',
        'fountain_root_id':fountain_root.name,'wet_volume_contracts':volumes,'objects':rows,
        'guardian_body_only_replacement_ids':guardian_remove,'protected_keep_ids':protected,
        'non_fountain_wet_intrusion_ids':[r['source_object_id'] for r in non_fountain],
        'merged_source_nodes':source_nodes,
        'bridge_lamp_assemblies':bridge_assemblies,
        'dev_swap_contract':{'remove_only':guardian_remove,'preserve':protected,
            'candidate_crystal_rule':'Body-only review preserves the old crown crystal and hooks; suppress the candidate crystal child to avoid overlapping blue geometry. A full crystal replacement requires a separately recorded choice.',
            'no_source_writes':True,'no_color_or_broad_centroid_deletion':True},
        'source_hashes_unchanged':immutable,'renders_performed':False,
        'limits':['Wet slabs/radii are inspection volumes, not a deletion rule.','Sample witnesses establish selected-source correspondence but do not identify every triangle range.','No native object-ID/solo capture or material/lighting diagnosis performed.','Source identities do not prove which fallback/HLOD/detail representations are currently visible.']}
if not immutable:raise RuntimeError('Selected source changed during read-only audit.')
A.output.resolve().write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('FOUNTAIN_SOURCE_IDENTITIES',json.dumps({'revision':active['revision'],'guardian_body_ids':guardian_remove,'protected_keep_ids':protected,'non_fountain_wet_intrusion_ids':report['non_fountain_wet_intrusion_ids'],'objects':len(rows),'hashes_unchanged':immutable}))
