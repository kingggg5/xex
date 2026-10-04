"""Contact sheet for the Blender VFX kit: each texture as it reads in game (ramp-tinted, additive over night ground).

python tools/vfx_kit_preview.py [--out planning/evidence/vfx-sample-v1/kit-preview.png]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'assets' / 'vfx' / 'kit-v1'
RAMPS = {  # core -> mid -> edge, per the spec palettes
    'blade': ['#F4FBFF', '#7FD3FF', '#2B6CFF'],
    'gale': ['#F2FFF9', '#5FF2C8', '#13A88A'],
    'void': ['#FFF0FF', '#B07CFF', '#5A1FD1'],
}
TINT = {
    'vfx_rune_circle_outer': 'void', 'vfx_rune_circle_inner': 'void', 'vfx_rune_ring_blade': 'blade',
    'vfx_swirl_arms': 'void', 'vfx_shock_ring': 'blade', 'vfx_impact_star': 'blade', 'vfx_ground_cracks': 'blade',
    'vfx_scorch': 'void', 'vfx_streak': 'gale', 'vfx_palm_sigil': 'gale', 'vfx_noise_erosion': None,
    'vfx_soft_disc': 'gale', 'vfx_fb_lightning': 'void', 'vfx_fb_impact': 'blade', 'vfx_fb_swirl': 'gale',
    'vfx_shards': 'blade', 'vfx_fb_dust': None,
}
BACKGROUND = np.array([0x14, 0x22, 0x2a], np.float32) / 255


def hex_rgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255


def ramp(value: np.ndarray, stops: list[str]) -> np.ndarray:
    core, mid, edge = (hex_rgb(s) for s in stops)
    v = value[..., None]
    low = edge + (mid - edge) * np.clip(v / 0.55, 0, 1)
    return np.where(v < 0.55, low, mid + (core - mid) * np.clip((v - 0.55) / 0.45, 0, 1))


def render_tile(name: str, size: int) -> Image.Image:
    rgba = np.asarray(Image.open(KIT / f'{name}.png').convert('RGBA'), np.float32) / 255
    value, alpha = rgba[..., 0], rgba[..., 3]
    if name == 'vfx_ground_cracks':
        seam, scorch = rgba[..., 0], rgba[..., 1]
        base = BACKGROUND * (1 - 0.85 * np.clip(scorch * alpha, 0, 1))[..., None]
        color = base + ramp(seam, RAMPS['blade']) * (seam * alpha)[..., None] * 1.4
    elif name == 'vfx_scorch':
        base = BACKGROUND * (1 - 0.9 * alpha)[..., None]
        color = base + ramp(value, RAMPS['void']) * (value * alpha)[..., None] * 1.5
    elif name == 'vfx_fb_dust':
        dust = np.array([0x9f, 0xb3, 0xc8], np.float32) / 255
        color = BACKGROUND * (1 - alpha[..., None]) + (dust * (0.35 + 0.75 * value[..., None])) * alpha[..., None]
    elif TINT.get(name) is None:
        color = np.repeat(value[..., None], 3, axis=2)
    else:
        color = BACKGROUND + ramp(value, RAMPS[TINT[name]]) * (value * alpha)[..., None] * 1.25
    img = Image.fromarray((np.clip(color, 0, 1) * 255).astype(np.uint8), 'RGB')
    img.thumbnail((size, size), Image.LANCZOS)
    tile = Image.new('RGB', (size, size + 22), tuple((BACKGROUND * 255).astype(int)))
    tile.paste(img, ((size - img.width) // 2, 22 + (size - img.height) // 2))
    draw = ImageDraw.Draw(tile)
    try:
        font = ImageFont.truetype('consola.ttf', 13)
    except OSError:
        font = ImageFont.load_default()
    receipt = json.loads((KIT / 'kit-receipt.json').read_text())['assets'].get(name, {})
    grid = receipt.get('grid')
    label = f'{name}  {receipt.get("width")}x{receipt.get("height")}' + (f'  {grid["cols"]}x{grid["rows"]}' if grid else '')
    draw.text((6, 4), label, fill=(230, 236, 240), font=font)
    return tile


def main() -> None:
    out = ROOT / 'planning' / 'evidence' / 'vfx-sample-v1' / 'kit-preview.png'
    if '--out' in sys.argv:
        out = ROOT / sys.argv[sys.argv.index('--out') + 1]
    names = [n for n in TINT if (KIT / f'{n}.png').exists()]
    size, cols = 420, 4
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * size, rows * (size + 22)), (8, 12, 16))
    for i, name in enumerate(names):
        sheet.paste(render_tile(name, size), ((i % cols) * size, (i // cols) * (size + 22)))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print('PREVIEW', out, sheet.size)


if __name__ == '__main__':
    main()
