"""Plan-view check image of the derived water (labelled PLAN, data only; not a render).

Draws the visual ground height (bed, banks), the waterline (f = 0), the hazard polygons (+0.7 m) with the open
deck corridor and the gap plug, the bridge deck, stones, anchors, the bluff toe and the trail clearance points.
Usage: python assets/blender/water/render_water_plan.py --out planning/evidence/water-20261002/plan/water-plan.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import water_layout as W  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default=str(W.LAYOUT_PATH))
    ap.add_argument("--out", required=True)
    ap.add_argument("--px-per-m", type=float, default=14.0)
    a = ap.parse_args()
    model = W.WaterModel(Path(a.layout))
    sp = model.sp
    rect = model.ground_rect()
    x0, x1, z0, z1 = rect
    k = a.px_per_m
    Wd, Hd = int((x1 - x0) * k), int((z1 - z0) * k)
    step = 1.0 / k
    xs = x0 + (np.arange(Wd) + 0.5) * step
    zs = z1 - (np.arange(Hd) + 0.5) * step          # image rows go south (north up)
    X, Z = np.meshgrid(xs, zs)
    F = sp.fields(np.stack([X.ravel(), Z.ravel()], 1))
    g = F["ground_y"].reshape(X.shape)
    f = F["f"].reshape(X.shape)
    depth = F["depth"].reshape(X.shape)
    img = np.zeros((Hd, Wd, 3), np.float32)
    grass = np.array([0.53, 0.62, 0.40])
    bank = np.array([0.45, 0.38, 0.27])
    water_sh = np.array([0.31, 0.62, 0.57])
    water_dp = np.array([0.04, 0.23, 0.27])
    t = np.clip(-g / 0.35, 0, 1)[..., None]
    img[:] = grass * (1 - t) + bank * t
    wet = (f < 0)[..., None]
    dd = np.clip(depth / 0.9, 0, 1)[..., None]
    img = np.where(wet, water_sh * (1 - dd) + water_dp * dd, img)
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGB")
    dr = ImageDraw.Draw(im)

    def px(x, z):
        return ((x - x0) * k, (z1 - z) * k)

    for loop in model.waterline():
        dr.line([px(*p) for p in np.vstack([loop, loop[:1]])], fill=(240, 250, 255), width=1)
    hz = model.hazard()
    for poly in hz["polygons"]:
        pts = [px(*p) for p in poly] + [px(*poly[0])]
        dr.line(pts, fill=(220, 40, 40), width=2)
    # bridge deck
    c, ax = sp.bridge_c, sp.bridge_axis
    nn = np.array([-ax[1], ax[0]])
    corners = [c + ax * sp.bridge_half_len * sa + nn * sp.bridge_half_wid * sb for sa, sb in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
    dr.polygon([px(*p) for p in corners], outline=(120, 80, 40))
    dr.line([px(*p) for p in corners + corners[:1]], fill=(150, 95, 45), width=3)
    # bluff toe
    dr.line([px(W.BLUFF_TOE_X, -46), px(W.BLUFF_TOE_X, -30)], fill=(90, 70, 60), width=3)
    for s in model.stones:
        r = s["r"] * k
        cx, cz = px(s["x"], s["z"])
        col = {"boulder": (250, 200, 60), "submerged": (90, 160, 200), "bank": (200, 200, 190), "sill": (230, 150, 230),
               "rim": (210, 210, 170), "toe": (160, 140, 120), "cascade": (255, 120, 60), "gap": (255, 80, 160), "spur": (140, 120, 110)}[s["group"]]
        dr.ellipse([cx - r, cz - r, cx + r, cz + r], outline=col, width=2)
    for name, an in model.anchors().items():
        x, _, z = an["position"]
        cx, cz = px(x, z)
        dr.rectangle([cx - 3, cz - 3, cx + 3, cz + 3], fill=(255, 255, 0) if name.startswith("emit") else (0, 255, 255))
    pine = (-23.0, -56.0)
    cx, cz = px(*pine)
    dr.ellipse([cx - 6, cz - 6, cx + 6, cz + 6], outline=(20, 90, 30), width=3)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    dr.text((8, 6), "PLAN (derived water data, not a render): sunmeadow stream + falls pool; red = hazard +0.7 m;"
                    " white = waterline; brown = deck; circles = stones", fill=(255, 255, 255), font=font)
    dr.text((8, 26), f"layout {model.layout_sha[:12]}  seed {model.seed}  A1={sp.amended_a1} A2={sp.amended_a2}  "
                     f"rect x[{x0},{x1}] z[{z0},{z1}]  1 px = {1 / k:.3f} m", fill=(255, 255, 255), font=font)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    im.save(a.out)
    print(json.dumps({"out": a.out, "size": im.size, "hazard_polygons": len(hz["polygons"]), "boxes": len(hz["boxes"])}))


if __name__ == "__main__":
    main()
