# Rimecrest Wilds (`rimecrest_snow`) v1: level design and map production plan

Date: 2026-10-02 · Author: Claude Opus 5.5 (map lane, senior level design) · Status: DESIGN, not live

- **Source of truth:** `planning/levels/rimecrest-v1-layout.json`, `planning/levels/rimecrest-v1-base.json` (colliding props, POIs, quest objects) and `planning/levels/rimecrest-v1-monsters.json`.
- **Plan and checks:** `planning/evidence/rimecrest-v1-layout/`:
  - `plan.png` and `checks.json`: 437 layout checks, 0 failures;
  - `monsters-plan.png` and `monsters-checks.json`: 4,702 hard checks, 0 failures.
- **Renamed:** the map was called "Frostvale" (`frostvale_snow`) until 20:50 today, when it was renamed to avoid closeness to another game's "Frostveil Pass". The Sunmeadow warp block already points to `rimecrest_snow`.

> **สรุปภาษาไทย (สำหรับเจ้าของ)**
>
> **ภาพรวม:**
> - แมพใหม่ชื่อ **Rimecrest Wilds** (id `rimecrest_snow`) เป็นแมพแรกหลัง Sunmeadow ผู้เล่นมาถึงทางพอร์ทัล Windstone หลังชนะ Galehorn ที่ประมาณเลเวล 12+
> - แมพมีขนาดกะทัดรัด 2×3 ช่อง (128 × 192 m) เส้นทางหลักเป็นวงรอบทะเลสาบน้ำแข็ง Glassmere ยาว 297 m เดินครบรอบประมาณ 66 วินาที
>
> **จุดเกิด:** ผู้เล่นมาถึงที่แท่นหิน Windstone ในแอ่งหิมะที่มีหินกับต้นสนบัง รัศมี 25 m รอบแท่นไม่มีมอนสเตอร์และไม่มีระยะ aggro เลย
>
> **แคมป์ Hearthhorn (ห่างจุดเกิด 26 m):**
> - คนดูแลแคมป์คือ **Mirun** (ชื่อชั่วคราว) ศิษย์ของผู้อาวุโส Ruun ใช้โมเดลวัวตัวเดิมแต่เปลี่ยนสี ส่วน Ruun ยังอยู่ในเมืองตามที่คุณตัดสิน
> - ในแคมป์มีกองไฟ บอร์ดเควสต์ ร้านค้า เต็นท์ และจุดเกิดใหม่หลังตาย
>
> **3 โซนเรียงเป็นวงรอบทะเลสาบ:**
> 1. **ริมทะเลสาบ Glassmere (lv1, Lv 12-14):**
>    - มอนสเตอร์คือ Rimeshell Tick (เห็บเปลือกเยือกแข็ง) และ Icerib Raptor (แร็พเตอร์ซี่โครงน้ำแข็ง)
>    - แผ่นน้ำแข็งริมฝั่งเดินได้ ส่วนกลางทะเลสาบเป็นน้ำแข็งบางกับน้ำเปิดที่เดินไม่ได้ ขอบกั้นเป็นแนวแผ่นน้ำแข็งที่มองเห็นได้ จึงไม่มีกำแพงล่องหน
>    - Landmark คือน้ำตกน้ำแข็ง **Stillfall** จะเผยตัวตอนเดินอ้อมแหลม Cairn Point (วัดแล้วว่าซ่อนอยู่จริงก่อนถึงแหลม)
> 2. **สันเขาสน Rimepine (lv2, Lv 15-17):**
>    - มอนสเตอร์คือ Shardveil Wraith (วิญญาณม่านเกล็ดน้ำแข็ง) กลางวันยืนนิ่งเหมือนรูปปั้น ไม่ตีก่อน ผู้เล่นเลือกเองว่าจะสู้ กลางคืนจะตื่นและเดินลาดตระเวน
>    - Landmark คือปากถ้ำน้ำแข็ง **Rimeheart** ข้างในเป็นถ้ำเล็ก (pocket) ที่มี elite **Rimeheart Warden** ถือขวาน Rime Cleaver
> 3. **ซากวิหาร Rimehold (lv3, Lv 18-20):**
>    - มอนสเตอร์คือ Rimehold Golem
>    - Landmark คือหอระฆังสูง 21 m ซึ่งเป็นตัวล่อสายตา เห็นได้ตั้งแต่จุดเกิด (วัดแล้ว: เห็นตั้งแต่ 4.6 m ถึงยอด และยอดอยู่ในเฟรม)
>
> **รางวัลลับ:** เกาะ **Cairn Isle** อยู่กลางทะเลสาบ ไปได้ทางสะพานน้ำแข็งลับ บนเกาะมีหีบที่เปิดได้ครั้งเดียวต่อตัวละคร และเป็นจุดชมวิวที่เห็น landmark ครบทุกจุด
>
> **บอส Solar Scorpion:**
> - อยู่ในแอ่งน้ำพุร้อน **Sunscald** ที่หิมะละลายหมด เหตุผลเชิงเรื่องคือแกนสุริยะของบอสยังร้อนอยู่ จึงเกิดน้ำพุร้อนกับไกเซอร์
> - สนามรัศมี 12 m ห้ามมีของชนภายใน 13 m (วัดจากขอบ collider) และพื้นเป็นหินบะซอลต์เปียกสีเข้ม ทั้งตัวบอสสีทองและวงเตือนสีแดงจึงเด่น
> - บอสเกิดตอนกลางวัน ตรงข้ามกับ Galehorn ที่เกิดตอนกลางคืน รอบเกิดเหมือน Galehorn คือ 45 นาทีบวกสุ่ม 0-15 นาที และประกาศล่วงหน้า 60 วินาที
> - พอร์ทัลกลับแคมป์จะเปิดหลังบอสตายเท่านั้น
>
> **เส้นสายตา:**
> - ไอน้ำจากแอ่งบอสเห็นได้จากสันเขา
> - จากจุดเกิดกับแคมป์ ไอน้ำถูกซ่อนไว้ (วัดแล้ว)
>
> **Warp:**
> - กลับ Sunmeadow โดยกด interact ที่แท่น
> - พอร์ทัลหลังบอส
> - ประตู Emberpass ไปแมพลาวาในอนาคต ตอนนี้ปิดอยู่ ป้ายเขียนว่าต้อง Lv 20 และต้องทำเควสต์ก่อน
>
> **ผลตรวจ:**
> - Layout ผ่าน 437/437 และมอนสเตอร์ผ่าน 4,702/4,702 มีมอนสเตอร์ 38 แถว (ไม่เกินเพดาน 64)
> - Step 0 ไม่มีแถวไหนที่ไล่ผู้เล่นทะลุหน้าผาหรือน้ำ (0/27)
> - Sunmeadow ไม่เปลี่ยน: ก่อน `zones.json` ถูกแก้ ผลได้ 66/66 และ 5,268/5,268 ตรงกับหลักฐานเดิมทุกไบต์ และหลังแก้ ผลจากเครื่องมือที่แก้แล้วก็ยังตรงกับเครื่องมือเดิมทุกไบต์
> - ข้อสังเกต: `zones.json` ถูกแก้ตอน 20:46 ทำให้ Sunmeadow มี check H12 3 ข้อที่ต้องอัปเดต `live_xz` ของแถว 3, 6, 8 เรื่องนี้ไม่เกี่ยวกับงานนี้
>
> **สิ่งที่ต้องตัดสินใจ:**
> 1. ชื่อ Mirun
> 2. หนามมงกุฎของโกเลม จะเก็บไว้ หรือเปลี่ยนเป็นคิ้วน้ำแข็งมนเพื่อเลี่ยงความคล้าย Lich King
> 3. ไอเทมใหม่ 9 ชิ้นที่ต้องผ่านรีวิวเศรษฐกิจ
> 4. ส่งพรอมต์ key art ใหม่ 3 ชุดให้ froggy (§8.2)
> 5. ภาพ 4 ด้านของมอนสเตอร์หิมะทั้ง 4 ตัวต้องทำใหม่ตาม F13-F16 ก่อนใช้เครดิต Tripo

## 1. Sources and intent

**Owner content used (read-only; nothing in the source folders was modified):**
- **Snow pack:** `Downloads\Xexoria-Game\sources\snow\` holds 18 PNGs: lv1 has 8 (two creatures × 4 views), lv2 has 4 (one creature × 4 views) and lv3 has 6 (the golem × 4 views plus the cleaver × 2).
  - All 18 were made on 2026-09-30, 21:45-21:52. They are the only snow concept work on disk.
  - `sources\froggy\` holds only the 2026-10-02 research notes and UI controls.
  - There are **no snow map images**, and the producer's review agrees (`docs/plans/2026-10-02-asset-production-board.md` §2.1). This layout is therefore the primary design; key art comes after it (§8.2).
- **Boss:** `sources\boss\` 21_10_21 / 40 / 46 / 49 (4 views) and `tripo-p2-output\` (the owner's Tripo P2.0 model).
  - Model: 51,376 triangles, 57 bones (46 deform), 7 clips.
  - Size: 4.2 m tall with a 3.85 × 3.58 m footprint, measured from the source bounds.
  - The arena is sized for this large six-legged quadruped (§5).
- **NPC:** `sources\boss\bovine-shaman\references\{front,left,back,right}.png` and rig v1 in `assets/characters/bovine-shaman/rig-v1/`.
  - Decision relayed at 20:50: the elder Ruun stays in the city, and his apprentice (same model, palette swap) runs the Rimecrest camp.
- **Reviews followed:**
  - `planning/evidence/asset-review-20261002/` (snow pack and boss verdicts);
  - `docs/reviews/2026-10-02-monster-combat-decisions.md` (tags, MVP, cadence, runes, the 64 cap);
  - `docs/plans/2026-10-02-device-tiers-plan.md` §6.4 (cell budgets);
  - `docs/plans/2026-10-02-reference-gauntlet-loop.md` (Stage A/B/C).

**Rules carried over from Sunmeadow v2 and llm.txt:**
- one landmark per space, a readable route and a way back;
- the walkable floor is Y=0 and every relief sits outside it;
- no invisible walls;
- the camera is a 13 m boom at beta 1.18 and FOV 1.02.

## 2. Layout (see `plan.png`)

**Frame:**
- **Stage and cells:** x −64..64, z −64..128 (128 × 192 m), which is six 64 m art cells (c0/c1 × r0..r2), within the producer's "2×2 to 2×3 cells".
- **Walkable hint:** x −58..58, z −56..123.

**The loop** runs round the frozen lake Glassmere: camp → west shore (lv1) → round Cairn Point → Stillfall cove → north shore under the pine ridge (lv2) → NE junction → east shore past the Rimehold ruin (lv3) → Steamrun Bridge → camp.
- It is 297 m long, or 66 s at 4.5 m/s.
- The boss basin is a **dead-end spur through the ruin**: 77 m from the return road to the arena rim. The post-fight portal saves the walk back.

| Zone | Where (x, z in m) | Landmark | Band | Purpose |
|---|---|---|---|---|
| Arrival hollow | Dais at (−42,−44), r 2.5 | Windstone dais with 3 snow-capped ring stones (r 4.0) | — | **Arrive and orient.**<br>- The spawn faces 40° east of north: the camp smoke is 26 m ahead, and the Rimehold tower is 118 m beyond it.<br>- No spawns or aggro within 25 m (the R6 apron, a 50 × 50 m box). |
| Hearthhorn Camp (hub) | (−34..−14, −34..−16); hearth (−24,−25) | Campfire smoke and wind-streamer poles | — | **NPC hub.**<br>- Mirun, the quest board, the vendor stall and the herder tent.<br>- Respawn at `camp_regroup` (−24,−12).<br>- A signpost points west to "Glassmere Shore Lv 12-14" and north-east to "Rimehold Lv 18-20". |
| **1 Glassmere Shore** | Field (−44..−23, 4..54) plus the walkable ice shelf (x −32..−22) | **Stillfall**: a 12 m wide frozen curtain under the 18-26 m cove cliff (−48,97). It is revealed at the Cairn Point tip (−35.4,64.5) | lv1, L12-14 | **First fights.**<br>- Tick pairs burst from snow mounds.<br>- A raptor pack prowls the reeds.<br>- A raptor den sits in the cove.<br>- Three ice-fishing holes are the zone's quest objects. |
| **2 Rimepine Ridge** | The wood (−32..40, 85..105) north of the ridge road | **Rimeheart Mouth**: an ice arch at (2,106), 11 m wide with a 9.5 m underside, with a bone warning cairn | lv2, L15-17 | **Choose your fights.**<br>- Wraiths are statues by day and patrol at night.<br>- Three wind-rune stones are the quest objects. |
| Rimeheart Grotto (pocket) | (−13..16, 107..122), roofless | **Grotto Falls**: a 10 m frozen cascade, framed by the arch | elite | **Optional elite.**<br>- The Rimeheart Warden plus 2 golems.<br>- The camera-safe walls are covered in §3. |
| **3 Rimehold Ruin** | Inside walls (16..54, 12..62), with west and south gates and a north gap | **Bell tower** at (34,46): 21 m, with a bronze bell under a frost-crystal finial. It is the map's lure | lv3, L18-20 | **Big telegraphs.**<br>- Golems guard the processional way to Sunscald.<br>- Three cold ward braziers are the quest objects, relit for the questline.<br>- Wraith "temple ghosts" walk here at night. |
| Sunscald Basin (boss) | Centre (36,−34): arena r 12, floor r ~21, rim r 22 | Steam and geysers, the sun-dais, a toppled sun-disc | boss, L21-23 | Solar Scorpion (§5). |
| Cairn Isle (hidden) | Isle r 4.4 at (−6.5,44), reached by a 14 m causeway from the shelf | Rime-warden cairn | — | **Discovery reward.**<br>- A one-time chest, a lore stone, and a 360° view of every landmark (§2.2). |
| Herders' soak | Warm pool at (19.5,−1.5), 11 m off the return road | Steam and two stone benches | — | A quiet social spot on the way home, kept warm by the Steamrun. |
| Frame | Cove cliffs and ridge cliffs (16-26 m); west and south hills; east mountains (22-34 m) with the Emberpass gap; Hearthfell knoll; east scree; outer slopes of the basin rim | — | — | Visible boundaries. Every former dead-end strip was filled with relief |

### 2.1 Why this shape

- **One lake, read from everywhere.** The lake gives long, cheap sightlines: the tower across the ice, the steam beyond the ruin, and the isle in the middle.
  - The lake is also a natural boundary. Its no-go centre stops any shortcut across the loop, so the reveals and the band order hold.
- **Bands grow away from the hub in both directions.**
  - Going clockwise: lv1 west, then lv2 north, then lv3 east.
  - The return road (east shore) is road-safe, so a L20 player can walk straight from the camp to the ruin, and a new player never meets lv3 by accident.
- **Each zone has one landmark, and a reveal happens between zones:**
  - between zones 1 and 2: the Stillfall at Cairn Point;
  - on the ridge: the steam;
  - at the edge of zone 2: the grotto falls through the arch.
- **The temple guards the boss.** The Rime-wardens built Rimehold at the mouth of the basin to keep the Solar Scorpion asleep. The only walking route to the arena is through the ruin.
  - The danger route `rimehold_way` is `road_safe: false`. Golems flank it.
  - Everything else is road-safe: no aggro disc ever touches the arrival, lakeshore, ridge, return or Emberpass roads (rule R7).

### 2.2 Sightlines

These are analytic game-camera checks: the camera sits 12.02 m behind the player at 6.60 m, and the frame top is 6.83° above the horizon. They are stored in the layout's `sightlines` and are render-checked in the blockout.

| # | From → to | Distance | Result | Intent |
|---|---|---|---|---|
| 1 | Arrival dais → Rimehold tower (21 m) | 118 m | **Visible from 4.6 m to its top**. The top is in frame (the frame top there is 22.2 m). The SW ruin wall hides only the base | The lure. A 12 m `lure_corridor` keeps every tree and prop taller than 6 m out of the line |
| 2 | Camp hearth → tower | 92 m | Visible from 4.5 to 19.0 m; the top 2 m runs above the frame | The lure again, from the hub |
| 3 | Ridge road (−4,78) → Sunscald steam (24 m geyser plume) | 119 m | **Visible from 7.1 m** up to the frame top (22.3 m). The low NW rim (5-7 m) and the Steamrun breach let it through | The boss's home is revealed, across the lake and beyond the ruin |
| 4 | Arrival → Sunscald constant steam (≤ 12 m) | 79 m | **Hidden.** The 14-16 m west rim hides everything below 16.6 m. A 24 m burst shows at most a 0.9 m sliver at the frame edge | The steam stays a later discovery |
| 5 | Camp → Sunscald steam | 61 m | **Hidden.** Everything below 17.6 m is hidden, and the frame top is 15.3 m | The camp feels safe |
| 6 | Lakeshore road (−51.5,31) → Stillfall | 63 m | **Hidden.** Cairn Point (12 m) hides everything below 18.1 m; the frame top is 15.5 m | It stays hidden on the approach |
| 7 | Cairn Point tip (−35.4,64.5) → Stillfall | 31 m | **Revealed**, from 5.0 to 11.8 m of the 12 m curtain. The ice cone hides only the foot | Frozen-waterfall reveal 1 |
| 8 | Cave spur (2,98) → Grotto Falls | 24 m | **Fully visible** (0-10 m), framed by the 9.5 m arch | Frozen-waterfall reveal 2 |
| 9 | Cairn Isle → each landmark | 40-89 m | Tower 5.7-12.9 m, Stillfall 5.0-12.0 m, mouth 0-11 m, steam 7.1-18.7 m, camp smoke 0.5-10 m | The hidden reward: an overlook of everything |

**Lesson recorded (camera pitch).**
- At a 13 m boom with beta 1.18, the frame top is only about 6.6 m + 0.12 × distance.
- A 22 m waterfall seen from 30 m loses its top half, so the frozen falls are wide 10-12 m curtains under taller cliffs: the cliff runs out of frame, and the ice stays in it.
- Tall landmarks (the 21 m tower) are lures only at 90 m or more.

## 3. Physical rules

- **Walkable ground** is Y=0 everywhere, using the server's planar `moveCapsule`.
- **Relief is visual and stays outside walkable space:**
  - cliff, hill and rim toes;
  - polygon footprints (Hearthfell, Cairn Point, the ice cone, the scree, the outer rim slope);
  - ruin walls, the pressure ridge and the barred gate.
- **Water:**
  - The Steamrun, the hot pools and the lake's open water sit at Y −0.35.
  - The banks drop within 1.2 m.
  - The Steamrun is warm, so it never freezes.
- **The frozen lake (decision).** The shore-fast ice shelf, plus the hidden causeway and the isle, are **walkable ground at Y=0**. The thin ice and the steaming open lead are a **no-go water hazard** (`glassmere_open_water`). The boundary is a visible line of tilted pressure-ridge slabs, which is the collider on the shelf side. Why:
  1. **Readability.** It gives lv1 a calm, open ice field that reads as solid and keeps telegraphs readable (mid value 0.70-0.78).
  2. **No invisible wall.** Slabs and dark water make the edge obvious.
  3. **No shortcut.** Nothing across the lake can skip the loop or the reveals.
  4. **Foreshadowing.** The open lead is kept open by the warm Steamrun, so it hints at the boss's heat before players see the basin.
  5. **No server work.** No new movement feature is needed.
- **Colliders on visible things only:**
  - water edges, slabs, rocks, cliff and rim toes, ruin walls and gate posts;
  - pine trunks (0.55-0.7 m);
  - the barred Emberpass gate, which is a collider only while locked.
- **Arena keep-clear.** In the 12 m Sunscald arena, no colliding prop, pool, stream or hazard comes within 13 m of the centre, **measured at collider edges** (`arena_keep_clear_basis: collider_edge`).
  - This is stricter than Sunmeadow's centre rule.
  - Ground cover inside 12 m is at most 0.35 m (moss patches, mineral crust) and never glows.
  - Measured edges: the hot pools sit at 13.8-14.4 m and the Steamrun at 14.0 m. The nearest colliding props sit at 16.9-17.1 m:
    - the exit sun-disc frame, 16.9 m;
    - the toppled sun-disc, 17.0 m;
    - the geyser cones, 17.1 m.
- **Grotto camera.** The grotto is roofless, so the vertical boom is always clear.
  - For the first 12 m out from the floor edge, the walls lean back at no more than 30° up to 7 m; above that they rise vertical.
  - So the 13 m boom (the camera 6.6 m high, 12 m behind) clips only within 0.6 m of a wall. Camera collision (roadmap milestone D1) covers the rest.
  - The mouth arch's 9.5 m underside keeps the camera clear when it passes under.
  - The blockout measures boom clearance at 1 m steps.
- **Layout clearances** (checks.json, all pass):
  - every path edge ≥ 1.5 m from the stream (except at the bridge, crossed 0 m from its centre) and from every pool;
  - ≥ 1.0 m from every relief footprint and toe line;
  - ≥ 0.5 m from the lake hazard;
  - every prop collider edge ≥ 0.5 m from path edges and ≥ 0.3 m from water;
  - main routes ≥ 4 m wide (the producer brief) and inside the walkable hint;
  - every warp trigger outside the arena.

## 4. Warps

| Warp | Where | Type | Destination | Unlock | Notes |
|---|---|---|---|---|---|
| `windstone_return` | Dais centre (−42,−44), r 1.8 | Portal ring, **interact** | Sunmeadow `windstone_circle` (2,−72) | Always on: arriving already proves the Galehorn kill | <ul><li>Same rule as the Sunmeadow portal: never walk-in, because arrivals land on the dais (jitter r 1.5).</li><li>**Fallback:** while Galehorn is announced or engaged, the return lands at (0,−50) instead, because (2,−72) is inside Galehorn's 11 m arena. Codex root implements the check server-side.</li><li>The first arrival adds "Rimecrest Windstone" to the city portal dais list.</li></ul> |
| `warp_sunscald_exit` | (43.5,−21), r 1.8; the trigger edge is 13.2 m from the arena centre | Sun-disc portal, **interact** | `rimecrest_snow` `hearthhorn_camp` (−24,−21.4) | Active **only after the fight**: from the boss's death to its next 60 s announcement (15 min at most) | Dark and inert while the boss is alive, announced or engaged. It saves the walk back through the ruin. It is never on the hub list |
| `warp_rimecrest_emberpass` | Emberpass gate (56,76), r 3.0 | Walk-through gate | Lava region (working name Ashveil Caldera; map id to be decided), spawn `rimecrest_gate_in` | **Lv 20 + "The Sun Beneath the Ice"** (Mirun's chain). Locked look: a barred gate and the sign "Road closed: Lv 20" in Thai/English | The barred gate (relief `emberpass_gate_bar`) is a collider while locked. The return arrives at `emberpass_gate_in` (50,76.9) |

**Network rules:**
- server-authoritative transfer with a request id (inbox A16);
- no trigger inside an arena or on a spawn home (checked);
- every destination has a return;
- ground rings show when a trigger is unlocked.
- Rimecrest is **its own zone instance**. Its rows never share Sunmeadow's 64-monster snapshot; together they would be 73.

## 5. Boss arena: Sunscald Basin and the Solar Scorpion

- **Contrast and lore.** A sun-forged guardian sleeps under the basin. Its solar core never cooled, so hot springs and geysers melt a round hollow out of the snowfield. That explains why a "solar" scorpion lives in a snow land.
  - The Rime-wardens raised Rimehold to keep it asleep, and the wards are failing. The questline relights the braziers before the fight.
- **Shape.** The basin has a flat, snow-free floor of about 21 m radius inside a basalt rim at r 22.
  - **The rim is deliberately uneven:**

    | Rim section | Height | Why |
    |---|---|---|
    | West | 14-16 m | Hides the steam from the arrival and the camp |
    | South and east | 11-14 m | — |
    | North-west | 5-7 m, with a 10° cleft | The steam reads from the ridge |
    | North-east | 6-8 m | — |

    The cleft is narrower than the Steamrun itself, so the stream is never a back door into the arena.
  - **Entry:** there is one way in, the Sunscald Pass from the Rimehold south gate, a 9-10 m wide basalt cut.
  - **Exit:** the post-fight portal is the second way out.
- **The arena** is r 12 m with a 13 m keep-clear at collider edges. It is sized for a large six-legged quadruped:
  - the 3.85 × 3.58 m body (r 2.4) turns in place with 5 m or more around it;
  - Tail Sweep (a 7 m cone) and Solar Slam (a 4.5 m ring), plus a ring of 3-6 melee and ranged players, fit inside 24 m with 2 m to spare;
  - 12 m keeps the 4.2 m body in frame from the rim.

  The Stage C draft proposed 14 m. This brief's "~12 m" wins because the extra floor only lengthens runs on a phone.
- **The floor is dark wet basalt** (value 0.25-0.35), with a flush carved sun-ray inlay in pale stone lines.
  - **Why not sandstone** (as in the earlier F12 draft): warm sandstone sits at the same hue and value as the boss's gold (#B57F47), so the boss would vanish into its floor. Dark basalt makes the gold pop and keeps the crimson boss rings readable.
  - **Outside 13 m:** turquoise hot pools in cream travertine rims (the turquoise echoes the boss's inlay #518483), warm green moss, three geyser cones, four basalt columns, and a toppled golden sun-disc.
  - **Steam:** it stays below 20 % opacity under 2 m inside the arena, and decals draw above the steam cards.
- **Cadence.** It works like Galehorn, but at noon:
  - respawn 45 min after death plus a random 0-15 min (`respawn_window_s` [2700, 3600]);
  - a daylight ≥ 0.5 gate (the sun is high; Galehorn wakes at dusk);
  - a 60 s zone announcement: "The ice groans over Sunscald… the buried sun is waking." Every geyser bursts and the steam turns gold.
  - Zone messages name the nest on spawn and give the MVP's name on defeat.
  - A tombstone on the dais shows the MVP and the respawn window.
- **Fight:**
  - The boss is passive until provoked. Its leash is the arena circle.
  - **Reset:** if no contributor is inside for 10 s, it evades and heals fully. Contribution persists 120 s across a reconnect, and a reset clears it (A17).
  - Stagger cap: 400 ms.
- **Skills** (each with a body cue, an audio cue and a punish):
  - **Solar Slam:** a ring of r 4.5, 1,500 ms windup. The forelegs stay planted for 1.2 s afterwards, a ×1.5 punish window. It falls back to the current splash.
  - **Tail Sweep:** a 120° cone of 7 m, 3 m knockback.
  - **Phases:**
    - **Phase 2 (60 %):** Sunflare Lance, a 2.5 × 14 m lane toward the farthest player. Geysers erupt in turn (VFX only, outside the arena).
    - **Phase 3 (30 %), "Zenith":** enrage, with cooldowns ×0.75 and a Solar Corona donut (safe inside 4 m and outside 10 m) every 20 s.
  - The owner's seven clips map onto these. Stage C re-times them and adds Spawn, Provoked, Run and the windup/active/recovery splits (`planning/assets/stage-c/solar-scorpion-frostvale-boss.md`).
- **Numbers (proposed):**
  - **Base stats:** L22, 60,000 HP (u16-safe; about 90,000 after the u32 widening), ATK 160, DEF 14, 3.4 m/s, 6,000 EXP split by contribution.
  - **Loot and MVP:**
    - every contributor gets a personal roll;
    - the MVP gets +1 roll, `mvp_chest` and +25 % EXP;
    - the rune drops at 5 % in the MVP chest, with pity.
  - The tables are in the monsters JSON.

## 6. Hearthhorn Camp (the NPC hub)

**The NPC:** **Mirun, Ruun's apprentice** (working name; Thai มีรุน) stands at the hearth (−22.4,−26.6) with a 3 m interaction range.
- **Model:** the bovine-shaman rig v1, with an ash-brown mane and beard tips, teal/cream/saffron robes (Ruun keeps red/blue) and a snow-dust material on the shoulders and hood.
- **Mesh:** the same mesh and clips (Idle, Talk, plus the Greet clip proposed in the NPC Stage C plan).
- **Originality guard (asset review):** no totems, feathers or war paint.

**Questline "The Sun Beneath the Ice":**
1. Ice-fish the three shelf holes, which feeds the camp (lv1).
2. Quiet the three wind runes on the ridge (lv2).
3. Relight the three Rimehold ward braziers (lv3). This unlocks the lore of the Solar Scorpion.
4. Contribute to one Scorpion defeat.

Completing the chain and reaching level 20 unlocks the Emberpass gate.

**Board, vendor and camp dressing:**
- **Quest board (daily bounties):** a kill set per band, rime shards, the Rimeheart Warden, and Scorpion contribution.
- **Vendor:** trail potions, `yakbutter_tea` (heal 120, proposed) and repairs; it buys materials.
- **Camp dressing:**
  - a felt-and-hide tent, a drying rack, pack baskets, a woodpile and wind-streamer poles;
  - the warm firelight and smoke mean "safe";
  - the whole camp is inside the 25 m arrival apron.

## 7. Monster roster and placement

**Proposed level bands:**

| Band | Levels |
|---|---|
| lv1 | L12-14 |
| lv2 | L15-17 |
| lv3 | L18-20 |
| Elite | L20 |
| Boss | L22 |

The Emberpass (the lava road) opens at L20.

**Kinds** are 8-13, after Sunmeadow's 1-7.

**Stats** use the EXP curve `exp_to_next = 100 + 20 × (L − 1)` (vocations.json), which gives about 16-23 regular kills per level. Damage assumes a player curve that is not defined yet, so it is re-tuned after SYS-04.

| Monster (EN / TH) | Band, level | Tier | Owner image files (`Downloads\Xexoria-Game\sources\…`) | Read and role | Rows |
|---|---|---|---|---|---|
| **Rimeshell Tick** / เห็บเปลือกเยือกแข็ง | lv1, L12 (12-13) | regular | `snow\lv1\ChatGPT Image 30 ก.ย. 2569 21_51_28.png` (front), `…21_51_37` (left), `…21_51_41` (back), `…21_51_46` (right) | <ul><li>**Look:** an eight-legged domed tick, with a bone-rib lattice shell over a glassy blue ice body, a skull head with cyan eyes, two swept antennae and black hooked claws.</li><li>**Role:** a swarm pest that ambushes from snow mounds (aggro 5 m, assist 5 m).</li><li>**Skills:** Rime Nip, a 1.8 m circle; Shell Burst (S3), 2.5 m on itself.</li></ul> | 5 + 3 snowfall |
| **Icerib Raptor** / แร็พเตอร์ซี่โครงน้ำแข็ง | lv1, L13 (13-14) | regular | `snow\lv1\…21_51_56` (front), `…21_52_02` (left), `…21_52_09` (back), `…21_52_12` (right) | <ul><li>**Look:** a skeletal four-legged raptor-drake: bone plates over dark sinew, a horned skull, a glowing ice ribcage and a spiked whip tail.</li><li>**Role:** a fast (4.2 m/s) pack hunter: aggressive at 7 m, packs of 3 linked within 8 m.</li><li>**Skills:** Ice Pounce, 2.4 m; Tail Lash against anyone behind it.</li></ul> | 8 |
| **Shardveil Wraith** / วิญญาณม่านเกล็ดน้ำแข็ง | lv2, L16 (15-17) | regular | `snow\lv2\…21_46_31` (front), `…21_46_40` (left), `…21_50_53` (back), `…21_51_01` (right) | <ul><li>**Look:** a tall (2.6 m) bone-armoured wraith with a beaked helm, a cyan ice heart and a skirt of ice shards.</li><li>**Role:** a statue by day (passive); at night it is aggressive at 8 m and patrols.</li><li>**Skills:** Frost Lance, a lane; Shard Veil, a 2-5 m donut.</li></ul> | 7 + 4 night |
| **Rimehold Golem** / โกเลมผู้เฝ้าไรม์โฮลด์ | lv3, L18 (18-20) | regular (large) | `snow\lv3\…21_45_59` (front), `…21_46_05` (left, 3/4), `…21_46_08` (back), `…21_46_12` (right, 3/4) | <ul><li>**Look:** a massive slate rime-stone golem (3.2 m), with a dragon-skull pauldron on the right, a bone ribcage over an ice heart, a spiked crown and a shard skirt.</li><li>**Role:** a slow (2.4 m/s) sentinel with the biggest regular telegraphs.</li><li>**Skills:** Rime Fist, a 3 m circle, 1.4 s windup, then 1.1 s stuck; Ward Quake, 4.5 m.</li></ul> | 7 + 2 grotto |
| **Rimeheart Warden** / ผู้คุมหัวใจเยือกแข็ง | grotto, L20 (19-21) | **elite** | The golem views above, plus the weapon `snow\lv3\…21_46_22` (Rime Cleaver, front) and `…21_46_26` (edge) | <ul><li>**Look:** the golem at 1.25× with a brighter heart and crown, wielding the stone-and-ice **Rime Cleaver** with its bronze sun-wheel boss.</li><li>**Skills:** Cleaver Drop, a lane plus a 3.5 m circle; Rimeheart Pulse, a 3-8 m donut.</li><li>**Phase:** at 40 % it tears one golem out of the wall.</li><li>**Numbers:** 9,000 HP; respawns every 10-15 min.</li></ul> | 1 |
| **Solar Scorpion**, Sentinel of the Buried Sun / แมงป่องสุริยะ | boss, L22 (21-23) | **boss (MVP)** | `boss\ChatGPT Image 30 ก.ย. 2569 21_10_21` (front), `…21_10_40` (left), `…21_10_46` (back), `…21_10_49` (right); `boss\tripo-p2-output\` (built model) | <ul><li>**Look:** a falcon-headed, gold-armoured scorpion-centaur with six legs, a segmented tail arching to an amber orb, a sun-disc halo, turquoise inlay and red cloth.</li><li>**Fight:** see §5.</li></ul> | 1 |
| (NPC) **Mirun** / มีรุน | camp | NPC | `boss\bovine-shaman\references\front.png`, `left.png`, `back.png`, `right.png`; rig v1 in the repo | <ul><li>**Look:** an elderly yak-like shaman with a white mane, braided beard, layered Himalayan-style robes, prayer beads and a carved crook staff.</li><li>**Variant:** shown here in its apprentice palette swap.</li></ul> | — |

**Placement** (`monsters-plan.png`):
- **Rows and deploy steps:** 38 rows in 10 zones. They deploy in three steps:

  | Step | Rows | What it adds |
  |---|---|---|
  | 0 | 27 | Content only, after zone transfer (S9) |
  | 1 | +9 = 36 | S1, S2, S4: zone leashes, statues, snowfall and night rows |
  | 2 | +2 = 38 | S3, S5: the elite and the boss |

- **Concurrent peak:** 37 monsters (night with snowfall; 31-34 by day). That is under the 64 snapshot cap without AOI and the 48 design target.
- **Every step-0 row is safe to chase.** Its circle-leash chase (leash + 2.5 m) stays clear of water and relief (0 of 27 cross), because monsters have no collision yet. That is why:
  - golems use aggro and leash 5 at step 0;
  - wraiths use the interim 3 m pseudo-passive (Sunmeadow decision 2);
  - the grotto golems wait for zone polygons at step 1.
- **Density:** 0.4-1.8 rows per 100 m² of leash. The worst case was measured on a 2 m grid of walkable points, counting weather rows:

  | Radius | By day | At night | Worst spot |
  |---|---|---|---|
  | 25 m | 11 | 13 | Shore in snowfall (day); west wood with its patrol (night) |
  | 40 m | 15 | 17 | — |

  Sunmeadow v2, already reviewed, measures 11/12 within 25 m and 20/20 within 40 m, so Rimecrest is no denser. On mobile-mid only 8 monsters draw at full detail (the device-tier cap); the rest drop to LOD1.
- **Kill capacity:** about 3-10 kills/min per zone.
- **Reward loop:**
  - **Kills give:**
    - `rime_shard` (every regular);
    - `frostbone_splinter` (bone constructs);
    - `golem_heartstone` (golems, rare; elite guaranteed);
    - `rimecrest_box`.
  - **Daily turn-ins:** the camp board takes them.
  - **Elite:** the Rimeheart Warden every 10-15 min drops heartstones and the `rimeguard_axe` (8 %).
  - **Boss:** every 45-60 min it drops `sunscald_ember`, the `rimeguard_mantle` (10 %) and the MVP chest.
  - **One-time:** the Cairn Isle chest and the lore cairn.
  - **Runes:** `rimecrest_rune`, outside the drop tables, at 0.2 % / 1 % / 5 % with pity.
  - **Item status:** all 9 new item ids are `proposed_items` in the monsters JSON, pending the economy review.

## 8. Art pipeline

### 8.1 Which owner images need 4-view sets for Tripo

| Owner set | Needs a new F6-format 4-view? | Why (asset review 2026-10-02) | Draft |
|---|---|---|---|
| lv1 tick (21_51_28/37/41/46) | **Yes** | Thin legs and antennae (2.6-6.1 % of the silhouette under 61 px); mirror IoU 0.717 and 0.838; 1,254 px canvases | `planning/assets/froggy-drafts/F13-snow-lv1-bone-tick-4view.md` |
| lv1 raptor (21_51_56, 21_52_02/09/12) | **Yes** | Heights differ 17.3 %; front/back IoU 0.405; left/right 0.649 | `F14-snow-lv1-bone-raptor-4view.md` |
| lv2 wraith (21_46_31/40, 21_50_53, 21_51_01) | **Yes** | Left/right width 21.6 %, IoU 0.790; needs an A-pose | `F15-snow-lv2-bone-wraith-4view.md` |
| lv3 golem (21_45_59, 21_46_05/08/12) | **Yes** | The side views are 3/4, not profiles; left/right width 12.8 %; front/back IoU 0.876. Run QA with `--asymmetric` (the pauldron). The Warden reuses this mesh | `F16-snow-lv3-rime-golem-4view.md` |
| lv3 cleaver (21_46_22/26) | No | QA PASS on the single image; a Blender hard-surface build (0 credits) | — |
| Solar Scorpion | No | Already built by the owner in Tripo (Stage C only) | `planning/assets/stage-c/solar-scorpion-frostvale-boss.md` |
| Bovine shaman | No | Already built (rig v1); the apprentice is a palette swap | `planning/assets/stage-c/bovine-shaman-npc.md` |

Tripo spend runs only after QA and design PASS: cards 09-12, 550 credits planned (950 worst case), pending the owner's ceiling.

### 8.2 froggy prompts for the missing key art (Stage A, 16:9, 3 variants each)

There are no snow map images on disk. The existing drafts are F10 (`F10-frostvale-snow-region-keyart.md`) and F12 (`F12-frostvale-boss-arena-keyart.md`). They describe an earlier composition: a frozen river and bridge, a glacier edge, and a sandstone sun-shrine plaza 28 m across.
- **Prompts 1 and 2 replace their scene content.** The producer copies them into the drafts.
- **Prompt 3 is new.**
- **F11** (the arrival platform) **stays valid.** Its 5 m dais and three stones with gaps of 3 m or more match the layout (stones at r 4.0, gaps 5.5 m).
- **Attach to all three:** the look target `docs/ui/xexoria-town-art-target-20261001.png`, plus each prompt's own attachments.
- **Common requirements:**
  - the core sentence from the gauntlet doc;
  - "CONCEPT" as the only text;
  - snow no brighter than #E8EEF2;
  - shadows #9FB3D1 / #7E8FB8;
  - faceted translucent ice with a cold core #2F7FA6;
  - no glow on water or snow;
  - original Xexoria content: no Northrend or Icecrown, Skyrim, God of War, Genshin Dragonspine or Frostveil look.

**Prompt 1: Rimecrest Wilds region key art from the arrival** (replaces F10's composition)

```text
Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), Xexoria look target attached. Keep the design clean
for 3D generation: clear shapes, clear light and shadow, uncluttered background, nothing too dark. Make 3 variants as separate
generations. Label "CONCEPT" in a small corner tag; no other text.

Camera: the game's player camera, 13 m behind a 1.8 m adventurer, about 22 degrees above the horizon, vertical FOV about 58 degrees,
looking north-east.

Front to back:
1. Foreground: a sheltered snowy hollow ringed by snow-capped boulders and a few pines. The adventurer has just stepped off a round
   carved stone dais (5 m across, two very low steps, a faint cyan rune ring #72D5DE, never white). Three snow-capped wind-carved
   sandstone standing stones (2.6 m) stand around it with a wide gap toward the viewer's path.
2. 25 m ahead: a yak-herder camp, a felt-and-hide tent, a stone-ringed campfire with warm light and a thin smoke line, a drying
   rack, pack baskets and cloth wind-streamer poles. A packed-snow trail (4 m) leads into it.
3. Middle: a wide frozen lake. The near shore is white, snow-dusted, shore-fast ice that looks solid and walkable. A clear line of
   tilted ice slabs (pressure ridge) separates it from grey thin ice and dark water. In the lake centre sits a small islet with
   a stone cairn. Far right of the lake: a steaming open lead of dark water.
4. Across the lake (far): the ruin of a frost temple on the east shore: broken pale stone walls and a slim bell tower (about 21 m)
   with a bronze bell under a frost-crystal finial that catches the sun. The tower is the eye's goal; the ruin stays small.
5. Left: a rocky headland reaching into the lake; behind it, unseen, a cove (no waterfall visible from here). Beyond the lake
   along the top of the frame: a pine-covered ridge under grey-blue cliffs, with a small blue ice arch in the cliff.
6. Far right, behind a tall dark basalt rim: at most one faint wisp of steam (the boss basin stays hidden).

Light: low winter sun, late morning, warm key from the right (#F6C95F tint), soft blue-violet fill, long soft shadows on the snow;
light blue haze only far away. Snow never pure white. Ice faceted and translucent at thin edges; no glossy plastic ice.
Gameplay: walkable ground is flat and wide; height only in cliffs, hills and the headland; combat snowfields calm and open.

Variants: A = the tower centred above the camp smoke; B = the camera turned 10 degrees left so the headland and islet read;
C = dusk, the camp fire and the tower bell catching the last sun.

Checklist (PASS/FAIL per variant): in greyscale at 160 px wide the dais, the camp, the shelf edge and the tower read; no area
darker than about 15 % brightness; no clipped highlights; only the CONCEPT tag as text; original.
```

**Prompt 2: Sunscald Basin boss arena with the Solar Scorpion** (replaces F12's arena)

```text
Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), Xexoria look target attached. Keep the design clean
for 3D generation: clear shapes, clear light and shadow, uncluttered background, nothing too dark. Make 3 variants as separate
generations. Label "CONCEPT" in a small corner tag; no other text.

Attach and keep EXACTLY on-model (no redesign, recolour, extra armour or frost): sources\boss\ChatGPT Image 30 ก.ย. 2569 21_10_21.png
(front), 21_10_40 (left), 21_10_46 (back), 21_10_49 (right) and tripo-p2-output\runtime-rig-v1\runtime_lod0_front.png.

Lore: a sun-forged guardian sleeps under a geothermal basin in the snow; its heat melts the snow and feeds hot springs and geysers.
Warm gold against cold blue snow is the point of the image.

The arena (what we will build):
- A round, flat, snow-free floor 24 m across of DARK WET BASALT flagstones (value 0.25-0.35) with a flush carved sun-ray inlay in
  pale stone lines radiating from a round sun-dais at the centre. Calm floor: no rubble, no ice spikes, no glowing ground; only
  thin moss patches.
- Outside the fighting floor: turquoise hot pools in cream travertine rims, warm green moss, three small geyser cones (one
  erupting softly), basalt columns, a toppled cracked golden sun-disc and a standing sun-disc portal frame (dark and inert).
- The rim: tall dark basalt walls with snow on top and dripping icicles; lower on the far left, where steam spills out. One
  entry: a basalt pass from the camera side.
- The Solar Scorpion (4.2 m) near the centre facing the camera, tail coiled high, amber orbs glowing warm but never clipping.
- Three small adventurers (1.8 m) at the entry for scale.
- One danger telegraph on the floor in front of the boss: a red boss ring (#D93A3A band, dark rim, bright inner glow, carved
  sun-ray edge), about 9 m across. It must read instantly on the dark basalt.

Camera: the game's player camera, third person, 13 m behind the middle adventurer at the north entry, about 22 degrees above the
horizon, vertical FOV about 58 degrees, looking south. The whole boss, halo and tail orb, fits in frame.

Light: winter noon (the boss wakes when the sun is high): warm key from the upper left, steam lit warm and drifting low across
the rim (never hiding the floor), snow on the rim blue-white (brightest #E8EEF2), shadows blue-violet.

Variants: A = boss centred; B = boss slightly left with the toppled sun-disc on the right rim; C = a geyser erupting behind the boss.

Checklist (PASS/FAIL per variant): in greyscale at 160 px the boss separates from the floor and the rim; the red ring reads on the
basalt; the floor is flat, calm and 24 m across with props only outside it; the boss matches the attached images; no area
darker than about 15 % except the wet basalt joints; no clipped highlights.
```

**Prompt 3: The Stillfall reveal from Cairn Point** (new; the zone 1 landmark and the ice-material reference)

```text
Make this a high-quality AAA stylised hand-painted render, 16:9 (2048x1152), Xexoria look target attached. Keep the design clean
for 3D generation: clear shapes, clear light and shadow, uncluttered background, nothing too dark. Make 3 variants as separate
generations. Label "CONCEPT" in a small corner tag; no other text.

Attach for scale and palette only (do not redesign): sources\snow\lv1\ChatGPT Image 30 ก.ย. 2569 21_51_56.png (raptor).

Camera: the game's player camera, 13 m behind a 1.8 m adventurer who has just rounded a rocky headland on a 4 m packed-snow trail,
about 22 degrees above the horizon, looking north-west into a cove about 30 m away.

In frame: a wide frozen waterfall, a curtain about 12 m tall and 12 m wide in three frozen tiers of blue-white ice columns
(translucent at thin edges, cold core #2F7FA6, never glowing) under a taller grey-blue granite cliff that runs out of the top
of the frame; a faceted ice cone at its foot; a calm snowy cove floor with three small skeletal raptors with glowing blue ribs
(tiny, mid-ground); on the right, the frozen lake's white walkable shelf with its line of tilted ice slabs; beyond, a pine
ridge under cliffs. Snow drifts against rocks, sastrugi, partly buried stones with snow rims.

Light: late-morning winter sun from the left, warm key, blue-violet shadows; the fall glows only by transmitted light.

Variants: A = morning; B = overcast with light snowfall (visibility >= 80 m); C = moonlit night (cool key, still readable).

Checklist (PASS/FAIL): the waterfall reads as one wide landmark in greyscale at 160 px; ice is faceted, not glossy; nothing darker
than about 15 % brightness except cliff shadows; the trail and cove floor are flat and open; only the CONCEPT tag.
```

**Picks:** Claude picks one variant per prompt with the Stage A checklist and lists the rejected variants with reasons.
- The Prompt 2 pick becomes the Solar Scorpion Stage C scene reference.
- The Prompt 1 pick becomes the region reference for the first Rimecrest gauntlet loop.

## 9. Budgets (64 m cells, mobile)

The device-tier plan §6.4 caps each cell at three levels:

| Level | Triangles (LOD0) | Draws |
|---|---|---|
| C0 | ≤ 120k | 40 |
| C1 | ≤ 60k | 24 |
| C2 | ≤ 40k | 16 |

Phones run the Medium preset, so they draw C1 in their own cell.

**Estimates** (layout `cells`; measured in the blockout):

| Cell | Contents | LOD0 triangles | Draws |
|---|---|---|---|
| c0_r0 | Arrival hollow, camp, west Hearthfell | about 72k | 22 |
| c1_r0 | Sunscald basin, east Hearthfell, bridge | about 98k | 30 |
| c0_r1 | Shelf, causeway and isle, shore | about 64k | 20 |
| c1_r1 | Ruin, bell tower, Sunscald Pass | about 104k | 32 |
| c0_r2 | Stillfall cove, west ridge wood | about 90k | 26 |
| c1_r2 | East ridge wood, mouth, grotto, Emberpass | about 96k | 28 |

- **The bosses and NPCs count as characters**, not cell geometry.
- **C1 is the LOD1 set** at about 50 % of each cell: 32-52k.
- **Kits reused:**
  - snow rock: Sunmeadow rocks with snow caps by normal.y;
  - snow pine: the snow variant of the trees-v4 pines;
  - ice: 4 pressure slabs, 3 blocks and 1 wall module;
  - ruin: the rime-warden kit;
  - basin: columns, terraces, pool rims and a geyser;
  - camp: the Sunmeadow camp kit in felt and snow;
  - warp: the F11/F09 masters.
- **Unique hero meshes** (≤ 6-9k each): the bell tower, the Stillfall, the Grotto Falls, the mouth arch, the sun-disc and the dais.
- **Vegetation, textures and VFX:**
  - Trees and reeds are thin instances, and impostors beyond 48 m.
  - Shared atlases; ≤ 4 MiB of unique texture per cell.
  - VFX follow the bar: ≤ 10 draws and ≤ 250 particles per effect, and at most 2 geyser bursts at once.

## 10. Checks and tools

**Commands:**

```text
python tools/levels/render_layout_plan.py planning/levels/rimecrest-v1-layout.json --base planning/levels/rimecrest-v1-base.json \
       --out planning/evidence/rimecrest-v1-layout
python tools/levels/check_monster_spawns.py --layout planning/levels/rimecrest-v1-layout.json --base planning/levels/rimecrest-v1-base.json \
       --monsters planning/levels/rimecrest-v1-monsters.json --out planning/evidence/rimecrest-v1-layout --scratch <scratch dir>
```

**Results:**

| Report | Checks | Failed | Notes |
|---|---|---|---|
| Layout | 437 | 0 | — |
| Monsters | 4,702 hard | 0 | H1-H13: bridge, paths, road safety, walkable and zone containment, water, relief/camp/prop/arena, apron, quest objects, safe points, leash polygons, the wire cap, roster validity, spacing |

- **Rows:** 27 / 36 / 38 by deploy step.
- **Step-0 chase reach** over a hazard: 0 of 27.
- **Evidence hashes:**
  - `plan.png` c57573598517…;
  - `monsters-plan.png` 9d6477088d78….

**Tool generalisation** (`tools/levels/`, no fork):
- **`--base`** now also accepts a minimal `xexoria.level-base.v1` file (props with collider radii, plus POIs).
- **Opt-in layout fields:**
  - several streams, pools and bridges;
  - polygon hazards and relief;
  - relief toe lines (`path_clearance_m`);
  - collider-edge arena keep-clear;
  - `plan_options` (warps, arenas and sightlines drawn; main-path width; paths inside the walkable hint; warps vs arenas).
- **The monster checker** reads an optional `checker_profile` and `proposed_items`:
  - arena and spawn landmark ids, the boss zone, quest objects and labels;
  - plan text;
  - day-passive/night-aggressive types (`day_passive_night_aggressive`);
  - snowfall rows;
  - no compact-v1 migration when there is no compact base.

**Sunmeadow is unchanged.** It was proven against the untouched tools (a backup copy in scratch):
- **Before 20:46:** with the inputs as they were, the generalised tools reproduced the committed evidence **byte for byte**: `plan.png` 80c75f99…, `monsters-plan.png` 015066e4…, **66/66 and 5,268/5,268**.
- **After 20:46:** `content/source/zones.json` was rewritten (not by this work). Sunmeadow rows 3, 6 and 8 have new live positions:
  - mossling (−14, 7.75);
  - thistle boar (18, 16);
  - glade wisp (0, 7.5).

  The **original** tools now report 5,268 checks with 3 H12 failures, "live xz matches zones.json". The generalised tools give identical PNGs and JSON on the same inputs. Updating the `live_xz` of those rows in `sunmeadow-v2-monsters.json` closes it. That is the Sunmeadow owner's (Claude main's) call; I did not edit Sunmeadow files.

**Jev** was not exposed in this sub-agent session. The fallback is deterministic checks plus Claude review, as llm.txt requires.

## 11. Next steps

**1. Blender blockout**, with `assets/blender/sunmeadow_v2/` as the template. Set up `assets/blender/rimecrest_v1/` from it:
- the `build_blockout.py` driver;
- `sm2_build`/`sm2_geom`/`sm2_meshes`/`sm2_relief`/`sm2_place`/`sm2_scatter`/`sm2_colliders`/`sm2_export`/`sm2_sightlines`;
- `walk_check.py`, `arena_check.py` and `review_sheet.py`.

The new site module reads `rimecrest-v1-layout.json` and `rimecrest-v1-base.json`. It adds the relief kinds:
- pressure ridge slabs; the ice cone; basalt rims, slopes and the scree;
- ruin walls; the headland and knoll polygons;
- grotto walls with the 30° camera-safe apron.

It adds the water:
- the lake: walkable shelf, open-water hazard and causeway/isle;
- the hot pools and the warm Steamrun;
- the frozen falls as unique meshes.

**Outputs:**
- per-cell GLBs, instance lists and collider JSON;
- BLENDER REVIEW renders from the four locked views, day and night, the 1.8 m witness, and the **8 sightlines in §2.2**.

**Gates:**
- the sightlines read as measured;
- `walk_check` finds no walk-area intrusion and confirms the shelf, causeway and pass are walkable while the lake and rim are not;
- `arena_check` gives collider edges ≥ 13 m;
- the grotto boom clearance is measured;
- each cell is within the C0 budget;
- the Codex root verifies the walk polygon against server movement.

**2. Forms:**
- the ruin kit and the bell tower;
- the basin kit;
- the ice kit (Stillfall and Grotto Falls from the Prompt 3 pick);
- the dais (F11) with the ring stones (F09 master, snow material);
- the camp kit in felt and snow;
- the Emberpass gate.

**3. Terrain and foliage snow recipes** (after the terrain P1→P2 lane):
- **Snow splat layers:**
  - fresh snow;
  - packed trail, a darker 0.70 value, from path distance;
  - wind-scoured crust;
  - drift tongues by slope and aspect.
- **Snow placement:**
  - snow on top faces by normal.y on every rock, ruin and log;
  - blue-violet shadow tint, never above 235/255.
- **Ice:**
  - the shelf (scratched, matte);
  - thin ice (grey, cracked, dark water showing);
  - the pressure slabs and frozen falls (faceted, thin-edge translucency, cold core).
- **Basin:** wet basalt with a roughness gradient by distance to the pools, cream travertine, warm moss, and mineral staining only outside the arena.
- **Foliage:**
  - snow-laden pine boughs by a normal.y mask on the trees-v4 pines;
  - frozen reeds, frost shrubs and hot-spring moss, all thin-instanced with mobile density factors (×0.72 / ×0.85);
  - snowfall weather on the shared weather slot.

**4. Light pass:** noon, dusk and night as in the layout's `lighting` block; fog from 100 m, and the tower keeps 0.15 or more luma contrast.

**5. Monsters:**
- F13-F16 → QA → Tripo cards 09-12 (owner ceiling);
- the Blender cleaver and the Warden variant;
- the Solar Scorpion Stage C (decimate to 22k, bakes, clips to §5 timings);
- Mirun's palette swap.

**6. Integration (Codex root):**
- S9 zone transfer (A35) and a `zones.json` zone for `rimecrest_snow`;
- enemies kinds 8-13; the proposed items after the economy review;
- the warp states;
- S1-S5 for steps 1-2.

## 12. Open questions for the owner

1. **The apprentice's name:** "Mirun" is a working name.
2. **The golem's crown spikes:** they recall a famous lich-king look. The zero-cost alternative in the F16 round is a rounded rime brow.
3. **The 9 proposed item ids and stats** need the economy review.
4. **The lava region's map id:** I used the working name "Ashveil Caldera"; the id is still to be decided.
5. **The Sunmeadow `live_xz` refresh** for rows 3, 6 and 8 (§10).
