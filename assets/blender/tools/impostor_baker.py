"""Xexoria impostor baker (Claude lane, 2026-10-01) — our own "impostor cards" tool.

Renders each asset from a grid of view directions (azimuth ring x elevation rows) with
an orthographic camera fitted to its projected extent, captures an unlit albedo pass with
coverage alpha and an OBJECT-SPACE normal pass (runtime/Babylon axes, so frames blend and
instance yaw rotates them correctly), and packs every frame into shared atlas pages
(normal pages at half resolution; optional KTX2). The v2 JSON manifest records the grid
convention, frame directions, each asset's cell block and its centre relative to the asset
origin, so the Babylon runtime (apps/client/src/impostors.ts) can billboard, blend frames,
light the card with the scene lights and cross-fade against the real mesh.

Run from the repo root:
  blender -b --factory-startup --python assets/blender/tools/impostor_baker.py -- \
      --inputs a.glb,b.glb --out assets/models/impostors/<name> --name <name> \
      [--az 8] [--el 3] [--el-min 0] [--el-max 50] [--res 256] [--page 2048] [--device cpu|gpu]

Axis note: Blender (x, y, z) maps to Babylon (-x, z, -y) for glTF assets loaded by Babylon's
glTF loader (verified numerically on 2026-10-01, docs/reviews/2026-10-01-claude-review-round-1.md).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[3]


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    a = {'inputs': '', 'config': '', 'out': '', 'name': 'impostors', 'az': 8, 'el': 4, 'el-min': 0.0, 'el-max': 45.0,
         'res': 256, 'page': 2048, 'device': 'cpu', 'samples': 12, 'bleed': 8, 'ktx': 1}
    for i in range(0, len(argv), 2):
        key = argv[i].lstrip('-')
        if key not in a:
            raise SystemExit(f'unknown argument {argv[i]}')
        a[key] = type(a[key])(argv[i + 1])
    def resolve(p):
        return Path(p) if Path(p).is_absolute() else ROOT / p
    if a['config']:
        config = json.loads(resolve(a['config']).read_text(encoding='utf-8'))
        for key in ('out', 'name', 'az', 'el', 'el-min', 'el-max', 'res', 'page', 'ktx'):
            if key in config:
                a[key] = type(a[key])(config[key])
        a['specs'] = config['inputs']
        a['shading'] = config.get('shading', {})
    else:
        a['specs'] = [{'path': p} for p in a['inputs'].split(',') if p]
        a['shading'] = {}
    if not a['specs'] or not a['out']:
        raise SystemExit('--config (or --inputs) and --out are required')
    a['out'] = resolve(a['out'])
    for spec in a['specs']:
        spec['path'] = resolve(spec['path'])
    return a


def blender_to_babylon(v) -> list[float]:
    return [round(-v[0], 6), round(v[2], 6), round(-v[1], 6)]


# ----------------------------------------------------------------------------
# Scene and per-pass materials
# ----------------------------------------------------------------------------

def setup_scene(args: dict) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    if args['device'] == 'gpu':
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type = 'CUDA'
            prefs.get_devices()
            for device in prefs.devices:
                device.use = device.type == 'CUDA'
            scene.cycles.device = 'GPU'
        except Exception:
            scene.cycles.device = 'CPU'
    scene.cycles.samples = args['samples']
    scene.cycles.max_bounces = 0
    scene.cycles.use_denoising = False
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = args['res']
    scene.render.resolution_percentage = 100
    scene.render.filter_size = 1.2
    scene.view_settings.view_transform = 'Standard'
    settings = scene.render.image_settings
    settings.file_format = 'OPEN_EXR'
    settings.color_depth = '32'
    settings.color_mode = 'RGBA'
    world = bpy.data.worlds.new('impostor-world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)
    scene.world = world


def _source_color(nt, bsdf):
    """Return (socket_or_None, default_rgba) feeding the base colour of a material."""
    if bsdf is not None:
        socket = bsdf.inputs.get('Base Color')
        if socket is not None:
            return (socket.links[0].from_socket if socket.is_linked else None), tuple(socket.default_value)
    for node in nt.nodes:
        if node.type in ('EMISSION', 'BACKGROUND'):
            socket = node.inputs['Color']
            return (socket.links[0].from_socket if socket.is_linked else None), tuple(socket.default_value)
    return None, (0.6, 0.6, 0.6, 1.0)


def make_pass_material(src: bpy.types.Material, mode: str) -> bpy.types.Material:
    mat = src.copy()
    mat.name = f'{src.name}__{mode}'
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output),
               next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)) or nt.nodes.new('ShaderNodeOutputMaterial')
    emission = nt.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.0
    if mode == 'albedo':
        socket, default = _source_color(nt, bsdf)
        if socket is not None:
            nt.links.new(socket, emission.inputs['Color'])
        else:
            emission.inputs['Color'].default_value = default
    else:
        # Shading normal in world space (Cycles flips it towards the ray on back faces, like
        # Babylon's twoSidedLighting), re-expressed in Babylon axes (-x, z, -y) and encoded.
        geometry = nt.nodes.new('ShaderNodeNewGeometry')
        split = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(geometry.outputs['Normal'], split.inputs['Vector'])
        join = nt.nodes.new('ShaderNodeCombineXYZ')
        neg_x = nt.nodes.new('ShaderNodeMath')
        neg_x.operation = 'MULTIPLY'
        neg_x.inputs[1].default_value = -1.0
        nt.links.new(split.outputs['X'], neg_x.inputs[0])
        neg_y = nt.nodes.new('ShaderNodeMath')
        neg_y.operation = 'MULTIPLY'
        neg_y.inputs[1].default_value = -1.0
        nt.links.new(split.outputs['Y'], neg_y.inputs[0])
        nt.links.new(neg_x.outputs['Value'], join.inputs['X'])
        nt.links.new(split.outputs['Z'], join.inputs['Y'])
        nt.links.new(neg_y.outputs['Value'], join.inputs['Z'])
        encode = nt.nodes.new('ShaderNodeVectorMath')
        encode.operation = 'MULTIPLY_ADD'
        encode.inputs[1].default_value = (0.5, 0.5, 0.5)
        encode.inputs[2].default_value = (0.5, 0.5, 0.5)
        nt.links.new(join.outputs['Vector'], encode.inputs[0])
        nt.links.new(encode.outputs['Vector'], emission.inputs['Color'])
    transparent = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    alpha = bsdf.inputs.get('Alpha') if bsdf is not None else None
    if alpha is not None and alpha.is_linked:
        nt.links.new(alpha.links[0].from_socket, mix.inputs['Fac'])
    else:
        mix.inputs['Fac'].default_value = float(alpha.default_value) if alpha is not None else 1.0
    nt.links.new(transparent.outputs['BSDF'], mix.inputs[1])
    nt.links.new(emission.outputs['Emission'], mix.inputs[2])
    for link in list(out.inputs['Surface'].links):
        nt.links.remove(link)
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    return mat


def override_material(name, rule):
    """Principled material matching a runtime override: colour or texture, UV scale, alpha cutoff."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = float(rule.get('roughness', 0.9))
    if 'texture' in rule:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(ROOT / rule['texture']), check_existing=True)
        tex.extension = rule.get('wrap', 'REPEAT')
        uv = nt.nodes.new('ShaderNodeUVMap')
        mapping = nt.nodes.new('ShaderNodeMapping')
        sx, sy = rule.get('uv_scale', [1, 1])
        mapping.inputs['Scale'].default_value = (sx, sy, 1)
        nt.links.new(uv.outputs['UV'], mapping.inputs['Vector'])
        nt.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        if 'alpha_cutoff' in rule:
            cut = nt.nodes.new('ShaderNodeMath')
            cut.operation = 'GREATER_THAN'
            cut.inputs[1].default_value = float(rule['alpha_cutoff'])
            nt.links.new(tex.outputs['Alpha'], cut.inputs[0])
            nt.links.new(cut.outputs['Value'], bsdf.inputs['Alpha'])
    elif 'color' in rule:
        hexv = rule['color'].lstrip('#')
        rgb = [int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        bsdf.inputs['Base Color'].default_value = (*[c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb], 1.0)
    return mat


def vertex_color_material(mesh_obj):
    attrs = getattr(mesh_obj.data, 'color_attributes', None)
    if not attrs:
        return None
    mat = bpy.data.materials.new(mesh_obj.name + '__vcol')
    mat.use_nodes = True
    nt = mat.node_tree
    node = nt.nodes.new('ShaderNodeVertexColor')
    node.layer_name = attrs[0].name
    nt.links.new(node.outputs['Color'], nt.nodes['Principled BSDF'].inputs['Base Color'])
    return mat


# ----------------------------------------------------------------------------
# Assets, frames, rendering
# ----------------------------------------------------------------------------

class Asset:
    def __init__(self, asset_id, path, objects, rules):
        self.path = path
        self.id = asset_id
        self.objects = objects
        self.meshes = [o for o in objects if o.type == 'MESH']
        if not self.meshes:
            raise SystemExit(asset_id + ' has no meshes')
        for o in self.meshes:
            rule = next((r for r in rules if r.get('match_mesh') and r['match_mesh'] in o.name), None)
            if rule is not None:
                mat = override_material(asset_id + ':' + rule['match_mesh'], rule)
                o.data.materials.clear()
                o.data.materials.append(mat)
                continue
            for slot in o.material_slots:
                rule = next((r for r in rules if r.get('match_material') and slot.material and r['match_material'] in slot.material.name), None)
                if rule is not None:
                    slot.material = override_material(asset_id + ':' + rule['match_material'], rule)
            if not o.material_slots or all(slot.material is None for slot in o.material_slots):
                mat = vertex_color_material(o) or override_material(o.name + '__grey', {'color': '#9a9a9a'})
                o.data.materials.clear()
                o.data.materials.append(mat)
        corners = [o.matrix_world @ Vector(c) for o in self.meshes for c in o.bound_box]
        lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
        hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
        self.center = (lo + hi) / 2
        self.radius = max((c - self.center).length for c in corners)
        # Tighter card than the bounding sphere: horizontal radius R about the vertical axis and
        # height H; the card must hold the projected extent at every baked elevation.
        verts = [o.matrix_world @ v.co for o in self.meshes for v in o.data.vertices]
        horizontal = max(math.hypot(v.x - self.center.x, v.y - self.center.y) for v in verts)
        height = hi.z - lo.z
        self.horizontal_radius = horizontal
        self.height = height
        self.pivot = Vector((self.center.x, self.center.y, lo.z))
        self.origin = Vector((0.0, 0.0, 0.0))  # glTF import keeps node transforms; instances are placed at the file origin
        self.triangles = sum(sum(len(poly.vertices) - 2 for poly in o.data.polygons) for o in self.meshes)
        self.variants = {}
        for mode in ('albedo', 'normal'):
            cache = {}
            for o in self.meshes:
                for slot in o.material_slots:
                    if slot.material and slot.material.name not in cache:
                        cache[slot.material.name] = make_pass_material(slot.material, mode)
            self.variants[mode] = cache

    def show(self, visible: bool) -> None:
        for o in self.objects:
            o.hide_render = not visible

    def use_pass(self, mode: str) -> None:
        for o in self.meshes:
            for slot in o.material_slots:
                if slot.material:
                    base = slot.material.name.split('__')[0]
                    slot.material = self.variants[mode].get(base, slot.material)


def load_assets(specs):
    import re
    assets = []
    for spec in specs:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(spec['path']))
        objects = [o for o in bpy.data.objects if o not in before]
        rules = spec.get('materials', [])
        if spec.get('split'):
            groups = {}
            for o in objects:
                m = re.search(spec['split'], o.name)
                if m and o.type == 'MESH':
                    groups.setdefault(m.group(1), []).append(o)
            for key in sorted(groups):
                assets.append(Asset(spec.get('id', spec['path'].stem) + '_' + key, spec['path'], groups[key], rules))
        else:
            assets.append(Asset(spec.get('id', spec['path'].stem.split('.')[0]), spec['path'], objects, rules))
    return assets


def frame_dirs(az: int, el: int, el_min: float, el_max: float) -> list[dict]:
    frames = []
    for j in range(el):
        e = math.radians(el_min + (el_max - el_min) * (j / max(1, el - 1)))
        for i in range(az):
            a = 2 * math.pi * i / az
            # Azimuth 0 = camera in front of the asset (Blender -Y), counter-clockwise seen from above.
            d = Vector((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))
            frames.append({'az': i, 'el': j, 'dir_blender': d})
    return frames


def render_frame(scene, asset: Asset, frame: dict, mode: str, tmp: Path, res: int) -> np.ndarray:
    cam = scene.camera
    cam.data.ortho_scale = asset.card
    cam.location = asset.center + frame['dir_blender'] * asset.radius * 4.0
    cam.rotation_euler = (asset.center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_start = asset.radius * 0.5
    cam.data.clip_end = asset.radius * 8.0
    path = tmp / f'{asset.id}_{mode}_{frame["el"]}_{frame["az"]}.exr'
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path), check_existing=False)
    image.colorspace_settings.name = 'Non-Color'
    pixels = np.empty(res * res * 4, np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return np.flipud(pixels.reshape(res, res, 4)).copy()


def frame_basis(direction: Vector) -> tuple[Vector, Vector]:
    """Right and up vectors of the frame camera (world space), matching to_track_quat('-Z', 'Y')."""
    forward = -direction.normalized()
    quat = forward.to_track_quat('-Z', 'Y')
    return quat @ Vector((1, 0, 0)), quat @ Vector((0, 1, 0))


# ----------------------------------------------------------------------------
# Post-processing and atlas packing
# ----------------------------------------------------------------------------

def linear_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def bleed(rgb: np.ndarray, alpha: np.ndarray, steps: int) -> np.ndarray:
    """Push edge colours outward into transparent texels so mip levels do not halo dark."""
    rgb = rgb.copy()
    filled = alpha > 0.02
    for _ in range(steps):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(alpha.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            shifted_fill = np.roll(np.roll(filled, dy, 0), dx, 1)
            shifted_rgb = np.roll(np.roll(rgb, dy, 0), dx, 1)
            acc += shifted_rgb * shifted_fill[..., None]
            cnt += shifted_fill
        grow = (~filled) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        filled = filled | grow
    return rgb


def downsample_normals(page: np.ndarray) -> np.ndarray:
    """Half-resolution normal page: alpha-weighted average of decoded normals, renormalised."""
    h, w = page.shape[0] // 2, page.shape[1] // 2
    blocks = page[:h * 2, :w * 2].reshape(h, 2, w, 2, 4)
    alpha = blocks[..., 3]
    weight = alpha + 1e-4
    n = blocks[..., :3] * 2.0 - 1.0
    summed = (n * weight[..., None]).sum(axis=(1, 3))
    length = np.linalg.norm(summed, axis=-1, keepdims=True)
    unit = np.where(length > 1e-6, summed / np.maximum(length, 1e-6), np.array([0.0, 1.0, 0.0]))
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = unit * 0.5 + 0.5
    out[..., 3] = alpha.mean(axis=(1, 3))
    return out


def to_ktx2(png: Path, srgb: bool) -> Path | None:
    """UASTC + zstd + mipmaps through the project's KTX-Software 4.4.2 (absent tool -> PNG only)."""
    import subprocess
    tool = ROOT / '.harness' / '.cache' / 'toolchains' / 'ktx-4.4.2' / 'portable' / 'bin' / 'ktx.exe'
    if not tool.exists():
        print('KTX tool missing; PNG only')
        return None
    out = png.with_suffix('.ktx2')
    # Albedo keeps its sRGB-encoded bytes as UNORM (no hardware decode) so it samples exactly like the
    # PNG path: StandardMaterial lights in gamma space and converts to linear before tone mapping.
    fmt = ['--format', 'R8G8B8A8_UNORM', '--assign-tf', 'linear']
    cmd = [str(tool), 'create', *fmt, '--encode', 'uastc', '--uastc-quality', '2', '--zstd', '18', '--generate-mipmap', str(png), str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print('KTX FAILED', result.stderr[-400:])
        return None
    return out


def save_png(path: Path, rgba: np.ndarray) -> None:
    h, w = rgba.shape[:2]
    image = bpy.data.images.new(path.stem, w, h, alpha=True, float_buffer=False)
    image.pixels.foreach_set(np.flipud(np.clip(rgba, 0, 1)).astype(np.float32).ravel())
    image.filepath_raw = str(path)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


def main() -> None:
    args = parse_args()
    setup_scene(args)
    scene = bpy.context.scene
    cam = bpy.data.objects.new('impostor-cam', bpy.data.cameras.new('impostor-cam'))
    cam.data.type = 'ORTHO'
    scene.collection.objects.link(cam)
    scene.camera = cam
    out: Path = args['out']
    tmp = out / '_frames'
    tmp.mkdir(parents=True, exist_ok=True)
    assets = load_assets(args['specs'])
    frames = frame_dirs(args['az'], args['el'], args['el-min'], args['el-max'])
    for asset in assets:
        widest = 2.0 * asset.horizontal_radius
        tallest = max(asset.height * math.cos(math.radians(e)) + 2.0 * asset.horizontal_radius * math.sin(math.radians(e))
                      for e in (args['el-min'], args['el-max'], (args['el-min'] + args['el-max']) / 2))
        asset.card = max(widest, tallest) * 1.04  # 4 % margin keeps leaf tips off the frame edge
    res, page = args['res'], args['page']
    cols_per_page = args['az']
    rows_per_page = (page // res) // args['el'] * args['el']
    if rows_per_page < args['el']:
        raise SystemExit('--el rows do not fit in one page; raise --page or lower --res')
    pages: list[dict] = []
    placements = []
    row = 0
    for asset in assets:
        if not pages or row + args['el'] > rows_per_page:
            pages.append({'rows': 0})
            row = 0
        placements.append((len(pages) - 1, 0, row))
        row += args['el']
        pages[-1]['rows'] = row
    for record in pages:
        h, w = record['rows'] * res, cols_per_page * res
        record['albedo'] = np.zeros((h, w, 4), np.float32)
        record['normal'] = np.zeros((h, w, 4), np.float32)
    for asset, (page_index, col0, row0) in zip(assets, placements):
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.hide_render = True
        asset.show(True)
        for mode in ('albedo', 'normal'):
            asset.use_pass(mode)
            for frame in frames:
                rgba = render_frame(scene, asset, frame, mode, tmp, res)
                alpha = rgba[..., 3]
                if mode == 'albedo':
                    straight = np.where(alpha[..., None] > 1e-4, rgba[..., :3] / np.maximum(alpha[..., None], 1e-4), 0)
                    rgb = linear_to_srgb(bleed(straight, alpha, args['bleed']))
                else:
                    straight = np.where(alpha[..., None] > 1e-4, rgba[..., :3] / np.maximum(alpha[..., None], 1e-4), 0.5)
                    rgb = bleed(straight, alpha, args['bleed'])
                y = (row0 + frame['el']) * res
                x = (col0 + frame['az']) * res
                pages[page_index][mode][y:y + res, x:x + res, :3] = rgb
                pages[page_index][mode][y:y + res, x:x + res, 3] = alpha
            print(f'IMPOSTOR {asset.id} {mode}: {len(frames)} frames')
    out.mkdir(parents=True, exist_ok=True)
    page_records = []
    for index, data in enumerate(pages):
        record = {'cols': cols_per_page, 'rows': data['rows'],
                  'width_px': data['albedo'].shape[1], 'height_px': data['albedo'].shape[0]}
        for mode in ('albedo', 'normal'):
            image = data[mode] if mode == 'albedo' else downsample_normals(data[mode])
            path = out / f'{args["name"]}_{mode}_{index}.png'
            save_png(path, image)
            record[mode] = path.name
            record[f'{mode}_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            if mode == 'normal':
                record['normal_width_px'], record['normal_height_px'] = image.shape[1], image.shape[0]
            if args['ktx']:
                ktx = to_ktx2(path, srgb=mode == 'albedo')
                if ktx:
                    record[f'{mode}_ktx2'] = ktx.name
                    record[f'{mode}_ktx2_sha256'] = hashlib.sha256(ktx.read_bytes()).hexdigest()
        page_records.append(record)
    frame_records = []
    for frame in frames:
        right, up = frame_basis(frame['dir_blender'])
        frame_records.append({'az': frame['az'], 'el': frame['el'], 'dir': blender_to_babylon(frame['dir_blender']),
                              'right': blender_to_babylon(right), 'up': blender_to_babylon(up)})
    first, second = frame_records[0], frame_records[1 % len(frame_records)]
    az_sign = 1 if math.atan2(second['dir'][0], second['dir'][2]) - math.atan2(first['dir'][0], first['dir'][2]) > 0 else -1
    manifest = {
        'schema': 'xexoria.impostor-atlas/2',
        'name': args['name'],
        'generator': 'assets/blender/tools/impostor_baker.py',
        'blender': bpy.app.version_string,
        'frame_px': res,
        'page_px': page,
        'grid': {'azimuth': args['az'], 'elevation': args['el'], 'el_min_deg': args['el-min'], 'el_max_deg': args['el-max'],
                 'az0_angle_rad': round(math.atan2(first['dir'][0], first['dir'][2]), 6), 'az_sign': az_sign,
                 'convention': 'frame dir = unit vector from the asset towards the camera in asset-local Babylon axes; '
                               'azimuth angle = atan2(dir.x, dir.z); frame az index i has angle az0 + az_sign * i * 2pi/azimuth; '
                               'elevation row j has asin(dir.y) = el_min + j * (el_max - el_min) / (elevation - 1)'},
        'passes': {'albedo': 'sRGB-encoded straight alpha, edge-bled (KTX2 stored as UNORM: sample without hardware sRGB decode)', 'normal': 'object-space normal in Babylon axes * 0.5 + 0.5 (half resolution), A = coverage'},
        'shading': args.get('shading', {}),
        'uv': 'v = 0 is the top row of the image (load PNG with invertY = false; KTX2 has no flip)',
        'frames': frame_records,
        'pages': page_records,
        'objects': [{
            'id': asset.id,
            'source': asset.path.relative_to(ROOT).as_posix() if asset.path.is_relative_to(ROOT) else asset.path.name,
            'source_sha256': hashlib.sha256(asset.path.read_bytes()).hexdigest(),
            'source_triangles': asset.triangles,
            'page': page_index, 'col': col0, 'row': row0,
            'card_size_m': round(asset.card, 4),
            'height_m': round(asset.height, 4),
            'horizontal_radius_m': round(asset.horizontal_radius, 4),
            'center_from_pivot': blender_to_babylon(asset.center - asset.pivot),
            'center_from_origin': blender_to_babylon(asset.center - asset.origin),
            'pivot_from_origin': blender_to_babylon(asset.pivot - asset.origin),
        } for asset, (page_index, col0, row0) in zip(assets, placements)],
        'status': 'CANDIDATE: verify in Babylon (tests/impostor-review.html) before replacing meshes',
    }
    (out / f'{args["name"]}.impostors.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('MANIFEST', out / f'{args["name"]}.impostors.json')


if __name__ == '__main__':
    main()
