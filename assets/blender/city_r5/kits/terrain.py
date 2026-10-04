"""R5 terrain kit: floating island, terraces, canal, pools, waterfalls, paths,
radial plaza paving and the hanging cliff underside.

Owned by D3 (PM). Reads layout.json; builds in layout/world coordinates
(metres, Z up, origin = fountain centre). Everything is original geometry.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import citykit as ck  # noqa: E402


# ---------------------------------------------------------------------------
# small math helpers
# ---------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _resample(points: np.ndarray, count: int) -> np.ndarray:
    """Resample a polyline to count points evenly spaced by arc length."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    target = np.linspace(0.0, s[-1], count)
    x = np.interp(target, s, points[:, 0])
    y = np.interp(target, s, points[:, 1])
    return np.stack([x, y], axis=1)


# ---------------------------------------------------------------------------
# Island outline and Coons-patch ground grid
# ---------------------------------------------------------------------------
class Island:
    def __init__(self, layout: dict):
        isl = layout['island']
        self.x0, self.x1 = isl['x_min'], isl['x_max']
        self.y0, self.y1 = isl['y_min'], isl['y_max']
        self.r = isl['corner_radius']
        self.noise = isl['edge_noise_m']
        self.depth = isl['underside_depth_m']
        self.cx = (self.x0 + self.x1) * 0.5
        self.cy = (self.y0 + self.y1) * 0.5

    def _arc(self, c, a0, a1, n=24):
        a = np.radians(np.linspace(a0, a1, n))
        return np.stack([c[0] + self.r * np.cos(a), c[1] + self.r * np.sin(a)], axis=1)

    def _line(self, p0, p1, n=40):
        t = np.linspace(0, 1, n)[:, None]
        return np.asarray(p0) * (1 - t) + np.asarray(p1) * t

    def _displace(self, pts: np.ndarray, normals: np.ndarray) -> np.ndarray:
        """Organic edge noise, kept straight where the gate front and the castle
        terrace need clean edges."""
        phi = np.arctan2(pts[:, 1] - self.cy, pts[:, 0] - self.cx)
        n = (0.50 * np.sin(3 * phi + 0.7) + 0.30 * np.sin(7 * phi + 2.1)
             + 0.20 * np.sin(13 * phi + 4.2) + 0.12 * np.sin(23 * phi + 1.3))
        south = (pts[:, 1] < self.y0 + self.r * 0.6) * (1 - smoothstep(52, 72, np.abs(pts[:, 0])))
        north = (pts[:, 1] > self.y1 - self.r * 0.6) * (1 - smoothstep(84, 100, np.abs(pts[:, 0])))
        mask = 1 - np.clip(south + north, 0, 1)
        return pts + normals * (self.noise * n * mask)[:, None]

    def _curve(self, parts):
        pts = np.concatenate(parts, axis=0)
        # outward normals of the undisplaced rounded rectangle
        nx = np.zeros(len(pts))
        ny = np.zeros(len(pts))
        for i, (x, y) in enumerate(pts):
            qx = min(max(x, self.x0 + self.r), self.x1 - self.r)
            qy = min(max(y, self.y0 + self.r), self.y1 - self.r)
            dx, dy = x - qx, y - qy
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                # on a straight edge: pick the nearest side
                d = [x - self.x0, self.x1 - x, y - self.y0, self.y1 - y]
                k = int(np.argmin(d))
                dx, dy = [(-1, 0), (1, 0), (0, -1), (0, 1)][k]
                ln = 1.0
            nx[i], ny[i] = dx / ln, dy / ln
        return self._displace(pts, np.stack([nx, ny], axis=1))

    def boundary_curves(self, nu: int, nv: int):
        r = self.r
        sw = (self.x0 + r, self.y0 + r)
        se = (self.x1 - r, self.y0 + r)
        ne = (self.x1 - r, self.y1 - r)
        nw = (self.x0 + r, self.y1 - r)
        bottom = self._curve([self._arc(sw, 225, 270), self._line((self.x0 + r, self.y0), (self.x1 - r, self.y0), 80),
                              self._arc(se, 270, 315)])
        right = self._curve([self._arc(se, 315, 360), self._line((self.x1, self.y0 + r), (self.x1, self.y1 - r), 90),
                             self._arc(ne, 0, 45)])
        top = self._curve([self._arc(nw, 135, 90), self._line((self.x0 + r, self.y1), (self.x1 - r, self.y1), 80),
                           self._arc(ne, 90, 45)])
        left = self._curve([self._arc(sw, 225, 180), self._line((self.x0, self.y0 + r), (self.x0, self.y1 - r), 90),
                            self._arc(nw, 180, 135)])
        return (_resample(bottom, nu + 1), _resample(right, nv + 1),
                _resample(top, nu + 1), _resample(left, nv + 1))

    def coons_grid(self, nu: int, nv: int) -> np.ndarray:
        B, R, T, L = self.boundary_curves(nu, nv)
        u = np.linspace(0, 1, nu + 1)[None, :, None]
        v = np.linspace(0, 1, nv + 1)[:, None, None]
        Bu, Tu = B[None, :, :], T[None, :, :]
        Lv, Rv = L[:, None, :], R[:, None, :]
        c00, c10, c01, c11 = B[0], B[-1], T[0], T[-1]
        P = ((1 - v) * Bu + v * Tu + (1 - u) * Lv + u * Rv
             - ((1 - u) * (1 - v) * c00 + u * (1 - v) * c10 + (1 - u) * v * c01 + u * v * c11))
        return P  # shape (nv+1, nu+1, 2)

    def outline_loop(self, nu: int, nv: int) -> np.ndarray:
        """CCW loop of boundary points consistent with the grid border."""
        B, R, T, L = self.boundary_curves(nu, nv)
        return np.concatenate([B[:-1], R[:-1], T[::-1][:-1], L[::-1][:-1]], axis=0)


# ---------------------------------------------------------------------------
# Height field
# ---------------------------------------------------------------------------
class Heights:
    """Ground height z(x, y) for grass, paths and building pads. Terraces,
    canal and pools are separate meshes; the ground only has soft slopes."""

    def __init__(self, layout: dict, outline: np.ndarray):
        self.layout = layout
        self.outline = outline
        self.pads = []
        levels = layout['levels']
        for lm in layout['landmarks']:
            kind = lm['kind']
            if kind in ('castle', 'stairs', 'arcade', 'wizard_tower', 'windmill', 'bridge_arched', 'gate'):
                continue
            level = levels.get(lm.get('level', 'plaza'), 0.0)
            if 'centers' in lm:
                for c in lm['centers']:
                    self.pads.append((c, lm.get('footprint', [12, 10]), level))
            elif 'center' in lm and 'footprint' in lm:
                self.pads.append((lm['center'], lm['footprint'], level))
        # Ground pools (gate + NE garden) sit in the terrain; their level is the
        # raw ground height at the pool centre and the ground is flattened round them.
        self.pools = []
        for pool in layout['water']['pools']:
            if pool['id'].startswith(('gate_pool', 'ne_garden')):
                cx, cy = pool['center']
                lvl = float(self._raw(np.array([cx]), np.array([cy]))[0])
                self.pools.append(dict(pool, level=lvl))

    def _raw(self, x, y):
        z = self.ne_slope(x, y)
        return z - 0.5 * smoothstep(-122, -146, y)

    def pool_level(self, pid):
        for p in self.pools:
            if p['id'] == pid:
                return p['level']
        return None

    def edge_distance(self, x, y):
        pts = np.stack([np.ravel(x), np.ravel(y)], axis=1)
        out = np.empty(len(pts))
        ol = self.outline
        for i in range(0, len(pts), 2048):
            chunk = pts[i:i + 2048]
            d = np.sqrt(((chunk[:, None, :] - ol[None, :, :]) ** 2).sum(-1)).min(1)
            out[i:i + 2048] = d
        return out.reshape(np.shape(x))

    def ne_slope(self, x, y):
        s = (x - 30.0) * 0.57 + (y - 25.0) * 0.82
        region = smoothstep(24, 40, x) * smoothstep(14, 32, y)
        plaza = smoothstep(44, 54, np.hypot(x, y))
        z = 8.0 * smoothstep(20, 95, s) * region * plaza
        hill = 8.0 * (1 - smoothstep(11, 26, np.hypot(x - 94, y - 108)))
        return np.maximum(z, hill)

    def __call__(self, x, y, with_edge=True):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        z = self._raw(x, y)
        # soft undulation away from built features
        far = smoothstep(46, 60, np.hypot(x, y)) * (1 - smoothstep(-120, -110, y) * 0)  # noqa
        und = 0.35 * np.sin(x * 0.11 + 1.3) * np.cos(y * 0.09 - 0.4) + 0.18 * np.sin(x * 0.23 - y * 0.19 + 2.0)
        mask = far.copy()
        for (cx, cy), (w, d), level in self.pads:
            r = math.hypot(w, d) * 0.5 + 4
            m = smoothstep(r, r + 8, np.hypot(x - cx, y - cy))
            mask = mask * m
            inside = 1 - smoothstep(r - 1, r + 6, np.hypot(x - cx, y - cy))
            z = z * (1 - inside) + level * inside
        for pool in self.pools:
            cx, cy = pool['center']
            w, d = pool['size']
            # distance to the pool rectangle (0 inside)
            qx = np.maximum(np.abs(x - cx) - w * 0.5, 0.0)
            qy = np.maximum(np.abs(y - cy) - d * 0.5, 0.0)
            dist = np.hypot(qx, qy)
            flat = 1 - smoothstep(2.5, 9.0, dist)
            z = z * (1 - flat) + pool['level'] * flat
            mask = mask * smoothstep(4, 14, dist)
        canal = smoothstep(9, 16, np.abs(x)) + (y > -40)
        mask = mask * np.clip(canal, 0, 1)
        z = z + und * mask
        if with_edge:
            d = self.edge_distance(x, y)
            z = z - 0.45 * (1 - smoothstep(0.0, 3.0, d))
        return z


# ---------------------------------------------------------------------------
# Region tests used for cut-outs
# ---------------------------------------------------------------------------
def point_in_poly(x, y, poly):
    """Vectorised even-odd test (poly: list of (x, y))."""
    x = np.asarray(x)
    y = np.asarray(y)
    inside = np.zeros(x.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1)
        inside ^= cond
    return inside


def chamfer_poly(points, c=2.0):
    """Cut every corner of a polygon by c metres for softer masonry corners."""
    out = []
    n = len(points)
    for i in range(n):
        p = Vector((*points[i], 0))
        a = Vector((*points[i - 1], 0))
        b = Vector((*points[(i + 1) % n], 0))
        da = (a - p)
        db = (b - p)
        ca = min(c, da.length * 0.45)
        cb = min(c, db.length * 0.45)
        out.append(tuple((p + da.normalized() * ca).xy))
        out.append(tuple((p + db.normalized() * cb).xy))
    return out


def offset_poly(points, d):
    """Offset a CCW polygon outward by d (negative = inward), mitred."""
    n = len(points)
    out = []
    for i in range(n):
        p = np.array(points[i])
        a = np.array(points[i - 1])
        b = np.array(points[(i + 1) % n])
        e1 = p - a
        e2 = b - p
        n1 = np.array([e1[1], -e1[0]]) / (np.linalg.norm(e1) + 1e-9)
        n2 = np.array([e2[1], -e2[0]]) / (np.linalg.norm(e2) + 1e-9)
        m = n1 + n2
        m = m / (np.linalg.norm(m) + 1e-9)
        cos = max(0.35, float(np.dot(m, n1)))
        out.append(tuple(p + m * d / cos))
    return out


def circle_poly(cx, cy, r, n=48):
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(0, math.tau, n, endpoint=False)]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
class TerrainBuilder:
    NU, NV = 96, 116

    def __init__(self, layout: dict, col):
        self.L = layout
        self.col = col
        self.objects: list = []
        self.hooks: list = []
        self.island = Island(layout)
        self.outline = self.island.outline_loop(self.NU, self.NV)
        self.h = Heights(layout, self.outline)
        self.rng = random.Random(5150)
        lv = layout['levels']
        self.castle_z = lv['castle_terrace']
        self.wizard_z = lv['wizard_terrace']
        self.canal_half = layout['water']['canal']['width'] * 0.5
        self.castle_poly = chamfer_poly([(-52, 72), (52, 72), (52, 106), (80, 106), (80, 125), (-80, 125),
                                         (-80, 106), (-52, 106)], 2.5)
        wz = next(l for l in layout['landmarks'] if l['id'] == 'wizard_tower')
        self.wizard_center = wz['center']
        self.wizard_poly = circle_poly(*wz['center'], 22.0, 40)

    # -- helpers ---------------------------------------------------------------
    def add(self, obj):
        self.objects.append(obj)
        return obj

    def hook(self, obj):
        self.hooks.append(obj)
        return obj

    def empty(self, name, loc):
        e = bpy.data.objects.new(name, None)
        e.location = loc
        e.empty_display_size = 1.0
        self.col.objects.link(e)
        return self.hook(e)

    # -- ground ----------------------------------------------------------------
    def build_ground(self):
        P = self.island.coons_grid(self.NU, self.NV)
        nv1, nu1, _ = P.shape
        X, Y = P[..., 0], P[..., 1]
        Z = self.h(X, Y)
        self.grid = (X, Y, Z)
        canal_rect = lambda x, y: (np.abs(x) < self.canal_half + 0.4) & (y < -44.5)
        cut_poly_castle = offset_poly(self.castle_poly, -1.2)
        cut_poly_wizard = circle_poly(*self.wizard_center, 20.8, 40)

        def cut(x, y):
            c = np.hypot(x, y) < 41.2
            c |= canal_rect(x, y)
            c |= point_in_poly(x, y, cut_poly_castle)
            c |= point_in_poly(x, y, cut_poly_wizard)
            for pool in self.h.pools:
                cx, cy = pool['center']
                w, d = pool['size']
                c |= (np.abs(x - cx) < w * 0.5 - 0.6) & (np.abs(y - cy) < d * 0.5 - 0.6)
                if pool['id'].startswith('gate_pool'):
                    c |= (np.abs(x - cx) < 3.4) & (y < cy) & (y > self.island.y0 - 10)
            return c

        inside = cut(X, Y)
        verts = []
        index = -np.ones((nv1, nu1), dtype=int)
        faces = []
        for j in range(nv1 - 1):
            for i in range(nu1 - 1):
                if inside[j, i] and inside[j, i + 1] and inside[j + 1, i] and inside[j + 1, i + 1]:
                    continue
                quad = [(j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)]
                ids = []
                for (a, b) in quad:
                    if index[a, b] < 0:
                        index[a, b] = len(verts)
                        verts.append((X[a, b], Y[a, b], Z[a, b]))
                    ids.append(index[a, b])
                faces.append(ids)
        obj = ck.new_object('terrain / grass ground', verts, faces, 'grass_ground', self.col)
        ck.shade_smooth(obj, 60)
        ck.uv_box(obj)
        self._ground_colors(obj)
        self.ground = self.add(obj)
        return obj

    def _ground_colors(self, obj):
        """Painterly large-scale value variation plus darker soil near edges."""
        mesh = obj.data
        attr = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        mesh.color_attributes.active_color = attr
        co = np.array([v.co[:] for v in mesh.vertices])
        x, y = co[:, 0], co[:, 1]
        var = (0.93 + 0.07 * np.sin(x * 0.045 + 0.4) * np.cos(y * 0.052 - 1.1)
               + 0.04 * np.sin(x * 0.13 + y * 0.11))
        d = self.h.edge_distance(x, y)
        var *= 0.80 + 0.20 * smoothstep(0, 4, d)
        warm = 1.0 + 0.05 * np.sin(x * 0.03 - y * 0.04)
        cols = np.stack([var * warm, var, var * (2 - warm)], axis=1).clip(0, 1)
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                vi = mesh.loops[li].vertex_index
                attr.data[li].color = (*cols[vi], 1.0)

    # -- cliff underside -----------------------------------------------------------
    def build_cliffs(self):
        ol = self.outline
        n = len(ol)
        cx, cy = self.island.cx, self.island.cy
        # outward normals of the loop
        nrm = np.zeros_like(ol)
        for i in range(n):
            t = ol[(i + 1) % n] - ol[i - 1]
            nrm[i] = np.array([t[1], -t[0]]) / (np.linalg.norm(t) + 1e-9)
        seg = np.linalg.norm(np.roll(ol, -1, axis=0) - ol, axis=1)
        s = np.concatenate([[0], np.cumsum(seg)[:-1]])
        z_top = self.h(ol[:, 0], ol[:, 1])
        depth = self.island.depth
        # (inset metres, z) profile: grass lip, soil band, cliff wall, taper
        prof = [(-0.9, None), (-0.5, -1.2), (0.3, -2.6), (0.9, -5.0), (1.8, -9.0), (2.6, -13.5), (4.0, -19.0),
                (6.5, -25.5), (10.5, -33.0), (16.0, -41.0), (23.0, -50.0), (32.0, -59.0), (43.0, -67.0),
                (56.0, -74.0), (70.0, -depth - 4)]
        rings = []
        for k, (inset, z) in enumerate(prof):
            ring = []
            for i in range(n):
                p = ol[i]
                if z is None:
                    zz = z_top[i] - 0.15
                else:
                    zz = z
                # columns + strata ledges + big lobes, fade the noise at the lip
                w = min(1.0, k / 3.0)
                lobes = 2.6 * math.sin(s[i] * 0.021 + 0.8) + 1.7 * math.sin(s[i] * 0.047 + 2.3)
                cols = 0.55 * math.sin(s[i] * 0.61 + zz * 0.05) + 0.35 * math.sin(s[i] * 1.37 + 1.1)
                ledge = 0.9 if (math.fmod(-zz + 0.7 * math.sin(s[i] * 0.05), 6.5) < 1.3) else 0.0
                noise = w * (lobes * min(1.0, k / 6.0) + cols + ledge)
                inset_eff = inset - noise
                if inset > 30:
                    # taper towards the centre of mass instead of the local normal
                    dirc = np.array([cx, cy]) - p
                    dirc /= np.linalg.norm(dirc) + 1e-9
                    q = p + dirc * (inset_eff * 0.8) - nrm[i] * inset_eff * 0.2
                else:
                    q = p - nrm[i] * inset_eff
                ring.append((q[0], q[1], zz))
            rings.append(ring)
        # split into material bands
        bands = [('terrain / cliff grass lip', 'grass_ground', 0, 1), ('terrain / cliff soil band', 'dirt_path', 1, 3),
                 ('terrain / cliff rock', 'cliff_rock', 3, len(rings) - 1)]
        for name, mat, r0, r1 in bands:
            verts, faces = [], []
            for k in range(r0, r1 + 1):
                verts.extend(rings[k])
            rows = r1 - r0 + 1
            for k in range(rows - 1):
                for i in range(n):
                    a = k * n + i
                    b = k * n + (i + 1) % n
                    faces.append((a, b, b + n, a + n))
            obj = ck.new_object(name, verts, faces, mat, self.col)
            ck.shade_smooth(obj, 50)
            self._uv_cliff(obj, s, n, rows)
            self.add(obj)
        # bottom cap + stalactite spurs
        last = rings[-1]
        cxb = sum(p[0] for p in last) / n
        cyb = sum(p[1] for p in last) / n
        verts = list(last) + [(cxb, cyb, -depth - 16)]
        faces = [(i, n, (i + 1) % n) for i in range(n)]
        cap = ck.new_object('terrain / cliff underside cap', verts, faces, 'cliff_rock', self.col)
        ck.shade_smooth(cap, 50)
        ck.uv_box(cap)
        self.add(cap)
        rng = random.Random(77)
        for k in range(14):
            a = rng.uniform(0, math.tau)
            rr = rng.uniform(0.15, 0.8)
            px = cxb + math.cos(a) * rr * 40
            py = cyb + math.sin(a) * rr * 34
            length = rng.uniform(9, 26)
            radius = rng.uniform(2.5, 6.0)
            top = -depth - 2 + rr * 20
            prof = [(radius, 0), (radius * 0.8, -length * 0.3), (radius * 0.45, -length * 0.7), (0.0, -length)]
            spur = ck.lathe('terrain / stalactite', [(r, z) for r, z in reversed(prof)], 9, 'cliff_rock', self.col,
                            center=(px, py, top), cap_top=True, cap_bottom=False)
            spur.rotation_euler = (rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.uniform(0, 6))
            ck.apply_transform(spur)
            ck.shade_smooth(spur, 50)
            ck.uv_box(spur)
            self.add(spur)
        self.cliff_rings = rings

    def _uv_cliff(self, obj, s, n, rows):
        mesh = obj.data
        layer = mesh.uv_layers.new(name='UVMap')
        tile = float(mesh.materials[0].get('city_tile_m', 9.0))
        total = s[-1] + np.linalg.norm(self.outline[0] - self.outline[-1])
        reps = max(1, round(total / tile))
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                vi = mesh.loops[li].vertex_index
                i = vi % n
                co = mesh.vertices[vi].co
                u = s[i] / total * reps
                if i == 0 and any(mesh.loops[l].vertex_index % n == n - 1 for l in poly.loop_indices):
                    u = reps
                layer.data[li].uv = (u, co.z / tile)

    # -- terraces ---------------------------------------------------------------
    def terrace(self, name, poly, z_top, openings=(), wall_mat='stone_wall_warm', top_mat='grass_ground',
                buttress_every=9.0):
        poly = list(poly)
        # top face via scanfill
        bm = bmesh.new()
        vs = [bm.verts.new((x, y, z_top)) for x, y in poly]
        edges = [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2, use_grid_fill=True)
        top = ck.object_from_bmesh(f'{name} / top', bm, top_mat, self.col)
        for p in top.data.polygons:
            if p.normal.z < 0:
                p.flip()
        ck.uv_box(top)
        ck.ensure_white_vertex_colors(top)
        self.add(top)
        # walls, coping and buttresses, skipping openings (x0, x1, y0, y1 boxes)
        wall_boxes = []
        coping = []
        n = len(poly)
        for i in range(n):
            a = Vector((*poly[i], 0))
            b = Vector((*poly[(i + 1) % n], 0))
            length = (b - a).length
            if length < 0.05:
                continue
            steps = max(1, int(length / 3.0))
            for k in range(steps):
                p0 = a + (b - a) * (k / steps)
                p1 = a + (b - a) * ((k + 1) / steps)
                mid = (p0 + p1) * 0.5
                if any(o[0] <= mid.x <= o[1] and o[2] <= mid.y <= o[3] for o in openings):
                    continue
                wall_boxes.append((p0, p1))
        verts, faces = [], []
        cverts, cfaces = [], []
        bverts, bfaces = [], []
        zb = -0.8
        for p0, p1 in wall_boxes:
            d = (p1 - p0).normalized()
            nrm = Vector((d.y, -d.x, 0))  # outward for CCW polygons
            base = len(verts)
            q0, q1 = p0 + nrm * 0.02, p1 + nrm * 0.02
            verts += [(q0.x, q0.y, zb), (q1.x, q1.y, zb), (q1.x, q1.y, z_top - 0.05), (q0.x, q0.y, z_top - 0.05)]
            faces.append((base, base + 1, base + 2, base + 3))
            # coping stone (0.45 thick, overhanging 0.18)
            o = nrm * 0.18
            ii = -nrm * 0.62
            cb = len(cverts)
            c0 = [p0 + o, p1 + o, p1 + ii, p0 + ii]
            cverts += [(c.x, c.y, z_top - 0.08) for c in c0] + [(c.x, c.y, z_top + 0.42) for c in c0]
            cfaces += [(cb + 0, cb + 1, cb + 5, cb + 4), (cb + 1, cb + 2, cb + 6, cb + 5), (cb + 2, cb + 3, cb + 7, cb + 6),
                       (cb + 3, cb + 0, cb + 4, cb + 7), (cb + 4, cb + 5, cb + 6, cb + 7), (cb + 3, cb + 2, cb + 1, cb + 0)]
        if verts:
            wall = ck.new_object(f'{name} / retaining wall', verts, faces, wall_mat, self.col)
            ck.uv_box(wall)
            ck.vertex_paint(wall, ground_z=0.0, ground_dark=0.6, ground_fade=2.5, cavity=0.0, edge=0.0)
            self.add(wall)
            cop = ck.new_object(f'{name} / coping', cverts, cfaces, 'stone_trim_carved', self.col)
            ck.bevel(cop, 0.04, 2, 40)
            ck.uv_box(cop)
            ck.vertex_paint(cop, cavity=0.3, edge=0.25)
            self.add(cop)
        # buttresses / pilasters every few metres for relief
        acc = 0.0
        for p0, p1 in wall_boxes:
            seglen = (p1 - p0).length
            d = (p1 - p0).normalized()
            nrm = Vector((d.y, -d.x, 0))
            acc += seglen
            if acc >= buttress_every:
                acc = 0.0
                c = p1 + nrm * 0.45
                bb = len(bverts)
                w, dep, h0, h1 = 0.75, 0.9, zb, z_top - 0.1
                corners = [c - d * w + nrm * dep * 0.5, c + d * w + nrm * dep * 0.5, c + d * w - nrm * dep * 0.5,
                           c - d * w - nrm * dep * 0.5]
                bverts += [(q.x, q.y, h0) for q in corners] + [(q.x, q.y, h1 - 0.9) for q in corners]
                slope = [corners[0] - nrm * 0.35, corners[1] - nrm * 0.35]
                bverts += [(slope[0].x, slope[0].y, h1), (slope[1].x, slope[1].y, h1)]
                bfaces += [(bb, bb + 1, bb + 5, bb + 4), (bb + 1, bb + 2, bb + 6, bb + 5), (bb + 3, bb, bb + 4, bb + 7),
                           (bb + 4, bb + 5, bb + 9, bb + 8), (bb + 5, bb + 6, bb + 9), (bb + 4, bb + 8, bb + 7),
                           (bb + 8, bb + 9, bb + 6, bb + 7)]
        if bverts:
            but = ck.new_object(f'{name} / buttresses', bverts, bfaces, 'stone_wall_warm', self.col)
            ck.bevel(but, 0.05, 2, 40)
            ck.uv_box(but)
            ck.vertex_paint(but, ground_z=0.0, ground_dark=0.6, ground_fade=2.0, cavity=0.3, edge=0.25)
            self.add(but)
        return top

    def build_terraces(self):
        self.terrace('terrain / castle terrace', self.castle_poly, self.castle_z,
                     openings=[(-9.5, 9.5, 60, 74)], buttress_every=8.0)
        # wizard terrace with a stair opening towards the NW avenue
        self.terrace('terrain / wizard terrace', self.wizard_poly, self.wizard_z,
                     openings=[(-60.5, -52.0, 64.0, 73.0)], buttress_every=7.0)
        self.stairs('terrain / wizard stairs', start=(-51.0, 61.2), end=(-57.6, 70.5), width=6.0,
                    z0=float(self.h(np.array([-51.0]), np.array([61.2]))[0]), z1=self.wizard_z)

    def stairs(self, name, start, end, width, z0, z1, mat='paver_surface'):
        a = Vector((*start, 0))
        b = Vector((*end, 0))
        d = (b - a)
        length = d.length
        d.normalize()
        side = Vector((-d.y, d.x, 0))
        rise = z1 - z0
        steps = max(2, int(round(abs(rise) / 0.28)))
        tread = length / steps
        verts, faces = [], []
        for k in range(steps):
            p0 = a + d * (tread * k)
            p1 = a + d * (tread * (k + 1) + 0.04)
            zt = z0 + rise * (k + 1) / steps
            zbot = z0 - 0.6 if k == 0 else z0 + rise * (k - 1) / steps
            corners = [p0 - side * width / 2, p0 + side * width / 2, p1 + side * width / 2, p1 - side * width / 2]
            base = len(verts)
            verts += [(c.x, c.y, zbot) for c in corners] + [(c.x, c.y, zt) for c in corners]
            faces += [(base + 4, base + 5, base + 6, base + 7), (base + 0, base + 1, base + 5, base + 4),
                      (base + 1, base + 2, base + 6, base + 5), (base + 3, base + 0, base + 4, base + 7)]
        st = ck.new_object(name, verts, faces, mat, self.col)
        ck.bevel(st, 0.035, 2, 40)
        ck.uv_box(st)
        ck.vertex_paint(st, cavity=0.35, edge=0.3)
        self.add(st)
        # cheek walls
        for sgn in (-1, 1):
            off = side * (width / 2 + 0.35) * sgn
            q0, q1 = a + off, b + off
            verts = [(q0.x - d.x * 0.3, q0.y - d.y * 0.3, z0 - 0.6), (q1.x, q1.y, z1 - 0.6),
                     (q1.x, q1.y, z1 + 0.9), (q0.x - d.x * 0.3, q0.y - d.y * 0.3, z0 + 0.9)]
            t = side * 0.35
            verts += [(v[0] + t.x, v[1] + t.y, v[2]) for v in verts]
            verts = [(v[0] - t.x * 0.5, v[1] - t.y * 0.5, v[2]) for v in verts]
            faces = [(0, 1, 2, 3), (5, 4, 7, 6), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]
            ch = ck.new_object(f'{name} cheek', verts, faces, 'stone_trim_carved', self.col)
            ck.bevel(ch, 0.04, 2, 40)
            ck.uv_box(ch)
            ck.vertex_paint(ch, cavity=0.3, edge=0.25, ground_z=z0, ground_fade=1.5)
            self.add(ch)

    # -- water ------------------------------------------------------------------
    def build_canal(self):
        hw = self.canal_half
        y_start, y_end = -45.0, self.island.y0 - 1.5
        bed_z, water_z = -2.4, self.L['levels']['canal_water_surface']
        L = y_start - y_end
        # side walls (inner faces) + coping
        for sgn in (-1, 1):
            x_in = sgn * hw
            x_out = sgn * (hw + 0.9)
            verts = [(x_in, y_end, bed_z), (x_in, y_start, bed_z), (x_in, y_start, 0.12), (x_in, y_end, 0.12)]
            faces = [(0, 1, 2, 3) if sgn < 0 else (3, 2, 1, 0)]
            wall = ck.new_object(f'terrain / canal wall {sgn:+d}', verts, faces, 'stone_foundation', self.col)
            bm = bmesh.new()
            bm.from_mesh(wall.data)
            bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.y - e.verts[1].co.y) > 1],
                                      cuts=40)
            bm.to_mesh(wall.data)
            bm.free()
            ck.uv_box(wall)
            ck.vertex_paint(wall, ground_z=water_z - 0.2, ground_dark=0.55, ground_fade=1.6, cavity=0, edge=0)
            self.add(wall)
            # segmented coping stones with slight irregularity
            cop_boxes = []
            y = y_end
            while y < y_start:
                seg = self.rng.uniform(1.1, 1.8)
                y1 = min(y_start, y + seg)
                cop_boxes.append(((x_in + x_out) / 2 + sgn * 0.05, (y + y1) / 2, 0.24 + self.rng.uniform(-0.02, 0.02),
                                  abs(x_out - x_in) + 0.25, (y1 - y) - 0.05, 0.3))
                y = y1
            objs = []
            for (bx, by, bz, w, d, h) in cop_boxes:
                objs.append(ck.box('canal coping', (bx, by, bz), (w, d, h), 'stone_trim_carved', self.col))
            cop = ck.join(objs, f'terrain / canal coping {sgn:+d}')
            ck.apply_transform(cop)
            ck.bevel(cop, 0.035, 2, 40)
            ck.uv_box(cop)
            ck.vertex_paint(cop, cavity=0.3, edge=0.3)
            self.add(cop)
        # rounded head basin at the plaza end
        head = []
        for k in range(17):
            a = math.pi + k * math.pi / 16
            head.append((hw * math.cos(a) * 1.0, y_start + hw * math.sin(-a) * -1.0))
        bed = ck.new_object('terrain / canal bed',
                            [(-hw, y_end, bed_z), (hw, y_end, bed_z), (hw, y_start, bed_z), (-hw, y_start, bed_z)],
                            [(0, 1, 2, 3)], 'stone_tiles_dark', self.col)
        ck.uv_box(bed)
        ck.ensure_white_vertex_colors(bed)
        self.add(bed)
        endwall = ck.box('terrain / canal head wall', (0, y_start + 0.45, (bed_z + 0.5) / 2), (2 * hw + 1.8, 0.9, 0.5 - bed_z + 0.1),
                         'stone_foundation', self.col)
        ck.apply_transform(endwall)
        ck.bevel(endwall, 0.04, 2)
        ck.uv_box(endwall)
        ck.vertex_paint(endwall, cavity=0.3, edge=0.2)
        self.add(endwall)
        water = ck.new_object('fx_water_canal',
                              [(-hw, y_end - 0.5, water_z), (hw, y_end - 0.5, water_z), (hw, y_start, water_z), (-hw, y_start, water_z)],
                              [(0, 1, 2, 3)], 'water', self.col)
        ck.uv_box(water)
        ck.ensure_white_vertex_colors(water)
        self.hook(water)
        # spout cascade from the plaza basin into the canal
        self.waterfall('fx_waterfall_canal_head', (0, y_start + 0.1, 0.35), (0, -1, 0), width=3.0, drop=1.3, outward=0.6,
                       rows=6)
        self.empty('emit_spray_canal_head', (0, y_start - 1.2, water_z + 0.1))

    def waterfall(self, name, lip, direction, width, drop, outward=3.0, rows=24, cols=8, flare=0.35):
        """Curved falling sheet; UV v runs down the fall so the client can scroll it."""
        lx, ly, lz = lip
        dx, dy, _ = direction
        side = Vector((-dy, dx, 0))
        verts, faces, uvs = [], [], []
        for r in range(rows + 1):
            t = r / rows
            fall = drop * (t ** 1.6)
            out = outward * math.sqrt(t) + 0.4 * t
            w = width * (1 + flare * t)
            for c in range(cols + 1):
                u = c / cols - 0.5
                ripple = 0.25 * math.sin(u * 9.0 + t * 7) * t
                px = lx + dx * (out + ripple) + side.x * u * w
                py = ly + dy * (out + ripple) + side.y * u * w
                verts.append((px, py, lz - fall))
                uvs.append((c / cols * width / 4.0, -fall / 4.0))
        for r in range(rows):
            for c in range(cols):
                a = r * (cols + 1) + c
                faces.append((a, a + 1, a + cols + 2, a + cols + 1))
        obj = ck.new_object(name, verts, faces, 'water_foam', self.col)
        layer = obj.data.uv_layers.new(name='UVMap')
        for poly in obj.data.polygons:
            for li in poly.loop_indices:
                layer.data[li].uv = uvs[obj.data.loops[li].vertex_index]
        ck.shade_smooth(obj, 80)
        ck.ensure_white_vertex_colors(obj)
        self.hook(obj)
        bottom = (lx + dx * (outward + 0.4), ly + dy * (outward + 0.4), lz - drop)
        if drop > 8:
            self.empty(f'emit_mist_{name[len("fx_waterfall_"):]}', bottom)
        return obj

    def build_pools_and_falls(self):
        y_edge = self.island.y0
        for pool in self.L['water']['pools']:
            pid = pool['id']
            cx, cy = pool['center']
            w, d = pool['size']
            raised = pid.startswith(('nw_castle', 'ne_castle'))
            if raised:
                level = self.castle_z
                water_z = level + 0.38
            else:
                level = self.h.pool_level(pid)
                water_z = level - 0.45
            self._pool(pid, cx, cy, w, d, level, water_z, raised=raised)
            if pid.startswith('gate_pool'):
                # channel to the cliff lip and the big waterfall
                ch_w = 6.8
                y0 = cy - d / 2
                self._channel(pid, cx, y0, y_edge - 1.0, ch_w, level, water_z)
                fall = next(f for f in self.L['water']['waterfalls'] if f['lip'][0] * cx > 0 and abs(f['lip'][0] - cx) < 5)
                self.waterfall(f'fx_waterfall_{fall["id"]}', (cx, y_edge - 0.8, water_z - 0.1), (0, -1, 0),
                               width=ch_w, drop=fall['drop'], outward=5.0, rows=28, cols=10, flare=0.6)
        centre = next(f for f in self.L['water']['waterfalls'] if f['id'] == 'gate_fall_centre')
        self.waterfall('fx_waterfall_gate_fall_centre', (0, self.island.y0 - 1.6, self.L['levels']['canal_water_surface'] - 0.05),
                       (0, -1, 0), width=2 * self.canal_half - 0.4, drop=centre['drop'], outward=6.0, rows=28, cols=10,
                       flare=0.5)
        # NE garden cascades between the stepped pools
        ne = [p for p in self.L['water']['pools'] if p['id'].startswith('ne_garden')]
        ne.sort(key=lambda p: p['center'][1])
        for lo, hi in zip(ne, ne[1:]):
            zl = self.h.pool_level(lo['id']) - 0.45
            zh = self.h.pool_level(hi['id']) - 0.45
            lip = (hi['center'][0] - 3, hi['center'][1] - hi['size'][1] / 2 - 0.2, zh)
            self.waterfall(f'fx_waterfall_{hi["id"]}_cascade', lip, (0, -1, 0), width=4.0, drop=max(0.6, zh - zl),
                           outward=1.0, rows=10, cols=6, flare=0.2)
            # stream bed between the two pools
            y_top = hi['center'][1] - hi['size'][1] / 2 - 0.2
            y_bot = lo['center'][1] + lo['size'][1] / 2
            if y_top - y_bot > 1.0:
                x = hi['center'][0] - 3
                zz_top = zh
                zz_bot = zl
                s = ck.new_object(f'fx_water_stream_{hi["id"]}',
                                  [(x - 2, y_bot, zz_bot + 0.02), (x + 2, y_bot, zz_bot + 0.02),
                                   (x + 2, y_top - 0.8, zz_bot + 0.05), (x - 2, y_top - 0.8, zz_bot + 0.05)],
                                  [(0, 1, 2, 3)], 'water', self.col)
                ck.uv_box(s)
                ck.ensure_white_vertex_colors(s)
                self.hook(s)

    def _pool(self, pid, cx, cy, w, d, level, water_z, raised=False):
        # rounded-rectangle rim of carved coping stones, basin walls and water
        r = min(w, d) * 0.28
        pts = []
        for (qx, qy, a0) in [(cx + w / 2 - r, cy - d / 2 + r, -90), (cx + w / 2 - r, cy + d / 2 - r, 0),
                             (cx - w / 2 + r, cy + d / 2 - r, 90), (cx - w / 2 + r, cy - d / 2 + r, 180)]:
            for k in range(7):
                a = math.radians(a0 + k * 15)
                pts.append((qx + r * math.cos(a), qy + r * math.sin(a)))
        inner = offset_poly(pts, -0.1)
        outer = offset_poly(pts, 1.0)
        n = len(pts)
        top = level + (0.62 if raised else 0.32)
        verts = [(x, y, top) for x, y in outer] + [(x, y, top) for x, y in inner]
        verts += [(x, y, level - 0.3) for x, y in outer] + [(x, y, water_z - 1.2) for x, y in inner]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.append((i, j, n + j, n + i))                  # top
            faces.append((2 * n + j, 2 * n + i, i, j))          # outer side
            faces.append((n + i, n + j, 3 * n + j, 3 * n + i))  # inner side down to bed
        rim = ck.new_object(f'terrain / pool rim {pid}', verts, faces, 'stone_trim_carved', self.col)
        for p in rim.data.polygons:
            c = p.center
            if p.normal.z < -0.2:
                p.flip()
        ck.bevel(rim, 0.05, 2, 35)
        ck.uv_box(rim)
        ck.vertex_paint(rim, cavity=0.35, edge=0.3, ground_z=water_z, ground_fade=0.8, ground_dark=0.6)
        self.add(rim)
        bm = bmesh.new()
        vs = [bm.verts.new((x, y, water_z - 1.2)) for x, y in inner]
        bm.faces.new(vs)
        bed = ck.object_from_bmesh(f'terrain / pool bed {pid}', bm, 'stone_tiles_dark', self.col)
        ck.uv_box(bed)
        ck.ensure_white_vertex_colors(bed)
        self.add(bed)
        bm = bmesh.new()
        vs = [bm.verts.new((x, y, water_z)) for x, y in inner]
        bm.faces.new(vs)
        wat = ck.object_from_bmesh(f'fx_water_{pid}', bm, 'water', self.col)
        ck.uv_box(wat)
        ck.ensure_white_vertex_colors(wat)
        self.hook(wat)
        # the ground around a pool must meet the rim: small grass skirt
        return rim

    def _channel(self, pid, cx, y0, y1, width, level, water_z):
        hw = width / 2
        for sgn in (-1, 1):
            xs = cx + sgn * (hw + 0.45)
            boxes = []
            y = y1
            while y < y0:
                seg = self.rng.uniform(1.2, 1.9)
                yy = min(y0, y + seg)
                boxes.append(ck.box('channel coping', (xs, (y + yy) / 2, level + 0.12), (0.9, yy - y - 0.05, 0.6),
                                    'stone_trim_carved', self.col))
                y = yy
            cop = ck.join(boxes, f'terrain / channel coping {pid} {sgn:+d}')
            ck.apply_transform(cop)
            ck.bevel(cop, 0.035, 2)
            ck.uv_box(cop)
            ck.vertex_paint(cop, cavity=0.3, edge=0.3)
            self.add(cop)
            wall = ck.new_object(f'terrain / channel wall {pid} {sgn:+d}',
                                 [(cx + sgn * hw, y1, water_z - 1.0), (cx + sgn * hw, y0, water_z - 1.0),
                                  (cx + sgn * hw, y0, level + 0.1), (cx + sgn * hw, y1, level + 0.1)],
                                 [(0, 1, 2, 3) if sgn < 0 else (3, 2, 1, 0)], 'stone_foundation', self.col)
            ck.uv_box(wall)
            ck.vertex_paint(wall, ground_z=water_z - 0.2, ground_dark=0.55, ground_fade=1.2, cavity=0, edge=0)
            self.add(wall)
        bed = ck.new_object(f'terrain / channel bed {pid}',
                            [(cx - hw, y1, water_z - 1.0), (cx + hw, y1, water_z - 1.0), (cx + hw, y0, water_z - 1.0),
                             (cx - hw, y0, water_z - 1.0)], [(0, 1, 2, 3)], 'stone_tiles_dark', self.col)
        ck.uv_box(bed)
        ck.ensure_white_vertex_colors(bed)
        self.add(bed)
        wat = ck.new_object(f'fx_water_channel_{pid}',
                            [(cx - hw, y1 - 0.3, water_z), (cx + hw, y1 - 0.3, water_z), (cx + hw, y0, water_z),
                             (cx - hw, y0, water_z)], [(0, 1, 2, 3)], 'water', self.col)
        ck.uv_box(wat)
        ck.ensure_white_vertex_colors(wat)
        self.hook(wat)

    # -- paths --------------------------------------------------------------------
    def strip(self, name, points, width, mat, lift=0.06, curb=True, start_r=None):
        pts = [Vector((p[0], p[1], 0)) for p in points]
        # densify so the strip follows the terrain
        dense = []
        for a, b in zip(pts, pts[1:]):
            n = max(1, int((b - a).length / 2.0))
            for k in range(n):
                dense.append(a + (b - a) * (k / n))
        dense.append(pts[-1])
        if start_r is not None:
            dense = [p for p in dense if p.length >= start_r - 0.5] or dense
        verts, faces = [], []
        left, right = [], []
        for i, p in enumerate(dense):
            if i == 0:
                t = dense[1] - dense[0]
            elif i == len(dense) - 1:
                t = dense[-1] - dense[-2]
            else:
                t = dense[i + 1] - dense[i - 1]
            t.normalize()
            s = Vector((-t.y, t.x, 0))
            left.append(p + s * width / 2)
            right.append(p - s * width / 2)
        xs = np.array([[q.x for q in left], [q.x for q in right]])
        ys = np.array([[q.y for q in left], [q.y for q in right]])
        zs = self.h(xs, ys) + lift
        m = len(dense)
        for i in range(m):
            verts.append((left[i].x, left[i].y, zs[0, i]))
            verts.append((right[i].x, right[i].y, zs[1, i]))
        for i in range(m - 1):
            a = 2 * i
            faces.append((a + 1, a + 3, a + 2, a))
        obj = ck.new_object(name, verts, faces, mat, self.col)
        for p in obj.data.polygons:
            if p.normal.z < 0:
                p.flip()
        ck.uv_box(obj)
        ck.ensure_white_vertex_colors(obj)
        self.add(obj)
        if curb:
            for side_pts, zrow, sgn in ((left, zs[0], 1), (right, zs[1], -1)):
                cv, cf = [], []
                for i in range(m):
                    q = side_pts[i]
                    t = (dense[min(i + 1, m - 1)] - dense[max(i - 1, 0)]).normalized()
                    s = Vector((-t.y, t.x, 0)) * sgn
                    inner = q - s * 0.05
                    outer = q + s * 0.32
                    z = float(zrow[i])
                    cv += [(inner.x, inner.y, z - 0.05), (inner.x, inner.y, z + 0.12), (outer.x, outer.y, z + 0.12),
                           (outer.x, outer.y, z - 0.12)]
                for i in range(m - 1):
                    a = 4 * i
                    b = a + 4
                    cf += [(a, b, b + 1, a + 1), (a + 1, b + 1, b + 2, a + 2), (a + 2, b + 2, b + 3, a + 3)]
                c = ck.new_object(f'{name} curb', cv, cf, 'stone_trim_carved', self.col)
                for p in c.data.polygons:
                    if p.normal.z < -0.1:
                        p.flip()
                ck.uv_box(c)
                ck.vertex_paint(c, cavity=0.2, edge=0.35)
                self.add(c)
        return obj

    def build_paths(self):
        L = self.L
        mats = {'north_stairs': None, 'south_canal': None, 'west_smithy': 'plaza_flagstone', 'east_market': 'plaza_flagstone'}
        for av in L['plaza']['avenues']:
            mat = mats.get(av['id'], 'cobble_path')
            if mat is None:
                continue
            tx, ty = av['to']
            d = math.hypot(tx, ty)
            self.strip(f'terrain / avenue {av["id"]}', [(tx / d * 40.5, ty / d * 40.5), (tx, ty)], av['width'], mat,
                       start_r=None)
        for p in L['paths']:
            if p['id'] == 'gate_avenue':
                continue
            self.strip(f'terrain / path {p["id"]}', p['points'], p['width'], 'cobble_path')
        # promenades either side of the canal
        for sgn in (-1, 1):
            x = sgn * (self.canal_half + 0.9 + 3.2)
            self.strip(f'terrain / canal promenade {sgn:+d}', [(x, -40.5), (x, self.island.y0 + 3.0)], 6.4,
                       'plaza_flagstone', curb=False)

    # -- plaza paving -------------------------------------------------------------
    def build_plaza(self):
        pl = self.L['plaza']
        R = pl['radius'] + 0.6
        inner = self.L['fountain']['plinth_radius'] + 0.2
        # mortar disc under the stones
        n = 128
        verts = [(0, 0, 0.0)] + [(R * math.cos(a), R * math.sin(a), 0.0) for a in np.linspace(0, math.tau, n, endpoint=False)]
        faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
        mortar = ck.new_object('terrain / plaza mortar bed', verts, faces, 'stone_tiles_dark', self.col)
        ck.uv_box(mortar)
        mortar.data.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        for d in mortar.data.color_attributes['Col'].data:
            d.color = (0.55, 0.52, 0.5, 1)
        self.add(mortar)
        accent_bands = {pl['planter_ring_radius'], pl['lamp_ring_radius'], pl['bench_ring_radius'] + 3.0}
        radii = [inner]
        r = inner
        rng = random.Random(4242)
        while r < R - 0.9:
            w = 1.05 + 0.45 * (r - inner) / (R - inner) + rng.uniform(-0.05, 0.05)
            r = min(R - 0.9, r + w)
            radii.append(r)
        radii.append(R)
        groups = {'paver_surface': ([], [], []), 'stone_accent_bluegrey': ([], [], []), 'stone_trim_carved': ([], [], [])}
        gap = 0.035
        for bi in range(len(radii) - 1):
            r0, r1 = radii[bi], radii[bi + 1]
            mid = (r0 + r1) / 2
            outer_curb = bi == len(radii) - 2
            accent = any(abs(mid - a) < (r1 - r0) * 0.75 for a in accent_bands)
            mat = 'stone_trim_carved' if outer_curb else ('stone_accent_bluegrey' if accent else 'paver_surface')
            stone_len = 1.9 if outer_curb else rng.uniform(1.35, 1.8)
            count = max(8, int(round(math.tau * mid / stone_len)))
            cuts = [k * math.tau / count + rng.uniform(-0.18, 0.18) * math.tau / count for k in range(count)]
            phase = rng.uniform(0, math.tau)
            verts, faces, info = groups[mat]
            for k in range(count):
                a0 = cuts[k] + phase
                a1 = (cuts[(k + 1) % count] + (math.tau if k == count - 1 else 0)) + phase
                self._paver(verts, faces, info, r0, r1, a0, a1, gap, rng, raised=0.16 if outer_curb else 0.0)
        for mat, (verts, faces, info) in groups.items():
            if not verts:
                continue
            obj = ck.new_object(f'terrain / plaza pavers {mat}', verts, faces, mat, self.col)
            self._paver_uv_and_color(obj, info, rng)
            self.add(obj)

    def _paver(self, verts, faces, info, r0, r1, a0, a1, gap, rng, raised=0.0):
        """One flagstone: bevelled top with a sloped rim down to the mortar."""
        da = gap / max(r0, 0.5)
        segs = max(1, int((a1 - a0) * r1 / 1.2))
        top_z = 0.085 + raised + rng.uniform(-0.012, 0.012)
        tilt = (rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01))
        bev = 0.06
        outer_ring, inner_ring = [], []
        for s in range(segs + 1):
            a = a0 + da + (a1 - a0 - 2 * da) * s / segs
            outer_ring.append((a, r1 - gap))
        for s in range(segs, -1, -1):
            a = a0 + da + (a1 - a0 - 2 * da) * s / segs
            inner_ring.append((a, r0 + gap))
        loop = outer_ring + inner_ring
        m = len(loop)
        base = len(verts)
        cx = sum(r * math.cos(a) for a, r in loop) / m
        cy = sum(r * math.sin(a) for a, r in loop) / m
        for a, r in loop:
            x, y = r * math.cos(a), r * math.sin(a)
            verts.append((x, y, 0.02))
        for a, r in loop:
            x, y = r * math.cos(a), r * math.sin(a)
            vx, vy = cx - x, cy - y
            ln = math.hypot(vx, vy) + 1e-9
            x2, y2 = x + vx / ln * bev, y + vy / ln * bev
            verts.append((x2, y2, top_z + tilt[0] * (x2 - cx) + tilt[1] * (y2 - cy)))
        for i in range(m):
            j = (i + 1) % m
            faces.append((base + i, base + j, base + m + j, base + m + i))
        faces.append(tuple(base + m + i for i in range(m)))
        info.append((base, m, (cx, cy), rng.random(), rng.randrange(4)))

    def _paver_uv_and_color(self, obj, info, rng):
        mesh = obj.data
        for p in mesh.polygons:
            if p.normal.z < 0:
                p.flip()
        layer = mesh.uv_layers.new(name='UVMap')
        col = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        mesh.color_attributes.active_color = col
        tile = float(mesh.materials[0].get('city_tile_m', 2.0))
        owner = {}
        for base, m, c, rnd, rot in info:
            for k in range(2 * m):
                owner[base + k] = (base, m, c, rnd, rot)
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                vi = mesh.loops[li].vertex_index
                base, m, (cx, cy), rnd, rot = owner[vi]
                co = mesh.vertices[vi].co
                lx, ly = co.x - cx, co.y - cy
                for _ in range(rot):
                    lx, ly = -ly, lx
                layer.data[li].uv = (lx / tile + rnd * 7.31, ly / tile + rnd * 3.17)
                is_top = (vi - base) >= m
                tone = 0.86 + 0.22 * rnd
                if is_top:
                    shade = tone * 1.04
                else:
                    shade = tone * (0.62 if co.z < 0.05 else 0.9)
                warm = 1.0 + (rnd - 0.5) * 0.08
                col.data[li].color = (min(1, shade * warm), min(1, shade), min(1, shade * (2 - warm)), 1.0)

    # -- everything ------------------------------------------------------------------
    def build(self):
        self.build_ground()
        self.build_cliffs()
        self.build_terraces()
        self.build_canal()
        self.build_pools_and_falls()
        self.build_paths()
        self.build_plaza()
        return self


def build_terrain(layout: dict, col):
    return TerrainBuilder(layout, col).build()
