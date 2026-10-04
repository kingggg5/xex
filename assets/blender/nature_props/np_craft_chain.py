"""One bounded Blender lease for build and immediately useful review views."""
import argparse
import traceback
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import np_lib as L
import kit_flora as F
from np_craft_specs import assets
from np_craft_build import build,EVID
from np_craft_review import review
ap=argparse.ArgumentParser();ap.add_argument('--only',default='');ap.add_argument('--group',default='');ap.add_argument('--review',default='');ap.add_argument('--revision',type=int,default=1);ap.add_argument('--review-revision',type=int);ap.add_argument('--views',default='game,close');ap.add_argument('--proof',action='store_true');ap.add_argument('--proof-only',default='')
a=ap.parse_args(L.args_after_dashdash());only=set(filter(None,a.only.split(',')));groups=set(filter(None,a.group.split(',')))
selected=[s for s in F.assets()+assets() if (not only or s['id'] in only) and (not groups or s.get('group') in groups or ('flora' in groups and not s.get('family')))]
failures=[]
for s in selected:
    try:
        prove=a.proof and (not a.proof_only or s['id'] in a.proof_only.split(','))
        first=build(s,a.revision,prove)
        if prove:
            hashes={f:L.sha256_file(L.REPO/f) for f in first['source_files']}
            second=build(s,a.revision,False)
            again={f:L.sha256_file(L.REPO/f) for f in second['source_files']}
            L.write_json(EVID/'determinism'/f'{s["id"]}.json',{'recipe':s['recipe'],'seed':s['seed'],'params':first['params'],
                'two_fresh_builds':True,'first':hashes,'second':again,'byte_identical':hashes==again,
                'geometry_identical':first['mesh']==second['mesh']})
    except Exception as exc:
        failures.append({'id':s['id'],'error':str(exc)});traceback.print_exc()
for group in filter(None,a.review.split(',')):
    try:review(group,a.review_revision or a.revision,a.views,available=True)
    except Exception as exc:failures.append({'review_group':group,'error':str(exc)});traceback.print_exc()
L.write_json(EVID/'logs'/f'build-revision{a.revision}-failures.json',failures)
if failures:raise RuntimeError(str(failures))
