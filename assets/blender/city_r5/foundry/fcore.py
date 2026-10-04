"""Foundry core: periodic (tileable) image operations for procedural PBR maps.

Every operation here wraps at the image borders (FFT filtering, np.roll
derivatives, periodic KD-trees, modulo indexing), so anything composed from
them tiles seamlessly. Arrays are float32, (H, W) or (H, W, C). Heights are in
metres; `Ctx.P` converts metres to pixels so a material looks the same at any
--size.
"""
from __future__ import annotations

import colorsys
import functools
import math
import os
import zlib

import numpy as np
from scipy import fft as sfft
from scipy import ndimage as ndi
from scipy import special
from scipy.spatial import cKDTree

WORKERS = max(1, int(os.environ.get('FOUNDRY_WORKERS', '4')))
F32 = np.float32


# --------------------------------------------------------------------------
# Context: resolution, tile size and deterministic seeds for one material.
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, name: str, size, tile_m: float):
        if isinstance(size, int):
            size = (size, size)
        self.name = name
        self.H, self.W = size
        self.shape = (self.H, self.W)
        self.N = self.W
        self.tile = float(tile_m)
        self.P = self.W / self.tile          # pixels per metre
        self.px = self.tile / self.W         # metres per pixel
        self.seed = zlib.crc32(name.encode('utf-8')) & 0x7FFFFFFF
        self.rng = np.random.default_rng(self.seed)
        self._key = 0

    def m(self, metres):
        """Metres -> pixels."""
        return metres * self.P

    def key(self):
        self._key += 1
        return self.seed * 7919 + self._key * 104729

    def noise(self, sigma_m, sigma_x_m=None, angle=0.0):
        sx = None if sigma_x_m is None else sigma_x_m * self.P
        return noise(self.shape, self.key(), sigma_m * self.P, sx, angle)

    def fbm(self, sigma_m, octaves=5, gain=0.5, lac=2.0, sigma_x_m=None, angle=0.0):
        sx = None if sigma_x_m is None else sigma_x_m * self.P
        return fbm(self.shape, self.key(), sigma_m * self.P, octaves, gain, lac, sx, angle)

    def white(self):
        return np.random.default_rng(self.key()).random(self.shape, dtype=np.float32)


@functools.lru_cache(maxsize=8)
def grid(h: int, w: int):
    """Pixel-centre coordinates (yy, xx) as float32 (read-only, cached)."""
    yy, xx = np.meshgrid(np.arange(h, dtype=F32) + 0.5, np.arange(w, dtype=F32) + 0.5, indexing='ij')
    yy.setflags(write=False)
    xx.setflags(write=False)
    return yy, xx


@functools.lru_cache(maxsize=8)
def igrid(h: int, w: int):
    yy, xx = np.meshgrid(np.arange(h, dtype=np.int32), np.arange(w, dtype=np.int32), indexing='ij')
    yy.setflags(write=False)
    xx.setflags(write=False)
    return yy, xx


def wrapd(d, n):
    """Wrap a coordinate difference into [-n/2, n/2)."""
    return (d + n * 0.5) % n - n * 0.5


# --------------------------------------------------------------------------
# FFT filtering (periodic by construction)
# --------------------------------------------------------------------------
@functools.lru_cache(maxsize=16)
def _freqs(h: int, w: int):
    fy = sfft.fftfreq(h).astype(F32)[:, None]
    fx = sfft.rfftfreq(w).astype(F32)[None, :]
    return fy, fx


def rfft(a):
    return sfft.rfft2(np.asarray(a, dtype=F32), workers=WORKERS)


def irfft(F, shape):
    return sfft.irfft2(F, s=shape, workers=WORKERS).astype(F32, copy=False)


def gauss_tf(shape, sy, sx=None, angle=0.0):
    """Transfer function of a periodic Gaussian (sigmas in px, sx along x)."""
    fy, fx = _freqs(*shape)
    sx = sy if sx is None else sx
    if angle:
        c, s = math.cos(angle), math.sin(angle)
        fu = fx * c + fy * s
        fv = -fx * s + fy * c
    else:
        fu, fv = fx, fy
    return np.exp(-2.0 * math.pi ** 2 * ((fu * sx) ** 2 + (fv * sy) ** 2)).astype(F32)


def blur(a, sy, sx=None, angle=0.0):
    a = np.asarray(a, dtype=F32)
    if a.ndim == 3:
        return np.stack([blur(a[..., c], sy, sx, angle) for c in range(a.shape[2])], axis=-1)
    if sy <= 0 and (sx is None or sx <= 0):
        return a.copy()
    return irfft(rfft(a) * gauss_tf(a.shape, sy, sx, angle), a.shape)


def blur_stack(a, sigmas):
    """One forward FFT, several isotropic blurs."""
    F = rfft(a)
    return [irfft(F * gauss_tf(a.shape, s), a.shape) for s in sigmas]


def _white_fft(shape, seed):
    rng = np.random.default_rng(seed)
    return rfft(rng.standard_normal(shape, dtype=np.float32))


def _normalize(n):
    n -= n.mean()
    n /= (n.std() + 1e-12)
    return n


def noise(shape, seed, sigma, sigma_x=None, angle=0.0):
    """Periodic band-limited Gaussian noise; zero mean, unit std."""
    return _normalize(irfft(_white_fft(shape, seed) * gauss_tf(shape, sigma, sigma_x, angle), shape))


def fbm(shape, seed, sigma, octaves=5, gain=0.5, lac=2.0, sigma_x=None, angle=0.0):
    """Fractal noise from one white-noise field with a composite spectrum."""
    W = _white_fft(shape, seed)
    filt = None
    amp = 1.0
    for i in range(octaves):
        s = sigma / lac ** i
        sx = (sigma if sigma_x is None else sigma_x) / lac ** i
        g = gauss_tf(shape, max(s, 0.35), max(sx, 0.35), angle) * (amp * math.sqrt(4 * math.pi * max(s, 0.35) * max(sx, 0.35)))
        filt = g if filt is None else filt + g
        amp *= gain
    return _normalize(irfft(W * filt, shape))


def to01(n):
    """Gaussian noise -> approximately uniform [0, 1]."""
    return (0.5 * (1.0 + special.erf(n * (1.0 / math.sqrt(2.0))))).astype(F32)


def ridge(n):
    """Sharp ridges where the noise crosses zero (1 at the ridge)."""
    return 1.0 - np.minimum(np.abs(n), 1.0)


# --------------------------------------------------------------------------
# Derivatives, normals, AO, curvature
# --------------------------------------------------------------------------
def dxdy(h):
    """Periodic Sobel derivatives in height-units per pixel: (d/dcol, d/drow)."""
    gx = np.roll(h, -1, 1) - np.roll(h, 1, 1)
    gy = np.roll(h, -1, 0) - np.roll(h, 1, 0)
    gx = (np.roll(gx, 1, 0) + 2 * gx + np.roll(gx, -1, 0)) * 0.125
    gy = (np.roll(gy, 1, 1) + 2 * gy + np.roll(gy, -1, 1)) * 0.125
    return gx, gy


def normal_map(h_m, px_m, strength=1.0):
    """Tangent-space normal, OpenGL convention (+Y = image up), unit vectors."""
    gx, gy = dxdy(h_m)
    k = strength / px_m
    sx = gx * k
    sy = gy * k
    inv = 1.0 / np.sqrt(sx * sx + sy * sy + 1.0)
    # surface z = h(u, v), v = image up = -row  ->  n = (-dh/du, -dh/dv, 1) = (-gx, +gy, 1)
    return np.stack([-sx * inv, sy * inv, inv], axis=-1).astype(F32)


def ao_map(h_m, px_m, radii_m=(0.004, 0.012, 0.035, 0.09), weights=(0.3, 0.3, 0.25, 0.15), strength=1.0):
    """Multi-radius height-difference ambient occlusion in [0, 1]."""
    F = rfft(h_m)
    acc = np.zeros(h_m.shape, F32)
    for r, w in zip(radii_m, weights):
        rp = max(r / px_m, 0.5)
        b = irfft(F * gauss_tf(h_m.shape, rp), h_m.shape)
        acc += w * np.maximum(b - h_m, 0.0) / r
    return np.clip(1.0 - strength * acc, 0.0, 1.0)


def curvature(h, sigma_px):
    """>0 on convex (raised) areas, <0 in cavities, in height units."""
    return h - blur(h, sigma_px)


def norm_pos(x, pct=99.0):
    """Scale a mostly-positive signal to [0, 1] by its percentile."""
    p = np.percentile(x[x > 0], pct) if np.any(x > 0) else 1.0
    return np.clip(x / (p + 1e-12), 0, 1)


def light_term(normal, L=(-0.45, 0.55, 0.70)):
    L = np.asarray(L, F32)
    L = L / np.linalg.norm(L)
    return np.clip(normal @ L, 0, 1)


# --------------------------------------------------------------------------
# Resampling
# --------------------------------------------------------------------------
def warp(a, dx, dy, order=1):
    """Periodic resample: out(p) = a(p + (dx, dy))."""
    H, W = a.shape[:2]
    yy, xx = igrid(H, W)
    coords = [yy + dy, xx + dx]
    if a.ndim == 3:
        return np.stack([ndi.map_coordinates(a[..., c], coords, order=order, mode='grid-wrap')
                         for c in range(a.shape[2])], -1).astype(F32)
    return ndi.map_coordinates(a, coords, order=order, mode='grid-wrap').astype(F32)


def sample(a, qy, qx, order=1):
    """Periodic sampling of `a` at continuous pixel coords (row, col)."""
    return ndi.map_coordinates(a, [qy, qx], order=order, mode='grid-wrap').astype(F32)


def gather_offset(field, eid, oy, ox):
    """Per-element decorrelated copy of a field: field(p + offset[eid])."""
    H, W = field.shape[:2]
    yy, xx = igrid(H, W)
    e = np.maximum(eid, 0)
    return field[(yy + oy[e]) % H, (xx + ox[e]) % W]


# --------------------------------------------------------------------------
# Scalar helpers
# --------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(F32)


def lerp(a, b, t):
    return a + (b - a) * t


def c255(*rgb):
    """sRGB 0-255 -> float32 0-1 colour."""
    if len(rgb) == 1:
        rgb = rgb[0]
    return np.asarray(rgb, F32) / 255.0


def mix(img, color, t):
    """Blend an (H,W,3) image toward a colour or image by mask t (H,W)."""
    t = np.asarray(t, F32)[..., None]
    return img * (1.0 - t) + np.asarray(color, F32) * t


def jitter_color(rgb, rng, dh=0.02, ds=0.08, dv=0.08):
    h, s, v = colorsys.rgb_to_hsv(*[float(x) for x in rgb])
    h = (h + rng.normal(0, dh)) % 1.0
    s = float(np.clip(s * (1 + rng.normal(0, ds)), 0, 1))
    v = float(np.clip(v * (1 + rng.normal(0, dv)), 0, 1))
    return np.asarray(colorsys.hsv_to_rgb(h, s, v), F32)


def srgb_to_lin(c):
    c = np.asarray(c, F32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(F32)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, F32), 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055).astype(F32)


def luminance(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def saturate_img(rgb, amount):
    l = luminance(rgb)[..., None]
    return l + (rgb - l) * amount


# --------------------------------------------------------------------------
# Element layouts (partitions of the torus into cells)
# --------------------------------------------------------------------------
def courses(W, H, rng, row_heights, len_range, min_stagger, first_offset=None):
    """Running-bond rows that wrap exactly. Returns rects (x0, y0, w, h, row)."""
    rh = np.asarray(row_heights, dtype=np.float64)
    rh = rh * (H / rh.sum())
    rects = []
    y = 0.0
    prev_joints = None
    for r, h in enumerate(rh):
        for _attempt in range(60):
            lens = []
            total = 0.0
            while total < W - len_range[1]:
                l = rng.uniform(*len_range)
                lens.append(l)
                total += l
            rest = W - total
            if rest < len_range[0]:
                lens[-1] += rest  # merge a short tail into the last block
            else:
                lens.append(rest)
            off = rng.uniform(0, W) if first_offset is None else first_offset
            joints = (off + np.cumsum([0.0] + lens[:-1])) % W
            if prev_joints is None:
                break
            dd = np.abs(wrapd(joints[:, None] - prev_joints[None, :], W))
            if dd.min() >= min_stagger:
                break
        x = off
        for l in lens:
            rects.append((x % W, y, l, h, r))
            x += l
        prev_joints = joints
        y += h
    return rects


def rect_ids(W, H, rects):
    """Exact id raster for rects (x0, y0, w, h, ...) covering the torus."""
    ids = np.full((H, W), -1, np.int32)
    for i, rc in enumerate(rects):
        x0, y0, w, h = rc[:4]
        c0 = int(math.ceil(x0 - 0.5))
        c1 = int(math.ceil(x0 + w - 0.5))
        r0 = int(math.ceil(y0 - 0.5))
        r1 = int(math.ceil(y0 + h - 0.5))
        cols = np.arange(c0, c1) % W
        rows = np.arange(r0, r1) % H
        ids[np.ix_(rows, cols)] = i
    return ids


class RectField:
    """Warped rectangle partition -> per-pixel id, local coords, stone distance."""

    def __init__(self, ctx: Ctx, rects, joint_px, radius_px, warp_px=0.0, warp_sigma_px=40.0,
                 rot_deg=0.0, radius_jitter=0.5, joint_jitter=0.3, fine_warp_px=0.0, fine_sigma_px=6.0):
        H, W = ctx.shape
        rng = ctx.rng
        n = len(rects)
        R = np.asarray([r[:4] for r in rects], np.float64)
        self.n = n
        self.rects = rects
        ids = rect_ids(W, H, rects)
        yy, xx = grid(H, W)
        qx = xx.copy()
        qy = yy.copy()
        if warp_px > 0:
            qx += noise(ctx.shape, ctx.key(), warp_sigma_px) * warp_px
            qy += noise(ctx.shape, ctx.key(), warp_sigma_px) * warp_px
        if fine_warp_px > 0:
            qx += noise(ctx.shape, ctx.key(), fine_sigma_px) * fine_warp_px
            qy += noise(ctx.shape, ctx.key(), fine_sigma_px) * fine_warp_px
        eid = ids[np.floor(qy).astype(np.int64) % H, np.floor(qx).astype(np.int64) % W]
        cx = (R[:, 0] + R[:, 2] * 0.5).astype(F32)
        cy = (R[:, 1] + R[:, 3] * 0.5).astype(F32)
        hw = (R[:, 2] * 0.5).astype(F32)
        hh = (R[:, 3] * 0.5).astype(F32)
        lx = wrapd(qx - cx[eid], W)
        ly = wrapd(qy - cy[eid], H)
        rot = np.deg2rad(rng.normal(0, rot_deg, n)).astype(F32) if rot_deg else np.zeros(n, F32)
        if rot_deg:
            c, s = np.cos(rot)[eid], np.sin(rot)[eid]
            lx, ly = lx * c + ly * s, -lx * s + ly * c
        jm = (joint_px * 0.5 * (1 + rng.uniform(-joint_jitter, joint_jitter, n))).astype(F32)
        rad = np.clip(radius_px * (1 + rng.uniform(-radius_jitter, radius_jitter, (n, 4))), 0.5, None).astype(F32)
        q = (lx > 0).astype(np.int32) + 2 * (ly > 0).astype(np.int32)
        r = rad[eid, q]
        ax = np.abs(lx) - (hw[eid] - jm[eid] - r)
        ay = np.abs(ly) - (hh[eid] - jm[eid] - r)
        outside = np.sqrt(np.maximum(ax, 0) ** 2 + np.maximum(ay, 0) ** 2)
        inside = np.minimum(np.maximum(ax, ay), 0)
        self.d = (-(outside + inside - r)).astype(F32)   # >0 inside the stone
        self.eid = eid
        self.lx, self.ly = lx.astype(F32), ly.astype(F32)
        self.hw, self.hh = hw - jm, hh - jm
        self.qx, self.qy = qx, qy
        self.cx, self.cy = cx, cy

    def uv(self):
        """Normalised position inside each stone (-1..1)."""
        e = self.eid
        return self.lx / np.maximum(self.hw[e], 1), self.ly / np.maximum(self.hh[e], 1)


def relax_points(pts, W, H, iters=2, samples=256):
    """Periodic Lloyd relaxation (sampled)."""
    pts = np.asarray(pts, np.float64) % [W, H]
    gy, gx = np.meshgrid((np.arange(samples) + 0.5) * H / samples, (np.arange(samples) + 0.5) * W / samples,
                         indexing='ij')
    g = np.stack([gx.ravel(), gy.ravel()], 1)
    for _ in range(iters):
        tree = cKDTree(pts, boxsize=[W, H])
        _, i = tree.query(g, workers=WORKERS)
        v = g - pts[i]
        v[:, 0] = wrapd(v[:, 0], W)
        v[:, 1] = wrapd(v[:, 1], H)
        cnt = np.bincount(i, minlength=len(pts)).astype(np.float64)
        sx = np.bincount(i, weights=v[:, 0], minlength=len(pts))
        sy = np.bincount(i, weights=v[:, 1], minlength=len(pts))
        ok = cnt > 0
        pts[ok, 0] += sx[ok] / cnt[ok]
        pts[ok, 1] += sy[ok] / cnt[ok]
        pts %= [W, H]
    return pts


class VoronoiField:
    """Periodic Voronoi partition with (smooth) distance to the cell border.

    `weights` (optional, per site) enlarge/shrink cells multiplicatively
    (a cheap power-diagram approximation) for size variety.
    """

    def __init__(self, ctx: Ctx, pts, k=6, smooth_px=0.0, warp_px=0.0, warp_sigma_px=30.0, aniso=(1.0, 1.0)):
        H, W = ctx.shape
        pts = np.asarray(pts, np.float64) % [W, H]
        ax, ay = aniso
        # anisotropic metric: scale space (keeps periodicity because the box scales too)
        spts = pts * [1.0 / ax, 1.0 / ay]
        box = [W / ax, H / ay]
        tree = cKDTree(spts % box, boxsize=box)
        yy, xx = grid(H, W)
        qx = xx.astype(np.float64)
        qy = yy.astype(np.float64)
        if warp_px > 0:
            qx = qx + noise(ctx.shape, ctx.key(), warp_sigma_px) * warp_px
            qy = qy + noise(ctx.shape, ctx.key(), warp_sigma_px) * warp_px
        q = np.stack([(qx.ravel() % W) / ax, (qy.ravel() % H) / ay], 1)
        n = q.shape[0]
        eid = np.empty(n, np.int32)
        dist = np.empty(n, F32)
        vx = np.empty(n, F32)
        vy = np.empty(n, F32)
        f1 = np.empty(n, F32)
        chunk = 1 << 19
        for s in range(0, n, chunk):
            qc = q[s:s + chunk]
            _, idx = tree.query(qc, k=k, workers=WORKERS)
            P = spts[idx]                       # (m, k, 2)
            v = P - qc[:, None, :]
            v[..., 0] = wrapd(v[..., 0], box[0])
            v[..., 1] = wrapd(v[..., 1], box[1])
            v0 = v[:, 0:1, :]
            l0 = (v0 ** 2).sum(-1)
            lj = (v[:, 1:, :] ** 2).sum(-1)
            dj = np.sqrt(((v[:, 1:, :] - v0) ** 2).sum(-1)) + 1e-9
            bis = (lj - l0) / (2 * dj)          # distance to each bisector
            if smooth_px > 0:
                kk = smooth_px
                m = bis.min(1)
                d = m - kk * np.log(np.exp(-(bis - m[:, None]) / kk).sum(1))
            else:
                d = bis.min(1)
            eid[s:s + chunk] = idx[:, 0]
            dist[s:s + chunk] = d * min(ax, ay)
            vx[s:s + chunk] = v0[:, 0, 0] * ax
            vy[s:s + chunk] = v0[:, 0, 1] * ay
            f1[s:s + chunk] = np.sqrt(l0[:, 0]) * min(ax, ay)
        self.eid = eid.reshape(H, W)
        self.d = dist.reshape(H, W)            # distance to cell border (>=0)
        self.vx = vx.reshape(H, W)             # vector pixel -> site
        self.vy = vy.reshape(H, W)
        self.f1 = f1.reshape(H, W)
        self.pts = pts
        self.n = len(pts)


def adjacency(eid, n, gap=3):
    """Neighbour lists of elements that touch within `gap` px."""
    pairs = []
    for dy, dx in ((0, gap), (gap, 0), (gap, gap), (gap, -gap)):
        b = np.roll(np.roll(eid, -dy, 0), -dx, 1)
        m = (eid != b) & (eid >= 0) & (b >= 0)
        if np.any(m):
            pairs.append(np.unique(eid[m].astype(np.int64) * n + b[m]))
    nb = [set() for _ in range(n)]
    if pairs:
        for p in np.unique(np.concatenate(pairs)):
            a, b = divmod(int(p), n)
            nb[a].add(b)
            nb[b].add(a)
    return nb


def assign_palette(n, palette, rng, neighbours=None, weights=None, jitter=(0.015, 0.06, 0.06)):
    """Per-element colours: palette pick avoiding neighbour repeats + HSV jitter."""
    palette = [np.asarray(c, F32) for c in palette]
    k = len(palette)
    w = np.ones(k) if weights is None else np.asarray(weights, np.float64)
    w = w / w.sum()
    choice = np.full(n, -1, np.int32)
    for i in rng.permutation(n):
        banned = {choice[j] for j in (neighbours[i] if neighbours else ()) if choice[j] >= 0}
        ww = np.array([0.0 if c in banned else w[c] for c in range(k)])
        if ww.sum() <= 0:
            ww = w.copy()
        choice[i] = rng.choice(k, p=ww / ww.sum())
    cols = np.stack([jitter_color(palette[c], rng, *jitter) for c in choice])
    return cols.astype(F32), choice


# --------------------------------------------------------------------------
# Strokes, cracks, carving
# --------------------------------------------------------------------------
def splat(shape, xs, ys, ws):
    """Bilinear splat of weighted points into a periodic image."""
    H, W = shape
    xs = np.asarray(xs, np.float64) - 0.5
    ys = np.asarray(ys, np.float64) - 0.5
    ws = np.broadcast_to(np.asarray(ws, np.float64), xs.shape)
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    fx = xs - x0
    fy = ys - y0
    acc = np.zeros(H * W, np.float64)
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        idx = ((y0 + dy) % H) * W + (x0 + dx) % W
        acc += np.bincount(idx, weights=ws * wt, minlength=H * W)
    return acc.reshape(H, W).astype(F32)


def walk(rng, x, y, angle, length_px, seg=(4.0, 14.0), dev=0.45, drift=0.10, step=0.5):
    """Jagged crack polyline: short straight segments around a drifting heading."""
    px, py = [x], [y]
    total = 0.0
    while total < length_px:
        L = rng.uniform(*seg)
        a = angle + rng.normal(0, dev)
        angle += rng.normal(0, drift)
        px.append(px[-1] + L * math.cos(a))
        py.append(py[-1] + L * math.sin(a))
        total += L
    px = np.asarray(px)
    py = np.asarray(py)
    seglen = np.hypot(np.diff(px), np.diff(py))
    s = np.concatenate([[0], np.cumsum(seglen)])
    t = np.arange(0, s[-1], step)
    return np.interp(t, s, px), np.interp(t, s, py)


def crack_mask(ctx, paths, width_px=0.7, taper=True):
    """Rasterise walks into a crisp line mask (0..1)."""
    xs, ys, ws = [], [], []
    for px, py, strength in paths:
        n = len(px)
        t = np.linspace(0, 1, n)
        w = np.sin(np.pi * np.clip(t, 0.02, 0.98)) ** 0.6 if taper else np.ones(n)
        xs.append(px)
        ys.append(py)
        ws.append(w * strength)
    if not xs:
        return np.zeros(ctx.shape, F32)
    acc = splat(ctx.shape, np.concatenate(xs), np.concatenate(ys), np.concatenate(ws))
    acc = blur(acc, width_px)
    return np.clip(acc * 2.2, 0, 1)


def carve(h, cx, cy, radius, depth, wall_px=1.5, rng=None, noise_amp=0.3, rough=None, floor_tilt=0.0,
          mask=None, top=None):
    """Chip/bite (in place): cut a broken facet `depth` below the local top.

    Inside a wobbly disc (radius px) the surface drops to a floor; the chip
    wall is `wall_px` wide, so small values give sharp, light-catching rims.
    """
    H, W = h.shape
    R = int(math.ceil(radius * (1 + noise_amp) + wall_px * 3 + 3))
    cyi, cxi = int(math.floor(cy)), int(math.floor(cx))
    ys = np.arange(cyi - R, cyi + R + 1)
    xs = np.arange(cxi - R, cxi + R + 1)
    iy, ix = ys % H, xs % W
    sub = h[np.ix_(iy, ix)]
    ly = (ys + 0.5 - cy)[:, None]
    lx = (xs + 0.5 - cx)[None, :]
    rr = np.sqrt(lx * lx + ly * ly)
    if rng is not None and noise_amp > 0:
        ang = np.arctan2(ly, lx)
        k = int(rng.integers(3, 7))
        wob = np.zeros_like(rr)
        for f in (k, k + 2, 2 * k + 1):
            wob += rng.uniform(0.3, 1.0) * np.sin(f * ang + rng.uniform(0, 2 * np.pi))
        rr = rr / (1 + noise_amp * wob / 2.3)
    inside = radius - rr
    if top is None:
        core = sub[inside > 0]
        top = np.percentile(core, 85) if core.size else sub.max()
    floor = top - depth
    if floor_tilt and rng is not None:
        a = rng.uniform(0, 2 * np.pi)
        floor = floor + floor_tilt * (math.cos(a) * lx + math.sin(a) * ly) / max(radius, 1.0)
    cap = floor + np.maximum(-inside, 0) * (depth / max(wall_px, 0.3))
    if rough is not None:
        cap = cap + rough[np.ix_(iy, ix)]
    new = np.minimum(sub, cap)
    if mask is not None:
        new = np.where(mask[np.ix_(iy, ix)], new, sub)
    h[np.ix_(iy, ix)] = new
    return h


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def to_u8(a, dither=True, seed=0):
    a = np.clip(np.asarray(a, F32), 0, 1) * 255.0
    if dither:
        a = a + (np.random.default_rng(seed).random(a.shape, dtype=np.float32) - 0.5)
    return np.clip(np.rint(a), 0, 255).astype(np.uint8)


def save_png(path, arr, mode=None, dither=True):
    from PIL import Image
    u8 = to_u8(arr, dither)
    if mode is None:
        mode = {2: 'L', 3: 'RGB'}[u8.ndim] if u8.ndim == 2 else ('RGBA' if u8.shape[2] == 4 else 'RGB')
    Image.fromarray(u8, mode).save(path, compress_level=6)


def seam_score(img):
    """Max ratio of wrap-edge gradient vs. interior gradient (≈1 means seamless)."""
    a = np.asarray(img, F32)
    if a.ndim == 3:
        a = a.mean(-1)
    inner_x = np.abs(np.diff(a, axis=1)).mean()
    inner_y = np.abs(np.diff(a, axis=0)).mean()
    edge_x = np.abs(a[:, 0] - a[:, -1]).mean()
    edge_y = np.abs(a[0, :] - a[-1, :]).mean()
    return max(edge_x / (inner_x + 1e-9), edge_y / (inner_y + 1e-9))
