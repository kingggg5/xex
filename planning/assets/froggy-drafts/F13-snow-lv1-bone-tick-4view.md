[Claude -> froggy | 2026-10-02 | F13]

TASK F13: Rimecrest lv1 monster "bone tick": model-ready turnaround of an APPROVED design (F6 format)

Attach before sending (the owner-approved design; do not redesign it):
- `sources\snow\lv1\ChatGPT Image 30 ก.ย. 2569 21_51_28.png` (front)
- `...21_51_37.png` (left profile, facing screen-left)
- `...21_51_41.png` (back)
- `...21_51_46.png` (right profile, facing screen-right)
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (for the lit hero view only)

The owner approved this creature as it is. Stage A is closed. This round only makes the views usable for Tripo P2.0 multi-view: same design, same colours, same proportions. Our automatic check (`tools/art/turnaround_qa.py`) rejected the current set for the reasons below, so please fix exactly these and nothing else.

What to keep: the domed carapace of bone-white plates over a blue-grey ice body, eight jointed legs with dark claws, the skull-like head with two glowing blue eyes, the spiky rim of the shell, the colours.

What to fix (measured on the current set):
1. **Format.** Each view 2048x2048 on pure white #FFFFFF (now 1254x1254 on a grey gradient). The creature fills about 80 % of the frame height (now 68-71 %). Same camera distance and the same ground line in all four views. Orthographic look, camera at mid-height, neutral flat light, no cast shadows.
2. **Thin parts.** 2.6-6.1 % of the outline is thinner than 3 % of the frame (61 px at 2048): the lower leg segments, claws and both antennae. Make every leg segment and claw at least 3 % of the frame width (about 61 px at 2048). Make the antennae short and thick (or leave them off; we can add them later as separate curves). Keep the claws pointed but stout.
3. **Legs must match between views.** Left vs mirrored right outline match is 0.717 and front vs mirrored back 0.838 (we need at least 0.90). Draw all eight legs in one identical, neutral standing stance, so the left profile is the exact mirror outline of the right and the back is the mirror outline of the front.
4. **No see-through holes.** The carapace has open lattice holes. Close them: show them as dark recessed panels on a solid shell, so the shell is one closed surface.
5. **No small hardware.** Rivets, bolts and ring joints on the legs become noise. Paint them as colour detail; do not draw them as raised parts.

Palette (measured from the approved images, keep these): bone light #DED8D1, bone #C4B7A9, warm grey #9C8C7D, mid grey #69615B, dark shell #3C3C3D, joints and claws #181717, ice body #7599A8, eye glow about #7FE6F2.

Views and files (TASK F6 rules):
- front.png, back.png, left.png (the creature's own left side: it faces screen-left), right.png (faces screen-right): 2048x2048 each, white background, no text in the image;
- hero34.png: one lit three-quarter view in the game look (warm key from the upper left, soft blue fill), for texture reference only;
- palette.png with the hex values above.

Deliver `turnarounds_snow_bone_tick_v1.zip`: the five PNGs, palette.png, README.md (pose, size in metres, the leg stance, materials, any asymmetry: none intended), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL in the README; Claude re-runs the automatic check on delivery and a FAIL means another round, at most 3):
- heights equal across views within 3 %; feet on one baseline;
- left is the mirror outline of right; back is the mirror outline of front;
- no part thinner than 3 % of the frame; no holes; no floating parts;
- white background, no shadows, no text;
- the design and colours match the attached images.
