"""Derive the R6 map-dressing candidate from the selected R5 city master.

Never rebuilds over or saves the R5 sources. Loads the selected immutable master
(r5/market-repair-candidate, SHA bda8d785...) read-only, applies the operations of
assets/blender/city_r5/layout-r6-candidate.json ("r6_dressing"), and saves a NEW
editable master into assets/models/reference-city/r6-candidate/ with a receipt.
Why derive instead of re-running build_city_r5.py: that builder writes into r5/
(it would overwrite the canonical master) and rebuilding from kits would drop the
accepted post-build repairs (walk geometry, stair/bridge/fountain caps, market pivots,
gate jambs and bank arrivals) that the active traversal receipt depends on.

  blender -b --factory-startup --disable-autoexec \
    assets/models/reference-city/r5/market-repair-candidate/reference_city_market_gate_repaired.blend \
    --python-exit-code 1 --python assets/blender/city_r5/build_city_r6_candidate.py -- [--pass-tag p1]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'lib'))
sys.path.insert(0, str(HERE / 'kits'))
sys.path.insert(0, str(HERE))
import citykit as ck  # noqa: E402
import r6lib as L  # noqa: E402
import lint_placement as lint  # noqa: E402

SOURCE = ROOT / 'assets/models/reference-city/r5/market-repair-candidate/reference_city_market_gate_repaired.blend'
SOURCE_SHA = 'bda8d7857108bf57cd75f59ee8aad0b170a50fef66b0b26e563bce9c4374d373'
LAYOUT_R6 = HERE / 'layout-r6-candidate.json'
OUT_DIR = ROOT / 'assets/models/reference-city/r6-candidate'
CANDIDATE = OUT_DIR / 'reference_city_r6_candidate.blend'
T0 = time.time()
LOG: list[str] = []
CHANGES: dict = defaultdict(lambda: {'deleted_objects': 0, 'deleted_triangles': 0, 'added_objects': 0, 'added_triangles': 0,
                                     'moved_objects': 0, 'notes': []})


def log(msg):
    line = f'[{time.time() - T0:7.1f}s] {msg}'
    LOG.append(line)
    print(line, flush=True)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def tris(objs):
    return sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == 'MESH')


def desc(o):
    out, st = [], [o]
    while st:
        x = st.pop()
        out.append(x)
        st.extend(x.children)
    return out


def delete(objs, op):
    objs = [o for o in objs if o is not None and o.name in bpy.data.objects]
    CHANGES[op]['deleted_objects'] += sum(1 for o in objs if o.type == 'MESH')
    CHANGES[op]['deleted_triangles'] += tris(objs)
    meshes = [o.data for o in objs if o.type == 'MESH']
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for m in meshes:
        if m.users == 0:
            bpy.data.meshes.remove(m)


def added(op, start):
    new = L.NEW[start:]
    CHANGES[op]['added_objects'] += sum(1 for o in new if o.type == 'MESH')
    CHANGES[op]['added_triangles'] += tris(new)


def meshes_named(pattern, root=None):
    rx = re.compile(pattern)
    pool = desc(root) if root is not None else bpy.context.scene.objects
    return [o for o in pool if o.type == 'MESH' and rx.search(o.name)]


def world_verts(o):
    me = o.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    m = np.array(o.matrix_world)
    return co @ m[:3, :3].T + m[:3, 3]


def translate(objs, v, op):
    v = Vector(v)
    for o in objs:
        o.matrix_world = Matrix.Translation(v) @ o.matrix_world
    CHANGES[op]['moved_objects'] += len(objs)


def rt(x, y, z=0.0):
    return [round(x, 2), round(z, 2), round(176 + y, 2)]


# ---------------------------------------------------------------------------
# 1. exact duplicate geometry (z-fighting twins)
# ---------------------------------------------------------------------------
def op_dedupe(cfg):
    op = 'dedupe_exact_duplicates'
    groups = defaultdict(list)
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or o.name.startswith(ck.RUNTIME_PREFIXES) or not len(o.data.vertices):
            continue
        w = world_verts(o)
        key = (len(o.data.vertices), len(o.data.polygons), o.data.materials[0].name if o.data.materials else '',
               tuple(np.round(w.min(axis=0), 3)), tuple(np.round(w.max(axis=0), 3)))
        groups[key].append((o, w))
    victims = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        seen = {}
        for o, w in items:
            h = hashlib.sha1(np.round(np.sort(np.round(w, 3).view([('', w.dtype)] * 3), axis=0).view(w.dtype), 3).tobytes()).hexdigest()
            if h in seen:
                victims.append(o)
                CHANGES[op]['notes'].append(f'{o.name} == {seen[h]}')
            else:
                seen[h] = o.name
    delete(victims, op)
    log(f'{op}: removed {len(victims)} exact duplicates')


# ---------------------------------------------------------------------------
# 2. orphan child parts (never received their kit-root transform)
# ---------------------------------------------------------------------------
def op_reparent_orphans(cfg):
    op = 'reparent_orphan_child_parts'
    rep = lint.run_lint('city', log=lambda *_: None)
    skip = re.compile(cfg.get('skip_owner_pattern', r'^$'))
    fixed = 0
    for f in rep['findings']:
        if f['rule'] != 'L3':
            continue
        o = bpy.data.objects.get(f['id'])
        owner = bpy.data.objects.get(f['owner'])
        if o is None or owner is None or owner.parent is None:
            continue
        if skip.search(owner.name):
            delete([o], op)  # owner is rebuilt by a later op
            continue
        o.parent = owner.parent
        o.matrix_parent_inverse = Matrix.Identity(4)  # vertices are already in the kit-local frame
        fixed += 1
        CHANGES[op]['notes'].append(f"{o.name} -> {owner.parent.name} at {f['fixed_at_runtime']}")
    CHANGES[op]['moved_objects'] += fixed
    log(f'{op}: re-parented {fixed}')


# ---------------------------------------------------------------------------
# 3. deletions by name family
# ---------------------------------------------------------------------------
def op_delete(cfg):
    op = cfg['op_id']
    victims = []
    for rule in cfg['rules']:
        root = bpy.data.objects.get(rule['root']) if rule.get('root') else None
        if rule.get('root') and root is None:
            continue
        if rule.get('whole_root'):
            victims += desc(root)
            continue
        found = meshes_named(rule['pattern'], root)
        if 'max_radius' in rule:
            found = [o for o in found if np.hypot(*world_verts(o).mean(axis=0)[:2]) <= rule['max_radius']]
        victims += found
    victims = list({o.name: o for o in victims}.values())
    delete(victims, op)
    log(f'{op}: deleted {len(victims)} objects')


# ---------------------------------------------------------------------------
# 4. structural fixes
# ---------------------------------------------------------------------------
def op_fountain_foot(cfg):
    op = 'fountain_stem_foot'
    root = bpy.data.objects['kit_plaza_fountain']
    s = len(L.NEW)
    L.lathe('fountain central stem foot', [(1.66, 1.28), (1.58, 1.62), (1.44, 2.02), (1.34, 2.44), (0.0, 2.44)],
            (0, 0, 0), 'stone_trim_carved', root, 40)
    L.lathe('fountain stem foot water collar', [(1.62, 2.06), (1.78, 2.16), (1.70, 2.30), (1.42, 2.34)],
            (0, 0, 0), 'stone_trim_carved', root, 40)
    added(op, s)
    log(f'{op}: stem now stands on the inner basin floor')


def op_gate_merlons(cfg):
    op = 'gate_merlons_seated'
    walls = meshes_named(r'^gate curtain wall block')
    tree = BVHTree.FromPolygons([tuple(v) for w in walls for v in world_verts(w)],
                                [tuple(i + sum(len(x.data.vertices) for x in walls[:k]) for i in p.vertices)
                                 for k, w in enumerate(walls) for p in w.data.polygons])
    moved = 0
    for m in meshes_named(r'^gate curtain merlon'):
        w = world_verts(m)
        c = w.mean(axis=0)
        hit = tree.ray_cast(Vector((c[0], c[1], w[:, 2].max() + 0.5)), Vector((0, 0, -1)), 30.0)
        if hit[0] is None:
            continue
        # skip the merlon's own extent: cast from just under its base
        hit = tree.ray_cast(Vector((c[0], c[1], w[:, 2].min() + 0.01)), Vector((0, 0, -1)), 30.0)
        if hit[0] is None:
            continue
        dz = hit[0].z - 0.04 - w[:, 2].min()
        if abs(dz) > 0.02:
            translate([m], (0, 0, dz), op)
            moved += 1
    log(f'{op}: {moved} merlons seated on their wall tops')


def op_lift_mortar(cfg):
    op = 'plaza_mortar_bed_lift'
    o = bpy.data.objects.get('terrain / plaza mortar bed')
    if o:
        translate([o], (0, 0, cfg.get('lift_m', 0.015)), op)
    log(f'{op}: mortar bed raised {cfg.get("lift_m", 0.015)} m above the coplanar grass')


def op_rose_window(cfg):
    op = 'rose_window_ring_caps_removed'
    n = 0
    for o in meshes_named(r'^castle rose window brass ring'):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        caps = [f for f in bm.faces if len(f.verts) > 4]
        n += len(caps)
        before = sum(len(f.verts) - 2 for f in bm.faces)
        bmesh.ops.delete(bm, geom=caps, context='FACES_ONLY')
        after = sum(len(f.verts) - 2 for f in bm.faces)
        bm.to_mesh(o.data)
        bm.free()
        CHANGES[op]['deleted_triangles'] += before - after
    log(f'{op}: removed {n} solid cap discs hiding the rose-window glass')


def op_coplanar_insets(cfg):
    """Nudge repaired shells that sit coplanar with older faces (z-fighting)."""
    op = 'coplanar_shell_insets'
    for rule in cfg['rules']:
        found = sorted(meshes_named(rule['pattern']), key=lambda o: o.name)
        if rule.get('alternate'):
            found = found[1::2]
        for o in found:
            s = rule.get('scale')
            if s:
                c = Vector(world_verts(o).mean(axis=0).tolist())
                mw = Matrix.Translation(c) @ Matrix.Diagonal((s[0], s[1], s[2], 1)) @ Matrix.Translation(-c) @ o.matrix_world
                o.matrix_world = mw
            if rule.get('offset'):
                translate([o], rule['offset'], op)
            CHANGES[op]['notes'].append(f"{o.name}: {rule}")
            CHANGES[op]['moved_objects'] += 1
    log(f'{op}: {CHANGES[op]["moved_objects"]} shells nudged')


def op_simplify_hardware(cfg):
    """Shutter straps and mullions: 2-segment 1 cm bevels (108 tris) -> exact-bounds boxes (12 tris)."""
    op = 'hardware_bevels_to_boxes'
    rx = re.compile(cfg['pattern'])
    n = before = after = 0
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or not rx.search(o.name) or len(o.data.polygons) <= 6:
            continue
        me = o.data
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        lo, hi = co.min(axis=0), co.max(axis=0)
        if np.min(hi - lo) > cfg.get('max_thickness_m', 0.12):
            continue
        before += sum(len(p.vertices) - 2 for p in me.polygons)
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        new = bpy.data.meshes.new(me.name + ' r6box')
        new.from_pydata(verts, [], faces)
        for m in me.materials:
            new.materials.append(m)
        old = me
        o.data = new
        if old.users == 0:
            bpy.data.meshes.remove(old)
        ck.uv_box(o)
        ck.vertex_paint(o, seed=n, cavity=0.2, edge=0.12, jitter=0.03)
        after += 12
        n += 1
    CHANGES[op]['deleted_triangles'] += before - after
    log(f'{op}: {n} parts, {before} -> {after} triangles')


# ---------------------------------------------------------------------------
# 5. lamps, bridges, trees
# ---------------------------------------------------------------------------
def lamp_groups(prefix='city lamp '):
    parts = meshes_named(r'^' + re.escape(prefix))
    groups = defaultdict(list)
    for o in parts:
        c = world_verts(o).mean(axis=0)
        groups[(round(c[0] * 2) / 2, round(c[1] * 2) / 2)].append(o)
    return groups


def op_relocate_lamps(cfg, G):
    op = 'plaza_lamps_relocated'
    groups = sorted(lamp_groups().items(), key=lambda kv: math.atan2(kv[0][1], kv[0][0]))
    targets = cfg['targets']
    used = 0
    for (cx, cy), parts in groups:
        if used >= len(targets):
            delete(parts, op)
            continue
        tx, ty = targets[used]
        z, _ = G.z(tx, ty)
        base = min(world_verts(o)[:, 2].min() for o in parts)
        translate(parts, (tx - cx, ty - cy, (z or 0.0) - 0.02 - base), op)
        used += 1
    log(f'{op}: {used} lamps moved to avenue mouths and bench nooks')


def op_bridge_lamps(cfg, G):
    op = 'bridge_crystal_lamps'
    s = len(L.NEW)
    for bid in ('kit_canal_bridge', 'kit_ring_bridge'):
        root = bpy.data.objects.get(bid)
        if root is None:
            continue
        old = meshes_named(r'^bridge (lamp pedestal|blue lamp finial)', root)
        delete(old, op)
        copings = meshes_named(r'^bridge pale coping', root)
        verts, polys, base = [], [], 0
        for c in copings:
            w = world_verts(c)
            verts.extend(map(tuple, w))
            polys.extend(tuple(base + i for i in p.vertices) for p in c.data.polygons)
            base += len(w)
        tree = BVHTree.FromPolygons(verts, polys)
        spec = next(l for l in LAYOUT['landmarks'] if 'kit_' + l['id'] == bid)
        length, width = float(spec['length']), float(spec['width'])
        for side in (-1, 1):
            for x in (-length * 0.42, 0.0, length * 0.42):
                p = root.matrix_world @ Vector((x, side * width * 0.5, 0))
                hit = tree.ray_cast(Vector((p.x, p.y, 20.0)), Vector((0, 0, -1)), 40.0)
                if hit[0] is None:
                    continue
                L.crystal_lamp(f'{bid[4:]} crystal lamp', p.x, p.y, hit[0].z, root, s=0.78, seed=int(x * 10))
    added(op, s)
    log(f'{op}: rebuilt 12 bridge lamps seated on the parapet coping')


def tree_components():
    """Each vegetation tree = trunk + touching branches/canopies (contact graph)."""
    veg = bpy.data.objects.get('kit_city_vegetation')
    parts = [o for o in desc(veg) if o.type == 'MESH' and re.search(r' tree (trunk|branch|canopy)|canopy flower|pine tier', o.name)]
    trunks = [o for o in parts if ' tree trunk' in o.name]
    info = {o.name: world_verts(o) for o in parts}
    comps = {t.name: [t] for t in trunks}
    centres = {t.name: info[t.name].mean(axis=0) for t in trunks}
    for o in parts:
        if o in trunks:
            continue
        c = info[o.name].mean(axis=0)
        best = min(trunks, key=lambda t: (c[0] - centres[t.name][0]) ** 2 + (c[1] - centres[t.name][1]) ** 2)
        comps[best.name].append(o)
    return comps, info


def op_trees(cfg, G):
    op = 'trees_seated_or_removed'
    comps, info = tree_components()
    moved = removed = 0
    veg_names = {o.name for o in desc(bpy.data.objects['kit_city_vegetation'])}
    sverts, spolys, sbase = [], [], 0
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or o.name in veg_names or o.name.startswith(ck.RUNTIME_PREFIXES) or L._WALK.search(o.name):
            continue
        if o.name.startswith('terrain / '):
            continue
        w = world_verts(o)
        sverts.extend(map(tuple, w))
        spolys.extend(tuple(sbase + i for i in p.vertices) for p in o.data.polygons)
        sbase += len(w)
    solid = BVHTree.FromPolygons(sverts, spolys)
    for tname, members in comps.items():
        t = bpy.data.objects[tname]
        w = info[tname]
        x, y = float(w[:, 0].mean()), float(w[:, 1].mean())
        base = float(w[:, 2].min())
        top, surf = G.z(x, y)
        reason = None
        if top is None:
            reason = 'no ground'
        elif surf and re.search(r'path|avenue|traversal|paving|plaza|promenade|stair', surf):
            reason = f'stands on walk surface {surf}'
        elif any(math.hypot(x - c[0], y - c[1]) < c[2] for c in cfg['keep_clear']):
            reason = 'inside a cleared lot or route corridor'
        else:
            for ox, oy in ((0, 0), (1.2, 0), (-1.2, 0), (0, 1.2), (0, -1.2)):
                hit = solid.ray_cast(Vector((x + ox, y + oy, top + 30.0)), Vector((0, 0, -1)), 29.0)
                if hit[0] is not None and hit[0].z > top + 0.3:
                    reason = f'under or inside a structure ({round(hit[0].z - top, 1)} m above the ground)'
                    break
        if reason:
            delete(members, op)
            removed += 1
            CHANGES[op]['notes'].append(f'removed {tname} at {rt(x, y)}: {reason}')
            continue
        dz = top - 0.14 - base
        if abs(dz) > 0.03:
            translate(members, (0, 0, dz), op)
            moved += 1
            CHANGES[op]['notes'].append(f'{tname} moved {dz:+.2f} m onto {surf}')
    log(f'{op}: {moved} trees re-seated on the terrain mesh, {removed} removed')


# ---------------------------------------------------------------------------
# 6. paths
# ---------------------------------------------------------------------------
def op_reroute_paths(cfg, G):
    op = 'paths_rerouted'
    terrain = importlib.import_module('terrain')
    col = bpy.data.collections.get('terrain')
    T = terrain.TerrainBuilder(LAYOUT, col)
    s = len(L.NEW)
    for p in cfg['paths']:
        old = meshes_named(r'^terrain / path ' + re.escape(p['id']) + r'( curb)?(\.\d{3})?$')
        delete(old, op)
        before = set(bpy.data.objects)
        T.strip(f"terrain / path {p['id']}", p['points'], p['width'], p.get('material', 'cobble_path'), lift=p.get('lift', 0.06))
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:
            L.NEW.append(o)
    added(op, s)
    G.rebuild()
    log(f'{op}: {len(cfg["paths"])} paths re-laid around buildings')
    return T


# ---------------------------------------------------------------------------
# 7. houses
# ---------------------------------------------------------------------------
def house_roots():
    return [o for o in bpy.context.scene.objects if o.type == 'EMPTY' and re.match(r'^kit_(nw|west|east)_residential_rows_\d|^kit_se_cottages_\d', o.name)]


def op_houses(cfg, G):
    op = 'houses_cut_and_turned'
    for name in cfg['cut']:
        r = bpy.data.objects.get(name)
        if r is not None:
            delete(desc(r), op)
            CHANGES[op]['notes'].append(f'cut {name}')
    for name, heading in cfg.get('face_heading_deg', {}).items():
        r = bpy.data.objects.get(name)
        if r is None:
            continue
        # runtime heading h (0 = +Z/north, 90 = +X/east): front direction (sin h, cos h) in Blender XY
        h = math.radians(heading)
        fx, fy = math.sin(h), math.cos(h)
        yaw = math.atan2(fy, fx)
        loc = r.matrix_world.translation.copy()
        r.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(yaw + math.pi / 2, 4, 'Z')
        CHANGES[op]['moved_objects'] += 1
        CHANGES[op]['notes'].append(f'{name} faces {heading} deg')
    G.rebuild()
    log(f'{op}: cut {len(cfg["cut"])}, re-faced {len(cfg.get("face_heading_deg", {}))}')


def house_frame(r):
    """Local frame helpers for an R5 house kit (front = local -Y, w 11, d 9, body 8.5 m)."""
    m = r.matrix_world

    def P(x, y, z):
        return m @ Vector((x, y, z))
    yaw = m.to_euler().z
    return P, yaw


def op_house_variants(cfg, G):
    op = 'house_variants'
    s = len(L.NEW)
    rng = random.Random(6061)
    w, d, body = 11.0, 9.0, 8.5
    for name, kinds in cfg['variants'].items():
        r = bpy.data.objects.get(name)
        if r is None:
            continue
        P, yaw = house_frame(r)
        roof = None
        for o in desc(r):
            if o.type == 'MESH' and o.name.endswith(' roof skin') and o.data.materials:
                roof = o.data.materials[0].name
        roof = roof or 'roof_slate_blue'
        for kind in kinds:
            if kind.startswith('lean_to'):
                side = 1 if kind.endswith('east') else -1
                x0 = side * (w * 0.5 + 0.05)
                x1 = side * (w * 0.5 + 3.4)
                xc = (x0 + x1) * 0.5
                c = P(xc, 0.6, 0)
                gz = G.footprint_min(c.x, c.y, 3.45, 6.4, math.degrees(yaw)) or 0.0
                L.box(f'{name[4:]} lean-to stone base', (c.x, c.y, gz + 0.27), (3.45, 6.4, 0.66), 'stone_foundation', r,
                      rot_z=yaw, bevel=0.06, ground=gz)
                L.box(f'{name[4:]} lean-to plaster wall', (c.x, c.y, gz + 0.5 + 1.9), (3.3, 6.2, 3.8), 'plaster_cream', r,
                      rot_z=yaw, bevel=0.05)
                for yy in (-3.0, 3.0):
                    p = P(x1 - side * 0.12, 0.6 + yy, 0)
                    L.box(f'{name[4:]} lean-to corner post', (p.x, p.y, gz + 2.4), (0.24, 0.24, 4.2), 'timber_dark', r, rot_z=yaw, bevel=0.03)
                # mono-pitch roof: high edge against the house wall, low edge outside
                hi_z, lo_z = gz + 5.6, gz + 4.25
                a = P(x0 - side * 0.14, -3.6 + 0.6, 0)
                b = P(x0 - side * 0.14, 3.6 + 0.6, 0)
                c2 = P(x1 + side * 0.45, 3.6 + 0.6, 0)
                d2 = P(x1 + side * 0.45, -3.6 + 0.6, 0)
                verts = [(a.x, a.y, hi_z), (b.x, b.y, hi_z), (c2.x, c2.y, lo_z), (d2.x, d2.y, lo_z),
                         (a.x, a.y, hi_z + 0.16), (b.x, b.y, hi_z + 0.16), (c2.x, c2.y, lo_z + 0.16), (d2.x, d2.y, lo_z + 0.16)]
                faces = [(4, 5, 6, 7), (0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
                L.mesh(f'{name[4:]} lean-to roof', verts, faces, roof, r)
                door = P(x1 + side * 0.02, 0.6, 0)
                L.box(f'{name[4:]} lean-to plank door', (door.x, door.y, gz + 1.55), (0.12, 1.5, 2.2), 'wood_planks_dark', r, rot_z=yaw, bevel=0.0)
            elif kind == 'porch':
                for xx in (-1.55, 1.55):
                    p = P(xx, -d * 0.5 - 2.0, 0)
                    gz, _ = G.z(p.x, p.y)
                    gz = gz or 0.0
                    L.box(f'{name[4:]} porch post', (p.x, p.y, gz + 1.95), (0.26, 0.26, 4.0), 'timber_dark', r, rot_z=yaw, bevel=0.03)
                    L.box(f'{name[4:]} porch post stone', (p.x, p.y, gz + 0.2), (0.48, 0.48, 0.44), 'stone_trim_carved', r, rot_z=yaw, bevel=0.04, ground=gz)
                c = P(0, -d * 0.5 - 1.05, 0)
                gz, _ = G.z(c.x, c.y)
                gz = gz or 0.0
                hz = gz + 4.05
                a = P(-2.0, -d * 0.5 + 0.05, 0)
                b = P(2.0, -d * 0.5 + 0.05, 0)
                c2 = P(2.0, -d * 0.5 - 2.35, 0)
                d2 = P(-2.0, -d * 0.5 - 2.35, 0)
                verts = [(a.x, a.y, hz + 0.75), (b.x, b.y, hz + 0.75), (c2.x, c2.y, hz), (d2.x, d2.y, hz),
                         (a.x, a.y, hz + 0.9), (b.x, b.y, hz + 0.9), (c2.x, c2.y, hz + 0.15), (d2.x, d2.y, hz + 0.15)]
                faces = [(4, 5, 6, 7), (0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
                L.mesh(f'{name[4:]} porch roof', verts, faces, roof, r)
                L.beam(f'{name[4:]} porch beam', tuple(P(-1.75, -d * 0.5 - 2.0, 0).to_2d()) + (hz - 0.05,),
                       tuple(P(1.75, -d * 0.5 - 2.0, 0).to_2d()) + (hz - 0.05,), 0.24, 'timber_dark', r)
            elif kind == 'window_boxes':
                for xx in (-2.25, 2.25):
                    p = P(xx, -d * 0.5 - 0.42, 0)
                    z = r.matrix_world.translation.z + 3.3 + 4.25 - 1.05
                    L.planter_box(f'{name[4:]} window box', p.x, p.y, z, 1.7, 0.42, math.degrees(yaw), rng, r, height=0.34,
                                  mat='wood_planks_dark')
            elif kind == 'flower_border':
                for xx in (-3.6, 3.6):
                    p = P(xx, -d * 0.5 - 1.7, 0)
                    gz, _ = G.z(p.x, p.y)
                    L.planter_box(f'{name[4:]} front flower border', p.x, p.y, gz or 0.0, 2.6, 0.75, math.degrees(yaw), rng, r,
                                  height=0.45)
    added(op, s)
    log(f'{op}: variants on {len(cfg["variants"])} houses')


# ---------------------------------------------------------------------------
# 8. dressing clusters (Quaternius CC0 + recipes)
# ---------------------------------------------------------------------------
def op_clusters(cfg, G):
    op = cfg.get('op_id', 'story_clusters')
    s = len(L.NEW)
    rng = random.Random(cfg.get('seed', 7))
    owner = bpy.data.objects.get(cfg.get('owner', 'kit_city_vegetation'))
    for cl in cfg['clusters']:
        for it in cl['items']:
            kind = it['kind']
            x, y = it['at'] if 'at' in it else it['points'][0]
            yaw = it.get('yaw', 0.0)
            name = it.get('name') or f"{cl['id']} {kind.lower()}"
            if 'z_above' in it:
                gz_, _ = G.z(x, y)
                it = dict(it, z=(gz_ or 0.0) + it['z_above'])
            if kind == 'crystal_lamp':
                z, _ = G.z(x, y)
                L.crystal_lamp(name, x, y, z or 0.0, owner, s=it.get('scale', 1.0), seed=len(L.NEW),
                               arm_yaw=it.get('arm_yaw'), banner=it.get('banner', False))
            elif kind == 'planter_box':
                z, _ = G.z(x, y)
                L.planter_box(name, x, y, z or 0.0, it.get('length', 2.4), it.get('depth', 0.9), yaw, rng, owner,
                              height=it.get('height', 0.55), ground=G)
            elif kind == 'flowers':
                z, _ = G.z(x, y)
                L.flower_cluster(name, x, y, (z or 0.0), it.get('radius', 0.8), rng, owner, mounds=it.get('mounds', 4))
            elif kind == 'hedge':
                z, _ = G.z(x, y)
                L.hedge(name, it['at'], it['to'], owner, height=it.get('height', 1.0), width=it.get('width', 0.85),
                        z=z or 0.0, seed=len(L.NEW), ground=G)
            elif kind == 'log_pile':
                z, _ = G.z(x, y)
                z = z or 0.0
                a = math.radians(yaw)
                for row, count in enumerate((4, 3, 2)):
                    for k in range(count):
                        off = (k - (count - 1) * 0.5) * 0.5
                        cx, cy = x + math.cos(a + math.pi / 2) * off, y + math.sin(a + math.pi / 2) * off
                        zz = z + 0.24 + row * 0.42
                        p0 = (cx - math.cos(a) * 1.3, cy - math.sin(a) * 1.3, zz)
                        p1 = (cx + math.cos(a) * 1.3, cy + math.sin(a) * 1.3, zz)
                        L.lathe(f'{name} log', [(0.24, 0), (0.24, 2.6)], (0, 0, 0), 'timber_dark', owner, 10)
                        lg = L.NEW[-1]
                        lg.data.transform(Matrix.Rotation(math.pi / 2, 4, 'Y'))
                        lg.data.transform(Matrix.Translation((-1.3, 0, 0)))
                        lg.matrix_world = Matrix.Translation(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, zz)) @ Matrix.Rotation(a, 4, 'Z')
                        ck.uv_box(lg)
            elif kind == 'laundry_line':
                z, _ = G.z(x, y)
                z = z or 0.0
                x2, y2 = it['to']
                z2, _ = G.z(x2, y2)
                z2 = z2 or 0.0
                for (px, py, pz) in ((x, y, z), (x2, y2, z2)):
                    L.box(f'{name} post', (px, py, pz + 1.5), (0.2, 0.2, 3.1), 'timber_dark', owner, bevel=0.03)
                top = max(z, z2) + 2.85
                L.beam(f'{name} rope', (x, y, top), (x2, y2, top), 0.04, 'wood_planks_light', owner)
                n = 4
                ang = math.atan2(y2 - y, x2 - x)
                for k in range(n):
                    t = (k + 0.6) / (n + 0.2)
                    cx, cy = x + (x2 - x) * t, y + (y2 - y) * t
                    L.box(f'{name} sheet', (cx, cy, top - 0.62), (0.95, 0.04, 1.2),
                          ['cloth_cream', 'cloth_blue', 'cloth_cream', 'cloth_red'][k], owner, rot_z=ang, bevel=0.0)
            elif kind == 'notice_board':
                z, _ = G.z(x, y)
                z = z or 0.0
                a = math.radians(yaw)
                ux, uy = math.cos(a), math.sin(a)
                for sx in (-1, 1):
                    L.box(f'{name} post', (x + ux * sx * 1.25, y + uy * sx * 1.25, z + 1.4), (0.22, 0.22, 2.9), 'timber_dark', owner,
                          rot_z=a, bevel=0.03)
                L.box(f'{name} board', (x, y, z + 1.75), (2.4, 0.12, 1.5), 'wood_planks_light', owner, rot_z=a, bevel=0.02)
                L.box(f'{name} roof', (x, y, z + 2.88), (3.0, 0.8, 0.14), 'roof_slate_blue', owner, rot_z=a, bevel=0.02)
                for k, (dx, dz) in enumerate(((-0.7, 0.25), (0.05, 0.4), (0.7, 0.15), (-0.3, -0.35), (0.55, -0.3))):
                    L.box(f'{name} posted notice', (x + ux * dx - uy * 0.07, y + uy * dx + ux * 0.07, z + 1.75 + dz),
                          (0.42, 0.02, 0.52), 'cloth_cream', owner, rot_z=a, bevel=0.0)
            elif kind == 'telescope':
                z, _ = G.z(x, y)
                z = z or 0.0
                L.lathe(f'{name} tripod hub', [(0.12, 0), (0.12, 0.2)], (x, y, z + 1.25), 'metal_gold', owner, 10)
                for k in range(3):
                    a = math.radians(yaw + k * 120)
                    L.beam(f'{name} tripod leg', (x + math.cos(a) * 0.55, y + math.sin(a) * 0.55, z - 0.02), (x, y, z + 1.3),
                           0.06, 'timber_dark', owner)
                a = math.radians(yaw)
                L.beam(f'{name} brass tube', (x - math.cos(a) * 0.6, y - math.sin(a) * 0.6, z + 1.32),
                       (x + math.cos(a) * 0.9, y + math.sin(a) * 0.9, z + 1.62), 0.16, 'metal_gold', owner)
            elif kind == 'balustrade':
                z, _ = G.z(x, y)
                z = z or 0.0
                x2, y2 = it['to']
                n = max(2, int(math.hypot(x2 - x, y2 - y) / 0.55))
                ang = math.atan2(y2 - y, x2 - x)
                tops = []
                for k in range(n + 1):
                    t = k / n
                    px, py = x + (x2 - x) * t, y + (y2 - y) * t
                    pz, _ = G.z(px, py)
                    bz = pz if pz is not None else z
                    L.lathe(f'{name} baluster', [(0.13, 0), (0.08, 0.25), (0.13, 0.55), (0.07, 0.85), (0.12, 1.0)],
                            (px, py, bz - 0.02), 'stone_trim_carved', owner, 8)
                    tops.append(bz + 0.98)
                ra, rb = (x, y, tops[0] + 0.06), (x2, y2, tops[-1] + 0.06)
                L.beam(f'{name} rail', (ra[0] - math.cos(ang) * 0.15, ra[1] - math.sin(ang) * 0.15, ra[2]),
                       (rb[0] + math.cos(ang) * 0.15, rb[1] + math.sin(ang) * 0.15, rb[2]), 0.32, 'stone_trim_carved', owner, depth=0.16)
            elif kind == 'market_cross':
                z, _ = G.z(x, y)
                L.market_cross(name, x, y, z or 0.0, owner)
            elif kind == 'strip':
                global _TERRAIN
                if _TERRAIN is None:
                    _TERRAIN = importlib.import_module('terrain').TerrainBuilder(LAYOUT, bpy.data.collections.get('terrain'))
                before = set(bpy.data.objects)
                _TERRAIN.strip(name, it['points'], it['width'], it.get('material', 'cobble_path'), lift=0.065, curb=False)
                L.NEW.extend(o for o in bpy.data.objects if o not in before)
            elif kind == 'crest_banner':
                L.crest_banner(name, x, y, it['z_top'], it.get('width', 1.2), it.get('height', 2.6), yaw, owner)
            else:  # vendored Quaternius CC0 prop
                L.q_prop(kind, it.get('name') or f"{cl['id']} {kind} CC0", (x, y, it.get('z')), yaw, it.get('scale', 1.3), owner,
                         ground=G, sink=it.get('sink', 0.012))
    added(op, s)
    log(f'{op}: {len(cfg["clusters"])} clusters, {len(L.NEW) - s} parts')


# ---------------------------------------------------------------------------
# 9. plaza: mosaic bands, star tint, fountain beds
# ---------------------------------------------------------------------------
def paver_islands(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    seen = set()
    islands = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, faces = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            faces.append(g.index)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        islands.append(faces)
    bm.free()
    return islands


def op_plaza_mosaic(cfg, G):
    op = 'plaza_mosaic_and_borders'
    s = len(L.NEW)
    terrain_col = bpy.data.collections.get('terrain')
    removed_ranges = []
    for band in cfg['bands']:
        r_lo, r_hi = band['replace_radius']
        for mat in ('paver_surface', 'stone_accent_bluegrey', 'stone_trim_carved'):
            obj = bpy.data.objects.get(f'terrain / plaza pavers {mat}')
            if obj is None:
                continue
            me = obj.data
            isl = paver_islands(obj)
            kill = []
            for faces in isl:
                vs = {vi for fi in faces for vi in me.polygons[fi].vertices}
                c = np.mean([me.vertices[v].co[:2] for v in vs], axis=0)
                rr = float(np.hypot(*c))
                if r_lo <= rr <= r_hi:
                    kill.extend(faces)
            if kill:
                bm = bmesh.new()
                bm.from_mesh(me)
                bm.faces.ensure_lookup_table()
                before = sum(len(f.verts) - 2 for f in bm.faces)
                bmesh.ops.delete(bm, geom=[bm.faces[i] for i in kill], context='FACES')
                after = sum(len(f.verts) - 2 for f in bm.faces)
                bm.to_mesh(me)
                bm.free()
                CHANGES[op]['deleted_triangles'] += before - after
        removed_ranges.append((r_lo, r_hi))
        mosaic_band(band, terrain_col)
    tint_star(cfg.get('star', {}))
    for i, bed in enumerate(cfg.get('perimeter_beds', [])):
        zb, _ = G.z(bed['r'][0] * math.cos(math.radians(sum(bed['a']) / 2)), bed['r'][0] * math.sin(math.radians(sum(bed['a']) / 2)))
        L.arc_planter(f'garden stone planter perimeter bed {i + 1}', bed['r'][0], bed['r'][1], math.radians(bed['a'][0]),
                      math.radians(bed['a'][1]), (zb or 0.085) - 0.01, random.Random(700 + i), bpy.data.objects['kit_city_vegetation'],
                      height=0.62, seg=max(4, int(abs(bed['a'][1] - bed['a'][0]) / 2.5)))
    for i, bed in enumerate(cfg.get('fountain_beds', [])):
        L.arc_planter(f'fountain base bed {i + 1}', bed['r'][0], bed['r'][1], math.radians(bed['a'][0]), math.radians(bed['a'][1]),
                      1.0, random.Random(900 + i), bpy.data.objects['kit_plaza_fountain'], height=0.48, seg=12)
    added(op, s)
    G.rebuild()
    log(f'{op}: {len(cfg["bands"])} meander bands, star tint, {len(cfg.get("fountain_beds", []))} fountain beds')


MEANDER = ['XXXX', 'X...', 'X.XX', 'X..X', 'XXXX']  # rows top->bottom of one 4-cell period (running hook)


def mosaic_band(band, col):
    r0, r1 = band['radius']
    z = band.get('z', 0.088)
    rm = (r0 + r1) * 0.5
    cells_v = 5
    pad = band.get('border_m', 0.22)
    inner, outer = r0 + pad, r1 - pad
    cell_r = (outer - inner) / cells_v
    period_cells = 4
    period_len = cell_r * period_cells * band.get('aspect', 1.0)
    n_periods = max(8, int(round(math.tau * rm / period_len)))
    n_cols = n_periods * period_cells
    groups = {'line': ([], []), 'field': ([], []), 'border': ([], [])}

    def quad(kind, a0, a1, ra, rb, segs=1):
        verts, faces = groups[kind]
        base = len(verts)
        for k in range(segs + 1):
            a = a0 + (a1 - a0) * k / segs
            verts.append((ra * math.cos(a), ra * math.sin(a), z))
            verts.append((rb * math.cos(a), rb * math.sin(a), z))
        for k in range(segs):
            b = base + 2 * k
            faces.append((b, b + 2, b + 3, b + 1))

    da = math.tau / n_cols
    for c in range(n_cols):
        a0, a1 = c * da, (c + 1) * da
        col_in_period = c % period_cells
        for row in range(cells_v):
            ch = MEANDER[cells_v - 1 - row][col_in_period]
            ra, rb = inner + row * cell_r, inner + (row + 1) * cell_r
            quad('line' if ch == 'X' else 'field', a0, a1, ra, rb)
    nb = max(64, int(math.tau * r1 / 0.9))
    for k in range(nb):
        a0, a1 = k * math.tau / nb, (k + 1) * math.tau / nb
        quad('border', a0, a1, r0, inner)
        quad('border', a0, a1, outer, r1)
    mats = {'line': band.get('line_mat', 'stone_trim_carved'), 'field': band.get('field_mat', 'stone_accent_bluegrey'),
            'border': band.get('border_mat', 'stone_trim_carved')}
    tints = {'line': (1.0, 0.93, 0.76), 'field': (0.50, 0.64, 1.0), 'border': (0.95, 0.89, 0.76)}
    for kind, (verts, faces) in groups.items():
        o = ck.new_object(f"terrain / plaza pavers mosaic {band['id']} {kind}", verts, faces, mats[kind], col)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.to_mesh(o.data)
        bm.free()
        for p in o.data.polygons:
            if p.normal.z < 0:
                p.flip()
        ck.uv_box(o)
        ck.vertex_paint(o, tint=tints[kind], cavity=0.0, edge=0.0, jitter=0.0, seed=7)
        L.NEW.append(o)


def tint_star(star):
    """Tint existing pavers into an eight-point compass star aligned with the avenues."""
    if not star:
        return
    obj = bpy.data.objects.get('terrain / plaza pavers paver_surface')
    if obj is None:
        return
    me = obj.data
    col = me.color_attributes.get('Col')
    r_in, r_out = star['radius']
    rays = [math.atan2(a['to'][1], a['to'][0]) for a in LAYOUT['plaza']['avenues']]
    vpos = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', vpos)
    vpos = vpos.reshape(-1, 3)
    for faces in paver_islands(obj):
        vs = sorted({vi for fi in faces for vi in me.polygons[fi].vertices})
        c = vpos[vs].mean(axis=0)
        rr = float(np.hypot(c[0], c[1]))
        if not (r_in <= rr <= r_out):
            continue
        ang = math.atan2(c[1], c[0])
        t = (rr - r_in) / (r_out - r_in)
        half = math.radians(star['ray_half_deg']) * (1.0 - t) + math.radians(1.2) * t
        on_ray = any(abs((ang - a + math.pi) % math.tau - math.pi) <= half for a in rays)
        ring = abs(rr - star.get('ring_r', -10)) < star.get('ring_half_m', 0.0)
        if not (on_ray or ring):
            continue
        tint = star['ray_tint'] if on_ray else star['ring_tint']
        for fi in faces:
            for li in me.polygons[fi].loop_indices:
                cc = col.data[li].color
                col.data[li].color = (cc[0] * tint[0], cc[1] * tint[1], cc[2] * tint[2], 1.0)


# ---------------------------------------------------------------------------
# 10. market
# ---------------------------------------------------------------------------
def op_market(cfg, G, T):
    op = 'market_square'
    s = len(L.NEW)
    root = bpy.data.objects['kit_market_square']
    for slot in cfg['remove_stalls']:
        piv = bpy.data.objects.get(f'market stall {slot} pivot')
        if piv is not None:
            delete(desc(piv), op)
    for slot, (dx, dy, dyaw) in cfg['move_stalls'].items():
        piv = bpy.data.objects.get(f'market stall {slot} pivot')
        if piv is None:
            continue
        loc = piv.matrix_world.translation.copy()
        piv.matrix_world = Matrix.Translation(loc + Vector((dx, dy, 0))) @ Matrix.Rotation(piv.matrix_world.to_euler().z + math.radians(dyaw), 4, 'Z')
        CHANGES[op]['moved_objects'] += 1
    cart = bpy.data.objects.get('market stall 1-1 Quaternius CC0 stall cart')
    if cart is not None and cfg.get('move_cart'):
        dx, dy, dyaw = cfg['move_cart']
        e = cart.matrix_world.to_euler()
        loc = cart.matrix_world.translation.copy() + Vector((dx, dy, 0))
        sc = cart.matrix_world.to_scale()
        cart.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(e.z + math.radians(dyaw), 4, 'Z') @ Matrix.Diagonal((sc.x, sc.y, sc.z, 1))
    # trim the east avenue strip and its curbs where the paved square now covers them
    def inside(px, py, poly):
        c = False
        j = len(poly) - 1
        for i in range(len(poly)):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi:
                c = not c
            j = i
        return c
    sq = [tuple(p) for p in cfg['square_poly']]
    for o in meshes_named(r'^terrain / avenue east_market'):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        mw = o.matrix_world
        kill = [f for f in bm.faces if inside(*(mw @ f.calc_center_median()).to_2d(), sq)]
        if kill:
            CHANGES[op]['deleted_triangles'] += sum(len(f.verts) - 2 for f in kill)
            bmesh.ops.delete(bm, geom=kill, context='FACES')
            bm.to_mesh(o.data)
        bm.free()
    # de-glow produce
    for o in meshes_named(r'^market stall .* produce'):
        for i, m in enumerate(o.data.materials):
            if m and m.name == 'magic_green':
                o.data.materials[i] = ck.get_material('foliage_sun')
            elif m and m.name == 'metal_gold':
                o.data.materials[i] = ck.get_material('flower_gold')
    # paved square draped on the terrain heights (walk surface family "terrain / path ...")
    poly = [tuple(p) for p in cfg['square_poly']]
    def mesh_h(x, y):
        z, _ = G.z(x, y)
        return z if z is not None else float(T.h(np.array([[x]]), np.array([[y]]))[0, 0])
    L.draped_area('terrain / path market square', poly, 'cobble_path', mesh_h, lift=0.08, cell=1.5)
    ck.uv_box(L.NEW[-1])
    border = poly + [poly[0]]
    T.strip('terrain / path market border', border, 0.9, 'stone_accent_bluegrey', lift=0.075, curb=False)
    added(op, s)
    # snap every remaining stall onto the new paving
    G.rebuild()
    for piv in [o for o in desc(root) if o.type == 'EMPTY' and o.name.endswith(' pivot')]:
        parts = [o for o in desc(piv) if o.type == 'MESH']
        if not parts:
            continue
        w = np.concatenate([world_verts(o) for o in parts])
        lo, hi = w.min(axis=0), w.max(axis=0)
        zs = [G.z(float(x), float(y))[0] for x in np.linspace(lo[0], hi[0], 4) for y in np.linspace(lo[1], hi[1], 4)]
        zs = [z for z in zs if z is not None]
        if zs:
            translate([piv], (0, 0, min(zs) - 0.02 - float(w[:, 2].min())), op)
    if cart is not None:
        w = world_verts(cart)
        c = w.mean(axis=0)
        z, _ = G.z(float(c[0]), float(c[1]))
        if z is not None:
            translate([cart], (0, 0, z - 0.012 - float(w[:, 2].min())), op)
    log(f'{op}: square paved, {len(cfg["remove_stalls"])} stalls removed, produce de-glowed')


# ---------------------------------------------------------------------------
# 11. gate
# ---------------------------------------------------------------------------
def op_gate(cfg, G):
    op = 'gate_crystal_pillars'
    s = len(L.NEW)
    root = bpy.data.objects['kit_town_gate']
    for st in meshes_named(r'^gate guardian statue', root):
        w = world_verts(st)
        c = w.mean(axis=0)
        x, y, z = float(c[0]), float(c[1]), float(w[:, 2].min())
        delete([st], op)
        L.lathe('gate guardian statue crystal pillar shaft', [(0.95, 0), (1.05, 0.25), (0.82, 0.55), (0.74, 3.2), (0.92, 3.45), (0.0, 3.45)],
                (x, y, z - 0.03), 'stone_trim_carved', root, 8)
        L.lathe('gate guardian statue crystal pillar cup', [(0.55, 0), (1.05, 0.42), (0.98, 0.62), (0.0, 0.62)],
                (x, y, z + 3.38), 'metal_gold', root, 16)
        L.lathe('gate guardian statue crystal', [(0.0, 0), (0.72, 0.35), (0.62, 2.2), (0.0, 3.0)],
                (x, y, z + 3.80), 'magic_blue', root, 8, paint=False)
        L.lathe('gate guardian statue crystal crown', [(0.86, 0), (0.95, 0.22), (0.18, 0.95), (0.0, 1.0)],
                (x, y, z + 6.55), 'roof_slate_blue', root, 8)
        # banner on the plinth's road-facing front (-Y, south)
        L.crest_banner('gate plinth crest banner', x, y - 2.04, z - 0.25, 2.2, 3.0, 0.0, root)
    added(op, s)
    log(f'{op}: blob statues replaced by crystal pillar lanterns with crest banners')


# ---------------------------------------------------------------------------
# 12. generic snap of remaining small floating groups
# ---------------------------------------------------------------------------
def op_snap_floaters(cfg):
    op = 'floating_groups_snapped'
    allow = re.compile(cfg['allow_pattern'])
    total = 0
    for it in range(cfg.get('iterations', 3)):
        rep = lint.run_lint('city', log=lambda *_: None)
        floaters = [f for f in rep['findings'] if f['rule'] == 'L1' and not f['intentional']]
        if not floaters:
            break
        moved = 0
        # support set: everything except the floating group itself
        all_meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.name.startswith(ck.RUNTIME_PREFIXES)]
        float_names = {m for f in floaters for m in f.get('all_members', f['members'])}
        verts, polys, base = [], [], 0
        for o in all_meshes:
            if o.name in float_names:
                continue
            w = world_verts(o)
            verts.extend(map(tuple, w))
            polys.extend(tuple(base + i for i in p.vertices) for p in o.data.polygons)
            base += len(w)
        tree = BVHTree.FromPolygons(verts, polys)
        for f in floaters:
            names = f.get('all_members', f['members'])
            if len(names) > cfg.get('max_members', 60) or not allow.search(' | '.join(names)):
                continue
            objs = [bpy.data.objects[n] for n in names if n in bpy.data.objects]
            w = np.concatenate([world_verts(o) for o in objs])
            if len(w) > 600:
                w = w[np.linspace(0, len(w) - 1, 600).astype(int)]
            best = None
            reach = cfg.get('max_snap_m', 1.2)
            for pat, dist in cfg.get('reach_overrides', {}).items():
                if re.search(pat, ' | '.join(names)):
                    reach = max(reach, dist)
            for v in w:
                hit = tree.find_nearest(Vector(v), reach)
                if hit[0] is not None and (best is None or hit[3] < best[2]):
                    best = (Vector(v), hit[0], hit[3])
            if best is None or best[2] < 1e-4:
                continue
            vec = (best[1] - best[0])
            vec = vec * ((vec.length + cfg.get('embed_m', 0.012)) / vec.length)
            translate(objs, vec, op)
            moved += 1
            CHANGES[op]['notes'].append(f"{f['id']}: {tuple(round(c, 3) for c in vec)}")
        total += moved
        log(f'{op}: pass {it + 1} snapped {moved} groups')
        if not moved:
            break
    log(f'{op}: {total} groups snapped in total')


def op_meadow_drifts(cfg, G):
    """Wildflower drifts in the large empty lawns: only where an 4.5 m disc is pure grass (no path, prop or building)."""
    op = 'meadow_flower_drifts'
    s0 = len(L.NEW)
    rng = random.Random(cfg.get('seed', 4404))
    verts, polys, owner, base = [], [], [], 0
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or o.name.startswith(ck.RUNTIME_PREFIXES) or 'cliff underside' in o.name or 'stalactite' in o.name:
            continue
        w = world_verts(o)
        verts.extend(map(tuple, w))
        for p in o.data.polygons:
            polys.append(tuple(base + i for i in p.vertices))
            owner.append(o.name)
        base += len(w)
    tree = BVHTree.FromPolygons(verts, polys)

    def grass(x, y):
        hit = tree.ray_cast(Vector((x, y, 120.0)), Vector((0, 0, -1)), 300.0)
        return hit[0] is not None and owner[hit[2]] == 'terrain / grass ground'

    palettes = [['flower_ivory', 'flower_lilac'], ['flower_gold', 'flower_ivory'], ['foliage_blossom', 'flower_ivory'],
                ['flower_lilac', 'foliage_blossom'], ['flower_gold', 'foliage_blossom']]
    placed = []
    for patch in cfg['patches']:
        x0, y0, x1, y1 = patch['bbox']
        step = patch.get('spacing', 11.0)
        in_patch = 0
        y = y0 + step * 0.5
        while y < y1:
            x = x0 + step * 0.5 + (rng.uniform(-0.5, 0.5) * step * 0.3)
            while x < x1:
                cx, cy = x + rng.uniform(-2.5, 2.5), y + rng.uniform(-2.5, 2.5)
                ring = [(cx + 4.5 * math.cos(a), cy + 4.5 * math.sin(a)) for a in np.linspace(0, math.tau, 10, endpoint=False)]
                if (in_patch < cfg.get('max_per_patch', 4) and grass(cx, cy) and all(grass(px, py) for px, py in ring)
                        and all(math.hypot(cx - qx, cy - qy) > cfg.get('min_gap_m', 14.0) for qx, qy in placed)):
                    in_patch += 1
                    z, _ = G.z(cx, cy)
                    pal = palettes[len(placed) % len(palettes)]
                    n = rng.randint(3, 5)
                    for k in range(n):
                        a = rng.uniform(0, math.tau)
                        r = rng.uniform(0.0, 2.4)
                        mx, my = cx + math.cos(a) * r, cy + math.sin(a) * r
                        mz, _ = G.z(mx, my)
                        L.flower_cluster(f'meadow drift {len(placed) + 1}', mx, my, (mz if mz is not None else z or 0.0) - 0.02,
                                         0.7, rng, bpy.data.objects['kit_city_vegetation'], mounds=1, palette=pal)
                    placed.append((cx, cy))
                x += step
            y += step
    added(op, s0)
    CHANGES[op]['notes'].append(f'{len(placed)} drifts at ' + ', '.join(f'({round(px, 1)}, {round(py, 1)})' for px, py in placed))
    log(f'{op}: {len(placed)} drifts')


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
LAYOUT: dict = {}
_TERRAIN = None


# ---------------------------------------------------------------------------
# 9. pass-4 repairs (r6-finish, 2026-10-03): canopies in walls, coincident faces, edge-gap skirts
# ---------------------------------------------------------------------------
def _bvh(objs, face_filter=None):
    verts, polys, base = [], [], 0
    for o in objs:
        w = world_verts(o)
        verts.extend(map(tuple, w))
        mw3 = o.matrix_world.to_3x3()
        for p in o.data.polygons:
            if face_filter is None or face_filter((mw3 @ p.normal).normalized()):
                polys.append(tuple(base + i for i in p.vertices))
        base += len(w)
    return BVHTree.FromPolygons(verts, polys) if polys else None


def op_canopy_clear(cfg):
    """Remove trees whose canopy cuts into a building, wall or the vertical face of a terrace (visible cut)."""
    op = 'canopies_clear_of_walls'
    comps, info = tree_components()
    rx_b, rx_t = re.compile(cfg['building_pattern']), re.compile(cfg['terrace_pattern'])
    scene = [o for o in bpy.context.scene.objects if o.type == 'MESH' and len(o.data.polygons)]
    b_tree = _bvh([o for o in scene if rx_b.search(o.name)])
    t_tree = _bvh([o for o in scene if rx_t.search(o.name)], lambda n: abs(n.z) < 0.35)
    removed = 0
    for tname, members in sorted(comps.items()):
        canopy = [m for m in members if m.name != tname]
        c_tree = _bvh(canopy) if canopy else None
        if c_tree is None:
            continue
        hits = sum(len(c_tree.overlap(t)) for t in (b_tree, t_tree) if t is not None)
        if hits >= cfg.get('min_hits', 4):
            w = info[tname]
            delete(members, op)
            removed += 1
            CHANGES[op]['notes'].append(f'removed {tname} at {rt(float(w[:, 0].mean()), float(w[:, 1].mean()))}: canopy cuts {hits} wall faces')
    log(f'{op}: {removed} trees removed')


def op_resolve_coplanar(cfg):
    """L4 repair. Decals are lifted clear of the face they decorate; then every face fully hidden under a
    coincident same-facing face of another mesh is deleted. Walk surfaces outrank everything else, and a
    face relied on as cover is never deleted, so the visible surface is unchanged and no hole opens."""
    import bmesh
    op = 'coincident_faces_removed'
    rx_decal, rx_cover = re.compile(cfg['decal_pattern']), re.compile(cfg['cover_pattern'])
    for o in sorted(meshes_named(cfg['decal_pattern']), key=lambda o: o.name):
        translate([o], (0, 0, cfg['decal_lift_m']), op)
        CHANGES[op]['notes'].append(f"{o.name}: decal lifted {cfg['decal_lift_m']} m")
    bpy.context.view_layer.update()
    prof = lint.PROFILES['city']
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not prof['skip'].search(o.name) and len(o.data.polygons)]
    parts = [lint.Part(o, i) for i, o in enumerate(meshes)]
    detail = []
    lint.coplanar_overlaps(parts, lambda *_: None, detail=detail)

    def rank(name):
        if rx_decal.search(name):
            return 5
        if name.startswith('terrain / grass ground'):
            return 3
        if L._WALK.search(name):
            return 4
        return 2 if rx_cover.search(name) else 1
    cover = defaultdict(list)
    for (oa, ob), (ta, tb), ar in detail:
        ra, rb = rank(parts[oa].name), rank(parts[ob].name)
        if ra <= rb:  # a face may only be hidden by an equal or higher-ranked face (walk surfaces never lose)
            cover[(oa, ta)].append(((ob, tb), ar))
        if rb <= ra:
            cover[(ob, tb)].append(((oa, ta), ar))

    def area(k):
        p = parts[k[0]]
        a, b, c = p.verts[p.tris[k[1]]]
        return 0.5 * float(np.linalg.norm(np.cross(b - a, c - a)))
    dead, support = set(), set()
    for k in sorted(cover, key=lambda k: (rank(parts[k[0]].name), parts[k[0]].name, k[1])):
        if k in support:
            continue
        ws = [(w, ar) for w, ar in cover[k] if w not in dead]
        if sum(ar for _w, ar in ws) >= cfg['min_cover'] * area(k):
            dead.add(k)
            support.update(w for w, _ar in ws)
    by_obj = defaultdict(set)
    for oi, ti in dead:
        by_obj[oi].add(ti)
    faces = 0
    for oi in sorted(by_obj, key=lambda i: parts[i].name):
        o, ts = parts[oi].obj, by_obj[oi]
        me = o.data
        per_poly = defaultdict(list)
        for lt in me.loop_triangles:
            per_poly[lt.polygon_index].append(lt.index)
        kill = sorted(pi for pi, lts in per_poly.items() if all(x in ts for x in lts))
        if not kill:
            continue
        if me.users > 1:
            o.data = me = me.copy()
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        geom = [bm.faces[pi] for pi in kill]
        CHANGES[op]['deleted_triangles'] += sum(len(f.verts) - 2 for f in geom)
        bmesh.ops.delete(bm, geom=geom, context='FACES')
        bm.to_mesh(me)
        bm.free()
        faces += len(kill)
        CHANGES[op]['notes'].append(f'{o.name}: {len(kill)} hidden coincident faces deleted')
    log(f'{op}: {len(detail)} coincident triangle pairs, {faces} hidden faces deleted on {len(by_obj)} meshes')


def op_edge_gap_skirts(cfg):
    """L1b repair: a base that touches the ground on one side and hangs over a drop on the other gets its
    lowest ring extended straight down by the measured gap (+ embed), so no daylight shows under it."""
    op = 'edge_gap_skirts'
    rep = lint.run_lint('city', log=lambda *_: None)
    for f in rep['findings']:
        if f['rule'] != 'L1b':
            continue
        drop = float(f['gap_m']) + cfg['embed_m']
        for name in f['members']:
            o = bpy.data.objects.get(name)
            if o is None or o.type != 'MESH':
                continue
            if o.data.users > 1:
                o.data = o.data.copy()
            w = world_verts(o)
            low = w[:, 2] < w[:, 2].min() + cfg['ring_tol_m']
            w[low, 2] -= drop
            inv = np.array(o.matrix_world.inverted())
            loc = w @ inv[:3, :3].T + inv[:3, 3]
            o.data.vertices.foreach_set('co', loc.reshape(-1))
            o.data.update()
            CHANGES[op]['moved_objects'] += 1
            CHANGES[op]['notes'].append(f'{name}: {int(low.sum())} base vertices extended {drop:.2f} m down')
    log(f'{op}: {CHANGES[op]["moved_objects"]} bases skirted')


def main():
    global LAYOUT
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--pass-tag', default='')
    ap.add_argument('--no-save', action='store_true')
    a = ap.parse_args(argv)
    src = Path(bpy.data.filepath).resolve()
    if src != SOURCE.resolve() or sha(src) != SOURCE_SHA:
        raise RuntimeError('Load the exact selected R5 master (market-repair-candidate, bda8d785...).')
    LAYOUT = json.loads(LAYOUT_R6.read_text(encoding='utf-8'))
    ops = LAYOUT['r6_dressing']['operations']
    before_tris = tris([o for o in bpy.context.scene.objects if o.type == 'MESH'])
    lint_before = lint.run_lint('city', log=lambda *_: None)
    G = L.Ground()
    T = None
    for opcfg in ops:
        kind = opcfg['op']
        if not opcfg.get('enabled', True):
            continue
        if kind == 'dedupe':
            op_dedupe(opcfg)
        elif kind == 'reparent_orphans':
            op_reparent_orphans(opcfg)
        elif kind == 'delete':
            op_delete(opcfg)
        elif kind == 'fountain_foot':
            op_fountain_foot(opcfg)
        elif kind == 'gate_merlons':
            op_gate_merlons(opcfg)
        elif kind == 'lift_mortar':
            op_lift_mortar(opcfg)
        elif kind == 'rose_window':
            op_rose_window(opcfg)
        elif kind == 'coplanar_insets':
            op_coplanar_insets(opcfg)
        elif kind == 'simplify_hardware':
            op_simplify_hardware(opcfg)
        elif kind == 'houses':
            op_houses(opcfg, G)
        elif kind == 'reroute_paths':
            T = op_reroute_paths(opcfg, G)
        elif kind == 'relocate_lamps':
            op_relocate_lamps(opcfg, G)
        elif kind == 'bridge_lamps':
            op_bridge_lamps(opcfg, G)
        elif kind == 'trees':
            op_trees(opcfg, G)
        elif kind == 'plaza_mosaic':
            op_plaza_mosaic(opcfg, G)
        elif kind == 'market':
            if T is None:
                T = importlib.import_module('terrain').TerrainBuilder(LAYOUT, bpy.data.collections.get('terrain'))
            op_market(opcfg, G, T)
        elif kind == 'gate':
            op_gate(opcfg, G)
        elif kind == 'house_variants':
            op_house_variants(opcfg, G)
        elif kind == 'clusters':
            op_clusters(opcfg, G)
            G.rebuild()
        elif kind == 'meadow_drifts':
            op_meadow_drifts(opcfg, G)
        elif kind == 'snap_floaters':
            op_snap_floaters(opcfg)
        elif kind == 'canopy_clear':
            op_canopy_clear(opcfg)
        elif kind == 'resolve_coplanar':
            op_resolve_coplanar(opcfg)
        elif kind == 'edge_gap_skirts':
            op_edge_gap_skirts(opcfg)
        else:
            raise RuntimeError(f'unknown op {kind}')
        bpy.context.view_layer.update()
    # templates are not scene objects; make sure none were left linked
    for o in list(bpy.data.objects):
        if o.name.startswith('r6 template ') and o.users_collection:
            for c in list(o.users_collection):
                c.objects.unlink(o)
    after_tris = tris([o for o in bpy.context.scene.objects if o.type == 'MESH'])
    lint_after = lint.run_lint('city', log=lambda *_: None)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    receipt = {
        'schema': 'xexoria.city-r6-dressing-candidate/1', 'status': 'CANDIDATE_NOT_ADMITTED',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'blender': bpy.app.version_string,
        'source': {'path': SOURCE.relative_to(ROOT).as_posix(), 'sha256': SOURCE_SHA, 'saved': False},
        'layout': {'path': LAYOUT_R6.relative_to(ROOT).as_posix(), 'sha256': sha(LAYOUT_R6)},
        'source_triangles': before_tris, 'candidate_triangles': after_tris,
        'operations': {k: v for k, v in CHANGES.items()},
        'lint_before': {'defects': lint_before['defects'], 'intentional': lint_before['intentional']},
        'lint_after': {'defects': lint_after['defects'], 'intentional': lint_after['intentional']},
        'log': LOG,
    }
    if not a.no_save:
        tex = ROOT / 'assets/models/reference-city/r5/textures'
        q = ROOT / 'assets/third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF'
        for img in bpy.data.images:
            raw = img.filepath.replace(chr(92), '/') if img.filepath else ''
            nm = raw.rsplit('/', 1)[-1] if raw else img.name
            if (tex / nm).is_file():
                img.filepath = '//../r5/textures/' + nm
            elif (q / nm).is_file():
                img.filepath = '//../../../third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF/' + nm
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(CANDIDATE), check_existing=False, relative_remap=False, copy=True)
        if sha(SOURCE) != SOURCE_SHA:
            raise RuntimeError('The R5 source changed during derivation.')
        receipt['candidate'] = {'path': CANDIDATE.relative_to(ROOT).as_posix(), 'sha256': sha(CANDIDATE), 'bytes': CANDIDATE.stat().st_size}
    rec = OUT_DIR / f'derivation-receipt{a.pass_tag and "-" + a.pass_tag}.json'
    rec.write_text(json.dumps(receipt, indent=1) + '\n', encoding='utf-8')
    log(f'triangles {before_tris} -> {after_tris}; lint {lint_before["defects"]} -> {lint_after["defects"]}')


if __name__ == '__main__':
    main()
