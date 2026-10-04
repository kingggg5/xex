"""Generate original, seamless hand-painted-style PBR maps for the R5 city.

The maps are authored from deterministic tile geometry, layered periodic
signals, wear, cracks and material palettes. No photo textures or reference
pixels are used. Run with the project Python environment from the repo root.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fcore as fc  # noqa: E402

ROOT = HERE.parents[3]
OUT = ROOT / 'assets' / 'models' / 'reference-city' / 'r5' / 'textures'
OUT.mkdir(parents=True, exist_ok=True)
SIZE = int(os.environ.get('CITY_TEXTURE_SIZE', '1024'))

STONE_PALETTE = [
    (0.60, 0.53, 0.43), (0.68, 0.59, 0.47), (0.73, 0.65, 0.53),
    (0.78, 0.70, 0.59), (0.64, 0.60, 0.54), (0.82, 0.74, 0.62),
]
WOOD_PALETTE = [
    (0.19, 0.095, 0.042), (0.26, 0.13, 0.055), (0.32, 0.17, 0.074),
    (0.39, 0.22, 0.10), (0.29, 0.15, 0.08),
]
ROOFS = {
    'roof_slate_blue': [(0.075, 0.16, 0.40), (0.095, 0.22, 0.52), (0.13, 0.27, 0.58), (0.18, 0.32, 0.62), (0.08, 0.19, 0.48)],
    'roof_slate_navy': [(0.045, 0.085, 0.22), (0.06, 0.13, 0.32), (0.09, 0.18, 0.40), (0.12, 0.23, 0.46)],
    'roof_shingle_green': [(0.08, 0.24, 0.18), (0.11, 0.34, 0.23), (0.15, 0.42, 0.28), (0.22, 0.46, 0.30)],
    'roof_tile_red': [(0.38, 0.095, 0.055), (0.51, 0.14, 0.08), (0.61, 0.20, 0.12), (0.68, 0.25, 0.15)],
}
STONE_PALETTE_COOL = [
    (0.36, 0.39, 0.43), (0.43, 0.46, 0.50), (0.49, 0.51, 0.53),
    (0.55, 0.55, 0.54), (0.38, 0.44, 0.48), (0.61, 0.60, 0.57),
]


def crack_field(ctx: fc.Ctx, count: int, length_m: tuple[float, float], seed: int):
    rng = np.random.default_rng(seed)
    paths = []
    for _ in range(count):
        x = rng.uniform(0, ctx.W)
        y = rng.uniform(0, ctx.H)
        angle = rng.uniform(0, math.tau)
        px, py = fc.walk(rng, x, y, angle, rng.uniform(*length_m) * ctx.P,
                         seg=(2.0, 9.0), dev=0.52, drift=0.14, step=0.55)
        paths.append((px, py, rng.uniform(0.55, 1.0)))
    return fc.crack_mask(ctx, paths, width_px=0.65, taper=True)


def seamless_edges(image, width: int):
    """Crossfade opposite edge strips so authored cells tile without a seam."""
    out = np.asarray(image, np.float32).copy()
    width = min(width, out.shape[0] // 8, out.shape[1] // 8)
    for axis in (1, 0):
        for i in range(width):
            left = np.take(out, i, axis=axis).copy()
            right = np.take(out, -(i + 1), axis=axis).copy()
            t = (i / max(1, width - 1)) ** 0.75
            average = (left + right) * 0.5
            a = average * (1.0 - t) + left * t
            b = average * (1.0 - t) + right * t
            index_a = [slice(None)] * out.ndim
            index_b = [slice(None)] * out.ndim
            index_a[axis] = i
            index_b[axis] = -(i + 1)
            out[tuple(index_a)] = a
            out[tuple(index_b)] = b
    return out


def quantized_seam_edges(path: Path):
    """Make opposite boundary texels byte-identical after 8-bit quantization.

    The float crossfade above can still quantize to adjacent byte values when
    deterministic dithering picks different noise at opposite edges. Average
    those paired edge texels after encoding; the adjustment is at most one
    byte and brings the manifest's measured wrap-gradient down to zero.
    """
    with Image.open(path) as image:
        pixels = np.asarray(image).copy()
        mode = image.mode
    dtype = pixels.dtype
    left_right = ((pixels[:, 0].astype(np.uint16) + pixels[:, -1].astype(np.uint16) + 1) // 2).astype(dtype)
    pixels[:, 0] = left_right
    pixels[:, -1] = left_right
    top_bottom = ((pixels[0, :].astype(np.uint16) + pixels[-1, :].astype(np.uint16) + 1) // 2).astype(dtype)
    pixels[0, :] = top_bottom
    pixels[-1, :] = top_bottom
    Image.fromarray(pixels, mode=mode).save(path, compress_level=6)


def write_maps(name: str, albedo, height, roughness, tile_m: float, metal=0.0):
    height = np.asarray(height, np.float32)
    normal = fc.normal_map(height, tile_m / SIZE, strength=0.82)
    normal = np.clip(normal * 0.5 + 0.5, 0, 1)
    # AO derives from shared recess masks and material relief rather than a
    # camera-dependent bake, so every map remains repeatable and tileable.
    # Heights are in metres, not unit Gaussian noise. Feeding them to to01
    # made AO nearly constant (~0.895). Use the existing periodic, physical
    # height-difference AO instead; G roughness and B metallic stay unchanged.
    ao = np.clip(fc.ao_map(height, tile_m / SIZE, strength=1.2), 0.72, 1.0)
    orm = np.stack([ao, np.clip(roughness, 0.0, 1.0), np.full_like(ao, metal)], axis=-1)
    paths = {
        'albedo': OUT / f'{name}_albedo.png',
        'normal': OUT / f'{name}_normal.png',
        'orm': OUT / f'{name}_orm.png',
    }
    # Course-based stone and roof palettes can put unlike cells across a tile
    # boundary; periodic blending removes that authored seam while retaining
    # the hand-painted variation a short distance inside the tile.
    albedo = seamless_edges(np.clip(albedo, 0, 1), 40)
    normal = seamless_edges(np.clip(normal, 0, 1), 16)
    orm = seamless_edges(np.clip(orm, 0, 1), 16)
    fc.save_png(paths['albedo'], albedo, dither=True)
    fc.save_png(paths['normal'], normal, dither=False)
    fc.save_png(paths['orm'], orm, dither=True)
    for path in paths.values():
        quantized_seam_edges(path)
    return {
        'name': name,
        'size': [SIZE, SIZE],
        'tileable_seam_score': {k: round(float(fc.seam_score(np.asarray(Image.open(p)).astype(np.float32) / 255.0)), 4)
                                for k, p in paths.items()},
        'files': {k: {'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                      'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for k, p in paths.items()},
    }


def stone_wall():
    ctx = fc.Ctx('stone-wall-warm-r5', (SIZE, SIZE), 2.4)
    rng = ctx.rng
    row_heights = rng.uniform(105, 155, 11)
    rects = fc.courses(SIZE, SIZE, rng, row_heights, (170, 480), 44)
    field = fc.RectField(ctx, rects, joint_px=7.0, radius_px=2.3, warp_px=1.2,
                         warp_sigma_px=38.0, radius_jitter=0.50, joint_jitter=0.26,
                         fine_warp_px=0.45, fine_sigma_px=7.0)
    neighbors = fc.adjacency(field.eid, field.n, gap=5)
    colors, _ = fc.assign_palette(field.n, STONE_PALETTE, rng, neighbors,
                                  jitter=(0.008, 0.035, 0.045))
    cell = colors[field.eid]
    face = fc.smoothstep(-0.3, 2.0, field.d)
    interior_noise = ctx.fbm(0.035, octaves=5, gain=0.54)
    pores = ctx.fbm(0.008, octaves=4, gain=0.48)
    rim = np.exp(-np.maximum(field.d, 0) / 3.5) * face
    weather = np.clip(0.52 + 0.28 * interior_noise + 0.10 * pores, 0.18, 0.92)
    chips = fc.smoothstep(0.82, 0.98, ctx.fbm(0.055, octaves=4)) * face
    albedo = cell * (0.91 + 0.11 * weather[..., None])
    albedo *= (1.0 + 0.13 * rim[..., None])
    albedo = fc.mix(albedo, (0.37, 0.40, 0.31), chips * 0.30)
    cracks = crack_field(ctx, 24, (0.045, 0.16), 10421)
    albedo = fc.mix(albedo, (0.27, 0.26, 0.23), cracks * 0.7)
    joint = 1.0 - face
    height = face * (0.008 + 0.0035 * interior_noise + 0.0012 * pores) - joint * 0.0015
    height -= chips * 0.0025 + cracks * 0.002
    rough = np.clip(0.78 + 0.10 * fc.to01(pores) + 0.12 * joint, 0.68, 1.0)
    return write_maps('stone_wall_warm', albedo, height, rough, 2.4)


def plaster():
    ctx = fc.Ctx('plaster-cream-r5', (SIZE, SIZE), 3.0)
    macro = ctx.fbm(0.21, octaves=5, gain=0.52)
    trowel = ctx.fbm(0.035, octaves=4, gain=0.42, sigma_x_m=0.42, angle=0.14)
    fine = ctx.fbm(0.004, octaves=4, gain=0.48)
    stain_cloud = fc.to01(ctx.fbm(0.68, octaves=4, gain=0.52))
    runoff = fc.to01(ctx.fbm(0.24, octaves=5, gain=0.50,
                             sigma_x_m=0.045, angle=0.0))
    height = 0.0014 * macro + 0.0010 * trowel + 0.00035 * fine
    albedo = np.empty((SIZE, SIZE, 3), np.float32)
    base = np.asarray((0.86, 0.77, 0.62), np.float32)
    variation = 0.90 + 0.09 * fc.to01(macro) + 0.025 * trowel + 0.018 * fine
    albedo[:] = base[None, None, :] * variation[..., None]
    hairline = crack_field(ctx, 18, (0.10, 0.42), 27502)
    wear = fc.smoothstep(0.84, 0.98, ctx.fbm(0.027, octaves=4))
    damp_stain = fc.smoothstep(0.63, 0.91, runoff) * (0.28 + 0.72 * fc.smoothstep(0.43, 0.84, stain_cloud))
    broad_age = fc.smoothstep(0.72, 0.96, stain_cloud) * 0.10
    # Narrow, periodic runoff streaks and diffuse age keep the plaster warm;
    # they remain subdued enough to read as limewash rather than dark stone.
    albedo = fc.mix(albedo, (0.42, 0.37, 0.30), damp_stain * 0.19)
    albedo = fc.mix(albedo, (0.70, 0.62, 0.49), broad_age)
    albedo = fc.mix(albedo, (0.37, 0.33, 0.26), hairline * 0.48)
    albedo = fc.mix(albedo, (0.66, 0.60, 0.50), wear * 0.13)
    height -= hairline * 0.0018 + wear * 0.0006 + damp_stain * 0.00035
    rough = np.clip(0.85 + 0.10 * fc.to01(fine) + damp_stain * 0.035, 0.78, 1.0)
    return write_maps('plaster_cream', albedo, height, rough, 3.0)


def timber():
    ctx = fc.Ctx('timber-dark-r5', (SIZE, SIZE), 2.0)
    rng = ctx.rng
    rects = fc.courses(SIZE, SIZE, rng, rng.uniform(82, 128, 13), (210, 560), 36)
    field = fc.RectField(ctx, rects, joint_px=4.0, radius_px=1.4, warp_px=0.55,
                         warp_sigma_px=45.0, radius_jitter=0.35, joint_jitter=0.2,
                         fine_warp_px=0.2, fine_sigma_px=10.0)
    colors, _ = fc.assign_palette(field.n, WOOD_PALETTE, rng,
                                  fc.adjacency(field.eid, field.n, gap=4), jitter=(0.008, 0.04, 0.05))
    face = fc.smoothstep(-0.3, 1.7, field.d)
    grain = ctx.fbm(0.035, octaves=5, gain=0.54, sigma_x_m=1.8)
    fine = ctx.fbm(0.005, octaves=4, gain=0.48, sigma_x_m=0.36)
    ring = np.exp(-np.maximum(field.d, 0) / 2.0) * face
    albedo = colors[field.eid] * (0.91 + 0.14 * fc.to01(grain)[..., None] + 0.04 * fine[..., None])
    albedo *= (1.0 + 0.12 * ring[..., None])
    # Peg and knot detail repeats seamlessly because distances wrap on the tile.
    knots = np.zeros((SIZE, SIZE), np.float32)
    yy, xx = fc.grid(SIZE, SIZE)
    for i in range(8):
        kx, ky = rng.uniform(0, SIZE, 2)
        dx, dy = fc.wrapd(xx - kx, SIZE), fc.wrapd(yy - ky, SIZE)
        rx, ry = rng.uniform(4, 9), rng.uniform(8, 16)
        rr = np.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
        knots = np.maximum(knots, np.exp(-((rr - 0.72) / 0.13) ** 2))
    cracks = crack_field(ctx, 13, (0.06, 0.26), 51788)
    albedo = fc.mix(albedo, (0.075, 0.035, 0.016), np.maximum(knots * 0.22, cracks * 0.50))
    height = face * (0.002 + 0.0015 * grain + 0.0006 * fine) - (1 - face) * 0.001
    height -= cracks * 0.0012 + knots * 0.0005
    rough = np.clip(0.68 + 0.18 * fc.to01(fine) + 0.16 * (1 - face), 0.58, 1.0)
    return write_maps('timber_dark', albedo, height, rough, 2.0)


def roof(name: str, palette):
    ctx = fc.Ctx(name + '-r5', (SIZE, SIZE), 2.2)
    rng = ctx.rng
    rects = fc.courses(SIZE, SIZE, rng, rng.uniform(118, 165, 9), (150, 310), 40)
    field = fc.RectField(ctx, rects, joint_px=4.0, radius_px=3.0, warp_px=0.55,
                         warp_sigma_px=58.0, radius_jitter=0.40, joint_jitter=0.24,
                         fine_warp_px=0.25, fine_sigma_px=12.0)
    colors, _ = fc.assign_palette(field.n, palette, rng,
                                  fc.adjacency(field.eid, field.n, gap=5), jitter=(0.006, 0.035, 0.05))
    face = fc.smoothstep(-0.4, 2.0, field.d)
    fine = ctx.fbm(0.006, octaves=4, gain=0.50)
    medium = ctx.fbm(0.028, octaves=4, gain=0.50)
    edge_wear = np.exp(-np.maximum(field.d, 0) / 4.2) * face
    chips = fc.smoothstep(0.86, 0.98, ctx.fbm(0.075, octaves=4)) * face
    moss = fc.smoothstep(0.72, 0.94, ctx.fbm(0.16, octaves=4)) * face
    albedo = colors[field.eid] * (0.94 + 0.06 * medium[..., None] + 0.025 * fine[..., None])
    albedo *= (1.0 + 0.12 * edge_wear[..., None])
    if 'green' in name:
        albedo = fc.mix(albedo, (0.08, 0.20, 0.105), moss * 0.30)
    else:
        albedo = fc.mix(albedo, (0.20, 0.23, 0.19), moss * 0.16)
    albedo = fc.mix(albedo, (0.36, 0.33, 0.28), chips * 0.35)
    # Pitted slate/terracotta faces and small broken edges are normal detail,
    # not extra polygons, keeping the runtime asset light.
    height = face * (0.003 + 0.0017 * medium + 0.00055 * fine) - (1 - face) * 0.0012
    height -= chips * 0.0014 + moss * 0.0007
    rough = np.clip(0.57 + 0.20 * fc.to01(medium) + 0.18 * moss, 0.46, 0.96)
    return write_maps(name, albedo, height, rough, 2.2)


def paving(name: str, tile_m: float, palette, cells: int, seed: int):
    ctx = fc.Ctx(name + '-r5', (SIZE, SIZE), tile_m)
    rng = ctx.rng
    if name in ('plaza_flagstone', 'paver_surface'):
        # Plaza slabs use an orderly running bond; smaller street pavers use
        # tighter, brick-like courses. This makes them visibly distinct from
        # the rounded Voronoi cobbles used on footpaths.
        row_count = 10 if name == 'plaza_flagstone' else 14
        row_heights = rng.uniform(0.86, 1.14, row_count)
        if name == 'plaza_flagstone':
            length_range, joint_px, min_stagger = (SIZE * 0.15, SIZE * 0.37), 4.2, 36
            radius_px, warp_px = 2.0, 0.55
        else:
            length_range, joint_px, min_stagger = (SIZE * 0.18, SIZE * 0.36), 3.1, 42
            radius_px, warp_px = 1.4, 0.35
        rects = fc.courses(SIZE, SIZE, rng, row_heights, length_range, min_stagger)
        field = fc.RectField(ctx, rects, joint_px=joint_px, radius_px=radius_px,
                             warp_px=warp_px, warp_sigma_px=58.0,
                             radius_jitter=0.28, joint_jitter=0.20,
                             fine_warp_px=0.25, fine_sigma_px=10.0)
    else:
        pts = []
        pitch = SIZE / cells
        for iy in range(cells):
            for ix in range(cells):
                x = (ix + 0.5 + 0.28 * (iy % 2)) * pitch + rng.uniform(-0.18, 0.18) * pitch
                y = (iy + 0.5) * pitch + rng.uniform(-0.18, 0.18) * pitch
                pts.append((x % SIZE, y % SIZE))
        is_cobble = name == 'cobble_path'
        field = fc.VoronoiField(ctx, pts, k=8, smooth_px=2.6 if is_cobble else 0.0,
                                warp_px=2.0 if is_cobble else 1.1,
                                warp_sigma_px=48.0, aniso=(1.0, 1.0))
    neighbors = fc.adjacency(field.eid, field.n, gap=5)
    colors, _ = fc.assign_palette(field.n, palette, rng, neighbors,
                                  jitter=(0.006, 0.035, 0.045))
    joint = fc.smoothstep(-0.5, 3.8 if name != 'cobble_path' else 5.0, field.d)
    fine = ctx.fbm(0.016 if name != 'cobble_path' else 0.025, octaves=5, gain=0.52)
    grit = ctx.fbm(0.0038, octaves=4, gain=0.48)
    rim = np.exp(-np.maximum(field.d, 0.0) / 5.0) * joint
    chips = fc.smoothstep(0.88, 0.99, ctx.fbm(0.052, octaves=4)) * joint
    albedo = colors[field.eid] * (0.91 + 0.12 * fc.to01(fine)[..., None] + 0.025 * grit[..., None])
    albedo *= (1.0 + 0.12 * rim[..., None])
    albedo = fc.mix(albedo, (0.31, 0.30, 0.27), chips * 0.30)
    if name == 'cobble_path':
        moss = fc.smoothstep(0.74, 0.96, fc.to01(ctx.fbm(0.13, octaves=4)))
        moss *= (1.0 - joint) * 0.82 + rim * 0.10
        albedo = fc.mix(albedo, (0.18, 0.24, 0.14), moss * 0.42)
        cracks = crack_field(ctx, 8, (0.025, 0.075), seed)
    else:
        moss = np.zeros_like(joint)
        cracks = crack_field(ctx, 18, (0.04, 0.15), seed)
    albedo = fc.mix(albedo, (0.25, 0.26, 0.27), cracks * (0.42 if name == 'plaza_flagstone' else 0.55))
    height = joint * (0.004 + 0.0017 * fine + 0.0007 * grit) - (1.0 - joint) * 0.0013
    height -= chips * 0.0017 + cracks * 0.0014 + moss * 0.00035
    rough = np.clip(0.76 + 0.13 * fc.to01(grit) + 0.15 * (1.0 - joint) - moss * 0.04, 0.62, 1.0)
    return write_maps(name, albedo, height, rough, tile_m)


def paver_surface():
    """Joint-free stone faces for already-modelled radial plaza slabs.

    The mesh supplies the slab boundaries and bevels. A second miniature
    brick layout in this map obscured those authored construction lines.
    Reuse the foundry's periodic noise, cracks and paired PBR map pipeline.
    """
    tile = 2.0
    ctx = fc.Ctx('paver_surface-r5', (SIZE, SIZE), tile)
    palette = np.asarray([(0.60, 0.56, 0.49), (0.69, 0.64, 0.56),
                          (0.75, 0.69, 0.60), (0.53, 0.55, 0.54)], np.float32)
    macro = ctx.fbm(0.18, octaves=4, gain=0.48)
    fine = ctx.fbm(0.016, octaves=5, gain=0.52)
    grit = ctx.fbm(0.0038, octaves=4, gain=0.48)
    stone_color = fc.mix(palette[0], palette[2], fc.to01(macro) * 0.62)
    cool_mineral = fc.smoothstep(0.76, 0.96, fc.to01(ctx.fbm(0.085, octaves=4)))
    albedo = fc.mix(stone_color, palette[3], cool_mineral * 0.18)
    albedo *= (0.95 + 0.065 * fc.to01(fine)[..., None] + 0.014 * grit[..., None])
    scars = crack_field(ctx, 6, (0.03, 0.08), 0x5014)
    albedo = fc.mix(albedo, (0.31, 0.30, 0.27), scars * 0.30)
    # Sub-millimetre grain and sparse shallow scars; no mortar or slab joints.
    height = 0.00045 * fine + 0.00022 * grit - scars * 0.0007
    rough = np.clip(0.79 + 0.10 * fc.to01(grit) + scars * 0.035, 0.76, 0.95)
    return write_maps('paver_surface', albedo, height, rough, tile)


def grass():
    tile = 6.0
    ctx = fc.Ctx('grass-ground-r5', (SIZE, SIZE), tile)
    macro = ctx.fbm(0.82, octaves=5, gain=0.55)
    meso = ctx.fbm(0.19, octaves=5, gain=0.52)
    blade = ctx.fbm(0.008, octaves=5, gain=0.52, sigma_x_m=0.12, angle=0.08)
    sparkle = ctx.fbm(0.0022, octaves=4, gain=0.48, sigma_x_m=0.015, angle=0.02)
    damp_field = fc.to01(ctx.fbm(0.55, octaves=4))
    damp = fc.smoothstep(0.60, 0.88, damp_field)
    dry = fc.smoothstep(0.77, 0.96, fc.to01(ctx.fbm(0.38, octaves=4))) * (1.0 - damp * 0.58)
    bare_field = fc.to01(ctx.fbm(0.92, octaves=4, gain=0.50))
    bare_soil = fc.smoothstep(0.935, 0.992, bare_field)
    bare_edge = np.clip(fc.blur(bare_soil, 3.2) - bare_soil, 0, 1)
    base = np.zeros((SIZE, SIZE, 3), np.float32)
    factor = 0.82 + 0.20 * fc.to01(macro) + 0.15 * fc.to01(meso) + 0.075 * blade + 0.032 * sparkle
    base[:] = np.asarray((0.22, 0.41, 0.125), np.float32)[None, None, :] * factor[..., None]
    base = fc.mix(base, (0.075, 0.205, 0.105), damp * 0.43)
    base = fc.mix(base, (0.46, 0.365, 0.115), dry * 0.20)
    base = fc.mix(base, (0.15, 0.12, 0.065), bare_soil * 0.48)
    base = fc.mix(base, (0.37, 0.29, 0.105), bare_edge * 0.24)
    # Leaf strokes add a readable grass scale at close range. Every walk wraps
    # through periodic splatting, and the fixed material RNG makes the tuft
    # layout repeatable from one build to the next.
    rng = ctx.rng
    centers_x = rng.uniform(0, SIZE, 520)
    centers_y = rng.uniform(0, SIZE, 520)
    leaf_paths, bright_paths = [], []
    for cx, cy in zip(centers_x, centers_y):
        start_angle = rng.uniform(0, math.tau)
        for leaf in range(5):
            angle = start_angle + leaf * math.tau / 5 + rng.normal(0, 0.13)
            length = rng.uniform(SIZE * 0.010, SIZE * 0.026)
            px, py = fc.walk(rng, cx, cy, angle, length, seg=(2.5, 7.0),
                             dev=0.12, drift=0.055, step=0.9)
            strength = rng.uniform(0.50, 0.95)
            path = (px, py, strength)
            leaf_paths.append(path)
            if leaf in (1, 3):
                bright_paths.append(path)
    blades = fc.crack_mask(ctx, leaf_paths, width_px=1.05, taper=True)
    blade_lights = fc.crack_mask(ctx, bright_paths, width_px=0.72, taper=True)
    base = fc.mix(base, (0.075, 0.235, 0.085), blades * 0.31)
    base = fc.mix(base, (0.47, 0.59, 0.19), blade_lights * 0.23)

    def flower_layer(count: int, seed_offset: int):
        flower_rng = np.random.default_rng(ctx.seed + seed_offset)
        fx = flower_rng.uniform(0, SIZE, count)
        fy = flower_rng.uniform(0, SIZE, count)
        radius = flower_rng.uniform(2.2, 4.0, count)
        angles = np.arange(6, dtype=np.float32) * (math.tau / 6)
        px = fx[:, None] + np.cos(angles)[None, :] * radius[:, None]
        py = fy[:, None] + np.sin(angles)[None, :] * radius[:, None]
        weights = np.full(px.size, 0.72, np.float32)
        petals = fc.splat(ctx.shape, px.ravel(), py.ravel(), weights)
        petals = np.clip(fc.blur(petals, 0.78), 0, 1)
        centers = fc.splat(ctx.shape, fx, fy, np.full(count, 0.95, np.float32))
        centers = np.clip(fc.blur(centers, 0.70), 0, 1)
        return petals, centers

    petals, centers = flower_layer(220, 0xF10A)
    base = fc.mix(base, (0.91, 0.84, 0.68), petals * 0.56)
    base = fc.mix(base, (0.96, 0.67, 0.16), centers * 0.62)
    gold, gold_centers = flower_layer(72, 0xF10B)
    base = fc.mix(base, (0.93, 0.70, 0.19), gold * 0.58)
    base = fc.mix(base, (0.99, 0.86, 0.34), gold_centers * 0.54)
    lilac, lilac_centers = flower_layer(54, 0xF10C)
    base = fc.mix(base, (0.66, 0.51, 0.81), lilac * 0.52)
    base = fc.mix(base, (0.93, 0.78, 0.32), lilac_centers * 0.44)

    height = 0.0015 * macro + 0.0013 * meso + 0.00055 * blade + 0.00025 * sparkle
    height += blades * 0.00042 + blade_lights * 0.00022 + bare_soil * 0.0003
    height += petals * 0.00035 + gold * 0.00035 + lilac * 0.00035
    rough = np.clip(0.90 + 0.07 * fc.to01(meso) + 0.06 * fc.to01(sparkle) - damp * 0.065, 0.78, 1.0)
    return write_maps('grass_ground', base, height, rough, tile)


def cliff_rock():
    ctx = fc.Ctx('cliff-rock-r5', (SIZE, SIZE), 9.0)
    strata = ctx.fbm(0.50, octaves=5, gain=0.55, sigma_x_m=4.8, angle=0.10)
    broken = ctx.fbm(0.12, octaves=5, gain=0.52)
    grit = ctx.fbm(0.012, octaves=4, gain=0.48)
    band = 0.5 + 0.5 * np.sin((np.arange(SIZE, dtype=np.float32)[:, None] / SIZE * 11.0 + broken) * math.tau)
    chips = fc.smoothstep(0.86, 0.99, ctx.fbm(0.10, octaves=4))
    shade = 0.78 + 0.14 * fc.to01(strata) + 0.10 * fc.to01(broken) + 0.04 * grit
    base = np.empty((SIZE, SIZE, 3), np.float32)
    base[:] = np.asarray((0.43, 0.35, 0.27), np.float32)[None, None, :] * shade[..., None]
    base = fc.mix(base, (0.60, 0.47, 0.33), band * 0.22)
    base = fc.mix(base, (0.24, 0.23, 0.21), chips * 0.16)
    height = 0.009 * strata + 0.004 * broken + 0.0015 * grit - chips * 0.004
    rough = np.clip(0.83 + 0.12 * fc.to01(grit), 0.78, 1.0)
    return write_maps('cliff_rock', base, height, rough, 9.0)


def main():
    if SIZE < 256 or SIZE > 2048 or SIZE & (SIZE - 1):
        raise ValueError('CITY_TEXTURE_SIZE must be a power of two from 256 through 2048')
    records = [stone_wall(), plaster(), timber(), grass(), cliff_rock()]
    for name, palette in ROOFS.items():
        records.append(roof(name, palette))
    records.extend([
        paving('stone_trim_carved', 1.6, [(0.72, 0.66, 0.55), (0.79, 0.73, 0.62),
                (0.84, 0.78, 0.68), (0.66, 0.63, 0.58)], 22, 0x5011),
        paving('stone_foundation', 2.4, [(0.39, 0.39, 0.37), (0.46, 0.45, 0.42),
                (0.52, 0.49, 0.43), (0.34, 0.36, 0.36)], 14, 0x5012),
        paving('plaza_flagstone', 4.0, [(0.67, 0.57, 0.43), (0.76, 0.66, 0.51),
                (0.83, 0.73, 0.58), (0.62, 0.61, 0.56)], 10, 0x5013),
        paver_surface(),
        paving('stone_accent_bluegrey', 2.0, STONE_PALETTE_COOL, 16, 0x5015),
        paving('cobble_path', 2.6, [(0.43, 0.41, 0.37), (0.52, 0.49, 0.43),
                (0.60, 0.56, 0.48), (0.41, 0.44, 0.44)], 18, 0x5016),
    ])
    receipt = {
        'schema': 'aetherfield.texture-foundry/1',
        'revision': 'r5-foundry-3',
        'generator': 'assets/blender/city_r5/foundry/build_materials_r5.py',
        'library': 'assets/blender/city_r5/foundry/fcore.py',
        'license': 'Original procedural images; no third-party scans or reference pixels.',
        'size': [SIZE, SIZE],
        'materials': records,
    }
    path = OUT / 'foundry-manifest.json'
    path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': path.as_posix(), 'materials': len(records),
                      'texture_files': len(records) * 3,
                      'total_bytes': sum(x['files'][k]['bytes'] for x in records for k in x['files']),
                      'max_seam_score': max(max(x['tileable_seam_score'].values()) for x in records)}, indent=2))


if __name__ == '__main__':
    main()
