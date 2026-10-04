#!/usr/bin/env python3
"""Turnaround QA gate and Tripo P2.0 multi-view prep for Xexoria concept images.

The owner's rule: an image that is wrong for 3D is regenerated, never "fixed
later", and nothing reaches Tripo (paid credits) until its view set passes.
This tool is the automatic half of that gate (Claude's design review is the
other half). It reads a turnaround set, measures the silhouettes and writes:

  report.json      every check with value, threshold and PASS/WARN/FAIL, plus
                   the overall verdict PASS or REGEN
  contact.png      the views side by side with bbox, baselines, centre lines,
                   thin parts, shadows, and the mirror overlays
  regen_notes.md   concrete English fix instructions for froggy

With --prep it also normalises a PASS set for Tripo multi-view upload (same
pixels-per-height and baseline, centred, 2048x2048, white or alpha) and
writes receipt.json with SHA-256 hashes and the applied transforms.

Inputs (read-only; source files are never modified):
  * a folder holding front/back/left/right images (png/jpg/webp), optional
    hero34 and palette; names are matched by token (front.png, mossling_back.webp)
  * a .zip delivery with the same files, or archive.zip!member/path.png
  * a single sheet image, auto-split into panels along background gutters
  * explicit files: --view front=a.png --view back=b.png ...
  * unnamed files (for example "ChatGPT Image ....png"): --order front,left,right,back,skip

Examples:
  python tools/art/turnaround_qa.py deliveries/turnarounds_mossling_v1.zip --out qa/mossling
  python tools/art/turnaround_qa.py "deliveries/hero/01" --order front,left,right,back,skip --out qa/hero01
  python tools/art/turnaround_qa.py sheet.png --sheet-order front,left,back,right --out qa/sheet
  python tools/art/turnaround_qa.py set_dir --out qa/x --prep tripo_upload/x            # PASS sets only
  python tools/art/turnaround_qa.py set_dir --out qa/x --prep tripo_upload/x --force    # override, logged

Exit codes: 0 = PASS, 2 = REGEN, 1 = error. Dependencies: numpy and Pillow only.
Thresholds live in turnaround_qa.config.json next to this file (override with --config).
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import io
import json
import math
import platform
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write("turnaround_qa.py needs numpy and Pillow; this tool installs nothing.\n")
    raise SystemExit(1)
import PIL
from PIL import Image, ImageDraw, ImageFont, ImageOps

TOOL_NAME = "turnaround_qa.py"
TOOL_VERSION = "1.0.0"
ROLES = ("front", "left", "back", "right")
EXTRA_ROLES = ("hero34", "palette")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
CONFIG_PATH = Path(__file__).with_name("turnaround_qa.config.json")

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_RANK = {SKIP: 0, PASS: 1, WARN: 2, FAIL: 3}

DEFAULT_CONFIG: dict = {
    "schema": "xexoria.turnaround_qa.config/1",
    "required_views": ["front", "back", "left", "right"],
    "analysis_max_side": 1024,
    "target": {"canvas_px": 2048, "fill_height": 0.80, "max_fill_width": 0.94},
    "segmentation": {
        "border_strip_frac": 0.02,
        "diff_min": 14.0,
        "diff_noise_k": 3.0,
        "alpha_threshold": 128,
        "open_frac": 0.0015,
        "close_frac": 0.004,
        "keep_component_frac": 0.002,
        "fill_holes_max_frac": 0.02,
        "soft_alpha_lo": 0.6,
        "soft_alpha_hi": 1.5,
    },
    "shadow": {
        "enabled": True,
        "k_min": 0.35,
        "k_max": 0.985,
        "chroma_tol": 0.06,
        "smooth_max": 9.0,
        "edge_grad_max": 4.0,
        "band_above_frac": 0.12,
        "floor_anchor_frac": 0.08,
        "min_area_frac": 0.0005,
    },
    "checks": {
        "resolution": {"pass_min_side": 2048, "fail_min_side": 1024, "pass_subject_px": 1500, "fail_subject_px": 900},
        "aspect": {"square_tol": 0.01},
        "background": {"pass_noise": 6.0, "fail_noise": 20.0, "pass_range": 10.0, "pass_white_dist": 12.0, "fail_cover": 0.75},
        "centring": {"pass": 0.03, "warn": 0.10},
        "margins": {"fail_px": 1, "pass_frac": 0.03},
        "fill": {"pass": [0.70, 0.90], "warn": [0.50, 0.97]},
        "height": {"pass": 0.03, "warn": 0.04},
        "baseline": {"pass": 0.015, "warn": 0.03},
        "width_front_back": {"pass": 0.05, "warn": 0.08},
        "width_left_right": {"pass": 0.05, "warn": 0.08},
        "mirror_left_right": {"pass": 0.90, "warn": 0.85, "shift_search_frac": 0.03, "asymmetry_relaxes": True},
        "mirror_front_back": {"pass": 0.90, "warn": 0.88, "shift_search_frac": 0.03},
        "thin_parts": {"diameter_frac_of_frame": 0.03, "min_extent_frac": 0.05, "min_extent_diameters": 2.5,
                       "pass": 0.005, "warn": 0.02},
        "components": {"warn_frac": 0.002, "fail_frac": 0.01},
        "shadow": {"pass_area": 0.01, "fail_reach": 0.25, "fail_area": 0.15, "fail_darkness": 0.25},
        "lighting": {"pass": 0.08, "warn": 0.15, "single_view_warn": 0.25},
        "palette": {"pass": 10.0, "warn": 16.0, "clusters": 8, "min_cluster_frac": 0.04},
        "view_colour_consistency": {"pass": 8.0, "warn": 14.0},
        "pose": {"arm_gap_pass": 0.15, "arm_gap_fail": 0.03},
        "profile": {"warn_above": 0.85},
    },
}


# --------------------------------------------------------------------------- config


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def load_config(path: str | None = None) -> dict:
    """Built-in defaults, then turnaround_qa.config.json, then --config."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.is_file():
        cfg = _deep_merge(cfg, json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    if path:
        cfg = _deep_merge(cfg, json.loads(Path(path).read_text(encoding="utf-8")))
    return cfg


# --------------------------------------------------------------------------- small helpers


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def grade_max(value: float, pass_max: float, warn_max: float) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return SKIP
    if value <= pass_max:
        return PASS
    return WARN if value <= warn_max else FAIL


def grade_min(value: float, pass_min: float, warn_min: float) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return SKIP
    if value >= pass_min:
        return PASS
    return WARN if value >= warn_min else FAIL


def worst(statuses) -> str:
    out = SKIP
    for s in statuses:
        if _RANK[s] > _RANK[out]:
            out = s
    return out


def _r(x, nd=4):
    if x is None:
        return None
    if isinstance(x, (np.floating, float)):
        return round(float(x), nd)
    if isinstance(x, (np.integer, int)):
        return int(x)
    return x


def hexcol(rgb) -> str:
    r, g, b = [int(max(0, min(255, round(float(v))))) for v in rgb[:3]]
    return f"#{r:02X}{g:02X}{b:02X}"


# --------------------------------------------------------------------------- colour science


def srgb_to_lab(rgb255: np.ndarray) -> np.ndarray:
    """sRGB (0-255, ...x3) to CIE L*a*b* (D65)."""
    c = np.asarray(rgb255, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    eps, kappa = 216.0 / 24389.0, 24389.0 / 27.0
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16.0) / 116.0)
    return np.stack([116.0 * f[..., 1] - 16.0,
                     500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 colour difference (Sharma, Wu and Dalal 2005), broadcasting."""
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    l1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    l2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    c1 = np.hypot(a1, b1)
    c2 = np.hypot(a2, b2)
    cbar7 = ((c1 + c2) / 2.0) ** 7
    g = 0.5 * (1.0 - np.sqrt(cbar7 / (cbar7 + 25.0 ** 7)))
    a1p, a2p = (1.0 + g) * a1, (1.0 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    h1p = np.where((a1p == 0) & (b1 == 0), 0.0, h1p)
    h2p = np.where((a2p == 0) & (b2 == 0), 0.0, h2p)
    dlp = l2 - l1
    dcp = c2p - c1p
    zero = (c1p * c2p) == 0
    dh = h2p - h1p
    dh = np.where(dh > 180.0, dh - 360.0, np.where(dh < -180.0, dh + 360.0, dh))
    dh = np.where(zero, 0.0, dh)
    dhp = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2.0))
    lbp = (l1 + l2) / 2.0
    cbp = (c1p + c2p) / 2.0
    hsum = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) <= 180.0, hsum / 2.0,
                   np.where(hsum < 360.0, (hsum + 360.0) / 2.0, (hsum - 360.0) / 2.0))
    hbp = np.where(zero, hsum, hbp)
    t = (1.0 - 0.17 * np.cos(np.radians(hbp - 30.0)) + 0.24 * np.cos(np.radians(2.0 * hbp))
         + 0.32 * np.cos(np.radians(3.0 * hbp + 6.0)) - 0.20 * np.cos(np.radians(4.0 * hbp - 63.0)))
    dtheta = 30.0 * np.exp(-(((hbp - 275.0) / 25.0) ** 2))
    cbp7 = cbp ** 7
    rc = 2.0 * np.sqrt(cbp7 / (cbp7 + 25.0 ** 7))
    sl = 1.0 + (0.015 * (lbp - 50.0) ** 2) / np.sqrt(20.0 + (lbp - 50.0) ** 2)
    sc = 1.0 + 0.045 * cbp
    sh = 1.0 + 0.015 * cbp * t
    rt = -np.sin(np.radians(2.0 * dtheta)) * rc
    return np.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dhp / sh) ** 2 + rt * (dcp / sc) * (dhp / sh))


def kmeans_lab(lab: np.ndarray, k: int, iters: int = 15, seed: int = 0):
    """Deterministic k-means++ in Lab. Returns (centres, weights) sorted by weight."""
    n = lab.shape[0]
    if n == 0:
        return np.zeros((0, 3)), np.zeros(0)
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)
    centres = [lab[rng.integers(n)]]
    d2 = ((lab - centres[0]) ** 2).sum(1)
    for _ in range(1, k):
        total = d2.sum()
        if total <= 0:
            break
        centres.append(lab[rng.choice(n, p=d2 / total)])
        d2 = np.minimum(d2, ((lab - centres[-1]) ** 2).sum(1))
    c = np.array(centres)
    for _ in range(iters):
        dist = ((lab[:, None, :] - c[None, :, :]) ** 2).sum(-1)
        lab_idx = dist.argmin(1)
        new = np.array([lab[lab_idx == j].mean(0) if np.any(lab_idx == j) else c[j] for j in range(len(c))])
        if np.allclose(new, c, atol=1e-3):
            c = new
            break
        c = new
    dist = ((lab[:, None, :] - c[None, :, :]) ** 2).sum(-1)
    lab_idx = dist.argmin(1)
    weights = np.bincount(lab_idx, minlength=len(c)) / float(n)
    order = np.argsort(-weights)
    return c[order], weights[order]


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    lab = np.asarray(lab, dtype=np.float64)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    eps, kappa = 216.0 / 24389.0, 24389.0 / 27.0

    def finv(f):
        f3 = f ** 3
        return np.where(f3 > eps, f3, (116.0 * f - 16.0) / kappa)

    xyz = np.stack([finv(fx), finv(fy), finv(fz)], -1) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2404542, -1.5371385, -0.4985314],
                  [-0.9692660, 1.8760108, 0.0415560],
                  [0.0556434, -0.2040259, 1.0572252]])
    lin = np.clip(xyz @ m.T, 0.0, 1.0)
    srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(srgb * 255.0, 0, 255)


# --------------------------------------------------------------------------- morphology and labelling


def _vdist(target: np.ndarray, outside_is_target: bool) -> np.ndarray:
    """Vertical distance (px) from each pixel to the nearest target pixel in its column."""
    h = target.shape[0]
    idx = np.arange(h, dtype=np.int32)[:, None]
    big = 1 << 30
    up_fill, down_fill = (-1, h) if outside_is_target else (-big, big)
    above = np.maximum.accumulate(np.where(target, idx, up_fill), axis=0)
    below = np.minimum.accumulate(np.where(target, idx, down_fill)[::-1], axis=0)[::-1]
    return np.minimum(idx - above, below - idx)


def _hshift(a: np.ndarray, dx: int, fill) -> np.ndarray:
    """out[:, x] = a[:, x + dx] (fill outside)."""
    if dx == 0:
        return a
    out = np.full_like(a, fill)
    w = a.shape[1]
    if abs(dx) >= w:
        return out
    if dx > 0:
        out[:, : w - dx] = a[:, dx:]
    else:
        out[:, -dx:] = a[:, : w + dx]
    return out


def erode_disk(mask: np.ndarray, r: float) -> np.ndarray:
    """Exact binary erosion by a Euclidean disk of radius r (outside counts as background)."""
    mask = mask.astype(bool)
    if r < 1:
        return mask.copy()
    g = _vdist(~mask, outside_is_target=True)
    out = mask.copy()
    w = mask.shape[1]
    ri = int(math.floor(r))
    for dx in range(-ri, ri + 1):
        need = math.sqrt(max(r * r - dx * dx, 0.0))
        if dx == 0:
            out &= g > need
        elif dx > 0:
            out[:, : w - dx] &= g[:, dx:] > need
            out[:, max(0, w - dx):] = False
        else:
            out[:, -dx:] &= g[:, : w + dx] > need
            out[:, : min(w, -dx)] = False
    return out


def dilate_disk(mask: np.ndarray, r: float) -> np.ndarray:
    """Exact binary dilation by a Euclidean disk of radius r."""
    mask = mask.astype(bool)
    if r < 1:
        return mask.copy()
    g = _vdist(mask, outside_is_target=False)
    out = np.zeros_like(mask)
    w = mask.shape[1]
    ri = int(math.floor(r))
    for dx in range(-ri, ri + 1):
        need = math.sqrt(max(r * r - dx * dx, 0.0))
        if dx == 0:
            out |= g <= need
        elif dx > 0:
            out[:, : w - dx] |= g[:, dx:] <= need
        else:
            out[:, -dx:] |= g[:, : w + dx] <= need
    return out


def open_disk(mask, r):
    return dilate_disk(erode_disk(mask, r), r)


def close_disk(mask, r):
    """Closing with edge-replicated padding, so a subject touching the frame keeps its edge pixels."""
    if r < 1:
        return mask.astype(bool).copy()
    p = int(math.ceil(r)) + 1
    padded = np.pad(mask.astype(bool), p, mode="edge")
    return erode_disk(dilate_disk(padded, r), r)[p:-p, p:-p]


def box_mean(a: np.ndarray, r: int) -> np.ndarray:
    """Mean over a (2r+1)^2 box with edge clipping (via integral image)."""
    if r <= 0:
        return a.astype(np.float64)
    h, w = a.shape
    ii = np.zeros((h + 1, w + 1), dtype=np.float64)
    ii[1:, 1:] = np.cumsum(np.cumsum(np.asarray(a, dtype=np.float64), 0), 1)  # float64: avoids cancellation
    y0 = np.clip(np.arange(h) - r, 0, h)
    y1 = np.clip(np.arange(h) + r + 1, 0, h)
    x0 = np.clip(np.arange(w) - r, 0, w)
    x1 = np.clip(np.arange(w) + r + 1, 0, w)
    s = ii[y1][:, x1] - ii[y0][:, x1] - ii[y1][:, x0] + ii[y0][:, x0]
    area = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    return s / area


def label(mask: np.ndarray):
    """8-connected component labelling. Returns (labels int32, areas, bboxes[x0,y0,x1,y1])."""
    mask = mask.astype(bool)
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    if not mask.any():
        return labels, np.zeros(0, np.int64), np.zeros((0, 4), np.int64)
    d = np.diff(np.pad(mask.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    sy, sx = np.nonzero(d == 1)
    _ey, ex = np.nonzero(d == -1)
    n = len(sx)
    parent = list(range(n))

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    rows = np.searchsorted(sy, np.arange(h + 1))
    sx_l, ex_l = sx.tolist(), ex.tolist()
    for y in range(1, h):
        a0, a1, b1 = rows[y - 1], rows[y], rows[y + 1]
        if a0 == a1 or a1 == b1:
            continue
        i, j = int(a0), int(a1)
        while i < a1 and j < b1:
            if sx_l[i] <= ex_l[j] and sx_l[j] <= ex_l[i]:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
            if ex_l[i] + 1 <= ex_l[j]:
                i += 1
            else:
                j += 1
    roots = np.array([find(i) for i in range(n)], dtype=np.int64)
    uniq, comp = np.unique(roots, return_inverse=True)
    comp = comp.astype(np.int32) + 1
    lengths = ex - sx
    offsets = np.arange(lengths.sum()) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    flat = np.repeat(sy.astype(np.int64) * w + sx, lengths) + offsets
    labels.ravel()[flat] = np.repeat(comp, lengths)
    ncomp = len(uniq)
    areas = np.bincount(comp, weights=lengths, minlength=ncomp + 1)[1:].astype(np.int64)
    bx0 = np.full(ncomp + 1, w, np.int64)
    by0 = np.full(ncomp + 1, h, np.int64)
    bx1 = np.full(ncomp + 1, -1, np.int64)
    by1 = np.full(ncomp + 1, -1, np.int64)
    np.minimum.at(bx0, comp, sx)
    np.minimum.at(by0, comp, sy)
    np.maximum.at(bx1, comp, ex - 1)
    np.maximum.at(by1, comp, sy)
    bboxes = np.stack([bx0, by0, bx1, by1], 1)[1:]
    return labels, areas, bboxes


def fill_holes(mask: np.ndarray, max_area: float | None = None) -> np.ndarray:
    """Fill background regions that do not touch the border (only those <= max_area px if given)."""
    lab, areas, bb = label(~mask)
    if len(areas) == 0:
        return mask.copy()
    h, w = mask.shape
    touch = (bb[:, 0] == 0) | (bb[:, 1] == 0) | (bb[:, 2] == w - 1) | (bb[:, 3] == h - 1)
    hole = ~touch
    if max_area is not None:
        hole &= areas <= max_area
    fill_ids = np.nonzero(hole)[0] + 1
    if len(fill_ids) == 0:
        return mask.copy()
    lut = np.zeros(len(areas) + 1, bool)
    lut[fill_ids] = True
    return mask | lut[lab]


def bbox_of(mask: np.ndarray):
    ys = np.nonzero(mask.any(1))[0]
    xs = np.nonzero(mask.any(0))[0]
    if len(ys) == 0:
        return None
    return int(xs[0]), int(ys[0]), int(xs[-1]), int(ys[-1])


def resize_mask(mask: np.ndarray, size_wh) -> np.ndarray:
    im = Image.fromarray(mask.astype(np.uint8) * 255, "L")
    w, h = size_wh
    resample = Image.BOX if (w < mask.shape[1] or h < mask.shape[0]) else Image.BILINEAR
    return np.asarray(im.resize((max(1, w), max(1, h)), resample)) >= 128


def resize_mask_nearest(mask: np.ndarray, size_wh) -> np.ndarray:
    im = Image.fromarray(mask.astype(np.uint8) * 255, "L")
    return np.asarray(im.resize(size_wh, Image.NEAREST)) >= 128


# --------------------------------------------------------------------------- inputs


@dataclass
class Source:
    label: str                     # human-readable origin
    data: bytes                    # raw bytes of the file (or of the parent sheet)
    path: str                      # filesystem path (zip path for members)
    member: str | None = None      # zip member name
    crop: tuple | None = None      # (x0, y0, x1, y1) panel crop in the parent sheet
    sha256: str = ""

    def __post_init__(self):
        if not self.sha256:
            self.sha256 = sha256_bytes(self.data)


@dataclass
class InputSet:
    mode: str
    path: str
    views: dict = field(default_factory=dict)       # role -> Source
    palette: Source | None = None
    hero34: Source | None = None
    unassigned: list = field(default_factory=list)  # Sources nobody claimed
    notes: list = field(default_factory=list)
    sheet_panels: list = field(default_factory=list)
    overlays: dict = field(default_factory=dict)    # mirror-check overlays for the contact sheet


_ROLE_TOKENS = {
    "front": {"front", "frontal"},
    "back": {"back", "rear"},
    "left": {"left"},
    "right": {"right"},
    "hero34": {"hero34", "34", "threequarter", "3q", "34view"},
    "palette": {"palette", "swatch", "swatches"},
}


def role_of(name: str) -> str | None:
    tokens = set(re.split(r"[^a-z0-9]+", Path(name).stem.lower())) - {""}
    hits = [role for role, alias in _ROLE_TOKENS.items() if tokens & alias]
    if {"three", "quarter"} <= tokens and "hero34" not in hits:
        hits.append("hero34")
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None
    for special in ("palette", "hero34"):
        if special in hits:
            return special
    return "ambiguous"


def _is_image_name(name: str) -> bool:
    base = Path(name).name
    return base.lower().endswith(IMAGE_EXTS) and not base.startswith(".") and "__MACOSX" not in name


def _collect_images(path: Path) -> list:
    """Image Sources inside a folder (top level), a zip, or a zip in a folder."""
    out = []
    if path.is_dir():
        for p in sorted(path.iterdir(), key=lambda q: q.name.lower()):
            if p.is_file() and _is_image_name(p.name):
                out.append(Source(label=p.name, data=p.read_bytes(), path=str(p)))
        if not out:
            for z in sorted(path.iterdir(), key=lambda q: q.name.lower()):
                if z.is_file() and z.suffix.lower() == ".zip":
                    out.extend(_collect_images(z))
    elif path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for info in sorted(zf.infolist(), key=lambda i: i.filename.lower()):
                if not info.is_dir() and _is_image_name(info.filename):
                    out.append(Source(label=f"{path.name}!{info.filename}", data=zf.read(info),
                                      path=str(path), member=info.filename))
    return out


def _read_single(spec: str) -> Source:
    if "!" in spec and spec.split("!", 1)[0].lower().endswith(".zip"):
        zpath, member = spec.split("!", 1)
        with zipfile.ZipFile(zpath) as zf:
            data = zf.read(member)
        return Source(label=f"{Path(zpath).name}!{member}", data=data, path=str(Path(zpath)), member=member)
    p = Path(spec)
    return Source(label=p.name, data=p.read_bytes(), path=str(p))


def _parse_roles(text: str | None) -> list:
    if not text:
        return []
    roles = [t.strip().lower() for t in text.split(",") if t.strip()]
    allowed = set(ROLES) | set(EXTRA_ROLES) | {"skip"}
    bad = [r for r in roles if r not in allowed]
    if bad:
        raise ValueError(f"unknown role(s) {bad}; allowed: {sorted(allowed)}")
    return roles


def discover(input_spec: str | None, views: list, order: str | None, sheet_order: str | None,
             palette: str | None, cfg: dict) -> InputSet:
    inset = InputSet(mode="explicit", path=input_spec or "")
    images: list = []
    if input_spec:
        is_member = "!" in input_spec and input_spec.split("!", 1)[0].lower().endswith(".zip")
        p = Path(input_spec)
        if is_member or (p.is_file() and p.suffix.lower() in IMAGE_EXTS):
            src = _read_single(input_spec)
            if role_of(src.member or src.label) in ROLES and not views:
                inset.mode = "single"
                inset.views[role_of(src.member or src.label)] = src
            else:
                inset.mode = "sheet"
                _split_sheet_into(inset, src, _parse_roles(sheet_order) or ["front", "left", "back", "right"], cfg)
            images = []
        elif p.is_dir() or p.suffix.lower() == ".zip":
            inset.mode = "zip" if p.suffix.lower() == ".zip" else "folder"
            images = _collect_images(p)
            if not images:
                inset.notes.append("No png/jpg/webp images were found in the input (folders are scanned at the "
                                   "top level, then inside top-level zip files).")
        else:
            raise FileNotFoundError(input_spec)
    unnamed = []
    for src in images:
        role = role_of(src.member or src.label)
        if role in ROLES:
            if role in inset.views:
                inset.notes.append(f"Two files claim the {role} view: {inset.views[role].label} and {src.label}; "
                                   f"the first is used.")
                inset.unassigned.append(src)
            else:
                inset.views[role] = src
        elif role == "palette":
            inset.palette = inset.palette or src
        elif role == "hero34":
            inset.hero34 = inset.hero34 or src
        else:
            if role == "ambiguous":
                inset.notes.append(f"{src.label}: the name matches more than one view role; it was not used.")
            unnamed.append(src)
    roles = _parse_roles(order)
    if roles and unnamed:
        for src, role in zip(unnamed, roles):
            if role == "skip":
                inset.unassigned.append(src)
                inset.notes.append(f"{src.label}: skipped by --order (not a view).")
            elif role == "palette":
                inset.palette = src
            elif role == "hero34":
                inset.hero34 = src
            else:
                inset.views[role] = src
        rest = unnamed[len(roles):]
        if rest:
            inset.notes.append(f"{len(rest)} image(s) beyond the --order list were not used.")
            inset.unassigned.extend(rest)
    elif unnamed:
        if not inset.views and len(unnamed) == 1 and inset.mode in ("folder", "zip"):
            inset.mode = "sheet"
            _split_sheet_into(inset, unnamed[0], _parse_roles(sheet_order) or ["front", "left", "back", "right"], cfg)
        else:
            inset.unassigned.extend(unnamed)
    for spec in views or []:
        if "=" not in spec:
            raise ValueError(f"--view expects role=path, got {spec!r}")
        role, path = spec.split("=", 1)
        role = role.strip().lower()
        src = _read_single(path.strip())
        if role in ROLES:
            inset.views[role] = src
        elif role == "palette":
            inset.palette = src
        elif role == "hero34":
            inset.hero34 = src
        else:
            raise ValueError(f"unknown role {role!r} in --view")
    if palette:
        inset.palette = _read_single(palette)
    return inset


# --------------------------------------------------------------------------- image decoding


def decode(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:  # pragma: no cover - exotic EXIF
        pass
    return im


def to_rgba(im: Image.Image):
    """RGBA uint8 array and whether a real (used) alpha channel is present."""
    had_alpha = im.mode in ("RGBA", "LA", "PA", "RGBa", "La") or (im.mode == "P" and "transparency" in im.info)
    rgba = np.asarray(im.convert("RGBA"), dtype=np.uint8)
    used = False
    if had_alpha:
        a = rgba[..., 3]
        h, w = a.shape
        ring = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        used = bool((a < 128).mean() >= 0.01 and (ring < 128).mean() >= 0.6)
    return rgba, used


def downscale_rgba(rgba: np.ndarray, max_side: int):
    h, w = rgba.shape[:2]
    f = min(1.0, max_side / float(max(h, w)))
    if f >= 1.0:
        return rgba.copy(), 1.0, 1.0
    nw, nh = max(1, int(round(w * f))), max(1, int(round(h * f)))
    im = Image.fromarray(rgba, "RGBA").convert("RGBa").resize((nw, nh), Image.LANCZOS).convert("RGBA")
    return np.asarray(im), nw / float(w), nh / float(h)


# --------------------------------------------------------------------------- segmentation


def _robust_profile(p: np.ndarray, tol: float = 12.0) -> np.ndarray:
    """Clean an N x C border profile: spikes (subject contamination) are replaced by interpolation.

    A running median follows monotonic ramps and soft wall/floor horizons exactly, so only
    non-monotonic spikes are rejected."""
    n = p.shape[0]
    if n < 7:
        return np.repeat(np.median(p, 0)[None], n, 0)
    w = max(9, (n // 15) | 1)
    pad = w // 2
    pp = np.pad(p, ((pad, pad), (0, 0)), mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(pp, w, axis=0)
    trend = np.median(win, axis=-1)
    good = np.linalg.norm(p - trend, axis=1) <= tol
    if good.sum() < max(3, 0.25 * n):
        return trend
    idx = np.arange(n)
    out = np.stack([np.interp(idx, idx[good], p[good, c]) for c in range(p.shape[1])], 1)
    k = 5
    padded = np.pad(out, ((k // 2, k // 2), (0, 0)), mode="edge")
    kernel = np.ones(k) / k
    return np.stack([np.convolve(padded[:, c], kernel, mode="valid") for c in range(p.shape[1])], 1)


def estimate_background(rgb: np.ndarray, strip_frac: float) -> np.ndarray:
    """Per-pixel background model for an opaque image: per-row left/right border colours
    interpolated across the width, plus a top/bottom column correction (vignette)."""
    h, w, _ = rgb.shape
    s = max(3, int(round(strip_frac * w)))
    sv = max(3, int(round(strip_frac * h)))
    left = _robust_profile(np.median(rgb[:, :s], axis=1))
    right = _robust_profile(np.median(rgb[:, w - s:], axis=1))
    t = (np.arange(w, dtype=np.float32) / max(w - 1, 1))[None, :, None]
    bg = left[:, None, :].astype(np.float32) * (1 - t) + right[:, None, :].astype(np.float32) * t
    top = np.median(rgb[:sv] - bg[:sv], axis=0)
    bot = np.median(rgb[h - sv:] - bg[h - sv:], axis=0)
    top = np.clip(_robust_profile(top, tol=8.0), -15, 15)
    bot = np.clip(_robust_profile(bot, tol=8.0), -15, 15)
    u = (np.arange(h, dtype=np.float32) / max(h - 1, 1))[:, None, None]
    bg = bg + top[None].astype(np.float32) * (1 - u) + bot[None].astype(np.float32) * u
    return bg.astype(np.float32)


@dataclass
class ViewData:
    role: str
    source: Source
    size: tuple                   # (W, H) source pixels
    mode: str
    has_alpha: bool
    sx: float                     # analysis scale x (analysis px / source px)
    sy: float
    rgb: np.ndarray               # analysis RGB float32
    mask: np.ndarray              # analysis subject mask (bool)
    shadow: np.ndarray            # analysis shadow mask (bool)
    fg_raw: np.ndarray            # analysis raw foreground before clean-up
    bg: np.ndarray | None         # analysis background model (None for alpha)
    thr: float                    # foreground threshold (RGB distance)
    bg_stats: dict
    components: list              # [(area, bbox)] kept components, largest first
    bbox: tuple | None            # analysis bbox (x0, y0, x1, y1) inclusive
    holes_kept: int = 0
    metrics: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    thin_mask: np.ndarray | None = None


def segment(role: str, src: Source, cfg: dict) -> ViewData:
    im = decode(src.data)
    if src.crop:
        im = im.crop(src.crop)
    mode = im.mode
    rgba, has_alpha = to_rgba(im)
    H, W = rgba.shape[:2]
    small, sx, sy = downscale_rgba(rgba, int(cfg["analysis_max_side"]))
    h, w = small.shape[:2]
    rgb = small[..., :3].astype(np.float32)
    seg = cfg["segmentation"]
    side = max(h, w)
    bg = None
    stats: dict = {}
    if has_alpha:
        alpha = small[..., 3]
        fg = alpha >= int(seg["alpha_threshold"])
        semi = ((alpha > 16) & (alpha < 240)).mean()
        stats = {"type": "alpha", "semi_transparent_frac": _r(semi), "noise": 0.0, "range": 0.0,
                 "white_dist": 0.0, "mean_hex": None}
        thr = float("nan")
    else:
        bg = estimate_background(rgb, float(seg["border_strip_frac"]))
        diff = np.sqrt(((rgb - bg) ** 2).sum(-1))
        s = max(3, int(round(float(seg["border_strip_frac"]) * w)))
        svv = max(3, int(round(float(seg["border_strip_frac"]) * h)))
        ring = np.concatenate([diff[:, :s].ravel(), diff[:, w - s:].ravel(), diff[:svv].ravel(), diff[h - svv:].ravel()])
        clean = ring[ring < 40]
        noise = float(np.percentile(clean, 90)) if clean.size > 50 else 40.0
        thr = max(float(seg["diff_min"]), float(seg["diff_noise_k"]) * noise)
        fg = diff > thr
        lum_bg = bg @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        mean_bg = bg.reshape(-1, 3).mean(0)
        stats = {
            "type": "opaque",
            "noise": _r(noise, 2),
            "range": _r(float(np.percentile(lum_bg, 98) - np.percentile(lum_bg, 2)), 2),
            "white_dist": _r(float(np.sqrt(((255.0 - mean_bg) ** 2).sum())), 2),
            "mean_hex": hexcol(mean_bg),
            "top_hex": hexcol(bg[: max(1, h // 20)].reshape(-1, 3).mean(0)),
            "bottom_hex": hexcol(bg[-max(1, h // 20):].reshape(-1, 3).mean(0)),
            "threshold": _r(thr, 2),
        }
    fg_raw = fg.copy()
    r_open = max(1.0, float(seg["open_frac"]) * side)
    r_close = max(1.0, float(seg["close_frac"]) * side)
    pre = close_disk(open_disk(fg, r_open), r_close)
    shadow = np.zeros_like(fg)
    feats = None
    scfg = cfg["shadow"]
    if not has_alpha and scfg["enabled"]:
        pb = bbox_of(pre)
        if pb is not None:
            feats = shadow_features(rgb, bg)
            shadow = classify_shadow(rgb, bg, fg, pre, pb, scfg, feats)
    subject = close_disk(open_disk(fg & ~shadow, r_open), r_close) & ~shadow
    lab, areas, bbs = label(subject)
    components = []
    if len(areas):
        keep_min = float(seg["keep_component_frac"]) * areas.max()
        main = int(np.argmax(areas))
        keep = []
        mx0, my0, mx1, my1 = bbs[main]
        mh = my1 - my0 + 1
        for i in np.nonzero(areas >= keep_min)[0]:
            if i != main and feats is not None and bbs[i][1] >= my1 - float(scfg["band_above_frac"]) * mh:
                sel = lab == i + 1
                if (scfg["k_min"] <= float(np.median(feats["k"][sel])) <= scfg["k_max"]
                        and float(np.percentile(feats["chroma"][sel], 90)) <= scfg["chroma_tol"]
                        and float(np.median(feats["lstd"][sel])) <= 2 * scfg["smooth_max"]):
                    shadow |= sel  # detached floor-level piece with shadow statistics
                    continue
            keep.append(i)
        keep = np.array(keep, dtype=np.int64)
        lut = np.zeros(len(areas) + 1, bool)
        lut[keep + 1] = True
        subject = lut[lab]
        order = keep[np.argsort(-areas[keep])]
        components = [(int(areas[i]), tuple(int(v) for v in bbs[i])) for i in order]
    total = int(subject.sum())
    filled = fill_holes(subject, max_area=float(seg["fill_holes_max_frac"]) * max(total, 1))
    holes_all = fill_holes(subject)
    holes_kept = int((holes_all & ~filled).sum())
    subject = filled
    shadow &= ~subject
    vd = ViewData(role=role, source=src, size=(W, H), mode=mode, has_alpha=has_alpha, sx=sx, sy=sy, rgb=rgb,
                  mask=subject, shadow=shadow, fg_raw=fg_raw, bg=bg, thr=thr, bg_stats=stats,
                  components=components, bbox=bbox_of(subject), holes_kept=holes_kept)
    return vd


def shadow_features(rgb, bg) -> dict:
    """Per-pixel shadow cues: k = mean ratio to the background (darkening), chroma = spread of the
    per-channel ratios (a shadow keeps the background's chromaticity), lstd = 5x5 luminance std."""
    ratio = rgb / np.maximum(bg, 1.0)
    k = ratio.mean(-1)
    chroma = np.abs(ratio - k[..., None]).max(-1)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    m1 = box_mean(lum, 2)
    m2 = box_mean(lum * lum, 2)
    return {"k": k, "chroma": chroma, "lstd": np.sqrt(np.maximum(m2 - m1 * m1, 0)), "lum": lum}


def classify_shadow(rgb, bg, fg, pre, pb, scfg, feats=None) -> np.ndarray:
    """Soft cast/contact shadows: darkened, neutral (same chromaticity as the background),
    smooth regions with soft outer edges, in a band around the subject's base."""
    h, w = fg.shape
    x0, y0, x1, y1 = pb
    hh = y1 - y0 + 1
    band_top = int(max(0, y1 - float(scfg["band_above_frac"]) * hh))
    band = np.zeros_like(fg)
    band[band_top:] = True
    feats = feats or shadow_features(rgb, bg)
    k, chroma, lstd, lum = feats["k"], feats["chroma"], feats["lstd"], feats["lum"]
    cand = fg & band & (k >= scfg["k_min"]) & (k <= scfg["k_max"]) & (chroma <= scfg["chroma_tol"]) & (lstd <= scfg["smooth_max"])
    if not cand.any():
        return np.zeros_like(fg)
    lab, areas, _ = label(cand)
    min_area = float(scfg["min_area_frac"]) * h * w
    gy, gx = np.gradient(lum)
    grad = np.hypot(gx, gy)
    bgpix = ~fg
    near_bg = dilate_disk(bgpix, 1) & cand
    out = np.zeros_like(fg)
    ids = np.nonzero(areas >= min_area)[0] + 1
    if len(ids) == 0:
        return out
    edge_lab = lab[near_bg]
    edge_grad = grad[near_bg]
    sums = np.bincount(edge_lab, weights=edge_grad, minlength=len(areas) + 1)
    cnts = np.bincount(edge_lab, minlength=len(areas) + 1)
    lut = np.zeros(len(areas) + 1, bool)
    floor_y = y1 - float(scfg.get("floor_anchor_frac", 0.03)) * hh
    bottoms = np.full(len(areas) + 1, -1, np.int64)
    ys = np.nonzero(cand)[0]
    np.maximum.at(bottoms, lab[cand], ys)
    for i in ids:
        if cnts[i] >= 5 and sums[i] / cnts[i] <= scfg["edge_grad_max"] and bottoms[i] >= floor_y:
            lut[i] = True
    return lut[lab]


# --------------------------------------------------------------------------- per-view measurement


def _to_src_box(vd: ViewData, box):
    x0, y0, x1, y1 = box
    return (x0 / vd.sx, y0 / vd.sy, (x1 + 1) / vd.sx, (y1 + 1) / vd.sy)


def measure_view(vd: ViewData, cfg: dict, ref_height_a: float | None = None):
    m = vd.metrics
    h, w = vd.mask.shape
    m["canvas_px"] = list(vd.size)
    m["analysis_px"] = [w, h]
    if vd.bbox is None:
        m["empty"] = True
        return
    x0, y0, x1, y1 = vd.bbox
    bh, bw = y1 - y0 + 1, x1 - x0 + 1
    sx0, sy0, sx1, sy1 = _to_src_box(vd, vd.bbox)
    W, H = vd.size
    m["bbox_src"] = [round(sx0, 1), round(sy0, 1), round(sx1, 1), round(sy1, 1)]
    m["height_src_px"] = round(sy1 - sy0, 1)
    m["width_src_px"] = round(sx1 - sx0, 1)
    m["height_frac"] = (sy1 - sy0) / H
    m["width_frac"] = (sx1 - sx0) / W
    m["aspect_w_over_h"] = (sx1 - sx0) / max(sy1 - sy0, 1e-6)
    m["centre_offset_frac"] = ((sx0 + sx1) / 2.0 - W / 2.0) / W
    m["baseline_frac"] = sy1 / H
    m["top_frac"] = sy0 / H
    m["margins_px"] = {"left": round(sx0, 1), "right": round(W - sx1, 1), "top": round(sy0, 1), "bottom": round(H - sy1, 1)}
    m["margins_frac"] = {"left": sx0 / W, "right": (W - sx1) / W, "top": sy0 / H, "bottom": (H - sy1) / H}
    edge = {"left": int(vd.mask[:, 0].sum()), "right": int(vd.mask[:, -1].sum()),
            "top": int(vd.mask[0].sum()), "bottom": int(vd.mask[-1].sum())}
    m["touching_edge_px"] = edge
    area = int(vd.mask.sum())
    m["area_analysis_px"] = area
    # components / floating parts
    comps = vd.components
    main_area = comps[0][0] if comps else area
    m["components"] = [{"area_frac_of_main": round(a / max(main_area, 1), 4),
                        "bbox_src": [round(v, 1) for v in _to_src_box(vd, b)]} for a, b in comps[1:]]
    # shadow: area, horizontal reach beyond the subject (in body heights) and darkness (1 - mean ratio to bg)
    m["shadow_area_frac"] = float(vd.shadow.sum()) / max(area, 1)
    m["shadow_reach_frac"] = 0.0
    m["shadow_darkness"] = 0.0
    if vd.shadow.any() and vd.bg is not None:
        sb = bbox_of(vd.shadow)
        m["shadow_reach_frac"] = max(x0 - sb[0], sb[2] - x1, 0) / float(bh)
        m["shadow_darkness"] = float(1.0 - (vd.rgb[vd.shadow] / np.maximum(vd.bg[vd.shadow], 1.0)).mean())
    # lighting: median brightness ratio of mirrored pixel pairs (screen-left vs screen-right of the bbox
    # centre). A key light shifts every pair; an asymmetric part (tail, pauldron) shifts only a few.
    lum = vd.rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    cx = (x0 + x1) / 2.0
    core = erode_disk(vd.mask, 2) if area > 400 else vd.mask
    ys, xs = np.nonzero(core[:, : int(math.floor(cx))])
    xm = np.round(2.0 * cx - xs).astype(np.int64)
    ok = (xm >= 0) & (xm < w)
    ys, xs, xm = ys[ok], xs[ok], xm[ok]
    ok = core[ys, xm]
    if ok.sum() > 200:
        a, b = lum[ys[ok], xs[ok]], lum[ys[ok], xm[ok]]
        m["light_imbalance"] = float(np.median((a - b) / ((a + b) / 2.0 + 1.0)))
        m["light_pairs"] = int(ok.sum())
    else:
        m["light_imbalance"] = 0.0
        m["light_pairs"] = 0
    # thin parts: opening with a disk whose diameter is diameter_frac of the normalised frame
    tcfg = cfg["checks"]["thin_parts"]
    fill = float(cfg["target"]["fill_height"])
    ref_h = ref_height_a if ref_height_a else bh
    frame_a = ref_h / fill
    diam = float(tcfg["diameter_frac_of_frame"]) * frame_a
    radius = diam / 2.0
    opened = open_disk(vd.mask, radius)
    thin = vd.mask & ~opened
    tl, tareas, tbbs = label(thin)
    min_ext = max(float(tcfg["min_extent_frac"]) * bh, float(tcfg.get("min_extent_diameters", 0.0)) * diam)
    keep = []
    for i in range(len(tareas)):
        bx0, by0, bx1, by1 = tbbs[i]
        ext = max(bx1 - bx0 + 1, by1 - by0 + 1)
        if ext >= min_ext and tareas[i] >= 0.25 * diam * diam:
            keep.append(i)
    lut = np.zeros(len(tareas) + 1, bool)
    for i in keep:
        lut[i + 1] = True
    vd.thin_mask = lut[tl] if len(tareas) else np.zeros_like(vd.mask)
    m["thin"] = {
        "diameter_src_px": round(diam / vd.sy, 1),
        "diameter_at_2048_px": round(float(tcfg["diameter_frac_of_frame"]) * float(cfg["target"]["canvas_px"]), 1),
        "area_frac": float(vd.thin_mask.sum()) / max(area, 1),
        "parts": [{"bbox_src": [round(v, 1) for v in _to_src_box(vd, tuple(int(v) for v in tbbs[i]))],
                   "area_frac": round(float(tareas[i]) / max(area, 1), 4),
                   "where": describe_region(tuple(int(v) for v in tbbs[i]), vd.bbox)} for i in
                  sorted(keep, key=lambda j: -tareas[j])[:6]],
    }
    # dominant colours (eroded core avoids anti-aliased edge pixels)
    pcfg = cfg["checks"]["palette"]
    pix = vd.rgb[core] if core.sum() > 100 else vd.rgb[vd.mask]
    if len(pix):
        rng = np.random.default_rng(1)
        if len(pix) > 12000:
            pix = pix[rng.choice(len(pix), 12000, replace=False)]
        centres, weights = kmeans_lab(srgb_to_lab(pix), int(pcfg["clusters"]))
        m["dominant"] = [{"hex": hexcol(lab_to_srgb(c)), "lab": [round(float(v), 2) for v in c],
                          "weight": round(float(wt), 4)} for c, wt in zip(centres, weights)]
    # pose gaps (front/back views): rows with >=3 runs = visible gap between arms and torso
    m["arm_gap_rows_frac"] = _gap_rows(vd.mask, vd.bbox, 0.25, 0.60, 3)
    m["leg_gap_rows_frac"] = _gap_rows(vd.mask, vd.bbox, 0.80, 0.97, 2)


def _gap_rows(mask, bbox, f0, f1, min_runs):
    x0, y0, x1, y1 = bbox
    bh = y1 - y0 + 1
    ra, rb = y0 + int(f0 * bh), y0 + int(f1 * bh)
    if rb <= ra:
        return 0.0
    sub = mask[ra:rb, x0:x1 + 1].astype(np.int8)
    min_run = max(2, int(0.01 * bh))
    count = 0
    for row in sub:
        d = np.diff(np.concatenate([[0], row, [0]]))
        starts = np.nonzero(d == 1)[0]
        ends = np.nonzero(d == -1)[0]
        runs = int(((ends - starts) >= min_run).sum())
        count += runs >= min_runs
    return count / float(rb - ra)


def describe_region(box, ref_box) -> str:
    """Plain-English location of box inside the subject box (head/upper body/... , side)."""
    x0, y0, x1, y1 = box
    rx0, ry0, rx1, ry1 = ref_box
    cy = ((y0 + y1) / 2.0 - ry0) / max(ry1 - ry0, 1)
    cx = ((x0 + x1) / 2.0 - rx0) / max(rx1 - rx0, 1)
    if cy < 0.18:
        band = "top (head/hat/horns)"
    elif cy < 0.45:
        band = "upper body (shoulders/arms/chest)"
    elif cy < 0.75:
        band = "middle (waist/hands/hips)"
    else:
        band = "bottom (legs/feet/hem)"
    side = "image-left side" if cx < 0.38 else ("image-right side" if cx > 0.62 else "centre")
    return f"{band}, {side}"


# --------------------------------------------------------------------------- cross-view comparisons


def _norm_crop(vd: ViewData, height: int, flip: bool):
    x0, y0, x1, y1 = vd.bbox
    crop = vd.mask[y0:y1 + 1, x0:x1 + 1]
    if flip:
        crop = crop[:, ::-1]
    bh, bw = crop.shape
    nw = max(1, int(round(bw * height / float(bh))))
    return resize_mask(crop, (nw, height))


def mirror_iou(a: ViewData, b: ViewData, shift_frac: float, height: int = 480):
    """IoU of a's silhouette with b's horizontally flipped silhouette, both scaled to the same
    height, bottom-aligned and bbox-centred; best over a small horizontal shift search."""
    ma = _norm_crop(a, height, False)
    mb = _norm_crop(b, height, True)
    smax = int(round(shift_frac * height))
    cw = max(ma.shape[1], mb.shape[1]) + 2 * smax + 4
    canvas_a = np.zeros((height, cw), bool)
    oa = (cw - ma.shape[1]) // 2
    canvas_a[:, oa:oa + ma.shape[1]] = ma
    ob = (cw - mb.shape[1]) // 2
    sa = float(ma.sum())
    sb = float(mb.sum())
    best = (-1.0, 0)
    zero_iou = 0.0
    for dx in range(-smax, smax + 1):
        canvas_b = np.zeros((height, cw), bool)
        canvas_b[:, ob + dx:ob + dx + mb.shape[1]] = mb
        inter = float((canvas_a & canvas_b).sum())
        iou = inter / max(sa + sb - inter, 1.0)
        if dx == 0:
            zero_iou = iou
        if iou > best[0]:
            best = (iou, dx)
    canvas_b = np.zeros((height, cw), bool)
    canvas_b[:, ob + best[1]:ob + best[1] + mb.shape[1]] = mb
    xor = canvas_a ^ canvas_b
    where = "none"
    both_box = bbox_of(canvas_a | canvas_b)

    def biggest(region):
        if not region.any():
            return None
        _, ar, bb = label(region)
        i = int(np.argmax(ar))
        return describe_region(tuple(int(v) for v in bb[i]), both_box), float(ar[i])

    only_a_mask, only_b_mask = canvas_a & ~canvas_b, canvas_b & ~canvas_a
    big_a, big_b = biggest(only_a_mask), biggest(only_b_mask)
    if xor.any():
        cands = [c for c in (big_a, big_b) if c]
        where = max(cands, key=lambda c: c[1])[0]
    only_a, only_b = float(only_a_mask.sum()), float(only_b_mask.sum())
    overlay = np.zeros((height, cw, 3), np.uint8)
    overlay[:] = (28, 28, 32)
    overlay[canvas_a & canvas_b] = (205, 205, 205)
    overlay[canvas_a & ~canvas_b] = (235, 70, 70)
    overlay[canvas_b & ~canvas_a] = (40, 200, 225)
    return {"iou": best[0], "iou_zero_shift": zero_iou, "best_shift_frac": best[1] / float(height),
            "only_a_frac": only_a / max(sa, 1.0), "only_b_frac": only_b / max(sb, 1.0),
            "largest_difference": where, "largest_only_a": big_a[0] if big_a else None,
            "largest_only_b": big_b[0] if big_b else None, "overlay": overlay}


def palette_from_image(src: Source) -> list:
    """Swatch colours from palette.png: flat-colour pixels, quantised, merged, ranked by area."""
    rgba, has_alpha = to_rgba(decode(src.data))
    small, _, _ = downscale_rgba(rgba, 512)
    rgb = small[..., :3].astype(np.float32)
    opaque = small[..., 3] >= 128 if has_alpha else np.ones(rgb.shape[:2], bool)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    m1, m2 = box_mean(lum, 1), box_mean(lum * lum, 1)
    flat = opaque & (np.sqrt(np.maximum(m2 - m1 * m1, 0)) < 2.5)
    if not has_alpha:
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bgc = np.median(border, 0)
        flat &= np.sqrt(((rgb - bgc) ** 2).sum(-1)) > 10
    pix = rgb[flat]
    if len(pix) < 20:
        return []
    q = (np.round(pix / 4.0) * 4.0).astype(np.int32)
    keys, counts = np.unique(q[:, 0] * 65536 + q[:, 1] * 256 + q[:, 2], return_counts=True)
    order = np.argsort(-counts)
    cols = []
    total = counts.sum()
    for idx in order:
        if counts[idx] < 0.005 * total:
            break
        key = int(keys[idx])
        rgbv = np.array([key // 65536, (key // 256) % 256, key % 256], np.float64)
        lab = srgb_to_lab(rgbv)
        if any(float(delta_e2000(lab, c["lab"])) < 3.0 for c in cols):
            continue
        cols.append({"hex": hexcol(rgbv), "lab": lab, "share": float(counts[idx] / total)})
        if len(cols) >= 16:
            break
    return cols


def colour_distance(dom_a: list, dom_b_labs: np.ndarray, min_w: float):
    """Area-weighted mean of each dominant colour's nearest-neighbour CIEDE2000 distance."""
    num, den, worst_item = 0.0, 0.0, None
    for d in dom_a:
        if d["weight"] < min_w:
            continue
        des = delta_e2000(np.array(d["lab"])[None], dom_b_labs)
        j = int(np.argmin(des))
        de = float(des[j])
        num += de * d["weight"]
        den += d["weight"]
        if worst_item is None or de > worst_item[0]:
            worst_item = (de, d["hex"], j)
    return (num / den if den else float("nan")), worst_item


# --------------------------------------------------------------------------- the checks


def add(checks: list, cid: str, scope: str, status: str, value, threshold, detail: str, unit: str = "", note=None):
    checks.append({"id": cid, "scope": scope, "status": status, "value": value, "threshold": threshold,
                   "unit": unit, "detail": detail, **({"note": note} if note else {})})


def run_checks(inset: InputSet, vds: dict, cfg: dict, kind: str, asymmetric: bool) -> list:
    C = cfg["checks"]
    checks: list = []
    required = list(cfg["required_views"])
    present = [r for r in ROLES if r in vds]
    missing = [r for r in required if r not in vds]
    status = FAIL if missing else PASS
    add(checks, "view_count", "set", status, {"present": present, "missing": missing,
                                              "unassigned": [s.label for s in inset.unassigned]},
        {"required": required},
        f"{len(present)} of {len(required)} required views present"
        + (f"; missing {', '.join(missing)}" if missing else "")
        + (f"; {len(inset.unassigned)} other image(s) not used" if inset.unassigned else ""))
    sizes = {r: tuple(vds[r].size) for r in present}
    # ---- per-view checks
    for role in present:
        vd = vds[role]
        m = vd.metrics
        scope = f"view:{role}"
        if m.get("empty"):
            add(checks, "subject_found", scope, FAIL, False, True, "No subject could be separated from the background.")
            continue
        W, H = vd.size
        rc = C["resolution"]
        subj = m["height_src_px"]
        sheet = inset.mode == "sheet"
        side_ok_fail = sheet or min(W, H) >= rc["fail_min_side"]
        side_ok_pass = sheet or min(W, H) >= rc["pass_min_side"]
        st = FAIL if (not side_ok_fail or subj < rc["fail_subject_px"]) else (
            PASS if (side_ok_pass and subj >= rc["pass_subject_px"]) else WARN)
        add(checks, "resolution", scope, st, {"width": W, "height": H, "subject_height_px": round(subj)},
            {"pass_min_side": rc["pass_min_side"], "fail_min_side": rc["fail_min_side"],
             "pass_subject_px": rc["pass_subject_px"], "fail_subject_px": rc["fail_subject_px"]},
            f"{W}x{H} px, subject {subj:.0f} px tall", "px")
        sq = abs(W - H) / float(max(W, H))
        if sheet:
            add(checks, "aspect", scope, SKIP, round(W / float(H), 4), None, "sheet panel: the crop is set by the split")
        else:
            add(checks, "aspect", scope, PASS if sq <= C["aspect"]["square_tol"] else WARN,
                round(W / float(H), 4), {"square_tol": C["aspect"]["square_tol"]},
                "square canvas" if sq <= C["aspect"]["square_tol"] else f"canvas is {W}x{H}, not square (prep pads it)")
        bs = vd.bg_stats
        bc = C["background"]
        cover = float(vd.fg_raw.mean())
        if bs["type"] == "alpha":
            st, txt = PASS, "transparent background (alpha)"
        else:
            if bs["noise"] > bc["fail_noise"] or cover > bc["fail_cover"]:
                st = FAIL
                txt = (f"background is not clean: residual texture/noise {bs['noise']:.1f} levels"
                       f" (limit {bc['fail_noise']}), foreground covers {cover * 100:.0f} % of the frame")
            elif bs["noise"] <= bc["pass_noise"] and bs["range"] <= bc["pass_range"] and bs["white_dist"] <= bc["pass_white_dist"]:
                st, txt = PASS, f"flat near-white background {bs['mean_hex']}"
            else:
                st = WARN
                txt = (f"background {bs['mean_hex']} (top {bs['top_hex']}, bottom {bs['bottom_hex']}), gradient range "
                       f"{bs['range']:.0f} levels, noise {bs['noise']:.1f}: not flat #FFFFFF/transparent; prep flattens it")
        add(checks, "background", scope, st, {k: v for k, v in bs.items()} | {"foreground_cover": round(cover, 4)},
            {"pass_noise": bc["pass_noise"], "fail_noise": bc["fail_noise"], "pass_range": bc["pass_range"],
             "pass_white_dist": bc["pass_white_dist"], "fail_cover": bc["fail_cover"]}, txt)
        off = m["centre_offset_frac"]
        add(checks, "centring", scope, SKIP if sheet else grade_max(abs(off), C["centring"]["pass"], C["centring"]["warn"]),
            round(off, 4), {"pass": C["centring"]["pass"], "warn": C["centring"]["warn"]},
            f"bbox centre is {off * 100:+.1f} % of the width from the image centre", "frac of width")
        mf = m["margins_frac"]
        mp = m["margins_px"]
        touching = [k for k, v in m["touching_edge_px"].items() if v > 0]
        min_side = min(mf, key=mf.get)
        if touching or min(mp.values()) <= C["margins"]["fail_px"]:
            st = FAIL
            txt = f"subject touches/crosses the {', '.join(touching or [min_side])} edge (cropped)"
        elif mf[min_side] < C["margins"]["pass_frac"]:
            st = WARN
            txt = f"tight {min_side} margin: {mf[min_side] * 100:.1f} %"
        else:
            st, txt = PASS, f"smallest margin {mf[min_side] * 100:.1f} % ({min_side})"
        add(checks, "margins", scope, st, {k: round(v, 4) for k, v in mf.items()},
            {"fail_px": C["margins"]["fail_px"], "pass_frac": C["margins"]["pass_frac"]}, txt, "frac")
        fc = C["fill"]
        fill = m["height_frac"] if m["height_frac"] >= m["width_frac"] else m["width_frac"]
        st = PASS if fc["pass"][0] <= fill <= fc["pass"][1] else (WARN if fc["warn"][0] <= fill <= fc["warn"][1] else FAIL)
        if st == FAIL:
            st = WARN  # framing is normalised by prep; resolution covers the real risk
        if sheet:
            st = SKIP
        add(checks, "fill", scope, st, round(fill, 4), {"pass": fc["pass"], "warn": fc["warn"]},
            f"subject fills {fill * 100:.0f} % of the {'height' if m['height_frac'] >= m['width_frac'] else 'width'} (target 80 %)")
        tc = C["thin_parts"]
        tf = m["thin"]["area_frac"]
        where = "; ".join(p["where"] for p in m["thin"]["parts"][:3]) or "none"
        add(checks, "thin_parts", scope, grade_max(tf, tc["pass"], tc["warn"]), round(tf, 4),
            {"pass": tc["pass"], "warn": tc["warn"], "diameter_frac_of_frame": tc["diameter_frac_of_frame"],
             "min_extent_frac": tc["min_extent_frac"]},
            f"{tf * 100:.2f} % of the silhouette is thinner than {m['thin']['diameter_at_2048_px']:.0f} px at 2048 "
            f"({len(m['thin']['parts'])} part(s): {where})", "frac of silhouette")
        cc = C["components"]
        big = max([c["area_frac_of_main"] for c in m["components"]] or [0.0])
        st = FAIL if big >= cc["fail_frac"] else (WARN if big >= cc["warn_frac"] else PASS)
        add(checks, "components", scope, st, {"detached": len(m["components"]), "largest_frac_of_main": round(big, 4)},
            {"warn_frac": cc["warn_frac"], "fail_frac": cc["fail_frac"]},
            "one connected silhouette" if not m["components"] else
            f"{len(m['components'])} detached piece(s), largest {big * 100:.1f} % of the main body")
        sc = C["shadow"]
        sf, reach, dark = m["shadow_area_frac"], m["shadow_reach_frac"], m["shadow_darkness"]
        if reach > sc["fail_reach"] or (sf > sc["fail_area"] and dark > sc["fail_darkness"]):
            st = FAIL
            txt = (f"cast shadow: {sf * 100:.1f} % of the subject area, reaching {reach * 100:.0f} % of the body "
                   f"height beyond the subject, {dark * 100:.0f} % darker than the background")
        elif sf > sc["pass_area"]:
            st = WARN
            txt = (f"soft contact shadow under the base ({sf * 100:.1f} % of the subject area, reach "
                   f"{reach * 100:.0f} %, {dark * 100:.0f} % darker); excluded from the silhouette, prep removes it")
        else:
            st, txt = PASS, "no floor shadow detected" if sf == 0 else f"trace shadow {sf * 100:.2f} %"
        add(checks, "shadow", scope, st, {"area_frac": round(sf, 4), "reach_frac_of_height": round(reach, 4),
                                          "darkness": round(dark, 4)},
            {k: sc[k] for k in ("pass_area", "fail_reach", "fail_area", "fail_darkness")}, txt, "frac")
        if vd.holes_kept:
            add(checks, "holes", scope, WARN, vd.holes_kept, {"fill_holes_max_frac": cfg["segmentation"]["fill_holes_max_frac"]},
                "large enclosed background-coloured region inside the silhouette (a see-through gap, or a subject "
                "colour equal to the background): check the contact sheet")
    # ---- pose (characters, front view)
    if kind == "character" and "front" in vds and not vds["front"].metrics.get("empty"):
        gap = vds["front"].metrics["arm_gap_rows_frac"]
        pc = C["pose"]
        st = PASS if gap >= pc["arm_gap_pass"] else (WARN if gap >= pc["arm_gap_fail"] else FAIL)
        add(checks, "pose_arm_gap", "view:front", st, round(gap, 4),
            {"pass": pc["arm_gap_pass"], "fail_below": pc["arm_gap_fail"]},
            f"{gap * 100:.0f} % of the rows between shoulders and hips show a gap between arms and torso"
            + ("" if gap >= pc["arm_gap_pass"] else " (arms touch the body: Tripo tends to fuse them)"))
    valid = [r for r in present if not vds[r].metrics.get("empty")]
    # ---- canvas consistency
    if len(set(sizes[r] for r in valid)) > 1 and inset.mode != "sheet":
        add(checks, "canvas_match", "set", WARN, {r: list(sizes[r]) for r in valid}, "identical canvas sizes",
            "views have different canvas sizes; heights/baselines are compared as fractions of each canvas")
    # ---- height
    if len(valid) >= 2:
        same = len(set(sizes[r] for r in valid)) == 1 or inset.mode == "sheet"  # sheet panels share one scale
        hs = {r: (vds[r].metrics["height_src_px"] if same else vds[r].metrics["height_frac"]) for r in valid}
        ref_role = "front" if "front" in hs else valid[0]
        med = float(np.median(list(hs.values())))
        devs = {r: hs[r] / med - 1.0 for r in hs}
        worst_role = max(devs, key=lambda r: abs(devs[r]))
        hc = C["height"]
        add(checks, "height", "set", grade_max(abs(devs[worst_role]), hc["pass"], hc["warn"]),
            {"heights": {r: round(v, 4 if not same else 1) for r, v in hs.items()},
             "deviation_from_median": {r: round(v, 4) for r, v in devs.items()}},
            {"pass": hc["pass"], "warn": hc["warn"]},
            f"largest height deviation {devs[worst_role] * 100:+.1f} % ({worst_role}); "
            + ", ".join(f"{r} {hs[r]:.0f}" if same else f"{r} {hs[r] * 100:.1f} %" for r in hs),
            "frac", note={"worst": worst_role, "ref": ref_role, "unit": "px" if same else "frac"})
        # ---- baseline (feet line), in units of the subject height
        bl = {r: vds[r].metrics["baseline_frac"] for r in valid}
        hf = float(np.median([vds[r].metrics["height_frac"] for r in valid]))
        medb = float(np.median(list(bl.values())))
        bdev = {r: (bl[r] - medb) / max(hf, 1e-6) for r in valid}
        wr = max(bdev, key=lambda r: abs(bdev[r]))
        bc = C["baseline"]
        add(checks, "baseline", "set", grade_max(abs(bdev[wr]), bc["pass"], bc["warn"]),
            {"baseline_frac_of_canvas": {r: round(v, 4) for r, v in bl.items()},
             "deviation_frac_of_height": {r: round(v, 4) for r, v in bdev.items()}},
            {"pass": bc["pass"], "warn": bc["warn"]},
            f"largest baseline offset {bdev[wr] * 100:+.1f} % of the body height ({wr}; + = lower)", "frac of height",
            note={"worst": wr})
    # ---- widths (normalised by height)
    for cid, (ra, rb) in (("width_front_back", ("front", "back")), ("width_left_right", ("left", "right"))):
        if ra in valid and rb in valid:
            na = vds[ra].metrics["aspect_w_over_h"]
            nb = vds[rb].metrics["aspect_w_over_h"]
            d = abs(na - nb) / ((na + nb) / 2.0)
            wc = C[cid]
            add(checks, cid, "set", grade_max(d, wc["pass"], wc["warn"]),
                {f"{ra}_w_over_h": round(na, 4), f"{rb}_w_over_h": round(nb, 4), "difference": round(d, 4)},
                {"pass": wc["pass"], "warn": wc["warn"]},
                f"{ra} vs {rb} width at equal height differs by {d * 100:.1f} % ({'wider: ' + (ra if na > nb else rb)})",
                "frac")
        else:
            add(checks, cid, "set", SKIP, None, None, f"needs both {ra} and {rb}")
    # ---- profile plausibility (characters): a true side view is much narrower than the front view;
    # a 3/4 view delivered as "left"/"right" mirrors fine but is nearly as wide as the front
    if kind == "character" and "front" in valid and any(r in valid for r in ("left", "right")):
        fw = vds["front"].metrics["aspect_w_over_h"]
        ratios = {r: vds[r].metrics["aspect_w_over_h"] / fw for r in ("left", "right") if r in valid}
        worst_r = max(ratios, key=ratios.get)
        pp = C["profile"]
        add(checks, "profile_plausibility", "set", PASS if ratios[worst_r] <= pp["warn_above"] else WARN,
            {k: round(v, 4) for k, v in ratios.items()}, {"warn_above": pp["warn_above"]},
            f"side/front width ratio {ratios[worst_r]:.2f} ({worst_r})"
            + ("" if ratios[worst_r] <= pp["warn_above"] else ": nearly as wide as the front, may be a 3/4 view, not a profile"))
    # ---- mirror IoU
    for cid, (ra, rb) in (("mirror_left_right", ("left", "right")), ("mirror_front_back", ("front", "back"))):
        mc = C[cid]
        if ra in valid and rb in valid:
            res = mirror_iou(vds[ra], vds[rb], float(mc["shift_search_frac"]))
            st = grade_min(res["iou"], mc["pass"], mc["warn"])
            relaxed = False
            if cid == "mirror_left_right" and asymmetric and mc.get("asymmetry_relaxes") and st == FAIL:
                st, relaxed = WARN, True
            inset.overlays[cid] = res
            add(checks, cid, "set", st,
                {"iou": round(res["iou"], 4), "iou_zero_shift": round(res["iou_zero_shift"], 4),
                 "best_shift_frac": round(res["best_shift_frac"], 4),
                 f"only_{ra}_frac": round(res["only_a_frac"], 4), f"only_{rb}_frac": round(res["only_b_frac"], 4),
                 "largest_difference": res["largest_difference"],
                 f"largest_{ra}_only": res["largest_only_a"], f"largest_{rb}_only": res["largest_only_b"]},
                {"pass": mc["pass"], "warn": mc["warn"]},
                f"{ra} vs mirrored {rb}: silhouette IoU {res['iou']:.3f}; biggest difference at "
                f"{res['largest_difference']}" + (" (FAIL relaxed: asymmetry declared)" if relaxed else ""), "IoU")
        else:
            add(checks, cid, "set", SKIP, None, None, f"needs both {ra} and {rb}")
    # ---- lighting (pairs cancel design asymmetry, keep camera-fixed light)
    lc = C["lighting"]
    light_vals = {}
    if all(p in valid for p in ("front", "back")):
        a, b = vds["front"].metrics["light_imbalance"], vds["back"].metrics["light_imbalance"]
        light_vals["front+back"] = (a + b) / 2.0
    singles = {r: vds[r].metrics["light_imbalance"] for r in valid if r in ("front", "back")}
    if light_vals or singles:
        pair_worst = max([abs(v) for v in light_vals.values()] or [0.0])
        single_worst = max([abs(v) for v in singles.values()] or [0.0])
        st = grade_max(pair_worst, lc["pass"], lc["warn"])
        if st == PASS and single_worst > lc["single_view_warn"]:
            st = WARN
        add(checks, "lighting", "set", st,
            {"pair_imbalance": {k: round(v, 4) for k, v in light_vals.items()},
             "view_imbalance": {k: round(v, 4) for k, v in singles.items()}},
            {"pass": lc["pass"], "warn": lc["warn"], "single_view_warn": lc["single_view_warn"]},
            f"side-light index {pair_worst * 100:.1f} % (median brightness ratio of mirrored pixel pairs, front and "
            f"back averaged); worst single view {single_worst * 100:.1f} %", "frac")
    # ---- palette
    pcfg = C["palette"]
    if inset.palette is not None:
        pal = palette_from_image(inset.palette)
        if pal:
            labs = np.array([p["lab"] for p in pal])
            per = {}
            worst_txt = ""
            worst_de = -1.0
            for r in valid:
                de, wi = colour_distance(vds[r].metrics.get("dominant", []), labs, float(pcfg["min_cluster_frac"]))
                per[r] = de
                if wi and wi[0] > worst_de:
                    worst_de = wi[0]
                    worst_txt = f"{wi[1]} in {r} (nearest palette {pal[wi[2]]['hex']}, dE00 {wi[0]:.1f})"
            mean_de = float(np.nanmax(list(per.values()))) if per else float("nan")
            add(checks, "palette", "set", grade_max(mean_de, pcfg["pass"], pcfg["warn"]),
                {"mean_dE00_per_view": {k: round(v, 2) for k, v in per.items()},
                 "palette": [p["hex"] for p in pal], "worst": worst_txt},
                {"pass": pcfg["pass"], "warn": pcfg["warn"]},
                f"dominant colours vs palette.png: worst view mean dE00 {mean_de:.1f}; worst colour {worst_txt}", "dE00")
        else:
            add(checks, "palette", "set", WARN, None, None, "palette.png has no readable flat swatches")
    else:
        add(checks, "palette", "set", SKIP, None, None, "no palette.png supplied")
    # ---- colour consistency between views (vs front)
    vc = C["view_colour_consistency"]
    if "front" in valid and len(valid) >= 2 and vds["front"].metrics.get("dominant"):
        fl = np.array([d["lab"] for d in vds["front"].metrics["dominant"]])
        per = {}
        detail = {}
        for r in valid:
            if r == "front" or not vds[r].metrics.get("dominant"):
                continue
            rl = np.array([d["lab"] for d in vds[r].metrics["dominant"]])
            d1, w1 = colour_distance(vds[r].metrics["dominant"], fl, float(pcfg["min_cluster_frac"]))
            d2, _ = colour_distance(vds["front"].metrics["dominant"], rl, float(pcfg["min_cluster_frac"]))
            per[r] = max(d1, d2)
            if w1:
                detail[r] = f"{w1[1]} vs front {vds['front'].metrics['dominant'][w1[2]]['hex']} (dE00 {w1[0]:.1f})"
        if per:
            wr = max(per, key=per.get)
            add(checks, "view_colour_consistency", "set", grade_max(per[wr], vc["pass"], vc["warn"]),
                {"mean_dE00_vs_front": {k: round(v, 2) for k, v in per.items()}, "worst_colour": detail},
                {"pass": vc["pass"], "warn": vc["warn"]},
                f"dominant colours vs the front view: worst {wr} mean dE00 {per[wr]:.1f}", "dE00", note={"worst": wr})
    return checks


# --------------------------------------------------------------------------- regen notes


FORMAT_COVERED = {"resolution", "aspect", "background", "margins", "fill", "shadow", "centring", "canvas_match",
                  "view_count"}


def _views_txt(views: list) -> str:
    if len(views) == 4 and set(views) == set(ROLES):
        return "all four views"
    if len(views) == 1:
        return f"the {views[0]} view"
    return "the " + ", ".join(views[:-1]) + f" and {views[-1]} views"


def _note_for_views(cid: str, status: str, items: list, vds: dict, canvas: int, ht: int, fill: float) -> str:
    """One merged instruction for a per-view check that fails or warns in several views."""
    views = [v for v, _ in items]
    vt = _views_txt(views)
    vals = {v: c["value"] for v, c in items}
    verb = "is" if len(views) == 1 else "are"
    if cid == "subject_found":
        return f"No subject could be separated in {vt}. Use one subject on a flat #FFFFFF or transparent background."
    if cid == "resolution":
        sizes = sorted({f"{vals[v]['width']}x{vals[v]['height']}" for v in views})
        hs = [vals[v]["subject_height_px"] for v in views]
        return (f"{vt[0].upper() + vt[1:]} {verb} {' / '.join(sizes)} px with the subject {min(hs)}-{max(hs)} px tall. "
                f"Deliver {canvas}x{canvas} px with the subject about {ht} px tall.")
    if cid == "aspect":
        sizes = sorted({f"{vds[v].size[0]}x{vds[v].size[1]}" for v in views})
        return f"{vt[0].upper() + vt[1:]} {verb} {', '.join(sizes)}, not square. Deliver {canvas}x{canvas} squares."
    if cid == "background":
        if status == FAIL:
            return (f"The background is not clean in {vt} ({'; '.join(c['detail'] for _, c in items)}). Use a pure "
                    f"flat #FFFFFF or transparent background: no floor, horizon, texture, vignette or props.")
        hexes = sorted({vals[v].get("mean_hex") or "" for v in views})
        rng = max(float(vals[v].get("range") or 0) for v in views)
        return (f"{vt[0].upper() + vt[1:]} use a studio backdrop ({', '.join(hexes)}, gradient up to {rng:.0f} levels, "
                f"floor and horizon visible) instead of flat #FFFFFF or transparent. Prep flattens it, but ask for pure "
                f"white or transparent next time.")
    if cid == "centring":
        parts = [f"the {v} view sits {abs(vals[v]) * 100:.1f} % of the width {'right' if vals[v] > 0 else 'left'} of centre"
                 for v in views]
        return f"Off-centre subject: {'; '.join(parts)}. Centre the subject horizontally in every view."
    if cid == "margins":
        if status == FAIL:
            return (f"Cropped: {'; '.join(v + ': ' + c['detail'] for v, c in items)}. Show the whole subject with "
                    f"about 10 % empty margin on every side; nothing may touch the frame edge.")
        parts = []
        for v, c in items:
            side = min(c["value"], key=c["value"].get)
            parts.append(f"{v} {side} {c['value'][side] * 100:.1f} %")
        return f"Tight margins ({', '.join(parts)}). Leave about 10 % empty margin on every side."
    if cid == "fill":
        fills = [vals[v] * 100 for v in views]
        span = f"{min(fills):.0f}" if round(min(fills)) == round(max(fills)) else f"{min(fills):.0f}-{max(fills):.0f}"
        return (f"The subject fills {span} % of the frame in {vt}; frame it at about {fill * 100:.0f} % of the image "
                f"height.")
    if cid == "thin_parts":
        d = vds[views[0]].metrics["thin"]["diameter_at_2048_px"]
        parts = []
        for v in views:
            th = vds[v].metrics["thin"]
            where = "; ".join(p["where"] for p in th["parts"][:2]) or "small pieces"
            parts.append(f"{v} {th['area_frac'] * 100:.1f} % ({where})")
        return (f"Thin parts narrower than {d:.0f} px on a {canvas} px canvas (3 % of the width): "
                f"{', '.join(parts)} of the silhouette. Thicken straps, horns, tails, hair strands and ornaments to at "
                f"least that width, or leave them out of the Tripo views (weapons and staffs are generated as separate "
                f"assets).")
    if cid == "components":
        parts = [f"{v}: {vals[v]['detached']} piece(s), largest {vals[v]['largest_frac_of_main'] * 100:.1f} % of the body"
                 for v in views]
        return (f"Pieces not connected to the body ({'; '.join(parts)}). Remove labels, text, scale bars and floating "
                f"parts; every part must visibly connect to the body.")
    if cid == "shadow":
        areas = [vals[v]["area_frac"] * 100 for v in views]
        aspan = f"{min(areas):.0f}" if round(min(areas)) == round(max(areas)) else f"{min(areas):.0f}-{max(areas):.0f}"
        if status == FAIL:
            return (f"Cast shadow in {vt} ({'; '.join(c['detail'] for _, c in items)}). Use flat, neutral, shadowless "
                    f"light with no floor plane.")
        return (f"Soft contact shadows under the feet in {vt} ({aspan} % of the "
                f"body area). They are excluded from the silhouette and prep removes them, but ask for flat shadowless "
                f"light with no floor next time.")
    if cid == "holes":
        return (f"Large enclosed background-coloured region inside the silhouette in {vt}. If it is a see-through gap, "
                f"that is fine; if it is a white or grey part of the design, use a transparent background.")
    if cid == "pose_arm_gap":
        shown = "none" if vals["front"] < 0.005 else f"only {vals['front'] * 100:.0f} %"
        return (f"Front view: the arms touch the body in the silhouette ({shown} of the rows between shoulders and hips "
                f"show a gap). Use an A-pose: arms about 30-45 degrees down with a clear gap to the torso, hands open, "
                f"legs slightly apart.")
    return f"{cid} in {vt}: " + "; ".join(c["detail"] for _, c in items)


def _note_for_set(c: dict, canvas: int, base_y: int) -> str:
    cid, v = c["id"], c["value"]
    if cid == "view_count":
        extra = ""
        if v["unassigned"]:
            extra = (f" The input also holds {len(v['unassigned'])} image(s) that are not named as views "
                     f"({', '.join(v['unassigned'][:4])}{'...' if len(v['unassigned']) > 4 else ''}).")
        return (f"Missing view(s): {', '.join(v['missing'])}. Deliver four separate PNGs named front.png, back.png, "
                f"left.png and right.png (one subject per image, no sheets, no labels).{extra}")
    if cid == "height":
        note = c.get("note", {})
        wr, ref = note.get("worst"), note.get("ref", "front")
        hs = v["heights"]
        if wr == ref:
            others = [r for r in hs if r != ref]
            ref = others[0] if others else ref
        pct = (hs[wr] / hs[ref] - 1.0) * 100 if hs.get(ref) else 0.0
        if note.get("unit") == "px":
            vw, vr = f"{hs[wr]:.0f} px", f"{hs[ref]:.0f} px"
        else:
            vw, vr = f"{hs[wr] * 100:.1f} % of the image", f"{hs[ref] * 100:.1f} % of the image"
        return (f"The {wr} view is {abs(pct):.1f} % {'shorter' if pct < 0 else 'taller'} than the {ref} view ({vw} vs "
                f"{vr}). Keep the same scale and baseline in all four views: the top of the head (or hat/horns) and the "
                f"soles must sit on the same two lines (y={canvas - base_y} and y={base_y} on a {canvas} px canvas).")
    if cid == "baseline":
        wr = c.get("note", {}).get("worst")
        d = v["deviation_frac_of_height"][wr]
        return (f"The {wr} view's feet sit {abs(d) * 100:.1f} % of the body height {'lower' if d > 0 else 'higher'} "
                f"than in the other views. Put the soles (or the base) on the same baseline in every view (y={base_y} "
                f"on a {canvas} px canvas).")
    if cid in ("width_front_back", "width_left_right"):
        a, b = ("front", "back") if cid == "width_front_back" else ("left", "right")
        na, nb = v[f"{a}_w_over_h"], v[f"{b}_w_over_h"]
        wide, narrow = (a, b) if na > nb else (b, a)
        what = ("same arm angle, same sleeve/cape/skirt spread, same stance" if a == "front"
                else "same depth: chest to back, cape, skirt, tail, feet")
        return (f"The {wide} view is {v['difference'] * 100:.1f} % wider than the {narrow} view at equal height. The "
                f"{a} and {b} silhouettes must have the same width ({what}).")
    if cid in ("mirror_left_right", "mirror_front_back"):
        a, b = ("left", "right") if cid == "mirror_left_right" else ("front", "back")
        oa, ob = v[f"only_{a}_frac"], v[f"only_{b}_frac"]
        big, small = (a, b) if oa >= ob else (b, a)
        loc = v.get(f"largest_{big}_only") or v["largest_difference"]
        if a == "left":
            intro = "The left and right views do not mirror each other"
            rule = ("In an orthographic turnaround the right outline is exactly the left outline flipped, even for "
                    "asymmetric designs.")
        else:
            intro = "The back view's outline is not the mirror of the front view's outline"
            rule = ("Seen from behind, the outline must be the front outline flipped: same pose, arm angles, hair, hat, "
                    "cape and tail; anything that sticks out in front must also stick out, flipped, at the back.")
        return (f"{intro} (silhouette IoU {v['iou']:.3f}; PASS needs {c['threshold']['pass']:.2f}). The {big} view has extra "
                f"silhouette ({max(oa, ob) * 100:.0f} % of its area, against {min(oa, ob) * 100:.0f} % the other way), "
                f"mostly at the {loc} as drawn in the {a} view. {rule} Redraw the {small} view so its outline includes "
                f"that part, or remove it from the {big} view, so both outlines agree.")
    if cid == "lighting":
        return (f"Lighting is directional ({c['detail']}). Use flat, even, neutral light with no key-light side and no "
                f"cast shadows, so the views read like albedo.")
    if cid == "palette":
        return f"Colours drift from palette.png ({c['detail']}). Use the palette strip's hex colours."
    if cid == "view_colour_consistency":
        wr = c.get("note", {}).get("worst")
        return (f"The {wr} view's colours differ from the front view (mean dE00 {v['mean_dE00_vs_front'][wr]:.1f}; "
                f"{v['worst_colour'].get(wr, '')}). Use identical colours and materials in every view.")
    if cid == "canvas_match":
        return f"The views have different canvas sizes; deliver every view at {canvas}x{canvas}."
    if cid == "profile_plausibility":
        return (f"The side views are nearly as wide as the front view ({c['detail']}). Left and right must be true "
                f"90-degree profiles (camera exactly at the side, orthographic), not 3/4 views.")
    return f"{cid}: {c['detail']}"


def build_notes(asset: str, checks: list, vds: dict, verdict: str, round_no: int, cfg: dict, kind: str,
                inset: InputSet) -> str:
    canvas = int(cfg["target"]["canvas_px"])
    fill = float(cfg["target"]["fill_height"])
    ht = int(round(canvas * fill))
    base_y = int(round((canvas + ht) / 2))
    fails = [c for c in checks if c["status"] == FAIL]
    warns = [c for c in checks if c["status"] == WARN]

    def merged(status: str) -> list:
        order: list = []
        groups: dict = {}
        for c in checks:
            if c["status"] != status:
                continue
            if c["scope"].startswith("view:"):
                if c["id"] not in groups:
                    groups[c["id"]] = []
                    order.append(("view", c["id"]))
                groups[c["id"]].append((c["scope"].split(":", 1)[1], c))
            else:
                order.append(("set", c))
        out = []
        for kind_, item in order:
            if kind_ == "set":
                out.append((item["id"], _note_for_set(item, canvas, base_y)))
            else:
                out.append((item, _note_for_views(item, status, groups[item], vds, canvas, ht, fill)))
        return out

    fix_lines = merged(FAIL)
    warn_lines = merged(WARN)
    keep = []
    for c in checks:
        if c["status"] != PASS:
            continue
        cid = c["id"]
        if cid == "height":
            keep.append("All views share the same height (within 3 %).")
        elif cid == "baseline":
            keep.append("The feet sit on the same baseline in every view.")
        elif cid == "mirror_left_right":
            keep.append(f"Left and right silhouettes mirror cleanly (IoU {c['value']['iou']:.2f}).")
        elif cid == "mirror_front_back":
            keep.append(f"Front and back silhouettes mirror cleanly (IoU {c['value']['iou']:.2f}).")
        elif cid == "width_front_back":
            keep.append("Front and back widths match.")
        elif cid == "width_left_right":
            keep.append("Left and right widths match.")
        elif cid == "pose_arm_gap":
            keep.append("The front pose shows clear gaps between arms and torso.")
        elif cid == "lighting":
            keep.append("No strong directional side light.")
        elif cid == "view_colour_consistency":
            keep.append("Colours are consistent between views.")
    lines = [f"# Regen notes: {asset}", "",
             f"Automatic pre-check by `tools/art/turnaround_qa.py` {TOOL_VERSION}. Verdict: **{verdict}** "
             f"({len(fails)} FAIL and {len(warns)} WARN check results). Round {round_no} of max 3.", "",
             "This is the automatic half of the gate. Claude's design review (style, originality, read at game "
             "distance, Tripo-buildability) still applies before anything goes to Tripo.", ""]
    if inset.notes:
        lines += ["Input notes:"] + [f"- {n}" for n in inset.notes] + [""]
    vc = next((c for c in checks if c["id"] == "view_count"), None)
    hc = next((c for c in checks if c["id"] == "height"), None)
    big_h = hc is not None and max(abs(v) for v in hc["value"]["deviation_from_median"].values()) > 0.25
    if (vc and vc["value"]["missing"] and (vc["value"]["unassigned"] or not vc["value"]["present"])) or big_h:
        lines += ["> **This input does not look like one subject seen from four sides** (missing views and/or heights "
                  "that differ by more than 25 %). Check that the right files were supplied before regenerating; "
                  "UI art, atlases and texture sheets need their own checks, not this gate.", ""]
    lines += ["## Fix these (FAIL)", ""]
    lines += ([f"{i}. {t}" for i, (_, t) in enumerate(fix_lines, 1)] if fix_lines
              else ["Nothing failed. The set may go to Claude's design review."]) + [""]
    if warn_lines:
        lines += ["## Also fix when regenerating (WARN)", ""] + [f"- {t}" for _, t in warn_lines] + [""]
    if keep:
        lines += ["## Keep (passed)", ""] + [f"- {t}" for t in dict.fromkeys(keep)] + [""]
    if verdict == "REGEN":
        pose = ("A-pose: arms about 30-45 degrees down, hands open, legs slightly apart" if kind == "character"
                else "neutral standing pose, legs apart, mouth slightly open" if kind == "monster"
                else "neutral upright placement")
        design_warns = [t for cid, t in warn_lines if cid not in FORMAT_COVERED]
        prompt = [f"TASK F6 regen - {asset} turnaround, round {round_no + 1} of max 3.",
                  "Keep the design exactly as approved (shapes, colours, materials, proportions). Change only what is listed.",
                  "Fix:"] + [f"- {t}" for _, t in fix_lines] + (
            ["Also fix:"] + [f"- {t}" for t in design_warns] if design_warns else []) + [
            "Format (checked automatically):",
            f"- 4 separate PNGs: front.png, back.png, left.png, right.png; {canvas}x{canvas} px each;",
            f"- subject centred, about {fill * 100:.0f} % of the image height, soles on the same baseline "
            f"(y={base_y}) in every view;",
            "- same scale in all views (height within 3 %, front/back and left/right widths within 5 %);",
            "- orthographic, camera at mid-height, no perspective;",
            "- flat #FFFFFF or transparent background, no floor, no cast or contact shadows, flat neutral light;",
            f"- {pose};",
            "- right view = exact mirror outline of the left view; back outline = mirror of the front outline;",
            "- thin parts (straps, horns, tails, weapons) at least 3 % of the image width; no floating parts; no text "
            "or labels on the views.",
            "Deliver turnarounds_<asset>_v<N>.zip with front/back/left/right/hero34/palette PNGs, README.md and "
            "receipt.json."]
        lines += ["## Paste-ready prompt for froggy", "", "```text"] + prompt + ["```", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- contact sheet


_FONT_CACHE: dict = {}


def font(size: int):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    f = None
    for name in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf", "Arial.ttf"):
        try:
            f = ImageFont.truetype(name, size)
            break
        except OSError:
            continue
    if f is None:
        try:
            f = ImageFont.load_default(size=size)
        except TypeError:  # pragma: no cover - old Pillow
            f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


_COL = {PASS: (70, 200, 110), WARN: (240, 190, 50), FAIL: (240, 80, 70), SKIP: (150, 150, 150),
        "PASS_V": (60, 190, 100), "REGEN": (235, 70, 60)}


def _dashed_h(draw, x0, x1, y, fill, dash=12, width=2):
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill=fill, width=width)
        x += 2 * dash


def _dashed_v(draw, x, y0, y1, fill, dash=10, width=1):
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + dash, y1))], fill=fill, width=width)
        y += 2 * dash


VIEW_CHECK_ROWS = ("resolution", "aspect", "background", "centring", "margins", "fill", "thin_parts", "components",
                   "shadow", "holes", "pose_arm_gap", "subject_found")


def _fit(draw, text: str, fnt, maxw: float) -> str:
    if draw.textlength(text, font=fnt) <= maxw:
        return text
    while len(text) > 4 and draw.textlength(text + "...", font=fnt) > maxw:
        text = text[:-1]
    return text + "..."


def _contact_no_views(path: Path, asset: str, verdict: str, checks: list, inset: InputSet):
    """Contact sheet for inputs without usable views: thumbnails of what was found, plus the checks."""
    pad, thumb, per_row = 16, 360, 4
    srcs = list(inset.unassigned)[:16]
    rows = max(1, math.ceil(len(srcs) / per_row))
    set_rows = [c for c in checks if c["scope"] == "set"]
    width = pad + per_row * (thumb + pad)
    height = 96 + 70 + rows * (thumb + 40) + 50 + 24 * len(set_rows) + pad
    sheet = Image.new("RGB", (width, height), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    d.rectangle([0, 0, width, 96], fill=(36, 36, 42))
    d.text((pad, 12), f"TURNAROUND QA  {asset}", font=font(34), fill=(240, 240, 240))
    d.text((pad, 58), f"{TOOL_NAME} {TOOL_VERSION}  |  input: {inset.mode}", font=font(18), fill=(170, 170, 170))
    vt = f"VERDICT: {verdict}"
    tw = d.textlength(vt, font=font(40))
    d.rectangle([width - tw - 2 * pad - 10, 14, width - pad, 76], fill=_COL["REGEN"] if verdict == "REGEN" else _COL["PASS_V"])
    d.text((width - tw - pad - 18, 20), vt, font=font(40), fill=(255, 255, 255))
    d.text((pad, 110), f"Not a turnaround set: no front/back/left/right views ({len(inset.unassigned)} other image(s) found).",
           font=font(26), fill=(240, 80, 70))
    for i, src in enumerate(srcs):
        x = pad + (i % per_row) * (thumb + pad)
        y = 166 + (i // per_row) * (thumb + 40)
        try:
            im = decode(src.data).convert("RGBA")
            if src.crop:
                im = im.crop(src.crop)
            im.thumbnail((thumb, thumb))
            cell = Image.new("RGBA", (thumb, thumb), (60, 60, 66, 255))
            cell.alpha_composite(im, ((thumb - im.size[0]) // 2, (thumb - im.size[1]) // 2))
            sheet.paste(cell.convert("RGB"), (x, y))
        except Exception:
            d.rectangle([x, y, x + thumb, y + thumb], outline=(240, 80, 70))
        d.text((x, y + thumb + 6), _fit(d, Path(src.member or src.label).name, font(15), thumb), font=font(15),
               fill=(200, 200, 200))
    ty = 166 + rows * (thumb + 40) + 10
    d.text((pad, ty), "Set checks", font=font(22), fill=(240, 240, 240))
    for i, c in enumerate(set_rows):
        yy = ty + 34 + 24 * i
        d.rectangle([pad, yy + 2, pad + 56, yy + 21], fill=_COL[c["status"]])
        d.text((pad + 6, yy + 2), c["status"], font=font(15), fill=(0, 0, 0))
        d.text((pad + 66, yy + 1), _fit(d, f"{c['id']}: {c['detail']}", font(16), width - 90), font=font(16),
               fill=(215, 215, 215))
    sheet.save(path, optimize=True)


def make_contact(path: Path, asset: str, verdict: str, checks: list, vds: dict, inset: InputSet, cfg: dict):
    panel_h, pad = 640, 16
    order = [r for r in ("front", "left", "back", "right") if r in vds and not vds[r].metrics.get("empty")]
    tiles = []
    for role in order:
        vd = vds[role]
        im = decode(vd.source.data)
        if vd.source.crop:
            im = im.crop(vd.source.crop)
        im = im.convert("RGBA")
        W, H = im.size
        s = panel_h / float(H)
        pw = max(1, int(round(W * s)))
        if vd.has_alpha:  # checkerboard behind transparency
            cb = (np.indices((H, W)).sum(0) // max(8, W // 64)) % 2
            arr = np.where(cb == 0, 235, 205).astype(np.uint8)
            base = Image.fromarray(np.dstack([arr, arr, arr, np.full((H, W), 255, np.uint8)]), "RGBA")
        else:
            base = Image.new("RGBA", im.size, (255, 255, 255, 255))
        base.alpha_composite(im)
        tile = base.convert("RGB").resize((pw, panel_h), Image.LANCZOS)
        arr = np.asarray(tile).astype(np.float32)
        if vd.thin_mask is not None and vd.thin_mask.any():
            thin = resize_mask_nearest(vd.thin_mask, (pw, panel_h))
            arr[thin] = arr[thin] * 0.35 + np.array([255, 0, 200]) * 0.65
        if vd.shadow.any():
            sh = resize_mask_nearest(vd.shadow, (pw, panel_h))
            arr[sh] = arr[sh] * 0.4 + np.array([40, 110, 255]) * 0.6
        tile = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
        d = ImageDraw.Draw(tile)
        bx0, by0, bx1, by1 = [v * s for v in vd.metrics["bbox_src"]]
        d.rectangle([bx0, by0, bx1, by1], outline=(255, 210, 0), width=2)
        _dashed_v(d, pw / 2.0, 0, panel_h, (120, 120, 120), width=1)
        cxv = (bx0 + bx1) / 2.0
        d.line([(cxv, by0), (cxv, by1)], fill=(0, 200, 255), width=2)
        d.line([(0, by1), (pw, by1)], fill=(40, 200, 80), width=2)
        d.line([(0, by0), (pw, by0)], fill=(40, 200, 80), width=1)
        tiles.append((role, tile, vd))
    if not tiles:
        _contact_no_views(path, asset, verdict, checks, inset)
        return
    med_base = float(np.median([t[2].metrics["baseline_frac"] for t in tiles])) if tiles else 0.0
    med_top = float(np.median([t[2].metrics["top_frac"] for t in tiles])) if tiles else 0.0
    view_rows = [cid for cid in VIEW_CHECK_ROWS if any(c["id"] == cid and c["scope"].startswith("view:") for c in checks)]
    set_rows = [c for c in checks if c["scope"] == "set"]
    header_h, text_h, ov_h = 96, 150, 400
    row_h = 24
    matrix_h = 40 + row_h * (len(view_rows) + 1)
    set_h = 40 + row_h * len(set_rows)
    panels_w = sum(t[1].size[0] for t in tiles) + pad * (len(tiles) + 1)
    width = max(panels_w, 1700)
    body_top = header_h + pad
    y_text = body_top + panel_h + 6
    y_legend = y_text + text_h
    y_ov = y_legend + 34
    y_tables = y_ov + ov_h + pad
    height = y_tables + max(matrix_h, set_h) + pad
    if not tiles:
        height = max(height, header_h + 520)
    sheet = Image.new("RGB", (width, height), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    vcol = _COL["REGEN"] if verdict == "REGEN" else _COL["PASS_V"]
    d.rectangle([0, 0, width, header_h], fill=(36, 36, 42))
    d.text((pad, 12), f"TURNAROUND QA  {asset}", font=font(34), fill=(240, 240, 240))
    d.text((pad, 58), _fit(d, f"{TOOL_NAME} {TOOL_VERSION}  |  input: {inset.mode}  |  "
                              f"{_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}  |  automatic pre-check; Claude's "
                              f"design review is separate", font(18), width - 480), font=font(18), fill=(170, 170, 170))
    vt = f"VERDICT: {verdict}"
    tw = d.textlength(vt, font=font(40))
    d.rectangle([width - tw - 2 * pad - 10, 14, width - pad, 76], fill=vcol)
    d.text((width - tw - pad - 18, 20), vt, font=font(40), fill=(255, 255, 255))
    x = pad
    for role, tile, vd in tiles:
        pw = tile.size[0]
        sheet.paste(tile, (x, body_top))
        _dashed_h(d, x, x + pw, body_top + med_base * panel_h, (255, 0, 255), width=2)
        _dashed_h(d, x, x + pw, body_top + med_top * panel_h, (255, 0, 255), dash=6, width=1)
        d.rectangle([x, body_top, x + 150, body_top + 30], fill=(0, 0, 0))
        d.text((x + 6, body_top + 4), role.upper(), font=font(22), fill=(255, 255, 255))
        vs = worst(c["status"] for c in checks if c["scope"] == f"view:{role}")
        d.rectangle([x + pw - 90, body_top, x + pw, body_top + 30], fill=_COL[vs])
        d.text((x + pw - 84, body_top + 4), vs, font=font(20), fill=(0, 0, 0))
        m = vd.metrics
        info = [f"{vd.size[0]}x{vd.size[1]}  {'alpha' if vd.has_alpha else 'bg ' + str(vd.bg_stats.get('mean_hex', ''))}",
                f"h {m['height_src_px']:.0f}px ({m['height_frac'] * 100:.0f}%)  w/h {m['aspect_w_over_h']:.3f}",
                f"centre {m['centre_offset_frac'] * 100:+.1f}%  baseline {m['baseline_frac'] * 100:.1f}%",
                f"thin {m['thin']['area_frac'] * 100:.2f}%  shadow {m['shadow_area_frac'] * 100:.1f}%"
                f" (reach {m['shadow_reach_frac'] * 100:.0f}%)",
                _fit(d, Path(vd.source.member or vd.source.label).name, font(15), pw - 8)]
        for i, line in enumerate(info):
            d.text((x + 4, y_text + i * 24), line, font=font(17 if i < 4 else 15),
                   fill=(220, 220, 220) if i < 4 else (150, 150, 150))
        x += pw + pad
    if not tiles:
        d.text((pad, body_top + 20), "No front/back/left/right views were found in this input.", font=font(30),
               fill=(240, 80, 70))
        tx, ty = pad, body_top + 80
        for src in (inset.unassigned or [])[:8]:
            try:
                im = decode(src.data).convert("RGBA")
                if src.crop:
                    im = im.crop(src.crop)
                im.thumbnail((300, 300))
                bgc = Image.new("RGBA", im.size, (60, 60, 66, 255))
                bgc.alpha_composite(im)
                sheet.paste(bgc.convert("RGB"), (tx, ty))
                d.text((tx, ty + 306), _fit(d, Path(src.member or src.label).name, font(15), 300), font=font(15),
                       fill=(200, 200, 200))
                tx += 320
                if tx + 300 > width:
                    break
            except Exception:
                continue
    legend = [((255, 210, 0), "bbox"), ((40, 200, 80), "this view top/baseline"),
              ((255, 0, 255), "median top/baseline (dashed)"), ((0, 200, 255), "bbox centre"),
              ((120, 120, 120), "image centre (dashed)"), ((255, 0, 200), "thin parts"), ((40, 110, 255), "floor shadow")]
    lx = pad
    for colr, txt in legend:
        d.rectangle([lx, y_legend + 4, lx + 18, y_legend + 18], fill=colr)
        d.text((lx + 24, y_legend + 1), txt, font=font(16), fill=(200, 200, 200))
        lx += 34 + int(d.textlength(txt, font=font(16)))
    ox = pad
    for cid, title in (("mirror_left_right", "LEFT vs flipped RIGHT"), ("mirror_front_back", "FRONT vs flipped BACK")):
        res = inset.overlays.get(cid)
        if res is None:
            continue
        ov = Image.fromarray(res["overlay"])
        ov.thumbnail((10000, ov_h - 64))
        st = next((c["status"] for c in checks if c["id"] == cid), SKIP)
        d.text((ox, y_ov), f"{title}: IoU {res['iou']:.3f}  {st}", font=font(20), fill=_COL[st])
        sheet.paste(ov, (ox, y_ov + 30))
        a, b = title.split(" vs flipped ")
        d.text((ox, y_ov + 34 + ov.size[1]), f"red = {a.lower()} only, cyan = {b.lower()} only, grey = both",
               font=font(14), fill=(190, 190, 190))
        ox += max(ov.size[0], 400) + 3 * pad
    # per-view matrix
    mx, my = pad, y_tables
    d.text((mx, my), "Per-view checks", font=font(22), fill=(240, 240, 240))
    col0 = 170
    colw = 92
    for j, role in enumerate(ROLES):
        d.text((mx + col0 + j * colw, my + 34), role, font=font(16), fill=(200, 200, 200))
    for i, cid in enumerate(view_rows):
        yy = my + 34 + row_h * (i + 1)
        d.text((mx, yy), cid, font=font(16), fill=(215, 215, 215))
        for j, role in enumerate(ROLES):
            c = next((c for c in checks if c["id"] == cid and c["scope"] == f"view:{role}"), None)
            st = c["status"] if c else SKIP
            if c is None and cid == "pose_arm_gap":
                continue
            d.rectangle([mx + col0 + j * colw, yy + 2, mx + col0 + j * colw + colw - 10, yy + row_h - 3], fill=_COL[st])
            d.text((mx + col0 + j * colw + 6, yy + 2), st, font=font(15), fill=(0, 0, 0))
    # set-level list
    sx0 = mx + col0 + 4 * colw + 3 * pad
    d.text((sx0, my), "Set checks", font=font(22), fill=(240, 240, 240))
    for i, c in enumerate(set_rows):
        yy = my + 34 + row_h * i
        d.rectangle([sx0, yy + 2, sx0 + 56, yy + row_h - 3], fill=_COL[c["status"]])
        d.text((sx0 + 6, yy + 2), c["status"], font=font(15), fill=(0, 0, 0))
        d.text((sx0 + 66, yy + 1), _fit(d, f"{c['id']}: {c['detail']}", font(16), width - sx0 - 80), font=font(16),
               fill=(215, 215, 215))
    sheet.save(path, optimize=True)


# --------------------------------------------------------------------------- prep for Tripo


def _alpha_full(vd: ViewData, rgba_full: np.ndarray, cfg: dict) -> tuple:
    """Full-resolution soft alpha and the background model (None for alpha sources)."""
    H, W = rgba_full.shape[:2]
    if vd.has_alpha:
        # keep only alpha near the cleaned subject, so stray specks cannot move the bbox or reach Tripo
        keep = resize_mask_nearest(dilate_disk(vd.mask, 2), (W, H))
        return rgba_full[..., 3].astype(np.float32) / 255.0 * keep, None
    seg = cfg["segmentation"]
    bg = np.stack([np.asarray(Image.fromarray(vd.bg[..., c].astype(np.float32), "F").resize((W, H), Image.BILINEAR))
                   for c in range(3)], -1)
    rgb = rgba_full[..., :3].astype(np.float32)
    diff = np.sqrt(((rgb - bg) ** 2).sum(-1))
    lo, hi = vd.thr * float(seg["soft_alpha_lo"]), vd.thr * float(seg["soft_alpha_hi"])
    soft = np.clip((diff - lo) / max(hi - lo, 1e-3), 0.0, 1.0)
    core = resize_mask_nearest(erode_disk(vd.mask, 1), (W, H))
    near = resize_mask_nearest(dilate_disk(vd.mask, 1), (W, H))
    shadow = resize_mask_nearest(vd.shadow, (W, H))
    alpha = np.where(core, 1.0, np.where(near & ~shadow, soft, 0.0)).astype(np.float32)
    return alpha, bg


def prep_views(vds: dict, out_dir: Path, cfg: dict, keep_alpha: bool, report_path: Path, verdict: str,
               forced: bool, asset: str, round_no: int, design_review: str = "PENDING",
               reviewer: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    canvas = int(cfg["target"]["canvas_px"])
    fill = float(cfg["target"]["fill_height"])
    max_w = float(cfg["target"]["max_fill_width"])
    roles = [r for r in ROLES if r in vds and not vds[r].metrics.get("empty")]
    prepared = {}
    for role in roles:
        vd = vds[role]
        im = decode(vd.source.data)
        if vd.source.crop:
            im = im.crop(vd.source.crop)
        rgba = np.asarray(im.convert("RGBA"), dtype=np.uint8)
        alpha, bg = _alpha_full(vd, rgba, cfg)
        sel = alpha > 0.5
        bb = bbox_of(sel)
        if bb is None:
            raise RuntimeError(f"{role}: empty alpha at full resolution")
        x0, y0, x1, y1 = bb
        prepared[role] = (rgba, alpha, bg, (float(x0), float(y0), float(x1 + 1), float(y1 + 1)))
    ht = fill * canvas
    for role in roles:
        _, _, _, (x0, y0, x1, y1) = prepared[role]
        s = ht / (y1 - y0)
        if (x1 - x0) * s > max_w * canvas:
            ht *= max_w * canvas / ((x1 - x0) * s)
    top = (canvas - ht) / 2.0
    base_y = top + ht
    views_out = {}
    for role in roles:
        vd = vds[role]
        rgba, alpha, bg, (x0, y0, x1, y1) = prepared[role]
        H, W = alpha.shape
        rgb = rgba[..., :3].astype(np.float32)
        a3 = alpha[..., None]
        white = np.float32(255.0)
        if keep_alpha:
            if bg is None:
                col = rgb
            else:
                col = np.where(a3 > 1e-3, (rgb - (1.0 - a3) * bg) / np.maximum(a3, 1e-3), 0.0)
            arr = np.dstack([np.clip(col, 0, 255), alpha * 255.0]).astype(np.uint8)
            src_im = Image.fromarray(arr, "RGBA").convert("RGBa")
            pad_val = (0, 0, 0, 0)
        else:
            if bg is None:
                out = a3 * rgb + (1.0 - a3) * white
            else:
                out = np.where(a3 > 0, rgb + (1.0 - a3) * (white - bg), white)
            src_im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
            pad_val = (255, 255, 255)
        s = ht / (y1 - y0)
        cx = (x0 + x1) / 2.0
        box = [cx - (canvas / 2.0) / s, y1 - base_y / s, cx + (canvas / 2.0) / s, y1 + (canvas - base_y) / s]
        padn = int(math.ceil(max(0.0, -box[0], -box[1], box[2] - W, box[3] - H))) + 4
        padded = Image.new(src_im.mode, (W + 2 * padn, H + 2 * padn), pad_val)
        padded.paste(src_im, (padn, padn))
        pbox = (box[0] + padn, box[1] + padn, box[2] + padn, box[3] + padn)
        res = padded.resize((canvas, canvas), Image.LANCZOS, box=pbox)
        if keep_alpha:
            res = res.convert("RGBA")
        out_path = out_dir / f"{role}.png"
        res.save(out_path, optimize=True)
        views_out[role] = {
            "source": vd.source.label, "source_path": vd.source.path, "source_member": vd.source.member,
            "source_crop": list(vd.source.crop) if vd.source.crop else None,
            "source_sha256": vd.source.sha256, "source_size": [W, H],
            "subject_bbox_src": [round(v, 2) for v in (x0, y0, x1, y1)],
            "scale": round(s, 6), "upscaled": s > 1.0,
            "source_box_mapped_to_canvas": [round(v, 3) for v in box],
            "output": out_path.name, "output_sha256": sha256_file(out_path), "output_size": [canvas, canvas],
            "warnings": ([f"upscaled x{s:.2f}: detail is interpolated"] if s > 1.25 else []),
        }
    receipt = {
        "schema": "xexoria.turnaround_prep.receipt/1",
        "asset": asset,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "qa": {"verdict": verdict, "report": str(report_path), "report_sha256": sha256_file(report_path),
               "forced": forced, "round": round_no},
        "credit_guard": {
            "qa_gate": verdict,
            "forced": forced,
            "design_review": {"status": design_review, "by": reviewer,
                              "date": None if design_review == "PENDING" else _dt.date.today().isoformat()},
            "eligible_for_tripo": verdict == "PASS" and not forced and design_review == "PASS",
            "rule": "Only a QA-PASS set that also passed Claude's design review goes to Tripo; one job per asset "
                    "per round; record the job here; stop after 2 failed jobs and report.",
        },
        "transform": {
            "canvas_px": canvas, "fill_height": fill, "subject_height_px": round(ht, 2),
            "top_y": round(top, 2), "baseline_y": round(base_y, 2), "centre_x": canvas / 2.0,
            "background": "alpha (straight, un-mixed from the fitted background)" if keep_alpha else "flattened to #FFFFFF",
            "resample": "Pillow LANCZOS, sub-pixel box", "per_view_height_normalised": True,
        },
        "views": views_out,
        "tripo": {
            "upload_slots": {r: f"{r}.png" for r in ("front", "left", "back", "right")},
            "job_id": None, "model_version": None, "settings": None, "credits_quoted": None,
            "credits_spent": None, "result": None, "failed_jobs_this_asset": 0,
            "note": "Fill these after the owner runs the job (credit-guard rule).",
        },
    }
    rp = out_dir / "receipt.json"
    rp.write_text(json.dumps(_jsonable(receipt), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return receipt


# --------------------------------------------------------------------------- sheet splitting


def _gaps(profile: np.ndarray, min_len: int, thresh: float):
    """Interior runs where profile <= thresh, at least min_len long: [(start, end_exclusive)]."""
    low = profile <= thresh
    out = []
    n = len(profile)
    i = 0
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            if i > 0 and j < n and j - i >= min_len:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def split_panels(mask: np.ndarray, depth: int = 0, origin=(0, 0)) -> list:
    h, w = mask.shape
    if depth > 4 or not mask.any():
        return [(origin[0], origin[1], origin[0] + w, origin[1] + h)] if mask.any() else []
    col = mask.sum(0)
    row = mask.sum(1)
    gx = _gaps(col, max(3, int(0.01 * w)), max(0, int(0.002 * h)))
    gy = _gaps(row, max(3, int(0.01 * h)), max(0, int(0.002 * w)))
    if gx:
        cuts = [0] + [(a + b) // 2 for a, b in gx] + [w]
        out = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            out += split_panels(mask[:, a:b], depth + 1, (origin[0] + a, origin[1]))
        return out
    if gy:
        cuts = [0] + [(a + b) // 2 for a, b in gy] + [h]
        out = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            out += split_panels(mask[a:b], depth + 1, (origin[0], origin[1] + a))
        return out
    return [(origin[0], origin[1], origin[0] + w, origin[1] + h)]


def _split_sheet_into(inset: InputSet, src: Source, roles: list, cfg: dict):
    vd = segment("sheet", src, cfg)
    mask = vd.fg_raw
    side = max(mask.shape)
    mask = close_disk(open_disk(mask, max(1.0, 0.0015 * side)), max(1.0, 0.004 * side))
    boxes = split_panels(mask)
    areas = []
    for (x0, y0, x1, y1) in boxes:
        areas.append(int(mask[y0:y1, x0:x1].sum()))
    if not boxes:
        inset.notes.append(f"{src.label}: no subject found on the sheet.")
        return
    big = max(areas)
    panels = [(b, a) for b, a in zip(boxes, areas) if a >= 0.05 * big]
    dropped = len(boxes) - len(panels)
    # reading order: rows (by vertical centre), then left to right
    panels.sort(key=lambda p: ((p[0][1] + p[0][3]) / 2.0 // max(1, mask.shape[0] / 3.0), p[0][0]))
    inset.notes.append(f"{src.label}: sheet split into {len(panels)} panel(s)"
                       + (f" ({dropped} tiny region(s) such as labels ignored)" if dropped else "")
                       + f"; roles assigned in reading order: {', '.join(roles[:len(panels)])}.")
    for i, ((x0, y0, x1, y1), _a) in enumerate(panels):
        crop = (int(x0 / vd.sx), int(y0 / vd.sy), int(math.ceil(x1 / vd.sx)), int(math.ceil(y1 / vd.sy)))
        crop = (max(0, crop[0]), max(0, crop[1]), min(vd.size[0], crop[2]), min(vd.size[1], crop[3]))
        psrc = Source(label=f"{src.label}#panel{i + 1}", data=src.data, path=src.path, member=src.member,
                      crop=crop, sha256=src.sha256)
        inset.sheet_panels.append({"panel": i + 1, "crop_src": list(crop)})
        if i < len(roles):
            role = roles[i]
            if role == "skip":
                continue
            if role in ROLES:
                inset.views[role] = psrc
            elif role == "hero34":
                inset.hero34 = psrc
            elif role == "palette":
                inset.palette = psrc
        else:
            inset.unassigned.append(psrc)


# --------------------------------------------------------------------------- driver


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return round(float(o), 6) if math.isfinite(float(o)) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def analyse(inset: InputSet, cfg: dict, kind: str = "character", asymmetric: bool = False):
    vds: dict = {}
    for role in ROLES:
        if role in inset.views:
            vds[role] = segment(role, inset.views[role], cfg)
    heights = [vd.bbox[3] - vd.bbox[1] + 1 for vd in vds.values() if vd.bbox is not None]
    ref_h = float(np.median(heights)) if heights else None
    for vd in vds.values():
        measure_view(vd, cfg, ref_h)
    checks = run_checks(inset, vds, cfg, kind, asymmetric)
    statuses = [c["status"] for c in checks]
    verdict = "REGEN" if FAIL in statuses else "PASS"
    return vds, checks, verdict


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("input", nargs="?", help="folder, .zip, zip!member, or a single sheet image")
    ap.add_argument("--out", required=True, help="output folder for report.json, contact.png and regen_notes.md")
    ap.add_argument("--name", help="asset name for the reports (default: input name)")
    ap.add_argument("--config", help="JSON file overriding thresholds (deep-merged)")
    ap.add_argument("--view", action="append", default=[], help="explicit role=path (front/back/left/right/hero34/palette)")
    ap.add_argument("--order", help="roles for unnamed images in filename order, e.g. front,left,right,back,skip")
    ap.add_argument("--sheet-order", help="roles for sheet panels in reading order (default front,left,back,right)")
    ap.add_argument("--palette", help="palette.png path (overrides one found in the input)")
    ap.add_argument("--kind", choices=("character", "monster", "prop"), default="character")
    ap.add_argument("--require", help="required views, e.g. front for a single-image prop job (default from config)")
    ap.add_argument("--asymmetric", action="store_true", help="design is declared asymmetric (relaxes left/right FAIL to WARN)")
    ap.add_argument("--round", type=int, default=1, help="regen round number (max 3)")
    ap.add_argument("--prep", help="write Tripo-ready front/back/left/right PNGs + receipt.json here (PASS sets only)")
    ap.add_argument("--force", action="store_true", help="allow --prep on a REGEN set (receipt marks it not eligible)")
    ap.add_argument("--keep-alpha", action="store_true", help="prep: keep transparency instead of flattening to white")
    ap.add_argument("--design-review", choices=("PENDING", "PASS", "FAIL"), default="PENDING",
                    help="prep: Claude's design-review result; eligible_for_tripo needs QA PASS and design review PASS")
    ap.add_argument("--reviewer", help="prep: who did the design review")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    if not args.input and not args.view:
        ap.error("give an input path or --view role=path")
    cfg = load_config(args.config)
    if args.require:
        cfg["required_views"] = _parse_roles(args.require)
    inset = discover(args.input, args.view, args.order, args.sheet_order, args.palette, cfg)
    asset = args.name or (Path(args.input.split("!")[0]).stem if args.input else "turnaround")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    vds, checks, verdict = analyse(inset, cfg, args.kind, args.asymmetric)
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in (PASS, WARN, FAIL, SKIP)}
    report = {
        "schema": "xexoria.turnaround_qa.report/1",
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION, "python": platform.python_version(),
                 "numpy": np.__version__, "pillow": PIL.__version__},
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "asset": asset,
        "input": {"mode": inset.mode, "path": inset.path, "kind": args.kind, "asymmetric_declared": args.asymmetric,
                  "notes": inset.notes, "sheet_panels": inset.sheet_panels,
                  "palette": inset.palette.label if inset.palette else None,
                  "hero34": inset.hero34.label if inset.hero34 else None,
                  "unassigned": [{"source": s.label, "sha256": s.sha256} for s in inset.unassigned]},
        "verdict": verdict,
        "summary": counts,
        "views": {r: {"source": vd.source.label, "source_path": vd.source.path, "member": vd.source.member,
                      "crop": list(vd.source.crop) if vd.source.crop else None, "sha256": vd.source.sha256,
                      "mode": vd.mode, "alpha_used": vd.has_alpha, "background": vd.bg_stats,
                      "metrics": {k: v for k, v in vd.metrics.items() if k != "dominant"},
                      "dominant_colours": vd.metrics.get("dominant", [])}
                  for r, vd in vds.items() if not r.startswith("_")},
        "checks": checks,
        "config": cfg,
        "config_sha256": sha256_bytes(json.dumps(cfg, sort_keys=True).encode()),
        "outputs": {"contact": "contact.png", "regen_notes": "regen_notes.md"},
    }
    rpath = out / "report.json"
    rpath.write_text(json.dumps(_jsonable(report), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    view_vds = {k: v for k, v in vds.items()}
    make_contact(out / "contact.png", asset, verdict, checks, view_vds, inset, cfg)
    (out / "regen_notes.md").write_text(build_notes(asset, checks, vds, verdict, args.round, cfg, args.kind, inset),
                                        encoding="utf-8")
    if not args.quiet:
        print(f"{asset}: {verdict}  ({counts[FAIL]} FAIL, {counts[WARN]} WARN, {counts[PASS]} PASS, {counts[SKIP]} SKIP)")
        for status in (FAIL, WARN):
            grouped: dict = {}
            for c in checks:
                if c["status"] == status:
                    grouped.setdefault(c["id"], []).append(c)
            for cid, items in grouped.items():
                scopes = ",".join(c["scope"].replace("view:", "") for c in items)
                print(f"  {status:<4} {cid:<24} [{scopes}] {items[0]['detail']}")
        print(f"  -> {out}")
    if args.prep:
        if verdict != "PASS" and not args.force:
            print(f"prep skipped: verdict is {verdict} (use --force to override; the receipt will say not eligible)")
        else:
            receipt = prep_views(vds, Path(args.prep), cfg, args.keep_alpha, rpath, verdict, args.force, asset,
                                 args.round, args.design_review, args.reviewer)
            if not args.quiet:
                cg = receipt["credit_guard"]
                print(f"  prep -> {args.prep} (QA {cg['qa_gate']}, design review {cg['design_review']['status']}, "
                      f"eligible_for_tripo={cg['eligible_for_tripo']})")
    return 0 if verdict == "PASS" else 2


def main():
    try:
        sys.exit(run())
    except (FileNotFoundError, KeyError, ValueError, zipfile.BadZipFile, OSError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
