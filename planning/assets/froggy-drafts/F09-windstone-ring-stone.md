[Claude -> froggy | 2026-10-02 | F09]

TASK F09: Windstone ring stone, reference sheet for a Tripo-route hero prop (CONCEPT)

Attach before sending:
- the look target: `docs/ui/xexoria-town-art-target-20261001.png`;
- your picked Windstone Circle arena key art from F8, once Claude has chosen it (so the stones match the arena).

Why this asset matters: six of these stones ring the Galehorn boss arena in Sunmeadow, two more replace the gate posts, and scaled-down copies become the three quest windmarks. It is also the shared stone language of the warp network: the same carved stones mark the arrival ring in Rimecrest. One master shape, reused about 11 times, so it must be excellent and buildable.

PART 1 (now): Stage A, 3 variants

Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), with the Xexoria look target attached. Keep the design clean for 3D generation: clear shapes, clear light and shadow, an uncluttered background, nothing too dark. Make 3 variants as separate generations of this same brief; vary the silhouette, not the material language.

Subject: ONE standing stone of the Windstone Circle, an ancient ring of wind-carved monoliths around a boss altar in a sunny meadow glade.
- Size: 4.2 m tall, about 1.4 m wide and 0.9 m deep. A plain 1.8 m human silhouette (flat mid-grey #8A8A8A, no weapon) stands beside it on the same ground line for scale.
- Form: a thick, slightly tapered slab of warm sandstone. The wind has rounded its windward edge and scooped two or three shallow hollows into one face. One chipped top corner. Flat-ish base sunk into the turf (no visible underside). Strong, simple, chunky silhouette with bevelled readable edges: it must read at 13 m and as a dark shape in greyscale.
- Carving: one carved wind-spiral glyph on the front face (wide grooves, at least 6 cm wide and deep), plus a carved horizontal band near the top where cloth streamers are tied. The grooves hold a faint cyan glow (#72D5DE, deep #1D95A9) that never clips to white. Design the glyph yourself: an original spiral of wind lines. No runes from real alphabets, no logos.
- Moss: soft painted moss on the shaded lower third and in the hollows (#6F9C4B, light #8FBB6F, shadow #2F6B3E).
- Cloth: show one faded blue and cream cloth streamer (#4F7BB0, #FFF6DC) tied in the top band and lifting in the wind. Keep it clearly a separate strip in front of the stone; it will be modelled separately.
- Palette: sandstone #C1BCA4, warm light #EAE3CD, shadow stone #98937F, grooves #72D5DE / #1D95A9, moss as above, cloth as above.

Style: stylised hand-painted, Warcraft-like readability (not Warcraft content). The style lives in the painted albedo: a large top-light gradient, painted occlusion in the grooves and hollows, crisp edge highlights on the bevels, gentle hue variation (warm tops, cooler undersides). Warm sun key from the upper left, soft blue sky fill.

Framing: three-quarter front view at a slight high angle (like a player camera 13 m away and about 22 degrees above the horizon, but closer). The stone fills about 75 % of the image height with clear margins. Background: a soft, plain, light warm-grey gradient with a small patch of meadow turf under the stone only. No other props, no ring of stones, no environment.

Label the image "CONCEPT" in a small corner tag. No other text.

What makes it fail (avoid):
- a thin or spiky stone, pierced holes, arches or floating pieces (Tripo cannot build them);
- hair-thin cracks or noisy micro-detail; fine wear belongs in the paint;
- a photographic rock texture, dark or moody lighting, fog, bloom, depth of field;
- Stonehenge or any real monument copied; anything from World of Warcraft, Blizzard, Genshin, Ragnarok or Lumivara (no runestone or obelisk look-alikes from those games).

Variant guidance: A = upright slab with a rounded crown; B = a slab leaning about 8 degrees with a stepped shoulder; C = a slab with a deep notch near the top where the cloth band sits.

PART 2 (only after Claude picks a variant): Stage B, F6 turnaround

Use TASK F6 rules exactly, for the picked variant only:
- front, back, left and right as 4 separate PNGs, each 2048x2048, plus one lit 3/4 hero view;
- orthographic, camera at mid-height, pure white #FFFFFF background, neutral flat light, no cast shadows;
- the stone about 80 % of the frame height, base on the same baseline in every view, same scale;
- draw it WITHOUT the cloth streamer (cloth is modelled separately); keep the carved tie band;
- every groove at least 3 % of the image width;
- palette.png with the hex values above.

Deliver `props_windstone_ring_stone_v1.zip`: front.png, back.png, left.png, right.png, hero34.png, palette.png, README.md (size in metres, materials, any asymmetry: the glyph is on the front face only), receipt.json (file list, pixel sizes, palette hex values, licence note "generated for Xexoria").

Checklist (state PASS/FAIL for each in the README):
- the stone reads as one chunky shape in greyscale at a 64 px thumbnail;
- light and shadow are clear; nothing too dark (no large area darker than about 15 % brightness);
- grooves are wide enough to survive meshing (at least 3 % of the image width in the turnaround);
- the 4 views agree: same height, same baseline, left is the mirror outline of right, back is the mirror outline of front;
- original design; no text other than the CONCEPT tag.
