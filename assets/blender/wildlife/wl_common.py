"""Shared paths, constants and utilities for the Sunmeadow ambient-wildlife pipeline.

Every wildlife script imports this module. Paths are repo-relative, so scripts run from any working directory:

    blender -b --factory-startup --python-exit-code 1 --python assets/blender/wildlife/<script>.py -- <args>

Rules (task brief 2026-10-02 21:05, owner direction 21:35 "try to make procedural"):
- third-party sources are read only from the kits folders, and only when their SHA-256 matches the download log;
- outputs go to assets/models/wildlife/{work,helper,runtime,vat} and planning/evidence/wildlife-20261002;
- one Blender process machine-wide (run blender_gate.ps1 first); Cycles renders on the CPU;
- every procedural recipe is seeded, and its seed and parameters go into the receipts.
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))


import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODELS = ROOT / "assets" / "models" / "wildlife"
WORK = MODELS / "work"
HELPER = MODELS / "helper"
RUNTIME = MODELS / "runtime"
VATDIR = MODELS / "vat"
TEXTURES = HELPER / "textures"
EVIDENCE = ROOT / "planning" / "evidence" / "wildlife-20261002"
RENDERS = EVIDENCE / "renders"
LOGS = EVIDENCE / "logs"
REPORTS = EVIDENCE / "reports"
KITS = Path(str(_XEXORIA_ASSET_SOURCE / 'kits'))

# Verified third-party sources (SHA-256 from planning/evidence/wildlife-20261002/reports/download_log.json).
SOURCES = {
    "deer": (KITS / "quaternius-animals-cc0" / "UltimateAnimatedAnimals_Deer.blend",
             "E0561B31230BB104"),
    "stag": (KITS / "quaternius-animals-cc0" / "UltimateAnimatedAnimals_Stag.blend",
             "09CC635A05452D14"),
    "sheep": (KITS / "quaternius-animals-cc0" / "FarmAnimalPack_Sheep.blend", "D4F137F393E5B3E5"),
    "sheep_fbx": (KITS / "quaternius-animals-cc0" / "FarmAnimalPack_Sheep.fbx", "4A3FC559CC9F37E3"),
    "frog": (KITS / "polypizza-cc0" / "Quaternius_Frog_9Z2V8fpazF.glb", "92DC96C90E722867"),
    "rabbit": (KITS / "opengameart-animals-cc0" / "Rattel_hand-painted-bunny_bunny.blend", "C77112902209B5AD"),
    "duck": (KITS / "opengameart-animals-cc0" / "weirdybeardyman_rigged-duck_duck6.blend", "CD686D02261606C9"),
}

FPS = 30
# Player camera (llm.txt verified facts): ArcRotate radius 13 m, beta 1.18 rad, vertical FOV 1.02 rad, target 1.65 m.
CAM_RADIUS = 13.0
CAM_BETA = 1.18
CAM_FOV = 1.02
CAM_TARGET_H = 1.65
WITNESS_H = 1.80

# Hand-painted wildlife palette (sRGB hex). Harmonised with the meadow/grass spec (docs/reviews/2026-10-02-map-grass-spec.md)
# and the tree palette (trees decision §5): warm earth browns, cream, sage, never pure black or white.
PALETTE = {
    "wool_light": "#EDE3CF", "wool_mid": "#D8CBB0", "wool_shadow": "#A99A82", "wool_dirty": "#B9A37E",
    "face_dark": "#3A3029", "face_mid": "#54453A", "hoof": "#2F2924", "horn": "#C9B48C",
    "deer_coat": "#A8683A", "deer_coat_hi": "#C98D52", "deer_coat_lo": "#6E4127", "deer_belly": "#E7D7B8",
    "rabbit_coat": "#8E6B4A", "rabbit_coat_hi": "#B48E66", "rabbit_coat_lo": "#5E4430", "rabbit_belly": "#E9DFC9",
    "duck_head": "#2F6B4E", "duck_head_hi": "#4FA07A", "duck_breast": "#7A4630", "duck_body": "#A8A39A",
    "duck_bill": "#D9B53C", "duck_collar": "#ECE6D6", "duck_wing_blue": "#3F5FA8", "duck_feet": "#D9822B",
    "frog_green": "#5E8B3A", "frog_green_hi": "#9DBB5A", "frog_belly": "#E1D7A8", "frog_dark": "#2F4A26",
    "koi_red": "#D9542A", "koi_white": "#F0E9DC", "koi_black": "#2C2A2E", "koi_gold": "#E9A93A", "koi_plat": "#D7D3C6",
    "fish_silver": "#B9C3C4", "fish_back": "#4A6A6E", "fish_belly": "#ECE8DC",
    "bird_brown": "#7C5A3E", "bird_brown_hi": "#A98158", "bird_cream": "#E8DCC1", "bird_dark": "#3E3229",
    "bird_red": "#B8553A", "bird_blue": "#4D79B0", "beak": "#C99A4A",
    "bfly_yellow": "#F0CC3E", "bfly_white": "#EEEADB", "bfly_blue": "#6D8DE0", "bfly_orange": "#E58A34",
    "bfly_red": "#B9443A", "bfly_vein": "#33281F", "bfly_body": "#3A3029",
    "dfly_teal": "#2FA39A", "dfly_blue": "#4A78C8", "dfly_red": "#C24A34", "dfly_wing": "#DCEBEA",
    "bee_gold": "#E3A92E", "bee_dark": "#2E261F", "bee_wing": "#E4EEF0",
    "firefly_glow": "#F4E58A", "firefly_core": "#FFF6C8", "firefly_body": "#3A3530",
    "eye": "#1E1A18", "eye_hi": "#F2EEE6", "nose_pink": "#C98C86",
}


def hex_to_linear(h: str) -> tuple:
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c)


def hex_to_srgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest().upper()


def verify_source(key: str) -> tuple:
    """Refuse to read a third-party source whose hash differs from the download log."""
    path, prefix = SOURCES[key]
    digest = sha256_file(path)
    if not digest.startswith(prefix):
        raise RuntimeError(f"{path.name}: sha256 {digest} does not start with {prefix}; refusing a modified source")
    return path, digest


def write_json(path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _json_default(o):
    if hasattr(o, "to_tuple"):
        return [round(v, 6) for v in o.to_tuple()]
    if isinstance(o, Path):
        return rel(o)
    if hasattr(o, "__iter__"):
        return list(o)
    return str(o)


def rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def script_args() -> list:
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def arg_value(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return default


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


class Rng:
    """Seeded generator for procedural recipes; every draw is reproducible from (recipe, seed)."""

    def __init__(self, recipe: str, seed: int):
        self.recipe = recipe
        self.seed = int(seed)
        self.r = random.Random(f"{recipe}:{self.seed}")

    def uniform(self, a, b):
        return self.r.uniform(a, b)

    def choice(self, seq):
        return self.r.choice(list(seq))

    def jitter(self, v, frac):
        return v * (1.0 + self.r.uniform(-frac, frac))

    def randint(self, a, b):
        return self.r.randint(a, b)


def smoothstep(a: float, b: float, x: float) -> float:
    if b == a:
        return 1.0 if x >= b else 0.0
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def deg(v: float) -> float:
    return math.radians(v)


def game_camera_location(target_xy=(0.0, 0.0), alpha_deg=-90.0):
    """Blender position of the ArcRotate player camera for a target on the ground at target_xy.

    Babylon beta is measured from +Y (up). Height above the target = R*cos(beta); horizontal = R*sin(beta).
    alpha_deg is the compass direction (Blender XY plane) from the target to the camera.
    """
    h = CAM_RADIUS * math.cos(CAM_BETA)
    d = CAM_RADIUS * math.sin(CAM_BETA)
    a = math.radians(alpha_deg)
    tx, ty = target_xy
    return (tx + d * math.cos(a), ty + d * math.sin(a), CAM_TARGET_H + h), (tx, ty, CAM_TARGET_H)
