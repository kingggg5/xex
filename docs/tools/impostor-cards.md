# Xexoria impostor cards (our own "Imposter Cards")

Date: 2026-10-02 · Author: Claude · Status: tool **candidate**. It is verified in `tests/impostor-review.html` and not yet integrated in the game.

> **สรุปภาษาไทย:** เครื่องมือแปลงต้นไม้หรือวัตถุไกล ๆ เป็นการ์ดภาพ โดย Blender อบภาพ 32 มุมพร้อม normal แล้ว Babylon วาดการ์ดที่รับแสงจริง ผสมมุมให้นุ่ม และมีหมอกตามฉาก ทุกหน้า atlas ใช้แค่ draw call เดียว
>
> ทดสอบป่า 400 ต้นแล้ว:
> - triangle ลดจาก 211,544 เหลือ 802;
> - mesh ที่วาดลดจาก 218 เหลือ 3;
> - เวลาเฟรมลดจาก 0.82 ms เหลือ 0.36 ms บน WebGL2.
>
> ระหว่างทดสอบพบบั๊กจริงในเกม 2 อย่าง:
> - ต้นไม้ในเกมถูกวาดกลับหน้ากลับหลัง ทำให้ใบมืดและลำต้นกลวง (แก้แล้วใน `static-model.mjs` พร้อม test);
> - texture ใบมีขอบดำ (ทำไฟล์ v2 ไว้ให้ root สลับ).

## 1. Bake (Blender 5.2, CPU)

```
blender -b --factory-startup --python assets/blender/tools/impostor_baker.py -- --config assets/models/impostors/<set>/bake.json
```

The config holds:
- the output folder and name;
- `az` (8) × `el` (4) views over `el-min`..`el-max` (0–45°);
- `res` (256 px per frame) and `page` (2048);
- `ktx` (1);
- `inputs[]`: a GLB path, a `split` regex to cut one GLB into variants, and per-mesh or per-material overrides that mirror the runtime material (texture with `uv_scale`/`wrap`/`alpha_cutoff`, or colour);
- `shading`, copied into the manifest.

Outputs:
- `<name>_albedo_<page>.png|ktx2`: sRGB-encoded, edge-bled. KTX2 is stored as UNORM so it samples exactly like the PNG.
- `<name>_normal_<page>.png|ktx2`: **object-space normals in Babylon axes**, at half resolution.
- `<name>.impostors.json`: schema `xexoria.impostor-atlas/2`, holding the grid convention, frames, pages, objects with `center_from_origin`, and shading.

Example set: `assets/models/impostors/sunmeadow-trees-v2/` (meadow trees A/B/C). The runtime copy is in `apps/client/src/assets/world/impostors/sunmeadow-trees-v2/`. Download size is 2.9 MB of KTX2.

**Decision.** Rocks (80–85 tris) and the bush (104 tris) are not impostored. A card would add overdraw and texture memory without saving geometry.

## 2. Runtime (`apps/client/src/impostors.ts`)

```ts
const field = createImpostorField(scene, manifest, file => urlOf[file]);  // one thin-instanced draw per atlas page
const h = field.add("meadow_tree_A", x, 0, z, yaw, scale);                // place at the asset origin
await field.whenReady();                                                  // compile before showing
createImpostorLod(scene, field, [{ parts: [trunkInst, canopyInst], handle: h, position }],
  { swap: shadowDistance + 10, band: 10, materials: [barkMaterial, leafMaterial] });
```

Per card, the shader:
- builds a camera-facing quad through the card centre;
- selects frames in the asset's own space, with instance yaw undone;
- bilinearly blends the 4 nearest baked views, sharpened so there is no ghosting;
- picks a mip from projected texel density, with alpha-coverage preservation;
- decodes the object-space normal and rotates it by yaw;
- applies the scene's own `StandardMaterial` lighting, fog and ACES (material named `*foliage*`, so `world-weather` dims its emissive at night);
- does an 8×8 Bayer screen-door fade that pairs exactly with Babylon's `DitheredTileFadeMaterialPlugin` on the real mesh. The cross-fade has no pop and no alpha blending.

**View–light compensation** (`shading.albedo_scale`, `shading.view_light_slope`): `f = a + b·dot(V, L)`, with V pointing from the asset to the camera and L towards the sun or moon.
- A baked texel averages several leaf normals, and that average leans towards the bake camera. Cards would otherwise over-light the sun side by about 15 % and under-light the shade side by about 20 %.
- Fit for the meadow trees: a = 1.0566, b = −0.2981, max error 4.5 % over 8 azimuths. The fit points are kept as a unit test.

Tests (`node --test`):
- `tests/impostor-math.test.mjs` (11): frame convention against the baked manifest, wrap and clamping, yaw invariance, cells, card centre, cross-fade, calibration points;
- `tests/static-model.test.mjs` (2): the winding regression.

## 3. Verified results (`tests/impostor-review.html`, game day lighting, evidence in `planning/evidence/vfx-sample-v1/impostor-*`)

| Check | Result |
|---|---|
| Silhouette, size, placement, yaw | Match the real mesh at 20/40/80/120 m (distance ladder, WebGL2 and WebGPU) |
| Coverage at 60 m | Card within 3 % of the real tree (alpha cutoff 0.35) |
| Brightness at 20/60 m (after the winding fix, bled leaves, a = 0.85, b = 0) | Within 9–17 % |
| View–light compensation | Unit-verified against the measured orbit. **Visual re-capture pending:** the dev server was stopped by low memory on 2026-10-02 |
| Forest stress, 400 trees at 60–200 m | Real: 211,544 tris, 218 active meshes, 7 draws, 0.82 ms (WebGL2) / 3.23 ms (WebGPU). Cards: 802 tris, 3 meshes, 3 draws, 0.36 ms / 2.96 ms (GPU-synced average of 90 frames) |
| Cross-fade sheet | Captured; the swap at 60 m ± 5 has no pop |

## 4. Game bugs found while validating

1. **Inside-out single-part models: fixed in `apps/client/src/static-model.mjs`.**
   - `Mesh.MergeMeshes` reverses the winding of a mirrored glTF part (the importer root has `scaling.z = -1`) only when it merges two or more meshes.
   - `environment.ts` merges each tree trunk and canopy on its own. As a result, canopies lost direct sun under `twoSidedLighting` and trunks rendered their back faces. Hero-oak LODs and VFX kit meshes were affected too.
   - The fix flips faces for a lone mirrored part.
   - Measured on tree A at 20 m: canopy brightness rose from RGB 23/27/9 to 38/42/16.
   - Regression test added; it fails without the fix.
2. **Black leaf fringes.**
   - `leaf_canopy_albedo.png` has RGB ≈ 0.03 in its transparent texels, so filtering darkens every leaf edge, and more so with distance.
   - Candidate: `apps/client/src/assets/world/leaf_canopy_albedo_v2.png` (RGB edge-bled, alpha unchanged, SHA-256 `573c3eae…`).
   - Real tree at 60 m: 31/34/13 → 40/44/16.
   - The swap belongs to root, in `environment.ts`.

## 5. Limits

- Cards do not cast shadows. Pair them with real meshes beyond the cascaded-shadow distance (55–190 m by preset).
- The compensation is fitted for this tree set under the day sun. Re-fit when the sun elevation range or the tree set changes.
- `StandardMaterial` path only. PBR assets (for example the hero oak) need a PBR variant of the plugin.
