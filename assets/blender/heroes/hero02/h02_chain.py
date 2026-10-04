"""Run several hero 02 stages inside ONE Blender session (the shared machine allows one Blender at a time, and
the map-dressing lane queues its own jobs back to back, so one slot for the whole chain is kinder than six).

blender -b --factory-startup --python h02_chain.py -- staff_prep staff_simplify staff_textures staff_lods clips \
        export postprocess sidecar test validator renders:pass1 label:pass1

Blender stages run with runpy (each opens its own .blend first, so state does not leak); node and system-Python
stages run as subprocesses from the repo root. Any failure stops the chain with a non-zero exit code.
"""
import runpy
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import h02_common as C  # noqa: E402

log = C.Log("h02_chain")
argv0 = sys.argv[0]
steps = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CLIPS = ("base.idle,base.walk,base.run,caster.attack_1,caster.attack_2,mage.skill_nova,mage.skill_gale,"
         "mage.skill_rift,mage.skill_bolt,mage.skill_ward,mage.skill_starfall,base.hit_light,base.dodge,base.death")


def blender_stage(script, args=()):
    sys.argv = [argv0, "--", *args]
    runpy.run_path(str(HERE / script), run_name="__main__")


def cmd(args, cwd=ROOT, log_name=None, check=True):
    t0 = time.time()
    res = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (res.stdout or "") + (res.stderr or "")
    if log_name:
        (C.LOGS / log_name).write_text(out, encoding="utf-8")
    log(" ".join(str(a) for a in args[:3]), "exit", res.returncode, f"{time.time() - t0:.1f}s")
    tail = out.strip().splitlines()[-6:]
    for line in tail:
        log("   ", line[:300])
    if check and res.returncode != 0:
        raise RuntimeError(f"{args[:3]} failed with exit {res.returncode}")
    return res.returncode


for step in steps:
    name, _, arg = step.partition(":")
    log("step", step)
    t0 = time.time()
    if name == "highpoly":
        blender_stage("h02_build_highpoly.py")
    elif name == "atlas":
        blender_stage("h02_atlas_bake.py")
    elif name == "textures":
        cmd(["python", str(HERE / "h02_textures.py")], log_name="run_textures.txt")
    elif name == "simplify":
        cmd(["node", str(HERE / "h02_simplify.mjs")], log_name="run_simplify.txt")
    elif name == "rig":
        blender_stage("h02_build_lods_rig.py")
    elif name == "clips":
        blender_stage("h02_clips.py")
    elif name == "staff_prep":
        blender_stage("h02_staff.py", ["--phase", "prep"])
    elif name == "staff_simplify":
        cmd(["node", str(HERE / "h02_staff_simplify.mjs")],
            log_name="run_staff_simplify.txt")
    elif name == "staff_textures":
        cmd(["python", str(HERE / "h02_textures_staff.py")], log_name="run_staff_textures.txt")
    elif name == "staff_lods":
        blender_stage("h02_staff.py", ["--phase", "lods"])
    elif name == "hair_policy":
        blender_stage("h02_hair_policy.py")
    elif name == "cloth_floor":
        blender_stage("h02_cloth_floor.py")
    elif name == "audit_deform":
        blender_stage("h02_deformation_audit.py")
    elif name == "repair_weights":
        blender_stage("h02_repair_weights.py", ["--expand"] if arg == "expand" else [])
    elif name == "review_fast":
        blender_stage("h02_deformation_audit.py")
        blender_stage("h02_review_fast.py", ["--tag", arg or "pass2"])
    elif name == "repair_meshes":
        blender_stage("h02_repair_meshes.py")
    elif name == "export":
        blender_stage("h02_export.py")
    elif name == "postprocess":
        cmd(["node", "apps/client/scripts/gltf-postprocess.mjs", "--jobs", str(HERE / "postprocess-jobs.json"),
             "--report", "planning/evidence/hero02-witch-20261002/reports/postprocess-summary.json"],
            log_name="run_postprocess.txt")
    elif name == "sidecar":
        cmd(["python", str(HERE / "h02_sidecar.py")], log_name="run_sidecar.txt")
    elif name == "test":
        cmd(["node", "--test", "tests/hero02-witch-runtime.test.mjs"], cwd=ROOT / "apps" / "client",
            log_name="run_smoke_test.txt")
    elif name == "validator":
        cmd(["node", "tools/validate-minotaur-runtime.mjs", "--input",
             "assets/models/heroes/hero02/runtime/hero02_witch_lod0.glb", "--out",
             "planning/evidence/hero02-witch-20261002/reports/validate_runtime_lod0.json", "--expected-clips", CLIPS,
             "--expected-height", "1.97"], log_name="run_validator.txt", check=False)
    elif name == "reimport":
        blender_stage("h02_reimport.py")
    elif name == "renders":
        blender_stage("h02_render_review.py", ["--tag", arg or "pass1", "--samples", "32"])
    elif name == "label":
        cmd(["python", str(HERE / "h02_label.py"), arg or "pass1"], log_name=f"run_label_{arg or 'pass1'}.txt")
    elif name == "debug":
        blender_stage("h02_debug_frames.py", arg.split("|"))
    else:
        raise ValueError(f"unknown step {step}")
    log("step done", step, f"{time.time() - t0:.1f}s")
log("chain done")
