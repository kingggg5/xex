[Claude -> froggy | 2026-10-03 | F29]

TASK F29: monster "Bramble Brute": 4-view turnaround (new design)

Status: DRAFT from the ref-look lane. Claude main reviews and sends it; nothing has been sent.

Attach before sending:
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (style and lighting only);
- the look-target doc `docs/reviews/2026-10-03-reference-look-target-v2.md` §6 and §10 (as text, for context).

Do NOT attach the owner's third-party screenshots (`references/owner-aaa-20261002`). They are study-only and never inputs (llm.txt rule 11). The design below is our own; do not imitate any existing game's character, statue, logo or costume.

Why: the owner's references include a big brute monster in a dirt clearing, and the owner asked for some models via GPT image -> Tripo P2.0 Smart UV -> rig. Sunmeadow's combat clearings need one heavy field monster with real weight.

Design (original; not an ogre with a hammer and loincloth):
- a hulking hill brute, 3.2 m tall standing, hunched; huge forearms; short thick legs; a small head sunk between the shoulders with two curled ram-like horns;
- its back is overgrown: a mossy turf hump with small ferns and two stubby saplings (solid clumps, no thin leaves);
- skin: weathered bark-brown hide (#6B4E36) with lighter lichen patches (#A8A060);
- weapon: a **root-bound stone maul** (a rough cream-stone block 0.8 m long, lashed to a gnarled root handle with thick vine bands), held in the right hand;
- a wide leather belt with a stone buckle carved with a simple spiral; wrapped forearms; bare feet with three thick toes;
- neutral A-pose for rigging: arms 35-45 degrees from the body, hands open as thick mitts, legs at shoulder width. Draw the maul on a separate sheet (front and side) so it can be a separate mesh.

Materials and value: the hide and moss hump must separate from a pale cliff background, so keep the hide mid-dark (value 0.25-0.45) with a lighter rim on the shoulders. Eyes small ember-amber (#E0902E), not glowing white.

Xexoria shared palette (use these families; small hue variation is welcome): warm cream stone #E8D9BC, sandstone #D9B98C, dark timber #4A3426, sapphire #2B4F86, slate blue #3E5A7A, terracotta #B8603F, restrained gold #C9A04A (accents only, at most 5 % of the object), moss #6F7F2E.

Budget after Tripo: 6,000-8,000 triangles (monster); a boss variant may go to 15,000-25,000 later. Est. Tripo ~145 credits. Rig: humanoid, about 45 bones (spine 3, neck 1, head 1, jaw 1, clavicles, arms, mitt hands with a thumb, legs, toes, and 2 jiggle bones for the moss hump). Clips: idle, walk, run, attack_swing, attack_slam (ground hit), roar, hit, stun, death.

Views and files (TASK F6 rules, so Tripo P2.0 multi-view and `tools/art/turnaround_qa.py` accept them):
- front.png, back.png, left.png (the object's own left side, facing screen-left), right.png (facing screen-right): 2048x2048 each, pure white #FFFFFF background, no shadows, no text;
- the object fills about 80 % of the frame height; same camera distance and the same ground line in all four views; orthographic look, camera at mid-height;
- no part thinner than 3 % of the frame (about 61 px at 2048); no see-through holes (paint openings as dark recessed panels); no floating parts;
- small hardware (rivets, nails, studs, stitching) is painted colour detail, never raised geometry;
- hero34.png: one lit three-quarter view in the game look (warm key from the upper left, soft blue sky fill, painted AO in crevices, crisp edge highlights), texture reference only;
- palette.png with the hex values you used.

Deliver `turnarounds_bramble_brute_monster_v1.zip`: the PNGs above, palette.png, README.md and receipt.json.

Checklist (PASS/FAIL in the README; Claude re-runs `tools/art/turnaround_qa.py` on delivery, and a FAIL means another round, at most 3):
1. the A-pose is identical in all 4 views;
2. the horns, hump and maul read at 64 px;
3. the hands are thick mitts with a separate thumb (no thin fingers);
4. the maul sheet is separate;
5. no holes, no floating parts, white background, no text;
6. the design is original: no element copied from another game's statue, character, logo or costume.

Self-review before you deliver (at least 3 passes; list each pass's fixes in the README):
1. Silhouette: shrink the front view to 64 px tall in greyscale. It must still read as the intended object at a 13 m game camera.
2. Views: left is the mirror outline of right; back is the mirror outline of front, except for any asymmetry listed in the README. Heights equal within 3 %.
3. Style: chunky, bevelled, hand-painted forms; values never pure black or pure white; the hero view's palette matches the palette above.

Report format (README.md inside the zip): the pose, the size in metres, the materials per part, the intended asymmetry (or none), the checklist below with PASS/FAIL, and the 3 self-review passes. receipt.json: the file list, pixel sizes, palette hex values, and the licence note "generated for Xexoria".

Approval: none needed for these images. Any Tripo job made from them needs Claude's design review, a `turnaround_qa.py` PASS and the owner's credit ceiling (credit guard §4).
