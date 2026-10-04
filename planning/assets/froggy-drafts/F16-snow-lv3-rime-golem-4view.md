[Claude -> froggy | 2026-10-02 | F16]

TASK F16: Rimecrest lv3 monster "rime golem": model-ready turnaround of an APPROVED design (F6 format)

Attach before sending (the owner-approved design; do not redesign it):
- `sources\snow\lv3\ChatGPT Image 30 ก.ย. 2569 21_45_59.png` (front)
- `...21_46_05.png` (left side) and `...21_46_12.png` (right side): note these are three-quarter views, which is the main problem
- `...21_46_08.png` (back)
- the weapon, for reference only: `...21_46_22.png` (cleaver front)
- the look target `docs/ui/xexoria-town-art-target-20261001.png` (for the lit hero view only)

The owner approved this creature as it is. Stage A is closed. This round only makes the views usable for Tripo P2.0 multi-view. Our automatic check (`tools/art/turnaround_qa.py`) and our design review rejected the current set for the reasons below; fix exactly these.

What to keep: the massive rime-stone golem build, the dragon-skull pauldron on its right shoulder and the rough rock pauldron on its left, the bone ribcage over the glowing ice heart, the crowned head with glowing eyes, the belt and straps, the shard skirt, the clawed stone hands and feet, the colours.

What to fix:
1. **True side profiles.** The current side views are three-quarter views: both pauldrons and the chest glow show. Draw exact side profiles at 90 degrees, orthographic, camera at mid-height.
2. **Left/right and front/back consistency.** Left vs right width differs 12.8 %; front vs mirrored back outline match is 0.876 (we need at least 0.90): the front hem of the shard skirt hangs differently from the back. One consistent hem and one stance in all four views, so left is the mirror outline of right (apart from the pauldron asymmetry) and back is the mirror outline of front.
3. **Declared asymmetry.** The skull pauldron (right shoulder) and the rock pauldron (left shoulder) are intentionally different. List this in the README; draw each pauldron identically wherever it is visible.
4. **Hands open and empty.** The cleaver is a separate asset; leave it out of all four body views.
5. **Format and thin parts.** Each view 2048x2048 on pure white #FFFFFF, the golem filling about 80 % of the frame height, feet on one baseline, same scale, neutral flat light, no cast shadows. Skirt shards, crown spikes and claws at least 3 % of the frame width (about 61 px at 2048); straps and rivets painted as colour, not raised parts.

Palette (measured from the approved images, keep these): rime stone #313132, deepest gaps #141313, slate #5A6066, warm grey #857C74, umber #534A44, pale frost #C2C5C1, bone tan #BAA58E, ice heart glow about #7FE6F2.

Views and files (TASK F6 rules):
- front.png, back.png, left.png (the golem's own left side: it faces screen-left), right.png (faces screen-right): 2048x2048 each, white background, no text;
- hero34.png: one lit three-quarter view in the game look, for texture reference only;
- palette.png with the hex values above.

Deliver `turnarounds_snow_rime_golem_v1.zip`: the five PNGs, palette.png, README.md (stance, height in metres, materials, the declared pauldron asymmetry), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL in the README; Claude re-runs the automatic check with the asymmetric flag on delivery; at most 3 rounds):
- the side views are true profiles, not three-quarter views;
- heights equal across views within 3 %; feet on one baseline;
- back is the mirror outline of front; left mirrors right apart from the declared pauldrons;
- no part thinner than 3 % of the frame; hands empty; no floating parts;
- white background, no shadows, no text; design and colours match the attached images.
