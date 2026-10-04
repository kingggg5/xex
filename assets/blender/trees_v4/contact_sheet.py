"""Build the labelled BLENDER REVIEW contact sheet for Route A (trees v4).

System Python + Pillow (already present; nothing installed). One row per model:
label cell (model name, triangle count, key measured numbers) + player / close / side views.
The side elevation gets metre ticks from the render's own sidecar (px per metre, ground row).

Usage:
  python contact_sheet.py --renders <dir> --measure <measure.json> --out <png> --pass-label "pass 3"
      [--models A,B,...]
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

VIEW_W, VIEW_H = 768, 432
LABEL_W = 330
GAP = 6
FONT_DIR = r"C:\Windows\Fonts"
DEFAULT_MODELS = ([f"CommonTree_{i}" for i in range(1, 6)] + [f"Pine_{i}" for i in range(1, 6)]
                  + ["Bush_Common", "Bush_Common_Flowers"])
SPEC_BAND = {"broadleaf": (2.2, 3.0), "conifer": (1.6, 2.4)}


def font(size, bold=False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        p = os.path.join(FONT_DIR, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def side_ticks(img, info, kind):
    d = ImageDraw.Draw(img, "RGBA")
    ppm = info["px_per_m"]
    g = info["ground_row_px"]
    f = font(13)
    top_m = int((g - 4) / ppm)
    for m in range(0, top_m + 1):
        y = g - m * ppm
        if y < 4:
            break
        d.line([(0, y), (14 if m % 5 else 22, y)], fill=(20, 20, 20, 230), width=2)
        d.text((26, y - 9), f"{m} m", fill=(20, 20, 20, 255), font=f)
    if kind in SPEC_BAND:
        lo, hi = SPEC_BAND[kind]
        y0, y1 = g - hi * ppm, g - lo * ppm
        d.rectangle([VIEW_W - 16, y0, VIEW_W - 4, y1], fill=(230, 120, 30, 170))
        d.text((VIEW_W - 150, y0 - 18), "spec crown base", fill=(150, 60, 0, 255), font=font(12))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", required=True)
    ap.add_argument("--measure", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pass-label", default="")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    args = ap.parse_args()
    measure = json.load(open(args.measure, encoding="utf-8"))["models"]
    models = args.models.split(",")
    header_h = 118
    width = LABEL_W + 3 * (VIEW_W + GAP) + GAP
    height = header_h + len(models) * (VIEW_H + GAP) + GAP
    sheet = Image.new("RGB", (width, height), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    d.text((16, 10), "BLENDER REVIEW  -  not a Babylon capture", fill=(255, 196, 64), font=font(30, True))
    d.text((16, 50), "Quaternius Stylized Nature MegaKit [Standard] (CC0) as shipped, kit materials unmodified  |  Route A step 1, "
                     "trees v4  |  " + args.pass_label, fill=(235, 235, 235), font=font(18))
    side0 = None
    for m in models:
        p = os.path.join(args.renders, f"{m}__views.json")
        if os.path.exists(p):
            side0 = json.load(open(p, encoding="utf-8"))
            break
    if side0:
        lt, rd = side0["light"], side0["render"]
        hemi = lt.get("hemispheric_fill", {})
        d.text((16, 76), f"Copies scaled to target height (broadleaf M 7.5 m, pine M 8 m, bush 1.2 m); 1.8 m capsule witness.  "
                         f"Sun #FFE7C2 x{lt['sun_strength']} at 45 deg + game-style sky fill {hemi.get('sky_srgb', '')}/"
                         f"{hemi.get('ground_srgb', '')} (ratio {hemi.get('ratio_to_sun', '')}).  Cycles {rd['device']}, "
                         f"{rd['samples']} spp + denoise, {rd['resolution'][0]}x{rd['resolution'][1]}, {rd['view_transform']}.",
               fill=(200, 200, 200), font=font(15))
    cols = ["player view: 13 m, 22.4 deg, FOV 1.02 rad, target 1.65 m", "close: 2-3 m from the canopy edge",
            "side elevation (orthographic, metre ticks)"]
    for i, c in enumerate(cols):
        d.text((LABEL_W + GAP + i * (VIEW_W + GAP) + 8, header_h - 22), c, fill=(255, 255, 255), font=font(16, True))
    for r, m in enumerate(models):
        y = header_h + r * (VIEW_H + GAP)
        meta = measure[m]
        sh = meta["shape_at_target"]
        pm = meta["per_material"]
        bark = sum(v["triangles"] for v in pm.values() if v["kind"] == "bark")
        leaf = sum(v["triangles"] for v in pm.values() if v["kind"] == "foliage")
        views = json.load(open(os.path.join(args.renders, f"{m}__views.json"), encoding="utf-8"))
        d.rectangle([GAP, y, LABEL_W - 2, y + VIEW_H], fill=(36, 39, 45))
        d.text((GAP + 12, y + 10), m, fill=(255, 255, 255), font=font(28, True))
        d.text((GAP + 12, y + 52), f"{meta['triangles_total']:,} tris", fill=(255, 214, 120), font=font(26, True))
        lines = [f"bark {bark:,}  /  foliage {leaf:,}",
                 f"materials {meta['material_count']}, mesh objects {meta['mesh_objects']}",
                 f"as imported {sh['visible_height_imported_m']:.2f} m tall",
                 f"  (+{sh['buried_depth_below_origin_m']:.2f} m buried below origin)",
                 f"shown at {sh['target_height_m']} m  (x{sh['scale_to_target']:.3f})"]
        if sh.get("trunk_radius_1m_m") is not None:
            lines += [f"trunk r @1 m  {sh['trunk_radius_1m_m']:.2f} m",
                      f"flare r0/r1  x{sh['flare_ratio_ground_over_1m']:.2f}"]
        if sh.get("crown_base_m_p5") is not None:
            lines += [f"crown base (p5)  {sh['crown_base_m_p5']:.2f} m",
                      f"crown width/height  {sh['crown_width_over_height']:.2f}"]
        fol = [v for v in pm.values() if v["kind"] == "foliage"]
        if fol and fol[0].get("cards_at_target_scale"):
            c = fol[0]["cards_at_target_scale"]
            lines.append(f"cards {sum(v.get('cards_at_target_scale', {}).get('count', 0) for v in fol)}, "
                         f"median diag {c['diag_m_median']:.2f} m")
        for i, line in enumerate(lines):
            d.text((GAP + 12, y + 96 + i * 26), line, fill=(215, 215, 215), font=font(18))
        close_info = views["views"].get("close", {})
        if close_info.get("note"):
            note = ["close view: no witness in frame",
                    f"crown base {views['crown_base_p5_m']:.1f} m: canopy edge and",
                    "a 1.8 m person do not fit within 3 m"]
            for k, t in enumerate(note):
                d.text((GAP + 12, y + VIEW_H - 70 + k * 22), t, fill=(255, 150, 60), font=font(15, k == 0))
        for i, v in enumerate(("player", "close", "side")):
            x = LABEL_W + GAP + i * (VIEW_W + GAP)
            fp = os.path.join(args.renders, f"{m}__{v}.png")
            if not os.path.exists(fp):
                d.rectangle([x, y, x + VIEW_W, y + VIEW_H], outline=(255, 60, 60), width=3)
                d.text((x + 20, y + 20), f"missing {v}", fill=(255, 80, 80), font=font(20))
                continue
            img = Image.open(fp).convert("RGB")
            if v == "side":
                img = side_ticks(img, views["views"]["side"], views["kind"])
            sheet.paste(img, (x, y))
            dd = ImageDraw.Draw(sheet)
            dd.rectangle([x, y, x + 205, y + 20], fill=(0, 0, 0))
            dd.text((x + 5, y + 1), "BLENDER REVIEW  " + v, fill=(255, 196, 64), font=font(14, True))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    sheet.save(args.out, optimize=True)
    print("WROTE", args.out, sheet.size)


if __name__ == "__main__":
    main()
