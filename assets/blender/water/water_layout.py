"""Sunmeadow natural water: layout JSON -> derived water geometry (pure Python + numpy, no bpy).

Procedural contract (owner direction 2026-10-02 21:35, "try to make procedural"):
  every water surface, bank, depth, flow and foam input is derived here from the layout polylines and
  polygons, deterministically from SEED. A layout change regenerates everything with no hand edits; the
  bake receipt records the seed and the input hashes.

Spec: docs/reviews/2026-10-02-map-water-spec.md (sections 3, 4, 8). Amendments A1 (pool at (-9.6,-38),
r 2.6) and A2 (stream exit P8/P9 with two cascades) are applied here when the layout does not carry them
yet, and the derived output records that they were applied.

Coordinates: Babylon world (+x east, +z north, +y up), metres. Blender = (-bx, -bz, by), the v2 blockout
convention (sm2_geom.bl); the glTF exporter then maps Blender (x, y, z) -> Babylon (-x, z, -y).
Left of the flow is +u (seen from above with north up, facing south, left is east).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
LAYOUT_PATH = REPO / "planning" / "levels" / "sunmeadow-v2-layout.json"
SEED = 20261002
SCHEMA = "xexoria.water-derived/1"
PX_PER_M = 12.5            # mask-atlas texel density (8 cm texels)
ATLAS_PAD = 4              # px around every island
EXTEND_UNDER_BANK = 0.15   # the surface mesh runs this far under the banks (depth-hidden)
WATER_Y = -0.35            # layout invariant: stream and pool surface
HAZARD_OFFSET = 0.7        # spec 4.9
TAU = math.tau

# Spec 3 (derived centreline table) for the v2 layout. Keys sit on the control points O, P1..P6, then the
# gap (-56,-58) and cascade-1 (-60.6,-59.2) points projected on the curve, then P8 and P9.
SPEC_WIDTH_KEYS = [3.0, 3.2, 3.6, 3.8, 4.3, 4.5, 4.2, 3.8, 3.4, 3.0, 2.6]
SPEC_DC_KEYS = [0.40, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.50, 0.55, 0.55, 0.40]
V2_STREAM_POINTS = [(-10.5, -38), (-11, -44), (-14, -49.5), (-20, -52.5), (-30, -54), (-42, -54), (-52, -57), (-64, -60)]
A1_POOL = ((-9.6, -38.0), 2.6)
A2_TAIL = [(-68.5, -63.5), (-70.5, -69.0)]
GAP_POINT = (-56.0, -58.0)
CASCADE_POINTS = [((-60.6, -59.2), -0.85), (A2_TAIL[0], -1.45)]   # lip point, surface Y after the lip
BLUFF_TOE_X = -7.0
POOL_LOBES = ((5, 0.6, 1.3), (7, 0.4, 4.1))   # (lobes, weight, phase): r = R + 0.15 * sum(w sin(k th + ph))
POOL_LOBE_AMP = 0.15
JUNCTION_K = 2.0           # smooth-union radius of the pool/stream join (a flared outlet, no folds in the bank strip)


# ----------------------------------------------------------------------------------------------------------
# Small numeric helpers (numpy-aware)
# ----------------------------------------------------------------------------------------------------------

def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smin(a, b, k):
    """Polynomial smooth minimum (union of two signed distance fields with a fillet of radius ~k)."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def keyed(s, keys_s, keys_v):
    """Smoothstep interpolation between (s, value) keys; constant beyond the ends."""
    ks = np.asarray(keys_s, dtype=float)
    kv = np.asarray(keys_v, dtype=float)
    s = np.asarray(s, dtype=float)
    i = np.clip(np.searchsorted(ks, s, side="right") - 1, 0, len(ks) - 2)
    t = smoothstep(ks[i], ks[i + 1], s)
    return kv[i] + (kv[i + 1] - kv[i]) * t


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def catmull_rom(points, samples=96, alpha=0.5, closed=False):
    """Centripetal Catmull-Rom through `points`; returns (dense points, index of each control point)."""
    P = np.asarray(points, dtype=float)
    if closed:
        ext = np.vstack([P[-1], P, P[0], P[1]])
        nseg = len(P)
    else:
        ext = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
        nseg = len(P) - 1
    out, idx = [], []
    for i in range(nseg):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0), 1e-6) ** alpha
        t2 = t1 + max(np.linalg.norm(p2 - p1), 1e-6) ** alpha
        t3 = t2 + max(np.linalg.norm(p3 - p2), 1e-6) ** alpha
        t = np.linspace(t1, t2, samples, endpoint=False)[:, None]
        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        idx.append(len(out) * samples)
        out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    dense = np.vstack(out)
    if not closed:
        idx.append(len(dense))
        dense = np.vstack([dense, P[-1][None]])
    return dense, idx


def polyline_project(q, pts, svals):
    """Nearest point of a polyline for many query points. Returns (s, u, dist): u is signed, + on the left."""
    q = np.asarray(q, dtype=float).reshape(-1, 2)
    if len(q) > 2000 and len(pts) > 16:
        fast = _polyline_project_kd(q, pts, svals)
        if fast is not None:
            return fast
    A, B = pts[:-1], pts[1:]
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    out_s = np.empty(len(q))
    out_u = np.empty(len(q))
    out_d = np.empty(len(q))
    for c0 in range(0, len(q), 4096):
        Q = q[c0:c0 + 4096]
        AP = Q[:, None, :] - A[None, :, :]
        t = np.clip((AP * AB[None]).sum(2) / L2[None], 0.0, 1.0)
        proj = A[None] + t[..., None] * AB[None]
        d2 = ((Q[:, None, :] - proj) ** 2).sum(2)
        j = d2.argmin(1)
        r = np.arange(len(Q))
        tj = t[r, j]
        pj = proj[r, j]
        tan = AB[j] / np.sqrt(L2[j])[:, None]
        nl = np.stack([-tan[:, 1], tan[:, 0]], 1)
        out_s[c0:c0 + len(Q)] = svals[j] + tj * (svals[j + 1] - svals[j])
        out_u[c0:c0 + len(Q)] = ((Q - pj) * nl).sum(1)
        out_d[c0:c0 + len(Q)] = np.sqrt(d2[r, j])
    return out_s, out_u, out_d


def _polyline_project_kd(q, pts, svals, window=6):
    """KD-tree accelerated projection (system Python with scipy); None when scipy is missing (Blender)."""
    try:
        from scipy.spatial import cKDTree
    except Exception:
        return None
    tree = cKDTree(pts)
    _, idx = tree.query(q, k=1)
    M = len(pts) - 1
    best = np.full(len(q), np.inf)
    out_s = np.zeros(len(q))
    out_u = np.zeros(len(q))
    for off in range(-window, window + 1):
        j = np.clip(idx + off, 0, M - 1)
        A, B = pts[j], pts[j + 1]
        AB = B - A
        L2 = np.maximum((AB ** 2).sum(1), 1e-12)
        t = np.clip(((q - A) * AB).sum(1) / L2, 0.0, 1.0)
        P = A + t[:, None] * AB
        d2 = ((q - P) ** 2).sum(1)
        better = d2 < best
        tan = AB / np.sqrt(L2)[:, None]
        nl = np.stack([-tan[:, 1], tan[:, 0]], 1)
        best = np.where(better, d2, best)
        out_s = np.where(better, svals[j] + t * (svals[j + 1] - svals[j]), out_s)
        out_u = np.where(better, ((q - P) * nl).sum(1), out_u)
    return out_s, out_u, np.sqrt(best)


def point_in_polygon(q, poly):
    """Even-odd test for many points against one closed polygon (N,2)."""
    q = np.asarray(q, dtype=float).reshape(-1, 2)
    P = np.asarray(poly, dtype=float)
    x, z = q[:, 0][:, None], q[:, 1][:, None]
    xa, za = P[:, 0][None], P[:, 1][None]
    xb, zb = np.roll(P[:, 0], -1)[None], np.roll(P[:, 1], -1)[None]
    cond = (za > z) != (zb > z)
    xi = xa + (z - za) * (xb - xa) / np.where(np.abs(zb - za) < 1e-12, 1e-12, zb - za)
    return (cond & (x < xi)).sum(1) % 2 == 1


def polygon_sdf(q, poly):
    """Signed distance to a closed polygon (negative inside)."""
    q = np.asarray(q, dtype=float).reshape(-1, 2)
    P = np.asarray(poly, dtype=float)
    closed = np.vstack([P, P[:1]])
    _, _, d = polyline_project(q, closed, np.arange(len(closed), dtype=float))
    return np.where(point_in_polygon(q, P), -d, d)


def rect_sdf(q, center, axis, half_len, half_wid):
    """Signed distance to an oriented rectangle (axis = unit direction of the long side)."""
    q = np.asarray(q, dtype=float).reshape(-1, 2)
    c = np.asarray(center, dtype=float)
    a = np.asarray(axis, dtype=float)
    n = np.array([-a[1], a[0]])
    d = q - c
    la = np.abs(d @ a) - half_len
    ln = np.abs(d @ n) - half_wid
    outside = np.sqrt(np.maximum(la, 0) ** 2 + np.maximum(ln, 0) ** 2)
    inside = np.minimum(np.maximum(la, ln), 0)
    return outside + inside


# ----------------------------------------------------------------------------------------------------------
# Marching squares (contours of a scalar field on a regular grid)
# ----------------------------------------------------------------------------------------------------------

def contours(field, x0, z0, step, level=0.0):
    """Closed/open iso-lines of field[j, i] (j along z, i along x). Returns a list of (N,2) Babylon XZ arrays,
    each oriented so that the region field < level lies on the left (counter-clockwise for outer loops)."""
    F = np.asarray(field, dtype=float) - level
    nz, nx = F.shape
    segs = []

    def lerp_pt(i0, j0, i1, j1):
        a, b = F[j0, i0], F[j1, i1]
        t = a / (a - b) if a != b else 0.5
        return (x0 + (i0 + (i1 - i0) * t) * step, z0 + (j0 + (j1 - j0) * t) * step)

    for j in range(nz - 1):
        for i in range(nx - 1):
            c = [F[j, i], F[j, i + 1], F[j + 1, i + 1], F[j + 1, i]]
            inside = [v < 0 for v in c]
            if all(inside) or not any(inside):
                continue
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            edges = []
            for e in range(4):
                a, b = e, (e + 1) % 4
                if inside[a] != inside[b]:
                    edges.append((e, lerp_pt(*corners[a], *corners[b])))
            if len(edges) == 2:
                (ea, pa), (eb, pb) = edges
                # orient: walking pa -> pb keeps the inside on the left
                segs.append(_orient(pa, pb, corners, inside, ea, x0, z0, step))
            elif len(edges) == 4:
                centre = sum(c) / 4.0
                pts = {e: p for e, p in edges}
                # saddle: join edges so that the centre's sign decides connectivity
                if (centre < 0) == inside[0]:
                    pairs = [(0, 1), (2, 3)] if not inside[1] else [(3, 0), (1, 2)]
                else:
                    pairs = [(3, 0), (1, 2)] if not inside[1] else [(0, 1), (2, 3)]
                for ea, eb in pairs:
                    segs.append(_orient(pts[ea], pts[eb], corners, inside, ea, x0, z0, step))
    return _link(segs)


def _orient(pa, pb, corners, inside, ea, x0, z0, step):
    # choose the direction pa->pb or pb->pa so that an inside corner of edge ea lies on the left
    i0, j0 = corners[ea]
    i1, j1 = corners[(ea + 1) % 4]
    ins = (i0, j0) if inside[ea] else (i1, j1)
    px, pz = x0 + ins[0] * step, z0 + ins[1] * step
    cross = (pb[0] - pa[0]) * (pz - pa[1]) - (pb[1] - pa[1]) * (px - pa[0])
    return (pa, pb) if cross > 0 else (pb, pa)


def _link(segs):
    key = lambda p: (round(p[0] * 1e4), round(p[1] * 1e4))
    starts = {}
    for k, (a, b) in enumerate(segs):
        starts.setdefault(key(a), []).append(k)
    used = [False] * len(segs)
    loops = []
    for k0 in range(len(segs)):
        if used[k0]:
            continue
        used[k0] = True
        line = [segs[k0][0], segs[k0][1]]
        while True:
            nxt = [k for k in starts.get(key(line[-1]), []) if not used[k]]
            if not nxt:
                break
            used[nxt[0]] = True
            line.append(segs[nxt[0]][1])
            if key(line[-1]) == key(line[0]):
                break
        arr = np.array(line, dtype=float)
        if len(arr) > 3 and np.allclose(arr[0], arr[-1]):
            arr = arr[:-1]
        loops.append(arr)
    return loops


def resample_loop(loop, step):
    """Uniform arc-length resampling of a closed loop; returns (points, cumulative arc at each point, length)."""
    P = np.vstack([loop, loop[:1]])
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    n = max(8, int(round(total / step)))
    s = np.linspace(0.0, total, n, endpoint=False)
    pts = np.stack([np.interp(s, cum, P[:, 0]), np.interp(s, cum, P[:, 1])], 1)
    return pts, s, total


def polygon_area(loop):
    x, z = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z))


# ----------------------------------------------------------------------------------------------------------
# The stream + falls pool body (spec 3, 4.2-4.5)
# ----------------------------------------------------------------------------------------------------------

class StreamPool:
    """Stream and falls pool as one water region with a metre flow frame (u across, s downstream)."""

    def __init__(self, layout: dict, notes: list):
        water = {w["id"]: w for w in layout["water"]}
        stream = water["sunmeadow_stream"]
        pool = water["falls_pool"]
        self.water_y = float(stream.get("surface_y", WATER_Y))
        pts = [tuple(map(float, p)) for p in stream["points"]]
        centre = tuple(map(float, pool["center_xz"]))
        radius = float(pool["radius_m"])
        self.amended_a1 = False
        self.amended_a2 = False
        if np.allclose(centre, (-10.5, -38.0)) and abs(radius - 2.5) < 1e-6:
            centre, radius = A1_POOL
            self.amended_a1 = True
            notes.append("A1 applied: falls pool moved to (-9.6,-38) r 2.6 (layout still holds (-10.5,-38) r 2.5).")
        self.v2_points = all(np.allclose(a, b) for a, b in zip(pts, V2_STREAM_POINTS)) and len(pts) == len(V2_STREAM_POINTS)
        tail = [tuple(map(float, p)) for p in stream.get("exit_points", [])]
        if not tail and self.v2_points:
            tail = list(A2_TAIL)
            self.amended_a2 = True
            notes.append("A2 applied: stream extended through the cliff gap with P8 (-68.5,-63.5), P9 (-70.5,-69) and two cascades.")
        self.C = np.array(centre)
        self.R = radius
        self.pool_bed = float(pool.get("bed_y", -1.1))
        self.stream_bed = float(stream.get("bed_y", -1.0))
        first = np.array(pts[1])
        self.T0 = (first - self.C) / np.linalg.norm(first - self.C)
        self.N0 = np.array([-self.T0[1], self.T0[0]])
        self.O = self.C + self.R * self.T0
        control = [tuple(self.O)] + pts[1:] + tail
        self.control = np.array(control)
        dense, idx = catmull_rom(self.control, samples=160)
        seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(cum[-1])
        self.control_s = cum[idx]
        step = 0.05
        n = int(math.ceil(self.length / step))
        self.s = np.linspace(0.0, self.length, n + 1)
        self.p = np.stack([np.interp(self.s, cum, dense[:, 0]), np.interp(self.s, cum, dense[:, 1])], 1)
        tan = np.gradient(self.p, axis=0)
        tan /= np.linalg.norm(tan, axis=1)[:, None]
        tan[0] = self.T0
        self.t = tan
        self.n = np.stack([-tan[:, 1], tan[:, 0]], 1)
        # projection polyline: straight prefix from the pool centre (s = -R) to O, then the curve every 0.25 m
        coarse = np.arange(0, len(self.s), 5)
        if coarse[-1] != len(self.s) - 1:
            coarse = np.append(coarse, len(self.s) - 1)
        self.proj_pts = np.vstack([self.C[None], self.p[coarse]])
        self.proj_s = np.concatenate([[-self.R], self.s[coarse]])
        # feature arc lengths
        self.s_gap = float(self.project(np.array([GAP_POINT]))[0][0]) if self.v2_points else self.length * 0.73
        self.cascades = []
        if self.amended_a2 or stream.get("cascades"):
            items = stream.get("cascades") or [{"point_xz": p, "surface_after_y": y} for p, y in CASCADE_POINTS]
            for c in items:
                point = c.get("point_xz", c.get("lip_xz"))
                after = c.get("surface_after_y", c.get("to_y"))
                if point is None or after is None:
                    raise ValueError("Cascade needs an authored lip position and receiving water level")
                sc = float(self.project(np.array([point]))[0][0])
                self.cascades.append((sc, float(after)))
        self.cascades.sort()
        bridge = layout["bridges"][0]
        self.bridge_c = np.array(bridge["center_xz"], dtype=float)
        a = np.array(bridge["along_xz"], dtype=float)
        self.bridge_axis = a / np.linalg.norm(a)
        self.bridge_half_len = float(bridge["length_m"]) / 2
        self.bridge_half_wid = float(bridge["deck_width_m"]) / 2
        self.bridge_deck_y = float(bridge.get("deck_y", 0.0))
        self.s_bridge = float(self.project(self.bridge_c[None])[0][0])
        # width and centre-depth keys
        key_s = list(self.control_s[: len(pts)])           # O, P1..P6, P7 (P7 is not a spec key)
        if self.v2_points and self.amended_a2:
            ks = list(self.control_s[:7]) + [self.s_gap, self.cascades[0][0], self.control_s[8], self.control_s[9]]
            self.width_keys = (ks, SPEC_WIDTH_KEYS)
            self.dc_keys = (ks, SPEC_DC_KEYS)
            self.width_source = "spec-3-table"
        else:
            w0, w1 = (float(v) for v in stream.get("width_m", [3.0, 4.5]))
            ks = list(self.control_s)
            frac = np.array(ks) / self.length
            widths = w0 + (w1 - w0) * smoothstep(0.0, 0.6, frac) - 0.35 * (w1 - w0) * smoothstep(0.75, 1.0, frac)
            dcs = np.where(frac < 0.02, 0.40, np.where(frac > 0.95, 0.40, 0.65))
            self.width_keys = (ks, list(widths))
            self.dc_keys = (ks, list(dcs))
            self.width_source = "procedural-from-width_m"
            notes.append("Stream width/depth keys derived procedurally from width_m (the polyline differs from the spec table).")
        # v3 carries explicit width/depth/speed keys. Project their authored XZ
        # onto the smoothed curve; old s_m values describe the unsmoothed plan.
        authored = stream.get("centreline_keys", [])
        if authored:
            ks = [float(self.project(np.array([k["xz"]]))[0][0]) for k in authored]
            ks[0] = 0.0
            self.width_keys = (ks, [float(k["width_m"]) for k in authored])
            self.dc_keys = (ks, [float(k["depth_m"]) for k in authored])
            self.width_source = "layout-centreline-keys"
        self.authored_speed_keys = (ks, [float(k["speed_m_s"]) for k in authored]) if authored else None
        del key_s
        # pine_west keep-out (spec 3): width <= 3.8 for s 16-24
        self.width_caps = [(16.0, 24.0, 3.8)]
        self.speed_keys = self._speed_keys()

    # ---------------------------------------------------------------- per-s functions
    def _speed_keys(self):
        if self.authored_speed_keys:
            return self.authored_speed_keys
        sb, L = self.s_bridge, self.length
        keys = [(0.0, 0.80), (1.5, 0.80), (3.5, 0.55), (sb - 3.0, 0.55), (sb, 0.60), (sb + 3.0, 0.55), (24.0, 0.55),
                (26.0, 0.45), (min(49.0, self.s_gap - 3.0), 0.45), (self.s_gap, 0.70)]
        for sc, _ in self.cascades:
            keys += [(sc - 1.5, 0.75), (sc, 1.10), (sc + 1.5, 0.65)]
        keys.append((L, 0.45))
        keys.sort()
        ks, vs = [], []
        for s, v in keys:
            if ks and s <= ks[-1] + 0.05:
                continue
            ks.append(s)
            vs.append(v)
        return ks, vs

    def variation_mask(self, s):
        s = np.asarray(s, dtype=float)
        m = np.ones_like(s)
        windows = [(-1.0, 1.5), (self.s_bridge - 3.0, self.s_bridge + 3.0), (16.0, 24.0)]
        windows += [(sc - 2.0, sc + 2.0) for sc, _ in self.cascades]
        for a, b in windows:
            inside = smoothstep(a - 1.0, a, s) * (1.0 - smoothstep(b, b + 1.0, s))
            m *= 1.0 - inside
        return m

    def width(self, s):
        s = np.asarray(s, dtype=float)
        ks, kv = self.width_keys
        w = keyed(np.clip(s, 0.0, self.length), ks, kv)
        var = 0.12 * np.sin(TAU * s / 9.3 + 0.7) + 0.08 * np.sin(TAU * s / 5.1 + 2.1)
        w = w + var * self.variation_mask(s)
        for a, b, cap in self.width_caps:
            w = np.where((s >= a) & (s <= b), np.minimum(w, cap), w)
        return w

    def centre_depth(self, s):
        ks, kv = self.dc_keys
        return keyed(np.clip(np.asarray(s, dtype=float), 0.0, self.length), ks, kv)

    def speed(self, s):
        ks, kv = self.speed_keys
        return keyed(np.clip(np.asarray(s, dtype=float), 0.0, self.length), ks, kv)

    def surface_y(self, s):
        s = np.asarray(s, dtype=float)
        y = np.full_like(s, self.water_y)
        prev = self.water_y
        for sc, after in self.cascades:
            ramp = np.clip((s - (sc - 0.125)) / 0.25, 0.0, 1.0)
            y = y + (after - prev) * ramp
            prev = after
        return y

    def bank_width(self, ysurf):
        return 1.2 * (np.abs(ysurf) / 0.35) ** 0.6

    # ---------------------------------------------------------------- frames
    def at(self, s):
        """Centreline position, tangent and left normal at arc length s (s < 0 runs straight into the pool)."""
        s = np.asarray(s, dtype=float)
        sc = np.clip(s, 0.0, self.length)
        p = np.stack([np.interp(sc, self.s, self.p[:, 0]), np.interp(sc, self.s, self.p[:, 1])], -1)
        t = np.stack([np.interp(sc, self.s, self.t[:, 0]), np.interp(sc, self.s, self.t[:, 1])], -1)
        t = t / np.linalg.norm(t, axis=-1, keepdims=True)
        neg = s < 0
        if np.any(neg):
            p = np.where(neg[..., None], self.O + s[..., None] * self.T0, p)
            t = np.where(neg[..., None], self.T0, t)
        n = np.stack([-t[..., 1], t[..., 0]], -1)
        return p, t, n

    def frame_point(self, u, s):
        p, _, n = self.at(s)
        return p + np.asarray(u, dtype=float)[..., None] * n

    def project(self, q):
        return polyline_project(q, self.proj_pts, self.proj_s)

    # ---------------------------------------------------------------- fields
    def pool_radius(self, theta):
        r = np.full_like(np.asarray(theta, dtype=float), self.R)
        for k, w, ph in POOL_LOBES:
            r = r + POOL_LOBE_AMP * w * np.sin(k * theta + ph)
        return r

    def pool_sdf(self, q):
        q = np.asarray(q, dtype=float).reshape(-1, 2)
        d = q - self.C
        rho = np.linalg.norm(d, axis=1)
        th = np.arctan2(d[:, 1], d[:, 0])
        f = rho - self.pool_radius(th)
        return np.maximum(f, q[:, 0] - BLUFF_TOE_X)

    def fields(self, q):
        """Every derived scalar at world XZ points q (N,2): flow frame, signed distance, depth, surface and ground."""
        q = np.asarray(q, dtype=float).reshape(-1, 2)
        s, u, dist = self.project(q)
        w = self.width(s)
        f_stream = dist - w / 2.0
        f_pool = self.pool_sdf(q)
        f = smin(f_pool, f_stream, JUNCTION_K)
        ys = self.surface_y(s)
        # depth below the local surface
        dc = self.centre_depth(s)
        lat = np.clip(np.abs(u) / (w / 2.0), 0.0, 1.0)
        d_stream = dc * (1.0 - lat ** 2.2) * smoothstep(-1.5, 0.5, s) * (f_stream < 0)
        d = q - self.C
        rho = np.linalg.norm(d, axis=1)
        rr = self.pool_radius(np.arctan2(d[:, 1], d[:, 0]))
        pool_depth = abs(self.pool_bed - self.water_y)                 # 0.75 m centre depth
        landing = self.landing_xz()
        dl = np.linalg.norm(q - landing, axis=1)
        d_pool = (pool_depth * (1.0 - np.clip(rho / rr, 0, 1) ** 2.5) + 0.35 * np.exp(-(dl / 0.7) ** 2)) * (f_pool < 0)
        shelf = 0.20 * smoothstep(0.0, 0.8, -f)
        depth = np.where(f < 0, np.maximum(np.maximum(d_stream, d_pool), shelf), 0.0)
        B = self.bank_width(ys)
        bank = ys * (1.0 - np.clip(f / B, 0.0, 1.0)) ** 2
        ground = np.where(f < 0, ys - depth, np.where(f < B, bank, 0.0))
        return {"s": s, "u": u, "dist": dist, "w": w, "f": f, "f_pool": f_pool, "f_stream": f_stream,
                "depth": depth, "surface_y": ys, "ground_y": ground, "bank_width": B}

    def landing_xz(self):
        return np.array([-9.31, -38.0]) if self.amended_a1 else np.array([self.C[0] + 0.29, self.C[1]])

    def deck_sdf(self, q):
        return rect_sdf(q, self.bridge_c, self.bridge_axis, self.bridge_half_len, self.bridge_half_wid)


# ----------------------------------------------------------------------------------------------------------
# Falls (spec 4.6) - data only; water_meshes builds the sheets
# ----------------------------------------------------------------------------------------------------------

class Falls:
    def __init__(self, layout: dict, sp: StreamPool):
        f = {w["id"]: w for w in layout["water"]}["bluff_falls"]
        self.top_xz = np.array(f["top_xz"], dtype=float)
        self.top_y = float(f["top_y"])
        self.width = float(f["width_m"])
        self.v0 = float(f.get("exit_velocity_m_s", 1.5))
        self.g = 9.81
        self.dir = np.array([-1.0, 0.0])           # west face: the water leaves toward -x
        self.mouth = np.array([-6.9, 7.6, -38.0])
        self.lip_start = np.array([-6.6, 7.55, -38.0])
        self.F0 = np.array([-7.42, 7.45, -38.0])
        self.y_end = sp.water_y
        self.t_impact = math.sqrt(2.0 * (self.F0[1] - self.y_end) / self.g)
        self.landing = np.array([self.F0[0] + self.dir[0] * self.v0 * self.t_impact, self.y_end,
                                 self.F0[2] + self.dir[1] * self.v0 * self.t_impact])

    def point(self, t):
        t = np.asarray(t, dtype=float)
        x = self.F0[0] + self.dir[0] * self.v0 * t
        z = self.F0[2] + self.dir[1] * self.v0 * t
        y = self.F0[1] - 0.5 * self.g * t * t
        return np.stack([x, y, z], -1)

    def width_at(self, t):
        return self.width * (1.0 + 0.375 * (np.asarray(t, dtype=float) / self.t_impact) ** 1.2)

    def rows(self, n):
        return self.t_impact * (np.arange(n + 1) / n) ** 0.8


# ----------------------------------------------------------------------------------------------------------
# Stones (spec 4.3, 4.5, A2) - deterministic placement
# ----------------------------------------------------------------------------------------------------------

def place_stones(sp: StreamPool, seed: int = SEED):
    rng = random.Random(seed)
    stones = []

    def ok(x, z, r, spacing=2.5, deck=3.0):
        for o in stones:
            if math.hypot(x - o["x"], z - o["z"]) < max(spacing, r + o["r"] + 0.3):
                return False
        if float(sp.deck_sdf(np.array([[x, z]]))[0]) - r < deck:
            return False
        return True

    def add(kind, x, z, size, top_y, group, yaw=None, squash=None):
        r = size / 2.0
        f = sp.fields(np.array([[x, z]]))
        ground = float(f["ground_y"][0])
        base = ground - 0.18 - 0.12 * r
        stones.append({
            "id": f"stone_{group}_{sum(1 for o in stones if o['group'] == group) + 1:02d}", "kind": kind, "group": group,
            "x": round(x, 4), "z": round(z, 4), "r": round(r, 4), "top_y": round(top_y, 4), "base_y": round(base, 4),
            "yaw": round(rng.uniform(0, TAU) if yaw is None else yaw, 4),
            "squash": round(rng.uniform(0.62, 0.86) if squash is None else squash, 4),
            "seed": rng.randrange(1 << 30), "surface_y": round(float(f["surface_y"][0]), 4),
        })

    s_stop = (sp.s_gap - 1.5) if sp.cascades else sp.length - 2.0
    # 3 emerged boulders (spec: s ~12 -> moved to the deck-clearance limit, ~20, ~40)
    for s_target, u_frac, size in ((max(12.0, sp.s_bridge + sp.bridge_half_wid + 3.0 + 0.8), -0.28, 1.35),
                                   (20.0, 0.22, 1.05), (40.0, -0.18, 1.55)):
        for _ in range(60):
            s = s_target + rng.uniform(-0.6, 0.6)
            w = float(sp.width(s))
            u = u_frac * w / 2 + rng.uniform(-0.1, 0.1)
            x, z = sp.frame_point(np.array(u), np.array(s))
            if ok(x, z, size / 2):
                ys = float(sp.surface_y(s))
                add("emerged_boulder", float(x), float(z), size, ys + rng.uniform(0.35, 0.6), "boulder")
                break
    # 4 submerged mid-channel stones
    tries = 0
    while sum(1 for o in stones if o["group"] == "submerged") < 4 and tries < 400:
        tries += 1
        s = rng.uniform(3.0, min(50.0, s_stop))
        w = float(sp.width(s))
        size = rng.uniform(0.5, 1.2)
        u = rng.uniform(-0.35, 0.35) * w / 2
        x, z = sp.frame_point(np.array(u), np.array(s))
        if ok(x, z, size / 2):
            ys = float(sp.surface_y(s))
            add("submerged", float(x), float(z), size, ys - rng.uniform(0.08, 0.20), "submerged")
    # 11 bank stones (|u| >= 0.6 w/2, emerged 0.05-0.35 m)
    tries = 0
    while sum(1 for o in stones if o["group"] == "bank") < 11 and tries < 2000:
        tries += 1
        s = rng.uniform(2.5, s_stop)
        w = float(sp.width(s))
        size = rng.uniform(0.4, 1.0)
        side = 1.0 if rng.random() < 0.5 else -1.0
        u = side * (w / 2) * rng.uniform(0.62, 1.02)
        x, z = sp.frame_point(np.array(u), np.array(s))
        if ok(x, z, size / 2):
            ys = float(sp.surface_y(s))
            add("bank", float(x), float(z), size, ys + rng.uniform(0.05, 0.35), "bank")
    # pool: outlet sill (4), rim (10), bluff toe boulders (2)
    for k in range(4):
        u = -1.15 + 2.3 * (k + rng.uniform(0.2, 0.8)) / 4
        s = rng.uniform(0.3, 1.0)
        x, z = sp.frame_point(np.array(u), np.array(s))
        add("sill", float(x), float(z), rng.uniform(0.35, 0.6), sp.water_y + rng.uniform(0.02, 0.10), "sill")
    outlet_th = math.atan2(sp.T0[1], sp.T0[0])
    placed = 0
    tries = 0
    while placed < 10 and tries < 3000:
        tries += 1
        th = rng.uniform(-math.pi, math.pi)
        dth = (th - outlet_th + math.pi) % TAU - math.pi
        if abs(dth) < math.radians(36):
            continue
        rr = float(sp.pool_radius(np.array(th))) + rng.uniform(-0.05, 0.25)
        x, z = sp.C[0] + rr * math.cos(th), sp.C[1] + rr * math.sin(th)
        if x > BLUFF_TOE_X - 0.6:                        # the bluff toe owns the east side
            continue
        size = rng.uniform(0.4, 1.0)
        if any(math.hypot(x - o["x"], z - o["z"]) < o["r"] + size / 2 + 0.18 for o in stones):
            continue
        add("rim", x, z, size, sp.water_y + rng.uniform(0.08, 0.45), "rim")
        placed += 1
    for (x, z), size in (((-7.6, -36.2), 0.9), ((-7.8, -39.9), 1.2)):
        add("toe", x, z, size, sp.water_y + size * 0.55, "toe", squash=0.78)
    # A2: cascade lip stones, gap boulders and the spur mass that hides the stream end
    for sc, _after in sp.cascades:
        w = float(sp.width(sc))
        for side in (-1.0, 1.0):
            x, z = sp.frame_point(np.array(side * (w / 2 + 0.25)), np.array(sc + 0.1))
            add("cascade_lip", float(x), float(z), rng.uniform(0.85, 1.25), float(sp.surface_y(sc - 0.5)) + rng.uniform(0.25, 0.45), "cascade")
    if sp.cascades:
        for side, size in ((-1.0, 1.7), (1.0, 1.35)):
            w = float(sp.width(sp.s_gap))
            x, z = sp.frame_point(np.array(side * (w / 2 + 1.25)), np.array(sp.s_gap + 0.8))
            add("gap_boulder", float(x), float(z), size, size * 0.6, "gap")
        end = sp.at(np.array(sp.length))[0]
        tan = sp.at(np.array(sp.length))[1]
        for k, (along, lat, size) in enumerate(((0.6, 0.0, 2.6), (-0.8, 1.6, 1.9), (-0.6, -1.7, 2.1), (1.9, 0.9, 1.6))):
            nrm = np.array([-tan[1], tan[0]])
            x, z = end + along * tan + lat * nrm
            add("spur", float(x), float(z), size, float(sp.surface_y(sp.length)) + size * 0.75, "spur", squash=0.9)
    return stones


# ----------------------------------------------------------------------------------------------------------
# The whole derived set
# ----------------------------------------------------------------------------------------------------------

class WaterModel:
    def __init__(self, layout_path: Path = LAYOUT_PATH, seed: int = SEED):
        self.layout_path = Path(layout_path)
        self.layout = json.loads(self.layout_path.read_text(encoding="utf-8"))
        self.layout_sha = sha256_file(self.layout_path)
        self.seed = seed
        self.notes: list[str] = []
        self.sp = StreamPool(self.layout, self.notes)
        self.falls = Falls(self.layout, self.sp)
        self.stones = place_stones(self.sp, seed)
        self.notes.append(f"Falls landing x = {self.falls.landing[0]:.3f} after t = {self.falls.t_impact:.3f} s.")

    # ------------------------------------------------------------ atlas (spec 4.2: 1024 x 128 at 12.5 px/m)
    def atlas(self):
        sp = self.sp
        s0, s1 = -0.5, sp.length + 0.5
        u_half = 2.4
        sw = int(math.ceil((s1 - s0) * PX_PER_M))
        sh = int(math.ceil(2 * u_half * PX_PER_M))
        pool_v0 = -(2 * sp.R + 0.3)
        pool_u_half = sp.R + 0.16
        pw = int(math.ceil(-pool_v0 * PX_PER_M))
        ph = int(math.ceil(2 * pool_u_half * PX_PER_M))
        W = 1024
        H = 128
        stream_rect = [ATLAS_PAD, ATLAS_PAD, sw, sh]
        pool_rect = [ATLAS_PAD * 3 + sw, ATLAS_PAD, pw, ph]
        if pool_rect[0] + pw + ATLAS_PAD > W:
            raise ValueError("stream + pool islands do not fit a 1024-wide atlas")
        return {
            "width": W, "height": H, "px_per_m": PX_PER_M, "pad": ATLAS_PAD,
            "stream": {"rect_px": stream_rect, "s_range": [s0, s0 + sw / PX_PER_M], "u_range": [-u_half, -u_half + sh / PX_PER_M]},
            "pool": {"rect_px": pool_rect, "v_range": [pool_v0, pool_v0 + pw / PX_PER_M], "u_range": [-pool_u_half, -pool_u_half + ph / PX_PER_M],
                     "frame": "straight outlet frame: U = (p-O).N0, V = (p-O).T0"},
        }

    def anchors(self):
        sp, fa = self.sp, self.falls
        L = fa.landing
        out = {
            "anchor_sm_falls_mouth": {"position": list(map(float, fa.mouth)), "dir": [-1.0, 0.0, 0.0], "width": fa.width},
            "anchor_sm_falls_lip": {"position": list(map(float, fa.F0))},
            "anchor_sm_falls_landing": {"position": [float(L[0]), sp.water_y, float(L[2])], "normal": [0.0, 1.0, 0.0], "radius": 1.1},
            "anchor_sm_pool_basin": {"position": [float(sp.C[0]), sp.water_y, float(sp.C[1])], "radius": sp.R},
            "anchor_sm_pool_outlet": {"position": [float(sp.O[0]), sp.water_y, float(sp.O[1])], "dir": [float(sp.T0[0]), 0.0, float(sp.T0[1])], "width": float(sp.width(0.0))},
            "emit_mist_sm_bluff_falls": {"position": [float(L[0]), -0.10, float(L[2])]},
            "emit_spray_sm_bluff_falls": {"position": [float(L[0]), -0.30, float(L[2])], "radius": 1.1},
            "emit_spray_sm_bluff_falls_lip": {"position": [float(fa.F0[0]), 7.40, float(fa.F0[2])], "dir": [-1.0, 0.0, 0.0]},
        }
        if sp.cascades:
            sc, after = sp.cascades[0]
            p, t, _ = sp.at(np.array(sc))
            land = p + t * 0.55
            out["anchor_sm_stream_exit_lip"] = {"position": [float(p[0]), float(sp.water_y), float(p[1])]}
            out["anchor_sm_stream_exit_landing"] = {"position": [float(land[0]), after, float(land[1])]}
            out["emit_spray_sm_stream_exit"] = {"position": [float(land[0]), after + 0.05, float(land[1])]}
        return {k: {kk: (round(vv, 4) if isinstance(vv, float) else [round(x, 4) for x in vv] if isinstance(vv, list) else vv)
                    for kk, vv in v.items()} for k, v in out.items()}

    # ------------------------------------------------------------ ground patch rectangle (exact host clip)
    def ground_rect(self):
        """Axis-aligned rectangle owned by the water ground patch: covers every bank (f < bank width) with margin."""
        sp = self.sp
        x0, x1, z0, z1 = -80.0, 0.0, -78.0, -30.0
        step = 0.5
        xs = np.arange(x0, x1 + 1e-6, step)
        zs = np.arange(z0, z1 + 1e-6, step)
        X, Z = np.meshgrid(xs, zs)
        F = sp.fields(np.stack([X.ravel(), Z.ravel()], 1))
        carved = (F["ground_y"] < -1e-4).reshape(X.shape)
        if not carved.any():
            raise ValueError("no carved ground found")
        cx, cz = X[carved], Z[carved]
        m = 1.0
        return [math.floor(cx.min() - m), math.ceil(cx.max() + m), math.floor(cz.min() - m), math.ceil(cz.max() + m)]

    # ------------------------------------------------------------ waterline loop and hazard (spec 4.9)
    def field_grid(self, rect, step):
        x0, x1, z0, z1 = rect
        xs = np.arange(x0, x1 + 1e-6, step)
        zs = np.arange(z0, z1 + 1e-6, step)
        X, Z = np.meshgrid(xs, zs)
        F = self.sp.fields(np.stack([X.ravel(), Z.ravel()], 1))
        return xs, zs, {k: v.reshape(X.shape) for k, v in F.items() if isinstance(v, np.ndarray) and v.shape == X.ravel().shape}

    def waterline(self, rect=None, step=0.15):
        rect = rect or self.ground_rect()
        xs, zs, F = self.field_grid(rect, step)
        loops = contours(F["f"], xs[0], zs[0], step, 0.0)
        loops = [l for l in loops if len(l) > 20]
        loops.sort(key=lambda l: -abs(polygon_area(l)))
        return loops

    def hazard(self, step=0.2):
        sp = self.sp
        rect = self.ground_rect()
        xs, zs, F = self.field_grid(rect, step)
        X, Z = np.meshgrid(xs, zs)
        q = np.stack([X.ravel(), Z.ravel()], 1)
        g = F["f"] - HAZARD_OFFSET
        # bridge deck corridor stays open (7.5 x 3.8 m)
        deck = sp.deck_sdf(q).reshape(X.shape)
        g = np.maximum(g, -deck)
        # cliff gap plug (A2): the water and its banks leave 2.4 m dry strips inside the 8 m gap, so the hazard
        # spans the gap from cliff face to cliff face; the strips carry the gap boulders (no invisible wall).
        plug = None
        if sp.cascades:
            p, t, n = sp.at(np.array(sp.s_gap + 0.8))
            plug = {"center_xz": [round(float(p[0]), 3), round(float(p[1]), 3)], "axis_xz": [round(float(n[0]), 4), round(float(n[1]), 4)],
                    "half_length": 5.2, "half_width": 1.1}
            g = np.minimum(g, rect_sdf(q, p, n, 5.2, 1.1).reshape(X.shape))
        loops = contours(g, xs[0], zs[0], step, 0.0)
        loops = [l for l in loops if abs(polygon_area(l)) > 1.0]
        polys = []
        for l in loops:
            pts, _, _ = resample_loop(l, 0.5)
            if polygon_area(pts) < 0:
                pts = pts[::-1]
            polys.append([[round(float(a), 3), round(float(b), 3)] for a, b in pts])
        boxes = self._hazard_boxes(polys)
        return {"polygons": polys, "boxes": boxes, "gap_plug": plug}

    def _hazard_boxes(self, polys, seg_len=2.0, overlap=0.3, band=1.3):
        """Oriented-box fallback: boxes 2.0 m long (0.3 m overlap) straddling each hazard edge inward."""
        boxes = []
        for pi, poly in enumerate(polys):
            P = np.array(poly)
            loop = np.vstack([P, P[:1]])
            seg = np.linalg.norm(np.diff(loop, axis=0), axis=1)
            cum = np.concatenate([[0], np.cumsum(seg)])
            total = cum[-1]
            n = max(3, int(math.ceil(total / (seg_len - overlap))))
            for k in range(n):
                a = k * total / n
                b = a + seg_len
                sa = np.array([np.interp(a % total, cum, loop[:, 0]), np.interp(a % total, cum, loop[:, 1])])
                sb = np.array([np.interp(b % total, cum, loop[:, 0]), np.interp(b % total, cum, loop[:, 1])])
                d = sb - sa
                L = float(np.linalg.norm(d))
                if L < 0.2:
                    continue
                d /= L
                inward = np.array([-d[1], d[0]])          # CCW polygon: the interior is on the left
                c = (sa + sb) / 2 + inward * (band / 2)
                yaw = math.atan2(d[0], d[1]) % TAU          # local Z along the edge
                boxes.append({"id": f"water_hazard_{pi:02d}_{k:03d}", "center_xz": [round(float(c[0]), 3), round(float(c[1]), 3)],
                              "size_xz": [round(band, 3), round(L, 3)], "yaw": round(yaw, 4)})
        return boxes

    # ------------------------------------------------------------ derived JSON
    def derived(self):
        sp, fa = self.sp, self.falls
        rows = np.arange(0.0, sp.length + 1e-6, 1.0)
        p, t, n = sp.at(rows)
        return {
            "schema": SCHEMA, "seed": self.seed, "layout": str(self.layout_path.relative_to(REPO)).replace("\\", "/"),
            "layout_sha256": self.layout_sha, "axes": "Babylon world XZ (+x east, +z north), metres; Blender = (-bx, -bz, by)",
            "amendments": {"A1": sp.amended_a1, "A2": sp.amended_a2}, "notes": list(self.notes),
            "stream": {
                "length_m": round(sp.length, 3), "outlet_O": [round(float(v), 4) for v in sp.O], "T0": [round(float(v), 4) for v in sp.T0],
                "N0": [round(float(v), 4) for v in sp.N0], "control_points": sp.control.round(4).tolist(),
                "control_s": [round(float(v), 3) for v in sp.control_s], "s_bridge": round(sp.s_bridge, 3), "s_gap": round(sp.s_gap, 3),
                "cascades": [{"s": round(sc, 3), "surface_after_y": y} for sc, y in sp.cascades],
                "width_source": sp.width_source,
                "samples_1m": [{"s": round(float(s), 2), "x": round(float(a[0]), 3), "z": round(float(a[1]), 3),
                                "w": round(float(sp.width(s)), 3), "dc": round(float(sp.centre_depth(s)), 3),
                                "speed": round(float(sp.speed(s)), 3), "surface_y": round(float(sp.surface_y(s)), 3)}
                               for s, a in zip(rows, p)],
            },
            "pool": {"center_xz": [float(v) for v in sp.C], "radius": sp.R, "bed_y": sp.pool_bed, "east_clip_x": BLUFF_TOE_X,
                     "lobes": [list(l) for l in POOL_LOBES], "lobe_amplitude": POOL_LOBE_AMP},
            "falls": {"lip_F0": fa.F0.tolist(), "mouth": fa.mouth.tolist(), "v0": fa.v0, "t_impact": round(fa.t_impact, 4),
                      "landing": [round(float(v), 4) for v in fa.landing], "width_top": fa.width,
                      "width_bottom": round(float(fa.width_at(fa.t_impact)), 4), "streak_tile_s": round(TAU / 0.45 / 40, 5)},
            "bridge": {"center_xz": sp.bridge_c.tolist(), "axis_xz": [round(float(v), 4) for v in sp.bridge_axis],
                       "half_length": sp.bridge_half_len, "half_width": sp.bridge_half_wid, "deck_y": sp.bridge_deck_y},
            "stones": self.stones, "atlas": self.atlas(), "anchors": self.anchors(), "ground_rect_xz": self.ground_rect(),
        }


if __name__ == "__main__":
    import argparse
    import time
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layout", default=str(LAYOUT_PATH))
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    t0 = time.time()
    model = WaterModel(Path(a.layout), a.seed)
    d = model.derived()
    d["hazard"] = model.hazard()
    text = json.dumps(d, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(json.dumps({k: d[k] for k in ("amendments", "notes", "ground_rect_xz")}, indent=1))
    print("stream length", d["stream"]["length_m"], "stones", len(d["stones"]), "hazard polys", len(d["hazard"]["polygons"]),
          "boxes", len(d["hazard"]["boxes"]), f"{time.time() - t0:.1f}s")
