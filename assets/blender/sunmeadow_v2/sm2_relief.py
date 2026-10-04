"""Relief and structure meshes: inner bluff, west cliffs, east hills, south palisade + gate, stream bridge."""
from __future__ import annotations

import math
import random

import sm2_geom as G
from sm2_geom import bl
from sm2_meshes import SceneAcc
from sm2_place import BLUFF_TIERS, OVERHANG, bluff_top_y
from sm2_site import Site, cell_of


def _orient(verts, faces, idx, expect_bl):
    """Flip every face if the sample face's normal does not point along expect_bl (Blender-space vector)."""
    a, b, c = (verts[i] for i in faces[idx][:3])
    n = ((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
         (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
         (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    if sum(n[i] * expect_bl[i] for i in range(3)) < 0:
        return [tuple(reversed(f)) for f in faces]
    return faces


# ----------------------------------------------------------------------------
# Lattice prism (bluff tiers, overhang)
# ----------------------------------------------------------------------------

def lattice_prism(S: SceneAcc, cell, rect, rows, top_fn, seed, side_mat, top_mat, spacing=0.8, bottom_fn=None,
                  layer='relief'):
    """rows: [(y or None for lip, {x0,x1,z0,z1} insets, inward noise amp, lip drop)] bottom -> lip."""
    x0, x1, z0, z1 = rect
    nx = max(2, int(round((x1 - x0) / spacing)))
    nz = max(2, int(round((z1 - z0) / spacing)))
    perim = [(i, 0) for i in range(nx)] + [(nx, j) for j in range(nz)] + \
            [(i, nz) for i in range(nx, 0, -1)] + [(0, j) for j in range(nz, 0, -1)]
    P = len(perim)
    verts: list[tuple] = []
    side_faces, top_faces, bottom_faces = [], [], []
    ring_ids = []
    last_rect = None
    for r, (y, ins, amp, drop) in enumerate(rows):
        rx0, rx1, rz0, rz1 = x0 + ins['x0'], x1 - ins['x1'], z0 + ins['z0'], z1 - ins['z1']
        last_rect = (rx0, rx1, rz0, rz1)
        ids = []
        for k, (i, j) in enumerate(perim):
            X = rx0 + (rx1 - rx0) * i / nx
            Z = rz0 + (rz1 - rz0) * j / nz
            n = G.norm(((i == nx) - (i == 0), (j == nz) - (j == 0)))
            off = amp * G.fbm2(k * spacing / 2.6, r * 1.31 + 0.5, seed, 3)
            X, Z = X - n[0] * off, Z - n[1] * off
            yy = (top_fn(X, Z) - drop) if y is None else y
            ids.append(len(verts))
            verts.append(bl(X, Z, yy))
        ring_ids.append(ids)
    for r in range(len(rows) - 1):
        lo, hi = ring_ids[r], ring_ids[r + 1]
        for k in range(P):
            k2 = (k + 1) % P
            side_faces.append((lo[k], lo[k2], hi[k2], hi[k]))
    # Top lattice; boundary vertices are the lip ring.
    rx0, rx1, rz0, rz1 = last_rect
    lip = ring_ids[-1]
    pidx = {ij: lip[k] for k, ij in enumerate(perim)}
    grid = {}
    for j in range(nz + 1):
        for i in range(nx + 1):
            if (i, j) in pidx:
                grid[(i, j)] = pidx[(i, j)]
            else:
                X = rx0 + (rx1 - rx0) * i / nx
                Z = rz0 + (rz1 - rz0) * j / nz
                grid[(i, j)] = len(verts)
                verts.append(bl(X, Z, top_fn(X, Z)))
    for j in range(nz):
        for i in range(nx):
            top_faces.append((grid[(i, j)], grid[(i + 1, j)], grid[(i + 1, j + 1)], grid[(i, j + 1)]))
    if bottom_fn is not None:
        first = ring_ids[0]
        bidx = {ij: first[k] for k, ij in enumerate(perim)}
        y0 = rows[0][0]
        bx0, bx1, bz0, bz1 = x0 + rows[0][1]['x0'], x1 - rows[0][1]['x1'], z0 + rows[0][1]['z0'], z1 - rows[0][1]['z1']
        bgrid = {}
        for j in range(nz + 1):
            for i in range(nx + 1):
                if (i, j) in bidx:
                    bgrid[(i, j)] = bidx[(i, j)]
                else:
                    X = bx0 + (bx1 - bx0) * i / nx
                    Z = bz0 + (bz1 - bz0) * j / nz
                    bgrid[(i, j)] = len(verts)
                    verts.append(bl(X, Z, bottom_fn(X, Z)))
        for j in range(nz):
            for i in range(nx):
                bottom_faces.append((bgrid[(i, j)], bgrid[(i, j + 1)], bgrid[(i + 1, j + 1)], bgrid[(i + 1, j)]))
    # Split into two material meshes sharing a vertex list (remapped per material).
    for mat, fl in ((side_mat, side_faces + bottom_faces), (top_mat, top_faces)):
        used = sorted({i for f in fl for i in f})
        remap = {o: n for n, o in enumerate(used)}
        S.add(cell, layer, mat, [verts[o] for o in used], [tuple(remap[i] for i in f) for f in fl])


def build_bluff(site: Site, S: SceneAcc):
    lower = BLUFF_TIERS['lower']
    upper = BLUFF_TIERS['upper']
    rect = site.bluff_rect
    cx = (rect[0] + rect[1]) / 2
    cell = cell_of(cx, (rect[2] + rect[3]) / 2)

    def scaled(ins, f, extra=0.0):
        return {k: v * f + extra for k, v in ins.items()}

    ins = lower['inset']
    rows = [(-1.0, scaled(ins, 0.0), 0.0, 0.0), (0.0, scaled(ins, 0.0), 0.12, 0.0), (1.4, scaled(ins, 0.25), 0.35, 0.0),
            (3.0, scaled(ins, 0.55), 0.45, 0.0), (4.4, scaled(ins, 0.8), 0.4, 0.0), (None, scaled(ins, 1.0, 0.22), 0.3, 0.32)]
    lattice_prism(S, cell, rect, rows, lambda x, z: bluff_top_y(site, 'lower', x, z), lower['seed'], 'rock_bluff',
                  'moss_top', 0.75)
    ur = upper['rect']
    ins = upper['inset']
    rows = [(4.6, scaled(ins, 0.0), 0.1, 0.0), (6.2, scaled(ins, 0.35), 0.35, 0.0), (7.8, scaled(ins, 0.65), 0.4, 0.0),
            (9.0, scaled(ins, 0.85), 0.35, 0.0), (None, scaled(ins, 1.0, 0.2), 0.25, 0.3)]
    lattice_prism(S, cell, ur, rows, lambda x, z: bluff_top_y(site, 'upper', x, z), upper['seed'], 'rock_bluff',
                  'moss_top', 0.75)
    o = OVERHANG
    zero = {'x0': 0.0, 'x1': 0.0, 'z0': 0.0, 'z1': 0.0}
    rows = [(o['y_base'], zero, 0.15, 0.0), (o['y_base'] + 0.7, {'x0': -0.12, 'x1': 0.0, 'z0': 0.1, 'z1': 0.1}, 0.3, 0.0),
            (None, {'x0': 0.25, 'x1': 0.0, 'z0': 0.3, 'z1': 0.3}, 0.25, 0.25)]
    lattice_prism(S, cell, o['rect'], rows,
                  lambda x, z: o['y_top'] + 0.15 * (2 * G.fbm2(x / 2.0, z / 2.0, o['seed'], 2) - 1),
                  o['seed'], 'rock_bluff', 'moss_top', 0.55,
                  bottom_fn=lambda x, z: o['y_base'] - 0.35 * G.fbm2(x / 1.3, z / 1.3, o['seed'] + 7, 2))


# ----------------------------------------------------------------------------
# Swept profiles (west cliffs, east hills)
# ----------------------------------------------------------------------------

def _stations(pts, step, breaks_z=(0.0, -64.0)):
    """Dense stations along a polyline with exact stations at segment joints and at z cell breaks."""
    out = [(pts[0], G.norm(G.sub(pts[1], pts[0])))]
    for a, b in zip(pts, pts[1:]):
        t = G.norm(G.sub(b, a))
        L = math.dist(a, b)
        cuts = {0.0, 1.0}
        n = max(1, int(math.ceil(L / step)))
        cuts.update(k / n for k in range(1, n))
        for zb in breaks_z:
            if (a[1] - zb) * (b[1] - zb) < 0:
                cuts.add((a[1] - zb) / (a[1] - b[1]))
        for c in sorted(cuts)[1:]:
            out.append(((G.lerp(a[0], b[0], c), G.lerp(a[1], b[1], c)), t))
    return out


def _smooth_tangents(st, window):
    """Average station tangents over +-window metres (triangular weights) so swept profiles rotate gradually.

    Piecewise-constant tangents make long profiles cross each other at polyline joints (a fold that renders as a
    dark crease, pass-1 review: east hills at z=-40). Profile start points stay exactly on the polyline.
    """
    cum = [0.0]
    for k in range(1, len(st)):
        cum.append(cum[-1] + math.dist(st[k - 1][0], st[k][0]))
    out = []
    for k, (P, t) in enumerate(st):
        sx = sz = 0.0
        for j in range(len(st)):
            w = window - abs(cum[j] - cum[k])
            if w > 0:
                sx += st[j][1][0] * w
                sz += st[j][1][1] * w
        out.append((P, G.norm((sx, sz))))
    return out


def _sweep(S, stations, profile_fn, mat_fn, layer_fn, expect_side, cap_start=False, cap_end=False, cap_mat=None,
           cap_points=None, expect_up=False, orient_idx=None, cap_layer='relief'):
    """profile_fn(k_station, P, t) -> list of (Babylon x, z, y) points. Strips are split per (cell, layer)."""
    profiles = [profile_fn(k, P, t) for k, (P, t) in enumerate(stations)]
    m = len(profiles[0])
    # split station index ranges by cell of the face point
    groups, cur = [], [0]
    for k in range(1, len(stations)):
        c_prev = cell_of(*stations[k - 1][0])
        c_now = cell_of(*stations[k][0])
        cur.append(k)
        mid_break = abs(stations[k][0][1]) < 1e-6 or abs(stations[k][0][1] + 64.0) < 1e-6
        if mid_break and k < len(stations) - 1:
            groups.append(cur)
            cur = [k]
    groups.append(cur)
    for g in groups:
        cell = cell_of(*stations[g[len(g) // 2]][0])
        verts = []
        for k in g:
            verts += [bl(x, z, y) for (x, z, y) in profiles[k]]
        faces_by = {}
        for a in range(len(g) - 1):
            for p in range(m - 1):
                f = (a * m + p, (a + 1) * m + p, (a + 1) * m + p + 1, a * m + p + 1)
                key = (mat_fn(p), layer_fn(p))
                faces_by.setdefault(key, []).append(f)
        # orientation from a sample face: profile row 2 should face expect_side (or up when expect_up)
        sample_key = (mat_fn(min(2, m - 2)), layer_fn(min(2, m - 2)))
        flip = False
        if sample_key in faces_by:
            fl = faces_by[sample_key]
            P, t = stations[g[0]]
            if expect_up:
                exp_bl = (0.0, 0.0, 1.0)
                idx = orient_idx if orient_idx is not None else 0
            else:
                e = expect_side(t)
                exp_bl = (-e[0], -e[1], 0.0)
                idx = min(2, len(fl) - 1)
            fixed = _orient(verts, fl, idx, exp_bl)
            flip = fixed[0] != fl[0]
        for (mat, layer), fl in faces_by.items():
            if flip:
                fl = [tuple(reversed(f)) for f in fl]
            used = sorted({i for f in fl for i in f})
            remap = {o: n for n, o in enumerate(used)}
            S.add(cell if layer != 'context' else 'none', layer, mat, [verts[o] for o in used],
                  [tuple(remap[i] for i in f) for f in fl])
    for flag, k, sgn in ((cap_start, 0, -1), (cap_end, len(stations) - 1, 1)):
        if not flag:
            continue
        prof = profiles[k][:cap_points] if cap_points else profiles[k]
        P, t = stations[k]
        q2 = []
        for (x, z, y) in prof:
            m_dir = (-G.left_normal(t)[0], -G.left_normal(t)[1])
            q2.append((G.dot(G.sub((x, z), P), m_dir), y))
        tris = G.ear_clip(q2)
        verts = [bl(x, z, y) for (x, z, y) in prof]
        tris = _orient(verts, tris, 0, (-t[0] * sgn, -t[1] * sgn, 0.0))
        S.add('none' if cap_layer == 'context' else cell_of(*P), cap_layer, cap_mat, verts, tris)


def build_cliffs(site: Site, S: SceneAcc):
    rel = site.relief['west_cliffs']
    hmin, hmax = rel['height_m']
    runs = site.cliff_runs()
    runs[-1] = runs[-1] + [(-55.2, -125.0)]          # frame extension inside art cell r6 (beyond the stage)
    gz = rel['gap']['between_z']
    u_base = 0.0
    batter = 0.12
    edge_x = -64.0

    def H(u, z):
        n = G.noise1(u / 23.0, 41, 3)
        n = min(1.0, max(0.0, (n - 0.25) / 0.5))
        h = hmin + (hmax - hmin) * n
        near_gap = min(abs(z - gz[0]), abs(z - gz[1]))
        if near_gap < 7:
            h += 1.6 * (1 - near_gap / 7)
        return min(hmax, max(hmin, h))

    for ri, run in enumerate(runs):
        st = _smooth_tangents(_stations(run, 1.2), 14.0)
        cum = [0.0]
        for k in range(1, len(st)):
            cum.append(cum[-1] + math.dist(st[k - 1][0], st[k][0]))

        def profile(k, P, t, cum=cum, ri=ri, context=False):
            u = (ri * 400.0) + cum[k]
            h = H(u, P[1])
            east = G.left_normal(t)
            west = (-east[0], -east[1])
            far = (P[0] - edge_x) / max(0.2, -west[0]) if west[0] < -0.2 else 9.0
            pts = []

            def at(o, y):
                return (P[0] + west[0] * o, P[1] + west[1] * o, y)

            noise = [G.fbm2(u / 2.4, r * 1.7, 59 + ri, 3) for r in range(8)]
            pts.append(at(0.0, -1.2))
            pts.append(at(0.15 * noise[0], 0.0))
            for r, f in enumerate((0.2, 0.42, 0.64, 0.84)):
                pts.append(at(batter * h * f + 0.75 * noise[r + 1] - 0.15, h * f))
            lip_o = batter * h + 0.45 + 0.4 * noise[5]
            pts.append(at(lip_o, h - 0.3))
            pts.append(at(lip_o + 1.0, h + 0.2 * noise[6]))
            o3 = min(far - 1.0, lip_o + 3.6)
            pts.append(at(o3, h + 0.45 * noise[7] - 0.1))
            pts.append(at(far, h - 0.6))
            pts.append(at(far, -1.2))
            if context:
                # render-only plateau continuation west of the cell edge; a closed solid (base point + end caps)
                # so no view can look into an unlit open shell (pass-1 review: black faces at the stream gap)
                return [at(far, -1.2), at(far, h - 0.6), at(far + 14.0, h - 1.2 - 1.5 * noise[2]), at(far + 34.0, h - 2.0),
                        at(far + 34.0, -1.2)]
            return pts

        mats = ['cliff', 'cliff', 'cliff', 'cliff', 'cliff', 'cliff', 'cliff_top', 'cliff_top', 'cliff_top', 'cliff']
        # End caps use the whole 11-point profile: the old cap_points=10 dropped the base point at the cell edge and
        # left a triangular hole in each stream-gap wall (pass-2 review: black slab seen through the gap).
        _sweep(S, st, profile, lambda p: mats[p], lambda p: 'relief',
               lambda t: G.left_normal(t), cap_start=True, cap_end=True, cap_mat='cliff', cap_points=None)
        _sweep(S, st, lambda k, P, t: profile(k, P, t, context=True), lambda p: 'context_cliff', lambda p: 'context',
               lambda t: (0.0, 0.0), expect_up=True, orient_idx=1, cap_start=True, cap_end=True,
               cap_mat='context_cliff', cap_layer='context')
        u_base += 400.0


def build_hills(site: Site, S: SceneAcc):
    rel = site.relief['east_hills']
    hmin, hmax = rel['height_m']
    toe = site.hill_toe() + [(46.5, -125.0)]
    st = _smooth_tangents(_stations(toe, 2.0), 24.0)
    cum = [0.0]
    for k in range(1, len(st)):
        cum.append(cum[-1] + math.dist(st[k - 1][0], st[k][0]))
    edge_x = 64.0
    # Toe bank: the collider starts at the toe line, so the visible slope must rise there (pass-1 collider check:
    # the old gentle toe left a 2.6-2.9 m invisible margin at body height). 1.25 m earth bank within 0.55 m.
    BANK = 1.25
    vs = [-0.45, 0.0, 0.12, 0.25, 0.4, 0.55, 0.8, 1.2, 1.9, 3.3, 5.0, 7.0, 9.5]

    def profile(k, P, t):
        u = cum[k]
        east = G.left_normal(t)
        n = G.noise1(u / 17.0, 73, 3)
        H = hmin + (hmax - hmin) * min(1.0, max(0.0, (n - 0.25) / 0.5))
        far = (edge_x - P[0]) / max(0.2, east[0])
        pts = []
        samples = [v for v in vs if v < far - 0.8] + [far, far + 8.0, far + 18.0]
        for v in samples:
            if v < 0:
                y = -0.25
            else:
                shape = G.smoothstep(0.0, 9.5, v) ** 0.85
                bump = 0.9 * (2 * G.fbm2(u / 9.0, v / 6.0, 77, 2) - 1) * G.smoothstep(2.0, 7.0, v)
                y = BANK * G.smoothstep(-0.05, 0.55, v) + max(0.0, H - BANK) * shape + bump
                if v > far + 1:
                    y = H * (0.85 - 0.02 * (v - far)) + bump
            pts.append((P[0] + east[0] * v, P[1] + east[1] * v, y))
        return pts

    m = len(profile(0, *st[0]))
    lens = {len(profile(k, *s)) for k, s in enumerate(st)}
    if len(lens) != 1:
        # keep a constant profile length: pad by repeating the far sample count from the first station
        raise RuntimeError(f'hill profile length varies {lens}')
    _sweep(S, st, profile, lambda p: 'hill' if p < m - 3 else 'context_hill',
           lambda p: 'context' if p >= m - 3 else 'relief', lambda t: (0.0, 0.0), expect_up=True)


# ----------------------------------------------------------------------------
# South palisade, closed gate, camp palisade runs
# ----------------------------------------------------------------------------

def palisade_run(S: SceneAcc, a, b, h_range, seed, layer='relief', rails_side=-1, mat='palisade'):
    rng = random.Random(seed)
    L = math.dist(a, b)
    u = G.norm(G.sub(b, a))
    n = G.left_normal(u)
    count = max(2, int(L / 0.33))
    yaw = G.yaw_to(u[0], u[1])
    for k in range(count + 1):
        t = k / count
        p = (G.lerp(a[0], b[0], t) + n[0] * rng.uniform(-0.03, 0.03), G.lerp(a[1], b[1], t) + n[1] * rng.uniform(-0.03, 0.03))
        h = rng.uniform(*h_range)
        v, f = G.cone_mesh(0.16, 0.15, -0.3, h, 6, bottom=False, top=False, phase=rng.uniform(0, 1))
        v2, f2 = G.cone_mesh(0.15, 0.0, h, h + 0.34, 6, bottom=False, phase=rng.uniform(0, 1))
        base = len(v)
        cell = cell_of(*p)
        S.add_local(cell, layer, mat, (v + v2, f + [tuple(i + base for i in ff) for ff in f2]), p[0], p[1], yaw)
    for y in (0.75, 1.85):
        mid = ((a[0] + b[0]) / 2 + n[0] * rails_side * 0.24, (a[1] + b[1]) / 2 + n[1] * rails_side * 0.24)
        v, f = G.box_mesh(0.12, L, y - 0.07, y + 0.07)
        S.add_local(cell_of(*mid), layer, 'timber', (v, f), mid[0], mid[1], yaw)


def build_south_wall(site: Site, S: SceneAcc):
    for k, (name, (a, b)) in enumerate(site.palisade_runs().items()):
        palisade_run(S, a, b, (2.45, 2.95), G.stable_seed(name), rails_side=-1 if 'wing' not in name else 1)
    (wx, wz), (ex, ez) = site.gate_posts()
    inner = 5.95
    rng = random.Random(G.stable_seed('south_gate'))
    for side in (-1, 1):
        x0, x1 = (-inner, -0.03) if side < 0 else (0.03, inner)
        planks = 8
        for k in range(planks):
            xa = G.lerp(x0, x1, k / planks) + 0.015
            xb = G.lerp(x0, x1, (k + 1) / planks) - 0.015
            h = 2.25 + 0.12 * math.sin(k * 1.3) + rng.uniform(0, 0.06)
            v, f = G.box_mesh(xb - xa, 0.12, 0.0, h)
            S.add_local(cell_of((xa + xb) / 2, wz), 'relief', 'gate_timber', (v, f), (xa + xb) / 2, wz, 0.0)
        for y in (0.55, 1.75):
            v, f = G.box_mesh(x1 - x0 - 0.2, 0.1, y - 0.09, y + 0.09)
            S.add_local(cell_of((x0 + x1) / 2, wz), 'relief', 'timber', (v, f), (x0 + x1) / 2, wz - 0.11, 0.0)
        # diagonal brace
        L = math.hypot(x1 - x0 - 0.4, 1.2)
        ang = math.atan2(1.2, x1 - x0 - 0.4)
        v, f = G.box_mesh(L, 0.09, -0.08, 0.08)
        v = [(x * math.cos(ang * side), y, z + x * math.sin(ang * side)) for (x, y, z) in v]
        S.add_local(cell_of((x0 + x1) / 2, wz), 'relief', 'timber', (v, f), (x0 + x1) / 2, wz - 0.12, 0.0, base_y=1.15)
        # iron bands
        for y in (0.4, 1.95):
            v, f = G.box_mesh(x1 - x0 - 0.1, 0.14, y - 0.04, y + 0.04)
            S.add_local(cell_of((x0 + x1) / 2, wz), 'relief', 'iron', (v, f), (x0 + x1) / 2, wz + 0.01, 0.0)


# ----------------------------------------------------------------------------
# Stream bridge
# ----------------------------------------------------------------------------

def build_bridge(site: Site, S: SceneAcc):
    c, u, n = site.bridge_c, site.bridge_u, site.bridge_n
    hl, hw = site.bridge_hl, site.bridge_hw
    yaw = G.yaw_to(u[0], u[1])       # local v (facing) runs along the bridge
    cell = cell_of(*c)

    def P(a, l):
        return (c[0] + u[0] * a + n[0] * l, c[1] + u[1] * a + n[1] * l)

    # deck planks across the width (local u axis = -n ... use add_local with yaw along the bridge)
    planks = 25
    for k in range(planks):
        a0 = -hl + 2 * hl * k / planks + 0.012
        a1 = -hl + 2 * hl * (k + 1) / planks - 0.012
        p = P((a0 + a1) / 2, 0.0)
        drop = 0.012 * math.sin(k * 2.1)
        v, f = G.box_mesh(2 * hw, a1 - a0, -0.12 + drop, 0.0 + drop * 0.3)
        S.add_local(cell, 'bridge', 'timber_light', (v, f), p[0], p[1], yaw)
    for l in (-1.35, 0.0, 1.35):
        p = P(0.0, l)
        v, f = G.box_mesh(0.22, 2 * hl + 0.3, -0.33, -0.12)
        S.add_local(cell, 'bridge', 'timber', (v, f), p[0], p[1], yaw)
    # rails: posts, top rail, rope
    for side in (-1, 1):
        l = side * 1.95
        for k in range(5):
            a = -hl + 0.25 + (2 * hl - 0.5) * k / 4
            p = P(a, l)
            v, f = G.box_mesh(0.15, 0.15, -0.3, 1.12)
            S.add_local(cell, 'bridge', 'timber', (v, f), p[0], p[1], yaw)
        p = P(0.0, l)
        v, f = G.box_mesh(0.11, 2 * hl - 0.3, 0.98, 1.08)
        S.add_local(cell, 'bridge', 'timber', (v, f), p[0], p[1], yaw)
        v, f = G.box_mesh(0.05, 2 * hl - 0.3, 0.52, 0.57)
        S.add_local(cell, 'bridge', 'rope', (v, f), p[0], p[1], yaw)
    # stone abutments under both deck ends + corner stones flanking the deck ends
    for end in (-1, 1):
        p = P(end * (hl - 0.35), 0.0)
        v, f = G.box_mesh(2 * hw + 0.9, 1.6, -1.15, -0.12)
        S.add_local(cell, 'bridge', 'stone_light', (v, f), p[0], p[1], yaw)
        for side in (-1, 1):
            q = P(end * (hl - 0.1), side * 2.0)
            v, f = G.box_mesh(0.5, 0.55, -1.0, 0.85, taper=0.86)
            S.add_local(cell, 'bridge', 'stone_light', (v, f), q[0], q[1], yaw + 0.05 * side)
