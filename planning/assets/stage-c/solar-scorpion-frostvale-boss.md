# Stage C task list: Solar Scorpion as the Rimecrest boss (for Claude)

Date: 2026-10-02 · Drafted by: C-PRODUCER (planning only; nothing was built or run) · Owner decision (relayed 19:50): the Solar Scorpion is the snow-map boss and Stage A/B are done.

> **สรุปภาษาไทย:** บอส Solar Scorpion สร้างเสร็จแล้วใน Tripo (รูปทรง, Smart UV, texture 8K, PBR) และมี rig กับท่าเบื้องต้นแล้ว 7 ท่า ไม่ต้องใช้เครดิต Tripo เพิ่ม งานที่เหลือทำใน Blender และในเกมทั้งหมด: ลดโพลีให้ตรงงบบอส (LOD0 ไม่เกิน 25k), bake normal/AO ให้มือถือ, แพ็ก texture ใหม่, ตรวจและซ่อม rig, ทำท่าให้ครบตามจังหวะของ server, export ผ่าน export helper แล้วเข้าวงจร gauntlet ในเกมกับฉากบอสของ Rimecrest ต้องมี 3 อย่างก่อนเริ่มทำท่า: แผนผังสนามบอสใน Rimecrest, ค่าบอสฝั่ง server และภาพ key art สนามบอส (F12)

## 1. What exists (verified from the receipts on disk)

| Part | State | Where |
|---|---|---|
| Tripo source | P2.0 multi-view, job `55fe86ef-92aa-4de8-9b17-f51a343f7693`; quad 25,000 requested, 30,307 faces = 51,376 triangles; 35 credits spent (geometry and Smart UV on free trials, texture 8K 30, PBR 5) | `Downloads\Xexoria-Game\sources\boss\tripo-p2-output\boss_solar_scorpion_p20_geometry.glb`, `..._smartuv_pbr_source.glb` (SHA-256 `141232a7...f2141`) |
| UV | Tripo Smart UV, 73.1 % utilisation; 33,851 UVs all inside 0-1 (numeric check only, no overlap proof) | `boss_smart_uv_layout.png`, `boss_uv_numeric_validation.json` |
| Textures | base colour 8192 JPEG (Remove Lighting ON), metallic-roughness 4096 PNG, normal 4096 JPEG; separate metallic and roughness PNGs; emission mask DRAFT, not applied | `boss_texture_0/1/2`, `boss_metallic.png`, `boss_roughness.png`, `boss_emission_mask_draft.png` |
| Editable FBX | Tripo convert with JPEG maps | `editable-fbx\` |
| Rig | 57 bones (46 deform), 6-leg IK with foot controls, 8-bone tail, sockets `fx_tail_tip`, `fx_chest`, `fx_hand.L`, `fx_hand.R`; max 4 influences, 0 unweighted | `runtime-rig-v1\solar_scorpion_rig.blend`, `rig_validation.json`, `skeleton-spec.json` |
| Clips (30 fps, in place) | Idle 3.0 s, Walk 1.2 s (0.457 m/s), TailSweep 1.8 s, SolarSlam 2.0 s, HitReact 0.6 s, Enrage 2.0 s, Death 2.4 s; events in `animation-events.json`. **Death is the first clip in the file.** | `runtime-rig-v1\` |
| LODs | 51,376 / 25,687 / 11,302 triangles; LOD0 maps 4096 JPEG base colour, 2048 PNG normal and RM | `boss_lod0/1/2.glb`, `.meshopt.glb` |
| Validation | glTF validator 0/0; Babylon NullEngine import with 7 animation groups; Blender renders only; no game camera, no witness, no KTX2, no GPU timing | `runtime-validation.json`, `babylon-headless-validation.json` |
| Height | 4.2 m | `animation-events.json` |
| Folder note | 7,498 of the 7,677 files in `tripo-p2-output\` are a Node `node_modules` tool folder; the 110 images are all this boss | — |

Gaps against our contracts: LOD0 is about 2x the boss budget (18-25k / 8k / 3k, 2048 maps); no low-tier bake (map set B); base colour is a delit Tripo texture without the hand-painted pass; JPEG base colour; no ORM pack; export used `export_def_bones=False` (57 joints exported, including controls); the clip set does not match the server state contract; the walk speed is far below any boss move speed; no capture in the game camera.

## 2. Prerequisites (owners)

| # | Needed | Owner | Why |
|---|---|---|---|
| P1 | Rimecrest arena in the layout JSON: centre, arena radius (proposal: 14 m, keep-clear 15 m for colliding props), entry side, ground material zones | Claude (map lane) | Arena checks, camera, telegraph space |
| P2 | Server boss row: level, HP (u16), ATK/DEF, move speed, skills with windup/active/recovery/cooldown on the 50 ms grid, telegraph shapes (proposal: TailSweep = 120-degree cone 7 m; SolarSlam = circle r 4.5 m; Enrage at 30 % HP), stagger cap 400 ms, spawn/event rules | owner (numbers) + Codex server | Clips are timed only after the row exists (monsters doc section 1.2) |
| P3 | F12 arena key art picked | froggy → Claude | The Stage C scene reference |
| P4 | Capture harness reference-match mode | Claude (C-P0-CAP) | Stage C metrics |
| P5 | Licence note: the Tripo plan at generation time (2026-09-30) for commercial rights (credit guard section 5.8) | owner | Receipt completeness |

## 3. Tasks (Claude; 0 Tripo credits)

Each task ends with its evidence in `planning/evidence/monsters/solar_scorpion/v1/` and a line in the asset receipt.

1. **Intake (M0/M2).** Copy the Tripo source GLB, PBR maps and the rig blend into `assets/characters/monsters/solar_scorpion/v1/source/` as immutable sources with their SHA-256 from the receipts; never edit them. Write `spec.json`: role (Rimecrest boss), height 4.2 m (check the read against the 1.8 m witness: 2.3x), budgets, clip list from P2, sockets.
2. **Cleanup on a copy (credit guard section 7).** Metres; pivot at ground centre; front = +Z in glTF; transforms applied; merge by distance; remove loose and interior pieces; check the halo, tail joints, six leg attachments and hands for fused or floating parts; strip `KHR_materials_volume`, `FB_ngon_encoding` and `KHR_materials_specular` from the runtime export.
3. **LODs to budget.** New LOD0 at 22-24k (UV-preserving collapse decimation of the 51k source; protect the head and halo, hands, leg claws, tail tip and orb silhouettes); LOD1 8k; LOD2 3k; same UVs. Triangles counted after triangulated export. The existing 25.7k LOD1 is only a fallback starting point.
4. **Weights onto the new LODs.** Transfer weights from the rigged source to each new LOD (data transfer, nearest face interpolated); re-normalise to at most 4 influences; re-run the existing deformation checks (coxa, tail, halo rigid).
5. **Bakes (device-tier plan section 6.2).** Map set A: normal (OpenGL +Y) and AO from the 51k source onto LOD0 at 2048 (Cycles CPU, cage sized to the decimation error); map set B: onto LOD1 at 1K and 512 for Low/Medium. Form AO also into the albedo.
6. **Materials.**
   - Albedo: from the 8K delit base colour, downsample to 2048 with light sharpening, then the hand-painted pass (monsters doc section 4): top-light gradient, painted AO from the bake, crisp edge highlights on gold rims, hue variation; values 0.04-0.92. Keep the owner's gold, turquoise and red.
   - ORM: R = baked AO, G = Tripo roughness, B = Tripo metallic (gold metal, cloth and skin non-metallic).
   - Emission: finish the mask (amber orbs, halo disc core and eyes only; not every gold highlight), capped below bloom clipping.
   - PNG intermediates only (never re-encode the JPEGs as JPEG); KTX2: UASTC for the painted albedo and the normal, UASTC quality 3 for ORM; 2K / 1K / 512 variants.
7. **Rig check and repair.** Keep the custom creature rig (a six-legged centaur does not fit XS1 or a stock Rigify preset). Check it against the runtime contract (monsters doc section 7): deform bones only plus the four `fx_*` socket nodes in the export, root at the feet, no root motion, at most 64 bones (46 deform: fine), 4 influences, weights normalised.
8. **Clips to the server contract.** Using P2's timings:
   - keep and re-time Idle, TailSweep (skill 1), SolarSlam (skill 2), HitReact (as an additive hit), Enrage, Death;
   - re-key Walk to the server move speed (the current 0.457 m/s in-place cycle is far too slow for a boss: lengthen the stride, check foot sliding at most 2 cm);
   - add Spawn (rises from the cracked ice), Run or Charge if the row has one, Provoked, Stagger (at most 400 ms), the windup/active/recovery splits as events, PhaseChange if the row has phases;
   - Death ends grounded (body minimum Y at most 1 cm);
   - every clip on the 50 ms grid; Attack events within 33 ms of the server values; `animation-events.json` updated;
   - the runtime always loads with `animationStartMode: NONE` and plays clips by name (the file starts with Death).
9. **Export** with `assets/blender/tools/export_helper.py` (`character_skinned`): every glTF option explicit, tangents on, 4 influences, deform bones only, sampled animation, `EXT_meshopt_compression` last (never KHR), Draco off; glTF validator 0 errors; record the Blender and glTF add-on versions.
10. **CPU gates.** NullEngine AnimationGroup check on every LOD (monsters doc section 7.7); triangles per LOD within budget; texture sizes per spec.
11. **BLENDER REVIEW.** Front, side, back, three-quarter and head close-up with the 1.8 m witness; greyscale; the game camera (13 m, beta 1.18, FOV 1.02, target 1.65 m) at 3 m, 15 m and 30 m from the boss; check that the 4.2 m boss and its tail orb stay in frame at melee range (a framing problem is a gameplay decision, report it).
12. **Stage C gauntlet loop in Babylon** (reference-gauntlet-loop doc), at most 6 passes:
    - capture both renderers at the camera matched to the picked F12 arena key art;
    - compare: mean luminance ±0.05, contrast ±0.05, histogram EMD ≤ 0.06, saturation ±0.06, palette ΔE00 ≤ 8, boss silhouette IoU ≥ 0.85 against the owner's reference views at the matched angle, art rubric ≥ 85/100 with every line ≥ 4/5;
    - list the 5 worst problems, fix only those, re-capture, revert anything that gets worse; change method after 2 unproductive passes;
    - device check: Low draws LOD1 8k with map set B at 1K; Medium and up LOD0;
    - snow-specific checks: gold separates from snow in greyscale at 13 m; the amber orbs never clip under bloom; red boss telegraphs read on the arena floor.
13. **Receipt and hand-off.** `receipt.json` with hashes of sources and runtime files, triangles per LOD, textures, clips with frames and events, sockets, the Tripo job ID and the 35 credits already spent; then hand-off to Codex root for content wiring (spawn row, encounter model).

## 4. Art-direction note (non-blocking)

Gold on snow is the strongest figure-ground contrast in the region, so the theme clash works for us if the arena tells the story: a sun-forged guardian frozen in a glacier sun-shrine (F12). Optional, owner call: a thin rime dusting on leg tips and tail joints in the albedo pass. Do not recolour or redesign the boss.

## 5. Done when

All technical, visual, gameplay and device verdicts pass separately (llm.txt rule 7), with the evidence package: the four locked views, day and night, the 1.8 m witness, labels and receipts.
