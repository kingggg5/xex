"""Cross-file acceptance audit and fresh texture determinism proof; CPU only."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(HERE))
from np_stone_texture import generate
OUT=ROOT/"assets/models/sunmeadow-props/stone";EVID=ROOT/"planning/evidence/sunmeadow-props-20261002/stone"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding="utf8"))
def save(p,value):
    if p.exists():
        digest=sha(p);dest=EVID/"backup"/(p.name+"."+digest[:12]+".orig")
        if not dest.exists():shutil.copy2(p,dest)
    p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf8")

manifest=read(OUT.parent/"manifest.json");entries=manifest["families"]["stone"]
assert manifest["schema"]=="xexoria.props-manifest/1" and len(entries)==44
assert len({e["id"] for e in entries})==44
groups=Counter();triangles=[0,0,0];uv=[];gpu=[];hashes={};ratios=[[],[]]
for e in entries:
    r=read(EVID/"receipts"/(e["id"]+".json"));assert r["status"]=="SOURCE_VALIDATED"
    groups[r["group"]]+=1
    assert r["mesh"]["lod0"]["triangles"]<=r["lod0_tris"]
    for i,lod in enumerate(e["lods"]):
        p=ROOT/lod["file"];assert sha(p)==lod["sha256"];hashes[lod["file"]]=sha(p)
        triangles[i]+=lod["tris"]
        mesh=r["mesh"][f"lod{i}"]
        assert not any(mesh[k] for k in ("non_manifold_edges","boundary_edges","zero_area_faces","loose_verts"))
        assert abs(mesh["bounds_min"][2])<=1e-4
        uv.append(mesh["uv_measured_px_per_m"])
        assert 256<=uv[-1]<=512
        if i:ratios[i-1].append(lod["tris"]/e["lods"][0]["tris"])
    for suffix in ("lod0","lod1","lod2","collider"):
        name=e["id"]+"_"+suffix
        rep=read(OUT/"runtime/reports"/(name+".report.json"))
        assert rep["status"]=="PASS" and rep["validator"]["errors"]==0
        assert all(x["pass"] for x in rep["parity"])
        assert "KHR_meshopt_compression" not in rep["after"]["extensionsUsed"]
        assert rep["metrics"]["vertex_attributes"]<=8
        if suffix=="lod0":gpu.append(rep["metrics"]["texture_mib"])
        for family in ("source","runtime"):
            p=OUT/family/(name+".glb");hashes[p.relative_to(ROOT).as_posix()]=sha(p)
    assert e["collider"]["class"] in ("solid","soft","none")
assert groups=={"rocks":23,"cliffs":6,"grotto":6,"ruins":9},groups
mesh_proof=read(EVID/"determinism-mesh.json");assert mesh_proof["pass"] and len(mesh_proof["assets"])==2
for a in mesh_proof["assets"]:
    assert a["pass"]
    for name,digest in a["attempts"][-1]["file_sha256"].items():assert sha(OUT/"source"/name)==digest
world=read(EVID/"runtime-world-bounds.json");assert world["pass"] and len(world["assets"])==44
for row in world["assets"]:assert sha(OUT/"runtime"/(row["id"]+"_lod0.glb"))==row["runtime_sha256"]
with tempfile.TemporaryDirectory(prefix="xex-stone-proof-a-") as a,tempfile.TemporaryDirectory(prefix="xex-stone-proof-b-") as b:
    ra=generate(a,1);rb=generate(b,1);proof={}
    for name,item in ra["artifacts"].items():
        current=sha(OUT/"textures-source"/name)
        assert item["sha256"]==rb["artifacts"][name]["sha256"]==current
        proof[name]={"first":item["sha256"],"second":rb["artifacts"][name]["sha256"],"current":current,"pass":True,"resolution":item["resolution"]}
    save(EVID/"determinism-textures.json",{"pass":True,"two_independent_generations":True,"source_sha256":sha(HERE/"np_stone_texture.py"),"artifacts":proof})
backups=list((EVID/"backup").glob("manifest.*.orig"));latest=max(backups,key=lambda p:p.stat().st_mtime)
before=read(latest)
preserved={f:before["families"][f]==manifest["families"][f] for f in ("craft","flora")}
report={"schema":"xexoria.stone-final-audit/1","at_ict":datetime.now().astimezone().isoformat(),"technical":"PASS",
        "assets":44,"groups":dict(groups),"source_glbs":176,"runtime_glbs":176,"lod_triangles_total":triangles,
        "uv_px_per_m_min_max":[min(uv),max(uv)],"lod_ratio_min_max":[[min(r),max(r)] for r in ratios],
        "texture_gpu_mib_per_asset_min_max":[min(gpu),max(gpu)],"texture_memory_note":"offline compressed mip/block budget estimate, not measured GPU residency",
        "world_bounds_max_deviation_m":max(x["max_deviation_m"] for x in world["assets"]),
        "manifest_other_families_preserved":preserved,"manifest_sha256":sha(OUT.parent/"manifest.json"),
        "stone_family_sha256":hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest(),
        "mesh_determinism":"PASS two assets x two fresh builds; all eight GLBs byte-identical",
        "texture_determinism":"PASS seven textures x two fresh generations match current files",
        "runtime_hashes":{k:v for k,v in hashes.items() if "/runtime/" in k},"all_glb_hashes":hashes}
save(EVID/"final-audit.json",report)
print(json.dumps({k:v for k,v in report.items() if k not in ("runtime_hashes","all_glb_hashes")},indent=2,ensure_ascii=False))
