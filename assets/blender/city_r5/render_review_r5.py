"""Render fresh R5 hero/top review shots from the saved editable master.

This is intentionally separate from the 45-minute geometry build so material,
camera or gate reviews can be repeated without regenerating the city.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'lib'))
import citykit as ck  # noqa: E402

args_raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--res', default='1536x1024')
parser.add_argument('--samples', type=int, default=16)
parser.add_argument('--threads', type=int, default=4)
args = parser.parse_args(args_raw)

layout_path = ROOT / 'assets/blender/city_r5/layout.json'
layout = json.loads(layout_path.read_text(encoding='utf-8'))
review = ROOT / 'assets/models/reference-city/r5/review'
review.mkdir(parents=True, exist_ok=True)
width, height = (int(v) for v in args.res.lower().split('x'))
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = args.samples
scene.cycles.use_denoising = True
scene.render.threads_mode = 'FIXED'
scene.render.threads = args.threads
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = 'AgX'
try:
    scene.view_settings.look = 'AgX - Medium High Contrast'
except TypeError:
    pass


def set_camera(name: str):
    spec = layout['review_cameras'][name]
    data = bpy.data.cameras.new(f'r5 final review {name}')
    camera = bpy.data.objects.new(f'r5 final review {name}', data)
    scene.collection.objects.link(camera)
    target = Vector(spec['target'])
    if name == 'top':
        data.type = 'ORTHO'
        data.ortho_scale = float(spec.get('ortho_scale', 310))
        camera.location = Vector((target.x, target.y, 420))
        camera.rotation_euler = (0, 0, 0)
        w, h = int(height * 240 / 288 * 1.08), height
    else:
        data.type = 'PERSP'
        data.lens = float(spec.get('lens_mm', 35))
        camera.location = Vector(spec['location'])
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        w, h = width, height
    data.clip_start = 0.5
    data.clip_end = 5000
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = w, h


for view, output in (('hero_front', 'r5_city_final_hero.png'), ('top', 'r5_city_final_top.png')):
    set_camera(view)
    scene.render.filepath = str(review / output)
    bpy.ops.render.render(write_still=True)
    print(f'R5_REVIEW {view} {review / output}', flush=True)

