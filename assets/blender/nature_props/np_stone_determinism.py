"""Two independent reset/build/export runs for two representative stone seeds."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import np_lib as L
import np_stone_build as B
from np_stone_specs import assets

ap=argparse.ArgumentParser();ap.add_argument("--revision",type=int,default=3)
args=ap.parse_args(L.args_after_dashdash())
records=[]
for spec in assets():
    if spec["id"] not in ("sm_medium_03","sm_boulder_02"):continue
    attempts=[]
    for run in (1,2):
        r=B.build_one(spec,argparse.Namespace(revision=args.revision,no_export=False))
        files={Path(p).name:L.sha256_file(L.REPO/p) for p in r["source_files"]}
        attempts.append({"run":run,"file_sha256":files,
                         "geometry_sha256":{k:v["geometry_sha256"] for k,v in r["mesh"].items() if "geometry_sha256" in v}})
    passed=attempts[0]["file_sha256"]==attempts[1]["file_sha256"] and attempts[0]["geometry_sha256"]==attempts[1]["geometry_sha256"]
    records.append({"id":spec["id"],"recipe":spec["recipe"],"seed":spec["seed"],"params":spec["params"],"attempts":attempts,"pass":passed})
L.write_json(B.EVID/"determinism-mesh.json",{"schema":"xexoria.stone-determinism/1","revision":args.revision,"assets":records,
                                         "pass":all(r["pass"] for r in records)})
if not all(r["pass"] for r in records):raise RuntimeError("Stone determinism mismatch")
L.log("STONE DETERMINISM PASS: two assets, two reset/build/export runs, all four GLBs each byte-identical")
