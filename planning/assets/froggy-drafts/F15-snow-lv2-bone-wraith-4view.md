[Claude -> froggy | 2026-10-02 | F15]

TASK F15: Rimecrest lv2 monster "bone wraith": model-ready turnaround of an APPROVED design (F6 format)

Attach before sending (the owner-approved design; do not redesign it):
- `sources\snow\lv2\ChatGPT Image 30 ก.ย. 2569 21_46_31.png` (front)
- `...21_46_40.png` (left profile, facing screen-left)
- `...21_50_53.png` (back)
- `...21_51_01.png` (right profile, facing screen-right)
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (for the lit hero view only)

The owner approved this creature as it is. Stage A is closed. This round only makes the views usable for Tripo P2.0 multi-view (humanoid, A-pose). Our automatic check (`tools/art/turnaround_qa.py`) rejected the current set for the reasons below; fix exactly these.

What to keep: the tall bone-armoured humanoid, the beaked bone helm with blue eyes, the glowing blue ice heart behind the ribs, the layered bone plates, the clawed hands and feet, the ice-shard skirt, the colours.

What to fix (measured on the current set):
1. **Arms must match left and right.** In the left profile the far arm hangs forward of the body; in the right profile it hangs at the side (widths differ 21.6 %, outline match 0.790; we need at least 0.90). Use one A-pose for all four views: arms 30-45 degrees down from the shoulders and hanging straight to the sides (not forward), hands open, a clear gap between the arms and the torso in the front and back views, legs slightly apart.
2. **Format.** Each view 2048x2048 on pure white #FFFFFF (now 1254x1254 on a grey gradient), the figure filling about 80 % of the frame height, feet on one baseline, same scale, orthographic look, neutral flat light, no cast shadows.
3. **Thin parts (so the model survives meshing).** Make the forearms, shins, fingers and claws about 15 % thicker, and draw the skirt as fewer, larger ice shards, each at least 3 % of the frame width (about 61 px at 2048). Same silhouette idea, just sturdier.
4. **No floating shards.** Every shard and plate touches the body.

Palette (measured from the approved images, keep these): dark plates #403E3D, deepest gaps #191919, bone tan #B8A592, warm brown #826F5E, slate grey #5D6367, pale bone #CBCCC8, cool grey #8D979B, ice glow about #7FE6F2.

Views and files (TASK F6 rules):
- front.png, back.png, left.png (faces screen-left), right.png (faces screen-right): 2048x2048 each, white background, no text;
- hero34.png: one lit three-quarter view in the game look, for texture reference only;
- palette.png with the hex values above.

Deliver `turnarounds_snow_bone_wraith_v1.zip`: the five PNGs, palette.png, README.md (pose, height in metres, materials, asymmetries: none intended), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL in the README; Claude re-runs the automatic check on delivery; at most 3 rounds):
- heights equal across views within 3 %; feet on one baseline;
- A-pose with a visible arm-torso gap; hands open;
- left is the mirror outline of right; back is the mirror outline of front;
- no part thinner than 3 % of the frame; no floating parts;
- white background, no shadows, no text; design and colours match the attached images.
