[Claude -> froggy | 2026-10-03 | F26]

TASK F26: market stall set: 4-view turnarounds of 3 stalls + goods (new design)

Status: DRAFT from the ref-look lane. Claude main reviews and sends it; nothing has been sent.

Attach before sending:
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (style and lighting only);
- the look-target doc `docs/reviews/2026-10-03-reference-look-target-v2.md` §6 and §10 (as text, for context).

Do NOT attach the owner's third-party screenshots (`references/owner-aaa-20261002`). They are study-only and never inputs (llm.txt rule 11). The design below is our own; do not imitate any existing game's character, statue, logo or costume.

Why: the references show lived-in market clusters (striped awnings, produce crates). Our city market and Brightwater Cove need 3-5 varied stalls placed as working clusters, never in a row. These sheets are the concept for a Blender kit (Codex props-craft lane, 0 credits); Tripo is optional, only for the produce crate.

Design: three stall variants that share one timber frame language:
- A: 2.4 m wide x 1.6 m deep, 2.6 m to the awning top; 4 square posts (0.14 m), a plank counter at 0.95 m, a sloped striped awning with a scalloped front valance;
- B: 3.0 m wide, an L-shaped counter, a flat cloth canopy on two poles, hanging herb bundles (solid clumps); no guy ropes;
- C: a hand-cart stall, 2.0 m long, two spoked wheels drawn as solid discs with painted spokes, a small peaked awning;
- goods sheet: a slatted crate (0.6 x 0.4 x 0.35 m) of apples, one of carrots, a woven basket of bread, two clay jars, a fish tray for the cove variant.

Materials: dark timber (#4A3426) with lighter worn edges; awnings in Xexoria stripes: sapphire/cream for A, terracotta/cream for B, slate/cream for C (never orange/yellow); produce in natural colours with moderate saturation (in-game crop target sat p50 0.45-0.65).

Xexoria shared palette (use these families; small hue variation is welcome): warm cream stone #E8D9BC, sandstone #D9B98C, dark timber #4A3426, sapphire #2B4F86, slate blue #3E5A7A, terracotta #B8603F, restrained gold #C9A04A (accents only, at most 5 % of the object), moss #6F7F2E.

Budget: each stall at most 4,000 triangles; each crate or basket with goods at most 1,200; the whole set shares one timber/cloth atlas and one goods atlas. Awning flutter comes from vertex wind in-engine (no rig).

Views and files (TASK F6 rules, so Tripo P2.0 multi-view and `tools/art/turnaround_qa.py` accept them):
- front.png, back.png, left.png (the object's own left side, facing screen-left), right.png (facing screen-right): 2048x2048 each, pure white #FFFFFF background, no shadows, no text;
- the object fills about 80 % of the frame height; same camera distance and the same ground line in all four views; orthographic look, camera at mid-height;
- no part thinner than 3 % of the frame (about 61 px at 2048); no see-through holes (paint openings as dark recessed panels); no floating parts;
- small hardware (rivets, nails, studs, stitching) is painted colour detail, never raised geometry;
- hero34.png: one lit three-quarter view in the game look (warm key from the upper left, soft blue sky fill, painted AO in crevices, crisp edge highlights), texture reference only;
- palette.png with the hex values you used.

Set naming: this is a set, so prefix every file with the piece id: stallA_front.png ... stallC_right.png, goods_front.png etc., and one hero34 per stall (stallA_hero34.png ...). The goods sheet may show all goods side by side in each view.

Deliver `turnarounds_market_stall_set_v1.zip`: the PNGs above, palette.png, README.md and receipt.json.

Checklist (PASS/FAIL in the README; Claude re-runs `tools/art/turnaround_qa.py` on delivery, and a FAIL means another round, at most 3):
1. each stall has front/back/left/right at the same scale, with a 1.8 m human silhouette on a separate reference sheet;
2. the three stalls have clearly different silhouettes;
3. the awning stripes are 0.25-0.35 m wide so they read at 13 m;
4. goods are grouped, readable shapes;
5. white background, no text, no shadows;
6. the design is original: no element copied from another game's statue, character, logo or costume.

Self-review before you deliver (at least 3 passes; list each pass's fixes in the README):
1. Silhouette: shrink the front view to 64 px tall in greyscale. It must still read as the intended object at a 13 m game camera.
2. Views: left is the mirror outline of right; back is the mirror outline of front, except for any asymmetry listed in the README. Heights equal within 3 %.
3. Style: chunky, bevelled, hand-painted forms; values never pure black or pure white; the hero view's palette matches the palette above.

Report format (README.md inside the zip): the pose, the size in metres, the materials per part, the intended asymmetry (or none), the checklist below with PASS/FAIL, and the 3 self-review passes. receipt.json: the file list, pixel sizes, palette hex values, and the licence note "generated for Xexoria".

Approval: none needed for these images. Any Tripo job made from them needs Claude's design review, a `turnaround_qa.py` PASS and the owner's credit ceiling (credit guard §4).
