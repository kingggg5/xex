[Claude -> froggy | 2026-10-02 | SKILLS-01-swordsman]

TASK SKILLS-01-swordsman: effect key-frame reference sheets for hero 01, the Orc Swordsman: 7 sheets (6 skills + the basic attack), CONCEPT, 16:9

Send order: 2 of 6 (the witch first). The VFX lane builds each effect from your sheet, then compares its in-game capture with it until they match (the reference-gauntlet loop). Design source: `docs/plans/2026-10-02-hero-skills-and-vfx-design.md`, hero 01.

Attach before sending:
- the owner's VFX quality-bar sheets, the bar to beat for layout, layering and readability (do not copy their designs): `content/ChatGPT Image Oct 1, 2026, 10_46_58 PM.png` (sword ring), `content/ChatGPT Image Oct 1, 2026, 10_45_00 PM.png` (palm projectile), `content/ChatGPT Image Oct 1, 2026, 10_46_38 PM.png` (ground vortex);
- the hero, for the silhouette only: `Downloads\hero\01\ChatGPT Image Oct 1, 2026, 01_13_38 PM.png` (front) and `Downloads\hero\01\ChatGPT Image Oct 1, 2026, 01_15_52 PM.png` (weapon);
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`.

Context: Xexoria is a stylised hand-painted browser MMO. Hero 01's party role: **Tank**. Element: Storm-steel (thunder + steel). Shape language: Heavy crescents and arcs, ground cracks and splits, spectral blades, the four-point stars and eight-point compass from his armour, lightning forks. Angular and heavy; everything lands on the ground. Hero palette: core #F4FBFF, body #7FD3FF, edge #2B6CFF, accent #FFC94A, dark #0E1F4D.

Sheet format (the same for all 7 sheets):
- One 16:9 image, 2400×1350, holding 8 equal frames in a 4 × 2 grid read left to right, top row first, with thin dark gutters (#101418), like the attached quality-bar sheets.
- Top-left of each frame, in small light text: `t=0.20s`. Above the grid, one header line: the skill id and English name. No other text.
- Camera: the game's player camera, third person, 13 m from the hero, about 22 degrees above the horizon, vertical field of view about 58 degrees. The same camera in all 8 frames.
- Stage: a neutral mid-grey ground plane (#7A7F85) with a faint 1 m grid and a plain light-grey sky gradient. No scenery, no props, no weather.
- Scale: the hero as a flat mid-dark grey silhouette (#4A4F55) with the weapon, 2.00 m tall at the crown (very broad orc knight: huge layered pauldrons, knee-length tabard, one-handed longsword in the right hand). Enemy dummies are plain dark grey capsules (#5E646B, 1.2-1.8 m); allies are light-grey silhouettes (#9AA1A8). Every silhouette stays readable in every frame; the effect never hides them.
- Telegraph: draw the exact ground shape given per sheet. The shape is the meaning: single smooth amber line = normal danger, double toothed vermilion with hatching = heavy, dashed pale-mint = ally benefit.

Look v2 (owner, 2026-10-02): bigger, more colourful, more detailed.
- Bigger: at the peak frame the effect covers about the given share of the frame, mostly through tall vertical shapes, not only flat ground rings; a short hold at the peak so it feels heavy.
- More colourful: the 2-3 hue palette given per sheet (core, body, accent), saturated mid-tones, value-graded edges, a coloured light spill on the ground. Bright cores stay below white: no blown-out white blobs.
- More detailed: show all five layers at the peak: anticipation (gather, runes), a solid core shape (mesh-like swirl, ring, slash, crystal, pillar), secondary particles (sparks, motes, petals, shards), a ground layer (decal, crack, scorch or rune circle) and an after-effect (motes, smoke, shimmer).
- Style: stylised hand-painted fantasy MMO effects with painterly, crisp shapes, readable at game distance.

## Sheet 1 of 7: `h01_lodestar_arc` Lodestar Arc (skill 1, damage)

What it is: A wide 120° storm-steel crescent that hits up to three enemies and leaves them Charged.
- Palette: core #F4FBFF, body #7FD3FF, edge #2B6CFF, accent #FFC94A.
- Telegraph on the ground: a single smooth amber wedge outline, 120 degrees, 4 m long, faint fill from the apex.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies 6-9 m ahead.
- Peak coverage: about 16 % of the frame.
- Layers to show: anticipation: A gold four-point star gathers on the sword tip; 6 static sparks crawl up the blade; dust grinds under the back foot. Core: A 120° x 4 m storm-steel crescent (scrolling storm streaks, cyan core → storm-blue edge, gold rim) sweeps with the weapon ribbon. Secondaries: 3 lightning forks peel off the crescent edge; 12 gold sparks; 6 steel shards. Ground: An arc-masked crack along the swing and dust puffs. After-effect: Blue haze cools; Charged crackle markers appear on hit enemies.
- Frames:
  1. t=0.10s: A gold four-point star gathers at the blade tip; static sparks crawl up the blade; the 4 m, 120° amber fan draws.
  2. t=0.23s: The star at its brightest; dust grinds under his back foot.
  3. t=0.27s: The 120° storm-steel crescent sweeps out (cyan core, storm-blue edge, gold rim).
  4. t=0.33s: Peak: the crescent at full 4 m; three lightning forks peel off its edge; gold sparks and steel shards fly; light flash on the ground.
  5. t=0.45s: Hold: the crescent thins; an arc-shaped crack glows; dust puffs.
  6. t=0.65s: The crescent is gone; Charged crackle on three dummies; blue haze.
  7. t=0.95s: The crack cools; the haze fades.
  8. t=1.30s: Aftermath: a faint crack and crackle; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 2 of 7: `h01_bladeward_nova` Bladeward Nova (skill 2, control + damage)

What it is: Twelve spectral swords erupt around the orc, knock enemies up and taunt them onto him.
- Palette: core #F4FBFF, body #7FD3FF, edge #2B6CFF, accent #FFC94A, scorch #0E1F4D.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 4 m.
- Stage: the hero silhouette left of centre, facing right into the frame; four dark dummies standing 2-4 m around the hero.
- Peak coverage: about 22 % of the frame.
- Layers to show: anticipation: The sword-notched ring draws clockwise at r 4.0 m; 16 charge sparks spiral from the ring into the hilt. Core: 12 spectral blades, scaled 1.3 to 2.7 m, rise at radii 2.9 / 3.5 m, staggered clockwise, with a fresnel rim, a glowing fuller and gold guards; erode tip → hilt from 700 ms. Secondaries: Dust puffs at the blade bases, shards thrown out, and 4-6 lightning arcs between neighbouring blades (260-700 ms). Ground: A 3.2 m ground flash, a shock ring and 0.6 m ring wall r 0.5 → 4.6 m, and base cracks per blade cooling to #0E1F4D. After-effect: Frost-blue mist cards drifting outward.
- Readability: Blades stand on the 2.9-3.5 m perimeter; the orc and the taunted enemies inside stay readable.
- Frames:
  1. t=0.05s: The sword-notched ring draws clockwise at r 4 m; charge sparks rise from it.
  2. t=0.15s: Ring complete; sparks spiral into the hilt as he plants the sword.
  3. t=0.21s: Eruption: spectral swords burst up in a clockwise wave; ground flash; dummies knocked up.
  4. t=0.30s: Peak: twelve 2.7 m spectral swords (blue bodies, bright edges, gold guards) tilted outward; shock ring and ring wall; lightning arcs between blades; debris.
  5. t=0.45s: Hold: base cracks glow at every blade; frost-blue mist rolls outward; taunt marks over the dummies.
  6. t=0.80s: The blades dissolve from tip to hilt with glowing edges.
  7. t=1.20s: The last hilts fade; the cracks cool to deep blue.
  8. t=1.80s: Aftermath: cracks and mist; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 3 of 7: `h01_ironfall_cleave` Ironfall Cleave (skill 3, debuff + damage)

What it is: A two-handed overhead cleave that splits the ground in a 5 m line, staggers, breaks guards and Cracks armour.
- Palette: core #F4FBFF, body #7FD3FF, edge #2B6CFF, accent #FFC94A.
- Telegraph on the ground: a DOUBLE vermilion outline (#FF4F3A) with teeth and a diagonal hatch fill, 1.6 m wide and 5 m long.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies in a line 4-6 m ahead.
- Peak coverage: about 15 % of the frame.
- Layers to show: anticipation: The sword lifts two-handed; gold light runs down the fuller; grit lifts off the ground along the lane. Core: A tall vertical 180° crescent (3 m) and a falling spectral blade ghost (×1.4) slam down at 333 ms. Secondaries: Rock chunks (earth-tinted shards), a spark burst, and dust walls along both sides of the split. Ground: A 5 m ground split with a cyan-gold emissive seam cooling to scorch. After-effect: Seam embers and settling dust; Cracked shard markers orbit hit enemies.
- Frames:
  1. t=0.12s: He lifts the sword two-handed; gold light runs down the fuller; grit lifts along the double toothed vermilion lane.
  2. t=0.30s: Overhead apex; sparks orbit the blade.
  3. t=0.36s: The slam: a 3 m vertical crescent and a falling spectral blade ghost hit the ground.
  4. t=0.45s: Peak: a 5 m ground split with a cyan-gold seam rips forward; rock chunks and spark bursts; dust walls on both sides.
  5. t=0.60s: Hold: the seam blazes; debris falls.
  6. t=0.90s: Cracked shard markers orbit the dummies; dust settles.
  7. t=1.30s: The seam cools to scorch; embers.
  8. t=1.80s: Aftermath: a dark split line; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 4 of 7: `h01_compass_rush` Compass Rush (skill 4, mobility)

What it is: Behind a spectral compass shield the orc charges 8 m, shouldering enemies aside; he stops at the first elite or boss and staggers it.
- Palette: core #FFF6DA, body #FFC94A, edge #2B6CFF, accent #7FD3FF.
- Telegraph on the ground: an amber rectangle outline 2 m wide and 8 m long with small chevrons pointing away from the hero.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies in a line 4-6 m ahead.
- Peak coverage: about 15 % of the frame.
- Layers to show: anticipation: A compass-star shield sigil (2 m) blooms in front; 8 gold motes snap into its points. Core: The sigil leads the charge with a gold → blue bow wave. Secondaries: Pauldron ribbons, ground-skid sparks, dust streaks. Ground: Two parallel scorched skid lines and dust puffs. After-effect: The sigil breaks into 8 gold shards that fade as the dust settles.
- Frames:
  1. t=0.05s: A compass-star shield sigil blooms in front of him; gold motes snap into its eight points; the 2 × 8 m chevron lane shows.
  2. t=0.12s: The sigil is complete; he leans into the charge.
  3. t=0.25s: Charging: the sigil leads, a gold bow wave, pauldron ribbons streaming, skid sparks.
  4. t=0.40s: Peak: dummies shouldered aside with spark bursts; two scorched skid lines behind him.
  5. t=0.53s: He stops; the sigil flares.
  6. t=0.70s: The sigil breaks into 8 gold shards.
  7. t=0.95s: The shards fade; dust settles along the skid lines.
  8. t=1.25s: Aftermath: faint skid lines; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 5 of 7: `h01_eightfold_ward` Eightfold Ward (skill 5, buff)

What it is: He plants the sword: eight spectral shields circle a 5 m compass, and allies inside take 25 % less damage for 6 s.
- Palette: core #FFF6DA, body #FFC94A, edge #2B6CFF, accent #7FD3FF.
- Telegraph on the ground: a DASHED pale-mint ring (#DFFFF0) with a soft inward glow, radius 5 m (never teeth).
- Stage: the hero silhouette left of centre, facing right into the frame; two light-grey allies inside the ring and two dark dummies just outside it.
- Peak coverage: about 22 % of the frame.
- Layers to show: anticipation: The sword plants; 8 thin gold light pillars rise at the compass points. Core: 8 shield sigils (1.4 m) orbit the 5 m ring at 15°/s; when an ally inside is hit, the nearest shield flares. Secondaries: Gold motes rising along the rim; slow gold threads linking neighbouring shields. Ground: An eight-point compass decal r 5 m, slowly turning. After-effect: The shields fold into the ground with a ring wave and motes.
- Readability: Shields stand on the perimeter; the centre stays clear for allies.
- Frames:
  1. t=0.10s: He plants the sword; 8 thin gold light pillars rise at the compass points of a 5 m dashed pale-mint ring.
  2. t=0.28s: The eight-point compass rune flashes onto the ground.
  3. t=0.40s: Eight spectral shield sigils rise from the pillars.
  4. t=0.80s: Peak: the shields orbit slowly at 1.4 m, gold threads link them, motes rise along the rim; light-grey allies inside.
  5. t=2.00s: A dummy hits an ally: the nearest shield flares.
  6. t=4.00s: Sustain: steady orbit; the compass rune turns slowly.
  7. t=6.40s: End: the shields fold into the ground with a ring wave.
  8. t=7.00s: Aftermath: fading motes; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 6 of 7: `h01_stormfall_cleave` Stormfall Cleave (skill 6, ultimate + damage)

What it is: The orc leaps, calls the storm into a 6 m spectral greatsword and brings it down along a 10 m line that ends in a thunder crater.
- Palette: core #F4FBFF, body #7FD3FF, edge #2B6CFF, accent #FFC94A, dark #0E1F4D.
- Telegraph on the ground: a DOUBLE vermilion outline (#FF4F3A) with teeth and a diagonal hatch fill, 3 m wide and 10 m long; then a double toothed vermilion ring of radius 4 m at the far end of the lane.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies in a line 4-8 m ahead.
- Peak coverage: about 42 % of the frame.
- Layers to show: anticipation: A storm-cloud disc forms 8 m above the line; the compass ring flashes under him; lightning crawls up the sword as he leaps 1.5 m. Core: A 6 m spectral greatsword falls along the line; a 6 m crater flash at 700 ms. Secondaries: 6 vertical bolts strike along the line, debris and gold sparks. Ground: A 10 m ground split, crater cracks, a shock ring r 0 → 5 m and scorch. After-effect: Static arcs crawl over the scorched line for 1.5 s; blue smoke; embers.
- Frames:
  1. t=0.20s: A dark storm-cloud disc spins up 8 m above the 10 m double toothed lane; lightning crawls up his sword.
  2. t=0.55s: He leaps; the sword is wrapped in storm light; the lane and the 4 m end ring are fully drawn.
  3. t=0.69s: A 6 m spectral greatsword falls along the line.
  4. t=0.75s: Impact: crater flash at the end of the line; six vertical bolts strike along it; debris and gold sparks.
  5. t=0.95s: Peak hold: a 10 m ground split blazing cyan-gold, a shock ring at the crater, dummies knocked down.
  6. t=1.40s: Static arcs crawl over the scorched line; blue smoke rises.
  7. t=2.20s: The greatsword dissolves; embers and smoke thin.
  8. t=2.90s: Aftermath: a dark scorched line; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 7 of 7: `h01_basic` Stormsteel Strikes (basic attack, damage)

What it is: Two heavy one-handed cuts; the second throws a short gold-rimmed crescent.
- Palette: core #F4FBFF, body #7FD3FF, edge #2B6CFF, accent #FFC94A.
- Telegraph on the ground: none on the ground (basic attack); you may show thin amber corner brackets under the target dummy.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 2 m ahead.
- Peak coverage: about 3 % of the frame.
- Layers to show: anticipation: A steel glint travels base → tip along the blade. Core: The weapon ribbon (sky-cyan core, storm-blue edge, 160 ms); link 2 adds a 90° crescent (1.2 m) with a gold rim. Secondaries: 6 gold sparks and 2 tiny static forks. Ground: Boot-scuff dust on link 2. After-effect: Static crackle on the blade.
- Frames:
  1. t=0.05s: A steel glint runs up the blade.
  2. t=0.10s: Cut 1: a sky-cyan ribbon arc with a storm-blue edge.
  3. t=0.16s: Contact: 6 gold sparks and a tiny static fork on the dummy.
  4. t=0.30s: The ribbon fades; static crackle on the blade.
  5. t=0.45s: Cut 2 begins: glint.
  6. t=0.50s: Cut 2: a wider 90° crescent with a gold rim.
  7. t=0.56s: Contact: sparks; dust scuffs under his boot.
  8. t=0.85s: The last crackle and dust; empty.
- Variants: 1 (basic attack).

Deliver `skills_01_swordsman_keyframes_v1.zip`: 19 PNG at 2400×1350 named `<skill_id>_v<n>.png`, plus README.md (per sheet: the prompt used, the palette hex values and the checklist results) and receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per sheet in the README):
- 8 frames in a 4 × 2 grid, each labelled with its time, one camera;
- anticipation → peak → dissipation reads at a 25 % thumbnail;
- the palette hues match the sheet; colourful mid-tones; no white-clipped blobs;
- the hero and every dummy or ally stay readable in every frame (check in greyscale);
- the telegraph shape and size are as specified and visible in the wind-up frames;
- all five layers are visible in the peak frame;
- original; only the allowed text.

Originality: original Xexoria effects. Not World of Warcraft, Genshin Impact, Ragnarok, Lumivara, League of Legends, Final Fantasy XIV, Diablo or any other game's spells, icons or UI; no logos; no recognisable characters. The hero is only a grey silhouette: do not redesign them.
