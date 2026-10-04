"""Painted flora atlases (system Python, numpy + scipy + Pillow): sm_flora_water (lily pads, lotus leaf, lotus
petals pink/white, seed pod, stamens, stems, cattail, four reed/sedge cards).

  python np_paint_flora.py --atlas water [--out DIR]

Everything is drawn from signed distances with 1.5 px anti-aliasing, then layered: base colour ramps, large
light/dark gradients (form), painted occlusion (bases, vein grooves, notch, card bottoms), edge highlights
(rims, midribs), hue/value noise, story marks (spots, dry tips, bloom, wet card base). A height field drawn at
the same time becomes the OpenGL (+Y) normal map. ORM: R = 1 (occlusion is painted), G = roughness, B = 0.
RGB under transparent texels is dilated from the nearest opaque texel (no dark mip halos).
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))


import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import flora_layout as FL  # noqa: E402
import np_noise as NZ  # noqa: E402
from np_paint import hexrgb, dilate_fill  # noqa: E402

CACHE = Path(os.environ.get("NP_CACHE", str(_XEXORIA_AGENT_OUTPUT / '20261002-sunmeadow-props/cache')))


def ss(a, b, x):
    return NZ.smoothstep(a, b, x)


class Canvas:
    def __init__(self, size):
        self.S = size
        self.rgb = np.zeros((size, size, 3))
        self.a = np.zeros((size, size))
        self.h = np.zeros((size, size))
        self.r = np.full((size, size), 0.7)

    def cell(self, rect):
        x, y, w, h = rect
        ys, xs = np.mgrid[y:y + h, x:x + w].astype(np.float64)
        return (slice(y, y + h), slice(x, x + w)), xs - x + 0.5, ys - y + 0.5, w, h

    def put(self, sl, rgb, a, h=None, r=None, mode="over"):
        """Composite rgb/alpha into the cell (over operator, alpha straight)."""
        A0 = self.a[sl]
        if mode == "over":
            out_a = a + A0 * (1 - a)
            w = np.where(out_a > 1e-6, a / np.maximum(out_a, 1e-6), 0)
            self.rgb[sl] = self.rgb[sl] * (1 - w[..., None]) + rgb * w[..., None]
            self.a[sl] = out_a
        if h is not None:
            self.h[sl] = np.where(a > 0.01, np.maximum(self.h[sl] * (1 - a), h * a + self.h[sl] * (1 - a)), self.h[sl])
        if r is not None:
            self.r[sl] = np.where(a > 0.5, r, self.r[sl])


def noise2(xs, ys, scale, seed, octaves=3):
    p = np.stack([xs.ravel() / scale, ys.ravel() / scale, np.full(xs.size, seed * 0.173)], 1)
    return NZ.fbm3(p, seed, octaves).reshape(xs.shape)


def ramp3(t, stops):
    pos = np.array([p for p, _ in stops])
    cols = np.stack([hexrgb(c) for _, c in stops])
    t = np.clip(t, 0, 1)
    return np.stack([np.interp(t, pos, cols[:, k]) for k in range(3)], -1)


# --------------------------------------------------------------------------------------------- lily pad

PAD_STYLES = {
    "pad_a": dict(stops=[(0, "#34562b"), (0.45, "#4f7a3a"), (0.8, "#7fae4f"), (1, "#9cc25e")],
                  rim="#a9c86a", vein="#93bd5c", spots=0.10, spot_col="#6b6a2c", red=0.0, seed=11),
    "pad_b": dict(stops=[(0, "#4e6a26"), (0.45, "#6f8f35"), (0.8, "#90a948"), (1, "#b2bf63")],
                  rim="#c2c470", vein="#a9bb62", spots=0.35, spot_col="#7f5e2e", red=0.0, seed=12),
    "pad_c": dict(stops=[(0, "#3b5f27"), (0.45, "#557f35"), (0.8, "#6f9a44"), (1, "#8fb35a")],
                  rim="#9a5a45", vein="#86ad58", spots=0.18, spot_col="#6e3f30", red=0.55, seed=13),
}


def paint_pad(cv, rect, st, notch_deg=28.0):
    sl, xs, ys, w, h = cv.cell(rect)
    cx, cy, R = w / 2, h / 2, 0.47 * w
    dx, dy = xs - cx, -(ys - cy)          # y up
    r = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)               # notch at angle 0 (+U)
    edge_wave = 1.0 + 0.018 * np.sin(th * 7 + st["seed"]) + 0.012 * np.sin(th * 13 + 1.3)
    rr = r / (R * edge_wave)
    half = math.radians(notch_deg) / 2
    # notch: wedge from the centre, slightly curved sides
    ang = np.abs(np.angle(np.exp(1j * th)))
    notch_d = (ang - half * (0.25 + 0.75 * np.clip(rr, 0, 1))) * r      # px distance to the notch edge (approx)
    disc_d = (1 - rr) * R
    d = np.minimum(disc_d, notch_d)
    a = ss(-0.75, 0.75, d)
    t = np.clip(rr, 0, 1)
    n1 = noise2(xs, ys, 22.0, st["seed"], 3)
    n2 = noise2(xs, ys, 6.0, st["seed"] + 5, 2)
    base = ramp3(0.55 + 0.25 * (1 - t) - 0.18 * t ** 3 + 0.18 * n1 + 0.06 * n2, st["stops"])
    # radial veins
    nv = 19
    vein = np.zeros_like(r)
    for k in range(nv):
        a0 = half + (2 * math.pi - 2 * half) * (k + 0.5) / nv + 0.05 * math.sin(k * 2.1 + st["seed"])
        curve = a0 + 0.10 * np.sin(rr * 3.0 + k)
        dd = np.abs(np.angle(np.exp(1j * (th - curve)))) * np.maximum(r, 1)
        vein = np.maximum(vein, np.exp(-(dd / (0.9 + 0.8 * t)) ** 2) * ss(0.08, 0.25, t) * (1 - ss(0.85, 0.98, t)))
    col = base * (1 - 0.0) + (hexrgb(st["vein"]) - base) * (0.55 * vein)[..., None]
    # rim highlight + dark ring inside the upturned rim + red rim variant
    rim = ss(0.86, 0.97, t) * (1 - ss(0.985, 1.0, t))
    ring = ss(0.72, 0.86, t) * (1 - ss(0.86, 0.93, t))
    col = col * (1 - 0.16 * ring)[..., None]
    col = col + (hexrgb(st["rim"]) - col) * (0.55 * rim)[..., None]
    if st["red"] > 0:
        rb = ss(0.80, 0.99, t) * (0.6 + 0.4 * n1)
        col = col + (hexrgb(st["rim"]) - col) * (st["red"] * rb)[..., None]
    # notch shadow
    col = col * (1 - 0.22 * np.exp(-(np.maximum(notch_d, 0) / 6.0) ** 2) * (t > 0.05))[..., None]
    # spots (age marks)
    f1, _, cid = NZ.worley3(np.stack([xs.ravel() / 14.0, ys.ravel() / 14.0, np.full(xs.size, 0.37)], 1), st["seed"] + 9)
    f1 = f1.reshape(xs.shape)
    pick = (NZ.hash01(cid.astype(np.int64), st["seed"]) < st["spots"]).reshape(xs.shape)
    spot = (1 - ss(0.15, 0.42, f1)) * pick * ss(0.3, 0.9, t)
    col = col + (hexrgb(st["spot_col"]) - col) * (0.6 * spot)[..., None]
    # top light: subtle radial gradient toward the upper-left (painted sun side)
    col = col * (1 + 0.07 * ((-dx + dy) / (R * 1.4)))[..., None]
    height = 0.35 * vein + 0.5 * rim - 0.2 * ring + 0.03 * n2
    cv.put(sl, np.clip(col, 0.035, 0.93), a, h=height, r=0.36 + 0.08 * rim + 0.05 * spot)


def paint_lotus_leaf(cv, rect, seed=21):
    sl, xs, ys, w, h = cv.cell(rect)
    cx, cy, R = w / 2, h / 2, 0.47 * w
    dx, dy = xs - cx, -(ys - cy)
    r = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)
    wave = 1.0 + 0.03 * np.sin(th * 9 + 0.4) + 0.015 * np.sin(th * 17)
    rr = r / (R * wave)
    a = ss(-0.75, 0.75, (1 - rr) * R)
    t = np.clip(rr, 0, 1)
    n1 = noise2(xs, ys, 26.0, seed, 3)
    stops = [(0, "#37573a"), (0.4, "#4f7a4f"), (0.75, "#6c9a63"), (1, "#8fb58a")]
    col = ramp3(0.5 + 0.22 * (1 - t) + 0.2 * n1, stops)
    vein = np.zeros_like(r)
    for k in range(22):
        a0 = 2 * math.pi * k / 22 + 0.08 * math.sin(k * 1.7)
        dd = np.abs(np.angle(np.exp(1j * (th - a0 - 0.06 * np.sin(rr * 4 + k))))) * np.maximum(r, 1)
        vein = np.maximum(vein, np.exp(-(dd / (0.8 + t)) ** 2) * ss(0.06, 0.2, t) * (1 - ss(0.9, 1.0, t)))
    col = col + (hexrgb("#a9c7a0") - col) * (0.5 * vein)[..., None]
    bloom = ss(0.15, 0.6, noise2(xs, ys, 40.0, seed + 3, 2)) * 0.35
    col = col + (hexrgb("#a7bfae") - col) * bloom[..., None]
    centre = np.exp(-(r / (0.09 * R)) ** 2)
    col = col + (hexrgb("#b9c98e") - col) * (0.7 * centre)[..., None]
    rim = ss(0.9, 0.99, t)
    col = col * (1 - 0.18 * rim)[..., None]
    height = 0.3 * vein - 0.4 * centre + 0.2 * rim
    cv.put(sl, np.clip(col, 0.035, 0.93), a, h=height, r=0.48 + 0.1 * bloom)


# --------------------------------------------------------------------------------------------- petals

PETALS = {
    "petal_pink_outer": [(0, "#b86185"), (0.10, "#d783a4"), (0.45, "#f2a7c3"), (0.80, "#f3d1df"), (1, "#f5e8ed")],
    "petal_pink_inner": [(0, "#d0789c"), (0.25, "#eda2bf"), (0.6, "#f2bfd3"), (0.88, "#f5dbe5"), (1, "#f6ecef")],
    "petal_white_outer": [(0, "#dde2bf"), (0.12, "#f1efdf"), (0.5, "#fbf7ef"), (0.85, "#f7e6e9"), (1, "#f0d2da")],
    "petal_white_inner": [(0, "#f6f3e4"), (0.3, "#fffaf2"), (0.75, "#fbf2f0"), (1, "#f4dfe4")],
}


def paint_petal(cv, rect, stops, seed):
    sl, xs, ys, w, h = cv.cell(rect)
    u = (xs - w / 2) / (w / 2 * 0.98)          # -1..1 across
    v = 1.0 - ys / h                            # 0 base (bottom) .. 1 tip (top)
    vv = np.clip((v - 0.015) / 0.97, 0, 1)
    hw = 0.93 * np.sin(np.pi * np.clip(vv, 0, 1) ** 0.78) ** 0.8 * (1 - 0.1 * vv)
    d = (hw - np.abs(u)) * (w / 2)
    a = ss(-0.75, 0.75, d) * (vv > 0) * (vv < 1)
    n1 = noise2(xs, ys, 18.0, seed, 3)
    t = vv + 0.05 * n1 + 0.06 * np.abs(u) ** 2
    col = ramp3(t, stops)
    veins = (0.5 + 0.5 * np.cos(u * np.pi * 7.5 + 0.6 * np.sin(vv * 5))) ** 6 * ss(0.05, 0.3, vv)
    col = col * (1 - 0.06 * veins)[..., None]
    # form: lighter keel, slightly more saturated edges, darker base (painted occlusion)
    keel = np.exp(-(u / 0.35) ** 2)
    col = col * (1 + 0.05 * keel - 0.05 * np.abs(u) ** 3)[..., None]
    col = col * (1 - 0.18 * (1 - ss(0.0, 0.16, vv)))[..., None]
    # edge highlight along the rim
    rimh = np.exp(-(np.maximum(d, 0) / 2.2) ** 2) * (vv > 0.15)
    col = col + (np.array([1.0, 0.97, 0.96]) - col) * (0.18 * rimh)[..., None]
    height = 0.25 * keel + 0.12 * veins
    cv.put(sl, np.clip(col, 0.035, 0.93), a, h=height, r=0.55)


def paint_pod(cv, rect_top, rect_side, rect_stam, seed=31):
    sl, xs, ys, w, h = cv.cell(rect_top)
    cx, cy, R = w / 2, h / 2, 0.46 * w
    r = np.hypot(xs - cx, ys - cy)
    a = ss(-0.75, 0.75, R - r)
    t = r / R
    col = ramp3(0.75 - 0.35 * t + 0.1 * noise2(xs, ys, 9, seed, 2),
                [(0, "#8e8a2c"), (0.5, "#b6b143"), (1, "#d7d06a")])
    holes = np.zeros_like(r)
    for k in range(13):
        if k == 0:
            hx, hy = cx, cy
        else:
            ang = 2 * math.pi * (k - 1) / 12 + 0.2
            rad = R * (0.38 if k <= 6 else 0.68)
            ang = ang * (1 if k <= 6 else 1) + (0.26 if k > 6 else 0)
            hx, hy = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
        holes = np.maximum(holes, 1 - ss(3.0, 5.5, np.hypot(xs - hx, ys - hy)))
    col = col + (hexrgb("#5e5a22") - col) * (0.85 * holes)[..., None]
    col = col * (1 - 0.22 * ss(0.85, 1.0, t))[..., None]
    cv.put(sl, np.clip(col, 0.035, 0.93), a, h=-0.6 * holes + 0.2 * (1 - t), r=0.62)
    # side strip
    sl, xs, ys, w, h = cv.cell(rect_side)
    v = 1 - ys / h
    col = ramp3(0.25 + 0.6 * v + 0.08 * noise2(xs, ys, 7, seed + 1, 2), [(0, "#6f7a2c"), (0.6, "#9da63c"), (1, "#c7c25a")])
    cv.put(sl, np.clip(col, 0.035, 0.93), np.ones_like(v), h=0.1 * v, r=0.62)
    # stamen fringe (alpha)
    sl, xs, ys, w, h = cv.cell(rect_stam)
    v = 1 - ys / h
    fil = np.zeros_like(v)
    tipm = np.zeros_like(v)
    rng = np.random.default_rng(seed)
    for k in range(70):
        x0 = rng.uniform(0, w)
        top = rng.uniform(0.62, 0.98)
        bend = rng.uniform(-4, 4)
        xc = x0 + bend * v ** 2
        dd = np.abs(xs - xc)
        on = (v < top) & (v > 0.0)
        fil = np.maximum(fil, (1 - ss(0.6, 1.6, dd)) * on)
        tipm = np.maximum(tipm, (1 - ss(1.0, 2.6, np.hypot(xs - xc, (v - top) * h))) * (v <= top + 0.03))
    a = np.clip(np.maximum(fil, tipm), 0, 1)
    col = ramp3(0.3 + 0.6 * v, [(0, "#d9a33c"), (0.6, "#efc64e"), (1, "#f7dc77")])
    col = col + (hexrgb("#e09a35") - col) * (0.7 * tipm)[..., None]
    cv.put(sl, np.clip(col, 0.035, 0.93), a, h=0.3 * a, r=0.7)


def paint_stem(cv, rect, stops, seed, prickles=True):
    sl, xs, ys, w, h = cv.cell(rect)
    v = ys / h                                  # around the stem
    shade = 0.5 + 0.5 * np.cos((v - 0.35) * 2 * np.pi)
    col = ramp3(0.25 + 0.6 * shade + 0.08 * noise2(xs * 0.2, ys, 6, seed, 2), stops)
    streak = (0.5 + 0.5 * np.sin(ys * 1.9 + 3 * noise2(xs, ys, 30, seed + 1, 2))) ** 8
    col = col * (1 - 0.08 * streak)[..., None]
    if prickles:
        f1, _, cid = NZ.worley3(np.stack([xs.ravel() / 9.0, ys.ravel() / 9.0, np.full(xs.size, 0.71)], 1), seed + 3)
        dots = (1 - ss(0.08, 0.25, f1.reshape(xs.shape))) * (NZ.hash01(cid.astype(np.int64), seed).reshape(xs.shape) < 0.4)
        col = col * (1 - 0.25 * dots)[..., None]
    cv.put(sl, np.clip(col, 0.035, 0.93), np.ones_like(v), h=0.15 * shade, r=0.6)


def paint_cattail(cv, rect, seed=41):
    sl, xs, ys, w, h = cv.cell(rect)
    v = 1 - ys / h
    around = xs / w
    shade = 0.5 + 0.5 * np.cos((around - 0.3) * 2 * np.pi)
    fuzz = noise2(xs, ys * 0.5, 2.2, seed, 2)
    col = ramp3(0.2 + 0.55 * shade + 0.12 * fuzz + 0.1 * ss(0.85, 1.0, v),
                [(0, "#3c2616"), (0.4, "#5a3a22"), (0.75, "#7a5232"), (1, "#9a7047")])
    col = col * (1 - 0.3 * (1 - ss(0.0, 0.08, v)) - 0.25 * ss(0.94, 1.0, v))[..., None]
    cv.put(sl, np.clip(col, 0.035, 0.93), np.ones_like(v), h=0.25 * fuzz, r=0.92)


# --------------------------------------------------------------------------------------------- blade cards

BLADE_STYLES = {
    "reeds_tall": dict(n=9, h=(0.72, 0.99), w=(9, 14), bend=(-0.18, 0.18), spread=(0.30, 0.70), curl=0.25,
                       stops=[(0, "#4f5b25"), (0.35, "#6d8833"), (0.75, "#90aa45"), (1, "#b4bc62")], dry=0.3, seed=51),
    "reeds_sedge": dict(n=6, h=(0.55, 0.85), w=(16, 24), bend=(-0.45, 0.45), spread=(0.36, 0.64), curl=0.7,
                        stops=[(0, "#3c5420"), (0.4, "#557a2b"), (0.8, "#79a03d"), (1, "#9cbc58")], dry=0.15, seed=52),
    "reeds_short": dict(n=13, h=(0.30, 0.58), w=(7, 11), bend=(-0.35, 0.35), spread=(0.22, 0.78), curl=0.55,
                        stops=[(0, "#4b5a24"), (0.4, "#6a8a32"), (0.8, "#8eae46"), (1, "#b2c463")], dry=0.2, seed=53),
    "reeds_mixed": dict(n=8, h=(0.6, 0.95), w=(9, 15), bend=(-0.3, 0.3), spread=(0.3, 0.7), curl=0.4,
                        stops=[(0, "#4d5824"), (0.4, "#6b8632"), (0.8, "#8eaa45"), (1, "#aeb860")], dry=0.35, seed=54,
                        stems=2),
}


def blade_layer(xs, ys, w, h, x0, top, width, bend, curl, seed):
    """Distance field of one tapered curved blade growing from (x0, bottom)."""
    v = 1 - ys / h                                  # 0 bottom .. 1 top of the card
    s = np.clip(v / max(top, 1e-3), 0, 1.0)         # position along the blade
    xc = x0 + bend * w * (s ** 1.6) + curl * bend * w * 0.25 * s ** 3
    half = 0.5 * width * (1 - s) ** 0.75 + 0.5
    d = half - np.abs(xs - xc)
    inside_len = (v <= top) & (v >= 0)
    tip = np.hypot(xs - (x0 + bend * w + curl * bend * w * 0.25), (v - top) * h)
    d = np.where(inside_len, d, np.minimum(d, 1.0 - tip))
    across = np.clip((xs - xc) / np.maximum(half, 0.6), -1, 1)
    return d, s, across


def paint_blades(cv, rect, st):
    sl, xs, ys, w, h = cv.cell(rect)
    rng = np.random.default_rng(st["seed"])
    rgb = np.zeros((h, w, 3))
    al = np.zeros((h, w))
    hh = np.zeros((h, w))
    order = sorted(range(st["n"]), key=lambda i: rng.random())
    for k in range(st["n"] + st.get("stems", 0)):
        is_stem = k >= st["n"]
        x0 = w * rng.uniform(*st["spread"])
        top = rng.uniform(*st["h"]) if not is_stem else rng.uniform(0.82, 0.97)
        width = rng.uniform(*st["w"]) if not is_stem else 4.0
        bend = rng.uniform(*st["bend"]) if not is_stem else rng.uniform(-0.04, 0.04)
        d, s, across = blade_layer(xs, ys, w, h, x0, top, width, bend, st["curl"] if not is_stem else 0.0, st["seed"] + k)
        a = ss(-0.6, 0.9, d)
        n1 = noise2(xs, ys, 30.0, st["seed"] + k, 2)
        t = 0.15 + 0.8 * s + 0.08 * n1 - 0.08 * (k % 3 == 0)
        col = ramp3(t, st["stops"] if not is_stem else [(0, "#5c6a2c"), (1, "#8d9a48")])
        # rounded blade: light midrib, darker edges; sun side lighter
        col = col * (1 + 0.10 * np.exp(-(across / 0.25) ** 2) - 0.14 * np.abs(across) ** 2 + 0.05 * across)[..., None]
        if not is_stem and rng.random() < st["dry"]:
            dry = ss(0.72, 0.95, s)
            col = col + (hexrgb("#a0804a") - col) * (0.8 * dry)[..., None]
        # painted occlusion at the clump base
        col = col * (1 - 0.35 * (1 - ss(0.0, 0.22, 1 - ys / h)))[..., None]
        over = a + al * (1 - a)
        wgt = np.where(over > 1e-6, a / np.maximum(over, 1e-6), 0)
        rgb = rgb * (1 - wgt[..., None]) + col * wgt[..., None]
        hh = np.where(a > 0.3, (1 - across ** 2) * 0.6, hh)
        al = over
    # wet band at the card base (sits in the water edge)
    v = 1 - ys / h
    rgb = rgb * (1 - 0.25 * (1 - ss(0.0, 0.06, v)))[..., None]
    # thicken alpha a little so blades survive lower mips
    al = np.clip(al * 1.08, 0, 1)
    cv.put(sl, np.clip(rgb, 0.035, 0.93), al, h=hh, r=0.72)


# --------------------------------------------------------------------------------------------- output

def height_to_normal(h, strength):
    gy, gx = np.gradient(h)
    nx, ny = -gx * strength, gy * strength
    n = np.stack([nx, ny, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def save(cv, out, name, normal_px=512, orm_px=256):
    out.mkdir(parents=True, exist_ok=True)
    mask = cv.a > 0.5
    rgb = dilate_fill(cv.rgb, mask)
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.clip(cv.a, 0, 1)[..., None]], -1)
    p_alb = out / f"{name}_albedo.png"
    Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA").save(p_alb, optimize=True)
    hsm = ndimage.gaussian_filter(cv.h, 0.8)
    nrm = height_to_normal(hsm, 2.2)
    nrm = dilate_fill(nrm, cv.a > 0.05)
    img = Image.fromarray(np.round(nrm * 255).astype(np.uint8), "RGB").resize((normal_px, normal_px), Image.LANCZOS)
    p_n = out / f"{name}_normal.png"
    img.save(p_n, optimize=True)
    r = dilate_fill(cv.r, mask)
    orm = np.stack([np.ones_like(r), r, np.zeros_like(r)], -1)
    p_o = out / f"{name}_orm.png"
    Image.fromarray(np.round(orm * 255).astype(np.uint8), "RGB").resize((orm_px, orm_px), Image.BILINEAR).save(p_o, optimize=True)
    print(f"[paint_flora] {name}: albedo {cv.S}px RGBA, normal {normal_px}, orm {orm_px}; opaque {mask.mean():.1%}")
    return {"albedo": str(p_alb), "normal": str(p_n), "orm": str(p_o)}


def paint_water(out):
    L = FL.WATER
    cv = Canvas(L["size"])
    R = L["rects"]
    for k in ("pad_a", "pad_b", "pad_c"):
        paint_pad(cv, R[k], PAD_STYLES[k])
    paint_lotus_leaf(cv, R["lotus_leaf"])
    for i, (k, stops) in enumerate(PETALS.items()):
        paint_petal(cv, R[k], stops, 60 + i)
    paint_pod(cv, R["pod_top"], R["pod_side"], R["stamens"])
    paint_stem(cv, R["stem"], [(0, "#3f5a26"), (0.6, "#5f7f36"), (1, "#86a14d")], 71, prickles=True)
    paint_stem(cv, R["stem_reed"], [(0, "#566328"), (0.6, "#7a8b3e"), (1, "#a1ad5a")], 72, prickles=False)
    paint_cattail(cv, R["cattail"])
    for k in ("reeds_tall", "reeds_sedge", "reeds_short", "reeds_mixed"):
        paint_blades(cv, R[k], BLADE_STYLES[k])
    return save(cv, out, L["id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atlas", default="water")
    ap.add_argument("--out", default=str(CACHE / "flora" / "tex"))
    a = ap.parse_args()
    out = Path(a.out)
    if a.atlas == "water":
        paint_water(out)
    elif a.atlas == "meadow":
        import np_paint_meadow as M
        M.paint_meadow(out)


if __name__ == "__main__":
    main()
