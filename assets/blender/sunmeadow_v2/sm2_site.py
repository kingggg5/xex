"""Sunmeadow v2 site model: every coordinate comes from the layout JSON (+ compact v1 for existing IDs).

Pure Python. Babylon XZ throughout (x east, z north). See sm2_geom for the Blender mapping.
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import sm2_geom as G

ROOT = Path(__file__).resolve().parents[3]
LAYOUT_PATH = ROOT / 'planning' / 'levels' / 'sunmeadow-v2-layout.json'
COMPACT_PATH = ROOT / 'planning' / 'sunmeadow-compact-v1.json'
ZONES_PATH = ROOT / 'content' / 'source' / 'zones.json'
MONSTERS_PATH = ROOT / 'planning' / 'levels' / 'sunmeadow-v2-monsters.json'

PATH_Y = {'gate_road': 0.010, 'gate_road_east': 0.011, 'southbound_trail': 0.012, 'boar_trail': 0.013,
          'east_return_path': 0.014, 'camp_spur': 0.016}
SIDE_WORDS = ('west', 'east', 'north', 'south')
BANK_W = 1.2          # bank drop 0 -> -0.35 within 1.2 m of the water edge
WATER_EDGE_BAND = (-0.2, 0.5)   # water-edge collider band, metres from the water edge (negative = in the water)
STONE_TRAIL_GAP = 1.5            # no circle stone within 1.5 m of the trail edge
PROP_PATH_GAP = 1.0              # props and scatter >= 1.0 m from path edges
WATER_GAP = 0.3                  # props and scatter >= 0.3 m from the water edge


def cell_of(x: float, z: float) -> str:
    return f'c{8 + math.floor(x / 64)}_r{8 + math.floor(z / 64)}'


@dataclass
class Item:
    id: str
    category: str              # tree | bush | rock | stone | prop | landmark | flower | reed | mushroom | fern
    species: str               # proxy kind, e.g. pine_L, broadleaf_M, boulder, standing_stone, cart
    x: float
    z: float
    yaw: float = 0.0
    scale: float = 1.0
    base_y: float = 0.0
    height: float = 0.0
    radius: float = 0.0        # footprint radius (trunk radius at 1 m for trees)
    canopy_r: float = 0.0
    params: dict = field(default_factory=dict)
    source: str = ''
    zone: str = ''
    collider: str | None = None    # 'capsule' | 'box' | None
    collider_r: float = 0.0
    collider_size: tuple = ()      # (sx, sz) for boxes, Babylon local X/Z
    collider_h: float = 0.0

    @property
    def cell(self) -> str:
        return cell_of(self.x, self.z)


class PathFeature:
    def __init__(self, spec):
        self.id = spec['id']
        self.width = float(spec['width_m'])
        self.hw = self.width / 2
        self.line = G.Polyline(spec['points'])
        self.y = PATH_Y.get(self.id, 0.012)
        self.surface = spec.get('surface', '')


class Site:
    """All derived layout geometry in Babylon coordinates."""

    def __init__(self, layout_path: Path = LAYOUT_PATH, compact_path: Path = COMPACT_PATH):
        self.layout_path, self.compact_path = Path(layout_path), Path(compact_path)
        self.L = json.loads(self.layout_path.read_text(encoding='utf-8'))
        self.C = json.loads(self.compact_path.read_text(encoding='utf-8'))
        L = self.L
        self.stage = L['bounds_xz']['stage']
        self.walk_hint = L['bounds_xz']['walkable_hint']
        self.anchors = {k: tuple(v) for k, v in L['anchors'].items()}
        self.clearings = {c['id']: c for c in L['clearings']}
        self.hazards = L.get('hazards', [])
        self.paths = {p['id']: PathFeature(p) for p in L['paths']}
        water = {w['id']: w for w in L['water']}
        s = water['sunmeadow_stream']
        self.stream = G.Polyline(s['points'])
        self.stream_w = tuple(float(v) for v in s['width_m'])
        self.water_y = float(s['surface_y'])
        self.stream_bed = float(s['bed_y'])
        p = water['falls_pool']
        self.pool = (float(p['center_xz'][0]), float(p['center_xz'][1]), float(p['radius_m']))
        self.pool_bed = float(p['bed_y'])
        self.falls = water['bluff_falls']
        b = L['bridges'][0]
        self.bridge = b
        self.bridge_c = (float(b['center_xz'][0]), float(b['center_xz'][1]))
        self.bridge_u = G.norm(tuple(b['along_xz']))
        self.bridge_n = G.left_normal(self.bridge_u)
        self.bridge_hl = float(b['length_m']) / 2
        self.bridge_hw = float(b['deck_width_m']) / 2
        self.relief = {r['id']: r for r in L['relief']}
        self.bluff_rect = tuple(float(v) for v in self.relief['inner_bluff']['footprint_xz'])
        self.landmarks = {m['id']: m for m in L['landmarks']}
        # Layout landmarks that move an existing compact v1 prop ("existing prop <id>, moved from ..."): the layout wins.
        self.prop_moves = {}
        for m in L['landmarks']:
            mm = re.search(r'existing prop (\w+)', m.get('note', ''))
            if mm and isinstance(m.get('position_xz'), list):
                self.prop_moves[mm.group(1)] = (float(m['position_xz'][0]), float(m['position_xz'][1]), m['id'])
        self.zones = {z['id']: z for z in L['vegetation_zones']}
        self.rock_specs = {r['id']: r for r in L['rock_clusters']}
        self.sightlines = L['sightlines']
        dep = self.C['dependencies']
        self.pois = {p['id']: (float(p['after']['x']), float(p['after']['z'])) for p in dep['pois']}
        self.spawns = [(m['enemy'], float(m['after_xz'][0]), float(m['after_xz'][1]), m['clearing_id'])
                       for m in dep['monsters']]
        self.existing_props = dep['props']
        self.town_wings = [c['after'] for c in dep['colliders'] if c['action'] == 'preserve-town-gate']
        self.zone_props = {}
        try:
            zones = json.loads(ZONES_PATH.read_text(encoding='utf-8'))
            for wp in zones['zones'][0]['world_props']:
                self.zone_props[wp['id']] = wp
        except Exception:
            pass
        self.content_pois = {}
        try:
            for poi in zones['zones'][0]['pois']:
                self.content_pois[poi['id']] = (poi['x'], poi['z'])
        except Exception:
            pass
        self.city_blockers = []
        try:
            for b in zones['zones'][0]['city_traversal']['blockers']:
                xs = [q[0] for q in b['polygon_xz']]
                zs = [q[1] for q in b['polygon_xz']]
                if max(xs) < self.stage[0] or min(xs) > self.stage[1] or max(zs) < self.stage[2] or min(zs) > self.stage[3]:
                    continue
                self.city_blockers.append(b)
        except Exception:
            pass
        # v2 monster plan (design proposal): homes, night/phase homes and patrols are scatter keep-clears.
        self.monster_homes, self.monster_patrols, self.monster_keep = [], [], []
        try:
            M = json.loads(MONSTERS_PATH.read_text(encoding='utf-8'))
            body = {r['id']: float(r.get('body_radius_m', 0.6)) for r in M['roster']}
            for r in M['spawn_rows']:
                br = body.get(r['enemy'], 0.6)
                homes = [r['home_xz']]
                if r.get('night_home_xz'):
                    homes.append(r['night_home_xz'])
                for ph in (r.get('phase_homes') or {}).values() if isinstance(r.get('phase_homes'), dict) else []:
                    if isinstance(ph, list) and len(ph) == 2 and all(isinstance(v, (int, float)) for v in ph):
                        homes.append(ph)
                for h in homes:
                    self.monster_homes.append((float(h[0]), float(h[1]), br, r['row'], r['enemy']))
                pat = r.get('patrol')
                if pat and pat.get('points'):
                    pts = [tuple(map(float, q)) for q in pat['points']]
                    segs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if pat.get('type') == 'loop' else [])
                    for a, b in segs:
                        self.monster_patrols.append((a, b, r['row']))
            for e in M['scatter_keep_clear']['explicit']:
                self.monster_keep.append((float(e['center_xz'][0]), float(e['center_xz'][1]), float(e['radius_m']), e['zone']))
            self.monsters_sha = __import__('hashlib').sha256(MONSTERS_PATH.read_bytes()).hexdigest()
        except FileNotFoundError:
            self.monsters_sha = None
        self.notes: list[str] = []

    # ------------------------------------------------------------------ water
    def stream_width_at(self, s: float) -> float:
        w0, w1 = self.stream_w
        return w0 + (w1 - w0) * max(0.0, min(1.0, s / self.stream.length))

    def stream_e(self, p, extended: bool = False) -> float:
        d, s, _ = self.stream.closest(p)
        e = d - self.stream_width_at(s) / 2
        if extended and p[0] < -62:
            # Render-only continuation beyond the stage edge (context, never exported or collided).
            ext = G.Polyline([self.stream.pts[-1], (-84.0, -65.0)])
            de, se, _ = ext.closest(p)
            e = min(e, de - self.stream_w[1] / 2)
        return e

    def pool_e(self, p) -> float:
        return math.hypot(p[0] - self.pool[0], p[1] - self.pool[1]) - self.pool[2]

    def water_e(self, p) -> float:
        return min(self.stream_e(p), self.pool_e(p))

    def bridge_local(self, p):
        d = G.sub(p, self.bridge_c)
        return G.dot(d, self.bridge_u), G.dot(d, self.bridge_n)

    def on_deck(self, p, margin=0.0) -> bool:
        a, l = self.bridge_local(p)
        return abs(a) <= self.bridge_hl + margin and abs(l) <= self.bridge_hw + margin

    @staticmethod
    def _bank_profile(e: float, bed: float, wall: float) -> float:
        if e >= BANK_W:
            return 0.0
        if e >= 0:
            return -0.35 * (1 - e / BANK_W) ** 2
        return -0.35 - (abs(bed) - 0.35) * G.smoothstep(0.0, wall, -e)

    def ground_h(self, p, extended: bool = False) -> float:
        """Visual ground height: Y=0 walk plane with the carved stream, pool and under-deck relief."""
        h = 0.0
        x, z = p
        if -86 <= x <= -4 and -70 <= z <= -32:
            h = min(h, self._bank_profile(self.stream_e(p, extended), self.stream_bed, 0.8),
                    self._bank_profile(self.pool_e(p), self.pool_bed, 1.0))
        if self.on_deck(p, 0.0):
            h = min(h, -0.03)
        return h

    def water_mask(self, p, extended: bool = False) -> float:
        """Negative where the water surface plane exists (slightly wider than the wet edge)."""
        return min(self.stream_e(p, extended), self.pool_e(p)) - 0.15

    # ------------------------------------------------------------------ paths
    def path_edge_gap(self, p, exclude=()) -> tuple[float, str]:
        """Distance from p to the nearest path edge (negative inside a path)."""
        best, best_id = 1e9, ''
        for pid, pf in self.paths.items():
            if pid in exclude:
                continue
            d = pf.line.distance(p) - pf.hw
            if d < best:
                best, best_id = d, pid
        return best, best_id

    def in_rect(self, p, rect, margin=0.0) -> bool:
        x0, x1, z0, z1 = rect
        return x0 - margin <= p[0] <= x1 + margin and z0 - margin <= p[1] <= z1 + margin

    def in_clearing(self, p, c, margin=0.0) -> bool:
        if 'radius_m' in c:
            cx, cz = c['center_xz']
            return math.hypot(p[0] - cx, p[1] - cz) <= float(c['radius_m']) + margin
        return self.in_rect(p, c['bounds_xz'], margin)

    def canal_rects(self):
        return [tuple(float(v) for v in h['bounds_xz']) for h in self.hazards if h.get('kind') == 'water']

    # ------------------------------------------------------------------ relief lines
    def cliff_runs(self):
        """West cliff face polyline split around the stream gap: list of point lists (north -> south)."""
        r = self.relief['west_cliffs']
        pts = [tuple(map(float, q)) for q in r['polyline_xz']]
        g0, g1 = sorted(r['gap']['between_z'], reverse=True)   # (-55, -63)
        runs, cur = [], [pts[0]]
        for a, b in zip(pts, pts[1:]):
            # walking south: z decreases
            hits = []
            for zg in (g0, g1):
                if (a[1] - zg) * (b[1] - zg) < 0:
                    t = (a[1] - zg) / (a[1] - b[1])
                    hits.append((t, (G.lerp(a[0], b[0], t), zg), zg))
            for t, q, zg in sorted(hits):
                if zg == g0:
                    cur.append(q)
                    runs.append(cur)
                    cur = None
                else:
                    cur = [q]
            if cur is not None:
                cur.append(b)
        if cur:
            runs.append(cur)
        return runs

    def hill_toe(self):
        return [tuple(map(float, q)) for q in self.relief['east_hills']['polyline_xz']]

    def forest_line(self):
        return [tuple(map(float, q)) for q in self.relief['south_forest_wall']['polyline_xz']]

    def gate_posts(self):
        posts = [p for p in self.existing_props if p['id'] in ('sunmeadow_stone_post_west_south', 'sunmeadow_stone_post_east_south')]
        return sorted([(float(p['after_xz'][0]), float(p['after_xz'][1])) for p in posts])

    def palisade_runs(self):
        """South palisade: west run, east run and the two wings that meet the gate posts."""
        line = self.forest_line()
        (wx, wz), (ex, ez) = self.gate_posts()
        west = [line[0], line[1]]
        east = [line[2], line[3]]
        wing_w = [line[1], (wx, wz)]
        wing_e = [(ex, ez), line[2]]
        return {'palisade_west': west, 'palisade_wing_west': wing_w, 'palisade_wing_east': wing_e,
                'palisade_east': east}

    # ------------------------------------------------------------------ misc
    def sightline_origins(self, frm: str):
        """Sightline origin -> [(id, xz)]: an anchor id, 'label [x,z]', a clearing id, or free text naming anchors
        without their side word ('city exit ramps (game camera, 13 m)' -> city_exit_ramp_west + city_exit_ramp_east)."""
        if frm in self.anchors:
            return [(frm, self.anchors[frm])]
        if '[' in frm:
            return [(frm, tuple(json.loads(frm[frm.index('['):frm.index(']') + 1])))]
        if frm in self.clearings:
            return [(frm, tuple(self.clearings[frm]['center_xz']))]
        text = frm.lower().replace('_', ' ')
        hits = []
        for k, v in self.anchors.items():
            stem = [w for w in k.split('_') if w not in SIDE_WORDS]
            if len(stem) >= 2 and ' '.join(stem) in text:
                hits.append((k, v))
        if not hits:
            raise KeyError(frm)
        return hits

    def sightline_points(self):
        """Resolve the four JSON sightlines to (from_xz, to_xz, to_height, label); from_points lists every origin
        (several when the origin names a pair of anchors), game_camera marks origins worded for the game camera."""
        out = []
        for sl in self.sightlines:
            frm, to = sl['from'], sl['to']
            pts = self.sightline_origins(frm)
            a = (sum(p[1][0] for p in pts) / len(pts), sum(p[1][1] for p in pts) / len(pts))
            if to in self.landmarks and isinstance(self.landmarks[to].get('position_xz'), list):
                b = tuple(self.landmarks[to]['position_xz'])
                h = float(self.landmarks[to].get('height_m', 6))
            elif to == 'bluff_falls':
                b, h = tuple(self.falls['top_xz']), float(self.falls['top_y'])
            elif to == 'inner_bluff':
                x0, x1, z0, z1 = self.bluff_rect
                b, h = ((x0 + x1) / 2, (z0 + z1) / 2), float(self.relief['inner_bluff']['height_m'])
            else:
                raise KeyError(to)
            out.append({'from': frm, 'to': to, 'from_xz': a, 'to_xz': b, 'to_h': h, 'intent': sl['intent'],
                        'from_points': pts, 'game_camera': 'game camera' in frm.lower()})
        return out
