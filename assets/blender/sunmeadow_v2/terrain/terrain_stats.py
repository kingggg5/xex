"""Shared terrain texture statistics (spec §3.3 method; same as planning/evidence/stone-r3-check-20261002.json).

Pure numpy (runs in Blender's Python and in system Python). Used by the forge composite (script 1), the
KTX2 exporter's decode-back checks (script 5) and check_terrain_textures.py (script 6), so a number means
the same thing everywhere.

Conventions
- Arrays: row 0 = image top. Normal maps are OpenGL (+Y = image up): n = (-dh/du, -dh/dv, 1) with v = image up.
- Normal decode: rgb / 255 * 2 - 1 (8-bit) and renormalise; tilt = angle from +Z.
- Albedo values are sRGB-encoded 0..1; luminance = Rec.709 weights on sRGB values; S = HSV saturation.
"""
from __future__ import annotations

import math

import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float64)


# ----------------------------------------------------------------------------
# Periodic helpers
# ----------------------------------------------------------------------------

def grad_periodic(h: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Central differences in texels, periodic: (dh/du with u = image right, dh/dv with v = image up)."""
    du = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dv = (np.roll(h, 1, 0) - np.roll(h, -1, 0)) * 0.5   # row - 1 is "up"
    return du, dv


def gaussian_periodic(img: np.ndarray, sigma_px: float) -> np.ndarray:
    """Periodic Gaussian blur through the FFT (seamless by construction). Works on (H, W) or (H, W, C)."""
    if sigma_px <= 0:
        return img.astype(np.float32, copy=True)
    h, w = img.shape[:2]
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    kernel = np.exp(-2.0 * (math.pi ** 2) * (sigma_px ** 2) * (fx * fx + fy * fy))
    if img.ndim == 2:
        return np.fft.irfft2(np.fft.rfft2(img) * kernel, s=(h, w)).astype(np.float32)
    return np.stack([np.fft.irfft2(np.fft.rfft2(img[..., c]) * kernel, s=(h, w)) for c in range(img.shape[2])],
                    -1).astype(np.float32)


def box_down(img: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return img
    h, w = img.shape[:2]
    shape = (h // factor, factor, w // factor, factor) + img.shape[2:]
    return img.reshape(shape).mean(axis=(1, 3))


def normal_from_height(h_m: np.ndarray, texel_m: float, gain: float = 1.0, cap: float | None = None) -> np.ndarray:
    """Unit normals (H, W, 3) from a metre heightfield sampled at texel_m, OpenGL convention.

    cap: optional soft slope limit (tan of the tilt); the direction is kept, steep walls become bevels."""
    du, dv = grad_periodic(h_m.astype(np.float64))
    nx = -du / texel_m * gain
    ny = -dv / texel_m * gain
    if cap:
        k = 1.0 / np.sqrt(1.0 + (np.hypot(nx, ny) / cap) ** 2)
        nx, ny = nx * k, ny * k
    n = np.stack([nx, ny, np.ones_like(nx)], -1)
    return (n / np.linalg.norm(n, axis=-1, keepdims=True)).astype(np.float32)


def encode_normal(n: np.ndarray) -> np.ndarray:
    return np.clip(np.rint((n * 0.5 + 0.5) * 255.0), 0, 255).astype(np.uint8)


def decode_normal(rgb: np.ndarray) -> np.ndarray:
    n = rgb[..., :3].astype(np.float64) / 255.0 * 2.0 - 1.0
    return n / np.maximum(1e-9, np.linalg.norm(n, axis=-1, keepdims=True))


def decode_normal_xy(xy: np.ndarray) -> np.ndarray:
    """Two-channel (X, Y) bytes -> unit normal with reconstructed Z (the runtime NRO decode)."""
    x = xy[..., 0].astype(np.float64) / 255.0 * 2.0 - 1.0
    y = xy[..., 1].astype(np.float64) / 255.0 * 2.0 - 1.0
    z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
    n = np.stack([x, y, z], -1)
    return n / np.maximum(1e-9, np.linalg.norm(n, axis=-1, keepdims=True))


def normal_mip(n: np.ndarray) -> np.ndarray:
    """One mip step of a unit normal field: decoded-vector average, renormalised; also |avg| for Toksvig."""
    avg = box_down(n, 2)
    length = np.linalg.norm(avg, axis=-1, keepdims=True)
    return avg / np.maximum(1e-9, length), length[..., 0]


def tilt_deg(n: np.ndarray) -> np.ndarray:
    return np.degrees(np.arccos(np.clip(n[..., 2], -1.0, 1.0)))


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64).ravel()
    b = b.astype(np.float64).ravel()
    a = a - a.mean()
    b = b - b.mean()
    den = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else 0.0


def seam_score(img: np.ndarray) -> float:
    """Forge metric (forge_textures_r6.py:827-831): edge discontinuity / inner gradient; 1.0 = seamless."""
    img = img.astype(np.float64)
    left_right = np.abs(img[:, 0] - img[:, -1]).mean()
    top_bottom = np.abs(img[0] - img[-1]).mean()
    inner = (np.abs(img[:, 1:] - img[:, :-1]).mean() + np.abs(img[1:] - img[:-1]).mean()) / 2
    return float(max(left_right, top_bottom) / max(1e-9, inner))


def rgb_to_saturation(rgb: np.ndarray) -> np.ndarray:
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


# ----------------------------------------------------------------------------
# Per-map statistics
# ----------------------------------------------------------------------------

def normal_stats(n: np.ndarray, flat_deg: float = 1.0) -> dict:
    t = tilt_deg(n)
    return dict(flat=float((t <= flat_deg).mean()), mean=float(t.mean()), p50=float(np.percentile(t, 50)),
                p90=float(np.percentile(t, 90)), p95=float(np.percentile(t, 95)))


def mip_tilt(n: np.ndarray, level: int) -> float:
    cur = n
    for _ in range(level):
        cur, _ = normal_mip(cur)
    return float(tilt_deg(cur).mean())


def rough_stats(r: np.ndarray, h: np.ndarray | None, ao: np.ndarray | None) -> dict:
    adj = np.concatenate([np.abs(np.diff(r, axis=1)).ravel(), np.abs(np.diff(r, axis=0)).ravel()])
    out = dict(p5=float(np.percentile(r, 5)), p95=float(np.percentile(r, 95)), mean=float(r.mean()),
               adjacent_p95=float(np.percentile(adj, 95)))
    out['span'] = out['p95'] - out['p5']
    out['corr_height'] = pearson(r, h) if h is not None else 0.0
    out['corr_ao'] = pearson(r, ao) if ao is not None else 0.0
    out['form_corr'] = max(abs(out['corr_height']), abs(out['corr_ao']))
    return out


def albedo_stats(rgb01: np.ndarray, h01: np.ndarray | None) -> dict:
    lum = (rgb01[..., :3].astype(np.float64) * LUMA).sum(-1)
    sat = rgb_to_saturation(rgb01[..., :3].astype(np.float64))
    flat = rgb01[..., :3].reshape(-1, 3)
    out = dict(lum_mean=float(lum.mean()), lum_p2=float(np.percentile(lum, 2)), lum_p98=float(np.percentile(lum, 98)),
               sat_mean=float(sat.mean()),
               channel_p01=[float(np.percentile(flat[:, c], 0.1)) for c in range(3)],
               channel_p999=[float(np.percentile(flat[:, c], 99.9)) for c in range(3)])
    if h01 is not None:
        du, dv = grad_periodic(h01.astype(np.float64))
        out['corr_lum_height'] = pearson(lum, h01)
        out['corr_lum_dhdx'] = pearson(lum, du)
        out['corr_lum_dhdy'] = pearson(lum, dv)
    return out


def height_stats(h01: np.ndarray) -> dict:
    return dict(p1=float(np.percentile(h01, 1)), p99=float(np.percentile(h01, 99)), mean=float(h01.mean()))


def normal_height_agreement(n: np.ndarray, h01: np.ndarray) -> float:
    """corr(decoded normal XY, normal recomputed from the height map); scale-free (Pearson), mean of X and Y."""
    du, dv = grad_periodic(h01.astype(np.float64))
    return 0.5 * (pearson(n[..., 0], -du) + pearson(n[..., 1], -dv))


def normal_y_check(n: np.ndarray, h01: np.ndarray) -> float:
    """corr(decoded n.y, -dh/dv) with v = image up (spec §6.2 item 7); negative means a flipped green channel."""
    _, dv = grad_periodic(h01.astype(np.float64))
    return pearson(n[..., 1], -dv)


# ----------------------------------------------------------------------------
# Layer gates (spec §3.3); returns (stats, failures)
# ----------------------------------------------------------------------------

def layer_report(layer: dict, gates: dict, albedo_srgb01: np.ndarray, normal: np.ndarray, rough: np.ndarray,
                 ao: np.ndarray, h01: np.ndarray, mip2_tilt: float | None = None, label: str = 'png') -> tuple[dict, list]:
    t = layer['targets']
    ns = normal_stats(normal, gates['flat_deg'])
    ns['mip2_mean'] = mip_tilt(normal, 2) if mip2_tilt is None else mip2_tilt
    rs = rough_stats(rough, h01, ao)
    al = albedo_stats(albedo_srgb01, h01)
    hs = height_stats(h01)
    agreement = normal_height_agreement(normal, h01)
    ny = normal_y_check(normal, h01)
    stats = dict(normal=ns, rough=rs, ao=dict(mean=float(ao.mean())), albedo=al, height=hs,
                 normal_height_corr=agreement, normal_y_corr=ny)
    fails = []

    def need(ok, msg):
        if not ok:
            fails.append(f'{layer["id"]} {label}: {msg}')

    tn = t['normal']
    need(ns['flat'] <= tn['flat_max'], f"flat {ns['flat']:.3f} > {tn['flat_max']}")
    need(tn['mean'][0] <= ns['mean'] <= tn['mean'][1], f"mean tilt {ns['mean']:.2f} not in {tn['mean']}")
    if 'p50_min' in tn:
        need(ns['p50'] >= tn['p50_min'], f"p50 {ns['p50']:.2f} < {tn['p50_min']}")
    if 'p95_max' in tn:
        need(ns['p95'] <= tn['p95_max'], f"p95 {ns['p95']:.2f} > {tn['p95_max']}")
    if 'p95_range' in tn:
        need(tn['p95_range'][0] <= ns['p95'] <= tn['p95_range'][1], f"p95 {ns['p95']:.2f} not in {tn['p95_range']}")
    need(ns['mip2_mean'] >= tn['mip2_mean_min'], f"mip2 tilt {ns['mip2_mean']:.2f} < {tn['mip2_mean_min']}")
    tr = t['rough']
    # Spec: "p5-p95 (mean)" — the measured p5/p95 must lie inside the target band, mean within +-0.05.
    need(rs['p5'] >= tr['p5'] - 0.02, f"rough p5 {rs['p5']:.3f} < {tr['p5']}")
    need(rs['p95'] <= tr['p95'] + 0.02, f"rough p95 {rs['p95']:.3f} > {tr['p95']}")
    need(abs(rs['mean'] - tr['mean']) <= 0.05, f"rough mean {rs['mean']:.3f} vs {tr['mean']}")
    need(rs['span'] >= tr['span_min'], f"rough span {rs['span']:.3f} < {tr['span_min']}")
    need(rs['adjacent_p95'] <= gates['rough_adjacent_p95_max'], f"rough noisy {rs['adjacent_p95']:.3f}")
    need(rs['form_corr'] >= gates['rough_form_corr_min'], f"rough form corr {rs['form_corr']:.3f}")
    if tr.get('corr_sign'):
        need(rs['corr_height'] * tr['corr_sign'] > 0, f"rough/height corr sign {rs['corr_height']:.3f} (expected {tr['corr_sign']:+d})")
    ta = t['ao']
    need(ta['mean'][0] <= stats['ao']['mean'] <= ta['mean'][1], f"ao mean {stats['ao']['mean']:.3f} not in {ta['mean']}")
    tal = t['albedo']
    need(min(al['channel_p01']) >= gates['albedo_channel_p01_min'], f"albedo p0.1 {min(al['channel_p01']):.3f}")
    need(max(al['channel_p999']) <= gates['albedo_channel_p999_max'], f"albedo p99.9 {max(al['channel_p999']):.3f}")
    need(tal['lum_mean'][0] <= al['lum_mean'] <= tal['lum_mean'][1], f"lum mean {al['lum_mean']:.3f} not in {tal['lum_mean']}")
    if 'sat_mean' in tal:
        need(tal['sat_mean'][0] <= al['sat_mean'] <= tal['sat_mean'][1], f"sat {al['sat_mean']:.3f} not in {tal['sat_mean']}")
    if 'sat_max' in tal:
        need(al['sat_mean'] <= tal['sat_max'], f"sat {al['sat_mean']:.3f} > {tal['sat_max']}")
    need(al['lum_p2'] >= tal['p2_min'], f"lum p2 {al['lum_p2']:.3f} < {tal['p2_min']}")
    need(al['lum_p98'] <= tal['p98_max'], f"lum p98 {al['lum_p98']:.3f} > {tal['p98_max']}")
    need(al['corr_lum_height'] >= gates['lum_height_corr_min'], f"lum/height corr {al['corr_lum_height']:.3f}")
    need(max(abs(al['corr_lum_dhdx']), abs(al['corr_lum_dhdy'])) <= gates['lum_gradient_corr_max'],
         f"directional light corr {al['corr_lum_dhdx']:.3f}/{al['corr_lum_dhdy']:.3f}")
    need(hs['p1'] <= gates['height_p1_max'] and hs['p99'] >= gates['height_p99_min'], f"height range p1 {hs['p1']:.3f} p99 {hs['p99']:.3f}")
    need(agreement >= gates['normal_height_corr_min'], f"normal/height agreement {agreement:.3f}")
    need(ny > gates['normal_y_corr_min'], f"normal-Y corr {ny:.3f} (flipped green?)")
    return stats, fails
