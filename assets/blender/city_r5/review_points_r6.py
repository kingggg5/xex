"""Collect audit findings into annotation points for render_review_r6.py / annotate_review_r6.py.

  python assets/blender/city_r5/review_points_r6.py --lint <lint.json> --audit <audit.json> --out <points.json>
Each point: {id, kind, label, x, y, z} in RUNTIME coordinates.
Kinds: F floating, S sinking, O orphan child part, Z z-fighting, P path into building,
B route-blocking ring prop, D duplicate house module, E empty filler patch, T legacy starter prop.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lint', required=True)
    ap.add_argument('--audit', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    lint = json.loads(Path(a.lint).read_text(encoding='utf-8'))
    audit = json.loads(Path(a.audit).read_text(encoding='utf-8'))
    pts = []

    def add(kind, label, xyz):
        pts.append({'id': f'{kind}{len([p for p in pts if p["kind"] == kind]) + 1}', 'kind': kind, 'label': label,
                    'x': xyz[0], 'y': xyz[1], 'z': xyz[2]})

    for f in lint['findings']:
        if f['intentional']:
            continue
        if f['rule'] in ('L1', 'L5'):
            add('F', f"{f['family'][:28]} {f['gap_m'] if f['gap_m'] is not None else 'no ground'}", f['at_runtime'])
        elif f['rule'] == 'L2':
            add('S', f"{f['family'][:28]} {f.get('depth_m')}", f['at_runtime'])
        elif f['rule'] == 'L3':
            add('O', f"{f['family'][:28]}", f['at_runtime'])
        elif f['rule'] == 'L4' and f.get('overlap_m2', 0) >= 0.25:
            add('Z', f"{f['family'][:24]} {f['overlap_m2']} m2", f['at_runtime'])
    for p in lint.get('probes', []):
        gap = p['gap_m'] if p.get('in_city_rect') else p['bottom_y']
        if p['family'] == 'grass cone tuft':
            continue
        if gap is None or gap > 0.03:
            y = p['ground_y'] if p.get('ground_y') is not None else 0.0
            add('T', f"{p['family']} {gap if gap is not None else 'no ground'}", [p['x'], max(p['bottom_y'], y), p['z']])
    for h in audit.get('paths_into_buildings', []):
        add('P', f"{h['path']} -> {h['building_part'][:26]}", h['first_at'])
    for r in audit.get('ring_props_vs_avenues', []):
        if r['inside_avenue_band']:
            add('B', f"{r['object'][:22]} in {r['nearest_avenue']}", r['at'])
    for k in audit['houses']['kits']:
        if k['copies_of_module'] > 2:
            add('D', f"{k['root'][4:]} ({k['roof'][5:] if k['roof'] else ''})", [k['at'][0], 8.0, k['at'][2]])
    for e in audit['occupancy']['empty_patches'][:6]:
        c = e['centre_runtime']
        add('E', f"empty {int(e['area_m2'])} m2", [c[0], 0.5, c[2]])
    Path(a.out).write_text(json.dumps(pts, indent=1) + '\n', encoding='utf-8')
    kinds = {}
    for p in pts:
        kinds[p['kind']] = kinds.get(p['kind'], 0) + 1
    print(json.dumps(kinds))


if __name__ == '__main__':
    main()
