"""Run Blender 5.2.2 headless jobs one at a time with a free-RAM gate.

Route A step 1 (trees v4) helper. Runs with the system Python (no installs).
For each job:
  1. check free physical memory; if < --min-free-mb, wait 60 s and re-check,
     up to --max-wait-s (default 300 s); if it is still low the job is recorded
     as LOW_MEMORY and skipped, so the caller can split it into smaller runs;
  2. start ONE Blender process, wait for it to exit (no parallel Blender);
  3. append a JSON line (command, PID, exit code, seconds, free RAM before and
     after) to --log.

Usage:
  python run_blender.py --log <jobs.jsonl> --job "<script.py>|arg1|arg2..." [--job ...]
"""
import argparse
import ctypes
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
ICT = timezone(timedelta(hours=7))


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_mb():
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return round(stat.ullAvailPhys / 1048576)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--job", action="append", required=True)
    ap.add_argument("--min-free-mb", type=int, default=1200)
    ap.add_argument("--max-wait-s", type=int, default=300)
    ap.add_argument("--stdout-dir", default=None)
    args = ap.parse_args()
    overall = 0
    for index, job in enumerate(args.job):
        parts = job.split("|")
        script, script_args = parts[0], parts[1:]
        waited = 0
        mem = free_mb()
        while mem < args.min_free_mb and waited < args.max_wait_s:
            print(f"[gate] free {mem} MB < {args.min_free_mb} MB, waiting 60 s", flush=True)
            time.sleep(60)
            waited += 60
            mem = free_mb()
        record = {"job": index, "script": script, "args": script_args,
                  "free_mb_before": mem, "gate_wait_s": waited,
                  "started": datetime.now(ICT).isoformat(timespec="seconds")}
        if mem < args.min_free_mb:
            record["status"] = "LOW_MEMORY_SKIPPED"
            overall = 3
        else:
            cmd = [BLENDER, "-b", "--factory-startup", "--python", script, "--"] + script_args
            record["command"] = subprocess.list2cmdline(cmd)
            t0 = time.time()
            out_path = None
            if args.stdout_dir:
                out_path = f"{args.stdout_dir}/job{index:02d}_{int(t0)}.log"
                handle = open(out_path, "w", encoding="utf-8", errors="replace")
            else:
                handle = None
            proc = subprocess.Popen(cmd, stdout=handle or None, stderr=subprocess.STDOUT if handle else None)
            record["pid"] = proc.pid
            print(f"[run] job {index} pid {proc.pid}: {script} {' '.join(script_args)}", flush=True)
            code = proc.wait()
            if handle:
                handle.close()
            record["exit_code"] = code
            record["seconds"] = round(time.time() - t0, 1)
            record["free_mb_after"] = free_mb()
            record["stdout_log"] = out_path
            record["status"] = "OK" if code == 0 else "FAILED"
            if code != 0:
                overall = 2
        with open(args.log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"[done] {json.dumps(record)}", flush=True)
    sys.exit(overall)


if __name__ == "__main__":
    main()
