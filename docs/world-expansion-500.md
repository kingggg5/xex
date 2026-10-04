# World expansion and 500-player target

The first large-world target is a **1,024 × 1,024 m continuous landscape** (1.05 km²) around the existing Aetherhold city, with one logical map and a future target of 500 concurrent players. The current city keeps its R5 coordinates, style, gate and plaza route. Two southbound Sunmeadow cells now ship in the local runtime; almost all of the target world remains planned.

The reviewed layout and coordinates live in [`world-layout-v1.json`](../planning/world-expansion/world-layout-v1.json). The map preview is a planning diagram, not a runtime screenshot: [open the world layout](../planning/world-expansion/world-layout-v1.svg). Regenerate it with `python -B tools/render_world_layout.py`; check its coordinate and grid contract with `python -B tools/verify_world_layout.py`.

The existing minimap now uses one projection for the player and world markers, retains authored POIs as the player moves, and draws the runtime southbound trail from the same route coordinates as the server content. This prevents markers from disappearing or drifting away from the player when routes get longer.

## What exists today

- Server movement is clamped to a 616 × 616 m square (`half_extent: 308`). The legacy starter ground is 100 × 100 m, from X=−50…50 and Z=−42…58; a flat connector now reaches X=−64…64, Z=−64…−42, and two flat detail cells continue the trail to Z=−128. The runtime clamp was not expanded.
- The R5 island spans X=−120…120, Z≈16…304. Its existing transform puts the city gate at (0,24) and the fountain plaza at (0,176). Preserve this placement exactly.
- R5’s detailed runtime model is about 67.7 MB with 892k triangles, 45 materials and 54 KTX2 textures. It nearly fills the current 900k desktop High target. Its 21.4k-triangle HLOD is a useful far-view proxy, but the Low/mobile targets have not been proven on a phone.
- One `World` accepts 50 players and the snapshot decoder caps each view at 50. The server runs 20 independent channel worlds; that is not 1,000 players together. Auth caps the process at 256 sessions. The room drains up to 512 commands per 50 ms tick, leaving little headroom if 500 players all submit movement in one tick. Snapshots are made globally and cloned per connection, so an AOI is required before scale testing.
- The strongest current capacity evidence is a 10-client, 10-minute local run. It proves a regression smoke path, not 50/500-player capacity or phone rendering.

The first necessary rule is to **leave runtime bounds at ±308 m until land, collision/navigation and the world perimeter cover every newly walkable cell**. Increasing the clamp alone would let players walk through empty or unsupported space.

## World shape

The blueprint covers X,Z=−512…512 m while keeping R5 centered at the same world coordinates. Its grid has three different purposes:

| Grid | Size | Purpose |
|---|---:|---|
| Macro sectors | 256 m, 4×4 | Blender authoring, region ownership and coarse HLOD selection |
| Art and streaming cells | 64 m, 16×16 | Terrain/prop packages, local detail and asset loading |
| Server AOI cells | 32 m, 32×32 | Player, monster and combat-interest lookup; never tied to asset chunks |

Seven connected regions provide a real travel loop rather than a larger empty square: Sunmeadow Verge leads south from the current starter route; Aetherhold preserves the city; Whispergrove wraps the west with forest ruins and a cascade; Glassmere follows the farms and river east; Emberfall Quarry and Moonfen form the southern loop; Skyreach Highlands closes the north beyond the city. Each region is planned around a recognizable skyline, two secondary route landmarks and four to six smaller activity points. Main trails get a visual cue about every 100–150 m.

The first geometry slice is implemented: **two adjacent 64 m cells** from X=−64…64, Z=−128…−64, connected to a flat 22 m strip at the old field edge. Blender reads the same prop records that produce Rust AABB colliders. The 24 authored props include fourteen trees, four bushes, four stone posts, a marker and cart; dense decorative grass/flowers and fern patches remain non-blocking. Details request at Z≤−40. The current bundle is `d25555bf8b371184`; the [latest authenticated route smoke](../planning/evidence/southbound-meadow-dressing-20260929.json) crossed both cells and checked all 26 colliders at 696 movement samples. It reached the marker within 2.13 m and cart within 2.88 m in 35.38 s. Earlier R5 gate-to-plaza evidence is retained at its own older content hash. Terrain is flat at y=0, without heightfield/navmesh enforcement.

Each cell is a Meshopt GLB with no embedded images: 21,389 and 20,382 triangles, 630,040 and 601,380 bytes respectively. Shared 512–1024 px PBR maps are separate Vite assets derived from the R5 foundry set, and the trail uses a repeating PBR cobble tile. The Blender master and renders are `assets/models/world-v1/sunmeadow_south_cells.blend`, `assets/models/world-v1/review/sunmeadow_south_cells.png` and `assets/models/world-v1/review/sunmeadow_waystone_closeup.png`; hashes and measurements are in `assets/models/world-v1/manifest.json` and `planning/evidence/southbound-meadow-dressing-20260929.json`.

The route test proves flat server movement and prop collision through this small slice. It does not prove client-side image quality on a live browser or phone, height transitions, navmesh behavior, world-boundary coverage beyond Z=−128, or 500-player capacity. The remainder of the ±308 m area is still not authored terrain.

Keep 256 m macro ownership and 64 m chunk seams in one versioned layout source. R5 remains a city-local Blender file; its global anchor is declared in the world layout and validated by the Blender-to-world transform. Export cells before static geometry is merged by material. Share tileable materials and trim sheets across cells, load detailed geometry near the player, and keep coarse HLOD visible during asynchronous loads. The simultaneously visible detail plus HLOD must fit the mobile scene budget; per-asset HLOD caps cannot be added without limit.

## 500 players in one logical map

Keep a single map identity and continuous coordinates. Art chunks are client streaming units; they must not be counted as separate player rooms. Add server spatial indexing and per-client area-of-interest snapshots before lifting caps. Each client view needs its own player, party members, nearby combatants, telegraphs and relevant events, with hysteresis or explicit enter/leave behavior. Use the same spatial index to reduce monster-to-player scans. Make client actor removal correct for both players and monsters that leave an AOI.

The protocol needs an explicit crowd decision: its player-count byte and current 50-record limit cannot describe an unfiltered 500-player view. Either version and widen/chunk player records, or retain a measured per-client crowd cap with priorities for self, party and combat. Bound packet bytes and queues in either case. Revisit the 512-command tick budget, session admission, room cap and test provisioning together; keep production abuse controls separate from local test setup.

Qualify one world through 50 → 100 → 250 → 500 clients, all in the same test world. Each rung gets three 10-minute runs with both an even distribution and a concentrated city/plaza hotspot. Include combat, reconnect bursts, slow readers and movement across AOI/cell edges. Require 20 Hz simulation, tick-work p99 ≤40 ms, fewer than 0.1% missed deadlines, at most two catch-up ticks, no unexplained command drops/resync closes, correct AOI enter/leave, bounded server and generator resources, and cleanup after each run. After three passing 500-client runs, run a six-hour 500-client soak on the intended Linux host. Stop admitting clients if the world is behind. A bot generator must support hundreds of clients and report aggregate room occupancy; the existing 1–16 bot runner is insufficient.

## Asset and PixelLab use

Continue the free-first Blender → GLB route. The first two cell assets are geometry-only Meshopt GLBs (21,389 / 20,382 triangles, 630,040 / 601,380 bytes, zero embedded images). Shared, Vite-hashed PBR PNGs use the R5 texture foundry; these first cells do not use KTX2 because KTX-Software is not configured in this build environment. Split future scenery by spatial cell before merging materials; keep R5’s source intact until the sector-export path is reviewed. Use a 512 m proxy ring, 256 m macro HLOD and 64 m detailed cells as initial packaging design, then tune them from measured draw calls, memory, transfer and device frame time.

PixelLab is useful for a separate 2D planning layer: its [Create Map tool](https://www.pixellab.ai/docs/tools/create-map) makes top-down or side-scroller pixel-art maps and documents a free canvas ceiling of 200×200; its [Create Texture tool](https://www.pixellab.ai/docs/tools/create-texture) is intended to pair with a tileset, and [Create Tileset](https://www.pixellab.ai/docs/tools/create-tileset) exports connectable pixel-art Wang/dual-grid/3×3 tiles. The texture and tileset tools require at least Tier 1. This project needs 3D terrain meshes, PBR materials and server collision, so Blender remains the scene-authoring tool; PixelLab can supply a low-cost top-down route/region concept or 2D minimap icon if the user's trial includes the needed feature. No PixelLab generation or account action was performed in this continuation, and 2D output is not used as runtime 3D/PBR content.

### Tripo shrine prototype

An original Sunmeadow Waystone concept image and H3.1 model now exist in the user's Tripo account. The generated model is public on the current Free plan, reports 1,903,553 faces / 1,002,067 vertices, and appears behind an export upgrade gate; it has not been downloaded or added to this repository. Tripo's [published pricing](https://www.tripo3d.ai/pricing) labels Free outputs public/non-commercial and Pro outputs private/commercial; its [commercial-use guide](https://www.tripo3d.ai/help/privacy-policy/how-to-use-tripo-models-commercially) also directs commercial work to a paid plan. Treat this output as an evaluation prototype only. If production use is intended, the user must complete the paid-plan checkout in Tripo; regenerate the asset under that plan rather than assuming an upgrade retroactively changes this Free-plan output, then export and reduce the mesh/texture to the verified browser/mobile budget. No payment was made.

## Verification gates

1. Validate world-layout JSON, 16×16 art grid, 32×32 AOI grid, built cell hashes and preserved R5 gate/plaza transform.
2. R5 gate-to-plaza and southbound c7/c8 routes pass separate local smokes. Both c7/c8 GLBs and shared PBR maps load in the desktop `?worldSector=1` preview, but their current visual quality remains below target. Improve that slice, then qualify Android cold/warm cell load, frame time, and memory before extending the map.
3. Build the adjoining biomes with the same content-driven cell, prop/collider and route contract. Keep map routes limited to implemented cells.
4. Run Android landscape checks and measure frame time, GPU texture residency, memory and cold/warm chunk loads. The project’s 150k-triangle / 80-material-group / 64MB compressed-texture Low targets remain unverified.
5. Implement AOI and protocol changes, then qualify the one-world load ladder and soak.
6. Consider the long-term 2.816 km square only after the first world and 500-player target pass; it is an expansion option, not today’s committed playable scope.

## Subagent reviews

Five read-only workstreams reviewed map bounds and mobile traversal, asset/PixelLab fit, the shared coordinate/data contract, mobile memory budgets and server-side 500-player capacity. No subagent edited shared files or ran a scale test. The parent retained the single-owner integration of this blueprint.

The [2026-09-30 plan reconciliation](reviews/2026-09-30-plan-reconciliation.md) connects the four new program/world/competitor/scale proposals to this contract. The [desktop meadow screenshot](../planning/evidence/meadow-lighting-20260930.png) verifies that the cells render and the cloud glow fix is visible; it does not qualify phone performance or the target art quality.
