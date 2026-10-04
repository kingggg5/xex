"""Side-by-side: owner's reference VFX frames vs Xexoria VFX lab captures (same beat, night).

python tools/vfx_compare_sheet.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'planning' / 'evidence' / 'vfx-sample-v1'
REFS = {
    'sw_iron_rebuke': ROOT / 'content' / 'ChatGPT Image Oct 1, 2026, 10_46_58 PM.png',
    'fs_palm_wave': ROOT / 'content' / 'ChatGPT Image Oct 1, 2026, 10_45_00 PM.png',
    'st_underworld_gate': ROOT / 'content' / 'ChatGPT Image Oct 1, 2026, 10_46_38 PM.png',
}
PAIRS = [  # (reference, ref frame index, ours, our frame index)
    ('sw_iron_rebuke', 3, 'xs_bladeward_nova', 3),
    ('sw_iron_rebuke', 4, 'xs_bladeward_nova', 4),
    ('fs_palm_wave', 3, 'xs_gale_palm', 2),
    ('fs_palm_wave', 6, 'xs_gale_palm', 4),
    ('st_underworld_gate', 3, 'xs_void_rift', 3),
    ('st_underworld_gate', 5, 'xs_void_rift', 4),
]


def frame_boxes(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """Find the 8 frames of a 4x2 contact sheet by locating the dark label/header bands."""
    a = np.asarray(img.convert('L'), np.float32)
    w = img.width
    row_dark = (a < 40).mean(axis=1) > 0.93
    bands, start = [], None
    for y, dark in enumerate(row_dark):
        if not dark and start is None:
            start = y
        if dark and start is not None:
            if y - start > 60:
                bands.append((start, y))
            start = None
    if start is not None and len(a) - start > 60:
        bands.append((start, len(a)))
    bands = bands[:2]
    col = w // 4
    return [(c * col + 2, top + 1, (c + 1) * col - 2, bottom - 1) for top, bottom in bands for c in range(4)]


def main() -> None:
    cell_w, cell_h, pad, label = 760, 428, 12, 26
    sheet = Image.new('RGB', (pad * 3 + cell_w * 2, 54 + len(PAIRS) * (cell_h + label + pad)), (12, 15, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('consola.ttf', 15)
        title = ImageFont.truetype('consolab.ttf', 20)
    except OSError:
        font = title = ImageFont.load_default()
    draw.text((pad, 14), 'Owner reference (left)  vs  Xexoria VFX sample v1 — Blender kit + Babylon lab capture, night (right)', fill=(242, 199, 110), font=title)
    y = 54
    for ref_name, ref_index, ours, our_index in PAIRS:
        ref = Image.open(REFS[ref_name]).convert('RGB')
        ref_box = frame_boxes(ref)[ref_index]
        mine = Image.open(EVIDENCE / f'final-{ours}-night-webgl2.png').convert('RGB')
        # Our sheets have a fixed layout: header 34, label 22, cells 640x360 in a 4x2 grid.
        col, row = our_index % 4, our_index // 4
        my_box = (col * 640, 34 + row * 382 + 22, (col + 1) * 640, 34 + row * 382 + 22 + 360)
        for x, (img, box, text) in zip((pad, pad * 2 + cell_w), ((ref, ref_box, f'REFERENCE  {ref_name}  frame {ref_index + 1}/8'),
                                                                   (mine, my_box, f'XEXORIA  {ours}  frame {our_index + 1}/8  (BABYLON CAPTURE)'))):
            crop = img.crop(box).resize((cell_w, cell_h), Image.LANCZOS)
            sheet.paste(crop, (x, y + label))
            draw.text((x + 4, y + 4), text, fill=(214, 226, 234), font=font)
        y += cell_h + label + pad
    out = EVIDENCE / 'compare-reference-vs-xexoria.png'
    sheet.save(out)
    print('COMPARE', out, sheet.size)


if __name__ == '__main__':
    main()
