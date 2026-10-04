"""Shared paths, constants and small utilities for the hero 02 (witch, Mage) Blender pipeline.

Every hero 02 script imports this module. Paths are repo-relative so the scripts run from any working directory:

    blender --background --factory-startup --python-exit-code 1 --python assets/blender/heroes/hero02/<script>.py -- <args>

Rules (docs/reviews/2026-10-02-hero02-witch-integration.md):
- the owner's source files are only read from assets/models/heroes/hero02/source/owner (verified copies);
- outputs go to assets/models/heroes/hero02/{work,helper,runtime} and planning/evidence/hero02-witch-20261002;
- one Blender process at a time, Cycles on the CPU.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MODELS = ROOT / "assets" / "models" / "heroes" / "hero02"
SOURCE = MODELS / "source" / "owner"
UAL_DIR = MODELS / "source" / "third-party" / "ual1-standard-2025-06-10"
WORK = MODELS / "work"
HELPER = MODELS / "helper"
RUNTIME = MODELS / "runtime"
EVIDENCE = ROOT / "planning" / "evidence" / "hero02-witch-20261002"
RENDERS = EVIDENCE / "renders"
LOGS = EVIDENCE / "logs"
REPORTS = EVIDENCE / "reports"

SRC_8K = SOURCE / "hero02_mage_p20_smartuv_pbr_source.glb"          # unrigged bake source (8K base colour)
SRC_RIG = SOURCE / "hero02_mage_p20_smartuv_pbr_rig_animations_4k.glb"  # Tripo Mixamo rig + 8 clips (reference)
SRC_STAFF = SOURCE / "hero02_staff_p20_smartuv_pbr_source_4k.glb"
UAL_GLTF = UAL_DIR / "AnimationLibrary_Godot_Standard.gltf"

EXPECTED_SHA256 = {
    SRC_8K.name: "c883f6b6a0905bef32375883a9f128008e2c3762cc74cd0542152ba2483f01b6",
    SRC_RIG.name: "5e073635c679f52a7638c347c446f7bd03f2f3ad3d4e518a24c68e73b5d5291b",
    SRC_STAFF.name: "d0a320f5d13219b0a3afa0ea777bf72237a9d72c7c428ee62e53675866f39264",
    UAL_GLTF.name: "0ff075c7ad6855c5c2c37a171592ee8f0d6ab2f58259e2be77a9b63dd8027765",
}

FPS = 30
CROWN_HEIGHT_M = 1.80          # decisions §2: Mage 1.80 m without the hat (skull crown)
LOD_TRIS = {0: 12000, 1: 6000, 2: 2500}
STAFF_TRIS = {0: 2000, 1: 1000, 2: 400}   # weapon budget 2.5k (decisions §6); the repo 'prop' class gates at 2,000
ATLAS = 2048


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_sources(paths=None) -> dict:
    """Refuse to run on anything but the verified copies of the owner's files."""
    out = {}
    for p in paths or (SRC_8K, SRC_RIG, SRC_STAFF):
        digest = sha256_file(p)
        want = EXPECTED_SHA256.get(p.name)
        if want and digest != want:
            raise RuntimeError(f"{p.name}: sha256 {digest} != expected {want}; refusing to use a modified source")
        out[p.name] = digest
    return out


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")
    tmp.replace(path)


def _json_default(o):
    if hasattr(o, "to_tuple"):
        return [round(v, 6) for v in o.to_tuple()]
    if hasattr(o, "__iter__"):
        return list(o)
    return str(o)


def rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def script_args() -> list:
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


class Log:
    def __init__(self, name: str):
        LOGS.mkdir(parents=True, exist_ok=True)
        self.path = LOGS / f"{name}.log"
        self.t0 = time.time()
        self.fh = self.path.open("a", encoding="utf-8")
        self(f"==== {name} start {time.strftime('%Y-%m-%d %H:%M:%S')}")

    def __call__(self, *parts):
        line = f"[{time.time() - self.t0:8.2f}s] " + " ".join(str(p) for p in parts)
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()


def smoothstep(a: float, b: float, x: float) -> float:
    if b == a:
        return 1.0 if x >= b else 0.0
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def deg(v: float) -> float:
    return math.radians(v)
