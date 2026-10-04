"""Sunmeadow natural water: derived model -> mesh arrays (pure Python + numpy, no bpy).

Every mesh is generated from water_layout.WaterModel, so a layout change regenerates it:
  surface    fx_water_sm_surface: stream + pool rows in the metre flow frame (TEXCOORD_0 = (u, s)),
             TEXCOORD_1 = mask atlas (stream island / pool island), extends 0.15 m under the banks.
  falls      fx_waterfall_sm_lod{0,1,2}: ballistic layered sheets, lip, splash crown and ring, exit cascades.
             TEXCOORD_0 = (across -1..1, time of flight s); COLOR_0 = (N_scroll/64, opacity, brightness, 1).
  strip      water_bank_strip: ribbon along the waterline loop, U across (0 = 0.25 m under water,
             1 = 1.6 m up the bank), V along in repeats of ~4 m (seam hidden under the bluff toe).
  stones     water_stones: noise-displaced, seeded rocks with COLOR_0 = painted wet line, moss and algae.
  ground     a height grid over the ground rectangle (the Blender build dissolves its flat areas).
All positions are Babylon world (x, y, z); faces wind counter-clockwise seen from their front side.
"""
from __future__ import annotations

import math

import numpy as np

import water_layout as W

TAU = math.tau
STREAK_TILE_S = TAU / 0.45 / 40.0      # 0.34907 s: 40 tiles per NatureClock period (13.963 s)


class MeshData:
    def __init__(self, name):
        self.name = name
        self.pos: list = []
        self.nrm: list = []
        self.uv0: list = []
        self.uv1: list = []
        self.col: list = []
        self.tri: list = []

    def add_vertex(self, p, n=(0.0, 1.0, 0.0), uv0=(0.0, 0.0), uv1=None, col=None):
        self.pos.append(tuple(float(v) for v in p))
        self.nrm.append(tuple(float(v) for v in n))
        self.uv0.append((float(uv0[0]), float(uv0[1])))
        if uv1 is not None:
            self.uv1.append((float(uv1[0]), float(uv1[1])))
        if col is not None:
            self.col.append(tuple(float(v) for v in col))
        return len(self.pos) - 1

    def add_tri(self, a, b, c, up_hint=None):
        """Adds a triangle; with up_hint (a unit vector) the winding is fixed so the face normal agrees with it."""
        if up_hint is not None:
            pa, pb, pc = (np.array(self.pos[i]) for i in (a, b, c))
            n = np.cross(pb - pa, pc - pa)
            # Babylon is left-handed: a counter-clockwise triangle seen from its front has cross(b-a, c-a)
            # pointing away from the viewer, i.e. n . front < 0.
            if float(np.dot(n, up_hint)) > 0:
                b, c = c, b
        self.tri.append((a, b, c))

    def arrays(self):
        out = {"position": np.array(self.pos, np.float32), "normal": np.array(self.nrm, np.float32),
               "uv0": np.array(self.uv0, np.float32), "indices": np.array(self.tri, np.uint32).reshape(-1)}
        if self.uv1:
            out["uv1"] = np.array(self.uv1, np.float32)
        if self.col:
            out["color"] = np.array(self.col, np.float32)
        return out

    @property
    def triangles(self):
        return len(self.tri)


# ----------------------------------------------------------------------------------------------------------
# Surface (spec 4.2 / 4.3)
# ----------------------------------------------------------------------------------------------------------

def _row_extent(sp, s, extend=W.EXTEND_UNDER_BANK, umax=4.2, du=0.02):
    """Lateral extent [u_left_neg, u_right_pos] of the region f < extend on the row at arc length s."""
    us = np.arange(-umax, umax + 1e-9, du)
    pts = sp.frame_point(us, np.full_like(us, s))
    f = sp.fields(pts)["f"]
    inside = f < extend
    if not inside.any():
        return None
    mid = len(us) // 2
    if not inside[mid]:
        # the row centre is outside (far pool rim): take the inside run nearest the centre
        idx = np.flatnonzero(inside)
        mid = idx[np.argmin(np.abs(idx - mid))]
    lo = mid
    while lo > 0 and inside[lo - 1]:
        lo -= 1
    hi = mid
    while hi < len(us) - 1 and inside[hi + 1]:
        hi += 1

    def refine(i_in, i_out):
        a, b = us[i_in], us[i_out]
        fa, fb = f[i_in] - extend, f[i_out] - extend
        return a + (b - a) * (fa / (fa - fb)) if fa != fb else a

    left = refine(lo, lo - 1) if lo > 0 else us[0]
    right = refine(hi, hi + 1) if hi < len(us) - 1 else us[-1]
    return float(left), float(right)


def surface_rows(model):
    sp = model.sp
    v_min = -(2 * sp.R + 0.2)
    rows = []
    v = v_min
    while v < -1e-6:
        rows.append(("pool", v))
        v += 0.3
    rows.append(("pool", 0.0))
    special = []
    for sc, _ in sp.cascades:
        special += [sc - 0.125, sc + 0.125]
    s = 0.0
    stream_s = [0.0]
    while s < sp.length - 1e-6:
        near_cascade = any(abs(s - sc) < 2.0 for sc, _ in sp.cascades)
        step = 0.5 if (s < 20.0 or near_cascade) else 0.75
        s = min(sp.length, s + step)
        stream_s.append(s)
    stream_s = sorted(set([round(x, 4) for x in stream_s + special]))
    clean = []
    for x in stream_s:
        if clean and x - clean[-1] < 0.1:
            if any(abs(x - y) < 1e-6 for y in special):
                clean[-1] = x
            continue
        clean.append(x)
    rows += [("stream", x) for x in clean]
    return rows


def atlas_uv(model, island, u, s):
    at = model.atlas()
    W_, H_ = at["width"], at["height"]
    if island == "stream":
        x, y, _, _ = at["stream"]["rect_px"]
        s0, u0 = at["stream"]["s_range"][0], at["stream"]["u_range"][0]
        return ((x + (s - s0) * W.PX_PER_M) / W_, (y + (u - u0) * W.PX_PER_M) / H_)
    x, y, _, _ = at["pool"]["rect_px"]
    v0, u0 = at["pool"]["v_range"][0], at["pool"]["u_range"][0]
    return ((x + (s - v0) * W.PX_PER_M) / W_, (y + (u - u0) * W.PX_PER_M) / H_)


def build_surface(model, cols=4):
    sp = model.sp
    mesh = MeshData("fx_water_sm_surface")
    up = np.array([0.0, 1.0, 0.0])
    prev = None
    prev_island = None
    for island, s in surface_rows(model):
        ext = _row_extent(sp, s)
        if ext is None:
            continue
        left, right = ext
        us = np.linspace(left, right, cols + 1)
        xz = sp.frame_point(us, np.full_like(us, s))
        y = float(sp.surface_y(np.array(max(s, 0.0))))
        ids = []
        for u, p in zip(us, xz):
            ids.append(mesh.add_vertex((p[0], y, p[1]), (0, 1, 0), (u, s), atlas_uv(model, island, u, s)))
        if prev is not None and prev_island != island:
            # UV1 seam row at s = 0: duplicate the pool's last row with stream-island UV1 (same positions, same UV0)
            prev = ids
            prev_island = island
            continue
        if prev is not None:
            for i in range(cols):
                a, b, c, d = prev[i], prev[i + 1], ids[i + 1], ids[i]
                mesh.add_tri(a, b, c, up)
                mesh.add_tri(a, c, d, up)
        prev = ids
        prev_island = island
    return mesh


# ----------------------------------------------------------------------------------------------------------
# Falls (spec 4.6)
# ----------------------------------------------------------------------------------------------------------

LAYERS = {
    # name: (width factor, normal offset toward rock, opacity, scroll tiles per period, brightness)
    "back": (0.92, 0.06, 0.75, 36, 0.82),
    "main": (1.00, 0.00, 0.85, 40, 1.00),
    "front": (None, -0.05, 0.55, 44, 1.08),
    "side": (None, -0.03, 0.45, 42, 1.00),
    "lip": (None, 0.00, 0.90, 52, 1.05),
    "crown": (None, 0.00, 0.60, 24, 1.00),
    "ring": (None, 0.00, 0.70, 24, 1.00),
}


def _colour(layer):
    _, _, opacity, scroll, bright = LAYERS[layer]
    return (scroll / 64.0, opacity, bright / 1.1, 1.0)


def _sheet(mesh, fa, rows, cols, width_fn, centre_fn=None, offset=0.0, layer="main", seed_u=0.0):
    """One ribbon of the ballistic sheet (spec 4.6): rows at t_k = t_impact (k/n)^0.8, across -1..1.

    width_fn(t) is the ribbon width, centre_fn(t) its centre offset across the sheet (strands), offset the
    displacement along the sheet normal (+ toward the rock). UV0 = (across + seed, time of flight)."""
    ts = fa.rows(rows)
    across = np.array([-fa.dir[1], 0.0, fa.dir[0]])                 # horizontal, perpendicular to the flow
    ids = []
    for t in ts:
        p = fa.point(t)
        vel = np.array([fa.dir[0] * fa.v0, -fa.g * t, fa.dir[1] * fa.v0])
        tan = vel / np.linalg.norm(vel)
        rock = np.cross(across, tan)
        rock = rock / np.linalg.norm(rock)
        if rock[0] * -fa.dir[0] + rock[2] * -fa.dir[1] - 0.2 * rock[1] < 0:   # toward the bluff (behind, below)
            rock = -rock
        front = -rock
        half = width_fn(t) / 2.0
        cen = centre_fn(t) if centre_fn else 0.0
        row = []
        for c in range(cols + 1):
            a = -1.0 + 2.0 * c / cols
            q = p + across * (cen + a * half) + rock * offset
            row.append(mesh.add_vertex(q, front, (a + seed_u, float(t)), None, _colour(layer)))
        ids.append((row, front))
    for k in range(len(ids) - 1):
        r0, f0 = ids[k]
        r1, _ = ids[k + 1]
        for c in range(cols):
            mesh.add_tri(r0[c], r0[c + 1], r1[c + 1], f0)
            mesh.add_tri(r0[c], r1[c + 1], r1[c], f0)


def _lip(mesh, fa, cols=8, rows=4):
    """Water sliding over the cleft floor (x -6.6 .. -7.30) and rounding the 0.12 m edge down to F0."""
    across = np.array([-fa.dir[1], 0.0, fa.dir[0]])
    pts = []
    x_edge = fa.F0[0] + 0.12
    for k in range(rows + 1):
        a = k / rows
        if a < 0.6:
            x = fa.lip_start[0] + (x_edge - fa.lip_start[0]) * (a / 0.6)
            y = fa.lip_start[1]
        else:
            th = (a - 0.6) / 0.4 * (math.pi / 2)
            x = x_edge - 0.12 * math.sin(th)
            y = fa.F0[1] + 0.10 * math.cos(th)
        pts.append(np.array([x, y, fa.F0[2]]))
    dist = [0.0]
    for k in range(1, len(pts)):
        dist.append(dist[-1] + float(np.linalg.norm(pts[k] - pts[k - 1])))
    total = dist[-1]
    grid = []
    for k, p in enumerate(pts):
        tfall = -(total - dist[k]) / 1.2                           # 1.2 m/s over the floor, 0 at F0
        width = 1.4 + 0.2 * (dist[k] / total)
        row = []
        for c in range(cols + 1):
            a = -1.0 + 2.0 * c / cols
            q = p + across * (a * width / 2.0)
            row.append(mesh.add_vertex(q, (0.3, 1.0, 0.0), (a, tfall), None, _colour("lip")))
        grid.append(row)
    up = np.array([0.0, 1.0, 0.0])
    for k in range(rows):
        for c in range(cols):
            mesh.add_tri(grid[k][c], grid[k][c + 1], grid[k + 1][c + 1], up)
            mesh.add_tri(grid[k][c], grid[k + 1][c + 1], grid[k + 1][c], up)


def _ring(mesh, centre, y, r0, r1, rings, segs, layer="ring", speed=0.6, stretch=(1.0, 1.0), axis=(1.0, 0.0)):
    """Splash disc / foam pad: annulus r0..r1, UV0.y = radial time r / speed (scrolls outward)."""
    ax = np.array(axis, dtype=float)
    ax /= np.linalg.norm(ax)
    nx = np.array([-ax[1], ax[0]])
    grid = []
    for i in range(rings + 1):
        r = r0 + (r1 - r0) * i / rings
        row = []
        for j in range(segs):
            th = TAU * j / segs
            local = ax * math.cos(th) * r * stretch[0] + nx * math.sin(th) * r * stretch[1]
            p = (centre[0] + local[0], y, centre[1] + local[1])
            row.append(mesh.add_vertex(p, (0, 1, 0), (math.cos(th) * 0.999, r / speed), None, _colour(layer)))
        grid.append(row)
    up = np.array([0.0, 1.0, 0.0])
    for i in range(rings):
        for j in range(segs):
            a, b = grid[i][j], grid[i][(j + 1) % segs]
            c, d = grid[i + 1][(j + 1) % segs], grid[i + 1][j]
            mesh.add_tri(a, b, c, up)
            mesh.add_tri(a, c, d, up)


def _crown(mesh, centre, y0, r=0.55, h=0.45, quads=12):
    """Splash crown: 12 outward-leaning cards around the landing; UV0.y = rise time (scrolls upward)."""
    for j in range(quads):
        th0, th1 = TAU * j / quads, TAU * (j + 0.8) / quads
        ids = []
        for th in (th0, th1):
            for k, hh in enumerate((0.0, h)):
                rr = r + 0.22 * (hh / h)
                p = (centre[0] + rr * math.cos(th), y0 + hh, centre[1] + rr * math.sin(th))
                n = (math.cos(th), 0.35, math.sin(th))
                ids.append(mesh.add_vertex(p, n, (-1.0 if th == th0 else 1.0, hh / 1.2), None, _colour("crown")))
        a, b, c, d = ids[0], ids[2], ids[3], ids[1]
        out = np.array([math.cos((th0 + th1) / 2), 0.0, math.sin((th0 + th1) / 2)])
        mesh.add_tri(a, b, c, out)
        mesh.add_tri(a, c, d, out)


def _cascade(mesh, model, sc, after, rows=6, cols=8, low=False):
    """Exit cascade (A2): the whole stream width falls over a lip; main sheet + lip + foam pad."""
    sp = model.sp
    p, t, n = sp.at(np.array(sc))
    before = float(sp.surface_y(np.array(sc - 0.5)))
    drop = before - after
    v0 = 0.9
    g = 9.81
    t_imp = math.sqrt(2 * drop / g)
    w = float(sp.width(np.array(sc))) + 0.1
    across3 = np.array([n[0], 0.0, n[1]])
    tan3 = np.array([t[0], 0.0, t[1]])
    lip_x0 = np.array([p[0], before, p[1]]) - tan3 * 0.6
    grid = []
    # lip: 2 rows on the surface sliding to the edge (tfall -0.5 .. 0)
    for k, tf in enumerate((-0.6 / 1.0, -0.25, 0.0)):
        q0 = lip_x0 + tan3 * (0.6 + tf * 1.0)
        row = []
        for c in range(cols + 1):
            a = -1.0 + 2.0 * c / cols
            row.append(mesh.add_vertex(q0 + across3 * (a * w / 2) + np.array([0, 0.012, 0]), (0, 1, 0), (a, tf), None, _colour("lip")))
        grid.append(row)
    up = np.array([0.0, 1.0, 0.0])
    for k in range(len(grid) - 1):
        for c in range(cols):
            mesh.add_tri(grid[k][c], grid[k][c + 1], grid[k + 1][c + 1], up)
            mesh.add_tri(grid[k][c], grid[k + 1][c + 1], grid[k + 1][c], up)
    # main sheet
    edge = np.array([p[0], before + 0.012, p[1]])
    sheet = []
    nr = max(3, rows if not low else rows // 2)
    for k in range(nr + 1):
        tt = t_imp * (k / nr) ** 0.8
        q = edge + tan3 * (v0 * tt) + np.array([0.0, -0.5 * g * tt * tt, 0.0])
        vel = tan3 * v0 + np.array([0.0, -g * tt, 0.0])
        front = np.cross(vel / np.linalg.norm(vel), across3)
        if front[1] < 0:
            front = -front
        row = []
        for c in range(cols + 1):
            a = -1.0 + 2.0 * c / cols
            row.append(mesh.add_vertex(q + across3 * (a * w / 2), front, (a, tt), None, _colour("main")))
        sheet.append((row, front))
    for k in range(nr):
        r0, f0 = sheet[k]
        r1, _ = sheet[k + 1]
        for c in range(cols):
            mesh.add_tri(r0[c], r0[c + 1], r1[c + 1], f0)
            mesh.add_tri(r0[c], r1[c + 1], r1[c], f0)
    # foam pad on the lower surface, stretched across the stream
    land = np.array([p[0], p[1]]) + t * (v0 * t_imp + 0.25)
    _ring(mesh, land, after + 0.02, 0.15, 0.95, 1 if low else 2, 12 if low else 16, "ring", 0.6,
          stretch=(0.9, max(1.0, w / 1.9)), axis=(float(t[0]), float(t[1])))


def build_falls(model, lod):
    """lod 0: High/Ultra/Epic, 1: Medium, 2: Low (spec 4.6 tier table)."""
    fa = model.falls
    mesh = MeshData(f"fx_waterfall_sm_lod{lod}")
    low = lod == 2
    rows = 10 if low else 14 if lod == 0 else 16
    _sheet(mesh, fa, rows, 3 if low else 6, lambda t: 0.92 * fa.width_at(t), None, LAYERS["back"][1], "back", 0.37)
    _sheet(mesh, fa, rows, 4 if low else 8, fa.width_at, None, 0.0, "main", 0.0)
    if lod == 0:
        for cu, wid, seed in ((-0.45, 0.42, 0.11), (0.05, 0.50, 0.53), (0.55, 0.36, 0.79)):
            _sheet(mesh, fa, rows, 3, lambda t, wid=wid: wid * (1 + 0.25 * t / fa.t_impact),
                   lambda t, cu=cu: cu * fa.width_at(t) / 2, LAYERS["front"][1], "front", seed)
        for side, seed in ((-1.0, 0.27), (1.0, 0.61)):
            _sheet(mesh, fa, rows, 3, lambda t: 0.25 * (1 + 0.2 * t / fa.t_impact),
                   lambda t, side=side: side * (fa.width_at(t) / 2 - 0.1), LAYERS["side"][1], "side", seed)
    _lip(mesh, fa)
    land = (float(fa.landing[0]), float(fa.landing[2]))
    _ring(mesh, land, model.sp.water_y + 0.02, 0.3, 1.3, 2 if low else 3, 16)
    if lod <= 1:
        _crown(mesh, land, model.sp.water_y - 0.02)
    for sc, after in model.sp.cascades:
        _cascade(mesh, model, sc, after, low=low)
    return mesh


# ----------------------------------------------------------------------------------------------------------
# Bank strip (spec 4.4): ribbon along the waterline loop
# ----------------------------------------------------------------------------------------------------------

STRIP_D = (-0.25, 0.10, 0.55, 1.05, 1.60)


def build_bank_strip(model, step=0.75, repeat=4.0):
    sp = model.sp
    loop = model.waterline()[0]
    if W.polygon_area(loop) < 0:
        loop = loop[::-1]
    pts, _, total = W.resample_loop(loop, step)
    # start the loop (and the V seam) at the point nearest the bluff toe: it is hidden under the rock
    start = int(np.argmax(pts[:, 0]))
    pts = np.roll(pts, -start, axis=0)
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    reps = max(1, round(total / repeat))
    vscale = reps / total
    # outward normals from the field gradient (smoothed along the loop)
    e = 0.05
    fx = sp.fields(pts + [e, 0])["f"] - sp.fields(pts - [e, 0])["f"]
    fz = sp.fields(pts + [0, e])["f"] - sp.fields(pts - [0, e])["f"]
    nrm = np.stack([fx, fz], 1)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1)[:, None], 1e-9)
    for _ in range(3):
        nrm = (np.roll(nrm, 1, 0) + 2 * nrm + np.roll(nrm, -1, 0))
        nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    mesh = MeshData("water_bank_strip")
    rows = []
    n_pts = len(pts)
    for k in range(n_pts + 1):
        i = k % n_pts
        v = cum[k] * vscale if k < n_pts else total * vscale
        ring = []
        for d in STRIP_D:
            q = pts[i] + nrm[i] * d
            ring.append(q)
        ring = np.array(ring)
        F = sp.fields(ring)
        ys = F["ground_y"] + 0.012
        # normals from the ground height gradient
        gx = sp.fields(ring + [e, 0])["ground_y"] - sp.fields(ring - [e, 0])["ground_y"]
        gz = sp.fields(ring + [0, e])["ground_y"] - sp.fields(ring - [0, e])["ground_y"]
        ids = []
        for j, (q, y) in enumerate(zip(ring, ys)):
            n = np.array([-gx[j] / (2 * e), 1.0, -gz[j] / (2 * e)])
            n /= np.linalg.norm(n)
            u = (STRIP_D[j] - STRIP_D[0]) / (STRIP_D[-1] - STRIP_D[0])
            ids.append(mesh.add_vertex((q[0], float(y), q[1]), n, (u, v)))
        rows.append(ids)
    up = np.array([0.0, 1.0, 0.0])
    for k in range(len(rows) - 1):
        for j in range(len(STRIP_D) - 1):
            a, b, c, d = rows[k][j], rows[k][j + 1], rows[k + 1][j + 1], rows[k + 1][j]
            mesh.add_tri(a, b, c, up)
            mesh.add_tri(a, c, d, up)
    return mesh


# ----------------------------------------------------------------------------------------------------------
# Stones (spec 4.3, 4.4 wet-line rule, 4.5)
# ----------------------------------------------------------------------------------------------------------

def icosphere(subdiv):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    verts = [np.array(p, float) / np.linalg.norm(p) for p in v]
    cache = {}

    def mid(a, b):
        key = (min(a, b), max(a, b))
        if key not in cache:
            m = verts[a] + verts[b]
            verts.append(m / np.linalg.norm(m))
            cache[key] = len(verts) - 1
        return cache[key]

    for _ in range(subdiv):
        nf = []
        for a, b, c in f:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    return np.array(verts), np.array(f)


def _noise_fn(rng):
    dirs = rng.normal(size=(7, 3))
    dirs /= np.linalg.norm(dirs, axis=1)[:, None]
    freq = np.array([1.1, 1.7, 2.3, 3.1, 4.3, 5.9, 7.7])
    amp = np.array([0.16, 0.10, 0.07, 0.05, 0.035, 0.022, 0.012])
    ph = rng.uniform(0, TAU, 7)

    def f(p):
        return (amp[None] * np.sin((p @ dirs.T) * freq[None] + ph[None])).sum(1)
    return f


def srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


MOSS = srgb_to_lin(hexrgb("#6e8a3e"))
ALGAE = srgb_to_lin(hexrgb("#4f6b3a"))


def build_stones(model, max_subdiv=3):
    mesh = MeshData("water_stones")
    for st in model.stones:
        rng = np.random.default_rng(st["seed"])
        r = st["r"]
        subdiv = min(max_subdiv, 1 if r < 0.3 else 2 if r < 1.0 else 3)
        v, faces = icosphere(subdiv)
        noise = _noise_fn(rng)
        disp = 1.0 + noise(v * 1.0)
        p = v * disp[:, None]
        # chunky river-stone proportions: flattened top, wide base, slight lean
        p[:, 1] *= st["squash"]
        p[:, 1] = np.where(p[:, 1] < -0.55 * st["squash"], -0.55 * st["squash"] + (p[:, 1] + 0.55 * st["squash"]) * 0.25, p[:, 1])
        top_flat = np.clip((p[:, 1] - 0.55 * st["squash"]) / (0.45 * st["squash"]), 0, 1)
        p[:, 1] -= top_flat * 0.12 * st["squash"]
        aspect = rng.uniform(0.75, 1.0)
        p[:, 0] *= r
        p[:, 2] *= r * aspect
        y0, y1 = p[:, 1].min(), p[:, 1].max()
        height = st["top_y"] - st["base_y"]
        p[:, 1] = st["base_y"] + (p[:, 1] - y0) / (y1 - y0) * height
        c, s = math.cos(st["yaw"]), math.sin(st["yaw"])
        x, z = p[:, 0] * c + p[:, 2] * s, -p[:, 0] * s + p[:, 2] * c
        p[:, 0], p[:, 2] = x + st["x"], z + st["z"]
        # smooth vertex normals
        n = np.zeros_like(p)
        for a, b, cc in faces:
            fn = np.cross(p[b] - p[a], p[cc] - p[a])
            n[a] += fn
            n[b] += fn
            n[cc] += fn
        n /= np.maximum(np.linalg.norm(n, axis=1)[:, None], 1e-9)
        out = (p - p.mean(0))
        if np.mean(np.sum(n * out, 1)) < 0:
            n = -n
        # painted vertex colour (linear multiplier of the stone albedo): top light, cavity, wet line, moss, algae
        ys = st["surface_y"]
        hrel = p[:, 1] - ys
        col = np.ones((len(p), 3))
        top = np.clip((p[:, 1] - st["base_y"]) / max(height, 1e-3), 0, 1)
        col *= (0.72 + 0.34 * top)[:, None]                                        # large top-light gradient
        cav = np.clip(noise(v * 2.7) * 3.0, -0.25, 0.25)
        col *= (1.0 + cav * 0.35)[:, None]                                         # hue/value variation
        wet = (hrel > -0.02) & (hrel < 0.12)
        col[wet] *= 0.62                                                           # wet line (spec 4.4)
        under = hrel <= -0.02
        col[under] *= 0.80
        deep = p[:, 1] < -0.55
        col[deep] = col[deep] * 0.7 + ALGAE * 0.30 * 2.2                           # algae below -0.55 Y
        mossy = np.clip((n[:, 1] - 0.45) / 0.4, 0, 1) * (hrel > 0.12)
        mossy *= np.clip(0.55 + noise(v * 3.3) * 2.0, 0, 1)
        col = col * (1 - mossy[:, None] * 0.85) + (MOSS * 2.4)[None] * mossy[:, None] * 0.85
        base = len(mesh.pos)
        for k in range(len(p)):
            # box-projected UVs (1 m tile): dominant normal axis picks the plane
            ax = int(np.argmax(np.abs(n[k])))
            uv = (p[k, 2], p[k, 1]) if ax == 0 else (p[k, 0], p[k, 2]) if ax == 1 else (p[k, 0], p[k, 1])
            mesh.add_vertex(p[k], n[k], uv, None, (*np.clip(col[k], 0, 2), 1.0))
        for a, b, cc in faces:
            ia, ib, ic = base + a, base + b, base + cc
            face_n = n[a] + n[b] + n[cc]
            mesh.add_tri(ia, ib, ic, face_n / np.linalg.norm(face_n))
    return mesh


# ----------------------------------------------------------------------------------------------------------
# Ground patch heights
# ----------------------------------------------------------------------------------------------------------

def ground_grid(model, step=0.35):
    x0, x1, z0, z1 = model.ground_rect()
    nx = int(round((x1 - x0) / step))
    nz = int(round((z1 - z0) / step))
    xs = np.linspace(x0, x1, nx + 1)
    zs = np.linspace(z0, z1, nz + 1)
    X, Z = np.meshgrid(xs, zs)
    F = model.sp.fields(np.stack([X.ravel(), Z.ravel()], 1))
    return {"xs": xs, "zs": zs, "y": F["ground_y"].reshape(X.shape), "f": F["f"].reshape(X.shape),
            "depth": F["depth"].reshape(X.shape), "surface_y": F["surface_y"].reshape(X.shape), "rect": [x0, x1, z0, z1]}


def build_all(model):
    meshes = {"surface": build_surface(model)}
    for lod in (0, 1, 2):
        meshes[f"falls{lod}"] = build_falls(model, lod)
    meshes["strip"] = build_bank_strip(model)
    meshes["stones"] = build_stones(model)
    return meshes


if __name__ == "__main__":
    import json
    import time
    t0 = time.time()
    m = W.WaterModel()
    meshes = build_all(m)
    print(json.dumps({k: {"verts": len(v.pos), "tris": v.triangles} for k, v in meshes.items()}, indent=1), f"{time.time() - t0:.1f}s")
