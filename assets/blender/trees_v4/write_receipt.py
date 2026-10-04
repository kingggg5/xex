"""Write receipt.json for Route A step 1 (trees v4): commands, versions, timings, output hashes.

System Python, standard library only. Reads logs/blender-jobs.jsonl and every render sidecar,
hashes every output file under the evidence folder plus provenance.json and the tool scripts.

Usage:
  python write_receipt.py --evidence <route-a dir> --provenance <provenance.json> --scripts <trees_v4 dir>
      --target <target png> --out <receipt.json> --extra <extra.json>
"""
import argparse
import glob
import hashlib
import json
import os
import platform
import time


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--provenance", required=True)
    ap.add_argument("--scripts", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra", required=True)
    args = ap.parse_args()
    extra = json.load(open(args.extra, encoding="utf-8"))
    jobs = [json.loads(l) for l in open(os.path.join(args.evidence, "logs", "blender-jobs.jsonl"), encoding="utf-8") if l.strip()]
    render_timings = {}
    for side in sorted(glob.glob(os.path.join(args.evidence, "renders", "*", "*__views.json"))):
        d = json.load(open(side, encoding="utf-8"))
        rel = os.path.relpath(side, args.evidence).replace("\\", "/")
        render_timings[rel] = {"seconds_total": d.get("seconds_total"),
                               "views": {k: v.get("seconds") for k, v in d.get("views", {}).items()},
                               "render": d.get("render")}
    outputs = {}
    receipt_name = os.path.abspath(args.out)
    for path in sorted(glob.glob(os.path.join(args.evidence, "**", "*"), recursive=True)):
        if os.path.isfile(path) and os.path.abspath(path) != receipt_name:
            rel = "planning/evidence/sunmeadow-trees-v4/route-a/" + os.path.relpath(path, args.evidence).replace("\\", "/")
            outputs[rel] = {"bytes": os.path.getsize(path), "sha256": sha256(path)}
    outputs["assets/models/sunmeadow-trees-v4/candidates/quaternius/provenance.json"] = {
        "bytes": os.path.getsize(args.provenance), "sha256": sha256(args.provenance)}
    scripts = {}
    for path in sorted(glob.glob(os.path.join(args.scripts, "*.py"))):
        scripts["assets/blender/trees_v4/" + os.path.basename(path)] = {"bytes": os.path.getsize(path), "sha256": sha256(path)}
    prov = json.load(open(args.provenance, encoding="utf-8"))
    receipt = {
        "label": "BLENDER REVIEW images (Cycles CPU renders in Blender 5.2.2). These are NOT Babylon captures: no WebGPU/WebGL2, "
                 "no day/night, no in-engine numbers. Target crops are from a concept image.",
        "task": "Route A step 1: acquire, verify, measure, render and select Quaternius Stylized Nature MegaKit [Standard] trees",
        "spec": "docs/reviews/2026-10-02-trees-free-assets-decision.md sections 3.2, 4, 5",
        "written_ict": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "agent": "Claude sub-agent (Opus 5.5), Claude lane (trees and map)",
        "environment": {"os": platform.platform(), "system_python": platform.python_version(),
                        "blender": "5.2.2 LTS (hash d13f752e3b9c, built 2026-09-15)", "gltf_importer": "5.2.40",
                        "blender_path": r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
                        "render_device": "CPU only (Cycles device CPU, compute_device_type NONE; GPU untouched)",
                        "python_libs": "Pillow 12.2.0, numpy 2.4.4 (pre-installed; nothing installed)"},
        "inputs": {"archive": {k: prov["archive"][k] for k in ("name", "path", "bytes", "sha256")},
                   "licence_verdict": prov["licence"]["verdict"],
                   "target_image": {"path": "docs/ui/xexoria-town-art-target-20261001.png", "sha256": sha256(args.target)}},
        "commands": extra["commands"],
        "blender_jobs": jobs,
        "render_timings": render_timings,
        "passes": extra["passes"],
        "gate_events": extra.get("gate_events", []),
        "process_hygiene": "One Blender process at a time (sequential runner, waits for exit). Only processes started by this "
                           "agent were run; none had to be stopped. Free-RAM gate 1200 MB, 60 s retries, 300 s limit.",
        "outputs": outputs,
        "scripts": scripts,
        "not_done_here": extra["not_done_here"],
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, ensure_ascii=False)
    print("WROTE", args.out, len(outputs), "outputs")


if __name__ == "__main__":
    main()
