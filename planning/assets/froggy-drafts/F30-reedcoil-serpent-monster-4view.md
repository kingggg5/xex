[Claude -> froggy | 2026-10-03 | F30]

TASK F30: monster "Reedcoil": 4-view turnaround (new design)

Status: DRAFT from the ref-look lane. Claude main reviews and sends it; nothing has been sent.

Attach before sending:
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (style and lighting only);
- the look-target doc `docs/reviews/2026-10-03-reference-look-target-v2.md` §6 and §10 (as text, for context).

Do NOT attach the owner's third-party screenshots (`references/owner-aaa-20261002`). They are study-only and never inputs (llm.txt rule 11). The design below is our own; do not imitate any existing game's character, statue, logo or costume.

Why: the harbour reference shows serpents bursting from the ground, a strong encounter idea for Brightwater Cove. Reedcoil is our own creature: a cove serpent that erupts from sand or shallow water.

Design (original; not a purple bone-spiked worm):
- a thick segmented serpent; the visible emerged body is 4.5 m tall and 0.7 m thick, tapering to the buried tail;
- 16-20 overlapping shell plates along the back in sand-gold (#C9A86A) over a teal-green belly (#2F6E6A) with cream underside bands;
- a row of broad **reed-fin crests** along the spine (solid paddle shapes, at least 3 % of the frame wide), fading from teal to sapphire (#2B4F86) at the tips;
- a blunt eel head with a wide hinged jaw, small rounded teeth painted as a cream band, and two small amber eyes;
- views: a straight, upright neutral pose so the rig can bend it (a slight S-curve is allowed only in hero34).

Materials: a wet sheen on the belly (low roughness), dry matte plates; barnacle clusters painted only.

Xexoria shared palette (use these families; small hue variation is welcome): warm cream stone #E8D9BC, sandstone #D9B98C, dark timber #4A3426, sapphire #2B4F86, slate blue #3E5A7A, terracotta #B8603F, restrained gold #C9A04A (accents only, at most 5 % of the object), moss #6F7F2E.

Budget after Tripo: 5,000-8,000 triangles. Est. ~145 credits. Rig: a spine chain of 20-24 bones, a jaw bone and two fin-control bones. Clips: emerge (bursts from the ground, with a hook for the sand/water VFX), idle_sway, bite, spit, hit, submerge, death.

Views and files (TASK F6 rules, so Tripo P2.0 multi-view and `tools/art/turnaround_qa.py` accept them):
- front.png, back.png, left.png (the object's own left side, facing screen-left), right.png (facing screen-right): 2048x2048 each, pure white #FFFFFF background, no shadows, no text;
- the object fills about 80 % of the frame height; same camera distance and the same ground line in all four views; orthographic look, camera at mid-height;
- no part thinner than 3 % of the frame (about 61 px at 2048); no see-through holes (paint openings as dark recessed panels); no floating parts;
- small hardware (rivets, nails, studs, stitching) is painted colour detail, never raised geometry;
- hero34.png: one lit three-quarter view in the game look (warm key from the upper left, soft blue sky fill, painted AO in crevices, crisp edge highlights), texture reference only;
- palette.png with the hex values you used.

Deliver `turnarounds_reedcoil_serpent_monster_v1.zip`: the PNGs above, palette.png, README.md and receipt.json.

Checklist (PASS/FAIL in the README; Claude re-runs `tools/art/turnaround_qa.py` on delivery, and a FAIL means another round, at most 3):
1. the neutral pose is straight and identical across views;
2. the fins and plates read at 64 px;
3. the jaw is closed in the turnaround and open only in hero34;
4. no holes, white background, no text;
5. the design is original: no element copied from another game's statue, character, logo or costume.

Self-review before you deliver (at least 3 passes; list each pass's fixes in the README):
1. Silhouette: shrink the front view to 64 px tall in greyscale. It must still read as the intended object at a 13 m game camera.
2. Views: left is the mirror outline of right; back is the mirror outline of front, except for any asymmetry listed in the README. Heights equal within 3 %.
3. Style: chunky, bevelled, hand-painted forms; values never pure black or pure white; the hero view's palette matches the palette above.

Report format (README.md inside the zip): the pose, the size in metres, the materials per part, the intended asymmetry (or none), the checklist below with PASS/FAIL, and the 3 self-review passes. receipt.json: the file list, pixel sizes, palette hex values, and the licence note "generated for Xexoria".

Approval: none needed for these images. Any Tripo job made from them needs Claude's design review, a `turnaround_qa.py` PASS and the owner's credit ceiling (credit guard §4).
