"""Promote the reviewed geometric repair, preserving explicit rollback files."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
root=Path(__file__).resolve().parents[1];city=root/'assets/models/reference-city/r5';candidate=city/'traversal-repair-candidate'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
expected_master='6a12e74fcc5e13e33a50f11159ace36795f750319cbfe32336c33013259a5b3b'
expected_runtime='f1369076862906dd6327faf37e364301a51dc7d288da1ef15e88e300d421caee'
items=[(city/'reference_city.blend',candidate/'reference_city_walk_repaired.blend','9f7a55a8a0be836a5f2d42a3723253a216becd5cb0017f74ea710d4814c5e933',expected_master),
       (city/'city-source.glb',candidate/'city-source.glb',None,'08edc7597f666484ea57533e49639b046f40dcab7c7c26772981d7e3bee00339'),
       (city/'city-runtime.glb',candidate/'city-runtime.meshopt.glb','dceeda6985dd99c61786deda6089bf3c89e3b752868b52163cfdf3eb30f5116e',expected_runtime),
       (root/'apps/client/src/assets/models/env_reference_city.glb',candidate/'city-runtime.meshopt.glb','dceeda6985dd99c61786deda6089bf3c89e3b752868b52163cfdf3eb30f5116e',expected_runtime)]
window_receipt=json.loads((root/'planning/evidence/city-window-promotion-20261001.json').read_text(encoding='utf-8'))
window_hashes={Path(row['destination']).as_posix():row['after'] for row in window_receipt['changes']}
for dest,src,before,after in items:
    assert sha(dest)==(before or window_hashes[dest.relative_to(root).as_posix()]),f'Active source changed: {dest}'
    assert sha(src)==after,f'Candidate bytes changed: {src}'
data=json.loads((candidate/'city-traversal-v1.json').read_text())
assert data['source']['master_sha256']==expected_master
backup=root/'.harness/.cache/city-traversal/backups';backup.mkdir(parents=True,exist_ok=True)
rows=[]
for index,(dest,src,_before,after) in enumerate(items):
    path=backup/f'{index}-{dest.name}';shutil.copy2(dest,path);assert sha(path)==sha(dest)
    rows.append({'destination':str(dest.relative_to(root)),'before':sha(dest),'after':after,'rollback':str(path.relative_to(root))})
try:
    for dest,src,_before,_after in items:shutil.copy2(src,dest)
    for row in rows:assert sha(root/row['destination'])==row['after']
except Exception:
    for row in rows:shutil.copy2(root/row['rollback'],root/row['destination'])
    raise
receipt={'status':'PASS','date':datetime.now(timezone.utc).isoformat(),'changes':rows,
    'runtime_bytes':items[-1][0].stat().st_size,'runtime_triangles':898989,
    'scope':'Reviewed art: windows retained, staircase/bridge/path repair, complete tree relocation, hollow fountain openings; operational data admission still separate.'}
(root/'planning/evidence/city-traversal-art-promotion-20261001.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','files':len(rows),'runtime_bytes':receipt['runtime_bytes'],'runtime_sha256':expected_runtime}))
