# Sunmeadow v2 — level design and map production plan

Date: 2026-10-02 · Author: Claude Opus 5.5 (map lane, owner re-split 2026-10-02) · Status: DESIGN, not live

- Source of truth: `planning/levels/sunmeadow-v2-layout.json`
- Plan and checks: `planning/evidence/sunmeadow-v2-layout/plan.png` and `checks.json`, from `python tools/levels/render_layout_plan.py …`. 37 clearance checks, 0 failures.

> **สรุปภาษาไทย**
>
> แมพ Sunmeadow รอบใหม่ต่อยอดจาก compact layout เดิมที่ผ่านการตรวจแล้ว ของเดิมเก็บไว้ทั้งหมด: ดงต่อสู้ 2 จุด, จุดเกิดมอนสเตอร์, เควสต์, Sella และ ID ของ prop
>
> สิ่งที่เพิ่มเข้าไปคือโครงสร้างภาพที่ compact layout ยังขาด เป็นแนวเดียวกับภาพตัวอย่างที่คุณส่งมา:
> - หน้าผากลาง สูง 10 m มีน้ำตก
> - ลำธารไหลลอดสะพานไม้
> - วงหินโบราณกับแท่นบูชาที่ดงที่สอง
> - แคมป์นักล่าแบบ WoW (เกวียน กองฟาง เต็นท์ กองไฟ)
> - ต้นโอ๊กใหญ่เป็นจุดค้นพบบนทางกลับ
> - ต้นสนโบราณที่ยอดโผล่พ้นหน้าผา ล่อสายตาผู้เล่นตั้งแต่ประตูเมือง
> - ขอบแมพเป็นหน้าผาฝั่งตะวันตก เนินฝั่งตะวันออก และกำแพงป่าฝั่งใต้
>
> พื้นที่เดินได้ยังอยู่ที่ Y=0 เพราะ server ยังไม่มี heightfield ความสูงทั้งหมดจึงเป็นส่วนภาพที่อยู่นอกทางเดิน และห้ามมีกำแพงล่องหน
>
> **ลำดับงานตามที่คุณกำหนด**
> 1. Opus วางโครงแมพ (ฉบับนี้)
> 2. Blender ขึ้นโครงโมเดลทั้งแมพ
> 3. ลงรายละเอียดพื้นผิวด้วยกฎ procedural shader/material
> 4. จัดแสงสีให้เข้ากับโทนเกม
>
> แต่ละขั้นให้ sub-agent ทำ และ Claude ตรวจทุกขั้นก่อนไปต่อ

## 1. References and intent

- **Look:**
  - the owner's game screenshots (`%USERPROFILE%\Pictures\Screenshots\Screenshot 2026-10-01 221912.png` and `…222225.png`): stylized hand-painted MMO, a lived-in camp, broadleaf trees, painted rocks;
  - the forest-glade sheet (`%USERPROFILE%\Downloads\Other-Projects\829632501_…_n.jpg`): a stream, a timber bridge, mossy boulders, lush bushes, an altar with a portal ring, dappled shadows, and a blue night with glowing orbs;
  - the volcanic sheet (`…828712242_…_n.jpg`): the lava region later, after Sunmeadow passes (llm.txt rule 1).
  - These are external references for direction only; do not copy them into the repo.
- **Target image:** `docs/ui/xexoria-town-art-target-20261001.png`.
- **Rules:**
  - llm.txt "Levels and dungeons": each space has one clear landmark, a readable route and a way back;
  - the route must be physically playable first;
  - no invisible walls.

## 2. Layout (see plan.png)

| Zone | Where (x, z in m) | Landmark | Purpose |
|---|---|---|---|
| Gate approach | Two roads from the city exit ramps: west (-10,15), 4.6 m, and east (10,15), 3.6 m. They join and run to (0,-24). The city canal `canal-water-0` (x ±6.4, z 16..60) blocks the centre line | signpost (15,11) | Leave the city and read the field |
| Windmark Hunt | clearing (-15..16, -10..21) | three restyled windmarks | Starter quest and first battle (spawn rows 0–9) |
| Hunter camp | (19..31, -16..-3), spur path | cart, haystack, tent, campfire, palisade | Lived-in dressing outside the combat footprint |
| Inner bluff | (-7..17, -46..-30), 10 m, 2 tiers | waterfall at (-7,-38), pool r 2.5 m | Breaks the line of sight; reveal moment from the trail |
| Stream and bridge | stream from the pool to the west cliff gap; bridge centre (-14,-50), 7.5 × 3.8 m | timber bridge | The trail crosses at 0.47 m from the bridge centre |
| Windstone Glade | clearing (-18..18, -86..-48) | **Stone circle:** r 8.12 m around (0,-68), 6 stones at 4/38/142/200/259/330°. The existing posts (±6.4,-63) are its gate stones; the Windstone (-9.5,-60) is a monolith outside the ring.<br>**Altar:** flush platform r 2.5 m at (-4,-70); only the central block (r 0.8) collides.<br>**Boss arena:** r 11 m, with a 12 m keep-clear for colliding props.<br>**Ancient pine:** 18 m at (8,-86) | Second battle (rows 10–12). The trail passes through the circle as a processional way. Galehorn field boss on the altar platform |
| Oak Wallow | clearing r 10 m at (32,-77.5) in the east oak grove | Mud wallow, no trees | Elite (Turfback Matriarch + boar pack) |
| East return loop | path (18,-60) → (4,-22), 2.5 m | Old Sunmeadow Oak 14 m at (32,-44), with a shrine and chest | The way back plus a discovery |
| Frame | west cliffs 8–14 m with a stream gap; east hills 3–6 m; south forest wall with a closed gate (0,-101) | — | Visible boundaries; future starter_to_south_loop |
| Beyond | impostor forest belts 90–220 m | — | Depth at low cost (`sunmeadow-trees-v3` atlas) |

**Sightlines (render-checked in the blockout):**
1. From the gate, the ancient pine's top shows above the bluff, but the glade stays hidden.
2. On the trail at (-18,-40), the waterfall and pool are revealed.
3. From the glade, the bluff and falls frame the way home.
4. On the return path at (28,-42), the hero oak comes into view.

Pass 4 results (`planning/evidence/sunmeadow-v2-blockout/sightlines_pass4.json`):

| # | Result |
|---|---|
| 1 | East ramp shows 6.0 m of the pine top; the gate road shows 5.5 m. The west ramp shows only 4.0 m, because the live city's round gate tower pulls the camera in to 8.85 m. **Accepted 2026-10-02:** the tower is fixed city geometry, and the other two exits meet the 5–6 m intent |
| 2 | The falls are fully visible from the trail |
| 3 | The falls are 93 % visible from the glade |
| 4 | All 23 of 23 samples of the hero oak are visible |

### Warps to new maps (owner, 2026-10-02)

The layout JSON holds a `warp` block on each landmark plus a `warp_network` block.

| Warp | Where | Type | Destination | Unlock | Why it is fun |
|---|---|---|---|---|---|
| City portal dais (hub) | City (40,10), r 8.5 m | Portal with rune rings and a light column | A list of **discovered** warps only | Visit a warp once to add it, as with flight paths. Free, with recommended-level labels | Exploration pays off, and the city stays the social hub |
| `warp_sunmeadow_south` | South gate (0,-101) | Walk-through gate | `southreach_field` (the next field) | Level 10 + the ridge quest. Locked look: barred gate with the sign "Road closed: Lv 10" | Shows the way onward from the start |
| `warp_windstone_portal` | Stone circle centre (0,-68), **interact-only**, r 1.8 m (the trail crosses the circle, so the portal never warps on walk-in; it clears the altar platform by 0.17 m) | Portal ring | `rimecrest_snow` ("Rimecrest Wilds", renamed from Frostvale): the first new map, built from the owner's snow pack (lv1-lv3 monsters, the Solar Scorpion boss, the bovine-shaman NPC) | Defeat Galehorn once per character. Dormant → awakening → active | Beating the boss is rewarded with a new world |

Rules:
- The server makes every transfer, with a request ID (inbox A16).
- Every destination has a return warp.
- Warp triggers never sit in a combat arena: the Windstone portal is inactive while Galehorn is announced or engaged.
- Unlocked triggers show a ground ring.
- Next maps: lava, then the dungeons from `docs/reviews/2026-10-01-dungeon-program-roadmap.md`.

## 3. Physical rules

- Walkable space is Y=0 everywhere (server planar `moveCapsule`).
- Relief is visual and stays outside walkable space:
  - bluff, cliffs and hills rise from their colliders;
  - stream banks drop from 0 to -0.35 within 1.2 m of the water;
  - the water surface sits at -0.35 and the bed at -1.0.
- Every collider sits on something visible: water edge, rock, cliff toe, hill toe, trunk capsule, bridge rails or fence.
  - The bridge deck is walkable.
  - Canopies never collide.
- Clearances, checked in checks.json:
  - path edge to water and pool ≥ 1.5 m, except at the bridge;
  - path edge to the bluff ≥ 1.0 m;
  - props ≥ 0.3 m from the water edge and ≥ 1.0 m from path edges;
  - boss arenas: no colliding prop within `arena_keep_clear_m` (12 m at the Windstone circle), except the ring's own stones and the altar block. The layout checker measures prop centres; the blockout check (`arena_check.py`) also measures collider edges, which must stay ≥ 11.5 m (0.5 m outside the 11 m arena). Pass 5: windstone edge 11.64 m, `pine_trail_north` edge 11.77 m, both accepted 2026-10-02. Inside the 11 m arena, ground cover is flowers only (≤ 0.35 m, no glow), so ground telegraphs stay readable.
- Codex root verifies the exported walk polygon and colliders against server movement before promotion.
- The server seam check still hard-codes Z=-64 (compact v1 note), so it needs Codex.

## 4. Production pipeline (owner's order), with sub-agent tasks

Each step ends at Claude's review gate. Each step must pass these before the next starts:
- the four locked views (player 13 m, side, close, elevated);
- day and night;
- the 1.8 m witness;
- labels on every image;
- receipts.

| Step | What | Who | Output | Done when |
|---|---|---|---|---|
| 0 | Layout (this doc + JSON + plan) | Claude (Opus) | layout JSON, plan.png, checks.json | ✅ 66/66 checks pass (2026-10-02, after the pass 4 review); monster plan 5,268/5,268 |
| 1 | **Blockout of the whole map** in Blender 5.2 headless from the layout JSON: walk plane, relief meshes, bluff, cliffs, hills, stream channel + water surface, path masks, bridge, landmark proxies at true scale, vegetation/rock placeholders from zones, colliders in their own collection | sub-agent | `assets/blender/sunmeadow_v2/` scripts; per-64 m-cell GLB + instance lists + collider JSON; BLENDER REVIEW renders from the 4 views and the 4 sightlines | Sightlines read as designed; no walk-area intrusions; colliders match visuals; cells ≤ budget |
| 2 | **Forms** ("ปั้นโครงโมเดล"): bluff/cliff sculpt via displacement → remesh → decimate; stone circle and altar; bridge planks; camp kit (CC0 kits where good: Quaternius props already downloaded) | sub-agent(s) | candidate GLBs with LOD0–2 and colliders | Silhouettes read at 13 m in greyscale; budgets met |
| 3 | **Procedural surface detail**: ground control maps per cell (grass / dry grass / dirt path / mud and moss from path distance, water distance, slope, AO and noise); triplanar painted rock with top moss by normal.y; forge trim sheets for wood. Bakes for unique assets | sub-agent + forge | control maps, baked textures, `meadow-surface.ts` rules (after hand-off) | No flat fills; tiling hidden at 13 m; both renderers |
| 4 | **Trees and foliage**: Route A/B of `docs/reviews/2026-10-02-trees-free-assets-decision.md`, scattered by the zone rules (clusters, gaps, never rows) | sub-agent (Route A running) | sunmeadow-trees-v4 + scatter lists + impostor atlas v3 | Section 4.4 gate of the tree doc |
| 5 | **Light, colour, tone**: noon, dusk and night per the layout JSON lighting block; dappled canopy shadows; fog; campfire and night glow (VFX lane supplies the effects) | Claude | `environment.ts` changes after hand-off; captures | Day/night parity; no clipping; contact shadows; shimmer-free cascades |
| 6 | **Integration and proof**: Babylon cells, streaming contracts (24/48/90 m detail, 34 m prefetch), server walk/collider verification by Codex | Claude + Codex root | native captures, frame-time p50/p95 on the GTX 1050, phone pass | llm.txt evidence package complete |

**Budgets:**
- Per 64 m cell: ≤ 120k triangles at LOD0, excluding vegetation, and ≤ 40 draw calls.
- Vegetation uses thin instances plus impostors.
- Textures are shared atlases.

## 5. Dependencies and open items

- **Codex root hand-off** (`docs/reviews/2026-10-02-root-handoff-maps-to-claude.md`, requested 2026-10-02 11:26): `environment.ts` and the world-cell scripts become Claude's only after it lands.
- **Existing positions to read from content:** the lookout POI and the three windmark POIs.
- **Water:** the stream surface uses the existing NodeMaterial water pattern (`city-water-engine.ts`): flow direction, depth tint, Fresnel and foam where it meets objects. Water never glows. Claude configures it for the map; the fountain stays with Codex.
- **Blockout pass 4 review decisions (2026-10-02, Claude as layout owner):**
  1. **Sightline 1 (west ramp):** accepted as is; see the sightline table in §2.
  2. **Galehorn and the altar block:** the 2.0 m body circle overlaps the r 0.8 block by 0.55 m.
     - Accepted for now. The circle is a bound, not the mesh, and the block is 1.1 m tall.
     - Re-check with the real Galehorn model footprint. If the mesh clips, widen the platform to r 3.0 m.
  3. **Arena keep-clear:** layout `arena_keep_clear_m: 12`. Three existing props move out (layout `prop_move` landmarks):
     - `sunmeadow_bush_east_north` (8,-64) → (11.5,-60.5);
     - `sunmeadow_oak_trail_north` (11,-67) → (13.5,-67);
     - `sunmeadow_bush_west_north` (-10,-62) → (-11.5,-62.5), because its collider touched the arena rim.

     The glowing mushrooms ring moves to 11.5–13 m (`sm2_scatter.py`); the flowers stay at 8.3–10.8 m. `render_layout_plan.py` now applies prop moves and checks the keep-clear.
  4. **Content migration:** done by Codex root (inbox A10). The cart goes to (13,-73), not the v1 spot (10.5,-70); `zones.json` still holds (10.5,-105) in old coordinates. The three moved props above go too.
  5. **`boar_trail` `road_safe: false`:** confirmed. It is the deliberate danger route into the elite's wallow.
  - **Rebuild:** blockout pass 5 is done (2026-10-02; `planning/evidence/sunmeadow-v2-blockout/pass5/`).
    - **Build:** Blender exit code 0, 182.6 s.
    - **Checks:** 6/6 cells re-import; 0 of 362 colliders flagged; max 30,811 triangles per cell; 0 unexpected walk hits.
    - **Arena:** 3/3 props moved with their colliders; 13 mushrooms at 11.57–12.95 m; flowers inside the arena ≤ 0.340 m.
    - **Sightlines:** unchanged.
    - **Checker:** `check_monster_spawns.py` now reads every `prop_move` landmark instead of a hard-coded cart. Result 5,268/5,268.
- **Jev:** UNAVAILABLE in this Claude session. The auto-mode classifier blocks the Jev CLI until the owner allows it. The fallback is deterministic checks (checks.json) plus Claude review. Recorded per llm.txt.

## 6. Sunmeadow v3 features — Codex continuation, 2026-10-03

**สรุปสำหรับเจ้าของ:** แผนใหม่มีถ้ำหลังน้ำตก บึงบัว อ่าวกับท่าเรือ และฟาร์มคนเลี้ยงแกะ พร้อมจุดพัก เส้นทางไปกลับ และการวางของแบบ seed เดิมสร้างซ้ำได้แล้ว มินิแมพส่งออกเป็นภาพพื้นฐานที่ยังไม่มีกรอบ/ไอคอน โดยใช้ทรงสี่เหลี่ยมมุมมนตามที่ขอ ตัวโหลดของจริงเปิดทดสอบด้วย `?dressing=v3` เท่านั้น ยังต้องตรวจภาพในเกม ทางเดินท่าเรือ น้ำ และ collision จริงก่อนเปิดเป็นค่าเริ่มต้น การผ่านแบบแปลนหรือโมเดลไม่ได้แปลว่าเล่นผ่านแล้ว

The source remains `planning/levels/sunmeadow-v2-layout.json`, now `version: v3-features`. Every v2 ID and warp/arena position is retained. M1–M3 were completed by the preceding map agent; this continuation supplies minimap, real-asset dressing loader and integration requests.

| Feature | Exact location / form | Route and purpose |
|---|---|---|
| Waterfall Grotto | West-facing inner mouth at (−4,−39), 4.5×5 m; tunnel 4.892 m; open-sky chamber centred (6.25,−39), semi-axes 6×5 m | Falls ledge from the southbound trail; hidden chamber/chest; return by the same short branch |
| Lotus Mere | Pond around (−46.4,3.5), 15.4×15.7 m; viewing terrace, 2.5 m boardwalk, broken columns | Mere spur from Sella crossroads; shrine, pond wildlife and quiet resting place |
| Brightwater Cove | Beach Z −66..−90; lake to west; 13 m pier run plus 4 m platform = 17 m reach | South-bank branch beyond the bridge; fishing slot (−60.6,−74.25), working boat/rod cluster |
| Sunmeadow Croft | Hut (38.6,11.4), well (35.6,4.6), pen [34,43]×[−14.2,−2.2] | Hunter camp → croft yard → east return loop; shepherd slot (37.9,6.4), sheep/bee zone |

The pond and cove moved from the brief's approximate positions to preserve existing hunt zones and calm-ring clearance. The Croft hut deliberately occupies the nonwalkable support band as a visible closed building; the yard stays below Z=8. Calm circles use 20/12/15/10 m radii for mere/cove/croft/grotto. Palms belong only at the cove. Wildlife definitions are species masks and anchors, not proof of a running wildlife system.

### 6.1 Seeded dressing and native loader

`tools/levels/generate_dressing.py` emits 411 entries across 17 classes from recipe `sunmeadow-dressing/1`, seed 20261003. Splitmix64 counter hashing, fixed iteration order, rounded coordinates and integer sort keys make output byte-identical. Paths plus 1 m, spawn slots, arena/warps, feature footprints, city ownership and seams are excluded. Trees are supplied only with a forest-edge mask. The source triangle estimate peaks at 38.4k per cell; it is an estimate, not the pack's actual triangle count.

`apps/client/src/sunmeadow-dressing.ts` resolves every generic scatter class to a real procedural-pack or local CC0 model. It additionally composes explicit pier/boardwalk, croft, ruin and grotto anchors from authored modules. No toy proxy is created. Some semantic substitutions remain for review: driftwood for fallen logs, farm skeps for hay-bale entries, rod racks/fish-goods crates for fishing props. Mushroom_Common is locally copied from the Quaternius Stylized Nature MegaKit standard CC0 source, with immutable licence/source hashes and canonical meshopt/KTX2 LODs (880/264/123 triangles, one draw and a shared 0.67 MiB albedo). Its native style acceptance remains separate.

Meshes preserve the full quantized glTF node/importer hierarchy before detaching: world geometry is baked, mirrored winding follows Babylon's repair, and normals use the inverse transpose. Unused tangent/colour/UV2 attributes are removed; derivative normal mapping uses position/normal/UV plus four instance-matrix attributes and one fade attribute, at most eight buffers. Shared PBR atlases and frozen cell/asset/LOD batch transforms keep material/geometry duplication bounded. Both shader languages use Babylon's complementary Bayer screen-door fade plugin.

Density follows the resolved graphics profile and never drops physical solids or landmarks. Desktop distance thresholds are 24/48/90 m, mobile 18/36/64 m, with 4 m handover bands. Actual manifest counts choose a conservative minimum source LOD per cell to keep dressing within 40k triangles. This does not certify the complete desktop 120k or mobile 40k whole-cell gate. Shadows are limited to flagged medium/large objects and LOD0/1; changing the shadow generator rebinds the casters. DEV diagnostics expose counts, source misses/errors, draws, triangle totals and cell peaks. Disposal removes observers, meshes, owned materials/textures and the debug handle.

The only environment integration is tagged `C-MAP-DRESSING`, DEV `?dressing=v3`, default OFF. Pair with root `?water=natural&look=v2` for integrated review. Model source deck top is .12 m, so the composed decks are lowered .12 m to meet physical Y=0. The historical layout deck height targets are superseded for this planar support model. Root must provide actual walk surfaces through terrain holes; visual placement alone is not a movement pass.

### 6.2 Checks and remaining gameplay contract

Continuation verification: Sunmeadow layout 168/168; monsters 5957/5957; features 130 checks, zero hard failures, one design-only warning; Rimecrest 437/437 and 4702/4702. Original v2 evidence remains under `planning/evidence/sunmeadow-v3-features/before/`. Dressing determinism is proved against two regenerated hashes and disk bytes. Python tests cover deterministic scatter, exclusions and minimap geometry; client tests cover alias coverage, hostile/oversized inputs, LOD complement, density/collider preservation, footprint fitting and quantized hierarchy transforms.

`planning/evidence/sunmeadow-v3-features/integration-contract.json` contains the exact 36 solid scatter circles, 28 feature blockers, three new polygon water hazards, four deck polygons, complete water/walk data and monster proposals. `codex-requests.md` explains admission order, A10 cell/seam rules, grotto visual/blocker carve, water holes/beds, safe spawn homes, calm suppression and UI tasks. No server/content files were changed by this lane. In particular, an intact render bluff behind a cave mouth, missing deck support or walking into negative water beds remains a blocking playability defect.

### 6.3 Minimap

`tools/levels/render_minimap.py` produces an exact flat-class 2048×2048 unframed map, binary edge mask, class-ID map, inverse/forward world-UV affines and thirteen separate icon anchors. North is +Z and UV origin is top-left. Bounds are X −64..64, Z −110..24. The west-cliff gap is rendered correctly, and the cove pier/platform and grotto route remain visible at 160 px.

The owner-requested shape is a rounded rectangle. `minimap/ui-spec.md` preserves the current Svelte UI's responsive placements and 1/2/4× zoom while documenting the preferred 160 px desktop/132 px phone target and safe zones. The source contains no baked frame, text or icons. F24 is an English three-variant painted-map draft with a strict 4 px edge tolerance and small-size QA; it is ready for supervisor review, and nothing was sent externally.

Technical planning/tests, native visual quality, server playability and device performance are separate verdicts. Refer to the continuation PROGRESS.md/receipt for actual capture status. Do not promote the dressing flag based on these plan or test results alone.
