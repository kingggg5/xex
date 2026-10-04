"""Mesh generation for the Sunmeadow v2 blockout (pure Python; Blender-space vertices).

Geometry is accumulated per (cell, layer, material) so each 64 m cell exports as a handful of merged meshes.
Layers: ground, path, water, relief, bridge, landmark, prop, rock (structure budget) and veg (vegetation proxies,
excluded from the triangle budget). Render-only layers: context, witness, annotation.
"""
from __future__ import annotations

import math
import random

import sm2_geom as G
from sm2_geom import bl
from sm2_site import Site, cell_of

EXPORT_LAYERS = ('ground', 'path', 'water', 'relief', 'bridge', 'landmark', 'prop', 'rock', 'veg')
BUDGET_LAYERS = ('ground', 'path', 'water', 'relief', 'bridge', 'landmark', 'prop', 'rock')
SMOOTH_MATS = {'broadleaf_L', 'broadleaf_M', 'broadleaf_S', 'bush', 'bush_flowering', 'hero_canopy', 'hay', 'water',
               'moss_top', 'hill', 'context_hill', 'witness'}

CELLS_X = [(-64.0, 0.0), (0.0, 64.0)]
CELLS_Z = [(-128.0, -64.0), (-64.0, 0.0), (0.0, 24.0)]


def disc_mesh(r, segments=16, z=0.0, jitter=0.0, seed=0):
    rng = random.Random(seed)
    v = [(0.0, 0.0, z)]
    for k in range(segments):
        a = math.tau * k / segments
        rr = r * (1 + rng.uniform(-jitter, jitter))
        v.append((rr * math.cos(a), rr * math.sin(a), z))
    f = [(0, 1 + k, 1 + (k + 1) % segments) for k in range(segments)]
    return v, f


class SceneAcc:
    def __init__(self):
        self.acc: dict[tuple[str, str, str], G.MeshAcc] = {}

    def add(self, cell, layer, mat, verts, faces):
        key = (cell, layer, mat)
        if key not in self.acc:
            self.acc[key] = G.MeshAcc(smooth=mat in SMOOTH_MATS)
        self.acc[key].add(verts, faces)

    def add_local(self, cell, layer, mat, vf, x, z, yaw=0.0, base_y=0.0, scale=(1, 1, 1)):
        """Local mesh (u = Babylon local X, v = local Z/facing, w = up) placed at Babylon (x, z) with yaw."""
        v, f = vf
        self.add(cell, layer, mat, G.transform(v, rot=math.pi - yaw, scale=scale, offset=bl(x, z, base_y)), f)

    def triangles(self, cell=None, layers=None):
        return sum(a.triangles for (c, l, m), a in self.acc.items()
                   if (cell is None or c == cell) and (layers is None or l in layers))


# ----------------------------------------------------------------------------
# Ground
# ----------------------------------------------------------------------------

def _axis(lo, hi, fine_lo, fine_hi, fine, coarse, breaks=()):
    """Monotone sample positions: fine spacing inside [fine_lo, fine_hi], coarse elsewhere, plus exact breaks."""
    pts = {round(lo, 4), round(hi, 4)}
    for b in breaks:
        if lo < b < hi:
            pts.add(round(b, 4))
    flo, fhi = max(lo, fine_lo), min(hi, fine_hi)
    if flo < fhi:
        n = int(math.ceil((fhi - flo) / fine))
        pts.update(round(flo + (fhi - flo) * k / n, 4) for k in range(n + 1))
    for a, b in ((lo, min(hi, flo if flo < fhi else hi)), (max(lo, fhi if flo < fhi else lo), hi)):
        if b - a > 1e-6:
            n = int(math.ceil((b - a) / coarse))
            pts.update(round(a + (b - a) * k / n, 4) for k in range(n + 1))
    return sorted(pts)


def build_ground(site: Site, S: SceneAcc):
    canals = site.canal_rects()
    for (x0, x1) in CELLS_X:
        for (z0, z1) in CELLS_Z:
            cell = cell_of((x0 + x1) / 2, (z0 + z1) / 2)
            breaks = []
            for (cx0, cx1, cz0, cz1) in canals:
                breaks += [cx0, cx1, cz0, cz1]
            xs = _axis(x0, x1, -66.0, -4.0, 0.5, 2.0, breaks)
            zs = _axis(z0, z1, -66.0, -32.5, 0.5, 2.0, breaks)
            if cell_of((x0 + x1) / 2, (z0 + z1) / 2) not in ('c7_r7',):
                xs = _axis(x0, x1, 0, 0, 0.5, 2.0, breaks)
                zs = _axis(z0, z1, 0, 0, 0.5, 2.0, breaks)
            nx = len(xs)
            verts = []
            heights = []
            for z in zs:
                for x in xs:
                    h = site.ground_h((x, z))
                    heights.append(h)
                    verts.append(bl(x, z, h))
            faces = {'grass': [], 'bank_mud': []}
            for j in range(len(zs) - 1):
                for i in range(nx - 1):
                    cxz = ((xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2)
                    if any(cx0 <= cxz[0] <= cx1 and cz0 <= cxz[1] <= cz1 for (cx0, cx1, cz0, cz1) in canals):
                        continue        # city canal hazard: no ground (the live canal owns this space)
                    a, b = j * nx + i, j * nx + i + 1
                    c, d = (j + 1) * nx + i + 1, (j + 1) * nx + i
                    low = min(heights[a], heights[b], heights[c], heights[d]) < -0.02
                    faces['bank_mud' if low else 'grass'].append((a, b, c, d))
            for mat, fl in faces.items():
                if fl:
                    used = sorted({i for f in fl for i in f})
                    remap = {o: n for n, o in enumerate(used)}
                    S.add(cell, 'ground', mat, [verts[o] for o in used], [tuple(remap[i] for i in f) for f in fl])


# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------

def _strip(centre, hw, y, round_start, round_end):
    tangents, normals = G.polyline_normals(centre)
    verts, faces = [], []
    for c, n in zip(centre, normals):
        verts.append(bl(c[0] - n[0] * hw, c[1] - n[1] * hw, y))   # right
        verts.append(bl(c[0] + n[0] * hw, c[1] + n[1] * hw, y))   # left
    for i in range(len(centre) - 1):
        r0, l0, r1, l1 = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        faces.append((r0, r1, l1, l0))
    for at_start, flag in ((True, round_start), (False, round_end)):
        if not flag:
            continue
        c = centre[0] if at_start else centre[-1]
        t = tangents[0] if at_start else tangents[-1]
        base = len(verts)
        verts.append(bl(c[0], c[1], y))
        n = G.left_normal(t)
        seg = 8
        # half disc on the outside of the end: from left normal through -t (start) or +t (end) to right normal
        sgn = -1 if at_start else 1
        for k in range(seg + 1):
            a = math.pi * k / seg
            d = (n[0] * math.cos(a) + sgn * t[0] * math.sin(a), n[1] * math.cos(a) + sgn * t[1] * math.sin(a))
            verts.append(bl(c[0] + d[0] * hw, c[1] + d[1] * hw, y))
        for k in range(seg):
            f = (base, base + 1 + k, base + 2 + k)
            faces.append(f if at_start else (f[0], f[2], f[1]))
    return verts, faces


def _cell_split(pts):
    """Split a centreline into runs per art cell (break at the midpoint between differing samples)."""
    runs, cur, cur_cell = [], [pts[0]], cell_of(*pts[0])
    for p in pts[1:]:
        c = cell_of(*p)
        if c != cur_cell:
            mid = ((cur[-1][0] + p[0]) / 2, (cur[-1][1] + p[1]) / 2)
            cur.append(mid)
            runs.append((cur_cell, cur))
            cur, cur_cell = [mid], c
        cur.append(p)
    runs.append((cur_cell, cur))
    return runs


def build_paths(site: Site, S: SceneAcc):
    stage_top = site.stage[3]
    for pid, pf in site.paths.items():
        pts = G.fillet_polyline(pf.line.pts, max(pf.hw + 0.6, 2.6), step=1.0, arc_step=0.5)
        pieces = [pts]
        if pid == 'southbound_trail':
            # cut the strip where the bridge deck replaces it
            keep, cur = [], []
            for p in pts:
                a, l = site.bridge_local(p)
                if abs(a) <= site.bridge_hl + 0.02 and abs(l) <= site.bridge_hw + 1.0:
                    if cur:
                        keep.append(cur)
                        cur = []
                    continue
                cur.append(p)
            if cur:
                keep.append(cur)
            pieces = []
            for k, run in enumerate(keep):
                # snap the cut ends exactly to the deck ends
                if k == 0:
                    run = run + [G.add(site.bridge_c, G.mul(site.bridge_u, -(site.bridge_hl + 0.02)))]
                else:
                    run = [G.add(site.bridge_c, G.mul(site.bridge_u, site.bridge_hl + 0.02))] + run
                pieces.append(run)
        for k, run in enumerate(pieces):
            round_start = not (pid == 'southbound_trail' and k > 0)
            round_end = not (pid == 'southbound_trail' and k == 0 and len(pieces) > 1)
            if run[0][1] >= stage_top - 0.01:
                round_start = False
            # worn cobble at the city ramps: first 5 m of both gate roads
            cobble = []
            if pid in ('gate_road', 'gate_road_east'):
                acc, cut = 0.0, 0
                for i in range(1, len(run)):
                    acc += math.dist(run[i - 1], run[i])
                    if acc >= 5.0:
                        cut = i
                        break
                cobble, run = run[:cut + 1], run[cut:]
            for cell, sub in _cell_split(run):
                if len(sub) < 2:
                    continue
                first = sub is run or sub[0] == run[0]
                last = sub[-1] == run[-1]
                v, f = _strip(sub, pf.hw, pf.y, round_start and first and not cobble, round_end and last)
                S.add(cell, 'path', f'path_{pid}', v, f)
            if cobble:
                for cell, sub in _cell_split(cobble):
                    v, f = _strip(sub, pf.hw, pf.y + 0.002, round_start and sub[0] == cobble[0], False)
                    S.add(cell, 'path', 'path_cobble', v, f)


# ----------------------------------------------------------------------------
# Water: stream + pool surface, waterfall, foam
# ----------------------------------------------------------------------------

def build_water(site: Site, S: SceneAcc):
    pts, tris = G.clip_grid_below(lambda x, z: site.water_mask((x, z), extended=True), -86.0, -4.0, -68.0, -32.0, 0.4)
    by_layer: dict[tuple[str, str], list] = {}
    for t in tris:
        cx = sum(pts[i][0] for i in t) / 3
        cz = sum(pts[i][1] for i in t) / 3
        if cx < site.stage[0]:
            key = ('none', 'context')
        else:
            key = (cell_of(cx, cz), 'water')
        by_layer.setdefault(key, []).append(t)
    for (cell, layer), tl in by_layer.items():
        used = sorted({i for t in tl for i in t})
        remap = {o: n for n, o in enumerate(used)}
        verts = [bl(pts[o][0], pts[o][1], site.water_y) for o in used]
        S.add(cell, layer, 'water' if layer == 'water' else 'context_water', verts,
              [tuple(remap[i] for i in t) for t in tl])
    # Waterfall: curved ribbon from the spring mouth on the bluff's west face to the pool.
    f = site.falls
    tx, tz = f['top_xz']
    top_y, bot_y, w = float(f['top_y']), float(f['bottom_y']), float(f['width_m'])
    px, pz, pr = site.pool
    land_x = px + pr - 1.7          # lands 1.7 m inside the pool's east edge
    n = 12
    verts, faces = [], []
    for k in range(n + 1):
        t = k / n
        x = tx - 0.06 - (tx - 0.06 - land_x) * (t ** 1.7)
        y = top_y + (bot_y + 0.02 - top_y) * t
        spread = w / 2 * (1 + 0.25 * t)
        verts.append(bl(x, tz - spread, y))
        verts.append(bl(x, tz + spread, y))
    for k in range(n):
        a, b, c, d = 2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2
        faces.append((a, b, c, d))
        faces.append((a, d, c, b))
    S.add(cell_of(tx, tz), 'water', 'waterfall', verts, faces)
    v, fc = disc_mesh(1.05, 16)
    S.add(cell_of(land_x, tz), 'water', 'foam', G.transform(v, offset=bl(land_x - 0.2, tz, site.water_y + 0.012)), fc)
    # Dark spring mouth set into the face behind the top of the falls.
    vb, fb = G.box_mesh(1.9, 0.65, -0.55, 0.45)
    S.add_local(cell_of(tx, tz), 'relief', 'spring_dark', (vb, fb), tx + 0.28, tz, yaw=math.pi / 2, base_y=top_y + 0.1)


def build_decals(site: Site, S: SceneAcc):
    """Ground decals for disc clearings (oak_wallow mud) — visual only, a few mm above the walk plane."""
    for cid, c in site.clearings.items():
        if 'radius_m' not in c:
            continue
        cx, cz = (float(v) for v in c['center_xz'])
        r = float(c['radius_m'])
        rng = random.Random(G.stable_seed(cid))
        n = 40
        v = [bl(cx, cz, 0.004)]
        for k in range(n):
            a = math.tau * k / n
            rr = r * (0.96 + 0.08 * (2 * G.noise1(k / 5.0, 91, 2) - 1))
            v.append(bl(cx + rr * math.cos(a), cz + rr * math.sin(a), 0.004))
        f = [(0, 1 + k, 1 + (k + 1) % n) for k in range(n)]
        S.add(cell_of(cx, cz), 'ground', 'mud', v, f)
        # Puddles never overlap and each sits at its own height: coplanar overlapping discs self-shadow in a path
        # tracer and z-fight in a depth buffer (pass-2 review: black patches in the wallow).
        placed = []
        for j in range(3):
            for _try in range(40):
                a = rng.uniform(0, math.tau)
                d = rng.uniform(1.5, r * 0.6)
                pr = rng.uniform(1.0, 1.9)
                px, pz = cx + d * math.cos(a), cz + d * math.sin(a)
                if all(math.hypot(px - qx, pz - qz) > pr + qr + 0.6 for qx, qz, qr in placed):
                    break
            else:
                continue
            placed.append((px, pz, pr))
            pv, pf = disc_mesh(pr, 14, jitter=0.18, seed=rng.randrange(1 << 20))
            S.add(cell_of(cx, cz), 'ground', 'mud_puddle', G.transform(pv, offset=bl(px, pz, 0.008 + 0.003 * j)), pf)
