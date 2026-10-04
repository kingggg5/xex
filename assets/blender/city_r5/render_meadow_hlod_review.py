"""Render arrival and overview checks for a packed meadow HLOD GLB.

Uses the established R5 review cameras without modifying the source scene.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LAYOUT = HERE / 'layout.json'


def parse_args():
    raw = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output-dir', default=str(ROOT / 'assets/models/reference-city/r5/review'))
    parser.add_argument('--samples', type=int, default=16)
    return parser.parse_args(raw)


def set_camera(name, location, target, lens=35, ortho=False, ortho_scale=310):
    data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    data.lens = lens
    if ortho:
        data.type = 'ORTHO'
        data.ortho_scale = ortho_scale
    return camera


def configure_scene(samples):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = samples
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    world = bpy.data.worlds.new('Meadow HLOD review sky')
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.34, 0.52, 0.75, 1.0)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.75
    scene.world = world
    light_data = bpy.data.lights.new('Meadow HLOD sun', 'SUN')
    light_data.energy = 3.0
    light_data.angle = 0.08
    light = bpy.data.objects.new('Meadow HLOD sun', light_data)
    scene.collection.objects.link(light)
    light.rotation_euler = (0.28, -0.42, -0.32)


def main():
    args = parse_args()
    model = Path(args.model).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not model.is_file():
        raise FileNotFoundError(model)
    output_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(model))
    configure_scene(args.samples)
    layout = __import__('json').loads(LAYOUT.read_text(encoding='utf-8'))

    views = {
        'arrival': layout['review_cameras']['arrival_gate'],
        'hero': layout['review_cameras']['hero_front'],
    }
    for name, spec in views.items():
        camera = set_camera(f'HLOD camera {name}', spec['location'], spec['target'], spec.get('lens_mm', 35))
        scene = bpy.context.scene
        scene.camera = camera
        scene.render.filepath = str(output_dir / f'r5_city_meadow_hlod_{name}.png')
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(camera, do_unlink=True)
    print(f'HLOD review renders saved in {output_dir}')


if __name__ == '__main__':
    main()
