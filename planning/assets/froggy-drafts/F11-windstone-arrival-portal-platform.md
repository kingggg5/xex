[Claude -> froggy | 2026-10-02 | F11]

TASK F11: Windstone arrival portal platform and portal-ring states (CONCEPT, 16:9, 3 variants)

Attach before sending:
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`;
- the picked F09 windstone variant once it exists (the ring stones here must be the same stones);
- the picked F10 Rimecrest variant once it exists (the platform must sit in that world).

What this is for: our builders model this platform in Blender from your image (it is NOT a Tripo job), so we need a clear construction reference. The same design is used twice:
- in Rimecrest as `windstone_arrival` / `windstone_return`, where players arrive from Sunmeadow and leave again (snow-covered);
- in Sunmeadow at the centre of the Windstone Circle as the portal ring `warp_windstone_portal` (meadow version, no snow), which wakes up after Galehorn is defeated.

PART 1 (now): Stage A, 3 variants of the Rimecrest arrival platform

Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), with the Xexoria look target attached. Keep the design clean for 3D generation: clear shapes, clear light and shadow, an uncluttered background, nothing too dark. Make 3 variants as separate generations of this same brief.

The platform:
- A round carved stone dais, 5.0 m across, rising only 0.3 m above the ground in two very low steps (a player walks onto it; it must look walkable from every side, no railings).
- Its top surface carries a carved portal ring: a circular channel 4.0 m across, with an inner ring of wind-spiral glyphs and four short spokes pointing outward. Channels are wide (at least 6 cm) and hold a faint cyan light (#72D5DE, deep #1D95A9) that never clips to white.
- Three standing stones of the Sunmeadow windstone design (rounded wind-carved sandstone slabs 2.2-2.8 m tall, a spiral glyph, a carved tie band with a faded blue/cream cloth streamer) stand just outside the dais at 120-degree spacing, leaning very slightly outward. The gaps between them are wide (at least 3 m), so the platform reads as open.
- Rimecrest version: snow on all upward surfaces, drifted against the stones and the step risers, packed and darker where feet walk across the dais, a little rime on the glyph edges. The cyan inlay glows softly through a thin layer of frost.
- Materials: warm sandstone #C1BCA4 / #EAE3CD with blue-grey base course stones #8A93A8 around the outer step; moss only at the very base, mostly hidden by snow; cloth #4F7BB0 and #FFF6DC.
- A 1.8 m adventurer stands on the platform for scale (simple figure, back three-quarter view).

Framing: the player camera, about 13 m away and 22 degrees above the horizon, so the whole platform, the three stones and a few metres of snowy ground around it are visible. Plain, calm surroundings: a soft snowy slope and a hint of distant mountains, nothing else.

Light: low winter sun, warm key from the upper left, soft blue fill; long soft shadows. Not dark, not foggy.

Variants: A = glyph ring with four spokes (as described); B = a double ring with a spiral centre medallion; C = a ring split into six arc segments with gaps (still one clear circle).

Label the image "CONCEPT" in a small corner tag; no other text.

Avoid: tall arches, gates or doorframes (it is a ground ring, not a doorway), floating crystals, thin metal filigree, chains, steep steps, fog, bloom, a ring of flames, a sci-fi teleporter look; anything from World of Warcraft, Blizzard, Genshin (no Teleport Waypoint look-alike), Ragnarok (no warp portal look-alike) or Lumivara.

PART 2 (only after Claude picks a variant): portal-ring state sheet, Sunmeadow version

One 16:9 image (2048x1152), three panels side by side, same camera and the same picked design, but in the Sunmeadow meadow (grass and flowers, no snow), labelled DORMANT, AWAKENING and ACTIVE in small tags:
1. DORMANT (before Galehorn is beaten): the channels are plain carved stone with only a faint cyan line at night; daylight shows no glow.
2. AWAKENING (Galehorn engaged nearby): the glyph ring glows soft cyan, a few wind motes rise, the cloth streamers lift.
3. ACTIVE (after the first defeat): the whole ring glows steadily (never white), a gentle swirl of wind and light rises about 2 m above the centre, and a thin bright ground ring marks the trigger edge.

Deliver `props_windstone_arrival_platform_v1.zip`: the 3 variants (Part 1) and later the state sheet (Part 2) as PNG, README.md (dimensions in metres, materials, how each state differs, checklist results), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (PASS/FAIL per variant in the README):
- in greyscale at a 160 px thumbnail the platform reads as one flat round landmark with three stones;
- the dais is clearly walkable: low steps, no railings, no obstacles on its surface;
- channels and glyphs are wide and simple enough to model (no hairline detail);
- snow sits on top faces and drifts against stones; no pure white; glow never clips;
- original; only the CONCEPT and state tags as text.
