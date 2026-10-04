"""P5: bounded deterministic repair derived from the immutable P4 master.

Adjusts only measured coplanar channel side planes and three road layers.
Does not write R5, engine code, shared exporter or source textures.
"""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys, shutil
import bpy
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
E=ROOT/'planning/evidence/map-dressing-20261002'
O=ROOT/'assets/models/reference-city/r6-candidate'
SNAP=Path(str(_XEXORIA_AGENT_OUTPUT / '20261003-r6-finish/revisions/0919-pre-tail'))
SOURCE=SNAP/'reference_city_r6_candidate.blend'
EXPECTED='8e062f47ab2211b412c7aedf0fd67848b1b1257b16dbe286370cefb9765cfd02'
LAYOUT=HERE/'layout-r6-candidate.json'
PARAMS={'seed':0,'channel_side_separation_m':.016,
        'road_lifts_m':{'terrain / path market square':.03,'terrain / path west_loop':.08},
        'channel_prefix':'terrain / channel coping gate_pool_'}
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert sha(SOURCE)==EXPECTED
def apply():
    records=[]
    for o in sorted(bpy.context.scene.objects,key=lambda o:o.name):
        if o.type!='MESH':continue
        if o.name not in PARAMS['road_lifts_m'] and not o.name.startswith(PARAMS['channel_prefix']):continue
        if o.data.users>1:o.data=o.data.copy()
        n=len(o.data.vertices);v=np.empty(n*3,dtype=np.float64);o.data.vertices.foreach_get('co',v);v=v.reshape(-1,3)
        m=np.array(o.matrix_world);w=v@m[:3,:3].T+m[:3,3]
        if o.name in PARAMS['road_lifts_m']:
            lift=PARAMS['road_lifts_m'][o.name]
            w[:,2]+=lift;count=n
            action=f'road layer +{lift}m (under 0.36m step budget)'
        else:
            lo,hi=w[:,0].min(),w[:,0].max();a=np.abs(w[:,0]-lo)<1e-4;b=np.abs(w[:,0]-hi)<1e-4
            w[a,0]-=PARAMS['channel_side_separation_m'];w[b,0]+=PARAMS['channel_side_separation_m'];count=int(a.sum()+b.sum())
            action='coping side planes outward 0.016m; height unchanged'
        inv=np.array(o.matrix_world.inverted());local=w@inv[:3,:3].T+inv[:3,3]
        o.data.vertices.foreach_set('co',local.reshape(-1));o.data.update()
        records.append({'object':o.name,'vertices':count,'action':action})
    bpy.context.view_layer.update()
    assert len(records)==6,records
    return records
def signature():
    h=hashlib.sha256()
    for o in sorted(bpy.context.scene.objects,key=lambda o:o.name):
        if o.type!='MESH':continue
        h.update(o.name.encode());h.update(np.asarray(o.matrix_world,dtype='<f4').tobytes())
        c=np.empty(len(o.data.vertices)*3,dtype='<f4');o.data.vertices.foreach_get('co',c);h.update(c.tobytes())
        for p in o.data.polygons:h.update(np.asarray(p.vertices,dtype='<u4').tobytes())
    return h.hexdigest()
hashes=[]
for _ in range(2):
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE),load_ui=False,use_scripts=False)
    records=apply();hashes.append(signature())
assert hashes[0]==hashes[1]
layout=json.loads(LAYOUT.read_text(encoding='utf-8'))
layout['r6_tail_repair']={'schema':'xexoria.r6-tail-repair/1','recipe':Path(__file__).relative_to(ROOT).as_posix(),
                         'input_sha256':EXPECTED,'params':PARAMS,'immutable_input':str(SOURCE)}
LAYOUT.write_text(json.dumps(layout,indent=1)+'\n',encoding='utf-8')
bpy.context.preferences.filepaths.save_version=0
master=O/'reference_city_r6_candidate.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(master),check_existing=False,relative_remap=False,copy=True)
receipt=json.loads((O/'derivation-receipt-final.json').read_text(encoding='utf-8'))
receipt['created_utc']=datetime.now(timezone.utc).isoformat()
receipt['layout']['sha256']=sha(LAYOUT)
receipt['candidate']={'path':master.relative_to(ROOT).as_posix(),'sha256':sha(master),'bytes':master.stat().st_size}
receipt['tail_input']={'path':str(SOURCE),'sha256':EXPECTED}
receipt['operations']['targeted_tail_plane_separation']={'params':PARAMS,'records':records,'geometry_hash_runs':hashes,
    'geometry_determinism':'PASS','blend_byte_determinism':'UNVERIFIED (two independent geometry replays; one saved master)'}
(O/'derivation-receipt-p5.json').write_text(json.dumps(receipt,indent=1)+'\n',encoding='utf-8')
assert sha(SOURCE)==EXPECTED
print('R6_P5 '+json.dumps({'master_sha256':sha(master),'geometry_hash_runs':hashes,'objects':records}),flush=True)
