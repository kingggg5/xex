"""Run one Route A step-2 art pass end to end (trees v4). System Python; Blender only through run_gate.py.

  1. stylize_kit.py (one Blender process, all 7 picks)  -> helper GLBs + receipts in the candidate folder,
                                                            images in <candidate>/textures-shared/, passN/stylize_report.json
  2. verify_glb.py (system Python read-back)             -> passN/verify.json
  3. gltf-postprocess.mjs (Node, one job per GLB)         -> runtime GLBs (EXT_meshopt + KTX2) in --runtime-out,
                                                            one shared KTX2 folder, passN/postprocess/*.report.json
  4. render_stylized.py x2 (one Blender process each, gated: 1920x1080 player + mask; 768x432 player/close/side)
  5. review_sheets.py                                    -> passN/metrics.json + sheets

Usage:
  python run_pass.py --pass N [--params <json>] [--samples 32] [--skip-stylize] [--skip-render]
                     [--skip-postprocess] [--pass-dir <dir>] [--log-dir <dir>] [--runtime-out <dir>] [--tier high]

Step 3 was added with the export-helper migration (2026-10-02, C-P1-TREE; docs/reviews/2026-10-02-export-helper.md
section 7.1). The budget class of each job comes from the GLB's receipt (tree_lod0/1, bush_lod0/1). --pass-dir and
--log-dir let a lane write its evidence outside route-a-stylized/.
"""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import argparse
import json
import os
import subprocess
import sys
import time

R = str(_XEXORIA_REPO)
KIT = str(_XEXORIA_ASSET_SOURCE / 'kits/quaternius-stylized-nature-megakit/extracted/glTF')
EV = f"{R}/planning/evidence/sunmeadow-trees-v4/route-a-stylized"
OUT = f"{R}/assets/models/sunmeadow-trees-v4/candidates/quaternius-stylized"
TEX = f"{OUT}/textures"
ST = f"{R}/assets/blender/trees_v4/stylize"
POSTPROCESS = f"{R}/apps/client/scripts/gltf-postprocess.mjs"
RUNTIME = f"{R}/apps/client/src/assets/models/sunmeadow-trees-v4"  # the folder environment.ts loads
SPECIES = [("qn_broadleaf_s", "broadleaf"), ("qn_broadleaf_m", "broadleaf"), ("qn_broadleaf_l", "broadleaf"),
           ("qn_conifer_m", "conifer"), ("qn_conifer_l", "conifer"), ("qn_bush_flowers", "bush"), ("qn_bush", "bush")]


def run(cmd):
    print("[cmd]", subprocess.list2cmdline(cmd), flush=True)
    t0 = time.time()
    r = subprocess.run(cmd)
    print(f"[exit {r.returncode}] {time.time() - t0:.1f} s", flush=True)
    if r.returncode != 0:
        sys.exit(r.returncode)


def postprocess(a, pdir):
    """Runtime GLBs: one gltf-postprocess.mjs job per helper GLB, class from its receipt, one shared KTX2 folder."""
    rdir = f"{pdir}/postprocess"
    os.makedirs(rdir, exist_ok=True)
    jobs = []
    for sp, _ in SPECIES:
        for lod in (0, 1):
            stem = f"{sp}_lod{lod}"
            receipt = json.load(open(f"{OUT}/{stem}.receipt.json", encoding="utf-8"))
            if receipt.get("status") != "PASS":
                sys.exit(f"{stem}: export receipt status {receipt.get('status')}")
            jobs.append({"input": f"{OUT}/{stem}.glb", "output": f"{a.runtime_out}/{stem}.glb",
                         "class": receipt["budget_class"], "tier": a.tier,
                         "textureOut": f"{a.runtime_out}/textures", "report": f"{rdir}/{stem}.report.json"})
    with open(f"{rdir}/jobs.json", "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, indent=1)
    run(["node", POSTPROCESS, "--jobs", f"{rdir}/jobs.json", "--report", f"{rdir}/postprocess-summary.json"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="n", type=int, required=True)
    ap.add_argument("--params", default="")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--skip-stylize", action="store_true")
    ap.add_argument("--skip-render", action="store_true")
    ap.add_argument("--skip-postprocess", action="store_true")
    ap.add_argument("--pass-dir", default="")
    ap.add_argument("--log-dir", default=f"{EV}/logs")
    ap.add_argument("--runtime-out", default=RUNTIME)
    ap.add_argument("--tier", default="high")
    ap.add_argument("--tag", default="", help="job/receipt tag (default passN)")
    a = ap.parse_args()
    tag = a.tag or f"pass{a.n}"
    pdir = a.pass_dir or f"{EV}/pass{a.n}"
    os.makedirs(f"{pdir}/renders", exist_ok=True)
    os.makedirs(a.log_dir, exist_ok=True)
    gate = [sys.executable, f"{ST}/run_gate.py", "--log", f"{a.log_dir}/blender-jobs.jsonl", "--stdout-dir", a.log_dir]
    if not a.skip_stylize:
        job = "|".join([f"{ST}/stylize_kit.py", "--src", KIT, "--atlas", f"{TEX}/qn_leaf_atlas_albedo.png",
                        "--layout", f"{EV}/atlas-forge/passes/layout.json", "--bark-albedo", f"{TEX}/qn_bark_albedo.png",
                        "--bark-normal", f"{TEX}/qn_bark_normal.png", "--out", OUT,
                        "--report", f"{pdir}/stylize_report.json", "--tag", tag]
                       + (["--params", a.params] if a.params else []))
        run(gate + ["--label", f"stylize_{tag}", "--job", job])
    run([sys.executable, f"{ST}/verify_glb.py", "--dir", OUT, "--species", ",".join(f"{s}:{k}" for s, k in SPECIES),
         "--out", f"{pdir}/verify.json"])
    if not a.skip_postprocess:
        postprocess(a, pdir)
    if not a.skip_render:
        names = ",".join(f"{s}_lod0" for s, _ in SPECIES)
        kinds = ",".join(k for _, k in SPECIES)
        base = [f"{ST}/render_stylized.py", "--src", OUT, "--model", names, "--kinds", kinds, "--keep-scale",
                "--out", f"{pdir}/renders", "--samples", str(a.samples), "--tag", f"pass{a.n}"]
        job_a = "|".join(base + ["--views", "player", "--res", "1920x1080", "--suffix", "_1080", "--mask"])
        job_b = "|".join(base + ["--views", "player,close,side"])
        run(gate + ["--label", f"render_p{a.n}", "--job", job_a, "--job", job_b])
    if a.skip_render:
        return
    run([sys.executable, f"{ST}/review_sheets.py", "--pass-dir", pdir, "--label", f"pass {a.n}",
         "--target", f"{R}/docs/ui/xexoria-town-art-target-20261001.png",
         "--step1-picks", f"{R}/planning/evidence/sunmeadow-trees-v4/route-a/renders/picks-1080",
         "--step1-views", f"{R}/planning/evidence/sunmeadow-trees-v4/route-a/renders/pass5",
         "--stylize-report", f"{pdir}/stylize_report.json", "--verify", f"{pdir}/verify.json",
         "--step1-palettes", f"{R}/planning/evidence/sunmeadow-trees-v4/route-a/target-vs-candidates.json"])
    if a.params:
        with open(f"{pdir}/params_used.json", "w", encoding="utf-8") as fh:
            json.dump(json.load(open(a.params, encoding="utf-8")), fh, indent=1)


if __name__ == "__main__":
    main()
