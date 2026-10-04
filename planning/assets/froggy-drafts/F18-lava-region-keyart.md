[Claude -> froggy | 2026-10-02 | F18]

TASK F18: Lava region key art, regeneration (CONCEPT, 16:9, 3 variants)

Attach before sending:
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`;
- the earlier lava image `sources\lava\ChatGPT Image 30 ก.ย. 2569 21_11_39.png`, as an example of what to change (read the notes below; do not copy it).

Why a new round: we reviewed the earlier lava key art. Its composition is good (one straight route to one landmark gate, lava falls far away), but it fails our checklist:
- it is a photoreal, grim render, not our stylised hand-painted look;
- it is too dark: average brightness 0.32 against 0.50 for the look target, and 19 % of the image is near-black (the target has 4 %);
- there is no clear light: an overcast sky and lava under-glow only;
- its motifs (chained titan hands, a giant face carved into the cliff, a lone caped spear warrior) read as God of War;
- it is not playable: a narrow broken causeway between lava drops, while our world needs flat, wide walkable ground, and lava next to the path hides our red, orange and amber attack warnings.

Context: the lava region (working name Ashveil Caldera) follows Rimecrest on the warp network. It is a wide volcanic caldera where a long-dead smith culture carved a giant ember forge into the crater wall. The forge is the landmark and the entrance of a future dungeon. The region boss waits on a forge-anvil plateau.

Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), with the Xexoria look target attached. Keep the design clean for 3D generation: clear shapes, clear light and shadow, an uncluttered background, nothing too dark. Make 3 variants as separate generations of this same brief.

Camera: the game's player camera. Third person, 13 m behind a 1.8 m adventurer, about 22 degrees above the horizon, vertical field of view about 58 degrees.

What must be in the frame (front to back):
1. **Arrival waystone (foreground):** a round carved basalt dais about 5 m across with a warm ember-orange rune ring inlay (never white) and two short standing stones: the arrival and return point.
2. **The road:** a wide basalt-paved road (at least 4 m) with low kerb stones, crossing pale ash fields.
3. **Ash fields (middle, the combat space):** flat pale-grey ash ground (#B5ADA8, #8E8790) with low rounded basalt outcrops, hardy red-leaf shrubs and a few sulphur-yellow crystal clusters (#E8C54A) for colour. These open, calm areas are where fights happen.
4. **Lava in its place:** lava runs only in channels with raised stone banks and in pools away from the road, crossed by solid stone bridges; distant lava falls pour from the crater wall. Lava keeps its hue: core #FFB347 to #FF7A1F, edges #D9441C, never clipping to white.
5. **The ember forge (far landmark):** a monumental forge hall carved into the crater wall: huge stone doors, chimney stacks with thin smoke, a glowing furnace mouth and bronze fittings (#A8743F). Original architecture, chunky and readable.
6. **The forge-anvil plateau (boss site, far side):** a flat round plateau about 30 m across, paved in dark stone, ringed by cooled-lava pillars, with a giant ruined anvil at one edge, shown empty.

Gameplay needs:
- Flat, wide walkable ground; height only in the frame (the crater walls and far cones). No narrow ledges, no climbing.
- No lava, red or orange ground anywhere near the combat ash fields or the road edge, so ground telegraph rings stay readable.
- One clear route from the arrival to the forge, and the arrival visible as the way back.

Light: warm late-afternoon sun from the upper left breaking through thin high cloud, a cool violet-blue sky fill (#7F78A8) and cool-violet shadows on the basalt (#5E5468). The ground reads mid-value (basalt #4A4550 lifted, ash lighter), never black. Smoke plumes thin and far away only; no fog over the play space; no bloom wash around lava or braziers.

Palette: basalt, ash, crust, lava, sulphur and bronze as above; obsidian #2B2630 only as small accents; warm stone #C1BCA4 for the carved forge details.

Style: stylised hand-painted MMO, Warcraft-like readability (not Warcraft content): chunky bevelled shapes, saturated but harmonious colour, painted occlusion, top-light gradients, crisp edge highlights. Purposeful clusters, never rows.

Variants: A: road straight to the forge, a lava channel parallel on the right. B: road curving over a stone bridge, the anvil plateau visible left. C: a lower sun with long violet shadows and the forge furnace as the brightest spot.

Originality: original Xexoria architecture and landscape. No chained titans, giant carved faces or Greek-Norse god imagery (God of War); not Molten Core, Firelands or Searing Gorge (World of Warcraft), not Mordor (Lord of the Rings), not Natlan (Genshin), not Lost Izalith (Dark Souls), not any Lumivara volcanic area. No logos, no text other than the "CONCEPT" tag.

Deliver `regions_lava_keyart_v2.zip`: the 3 variants as PNG (2048x1152), README.md (what is where, prompts used, checklist results), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per variant in the README):
- average brightness close to the look target (around 0.45-0.55); no more than about 6 % of the image near-black;
- in greyscale at a 160 px thumbnail the road, the forge and the plateau read;
- clear warm key and cool fill; lava never clips to white;
- combat ash fields flat, open and free of lava; the road at least 4 m wide;
- original; only the CONCEPT tag as text.
