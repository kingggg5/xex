"""Generate deterministic, seamless painted stone PBR atlases with system Python.

  python np_stone_texture.py --out DIR [--revision 1]

Each atlas is 1024 x 1024 RGB and tiles over a 2.5 m repeat (about 409 source
pixels per metre). Direction convention: U increases right, V increases up;
the normal texture is tangent-space OpenGL +Y, with RGB = +U, +V, outward.
ORM is R = occlusion, G = roughness, B = metallic. The emissive image is an
RGB cyan crystal mask; black means no emission. All fields are periodic
integer-frequency functions or wrap-indexed cells, so opposite edges meet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


SIZE = 1024
REPEAT_METRES = 2.5
PIXELS_PER_METRE = SIZE / REPEAT_METRES
SCHEMA = "xexoria.stone-texture-receipt/1"


def smoothstep(a: float, b: float, value: np.ndarray) -> np.ndarray:
    t = np.clip((value - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _rgb(hex_colour: str) -> np.ndarray:
    raw = hex_colour.lstrip("#")
    return np.array([int(raw[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def _cell_field(size: int, cells_x: int, cells_y: int, rng: np.random.Generator):
    """Return nearest/second-nearest jittered periodic cell data."""
    xs = (np.arange(size, dtype=np.float32) + 0.5) / size * cells_x
    ys = (np.arange(size, dtype=np.float32) + 0.5) / size * cells_y
    xx, yy = np.meshgrid(xs, ys)
    fx, fy = xx - np.floor(xx), yy - np.floor(yy)
    bx, by = np.floor(xx).astype(np.int32), np.floor(yy).astype(np.int32)

    jx = rng.uniform(0.24, 0.76, (cells_y, cells_x)).astype(np.float32)
    jy = rng.uniform(0.24, 0.76, (cells_y, cells_x)).astype(np.float32)
    near = np.full((size, size), np.inf, dtype=np.float32)
    second = near.copy()
    cell = np.zeros((size, size), dtype=np.int32)
    local_x = np.zeros((size, size), dtype=np.float32)
    local_y = np.zeros((size, size), dtype=np.float32)
    for oy in (-1, 0, 1):
        iy = np.mod(by + oy, cells_y)
        for ox in (-1, 0, 1):
            ix = np.mod(bx + ox, cells_x)
            dx = ox + jx[iy, ix] - fx
            dy = oy + jy[iy, ix] - fy
            # Mild anisotropy makes broad fractured patches feel layered.
            distance = dx * dx * 1.08 + dy * dy * 0.92
            is_near = distance < near
            second = np.where(is_near, near, np.minimum(second, distance))
            near = np.where(is_near, distance, near)
            cell = np.where(is_near, iy * cells_x + ix, cell)
            local_x = np.where(is_near, dx, local_x)
            local_y = np.where(is_near, dy, local_y)
    return near, second, cell, local_x, local_y, jx, jy


def _periodic_detail(u: np.ndarray, v: np.ndarray, revision: int) -> np.ndarray:
    """Low-amplitude broad variation from integer-frequency periodic waves."""
    phase = (revision % 997) * 0.013
    return (
        0.46 * np.sin(2 * np.pi * (3 * u + 2 * v) + phase)
        + 0.31 * np.cos(2 * np.pi * (5 * u - 3 * v) + 1.2 + phase * 0.7)
        + 0.23 * np.sin(2 * np.pi * (2 * u - 7 * v) + 2.1 - phase * 0.4)
    ).astype(np.float32)


def _write_rgb(path: Path, image: np.ndarray) -> dict:
    quantized = np.clip(np.rint(image), 0, 255).astype(np.uint8)
    Image.fromarray(quantized, mode="RGB").save(path, format="PNG", optimize=True)
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "resolution": [int(quantized.shape[1]), int(quantized.shape[0])],
        "mean_rgb": [round(float(x), 3) for x in quantized.mean(axis=(0, 1))],
        "std_rgb": [round(float(x), 3) for x in quantized.std(axis=(0, 1))],
        "min_rgb": [int(x) for x in quantized.min(axis=(0, 1))],
        "max_rgb": [int(x) for x in quantized.max(axis=(0, 1))],
    }


def paint_atlas(out_dir: Path, family: str, revision: int) -> dict[str, dict]:
    ruin = family == "ruin"
    base = _rgb("#b5ab98" if ruin else "#a8a398")
    rng = np.random.default_rng(2401 + revision * 31 + (17 if ruin else 0))
    cells_x, cells_y = (7, 6) if ruin else (4, 5)
    near, second, cell, lx, ly, _, _ = _cell_field(SIZE, cells_x, cells_y, rng)
    cell_variation = rng.uniform(-0.115, 0.105, cells_x * cells_y).astype(np.float32)[cell]
    cell_warmth = rng.uniform(-1.0, 1.0, cells_x * cells_y).astype(np.float32)[cell]
    cell_height = rng.uniform(-1.0, 1.0, cells_x * cells_y).astype(np.float32)[cell]

    axis = (np.arange(SIZE, dtype=np.float32) + 0.5) / SIZE
    u, v = np.meshgrid(axis, axis)
    broad = _periodic_detail(u, v, revision + (7 if ruin else 0))
    # The distance gap is narrow around the polygon boundary and periodic at the seam.
    edge_gap = np.sqrt(np.maximum(second, 0.0)) - np.sqrt(np.maximum(near, 0.0))
    cavity = 1.0 - smoothstep(0.018, 0.075 if ruin else 0.085, edge_gap)
    edge_lit = smoothstep(0.08, 0.19, edge_gap) * (1.0 - smoothstep(0.28, 0.39, edge_gap))
    # Incomplete weathering seams, not a continuous paving/cobble grid.
    cavity *= smoothstep(-0.08, 0.48, broad * 0.72 + cell_height * 0.28)
    edge_lit *= smoothstep(-0.12, 0.28, ly - lx * 0.28)
    if ruin:
        cavity *= 0.34
        edge_lit *= 0.5

    # A restrained face facet and painted strata give the broad angular patchwork depth.
    facet = np.tanh((lx * (0.68 + 0.18 * cell_height) + ly * (0.42 - 0.14 * cell_height)) * 2.1)
    strata_phase = 2 * np.pi * (4 * u + 3 * v) + 0.5 * broad
    strata = np.maximum(0.0, np.cos(strata_phase)) ** 10
    shade = cell_variation * 0.30 + broad * 0.035 + facet * 0.028
    shade -= cavity * (0.08 if ruin else 0.12)
    shade += edge_lit * 0.025
    shade += strata * (0.014 if ruin else 0.007)
    # Warm and cool mineral shifts stay close to the supplied warm-grey palette.
    rgb = base[None, None, :] * (1.0 + shade[..., None])
    cool = np.clip(-cell_warmth * 0.06, 0.0, 0.07)
    warm = np.clip(cell_warmth * 0.055, 0.0, 0.06)
    rgb[..., 0] += warm * 16.0 - cool * 10.0
    rgb[..., 1] += warm * 4.0 - cool * 3.0
    rgb[..., 2] += cool * 16.0 - warm * 8.0
    shadow_colour = _rgb("#5d6470")
    highlight_colour = _rgb("#c1b9a8")
    rgb = rgb * (1.0 - cavity[..., None] * 0.18) + shadow_colour * (cavity[..., None] * 0.18)
    rgb = rgb * (1.0 - edge_lit[..., None] * 0.12) + highlight_colour * (edge_lit[..., None] * 0.12)

    height = (cell_height * 0.001 + facet * 0.003 - cavity * 0.003 + edge_lit * 0.001).astype(np.float32)
    if ruin:
        # Fine, shallow chisel marks: all wave frequencies are integer, so the strokes tile.
        stroke_wave = np.sin(2 * np.pi * (29 * u + 12 * v) + 0.4 * broad)
        stroke_gate = smoothstep(0.72, 0.94, np.sin(2 * np.pi * (3 * u - 2 * v) + 0.8))
        strokes = np.maximum(0.0, stroke_wave) ** 18 * stroke_gate
        rgb *= (1.0 - strokes[..., None] * 0.065)
        rgb += edge_lit[..., None] * strokes[..., None] * 4.0
        height += strokes * 0.003

    # Small directional crystal flecks share periodic coordinates and remain a mask only.
    crystal_a = np.sin(2 * np.pi * (7 * u + 4 * v) + 0.25 * broad)
    crystal_b = np.cos(2 * np.pi * (5 * u - 8 * v) + 0.3)
    crystal = smoothstep(0.91, 0.99, crystal_a * crystal_b) * (1.0 - cavity * 0.65)
    if ruin:
        crystal *= 0.55

    # Periodic central differences, with V pointing up although PNG rows point down.
    du = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * (0.5 * SIZE)
    dv = -(np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * (0.5 * SIZE)
    nx, ny, nz = -du * 1.35, -dv * 1.35, np.ones_like(height)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack(((nx / norm + 1) * 127.5,
                       (ny / norm + 1) * 127.5,
                       (nz / norm + 1) * 127.5), axis=-1)

    ao = np.clip(1.0 - cavity * 0.27 - strata * (0.018 if ruin else 0.0), 0.68, 1.0)
    roughness = np.clip(0.835 + 0.035 * broad + cavity * 0.045 + strata * 0.015, 0.72, 0.93)
    orm = np.stack((ao * 255.0, roughness * 255.0, np.zeros_like(ao)), axis=-1)

    stem = "sm_ruin" if ruin else "sm_stone"
    records = {
        f"{stem}_albedo.png": _write_rgb(out_dir / f"{stem}_albedo.png", rgb),
        f"{stem}_normal.png": _write_rgb(out_dir / f"{stem}_normal.png", normal),
        f"{stem}_orm.png": _write_rgb(out_dir / f"{stem}_orm.png", orm),
    }
    if not ruin:
        emission = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
        glow = np.clip(0.35 + 0.50 * smoothstep(-0.3, 0.8, broad) + 0.10 * crystal, 0, 0.95)
        emission[..., 0] = glow * 39.0
        emission[..., 1] = glow * 185.0
        emission[..., 2] = glow * 230.0
        emission = emission.reshape(512, 2, 512, 2, 3).mean(axis=(1, 3))
        records["sm_stone_emissive.png"] = _write_rgb(out_dir / "sm_stone_emissive.png", emission)
    return records


def generate(out_dir: str | Path, revision: int = 1) -> dict:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    artifacts.update(paint_atlas(out_path, "stone", revision))
    artifacts.update(paint_atlas(out_path, "ruin", revision))
    receipt = {
        "schema": SCHEMA,
        "revision": revision,
        "resolution": [SIZE, SIZE],
        "emissive_resolution": [512, 512],
        "repeat_metres": REPEAT_METRES,
        "source_pixels_per_metre": PIXELS_PER_METRE,
        "normal_convention": "OpenGL +Y tangent space; RGB = +U, +V, outward",
        "orm_channels": {"r": "ambient occlusion", "g": "roughness", "b": "metallic"},
        "families": {
            "stone": {"base": "#a8a398", "highlight": "#c1b9a8", "shadow": "#5d6470"},
            "ruin": {"base": "#b5ab98", "finish": "subtle worked chisel strokes"},
        },
        "artifacts": artifacts,
    }
    receipt_path = out_path / "stone_texture_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="directory for texture PNGs and receipt")
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    receipt = generate(args.out, args.revision)
    print(json.dumps({"output": str(args.out), "revision": args.revision,
                      "textures": len(receipt["artifacts"]),
                      "receipt": str(args.out / "stone_texture_receipt.json")}, indent=2))


if __name__ == "__main__":
    main()
