"""A/B material review render for the texture forge (Claude lane).

Builds one small, fixed diorama — a cobble street, a stone wall house with a
slate gable roof — lit by a sun and a physical sky, and renders it twice with
the same camera and light: once with the live R5 foundry textures (BEFORE) and
once with a forge candidate folder (AFTER). World-space box UVs use each
material's real tile size, matching the city build.

Run from the repo root:
  blender -b --factory-startup --python assets/blender/city_r5/forge/review_forge_r6.py -- \
      --candidate assets/models/reference-city/r5/textures-forge-r6 --out planning/evidence/forge-r6
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[4]
LIVE = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'textures'
TILES = {'cobble_path': 2.6, 'stone_wall_warm': 2.4, 'roof_slate_blue': 2.2, 'stone_foundation': 2.4,
         'timber_dark': 2.0, 'plaster_cream': 3.0, 'plaza_flagstone': 4.0}


def args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out = {'candidate': 'assets/models/reference-city/r5/textures-forge-r6', 'out': 'planning/evidence/forge-r6',
           'samples': '96', 'width': '1600', 'height': '900'}
    for i in range(0, len(argv), 2):
        out[argv[i].lstrip('-')] = argv[i + 1]
    return out


def material(name: str, folder: Path) -> bpy.types.Material:
    mat = bpy.data.materials.new(f'{name}@{folder.name}')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    coords = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    scale = 1.0 / TILES[name]
    mapping.inputs['Scale'].default_value = (scale, scale, scale)
    links.new(coords.outputs['UV'], mapping.inputs['Vector'])

    def tex(kind: str, non_color: bool):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(folder / f'{name}_{kind}.png'), check_existing=False)
        node.image.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    albedo, normal, orm = tex('albedo', False), tex('normal', True), tex('orm', True)
    split = nodes.new('ShaderNodeSeparateColor')
    links.new(orm.outputs['Color'], split.inputs['Color'])
    ao_mix = nodes.new('ShaderNodeMix'); ao_mix.data_type = 'RGBA'; ao_mix.blend_type = 'MULTIPLY'
    ao_mix.inputs['Factor'].default_value = 1.0
    links.new(albedo.outputs['Color'], ao_mix.inputs['A'])
    links.new(split.outputs['Red'], ao_mix.inputs['B'])
    links.new(ao_mix.outputs['Result'], bsdf.inputs['Base Color'])
    links.new(split.outputs['Green'], bsdf.inputs['Roughness'])
    links.new(split.outputs['Blue'], bsdf.inputs['Metallic'])
    nmap = nodes.new('ShaderNodeNormalMap')
    links.new(normal.outputs['Color'], nmap.inputs['Color'])
    links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def world_box_uv(obj: bpy.types.Object) -> None:
    """Box-project world coordinates in metres into the UV layer (scaled per material by the mapping node)."""
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name='UVMap')
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv = bm.loops.layers.uv.active
    matrix = obj.matrix_world
    for face in bm.faces:
        n = (matrix.to_3x3() @ face.normal).normalized()
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in face.loops:
            p = matrix @ loop.vert.co
            if ax == 2:
                loop[uv].uv = (p.x, p.y)
            elif ax == 0:
                loop[uv].uv = (p.y, p.z)
            else:
                loop[uv].uv = (p.x, p.z)
    bm.to_mesh(mesh)
    bm.free()


def box(name, size, location, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(mat)
    world_box_uv(obj)
    return obj


def gable_roof(name, width, depth, rise, overhang, base_z, mat):
    w, d = width / 2 + overhang, depth / 2 + overhang
    verts = [(-w, -d, base_z), (w, -d, base_z), (w, d, base_z), (-w, d, base_z), (0, -d, base_z + rise), (0, d, base_z + rise)]
    faces = [(0, 1, 4), (3, 5, 2), (0, 4, 5, 3), (1, 2, 5, 4)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    # Roof UVs run up the slope (V toward the ridge), the same convention as the R5 roof repair.
    bm = bmesh.new(); bm.from_mesh(mesh); uv = bm.loops.layers.uv.verify()
    for face in bm.faces:
        for loop in face.loops:
            p = loop.vert.co
            slope = math.hypot(abs(p.x), p.z - base_z)
            loop[uv].uv = (p.y, (w - abs(p.x)) / w * math.hypot(w, rise))
    bm.to_mesh(mesh); bm.free()
    solidify = obj.modifiers.new('thickness', 'SOLIDIFY'); solidify.thickness = 0.12
    return obj


def build(folder: Path) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'CUDA'; prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == 'CUDA'
        scene.cycles.device = 'GPU'
    except Exception:
        scene.cycles.device = 'CPU'
    scene.view_settings.view_transform = 'AgX'
    for look in ('AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    mats = {name: material(name, folder) for name in TILES}
    box('street', (16, 12, 0.2), (0, 0, -0.1), mats['cobble_path'])
    box('plaza', (6, 12, 0.21), (-8, 0, -0.095), mats['plaza_flagstone'])
    box('plinth', (6.4, 4.4, 0.6), (1.5, 2.2, 0.3), mats['stone_foundation'])
    box('wall', (6, 4, 3.4), (1.5, 2.2, 2.3), mats['stone_wall_warm'])
    box('gable_beam', (0.25, 4.3, 0.3), (1.5 - 3.0, 2.2, 4.05), mats['timber_dark'])
    roof = gable_roof('roof', 4.0, 6.0, 2.2, 0.45, 4.0, mats['roof_slate_blue'])
    roof.rotation_euler = (0, 0, math.pi / 2)
    roof.location = (1.5, 2.2, 0)
    sky = bpy.data.worlds.new('sky'); sky.use_nodes = True
    nodes = sky.node_tree.nodes
    tex = nodes.new('ShaderNodeTexSky')
    try:
        tex.sky_type = 'NISHITA'; tex.sun_elevation = math.radians(38); tex.sun_rotation = math.radians(140)
    except Exception:
        pass
    sky.node_tree.links.new(tex.outputs['Color'], nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value = 0.35
    scene.world = sky
    sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 3.2; sun.angle = math.radians(1.2)
    sun_obj = bpy.data.objects.new('sun', sun); sun_obj.rotation_euler = (math.radians(52), 0, math.radians(140))
    scene.collection.objects.link(sun_obj)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); cam.data.lens = 32
    scene.collection.objects.link(cam); scene.camera = cam
    cam.location = (-6.5, -9.5, 4.2)
    target = (1.0, 1.5, 1.6)
    direction = [target[i] - cam.location[i] for i in range(3)]
    cam.rotation_euler = (math.atan2(math.hypot(direction[0], direction[1]), -direction[2]), 0,
                          math.atan2(direction[1], direction[0]) - math.pi / 2)


def main() -> None:
    a = args()
    candidate = Path(a['candidate']); candidate = candidate if candidate.is_absolute() else ROOT / candidate
    out = Path(a['out']); out = out if out.is_absolute() else ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    for label, folder in (('before-live-r5', LIVE), ('after-forge-r6', candidate)):
        build(folder)
        scene = bpy.context.scene
        scene.cycles.samples = int(a['samples']); scene.cycles.use_denoising = True
        scene.render.resolution_x, scene.render.resolution_y = int(a['width']), int(a['height'])
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = str(out / f'forge-review-{label}.png')
        bpy.ops.render.render(write_still=True)
        print('REVIEW', scene.render.filepath)


if __name__ == '__main__':
    main()
