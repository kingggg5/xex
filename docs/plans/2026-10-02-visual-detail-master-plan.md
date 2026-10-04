# Visual detail master plan: map, shaders, props, models, weather, atmosphere

Date: 2026-10-02 · Author: Claude Opus 5.5 (map and visual lane) · Status: ACTIVE PLAN
Scope: Sunmeadow v2 first (llm.txt rule 1), then the city, then later regions.
This plan joins today's specs into one order of work. The numbers live in the linked specs; this file says what happens, in which order, who owns it, and what proves it is done.

> **สรุปภาษาไทย (สำหรับเจ้าของ)**
>
> เป้าหมายคือให้ทั้งแมพดูสวยแบบเกม stylized hand-painted ระดับ AAA เหมือนภาพเป้าหมาย และวัดผลได้จริงในเกม ไม่ใช่แค่ภาพจาก Blender แผนแบ่งเป็น 10 ด้าน:
> 1. โครงแมพและรูปทรง
> 2. พื้นและ shader พื้น
> 3. ต้นไม้ หญ้า และดอกไม้
> 4. น้ำ
> 5. prop และการตกแต่ง
> 6. โมเดล (มอนสเตอร์และฮีโร่)
> 7. แสง ท้องฟ้า หมอก และเมฆ
> 8. **สภาพอากาศ** (ฝน ลม พายุ พื้นเปียก)
> 9. **บรรยากาศ** (แสงลอดใบไม้ หมอกในหุบ ละอองฝุ่น หิ่งห้อย)
> 10. ฐานเทคนิค
>
> ทำเป็น 5 เฟส:
> - **เฟส 0:** ซ่อมฐานเทคนิคที่ทำให้ทุกอย่างดูแย่หรือช้า เช่น texture บีบอัดไม่ทำงานบน WebGPU และวัสดุสองระบบที่ให้แสงไม่ตรงกัน
> - **เฟส 1:** ทำ Sunmeadow ให้เป็น vertical slice ที่สวยครบ
> - **เฟส 2:** เติม prop, สภาพอากาศ และบรรยากาศ
> - **เฟส 3:** โมเดลมอนสเตอร์และฮีโร่
> - **เฟส 4:** เก็บงานเมือง แล้วขยายไปแมพอื่น
>
> ทุกเฟสต้องผ่านเกณฑ์ภาพจริงในเกมทั้งกลางวันและกลางคืน บน WebGPU และ WebGL2 ต้องวัด FPS บน GTX 1050 และมือถือ ทุกงานต้องผ่านอย่างน้อย 3 รอบ (สร้าง → จับภาพ → วิจารณ์ → แก้)
>
> **ประสิทธิภาพและมือถือ (เป้าหมายของเจ้าของ 2026-10-02):** ภาพต้องสวยเทียบเท่าเกม DX11/DX12 แต่กิน CPU, GPU และ RAM น้อย และต้องเล่นบนมือถือได้ดี กฎทั้งหมดพร้อมผู้รับผิดชอบอยู่ใน P10 หัวข้อ "Performance and mobile" เช่น เลือก WebGPU หรือ WebGL2 จากผลวัดจริง, เปิด texture บีบอัด, ให้ glow วาดเฉพาะของที่เรืองแสง และให้มือถือใช้รายละเอียดผิวที่ bake จาก Blender แทนการคำนวณใน shader
>
> agent ใช้ effort ระดับ high หรือ xhigh ไม่ใช่ max และรันพร้อมกันครั้งละ 3–5 ตัว

## 1. Quality bar and proof

- **Look:** `docs/ui/xexoria-town-art-target-20261001.png` and the owner references (glade, volcano and WoW-like screenshots).
  - llm.txt LOOK TARGET: chunky, readable shapes; the style lives in the painted albedo; warm sun with blue fill.
- **Proof** is a BABYLON CAPTURE, not a Blender render, and covers:
  - the four locked views (player 13 m, side, close, elevated);
  - dawn, noon, dusk and night;
  - WebGPU and WebGL2;
  - frame time p50 and p95.
- **Frame-time budgets:**

  | Target | Tier | p95 |
  |---|---|---|
  | GTX 1050, 1080p | High | ≤ 16.7 ms |
  | Phone | Medium | ≤ 33.3 ms |

  - Phone results stay UNVERIFIED until a device is named.
  - **Run three capture scenes** (owner deep review §8 P0-08):
    - a solo walk;
    - a party of 5 fighting;
    - a dense-effects fight.
  - **Report:** p50/p95 frame time, memory and network stalls, with the device model and conditions. A one-off FPS number never counts.
  - **Low effects mode** keeps telegraphs, party members and HP plates (inbox B10).
- **Process:** every pillar runs at least 3 passes of build → capture → critique against its spec → repair. Same cameras, before and after.
- **Measured gates, not adjectives:**
  - normal and roughness statistics on textures;
  - foliage value percentiles against the target swatches;
  - triangles counted after export;
  - draw calls and texture MiB per tier;
  - no white clipping in emissives and glow.

## 2. Where we are (measured today)

| Area | Main defects | Source |
|---|---|---|
| Light | No real day: the sun stays 36–57° high all day. Grass and leaves use StandardMaterial (gamma, capped at 1.0) while the ground is PBR. The IBL sun sits 88° off the key light. Contrast is 1.12 against 1.04. Glow is additive and can clip | `docs/reviews/2026-10-02-map-sky-light-spec.md` |
| Ground | One grass texture plus a colour-only plugin. Roughness is fixed at 0.94 and the normal scaled to 0.35. Saturation is 0.68 against the reference's 0.54–0.57. Stone R3 normals are 98.3 % flat | `2026-10-02-map-terrain-spec.md` |
| Grass | About 3,000 cone blades, uniform ("carpet of spikes"); mirrored patches; black at night | `2026-10-02-map-grass-spec.md` |
| Trees | Home-made trees are live. The Quaternius picks have flat colour and are too dark and narrow. Stylization is in progress | trees decision; route-a evidence |
| Water | No natural water yet. Layout fixes A1 (falls landing) and A2 (stream end visible) are open | `2026-10-02-map-water-spec.md` |
| Props | Unparented gold finials sit at the fountain; produce glows; plaza rings block the main route; there are rows and clutter | `2026-10-02-prop-audit.md` |
| Models | All monsters render as one pink slime. Hero 02 is 4× over budget, with no attack, dodge or death clips | monster docs; heroes docs |
| Tech | Requested WebGPU compressed textures are off (GAP-1). KTX2 decoders come from a CDN (GAP-2). RGBA COLOR_0 pushes the ground into alpha blending (GAP-3). Double-sided materials are everywhere (GAP-4) | `2026-10-02-blender-asset-official-docs.md` |
| Map | Sunmeadow v2 layout and blockout are done (pass 4 running); spawns are planned | `docs/levels/sunmeadow-v2-level-design.md` |

## 3. The ten pillars

### P1. Map structure and forms
- **Now:** blockout pass 4 (layout v2: stone circle r 8.12, flush altar, boar trail).
- **Next:** the forms pass, which turns the blockout into modelled shapes.
  - The bluff and cliffs are sculpted by displacement, then remesh and decimate; they get painted strata.
  - The stone circle and altar get carved stones and a worn platform.
  - The bridge gets planks with chamfers and rope rails.
  - Camp structures are built from Blender recipes: haystack, tent, palisade, campfire, fence.
  - Silhouettes must read in greyscale at 13 m.
- **Also open:** the layout fixes from the water spec. The falls pool moves to (-9.6,-38) with r 2.6, and the stream end gains two small cascades and ends behind a spur boulder.
- **Owner and tools:** Claude, with xex-blender agents.
- **Gate:** per-cell ≤ 120k triangles and ≤ 40 materials; walk check passes; colliders sit on visible objects.

### P2. Ground and terrain shaders
- **Spec:** the terrain spec. A 4-layer splat (lush grass, dry grass, dirt, mud/moss) with two 257² control maps per 64 m cell (129² on phones).
  - The layers blend by height.
  - Paths come from a distance field.
  - Macro variation at 31/13 m.
  - Rotated second sample against tiling.
- **Painted texture targets per layer:**
  - ≤ 15 % of pixels within 1° of flat;
  - mean tilt 8–16°;
  - roughness span ≥ 0.12;
  - re-checked after KTX2.
- **Relief:** rock uses dual world-space projection with strata bands; top moss by normal.y between 0.50 and 0.82; curvature edge highlight; baked AO; unique bakes only near the trail.
- **Rock detail from MountainRIver:** port its rock rules (`src/materials.js`; MIT, carry both notices; `docs/reviews/2026-10-02-samg-coder-repos-review.md`) as a desktop-tier MaterialPlugin (High/Ultra, GLSL + WGSL), with a Blender bake of the same rules for mobile. The rules are triplanar macro/meso/grain noise, fracture lines, moss on up-facing faces, the wet band and the derivative bump. Owner: Claude.
- **Budgets:**

  | Tier | Texture memory |
  |---|---|
  | High | 22.7 / 24 MiB |
  | Medium | 15.2 / 16 MiB |
  | Low | 6.2 / 8 MiB |

  - ≤ 4 draws per cell; ≤ +0.8 ms p95.
- **Owner:** Claude. New `terrain-surface.ts` and `terrain-rock-surface.ts` (GLSL and WGSL).

### P3. Foliage (trees, grass, flowers)
- **Trees:**
  - Route A, the stylized Quaternius set (painted atlas, COLOR_0 gradient, wider crowns, ×1.8–2.2 root flare, proxy normals, TEXCOORD_1 wind).
  - Route B, EZ-Tree, is the fallback for broadleaf.
  - Impostor atlas v3 for 90–220 m.
  - Budgets: LOD0 4–6k triangles, LOD1 ≤ 1.6k, LOD2 an impostor.
  - LOD1 → impostor cross-fade (recheck C14): mesh LOD switches instantly, so use `DitheredTileFadeMaterialPlugin` (GLSL + WGSL; colour pass only, not depth or shadows), driven by `onLODLevelSelection` or our own distance controller.
  - Spec: the trees decision doc, sections 4–5.
- **Grass:**
  - Clumps of 3 crossed cards (12 triangles), 0.26–0.95 m tall.
  - A 2048×1024 painted atlas with 8 cells.
  - Placement:
    - 16 m thin-instance patches;
    - clustered tufts with real gaps;
    - the tuft base takes the ground colour;
    - a dithered fade ending at 60 m on High.
  - Wind weight in UV2.
  - Budgets:

    | Tier | Visible clumps | Draws | Time |
    |---|---|---|---|
    | High | ~2,000 | ≤ 24 | ≤ 1.5 ms |
    | Phone | ~420 | ≤ 10 | ≤ 2.5 ms |

  - Spec: the grass spec.
- **Flowers and understory:** the Quaternius CC0 flower heads, ferns, clover and mushrooms, placed in clusters by zone.
- **Foliage shading:** all of it moves to PBR, with a wrap/back-light term (light through leaves).
- **Foliage cost:** alpha-test cutout with depth write, cards trimmed to the painted silhouette, dithered distance fade; `needDepthPrePass` only on PBR crowns and only if measured to win (never on grass); A2C only as a WebGPU-High experiment. Owner: Claude (`2026-10-02-babylon-community-practice.md` §3.12, Top 15 #9).
- **Owner:** Claude.

### P4. Water
- **Spec:** the water spec.
- **Bed and transparency:** the real bed and stones render first; the water is one alpha layer whose opacity comes from a baked depth map.
- **Shading:**
  - two-phase flow normals;
  - Fresnel at power 5, capped at 0.6;
  - sky reflection from `env-sky-texture`;
  - sparkle clamped below white;
  - never glows, and stays out of the glow layer.
- **Optional foam detail:** the foam lace and filaments from the same MountainRIver source as P2's rock rules (`src/materials.js`; MIT; `2026-10-02-samg-coder-repos-review.md`), at runtime on High/Ultra only (P10 mobile rule) and within the budget below. Owner: Claude.
- **Waterfall:** a ballistic arc (lands 1.261 s after the lip) with 3–5 sheets, a lip and a splash ring.
- **Budget:** 2 draws, ≤ 0.25–0.70 ms by tier.
- **Owners:** Claude makes the meshes and materials. The VFX lane makes mist and spray (≤ 3 draws, ≤ 116 particles). Root adds the server hazard colliders.

### P5. Props and dressing
- **Spec:** the prop audit.
- **City, first:**
  - re-attach the 21 finials and stoppers (0 triangles);
  - switch the glowing produce to a non-emissive material;
  - clear the main route;
  - remove the even rings, cloned barrels, non-shop signs, the stall grid and the gate blob statues;
  - add story clusters (guard post, trader cart, flower beds, bench pairs, lamp pairs with banners, 3 market and 6 house scenes) from the Quaternius CC0 kits;
  - Blender recipes for what the kits lack.
  - Budget: removals free about 54k triangles; removing the 1 cm shutter-strap bevels frees about 80k more, leaving about 39k under the 900k gate.
- **Sunmeadow:**
  - remove the egg stones, mirrored Kenney pieces, the starter trees inside the walls, and anything that blocks v2;
  - add the hunter camp and dress the glade.
- **Shared rules:**
  - clusters of 3–7 with story logic, never rows;
  - kept off walking lines;
  - shared trim sheets;
  - vertex-colour variation;
  - LOD0–2 plus a collider proxy for every placed prop.
- **Owners:** Claude. Root re-verifies city traversal after any city rebuild.

### P6. Models (monsters, heroes, later NPCs)
- **Monsters:**
  - 7-monster roster with placement (checker passes);
  - pipeline steps M0–M9: concept, then Tripo P2 or a Blender build, Rigify, Mesh2Motion CC0 clips plus hand-authored combat clips, LODs, and a Babylon check;
  - budgets: regular 4–8k / 2.5k / 1k; boss ≤ 25k;
  - see the monster docs and decisions.
- **Heroes:**
  - the XS1 shared skeleton (43 core joints, ≤ 59 with extras);
  - the Quaternius UAL CC0 clip library, retargeted once;
  - combat clips authored to server timings;
  - budgets 12k / 6k / 2.5k with a 2048 atlas; separate weapon GLBs;
  - order: 02 (pilot, repair) → 01 → 05 → 06 → 04 → 03; Tripo credits are staged;
  - see the heroes docs.
- **Shading for all characters:**
  - PBR with painted albedo;
  - a rim/Fresnel term for readability at 13 m;
  - a contact shadow blob (root).

### P7. Light, sky, fog, clouds and post
- **Spec:** the sky/light spec.
- **Sun path:** rises ENE at 05:15, peaks at 58° due south at 12:00, sets WNW at 18:45. The moon peaks at 50° at 00:00.
- **Noon key:** `#FFF1DC` at 2.45, hemi `#A3C4EE` at 0.60, IBL 0.20. The IBL is rotated to the key light.
- **Shadows:** cascades at 24 / 55.5 / 130 m, 2048 × 3 on High.
- **Fog:** at noon it starts at 30 m with density 0.0028 and max 0.70. One horizon colour function feeds both the sky and the fog.
- **Clouds:** three painted layers (horizon band, mid deck, cirrus). No ball clouds, and no clouds in the shadow map.
- **Post (recheck C3):** a colour grade per time of day, using ColorCurves per key (Babylon has a single LUT slot with a `level` weight); emissive cap about 1.3.
  - **LDR path:** recreate the glow as `new GlowLayer("env-glow", scene, { alphaBlendingMode: Constants.ALPHA_SCREENMODE, ldrMerge: true, mainTextureRatio, blurKernelSize })`. The blend mode can be set only when the layer is constructed, and screen-blending a clamped glow cannot pass white.
  - **HDR candidate:** do not use screen mode. Use `DefaultRenderingPipeline` bloom (`bloomThreshold`, `bloomWeight`, `bloomKernel` 64, `bloomScale` 0.5).
- **Budget:** sky + light + post ≤ 5 ms.
- **Passes:** pass 0 instruments; pass 1 the light rig plus PBR for all lit map materials; pass 2 the sky, fog and clouds; pass 3 night lights and device runs.
- **Owners:** Claude does `environment.ts` and the lighting fields. The VFX lane makes the `world-weather` `sampleAt()` refactor (merged together with Claude's pass 1), plus the celestial path, clouds and stars.

### P8. Weather (new in this plan)

**States** (server-driven by the Codex root world clock; the client blends them):

| State | Sky / light | Fog | Wind | Surfaces | FX (VFX lane) |
|---|---|---|---|---|---|
| Clear | Per the sky spec | Normal | 0.3 | Dry | Pollen and motes |
| Overcast | Key ×0.55, hemi cooler, clouds 0.7 coverage | +30 % density | 0.5 | Dry | — |
| Light rain | Key ×0.45 | +60 % | 0.6 | Wetness ramps up | Rain streaks, ripples on water and puddles |
| Storm | Key ×0.30, lightning flashes ≤ 2 per min, capped below clipping | +90 % | 1.0 (gusts) | Fully wet, puddles fill | Heavy rain, splashes, gust leaves |
| Morning mist | Dawn grade | Height fog in the stream valley, under 3 m | 0.2 | Damp | Low mist cards |

**Shader hooks, shared by every lit map material:**
- one `weather.wetness` uniform (0–1) from `sampleAt()`;
- wet = albedo ×0.75 toward a darker hue, roughness ×0.45, plus a puddle mask (terrain cavity/AO and flat low ground) that becomes a mirror-like sky reflection;
- wet foliage gets a slight specular sheen;
- dry-out takes 120 s after the rain stops.

**Wind:**
- `nature-motion` amplitude follows the weather wind and gust curve. Grass and trees use their per-vertex weights, so no trunk-base bending.
- Water flow normals speed up by up to 1.5×.

**Rules:**
- State transitions take 60–120 s, blended.
- HP bars and damage numbers stay readable in every state.
- Snow, for later regions: an accumulation mask on upward faces (normal.y), drifts against obstacles, footprints where supported (llm.txt "Water and snow").

**Budget:** ≤ 0.6 ms on High for the weather shader terms and FX (VFX particle budgets per the VFX quality bar).

**Owners:** Codex root adds the server weather state to the clock. The VFX lane does particles and `world-weather`. Claude does the shader wetness and wind response, plus the light and fog response.

### P9. Atmosphere and ambience (new in this plan)
- **Light shafts in the glade and forest edges:** fake volumetrics as painted gradient cards, oriented to the sun, faded by angle and time of day, ≤ 8 cards per view. Real volumetrics are too costly for the GTX 1050.
- **Aerial perspective:** the sky-spec fog curve, plus the far-hill impostor belts tinted by fog.
- **Dawn valley fog:** a height fog layer under 3 m along the stream.
- **Particles (VFX lane):** dust and pollen motes by day; fireflies and wisps at night; falling leaves near the oak grove; all pooled and within the VFX bar.
- **Glow:** campfire and brazier light pools at night through the one clustered light slot (sky spec pass 3); glowing mushrooms capped below clipping.
- **Audio hooks** for later: wind, stream, birds by day, crickets at night.
- **Owners:** Claude does the cards, height fog and lighting. The VFX lane does the particles.

### P10. Technical foundation
- **GAP-1 (recheck C1):** in `scene.ts` `createRenderer`, create the WebGPU engine with `deviceDescriptor: { requiredFeatures: ["texture-compression-bc", "texture-compression-etc2", "texture-compression-astc", "float32-filterable", "float32-blendable", "rg11b10ufloat-renderable", "texture-formats-tier1", "dual-source-blending", "timestamp-query"] }`.
  - Babylon drops any feature the adapter lacks (`webgpuEngine.pure.js:431-440`).
  - An explicit list replaces `enableAllFeatures`; `enableAllFeatures: true` is the one-line alternative.
  - Ship it with GAP-2, because UASTC → BC7/ASTC uses the Lite transcoders.
  - Verify `engine.getCaps().bptc` on the GTX 1050 and `.astc`/`.etc2` on phones, and measure VRAM before and after.
  - KTX2 currently decodes to RGBA, about 4× the VRAM.
- **GAP-2 (recheck C2):** self-host every KTX2 transcoder.
  - Import `@babylonjs/ktx2decoder/wasm/{uastc_astc,uastc_bc7,uastc_rgba8_unorm_v2,uastc_rgba8_srgb_v2,uastc_r8_unorm,uastc_rg8_unorm,zstddec}.wasm?url` next to the two MSC files.
  - Post them as absolute URLs in the worker `init` message (`asset-codecs.ts:53`): `{ action: "init", urls: { wasmUASTCToASTC, wasmUASTCToBC7, wasmUASTCToRGBA_UNORM, wasmUASTCToRGBA_SRGB, wasmUASTCToR8_UNORM, wasmUASTCToRG8_UNORM, jsMSCTranscoder, wasmMSCTranscoder, wasmZSTDDecoder } }`. The worker applies them in `khronosTextureContainer2Worker.js:75-89`.
  - Gate: zero requests to `cdn.babylonjs.com` on both renderers while loading UASTC+zstd and ETC1S assets.
- **GAP-3:** world builders export RGBA COLOR_0. Use RGB, or set `transparencyMode` on materials assigned at runtime.
- **GAP-4:** make opaque materials single-sided; only foliage and cloth stay double-sided.
- **WGSL everywhere on WebGPU (recheck C16):**
  - Every material plugin overrides `isCompatible` for GLSL and WGSL.
  - Every ShaderMaterial, NodeMaterial and post-process has a WGSL path.
  - GPU particles import `@babylonjs/core/Particles/computeShaderParticleSystem` and `@babylonjs/core/Particles/webgl2ParticleSystem`.
  - Gate: no request to `cdn.babylonjs.com` (glslang, twgsl, KTX2) on either renderer.
- **Export helper:** one shared Blender glTF export helper.
  - Every option is explicit; tangents go with normal maps.
  - Never `KHR_meshopt_compression`.
  - Validate by re-import.
  - Write a receipt.
  - Sources: the official-docs and headless-automation reviews.
- **Visual test harness:** a fixed-camera capture of all views, times and renderers with metric readouts (lookdev tooling), used by every pillar.
- **Owners:** `scene.ts` is shared, so root makes a narrow patch (inbox A12). Claude owns the export helper and capture harness.

**Performance and mobile (owner goal 2026-10-02):** "look as good as DX11/DX12 games but low CPU/GPU/RAM cost, and it must work well on mobile." Research pointers: CP = `docs/reviews/2026-10-02-babylon-community-practice.md` (ranked Top 15 in §11); recheck = `docs/reviews/2026-10-02-babylon-docs-recheck.md`.

1. **Renderer by measurement:** choose WebGPU or WebGL2 per tier and device class from harness numbers, measured before and after every change. WebGPU is not automatically faster: our 400-tree test gave WebGL2 0.82 ms vs WebGPU 3.23 ms (`docs/tools/impostor-cards.md` §3). Owner: Claude (harness); root (`scene.ts` defaults). Research: CP §2.14, §7.1, §7.5; Top 15 #3.
2. **Compressed textures:** A12 (GAP-1) ships in the same patch as the self-hosted transcoders (GAP-2); BC/ASTC alone moves every UASTC texture onto CDN-loaded Lite transcoders. Owner: root (A12). Research: CP §3.1, §3.3; recheck §4 item 1; Top 15 #1, #2.
3. **WebGPU limits:** the same A12 patch passes `setMaximumLimits: true` (PBR + CSM exceed the default 16 inter-stage variables) and requests `timestamp-query` for GPU timing. Meshes keep ≤ 8 vertex buffers (drop unused `COLOR_0`/`TEXCOORD_1`, above all on skinned meshes). Owner: root (A12); Claude and the VFX lane for mesh layouts. Research: CP §3.2, §7.5; Top 15 #1, #8.
4. **Opt-in glow:** `env-glow` draws only registered emitters (an emissive material, or `mesh.metadata.glow = true`) instead of drawing every mesh a second time. A Claude agent is implementing it in `environment.ts` now; details in `2026-10-02-env-perf-quickwins.md`. P7's screen-mode options are constructor-only (recheck C3), so they go into the same `new GlowLayer` call. Owner: Claude; the VFX lane registers its emitters (inbox B11). Research: CP §3.11, §4.5; recheck 8.1, N9; Top 15 #4.
5. **Freeze static meshes and materials:** placed static meshes get `freezeWorldMatrix()` and `doNotSyncBoundingInfo = true`; static materials get `material.freeze()` (plugin uniforms still upload once per pass). Weather and time stay uniforms, never defines. Characters and morph meshes stay unfrozen; unfreeze before edits and cell rebuilds. Owner: Claude (world builders). Research: CP §2.1, §2.2; Top 15 #5.
6. **Instancing:** thin instances, one batch per type per 16–64 m tile, static buffers, bounds refreshed after edits. `InstancedMesh` only where one object must be culled or picked on its own. Owner: Claude. Research: CP §2.7, §2.8; Top 15 #7.
7. **LOD:** LOD chains ending in impostors (P3), switched by `useLODScreenCoverage`; thin-instance tiles split into distance bands; dithered LOD1 → impostor fades (P3, recheck C14). Owner: Claude. Research: CP §4.12; recheck 17.1–17.2.
8. **Resolution:** FSR1 render scaling plus an adaptive-resolution controller (frame-time p95 with hysteresis) in place of the stock SceneOptimizer. Prototype in progress: `2026-10-02-render-scaling-fsr1.md`. Owner: Claude (prototype); root for the `scene.ts` and `graphics-quality.mjs` hunks. Research: CP §3.7, §3.8.
9. **Mobile surface detail:** Blender evaluates the procedural surface rules (such as P2's rock rules) and bakes them to textures, so phones keep the look. Runtime procedural shader detail runs only on High/Ultra: mobile GPUs are bandwidth-limited, and triplanar detail triples texture fetches. Owner: Claude. Research: CP §4.1, §3.12.
10. **Shadows (the shadow diet):** cast only what reads at that distance, so no grass, small props, impostors or clouds; complex meshes cast through `layerMask` proxies. `autoCalcDepthBounds` stays off, cascades stay stabilised, and `shadowMaxZ` is fixed per tier; phones use PCF or a blob, never PCSS. Claude removes today's cloud casters in `environment.ts` (no longer part of inbox B5). Owner: Claude; root for actor casters. Research: CP §3.9, §3.10, §7.3; Top 15 #6.
11. **Characters:** animation LOD (pause off-screen and far groups, lower the update rate in the middle band); VAT plus thin instances for crowds and far monsters; `instantiateModelsToScene` for each independent character; never `createInstance` a skinned rig. Owner: root (inbox A21); Claude for export (stripped tracks, VAT bake, channel count in the receipt). Research: CP §5.1–§5.4; Top 15 #13.
12. **Pooling:** pools for monsters, players, FX and labels, and zone content through AssetContainers in one scene, because the WebGPU bind-group cache never shrinks. Owner: root (A3, A20); VFX lane (B2); UI thread (C1). Research: CP §2.10; Top 15 #12.
13. **Avoid in the world scene:** SceneOptimizer; `performancePriority` Intermediate or Aggressive; `freezeActiveMeshes`; octrees. Snapshot rendering and the Frame Graph wait until Phase 4. Owner: all lanes. Research: CP §2.3, §2.4, §2.9, §2.13, §2.15, §3.8.
14. **Phone engine options:** `powerPreference: "default"` on phones; renderer per device class (rule 1); test MSAA off at phone pixel counts; PCF or blob shadows; no SSR, TAA or SSAO; rebuild runtime-built textures on context restore (context loss means out of memory). Owner: root (inbox A18). Research: CP §3.6, §3.7, §7.1–§7.3; Top 15 #14.
15. **Shader languages:** every new shader ships WGSL and GLSL (the WGSL bullet above); no CDN glslang or twgsl. Owner: Claude (terrain, rock, water and foliage plugins); VFX lane (effect materials). Research: CP §4.2; recheck N1; Top 15 #8.
16. **No first-use hitches:** `forceCompilationAsync` for every material that can appear in the zone, then `whenReadyAsync`; lights change intensity only and are never added, removed or disabled at runtime; night lights live in one clustered container created with `dontAddToScene`. Owner: root (zone load); VFX lane (B1); Claude (environment lights). Research: CP §2.11, §2.12, §6.1; Top 15 #11.
17. **Cheap picking:** `skipPointerMovePicking = true`, `GPUPicker` with a pick list for targeting, decor unpickable. Owner: root (inbox A19). Research: CP §2.5; Top 15 #15.
18. **Core features only:** PBR plus GLSL/WGSL plugins, a painted sky with card clouds, custom water, shaft cards, baked AO, and ACES with per-time curves. No SSAO on the target tiers, and no SkyMaterial, WaterMaterial, Atmosphere addon or light-scattering post-process. Owner: Claude; VFX lane (clouds, B5). Research: CP §3.13, §4.1–§4.11; Top 15 #10.

## 4. Phases and gates

| Phase | Content | Gate to exit |
|---|---|---|
| **0, foundation** | GAP-1 to GAP-4; export helper; capture harness; light pass 0 (instrument) and pass 1 (light rig, all lit map materials to PBR, IBL rotation, contrast 1.04) | Both renderers and VRAM measured before and after; no regressions in 300 client tests; day/night captures |
| **1, Sunmeadow slice** | P1 forms; P2 terrain splat; P3 stylized trees, impostor v3 and grass; P4 water; P7 pass 2 (sky, fog, clouds) | Side-by-side against target crops at the locked views; all pillar budgets; GTX 1050 p95 ≤ 16.7 ms |
| **2, life** | P5 dressing (camp, glade, Sunmeadow clean-up); P8 weather v1 (clear, overcast, rain, mist); P9 atmosphere; P7 pass 3 (night lights) | Every weather state readable; night readable; no clipping; device runs |
| **3, models** | P6 monster samples (Mossling S1, Puddlekin, boar) and hero 02 repair plus hero 01; runtime animation controller (root) | M9 and hero validation checks; a lineup next to the 1.8 m witness |
| **4, city and rollout** | P5 city clean-up, then the remaining heroes and monsters, then the snow and lava regions with the same recipes | City ≤ 900k triangles; traversal re-verified by root |

Phases 0 and 1 can overlap where files don't collide. Keep one owner per file, and never run Blender jobs in parallel.

## 5. How the work is run

- **Agents:** `.claude/agents/`
  - `xex-blender` (high): Blender builds and stylization;
  - `xex-worker` (high): specs, code and audits;
  - `xex-reviewer` (xhigh): synthesis and art gates.
  - 3–5 at once.
  - One Blender process at a time; at least 1.5 GB free RAM before each run; Cycles on the CPU while the game runs.
- **Codex:** root, VFX lane and UI-thread tasks go through `docs/reviews/2026-10-02-claude-to-codex-inbox.md`; new items are appended there.
- **Reports to the owner:** same-day reports with images, including rejections. Never drop a route silently.
- **Approvals still needed from the owner:**
  - the Tripo login and credit stages;
  - any CC-BY asset (shop signs);
  - phone model for device runs;
  - the status screen choice.
