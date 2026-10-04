"""Pure-Python geometry helpers for the Sunmeadow v2 blockout (no bpy, no numpy).

Coordinates
  Babylon world: +x east, +z north, +y up (layout JSON, colliders.json, instances.json).
  Blender world: x = -bx, y = -bz, z = by  (glTF export maps Blender (x, y, z) -> Babylon (-x, z, -y)).
  In plan view this is a 180 degree rotation, so polygon winding seen from above is preserved.
Yaw
  Babylon yaw a: 0 faces +Z, pi/2 faces +X (atan2(dx, dz)).  Blender rotation about +Z = -a.
Mesh builders emit Blender-space vertices with outward, counter-clockwise winding.
"""
from __future__ import annotations

import math
import random
from collections import deque

TAU = math.tau


# ----------------------------------------------------------------------------
# Coordinate conversion and small vector helpers
# ----------------------------------------------------------------------------

def bl(bx: float, bz: float, by: float = 0.0) -> tuple[float, float, float]:
    """Babylon (x, z, height) -> Blender (x, y, z)."""
    return (-bx, -bz, by)


def bab(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Blender (x, y, z) -> Babylon (x, y, z)."""
    return (-x, z, -y)


def yaw_to(dx: float, dz: float) -> float:
    """Babylon facing yaw for a direction in XZ, normalised to [0, 2pi)."""
    return math.atan2(dx, dz) % TAU


def r6(v: float) -> float:
    return round(float(v), 4)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, s):
    return (a[0] * s, a[1] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def norm(a):
    length = math.hypot(a[0], a[1])
    return (a[0] / length, a[1] / length) if length > 1e-12 else (0.0, 0.0)


def left_normal(d):
    """Left of a direction in Babylon XZ seen from above (x right, z up)."""
    return (-d[1], d[0])


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def stable_seed(text: str, base: int = 20261002) -> int:
    h = base
    for ch in text:
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return h


# ----------------------------------------------------------------------------
# Deterministic value noise
# ----------------------------------------------------------------------------

def _hash2(ix: int, iy: int, seed: int) -> float:
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def value_noise2(x: float, y: float, seed: int = 0) -> float:
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash2(ix, iy, seed), _hash2(ix + 1, iy, seed)
    c, d = _hash2(ix, iy + 1, seed), _hash2(ix + 1, iy + 1, seed)
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


def fbm2(x: float, y: float, seed: int = 0, octaves: int = 3, gain: float = 0.5) -> float:
    """Fractal value noise in [0, 1]."""
    amp, freq, total, normaliser = 1.0, 1.0, 0.0, 0.0
    for o in range(octaves):
        total += amp * value_noise2(x * freq, y * freq, seed + 101 * o)
        normaliser += amp
        amp *= gain
        freq *= 2.03
    return total / normaliser


def noise1(x: float, seed: int = 0, octaves: int = 2) -> float:
    return fbm2(x, 0.37, seed, octaves)


# ----------------------------------------------------------------------------
# Polylines (Babylon XZ)
# ----------------------------------------------------------------------------

def seg_closest(p, a, b):
    """Return (distance, t, foot) from point p to segment ab."""
    d = sub(b, a)
    l2 = dot(d, d)
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, dot(sub(p, a), d) / l2))
    foot = (a[0] + d[0] * t, a[1] + d[1] * t)
    return math.hypot(p[0] - foot[0], p[1] - foot[1]), t, foot


class Polyline:
    def __init__(self, pts):
        self.pts = [(float(x), float(z)) for x, z in pts]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.dist(a, b))

    @property
    def length(self) -> float:
        return self.cum[-1]

    def seg_index(self, s: float) -> int:
        for i in range(len(self.pts) - 1):
            if s <= self.cum[i + 1]:
                return i
        return len(self.pts) - 2

    def point_at(self, s: float):
        s = max(0.0, min(self.length, s))
        i = self.seg_index(s)
        seg = self.cum[i + 1] - self.cum[i]
        t = 0.0 if seg == 0 else (s - self.cum[i]) / seg
        a, b = self.pts[i], self.pts[i + 1]
        return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))

    def tangent_at(self, s: float):
        i = self.seg_index(max(0.0, min(self.length, s)))
        return norm(sub(self.pts[i + 1], self.pts[i]))

    def closest(self, p):
        """(distance, arc length s, side) with side > 0 when p is left of the direction."""
        best = (1e18, 0.0, 0.0)
        for i in range(len(self.pts) - 1):
            a, b = self.pts[i], self.pts[i + 1]
            dist, t, foot = seg_closest(p, a, b)
            if dist < best[0]:
                side = cross(sub(b, a), sub(p, a))
                best = (dist, self.cum[i] + t * (self.cum[i + 1] - self.cum[i]), side)
        return best

    def distance(self, p) -> float:
        return min(seg_closest(p, a, b)[0] for a, b in zip(self.pts, self.pts[1:]))

    def sample(self, step: float):
        n = max(1, int(math.ceil(self.length / step)))
        return [(self.point_at(self.length * k / n), self.length * k / n) for k in range(n + 1)]


def fillet_polyline(pts, radius: float, step: float = 1.0, arc_step: float = 0.5):
    """Densified polyline with circular fillets of `radius` at interior corners."""
    pts = [(float(x), float(z)) for x, z in pts]
    if len(pts) < 3:
        out = []
        line = Polyline(pts)
        n = max(1, int(math.ceil(line.length / step)))
        return [line.point_at(line.length * k / n) for k in range(n + 1)]
    corners = []  # (P1, arc points, P2) per interior vertex
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        u1, u2 = norm(sub(b, a)), norm(sub(c, b))
        theta = math.acos(max(-1.0, min(1.0, dot(u1, u2))))
        if theta < 1e-3:
            corners.append((b, [], b))
            continue
        t = radius * math.tan(theta / 2)
        t = min(t, 0.45 * math.dist(a, b), 0.45 * math.dist(b, c))
        r_eff = t / math.tan(theta / 2)
        p1, p2 = sub(b, mul(u1, t)), add(b, mul(u2, t))
        turn_left = cross(u1, u2) > 0
        n1 = left_normal(u1) if turn_left else mul(left_normal(u1), -1)
        centre = add(p1, mul(n1, r_eff))
        a0 = math.atan2(p1[1] - centre[1], p1[0] - centre[0])
        a1 = math.atan2(p2[1] - centre[1], p2[0] - centre[0])
        sweep = a1 - a0
        if turn_left and sweep < 0:
            sweep += TAU
        if not turn_left and sweep > 0:
            sweep -= TAU
        n = max(2, int(math.ceil(abs(sweep) * r_eff / arc_step)))
        arc = [(centre[0] + r_eff * math.cos(a0 + sweep * k / n), centre[1] + r_eff * math.sin(a0 + sweep * k / n))
               for k in range(1, n)]
        corners.append((p1, arc, p2))
    out = [pts[0]]

    def straight(p, q):
        n = max(1, int(math.ceil(math.dist(p, q) / step)))
        for k in range(1, n + 1):
            out.append((lerp(p[0], q[0], k / n), lerp(p[1], q[1], k / n)))

    cursor = pts[0]
    for p1, arc, p2 in corners:
        straight(cursor, p1)
        out.extend(arc)
        if p2 != p1:
            out.append(p2)
        cursor = p2
    straight(cursor, pts[-1])
    cleaned = [out[0]]
    for q in out[1:]:
        if math.dist(q, cleaned[-1]) > 1e-4:
            cleaned.append(q)
    return cleaned


def polyline_normals(pts):
    """Per-vertex unit tangents and left normals using averaged neighbouring segments."""
    tangents = []
    for i in range(len(pts)):
        if i == 0:
            d = sub(pts[1], pts[0])
        elif i == len(pts) - 1:
            d = sub(pts[-1], pts[-2])
        else:
            d = add(norm(sub(pts[i], pts[i - 1])), norm(sub(pts[i + 1], pts[i])))
        tangents.append(norm(d))
    return tangents, [left_normal(t) for t in tangents]


# ----------------------------------------------------------------------------
# Polygons and shapes (Babylon XZ)
# ----------------------------------------------------------------------------

def point_in_polygon(p, poly) -> bool:
    x, z = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = x1 + (z - z1) * (x2 - x1) / (z2 - z1)
            if x < xi:
                inside = not inside
    return inside


def polygon_area(poly) -> float:
    return 0.5 * abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                         for i in range(len(poly))))


def polygon_edge_distance(p, poly) -> float:
    return min(seg_closest(p, poly[i], poly[(i + 1) % len(poly)])[0] for i in range(len(poly)))


def ccw(poly):
    area2 = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                for i in range(len(poly)))
    return list(poly) if area2 > 0 else list(reversed(poly))


def obb_corners(cx, cz, sx, sz, yaw):
    """Corners (CCW) of a Babylon oriented box: size sx along local X=(cos a, -sin a), sz along local Z=(sin a, cos a)."""
    ux, uz = (math.cos(yaw), -math.sin(yaw)), (math.sin(yaw), math.cos(yaw))
    pts = []
    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append((cx + ux[0] * a * sx / 2 + uz[0] * b * sz / 2, cz + ux[1] * a * sx / 2 + uz[1] * b * sz / 2))
    return ccw(pts)


def obb_distance(p, cx, cz, sx, sz, yaw) -> float:
    """Signed distance from p to an oriented box in XZ (negative inside)."""
    dx, dz = p[0] - cx, p[1] - cz
    lx = dx * math.cos(yaw) - dz * math.sin(yaw)
    lz = dx * math.sin(yaw) + dz * math.cos(yaw)
    qx, qz = abs(lx) - sx / 2, abs(lz) - sz / 2
    outside = math.hypot(max(qx, 0.0), max(qz, 0.0))
    return outside + min(max(qx, qz), 0.0)


def obb_from_segment(a, b, offset0: float, offset1: float, extend: float = 0.0):
    """Oriented box covering the band between left offsets offset0..offset1 of segment ab.

    Returns (cx, cz, sx, sz, yaw) where local Z runs along the segment."""
    d = norm(sub(b, a))
    n = left_normal(d)
    length = math.dist(a, b) + 2 * extend
    mid = mul(add(a, b), 0.5)
    off = (offset0 + offset1) / 2
    centre = add(mid, mul(n, off))
    yaw = math.atan2(d[0], d[1])
    return centre[0], centre[1], abs(offset1 - offset0), length, yaw


def circle_polygon(cx, cz, r, n=12, circumscribe=True):
    rr = r / math.cos(math.pi / n) if circumscribe else r
    return [(cx + rr * math.cos(TAU * k / n), cz + rr * math.sin(TAU * k / n)) for k in range(n)]


# ----------------------------------------------------------------------------
# Sampling
# ----------------------------------------------------------------------------

def poisson_in_polygon(poly, r: float, rng: random.Random, accept=None, seeds=(), k: int = 30, limit: int = 4000):
    """Bridson Poisson-disc samples inside `poly` with minimum spacing r.

    `seeds` are pre-existing points that constrain spacing but are not returned."""
    xs, zs = [p[0] for p in poly], [p[1] for p in poly]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    cell = r / math.sqrt(2)
    grid: dict[tuple[int, int], tuple[float, float]] = {}

    def key(p):
        return (int((p[0] - x0) // cell), int((p[1] - z0) // cell))

    def far_enough(p):
        kx, kz = key(p)
        for i in range(kx - 2, kx + 3):
            for j in range(kz - 2, kz + 3):
                q = grid.get((i, j))
                if q is not None and math.dist(p, q) < r:
                    return False
        return True

    def ok(p):
        return point_in_polygon(p, poly) and far_enough(p) and (accept is None or accept(p))

    extra_seed_points = []
    for s in seeds:
        if x0 - r <= s[0] <= x1 + r and z0 - r <= s[1] <= z1 + r:
            kk = key(s)
            if kk in grid:
                extra_seed_points.append(s)
            else:
                grid[kk] = (s[0], s[1])
    out, active = [], []
    for _ in range(200):
        p = (rng.uniform(x0, x1), rng.uniform(z0, z1))
        if ok(p):
            grid[key(p)] = p
            out.append(p)
            active.append(p)
            break
    while active and len(out) < limit:
        i = rng.randrange(len(active))
        base = active[i]
        placed = False
        for _ in range(k):
            ang = rng.uniform(0, TAU)
            rad = rng.uniform(r, 2 * r)
            p = (base[0] + rad * math.cos(ang), base[1] + rad * math.sin(ang))
            if ok(p):
                grid[key(p)] = p
                out.append(p)
                active.append(p)
                placed = True
                break
        if not placed:
            active.pop(i)
        if not active and len(out) < limit:
            # Restart in an unreached region (polygons with notches can strand the front).
            for _ in range(300):
                p = (rng.uniform(x0, x1), rng.uniform(z0, z1))
                if ok(p):
                    grid[key(p)] = p
                    out.append(p)
                    active.append(p)
                    break
    for p in extra_seed_points:
        pass
    return out


class SpatialHash:
    """Occupied discs (x, z, radius, tag) for spacing checks across all placement passes."""

    def __init__(self, cell: float = 4.0):
        self.cell = cell
        self.items: dict[tuple[int, int], list[tuple[float, float, float, str]]] = {}

    def add(self, x, z, radius, tag=""):
        k = (int(math.floor(x / self.cell)), int(math.floor(z / self.cell)))
        self.items.setdefault(k, []).append((x, z, radius, tag))

    def clear_of(self, x, z, radius, gap=0.0, ignore=()) -> bool:
        reach = radius + gap + 6.0
        kx0, kx1 = int(math.floor((x - reach) / self.cell)), int(math.floor((x + reach) / self.cell))
        kz0, kz1 = int(math.floor((z - reach) / self.cell)), int(math.floor((z + reach) / self.cell))
        for i in range(kx0, kx1 + 1):
            for j in range(kz0, kz1 + 1):
                for (qx, qz, qr, tag) in self.items.get((i, j), ()):
                    if tag in ignore:
                        continue
                    if math.hypot(x - qx, z - qz) < radius + qr + gap:
                        return False
        return True


# ----------------------------------------------------------------------------
# Mesh accumulation (Blender space)
# ----------------------------------------------------------------------------

class MeshAcc:
    def __init__(self, smooth: bool = False):
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.smooth = smooth

    def add(self, verts, faces):
        base = len(self.verts)
        self.verts.extend(verts)
        self.faces.extend(tuple(base + i for i in f) for f in faces)

    @property
    def triangles(self) -> int:
        return sum(len(f) - 2 for f in self.faces)


def transform(verts, rot: float = 0.0, scale=(1.0, 1.0, 1.0), offset=(0.0, 0.0, 0.0)):
    c, s = math.cos(rot), math.sin(rot)
    out = []
    for x, y, z in verts:
        x, y, z = x * scale[0], y * scale[1], z * scale[2]
        out.append((x * c - y * s + offset[0], x * s + y * c + offset[1], z + offset[2]))
    return out


def box_mesh(sx, sy, z0, z1, taper: float = 1.0, bottom: bool = True):
    """Box centred on the origin in XY (Blender), from z0 to z1. taper scales the top face."""
    hx, hy = sx / 2, sy / 2
    tx, ty = hx * taper, hy * taper
    v = [(-hx, -hy, z0), (hx, -hy, z0), (hx, hy, z0), (-hx, hy, z0),
         (-tx, -ty, z1), (tx, -ty, z1), (tx, ty, z1), (-tx, ty, z1)]
    f = [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    if bottom:
        f.append((0, 3, 2, 1))
    return v, f


def cone_mesh(r0, r1, z0, z1, segments=10, bottom=True, top=True, phase=0.0):
    """Cylinder/cone frustum around the origin (r1 == 0 gives a pointed cone)."""
    v, f = [], []
    for i in range(segments):
        a = phase + TAU * i / segments
        v.append((r0 * math.cos(a), r0 * math.sin(a), z0))
    if r1 > 1e-6:
        for i in range(segments):
            a = phase + TAU * i / segments
            v.append((r1 * math.cos(a), r1 * math.sin(a), z1))
        for i in range(segments):
            j = (i + 1) % segments
            f.append((i, j, segments + j, segments + i))
        if top:
            c = len(v)
            v.append((0.0, 0.0, z1))
            for i in range(segments):
                f.append((c, segments + i, segments + (i + 1) % segments))
    else:
        tip = len(v)
        v.append((0.0, 0.0, z1))
        for i in range(segments):
            f.append((i, (i + 1) % segments, tip))
    if bottom:
        c = len(v)
        v.append((0.0, 0.0, z0))
        for i in range(segments):
            f.append((c, (i + 1) % segments, i))
    return v, f


_ICO: dict[int, tuple[list, list]] = {}


def icosphere(subdiv: int):
    if subdiv in _ICO:
        return _ICO[subdiv]
    t = (1 + 5 ** 0.5) / 2
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    verts = [tuple(c / math.sqrt(sum(q * q for q in p)) for c in p) for p in verts]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(subdiv):
        cache: dict[tuple[int, int], int] = {}

        def mid(i, j):
            k = (min(i, j), max(i, j))
            if k not in cache:
                p = [(verts[i][c] + verts[j][c]) / 2 for c in range(3)]
                length = math.sqrt(sum(q * q for q in p))
                verts.append(tuple(q / length for q in p))
                cache[k] = len(verts) - 1
            return cache[k]

        new_faces = []
        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = new_faces
    # Make sure every face winds outward (right-handed, CCW seen from outside).
    fixed = []
    for f in faces:
        a, b, c = (verts[i] for i in f)
        n = ((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
             (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
             (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        centroid = [(a[i] + b[i] + c[i]) / 3 for i in range(3)]
        fixed.append(f if sum(n[i] * centroid[i] for i in range(3)) > 0 else (f[0], f[2], f[1]))
    _ICO[subdiv] = (verts, fixed)
    return _ICO[subdiv]


def lumpy_sphere(subdiv, radius, seed, amp=0.15, squash=1.0, flat_bottom=None):
    """Noisy icosphere around the origin; radial jitter `amp`, vertical scale `squash`."""
    v0, f = icosphere(subdiv)
    rng = random.Random(seed)
    ox, oy, oz = rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)
    v = []
    for x, y, z in v0:
        n = fbm2(x * 1.7 + ox + z * 0.9, y * 1.7 + oy - z * 0.7 + oz, seed, 2)
        rr = radius * (1 + amp * (2 * n - 1))
        zz = z * rr * squash
        if flat_bottom is not None:
            zz = max(zz, flat_bottom)
        v.append((x * rr, y * rr, zz))
    return v, list(f)


def ear_clip(poly2d):
    """Triangulate a simple polygon given as 2D points; returns index triples (CCW)."""
    pts = list(poly2d)
    idx = list(range(len(pts)))
    area2 = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if area2 < 0:
        idx.reverse()
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        clipped = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(sub(b, a), sub(c, b)) <= 1e-12:
                continue
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = pts[j]
                if (cross(sub(b, a), sub(p, a)) >= 0 and cross(sub(c, b), sub(p, b)) >= 0 and
                        cross(sub(a, c), sub(p, c)) >= 0):
                    inside = True
                    break
            if inside:
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            clipped = True
            break
        if not clipped:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


# ----------------------------------------------------------------------------
# Iso-surface clipping on a grid (water surfaces)
# ----------------------------------------------------------------------------

def clip_grid_below(fn, x0, x1, z0, z1, step):
    """Triangles (Babylon XZ) of the region where fn(x, z) < 0, by marching triangles on a grid.

    Returns (points, triangles) with shared vertices; triangles wind CCW in plan view."""
    nx, nz = int(math.ceil((x1 - x0) / step)), int(math.ceil((z1 - z0) / step))
    xs = [x0 + (x1 - x0) * i / nx for i in range(nx + 1)]
    zs = [z0 + (z1 - z0) * j / nz for j in range(nz + 1)]
    val = [[fn(x, z) for x in xs] for z in zs]
    pts: list[tuple[float, float]] = []
    lookup: dict[tuple[int, int], int] = {}
    tris = []

    def vid(p):
        k = (round(p[0] * 2000), round(p[1] * 2000))
        if k not in lookup:
            lookup[k] = len(pts)
            pts.append(p)
        return lookup[k]

    def clip(tri):
        poly = []
        for i in range(3):
            (pa, fa), (pb, fb) = tri[i], tri[(i + 1) % 3]
            if fa < 0:
                poly.append(pa)
            if (fa < 0) != (fb < 0):
                t = fa / (fa - fb)
                poly.append((pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t))
        if len(poly) >= 3:
            ids = [vid(p) for p in poly]
            for k in range(1, len(ids) - 1):
                if len({ids[0], ids[k], ids[k + 1]}) == 3:
                    tris.append((ids[0], ids[k], ids[k + 1]))

    for j in range(nz):
        for i in range(nx):
            c00 = ((xs[i], zs[j]), val[j][i])
            c10 = ((xs[i + 1], zs[j]), val[j][i + 1])
            c11 = ((xs[i + 1], zs[j + 1]), val[j + 1][i + 1])
            c01 = ((xs[i], zs[j + 1]), val[j + 1][i])
            for tri in ((c00, c10, c11), (c00, c11, c01)):
                if all(v[1] >= 0 for v in tri):
                    continue
                clip(tri)
    return pts, tris


# ----------------------------------------------------------------------------
# Occupancy grid flood fill (walk reachability)
# ----------------------------------------------------------------------------

class Raster:
    """Boolean blocked-cell raster over Babylon XZ bounds with a fixed resolution."""

    def __init__(self, x0, x1, z0, z1, res=0.1):
        self.x0, self.z0, self.res = x0, z0, res
        self.nx, self.nz = int(round((x1 - x0) / res)), int(round((z1 - z0) / res))
        self.blocked = bytearray(self.nx * self.nz)

    def centre(self, i, j):
        return (self.x0 + (i + 0.5) * self.res, self.z0 + (j + 0.5) * self.res)

    def index(self, x, z):
        i, j = int((x - self.x0) / self.res), int((z - self.z0) / self.res)
        if 0 <= i < self.nx and 0 <= j < self.nz:
            return i, j
        return None

    def block_shape(self, bbox, signed_distance, inflate):
        bx0, bx1, bz0, bz1 = bbox
        i0 = max(0, int((bx0 - inflate - self.x0) / self.res) - 1)
        i1 = min(self.nx - 1, int((bx1 + inflate - self.x0) / self.res) + 1)
        j0 = max(0, int((bz0 - inflate - self.z0) / self.res) - 1)
        j1 = min(self.nz - 1, int((bz1 + inflate - self.z0) / self.res) + 1)
        res, x0, z0, nx = self.res, self.x0, self.z0, self.nx
        blocked = self.blocked
        for j in range(j0, j1 + 1):
            z = z0 + (j + 0.5) * res
            row = j * nx
            for i in range(i0, i1 + 1):
                if blocked[row + i]:
                    continue
                if signed_distance((x0 + (i + 0.5) * res, z)) < inflate:
                    blocked[row + i] = 1

    def flood(self, start):
        st = self.index(*start)
        reach = bytearray(self.nx * self.nz)
        if st is None or self.blocked[st[1] * self.nx + st[0]]:
            return reach
        nx, nz, blocked = self.nx, self.nz, self.blocked
        q = deque([st[1] * nx + st[0]])
        reach[q[0]] = 1
        while q:
            k = q.popleft()
            i, j = k % nx, k // nx
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ii, jj = i + di, j + dj
                if 0 <= ii < nx and 0 <= jj < nz:
                    kk = jj * nx + ii
                    if not reach[kk] and not blocked[kk]:
                        reach[kk] = 1
                        q.append(kk)
        return reach
