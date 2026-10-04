"""Generate small, tileable, original city surface textures with Pillow/NumPy.

Run once before build_reference_city_r3.py. The resulting PNGs are local,
source-controlled game assets; this script makes no network or paid API calls.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets/models/reference-city/r3/textures"
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 512


def periodic_noise(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(SIZE, dtype=np.float32) / SIZE
    x, y = np.meshgrid(t, t)
    out = np.zeros((SIZE, SIZE), dtype=np.float32)
    for frequency, amplitude in [(1, 0.10), (2, 0.07), (4, 0.045), (8, 0.028), (16, 0.018), (32, 0.010)]:
        for _ in range(3):
            fx = int(rng.integers(1, frequency + 1))
            fy = int(rng.integers(1, frequency + 1))
            phase = float(rng.random() * np.pi * 2)
            out += amplitude * np.sin(2 * np.pi * fx * x + phase) * np.cos(2 * np.pi * fy * y - phase * 0.7)
    return out


def unit_color(rgb: tuple[int, int, int], intensity: np.ndarray) -> np.ndarray:
    base = np.asarray(rgb, dtype=np.float32)[None, None, :]
    return np.clip(base * intensity[..., None], 0, 255).astype(np.uint8)


def brick_surface(seed: int, base: tuple[int, int, int], rows: int = 8, columns: int = 4):
    noise = periodic_noise(seed)
    xx = np.arange(SIZE)[None, :]
    yy = np.arange(SIZE)[:, None]
    brick_h, brick_w = SIZE // rows, SIZE // columns
    row = yy // brick_h
    shifted_x = (xx + (row % 2) * (brick_w // 2)) % SIZE
    dx = shifted_x % brick_w
    dy = yy % brick_h
    edge = np.minimum(np.minimum(dx, brick_w - dx), np.minimum(dy, brick_h - dy))
    grout = edge < 4
    bevel = np.clip((edge.astype(np.float32) - 3) / 12, 0, 1)
    cell_x = shifted_x // brick_w
    cell_y = row
    variation = 0.91 + 0.10 * np.sin((cell_x + 1) * 13.7 + (cell_y + 2) * 5.1 + seed)
    intensity = (0.86 + noise * 0.48 + bevel * 0.10) * variation
    intensity = np.where(grout, 0.53 + noise * 0.08, intensity)
    height = np.where(grout, 0.36, 0.58 + bevel * 0.22 + noise * 0.09)
    return unit_color(base, intensity), height.astype(np.float32)


def cobble_surface(seed: int, base: tuple[int, int, int]):
    noise = periodic_noise(seed)
    xx = np.arange(SIZE)[None, :]
    yy = np.arange(SIZE)[:, None]
    row_h, stone_w = SIZE // 8, SIZE // 5
    row = yy // row_h
    shifted_x = (xx + (row % 2) * (stone_w // 2)) % SIZE
    dx = shifted_x % stone_w
    dy = yy % row_h
    # Slightly rounded stone edges rather than a perfect rectangular grid.
    ex = np.minimum(dx, stone_w - dx).astype(np.float32)
    ey = np.minimum(dy, row_h - dy).astype(np.float32)
    edge = np.minimum(ex, ey)
    edge += 5.0 * np.sin((dx + dy) * (2 * np.pi / 110.0))
    grout = edge < 5
    cells = np.sin((shifted_x // stone_w + 2) * 11.9 + (row + 1) * 4.3 + seed)
    intensity = 0.79 + noise * 0.44 + cells * 0.055 + np.clip((edge - 5) / 16, 0, 1) * 0.12
    intensity = np.where(grout, 0.47 + noise * 0.06, intensity)
    height = np.where(grout, 0.28, 0.60 + np.clip((edge - 5) / 16, 0, 1) * 0.20 + noise * 0.07)
    return unit_color(base, intensity), height.astype(np.float32)


def plaster_surface(seed: int, base: tuple[int, int, int]):
    noise = periodic_noise(seed)
    xx = np.arange(SIZE, dtype=np.float32)[None, :]
    grain = 0.018 * np.sin(xx * (2 * np.pi / 17.0) + seed)
    intensity = 0.96 + noise * 0.40 + grain
    height = 0.55 + noise * 0.18
    return unit_color(base, intensity), height.astype(np.float32)


def slate_surface(seed: int, base: tuple[int, int, int]):
    noise = periodic_noise(seed)
    xx = np.arange(SIZE, dtype=np.float32)[None, :]
    streaks = 0.025 * np.sin(xx * (2 * np.pi / 37.0) + seed * 0.31)
    intensity = 0.94 + noise * 0.35 + streaks
    height = 0.55 + noise * 0.14 + streaks * 0.7
    return unit_color(base, intensity), height.astype(np.float32)


def wood_surface(seed: int, base: tuple[int, int, int]):
    noise = periodic_noise(seed)
    yy = np.arange(SIZE, dtype=np.float32)[:, None]
    grain = 0.065 * np.sin(yy * (2 * np.pi / 29.0) + np.sin(yy * (2 * np.pi / 113.0) + seed))
    intensity = 0.93 + noise * 0.30 + grain
    height = 0.55 + noise * 0.12 + grain
    return unit_color(base, intensity), height.astype(np.float32)


def grass_surface(seed: int, base: tuple[int, int, int]):
    noise = periodic_noise(seed)
    rng = np.random.default_rng(seed)
    intensity = 0.94 + noise * 0.58
    yy, xx = np.meshgrid(np.arange(SIZE), np.arange(SIZE), indexing="ij")
    # Short, soft blades repeat seamlessly at the tile boundary.
    for _ in range(900):
        x = int(rng.integers(0, SIZE))
        y = int(rng.integers(0, SIZE))
        length = int(rng.integers(2, 8))
        delta = float(rng.uniform(-0.16, 0.20))
        for step in range(length):
            px = (x + int(delta * step * 8)) % SIZE
            py = (y - step) % SIZE
            intensity[py, px] += 0.08 if delta > 0 else -0.09
    intensity = np.clip(intensity, 0.66, 1.23)
    height = 0.52 + noise * 0.10
    return unit_color(base, intensity), height.astype(np.float32)


def water_surface(seed: int, base: tuple[int, int, int]):
    noise = periodic_noise(seed)
    xx = np.arange(SIZE, dtype=np.float32)[None, :]
    yy = np.arange(SIZE, dtype=np.float32)[:, None]
    ripple = 0.035 * np.sin((xx + yy * 0.36) * (2 * np.pi / 42.0) + seed)
    intensity = 0.97 + noise * 0.33 + ripple
    height = 0.55 + noise * 0.05 + ripple * 0.7
    return unit_color(base, intensity), height.astype(np.float32)


def dirt_surface(seed: int, base: tuple[int, int, int]):
    noise = periodic_noise(seed)
    xx = np.arange(SIZE, dtype=np.float32)[None, :]
    yy = np.arange(SIZE, dtype=np.float32)[:, None]
    grit = 0.035 * np.sin((xx + 0.53 * yy) * (2 * np.pi / 8.0) + seed)
    intensity = 0.94 + noise * 0.40 + grit
    height = 0.52 + noise * 0.09 + grit * 0.7
    return unit_color(base, intensity), height.astype(np.float32)


def save_pair(name: str, color: np.ndarray, height: np.ndarray, blur: float = 0.0):
    color_image = Image.fromarray(color, "RGB")
    if blur:
        color_image = color_image.filter(ImageFilter.GaussianBlur(blur))
    color_image.save(OUT / f"{name}.png", optimize=True)
    dx = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    dy = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    nx, ny, nz = -dx * 2.5, -dy * 2.5, np.ones_like(height)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack([(nx / norm + 1) * 127.5, (ny / norm + 1) * 127.5, (nz / norm + 1) * 127.5], axis=-1)
    Image.fromarray(np.clip(normal, 0, 255).astype(np.uint8), "RGB").save(OUT / f"{name}_normal.png", optimize=True)


def main():
    stone, h = brick_surface(31, (190, 183, 163))
    save_pair("stone_limestone", stone, h)
    trim, h = brick_surface(32, (225, 214, 184))
    save_pair("stone_trim", trim, h)
    plaster, h = plaster_surface(41, (224, 211, 178))
    save_pair("plaster_warm", plaster, h)
    colors = [
        ("roof_slate", (63, 100, 143), 51),
        ("roof_slate_light", (94, 132, 166), 52),
        ("roof_terracotta", (176, 97, 67), 53),
        ("roof_teal", (62, 132, 121), 54),
        ("roof_copper", (141, 112, 77), 55),
    ]
    for name, color, seed in colors:
        image, h = slate_surface(seed, color)
        save_pair(name, image, h)
    cobble, h = cobble_surface(61, (137, 143, 141))
    save_pair("street_cobble", cobble, h)
    wood, h = wood_surface(71, (119, 79, 47))
    save_pair("wood_oak", wood, h)
    grass, h = grass_surface(81, (128, 168, 74))
    save_pair("grass_field", grass, h)
    water, h = water_surface(91, (69, 145, 169))
    save_pair("water_soft", water, h, blur=0.35)
    dirt, h = dirt_surface(101, (147, 102, 58))
    save_pair("dirt_path", dirt, h)


if __name__ == "__main__":
    main()
