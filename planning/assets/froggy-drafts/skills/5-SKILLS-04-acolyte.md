[Claude -> froggy | 2026-10-02 | SKILLS-04-acolyte]

TASK SKILLS-04-acolyte: effect key-frame reference sheets for hero 04, the Bull-kin Acolyte: 7 sheets (6 skills + the basic attack), CONCEPT, 16:9

Send order: 5 of 6 (the witch first). The VFX lane builds each effect from your sheet, then compares its in-game capture with it until they match (the reference-gauntlet loop). Design source: `docs/plans/2026-10-02-hero-skills-and-vfx-design.md`, hero 04.

Attach before sending:
- the owner's VFX quality-bar sheets, the bar to beat for layout, layering and readability (do not copy their designs): `content/ChatGPT Image Oct 1, 2026, 10_46_58 PM.png` (sword ring), `content/ChatGPT Image Oct 1, 2026, 10_45_00 PM.png` (palm projectile), `content/ChatGPT Image Oct 1, 2026, 10_46_38 PM.png` (ground vortex);
- the hero, for the silhouette only: `Downloads\hero\04\ChatGPT Image Oct 1, 2026, 01_14_07 PM.png` (front) and `Downloads\hero\04\ChatGPT Image Oct 1, 2026, 01_16_04 PM.png` (weapon);
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`.

Context: Xexoria is a stylised hand-painted browser MMO. Hero 04's party role: **Healer-support**. Element: Sun and spring (holy sunlight, healing water). Shape language: Sun-wheels with spokes (his shoulder emblems), halos and rays, rings of water, droplets and ripples, horn-like arcs. Round, radiant, calm. Hero palette: core #FFF8E1, body #FFC94A, edge #E07A1F, accent #3FE0C5, deep #167A8C.

Sheet format (the same for all 7 sheets):
- One 16:9 image, 2400×1350, holding 8 equal frames in a 4 × 2 grid read left to right, top row first, with thin dark gutters (#101418), like the attached quality-bar sheets.
- Top-left of each frame, in small light text: `t=0.20s`. Above the grid, one header line: the skill id and English name. No other text.
- Camera: the game's player camera, third person, 13 m from the hero, about 22 degrees above the horizon, vertical field of view about 58 degrees. The same camera in all 8 frames.
- Stage: a neutral mid-grey ground plane (#7A7F85) with a faint 1 m grid and a plain light-grey sky gradient. No scenery, no props, no weather.
- Scale: the hero as a flat mid-dark grey silhouette (#4A4F55) with the weapon, 2.05 m tall at the crown (very chunky bull-kin priest: curved horns, wide bell sleeves, layered robe with tassels, sun-ring sceptre in the right hand). Enemy dummies are plain dark grey capsules (#5E646B, 1.2-1.8 m); allies are light-grey silhouettes (#9AA1A8). Every silhouette stays readable in every frame; the effect never hides them.
- Telegraph: draw the exact ground shape given per sheet. The shape is the meaning: single smooth amber line = normal danger, double toothed vermilion with hatching = heavy, dashed pale-mint = ally benefit.

Look v2 (owner, 2026-10-02): bigger, more colourful, more detailed.
- Bigger: at the peak frame the effect covers about the given share of the frame, mostly through tall vertical shapes, not only flat ground rings; a short hold at the peak so it feels heavy.
- More colourful: the 2-3 hue palette given per sheet (core, body, accent), saturated mid-tones, value-graded edges, a coloured light spill on the ground. Bright cores stay below white: no blown-out white blobs.
- More detailed: show all five layers at the peak: anticipation (gather, runes), a solid core shape (mesh-like swirl, ring, slash, crystal, pillar), secondary particles (sparks, motes, petals, shards), a ground layer (decal, crack, scorch or rune circle) and an after-effect (motes, smoke, shimmer).
- Style: stylised hand-painted fantasy MMO effects with painterly, crisp shapes, readable at game distance.

## Sheet 1 of 7: `h04_springwell_rain` Springwell Rain (skill 1, heal + debuff)

What it is: A sunlit rain cloud blesses a 4 m circle for 4 s: allies heal and enemies get Soaked.
- Palette: core #F2FFFD, body #3FE0C5, edge #167A8C, accent #FFC94A.
- Telegraph on the ground: a DASHED pale-mint ring (#DFFFF0) with a soft inward glow, radius 4 m (never teeth).
- Stage: the hero silhouette left of centre, facing right into the frame; two light-grey allies and two dark dummies inside the circle 8 m ahead.
- Peak coverage: about 22 % of the frame.
- Layers to show: anticipation: Turquoise droplets spiral up from the sceptre ring; a cloud gathers 4 m above the target. Core: The cloud cluster with a sun-lit gold rim; rain streaks inside r 4 m; a small rainbow arc on the cloud edge. Secondaries: Splash crowns, gold glints in the drops, heal motes rising from allies. Ground: Wet ground r 4 m with ripples under the dashed ring. After-effect: The puddle sheen and a low mist fade.
- Readability: The cloud sits 4 m up and the rain streaks are thin at alpha 0.35, so characters under it stay readable.
- Frames:
  1. t=0.12s: Turquoise droplets spiral up from the sceptre ring; the 4 m dashed pale-mint ring appears at the target.
  2. t=0.30s: A cloud gathers 4 m above the circle, its edge lit gold.
  3. t=0.45s: Rain begins: thin turquoise streaks and the first splash crowns.
  4. t=1.00s: Peak: steady rain, a small rainbow on the cloud edge, splash rings and ripples, heal motes rising from allies, enemies dripping (Soaked).
  5. t=2.00s: Sustain.
  6. t=3.50s: Late sustain: the puddle sheen grows.
  7. t=4.40s: The cloud thins; the rain stops.
  8. t=5.30s: Aftermath: puddle sheen and mist; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 2 of 7: `h04_sunpalm_wave` Sunpalm Wave (skill 2, damage + heal)

What it is: A great sun-palm sigil flies 10 m: it heals each ally it passes through, then strikes the first enemy, blasting everything within 2.2 m back and leaving them Sunlit.
- Palette: core #FFF8E1, body #FFC94A, edge #E07A1F, accent #3FE0C5.
- Telegraph on the ground: an amber rectangle outline 2 m wide and 10 m long with small chevrons pointing away from the hero; then a single smooth amber ring of radius 2.2 m flashes at the impact point.
- Stage: the hero silhouette left of centre, facing right into the frame; one light-grey ally 4 m ahead in the path and three dark dummies 8 m ahead.
- Peak coverage: about 18 % of the frame.
- Layers to show: anticipation: Two gold sun swirls at his open palm and the sceptre ring; 12 converging light streaks. Core: the palm sigil at 1.8 m (a broad open palm inside a sun-wheel disc) and a gold release cone. Secondaries: 3 gold / turquoise helix ribbons, shed light streaks and light petals; a turquoise heal splash on each ally passed. Ground: A sun-flare vortex decal r 0 → 2.6 m and an impact flash decal. After-effect: A 2.5 m gold light funnel with lifted motes; Sunlit halos appear on the hit enemies.
- Frames:
  1. t=0.08s: Two gold swirls gather at his open palm; light streaks converge; the 2 × 10 m amber lane.
  2. t=0.18s: Palm thrust; the swirls at full size.
  3. t=0.26s: Release: a 1.8 m sun-palm sigil (an open palm in a sun-wheel disc) bursts out of a gold cone.
  4. t=0.45s: It passes through a light-grey ally: a turquoise heal splash; gold and turquoise helix ribbons.
  5. t=0.71s: Impact on the enemy: a broad gold flash, the 2.2 m amber ring flashes, dummies blasted back.
  6. t=0.90s: Peak hold: a sun-flare vortex and a rising light funnel; Sunlit halos on the dummies.
  7. t=1.40s: The funnel thins; the vortex slows.
  8. t=2.00s: Aftermath; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 3 of 7: `h04_dawn_mend` Dawn Mend (skill 3, heal)

What it is: A column of dawn light heals one ally for 35 plus 20 over 5 s and lifts one debuff.
- Palette: core #FFF8E1, body #FFD873, edge #E9A23B, accent #3FE0C5.
- Telegraph on the ground: four dashed pale-mint corner brackets (#DFFFF0) at the ally's feet.
- Stage: the hero silhouette left of centre, facing right into the frame; one light-grey ally 6 m ahead.
- Peak coverage: about 12 % of the frame.
- Layers to show: anticipation: A sun-wheel spins up in the crystal in the sceptre ring; a thin light thread reaches toward the ally. Core: A hollow light pillar descends on the ally, with a halo above the head. Secondaries: Rising gold motes and turquoise droplets. Ground: A sun-wheel decal r 1.2 m with turning spokes. After-effect: HoT: a faint slow halo and a few rising motes for 5 s.
- Readability: The pillar is hollow, so the ally's silhouette shows through.
- Frames:
  1. t=0.15s: A sun-wheel spins up in the sceptre ring; dashed pale-mint brackets on the ally.
  2. t=0.36s: A thin light thread reaches toward the ally.
  3. t=0.43s: A hollow column of dawn light descends on the ally; a halo above the head.
  4. t=0.55s: Peak: the column at full height, gold motes and turquoise droplets rising, a sun-wheel decal under the ally.
  5. t=0.75s: Hold.
  6. t=1.20s: The column fades to a soft halo (heal over time).
  7. t=3.00s: Heal over time: a faint halo and a few motes.
  8. t=5.30s: End; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 4 of 7: `h04_pilgrims_horn` Pilgrim's Horn Rush (skill 4, mobility + buff)

What it is: Head down, horns first: a 7 m bull rush that shoulders enemies aside and gives each ally he passes a 25 HP shield.
- Palette: core #FFF8E1, body #FFC94A, edge #E07A1F, accent #3FE0C5.
- Telegraph on the ground: an amber rectangle outline 2 m wide and 7 m long with small chevrons pointing away from the hero.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy and one light-grey ally along the 7 m path.
- Peak coverage: about 15 % of the frame.
- Layers to show: anticipation: Hooves scrape up dust; a sun-wheel spins between the horns. Core: A radiant gold bow wave and 2 horn ribbons. Secondaries: Hoof sparks and dust each step; a turquoise splash on each shielded ally. Ground: 4 glowing hoof prints and a dust trail. After-effect: Dust settles; a gold-hex shimmer (alpha 0.25) on shielded allies.
- Frames:
  1. t=0.07s: Hooves scrape up dust; a sun-wheel spins between his horns; the 2 × 7 m chevron lane.
  2. t=0.15s: Head down.
  3. t=0.25s: Rushing: a radiant gold bow wave and horn ribbons; hoof sparks.
  4. t=0.40s: He shoulders a dummy aside and passes an ally, who gets a turquoise splash and a gold-hex shield shimmer.
  5. t=0.52s: Stop; a dust burst.
  6. t=0.70s: Glowing hoof prints behind him.
  7. t=1.00s: Dust settling.
  8. t=1.25s: Empty.
- Variants: 3 separate generations of this same brief.

## Sheet 5 of 7: `h04_sunwheel_sanctum` Sunwheel Sanctum (skill 5, buff)

What it is: A 6 m sun-wheel blazes on the ground for 8 s: allies inside take 15 % less damage and get 20 % more healing; enemies entering are Sunlit.
- Palette: core #FFF8E1, body #FFC94A, edge #E07A1F, accent #3FE0C5.
- Telegraph on the ground: a DASHED pale-mint ring (#DFFFF0) with a soft inward glow, radius 6 m (never teeth).
- Stage: the hero silhouette left of centre, facing right into the frame; three light-grey allies inside the wheel and one dark dummy stepping in.
- Peak coverage: about 28 % of the frame.
- Layers to show: anticipation: 12 sun spokes wipe out along the ground from his hooves to r 6 m. Core: The sun-wheel (12 spokes, double ring, sun glyphs) and a translucent gold rim wall (r 6 m, 1.2 m tall, alpha 0.35). Secondaries: Gold motes rising along the rim, occasional turquoise droplets inside, slowly turning spoke beams. Ground: A warm ground tint under the wheel. After-effect: The spokes retract into the centre; gold mist fades.
- Frames:
  1. t=0.10s: Twelve sun spokes wipe outward along the ground from his hooves; the 6 m dashed pale-mint ring.
  2. t=0.28s: The spokes reach 6 m.
  3. t=0.40s: The full sun-wheel blazes; a translucent gold rim wall rises 1.2 m.
  4. t=0.80s: Peak: gold motes along the rim, slow turning spoke beams, allies inside lit warm; a dummy entering gets a Sunlit halo.
  5. t=2.50s: Sustain.
  6. t=6.00s: Late sustain.
  7. t=8.40s: The spokes retract into the centre.
  8. t=9.20s: Gold mist fading; empty.
- Variants: 3 separate generations of this same brief.

## Sheet 6 of 7: `h04_noonspring_covenant` Noonspring Covenant (skill 6, ultimate + heal)

What it is: He calls the noon sun down and a holy spring up: allies within 8 m heal 50, shed every debuff, and downed allies rise at 30 % HP; enemies inside are Soaked and Sunlit.
- Palette: core #FFF8E1, body #FFC94A, edge #E07A1F, accent #3FE0C5.
- Telegraph on the ground: a DOUBLE DASHED pale-mint ring (#DFFFF0) with a soft inward glow, radius 8 m (never teeth).
- Stage: the hero silhouette left of centre, facing right into the frame; three light-grey allies around him (one lying down, being revived) and two dark dummies at 6 m.
- Peak coverage: about 45 % of the frame.
- Layers to show: anticipation: A sun disc descends to 10 m above him; turquoise water rises in a spiral from the ground. Core: A hollow central light pillar (r 2 m, 10 m tall), a turquoise geyser column and an expanding water ring wave (r 0 → 8 m, 0.8 m tall). Secondaries: Sun sparks, water droplet arcs, a rainbow arc in the geyser spray. Ground: The sun-wheel r 8 m and wet ripples. After-effect: A gentle gold mote rain, puddle sheen and mist.
- Readability: The pillar is hollow and alpha-capped; the water ring is low (0.8 m) and fast; every ally stays visible; SAFE rings never get teeth.
- Frames:
  1. t=0.25s: A sun disc with turning spokes descends toward 10 m above him; the double dashed pale-mint ring (8 m).
  2. t=0.70s: Turquoise water rises in a spiral from the ground around him.
  3. t=0.85s: Release: a hollow pillar of noon light and a turquoise geyser burst up together.
  4. t=1.05s: Peak: a water ring wave races out to 8 m; droplet arcs and a rainbow in the spray; allies lit gold and healed; a downed ally rises.
  5. t=1.30s: Hold: the sun-wheel blazes; enemies dripping and haloed (Soaked + Sunlit).
  6. t=1.80s: The pillar fades; a gold mote rain.
  7. t=2.50s: Puddle sheen and mist.
  8. t=3.20s: Aftermath; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 7 of 7: `h04_basic` Sunring Strikes (basic attack, damage)

What it is: Two sceptre strikes; each flashes a small sun-wheel on contact.
- Palette: core #FFF8E1, body #FFC94A, edge #E07A1F, accent #3FE0C5.
- Telegraph on the ground: none on the ground (basic attack); you may show thin amber corner brackets under the target dummy.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 2 m ahead.
- Peak coverage: about 4 % of the frame.
- Layers to show: anticipation: The sun-ring flares gold. Core: A short gold arc ribbon and a spoked sun-wheel flash (0.8 m) on hit. Secondaries: 6 gold sparks and 4 turquoise droplets. Ground: A small radiant ring r 1 m on link 2. After-effect: Gold motes for 300 ms.
- Frames:
  1. t=0.05s: The sun-ring flares gold.
  2. t=0.10s: Strike 1: a short gold arc.
  3. t=0.16s: Contact: a spoked sun-wheel flash, gold sparks, turquoise droplets.
  4. t=0.30s: Motes.
  5. t=0.45s: The strike-2 glow.
  6. t=0.50s: Strike 2 arc.
  7. t=0.56s: Contact and a small radiant ring on the ground.
  8. t=0.85s: Empty.
- Variants: 1 (basic attack).

Deliver `skills_04_acolyte_keyframes_v1.zip`: 19 PNG at 2400×1350 named `<skill_id>_v<n>.png`, plus README.md (per sheet: the prompt used, the palette hex values and the checklist results) and receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per sheet in the README):
- 8 frames in a 4 × 2 grid, each labelled with its time, one camera;
- anticipation → peak → dissipation reads at a 25 % thumbnail;
- the palette hues match the sheet; colourful mid-tones; no white-clipped blobs;
- the hero and every dummy or ally stay readable in every frame (check in greyscale);
- the telegraph shape and size are as specified and visible in the wind-up frames;
- all five layers are visible in the peak frame;
- original; only the allowed text.

Originality: original Xexoria effects. Not World of Warcraft, Genshin Impact, Ragnarok, Lumivara, League of Legends, Final Fantasy XIV, Diablo or any other game's spells, icons or UI; no logos; no recognisable characters. The hero is only a grey silhouette: do not redesign them.
