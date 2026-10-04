[Claude -> froggy | 2026-10-02 | SKILLS-05-thief]

TASK SKILLS-05-thief: effect key-frame reference sheets for hero 05, the Rogue Thief: 7 sheets (6 skills + the basic attack), CONCEPT, 16:9

Send order: 3 of 6 (the witch first). The VFX lane builds each effect from your sheet, then compares its in-game capture with it until they match (the reference-gauntlet loop). Design source: `docs/plans/2026-10-02-hero-skills-and-vfx-design.md`, hero 05.

Attach before sending:
- the owner's VFX quality-bar sheets, the bar to beat for layout, layering and readability (do not copy their designs): `content/ChatGPT Image Oct 1, 2026, 10_46_58 PM.png` (sword ring), `content/ChatGPT Image Oct 1, 2026, 10_45_00 PM.png` (palm projectile), `content/ChatGPT Image Oct 1, 2026, 10_46_38 PM.png` (ground vortex);
- the hero, for the silhouette only: `Downloads\hero\05\ChatGPT Image Oct 1, 2026, 01_14_13 PM.png` (front) and `planning\evidence\turnaround-qa-20261002\hero-05\weapon-crop\dagger_left.png` (weapon);
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`.

Context: Xexoria is a stylised hand-painted browser MMO. Hero 05's party role: **Melee DPS**. Element: Shadow and venom. Shape language: Diamonds (his cape's diamond-cut hem), X-crosses, thin crescents, smoke petals and drips. Sharp, quick, low to the ground. Hero palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.

Sheet format (the same for all 7 sheets):
- One 16:9 image, 2400×1350, holding 8 equal frames in a 4 × 2 grid read left to right, top row first, with thin dark gutters (#101418), like the attached quality-bar sheets.
- Top-left of each frame, in small light text: `t=0.20s`. Above the grid, one header line: the skill id and English name. No other text.
- Camera: the game's player camera, third person, 13 m from the hero, about 22 degrees above the horizon, vertical field of view about 58 degrees. The same camera in all 8 frames.
- Stage: a neutral mid-grey ground plane (#7A7F85) with a faint 1 m grid and a plain light-grey sky gradient. No scenery, no props, no weather.
- Scale: the hero as a flat mid-dark grey silhouette (#4A4F55) with the weapon, 1.78 m tall at the crown (slim human rogue: hood worn as a scarf, steel pauldrons, long purple cape with a diamond-cut hem, a curved dagger in each hand). Enemy dummies are plain dark grey capsules (#5E646B, 1.2-1.8 m); allies are light-grey silhouettes (#9AA1A8). Every silhouette stays readable in every frame; the effect never hides them.
- Telegraph: draw the exact ground shape given per sheet. The shape is the meaning: single smooth amber line = normal danger, double toothed vermilion with hatching = heavy, dashed pale-mint = ally benefit.

Look v2 (owner, 2026-10-02): bigger, more colourful, more detailed.
- Bigger: at the peak frame the effect covers about the given share of the frame, mostly through tall vertical shapes, not only flat ground rings; a short hold at the peak so it feels heavy.
- More colourful: the 2-3 hue palette given per sheet (core, body, accent), saturated mid-tones, value-graded edges, a coloured light spill on the ground. Bright cores stay below white: no blown-out white blobs.
- More detailed: show all five layers at the peak: anticipation (gather, runes), a solid core shape (mesh-like swirl, ring, slash, crystal, pillar), secondary particles (sparks, motes, petals, shards), a ground layer (decal, crack, scorch or rune circle) and an after-effect (motes, smoke, shimmer).
- Style: stylised hand-painted fantasy MMO effects with painterly, crisp shapes, readable at game distance.

## Sheet 1 of 7: `h05_adders_kiss` Adder's Kiss (skill 1, damage)

What it is: A double stab that injects Venom: one stack, or two from behind.
- Palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.
- Telegraph on the ground: four solid amber corner brackets (#FFBA4B, dark rim) at the target dummy's feet.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy in melee range.
- Peak coverage: about 10 % of the frame.
- Layers to show: anticipation: Lime venom beads run along both blades. Core: A crossed pair of thin crescents (X-diamond) at the target, magenta-plum. Secondaries: A small lime droplet spray and 8 bubbles. Ground: A 0.9 m lime splatter under the target. After-effect: Venom drips and pips on the target; green bubbles rising.
- Frames:
  1. t=0.05s: Lime venom beads run along both blades; solid amber brackets at the dummy's feet.
  2. t=0.12s: He lunges; the blades cross.
  3. t=0.15s: First stab: a thin magenta crescent.
  4. t=0.25s: Second stab: the crossed X-diamond slash at full size; lime spray.
  5. t=0.35s: A lime splatter decal under the dummy; bubbles.
  6. t=0.60s: Venom drips and two pips on the dummy.
  7. t=1.00s: Bubbles rising; the splatter fades.
  8. t=1.40s: Aftermath: a faint splatter; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 2 of 7: `h05_diamond_scatter` Diamond Scatter (skill 2, damage)

What it is: Six venom-coated diamond knives fan across a 70° cone.
- Palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.
- Telegraph on the ground: a single smooth amber wedge outline, 70 degrees, 8 m long, faint fill from the apex.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies 6-9 m ahead.
- Peak coverage: about 16 % of the frame.
- Layers to show: anticipation: Six knives fan between his fingers with glints; lime drips. Core: 6 spinning diamond knives with thin magenta ribbons. Secondaries: Lime droplets, sparks at impacts, diamond glints. Ground: Six small diamond knife marks and a fan-shaped lime splatter. After-effect: Venom bubbles on hit targets; the marks fade.
- Frames:
  1. t=0.08s: Six diamond knives fan between his fingers; lime drips; the 8 m, 70° amber fan shows.
  2. t=0.18s: Arm cocked; the knives glint.
  3. t=0.23s: Release: six spinning knives with thin magenta ribbons.
  4. t=0.32s: Peak: the knives hit the dummies: lime splashes, diamond glints, a magenta light flash.
  5. t=0.45s: Knife marks and a fan-shaped lime splatter on the ground.
  6. t=0.70s: Venom bubbles on the hit dummies.
  7. t=1.00s: The ribbons are gone; the splatter fades.
  8. t=1.40s: Aftermath; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 3 of 7: `h05_fangfall` Fangfall (skill 3, damage)

What it is: A leaping cross-cut that detonates every Venom stack on the target; brutal on wounded prey.
- Palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.
- Telegraph on the ground: four solid amber corner brackets (#FFBA4B, dark rim) at the target dummy's feet.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy in melee range.
- Peak coverage: about 14 % of the frame.
- Layers to show: anticipation: The blades cross overhead; lime venom swirls up both arms. Core: A large X-diamond slash (2 × 120°, 2 m) and a vertical fang spike. Secondaries: A venom burst scaled by stacks (1-3 rings of lime droplets) and magenta sparks. Ground: A diamond splatter r 1.2 m. After-effect: A lime mist lingers.
- Readability: Coverage grows +3 % per consumed stack, so a big detonation reads as big.
- Frames:
  1. t=0.07s: The blades cross overhead; lime venom swirls up both arms; amber brackets on the dummy.
  2. t=0.18s: Leap apex.
  3. t=0.22s: The cross-cut: a large 2 m X-diamond slash and a vertical fang spike.
  4. t=0.30s: Venom burst: three rings of lime droplets (three stacks); magenta sparks.
  5. t=0.42s: A 1.2 m diamond splatter; a lime light flash.
  6. t=0.65s: A lime mist lingers.
  7. t=1.00s: The mist thins.
  8. t=1.40s: Aftermath; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 4 of 7: `h05_duskstep` Duskstep (skill 4, mobility)

What it is: A 6 m smoke dash through enemies; everyone passed is Shadowed, and ending behind a target sets up a from-behind Adder's Kiss.
- Palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.
- Telegraph on the ground: an amber rectangle outline 1.5 m wide and 6 m long with small chevrons pointing away from the hero.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies in a line 4-6 m ahead.
- Peak coverage: about 15 % of the frame.
- Layers to show: anticipation: His silhouette smears; plum smoke gathers at the feet. Core: A wide plum smoke ribbon with diamond smoke puffs at the start and end. Secondaries: Diamond smoke petals and lime sparks. Ground: A plum shadow streak along the path (alpha-blended, value-lifted). After-effect: Lingering smoke wisps; Shadowed wisps trail from the passed enemies.
- Frames:
  1. t=0.03s: His silhouette smears; plum smoke at his feet; the 1.5 × 6 m chevron lane.
  2. t=0.08s: He dissolves into a diamond-shaped smoke puff.
  3. t=0.15s: A wide plum smoke ribbon streaks through two dummies.
  4. t=0.27s: He reappears behind them in a second diamond puff; smoke petals.
  5. t=0.40s: A shadow streak along the path; Shadowed wisps trail from the dummies.
  6. t=0.60s: Smoke wisps drifting.
  7. t=0.90s: The streak fades.
  8. t=1.25s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 5 of 7: `h05_nightbloom_smoke` Nightbloom Smoke (skill 5, control)

What it is: A bomb blooms into a 4 m flower of plum smoke for 4 s: enemies inside are Shadowed and slowed; allies inside shed threat.
- Palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 4 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 6 m ahead.
- Peak coverage: about 26 % of the frame.
- Layers to show: anticipation: A plum smoke bomb arcs to the point, trailing smoke. Core: 8 smoke petals unfold from the impact around a central bloom with a magenta core. Secondaries: Magenta glitter, lime pollen sparks, swirling wisps. Ground: A shadow-flower decal r 4 m (alpha-blended plum, value-lifted). After-effect: The petals dissolve into motes.
- Readability: Smoke stays ≤ 1.2 m tall at alpha ≤ 0.45: heads, nameplates and the amber ring stay visible.
- Frames:
  1. t=0.10s: He lobs a plum smoke bomb; the 4 m amber ring at the target.
  2. t=0.45s: The bomb mid-arc, trailing smoke.
  3. t=0.66s: Burst: eight smoke petals unfold like a night flower.
  4. t=1.00s: Peak: a 4 m plum smoke flower with a magenta core, lime pollen sparks and glitter; the dummies shadowed but visible (smoke under 1.2 m).
  5. t=2.00s: Sustain: the petals breathe and swirl slowly.
  6. t=3.50s: Late sustain: the petals thin.
  7. t=4.70s: End: the petals dissolve into motes.
  8. t=5.40s: Aftermath; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 6 of 7: `h05_violet_masquerade` Violet Masquerade (skill 6, ultimate + damage)

What it is: He vanishes behind a diamond mask and blinks between up to six enemies within 8 m, cutting each twice, then reappears in a diamond burst.
- Palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.
- Telegraph on the ground: a DOUBLE vermilion ring (#FF4F3A) with 8 inward-pointing teeth and a diagonal hatch fill, radius 8 m.
- Stage: the hero silhouette left of centre, facing right into the frame; four dark dummies standing 2-4 m around the hero.
- Peak coverage: about 38 % of the frame.
- Layers to show: anticipation: A diamond mask glyph flashes; the cape bursts into diamond shards; smoke engulfs him. Core: At each victim an X-diamond slash pair and a smoke-blink portal; an afterimage ribbon links the blink points. Secondaries: Lime venom spray, magenta petals, plum glitter. Ground: A diamond rune circle r 8 m and a splatter under each victim. After-effect: The finale diamond burst: a shock ring r 0 → 3 m and 8 diamond knives flung outward, then falling smoke petals and motes.
- Frames:
  1. t=0.10s: A diamond mask glyph flashes before him; the double toothed vermilion ring (8 m).
  2. t=0.28s: His cape bursts into diamond shards; smoke engulfs him.
  3. t=0.45s: Blink 1: an X-diamond slash on dummy 1, a smoke portal, an afterimage ribbon.
  4. t=0.80s: Blinks 2-3: two X slashes, lime venom spray; the afterimage ribbon zig-zags between dummies.
  5. t=1.30s: Blinks 4-6: the ribbon web across the ring, petals, one hopping magenta light.
  6. t=1.82s: Finale: he reappears in a diamond burst; a 3 m shock ring.
  7. t=2.40s: Petals and smoke falling; a splatter under each dummy.
  8. t=3.10s: Aftermath; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 7 of 7: `h05_basic` Dusk Cuts (basic attack, damage)

What it is: Right then left: two fast reverse-grip cuts.
- Palette: core #FFE6F6, body #C83C9E, edge #5E1150, accent #B6F23A.
- Telegraph on the ground: none on the ground (basic attack); you may show thin amber corner brackets under the target dummy.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 1 m ahead.
- Peak coverage: about 3 % of the frame.
- Layers to show: anticipation: A plum glint on the leading blade. Core: A thin dagger ribbon per hand (100 ms; magenta core → plum edge, lime rim). Secondaries: 4 sparks and a small X-diamond slash mark. Ground: A tiny dust tick on link 2. After-effect: One plum smoke wisp.
- Frames:
  1. t=0.03s: A plum glint on the right dagger.
  2. t=0.07s: Right cut: a thin magenta ribbon with a lime edge.
  3. t=0.12s: Contact: sparks and a small X-diamond slash mark.
  4. t=0.25s: A plum smoke wisp.
  5. t=0.43s: A glint on the left dagger.
  6. t=0.47s: Left cut ribbon.
  7. t=0.52s: Contact sparks and a dust tick.
  8. t=0.75s: Empty.
- Variants: 1 (basic attack).

Deliver `skills_05_thief_keyframes_v1.zip`: 19 PNG at 2400×1350 named `<skill_id>_v<n>.png`, plus README.md (per sheet: the prompt used, the palette hex values and the checklist results) and receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per sheet in the README):
- 8 frames in a 4 × 2 grid, each labelled with its time, one camera;
- anticipation → peak → dissipation reads at a 25 % thumbnail;
- the palette hues match the sheet; colourful mid-tones; no white-clipped blobs;
- the hero and every dummy or ally stay readable in every frame (check in greyscale);
- the telegraph shape and size are as specified and visible in the wind-up frames;
- all five layers are visible in the peak frame;
- original; only the allowed text.

Originality: original Xexoria effects. Not World of Warcraft, Genshin Impact, Ragnarok, Lumivara, League of Legends, Final Fantasy XIV, Diablo or any other game's spells, icons or UI; no logos; no recognisable characters. The hero is only a grey silhouette: do not redesign them.
