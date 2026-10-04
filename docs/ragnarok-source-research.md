# Ragnarok source and database research — baseline audit 01

**วันที่ตรวจ:** 23 กันยายน 2026  
**คำขอ:** ศึกษาข้อมูลในเกมทุกหมวดจาก source และเว็บอ้างอิงเพื่อทำใหม่ให้เทียบต้นฉบับได้ละเอียด  
**สถานะ:** ทำ source inventory ครอบคลุมขอบเขตไฟล์ที่ระบุแล้ว; ตรวจเว็บทั้ง 5 แหล่งในระดับหน้าหลัก/ตัวอย่าง; ยังไม่ใช่การตรวจ semantic ทุก record หรือพิสูจน์เกมเหมือนต้นฉบับ 100%

## 1. ข้อค้นพบที่เปลี่ยนวิธีทำงาน

ต้องแยก **ข้อเท็จจริงของเกมต้นฉบับ** ออกจาก **การออกแบบ Aetherfield**. แผน v4 ที่ใช้ party 4 คน, WASD/dodge/action combat และ personal guaranteed drops เป็น adaptation ไม่ใช่หลักฐานว่าตรง RO. งาน research นี้จะเก็บ source behavior ก่อน แล้วระบุความต่างของเกมใหม่อย่างตรงไปตรงมา; การพบระบบเดิมไม่ได้แปลว่าระบบนั้นถูก implement แล้ว

Source ที่มีคือ rAthena server emulator แบบ C++ ไม่ใช่ source client หรือ source ภายใน Gravity. Pin ที่ตรวจ: `e985006171d2eb320ee512a653f4c83aea3d81b6`; ดู [README](../references/rathena/README.md) และ [LICENSE](../references/rathena/LICENSE). ไม่ pull หรือแก้ checkout ระหว่าง audit. Snapshot หนึ่งไม่รับประกันว่าตรง server ไทย/iRO/kRO ปัจจุบัน

MidgardHub ระบุ **Ragnarok Zero Global** และ 4,065 items พร้อมวันที่อัปเดต 22.09.2026 บนหน้าที่อ่านได้; เป็นข้ออ้างของเว็บไซต์ ไม่ใช่จำนวนที่เราตรวจ independently. แหล่งนี้ต้องอยู่คนละ dataset กับ Renewal. หน้ามีข้อจำกัดการคัดลอก/scrape จึงใช้เป็น reference metadata และไม่ mirror database. [MidgardHub items](https://midgardhub.com/database/items)

## 2. แหล่งข้อมูลและบทบาท

| แหล่ง | ตรวจได้ในรอบนี้ | ใช้เพื่ออะไร | ข้อจำกัด |
|---|---|---|---|
| [RateMyServer sitemap](https://ratemyserver.net/sitemap.html) | อ่านได้; มีทางแยก Pre-Re/Renewal, items, monsters, maps, NPCs, shops, skills, crafting/quests | taxonomy และ lookup ตาม ID/โหมด | Community database; อย่าสรุปว่าตรง official region ทุกค่าจากชื่อเดียวกัน |
| [iW weapon search](https://db.irowiki.org/db/weapon-search/?search&sort=1,1) | หน้าแสดง 1,050 results ใน view ที่ตรวจ; เปิด item 18180 ได้ | ตรวจชนิดอาวุธ, requirements, stats และ price semantics ตัวอย่าง | จำนวนนี้เป็นผลค้นหาอาวุธในเว็บ ไม่ใช่ item catalog ทั้งเกม |
| [MidgardHub](https://midgardhub.com/database/items) | อ่าน metadata หน้าได้; ไม่ดึงรายการทั้งหมด | Zero-only source candidate | Zero ไม่ใช่ Renewal; ไม่มี permission สำหรับ bulk republication ที่ยืนยันแล้ว |
| [iRO Wiki](https://irowiki.org/wiki/Main_Page) | อ่าน navigation, controls และ instance page ได้ | player-facing flows, UI, social/quest systems | Wiki ชุมชน; ตรวจ region/date/page-specific rules |
| [Ragnarok Fandom](https://ragnarok.fandom.com/wiki/Ragnarok_Wiki) | direct open ล้มเหลว/robots; search index ให้ summary | lore/franchise coverage และ discovery | ไม่อ้างว่าเปิดตรวจทุกหน้า; ครอบคลุมหลายเกมรวม RO2 จึงต้องกรอง product |

เว็บเป็นหลักฐานประกอบ ไม่ใช่ runtime authority หรือใบอนุญาตใช้ code/art/text. รอบนี้ไม่มี login, script execution, web publishing หรือ bulk website scraping

## 3. Inventory ที่รันจริง

สร้าง [ตัวทำดัชนี](../tools/ragnarok_research_inventory.py) ใช้ PyYAML ที่มีอยู่ อ่าน `db/**/*.yml`, `npc/**/*.yml`, NPC `.txt/.conf`, map index, text DB, configuration และ manifest C++ mechanics. ไม่ execute NPC scripts และไม่ import เข้าเกมใหม่

```powershell
python -B tools/ragnarok_research_inventory.py
```

ผล [summary.json](../exports/ragnarok-research/summary.json):

| ขอบเขต | จำนวนที่นับได้ | ความหมาย |
|---|---:|---|
| YAML database files | 200 | รวม common, re, pre-re และ templates; parse error 0 |
| Database header types | 46 | ประเภทที่พบจาก Header.Type |
| Top-level Body records | 64,219 | source declarations รวมทุก mode; **ห้ามนับเป็น unique live records** |
| Map index entries | 1,295 | ID/name registry; ไม่ยืนยันว่ามี renderable map หรือถูกโหลด |
| NPC text/config files | 1,159 | source files, ไม่ใช่ NPC entities |
| C++ map subsystem files | 2,577 | recursive .cpp/.hpp manifest; รวม class/skill modules |

Renewal-only **declared records** ที่สำคัญ:

| ประเภท | จำนวน | ต้องตรวจต่อ |
|---|---:|---|
| Items | 29,356 | 20,053 มี script field; numeric columns อย่างเดียวไม่ครบ effect |
| Monsters | 2,675 | AI, skills, spawn, config rate modifiers อยู่นอก mob row |
| Skills | 1,635 | formulas และ per-skill code ไม่อยู่ YAML ทั้งหมด |
| Skill-tree records | 175 | inheritance/variants; ไม่ใช่ 175 playable jobs |
| Quest DB records | 4,821 | ไม่เท่ากับจำนวน quest stories หรือ NPC quest chains |
| Item groups | 2,996 | ไม่ใช่กล่องขาย 2,996 แบบ; scripts ต้องอ้างถึง group ด้วย |
| Item packages | 79 | package rules แยกจาก item groups |
| Item combinations | 5,114 | ต้อง resolve IDs และ effect scripts |
| Instances | 78 | lifecycle DB + scripts + map flags + quest cooldown |
| Pets | 107 | tame/food/egg/intimacy/skill/script relationships |
| Status definitions | 1,018 | durations, stacking/cure, client state และ combat logic |
| Achievements | 361 | conditions/rewards ต้อง trace |
| Barter records | 114 | shop definition + requirements/material cost |

Additional Renewal relationship counts: ordinary drop entries 12,823; MVP drop entries 516; item-group subgroups 3,105; subgroup item entries 34,315. These are nested entries, not item-definition counts

NPC lexical matches: script 10,068; duplicate 11,774; warp 4,462; mapflag 6,138; shop 405; cashshop 18; marketshop 45; monster spawn declarations 10,243; boss spawn declarations 122. **ยังไม่ใช่ loaded NPC/spawn count**: config อาจปิดไฟล์, mode เลือกไฟล์ต่างกัน, duplicate และ dynamic scripts เปลี่ยนผลจริง. NPC scanner เป็น lexical candidate index ไม่ใช่ script VM

## 4. Output สำหรับค้นหาและแปลงต่อ

| Artifact | ใช้ตรวจ |
|---|---|
| [records.jsonl](../exports/ragnarok-research/records.jsonl) | แต่ละ record มี mode, type, key/name, source file, `/Body/N`, commit, field names และ script hash; ไม่ฝัง dialogue/script bodies |
| [database-files.csv](../exports/ragnarok-research/database-files.csv) | SHA-256, schema version, mode, Body count และ parse status ทุก YAML |
| [field-catalog.json](../exports/ragnarok-research/field-catalog.json) | field paths จริงที่พบ รวม nested fields |
| [imports.json](../exports/ragnarok-research/imports.json) | Footer imports/mode/path existence; ยังไม่ merge effective rows |
| [NPC declarations](../exports/ragnarok-research/npc-declarations.csv) | candidate declaration, location, type, name/value, source line |
| [NPC load references](../exports/ragnarok-research/npc-load-references.csv) | uncommented include/import references และ path ที่มี/ไม่มี |
| [Map index](../exports/ragnarok-research/map-index.csv) | stable map IDs ที่คำนวณทั้ง explicit และ implicit index |
| [Text DB inventory](../exports/ragnarok-research/text-database-files.json) | mob skill/production/no-equip/no-cast และ text tables; จำนวน line ไม่ใช่ semantic record |
| [Config manifest](../exports/ragnarok-research/config-files.json) | configuration hashes เพื่อไม่ทำข้อมูล default กับ custom ปนกัน |
| [Mechanics source](../exports/ragnarok-research/mechanics-files.json) | C++ paths/hashes สำหรับ trace formulas และ behavior |
| [Existing item viewer](../exports/rathena-items/index.html) | ค้น 29,356 Renewal item records แบบ offline จาก export เดิม |

Indexes are research-only. `duplicate_source_keys` เป็น candidate key collisions จาก heuristic; JOB_STATS มีข้อมูลหลายตารางต่อ job และบาง row ไม่มี stable key จึงไม่ใช่ verdict ว่า source ผิด. Missing `db/import` paths อาจเป็น optional custom files ที่ยังไม่สร้าง

## 5. Mapping ระบบ → source ที่ต้องอ่าน

Paths below are relative to `references/rathena/`; database wrappers select mode-specific imports. File presence proves an implementation location, not correctness or fidelity to every official server.

| ระบบ | Data/config | Mechanics / scripts |
|---|---|---|
| Item/equipment/card | `db/re/item_db_{equip,etc,usable}.yml` | `src/map/itemdb.cpp`, `pc.cpp`, `status.cpp` |
| Combo/random option | `item_combos.yml`, `item_randomopt_db.yml`, `item_randomopt_group.yml` | `itemdb.cpp`, `status.cpp`, item scripts |
| Boxes/packages | `item_group_db.yml`, `item_packages.yml` | `doc/item_group.txt`, `itemdb.cpp`, `script.cpp` |
| NPC/cash/barter shops | `db/item_cash.yml`, `npc/barters.yml` and mode imports | `npc/merchants/shops.txt`, `cashshop.cpp`, `npc.cpp` |
| Refine/grade/enchant/reform | `refine.yml`, `enchantgrade.yml`, `item_enchant.yml`, `item_reform.yml` | `npc/merchants/refine.txt`, `advanced_refiner.txt`, `itemdb.cpp` |
| Craft/brew/cook/synthesis | `produce_db.txt`, `create_arrow_db.yml`, `laphine_*.yml` | `skill.cpp`, per-skill source, `npc/merchants/alchemist.txt` |
| Jobs/EXP/traits | `job_stats.yml`, `job_exp.yml`, `job_aspd.yml`, `job_basepoints.yml`, `statpoint.yml` | `pc.cpp`, `status.cpp`, `npc/jobs/` |
| Skills/skill tree | `skill_db.yml`, `skill_tree.yml`, `skill_nocast_db.txt` | `skill.cpp`, per-class subdirectories, `npc/quests/skills/` |
| Damage/status/elements/size | `status.yml`, `attr_fix.yml`, `size_fix.yml` | `battle.cpp`, `status.cpp`, `conf/battle/` |
| Monster/AI/spawn/drop | `mob_db.yml`, `mob_skill_db.txt`, `mob_summon.yml`, `map_drops.yml` | `mob.cpp`, `npc/mobs/`, `conf/battle/drops.conf` |
| Quest progress/story | `quest_db.yml` | `quest.cpp`, `npc/quests/`, `npc/re/quests/`, script VM |
| NPC dialogue/services | `npc/scripts_athena.conf`, `scripts_jobs.conf` | `npc/cities/`, `npc/kafras/`, `npc/merchants/`, `npc.cpp` |
| Map graph/warps/flags | `map_index.txt`, `conf/maps_athena.conf`, map caches | `npc/warps/`, `npc/mapflag/`, `map.cpp`, `unit.cpp`, `path.cpp` |
| Instances | `instance_db.yml` | `instance.cpp`, `npc/instances/`, per-instance scripts |
| Party | `conf/battle/party.conf`, `conf/inter_athena.conf` | `party.cpp`, `src/common/mmo.hpp` |
| Guild/siege | `castle_db.yml`, `guild_skill_tree.yml`, `exp_guild.yml` | `guild.cpp`, `npc/guild/`, `npc/guild2/` |
| Battleground/PvP | `battleground_db.yml`, map flags | `battleground.cpp`, `npc/battleground/`, `battle.cpp` |
| Pet/homunculus/mercenary/elemental | corresponding `*_db.yml`, EXP tables | `pet.cpp`, `homunculus.cpp`, `mercenary.cpp`, `elemental.cpp` |
| Inventory/cart/storage | item flags, storage configuration | `pc.cpp`, `storage.cpp`, `clif.cpp` |
| Trade/vending/buying store | item trade flags and feature config | `trade.cpp`, `vending.cpp`, `buyingstore.cpp` |
| Mail/auction | item/mail constraints and config | `mail.cpp`, `auction.cpp`, `clif.cpp` |
| Achievements/attendance/reputation | corresponding YAML + level/group DB | `achievement.cpp`, scripts, player state |
| Marriage/adoption/family | class/skill constraints | `pc.cpp`, `script.cpp`, family scripts and packet handlers |
| UI/chat/control/appearance | server interfaces, skill/item IDs, client config | `clif.cpp`, `chat.cpp`; actual client windows/assets are external |
| Account/character persistence | `sql-files/`, account and inter-server config | `src/login/`, `src/char/`, `src/map/` ownership boundaries |

## 6. ตรวจข้อมูลจริงข้ามแหล่ง: item 18180

ใช้ ID เดียวกัน ไม่ใช้ชื่อคล้ายกัน: [iW item](https://db.irowiki.org/db/item-info/18180/), [RMS Renewal item](https://ratemyserver.net/index.php?item_id=18180&page=re_item_db), [local equipment DB](../references/rathena/db/re/item_db_equip.yml), record `/Body/3817`.

| Field | Local source | iW / RMS observation | ผลตรวจ |
|---|---|---|---|
| ID/subtype | 18180 / Bow | ID 18180 / Bow | identity matches |
| ATK | 190 | 190 / 190 | matches sample |
| Slots | 2 | name suffix [2] / 2 | matches sample |
| Weapon level / required level | 4 / 130 | 4 / 130 | matches sample |
| Weight | 600 internal units | 60 / 60 display | matches after conversion ×0.1 |
| MATK | absent scalar; script bonus 135 | 135 / description 135 | missing scalar must not become zero effect |
| Buy/Sell | Buy 20; Sell omitted | iW buy unavailable, sell 0; RMS 20/10 | conflict: preserve variants; do not average or overwrite |

Weight scale and price defaults are documented in [item_db.txt](../references/rathena/doc/item_db.txt). [itemdb.cpp](../references/rathena/src/map/itemdb.cpp) derives Sell from Buy when missing, then applies an anti-arbitrage check. Thus absent YAML field is not equivalent to a zero/unknown runtime value. The price conflict is recorded, not resolved by assuming one region is wrong.

Effect descriptions can also differ in scope (weapon-type damage versus ranged damage). Verify actual bonus semantics in C++/script constants and build configuration before claiming numerical parity; matching the displayed ATK is insufficient

## 7. กล่องสุ่ม: สิ่งที่ converter ห้ามทำผิด

[doc/item_group.txt](../references/rathena/doc/item_group.txt) และ [itemdb.cpp](../references/rathena/src/map/itemdb.cpp) แยก:

- **Random:** rate เป็น relative weight ใน subgroup; 5 และ 1 ให้ 5/6 กับ 1/6 เมื่อไม่มีเงื่อนไขอื่น
- **All:** ให้ทุก entry ตาม command semantics; rate ต้องไม่กำหนดหรือเป็น 0
- **SharedPool (default ใน snapshot นี้):** rate เป็นจำนวนใน pool; สุ่มแล้วลด pool จึงมีความน่าจะเป็นแบบมี state จน refill/restart

Renewal inventory พบ All 2,094 subgroups, Random 312, unspecified/default SharedPool 699. ต้องเก็บ algorithm, subgroup, command caller, quantity, rental duration, binding, refine/grade, random options, source config modifiers และ pool lifecycle. ห้ามนำ `Rate: 100` ไปแสดงเป็น 100% โดยอัตโนมัติ. Source item groups ไม่ใช่หลักฐาน odds ปัจจุบันของ paid box ใน official server

## 8. ข้อมูลที่ต้องอ่านลึกกว่าตาราง

**Skills/jobs:** skill-tree inheritance ไม่ได้หมายถึงรวม child trees ทุกทอด; schema comment ระบุขอบเขต inheritance. JOB_STATS rows จากหลายไฟล์ต่อ job ต้อง merge ตาม loader. Fourth-job trait fields ปรากฏใน source จึงห้ามจำกัด research ไว้แค่หก base stats แม้ prototype ใช้ระบบง่ายกว่า

**Quest/NPC:** quest_db บอก objectives/time limits แต่บทสนทนา prerequisites, consume/grant และ custom variables อยู่ใน script. ต้องสร้าง graph จาก script commands, labels, function calls และ persistent variables แล้วแยกส่วนที่แปลความหมายไม่ได้ ไม่ควร convert ด้วย regex แล้วเรียก quest_complete

**Maps:** map index เป็น inter-server identity; cache เป็นข้อมูล server. Warp/monster/NPC placement มี coordinates แต่ไม่ได้ให้ terrain mesh/texture/sprite/UI. ต้อง trace enabled manifests และ map flags ก่อนแปลง route; sprite/visual provenance เป็นงานอีกชุด

**Instances:** lifecycle, entrance, timeout และ map copies มีใน DB; quest gates/cooldown/re-entry อยู่ใน scripts และ behavior. Wiki อธิบาย instance แบบ party-specific พร้อมข้อจำกัดการเข้า/เวลา แต่ไม่ควรนำค่าจากหน้าหนึ่งครอบทุก instance/region. [iRO instances](https://irowiki.org/wiki/Instance)

**Party/control fidelity:** source header กำหนด `MAX_PARTY 12`; Aetherfield P1 กำหนด 4 จึงเป็นความต่างที่ต้องแสดง. RO wiki อธิบาย movement ด้วย mouse/cell และ shortcuts/windows; prototype WASD/dodge/third-person ไม่ใช่ input parity. [mmo.hpp](../references/rathena/src/common/mmo.hpp), [Basic Game Control](https://irowiki.org/wiki/Basic_Game_Control)

**Family/social:** marriage/adoption, chatrooms, pet/homunculus windows, cart, mail และ shortcuts ต้องเป็นรายการแยก ไม่ซ่อนใต้คำว่า “social/UI complete”. [iRO navigation](https://irowiki.org/wiki/Main_Page) ระบุหมวดเหล่านี้; ไม่ได้แปลว่าทุกระบบพร้อมในโค้ดใหม่

## 9. นิยาม “100%” ที่ทดสอบได้

ใช้ namespace ต่อ record: `game/product + region + ruleset + patch/episode + source_commit + type + original_id`. ชื่อเดียวกันข้าม ruleset เป็น candidate match เท่านั้น. ระหว่างรอผู้ใช้เลือก baseline ให้เก็บ Renewal/Pre-Re/Zero แยกกันและไม่แก้ production balance ตามเว็บ

| Layer | ตัวหารที่ต้องตรึง | หลักฐานว่า complete |
|---|---|---|
| Source discovery | files/types/includes ของ pinned snapshot | hashes + parse errors + unresolved includes |
| Effective data | records หลัง loader defaults/imports/overrides | stable keys, no unresolved references; exact fields/source origins |
| Mechanics | behavior cases ของทุก rule/skill/status/quest branch | input→expected output, edge cases, source-function link |
| Content relationships | NPC→quest→map→spawn→drop→item→shop/box | resolved graph; no orphan/dynamic branch silently discarded |
| Player experience/UI | screen/interaction/state matrix ของ chosen version | observed flow evidence, mobile adaptation flagged explicitly |
| Runtime/assets | client/server geometry, animations/audio/UI resources | provenance + validated build + device playthrough |

รายงานแต่ละ layer แยกกัน: indexed, traced, cross-checked, disputed, implemented, tested, unavailable. ห้ามเอา 200/200 YAML parsed ไปอ้างว่า remake ทั้งเกมครบ. Source-index coverage รอบนี้ครบตาม scope ที่ประกาศ; effective runtime merge, semantic behavior, exhaustive web comparison และ UI/assets ยังไม่ครบ

## 10. งาน research ถัดไปตาม dependency

1. **RDATA-01:** mode-aware import resolver และ field defaults; แยก source provenance ทุก override; optional imports ไม่ถูกนับเป็น content หายโดยไม่ตรวจ
2. **RDATA-02:** normalized ID/reference graph; resolve Aegis names, item groups, skill prerequisites, drop/item refs และ map refs; export unresolved list
3. **RDATA-03:** effect analyzer แบบ whitelist สำหรับ item/skill scripts; ทุก unsupported builtin/branch ต้องเข้าคิว manual trace; ห้าม execute source script ใน browser
4. **RDATA-04:** enabled NPC include graph แยก modes, duplicate resolution, static shops/warp/spawn; dynamic spawn/shop/instance logic marked unresolved
5. **RDATA-05:** equivalence fixtures: เริ่ม item 18180 + consumable/card/box + monster/drop + skill + party rule + quest/instance; เพิ่มจนทุก behavior class มี case
6. **RDATA-06:** UI/control checklist และ source/client boundary, family/carts/mail/shortcuts, screenshots ที่มีสิทธิ์ใช้เป็น reference; รายงาน adaptation จากต้นฉบับ
7. **RDATA-07:** เปรียบเทียบเว็บแบบเจาะจงตาม record ID/version พร้อม contradiction ledger; ใช้ช่องทาง/API/dataset ที่อนุญาตเมื่อมี แทน mirror หน้าเว็บทั้งชุด

ผล research เป็น baseline สำหรับตัดสินใจว่าอะไรต้องตรงต้นฉบับและอะไรปรับเพื่อ browser/mobile. ยังไม่มีการนำข้อมูลเหล่านี้เข้า runtime เกมหรือประกาศว่าทุก behavior เทียบผ่านแล้ว
