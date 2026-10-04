"""Forge R7: Sunmeadow v2 terrain layers from real geometry (terrain spec §3.3, §6 script 1).

Builds wrap-around geometry for each layer (grass clumps and blades, clover, straw tufts, dead leaves,
packed soil with footprints, three pebble sizes, clods, roots, seeds, mud with puddle hollows, moss
cushions, wet stones, twigs, layered rock, moss mats) inside one square tile, renders top-down
orthographic Cycles data passes on the CPU (R6 pass materials: albedo, normal, height, AO, edge, id) and
saves them as .npy. The numpy composite (assets/blender/sunmeadow_v2/terrain/terrain_forge_composite.py)
then paints and grades the shipped maps; it can re-run without Blender while tuning.

Differences from R6 (forge_textures_r6.py):
- Cycles device is CPU by default and CUDA is never queried (llm.txt: CPU while a browser/game runs);
  pass --device gpu to opt in.
- Planes carry no object-space speckle (that noise is not periodic and seams at the tile border);
  periodic speckle is added in the composite.
- The final normal is derived from the rendered height (metre-calibrated), so normal and height agree.

Run from the repo root (one Blender process at a time; >= 1.5 GB free RAM):
  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup \\
      --python assets/blender/city_r5/forge/forge_terrain_r7.py -- [--only L0,L2] [--seed 7] \\
      [--passes <dir>] [--device cpu] [--no-composite]
"""
from __future__ import annotations

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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'assets' / 'blender' / 'sunmeadow_v2' / 'terrain'))
import forge_textures_r6 as r6  # noqa: E402  (imports R6 Forge, pnoise and the mesh helpers)
import terrain_spec as TS  # noqa: E402

pnoise = r6.pnoise
sample_periodic = r6.sample_periodic
finalize_mesh = r6.finalize_mesh
hexrgb = r6.hexrgb
srgb_to_linear = r6.srgb_to_linear

# Raw passes are agent output, not repo content (llm.txt: Downloads/Xexoria-Game/agent-output/<date>-<topic>/).
DEFAULT_PASSES = Path.home() / 'Downloads' / 'Xexoria-Game' / 'agent-output' / '20261002-map-terrain' / 'forge-r7-passes'

# kind codes written to the id pass (G); the composite turns them into masks.
K_SOIL, K_TURF, K_FLAT, K_STONE, K_MOSS, K_BLADE, K_WOOD, K_LEAF = 0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 0.5, 0.3


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = {'only': '', 'seed': 7, 'passes': str(DEFAULT_PASSES), 'device': TS.FORGE['device_default'],
            'composite': True, 'scale': TS.FORGE['render_scale'], 'final': 0}
    i = 0
    while i < len(argv):
        key = argv[i].lstrip('-')
        if key == 'no-composite':
            args['composite'] = False
            i += 1
        elif key in args and i + 1 < len(argv):
            args[key] = type(args[key])(argv[i + 1]) if not isinstance(args[key], str) else argv[i + 1]
            i += 2
        else:
            raise SystemExit(f'unknown argument {argv[i]}')
    if args['device'] not in ('cpu', 'gpu'):
        raise SystemExit('--device must be cpu or gpu')
    return args


def lin(hex_value: str, scale: float = 1.0) -> tuple[float, float, float]:
    return tuple(float(c) for c in srgb_to_linear(np.clip(np.array(hexrgb(hex_value), np.float32) * scale, 0, 1)))


def jitter(rng: random.Random, hex_value: str, value=0.08, hue=0.03) -> np.ndarray:
    base = np.array(hexrgb(hex_value), np.float32) * (1 + rng.uniform(-value, value))
    tint = np.array([1 + rng.uniform(-hue, hue) for _ in range(3)], np.float32)
    return srgb_to_linear(np.clip(base * tint, 0, 1)).astype(np.float32)


class ForgeR7(r6.Forge):
    """R6 forge with a CPU-only render setup (CUDA is not even enumerated unless --device gpu)."""

    device = 'cpu'

    def _setup_render(self):
        scene = self.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        if ForgeR7.device == 'gpu':
            try:
                prefs = bpy.context.preferences.addons['cycles'].preferences
                prefs.compute_device_type = 'CUDA'
                prefs.get_devices()
                for device in prefs.devices:
                    device.use = device.type == 'CUDA'
                if any(d.type == 'CUDA' for d in prefs.devices):
                    scene.cycles.device = 'GPU'
            except Exception:
                scene.cycles.device = 'CPU'
        scene.cycles.max_bounces = 0
        scene.cycles.diffuse_bounces = 0
        scene.cycles.glossy_bounces = 0
        scene.cycles.transmission_bounces = 0
        scene.cycles.use_adaptive_sampling = False
        scene.render.threads_mode = 'AUTO'
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

    def render_passes(self, out_dir: Path, ao_distance: float, bevel_radius: float) -> dict:
        self.pass_materials['ao'].node_tree.nodes['forge-ao'].inputs['Distance'].default_value = ao_distance
        self.pass_materials['edge'].node_tree.nodes['forge-bevel'].inputs['Radius'].default_value = bevel_radius
        arrays = {}
        layer = self.scene.view_layers[0]
        exr_dir = out_dir / '_exr'
        exr_dir.mkdir(parents=True, exist_ok=True)
        for name, material in self.pass_materials.items():
            layer.material_override = material
            self.scene.cycles.samples = TS.FORGE['samples'].get(name, 8)
            self.scene.cycles.use_denoising = name in ('ao', 'edge')
            path = exr_dir / f'{self.name}_{name}.exr'
            self.scene.render.filepath = str(path)
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            image = bpy.data.images.load(str(path), check_existing=False)
            image.colorspace_settings.name = 'Non-Color'
            pixels = np.empty(self.px * self.px * 4, np.float32)
            image.pixels.foreach_get(pixels)
            data = np.flipud(pixels.reshape(self.px, self.px, 4)[..., :3]).copy()
            bpy.data.images.remove(image)
            path.unlink(missing_ok=True)
            arrays[name] = data[..., 0] if name in ('height', 'ao', 'edge') else data
            np.save(out_dir / f'{self.name}_{name}.npy', arrays[name].astype(np.float32))
            print(f'  pass {name}: {time.time() - t0:.1f} s', flush=True)
        layer.material_override = None
        return arrays


# ----------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------

class BladeBatch:
    """Many thin curved blades in one mesh, with a per-corner colour layer and manual wrap copies."""

    def __init__(self, T: float, name: str):
        self.T, self.name = T, name
        self.bm = bmesh.new()
        self.col = self.bm.loops.layers.color.new('col')
        self.count = 0

    def blade(self, bx, by, az, lean, length, width, c_base, c_tip, curl=0.6, z0=0.0, segs=3):
        dx, dy = math.cos(az), math.sin(az)
        px, py = -dy, dx
        pts = []
        for k in range(segs + 1):
            t = k / segs
            a = lean * (curl * t + (1 - curl) * t * t) * 1.15
            # arc: horizontal reach grows with lean, height shrinks
            r = length * t
            hx = math.sin(min(1.45, a)) * r
            hz = math.cos(min(1.45, a)) * r
            w = width * (1 - t) ** 0.8
            col = c_base * (1 - t) + c_tip * t
            pts.append((bx + dx * hx, by + dy * hx, z0 + hz, w, col))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        lo_x, hi_x, lo_y, hi_y = min(xs) - width, max(xs) + width, min(ys) - width, max(ys) + width
        T = self.T
        for ox in (-T, 0.0, T):
            if hi_x + ox < -0.02 or lo_x + ox > T + 0.02:
                continue
            for oy in (-T, 0.0, T):
                if hi_y + oy < -0.02 or lo_y + oy > T + 0.02:
                    continue
                self._emit(pts, px, py, ox, oy)
        self.count += 1

    def _emit(self, pts, px, py, ox, oy):
        bm, col = self.bm, self.col
        verts = []
        for x, y, z, w, c in pts[:-1]:
            verts.append((bm.verts.new((x + px * w + ox, y + py * w + oy, z)), c))
            verts.append((bm.verts.new((x - px * w + ox, y - py * w + oy, z)), c))
        tx, ty, tz, _, tc = pts[-1]
        tip = (bm.verts.new((tx + ox, ty + oy, tz)), tc)
        for k in range(len(pts) - 2):
            a, b, c2, d = verts[2 * k], verts[2 * k + 1], verts[2 * k + 3], verts[2 * k + 2]
            self._face([a, b, c2, d])
        self._face([verts[-2], verts[-1], tip])

    def _face(self, vc):
        try:
            face = self.bm.faces.new([v for v, _ in vc])
        except ValueError:
            return
        for loop, (_, c) in zip(face.loops, vc):
            loop[self.col] = (float(c[0]), float(c[1]), float(c[2]), 1.0)

    def finish(self, forge: ForgeR7, kind: float, rough: float):
        mesh = finalize_mesh(self.bm, self.name, smooth=True)
        forge.add(mesh, (0, 0, 0), albedo=(0.1, 0.2, 0.05), kind=kind, rough=rough, speckle=0.0, use_vcol=1.0,
                  wrap=False, name=self.name)


def periodic_points(rng: random.Random, T: float, count: int, min_dist: float, density=None, attempts=30):
    """Dart throwing with a periodic grid; density(x, y) in 0..1 thins the field (clustered placement)."""
    cell = max(min_dist, 1e-3)
    grid: dict[tuple[int, int], list] = {}
    n = max(1, int(T / cell))
    pts = []
    tries = 0
    while len(pts) < count and tries < count * attempts:
        tries += 1
        x, y = rng.uniform(0, T), rng.uniform(0, T)
        if density is not None and rng.random() > density(x, y):
            continue
        gx, gy = int(x / T * n) % n, int(y / T * n) % n
        ok = True
        for ix in (-1, 0, 1):
            for iy in (-1, 0, 1):
                for qx, qy in grid.get(((gx + ix) % n, (gy + iy) % n), ()):
                    ddx = min(abs(x - qx), T - abs(x - qx))
                    ddy = min(abs(y - qy), T - abs(y - qy))
                    if ddx * ddx + ddy * ddy < min_dist * min_dist:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            grid.setdefault((gx, gy), []).append((x, y))
            pts.append((x, y))
    return pts


def field_plane(forge: ForgeR7, z_fn, res: int, name: str) -> bpy.types.Mesh:
    """Periodic heightfield grid over the tile plus a margin; z_fn(u, v) takes tile-relative coordinates."""
    bm = bmesh.new()
    T = forge.T
    m = forge.margin + T * 0.04
    span = T + 2 * m
    step = span / res
    rows = []
    for j in range(res + 1):
        row = []
        for i in range(res + 1):
            x, y = -m + i * step, -m + j * step
            row.append(bm.verts.new((x, y, z_fn(x / T, y / T))))
        rows.append(row)
    for j in range(res):
        for i in range(res):
            bm.faces.new((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]))
    return finalize_mesh(bm, name)


def pebble_mesh(rng: random.Random, r: float, flat: float, chips: int, displace: float, smooth_round=False,
                name='pebble') -> bpy.types.Mesh:
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3 if r > 0.012 else 2, radius=1.0)
    sx, sy, sz = r * rng.uniform(0.85, 1.2), r * rng.uniform(0.7, 1.0), r * flat * rng.uniform(0.85, 1.15)
    seed = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50)))
    for v in bm.verts:
        n = noise.noise(v.co * 1.9 + seed)
        n2 = noise.noise(v.co * 4.3 + seed * 1.3)
        k = 1 + displace * (n + 0.35 * n2)
        v.co.x *= sx * k
        v.co.y *= sy * k
        v.co.z *= sz * k
    if not smooth_round:
        for _ in range(chips):
            direction = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.2, 1.0))).normalized()
            point = direction * (r * rng.uniform(0.55, 0.85))
            point.z *= flat
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            result = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=point, plane_no=direction, clear_outer=True)
            cut = [e for e in result['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
            if cut:
                bmesh.ops.holes_fill(bm, edges=cut, sides=0)
    return finalize_mesh(bm, name)


def dome_mesh(rng: random.Random, r: float, height: float, lumps: float, name='dome', subdiv=3) -> bpy.types.Mesh:
    """Cushion: a squashed, lumpy hemisphere-ish blob (moss, clods)."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    seed = Vector((rng.uniform(-60, 60), rng.uniform(-60, 60), rng.uniform(-60, 60)))
    sx, sy = r * rng.uniform(0.85, 1.15), r * rng.uniform(0.8, 1.1)
    for v in bm.verts:
        n = noise.noise(v.co * 2.4 + seed) + 0.45 * noise.noise(v.co * 6.0 + seed * 1.7)
        k = 1 + lumps * n
        z = v.co.z
        v.co.x *= sx * k
        v.co.y *= sy * k
        v.co.z = (z if z > 0 else z * 0.25) * height * k
    return finalize_mesh(bm, name)


def tube_mesh(points, radius, name='tube', sides=6) -> bpy.types.Mesh:
    bm = bmesh.new()
    rings = []
    for k, p in enumerate(points):
        a = Vector(points[min(k + 1, len(points) - 1)]) - Vector(points[max(k - 1, 0)])
        a.normalize()
        up = Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))
        side = a.cross(up).normalized()
        up2 = side.cross(a).normalized()
        rr = radius * (1 - 0.6 * k / max(1, len(points) - 1))
        ring = [bm.verts.new(Vector(p) + (side * math.cos(t) + up2 * math.sin(t)) * rr)
                for t in (i / sides * math.tau for i in range(sides))]
        rings.append(ring)
    for k in range(len(rings) - 1):
        for i in range(sides):
            bm.faces.new((rings[k][i], rings[k][(i + 1) % sides], rings[k + 1][(i + 1) % sides], rings[k + 1][i]))
    return finalize_mesh(bm, name)


def leaf_mesh(rng: random.Random, length: float, width: float, curl: float, name='leaf') -> bpy.types.Mesh:
    bm = bmesh.new()
    segs = 6
    rows = []
    for k in range(segs + 1):
        t = k / segs
        w = width * math.sin(math.pi * t) ** 0.8 + 1e-4
        x = (t - 0.5) * length
        z_mid = curl * (t - 0.5) ** 2 * length
        row = [bm.verts.new((x, -w, z_mid + curl * 0.4 * w)), bm.verts.new((x, 0, z_mid)), bm.verts.new((x, w, z_mid + curl * 0.4 * w))]
        rows.append(row)
    for k in range(segs):
        for i in range(2):
            bm.faces.new((rows[k][i], rows[k][i + 1], rows[k + 1][i + 1], rows[k + 1][i]))
    return finalize_mesh(bm, name)


def clover_mesh(rng: random.Random, leaf_r: float, name='clover') -> bpy.types.Mesh:
    bm = bmesh.new()
    for k in range(3):
        a = k / 3 * math.tau + rng.uniform(-0.2, 0.2)
        cx, cy = math.cos(a) * leaf_r * 0.95, math.sin(a) * leaf_r * 0.95
        centre = bm.verts.new((cx, cy, leaf_r * 0.25))
        ring = []
        for i in range(10):
            t = i / 10 * math.tau
            # heart-ish leaflet: notch toward the stem
            rr = leaf_r * (1 - 0.18 * max(0.0, math.cos(t - a)) ** 6)
            ring.append(bm.verts.new((cx + math.cos(t) * rr, cy + math.sin(t) * rr, leaf_r * 0.25 * (0.6 + 0.4 * math.cos(t - a - math.pi)))))
        for i in range(10):
            bm.faces.new((centre, ring[i], ring[(i + 1) % 10]))
    return finalize_mesh(bm, name)


def add_wrapped(forge: ForgeR7, mesh, x, y, z, rot, **kw):
    forge.add(mesh, (x % forge.T, y % forge.T, z), rot, **kw)


# ----------------------------------------------------------------------------
# Layer generators (spec §3.3 "Geometry content")
# ----------------------------------------------------------------------------

def gen_lush(forge: ForgeR7, layer: dict, seed: int) -> dict:
    """L0: soil plane +-1.5 cm fBm; clumps 0.08-0.22 m wide, 0.04-0.12 m tall, 6-14 blades, 40-60 % cover; clover ~5 %.

    v2 (visual pass): blades are 5-11 mm wide so they survive the 5.9 mm texel, the short turf is dense enough
    that no bare felt-like base shows, clumps carry dark cores and bright tips, clover is a dark accent."""
    rng, T = forge.rng, forge.T
    forge.margin = 0.3
    soil = pnoise(256, 256 * 0.55 / T, seed + 1, octaves=3)
    soil2 = pnoise(256, 256 * 0.18 / T, seed + 2, octaves=2)
    forge.add(field_plane(forge, lambda u, v: (sample_periodic(soil, u, v) - 0.5) * 0.030
                          + (sample_periodic(soil2, u, v) - 0.5) * 0.008, 220, 'soil'),
              (0, 0, 0), albedo=lin('#1f3818'), kind=K_SOIL, rough=0.93, speckle=0.0, wrap=False, name='soil')
    density = pnoise(256, 256 * 0.9 / T, seed + 3, octaves=2)
    dens = lambda x, y: 0.35 + 0.65 * smooth01(sample_periodic(density, x / T, y / T), 0.2, 0.8)  # noqa: E731
    hue = pnoise(256, 256 * 1.4 / T, seed + 4, octaves=2)
    turf = BladeBatch(T, 'turf')
    for x, y in periodic_points(rng, T, 26000, 0.016):
        h = rng.uniform(0.016, 0.045)
        cool = sample_periodic(hue, x / T, y / T)
        base = jitter(rng, rng.choice(['#22401c', '#284a1e', '#1e3a19']), 0.10, 0.04)
        tip = jitter(rng, '#3f6e2e' if cool > 0.55 else rng.choice(['#4c7a2f', '#557f30']), 0.12, 0.04)
        turf.blade(x, y, rng.uniform(0, math.tau), rng.uniform(0.35, 1.1), h, rng.uniform(0.0045, 0.0075), base, tip, segs=2)
    turf.finish(forge, K_TURF, 0.86)
    blades = BladeBatch(T, 'blades')
    centres = periodic_points(rng, T, 1500, 0.07, density=dens)
    families = [('#2e5222', ['#8fb04c', '#9fbe55']), ('#365c25', ['#9fbe55', '#b9cc6a']),
                ('#2c5530', ['#7fa860', '#8db86a']), ('#3d5f22', ['#a8b858', '#b5c060'])]
    for cx, cy in centres:
        width = rng.uniform(0.08, 0.22)
        height = rng.uniform(0.04, 0.12) * (0.7 + 0.3 * width / 0.22)
        root_hex, tips = families[rng.choices(range(4), weights=(0.35, 0.35, 0.18, 0.12))[0]]
        dry = rng.random() < 0.05
        c_base = jitter(rng, '#5a6a2c' if dry else root_hex, 0.10, 0.03)
        c_tip = jitter(rng, '#c0b464' if dry else rng.choice(tips), 0.08, 0.03)
        for _ in range(rng.randint(8, 14)):
            a = rng.uniform(0, math.tau)
            rr = width * 0.5 * math.sqrt(rng.random()) * 0.5
            bx, by = cx + math.cos(a) * rr, cy + math.sin(a) * rr
            out = math.atan2(by - cy, bx - cx) if rr > 1e-4 else rng.uniform(0, math.tau)
            az = out + rng.uniform(-0.55, 0.55)
            lean = rng.uniform(0.3, 0.8) + 0.45 * rr / max(1e-3, width * 0.5)
            length = height * rng.uniform(0.85, 1.25) / max(0.4, math.cos(min(1.2, lean * 0.6)))
            blades.blade(bx, by, az, lean, length, rng.uniform(0.0055, 0.011), c_base * rng.uniform(0.9, 1.1),
                         c_tip * rng.uniform(0.92, 1.08), curl=rng.uniform(0.35, 0.8))
    blades.finish(forge, K_BLADE, 0.76)
    clovers = 0
    for px_, py_ in periodic_points(rng, T, 70, 0.4):
        for _ in range(rng.randint(5, 11)):
            r = rng.uniform(0.008, 0.015)
            x, y = px_ + rng.gauss(0, 0.06), py_ + rng.gauss(0, 0.06)
            mesh = clover_mesh(rng, r)
            add_wrapped(forge, mesh, x, y, rng.uniform(0.006, 0.022), (rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.uniform(0, math.tau)),
                        albedo=jitter(rng, rng.choice(['#3f6a2a', '#466f2c']), 0.08, 0.03), kind=K_FLAT, rough=0.70, speckle=0.05, name='clover')
            clovers += 1
    return dict(clumps=len(centres), blades=blades.count, turf=turf.count, clovers=clovers)


def gen_dry(forge: ForgeR7, layer: dict, seed: int) -> dict:
    """L1: straw tufts 0.03-0.08 m, 25-35 % bare soil with grit, dead leaves 3 %.

    v2: olive-to-straw strokes 4-9 mm wide cover 65-75 %, bare warm soil reads as patches, not as the base."""
    rng, T = forge.rng, forge.T
    pal = layer['palette']
    forge.margin = 0.25
    soil = pnoise(256, 256 * 0.45 / T, seed + 1, octaves=3)
    grit = pnoise(256, 256 * 0.08 / T, seed + 2, octaves=2)
    forge.add(field_plane(forge, lambda u, v: (sample_periodic(soil, u, v) - 0.5) * 0.020
                          + (sample_periodic(grit, u, v) - 0.5) * 0.005, 220, 'soil'),
              (0, 0, 0), albedo=lin(pal['shadow'][0]), kind=K_SOIL, rough=0.96, speckle=0.0, wrap=False, name='soil')
    bare = pnoise(256, 256 * 0.6 / T, seed + 3, octaves=2)
    cover = lambda x, y: 1.0 - smooth01(sample_periodic(bare, x / T, y / T), 0.60, 0.74)  # noqa: E731
    turf = BladeBatch(T, 'turf')
    for x, y in periodic_points(rng, T, 15000, 0.017, density=lambda x, y: 0.08 + 0.92 * cover(x, y)):
        base = jitter(rng, rng.choice(['#6f7a36', '#7c8a3a', '#66702f']), 0.10, 0.04)
        tip = jitter(rng, rng.choice(['#a5a14a', '#b3a957', '#9a9a48']), 0.08, 0.04)
        turf.blade(x, y, rng.uniform(0, math.tau), rng.uniform(0.6, 1.3), rng.uniform(0.012, 0.03), rng.uniform(0.004, 0.006),
                   base, tip, segs=2)
    turf.finish(forge, K_TURF, 0.90)
    tufts = BladeBatch(T, 'tufts')
    centres = periodic_points(rng, T, 1500, 0.055, density=lambda x, y: 0.04 + 0.96 * cover(x, y))
    for cx, cy in centres:
        height = rng.uniform(0.03, 0.08)
        green = rng.random() < 0.3
        c_base = jitter(rng, '#6f7a36' if green else rng.choice(pal['base']), 0.10, 0.03)
        c_tip = jitter(rng, '#a5a14a' if green else rng.choice([pal['light'][0], '#d0bc72', '#bfae62']), 0.08, 0.03)
        for _ in range(rng.randint(7, 13)):
            a = rng.uniform(0, math.tau)
            rr = rng.uniform(0, 0.022)
            bx, by = cx + math.cos(a) * rr, cy + math.sin(a) * rr
            tufts.blade(bx, by, a + rng.uniform(-0.8, 0.8), rng.uniform(0.6, 1.35), height * rng.uniform(0.8, 1.3),
                        rng.uniform(0.0045, 0.0085), c_base, c_tip * rng.uniform(0.95, 1.08), curl=rng.uniform(0.3, 0.7))
    tufts.finish(forge, K_BLADE, 0.88)
    leaves = 0
    for x, y in periodic_points(rng, T, 200, 0.07):
        mesh = leaf_mesh(rng, rng.uniform(0.028, 0.05), rng.uniform(0.009, 0.016), rng.uniform(0.15, 0.5))
        add_wrapped(forge, mesh, x, y, rng.uniform(0.004, 0.012), (rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), rng.uniform(0, math.tau)),
                    albedo=jitter(rng, rng.choice([pal['accent'][0], '#8a5a30', '#a87a42']), 0.10, 0.04), kind=K_LEAF, rough=0.88,
                    speckle=0.08, name='leaf')
        leaves += 1
    return dict(tufts=len(centres), blades=tufts.count, turf=turf.count, leaves=leaves)


def footprint_field(rng: random.Random, T: float, count: int) -> list:
    prints = []
    for _ in range(count):
        x, y = rng.uniform(0, T), rng.uniform(0, T)
        a = rng.uniform(0, math.tau)
        for k in range(rng.randint(1, 3)):
            ox = math.cos(a) * 0.65 * k + math.cos(a + math.pi / 2) * (0.12 if k % 2 else -0.12)
            oy = math.sin(a) * 0.65 * k + math.sin(a + math.pi / 2) * (0.12 if k % 2 else -0.12)
            prints.append(((x + ox) % T, (y + oy) % T, a + rng.uniform(-0.15, 0.15), rng.uniform(0.24, 0.29), rng.uniform(0.085, 0.105)))
    return prints


def gen_dirt(forge: ForgeR7, layer: dict, seed: int) -> dict:
    """L2: packed soil +-1 cm, clods 2-6 cm, pebbles 0.8-1.5 / 1.5-3 / 3-6 cm sunk 30-60 %, 5 mm footprints, roots, seeds."""
    rng, T = forge.rng, forge.T
    pal = layer['palette']
    forge.margin = 0.12
    soil = pnoise(256, 256 * 0.6 / T, seed + 1, octaves=3)
    soil2 = pnoise(256, 256 * 0.25 / T, seed + 2, octaves=2)
    prints = footprint_field(rng, T, rng.randint(9, 14))

    def z_fn(u, v):
        x, y = u * T, v * T
        z = (sample_periodic(soil, u, v) - 0.5) * 0.020 + (sample_periodic(soil2, u, v) - 0.5) * 0.006
        for fx, fy, a, length, width in prints:
            dx = (x - fx + T / 2) % T - T / 2   # wrapped signed difference (periodic tile)
            dy = (y - fy + T / 2) % T - T / 2
            lx = dx * math.cos(a) + dy * math.sin(a)
            ly = -dx * math.sin(a) + dy * math.cos(a)
            q = (lx / (length / 2)) ** 2 + (ly / (width / 2)) ** 2
            if q < 1.3:
                z -= 0.005 * (1 - min(1.0, q) ** 2) * (0.7 + 0.3 * (lx > 0))
        return z

    forge.add(field_plane(forge, z_fn, 260, 'soil'), (0, 0, 0), albedo=lin(pal['base'][0], 0.97), kind=K_SOIL, rough=0.95,
              speckle=0.0, wrap=False, name='soil')
    cluster = pnoise(256, 256 * 0.5 / T, seed + 3, octaves=2)
    dens = lambda x, y: 0.35 + 0.65 * sample_periodic(cluster, x / T, y / T)  # noqa: E731
    counts = {}
    for label, (lo, hi), count, flat in (('large', (0.015, 0.03), 120, 0.55), ('medium', (0.0075, 0.015), 650, 0.6),
                                         ('small', (0.004, 0.0075), 2400, 0.65)):
        pts = periodic_points(rng, T, count, hi * 1.6, density=dens)
        for x, y in pts:
            r = rng.uniform(lo, hi)
            mesh = pebble_mesh(rng, r, flat, chips=rng.choice((0, 1, 1, 2)), displace=0.12, name=f'pebble-{label}')
            sink = rng.uniform(0.30, 0.60)
            z = r * flat * (1 - 2 * sink)
            add_wrapped(forge, mesh, x, y, z, (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0, math.tau)),
                        albedo=jitter(rng, rng.choice(pal['accent']), 0.10, 0.02), kind=K_STONE, rough=rng.uniform(0.62, 0.72),
                        speckle=0.18, name='pebble')
        counts[label] = len(pts)
    clods = 0
    for x, y in periodic_points(rng, T, 130, 0.06):
        r = rng.uniform(0.01, 0.03)
        mesh = dome_mesh(rng, r, r * 0.55, 0.28, 'clod', subdiv=2)
        add_wrapped(forge, mesh, x, y, -r * 0.1, (0, 0, rng.uniform(0, math.tau)), albedo=jitter(rng, pal['shadow'][0], 0.08, 0.02),
                    kind=K_SOIL, rough=0.97, speckle=0.2, name='clod')
        clods += 1
    roots = 0
    for _ in range(4):
        x, y = rng.uniform(0, T), rng.uniform(0, T)
        a = rng.uniform(0, math.tau)
        length = rng.uniform(0.3, 0.8)
        pts = []
        for k in range(10):
            t = k / 9
            a += rng.uniform(-0.25, 0.25)
            pts.append((x + math.cos(a) * length * t, y + math.sin(a) * length * t, -0.002 + 0.004 * math.sin(t * 9 + rng.random())))
        mesh = tube_mesh(pts, rng.uniform(0.004, 0.008), 'root')
        add_wrapped(forge, mesh, 0, 0, 0, (0, 0, 0), albedo=lin('#5a4030'), kind=K_WOOD, rough=0.85, speckle=0.1, name='root')
        roots += 1
    seeds = 0
    for x, y in periodic_points(rng, T, 160, 0.03):
        mesh = pebble_mesh(rng, 0.0018, 0.6, 0, 0.0, smooth_round=True, name='seed')
        add_wrapped(forge, mesh, x, y, 0.0008, (0, 0, rng.uniform(0, math.tau)), albedo=jitter(rng, '#c4b066', 0.1, 0.03),
                    kind=K_LEAF, rough=0.8, speckle=0.0, name='seed')
        seeds += 1
    return dict(pebbles=counts, clods=clods, roots=roots, seeds=seeds, footprints=len(prints))


def gen_mud(forge: ForgeR7, layer: dict, seed: int) -> dict:
    """L3: smooth wet mud +-4 mm, puddle hollows -8 mm, moss cushions 3-8 cm at 25 %, wet stones 2-6 cm, twigs."""
    rng, T = forge.rng, forge.T
    pal = layer['palette']
    forge.margin = 0.1
    mud = pnoise(256, 256 * 0.35 / T, seed + 1, octaves=3)
    puddle = pnoise(256, 256 * 0.45 / T, seed + 2, octaves=2)
    forge.add(field_plane(forge, lambda u, v: (sample_periodic(mud, u, v) - 0.5) * 0.008
                          - 0.008 * smooth01(sample_periodic(puddle, u, v), 0.62, 0.80), 200, 'mud'),
              (0, 0, 0), albedo=lin(pal['base'][0]), kind=K_SOIL, rough=0.55, speckle=0.0, wrap=False, name='mud')
    patch = pnoise(256, 256 * 0.5 / T, seed + 3, octaves=3)
    moss_dens = lambda x, y: smooth01(sample_periodic(patch, x / T, y / T), 0.46, 0.60)  # noqa: E731
    cushions = 0
    for x, y in periodic_points(rng, T, 2600, 0.016, density=moss_dens):
        r = rng.uniform(0.008, 0.03)
        mesh = dome_mesh(rng, r, r * rng.uniform(0.3, 0.6), 0.3, 'moss', subdiv=2)
        add_wrapped(forge, mesh, x, y, -0.002, (0, 0, rng.uniform(0, math.tau)),
                    albedo=jitter(rng, rng.choice(['#3d5a26', pal['accent'][0], '#46602a', '#55702c']), 0.10, 0.04), kind=K_MOSS,
                    rough=0.88, speckle=0.3, name='moss')
        cushions += 1
    stones = 0
    for x, y in periodic_points(rng, T, 60, 0.09):
        r = rng.uniform(0.010, 0.030)
        mesh = pebble_mesh(rng, r, 0.55, 0, 0.08, smooth_round=True, name='wet-stone')
        add_wrapped(forge, mesh, x, y, r * 0.55 * (1 - 2 * rng.uniform(0.3, 0.55)), (0, 0, rng.uniform(0, math.tau)),
                    albedo=jitter(rng, pal['accent'][1], 0.10, 0.02), kind=K_STONE, rough=0.45, speckle=0.12, name='stone')
        stones += 1
    twigs = 0
    for _ in range(18):
        x, y = rng.uniform(0, T), rng.uniform(0, T)
        a = rng.uniform(0, math.tau)
        length = rng.uniform(0.08, 0.25)
        pts = [(x + math.cos(a) * length * t + rng.uniform(-0.004, 0.004), y + math.sin(a) * length * t, 0.0015) for t in np.linspace(0, 1, 6)]
        mesh = tube_mesh(pts, rng.uniform(0.0015, 0.003), 'twig', sides=5)
        add_wrapped(forge, mesh, 0, 0, 0, (0, 0, 0), albedo=lin('#4a3626'), kind=K_WOOD, rough=0.8, speckle=0.1, name='twig')
        twigs += 1
    return dict(cushions=cushions, stones=stones, twigs=twigs)


def gen_rock(forge: ForgeR7, layer: dict, seed: int) -> dict:
    """R0: R6 gen_strata re-tiled to 4 m; blocks, chips and cracks, displacement 4-8 cm; near-neutral (tinted at runtime)."""
    spec = dict(layer=(0.11, 0.42), seg=(1.1, 3.1), gap=0.016, protrude=(0.085, 0.13), bevel=0.022, displace=0.03, freq=3.2,
                cuts=11, chips=(1, 2, 2, 3), back='#3f382f',
                palette=['#9a9284', '#8c867b', '#a39b8c', '#857f74', '#ada392', '#958d7f'])
    r6.gen_strata(forge, spec)
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.name.startswith('crevice'):
            obj.location.z -= 0.045   # keep the crevice plane (+-4 cm) below the lowest slab faces
    # R6's strata always start a band at y = 0, so the tile edge sits on a crevice edge (R6 cliff_rock reported
    # seam 3.1 for that reason). Shift everything by part of a band: the arrangement stays periodic, the crevice
    # plane is periodic and extends past the tile, and copies cover the shift (margin 1.3 m).
    shift = forge.rng.uniform(0.09, 0.2)
    blocks = 0
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        obj.location.y += shift
        if obj.name.startswith('crevice'):
            obj['speckle'] = 0.0   # object-space speckle is not periodic; the composite adds periodic grain
        elif obj.name.startswith('strata'):
            blocks += 1
    # Hairline cracks are painted in the composite from one mask into height, albedo and roughness.
    return dict(blocks=blocks, band_shift_m=round(shift, 3))


def gen_moss(forge: ForgeR7, layer: dict, seed: int) -> dict:
    """R1: moss mat - dense cushions and short fibres over dark humus."""
    rng, T = forge.rng, forge.T
    pal = layer['palette']
    forge.margin = 0.1
    humus = pnoise(256, 256 * 0.3 / T, seed + 1, octaves=3)
    forge.add(field_plane(forge, lambda u, v: (sample_periodic(humus, u, v) - 0.5) * 0.012, 180, 'humus'),
              (0, 0, 0), albedo=lin('#2a2a18'), kind=K_SOIL, rough=0.92, speckle=0.0, wrap=False, name='humus')
    cushions = 0
    clump = pnoise(256, 256 * 0.35 / T, seed + 2, octaves=3)
    for x, y in periodic_points(rng, T, 5200, 0.014, density=lambda x, y: 0.25 + 0.75 * sample_periodic(clump, x / T, y / T)):
        r = rng.uniform(0.010, 0.032)
        mesh = dome_mesh(rng, r, r * rng.uniform(0.35, 0.7), 0.32, 'moss', subdiv=2)
        add_wrapped(forge, mesh, x, y, -0.003, (0, 0, rng.uniform(0, math.tau)),
                    albedo=jitter(rng, rng.choice(pal['base'] + ['#46602a', '#3d5a26', '#64822f']), 0.12, 0.05), kind=K_MOSS,
                    rough=0.84, speckle=0.3, name='moss')
        cushions += 1
    fibres = BladeBatch(T, 'fibres')
    for x, y in periodic_points(rng, T, 11000, 0.011):
        base = jitter(rng, rng.choice(pal['base']), 0.1, 0.04)
        tip = jitter(rng, rng.choice(pal['light']), 0.08, 0.04)
        fibres.blade(x, y, rng.uniform(0, math.tau), rng.uniform(0.2, 0.9), rng.uniform(0.008, 0.02), 0.0024, base, tip, segs=2,
                     z0=0.006)
    fibres.finish(forge, K_BLADE, 0.80)
    return dict(cushions=cushions, fibres=fibres.count)


def smooth01(x, a, b):
    t = min(1.0, max(0.0, (x - a) / max(1e-6, b - a)))
    return t * t * (3 - 2 * t)


GENERATORS = {'L0': gen_lush, 'L1': gen_dry, 'L2': gen_dirt, 'L3': gen_mud, 'R0': gen_rock, 'R1': gen_moss}
# Cycles AO distance and bevel radius per layer (metres).
PASS_SETTINGS = {'L0': (0.07, 0.004), 'L1': (0.05, 0.004), 'L2': (0.12, 0.005), 'L3': (0.06, 0.005),
                 'R0': (0.10, 0.02), 'R1': (0.05, 0.005)}


def main() -> None:
    args = parse_args()
    ForgeR7.device = args['device']
    passes_dir = Path(args['passes'])
    passes_dir.mkdir(parents=True, exist_ok=True)
    only = [s for s in args['only'].split(',') if s]
    layers = [layer for layer in TS.ALL_LAYERS if not only or layer['id'] in only]
    records = {}
    for layer in layers:
        started = time.time()
        final = args['final'] or layer['res']['high']   # --final 128: smoke test of every generator
        render_px = final * args['scale']
        forge = ForgeR7(layer['id'], layer['tile_m'], render_px, args['seed'])
        seed = args['seed'] * 1000 + sum(ord(c) for c in layer['id'])
        print(f'FORGE R7 {layer["id"]} {layer["name"]}: tile {layer["tile_m"]} m, render {render_px}^2 -> {final}^2', flush=True)
        content = GENERATORS[layer['id']](forge, layer, seed)
        objects = len([o for o in bpy.data.objects if o.type == 'MESH'])
        tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
        ao_d, bevel_r = PASS_SETTINGS[layer['id']]
        forge.render_passes(passes_dir, ao_d, bevel_r)
        records[layer['id']] = dict(name=layer['name'], tile_m=layer['tile_m'], render_px=render_px, final_px=final,
                                    objects=objects, faces=tris, content=content, ao_distance_m=ao_d, bevel_radius_m=bevel_r,
                                    device=bpy.context.scene.cycles.device, seed=args['seed'],
                                    seconds=round(time.time() - started, 1))
        print(f'FORGE R7 {layer["id"]}: {objects} objects, {tris} faces, {records[layer["id"]]["seconds"]} s, {content}', flush=True)
        # Written after every layer so a later crash never loses earlier metadata.
        meta_path = passes_dir / 'forge-r7-passes.json'
        previous = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        previous.update(records)
        meta_path.write_text(json.dumps(previous, indent=1) + '\n')
    if args['composite']:
        import terrain_forge_composite as comp
        comp.main(['--passes', str(passes_dir)] + (['--only', ','.join(only)] if only else []))


if __name__ == '__main__':
    main()
