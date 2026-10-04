"""One bounded final crystal repair, compression, all-model readback and review."""
from pathlib import Path
import argparse
import runpy
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import np_stone_build as B
import np_stone_review as V
from np_stone_specs import assets

ids=[]
for spec in assets():
    if spec["recipe"]=="stone.crystals/2":
        ids.append(spec["id"]);B.build_one(spec,argparse.Namespace(revision=5,no_export=False))
system_python=shutil.which("python")
if not system_python:raise RuntimeError("Existing system Python unavailable")
subprocess.run([system_python,str(Path(__file__).with_name("np_stone_post.py")),"--only",",".join(ids),"--stage-only"],check=True)
runpy.run_path(str(Path(__file__).with_name("np_stone_runtime_audit.py")),run_name="__main__")
sys.argv=[__file__,"--","--revision","7","--runtime","--group","crystals","--views","close,night"]
V.main()
