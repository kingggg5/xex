[Claude -> froggy | 2026-10-02 | F12]

TASK F12: Rimecrest boss arena key art with the Solar Scorpion (CONCEPT, 16:9, 3 variants)

Attach before sending:
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`;
- the boss, exactly as built: `sources\boss\ChatGPT Image 30 ก.ย. 2569 21_10_21.png` (front), `...21_10_40.png` (left), `...21_10_46.png` (back), `...21_10_49.png` (right), and the built model render `sources\boss\tripo-p2-output\runtime-rig-v1\runtime_lod0_front.png`;
- the picked F10 Rimecrest variant once Claude has chosen it.

What this image is for: it becomes the scene reference for our in-engine "gauntlet loop". We will rebuild this arena in the game and compare our captures to your image (brightness, contrast, colour and the boss's outline). So it must show the arena exactly as a player would see it, with buildable shapes.

The boss: the Solar Scorpion, a 4.2 m falcon-headed, gold-armoured scorpion-centaur with six legs, a segmented raised tail tipped with an amber orb, a sun-disc halo, turquoise inlay and red cloth. The owner designed and built it. Keep it EXACTLY on-model: same proportions, same gold, turquoise and red, same halo and orbs. Do not redesign, recolour, add armour or add frost.

Lore for the mood: a sun-forged guardian of an old sun temple, frozen for centuries in the glacier. The ice around its shrine has cracked open, and it wakes when heroes come near. Warm gold against cold blue snow is the whole point of the image.

Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), with the Xexoria look target attached. Keep the design clean for 3D generation: clear shapes, clear light and shadow, an uncluttered background, nothing too dark. Make 3 variants as separate generations of this same brief.

The arena (what the builders will model):
- A flat, round plaza about 28 m across: old warm sandstone paving (#C9A36B, light #E3C48F) half-buried in packed snow, with a carved sun-ray pattern radiating from the centre (wide grooves, simple shapes).
- Around the rim, outside the fighting space: broken sandstone pillars, a toppled golden sun-disc (cracked, half in the ice), and two great ice walls of the glacier with crystalline facets and a cold blue core (#7FC8E0, #2F7FA6) framing the back. One entry: a snowy trail coming in from the camera side.
- The fighting floor itself is calm and flat: paving and snow only, no rubble, no glowing ground, no ice spikes in the middle.
- The boss stands near the centre facing the camera, tail raised and coiling for a strike.
- Three small adventurers (1.8 m each, simple fantasy gear) stand near the entry for scale. They are tiny next to the boss.
- On the snow in front of the boss, one danger telegraph: a red boss ring (#D93A3A band with a darker rim and a carved-rune edge) marking where the tail will strike. It must read clearly on the snow and the paving.

Camera: the game's player camera, third person, 13 m behind the middle adventurer, about 22 degrees above the horizon, vertical field of view about 58 degrees. The whole boss fits in the frame, halo and tail orb included.

Light: low winter sun from the upper left (warm key), soft blue sky fill, long soft shadows; the boss's amber orbs glow warm but never clip to white. Light blue haze only behind the ice walls. Nothing too dark: the gold must read as bright metal, the snow as soft white-blue (brightest about #E8EEF2), shadows blue-violet (#9FB3D1, #7E8FB8).

Variants: A = boss centred, ice walls behind; B = boss slightly left, the toppled sun-disc on the right rim; C = a lower sun, longer shadows, the shrine pillars catching warm light.

Style: stylised hand-painted MMO with Warcraft-like readability (not Warcraft content): chunky forms, painted occlusion and top-light gradients, crisp edge highlights, saturated but harmonious colour.

Originality: original Xexoria arena. No Ahn'Qiraj, Uldum or any World of Warcraft zone, no Egyptian temple copied from a real monument or another game, nothing from Genshin, Ragnarok or Lumivara. No text other than the "CONCEPT" tag.

Avoid: blizzard or fog hiding the boss, dark scenes, bloom, clutter on the fighting floor, extra monsters, a boss that differs from the attached images.

Deliver `regions_rimecrest_boss_arena_keyart_v1.zip`: the 3 variants as PNG (2048x1152), README.md (layout description with sizes in metres, prompts used, checklist results), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per variant in the README):
- in greyscale the boss separates clearly from the snow and the ice walls at a 160 px thumbnail;
- the red telegraph ring is instantly readable on the floor;
- the fighting floor is flat, calm and about 28 m across; props only on the rim;
- the boss matches the attached images (no redesign);
- no large area darker than about 15 % brightness; no clipped highlights; only the CONCEPT tag as text.
