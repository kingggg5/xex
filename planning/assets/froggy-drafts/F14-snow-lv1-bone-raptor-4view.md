[Claude -> froggy | 2026-10-02 | F14]

TASK F14: Rimecrest lv1 monster "bone raptor": model-ready turnaround of an APPROVED design (F6 format)

Attach before sending (the owner-approved design; do not redesign it):
- `sources\snow\lv1\ChatGPT Image 30 ก.ย. 2569 21_51_56.png` (front)
- `...21_52_02.png` (left profile, facing screen-left)
- `...21_52_09.png` (back)
- `...21_52_12.png` (right profile, facing screen-right)
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (for the lit hero view only)

The owner approved this creature as it is. Stage A is closed. This round only makes the views usable for Tripo P2.0 multi-view. Our automatic check (`tools/art/turnaround_qa.py`) rejected the current set for the reasons below; fix exactly these.

What to keep: the skeletal raptor-drake body, bone-tan plates over a glowing blue ice ribcage, the spiked spine and long spiked tail, the horned skull head with blue eyes, the clawed feet, the colours.

What to fix (measured on the current set):
1. **Same scale in every view.** The creature's height differs by up to 17.3 % between views (front 1171 px, left 893, back 1201, right 854) and the ground line moves by 9.4 % of the body height. Use one camera distance and one ground line for all four views. Each view 2048x2048 on pure white #FFFFFF, the creature filling about 80 % of the frame height in the front view, orthographic look, no cast shadows.
2. **Front and back must be the same stance.** The front shows the legs splayed wide; the back shows a narrow stance (front 58.9 % wider; outline match 0.405, we need at least 0.90). Pick one neutral standing stance and show it identically from front and back.
3. **Left and right must mirror.** Outline match 0.649: head height, tail curve and tail tip differ (the tail touches the ground in one profile only). Use the same pose, mirrored. Keep the tail clear of the ground and of the legs in every view.
4. **Spikes and tail tip.** Every spine spike, claw and the tail tip at least 3 % of the frame width (about 61 px at 2048); fewer, larger spikes are better than many thin ones.
5. **No see-through ribcage.** Put a solid ice core behind the ribs (closed surface). The blue glow is colour on that core, not empty space.

Palette (measured from the approved images, keep these): bone tan #AB917A, bone light #D3C4B5, warm brown #765D49, dark plates #3F3934, deepest gaps #1A1917, cool grey #5F6464, ice glow #88B6C0 with bright cores about #7FE6F2.

Views and files (TASK F6 rules):
- front.png, back.png, left.png (faces screen-left), right.png (faces screen-right): 2048x2048 each, white background, no text;
- hero34.png: one lit three-quarter view in the game look, for texture reference only;
- palette.png with the hex values above.

Deliver `turnarounds_snow_bone_raptor_v1.zip`: the five PNGs, palette.png, README.md (stance, size in metres including tail length, materials, asymmetries: none intended), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL in the README; Claude re-runs the automatic check on delivery; at most 3 rounds):
- heights equal across views within 3 %; feet on one baseline;
- left is the mirror outline of right; back is the mirror outline of front;
- no part thinner than 3 % of the frame; no see-through gaps; no floating parts;
- white background, no shadows, no text;
- the design and colours match the attached images.
