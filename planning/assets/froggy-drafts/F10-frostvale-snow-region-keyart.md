[Claude -> froggy | 2026-10-02 | F10]

TASK F10: Rimecrest region key art, the first new map (CONCEPT, 16:9, 3 variants)

Attach before sending:
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`;
- the owner's snow monsters, for scale and palette only (do not redesign them): `sources\snow\lv1\...21_51_28.png` (bone tick), `...21_51_56.png` (bone raptor), `sources\snow\lv2\...21_46_31.png` (bone wraith), `sources\snow\lv3\...21_45_59.png` (rime golem);
- the region NPC: `sources\boss\bovine-shaman\references\front.png` (a yak-like bovine elder; keep him on-model);
- the region boss: `sources\boss\ChatGPT Image 30 ก.ย. 2569 21_10_21.png` (the Solar Scorpion; on-model, small and far away in this image).

Context: Rimecrest is the first new map of Xexoria. Players reach it through the Windstone portal ring in Sunmeadow after they defeat the field boss Galehorn. They arrive in a ring of carved windstones in a snowy highland valley. The valley holds three monster bands (lv1 near the arrival, lv2 in the middle, lv3 far out), a yak-herder camp with the bovine elder, and, at the far end, a frozen sun-shrine where a golden scorpion guardian (the boss) sleeps in the ice. Warm gold against cool snow is the region's signature.

Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), with the Xexoria look target attached. Keep the design clean for 3D generation: clear shapes, clear light and shadow, an uncluttered background, nothing too dark. Make 3 variants as separate generations of this same brief.

Camera: the game's player camera. Third person, 13 m behind a 1.8 m adventurer, about 22 degrees above the horizon, vertical field of view about 58 degrees. The adventurer has just stepped out of the arrival ring in the foreground.

What must be in the frame (front to back):
1. **Arrival ring (foreground, the player's spawn):** a round carved stone dais about 5 m across, flush with the ground and dusted with snow, with a rune ring inlaid in its surface (faint cyan glow #72D5DE, never white). Three snow-capped standing stones of the same wind-carved sandstone as Sunmeadow's windstones (rounded slabs with a spiral glyph and faded blue/cream cloth streamers) stand around it. This ring is also the way home, so it must read as a portal: one clear landmark at the start.
2. **Yak-herder camp (near, to one side):** a felt-and-hide tent, a stone-ringed campfire with warm light and a thin smoke line, a wooden drying rack, two pack baskets, and the bovine elder standing by the fire. Warm light means "safe here".
3. **First snowfield (middle):** an open, gently rolling snowfield where a few bone ticks and bone raptors roam, kept small. Trodden trails (packed, slightly darker snow, at least 4 m wide) lead from the arrival past the camp to a bridge.
4. **Frozen river and bridge:** a wide timber-and-stone bridge (at least 4 m wide) over a frozen river with cracked blue ice and snowy banks.
5. **Rune-stone ridge (beyond):** half-buried carved stones and broken walls on a low ridge where the bone wraiths walk.
6. **Glacier edge (far):** big crystalline ice boulders and one frozen waterfall as the strongest far landmark, where the rime golems stand.
7. **Boss lair on the skyline:** a frozen sun-shrine: warm sandstone pillars and a broken golden sun-disc half-buried in ice on a far plateau, with a tiny golden glint of the scorpion. It pulls the eye but stays small.
8. Optional, very small on the far horizon: the roofline of a carved timber longhall (a future dungeon). Original, not a Viking-film copy.

Gameplay needs (they decide what "good" means here):
- The walkable ground is flat and wide. Height lives only in the frame: cliffs, ridges and mountains rise around the edges and never block the trail. No climbing, no narrow ledges.
- Combat areas are open snowfields with calm ground. Ground telegraph rings must stay readable on them (amber, orange and red rings), so no glowing ground, no red or orange ground anywhere near the fights.
- One clear route from the arrival to the far lair, and a visible way back to the ring.
- Monsters stay readable against snow: the bone-white monsters need the snow to sit a little darker (soft blue-violet shadows, packed trails) so their silhouettes separate.

Snow done right (fixes from our earlier snow-map review):
- Snow sits on upward-facing surfaces and drifts against rocks, walls and tent sides. Visible wind drifts and soft sastrugi, not a flat white sheet.
- Snow is never pure white: brightest snow about #E8EEF2 (235/255), shadows blue-violet (#9FB3D1, #7E8FB8).
- Stepping stones and rocks are partly buried with snow rims on top, never flat black cut-outs lying on the snow.
- Ice is crystalline: sharp facets, translucency at thin edges, inner cracks, a cold blue core (#7FC8E0, deep #2F7FA6). Not plastic, not glossy blobs.

Light: low winter sun, late morning, warm key from the upper left (#F6C95F tint), soft blue sky fill, long soft shadows across the snow. Clear air near the player; light blue aerial haze only far away. Nothing too dark: the darkest large areas are rock faces in shade, still readable.

Palette (shared Xexoria language): warm sandstone #C1BCA4 and light #EAE3CD for the windstones and the shrine; dark timber #6B4A32 and felt reds and ochres for the camp; blue-slate accents #4F7BB0; snow and ice as above; the boss's warm gold (#E0A43A) and amber orbs (#F29A2E) only at the far lair.

Style: stylised hand-painted MMO, Warcraft-like readability (not Warcraft content). Chunky, bevelled shapes, saturated but harmonious colour, painted occlusion and top-light gradients, crisp edge highlights. Purposeful clusters, never rows.

Variants: same brief, different compositions. A: arrival ring lower left, camp right, trail curving to the bridge. B: arrival ring centred, trail running straight to the bridge, camp left. C: the camera turned so the frozen waterfall frames the far lair.

Originality: an original Xexoria region. Not Northrend, Icecrown or any World of Warcraft zone (no Scourge spires, no Lich King imagery), not Skyrim, not God of War (no Jotunheim, no giant faces), not Genshin's Dragonspine, not Frostveil or any Lumivara area. No logos, no text other than the "CONCEPT" tag.

Avoid: blizzards that hide the scene, darkness, bloom on snow or ice, glowing rivers, clutter in the play space, impossible floating rocks.

Deliver `regions_rimecrest_snow_keyart_v1.zip`: the 3 variants as PNG (2048x1152), README.md (what is where, prompts used, which checklist items pass or fail), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (state PASS/FAIL per variant in the README):
- in greyscale at a phone thumbnail (160 px wide) the arrival ring, the trail, the bridge and the far lair still read;
- light and shadow are clear; no large area darker than about 15 % brightness; snow highlights never clip to white;
- the play space is calm and uncluttered; trails at least 4 m wide; combat snowfields flat and open;
- snow drifts and buried stones are visible; ice is faceted and translucent;
- original; only the CONCEPT tag as text.
