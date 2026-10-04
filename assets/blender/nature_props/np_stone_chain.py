"""One short machine-slot run: build sample then capture fixed cameras."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import np_lib as L
import np_stone_build as B
import np_stone_review as V
from np_stone_specs import assets

ap=argparse.ArgumentParser();ap.add_argument("--revision",type=int,required=True)
ap.add_argument("--views",default="game,close")
args=ap.parse_args(L.args_after_dashdash())
for d in (B.OUT/"source",B.OUT/"colliders",B.EVID/"receipts",B.CACHE):d.mkdir(parents=True,exist_ok=True)
ids={"sm_medium_03","sm_boulder_02","sm_cliff_wall_01"}
for spec in assets():
    if spec["id"] in ids:B.build_one(spec,argparse.Namespace(revision=args.revision,no_export=False))
sys.argv=[__file__,"--","--revision",str(args.revision),"--views",args.views]
V.main()
