"""Select a versioned source without overwriting it; admit matching runtime/data."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
root=Path(__file__).resolve().parents[1];city=root/'assets/models/reference-city/r5';package=city/'market-repair-candidate'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
expected={'reference_city_market_gate_repaired.blend':'bda8d7857108bf57cd75f59ee8aad0b170a50fef66b0b26e563bce9c4374d373',
 'city-source.glb':'91b5c4952deeff608bbc2f6b5a9e0c67927f838aa70f34c6d9191ebdf21c4572',
 'city-runtime.meshopt.glb':'95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72',
 'city-traversal-v1.json':'e4de865748d1194b90bbc0e3b63cd806f637948f1e14ab4ee17e74ed0dcb6474'}
for name,digest in expected.items():assert sha(package/name)==digest,f'Candidate changed: {name}'
client=root/'apps/client/src/assets/models/env_reference_city.glb'
assert sha(client) in ('f1369076862906dd6327faf37e364301a51dc7d288da1ef15e88e300d421caee',expected['city-runtime.meshopt.glb'])
raw=json.loads((package/'city-traversal-v1.json').read_text(encoding='utf-8'))
assert raw['source']['master_sha256']==expected['reference_city_market_gate_repaired.blend']
operation={key:raw[key] for key in ('schema','units','city_bounds','surfaces','blockers')}
operation['surfaces']=[{key:s[key] for key in ('id','kind','vertices','triangles')} for s in raw['surfaces']]
operation['blockers']=[{key:b[key] for key in ('id','kind','polygon_xz','y_min','y_max')} for b in raw['blockers']]
keys=('max_step_m','max_slope_degrees','feet_offset_m','query_epsilon_m','max_movement_substep_m')
operation['contract']={key:raw['contract'][key] for key in keys}
gate_ids=[b['id'] for b in operation['blockers'] if 'gate' in b['id'].lower()]
assert len(gate_ids)>=15,'Accurate gate blockers required before retiring broad boxes'
zone_path=root/'content/source/zones.json';zones=json.loads(zone_path.read_text(encoding='utf-8'));zone=zones['zones'][0]
retired={'town_gate_west_wing','town_gate_east_wing'}
present={c['id'] for c in zone['static_colliders'] if c['id'] in retired}
assert present==retired or (not present and 'city_traversal' in zone),'Unexpected partial static retirement'
zone['static_colliders']=[c for c in zone['static_colliders'] if c['id'] not in retired]
zone['city_traversal']=operation
backup=root/'.harness/.cache/city-admission/backups';backup.mkdir(parents=True,exist_ok=True)
if not (backup/'zones-before.json').exists():shutil.copy2(zone_path,backup/'zones-before.json')
if not (backup/'runtime-before.glb').exists():shutil.copy2(client,backup/'runtime-before.glb')
selected={'schema':'xexoria.city-active-revision/1','revision':'r5-market-gate-20261001','selected_utc':datetime.now(timezone.utc).isoformat(),
 'files':{name:{'path':(package/name).relative_to(root).as_posix(),'sha256':digest} for name,digest in expected.items()},
 'texture_policy':'54 previous KTX2 images unchanged; no map-wide material or texture pass',
 'source_policy':'All selected versioned source files and prior canonical sources remain immutable.',
 'retired_static_ids':sorted(retired),'replacement_gate_ids':gate_ids,'native_status':'Pending actual walking/capture acceptance'}
try:
 zone_path.write_text(json.dumps(zones,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 shutil.copy2(package/'city-runtime.meshopt.glb',client)
 assert sha(client)==expected['city-runtime.meshopt.glb']
 (city/'active-revision.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
except Exception:
 shutil.copy2(backup/'zones-before.json',zone_path);shutil.copy2(backup/'runtime-before.glb',client);raise
receipt={'status':'PASS','revision':selected['revision'],'runtime_sha256':sha(client),'zone_source_sha256':sha(zone_path),
 'support_triangles':sum(len(s['triangles']) for s in operation['surfaces']),'blockers':len(operation['blockers']),
 'retired_static_ids':sorted(retired),'source_immutable':True,'limits':'Byte/data admission only; server build and native walking not yet verified.'}
(root/'planning/evidence/city-revision-admission-20261001.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
