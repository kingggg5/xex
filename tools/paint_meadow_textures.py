"""Hand-painted meadow ground and dirt-road textures (art pass v1, 2026-10-02).

Deterministic (seeded) painter; writes sRGB PNGs into apps/client/src/assets/world/:

  meadow_grass_painted_albedo.png   1024 x 1024 RGB, tiles both ways (game: 6 m world repeat)
  meadow_grass_painted_normal.png   1024 x 1024, weak, derived from the painted height
  meadow_road_painted_albedo.png    512 x 1024 RGBA strip. U runs across the road (alpha = ragged grass
                                    edge, alpha-tested at 0.5), V runs along it and tiles (game: 10 m)
  meadow_road_painted_normal.png    512 x 1024
  stone_painted_albedo.png          512 x 512 RGB, tiles both ways (dressed stone: arch, posts, waystone)
  stone_painted_normal.png          512 x 512

Look target (llm.txt LOOK TARGET): WoW-like hand-painted ground. Readable clumps instead of photo noise,
warm sunlit blade tips over cool dark gaps, warm tan road with painted pebbles and grass creeping over
its edges. Low high-frequency noise so it holds up at the 13-17 m game camera.

  python tools/paint_meadow_textures.py [--preview planning/evidence/art-pass-v1/textures-preview.png]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps" / "client" / "src" / "assets" / "world"
SS = 2  # supersampling for anti-aliased strokes


def srgb(hex_colour: str) -> np.ndarray:
    hex_colour = hex_colour.lstrip("#")
    return np.array([int(hex_colour[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def tile_noise(h: int, w: int, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """Periodic smooth noise in [0, 1] (wrap-mode blur of white noise)."""
    n = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), sigma, mode="wrap")
    n -= n.min()
    return n / max(1e-6, n.max())


def fbm(h: int, w: int, sigmas, weights, rng) -> np.ndarray:
    acc = sum(wt * tile_noise(h, w, s, rng) for s, wt in zip(sigmas, weights))
    acc -= acc.min()
    return acc / max(1e-6, acc.max())


def wrap_offsets(x: float, y: float, reach: float, w: int, h: int, wrap_x: bool, wrap_y: bool):
    """Copies needed so a stroke near a border also appears on the opposite side (tileable)."""
    xs = [0]
    ys = [0]
    if wrap_x:
        if x < reach:
            xs.append(w)
        if x > w - reach:
            xs.append(-w)
    if wrap_y:
        if y < reach:
            ys.append(h)
        if y > h - reach:
            ys.append(-h)
    return [(dx, dy) for dx in xs for dy in ys]


def fill(img: np.ndarray, pts, colour, wrap_x=True, wrap_y=True):
    """Anti-aliased convex polygon on a uint8 canvas, wrapped across tile borders."""
    h, w = img.shape[:2]
    pts = np.asarray(pts, dtype=np.float32)
    cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
    reach = float(np.abs(pts - [cx, cy]).max()) + 2
    c = tuple(int(round(v)) for v in colour)
    for dx, dy in wrap_offsets(cx, cy, reach, w, h, wrap_x, wrap_y):
        p = ((pts + [dx, dy]) * 8).round().astype(np.int32)
        cv2.fillConvexPoly(img, p, c, lineType=cv2.LINE_AA, shift=3)


def ellipse(img, cx, cy, rx, ry, angle_deg, colour, wrap_x=True, wrap_y=True):
    h, w = img.shape[:2]
    c = tuple(int(round(v)) for v in colour)
    for dx, dy in wrap_offsets(cx, cy, max(rx, ry) + 2, w, h, wrap_x, wrap_y):
        cv2.ellipse(img, (int(round((cx + dx) * 8)), int(round((cy + dy) * 8))),
                    (max(1, int(round(rx * 8))), max(1, int(round(ry * 8)))), angle_deg, 0, 360, c, -1,
                    lineType=cv2.LINE_AA, shift=3)


def blade(img, x, y, angle, length, width, root_c, tip_c, bend, wrap_x=True, wrap_y=True, segments=3):
    """Tapered, slightly curved grass blade seen from above: dark root -> lit tip in `segments` bands."""
    dirx, diry = math.cos(angle), math.sin(angle)
    nx, ny = -diry, dirx
    pts_l, pts_r = [], []
    for k in range(segments + 1):
        t = k / segments
        curve = bend * t * t * length
        px = x + dirx * length * t + nx * curve
        py = y + diry * length * t + ny * curve
        half = width * 0.5 * (1.0 - t) ** 0.85
        pts_l.append((px + nx * half, py + ny * half))
        pts_r.append((px - nx * half, py - ny * half))
    for k in range(segments):
        t = (k + 0.5) / segments
        colour = root_c * (1 - t) + tip_c * t
        fill(img, [pts_l[k], pts_l[k + 1], pts_r[k + 1], pts_r[k]], colour * 255, wrap_x, wrap_y)


def blur_wrap(a: np.ndarray, sigma: float, wrap_x=True, wrap_y=True) -> np.ndarray:
    mode = ["wrap" if wrap_y else "nearest", "wrap" if wrap_x else "nearest"]
    if a.ndim == 3:
        mode.append("nearest")
        sigma = (sigma, sigma, 0)
    return gaussian_filter(a, sigma, mode=mode)


def normal_from_height(height: np.ndarray, strength: float, wrap_x=True, wrap_y=True) -> np.ndarray:
    hy = np.roll(height, -1, 0) - np.roll(height, 1, 0) if wrap_y else np.gradient(height, axis=0) * 2
    hx = np.roll(height, -1, 1) - np.roll(height, 1, 1) if wrap_x else np.gradient(height, axis=1) * 2
    n = np.stack([-hx * strength, hy * strength, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return ((n * 0.5 + 0.5) * 255).round().clip(0, 255).astype(np.uint8)


def to_uint8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0, 1) * 255).round().astype(np.uint8)


def downsample(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (w // SS, h // SS), interpolation=cv2.INTER_AREA)


# --------------------------------------------------------------------------------------------------
# Grass ground
# --------------------------------------------------------------------------------------------------
GRASS_DARK = srgb("#2f4a26")     # gaps between clumps (cool, deep)
GRASS_MID = srgb("#637f37")      # body colour
GRASS_WARM = srgb("#93a047")     # sunny patches
GRASS_TIP = srgb("#b9c96a")      # lit blade tips
GRASS_TIP_WARM = srgb("#d6cf7a") # dry-gold tips (sparse)
GRASS_COOL_TIP = srgb("#86a65a") # cooler tips in the darker patches
CLOVER = srgb("#49693a")


def paint_grass(size=1024, seed=20261002):
    rng = np.random.default_rng(seed)
    pyrng = np.random.default_rng(seed + 1)
    S = size * SS
    # Broad tonal patches (periodic): which areas read warm/sunny vs deep.
    patch = fbm(S, S, (S / 9, S / 22, S / 60), (0.55, 0.3, 0.15), rng)
    warmth = fbm(S, S, (S / 7, S / 30), (0.7, 0.3), rng)
    base = (GRASS_DARK[None, None] * (1 - patch[..., None]) + GRASS_MID[None, None] * patch[..., None])
    base = base * (1 - 0.35 * warmth[..., None]) + (base * 0.6 + GRASS_WARM * 0.4) * 0.35 * warmth[..., None]
    canvas = to_uint8(base)

    # Soft contact shade under every clump keeps depth between blades.
    shade = np.zeros((S, S), np.uint8)
    tufts = []
    count = 1080
    for _ in range(count):
        x, y = pyrng.uniform(0, S), pyrng.uniform(0, S)
        tufts.append((x, y))
        r = pyrng.uniform(9, 17) * SS
        ellipse(shade, x, y, r, r * pyrng.uniform(0.6, 1.0), pyrng.uniform(0, 180), (255,))
    shade_f = blur_wrap(shade.astype(np.float32) / 255.0, 5 * SS)
    canvas = to_uint8(canvas.astype(np.float32) / 255.0 * (1 - 0.38 * shade_f[..., None]))

    height = np.zeros((S, S), np.float32)
    hcanvas = np.zeros((S, S, 3), np.uint8)
    # Clover leaves sit low, under the blades.
    for _ in range(170):
        x, y = pyrng.uniform(0, S), pyrng.uniform(0, S)
        r = pyrng.uniform(3.2, 5.2) * SS
        a0 = pyrng.uniform(0, math.tau)
        tone = CLOVER * pyrng.uniform(0.85, 1.15)
        for k in range(3):
            a = a0 + k * math.tau / 3
            ellipse(canvas, x + math.cos(a) * r * 0.9, y + math.sin(a) * r * 0.9, r, r * 0.8, math.degrees(a),
                    np.clip(tone, 0, 1) * 255)
            ellipse(canvas, x + math.cos(a) * r * 1.05 - r * 0.2, y + math.sin(a) * r * 1.05 - r * 0.2, r * 0.45, r * 0.3,
                    math.degrees(a), np.clip(tone * 1.35, 0, 1) * 255)
    # Blades: tufts fan out from a centre with a shared lean (top-down view), tips catch the light.
    order = pyrng.permutation(len(tufts))
    for i in order:
        x, y = tufts[i]
        p = patch[int(y) % S, int(x) % S]
        wm = warmth[int(y) % S, int(x) % S]
        lean = pyrng.uniform(0, math.tau)
        n = int(pyrng.integers(6, 13))
        vigour = 0.75 + 0.5 * p  # sunny patches grow longer, warmer clumps
        for _ in range(n):
            ang = lean + pyrng.normal(0, 0.9)
            length = pyrng.uniform(12, 32) * SS * vigour
            width = pyrng.uniform(3.6, 6.4) * SS
            tip = GRASS_COOL_TIP * (1 - p) + GRASS_TIP * p
            if pyrng.random() < 0.10 + 0.25 * wm:
                tip = tip * 0.5 + GRASS_TIP_WARM * 0.5
            tip = np.clip(tip * pyrng.uniform(0.88, 1.10), 0, 1)
            root = GRASS_DARK * 0.65 + GRASS_MID * 0.35
            blade(canvas, x, y, ang, length, width, root, tip, pyrng.uniform(-0.25, 0.25))
            blade(hcanvas, x, y, ang, length, width, np.array([0.35] * 3), np.array([1.0] * 3), 0.0)
    # Sparse bright sparkle strokes (thin, short) on top.
    for _ in range(900):
        x, y = pyrng.uniform(0, S), pyrng.uniform(0, S)
        ang = pyrng.uniform(0, math.tau)
        blade(canvas, x, y, ang, pyrng.uniform(6, 13) * SS, pyrng.uniform(1.6, 2.4) * SS,
              GRASS_TIP * 0.8, np.clip(GRASS_TIP * 1.12, 0, 1), 0.0, segments=2)
    height = np.maximum(height, hcanvas[..., 0].astype(np.float32) / 255.0)

    albedo = downsample(canvas).astype(np.float32) / 255.0
    # Painterly softening: a light wrap blur mixed back keeps strokes but removes pixel crunch.
    albedo = albedo * 0.75 + blur_wrap(albedo, 0.9) * 0.25
    # Saturation lift around the mean luminance (hand-painted, not photographic).
    lum = albedo @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # On-screen the lighting + ACES + the +16 saturation grade add ~0.1 saturation; keep the texture neutral.
    albedo = np.clip(lum[..., None] + (albedo - lum[..., None]) * 1.0, 0, 1)
    h_small = downsample(height)
    h_small = blur_wrap(h_small, 0.8)
    normal = normal_from_height(h_small, 2.2)
    return to_uint8(albedo), normal


# --------------------------------------------------------------------------------------------------
# Dirt road strip
# --------------------------------------------------------------------------------------------------
DIRT_LIGHT = srgb("#c9ad7a")
DIRT_MID = srgb("#a8885a")
DIRT_RUT = srgb("#8a6c45")
DIRT_EDGE = srgb("#7b6a40")
PEBBLE_TONES = [srgb(c) for c in ("#a59c88", "#bdb39d", "#8f8676", "#b3a58a", "#9a8f7d", "#c4bba6")]


def paint_road(width=512, length=1024, seed=20261003):
    rng = np.random.default_rng(seed)
    pyrng = np.random.default_rng(seed + 1)
    W, H = width * SS, length * SS
    u = (np.arange(W, dtype=np.float32) + 0.5) / W
    # Ragged edge: margin from each side varies along V (periodic) and with fine notches.
    edge_lo = fbm(H, 1, (H / 10, H / 40), (0.7, 0.3), rng)[:, 0]
    edge_hi = fbm(H, 1, (H / 10, H / 40), (0.7, 0.3), rng)[:, 0]
    margin_l = 0.09 + 0.11 * edge_lo
    margin_r = 0.09 + 0.11 * edge_hi
    uu = np.broadcast_to(u[None, :], (H, W))
    # 0 at the edge line, positive inside the road (in U units).
    inside = np.minimum(uu - margin_l[:, None], (1 - uu) - margin_r[:, None])
    mott = fbm(H, W, (W / 6, W / 18, W / 50), (0.5, 0.33, 0.17), rng)
    centre = np.clip(1 - np.abs(uu - 0.5) / 0.38, 0, 1)
    # Wheel ruts waver along the road and fade in and out (periodic in V).
    wob_l = (fbm(H, 1, (H / 6, H / 24), (0.7, 0.3), rng)[:, 0] - 0.5) * 0.06
    wob_r = (fbm(H, 1, (H / 6, H / 24), (0.7, 0.3), rng)[:, 0] - 0.5) * 0.06
    fade = 0.45 + 0.55 * fbm(H, 1, (H / 8,), (1.0,), rng)[:, 0]
    ruts = (np.exp(-((uu - 0.315 - wob_l[:, None]) / 0.042) ** 2)
            + np.exp(-((uu - 0.685 - wob_r[:, None]) / 0.042) ** 2)) * fade[:, None]
    rut_noise = fbm(H, W, (W / 20, W / 60), (0.6, 0.4), rng)
    ruts = ruts * (0.65 + 0.35 * rut_noise)
    col = DIRT_MID[None, None] * (1 - centre[..., None] * 0.6) + DIRT_LIGHT[None, None] * centre[..., None] * 0.6
    col = col * (0.88 + 0.24 * mott[..., None])
    ruts = np.clip(ruts, 0, 1)
    col = col * (1 - 0.6 * ruts[..., None]) + DIRT_RUT * 0.6 * ruts[..., None]
    # Grassy crown between the wheel ruts (classic country road), faint green bleed under the tufts.
    crown = np.exp(-((uu - 0.5) / 0.06) ** 2) * (0.4 + 0.6 * fbm(H, W, (W / 10, W / 30), (0.6, 0.4), rng))
    col = col * (1 - 0.35 * crown[..., None]) + (GRASS_MID * 0.8 + DIRT_MID * 0.2) * 0.35 * crown[..., None]
    edge_band = np.clip(1 - inside / 0.10, 0, 1)
    col = col * (1 - edge_band[..., None] * 0.7) + DIRT_EDGE * edge_band[..., None] * 0.7
    canvas = to_uint8(col)
    height = (0.5 - 0.25 * ruts + 0.1 * mott).astype(np.float32)
    hcanvas = to_uint8(np.repeat(height[..., None], 3, -1))
    alpha = (inside > 0).astype(np.uint8) * 255

    def polygon(cx, cy, r, squash, ang, jag):
        k = int(pyrng.integers(6, 10))
        a = np.sort(pyrng.uniform(0, math.tau, k))
        rad = r * (1 - jag + jag * pyrng.uniform(0.4, 1.0, k))
        ca, sa = math.cos(ang), math.sin(ang)
        pts = []
        for ai, ri in zip(a, rad):
            x, y = math.cos(ai) * ri, math.sin(ai) * ri * squash
            pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
        return cv2.convexHull(np.array(pts, np.float32)).reshape(-1, 2)

    def stone(cx, cy, r, tone, buried):
        """Flat, chipped stone: soft contact shadow, darker rim, matte body, one lit top-left facet."""
        ang = pyrng.uniform(0, math.pi)
        squash = pyrng.uniform(0.55, 0.92)
        body = polygon(cx, cy, r, squash, ang, 0.35)
        fill(canvas, body + [r * 0.18, r * 0.24], np.clip(DIRT_RUT * 0.62, 0, 1) * 255, False, True)
        fill(canvas, body, np.clip(tone * 0.78, 0, 1) * 255, False, True)
        inner = (body - [cx, cy]) * 0.8 + [cx - r * 0.06, cy - r * 0.08]
        fill(canvas, inner, np.clip(tone, 0, 1) * 255, False, True)
        facet = (body - [cx, cy]) * 0.42 + [cx - r * 0.24, cy - r * 0.26]
        fill(canvas, facet, np.clip(tone * 1.10 + 0.02, 0, 1) * 255, False, True)
        if buried:
            lip = (body - [cx, cy]) * [0.95, 0.4] + [cx, cy + r * squash * 0.62]
            fill(canvas, lip, np.clip(DIRT_MID * 0.92, 0, 1) * 255, False, True)
        fill(hcanvas, body, (225, 225, 225), False, True)

    density = fbm(H, W, (W / 5, W / 14), (0.6, 0.4), rng)
    shoulder_w = np.clip(1 - np.minimum(uu - margin_l[:, None], (1 - uu) - margin_r[:, None]) / 0.16, 0, 1)

    def place(n, r_lo, r_hi, buried, avoid_ruts):
        placed = 0
        tries = 0
        while placed < n and tries < n * 40:
            tries += 1
            cx, cy = pyrng.uniform(0.06, 0.94) * W, pyrng.uniform(0, H)
            iy, ix = int(cy) % H, int(cx) % W
            if inside[iy, ix] < 0.01:
                continue
            w = 0.25 + 0.9 * density[iy, ix] ** 2 + 0.6 * shoulder_w[iy, ix]
            if avoid_ruts:
                w *= 1 - 0.8 * ruts[iy, ix]
            if pyrng.random() > w / 1.75:
                continue
            tone = PEBBLE_TONES[int(pyrng.integers(len(PEBBLE_TONES)))] * pyrng.uniform(0.9, 1.06)
            stone(cx, cy, pyrng.uniform(r_lo, r_hi) * SS, tone, buried)
            placed += 1

    # Painterly dirt grain: short dabs a shade lighter/darker than the ground under them.
    for _ in range(3200):
        cx, cy = pyrng.uniform(0.04, 0.96) * W, pyrng.uniform(0, H)
        iy, ix = int(cy) % H, int(cx) % W
        if inside[iy, ix] < 0:
            continue
        under = canvas[iy, ix].astype(np.float32) / 255.0
        k = pyrng.choice((0.86, 0.9, 1.08, 1.12))
        ellipse(canvas, cx, cy, pyrng.uniform(1.6, 3.6) * SS, pyrng.uniform(0.8, 1.6) * SS, pyrng.uniform(0, 180),
                np.clip(under * k, 0, 1) * 255, False, True)
    place(22, 9, 15, True, True)    # half-buried flat stones
    place(130, 4, 8, False, True)   # gravel stones
    place(520, 1.4, 3.6, False, False)  # grit
    # Fine cracks and dark clods in the packed dirt.
    for _ in range(60):
        cx, cy = pyrng.uniform(0.15, 0.85) * W, pyrng.uniform(0, H)
        ang = pyrng.uniform(0, math.tau)
        blade(canvas, cx, cy, ang, pyrng.uniform(8, 22) * SS, pyrng.uniform(1.0, 1.8) * SS,
              DIRT_RUT * 0.75, DIRT_RUT * 0.9, pyrng.uniform(-0.4, 0.4), False, True, segments=2)
    # Grassy crown tufts between the ruts.
    for _ in range(90):
        cx = (0.5 + pyrng.normal(0, 0.035)) * W
        cy = pyrng.uniform(0, H)
        if crown[int(cy) % H, int(cx) % W] < 0.35:
            continue
        lean = pyrng.uniform(0, math.tau)
        for _ in range(int(pyrng.integers(4, 9))):
            ang = lean + pyrng.normal(0, 1.0)
            tip = np.clip(GRASS_TIP * pyrng.uniform(0.85, 1.05), 0, 1)
            blade(canvas, cx, cy, ang, pyrng.uniform(8, 20) * SS, pyrng.uniform(2.6, 4.4) * SS,
                  GRASS_DARK * 0.6 + GRASS_MID * 0.4, tip, pyrng.uniform(-0.25, 0.25), False, True)

    # Grass creeping over both shoulders: tufts rooted outside the dirt, blades leaning onto it.
    acanvas = np.zeros((H, W, 3), np.uint8)
    acanvas[..., 0] = alpha
    for _ in range(520):
        left = pyrng.random() < 0.5
        cy = pyrng.uniform(0, H)
        row = int(cy) % H
        m = margin_l[row] if left else margin_r[row]
        off = pyrng.normal(0.0, 0.035)
        cx = ((m + off) if left else (1 - m - off)) * W
        inward = 0.0 if left else math.pi
        n = int(pyrng.integers(5, 11))
        for _ in range(n):
            ang = inward + pyrng.normal(0, 0.75)
            length = pyrng.uniform(12, 30) * SS
            width = pyrng.uniform(3.4, 6.0) * SS
            tip = np.clip((GRASS_TIP if pyrng.random() < 0.7 else GRASS_TIP_WARM) * pyrng.uniform(0.85, 1.05), 0, 1)
            root = GRASS_DARK * 0.6 + GRASS_MID * 0.4
            bend = pyrng.uniform(-0.25, 0.25)
            blade(canvas, cx, cy, ang, length, width, root, tip, bend, False, True)
            blade(acanvas, cx, cy, ang, length, width, np.array([1.0] * 3), np.array([1.0] * 3), bend, False, True)
            blade(hcanvas, cx, cy, ang, length, width, np.array([0.6] * 3), np.array([1.0] * 3), bend, False, True)
    albedo = downsample(canvas).astype(np.float32) / 255.0
    albedo = albedo * 0.8 + blur_wrap(albedo, 0.8, wrap_x=False) * 0.2
    a = downsample(acanvas)[..., 0]
    # Outside the alpha-tested edge, bleed the shoulder colour so filtering never pulls in black texels.
    bleed = blur_wrap(albedo * (a[..., None] / 255.0), 6, wrap_x=False) / np.maximum(1e-3, blur_wrap(a.astype(np.float32) / 255.0, 6, wrap_x=False))[..., None]
    albedo = np.where(a[..., None] > 0, albedo, np.clip(bleed, 0, 1))
    rgba = np.dstack([to_uint8(albedo), a])
    h_small = downsample(hcanvas)[..., 0].astype(np.float32) / 255.0
    normal = normal_from_height(blur_wrap(h_small, 0.7, wrap_x=False), 2.6, wrap_x=False)
    return rgba, normal



# --------------------------------------------------------------------------------------------------
# Dressed stone (arch, posts, waystone, pads, stepping stones; box-UV 2.4 m tile in the cells)
# --------------------------------------------------------------------------------------------------
STONE_WARM = srgb("#b3aa98")
STONE_COOL = srgb("#9a9a99")
STONE_DEEP = srgb("#6f6a62")
STONE_LIGHT = srgb("#d3cab6")
LICHEN = srgb("#a39c6a")
MOSS = srgb("#76884a")


def paint_stone(size=512, seed=20261004):
    """Dressed stone that reads as ONE block per arch voussoir at game distance: an almost flat warm grey
    with low-amplitude mottling, painted chips (lit top-left facet, dark lower lip), pits, a few hairline
    cracks and sparse muted lichen. Edges and cavities come from the mesh bevels and vertex paint."""
    rng = np.random.default_rng(seed)
    pyrng = np.random.default_rng(seed + 1)
    S = size * SS
    broad = fbm(S, S, (S / 3,), (1.0,), rng)
    mottle = fbm(S, S, (S / 10, S / 24), (0.6, 0.4), rng)
    grain = fbm(S, S, (S / 70, S / 160), (0.6, 0.4), rng)
    warm = fbm(S, S, (S / 6,), (1.0,), rng)
    base = STONE_COOL[None, None] * (1 - warm[..., None]) + STONE_WARM[None, None] * warm[..., None]
    col = base * (0.94 + 0.08 * broad[..., None]) * (0.88 + 0.22 * mottle[..., None]) * (0.95 + 0.10 * grain[..., None])
    canvas = to_uint8(col)
    height = np.full((S, S), 0.5, np.float32)
    hcanvas = to_uint8(np.repeat(height[..., None], 3, -1))

    def chip(cx, cy, r):
        k = int(pyrng.integers(4, 7))
        a = np.sort(pyrng.uniform(0, math.tau, k))
        pts = np.stack([cx + np.cos(a) * r * pyrng.uniform(0.6, 1.0, k), cy + np.sin(a) * r * pyrng.uniform(0.6, 1.0, k)], -1)
        hull = cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2)
        under = canvas[int(cy) % S, int(cx) % S].astype(np.float32) / 255.0
        fill(canvas, hull + [r * 0.18, r * 0.22], np.clip(under * 0.72, 0, 1) * 255)   # dark lower lip
        fill(canvas, hull, np.clip(under * 1.06, 0, 1) * 255)                              # lit chipped facet
        fill(hcanvas, hull, (90, 90, 90))

    for _ in range(34):
        chip(pyrng.uniform(0, S), pyrng.uniform(0, S), pyrng.uniform(2.5, 6.0) * SS)
    for _ in range(260):  # pits
        cx, cy = pyrng.uniform(0, S), pyrng.uniform(0, S)
        under = canvas[int(cy) % S, int(cx) % S].astype(np.float32) / 255.0
        r = pyrng.uniform(0.8, 1.8) * SS
        ellipse(canvas, cx, cy, r, r * pyrng.uniform(0.6, 1.0), pyrng.uniform(0, 180), np.clip(under * 0.78, 0, 1) * 255)
    for _ in range(5):  # hairline cracks: one gently curving stroke each
        cx, cy = pyrng.uniform(0, S), pyrng.uniform(0, S)
        ang = pyrng.uniform(0, math.tau)
        length = pyrng.uniform(30, 70) * SS
        under = canvas[int(cy) % S, int(cx) % S].astype(np.float32) / 255.0
        blade(canvas, cx, cy, ang, length, pyrng.uniform(1.0, 1.5) * SS, np.clip(under * 0.62, 0, 1),
              np.clip(under * 0.8, 0, 1), pyrng.uniform(-0.25, 0.25), segments=4)
        blade(hcanvas, cx, cy, ang, length, 1.3 * SS, np.array([0.15] * 3), np.array([0.35] * 3), 0.0, segments=2)
    for colour, count in ((LICHEN, 7), (MOSS, 4)):
        for _ in range(count):
            cx, cy = pyrng.uniform(0, S), pyrng.uniform(0, S)
            for _ in range(int(pyrng.integers(3, 6))):
                under = canvas[int(cy) % S, int(cx) % S].astype(np.float32) / 255.0
                tint = np.clip(under * 0.5 + colour * 0.5 * pyrng.uniform(0.85, 1.05), 0, 1)
                ellipse(canvas, cx + pyrng.normal(0, 4) * SS, cy + pyrng.normal(0, 4) * SS, pyrng.uniform(1.8, 3.6) * SS,
                        pyrng.uniform(1.4, 2.8) * SS, pyrng.uniform(0, 180), tint * 255)
    albedo = downsample(canvas).astype(np.float32) / 255.0
    albedo = albedo * 0.8 + blur_wrap(albedo, 0.8) * 0.2
    h = downsample(hcanvas)[..., 0].astype(np.float32) / 255.0
    normal = normal_from_height(blur_wrap(h, 1.0), 2.0)
    return to_uint8(albedo), normal


def save_png(path: Path, arr: np.ndarray):
    # cv2.imwrite silently fails on non-ASCII Windows paths (this repo lives under a Thai user name).
    from PIL import Image
    Image.fromarray(arr, "RGBA" if arr.shape[2] == 4 else "RGB").save(path, optimize=True)
    if not path.exists():
        raise RuntimeError(f"failed to write {path}")


def preview(grass: np.ndarray, road: np.ndarray, out: Path):
    """2x2 grass tiles with the road strip laid over the middle (alpha-tested at 0.5), plus a 1/4-scale
    copy that approximates the texel density at the game camera's mid distance."""
    g = np.tile(grass, (2, 2, 1))
    h, w = g.shape[:2]
    rh = h
    # Game texel densities: grass 1024 px / 6 m, road 512 px across ~5 m -> scale the road to match.
    k = (1024 / 6.0) / (512 / 5.0)
    road = cv2.resize(road, (int(road.shape[1] * k), int(road.shape[0] * k)), interpolation=cv2.INTER_LINEAR)
    strip = np.tile(road, (2, 1, 1))[:rh]
    x0 = (w - strip.shape[1]) // 2
    mask = strip[..., 3:4] >= 128
    region = g[:, x0:x0 + strip.shape[1]]
    g[:, x0:x0 + strip.shape[1]] = np.where(mask, strip[..., :3], region)
    small = cv2.resize(g, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    canvas = np.full((h, w + w // 4 + 16, 3), 24, np.uint8)
    canvas[:, :w] = g
    canvas[:h // 4, w + 16:] = small
    save_png(out, canvas)


MANIFEST = ROOT / "assets" / "models" / "world-v1" / "painted-texture-manifest.json"
OUTPUTS = {
    "meadow_grass_painted_albedo.png": ("RGB", "sRGB", "ground albedo, tiles both ways; game repeat 6 m"),
    "meadow_grass_painted_normal.png": ("RGB", "linear, +Y, weak (from painted height)", "ground normal"),
    "meadow_road_painted_albedo.png": ("RGBA", "sRGB; alpha = ragged grass shoulder, alpha-tested at 0.5",
                                       "road strip: U across the road (clamped), V along (tiles, 10 m)"),
    "meadow_road_painted_normal.png": ("RGB", "linear, +Y (from painted height)", "road strip normal"),
    "stone_painted_albedo.png": ("RGB", "sRGB", "dressed stone (arch, posts, waystone, pads), tiles both ways"),
    "stone_painted_normal.png": ("RGB", "linear, +Y (from facet tilt)", "dressed stone normal"),
}


def write_manifest():
    """Provenance for the painted runtime textures (kept apart from tools/build_world_textures.py's manifest)."""
    import hashlib
    import json
    from PIL import Image
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    script = Path(__file__).resolve()
    records = []
    for name, (channels, colourspace, use) in OUTPUTS.items():
        path = OUT / name
        records.append({"runtime": f"apps/client/src/assets/world/{name}", "runtime_sha256": sha(path),
                        "pixels": list(Image.open(path).size), "channels": channels, "colorspace": colourspace,
                        "use": use, "bytes": path.stat().st_size})
    MANIFEST.write_text(json.dumps({
        "schema": "xexoria.painted-textures/1",
        "generator": "tools/paint_meadow_textures.py",
        "generator_sha256": sha(script),
        "deterministic": True,
        "note": "Art pass v1 (2026-10-02). Re-run the generator to reproduce byte-identical PNGs.",
        "textures": records,
    }, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="")
    args = ap.parse_args()
    grass, grass_n = paint_grass()
    road, road_n = paint_road()
    stone, stone_n = paint_stone()
    save_png(OUT / "stone_painted_albedo.png", stone)
    save_png(OUT / "stone_painted_normal.png", stone_n)
    save_png(OUT / "meadow_grass_painted_albedo.png", grass)
    save_png(OUT / "meadow_grass_painted_normal.png", grass_n)
    save_png(OUT / "meadow_road_painted_albedo.png", road)
    save_png(OUT / "meadow_road_painted_normal.png", road_n)
    write_manifest()
    for name, arr in (("grass", grass), ("road", road[..., :3])):
        m = arr.reshape(-1, 3).mean(0)
        print(f"{name}: mean sRGB {m.round(1)} std {arr.reshape(-1, 3).std(0).round(1)}")
    print(f"road alpha coverage {(road[..., 3] >= 128).mean():.3f}")
    if args.preview:
        out = Path(args.preview)
        out.parent.mkdir(parents=True, exist_ok=True)
        preview(grass, road, out)
        print("preview", out)


if __name__ == "__main__":
    main()
