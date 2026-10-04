"""Re-run owned pure recipes twice; compare complete authored output hashes."""
from pathlib import Path
import subprocess, sys, hashlib, json
ROOT=Path(__file__).resolve().parents[3]
ASSETS=ROOT/"apps/client/src/assets/world/water-v3"
EV=ROOT/"planning/evidence/water-20261002"
def snapshot():
    paths=list(sorted(p for p in ASSETS.iterdir() if p.suffix in (".png",".bin") or p.name in ("textures-report.json","water-manifest.json")))
    paths += [EV/n for n in ("water-geometry.json","water-support-geometry.json","water-derived.json","water-hazard.json")]
    return {str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
def main():
    runs=[]
    for _ in range(2):
        subprocess.run([sys.executable,str(ROOT/"assets/blender/water/forge_water_textures.py"),"--out",str(ASSETS)],check=True,cwd=ROOT,stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable,str(ROOT/"assets/blender/water/prepare_water_v3.py")],check=True,cwd=ROOT,stdout=subprocess.DEVNULL)
        runs.append(snapshot())
    differences=[p for p in runs[0] if runs[0][p]!=runs[1][p]]
    receipt={"schema":"xexoria.water-determinism/1","seed":20261002,"status":"FAIL" if differences else "PASS","files":len(runs[0]),"run1":runs[0],"run2":runs[1],"differences":differences,
             "glb_sha256":hashlib.sha256((ASSETS/"env_sunmeadow_water_v3.glb").read_bytes()).hexdigest(),"note":"GLB two-export parity is recorded separately. Export receipt timing fields are excluded."}
    (EV/"determinism-receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(json.dumps({"status":receipt["status"],"files":receipt["files"],"differences":differences}))
    if differences:raise SystemExit(1)
if __name__=="__main__":main()
