"""Claude forge: leaf-cluster atlas geometry -> data passes (Route A step 2, trees v4).

Builds real stylized leaf geometry in Blender (chunky ovate leaves with cupping, midrib crease and tilt,
twigs, conifer fronds with leaflets, red five-petal flowers and berries), lays the clusters out in a 3x3
atlas (1024 px layout: 320 px cells, 16 px gutters) and renders three orthographic data passes with
emission-only override materials (Cycles CPU, Raw view transform, point-sampled at 2x = 2048 px):

  normal.png  RGB = world normal * 0.5 + 0.5 (card space: +X right, +Y = texture up, +Z = card front), A = coverage
  aox.png     R = ambient occlusion (AO node, local cavity between overlapping leaves), G = layer height,
              B = per-part random value, A = coverage
  part.png    R = part class (0.1 twig, 0.3 leaf, 0.5 conifer leaflet, 0.7 petal, 0.8 flower centre, 0.9 berry),
              G = along-part coordinate t (base 0 -> tip 1), B = across-part coordinate (s * 0.5 + 0.5), A = coverage

paint_leaf_atlas.py (system Python) turns these passes into the painted albedo. Cell layout and the conifer
envelope (the kit's frond mesh outline in UV space, measured in probe/uv_dump.json) are written to
layout.json so the stylize script maps kit card UVs onto the same cells.

Usage:
  blender -b --factory-startup --python forge_leaf_atlas.py -- --out <dir> [--res 2048] [--seed 7]
"""
import argparse
import json
import math
import os
import random
import sys
import time

import bpy
import numpy as np

ATLAS_PX = 1024
CELL_PX, GUTTER_PX, STEP_PX = 320, 16, 336
# row 0 is the TOP image row; (row, col) -> name
CELLS = {(0, 0): "B1_rosette", (0, 1): "B2_spray", (0, 2): "B3_dense",
         (1, 0): "B4_fan", (1, 1): "B6_loose", (1, 2): "BB_blossom",
         (2, 0): "C1_frond", (2, 1): "C2_frond", (2, 2): "B5_bush"}
# kit Leaf_Pine frond mesh outline (UV space, v up), from probe/uv_dump.json (19 unique UVs of the 22-tri frond)
FROND_OUTLINE_UV = [(0.469, 0.0), (0.4, 0.138), (0.271, 0.298), (0.169, 0.498), (0.325, 0.675), (0.354, 0.817),
                    (0.502, 0.999), (0.627, 0.817), (0.704, 0.675), (0.802, 0.498), (0.821, 0.298), (0.643, 0.138),
                    (0.598, 0.0)]
CLASS = {"twig": 0.1, "leaf": 0.3, "leaflet": 0.5, "petal": 0.7, "centre": 0.8, "berry": 0.9}


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--res", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--ao-distance", type=float, default=0.014)
    a, _ = ap.parse_known_args(argv)
    return a


def cell_rect_uv(row, col):
    """(u0, v0, u1, v1) of a cell in UV space (v up)."""
    x0 = (GUTTER_PX + col * STEP_PX) / ATLAS_PX
    y_top = (GUTTER_PX + row * STEP_PX) / ATLAS_PX
    return (x0, 1.0 - y_top - CELL_PX / ATLAS_PX, x0 + CELL_PX / ATLAS_PX, 1.0 - y_top)


# ---------------------------------------------------------------------------------------------------------
# part generators: return dict(v=(N,3), f=list of index tuples, t=(N,), s=(N,)) in cell-normalised units
# (cell spans -0.5..0.5; +y = texture up; z = height above the card plane, toward the viewer)
# ---------------------------------------------------------------------------------------------------------

def leaf_part(L, W, cup=0.18, curl=0.0, crease=0.05, a=0.75, b=0.85, wave=0.0, waves=4, serr=0.0, serr_n=7,
              nt=12, ns=6, base_w=0.05):
    vs, ts, ss = [], [], []
    for i in range(nt + 1):
        t = i / nt
        w = W * (math.sin(math.pi * min(1.0, t ** a))) ** b
        w *= 1.0 + wave * math.sin(math.pi * waves * t) ** 2
        if serr > 0:
            w *= 1.0 - serr * (abs(math.sin(math.pi * serr_n * t)) ** 0.6)
        if t < 0.08:
            w = max(w, W * base_w)
        for j in range(ns + 1):
            s = -1.0 + 2.0 * j / ns
            x = s * w
            y = t * L
            z = cup * (s * s) * w - crease * W * (1.0 - abs(s)) ** 3 + curl * (t * t) * L
            vs.append((x, y, z))
            ts.append(t)
            ss.append(s)
    faces = []
    for i in range(nt):
        for j in range(ns):
            a0 = i * (ns + 1) + j
            faces.append((a0, a0 + 1, a0 + ns + 2, a0 + ns + 1))
    return {"v": np.array(vs, np.float64), "f": faces, "t": np.array(ts), "s": np.array(ss)}


def tube_part(points, r0, r1, sides=6):
    """Tube along a polyline (twig / rachis), radius tapering r0 -> r1."""
    pts = np.asarray(points, np.float64)
    n = len(pts)
    vs, ts, ss, faces = [], [], [], []
    for i, p in enumerate(pts):
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        d /= max(np.linalg.norm(d), 1e-9)
        side = np.cross(d, (0, 0, 1.0))
        side /= max(np.linalg.norm(side), 1e-9)
        up = np.cross(side, d)
        r = r0 + (r1 - r0) * i / max(1, n - 1)
        for k in range(sides):
            ang = 2 * math.pi * k / sides
            vs.append(p + r * (math.cos(ang) * side + math.sin(ang) * up))
            ts.append(i / max(1, n - 1))
            ss.append(math.cos(ang))
    for i in range(n - 1):
        for k in range(sides):
            a0, a1 = i * sides + k, i * sides + (k + 1) % sides
            faces.append((a0, a1, a1 + sides, a0 + sides))
    return {"v": np.array(vs), "f": faces, "t": np.array(ts), "s": np.array(ss)}


def sphere_part(r, squash=1.0, seg=10, rings=7):
    vs, ts, ss, faces = [], [], [], []
    for i in range(rings + 1):
        th = math.pi * i / rings
        for k in range(seg):
            ph = 2 * math.pi * k / seg
            vs.append((r * math.sin(th) * math.cos(ph), r * math.sin(th) * math.sin(ph), squash * r * math.cos(th)))
            ts.append(i / rings)
            ss.append(math.cos(ph))
    for i in range(rings):
        for k in range(seg):
            a0, a1 = i * seg + k, i * seg + (k + 1) % seg
            faces.append((a0, a1, a1 + seg, a0 + seg))
    return {"v": np.array(vs), "f": faces, "t": np.array(ts), "s": np.array(ss)}


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def place(part, angle, base, z, roll=0.0, pitch=0.0):
    """Orient a part built along +Y: roll about its axis, pitch its tip up (+) / down (-), point it along `angle`
    (radians from +X), move its base to `base` (x, y) at height z."""
    R = rot_z(angle - math.pi / 2) @ rot_x(pitch) @ rot_y(roll)
    v = part["v"] @ R.T
    v[:, 0] += base[0]
    v[:, 1] += base[1]
    v[:, 2] += z
    out = dict(part)
    out["v"] = v
    return out


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def shrink_poly(poly, k):
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in poly]


# ---------------------------------------------------------------------------------------------------------
# cluster builders (cell-normalised coordinates)
# ---------------------------------------------------------------------------------------------------------

def leaf(rng, L, ratio=0.44, **kw):
    return leaf_part(L, L * ratio * rng.uniform(0.9, 1.1), cup=rng.uniform(0.12, 0.26), curl=rng.uniform(-0.06, 0.1),
                     crease=rng.uniform(0.03, 0.07), a=rng.uniform(0.68, 0.85), b=rng.uniform(0.75, 0.95),
                     wave=rng.uniform(0.0, 0.06), **kw)


def add(parts, cls, part, rnd):
    part = dict(part)
    part["cls"] = CLASS[cls]
    part["rnd"] = rnd
    parts.append(part)


def twig(parts, rng, pts, r0=0.012, r1=0.006):
    add(parts, "twig", tube_part(pts, r0, r1), rng.random())


def ring(parts, rng, n, L, base_r, z0, z1, phase=0.0, jitter=0.18, fan=(0, 2 * math.pi), ratio=0.44, lmin=0.88):
    a0, a1 = fan
    span = a1 - a0
    full = abs(span - 2 * math.pi) < 1e-6
    for k in range(n):
        ang = a0 + span * (k + (0.5 if not full else 0.0)) / n + phase + rng.uniform(-jitter, jitter)
        Lk = L * rng.uniform(lmin, 1.06)
        b = (base_r * math.cos(ang), base_r * math.sin(ang))
        p = place(leaf(rng, Lk, ratio), ang, b, rng.uniform(z0, z1), roll=rng.uniform(-0.3, 0.3),
                  pitch=rng.uniform(-0.15, 0.12))
        add(parts, "leaf", p, rng.random())


def clamp_disk(parts, rmax=0.395):
    """Uniformly shrink a cluster about the cell centre so every vertex lies inside radius rmax."""
    r = max(float(np.max(np.linalg.norm(p["v"][:, :2], axis=1))) for p in parts)
    if r > rmax:
        k = rmax / r
        for p in parts:
            p["v"] = p["v"] * np.array([k, k, k])
    return parts


def clump(parts, rng, n, L, spread, ratio=0.5, z0=0.0, dir_jitter=0.55, up_bias=0.0, centre=(0.0, 0.0), lrange=(0.75, 1.1)):
    """Organic leaf clump: bases scattered in a small disk, leaves pointing outward (+/- jitter), centre leaves on top."""
    cx, cy = centre
    for k in range(n):
        r = spread * math.sqrt(rng.random())
        th = rng.uniform(0, 2 * math.pi)
        bx, by = cx + r * math.cos(th), cy + r * math.sin(th)
        out = th if r > 0.15 * spread else rng.uniform(0, 2 * math.pi)
        ang = out + rng.uniform(-dir_jitter, dir_jitter)
        if up_bias:
            ang = math.atan2(math.sin(ang) + up_bias, math.cos(ang))
        Lk = L * rng.uniform(*lrange) * (1.0 - 0.25 * (1.0 - r / max(spread, 1e-6)))
        z = z0 + 0.022 * (1.0 - r / max(spread, 1e-6)) + rng.uniform(0.0, 0.008)
        q = place(leaf(rng, Lk, ratio), ang, (bx, by), z, roll=rng.uniform(-0.32, 0.32), pitch=rng.uniform(-0.18, 0.22))
        add(parts, "leaf", q, rng.random())
    for k in range(max(2, n // 5)):                 # cap leaves on top of the clump centre
        r = 0.35 * spread * math.sqrt(rng.random())
        th = rng.uniform(0, 2 * math.pi)
        ang = rng.uniform(0, 2 * math.pi)
        if up_bias:
            ang = math.atan2(math.sin(ang) + up_bias, math.cos(ang))
        q = place(leaf(rng, L * rng.uniform(0.6, 0.8), ratio), ang, (cx + r * math.cos(th), cy + r * math.sin(th)),
                  z0 + 0.03 + rng.uniform(0.0, 0.006), roll=rng.uniform(-0.3, 0.3), pitch=rng.uniform(-0.05, 0.2))
        add(parts, "leaf", q, rng.random())


def build_B1(rng):
    parts = []
    twig(parts, rng, [(0.0, -0.24, 0.0), (0.01, -0.14, 0.004), (0.0, -0.03, 0.008)])
    clump(parts, rng, 12, 0.3, 0.13, ratio=0.56)
    return clamp_disk(parts)


def build_B2(rng):
    parts = []
    path = [(-0.26, -0.27, 0.0), (-0.15, -0.15, 0.004), (-0.03, -0.01, 0.008), (0.09, 0.12, 0.012), (0.2, 0.25, 0.014)]
    twig(parts, rng, path, 0.013, 0.006)
    pts = np.array(path)
    for k in range(13):
        t = 0.12 + 0.86 * k / 12
        seg = min(int(t * (len(pts) - 1)), len(pts) - 2)
        f = t * (len(pts) - 1) - seg
        p = pts[seg] * (1 - f) + pts[seg + 1] * f
        d = pts[seg + 1] - pts[seg]
        da = math.atan2(d[1], d[0])
        side = 1 if k % 2 == 0 else -1
        ang = da + side * rng.uniform(0.7, 1.05)
        L = 0.27 * (1.0 - 0.35 * t) * rng.uniform(0.9, 1.08)
        q = place(leaf(rng, L, 0.46), ang, (p[0], p[1]), p[2] + rng.uniform(0.0, 0.006) + 0.004 * k / 12,
                  roll=rng.uniform(-0.5, 0.5), pitch=rng.uniform(-0.2, 0.3))
        add(parts, "leaf", q, rng.random())
    for ang in (0.55, 1.05, 1.6):
        q = place(leaf(rng, 0.17, 0.46), ang, (0.2, 0.26), 0.018 + rng.uniform(0, 0.004), roll=rng.uniform(-0.4, 0.4),
                  pitch=rng.uniform(0.0, 0.3))
        add(parts, "leaf", q, rng.random())
    return clamp_disk(parts)


def build_B3(rng):
    parts = []
    twig(parts, rng, [(0.02, -0.24, 0.0), (0.0, -0.13, 0.004), (0.01, -0.03, 0.008)])
    clump(parts, rng, 14, 0.26, 0.15, ratio=0.55)
    return clamp_disk(parts)


def build_B4(rng):
    parts = []
    twig(parts, rng, [(-0.03, -0.25, 0.0), (-0.02, -0.15, 0.004), (0.0, -0.06, 0.008)])
    clump(parts, rng, 10, 0.34, 0.1, ratio=0.58, up_bias=0.55, dir_jitter=0.45, centre=(0.0, -0.06))
    return clamp_disk(parts)


def build_B6(rng):
    parts = []
    twig(parts, rng, [(0.0, -0.3, 0.0), (-0.02, -0.2, 0.004), (-0.08, -0.05, 0.006), (-0.15, 0.1, 0.008)])
    twig(parts, rng, [(-0.02, -0.2, 0.004), (0.1, -0.1, 0.006), (0.19, 0.02, 0.008)], 0.009, 0.005)
    sub = []
    ring(sub, rng, 6, 0.2, 0.02, 0.000, 0.008, phase=0.3)
    ring(sub, rng, 3, 0.14, 0.0, 0.010, 0.016, phase=1.1)
    for p in sub:
        p["v"] = p["v"] + np.array([-0.16, 0.13, 0.0])
    parts += sub
    sub = []
    ring(sub, rng, 5, 0.18, 0.02, 0.002, 0.008, phase=0.8)
    ring(sub, rng, 2, 0.12, 0.0, 0.012, 0.016, phase=0.1)
    for p in sub:
        p["v"] = p["v"] + np.array([0.2, 0.03, 0.0])
    parts += sub
    for ang in (-1.2, -1.9):
        q = place(leaf(rng, 0.17), ang, (0.0, -0.18), 0.004, roll=rng.uniform(-0.4, 0.4), pitch=rng.uniform(-0.2, 0.2))
        add(parts, "leaf", q, rng.random())
    return clamp_disk(parts)


def build_B5(rng):
    """Bush cluster: many small, cupped leaves in a dense dome."""
    parts = []
    twig(parts, rng, [(0.0, -0.22, 0.0), (0.0, -0.1, 0.004)], 0.01, 0.006)
    ring(parts, rng, 9, 0.25, 0.07, 0.000, 0.006, phase=0.3, ratio=0.58)
    ring(parts, rng, 6, 0.19, 0.03, 0.008, 0.012, phase=0.8, ratio=0.58)
    clump(parts, rng, 3, 0.16, 0.05, ratio=0.6, z0=0.006)
    return clamp_disk(parts)


def flower(parts, rng, cx, cy, z, size):
    rot0 = rng.uniform(0, 2 * math.pi)
    rnd = rng.random()
    for k in range(5):
        ang = rot0 + 2 * math.pi * k / 5 + rng.uniform(-0.08, 0.08)
        p = leaf_part(size, size * 0.62, cup=0.22, curl=0.08, crease=0.02, a=1.0, b=0.6, nt=8, ns=5, base_w=0.2)
        q = place(p, ang, (cx, cy), z + 0.002 * k / 5, roll=rng.uniform(-0.15, 0.15), pitch=rng.uniform(0.04, 0.16))
        add(parts, "petal", q, rnd)
    c = sphere_part(size * 0.32, squash=0.55)
    c["v"] = c["v"] + np.array([cx, cy, z + 0.008])
    add(parts, "centre", c, rnd)


def build_BB(rng):
    """Blossom / berry cluster: dark bush leaves under red five-petal flowers and a red berry bunch."""
    parts = []
    twig(parts, rng, [(0.0, -0.22, 0.0), (0.0, -0.1, 0.004)], 0.01, 0.006)
    ring(parts, rng, 8, 0.25, 0.05, 0.000, 0.006, phase=0.2, ratio=0.5)
    ring(parts, rng, 4, 0.17, 0.02, 0.006, 0.010, phase=0.9, ratio=0.5)
    flower(parts, rng, -0.12, 0.09, 0.10, 0.1)
    flower(parts, rng, 0.13, 0.12, 0.11, 0.09)
    flower(parts, rng, 0.02, -0.12, 0.10, 0.095)
    for k in range(7):
        bx = 0.17 + rng.uniform(-0.06, 0.06)
        by = -0.1 + rng.uniform(-0.07, 0.06)
        s = sphere_part(rng.uniform(0.024, 0.032))
        s["v"] = s["v"] + np.array([bx, by, 0.09 + rng.uniform(0, 0.006)])
        add(parts, "berry", s, rng.random())
    for k in range(4):
        bx = -0.2 + rng.uniform(-0.05, 0.05)
        by = -0.12 + rng.uniform(-0.05, 0.05)
        s = sphere_part(rng.uniform(0.022, 0.028))
        s["v"] = s["v"] + np.array([bx, by, 0.088 + rng.uniform(0, 0.004)])
        add(parts, "berry", s, rng.random())
    return clamp_disk(parts)


def frond(rng, variant):
    """Conifer tier frond inside the kit frond outline (cell coords: u-0.5, v-0.5)."""
    env = shrink_poly([(u - 0.5, v - 0.5) for u, v in FROND_OUTLINE_UV], 0.965)
    parts = []
    rach = [(0.002 + 0.006 * math.sin(3 * t), -0.5 + 0.985 * t, 0.004 + 0.004 * t) for t in np.linspace(0, 1, 9)]
    add(parts, "twig", tube_part(rach, 0.014, 0.004), rng.random())

    def env_len(x0, y0, ang, lmax):
        L = lmax
        while L > 0.02:
            ok = True
            for f in (0.5, 0.8, 1.0):
                if not point_in_poly(x0 + f * L * math.cos(ang), y0 + f * L * math.sin(ang), env):
                    ok = False
                    break
            if ok:
                return L
            L *= 0.92
        return 0.0

    def leaflet(L, W):
        return leaf_part(L, W, cup=0.25, curl=-0.05, crease=0.04, a=0.55, b=0.9, serr=0.32, serr_n=5, nt=12, ns=4,
                         base_w=0.3)

    if variant == 1:
        n = 22
        for k in range(n):
            t = 0.06 + 0.9 * k / (n - 1)
            y0 = -0.5 + 0.985 * t
            for side in (-1, 1):
                ang = math.pi / 2 - side * math.radians(rng.uniform(48, 62))
                L = env_len(0.0, y0, ang, 0.36)
                if L < 0.03:
                    continue
                L *= rng.uniform(0.9, 1.0)
                q = place(leaflet(L, L * 0.2), ang, (0.0, y0), 0.002 + 0.006 * t + rng.uniform(0, 0.004),
                          roll=side * rng.uniform(0.15, 0.45), pitch=rng.uniform(-0.15, 0.15))
                add(parts, "leaflet", q, rng.random())
        for k in range(14):                       # upper layer of short leaflets for density
            t = 0.1 + 0.85 * k / 13
            y0 = -0.5 + 0.985 * t
            side = 1 if k % 2 else -1
            ang = math.pi / 2 - side * math.radians(rng.uniform(30, 45))
            L = env_len(0.0, y0, ang, 0.2) * rng.uniform(0.7, 0.9)
            if L < 0.03:
                continue
            q = place(leaflet(L, L * 0.24), ang, (0.0, y0), 0.014 + 0.004 * t, roll=side * 0.3,
                      pitch=rng.uniform(0.0, 0.2))
            add(parts, "leaflet", q, rng.random())
        tip = place(leaflet(0.12, 0.03), math.pi / 2, (0.0, 0.36), 0.016)
        add(parts, "leaflet", tip, rng.random())
    else:
        subs = [(0.12, -1), (0.2, 1), (0.33, -1), (0.42, 1), (0.55, -1), (0.63, 1), (0.76, -1), (0.83, 1)]
        for t, side in subs:
            y0 = -0.5 + 0.985 * t
            ang = math.pi / 2 - side * math.radians(rng.uniform(40, 52))
            L = env_len(0.0, y0, ang, 0.4) * rng.uniform(0.92, 1.0)
            if L < 0.05:
                continue
            ax = (math.cos(ang), math.sin(ang))
            sub_r = [(ax[0] * L * f, y0 + ax[1] * L * f, 0.006 + 0.004 * f) for f in np.linspace(0, 1, 5)]
            add(parts, "twig", tube_part(sub_r, 0.007, 0.003), rng.random())
            m = 6
            for j in range(m):
                f = 0.12 + 0.85 * j / (m - 1)
                bx, by = ax[0] * L * f, y0 + ax[1] * L * f
                for s2 in (-1, 1):
                    a2 = ang + s2 * math.radians(rng.uniform(40, 55))
                    l2 = env_len(bx, by, a2, 0.14 * (1.15 - 0.6 * f))
                    if l2 < 0.025:
                        continue
                    q = place(leaflet(l2, l2 * 0.26), a2, (bx, by), 0.008 + 0.006 * f + rng.uniform(0, 0.003),
                              roll=s2 * rng.uniform(0.1, 0.4), pitch=rng.uniform(-0.1, 0.2))
                    add(parts, "leaflet", q, rng.random())
            q = place(leaflet(min(0.13, L * 0.4), 0.03), ang, (ax[0] * L * 0.92, y0 + ax[1] * L * 0.92), 0.016)
            add(parts, "leaflet", q, rng.random())
        for k in range(12):                       # short leaflets hugging the rachis
            t = 0.05 + 0.9 * k / 11
            y0 = -0.5 + 0.985 * t
            side = 1 if k % 2 else -1
            ang = math.pi / 2 - side * math.radians(rng.uniform(25, 40))
            L = env_len(0.0, y0, ang, 0.15) * rng.uniform(0.75, 0.95)
            if L < 0.03:
                continue
            q = place(leaflet(L, L * 0.25), ang, (0.0, y0), 0.018, roll=side * 0.25, pitch=0.1)
            add(parts, "leaflet", q, rng.random())
        tip = place(leaflet(0.14, 0.035), math.pi / 2, (0.0, 0.34), 0.02)
        add(parts, "leaflet", tip, rng.random())
    # keep every leaflet vertex inside the kit outline (clip overshoot by pulling toward the rachis)
    for p in parts:
        v = p["v"]
        for i in range(len(v)):
            x, y = v[i, 0], v[i, 1]
            k = 1.0
            while not point_in_poly(x * k, y, env) and k > 0.05:
                k *= 0.95
            v[i, 0] = x * k
    return parts


BUILDERS = {"B1_rosette": build_B1, "B2_spray": build_B2, "B3_dense": build_B3, "B4_fan": build_B4,
            "B6_loose": build_B6, "BB_blossom": build_BB, "B5_bush": build_B5,
            "C1_frond": lambda rng: frond(rng, 1), "C2_frond": lambda rng: frond(rng, 2)}


# ---------------------------------------------------------------------------------------------------------
# scene
# ---------------------------------------------------------------------------------------------------------

def make_mesh(all_parts):
    V, F, T, S, C, R = [], [], [], [], [], []
    off = 0
    for p in all_parts:
        n = len(p["v"])
        V.append(p["v"])
        F.extend(tuple(i + off for i in f) for f in p["f"])
        T.append(p["t"])
        S.append(p["s"])
        C.append(np.full(n, p["cls"]))
        R.append(np.full(n, p["rnd"]))
        off += n
    V = np.concatenate(V)
    me = bpy.data.meshes.new("atlas_geo")
    me.from_pydata([tuple(v) for v in V], [], F)
    me.update()
    for name, data in (("pt", np.concatenate(C)), ("lt", np.concatenate(T)), ("ls", np.concatenate(S)),
                       ("rnd", np.concatenate(R))):
        at = me.attributes.new(name, "FLOAT", "POINT")
        at.data.foreach_set("value", data.astype(np.float32))
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new("atlas_geo", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob, len(V), len(F)


def attr_node(nt, name):
    n = nt.nodes.new("ShaderNodeAttribute")
    n.attribute_type = "GEOMETRY"
    n.attribute_name = name
    return n


def emission_material(name, builder):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    builder(nt, em)
    return mat


def build_normal(nt, em):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "MULTIPLY_ADD"
    mul.inputs[1].default_value = (0.5, 0.5, 0.5)
    mul.inputs[2].default_value = (0.5, 0.5, 0.5)
    nt.links.new(geo.outputs["Normal"], mul.inputs[0])
    nt.links.new(mul.outputs["Vector"], em.inputs["Color"])


def make_build_aox(ao_dist, zmax):
    def build(nt, em):
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.samples = 32
        ao.inside = False
        ao.only_local = False
        ao.inputs["Distance"].default_value = ao_dist
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
        div = nt.nodes.new("ShaderNodeMath")
        div.operation = "DIVIDE"
        div.inputs[1].default_value = zmax
        nt.links.new(sep.outputs["Z"], div.inputs[0])
        rnd = attr_node(nt, "rnd")
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(ao.outputs["AO"], comb.inputs["X"])
        nt.links.new(div.outputs["Value"], comb.inputs["Y"])
        nt.links.new(rnd.outputs["Fac"], comb.inputs["Z"])
        nt.links.new(comb.outputs["Vector"], em.inputs["Color"])
    return build


def build_part(nt, em):
    pt, lt, ls = attr_node(nt, "pt"), attr_node(nt, "lt"), attr_node(nt, "ls")
    ma = nt.nodes.new("ShaderNodeMath")
    ma.operation = "MULTIPLY_ADD"
    ma.inputs[1].default_value = 0.5
    ma.inputs[2].default_value = 0.5
    nt.links.new(ls.outputs["Fac"], ma.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(pt.outputs["Fac"], comb.inputs["X"])
    nt.links.new(lt.outputs["Fac"], comb.inputs["Y"])
    nt.links.new(ma.outputs["Value"], comb.inputs["Z"])
    nt.links.new(comb.outputs["Vector"], em.inputs["Color"])


def main():
    a = parse()
    t0 = time.time()
    os.makedirs(a.out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.filter_width = 0.01            # point sampling: pure per-pixel data, AA comes from the 2x downsample
    scene.cycles.max_bounces = 0
    scene.render.resolution_x = a.res
    scene.render.resolution_y = a.res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.dither_intensity = 0.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "16"
    scene.render.image_settings.compression = 15
    scene.view_settings.view_transform = "Raw"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    world = bpy.data.worlds.new("black")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    scene.world = world

    rng = random.Random(a.seed)
    cs = CELL_PX / ATLAS_PX
    all_parts, layout = [], {"atlas_px": ATLAS_PX, "cell_px": CELL_PX, "gutter_px": GUTTER_PX, "step_px": STEP_PX,
                             "uv_convention": "Blender UV (v up); glTF/image rows are v flipped",
                             "cells": {}, "frond_outline_uv": FROND_OUTLINE_UV, "seed": a.seed}
    stats = {}
    for (row, col), name in CELLS.items():
        parts = BUILDERS[name](rng)
        u0, v0, u1, v1 = cell_rect_uv(row, col)
        cx, cy = (u0 + u1) / 2, (v0 + v1) / 2
        for p in parts:
            p["v"] = p["v"] * cs + np.array([cx, cy, 0.0])
        all_parts += parts
        layout["cells"][name] = {"row": row, "col": col, "uv_rect": [round(u0, 6), round(v0, 6), round(u1, 6), round(v1, 6)],
                                 "px_rect_top_left": [GUTTER_PX + col * STEP_PX, GUTTER_PX + row * STEP_PX, CELL_PX, CELL_PX],
                                 "kind": "conifer" if name.startswith("C") else ("blossom" if name == "BB_blossom" else
                                                                                ("bush" if name == "B5_bush" else "broadleaf")),
                                 "parts": {k: sum(1 for p in parts if p["cls"] == v) for k, v in CLASS.items()}}
        stats[name] = layout["cells"][name]["parts"]
    ob, nv, nf = make_mesh(all_parts)
    zmax = float(max(np.max(p["v"][:, 2]) for p in all_parts)) + 1e-4
    layout["z_max_world"] = zmax
    cam_data = bpy.data.cameras.new("ortho")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 1.0
    cam_data.clip_start = 0.01
    cam_data.clip_end = 100
    cam = bpy.data.objects.new("ortho", cam_data)
    cam.location = (0.5, 0.5, 5.0)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    passes = [("normal", emission_material("m_normal", build_normal), 4),
              ("aox", emission_material("m_aox", make_build_aox(a.ao_distance, zmax)), 6),
              ("part", emission_material("m_part", build_part), 4)]
    timings = {}
    for name, mat, spp in passes:
        t1 = time.time()
        scene.view_layers[0].material_override = mat
        scene.cycles.samples = spp
        scene.render.filepath = os.path.join(a.out, f"{name}.png")
        bpy.ops.render.render(write_still=True)
        timings[name] = round(time.time() - t1, 2)
        print("RENDERED", name, timings[name], flush=True)
    layout["render"] = {"res": a.res, "engine": "CYCLES", "device": "CPU", "view_transform": "Raw",
                        "filter_width_px": 0.01, "ao_distance_world": a.ao_distance, "seconds": timings,
                        "vertices": nv, "faces": nf}
    layout["seconds_total"] = round(time.time() - t0, 2)
    with open(os.path.join(a.out, "layout.json"), "w", encoding="utf-8") as fh:
        json.dump(layout, fh, indent=1)
    print("WROTE", a.out, json.dumps(stats))


main()
