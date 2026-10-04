"""LOD0 vs LOD1 strip (BLENDER REVIEW, same light and player camera) for Route A step 2. System Python + Pillow.

Usage:
  python lod_strip.py --lod0 <renders dir> --lod1 <renders dir> --verify <verify.json> --out <png>
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import compare_sheets as cs  # noqa: E402

SPECIES = ["qn_broadleaf_s", "qn_broadleaf_m", "qn_broadleaf_l", "qn_conifer_m", "qn_conifer_l", "qn_bush_flowers",
           "qn_bush"]


def crop(dirn, name):
    info = json.load(open(os.path.join(dirn, f"{name}__views.json"), encoding="utf-8"))["views"]["player"]
    img = Image.open(os.path.join(dirn, f"{name}__player.png")).convert("RGB")
    bb = info["tree_bbox_px"]
    fx, fy = info["witness_feet_px"]
    box = (int(max(0, min(bb["x0"], fx - 14) - 8)), int(max(0, bb["y0"] - 8)),
           int(min(img.width, max(bb["x1"], fx + 14) + 8)), int(min(img.height, max(bb["y1"], fy) + 8)))
    c = img.crop(box)
    return c.resize((c.width * 2, c.height * 2), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lod0", required=True)
    ap.add_argument("--lod1", required=True)
    ap.add_argument("--verify", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ver = json.load(open(a.verify, encoding="utf-8"))["files"]
    tiles = []
    for sp in SPECIES:
        for lod, d in ((0, a.lod0), (1, a.lod1)):
            tiles.append((f"{sp} LOD{lod}  {ver[f'{sp}_lod{lod}']['triangles']:,} tris", crop(d, f"{sp}_lod{lod}")))
    h = max(t[1].height for t in tiles)
    w = sum(t[1].width + 10 for t in tiles) + 10
    sheet = Image.new("RGB", (w, h + 70), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    d.text((10, 6), "LOD0 vs LOD1 at the 13 m player view (x2 crops of 768x432) - BLENDER REVIEW, step-1 light, not Babylon",
           fill=(255, 196, 64), font=cs.font(18, True))
    x = 10
    for label, img in tiles:
        sheet.paste(img, (x, 34 + h - img.height))
        d.text((x, h + 40), label, fill=(230, 230, 230), font=cs.font(12))
        x += img.width + 10
    sheet.save(a.out, optimize=True)
    print("WROTE", a.out, sheet.size)


if __name__ == "__main__":
    main()
