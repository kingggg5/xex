# R5 district residency candidate

R5 keeps its authored size and composition. The district candidate divides resource
ownership and visibility, using near focal detail, middle LOD and the existing distant
city silhouette. It does not move, shrink, regenerate or publish the city.

The current runtime is **72,834,756 bytes / 892,348 triangles / 45 materials /
54 textures**. The meadow HLOD is **205,644 bytes / 21,400 triangles**. These are
transfer/geometry measurements; neither is a decoded-memory or frame-rate benchmark.

## Read-only source experiment

`assets/blender/city_r5/export_city_district_candidate.py` reads the current
`reference_city.blend`, refreshes image caches from the existing final PNGs in memory,
and builds ownership records without saving the master. Its only output locations are
`assets/models/reference-city/r5/district-candidates/` and the dedicated receipt
`planning/evidence/city-district-candidate-20261001.json`.

Run with the already installed Blender 5.2.2 LTS:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' `
  --background 'assets/models/reference-city/r5/reference_city.blend' `
  --python-exit-code 1 `
  --python 'assets/blender/city_r5/export_city_district_candidate.py' `
  -- --export-representatives
```

Omit `--export-representatives` for an inventory-only run. The script does not call
the city assembler, decimator, current package builder or any provider. The installed
exporter's operator properties were inspected locally and the recipe checks required
options at runtime; current selection/material/attribute documentation was fetched
through Context7 from the [Blender Python API](https://docs.blender.org/api/current/bpy.ops.export_scene.html).

The manifest records **16 ownership cells**, **37 stable authored roots**, **10,440
source meshes**, **10,422 static meshes**, **34 runtime hooks**, and **1,047,095
triangles**. Each object has exactly one owner; duplicate and unassigned counts are
zero. All authored roots retain their world positions and rotations. Static parts
are merged by material inside a candidate district, using copied mesh data only.
Original scene world matrices and all protected asset file hashes must match after
export. The recipe records the master, layout and recipe hashes.

| Representative source candidate | GLB bytes | Triangles | Materials | Shared PNGs | Conservative resident bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gate | 2,856,540 | 33,928 | 17 | 18 | 129,364,418 |
| Plaza | 5,706,028 | 74,738 | 32 | 33 | 240,225,011 |

These source GLBs embed **zero images**. Existing material texture bindings point to
shared final PNGs by relative URI; resource IDs contain each file's SHA-256. They
retain their authored materials, UV0, COLOR_0, normals and geometry. The receipt
contains exact triangle counts, per-static-mesh world-position/UV readback results,
resource bindings and file hashes. Shared texture references across districts are
intentional; no geometry is duplicated.

Resident-byte estimates include twice the uncompressed geometry buffer (CPU and
GPU copies), complete RGBA8 texture mip chains and source PNG bytes. They do not
pretend to measure browser or engine allocations. The PNG source candidates exceed
the mobile ceiling below. They are **source candidates only**, and must not enter
the live loader without shared KTX2 resource packaging, validated cost estimates,
district LODs and GPU review.

## Coordinates and culling ownership

All coordinates remain metres at scale 1. The conversion is:

```text
Blender (X, Y, Z) → shared (X, Z, 176 + Y)
glTF    (X, Y, Z) → shared (X, Y, 176 - Z)
```

District IDs use an 80 m ownership grid with shared X/Z origin `(-120, 16)`.
Every authored root and all its descendants belong to the root's single stable
district. Unrooted whole meshes use their AABB centre. A mesh larger than 80 m in
either horizontal dimension belongs exclusively to `city-wide-support`; the manifest
lists each of these large terrain/cliff/canal parts explicitly.

The source experiment does not cut terrain or duplicate it in adjacent districts.
`city-wide-support` has no loadable candidate here. Seam-safe terrain pages or a
separately budgeted support LOD remain an admission requirement. Keep the existing
distant city/ground fallback and collision independent until that exists.

Each district's full geometry AABB is the load/cull bound. Grid boxes and root
centres alone cannot cull roofs, cliffs or long arcades safely. A root may overhang
its ownership cell; its AABB records this. Runtime proxy suppression must follow
explicit geometry ownership and a verified prepared replacement. A whole-city
proxy cannot be hidden just because the gate alone is ready.

## Pure residency policy

`apps/client/src/city-residency.mjs` produces decisions without engine objects or
side effects. Its catalog contains only loadable LODs with conservative
`residentBytes`; do not feed unexported inventory rows with empty `lods`.

```js
const profile = resolveCityResidencyProfile(quality.preset, {
  formFactor: quality.formFactor,
});
const plan = planCityResidency({
  cells, position: { x, z }, velocity: { x: vx, z: vz },
  resident, inflight, previous, profile,
  reservedBytes: separatelyOwnedCitySupportBytes,
});
previous = plan.next;
```

Every supported asset has a distinct `near`, `mid` or `far` entry. The planner picks
near detail around the current focal region, downgrades by distance, and prefers
the closest focal cells when budgets cannot admit everything. It looks up to
3 seconds ahead at a capped 18 m/s and prefetches detail only along the approach.
The 12 m exit buffer prevents load/cancel churn at LOD boundaries. Displacements
over 140 m clear prior hysteresis and cancel obsolete work as a teleport.

| Preset | Near / mid / far distance (m) | Decoded residency ceiling | Cell ceiling | Inflight ceiling |
| --- | --- | ---: | ---: | ---: |
| Low | 24 / 64 / 150 | 64 MiB | 6 | 1 |
| Medium | 34 / 90 / 180 | 96 MiB | 8 | 2 |
| High | 44 / 120 / 230 | 160 MiB | 12 | 2 |
| Ultra | 60 / 150 / 280 | 256 MiB | 16 | 3 |

Mobile explicitly caps all presets at **96 MiB / 8 cells / 2 inflight loads**. It
preserves the selected near-distance quality choice within these resource limits.
The city budget excludes the rest of the game unless the host reserves those bytes.
These are starting ceilings, not certification for an old phone.

The host must apply the returned cancellation/eviction plan and wait for resource
release acknowledgements **before** starting replacement loads. Cancellation is
not proof that network, decoder, or GPU allocations were released. A pending row
keeps its request ID and reserved allocation across updates; duplicate requests are
not emitted. Old and new variants both count until `retireAfterReady` can release
the old one. If an existing variant already exceeds a reduced ceiling, the plan
can evict it before requesting a smaller replacement; the fallback must remain
visible. Cell count is distinct ownership cells, and temporary old/new variant
overlap is additionally constrained by the byte budget.

Use request IDs to reject late completions after cancellation or teleport; dispose
their containers and unreferenced shared resources. Update the acknowledged
resident/inflight snapshot only after host work completes. Failed loads disappear
from `inflight`; retry delays and failure telemetry belong to the host. Reserve
shared resource allocations exactly once upstream, or conservatively include them
in every asset; never omit them from both places.

The tests travel from meadow through gate and plaza, wobble around a threshold,
simulate a slow network and teleport, exercise a dense plaza under pressure, count
overlapping LOD allocations, reject oversized detail, and check capped directional
prefetch. Run `node --test apps/client/tests/city-residency.test.mjs`.

This work proves source ownership and policy bounds. GPU visual review, actual
decoded allocations, seams, hardware performance and future shared-resource
runtime packaging remain unverified. It makes no mobile-FPS or 500-player claim.
