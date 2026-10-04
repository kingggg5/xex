"""Blender texture forge for the R5 city materials (Claude lane, 2026-10-01).

Each material is built as real, wrap-around geometry inside one square tile
(stones, slates, planks, cobbles, grass blades), rendered top-down with an
orthographic Cycles camera into data passes (albedo, normal, height, AO, edge,
id) and composited with periodic numpy noise into seamless PBR maps.

Output contract matches build_materials_r5.py so the city build can pick the
maps up unchanged: <name>_albedo.png (sRGB), <name>_normal.png (OpenGL, +Y up),
<name>_orm.png (R ambient occlusion, G roughness, B metal). Tile sizes in
metres are the same as the R5 foundry, so UV density does not change.

Run from the repo root:
  blender -b --factory-startup --python assets/blender/city_r5/forge/forge_textures_r6.py -- \
      --out assets/models/reference-city/r5/textures-forge-r6 [--only roof_slate_blue,cobble_path]
      [--render 2048] [--final 1024] [--seed 6]

Writes forge-manifest.json with hashes. Never writes into the live textures/ folder.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector, noise

ROOT = Path(__file__).resolve().parents[4]


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def parse_args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = {'out': 'assets/models/reference-city/r5/textures-forge-r6', 'only': '', 'render': 2048, 'final': 1024, 'seed': 6}
    i = 0
    while i < len(argv):
        key = argv[i].lstrip('-')
        if key in args and i + 1 < len(argv):
            args[key] = type(args[key])(argv[i + 1]) if not isinstance(args[key], str) else argv[i + 1]
            i += 2
        else:
            raise SystemExit(f'unknown argument {argv[i]}')
    out = Path(args['out'])
    args['out'] = out if out.is_absolute() else ROOT / out
    if 'textures' == args['out'].name:
        raise SystemExit('refusing to overwrite the live textures/ folder; write a candidate folder')
    return args


# ----------------------------------------------------------------------------
# Colour helpers
# ----------------------------------------------------------------------------

def srgb_to_linear(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def hexrgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def jitter_color(rng: random.Random, palette: list[str], value_jitter=0.08, hue_jitter=0.02):
    base = np.array(hexrgb(rng.choice(palette)), np.float32)
    v = 1.0 + rng.uniform(-value_jitter, value_jitter)
    tint = np.array([1 + rng.uniform(-hue_jitter, hue_jitter) for _ in range(3)], np.float32)
    return tuple(float(x) for x in srgb_to_linear(np.clip(base * v * tint, 0, 1)))


# ----------------------------------------------------------------------------
# Periodic numpy noise (seamless by construction)
# ----------------------------------------------------------------------------

def pnoise(size: int, feature_px: float, seed: int, octaves=1, persistence=0.5) -> np.ndarray:
    """Band-limited periodic noise in [0, 1] built from filtered white noise in the FFT domain."""
    rng = np.random.default_rng(seed)
    total = np.zeros((size, size), np.float32)
    amp, weight = 1.0, 0.0
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.rfftfreq(size)[None, :]
    radius = np.sqrt(fx * fx + fy * fy)
    for octave in range(octaves):
        sigma = 1.0 / max(1.0, feature_px / (2 ** octave))
        spectrum = np.fft.rfft2(rng.standard_normal((size, size)).astype(np.float32))
        layer = np.fft.irfft2(spectrum * np.exp(-(radius / sigma) ** 2), s=(size, size)).astype(np.float32)
        layer /= max(1e-6, float(layer.std()))
        total += layer * amp
        weight += amp
        amp *= persistence
    total /= weight
    lo, hi = np.percentile(total, 1), np.percentile(total, 99)
    return np.clip((total - lo) / max(1e-6, hi - lo), 0.0, 1.0)


def sample_periodic(field: np.ndarray, u: float, v: float) -> float:
    """Bilinear sample of a periodic field at tile-relative coordinates (u, v in tiles)."""
    n = field.shape[0]
    x, y = (u % 1.0) * n, (v % 1.0) * n
    x0, y0 = int(math.floor(x)) % n, int(math.floor(y)) % n
    x1, y1 = (x0 + 1) % n, (y0 + 1) % n
    fx, fy = x - math.floor(x), y - math.floor(y)
    top = field[y0, x0] * (1 - fx) + field[y0, x1] * fx
    bottom = field[y1, x0] * (1 - fx) + field[y1, x1] * fx
    return float(top * (1 - fy) + bottom * fy)


def smoothstep(a, b, x):
    t = np.clip((x - a) / max(1e-6, b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------
# Scene
# ----------------------------------------------------------------------------

class Forge:
    def __init__(self, name: str, tile_m: float, render_px: int, seed: int):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.name, self.T, self.px = name, tile_m, render_px
        self.rng = random.Random(f'{name}:{seed}')
        self.seed = seed
        self.scene = bpy.context.scene
        self.collection = self.scene.collection
        self.margin = 0.0
        self._setup_render()
        self._setup_camera()
        self.pass_materials = self._pass_materials()

    # -- render setup ---------------------------------------------------------
    def _setup_render(self):
        scene = self.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            prefs.compute_device_type = 'CUDA'
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type == 'CUDA']
            for device in prefs.devices:
                device.use = device.type == 'CUDA'
            if gpus:
                scene.cycles.device = 'GPU'
        except Exception:
            scene.cycles.device = 'CPU'
        scene.cycles.max_bounces = 0
        scene.cycles.diffuse_bounces = 0
        scene.cycles.glossy_bounces = 0
        scene.cycles.transmission_bounces = 0
        scene.cycles.use_adaptive_sampling = False
        scene.render.resolution_x = scene.render.resolution_y = self.px
        scene.render.resolution_percentage = 100
        scene.render.filter_size = 1.0
        scene.render.film_transparent = False
        world = bpy.data.worlds.new('forge-world')
        world.use_nodes = True
        world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)
        scene.world = world
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
        settings = scene.render.image_settings
        settings.file_format = 'OPEN_EXR'
        settings.color_depth = '32'
        settings.exr_codec = 'ZIP'
        settings.color_mode = 'RGB'

    def _setup_camera(self):
        data = bpy.data.cameras.new('forge-cam')
        data.type = 'ORTHO'
        data.ortho_scale = self.T
        data.clip_start = 0.01
        data.clip_end = 200.0
        cam = bpy.data.objects.new('forge-cam', data)
        cam.location = (self.T / 2, self.T / 2, 50.0)
        cam.rotation_euler = (0.0, 0.0, 0.0)
        self.collection.objects.link(cam)
        self.scene.camera = cam

    # -- pass materials -----------------------------------------------------
    def _emission_material(self, name: str, build) -> bpy.types.Material:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        nodes, links = material.node_tree.nodes, material.node_tree.links
        nodes.clear()
        out = nodes.new('ShaderNodeOutputMaterial')
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs['Strength'].default_value = 1.0
        links.new(emission.outputs['Emission'], out.inputs['Surface'])
        links.new(build(nodes, links), emission.inputs['Color'])
        return material

    def _pass_materials(self) -> dict:
        def albedo(nodes, links):
            obj_attr = nodes.new('ShaderNodeAttribute'); obj_attr.attribute_type = 'OBJECT'; obj_attr.attribute_name = 'albedo'
            vcol = nodes.new('ShaderNodeAttribute'); vcol.attribute_type = 'GEOMETRY'; vcol.attribute_name = 'col'
            use = nodes.new('ShaderNodeAttribute'); use.attribute_type = 'OBJECT'; use.attribute_name = 'use_vcol'
            mix = nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'
            links.new(use.outputs['Fac'], mix.inputs['Factor'])
            links.new(obj_attr.outputs['Color'], mix.inputs['A'])
            links.new(vcol.outputs['Color'], mix.inputs['B'])
            # Per-object mineral speckle in object space; copies share mesh data, so it tiles.
            coords = nodes.new('ShaderNodeTexCoord')
            grain = nodes.new('ShaderNodeTexNoise'); grain.inputs['Scale'].default_value = 38.0; grain.inputs['Detail'].default_value = 6.0
            links.new(coords.outputs['Object'], grain.inputs['Vector'])
            amount = nodes.new('ShaderNodeAttribute'); amount.attribute_type = 'OBJECT'; amount.attribute_name = 'speckle'
            remap = nodes.new('ShaderNodeMath'); remap.operation = 'MULTIPLY_ADD'
            links.new(grain.outputs['Fac'], remap.inputs[0]); links.new(amount.outputs['Fac'], remap.inputs[1])
            offset = nodes.new('ShaderNodeMath'); offset.operation = 'MULTIPLY'; offset.inputs[1].default_value = -0.5
            links.new(amount.outputs['Fac'], offset.inputs[0]); links.new(offset.outputs[0], remap.inputs[2])
            bias = nodes.new('ShaderNodeMath'); bias.operation = 'ADD'; bias.inputs[1].default_value = 1.0
            links.new(remap.outputs[0], bias.inputs[0])
            scale = nodes.new('ShaderNodeMix'); scale.data_type = 'RGBA'; scale.blend_type = 'MULTIPLY'; scale.inputs['Factor'].default_value = 1.0
            links.new(mix.outputs['Result'], scale.inputs['A'])
            combine = nodes.new('ShaderNodeCombineColor')
            for channel in ('Red', 'Green', 'Blue'):
                links.new(bias.outputs[0], combine.inputs[channel])
            links.new(combine.outputs['Color'], scale.inputs['B'])
            return scale.outputs['Result']

        def normal(nodes, links):
            geometry = nodes.new('ShaderNodeNewGeometry')
            mad = nodes.new('ShaderNodeVectorMath'); mad.operation = 'MULTIPLY_ADD'
            mad.inputs[1].default_value = (0.5, 0.5, 0.5); mad.inputs[2].default_value = (0.5, 0.5, 0.5)
            links.new(geometry.outputs['Normal'], mad.inputs[0])
            return mad.outputs['Vector']

        def height(nodes, links):
            geometry = nodes.new('ShaderNodeNewGeometry')
            split = nodes.new('ShaderNodeSeparateXYZ')
            links.new(geometry.outputs['Position'], split.inputs['Vector'])
            combine = nodes.new('ShaderNodeCombineColor')
            for channel in ('Red', 'Green', 'Blue'):
                links.new(split.outputs['Z'], combine.inputs[channel])
            return combine.outputs['Color']

        def ao(nodes, links):
            node = nodes.new('ShaderNodeAmbientOcclusion'); node.samples = 16; node.inputs['Distance'].default_value = 0.08
            node.name = 'forge-ao'
            combine = nodes.new('ShaderNodeCombineColor')
            for channel in ('Red', 'Green', 'Blue'):
                links.new(node.outputs['AO'], combine.inputs[channel])
            return combine.outputs['Color']

        def edge(nodes, links):
            bevel = nodes.new('ShaderNodeBevel'); bevel.samples = 8; bevel.inputs['Radius'].default_value = 0.012
            bevel.name = 'forge-bevel'
            geometry = nodes.new('ShaderNodeNewGeometry')
            dot = nodes.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
            links.new(bevel.outputs['Normal'], dot.inputs[0]); links.new(geometry.outputs['Normal'], dot.inputs[1])
            inv = nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
            links.new(dot.outputs['Value'], inv.inputs[1])
            gain = nodes.new('ShaderNodeMath'); gain.operation = 'MULTIPLY'; gain.inputs[1].default_value = 6.0; gain.use_clamp = True
            links.new(inv.outputs[0], gain.inputs[0])
            combine = nodes.new('ShaderNodeCombineColor')
            for channel in ('Red', 'Green', 'Blue'):
                links.new(gain.outputs[0], combine.inputs[channel])
            return combine.outputs['Color']

        def ident(nodes, links):
            info = nodes.new('ShaderNodeObjectInfo')
            kind = nodes.new('ShaderNodeAttribute'); kind.attribute_type = 'OBJECT'; kind.attribute_name = 'kind'
            rough = nodes.new('ShaderNodeAttribute'); rough.attribute_type = 'OBJECT'; rough.attribute_name = 'rough'
            combine = nodes.new('ShaderNodeCombineColor')
            links.new(info.outputs['Random'], combine.inputs['Red'])
            links.new(kind.outputs['Fac'], combine.inputs['Green'])
            links.new(rough.outputs['Fac'], combine.inputs['Blue'])
            return combine.outputs['Color']

        return {name: self._emission_material(f'forge-pass-{name}', fn)
                for name, fn in (('albedo', albedo), ('normal', normal), ('height', height),
                                 ('ao', ao), ('edge', edge), ('id', ident))}

    # -- geometry helpers ---------------------------------------------------
    def add(self, mesh: bpy.types.Mesh, location, rotation=(0, 0, 0), *, albedo, kind=1.0, rough=0.85,
            speckle=0.12, use_vcol=0.0, wrap=True, name='part') -> None:
        """Link a mesh plus its wrap-around copies so the tile is seamless."""
        offsets = [(0.0, 0.0)]
        if wrap:
            offsets = [(dx * self.T, dy * self.T) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        radius = max((max(abs(c) for c in v.co) for v in mesh.vertices), default=1.0)
        albedo = [float(c) for c in albedo]
        x, y = location[0], location[1]
        for dx, dy in offsets:
            px, py = x + dx, y + dy
            reach = self.margin + radius
            if px < -reach or px > self.T + reach or py < -reach or py > self.T + reach:
                continue
            obj = bpy.data.objects.new(name, mesh)
            obj.location = (px, py, location[2])
            obj.rotation_euler = rotation
            obj['albedo'] = list(albedo)
            obj['kind'] = float(kind)
            obj['rough'] = float(rough)
            obj['speckle'] = float(speckle)
            obj['use_vcol'] = float(use_vcol)
            self.collection.objects.link(obj)

    def render(self, out_dir: Path) -> dict:
        """Render every data pass to EXR and return numpy arrays (H, W, 3) with row 0 = image top."""
        arrays = {}
        layer = self.scene.view_layers[0]
        for name, material in self.pass_materials.items():
            layer.material_override = material
            samples = {'ao': 32, 'edge': 16}.get(name, 6)
            self.scene.cycles.samples = samples
            self.scene.cycles.use_denoising = name in ('ao', 'edge')
            path = out_dir / '_passes' / f'{self.name}_{name}.exr'
            path.parent.mkdir(parents=True, exist_ok=True)
            self.scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            image = bpy.data.images.load(str(path), check_existing=False)
            image.colorspace_settings.name = 'Non-Color'
            pixels = np.empty(self.px * self.px * 4, np.float32)
            image.pixels.foreach_get(pixels)
            arrays[name] = np.flipud(pixels.reshape(self.px, self.px, 4)[..., :3]).copy()
            bpy.data.images.remove(image)
        layer.material_override = None
        return arrays


def finalize_mesh(bm: bmesh.types.BMesh, name: str, smooth=True) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    mesh.update()
    return mesh


def chipped_block(rng: random.Random, sx, sy, sz, bevel, chips=2, displace=0.0, freq=6.0, segments=2, name='block', cuts=3):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= sx; v.co.y *= sy; v.co.z *= sz
    for _ in range(chips):
        corner = Vector((rng.choice((-1, 1)) * sx / 2, rng.choice((-1, 1)) * sy / 2, sz / 2))
        depth = rng.uniform(0.07, 0.22) * min(sx, sy, sz * 2)
        direction = Vector((corner.x / max(1e-6, abs(corner.x)) * rng.uniform(0.4, 1.0),
                            corner.y / max(1e-6, abs(corner.y)) * rng.uniform(0.4, 1.0),
                            rng.uniform(0.6, 1.2))).normalized()
        point = corner - direction * depth
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        result = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=point, plane_no=direction, clear_outer=True)
        cut_edges = [e for e in result['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
        if cut_edges:
            bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, offset_type='OFFSET', segments=segments,
                        profile=0.6, affect='EDGES', clamp_overlap=True)
    if displace > 0:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
        seed = Vector((rng.uniform(-90, 90), rng.uniform(-90, 90), rng.uniform(-90, 90)))
        bm.normal_update()
        for v in bm.verts:
            n = noise.noise(v.co * freq + seed) + 0.5 * noise.noise(v.co * freq * 2.7 + seed * 1.7)
            v.co += v.normal * n * displace
    return finalize_mesh(bm, name)


def ground_plane(forge: Forge, height_field: np.ndarray, amplitude: float, res=160, name='ground') -> bpy.types.Mesh:
    """Grid over the tile plus margin whose height is sampled from a periodic field."""
    bm = bmesh.new()
    T = forge.T
    m = forge.margin + T * 0.06
    span = T + 2 * m
    step = span / res
    grid = []
    for j in range(res + 1):
        row = []
        for i in range(res + 1):
            x, y = -m + i * step, -m + j * step
            z = (sample_periodic(height_field, x / T, y / T) - 0.5) * amplitude
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for j in range(res):
        for i in range(res):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    return finalize_mesh(bm, name)


def partition(rng: random.Random, total: float, low: float, high: float) -> list[float]:
    """Random lengths in [low, high] that sum exactly to total (periodic rows)."""
    parts = []
    while sum(parts) < total - low * 0.5:
        parts.append(rng.uniform(low, high))
    scale = total / sum(parts)
    return [p * scale for p in parts]


# ----------------------------------------------------------------------------
# Generators
# ----------------------------------------------------------------------------

def gen_masonry(forge: Forge, spec: dict) -> None:
    rng, T = forge.rng, forge.T
    forge.margin = spec['len'][1]
    mortar = srgb_to_linear(np.array(hexrgb(spec['mortar']), np.float32))
    field = pnoise(256, 24, rng.randrange(1 << 30), octaves=3)
    forge.add(ground_plane(forge, field, spec.get('mortar_relief', 0.006)), (0, 0, 0), albedo=mortar,
              kind=0.0, rough=0.95, speckle=0.18, wrap=False, name='mortar')
    courses = partition(rng, T, *spec['course'])
    y = 0.0
    for course_h in courses:
        lengths = partition(rng, T, *spec['len'])
        x = rng.uniform(0, T)
        for length in lengths:
            gap = spec['gap'] * rng.uniform(0.75, 1.3)
            depth = rng.uniform(*spec['depth'])
            mesh = chipped_block(rng, length - gap, course_h - gap, depth, spec['bevel'] * rng.uniform(0.7, 1.3),
                                 chips=rng.choice(spec.get('chips', (0, 1, 2))), displace=spec.get('displace', 0.004),
                                 freq=spec.get('freq', 7.0), name='stone')
            tilt = spec.get('tilt', 0.012)
            rotation = (rng.uniform(-tilt, tilt), rng.uniform(-tilt, tilt), rng.uniform(-spec.get('twist', 0.01), spec.get('twist', 0.01)))
            z = depth / 2 + rng.uniform(-spec.get('z_jitter', 0.004), spec.get('z_jitter', 0.004))
            forge.add(mesh, ((x + length / 2) % T, y + course_h / 2, z), rotation,
                      albedo=jitter_color(rng, spec['palette'], spec.get('value_jitter', 0.09)),
                      rough=rng.uniform(*spec.get('rough', (0.78, 0.9))), speckle=spec.get('speckle', 0.16), name='stone')
            x += length
        y += course_h


def gen_cobbles(forge: Forge, spec: dict) -> None:
    rng, T = forge.rng, forge.T
    forge.margin = spec['radius'][1] * 2
    sand = srgb_to_linear(np.array(hexrgb(spec['mortar']), np.float32))
    field = pnoise(256, 18, rng.randrange(1 << 30), octaves=3)
    forge.add(ground_plane(forge, field, 0.012), (0, 0, 0), albedo=sand, kind=0.0, rough=0.97, speckle=0.25,
              wrap=False, name='sand')
    points: list[tuple[float, float, float]] = []
    r_lo, r_hi = spec['radius']
    # Dense packing: large stones first, then progressively smaller ones fill the joints.
    for band in range(4):
        hi = r_hi - (r_hi - r_lo) * band / 4
        lo = r_hi - (r_hi - r_lo) * (band + 1) / 4
        for _ in range(spec['attempts']):
            r = rng.uniform(lo, hi)
            x, y = rng.uniform(0, T), rng.uniform(0, T)
            ok = True
            for px, py, pr in points:
                dx = min(abs(x - px), T - abs(x - px))
                dy = min(abs(y - py), T - abs(y - py))
                if dx * dx + dy * dy < (r + pr + spec['gap']) ** 2:
                    ok = False
                    break
            if ok:
                points.append((x, y, r))
    for x, y, r in points:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
        sx, sy = r * rng.uniform(0.9, 1.2), r * rng.uniform(0.8, 1.05)
        sz = r * spec.get('flat', 0.42)
        seed = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50)))
        for v in bm.verts:
            n = noise.noise(v.co * 2.2 + seed)
            v.co.x *= sx * (1 + 0.12 * n)
            v.co.y *= sy * (1 + 0.12 * n)
            v.co.z *= sz * (1 + 0.2 * n)
            if v.co.z < 0:
                v.co.z *= 0.3
            elif v.co.z > sz * 0.72:
                v.co.z = sz * 0.72 + (v.co.z - sz * 0.72) * 0.35  # worn, walkable tops
        mesh = finalize_mesh(bm, 'cobble')
        forge.add(mesh, (x, y, sz * 0.35), (0, 0, rng.uniform(0, math.tau)),
                  albedo=jitter_color(rng, spec['palette'], 0.12, 0.03), rough=rng.uniform(0.72, 0.86),
                  speckle=0.2, name='cobble')


def roof_tile_mesh(rng: random.Random, width, length, thickness, shape: str, bevel) -> bpy.types.Mesh:
    """Flat tile outline in XY (bottom edge at y=0) extruded to thickness."""
    outline: list[tuple[float, float]] = []
    w2 = width / 2
    if shape == 'round':
        outline += [(w2, length), (-w2, length)]
        for k in range(13):
            a = math.pi + k / 12 * math.pi
            outline.append((math.cos(a) * w2, w2 + math.sin(a) * w2 * 0.9))
    elif shape == 'shingle':
        outline += [(w2, length), (-w2, length), (-w2, rng.uniform(0.0, 0.03))]
        for k in range(1, 6):
            outline.append((-w2 + width * k / 6, rng.uniform(0.0, 0.035)))
        outline.append((w2, rng.uniform(0.0, 0.03)))
    else:
        cut = rng.uniform(0.01, 0.04)
        outline += [(w2, length), (-w2, length), (-w2, cut * rng.uniform(0.3, 1.0)),
                    (-w2 + cut, 0.0), (w2 - cut * rng.uniform(0.2, 1.0), 0.0), (w2, cut)]
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, 0.0)) for x, y in outline]
    face = bm.faces.new(verts)
    bmesh.ops.reverse_faces(bm, faces=[face]) if face.normal.z < 0 else None
    result = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [v for v in result['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, thickness), verts=top)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=2, profile=0.6, affect='EDGES', clamp_overlap=True)
    seed = Vector((rng.uniform(-40, 40), rng.uniform(-40, 40), 0))
    for v in bm.verts:
        v.co.z += noise.noise(v.co * 9.0 + seed) * thickness * 0.18
    return finalize_mesh(bm, 'roof-tile')


def gen_roof(forge: Forge, spec: dict) -> None:
    rng, T = forge.rng, forge.T
    pitch = T / round(T / spec['pitch'])
    length = pitch * spec.get('overlap', 2.3)
    forge.margin = length
    under = srgb_to_linear(np.array(hexrgb(spec['under']), np.float32))
    forge.add(ground_plane(forge, pnoise(128, 16, 7, 2), 0.002, res=48), (0, 0, -0.01), albedo=under, kind=0.0,
              rough=0.9, wrap=False, name='underlay')
    lift = spec['lift']
    rows = round(T / pitch)
    for r in range(rows):
        widths = partition(rng, T, *spec['width'])
        x = rng.uniform(0, T) if spec.get('random_offset') else (r % 2) * sum(widths) / len(widths) * 0.5
        for width in widths:
            w = width - spec['gap'] * rng.uniform(0.7, 1.3)
            mesh = roof_tile_mesh(rng, w, length, spec['thickness'], spec['shape'], spec['bevel'])
            tilt = math.atan2(lift, length) + rng.uniform(-0.01, 0.01)
            rotation = (-tilt, rng.uniform(-0.02, 0.02), rng.uniform(-0.018, 0.018))
            forge.add(mesh, ((x + width / 2) % T, r * pitch + pitch * 0.37 + rng.uniform(-0.006, 0.006), lift + rng.uniform(-0.003, 0.003)),
                      rotation, albedo=jitter_color(rng, spec['palette'], 0.1, 0.025), rough=rng.uniform(*spec['rough']),
                      speckle=0.2, name='tile')
            x += width


def gen_planks(forge: Forge, spec: dict) -> None:
    rng, T = forge.rng, forge.T
    forge.margin = spec['len'][1]
    backing = srgb_to_linear(np.array(hexrgb(spec['gapcolor']), np.float32))
    forge.add(ground_plane(forge, pnoise(128, 12, 3, 2), 0.002, res=48), (0, 0, -0.004), albedo=backing, kind=0.0,
              rough=0.95, wrap=False, name='backing')
    rows = partition(rng, T, *spec['board'])
    y = 0.0
    for board_w in rows:
        lengths = partition(rng, T, *spec['len'])
        x = rng.uniform(0, T)
        for board_len in lengths:
            gap = spec['gap']
            bm = bmesh.new()
            bmesh.ops.create_grid(bm, x_segments=max(8, int(board_len / 0.05)), y_segments=6, size=0.5)
            for v in bm.verts:
                v.co.x *= board_len - gap
                v.co.y *= board_w - gap
            seed = Vector((rng.uniform(-60, 60), rng.uniform(-60, 60), 0))
            result = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
            top = [v for v in result['geom'] if isinstance(v, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, vec=(0, 0, spec['thick']), verts=top)
            bmesh.ops.bevel(bm, geom=[e for e in bm.edges if e.is_boundary or len(e.link_faces) == 2 and abs(e.link_faces[0].normal.dot(e.link_faces[1].normal)) < 0.5],
                            offset=spec['bevel'], segments=2, profile=0.6, affect='EDGES', clamp_overlap=True)
            for v in bm.verts:
                if v.co.z > spec['thick'] * 0.5:
                    grain = noise.noise(Vector((v.co.x * 2.5, v.co.y * 34.0, 0)) + seed)
                    v.co.z += grain * spec['grain']
            mesh = finalize_mesh(bm, 'plank')
            forge.add(mesh, ((x + board_len / 2) % T, y + board_w / 2, 0.0), (0, 0, rng.uniform(-0.004, 0.004)),
                      albedo=jitter_color(rng, spec['palette'], 0.12, 0.02), rough=rng.uniform(0.74, 0.86), speckle=0.08,
                      name='plank')
            for end in (-1, 1):
                for k in range(2):
                    nail = bmesh.new()
                    bmesh.ops.create_cone(nail, cap_ends=True, segments=10, radius1=0.007, radius2=0.006, depth=0.004)
                    nail_mesh = finalize_mesh(nail, 'nail')
                    forge.add(nail_mesh, ((x + board_len / 2 + end * (board_len / 2 - 0.05)) % T,
                                          y + board_w * (0.3 + 0.4 * k), spec['thick'] + 0.002),
                              albedo=srgb_to_linear(np.array(hexrgb('#3a3632'), np.float32)), rough=0.5, speckle=0.0,
                              name='nail')
            x += board_len
        y += board_w


def gen_plaster(forge: Forge, spec: dict) -> None:
    rng, T = forge.rng, forge.T
    forge.margin = 0.6
    field = pnoise(512, 60, rng.randrange(1 << 30), octaves=4, persistence=0.55)
    color = srgb_to_linear(np.array(hexrgb(spec['plaster']), np.float32))
    forge.add(ground_plane(forge, field, spec['relief'], res=220), (0, 0, 0.02), albedo=color, kind=0.0, rough=0.9,
              speckle=0.05, wrap=False, name='plaster')
    for _ in range(spec['patches']):
        cx, cy = rng.uniform(0, T), rng.uniform(0, T)
        for k in range(rng.randint(3, 6)):
            length, height = rng.uniform(0.22, 0.38), rng.uniform(0.1, 0.14)
            mesh = chipped_block(rng, length, height, 0.04, 0.008, chips=1, displace=0.003, name='brick')
            forge.add(mesh, (cx + (k % 3) * 0.3 + (0.15 if (k // 3) % 2 else 0), cy + (k // 3) * 0.14, 0.012),
                      albedo=jitter_color(rng, spec['palette'], 0.1), rough=0.85, speckle=0.12, name='brick')


def gen_grass(forge: Forge, spec: dict) -> None:
    rng, T = forge.rng, forge.T
    forge.margin = 0.2
    dirt = srgb_to_linear(np.array(hexrgb(spec['dirt']), np.float32))
    forge.add(ground_plane(forge, pnoise(256, 30, rng.randrange(1 << 30), 3), 0.03, res=120), (0, 0, 0),
              albedo=dirt, kind=0.0, rough=0.98, speckle=0.3, wrap=False, name='dirt')
    density = pnoise(256, 40, rng.randrange(1 << 30), 2)
    bm = bmesh.new()
    col = bm.loops.layers.color.new('col')
    palette = [srgb_to_linear(np.array(hexrgb(c), np.float32)) for c in spec['blades']]
    tips = [srgb_to_linear(np.array(hexrgb(c), np.float32)) for c in spec['tips']]
    clumps = 0
    for _ in range(spec['clumps']):
        x, y = rng.uniform(0, T), rng.uniform(0, T)
        if rng.random() > spec.get('coverage', 0.25) + (1 - spec.get('coverage', 0.25)) * sample_periodic(density, x / T, y / T):
            continue
        clumps += 1
        base = palette[rng.randrange(len(palette))] * rng.uniform(0.85, 1.1)
        tip = tips[rng.randrange(len(tips))] * rng.uniform(0.9, 1.1)
        for _blade in range(rng.randint(4, 9)):
            az = rng.uniform(0, math.tau)
            lean = rng.uniform(0.35, 1.05)
            length = rng.uniform(*spec['length'])
            width = rng.uniform(*spec.get('width', (0.006, 0.012)))
            bx, by = x + rng.uniform(-0.03, 0.03), y + rng.uniform(-0.03, 0.03)
            dx, dy = math.cos(az), math.sin(az)
            px, py = -dy * width, dx * width
            tipx = bx + dx * math.sin(lean) * length
            tipy = by + dy * math.sin(lean) * length
            tipz = math.cos(lean) * length
            for ox, oy in ((0, 0), (T, 0), (-T, 0), (0, T), (0, -T)):
                if (ox or oy) and not (min(bx, tipx) + ox < 0.2 or max(bx, tipx) + ox > T - 0.2 or
                                      min(by, tipy) + oy < 0.2 or max(by, tipy) + oy > T - 0.2):
                    continue
                if ox and not ((bx + ox) > -0.2 and (bx + ox) < T + 0.2):
                    continue
                if oy and not ((by + oy) > -0.2 and (by + oy) < T + 0.2):
                    continue
                v1 = bm.verts.new((bx + px + ox, by + py + oy, 0.0))
                v2 = bm.verts.new((bx - px + ox, by - py + oy, 0.0))
                v3 = bm.verts.new((tipx + ox, tipy + oy, tipz))
                face = bm.faces.new((v1, v2, v3))
                for loop, c in zip(face.loops, (base, base, tip)):
                    loop[col] = (float(c[0]), float(c[1]), float(c[2]), 1.0)
    mesh = finalize_mesh(bm, 'grass-blades', smooth=False)
    forge.add(mesh, (0, 0, 0), albedo=(0.1, 0.2, 0.05), kind=1.0, rough=0.9, speckle=0.0, use_vcol=1.0, wrap=False,
              name='blades')
    print(f'  grass clumps: {clumps}')



def gen_strata(forge: Forge, spec: dict) -> None:
    rng, T = forge.rng, forge.T
    forge.margin = spec['seg'][1]
    back = srgb_to_linear(np.array(hexrgb(spec['back']), np.float32))
    forge.add(ground_plane(forge, pnoise(256, 20, rng.randrange(1 << 30), 3), 0.08), (0, 0, 0), albedo=back,
              kind=0.0, rough=0.97, speckle=0.3, wrap=False, name='crevice')
    layers = partition(rng, T, *spec['layer'])
    y = 0.0
    for layer_h in layers:
        band = jitter_color(rng, spec['palette'], 0.06, 0.02)
        protrude = rng.uniform(*spec['protrude'])
        lengths = partition(rng, T, *spec['seg'])
        x = rng.uniform(0, T)
        for length in lengths:
            gap = spec['gap'] * rng.uniform(0.6, 1.6)
            depth = protrude + rng.uniform(-0.05, 0.05)
            mesh = chipped_block(rng, length - gap, layer_h - gap * 0.6, depth, spec['bevel'] * rng.uniform(0.7, 1.4),
                                 chips=rng.choice(spec.get('chips', (1, 2))), displace=spec['displace'], freq=spec['freq'],
                                 name='strata', cuts=spec.get('cuts', 6))
            tint = np.array(band, np.float32) * rng.uniform(0.9, 1.1)
            rotation = (rng.uniform(-0.03, 0.03), rng.uniform(-0.05, 0.05), rng.uniform(-0.04, 0.04))
            forge.add(mesh, ((x + length / 2) % T, y + layer_h / 2 + rng.uniform(-0.04, 0.04), depth / 2), rotation,
                      albedo=tuple(float(c) for c in tint), rough=rng.uniform(0.84, 0.95), speckle=0.22, name='strata')
            x += length
        y += layer_h

GENERATORS = {'strata': gen_strata, 'masonry': gen_masonry, 'cobbles': gen_cobbles, 'roof': gen_roof, 'planks': gen_planks,
              'plaster': gen_plaster, 'grass': gen_grass}


# ----------------------------------------------------------------------------
# Material specs (tile sizes match the R5 foundry so UV density is unchanged)
# ----------------------------------------------------------------------------

WARM_STONE = ['#9c8a70', '#ae9a7c', '#bba889', '#c7b494', '#a49482', '#d0bd9b']
COOL_STONE = ['#5f666d', '#6e7378', '#7c7f80', '#878784', '#646f76', '#8f8c86']
SPECS: dict[str, dict] = {
    'stone_wall_warm': dict(gen='masonry', tile=2.4, course=(0.24, 0.36), len=(0.34, 0.72), gap=0.018, depth=(0.05, 0.08),
                            bevel=0.012, chips=(0, 1, 1, 2), palette=WARM_STONE, mortar='#a39578', displace=0.006,
                            look=dict(cavity=0.32, edge=0.16, dirt='#4a4034', dirt_amt=0.2, moss=0.0, rough=(0.8, 0.95), normal=0.85)),
    'stone_foundation': dict(gen='masonry', tile=2.4, course=(0.34, 0.56), len=(0.42, 0.95), gap=0.024, depth=(0.06, 0.11),
                             bevel=0.018, chips=(1, 2, 2, 3), palette=['#6a6862', '#77736a', '#5e5d58', '#827c70'],
                             mortar='#4e4a42', displace=0.008, tilt=0.03, z_jitter=0.01,
                             look=dict(cavity=0.5, edge=0.14, dirt='#2f2a24', dirt_amt=0.35, moss=0.3, rough=(0.82, 0.97), normal=0.95)),
    'stone_trim_carved': dict(gen='masonry', tile=1.6, course=(0.26, 0.4), len=(0.38, 0.62), gap=0.008, depth=(0.05, 0.07),
                              bevel=0.008, chips=(0, 0, 1), palette=['#c0b296', '#cbbd9f', '#b8a98c', '#d3c5a6'],
                              mortar='#9a8f79', displace=0.002, tilt=0.006,
                              look=dict(cavity=0.3, edge=0.2, dirt='#5c5242', dirt_amt=0.18, moss=0.0, rough=(0.74, 0.9), normal=0.75)),
    'stone_accent_bluegrey': dict(gen='masonry', tile=2.0, course=(0.22, 0.34), len=(0.3, 0.6), gap=0.014, depth=(0.05, 0.08),
                                  bevel=0.01, chips=(0, 1, 2), palette=COOL_STONE, mortar='#6a6e70', displace=0.006,
                                  look=dict(cavity=0.35, edge=0.16, dirt='#2e3134', dirt_amt=0.22, moss=0.1, rough=(0.78, 0.93), normal=0.85)),
    'plaza_flagstone': dict(gen='masonry', tile=4.0, course=(0.42, 0.8), len=(0.55, 1.2), gap=0.016, depth=(0.03, 0.045),
                            bevel=0.014, chips=(0, 1, 1), palette=['#b8a688', '#c4b293', '#a99a83', '#9e9384', '#cdbb9a'],
                            mortar='#6f6656', displace=0.003, tilt=0.008, z_jitter=0.005,
                            look=dict(cavity=0.5, edge=0.12, dirt='#4a4236', dirt_amt=0.4, moss=0.12, rough=(0.78, 0.94), normal=0.8)),
    'paver_surface': dict(gen='masonry', tile=2.0, course=(0.16, 0.2), len=(0.22, 0.34), gap=0.01, depth=(0.03, 0.04),
                          bevel=0.008, chips=(0, 0, 1), palette=['#8f8b84', '#9a958c', '#86827c', '#a39e94'],
                          mortar='#5c5850', displace=0.002, tilt=0.006,
                          look=dict(cavity=0.5, edge=0.12, dirt='#3c3934', dirt_amt=0.35, moss=0.05, rough=(0.8, 0.94), normal=0.75)),
    'cobble_path': dict(gen='cobbles', tile=2.6, radius=(0.045, 0.1), gap=0.007, attempts=6000, flat=0.42,
                        palette=['#6c675e', '#7a746a', '#857d71', '#5e5b55', '#8d8678', '#706b66'], mortar='#7a6d58',
                        look=dict(cavity=0.6, edge=0.14, dirt='#3e3428', dirt_amt=0.45, moss=0.18, rough=(0.76, 0.97), normal=0.9)),
    'roof_slate_blue': dict(gen='roof', tile=2.2, pitch=0.22, width=(0.24, 0.36), gap=0.01, thickness=0.02, lift=0.028,
                            shape='slate', bevel=0.004, palette=['#2f4f8f', '#365aa0', '#3e64aa', '#2b4680', '#4a6fb3', '#33528f'],
                            under='#121a2a', rough=(0.55, 0.72),
                            look=dict(cavity=0.72, edge=0.3, dirt='#141a24', dirt_amt=0.3, moss=0.08, rough=(0.55, 0.85), normal=0.9)),
    'roof_slate_navy': dict(gen='roof', tile=2.2, pitch=0.22, width=(0.24, 0.36), gap=0.01, thickness=0.02, lift=0.028,
                            shape='slate', bevel=0.004, palette=['#1d2c52', '#22355f', '#29406e', '#1a2747', '#30477a'],
                            under='#0c1220', rough=(0.55, 0.72),
                            look=dict(cavity=0.72, edge=0.28, dirt='#0d121c', dirt_amt=0.3, moss=0.06, rough=(0.55, 0.85), normal=0.9)),
    'roof_shingle_green': dict(gen='roof', tile=2.2, pitch=0.2, width=(0.18, 0.28), gap=0.01, thickness=0.02, lift=0.028,
                               shape='round', bevel=0.004, palette=['#2f6a4e', '#357658', '#2a5e46', '#3d8060', '#2c6450'],
                               under='#0f1f18', rough=(0.6, 0.78),
                               look=dict(cavity=0.6, edge=0.2, dirt='#0e1a14', dirt_amt=0.3, moss=0.12, rough=(0.6, 0.88), normal=0.9)),
    'roof_tile_red': dict(gen='roof', tile=2.2, pitch=0.19, width=(0.18, 0.24), gap=0.009, thickness=0.022, lift=0.03,
                          shape='round', bevel=0.005, palette=['#8a3424', '#9c3e2a', '#a8492f', '#7c2e22', '#b25536'],
                          under='#1e0d08', rough=(0.66, 0.82),
                          look=dict(cavity=0.6, edge=0.18, dirt='#24120c', dirt_amt=0.3, moss=0.1, rough=(0.66, 0.9), normal=0.9)),
    'timber_dark': dict(gen='planks', tile=2.0, board=(0.16, 0.26), len=(0.7, 1.6), gap=0.006, thick=0.03, bevel=0.005,
                        grain=0.0022, palette=['#4a2c18', '#57341c', '#3f2615', '#623b20', '#4e3019'], gapcolor='#140b06',
                        look=dict(cavity=0.55, edge=0.18, dirt='#1c120a', dirt_amt=0.3, moss=0.0, rough=(0.72, 0.92), normal=0.8)),
    'plaster_cream': dict(gen='plaster', tile=3.0, plaster='#d8c9a6', relief=0.018, patches=4, palette=WARM_STONE,
                          look=dict(cavity=0.5, edge=0.1, dirt='#8a7a5c', dirt_amt=0.35, moss=0.0, rough=(0.84, 0.95), normal=0.75, macro_amp=0.32, micro=0.5)),
    'grass_ground': dict(gen='grass', tile=6.0, clumps=15000, coverage=0.6, length=(0.09, 0.21), width=(0.013, 0.026), dirt='#3f4a27',
                         blades=['#3f6b2a', '#4c7a2f', '#567f32', '#3a5f27', '#5f8a38'], tips=['#a8c25a', '#b9cc6a', '#93b04c', '#c2c46e'],
                         look=dict(cavity=0.5, edge=0.0, dirt='#3b2f20', dirt_amt=0.2, moss=0.0, rough=(0.88, 0.98), normal=0.7)),
    'cliff_rock': dict(gen='strata', tile=9.0, layer=(0.35, 1.25), seg=(1.0, 3.8), gap=0.05, protrude=(0.2, 0.55),
                       bevel=0.06, displace=0.16, freq=0.85, cuts=8, chips=(0, 1, 1), back='#2e2822',
                       palette=['#7d705f', '#8a7c68', '#6f6556', '#958673', '#665d50', '#a08f78'],
                       look=dict(cavity=0.7, edge=0.2, dirt='#2a241d', dirt_amt=0.4, moss=0.22, rough=(0.82, 0.97), normal=1.0, macro_amp=0.24)),
}


# ----------------------------------------------------------------------------
# Compositing
# ----------------------------------------------------------------------------

def box_down(img: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return img
    h, w = img.shape[:2]
    return img.reshape(h // factor, factor, w // factor, factor, -1).mean(axis=(1, 3))


def composite(name: str, spec: dict, passes: dict, final_px: int, seed: int):
    look = spec['look']
    n = passes['albedo'].shape[0]
    albedo = passes['albedo']  # linear
    height = passes['height'][..., 0]
    ao = np.clip(passes['ao'][..., 0], 0, 1)
    edge = np.clip(passes['edge'][..., 0], 0, 1)
    ident = passes['id']
    kind = ident[..., 1]
    rough_obj = ident[..., 2]
    normal = passes['normal'] * 2.0 - 1.0
    normal /= np.maximum(1e-6, np.linalg.norm(normal, axis=-1, keepdims=True))

    hmin, hmax = np.percentile(height, 0.5), np.percentile(height, 99.5)
    h01 = np.clip((height - hmin) / max(1e-6, hmax - hmin), 0, 1)

    macro = pnoise(n, n / 5, seed + 11, octaves=3)
    micro = pnoise(n, n / 120, seed + 12, octaves=2)
    cavity = np.clip(1.0 - (1.0 - ao) * 1.6 * (1.0 - 0.5 * kind), 0, 1)
    dirt_mask = np.clip((1.0 - ao) * 1.4 + (1.0 - kind) * 0.35, 0, 1) * smoothstep(0.25, 0.8, macro * 0.6 + (1 - h01) * 0.6)
    dirt = srgb_to_linear(np.array(hexrgb(look['dirt']), np.float32))
    moss = srgb_to_linear(np.array(hexrgb('#4f6b2c'), np.float32))
    moss_mask = look['moss'] * smoothstep(0.55, 0.85, macro) * np.clip((1 - h01) * 1.3 + (1 - ao), 0, 1)

    amp = look.get('macro_amp', 0.16)
    color = albedo * (1 - amp / 2 + amp * macro[..., None]) * (0.94 + 0.12 * micro[..., None])
    color = color * (1.0 - look['cavity'] * (1.0 - cavity[..., None]))
    color = color * (1 - look['dirt_amt'] * dirt_mask[..., None]) + dirt * (look['dirt_amt'] * dirt_mask[..., None])
    color = color * (1 - moss_mask[..., None]) + moss * moss_mask[..., None]
    # Hand-finished edge wear: raised, worn edges catch light (Warcraft-style readability).
    highlight = look['edge'] * edge * kind * smoothstep(0.35, 0.9, h01)
    color = color + highlight[..., None] * (0.55 + 0.45 * color)

    r_lo, r_hi = look['rough']
    rough = np.where(kind > 0.5, rough_obj, r_hi)
    rough = rough + (1 - ao) * 0.08 + dirt_mask * 0.06 - edge * kind * 0.08 + (micro - 0.5) * 0.06
    rough = np.clip(rough, r_lo, r_hi)
    occlusion = np.clip(0.35 + 0.65 * ao, 0.45, 1.0)

    strength = look['normal']
    detail = pnoise(n, n / 90, seed + 13, octaves=3) * look.get('micro', 0.35)
    gx = (np.roll(detail, -1, 1) - np.roll(detail, 1, 1)) * 0.5 * n / 200
    gy = -(np.roll(detail, -1, 0) - np.roll(detail, 1, 0)) * 0.5 * n / 200
    weight = 0.45 + 0.55 * kind
    nx, ny = (normal[..., 0] - gx * weight) * strength, (normal[..., 1] - gy * weight) * strength
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0.05, 1))
    nmap = np.stack([nx, ny, nz], -1)
    nmap /= np.linalg.norm(nmap, axis=-1, keepdims=True)

    factor = max(1, n // final_px)
    out_albedo = linear_to_srgb(box_down(np.clip(color, 0, 1), factor))
    out_normal = box_down(nmap, factor)
    out_normal /= np.maximum(1e-6, np.linalg.norm(out_normal, axis=-1, keepdims=True))
    out_normal = out_normal * 0.5 + 0.5
    out_orm = box_down(np.stack([occlusion, rough, np.zeros_like(rough)], -1), factor)
    return out_albedo, out_normal, out_orm


def save_png(path: Path, rgb: np.ndarray) -> None:
    h, w = rgb.shape[:2]
    image = bpy.data.images.new(path.stem, w, h, alpha=False, float_buffer=False)
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.ones((h, w, 1), np.float32)], -1)
    # Blender images store row 0 at the bottom.
    image.pixels.foreach_set(np.flipud(rgba).astype(np.float32).ravel())
    image.filepath_raw = str(path)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


def seam_score(img: np.ndarray) -> float:
    left_right = np.abs(img[:, 0] - img[:, -1]).mean()
    top_bottom = np.abs(img[0] - img[-1]).mean()
    inner = (np.abs(img[:, 1:] - img[:, :-1]).mean() + np.abs(img[1:] - img[:-1]).mean()) / 2
    return float(max(left_right, top_bottom) / max(1e-6, inner))


def main() -> None:
    args = parse_args()
    out: Path = args['out']
    out.mkdir(parents=True, exist_ok=True)
    names = [n for n in args['only'].split(',') if n] or list(SPECS)
    records = []
    for name in names:
        spec = SPECS[name]
        started = time.time()
        forge = Forge(name, spec['tile'], args['render'], args['seed'])
        GENERATORS[spec['gen']](forge, spec)
        ao_node = forge.pass_materials['ao'].node_tree.nodes['forge-ao']
        ao_node.inputs['Distance'].default_value = {'cliff_rock': 0.5, 'grass_ground': 0.06}.get(name, 0.06 if spec['gen'] != 'masonry' else 0.08)
        bevel = forge.pass_materials['edge'].node_tree.nodes['forge-bevel']
        bevel.inputs['Radius'].default_value = 0.04 if name == 'cliff_rock' else 0.012
        objects = len([o for o in bpy.data.objects if o.type == 'MESH'])
        passes = forge.render(out)
        albedo, normal, orm = composite(name, spec, passes, args['final'], args['seed'] * 1000 + len(name))
        files = {}
        for kind, data in (('albedo', albedo), ('normal', normal), ('orm', orm)):
            path = out / f'{name}_{kind}.png'
            save_png(path, data)
            files[kind] = {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'seam_score': round(seam_score(data), 3)}
        record = {'name': name, 'tile_m': spec['tile'], 'generator': spec['gen'], 'objects': objects,
                  'render_px': args['render'], 'final_px': args['final'], 'seconds': round(time.time() - started, 1),
                  'device': bpy.context.scene.cycles.device, 'files': files}
        records.append(record)
        print(f"FORGE {name}: {objects} objects, {record['seconds']} s, seams " +
              ', '.join(f"{k}={v['seam_score']}" for k, v in files.items()))
    manifest = out / 'forge-manifest.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {'materials': []}
    merged = {r['name']: r for r in previous.get('materials', [])}
    merged.update({r['name']: r for r in records})
    manifest.write_text(json.dumps({
        'schema': 'xexoria.texture-forge/1', 'generator': 'assets/blender/city_r5/forge/forge_textures_r6.py',
        'blender': bpy.app.version_string, 'license': 'Original procedural work for Xexoria; no third-party pixels.',
        'contract': '<name>_albedo.png sRGB, <name>_normal.png OpenGL +Y, <name>_orm.png AO/roughness/metal',
        'status': 'CANDIDATE — not promoted; review in Blender and native Babylon before replacing textures/',
        'materials': sorted(merged.values(), key=lambda r: r['name']),
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
