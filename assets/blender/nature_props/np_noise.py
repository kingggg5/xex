"""Seeded 3D noise in pure numpy (no scipy), shared by the Blender recipes and the painter.

Every function is deterministic for (points, seed) on any machine: integer hashing on uint32 with explicit
wrap-around, float64 maths. Points are (N, 3) arrays in metres (or any unit; scale before calling).

  perlin3(p, seed)            gradient noise, about [-1, 1]
  fbm3(p, seed, octaves, ...) fractal sum of perlin3, about [-1, 1]
  ridged3(p, seed, ...)       1 - |perlin| fractal, [0, 1], sharp crests
  worley3(p, seed, jitter)    (F1, F2, cell_hash) for 3D cellular patterns
  value3(p, seed)             lattice value noise in [0, 1]
  hash01(int_array, seed)     per-id random number in [0, 1)
"""
from __future__ import annotations

import numpy as np

_M32 = np.uint64(0xFFFFFFFF)

_GRAD12 = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0],
                    [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
                    [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1]], dtype=np.float64)


def _u32(a):
    """int array (any sign) -> uint32 with two's-complement wrap."""
    return (np.asarray(a, dtype=np.int64) & 0xFFFFFFFF).astype(np.uint32)


def _mix(x):
    """lowbias32 integer hash (Chris Wellons), vectorised on uint32."""
    x = x.astype(np.uint32)
    with np.errstate(over="ignore"):
        x ^= x >> np.uint32(16)
        x *= np.uint32(0x7FEB352D)
        x ^= x >> np.uint32(15)
        x *= np.uint32(0x846CA68B)
        x ^= x >> np.uint32(16)
    return x


def hash3(ix, iy, iz, seed: int):
    with np.errstate(over="ignore"):
        s = np.uint32((int(seed) * 0x9E3779B1) & 0xFFFFFFFF)
        h = _mix(_u32(ix) * np.uint32(0x8DA6B343) ^ s)
        h = _mix(h ^ (_u32(iy) * np.uint32(0xD8163841)))
        h = _mix(h ^ (_u32(iz) * np.uint32(0xCB1AB31F)))
    return h


def hash01(ids, seed: int = 0):
    """Per-id random float in [0, 1)."""
    ids = np.asarray(ids)
    return hash3(ids, ids * 0 + 7, ids * 0 + 13, seed).astype(np.float64) / 4294967296.0


def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def perlin3(p, seed: int = 0):
    p = np.asarray(p, dtype=np.float64)
    pi = np.floor(p)
    pf = p - pi
    ix, iy, iz = (pi[:, k].astype(np.int64) for k in range(3))
    u = _fade(pf)
    out = np.zeros(len(p), dtype=np.float64)
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1.0 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1.0 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1.0 - u[:, 2]
                h = hash3(ix + dx, iy + dy, iz + dz, seed)
                g = _GRAD12[(h % np.uint32(12)).astype(np.int64)]
                d = pf - np.array([dx, dy, dz], dtype=np.float64)
                out += wx * wy * wz * np.einsum("ij,ij->i", g, d)
    return out * 1.1  # roughly [-1, 1]


def value3(p, seed: int = 0):
    p = np.asarray(p, dtype=np.float64)
    pi = np.floor(p)
    pf = p - pi
    ix, iy, iz = (pi[:, k].astype(np.int64) for k in range(3))
    u = _fade(pf)
    out = np.zeros(len(p), dtype=np.float64)
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1.0 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1.0 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1.0 - u[:, 2]
                h = hash3(ix + dx, iy + dy, iz + dz, seed).astype(np.float64) / 4294967296.0
                out += wx * wy * wz * h
    return out


def fbm3(p, seed: int = 0, octaves: int = 4, lacunarity: float = 2.03, gain: float = 0.5):
    p = np.asarray(p, dtype=np.float64)
    amp, total, norm = 1.0, np.zeros(len(p)), 0.0
    q = p.copy()
    for o in range(octaves):
        total += amp * perlin3(q, seed + 101 * o)
        norm += amp
        amp *= gain
        q = q * lacunarity + 17.31
    return total / norm


def ridged3(p, seed: int = 0, octaves: int = 3, lacunarity: float = 2.1, gain: float = 0.55):
    p = np.asarray(p, dtype=np.float64)
    amp, total, norm = 1.0, np.zeros(len(p)), 0.0
    q = p.copy()
    for o in range(octaves):
        total += amp * (1.0 - np.abs(perlin3(q, seed + 211 * o)))
        norm += amp
        amp *= gain
        q = q * lacunarity + 5.77
    return np.clip(total / norm, 0.0, 1.0)


def worley3(p, seed: int = 0, jitter: float = 0.9, chunk: int = 262144):
    """3D cellular noise. Returns F1, F2 (distances in cell units) and the uint32 hash of the nearest cell."""
    p = np.asarray(p, dtype=np.float64)
    n = len(p)
    f1 = np.empty(n)
    f2 = np.empty(n)
    cid = np.empty(n, dtype=np.uint32)
    offs = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
    for a in range(0, n, chunk):
        q = p[a:a + chunk]
        qi = np.floor(q)
        b1 = np.full(len(q), np.inf)
        b2 = np.full(len(q), np.inf)
        bid = np.zeros(len(q), dtype=np.uint32)
        for dx, dy, dz in offs:
            cx = qi[:, 0].astype(np.int64) + dx
            cy = qi[:, 1].astype(np.int64) + dy
            cz = qi[:, 2].astype(np.int64) + dz
            h = hash3(cx, cy, cz, seed)
            jx = _mix(h ^ np.uint32(0x68E31DA4)).astype(np.float64) / 4294967296.0
            jy = _mix(h ^ np.uint32(0xB5297A4D)).astype(np.float64) / 4294967296.0
            jz = _mix(h ^ np.uint32(0x1B56C4E9)).astype(np.float64) / 4294967296.0
            fx = cx + 0.5 + jitter * (jx - 0.5)
            fy = cy + 0.5 + jitter * (jy - 0.5)
            fz = cz + 0.5 + jitter * (jz - 0.5)
            d = np.sqrt((q[:, 0] - fx) ** 2 + (q[:, 1] - fy) ** 2 + (q[:, 2] - fz) ** 2)
            closer = d < b1
            b2 = np.where(closer, b1, np.minimum(b2, d))
            bid = np.where(closer, h, bid)
            b1 = np.where(closer, d, b1)
        f1[a:a + chunk] = b1
        f2[a:a + chunk] = b2
        cid[a:a + chunk] = bid
    return f1, f2, cid


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0 + 1e-12), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def fibonacci_sphere(n: int, rng=None, jitter: float = 0.0):
    i = np.arange(n, dtype=np.float64) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)
    theta = np.pi * (1.0 + 5.0 ** 0.5) * i
    pts = np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)
    if rng is not None and jitter > 0:
        pts = pts + rng.normal(0.0, jitter, pts.shape)
        pts /= np.linalg.norm(pts, axis=1, keepdims=True)
    return pts
