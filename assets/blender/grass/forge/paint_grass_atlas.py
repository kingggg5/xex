#!/usr/bin/env python3
"""Seeded procedural painter for the grass / flower / clover texture atlas `grass_atlas_v1`.

Everything is generated from the seed (default 20261002) with numpy / scipy / OpenCV / Pillow on the CPU:
no Blender (despite the folder name), no GPU, no source images, no third-party pixels. Seeded variation of
height, bend, hue and value comes from the generator; hand polish, if ever wanted, is a separate final layer.

Outputs (binding atlas contract, documented in the manifest, schema xexoria.grass-atlas/1):
  apps/client/src/assets/world/grass/grass_atlas_v1_albedo.png       2048 x 1024 RGBA8, sRGB, straight alpha, edge-bled
  apps/client/src/assets/world/grass/grass_atlas_v1_1024_albedo.png  1024 x 512, cell-wise 2x2, alpha x mip-1 coverage scale
  apps/client/src/assets/world/grass/grass_atlas_v1.json             cells, anchors, coverage scales, seed, params, hashes
Previews (labelled "FORGE PREVIEW (procedural, not a render)") and the self-review gate numbers:
  planning/evidence/grass-20261002/forge/*.png, forge-review.json

Layout: unit 256 px, 8 x 4 grid, image row 0 at the TOP (the runtime loads with invertY = false: v = y / 1024).
  rows 0-1  B0..B7  side-view grass bundles 256 x 512; roots on y 496..504 within +-26 px of x = 256c+128
  row 2     F0..F7  top-down flower heads centred at (256c+128, 640), inside r = 112
  row 3     G0..G7  clover leaves, plantain leaf, stems (tips_px), leafy base, white clover globe, reserved

Painting: 2x supersampled hard coverage per cell (per-cell canvases keep peak RAM well under 1 GB), 2x2 box
resolve to straight alpha (RGB = mean of the covered sub-samples, linear light), per-cell nearest-opaque edge
bleed + 5x5 box blur of the transparent texels, Castano mip-coverage scales per cell.

  python assets/blender/grass/forge/paint_grass_atlas.py [--seed N] [--out-dir DIR] [--no-previews]
         [--review-pass N --verify-determinism]
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import io
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
SCRIPT_REL = "assets/blender/grass/forge/paint_grass_atlas.py"
OUT_DIR = ROOT / "apps" / "client" / "src" / "assets" / "world" / "grass"
OUT_DIR_REL = "apps/client/src/assets/world/grass"
EVIDENCE_DIR = ROOT / "planning" / "evidence" / "grass-20261002" / "forge"
FULL_NAME = "grass_atlas_v1_albedo.png"
HALF_NAME = "grass_atlas_v1_1024_albedo.png"
JSON_NAME = "grass_atlas_v1.json"
REVIEW_NAME = "forge-review.json"
PREVIEW_LABEL = "FORGE PREVIEW (procedural, not a render)"

DEFAULT_SEED = 20261002
UNIT = 256
COLS, ROWS = 8, 4
ATLAS_W, ATLAS_H = UNIT * COLS, UNIT * ROWS
GUTTER = 8
SS = 2  # supersampling factor (hard coverage at 2x, 2x2 box resolve)
MIP_LEVELS = 5
HEAD_RADIUS_MAX = 112.0
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

# --------------------------------------------------------------------------------------------------
# Every tunable, as data (dumped verbatim into the manifest's generator.params)
# --------------------------------------------------------------------------------------------------
PARAMS = {
    "supersampling": SS,
    "clamp_srgb8": [0x1A, 0xF0],
    "light_top_down_xy": [-0.6, -0.8],
    "palettes": {
        "lush": {"root": "#2c4a28", "mid": "#4e7a34", "tip": "#9cbc58", "tip_front": "#a9c25e", "edge": "#c4d27a"},
        "dry": {"root": "#3a4a26", "mid": "#7a8a40", "tip": "#c2b062", "tip_front": "#c9b86a", "tip_straw": "#b9a95a",
                "edge": "#d6c98a"},
        "sedge": {"root": "#2e5444", "mid": "#4f7a5c", "tip": "#8fae7a", "tip_front": "#9ab880", "edge": "#b7cc9c"},
        "oat": {"head": "#cbb873", "shade": "#9e8a4e", "light": "#dccb8c", "stalk_root": "#4f6a32",
                "stalk_top": "#a9a062"},
    },
    "blade": {
        "taper_power": 0.85, "belly_t": 0.15, "belly_sigma": 0.10, "belly_amount": [0.06, 0.16],
        "root_pinch": 0.10, "s_curve_prob": 0.30, "s_curve_deg": [6.0, 15.0], "ctrl_k": [0.30, 0.42],
        "hue_jitter_deg": 6.0, "value_jitter": 0.08, "sat_jitter": 0.06,
        "mid_t": 0.40, "root_ease": 1.0, "tip_ease": 0.70, "streak_amount": 0.035,
        "fit_margin_px": 2.0,
    },
    "depth": {"back_fraction": 0.40, "back_value": 0.78, "back_hue_deg": 6.0,
              "front_fraction": 0.25, "front_value": 1.06, "front_tip_hue_deg": -5.0,
              "length_weight": 0.45},
    "form": {"lit_half": 1.08, "shade_half": 0.90, "fold_softness": 0.20, "rib_lift": 0.05, "rib_width": 0.16,
             "edge_highlight_px": 1.25, "edge_t": [0.35, 0.90], "edge_strength": 0.80,
             "fold_underside_value": 0.86, "fold_underside_hue_deg": 4.0},
    "occlusion": {"contact_sigma_px": 4.0, "contact_offset_px": 3.0, "contact_factor": 0.85,
                  "root_fraction": 0.14, "root_factor": 0.72,
                  "head_sigma_px": 2.5, "head_offset_px": [1.5, 2.5], "head_factor": 0.85},
    "macro": {"sigma_px": 22.0, "value": 0.04, "warmth": 0.03, "top_light": 0.06},
    "cells": {
        "B0": {"palette": "lush", "count": [7, 9], "base_width_px": [16, 26], "length_frac": [0.55, 0.95],
               "spread_deg": 40.0, "droop_deg": [10.0, 34.0], "curl_tips": 2, "curl_deg": [80.0, 115.0]},
        "B1": {"palette": "lush", "count": [6, 8], "base_width_px": [15, 26], "length_frac": [0.52, 0.92],
               "spread_deg": 36.0, "droop_deg": [6.0, 30.0], "s_curve_prob": 0.45, "folds": 1,
               "fold_t": [0.64, 0.78], "fold_deg": [120.0, 150.0], "fold_len": [0.85, 1.0]},
        "B2": {"palette": "lush", "count": [6, 8], "base_width_px": [16, 24], "length_frac": [0.70, 1.0],
               "spread_deg": 25.0, "droop_deg": [4.0, 20.0]},
        "B3": {"palette": "lush", "count": [7, 9], "base_width_px": [14, 22], "length_frac": [0.50, 0.90],
               "lean_deg": [10.0, 35.0], "droop_deg": [8.0, 26.0]},
        "B4": {"palette": "lush", "count": [5, 7], "base_width_px": [7, 11], "length_frac": [0.65, 0.95],
               "spread_deg": 30.0, "droop_deg": [6.0, 28.0], "stalks": [2, 3], "stalk_width_px": [3.0, 4.0],
               "stalk_length_frac": [0.82, 0.97], "spikelets": [5, 8], "spikelet_len_px": [13.0, 20.0],
               "spikelet_width_px": [5.0, 7.0], "pedicel_px": [4.0, 9.0], "seed_zone": 0.20},
        "B5": {"palette": "dry", "count": [6, 8], "base_width_px": [14, 22], "length_frac": [0.50, 0.90],
               "spread_deg": 36.0, "droop_deg": [6.0, 28.0], "broken_frac": 0.40, "break_t": [0.52, 0.80],
               "bend_deg": [110.0, 160.0], "cut_slope": [-0.9, 0.9]},
        "B6": {"palette": "sedge", "count": [6, 8], "base_width_px": [10, 14], "length_frac": [0.60, 0.95],
               "spread_deg": 18.0, "droop_deg": [0.0, 7.0], "s_curve_prob": 0.0, "lit_half": 1.11,
               "shade_half": 0.86, "rib_lift": 0.07},
        "B7": {"palette": "lush", "count": [12, 16], "base_width_px": [8, 12], "length_frac": [0.40, 0.80],
               "spread_deg": 34.0, "droop_deg": [6.0, 32.0]},
        "F0": {"petals": 5, "petal": "#e8c23a", "shade": "#b38a2a", "highlight": "#f6e488", "rim": "#f2d660",
               "petal_len_px": [94.0, 100.0], "petal_halfwidth_px": [40.0, 46.0], "centre": "#a9ae3c",
               "centre_light": "#cfc957", "stamen": "#f0cc42", "stamen_shade": "#b5952c", "centre_r_px": 17.0,
               "stamens": [14, 18]},
        "F1": {"petals": [16, 22], "petal": "#ece8d8", "shade": "#b8b6a6", "petal_len_px": [82.0, 100.0],
               "petal_halfwidth_px": [6.5, 8.5], "disc": "#e2b23a", "ring": "#b8862a", "disc_light": "#f0c858",
               "disc_dark": "#c08a28", "disc_r_px": [24.0, 27.0], "back_value": 0.86},
        "F2": {"petals": [4, 5], "petal": "#e8742a", "rim": "#f29a4a", "base": "#c4561e",
               "outer_len_px": [96.0, 101.0], "outer_halfwidth_px": [56.0, 63.0], "inner_len_px": [86.0, 94.0],
               "inner_halfwidth_px": [50.0, 56.0], "centre": "#3a2a1a", "centre_light": "#5a4a2e",
               "stamen": "#2e2216", "stamen_tip": "#6a5a38", "centre_r_px": 15.0},
        "F3": {"petals": 5, "base": "#c8323a", "petal": "#e0505a", "petal_len_px": [88.0, 95.0],
               "petal_halfwidth_px": [26.0, 30.0], "notch_depth": 0.24, "notch_width": 0.55, "ring": "#f2c8cc",
               "eye": "#8a2030"},
        "F4": {"flowers": [5, 7], "flower_r_px": [26.0, 34.0], "petal": "#6d8de0", "shade": "#4a62b0",
               "rim": "#8ea8ec", "ring": "#eeeadf", "eye": "#f2e2a0", "eye_dot": "#b89a50", "buds": [3, 5],
               "bud_colours": ["#d890b8", "#8a9ae0"], "cluster_r_px": 100.0},
        "F5": {"subclusters": [5, 8], "florets_total": [30, 60], "floret_r_px": [6.0, 10.0], "floret": "#f0eee2",
               "shade": "#b2b8a0", "centre": "#d8cfa0", "under": "#6e7c58", "under_light": "#8a9a70",
               "subcluster_r_px": [24.0, 32.0], "cluster_r_px": 100.0},
        "F6": {"radius_px": 70.0, "base": "#a24c74", "mid": "#d77a9f", "tip": "#eaa6c0", "under": "#8a3c62",
               "rings": [[0.42, 0.58, 26, 4.4], [0.30, 0.50, 20, 4.2], [0.18, 0.40, 13, 4.0], [0.05, 0.28, 7, 3.6]]},
        "F7": {"petals": 5, "petal": "#8a6ad0", "centre": "#c8b0f0", "vein": "#6c50b0", "tip": "#7a5cc0",
               "eye": "#f0e0a8", "petal_len_px": [80.0, 86.0], "petal_halfwidth_px": [24.0, 28.0]},
        "G0": {"leaflets": 3, "leaf": "#4f8a3a", "chevron": "#8fbf6a", "rim": "#2f5a26", "midrib": "#79a85a",
               "leaflet_len_px": [48.0, 56.0], "half_angle_deg": 58.0, "chevron_strength": 0.75,
               "notch": [0.14, 0.20], "value_var": 0.08},
        "G1": {"leaflets": 4, "leaf": "#3f7a32", "chevron": "#86b462", "rim": "#28501f", "midrib": "#6a9a4e",
               "leaflet_len_px": [48.0, 56.0], "half_angle_deg": 44.0, "chevron_strength": 0.38,
               "notch": [0.12, 0.18], "value_var": 0.08},
        "G2": {"leaf": "#5a8a3c", "vein": "#8db866", "groove": "#40682c", "rim": "#3a6228", "length_px": 208.0,
               "halfwidth_px": 45.0, "veins": 5},
        "G3": {"stems": [3, 5], "height_px": [160.0, 240.0], "width_px": [4.0, 6.0], "root": "#3e5e2a",
               "top": "#7aa048", "leaves_per_stem": [1, 2], "leaf_len_px": [26.0, 44.0], "leaf_width_px": [8.0, 12.0],
               "leaf_attach_t": [0.25, 0.70], "spread_deg": 20.0},
        "G4": {"stems": [2, 3], "height_px": [160.0, 240.0], "width_px": [4.0, 6.0], "root": "#3e5e2a",
               "top": "#7aa048", "base_leaves": [2, 4], "leaf_len_px": [60.0, 100.0], "leaf_width_px": [8.0, 12.0],
               "leaf_attach_t": [0.03, 0.22], "spread_deg": 16.0},
        "G5": {"leaves": [6, 9], "leaf_len_px": [60.0, 130.0], "leaf_width_px": [22.0, 34.0], "spread_deg": 74.0,
               "root": "#36582a", "mid": "#5a8a3a", "tip": "#86ae52", "midrib": "#9cbc6a", "edge": "#b4cc78"},
        "G6": {"radius_px": 60.0, "base": "#b9b498", "mid": "#e4e0d2", "tip": "#f2efe6", "under": "#9ea486",
               "pink": "#d8b4ae",
               "rings": [[0.42, 0.58, 22, 4.2], [0.30, 0.50, 17, 4.0], [0.18, 0.40, 11, 3.8], [0.05, 0.28, 6, 3.4]]},
    },
}

# Requested flower families share the existing procedural form painters.
PARAMS["cells"]["F3"] = {**PARAMS["cells"]["F2"], "petal": "#d94a51", "rim": "#ec7b78", "base": "#9f2938"}
PARAMS["cells"]["F4"] = {**PARAMS["cells"]["F1"], "petals": [24, 30], "petal": "#638ad8", "shade": "#354d96",
                        "petal_len_px": [74.0, 96.0], "petal_halfwidth_px": [5.0, 7.0], "disc": "#3a356b", "ring": "#635489",
                        "disc_light": "#897cb2", "disc_dark": "#29264f", "disc_r_px": [14.0, 17.0]}
PARAMS["cells"]["F7"] = {"petal": "#a987d2", "shade": "#624d8a", "tip": "#d0b7e5", "spikes": 3, "florets_per_spike": 8}

CELL_DEFS = [
    ("B0", "lush_fan_a", "bundle", "side"), ("B1", "lush_fan_b", "bundle", "side"),
    ("B2", "lush_tall", "bundle", "side"), ("B3", "combed", "bundle", "side"),
    ("B4", "wispy_seed", "bundle", "side"), ("B5", "dry_broken", "bundle", "side"),
    ("B6", "sedge", "bundle", "side"), ("B7", "fine_dense", "bundle", "side"),
    ("F0", "yellow_buttercup", "head", "top"), ("F1", "white_daisy", "head", "top"),
    ("F2", "orange_poppy", "head", "top"), ("F3", "red_poppy", "head", "top"),
    ("F4", "blue_cornflower", "head", "top"), ("F5", "white_yarrow", "head", "top"),
    ("F6", "pink_clover_head", "head", "top"), ("F7", "lavender_sprigs", "head", "top"),
    ("G0", "clover_leaf_a", "leaf", "top"), ("G1", "clover_leaf_b", "leaf", "top"),
    ("G2", "round_leaf", "leaf", "top"), ("G3", "stems_a", "stems", "side"),
    ("G4", "stems_b", "stems", "side"), ("G5", "leafy_base", "leaf", "side"),
    ("G6", "clover_flower_white", "head", "top"), ("G7", "reserved", "reserved", "none"),
]


# --------------------------------------------------------------------------------------------------
# Small helpers: colour, maths
# --------------------------------------------------------------------------------------------------
def hexc(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def to_hex(rgb) -> str:
    c = np.clip(np.round(np.asarray(rgb, np.float64) * 255.0), 0, 255).astype(int)
    return "#%02x%02x%02x" % (c[0], c[1], c[2])


def srgb_to_linear(c):
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055).astype(np.float32)


def hsv_adjust(rgb, dh_deg=0.0, s_mul=1.0, v_mul=1.0) -> np.ndarray:
    r, g, b = [float(x) for x in np.clip(rgb, 0.0, 1.0)]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + dh_deg / 360.0) % 1.0
    s = min(1.0, max(0.0, s * s_mul))
    v = min(1.0, max(0.0, v * v_mul))
    return np.array(colorsys.hsv_to_rgb(h, s, v), np.float32)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, w):
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    w = np.asarray(w, np.float32)
    if w.ndim == 1:
        w = w[:, None]
    return a + (b - a) * w


def rng_for(seed: int, *keys: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([int(seed)] + [int(k) for k in keys]))


def dvec(theta: float) -> np.ndarray:
    """Unit direction for an angle measured from vertical-up, positive toward +x (image y grows down)."""
    return np.array([math.sin(theta), -math.cos(theta)])


def poly_len(p: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def resample(p: np.ndarray, step: float) -> np.ndarray:
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(3, int(math.ceil(s[-1] / step)) + 1)
    u = np.linspace(0.0, s[-1], n)
    return np.stack([np.interp(u, s, p[:, 0]), np.interp(u, s, p[:, 1])], axis=1)


def bezier3(p0, p1, p2, p3, n=400) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)[:, None]
    mt = 1.0 - t
    return mt ** 3 * p0 + 3 * mt ** 2 * t * p1 + 3 * mt * t ** 2 * p2 + t ** 3 * p3


def bezier2(p0, p1, p2, n=200) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def smooth_noise(shape, sigma, rng) -> np.ndarray:
    n = ndimage.gaussian_filter(rng.standard_normal(shape).astype(np.float32), sigma, mode="reflect")
    n -= n.mean()
    return n / max(1e-6, float(n.std()))


def light_dir() -> np.ndarray:
    v = np.array(PARAMS["light_top_down_xy"], np.float64)
    return v / np.linalg.norm(v)


# CIE Lab / CIEDE2000 (Sharma, Wu & Dalal 2005) for the palette gate
def srgb_to_lab(rgb) -> np.ndarray:
    lin = srgb_to_linear(np.asarray(rgb, np.float32)).astype(np.float64)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def ciede2000(lab1, lab2) -> float:
    L1, a1, b1 = [float(x) for x in lab1]
    L2, a2, b2 = [float(x) for x in lab2]
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cb = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(cb ** 7 / (cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0
    dLp, dCp = L2 - L1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    Lbp, cbp = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-((hbp - 275) / 25) ** 2)
    rc = 2 * math.sqrt(cbp ** 7 / (cbp ** 7 + 25.0 ** 7))
    sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    sc = 1 + 0.045 * cbp
    sh = 1 + 0.015 * cbp * t
    rt = -math.sin(math.radians(2 * dtheta)) * rc
    return math.sqrt((dLp / sl) ** 2 + (dCp / sc) ** 2 + (dHp / sh) ** 2 + rt * (dCp / sc) * (dHp / sh))


# --------------------------------------------------------------------------------------------------
# Cell geometry
# --------------------------------------------------------------------------------------------------
def cell_rect(cid: str):
    c = int(cid[1])
    if cid[0] == "B":
        return [UNIT * c, 0, UNIT, 2 * UNIT]
    if cid[0] == "F":
        return [UNIT * c, 2 * UNIT, UNIT, UNIT]
    return [UNIT * c, 3 * UNIT, UNIT, UNIT]


def cell_local_content(cid: str, view: str):
    """Nominal content box (local px, x0 y0 x1 y1) and whether a r=112 circle clip applies."""
    if cid[0] == "B":
        return (8, 8, 248, 504), False
    if view == "top":
        return (16, 16, 240, 240), True
    return (8, 8, 248, 248), False


def cell_local_anchor(cid: str, view: str):
    if cid[0] == "B":
        return (128.0, 504.0)
    if view == "side":
        return (128.0, 248.0)
    return (128.0, 128.0)


class Fields:
    """Per-pixel fields of one painted shape (SS px). ys/xs are canvas coordinates of covered pixels."""
    pass


class Canvas:
    def __init__(self, w_px: int, h_px: int, clip_px):
        self.w, self.h = w_px * SS, h_px * SS
        self.rgb = np.zeros((self.h, self.w, 3), np.float32)
        self.cov = np.zeros((self.h, self.w), np.float32)
        self.clip = tuple(int(round(v * SS)) for v in clip_px)

    def occlude(self, f: Fields, sigma_px: float, dx_px: float, dy_px: float, factor: float):
        """Darken what is already painted under a blurred, offset copy of the new shape's mask."""
        sig = sigma_px * SS
        dx, dy = int(round(dx_px * SS)), int(round(dy_px * SS))
        pad = int(math.ceil(3 * sig)) + max(abs(dx), abs(dy)) + 1
        y0, x0 = max(0, int(f.ys.min()) - pad), max(0, int(f.xs.min()) - pad)
        y1, x1 = min(self.h, int(f.ys.max()) + pad + 1), min(self.w, int(f.xs.max()) + pad + 1)
        m = np.zeros((y1 - y0, x1 - x0), np.float32)
        yy, xx = f.ys - y0 + dy, f.xs - x0 + dx
        ok = (yy >= 0) & (yy < m.shape[0]) & (xx >= 0) & (xx < m.shape[1])
        m[yy[ok], xx[ok]] = 1.0
        b = ndimage.gaussian_filter(m, sig, mode="constant", truncate=3.0)
        self.rgb[y0:y1, x0:x1] *= (1.0 - (1.0 - factor) * b)[..., None]

    def put(self, f: Fields, rgb):
        self.rgb[f.ys, f.xs] = np.clip(rgb, 0.0, 1.0)
        self.cov[f.ys, f.xs] = 1.0


def _finish_fields(cand_shape, cy, cx, inside, x0, y0) -> Fields:
    mask = np.zeros(cand_shape, np.uint8)
    mask[cy[inside], cx[inside]] = 1
    dist = cv2.distanceTransform(np.pad(mask, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    f = Fields()
    f.ys = (cy[inside] + y0).astype(np.int64)
    f.xs = (cx[inside] + x0).astype(np.int64)
    f.edge = dist[cy[inside], cx[inside]].astype(np.float32)
    f.n = int(inside.sum())
    return f


def ribbon(cv: Canvas, spine_px: np.ndarray, hw_px: np.ndarray, cut=None):
    """Hard-coverage ribbon along a polyline spine (final px) with per-sample half widths (final px).

    Returns per-pixel t (arc-length fraction 0 root .. 1 tip), d (signed lateral offset, +normal = right of the
    direction of travel rotated +90 deg in image space), s = d / halfwidth, edge (distance to the silhouette)."""
    P = np.asarray(spine_px, np.float64) * SS
    hw = np.asarray(hw_px, np.float64) * SS
    n = len(P)
    if n < 3:
        return None
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.stack([-T[:, 1], T[:, 0]], axis=1)
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    total = arc[-1]
    m = hw.max() + 3.0
    x0 = max(cv.clip[0], int(math.floor(P[:, 0].min() - m)))
    x1 = min(cv.clip[2], int(math.ceil(P[:, 0].max() + m)))
    y0 = max(cv.clip[1], int(math.floor(P[:, 1].min() - m)))
    y1 = min(cv.clip[3], int(math.ceil(P[:, 1].max() + m)))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    cand = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for i in range(0, n - 1, 10):
        j = min(n, i + 11)
        th = int(math.ceil(2 * hw[i:j].max() + 5))
        pts = np.round((P[i:j] - [x0 + 0.5, y0 + 0.5]) * 4).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(cand, [pts], False, 1, thickness=th, lineType=cv2.LINE_8, shift=2)
    cy, cx = np.nonzero(cand)
    if len(cy) == 0:
        return None
    q = np.stack([cx + x0 + 0.5, cy + y0 + 0.5], axis=1)
    _, idx = cKDTree(P).query(q)
    rel = q - P[idx]
    along = np.einsum("ij,ij->i", rel, T[idx])
    d = np.einsum("ij,ij->i", rel, N[idx])
    sa = np.clip(arc[idx] + along, 0.0, total)
    hw_t = np.interp(sa, arc, hw)
    inside = np.abs(d) <= hw_t
    inside &= ~((idx == 0) & (along < 0))
    inside &= ~((idx == n - 1) & (along > 0))
    if cut is not None:
        inside &= cut(q, d)
    if not inside.any():
        return None
    f = _finish_fields(cand.shape, cy, cx, inside, x0, y0)
    f.t = (sa[inside] / total).astype(np.float32)
    f.d = d[inside].astype(np.float32)
    f.hw = hw_t[inside].astype(np.float32)
    f.s = (f.d / np.maximum(f.hw, 1e-6)).astype(np.float32)
    return f


def axis_shape(cv: Canvas, base_px, phi: float, length_px: float, hwmax_px: float, prof, extra=None,
               bend_px: float = 0.0, asym: float = 0.0):
    """Shape around a straight axis from `base` (final px) at image angle `phi` (0 = +x, y down).

    Inside: 0 <= u <= 1 and |v| <= hwmax * prof(u), u = along / length, v = lateral offset (optionally bent by
    bend_px * sin(pi u)); asym scales the two sides (+asym widens the +v side)."""
    b = np.asarray(base_px, np.float64) * SS
    L = length_px * SS
    hwm = hwmax_px * SS
    a = np.array([math.cos(phi), math.sin(phi)])
    nrm = np.array([-a[1], a[0]])
    reach = hwm * (1 + abs(asym)) + abs(bend_px) * SS + 3
    corners = np.array([b + nrm * reach, b - nrm * reach, b + a * L + nrm * reach, b + a * L - nrm * reach,
                        b - a * 3 + nrm * reach, b - a * 3 - nrm * reach])
    x0 = max(cv.clip[0], int(math.floor(corners[:, 0].min())))
    x1 = min(cv.clip[2], int(math.ceil(corners[:, 0].max())) + 1)
    y0 = max(cv.clip[1], int(math.floor(corners[:, 1].min())))
    y1 = min(cv.clip[3], int(math.ceil(corners[:, 1].max())) + 1)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    gy, gx = np.mgrid[y0:y1, x0:x1]
    qx = gx.ravel() + 0.5 - b[0]
    qy = gy.ravel() + 0.5 - b[1]
    u = (qx * a[0] + qy * a[1]) / L
    v = qx * nrm[0] + qy * nrm[1]
    uc = np.clip(u, 0.0, 1.0)
    v = v - bend_px * SS * np.sin(np.pi * uc)
    hw = hwm * prof(uc) * (1.0 + asym * np.sign(v))
    inside = (u >= 0) & (u <= 1) & (np.abs(v) <= hw)
    if extra is not None:
        inside &= extra(u, v, hw)
    if not inside.any():
        return None
    cy = (gy.ravel() - y0)
    cx = (gx.ravel() - x0)
    f = _finish_fields((y1 - y0, x1 - x0), cy, cx, inside, x0, y0)
    f.u = u[inside].astype(np.float32)
    f.v = v[inside].astype(np.float32)
    f.hw = hw[inside].astype(np.float32)
    f.vn = (f.v / np.maximum(f.hw, 1e-6)).astype(np.float32)
    f.px = (gx.ravel()[inside] + 0.5).astype(np.float32)
    f.py = (gy.ravel()[inside] + 0.5).astype(np.float32)
    return f


def polar_shape(cv: Canvas, centre_px, rmax_px: float, inside_fn):
    """Shape defined in polar coordinates around `centre` (final px): inside_fn(rho_px_final, theta) -> bool."""
    c = np.asarray(centre_px, np.float64) * SS
    r = rmax_px * SS + 3
    x0, x1 = max(cv.clip[0], int(math.floor(c[0] - r))), min(cv.clip[2], int(math.ceil(c[0] + r)) + 1)
    y0, y1 = max(cv.clip[1], int(math.floor(c[1] - r))), min(cv.clip[3], int(math.ceil(c[1] + r)) + 1)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    gy, gx = np.mgrid[y0:y1, x0:x1]
    dx = (gx.ravel() + 0.5 - c[0]) / SS
    dy = (gy.ravel() + 0.5 - c[1]) / SS
    rho = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)
    inside = inside_fn(rho, th)
    if not inside.any():
        return None
    f = _finish_fields((y1 - y0, x1 - x0), gy.ravel() - y0, gx.ravel() - x0, inside, x0, y0)
    f.rho = rho[inside].astype(np.float32)
    f.th = th[inside].astype(np.float32)
    f.dx = dx[inside].astype(np.float32)
    f.dy = dy[inside].astype(np.float32)
    return f


def disc(cv: Canvas, centre_px, r_px: float):
    return polar_shape(cv, centre_px, r_px, lambda rho, th: rho <= r_px)


def head_occlude(cv: Canvas, f: Fields, strength: float = 1.0):
    o = PARAMS["occlusion"]
    fac = 1.0 - (1.0 - o["head_factor"]) * strength
    cv.occlude(f, o["head_sigma_px"], o["head_offset_px"][0], o["head_offset_px"][1], fac)


def dome_light(dx, dy, r, amount=0.18):
    """Value multiplier for a small dome lit from the upper-left (top-down view)."""
    lx, ly = light_dir()
    nx, ny = dx / max(r, 1e-6), dy / max(r, 1e-6)
    return 1.0 + amount * np.clip(nx * lx + ny * ly, -1.0, 1.0)


# --------------------------------------------------------------------------------------------------
# Width profiles (u or t in [0, 1] -> relative half width in [0, 1])
# --------------------------------------------------------------------------------------------------
def prof_obovate(umax=0.6, base=0.16, p=0.7, cap=1.0):
    def f(u):
        rise = base + (1 - base) * np.sin(0.5 * np.pi * np.clip(u / umax, 0, 1)) ** p
        capv = np.sqrt(np.clip(1 - ((u - umax) / (1 - umax)) ** 2, 0, 1)) ** cap
        return np.where(u <= umax, rise, capv)
    return f


def prof_strap(base=0.55, rise=0.18, ucap=0.86):
    def f(u):
        w = base + (1 - base) * smoothstep(0.0, rise, u)
        capv = np.sqrt(np.clip(1 - ((u - ucap) / (1 - ucap)) ** 2, 0, 1))
        return np.where(u <= ucap, w, capv)
    return f


def prof_lance(p=0.72, q=0.85, join=0.22):
    def f(u):
        w = np.sin(np.pi * np.clip(u, 0, 1) ** p) ** q
        return np.maximum(w, join * (1 - smoothstep(0.0, 0.25, u)))
    return f


def prof_floret(ucap=0.80):
    def f(u):
        w = 0.55 + 0.45 * np.clip(u, 0, 1) ** 0.6
        capv = np.sqrt(np.clip(1 - ((u - ucap) / (1 - ucap)) ** 2, 0, 1))
        return np.where(u <= ucap, w, capv)
    return f


def blade_halfwidth(t, w0, belly):
    b = PARAMS["blade"]
    hw = 0.5 * w0 * np.clip(1 - t, 0, 1) ** b["taper_power"]
    hw = hw * (1 + belly * np.exp(-((t - b["belly_t"]) / b["belly_sigma"]) ** 2))
    return hw * (1 - b["root_pinch"] * (1 - smoothstep(0.0, 0.06, t)))


def leaf_halfwidth(t, wmax, pet=0.12, widest=0.45, pet_w=0.16):
    rise = pet_w + (1 - pet_w) * np.sin(0.5 * np.pi * np.clip((t - pet) / (widest - pet), 0, 1))
    fall = np.clip((1 - t) / (1 - widest), 0, 1) ** 0.8
    w = np.where(t < pet, pet_w, np.where(t < widest, rise, fall))
    return 0.5 * wmax * w


def lanceolate_halfwidth(t, wmax):
    return 0.5 * wmax * np.sin(np.pi * np.clip(t, 0, 1) ** 0.6) ** 0.9


# --------------------------------------------------------------------------------------------------
# Grass bundles (B cells, side view)
# --------------------------------------------------------------------------------------------------
B_CONTENT = (8.0, 8.0, 248.0, 504.0)


def blade_bezier(root, L, th_c, d0, d1, k1, k2) -> np.ndarray:
    root = np.asarray(root, np.float64)

    def build(chord):
        p3 = root + chord * dvec(th_c)
        p1 = root + k1 * chord * dvec(th_c + d0)
        p2 = p3 - k2 * chord * dvec(th_c + d1)
        return bezier3(root, p1, p2, p3, 400)

    arc = poly_len(build(1.0))
    return resample(build(L / arc), 0.5)


def spine_tangent_angle(sp: np.ndarray, i: int) -> float:
    j0, j1 = max(0, i - 4), min(len(sp) - 1, i + 4)
    v = sp[j1] - sp[j0]
    return math.atan2(v[0], -v[1])


def fold_spine(sp: np.ndarray, t_f: float, angle: float, rel_len: float) -> np.ndarray:
    """Keep the spine up to arc fraction t_f, then add a short segment turned by `angle` (a fold / bend)."""
    k = max(4, int(round(t_f * (len(sp) - 1))))
    head = sp[:k + 1]
    total = poly_len(sp)
    rest = max(6.0, (1 - t_f) * total * rel_len)
    a0 = spine_tangent_angle(sp, k)
    q0 = head[-1]
    q1 = q0 + 0.30 * rest * dvec(a0 + angle * 0.85)
    q2 = q1 + 0.70 * rest * dvec(a0 + angle * 1.0)
    seg = resample(bezier2(q0, q1, q2, 120), 0.5)
    return np.concatenate([head, seg[1:]], axis=0)


def spine_outline_box(sp: np.ndarray, hw: np.ndarray):
    T = np.gradient(sp, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.stack([-T[:, 1], T[:, 0]], axis=1)
    pts = np.concatenate([sp + N * hw[:, None], sp - N * hw[:, None]], axis=0)
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


def fits_box(sp, hw, margin, extra_top=0.0, extra_side=0.0):
    x0, y0, x1, _ = spine_outline_box(sp, hw)
    return (x0 >= B_CONTENT[0] + margin + extra_side and x1 <= B_CONTENT[2] - margin - extra_side
            and y0 >= B_CONTENT[1] + margin + extra_top)


def blade_palette(pal: dict, rng, depth: str, cell_rec: dict):
    b, dp = PARAMS["blade"], PARAMS["depth"]
    dh = rng.uniform(-b["hue_jitter_deg"], b["hue_jitter_deg"])
    dv = 1.0 + rng.uniform(-b["value_jitter"], b["value_jitter"])
    ds = 1.0 + rng.uniform(-b["sat_jitter"], b["sat_jitter"])
    root, mid, tip, edge = hexc(pal["root"]), hexc(pal["mid"]), hexc(pal["tip"]), hexc(pal["edge"])
    tip_dh = 0.0
    if depth == "back":
        dv *= dp["back_value"]
        dh += dp["back_hue_deg"]
    elif depth == "front":
        dv *= dp["front_value"]
        tip = hexc(pal.get("tip_front", pal["tip"]))
        tip_dh = dp["front_tip_hue_deg"]
    return {"root": hsv_adjust(root, dh, ds, dv), "mid": hsv_adjust(mid, dh, ds, dv),
            "tip": hsv_adjust(tip, dh + tip_dh, ds, dv), "edge": hsv_adjust(edge, dh + tip_dh, 1.0, dv)}


def gradient3(t, c0, c1, c2):
    b = PARAMS["blade"]
    mt = b["mid_t"]
    lo = smoothstep(0.0, mt, t) ** b["root_ease"]
    hi = np.clip((t - mt) / (1 - mt), 0, 1) ** b["tip_ease"]
    col_lo = mix(c0, c1, lo)
    col_hi = mix(c1, c2, hi)
    return np.where((t <= mt)[:, None], col_lo, col_hi)


def streak(rng, t, s):
    g = smooth_noise((48, 7), (2.0, 0.9), rng)
    return ndimage.map_coordinates(g, [np.clip(t, 0, 1) * 47, (np.clip(s, -1, 1) + 1) * 0.5 * 6], order=1,
                                   mode="nearest").astype(np.float32)


def plan_bundle(rng, cid: str, R: dict) -> list:
    """Lay out the blades of one bundle: a partial fan rooted within +-26 px of the cell centre."""
    bp = PARAMS["blade"]
    H = B_CONTENT[3] - B_CONTENT[1]
    n = int(rng.integers(R["count"][0], R["count"][1] + 1))
    combed = "lean_deg" in R
    q = np.clip((np.arange(n) + 0.5) / n + rng.uniform(-0.35, 0.35, n) / n, 0.0, 1.0)
    p = q * 2 - 1
    if combed:
        lo, hi = (math.radians(v) for v in R["lean_deg"])
        th_target = lo + (hi - lo) * q
        key = q + rng.uniform(0, 0.30, n)
        root_x = 128 + np.clip(-12 + p * 12 + rng.normal(0, 3, n), -26, 26)
    else:
        th_target = p * math.radians(R["spread_deg"]) * rng.uniform(0.85, 1.0, n)
        key = np.abs(p) + rng.uniform(0, 0.35, n)
        root_x = 128 + np.clip(p * 18 + rng.normal(0, 4, n), -26, 26)
    lengths = np.sort(rng.uniform(R["length_frac"][0], R["length_frac"][1], n))[::-1] * H
    L = np.empty(n)
    L[np.argsort(key, kind="stable")] = lengths
    root_y = 504.0 - rng.uniform(0.0, 4.0, n)
    widths = rng.uniform(R["base_width_px"][0], R["base_width_px"][1], n)
    s_prob = R.get("s_curve_prob", bp["s_curve_prob"])
    kinds = ["normal"] * n
    # specials
    if R.get("curl_tips"):
        cand = [i for i in np.argsort(-np.abs(p) + rng.uniform(0, 0.3, n)) if abs(p[i]) >= 0.3]
        for i in cand[:R["curl_tips"]]:
            kinds[i] = "curl"
    if R.get("folds"):
        cand = [i for i in rng.permutation(n) if 0.15 <= abs(p[i]) <= 0.85 and kinds[i] == "normal"]
        for i in cand[:R["folds"]]:
            kinds[i] = "fold"
    if R.get("broken_frac"):
        k = max(2, int(round(R["broken_frac"] * n)))
        idx = list(rng.permutation(n))[:k]
        for j, i in enumerate(idx):
            kinds[i] = "bent" if j % 2 == 0 else "snapped"
    blades = []
    margin = bp["fit_margin_px"]
    for i in range(n):
        lean_dir = 1.0 if (th_target[i] > 0 or combed) else -1.0
        if abs(p[i]) < 0.12 and not combed:
            lean_dir = 1.0 if rng.random() < 0.5 else -1.0
        droop = math.radians(rng.uniform(*R["droop_deg"])) * (0.5 + 0.5 * abs(p[i]))
        k1, k2 = rng.uniform(*bp["ctrl_k"]), rng.uniform(*bp["ctrl_k"])
        shape = "c"
        if kinds[i] == "curl":
            d0 = -lean_dir * math.radians(rng.uniform(4, 10))
            d1 = lean_dir * math.radians(rng.uniform(*R["curl_deg"]))
            k2 = rng.uniform(0.45, 0.55)
            shape = "curl"
        elif kinds[i] == "normal" and rng.random() < s_prob:
            sgn = 1.0 if rng.random() < 0.5 else -1.0
            d0 = sgn * math.radians(rng.uniform(*bp["s_curve_deg"]))
            d1 = sgn * math.radians(rng.uniform(*bp["s_curve_deg"])) + lean_dir * droop * 0.5
            shape = "s"
        else:
            d0 = -lean_dir * droop * rng.uniform(0.15, 0.45)
            d1 = lean_dir * droop
        belly = rng.uniform(*bp["belly_amount"])
        th_c, Li = float(th_target[i]), float(L[i])
        bias = math.radians(R["lean_deg"][0]) if combed else 0.0
        t_f = fold_ang = fold_len = None
        if kinds[i] == "fold":
            t_f = rng.uniform(*R["fold_t"])
            fold_ang = lean_dir * math.radians(rng.uniform(*R["fold_deg"]))
            fold_len = rng.uniform(*R["fold_len"])
        elif kinds[i] == "bent":
            t_f = rng.uniform(*R["break_t"])
            fold_ang = lean_dir * math.radians(rng.uniform(*R["bend_deg"]))
            fold_len = rng.uniform(0.75, 1.0)
        t_cut = rng.uniform(*R["break_t"]) if kinds[i] == "snapped" else None
        sp = hw = None
        for attempt in range(80):
            sp = blade_bezier((root_x[i], root_y[i]), Li, th_c, d0, d1, k1, k2)
            if t_f is not None:
                sp = fold_spine(sp, t_f, fold_ang, fold_len)
            if t_cut is not None:
                k = int(round(t_cut * (len(sp) - 1)))
                t_full = np.linspace(0, 1, len(sp))
                sp_c = sp[:k + 1]
                hw = blade_halfwidth(t_full[:k + 1], widths[i], belly)
            else:
                sp_c = sp
                hw = blade_halfwidth(np.linspace(0, 1, len(sp_c)), widths[i], belly)
            if fits_box(sp_c, hw, margin):
                sp = sp_c
                break
            if attempt % 3 != 2:
                th_c = bias + (th_c - bias) * 0.88
            else:
                Li *= 0.965
        else:
            sp = sp_c
        tip = sp[-1]
        chord = tip - sp[0]
        blades.append({
            "i": i, "kind": kinds[i], "shape": shape, "spine": sp, "hw": hw, "width": float(widths[i]),
            "length": float(poly_len(sp)), "length_nominal": float(Li), "theta_c": th_c, "lean_dir": lean_dir,
            "chord_deg": math.degrees(math.atan2(chord[0], -chord[1])), "tip": tip, "t_fold": t_f,
            "t_cut": t_cut, "cut_slope": rng.uniform(*R["cut_slope"]) if t_cut is not None else 0.0,
            "jag_phase": rng.uniform(0, 2 * math.pi),
        })
    return blades


def plan_stalks(rng, R: dict) -> list:
    """Thin oat-like seed stalks with spikelets hanging in the top `seed_zone` of the stalk."""
    H = B_CONTENT[3] - B_CONTENT[1]
    n = int(rng.integers(R["stalks"][0], R["stalks"][1] + 1))
    out = []
    slots = np.linspace(-0.6, 0.6, n) + rng.uniform(-0.15, 0.15, n)
    for j in range(n):
        lean_dir = 1.0 if slots[j] >= 0 else -1.0
        th_c = math.radians(slots[j] * 18.0)
        L = rng.uniform(*R["stalk_length_frac"]) * H
        d0 = -lean_dir * math.radians(rng.uniform(2, 6))
        d1 = lean_dir * math.radians(rng.uniform(8, 22))
        root = (128 + slots[j] * 14 + rng.normal(0, 3), 504.0 - rng.uniform(0, 3))
        w = rng.uniform(*R["stalk_width_px"])
        for attempt in range(80):
            sp = blade_bezier(root, L, th_c, d0, d1, 0.36, 0.36)
            hw = 0.5 * w * (1 - 0.35 * np.linspace(0, 1, len(sp)))
            if fits_box(sp, hw, 2.0, extra_top=12.0, extra_side=22.0):
                break
            if attempt % 3 != 2:
                th_c *= 0.88
            else:
                L *= 0.965
        # spikelets
        k = int(rng.integers(R["spikelets"][0], R["spikelets"][1] + 1))
        ts = np.sort(1.0 - R["seed_zone"] + R["seed_zone"] * ((np.arange(k) + rng.uniform(0.2, 0.8, k)) / k))
        spk = []
        for m, tt in enumerate(ts):
            side = 1.0 if m % 2 == 0 else -1.0
            idx = min(len(sp) - 1, int(round(tt * (len(sp) - 1))))
            a_st = spine_tangent_angle(sp, idx)
            at = sp[idx]
            if m == k - 1:  # terminal spikelet nods over the stalk tip
                at = sp[-1]
                side = lean_dir
                ped_a = a_st + side * math.radians(rng.uniform(20, 40))
            else:
                ped_a = a_st + side * math.radians(rng.uniform(35, 70))
            ped_len = rng.uniform(*R["pedicel_px"])
            ped = resample(np.array([at, at + ped_len * dvec(ped_a)]), 0.5)
            hang = ped_a + side * math.radians(rng.uniform(45, 85))
            hang = float(np.clip(hang, -math.radians(165), math.radians(165)))
            sl = rng.uniform(*R["spikelet_len_px"])
            s0 = ped[-1]
            s1 = s0 + 0.5 * sl * dvec(ped_a + side * math.radians(20))
            s2 = s0 + sl * dvec(hang)
            body = resample(bezier2(s0, s1, s2, 60), 0.5)
            spk.append({"pedicel": ped, "body": body, "width": rng.uniform(*R["spikelet_width_px"]), "side": side})
        out.append({"spine": sp, "hw": hw, "spikelets": spk, "lean_dir": lean_dir, "tip": sp[-1]})
    return out


def shade_blade(f: Fields, cols: dict, lit_sign: float, rng, rec: dict, t_fold=None, straw=None):
    fm = PARAMS["form"]
    lit_half = rec.get("lit_half", fm["lit_half"])
    shade_half = rec.get("shade_half", fm["shade_half"])
    rib_lift = rec.get("rib_lift", fm["rib_lift"])
    t, s = f.t, f.s
    col = gradient3(t, cols["root"], cols["mid"], cols["tip"])
    if straw is not None:  # snapped dry blade: straw-coloured broken end
        t_end = float(t.max())
        col = mix(col, straw, 0.85 * smoothstep(t_end - 0.12, t_end, t))
    lit = lit_sign * s
    form = shade_half + (lit_half - shade_half) * smoothstep(-fm["fold_softness"], fm["fold_softness"], lit)
    rib = 1.0 + rib_lift * np.exp(-(s / fm["rib_width"]) ** 2)
    stk = 1.0 + PARAMS["blade"]["streak_amount"] * streak(rng, t, s)
    col = col * (form * rib * stk)[:, None]
    e0, e1 = fm["edge_t"]
    wt = smoothstep(e0 - 0.04, e0 + 0.03, t) * (1 - smoothstep(e1 - 0.04, e1 + 0.03, t))
    band = np.clip(fm["edge_highlight_px"] * SS + 0.5 - f.edge, 0, 1) * (lit > 0.2)
    if t_fold is not None:
        under = t > t_fold
        wt = wt * (~under)
        col[under] = col[under] * fm["fold_underside_value"]
        col[under] = col[under] * np.array([0.97, 1.0, 1.04], np.float32)
        crease = np.exp(-((t - t_fold) / 0.012) ** 2) * 0.35
        col = mix(col, cols["edge"], crease)
    col = mix(col, cols["edge"], fm["edge_strength"] * wt * band)
    return col


def paint_blade(cv: Canvas, b: dict, cols: dict, rng, rec: dict, pal: dict):
    o = PARAMS["occlusion"]
    cut = None
    if b["t_cut"] is not None:
        sp = b["spine"]
        end = sp[-1] * SS
        a = spine_tangent_angle(sp, len(sp) - 1)
        tvec = dvec(a)
        slope = b["cut_slope"]
        jag_amp = 1.6 * SS
        ph = b["jag_phase"]

        def cut(q, d, end=end, tvec=tvec, slope=slope, jag_amp=jag_amp, ph=ph):
            along_end = (q - end) @ tvec
            jag = jag_amp * np.abs(np.sin(d / (2.2 * SS) + ph))
            return along_end + slope * d + jag <= 0.0
        # extend the spine a little so a slanted cut has material on its long side
        ext = abs(slope) * b["hw"][-1] + 3.0
        sp_ext = np.concatenate([sp, resample(np.array([sp[-1], sp[-1] + ext * tvec]), 0.5)[1:]], axis=0)
        hw_ext = np.concatenate([b["hw"], np.full(len(sp_ext) - len(sp), b["hw"][-1])])
        f = ribbon(cv, sp_ext, hw_ext, cut=cut)
        if f is not None:  # t over the visible blade
            f.t = np.clip(f.t * poly_len(sp_ext) / max(poly_len(sp), 1e-6), 0, 1)
    else:
        f = ribbon(cv, b["spine"], b["hw"])
    if f is None:
        return None
    cv.occlude(f, o["contact_sigma_px"], 0.0, o["contact_offset_px"], o["contact_factor"])
    lit_sign = 1.0 if b["chord_deg"] < -3.0 else -1.0
    t_fold = None
    if b["t_fold"] is not None:
        t_fold = b["t_fold"] * b["length_nominal"] / max(b["length"], 1e-6)
        t_fold = float(np.clip(t_fold, 0.3, 0.98))
    straw = hexc(pal["tip_straw"]) if (b["t_cut"] is not None and "tip_straw" in pal) else None
    rgb = shade_blade(f, cols, lit_sign, rng, rec, t_fold=t_fold, straw=straw)
    cv.put(f, rgb)
    return f


def paint_stalk(cv: Canvas, st: dict, rng, rec: dict):
    o = PARAMS["occlusion"]
    oat = PARAMS["palettes"]["oat"]
    f = ribbon(cv, st["spine"], st["hw"])
    if f is not None:
        cv.occlude(f, o["contact_sigma_px"] * 0.6, 0.0, o["contact_offset_px"] * 0.6, 0.9)
        col = mix(hexc(oat["stalk_root"]), hexc(oat["stalk_top"]), smoothstep(0.1, 0.95, f.t))
        lit = (1.0 if st["lean_dir"] < 0 else -1.0) * f.s
        col = col * (0.9 + 0.18 * smoothstep(-0.3, 0.3, lit))[:, None]
        cv.put(f, col)
    head, shade, light = hexc(oat["head"]), hexc(oat["shade"]), hexc(oat["light"])
    for spk in st["spikelets"]:
        fp = ribbon(cv, spk["pedicel"], np.full(len(spk["pedicel"]), 0.65))
        if fp is not None:
            cv.put(fp, np.broadcast_to(hexc(oat["stalk_top"]) * 0.92, (fp.n, 3)))
        body = spk["body"]
        tt = np.linspace(0, 1, len(body))
        hw = 0.5 * spk["width"] * np.sin(np.pi * np.clip(tt, 0, 1) ** 0.65) ** 0.9 + 0.35
        fb = ribbon(cv, body, hw)
        if fb is None:
            continue
        cv.occlude(fb, 1.6, 0.0, 1.2, 0.88)
        c = mix(shade, head, smoothstep(0.0, 0.45, fb.t))
        lit = -spk["side"] * fb.s
        c = c * (0.88 + 0.2 * smoothstep(-0.4, 0.4, lit))[:, None]
        c = mix(c, light, 0.55 * np.clip(1.0 * SS + 0.5 - fb.edge, 0, 1) * (lit > 0.1))
        c = mix(c, shade * 0.9, 0.5 * np.exp(-(fb.s / 0.12) ** 2) * smoothstep(0.2, 0.5, fb.t))  # husk seam
        cv.put(fb, c)


def finish_bundle(cv: Canvas, rng, root_y=504.0, content_h=496.0):
    o, mc = PARAMS["occlusion"], PARAMS["macro"]
    y = (np.arange(cv.h, dtype=np.float32) + 0.5) / SS
    k = o["root_fraction"] * content_h
    root = o["root_factor"] + (1 - o["root_factor"]) * smoothstep(root_y, root_y - k, y)
    yn = np.clip((y - 8.0) / content_h, 0, 1)
    top = 1.0 + mc["top_light"] * (0.5 - yn)
    cv.rgb *= (root * top)[:, None, None]
    apply_macro(cv, rng)


def apply_macro(cv: Canvas, rng, value=None, warmth=None):
    mc = PARAMS["macro"]
    value = mc["value"] if value is None else value
    warmth = mc["warmth"] if warmth is None else warmth
    step = 8
    g1 = smooth_noise((cv.h // step, cv.w // step), mc["sigma_px"] * SS / step, rng)
    g2 = smooth_noise((cv.h // step, cv.w // step), mc["sigma_px"] * SS / step * 1.5, rng)
    n1 = np.clip(cv2.resize(g1, (cv.w, cv.h), interpolation=cv2.INTER_CUBIC), -2.5, 2.5) * 0.5
    n2 = np.clip(cv2.resize(g2, (cv.w, cv.h), interpolation=cv2.INTER_CUBIC), -2.5, 2.5) * 0.5
    gain = 1.0 + value * n1
    cv.rgb[..., 0] *= gain * (1 + warmth * n2)
    cv.rgb[..., 1] *= gain
    cv.rgb[..., 2] *= gain * (1 - warmth * n2)


def paint_bundle_cell(cv: Canvas, rng, cid: str):
    R = PARAMS["cells"][cid]
    dp = PARAMS["depth"]
    pal = PARAMS["palettes"][R["palette"]]
    blades = plan_bundle(rng, cid, R)
    stalks = plan_stalks(rng, R) if R.get("stalks") else []
    n = len(blades)
    lmax = max(b["length"] for b in blades)
    key = (1 - dp["length_weight"]) * rng.uniform(0, 1, n) + dp["length_weight"] * np.array(
        [b["length"] / lmax for b in blades])
    order = list(np.argsort(-key, kind="stable"))  # back (long) first
    n_back = int(round(dp["back_fraction"] * n))
    n_front = int(round(dp["front_fraction"] * n))
    depth_of = {}
    for rank, i in enumerate(order):
        depth_of[i] = "back" if rank < n_back else ("front" if rank >= n - n_front else "mid")
    seq = [("blade", i) for i in order]
    if stalks:  # seed stalks stand among the middle layer
        mid_pos = n_back + max(0, (n - n_back - n_front) // 2)
        for j in range(len(stalks)):
            seq.insert(mid_pos + j, ("stalk", j))
    for kind, i in seq:
        if kind == "stalk":
            paint_stalk(cv, stalks[i], rng, R)
            continue
        b = blades[i]
        cols = blade_palette(pal, rng, depth_of[i], R)
        paint_blade(cv, b, cols, rng, R, pal)
        b["depth"] = depth_of[i]
    finish_bundle(cv, rng)
    chords = [b["chord_deg"] for b in blades]
    tips = [[round(float(b["tip"][0]), 1), round(float(b["tip"][1]), 1)] for b in blades]
    tips += [[round(float(s["tip"][0]), 1), round(float(s["tip"][1]), 1)] for s in stalks]
    return {
        "blade_count": n, "stalk_count": len(stalks),
        "chord_deg_range": [round(min(chords), 1), round(max(chords), 1)],
        "length_frac_range": [round(min(b["length"] for b in blades) / 496.0, 3),
                              round(max(b["length"] for b in blades) / 496.0, 3)],
        "base_width_px_range": [round(min(b["width"] for b in blades), 1), round(max(b["width"] for b in blades), 1)],
        "root_x_offset_px": [round(min(float(b["spine"][0][0]) - 128 for b in blades), 1),
                             round(max(float(b["spine"][0][0]) - 128 for b in blades), 1)],
        "kinds": {k: sum(1 for b in blades if b["kind"] == k) for k in ("normal", "curl", "fold", "bent", "snapped")},
        "s_curves": sum(1 for b in blades if b["shape"] == "s"),
        "tips_local": tips,
        "palette": dict(pal),
    }


# --------------------------------------------------------------------------------------------------
# Flower heads (F cells and G6, top-down)
# --------------------------------------------------------------------------------------------------
CENTRE = np.array([128.0, 128.0])


def petal_axis_light(phi: float) -> float:
    lx, ly = light_dir()
    return math.cos(phi) * lx + math.sin(phi) * ly


def paint_buttercup(cv: Canvas, rng, R: dict):
    n = R["petals"]
    phi0 = rng.uniform(0, 2 * math.pi)
    col, shade, hi, rim = hexc(R["petal"]), hexc(R["shade"]), hexc(R["highlight"]), hexc(R["rim"])
    prof = prof_obovate(0.60, 0.15, 0.7)
    petals = []
    for i in range(n):
        petals.append(dict(phi=phi0 + i * 2 * math.pi / n + math.radians(rng.uniform(-5, 5)),
                           L=rng.uniform(*R["petal_len_px"]), hw=rng.uniform(*R["petal_halfwidth_px"]),
                           val=rng.uniform(0.94, 1.05), asym=rng.uniform(-0.06, 0.06)))
    lx, ly = light_dir()

    def draw(pt, half=None):
        extra = None if half is None else (lambda u, v, hw, h=half: v * h > 0)
        f = axis_shape(cv, CENTRE, pt["phi"], pt["L"], pt["hw"], prof, extra=extra, asym=pt["asym"])
        if f is None:
            return
        if half is None:
            head_occlude(cv, f)
        u, vn = f.u, f.vn
        nrm = np.array([-math.sin(pt["phi"]), math.cos(pt["phi"])])
        side = 1.0 if (nrm[0] * lx + nrm[1] * ly) > 0 else -1.0
        c = mix(shade, col, smoothstep(0.06, 0.58, u))
        spot = np.exp(-((u - 0.66) / 0.15) ** 2 - ((vn - 0.32 * side) / 0.36) ** 2)
        c = mix(c, hi, 0.55 * spot)
        rimw = (1 - smoothstep(1.0 * SS, 3.2 * SS, f.edge)) * smoothstep(0.45, 0.72, u)
        c = mix(c, rim, 0.45 * rimw * (vn * side > -0.2))
        c = c * (0.92 + 0.10 * smoothstep(-0.8, 0.8, vn * side))[:, None]  # cupped: lit half vs shaded half
        c = c * (pt["val"] * (1 - 0.06 * petal_axis_light(pt["phi"])))
        cv.put(f, c)

    for pt in petals:
        draw(pt)
    draw(petals[0], half=-1.0)  # quincuncial overlap: the first petal tucks over the last one
    # centre: green-yellow boss + stamen dots
    cr = R["centre_r_px"]
    f = disc(cv, CENTRE, cr)
    head_occlude(cv, f, 1.2)
    c = mix(hexc(R["centre_light"]), hexc(R["centre"]), smoothstep(0.0, 1.0, f.rho / cr))
    c = c * dome_light(f.dx, f.dy, cr, 0.16)[:, None]
    cv.put(f, c)
    k = int(rng.integers(R["stamens"][0], R["stamens"][1] + 1))
    st, sts = hexc(R["stamen"]), hexc(R["stamen_shade"])
    for j in range(k):
        a = j * 2 * math.pi / k + rng.uniform(-0.15, 0.15)
        rr = rng.uniform(cr * 0.62, cr * 1.18)
        r = rng.uniform(2.6, 3.4)
        ctr = CENTRE + rr * np.array([math.cos(a), math.sin(a)])
        fd = disc(cv, ctr, r)
        if fd is None:
            continue
        cv.occlude(fd, 1.0, 0.6, 0.9, 0.85)
        cc = mix(st, sts, smoothstep(-0.2, 1.0, (fd.dx * -light_dir()[0] + fd.dy * -light_dir()[1]) / r))
        cv.put(fd, cc)
    return {"petals": n, "radius_px": round(max(p["L"] for p in petals), 1),
            "palette": {k2: R[k2] for k2 in ("petal", "shade", "highlight", "centre", "stamen")}}


def paint_daisy(cv: Canvas, rng, R: dict):
    n = int(rng.integers(R["petals"][0], R["petals"][1] + 1))
    n_back = n // 2
    n_front = n - n_back
    phi0 = rng.uniform(0, 2 * math.pi)
    col, shade = hexc(R["petal"]), hexc(R["shade"])
    lx, ly = light_dir()
    specs = []
    for k in range(n_back):
        specs.append(("back", phi0 + k * 2 * math.pi / n_back + math.radians(rng.uniform(-4, 4))))
    for k in range(n_front):
        specs.append(("front", phi0 + (k + 0.5) * 2 * math.pi / n_front + math.radians(rng.uniform(-4, 4))))
    rmax = 0.0
    for layer, phi in specs:
        L = rng.uniform(*R["petal_len_px"]) if layer == "back" else rng.uniform(R["petal_len_px"][0],
                                                                               R["petal_len_px"][1] - 4)
        hw = rng.uniform(*R["petal_halfwidth_px"])
        notch = rng.random() < 0.4
        prof = prof_strap(0.5, 0.2, 1 - 1.1 * hw / L)

        def extra(u, v, hwv, notch=notch, L=L, hw0=hw):
            if not notch:
                return np.ones_like(u, bool)
            return ~((u > 1 - 0.035) & (np.abs(v) < 0.22 * hw0 * SS))
        f = axis_shape(cv, CENTRE, phi, L, hw, prof, extra=extra, bend_px=rng.uniform(-3, 3),
                       asym=rng.uniform(-0.08, 0.08))
        if f is None:
            continue
        rmax = max(rmax, L)
        head_occlude(cv, f, 0.8)
        u, vn = f.u, f.vn
        c = mix(shade, col, smoothstep(0.12, 0.42, u))
        c = c * (1 - 0.06 * np.exp(-(vn / 0.14) ** 2) * smoothstep(0.25, 0.4, u))[:, None]  # centre crease
        nrm = np.array([-math.sin(phi), math.cos(phi)])
        side = 1.0 if (nrm[0] * lx + nrm[1] * ly) > 0 else -1.0
        c = c * (0.95 + 0.07 * smoothstep(-0.6, 0.6, vn * side))[:, None]
        c = mix(c, shade, 0.30 * (1 - smoothstep(0.8 * SS, 2.6 * SS, f.edge)))  # soft grey rim between petals
        val = rng.uniform(0.95, 1.03) * (R["back_value"] if layer == "back" else 1.0)
        c = c * (val * (1 + 0.03 * petal_axis_light(phi) * -1))
        cv.put(f, c)
    # disc
    dr = rng.uniform(*R["disc_r_px"])
    f = disc(cv, CENTRE, dr)
    head_occlude(cv, f, 1.3)
    rr = f.rho / dr
    c = mix(hexc(R["disc"]), hexc(R["ring"]), 0.8 * smoothstep(0.66, 0.95, rr))
    c = c * dome_light(f.dx, f.dy, dr, 0.20)[:, None]
    cv.put(f, c)
    # dotted floret texture (phyllotaxis)
    m = 70
    ga = math.pi * (3 - math.sqrt(5))
    light, dark = hexc(R["disc_light"]), hexc(R["disc_dark"])
    for j in range(m):
        rj = dr * 0.9 * math.sqrt((j + 0.5) / m)
        aj = j * ga
        ctr = CENTRE + rj * np.array([math.cos(aj), math.sin(aj)])
        fd = disc(cv, ctr, 1.5 + 0.7 * (1 - rj / dr))
        if fd is None:
            continue
        base = cv.rgb[fd.ys, fd.xs]
        tone = light if j % 2 == 0 else dark
        cv.put(fd, mix(base, tone, 0.55))
    return {"petals": n, "radius_px": round(rmax, 1), "disc_r_px": round(dr, 1),
            "palette": {k: R[k] for k in ("petal", "shade", "disc", "ring")}}


def paint_poppy(cv: Canvas, rng, R: dict):
    n = int(rng.integers(R["petals"][0], R["petals"][1] + 1))
    phi0 = rng.uniform(0, 2 * math.pi)
    col, rim, base = hexc(R["petal"]), hexc(R["rim"]), hexc(R["base"])
    if n == 4:  # two broad outer petals, two inner ones on top
        specs = [("outer", phi0), ("outer", phi0 + math.pi), ("inner", phi0 + math.pi / 2),
                 ("inner", phi0 + 3 * math.pi / 2)]
    else:
        specs = [("outer" if k < 3 else "inner", phi0 + k * 2 * math.pi / 5) for k in range(5)]
    rmax = 0.0
    for layer, phi in specs:
        phi += math.radians(rng.uniform(-6, 6))
        if layer == "outer":
            L, hw = rng.uniform(*R["outer_len_px"]), rng.uniform(*R["outer_halfwidth_px"])
        else:
            L, hw = rng.uniform(*R["inner_len_px"]), rng.uniform(*R["inner_halfwidth_px"])
        prof = prof_obovate(0.66, 0.22, 0.8, cap=0.6)
        wave_ph, wave_k = rng.uniform(0, 2 * math.pi), rng.uniform(3.5, 5.5)

        def extra(u, v, hwv, ph=wave_ph, k=wave_k, hw0=hw):
            vn = v / (hw0 * SS)
            return u <= 1 - 0.035 * (0.5 + 0.5 * np.sin(vn * k * math.pi + ph))
        f = axis_shape(cv, CENTRE, phi, L, hw, prof, extra=extra, asym=rng.uniform(-0.07, 0.07))
        if f is None:
            continue
        rmax = max(rmax, L)
        head_occlude(cv, f, 1.1)
        u, vn = f.u, f.vn
        c = mix(base, col, smoothstep(0.04, 0.36, u))
        rimw = (1 - smoothstep(2.0 * SS, 12.0 * SS, f.edge)) * smoothstep(0.5, 0.8, u)
        c = mix(c, rim, 0.75 * rimw)
        vein = np.maximum(0, np.cos(vn * 7 * math.pi)) ** 8 * smoothstep(0.1, 0.4, u) * (1 - smoothstep(0.75, 1, u))
        c = c * (1 - 0.06 * vein)[:, None]
        c = c * (0.93 + 0.1 * smoothstep(-1, 1, vn * (1 if layer == "inner" else -1)))[:, None]
        c = mix(c, base * 0.62, 0.3 * (1 - smoothstep(0.0, 0.14, u)))  # dark basal blotch hint
        val = rng.uniform(0.95, 1.04) * (0.95 if layer == "outer" else 1.0)
        cv.put(f, c * val)
    cr = R["centre_r_px"]
    f = disc(cv, CENTRE, cr)
    head_occlude(cv, f, 1.4)
    c = mix(hexc(R["centre_light"]), hexc(R["centre"]), smoothstep(0.0, 0.9, f.rho / cr))
    c = c * dome_light(f.dx, f.dy, cr, 0.18)[:, None]
    ray = np.maximum(0, np.cos(f.th * 7)) ** 16 * smoothstep(0.25, 0.5, f.rho / cr) * (1 - smoothstep(0.8, 1, f.rho / cr))
    c = mix(c, hexc("#7a7050"), 0.5 * ray)  # stigma rays
    cv.put(f, c)
    k = int(rng.integers(26, 37))
    for j in range(k):
        a = j * 2 * math.pi / k + rng.uniform(-0.1, 0.1)
        rr = rng.uniform(cr + 1.0, cr + 9.0)
        ctr = CENTRE + rr * np.array([math.cos(a), math.sin(a)])
        fd = disc(cv, ctr, rng.uniform(1.8, 2.6))
        if fd is None:
            continue
        cv.put(fd, mix(hexc(R["stamen"]), hexc(R["stamen_tip"]), 0.6 * (rr > cr + 5)))
    return {"petals": n, "radius_px": round(rmax, 1),
            "palette": {k2: R[k2] for k2 in ("petal", "rim", "base", "centre")}}


def paint_campion(cv: Canvas, rng, R: dict):
    n = R["petals"]
    phi0 = rng.uniform(0, 2 * math.pi)
    base, col = hexc(R["base"]), hexc(R["petal"])
    lx, ly = light_dir()
    rmax = 0.0
    for i in range(n):
        phi = phi0 + i * 2 * math.pi / n + math.radians(rng.uniform(-4, 4))
        L, hw = rng.uniform(*R["petal_len_px"]), rng.uniform(*R["petal_halfwidth_px"])
        nd, nw = R["notch_depth"] * rng.uniform(0.85, 1.1), R["notch_width"]

        def prof(u):
            w = 0.18 + 0.82 * smoothstep(0.08, 0.62, u)
            capv = np.sqrt(np.clip(1 - ((u - 0.78) / 0.22) ** 2, 0, 1)) ** 0.7
            return np.where(u <= 0.78, w, np.maximum(capv, 0.0))

        def extra(u, v, hwv, nd=nd, nw=nw, hw0=hw):
            vn = np.abs(v) / (hw0 * SS)
            return ~(u > 1 - nd * np.clip(1 - vn / nw, 0, 1))
        f = axis_shape(cv, CENTRE, phi, L, hw, prof, extra=extra, asym=rng.uniform(-0.06, 0.06))
        if f is None:
            continue
        rmax = max(rmax, L)
        head_occlude(cv, f, 0.9)
        u, vn = f.u, f.vn
        c = mix(base, col, smoothstep(0.1, 0.7, u))
        nrm = np.array([-math.sin(phi), math.cos(phi)])
        side = 1.0 if (nrm[0] * lx + nrm[1] * ly) > 0 else -1.0
        c = c * (0.92 + 0.12 * smoothstep(-0.7, 0.7, vn * side))[:, None]
        vein = np.maximum(0, np.cos(vn * 5 * math.pi)) ** 10 * smoothstep(0.1, 0.35, u) * (1 - smoothstep(0.7, 0.95, u))
        c = c * (1 - 0.07 * vein)[:, None]
        c = mix(c, col * 1.08, 0.4 * (1 - smoothstep(0.8 * SS, 2.5 * SS, f.edge)) * (vn * side > 0))
        cv.put(f, c * rng.uniform(0.95, 1.04))
    # pale corona ring + eye
    ring = hexc(R["ring"])
    for j in range(10):
        a = j * 2 * math.pi / 10 + phi0
        ctr = CENTRE + 10.5 * np.array([math.cos(a), math.sin(a)])
        fd = disc(cv, ctr, rng.uniform(3.0, 3.8))
        if fd is not None:
            cv.put(fd, ring * dome_light(fd.dx, fd.dy, 3.4, 0.12)[:, None])
    f = disc(cv, CENTRE, 7.0)
    head_occlude(cv, f, 0.8)
    cv.put(f, hexc(R["eye"]) * dome_light(f.dx, f.dy, 7.0, 0.25)[:, None])
    return {"petals": n, "radius_px": round(rmax, 1), "palette": {k: R[k] for k in ("base", "petal", "ring")}}


def paint_forgetmenot(cv: Canvas, rng, R: dict):
    nf = int(rng.integers(R["flowers"][0], R["flowers"][1] + 1))
    radii = rng.uniform(*R["flower_r_px"], nf)
    centres = [CENTRE + rng.uniform(-6, 6, 2)]
    ring_r = 60.0
    a0 = rng.uniform(0, 2 * math.pi)
    for k in range(1, nf):
        a = a0 + (k - 1) * 2 * math.pi / (nf - 1) + rng.uniform(-0.15, 0.15)
        rr = min(ring_r + rng.uniform(-4, 4), R["cluster_r_px"] - radii[k] - 2)
        centres.append(CENTRE + rr * np.array([math.cos(a), math.sin(a)]))
    petal, shade, rim = hexc(R["petal"]), hexc(R["shade"]), hexc(R["rim"])
    lx, ly = light_dir()
    # buds first (they sit under the open flowers, in the gaps at the cluster edge)
    nb = int(rng.integers(R["buds"][0], R["buds"][1] + 1))
    for k in range(nb):
        a = a0 + (k + 0.5) * 2 * math.pi / max(nb, 1) + rng.uniform(-0.2, 0.2)
        rb = rng.uniform(6.0, 9.0)
        ctr = CENTRE + (R["cluster_r_px"] - rb - rng.uniform(2, 10)) * np.array([math.cos(a), math.sin(a)])
        fd = disc(cv, ctr, rb)
        if fd is None:
            continue
        bc = hexc(R["bud_colours"][k % len(R["bud_colours"])])
        cv.put(fd, bc * dome_light(fd.dx, fd.dy, rb, 0.28)[:, None])
    order = list(rng.permutation(nf))
    for k in order:
        r, ctr = radii[k], centres[k]
        rot = rng.uniform(0, 2 * math.pi)
        dh, dv = rng.uniform(-8, 10), rng.uniform(0.93, 1.06)
        pc, sc, rc = hsv_adjust(petal, dh, 1, dv), hsv_adjust(shade, dh, 1, dv), hsv_adjust(rim, dh, 1, dv)
        for j in range(5):
            a = rot + j * 2 * math.pi / 5
            pctr = ctr + 0.52 * r * np.array([math.cos(a), math.sin(a)])
            pr = 0.47 * r
            fd = disc(cv, pctr, pr)
            if fd is None:
                continue
            head_occlude(cv, fd, 0.7 if j else 1.0)
            # radial position measured from the flower centre
            gx = (fd.xs + 0.5) / SS - ctr[0]
            gy = (fd.ys + 0.5) / SS - ctr[1]
            rr = np.hypot(gx, gy) / r
            c = mix(sc, pc, smoothstep(0.18, 0.62, rr))
            c = mix(c, rc, 0.5 * smoothstep(0.75, 0.98, rr) * (gx * lx + gy * ly > 0))
            c = c * dome_light(fd.dx, fd.dy, pr, 0.10)[:, None]
            cv.put(fd, c)
        # white ring (rounded pentagon) and yellow eye
        rot2 = rot + math.pi / 5

        def ring_fn(rho, th, r=r, rot2=rot2):
            return rho <= 0.33 * r * (0.86 + 0.14 * np.cos(5 * (th - rot2)))
        fr = polar_shape(cv, ctr, 0.4 * r, ring_fn)
        if fr is not None:
            head_occlude(cv, fr, 0.5)
            cv.put(fr, hexc(R["ring"]) * dome_light(fr.dx, fr.dy, 0.33 * r, 0.10)[:, None])
        fe = disc(cv, ctr, 0.15 * r)
        if fe is not None:
            ce = mix(hexc(R["eye"]), hexc(R["eye_dot"]), smoothstep(0.0, 1.0, 1 - fe.rho / (0.15 * r)) * 0.6)
            cv.put(fe, ce)
    return {"flowers": nf, "flower_r_px": [round(float(radii.min()), 1), round(float(radii.max()), 1)],
            "buds": nb, "radius_px": round(float(max(np.linalg.norm(c - CENTRE) + r for c, r in zip(centres, radii))), 1),
            "palette": {k: R[k] for k in ("petal", "shade", "ring", "eye")}}


def paint_yarrow(cv: Canvas, rng, R: dict):
    ns = int(rng.integers(R["subclusters"][0], R["subclusters"][1] + 1))
    lo, hi = R["florets_total"]
    total = int(rng.integers(lo + 6, hi - 5))
    per = np.full(ns, total // ns)
    per[: total - per.sum()] += 1
    sub_r = rng.uniform(*R["subcluster_r_px"], ns)
    centres = [CENTRE + rng.uniform(-5, 5, 2)]
    a0 = rng.uniform(0, 2 * math.pi)
    for k in range(1, ns):
        a = a0 + (k - 1) * 2 * math.pi / (ns - 1) + rng.uniform(-0.18, 0.18)
        rr = min(rng.uniform(48, 60), R["cluster_r_px"] - sub_r[k] - 4)
        centres.append(CENTRE + rr * np.array([math.cos(a), math.sin(a)]))
    under, under_l = hexc(R["under"]), hexc(R["under_light"])
    flo, sh, cen = hexc(R["floret"]), hexc(R["shade"]), hexc(R["centre"])
    lx, ly = light_dir()
    # grey-green umbel bed under each sub-cluster
    for k in range(ns):
        fd = disc(cv, centres[k], sub_r[k] * 0.86)
        if fd is None:
            continue
        head_occlude(cv, fd, 0.8)
        c = mix(under, under_l, smoothstep(-0.6, 0.8, -(fd.dx * lx + fd.dy * ly) / (sub_r[k] * 0.86) * -1))
        cv.put(fd, c)
    placed = 0
    for k in range(ns):
        pts = []
        tries = 0
        while len(pts) < per[k] and tries < 400:
            tries += 1
            rf = rng.uniform(*R["floret_r_px"])
            a = rng.uniform(0, 2 * math.pi)
            rr = math.sqrt(rng.uniform(0, 1)) * max(1.0, sub_r[k] - rf * 0.6)
            p = centres[k] + rr * np.array([math.cos(a), math.sin(a)])
            if np.linalg.norm(p - CENTRE) + rf > R["cluster_r_px"]:
                continue
            if all(np.linalg.norm(p - q) >= 0.78 * (rf + qr) for q, qr in pts):
                pts.append((p, rf))
        for p, rf in pts:
            ph = rng.uniform(0, 2 * math.pi)

            def fl(rho, th, rf=rf, ph=ph):
                return rho <= rf * (0.84 + 0.16 * np.maximum(np.cos(5 * (th - ph)), -0.4))
            f = polar_shape(cv, p, rf, fl)
            if f is None:
                continue
            head_occlude(cv, f, 0.75)
            lit = -(f.dx * lx + f.dy * ly) / rf
            c = mix(sh, flo, smoothstep(-0.9, 0.4, lit))
            c = mix(c, sh * 0.95, 0.35 * (1 - smoothstep(0.6 * SS, 1.8 * SS, f.edge)))
            c = mix(c, cen, 0.85 * (1 - smoothstep(0.18 * rf, 0.34 * rf, f.rho)))
            cv.put(f, c * rng.uniform(0.96, 1.02))
            placed += 1
    return {"subclusters": ns, "florets": placed, "radius_px": round(
        float(max(np.linalg.norm(c - CENTRE) + r for c, r in zip(centres, sub_r))), 1),
        "palette": {k: R[k] for k in ("floret", "shade", "under", "centre")}}


def paint_globe(cv: Canvas, rng, R: dict, white=False):
    """Clover globe: an under-layer disc plus rings of radial florets, darker base -> lighter tips, dome-lit."""
    Rg = R["radius_px"]
    base, mid, tip, under = hexc(R["base"]), hexc(R["mid"]), hexc(R["tip"]), hexc(R["under"])
    lx, ly = light_dir()
    l3 = np.array([lx * 0.62, ly * 0.62, 0.78])
    l3 /= np.linalg.norm(l3)

    def sphere_light(px, py):
        x = (px / SS - CENTRE[0]) / Rg
        y = (py / SS - CENTRE[1]) / Rg
        z = np.sqrt(np.clip(1 - x * x - y * y, 0.0, 1.0))
        nl = np.clip(x * l3[0] + y * l3[1] + z * l3[2], 0, 1)
        return 0.74 + 0.36 * nl

    f = disc(cv, CENTRE, Rg * 0.84)
    xy = np.stack([f.xs + 0.5, f.ys + 0.5])
    cv.put(f, under * sphere_light(xy[0], xy[1])[:, None])
    count = 0
    for r0, ln, nk, hwk in R["rings"]:
        phi0 = rng.uniform(0, 2 * math.pi)
        for j in range(int(nk)):
            phi = phi0 + j * 2 * math.pi / nk + math.radians(rng.uniform(-7, 7))
            start = CENTRE + r0 * Rg * np.array([math.cos(phi), math.sin(phi)])
            L = ln * Rg * rng.uniform(0.86, 1.08)
            if r0 * Rg + L > Rg * 1.02:
                L = Rg * 1.02 - r0 * Rg
            fl = axis_shape(cv, start, phi + math.radians(rng.uniform(-8, 8)), L, hwk * rng.uniform(0.9, 1.1),
                            prof_floret(0.8), bend_px=rng.uniform(-1.5, 1.5))
            if fl is None:
                continue
            head_occlude(cv, fl, 0.8)
            c = mix(base, mid, smoothstep(0.0, 0.55, fl.u))
            c = mix(c, tip, smoothstep(0.55, 1.0, fl.u))
            if white:
                c = mix(c, hexc(R["pink"]), 0.35 * (1 - smoothstep(0.0, 0.5, fl.u)))
            c = c * (0.93 + 0.1 * smoothstep(-0.8, 0.8, fl.vn))[:, None]
            c = c * sphere_light(fl.px, fl.py)[:, None]
            cv.put(fl, c * rng.uniform(0.95, 1.04))
            count += 1
    return {"florets": count, "radius_px": Rg, "palette": {k: R[k] for k in ("base", "mid", "tip", "under")}}


def paint_violet(cv: Canvas, rng, R: dict):
    n = R["petals"]
    phi0 = rng.uniform(0, 2 * math.pi)
    col, centre, vein, tipc = hexc(R["petal"]), hexc(R["centre"]), hexc(R["vein"]), hexc(R["tip"])
    lx, ly = light_dir()
    prof = prof_lance(0.72, 0.85, 0.30)
    rmax = 0.0
    petals = []
    for i in range(n):
        petals.append(dict(phi=phi0 + i * 2 * math.pi / n + math.radians(rng.uniform(-4, 4)),
                           L=rng.uniform(*R["petal_len_px"]), hw=rng.uniform(*R["petal_halfwidth_px"]),
                           bend=rng.uniform(-4, 4), asym=rng.uniform(-0.06, 0.06)))

    def draw(pt, half=None):
        extra = None if half is None else (lambda u, v, hw, h=half: v * h > 0)
        f = axis_shape(cv, CENTRE, pt["phi"], pt["L"], pt["hw"], prof, extra=extra, bend_px=pt["bend"],
                       asym=pt["asym"])
        if f is None:
            return 0.0
        if half is None:
            head_occlude(cv, f, 0.9)
        u, vn = f.u, f.vn
        c = mix(centre, col, smoothstep(0.12, 0.5, u))
        c = mix(c, tipc, 0.6 * smoothstep(0.7, 1.0, u))
        nrm = np.array([-math.sin(pt["phi"]), math.cos(pt["phi"])])
        side = 1.0 if (nrm[0] * lx + nrm[1] * ly) > 0 else -1.0
        c = c * (0.9 + 0.14 * smoothstep(-0.5, 0.5, vn * side))[:, None]
        c = mix(c, vein, 0.55 * np.exp(-(vn / 0.09) ** 2) * smoothstep(0.22, 0.32, u) * (1 - smoothstep(0.75, 0.9, u)))
        c = mix(c, col * 0.82, 0.3 * (1 - smoothstep(0.8 * SS, 2.4 * SS, f.edge)))
        cv.put(f, c)
        return pt["L"]

    for pt in petals:
        rmax = max(rmax, draw(pt))
    draw(petals[0], half=-1.0)
    f = disc(cv, CENTRE, 8.0)
    head_occlude(cv, f, 0.6)
    cv.put(f, hexc(R["eye"]) * dome_light(f.dx, f.dy, 8.0, 0.2)[:, None])
    for j in range(5):
        a = phi0 + (j + 0.5) * 2 * math.pi / 5
        fd = disc(cv, CENTRE + 6.0 * np.array([math.cos(a), math.sin(a)]), 1.8)
        if fd is not None:
            cv.put(fd, np.broadcast_to(vein * 0.8, (fd.n, 3)))
    return {"petals": n, "radius_px": round(rmax, 1), "palette": {k: R[k] for k in ("petal", "centre", "vein")}}


# --------------------------------------------------------------------------------------------------
# Leaves and stems (G cells)
# --------------------------------------------------------------------------------------------------
def paint_clover_leaf(cv: Canvas, rng, R: dict):
    n = R["leaflets"]
    phi0 = rng.uniform(0, 2 * math.pi)
    half = math.radians(R["half_angle_deg"])
    leaf, chev, rimc, mid = hexc(R["leaf"]), hexc(R["chevron"]), hexc(R["rim"]), hexc(R["midrib"])
    lx, ly = light_dir()
    lens = []
    for i in range(n):
        phi = phi0 + i * 2 * math.pi / n + math.radians(rng.uniform(-5, 5))
        L = rng.uniform(*R["leaflet_len_px"])
        lens.append(L)
        notch = rng.uniform(*R["notch"])
        gexp = rng.uniform(0.28, 0.36)
        dn = math.radians(rng.uniform(7.5, 9.5))
        val = 1 + rng.uniform(-R["value_var"], R["value_var"])

        def shape(rho, th, phi=phi, L=L, notch=notch, gexp=gexp, dn=dn):
            dl = (th - phi + math.pi) % (2 * math.pi) - math.pi
            x = np.clip(np.abs(dl) / half, 0, 1)
            g = np.cos(0.5 * np.pi * x) ** gexp * (1 - notch * np.exp(-(dl / dn) ** 2))
            return (np.abs(dl) <= half) & (rho <= L * g)
        f = polar_shape(cv, CENTRE, L + 2, shape)
        if f is None:
            continue
        head_occlude(cv, f, 0.9)
        dl = (f.th - phi + math.pi) % (2 * math.pi) - math.pi
        vn = dl / half
        u = f.rho / L
        c = leaf * (0.82 + 0.18 * smoothstep(0.0, 0.45, u))[:, None]
        uc = 0.40 + 0.36 * np.abs(vn)
        band = np.exp(-((u - uc) / 0.075) ** 2) * (1 - smoothstep(0.62, 0.92, np.abs(vn)))
        c = mix(c, chev, R["chevron_strength"] * band)
        rib = np.exp(-(vn / 0.045) ** 2) * smoothstep(0.08, 0.2, u) * (1 - smoothstep(0.72, 0.9, u))
        c = mix(c, mid, 0.40 * rib)
        nrm = np.array([-math.sin(phi), math.cos(phi)])
        side = 1.0 if (nrm[0] * lx + nrm[1] * ly) > 0 else -1.0
        c = c * (0.94 + 0.11 * smoothstep(-0.25, 0.25, vn * side))[:, None]
        c = mix(c, rimc, 0.6 * (1 - smoothstep(0.8 * SS, 2.8 * SS, f.edge)))
        c = c * (val * (1 + 0.04 * -petal_axis_light(phi)))
        cv.put(f, c)
    fj = disc(cv, CENTRE, 3.5)
    cv.put(fj, np.broadcast_to(rimc * 1.1, (fj.n, 3)))
    return {"leaflets": n, "leaflet_len_px": [round(min(lens), 1), round(max(lens), 1)],
            "radius_px": round(max(lens), 1), "palette": {k: R[k] for k in ("leaf", "chevron", "rim", "midrib")}}


def paint_plantain(cv: Canvas, rng, R: dict):
    base = np.array([128.0, 232.0])
    L, hwm = R["length_px"], R["halfwidth_px"]
    leaf, vein, groove, rimc = hexc(R["leaf"]), hexc(R["vein"]), hexc(R["groove"]), hexc(R["rim"])
    wave_ph = rng.uniform(0, 2 * math.pi)

    def prof(u):
        w = np.sin(np.pi * np.clip(u, 0, 1) ** 0.85) ** 0.75
        w = w * (1 + 0.025 * np.sin(u * 9 * math.pi + wave_ph))
        return np.maximum(w, (4.5 / hwm) * (1 - smoothstep(0.0, 0.08, u)))
    f = axis_shape(cv, base, -math.pi / 2, L, hwm, prof, bend_px=rng.uniform(-5, 5), asym=rng.uniform(-0.05, 0.05))
    u, vn = f.u, f.vn
    c = leaf * (0.84 + 0.16 * smoothstep(0.0, 0.35, u))[:, None]
    lx, _ = light_dir()
    side = -1.0 if lx < 0 else 1.0  # axis points up: +v is +x... normal of (0,-1) is (1,0)
    c = c * (0.92 + 0.15 * smoothstep(-0.2, 0.2, vn * -side))[:, None]
    nv = R["veins"]
    pos = np.linspace(-0.72, 0.72, nv)
    fade = smoothstep(0.03, 0.12, u) * (1 - smoothstep(0.86, 0.97, u))
    for k, vk in enumerate(pos):
        dist_px = np.abs(vn - vk) * f.hw / SS
        w = 1.3 if abs(vk) < 1e-6 else 1.0
        line = np.clip(w + 0.5 - dist_px, 0, 1) * fade
        grv = np.clip(1.0 + 0.5 - np.abs(vn - vk - 0.06 * np.sign(vk + 1e-6)) * f.hw / SS, 0, 1) * fade
        c = mix(c, groove, 0.35 * grv * (1 - line))
        c = mix(c, vein, (0.55 if abs(vk) < 1e-6 else 0.42) * line)
    c = mix(c, rimc, 0.6 * (1 - smoothstep(0.8 * SS, 3.0 * SS, f.edge)))
    cv.put(f, c)
    return {"length_px": L, "width_px": 2 * hwm, "veins": nv, "base_px_local": [128.0, 232.0],
            "tip_px_local": [128.0, 24.0], "palette": {k: R[k] for k in ("leaf", "vein", "rim")}}


def stem_leaf(cv: Canvas, rng, attach, angle, length, width, cols, lit_sign, droop_deg):
    o = PARAMS["occlusion"]
    sp = blade_bezier(attach, length, angle, -math.copysign(math.radians(6), droop_deg),
                      math.radians(droop_deg), 0.35, 0.38)
    tt = np.linspace(0, 1, len(sp))
    hw = lanceolate_halfwidth(tt, width) + 0.3
    f = ribbon(cv, sp, hw)
    if f is None:
        return
    cv.occlude(f, o["contact_sigma_px"] * 0.6, 0.0, o["contact_offset_px"] * 0.6, 0.88)
    c = mix(cols[0], cols[1], smoothstep(0.0, 0.8, f.t))
    lit = lit_sign * f.s
    c = c * (0.9 + 0.17 * smoothstep(-0.2, 0.2, lit))[:, None]
    c = mix(c, cols[2], 0.35 * np.exp(-(f.s / 0.12) ** 2) * smoothstep(0.05, 0.2, f.t) * (1 - smoothstep(0.7, 0.9, f.t)))
    c = mix(c, cols[2], 0.6 * np.clip(1.0 * SS + 0.5 - f.edge, 0, 1) * (lit > 0.2) * smoothstep(0.2, 0.3, f.t))
    cv.put(f, c)


def paint_stems(cv: Canvas, rng, R: dict, base_leaves=False):
    n = int(rng.integers(R["stems"][0], R["stems"][1] + 1))
    root_c, top_c = hexc(R["root"]), hexc(R["top"])
    leaf_cols = (hexc("#4a6e30"), hexc("#7aa048"), hexc("#a4c46a"))
    q = (np.arange(n) + 0.5) / n + rng.uniform(-0.3, 0.3, n) / n
    p = q * 2 - 1
    heights = rng.uniform(*R["height_px"], n)
    tips = []
    order = list(rng.permutation(n))
    stems = []
    for i in range(n):
        th = math.radians(p[i] * R["spread_deg"] * rng.uniform(0.6, 1.0))
        lean_dir = 1.0 if th >= 0 else -1.0
        d0 = -lean_dir * math.radians(rng.uniform(2, 6))
        d1 = lean_dir * math.radians(rng.uniform(3, 12))
        root = (128 + rng.uniform(-6, 6), 248.0)
        h = heights[i]
        L = h / max(0.5, math.cos(th)) * 1.01
        for _ in range(40):
            sp = blade_bezier(root, L, th, d0, d1, 0.34, 0.34)
            vert = root[1] - sp[:, 1].min()
            if abs(vert - h) < 0.5:
                break
            L *= h / max(vert, 1e-3)
        while sp[:, 0].min() < 14 or sp[:, 0].max() > 242:
            th *= 0.85
            sp = blade_bezier(root, L, th, d0, d1, 0.34, 0.34)
        w0 = rng.uniform(*R["width_px"])
        tt = np.linspace(0, 1, len(sp))
        hw = 0.5 * w0 * (1 - 0.32 * tt)
        stems.append(dict(sp=sp, hw=hw, lean_dir=lean_dir, th=th))
        tips.append([float(sp[-1][0]), float(sp[-1][1])])
    o = PARAMS["occlusion"]
    for i in order:
        st = stems[i]
        sp, hw = st["sp"], st["hw"]
        if base_leaves:
            k = int(rng.integers(R["base_leaves"][0], R["base_leaves"][1] + 1))
            for j in range(k):
                ta = rng.uniform(*R["leaf_attach_t"])
                idx = int(round(ta * (len(sp) - 1)))
                side = 1.0 if (j % 2 == 0) == (st["lean_dir"] > 0) else -1.0
                ang = spine_tangent_angle(sp, idx) + side * math.radians(rng.uniform(16, 40))
                ln = rng.uniform(*R["leaf_len_px"])
                # keep the long leaf inside the cell
                for _ in range(20):
                    end = sp[idx] + ln * dvec(ang + side * math.radians(20))
                    if 12 < end[0] < 244 and end[1] > 12:
                        break
                    ln *= 0.9
                stem_leaf(cv, rng, sp[idx], ang, ln, rng.uniform(*R["leaf_width_px"]), leaf_cols,
                          -side, side * rng.uniform(25, 50))
        f = ribbon(cv, sp, hw)
        if f is not None:
            cv.occlude(f, o["contact_sigma_px"] * 0.6, 0.0, o["contact_offset_px"] * 0.6, 0.88)
            c = mix(root_c, top_c, smoothstep(0.0, 1.0, f.t))
            lit = (-1.0 if st["lean_dir"] > 0 else 1.0) * f.s
            c = c * (0.86 + 0.22 * smoothstep(-0.6, 0.6, lit))[:, None]
            cv.put(f, c)
        cap = disc(cv, sp[-1], float(hw[-1]) + 0.2)
        if cap is not None:
            cv.put(cap, np.broadcast_to(top_c, (cap.n, 3)))
        if not base_leaves:
            k = int(rng.integers(R["leaves_per_stem"][0], R["leaves_per_stem"][1] + 1))
            ts = np.sort(rng.uniform(*R["leaf_attach_t"], k))
            for j, ta in enumerate(ts):
                idx = int(round(ta * (len(sp) - 1)))
                side = 1.0 if j % 2 == 0 else -1.0
                if st["lean_dir"] < 0:
                    side = -side
                ang = spine_tangent_angle(sp, idx) + side * math.radians(rng.uniform(30, 55))
                stem_leaf(cv, rng, sp[idx], ang, rng.uniform(*R["leaf_len_px"]), rng.uniform(*R["leaf_width_px"]),
                          leaf_cols, -side, side * rng.uniform(12, 30))
    finish_side_cell(cv, rng)
    return {"stems": n, "tips_local": tips, "heights_px": [round(float(h), 1) for h in heights],
            "palette": {"root": R["root"], "top": R["top"], "leaf": "#4a6e30", "leaf_tip": "#7aa048"}}


def paint_leafy_base(cv: Canvas, rng, R: dict):
    n = int(rng.integers(R["leaves"][0], R["leaves"][1] + 1))
    o = PARAMS["occlusion"]
    q = (np.arange(n) + 0.5) / n + rng.uniform(-0.3, 0.3, n) / n
    p = q * 2 - 1
    lens = rng.uniform(*R["leaf_len_px"], n)
    key = np.abs(p) + rng.uniform(0, 0.3, n)
    lens_sorted = np.sort(lens)[::-1]
    Ls = np.empty(n)
    Ls[np.argsort(key, kind="stable")] = lens_sorted
    order = list(np.argsort(-(Ls + rng.uniform(0, 30, n)), kind="stable"))
    root_c, mid_c, tip_c, rib_c, edge_c = (hexc(R[k]) for k in ("root", "mid", "tip", "midrib", "edge"))
    for rank, i in enumerate(order):
        th = math.radians(p[i] * R["spread_deg"])
        lean_dir = 1.0 if th >= 0 else -1.0
        droop = math.radians(rng.uniform(15, 45)) * abs(p[i])
        L = Ls[i]
        w = rng.uniform(*R["leaf_width_px"])
        root = (128 + rng.uniform(-8, 8) + p[i] * 6, 248.0)
        for _ in range(40):
            sp = blade_bezier(root, L, th, -lean_dir * droop * 0.3, lean_dir * droop, 0.36, 0.38)
            hw = leaf_halfwidth(np.linspace(0, 1, len(sp)), w)
            x0, y0, x1, y1 = spine_outline_box(sp, hw)
            if x0 >= 10 and x1 <= 246 and y0 >= 10 and y1 <= 250:
                break
            L *= 0.95
        f = ribbon(cv, sp, hw)
        if f is None:
            continue
        cv.occlude(f, o["contact_sigma_px"], 0.0, o["contact_offset_px"], o["contact_factor"])
        dv = (0.82 if rank < n * 0.4 else 1.0) * rng.uniform(0.94, 1.06)
        c = gradient3(f.t, root_c * dv, mid_c * dv, tip_c * dv)
        lit_sign = 1.0 if th < -0.05 else -1.0
        lit = lit_sign * f.s
        c = c * (0.9 + 0.17 * smoothstep(-0.2, 0.2, lit))[:, None]
        c = mix(c, rib_c * dv, 0.4 * np.exp(-(f.s / 0.08) ** 2) * smoothstep(0.08, 0.2, f.t) * (1 - smoothstep(0.75, 0.92, f.t)))
        c = mix(c, edge_c * dv, 0.7 * np.clip(1.25 * SS + 0.5 - f.edge, 0, 1) * (lit > 0.2) * smoothstep(0.25, 0.35, f.t))
        cv.put(f, c)
    finish_side_cell(cv, rng)
    return {"leaves": n, "leaf_len_px": [round(float(Ls.min()), 1), round(float(Ls.max()), 1)],
            "palette": {k: R[k] for k in ("root", "mid", "tip", "midrib")}}


def finish_side_cell(cv: Canvas, rng):
    o = PARAMS["occlusion"]
    y = (np.arange(cv.h, dtype=np.float32) + 0.5) / SS
    k = o["root_fraction"] * 240.0
    root = o["root_factor"] + (1 - o["root_factor"]) * smoothstep(248.0, 248.0 - k, y)
    cv.rgb *= root[:, None, None]
    apply_macro(cv, rng, value=0.03, warmth=0.02)


def paint_lavender(cv: Canvas, rng, R: dict):
    """Three elongated spikes with paired florets, rather than a generic five-petal violet."""
    count = 0
    for spike in range(R["spikes"]):
        angle = -0.18 + spike * 0.18
        direction = np.array([math.sin(angle), -math.cos(angle)])
        side = np.array([math.cos(angle), math.sin(angle)])
        origin = CENTRE + np.array([(spike-1)*38.0, 44.0])
        for level in range(R["florets_per_spike"]):
            for sign in [-1, 1]:
                centre = origin + direction * (level*14.0) + side * sign * (9.0-level*.7)
                radius = 10.0-level*.55
                field = disc(cv, centre, radius)
                if field is None: continue
                head_occlude(cv, field, .7)
                shade = hexc(R["shade"]);petal = hexc(R["petal"]);tip = hexc(R["tip"])
                colour = mix(shade, petal, smoothstep(-radius, radius, -field.dy))
                colour = mix(colour, tip, .3*smoothstep(0, radius, -field.dy))
                cv.put(field, colour * dome_light(field.dx, field.dy, radius, .15)[:, None]);count += 1
    return {"spikes":R["spikes"],"florets":count,"radius_px":105.0,"palette":{k:R[k] for k in ("petal","shade","tip")}}


PAINTERS = {
    "F0": paint_buttercup, "F1": paint_daisy, "F2": paint_poppy, "F3": paint_poppy, "F4": paint_daisy,
    "F5": paint_yarrow, "F6": paint_globe, "F7": paint_lavender, "G0": paint_clover_leaf, "G1": paint_clover_leaf,
    "G2": paint_plantain, "G5": paint_leafy_base,
}


# --------------------------------------------------------------------------------------------------
# Resolve, assemble, edge bleed, mips, coverage
# --------------------------------------------------------------------------------------------------
def resolve(cv: Canvas):
    """2x2 box resolve: alpha = covered fraction, RGB = mean of the covered sub-samples (linear light)."""
    h, w = cv.h // SS, cv.w // SS
    cov = cv.cov.reshape(h, SS, w, SS)
    n = cov.sum(axis=(1, 3))
    lin = srgb_to_linear(cv.rgb) * cv.cov[..., None]
    lin = lin.reshape(h, SS, w, SS, 3).sum(axis=(1, 3))
    rgb = linear_to_srgb(lin / np.maximum(n, 1)[..., None])
    return rgb, (n / (SS * SS)).astype(np.float32)


def content_mask(cid: str, view: str):
    rect = cell_rect(cid)
    h, w = rect[3], rect[2]
    (x0, y0, x1, y1), circ = cell_local_content(cid, view)
    yy, xx = np.mgrid[0:h, 0:w]
    m = (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
    if circ:
        m &= (xx + 0.5 - 128) ** 2 + (yy + 0.5 - 128) ** 2 <= HEAD_RADIUS_MAX ** 2
    return m


def edge_bleed(rgb: np.ndarray, a: np.ndarray, fill=None) -> np.ndarray:
    """Transparent texels take the RGB of the nearest texel with alpha >= 0.5 (unlimited radius), then a 5x5
    box blur is applied to the transparent texels only. Works on one cell so colours never cross cells."""
    src = a >= 0.5
    out = rgb.copy()
    trans = a < (1.0 / 255.0)
    if not src.any():
        if fill is not None:
            out[trans] = fill
        return out
    _, (iy, ix) = ndimage.distance_transform_edt(~src, return_indices=True)
    out[trans] = rgb[iy[trans], ix[trans]]
    blurred = ndimage.uniform_filter(out, size=(5, 5, 1), mode="nearest")
    out[trans] = blurred[trans]
    return out


def box_down(rgb_lin: np.ndarray, a: np.ndarray, weighted: bool):
    h, w = a.shape[0] // 2, a.shape[1] // 2
    a4 = a.reshape(h, 2, w, 2)
    a2 = a4.mean(axis=(1, 3))
    if weighted:
        num = (rgb_lin * a[..., None]).reshape(h, 2, w, 2, 3).sum(axis=(1, 3))
        den = a4.sum(axis=(1, 3))[..., None]
        plain = rgb_lin.reshape(h, 2, w, 2, 3).mean(axis=(1, 3))
        rgb2 = np.where(den > 1e-6, num / np.maximum(den, 1e-6), plain)
    else:
        rgb2 = rgb_lin.reshape(h, 2, w, 2, 3).mean(axis=(1, 3))
    return rgb2.astype(np.float32), a2.astype(np.float32)


def coverage_scales(a0: np.ndarray, content_area: float):
    """Castano: per mip, find s so that the alpha-tested (>= 0.5) coverage of min(1, a*s) matches mip 0."""
    c0_count = float((a0 >= 0.5).sum())
    c0 = c0_count / content_area
    scales, errs, raw = [], [], []
    a = a0
    for k in range(1, MIP_LEVELS + 1):
        h, w = a.shape[0] // 2, a.shape[1] // 2
        a = a.reshape(h, 2, w, 2).mean(axis=(1, 3))
        texel = 4.0 ** k

        def cover(s, a=a, texel=texel):
            return float((np.minimum(1.0, a * s) >= 0.5).sum()) * texel / content_area
        raw.append(cover(1.0) - c0)
        lo, hi = 1.0 / 16, 64.0
        best_s, best_e = 1.0, abs(cover(1.0) - c0)
        for _ in range(60):
            mid = math.sqrt(lo * hi)
            cv_ = cover(mid)
            e = abs(cv_ - c0)
            if e < best_e - 1e-12 or (abs(e - best_e) <= 1e-12 and abs(math.log(mid)) < abs(math.log(best_s))):
                best_s, best_e = mid, e
            if cv_ < c0:
                lo = mid
            else:
                hi = mid
            if hi / lo < 1.0 + 1e-6:
                break
        scales.append(best_s)
        errs.append(cover(best_s) - c0)
    lods = np.arange(1, MIP_LEVELS + 1, dtype=np.float64)
    kfit = float(((np.array(scales) - 1.0) * lods).sum() / (lods ** 2).sum())
    return c0, scales, errs, raw, kfit


def build_atlas(seed: int, log=print):
    full_rgb = np.zeros((ATLAS_H, ATLAS_W, 3), np.float32)
    full_a = np.zeros((ATLAS_H, ATLAS_W), np.float32)
    meta = {}
    for index, (cid, name, kind, view) in enumerate(CELL_DEFS):
        t0 = time.time()
        x, y, w, h = cell_rect(cid)
        if kind == "reserved":
            meta[cid] = {}
            continue
        (cx0, cy0, cx1, cy1), _ = cell_local_content(cid, view)
        cv = Canvas(w, h, (cx0, cy0, cx1, cy1))
        rng = rng_for(seed, index, 1)
        if cid[0] == "B":
            info = paint_bundle_cell(cv, rng, cid)
        elif cid in ("G3", "G4"):
            info = paint_stems(cv, rng, PARAMS["cells"][cid], base_leaves=(cid == "G4"))
        elif cid == "G6":
            info = paint_globe(cv, rng, PARAMS["cells"][cid], white=True)
            apply_macro(cv, rng, value=0.03, warmth=0.015)
        else:
            info = PAINTERS[cid](cv, rng, PARAMS["cells"][cid])
            if view == "top":
                apply_macro(cv, rng, value=0.035, warmth=0.02)
        rgb, a = resolve(cv)
        del cv
        a = a * content_mask(cid, view)
        full_rgb[y:y + h, x:x + w] = rgb
        full_a[y:y + h, x:x + w] = a
        meta[cid] = info
        log(f"  painted {cid} {name:<20s} {time.time() - t0:5.2f}s")
    lo, hi = PARAMS["clamp_srgb8"]
    full_rgb = np.clip(full_rgb, lo / 255.0, hi / 255.0)
    a8 = np.round(full_a * 255.0).astype(np.uint8)
    af = a8.astype(np.float32) / 255.0
    # bundle mean colour (linear, alpha-weighted) used to fill the reserved cell
    sel = af[0:512] >= 0.5
    lin_b = srgb_to_linear(full_rgb[0:512])
    fill = linear_to_srgb((lin_b[sel] * af[0:512][sel][:, None]).sum(0) / af[0:512][sel].sum())
    for cid, name, kind, view in CELL_DEFS:
        x, y, w, h = cell_rect(cid)
        full_rgb[y:y + h, x:x + w] = edge_bleed(full_rgb[y:y + h, x:x + w], af[y:y + h, x:x + w], fill=fill)
    full_rgb = np.clip(full_rgb, lo / 255.0, hi / 255.0)
    rgba = np.dstack([np.round(full_rgb * 255.0).astype(np.uint8), a8])
    return rgba, meta, fill


def build_half(rgba: np.ndarray, s1: dict, fill) -> np.ndarray:
    lo, hi = PARAMS["clamp_srgb8"]
    out = np.zeros((ATLAS_H // 2, ATLAS_W // 2, 4), np.uint8)
    for cid, name, kind, view in CELL_DEFS:
        x, y, w, h = cell_rect(cid)
        cell = rgba[y:y + h, x:x + w].astype(np.float32) / 255.0
        lin = srgb_to_linear(cell[..., :3])
        rgb2, a2 = box_down(lin, cell[..., 3], weighted=True)
        a2 = np.minimum(1.0, a2 * s1.get(cid, 1.0))
        a8 = np.round(a2 * 255.0).astype(np.uint8)
        srgb2 = linear_to_srgb(rgb2)
        srgb2 = edge_bleed(srgb2, a8.astype(np.float32) / 255.0, fill=fill)
        srgb2 = np.clip(srgb2, lo / 255.0, hi / 255.0)
        out[y // 2:(y + h) // 2, x // 2:(x + w) // 2] = np.dstack([np.round(srgb2 * 255.0).astype(np.uint8), a8])
    return out


# --------------------------------------------------------------------------------------------------
# PNG + manifest
# --------------------------------------------------------------------------------------------------
def png_bytes(arr: np.ndarray) -> bytes:
    """Deterministic PNG: RGBA8, zlib level 9, no ancillary chunks (no gAMA/cHRM/sRGB/iCCP/tIME/pHYs)."""
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(arr), "RGBA").save(buf, format="PNG", compress_level=9, optimize=False)
    return buf.getvalue()


def png_chunks(data: bytes) -> list:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, out = 8, []
    while pos < len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        out.append(data[pos + 4:pos + 8].decode("ascii"))
        pos += 12 + ln
    return out


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rnd(v, n=6):
    if isinstance(v, (list, tuple, np.ndarray)):
        return [rnd(x, n) for x in v]
    return round(float(v), n)


def cell_stats(rgba: np.ndarray, cid: str, kind: str):
    x, y, w, h = cell_rect(cid)
    cell = rgba[y:y + h, x:x + w].astype(np.float32) / 255.0
    a = cell[..., 3]
    lin = srgb_to_linear(cell[..., :3])
    sel = a >= 0.5
    out = {}
    if sel.any():
        wts = a[sel][:, None]
        out["mean_linear_rgb"] = rnd((lin[sel] * wts).sum(0) / wts.sum(), 5)
        if kind == "bundle":
            ys = np.nonzero(sel)[0]
            order = np.argsort(ys, kind="stable")
            k = max(1, int(round(0.15 * len(ys))))
            px = lin[sel]
            wv = a[sel]
            top, bot = order[:k], order[-k:]
            out["root_linear_rgb"] = rnd((px[bot] * wv[bot, None]).sum(0) / wv[bot].sum(), 5)
            out["tip_linear_rgb"] = rnd((px[top] * wv[top, None]).sum(0) / wv[top].sum(), 5)
        ys, xs = np.nonzero(a > 0)
        out["bbox_px"] = [int(x + xs.min()), int(y + ys.min()), int(x + xs.max() + 1), int(y + ys.max() + 1)]
    return out


def build_manifest(seed, rgba, meta, cov, outputs, script_sha):
    cells = []
    for cid, name, kind, view in CELL_DEFS:
        x, y, w, h = cell_rect(cid)
        (cx0, cy0, cx1, cy1), circ = cell_local_content(cid, view)
        ax, ay = cell_local_anchor(cid, view)
        entry = {"id": cid, "name": name, "kind": kind, "view": view, "rect_px": [x, y, w, h],
                 "anchor_px": [x + ax, y + ay], "content_px": [x + cx0, y + cy0, x + cx1, y + cy1]}
        if circ:
            entry["content_radius_px"] = HEAD_RADIUS_MAX
        c = cov[cid]
        entry["coverage_mip0"] = rnd(c["c0"], 6)
        entry["mip_scales"] = rnd(c["scales"], 5)
        entry["mip_coverage_k"] = rnd(c["k"], 5)
        entry.update(cell_stats(rgba, cid, kind))
        info = meta.get(cid, {})
        if cid in ("G3", "G4"):
            entry["tips_px"] = [[round(x + tx, 1), round(y + ty, 1)] for tx, ty in info["tips_local"]]
        if kind == "bundle":
            entry["blade_count"] = info["blade_count"]
            entry["stalk_count"] = info["stalk_count"]
            entry["chord_deg_range"] = info["chord_deg_range"]
            entry["length_frac_range"] = info["length_frac_range"]
            entry["base_width_px_range"] = info["base_width_px_range"]
            entry["root_x_offset_px"] = info["root_x_offset_px"]
            entry["blade_kinds"] = info["kinds"]
        if "radius_px" in info:
            entry["radius_px"] = info["radius_px"]
        if kind == "reserved":
            entry["note"] = "fully transparent; RGB is a constant fill (mean bundle colour) as there is no opaque source"
        entry["palette"] = info.get("palette", {})
        cells.append(entry)
    ks = [cov[cid]["k"] for cid, _, kind, _ in CELL_DEFS if kind == "bundle"]
    return {
        "schema": "xexoria.grass-atlas/1",
        "name": "grass_atlas_v1",
        "size": [ATLAS_W, ATLAS_H],
        "unit_px": UNIT,
        "grid": [COLS, ROWS],
        "gutter_px": GUTTER,
        "color_space": "sRGB",
        "alpha": "straight, edge-bled",
        "alpha_test": 0.5,
        "uv": "image row 0 at the top; load with invertY = false; u = x / 2048, v = y / 1024",
        "files": {"full": FULL_NAME, "half": HALF_NAME, "dir": OUT_DIR_REL},
        "half_atlas": "cell-wise 2x2 box (alpha averaged, RGB alpha-weighted in linear light), alpha x mip_scales[0], edge-bled",
        "mip_coverage": "alpha_mip = min(1, alpha * (1 + mip_coverage_k * lod)); per-cell mip_scales are exact for lod 1..5",
        "mip_coverage_k": rnd(float(np.median(ks)), 5),
        "cells": cells,
        "generator": {"script": SCRIPT_REL, "sha256": script_sha, "seed": int(seed), "params": PARAMS},
        "outputs": outputs,
        "licence": "Project-owned procedural output; no third-party pixels",
        "provenance": "Generated from the seed by the script; no source images",
    }


# --------------------------------------------------------------------------------------------------
# Gates (self-review metrics)
# --------------------------------------------------------------------------------------------------
def zhang_suen(mask: np.ndarray) -> np.ndarray:
    img = np.pad(mask.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            P2, P3, P4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            P5, P6, P7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            P8, P9 = img[1:-1, :-2], img[:-2, :-2]
            C = img[1:-1, 1:-1]
            B = (P2.astype(int) + P3 + P4 + P5 + P6 + P7 + P8 + P9)
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(int) for i in range(8))
            if step == 0:
                c1 = (P2 * P4 * P6) == 0
                c2 = (P4 * P6 * P8) == 0
            else:
                c1 = (P2 * P4 * P8) == 0
                c2 = (P2 * P6 * P8) == 0
            rm = (C == 1) & (B >= 2) & (B <= 6) & (A == 1) & c1 & c2
            if rm.any():
                img[1:-1, 1:-1][rm] = 0
                changed = True
        if not changed:
            break
    return img[1:-1, 1:-1].astype(bool)


def skeleton_tips(mask: np.ndarray, top_frac=0.85) -> int:
    sk = zhang_suen(mask)
    nb = ndimage.convolve(sk.astype(int), np.ones((3, 3), int), mode="constant") - sk
    ends = sk & (nb == 1)
    ys, xs = np.nonzero(ends)
    keep = ys < top_frac * mask.shape[0]
    pts = list(zip(ys[keep], xs[keep]))
    merged = []
    for p in pts:
        if all(max(abs(p[0] - q[0]), abs(p[1] - q[1])) > 1 for q in merged):
            merged.append(p)
    return len(merged)


def alpha_mips(a0: np.ndarray):
    out = [a0]
    a = a0
    for _ in range(MIP_LEVELS):
        h, w = a.shape[0] // 2, a.shape[1] // 2
        a = a.reshape(h, 2, w, 2).mean(axis=(1, 3))
        out.append(a)
    return out


def compute_gates(rgba: np.ndarray, cov: dict, meta: dict):
    lo, hi = PARAMS["clamp_srgb8"]
    a8 = rgba[..., 3]
    opaque = a8 >= 128
    rgb8 = rgba[..., :3]
    g2 = {"min_channel_opaque": int(rgb8[opaque].min()), "max_channel_opaque": int(rgb8[opaque].max()),
          "violations": int(((rgb8[opaque] < lo) | (rgb8[opaque] > hi)).any(axis=1).sum()),
          "limits": [lo, hi]}
    g2["pass"] = g2["violations"] == 0
    # palette bands over fully opaque bundle texels
    px = []
    for c in range(8):
        reg = rgba[0:512, 256 * c:256 * c + 256]
        px.append(reg[..., :3][reg[..., 3] == 255])
    px = np.concatenate(px).astype(np.float32)
    luma = px @ LUMA
    order = np.argsort(luma, kind="stable")
    bands = []
    for nm, b0, b1, target in (("p10-30", 10, 30, "#2a4a31"), ("p40-60", 40, 60, "#4d6a3c"),
                               ("p70-90", 70, 90, "#7a914c"), ("p90-98", 90, 98, "#9fb257")):
        i0, i1 = int(len(order) * b0 / 100), int(len(order) * b1 / 100)
        mean = px[order[i0:i1]].mean(0) / 255.0
        de = ciede2000(srgb_to_lab(mean), srgb_to_lab(hexc(target)))
        bands.append({"band": nm, "target": target, "measured": to_hex(mean), "dE2000": round(de, 2)})
    g3 = {"bands": bands, "max_dE2000": max(b["dE2000"] for b in bands), "aim": 10.0, "texels": int(len(px))}
    g3["pass"] = g3["max_dE2000"] <= 10.0
    # edge bleed: GPU-style unweighted box mips of the shipped RGBA; edge texel luminance vs opaque neighbours
    lin = srgb_to_linear(rgb8.astype(np.float32) / 255.0)
    a = a8.astype(np.float32) / 255.0
    per_mip = []
    for k in range(0, MIP_LEVELS + 1):
        if k > 0:
            lin, a = box_down(lin, a, weighted=False)
        lum = lin @ LUMA
        op = (a >= 0.5).astype(np.float32)
        ker = np.ones((3, 3), np.float32)
        ker[1, 1] = 0
        s_l = ndimage.convolve(lum * op, ker, mode="constant")
        s_n = ndimage.convolve(op, ker, mode="constant")
        edge = (a > 0.5 / 255) & (a < 254.5 / 255) & (s_n > 0)
        le = lum[edge]
        ln = s_l[edge] / s_n[edge]
        rel = abs(float(le.mean()) / float(ln.mean()) - 1.0)
        per_mip.append({"mip": k, "edge_texels": int(edge.sum()), "rel_diff_of_means": round(rel, 4),
                        "mean_abs_rel_diff": round(float(np.mean(np.abs(le / np.maximum(ln, 1e-6) - 1.0))), 4)})
    g4 = {"per_mip": per_mip, "max_rel_diff": max(m["rel_diff_of_means"] for m in per_mip), "limit": 0.06}
    g4["pass"] = g4["max_rel_diff"] <= 0.06
    # mip coverage after scaling
    worst = max(((cid, k + 1, abs(e)) for cid, c in cov.items() for k, e in enumerate(c["errs"])), key=lambda t: t[2])
    raw_worst = max(((cid, k + 1, abs(e)) for cid, c in cov.items() for k, e in enumerate(c["raw"])), key=lambda t: t[2])
    g5 = {"max_abs_err": round(worst[2], 5), "worst": [worst[0], worst[1]], "limit": 0.01,
          "unscaled_max_abs_err": round(raw_worst[2], 5), "unscaled_worst": [raw_worst[0], raw_worst[1]],
          "units": "fraction of the cell content box (percentage points / 100)"}
    g5["pass"] = g5["max_abs_err"] <= 0.01
    # mip-4 silhouettes of bundles
    tips = {}
    for c in range(8):
        cid = "B%d" % c
        cell_a = a[0:0] if False else None
        x, y, w, h = cell_rect(cid)
        a0 = rgba[y:y + h, x:x + w, 3].astype(np.float32) / 255.0
        m4 = alpha_mips(a0)[4] * cov[cid]["scales"][3] >= 0.5
        sk_tips = skeleton_tips(m4)
        known = 0
        hits = []
        for tx, ty in meta[cid]["tips_local"]:
            gx, gy = int(tx / 16), int(ty / 16)
            ok = m4[max(0, gy - 1):gy + 2, max(0, gx - 1):gx + 2].any()
            if ok and all(max(abs(gx - hx), abs(gy - hy)) > 1 for hx, hy in hits):
                hits.append((gx, gy))
        known = len(hits)
        tips[cid] = {"skeleton_tips": sk_tips, "distinct_known_tips": known}
    g6 = {"per_cell": tips, "min_skeleton_tips": min(v["skeleton_tips"] for v in tips.values()),
          "min_known_tips": min(v["distinct_known_tips"] for v in tips.values()), "required": 3}
    g6["pass"] = g6["min_skeleton_tips"] >= 3 and g6["min_known_tips"] >= 3
    # silhouettes: structure numbers (visual judgement is recorded in the critique)
    g1 = {"bundles": {cid: {k: meta[cid][k] for k in ("blade_count", "chord_deg_range", "length_frac_range",
                                                         "base_width_px_range", "root_x_offset_px", "kinds", "s_curves")}
                      for cid in ("B%d" % c for c in range(8))},
          "heads": {cid: {k: v for k, v in meta[cid].items() if k not in ("palette", "tips_local")}
                    for cid in ("F%d" % c for c in range(8))}}
    return {"g1_silhouettes": g1, "g2_value_range": g2, "g3_palette_bands": g3, "g4_edge_bleed": g4,
            "g5_mip_coverage": g5, "g6_mip4_tips": g6}


# --------------------------------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------------------------------
def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except Exception:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def labelled(img: np.ndarray, title: str, band=44) -> Image.Image:
    h, w = img.shape[:2]
    out = Image.new("RGB", (w, h + band), (18, 20, 18))
    out.paste(Image.fromarray(img), (0, band))
    d = ImageDraw.Draw(out)
    d.text((10, 6), PREVIEW_LABEL, fill=(240, 214, 120), font=_font(20))
    d.text((10, 26), title, fill=(200, 200, 190), font=_font(14))
    return out


def composite(rgba: np.ndarray, bg_hex: str) -> np.ndarray:
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    bg = hexc(bg_hex) * 255.0
    return np.clip(rgba[..., :3].astype(np.float32) * a + bg * (1 - a), 0, 255).round().astype(np.uint8)


def premul_resize(rgba: np.ndarray, size) -> np.ndarray:
    a = rgba[..., 3].astype(np.float32) / 255.0
    lin = srgb_to_linear(rgba[..., :3].astype(np.float32) / 255.0) * a[..., None]
    lin_r = cv2.resize(lin, size, interpolation=cv2.INTER_AREA)
    a_r = cv2.resize(a, size, interpolation=cv2.INTER_AREA)
    rgb = linear_to_srgb(lin_r / np.maximum(a_r, 1e-6)[..., None])
    return np.dstack([np.round(rgb * 255).astype(np.uint8), np.round(a_r * 255).astype(np.uint8)])


def display_mips(cell: np.ndarray):
    """Mips for display: alpha averaged, RGB alpha-weighted (linear)."""
    a = cell[..., 3].astype(np.float32) / 255.0
    lin = srgb_to_linear(cell[..., :3].astype(np.float32) / 255.0)
    out = [(linear_to_srgb(lin), a)]
    for _ in range(MIP_LEVELS):
        lin, a = box_down(lin, a, weighted=True)
        out.append((linear_to_srgb(lin), a))
    return out


def write_previews(rgba: np.ndarray, cov: dict, meta: dict, evdir: Path, seed: int):
    evdir.mkdir(parents=True, exist_ok=True)
    sub = f"grass_atlas_v1 seed {seed}  |  2048 x 1024 RGBA8, straight alpha"
    labelled(composite(rgba, "#2a3a22"), sub + "  |  over #2a3a22").save(evdir / "atlas-on-dark.png")
    labelled(composite(rgba, "#587036"), sub + "  |  over meadow ground #587036").save(evdir / "atlas-on-ground.png")
    # cells labelled at 50 %
    half = premul_resize(rgba, (ATLAS_W // 2, ATLAS_H // 2))
    img = Image.fromarray(composite(half, "#46503e"))
    d = ImageDraw.Draw(img)
    for cid, name, kind, view in CELL_DEFS:
        x, y, w, h = [v // 2 for v in cell_rect(cid)]
        d.rectangle([x, y, x + w - 1, y + h - 1], outline=(150, 150, 140))
        d.text((x + 4, y + 3), f"{cid} {name}", fill=(250, 240, 200), font=_font(12))
    labelled(np.asarray(img), "atlas at 50 % with cell ids / names (grey = transparent)").save(evdir / "cells-labelled.png")
    # mip strip: alpha-tested at 0.5 with each cell's coverage scale, nearest-upscaled to 128 px tall
    grey = np.array([118, 118, 118], np.uint8)
    panels = []
    for row in ("B", "F", "G"):
        tiles_rows = []
        for c in range(8):
            cid = f"{row}{c}"
            x, y, w, h = cell_rect(cid)
            mips = display_mips(rgba[y:y + h, x:x + w])
            col_tiles = []
            for k, (rgb, a) in enumerate(mips):
                s = 1.0 if k == 0 else cov[cid]["scales"][k - 1]
                m = np.minimum(1.0, a * s) >= 0.5
                t = np.where(m[..., None], np.round(rgb * 255).astype(np.uint8), grey)
                th = 128
                tw = int(round(th * t.shape[1] / t.shape[0]))
                col_tiles.append(cv2.resize(t, (tw, th), interpolation=cv2.INTER_NEAREST))
            gap = np.full((col_tiles[0].shape[0], 4, 3), 40, np.uint8)
            strip = np.concatenate(sum([[t, gap] for t in col_tiles], [])[:-1], axis=1)
            tiles_rows.append(strip)
        wmax = max(t.shape[1] for t in tiles_rows)
        rows = []
        for c, t in enumerate(tiles_rows):
            pad = np.full((t.shape[0], wmax - t.shape[1], 3), 40, np.uint8)
            lab = np.full((t.shape[0], 60, 3), 30, np.uint8)
            rows.append(np.concatenate([lab, t, pad], axis=1))
            rows.append(np.full((6, wmax + 60, 3), 30, np.uint8))
        panels.append(np.concatenate(rows, axis=0))
    wmax = max(p.shape[1] for p in panels)
    panels = [np.concatenate([p, np.full((p.shape[0], wmax - p.shape[1], 3), 30, np.uint8)], axis=1) for p in panels]
    strip = np.concatenate(panels, axis=0)
    img = Image.fromarray(strip)
    d = ImageDraw.Draw(img)
    yy = 0
    for row in ("B", "F", "G"):
        for c in range(8):
            d.text((6, yy + 54), f"{row}{c}", fill=(240, 230, 190), font=_font(16))
            yy += 134
    labelled(np.asarray(img), "mips 0..5 per cell (left to right), alpha-tested at 0.5 with the cell's coverage scale; "
                              "grey = rejected").save(evdir / "mip-strip.png")
    # game scale: bundle ~64 px tall, head ~12 px, over the meadow ground, 4x nearest
    ground = "#587036"
    row1, row2, row3 = [], [], []
    for c in range(8):
        x, y, w, h = cell_rect(f"B{c}")
        small = premul_resize(rgba[y:y + h, x:x + w], (32, 64))
        row1.append(np.pad(composite(small, ground), ((4, 4), (4, 4), (0, 0)), constant_values=0))
        mips = display_mips(rgba[y:y + h, x:x + w])
        rgb3, a3 = mips[3]
        m = np.minimum(1.0, a3 * cov[f"B{c}"]["scales"][2]) >= 0.5
        bg = hexc(ground) * 255
        t = np.where(m[..., None], np.round(rgb3 * 255), bg).astype(np.uint8)
        row2.append(np.pad(t, ((4, 4), (4, 4), (0, 0)), constant_values=0))
        x, y, w, h = cell_rect(f"F{c}")
        sm = premul_resize(rgba[y:y + h, x:x + w], (12, 12))
        row3.append(np.pad(composite(sm, ground), ((10, 10), (14, 14), (0, 0)), constant_values=0))
    def band(tiles):
        return np.concatenate([np.pad(t, ((0, 0), (0, 0), (0, 0))) for t in tiles], axis=1)
    b1, b2, b3 = band(row1), band(row2), band(row3)
    wmax = max(b.shape[1] for b in (b1, b2, b3))
    rows = [np.pad(b, ((0, 6), (0, wmax - b.shape[1]), (0, 0))) for b in (b1, b2, b3)]
    # a mock meadow patch: overlapping bundles with heads near the tips (game scale)
    patch = np.empty((80, wmax, 3), np.uint8)
    patch[:] = (hexc(ground) * 255).astype(np.uint8)
    prng = rng_for(seed, 999)
    for j in range(26):
        c = int(prng.integers(0, 8))
        x, y, w, h = cell_rect(f"B{c}")
        hh = int(prng.integers(46, 70))
        small = premul_resize(rgba[y:y + h, x:x + w], (hh // 2, hh))
        if prng.random() < 0.5:
            small = small[:, ::-1]
        px0 = int(prng.integers(0, wmax - hh // 2))
        py0 = 76 - hh
        reg = patch[py0:py0 + hh, px0:px0 + hh // 2]
        al = small[..., 3:4].astype(np.float32) / 255
        patch[py0:py0 + hh, px0:px0 + hh // 2] = np.round(small[..., :3] * al + reg * (1 - al)).astype(np.uint8)
    for j in range(10):
        c = int(prng.integers(0, 8))
        x, y, w, h = cell_rect(f"F{c}")
        sm = premul_resize(rgba[y:y + h, x:x + w], (11, 9))
        px0, py0 = int(prng.integers(0, wmax - 11)), int(prng.integers(14, 50))
        reg = patch[py0:py0 + 9, px0:px0 + 11]
        al = sm[..., 3:4].astype(np.float32) / 255
        patch[py0:py0 + 9, px0:px0 + 11] = np.round(sm[..., :3] * al + reg * (1 - al)).astype(np.uint8)
    rows.append(patch)
    gs = np.concatenate(rows, axis=0)
    gs = cv2.resize(gs, (gs.shape[1] * 4, gs.shape[0] * 4), interpolation=cv2.INTER_NEAREST)
    labelled(gs, "game scale (13 m camera), 4x nearest: row 1 bundles at 64 px blended | row 2 bundles at mip 3 "
                 "alpha-tested with coverage scale | row 3 heads at 12 px | row 4 mock patch").save(evdir / "game-scale.png")


# --------------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------------
def generate(seed: int, out_dir: Path, log=print):
    t0 = time.time()
    rgba, meta, fill = build_atlas(seed, log)
    cov = {}
    for cid, name, kind, view in CELL_DEFS:
        x, y, w, h = cell_rect(cid)
        (cx0, cy0, cx1, cy1), circ = cell_local_content(cid, view)
        area = float(content_mask(cid, view).sum()) if circ else float((cx1 - cx0) * (cy1 - cy0))
        a0 = rgba[y:y + h, x:x + w, 3].astype(np.float32) / 255.0
        if kind == "reserved":
            cov[cid] = {"c0": 0.0, "scales": [1.0] * MIP_LEVELS, "errs": [0.0] * MIP_LEVELS,
                        "raw": [0.0] * MIP_LEVELS, "k": 0.0}
            continue
        c0, scales, errs, raw, kfit = coverage_scales(a0, area)
        cov[cid] = {"c0": c0, "scales": scales, "errs": errs, "raw": raw, "k": kfit}
    half = build_half(rgba, {cid: c["scales"][0] for cid, c in cov.items()}, fill)
    full_png, half_png = png_bytes(rgba), png_bytes(half)
    outputs = {FULL_NAME: {"sha256": sha256(full_png), "bytes": len(full_png)},
               HALF_NAME: {"sha256": sha256(half_png), "bytes": len(half_png)}}
    script_sha = sha256(HERE.read_bytes())
    manifest = build_manifest(seed, rgba, meta, cov, outputs, script_sha)
    js = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / FULL_NAME).write_bytes(full_png)
    (out_dir / HALF_NAME).write_bytes(half_png)
    (out_dir / JSON_NAME).write_bytes(js)
    hashes = {FULL_NAME: sha256(full_png), HALF_NAME: sha256(half_png), JSON_NAME: sha256(js)}
    log(f"  wrote outputs in {time.time() - t0:.1f}s")
    return rgba, half, meta, cov, manifest, hashes


def determinism_check(seed: int, hashes: dict):
    with tempfile.TemporaryDirectory(prefix="grass_forge_") as tmp:
        cmd = [sys.executable, str(HERE), "--seed", str(seed), "--out-dir", tmp, "--no-previews", "--quiet"]
        subprocess.run(cmd, check=True, cwd=str(ROOT))
        other = {name: sha256((Path(tmp) / name).read_bytes()) for name in hashes}
    return {"run_a": hashes, "run_b": other, "identical": other == hashes, "method": "second process, same seed"}


def update_review(evdir: Path, pass_no: int, seed: int, hashes: dict, gates: dict, script_sha: str):
    path = evdir / REVIEW_NAME
    doc = {}
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
    doc.setdefault("schema", "xexoria.grass-forge-review/1")
    doc["subject"] = f"{OUT_DIR_REL}/{FULL_NAME} (+ half atlas, manifest)"
    doc["label"] = PREVIEW_LABEL
    doc["generator"] = SCRIPT_REL
    passes = doc.setdefault("passes", [])
    entry = next((p for p in passes if p.get("pass") == pass_no), None)
    if entry is None:
        entry = {"pass": pass_no}
        passes.append(entry)
        passes.sort(key=lambda p: p["pass"])
    entry.update({"seed": seed, "script_sha256": script_sha, "outputs_sha256": hashes, "gates": gates})
    entry.setdefault("critique", [])
    entry.setdefault("fixed_next", [])
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Seeded procedural grass / flower / clover atlas (grass_atlas_v1).")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--evidence-dir", default=str(EVIDENCE_DIR))
    ap.add_argument("--no-previews", action="store_true")
    ap.add_argument("--review-pass", type=int, default=0, help="record the measured gates as pass N in forge-review.json")
    ap.add_argument("--verify-determinism", action="store_true", help="re-run in a second process and compare hashes")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    log = (lambda *a, **k: None) if args.quiet else print
    t0 = time.time()
    rgba, half, meta, cov, manifest, hashes = generate(args.seed, Path(args.out_dir), log)
    if args.quiet:
        return 0
    gates = compute_gates(rgba, cov, meta)
    if args.verify_determinism:
        gates["g7_determinism"] = determinism_check(args.seed, hashes)
    evdir = Path(args.evidence_dir)
    if not args.no_previews:
        write_previews(rgba, cov, meta, evdir, args.seed)
        log(f"  previews in {evdir}")
    if args.review_pass:
        update_review(evdir, args.review_pass, args.seed, hashes, gates, manifest["generator"]["sha256"])
    for name, h in hashes.items():
        log(f"  {name}: {h}")
    log("  g2 value range:", {k: gates["g2_value_range"][k] for k in ("min_channel_opaque", "max_channel_opaque", "violations")})
    log("  g3 bands:", [(b["band"], b["measured"], b["dE2000"]) for b in gates["g3_palette_bands"]["bands"]])
    log("  g4 edge bleed:", [(m["mip"], m["rel_diff_of_means"]) for m in gates["g4_edge_bleed"]["per_mip"]])
    log("  g5 mip coverage max err:", gates["g5_mip_coverage"]["max_abs_err"], gates["g5_mip_coverage"]["worst"],
        "unscaled", gates["g5_mip_coverage"]["unscaled_max_abs_err"])
    log("  g6 mip-4 tips:", {k: (v["skeleton_tips"], v["distinct_known_tips"]) for k, v in gates["g6_mip4_tips"]["per_cell"].items()})
    if "g7_determinism" in gates:
        log("  g7 determinism identical:", gates["g7_determinism"]["identical"])
    log(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
