# Asset production board (2026-10-02)

Date: 2026-10-02 · Producer and art director: Claude (C-PRODUCER sub-agent; planning and review only, no apps, browsers or spending) · Status: ACTIVE BOARD · Data: `planning/assets/asset-tracker.json` (73 rows) · Evidence: `planning/evidence/asset-review-20261002/` · Drafts: `planning/assets/froggy-drafts/` · Tripo cards: `planning/assets/tripo-cards/` · Stage C plans: `planning/assets/stage-c/`

> **สรุปภาษาไทย (สำหรับเจ้าของ)**
>
> **ตรวจอะไรไปบ้าง:** ภาพลาวา 4 ภาพ, ภาพหิมะ 18 ภาพ (มอนสเตอร์ 4 ตัวกับอาวุธ 1 ชิ้น), โฟลเดอร์ boss (Solar Scorpion กับวัว), จอยสติ๊ก UI 8 แบบ และภาพอ้างอิงอื่นอีก 3 ภาพ ทุกชุดที่เป็นภาพ 4 ด้านผ่านเครื่องตรวจ `turnaround_qa.py` แล้ว และวัดความสว่าง ความมืด สี และความรกของทุกภาพเทียบกับภาพเป้าหมาย
>
> **ผลตามที่คุณตัดสิน (แมพหิมะ Rimecrest):**
> - มอนสเตอร์หิมะทั้ง 4 ตัว **เก็บไว้ทั้งหมด** แต่ภาพ 4 ด้านยังใช้กับ Tripo ไม่ได้ทั้ง 4 ชุด (ขาบาง ภาพแต่ละด้านไม่ตรงกัน ภาพข้างของ golem เป็นมุมเฉียง) ผมร่างคำสั่งให้ froggy ทำภาพ 4 ด้านใหม่ **โดยไม่เปลี่ยนดีไซน์** ไว้แล้ว (F13-F16)
> - ในโฟลเดอร์ snow **ไม่มีภาพแมพเลย** มีแต่ภาพมอนสเตอร์ ถ้าคุณมีภาพแมพหิมะ ให้วางไว้ที่ `sources\snow\map\` ระหว่างนี้ใช้ F10 สร้าง key art ของ Rimecrest
> - บอส **Solar Scorpion** สร้างเสร็จแล้ว (รูปทรง, UV, texture 8K, rig, 7 ท่า) **ไม่ต้องใช้เครดิตเพิ่ม** ที่เหลือคือ Stage C: ลดโพลีจาก 51k ให้เหลือไม่เกิน 25k, bake normal/AO ให้มือถือ, ทำท่าให้ตรงกับ server, export แล้วตรวจในเกม (task list พร้อม)
> - **วัวเป็น NPC** แต่ตอนนี้หนักกว่างบ NPC 6.75 เท่า (54k เทียบกับ 8k) และยังไม่มี normal map ต้องเลือกก่อนว่าจะอยู่ที่ Rimecrest, ในเมือง (ตอนนี้ลงทะเบียนเป็น Ruun) หรือทั้งสองที่
>
> **ส่วนอื่น:**
> - **ลาวา:** ภาพแมพต้องทำใหม่: มืดเกินไป (ความสว่างเฉลี่ย 0.32 เทียบกับเป้าหมาย 0.50) เป็นสไตล์ภาพถ่าย มีลวดลายคล้าย God of War และทางเดินแคบเดินไม่ได้ golem ใช้เป็นแนวทางของบอสลาวาได้แต่ต้องทำใหม่ งูนาค (naga) ทำใหม่ภายหลัง ส่วนอัศวินวงแหวนตัดทิ้ง (คล้าย Elden Ring)
> - **UI:** ใช้ b13 Celestial Rune เป็นค่าเริ่มต้น และ a04 Wildwood Jade เป็นแบบเสริม a10 ให้แก้เฉพาะปุ่มกลางถ้าต้องการแบบที่ 3 อีก 5 แบบตัดทิ้ง
> - ภาพ Prontera (มีชื่อและมอนสเตอร์ของ Ragnarok) และภาพหน้าจอเกมอื่น **ห้ามใช้เป็นต้นแบบ**
>
> **Warp และแมพใหม่:**
> - เพิ่ม Rimecrest (แมพแรก) และ Southreach (Lv 10) ในบอร์ดแล้ว พร้อม brief ของแผนผัง มอนสเตอร์แต่ละช่วงเลเวล สนามบอส NPC และจุด warp ไป-กลับ
> - ของประกอบ warp ทั้งหมดทำใน Blender (วงพอร์ทัล 3 สถานะ, ประตูใต้แบบปิดและแบบเปิด, แท่นที่จุดเกิด, พอร์ทัลในเมือง)
> - **พบจุดทับกัน:** วงพอร์ทัล (รัศมี 2.5 m) ทับแท่นบูชา 0.53 m และทับขอบทางเดินราว 1.4 m ต้องให้ Claude (ผู้ดูแลแผนผัง) ตัดสินใจแก้
>
> **Prop ของ Sunmeadow:** ใช้ Tripo ชิ้นเดียว คือหินวงกลม 1 แบบที่ใช้ซ้ำราว 11 จุด (145 เครดิต) ที่เหลือทำใน Blender หรือใช้ชุดฟรี CC0 ไม่เสียเครดิต
>
> **เครดิต:**
> - รอบแรก 600: ฮีโร่ 01/04/06 (435) + Mossling (145) = **580 เหลือ 20** ถ้าต้องสร้างรูปทรงใหม่แม้แค่ครั้งเดียวจะเกินเพดาน จึงต้องเริ่มที่ฮีโร่ 01 ก่อน ดูผล แล้วค่อยทำตัวถัดไป
> - งานบอส มอนสเตอร์ และ prop ที่เหลือ **ยังไม่มีเพดานที่อนุมัติ** ผมเสนอไว้ 3 ก้อน: Sunmeadow 705, Rimecrest 550 และบอส 435
>
> **สิ่งที่คุณต้องตัดสินใจ:**
> 1. อนุมัติเพดานเครดิตรอบถัดไป
> 2. เลือกที่อยู่ของวัว
> 3. ส่งภาพแมพหิมะ (ถ้ามี)
> 4. ชื่อ "Rimecrest" ใกล้กับ "Frostveil Pass" ของ Lumivara ควรเปลี่ยนชื่อที่แสดงในเกมหรือไม่
> 5. เก็บหรือทิ้ง 2 แมพที่ผมเสนอ (Whisperwood และ Cloudshoal Isles)

## 0. How to read this board

- **Stage A:** a 16:9 reference, 3 variants, pick one.
- **Stage B:** a 4-view set, then `tools/art/turnaround_qa.py`, then the design review, then Tripo (or the Blender/CC0 build).
- **Stage C:** the in-engine gauntlet loop (`docs/plans/2026-10-02-reference-gauntlet-loop.md`).
- **Status values:** KEEP is an owner-approved design (snow pack, Solar Scorpion, bovine NPC); PASS is a Claude-approved stage; `built` means a Tripo model already exists; `n/a` means the stage does not apply to the route (Blender and CC0 props skip Stage B).
- **Credits:** 2026-10-02 Studio prices (credit guard section 5.5). "Worst" adds the one allowed geometry retry per asset.
- **Owner decisions applied:**
  - 19:50: the snow material is KEEP; the Solar Scorpion is the snow-map boss; the bovine shaman is a map NPC.
  - 20:05: warps (the Windstone portal leads to `rimecrest_snow`, the first new map; the south gate leads to `southreach_field`).
- **Jev:** UNAVAILABLE in this sub-agent session (no Jev integration exposed). Fallback: deterministic measurements plus Claude review, as llm.txt requires.

## 1. Board counts per stage

| Stage | Done or decided | In progress | Needs a fix | Not started | Dropped | Not applicable |
|---|---|---|---|---|---|---|
| A (reference) | 18 PASS + 11 KEEP | 6 | 4 REGEN | 17 | 6 | 11 |
| B (4-view / build input) | 4 PASS + 4 built | 1 in progress + 2 awaiting review | 7 REGEN | 14 | — | 41 |
| C (in engine) | 0 done | 4 | 1 blocked | 62 | — | 6 |

By class: hero 6, hero prop 13, monster 14, boss 9, prop 11, region-map 10, NPC 1, UI 9 (total 73). Four reviewed inputs that are not assets are listed under `references` in the JSON: the Ragnarok-style mock, a third-party phone screenshot, the external volcanic sheet and the scorpion's optional staff.

## 2. Verdicts on what is on disk

Evidence per item: `planning/evidence/asset-review-20261002/<item>/verdict.json`, plus `value-read.png` and `metrics.json`, and `turnaround-qa/` for every turnaround set. Index: `verdicts-index.json`. Baselines: the look target (mean luma 0.499, contrast 0.583, 4.0 % near-black) and the QA-PASS hero 01 front (subject mean 0.454, 8.9 % near-black).

### 2.1 Maps

| Item | Verdict | Why (measured) |
|---|---|---|
| Lava key art `lava\...21_11_39.png` | **REGEN** | Photoreal grim-dark, not hand-painted. Too dark: mean luma 0.323 vs 0.499; 18.8 % near-black vs 4.0 %. No warm key. God of War motifs (chained titan hands, carved giant face, caped spear hero). A narrow causeway over lava is unplayable on a flat walk plane, and lava beside the path hides telegraphs. Clutter is NOT the issue (edge energy 0.051 vs the target's 0.080); haze is. Keep the one-route-to-one-gate composition. Fix in F18. |
| Snow map images | **KEEP (owner) — not on disk** | `snow\` holds 18 creature/weapon PNGs and no map image; the historical froggy Snow v1/v2 renders are not on disk either. F10 makes the Rimecrest key art; the old Snow v2 review defects (flat over-bright snow, black stepping stones, plastic ice, 901k triangles) are written into F10 as fixes. |
| Ragnarok-style HUD mock (Sep 23) | **DROP as input** | Names Prontera, Poring and Lunatic and shows RO monsters: IP. Mood only; no derived image written. |
| Third-party phone screenshot (Sep 27) | **DROP as input** | Another game's capture. Mood only. |
| External volcanic sheet (`Downloads\Other-Projects\828712242...`) | **Reference only** | Already ruled direction-only. Lessons folded into F18: lava river as the value anchor, mid-value ash ground, cool-violet shadows, no bloom wash. |

### 2.2 Bosses and the NPC

| Item | Verdict | Why |
|---|---|---|
| Solar Scorpion (`boss\` images + `tripo-p2-output\`) | **KEEP: Rimecrest boss** (owner; Stage A/B done) | Built: 51,376 triangles (2x the 25k boss ceiling), Smart UV 73.1 %, 8K delit texture, PBR, 57-bone rig (46 deform), 7 clips, glTF 0/0, NullEngine PASS; no game camera, no KTX2, emission mask unapplied, walk 0.457 m/s. Retro QA of its views: REGEN (LR IoU 0.659), record only. Gold on snow is the region's strongest figure-ground contrast: frame it as a sun-forged guardian frozen in a glacier shrine. Stage C list: `planning/assets/stage-c/solar-scorpion-rimecrest-boss.md`. |
| `tripo-p2-output\` folder | finding | 7,677 files, of which 7,498 are `runtime-rig-v1\tools\node_modules` (Babylon, gltf-transform, sharp, meshoptimizer, gltf-validator). Only 110 images (75 motion frames, review renders, Tripo textures, Smart UV layout), all of the scorpion. |
| Bovine shaman (`boss\bovine-shaman\`, 20 files, 12 images) | **KEEP: map NPC** (owner) | Reads well (horns, crook, robe); mean luma 0.396, 10.9 % near-black. Built: 54,011 triangles (6.75x the 8k NPC budget), base colour only, Rigify 32 joints, Idle/Talk exist. Originality note: bovine elder shaman overlaps the WoW tauren archetype; the yak mane, Himalayan textiles and prayer beads differentiate it, so keep totems, feathers and war paint out. Registered today as the city elder Ruun: placement decision needed. Plan: `planning/assets/stage-c/bovine-shaman-npc.md`. |
| Lava obsidian golem (22_29_22) | **REGEN → lava boss direction** | Near-black on dark: subject luma 0.203 (hero 01: 0.454), 44.7 % near-black; even the QA segmenter could not separate the silhouette, and players could not against basalt. Four arms, cloth tatters. Keep the lava-veined greatblade and obsidian plates. F19 "the Emberwright". |
| Lava serpent priestess (23_06_24) | **REGEN (backlog)** | Luma 0.186, 58.7 % near-black; hair-thin chains, tatters, a thin scythe; pharaonic styling duplicates the Solar Scorpion's language. |
| Lava halo knight (23_06_45) | **DROP** | FromSoftware look-alike (elongated knight, crescent halo, shredded cloak), a sliver at distance, dark, no lava identity. |

### 2.3 Rimecrest pack: snow monsters by level band (owner KEEP; Stage B fixes only)

| Band | Monster | Stage A | Stage B (`turnaround_qa.py`) | Pipeline fixes (froggy draft) | Route, credits |
|---|---|---|---|---|---|
| lv1 | Bone tick (8 legs, ice body) | KEEP | REGEN: thin parts 2.6-6.1 %, LR IoU 0.717, FB 0.838, 1254 px canvases | Thicken legs/claws to 3 % of the frame, close the lattice holes, one leg stance in all views, 2048² white (F13) | Tripo, 135 |
| lv1 | Bone raptor | KEEP | REGEN: heights differ 17.3 %, baseline 9.4 %, FB IoU 0.405, LR IoU 0.649 | One camera distance, same stance front/back, mirrored profiles, closed ice core behind the ribs (F14) | Tripo, 135 |
| lv2 | Bone wraith | KEEP | REGEN: LR width 21.6 %, LR IoU 0.790 | A-pose with arms at the sides in every view, sturdier limbs and fewer, bigger shards (F15) | Tripo, 135 |
| lv3 | Rime golem (elite) | KEEP | REGEN: LR width 12.8 %, FB IoU 0.876; side views are 3/4 (tool passes them, design review catches it) | True profiles, one hem, declared pauldron asymmetry, hands empty (F16) | Tripo, 145 |
| lv3 | Rime cleaver | KEEP | QA PASS (single image) | Build in Blender (hard-surface blade) | Blender, 0 |
| boss | Solar Scorpion | KEEP | built | Stage C list | 0 (35 spent earlier) |
| NPC | Bovine shaman | KEEP | built | NPC Stage C plan | 0 (100 spent earlier) |

Non-blocking notes (owner accepted the designs):
- The bone + frost-blue glow constructs echo an undead "Scourge" read.
- The lv3 golem's spiked crown and skull pauldron recall the Lich King. A zero-cost mitigation, only with the owner's OK, is a rounded rime brow instead of the crown spikes in the F16 round.
- Gameplay: bone-white shells merge with snow above about 0.8 luma. Stage C must check greyscale separation on snow at 13 m, and F10 asks for blue-violet snow shadows.

### 2.4 UI controls (`froggy\ui-controls-20261002\`, 8 joystick atlases)

Proofs at the manifest's CSS sizes on dark, light and meadow backgrounds (`ui-proof-1x.png`), plus greyscale sheets. The key number is the thumb-vs-well luma delta: a thumb with no value separation disappears when centred.

| Style | Verdict | Reason |
|---|---|---|
| b13 Celestial Rune | **KEEP (default)** | Best separation 0.196; blue-slate and silver match the palette and read on snow |
| a04 Wildwood Jade | **KEEP (alternate)** | Gold-bronze family; delta 0.109 |
| a10 Dragonbone | REGEN (thumb only, optional) | Strong frame, but delta 0.017 |
| a02 Frostglass | DROP | Delta 0.001 (invisible thumb), redundant |
| a05 Astral Orbit | DROP | Orbit lines thin to 1-2 px at 1x; delta 0.042 |
| a08 Dawn Petal | DROP | Washes out on light backgrounds; off identity |
| b04 Floating Thumbstick | DROP | Invisible on light and snow backgrounds |
| b09 Crystal Silver | DROP | Redundant with b13 |

Shared fixes for the UI lane: no pressed/disabled art (use CSS states for v1); alpha residue up to 4/255 (clean at import); atlases are not mip-padded (repack with extrusion).

## 3. Regions and warps

### 3.1 `rimecrest_snow`, the first new map (P1)

Reached through `warp_windstone_portal` (Sunmeadow stone circle (0,-68), trigger r 2.5, unlocked by the first Galehorn kill per character; states dormant, awakening, active). Return: `windstone_return` leads to the Sunmeadow circle at (2,-72). This is a producer brief for the map lane; Claude owns the layout JSON.

| Part | Brief |
|---|---|
| Size and rules | Compact, about 2 x 2 to 2 x 3 cells of 64 m; flat Y=0 walk plane with relief only as the frame (like Sunmeadow); trails at least 4 m wide; one landmark per space, a readable route, a way back |
| Arrival / return | `windstone_arrival` = `windstone_return`: a 5 m carved dais with a rune ring and 3 snow-capped ring stones (reuse of the Tripo master) in a sheltered hollow; no spawns or aggro discs within 25 m; first sightline to the camp smoke and the far sun-shrine glint (F10, F11) |
| NPC hub | The bovine shaman's yak-herder camp 20-30 m from the arrival: hide tent, campfire (warm light = safe), drying rack, pack baskets, cloth wind-streamers echoing the windstones |
| lv1 band | Open rolling snowfield: bone ticks and bone raptors; drifts against rocks, packed trails |
| Crossing | A frozen river with a timber-and-stone bridge (at least 4 m); faceted, translucent ice |
| lv2 band | Rune-stone ridge with half-buried carved stones and broken walls: bone wraiths |
| lv3 band | Glacier edge with crystalline ice boulders and a frozen waterfall (the far landmark): rime golems |
| Boss arena | The frozen sun-shrine: flat sandstone paving half-buried in packed snow, r 14 m arena with a 15 m keep-clear for colliding props, broken sun-disc pillars on the rim only, one entry; calm floor so red boss rings read (F12); Solar Scorpion |
| Future hook | The Halls of the Frost Jarl longhall on the skyline (dungeon entrance later) |
| Levels (proposal) | Galehorn is Lv 10 and Southreach opens at Lv 10, so the bands could be about L12-15 (lv1), L16-19 (lv2), L20-23 (lv3), with the boss for groups; a systems decision |
| Light | Low warm winter sun, blue-violet fill and shadows, snow never above about 235/255, light blue haze from 100 m; night: moon key, warm camp light, the boss's amber orbs |
| Name check | "Rimecrest" is close to Lumivara's "Frostveil Pass": consider another display name and keep the ID |

### 3.2 `southreach_field`, Lv 10 (P2)

Reached through `warp_sunmeadow_south` (south gate (0,-101), trigger r 3.0; unlocked at Lv 10 + "Signal on the Ridge"; locked look: barred gate with "Road closed: Lv 10"). Arrival `north_gate_in`; return `north_gate_out` leads to Sunmeadow `south_gate_in` (0,-97).

| Part | Brief |
|---|---|
| Identity | Older, wider and golden: late-summer harvest-gold fields with blue and violet wildflowers, dry-stone walls, windbreak tree lines; the next chapter of Sunmeadow, not a copy |
| Arrival | The open north gate in a short palisade, a lantern post and a waystation (bench, notice board): the NPC hub (a ridge signal-keeper, proposal) |
| Route | A 4 m+ cart road south across the fields to a wide shallow ford with stepping stones and a footbridge |
| Landmark | A long ridge crowned by a stone signal-beacon tower; beside it a flat 24 m stone platform ringed by short stones: the future boss site |
| Bands (proposal) | Lv 10-13 near the gate (variants of Sunmeadow rigs with new albedos, route V, 0 Tripo credits), Lv 14-17 mid (1 new monster), Lv 18-20 far (1 new elite), field boss at the beacon (design after F17) |
| Avoid | Westfall's harvest golems and scarecrows, Mondstadt windmills, Prontera fields |

### 3.3 Other regions

| Region | State | Next |
|---|---|---|
| Sunmeadow v2 | Layout 66/66, blockout pass 5 done, F8 arena key art in flight | Forms pass C-P1-FORM |
| Lava (working name Ashveil Caldera) | Key art REGEN | F18, then F19 boss |
| Whisperwood (proposal) | Overworld for the Whisperwood Hollow dungeon; the cheapest next region because it reuses the mature tree, grass, water and moss-stone pipelines | F22 after the owner keeps it |
| Cloudshoal Isles (proposal) | Makes the look target's floating isles visitable; needs flat broad tops and railed bridges (planar movement) | F23 after the owner keeps it |
| Dungeons (Sunken Temple, Whisperwood Hollow, Gloamcrystal, Frost Jarl) | froggy round-1 packs A-D approved on 2026-10-01 but **not on disk** | Ask froggy to deliver the zips before any new boss prompt |

### 3.4 Warp props (all Blender; no Tripo pick)

| Prop | States | Route and why |
|---|---|---|
| Windstone portal ring (Sunmeadow) | dormant (faint runes at night only), awakening (Galehorn engaged), active (after the first defeat), plus the ground ring when unlocked | Blender flush inlay with an emissive channel per state, plus a VFX swirl. Flush ground geometry and state-driven materials are not Tripo work. **Layout flag:** the r 2.5 trigger overlaps the altar platform by 0.53 m and the trail's west edge by about 1.4 m; suggest r 2.0 or a 1 m east offset (map lane) |
| Rimecrest arrival / return platform | arrival and return (one ring) | Blender modular dais plus 3 ring stones from the Tripo master in a snow material: no new job; F11 sets the design |
| Sunmeadow south gate | barred (crossbeam, iron bands, "Road closed: Lv 10" via decal/UI) and open (doors swung) | Blender timber doors and palisade: planks and straps are hard-surface |
| Southreach north gate | arrival / return | Blender, mirroring the Sunmeadow gate (F17 sets the look) |
| City portal dais (hub) | destination list of discovered warps | Keep the dais, rings and pylons; replace the solid light column (fresnel or `fx_portal_beam`); the list is a Codex UI task |

## 4. The board

### Heroes and hero weapons (12)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `hero-01-swordsman` | hero | global | PASS | PASS | not_started | Tripo | hero | owner (Tripo run; R-TRIPO queued) | 145 / 245 | Run geometry first (100), Claude inspects, then Smart UV + 4K texture + PBR per the job card |
| `hero-02-mage` | hero | global | PASS | built | in_progress | built (Tripo pilot, earlier) | hero | Claude (C-H2) | 0 (spent earlier 175) | C-H2 repairs: LOD 12k/6k/2.5k, staff to the right-hand socket, sleeve/waist fix, run.001 hip offset, add attack/dodge/death, crown-height scale |
| `hero-03-archer` | hero | global | PASS | REGEN | not_started | Tripo | hero | froggy (round 2 in flight) | 145 / 245 | Claude QA + design review on delivery (tail straight, quiver removed, arms 45 degrees) |
| `hero-04-acolyte` | hero | global | PASS | PASS | not_started | Tripo | hero | owner (Tripo run) | 145 / 245 | Run after hero 01 geometry is inspected (see the stage-1 rule in the board) |
| `hero-05-thief` | hero | global | PASS | REGEN | not_started | Tripo | hero | froggy (round 2 in flight) | 145 / 245 | Claude QA + design review on delivery (cape sides match front/back) |
| `hero-06-merchant` | hero | global | PASS | PASS | not_started | Tripo | hero | owner (Tripo run) | 145 / 245 | Run after hero 01 geometry is inspected |
| `weapon-01-sword` | hero prop | global | PASS | awaiting_review | not_started | Tripo (single image) | weapon | Claude (--prep + design review) | 135 / 235 | Run --prep with the design review; job after hero 01 passes review |
| `weapon-02-staff` | hero prop | global | PASS | built | in_progress | built (Tripo, earlier) | weapon | Claude (C-H2) | 0 | Attach to the right-hand socket in the C-H2 repairs |
| `weapon-03-bow` | hero prop | global | PASS | n/a | not_started | Blender | weapon | Claude | 0 | Blender build (limbs + string) after hero 03 passes |
| `weapon-04-staff` | hero prop | global | PASS | n/a | not_started | Blender | weapon | Claude | 0 | Blender build (shaft too thin for Tripo) |
| `weapon-05-dagger` | hero prop | global | PASS | REGEN | not_started | Tripo (single image) or Blender | dagger | Claude (crop + QA) | 135 / 235 | Crop one dagger (framing only), re-run QA, decide Tripo vs Blender |
| `weapon-06-hammer` | hero prop | global | PASS | awaiting_review | not_started | Tripo (single image) | weapon | Claude (--prep + design review) | 135 / 235 | Run --prep with the design review; job after hero 06 passes review |

### Sunmeadow monsters and boss (7)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `mossling` | monster | sunmeadow | PASS | in_progress | blocked | Tripo | regular | froggy (F2/F6 4-view) | 145 / 245 | QA + design review on delivery; then card 01 |
| `puddlekin` | monster | sunmeadow | in_progress | n/a | not_started | Blender | regular | froggy (F2) | 0 | Claude reviews the F2 concept; Blender build (deformation + water material) |
| `thistle-boar` | monster | sunmeadow | in_progress | not_started | not_started | Tripo | regular | froggy (F2/F6) | 135 / 235 | QA + design review on delivery; card 06 |
| `glade-wisp` | monster | sunmeadow | in_progress | n/a | not_started | Blender + FX | regular | froggy (F2) | 0 | Claude reviews the F2 concept; Blender build + VFX lane |
| `brookclaw` | monster | sunmeadow | not_started | not_started | not_started | Tripo | regular | Claude (send roster section 9.5 as an F2 addendum) | 135 / 235 | Send the copy-paste prompt from the roster doc section 9.5; it is not part of F2 |
| `turfback-matriarch` | monster | sunmeadow | in_progress | not_started | not_started | Tripo | elite | froggy (F2/F6) | 145 / 245 | QA + design review on delivery; card 08 |
| `galehorn` | boss | sunmeadow | in_progress | not_started | not_started | Tripo body + Blender phase parts | boss | froggy (F8 key art x3) | 145 / 245 | Claude picks an F8 variant, then sends the F6 block for the 4-view set; card 02 |

### Sunmeadow props (12)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `windstone-ring-stone` | hero prop | sunmeadow (+ warp network) | not_started | not_started | not_started | Tripo (justified) | hero prop | Claude (send F09) | 145 / 245 | Send F09 Part 1; pick; F09 Part 2; QA --kind prop; card 03 |
| `windstone-altar` | hero prop | sunmeadow | n/a | n/a | not_started | Blender | hero prop | Claude (C-P1-FORM) | 0 | Blender: flush walkable platform matching the collider; carved block from the forge stone + groove height map; reuse the ring-stone material |
| `windmarks` | hero prop | sunmeadow | n/a | n/a | not_started | reuse ring-stone master + Blender streamers | hero prop | Claude | 0 | Scale the ring-stone master to 0.35-0.45, add cloth streamers, keep the ring/crystal material-swap hooks (actors.ts) |
| `windstone-shrine-steps` | prop | sunmeadow | n/a | n/a | not_started | CC0 kit | prop | Claude | 0 | KEEP the shrine; replace the slab row with a worn dirt spur or 3-4 jittered Quaternius RockPath_Round_Small stones |
| `broken-cart` | prop | sunmeadow | n/a | n/a | not_started | Blender + CC0 kit | prop | Claude | 0 | Blender recipe from the Quaternius cart (tilted bed, one wheel off) at (13,-73); spill: Crate_Wooden x2 (one open), Bag, Barrel rolled 2 m |
| `camp-kit` | prop | sunmeadow | n/a | n/a | not_started | CC0 kit + Blender recipes | prop | Claude (C-P1-FORM) | 0 | Quaternius pieces placed per prop audit section 3.5; recipes for campfire, log seats, haystacks (5 m from the fire) and palisade; about 21k triangles |
| `camp-tent` | prop | sunmeadow | n/a | n/a | not_started | Blender | prop | Claude | 0 | Recipe: A-frame 3 x 2.4 x 2.2 m, two poles, ridge, open flap facing the fire, 4 guy ropes and stakes; 600-1,200 triangles |
| `gate-signpost` | prop | sunmeadow | n/a | n/a | not_started | Blender (reuse prop_wayfinder_sign_01) | prop | Claude | 0 | Reuse the wayfarer sign model; Thai/English text through decal/UI, never baked geometry |
| `lookout-watchtower` | prop | sunmeadow | n/a | n/a | not_started | Blender + CC0 kit | prop | Claude | 0 | Recipe: 4 posts 6 m, platform, ladder, roof (2-3k) with Crate_Wooden and Torch_Metal; visual only at Y=0 |
| `painted-rock-clusters` | prop | sunmeadow | n/a | n/a | not_started | CC0 kit | prop | Claude | 0 | Quaternius Rock_Medium anchor + 2-3 Pebble + Flower/Clover, asymmetric, outside spawn rows |
| `glade-edge-dressing` | prop | sunmeadow | n/a | n/a | not_started | CC0 kit | prop | Claude | 0 | Stylized Nature MegaKit pieces per prop audit section 3.6; mushrooms at 11.5-13 m from the arena centre |
| `sella-wayfarer-kit` | prop | sunmeadow | KEEP | n/a | not_started | existing models | prop | Claude | 0 | Move for v2: west banner to (-4.5,-21.0), lantern to (5.1,-14.3); make one planter part of a Sella cluster |

### Warp props (5)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `warp-windstone-portal-ring` | hero prop | sunmeadow | not_started | n/a | not_started | Blender + VFX | hero prop | Claude (layout fix) + VFX lane | 0 | Blender flush rune-ring inlay with an emissive channel driven per state; VFX swirl and unlock ground ring; F11 Part 2 gives the state sheet |
| `warp-rimecrest-arrival-platform` | hero prop | rimecrest_snow | not_started | n/a | not_started | Blender + reuse of the ring-stone master | hero prop | Claude (send F11) | 0 | F11 Part 1 picks the design; Blender modular dais (5 m, two 0.15 m steps) + 3 snow-capped ring stones (material variant) |
| `warp-sunmeadow-south-gate` | prop | sunmeadow | not_started | n/a | not_started | Blender | prop | Claude | 0 | Timber double doors + lintel between the posts (+-6.4,-99), 2-4 palisade segments; barred: crossbeam, iron bands, sign 'Road closed: Lv 10' via decal/UI (Thai/English); open: doors swung (two meshes or node animation) |
| `warp-southreach-north-gate` | prop | southreach_field | not_started | n/a | not_started | Blender | prop | Claude | 0 | Mirror of the Sunmeadow gate from the far side + waystation (bench, notice board, lantern) per F17 |
| `warp-city-portal-dais` | hero prop | city | KEEP | n/a | not_started | existing + Blender/VFX fix | hero prop | Claude + VFX lane + Codex UI | 0 | Keep the dais, rings and pylons; replace the solid cyan light column (additive fresnel or fx_portal_beam); destination list of discovered warps in the UI |

### Region maps and dungeons (10)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `region-sunmeadow-v2` | region-map | sunmeadow | in_progress | n/a | in_progress | Blender (map lane) | region | Claude (map lane) + froggy (F8 arena key art) | 0 | F8 arena key art becomes the Stage C scene reference; forms pass C-P1-FORM next |
| `region-rimecrest-snow` | region-map | rimecrest_snow | not_started | n/a | not_started | Blender (map lane) | region | Claude (send F10, F11, F12) + map lane (layout JSON) | 0 | Send F10 (region) and F12 (boss arena); write the Rimecrest layout JSON from the brief in the board |
| `region-southreach-field` | region-map | southreach_field | not_started | n/a | not_started | Blender (map lane) | region | Claude (send F17) + map lane | 0 | Send F17; roster and boss design to follow (variants of Sunmeadow rigs proposed) |
| `region-lava` | region-map | lava | REGEN | n/a | not_started | Blender (map lane) | region | Claude (send F18) | 0 | Send F18 (lava key art regeneration) |
| `region-whisperwood` | region-map | whisperwood (proposal) | not_started | n/a | not_started | Blender (map lane) | region | owner (keep or drop) | 0 | Send F22 only after F10/F17/F18 are picked |
| `region-cloudshoal-isles` | region-map | cloudshoal (proposal) | not_started | n/a | not_started | Blender (map lane) | region | owner (keep or drop) | 0 | Send F23 only after F10/F17/F18 are picked; needs flat broad tops and railed bridges |
| `dungeon-sunken-temple` | region-map | dungeon | PASS | n/a | in_progress | Blender kits (forge) | region | Claude | 0 | D3 kit/materials after D1; ask froggy for the round-1 Pack A zip (approved, not on disk) |
| `dungeon-whisperwood-hollow` | region-map | dungeon | PASS | n/a | not_started | Blender kits | region | froggy (deliver Pack B zip) | 0 | Deliver the round-1 Pack B zip to sources\froggy\dungeons-20261001\ |
| `dungeon-gloamcrystal-caverns` | region-map | dungeon | PASS | n/a | not_started | Blender kits | region | froggy (deliver Pack C zip) | 0 | Deliver the round-1 Pack C zip |
| `dungeon-halls-of-the-frost-jarl` | region-map | dungeon | PASS | n/a | not_started | Blender kits | region | froggy (deliver Pack D zip) | 0 | Deliver the round-1 Pack D zip; the entrance can sit on Rimecrest's skyline |

### Rimecrest pack (monsters by level band, boss, NPC) (7)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `boss-solar-scorpion` | boss | rimecrest_snow | KEEP | built | not_started | built (Tripo, owner) + Blender Stage C | boss | Claude (Stage C task list) | 0 (spent earlier 35) | Needs the Rimecrest arena layout, the server boss row and the F12 arena art, then the Stage C task list |
| `snow-lv1-bone-tick` | monster | rimecrest_snow (lv1) | KEEP | REGEN | not_started | Tripo | regular | Claude (send F13) | 135 / 235 | Send F13 (F6 4-view, design unchanged); QA + design review; then the card |
| `snow-lv1-bone-raptor` | monster | rimecrest_snow (lv1) | KEEP | REGEN | not_started | Tripo | regular | Claude (send F14) | 135 / 235 | Send F14 (F6 4-view, design unchanged); QA + design review; then the card |
| `snow-lv2-bone-wraith` | monster | rimecrest_snow (lv2) | KEEP | REGEN | not_started | Tripo | regular | Claude (send F15) | 135 / 235 | Send F15 (F6 4-view, design unchanged); QA + design review; then the card |
| `snow-lv3-rime-golem` | monster | rimecrest_snow (lv3) | KEEP | REGEN | not_started | Tripo | elite | Claude (send F16) | 145 / 245 | Send F16 (F6 4-view, design unchanged); QA + design review; then the card |
| `snow-lv3-rime-cleaver` | hero prop | rimecrest_snow (lv3) | KEEP | PASS | not_started | Blender (recommended) | weapon | Claude | 0 | Blender build with the golem (hard-surface blade, monster weapon) |
| `npc-bovine-shaman` | NPC | rimecrest_snow (owner) / city (today) | KEEP | built | not_started | built (Tripo, earlier) + Blender Stage C | npc | owner/Claude (placement), then Claude | 0 (spent earlier 100) | Decide placement; then the NPC Stage C plan |

### Other bosses (one per region or dungeon) (7)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `boss-guardian-of-aurel` | boss | dungeon: sunken temple | not_started | not_started | not_started | Tripo body + Blender shield/phase parts | boss | Claude (send F20; ask for the Pack A zip) | 145 / 245 | Send F20; pick; F6 4-view; card 16 |
| `boss-lava-emberwright` | boss | lava | REGEN | not_started | not_started | Tripo body + Blender blade/phase parts | boss | Claude (send F19 after F18) | 145 / 245 | Send F19 after F18 is picked; card 17 |
| `boss-frost-jarl` | boss | dungeon: frost jarl | not_started | not_started | not_started | Tripo body + Blender cleaver/phase parts | boss | Claude (send F21; ask for the Pack D zip) | 145 / 245 | Send F21; pick; F6 4-view; card 18 |
| `boss-whisperwood-treant` | boss | dungeon: whisperwood hollow | not_started | not_started | not_started | Tripo | boss | froggy (Pack B zip first) | 145 / 245 | Review Pack B before any new prompt |
| `boss-gloamcrystal-wyrm` | boss | dungeon: gloamcrystal caverns | not_started | not_started | not_started | Tripo + Blender crystals | boss | froggy (Pack C zip first) | 145 / 245 | Review Pack C before any new prompt |
| `boss-southreach` | boss | southreach_field | not_started | not_started | not_started | TBD | boss | owner + Claude (design) | 0 | Design after F17 is picked (boss site: the beacon-ridge platform) |
| `boss-cloudshoal` | boss | cloudshoal (proposal) | not_started | not_started | not_started | TBD | boss | owner | 0 | Only if the region is kept |

### Lava monsters and dungeon regulars (4)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `lava-serpent-priestess` | monster | lava | REGEN | not_started | not_started | TBD (Tripo likely) | regular | backlog | 0 | Re-brief with the lava roster after F18/F19 |
| `lava-halo-knight` | monster | lava | DROP | n/a | n/a | none | regular | none | 0 | None |
| `sunken-temple-statue-sentinel` | monster | dungeon: sunken temple | PASS | not_started | not_started | Tripo (statue) | regular | froggy (Pack A zip) | 135 / 235 | Review Pack A's sentinel sheet before any new prompt |
| `sunken-temple-water-slime` | monster | dungeon: sunken temple | n/a | n/a | not_started | Blender (Puddlekin variant) | regular | Claude | 0 | Variant of the Puddlekin build |

### UI (9)

| id | class | region | A | B | C | route | budget | next owner | credits plan / worst | next action |
|---|---|---|---|---|---|---|---|---|---|---|
| `ui-joystick-b13-celestial-rune` | UI | global HUD | KEEP | n/a | not_started | PNG atlas (froggy) | ui | Codex UI | 0 | Integrate: clean alpha residue (<8 -> 0), repack with edge extrusion, CSS pressed/disabled states |
| `ui-joystick-a04-wildwood-jade` | UI | global HUD | KEEP | n/a | not_started | PNG atlas (froggy) | ui | Codex UI | 0 | Integrate: clean alpha residue (<8 -> 0), repack with edge extrusion, CSS pressed/disabled states |
| `ui-joystick-a10-dragonbone` | UI | global HUD | REGEN | n/a | not_started | PNG atlas (froggy) | ui | froggy (thumb only) | 0 | Optional: thumb-only regen |
| `ui-joystick-a02-frostglass` | UI | global HUD | DROP | n/a | n/a | PNG atlas (froggy) | ui | none | 0 | None |
| `ui-joystick-a05-astral-orbit` | UI | global HUD | DROP | n/a | n/a | PNG atlas (froggy) | ui | none | 0 | None |
| `ui-joystick-a08-dawn-petal` | UI | global HUD | DROP | n/a | n/a | PNG atlas (froggy) | ui | none | 0 | None |
| `ui-joystick-b04-floating-thumbstick` | UI | global HUD | DROP | n/a | n/a | PNG atlas (froggy) | ui | none | 0 | None |
| `ui-joystick-b09-crystal-silver` | UI | global HUD | DROP | n/a | n/a | PNG atlas (froggy) | ui | none | 0 | None |
| `ui-kit-v2` | UI | global HUD | not_started | n/a | not_started | PNG (froggy) | ui | Claude (send F7 when the UI lane needs it) | 0 | Send TASK F7 from the froggy task pack |

## 5. Next batch plan (priority order) and credits

### 5.1 Order of work

**P0, now:**
1. Stage-1 Tripo (owner, job card `docs/plans/2026-10-02-tripo-job-card.md`): **hero 01 geometry first** (100), Claude inspects, then hero 01's UV/texture/PBR (45). Then **Mossling** (145) when its F2/F6 set passes. Heroes 04 and 06 (290) last.
2. Claude reviews the F8 deliveries on arrival (Galehorn x3, Windstone arena x3, hero 03/05 round 2).

**P1, next (0 credits; froggy images and Claude's local work):**
3. Send **F09** (Windstone ring stone: the only Tripo-route Sunmeadow prop).
4. Send **F10** (Rimecrest key art), **F11** (arrival portal platform), **F12** (Rimecrest boss arena).
5. Send **F13-F16** (snow monster 4-view sets, design unchanged).
6. Solar Scorpion Stage C prerequisites (arena layout, server boss row, F12 pick), then its Stage C list.
7. Bovine NPC placement decision, then the NPC Stage C plan.
8. Sunmeadow Blender/CC0 props (altar, camp kit, tent, signpost, broken cart, Sella moves) and the warp props.

**P2:**
9. Send **F17** (Southreach), **F18** (lava key art), **F19** (lava boss, after F18), **F20** (Guardian of Aurel, after the Pack A zip).
10. Tripo stage 2, after the owner approves: Galehorn, ring stone, Thistle Boar, Brookclaw, Turfback Matriarch.
11. Rimecrest Tripo jobs after the owner approves **and** after the S1 Mossling sample passes (pipeline proven): tick, raptor, wraith, golem.
12. Hero pot (opens when hero 01 passes review): heroes 03/05, sword, hammer, dagger.

**P3:**
13. **F21** (Frost Jarl, after the Pack D zip); F22 and F23 only if the owner keeps the proposed regions; later bosses (treant, crystal wyrm) after the Pack B/C zips; the statue sentinel.

### 5.2 Credit ledger

| Pot | Ceiling | Planned | Worst case | Contents |
|---|---|---|---|---|
| Stage 1 | **600** | **580** | 980 if every job retries once; **680 with a single retry**, which already crosses 600 | Heroes 01, 04, 06 (145 each) + Mossling (145, 4K S1) |
| Hero pot | 2,500 cumulative, opens when hero 01 passes review | 695 (cumulative with stage-1 heroes: 1130) | 1195 | Heroes 03, 05 (145 each), sword, hammer, dagger (135 each) |
| Sunmeadow slice | **none approved** | 705 | 1205 | Galehorn 145, ring stone 145, Thistle Boar 135, Brookclaw 135, Turfback 145 |
| Rimecrest | **none approved** | 550 | 950 | Bone tick 135, bone raptor 135, bone wraith 135, rime golem 145 (boss and NPC already built: 0) |
| Bosses | **none approved** | 435 | 735 | Guardian of Aurel, Emberwright, Frost Jarl (145 each) |
| Later | — | 425 | 725 | Treant matriarch, crystal wyrm (145 each), statue sentinel (135) |

Stage-1 rule: 580 of 600 leaves 20 credits of headroom, so one geometry retry (+100) would cross the ceiling. Run hero 01 first. If any retry happens, stop before the third hero and move it to the hero pot (credit guard rule 6: never start a job that would cross a ceiling).

Already spent before stage 1, under separate approvals: hero 02 pilot 175, Solar Scorpion 35, bovine shaman 100 (310 in total). Credits are policy-limited, not balance-limited (the Studio balance in the 2026-10-01 receipts was 25,125), so the ceilings are the owner's call.

### 5.3 Sunmeadow props: routing

| Prop | Route | Why |
|---|---|---|
| Camp kit (cart, crates, bags, barrel, weapon rack, dummy, torch + campfire, log seats, haystacks, palisade) | CC0 kit + Blender recipes | Quaternius pieces are on disk; the kits lack haystack, tent, palisade and campfire, so these are recipes (prop audit 3.8); about 21k triangles |
| Altar (flush platform + block) | Blender | The walkable flush platform must match its collider exactly; the carved block uses the forge stone + a groove height map and the ring-stone material |
| **Standing stones (ring)** | **Tripo, one master (145)** | Large sculpted erosion + carved glyph is what P2 does well and headless Blender does poorly (procedural noise rocks read as the removed egg rocks). One master serves 6 ring stones, 2 gate stones, 3 windmarks and the warp arrival rings (about 11+ placements) |
| Broken cart | Blender + CC0 | Planks and spokes are hard-surface thin parts (a Tripo weakness); built from the Quaternius cart |
| Tent | Blender | Thin poles and guy ropes; a simple A-frame recipe (600-1,200 triangles) |
| Signpost | Blender (reuse `prop_wayfinder_sign_01`) | Text belongs in decals/UI (Thai/English), never in geometry |
| Windmarks | Reuse of the ring-stone master + Blender streamers | No new job |

### 5.4 One boss per region or dungeon

| Region / dungeon | Boss | State | Next |
|---|---|---|---|
| Sunmeadow | Galehorn | F8 key art in flight | F6 4-view after the pick, card 02 |
| Rimecrest | Solar Scorpion | Built | Stage C list (0 credits) |
| Southreach | TBD | — | Design after F17 |
| Lava | the Emberwright (proposed name) | Direction REGEN | F19, card 17 |
| Sunken Temple of Aurel | Guardian of Aurel | Not started (Pack A not on disk) | F20, card 16 |
| Halls of the Frost Jarl | the Frost Jarl | Not started (Pack D not on disk) | F21, card 18 |
| Whisperwood Hollow | Treant matriarch | Pack B not on disk | Backlog card |
| Gloamcrystal Caverns | Crystal wyrm | Pack C not on disk | Backlog card |
| Cloudshoal Isles (proposal) | TBD | — | Only if the region is kept |

## 6. froggy drafts, in sending order

Each file starts with `[Claude -> froggy | 2026-10-02 | <id>]` and lists its attachments (always the look target). F13-F16 use the F6 turnaround format because the owner already closed Stage A for the snow pack; all others use the Stage A format (16:9, 3 variants, clean for 3D generation).

| # | Draft | Send when |
|---|---|---|
| 1 | `planning/assets/froggy-drafts/F09-windstone-ring-stone.md` (Part 1 now; Part 2 after the pick) | Now (attach the F8 arena pick when it exists) |
| 2 | `F10-rimecrest-snow-region-keyart.md` | Now |
| 3 | `F11-windstone-arrival-portal-platform.md` (Part 2 state sheet after the pick) | After F09 and F10 picks (needs both looks) |
| 4 | `F12-rimecrest-boss-arena-keyart.md` | After the F10 pick |
| 5 | `F13-snow-lv1-bone-tick-4view.md` | Now |
| 6 | `F14-snow-lv1-bone-raptor-4view.md` | Now |
| 7 | `F15-snow-lv2-bone-wraith-4view.md` | Now |
| 8 | `F16-snow-lv3-rime-golem-4view.md` | Now |
| 9 | `F17-southreach-field-keyart.md` | After F8 (attach its arena pick) |
| 10 | `F18-lava-region-keyart.md` | After the Rimecrest picks |
| 11 | `F19-lava-boss-keyart.md` | After the F18 pick |
| 12 | `F20-guardian-of-aurel-keyart.md` | After froggy re-delivers Pack A |
| 13 | `F21-frost-jarl-keyart.md` | After Pack D |
| 14 | `F22-whisperwood-region-keyart.md` | Only if the owner keeps the region |
| 15 | `F23-cloudshoal-isles-keyart.md` | Only if the owner keeps the region |

Also send, without a new draft: the Brookclaw prompt from `docs/reviews/2026-10-02-monsters-sunmeadow-roster-and-placement.md` section 9.5 as an F2 addendum (Brookclaw is not in F2), and the F6 block for Galehorn after the F8 pick.

## 7. Tripo job cards, in priority order

All cards are in `planning/assets/tripo-cards/`, and every one is **NOT READY** until its set passes QA and the design review (the receipt must say `eligible_for_tripo: true`). Heroes 01, 04 and 06 use the existing `docs/plans/2026-10-02-tripo-job-card.md`.

| # | Card | Credits plan / worst | Pot |
|---|---|---|---|
| 0 | Heroes 01, 04, 06 (existing job card) | 435 / 735 | stage 1 |
| 1 | `01-mossling.md` | 145 / 245 | stage 1 |
| 2 | `02-galehorn.md` | 145 / 245 | Sunmeadow slice |
| 3 | `03-windstone-ring-stone.md` | 145 / 245 | Sunmeadow slice |
| 4 | `04-hero-01-sword.md` | 135 / 235 | hero pot |
| 5 | `05-hero-06-hammer.md` | 135 / 235 | hero pot |
| 6 | `13-hero-05-thief.md` | 145 / 245 | hero pot |
| 7 | `14-hero-03-archer.md` | 145 / 245 | hero pot |
| 8 | `06-thistle-boar.md` | 135 / 235 | Sunmeadow slice |
| 9 | `08-turfback-matriarch.md` | 145 / 245 | Sunmeadow slice |
| 10 | `07-brookclaw.md` | 135 / 235 | Sunmeadow slice |
| 11 | `09-snow-bone-tick.md` | 135 / 235 | Rimecrest |
| 12 | `10-snow-bone-raptor.md` | 135 / 235 | Rimecrest |
| 13 | `11-snow-bone-wraith.md` | 135 / 235 | Rimecrest |
| 14 | `12-snow-rime-golem.md` | 145 / 245 | Rimecrest |
| 15 | `15-hero-05-dagger.md` | 135 / 235 | hero pot |
| 16 | `17-lava-emberwright.md` | 145 / 245 | bosses |
| 17 | `16-guardian-of-aurel.md` | 145 / 245 | bosses |
| 18 | `18-frost-jarl.md` | 145 / 245 | bosses |
| — | `99-backlog.md` (treant, crystal wyrm, statue sentinel, Southreach and Cloudshoal bosses) | class defaults | later |

Stage C task lists (0 Tripo credits): `planning/assets/stage-c/solar-scorpion-rimecrest-boss.md` and `planning/assets/stage-c/bovine-shaman-npc.md`.

## 8. Requests

**For Claude (main):**
1. Send the froggy drafts in the order of section 6, plus the Brookclaw addendum and the Galehorn F6 block.
2. Ask froggy to deliver files that exist only in its chat:
   - the passed Mossling concept (to `sources\froggy\monsters-20261002\`);
   - the round-1 dungeon packs A-D (to `sources\froggy\dungeons-20261001\`);
   - the Snow v1/v2 renders.
3. Map lane:
   - fix the Windstone portal trigger overlaps (altar 0.53 m, trail edge about 1.4 m);
   - write the Rimecrest layout JSON from section 3.1, with the scorpion arena;
   - start a Southreach roster.
4. Settle a doc conflict before the first monster or boss job. The credit guard and the job card set face targets at about the runtime budget (for example hero quad 5,900, about 12k), while the device-tier plan section 6.2 says "generate at twice LOD0" as a bake source. Geometry costs 100 either way; only Smart UV limits (80k triangles) and the bake workflow differ.
5. Solar Scorpion Stage C prerequisites:
   - the server boss row (owner numbers, Codex server);
   - the arena in the layout;
   - the capture harness reference mode.
6. Resolve the bovine placement: the rig-v1 README registers it as the city elder Ruun, while the owner calls it a map NPC.
7. Run `--prep` with the design review for the sword and hammer (both QA PASS) when their heroes pass.
8. Originality checks for the board's names:
   - "Rimecrest" vs Lumivara's "Frostveil Pass";
   - the proposed names "Ashveil Caldera", "Emberwright" and "Cloudshoal" were chosen to avoid known game names, but no external search was run.

**For the owner:**
1. Approve the next Tripo ceilings, or one combined ceiling. Proposed: Sunmeadow slice 705 (worst 1205), Rimecrest 550 (worst 950), bosses 435 (worst 735).
2. Run stage 1 in this order: hero 01 geometry, inspection, hero 01 finish, Mossling, then heroes 04 and 06. Record every job in its receipt.
3. Choose the bovine NPC's home: Rimecrest, the city as Ruun, or both.
4. Put the snow map images, if they exist, in `sources\snow\map\`.
5. Keep or drop the proposed regions (Whisperwood, Cloudshoal Isles), and confirm or rename "Ashveil Caldera", "the Emberwright" and the Rimecrest display name.
6. Confirm the Tripo plan, for commercial rights, used for the scorpion (2026-09-30) and bovine (2026-10-01) jobs.
7. Optional: a thin rime dusting on the scorpion's leg tips (albedo only), yes or no.

## 9. Method and limits

**Method:**
- Every image listed in section 2 was viewed directly.
- `tools/art/turnaround_qa.py` 1.0.0 ran on all 6 turnaround sets and 2 single-image weapons.
- `planning/evidence/asset-review-20261002/_method/value_check.py` measured luma, contrast, darkness, saturation, interior edge energy and value fragmentation, wrote greyscale and silhouette reads at 64 and 32 px, and made the UI proofs. It reuses the QA tool's segmenter for subject masks.

**Limits:**
- Masks on dark-on-dark images (the lava golem) are approximate; that failure is itself a readability finding.
- The metrics are review aids, not gates.
- The edge-energy clutter proxy is only comparable within a class.
- Nothing in `Downloads` was modified. No Blender, browser, app or Tripo action was taken, and nothing was spent.
- Third-party and IP references produced numbers only; no derived image was written for them.
- This is a self-review by one agent, not an independent review.
- **Not reviewed here**, because they are not art inputs for this board or are already decided elsewhere:
  - `froggy\research-20261002\` (F1 text research, already folded into the mobile plan);
  - `water\MountainRIver\` and `github\` (code, with their own provenance files);
  - `coastal_cliff_01_2k.blend` (Poly Haven CC0 source);
  - the hero 02 GLBs (built pilot);
  - `sunmeadow_hero_oak_p20_source.glb` (the failed Tripo oak; trees are no longer a Tripo route);
  - `logoxex`, the two `uv-layout` PNGs and the VFX videos.
