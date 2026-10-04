"""Versioned S04 guardian/lamp/nozzle geometry review, never active promotion.

Only its new candidate directory and JSON evidence are writable outputs.
No Blender renders, texture bakes, map-wide material pass or collider writes.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/models/reference-city/r5/fountain-guardian-review-candidate'
EVIDENCE=ROOT/'planning/evidence/fountain-guardian-city-review-20261001.json'
ACTIVE=ROOT/'assets/models/reference-city/r5/active-revision.json'
AUDIT=ROOT/'planning/evidence/fountain-s04-source-identities-20261001.json'
FORM=ROOT/'assets/models/reference-city/r5/art-candidates/fountain-guardian-v1/fountain_guardian_lod0.glb'
FORM_SHA='95495b9ae41057482ebad8b428036c9d94b04d4e9ca868b82cd498225c92a1c8'
CANDIDATE=OUT/'reference_city_guardian_review_v1.blend'
REVIEW_LIMIT=930000

P=argparse.ArgumentParser();P.add_argument('--mode',choices=['build','source','runtime'],required=True)
A=P.parse_args(sys.argv[sys.argv.index('--')+1:])
sys.path.insert(0,str(ROOT/'assets/blender/city_r5/lib'))
sys.path.insert(0,str(ROOT/'assets/blender/city_r5'))
import citykit as ck

spec=importlib.util.spec_from_file_location('guardian_review_existing_helpers',ROOT/'tools/repair-city-walk-geometry.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

active=json.loads(ACTIVE.read_text(encoding='utf8'))
selected_source=ROOT/active['files']['city-source.glb']['path']
master_entry=next(row for name,row in active['files'].items() if name.endswith('.blend'))
selected_master=ROOT/master_entry['path']
protected_paths=[ACTIVE,selected_source,selected_master,ROOT/active['files']['city-traversal-v1.json']['path'],
                 ROOT/'assets/models/reference-city/r5/reference_city.blend',ROOT/'assets/models/reference-city/r5/city-source.glb',ROOT/'assets/models/reference-city/r5/city-runtime.glb']
protected_before={str(p.relative_to(ROOT)):sha(p) for p in protected_paths if p.is_file()}
if sha(selected_source)!=active['files']['city-source.glb']['sha256'] or sha(selected_master)!=master_entry['sha256']:
    raise RuntimeError('Active source/master hash mismatch.')

def unchanged_files():
    return {name:sha(ROOT/name)==digest for name,digest in protected_before.items()}

def object_bounds(ob):
    points=np.array([tuple(ob.matrix_world@v.co) for v in ob.data.vertices])
    return {'min':points.min(0).tolist(),'max':points.max(0).tolist()}

def own_neutral_schema(ob):
    if not ob.data.uv_layers:raise RuntimeError(f'New geometry has no UVs: {ob.name}')
    color=ob.data.color_attributes.get('Col') or ob.data.color_attributes.new(name='Col',type='BYTE_COLOR',domain='CORNER')
    color.data.foreach_set('color',np.ones(len(color.data)*4,dtype=np.float32))
    ob.data.color_attributes.active_color=color
    ob.data.validate(clean_customdata=False)

def nozzle(name,radius,height,angle,material,owner):
    direction=Vector((math.cos(angle),math.sin(angle),0))
    side=Vector((-math.sin(angle),math.cos(angle),0));up=Vector((0,0,1))
    segments=12;verts=[];faces=[];uv=[]
    # Open bore through the bronze barrel; both end faces are annular.
    profiles=[(-.28,.135),(-.12,.120),(0,.140),(0,.065),(-.12,.060),(-.28,.065)]
    for row,(distance,r) in enumerate(profiles):
        center=direction*(radius+distance)+up*height
        for col in range(segments):
            theta=col/segments*math.tau
            verts.append(tuple(center+side*(r*math.cos(theta))+up*(r*math.sin(theta))))
            uv.append((col/segments,row/(len(profiles)-1)))
    for row in range(len(profiles)):
        next_row=(row+1)%len(profiles)
        for col in range(segments):
            a=row*segments+col;b=row*segments+(col+1)%segments
            c=next_row*segments+(col+1)%segments;d=next_row*segments+col
            faces.append((a,b,c,d))
    mesh=bpy.data.meshes.new(name+' geometry');mesh.from_pydata(verts,[],faces);mesh.update()
    bm=bmesh.new();bm.from_mesh(mesh)
    if bm.calc_volume(signed=True)<0:bmesh.ops.reverse_faces(bm,faces=list(bm.faces))
    bm.to_mesh(mesh);bm.free();mesh.uv_layers.new(name='UVMap')
    for polygon in mesh.polygons:
        polygon.use_smooth=True
        for loop in polygon.loop_indices:mesh.uv_layers.active.data[loop].uv=uv[mesh.loops[loop].vertex_index]
    ob=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(ob)
    mesh.materials.append(material);ob.parent=owner;ob.matrix_parent_inverse=Matrix.Identity(4)
    own_neutral_schema(ob)
    ob['outlet_source_local_xyz']=[radius*math.cos(angle),radius*math.sin(angle),height]
    ob['geometry_role']='Non-walked hollow bowl outlet; no fluid/physics/collider behavior added.'
    return ob

OUT.mkdir(parents=True,exist_ok=True)
if A.mode=='build':
    if CANDIDATE.exists():raise RuntimeError('Candidate already exists; preserve reviewed/finishing work and use a new version.')
    audit=json.loads(AUDIT.read_text(encoding='utf8'))
    if audit['selected_source']['sha256']!=sha(selected_source):raise RuntimeError('Identity audit belongs to a different source revision.')
    if sha(FORM)!=FORM_SHA:raise RuntimeError('Approved form candidate hash changed.')
    bpy.ops.wm.open_mainfile(filepath=str(selected_master))
    before={o.name:helper.signature(o) for o in bpy.context.scene.objects}
    root=bpy.data.objects['kit_plaza_fountain']
    protected_ids=[name for name in audit['protected_keep_ids'] if name!='fountain guardian crown crystal']
    protected_object_signatures={name:helper.signature(bpy.data.objects[name]) for name in protected_ids}
    old_crystal=bpy.data.objects['fountain guardian crown crystal']
    old_crystal_record={'name':old_crystal.name,'bounds_source_blender':object_bounds(old_crystal),'signature':helper.signature(old_crystal)}
    removed=list(audit['guardian_body_only_replacement_ids'])+['fountain guardian crown crystal']
    for name in removed:
        ob=bpy.data.objects.get(name)
        if ob is None:raise RuntimeError(f'Missing exact removal ID: {name}')
        cursor=ob;belongs=False
        while cursor:
            belongs|=cursor is root;cursor=cursor.parent
        if not belongs:raise RuntimeError(f'Removal ID is not owned by fountain root: {name}')
        bpy.data.objects.remove(ob,do_unlink=True)

    material_lookup={name:bpy.data.materials[name] for name in ['marble_statue','metal_gold','magic_blue']}
    prior=set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(FORM))
    imported=set(bpy.context.scene.objects)-prior
    new_meshes=[o for o in imported if o.type=='MESH']
    if len(new_meshes)!=4:raise RuntimeError('Expected exactly four form meshes.')
    existing_hook=bpy.data.objects['anim_crystal_fountain']
    mount=Matrix.Translation((0,0,7.4))
    added=[]
    for ob in new_meshes:
        is_crystal='crystal_animated_hook' in ob.name
        desired=root.matrix_world@mount@ob.matrix_world.copy()
        for slot in ob.material_slots:
            current=slot.material.name
            match=next((name for name in material_lookup if current==name or current.startswith(name+'.')),None)
            if match is None:raise RuntimeError(f'Unexpected form material: {current}')
            slot.material=material_lookup[match]
        ob.parent=existing_hook if is_crystal else root;ob.matrix_parent_inverse=Matrix.Identity(4)
        ob.matrix_basis=ob.parent.matrix_world.inverted()@desired
        if is_crystal:ob.name='fountain guardian crown crystal'
        elif ob.data.materials[0].name=='marble_statue':ob.name='fountain guardian approved form marble'
        elif ob.data.materials[0].name=='metal_gold':ob.name='fountain guardian approved form gold'
        else:ob.name='fountain guardian approved form fixed inlays'
        own_neutral_schema(ob);added.append(ob.name)
    for ob in imported:
        if ob.type!='MESH':bpy.data.objects.remove(ob,do_unlink=True)
    bpy.context.view_layer.update()
    if bpy.data.objects.get('anim_crystal_fountain.001'):raise RuntimeError('Duplicate crystal animation hook remained after import.')

    lamp_rows=[];moved=set()
    for row in audit['bridge_lamp_assemblies']:
        if row['status']!='PROVEN_CONSTRUCTION_PAIR':raise RuntimeError('Do not repair an unproven lamp assembly.')
        finial=bpy.data.objects[row['finial_id']];roof=bpy.data.objects[row['roof_id']];pedestal=bpy.data.objects[row['pedestal_id']];owner=bpy.data.objects[row['owner_root_id']]
        if roof.parent is not owner or pedestal.parent is not owner or finial.parent is not None:
            raise RuntimeError('Lamp ownership changed since audit; refuse guessed repair.')
        pedestal_signature=helper.signature(pedestal)
        rise=row['arch_rise_from_pedestal_m']
        roof.matrix_basis=Matrix.Translation((0,0,rise))@roof.matrix_basis
        finial.parent=owner;finial.matrix_parent_inverse=Matrix.Identity(4)
        finial.matrix_basis=Matrix.Translation((0,0,rise))@finial.matrix_basis
        bpy.context.view_layer.update()
        if helper.signature(pedestal)!=pedestal_signature:raise RuntimeError('Lamp pedestal moved unexpectedly.')
        expected=Matrix(row['expected_finial_matrix_blender'])
        error=max(abs(expected[r][c]-finial.matrix_world[r][c]) for r in range(4) for c in range(4))
        if error>1e-5:raise RuntimeError('Lamp world transform differs from proved repair.')
        moved.update([roof.name,finial.name]);lamp_rows.append({**row,'actual_matrix_error':error,'pedestal_preserved':True})

    outlets=[]
    for tier,radius,height in [('upper',3.1,6.85),('lower',6.1,4.35)]:
        for i in range(12):
            ob=nozzle(f'fountain outlet {tier} nozzle {i:02d}',radius,height,i*math.tau/12,material_lookup['metal_gold'],root)
            outlets.append({'id':ob.name,'tier':tier,'angle_rad':i*math.tau/12,'outlet_source_local_xyz':list(ob['outlet_source_local_xyz'])})
            added.append(ob.name)
    bpy.context.view_layer.update()
    for name,signature in protected_object_signatures.items():
        if helper.signature(bpy.data.objects[name])!=signature:raise RuntimeError(f'Protected fountain component changed: {name}')
    altered=set(removed)|moved
    unrelated=[name for name in before if name not in altered]
    changed_unrelated=[name for name in unrelated if bpy.data.objects.get(name) is None or helper.signature(bpy.data.objects[name])!=before[name]]
    if changed_unrelated:raise RuntimeError(f'Unrelated source geometry changed: {changed_unrelated[:10]}')
    textures=helper.reload_textures_absolute()
    bpy.ops.wm.save_as_mainfile(filepath=str(CANDIDATE),check_existing=False,relative_remap=False,copy=True)
    record={'schema':'xexoria.fountain-guardian-city-review/1','status':'VERSIONED_GEOMETRY_REVIEW_ONLY_NOT_PROMOTED',
        'selected_revision':active['revision'],'selected_source':{'path':str(selected_source.relative_to(ROOT)),'sha256':sha(selected_source)},
        'selected_master':{'path':str(selected_master.relative_to(ROOT)),'sha256':sha(selected_master)},
        'approved_form':{'path':str(FORM.relative_to(ROOT)),'sha256':FORM_SHA},
        'candidate_master':{'path':str(CANDIDATE.relative_to(ROOT)),'sha256':sha(CANDIDATE)},
        'removed_exact_source_ids':removed,'added_mesh_ids':added,'lamp_assembly_repairs':lamp_rows,'nozzle_outlets':outlets,
        'crystal_ownership':{'single_owner_id':'fountain guardian crown crystal','preserved_hook_id':'anim_crystal_fountain',
            'original_crystal':old_crystal_record,'new_bounds_source_blender':object_bounds(bpy.data.objects['fountain guardian crown crystal']),
            'choice':'Approved form crystal replaces original crystal geometry under the original unchanged hook. Imported duplicate hook is removed; fixed robe inlays stay under the fountain root.',
            'grasp':'Body/cage/crystal preserve their approved-form relative transforms through one7.4m mounting transform. Existing hook origin remains unchanged; runtime animation pivot/close grasp still needs review.'},
        'protected_fountain_ids_unchanged':protected_ids,'unrelated_objects_verified':len(unrelated),
        'textures_reloaded_existing_only':textures,'stable_material_slots':['marble_statue','metal_gold','magic_blue'],
        'protected_file_checks':unchanged_files(),'no_colliders_or_support_data_written':True,'renders_performed':False,
        'runtime_review_limit':REVIEW_LIMIT,'production_runtime_triangle_budget':900000,
        'limits':['No native before/after capture yet; geometry export is not visual acceptance.',
                  'Runtime review can exceed production900k budget; report separately rather than decimating unrelated geometry.',
                  'Bridge pedestal coping contact was not redesigned; source pedestal transforms remain unchanged.',
                  'Existing static source jets are preserved; runtime owner must avoid duplication with live jets.',
                  'No texture/material finishing or active city revision promotion.']}
    if not all(record['protected_file_checks'].values()):raise RuntimeError('Protected source file changed during candidate build.')
    (OUT/'geometry-repair-receipt.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8');EVIDENCE.write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    print('GUARDIAN_CITY_BUILD',json.dumps({'candidate_sha256':record['candidate_master']['sha256'],'removed':len(removed),'added':len(added),'lamps':len(lamp_rows),'unrelated_verified':len(unrelated),'protected_unchanged':all(record['protected_file_checks'].values())}))
else:
    record=json.loads((OUT/'geometry-repair-receipt.json').read_text(encoding='utf8'))
    if sha(CANDIDATE)!=record['candidate_master']['sha256']:raise RuntimeError('Candidate changed after geometry verification.')
    bpy.ops.wm.open_mainfile(filepath=str(CANDIDATE))
    if A.mode=='source':import export_source_r5 as exporter
    else:import export_runtime_r5 as exporter
    exporter.MASTER=CANDIDATE
    if A.mode=='source':exporter.SOURCE=selected_source
    exporter.refresh_texture_images=helper.reload_textures_absolute
    stats=OUT/f'city-{A.mode}.stats.json'
    args=['--candidate',str(OUT/f'city-{A.mode}.glb'),'--stats',str(stats)]
    if A.mode=='runtime':args+=['--limit',str(REVIEW_LIMIT)]
    sys.argv=[sys.argv[0],'--',*args]
    exporter.main()
    result=json.loads(stats.read_text(encoding='utf8'))
    record[A.mode+'_export']=result
    if A.mode=='runtime':
        triangles=result['candidate']['glb_accessor_triangles']
        record['production_runtime_triangle_budget_pass']=triangles<=900000
        record['runtime_triangle_delta_from_selected']=triangles-899685
    record['protected_file_checks']=unchanged_files()
    if not all(record['protected_file_checks'].values()):raise RuntimeError('Protected source changed during review export.')
    (OUT/'geometry-repair-receipt.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8');EVIDENCE.write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    print('GUARDIAN_CITY_EXPORT',json.dumps({'mode':A.mode,'candidate':result['candidate'],'production900k_pass':record.get('production_runtime_triangle_budget_pass'),'protected_unchanged':True}))
