"""BLENDER REVIEW renders for the R6 dressing candidate (and its R5 baseline).

Read-only: renders the loaded .blend with fixed, data-driven cameras and never
saves it. The same camera file is used for before and after so every pair is
comparable. Each station gets the four locked views (player 13 m, side, close,
elevated) around a 1.8 m human witness, plus orthographic top views.
Annotation points (runtime XZ + height) are projected into every view and
written to <out>/views.json for the PIL annotator (annotate_review_r6.py).

  blender -b --factory-startup --disable-autoexec <file.blend> --python-exit-code 1 \
    --python assets/blender/city_r5/render_review_r6.py -- --cameras <cameras.json> \
    --out <dir> --tag before [--only fountain,top_city] [--samples 20] [--points pts.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'lib'))
import citykit as ck  # noqa: E402

ROOT = HERE.parents[2]


def args_():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--cameras', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--samples', type=int, default=20)
    ap.add_argument('--threads', type=int, default=10)
    ap.add_argument('--points', default='')
    ap.add_argument('--no-witness', action='store_true')
    return ap.parse_args(argv)


def to_blender(rx, ry, rz):
    """runtime (x, y, z) -> Blender (x, z - 176, y)"""
    return Vector((rx, rz - 176.0, ry))


def ground_tree():
    verts, polys = [], []
    for o in bpy.context.scene.objects:
        if o.type != 'MESH':
            continue
        n = o.name
        if not (n.startswith(('terrain / ', 'traversal / ', 'castle terrace paving', 'castle grand stair tread', 'bridge dressed flagstone'))):
            continue
        if ' curb' in n or 'cliff rock' in n or 'underside' in n or 'stalactite' in n:
            continue
        mw = o.matrix_world
        base = len(verts)
        verts.extend(mw @ v.co for v in o.data.vertices)
        polys.extend(tuple(base + i for i in p.vertices) for p in o.data.polygons)
    return BVHTree.FromPolygons(verts, polys)


def ground_z(tree, x, y, z0=120.0):
    hit = tree.ray_cast(Vector((x, y, z0)), Vector((0, 0, -1)), 400.0)
    return hit[0].z if hit[0] is not None else 0.0


def witness(name, loc, col):
    """1.8 m human witness: capsule body + head, warm red so it reads in every view."""
    mat = bpy.data.materials.get('review witness') or bpy.data.materials.new('review witness')
    mat.use_nodes = True
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (0.75, 0.12, 0.08, 1)
    b.inputs['Roughness'].default_value = 0.6
    parts = []
    body = ck.lathe(f'{name} body', [(0.0, 0.0), (0.2, 0.02), (0.24, 0.5), (0.26, 1.0), (0.22, 1.42), (0.12, 1.5), (0.0, 1.52)],
                    segments=16, col=col, center=(loc.x, loc.y, loc.z))
    head = ck.lathe(f'{name} head', [(0.0, 1.52), (0.11, 1.55), (0.13, 1.66), (0.11, 1.77), (0.0, 1.80)],
                    segments=16, col=col, center=(loc.x, loc.y, loc.z))
    for o in (body, head):
        o.data.materials.append(mat)
        parts.append(o)
    return parts


def setup_scene(samples, threads):
    pres = bpy.data.collections.get('Presentation only')
    if pres is None:
        pres = ck.collection('Presentation only')
    if bpy.data.objects.get('presentation cloud sea') is None:
        sea = ck.new_object('presentation cloud sea', [(-2000, -2000, -95), (2000, -2000, -95), (2000, 2000, -95),
                                                       (-2000, 2000, -95)], [(0, 1, 2, 3)], None, pres)
        m = bpy.data.materials.new('presentation clouds r6')
        m.use_nodes = True
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.86, 0.9, 0.97, 1)
        sea.data.materials.append(m)
    ck.setup_review_world(strength=1.0, sun_energy=4.0, sun_rot=(math.radians(48), 0, math.radians(-28)))
    scene = ck.render_settings((1280, 720), samples, threads)
    scene.render.use_persistent_data = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.03
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transparent_max_bounces = 6
    scene.render.image_settings.file_format = 'PNG'
    return scene


def reload_textures():
    """Point every city image at the final R5 foundry maps (absolute), like the exporters."""
    tex = ROOT / 'assets/models/reference-city/r5/textures'
    q = ROOT / 'assets/third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF'
    fixed = 0
    for img in bpy.data.images:
        raw = img.filepath.replace('\\', '/') if img.filepath else ''
        name = raw.rsplit('/', 1)[-1] if raw else img.name  # '//textures/x.png' would parse as a UNC share
        for folder in (tex, q):
            p = folder / name
            if p.is_file():
                img.filepath = str(p)
                try:
                    img.reload()
                except RuntimeError:
                    pass
                fixed += 1
                break
    return fixed


def make_camera(name):
    data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam = bpy.data.objects.get(name) or bpy.data.objects.new(name, data)
    if cam.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(cam)
    return cam


def look(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat('-Z', 'Y').to_euler()


def main():
    a = args_()
    t0 = time.time()
    spec = json.loads(Path(a.cameras).read_text(encoding='utf-8'))
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    only = {s for s in a.only.split(',') if s}
    print('textures reloaded', reload_textures(), flush=True)
    scene = setup_scene(a.samples, a.threads)
    tree = ground_tree()
    col = ck.collection('review witnesses r6')
    points = json.loads(Path(a.points).read_text(encoding='utf-8')) if a.points else []
    cam = make_camera('review r6 camera')
    scene.camera = cam
    views_out = []
    jobs = []
    for st in spec['stations']:
        bx, by = st['witness'][0], st['witness'][1] - 176.0
        gz = ground_z(tree, bx, by)
        feet = Vector((bx, by, gz))
        if not a.no_witness:
            witness(f"witness {st['id']}", feet, col)
        yaw = math.radians(st['heading_deg'])  # runtime heading: 0 = +Z (north), 90 = +X (east)
        fwd = Vector((math.sin(yaw), math.cos(yaw), 0.0))
        right = Vector((fwd.y, -fwd.x, 0.0))
        tgt = feet + Vector((0, 0, 1.65))
        el = math.radians(22.4)
        views = {
            'player': (tgt - fwd * (13 * math.cos(el)) + Vector((0, 0, 13 * math.sin(el))), tgt + fwd * 0.01, 58.4),
            'side': (feet + right * st.get('side_m', 22) + fwd * st.get('side_ahead', 6) + Vector((0, 0, st.get('side_up', 7))),
                     feet + fwd * st.get('side_ahead', 6) + Vector((0, 0, 2.5)), 40),
            'close': (feet + Vector(st.get('close_offset', [2.2, -2.6, 1.7])), feet + Vector(st.get('close_target', [0, 2.5, 1.2])), 32),
            'elevated': (feet - fwd * st.get('elev_back', 42) + Vector((0, 0, st.get('elev_up', 34))), feet + fwd * st.get('elev_ahead', 18), 34),
        }
        for vname, (loc, target, fov_or_lens) in views.items():
            jobs.append((f"{st['id']}_{vname}", 'PERSP', loc, target, fov_or_lens, vname))
    for tv in spec.get('tops', []):
        jobs.append((tv['id'], 'ORTHO', Vector((tv['center'][0], tv['center'][1] - 176.0, 400.0)),
                     Vector((tv['center'][0], tv['center'][1] - 176.0, 0.0)), tv['scale'], 'top'))
    bpy.context.view_layer.update()
    for jid, kind, loc, target, val, vname in jobs:
        if only and jid not in only and jid.split('_')[0] not in only:
            continue
        data = cam.data
        data.clip_start = 0.1
        data.clip_end = 3000
        if kind == 'ORTHO':
            data.type = 'ORTHO'
            data.ortho_scale = val
            cam.location = loc
            cam.rotation_euler = (0, 0, 0)
            scene.render.resolution_x, scene.render.resolution_y = 1400, 1400
        else:
            data.type = 'PERSP'
            if vname == 'player':
                data.sensor_fit = 'VERTICAL'
                data.angle_y = 1.02
            else:
                data.sensor_fit = 'AUTO'
                data.lens = val
            look(cam, loc, target)
            scene.render.resolution_x, scene.render.resolution_y = 1280, 720
        bpy.context.view_layer.update()
        path = out / f'{a.tag}_{jid}.png'
        ck.render(path)
        proj = []
        for p in points:
            w = to_blender(p['x'], p['y'], p['z'])
            v = world_to_camera_view(scene, cam, w)
            if 0 <= v.x <= 1 and 0 <= v.y <= 1 and v.z > 0:
                proj.append({'id': p['id'], 'u': round(v.x, 5), 'v': round(1 - v.y, 5), 'depth': round(v.z, 2)})
        views_out.append({'id': jid, 'kind': kind, 'image': path.name, 'camera_blender': [round(x, 3) for x in cam.location],
                          'target_blender': [round(x, 3) for x in target], 'width': scene.render.resolution_x,
                          'height': scene.render.resolution_y, 'points': proj})
        print(f'[{time.time() - t0:6.1f}s] {path.name}', flush=True)
    rec = out / f'{a.tag}_views.json'
    rec.write_text(json.dumps({'file': bpy.data.filepath, 'tag': a.tag, 'label': 'BLENDER REVIEW', 'renderer': 'Cycles CPU',
                               'samples': a.samples, 'views': views_out}, indent=1) + '\n', encoding='utf-8')
    print('done', rec, flush=True)


if __name__ == '__main__':
    main()
