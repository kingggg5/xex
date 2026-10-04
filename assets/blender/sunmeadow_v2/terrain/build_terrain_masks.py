"""Script 3: per-cell terrain splat and data maps (terrain spec §3.4, §3.5, §4.1; §6 script 3).

Sources (one set per run, written to <out>/<set>/):
  --source live  content/source/zones.json routes and props (Pass 1 data: live c7/c8 cells)
  --source v2    planning/levels/sunmeadow-v2-layout.json + the pass-5 blockout colliders/instances
  --source lab   assets/blender/sunmeadow_v2/terrain/terrain-lab-layout.json (terrain lab cell)

Per cell: <cell>_splat_{257,129}.png (RGB8 linear: R lush, G dry, B dirt; mud = 255 - R - G - B),
<cell>_terrain_{257,129}.png (RGB8 linear: R path-edge SDF, G rut lateral, B ground AO),
<cell>_mask-preview.png (labelled MASK PREVIEW), and the set receipt masks-receipt-<set>.json.

Every input is a deterministic function of world XZ, so texels on a shared border are bit-identical.
Relief inputs (slope, aspect, cav, top-down Cycles AO) come from script 2, which waits for the forms pass;
until then v2/live use slope = 0 and an analytic AO proxy (trunks, props, stones, relief), recorded in the
receipt. The lab cell has an analytic relief (hill), so its slope and aspect rules are exercised.

Usage: python assets/blender/sunmeadow_v2/terrain/build_terrain_masks.py --source v2 [--cells c7_r7] [--no-preview]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import terrain_png  # noqa: E402
import terrain_spec as TS  # noqa: E402

ROOT = TS.ROOT
SEED = TS.SEED
MASK = TS.MASK
VAL = TS.VALIDATION
LAYOUT = 'planning/levels/sunmeadow-v2-layout.json'
ZONES = 'content/source/zones.json'
BLOCKOUT = 'assets/models/sunmeadow-v2/blockout'
LAB_LAYOUT = 'assets/blender/sunmeadow_v2/terrain/terrain-lab-layout.json'


# ----------------------------------------------------------------------------
# Deterministic world-space noise (hash lattice; identical in every cell)
# ----------------------------------------------------------------------------
_M32 = np.uint64(0xffffffff)


def _hash01(ix: np.ndarray, iz: np.ndarray, seed: int) -> np.ndarray:
    h = ((ix.astype(np.int64) & 0xffffffff).astype(np.uint64) * np.uint64(0x9E3779B1)) & _M32
    h ^= (((iz.astype(np.int64) & 0xffffffff).astype(np.uint64) + np.uint64(seed & 0xffffffff)) * np.uint64(0x85EBCA77)) & _M32
    h ^= h >> np.uint64(15)
    h = (h * np.uint64(0x2C1B3C6D)) & _M32
    h ^= h >> np.uint64(12)
    h = (h * np.uint64(0x297A2D39)) & _M32
    h ^= h >> np.uint64(15)
    return h.astype(np.float64) / 4294967295.0


def vnoise(x: np.ndarray, z: np.ndarray, scale: float, seed: int) -> np.ndarray:
    """Value noise in [0, 1] with feature size `scale` metres (quintic interpolation)."""
    u, v = x / scale, z / scale
    iu, iv = np.floor(u), np.floor(v)
    fu, fv = u - iu, v - iv
    fu = fu * fu * fu * (fu * (fu * 6 - 15) + 10)
    fv = fv * fv * fv * (fv * (fv * 6 - 15) + 10)
    a = _hash01(iu, iv, seed)
    b = _hash01(iu + 1, iv, seed)
    c = _hash01(iu, iv + 1, seed)
    d = _hash01(iu + 1, iv + 1, seed)
    return (a + (b - a) * fu) + ((c + (d - c) * fu) - (a + (b - a) * fu)) * fv


def fbm(x, z, scale, seed, octaves=4):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total = total + amp * vnoise(x, z, scale / (2 ** o), seed + 101 * o)
        norm += amp
        amp *= 0.5
    return total / norm


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def normal_cdf(z: np.ndarray) -> np.ndarray:
    """Phi(z) via Abramowitz-Stegun 7.1.26 erf (|error| < 1.5e-7); numpy only, deterministic."""
    x = np.abs(z) / math.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * x)
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = 1.0 - poly * np.exp(-x * x)
    return 0.5 * (1.0 + np.sign(z) * erf)


# ----------------------------------------------------------------------------
# Geometry
# ----------------------------------------------------------------------------

def polyline_fields(px, pz, pts):
    """Distance to an open polyline, signed lateral offset (+ = left of travel) and arc length at the foot."""
    best = np.full(px.shape, np.inf)
    side = np.zeros(px.shape)
    arc = np.zeros(px.shape)
    total = 0.0
    for (ax, az), (bx, bz) in zip(pts[:-1], pts[1:]):
        dx, dz = bx - ax, bz - az
        length = math.hypot(dx, dz)
        if length < 1e-9:
            continue
        t = np.clip(((px - ax) * dx + (pz - az) * dz) / (length * length), 0.0, 1.0)
        qx, qz = ax + t * dx, az + t * dz
        dist = np.hypot(px - qx, pz - qz)
        cross = dx * (pz - az) - dz * (px - ax)
        closer = dist < best
        best = np.where(closer, dist, best)
        side = np.where(closer, np.sign(cross) + (cross == 0), side)
        arc = np.where(closer, total + t * length, arc)
        total += length
    return best, side, arc, total


def polygon_sdf(px, pz, poly):
    """Signed distance to a simple polygon (negative inside)."""
    pts = list(poly)
    d = np.full(px.shape, np.inf)
    inside = np.zeros(px.shape, bool)
    for (ax, az), (bx, bz) in zip(pts, pts[1:] + pts[:1]):
        dx, dz = bx - ax, bz - az
        ll = dx * dx + dz * dz
        t = np.clip(((px - ax) * dx + (pz - az) * dz) / max(ll, 1e-12), 0, 1)
        d = np.minimum(d, np.hypot(px - (ax + t * dx), pz - (az + t * dz)))
        cond = ((az > pz) != (bz > pz)) & (px < (bx - ax) * (pz - az) / np.where(bz - az == 0, 1e-12, bz - az) + ax)
        inside ^= cond
    return np.where(inside, -d, d)


# ----------------------------------------------------------------------------
# Site descriptions (sources)
# ----------------------------------------------------------------------------

class Site:
    def __init__(self, name):
        self.name = name
        self.paths = []        # dict(id, cls, width, pts)
        self.water = []        # dict(kind, pts, widths | centre, radius)
        self.bridges = []      # dict(centre, along, length)
        self.relief = []       # dict(id, kind, poly) collider footprints (toe bands, AO)
        self.stones = []       # (x, z, r) stone bases
        self.trunks = []       # (x, z, r)
        self.canopies = []     # (x, z, R)
        self.props = []        # (x, z, r) AO only
        self.bushes = []       # (x, z, r)
        self.rocks = []        # (x, z, r)
        self.clearings = []    # (id, minx, maxx, minz, maxz) combat calm
        self.camp = None       # (minx, maxx, minz, maxz)
        self.altar = None      # (x, z, r)
        self.spray = []        # (x, z)
        self.wallow = []       # (x, z, r)
        self.hills = []        # analytic relief (lab): (x, z, R, H)
        self.cells = []        # dict(id, bounds)
        self.authored = set()  # cell ids with an authored neighbour set
        self.sources = {}      # path -> sha256
        self.notes = []


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    """Repo-relative POSIX path; absolute for outputs outside the repo (scratch runs)."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def collider_circle(c):
    if c['shape'] == 'capsule':
        return (c['center'][0], c['center'][2], c.get('radius', c['size'][0] / 2))
    poly = c['polygon_xz']
    cx = sum(p[0] for p in poly) / len(poly)
    cz = sum(p[1] for p in poly) / len(poly)
    r = max(math.hypot(p[0] - cx, p[1] - cz) for p in poly)
    return (cx, cz, r * 0.8)


def load_v2() -> Site:
    site = Site('v2')
    layout_path = ROOT / LAYOUT
    layout = json.loads(layout_path.read_text(encoding='utf-8'))
    cols_path = ROOT / BLOCKOUT / 'colliders.json'
    inst_path = ROOT / BLOCKOUT / 'instances.json'
    cells_path = ROOT / BLOCKOUT / 'cells.json'
    colliders = json.loads(cols_path.read_text(encoding='utf-8'))['colliders']
    instances = json.loads(inst_path.read_text(encoding='utf-8'))['instances']
    cells = json.loads(cells_path.read_text(encoding='utf-8'))['cells']
    site.sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in (layout_path, cols_path, inst_path, cells_path)}
    for p in layout['paths']:
        site.paths.append(dict(id=p['id'], cls=TS.PATH_CLASS_OF[p['id']], width=p['width_m'], pts=[tuple(q) for q in p['points']]))
    for w in layout['water']:
        if w['kind'] == 'stream':
            site.water.append(dict(kind='stream', pts=[tuple(q) for q in w['points']], widths=tuple(w['width_m'])))
        elif w['kind'] == 'pool':
            site.water.append(dict(kind='pool', centre=tuple(w['center_xz']), radius=w['radius_m']))
        elif w['kind'] == 'waterfall':
            site.spray.append(tuple(w['top_xz']))
    for b in layout['bridges']:
        along = np.array(b['along_xz'], float)
        site.bridges.append(dict(centre=tuple(b['center_xz']), along=tuple(along / np.linalg.norm(along)), length=b['length_m']))
    for c in layout['clearings']:
        if c['id'] in ('windmark_hunt', 'windstone_glade'):
            site.clearings.append((c['id'], *c['bounds_xz']))
        if c['id'] == 'oak_wallow':
            site.wallow.append((c['center_xz'][0], c['center_xz'][1], 3.6))
    for lm in layout['landmarks']:
        if lm['id'] == 'hunter_camp':
            site.camp = tuple(lm['bounds_xz'])
        if lm['id'] == 'windstone_altar':
            site.altar = (lm['position_xz'][0], lm['position_xz'][1], lm['radius_m'])
    for c in colliders:
        cat = c['category']
        if cat == 'relief':
            kind = 'bluff' if 'bluff' in c['id'] else 'cliff' if 'cliff' in c['id'] else 'hill' if 'hill' in c['id'] else 'wall'
            site.relief.append(dict(id=c['id'], kind=kind, poly=[tuple(p) for p in c['polygon_xz']]))
        elif cat == 'stone':
            site.stones.append(collider_circle(c))
        elif cat == 'trunk':
            site.trunks.append(collider_circle(c))
        elif cat in ('camp', 'prop', 'landmark', 'bridge'):
            site.props.append(collider_circle(c))
        elif cat == 'bush_existing':
            site.bushes.append(collider_circle(c))
        elif cat == 'rock':
            site.rocks.append(collider_circle(c))
    for it in instances:
        x, z = it['position_xz']
        if it['category'] == 'tree':
            site.canopies.append((x, z, it.get('canopy_radius_m', 2.0)))
        elif it['category'] == 'bush':
            site.bushes.append((x, z, it.get('canopy_radius_m', it.get('footprint_radius_m', 0.8))))
    for key in cells:
        cid = f'sunmeadow_{key}'
        site.cells.append(dict(id=cid, bounds=TS.cell_bounds(cid)))
    site.notes.append('relief slope/aspect/cav and Cycles AO: script 2 deferred to the forms pass; slope = 0, analytic AO proxy')
    site.notes.append('boar_trail and gate_road_east are v2 layout paths without a spec class row; classes in terrain_spec.PATH_CLASSES')
    site.notes.append('oak_wallow mud patch (layout: "mud wallow") is an explicit mud exception zone')
    return site


def load_live() -> Site:
    site = Site('live')
    zones_path = ROOT / ZONES
    zone = json.loads(zones_path.read_text(encoding='utf-8'))['zones'][0]
    site.sources = {zones_path.relative_to(ROOT).as_posix(): sha(zones_path)}
    for r in zone['world_routes']:
        site.paths.append(dict(id=r['id'], cls=TS.PATH_CLASS_OF.get(r['id'], 'southbound_trail'), width=r['width'],
                               pts=[tuple(q) for q in r['points']]))
    for p in zone['world_props']:
        x, z = p['x'], p['z']
        kind = p['kind']
        if kind.startswith('tree'):
            site.trunks.append((x, z, 0.32 * p.get('scale', 1)))
            site.canopies.append((x, z, 0.28 * p['height'] * p.get('scale', 1)))
        elif kind == 'bush':
            site.bushes.append((x, z, 0.75 * p.get('scale', 1)))
        elif kind in ('stone_pillar', 'trail_marker'):
            site.stones.append((x, z, p['collider_size'][0] / 2))
        else:
            site.props.append((x, z, max(p['collider_size'][0], p['collider_size'][2]) / 2))
    for c in zone['terrain_cells']:
        site.cells.append(dict(id=c['id'], bounds=tuple(c['bounds_xz'])))
    site.notes.append('Pass 1 data source (spec §3.1): zones.json routes and props; no water, relief or clearings in c7/c8')
    site.notes.append('north border z = -64 neighbours the legacy starter_field (not authored): blended to the far default')
    return site


def load_lab() -> Site:
    site = Site('lab')
    path = ROOT / LAB_LAYOUT
    lab = json.loads(path.read_text(encoding='utf-8'))
    site.sources = {path.relative_to(ROOT).as_posix(): sha(path)}
    for p in lab['paths']:
        site.paths.append(dict(id=p['id'], cls=TS.PATH_CLASS_OF[p['id']], width=p['width_m'], pts=[tuple(q) for q in p['points']]))
    for w in lab['water']:
        site.water.append(dict(kind='stream', pts=[tuple(q) for q in w['points']], widths=tuple(w['width_m'])))
    for b in lab['bridges']:
        along = np.array(b['along_xz'], float)
        site.bridges.append(dict(centre=tuple(b['center_xz']), along=tuple(along / np.linalg.norm(along)), length=b['length_m']))
    for r in lab['relief']:
        if r['kind'] == 'hill':
            cx, cz = r['center_xz']
            site.hills.append((cx, cz, r['radius_m'], r['height_m']))
            ring = [(cx + r['toe_radius_m'] * math.cos(a), cz + r['toe_radius_m'] * math.sin(a))
                    for a in np.linspace(0, math.tau, 24, endpoint=False)]
            site.relief.append(dict(id=r['id'], kind='hill', poly=ring))
        else:
            site.relief.append(dict(id=r['id'], kind=r['kind'], poly=[tuple(p) for p in r['polygon_xz']]))
    for r in lab['rocks']:
        site.rocks.append((r['center_xz'][0], r['center_xz'][1], r['radius_m']))
        if r['kind'] == 'boulder':
            site.stones.append((r['center_xz'][0], r['center_xz'][1], r['radius_m']))
    for t in lab['trees']:
        x, z = t['position_xz']
        site.trunks.append((x, z, t['trunk_radius_m']))
        site.canopies.append((x, z, t['canopy_radius_m']))
    b = lab['cell']['bounds_xz']
    site.cells.append(dict(id=lab['cell']['id'], bounds=tuple(b)))
    site.notes.append('lab relief: analytic hill (slope and aspect rules active); cliff as a collider footprint')
    return site


# ----------------------------------------------------------------------------
# Field computation (spec §3.5 rules 1-7)
# ----------------------------------------------------------------------------

def hill_height(site: Site, x, z):
    h = np.zeros_like(x)
    for cx, cz, R, H in site.hills:
        r = np.hypot(x - cx, z - cz)
        h = np.maximum(h, np.where(r < R, H * 0.5 * (1 + np.cos(np.pi * np.clip(r / R, 0, 1))), 0.0))
    return h


def compute(site: Site, x: np.ndarray, z: np.ndarray, authored_bounds) -> dict:
    """All §3.5 inputs and rules on a world grid (x, z arrays of equal shape)."""
    F = {}
    n1 = vnoise(x, z, MASK['edge_noise_m'], SEED + 7)
    jitter = MASK['edge_noise_amp'] * (2 * n1 - 1)
    # Macro M: 0.65 fBm(p/32) + 0.35 fBm(p/12), domain-warped by 6 m
    wx = x + MASK['macro_warp_m'] * (2 * fbm(x, z, 24.0, SEED + 11, 3) - 1)
    wz = z + MASK['macro_warp_m'] * (2 * fbm(x + 37.1, z - 11.7, 24.0, SEED + 13, 3) - 1)
    M = MASK['macro_weights'][0] * fbm(wx, wz, MASK['macro_scales_m'][0], SEED + 17) + \
        MASK['macro_weights'][1] * fbm(wx, wz, MASK['macro_scales_m'][1], SEED + 19)
    # Normalise with the field's world statistics (fBm of value noise clusters at 0.48 +- 0.10). P1 fix: the old
    # fixed 3x stretch clipped 10.6 % of the stage to exactly 0 / 1, which smoothstep turned into flat 0 / 0.55
    # dry plateaus with crisp edges (the mask "blotches"); Phi keeps every gradient and is still a pure function
    # of world XZ, so shared borders stay bit-identical.
    M = normal_cdf((M - MASK['macro_mean']) / MASK['macro_std'])
    F['macro'] = M
    # Relief (analytic in the lab; script 2 later)
    h = hill_height(site, x, z)
    step = 0.25
    hx = (hill_height(site, x + step, z) - hill_height(site, x - step, z)) / (2 * step)
    hz = (hill_height(site, x, z + step) - hill_height(site, x, z - step)) / (2 * step)
    slope = np.degrees(np.arctan(np.hypot(hx, hz)))
    nx, nz = -hx, -hz
    nlen = np.sqrt(nx * nx + nz * nz + 1.0)
    aspect = np.maximum(0.0, (nx * TS.SUN_XZ[0] + nz * TS.SUN_XZ[1]) / nlen)
    lap = (hill_height(site, x + 2, z) + hill_height(site, x - 2, z) + hill_height(site, x, z + 2) + hill_height(site, x, z - 2) - 4 * h) / 4.0
    concave = smoothstep(0.05, 0.4, lap)
    convex = smoothstep(0.05, 0.4, -lap)
    F['slope'], F['aspect'] = slope, aspect
    # Paths: SDF to the nearest edge, class, lateral rut coordinate
    d_path = np.full(x.shape, 99.0)
    cls_idx = np.full(x.shape, -1)
    rut_l = np.full(x.shape, np.nan)
    d_by_path = []
    for i, p in enumerate(site.paths):
        dist, side, _arc, _ = polyline_fields(x, z, p['pts'])
        d = dist - p['width'] / 2
        d_by_path.append(d)
        closer = d < d_path
        d_path = np.where(closer, d, d_path)
        cls_idx = np.where(closer, i, cls_idx)
        cls = TS.PATH_CLASSES[p['cls']]
        if cls.get('ruts') and p['id'] not in TS.PATH_NO_RUTS:
            lat = side * dist
            rut_l = np.where(closer & (dist <= 2.9), lat, np.where(closer, np.nan, rut_l))
    # junctions: path endpoints lying on another path; ruts fade (sentinel) within 3 m
    junctions = []
    for i, p in enumerate(site.paths):
        for end in (p['pts'][0], p['pts'][-1]):
            for j, q in enumerate(site.paths):
                if i == j:
                    continue
                dist, _, _, _ = polyline_fields(np.array([end[0]]), np.array([end[1]]), q['pts'])
                if dist[0] < q['width'] / 2 + 0.5:
                    junctions.append(end)
    for jx, jz in junctions:
        rut_l = np.where(np.hypot(x - jx, z - jz) < TS.RUT['junction_fade_m'], np.nan, rut_l)
    F['sdf'], F['cls'], F['rut'], F['junctions'] = d_path, cls_idx, rut_l, junctions
    # Rule 1: path dirt, worn dry band, inner tufts / trampled dry
    D_path = np.zeros(x.shape)
    worn = np.zeros(x.shape)
    inner_dry = np.zeros(x.shape)
    path_mud = np.zeros(x.shape)
    for i, (p, d) in enumerate(zip(site.paths, d_by_path)):
        c = TS.PATH_CLASSES[p['cls']]
        dj = d + jitter
        Dp = c['s_c'] * (1 - smoothstep(-0.30, c['e_c'], dj))
        if c.get('track_m'):
            # a single worn track (1.4 m) with grass verges inside the 2.5 m path
            dist_c = d + p['width'] / 2
            Dp = np.maximum(Dp * 0.55, c['s_c'] * (1 - smoothstep(c['track_m'] / 2 - 0.2, c['track_m'] / 2 + 0.25, dist_c + 0.6 * jitter)))
        D_path = np.maximum(D_path, Dp)
        band = smoothstep(-0.2, c['worn_peak_m'], dj) * (1 - smoothstep(c['worn_peak_m'], c['worn_end_m'], dj))
        worn = np.maximum(worn, c['worn'] * band)
        if c.get('inner_dry'):
            inner_dry = np.maximum(inner_dry, c['inner_dry'] * (1 - smoothstep(-0.1, 0.3, d)))
        if c.get('mud'):
            path_mud = np.maximum(path_mud, c['mud'] * (1 - smoothstep(-0.4, 0.4, dj)) * (0.6 + 0.4 * vnoise(x, z, 1.1, SEED + 23)))
    # southbound trail: grass tufts inside the inner 0.4 m (weight 0.2-0.4, height-gated at runtime)
    tufts = np.zeros(x.shape)
    for i, (p, d) in enumerate(zip(site.paths, d_by_path)):
        c = TS.PATH_CLASSES[p['cls']]
        if c.get('tufts_inner_m'):
            lo, hi = c['tufts_weight']
            gate = smoothstep(0.55, 0.8, vnoise(x, z, 0.45, SEED + 29))
            # only where this trail is the nearest path: at a junction its inner tuft band must not cut into another
            # path's core (fixture test: gate_road core dirt fell to 0.73 at the southbound junction)
            tufts = np.maximum(tufts, (lo + (hi - lo) * vnoise(x, z, 0.9, SEED + 31)) * gate * (cls_idx == i) *
                               smoothstep(-c['tufts_inner_m'], -c['tufts_inner_m'] + 0.15, d) * (1 - smoothstep(-0.12, 0.0, d)))
    # Water
    d_water = np.full(x.shape, 99.0)
    for w in site.water:
        if w['kind'] == 'stream':
            dist, _, arc, total = polyline_fields(x, z, w['pts'])
            width = w['widths'][0] + (w['widths'][1] - w['widths'][0]) * np.clip(arc / max(total, 1e-6), 0, 1)
            d_water = np.minimum(d_water, dist - width / 2)
        else:
            d_water = np.minimum(d_water, np.hypot(x - w['centre'][0], z - w['centre'][1]) - w['radius'])
    F['d_water'] = d_water
    bridge_zone = np.zeros(x.shape, bool)
    bridge_centre_zone = np.zeros(x.shape, bool)
    for b in site.bridges:
        cx, cz = b['centre']
        ax, az = b['along']
        for s in (-1, 1):
            ex, ez = cx + s * ax * b['length'] / 2, cz + s * az * b['length'] / 2
            bridge_zone |= np.hypot(x - ex, z - ez) <= MASK['bridge_apron_m']
        bridge_centre_zone |= np.hypot(x - cx, z - cz) <= VAL['bridge_exempt_m']
    F['bridge_zone'] = bridge_zone | bridge_centre_zone
    # Relief toe bands and collider SDFs
    d_relief = np.full(x.shape, 99.0)
    toe = np.zeros(x.shape)
    relief_sdfs = []
    for r in site.relief:
        sd = polygon_sdf(x, z, r['poly'])
        relief_sdfs.append(sd)
        d_relief = np.minimum(d_relief, sd)
        if r['kind'] in ('bluff', 'cliff', 'hill'):
            lo, hi = MASK['toe_band_m']
            toe = np.maximum(toe, (1 - smoothstep(lo, hi, sd + 0.25 * (2 * n1 - 1))) * (sd > -0.3))
    F['d_relief'], F['toe'] = d_relief, toe
    # AO proxy (until script 2's top-down Cycles AO): multiplicative contact occlusion
    ao = np.ones(x.shape)

    def occlude(items, amount, reach):
        nonlocal ao
        for cx, cz, rr in items:
            dd = np.maximum(0.0, np.hypot(x - cx, z - cz) - rr)
            near = dd < reach * 3
            if near.any():
                ao = np.where(near, ao * (1 - amount * np.exp(-(dd / reach) ** 2)), ao)

    occlude(site.trunks, 0.30, 0.9)
    occlude(site.stones, 0.32, 0.8)
    occlude(site.rocks, 0.30, 0.8)
    occlude(site.props, 0.25, 0.7)
    occlude(site.bushes, 0.22, 0.8)
    for r, sd in zip(site.relief, relief_sdfs):
        # hills are smooth ground surfaces (no rock/ground contact): a mild toe term; the concave term adds the rest
        amount, reach = (0.48, 2.0) if r['kind'] in ('bluff', 'cliff') else (0.15, 1.6) if r['kind'] == 'hill' else (0.25, 0.8)
        # Contact occlusion is a band at the toe. P1 fix: max(sd, 0) gave the full amount everywhere inside the
        # footprint, so a walkable hill (a ground surface under open sky, §5.4) became one dark AO disc (0.64,
        # -27 % albedo at runtime). Inside, the occlusion now fades out within 0.6 m of the edge.
        inner = np.where(sd < 0, 1 - smoothstep(0.0, 0.6, -sd), 1.0)
        ao = ao * (1 - amount * inner * np.exp(-(np.maximum(sd, 0) / reach) ** 2))
    canopy = np.zeros(x.shape)
    for cx, cz, R in site.canopies:
        dd = np.hypot(x - cx, z - cz)
        near = dd < R + MASK['canopy_fade_m'] + 0.5
        if near.any():
            canopy = np.where(near, np.maximum(canopy, 1 - smoothstep(0.5 * R, R + MASK['canopy_fade_m'], dd)), canopy)
    ao = np.clip(ao * (1 - 0.12 * canopy) * (1 - 0.18 * concave), 0.35, 1.0)
    F['ao'], F['canopy'] = ao, canopy
    # Rule 2: other dirt
    D_other = np.zeros(x.shape)
    lo, hi, val = MASK['dirt_slope']
    # erosion scars (§5.4): the slope band is broken by 2.5 m noise, so a round hill gets scars, not a bullseye ring
    scar = smoothstep(*MASK['slope_scar_edges'], fbm(x, z, MASK['slope_scar_m'], SEED + 43, 2))
    D_other = np.maximum(D_other, val * smoothstep(lo - 2, lo, slope) * (1 - smoothstep(hi, hi + 4, slope)) * scar)
    D_other = np.maximum(D_other, MASK['scree_toe'] * toe)
    # stone bases (r + 0.9 m -> 0.5): P1 lab pass 1 showed round "pancakes"; a 1.6 m noise breaks the outline
    # (+-0.45 m) and the amount (0.75-1.0x) so bases read as irregular trampled patches, same reach and peak
    base_shape = 0.45 * (2 * vnoise(x, z, 1.6, SEED + 53) - 1) + 0.2 * (2 * n1 - 1)
    base_amount = 0.75 + 0.25 * vnoise(x, z, 2.3, SEED + 59)
    for cx, cz, rr in site.stones:
        reach = rr + MASK['stone_base_extra_m']
        D_other = np.maximum(D_other, MASK['stone_base_dirt'] * base_amount * (1 - smoothstep(reach - 0.35, reach + 0.25, np.hypot(x - cx, z - cz) + base_shape)))
    if site.altar:
        cx, cz, rr = site.altar
        reach = rr + MASK['altar_apron_m']
        D_other = np.maximum(D_other, MASK['altar_apron_dirt'] * (1 - smoothstep(reach - 0.3, reach + 0.3, np.hypot(x - cx, z - cz) + 0.2 * (2 * n1 - 1))))
    if site.camp:
        x0, x1, z0, z1 = site.camp
        inside = smoothstep(x0 - 1, x0 + 1, x) * (1 - smoothstep(x1 - 1, x1 + 1, x)) * smoothstep(z0 - 1, z0 + 1, z) * (1 - smoothstep(z1 - 1, z1 + 1, z))
        a, b = MASK['camp_noise']
        D_other = np.maximum(D_other, MASK['camp_patch'] * smoothstep(a, b, vnoise(x, z, 1.6, SEED + 37)) * inside)
    D = np.maximum(D_path, D_other)
    # Rule 3: mud / moss
    a, b = MASK['bank']
    # edge noise tapers toward the waterline so the 0.4 m bank strip stays mud (validation 4); organic further out
    bank = 1 - smoothstep(a, b, d_water + MASK['bank_noise'] * (2 * n1 - 1) * smoothstep(0.0, 1.2, d_water))
    bank = np.maximum(bank, MASK['bank_slope_mud'] * (slope > MASK['bank_slope_deg']) * (d_water < MASK['bank_slope_reach_m']))
    spray = np.zeros(x.shape)
    for sx, sz in site.spray:
        r0, r1 = MASK['spray_r']
        spray = np.maximum(spray, MASK['spray'] * (1 - smoothstep(r0, r1, np.hypot(x - sx, z - sz))))
    shade = np.where(ao < MASK['shade_ao'], MASK['shade_moss'] * (MASK['shade_ao'] - ao) / MASK['shade_ao'], 0.0)
    wallow = np.zeros(x.shape)
    for cx, cz, rr in site.wallow:
        wallow = np.maximum(wallow, 0.58 * (1 - smoothstep(rr * 0.55, rr, np.hypot(x - cx, z - cz) + 0.6 * (2 * vnoise(x, z, 1.3, SEED + 41) - 1))))
    # toe bands next to water become wet moss (water > bands: dirt is clamped there, the blocker stays visible)
    toe_wet = 0.6 * toe * (1 - smoothstep(1.5, 2.5, d_water))
    Mu = np.maximum.reduce([bank, spray, shade, wallow, path_mud, toe_wet])
    F['spray'], F['shade'], F['wallow'], F['toe_wet'], F['path_mud'] = spray, shade, wallow, toe_wet, path_mud
    # Rule 4: dry share
    lo, hi = MASK['dry_macro']
    b_m, b_amp = MASK['dry_breath']
    breath = 1 + b_amp * (2 * fbm(x, z, b_m, SEED + 47, 2) - 1)   # no flat plateau inside a dry patch
    dry = smoothstep(lo, hi, M) * (MASK['dry_aspect'][0] + MASK['dry_aspect'][1] * aspect) * breath
    s_lo, s_hi, s_val = MASK['dry_slope']
    dry = dry + s_val * smoothstep(s_lo - 2, s_lo, slope) * (1 - smoothstep(s_hi, s_hi + 4, slope)) * smoothstep(0.1, 0.5, aspect)
    dry = dry + worn + MASK['dry_convex'] * convex
    lb0, lb1 = MASK['lush_band_m']
    lush_band = smoothstep(lb0 - 0.5, lb0, d_water) * (1 - smoothstep(lb1, lb1 + 0.5, d_water))
    dry = dry * (1 - MASK['lush_suppress'] * np.maximum.reduce([canopy, lush_band, 1 - ao, concave]))
    dry = np.maximum(dry, inner_dry)
    dry = np.clip(dry, 0, 1)
    # Rule 5: combine (water > paths > bands > macro)
    mud = np.clip(Mu, 0, 1)
    on_land_bridge = F['bridge_zone'] & (d_water > 0)
    dirt = np.where(on_land_bridge, D, D * (1 - MASK['mud_dirt_suppress'] * mud))
    near_water = (d_water < VAL['water_dirt_reach_m'])
    dirt = np.where(near_water & ~on_land_bridge, np.minimum(dirt, VAL['water_dirt_max'] - 0.01), dirt)
    dirt = np.clip(dirt, 0, 1)
    mud = np.where(on_land_bridge, np.minimum(mud, 1 - dirt), mud)
    # southbound inner tufts take share from dirt (grass sprigs at the inner edge)
    dirt = dirt * (1 - tufts)
    # Rule 6: combat calm inside the clearings (minus paths)
    # soft-edged (4 m) so the clamp never draws the clearing rectangle into the ground
    calm = np.zeros(x.shape)
    for _id, x0, x1, z0, z1 in site.clearings:
        calm = np.maximum(calm, smoothstep(x0 - 4, x0, x) * (1 - smoothstep(x1, x1 + 4, x)) *
                          smoothstep(z0 - 4, z0, z) * (1 - smoothstep(z1, z1 + 4, z)))
    calm = calm * smoothstep(0.3, 1.0, d_path)
    # paths and collider toe bands keep their dirt (no invisible walls outranks clearing readability)
    calm_dirt = np.minimum(dirt, np.where((D_path > 0.05) | (toe > 0.05), dirt, MASK['combat_dirt_max']))
    dirt = dirt + (calm_dirt - dirt) * calm
    dry = dry + (np.clip(dry, *MASK['combat_dry']) - dry) * calm
    F['calm'] = calm > 0.999
    # every §3.5 intermediate, for --dump-terms (labelled MASK PREVIEW term sheets)
    F['terms'] = {'1 path dirt D_path': D_path, '2 other dirt D_other': D_other, '3 mud/moss Mu': Mu, '3c shade moss': shade,
                  'macro M': M, '4 dry share': dry, 'canopy': canopy, 'AO proxy': ao, '5 dirt (combined)': dirt,
                  '5 mud (combined)': mud, '6 combat calm': calm}
    rem = np.maximum(0, 1 - mud - dirt)
    lush = rem * (1 - dry)
    dry_w = rem * dry
    # Rule 7: outer borders without an authored neighbour blend to the far default over 4 m
    fade = np.zeros(x.shape)
    for (bx0, bx1, bz0, bz1), sides in authored_bounds:
        for side in sides:
            if side == 'w':
                fade = np.maximum(fade, 1 - smoothstep(0, MASK['border_blend_m'], x - bx0))
            if side == 'e':
                fade = np.maximum(fade, 1 - smoothstep(0, MASK['border_blend_m'], bx1 - x))
            if side == 's':
                fade = np.maximum(fade, 1 - smoothstep(0, MASK['border_blend_m'], z - bz0))
            if side == 'n':
                fade = np.maximum(fade, 1 - smoothstep(0, MASK['border_blend_m'], bz1 - z))
    fl, fd = MASK['border_default']
    lush = lush * (1 - fade) + fl * fade
    dry_w = dry_w * (1 - fade) + fd * fade
    dirt = dirt * (1 - fade)
    mud = mud * (1 - fade)
    total = np.maximum(1e-9, lush + dry_w + dirt + mud)
    F['w'] = np.stack([lush, dry_w, dirt, mud], -1) / total[..., None]
    F['fade'] = fade
    F['terms']['7 outer border fade'] = fade
    F['D_path'] = D_path
    return F


# ----------------------------------------------------------------------------
# Encoding
# ----------------------------------------------------------------------------

def quantise(w: np.ndarray) -> np.ndarray:
    """Largest-remainder rounding of 4 weights to bytes summing to exactly 255; returns RGB (mud implied)."""
    scaled = w * 255.0
    base = np.floor(scaled).astype(np.int32)
    rem = scaled - base
    short = 255 - base.sum(-1)
    order = np.argsort(-rem, axis=-1, kind='stable')
    rank = np.argsort(order, axis=-1, kind='stable')
    base = base + (rank < short[..., None]).astype(np.int32)
    assert np.all(base.sum(-1) == 255)
    return base[..., :3].astype(np.uint8)


def encode_data(sdf, rut, ao) -> np.ndarray:
    r = np.clip(np.rint((sdf - TS.SDF_MIN_M) / TS.SDF_RANGE_M * 255.0), 0, 255)
    g = np.where(np.isnan(rut), TS.RUT_SENTINEL, np.clip(np.rint((np.nan_to_num(rut) - TS.RUT_MIN_M) / TS.RUT_RANGE_M * 254.0), 0, 254))
    b = np.clip(np.rint(ao * 255.0), 0, 255)
    return np.stack([r, g, b], -1).astype(np.uint8)


def filt121(a: np.ndarray) -> np.ndarray:
    """[1,2,1]/4 separable low-pass on an extended grid (interior only is valid)."""
    out = a.copy()
    out[:, 1:-1] = (a[:, :-2] + 2 * a[:, 1:-1] + a[:, 2:]) / 4
    out2 = out.copy()
    out2[1:-1] = (out[:-2] + 2 * out[1:-1] + out[2:]) / 4
    return out2


# ----------------------------------------------------------------------------
# Validation (spec §3.5 checks 1-8) and coverage
# ----------------------------------------------------------------------------

LAYER_MEAN_LUM = None


def layer_mean_lum():
    """Layer mean luminance for check 6: from the forge manifest if present, else the palette base."""
    global LAYER_MEAN_LUM
    if LAYER_MEAN_LUM is None:
        manifest = ROOT / TS.LAYER_SOURCE_DIR / 'forge-manifest.json'
        vals = []
        data = json.loads(manifest.read_text(encoding='utf-8'))['layers'] if manifest.exists() else {}
        for layer in TS.LAYERS:
            rec = data.get(layer['id'])
            if rec:
                vals.append(rec['stats']['albedo']['lum_mean'])
            else:
                v = layer['palette']['base'][0].lstrip('#')
                rgb = [int(v[i:i + 2], 16) / 255 for i in (0, 2, 4)]
                vals.append(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
        LAYER_MEAN_LUM = np.array(vals)
    return LAYER_MEAN_LUM


def box_mean(a: np.ndarray, k: int) -> np.ndarray:
    pad = k // 2
    p = np.pad(a, pad, mode='edge')
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def validate(site: Site, cell: dict, F: dict, splat: np.ndarray, data: np.ndarray, x, z) -> list:
    checks = []

    def check(name, ok, value, limit, note=''):
        checks.append(dict(check=name, pass_=bool(ok), value=value, limit=limit, note=note))

    w = splat.astype(np.int32)
    mud = 255 - w.sum(-1)
    live = F['fade'] < 1e-6   # rule 7 border blend has priority; checks 2-4, 7 skip that 4 m strip
    check('1 R+G+B<=255, mud exact', bool((w.sum(-1) <= 255).all() and (mud >= 0).all()), int(w.sum(-1).max()), 255)
    dirt = w[..., 2] / 255.0
    mudw = mud / 255.0
    sdf = F['sdf']
    # 2: path cores
    for i, p in enumerate(site.paths):
        sel = (F['cls'] == i) & (sdf <= VAL['dirt_core_d']) & live
        sel &= ~(F['d_water'] < VAL['water_dirt_reach_m'] + 0.5)  # water has priority over paths (rule priority)
        if not sel.any():
            continue
        need = VAL['dirt_core'] if p['id'] in VAL['dirt_core_paths'] else VAL['dirt_min'].get(p['cls'], VAL['dirt_min'].get(p['id']))
        if need is None:
            need = TS.PATH_CLASSES[p['cls']]['dirt_min_core']
        if TS.PATH_CLASSES[p['cls']].get('track_m'):
            dist_c = sdf + p['width'] / 2
            sel &= dist_c <= TS.PATH_CLASSES[p['cls']]['track_m'] / 2 - 0.3
        vmin = float(dirt[sel].min()) if sel.any() else None
        frac = float((dirt[sel] >= need - 1e-9).mean()) if sel.any() else None
        check(f'2 dirt core {p["id"]} (d<=-0.4)', vmin is None or frac >= 0.995, dict(min=vmin, frac_ok=frac), f'>= {need}')
    # 3: no dirt near water except the bridge
    near = (F['d_water'] >= 0) & (F['d_water'] < VAL['water_dirt_reach_m']) & ~F['bridge_zone'] & live
    if near.any():
        check('3 no dirt>0.2 within 1.5 m of water (bridge approach exempt)', float(dirt[near].max()) <= VAL['water_dirt_max'] + 1e-9,
              float(dirt[near].max()), VAL['water_dirt_max'], 'exemption = 3.5 m around the bridge centre and each deck end (rule 5)')
    # 4: banks
    bank = (F['d_water'] >= 0) & (F['d_water'] <= VAL['bank_mud_reach_m']) & ~F['bridge_zone'] & live
    if bank.any():
        check('4a mud>=0.6 within 0.4 m of water', float(np.percentile(mudw[bank], 1)) >= VAL['bank_mud_min'] - 1e-9,
              float(np.percentile(mudw[bank], 1)), VAL['bank_mud_min'], 'p1 over bank texels')
    far = (F['d_water'] > VAL['far_mud_reach_m']) & (F['spray'] < 0.01) & (F['shade'] < 0.01) & (F['wallow'] < 0.01) & (F['toe_wet'] < 0.01) & live
    far &= F['path_mud'] < 0.01   # trampled mud trails (boar_trail) are authored mud
    check('4b mud<=0.15 beyond 2.5 m from water (spray/shade/wallow/mud-trail exempt)', float(mudw[far].max()) <= VAL['far_mud_max'] + 1e-9 if far.any() else True,
          float(mudw[far].max()) if far.any() else None, VAL['far_mud_max'])
    # 6: combat calm albedo variation
    if F['calm'].any():
        lum = (np.stack([w[..., 0], w[..., 1], w[..., 2], mud], -1) / 255.0 * layer_mean_lum()).sum(-1)
        band = box_mean(lum, 5) - box_mean(lum, 17)   # 1.25 m vs 4.25 m windows at 0.25 m texels
        val = float(band[F['calm']].std())
        check('6 combat clearing albedo std (1-4 m band)', val <= MASK['combat_std_max'], val, MASK['combat_std_max'])
    # 7: toe bands
    for r in site.relief:
        if r['kind'] not in ('bluff', 'cliff', 'hill'):
            continue
        samples, ok = 0, 0
        pts = r['poly']
        for (ax, az), (bx, bz) in zip(pts, pts[1:] + pts[:1]):
            length = math.hypot(bx - ax, bz - az)
            if length < 1e-6:
                continue
            nx, nz = (bz - az) / length, -(bx - ax) / length   # outward for CCW
            mx, mz = (ax + bx) / 2, (az + bz) / 2
            if polygon_sdf(np.array([mx + nx * 0.5]), np.array([mz + nz * 0.5]), pts)[0] < 0:
                nx, nz = -nx, -nz
            for t in np.arange(0.125, length, 0.25):
                for off in (0.3, 0.6):
                    px_ = ax + (bx - ax) * t / length + nx * off
                    pz_ = az + (bz - az) * t / length + nz * off
                    b0, b1, c0, c1 = cell['bounds']
                    if not (b0 + 0.5 <= px_ <= b1 - 0.5 and c0 + 0.5 <= pz_ <= c1 - 0.5):
                        continue
                    pxa, pza = np.array([px_]), np.array([pz_])
                    if any(polygon_sdf(pxa, pza, o['poly'])[0] < 0 for o in site.relief if o is not r):
                        continue
                    stage = TS_STAGE.get(site.name)
                    if stage and not (stage[0] <= px_ <= stage[1] and stage[2] <= pz_ <= stage[3]):
                        continue
                    i = int(round((px_ - x[0, 0]) / (x[0, 1] - x[0, 0])))
                    j = int(round((pz_ - z[0, 0]) / (z[1, 0] - z[0, 0])))
                    if 0 <= j < w.shape[0] and 0 <= i < w.shape[1] and live[j, i]:
                        samples += 1
                        ok += (dirt[j, i] + mudw[j, i]) >= VAL['toe_band_min']
        if samples:
            check(f'7 toe band {r["id"]}', ok / samples >= VAL['toe_coverage_min'], round(ok / samples, 4), VAL['toe_coverage_min'],
                  f'{samples} samples at 0.3/0.6 m outside the walkable-facing edges')
    # 8: SDF decode error inside +-2 m
    dec = data[..., 0] / 255.0 * TS.SDF_RANGE_M + TS.SDF_MIN_M
    sel = np.abs(sdf) <= VAL['sdf_err_reach_m']
    if sel.any():
        err = float(np.abs(dec[sel] - sdf[sel]).max())
        check('8 SDF decode error inside +-2 m', err <= VAL['sdf_err_max_m'], round(err, 5), VAL['sdf_err_max_m'])
    return checks


TS_STAGE = {'v2': (-64.0, 64.0, -110.0, 24.0)}


def edge_irregularity(site: Site, F: dict, x, z, splat) -> dict:
    """Std of the 50 % dirt iso-line position along each path (spec §4.2), sampled every 0.5 m, both sides."""
    out = {}
    dirt = splat[..., 2] / 255.0
    step = x[0, 1] - x[0, 0]
    for p in site.paths:
        offs = []
        pts = p['pts']
        for (ax, az), (bx, bz) in zip(pts[:-1], pts[1:]):
            length = math.hypot(bx - ax, bz - az)
            tx, tz = (bx - ax) / length, (bz - az) / length
            nx, nz = -tz, tx
            for t in np.arange(1.0, length - 1.0, 0.5):
                cx, cz = ax + tx * t, az + tz * t
                for s in (-1, 1):
                    prev = None
                    for k in np.arange(-0.6, 1.4, 0.05):
                        o = p['width'] / 2 + k
                        px_, pz_ = cx + s * nx * o, cz + s * nz * o
                        i = (px_ - x[0, 0]) / step
                        j = (pz_ - z[0, 0]) / (z[1, 0] - z[0, 0])
                        if not (0 <= i < dirt.shape[1] - 1 and 0 <= j < dirt.shape[0] - 1):
                            prev = None
                            break
                        i0, j0 = int(i), int(j)
                        fi, fj = i - i0, j - j0
                        v = (dirt[j0, i0] * (1 - fi) * (1 - fj) + dirt[j0, i0 + 1] * fi * (1 - fj) +
                             dirt[j0 + 1, i0] * (1 - fi) * fj + dirt[j0 + 1, i0 + 1] * fi * fj)
                        if prev is not None and prev >= 0.5 > v:
                            offs.append(k)
                            break
                        prev = v
        if len(offs) > 8:
            out[p['id']] = dict(std_m=round(float(np.std(offs)), 4), mean_m=round(float(np.mean(offs)), 4), samples=len(offs))
    return out


# ----------------------------------------------------------------------------
# Preview (MASK PREVIEW, never presented as a render)
# ----------------------------------------------------------------------------

COLOURS = np.array([[0.30, 0.52, 0.20], [0.80, 0.74, 0.32], [0.74, 0.56, 0.36], [0.24, 0.20, 0.13]])


def preview(cell: dict, F: dict, splat, data, path: Path, title_extra=''):
    from PIL import Image, ImageDraw
    w = np.concatenate([splat.astype(np.float64), (255 - splat.astype(np.int32).sum(-1))[..., None]], -1) / 255.0
    rgb = (w[..., :, None] * COLOURS[None, None]).sum(2)
    sdf = data[..., 0] / 255.0 * TS.SDF_RANGE_M + TS.SDF_MIN_M
    rgb = np.where((np.abs(sdf) < 0.06)[..., None], [0.95, 0.95, 0.95], rgb)
    rut = data[..., 1]
    rut_l = rut / 254.0 * TS.RUT_RANGE_M + TS.RUT_MIN_M
    rgb = np.where(((rut < 255) & (np.abs(np.abs(rut_l) - TS.RUT['centre_m']) < 0.08))[..., None], [0.45, 0.30, 0.18], rgb)
    rgb = rgb * (0.55 + 0.45 * data[..., 2:3] / 255.0)
    if 'd_water' in F:
        rgb = np.where((F['d_water'] < 0)[..., None], rgb * 0.6 + np.array([0.10, 0.25, 0.40]), rgb)
    img = Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)).resize((514, 514), Image.NEAREST)
    canvas = Image.new('RGB', (514, 560), (16, 20, 26))
    canvas.paste(img, (0, 46))
    g = ImageDraw.Draw(canvas)
    b = cell['bounds']
    g.text((6, 4), f'MASK PREVIEW (not a render) - {cell["id"]} {title_extra}', fill=(242, 199, 110))
    g.text((6, 18), f'x {b[0]:g}..{b[1]:g}  z {b[2]:g}..{b[3]:g}  north up  0.25 m/texel  257x257', fill=(200, 210, 220))
    g.text((6, 32), 'green lush / yellow dry / tan dirt / dark mud-moss; white = path edge; brown = rut lines; shade = AO', fill=(160, 170, 180))
    canvas.save(path)


def dump_terms(cell: dict, terms: dict, final_rgb_path: Path | None, path: Path, set_name: str) -> dict:
    """Labelled MASK PREVIEW sheet of every §3.5 term for one cell (0..1 grey, north up) plus per-term statistics.

    The band statistic is the std of a 1-4 m band-pass (texel 0.25 m): round spots and rectangles from a term show
    up as a high band std relative to the term's own std."""
    from PIL import Image, ImageDraw
    names = list(terms)
    cols, panel, label_h = 4, 257, 16
    rows = (len(names) + 1 + cols - 1) // cols
    canvas = Image.new('RGB', (cols * panel, 40 + rows * (panel + label_h)), (16, 20, 26))
    g = ImageDraw.Draw(canvas)
    b = cell['bounds']
    g.text((6, 4), f'MASK PREVIEW (term sheet, not a render) - {cell["id"]} [{set_name}]', fill=(242, 199, 110))
    g.text((6, 20), f'x {b[0]:g}..{b[1]:g}  z {b[2]:g}..{b[3]:g}  north up, 0.25 m/texel; grey 0..1 per term (spec §3.5 rules 1-7)',
           fill=(200, 210, 220))
    stats = {}
    for k, name in enumerate(names):
        a = np.clip(np.asarray(terms[name], np.float64), 0, 1)
        band = box_mean(a, 5) - box_mean(a, 17)
        stats[name] = dict(mean=round(float(a.mean()), 4), std=round(float(a.std()), 4), band_1_4m_std=round(float(band.std()), 4),
                           max=round(float(a.max()), 4))
        img = Image.fromarray((a * 255).astype(np.uint8)).convert('RGB')
        x0, y0 = (k % cols) * panel, 40 + (k // cols) * (panel + label_h)
        canvas.paste(img, (x0, y0 + label_h))
        g.text((x0 + 4, y0 + 2), f'{name}  (mean {a.mean():.2f})', fill=(220, 226, 232))
    if final_rgb_path and final_rgb_path.exists():
        k = len(names)
        x0, y0 = (k % cols) * panel, 40 + (k // cols) * (panel + label_h)
        fin = Image.open(final_rgb_path).convert('RGB').crop((0, 46, 514, 560)).resize((panel, panel), Image.NEAREST)
        canvas.paste(fin, (x0, y0 + label_h))
        g.text((x0 + 4, y0 + 2), 'final weights (mask preview colours)', fill=(220, 226, 232))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return stats


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def cell_grid(bounds, n: int, apron: int = 1):
    min_x, max_x, min_z, max_z = bounds
    step = (max_x - min_x) / n
    i = np.arange(-apron, n + 1 + apron)
    xs = min_x + i * step
    zs = max_z - i * step   # row 0 = north (z = maxZ); PNG row 0 = north, loaded with invertY = true
    return np.meshgrid(xs, zs)


def authored_sides(site: Site, cell: dict) -> list:
    b = cell['bounds']
    others = [c['bounds'] for c in site.cells if c is not cell]
    sides = []
    for side, probe in (('w', (b[0] - 1, (b[2] + b[3]) / 2)), ('e', (b[1] + 1, (b[2] + b[3]) / 2)),
                        ('s', ((b[0] + b[1]) / 2, b[2] - 1)), ('n', ((b[0] + b[1]) / 2, b[3] + 1))):
        if not any(o[0] <= probe[0] <= o[1] and o[2] <= probe[1] <= o[3] for o in others):
            sides.append(side)
    return [(b, sides)]


def build(site: Site, out: Path, only: list[str], previews: bool, terms_dir: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    borders = {}
    stage_acc = np.zeros(4)
    stage_n = 0
    for cell in site.cells:
        short = cell['id'].replace('sunmeadow_', '')
        if only and short not in only and cell['id'] not in only:
            continue
        t0 = time.time()
        rec = dict(id=cell['id'], bounds=list(cell['bounds']))
        for n in (TS.CELL_N['high'],):
            X, Z = cell_grid(cell['bounds'], n)
            F = compute(site, X, Z, authored_sides(site, cell))
            inner = (slice(1, -1), slice(1, -1))
            w257 = F['w'][inner]
            splat = quantise(w257)
            data = encode_data(F['sdf'][inner], F['rut'][inner], F['ao'][inner])
            # 129 derived from the same world field: [1,2,1] low-pass on the apron grid, even texels
            wf = np.stack([filt121(F['w'][..., k]) for k in range(4)], -1)[inner][::2, ::2]
            wf = wf / wf.sum(-1, keepdims=True)
            splat129 = quantise(wf)
            sdf129 = filt121(F['sdf'])[inner][::2, ::2]
            ao129 = filt121(F['ao'])[inner][::2, ::2]
            data129 = encode_data(sdf129, F['rut'][inner][::2, ::2], ao129)
            Fi = {k: (v[inner] if isinstance(v, np.ndarray) and v.shape[:2] == X.shape else v) for k, v in F.items()}
            checks = validate(site, cell, Fi, splat, data, X[inner], Z[inner])
            files = {}
            for kind, arr in (('splat_257', splat), ('terrain_257', data), ('splat_129', splat129), ('terrain_129', data129)):
                p = out / f'{cell["id"]}_{kind}.png'
                terrain_png.write_png(p, arr)
                bad = [c for c in terrain_png.chunks(p) if c in TS.FORBIDDEN_PNG_CHUNKS]
                if bad:
                    raise SystemExit(f'{p} carries forbidden chunks {bad}')
                files[kind] = dict(path=rel(p), bytes=p.stat().st_size, sha256=sha(p),
                                   size=list(arr.shape[:2]))
            wv = np.concatenate([splat.astype(np.int32), (255 - splat.astype(np.int32).sum(-1))[..., None]], -1) / 255.0
            cov = wv.mean((0, 1))
            rec.update(files=files, checks=checks, coverage=dict(lush=round(float(cov[0]), 4), dry=round(float(cov[1]), 4),
                                                                  dirt=round(float(cov[2]), 4), mud=round(float(cov[3]), 4)),
                       edge_irregularity=edge_irregularity(site, Fi, X[inner], Z[inner], splat),
                       junctions=[list(j) for j in F['junctions']], seconds=0.0)
            stage = TS_STAGE.get(site.name)
            if stage:
                xi, zi = X[inner], Z[inner]
                sel = (xi >= stage[0]) & (xi <= stage[1]) & (zi >= stage[2]) & (zi <= stage[3])
                stage_acc += wv[sel].sum(0)
                stage_n += int(sel.sum())
            borders[cell['id']] = dict(bounds=cell['bounds'], splat=splat, data=data, splat129=splat129, data129=data129)
            pv = out / f'{cell["id"]}_mask-preview.png'
            if previews:
                preview(cell, Fi, splat, data, pv, f'[{site.name}]')
                rec['preview'] = rel(pv)
            if terms_dir is not None:
                tp = terms_dir / f'{site.name}_{cell["id"]}_terms.png'
                rec['term_stats'] = dump_terms(cell, {k: v[inner] for k, v in F['terms'].items()}, pv if previews else None,
                                               tp, site.name)
                rec['term_sheet'] = rel(tp)
        rec['seconds'] = round(time.time() - t0, 1)
        rec['pass'] = all(c['pass_'] for c in rec['checks'])
        results[cell['id']] = rec
        fails = [c for c in rec['checks'] if not c['pass_']]
        print(f"MASKS {site.name} {cell['id']}: {'PASS' if not fails else 'FAIL'} coverage {rec['coverage']} "
              f"{rec['seconds']} s", flush=True)
        for c in fails:
            print(f"   FAIL {c['check']}: {c['value']} (limit {c['limit']})")
    # 5: shared borders bit-identical
    border_checks = []
    ids = list(borders)
    for a in ids:
        for b in ids:
            if a >= b:
                continue
            A, B = borders[a], borders[b]
            ab, bb = A['bounds'], B['bounds']
            pairs = []
            if ab[1] == bb[0] and ab[2] == bb[2]:
                pairs.append(('east-west', lambda m: m[:, -1], lambda m: m[:, 0]))
            if bb[1] == ab[0] and ab[2] == bb[2]:
                pairs.append(('west-east', lambda m: m[:, 0], lambda m: m[:, -1]))
            if ab[3] == bb[2] and ab[0] == bb[0]:
                pairs.append(('north-south', lambda m: m[0], lambda m: m[-1]))
            if bb[3] == ab[2] and ab[0] == bb[0]:
                pairs.append(('south-north', lambda m: m[-1], lambda m: m[0]))
            for name, fa, fb in pairs:
                same = all(np.array_equal(fa(A[k]), fb(B[k])) for k in ('splat', 'data', 'splat129', 'data129'))
                border_checks.append(dict(check=f'5 border {a}|{b} ({name})', pass_=bool(same)))
                if not same:
                    print(f'   FAIL border {a}|{b} {name}')
    summary = dict(cells=len(results), pass_cells=sum(1 for r in results.values() if r['pass']),
                   border_checks=border_checks, borders_pass=all(c['pass_'] for c in border_checks))
    if stage_n:
        cov = stage_acc / stage_n
        exp = TS.STAGE_COVERAGE_EXPECT
        summary['stage_coverage'] = dict(lush=round(float(cov[0]), 4), dry=round(float(cov[1]), 4), dirt=round(float(cov[2]), 4),
                                         mud=round(float(cov[3]), 4))
        summary['stage_coverage_expected'] = exp
        summary['stage_coverage_in_range'] = {k: exp[k][0] <= summary['stage_coverage'][k] <= exp[k][1] for k in exp}
    return dict(cells=results, summary=summary)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', choices=('live', 'v2', 'lab'), required=True)
    ap.add_argument('--out', default=str(ROOT / TS.CELL_SOURCE_DIR))
    ap.add_argument('--cells', default='')
    ap.add_argument('--no-preview', action='store_true')
    ap.add_argument('--receipt', default=str(ROOT / TS.EVIDENCE_DIR))
    ap.add_argument('--dump-terms', action='store_true', help='write labelled per-term MASK PREVIEW sheets (evidence/mask-terms)')
    args = ap.parse_args(argv)
    t0 = time.time()
    site = {'live': load_live, 'v2': load_v2, 'lab': load_lab}[args.source]()
    out = Path(args.out) / site.name
    only = [c for c in args.cells.split(',') if c]
    terms_dir = Path(args.receipt) / 'mask-terms' if args.dump_terms else None
    result = build(site, out, only, not args.no_preview, terms_dir)
    receipt = dict(schema='xexoria.terrain-masks-receipt/1', script='assets/blender/sunmeadow_v2/terrain/build_terrain_masks.py',
                   spec=TS.SPEC_DOC, source=site.name, inputs=site.sources, notes=site.notes, seed=SEED,
                   parameters=dict(mask=MASK, validation=VAL, path_classes={k: TS.PATH_CLASSES[k] for k in sorted({p['cls'] for p in site.paths})},
                                   cell_n=TS.CELL_N, encodings=dict(sdf=[TS.SDF_MIN_M, TS.SDF_RANGE_M], rut=[TS.RUT_MIN_M, TS.RUT_RANGE_M, TS.RUT_SENTINEL])),
                   relief_source='analytic lab hill' if site.name == 'lab' else 'none: script 2 deferred (forms pass); slope = 0, AO proxy',
                   seconds=round(time.time() - t0, 1), **result)
    rdir = Path(args.receipt)
    rdir.mkdir(parents=True, exist_ok=True)
    rpath = rdir / f'masks-receipt-{site.name}.json'

    def clean(o):
        if isinstance(o, dict):
            return {('pass' if k == 'pass_' else k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return o
    rpath.write_text(json.dumps(clean(receipt), indent=1) + '\n', encoding='utf-8')
    s = result['summary']
    print(f"MASKS {site.name}: {s['pass_cells']}/{s['cells']} cells pass, borders {'PASS' if s['borders_pass'] else 'FAIL'} "
          f"({len(s['border_checks'])} shared edges); receipt {rel(rpath)}")
    if 'stage_coverage' in s:
        print(f"   stage coverage {s['stage_coverage']} in range {s['stage_coverage_in_range']}")
    return 0 if s['pass_cells'] == s['cells'] and s['borders_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
