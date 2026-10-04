# City art program — R5 production plan ("like the image")

This is the long-lived art and tech-art plan for turning the reference sheet
`docs/ui/city-layout-target-20260928.png` into a playable, game-quality sky
city. The user's wording ("AAA", "a 1,000-person team", "a budget of millions")
is treated as the **quality bar and production discipline**, not as a claim
that the project has that team or permission to spend money. Spending stays
**0 THB** unless the user authorizes a specific paid item (see §10).

## 1. Why a new plan: user feedback on 2026-09-28

- R4 "does not look like the image at all". The town is **too small**. It
  needs **more detail, closer to the image**, and **landmarks in the image's
  positions**.
- Textures do not match. The user asked for **sharpness, marks, and small
  details, like an expert 3D modeler's work**, plus **shadows**.
- The user's score for the previous city was **10/100**. Scores are only
  changed by the user.

Root causes found in R4 (script and in-game review):

| Gap | R4 cause | R5 fix |
|---|---|---|
| Wrong composition | 22 small identical rowhouses in concentric rings, a crenellated wall around everything | The reference is a **diorama of ~10 large landmark buildings** among gardens, water, trees and terraces. Build that. |
| Too small | 154 × 141 m island, 13 m paved plaza, 5–6 m houses | **240 × 288 m island**, 84 m plaza, landmark sizes measured from the top map (§3) |
| Primitive shapes | Unbevelled boxes, cones and icospheres | Shaped geometry: bevels on every hard edge, profiles, overhangs, jetties, dormers, tracery, weighted normals |
| Wrong textures | Photographic 1K CC0 scans on chunky shapes look muddy and do not match the painted stylized sheet | **Texture foundry**: procedurally authored stylized PBR sets modelled on the sheet's "Materials & Textures" panel, with chips, cracks, stains, moss and crevice shadow in the maps |
| No contact shadow or wear | No AO, uniform albedo, no edge wear | Vertex-colour AO + cavity dirt + edge highlights on every mesh; AO atlas for ground; real-time cascaded sun shadows |
| Flat lighting | Hemispheric light + one 1K shadow map, no IBL | IBL environment, cascaded shadows, ACES tone mapping, bloom on magic, SSAO on High |
| Lifeless | Static scene | Water, waterfalls, fountain spray, portal column, rotating rune rings, windmill, smoke, forge fire, banners, birds, airship |

## 2. What makes the reference look the way it does

1. **Composition.** A rounded-rectangle floating island. The Town Gate and
   three waterfalls are on the south edge. A central canal runs north to a
   huge radial plaza. The fountain and statue sit at the centre, with the
   blue portal to its east. The Magic Castle is raised on a terrace at the
   north, with grand stairs. The wizard tower is north-west and the windmill
   north-east. Blacksmith, guild hall and tavern are west and south-west.
   Market stalls and the potion shop are east and south-east. Tree belts and
   water gardens fill the edges.
2. **Shape language.** Large, readable silhouettes. Tall thin conical spires
   with gold finials. Steep blue roofs with dormers and cross-gables. Jettied
   timber upper floors. Chunky stone bases. Every roof and tower is capped by
   an ornament.
3. **Materials, hand-painted PBR.** Warm cream limestone blocks with chipped
   bevels. Saturated royal-blue slate. Dark timber, cream plaster, mossy stone
   caps and light radial flagstones. Glowing blue and purple rune circles.
   Blue banners with a gold crest. Colour variation between neighbouring
   stones, with darker joints and brighter worn edges.
4. **Lighting.** Warm late-morning key light, a cool sky fill, and strong
   ambient occlusion in every crevice and at every contact. Soft sun shadows.
   Emissive accents (crystals, portal, windows, forge) bloom.
5. **Density of story details.** Lamps, planters, benches, crates, barrels,
   sacks, signs, banners, awnings, notice boards, carts, fences, flowers, ivy,
   birds and people. No bare surface is left undressed.
6. **Atmosphere.** A sea of clouds below, floating rocks with trees, an
   airship, and soft aerial perspective.

## 3. Scale and positions (the layout contract)

All positions live in **`assets/blender/city_r5/layout.json`**. The Blender
builder, the runtime VFX anchors and, later, collision and navigation read
that one file. To move a building, edit the JSON and rebuild. Positions were
measured on a metric grid laid over the reference TOP VIEW (0.28 m per pixel
at 3×). The origin is the fountain; +Y is north, toward the castle.

| Landmark | Centre (x, y) m | Level | Size | Faces |
|---|---|---|---|---|
| Island | x −120…120, y −160…128 | cliff 75 m deep | 240 × 288 m | — |
| Plaza + fountain | (0, 0) | 0 | plaza r 42 m, basin r 11.5 m, statue top about 13 m, crystal at 17 m | — |
| Portal | (40, 10) | 0 | dais r 8.5 m | — |
| Magic Castle | (0, 96) | +9 | 64 × 36 m, main spire tip about 72 m | south |
| Grand stairs | (0, 42) → (0, 78) | 0 → +9 | 16 m wide, 3 flights | — |
| Wizard Tower | (−65, 88) | +6 | base r 8 m, 62 m + spire, rune rings r 13/11 m | — |
| Windmill | (94, 108) | +8 | r 6 m, 17 m, sails r 12 m | plaza |
| Blacksmith / Armor | (−72, −18) | +0.3 | 26 × 20 m, 2 storeys | plaza |
| Armory house | (−30, 54) | 0 | 16 × 12 m | plaza |
| Guild Hall | (−90, −56) | 0 | 30 × 22 m, 3 storeys | plaza |
| Tavern | (−58, −88) | 0 | 20 × 16 m | north-east |
| Market stalls | rows at y −8 and −34, x 50…84 | 0 | 8 stalls | — |
| Potion Shop | (98, −62) | 0 | 16 × 14 m | north-west |
| Canal | x 0, y −46 → −148 | water −1.0 | 12 m wide | — |
| Canal Bridge / Ring Bridge | (0, −74) / (0, −112) | 0 | 20 × 10 m / 18 × 8 m | — |
| Town Gate + 3 waterfalls | gate (0, −152); falls x −48, 0, +49 | −0.5 | 30 m front | south |

## 4. Studio structure (how "1,000 people" maps to this project)

Work is split into departments with one owner each. The PM is the art lead
and integrator: layout, shared library, reviews and final assembly. Parallel
workers own separate files and never edit another department's modules.

| # | Department | Owns | Key deliverables |
|---|---|---|---|
| D1 | Art direction | `docs/city-art-roadmap.md` §2, §5 | Style rules, palette, review scoring, matched reference crops |
| D2 | Layout / level design | `layout.json` | Positions, levels, paths, sightlines, camera presets |
| D3 | Terrain, island & water | `kits/terrain.py` | Floating island sculpt, cliffs, terraces, retaining walls, canal, pools, waterfalls |
| D4 | Architecture kit | `kits/buildings.py` | Timber/stone building generator, blacksmith, guild hall, tavern, potion shop, houses, gazebo |
| D5 | Hero landmarks | `kits/landmarks.py` | Magic castle, wizard tower, windmill, fountain + statue, portal, gate, bridges, arcades |
| D6 | Props & dressing | `kits/props.py` | Lamps, banners, stalls, crates, barrels, sacks, planters, benches, boards, fences, anvils, racks, carts, potion shelves |
| D7 | Vegetation | `kits/vegetation.py` | Round oak, pine, blossom, autumn trees; bushes; flowers; potted plants; ivy (alpha cards + spherical normals) |
| D8 | Materials (texture foundry) | `foundry/` | Stylized PBR sets (albedo, normal, ORM) with micro detail; emblem, rune, cloth and leaf atlases |
| D9 | Lighting & rendering | `apps/client/src/city-render.ts` | IBL, cascaded shadows, post-process, quality presets |
| D10 | VFX & animation | `apps/client/src/city-fx.ts` | Water, waterfalls, spray, portal, rings, windmill, smoke, fire, banners, birds, clouds, airship |
| D11 | Tech art & performance | `build_city_r5.py`, `build-city-asset.mjs` | Merge-by-material, LOD/HLOD, KTX2, budgets, receipts |
| D12 | QA & review | `assets/models/reference-city/r5/review/` | Matched shots (hero, front, back, left, right, top, plaza, gate) beside reference crops; performance and regression logs |

## 5. Quality bar ("expert 3D model" checklist)

Every asset must pass this checklist before integration.

- **Sharpness.** Every visible hard edge is chamfered: 2+ segments, harden
  normals. No faceted curved surface: lathe profiles use ≥ 24 segments on hero
  pieces. Textures are authored at ≥ 400 px/m on walls and roofs and are never
  upscaled. Runtime uses mipmaps, anisotropic filtering and native pixel
  ratio on desktop.
- **Marks and micro detail in the maps.** Chipped stone corners, hairline
  cracks, mortar erosion, water stains, lichen and moss in crevices. Wood
  grain, knots, nail heads and scratches. Slate tiles with individual rotation,
  chipped corners and moss patches. Plaster with trowel marks and hairline
  cracks. No two neighbouring tiles share a colour.
- **Shadows.** Crevice AO in every texture. Vertex-colour cavity and contact
  darkening on every mesh. Baked AO where objects meet the ground. Real-time
  sun shadows at runtime.
- **Construction logic.** Buildings have foundations, a plinth course,
  corner posts, beams that meet, window frames with sills, shutters and
  lintels, doors with frames and hinges, eaves with rafters, ridge caps,
  gutters or drip edges, chimney caps, and roof ornaments.
- **No clones.** Repeated kit parts vary in size, tint, wear, props and
  roof ornament. Landmark buildings are unique.
- **Silhouette check.** Every landmark is recognizable as a black silhouette
  from the hero camera.
- **Budget check.** Triangles, materials, textures and memory are recorded
  per asset (§9).

## 6. Pipeline

```
foundry/*.py (numpy)        -> r5/textures/*_{albedo,normal,orm}.png   (tileable stylized PBR)
kits/*.py (Blender, citykit) -> per-kit review sheets in r5/review/
build_city_r5.py            -> reads layout.json, assembles kits, vertex AO/cavity/edge,
                               AO atlas (UV1) for ground, merge by material,
                               keeps anim_/fx_/emit_/light_ nodes, review renders,
                               r5/city-source.glb + manifest
build-city-asset.mjs        -> KTX2 (ETC1S colour, UASTC normal/ORM) + Meshopt -> runtime GLB
client city-render/city-fx  -> IBL, CSM, post, water, VFX bound to hook nodes
```

- **Texture foundry.** It builds a periodic height field (bricks, flagstones,
  shingles, planks, cobbles, strata), then derives normal, AO, curvature,
  crevice and edge masks from it. Albedo is painted from per-element palettes
  plus grime, stains, moss and chips. Roughness and metallic come from the
  same masks. The foundry is original, reproducible, tileable, and needs no
  licence.
- **UV rules.** Walls and ground use world box projection. Roofs use a planar
  projection aligned to the eave. Beams and planks use grain-aligned
  projection. Cloth and emblems use 0–1 panels. All kits get their material
  tile sizes from `citykit.MATERIALS`, for consistent texel density.
- **Vertex colour (COLOR_0).** Holds AO bake, cavity darkening, edge
  highlights, ground-contact fade and per-object tint jitter. Babylon
  multiplies it over the base colour.
- **Runtime hooks.** Anything named `anim_*`, `fx_*`, `emit_*` or `light_*`
  is exported as a separate node for the client to animate or attach effects
  to. Everything else is merged by material.

## 7. Runtime rendering plan (client)

- Environment IBL for PBR reflections and ambient. The warm sun uses a
  `CascadedShadowGenerator` (3–4 cascades, PCF) sized to the city.
- `DefaultRenderingPipeline`: ACES tone mapping, bloom on emissive magic,
  FXAA/MSAA, light sharpen, vignette. SSAO2 on the High preset only.
- Sky: gradient sky with cloud billboards, a cloud sea below the island,
  floating rock islets, and a slow airship path.
- Water: scrolling normal-map surfaces, waterfall ribbons with scrolling foam
  and mist particles, fountain jets, and pool caustic sparkle.
- Animation: windmill sails, wizard rune rings, bobbing crystals, the portal
  disc and light column, waving banners, forge fire flicker, and smoke from
  the blacksmith and potion shop chimneys.
- The development-only `?cityOverview=1` presets must reproduce the review
  cameras in `layout.json` so in-game shots can be compared with the
  reference and with Blender renders.

## 8. Phases and gates

Each phase ends with matched review shots (hero, top, plaza, gate; in Blender
and in-game) placed beside reference crops, recorded budgets, and the user's
score. A phase is not complete until the user has seen it.

| Phase | Scope | Gate |
|---|---|---|
| **R5a** | Layout contract, shared library, texture foundry v1 (all core materials), island/terraces/canal/waterfalls, plaza + fountain + portal blockout at the new scale | Top view matches the reference map; texture sheet reviewed against the reference material panel |
| **R5b** | Architecture kit v1 and the 4 signature shops (blacksmith, guild hall, tavern, potion shop), market stalls | Key Buildings panel comparison per building |
| **R5c** | Castle, wizard tower, windmill, gate, bridges, arcades, fountain statue | Silhouette test from the hero camera |
| **R5d** | Vegetation and props dressing pass | Props & Trees panel comparison; hero-view density |
| **R6** | Runtime lighting, post-processing, water and VFX, sky, clouds, floating rocks, airship | In-game hero and plaza shots; FPS on this PC |
| **R7** | Decals (cracks, moss, stains, puddles), light pools, colour grading, story props | Street-level plaza review |
| **R8** | LOD/HLOD, KTX2 budgets, streaming, phone presets | Budgets in §9 on one Android and one iPhone |
| **R9** | Gameplay integration: city zone, collision/navmesh from layout, NPC spots, transitions | Walk the gate → plaza → castle route online |

## 9. Budgets

| Preset | Visible triangles | Draw calls | Compressed textures (GPU) | Shadows |
|---|---|---|---|---|
| High (desktop) | ≤ 900k | ≤ 180 | ≤ 160 MB | CSM 4×2048 + SSAO |
| Medium | ≤ 350k | ≤ 110 | ≤ 110 MB | CSM 3×1024 |
| Low (phone) | ≤ 150k via LOD/HLOD | ≤ 80 | ≤ 64 MB | 1 cascade or baked only |

These replace the single V5 §14 figure for the city scene only, because the
city is a separate hub zone. The meadow keeps its budget and sees the city
through a low-poly HLOD.

## 10. Money (0 THB by default)

No paid step is taken without a specific user authorization. If the user
later wants to buy speed, these are the useful options, each needing
explicit approval of the item and price:

1. A commercial stylized fantasy-town kit whose licence covers browser games.
2. A commissioned artist for the statue, emblem and hero textures.
3. Paid AI 3D generation for props, cleaned and retopologized afterwards.

## 11. Risks

- Procedural modeling can reach a strong stylized look, but the painted
  concept will not be matched pixel-for-pixel. We track it with the user's
  score, not with claims.
- Phone memory and fill rate: foliage cards, bloom and shadows need presets
  (R8).
- The city is a visual hub until R9. Collision, navigation and server zones
  are separate deliverables.
- The pink blob creature in the reference resembles a protected mascot. It
  is excluded; the emblem, statue and names are original.

## 12. History

- R1–R3: Blender blockout → textured kit (134k triangles, 4.7 MB). R3 fixed
  an invalid cliff face. Evidence: `planning/evidence/e08-city-visual-r3.json`.
- R4: layout from the current sheet, CC0 Poly Haven scans, KTX2 + Meshopt
  (129k triangles, 16.6 MB runtime GLB). User feedback: too small, wrong
  textures, not like the image. R4 files are kept unchanged in
  `assets/models/reference-city/r4/` and `build_reference_city_r4.py`.
- R5: this plan. The builder is `assets/blender/city_r5/`, outputs go to
  `assets/models/reference-city/r5/`, and the runtime switches only after
  review and validation pass.
