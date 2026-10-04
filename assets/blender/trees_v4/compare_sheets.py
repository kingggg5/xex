"""Target-vs-candidates and greyscale sheets for Route A (trees v4). System Python + Pillow + numpy.

target-vs-candidates.png: crops of the owner's target image (docs/ui/xexoria-town-art-target-20261001.png)
next to the picked candidates, every cell scaled to the same tree height (matching scale), with
foliage palette swatches (dark p10 / mid p50 / light p90 by luminance) under each cell.
Candidate crops come from the 1920x1080 player-view renders (game pixel density) and their
alpha masks (ground as holdout), so the swatches sample only the tree's own pixels.

greyscale-player-views.png: every candidate's 768x432 player view, cropped to tree + witness and
converted to luminance, beside the target crops in luminance (decision doc 4.4: "the silhouette
reads in greyscale at 13 m").

Usage:
  python compare_sheets.py --target <png> --renders <pass dir> --picks <picks dir> --out-dir <dir>
      --broadleaf A,B,C --pines D,E --bushes F,G [--all A,B,...]
"""
import argparse
import colorsys
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = r"C:\Windows\Fonts"
CELL_H = 400
GROUP_H = {"broadleaf": 400, "pines": 400, "bushes": 260}
# decision doc 4.2 step 5 start palette (shadow / mid / highlight) and the kit's flat leaf texture colours
DOC_PALETTE = {"broadleaf": ("#2F6B3E", "#6FA83C", "#B5D65A"), "pines": ("#1D4A35", "#2E6B3F", "#6FA65A"),
               "bushes": ("#2F6B3E", "#6FA83C", "#B5D65A")}
KIT_FLAT = {"broadleaf": ("Leaves_NormalTree_C", "#587B00"), "pines": ("Leaf_Pine_C", "#335800"),
            "bushes": ("Leaves_NormalTree_C / Leaves_TwistedTree_C", "#587B00 / #A71717")}
# Target crops (x0, y0, x1, y1) in the 1536x1024 target; "crown" boxes are for palette sampling.
TARGET_TREES = {
    "broadleaf": [("target: foreground broadleaf, right of path", (995, 640, 1195, 880), (1010, 650, 1185, 790)),
                  ("target: broadleaf, left of path", (248, 605, 412, 785), (258, 612, 400, 735)),
                  ("target: broadleaf, right edge", (1372, 620, 1536, 940), (1385, 640, 1536, 830))],
    "pines": [("target: foreground pine, left", (30, 535, 300, 880), (45, 545, 290, 850)),
              ("target: pine at the gate", (562, 585, 658, 698), (570, 590, 652, 690)),
              ("target: pine, right", (1305, 780, 1415, 912), (1315, 790, 1400, 905))],
    "bushes": [("target: red-flowered bush, lower left", (35, 890, 165, 1000), (45, 898, 158, 990)),
               ("target: berry bush, right of path", (1175, 885, 1305, 978), (1182, 892, 1298, 970))],
}


def font(size, bold=False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        p = os.path.join(FONT_DIR, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def foliage_palette(rgb, mask=None):
    a = np.asarray(rgb).reshape(-1, 3).astype(np.float64) / 255.0
    sel = np.ones(len(a), bool) if mask is None else (np.asarray(mask).reshape(-1) > 242)
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in a[sel][:: max(1, sel.sum() // 20000)]])
    pix = a[sel][:: max(1, sel.sum() // 20000)]
    if not len(hsv):
        return None
    green = (hsv[:, 0] * 360 >= 45) & (hsv[:, 0] * 360 <= 170) & (hsv[:, 1] >= 0.22) & (hsv[:, 2] >= 0.04)
    if green.sum() < 50 and mask is not None:
        green = (hsv[:, 1] >= 0.22) & (hsv[:, 2] >= 0.04)   # exact mask: accept non-green foliage (red bush)
    pix = pix[green]
    if len(pix) < 50:
        return None
    lum = pix @ np.array([0.2126, 0.7152, 0.0722])
    order = np.argsort(lum)
    out = {}
    for name, q in (("dark_p10", 0.10), ("mid_p50", 0.50), ("light_p90", 0.90)):
        i0, i1 = int(len(order) * max(0, q - 0.04)), int(len(order) * min(1, q + 0.04))
        c = np.median(pix[order[i0:max(i1, i0 + 1)]], axis=0)
        out[name] = "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in c)
    out["pixels"] = int(len(pix))
    out["value_range_p90_minus_p10"] = round(float(lum[order[int(len(order) * 0.9)]] - lum[order[int(len(order) * 0.1)]]), 3)
    return out


def swatch_row(draw, x, y, pal, w):
    if not pal:
        draw.text((x + 4, y + 2), "no foliage pixels", fill=(220, 120, 120), font=font(13))
        return
    sw = (w - 8) // 3
    for i, k in enumerate(("dark_p10", "mid_p50", "light_p90")):
        c = tuple(int(pal[k][j:j + 2], 16) for j in (1, 3, 5))
        draw.rectangle([x + 4 + i * sw, y, x + 4 + (i + 1) * sw - 3, y + 26], fill=c)
        lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        draw.text((x + 8 + i * sw, y + 5), pal[k], fill=(0, 0, 0) if lum > 110 else (255, 255, 255), font=font(12))


def scaled(img, h):
    return img.resize((max(1, round(img.width * h / img.height)), h), Image.LANCZOS)


def candidate_crop(picks_dir, model, pad=0.06):
    side = json.load(open(os.path.join(picks_dir, f"{model}__views.json"), encoding="utf-8"))
    info = side["views"]["player_1080"]
    img = Image.open(os.path.join(picks_dir, f"{model}__player_1080.png")).convert("RGB")
    mask = Image.open(os.path.join(picks_dir, f"{model}__player_1080_mask.png")).convert("RGBA").split()[3]
    bb = info["tree_bbox_px"]
    w, h = bb["x1"] - bb["x0"], bb["y1"] - bb["y0"]
    box = (int(max(0, bb["x0"] - pad * w)), int(max(0, bb["y0"] - pad * h)),
           int(min(img.width, bb["x1"] + pad * w)), int(min(img.height, bb["y1"] + pad * h * 0.6)))
    return img.crop(box), mask.crop(box), side


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--renders", required=True)
    ap.add_argument("--picks", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--broadleaf", required=True)
    ap.add_argument("--pines", required=True)
    ap.add_argument("--bushes", required=True)
    ap.add_argument("--all", default="")
    ap.add_argument("--measure", required=True)
    args = ap.parse_args()
    target = Image.open(args.target).convert("RGB")
    measure = json.load(open(args.measure, encoding="utf-8"))["models"]
    groups = [("broadleaf", args.broadleaf.split(",")), ("pines", args.pines.split(",")), ("bushes", args.bushes.split(","))]
    report = {"label": "BLENDER REVIEW candidates vs owner target crops (target = concept image, not a game capture)",
              "palette_method": "foliage pixels by hue 45-170 deg, sat >= 0.22; luminance percentiles p10/p50/p90; "
                                "candidates sampled inside the render's own alpha mask", "rows": {}}
    rows = []
    for gname, models in groups:
        cells = []
        for label, box, crown in TARGET_TREES[gname]:
            crop = target.crop(box)
            pal = foliage_palette(target.crop(crown))
            cells.append((label, scaled(crop, GROUP_H[gname]), pal, "TARGET (concept)"))
            report["rows"].setdefault(gname, []).append({"cell": label, "box": box, "palette": pal})
        for m in models:
            crop, mask, side = candidate_crop(args.picks, m)
            pal = foliage_palette(crop, mask)
            tris = measure[m]["triangles_total"]
            cells.append((f"{m}" + (f"  ({tris:,} tris)" if tris else ""), scaled(crop, GROUP_H[gname]), pal, "BLENDER REVIEW 1080p player view"))
            report["rows"].setdefault(gname, []).append({"cell": m, "palette": pal})
        rows.append((gname, cells))
    pad = 10
    label_h, sw_h = 46, 34
    width = max(sum(c[1].width + pad for c in cells) + pad for _, cells in rows)
    height = 92 + sum(GROUP_H[g] + label_h + sw_h + 30 for g, _ in rows)
    sheet = Image.new("RGB", (width, height), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    d.text((14, 8), "TARGET vs CANDIDATES  -  target crops (concept image)  |  candidates: BLENDER REVIEW, not Babylon",
           fill=(255, 196, 64), font=font(26, True))
    d.text((14, 46), "Every cell scaled to the same height (matching scale). Candidates = kit as shipped at target height, "
                     "player camera 13 m / 22.4 deg / FOV 1.02 rad rendered at 1920x1080. Swatches: foliage dark p10 / mid p50 / light p90.",
           fill=(220, 220, 220), font=font(16))
    y = 92
    for gname, cells in rows:
        d.text((14, y), gname.upper(), fill=(255, 255, 255), font=font(20, True))
        xx = 160
        d.text((xx, y + 3), "decision-doc start palette:", fill=(200, 200, 200), font=font(14))
        for k, hx in enumerate(DOC_PALETTE[gname]):
            c = tuple(int(hx[j:j + 2], 16) for j in (1, 3, 5))
            d.rectangle([xx + 190 + k * 92, y + 2, xx + 278 + k * 92, y + 22], fill=c)
            d.text((xx + 194 + k * 92, y + 4), hx, fill=(0, 0, 0) if sum(c) > 330 else (255, 255, 255), font=font(12))
        d.text((xx + 480, y + 3), f"kit leaf texture is one flat colour: {KIT_FLAT[gname][0]} {KIT_FLAT[gname][1]}",
               fill=(255, 170, 90), font=font(14))
        y += 28
        x = pad
        for label, img, pal, tag in cells:
            sheet.paste(img, (x, y))
            d.rectangle([x, y, x + min(img.width, 300), y + 18], fill=(0, 0, 0))
            d.text((x + 4, y + 1), tag, fill=(255, 196, 64) if tag.startswith("BLENDER") else (140, 220, 255), font=font(12, True))
            d.text((x + 2, y + GROUP_H[gname] + 4), label, fill=(235, 235, 235), font=font(14, True))
            swatch_row(d, x, y + GROUP_H[gname] + label_h - 18, pal, img.width)
            x += img.width + pad
        y += GROUP_H[gname] + label_h + sw_h
    os.makedirs(args.out_dir, exist_ok=True)
    out = os.path.join(args.out_dir, "target-vs-candidates.png")
    sheet.save(out, optimize=True)
    with open(os.path.join(args.out_dir, "target-vs-candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print("WROTE", out, sheet.size)

    # greyscale sheet: native pixel scale (x2 for every candidate tile, x1 for the target crops), flow layout,
    # so the relative size of each silhouette at 13 m is preserved (a bush stays small)
    models = [m for m in args.all.split(",") if m] or [m for _, ms in groups for m in ms]
    scale_c = 2
    targets_l = [(label, target.crop(box).convert("L")) for label, box, _c in
                 TARGET_TREES["broadleaf"] + TARGET_TREES["pines"]]
    cands = []
    for m in models:
        side = json.load(open(os.path.join(args.renders, f"{m}__views.json"), encoding="utf-8"))
        info = side["views"]["player"]
        img = Image.open(os.path.join(args.renders, f"{m}__player.png")).convert("L")
        bb = info["tree_bbox_px"]
        fx, fy = info["witness_feet_px"]
        x0 = int(max(0, min(bb["x0"], fx - 14) - 8))
        x1 = int(min(img.width, max(bb["x1"], fx + 14) + 8))
        y0 = int(max(0, bb["y0"] - 8))
        y1 = int(min(img.height, max(bb["y1"], fy) + 8))
        c = img.crop((x0, y0, x1, y1))
        cands.append((m, c.resize((c.width * scale_c, c.height * scale_c), Image.LANCZOS)))
    pad, lab = 12, 18
    def flow(tiles, max_w):
        rows, cur, w = [], [], pad
        for t in tiles:
            if cur and w + t[1].width + pad > max_w:
                rows.append(cur)
                cur, w = [], pad
            cur.append(t)
            w += t[1].width + pad
        if cur:
            rows.append(cur)
        return rows
    max_w = 2400
    t_rows = flow(targets_l, max_w)
    c_rows = flow(cands, max_w)
    height = 86 + sum(max(t[1].height for t in r) + lab + pad for r in t_rows) + 34 +         sum(max(t[1].height for t in r) + lab + pad for r in c_rows) + 10
    g = Image.new("L", (max_w, height), 30)
    gd = ImageDraw.Draw(g)
    gd.text((12, 8), "GREYSCALE silhouettes @ 13 m player view (luminance only)", fill=235, font=font(24, True))
    gd.text((12, 44), "Top: target crops at native size (concept image).  Bottom: BLENDER REVIEW candidates cropped from the "
                      "768x432 player views, all at the same x2 scale, so relative sizes are true (1.8 m witness in each).",
            fill=200, font=font(15))
    y = 86
    for r in t_rows:
        x = pad
        for label, img in r:
            g.paste(img, (x, y))
            gd.text((x, y + img.height + 2), "TARGET: " + label.replace("target: ", ""), fill=220, font=font(12))
            x += img.width + pad
        y += max(t[1].height for t in r) + lab + pad
    gd.text((12, y + 4), "BLENDER REVIEW candidates (kit as shipped, scaled to 7.5 m broadleaf / 8 m pine / 1.2 m bush)",
            fill=235, font=font(16, True))
    y += 34
    for r in c_rows:
        x = pad
        for label, img in r:
            g.paste(img, (x, y))
            gd.text((x, y + img.height + 2), label, fill=220, font=font(12))
            x += img.width + pad
        y += max(t[1].height for t in r) + lab + pad
    gout = os.path.join(args.out_dir, "greyscale-player-views.png")
    g.save(gout, optimize=True)
    print("WROTE", gout, g.size)


if __name__ == "__main__":
    main()
