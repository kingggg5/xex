"""Bounded full stone candidate build with per-asset failures and review receipts."""
import argparse
from pathlib import Path
import sys
import time
import traceback
import runpy

sys.path.insert(0,str(Path(__file__).resolve().parent))
import np_lib as L
import np_stone_build as B
import np_stone_review as V
from np_stone_specs import assets

ap=argparse.ArgumentParser();ap.add_argument("--revision",type=int,default=5)
ap.add_argument("--only",default="");ap.add_argument("--no-review",action="store_true")
ap.add_argument("--tag",default="")
ap.add_argument("--prove",action="store_true")
args=ap.parse_args(L.args_after_dashdash());start=time.monotonic()
only=set(filter(None,args.only.split(",")));results=[]
report_path=B.EVID/f"batch-pass{args.revision}{'-'+args.tag if args.tag else ''}.json"
B.backup_existing(report_path)
for d in (B.OUT/"source",B.OUT/"colliders",B.EVID/"receipts",B.CACHE):d.mkdir(parents=True,exist_ok=True)
for spec in assets():
    if only and spec["id"] not in only:continue
    try:
        r=B.build_one(spec,argparse.Namespace(revision=args.revision,no_export=False))
        results.append({"id":spec["id"],"status":r["status"]})
    except Exception as exc:
        results.append({"id":spec["id"],"status":"FAILED","error":str(exc)})
        L.log(f"STONE FAILED {spec['id']}: {exc}");traceback.print_exc()
    L.write_json(report_path,{"results":results,"seconds":round(time.monotonic()-start,2)})
failed=[r["id"] for r in results if r["status"]=="FAILED"]
if not args.no_review and not failed:
    for group,views in (("sample","game,close,night,front,side"),("rocks","lineup"),("cliffs","lineup"),
                        ("grotto","lineup,game,night"),("ruins","lineup,game,close")):
        sys.argv=[__file__,"--","--revision",str(args.revision),"--group",group,"--views",views]
        V.main()
if args.prove and not failed:
    sys.argv=[__file__,"--","--revision",str(args.revision)]
    runpy.run_path(str(Path(__file__).resolve().parent/"np_stone_determinism.py"),run_name="__main__")
L.log(f"STONE BATCH {len(results)} processed; {len(failed)} failed; {time.monotonic()-start:.1f}s")
if failed:sys.exit(1)
