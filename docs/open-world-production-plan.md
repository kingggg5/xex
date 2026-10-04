# Open-World Production Plan — big map, dense detail, AAA-looking models in a browser

Status: proposed production roadmap · Written 2026-09-29 · Reconciled 2026-09-30

This is the T-WORLD track of [mmo-master-plan-2027.md](mmo-master-plan-2027.md) in full. It answers three questions:
how big the world actually gets, how it holds detail without dying on a phone, and how one person produces models
that read as AAA. Pipeline mechanics stay in [delivery-and-asset-playbook.md](delivery-and-asset-playbook.md); the
city programme stays in [city-art-roadmap.md](city-art-roadmap.md); the scale gates stay in
[world-expansion-500.md](world-expansion-500.md).

## 1. What "AAA" can and cannot mean on this target

A browser page, 12 MB to first play, WebGL2 on the low tier, 30 fps on a mid Android, one developer, 0 THB of paid
assets. Under those constraints the following **is** reachable, and is what modern stylized releases actually do:

- strong art direction with a fixed palette and one lighting model, read at gameplay distance;
- silhouette-first models with detail in textures, not triangles;
- baked lighting and AO, so the runtime pays for almost no shadow work on low tiers;
- trim sheets and atlases, so a whole district runs on a handful of materials;
- instanced density: thousands of visible objects from dozens of unique meshes;
- landmark composition that makes a 1 km world feel authored rather than tiled.

What is **not** reachable, and must not appear in any plan: virtualized geometry (Nanite-class), realtime global
illumination, 4K texture sets per asset, film-density foliage, per-object unique materials, or photoscanned kits at
browser download sizes. Anything that needs those is cut at the design stage, not discovered at the budget gate.

## 2. World size — staged, each stage gated

| Stage | Size | Walkable content | Unlocks after |
|---|---|---|---|
| **W1** target | 1,024 x 1,024 m (1.048576 km²) | Aetherhold + 3 regions | M1.3 AOI, collision and perimeter on every cell |
| **W2** proposed | 1,792 x 1,792 m (3.211264 km²) | +3 regions, one dungeon valley | W1 holds 250 players and the streaming budget; 500-player gate remains required |
| **W3** | 2,560 x 2,560 m (6.55 km²) | +mountain pass, coast, second town | W2 holds 500 players, art cadence proven for two quarters |

The rule from [world-expansion-500.md](world-expansion-500.md) stands and is the reason this is staged: the server
clamp does not move until land, collision, navigation and a perimeter cover every walkable cell. A bigger empty box
is not a bigger world, and it costs the same streaming work to maintain.

Separate authoring, streaming and simulation partitions:

- **512 m proxy ring** — always resident silhouette of everything beyond the horizon, ~8k triangles total per ring.
- **256 m macro sector** — authoring and HLOD unit; ≤25k triangles and ≤8 material groups, with atlasing preferred.
- **64 m detail cell** — streaming unit, 9-cell neighbourhood resident, ≤40k triangles and ≤2 MiB each.
- **32 m server AOI cell** — simulation only, independent of art, set in M1.3.

Morton order is an optional manifest-locality convention; it does not guarantee CDN placement or cache hits.
W2 is grid-aligned to seven 256 m sectors and twenty-eight 64 m cells per side. Expansion remains proposed;
the currently authored runtime still uses ±308 m and two southbound cells.

## 3. Terrain: one master, cut into cells

Authoring cells by hand does not scale and produces seams. The terrain comes from one source per sector:

1. A 16-bit heightmap per 256 m sector (2049 px, 8 px/m), sculpted in Blender or painted, kept in `content/source`.
2. A splat map (RGBA = four ground materials) at the same resolution.
3. Resample the render mesh before cutting into sixteen 64 m cells. A direct 2049² source cut gives
   512² × 2 = 524,288 terrain triangles per cell. Begin with 48×48 render quads per cell (4,608 triangles),
   preserve shared seam samples and normals, then select denser landmark patches only within the scene budget.
   The high-resolution source remains available for baking and height queries; it is not shipped as dense geometry.
4. The same heightmap generates the collision heightfield and feeds the navmesh bake — one source, three outputs, so
   they cannot disagree.

Terrain material budget: 4 ground layers per sector, one shared atlas, height-blended at transitions.

## 4. Density: how a cell gets "many details" for almost nothing

A detail package retains the ≤40k exported-triangle / ≤2 MiB asset ceiling. Count repeated instances separately
when measuring the rendered scene: instancing shares storage and reduces submission overhead, while visible
triangles, shadow work and alpha overdraw still grow with placements. The following density counts are authoring
examples, not guaranteed cheap runtime limits:

| Layer | Source | Typical count per 64 m cell | Cost |
|---|---|---|---|
| Terrain | cut from sector heightmap | 1 mesh, ~5k tris | 1 draw |
| Structures | modular kit pieces | 20–120 placements | 1 draw per kit mesh |
| Props | shared prop set | 40–250 placements | 1 draw per prop mesh |
| Foliage | 8–15 species, 3 LODs + billboard | 400–3,000 placements | 1 draw per species per LOD |
| Grass/ground cover | scatter, GPU-friendly clusters | 2,000–12,000 blades in clusters | 2–6 draws |
| Decals | damage, moss, cracks, road wear | 10–60 | 1–2 draws, atlas |
| Landmark | authored, unique | 0–1 | 1–4 draws |

Everything in that table lands in `layout.json` as an instance record. Variation comes from per-instance rotation,
uniform scale within ±15% and a tint index. Keep this consistent with the current scalar placement schema;
non-uniform scaling requires a versioned schema and collision-transform migration first.

Density presets by tier are proposed runtime requirements: Low uses coarser foliage LOD and shorter detail radius,
with decorative grass disabled first; Medium density follows measured frame time; High also stays bounded.
Nine resident cells at 40k triangles each already total 360k base triangles if all are drawn, exceeding Medium's
350k scene target before actors and HLOD. Residency, visibility, LOD and density therefore need separate caps.
Cutting density must never remove a
navigation blocker or a quest object — those are tagged `essential` in `layout.json`.

## 5. Making a model look AAA on a small budget

The workflow per asset, and the reason for each step:

1. **Blockout at gameplay scale first.** Place it in the level, look at it from the game camera, judge the silhouette.
   Most "cheap-looking" assets are proportion failures, not texture failures.
2. **High-poly only for the bake.** Sculpt or bevel-heavy modelling exists to produce a normal map, never to ship.
3. **Low-poly with clean topology to budget** (kit piece 200–3,000 tris, landmark ≤15,000).
4. **Bake** normal + AO + curvature from high to low.
5. **Texture from trim sheets and atlases.** One 2048 trim sheet can clothe an entire architectural kit. Unique
   textures are reserved for landmarks and characters.
6. **Pack ORM** (occlusion/roughness/metallic in R/G/B), ETC1S for colour, UASTC for normal and ORM.
7. **Author the LOD chain by hand for hero assets**, by decimation for the rest: LOD0 / LOD1 at 50% / LOD2 at 20% /
   billboard or HLOD merge beyond.
8. **Bake lighting**: AO into the texture, bounce into vertex colour or a small lightmap per sector. Runtime keeps one
   directional light plus ambient on Low and Medium; cascaded shadows and SSAO only on High.
9. **Export and gate**: glTF-Transform `dedup → prune → weld → resize → KTX2 → meshopt` last, validator clean, budget
   check fails the build.

Quality rules that do more than any shader: one palette per region; value contrast reserved for gameplay-relevant
objects; consistent texel density (256 px/m environment, 512 px/m characters); no single-use materials; every asset
readable in silhouette at 60 m; wear and damage from decals rather than modelled geometry.

## 6. Content volume and where it comes from

For W1 (city plus three regions), with kit reuse across regions:

| Class | Unique meshes | Source |
|---|---|---|
| Architecture kits (3 themes) | ~120 | 60% CC0 kits re-textured to our trims, 40% authored |
| Props | ~140 | mostly CC0, re-scaled and re-textured |
| Foliage species | ~18 (x3 LOD + billboard) | CC0 base, re-authored cards |
| Rocks and cliffs | ~24 | authored from 6 sculpts |
| Landmarks | ~14 | authored, unique |
| Characters and monsters | ~30 | CC0 base meshes, our materials |
| Terrain materials | 12 | authored, tileable |

≈350 unique meshes for W1 is a rounded inventory target: the listed geometry classes total 348 before LOD variants;
terrain materials are separate. At an assumed solo rate of 2–4 hours for a prop, 1–2 days for a kit theme piece set, and 2–4 days
for a landmark, W1 art is roughly **five months of half-time art work** — which is why Q2 in the master plan is a
world quarter and Q3 is not. W2 and W3 reuse 70%+ of W1 and cost proportionally less.

Every CC0 source keeps its `ASSET.md` provenance record. Paid assets stay out until the owner lifts the 0 THB rule.

## 7. Engine work this plan depends on

None of this renders well without the runtime catching up. Ordered, and already in the master plan:

1. **Thin instances** for every repeated placement (the client uses hardware instances today and no thin instances).
2. **LOD levels** via `addLODLevel` plus the existing HLOD swap, and mesh freezing for static geometry.
3. **Texture streaming and atlas residency** per tier, with a measured cap rather than a guess.
4. **Frustum plus simple occlusion** using the sector grid; portals for interiors.
5. **Impostors** for distant landmarks and tree masses.
6. **Decal system** with a shared atlas.
7. **Scatter loader** that reads `layout.json` instance records straight into instance buffers without per-object JS.
8. **Occlusion fade** when geometry hides the player — required for a dense city, as the competitor teardown notes.

## 8. Tooling to build before the bulk of the art

Producing 350 assets by hand-running commands will not happen. Before Q2 bulk production starts:

- `build_cell.py` — heightmap sector → 16 cells + collision heightfield + navmesh input, deterministic.
- `scatter.py` — density rules (slope, altitude, biome mask, exclusion zones) → `layout.json` instances.
- `bake_asset.py` — high→low bake, trim assignment, LOD generation, export, budget check, one command per asset.
- `layout_lint.py` — orphan instances, floating or sunken objects, blocked navigation, missing `essential` tags.
- A screenshot runner that captures fixed camera positions per cell each build, so visual regressions are visible in
  a diff rather than discovered by a player.

## 9. Acceptance per cell, per sector, per region

- **Cell**: budget table passes; collision closed and walkable; navmesh connected to neighbours; no hitch >100 ms on
  load at Medium; silhouette readable at 60 m; `layout.json` round-trips into the server's blocker import.
- **Sector**: HLOD ≤25k triangles and ≤4 MiB; proxy ring updated; seams invisible at the cut lines; lighting bake
  consistent with neighbours.
- **Region**: a visual cue every 100–150 m; a landmark visible from at least two neighbouring regions; a walk from
  edge to edge with no dead stretch longer than 30 seconds; tier budgets met with the density preset applied.

## 10. Schedule inside the master plan

| Month | Work | Gate |
|---|---|---|
| Oct 2026 | Tooling (§8), map standard, one cell end to end | A cell built by script passes §9 |
| Nov 2026 | Terrain masters for city + 3 regions, kit theme 1 | Seamless 256 m sector, HLOD in budget |
| Dec 2026 | Thin instances, LOD levels, scatter loader | Draw calls −50% on the city scene |
| Jan–Feb 2027 | Aetherhold final, occlusion fade, decals | M2.1 budgets on all three tiers |
| Mar 2027 | Three regions populated, navmesh, perimeter | M2.3, clamp raised to 1,024 m |
| Apr–Jun 2027 | Landmarks, dungeon valley blockout, W2 terrain | W2 gate after the 250-player run |
| Jul–Sep 2027 | Polish pass, impostors, lighting bake per sector, W3 blockout only | Beta build holds tier budgets |

## 11. Open decisions this plan needs

| ID | Question | Blocks |
|---|---|---|
| D-23 | Target world stage for 2027: W1 polished, or W2 wide | §2, all art scheduling |
| D-24 | Navmesh: bake offline from the heightmap, or run a runtime navigation grid on the server | §3, §8 |
| D-25 | Lighting: fully baked per sector, or baked AO plus one realtime directional light everywhere | §5 step 8, tier budgets |
| D-26 | Character art source: keep CC0 bases, or author one custom base mesh with a shared skeleton | §6, animation retarget cost |
| D-27 | Whether interiors are real spaces or portal-loaded instances | §7 item 4, city layout |
