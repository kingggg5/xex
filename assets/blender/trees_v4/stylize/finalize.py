"""Write provenance.json (candidate folder) and receipt.json (evidence) for Route A step 2 (trees v4).

System Python. Reads the step-1 provenance (source, licence, archive hash), the final pass outputs
(stylize_report.json, verify.json, metrics.json), every pass's metrics, the gated Blender job log, and hashes
every output file and script. Nothing is downloaded or installed.

Usage:
  python finalize.py --final-pass N --passes 1,2,3
      [--report-dir <dir with stylize_report.json + verify.json>]   (default: the final pass dir)
      [--jobs-log <blender-jobs.jsonl>]...                          (default: route-a-stylized/logs)
      [--receipt-out <receipt.json>]                                (default: route-a-stylized/receipt.json)
      [--runtime-dir <runtime GLB folder> --postprocess-dir <dir with *.report.json>]

2026-10-02 export-helper migration (C-P1-TREE): the candidate GLBs are written by assets/blender/tools/export_helper.py
(receipts *.receipt.json, images in textures-shared/), and gltf-postprocess.mjs turns them into the runtime GLBs.
provenance.json pins the SHA-256 of every script, candidate file (receipts and textures-shared/ included) and, with
--runtime-dir, every runtime file plus its post-process report summary. --final-pass still names the BLENDER REVIEW
pass whose metrics.json holds the palette numbers; --report-dir names the stylize run that produced the files.
"""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timedelta, timezone

R = str(_XEXORIA_REPO)
EV = f"{R}/planning/evidence/sunmeadow-trees-v4/route-a-stylized"
OUT = f"{R}/assets/models/sunmeadow-trees-v4/candidates/quaternius-stylized"
ST = f"{R}/assets/blender/trees_v4/stylize"
STEP1_PROV = f"{R}/assets/models/sunmeadow-trees-v4/candidates/quaternius/provenance.json"
ICT = timezone(timedelta(hours=7))
STEP2_LABEL_PREFIXES = ("forge", "probe", "uvdump", "paint", "stylize", "render")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(p):
    return os.path.relpath(p, R).replace("\\", "/")


def load(p):
    return json.load(open(p, encoding="utf-8-sig"))


def atlas_dir(n):
    """Atlas used by pass n = the latest repaint at or before n (pass 1 used the original forge output)."""
    for k in range(n, 1, -1):
        d = f"{EV}/atlas-forge/out-pass{k}"
        if os.path.exists(d):
            return d
    return f"{EV}/atlas-forge/out"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final-pass", type=int, required=True)
    ap.add_argument("--passes", default="1,2,3")
    ap.add_argument("--verdict", default="")
    ap.add_argument("--report-dir", default="")
    ap.add_argument("--jobs-log", action="append", default=[])
    ap.add_argument("--receipt-out", default=f"{EV}/receipt.json")
    ap.add_argument("--runtime-dir", default="")
    ap.add_argument("--postprocess-dir", default="")
    a = ap.parse_args()
    now = datetime.now(ICT).isoformat(timespec="seconds")
    fp = f"{EV}/pass{a.final_pass}"
    rd = a.report_dir or fp
    rep = load(f"{rd}/stylize_report.json")
    ver = load(f"{rd}/verify.json")
    met = load(f"{fp}/metrics.json")
    p1 = load(STEP1_PROV)
    kit_sha = p1.get("gltf_folder_sha256", {})
    # ---------------------------------------------------------------- provenance (candidate folder)
    files = {}
    for root, _, names in os.walk(OUT):
        for n in sorted(names):
            if n == "provenance.json":
                continue
            p = os.path.join(root, n)
            files[rel(p)] = {"bytes": os.path.getsize(p), "sha256": sha(p)}
    species = {}
    for model, r in rep["models"].items():
        sp = r["species"]
        species[sp] = {
            "kit_model": model, "role": r["slot"], "height_m": r["height_m"],
            "kit_files": {f"{model}.gltf": kit_sha.get(f"{model}.gltf"), f"{model}.bin": kit_sha.get(f"{model}.bin")},
            "lod0": {"file": f"{sp}_lod0.glb", "triangles": ver["files"][f"{sp}_lod0"]["triangles"]},
            "lod1": {"file": f"{sp}_lod1.glb", "triangles": ver["files"][f"{sp}_lod1"]["triangles"]},
            "materials": r["export"]["materials"], "before": r["before"], "after": r["after"],
            "readback_all_ok": ver["files"][f"{sp}_lod0"]["all_ok"] and ver["files"][f"{sp}_lod1"]["all_ok"]}
        helper = r["export"].get("export_helper")
        if helper:
            species[sp]["export_helper"] = {"receipts": helper["receipts"], "status": helper["status"],
                                            "budget_classes": helper["budget_classes"]}
    runtime = None
    if a.runtime_dir:
        rfiles = {}
        for root, _, names in os.walk(a.runtime_dir):
            for n in sorted(names):
                q = os.path.join(root, n)
                rfiles[rel(q)] = {"bytes": os.path.getsize(q), "sha256": sha(q)}
        reports = {}
        for n in sorted(os.listdir(a.postprocess_dir)) if a.postprocess_dir else []:
            if not n.endswith(".report.json"):
                continue
            r = load(os.path.join(a.postprocess_dir, n))
            reports[n[:-len(".report.json")]] = {
                "status": r.get("status"), "budget_class": r.get("budget_class"), "tier": r.get("tier"),
                "triangles": r.get("metrics", {}).get("triangles"), "draw_calls": r.get("metrics", {}).get("draw_calls"),
                "texture_mib": r.get("metrics", {}).get("texture_mib"), "glb_bytes": r.get("sizes", {}).get("glb", {}).get("raw"),
                "breaches": r.get("budget", {}).get("breaches"), "report": rel(os.path.join(a.postprocess_dir, n))}
        runtime = {"folder": rel(a.runtime_dir), "made_by": "apps/client/scripts/gltf-postprocess.mjs (EXT_meshopt_compression + "
                   "KHR_mesh_quantization, KHR_texture_basisu: ETC1S colour, UASTC normal; one shared KTX2 folder)",
                   "files": rfiles, "postprocess": reports}
    prov = {
        "asset": "Quaternius Stylized Nature MegaKit (Standard, free) - 7 picks, STYLIZED (Route A step 2)",
        "status": ("RUNTIME ADMITTED (C-P1-TREE, not committed): candidate GLBs through the export helper, runtime "
                   "GLBs + shared KTX2 in " + rel(a.runtime_dir)) if a.runtime_dir else
                  "CANDIDATE ONLY - not integrated into the game runtime, not committed, not KTX2-compressed, "
                  "no LOD2 impostor yet",
        "written_ict": now,
        "route": "docs/reviews/2026-10-02-trees-free-assets-decision.md section 5, Route A step 3 (normalise + "
                 "stylize) on the step-2 picks of planning/evidence/sunmeadow-trees-v4/route-a/selection.json",
        "source": p1.get("source"), "licence": p1.get("licence"), "archive": p1.get("archive"),
        "extracted_copy": p1.get("extracted_copy"),
        "step1_provenance": rel(STEP1_PROV),
        "kit_files_used": {
            "meshes": "glTF/<model>.gltf + .bin of the 7 picks (imported read-only into an empty Blender scene)",
            "bark": {"Bark_NormalTree.png": kit_sha.get("Bark_NormalTree.png"),
                     "Bark_NormalTree_Normal.png": kit_sha.get("Bark_NormalTree_Normal.png"),
                     "derived": "regraded to the decision-doc bark palette and resized to 1024 px "
                                "(textures/qn_bark_albedo.png, textures/qn_bark_normal.png; textures/bark_regrade.json)"},
            "leaf_textures": "NOT used: Leaves_NormalTree_C / Leaf_Pine_C / Leaves_TwistedTree_C are single flat "
                             "colours; every card is re-mapped to the painted cluster atlas below",
            "flowers": "Flowers.png NOT used: the 38 kit flower meshes of Bush_Common_Flowers became 38 two-triangle "
                       "quads mapped to the red blossom cell of the atlas"},
        "original_work": {
            "leaf_atlas": {"file": "textures/qn_leaf_atlas_albedo.png",
                           "final_atlas_report": rel(atlas_dir(a.final_pass) + "/atlas_report.json"),
                           "final_atlas_calibration": load(atlas_dir(a.final_pass) + "/atlas_report.json").get("calibration"),
                           "made_by": "Claude forge (decision doc 4.2 step 6, source 4): Blender 5.2.2 geometry passes "
                                      "(forge_leaf_atlas.py) + numpy painting (paint_leaf_atlas.py); no photo leaves, no "
                                      "third-party pixels", "evidence": rel(f"{EV}/atlas-forge")}},
        "derived_licence_note": "Kit content is CC0-1.0 (modification and redistribution allowed without attribution; "
                                "credit kept as a courtesy). The atlas and all scripts are project-original.",
        "recipe": {"scripts": {rel(os.path.join(ST, n)): sha(os.path.join(ST, n)) for n in sorted(os.listdir(ST))
                               if n.endswith(".py")},
                   "global": rep["global"], "per_model": {m: r["recipe"] for m, r in rep["models"].items()},
                   "blender": rep["blender"], "final_pass": a.final_pass,
                   "gltf_export_options": next(iter(rep["models"].values()))["export"]["gltf_options"]},
        "runtime_contract": {"materials": "<species>_bark (OPAQUE) + <species>_foliage (MASK, alphaCutoff 0.45, "
                                          "doubleSided)", "COLOR_0": "VEC3 float multiplier, Material mode",
                             "TEXCOORD_1": "x = sway weight 0 at ground -> 1 at the tips; y = per-clump phase 0..1",
                             "pivot": "origin at the trunk's ground contact, ground = y 0 (glTF), buried skirt to "
                                      "about -0.25 m kept for slopes",
                             "extensions": "candidate GLBs: none (no meshopt, no Draco), images external in "
                                           "textures-shared/; runtime GLBs: EXT_meshopt_compression, "
                                           "KHR_mesh_quantization, KHR_texture_basisu"},
        "species": species, "files": files, "runtime": runtime}
    with open(os.path.join(OUT, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=1, ensure_ascii=False)
    # ---------------------------------------------------------------- receipt (evidence)
    jobs = []
    for log in a.jobs_log or [f"{EV}/logs/blender-jobs.jsonl"]:
        for line in open(log, encoding="utf-8"):
            try:
                j = json.loads(line)
            except Exception:
                continue
            jobs.append({k: j.get(k) for k in ("label", "job", "script", "pid", "status", "exit_code", "seconds",
                                               "peak_rss_mb", "free_mb_before", "free_mb_after", "gate_wait_s",
                                               "other_blender_before", "started", "command")})
    passes = {}
    for n in [int(x) for x in a.passes.split(",") if x]:
        pdir = f"{EV}/pass{n}"
        if not os.path.exists(f"{pdir}/metrics.json"):
            continue
        m = load(f"{pdir}/metrics.json")
        v = load(f"{pdir}/verify.json")
        params = load(f"{pdir}/params_used.json") if os.path.exists(f"{pdir}/params_used.json") else None
        ad = atlas_dir(n)
        passes[f"pass{n}"] = {
            "params_override": params, "readback_all_ok": v["all_ok"],
            "atlas": {"report": rel(ad + "/atlas_report.json"), "albedo_sha256": sha(ad + "/qn_leaf_atlas_albedo.png"),
                      "calibration": load(ad + "/atlas_report.json").get("calibration")},
            "foliage_palette_vs_target": {sp: {"p10": s["vs_target"]["dark_p10"], "p50": s["vs_target"]["mid_p50"],
                                               "p90": s["vs_target"]["light_p90"],
                                               "value_range": s["vs_target"]["swatch_value_range"],
                                               "mean_rgb_dist": s["vs_target"]["mean_rgb_dist"],
                                               "gate_pass": s["vs_target"]["gate"]["pass"]}
                                          for sp, s in m["species"].items() if s.get("vs_target")},
            "sheets": {k: rel(p) for k, p in m["outputs"].items()}, "metrics": rel(f"{pdir}/metrics.json")}
    table = {}
    for model, r in rep["models"].items():
        sp = r["species"]
        mm = met["species"][sp]
        table[sp] = {"kit_model": model, "tris_kit": r["kit_triangles"], "tris_lod0": r["export"]["lod0_tris"],
                     "tris_lod1": r["export"]["lod1_tris"], "before": r["before"], "after": r["after"],
                     "checks": r["checks"], "palette_step1": mm["step1_original"], "palette_stylized": mm["stylized"],
                     "palette_gate": mm["vs_target"]["gate"] if mm.get("vs_target") else None}
    receipt = {
        "label": "RECEIPT - Route A step 2: stylize the 7 Quaternius CC0 picks (BLENDER REVIEW evidence, not Babylon)",
        "written_ict": now, "agent": "Claude (sub-agent, resumed after a usage-limit cut-off)",
        "spec": ["docs/reviews/2026-10-02-trees-free-assets-decision.md 4.1-4.4",
                 "planning/evidence/sunmeadow-trees-v4/route-a/selection.json (per-pick fixes) + measure.json",
                 "docs/reviews/2026-10-02-blender-asset-official-docs.md (glTF export rules)"],
        "environment": {"blender": rep["blender"], "python": sys.version.split()[0], "os": platform.platform(),
                        "device": "Cycles CPU only", "gate": "one blender.exe at a time (any owner) and >= 1500 MB "
                                                             "free RAM before every job, polled every 60 s"},
        "resumed_from": {"atlas": "forge passes + painted albedo were complete (atlas-forge/out, mip coverage held to "
                                  "64 px); reviewed and applied, not redone"},
        "outputs": {"candidate_folder": rel(OUT), "provenance": rel(os.path.join(OUT, "provenance.json")),
                    "final_pass": f"pass{a.final_pass}", "files": files},
        "before_after": table, "passes": passes, "blender_jobs": jobs,
        "process_hygiene": {"max_concurrent_blender": 1, "stopped_pids": "none (no job hit its timeout)",
                            "kit_folder_written": False, "git": "not used", "installs": "none",
                            "apps_client_touched": (f"runtime GLBs + KTX2 written to {rel(a.runtime_dir)}"
                                                    if a.runtime_dir else False)},
        "not_done_here": ["Babylon captures (WebGPU + WebGL2, day + night, 4 locked views) - review here is Cycles CPU "
                          "BLENDER REVIEW under the step-1 light", "LOD2 impostor re-bake (impostor_baker.py)",
                          "KTX2 compression and alpha-mip check after compression", "runtime admission / TREE_SPOTS",
                          "addWind TEXCOORD_1 support (Codex root lane)"],
        "verdict": a.verdict}
    if runtime:
        receipt["runtime"] = {k: v for k, v in runtime.items() if k != "files"}
        receipt["not_done_here"] = [x for x in receipt["not_done_here"] if not x.startswith(("KTX2", "runtime"))]
    os.makedirs(os.path.dirname(a.receipt_out), exist_ok=True)
    with open(a.receipt_out, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, ensure_ascii=False)
    print("WROTE", os.path.join(OUT, "provenance.json"), a.receipt_out, len(jobs), "jobs")


if __name__ == "__main__":
    main()
