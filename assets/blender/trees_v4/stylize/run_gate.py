"""Run Blender 5.2.2 headless jobs one at a time behind a strict resource gate.

Route A step 2 (trees v4 stylization) helper. System Python + psutil (pre-installed; nothing installed).
Before EVERY job:
  1. free physical memory must be >= --min-free-mb (default 1500 MB), and
  2. no blender.exe may be running (any owner: other sessions also use Blender);
  otherwise wait 60 s and re-check (up to --max-wait-s, default 4 h). A job that never clears the gate is
  recorded as GATE_TIMEOUT and the runner stops (later jobs depend on earlier ones).
Then ONE Blender process is started (Cycles device CPU), waited for, and a JSON line (command, PID, exit
code, seconds, free RAM before/after, gate waits) is appended to --log. Only the PID started here is ever
stopped (on --job-timeout-s).

Usage:
  python run_gate.py --log <jobs.jsonl> --stdout-dir <dir> --job "<script.py>|arg1|arg2..." [--job ...]
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import psutil

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
ICT = timezone(timedelta(hours=7))


def free_mb():
    return round(psutil.virtual_memory().available / 1048576)


def blender_pids():
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info["name"] or "").lower() == "blender.exe":
                out.append(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--job", action="append", required=True)
    ap.add_argument("--min-free-mb", type=int, default=1500)
    ap.add_argument("--max-wait-s", type=int, default=4 * 3600)
    ap.add_argument("--poll-s", type=int, default=60)
    ap.add_argument("--job-timeout-s", type=int, default=3600)
    ap.add_argument("--stdout-dir", default=None)
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    overall = 0
    for index, job in enumerate(args.job):
        parts = job.split("|")
        script, script_args = parts[0], parts[1:]
        waited, events = 0, []
        while True:
            mem, others = free_mb(), blender_pids()
            if mem >= args.min_free_mb and not others:
                break
            if waited >= args.max_wait_s:
                break
            events.append({"t": datetime.now(ICT).isoformat(timespec="seconds"), "free_mb": mem, "blender_pids": others})
            print(f"[gate] free {mem} MB (need {args.min_free_mb}), other blender.exe {others}: waiting {args.poll_s} s",
                  flush=True)
            time.sleep(args.poll_s)
            waited += args.poll_s
        record = {"label": args.label, "job": index, "script": script, "args": script_args, "free_mb_before": mem,
                  "other_blender_before": others, "gate_wait_s": waited, "gate_events": events[-20:],
                  "started": datetime.now(ICT).isoformat(timespec="seconds")}
        if mem < args.min_free_mb or others:
            record["status"] = "GATE_TIMEOUT"
            with open(args.log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[stop] {json.dumps(record, ensure_ascii=False)}", flush=True)
            sys.exit(3)
        cmd = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", script, "--"] + script_args + [
            "--cycles-device", "CPU"]
        record["command"] = subprocess.list2cmdline(cmd)
        t0 = time.time()
        out_path = None
        handle = None
        if args.stdout_dir:
            out_path = f"{args.stdout_dir}/job_{args.label or 'x'}_{index:02d}_{int(t0)}.log"
            handle = open(out_path, "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(cmd, stdout=handle or None, stderr=subprocess.STDOUT if handle else None)
        record["pid"] = proc.pid
        print(f"[run] job {index} pid {proc.pid}: {script} {' '.join(script_args)}", flush=True)
        peak = 0
        try:
            ps = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            ps = None
        timed_out = False
        while proc.poll() is None:
            try:
                if ps is not None:
                    peak = max(peak, ps.memory_info().rss)
            except psutil.NoSuchProcess:
                pass
            if time.time() - t0 > args.job_timeout_s:
                proc.kill()          # only the PID this runner started
                timed_out = True
                break
            time.sleep(0.5)
        code = proc.wait()
        if handle:
            handle.close()
        record["exit_code"] = code
        record["seconds"] = round(time.time() - t0, 1)
        record["peak_rss_mb"] = round(peak / 1048576)
        record["free_mb_after"] = free_mb()
        record["stdout_log"] = out_path
        record["status"] = "TIMEOUT_KILLED" if timed_out else ("OK" if code == 0 else "FAILED")
        if record["status"] != "OK":
            overall = 2
        with open(args.log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[done] job {index} {record['status']} {record['seconds']} s peak {record['peak_rss_mb']} MB", flush=True)
        if record["status"] != "OK":
            break
    sys.exit(overall)


if __name__ == "__main__":
    main()
