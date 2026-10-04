"""BLENDER REVIEW sheets + foliage palette metrics for one Route A step-2 pass (trees v4). System Python.

Re-uses the step-1 measurement (compare_sheets.foliage_palette: foliage pixels by hue 45-170 deg, sat >= 0.22,
luminance p10/p50/p90, sampled inside the render's own alpha mask, 1920x1080 player view) so step-1 originals,
step-2 stylized trees and the target crops are measured the same way under the same light.

Writes into --pass-dir:
  metrics.json           per species: stylized p10/p50/p90 + value range, step-1 original, target, deltas, gate
  target-vs-stylized.png target crops | step-1 original | stylized, matching scale, swatches under each cell
  contact-sheet.png      per species: numbers + player / close / side views (768x432)
  greyscale.png          luminance-only player views (original vs stylized, x2) + alpha silhouettes + target crops

Usage:
  python review_sheets.py --pass-dir <dir> --label "pass 1" --target <png> --step1-picks <dir> --step1-views <dir>
      --stylize-report <json> --verify <json> --step1-palettes <target-vs-candidates.json>
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import compare_sheets as cs  # noqa: E402  (step-1 helpers: foliage_palette, swatch_row, scaled, font, crops)

ROWS = [("broadleaf", [("CommonTree_2", "qn_broadleaf_s"), ("CommonTree_5", "qn_broadleaf_m"),
                       ("CommonTree_1", "qn_broadleaf_l")]),
        ("pines", [("Pine_2", "qn_conifer_m"), ("Pine_5", "qn_conifer_l")]),
        ("bushes", [("Bush_Common_Flowers", "qn_bush_flowers"), ("Bush_Common", "qn_bush")])]
# target references for the gate: the foreground crop of each group (the owner's swatches)
TARGET_REF = {"broadleaf": ("#223313", "#717C2A", "#D4CD4E"), "pines": ("#17271B", "#546632", "#B4B859"),
              "bushes": ("#162A18", "#365B30", "#849746")}
KEYS = ("dark_p10", "mid_p50", "light_p90")


def rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float64)


def luma(h):
    return float(rgb(h) @ np.array([0.2126, 0.7152, 0.0722]) / 255.0)


def compare(pal, ref):
    if not pal:
        return None
    out = {}
    for k, r in zip(KEYS, ref):
        out[k] = {"render": pal[k], "target": r, "d_luma": round(luma(pal[k]) - luma(r), 3),
                  "rgb_dist": round(float(np.linalg.norm(rgb(pal[k]) - rgb(r))), 1)}
    rng_t = luma(ref[2]) - luma(ref[0])
    rng_r = luma(pal["light_p90"]) - luma(pal["dark_p10"])
    out["swatch_value_range"] = {"render": round(rng_r, 3), "target": round(rng_t, 3)}
    out["mean_rgb_dist"] = round(float(np.mean([out[k]["rgb_dist"] for k in KEYS])), 1)
    out["gate"] = {"each_swatch_within_0p08_luma": all(abs(out[k]["d_luma"]) <= 0.08 for k in KEYS),
                   "value_range_within_0p10": abs(rng_r - rng_t) <= 0.10,
                   "mean_rgb_dist_le_40": out["mean_rgb_dist"] <= 40}
    out["gate"]["pass"] = all(out["gate"].values())
    return out


def crop_for(dirname, name):
    return cs.candidate_crop(dirname, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass-dir", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--step1-picks", required=True)
    ap.add_argument("--step1-views", required=True)
    ap.add_argument("--stylize-report", required=True)
    ap.add_argument("--verify", required=True)
    ap.add_argument("--step1-palettes", required=True)
    a = ap.parse_args()
    rdir = os.path.join(a.pass_dir, "renders")
    target = Image.open(a.target).convert("RGB")
    rep = json.load(open(a.stylize_report, encoding="utf-8"))["models"]
    ver = json.load(open(a.verify, encoding="utf-8"))["files"]
    s1 = json.load(open(a.step1_palettes, encoding="utf-8"))["rows"]
    s1_pal = {r["cell"]: r["palette"] for g in s1.values() for r in g}
    metrics = {"label": f"BLENDER REVIEW foliage palette, {a.label} (Cycles CPU, step-1 light; not a Babylon capture)",
               "method": "compare_sheets.foliage_palette on the 1920x1080 player view inside the render's alpha mask "
                         "(hue 45-170 deg, sat >= 0.22, luminance p10/p50/p90); target = owner's foreground crop",
               "gate_rule": "each swatch within +/-0.08 luma of the target, swatch value range within 0.10, "
                            "mean RGB distance <= 40", "species": {}}
    GH = cs.GROUP_H
    rows = []
    for gname, picks in ROWS:
        cells = []
        for label, box, crown in cs.TARGET_TREES[gname]:
            cells.append((label, cs.scaled(target.crop(box), GH[gname]), cs.foliage_palette(target.crop(crown)),
                          "TARGET (concept)"))
        for model, sp in picks:
            crop0, mask0, _ = crop_for(a.step1_picks, model)
            pal0 = cs.foliage_palette(crop0, mask0)
            crop1, mask1, side1 = crop_for(rdir, f"{sp}_lod0")
            pal1 = cs.foliage_palette(crop1, mask1)
            r = rep[model]
            cells.append((f"{model} kit ({r['kit_triangles']:,} tris)", cs.scaled(crop0, GH[gname]), pal0,
                          "STEP 1 original"))
            cells.append((f"{sp} ({r['export']['lod0_tris']:,} / {r['export']['lod1_tris']:,})",
                          cs.scaled(crop1, GH[gname]), pal1, f"STYLIZED {a.label}"))
            metrics["species"][sp] = {"kit_model": model, "group": gname, "stylized": pal1, "step1_original": pal0,
                                      "step1_original_reported": s1_pal.get(model),
                                      "vs_target": compare(pal1, TARGET_REF[gname]),
                                      "step1_vs_target": compare(pal0, TARGET_REF[gname])}
        rows.append((gname, cells))
    # ---- target-vs-stylized sheet
    pad, label_h, sw_h = 10, 46, 34
    width = max(sum(c[1].width + pad for c in cells) + pad for _, cells in rows)
    height = 92 + sum(GH[g] + label_h + sw_h + 30 for g, _ in rows)
    sheet = Image.new("RGB", (width, height), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    d.text((14, 8), f"TARGET vs STYLIZED ({a.label})  -  target crops | step-1 kit original | stylized  -  BLENDER REVIEW, "
                    "not Babylon", fill=(255, 196, 64), font=cs.font(26, True))
    d.text((14, 46), "Same light and player camera as step 1 (13 m / 22.4 deg / FOV 1.02 rad, 1920x1080, Cycles CPU). "
                     "Every cell scaled to the same height. Swatches: foliage dark p10 / mid p50 / light p90.",
           fill=(220, 220, 220), font=cs.font(16))
    y = 92
    for gname, cells in rows:
        d.text((14, y), gname.upper(), fill=(255, 255, 255), font=cs.font(20, True))
        d.text((170, y + 3), "target swatches (gate): " + " / ".join(TARGET_REF[gname]), fill=(200, 200, 200),
               font=cs.font(14))
        y += 28
        x = pad
        for label, img, pal, tag in cells:
            sheet.paste(img, (x, y))
            d.rectangle([x, y, x + min(img.width, 300), y + 18], fill=(0, 0, 0))
            col = (140, 220, 255) if tag.startswith("TARGET") else ((200, 200, 200) if tag.startswith("STEP") else (255, 196, 64))
            d.text((x + 4, y + 1), tag, fill=col, font=cs.font(12, True))
            d.text((x + 2, y + GH[gname] + 4), label, fill=(235, 235, 235), font=cs.font(13, True))
            cs.swatch_row(d, x, y + GH[gname] + label_h - 18, pal, img.width)
            x += img.width + pad
        y += GH[gname] + label_h + sw_h
    p_tvs = os.path.join(a.pass_dir, "target-vs-stylized.png")
    sheet.save(p_tvs, optimize=True)
    # ---- contact sheet
    VW, VH, LW, G = 768, 432, 360, 6
    order = [sp for _, picks in ROWS for _, sp in picks]
    model_of = {sp: m for _, picks in ROWS for m, sp in picks}
    cs_img = Image.new("RGB", (LW + 3 * (VW + G) + G, 70 + len(order) * (VH + G)), (22, 24, 28))
    cd = ImageDraw.Draw(cs_img)
    cd.text((12, 10), f"CONTACT SHEET {a.label} - stylized Quaternius CC0 picks (LOD0)  |  BLENDER REVIEW (Cycles CPU, "
                      "step-1 light), not Babylon", fill=(255, 196, 64), font=cs.font(24, True))
    cd.text((12, 42), "Views: player 13 m / close 2-3 m / orthographic side elevation; 1.8 m capsule witness.",
            fill=(210, 210, 210), font=cs.font(15))
    for i, sp in enumerate(order):
        y0 = 70 + i * (VH + G)
        r = rep[model_of[sp]]
        v0 = ver[f"{sp}_lod0"]
        af, bf = r["after"], r["before"]
        lines = [(f"{sp}", (255, 255, 255), 20), (f"{model_of[sp]} - {r['slot']} {r['height_m']} m", (200, 200, 200), 14),
                 (f"tris LOD0 {r['export']['lod0_tris']:,} (kit {r['kit_triangles']:,})  LOD1 {r['export']['lod1_tris']:,}",
                  (230, 230, 230), 14)]
        if r["kind"] != "bush":
            lines += [(f"W/H {bf.get('crown_width_over_height')} -> {af.get('crown_width_over_height')}", (230, 230, 230), 14),
                      (f"crown base {bf.get('crown_base_p5_m')} -> {af.get('crown_base_p5_m')} m", (230, 230, 230), 14),
                      (f"trunk r@1m {bf.get('trunk_r_1m_m')} -> {af.get('trunk_r_1m_m')} m", (230, 230, 230), 14),
                      (f"flare {bf.get('flare_ground_over_1m')} -> {af.get('flare_ground_over_1m')}", (230, 230, 230), 14)]
        fn = r["steps"]["foliage_normals"]
        sh = r["steps"]["foliage_shading"]
        lines += [(f"clumps/tiers {af.get('clumps_or_tiers')}  cards {af.get('cards')}", (230, 230, 230), 14),
                  (f"normals dot proxy {fn['mean_dot_with_proxy_normal']}", (230, 230, 230), 14),
                  (f"COLOR_0 foliage {sh['color0_lum_min']}-{sh['color0_lum_max']}", (230, 230, 230), 14),
                  (f"read-back {'OK' if v0['all_ok'] else 'FAIL'}", (120, 230, 120) if v0["all_ok"] else (255, 120, 120), 15)]
        m = metrics["species"][sp]["vs_target"]
        if m:
            lines.append((f"palette vs target: mean RGB d {m['mean_rgb_dist']}  gate {'PASS' if m['gate']['pass'] else 'miss'}",
                          (120, 230, 120) if m["gate"]["pass"] else (255, 190, 90), 14))
        yy = y0 + 8
        for text, col, size in lines:
            cd.text((12, yy), text, fill=col, font=cs.font(size, size >= 20))
            yy += size + 9
        for j, view in enumerate(("player", "close", "side")):
            p = os.path.join(rdir, f"{sp}_lod0__{view}.png")
            if os.path.exists(p):
                cs_img.paste(Image.open(p).convert("RGB").resize((VW, VH)), (LW + G + j * (VW + G), y0))
    p_cs = os.path.join(a.pass_dir, "contact-sheet.png")
    cs_img.save(p_cs, optimize=True)
    # ---- greyscale silhouettes
    tiles = []
    for _, picks in ROWS:
        for model, sp in picks:
            for tag, dirn, name in (("step 1", a.step1_views, model), ("stylized", rdir, f"{sp}_lod0")):
                side = json.load(open(os.path.join(dirn, f"{name}__views.json"), encoding="utf-8"))
                info = side["views"]["player"]
                img = Image.open(os.path.join(dirn, f"{name}__player.png")).convert("L")
                bb = info["tree_bbox_px"]
                fx, fy = info["witness_feet_px"]
                box = (int(max(0, min(bb["x0"], fx - 14) - 8)), int(max(0, bb["y0"] - 8)),
                       int(min(img.width, max(bb["x1"], fx + 14) + 8)), int(min(img.height, max(bb["y1"], fy) + 8)))
                c = img.crop(box)
                tiles.append((f"{tag}: {name}", c.resize((c.width * 2, c.height * 2), Image.LANCZOS)))
            crop1, mask1, _ = crop_for(rdir, f"{sp}_lod0")
            sil = Image.new("L", mask1.size, 235)
            sil.paste(30, (0, 0), mask1)
            tiles.append((f"silhouette: {sp}", cs.scaled(sil, 260)))
    targets_l = [("TARGET " + lab.replace("target: ", ""), target.crop(box).convert("L"))
                 for lab, box, _ in cs.TARGET_TREES["broadleaf"] + cs.TARGET_TREES["pines"]]
    max_w, gp = 2600, 12

    def flow(ts):
        out, cur, w = [], [], gp
        for t in ts:
            if cur and w + t[1].width + gp > max_w:
                out.append(cur)
                cur, w = [], gp
            cur.append(t)
            w += t[1].width + gp
        if cur:
            out.append(cur)
        return out
    trs, crs = flow(targets_l), flow(tiles)
    hgt = 80 + sum(max(t[1].height for t in r) + 30 for r in trs) + 30 + sum(max(t[1].height for t in r) + 30 for r in crs)
    g = Image.new("L", (max_w, hgt), 30)
    gd = ImageDraw.Draw(g)
    gd.text((12, 8), f"GREYSCALE @ 13 m player view ({a.label}) - luminance only; step-1 original vs stylized at the same "
                     "x2 scale (1.8 m witness), plus the alpha silhouette", fill=235, font=cs.font(22, True))
    y = 80
    for r_ in trs + [None] + crs:
        if r_ is None:
            gd.text((12, y), "BLENDER REVIEW: step-1 kit original | stylized | silhouette (black = tree)", fill=235,
                    font=cs.font(16, True))
            y += 30
            continue
        x = gp
        for lab, img in r_:
            g.paste(img, (x, y))
            gd.text((x, y + img.height + 3), lab, fill=220, font=cs.font(12))
            x += img.width + gp
        y += max(t[1].height for t in r_) + 30
    p_g = os.path.join(a.pass_dir, "greyscale.png")
    g.save(p_g, optimize=True)
    metrics["outputs"] = {"target_vs_stylized": p_tvs, "contact_sheet": p_cs, "greyscale": p_g}
    with open(os.path.join(a.pass_dir, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=1)
    for sp, v in metrics["species"].items():
        m = v["vs_target"]
        if m:
            print(f"{sp:16s} p10 {m['dark_p10']['render']} ({m['dark_p10']['d_luma']:+.3f})  p50 {m['mid_p50']['render']} "
                  f"({m['mid_p50']['d_luma']:+.3f})  p90 {m['light_p90']['render']} ({m['light_p90']['d_luma']:+.3f})  "
                  f"range {m['swatch_value_range']['render']:.3f}/{m['swatch_value_range']['target']:.3f}  "
                  f"rgbd {m['mean_rgb_dist']:5.1f}  {'PASS' if m['gate']['pass'] else 'miss'}")
    print("WROTE", p_tvs, p_cs, p_g)


if __name__ == "__main__":
    main()
