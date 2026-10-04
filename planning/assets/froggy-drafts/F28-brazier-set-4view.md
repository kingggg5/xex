[Claude -> froggy | 2026-10-03 | F28]

TASK F28: brazier set for bridges and gates: 4-view turnarounds (new design)

Status: DRAFT from the ref-look lane. Claude main reviews and sends it; nothing has been sent.

Attach before sending:
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (style and lighting only);
- the look-target doc `docs/reviews/2026-10-03-reference-look-target-v2.md` §6 and §10 (as text, for context).

Do NOT attach the owner's third-party screenshots (`references/owner-aaa-20261002`). They are study-only and never inputs (llm.txt rule 11). The design below is our own; do not imitate any existing game's character, statue, logo or costume.

Why: the bridge and gate references use braziers to frame thresholds and add warm light. Our bridge/gate kit (Codex props-craft) needs a brazier every 8-12 m. A Blender kit is preferred; fire is a VFX flipbook, not geometry.

Design: three pieces sharing one stone-and-iron language:
- pillar brazier: a 1.2 m square cream-stone pillar with a chamfered cap and a 0.9 m wide wrought-iron bowl (thick rim, 4 leaf-shaped supports), coals painted inside;
- tripod bowl: 1.1 m tall, three thick iron legs, a 0.7 m bowl;
- wall cresset: an iron cage basket on a bracket, 0.5 m, with the cage drawn as solid bands over a dark painted interior (no see-through gaps).

Materials: cream stone (#E8D9BC) with soot darkening on the upper 30 %, iron (#3A3A40) with warm worn edges, coals #2A1A12 with ember orange (#E07A2E) painted only in the bowl.

Xexoria shared palette (use these families; small hue variation is welcome): warm cream stone #E8D9BC, sandstone #D9B98C, dark timber #4A3426, sapphire #2B4F86, slate blue #3E5A7A, terracotta #B8603F, restrained gold #C9A04A (accents only, at most 5 % of the object), moss #6F7F2E.

Budget: at most 1,500 triangles each; one shared stone/iron atlas. No rig.

Views and files (TASK F6 rules, so Tripo P2.0 multi-view and `tools/art/turnaround_qa.py` accept them):
- front.png, back.png, left.png (the object's own left side, facing screen-left), right.png (facing screen-right): 2048x2048 each, pure white #FFFFFF background, no shadows, no text;
- the object fills about 80 % of the frame height; same camera distance and the same ground line in all four views; orthographic look, camera at mid-height;
- no part thinner than 3 % of the frame (about 61 px at 2048); no see-through holes (paint openings as dark recessed panels); no floating parts;
- small hardware (rivets, nails, studs, stitching) is painted colour detail, never raised geometry;
- hero34.png: one lit three-quarter view in the game look (warm key from the upper left, soft blue sky fill, painted AO in crevices, crisp edge highlights), texture reference only;
- palette.png with the hex values you used.

Set naming: this is a set, so prefix every file with the piece id: pillar_front.png ..., tripod_front.png ..., cresset_front.png ..., and one hero34 per piece.

Deliver `turnarounds_brazier_set_v1.zip`: the PNGs above, palette.png, README.md and receipt.json.

Checklist (PASS/FAIL in the README; Claude re-runs `tools/art/turnaround_qa.py` on delivery, and a FAIL means another round, at most 3):
1. the bowl rims are thick (at least 3 % of the frame);
2. no flames drawn (empty, coal-filled bowls);
3. soot reads as a painted gradient, not noise;
4. white background, no text, no shadows;
5. the design is original: no element copied from another game's statue, character, logo or costume.

Self-review before you deliver (at least 3 passes; list each pass's fixes in the README):
1. Silhouette: shrink the front view to 64 px tall in greyscale. It must still read as the intended object at a 13 m game camera.
2. Views: left is the mirror outline of right; back is the mirror outline of front, except for any asymmetry listed in the README. Heights equal within 3 %.
3. Style: chunky, bevelled, hand-painted forms; values never pure black or pure white; the hero view's palette matches the palette above.

Report format (README.md inside the zip): the pose, the size in metres, the materials per part, the intended asymmetry (or none), the checklist below with PASS/FAIL, and the 3 self-review passes. receipt.json: the file list, pixel sizes, palette hex values, and the licence note "generated for Xexoria".

Approval: none needed for these images. Any Tripo job made from them needs Claude's design review, a `turnaround_qa.py` PASS and the owner's credit ceiling (credit guard §4).
