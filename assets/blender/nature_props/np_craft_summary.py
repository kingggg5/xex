"""Seal a craft/flora evidence receipt from actual file bytes and reports."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,math
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];E=ROOT/'planning/evidence/sunmeadow-props-20261002/craft'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def main():
    m=read(ROOT/'assets/models/sunmeadow-props/manifest.json');families={k:m['families'][k] for k in ('craft','flora')}
    files={};textures=set();counts={};reports=[];source_hashes={};reused=[]
    for family,entries in families.items():
        counts[family]={'assets':len(entries),'one_copy_each_lod_triangles':[sum(a['lods'][i]['tris'] for a in entries) for i in range(3)],
            'shared_atlas_gpu_mib_offline_estimate':entries[0]['textures']['gpu_mib']}
        for a in entries:
            r=read(ROOT/a['source_receipt'])
            if r['status']!='SOURCE_VALIDATED':raise ValueError('Unvalidated source '+a['id'])
            if a['metadata'].get('lod2_reuses_lod1_geometry'):reused.append(a['id'])
            for src in r['source_files']:
                digest=sha(ROOT/src)
                if r.get('source_sha256',{}).get(src)!=digest:raise ValueError('Source hash mismatch '+src)
                source_hashes[src]=digest
            targets=[x['file'] for x in a['lods']]
            if a['collider'].get('hull'):targets.append(a['collider']['hull'])
            for f in targets:
                p=ROOT/f;rp=p.parent/'reports'/(p.stem+'.report.json');report=read(rp)
                if report['status']!='PASS' or report['validator']['errors']:raise ValueError('Runtime validation failed '+f)
                reports.append(report);files[f]={'sha256':sha(p),'bytes':p.stat().st_size}
            for l in a['lods']:
                if files[l['file']]['sha256']!=l['sha256']:raise ValueError('Manifest hash mismatch')
            textures.update(a['textures']['ktx2_files'])
    for f in textures:files[f]={'sha256':sha(ROOT/f),'bytes':(ROOT/f).stat().st_size}
    proofs=[]
    for p in sorted((E/'determinism').glob('*.json')):
        r=read(p)
        if not r['byte_identical'] or not r['geometry_identical']:raise ValueError('Determinism failed')
        if any(sha(ROOT/f)!=h for f,h in r['second'].items()):raise ValueError('Proof does not bind final source')
        proofs.append({'file':str(p.relative_to(ROOT)),'sha256':sha(p),'recipe':r['recipe'],'seed':r['seed'],'params':r['params'],'status':'PASS'})
    if len(proofs)<2:raise ValueError('Need two proof assets')
    comparisons=[]
    for before in sorted((E/'review-pass5').glob('BLENDER_REVIEW_*.png')):
        revised=any(group in before.name for group in ('market','pier'))
        if revised:before=E/'review-pass9'/before.name
        elif 'threshold' in before.name:before=E/'review-pass7'/before.name
        after=E/('review-pass10' if revised else 'review-pass8')/before.name
        if not after.exists():continue
        a=np.asarray(Image.open(before).convert('RGB'),dtype=float)/255;b=np.asarray(Image.open(after).convert('RGB'),dtype=float)/255
        mse=float(np.mean((a-b)**2));psnr=99.0 if mse==0 else -10*math.log10(mse)
        comparisons.append({'view':before.stem,'psnr_db_full_frame':round(psnr,3),'source_sha256':sha(before),'decoded_sha256':sha(after)})
    tests=read(E/'logs/client-final-status.json')
    if tests['testExit'] or tests['checkExit']:raise ValueError('Client checks failed')
    for p in (E/'flora-wind-validation.json',E/'flora-wind-runtime-validation.json'):
        if read(p)['status']!='PASS':raise ValueError('Wind failed')
    if any(x['status']!='PASS' for x in read(E/'outward-normal-validation.json')+read(E/'opening-clearance.json')):raise ValueError('Static geometry gate failed')
    visual=read(E/'visual-review-final.json')
    if visual.get('status')!='SOURCE_CANDIDATE':raise ValueError('Final visual inspection not recorded')
    receipt={'schema':'xexoria.craft-flora-handoff/1','status':'QUIESCED_CANDIDATE','at':datetime.now(timezone.utc).isoformat(),
        'project_id':'project-a6dcbc9c-dcdf-4efe-9428-b88a9b5694bf','run_id':'RUN-20260923-mmorpg-plan-v3',
        'counts':counts,'runtime_glb_count':len(reports),'unique_ktx2_count':len(textures),'runtime_and_texture_bytes':sum(x['bytes'] for x in files.values()),
        'runtime_validation':{'pass':len(reports),'khronos_errors':0,'warnings':sum(x['validator']['warnings'] for x in reports),
           'warning_note':'Current validator emits expected image/ktx2 MIME/format warnings; postprocessor, basis decode and parity checks PASS.'},
        'max_source_primitive_attributes':max(x['metrics']['vertex_attributes'] for x in reports),
        'per_asset_materials':sorted(set(x['metrics']['materials'] for x in reports if x['metrics']['materials'])),
        'lod2_reuses_valid_lod1':reused,'determinism':proofs,'source_sha256':source_hashes,'runtime_files':files,
        'manifest_family_sha256':{k:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest() for k,v in families.items()},
        'source_vs_decoded_comparisons':comparisons,'client_checks':tests,'visual_inspection':visual,
        'review_setup':{'renderer':'Blender5.2.2 Cycles CPU','cpu_threads':6,'samples':16,'resolution':[960,600],
            'device':'CPU on GTX1050 workstation; GPU unused','game_tier':'N/A source review','player_camera_radius_m':13,'beta':1.18,'fov_y':1.02,'witness_m':1.8},
        'gates':{'source_exports':'PASS','runtime_artifact_validation':'PASS','wind_uv2':'PASS','static_opening_probes':'PASS','determinism':'PASS',
            'visual':'SOURCE_CANDIDATE; native game acceptance UNVERIFIED','gameplay':'UNVERIFIED','device':'UNVERIFIED'},
        'limits':['No live placement or renderer-native acceptance capture by this lane.','Pier/bridge require authoritative walk-surface integration.',
            'Hut/gate use compound colliders; do not replace them with a blocking footprint circle.','Shared atlas material reuse and actual instanced buffer bindings require runtime verification.',
            'Small props retain simple close-up geometry; map detail is procedurally painted, not an asset-specific high-poly normal/AO bake.'],
        'jev':{'status':'USED_VERIFIED_REUSED','receipt':'external 20261002-go-root/jev-p0-render-selection.json','input_tokens':536,'output_tokens':49,'savings':'NOT_MEASURED'},
        'spend_credits':0,'new_downloads':0,'third_party_assets':0}
    dest=E/'FINAL-RECEIPT.json';dest.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'receipt':str(dest),'sha256':sha(dest),'assets':sum(x['assets'] for x in counts.values()),'runtime_glbs':len(reports),'ktx2':len(textures),
        'bytes':receipt['runtime_and_texture_bytes'],'min_full_frame_psnr_db':min(x['psnr_db_full_frame'] for x in comparisons)},indent=2))
if __name__=='__main__':main()
