"""Render matched house/roof and plaza material views without saving source art."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'lib'))
sys.path.insert(0, str(HERE))
import citykit as ck
from export_runtime_r5 import refresh_texture_images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', required=True)
    parser.add_argument('--textures', type=Path)
    parser.add_argument('--outdir', type=Path, default=ROOT / 'planning/evidence')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.textures:
        for image in bpy.data.images:
            name = image.name if image.name.lower().endswith(('.png', '.jpg', '.jpeg')) else Path(image.filepath).name
            source = args.textures / name
            if source.is_file():
                image.filepath = str(source.resolve())
                image.reload()
    else:
        refresh_texture_images()
    scene = ck.render_settings(res=(1152, 768), samples=16, threads=4)
    source = Path(bpy.data.filepath)
    args.outdir.mkdir(parents=True, exist_ok=True)
    armory = bpy.data.objects.get('kit_armory_house')
    if armory is None:
        raise RuntimeError('Authored armory house is required for the matched close view')
    bpy.context.view_layer.update()
    objects = [o for o in armory.children_recursive if o.type == 'MESH']
    camera = ck.frame_camera(objects, azimuth_deg=-30, elevation_deg=28, lens=50,
                             margin=1.06, name='Material house close review')
    camera.data.clip_start = 0.2
    house = args.outdir / f'city-material-house-{args.variant}-20261001.png'
    ck.render(house)
    data = bpy.data.cameras.new('Material plaza close review')
    camera = bpy.data.objects.new('Material plaza close review', data)
    scene.collection.objects.link(camera)
    camera.location = (29, -29, 18)
    target = Vector((15, -9, 0))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    data.lens = 48
    data.clip_start, data.clip_end = 0.2, 2000
    scene.camera = camera
    plaza = args.outdir / f'city-material-plaza-{args.variant}-20261001.png'
    ck.render(plaza)
    print(json.dumps({'source': str(source), 'house': str(house), 'plaza': str(plaza),
                      'source_saved': False, 'resolution': [1152, 768], 'samples': 16}))


if __name__ == '__main__':
    main()
