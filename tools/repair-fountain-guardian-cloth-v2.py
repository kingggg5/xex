"""Versioned, geometry-only continuous-cloth and static-water repair.

Preserves v1 inputs; no Blender renders, material pass or active promotion.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import struct
import sys
from collections import defaultdict
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1]
V1=ROOT/'assets/models/reference-city/r5/art-candidates/fountain-guardian-v1'
FORM=ROOT/'assets/models/reference-city/r5/art-candidates/fountain-guardian-v2'
CITY1=ROOT/'assets/models/reference-city/r5/fountain-guardian-review-candidate'
CITY=ROOT/'assets/models/reference-city/r5/fountain-guardian-review-v2-candidate'
EVIDENCE=ROOT/'planning/evidence/fountain-guardian-cloth-v2-20261001.json'
P=argparse.ArgumentParser();P.add_argument('--mode',required=True,choices=['form','city','source','runtime'])
A=P.parse_args(sys.argv[sys.argv.index('--')+1:])
spec=importlib.util.spec_from_file_location('guardian_v2_read_helpers',ROOT/'tools/repair-city-walk-geometry.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
sys.path.insert(0,str(ROOT/'assets/blender/city_r5'));sys.path.insert(0,str(ROOT/'assets/blender/city_r5/lib'))

CLOTH_IDS=['guardian_carved_robe_main','guardian_mantle_left','guardian_mantle_right',
           'guardian_robe_wind_sweep','guardian_front_fold_left','guardian_front_fold_right']
WATER_IDS=['fountain blue water','fountain second water','fountain upper water']+[
    'fountain arcing water jet'+('' if i==0 else f'.{i:03d}') for i in range(12)]
PROTECTED=[V1/'fountain_guardian_v1.blend',*[V1/f'fountain_guardian_lod{i}.glb' for i in range(3)],
           CITY1/'reference_city_guardian_review_v1.blend',CITY1/'city-source.glb',CITY1/'city-runtime.glb',
           CITY1/'city-runtime.meshopt.glb',ROOT/'assets/models/reference-city/r5/active-revision.json']

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

before_files={str(p.relative_to(ROOT)):sha(p) for p in PROTECTED if p.exists()}
def guarded_files():return {path:sha(ROOT/path)==digest for path,digest in before_files.items()}
def bounds(points):return {'min':np.min(points,axis=0).tolist(),'max':np.max(points,axis=0).tolist()}

def atomic_json(path,record):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(record,indent=2)+'\n',encoding='utf8');temp.replace(path)

def profile_value(z,column):
    keys=[(.18,1.14,.75),(.75,1.13,.74),(1.50,1.05,.70),(2.50,.88,.57),
          (3.50,.72,.44),(3.95,.55,.36),(4.50,.71,.44),(5.00,.74,.38),(5.37,.79,.34)]
    for i,(a,b) in enumerate(zip(keys,keys[1:])):
        if a[0]<=z<=b[0]:
            t=(z-a[0])/(b[0]-a[0]);p=keys[max(0,i-1)][column];q=a[column];r=b[column];s=keys[min(len(keys)-1,i+2)][column]
            return .5*((2*q)+(-p+r)*t+(2*p-5*q+4*r-s)*t*t+(-p+3*q-3*r+s)*t*t*t)
    return keys[-1][column]

def continuous_robe(material,collection,parent=None):
    # One closed solid loft. It has broad asymmetric billows, no independent
    # ribbons and no thin inward-facing duplicate shell inside the folds.
    rings=25;around=48;verts=[];faces=[];loop_uv=[]
    for row in range(rings):
        t=row/(rings-1);z=.18+t*5.19;rx=profile_value(z,1);ry=profile_value(z,2)
        for col in range(around):
            theta=col/around*math.tau;cs=math.cos(theta);sn=math.sin(theta)
            lower=max(0,min(1,(3.95-z)/3.2))
            # Controlled full-width folds remain readable at gameplay distance.
            fold=.065*math.cos(theta*7+z*.38)*lower**.45
            secondary=.012*math.cos(theta*14-z*.22)*lower
            side_right=max(0,cs)**8;side_left=max(0,-cs)**8
            right_billow=(1.31*math.exp(-((z-1.90)/.79)**2)+.53*math.exp(-((z-3.48)/.92)**2))*side_right
            left_billow=.57*math.exp(-((z-3.40)/1.12)**2)*side_left
            extended=rx+fold+secondary+right_billow+left_billow
            front=max(0,-sn)
            neckline=.31*front**12*max(0,(t-.86)/.14)
            verts.append((extended*cs,(ry+.68*fold)*sn,z-neckline))
    for row in range(rings-1):
        for col in range(around):
            nxt=(col+1)%around;a=row*around+col;b=row*around+nxt
            faces.append((a,b,b+around,a+around))
            loop_uv.append([(col/around,row/(rings-1)),((col+1)/around,row/(rings-1)),
                            ((col+1)/around,(row+1)/(rings-1)),(col/around,(row+1)/(rings-1))])
    faces.append(tuple(range(around-1,-1,-1)))
    faces.append(tuple((rings-1)*around+i for i in range(around)))
    for face in faces[-2:]:
        points=np.array([verts[i] for i in face]);lo=points.min(0);hi=points.max(0)
        loop_uv.append([((p[0]-lo[0])/max(1e-9,hi[0]-lo[0]),(p[1]-lo[1])/max(1e-9,hi[1]-lo[1])) for p in points])
    mesh=bpy.data.meshes.new('guardian_continuous_robe_v2 geometry');mesh.from_pydata(verts,[],faces);mesh.update()
    uv=mesh.uv_layers.new(name='UVMap')
    for poly,values in zip(mesh.polygons,loop_uv):
        poly.use_smooth=len(poly.vertices)==4
        for loop,value in zip(poly.loop_indices,values):uv.data[loop].uv=value
    bm=bmesh.new();bm.from_mesh(mesh);closed=all(e.is_manifold for e in bm.edges);volume=bm.calc_volume(signed=True)
    if volume<0:bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(mesh);volume=-volume
    bm.free()
    if not closed or volume<=0:raise RuntimeError('Continuous robe is not a closed positive-volume mesh.')
    ob=bpy.data.objects.new('guardian_continuous_robe_v2',mesh);collection.objects.link(ob);mesh.materials.append(material);ob.parent=parent
    ob['form_contract']='Closed continuous cloth mass with seven broad folds and integrated wind billows; no separate ribbon panels.'
    return ob,{'closed_manifold':closed,'signed_volume_m3':volume,'triangles':sum(len(p.vertices)-2 for p in mesh.polygons),'bounds':bounds(verts)}

def world_bvh(ob):
    points=[ob.matrix_world@v.co for v in ob.data.vertices];ob.data.calc_loop_triangles()
    return BVHTree.FromPolygons(points,[tuple(t.vertices) for t in ob.data.loop_triangles],all_triangles=True),bounds(points)

def components(mesh):
    parents=list(range(len(mesh.vertices)))
    def find(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parents[b]=a
    for edge in mesh.edges:union(*edge.vertices)
    welded={}
    for vertex in mesh.vertices:
        key=tuple(round(v,5) for v in vertex.co)
        if key in welded:union(vertex.index,welded[key])
        else:welded[key]=vertex.index
    out=defaultdict(list)
    for vertex in mesh.vertices:out[find(vertex.index)].append(vertex.index)
    return list(out.values())

def retain_mesh_without_cloth(ob,refs,lod):
    mesh=ob.data;removed=set();matches=[]
    for ids in components(mesh):
        points=[ob.matrix_world@mesh.vertices[i].co for i in ids];bb=bounds(points)
        if bb['min'][2]>=3.2 or bb['max'][2]-bb['min'][2]<=1.8:continue
        sample=[points[n] for n in sorted({0,len(points)//5,len(points)*2//5,len(points)*3//5,len(points)*4//5,len(points)-1})]
        ranked=[]
        for name,(tree,reference_bounds) in refs.items():
            bound_error=max(abs(bb[k][axis]-reference_bounds[k][axis]) for k in ['min','max'] for axis in range(3))
            distances=[tree.find_nearest(p)[3] for p in sample]
            ranked.append((bound_error+sum(distances)/len(distances),name,bound_error,max(distances)))
        ranked.sort();score,name,bound_error,distance=ranked[0]
        if bound_error>.30 or distance>.23:raise RuntimeError(f'Unproven cloth component in LOD{lod}: {bb}')
        if any(r['source_id']==name for r in matches):raise RuntimeError('Ambiguous duplicate cloth identity.')
        matches.append({'source_id':name,'bounds':bb,'vertices':len(ids),'source_bounds_error_m':bound_error,'sample_surface_gap_max_m':distance})
        removed.update(ids)
    if lod==0 and len(matches)!=6:raise RuntimeError(f'Expected six proved cloth components, got{len(matches)}.')
    polygons=[p for p in mesh.polygons if not all(i in removed for i in p.vertices)]
    kept=sorted({i for p in polygons for i in p.vertices});remap={old:new for new,old in enumerate(kept)}
    positions=[tuple(mesh.vertices[i].co) for i in kept]
    uv_data=[[(tuple(layer.data[i].uv)) for p in polygons for i in p.loop_indices] for layer in mesh.uv_layers]
    normals=[tuple(mesh.corner_normals[i].vector) for p in polygons for i in p.loop_indices]
    rebuilt=bpy.data.meshes.new(f'guardian_noncloth_preserved_lod{lod}')
    rebuilt.from_pydata(positions,[],[[remap[i] for i in p.vertices] for p in polygons]);rebuilt.update()
    for layer,values in zip(mesh.uv_layers,uv_data):
        target=rebuilt.uv_layers.new(name=layer.name)
        for i,value in enumerate(values):target.data[i].uv=value
    for p,old in zip(rebuilt.polygons,polygons):p.use_smooth=old.use_smooth
    rebuilt.normals_split_custom_set(normals)
    rebuilt.materials.append(mesh.materials[0]);ob.data=rebuilt
    if any(tuple(rebuilt.vertices[remap[i]].co)!=tuple(mesh.vertices[i].co) for i in kept):raise RuntimeError('Non-cloth positions changed.')
    return {'lod':lod,'removed_components':matches,'preserved_vertex_count':len(kept),
            'preserved_triangle_count':sum(len(p.vertices)-2 for p in rebuilt.polygons),
            'preserved_positions_exact':True,'preserved_uv_loop_values_exact':True,'source_corner_normals_copied':True}

def export_full_source_v2(master):
    """Source wrapper with the intentional missing static water_foam bucket."""
    import citykit as ck
    textures=helper.reload_textures_absolute()
    presentation=bpy.data.collections.get('Presentation only');excluded=set(presentation.all_objects) if presentation else set()
    objects=[o for o in bpy.context.scene.objects if o not in excluded]
    meshes=[o for o in objects if o.type=='MESH']
    prefixes=('anim_','fx_','emit_','light_')
    hooks=[o for o in objects if o.name.startswith(prefixes)]
    static=[o for o in meshes if not o.name.startswith(prefixes)]
    materials={o.data.materials[0].name for o in static}
    if len(materials)!=42 or 'water_foam' in materials or len(hooks)!=34:
        raise RuntimeError(f'Unexpected v2 static/hook schema: {len(materials)}/{len(hooks)}')
    cart=bpy.data.objects.get('market stall 1-1 Quaternius CC0 stall cart')
    if cart is None:raise RuntimeError('Missing preserved featured cart.')
    ck.normalize_imported_gltf_prop_attributes(cart);bpy.context.view_layer.update()
    original={o.name:o.matrix_world.copy() for o in static}
    for ob in static:
        if ob.parent and ob.parent.type=='EMPTY':
            world=ob.matrix_world.copy();ob.parent=None;ob.matrix_world=world
    bpy.context.view_layer.update()
    error=max(abs(original[o.name][r][c]-o.matrix_world[r][c]) for o in static for r in range(4) for c in range(4))
    if error>1e-4:raise RuntimeError('World transforms changed during v2 source detachment.')
    triangles=ck.triangle_count(meshes);merged,_=ck.merge_by_material(static,'City')
    if len(merged)!=42:raise RuntimeError('V2 merge schema changed unexpectedly.')
    path=CITY/'city-source.glb';ck.export_glb(merged+hooks,path)
    blob=path.read_bytes();length=struct.unpack_from('<I',blob,12)[0];doc=json.loads(blob[20:20+length])
    actual=sum(doc['accessors'][p.get('indices',p['attributes']['POSITION'])]['count']//3 for m in doc['meshes'] for p in m['primitives'])
    if actual!=triangles:raise RuntimeError('Full v2 source lost or added triangles during export.')
    result={'schema':'xexoria.guardian-v2-full-source-export/1','master_sha256':sha(master),
            'source_master_saved':False,'original_source_overwritten':False,'max_world_matrix_error':error,
            'texture_images_refreshed':textures,'candidate':{'path':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size,
            'triangles':actual,'meshes':len(doc['meshes']),'materials':len(doc['materials']),'images':len(doc.get('images',[])),
            'static_material_groups':len(merged),'runtime_hooks':len(hooks)},
            'intentional_schema_change':'Removed sole static water_foam bucket with exact twelve obsolete arcing-jet IDs; dynamic FX hooks/materials retained.'}
    atomic_json(CITY/'city-source.stats.json',result)
    return result

if A.mode=='form':
    if (FORM/'fountain_guardian_v2.blend').exists():raise RuntimeError('Do not overwrite a reviewed v2 form.')
    FORM.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(V1/'fountain_guardian_v1.blend'))
    before={o.name:helper.signature(o) for o in bpy.context.scene.objects}
    refs={name:world_bvh(bpy.data.objects[name]) for name in CLOTH_IDS}
    for name in CLOTH_IDS:bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
    collection=bpy.data.collections['Guardian_v1_editable_form'];parent=bpy.data.objects['fountain_guardian_candidate_root']
    robe,robe_record=continuous_robe(bpy.data.materials['marble_statue'],collection,parent)
    if any(helper.signature(bpy.data.objects[name])!=signature for name,signature in before.items() if name not in CLOTH_IDS):
        raise RuntimeError('A non-clothing editable form changed.')
    bpy.ops.wm.save_as_mainfile(filepath=str(FORM/'fountain_guardian_v2.blend'),relative_remap=False,copy=True)
    record={'schema':'xexoria.guardian-cloth-v2/1','status':'GEOMETRY_CANDIDATE_PENDING_NATIVE_REVIEW',
        'source_form_sha256':before_files[str((V1/'fountain_guardian_v1.blend').relative_to(ROOT))],
        'reference':'docs/ui/concepts/fountain-guardian-v1-20261001.png','native_problem_observed':'planning/evidence/fountain-native-20261001-after-close.png',
        'source_cloth_ids_replaced':CLOTH_IDS,'continuous_robe':robe_record,'nonclothing_editable_signatures_unchanged':True,
        'editable':{'path':str((FORM/'fountain_guardian_v2.blend').relative_to(ROOT)),'sha256':sha(FORM/'fountain_guardian_v2.blend')},'lods':[]}
    for lod in range(3):
        bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(V1/f'fountain_guardian_lod{lod}.glb'))
        marble=next(o for o in bpy.context.scene.objects if o.type=='MESH' and o.data.materials[0].name=='marble_statue')
        preservation=retain_mesh_without_cloth(marble,refs,lod);marble.name=f'guardian_lod{lod}_marble_preserved_noncloth_v2'
        robe,stats=continuous_robe(bpy.data.materials['marble_statue'],bpy.context.scene.collection)
        robe.name=f'guardian_lod{lod}_continuous_robe_v2'
        if lod:
            modifier=robe.modifiers.new('cloth_lod_only','DECIMATE');modifier.ratio=.48 if lod==1 else .22
            bpy.context.view_layer.objects.active=robe;robe.select_set(True);bpy.ops.object.modifier_apply(modifier=modifier.name)
        meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
        path=FORM/f'fountain_guardian_lod{lod}.glb'
        bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_animations=False,export_skins=False,export_extras=True)
        triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in meshes)
        record['lods'].append({'lod':lod,'path':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size,'triangles':triangles,'mesh_count':len(meshes),'preservation':preservation})
    record['v1_file_guards']=guarded_files();record['no_material_or_image_pass']=True;record['renders_performed']=False
    if not all(record['v1_file_guards'].values()):raise RuntimeError('A v1 input changed.')
    atomic_json(FORM/'asset-manifest.json',record);atomic_json(EVIDENCE,record)
    print('GUARDIAN_CLOTH_V2_FORM',json.dumps({'robe':robe_record,'lods':[{'lod':r['lod'],'triangles':r['triangles'],'bytes':r['bytes']} for r in record['lods']],'v1_unchanged':True}))
elif A.mode=='city':
    CITY.mkdir(parents=True,exist_ok=True);target=CITY/'reference_city_guardian_review_v2.blend'
    if target.exists():raise RuntimeError('Do not overwrite a reviewed v2 city.')
    form_record=json.loads((FORM/'asset-manifest.json').read_text());form=FORM/'fountain_guardian_lod0.glb'
    if sha(form)!=form_record['lods'][0]['sha256']:raise RuntimeError('V2 form hash changed.')
    bpy.ops.wm.open_mainfile(filepath=str(CITY1/'reference_city_guardian_review_v1.blend'))
    before={o.name:helper.signature(o) for o in bpy.context.scene.objects};root=bpy.data.objects['kit_plaza_fountain']
    for name in WATER_IDS:
        ob=bpy.data.objects.get(name)
        if ob is None or ob.type!='MESH' or ob.parent is not root:raise RuntimeError(f'Exact static water identity mismatch: {name}')
        bpy.data.objects.remove(ob,do_unlink=True)
    old_marble=bpy.data.objects['fountain guardian approved form marble'];bpy.data.objects.remove(old_marble,do_unlink=True)
    materials={name:bpy.data.materials[name] for name in ['marble_statue','metal_gold','magic_blue']}
    prior=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(form));imported=set(bpy.context.scene.objects)-prior
    added=[]
    for ob in list(imported):
        if ob.type!='MESH' or not ob.data.materials[0].name.startswith('marble_statue'):continue
        desired=root.matrix_world@Matrix.Translation((0,0,7.4))@ob.matrix_world.copy()
        ob.data.materials.clear();ob.data.materials.append(materials['marble_statue'])
        ob.parent=root;ob.matrix_parent_inverse=Matrix.Identity(4);ob.matrix_basis=root.matrix_world.inverted()@desired
        ob.name='fountain guardian continuous robe v2' if 'continuous_robe' in ob.name else 'fountain guardian preserved anatomy wings v2'
        color=ob.data.color_attributes.new(name='Col',type='BYTE_COLOR',domain='CORNER');color.data.foreach_set('color',np.ones(len(color.data)*4,dtype=np.float32));ob.data.color_attributes.active_color=color
        added.append(ob.name)
    for ob in imported:
        if ob.name not in added:bpy.data.objects.remove(ob,do_unlink=True)
    if len(added)!=2:raise RuntimeError('Expected preserved non-cloth marble and one continuous robe.')
    bpy.context.view_layer.update();changed=set(WATER_IDS)|{'fountain guardian approved form marble'}
    unrelated=[name for name in before if name not in changed]
    mismatches=[name for name in unrelated if bpy.data.objects.get(name) is None or helper.signature(bpy.data.objects[name])!=before[name]]
    if mismatches:raise RuntimeError(f'Unrelated v1 geometry changed: {mismatches[:8]}')
    textures=helper.reload_textures_absolute();bpy.ops.wm.save_as_mainfile(filepath=str(target),relative_remap=False,copy=True)
    record={'schema':'xexoria.guardian-city-v2/1','status':'GEOMETRY_CANDIDATE_PENDING_NATIVE_REVIEW','form':form_record,
        'source_city_v1':{'path':str((CITY1/'reference_city_guardian_review_v1.blend').relative_to(ROOT)),'sha256':before_files[str((CITY1/'reference_city_guardian_review_v1.blend').relative_to(ROOT))]},
        'candidate_master':{'path':str(target.relative_to(ROOT)),'sha256':sha(target)},'removed_exact_static_water_ids':WATER_IDS,
        'replaced_city_marble_id':'fountain guardian approved form marble','added_marble_ids':added,'unrelated_v1_objects_verified':len(unrelated),
        'original_crystal_gold_inlays_hooks_bowls_stem_outlets_lamps_unchanged':True,'collider_support_data_written':False,
        'textures_reloaded_existing_only':textures,'no_material_or_image_pass':True,'renders_performed':False,'v1_file_guards':guarded_files(),
        'limits':['Live water must replace removed static references; no live-water shader/code changes here.','Fresh native close/player/side comparison required; coherent mesh does not establish approved-reference quality.','Existing production900k budget remains separately measured; no active promotion.']}
    if not all(record['v1_file_guards'].values()):raise RuntimeError('A v1 input changed during v2 city build.')
    atomic_json(CITY/'geometry-repair-receipt.json',record);atomic_json(EVIDENCE,record)
    print('GUARDIAN_CLOTH_V2_CITY',json.dumps({'master_sha256':record['candidate_master']['sha256'],'removed_water':len(WATER_IDS),'unrelated_verified':len(unrelated),'v1_unchanged':True}))
else:
    record=json.loads((CITY/'geometry-repair-receipt.json').read_text());master=ROOT/record['candidate_master']['path']
    if sha(master)!=record['candidate_master']['sha256']:raise RuntimeError('V2 city changed after geometry validation.')
    bpy.ops.wm.open_mainfile(filepath=str(master))
    if A.mode=='source':stats=export_full_source_v2(master)
    else:
        import export_runtime_r5 as exporter
        exporter.MASTER=master;exporter.EXPECTED_STATIC_MATERIAL_GROUPS=42
        exporter.refresh_texture_images=helper.reload_textures_absolute
        args=['--candidate',str(CITY/'city-runtime.glb'),'--stats',str(CITY/'city-runtime.stats.json'),'--limit','930000']
        sys.argv=[sys.argv[0],'--',*args];exporter.main()
        stats=json.loads((CITY/'city-runtime.stats.json').read_text())
    record[A.mode+'_export']=stats
    if A.mode=='runtime':record['production900k_pass']=stats['candidate']['glb_accessor_triangles']<=900000
    record['v1_file_guards']=guarded_files()
    if not all(record['v1_file_guards'].values()):raise RuntimeError('A v1 input changed during export.')
    atomic_json(CITY/'geometry-repair-receipt.json',record);atomic_json(EVIDENCE,record)
    print('GUARDIAN_CLOTH_V2_EXPORT',json.dumps({'mode':A.mode,'candidate':stats['candidate'],'v1_unchanged':True}))
