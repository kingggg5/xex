"""CPU post-process and family-only manifest publication for stone candidates.

The shared manifest is written only after every selected source has a PASS
postprocess report and actual file. No live placement or assets outside stone.
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
sys.path.insert(0,str(HERE))
from np_manifest import merge_family
OUT=REPO/"assets/models/sunmeadow-props/stone"
EVID=REPO/"planning/evidence/sunmeadow-props-20261002/stone"
DECODED=Path(os.environ.get("NP_CACHE",str(_XEXORIA_AGENT_OUTPUT / '20261002-sunmeadow-props/cache')))/"stone-v2"/"decoded-review"


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return Path(p).relative_to(REPO).as_posix()


def backup_existing(p):
    p=Path(p)
    if not p.exists():return
    digest=sha(p);backup=EVID/"backup";backup.mkdir(parents=True,exist_ok=True)
    dst=backup/(p.name+"."+digest[:12]+".orig")
    if not dst.exists():
        shutil.copy2(p,dst)
        with open(backup/"SHA256SUMS.txt","a",encoding="utf8") as log:log.write(f"{digest}  {rel(p)}\n")


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--only",default="");ap.add_argument("--no-node",action="store_true")
    ap.add_argument("--stage-only",action="store_true",help="validate runtime bytes without publishing the family manifest")
    args=ap.parse_args();only=set(filter(None,args.only.split(",")))
    receipts=[]
    for p in sorted((EVID/"receipts").glob("sm_*.json")):
        r=json.loads(p.read_text(encoding="utf8"))
        if "id" not in r or "source_files" not in r:continue
        if (not only or r["id"] in only) and r["status"]=="SOURCE_VALIDATED":receipts.append(r)
    if not receipts:raise ValueError("No validated source receipts selected")
    runtime=OUT/"runtime";reports=runtime/"reports";reports.mkdir(parents=True,exist_ok=True)
    jobs=[]
    for r in receipts:
        for src in r["source_files"]:
            name=Path(src).name
            if not args.no_node:
                backup_existing(runtime/name)
                backup_existing(reports/(Path(name).stem+".report.json"))
            job={"input":str(REPO/src),"output":str(runtime/name),"textureOut":str(runtime/"textures"),
                 "report":str(reports/(Path(name).stem+".report.json"))}
            if name.endswith("_lod0.glb"):job["reviewOut"]=str(DECODED)
            jobs.append(job)
    stamp=datetime.now().strftime("%Y%m%d-%H%M%S");logs=EVID/"logs";logs.mkdir(parents=True,exist_ok=True)
    jp=logs/f"post-{stamp}.jobs.json";jp.write_text(json.dumps(jobs,indent=2),encoding="utf8")
    if not args.no_node:
        env=dict(os.environ)
        env["KTX_SOFTWARE_BIN"]=str(REPO/".harness/.cache/toolchains/ktx-4.4.2/portable/bin")
        cmd=["node",str(REPO/"apps/client/scripts/gltf-postprocess.mjs"),"--jobs",str(jp),"--report",str(logs/f"post-{stamp}.summary.json")]
        with open(logs/f"post-{stamp}.stdout.txt","w",encoding="utf8") as so,open(logs/f"post-{stamp}.stderr.txt","w",encoding="utf8") as se:
            p=subprocess.run(cmd,cwd=REPO,env=env,stdout=so,stderr=se)
        print(f"postprocess exit={p.returncode}, log={logs/f'post-{stamp}.stdout.txt'}",flush=True)
        if p.returncode:
            lines=(logs/f"post-{stamp}.stderr.txt").read_text(encoding="utf8").splitlines()
            print("\n".join(x for x in lines if not x.startswith("quantize:"))[-4500:]);sys.exit(p.returncode)
    if args.stage_only:
        print("STONE runtime staged only; shared manifest unchanged")
        return
    # Keep previously validated stone entries during a bounded subset update.
    staged=EVID/"manifest-stone.json"
    merged={x["id"]:x for x in json.loads(staged.read_text(encoding="utf8"))} if staged.exists() else {}
    for r in receipts:
        aid=r["id"];lods=[];tex={};hashes={}
        for i in range(3):
            f=runtime/f"{aid}_lod{i}.glb";rp=reports/f"{aid}_lod{i}.report.json"
            post=json.loads(rp.read_text(encoding="utf8"))
            if not f.is_file() or post.get("status")!="PASS":raise ValueError(f"Unpassed runtime: {aid}/lod{i}")
            lods.append({"file":rel(f),"tris":post["metrics"]["triangles"],"bytes":f.stat().st_size,"sha256":sha(f)})
            hashes[f.name]=sha(f)
            if i==0:
                tex={"atlas":r["atlas"],"source":r["textures"],"gpu_mib":post["metrics"]["texture_mib"],
                     "draw_calls":post["metrics"]["draw_calls"],"ktx2_files":[x["file"] for x in post["sizes"]["external_textures"]],
                     "texture_receipts":post["textures"]}
        m=r["mesh"]["lod0"];mn,mx=m["bounds_min"],m["bounds_max"]
        cf=runtime/f"{aid}_collider.glb";cp=reports/f"{aid}_collider.report.json"
        if not cf.exists() or json.loads(cp.read_text(encoding="utf8")).get("status")!="PASS":raise ValueError(f"Unpassed collider {aid}")
        hashes[cf.name]=sha(cf)
        merged[aid]={"id":aid,"family":"stone","recipe":r["recipe"],"seed":r["seed"],
                     "params":{"geometry":r["params_resolved"],"paint":r["paint"],"surface_revision":r["revision"],
                               "atlas_recipe":"stone.painted-pbr/2","atlas_revision":1},
                     "lods":lods,"textures":tex,"bounds":{"min":[mn[0],mn[2],-mx[1]],"max":[mx[0],mx[2],-mn[1]]},
                     "pivot":[0,0,0],"collider":{"class":r["collider"]["class"],"footprint_r":round(max(abs(mn[0]),abs(mx[0]),abs(mn[1]),abs(mx[1]))*2**.5,4),
                     "hull":rel(cf),"sidecar":rel(OUT/"colliders"/f"{aid}.json")},"tags":r["tags"],"metadata":r["metadata"],
                     "status":"TECHNICAL_CANDIDATE","revision":r["revision"],"source_receipt":rel(EVID/"receipts"/f"{aid}.json")}
        (EVID/"receipts"/f"{aid}.runtime-hashes.json").write_text(json.dumps(hashes,indent=2),encoding="utf8")
    entries=sorted(merged.values(),key=lambda x:x["id"])
    staged.write_text(json.dumps(entries,indent=2),encoding="utf8")
    manifest=OUT.parent/"manifest.json"
    if manifest.exists():
        backup=EVID/"backup";backup.mkdir(parents=True,exist_ok=True)
        shutil.copy2(manifest,backup/f"manifest.{stamp}.orig")
        with open(backup/"SHA256SUMS.txt","a",encoding="utf8") as f:f.write(f"{sha(manifest)}  {rel(manifest)}\n")
    merge_family(manifest,"stone",entries)
    print(f"STONE manifest family atomically merged: {len(entries)} candidates")


if __name__=="__main__":main()
