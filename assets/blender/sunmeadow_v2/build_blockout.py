"""Sunmeadow v2 whole-map BLOCKOUT — Blender 5.2 headless driver (Claude map lane, 2026-10-02).

Every coordinate comes from planning/levels/sunmeadow-v2-layout.json (via sm2_build); compact v1 supplies the
existing prop IDs/positions and spawn anchors. Blender (x, y, z) = Babylon (-x, -z, y).

Run from the repo root:
  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup \\
      --python assets/blender/sunmeadow_v2/build_blockout.py -- \\
      --out assets/models/sunmeadow-v2/blockout --raw <scratch>/raw/pass1 --pass 1 --samples 20 --device CPU
Options: --no-render, --no-export, --views a,b,c
"""
from __future__ import annotations

import json
import math
import struct
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sm2_build as B  # noqa: E402
import sm2_export as X  # noqa: E402
import sm2_geom as G  # noqa: E402
import sm2_sightlines as SL  # noqa: E402
from sm2_items import witness_mesh  # noqa: E402
from sm2_meshes import EXPORT_LAYERS  # noqa: E402
from sm2_site import ROOT  # noqa: E402

CAM_RADIUS, CAM_BETA, CAM_FOV, CAM_TARGET = 13.0, 1.18, 1.02, 1.65
ARENA_TOP_M, ARENA_TOP_RES = 34.0, 1020      # arena close-up ortho: 34 x 34 m at 30 px/m (12 m keep-clear + moved props)

from sm2_materials import EMISSIVE, MATS, METAL  # noqa: E402


def parse_args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    a = {'out': 'assets/models/sunmeadow-v2/blockout', 'raw': None, 'pass': 1, 'samples': 20, 'device': 'CPU',
         'render': True, 'export': True, 'views': None, 'blend': False, 'blend_path': None,
         'evidence': 'planning/evidence/sunmeadow-v2-blockout'}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip('-')
        if k in ('no-render', 'no-export', 'no-blend'):
            a[k[3:]] = False
            i += 1
            continue
        a[k] = argv[i + 1]
        i += 2
    a['samples'] = int(a['samples'])
    a['pass'] = int(a['pass'])
    out = Path(a['out'])
    a['out'] = out if out.is_absolute() else ROOT / out
    if a['raw']:
        raw = Path(a['raw'])
        a['raw'] = raw if raw.is_absolute() else ROOT / raw
    ev = Path(a['evidence'])
    a['evidence'] = ev if ev.is_absolute() else ROOT / ev
    if a['blend_path']:
        a['blend'] = True
    if a['views']:
        a['views'] = [v.strip() for v in a['views'].split(',') if v.strip()]
    return a


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def make_material(name):
    hexv, rough = MATS.get(name, ('#ff00ff', 0.5))
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    rgb = [srgb_to_linear(int(hexv[i:i + 2], 16) / 255) for i in (1, 3, 5)]
    bsdf.inputs['Base Color'].default_value = (*rgb, 1.0)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = METAL.get(name, 0.0)
    if name in EMISSIVE:
        bsdf.inputs['Emission Color'].default_value = (*rgb, 1.0)
        bsdf.inputs['Emission Strength'].default_value = EMISSIVE[name]
    mat.diffuse_color = (*rgb, 1.0)
    return mat


def collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in (parent or bpy.context.scene.collection).children:
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def mesh_object(name, verts, faces, mat, smooth, col, uv_scale=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(clean_customdata=False)
    me.update()
    if smooth:
        me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    if uv_scale:
        uv = me.uv_layers.new(name='UVMap')
        co = [0.0] * (len(me.vertices) * 3)
        me.vertices.foreach_get('co', co)
        loops = [0] * len(me.loops)
        me.loops.foreach_get('vertex_index', loops)
        data = []
        for vi in loops:
            data += [-co[3 * vi] / uv_scale, -co[3 * vi + 1] / uv_scale]   # Babylon world XZ / tile
        uv.data.foreach_set('uv', data)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def build_scene(res, log):
    S = res['scene']
    mats = {}
    cols = {}
    objs = []
    for (cell, layer, mname), acc in sorted(S.acc.items()):
        if not acc.faces:
            continue
        if mname not in mats:
            mats[mname] = make_material(mname)
        key = f'SM2_{layer}'
        if key not in cols:
            cols[key] = collection(key)
        name = f'{cell}__{layer}__{mname}'
        uv = 6.0 if layer in ('ground', 'path') else None
        ob = mesh_object(name, acc.verts, acc.faces, mats[mname], acc.smooth, cols[key], uv)
        ob['cell'], ob['layer'], ob['material_key'] = cell, layer, mname
        objs.append(ob)
    # Colliders: own collection, never rendered or exported.
    ccol = collection('SM2_colliders')
    cmat = make_material('collider')
    for c in res['cols'].items + res['cols'].existing:
        poly = c['polygon_xz']
        y0, y1 = max(-1.0, c['y_min']), min(c['y_max'], 20.0)
        v, f = __import__('sm2_items').extrude_polygon([tuple(q) for q in poly], y0, y1)
        ob = mesh_object(f"COL_{c['id']}", v, f, cmat, False, ccol)
        ob.display_type = 'WIRE'
        ob.hide_render = True
        ob['collider_json_id'] = c['id']
        ob['visual'] = c['visual']
    log(f'objects={len(objs)} materials={len(mats)} colliders={len(res["cols"].items) + len(res["cols"].existing)}')
    return objs


def export_cells(objs, out: Path, per_cell, log):
    """Explicit-option GLB export per 64 m cell + re-import validation (sm2_export)."""
    results, options = X.export_cells(objs, out, per_cell, B.sha, rel, log, EXPORT_LAYERS)
    return results, options


# ----------------------------------------------------------------------------
# Lighting, cameras, views
# ----------------------------------------------------------------------------

def setup_render(samples, device):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU' if str(device).upper() == 'CPU' else 'GPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.transparent_max_bounces = 4
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.resolution_percentage = 100
    sc.render.use_persistent_data = True
    chosen = None
    for vt in ('ACES 2.0', 'ACES 1.3', 'ACES', 'AgX', 'Filmic', 'Standard'):
        try:
            sc.view_settings.view_transform = vt
            chosen = vt
            break
        except TypeError:
            continue
    try:
        sc.view_settings.look = 'None'
    except TypeError:
        pass
    sc.view_settings.exposure = 0.0
    # World: gradient sky for camera rays, soft blue uniform fill for lighting.
    world = bpy.data.worlds.new('sm2_sky')
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new('ShaderNodeOutputWorld')
    mix = nodes.new('ShaderNodeMixShader')
    fill = nodes.new('ShaderNodeBackground')
    fill.inputs['Color'].default_value = (0.42, 0.56, 0.82, 1.0)
    fill.inputs['Strength'].default_value = 0.85
    sky = nodes.new('ShaderNodeBackground')
    sky.inputs['Strength'].default_value = 1.0
    tc = nodes.new('ShaderNodeTexCoord')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.80, 0.86, 0.93, 1.0)
    ramp.color_ramp.elements[1].position = 0.55
    ramp.color_ramp.elements[1].color = (0.30, 0.48, 0.80, 1.0)
    lp = nodes.new('ShaderNodeLightPath')
    links.new(tc.outputs['Generated'], sep.inputs['Vector'])
    links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], sky.inputs['Color'])
    links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(fill.outputs['Background'], mix.inputs[1])
    links.new(sky.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], out.inputs['Surface'])
    sc.world = world
    # Sun: warm key from the south-east at 55 degrees.
    el = math.radians(55.0)
    to_sun_b = (math.cos(el) * 0.70711, math.sin(el), -math.cos(el) * 0.70711)   # Babylon (x east, y up, z north)
    to_sun = Vector((-to_sun_b[0], -to_sun_b[2], to_sun_b[1]))
    sun = bpy.data.lights.new('sm2_sun', 'SUN')
    sun.energy = 4.2
    sun.angle = math.radians(1.6)
    sun.color = (1.0, 0.93, 0.82)
    so = bpy.data.objects.new('sm2_sun', sun)
    so.rotation_euler = (-to_sun).to_track_quat('-Z', 'Y').to_euler()
    sc.collection.objects.link(so)
    return chosen


def ray_hits_structure(origin, target, depsgraph):
    """First non-vegetation hit between origin and target (canopies never block the camera)."""
    d = target - origin
    dist = d.length
    d.normalize()
    o = origin.copy()
    travelled = 0.0
    for _ in range(24):
        hit, loc, nrm, idx, ob, mtx = bpy.context.scene.ray_cast(depsgraph, o, d, distance=dist - travelled)
        if not hit:
            return None
        if ob is not None and (ob.get('layer') in ('veg', 'annotation') or ob.name.startswith(('W_', 'COL_'))):
            step = (loc - o).length + 0.02
            o = loc + d * 0.02
            travelled += step
            continue
        return (loc - origin).length
    return None


def game_camera(name, feet_xz, yaw, depsgraph, ground_y=0.0):
    tb = (feet_xz[0], ground_y + CAM_TARGET, feet_xz[1])
    fwd = (math.sin(yaw), math.cos(yaw))
    hd, vd = CAM_RADIUS * math.sin(CAM_BETA), CAM_RADIUS * math.cos(CAM_BETA)
    cb = (tb[0] - fwd[0] * hd, tb[1] + vd, tb[2] - fwd[1] * hd)
    target = Vector(G.bl(tb[0], tb[2], tb[1]))
    pos = Vector(G.bl(cb[0], cb[2], cb[1]))
    hit = ray_hits_structure(target, pos, depsgraph)
    boom = CAM_RADIUS
    if hit is not None and hit < CAM_RADIUS:
        boom = max(2.5, hit - 0.4)
        pos = target + (pos - target).normalized() * boom
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    cam.data.sensor_fit = 'VERTICAL'
    cam.data.angle_y = CAM_FOV
    cam.data.clip_start, cam.data.clip_end = 0.1, 600.0
    cam.location = pos
    cam.rotation_euler = (target - pos).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.collection.objects.link(cam)
    return cam, {'type': 'game', 'feet_xz': list(feet_xz), 'yaw': round(yaw, 4), 'radius': CAM_RADIUS, 'beta': CAM_BETA,
                 'fov_y': CAM_FOV, 'target_h': CAM_TARGET, 'boom_m': round(boom, 2), 'collided': hit is not None and hit < CAM_RADIUS,
                 'camera_babylon': [round(-pos.x, 2), round(pos.z, 2), round(-pos.y, 2)]}


def look_camera(name, eye_b, at_b, fov=CAM_FOV):
    """eye_b/at_b are Babylon (x, y, z)."""
    pos = Vector(G.bl(eye_b[0], eye_b[2], eye_b[1]))
    tgt = Vector(G.bl(at_b[0], at_b[2], at_b[1]))
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    cam.data.sensor_fit = 'VERTICAL'
    cam.data.angle_y = fov
    cam.data.clip_start, cam.data.clip_end = 0.05, 600.0
    cam.location = pos
    cam.rotation_euler = (tgt - pos).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.collection.objects.link(cam)
    return cam, {'type': 'look', 'eye_babylon': list(eye_b), 'at_babylon': list(at_b), 'fov_y': fov}


def top_camera(site, name='cam_top', centre_xz=None, size_m=None, res=None):
    """Orthographic top view, image up = Babylon north. Default: the whole stage at 6 px/m; with centre_xz/size_m/res
    a square close-up (e.g. the boss arena) at res[0] / size_m px per metre."""
    x0, x1, z0, z1 = site.stage
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = size_m if size_m else max(x1 - x0, z1 - z0)
    cam.data.clip_start, cam.data.clip_end = 1.0, 400.0
    cx, cz = centre_xz if centre_xz else ((x0 + x1) / 2, (z0 + z1) / 2)
    cam.location = Vector(G.bl(cx, cz, 200.0))
    cam.rotation_euler = (0.0, 0.0, math.pi)     # image up = Babylon north
    bpy.context.scene.collection.objects.link(cam)
    if centre_xz:
        return cam, {'type': 'ortho_close', 'centre_xz': [cx, cz], 'size_m': size_m, 'res': list(res),
                     'px_per_m': round(res[0] / size_m, 4)}
    return cam, {'type': 'ortho_top', 'stage': [x0, x1, z0, z1], 'px_per_m': 6.0}


def add_witness(name, x, z, yaw=0.0, base_y=0.0):
    v, f = witness_mesh()
    vv = G.transform(v, rot=math.pi - yaw, offset=G.bl(x, z, base_y))
    col = collection('SM2_witness')
    ob = mesh_object(name, vv, f, bpy.data.materials.get('witness') or make_material('witness'), True, col)
    ob['layer'] = 'witness'
    return ob


def view_specs(site):
    """(name, kind, label, spec) — positions from the layout JSON and the placed landmarks."""
    sl = {s['to']: s for s in site.sightline_points()}
    wm2 = site.pois['windmark_2']
    altar = site.landmarks['windstone_altar']['position_xz']
    cc = tuple(float(v) for v in site.landmarks['windstone_circle']['center_xz'])

    def on_path(p):
        """p when it already stands on a path surface, else the nearest point of the nearest path's centreline."""
        gap, pid = site.path_edge_gap(p)
        if gap <= 0:
            return (round(p[0], 2), round(p[1], 2))
        d, s, _ = site.paths[pid].line.closest(p)
        q = site.paths[pid].line.point_at(s)
        return (round(q[0], 2), round(q[1], 2))

    def ahead(eye_xz, to_xz, dist=4.0):
        """Witness for an eye-height view: on the nearest path, about dist metres toward the target."""
        u = G.norm((to_xz[0] - eye_xz[0], to_xz[1] - eye_xz[1]))
        return on_path((eye_xz[0] + u[0] * dist, eye_xz[1] + u[1] * dist))

    def xz(p):
        return f'({p[0]:g},{p[1]:g})'

    gfeet = (-5.0, -57.5)      # on the southbound trail, entering the circle from the north-west
    views = [
        ('hunt_player', 'game', 'windmark_hunt player view: witness on gate_road at the clearing entry, camera 13 m behind',
         {'feet': (-4.25, 4.0), 'yaw': 2.6}),
        ('hunt_side', 'look', 'windmark_hunt side view at eye height from the east edge (witness on gate_road_east)',
         {'eye': (17.5, 1.7, 6.0), 'at': (-6.0, 1.2, 5.0), 'witness': (5.0, 6.0)}),
        ('hunt_close', 'look', 'windmark_hunt close view (2.6 m): windmark_2 with the witness',
         {'eye': (wm2[0] + 1.84, 1.55, wm2[1] - 1.84), 'at': (wm2[0], 1.05, wm2[1]), 'witness': (wm2[0] + 0.55, wm2[1] + 1.05)}),
        ('hunt_elevated', 'look', 'windmark_hunt elevated 45-degree oblique from the south-east',
         {'eye': (26.9, 38.0, -21.9), 'at': (0.0, 0.0, 5.0), 'witness': (-2.0, 1.0)}),
        ('glade_player', 'game', f'windstone_glade player view: witness on the trail entering the circle (centre {xz(cc)}), '
                                 'camera 13 m behind',
         {'feet': gfeet, 'yaw': G.yaw_to(cc[0] - gfeet[0], cc[1] - gfeet[1])}),
        ('glade_side', 'look', 'windstone_glade side view at eye height from the south-west',
         {'eye': (-16.5, 1.7, -75.5), 'at': (cc[0] + 1.0, 1.6, cc[1] + 1.5), 'witness': on_path((cc[0] + 3.9, cc[1] - 2.2))}),
        ('glade_close', 'look', 'windstone_glade close view: windstone_altar block on its flush platform (portal ring inlaid) '
                                'with the witness',
         {'eye': None, 'at': None, 'witness': None, 'altar': altar}),
        ('glade_elevated', 'look', 'windstone_glade elevated 45-degree oblique from the south-east',
         {'eye': (cc[0] + 28.3, 40.0, cc[1] - 28.3), 'at': (cc[0], 0.0, cc[1]), 'witness': on_path((cc[0] + 3.75, cc[1] - 4.5))}),
    ]
    wc = site.clearings['oak_wallow']['center_xz']
    wr = float(site.clearings['oak_wallow']['radius_m'])
    if 'boar_trail' in site.paths:
        wx0, wz0 = site.paths['boar_trail'].line.pts[-1]     # witness at the boar_trail end, the approach into the wallow
        wlabel = (f'oak_wallow player view: witness at the boar_trail end {xz((wx0, wz0))} (approach from the east return '
                  'path), camera 13 m behind')
    else:
        wx0, wz0 = wc[0] - 0.55 * wr, wc[1] + 0.8 * wr      # witness just inside the north-west rim (approach from the return path)
        wlabel = 'oak_wallow player view: witness entering from the north-west (return-path side), camera 13 m behind'
    views += [
        ('wallow_player', 'game', wlabel,
         {'feet': (wx0, wz0), 'yaw': G.yaw_to(wc[0] - wx0, wc[1] - wz0)}),
        ('wallow_side', 'look', 'oak_wallow side view at eye height from the west rim',
         {'eye': (wc[0] - 11.5, 1.7, wc[1] - 3.0), 'at': (wc[0] + 4.0, 1.2, wc[1] + 1.0), 'witness': (wc[0] - 5.0, wc[1] - 1.5)}),
        ('wallow_close', 'look', 'oak_wallow close view (2.6 m): the mud wallow rim with the witness',
         {'eye': (wc[0] - 4.84, 1.55, wc[1] + 4.34), 'at': (wc[0] - 2.4, 0.8, wc[1] + 1.9), 'witness': (wc[0] - 3.0, wc[1] + 2.5)}),
        ('wallow_elevated', 'look', 'oak_wallow elevated 45-degree oblique from the south-east',
         {'eye': (wc[0] + 26.9, 38.0, wc[1] - 26.9), 'at': (wc[0] - 2.0, 0.0, wc[1] + 2.0), 'witness': (wc[0] - 2.0, wc[1] + 3.5)}),
    ]
    s1 = sl['ancient_pine']
    f1id, f1 = s1['from_points'][0]          # 'city exit ramps': the west ramp first (gate_road starts there)
    views += [
        ('sl1_eye', 'look', f'sightline 1 {s1["from"]} -> ancient_pine, eye height 1.65 m at {f1id} {xz(f1)}',
         {'eye': (f1[0], 1.65, f1[1]), 'at': (s1['to_xz'][0], 9.0, s1['to_xz'][1]), 'witness': ahead(f1, s1['to_xz'])}),
        ('sl1_cam', 'game', f'sightline 1 game camera: witness at {f1id} {xz(f1)} facing the ancient pine',
         {'feet': f1, 'yaw': G.yaw_to(s1['to_xz'][0] - f1[0], s1['to_xz'][1] - f1[1])}),
    ]
    s2 = sl['bluff_falls']
    views += [
        ('sl2_eye', 'look', f'sightline 2 {s2["from"]} -> bluff_falls, eye height 1.65 m',
         {'eye': (s2['from_xz'][0], 1.65, s2['from_xz'][1]), 'at': (s2['to_xz'][0] - 0.5, 3.6, s2['to_xz'][1]), 'witness': (-17.4, -43.5)}),
        ('sl2_cam', 'game', f'sightline 2 game camera: witness at {xz(s2["from_xz"])} facing the falls',
         {'feet': s2['from_xz'], 'yaw': G.yaw_to(s2['to_xz'][0] - s2['from_xz'][0], s2['to_xz'][1] - s2['from_xz'][1])}),
    ]
    s3 = sl['inner_bluff']
    views += [
        ('sl3_eye', 'look', f'sightline 3 {s3["from"]} -> inner_bluff, eye height 1.65 m (look back home)',
         {'eye': (s3['from_xz'][0], 1.65, s3['from_xz'][1]), 'at': (s3['to_xz'][0], 4.0, s3['to_xz'][1]),
          'witness': ahead(s3['from_xz'], s3['to_xz'])}),
        ('sl3_cam', 'game', f'sightline 3 game camera: witness at {xz(s3["from_xz"])} (glade) facing the bluff',
         {'feet': s3['from_xz'], 'yaw': G.yaw_to(s3['to_xz'][0] - s3['from_xz'][0], s3['to_xz'][1] - s3['from_xz'][1])}),
    ]
    s4 = sl['old_sunmeadow_oak']
    views += [
        ('sl4_eye', 'look', f'sightline 4 {s4["from"]} -> old_sunmeadow_oak, eye height 1.65 m',
         {'eye': (s4['from_xz'][0], 1.65, s4['from_xz'][1]), 'at': (s4['to_xz'][0], 6.0, s4['to_xz'][1]),
          'witness': ahead(s4['from_xz'], s4['to_xz'])}),
        ('sl4_cam', 'game', f'sightline 4 game camera: witness at {xz(s4["from_xz"])} facing the hero oak',
         {'feet': s4['from_xz'], 'yaw': G.yaw_to(s4['to_xz'][0] - s4['from_xz'][0], s4['to_xz'][1] - s4['from_xz'][1])}),
        ('top', 'ortho', 'top orthographic view of the stage (6 px/m, north up) for comparison with plan.png',
         {'witness': (0.0, -24.0)}),
        ('arena_top', 'ortho', f'windstone_circle boss arena top orthographic view: {ARENA_TOP_M:g} x {ARENA_TOP_M:g} m '
                               f'centred on the circle centre {xz(cc)} ({ARENA_TOP_RES / ARENA_TOP_M:g} px/m, north up); '
                               'witness at the centre',
         {'witness': cc, 'centre': cc, 'size_m': ARENA_TOP_M, 'res': (ARENA_TOP_RES, ARENA_TOP_RES)}),
    ]
    return views


def render_views(site, raw: Path, samples, device, only, log):
    raw.mkdir(parents=True, exist_ok=True)
    vt = setup_render(samples, device)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    specs = view_specs(site)
    cams, meta, witnesses = {}, {}, {}
    annotation_objs = [ob for ob in bpy.data.objects if ob.get('layer') == 'annotation']
    for name, kind, label, sp in specs:
        if only and name not in only:
            continue
        if kind == 'game':
            cam, m = game_camera(f'cam_{name}', sp['feet'], sp['yaw'], depsgraph)
            w = add_witness(f'W_{name}', sp['feet'][0], sp['feet'][1], sp['yaw'])
            wxz = sp['feet']
        elif kind == 'ortho':
            if sp.get('centre'):
                cam, m = top_camera(site, f'cam_{name}', sp['centre'], sp['size_m'], sp['res'])
            else:
                cam, m = top_camera(site)
            w = add_witness(f'W_{name}', *sp['witness'])
            wxz = sp['witness']
        else:
            if sp.get('altar'):
                ax, az = sp['altar']
                # the altar faces the trail; put the camera on the trail side
                pf = site.paths['southbound_trail']
                d, s, _ = pf.line.closest((ax, az))
                tx, tz = pf.line.point_at(s)
                u = G.norm((tx - ax, tz - az))
                sp = dict(sp)
                sp['eye'] = (ax + u[0] * 5.3 + u[1] * 0.9, 1.6, az + u[1] * 5.3 - u[0] * 0.9)
                sp['at'] = (ax - u[0] * 0.8, 1.15, az - u[1] * 0.8)
                sp['witness'] = (ax + u[0] * 3.05 - u[1] * 1.2, az + u[1] * 3.05 + u[0] * 1.2)
            cam, m = look_camera(f'cam_{name}', sp['eye'], sp['at'])
            wx, wz = sp['witness']
            w = add_witness(f'W_{name}', wx, wz, G.yaw_to(sp['eye'][0] - wx, sp['eye'][2] - wz))
            wxz = (wx, wz)
        m.update({'label': label, 'witness_xz': [round(wxz[0], 2), round(wxz[1], 2)], 'kind': kind})
        cams[name], meta[name], witnesses[name] = cam, m, w
        if sp.get('res'):
            meta[name]['resolution'] = list(sp['res'])
    sc = bpy.context.scene
    timings = {}
    for name in cams:
        for wn, w in witnesses.items():
            w.hide_render = wn != name
        for ob in annotation_objs:
            ob.hide_render = meta[name]['kind'] != 'ortho'     # spawn / home / POI marks only in the top views
        sc.camera = cams[name]
        if name == 'top':
            sc.render.resolution_x, sc.render.resolution_y = 768, 804
        elif meta[name].get('resolution'):
            sc.render.resolution_x, sc.render.resolution_y = meta[name]['resolution']
        else:
            sc.render.resolution_x, sc.render.resolution_y = 960, 540
        sc.render.filepath = str(raw / f'{name}.png')
        t = time.time()
        bpy.ops.render.render(write_still=True)
        timings[name] = round(time.time() - t, 1)
        log(f'RENDER {name} {timings[name]}s')
    for name in meta:
        meta[name]['render_s'] = timings.get(name)
    (raw / 'views.json').write_text(json.dumps({'view_transform': vt, 'samples': samples, 'device': device,
                                                'views': meta}, indent=1) + '\n', encoding='utf-8')
    return meta, vt


def main():
    a = parse_args()
    t0 = time.time()
    logs = []

    def log(msg):
        print('[sm2]', msg, flush=True)
        logs.append(msg)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    res = B.build_all(log)
    out = a['out']
    out.mkdir(parents=True, exist_ok=True)
    inst_path, col_path = B.write_jsons(res, out)
    t1 = time.time()
    objs = build_scene(res, log)
    t_scene = time.time() - t1
    report = {'blender_version': bpy.app.version_string, 'gltf_addon_version': X.addon_version(), 'pass': a['pass'],
              'argv': sys.argv, 'timings': dict(res['timings'])}
    report['timings']['blender_scene_s'] = round(t_scene, 2)
    if a['export']:
        t2 = time.time()
        report['cells'], report['gltf_export_options'] = export_cells(objs, out, res['per_cell'], log)
        report['timings']['export_s'] = round(time.time() - t2, 2)
        t2 = time.time()
        report['reimport_validation'] = X.reimport_validate(report['cells'], ROOT, log)
        report['timings']['reimport_s'] = round(time.time() - t2, 2)
        cells_doc = {'schema': 'xexoria.sunmeadow-v2.blockout-cells/1', 'status': 'BLOCKOUT proxies (replace with final art)',
                     'cell_naming': 'c{8+floor(x/64)}_r{8+floor(z/64)} over Babylon XZ; c7_r6 = x[-64,0] z[-128,-64]',
                     'budget_triangles_lod0_excl_vegetation': B.TRI_BUDGET, 'budget_draw_calls': B.DRAW_BUDGET,
                     'cells': {c: {'glb': r['glb'], 'sha256': r['sha256'], 'bytes': r['bytes'],
                                   'glb_triangles_total': r['glb_inspect']['triangles'],
                                   'triangles_lod0_excl_vegetation': r['blender_triangles_structure'],
                                   'vegetation_proxy_triangles': r['blender_triangles_vegetation'],
                                   'within_budget': r['blender_triangles_structure'] <= B.TRI_BUDGET,
                                   'materials_structure': r.get('draw_calls_structure'),
                                   'materials_vegetation': r.get('draw_calls_vegetation'),
                                   'glb_primitives': r['glb_inspect']['primitives'],
                                   'by_layer_triangles': r.get('by_layer'),
                                   'reimport_pass': report['reimport_validation']['cells'][c]['pass']}
                               for c, r in report['cells'].items()}}
        (out / 'cells.json').write_text(json.dumps(cells_doc, indent=1) + '\n', encoding='utf-8')
        report['cells_json'] = {'path': rel(out / 'cells.json'), 'sha256': B.sha(out / 'cells.json')}
    t2 = time.time()
    cv = X.collider_visual_check(res['cols'].items + res['cols'].existing, log)
    report['timings']['collider_visual_s'] = round(time.time() - t2, 2)
    report['collider_visual_check'] = {k: v for k, v in cv.items() if k != 'rows'}
    ev = a['evidence']
    ev.mkdir(parents=True, exist_ok=True)
    (ev / f'collider_visual_check_pass{a["pass"]}.json').write_text(json.dumps(cv, indent=1) + '\n', encoding='utf-8')
    t2 = time.time()
    slc = SL.sightline_check(res['site'], res['items'], game_camera, log)
    report['timings']['sightlines_s'] = round(time.time() - t2, 2)
    report['sightline_check'] = slc['sightlines']
    (ev / f'sightlines_pass{a["pass"]}.json').write_text(json.dumps(slc, indent=1) + '\n', encoding='utf-8')
    if a['blend']:
        blend = Path(a['blend_path']) if a.get('blend_path') else out / 'sunmeadow-v2-blockout.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
        report['blend'] = {'path': rel(blend), 'bytes': blend.stat().st_size}
    report['instances_json'] = {'path': rel(inst_path), 'sha256': B.sha(inst_path)}
    report['colliders_json'] = {'path': rel(col_path), 'sha256': B.sha(col_path),
                                'count': len(res['cols'].items), 'existing_preserved': len(res['cols'].existing)}
    report['notes'] = res['site'].notes
    if a['render'] and a['raw']:
        t3 = time.time()
        meta, vt = render_views(res['site'], a['raw'], a['samples'], a['device'], a['views'], log)
        report['views'] = meta
        report['view_transform'] = vt
        report['timings']['render_total_s'] = round(time.time() - t3, 1)
    report['timings']['total_s'] = round(time.time() - t0, 1)
    report['log'] = logs
    (ev / f'build_report_pass{a["pass"]}.json').write_text(json.dumps(report, indent=1, default=str) + '\n', encoding='utf-8')
    log(f'DONE total {report["timings"]["total_s"]}s')


if __name__ == '__main__':
    main()
