"""Xexoria VFX kit v1 (Claude lane, 2026-10-02) — Blender-rendered textures, flipbooks and meshes.

Spec: docs/reviews/2026-10-02-vfx-sample-set-v1.md section 4.

Every texture stores a straight (un-premultiplied) greyscale intensity in RGB and coverage in A, so a single
texture serves every palette through Babylon ramp gradients / colour tints; RGB * A is the additive contribution.
Shapes are built as real geometry (bevelled poly curves and filled meshes), rendered top-down with an orthographic
Cycles camera (emission only, CPU), then given a two-radius glow halo in numpy. Flipbook frames are packed
row-major from the top-left cell. Meshes are exported as GLB (Blender +Z up -> Babylon +Y; Blender -Y -> Babylon +Z).

Run from the repo root (CPU keeps the 2 GB GPU free for the browser):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      --python assets/blender/vfx/build_vfx_kit_v1.py -- [--only name,name] [--samples 24]
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'assets' / 'vfx' / 'kit-v1'
RUNTIME = ROOT / 'apps' / 'client' / 'src' / 'assets' / 'vfx' / 'kit-v1'
TMP = OUT / '_frames'
SEED = 20261002


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = {'only': '', 'samples': 24}
    for i in range(0, len(argv), 2):
        key = argv[i].lstrip('-')
        if key not in args:
            raise SystemExit(f'unknown argument {argv[i]}')
        args[key] = type(args[key])(argv[i + 1])
    args['only'] = {s for s in args['only'].split(',') if s}
    return args


# ----------------------------------------------------------------------------
# Scene, materials, rendering
# ----------------------------------------------------------------------------

def reset_scene(samples: int) -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    scene.render.film_transparent = True
    scene.render.filter_size = 1.5
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'Standard'
    settings = scene.render.image_settings
    settings.file_format = 'OPEN_EXR'
    settings.color_depth = '32'
    settings.color_mode = 'RGBA'
    world = bpy.data.worlds.new('vfx-world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.0
    scene.world = world
    cam = bpy.data.objects.new('vfx-cam', bpy.data.cameras.new('vfx-cam'))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = 2.0
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100.0
    cam.location = (0.0, 0.0, 10.0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene


_materials: dict[str, bpy.types.Material] = {}


def emission(strength: float) -> bpy.types.Material:
    key = f'emit-{strength:.3f}'
    if key in _materials and _materials[key].name in bpy.data.materials:
        return _materials[key]
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (1, 1, 1, 1)
    em.inputs['Strength'].default_value = strength
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    _materials[key] = mat
    return mat


def radial_emission(name: str, stops: list[tuple[float, float]], noise: float = 0.0, noise_scale: float = 6.0) -> bpy.types.Material:
    """Emission whose strength follows a ramp over the object-space radius (0 at the origin)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    coord = nt.nodes.new('ShaderNodeTexCoord')
    length = nt.nodes.new('ShaderNodeVectorMath')
    length.operation = 'LENGTH'
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    elements = ramp.color_ramp.elements
    while len(elements) > 1:
        elements.remove(elements[-1])
    elements[0].position, value = stops[0]
    elements[0].color = (value, value, value, 1)
    for position, value in stops[1:]:
        e = elements.new(position)
        e.color = (value, value, value, 1)
    nt.links.new(coord.outputs['Object'], length.inputs[0])
    source = length.outputs['Value']
    if noise > 0:
        tex = nt.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = noise_scale
        tex.inputs['Detail'].default_value = 4.0
        mix = nt.nodes.new('ShaderNodeMath')
        mix.operation = 'MULTIPLY_ADD'
        nt.links.new(coord.outputs['Object'], tex.inputs['Vector'])
        sub = nt.nodes.new('ShaderNodeMath')
        sub.operation = 'SUBTRACT'
        sub.inputs[1].default_value = 0.5
        nt.links.new(tex.outputs['Fac'], sub.inputs[0])
        nt.links.new(sub.outputs['Value'], mix.inputs[0])
        mix.inputs[1].default_value = noise
        nt.links.new(length.outputs['Value'], mix.inputs[2])
        source = mix.outputs['Value']
    nt.links.new(source, ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], em.inputs['Strength'])
    em.inputs['Color'].default_value = (1, 1, 1, 1)
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return mat


def clear_objects() -> None:
    for obj in list(bpy.data.objects):
        if obj.type != 'CAMERA' and obj.type != 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
    for curve in list(bpy.data.curves):
        if curve.users == 0:
            bpy.data.curves.remove(curve)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def stroke(points, width: float, strength: float = 1.0, radii=None, closed: bool = False, z: float = 0.0):
    """A bevelled poly curve: width is the full stroke width in scene units (canvas spans [-1, 1])."""
    data = bpy.data.curves.new('stroke', 'CURVE')
    data.dimensions = '3D'
    data.bevel_depth = width / 2.0
    data.bevel_resolution = 3
    data.use_fill_caps = True
    spline = data.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for i, (x, y) in enumerate(points):
        spline.points[i].co = (x, y, z, 1.0)
        spline.points[i].radius = 1.0 if radii is None else max(0.0, radii[i])
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new('stroke', data)
    bpy.context.scene.collection.objects.link(obj)
    data.materials.append(emission(strength))
    return obj


def fill(polygon, strength: float = 1.0, z: float = 0.0, material=None):
    mesh = bpy.data.meshes.new('fill')
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z)) for x, y in polygon]
    bm.faces.new(verts)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new('fill', mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material or emission(strength))
    return obj


def circle_points(cx, cy, r, n=128, a0=0.0, a1=2 * math.pi):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def ring(r, width, strength=1.0, n=256):
    return stroke(circle_points(0, 0, r, n)[:-1], width, strength, closed=True)


def render(scene, res: int, name: str, size=(None, None)) -> np.ndarray:
    scene.render.resolution_x = size[0] or res
    scene.render.resolution_y = size[1] or res
    path = TMP / f'{name}.exr'
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path), check_existing=False)
    w, h = image.size
    pixels = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    path.unlink(missing_ok=True)
    return np.flipud(pixels.reshape(h, w, 4)).copy()  # row 0 = top


# ----------------------------------------------------------------------------
# numpy post-processing
# ----------------------------------------------------------------------------

def blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur through the FFT, zero padded (no wrap-around)."""
    if sigma <= 0:
        return img.copy()
    pad = int(math.ceil(sigma * 3))
    h, w = img.shape
    padded = np.zeros((h + 2 * pad, w + 2 * pad), np.float32)
    padded[pad:pad + h, pad:pad + w] = img
    fy = np.fft.fftfreq(padded.shape[0])[:, None]
    fx = np.fft.fftfreq(padded.shape[1])[None, :]
    kernel = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    out = np.real(np.fft.ifft2(np.fft.fft2(padded) * kernel)).astype(np.float32)
    return out[pad:pad + h, pad:pad + w]


def glow(rgba: np.ndarray, near: float, far: float, near_gain: float = 0.55, far_gain: float = 0.28) -> np.ndarray:
    """Core plus two halos. Input/output: premultiplied intensity in R, coverage in A."""
    core = rgba[..., 0]
    alpha = rgba[..., 3]
    scale = rgba.shape[0] / 1024.0
    halo = near_gain * blur(core, near * scale) + far_gain * blur(core, far * scale)
    intensity = np.clip(core + halo, 0, None)
    coverage = np.clip(np.maximum(alpha, 1.6 * halo), 0, 1)
    out = np.zeros_like(rgba)
    out[..., 0] = intensity
    out[..., 3] = coverage
    return out


def to_straight(premult: np.ndarray) -> np.ndarray:
    """Premultiplied intensity (R) + coverage (A) -> straight greyscale RGB + A."""
    alpha = premult[..., 3]
    value = np.where(alpha > 1e-4, premult[..., 0] / np.maximum(alpha, 1e-4), 0.0)
    value = np.clip(value, 0, 1)
    out = np.empty(premult.shape[:2] + (4,), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = value
    out[..., 3] = np.clip(alpha, 0, 1)
    return out


def bleed(rgba: np.ndarray, steps: int = 6) -> np.ndarray:
    """Spread RGB into fully transparent texels so mipmaps do not pull in black."""
    rgb = rgba[..., :3].copy()
    filled = rgba[..., 3] > 0.004
    for _ in range(steps):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(filled.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = np.roll(np.roll(filled, dy, 0), dx, 1)
            acc += np.roll(np.roll(rgb, dy, 0), dx, 1) * shifted[..., None]
            cnt += shifted
        grow = (~filled) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        filled |= grow
    out = rgba.copy()
    out[..., :3] = rgb
    return out


def save_png(path: Path, rgba: np.ndarray) -> None:
    h, w = rgba.shape[:2]
    image = bpy.data.images.new(path.stem, w, h, alpha=True, float_buffer=False)
    image.pixels.foreach_set(np.flipud(np.clip(rgba, 0, 1)).astype(np.float32).ravel())
    image.filepath_raw = str(path)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


def pack(frames: list[np.ndarray], cols: int) -> np.ndarray:
    h, w = frames[0].shape[:2]
    rows = math.ceil(len(frames) / cols)
    atlas = np.zeros((rows * h, cols * w, 4), np.float32)
    for i, frame in enumerate(frames):
        r, c = divmod(i, cols)
        atlas[r * h:(r + 1) * h, c * w:(c + 1) * w] = frame
    return atlas


def tileable_noise(size: int, beta: float, seed: int, aspect=(1, 1)) -> np.ndarray:
    """Periodic fbm-like noise from a random-phase 1/f^beta spectrum (tiles perfectly)."""
    rng = np.random.default_rng(seed)
    h, w = size * aspect[1], size * aspect[0]
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.fftfreq(w)[None, :] * w
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    amplitude = 1.0 / np.power(f, beta)
    amplitude[0, 0] = 0.0
    phase = rng.uniform(0, 2 * math.pi, (h, w))
    field = np.real(np.fft.ifft2(amplitude * np.exp(1j * phase)))
    field = (field - field.min()) / (field.max() - field.min())
    return field.astype(np.float32)


# ----------------------------------------------------------------------------
# Glyph grammar (original Xexoria runes: seeded stroke combinations, not a font)
# ----------------------------------------------------------------------------

def glyph_strokes(rng: random.Random) -> list[list[tuple[float, float]]]:
    strokes = []
    spine = rng.choice(['stem', 'stem2', 'diag', 'arc', 'fork'])
    if spine == 'stem':
        x = rng.choice([-0.18, 0.0, 0.18])
        strokes.append([(x, -0.42), (x, 0.42)])
    elif spine == 'stem2':
        strokes += [[(-0.2, -0.42), (-0.2, 0.42)], [(0.2, -0.42), (0.2, 0.42)]]
    elif spine == 'diag':
        s = rng.choice([-1, 1])
        strokes.append([(-0.28 * s, -0.42), (0.28 * s, 0.42)])
    elif spine == 'arc':
        a0 = rng.choice([0.0, math.pi / 2, math.pi, -math.pi / 2])
        strokes.append(circle_points(0, 0, 0.3, 24, a0, a0 + math.pi * 1.25))
    else:
        strokes += [[(0, -0.42), (0, 0.05)], [(0, 0.05), (-0.25, 0.42)], [(0, 0.05), (0.25, 0.42)]]
    for _ in range(rng.choice([1, 1, 2])):
        mod = rng.choice(['bar', 'chev', 'hook', 'dot', 'ring', 'tick'])
        y = rng.choice([-0.22, 0.0, 0.24])
        if mod == 'bar':
            strokes.append([(-0.3, y), (0.3, y)])
        elif mod == 'chev':
            d = rng.choice([-1, 1]) * 0.16
            strokes.append([(-0.24, y - d), (0, y + d), (0.24, y - d)])
        elif mod == 'hook':
            s = rng.choice([-1, 1])
            strokes.append([(0, 0.42), (0.22 * s, 0.3), (0.22 * s, 0.12)])
        elif mod == 'dot':
            strokes.append(circle_points(rng.choice([-0.22, 0.22]), y, 0.05, 10))
        elif mod == 'ring':
            strokes.append(circle_points(0, y, 0.12, 16))
        else:
            s = rng.choice([-1, 1])
            strokes.append([(0.0, y), (0.26 * s, y + 0.14)])
    return strokes


def place_glyph(strokes, cx, cy, angle, size):
    """Glyph local +y points outward along the radius; local +x follows the tangent."""
    radial = (math.cos(angle), math.sin(angle))
    tangent = (-math.sin(angle), math.cos(angle))
    return [[(cx + (x * tangent[0] + y * radial[0]) * size, cy + (x * tangent[1] + y * radial[1]) * size)
             for x, y in s] for s in strokes]


# ----------------------------------------------------------------------------
# Static textures
# ----------------------------------------------------------------------------

def build_rune_circle_outer(scene, args):
    rng = random.Random(SEED + 1)
    ring(0.955, 0.016, 1.0)
    ring(0.915, 0.006, 0.8)
    ring(0.765, 0.010, 1.0)
    ring(0.705, 0.004, 0.55)
    for k in range(48):
        a = 2 * math.pi * k / 48
        r0 = 0.718 if k % 4 == 0 else 0.735
        stroke([(r0 * math.cos(a), r0 * math.sin(a)), (0.758 * math.cos(a), 0.758 * math.sin(a))], 0.006 if k % 4 else 0.009, 0.9)
    for k in range(24):
        a = 2 * math.pi * k / 24 + math.pi / 24
        for s in place_glyph(glyph_strokes(rng), 0.84 * math.cos(a), 0.84 * math.sin(a), a, 0.088):
            stroke(s, 0.0085, 1.0)
        b = a + math.pi / 24
        cx, cy, d = 0.84 * math.cos(b), 0.84 * math.sin(b), 0.014
        t, n = (-math.sin(b), math.cos(b)), (math.cos(b), math.sin(b))
        fill([(cx + n[0] * d * 1.6, cy + n[1] * d * 1.6), (cx + t[0] * d, cy + t[1] * d),
              (cx - n[0] * d * 1.6, cy - n[1] * d * 1.6), (cx - t[0] * d, cy - t[1] * d)], 0.9)
    return glow(render(scene, 2048, 'rune_outer'), 3, 14)


def build_rune_circle_inner(scene, args):
    rng = random.Random(SEED + 2)
    ring(0.93, 0.012, 1.0)
    ring(0.885, 0.005, 0.6)
    ring(0.30, 0.008, 0.9)
    ring(0.12, 0.006, 0.7)
    star = [(0.885 * math.cos(math.pi / 2 + 2 * math.pi * (3 * i % 7) / 7), 0.885 * math.sin(math.pi / 2 + 2 * math.pi * (3 * i % 7) / 7)) for i in range(7)]
    stroke(star, 0.010, 1.0, closed=True)
    hept = [(0.885 * math.cos(math.pi / 2 + 2 * math.pi * i / 7), 0.885 * math.sin(math.pi / 2 + 2 * math.pi * i / 7)) for i in range(7)]
    stroke(hept, 0.005, 0.55, closed=True)
    for i in range(7):
        a = math.pi / 2 + 2 * math.pi * i / 7
        cx, cy = 0.885 * math.cos(a), 0.885 * math.sin(a)
        fill(circle_points(cx, cy, 0.062, 32)[:-1], 0.0, material=emission(0.0001))
        stroke(circle_points(cx, cy, 0.062, 48)[:-1], 0.008, 1.0, closed=True)
        for s in place_glyph(glyph_strokes(rng), cx, cy, a, 0.075):
            stroke(s, 0.007, 1.0)
        b = a + math.pi / 7
        for s in place_glyph(glyph_strokes(rng), 0.52 * math.cos(b), 0.52 * math.sin(b), b, 0.07):
            stroke(s, 0.006, 0.75)
    return glow(render(scene, 1024, 'rune_inner'), 3, 14)


def build_rune_ring_blade(scene, args):
    ring(0.93, 0.014, 1.0)
    ring(0.875, 0.005, 0.55)
    for k in range(12):
        a = 2 * math.pi * k / 12
        r, s = 0.905, 0.075
        t, n = (-math.sin(a), math.cos(a)), (math.cos(a), math.sin(a))
        def p(x, y):
            return (r * n[0] + (x * t[0] + y * n[0]) * s, r * n[1] + (x * t[1] + y * n[1]) * s)
        fill([p(0, 1.15), p(0.22, 0.45), p(0.18, -0.35), p(-0.18, -0.35), p(-0.22, 0.45)], 1.0)
        fill([p(-0.5, -0.38), p(0.5, -0.38), p(0.42, -0.55), p(-0.42, -0.55)], 1.0)
        stroke([p(0, -0.55), p(0, -0.95)], 0.012, 0.9)
    for k in range(12):
        a = 2 * math.pi * (k + 0.5) / 12
        stroke(circle_points(0, 0, 0.905, 12, a - 0.11, a + 0.11), 0.004, 0.6)
    return glow(render(scene, 1024, 'rune_blade'), 3, 12)


def build_swirl_arms(scene, args):
    rng = random.Random(SEED + 3)
    for arm in range(6):
        a0 = 2 * math.pi * arm / 6
        pts, radii = [], []
        n = 90
        for i in range(n + 1):
            u = i / n
            r = 0.07 + 0.92 * u
            pts.append((r * math.cos(a0 + 2.1 * math.log(1 + 3.2 * u)), r * math.sin(a0 + 2.1 * math.log(1 + 3.2 * u))))
            radii.append(math.sin(math.pi * min(1.0, u * 1.15)) ** 0.8 * (1.0 - 0.35 * u))
        stroke(pts, 0.085, 1.0, radii)
        pts2 = [(x * 0.97 + rng.uniform(-0.004, 0.004), y * 0.97) for x, y in pts]
        stroke(pts2, 0.026, 0.85, [r ** 0.5 for r in radii])
    for arm in range(12):
        a0 = 2 * math.pi * arm / 12 + 0.26
        pts = [((0.2 + 0.75 * i / 60) * math.cos(a0 + 2.1 * math.log(1 + 3.2 * i / 60)),
                (0.2 + 0.75 * i / 60) * math.sin(a0 + 2.1 * math.log(1 + 3.2 * i / 60))) for i in range(61)]
        stroke(pts, 0.012, 0.45, [math.sin(math.pi * i / 60) for i in range(61)])
    return glow(render(scene, 1024, 'swirl'), 4, 18, 0.6, 0.35)


def build_shock_ring(scene, args):
    mat = radial_emission('shock', [(0.0, 0.0), (0.62, 0.0), (0.84, 0.10), (0.905, 0.65), (0.93, 1.0), (0.945, 0.0)], noise=0.05, noise_scale=9)
    fill(circle_points(0, 0, 0.97, 256)[:-1], material=mat)
    return glow(render(scene, 512, 'shock'), 2, 8, 0.4, 0.2)


def build_impact_star(scene, args):
    rng = random.Random(SEED + 4)
    mat = radial_emission('star', [(0.0, 1.0), (0.12, 1.0), (0.45, 0.55), (0.95, 0.0)])
    rays = 11
    for i in range(rays):
        a = 2 * math.pi * i / rays + rng.uniform(-0.12, 0.12)
        length = rng.uniform(0.55, 0.97) if i % 2 else rng.uniform(0.35, 0.6)
        width = rng.uniform(0.045, 0.075)
        t = (-math.sin(a), math.cos(a))
        fill([(t[0] * width, t[1] * width), (length * math.cos(a), length * math.sin(a)), (-t[0] * width, -t[1] * width)], material=mat)
    fill(circle_points(0, 0, 0.16, 48)[:-1], material=radial_emission('star-core', [(0.0, 1.0), (0.1, 1.0), (0.16, 0.6)]))
    return glow(render(scene, 512, 'star'), 3, 12, 0.6, 0.35)


def crack_paths(rng: random.Random, branches=9):
    paths = []
    def walk(x, y, a, length, width, depth):
        pts, radii = [(x, y)], [width]
        steps = int(length / 0.03)
        for i in range(steps):
            a += rng.uniform(-0.45, 0.45)
            x, y = x + 0.03 * math.cos(a), y + 0.03 * math.sin(a)
            pts.append((x, y))
            radii.append(width * (1 - (i + 1) / (steps + 1)) ** 0.7)
            if depth < 2 and rng.random() < 0.09:
                walk(x, y, a + rng.choice([-1, 1]) * rng.uniform(0.5, 1.0), length * 0.45, radii[-1] * 0.8, depth + 1)
        paths.append((pts, radii))
    for i in range(branches):
        a = 2 * math.pi * i / branches + rng.uniform(-0.25, 0.25)
        walk(0.05 * math.cos(a), 0.05 * math.sin(a), a, rng.uniform(0.55, 0.9), rng.uniform(0.8, 1.0), 0)
    return paths


def build_ground_cracks(scene, args):
    rng = random.Random(SEED + 5)
    for pts, radii in crack_paths(rng):
        stroke(pts, 0.022, 1.0, radii)
    seams = render(scene, 1024, 'cracks')
    core = seams[..., 0]
    scorch = np.clip(blur(core, 14) * 3.0 + blur(core, 40) * 2.0, 0, 1)
    yy, xx = np.mgrid[0:1024, 0:1024]
    radial = np.clip(1 - np.hypot(xx - 511.5, yy - 511.5) / 512, 0, 1) ** 0.6
    scorch *= radial
    glowing = glow(seams, 2, 8, 0.7, 0.3)
    out = np.zeros((1024, 1024, 4), np.float32)
    alpha = np.clip(np.maximum(glowing[..., 3], scorch), 0, 1)
    out[..., 0] = np.where(alpha > 1e-4, np.clip(glowing[..., 0], 0, 1) / np.maximum(alpha, 1e-4), 0)  # seam glow
    out[..., 1] = np.where(alpha > 1e-4, scorch / np.maximum(alpha, 1e-4), 0)  # scorch darkening
    out[..., 2] = out[..., 0]
    out[..., 3] = alpha
    return out, True


def build_scorch(scene, args):
    rng = np.random.default_rng(SEED + 6)
    size = 1024
    yy, xx = np.mgrid[0:size, 0:size] / (size - 1) * 2 - 1
    r = np.hypot(xx, yy)
    angle = np.arctan2(yy, xx)
    noise = tileable_noise(size, 1.6, SEED + 6)
    edge = 0.62 + 0.18 * np.sin(angle * 5 + 1.3) * 0.5 + (noise - 0.5) * 0.35
    burn = np.clip((edge - r) / 0.22, 0, 1) ** 1.2
    embers = (rng.random((size, size)) > 0.9965).astype(np.float32)
    embers = np.clip(blur(embers, 1.6) * 22, 0, 1) * np.clip((0.55 - r) / 0.4, 0, 1)
    cracks = np.clip(1 - np.abs(noise - 0.5) * 18, 0, 1) * burn * 0.8
    out = np.zeros((size, size, 4), np.float32)
    ember = np.clip(embers + cracks, 0, 1)
    out[..., 0] = out[..., 1] = out[..., 2] = ember
    out[..., 3] = np.clip(burn * (0.75 + 0.25 * noise), 0, 1)
    return out, True


def build_streak(scene, args):
    rng = np.random.default_rng(SEED + 7)
    w, h = 256, 1024
    v = np.arange(h) / h
    img = np.zeros((h, w), np.float32)
    x = np.arange(w)
    for _ in range(46):
        cx = rng.uniform(0, w)
        width = rng.uniform(0.8, 5.5)
        dx = np.minimum(np.abs(x - cx), w - np.abs(x - cx))
        column = np.exp(-(dx / width) ** 2)
        k = rng.integers(1, 4)
        phase = rng.uniform(0, 2 * math.pi)
        profile = np.clip(np.sin(2 * math.pi * k * v + phase) * 0.8 + rng.uniform(-0.2, 0.5), 0, 1) ** 1.5
        img += rng.uniform(0.35, 1.0) * profile[:, None] * column[None, :]
    img = np.clip(img / np.percentile(img, 99.5), 0, 1)
    out = np.zeros((h, w, 4), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = np.clip(img * 1.2, 0, 1)
    out[..., 3] = img
    return out, True


def capsule_polygon(cx, cy, length, radius, angle, n=14):
    """Filled capsule from (cx, cy) along angle (0 = +Y), round far end and round base."""
    ux, uy = math.sin(angle), math.cos(angle)
    tx, ty = uy, -ux
    top = (cx + ux * length, cy + uy * length)
    a_side = math.atan2(ty, tx)
    pts = circle_points(top[0], top[1], radius, n, a_side, a_side + math.pi)
    pts += circle_points(cx, cy, radius, n, a_side + math.pi, a_side + 2 * math.pi)
    return pts[:-1]


def build_palm_sigil(scene, args):
    """Original Xexoria gale-palm sigil: one clean silhouette outline (union of palm, fingers, thumb),
    a tip-bright gradient fill, two palm lines, wind curls and a glyph ring."""
    rng = random.Random(SEED + 8)
    s = 0.92
    palm = [(-0.29, -0.40), (0.27, -0.42), (0.34, -0.08), (0.33, 0.13), (-0.31, 0.13), (-0.35, -0.06)]
    fingers = ((-0.225, 0.10, 0.34, 0.068, -0.12), (-0.075, 0.12, 0.44, 0.07, -0.035),
               (0.08, 0.12, 0.46, 0.07, 0.03), (0.235, 0.10, 0.36, 0.066, 0.11))
    fill([(x * s, y * s) for x, y in palm], 1.0)
    for cx, cy, length, radius, angle in fingers:
        fill([(x * s, y * s) for x, y in capsule_polygon(cx, cy, length, radius, angle)], 1.0)
    fill([(x * s, y * s) for x, y in capsule_polygon(-0.30, -0.16, 0.30, 0.075, -1.05)], 1.0)
    mask = render(scene, 1024, 'palm_mask')[..., 3]
    clear_objects()
    eroded = (blur(mask, 7) > 0.985).astype(np.float32)
    outline = np.clip(mask * (1 - blur(eroded, 1.2)), 0, 1)
    inner = np.clip(blur(eroded, 1.0), 0, 1)
    yy, xx = np.mgrid[0:1024, 0:1024] / 1023.0 * 2 - 1
    yy = -yy  # image rows grow downward; canvas +y is up
    gradient = 0.30 + 0.28 * np.clip((yy + 0.35) / 0.9, 0, 1) + 0.18 * np.exp(-(xx ** 2 + (yy + 0.12) ** 2) / 0.03)
    for a, b, c in (((-0.22, -0.02), (0.0, -0.10), (0.24, -0.04)), ((-0.18, -0.24), (0.02, -0.20), (0.20, -0.28))):
        pts = [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * b[0] + t * t * c[0],
                (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * b[1] + t * t * c[1]) for t in [i / 20 for i in range(21)]]
        stroke([(x * s, y * s) for x, y in pts], 0.016, 1.0, [math.sin(math.pi * i / 20) ** 0.6 for i in range(21)])
    lines = render(scene, 1024, 'palm_lines')
    clear_objects()
    for a in (0.6, 2.7, 4.8):
        pts = [((0.73 + 0.12 * i / 30) * math.cos(a + 0.9 * i / 30), (0.73 + 0.12 * i / 30) * math.sin(a + 0.9 * i / 30)) for i in range(31)]
        pts += circle_points(0.85 * math.cos(a + 0.9), 0.85 * math.sin(a + 0.9), 0.06, 16, a + 0.9, a + 0.9 + math.pi * 1.4)
        stroke(pts, 0.02, 0.9, [math.sin(math.pi * min(1, (i + 2) / len(pts))) ** 0.4 for i in range(len(pts))])
    ring(0.95, 0.018, 1.0)
    ring(0.905, 0.006, 0.6)
    for k in range(16):
        a = 2 * math.pi * k / 16
        if k % 4 == 1:
            for st in place_glyph(glyph_strokes(rng), 0.925 * math.cos(a), 0.925 * math.sin(a), a, 0.05):
                stroke(st, 0.006, 0.9)
    frame = render(scene, 1024, 'palm_ring')
    intensity = np.maximum.reduce([outline * 1.0, inner * gradient, lines[..., 0] * 0.85 * inner, frame[..., 0]])
    coverage = np.maximum.reduce([outline, inner * 0.82, frame[..., 3]])
    combined = np.zeros((1024, 1024, 4), np.float32)
    combined[..., 0] = np.minimum(intensity, 1.0) * coverage  # premultiplied for glow()
    combined[..., 3] = coverage
    return glow(combined, 3, 14, 0.6, 0.3)


def build_noise_erosion(scene, args):
    noise = tileable_noise(512, 1.35, SEED + 9)
    noise = np.clip((noise - 0.08) / 0.84, 0, 1)
    out = np.zeros((512, 512, 4), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = noise
    out[..., 3] = 1.0
    return out, True


def build_soft_disc(scene, args):
    size = 256
    yy, xx = np.mgrid[0:size, 0:size] / (size - 1) * 2 - 1
    r = np.hypot(xx, yy)
    v = np.clip(1 - r, 0, 1) ** 2.2
    out = np.zeros((size, size, 4), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = 1.0
    out[..., 3] = v
    return out, True


# ----------------------------------------------------------------------------
# Flipbooks
# ----------------------------------------------------------------------------

def build_fb_lightning(scene, args):
    rng = random.Random(SEED + 10)
    frames = []
    def bolt(a, b, rough, depth, out):
        if depth == 0:
            out.append(b)
            return
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        offset = rng.uniform(-rough, rough) * length
        m = (mx - dy / length * offset, my + dx / length * offset)
        bolt(a, m, rough, depth - 1, out)
        bolt(m, b, rough, depth - 1, out)
    for f in range(16):
        clear_objects()
        main = [(-0.96, rng.uniform(-0.1, 0.1))]
        bolt(main[0], (0.96, rng.uniform(-0.1, 0.1)), 0.32, 7, main)
        n = len(main)
        stroke(main, 0.022, 1.0, [0.55 + 0.45 * math.sin(math.pi * i / (n - 1)) for i in range(n)])
        for _ in range(rng.randint(2, 4)):
            i0 = rng.randint(n // 6, n * 5 // 6)
            start = main[i0]
            end = (start[0] + rng.uniform(0.15, 0.4), start[1] + rng.choice([-1, 1]) * rng.uniform(0.15, 0.45))
            branch = [start]
            bolt(start, end, 0.35, 5, branch)
            m = len(branch)
            stroke(branch, 0.013, 0.8, [1 - i / m for i in range(m)])
        frames.append(to_straight(glow(render(scene, 256, f'lightning_{f}'), 2.5, 10, 0.7, 0.4)))
    return pack(frames, 4), True


def build_fb_impact(scene, args):
    rng = random.Random(SEED + 11)
    rays = [(2 * math.pi * i / 14 + rng.uniform(-0.12, 0.12), rng.uniform(0.6, 1.0), rng.uniform(0.7, 1.2)) for i in range(14)]
    frames = []
    for f in range(16):
        clear_objects()
        t = f / 15
        grow = 1 - (1 - min(1, t / 0.45)) ** 3
        thin = max(0.0, 1 - t) ** 0.8
        fade = 1.0 if t < 0.55 else max(0.0, 1 - (t - 0.55) / 0.45)
        mat = radial_emission(f'impact-{f}', [(0.0, 1.0 * fade), (0.2, 0.9 * fade), (0.9, 0.0)])
        for a, length, width in rays:
            inner = 0.08 + 0.45 * grow * length
            outer = 0.15 + 0.82 * grow * length
            w = 0.05 * width * thin + 0.004
            t2 = (-math.sin(a), math.cos(a))
            fill([(inner * math.cos(a) + t2[0] * w, inner * math.sin(a) + t2[1] * w), (outer * math.cos(a), outer * math.sin(a)),
                  (inner * math.cos(a) - t2[0] * w, inner * math.sin(a) - t2[1] * w), ((inner - 0.08) * math.cos(a), (inner - 0.08) * math.sin(a))], material=mat)
        core = max(0.0, 1 - t / 0.26) ** 1.5
        if core > 0.02:
            radius = 0.07 + 0.2 * (1 - core)
            fill(circle_points(0, 0, radius, 48)[:-1], material=radial_emission(f'impact-core-{f}', [(0.0, core), (radius * 0.45, core * 0.75), (radius, 0.0)]))
        if 0.1 < t < 0.8:
            ring(0.25 + 0.7 * grow, 0.02 * thin + 0.004, 0.6 * fade)
        frames.append(to_straight(glow(render(scene, 256, f'impact_{f}'), 2.5, 9, 0.6, 0.35)))
    return pack(frames, 4), True


def build_fb_swirl(scene, args):
    frames = []
    for f in range(16):
        clear_objects()
        spin = 2 * math.pi / 3 * f / 16
        for arm in range(3):
            a0 = 2 * math.pi * arm / 3 + spin
            pts = [((0.12 + 0.82 * i / 70) * math.cos(a0 + 2.6 * i / 70), (0.12 + 0.82 * i / 70) * math.sin(a0 + 2.6 * i / 70)) for i in range(71)]
            stroke(pts, 0.07, 1.0, [math.sin(math.pi * i / 70) ** 0.7 * (1 - 0.4 * i / 70) for i in range(71)])
            pts2 = [((0.3 + 0.62 * i / 50) * math.cos(a0 + 1.0 + 2.2 * i / 50), (0.3 + 0.62 * i / 50) * math.sin(a0 + 1.0 + 2.2 * i / 50)) for i in range(51)]
            stroke(pts2, 0.022, 0.6, [math.sin(math.pi * i / 50) for i in range(51)])
        frames.append(to_straight(glow(render(scene, 256, f'swirl_{f}'), 3, 10, 0.6, 0.3)))
    return pack(frames, 4), True


def build_shards(scene, args):
    rng = random.Random(SEED + 12)
    frames = []
    for f in range(16):
        clear_objects()
        n = rng.randint(5, 7)
        length, width = rng.uniform(0.7, 0.94), rng.uniform(0.2, 0.36)
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n + rng.uniform(-0.2, 0.2)
            stretch = length if abs(math.sin(a)) > 0.75 else width * rng.uniform(1.0, 1.6)
            pts.append((width * math.cos(a) * rng.uniform(0.8, 1.15), stretch * math.sin(a)))
        rot = rng.uniform(-0.7, 0.7)
        pts = [(x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)) for x, y in pts]
        centre = (rng.uniform(-0.06, 0.06), rng.uniform(-0.1, 0.1))
        for i in range(n):
            shade = 0.3 + 0.65 * (0.5 + 0.5 * math.cos(math.atan2(pts[i][1], pts[i][0]) - 2.2))
            fill([centre, pts[i], pts[(i + 1) % n]], round(shade, 2))
        stroke(pts, 0.014, 0.95, closed=True)
        top = max(range(n), key=lambda i: pts[i][1] - pts[i][0] * 0.4)
        stroke([centre, pts[top]], 0.012, 1.0)
        frames.append(to_straight(glow(render(scene, 128, f'shard_{f}'), 1.5, 5, 0.4, 0.2)))
    return pack(frames, 4), True


def build_fb_dust(scene, args):
    """Cycles volumetric puff: animated 4D noise density, expanding and thinning over 64 frames."""
    clear_objects()
    scene.cycles.max_bounces = 2
    scene.cycles.volume_bounces = 1
    scene.cycles.samples = max(32, args['samples'])
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(35), math.radians(-25), math.radians(20))
    scene.collection.objects.link(sun)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.45
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0)
    puff = bpy.context.active_object
    mat = bpy.data.materials.new('dust')
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    vol = nt.nodes.new('ShaderNodeVolumePrincipled')
    vol.inputs['Color'].default_value = (1, 1, 1, 1)
    coord = nt.nodes.new('ShaderNodeTexCoord')
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.noise_dimensions = '4D'
    noise.inputs['Scale'].default_value = 1.55
    noise.inputs['Detail'].default_value = 8.0
    noise.inputs['Roughness'].default_value = 0.62
    length = nt.nodes.new('ShaderNodeVectorMath')
    length.operation = 'LENGTH'
    falloff = nt.nodes.new('ShaderNodeMapRange')
    falloff.inputs['From Min'].default_value = 1.0
    falloff.inputs['From Max'].default_value = 0.45
    shape = nt.nodes.new('ShaderNodeMath')
    shape.operation = 'MULTIPLY'
    sharpen = nt.nodes.new('ShaderNodeMapRange')
    sharpen.inputs['From Min'].default_value = 0.30
    sharpen.inputs['From Max'].default_value = 0.62
    density = nt.nodes.new('ShaderNodeMath')
    density.operation = 'MULTIPLY'
    nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
    nt.links.new(coord.outputs['Object'], length.inputs[0])
    nt.links.new(length.outputs['Value'], falloff.inputs['Value'])
    nt.links.new(noise.outputs['Fac'], sharpen.inputs['Value'])
    nt.links.new(sharpen.outputs['Result'], shape.inputs[0])
    nt.links.new(falloff.outputs['Result'], shape.inputs[1])
    nt.links.new(shape.outputs['Value'], density.inputs[0])
    nt.links.new(density.outputs['Value'], vol.inputs['Density'])
    nt.links.new(vol.outputs['Volume'], out.inputs['Volume'])
    puff.data.materials.append(mat)
    scene.camera.location = (0, 0, 10)
    scene.camera.data.ortho_scale = 2.1
    raw = []
    for f in range(64):
        t = f / 63
        scale = 0.72 + 0.28 * (1 - (1 - t) ** 2.2)
        puff.scale = (scale, scale, scale)
        noise.inputs['W'].default_value = 0.6 + t * 1.6
        # Thin by erosion: raise the noise threshold so the puff breaks into wisps, then lower density.
        sharpen.inputs['From Min'].default_value = 0.30 + 0.30 * max(0.0, t - 0.3) / 0.7
        sharpen.inputs['From Max'].default_value = 0.62 + 0.25 * max(0.0, t - 0.3) / 0.7
        density.inputs[1].default_value = 12.0 * (1.0 if t < 0.45 else max(0.0, 1 - (t - 0.45) / 0.55) ** 1.2) + 0.05
        rgba = render(scene, 128, f'dust_{f}')
        alpha = rgba[..., 3]
        lum = rgba[..., :3].mean(axis=2)
        raw.append((np.where(alpha > 1e-4, lum / np.maximum(alpha, 1e-4), 0), np.clip(alpha, 0, 1)))
    solid = np.concatenate([v[a > 0.5] for v, a in raw if (a > 0.5).any()])
    norm = float(np.percentile(solid, 99.0)) if solid.size else 1.0
    frames = []
    for value, alpha in raw:
        straight = np.zeros((128, 128, 4), np.float32)
        straight[..., 0] = straight[..., 1] = straight[..., 2] = np.clip(value / norm, 0, 1)
        straight[..., 3] = alpha
        frames.append(straight)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.0
    bpy.data.objects.remove(sun, do_unlink=True)
    scene.cycles.max_bounces = 0
    scene.camera.data.ortho_scale = 2.0
    return pack(frames, 8), True


# ----------------------------------------------------------------------------
# Meshes
# ----------------------------------------------------------------------------

def export_glb(objects, path: Path) -> None:
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    kwargs = dict(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
                  export_texcoords=True, export_normals=True, export_materials='PLACEHOLDER')
    try:
        bpy.ops.export_scene.gltf(**kwargs, export_vertex_color='ACTIVE')
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)


def mesh_object(name, verts, faces, uvs=None, colors=None, smooth=False):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if uvs is not None:
        layer = mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                layer.data[li].uv = uvs[mesh.loops[li].vertex_index]
    if colors is not None:
        attr = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
        for i, c in enumerate(colors):
            attr.data[i].color = (c, c, c, 1.0)
        mesh.color_attributes.active_color = attr
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mat = bpy.data.materials.new(name + '-mat')
    mesh.materials.append(mat)
    return obj


def build_spectral_blade(scene, args):
    clear_objects()
    verts, faces, uvs, cols = [], [], [], []
    total = 2.07
    def add(v, uv, c):
        verts.append(v)
        uvs.append(uv)
        cols.append(c)
        return len(verts) - 1
    stations = [(0.0, 0.27, 0.055), (0.35, 0.305, 0.056), (0.75, 0.295, 0.05), (1.12, 0.235, 0.042), (1.42, 0.13, 0.03)]
    rings = []
    for z, w, t in stations:
        v = (z + 0.47) / total
        rings.append([add((-w / 2, 0, z), (0.0, v), 1.0), add((0, t / 2, z), (0.5, v), 0.25),
                      add((w / 2, 0, z), (1.0, v), 1.0), add((0, -t / 2, z), (0.5, v), 0.25)])
    tip = add((0, 0, 1.6), (0.5, 1.0), 1.0)
    for a, b in zip(rings, rings[1:]):
        for k in range(4):
            faces.append((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    for k in range(4):
        faces.append((rings[-1][k], rings[-1][(k + 1) % 4], tip))
    faces.append(tuple(reversed(rings[0])))
    # Crossguard: chunky bar with raised, angled ends.
    gw, gh, gd = 0.38, 0.095, 0.07
    guard = [(-gw, -gd, -gh), (gw, -gd, -gh), (gw, gd, -gh), (-gw, gd, -gh),
             (-gw - 0.04, -gd, 0.02), (gw + 0.04, -gd, 0.02), (gw + 0.04, gd, 0.02), (-gw - 0.04, gd, 0.02)]
    g = [add(p, (0.5 + p[0] / (2 * gw + 0.1), (p[2] + 0.47) / total), 0.8) for p in guard]
    for quad in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
        faces.append(tuple(g[i] for i in quad))
    # Grip: octagonal prism and a diamond pommel.
    grip_top, grip_bottom = [], []
    for k in range(8):
        a = 2 * math.pi * k / 8
        x, y = 0.042 * math.cos(a), 0.042 * math.sin(a)
        grip_top.append(add((x, y, -gh), (k / 8, (0.47 - gh) / total), 0.1))
        grip_bottom.append(add((x, y, -0.41), (k / 8, 0.06 / total), 0.1))
    for k in range(8):
        faces.append((grip_bottom[k], grip_bottom[(k + 1) % 8], grip_top[(k + 1) % 8], grip_top[k]))
    pom_top = add((0, 0, -0.39), (0.5, 0.08 / total), 0.6)
    pom_bottom = add((0, 0, -0.47), (0.5, 0.0), 0.6)
    pom_mid = [add((0.06 * math.cos(2 * math.pi * k / 6), 0.06 * math.sin(2 * math.pi * k / 6), -0.43), (k / 6, 0.04 / total), 0.6) for k in range(6)]
    for k in range(6):
        faces.append((pom_mid[k], pom_mid[(k + 1) % 6], pom_top))
        faces.append((pom_mid[(k + 1) % 6], pom_mid[k], pom_bottom))
    obj = mesh_object('vfx_spectral_blade', verts, faces, uvs, cols)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    path = OUT / 'vfx_spectral_blade.glb'
    export_glb([obj], path)
    return path, tris


def lathe(name, profile, segments, spiral=0.0, u_repeat=1.0):
    """profile: [(radius, z, v)] top to bottom; UV u wraps around (with a seam column), v follows the profile."""
    verts, faces, uvs = [], [], []
    for r, z, v in profile:
        for j in range(segments + 1):
            a = 2 * math.pi * j / segments
            verts.append((r * math.cos(a), r * math.sin(a), z))
            uvs.append((u_repeat * j / segments + spiral * v, v))
    cols = segments + 1
    for i in range(len(profile) - 1):
        for j in range(segments):
            a, b = i * cols + j, i * cols + j + 1
            faces.append((a, b, b + cols, a + cols))
    return mesh_object(name, verts, faces, uvs, smooth=True)


def build_funnel(scene, args):
    clear_objects()
    profile = [((1.0 - v) ** 1.7 * 0.94 + 0.06, -v * 1.0, v) for v in [i / 12 for i in range(13)]]
    obj = lathe('vfx_funnel', profile, 48, spiral=0.6, u_repeat=2.0)
    path = OUT / 'vfx_funnel.glb'
    export_glb([obj], path)
    return path, sum(len(p.vertices) - 2 for p in obj.data.polygons)


def build_cone_burst(scene, args):
    clear_objects()
    profile = [(0.04 + 0.56 * v, 0.0, v) for v in [i / 4 for i in range(5)]]
    obj = lathe('vfx_cone_burst', [(r, 0.0, v) for r, _, v in profile], 32, u_repeat=2.0)
    for vert, (r, _, v) in zip(obj.data.vertices, [p for p in profile for _ in range(33)]):
        vert.co.z = 0.0
    # Re-lay the cone along Blender -Y (Babylon +Z): radius in XZ, length along -Y.
    for idx, vert in enumerate(obj.data.vertices):
        ring_i, j = divmod(idx, 33)
        v = ring_i / 4
        a = 2 * math.pi * j / 32
        r = 0.04 + 0.56 * v
        vert.co = (r * math.cos(a), -v * 1.0, r * math.sin(a))
    path = OUT / 'vfx_cone_burst.glb'
    export_glb([obj], path)
    return path, sum(len(p.vertices) - 2 for p in obj.data.polygons)


def build_ring_wall(scene, args):
    clear_objects()
    profile = [(1.0, 1.0 - v, v) for v in (0.0, 0.25, 0.5, 0.75, 1.0)]
    obj = lathe('vfx_ring_wall', profile, 64, u_repeat=4.0)
    path = OUT / 'vfx_ring_wall.glb'
    export_glb([obj], path)
    return path, sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ----------------------------------------------------------------------------

TEXTURES = {
    'vfx_rune_circle_outer': (build_rune_circle_outer, None),
    'vfx_rune_circle_inner': (build_rune_circle_inner, None),
    'vfx_rune_ring_blade': (build_rune_ring_blade, None),
    'vfx_swirl_arms': (build_swirl_arms, None),
    'vfx_shock_ring': (build_shock_ring, None),
    'vfx_impact_star': (build_impact_star, None),
    'vfx_ground_cracks': (build_ground_cracks, None),
    'vfx_scorch': (build_scorch, None),
    'vfx_streak': (build_streak, None),
    'vfx_palm_sigil': (build_palm_sigil, None),
    'vfx_noise_erosion': (build_noise_erosion, None),
    'vfx_soft_disc': (build_soft_disc, None),
    'vfx_fb_lightning': (build_fb_lightning, (4, 4, 256)),
    'vfx_fb_impact': (build_fb_impact, (4, 4, 256)),
    'vfx_fb_swirl': (build_fb_swirl, (4, 4, 256)),
    'vfx_shards': (build_shards, (4, 4, 128)),
    'vfx_fb_dust': (build_fb_dust, (8, 8, 128)),
}
MESHES = {
    'vfx_spectral_blade': build_spectral_blade,
    'vfx_funnel': build_funnel,
    'vfx_cone_burst': build_cone_burst,
    'vfx_ring_wall': build_ring_wall,
}


def main() -> None:
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    receipt_path = OUT / 'kit-receipt.json'
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {'assets': {}}
    receipt.update({'schema': 'xexoria.vfx-kit/1', 'generator': 'assets/blender/vfx/build_vfx_kit_v1.py',
                    'blender': bpy.app.version_string, 'seed': SEED,
                    'encoding': 'RGB = straight greyscale intensity, A = coverage; additive contribution = RGB*A. '
                                'ground_cracks: R seam glow, G scorch. Flipbooks row-major from the top-left cell.'})
    scene = reset_scene(args['samples'])
    for name, (builder, grid) in TEXTURES.items():
        if args['only'] and name not in args['only']:
            continue
        started = time.time()
        clear_objects()
        result = builder(scene, args)
        image, straight = (result if isinstance(result, tuple) else (result, False))
        if not straight:
            image = to_straight(image)
        image = bleed(image)
        path = OUT / f'{name}.png'
        save_png(path, image)
        shutil.copy2(path, RUNTIME / path.name)
        entry = {'file': path.name, 'width': image.shape[1], 'height': image.shape[0],
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'seconds': round(time.time() - started, 1)}
        if grid:
            entry['grid'] = {'cols': grid[0], 'rows': grid[1] if name != 'vfx_fb_dust' else 8, 'cell_px': grid[2],
                             'frames': grid[0] * (grid[1] if name != 'vfx_fb_dust' else 8)}
        receipt['assets'][name] = entry
        print(f'VFX {name}: {entry["width"]}x{entry["height"]} in {entry["seconds"]}s')
    for name, builder in MESHES.items():
        if args['only'] and name not in args['only']:
            continue
        path, tris = builder(scene, args)
        shutil.copy2(path, RUNTIME / path.name)
        receipt['assets'][name] = {'file': path.name, 'triangles': tris, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        print(f'VFX {name}: {tris} triangles')
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    shutil.rmtree(TMP, ignore_errors=True)
    print('RECEIPT', receipt_path)


if __name__ == '__main__':
    main()
