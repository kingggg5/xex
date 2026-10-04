"""Slot-locked Blender runner for nature_props (system Python).

  python run_blender.py [--label LANE] [--max-wait S] [--logs DIR] <tag> <script.py> [-- script args...]

1. Resolves <script.py> to an absolute path: as given if it exists (relative to the current directory), else
   relative to this folder (assets/blender/nature_props). A missing script exits 2 before Blender starts.
   (Fix 2026-10-02 22:45: t01 failed because the bare name was handed to Blender running with cwd = repo root.)
2. Starts Blender 5.2 headless through the machine-wide slot helper, which waits for the lock, for any other
   Blender to exit and for >= 1.5 GB free RAM:
     python with_blender_slot.py --label <lane> --max-wait <s> -- blender.exe -b --factory-startup
            --python-exit-code 1 --python <abs script> -- <args>
   Lane label: --label, else env NP_SLOT_LABEL, else "nature-props". Exit 75 = slot not obtained in time.
3. Logs stdout/stderr to <logs>/<tag>.{stdout,stderr}.txt and a run record <tag>.run.json (slot helper PID,
   command, start/end, exit code). Default logs folder: planning/evidence/sunmeadow-props-20261002/logs
   (or env NP_LOG_DIR). Only the process started here is ever touched.
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))


import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LOGS = Path(os.environ.get("NP_LOG_DIR", str(REPO / "planning" / "evidence" / "sunmeadow-props-20261002" / "logs")))
SLOT = str(_XEXORIA_AGENT_OUTPUT / '20261002-claude-handoff/scripts/with_blender_slot.py')
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"


def resolve_script(script: str) -> Path | None:
    p = Path(script)
    if p.is_absolute():
        return p if p.exists() else None
    for base in (Path.cwd(), HERE):
        q = (base / p).resolve()
        if q.exists():
            return q
    return None


def main():
    argv = sys.argv[1:]
    label = os.environ.get("NP_SLOT_LABEL", "nature-props")
    max_wait = 3600
    logs = LOGS
    while argv and argv[0] in ("--label", "--max-wait", "--logs"):
        if len(argv) < 2:
            print(__doc__)
            return 2
        k, v = argv[0], argv[1]
        argv = argv[2:]
        if k == "--label":
            label = v
        elif k == "--max-wait":
            max_wait = int(v)
        else:
            logs = Path(v)
    if len(argv) < 2:
        print(__doc__)
        return 2
    tag, script = argv[0], argv[1]
    rest = argv[2:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    spath = resolve_script(script)
    if spath is None:
        print(f"run_blender: script not found: {script} (looked in {Path.cwd()} and {HERE})", flush=True)
        return 2
    logs.mkdir(parents=True, exist_ok=True)
    blender_cmd = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(spath), "--"] + rest
    cmd = [sys.executable, SLOT, "--label", label, "--max-wait", str(max_wait), "--cwd", str(REPO), "--"] + blender_cmd
    out_p, err_p = logs / f"{tag}.stdout.txt", logs / f"{tag}.stderr.txt"
    start = datetime.now().astimezone()
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    with open(out_p, "w", encoding="utf-8", errors="replace") as fo, open(err_p, "w", encoding="utf-8", errors="replace") as fe:
        proc = subprocess.Popen(cmd, stdout=fo, stderr=fe, cwd=str(REPO), env=env)
        print(f"started slot helper PID {proc.pid} (label {label}) at {start.isoformat()}", flush=True)
        code = proc.wait()
    end = datetime.now().astimezone()
    lines = out_p.read_text(encoding="utf-8", errors="replace").splitlines()
    slot_lines = [l for l in lines if l.startswith("[blender-slot")]
    rec = {"tag": tag, "slot_helper_pid": proc.pid, "label": label, "command": cmd, "blender_command": blender_cmd,
           "script": str(spath), "cwd": str(REPO), "start": start.isoformat(), "end": end.isoformat(),
           "elapsed_s": round((end - start).total_seconds(), 1), "exit_code": code, "slot": slot_lines,
           "stdout": str(out_p), "stderr": str(err_p)}
    (logs / f"{tag}.run.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"exit {code} elapsed {rec['elapsed_s']}s", flush=True)
    keep = [l for l in lines if l.startswith("[np]") or l.startswith("[blender-slot") or "Error" in l
            or "Traceback" in l or "error" in l.lower()[:40]]
    for l in keep[-60:]:
        print(l[:400])
    err = err_p.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    for l in err[-25:]:
        print("ERR", l[:400])
    return code


if __name__ == "__main__":
    sys.exit(main())
