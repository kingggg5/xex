[Claude -> froggy | 2026-10-03 | F25]

TASK F25: plaza statue "Lantern Warden": 4-view turnaround (new design)

Status: DRAFT from the ref-look lane. Claude main reviews and sends it; nothing has been sent.

Attach before sending:
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (style and lighting only);
- the look-target doc `docs/reviews/2026-10-03-reference-look-target-v2.md` §6 and §10 (as text, for context).

Do NOT attach the owner's third-party screenshots (`references/owner-aaa-20261002`). They are study-only and never inputs (llm.txt rule 11). The design below is our own; do not imitate any existing game's character, statue, logo or costume.

Why: the owner wants the starter city to match the grandeur of paired guardian statues on a plaza approach. Jev ranked this as the most valuable new model (p 0.96). Two copies flank the main approach into the fountain plaza, at least 10 m apart. It must not duplicate the fountain's own guardian figure.

Design (original Xexoria; not an armoured angel with a spear):
- a robed sentinel kneeling on one knee on a square plinth; head bowed under a deep hood; the face is hidden in shadow apart from a calm carved jaw;
- a **wing-cloak**: two large stone wings folded forward around the shoulders like a cloak, with 5-6 broad feather groups per wing (never thin individual feathers);
- both hands raise a **sun-disc lantern** at chest height: a round gold-trimmed cage with a sapphire glass core (the core will glow at night in-engine);
- the robe's hem flows over the plinth edge; a small Xexoria crest beast is carved on the plinth front (our own crest beast head; no wings, no caduceus);
- plinth 1.6 m x 1.6 m x 1.2 m high, a simple stepped base with sapphire inlay strips; statue 4.4 m from the plinth top, so 5.6 m in total.

Materials: weathered cream stone (#E8D9BC to #CBB894) with darker cavities, moss only on the top faces of the wings and plinth, bronze-gold lantern frame (#C9A04A), sapphire glass (#2B4F86 to a #6FA3E0 core).

Xexoria shared palette (use these families; small hue variation is welcome): warm cream stone #E8D9BC, sandstone #D9B98C, dark timber #4A3426, sapphire #2B4F86, slate blue #3E5A7A, terracotta #B8603F, restrained gold #C9A04A (accents only, at most 5 % of the object), moss #6F7F2E.

Budget after Tripo: LOD0 at most 4,000 triangles with a normal map baked from the high-poly result; LOD1 1,500; LOD2 500; a box collider proxy for the plinth. Est. Tripo ~135 credits. No rig.

Views and files (TASK F6 rules, so Tripo P2.0 multi-view and `tools/art/turnaround_qa.py` accept them):
- front.png, back.png, left.png (the object's own left side, facing screen-left), right.png (facing screen-right): 2048x2048 each, pure white #FFFFFF background, no shadows, no text;
- the object fills about 80 % of the frame height; same camera distance and the same ground line in all four views; orthographic look, camera at mid-height;
- no part thinner than 3 % of the frame (about 61 px at 2048); no see-through holes (paint openings as dark recessed panels); no floating parts;
- small hardware (rivets, nails, studs, stitching) is painted colour detail, never raised geometry;
- hero34.png: one lit three-quarter view in the game look (warm key from the upper left, soft blue sky fill, painted AO in crevices, crisp edge highlights), texture reference only;
- palette.png with the hex values you used.

Deliver `turnarounds_plaza_lantern_warden_statue_v1.zip`: the PNGs above, palette.png, README.md and receipt.json.

Checklist (PASS/FAIL in the README; Claude re-runs `tools/art/turnaround_qa.py` on delivery, and a FAIL means another round, at most 3):
1. the 4 views and hero34 show the same design, proportions and colours;
2. the wing-cloak reads as two folded wings at 64 px height;
3. the lantern is a closed solid shape (glass painted, no holes);
4. no thin parts, no holes, no floating parts;
5. white background, no text, no shadows;
6. the design is original: no element copied from another game's statue, character, logo or costume.

Self-review before you deliver (at least 3 passes; list each pass's fixes in the README):
1. Silhouette: shrink the front view to 64 px tall in greyscale. It must still read as the intended object at a 13 m game camera.
2. Views: left is the mirror outline of right; back is the mirror outline of front, except for any asymmetry listed in the README. Heights equal within 3 %.
3. Style: chunky, bevelled, hand-painted forms; values never pure black or pure white; the hero view's palette matches the palette above.

Report format (README.md inside the zip): the pose, the size in metres, the materials per part, the intended asymmetry (or none), the checklist below with PASS/FAIL, and the 3 self-review passes. receipt.json: the file list, pixel sizes, palette hex values, and the licence note "generated for Xexoria".

Approval: none needed for these images. Any Tripo job made from them needs Claude's design review, a `turnaround_qa.py` PASS and the owner's credit ceiling (credit guard §4).
