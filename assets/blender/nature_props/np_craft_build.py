"""Craft/flora source build, shared helper export, receipt and deterministic proof."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
import bpy
import numpy as np

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import np_lib as L
import kit_flora as F
from np_craft_specs import assets
from np_craft_geometry import construct
EVID=L.EVIDENCE/'craft';CACHE=L.CACHE/'craft-v1'

def backup(path):
    path=Path(path)
    if not path.exists():return
    dest=EVID/'backup';dest.mkdir(parents=True,exist_ok=True)
    digest=L.sha256_file(path);out=dest/(path.name+'.'+digest[:12]+'.orig')
    if not out.exists():
        shutil.copy2(path,out)
        with open(dest/'SHA256SUMS.txt','a',encoding='utf8') as f:f.write(digest+'  '+str(path)+'\n')

def hashshape(ob):
    h=hashlib.sha256(L.verts(ob.data).astype('<f4').tobytes())
    for p in L.faces_list(ob.data):h.update(np.asarray(p,dtype='<u4').tobytes())
    for uv in ob.data.uv_layers:h.update(L.uv_array(ob,uv.name).astype('<f4').tobytes())
    return h.hexdigest()

def build(spec,revision=1,proof=False):
    spec={**spec,'params':{**spec['params'],'art_revision':revision}}
    started=time.monotonic();L.reset();L.setup_cycles(16,6)
    family=spec.get('family','flora');out=L.OUT_MODELS/family;tex=out/'textures-source'
    for d in (out/'source',out/'colliders',EVID/'receipts',CACHE):d.mkdir(parents=True,exist_ok=True)
    # Interrupted builds cannot leave a prior SOURCE_VALIDATED receipt over new partial bytes.
    receipt_path=EVID/'receipts'/f'{spec["id"]}.json';backup(receipt_path)
    L.write_json(receipt_path,{**spec,'family':family,'revision':revision,'status':'BUILDING','source_files':[]})
    if family=='flora':
        lods=list(F.build_lods(spec).values());col=None;meta={'wind_uv2':{'x':'sway weight','y':'phase after exporter v flip','phase_expected':(spec['seed']*.137)%1}}
        mat=L.pbr_material('sm_flora_water_mat',tex/'sm_flora_water_albedo.png',tex/'sm_flora_water_normal.png',tex/'sm_flora_water_orm.png',alpha_clip=.5,double_sided=True,normal_strength=.30)
        profile='foliage';budget='bush_lod0';atlas='sm_flora_water'
        # np_lib's 1-LESS_THAN(alpha,.5) is the installed exporter's MASK pattern.
    else:
        lod0,col,meta=construct(spec,revision)
        if L.tri_count(lod0)>spec['lod0_tris']:
            tmp=L.decimate_to(lod0,int(spec['lod0_tris']*.96),name=spec['id']+'__lod0',tol=.01);L.delete([lod0]);lod0=tmp
        lods=[lod0]
        if spec['recipe'] in ('craft.well/1','craft.brazier/1'):
            mid,mid_col,_=construct(spec,revision,lod=1);L.delete([mid_col]);mid.name=spec['id']+'__lod1';lods.append(mid)
        else:
            mid=L.decimate_to(lod0,max(12,int(L.tri_count(lod0)*.50)),name=spec['id']+'__lod1',tol=.02)
            mid.data.validate(clean_customdata=False);mid.data.update();check=L.mesh_report(mid)
            if check['non_manifold_edges'] or check['zero_area_faces']:
                L.delete([mid]);mid,mid_col,_=construct(spec,revision,lod=1);L.delete([mid_col]);meta['lod1_structural_fallback']=True
            mid.name=spec['id']+'__lod1';lods.append(mid)
        far,far_col,_=construct(spec,revision,lod=2);L.delete([far_col]);far.name=spec['id']+'__lod2'
        if L.tri_count(far)>=L.tri_count(lods[1]):
            # Tiny closed props do not benefit from a more expensive structural far mesh.
            # Reuse the valid middle geometry where further collapse destroys their form.
            L.delete([far]);far=L.copy_object(lods[1],spec['id']+'__lod2');meta['lod2_reuses_lod1_geometry']=True
        lods.append(far)
        mat=L.pbr_material('sm_craft_mat',tex/'sm_craft_albedo.png',tex/'sm_craft_normal.png',tex/'sm_craft_orm.png',vertex_color='Col',normal_strength=.3)
        profile='prop';budget=spec['budget_class'];atlas='sm_craft'
    reports={};source=[];det=[]
    for i,ob in enumerate(lods):
        ob.name=spec['id']+f'__lod{i}';ob.data.name=ob.name+'_mesh';ob.data.materials.clear();ob.data.materials.append(mat)
        L.triangulate(ob);cleaned=ob.data.validate(clean_customdata=False);ob.data.update()
        report=L.mesh_report(ob);report['geometry_sha256']=hashshape(ob);report['mesh_validation_repaired']=bool(cleaned)
        if report['zero_area_faces']:raise ValueError(f'Zero area: {spec["id"]} {i}')
        if family=='craft' and report['non_manifold_edges']:raise ValueError(f'Non-manifold craft: {spec["id"]} {i}')
        if i==0 and report['triangles']>spec['lod0_tris']:raise ValueError('Budget exceeded '+spec['id'])
        reports[f'lod{i}']=report
        dest=out/'source'/f'{spec["id"]}_lod{i}.glb';backup(dest);backup(dest.with_suffix('.receipt.json'))
        rec=L.export_lod(ob,dest,profile=profile,budget_class=budget,texture_dir=out/'source'/'textures',
                         double_sided=[mat.name] if family=='flora' else [],vertex_color='NONE' if family=='flora' else 'MATERIAL',
                         notes=f'original procedural candidate; recipe={spec["recipe"]} seed={spec["seed"]} revision={revision}')
        if rec.get('status')!='PASS':raise ValueError('Export validation failed '+str(dest))
        source.append(str(dest.relative_to(L.REPO)))
        if proof and i==0:
            first=dest.read_bytes();again=out/'source'/f'{spec["id"]}_proof.glb'
            L.export_lod(ob,again,profile=profile,budget_class=budget,asset_id=dest.stem,texture_dir=out/'source'/'textures',
                         double_sided=[mat.name] if family=='flora' else [],vertex_color='NONE' if family=='flora' else 'MATERIAL',
                         notes=f'original procedural candidate; recipe={spec["recipe"]} seed={spec["seed"]} revision={revision}')
            # Separate rebuilt mesh proof is performed in the next build call, not this repeat-export check.
            det.append({'repeat_export_identical':first==again.read_bytes(),'first':hashlib.sha256(first).hexdigest(),'second':L.sha256_file(again)})
    if col:
        L.triangulate(col);reports['collider']=L.mesh_report(col)
        dest=out/'source'/f'{spec["id"]}_collider.glb';backup(dest);backup(dest.with_suffix('.receipt.json'))
        rr=L.export_lod(col,dest,profile='prop',budget_class='prop',materials='NONE',vertex_color='NONE',texture_dir=out/'source'/'textures',notes='opening-aware compound collider candidate')
        if rr.get('status')!='PASS':raise ValueError('Collider export failed')
        source.append(str(dest.relative_to(L.REPO)))
        collider={'class':'solid','compound':bool(meta.get('door_opening') or meta.get('walk_surface')),'metadata':meta,
                  'coordinate_space':'glTF local +Y up; runtime placement uses Babylon reflected X','pivot':[0,0,0]}
        backup(out/'colliders'/f'{spec["id"]}.json');L.write_json(out/'colliders'/f'{spec["id"]}.json',collider)
    for ob in lods[1:]+([col] if col else []):ob.hide_render=True;ob.hide_set(True)
    backup(CACHE/f'{spec["id"]}.blend');bpy.ops.wm.save_as_mainfile(filepath=str(CACHE/f'{spec["id"]}.blend'),compress=True)
    rec={**spec,'family':family,'atlas':atlas,'revision':revision,'source_files':source,'mesh':reports,'metadata':meta,
         'source_sha256':{f:L.sha256_file(L.REPO/f) for f in source},
         'recipe_sources_sha256':{f:L.sha256_file(HERE/f) for f in
            (['kit_flora.py','flora_layout.py','np_paint_flora.py','np_craft_build.py'] if family=='flora' else
             ['np_craft_specs.py','np_craft_geometry.py','np_craft_texture.py','np_craft_build.py'])},
         'textures':{'albedo_px':1024 if family=='flora' else 2048,'normal_px':512,'orm_px':256,'normal_convention':'OpenGL +Y','orm':'R=AO,G=roughness,B=metal'},
         'status':'SOURCE_VALIDATED','seconds':round(time.monotonic()-started,2),'export_proof':det}
    backup(EVID/'receipts'/f'{spec["id"]}.json');L.write_json(EVID/'receipts'/f'{spec["id"]}.json',rec)
    L.log('CRAFT',spec['id'],[reports[f'lod{i}']['triangles'] for i in range(3)],rec['seconds'],'seconds')
    return rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--only',default='');ap.add_argument('--group',default='');ap.add_argument('--revision',type=int,default=1);ap.add_argument('--proof',action='store_true')
    a=ap.parse_args(L.args_after_dashdash());only=set(filter(None,a.only.split(',')));groups=set(filter(None,a.group.split(',')))
    selected=[s for s in F.assets()+assets() if (not only or s['id'] in only) and (not groups or s.get('group') in groups or ('flora' in groups and not s.get('family')))]
    for s in selected:build(s,a.revision,a.proof)
    L.log('CRAFT BUILD COMPLETE',len(selected))

if __name__=='__main__':main()
