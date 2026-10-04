"""Bottom heights of the code-placed starter-field props (apps/client/src/environment.ts).

Pure Python (no Blender): replays the environment's seeded LCG in its exact call order
(createSky -> createGroundAndPath -> createTrees -> createMeadowDressing) and writes a
probe list in RUNTIME coordinates for lint_placement.py --probes. Points inside the
authored city rectangle (|x| <= 124, 8 <= z <= 304) must be sampled against the city
master's ground; the rest stand on the flat Y = 0 meadow (env-meadow / cells).

  python assets/blender/city_r5/starter_field_probes_r6.py --out planning/evidence/map-dressing-20261002/starter-probes.json

Source constants were read from environment.ts on 2026-10-02 (rng seed 20260925,
FIELD_LIMIT 27, PATH_HALF_WIDTH 3.2, STREAM_Z 19, STREAM_HALF_WIDTH 2.4, CASTLE_Z_START 31).
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIELD_LIMIT, PATH_HALF_WIDTH, STREAM_Z, STREAM_HALF_WIDTH, CASTLE_Z_START = 27, 3.2, 19, 2.4, 31
TREE_SPOTS = [(-18, 5, 7), (18, 7, 8), (-20, 17, 8), (20, 21, 9), (-25, 30, 9), (-12, 35, 7), (14, 35, 8), (27, 31, 9),
              (-22, -6, 7), (22, -4, 8), (-8, 40, 9), (9, 42, 8)]


class LCG:
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def __call__(self):
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.s / 4294967296.0


def quat_ypr(yaw, pitch, roll):
    hr, hp, hy = roll * 0.5, pitch * 0.5, yaw * 0.5
    sr, cr, sp, cp, sy, cy = math.sin(hr), math.cos(hr), math.sin(hp), math.cos(hp), math.sin(hy), math.cos(hy)
    x = cy * sp * cr + sy * cp * sr
    y = sy * cp * cr - cy * sp * sr
    z = cy * cp * sr - sy * sp * cr
    w = cy * cp * cr + sy * sp * sr
    return x, y, z, w


def rot_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def y_half_extent(radius, scale, rot):
    R = rot_matrix(quat_ypr(rot[1], rot[0], rot[2]))
    return math.sqrt(sum((scale[i] * radius * R[1][i]) ** 2 for i in range(3)))


def glb_min_y(path):
    data = path.read_bytes()
    jlen = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + jlen])
    ys = [doc['accessors'][p['attributes']['POSITION']]['min'][1] for m in doc['meshes'] for p in m['primitives']]
    return min(ys)


def meadow_spot(rng, spread):
    x = (rng() * 2 - 1) * FIELD_LIMIT * spread
    z = -9 + rng() * 42
    if abs(x) < PATH_HALF_WIDTH and -6 < z < 34:
        return None
    if abs(z - STREAM_Z) < STREAM_HALF_WIDTH + 0.6:
        return None
    if z > CASTLE_Z_START:
        return None
    return x, z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    rng = LCG(20260925)
    probes = []

    def add(pid, fam, x, z, bottom, note=''):
        probes.append({'id': pid, 'family': fam, 'x': round(x, 4), 'z': round(z, 4), 'bottom_y': round(bottom, 4),
                       'in_city_rect': abs(x) <= 124 and 8 <= z <= 304, 'note': note})

    # createSky: 16 clouds
    for cloud in range(16):
        rng(); rng(); rng()
        puffs = 5 + math.floor(rng() * 3)
        for _ in range(puffs):
            rng(); rng(); rng(); rng()
    # createGroundAndPath: 26 path stones (sphere d 0.5, uniform scale, flat shaded)
    for i in range(26):
        side = -1 if rng() < 0.5 else 1
        z = -6 + rng() * 40
        x = side * (PATH_HALF_WIDTH + 0.5 + rng() * 1.2)
        y = 0.1 + rng() * 0.05
        rng(); rng()
        s = 0.5 + rng() * 0.9
        add(f'env-path-stone-{i}', 'env-path-stone', x, z, y - 0.25 * s, f'sphere r {0.25 * s:.3f}')
    # createTrees: crowns consume the RNG; trunk bottoms sit at Y 0
    for idx, (x, z, h) in enumerate(TREE_SPOTS):
        crowns = 3 + math.floor(rng() * 3)
        for _ in range(crowns):
            for _k in range(6):
                rng()
        add(f'env-tree-trunk-{idx}', 'TREE_SPOTS trunk', x, z, 0.0, f'height {h} m')
    # Kenney foliage (no RNG)
    kb = ROOT / 'apps/client/src/assets/foliage/kenney'
    bush_min = glb_min_y(kb / 'plant_bushDetailed.glb')
    rock_min = [glb_min_y(kb / 'rock_largeA.glb'), glb_min_y(kb / 'rock_largeB.glb')]
    for i, (x, z) in enumerate([(-9, 11), (9, 12), (-8, 27), (10, 29), (-14, 38), (15, 39)]):
        s = 2.4 + (i % 3) * 0.35
        add(f'kenney-bush-{i}', 'kenney bush', x, z, 0 + bush_min * s, f'scale {s:.2f}')
    for i, (x, z) in enumerate([(-8, 8), (8, 9), (-9, 21), (9, 24), (-13, 33), (13, 35)]):
        s = 1.7 + (i % 3) * 0.25
        add(f'kenney-rock-{i % 2}-{i}', 'kenney rock', x, z, 0.15 + rock_min[i % 2] * s, f'scale {s:.2f}, placed at y 0.15')
    # Fences (no RNG): posts h 1.15 at y 0.56
    zf = -4.0
    while zf < 12:
        for side in (-1, 1):
            add(f'env-fence-post-{side}-{zf:.1f}', 'starter fence post', side * (5.3 + math.sin(zf * 0.2) * 0.4), zf, 0.56 - 0.575)
        zf += 1.9
    # createMeadowDressing: 720 spots (tufts and flowers), then 26 rocks
    tufts_float = 0
    for index in range(720):
        bloom = index % 3 == 2
        spot = meadow_spot(rng, 0.5 if bloom else 1)
        if spot is None:
            continue
        if bloom:
            continue  # stems are 0.38 m tall at y 0.19: bottom exactly 0
        h0 = 0.62 if index % 2 == 0 else 0.52
        for t in range(3):
            bx = spot[0] + (rng() - 0.5) * 0.24
            bz = spot[1] + (rng() - 0.5) * 0.24
            rng()
            rng(); sy = 0.65 + rng() * 0.75; rng()
            bottom = 0.24 - h0 * sy * 0.5
            if bottom > 0.03:
                tufts_float += 1
            add(f'env-blade-{index}-{t}', 'grass cone tuft', bx, bz, bottom)
    for index in range(26):
        spot = meadow_spot(rng, 1)
        if spot is None:
            continue
        y = 0.2 + rng() * 0.1
        rot = (rng() * math.pi, rng() * math.pi, rng() * math.pi)
        sc = (0.6 + rng() * 1.1, 0.5 + rng() * 0.6, 0.6 + rng() * 1.1)
        ext = y_half_extent(0.55, sc, rot)
        add(f'env-rock-{index}', 'egg rock', spot[0], spot[1], y - ext, f'centre y {y:.3f}, half height {ext:.3f}')
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(probes, indent=1) + '\n', encoding='utf-8')
    fam = {}
    for p in probes:
        fam.setdefault(p['family'], 0)
        fam[p['family']] += 1
    print(json.dumps({'probes': len(probes), 'families': fam, 'tufts_floating_over_3cm_on_flat_ground': tufts_float,
                      'kenney_min_y': {'bush': bush_min, 'rockA': rock_min[0], 'rockB': rock_min[1]}}))


if __name__ == '__main__':
    main()
