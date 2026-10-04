from pathlib import Path
from datetime import datetime,timezone
import json
ROOT=Path(__file__).resolve().parents[4]
E=ROOT/'planning/evidence/blueprint-p0-20261003/cc0'
M=json.loads((ROOT/'assets/models/blueprint-cc0/manifest.json').read_text(encoding='utf-8'))
R=json.loads((E/'readback-final.json').read_text(encoding='utf-8'))
record={'schema':'xexoria.blueprint-cc0-handoff/1','status':'QUIESCED_STATIC_MANIFEST_READY_NATIVE_PENDING',
 'created_utc':datetime.now(timezone.utc).isoformat(),'start_ict':'2026-10-03 11:36 ICT','first_usable_manifest_ict':'11:55 ICT',
 'assets':[a['id'] for a in M['assets']],'runtime_lod_files':15,'readback':R['result'],'determinism':'PASS15binaryfiles',
 'owned_processes':[],'owned_gpu_lease':False,'owned_blender_lease':False,'missing':M['missingAssets'],
 'limits':['Source previews and decoded geometry only; final3D/native/motion/collider/shadow/device acceptance pending.',
           'Palm336tris/3draws is a provisional licensed stock stand-in, not production tree pass.'],
 'next':'Root loader integrates exactP0anchors and verifies native capture after liveforeignGPUownerrelease; no defaultpromotion from this manifest alone.'}
(E/'HANDOFF.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':record['status'],'assets':len(M['assets'])}))
