"""Stage 4 (system Python): Node post-process (meshopt EXT + KTX2), per-asset receipts and the placement manifest.

  python np_stage_post.py --kit rocks [--only id1,id2] [--no-node]

1. jobs for every helper GLB of the kit -> node apps/client/scripts/gltf-postprocess.mjs --jobs <jobs> --report
   (runtime GLBs in assets/models/sunmeadow-props/runtime/, shared KTX2 in runtime/textures/, reports in
   runtime/reports/, decoded review copies in <cache>/<kit>/review_copies/ for the re-import validation stage)
2. receipt per asset: planning/evidence/sunmeadow-props-20261002/receipts/<id>.json (recipe id, seed, parameters,
   source/licence, SHA-256 of every source/runtime file and texture, triangles per LOD, texture sizes, budgets)
3. assets/models/sunmeadow-props/manifest.json (merged across kits): id, file, LOD paths, bounds, pivot,
   collider, shadow proxy, recipe id/seed/params, placement hints.
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
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "assets" / "models" / "sunmeadow-props"
SRC, RT = OUT / "source", OUT / "runtime"
EVID = REPO / "planning" / "evidence" / "sunmeadow-props-20261002"
CACHE = Path(os.environ.get("NP_CACHE", str(_XEXORIA_AGENT_OUTPUT / '20261002-sunmeadow-props/cache')))
POST = REPO / "apps" / "client" / "scripts" / "gltf-postprocess.mjs"

LICENCE = ("Original Xexoria asset, generated procedurally by assets/blender/nature_props (recipe + seed). "
           "No third-party mesh or texture data. CC0 kits were viewed as references only.")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def rel(p):
    return Path(p).resolve().relative_to(REPO).as_posix()


def gltf_to_babylon_note():
    return ("Coordinates are glTF local (x, +y up, z; metres). Asset front = +Z (Blender -Y). Load with "
            "alignWorldAuthoredGlb (no mirroring) so local = Babylon local; the plain AUTO loader mirrors X.")


def run_node(jobs, summary):
    cmd = ["node", str(POST), "--jobs", str(jobs), "--report", str(summary)]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr, round(time.time() - t0, 1), cmd


def bounds_from_receipt(r):
    g = r.get("glb", {}) or r.get("glb_facts", {})
    for key in ("bounds", "bounds_y_up"):
        if key in g:
            return g[key]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--no-node", action="store_true")
    a = ap.parse_args()
    kdir = CACHE / a.kit
    kj = json.loads((kdir / "kit.json").read_text(encoding="utf-8"))
    ex = json.loads((kdir / "export.json").read_text(encoding="utf-8"))
    only = set(filter(None, a.only.split(",")))
    ids = [i for i in ex["assets"] if not only or i in only]
    (RT / "reports").mkdir(parents=True, exist_ok=True)
    review = kdir / "review_copies"
    review.mkdir(parents=True, exist_ok=True)
    jobs = []
    for aid in ids:
        for key, f in ex["assets"][aid]["files"].items():
            jobs.append({"input": str(SRC / f), "output": str(RT / f), "textureOut": str(RT / "textures"),
                         "report": str(RT / "reports" / (Path(f).stem + ".report.json")), "reviewOut": str(review)})
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logs = EVID / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    jobs_path = logs / f"post_{a.kit}_{stamp}.jobs.json"
    jobs_path.write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    node = {"skipped": True}
    if not a.no_node:
        code, out, err, secs, cmd = run_node(jobs_path, logs / f"post_{a.kit}_{stamp}.summary.json")
        (logs / f"post_{a.kit}_{stamp}.stdout.txt").write_text(out, encoding="utf-8")
        (logs / f"post_{a.kit}_{stamp}.stderr.txt").write_text(err, encoding="utf-8")
        node = {"exit_code": code, "seconds": secs, "command": cmd, "jobs": rel(jobs_path)}
        print(out[-6000:])
        if err.strip():
            print("STDERR:", err[-3000:])
    # ---------------------------------------------------------------- receipts + manifest
    man_path = OUT / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    man.setdefault("schema", "xexoria.sunmeadow-props-manifest/1")
    man["coordinate_note"] = gltf_to_babylon_note()
    man["generated_by"] = "assets/blender/nature_props (np_stage_post.py)"
    man.setdefault("assets", {})
    man["updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
    (EVID / "receipts").mkdir(parents=True, exist_ok=True)
    summary = {"kit": a.kit, "assets": {}, "node": node}
    for aid in ids:
        A = kj["assets"][aid]
        E = ex["assets"][aid]
        files, reports = {}, {}
        statuses = {}
        for key, f in E["files"].items():
            sp, rp = SRC / f, RT / f
            rep_p = RT / "reports" / (Path(f).stem + ".report.json")
            rep = json.loads(rep_p.read_text(encoding="utf-8")) if rep_p.exists() else None
            hr = json.loads((SRC / E["receipts"][key]).read_text(encoding="utf-8"))
            files[key] = {"source": rel(sp), "source_sha256": sha(sp), "source_bytes": sp.stat().st_size,
                          "runtime": rel(rp) if rp.exists() else None,
                          "runtime_sha256": sha(rp) if rp.exists() else None,
                          "runtime_bytes": rp.stat().st_size if rp.exists() else None,
                          "helper_receipt": rel(SRC / E["receipts"][key]), "helper_status": hr.get("status"),
                          "triangles": E["triangles"][key]}
            if rep:
                m = rep.get("metrics", {})
                files[key].update({"post_status": rep.get("status"), "budget_class": rep.get("budget_class"),
                                   "post_triangles": m.get("triangles"), "draw_calls": m.get("draw_calls"),
                                   "texture_gpu_mib": round(m.get("texture_mib", 0) or 0, 3),
                                   "glb_brotli_bytes": rep.get("sizes", {}).get("glb", {}).get("brotli_q11"),
                                   "breaches": rep.get("budget", {}).get("breaches", []),
                                   "failures": rep.get("failures", [])})
                reports[key] = rel(rep_p)
            statuses[key] = (hr.get("status"), rep.get("status") if rep else None)
        atlas = kj["atlases"][A["atlas"]]
        textures = {}
        tdir = kdir / "tex"
        for k in ("albedo", "normal", "orm"):
            p = tdir / f"{A['atlas']}_{k}.png"
            if p.exists():
                from PIL import Image
                with Image.open(p) as im:
                    textures[k] = {"png": p.name, "sha256": sha(p), "size": list(im.size), "mode": im.mode}
        ktx = sorted(x.name for x in (RT / "textures").glob(f"{A['atlas']}_*.ktx2")) if (RT / "textures").exists() else []
        mesh = A["mesh"]
        receipt = {
            "schema": "xexoria.sunmeadow-prop-receipt/1", "id": aid, "name": A.get("name"), "kit": a.kit,
            "group": A.get("group"), "priority": A.get("priority"),
            "recipe": {"id": A["recipe"], "seed": A["seed"], "params": A["params"],
                       "params_resolved": A.get("params_resolved"), "library": kj.get("lib"),
                       "regenerate": f"np_stage_bake.py -- --kit {a.kit} --atlas {A['atlas']} --only {aid}"},
            "source": {"kind": "procedural", "third_party_inputs": [], "licence": LICENCE,
                       "references_viewed": A.get("references", [])},
            "files": files, "post_reports": reports,
            "triangles": {k: v["triangles"] for k, v in mesh.items() if isinstance(v, dict) and "triangles" in v},
            "lod_ratio": {k: round(mesh[k]["triangles"] / max(mesh["lod0"]["triangles"], 1), 3) for k in ("lod1", "lod2")},
            "mesh_checks": {k: {x: mesh[k][x] for x in ("non_manifold_edges", "boundary_edges", "zero_area_faces",
                                                          "loose_verts", "parts")} for k in ("lod0", "lod1", "lod2", "collider")},
            "texture_set": {"atlas": A["atlas"], "albedo_px": atlas["albedo_px"], "data_px": atlas["data_px"],
                            "png": textures, "ktx2": ktx,
                            "texel_density_px_per_m": mesh.get("texel_density_px_m_albedo")},
            "budget_class": A["budget_class"], "lod0_target": A["lod0_tris"],
            "bake": atlas.get("bake"), "info": A.get("info"),
            "status": statuses,
        }
        rp = EVID / "receipts" / f"{aid}.json"
        rp.write_text(json.dumps(receipt, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        # manifest entry (glTF coordinates)
        b0 = mesh["lod0"]
        bmin = [b0["bounds_min"][0], b0["bounds_min"][2], -b0["bounds_max"][1]]
        bmax = [b0["bounds_max"][0], b0["bounds_max"][2], -b0["bounds_min"][1]]
        col = A.get("collider", {})
        cm = mesh["collider"]
        entry = {
            "id": aid, "name": A.get("name"), "kit": a.kit, "group": A.get("group"), "priority": A.get("priority"),
            "file": files["lod0"]["runtime"],
            "lods": [{"level": i, "file": files[f"lod{i}"]["runtime"], "triangles": files[f"lod{i}"]["triangles"],
                      "suggested_max_distance_m": d} for i, d in ((0, 28), (1, 55), (2, 110))],
            "bounds_m": {"min": [round(x, 3) for x in bmin], "max": [round(x, 3) for x in bmax]},
            "pivot": A.get("pivot", "ground contact: y = 0 is the terrain surface at the asset centre"),
            "embed_m": A.get("info", {}).get("embed_m"),
            "collider": {"shape": col.get("shape", "convex"), "kind": col.get("kind"), "blocking": col.get("blocking"),
                         "file": files["collider"]["runtime"], "triangles": files["collider"]["triangles"],
                         "polygon_xz": E.get("footprint_xz"),
                         "y_min": round(cm["bounds_min"][2], 3), "y_max": round(cm["bounds_max"][2], 3)},
            "shadow_proxy": files.get("shadow", {}).get("runtime"),
            "material": {"atlas": A["atlas"], "textures_ktx2": ktx, "alpha": atlas.get("material", {}).get("alpha_clip"),
                         "double_sided": atlas.get("material", {}).get("double_sided", False),
                         "wind_uv2": A.get("wind")},
            "recipe": {"id": A["recipe"], "seed": A["seed"], "params": A["params"]},
            "placement": A.get("placement", {}),
            "budget_class": A["budget_class"], "receipt": rel(rp),
            "status": "PASS" if all(s == ("PASS", "PASS") for s in statuses.values()) else "CHECK",
        }
        man["assets"][aid] = entry
        summary["assets"][aid] = {"status": entry["status"], "statuses": statuses}
    man["assets"] = dict(sorted(man["assets"].items()))
    man_path.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (EVID / f"post_{a.kit}_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    bad = [k for k, v in summary["assets"].items() if v["status"] != "PASS"]
    print(f"[post] {a.kit}: {len(ids)} assets, {len(bad)} not PASS {bad[:10]}")


if __name__ == "__main__":
    main()
