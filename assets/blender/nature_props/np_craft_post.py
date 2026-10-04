"""CPU KTX2/meshopt processing; publish only verified craft/flora families."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];sys.path.insert(0,str(HERE))
from np_manifest import merge_family
from np_craft_normals import check as check_normals
EVID=REPO/'planning/evidence/sunmeadow-props-20261002/craft';OUT=REPO/'assets/models/sunmeadow-props'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return Path(p).relative_to(REPO).as_posix()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--only',default='');ap.add_argument('--family',default='');ap.add_argument('--no-node',action='store_true');a=ap.parse_args()
    only=set(filter(None,a.only.split(',')));records=[]
    for p in sorted((EVID/'receipts').glob('sm_*.json')):
        r=json.loads(p.read_text(encoding='utf8'))
        if r.get('status')=='SOURCE_VALIDATED' and (not only or r['id'] in only) and (not a.family or r['family']==a.family):records.append(r)
    if not records:raise ValueError('No source receipts')
    jobs=[]
    for r in records:
        runtime=OUT/r['family']/'runtime'
        for f in r['source_files']:
            src=REPO/f;name=src.name
            if r.get('source_sha256',{}).get(f) and sha(src)!=r['source_sha256'][f]:raise ValueError('Source changed after validation: '+f)
            if r['family']=='craft' and '_lod' in name and check_normals(src)['status']!='PASS':raise ValueError('Inward source component: '+f)
            for previous in (runtime/name,runtime/'reports'/(src.stem+'.report.json')):
                if previous.exists():
                    backup=EVID/'backup';backup.mkdir(parents=True,exist_ok=True);digest=sha(previous)
                    shutil.copy2(previous,backup/(previous.name+'.'+digest[:12]+'.orig'))
                    with open(backup/'SHA256SUMS.txt','a',encoding='utf8') as log:log.write(digest+'  '+str(previous)+'\n')
            jobs.append({'input':str(src),'output':str(runtime/name),'textureOut':str(runtime/'textures'),
                         'report':str(runtime/'reports'/(src.stem+'.report.json')),'reviewOut':str(EVID/'decoded-review'/r['family'])})
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S');logs=EVID/'logs';logs.mkdir(parents=True,exist_ok=True)
    jp=logs/f'post-{stamp}.jobs.json';jp.write_text(json.dumps(jobs,indent=2),encoding='utf8')
    if not a.no_node:
        env=dict(os.environ);env['KTX_SOFTWARE_BIN']=str(REPO/'.harness/.cache/toolchains/ktx-4.4.2/portable/bin')
        with open(logs/f'post-{stamp}.stdout.txt','w',encoding='utf8') as so,open(logs/f'post-{stamp}.stderr.txt','w',encoding='utf8') as se:
            cp=subprocess.run(['node',str(REPO/'apps/client/scripts/gltf-postprocess.mjs'),'--jobs',str(jp),'--report',str(logs/f'post-{stamp}.summary.json')],cwd=REPO,env=env,stdout=so,stderr=se)
        print('CRAFT postprocess exit',cp.returncode,flush=True)
        if cp.returncode:
            print((logs/f'post-{stamp}.stderr.txt').read_text(encoding='utf8')[-4000:]);sys.exit(cp.returncode)
    for family in sorted(set(r['family'] for r in records)):
        staged=EVID/f'manifest-{family}.json';entries={r['id']:r for r in json.loads(staged.read_text(encoding='utf8'))} if staged.exists() else {}
        for r in [r for r in records if r['family']==family]:
            runtime=OUT/family/'runtime';lods=[];tex={}
            for i in range(3):
                f=runtime/f'{r["id"]}_lod{i}.glb';pr=runtime/'reports'/f'{f.stem}.report.json';post=json.loads(pr.read_text(encoding='utf8'))
                if not f.is_file() or post.get('status')!='PASS':raise ValueError('Unpassed '+str(f))
                lods.append({'file':rel(f),'tris':post['metrics']['triangles'],'bytes':f.stat().st_size,'sha256':sha(f)})
                if i==0:tex={'atlas':r['atlas'],'source':r['textures'],'gpu_mib':post['metrics']['texture_mib'],'draw_calls':post['metrics']['draw_calls'],
                             'ktx2_files':[x['file'] for x in post['sizes']['external_textures']],'receipts':post['textures']}
            m=r['mesh']['lod0'];mn,mx=m['bounds_min'],m['bounds_max'];collider={'class':'none','footprint_r':0}
            if family=='craft':
                cf=runtime/f'{r["id"]}_collider.glb';cr=runtime/'reports'/f'{cf.stem}.report.json'
                if not cf.exists() or json.loads(cr.read_text(encoding='utf8')).get('status')!='PASS':raise ValueError('Unpassed collider')
                collider={'class':'solid','footprint_r':round(max(abs(mn[0]),abs(mx[0]),abs(mn[1]),abs(mx[1]))*2**.5,4),
                          'hull':rel(cf),'sha256':sha(cf),'sidecar':rel(OUT/family/'colliders'/f'{r["id"]}.json')}
            entries[r['id']]={'id':r['id'],'family':family,'recipe':r['recipe'],'seed':r['seed'],'params':r['params'],'lods':lods,'textures':tex,
                'bounds':{'min':[mn[0],mn[2],-mx[1]],'max':[mx[0],mx[2],-mn[1]]},'pivot':[0,0,0],'collider':collider,
                'tags':r.get('tags',['WIND_UV2','DECORATIVE_WATER']), 'metadata':r['metadata'],'status':'TECHNICAL_CANDIDATE',
                'revision':r['revision'],'source_receipt':rel(EVID/'receipts'/f'{r["id"]}.json')}
        values=sorted(entries.values(),key=lambda r:r['id']);staged.write_text(json.dumps(values,indent=2),encoding='utf8')
        target=OUT/'manifest.json'
        if target.exists():
            backup=EVID/'backup';backup.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup/f'manifest.{stamp}.{family}.orig')
            with open(backup/'SHA256SUMS.txt','a',encoding='utf8') as f:f.write(sha(target)+'  '+str(target)+'\n')
        merge_family(target,family,values);print('CRAFT merged',family,len(values),'technical candidates')
if __name__=='__main__':main()
