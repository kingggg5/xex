# Xexoria two-year playable plan, fast build (2026-10 → 2028-09)

- **Date:** 2026-10-02
- **Author:** Claude (supervisor for maps and visuals), for the owner and Codex root
- **Status:** PLAN. These are targets, not evidence.
- **Companion:** `docs/plans/2026-10-02-two-year-roadmap.json` holds the machine-readable milestones, gates and dependencies.
- **Re-planning:** every quarter, from measured throughput, using the perf ledger, the task graph burndown and the region/dungeon cycle times.

> **สรุปสำหรับเจ้าของ**
> - **เป้าหมาย 2 ปี:** Xexoria 1.0 คือ MMO บนเว็บที่เล่นได้ครบทั้ง PC และมือถือ (iPhone 11 ขึ้นไป และ Android ระดับกลาง) ให้ความรู้สึกแบบ Ragnarok แต่เป็นงานของเราเองทั้งหมด ขอบเขตที่ 1.0:
>   - เมืองหลวง 1 แห่ง แมพสนาม 10 แมพ และดันเจี้ยน 8 แห่ง
>   - อาชีพเริ่มต้น 6 อาชีพ และอาชีพขั้นสอง 12 อาชีพ
>   - เลเวลสูงสุด 80
>   - ไอเท็ม การ์ด ตีบวก ปาร์ตี้ กิลด์ ร้านค้าผู้เล่น PvP สงครามกิลด์ และอีเวนต์
> - **8 milestone ไตรมาสละหนึ่ง:**
>   1. M1 (ธ.ค. 2026): Sunmeadow เล่นได้ครบ บนมือถือได้ 30 fps
>   2. M2 (มี.ค. 2027): closed alpha ครบ 6 อาชีพ และมีดันเจี้ยนแรก
>   3. M3: แมพลาวา แมพป่า กิลด์ และร้านค้า
>   4. M4: อาชีพขั้นสอง และ PvP
>   5. M5 (ธ.ค. 2027): open beta
>   6. M6 และ M7: เติมเนื้อหาจนครบ
>   7. M8 (ก.ย. 2028): เปิดตัว 1.0
> - **ทำให้เร็วด้วย 3 อย่าง:**
>   1. ทำ Sunmeadow ให้ดีที่สุดเป็นต้นแบบ แล้วใช้ template กับ procedural สร้างแมพใหม่ทุก ~6 สัปดาห์ ดันเจี้ยนทุก ~8 สัปดาห์ และอาชีพใหม่ 2 อาชีพต่อไตรมาส
>   2. ให้ agent หลายสายทำงานขนานกัน และมีเครื่องตรวจอัตโนมัติ
>   3. คุณตัดสินใจ keep/drop สัปดาห์ละครั้ง
> - **คอขวดที่ใหญ่ที่สุด:** เรามีคอมเครื่องเดียว (GTX 1050, Blender รันได้ทีละตัว) ถ้าเพิ่มเครื่องที่สองหรือ cloud GPU งานภาพจะเร็วขึ้นราวเท่าตัว
> - **สิ่งที่ต้องให้คุณตัดสินใจ:** ดูหัวข้อ 11 เช่น รูปแบบรายได้ งบ server และ Tripo จำนวนอาชีพ สงครามกิลด์ และเครื่องทดสอบ

## 1. What "full playable" means at 1.0 (September 2028)

These are targets. Calibrate them after M2 from measured cycle times. They follow the owner's intent in `llm.txt`: Ragnarok warmth, Warcraft readability, God of War construction discipline, every design original, and AAA craft as a target, never a claim of AAA parity.

| Area | 1.0 target |
|---|---|
| **World** | 1 capital city hub. 10 field regions of 2×2 to 2×3 cells of 64 m each: Sunmeadow, Rimecrest, Southreach, Ashveil Caldera, Whisperwood, Cloudshoal Isles and 4 more to design. 8 dungeons: Sunken Temple of Aurel, Whisperwood Hollow, Gloamcrystal Caverns, Halls of the Frost Jarl, plus 4 from the slate (ember forge, sky ruin, tidal grotto, a clockwork tower). An endless tower as endgame, reusing the tower/room code |
| **Classes** | 6 base classes: Swordsman, Mage, Archer, Acolyte, Thief, Merchant. Each has 6 skills plus a basic attack. 12 second classes, two branches per base class, each with 6 new skills and 2-3 passives. A job-change quest for each |
| **Progression** | Base level 80 / job level 50 at 1.0. Interim caps: 30 at M2, 45 at M3, 60 at M4, 70 at M6. Stats, skill points, equipment |
| **Monsters** | About 60 regular types (4-6 per region plus dungeon regulars), about 10 elites, 10 field bosses, 8 dungeon bosses, 2-3 world bosses |
| **Items** | About 400 at 1.0, across weapons per class, armour slots, accessories, consumables and materials. **Cards**: one per monster (about 80), socketed. **Refine** +1..+10 with risk. Enchant. Crafting for the Merchant line |
| **Quests** | Main story with one chapter per region; 8-12 side quests per region; daily and weekly tasks; achievements; a tutorial that plays on its own (deep review P0 03) |
| **Social** | Parties of up to 6 with a party finder; guilds of up to 50; friends; chat channels with safety filters (P0 06); emotes |
| **Economy** | Zeny; NPC shops; player vending for the Merchant line; mail; an escrow ledger for every transfer (deep review §10.4); designed gold sinks. Auction house: owner decision |
| **PvP** | Arena 1v1 and 3v3 from M4. Guild siege, a territory war in the spirit of WoE, at 1.0 (owner decision). Combo reactions stay off in PvP |
| **Live ops** | An events engine and seasonal events; GM tools, moderation, reports; telemetry. Battle pass and cash shop are owner decisions; cosmetic-only is recommended |
| **Platforms** | Desktop Chrome, Edge, Firefox, Safari; iOS Safari from iPhone 11; Android Chrome from mid-range 2021 phones. App wrappers are an owner decision. Device tiers Low/Medium/High/Ultra/Epic (`docs/plans/2026-10-02-device-tiers-plan.md`) |
| **Scale** | About 500 CCU per world server (AOI + delta, protocol v8). Several channels or shards behind a world router. Launch target of 2,000+ CCU in total, calibrated from the sweeps |
| **Languages** | Thai and English throughout, including long Thai strings in every UI test |

## 2. How we build fast

### 2.1 Lanes and their throughput

| Lane | Owns | Parallelism | Throughput lever |
|---|---|---|---|
| **Claude** (supervisor) | Map layouts and level design, Blender map construction, terrain, foliage, water, light, sky and fog, art direction, the asset board, every review gate | Up to 10 Opus 5.5 sub-agents | Templates, procedural recipes, review checklists |
| **Codex root** | PM and integrator; Rust server; gameplay and combat; `main.ts`/`scene.ts` | Root plus up to 10 workers | Data-driven systems, validators, server tests |
| **Codex VFX lane** | Combat FX, ambient, weather, celestial, clouds | Workers | Kit v2 and the data-driven particle pool (B13) |
| **Codex UI thread** | `ui/**`, HUD, menus, minimap UI | Workers | The responsive audit and the capture harness |
| **Codex side chats** | Bounded tool tasks: sweep bots, overlays, Blender weapons | As many as needed | Isolated file scopes |
| **froggy** (GPT, cloud) | Concept and key art, 4-view sheets, painted textures, minimaps | 1 task at a time | Uses no local CPU or GPU; batch each week |
| **Tripo P2.0** | Organic 3D: monsters, bosses, hero gear | Credit pots | Turnaround QA and the credit guard before any spend |
| **Owner** | System design, keep/drop, approvals, device tests | Weekly | One batched decision list per week |

On 2026-10-02 the program ran 10 Claude sub-agents, 4 Codex workers and 3 side chats in parallel. The limit is the shared workstation, not the number of agents (§2.7).

### 2.2 Templates multiply speed: prove once on Sunmeadow, then clone

**Region template, 6 weeks per region after M1:**

| Week | Claude | Codex | froggy / Tripo |
|---|---|---|---|
| 1 | Layout JSON, procedural dressing rules, minimap base, playability checks | Zone transfer, server zone row | Region key art ×3, minimap painting |
| 2 | Blender blockout, walk export, sightline renders | Spawn rows, collider verification | 4-view sets for 4 monsters plus the boss |
| 3 | Forms pass: cliffs, landmarks, kit pieces from recipes | Monster AI variants | Tripo monster geometry |
| 4 | Terrain, grass, water and tree recipes; lighting preset | Encounters, the field boss | Tripo textures, then the Blender rigs |
| 5 | Dressing bake, materials, props, ambient zones | VFX for the boss and region weather | Painted texture fixes |
| 6 | Captures, device pass, polish, the 4 verdicts | Quests, NPCs, rewards | — |

**Dungeon template, 8 weeks** (`docs/reviews/2026-10-01-dungeon-program-roadmap.md`):
- a concept pack;
- a blockout on an 8 m grid with camera collision;
- a kit and materials;
- encounters with 3 regulars and 1 boss;
- review on all four verdicts.

**Hero/class template, 4 weeks per class, 2 in parallel:**
- turnaround QA, Tripo, Blender cleanup, the XS1 rig and clips;
- skills data plus Look v2 VFX;
- a weapon with `fx_` markers;
- UI for the skill bar.

**Monster template, 2 weeks:** 4-view QA, Tripo quad 5,900, Blender with the XS1 or quadruped rig, clips, LOD0-2 with a bake, KTX2, server row, capture.

**Boss template, 4 weeks:** the monster template plus phases, telegraphs, arena keep-clear, MVP and a RewardReceipt (A17).

### 2.3 Procedural first (owner direction, 2026-10-02 21:35)

- **Dressing:** seeded scatter rules are baked into one placement file. Server colliders, the minimap and both renderers read that file. The same seed gives byte-identical output.
- **Props:** rocks, cliffs, piers, walls and ruins are seeded parametric Blender recipes with procedurally painted albedo. A new region mostly re-skins existing recipe families.
- **Generated from layout plus seeds:** water (flow, foam, depth bakes, shader motion), grass and flower distribution, and small creatures.
- **Trees:** only the CC0 kit or an approved generator. `llm.txt` bans home-made tree generators.

### 2.4 Content is data

Every content type has a schema, a validator and a content hash:
- layouts: `planning/levels/*-layout.json`;
- monster plans: `*-monsters.json`;
- skills: `xexoria.hero-skills/1`;
- dungeons: `xexoria.dungeon/1`;
- items and cards: a schema to define in M2;
- quests and dialogue: `content/source/*`;
- zones: `content/source/zones.json`.

Balance stays in data, so tuning never needs a code change.

### 2.5 Automated gates catch problems early

| Gate | Tool |
|---|---|
| Visual before/after with a noise floor | `node tools/capture/ab.mjs --label <x>` |
| Frame time, draws, memory over time | `planning/perf-ledger.jsonl` (`xexoria.ledger/1`) |
| Server scale | `tools/sweep` (500 bots, tick p95, egress) |
| Phone measurements | Perf overlay `?perf=1` (A28) on the iPhone 11 |
| Layout and spawns | `tools/levels/*` checks, plus the new `check_features.py` |
| Art inputs | `tools/art/turnaround_qa.py`, the Tripo credit guard |
| WebGPU health | 0 GPU validation errors (`root-errors-diag.mjs`) |
| Responsive UI | `tools/capture/responsive-audit.mjs` (13 devices) |
| Licences | `PROVENANCE.txt` and SHA-256 for every admitted file |

### 2.6 Cadence
- **Daily:** each agent loops build → capture → critique → repair at least 3 times. Claude verifies; Codex integrates; froggy and Tripo deliveries go through QA.
- **Weekly:**
  - an owner report with keep/drop calls;
  - one froggy batch and one Tripo batch;
  - a device run on the iPhone 11, a mid-range Android and the GTX 1050;
  - the trend of the perf ledger.
- **Monthly:** milestone burndown; re-plan the next month.
- **Quarterly:** the milestone gate review on all four verdicts (technical, visual, gameplay, device) plus owner acceptance; re-plan this document.

### 2.7 Constraints and how to lift them

| Constraint | Effect | Fix (owner decision) |
|---|---|---|
| One workstation: GTX 1050 2 GB, 15.8 GB RAM; one Blender at a time; one GPU lock | Art and capture work queue behind each other. It is today's biggest bottleneck | A second workstation or a cloud GPU VM for Blender bakes and captures roughly doubles art throughput; 32 GB of RAM |
| No device lab | Mobile numbers are guesses until measured | iPhone 11 (owned), iPhone 16 Pro Max, a mid-range Android, an RTX 5060 desktop, or paid cloud devices |
| Owner decision bandwidth | Work blocks on keep/drop | A weekly batched decision list (§11) |
| Tripo credits | Monster and boss throughput | One pot per milestone (§8) |
| Agent context limits | Rework after compaction | Handoff docs, memory, receipts. Fast Jev for CLI sessions once the owner allows the last hook write |

## 3. Timeline: 8 quarters, 8 milestones

| # | Target date | Name | Theme |
|---|---|---|---|
| **M1** | 2026-12-18 | Sunmeadow vertical slice | One excellent region, two heroes, the core loop, mobile at 30 fps |
| **M2** | 2027-03-26 | Closed alpha 1 | 6 base classes, 3 regions, the first dungeon, items/cards v1 |
| **M3** | 2027-06-25 | Closed alpha 2 | Lava and forest regions, refine, crafting, vending, guilds |
| **M4** | 2027-09-24 | Second jobs | 6 second classes, PvP arena, the cave dungeon |
| **M5** | 2027-12-17 | Open beta | 8 regions, 5 dungeons, multi-zone servers, live ops |
| **M6** | 2028-03-24 | Beta live | 9 of 12 second classes, seasonal events, low-end Android |
| **M7** | 2028-06-23 | Launch candidate | Content complete: 10 regions, 8 dungeons, 12 classes, guild siege |
| **M8** | 2028-09-22 | 1.0 launch | Launch, live-ops cadence, post-launch roadmap |

### M1: Sunmeadow vertical slice (target 2026-12-18)

**World:**
- the city hub with the r6 dressing promoted;
- **Sunmeadow v3**: grotto, Lotus Mere, Brightwater Cove, the croft, flowing water and waterfall, grass and trees in the wind, animals, clouds, and the painted minimap (handoff §14);
- **Rimecrest v1** built from its layout;
- warps: city dais, Windstone portal, the south gate locked.

**Heroes:**
- 02 witch: 6 skills plus basic, Look v2 VFX;
- 01 orc via Tripo, playable;
- 04 and 06 rigged.

**Monsters:**
- the Sunmeadow roster: Mossling, Puddlekin, Thistle Boar, Brookclaw, Glade Wisp, Turfback Matriarch (elite) and Galehorn (boss);
- the 4 Rimecrest monsters and the Solar Scorpion (Stage C).

**Systems:**
- deep review P0 01-08 closed: movement and camera, one readable combat set, a self-playing tutorial, an inventory that never loses items, a small party loop, chat safety, load/save/reconnect, readability;
- inbox A1-A17 and A31-A36;
- protocol v8;
- death UI (C4), load states (C5), the skill bar (C8), warp UI (C9), nameplates (C1), damage numbers (B2), the minimap UI;
- the perf overlay (A28).

**Tech:**
- the WebGPU P0 fixed, with 0 GPU errors;
- iPhone 11 on Medium: 30 fps, p95 ≤ 33.3 ms in Sunmeadow, within 500/700 MiB;
- GTX 1050 on High at 1080p: p95 ≤ 16.7 ms;
- the 500-bot sweep: egress ≤ 15 Mbit/s, tick p95 within budget;
- boot ≤ 1.5 MB for login (C7).

**Gate:**
- all four verdicts, with the evidence package from `llm.txt`;
- owner acceptance;
- a friends test with 10-20 players.

### M2: Closed alpha 1 (target 2027-03-26)

- **World:**
  - Southreach, Lv 10-20;
  - the Sunken Temple of Aurel: dungeon milestones D1-D3, including camera collision;
  - Rimecrest art complete;
  - the lava key art approved.
- **Classes:**
  - all 6 base heroes playable, each with 6 skills, a basic attack and its weapon;
  - level caps: base 30, job 20.
- **Items v1:**
  - the item and card schema, plus validators;
  - about 120 items, with drop tables and NPC shops;
  - about 20 cards;
  - storage.
- **Quests:**
  - main story chapters 1-2;
  - 20 side quests;
  - the tutorial.
- **Social:** party finder, friends, chat channels.
- **Tech:**
  - accounts and auth hardening;
  - persistence (database), migrations and backups;
  - telemetry and crash reports;
  - anti-cheat basics: server authority, rate limits, sanity checks;
  - deploy pipeline: staging plus production;
  - 2 channels.
- **Gate:**
  - 50-100 testers;
  - day-1 and day-7 retention measured;
  - no P0 bugs open.

### M3: Closed alpha 2 (target 2027-06-25)

- **World:** Ashveil Caldera (lava: F18, F19 Emberwright), Whisperwood (forest), and the Whisperwood Hollow dungeon.
- **Systems:**
  - refine +1..+10;
  - enchant v1;
  - crafting v1 and vending v1 for the Merchant line;
  - mail;
  - guilds v1: create, join, ranks, chat;
  - MVP and world boss v1;
  - weather in every region.
- **Level cap:** 45.
- **Gate:**
  - 200-500 testers;
  - an economy telemetry report on sources and sinks;
  - an inflation check.

### M4: Second jobs (target 2027-09-24)

- **Classes:** 6 second classes, one branch per base class, with original names. Each has 6 new skills, 2-3 passives and a job-change quest.
- **World:** Cloudshoal Isles, or another region if the owner drops it. The Gloamcrystal Caverns dungeon.
- **PvP:** arena v1 (1v1, 3v3) with normalised stats; ranked seasons later.
- **Level cap:** 60.
- **Gate:**
  - combat simulations for balance;
  - a PvP fairness review;
  - tier performance checks with second-class VFX.

### M5: Open beta (target 2027-12-17)

- **World:** 8 regions, 5 dungeons, including the Halls of the Frost Jarl.
- **Systems:**
  - guild siege prototype (owner decision);
  - events engine;
  - GM tools, moderation, reports;
  - anti-cheat v2;
  - payments, if the owner chooses them (cosmetic-first);
  - full Thai and English localisation.
- **Tech:**
  - zone servers behind a world router;
  - a 2,000 CCU load test at twice the expected peak;
  - CDN, autoscaling, monitoring, alerting.
- **Gate:**
  - open beta launch;
  - security review;
  - a load test passed.

### M6: Beta live (target 2028-03-24)

- **Content:**
  - one more region and one more dungeon;
  - seasonal event #1;
  - a battle pass if the owner chooses one.
- **Classes:** the second branch for 3 base classes, making 9 of the 12 second classes.
- **Level cap:** 70.
- **Gate:**
  - retention targets;
  - low-end Android passes on the Low tier.

### M7: Launch candidate (target 2028-06-23)

- **Content complete for 1.0:**
  - 10 regions and 8 dungeons;
  - all 12 second classes;
  - level cap 80;
  - guild siege live;
  - endgame: the endless tower, world bosses, MVP cards.
- **Polish:** UX, onboarding, accessibility, an audio pass (music and SFX).
- **Gate:**
  - content lock;
  - performance certified on every device class;
  - security and privacy review.

### M8: 1.0 launch (target 2028-09-22)

- **Launch** with a live-ops cadence: a patch every 2 weeks and a content drop every 6 weeks.
- **Post-launch roadmap:** transcendent or third classes, and a new continent.

## 4. Content counts per milestone (cumulative targets)

| | M1 | M2 | M3 | M4 | M5 | M6 | M7/M8 |
|---|---|---|---|---|---|---|---|
| Regions (+ city) | 2 | 3 | 5 | 6 | 8 | 9 | 10 |
| Dungeons | 0 (D1 system) | 1 | 2 | 3 | 5 | 6 | 8 |
| Base / second classes | 2 / 0 | 6 / 0 | 6 / 0 | 6 / 6 | 6 / 6 | 6 / 9 | 6 / 12 |
| Regular monster types | 10 | 18 | 28 | 34 | 46 | 52 | 60 |
| Elites / field bosses | 2 / 2 | 3 / 3 | 5 / 5 | 6 / 6 | 8 / 8 | 9 / 9 | 10 / 10 |
| Dungeon / world bosses | 0 / 0 | 1 / 0 | 2 / 1 | 3 / 1 | 5 / 2 | 6 / 2 | 8 / 3 |
| Items / cards | 40 / 0 | 120 / 20 | 200 / 35 | 260 / 45 | 320 / 60 | 360 / 70 | 400 / 80 |
| Main chapters / side quests | 1 / 8 | 2 / 20 | 4 / 40 | 5 / 55 | 7 / 80 | 8 / 90 | 10 / 110 |
| Level cap (base) | 15 | 30 | 45 | 60 | 60 | 70 | 80 |

## 5. Systems roadmap

| Area | M1 | M2 | M3 | M4 | M5 | M6-M8 |
|---|---|---|---|---|---|---|
| **Core loop** (deep review P0) | P0 01-08 closed; reconnect; idempotent rewards | Hardening; analytics | — | — | — | — |
| **Combat** | One readable set; telegraph shapes; hit feedback; witch 6 skills; reactions off | 6 classes; combo windows; balance tool | Elemental tuning | Second-class kits; PvP normalisation | — | Third-class prototype (post-launch) |
| **Progression** | Base/job levels to 15; stats | To 30; skill points | To 45 | Job change; to 60 | — | To 70, then 80 |
| **Items** | Equipment v0 | Schema, 120 items, cards v1, shops, storage | Refine, enchant, crafting | Card sets | Cosmetics (owner) | 400 items, 80 cards |
| **Economy** | Escrow ledger for rewards | NPC shops; sinks | Vending, mail | Market telemetry | Auction (owner) | Live balance |
| **Social** | Party loop; chat safety | Party finder, friends, channels | Guilds v1 | Guild skills | Guild siege prototype | Guild siege live |
| **Encounters** | Galehorn MVP + RewardReceipt | Dungeon boss phases | World boss v1 | — | Events engine | Seasonal events |
| **World** | Warps; zone transfer | Instances (D1-D3) | Weather everywhere | — | World router, multi-zone | — |
| **UI** | Nameplates, damage numbers, death, load states, skill bar, warp UI, minimap | Inventory, shops, quest log | Guild UI, vending UI | Job change UI | Settings, accessibility | Polish |
| **Platform** | Tiers, FSR, frame pacing, overlay | Android pass | — | — | App wrappers (owner) | Certification |

## 6. Tech roadmap

| Track | M1 | M2-M3 | M4-M5 | M6-M8 |
|---|---|---|---|---|
| **Client rendering** | WebGPU P0 fix (combat-text buffers); KTX2 everywhere; city build-time join; streaming cells; terrain splat at ≤ +0.8 ms; trees with wind and impostors; water and grass modules; VAT crowds | AssetContainers per zone; texture budgets per tier; shader warm-up gate (A25) | Second-class VFX budgets; dynamic resolution on phones | Final tier certification |
| **Server** | Protocol v8 (AOI, delta, encode once); A33 collision parity; tick profile; 500-bot gate | Persistence (database) and migrations; auth; rate limits; instance reservation | World router + zone servers; 2,000 CCU | Shard ops; live patching |
| **Tools** | Capture harness; ledger; sweep; layout and feature checks; dressing generator; minimap renderer | Item/card/quest validators; balance simulator | Telemetry dashboards | GM tools |
| **Infra** | Vercel static plus one game server | Staging + production; backups | CDN; autoscaling; monitoring | On-call runbooks |
| **Security** | Server authority; chat filter | Anti-cheat basics; abuse reports | Anti-cheat v2; pen test | Security review |
| **QA** | Device runs: iPhone 11, GTX 1050 | Android mid-range; regression packs | Load tests | Certification matrix |

## 7. Art and asset pipeline at speed

- **One recipe library, grown each region:**
  - rock and cliff families;
  - water recipes for streams, ponds, lakes and waterfalls;
  - grass and flower families;
  - dressing rule presets: meadow, forest edge, shore, snow, ash;
  - building kits: croft and village pieces from Quaternius CC0;
  - ruins;
  - lighting presets per biome.
- **Materials:** the stylised CC0 library (17 hand-painted 4K sets) plus the texture forge. Each region adds 2-4 painted sets from froggy F4-style tasks.
- **Characters:** the XS1 shared skeleton and the UAL CC0 clips. Bows and staffs are Blender builds. Second classes reuse base bodies with new gear sets, so Tripo builds the gear pieces only.
- **Minimaps:** every region gets a minimap base from the layout, a froggy painting and an overlay QA check.
- **Asset board:** `docs/plans/2026-10-02-asset-production-board.md` stays the single source of truth for status per asset.

## 8. Budgets (estimates; the owner approves each pot)

**Tripo credits**, at 2026-10-02 Studio prices (credit guard §5.5):

| Pot | Count | Plan | Worst case (one retry each) |
|---|---|---|---|
| Heroes 01-06 + weapons | 6 + 3 | ≈ 1,275 | ≈ 2,175 |
| Each region (4 monsters + boss + 1-2 hero props) | 9 more regions | ≈ 950 each, ≈ 8,550 total | ≈ 13,000 |
| Each dungeon (3 monsters + boss) | 8 | ≈ 570 each, ≈ 4,560 total | ≈ 7,800 |
| Second-class gear sets | 12 | ≈ 270 each, ≈ 3,240 total | ≈ 5,400 |
| **Two-year total** | | **≈ 17,600** | **≈ 28,400** |

The Studio balance seen on 2026-10-01 was 25,125, so the plan fits; the worst case does not. The credit guard and staged spending keep the real number near plan.

**Owner decisions on hardware and services:**
- a second workstation or cloud GPU;
- device lab purchases;
- hosting (game servers, database, CDN), sized from the 500-bot sweep result per shard;
- an optional audio budget (music, SFX).

## 9. Quality gates (every milestone)

1. The four verdicts, technical, visual, gameplay and device, each pass on its own. A failure in one cannot be offset by another (`llm.txt` rule 7).
2. The evidence package from `llm.txt`:
   - CONCEPT / BLENDER REVIEW / BABYLON CAPTURE labels;
   - player, side, close and elevated views;
   - both renderers;
   - numbers with device, renderer, resolution and preset.
3. Performance per tier holds on real devices, including memory, and network numbers come from the sweep.
4. No open P0 bug. Each P1 has an owner and a date.
5. Owner acceptance, with a written keep/drop list.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Scope creep** (more regions or classes before the loop is fun) | `llm.txt` rule 1: finish one excellent region first. Gates before scale. Re-plan quarterly |
| **IP likeness** (RO, WoW, Genshin, Lumivara) | Originality checks in every brief; renames such as Starless Hollow; no reference art in the repo |
| **Mobile performance** | Tier budgets, the overlay, device runs every week, FSR, VAT crowds, KTX2 |
| **WebGPU regressions** | 0-validation-error gate; renderer per device class by measurement; WebGL2 fallback |
| **Server scale** | Protocol v8, sweeps at each milestone, world router at M5 |
| **Single-machine bottleneck** | A second workstation or cloud GPU (owner); Blender queue discipline; cloud art through froggy |
| **Agent quality drift and re-prompting** | Detail-first briefs; at least 3 repair passes; independent Claude verification; handoffs and memory |
| **Licence risk** (Quaternius QAL, CC-BY, RaGEZONE) | Provenance per file; the `llm.txt` licence rules; owner approval outside CC0 |
| **Tripo cost overrun** | Credit guard, staged spend, a pot per milestone, Blender for thin parts |
| **Owner bandwidth** | A weekly decision list; defaults chosen by Claude when a decision is reversible |

## 11. Owner decisions, by the milestone they block

| Decision | Blocks | Claude's recommendation |
|---|---|---|
| Tripo pots: Sunmeadow 705, Rimecrest 550, bosses 435 | M1 | Approve the Sunmeadow and Rimecrest pots now |
| Second workstation or cloud GPU, more RAM | M1 speed | Yes: the biggest throughput gain available |
| Device lab: Android mid-range, iPhone 16 Pro Max, RTX 5060 | M1/M2 gates | At least one mid-range Android before M2 |
| Monetisation model (cosmetic shop, battle pass, none) | M5 | Cosmetic-only plus an optional pass, never pay-to-win |
| Guild siege scope | M5/M7 | Prototype at M5, live at M7 |
| Number of second classes (6 or 12) at 1.0 | M4/M7 | 12, two per base, as in RO |
| Level cap at 1.0 | M7 | 80 |
| Auction house or vending only | M3/M5 | Vending at M3; decide on an auction house at M5 from the economy data |
| App wrappers (iOS/Android stores) | M5 | After the open beta, if web retention is good |
| Regions to keep: Whisperwood, Cloudshoal Isles | M3/M4 | Keep both: they reuse mature pipelines |
| Display names: Rimecrest, Ashveil Caldera, Emberwright, Mirun | M1/M3 | Run an originality check, then confirm |
| Hosting budget | M2 | Size it from the 500-bot sweep per shard |

## 12. The next 11 weeks, to M1 (week by week)

| Week | Dates | Claude (maps and visuals) | Codex (root, VFX, UI, side chats) | froggy / Tripo / owner |
|---|---|---|---|---|
| W0 | Oct 2-4 | Main-map agents run: layout v3 + procedural dressing, props, water, grass, wildlife. Witch, city r6, trees, terrain cost | WebGPU P0 (combat-text buffers); A33 homes; skills catalog + validator; v8 measurements | F5 clouds; S7 hero 01 geometry (Claude reviews it) |
| W1 | Oct 5-11 | Integrate trees → terrain → water → grass into `environment.ts`; props P1; Sunmeadow v3 captures; minimap base | A1-A8 + A16; A28 overlay; tick-profile patch; 500-bot sweep | F4 terrain, F3 leaves, F24 minimap; heroes 04/06 Tripo; owner: first iPhone 11 run |
| W2 | Oct 12-18 | Props P2/P3 placed from the dressing bake; grotto, mere, cove, croft built; light pass 1; Rimecrest blockout | A35 warps; C9 warp UI; C8 skill bar; minimap UI from `ui-spec.md` | F09, Rimecrest key art; Mossling S1 and Galehorn Tripo |
| W3 | Oct 19-25 | Heroes 01/04/06: cleanup, XS1 rig, clips, LOD bake; city r6 promotion; Southreach layout | A31 skills live for the witch; B15 Look v2; city r6 traversal check | F13-F16; hero 03/05 regen QA |
| W4 | Oct 26-Nov 1 | Rimecrest art (snow recipes); Solar Scorpion Stage C; bovine NPC; dungeon D1 kit start | Dungeon transition (D1) + camera collision; A36 boss row | Rimecrest monsters in Tripo; lava key art F18 |
| W5 | Nov 2-8 | Sunmeadow monsters built (Thistle Boar, Brookclaw, Turfback, Glade Wisp); wildlife models placed | Wildlife runtime (`ambient-*.ts`); clouds B5; weather B8 | F19 Emberwright; SKILLS sheets |
| W6 | Nov 9-15 | Mobile tier tuning from the device runs; city join (memory); boot KTX2 | A22-A24 memory and boot; A29 iOS fixes | Owner: Android device run |
| W7 | Nov 16-22 | Tutorial spaces in Sunmeadow; readability pass | P0 03 tutorial, P0 04 inventory, P0 05 party loop; C4/C5 | — |
| W8 | Nov 23-29 | Galehorn arena polish; night lighting; fireflies | A17 encounter + MVP + RewardReceipt; Look v2 for the orc and Galehorn | — |
| W9 | Nov 30-Dec 6 | Full-slice internal playtest; bug burndown; captures | Bug burndown; load test | Owner playtest |
| W10 | Dec 7-13 | Polish; perf gates | Staging deploy; friends-test prep | — |
| W11 | Dec 14-18 | **M1 gate review** (four verdicts) | M1 gate | **Friends test (10-20 players)**; owner acceptance |

## 13. How this plan stays true

- **Quarterly re-plan:** measure the region, dungeon, monster and hero cycle times, and shrink or grow scope from them. Keep the dates, not the counts, unless the owner decides otherwise.
- **Status lives in the files:** the task graph JSON, the asset board, the perf ledger and the handoff doc. Never trust memory.
- **Every agent brief cites** this plan's milestone and gate, so work always points at the next gate.
