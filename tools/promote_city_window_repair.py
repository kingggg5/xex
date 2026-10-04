"""Promote the reviewed window-only city revision with exact rollback copies."""
import hashlib,json,shutil
from pathlib import Path
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1]
receipt=json.loads((root/'planning/evidence/city-windows-20261001-runtime-pack.json').read_text(encoding='utf-8'))
assert receipt['result']=='PASS'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
city=root/'assets/models/reference-city/r5';candidate=city/'window-repair-candidate'
before={Path(row['path']).name:row['sha256'] for row in receipt['canonicalFilesUnchanged']}
items=[(city/'reference_city.blend',candidate/'reference_city_side_windows.blend'),
       (city/'city-source.glb',candidate/'city-source-window-candidate.glb'),
       (city/'city-runtime.glb',candidate/'city-runtime.meshopt.glb'),
       (root/'apps/client/src/assets/models/env_reference_city.glb',candidate/'city-runtime.meshopt.glb')]
for destination,source in items:
    expected=before.get(destination.name,before['city-runtime.glb'])
    assert sha(destination)==expected,f'Active file changed; refusing promotion: {destination}'
    assert source.is_file()
assert sha(items[-1][1])==receipt['output']['sha256']
backup=root/'.harness/.cache/city-windows/backups';backup.mkdir(parents=True,exist_ok=True)
rows=[]
for index,(destination,source) in enumerate(items):
    saved=backup/f'{index}-{destination.name}';shutil.copy2(destination,saved)
    assert sha(saved)==sha(destination)
    rows.append({'destination':str(destination.relative_to(root)),'before':sha(destination),'after':sha(source),'rollback':str(saved.relative_to(root))})
try:
    for destination,source in items:shutil.copy2(source,destination)
    for row in rows:assert sha(root/row['destination'])==row['after']
except Exception:
    for row in rows:shutil.copy2(root/row['rollback'],root/row['destination'])
    raise
out={'status':'PASS','date':datetime.now(timezone.utc).isoformat(),'changes':rows,
     'scope':'134 window assemblies; preserved all other object poses, mesh/UV/color/material content; no map movement/collision changes',
     'verification':'Offline structural + matched front/side Blender review; final GPU window view pending.'}
(root/'planning/evidence/city-window-promotion-20261001.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','files':len(rows),'runtime_bytes':items[-1][0].stat().st_size,'runtime_sha256':sha(items[-1][0])}))
