[Claude -> froggy | 2026-10-02 | SKILLS-02-witch]

TASK SKILLS-02-witch: effect key-frame reference sheets for hero 02, the Witch (Mage): 7 sheets (6 skills + the basic attack), CONCEPT, 16:9

Send order: 1 of 6 (the witch first). The VFX lane builds each effect from your sheet, then compares its in-game capture with it until they match (the reference-gauntlet loop). Design source: `docs/plans/2026-10-02-hero-skills-and-vfx-design.md`, hero 02.

Attach before sending:
- the owner's VFX quality-bar sheets, the bar to beat for layout, layering and readability (do not copy their designs): `content/ChatGPT Image Oct 1, 2026, 10_46_58 PM.png` (sword ring), `content/ChatGPT Image Oct 1, 2026, 10_45_00 PM.png` (palm projectile), `content/ChatGPT Image Oct 1, 2026, 10_46_38 PM.png` (ground vortex);
- the hero, for the silhouette only: `Downloads\hero\02\ChatGPT Image Oct 1, 2026, 01_14_27 PM.png` (front) and `Downloads\hero\02\ChatGPT Image Oct 1, 2026, 01_15_58 PM.png` (weapon);
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`.
- prior art for structure only: the three contact sheets in `Downloads\hero\02\vfx-blender-samples\lance\`, `...\aegis\` and `...\orrery\` (`contact_sheet.png`). They are too thin and too small for this brief: keep their rings, star arrays and crystal ideas, then add mass, colour and ground layers.

Context: Xexoria is a stylised hand-painted browser MMO. Hero 02's party role: **Control + ranged AoE**. Element: Astral frost and hollow (starlight, crystal ice, gravity). Shape language: Four-point sparkle stars (from her robe), heptagram rune circles, crescent moons, spirals and orbits, hexagonal crystal shards. Curved, orbiting, layered rings. Hero palette: core #FFF0FF, body #B07CFF, frost #A9C8FF, edge #5A1FD1, accent #FFD36E, rim #5FF2D8, abyss #12052B.

Sheet format (the same for all 7 sheets):
- One 16:9 image, 2400×1350, holding 8 equal frames in a 4 × 2 grid read left to right, top row first, with thin dark gutters (#101418), like the attached quality-bar sheets.
- Top-left of each frame, in small light text: `t=0.20s`. Above the grid, one header line: the skill id and English name. No other text.
- Camera: the game's player camera, third person, 13 m from the hero, about 22 degrees above the horizon, vertical field of view about 58 degrees. The same camera in all 8 frames.
- Stage: a neutral mid-grey ground plane (#7A7F85) with a faint 1 m grid and a plain light-grey sky gradient. No scenery, no props, no weather.
- Scale: the hero as a flat mid-dark grey silhouette (#4A4F55) with the weapon, 1.80 m (without the hat) tall at the crown (slim witch: wide-brim pointed hat with a bent tip, bell sleeves, floor-length layered robe, crystal staff in the right hand). Enemy dummies are plain dark grey capsules (#5E646B, 1.2-1.8 m); allies are light-grey silhouettes (#9AA1A8). Every silhouette stays readable in every frame; the effect never hides them.
- Telegraph: draw the exact ground shape given per sheet. The shape is the meaning: single smooth amber line = normal danger, double toothed vermilion with hatching = heavy, dashed pale-mint = ally benefit.

Look v2 (owner, 2026-10-02): bigger, more colourful, more detailed.
- Bigger: at the peak frame the effect covers about the given share of the frame, mostly through tall vertical shapes, not only flat ground rings; a short hold at the peak so it feels heavy.
- More colourful: the 2-3 hue palette given per sheet (core, body, accent), saturated mid-tones, value-graded edges, a coloured light spill on the ground. Bright cores stay below white: no blown-out white blobs.
- More detailed: show all five layers at the peak: anticipation (gather, runes), a solid core shape (mesh-like swirl, ring, slash, crystal, pillar), secondary particles (sparks, motes, petals, shards), a ground layer (decal, crack, scorch or rune circle) and an after-effect (motes, smoke, shimmer).
- Style: stylised hand-painted fantasy MMO effects with painterly, crisp shapes, readable at game distance.

## Sheet 1 of 7: `h02_hoarfrost_gale` Hoarfrost Gale (skill 1, damage + control)

What it is: A crescent-moon hex rides a frost gale; it blasts the first enemy and everything within 2.2 m back 1.5 m and Chills them.
- Palette: core #F4F7FF, body #A9C8FF, edge #6A5CFF, accent #FFD36E.
- Telegraph on the ground: an amber rectangle outline 1.5 m wide and 10 m long with small chevrons pointing away from the hero; then a single smooth amber ring of radius 2.2 m flashes at the impact point.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies in a line 4-8 m ahead.
- Peak coverage: about 18 % of the frame.
- Layers to show: anticipation: Two counter-rotating frost swirls on the staff crystal grow 0.4 → 1.0 m; 12 ice streaks converge; hoarfrost creeps up the staff. Core: the crescent hex sigil 1.6 m (a crescent moon cradling a snow crystal in a rune disc) wobbling ±6° at 9 Hz with a pale core; a frost release cone 200-320 ms. The broad crescent silhouette. Secondaries: 3 lilac → violet helix ribbons, shed frost streaks at 60/s, gold glints. Ground: A frost vortex decal r 0 → 2.6 m spinning 2.4 → 0.6 rad/s, a lilac frost-crack ring, and a dust ring under the caster at release. After-effect: A 2.5 m frost funnel twists up while 24 ice-glitter bits spiral up and settle as rime.
- Readability: Core alpha 0.85, rim 0.5; the funnel is thin and translucent, so pushed enemies stay visible.
- Frames:
  1. t=0.08s: Two small frost swirls start turning at the staff crystal; ice streaks converge; the 1.5 × 10 m amber lane shows ahead.
  2. t=0.18s: Anticipation peak: the swirls are 1 m wide, hoarfrost climbs the staff, a pale violet glow.
  3. t=0.26s: Release: the 1.6 m crescent-moon hex sigil bursts out of a frost cone; a dust ring under the witch.
  4. t=0.45s: Mid-flight: three lilac helix ribbons spiral around the sigil; frost streaks and gold glints trail behind.
  5. t=0.66s: Impact on the lead dummy: a broad frost flash, the 2.2 m amber ring flashes, dummies pushed back.
  6. t=0.85s: Peak hold: the frost vortex spins open to 2.6 m and a 2.5 m frost funnel twists up with ice glitter.
  7. t=1.40s: Dissipation: the funnel thins, the vortex slows, rime cracks glow lilac.
  8. t=2.00s: Aftermath: a faint rime decal and a few settling ice motes; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 2 of 7: `h02_rimeshard_nova` Rimeshard Nova (skill 2, control + damage)

What it is: Twelve hexagonal ice crystals erupt in a ring around her and knock nearby enemies up: her get-off-me button.
- Palette: core #F4F7FF, body #A9C8FF, edge #6A5CFF, accent #FFD36E.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 4 m.
- Stage: the hero silhouette left of centre, facing right into the frame; four dark dummies standing 2-4 m around the hero.
- Peak coverage: about 22 % of the frame.
- Layers to show: anticipation: The notched ring (crystal notches) draws clockwise at r 4.0 m; 16 frost motes spiral from the ring into the staff heel. Core: 12 hex crystals, 2.6 m tall, rise from -1.7 m with back-out over 110 ms at radii 2.9 / 3.5 m, staggered 8 ms clockwise, tilted out 10-22°; lilac fresnel rim, violet body; erode tip → base from 700 ms. Secondaries: Ice shards thrown out under gravity, snow-dust puffs at 45 %, and 4-6 gold star-threads arcing between neighbouring crystals. Ground: A 3.2 m ground flash, a shock ring and 0.6 m ring wall r 0.5 → 4.6 m, then a frost crack per crystal cooling lilac → indigo. After-effect: Low frost mist at 12 % drifting outward; falling ice glitter.
- Readability: Crystals stand on the 2.9-3.5 m perimeter; the witch and enemies inside stay visible.
- Frames:
  1. t=0.05s: The crystal-notched ring starts drawing clockwise at r 4 m; frost motes lift off it.
  2. t=0.15s: Ring complete; the motes spiral into the staff heel as she plants it.
  3. t=0.21s: Eruption: hexagonal ice crystals burst up around her in a clockwise wave; ground flash; dummies lifted.
  4. t=0.30s: Peak: twelve 2.6 m crystals tilted outward, a shock ring and low ring wall expanding, ice shards and snow puffs, gold star-threads between crystals.
  5. t=0.45s: Hold: crystals at full height, lilac frost cracks at every base, frost mist rolling outward.
  6. t=0.80s: The crystals start dissolving from the tips down with glowing edges.
  7. t=1.20s: Stumps dissolve, the mist thins, the cracks cool to indigo.
  8. t=1.80s: Aftermath: cooling cracks and a few ice motes; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 3 of 7: `h02_starless_hollow` Starless Hollow (skill 3, control + damage)

What it is: She tears a starless hole in the ground: a 4.5 m gravity well that drags enemies in for six beats and then implodes.
- Palette: core #FFF0FF, body #B07CFF, edge #5A1FD1, accent #5FF2D8, abyss #12052B.
- Telegraph on the ground: a single smooth amber ring (#FFBA4B band, dark #080C12 outer rim, faint warm fill) of radius 4.5 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 7 m ahead.
- Peak coverage: about 30 % of the frame.
- Layers to show: anticipation: The outer rune circle wipes in over 450 ms turning +10°/s; the inner heptagram (r 3.0 m) fades in turning -20°/s; 3 arcs crawl along the ring; rim motes rise 0.6 m. Core: Abyss disc (alpha-blended, not additive) r 0 → 4.2 m with back-out, spin 1.2 → 2.0 rad/s; an inverted depth funnel below the ground; a broken teal rim pulsing (width ×1.4, brightness ×2 for 120 ms) on each tick. Secondaries: 40 pull motes born at the rim spiral in and down; each tick sends an inward shock ring 4.5 → 1 m and a violet impact on every enemy. Ground: Implosion at 3050 ms: 8 radial arcs, an outward shock ring r 0 → 5 m and debris, then an abyss-violet scorch. After-effect: Embers and violet motes drift up while the scorch cools.
- Readability: The abyss is value-lifted to L* ≥ 25 under enemies and the violet light rims them; the broken teal rim never competes with the smooth amber band.
- Frames:
  1. t=0.20s: At the target point the outer rune circle wipes in (a third drawn); crackle arcs crawl along it.
  2. t=0.55s: Outer circle and inner heptagram complete and turning; rim motes rising; the witch's staff slams.
  3. t=0.75s: The hollow opens: a dark abyss disc spirals open inside a broken teal rim; dummies at the edge start sliding in.
  4. t=1.25s: A tick beat: the teal rim pulses wide, an inward shock ring, violet flashes on the dummies; pull motes spiral into the dark centre.
  5. t=1.95s: Peak sustain: dense irregular violet bands spin fast, depth reads below the ground, dummies dragged to the centre and lit violet.
  6. t=2.85s: Collapse: the core contracts to a point; the rim breaks up.
  7. t=3.10s: Implosion: 8 radial arcs and an outward shock ring to 5 m, debris flying.
  8. t=3.90s: Aftermath: a violet scorch with fading embers; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 4 of 7: `h02_star_lance` Sapphire Star Lance (skill 4, damage)

What it is: A heptagram opens before the staff and fires a faceted sapphire lance that pierces three enemies in a 16 m line.
- Palette: core #F2F8FF, body #4FA8FF, edge #6A4CFF, accent #FFD36E.
- Telegraph on the ground: an amber rectangle outline 1.2 m wide and 16 m long with small chevrons pointing away from the hero.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies in a line 4-12 m ahead.
- Peak coverage: about 16 % of the frame.
- Layers to show: anticipation: A vertical heptagram disc (1.4 m) unfolds in front of the staff crystal; 12 crystal motes converge; 3 gold four-point stars orbit the disc; sapphire light ramps 0 → 3. Core: A 2.6 m faceted sapphire spear with a star head and gold inlay, plus a 2-ribbon spiral. Secondaries: Shed crystal glitter, 3 thin sonic rings stamped along the path, star sparks at each pierce. Ground: A lilac frost streak along the lane and a star flash under each pierced enemy. After-effect: The heptagram erodes away; sapphire motes hang along the lane.
- Frames:
  1. t=0.15s: A vertical heptagram rune disc unfolds in front of the staff crystal; crystal motes converge; the 1.2 × 16 m lane shows.
  2. t=0.42s: The disc spins at full size, three gold four-point stars orbit it, sapphire light at its brightest.
  3. t=0.50s: Release: a faceted 2.6 m sapphire lance with a star-shaped head shoots through the disc; a sonic ring at the muzzle.
  4. t=0.62s: The lance pierces the first dummy: star-spark burst; a frost streak glows along the lane.
  5. t=0.72s: It pierces the second and third dummies; three thin sonic rings stand along the path; crystal glitter sheds.
  6. t=0.95s: The lance fades at the end of its 16 m; the lane streak glows.
  7. t=1.30s: The heptagram dissolves with noise erosion; sapphire motes hang along the line.
  8. t=1.80s: Aftermath: a faint frost streak and a few motes; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 5 of 7: `h02_moonveil_ward` Moonveil Ward (skill 5, buff)

What it is: A faceted moon-crystal dome shields one ally (or herself) for 40 damage over 5 s; when it breaks or ends it pulses frost 3 m.
- Palette: core #F4F7FF, body #A9C8FF, edge #8A5CFF, accent #FFD36E.
- Telegraph on the ground: four dashed pale-mint corner brackets (#DFFFF0) at the ally's feet; then a single smooth amber ring of radius 3 m flashes at the ally when the pulse fires.
- Stage: the hero silhouette left of centre, facing right into the frame; one light-grey ally silhouette 5 m ahead, two dark dummies attacking it.
- Peak coverage: about 12 % of the frame.
- Layers to show: anticipation: Two crescent moons orbit in from 2 m and lock above the ally; the aegis star-plate glyph flickers on. Core: A geodesic hex-crystal dome r 1.2 m, alpha 0.35 body / 0.7 rim, scrolling star sparkle; each absorbed hit flashes the struck facet gold. Secondaries: 3 orbiting diamond crystals and gold four-point glints on the facets. Ground: A moon-phase heptagram r 1.2 m under the ally. After-effect: On break or expiry the dome shatters into hex shards, a frost pulse ring races to 3 m, and a rime decal spreads.
- Readability: Dome alpha caps keep the ally's silhouette and HP plate visible; a refresh replaces the old dome, so there is never a double dome.
- Frames:
  1. t=0.10s: Two crescent moons orbit in toward the light-grey ally silhouette; dashed brackets at the ally's feet.
  2. t=0.28s: The crescents lock above the ally's head; a star-plate glyph flickers on.
  3. t=0.35s: A faceted hex-crystal dome forms around the ally (low alpha, bright rim); a moon-phase circle on the ground.
  4. t=0.60s: Sustain: three diamond crystals orbit the dome with gold glints; the ally is clearly visible inside.
  5. t=1.20s: A dummy strikes the dome: one facet flashes gold.
  6. t=2.00s: Break: the dome shatters into hex shards and a frost pulse ring races out to 3 m (amber ring flash); dummies frosted.
  7. t=2.30s: A rime decal spreads; shards fall and melt.
  8. t=2.90s: Aftermath: fading rime and motes; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 6 of 7: `h02_celestial_orrery` Celestial Orrery (skill 6, ultimate + control)

What it is: She conjures a sky orrery over a 7 m field: three gold rings and seven crystal moons orbit and sweep beams that Chill and Anchor, then collapse into a star-nova.
- Palette: core #FFF4FF, body #B07CFF, edge #5A1FD1, accent #FFD36E, rim #5FF2D8.
- Telegraph on the ground: a DOUBLE vermilion ring (#FF4F3A) with 8 inward-pointing teeth and a diagonal hatch fill, radius 7 m.
- Stage: the hero silhouette left of centre, facing right into the frame; three dark dummies inside the area 8 m ahead.
- Peak coverage: about 45 % of the frame.
- Layers to show: anticipation: The 7 m outer rune circle (gold-violet) and inner heptagram wipe in; 3 gold orbit rings assemble 4-6 m above the field; starfield motes rise from the ground. Core: 7 crystal moons (0.6 m) ride the tilted, precessing rings, each casting a thin value-graded beam (0.3 m) that sweeps the ground. Secondaries: Comet trails behind the moons, violet arcs linking the rings, falling star glints. Ground: Turning circles and beam scorch dots; at 3300 ms the star-nova: an 8 m star flash, a shock ring r 0 → 7.5 m and a violet-gold star scorch. After-effect: The rings erode away; star motes fall slowly; teal rim motes.
- Readability: Rings and moons sit 4-6 m up, above every head; beams are thin; the toothed HEAVY band draws above every layer.
- Frames:
  1. t=0.30s: At the target the 7 m outer rune circle and the double toothed vermilion ring draw in; starfield motes rise.
  2. t=0.80s: Three gold rings assemble 4-6 m above the field; seven crystal moons appear on them.
  3. t=1.20s: The orrery turns: moons orbit, thin beams sweep the ground, the heptagram turns; dummies frosted.
  4. t=1.90s: Peak: rings tilted and precessing, comet trails behind the moons, violet arcs between rings, the field lit violet.
  5. t=2.60s: Sustain: the beams converge toward the centre; the rings tighten.
  6. t=3.30s: Star-nova: a bright (never white) violet-gold starburst 8 m wide, a shock ring racing out, dummies knocked up.
  7. t=3.80s: The rings dissolve with erosion; star motes fall; the star scorch glows.
  8. t=4.50s: Aftermath: the scorch and the last motes; nearly empty.
- Variants: 3 separate generations of this same brief.

## Sheet 7 of 7: `h02_basic` Starmote Bolts (basic attack, damage)

What it is: Two quick bolts from the staff crystal: a spinning four-point star mote, then a small crescent.
- Palette: core #FFF0FF, body #B07CFF, edge #5A1FD1, accent #FFD36E.
- Telegraph on the ground: none on the ground (basic attack); you may show thin amber corner brackets under the target dummy.
- Stage: the hero silhouette left of centre, facing right into the frame; one dark dummy 8 m ahead.
- Peak coverage: about 3 % of the frame.
- Layers to show: anticipation: A gold four-point glint swells on the staff crystal; 4 motes converge. Core: Link 1: a spinning four-point crystal star (0.45 m) with a short violet ribbon. Link 2: a small 60° crescent bolt (0.6 m). Secondaries: 8 sparkle motes shed along the path, gold accent. Ground: A 0.8 m star flash under the target. After-effect: 6 glitter motes fade.
- Frames:
  1. t=0.05s: A gold four-point glint swells on the staff crystal.
  2. t=0.10s: Release: a spinning star-crystal mote leaves the crystal with a short violet ribbon.
  3. t=0.25s: The star mote mid-flight, shedding gold sparkles.
  4. t=0.38s: Impact on the dummy: a small violet-gold star flash and 6 sparks.
  5. t=0.45s: Link 2 wind-up: the crystal glints, a small crescent forms.
  6. t=0.50s: The crescent bolt leaves the staff.
  7. t=0.65s: Crescent impact: flash and glitter.
  8. t=0.95s: The last glitter fades; empty.
- Variants: 1 (basic attack).

Deliver `skills_02_witch_keyframes_v1.zip`: 19 PNG at 2400×1350 named `<skill_id>_v<n>.png`, plus README.md (per sheet: the prompt used, the palette hex values and the checklist results) and receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per sheet in the README):
- 8 frames in a 4 × 2 grid, each labelled with its time, one camera;
- anticipation → peak → dissipation reads at a 25 % thumbnail;
- the palette hues match the sheet; colourful mid-tones; no white-clipped blobs;
- the hero and every dummy or ally stay readable in every frame (check in greyscale);
- the telegraph shape and size are as specified and visible in the wind-up frames;
- all five layers are visible in the peak frame;
- original; only the allowed text.

Originality: original Xexoria effects. Not World of Warcraft, Genshin Impact, Ragnarok, Lumivara, League of Legends, Final Fantasy XIV, Diablo or any other game's spells, icons or UI; no logos; no recognisable characters. The hero is only a grey silhouette: do not redesign them.
