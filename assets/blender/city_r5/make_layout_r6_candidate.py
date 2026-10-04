"""Write assets/blender/city_r5/layout-r6-candidate.json: a copy of the canonical layout.json
with the R6 map-dressing changes (cuts, re-routed paths, district identities, dressing clusters)
and the ordered "r6_dressing" operations consumed by build_city_r6_candidate.py.

The canonical layout.json and every R5 candidate stay untouched.
  python assets/blender/city_r5/make_layout_r6_candidate.py
Blender/layout coordinates: x east, y north, fountain at the origin (runtime z = 176 + y).
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / 'layout.json'
OUT = HERE / 'layout-r6-candidate.json'


def polar(r, deg):
    a = math.radians(deg)
    return [round(r * math.cos(a), 3), round(r * math.sin(a), 3)]


def avenue_point(to, t, s):
    L = math.hypot(*to)
    u = (to[0] / L, to[1] / L)
    n = (-u[1], u[0])
    return [round(t * u[0] + s * n[0], 3), round(t * u[1] + s * n[1], 3)]


def main():
    base = json.loads(SRC.read_text(encoding='utf-8'))
    lay = copy.deepcopy(base)
    lay['revision'] = 'r6-candidate'
    lay['derived_from'] = {'layout': 'assets/blender/city_r5/layout.json',
                           'master': 'assets/models/reference-city/r5/market-repair-candidate/reference_city_market_gate_repaired.blend',
                           'master_sha256': 'bda8d7857108bf57cd75f59ee8aad0b170a50fef66b0b26e563bce9c4374d373'}
    cut = ['kit_nw_residential_rows_3', 'kit_nw_residential_rows_6', 'kit_west_residential_rows_2', 'kit_west_residential_rows_3',
           'kit_west_residential_rows_6', 'kit_east_residential_rows_3', 'kit_east_residential_rows_6', 'kit_se_cottages_1']
    cut_centres = {'nw_residential_rows': [2, 5], 'west_residential_rows': [1, 2, 5], 'east_residential_rows': [2, 5], 'se_cottages': [0]}
    for lm in lay['landmarks']:
        if lm['id'] in cut_centres:
            keep = [c for i, c in enumerate(lm['centers']) if i not in cut_centres[lm['id']]]
            lm['r6_cut_centers'] = [c for i, c in enumerate(lm['centers']) if i in cut_centres[lm['id']]]
            lm['centers_r6'] = keep
    facing = {  # runtime heading degrees: 0 = +Z (north), 90 = +X (east)
        'kit_nw_residential_rows_1': 128, 'kit_nw_residential_rows_2': 148, 'kit_nw_residential_rows_4': 182,
        'kit_nw_residential_rows_5': 262, 'kit_west_residential_rows_1': 86, 'kit_west_residential_rows_4': 150,
        'kit_west_residential_rows_5': 322, 'kit_east_residential_rows_1': 254, 'kit_east_residential_rows_2': 288,
        'kit_east_residential_rows_4': 318, 'kit_east_residential_rows_5': 352, 'kit_se_cottages_2': 340}
    paths = [
        {'id': 'west_loop', 'width': 7, 'lift': 0.13, 'points': [[-52, -9], [-58, 3.5], [-88, 1.5], [-98, -12], [-98, -30], [-114.5, -47], [-110, -62], [-110.5, -74], [-100, -86]]},
        {'id': 'east_loop', 'width': 7, 'points': [[84, -42], [80, -56], [82, -74], [100, -85]]},
    ]
    for p in lay['paths']:
        for q in paths:
            if p['id'] == q['id']:
                p['points_r5'] = p['points']
                p['points'] = q['points']
                p['note_r6'] = 'Re-laid around the smithy, guild hall and apothecary; the R5 centreline ran through them.'
    lay['districts_r6'] = {
        'gate_and_canal': {'identity': 'Civic arrival: crystal pillar lanterns, blue crest banners, guard post and arriving trader, flower boxes at both bridges.',
                           'palette': ['warm stone', 'blue crest banners', 'gold', 'blue crystal light'], 'silhouette': 'twin round towers, crystal lanterns, bridge lamp rhythm'},
        'fountain_plaza': {'identity': 'Mosaic plaza: cream/blue meander borders, eight-point compass star, fountain-base flower beds, four bench nooks, avenue-mouth lamp pairs with banners.',
                           'palette': ['cream carved stone', 'slate-blue mosaic', 'terracotta ring', 'ivory/lilac/gold flowers'], 'silhouette': 'fountain + statue, ring of crystal lamps'},
        'market': {'identity': 'Paved market square with three stall clusters (produce, crafts, arcane) around an open centre; goods on the ground beside each stall.',
                   'palette': ['striped red/blue/green canopies', 'warm timber', 'produce colours (no glow)'], 'silhouette': 'canopy roofline, cart'},
        'craftsmen_west': {'identity': 'Smithy, guild hall and tavern on a re-laid west loop; woodcutter yard, guild supplies, tavern green.',
                           'palette': ['dark timber', 'iron', 'red/cream awnings', 'log piles'], 'silhouette': 'smithy chimney, guild turret'},
        'residential_lanes': {'identity': '12 of 20 houses kept, each turned to face its lane or green; variants (lean-to, porch, window boxes, flower borders); six story yards.',
                              'palette': ['plaster', 'timber', 'mixed roofs', 'hedges and flower borders'], 'silhouette': 'varied roof angles instead of 20 clones facing the fountain'},
        'castle_approach': {'identity': 'Grand stairs kept clear; castle terrace trees raised onto the terrace lawn; rose window glass visible again.',
                            'palette': ['pale stone', 'navy/blue slate', 'gold'], 'silhouette': 'castle spires'},
    }
    # ---------------- dressing clusters ---------------------------------------------
    def clear_of_routes(pt, margin):
        """False when a point (with a footprint margin) intrudes on an avenue band, a canal-promenade
        walking line into the plaza, or the fountain loop."""
        x, y = pt
        r = math.hypot(x, y)
        if 13.5 < r < 20.5:
            return False
        if y < -8 and 6.9 - margin < abs(x) < 13.3 + margin:
            return False
        for a_ in lay['plaza']['avenues']:
            tx, ty = a_['to']
            L = math.hypot(tx, ty)
            ux, uy = tx / L, ty / L
            t = x * ux + y * uy
            if 14 < t < L + 2 and abs(-x * uy + y * ux) < a_['width'] * 0.5 + margin:
                return False
        return True

    plaza_items = []
    rejected = []
    nooks = [(69, (-4.2, 4.2)), (110, (-4.2, 4.2)), (235, (0.0,)), (305, (0.0,))]
    for a, offsets in nooks:
        for k, da in enumerate(offsets):
            p = polar(30.0, a + da)
            turn = 0 if len(offsets) == 1 else (15 if k == 0 else -15)
            item = {'kind': 'Bench', 'at': p, 'yaw': a + da + 90 + turn, 'scale': 1.3, 'name': 'plaza bench CC0'}
            (plaza_items if clear_of_routes(p, 2.8) else rejected).append(item)
        lp = polar(33.6, a)
        (plaza_items if clear_of_routes(lp, 1.0) else rejected).append({'kind': 'crystal_lamp', 'at': lp, 'scale': 1.0})
        for side in (1, -1):
            pa = a + side * (9.5 if len(offsets) > 1 else 6.0)
            pp = polar(31.9, pa)
            item = {'kind': 'planter_box', 'at': pp, 'yaw': pa + 90, 'length': 1.4, 'depth': 1.4, 'height': 0.6, 'name': 'garden stone planter nook'}
            (plaza_items if clear_of_routes(pp, 1.8) else rejected).append(item)
    mouths = []
    # north stairs mouth, south promenade mouths, east market and west smithy avenues
    for x, y, arm in ((9.4, 38.6, 0), (-9.4, 38.6, 180), (14.6, -38.2, 0), (-14.6, -38.2, 180)):
        mouths.append({'kind': 'crystal_lamp', 'at': [x, y], 'arm_yaw': arm, 'banner': True, 'scale': 1.05})
    for av, sides in (([50, -20], (6.3, -6.3)), ([-58, -10], (6.3, -6.3))):
        for s in sides:
            p = avenue_point(av, 40.2, s)
            ang = math.degrees(math.atan2(p[1], p[0]))
            mouths.append({'kind': 'crystal_lamp', 'at': p, 'arm_yaw': ang + (90 if s > 0 else -90), 'banner': True, 'scale': 1.05})
    quest = {'id': 'guild quest board', 'items': [
        {'kind': 'notice_board', 'at': polar(38.0, 232), 'yaw': 232 + 90},
        {'kind': 'Crate_Wooden', 'at': polar(38.6, 236.5), 'yaw': 20, 'scale': 1.2},
        {'kind': 'Barrel', 'at': polar(37.4, 227.6), 'yaw': 0, 'scale': 1.35},
        {'kind': 'Bag', 'at': polar(39.3, 228.4), 'yaw': 40, 'scale': 1.3}]}
    gate = [
        {'id': 'gate watch post', 'items': [
            {'kind': 'WeaponStand', 'at': [-17.5, -145.0], 'yaw': 90, 'scale': 1.45},
            {'kind': 'Barrel', 'at': [-19.4, -146.6], 'yaw': 0, 'scale': 1.55},
            {'kind': 'Barrel', 'at': [-20.3, -145.2], 'yaw': 33, 'scale': 1.55},
            {'kind': 'Crate_Wooden', 'at': [-19.6, -143.1], 'yaw': 12, 'scale': 1.55},
            {'kind': 'Stool', 'at': [-16.6, -142.6], 'yaw': 30, 'scale': 1.55},
            {'kind': 'Torch_Metal', 'at': [-18.2, -150.25], 'z': 3.1, 'yaw': 180, 'scale': 1.5},
            {'kind': 'Torch_Metal', 'at': [18.2, -150.25], 'z': 3.1, 'yaw': 180, 'scale': 1.5}]},
        {'id': 'gate arriving trader', 'items': [
            {'kind': 'Stall_Cart_Empty', 'at': [18.6, -139.0], 'yaw': 102, 'scale': 1.8},
            {'kind': 'Bag', 'at': [16.4, -142.4], 'yaw': 15, 'scale': 1.55},
            {'kind': 'Bag', 'at': [17.2, -143.2], 'yaw': 70, 'scale': 1.55},
            {'kind': 'Crate_Wooden', 'at': [20.6, -142.6], 'yaw': -8, 'scale': 1.55},
            {'kind': 'Crate_Wooden', 'at': [21.0, -142.4], 'z': None, 'yaw': 25, 'scale': 1.55},
            {'kind': 'Barrel', 'at': [21.9, -140.6], 'yaw': 0, 'scale': 1.55}]},
        {'id': 'bridge flower boxes', 'items': [
            {'kind': 'planter_box', 'at': [s * 14.9, y], 'yaw': 90, 'length': 2.8, 'depth': 1.0, 'name': 'garden stone planter bridge box'}
            for s in (-1, 1) for y in (-79.6, -68.4, -116.6, -107.4)]},
    ]
    market = [
        {'id': 'market produce', 'items': [
            {'kind': 'Stall_Empty', 'at': [52.0, -30.5], 'yaw': 78, 'scale': 1.75},
            {'kind': 'Barrel', 'at': [54.6, -27.2], 'yaw': 0, 'scale': 1.55},
            {'kind': 'Barrel', 'at': [55.6, -28.4], 'yaw': 40, 'scale': 1.55},
            {'kind': 'FarmCrate_Empty', 'at': [50.4, -26.6], 'yaw': 12, 'scale': 1.7},
            {'kind': 'FarmCrate_Empty', 'at': [49.9, -27.6], 'yaw': -20, 'scale': 1.7},
            {'kind': 'Bag', 'at': [57.4, -23.4], 'yaw': 30, 'scale': 1.55},
            {'kind': 'Crate_Wooden', 'at': [53.6, -33.6], 'yaw': 8, 'scale': 1.55},
            {'kind': 'Bag', 'at': [58.0, -24.5], 'yaw': 75, 'scale': 1.55},
            {'kind': 'Crate_Wooden', 'at': [49.0, -13.5], 'yaw': 18, 'scale': 1.55},
            {'kind': 'Barrel_Holder', 'at': [62.6, -2.6], 'yaw': 180, 'scale': 1.45}]},
        {'id': 'market crafts', 'items': [
            {'kind': 'Stall_Empty', 'at': [83.0, -21.0], 'yaw': -96, 'scale': 1.75},
            {'kind': 'Table_Large', 'at': [79.4, -27.8], 'yaw': 8, 'scale': 1.45},
            {'kind': 'Pot_1', 'at': [78.8, -27.6], 'z_above': 1.04, 'yaw': 0, 'scale': 1.55},
            {'kind': 'Crate_Wooden', 'at': [85.2, -26.6], 'yaw': -12, 'scale': 1.55},
            {'kind': 'Bag', 'at': [84.2, -18.2], 'yaw': 25, 'scale': 1.55},
            {'kind': 'Barrel', 'at': [84.6, -24.0], 'yaw': 0, 'scale': 1.55},
            {'kind': 'Chair_1', 'at': [81.6, -29.6], 'yaw': 200, 'scale': 1.45}]},
        {'id': 'market arcane', 'items': [
            {'kind': 'Cauldron', 'at': [64.8, -40.2], 'yaw': 0, 'scale': 1.5},
            {'kind': 'Crate_Wooden', 'at': [61.2, -39.6], 'yaw': 15, 'scale': 1.55},
            {'kind': 'Bag', 'at': [68.4, -41.0], 'yaw': -20, 'scale': 1.55},
            {'kind': 'Bucket_Metal', 'at': [66.6, -38.0], 'yaw': 0, 'scale': 1.55},
            {'kind': 'crystal_lamp', 'at': [58.6, -40.6], 'scale': 0.95}]},
        {'id': 'market centre', 'items': [
            {'kind': 'market_cross', 'at': [67.0, -20.5], 'name': 'garden stone planter market cross'},
            {'kind': 'planter_box', 'at': [67.0, -16.6], 'yaw': 0, 'length': 2.6, 'depth': 1.0},
            {'kind': 'planter_box', 'at': [67.0, -24.4], 'yaw': 0, 'length': 2.6, 'depth': 1.0}]},
    ]
    yards = [
        {'id': 'cooper yard', 'items': [  # nw_2 side yard
            {'kind': 'Barrel', 'at': [-86.4, 43.6], 'yaw': 0, 'scale': 1.55}, {'kind': 'Barrel', 'at': [-85.5, 42.2], 'yaw': 40, 'scale': 1.55},
            {'kind': 'Barrel', 'at': [-87.6, 42.0], 'yaw': 10, 'scale': 1.55}, {'kind': 'Barrel_Holder', 'at': [-84.6, 45.6], 'yaw': 60, 'scale': 1.45},
            {'kind': 'Bucket_Wooden_1', 'at': [-88.2, 44.8], 'yaw': 0, 'scale': 1.55}]},
        {'id': 'gardener plot', 'items': [  # nw_5 front garden
            {'kind': 'hedge', 'at': [-60.0, 22.0], 'to': [-60.0, 36.0], 'height': 0.95},
            {'kind': 'planter_box', 'at': [-58.0, 26.0], 'yaw': 90, 'length': 2.6, 'depth': 1.0},
            {'kind': 'planter_box', 'at': [-58.0, 32.0], 'yaw': 90, 'length': 2.6, 'depth': 1.0},
            {'kind': 'Pot_1', 'at': [-57.6, 29.0], 'yaw': 0, 'scale': 1.6}, {'kind': 'Bucket_Wooden_1', 'at': [-58.2, 28.2], 'yaw': 0, 'scale': 1.55}]},
        {'id': 'woodcutter yard', 'items': [  # former west_2 lot, west of the new loop
            {'kind': 'log_pile', 'at': [-108.5, -22.0], 'yaw': 8}, {'kind': 'log_pile', 'at': [-108.0, -28.5], 'yaw': -6},
            {'kind': 'Workbench', 'at': [-105.2, -33.2], 'yaw': 95, 'scale': 1.45},
            {'kind': 'Anvil', 'at': [-104.8, -25.4], 'yaw': 0, 'scale': 1.55}]},
        {'id': 'guild supplies', 'items': [  # former west_3 lot by the guild hall
            {'kind': 'Crate_Wooden', 'at': [-106.5, -61.0], 'yaw': 10, 'scale': 1.55}, {'kind': 'Crate_Wooden', 'at': [-107.6, -62.5], 'yaw': -15, 'scale': 1.55},
            {'kind': 'Barrel', 'at': [-105.3, -63.4], 'yaw': 0, 'scale': 1.55}, {'kind': 'Crate_Wooden', 'at': [-104.2, -60.4], 'yaw': 30, 'scale': 1.55}]},
        {'id': 'laundry yard', 'items': [  # former nw_3 lot
            {'kind': 'laundry_line', 'at': [-112.0, 22.0], 'to': [-104.0, 30.5]},
            {'kind': 'Bucket_Wooden_1', 'at': [-106.4, 23.4], 'yaw': 0, 'scale': 1.6},
            {'kind': 'Bag', 'at': [-109.6, 21.2], 'yaw': 30, 'scale': 1.55}]},
        {'id': 'tavern green', 'items': [  # former west_6 lot
            {'kind': 'Table_Large', 'at': [-45.0, -73.0], 'yaw': 35, 'scale': 1.45},
            {'kind': 'Stool', 'at': [-46.8, -71.2], 'yaw': 0, 'scale': 1.55}, {'kind': 'Stool', 'at': [-43.2, -74.8], 'yaw': 0, 'scale': 1.55},
            {'kind': 'Stool', 'at': [-46.1, -75.4], 'yaw': 0, 'scale': 1.55},
            {'kind': 'Table_Large', 'at': [-38.8, -78.6], 'yaw': -20, 'scale': 1.45},
            {'kind': 'Stool', 'at': [-38.0, -76.4], 'yaw': 0, 'scale': 1.55}, {'kind': 'Stool', 'at': [-39.6, -80.8], 'yaw': 0, 'scale': 1.55},
            {'kind': 'Barrel_Holder', 'at': [-50.0, -78.0], 'yaw': 125, 'scale': 1.45},
            {'kind': 'crystal_lamp', 'at': [-42.0, -69.4], 'scale': 0.95}]},
        {'id': 'carter yard', 'items': [  # west_4
            {'kind': 'Crate_Wooden', 'at': [-60.6, -45.6], 'yaw': 10, 'scale': 1.55}, {'kind': 'Crate_Wooden', 'at': [-61.8, -44.4], 'yaw': -25, 'scale': 1.55},
            {'kind': 'FarmCrate_Empty', 'at': [-59.4, -43.6], 'yaw': 40, 'scale': 1.7}, {'kind': 'Bag', 'at': [-62.6, -46.6], 'yaw': 0, 'scale': 1.55}]},
        {'id': 'herbalist yard', 'items': [  # east_2
            {'kind': 'Table_Large', 'at': [101.0, 8.0], 'yaw': 15, 'scale': 1.45},
            {'kind': 'Pot_1', 'at': [100.2, 7.8], 'z_above': 1.04, 'yaw': 0, 'scale': 1.55},
            {'kind': 'planter_box', 'at': [100.6, 11.4], 'yaw': 15, 'length': 2.8, 'depth': 1.0}]},
        {'id': 'market green', 'items': [  # former east_3 lot
            {'kind': 'hedge', 'at': [98.0, -20.0], 'to': [110.0, -22.0]}, {'kind': 'hedge', 'at': [98.0, -36.0], 'to': [110.0, -34.0]},
            {'kind': 'Bench', 'at': [103.0, -27.8], 'yaw': 95, 'scale': 1.3},
            {'kind': 'planter_box', 'at': [108.0, -27.6], 'yaw': 95, 'length': 2.6, 'depth': 1.1},
            {'kind': 'crystal_lamp', 'at': [99.4, -27.5], 'scale': 0.95}]},
        {'id': 'herb garden', 'items': [  # former se_cottages_1 lot, north of the ring road
            {'kind': 'planter_box', 'at': [68.0, -93.0], 'yaw': 8, 'length': 3.0, 'depth': 1.1},
            {'kind': 'planter_box', 'at': [72.6, -92.2], 'yaw': 8, 'length': 3.0, 'depth': 1.1},
            {'kind': 'planter_box', 'at': [77.2, -91.4], 'yaw': 8, 'length': 3.0, 'depth': 1.1},
            {'kind': 'hedge', 'at': [64.6, -89.0], 'to': [80.6, -86.6], 'height': 0.9},
            {'kind': 'Bucket_Wooden_1', 'at': [70.4, -94.6], 'yaw': 0, 'scale': 1.55}]},
        {'id': 'skywatch overlook', 'items': [  # former east_6 lot, south-east rim
            {'kind': 'balustrade', 'at': [99.0, -137.0], 'to': [111.0, -127.0]},
            {'kind': 'telescope', 'at': [104.2, -129.6], 'yaw': -45},
            {'kind': 'Bench', 'at': [101.2, -128.6], 'yaw': -50, 'scale': 1.3},
            {'kind': 'crystal_lamp', 'at': [109.0, -124.0], 'scale': 0.95, 'arm_yaw': -40, 'banner': True}]},
        {'id': 'wizard walk garden', 'items': [  # former nw_6 lot, south-west side of the wizard avenue
            {'kind': 'hedge', 'at': avenue_point([-48, 58], 56.0, -6.6), 'to': avenue_point([-48, 58], 71.0, -6.6), 'height': 0.9},
            {'kind': 'planter_box', 'at': avenue_point([-48, 58], 59.0, -8.6), 'yaw': 140, 'length': 2.4, 'depth': 1.0},
            {'kind': 'planter_box', 'at': avenue_point([-48, 58], 68.0, -8.6), 'yaw': 140, 'length': 2.4, 'depth': 1.0},
            {'kind': 'Bench', 'at': avenue_point([-48, 58], 63.5, -8.8), 'yaw': 140, 'scale': 1.3},
            {'kind': 'crystal_lamp', 'at': avenue_point([-48, 58], 63.5, -11.4), 'scale': 0.95}]},
        {'id': 'cottage rope yard', 'items': [  # se_cottages_2
            {'kind': 'Barrel', 'at': [104.6, -100.4], 'yaw': 0, 'scale': 1.55}, {'kind': 'Rope_2', 'at': [103.2, -99.2], 'yaw': 20, 'scale': 1.55},
            {'kind': 'Bucket_Metal', 'at': [105.4, -98.6], 'yaw': 0, 'scale': 1.55}]},
    ]
    parterre = {'id': 'canal parterre', 'items': []}
    cx, cy, hw, hh = 42.0, -78.0, 15.0, 10.0
    for (ax, ay, bx, by) in ((cx - hw, cy - hh, cx - 2.2, cy - hh), (cx + 2.2, cy - hh, cx + hw, cy - hh),
                             (cx - hw, cy + hh, cx - 2.2, cy + hh), (cx + 2.2, cy + hh, cx + hw, cy + hh),
                             (cx - hw, cy - hh, cx - hw, cy - 2.2), (cx - hw, cy + 2.2, cx - hw, cy + hh),
                             (cx + hw, cy - hh, cx + hw, cy - 2.2), (cx + hw, cy + 2.2, cx + hw, cy + hh)):
        parterre['items'].append({'kind': 'hedge', 'at': [ax, ay], 'to': [bx, by], 'height': 0.95, 'name': 'garden stone planter hedge'})
    for qx in (-1, 1):
        for qy in (-1, 1):
            bx, by = cx + qx * 7.6, cy + qy * 5.0
            parterre['items'].append({'kind': 'hedge', 'at': [bx - 4.6, by - qy * 2.6], 'to': [bx + 4.6, by - qy * 2.6], 'height': 0.6,
                                      'width': 0.6, 'name': 'garden stone planter hedge'})
            parterre['items'].append({'kind': 'planter_box', 'at': [bx, by + qy * 0.4], 'yaw': 0, 'length': 7.2, 'depth': 2.6,
                                      'height': 0.42, 'name': 'garden stone planter parterre bed'})
    parterre['items'] += [{'kind': 'crystal_lamp', 'at': [cx, cy], 'scale': 1.1, 'arm_yaw': 90, 'banner': True},
                          {'kind': 'Bench', 'at': [cx - 3.0, cy - 6.6], 'yaw': 0, 'scale': 1.3, 'name': 'plaza bench CC0 parterre'},
                          {'kind': 'Bench', 'at': [cx + 3.0, cy + 6.6], 'yaw': 180, 'scale': 1.3, 'name': 'plaza bench CC0 parterre'},
                          {'kind': 'strip', 'points': [[cx - hw + 0.6, cy], [cx + hw - 0.6, cy]], 'width': 2.6, 'name': 'terrain / path canal parterre east-west'},
                          {'kind': 'strip', 'points': [[cx, cy - hh + 0.6], [cx, cy + hh - 0.6]], 'width': 2.6, 'name': 'terrain / path canal parterre north-south'}]
    nw_green = {'id': 'nw residents green', 'items': [
        {'kind': 'hedge', 'at': [-84.0, 33.0], 'to': [-72.0, 33.0], 'height': 0.9, 'name': 'garden stone planter hedge'},
        {'kind': 'planter_box', 'at': [-78.0, 38.0], 'yaw': 0, 'length': 3.2, 'depth': 1.2, 'name': 'garden stone planter green bed'},
        {'kind': 'Bench', 'at': [-78.0, 35.0], 'yaw': 0, 'scale': 1.3, 'name': 'plaza bench CC0 green'},
        {'kind': 'crystal_lamp', 'at': [-73.0, 40.0], 'scale': 0.95},
        {'kind': 'flowers', 'at': [-82.5, 41.5], 'radius': 1.1, 'mounds': 4}, {'kind': 'flowers', 'at': [-73.5, 44.0], 'radius': 0.9, 'mounds': 3}]}
    pool_nook = {'id': 'ne pool terrace', 'items': [
        {'kind': 'Bench', 'at': [52.0, 29.4], 'yaw': 0, 'scale': 1.3, 'name': 'plaza bench CC0 pool'},
        {'kind': 'Bench', 'at': [60.0, 29.4], 'yaw': 0, 'scale': 1.3, 'name': 'plaza bench CC0 pool'},
        {'kind': 'planter_box', 'at': [47.4, 29.8], 'yaw': 0, 'length': 1.6, 'depth': 1.6, 'height': 0.62, 'name': 'garden stone planter pool'},
        {'kind': 'planter_box', 'at': [64.6, 29.8], 'yaw': 0, 'length': 1.6, 'depth': 1.6, 'height': 0.62, 'name': 'garden stone planter pool'},
        {'kind': 'crystal_lamp', 'at': [56.0, 28.2], 'scale': 1.0, 'arm_yaw': 90, 'banner': True}]}
    yards += [parterre, nw_green, pool_nook]
    variants = {
        'kit_nw_residential_rows_1': ['porch', 'window_boxes'], 'kit_nw_residential_rows_2': ['lean_to_west'],
        'kit_nw_residential_rows_4': ['flower_border', 'window_boxes'], 'kit_nw_residential_rows_5': ['porch'],
        'kit_west_residential_rows_1': ['lean_to_east', 'window_boxes'], 'kit_west_residential_rows_4': ['porch'],
        'kit_west_residential_rows_5': ['flower_border'], 'kit_east_residential_rows_1': ['window_boxes', 'flower_border'],
        'kit_east_residential_rows_2': ['lean_to_east'], 'kit_east_residential_rows_4': ['porch', 'window_boxes'],
        'kit_east_residential_rows_5': ['lean_to_west', 'flower_border'], 'kit_se_cottages_2': ['window_boxes'],
    }
    fountain_beds = []
    av_angles = sorted(math.degrees(math.atan2(a['to'][1], a['to'][0])) for a in lay['plaza']['avenues'])
    gaps = list(zip(av_angles, av_angles[1:] + [av_angles[0] + 360]))
    for a0, a1 in gaps:
        span = a1 - a0
        if span < 20:
            continue
        pieces = 2 if span > 55 else 1
        for k in range(pieces):
            s0 = a0 + 6 + (span - 12) * k / pieces
            s1 = a0 + 6 + (span - 12) * (k + 1) / pieces - (2 if pieces > 1 and k == 0 else 0)
            fountain_beds.append({'r': [11.7, 13.15], 'a': [round(s0, 2), round(s1, 2)]})
    perimeter_beds = []
    R_MID = 35.8
    excl = []
    for a_ in lay['plaza']['avenues']:
        if a_['id'] == 'south_canal':
            continue
        ang = math.degrees(math.atan2(a_['to'][1], a_['to'][0]))
        half = math.degrees(math.asin(min(0.99, (a_['width'] * 0.5 + 3.0) / R_MID)))
        excl.append((ang - half, ang + half))
    excl += [(-117.0, -63.0), (-2.0, 30.0)]  # canal promenade mouths; arcane portal dais
    norm = []
    for a0, a1 in excl:
        if a0 < -180:
            norm += [(a0 + 360, 180.0), (-180.0, a1)]
        elif a1 > 180:
            norm += [(a0, 180.0), (-180.0, a1 - 360)]
        else:
            norm.append((a0, a1))
    norm.sort()
    free, cur = [], -180.0
    for a0, a1 in norm:
        if a0 > cur:
            free.append((cur, a0))
        cur = max(cur, a1)
    if cur < 180.0:
        free.append((cur, 180.0))
    for a0, a1 in free:
        a0, a1 = a0 + 1.5, a1 - 1.5
        if a1 - a0 < 9:
            continue
        if a1 - a0 > 20:
            mid = (a0 + a1) / 2
            perimeter_beds += [{'r': [35.0, 36.6], 'a': [round(a0, 2), round(mid - 1.6, 2)]},
                               {'r': [35.0, 36.6], 'a': [round(mid + 1.6, 2), round(a1, 2)]}]
        else:
            perimeter_beds.append({'r': [35.0, 36.6], 'a': [round(a0, 2), round(a1, 2)]})
    promenade = {'id': 'canal promenade lamps', 'items': []}
    for sx in (-1, 1):
        for y in (-136.0, -94.0, -54.0):
            promenade['items'].append({'kind': 'crystal_lamp', 'at': [sx * 14.7, y], 'arm_yaw': 0 if sx < 0 else 180, 'banner': True, 'scale': 1.0})
    lamp_and_bench_clear = [[0, 0, 0]]
    ops = [
        {'op': 'dedupe', 'note': 'Exact duplicate meshes (castle portal arch built twice, etc.)'},
        {'op': 'delete', 'op_id': 'cut_duplicate_houses', 'rules': [{'root': n, 'whole_root': True} for n in cut]},
        {'op': 'delete', 'op_id': 'plaza_rings_removed', 'rules': [
            {'pattern': r'^(garden stone planter|garden dark soil|garden leafy stem|garden blossom|plaza bench |city lamp )', 'root': 'kit_city_vegetation', 'max_radius': 45}]},
        {'op': 'delete', 'op_id': 'house_clutter_removed', 'rules': [
            {'pattern': r'^(nw|west|east)_residential_rows_\d (front barrel|herb keg|shop sign)'},
            {'pattern': r'^se_cottages_\d (front barrel|herb keg|shop sign)'},
            {'pattern': r'^(armory_house|apothecary|blacksmith forge hall) street crest'},
            {'pattern': r'^tavern (shop sign|street crest)'}]},
        {'op': 'delete', 'op_id': 'static_portal_spike_removed', 'rules': [{'pattern': r'^portal vertical light column'}]},
        {'op': 'delete', 'op_id': 'window_over_shop_door_removed', 'rules': [
            {'pattern': r'^(apothecary|armory_house) front window 1-2 '},
            {'pattern': r'^blacksmith forge hall front window 1-3 '}]},
        {'op': 'coplanar_insets', 'rules': [
            {'pattern': r'^castle lower plinth$', 'scale': [1.002, 1.002, 1.0]},
            {'pattern': r'^castle plinth moulding$', 'scale': [1.003, 1.003, 1.0]},
            {'pattern': r'^castle rear cloister', 'offset': [0, 0, 0.012]},
            {'pattern': r'^castle facade buttress', 'offset': [0, -0.012, 0]},
            {'pattern': r'^terrain / channel coping', 'offset': [0, 0, 0.012]},
            {'pattern': r'^north arcade carved arch', 'scale': [1.0, 0.995, 1.0], 'alternate': True},
            {'pattern': r'^fountain guardian wing feather', 'scale': [1.0, 0.985, 0.985], 'alternate': True}]},
        {'op': 'reparent_orphans', 'skip_owner_pattern': r'^bridge blue lamp finial'},
        {'op': 'fountain_foot'},
        {'op': 'gate_merlons'},
        {'op': 'lift_mortar', 'lift_m': 0.015},
        {'op': 'rose_window'},
        {'op': 'simplify_hardware', 'pattern': r' shutter strap| hinge strap|(vertical|horizontal) mullion|gold mullion|window lead', 'max_thickness_m': 0.12},
        {'op': 'houses', 'cut': [], 'face_heading_deg': facing},
        {'op': 'reroute_paths', 'paths': paths},
        {'op': 'bridge_lamps'},
        {'op': 'trees', 'castle_terrace_poly': [[-52, 72], [52, 72], [52, 106], [80, 106], [80, 125], [-80, 125], [-80, 106], [-52, 106]],
         'keep_clear': [[avenue_point([-48, 58], 64, 0)[0], avenue_point([-48, 58], 64, 0)[1], 5.5]]},
        {'op': 'plaza_mosaic',
         'bands': [{'id': 'fountain meander', 'replace_radius': [14.25, 16.3], 'radius': [14.2, 16.35], 'border_m': 0.22},
                   {'id': 'outer meander', 'replace_radius': [37.1, 39.8], 'radius': [37.03, 39.84], 'border_m': 0.26}],
         'star': {'radius': [18.5, 31.6], 'ray_half_deg': 9.0, 'ray_tint': [0.44, 0.58, 0.96], 'ring_r': 28.46, 'ring_half_m': 0.6,
                  'ring_tint': [1.0, 0.72, 0.55]},
         'fountain_beds': fountain_beds, 'perimeter_beds': perimeter_beds},
        {'op': 'market', 'remove_stalls': ['1-3', '2-1', '2-2', '2-4'],
         'move_stalls': {'1-2': [-3.5, -1.5, 12], '1-4': [1.5, -4.5, -15], '2-3': [0.5, 2.5, 8]},
         'move_cart': [-3.0, -7.0, -20],
         'square_poly': [[46, -2], [84, -2], [88, -6], [88, -38], [84, -43], [51, -43], [46, -38]]},
        {'op': 'gate'},
        {'op': 'house_variants', 'variants': variants},
        {'op': 'clusters', 'op_id': 'plaza_clusters', 'owner': 'kit_city_vegetation',
         'clusters': [{'id': 'plaza bench nook', 'items': plaza_items}, {'id': 'avenue mouth lamps', 'items': mouths}, quest]},
        {'op': 'clusters', 'op_id': 'gate_clusters', 'owner': 'kit_town_gate', 'clusters': gate + [promenade]},
        {'op': 'clusters', 'op_id': 'market_clusters', 'owner': 'kit_market_square', 'clusters': market},
        {'op': 'clusters', 'op_id': 'story_yards', 'owner': 'kit_city_vegetation', 'clusters': yards},
        {'op': 'meadow_drifts', 'seed': 4404, 'max_per_patch': 4, 'min_gap_m': 14.0, 'patches': [
            {'bbox': [14, -102, 90, -34], 'spacing': 17.0}, {'bbox': [34, -14, 94, 90], 'spacing': 17.0},
            {'bbox': [-94, -2, -42, 102], 'spacing': 17.0}, {'bbox': [-94, -134, -50, -94], 'spacing': 17.0},
            {'bbox': [10, 38, 46, 62], 'spacing': 17.0}, {'bbox': [-42, -102, -14, -70], 'spacing': 17.0},
            {'bbox': [46, 74, 74, 102], 'spacing': 17.0}, {'bbox': [-42, -66, -14, -34], 'spacing': 17.0}]},
        {'op': 'snap_floaters', 'iterations': 3, 'max_snap_m': 1.25, 'embed_m': 0.012, 'max_members': 70,
         'reach_overrides': {'castle central nave slate dormer': 2.2},
         'allow_pattern': r'window|counter|goods crate|display|standard|banner|sigil|staff|crest|lancet|capital|dormer|chimney|herb|'
                          r'hanging|sign|bracket|bench|lantern|stall|glasshouse|tree|planter|lamp|CC0|flower|mound|blossom|merlon|well water|rack|blade'},
        # pass 4 (r6-finish, 2026-10-03): visible cuts and z-fights found in the owner review
        {'op': 'canopy_clear', 'min_hits': 4,
         'building_pattern': r' (masonry body|foundation plinth)$|^castle |curtain wall|round tower|observatory|windmill plaster tower|guild |tavern|smithy|forge',
         'terrace_pattern': r'^terrain / (castle|wizard) terrace'},
        {'op': 'resolve_coplanar', 'min_cover': 0.97, 'decal_lift_m': 0.004,
         'decal_pattern': r'^terrain / plaza pavers mosaic .*meander line',
         'cover_pattern': r'coping|paving|tread|landing|cap\b|top\b|roof|slab|floor|sill'},
        {'op': 'edge_gap_skirts', 'embed_m': 0.06, 'ring_tol_m': 0.02},
    ]
    lay['r6_dressing'] = {'schema': 'xexoria.city-r6-dressing/1', 'operations': ops,
                          'house_cut': cut, 'house_facing_runtime_heading_deg': facing,
                          'rule': 'Every op runs on a loaded copy of the selected R5 master; outputs go to assets/models/reference-city/r6-candidate/.'}
    OUT.write_text(json.dumps(lay, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(OUT), 'ops': len(ops), 'fountain_beds': len(fountain_beds), 'plaza_items': len(plaza_items) + len(mouths),
                      'nook_items_rejected_by_route_clearance': [(r['kind'], r['at']) for r in rejected]}))


if __name__ == '__main__':
    main()
