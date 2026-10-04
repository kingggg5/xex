[Claude -> froggy | 2026-10-02 | SKILLS-03-archer]

TASK SKILLS-03-archer: effect key-frame reference sheets for hero 03, the Wolf-kin Archer: 7 sheets (6 skills + the basic attack), CONCEPT, 16:9

Send order: 6 of 6 (the witch first). The VFX lane builds each effect from your sheet, then compares its in-game capture with it until they match (the reference-gauntlet loop). Design source: `docs/plans/2026-10-02-hero-skills-and-vfx-design.md`, hero 03.

Attach before sending:
- the owner's VFX quality-bar sheets, the bar to beat for layout, layering and readability (do not copy their designs): `content/ChatGPT Image Oct 1, 2026, 10_46_58 PM.png` (sword ring), `content/ChatGPT Image Oct 1, 2026, 10_45_00 PM.png` (palm projectile), `content/ChatGPT Image Oct 1, 2026, 10_46_38 PM.png` (ground vortex);
- the hero, for the silhouette only: `Downloads\hero\03\ChatGPT Image Oct 1, 2026, 01_14_18 PM.png` (front) and `Downloads\hero\03\ChatGPT Image Oct 1, 2026, 01_16_20 PM.png` (weapon);
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`.

Context: Xexoria is a stylised hand-painted browser MMO. Hero 03's party role: **Ranged DPS**. Element: Gale and wild (wind, leaves, the moonlit hunt). Shape language: Arrowheads and chevrons, feathers and leaf blades (from her cape's gold leaves), wind streaks and spiral curls, crescent fangs. Fast, directional, light. Hero palette: core #F0FFF6, body #5CE6A0, edge #1F9E86, accent #FFB84A, leaf #8EDB4F, moon #DDE6F2.

Sheet format (the same for all 7 sheets):
- One 16:9 image, 2400×1350, holding 8 equal frames in a 4 × 2 grid read left to right, top row first, with thin dark gutters (#101418), like the attached quality-bar sheets.
- Top-left of each frame, in small light text: `t=0.20s`. Above the grid, one header line: the skill id and English name. No other text.
- Camera: the game's player camera, third person, 13 m from the hero, about 22 degrees above the horizon, vertical field of view about 58 degrees. The same camera in all 8 frames.
- Stage: a neutral mid-grey ground plane (#7A7F85) with a faint 1 m grid and a plain light-grey sky gradient. No scenery, no props, no weather.
- Scale: the hero as a flat mid-dark grey silhouette (#4A4F55) with the weapon, 1.85 m (with the ears) tall at the crown (slim athletic wolf-kin woman: tall ears, big fluffy tail, hooded capelet and leaf-cut cape, recurve bow in the left hand). Enemy dummies are plain dark grey capsules (#5E646B, 1.2-1.8 m); allies are light-grey silhouettes (#9AA1A8). Every silhouette stays readable in every frame; the effect never hides them.
- Telegraph: draw the exact ground shape given per sheet. The shape is the meaning: single smooth amber line = normal danger, double toothed vermilion with hatching = heavy, dashed pale-mint = ally benefit.

Look v2 (owner, 2026-10-02): bigger, more colourful, more detailed.
- Bigger: at the peak frame the effect covers about the given share of the frame, mostly through tall vertical shapes, not only flat ground rings; a short hold at the peak so it feels heavy.
- More colourful: the 2-3 hue palette given per sheet (core, body, accent), saturated mid-tones, value-graded edges, a coloured light spill on the ground. Bright cores stay below white: no blown-out white blobs.
- More detailed: show all five layers at the peak: anticipation (gather, runes), a solid core shape (mesh-like swirl, ring, slash, crystal, pillar), secondary particles (sparks, motes, petals, shards), a ground layer (decal, crack, scorch or rune circle) and an after-effect (motes, smoke, shimmer).
- Style: stylised hand-painted fantasy MMO effects with painterly, crisp shapes, readable at game distance.

## Sheet 1 of 7: `h03_amberwatch_arrow` Amberwatch Arrow (skill 1, debuff + damage)

What it is: An amber-sigil arrow Marks a target for 8 s: the whole party deals 10 % more to it and sees it through walls.
- Palette: core #FFF6E0, body #FFB84A, edge #C9731F, accent #5CE6A0.
- Telegraph on the ground: four solid amber corner brackets (#FFBA4B, dark rim) at the target dummy's feet.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 12 m ahead.
- Peak coverage: about 12 % of the frame.
- Layers to show: anticipation: An amber diamond-eye glyph flares at the bow grip; 6 amber motes converge on the arrowhead. Core: The arrow wrapped in an amber spiral ribbon; on hit an amber diamond sigil (0.8 m) snaps above the target with 4 closing ticks. Secondaries: Amber sparks and jade feathers. Ground: A small amber ring r 0.8 m under the target, pulsing at ≤ 1 Hz. After-effect: The mark holds at low intensity; party-only through-wall outline.
- Frames:
  1. t=0.08s: An amber diamond-eye glyph flares at the bow grip; solid amber brackets on the dummy.
  2. t=0.21s: Full draw; amber motes converge on the arrowhead.
  3. t=0.27s: Release: the arrow wrapped in an amber spiral ribbon.
  4. t=0.50s: Hit: an amber spark burst; an amber diamond sigil snaps above the dummy's head with four closing ticks.
  5. t=0.65s: Peak: the sigil locked; a small amber ring under the dummy.
  6. t=1.50s: The mark holds at low intensity (1 Hz pulse).
  7. t=4.00s: Still marked: the party sees it through a wall as a dotted outline.
  8. t=8.20s: The mark ends; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 2 of 7: `h03_featherfan_volley` Featherfan Volley (skill 2, damage + control)

What it is: Five wind-wrapped arrows fan across a 60° cone, push enemies back and Gust them.
- Palette: core #F0FFF6, body #5CE6A0, edge #1F9E86, accent #FFB84A.
- Telegraph on the ground: a single smooth amber wedge outline, 60 degrees, 12 m long, faint fill from the apex.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies 6-9 m ahead.
- Peak coverage: about 18 % of the frame.
- Layers to show: anticipation: The bow tilts flat; 5 ghost arrows fan out as a preview; wind gathers on the string. Core: 5 arrows with jade wind ribbons and a 60° x 3 m wind-fan crescent muzzle burst. Secondaries: Leaves and feathers spiralling; gust puffs at impacts. Ground: A fan-shaped wind-streak decal across the wedge. After-effect: Leaves settle; Gusted ribbons on the hit enemies.
- Frames:
  1. t=0.10s: The bow tilts flat; five ghost arrows fan out as a preview; the 12 m, 60° amber fan.
  2. t=0.24s: Full draw; wind gathers on the string.
  3. t=0.30s: Release: five arrows with jade wind ribbons and a wind-fan crescent muzzle burst.
  4. t=0.42s: Peak: the arrows hit; gust puffs, leaves and feathers spiralling; a jade light flash.
  5. t=0.55s: A fan-shaped wind-streak decal; Gusted ribbons on the dummies.
  6. t=0.80s: Leaves settling.
  7. t=1.20s: The decal fades.
  8. t=1.55s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 3 of 7: `h03_crescent_howl` Crescent Howl (skill 3, damage)

What it is: Hold to draw (up to 1 s): the arrow grows a pair of crescent wind-fangs and pierces everything in a 24 m line.
- Palette: core #F4FFF8, body #5CE6A0, edge #1F9E86, accent #FFB84A, moon #DDE6F2.
- Telegraph on the ground: an amber rectangle outline 1.2 m wide and 24 m long with small chevrons pointing away from the hero.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies in a line 4-19 m ahead.
- Peak coverage: about 20 % of the frame.
- Layers to show: anticipation: Two small crescents form at the arrowhead and widen with the charge; moonlight motes converge; at full charge a 'ting' glint and the crescents lock as fangs. Core: The arrow becomes a 3 m crescent-fang wind spear with a muzzle cone, leaving a straight helix wake. Secondaries: A vertical sonic ring at release, shed feathers, streaks. Ground: A wind-scar decal along the lane and dust kicked up along the path. After-effect: Jade and moon-silver motes hang along the path.
- Frames:
  1. t=0.15s: Drawing: two small crescents form at the arrowhead; the 1.2 m amber lane starts short.
  2. t=0.60s: Charging: the crescents widen, moonlight motes converge, the lane grows.
  3. t=1.25s: Full charge: a 'ting' glint; the crescents lock as fangs; the lane at 24 m.
  4. t=1.30s: Release: a 3 m crescent-fang wind spear, a vertical sonic ring at the bow, a muzzle cone.
  5. t=1.45s: It pierces the dummies in the line: helix wake, feathers, dust kicked up.
  6. t=1.70s: A wind-scar decal along the lane; motes hanging.
  7. t=2.10s: Fading.
  8. t=2.55s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 4 of 7: `h03_brushtail_vault` Brushtail Vault (skill 4, mobility + control)

What it is: A 7 m backflip; the takeoff leaves a gust that knocks enemies back and Gusts them.
- Palette: core #F0FFF6, body #5CE6A0, edge #1F9E86, accent #FFB84A.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 2.5 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 4 m ahead.
- Peak coverage: about 15 % of the frame.
- Layers to show: anticipation: Wind coils around her legs and tail (2 ribbons). Core: A gust bloom at takeoff (squashed funnel) and a ring wall burst r 0.5 → 2.5 m. Secondaries: Leaves and feathers burst; a limb-arc ribbon (the lower bow tip → the upper bow tip) traces the flip. Ground: A jade swirl decal r 2.5 m at takeoff and a landing dust ring. After-effect: Drifting leaves.
- Frames:
  1. t=0.04s: Wind coils around her legs and tail.
  2. t=0.09s: The 2.5 m amber ring at her feet; crouch.
  3. t=0.15s: Gust bloom: a squashed funnel and a ring-wall burst push the dummies back.
  4. t=0.30s: Mid-flip: a limb-arc ribbon traces the bow; leaves and feathers burst.
  5. t=0.48s: Landing 7 m back: a dust ring.
  6. t=0.70s: A jade swirl decal at the takeoff point.
  7. t=1.10s: Drifting leaves.
  8. t=1.45s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 5 of 7: `h03_briar_snare` Briar Snare (skill 5, control)

What it is: An arrow bursts into a ring of thorned vines: enemies within 3 m are Rooted for 1.5 s.
- Palette: core #F6FFE8, body #8EDB4F, edge #6B4A2B, accent #FFB84A.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 3 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 9 m ahead.
- Peak coverage: about 15 % of the frame.
- Layers to show: anticipation: The arrowhead glows amber-green; seed motes trail the arrow. Core: 10 thorned vine arcs burst up with back-out and coil around targets; amber thorn glints. Secondaries: Leaf and petal particles; seed pods popping. Ground: Root cracks with a bark seam and a leaf-notch ring r 3 m. After-effect: The vines wither with noise erosion; leaves fall.
- Frames:
  1. t=0.08s: The arrowhead glows amber-green; the 3 m amber ring at the target.
  2. t=0.25s: Release; seed motes trail the arrow.
  3. t=0.60s: Impact: vines burst from the ground in a ring.
  4. t=0.75s: Peak: ten thorned vine arcs coil around the dummies; amber thorn glints; leaves and petals; root cracks and a leaf-notch ring.
  5. t=1.20s: Hold: the dummies rooted.
  6. t=2.10s: The vines wither from the tips.
  7. t=2.50s: Falling leaves.
  8. t=2.85s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 6 of 7: `h03_featherstorm` Featherstorm Murmuration (skill 6, ultimate + damage)

What it is: One great moon-arrow shot skyward bursts into a murmuration of 24 feather-blades that swirl and dive over a 6 m field in waves, ending in a crescent dive.
- Palette: core #F4FFF8, body #5CE6A0, edge #1F9E86, accent #FFB84A, moon #DDE6F2.
- Telegraph on the ground: a DOUBLE vermilion ring (#FF4F3A) with 8 inward-pointing teeth and a diagonal hatch fill, radius 6 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 10 m ahead.
- Peak coverage: about 40 % of the frame.
- Layers to show: anticipation: The moon-arrow streaks up with a jade-amber trail; a pale crescent-moon appears 8 m above the field. Core: 24 feather-blades flock in a deterministic spiral murmuration and dive in waves. Secondaries: Shed feathers, wind ribbons on 6 lead blades, impact puffs per dive. Ground: A large jade swirl r 6 m turning, feather-cut marks and the leaf ring. After-effect: The crescent dive impact (amber star and shock ring), then falling feathers and mist for 1.5 s.
- Readability: Blades are thin and dark-edged and dive in waves, never all at once; enemies inside stay visible.
- Frames:
  1. t=0.25s: She shoots one great moon-arrow skyward with a jade-amber trail; the double toothed vermilion ring (6 m) at the target.
  2. t=0.90s: A pale crescent moon appears 8 m above the field.
  3. t=1.10s: The arrow bursts into a murmuration of 24 feather-blades swirling in a spiral flock.
  4. t=1.60s: Wave dives: blades stream down in arcs, impact puffs, wind ribbons, a large jade swirl turning.
  5. t=2.20s: The flock re-forms higher and dives again.
  6. t=2.85s: The final crescent dive: an amber flash and a shock ring; the dummies Marked and Gusted.
  7. t=3.40s: Falling feathers and mist.
  8. t=4.20s: Aftermath; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 7 of 7: `h03_basic` Snapfeather Shots (basic attack, damage)

What it is: Two quick snap shots.
- Palette: core #F0FFF6, body #5CE6A0, edge #1F9E86, accent #FFB84A.
- Telegraph on the ground: none on the ground (basic attack); you may show thin amber corner brackets under the target dummy.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 9 m ahead.
- Peak coverage: about 3 % of the frame.
- Layers to show: anticipation: A jade flicker at the nock. Core: The arrow with a thin jade wind ribbon. Secondaries: 4 feather motes shed. Ground: A small jade impact burst. After-effect: A drifting feather.
- Frames:
  1. t=0.05s: A jade flicker at the nock.
  2. t=0.10s: Release: the arrow with a thin jade ribbon.
  3. t=0.25s: Mid-flight; feather motes shed.
  4. t=0.40s: Impact: a small jade burst.
  5. t=0.45s: Second draw.
  6. t=0.50s: Release 2.
  7. t=0.70s: Impact 2.
  8. t=0.95s: A drifting feather; empty.
- Variants: 1 (basic attack).

Deliver `skills_03_archer_keyframes_v1.zip`: 19 PNG at 2400×1350 named `<skill_id>_v<n>.png`, plus README.md (per sheet: the prompt used, the palette hex values and the checklist results) and receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per sheet in the README):
- 8 frames in a 4 × 2 grid, each labelled with its time, one camera;
- anticipation → peak → dissipation reads at a 25 % thumbnail;
- the palette hues match the sheet; colourful mid-tones; no white-clipped blobs;
- the hero and every dummy or ally stay readable in every frame (check in greyscale);
- the telegraph shape and size are as specified and visible in the wind-up frames;
- all five layers are visible in the peak frame;
- original; only the allowed text.

Originality: original Xexoria effects. Not World of Warcraft, Genshin Impact, Ragnarok, Lumivara, League of Legends, Final Fantasy XIV, Diablo or any other game's spells, icons or UI; no logos; no recognisable characters. The hero is only a grey silhouette: do not redesign them.
