"""Labelled contact sheet from a JSON item list (used by capture.mjs and responsive-audit.mjs).

python tools/capture/contact_sheet.py --items items.json --out sheet.png [--cols 4] [--thumb 480] [--title "..."]
items.json: [{"path": "...png", "label": "...", "sublabel": "...", "badge": "BLANK" | null}, ...]
Thumbnails keep their aspect ratio inside a thumb x (thumb * 9/16) cell, or a square-ish cell for portrait shots.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from imaging import font


def build_sheet(items: list[dict], out: Path, cols: int = 4, thumb: int = 480, title: str | None = None) -> Path:
    cols = max(1, min(cols, len(items) or 1))
    portrait = sum(1 for item in items if _aspect(item["path"]) < 1) > len(items) / 2
    cell_w = thumb
    cell_h = int(thumb * (1.25 if portrait else 9 / 16))
    label_h = 46
    pad = 10
    title_h = 44 if title else 0
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (pad + cols * (cell_w + pad), title_h + pad + rows * (cell_h + label_h + pad)), (18, 22, 28))
    draw = ImageDraw.Draw(sheet)
    big, small, tiny = font(20), font(15), font(13)
    if title:
        draw.text((pad, 12), title, fill=(240, 228, 196), font=big)
    for index, item in enumerate(items):
        x = pad + (index % cols) * (cell_w + pad)
        y = title_h + pad + (index // cols) * (cell_h + label_h + pad)
        draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), fill=(32, 38, 46))
        try:
            with Image.open(item["path"]) as source:
                image = source.convert("RGB")
            image.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
            sheet.paste(image, (x + (cell_w - image.width) // 2, y + (cell_h - image.height) // 2))
        except (OSError, KeyError) as error:
            draw.text((x + 8, y + 8), f"missing: {error}", fill=(255, 120, 120), font=tiny)
        if item.get("badge"):
            draw.rectangle((x + 6, y + 6, x + 6 + 9 * len(item["badge"]) + 12, y + 28), fill=(170, 30, 30))
            draw.text((x + 12, y + 8), item["badge"], fill=(255, 255, 255), font=small)
        draw.text((x + 2, y + cell_h + 4), str(item.get("label", ""))[:64], fill=(236, 232, 220), font=small)
        draw.text((x + 2, y + cell_h + 24), str(item.get("sublabel", ""))[:80], fill=(160, 176, 192), font=tiny)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, optimize=True)
    return out


def _aspect(path: str) -> float:
    try:
        with Image.open(path) as image:
            return image.width / max(1, image.height)
    except OSError:
        return 16 / 9


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--thumb", type=int, default=480)
    parser.add_argument("--title")
    args = parser.parse_args()
    print(build_sheet(json.loads(args.items.read_text(encoding="utf-8")), args.out, args.cols, args.thumb, args.title))
