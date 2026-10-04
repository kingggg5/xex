# Sunmeadow main-map blueprint v1 (2026-10-03)

**Status:** PLAN, by Claude (map lane). Built from the live v3 layout, the monster plan and the owner's references.

**Image:** [2026-10-03-sunmeadow-blueprint-v1.png](2026-10-03-sunmeadow-blueprint-v1.png). North is up; the city gate is at the top and the south gate at the bottom.

**Data:** `planning/levels/sunmeadow-blueprint-v1.json`, schema `xexoria.map-blueprint/1`.

**Script:** `planning/evidence/sunmeadow-blueprint-v1/blueprint_v1.py`. It checks every solid item against:
- the walk paths (at least 0.5 m clear);
- the boss arena's keep-clear (12 m);
- the warps;
- the 48 spawn slots;
- the calm zones.

**Result:** 45 items, 0 conflicts. 7 items were nudged by up to 5 m to clear the paths; the moves are recorded in the JSON.

## สรุปสำหรับเจ้าของ

ตอนนี้แมพโล่งเพราะมีแค่หินเล็ก กก และพุ่มไม้กระจาย ๆ (411 ชิ้น) ยังไม่มีแลนด์มาร์ก สิ่งก่อสร้าง หรือจุดที่ทำให้แต่ละมุมของแมพมีเรื่องราว blueprint นี้บอกว่าจะเพิ่มอะไรตรงไหน:

- **มุมซ้ายบน (บึงบัว):** สวนหินใหญ่ (R1), รูปปั้นหญิงสาวที่ศาล (S4), ตลาด 3 แผงหน้าประตูเมือง (ST2), รูปปั้นผู้พิทักษ์ปีกคู่หน้าประตู (S1/S2)
- **ซ้ายกลาง:** หินตีนหน้าผา (R2/R3), หัวรูปปั้นยักษ์จมดินเป็นจุดค้นพบ (S5), ลูกคลื่นพื้นดิน (T2), แอ่งน้ำฝน (P4)
- **มุมซ้ายล่าง (อ่าว):** ดงมะพร้าว 10 ต้น (PL1), เสาหินกลางทะเล (R4), กระท่อมชาวประมงกับเรือ (ST7), เนินทรายหลังหาด (T3), คบเพลิงชายหาด (L3)
- **กลางแมพ:** ซุ้มประตูหินคร่อมทาง (ST5), หินสามพี่น้อง (R5), ป้ายบอกทางและศาลเล็กตามแยก (ST8), โคมไฟตามทางทุก 20 m (L1), สระน้ำพุ (P2), รูปปั้นผู้รักษาสายลมหน้าลานบอส (S3), กระถางไฟ (L2)
- **บอส:** Galehorn Lv 9–11 ที่ลานหิน (0,−68) ตามเดิม ห้ามวางของแข็งในรัศมี 12 m
- **มุมขวาบน (บ้านไร่):** กังหันลม (ST1), รั้วทุ่งแกะ (F1), แปลงผัก (F2), เกวียนฟาง (C3), รังผึ้ง (ST6), ค่ายนายพรานพร้อมเต็นท์และรั้วไม้แหลม (ST3/F5), เกวียนหนังสัตว์ (C4), เกวียนพ่อค้า (C2)
- **ขวากลาง:** โขดหินเนินตะวันออก (R7), ปลักโคลนหมูป่าพร้อมรั้วพัง (P1/F4), elite Lv 6–7
- **มุมขวาล่าง:** **เนินอรุณ (T1)** สูง 3–6 m มีโขดหินยอดเนิน (R6), หอสังเกตการณ์ร้าง (ST4), น้ำซับ (P3) และ**จุดมอนสเตอร์ใหม่ Lv 7–8** (N1)
  - ข้อจำกัด: ตอนนี้ server ให้เดินได้เฉพาะพื้นเรียบ Y=0 เวอร์ชันแรกจึงเป็นเนินที่เดินอ้อมได้ ส่วนการขึ้นไปบนยอดได้ต้องให้ Codex เพิ่มระบบความสูงพื้นที่ server ก่อน
- **ล่างกลาง:** รูปปั้นยามคู่ (S6), รั้วสองข้างถนนใต้ (F6), เกวียนคว่ำเป็นจุดเล่าเรื่อง (C5), หินชายป่า (R8)
- **มอนสเตอร์:** ใช้ 10 โซนเดิม (Lv 1–2 ทุ่งเหนือ → Lv 3–5 ทุ่งน้ำตกและลานหิน → Lv 4–6 ริมลำธาร → Lv 6–7 ปลักหมูป่า → บอส Lv 9–11) และเพิ่ม N1 Lv 7–8
- **หญ้า:** กอหญ้า 5–12 ใบ 3 ระดับความสูง โคนเข้ม (ไม่ใช่สามเหลี่ยมแปะ) มีทุ่งดอกไม้ 4 จุด หญ้าแห้งสีทองบนเนิน หญ้าเข้มริมน้ำ และหญ้าสั้นในลานต่อสู้
- **แสง:**
  - กลางวัน: ฟ้าไล่สี แดดอุ่น เงาอมฟ้า
  - เย็น: ฟ้าม่วงแบบภาพอ้างอิง
  - กลางคืน: โคมไฟเป็นวงกับหิ่งห้อย
  - พายุ: ม่วงเทา ฟ้าผ่า มีแอ่งน้ำฝน
- **ฉากหลัง:**
  - เหนือ: เมืองกับปราสาท
  - ตะวันตก: ทะเลกับเกาะไกล ๆ
  - ใต้: ภูเขาป่า
  - ตะวันออก: เนินเขากับกังหันลม

**ลำดับทำ:** P0 (20 รายการ) ทำให้แมพดูเต็มก่อน แล้วตามด้วย P1 และ P2 ถ้าโมเดลจริงยังไม่เสร็จ จะใช้โมเดล CC0 ที่มีอยู่แทนไปก่อน เพื่อให้เห็นในเกมเร็วที่สุด แล้วค่อยเปลี่ยนเป็นโมเดลจริงทีหลัง

## Items

| ID | Wave | ไทย | English | Where (x, z) m | Spec | Builds it |
|---|---|---|---|---|---|---|
| R1 | P0 | สวนหินมุมซ้ายบน (ริมบึงบัว) | NW rock garden by Lotus Mere | (-41, 17) | 1 boulder 3 m + 4 medium + 6 small, moss caps, ferns between | Codex props-stone |
| R2 | P0 | หินใหญ่ตีนหน้าผาตะวันตก | West cliff-foot boulders | (-49, -14) | 3 boulders 2-4 m leaning on the cliff, scree fan | Codex props-stone |
| R3 | P1 | หินเรียงตีนหน้าผา (ช่วงกลาง) | Cliff-foot scree line | (-50, -34) | boulder every 6-8 m along the cliff foot z -24..-46, mossy, fallen slabs | Codex props-stone |
| R4 | P0 | เสาหินกลางทะเลที่อ่าว (มุมซ้ายล่าง) | Cove sea stacks (SW corner) | (-60, -90) | 2 sea stacks 4-6 m in the shallows (-60,-90) and (-55,-97), shore rocks + foam | Codex props-stone |
| R5 | P0 | หินสามพี่น้อง (แลนด์มาร์กกลางทุ่ง) | Three Sisters standing boulders | (19.38, -19.89) | three upright boulders 2.5 / 3.2 / 4 m, lichen, flower ring; reads from spawn | Codex props-stone |
| R6 | P0 | โขดหินยอดเนิน | Knoll crown outcrop | (36, -97) | layered outcrop 4-5 m on the knoll top, strata + moss on ledges | Codex props-stone |
| R7 | P1 | โขดหินเนินตะวันออก | East-hill outcrops | (40, -34) | 2 outcrops (40,-34) and (41,-54), half-buried in the hill | Codex props-stone |
| R8 | P1 | หินชายป่าใต้ | South forest-edge rocks | (-24, -99) | 2 clusters (-24,-99) and (22,-100) framing the south road | Codex props-stone |
| S1 | P0 | รูปปั้นผู้พิทักษ์ปีก (ซ้าย) หน้าประตูเมือง | Winged guardian statue W (city exit) | (-15, 18) | 5.5-6 m on a 1.2 m plinth, faces south; original Xexoria design (F25) | froggy F25 -> Tripo (owner ceiling) / Blender stand-in |
| S2 | P0 | รูปปั้นผู้พิทักษ์ปีก (ขวา) หน้าประตูเมือง | Winged guardian statue E (city exit) | (15, 18) | mirror pair of S1 | froggy F25 -> Tripo / Blender stand-in |
| S3 | P1 | รูปปั้นผู้รักษาสายลม หน้าลานบอส | Windkeeper statue at the arena approach | (7, -53) | 4 m weathered stone figure holding a horn, faces north toward arriving players; 16 m from the arena centre | Codex props-stone (Blender)  |
| S4 | P1 | รูปปั้นหญิงสาวที่ศาลบึงบัว | Lotus shrine maiden | (-51, 7) | 2.4 m mossy statue with an offering bowl beside the shrine | Codex props-stone |
| S5 | P1 | หัวรูปปั้นยักษ์จมดิน (จุดค้นพบ) | Fallen giant statue head (discovery) | (-26, -31) | 3 m tall stone head half-buried, flowers in the cracks, photo spot | Codex props-stone |
| S6 | P2 | รูปปั้นยามคู่ที่ประตูใต้ | South-gate sentinel pair | (-6, -96) | pair at (-6,-96) and (6,-96), 3.5 m, braziers at their feet | Codex props-stone |
| F1 | P0 | รั้วทุ่งเลี้ยงแกะ (บ้านไร่) | Croft sheep pasture fence | (33.63, -23.08) | split-rail, gate gap at the west side, 6 sheep inside | Codex props-craft |
| F2 | P1 | รั้วแปลงผัก/ข้าวสาลี | Crop field fence | (18, 2) | low wattle fence around a wheat/vegetable plot with a scarecrow | Codex props-craft |
| F3 | P1 | รั้วไม้ข้างทางหลัก (มีช่องว่าง) | Main-trail rail fence with gaps | (-5, -8) | 1 side only, broken segments, guides the eye down the trail | Codex props-craft |
| F4 | P1 | รั้วพังที่ปลักหมู | Broken fence at the boar wallow | (26.68, -67.88) | smashed rails, tusk marks; tells the elite pack story | Codex props-craft |
| F5 | P0 | รั้วไม้แหลมรอบค่ายนายพราน | Hunter camp stake fence | (16.62, -5.37) | low stakes, opening west toward the trail | Codex props-craft |
| F6 | P2 | รั้วสองข้างถนนใต้ | South road fences | (6, -84) | both sides of the south road: (-6,-84)->(-6,-93) and (6,-84)->(6,-93) | Codex props-craft |
| T1 | P0 | เนินอรุณ (เนินดินมุมขวาล่าง) | Sunrise Knoll (SE raised ground) | (18, -84) | grass + dry ochre top, rock ring R6, watchtower ruin ST4, spring P3. Server support is Y=0 today: v1 = visual hill ringed by rocks (walk around); v2 walkable top needs the server terrain-height request (Codex) | Claude terrain + Codex server request |
| T2 | P1 | ลูกคลื่นพื้นดินทุ่งตะวันตก/ตะวันออก | Meadow swells | (-36, -10) | soft visual undulation breaks the flat carpet; same treatment east (20..40, -40..-58) | Claude terrain |
| T3 | P1 | เนินทรายหลังชายหาด | Dune ridge behind the beach | (-38, -70) | dune grass, driftwood, palms on the crest | Claude terrain |
| P1 | P0 | ปลักโคลนหมูป่า | Boar wallow mud pools | (33, -78) | 3 muddy puddles, hoof prints, splash VFX; elite clearing flavour | Codex water |
| P2 | P0 | สระน้ำพุกลางทุ่ง | Meadow spring pond | (22, -56) | 7 x 4 m pond, reeds, 5 stepping stones, dragonflies | Codex water |
| P3 | P1 | น้ำซับตีนเนิน | Knoll spring + trickle | (24, -91) | 4 m pool fed by a trickle off the knoll rocks | Codex water |
| P4 | P2 | แอ่งน้ำฝนบนทาง | Rain puddles on the trail | (-14, -27) | appear only in rain (storm weather), reflect the sky | Codex water + VFX |
| PL1 | P0 | ดงมะพร้าวชายหาดอ่าว | Cove coconut palms | (-37, -80) | 8 palms leaning 5-15 deg toward the water + 2 at the pier landing; coconuts, shadow on sand. Source: CC0 kit (Kenney Nature Kit / Quaternius Ultimate Nature, pre-QAL) restyled by the trees lane; never home-made | Claude trees lane (CC0 download) |
| C1 | - | เกวียนพัง (มีอยู่แล้ว) | Broken cart (existing) | (13, -73) | keep | existing |
| C2 | P0 | เกวียนพ่อค้าหน้าประตูเมือง | Merchant cart at the city exit | (21, 9) | cart + crates + sacks beside the signpost; the gate market's supply | Codex props-craft |
| C3 | P0 | เกวียนฟางบ้านไร่ | Croft hay cart | (35.9, -2.78) | hay load, pitchfork | Codex props-craft |
| C4 | P1 | เกวียนนายพราน (หนังสัตว์) | Hunter's game cart | (20, -14) | pelts, antlers, a caged bird | Codex props-craft |
| C5 | P1 | เกวียนคว่ำใกล้ประตูใต้ | Overturned cart near the south gate | (11, -89) | spilled crates and apples: an ambush story beat | Codex props-craft |
| ST1 | P0 | กังหันลมบ้านไร่ (แลนด์มาร์กขวาบน) | Croft windmill (NE skyline) | (43, 18) | 10-12 m windmill, turning sails; visible from spawn | Codex props-craft |
| ST2 | P0 | ตลาดหน้าประตูเมือง 3 แผง | Gate market (3 stalls) | (-17, 9) | 3 varied stalls (F26 kit), awnings sapphire/cream + terracotta/cream, fruit crates, never in a row | Codex props-craft |
| ST3 | P0 | เต็นท์และราวตากหนังค่ายนายพราน | Hunter camp tents + racks | (25.94, -9.76) | 2 canvas tents, drying racks, campfire, weapon rack | Codex props-craft |
| ST4 | P0 | หอสังเกตการณ์ร้างบนเนิน | Ruined watchtower on the knoll | (31, -95) | 8 m broken stone tower, banner remnant, watch-fire; visible from the arena | Codex props-stone |
| ST5 | P1 | ซุ้มประตูหินโบราณคร่อมทาง | Ancient arch over the trail | (-1, -30) | arch spans the 4 m trail (legs outside the path), ivy; frames the bluff/grotto view | Codex props-stone |
| ST6 | P1 | รังผึ้งบ้านไร่ 3 รัง | Croft beehives | (45, -6) | 3 skep hives on a bench + bees (wildlife) | Codex props-craft |
| ST7 | P1 | กระท่อมชาวประมง + เรือ | Cove fishing hut + skiffs | (-36, -92) | small stilt hut, nets, 2 skiffs (F27) at the pier | Codex props-craft |
| ST8 | P1 | ป้ายบอกทาง + ศาลเล็กตามแยก | Signposts + wayshrines at junctions | (-10, -22) | 4 signposts (trail_start, falls junction, glade north, south road) + 2 wayshrines with candles | Codex props-craft |
| L1 | P0 | โคมไฟตามทางหลัก ทุก ~20 m | Trail lanterns every ~20 m | (3, -20) | post lanterns 2.5 m beside the main trail and croft lane; warm pools at night | Codex props-craft + Claude look-grade |
| L2 | P1 | กระถางไฟหน้าลานบอส | Arena approach braziers | (-3.75, -54.0) | pair at (-4,-54) and (4,-54), 14.6 m from the arena centre | Codex props-craft |
| L3 | P2 | คบเพลิงชายหาด | Beach torches | (-42, -84) | 3 tiki torches along the beach | Codex props-craft |
| N1 | P1 | จุดมอนสเตอร์ใหม่: ลาดเนินอรุณ Lv 7-8 | New spawn: Knoll slopes Lv 7-8 | (24, -98) | thistle boars + one Mossling Elder, after the oak wallow; outside every calm zone | Claude layout + Codex server spawns |

## Grass

- **G1** หญ้าเป็นกอ 3 ระดับความสูง (ทั้งแมพ) (Clumped tufts, 3 heights (whole map)): no single-triangle cards: 5-12 blade clumps, dark roots, 3 hue families; look target §5 #5
- **G2** ทุ่งดอกไม้ป่า: ทุ่งเหนือ วงลานหิน ลาดเนิน สวนบ้านไร่ (Wildflower meadows): north hunt meadow (daisies, buttercups), glade ring (white/yellow), knoll slopes (red/orange poppies), croft garden (lavender)
- **G3** หญ้าแห้งสีทองบนเนินและเนินตะวันออก (Dry ochre grass on the knoll + east hills): #b59a4e highlights, shorter
- **G4** หญ้าเขียวเข้มชุ่มน้ำริมลำธาร/บึง/อ่าว (Lush dark grass by water): taller, reeds mixed in
- **G5** หญ้าสั้นถูกเหยียบในลานต่อสู้และค่าย (Short trampled grass in clearings): keeps combat readable

## Lighting tone

- **noon:** ท้องฟ้าไล่สี #a5cbfb (บน) -> #aed3f0 (ขอบฟ้า); แดดอุ่น; เงาอมฟ้า; หมอกไกลสีฟ้าอ่อน
- **golden_hour:** ฟ้าส้มทอง-ชมพู แสงเฉียงยาว, เงายาว, ลำแสงลอดต้นไม้ (Codex sun shafts)
- **violet_dusk:** ฟ้าม่วง-น้ำเงินแบบภาพ R07, หมอกม่วงอ่อน, โคมเริ่มติด
- **night:** ฟ้าน้ำเงินเข้ม เห็นดาว/ดวงจันทร์ ambient ฟ้าอมเขียว แสงโคมอุ่นเป็นวง หิ่งห้อย (Codex)
- **storm:** ม่วงเข้ม-ดำ-เทา-ขาว ฝน + ฟ้าผ่า (Codex) ไม่มีแสงอาทิตย์ แอ่งน้ำฝน P4
- **targets:** docs/reviews/2026-10-03-reference-look-target-v2.md §3 + §5 #1 #2 #7 (Claude look-grade v2, ?look=v2)

## Skyline

- N: city walls + castle (existing) + guardian statues S1/S2 in front
- W: the sea beyond the cove with 2 distant islands; sea stacks R4
- S: forested mountains behind the south forest wall (impostor silhouettes, aerial perspective)
- E: rolling hills, the windmill ST1 and distant peaks

## Rules

- arena keep-clear 12 m around (0,-68) for solid props
- warps unchanged
- solid props >= 0.5 m off every walk line
- physical support stays Y=0 (T1 v1 is a visual hill ringed by rocks; a walkable top needs the server terrain-height request)
- trees and palms only from CC0 kits / approved generators (llm.txt rule 4)
- principles only from the owner's AAA refs (no copied art/UI/names)

## How it gets into the game fast (wave P0)

1. **Placement.** The dressing generator reads `sunmeadow-blueprint-v1.json` as explicit anchors, so the existing `?dressing=v3` loader places every item.
   - Until each procedural kit lands, use stand-ins from CC0 kits already on disk (Quaternius Fantasy Props and Medieval Village, Kenney), clearly tagged `standin`.
   - Swap the stand-ins as the props-stone and props-craft kits arrive.
2. **Palms (PL1).** Download a CC0 palm kit (Kenney Nature Kit or the pre-QAL Quaternius Ultimate Nature) with provenance, and restyle it to the trees lane's rules. Never home-made, never Tripo.
3. **Knoll (T1).** v1 is a visual terrain mound plus a rock-ring collider. v2, a walkable top, follows the server terrain-height request.
4. **Proof.** BABYLON CAPTURE from the locked cameras (spawn, elevated, arena approach, cove, croft, knoll) with `?dressing=v3&look=v2`, before and after, on both renderers.
