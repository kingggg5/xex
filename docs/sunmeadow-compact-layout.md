# Sunmeadow compact candidate v1

Candidate only, activation blocked: The candidate SourceLoader gate declares BLOCKED_MISSING_VISUAL_PACKAGE for the required inner-bluff visual and verified collider bounds. Do not introduce its collider as an invisible wall. Stage/server 50 cap and 500 goal remain unqualified. All coordinates and an RFC6902 patch are in [sunmeadow-compact-v1.json](../planning/sunmeadow-compact-v1.json). Run `node tools/compact-region-candidate.mjs` for read-only validation; `--write` regenerates only this document, that JSON and the SVG. No live content, canonical art or generated bundle is changed.

The stage has exactly two combat clearings. Windmark Hunt keeps the ten existing starter encounter rows and all three windmarks in a 31×31m footprint around (0,5). Windstone Glade arranges the remaining three rows in a 36×38m footprint around (0,-68), beside the existing Windstone and broken cart. Sella remains at (2,-14); the three_windmarks quest and its three puddlekin targets remain intact. Footprints contain spawn anchors; enemy aggro/leash behavior remains unchanged and can extend beyond those footprints.

Translate both entire 64m terrain packages and their 24 props by 22m north, then re-anchor Windstone/cart to Z=-60/-70: west(-64..0,-106..-42), east(0..64,-106..-42). Their northern edges meet the existing starter floor at Z=-42. The 22m empty connector disappears. Character, building, tree, prop, collider and terrain-meter scales are preserved. City gate(0,24), fountain(0,176), castle(0,272), the 308m zone boundary and blueprint town are preserved.

The 3.8m route bends west around a new inner bluff: (0,-24) → (-12,-28) → (-18,-36) → (-18,-46) → (-10,-54) → (0,-61) → (5,-70) → (0,-80). The bluff's XZ footprint is -7..17 by -46..-30; its 10m visual height and matching candidate AABB interrupt the straight view between clearing centers. A new visual cliff package is required before promotion. Actual camera sightlines, turning and LOD visibility still need rendered evidence. Players walk on Y=0 throughout; this does not qualify ramps, cliff-top movement or a future Rapier heightfield.

![Same-scale source and candidate route](../planning/evidence/sunmeadow-compact-route-v1.svg)

| Route | Source distance / walk | Candidate distance / walk | Saving |
|---|---:|---:|---:|
| Entry to terminal trail bend | 104.222m / 23.16s | 77.645m / 17.255s | 5.906s (25.5%) |
| Entry → safe Windstone approach → safe cart approach | 100.351m / 22.3s | 69.549m / 15.455s | 6.845s (30.694%) |
| Sella → second encounter centroid via curved trail | 96.927m / 21.539s | 71.711m / 15.936s | 5.604s (26.015%) |

Walking speed is 4.5m/s from content/source/manifest.json; capsule radius 0.35m and height 1.8m come from the shared fixture. Distances follow the explicitly recorded polylines and safe landmark approach positions rather than passing through solid marker/cart centers. The terminal trail comparison moves the destination forward; this is the intended shorter stage extent. Combat/channel/input/network time is excluded. Prior 27.26s authenticated source proof is retained as provenance and is not represented as a candidate benchmark.

The candidate validator imports the existing client planar collision helper. It checks 4578 capsule samples at 0.1m spacing across the full route width and side branches and drives 985 actual 20Hz helper steps to reach every candidate endpoint. Minimum tested capsule-edge gap is 0.858m at sunmeadow_windstone. It verifies all IDs, finite coordinates, prop-cell bounds, seam continuity, quest dependencies and spawn membership. The current server seam special-case still hardcodes Z=-64; therefore the source candidate cannot be promoted merely by copying its JSON.

## Complete dependency ledger

All 24 source prop IDs preserve their identity: 22 move +22m with their package, while Windstone/cart translate and re-anchor toward the second clearing entrance, and all 24 derived static colliders move with them (including the two independently re-anchored focal landmarks). The two explicit town gate wing colliders are preserved. A new sunmeadow_compact_inner_bluff collider is added. The machine-readable ledger includes before/after centers and full collider sizes for all 27 candidate colliders.

| Prop ID | Cell | Before X,Z | After X,Z |
|---|---|---:|---:|
| sunmeadow_pine_west | sunmeadow_c7_r6 | -23, -78 | -23, -56 |
| sunmeadow_pine_northwest | sunmeadow_c7_r6 | -28, -111 | -28, -89 |
| sunmeadow_pine_west_mid | sunmeadow_c7_r6 | -27, -91 | -27, -69 |
| sunmeadow_pine_west_south | sunmeadow_c7_r6 | -23, -121 | -23, -99 |
| sunmeadow_pine_west_inner_north | sunmeadow_c7_r6 | -14, -83 | -14, -61 |
| sunmeadow_pine_west_inner_south | sunmeadow_c7_r6 | -17, -111 | -17, -89 |
| sunmeadow_windstone | sunmeadow_c7_r6 | -9.5, -97.5 | -9.5, -60 |
| sunmeadow_oak_east | sunmeadow_c8_r6 | 24, -86 | 24, -64 |
| sunmeadow_oak_east_mid | sunmeadow_c8_r6 | 23, -103 | 23, -81 |
| sunmeadow_oak_east_south | sunmeadow_c8_r6 | 28, -123 | 28, -101 |
| sunmeadow_oak_east_inner_north | sunmeadow_c8_r6 | 15, -78 | 15, -56 |
| sunmeadow_oak_east_inner_south | sunmeadow_c8_r6 | 15, -119 | 15, -97 |
| sunmeadow_bush_west_north | sunmeadow_c7_r6 | -10, -84 | -10, -62 |
| sunmeadow_bush_west_south | sunmeadow_c7_r6 | -12, -104 | -12, -82 |
| sunmeadow_bush_east_north | sunmeadow_c8_r6 | 8, -86 | 8, -64 |
| sunmeadow_bush_east_south | sunmeadow_c8_r6 | 14, -110 | 14, -88 |
| sunmeadow_oak_southeast | sunmeadow_c8_r6 | 22, -113 | 22, -91 |
| sunmeadow_broken_cart | sunmeadow_c8_r6 | 10.5, -105 | 10.5, -70 |
| sunmeadow_pine_trail_north | sunmeadow_c7_r6 | -12, -90 | -12, -68 |
| sunmeadow_oak_trail_north | sunmeadow_c8_r6 | 11, -89 | 11, -67 |
| sunmeadow_stone_post_west_north | sunmeadow_c7_r6 | -6.4, -85 | -6.4, -63 |
| sunmeadow_stone_post_east_north | sunmeadow_c8_r6 | 6.4, -85 | 6.4, -63 |
| sunmeadow_stone_post_west_south | sunmeadow_c7_r6 | -6.4, -121 | -6.4, -99 |
| sunmeadow_stone_post_east_south | sunmeadow_c8_r6 | 6.4, -121 | 6.4, -99 |

| Source spawn index | Existing enemy | Before X,Z | After X,Z | Clearing |
|---:|---|---:|---:|---|
| 0 | puddlekin | 3.5, 4 | -8, 6 | windmark_hunt |
| 1 | puddlekin | -8, 8 | 0, 9 | windmark_hunt |
| 2 | puddlekin | 10, 13 | 8, 5 | windmark_hunt |
| 3 | mossling | -14, 8 | -9, -3 | windmark_hunt |
| 4 | mossling | -8, 14 | -3, 0 | windmark_hunt |
| 5 | mossling | 12, -10 | 9, -5 | windmark_hunt |
| 6 | thistle_boar | 18, 14 | -7, 13 | windmark_hunt |
| 7 | thistle_boar | 20, -18 | 7, 13 | windmark_hunt |
| 8 | glade_wisp | 0, 20 | 0, 17 | windmark_hunt |
| 9 | glade_wisp | -20, -12 | 11, 0 | windmark_hunt |
| 10 | mossling | 14, -88 | -7, -60 | windstone_glade |
| 11 | thistle_boar | -16, -121 | 8, -66 | windstone_glade |
| 12 | glade_wisp | 25, -110 | 0, -73 | windstone_glade |

Only hunt_clearing POI moves to(0,5), and south_trail_marker moves from(-9.5,-97.5) to(-9.5,-60). Entry, regroup, Sella, three windmarks, lookout and city_gate remain fixed. NPC and quest source files, enemy tuning, drops, respawns, aggro and leash lengths remain fixed. southbound_trail retains its ID and 3.8m width with the new points above. No lava endpoint or portal is added; starter_to_south_loop stays planned and non-traversable.

Before integration, update the server starter_field seam check, remove the hardcoded22m client connector, update the route preload trigger, translate/rebuild both world-authored GLBs plus source/meshopt hashes, and update world-v1 runtime_extension cells/route/marker without renumbering macro grid packages. tools/verify_world_layout.py currently assumes the old connector and needs a compact runtime contract. Movement smoke uses fixedZ=-86/-94 targets and needs candidate route waypoints; quest smoke already follows live monster targets and must be rerun. Full exact dependencies are in the JSON.

Near detail contracts are 24m full,48m reduced and90m silhouette with 8m hysteresis. Package prefetch is 34m and  retirement 46m from package bounds. Authoring separates first-clearing, Windstone and bluff packages; matching physical collision remains present across visual LOD. Existing lazy loading loads both full cells once and retains them; per-focal release and replacements need implementation and a phone route before any memory or performance claim.

Promotion requires matching server/client bundle and art hashes, authenticated compact-route and quest completion proofs, cliff/camera/LOD look-back screenshots, and actual phone frame-time and memory results. Heightfield and Rapier traversal remain separate future engine work.
