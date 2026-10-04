"""Numbered circles / rectangles on a capture: the circled-region fix requests of the gauntlet loop (Stage C step 7).

python tools/capture/annotate.py --image capture.png --spec issues.json --out annotated.png [--no-legend]

issues.json: {"title": "...", "items": [
   {"shape": "circle", "x": 0.42, "y": 0.55, "r": 0.06, "note": "Fountain rim reads flat; add bevel + AO"},
   {"shape": "rect", "x": 0.10, "y": 0.62, "w": 0.20, "h": 0.15, "note": "...", "color": "#ffb000"}]}
Coordinates are fractions of the image when every value is <= 1, otherwise pixels. Items are numbered in order
(or by "label"). The legend under the image repeats each number with its note (Thai text supported).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

from imaging import font

PALETTE = ["#ff3b30", "#ffcc00", "#34c759", "#0a84ff", "#ff9f0a", "#bf5af2", "#64d2ff", "#ff375f"]


def annotate(image_path: Path, spec: dict, out: Path, legend: bool = True) -> Path:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    items = spec.get("items", [])
    units = spec.get("units")
    normalised = units == "norm" if units in ("norm", "px") else all(max(abs(float(item.get(key, 0))) for key in ("x", "y", "r", "w", "h")) <= 1.0 for item in items)
    sx, sy = (width, height) if normalised else (1, 1)
    stroke = max(3, width // 320)
    badge_font, legend_font = font(max(16, width // 70)), font(max(15, width // 90))
    draw = ImageDraw.Draw(image)
    for index, item in enumerate(items):
        color = ImageColor.getrgb(item.get("color", PALETTE[index % len(PALETTE)]))
        label = str(item.get("label", index + 1))
        x, y = float(item["x"]) * sx, float(item["y"]) * sy
        if item.get("shape", "circle") == "rect":
            box = (x, y, x + float(item["w"]) * sx, y + float(item["h"]) * sy)
            draw.rectangle(box, outline=(0, 0, 0), width=stroke + 4)
            draw.rectangle(box, outline=color, width=stroke)
            anchor = (box[0], box[1])
        else:
            r = float(item.get("r", 0.05)) * (min(width, height) if normalised else 1)
            box = (x - r, y - r, x + r, y + r)
            draw.ellipse(box, outline=(0, 0, 0), width=stroke + 4)
            draw.ellipse(box, outline=color, width=stroke)
            anchor = (x - r * 0.72, y - r * 0.72)
        radius = max(14, width // 90)
        cx, cy = max(radius, min(width - radius, anchor[0])), max(radius, min(height - radius, anchor[1]))
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline=(0, 0, 0), width=2)
        draw.text((cx, cy), label, fill=(0, 0, 0) if sum(color) > 400 else (255, 255, 255), font=badge_font, anchor="mm")
    if legend and items:
        line_h = int(legend_font.size * 1.6) if hasattr(legend_font, "size") else 24
        title = spec.get("title")
        panel_h = line_h * (len(items) + (1 if title else 0)) + 16
        canvas = Image.new("RGB", (width, height + panel_h), (16, 20, 26))
        canvas.paste(image, (0, 0))
        legend_draw = ImageDraw.Draw(canvas)
        y = height + 8
        if title:
            legend_draw.text((12, y), str(title), fill=(240, 228, 196), font=legend_font)
            y += line_h
        for index, item in enumerate(items):
            color = ImageColor.getrgb(item.get("color", PALETTE[index % len(PALETTE)]))
            legend_draw.ellipse((12, y + 2, 12 + line_h - 8, y + line_h - 6), fill=color)
            legend_draw.text((12 + line_h, y), f"{item.get('label', index + 1)}. {item.get('note', '')}", fill=(232, 232, 228), font=legend_font)
            y += line_h
        image = canvas
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, optimize=True)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-legend", action="store_true")
    args = parser.parse_args()
    print(annotate(args.image, json.loads(args.spec.read_text(encoding="utf-8")), args.out, legend=not args.no_legend))
