[Claude -> froggy | 2026-10-02 | SKILLS-06-tinker]

TASK SKILLS-06-tinker: effect key-frame reference sheets for hero 06, the Tinker Merchant: 7 sheets (6 skills + the basic attack), CONCEPT, 16:9

Send order: 4 of 6 (the witch first). The VFX lane builds each effect from your sheet, then compares its in-game capture with it until they match (the reference-gauntlet loop). Design source: `docs/plans/2026-10-02-hero-skills-and-vfx-design.md`, hero 06.

Attach before sending:
- the owner's VFX quality-bar sheets, the bar to beat for layout, layering and readability (do not copy their designs): `content/ChatGPT Image Oct 1, 2026, 10_46_58 PM.png` (sword ring), `content/ChatGPT Image Oct 1, 2026, 10_45_00 PM.png` (palm projectile), `content/ChatGPT Image Oct 1, 2026, 10_46_38 PM.png` (ground vortex);
- the hero, for the silhouette only: `Downloads\hero\06\ChatGPT Image Oct 1, 2026, 01_14_23 PM.png` (front) and `Downloads\hero\06\ChatGPT Image Oct 1, 2026, 01_16_12 PM.png` (weapon);
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`.

Context: Xexoria is a stylised hand-painted browser MMO. Hero 06's party role: **Utility**. Element: Forge and steam (heat, oil, clockwork). Shape language: Gears and cog teeth (her choker and studs), rivets, pistons, steam puffs, sparks, hex nuts. Chunky, mechanical, stepped. Hero palette: core #FFE7A3, body #FF7A1A, edge #C2361B, brass #D9A441, accent #2FD4C4, steam #E6EEF0.

Sheet format (the same for all 7 sheets):
- One 16:9 image, 2400×1350, holding 8 equal frames in a 4 × 2 grid read left to right, top row first, with thin dark gutters (#101418), like the attached quality-bar sheets.
- Top-left of each frame, in small light text: `t=0.20s`. Above the grid, one header line: the skill id and English name. No other text.
- Camera: the game's player camera, third person, 13 m from the hero, about 22 degrees above the horizon, vertical field of view about 58 degrees. The same camera in all 8 frames.
- Stage: a neutral mid-grey ground plane (#7A7F85) with a faint 1 m grid and a plain light-grey sky gradient. No scenery, no props, no weather.
- Scale: the hero as a flat mid-dark grey silhouette (#4A4F55) with the weapon, 1.72 m tall at the crown (sturdy tinker woman: big curly red hair with goggles, bulky gauntlets, apron and tool belt, wrench-hammer held two-handed). Enemy dummies are plain dark grey capsules (#5E646B, 1.2-1.8 m); allies are light-grey silhouettes (#9AA1A8). Every silhouette stays readable in every frame; the effect never hides them.
- Telegraph: draw the exact ground shape given per sheet. The shape is the meaning: single smooth amber line = normal danger, double toothed vermilion with hatching = heavy, dashed pale-mint = ally benefit.

Look v2 (owner, 2026-10-02): bigger, more colourful, more detailed.
- Bigger: at the peak frame the effect covers about the given share of the frame, mostly through tall vertical shapes, not only flat ground rings; a short hold at the peak so it feels heavy.
- More colourful: the 2-3 hue palette given per sheet (core, body, accent), saturated mid-tones, value-graded edges, a coloured light spill on the ground. Bright cores stay below white: no blown-out white blobs.
- More detailed: show all five layers at the peak: anticipation (gather, runes), a solid core shape (mesh-like swirl, ring, slash, crystal, pillar), secondary particles (sparks, motes, petals, shards), a ground layer (decal, crack, scorch or rune circle) and an after-effect (motes, smoke, shimmer).
- Style: stylised hand-painted fantasy MMO effects with painterly, crisp shapes, readable at game distance.

## Sheet 1 of 7: `h06_forgeheart_slam` Forgeheart Slam (skill 1, damage)

What it is: The hammer head glows forge-hot and slams a 2.5 m gear-shock that Scorches.
- Palette: core #FFE7A3, body #FF7A1A, edge #C2361B, accent #2FD4C4.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 2.5 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 2 m ahead.
- Peak coverage: about 17 % of the frame.
- Layers to show: anticipation: The head heats brass → glowing orange; 3 steam jets from the vents; sparks drip. Core: An orange anvil-star flash and a gear-tooth shock ring r 0 → 2.5 m. Secondaries: A forge-spark fountain, ember chunks, steam puffs. Ground: A soot-and-orange scorch with molten cracks cooling. After-effect: Soot smoke, small flames licking the scorch, embers; heat shimmer.
- Frames:
  1. t=0.10s: The hammer head heats from brass to glowing orange; steam jets from the vents; the 2.5 m amber ring.
  2. t=0.24s: Overhead; sparks drip from the head.
  3. t=0.29s: Slam: an anvil-star flash and a gear-tooth shock ring.
  4. t=0.36s: Peak: the gear ring at 2.5 m, a fountain of forge sparks, ember chunks, an orange light flash.
  5. t=0.50s: Hold: a scorch decal with glowing molten cracks; steam puffs.
  6. t=0.80s: Soot smoke rising; heat shimmer.
  7. t=1.40s: The cracks cool orange → soot; embers.
  8. t=2.20s: Aftermath; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 2 of 7: `h06_grease_flask` Grease Flask (skill 2, debuff + control)

What it is: A lobbed flask bursts into a 3.5 m puddle of glossy grease that Oils and slows enemies for 6 s.
- Palette: core #FFE7A3, body #8A5A1E, edge #2FD4C4, accent #E05AD0.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 3.5 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 7 m ahead.
- Peak coverage: about 16 % of the frame.
- Layers to show: anticipation: She pops the cork; the brass flask glints; a drip falls. Core: The flask arcs with a dripping trail; at 733 ms an oil crown splash. Secondaries: Oil droplets with an iridescent rim; bubbles. Ground: The puddle r 3.5 m: dark amber body lifted to sRGB ≥ 60, with a slow teal → magenta → gold sheen sweep. After-effect: The puddle shrinks and dulls; drips on Oiled enemies.
- Readability: The puddle body stays at sRGB ≥ 60 so dark enemies remain readable on it; the sheen carries the colour, so no PointLight.
- Frames:
  1. t=0.10s: She pops the cork; the brass flask glints; the 3.5 m amber ring at the target.
  2. t=0.45s: The flask mid-arc with a dripping trail.
  3. t=0.75s: Splat: a dark oil crown splash.
  4. t=0.95s: Peak: a glossy 3.5 m grease puddle with a slowly sweeping teal-magenta-gold sheen; bubbles; the dummies slowed and dripping.
  5. t=2.00s: Sustain: the sheen bands drift.
  6. t=4.00s: Late sustain.
  7. t=6.20s: The puddle shrinks and dulls.
  8. t=6.70s: Aftermath; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 3 of 7: `h06_cog_sentry` Cog Sentry (skill 3, damage)

What it is: A clockwork turret unfolds and fires brass bolts at the nearest enemy for 12 s, pulling threat off the back line.
- Palette: core #FFE7A3, body #D9A441, edge #FF7A1A, accent #2FD4C4.
- Telegraph on the ground: a thin brass-tinted ring of radius 1 m at the deploy spot.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 7 m from the sentry.
- Peak coverage: about 12 % of the frame.
- Layers to show: anticipation: A brass case unfolds with spinning gears over a 1 m gear-ring decal. Core: The sentry (teal lens eye, spinning gear); each shot is a muzzle cone and a brass bolt tracer. Secondaries: Spark casings and steam puffs per shot. Ground: The gear ring under it and small scorch ticks where bolts hit. After-effect: It folds, puffs steam and dissolves.
- Readability: Persistent effects stay small: about 4 % sustained.
- Frames:
  1. t=0.15s: She sets down a brass case; a gear-ring decal under it; a thin turning ring marks the spot.
  2. t=0.38s: The case unfolds: gears spin, the teal lens opens.
  3. t=0.55s: First shot: a muzzle cone and a brass bolt tracer toward the dummy.
  4. t=1.20s: Second shot: spark casings and a steam puff; a scorch tick where the bolt hit.
  5. t=3.00s: Sustain: the sentry tracks, gears turning.
  6. t=8.00s: Late sustain: more scorch ticks.
  7. t=12.40s: It folds with a steam puff.
  8. t=13.00s: Dissolving; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 4 of 7: `h06_boiler_leap` Boiler Leap (skill 4, mobility)

What it is: A steam canister blasts her 8 m through the air; the takeoff blast knocks enemies back.
- Palette: core #FFE7A3, body #FF7A1A, edge #C2361B, accent #2FD4C4, steam #E6EEF0.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 2.5 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 4 m ahead.
- Peak coverage: about 16 % of the frame.
- Layers to show: anticipation: The back canister hisses; its valves glow orange. Core: An upright steam blast funnel (pearl, orange core) and a ring wall burst r 0 → 2.5 m. Secondaries: Steam puffs, sparks, rivet glints; a steam contrail from the canister. Ground: A scald ring at takeoff and a landing dust ring. After-effect: Low steam lingers and fades at alpha ≤ 0.3.
- Frames:
  1. t=0.05s: The back canister hisses; the valves glow.
  2. t=0.12s: Crouch; steam leaks; the 2.5 m amber ring at her feet.
  3. t=0.20s: Blast: an upright steam funnel and a ring-wall burst push the dummies back.
  4. t=0.35s: Peak: she arcs through the air with a steam contrail; steam puffs and sparks below.
  5. t=0.55s: Mid-flight; a scald ring at the takeoff point.
  6. t=0.75s: Landing: a dust ring.
  7. t=1.20s: Low steam lingers at both points.
  8. t=1.80s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 5 of 7: `h06_mending_anvil` Mending Anvil (skill 5, buff)

What it is: She hammers an anvil-pylon into the ground: for 10 s it welds 12 HP of armour onto allies within 5 m every 2 s (max 36) and gives +10 % DEF.
- Palette: core #FFE7A3, body #D9A441, edge #FF7A1A, accent #2FD4C4.
- Telegraph on the ground: a DASHED pale-mint ring (#DFFFF0) with a soft inward glow, radius 5 m (never teeth).
- Stage: the hero silhouette left of centre, facing right into the frame; two light-grey allies inside the ring.
- Peak coverage: about 18 % of the frame.
- Layers to show: anticipation: Three hammer taps with spark bursts as the pylon drives in. Core: The pylon (anvil on a brass tripod, teal lens, spinning gear ring); a gear-tooth pulse ring every 2 s. Secondaries: Welding arcs (thin teal-orange beams) to each ally on every pulse; floating rivet and bolt motes. Ground: A gear-ring decal r 5 m under the dashed ring. After-effect: Allies wear a brass-hex shimmer (alpha 0.25) while shielded; at the end the pylon folds with a steam puff.
- Frames:
  1. t=0.10s: Tap one: she drives the anvil-pylon in; sparks; the 5 m dashed pale-mint ring.
  2. t=0.30s: Taps two and three: sparks; the gear-ring decal draws.
  3. t=0.50s: The pylon stands: teal lens lit, gear ring spinning.
  4. t=0.55s: First pulse: a gear-tooth ring sweeps out; welding arcs reach each ally; a brass-hex shimmer on them.
  5. t=2.55s: Second pulse.
  6. t=6.00s: Sustain: rivet motes drift; shields shimmer.
  7. t=10.50s: The pylon folds with a steam puff.
  8. t=11.00s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 6 of 7: `h06_gearstorm_hammerfall` Gearstorm Hammerfall (skill 6, ultimate + damage)

What it is: She hurls a beacon; a ring of spinning gears opens in the sky and a giant brass forge-hammer slams a 6 m crater of molten slag.
- Palette: core #FFE7A3, body #FF7A1A, edge #C2361B, accent #2FD4C4, brass #D9A441.
- Telegraph on the ground: a DOUBLE vermilion ring (#FF4F3A) with 8 inward-pointing teeth and a diagonal hatch fill, radius 6 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 8 m ahead.
- Peak coverage: about 48 % of the frame.
- Layers to show: anticipation: The beacon blinks; 3 gear rings assemble 8 m up and spin; steam jets and falling sparks. Core: A 5 m brass forge-hammer with glowing orange vents drops with ease-in; impact at 1900 ms. Secondaries: Spark fountains, molten droplets, steam bursts, flying gear teeth and rivets. Ground: Molten cracks r 6 m with an orange seam, a gear-tooth imprint and scorch. After-effect: The slag cools orange → soot with small flames; a smoke column; heat shimmer.
- Readability: The hammer is opaque for only 200 ms and lands on the HEAVY ring, which stays on top; the slag is a decal under characters.
- Frames:
  1. t=0.20s: She hurls a brass beacon; the double toothed vermilion ring (6 m) at the target.
  2. t=0.75s: The beacon lands blinking teal; three gear rings assemble 8 m up.
  3. t=1.40s: The rings spin into a portal; steam jets and raining sparks; a giant hammer head emerges.
  4. t=1.90s: Impact: the 5 m forge-hammer slams; spark fountains, gear teeth and rivets fly; an orange light flash.
  5. t=2.10s: Peak hold: molten cracks across 6 m, a gear-tooth imprint, steam bursts; dummies knocked down.
  6. t=2.80s: The hammer lifts and dissolves; the slag glows.
  7. t=4.50s: The slag cools orange → soot; a smoke column; heat shimmer.
  8. t=5.80s: Aftermath: dark cracks; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 7 of 7: `h06_basic` Wrench & Clang (basic attack, damage)

What it is: Two chunky two-handed swings of the wrench-hammer.
- Palette: core #FFE7A3, body #FF7A1A, edge #C2361B, accent #2FD4C4.
- Telegraph on the ground: none on the ground (basic attack); you may show thin amber corner brackets under the target dummy.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 2 m ahead.
- Peak coverage: about 4 % of the frame.
- Layers to show: anticipation: The hammer head flushes brass → warm orange. Core: A chunky arc ribbon (orange core → brass edge, 180 ms). Secondaries: 8 forge sparks and a gear-shaped glint. Ground: A 0.6 m scorch tap mark on link 2. After-effect: A soot puff.
- Frames:
  1. t=0.05s: The hammer head flushes warm orange.
  2. t=0.10s: Swing 1: a chunky orange-to-brass arc.
  3. t=0.16s: Clang: forge sparks and a gear-shaped glint.
  4. t=0.30s: A soot puff.
  5. t=0.45s: The second wind-up glow.
  6. t=0.50s: Swing 2 arc.
  7. t=0.56s: Clang and a scorch tap mark.
  8. t=0.85s: Empty.
- Variants: 1 (basic attack).

Deliver `skills_06_tinker_keyframes_v1.zip`: 19 PNG at 2400×1350 named `<skill_id>_v<n>.png`, plus README.md (per sheet: the prompt used, the palette hex values and the checklist results) and receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per sheet in the README):
- 8 frames in a 4 × 2 grid, each labelled with its time, one camera;
- anticipation → peak → dissipation reads at a 25 % thumbnail;
- the palette hues match the sheet; colourful mid-tones; no white-clipped blobs;
- the hero and every dummy or ally stay readable in every frame (check in greyscale);
- the telegraph shape and size are as specified and visible in the wind-up frames;
- all five layers are visible in the peak frame;
- original; only the allowed text.

Originality: original Xexoria effects. Not World of Warcraft, Genshin Impact, Ragnarok, Lumivara, League of Legends, Final Fantasy XIV, Diablo or any other game's spells, icons or UI; no logos; no recognisable characters. The hero is only a grey silhouette: do not redesign them.
