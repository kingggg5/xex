"""Forge R7 composite: paint, grade and gate the terrain layers from the Blender data passes.

Input: <passes>/<layer>_{albedo,height,ao,edge,id,normal}.npy written by
assets/blender/city_r5/forge/forge_terrain_r7.py (row 0 = image top = tile +Y = world +Z).
Output (spec §3.3, §6 script 1): assets/models/sunmeadow-v2/terrain/layers-r7/
    <name>_albedo.png  sRGB 8-bit RGB          <name>_normal.png  OpenGL +Y, 8-bit RGB
    <name>_orm.png     R AO, G rough, B metal 0  <name>_height.png  16-bit linear, percentile-normalised
    forge-manifest.json, layer-stats.json
Runs in Blender's Python (called by the forge) or standalone for tuning without re-rendering:
    python assets/blender/sunmeadow_v2/terrain/terrain_forge_composite.py --passes <dir> [--only L0]

Style (llm.txt LOOK TARGET): the style lives in the albedo - base, a non-directional top-light gradient,
painted cavity, crisp edge highlights, hue/value variation and story marks. No directional light is painted,
so tile rotation stays valid. Normals are derived from the metre heightfield (normal and height agree).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import terrain_png  # noqa: E402
import terrain_spec as TS  # noqa: E402
import terrain_stats as ST  # noqa: E402

ROOT = TS.ROOT
# Raw forge passes are agent output, not repo content (llm.txt: Downloads/Xexoria-Game/agent-output/<date>-<topic>/).
DEFAULT_PASSES = Path.home() / 'Downloads' / 'Xexoria-Game' / 'agent-output' / '20261002-map-terrain' / 'forge-r7-passes'


def rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


K = dict(soil=0.0, turf=0.2, leaf=0.3, flat=0.4, wood=0.5, stone=0.6, moss=0.8, blade=1.0)


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def hexlin(value: str) -> np.ndarray:
    value = value.lstrip('#')
    return srgb_to_linear(np.array([int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]))


def smoothstep(a, b, x):
    """GLSL smoothstep; reversed edges (a > b) give the falling ramp, as in GLSL."""
    span = b - a
    if abs(span) < 1e-12:
        span = 1e-12
    t = np.clip((x - a) / span, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def pnoise(size: int, feature_px: float, seed: int, octaves=1, persistence=0.5) -> np.ndarray:
    """Same periodic FFT noise as forge_textures_r6.pnoise (kept here so the composite needs no Blender)."""
    rng = np.random.default_rng(seed)
    total = np.zeros((size, size), np.float64)
    amp, weight = 1.0, 0.0
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.rfftfreq(size)[None, :]
    radius = np.sqrt(fx * fx + fy * fy)
    for octave in range(octaves):
        sigma = 1.0 / max(1.0, feature_px / (2 ** octave))
        spectrum = np.fft.rfft2(rng.standard_normal((size, size)))
        layer = np.fft.irfft2(spectrum * np.exp(-(radius / sigma) ** 2), s=(size, size))
        layer /= max(1e-9, float(layer.std()))
        total += layer * amp
        weight += amp
        amp *= persistence
    total /= weight
    lo, hi = np.percentile(total, 1), np.percentile(total, 99)
    return np.clip((total - lo) / max(1e-9, hi - lo), 0.0, 1.0)


def kind_mask(ident: np.ndarray, value: float, tol=0.05) -> np.ndarray:
    return (np.abs(ident[..., 1] - value) < tol).astype(np.float64)


def lum_srgb(rgb):
    return (rgb * ST.LUMA).sum(-1)


def soft_range(x, lo=0.045, hi=0.885, k=0.03):
    """Smooth max/min knees so albedo never hits pure black/white (p0.1 >= 0.04, p99.9 <= 0.90), no flat clipping."""
    y = 0.5 * (x + lo + np.sqrt((x - lo) ** 2 + k * k))
    return 0.5 * (y + hi - np.sqrt((y - hi) ** 2 + k * k))


def grade(rgb_srgb: np.ndarray, lum_target: float, sat_target: float | None, sat_max: float | None = None):
    """Uniform saturation then value correction toward the spec's layer means (records the factors)."""
    rgb = np.clip(rgb_srgb, 0, 1)
    s_factor = 1.0
    if sat_target is not None or sat_max is not None:
        goal = sat_target if sat_target is not None else min(sat_max * 0.85, float(ST.rgb_to_saturation(rgb).mean()))
        lo, hi = 0.3, 2.0
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            lum = lum_srgb(rgb)[..., None]
            test = np.clip(lum + (rgb - lum) * mid, 0, 1)
            if ST.rgb_to_saturation(test).mean() < goal:
                lo = mid
            else:
                hi = mid
        s_factor = 0.5 * (lo + hi)
        lum = lum_srgb(rgb)[..., None]
        rgb = np.clip(lum + (rgb - lum) * s_factor, 0, 1)
    lin = srgb_to_linear(rgb)
    lo, hi = 0.3, 3.0
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if lum_srgb(soft_range(linear_to_srgb(lin * mid))).mean() < lum_target:
            lo = mid
        else:
            hi = mid
    v_factor = 0.5 * (lo + hi)
    out = soft_range(linear_to_srgb(lin * v_factor))
    return out, dict(saturation=round(s_factor, 4), value=round(v_factor, 4))


def tone_fit(srgb: np.ndarray, p2_min: float, p98_max: float, lum_goal: float):
    """Keep luminance p2/p98 inside the layer limits: compress tails around the median (hue kept), restore the mean."""
    info = dict(high_compress=1.0, low_compress=1.0)
    out = srgb
    for _ in range(3):
        lum = lum_srgb(out)
        med = float(np.median(lum))
        p2, p98 = np.percentile(lum, 2), np.percentile(lum, 98)
        target = lum.copy()
        if p98 > p98_max - 0.01:
            c = (p98_max - 0.015 - med) / max(1e-6, p98 - med)
            target = np.where(lum > med, med + (lum - med) * c, target)
            info['high_compress'] = round(info['high_compress'] * c, 4)
        if p2 < p2_min + 0.01:
            c = (med - p2_min - 0.015) / max(1e-6, med - p2)
            target = np.where(lum < med, med - (med - lum) * c, target)
            info['low_compress'] = round(info['low_compress'] * c, 4)
        out = np.clip(out * (target / np.maximum(lum, 1e-6))[..., None], 0, 1)
        delta = lum_goal - lum_srgb(out).mean()
        out = np.clip(out + delta * out / np.maximum(lum_srgb(out).mean(), 1e-6), 0, 1)
        out = soft_range(out)
        lum = lum_srgb(out)
        if np.percentile(lum, 98) <= p98_max and np.percentile(lum, 2) >= p2_min:
            break
    return out, info


def fit_band(x, lo, hi, mean_goal):
    """Map p5 -> lo and p95 -> hi exactly, with a power curve between them chosen so the mean hits mean_goal."""
    a, b = np.percentile(x, 5), np.percentile(x, 95)
    t = (x - a) / max(1e-9, b - a)
    tin = np.clip(t, 0.0, 1.0)
    tail = t - tin
    g_lo, g_hi = 0.15, 6.0
    for _ in range(40):
        g = math.sqrt(g_lo * g_hi)
        if (lo + (hi - lo) * (tin ** g + tail)).mean() > mean_goal:
            g_lo = g
        else:
            g_hi = g
    g = math.sqrt(g_lo * g_hi)
    return lo + (hi - lo) * (tin ** g + tail), g


def calibrate_normal(h_m: np.ndarray, texel_m: float, targets: dict, gates: dict):
    """Pick a pre-blur and a gain so the derived normal meets the §3.3 tilt targets (records both)."""
    lo_t, hi_t = targets['mean']
    goal = 0.5 * (lo_t + hi_t)
    best = None
    # Wider bevels (blur) before slope caps: a cap bends the normal away from the height gradient at steps
    # (R0 slab edges: agreement 0.61 with a cap), a blur keeps normal and height describing the same surface.
    # (R0 slab steps need ~4 cm of bevel: sigma 10-11.5 px gives p95 <= 42 with agreement ~0.99 and no cap)
    combos = [(s, None) for s in (0.6, 0.85, 1.15, 1.5, 2.0, 2.8, 3.8, 5.0, 6.5, 8.0, 10.0, 11.5, 13.0)] + \
        [(s, c) for c in (1.3, 0.95, 0.7) for s in (0.85, 1.5, 2.6, 3.8)]
    for sigma, cap in combos:
        hb = ST.gaussian_periodic(h_m, sigma)
        lo, hi = 0.02, 8.0
        for _ in range(28):
            mid = math.sqrt(lo * hi)
            n = ST.normal_from_height(hb, texel_m, mid, cap)
            if ST.tilt_deg(n).mean() < goal:
                lo = mid
            else:
                hi = mid
        gain = math.sqrt(lo * hi)
        n = ST.normal_from_height(hb, texel_m, gain, cap)
        s = ST.normal_stats(n, gates['flat_deg'])
        s['mip2_mean'] = ST.mip_tilt(n, 2)
        bad = 0.0
        bad += max(0.0, s['flat'] - targets['flat_max']) * 100
        if 'p95_max' in targets:
            bad += max(0.0, s['p95'] - targets['p95_max'])
        if 'p95_range' in targets:
            bad += max(0.0, targets['p95_range'][0] - s['p95']) + max(0.0, s['p95'] - targets['p95_range'][1])
        if 'p50_min' in targets:
            bad += max(0.0, targets['p50_min'] - s['p50'])
        bad += max(0.0, targets['mip2_mean_min'] - s['mip2_mean']) * 2
        # normal and height must agree (spec §3.3 gate) after KTX2 too: UASTC costs R0 ~0.06 of agreement, so the
        # source keeps a 0.07 margin
        s['agreement'] = ST.normal_height_agreement(n, h01_of(hb))
        bad += max(0.0, gates['normal_height_corr_min'] + 0.07 - s['agreement']) * 100
        cand = (bad, sigma, gain, hb, n, s, cap)
        if best is None or bad < best[0] - 1e-9:
            best = cand
        if bad == 0.0:
            break
    bad, sigma, gain, hb, n, s, cap = best
    return hb, n, dict(blur_px=sigma, gain=round(gain, 4), slope_cap=cap, calibration_violation=round(bad, 3), mean_target=goal)


# ----------------------------------------------------------------------------
# Per-layer painting
# ----------------------------------------------------------------------------

class Passes:
    def __init__(self, folder: Path, lid: str, final: int):
        self.lid, self.final = lid, final
        load = lambda name: np.load(folder / f'{lid}_{name}.npy').astype(np.float64)  # noqa: E731
        self.raw = {name: load(name) for name in ('albedo', 'height', 'ao', 'edge', 'id', 'normal')}
        self.render = self.raw['height'].shape[0]
        self.factor = self.render // final

    def down(self, name_or_array):
        arr = self.raw[name_or_array] if isinstance(name_or_array, str) else name_or_array
        return ST.box_down(arr, self.factor)

    def mask(self, kind: str, tol=0.05):
        return self.down(kind_mask(self.raw['id'], K[kind], tol))

    def kind_rough(self, kind: str, default: float):
        """Per-object roughness (id pass B) averaged over the pixels of one kind only."""
        m = kind_mask(self.raw['id'], K[kind])
        num = self.down(self.raw['id'][..., 2] * m)
        den = self.down(m)
        return np.where(den > 1e-6, num / np.maximum(den, 1e-6), default)


def h01_of(h):
    lo, hi = np.percentile(h, 0.5), np.percentile(h, 99.5)
    return np.clip((h - lo) / max(1e-9, hi - lo), 0, 1)


def paint_common(alb_lin, h01, ao, edge, top=(0.72, 1.22), gamma=1.0, cavity=0.5, edge_amt=0.12, edge_col='#e8d8b0',
                 edge_gate=(0.45, 0.9)):
    """Non-directional painted look: top-light gradient, cavity, edge highlight."""
    topk = top[0] + (top[1] - top[0]) * h01 ** gamma
    out = alb_lin * topk[..., None]
    out *= (1.0 - cavity * (1.0 - ao))[..., None]
    hl = edge_amt * edge * smoothstep(edge_gate[0], edge_gate[1], h01)
    return out + hl[..., None] * (0.45 * hexlin(edge_col) + 0.55 * out)


def comp_L0(P: Passes, layer, seed):
    f = P.final
    alb = P.down('albedo')
    h = P.down('height')
    ao, edge = P.down('ao'), P.down('edge')
    soil, turf, blade, clover = P.mask('soil'), P.mask('turf'), P.mask('blade'), P.mask('flat')
    grit = (pnoise(f, f / 220, seed + 21, 2) - 0.5)
    h = h + grit * 0.0015 * soil
    h01 = h01_of(h)
    pal = layer['palette']
    # gaps: dark lush with a few warm soil specks
    gap = hexlin(pal['shadow'][0]) * (0.85 + 0.3 * pnoise(f, f / 18, seed + 22, 2))[..., None]
    alb = alb * (1 - soil[..., None]) + gap * soil[..., None]
    alb = paint_common(alb, h01, ao, edge, top=(0.66, 1.30), gamma=0.9, cavity=0.55, edge_amt=0.14, edge_col='#c8d878')
    # broad (sub-tile) value and hue breathing; the runtime macro does the big scales
    breath = pnoise(f, f / 2.5, seed + 24, 2)
    alb *= (0.94 + 0.12 * breath)[..., None]
    alb *= np.stack([0.98 + 0.04 * breath, np.ones_like(breath), 1.02 - 0.04 * breath], -1)
    rough = (0.93 * soil + 0.86 * turf + 0.76 * blade + 0.72 * clover) / np.maximum(1e-6, soil + turf + blade + clover)
    rough = rough + 0.06 * (1 - ao)
    return alb, h, ao, rough, dict(cover_blade=float(blade.mean()), cover_turf=float(turf.mean()),
                                   cover_clover=float(clover.mean()))


def comp_L1(P: Passes, layer, seed):
    f = P.final
    alb = P.down('albedo')
    h = P.down('height')
    ao, edge = P.down('ao'), P.down('edge')
    soil, turf, blade, leaf = P.mask('soil'), P.mask('turf'), P.mask('blade'), P.mask('leaf')
    grit = pnoise(f, f / 260, seed + 31, 2)
    h = h + (grit - 0.5) * 0.002 * soil
    h01 = h01_of(h)
    pal = layer['palette']
    soil_col = hexlin(pal['shadow'][0]) * (0.88 + 0.28 * pnoise(f, f / 25, seed + 32, 2))[..., None]
    soil_col = soil_col * (0.9 + 0.2 * grit)[..., None]
    alb = alb * (1 - soil[..., None]) + soil_col * soil[..., None]
    alb = paint_common(alb, h01, ao, edge, top=(0.70, 1.26), gamma=0.9, cavity=0.5, edge_amt=0.12, edge_col='#e0cc80')
    breath = pnoise(f, f / 2.2, seed + 33, 2)
    alb *= (0.95 + 0.10 * breath)[..., None]
    rough = (0.96 * soil + 0.90 * turf + 0.86 * blade + 0.88 * leaf) / np.maximum(1e-6, soil + turf + blade + leaf)
    rough = rough + 0.04 * (1 - ao)
    return alb, h, ao, rough, dict(cover_blade=float(blade.mean()), cover_turf=float(turf.mean()), bare=float(soil.mean()),
                                   cover_leaf=float(leaf.mean()))


def comp_L2(P: Passes, layer, seed):
    f = P.final
    alb = P.down('albedo')
    h = P.down('height')
    ao, edge = P.down('ao'), P.down('edge')
    soil, stone, wood, leaf = P.mask('soil'), P.mask('stone'), P.mask('wood'), P.mask('leaf')
    grit = pnoise(f, f / 300, seed + 41, 2)
    h = h + (grit - 0.5) * 0.0012 * soil
    h01 = h01_of(h)
    pal = layer['palette']
    # soil-only height: pebbles/clods in-painted by a masked blur, normalised over soil texels (pebbles would
    # otherwise own the top of the range and push every soil texel into the dark "rut" band)
    hs = ST.gaussian_periodic(h * soil, 3.0) / np.maximum(ST.gaussian_periodic(soil, 3.0), 1e-3)
    sel = soil > 0.5
    lo_s, hi_s = np.percentile(hs[sel], 1), np.percentile(hs[sel], 99)
    soil_h = np.clip((hs - lo_s) / max(1e-9, hi_s - lo_s), 0, 1)
    sun, shade = hexlin(pal['light'][0]), hexlin(pal['shadow'][0])
    base = hexlin(pal['base'][0])
    # Blotch fix (P1): the broad +-1 cm soil undulation (0.25-1 m) is NOT painted into the albedo. It was painted
    # twice - a soil-height "sun lean" and a 0.25 * h01 share of the top-light - and together they made 0.15-1.5 m
    # cloud blotches (lum band corr with the height band 0.98; 72 % / 55 % of the 0.15-0.5 m band variance).
    # The undulation stays in height/normal (lighting shows it); the painted value follows the mid band only
    # (prints, rims, clods: ~4-16 cm), plus fine grain and the darker tone in real prints and dips.
    mid_h = ST.gaussian_periodic(hs, 3.0) - ST.gaussian_periodic(hs, 40.0)
    mid = h01_of(mid_h) * soil
    s = smoothstep(0.25, 0.85, mid)[..., None]
    soil_col = base * (0.97 + 0.06 * s) + (sun - base) * 0.10 * s
    fine = pnoise(f, f / 40, seed + 42, 2)[..., None]
    soil_col = soil_col * (0.95 + 0.10 * fine)
    local_m = hs - ST.gaussian_periodic(hs, 8.0)
    rut = np.clip(-local_m / 0.004, 0, 1) * soil  # footprints are 5 mm deep
    soil_col = soil_col * (1 - 0.35 * rut[..., None]) + hexlin(pal['shadow'][1]) * (0.35 * rut[..., None])
    soil_col = soil_col * (0.9 + 0.2 * grit)[..., None]
    alb = alb * (1 - soil[..., None]) + soil_col * soil[..., None]
    # top-light on the features (pebbles, clods: < 4 cm high-pass) and on the mid band (prints, rims); never on
    # the broad undulation (see the blotch note above)
    local = h01_of(h - ST.gaussian_periodic(h, 10.0))
    feat_mid = h01_of(ST.gaussian_periodic(h, 2.0) - ST.gaussian_periodic(h, 40.0))
    paint_h = 0.7 * local + 0.3 * feat_mid
    ao_local = np.clip(1 - (ST.gaussian_periodic(ao, 1.0) - ST.gaussian_periodic(ao, 12.0)).clip(max=0) * -1.6, 0, 1)
    alb = paint_common(alb, paint_h, ao_local * 0.6 + ao * 0.4, edge, top=(0.80, 1.18), gamma=1.0, cavity=0.45, edge_amt=0.16,
                       edge_col='#efe2c4')
    stone_r = P.kind_rough('stone', 0.68)
    # packed soil: crowns polished by traffic are smoother, loose dips and prints rougher (follows the form)
    soil_r = 0.97 - 0.07 * soil_h
    rough = (soil_r * soil + 0.85 * wood + 0.80 * leaf + stone_r * stone) / np.maximum(1e-6, soil + wood + leaf + stone)
    rough = rough + 0.05 * (1 - ao) - 0.05 * edge * stone
    return alb, h, ao, rough, dict(cover_stone=float(stone.mean()), cover_wood=float(wood.mean()))


def comp_L3(P: Passes, layer, seed):
    f = P.final
    alb = P.down('albedo')
    h = P.down('height')
    ao, edge = P.down('ao'), P.down('edge')
    soil, moss, stone, wood = P.mask('soil'), P.mask('moss'), P.mask('stone'), P.mask('wood')
    h01 = h01_of(h)
    pal = layer['palette']
    mud_h = h01_of(ST.gaussian_periodic(h * soil + (1 - soil) * np.percentile(h, 50), 2.0))
    # low mud is wet and dark; puddles shine. P1: softer ramp and 0.5 (was 0.65) so hollows read as damp ground,
    # not as hard-edged dark stains at the 3 m tile scale.
    wet = smoothstep(0.50, 0.08, mud_h) * soil
    mud_col = hexlin(pal['base'][0]) * (0.9 + 0.2 * pnoise(f, f / 20, seed + 51, 2))[..., None]
    mud_col = mud_col * (1 - 0.5 * wet[..., None]) + hexlin(pal['shadow'][0]) * (0.5 * wet[..., None])
    alb = alb * (1 - soil[..., None]) + mud_col * soil[..., None]
    # moss tips catch the top light
    tips = smoothstep(0.55, 0.95, h01) * moss
    alb = alb * (1 - 0.35 * tips[..., None]) + hexlin(pal['light'][0]) * (0.35 * tips[..., None])
    alb = paint_common(alb, h01, ao, edge, top=(0.74, 1.24), gamma=1.0, cavity=0.5, edge_amt=0.10, edge_col='#c8d888')
    puddle = smoothstep(0.30, 0.06, mud_h) * soil
    rough = soil * (0.62 - 0.30 * puddle - 0.10 * wet) + moss * 0.88 + stone * 0.45 + wood * 0.80
    rough = rough / np.maximum(1e-6, soil + moss + stone + wood)
    rough = rough + 0.03 * (1 - ao)
    return alb, h, ao, rough, dict(cover_moss=float(moss.mean()), cover_stone=float(stone.mean()), puddle=float(puddle.mean()))


def comp_R0(P: Passes, layer, seed):
    f = P.final
    alb = P.down('albedo')
    h = P.down('height')
    ao, edge = P.down('ao'), P.down('edge')
    soil = P.mask('soil')
    stone = 1.0 - soil
    # hairline cracks from one mask into height, albedo and roughness (lesson 1: same mask everywhere)
    ridge = np.abs(pnoise(f, f / 14, seed + 61, 3) - 0.5)
    crack = smoothstep(0.018, 0.0, ridge) * smoothstep(0.55, 0.75, pnoise(f, f / 6, seed + 62, 2)) * stone
    h = h - 0.012 * crack
    grain = pnoise(f, f / 160, seed + 63, 2)
    h = h + (grain - 0.5) * 0.0025 * stone
    h01 = h01_of(h)
    alb = alb * (1 - soil[..., None]) + hexlin('#4a4034') * soil[..., None] * (0.9 + 0.2 * grain)[..., None]
    alb = alb * (1 - 0.55 * crack[..., None])
    alb = paint_common(alb, h01, ao, edge, top=(0.76, 1.18), gamma=1.0, cavity=0.38, edge_amt=0.24, edge_col='#e8d8b0',
                       edge_gate=(0.30, 0.85))
    alb *= (0.92 + 0.16 * grain)[..., None]
    # weathered faces: exposed tops and arrises are smoother, crevices and cracks rough; small per-block spread
    top = smoothstep(0.45, 0.95, h01)
    rough = stone * (0.88 + 0.35 * (P.kind_rough('stone', 0.9) - 0.9) - 0.16 * top) + soil * 0.97
    rough = rough - 0.24 * edge * stone + 0.05 * crack + 0.05 * (1 - ao)
    return alb, h, ao, rough, dict(cover_crevice=float(soil.mean()), cracks=float(crack.mean()))


def comp_R1(P: Passes, layer, seed):
    f = P.final
    alb = P.down('albedo')
    h = P.down('height')
    ao, edge = P.down('ao'), P.down('edge')
    soil, moss, blade = P.mask('soil'), P.mask('moss'), P.mask('blade')
    h01 = h01_of(h)
    pal = layer['palette']
    alb = alb * (1 - soil[..., None]) + hexlin(pal['shadow'][0]) * soil[..., None]
    tips = smoothstep(0.6, 0.95, h01)
    alb = alb * (1 - 0.3 * tips[..., None]) + hexlin(pal['light'][1]) * (0.3 * tips[..., None])
    alb = paint_common(alb, h01, ao, edge, top=(0.70, 1.26), gamma=0.9, cavity=0.5, edge_amt=0.10, edge_col='#c8d888')
    rough = (soil * 0.92 + moss * 0.84 + blade * 0.80) / np.maximum(1e-6, soil + moss + blade)
    rough = rough + 0.05 * (1 - ao)
    return alb, h, ao, rough, dict(cover_moss=float(moss.mean()), cover_fibre=float(blade.mean()))


COMPOSITORS = {'L0': comp_L0, 'L1': comp_L1, 'L2': comp_L2, 'L3': comp_L3, 'R0': comp_R0, 'R1': comp_R1}


# ----------------------------------------------------------------------------
# Finishing, gates and output
# ----------------------------------------------------------------------------

def finish_layer(layer: dict, P: Passes, seed: int, out_dir: Path) -> dict:
    gates = TS.GATES
    t = layer['targets']
    alb_lin, h_m, ao_pass, rough, info = COMPOSITORS[layer['id']](P, layer, seed)
    texel_m = layer['tile_m'] / P.final
    hb, normal, ncal = calibrate_normal(h_m, texel_m, t['normal'], gates)
    h01 = h01_of(hb)
    # roughness: smooth until it is never noisy, then place it in the target band with the target mean
    raw_rough = rough
    for rough_blur in (1.2, 1.7, 2.3, 3.0, 4.0, 5.2):
        rough = ST.gaussian_periodic(raw_rough, rough_blur)
        rough, rough_gamma = fit_band(rough, t['rough']['p5'] + 0.004, t['rough']['p95'] - 0.004, t['rough']['mean'])
        rough = np.clip(rough, 0.2, 1.0)
        q = np.rint(rough * 255) / 255
        adj = np.concatenate([np.abs(np.diff(q, axis=1)).ravel(), np.abs(np.diff(q, axis=0)).ravel()])
        # 0.015 margin: UASTC adds ~0.01-0.04 of adjacent roughness noise (decoded L0/L3/R1 were 0.055-0.059)
        if np.percentile(adj, 95) <= gates['rough_adjacent_p95_max'] - 0.015:
            break
    # AO: occlusion = 1 - k (1 - ao), k chosen for the target mean
    lo_ao, hi_ao = t['ao']['mean']
    ao_goal = 0.5 * (lo_ao + hi_ao)
    k = float(np.clip((1 - ao_goal) / max(1e-6, (1 - ao_pass).mean()), 0.2, 4.0))
    occlusion = np.clip(1 - k * (1 - ao_pass), 0.30, 1.0)
    occlusion = ST.gaussian_periodic(occlusion, 0.6)
    # albedo: sRGB, graded to the layer means, soft knees
    srgb = linear_to_srgb(np.clip(alb_lin, 0, 1))
    ta = t['albedo']
    lum_goal = 0.5 * (ta['lum_mean'][0] + ta['lum_mean'][1])
    sat_goal = 0.5 * (ta['sat_mean'][0] + ta['sat_mean'][1]) if 'sat_mean' in ta else None
    srgb, grade_info = grade(srgb, lum_goal, sat_goal, ta.get('sat_max'))
    srgb, tone_info = tone_fit(srgb, ta['p2_min'], ta['p98_max'], lum_goal)
    grade_info.update(tone_info)
    # quantise exactly as written, then measure what ships
    alb8 = np.clip(np.rint(srgb * 255), 0, 255).astype(np.uint8)
    nrm8 = ST.encode_normal(normal)
    orm8 = np.stack([np.clip(np.rint(occlusion * 255), 0, 255), np.clip(np.rint(rough * 255), 0, 255),
                     np.zeros_like(rough)], -1).astype(np.uint8)
    h16 = np.clip(np.rint(h01 * 65535), 0, 65535).astype(np.uint16)
    # Tile origin: the maps are periodic, so any origin is valid. The forge seam metric compares one edge row pair
    # with the mean gradient, and single row pairs vary +-30 % for clustered content (see interior_pair_ratio);
    # pick the origin (multiples of 8 px, mip-aligned) whose edge pair is typical, and record the distribution.
    rng = np.random.default_rng(seed + 5)
    maps = dict(albedo=alb8, normal=nrm8, orm=orm8, height=h16)
    best_shift, best_score = (0, 0), max(ST.seam_score(m) for m in maps.values())
    for _ in range(24):
        dy, dx = (int(v) * 8 for v in rng.integers(0, P.final // 8, 2))
        score = max(ST.seam_score(np.roll(m, (dy, dx), (0, 1))) for m in maps.values())
        if score < best_score:
            best_shift, best_score = (dy, dx), score
    alb8, nrm8, orm8, h16 = (np.roll(m, best_shift, (0, 1)) for m in (alb8, nrm8, orm8, h16))
    pair_ratio = {}
    for name, m in (('albedo', alb8), ('normal', nrm8), ('height', h16)):
        mf = m.astype(np.float64)
        inner = (np.abs(np.diff(mf, axis=1)).mean() + np.abs(np.diff(mf, axis=0)).mean()) / 2
        ratios = [np.abs(mf[k] - mf[k + 1]).mean() / inner for k in range(0, mf.shape[0] - 1, 7)]
        ratios += [np.abs(mf[:, k] - mf[:, k + 1]).mean() / inner for k in range(0, mf.shape[1] - 1, 7)]
        pair_ratio[name] = dict(p5=round(float(np.percentile(ratios, 5)), 3), p50=round(float(np.percentile(ratios, 50)), 3),
                                p95=round(float(np.percentile(ratios, 95)), 3))
    stats, fails = ST.layer_report(layer, gates, alb8 / 255.0, ST.decode_normal(nrm8), orm8[..., 1] / 255.0,
                                   orm8[..., 0] / 255.0, h16 / 65535.0, label='source')
    seams = {name: ST.seam_score(arr.astype(np.float64)) for name, arr in
             (('albedo', alb8), ('normal', nrm8), ('orm', orm8), ('height', h16))}
    for name, s in seams.items():
        if s > gates['seam_max']:
            fails.append(f'{layer["id"]} source: seam {name} {s:.3f} > {gates["seam_max"]}')
    if int(orm8[..., 2].max()) != 0:
        fails.append(f'{layer["id"]} source: ORM B (metal) not exactly 0')
    files = {}
    for kind, arr, bits in (('albedo', alb8, 8), ('normal', nrm8, 8), ('orm', orm8, 8), ('height', h16, 16)):
        path = out_dir / f'{layer["name"]}_{kind}.png'
        terrain_png.write_png(path, arr, bits=bits)
        files[kind] = dict(path=rel(path), bytes=path.stat().st_size,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(), seam_score=round(seams[kind], 4))
    span = float(np.percentile(hb, 99.5) - np.percentile(hb, 0.5))
    return dict(id=layer['id'], name=layer['name'], tile_m=layer['tile_m'], px=P.final, render_px=P.render,
                height_range_m=layer['height_range_m'], measured_height_span_m=round(span, 4),
                normal_calibration=ncal, ao_k=round(k, 4), rough_gamma=round(rough_gamma, 4), rough_blur_px=rough_blur,
                albedo_grade=grade_info, tile_origin_shift_px=list(best_shift), interior_pair_ratio=pair_ratio,
                content=info, files=files,
                stats=stats, pass_source=not fails, failures=fails)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = {'passes': str(DEFAULT_PASSES),
            'out': str(ROOT / TS.LAYER_SOURCE_DIR), 'only': '', 'seed': '7'}
    i = 0
    while i < len(argv):
        key = argv[i].lstrip('-')
        if key in args and i + 1 < len(argv):
            args[key] = argv[i + 1]
            i += 2
        else:
            raise SystemExit(f'unknown argument {argv[i]}')
    passes = Path(args['passes'])
    out = Path(args['out'])
    out.mkdir(parents=True, exist_ok=True)
    only = [s for s in args['only'].split(',') if s]
    meta = json.loads((passes / 'forge-r7-passes.json').read_text()) if (passes / 'forge-r7-passes.json').exists() else {}
    stats_path = out / 'layer-stats.json'
    manifest_path = out / 'forge-manifest.json'
    previous = json.loads(manifest_path.read_text(encoding='utf-8')).get('layers', {}) if manifest_path.exists() else {}
    records = dict(previous)
    all_fail = []
    for layer in TS.ALL_LAYERS:
        if only and layer['id'] not in only:
            continue
        if not (passes / f'{layer["id"]}_height.npy').exists():
            print(f'skip {layer["id"]}: no passes in {passes}')
            continue
        t0 = time.time()
        render_px = np.load(passes / f'{layer["id"]}_height.npy', mmap_mode='r').shape[0]
        final = int(meta.get(layer['id'], {}).get('final_px') or render_px // TS.FORGE['render_scale'])
        P = Passes(passes, layer['id'], final)
        rec = finish_layer(layer, P, int(args['seed']) * 977 + sum(map(ord, layer['id'])), out)
        rec['forge'] = meta.get(layer['id'], {})
        rec['composite_seconds'] = round(time.time() - t0, 1)
        records[layer['id']] = rec
        all_fail += rec['failures']
        s = rec['stats']
        print(f"COMPOSITE {layer['id']}: {'PASS' if rec['pass_source'] else 'FAIL'} tilt {s['normal']['mean']:.1f} "
              f"flat {s['normal']['flat']:.3f} p95 {s['normal']['p95']:.1f} mip2 {s['normal']['mip2_mean']:.1f} | rough "
              f"{s['rough']['p5']:.2f}-{s['rough']['p95']:.2f} m{s['rough']['mean']:.2f} adj {s['rough']['adjacent_p95']:.3f} "
              f"fc {s['rough']['form_corr']:.2f} | ao {s['ao']['mean']:.2f} | lum {s['albedo']['lum_mean']:.3f} "
              f"sat {s['albedo']['sat_mean']:.2f} p2 {s['albedo']['lum_p2']:.2f} p98 {s['albedo']['lum_p98']:.2f} "
              f"lh {s['albedo']['corr_lum_height']:.2f} dir {s['albedo']['corr_lum_dhdx']:.2f}/{s['albedo']['corr_lum_dhdy']:.2f} "
              f"| nh {s['normal_height_corr']:.2f} ny {s['normal_y_corr']:.2f}", flush=True)
        for fail in rec['failures']:
            print('   ', fail)
    manifest = dict(schema='xexoria.terrain-forge/1', generator='assets/blender/city_r5/forge/forge_terrain_r7.py',
                    composite='assets/blender/sunmeadow_v2/terrain/terrain_forge_composite.py', spec=TS.SPEC_DOC,
                    contract='<name>_albedo.png sRGB, <name>_normal.png OpenGL +Y, <name>_orm.png R AO / G roughness / B metal 0, '
                             '<name>_height.png 16-bit linear percentile-normalised; row 0 = tile +Y (world +Z)',
                    license='Original procedural work for Xexoria; no third-party pixels (no CC0 underlayer in R7 v1).',
                    status='CANDIDATE - terrain splat P1 source set', layers=records)
    manifest_path.write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    stats_path.write_text(json.dumps({lid: dict(stats=r['stats'], pass_source=r['pass_source'], failures=r['failures'])
                                      for lid, r in records.items()}, indent=1) + '\n', encoding='utf-8')
    print(f'COMPOSITE done: {len(all_fail)} gate failure(s)')
    return 1 if all_fail else 0


if __name__ == '__main__':
    raise SystemExit(main())
