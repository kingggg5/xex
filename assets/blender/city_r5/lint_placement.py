"""Placement lint for Blender map sources (city masters, Sunmeadow cells, kits).

Read-only: the loaded .blend is never saved or modified (the script only reads
mesh data and builds BVH trees in memory).

Rules (thresholds are profile values; defaults below):
  L1  floating      A connected group of parts (contact graph, 3 cm tolerance = the float threshold)
                    that touches neither the ground nor an anchored structure and
                    whose lowest point is more than 3 cm above the ground beneath.
      L1b edge-gap  (warning) A grounded prop base that touches the ground on one
                    side but leaves a gap of more than 10 cm under another part of
                    its footprint.
  L2  sinking       A prop base whose lowest vertices are more than 10 cm under the
                    ground surface at every footprint sample.
  L3  unparented    A mesh without a parent whose name extends a parented sibling's
                    name and whose world-space centre equals that sibling's kit-local
                    centre: a child part that never received its root transform.
                    Other loose meshes outside the profile's allow-list are L3 warnings.
  L4  z-fighting    Coplanar, same-facing, overlapping faces on two different meshes
                    (includes exact duplicate meshes).
  L5  no ground     A part or floating group with no ground surface under any of its
                    footprint samples.
Intentional cases (magic hover pieces, hanging signs, embedded foundations, rocks,
tree flare...) are matched by explicit profile rules, reported with their reason and
kept out of the defect counts. Nothing is hidden.

CLI (one Blender process at a time):
  blender -b --factory-startup --disable-autoexec <file.blend> --python-exit-code 1 \
    --python assets/blender/city_r5/lint_placement.py -- --profile city \
    --out <report.json> [--csv <report.csv>] [--probes <probes.json>] [--fail-on L1,L2,L3,L4,L5]

  --probes: JSON list of {"id","family","x","z","bottom_y"} points in RUNTIME
  coordinates (e.g. code-placed props); each is sampled against this scene's ground.

Import use (planned export_helper.preflight hook):
  import lint_placement; report = lint_placement.run_lint('city')
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SCHEMA = 'xexoria.placement-lint/1'

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
_CITY_GROUND = re.compile(
    r'^(terrain / (grass ground|plaza |avenue |path |canal promenade|canal bed|channel bed|pool bed|castle terrace / top|'
    r'wizard terrace / top|wizard stairs$|cliff grass lip)|traversal / |castle terrace paving|castle grand stair tread|'
    r'castle stair landing|bridge dressed flagstone|walk_)')
_CITY_GROUND_EXCLUDE = re.compile(r' curb')

PROFILES = {
    'city': {
        'frame': 'city',  # runtime = (x, z, 176 + y)
        'skip': re.compile(r'^(fx_|anim_|emit_|light_|presentation |cam |Review )'),
        'anchor': re.compile(r'^terrain / '),
        'ground': lambda n: bool(_CITY_GROUND.search(n)) and not _CITY_GROUND_EXCLUDE.search(n),
        'loose_ok': re.compile(r'^(terrain / |traversal / |castle terrace paving|castle grand stair masonry core|castle lower plinth|'
                               r'castle plinth moulding|castle stair stone handrail|city arrival |wizard entry masonry stair core|'
                               r'fx_|anim_|emit_|light_|presentation |City / )'),
        'intentional_float': [
            (re.compile(r'rune ring|anim_wizard_ring|anim_portal|portal rune disc'), 'animated rune ring that hovers by design (runtime spin hook)'),
            (re.compile(r'floating shard|hover shard|pylon shard|portal shard'), 'magic shard that hovers by design'),
            (re.compile(r'stalactite|satellite rock|floating rock|island underside'), 'island underside / satellite rock by design'),
            (re.compile(r'anim_crystal|fountain crystal|crowning crystal'), 'hovering crystal by design (runtime spin hook)'),
            (re.compile(r'well water|blue water|second water|upper water'), 'water surface held inside its basin walls'),
        ],
        'intentional_sink': [
            (re.compile(r'bank backing'), 1.0, 'solid masonry backing under the arrival paving (never visible)'),
            (re.compile(r'arch voussoir'), 2.0, 'arch springer voussoirs embedded in the bridge abutments'),
            (re.compile(r'entrance carved surround'), 0.30, 'door surround footing set into the threshold'),
            (re.compile(r'leaf mound'), 0.25, 'shrub mound rooted below the soil (reads as a planted bush)'),
            (re.compile(r'foundation|plinth|footing|retaining wall|buttress|masonry core|canal wall|pier|abutment|'
                        r'cheek|stair core|head wall|gate curtain|gate lion|tower base|bridge arch|bridge spandrel|bridge pier'),
             0.60, 'structural footing embedded so it never shows a gap on uneven ground'),
            (re.compile(r'tree trunk|tree_bark|trunk'), 0.45, 'tree root flare embedded in the ground'),
            (re.compile(r'rock|boulder|stone_post_.*_foot|edge_stone|pebble'), 0.60, 'rock or stone set into the ground (reads as embedded)'),
        ],
        'float_tol': 0.03, 'sink_tol': 0.10, 'contact_tol': 0.03, 'edge_gap': 0.10,
    },
    'cells': {
        'frame': 'cells',  # runtime = (x, z, -y)
        'skip': re.compile(r'^(review_|fx_|anim_|emit_|light_)'),
        'anchor': re.compile(r'^(terrain_ground|terrain_rock_fascia)'),
        'ground': lambda n: n.startswith('terrain_ground'),
        'loose_ok': re.compile(r'.*'),
        'intentional_float': [
            (re.compile(r'rune_crystal|arch_rune|beacon'), 'rune gem fixed to the stone (checked for contact)'),
        ],
        'intentional_sink': [
            (re.compile(r'tree_bark|trunk'), 0.45, 'tree root flare embedded in the ground'),
            (re.compile(r'edge_stone|rock|pebble|fascia|foot'), 0.60, 'rock or stone set into the ground (reads as embedded)'),
            (re.compile(r'flora|ferns|flower'), 0.25, 'grass and flower cards rooted below the surface'),
        ],
        'float_tol': 0.03, 'sink_tol': 0.10, 'contact_tol': 0.03, 'edge_gap': 0.10,
    },
}


def runtime_xyz(p, frame):
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    if frame == 'city':
        return [round(x, 3), round(z, 3), round(176.0 + y, 3)]
    if frame == 'cells':
        return [round(x, 3), round(z, 3), round(-y, 3)]
    return [round(x, 3), round(y, 3), round(z, 3)]


def blender_from_runtime(x, z, frame):
    if frame == 'city':
        return x, z - 176.0
    if frame == 'cells':
        return x, -z
    return x, z


def family_of(name: str) -> str:
    base = re.sub(r'\.\d{3}$', '', name)
    return re.sub(r'\d+', '#', base)


# ---------------------------------------------------------------------------
# Mesh data
# ---------------------------------------------------------------------------
class Part:
    __slots__ = ('obj', 'name', 'idx', 'verts', 'tris', 'lo', 'hi', 'root', '_bvh', 'is_anchor', 'is_ground')

    def __init__(self, obj, idx):
        self.obj = obj
        self.name = obj.name
        self.idx = idx
        mesh = obj.data
        n = len(mesh.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        mesh.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        m = np.array(obj.matrix_world, dtype=np.float64)
        self.verts = co @ m[:3, :3].T + m[:3, 3]
        mesh.calc_loop_triangles()
        t = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
        mesh.loop_triangles.foreach_get('vertices', t)
        self.tris = t.reshape(-1, 3)
        if n:
            self.lo = self.verts.min(axis=0)
            self.hi = self.verts.max(axis=0)
        else:
            self.lo = self.hi = np.zeros(3)
        r = obj
        while r.parent is not None:
            r = r.parent
        self.root = r.name if r is not obj else None
        self._bvh = None
        self.is_anchor = False
        self.is_ground = False

    @property
    def bvh(self):
        if self._bvh is None:
            self._bvh = BVHTree.FromPolygons([tuple(v) for v in self.verts], [tuple(t) for t in self.tris], all_triangles=True)
        return self._bvh


def combined_bvh(parts):
    verts, tris, owner = [], [], []
    offset = 0
    for p in parts:
        if not len(p.tris):
            continue
        verts.append(p.verts)
        tris.append(p.tris + offset)
        owner.extend([p.idx] * len(p.tris))
        offset += len(p.verts)
    if not verts:
        return None, np.zeros(0, dtype=np.int64)
    v = np.concatenate(verts)
    t = np.concatenate(tris)
    tree = BVHTree.FromPolygons([tuple(x) for x in v], [tuple(x) for x in t], all_triangles=True)
    return tree, np.array(owner, dtype=np.int64)


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a
        return a


# ---------------------------------------------------------------------------
# Ground sampling
# ---------------------------------------------------------------------------
DOWN = Vector((0.0, 0.0, -1.0))
UP = Vector((0.0, 0.0, 1.0))


def ground_at(tree, owner, parts, x, y, z_from, window=1.0):
    """Ground height under (x, y) seen from z_from + window; returns (z, mesh) or (None, None)."""
    loc, _n, index, _d = tree.ray_cast(Vector((x, y, z_from + window)), DOWN, 500.0)
    if loc is None:
        # Deeply sunk: look for a surface above the point.
        loc, _n, index, _d = tree.ray_cast(Vector((x, y, z_from - 0.001)), UP, 60.0)
        if loc is None:
            return None, None
    return float(loc.z), parts[int(owner[index])].name


def base_samples(part, max_samples=24):
    v = part.verts
    if not len(v):
        return np.zeros((0, 3))
    zmin = v[:, 2].min()
    base = v[v[:, 2] <= zmin + 0.02]
    if len(base) > max_samples:
        step = len(base) / max_samples
        base = base[[int(i * step) for i in range(max_samples)]]
    # add the footprint centre at the base height
    c = np.array([[(part.lo[0] + part.hi[0]) * 0.5, (part.lo[1] + part.hi[1]) * 0.5, zmin]])
    return np.concatenate([base, c])


def ground_gaps(tree, owner, parts, samples):
    out = []
    for x, y, z in samples:
        gz, mesh = ground_at(tree, owner, parts, float(x), float(y), float(z))
        out.append((float(x), float(y), float(z), gz, mesh))
    return out


# ---------------------------------------------------------------------------
# Contact graph
# ---------------------------------------------------------------------------
def aabb_overlap(a_lo, a_hi, b_lo, b_hi, pad):
    return bool(np.all(a_lo - pad <= b_hi) and np.all(b_lo - pad <= a_hi))


def touches(a, b, tol):
    """True when meshes a and b intersect or come within tol of each other."""
    if not len(a.tris) or not len(b.tris):
        return False
    if a.bvh.overlap(b.bvh):
        return True
    # vertex proximity: query the smaller vertex set against the other tree,
    # restricted to vertices inside the other's padded box
    small, big = (a, b) if len(a.verts) <= len(b.verts) else (b, a)
    v = small.verts
    mask = np.all((v >= big.lo - tol) & (v <= big.hi + tol), axis=1)
    tree = big.bvh
    for co in v[mask]:
        if tree.find_nearest(Vector(co), tol)[0] is not None:
            return True
    # the bigger set against the smaller tree (thin parts with few vertices)
    v = big.verts
    mask = np.all((v >= small.lo - tol) & (v <= small.hi + tol), axis=1)
    if mask.any():
        tree = small.bvh
        for co in v[mask][:4000]:
            if tree.find_nearest(Vector(co), tol)[0] is not None:
                return True
    # full containment (a part hidden inside another closed part)
    if np.all(small.lo >= big.lo) and np.all(small.hi <= big.hi):
        c = Vector(((small.lo + small.hi) * 0.5).tolist())
        hits = 0
        origin = c.copy()
        for _ in range(64):
            loc, _n, _i, _d = big.bvh.ray_cast(origin, Vector((1.0, 0.0001, 0.0002)), 1e4)
            if loc is None:
                break
            hits += 1
            origin = loc + Vector((1e-4, 0, 0))
        if hits % 2 == 1:
            return True
    return False


def build_contacts(parts, movable, tol, log):
    """Union-find over movable parts using a 3D grid broadphase."""
    uf = UnionFind(len(parts))
    cell = 3.0
    grid = defaultdict(list)
    for p in movable:
        lo = np.floor((p.lo - tol) / cell).astype(int)
        hi = np.floor((p.hi + tol) / cell).astype(int)
        span = (hi - lo + 1)
        if span.prod() > 4000:  # huge part: register on a coarse shell of cells
            hi = np.minimum(hi, lo + 60)
        for i in range(lo[0], hi[0] + 1):
            for j in range(lo[1], hi[1] + 1):
                for k in range(lo[2], hi[2] + 1):
                    grid[(i, j, k)].append(p.idx)
    pairs = set()
    for members in grid.values():
        if len(members) < 2:
            continue
        for ai in range(len(members)):
            a = members[ai]
            pa = parts[a]
            for bi in range(ai + 1, len(members)):
                b = members[bi]
                key = (a, b) if a < b else (b, a)
                if key in pairs:
                    continue
                if aabb_overlap(pa.lo, pa.hi, parts[b].lo, parts[b].hi, tol):
                    pairs.add(key)
    log(f'contact broadphase: {len(pairs)} candidate pairs from {len(movable)} parts')
    # big parts first so structural shells merge early and prune the rest
    vol = {p.idx: float(np.prod(np.maximum(p.hi - p.lo, 0.01))) for p in movable}
    order = sorted(pairs, key=lambda k: -max(vol[k[0]], vol[k[1]]))
    tested = 0
    for a, b in order:
        if uf.find(a) == uf.find(b):
            continue
        tested += 1
        if touches(parts[a], parts[b], tol):
            uf.union(a, b)
    log(f'contact narrowphase: {tested} pairs tested')
    return uf


# ---------------------------------------------------------------------------
# L4 coplanar overlap
# ---------------------------------------------------------------------------
def _clip(subject, clipper):
    """Sutherland-Hodgman clip of convex polygon subject by convex clipper (2D, CCW)."""
    out = subject
    n = len(clipper)
    for i in range(n):
        if not out:
            break
        ax, ay = clipper[i]
        bx, by = clipper[(i + 1) % n]
        inp = out
        out = []
        m = len(inp)
        for j in range(m):
            px, py = inp[j]
            qx, qy = inp[(j + 1) % m]
            pin = (bx - ax) * (py - ay) - (by - ay) * (px - ax) >= -1e-12
            qin = (bx - ax) * (qy - ay) - (by - ay) * (qx - ax) >= -1e-12
            if pin:
                out.append((px, py))
            if pin != qin:
                dx, dy = qx - px, qy - py
                ex, ey = bx - ax, by - ay
                den = ex * dy - ey * dx
                if abs(den) > 1e-15:
                    t = (ey * (px - ax) - ex * (py - ay)) / den
                    out.append((px + dx * t, py + dy * t))
    return out


def _area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def coplanar_overlaps(parts, log, min_area=0.0025, n_q=0.02, d_q=0.004, min_pair_area=0.01, eps=1e-4, detail=None):
    """Same-facing coplanar overlapping triangles between different meshes.

    Downward-facing faces (normal z < -0.7) are skipped: they sit on the ground or
    under ledges and cannot flicker from the game camera.
    """
    rows = []
    for p in parts:
        if not len(p.tris):
            continue
        a = p.verts[p.tris[:, 0]]
        b = p.verts[p.tris[:, 1]]
        c = p.verts[p.tris[:, 2]]
        cr = np.cross(b - a, c - a)
        ln = np.linalg.norm(cr, axis=1)
        area = ln * 0.5
        keep = area >= min_area
        if not keep.any():
            continue
        nrm = cr[keep] / ln[keep][:, None]
        up_ok = nrm[:, 2] >= -0.7
        if not up_ok.any():
            continue
        idx = np.nonzero(keep)[0][up_ok]
        nrm = nrm[up_ok]
        ak, bk, ck_ = a[keep][up_ok], b[keep][up_ok], c[keep][up_ok]
        d = np.einsum('ij,ij->i', nrm, ak)
        rows.append((p.idx, idx, nrm, d, ak, bk, ck_))
    if not rows:
        return []
    obj = np.concatenate([np.full(len(r[1]), r[0]) for r in rows])
    tri = np.concatenate([r[1] for r in rows])
    nrm = np.concatenate([r[2] for r in rows])
    dd = np.concatenate([r[3] for r in rows])
    A = np.concatenate([r[4] for r in rows])
    B = np.concatenate([r[5] for r in rows])
    C = np.concatenate([r[6] for r in rows])
    nq = np.round(nrm / n_q).astype(np.int64) + 64
    lo = np.minimum(np.minimum(A, B), C)
    hi = np.maximum(np.maximum(A, B), C)
    pair_area = defaultdict(float)
    pair_count = Counter()
    pair_where = {}
    checked = 0

    def exact(ti, tj):
        nonlocal checked
        if float(np.dot(nrm[ti], nrm[tj])) < 0.9995 or abs(dd[ti] - dd[tj]) > 0.002:
            return
        key_t = (int(tri[ti]), int(tri[tj]))
        k = (int(obj[ti]), int(obj[tj]))
        if k[0] > k[1]:
            k = (k[1], k[0])
            key_t = (key_t[1], key_t[0])
        if (k, key_t) in pair_where:
            return
        n = nrm[ti]
        ax = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(n, ax)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        P = [(float(np.dot(q, u)), float(np.dot(q, v))) for q in (A[ti], B[ti], C[ti])]
        Q = [(float(np.dot(q, u)), float(np.dot(q, v))) for q in (A[tj], B[tj], C[tj])]
        if (P[1][0] - P[0][0]) * (P[2][1] - P[0][1]) - (P[1][1] - P[0][1]) * (P[2][0] - P[0][0]) < 0:
            P.reverse()
        if (Q[1][0] - Q[0][0]) * (Q[2][1] - Q[0][1]) - (Q[1][1] - Q[0][1]) * (Q[2][0] - Q[0][0]) < 0:
            Q.reverse()
        checked += 1
        inter = _clip(P, Q)
        if len(inter) < 3:
            return
        ar = _area(inter)
        if ar < 1e-4:
            return
        pair_where[(k, key_t)] = ((A[ti] + B[ti] + C[ti]) / 3.0).tolist()
        if detail is not None:  # triangle-level record for the r6 coincident-face repair op
            detail.append((k, key_t, ar))
        pair_area[k] += ar
        pair_count[k] += 1

    for shift in (0.0, 0.5):
        dq = np.floor(dd / d_q + shift).astype(np.int64)
        key = ((nq[:, 0] * 129 + nq[:, 1]) * 129 + nq[:, 2]) * 1_000_003 + dq
        order = np.argsort(key, kind='stable')
        ks = key[order]
        cut = np.nonzero(np.diff(ks))[0] + 1
        starts = np.concatenate([[0], cut])
        ends = np.concatenate([cut, [len(ks)]])
        for s, e in zip(starts, ends):
            if e - s < 2:
                continue
            members = order[s:e]
            objs = obj[members]
            uniq = np.unique(objs)
            if len(uniq) < 2:
                continue
            groups = {int(o): members[objs == o] for o in uniq}
            boxes = {o: (lo[g].min(axis=0), hi[g].max(axis=0)) for o, g in groups.items()}
            keys = list(groups)
            for i, oa in enumerate(keys):
                la, ha = boxes[oa]
                for ob in keys[i + 1:]:
                    lb, hb = boxes[ob]
                    if np.any(la > hb + eps) or np.any(lb > ha + eps):
                        continue
                    ga, gb = groups[oa], groups[ob]
                    ga = ga[np.all((lo[ga] <= hb + eps) & (hi[ga] >= lb - eps), axis=1)]
                    gb = gb[np.all((lo[gb] <= ha + eps) & (hi[gb] >= la - eps), axis=1)]
                    if not len(ga) or not len(gb):
                        continue
                    for c0 in range(0, len(ga), 512):
                        sa = ga[c0:c0 + 512]
                        ov = np.all((lo[sa][:, None, :] <= hi[gb][None, :, :] + eps) &
                                    (lo[gb][None, :, :] <= hi[sa][:, None, :] + eps), axis=2)
                        ia, ib = np.nonzero(ov)
                        for ti, tj in zip(sa[ia], gb[ib]):
                            exact(int(ti), int(tj))
    log(f'coplanar check: {checked} triangle pairs clipped')
    out = []
    first = {}
    for (k, _t), w in pair_where.items():
        first.setdefault(k, w)
    for k, ar in pair_area.items():
        if ar >= min_pair_area:
            out.append({'a': parts[k[0]].name, 'b': parts[k[1]].name, 'overlap_m2': round(ar, 4),
                        'triangle_pairs': pair_count[k], 'at_blender': [round(x, 3) for x in first[k]]})
    out.sort(key=lambda r: -r['overlap_m2'])
    return out


# ---------------------------------------------------------------------------
# Main lint
# ---------------------------------------------------------------------------
def classify(rules, name):
    for item in rules:
        if item[0].search(name):
            return item
    return None


def run_lint(profile_name='city', objects=None, probes=None, log=print):
    prof = PROFILES[profile_name]
    frame = prof['frame']
    t0 = time.time()
    scene_objs = objects if objects is not None else list(bpy.context.scene.objects)
    meshes = [o for o in scene_objs if o.type == 'MESH' and not prof['skip'].search(o.name) and len(o.data.polygons)]
    parts = [Part(o, i) for i, o in enumerate(meshes)]
    by_name = {p.name: p for p in parts}
    for p in parts:
        p.is_anchor = bool(prof['anchor'].search(p.name))
        p.is_ground = bool(prof['ground'](p.name))
    anchors = [p for p in parts if p.is_anchor]
    grounds = [p for p in parts if p.is_ground]
    movable = [p for p in parts if not p.is_anchor]
    log(f'lint {profile_name}: {len(parts)} meshes ({len(anchors)} anchors, {len(grounds)} ground surfaces) in {time.time() - t0:.1f}s')
    g_tree, g_owner = combined_bvh(grounds)
    a_tree, a_owner = combined_bvh(anchors)
    tol, ftol, stol, egap = prof['contact_tol'], prof['float_tol'], prof['sink_tol'], prof['edge_gap']

    # --- per-part ground contact ------------------------------------------
    base_info = {}
    anchored = set()
    for p in movable:
        samples = base_samples(p)
        gaps = ground_gaps(g_tree, g_owner, parts, samples) if g_tree else []
        base_info[p.idx] = gaps
        if p.is_ground:
            continue  # a walk surface measures itself; contact decides its support
        valid = [z - gz for (_x, _y, z, gz, _m) in gaps if gz is not None]
        if valid and min(valid) <= ftol:
            anchored.add(p.idx)
    log(f'ground sampling done {time.time() - t0:.1f}s; {len(anchored)} parts touch the ground directly')
    if a_tree is not None:
        a_lo = np.min([a.lo for a in anchors], axis=0)
        a_hi = np.max([a.hi for a in anchors], axis=0)
        for p in movable:
            if p.idx in anchored or not aabb_overlap(p.lo, p.hi, a_lo, a_hi, tol):
                continue
            hit = False
            if p.bvh.overlap(a_tree):
                hit = True
            else:
                for co in p.verts:
                    if a_tree.find_nearest(Vector(co), tol)[0] is not None:
                        hit = True
                        break
            if hit:
                anchored.add(p.idx)
    log(f'anchor contact done {time.time() - t0:.1f}s; {len(anchored)} parts anchored directly')
    uf = build_contacts(parts, movable, tol, log)
    comp = defaultdict(list)
    for p in movable:
        comp[uf.find(p.idx)].append(p.idx)
    grounded_roots = {uf.find(i) for i in anchored}
    log(f'components: {len(comp)} ({len(grounded_roots)} grounded) {time.time() - t0:.1f}s')

    findings = []

    def rec(rule, ident, members, at, gap, mesh, intentional=None, extra=None):
        p0 = parts[members[0]]
        row = {'rule': rule, 'id': ident, 'family': family_of(p0.name), 'root': p0.root,
               'members': [parts[m].name for m in members[:12]], 'member_count': len(members),
               'at_blender': [round(float(v), 3) for v in at], 'at_runtime': runtime_xyz(at, frame),
               'gap_m': None if gap is None else round(float(gap), 4), 'ground_mesh': mesh,
               'intentional': intentional is not None, 'reason': intentional or ''}
        if extra:
            row.update(extra)
        findings.append(row)

    # --- L1 / L5 floating groups --------------------------------------------
    for root, members in comp.items():
        if root in grounded_roots:
            continue
        verts = np.concatenate([parts[m].verts for m in members])
        zmin = verts[:, 2].min()
        low = verts[verts[:, 2] <= zmin + 0.02]
        if len(low) > 24:
            low = low[np.linspace(0, len(low) - 1, 24).astype(int)]
        gaps = ground_gaps(g_tree, g_owner, parts, low) if g_tree else []
        valid = [(z - gz, m) for (_x, _y, z, gz, m) in gaps if gz is not None]
        names = ' | '.join(parts[m].name for m in members)
        why = classify(prof['intentional_float'], names)
        at = low[0] if len(low) else verts[0]
        ident = parts[members[0]].name if len(members) == 1 else f'{parts[members[0]].name} (+{len(members) - 1})'
        full = {'all_members': [parts[m].name for m in members]}
        if not valid:
            rec('L5', ident, members, at, None, None, why[1] if why else None, full)
            continue
        gap, mesh = min(valid, key=lambda r: r[0])
        if gap > ftol:
            rec('L1', ident, members, at, gap, mesh, why[1] if why else None, full)

    # --- L2 sinking and L1b edge gaps on direct ground contacts --------------
    for p in movable:
        if p.is_ground or p.idx not in anchored:
            continue
        gaps = [(z - gz, m, (x, y, z)) for (x, y, z, gz, m) in base_info.get(p.idx, []) if gz is not None]
        if not gaps:
            continue
        lo_gap = min(g for g, _m, _a in gaps)
        hi_gap = max(g for g, _m, _a in gaps)
        if hi_gap < -stol:  # under the ground at every sample
            rule = classify(prof['intentional_sink'], p.name)
            depth = -hi_gap
            intentional = None
            if rule and depth <= rule[1]:
                intentional = f'{rule[2]} (allowed to {rule[1]:.2f} m)'
            at = min(gaps, key=lambda r: r[0])[2]
            rec('L2', p.name, [p.idx], at, hi_gap, gaps[0][1], intentional, {'depth_m': round(depth, 4)})
        near = [g for g, m_, _a in gaps if g <= 2.5 and not re.search(r'canal|pool|channel|cliff|bed', m_ or '')]
        hi_gap = max(near) if near else lo_gap
        if lo_gap <= ftol and hi_gap > egap and not re.search(r'foundation|plinth|bridge parapet|stair|tread|landing', p.name):
            at = max(gaps, key=lambda r: r[0])[2]
            rec('L1b', p.name, [p.idx], at, hi_gap, gaps[0][1], None, {'contact_gap_m': round(lo_gap, 4)})

    # --- L3 unparented child parts -----------------------------------------
    parented = {p.name: p for p in parts if p.obj.parent is not None}
    stem_index = defaultdict(list)
    for p in parented.values():
        stem_index[re.sub(r'\.\d{3}$', '', p.name)].append(p)
    for p in parts:
        if p.obj.parent is not None or p.is_anchor:
            continue
        base = re.sub(r'\.\d{3}$', '', p.name)
        suffix = p.name[len(base):]
        centre = (p.lo + p.hi) * 0.5
        words = base.split(' ')
        best = None
        for cut in range(len(words) - 1, 0, -1):
            stem = ' '.join(words[:cut])
            for cand in stem_index.get(stem, []):
                inv = np.array(cand.obj.parent.matrix_world.inverted(), dtype=np.float64)
                oc = (cand.lo + cand.hi) * 0.5
                local = inv[:3, :3] @ oc + inv[:3, 3]
                err = float(np.linalg.norm(local[:2] - centre[:2]))
                same_suffix = cand.name[len(stem):] == suffix
                score = (err >= 0.05, not same_suffix, err)
                if best is None or score < best[0]:
                    best = (score, cand, err)
            if best is not None and best[2] < 0.05:
                break
        if best is not None and best[2] < 0.05:
            owner, err = best[1], best[2]
            world = np.array(owner.obj.parent.matrix_world, dtype=np.float64)
            fixed = world[:3, :3] @ centre + world[:3, 3]
            rec('L3', p.name, [p.idx], centre, None, None, None,
                {'owner': owner.name, 'owner_parent': owner.obj.parent.name, 'local_match_m': round(err, 4),
                 'fixed_at_runtime': runtime_xyz(fixed, frame),
                 'fix': f'parent to {owner.obj.parent.name} with identity parent inverse'})
            continue
        if not prof['loose_ok'].search(p.name):
            rec('L3w', p.name, [p.idx], centre, None, None, None, {'note': 'loose mesh outside the allow-list'})

    # --- L4 coplanar overlaps -------------------------------------------------
    z_pairs = coplanar_overlaps(parts, log)
    for row in z_pairs:
        a = by_name[row['a']]
        rec('L4', f"{row['a']} x {row['b']}", [a.idx, by_name[row['b']].idx], row['at_blender'], None, None, None,
            {'overlap_m2': row['overlap_m2'], 'triangle_pairs': row['triangle_pairs']})
    log(f'L4 done {time.time() - t0:.1f}s')

    # --- probes ---------------------------------------------------------------
    probe_rows = []
    for pr in probes or []:
        bx, by = blender_from_runtime(pr['x'], pr['z'], frame)
        gz, mesh = ground_at(g_tree, g_owner, parts, bx, by, float(pr['bottom_y']), window=3.0) if g_tree else (None, None)
        gap = None if gz is None else float(pr['bottom_y']) - gz
        probe_rows.append(dict(pr, ground_y=None if gz is None else round(gz, 4), gap_m=None if gap is None else round(gap, 4),
                               ground_mesh=mesh))

    counts = Counter(f['rule'] for f in findings if not f['intentional'])
    intentional = Counter(f['rule'] for f in findings if f['intentional'])
    by_family = defaultdict(Counter)
    for f in findings:
        by_family[f['rule']][f['family'] + (' (intentional)' if f['intentional'] else '')] += 1
    report = {
        'schema': SCHEMA, 'profile': profile_name, 'file': bpy.data.filepath, 'blender': bpy.app.version_string,
        'thresholds': {'float_m': ftol, 'sink_m': stol, 'contact_tolerance_m': tol, 'edge_gap_m': egap},
        'meshes': len(parts), 'anchors': len(anchors), 'ground_surfaces': len(grounds),
        'components': len(comp), 'grounded_components': len(grounded_roots),
        'defects': dict(sorted(counts.items())), 'intentional': dict(sorted(intentional.items())),
        'by_family': {k: dict(v.most_common()) for k, v in sorted(by_family.items())},
        'findings': findings, 'probes': probe_rows, 'seconds': round(time.time() - t0, 1),
    }
    return report


def write_csv(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['rule', 'id', 'family', 'root', 'runtime_x', 'runtime_y', 'runtime_z', 'gap_m', 'ground_mesh',
                    'intentional', 'reason', 'member_count', 'detail'])
        for r in report['findings']:
            x, y, z = r['at_runtime']
            detail = {k: r[k] for k in ('owner', 'fix', 'depth_m', 'overlap_m2', 'contact_gap_m', 'note', 'fixed_at_runtime') if k in r}
            w.writerow([r['rule'], r['id'], r['family'], r['root'], x, y, z, r['gap_m'], r['ground_mesh'],
                        r['intentional'], r['reason'], r['member_count'], json.dumps(detail) if detail else ''])
        for p in report['probes']:
            w.writerow(['probe', p.get('id'), p.get('family'), '', p.get('x'), p.get('bottom_y'), p.get('z'), p.get('gap_m'),
                        p.get('ground_mesh'), '', p.get('note', ''), 1, ''])


def preflight(objects=None, profile='city', fail_on=('L1', 'L2', 'L3', 'L5')):
    """Hook for export_helper: returns (passed, report)."""
    report = run_lint(profile, objects=objects, log=lambda *_a: None)
    bad = sum(report['defects'].get(r, 0) for r in fail_on)
    return bad == 0, report


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--profile', default='city', choices=sorted(PROFILES))
    ap.add_argument('--out', required=True)
    ap.add_argument('--csv')
    ap.add_argument('--probes')
    ap.add_argument('--fail-on', default='')
    args = ap.parse_args(argv)
    probes = json.loads(Path(args.probes).read_text(encoding='utf-8')) if args.probes else None
    report = run_lint(args.profile, probes=probes, log=lambda m: print('[lint]', m, flush=True))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    if args.csv:
        write_csv(report, args.csv)
    print(json.dumps({'defects': report['defects'], 'intentional': report['intentional'], 'seconds': report['seconds']}))
    fail = [r for r in args.fail_on.split(',') if r]
    if fail and any(report['defects'].get(r, 0) for r in fail):
        sys.exit(3)


if __name__ == '__main__':
    main()
