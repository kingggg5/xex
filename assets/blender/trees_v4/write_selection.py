"""Write selection.json for Route A step 1 (trees v4): picks, slot metrics, reasons and stylization fixes.

System Python + numpy. Numbers come from measure.json (Blender measurement) and target-vs-candidates.json
(palette sampling of the BLENDER REVIEW renders and the target crops); the reasons and fix lists are the
reviewer's judgement against docs/reviews/2026-10-02-trees-free-assets-decision.md sections 4.1-4.4.

Usage:
  python write_selection.py --evidence <route-a dir>
"""
import argparse
import json
import os

import numpy as np

SPEC = {  # slot: (height m, trunk r at 1 m min, crown base range, crown W/H range, flare range)
    "broadleaf S": (5.5, 0.25, (2.2, 3.0), (0.8, 1.1), (1.8, 2.2)),
    "broadleaf M": (7.5, 0.32, (2.2, 3.0), (0.8, 1.1), (1.8, 2.2)),
    "broadleaf L": (9.5, 0.42, (2.2, 3.0), (0.8, 1.1), (1.8, 2.2)),
    "conifer M": (8.0, 0.22, (1.6, 2.4), (0.45, 0.6), (1.6, 1.6)),
    "conifer L": (12.0, 0.30, (1.6, 2.4), (0.45, 0.6), (1.6, 1.6)),
    "bush": (1.2, None, None, None, None),
}
COMMON_PALETTE = ("replace the flat leaf colour with a painted cluster atlas (4-6 clusters, 8-20 leaves each, top-light "
                  "gradient), graded to the decision-doc start palette, then locked against the target crops")


def slot_metrics(M, P, m, slot):
    h, rspec, cb, wh, fl = SPEC[slot]
    sh = M[m]["shape_at_target"]
    k = h / sh["target_height_m"]
    pm = M[m]["per_material"]
    out = {"slot": slot, "height_m": h, "triangles": M[m]["triangles_total"],
           "bark_tris": sum(v["triangles"] for v in pm.values() if v["kind"] == "bark"),
           "foliage_tris": sum(v["triangles"] for v in pm.values() if v["kind"] == "foliage"),
           "crown_width_over_height": sh.get("crown_width_over_height")}
    if sh.get("bark_sections_at_target"):
        secs = {s["height_m"]: s["main_r_m"] for s in sh["bark_sections_at_target"]}
        hs = sorted(secs)
        rs = [secs[x] for x in hs]
        r1 = float(np.interp(1.0 / k, hs, rs)) * k
        r0 = float(np.interp(0.05 / k, hs, rs)) * k
        out.update({"trunk_r_1m_m": round(r1, 3), "trunk_spec_min_m": rspec, "trunk_ok": r1 >= rspec - 1e-3,
                    "flare_ground_over_1m": round(r0 / r1, 2), "flare_spec": list(fl), "flare_ok": r0 / r1 >= fl[0]})
    if cb and sh.get("crown_base_m_p5") is not None:
        c = sh["crown_base_m_p5"] * k
        out.update({"crown_base_p5_m": round(c, 2), "crown_base_spec_m": list(cb), "crown_base_ok": cb[0] <= c <= cb[1]})
    if wh:
        out.update({"crown_width_spec": list(wh), "crown_width_ok": wh[0] <= sh["crown_width_over_height"] <= wh[1]})
    fol = [v for v in pm.values() if v["kind"] == "foliage"]
    if fol:
        out["foliage_normals_outward_dot"] = round(float(np.mean([v["normals"]["mean_dot_with_outward_radial"] for v in fol])), 3)
        c = fol[0].get("cards_at_target_scale")
        if c:
            out["card_diag_m_at_slot"] = round(c["diag_m_median"] * k, 2)
            out["cards"] = sum(v.get("cards_at_target_scale", {}).get("count", 0) for v in fol)
    pal = P.get(m)
    out["rendered_foliage_palette_p10_p50_p90"] = [pal["dark_p10"], pal["mid_p50"], pal["light_p90"]] if pal else None
    out["rendered_foliage_value_range"] = pal["value_range_p90_minus_p10"] if pal else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    args = ap.parse_args()
    M = json.load(open(os.path.join(args.evidence, "measure.json"), encoding="utf-8"))["models"]
    rows = json.load(open(os.path.join(args.evidence, "target-vs-candidates.json"), encoding="utf-8"))["rows"]
    P = {r["cell"]: r["palette"] for g in rows.values() for r in g}
    picks = [
        ("CommonTree_2", "broadleaf S", "broadleaf S 5.5 m",
         ["clearest clump structure in the kit: 3-4 separate leaf masses on visible forked limbs with sky gaps, so not a "
          "ball canopy and not shelves (4.4)",
          "at S every 4.1 number except crown width and flare is in spec: crown base 2.66 m, trunk r 0.27 m at 1 m",
          "5,648 tris, already inside the 4-6k LOD0 band"],
         {"palette_regrade": COMMON_PALETTE + "; canopy shadow #2F6B3E, mid #6FA83C, highlight #B5D65A (target highlights "
                                              "reach #D4CD4E); bark #8B5942 -> #6B4A32 / #9A7350",
          "color_0_gradient": "foliage 0.55-0.70 inside/underside -> 1.0 top/outside, +/-4 % hue per clump; raise the baked "
                              "bark base ramp from 0.10 to >= 0.50",
          "normals_from_proxies": "Data Transfer from 3-4 clump ellipsoids, mix 0.9 (kit normals are already bent, outward "
                                  "dot 0.46, but not clump-shaped)",
          "trunk_root_flare": "add flare x1.8-2.0 over the bottom 0.5 m with 4-5 buttresses (now x1.49); trunk radius is fine",
          "card_visibility": "cards are ~1.0 m squares at S carrying ~12 big leaves: no straight edges at 13 m, but leaves read "
                             "oversized close up; repaint the cluster with 8-20 smaller leaves, alpha cutoff 0.45 (kit 0.2), "
                             "check alpha on every mip",
          "budget_decimation": "bark is 4,310 tris (76 %): decimate hidden limbs ~35 % to free ~1.5k for 2-3 extra clumps; "
                               "LOD1 <= 1.6k",
          "shape": "widen the crown x1.35 radially above the first split (W/H 0.59 -> >= 0.8)"}),
        ("CommonTree_5", "broadleaf M", "broadleaf M 7.5 m",
         ["compact lumpy 3-clump crown with gaps (not a ball, not shelves)",
          "trunk r 0.35 m at 1 m meets M and it has the strongest flare in the set (x1.52)",
          "cheapest broadleaf (3,182 tris): ~2.5k headroom for the clumps its crown needs"],
         {"palette_regrade": COMMON_PALETTE + "; same canopy and bark targets as CommonTree_2",
          "color_0_gradient": "as CommonTree_2",
          "normals_from_proxies": "3 existing clumps + 3-5 added clumps as ellipsoid proxies, mix 0.9",
          "trunk_root_flare": "flare x1.52 -> x1.8-2.0 with 4-6 buttresses",
          "card_visibility": "cards ~1.4 m squares at M (median diagonal 2.0 m): same repaint and cutoff as CommonTree_2",
          "budget_decimation": "add clumps up to 4.5-5.5k; bark (1,882 tris) needs no decimation",
          "shape": "crown base 3.40 m > 3.0: Z-compress the bare trunk below the first split ~15 % or add 1-2 low clumps; "
                   "widen the crown x1.4 to W/H >= 0.8"}),
        ("CommonTree_1", "broadleaf L", "broadleaf L 9.5 m",
         ["fullest, lushest crown in the kit (960 cards), closest to the target's dense foreground broadleaf",
          "trunk r 0.54 m at 1 m at L (spec 0.42)"],
         {"palette_regrade": COMMON_PALETTE + "; same canopy and bark targets",
          "color_0_gradient": "as CommonTree_2; the dense crown needs the strongest inner darkening (0.55) so it does not read "
                              "as one flat ball",
          "normals_from_proxies": "6-8 clump ellipsoids, mix 0.9; open 2-3 sky gaps by deleting ~10 % of the inner cards",
          "trunk_root_flare": "flare x1.32 at L -> x1.8-2.2 with 5-6 buttresses",
          "card_visibility": "as CommonTree_2",
          "budget_decimation": "6,265 tris is over the 6k LOD0 cap: decimate bark 4,345 -> ~2,600 (-40 %) to land at 4.6-5.5k "
                               "with the extra clumps; LOD1 <= 1.6k",
          "shape": "crown base 4.16 m at L > 3.0: add low limbs/clumps or compress the bare trunk; widen x1.3 (W/H 0.63 -> "
                   ">= 0.8)"}),
        ("Pine_2", "conifer M", "conifer M 8 m",
         ["most target-like conifer: full stacked drooping tiers with jagged tips and an upturned top (4.1 conifer shape)",
          "crown base 2.33 m, inside 1.6-2.4", "3,648 tris, inside 2.5-5k"],
         {"palette_regrade": "replace the flat #335800 tier card with a painted tier atlas with light-tipped edges, graded to "
                             "#1D4A35 / #2E6B3F / #6FA65A (target tips reach #B4B859)",
          "color_0_gradient": "0.55 inside/under each tier -> 1.0 at the tips (rendered value range now 0.15 vs target 0.49-0.55)",
          "normals_from_proxies": "needed: card normals are nearly flat (outward dot 0.36); transfer from one cone per tier, "
                                  "mix 0.85-1.0",
          "trunk_root_flare": "trunk r 0.18 m < 0.22 spec (the 'thinner than spec' fail): thicken x1.25 below the first tier; "
                              "flare x1.33 -> x1.6",
          "card_visibility": "tier cards ~1.1 m, fine at 13 m; trim or hide the two bare lower limbs under the first tier",
          "budget_decimation": "bark/branches are 2,878 tris (79 %), mostly hidden inside the tiers: decimate ~40 %; LOD1 <= 1.4k",
          "shape": "W/H 0.77 is wider than the 0.45-0.6 spec but close to the target crops (they read ~0.6-0.75); narrow the "
                   "skirt by 10 % at most"}),
        ("Pine_5", "conifer L", "conifer L 12 m",
         ["densest tiers and cleanest cone; the only pine whose trunk meets spec (r 0.22 m at 8 m, 0.37 m at 12 m)",
          "1,646 tris leaves room for the 1-2 extra low tiers that also fix its crown base at L"],
         {"palette_regrade": "as Pine_2", "color_0_gradient": "as Pine_2",
          "normals_from_proxies": "as Pine_2 (outward dot 0.36)",
          "trunk_root_flare": "flare x1.38 at 12 m (x1.53 at 8 m) -> x1.6", "card_visibility": "as Pine_2",
          "budget_decimation": "add 1-2 low drooping tiers (~+800 tris) to reach the 2.5-5k band; LOD1 <= 1.4k",
          "shape": "crown base 3.4 m at L > 2.4: the added low tiers bring it to <= 2.4 m; the slight trunk lean is acceptable"}),
        ("Bush_Common_Flowers", "bush", "flowering bush 1.2 m (preferred)",
         ["the only flowering bush in the Standard edition; dense lumpy dome", "leaf-card normals already spherical (outward dot 0.74; flower cards 0.53)",
          "green leaves from the same atlas as the broadleaf picks"],
         {"palette_regrade": "canopy palette as the broadleaf; move the flower-card UVs from the purple cell to the red/pink "
                             "cell of Flowers.png (target bushes carry red flowers; no new texture)",
          "color_0_gradient": "0.6 at the base/inside -> 1.0 on top",
          "normals_from_proxies": "optional: 2-3 clump proxies to break the single dome (spec 2-4 clumps)",
          "trunk_root_flare": "n/a", "card_visibility": "cards ~0.6 m, fine",
          "budget_decimation": "1,368 tris > 900 budget: merge leaf cards 450 -> ~280 and simplify the 38 flower cards "
                               "(468 tris) to <= 900 in total",
          "shape": "W/H 1.44 dome, fine for 0.8-1.6 m bushes"}),
        ("Bush_Common", "bush", "plain bush 1.2 m",
         ["same dome geometry at 900 tris (inside 300-900)", "simplest filler; pairs with the flowering variant"],
         {"palette_regrade": "ships with the red Leaves_TwistedTree material (#A71717, reads as autumn): swap to the green "
                             "cluster atlas or regrade to the canopy palette",
          "color_0_gradient": "as Bush_Common_Flowers", "normals_from_proxies": "optional, as Bush_Common_Flowers",
          "trunk_root_flare": "n/a", "card_visibility": "fine",
          "budget_decimation": "at the 900 ceiling: trim ~25 % of the cards (~650 tris) for headroom",
          "shape": "as Bush_Common_Flowers"}),
    ]
    sel = {
        "label": "SELECTION from BLENDER REVIEW evidence (not Babylon captures); numbers from measure.json and "
                 "target-vs-candidates.json",
        "spec": "docs/reviews/2026-10-02-trees-free-assets-decision.md 4.1 (shapes), 4.2 (foliage), 4.3 (budgets), 4.4 (fail list)",
        "target_reference_from_crops": {"broadleaf_p10_p50_p90": ["#223313", "#717C2A", "#D4CD4E"], "broadleaf_value_range": [0.542, 0.621],
                                        "pines_p10_p50_p90": ["#17271B", "#546632", "#B4B859"], "pines_value_range": [0.494, 0.55],
                                        "bushes_value_range": [0.409, 0.546]},
        "kit_facts_shared_by_all_picks": {
            "leaf_textures": "single flat colour + alpha: Leaves_NormalTree_C #587B00 (1024^2, 22.7 % coverage), Leaf_Pine_C "
                             "#335800 (2048^2 for one branch silhouette, 29.3 % coverage), Leaves_TwistedTree_C #A71717 (1024^2)",
            "foliage_COLOR_0": "constant 1.0 on every model (no gradient)",
            "bark_COLOR_0": "baked ground-up darkening, linear 0.10 at the base to 1.0 above ~30 % height; Babylon multiplies "
                            "COLOR_0 into albedo, so trunk bases go near-black",
            "bark_texture": "Bark_NormalTree 2048^2 painted vertical strokes, mean #8B5942 (warmer/redder than the doc's bark "
                            "mid #6B4A32) + 2048^2 OpenGL normal map",
            "materials": "2 per tree (bark, foliage), alphaMode MASK cutoff 0.2 (runtime contract 0.4-0.5), doubleSided, "
                         "roughness 1, metallic 0",
            "pivot": "origin = ground plane; trunks/cards continue 0.20-0.34 m below it (buried skirt)",
            "uv_and_attributes": "one UV map (TEXCOORD_0) and COLOR_0; no TEXCOORD_1 (wind data must be added)"},
        "picks": [{"model": m, "role": role, "metrics": slot_metrics(M, P, m, slot), "why": why, "fixes": fixes}
                  for m, slot, role, why, fixes in picks],
        "not_picked": {
            "CommonTree_3": "narrow columnar crown (W/H 0.45) and trunk 0.29 m < 0.32 at M; alternate for S",
            "CommonTree_4": "lollipop: crown base 5.4 m, 786 foliage tris on spindly limbs; fails crown base, reads as a stick",
            "Pine_1": "bare dead lower limbs, crown base 3.31 m, 80 % of tris in bark",
            "Pine_3": "sparse; bare trunk with dead side branches up to 4.1 m",
            "Pine_4": "good slender alternate (W/H 0.56 and flare x1.61 meet spec) but trunk 0.18 m is thin and crown base 2.81 m high",
            "TwistedTree_1-5": "9,134-10,104 tris (needs >= 10 % decimation for the <= 9k hero), red leaves; measured only",
            "DeadTree_1-5": "later biomes; measured only"},
        "verdict_vs_target": (
            "As shipped, no kit model reaches the target. The kit gives usable structure (tapered trunks, forked limbs, clumped "
            "crowns, drooping conifer tiers, sane budgets) but not the look: leaf textures are single flat colours, foliage "
            "COLOR_0 is white, the rendered foliage value range is 0.15-0.26 against the target's 0.49-0.62, highlights never "
            "reach the target's warm yellow-green, broadleaf crowns are ~40 % too narrow (W/H 0.41-0.63 vs 0.8-1.1), crown "
            "bases sit 0.4-2.4 m too high at M, and root flare is x1.2-1.6 vs x1.8-2.2. Route A can pass the 4.4 gate only "
            "through the full 4.2 stylization pass; if crown widening fails, take broadleaf crowns from Route B (EZ-Tree) and "
            "keep the kit's pines and bushes."),
    }
    out = os.path.join(args.evidence, "selection.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sel, fh, indent=1, ensure_ascii=False)
    for p in sel["picks"]:
        mt = p["metrics"]
        print(p["model"], p["role"], {k: mt.get(k) for k in ("triangles", "trunk_r_1m_m", "flare_ground_over_1m",
                                                              "crown_base_p5_m", "crown_width_over_height",
                                                              "foliage_normals_outward_dot", "rendered_foliage_value_range")})
    print("WROTE", out)


if __name__ == "__main__":
    main()
