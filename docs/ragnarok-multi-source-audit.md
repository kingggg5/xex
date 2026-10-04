# Ragnarok multi-source data audit

**Checked:** 2026-09-23 · **Scope:** public reference pages and the pinned local rAthena checkout · **Status:** research crosswalk, not a content import

This audit follows the request to study Ragnarok's systems and in-game data across several sites. It maps the sources to the project's 34-system catalog and records where one sample item agrees or conflicts. It does **not** claim every official regional version or every live record has been exhaustively checked.

## Working baseline and version separation

For the current plan, use the local rAthena Renewal (`re`) plus `common` definitions at commit `e985006171d2eb320ee512a653f4c83aea3d81b6` as the **implementation reference baseline**. This is an open-source server emulator snapshot, not an official Gravity server dump or a complete client-data archive. Keep Pre-Renewal and Ragnarok Zero as separate comparison tracks; never merge their records, prices, rates, progression formulas, or names into one presumed canonical database.

The target release region/build has not been established by the source list. A later choice may replace the working baseline, but it must be recorded as a versioned dataset rather than silently changing values in place.

## Source register

| Source | What it covers | How to use it | Confidence and limit |
|---|---|---|---|
| [RateMyServer site map](https://ratemyserver.net/sitemap.html) | Separate Pre-Renewal and Renewal item/monster indexes; equipment, cards, consumables, map/dungeon spawns, WoE castles, NPC and shop searches, skills, quests, and calculators. | Use as a broad coverage checklist and a community cross-check for record-level fields. | Community-maintained and server/version sensitive. The labels help keep modes apart; a page is not proof that all servers share the same data. |
| [iRO Wiki](https://irowiki.org/wiki/Main_Page), [iW weapon database](https://db.irowiki.org/db/weapon-search/?search&sort=1,1), and [item 18180](https://db.irowiki.org/db/item-info/18180/) | Player-facing mechanics and guides, plus queryable item attributes such as type, job, ATK/MATK, weight, slots, level, element, refine/break state and binding. | Use Wiki pages for mechanics and flows; use the database for comparison of named fields and examples. | Community reference focused on iRO. [iRO Wiki Classic](https://irowiki.org/classic/Main_Page) explicitly preserves Pre-Renewal material, so Classic and current iRO pages must be version-tagged separately. |
| [Midgard Community Hub item database](https://midgardhub.com/database/items) and its [Terms of Service](https://midgardhub.com/terms-of-service) | Ragnarok Zero Global data sourced from TWRo Zero; the page reports 4,065 translated items and a client-data update dated 2026-09-22. It describes Zero-specific random options, dungeon enchantments and activation upgrades. | Use only as a cited, version-specific Zero comparison. Do not build a bulk mirror or replacement database from it. | The site's Terms prohibit scraping, mirroring, bulk downloads and substantial republication without permission. The terms allow attributed summaries and short excerpts; this audit summarizes and links instead of copying its catalog. |
| [Ragnarök Wiki](https://ragnarok.fandom.com/wiki/Ragnarok_Wiki), [About the wiki](https://ragnarok.fandom.com/wiki/Ragnarok_Wiki%3AAbout_the_wiki), and [general disclaimer](https://ragnarok.fandom.com/wiki/Ragnarok_Wiki%3AGeneral_disclaimer) | Broad franchise discovery: RO, RO2, manhwa, jobs, monsters, items, places, quests and many later systems. | Use to find candidate feature families and terminology, then verify each claim against a version-specific source. | User-edited and not formally reviewed by the developer/publisher. Its pages show differing license notices (the About page and the general footer do not state the same CC variant); review the exact page/license before any reuse. This audit copies no wiki text or media. |
| [Pinned local rAthena source](../references/rathena/LICENSE), [Renewal item database](../references/rathena/db/re/item_db_equip.yml), [item loader](../references/rathena/src/map/itemdb.cpp), and [research inventory](../exports/ragnarok-research/summary.json) | Server-side schemas, values, scripts, imports, NPC declarations, map indexes and implementation behavior. | Use as the reproducible technical reference for this project's Renewal server rules. Record exact file/commit and transformations. | Repository license is GPL-3.0-or-later, with per-file headers still relevant. The server source does not grant rights to the commercial client, artwork, maps, sounds, dialogue or trademarked presentation. Imports/overrides need runtime-aware resolution. |

## Coverage crosswalk to the 34-system catalog

The links below show where to investigate each family. They do not mean every row in a website database has been imported or verified.

| Catalog IDs | Research areas | First sources to check | Current decision for the game plan |
|---|---|---|---|
| SYS-01–SYS-06 | Account/session, appearance, base/job progression, attributes, vocations and skill graph | rAthena `job_stats`, `skill_tree`, `skill_db`, `status_db`; iRO Wiki Classes/Levels/Stats/Skills; RMS class skill lists and calculators | Rebuild progression rules as versioned data; author original vocations, names and skill expression. |
| SYS-07–SYS-10 | Combat, enemy AI/status, bosses, loot and ownership | rAthena `mob_db`, `mob_skill_db`, item/drop scripts and battle code; RMS monster search; iRO Wiki combat/mechanics pages | Recreate behavior families and readable telegraphs; retain server-side eligibility and reward invariants from the existing catalog. |
| SYS-11–SYS-13 | Quest journal, NPC dialogue and town services | rAthena `quest_db`, active NPC manifests/scripts, shop definitions; RMS quest/NPC/shop search; iRO Wiki [quests](https://irowiki.org/wiki/Quest) and [instances](https://irowiki.org/wiki/Instance) | Use quest prerequisites, choices, repeat rules and service categories as a checklist. Write new dialogue and NPC identities. |
| SYS-14–SYS-16 | Zones, travel/map flags, exploration, geometry and asset pipeline | rAthena `map_index`, map flags, warps, spawn declarations and map-cache docs; RMS map/dungeon/WoE indexes; iRO world map | Preserve adjacency, portals, spawn/flag concepts, not the original cartography or client map files. Keep geometry and art original or explicitly licensed. |
| SYS-17–SYS-23 | Inventory/equipment, storage, NPC shops, boxes, cards/sockets, refining/crafting, trade/market/mail | rAthena item/group/refine/barter data and loader logic; RMS/iW item records and calculators; MidgardHub only for Zero-specific comparison | Store source edition, units, scripts and rights per record. Keep the project's free-first rule: no paid random boxes; any future earned box must disclose odds and resolve rewards atomically. |
| SYS-24–SYS-31 | Party, guild, PvP/siege, pets/companions, chat, events/achievements, exploration and instances/operations | rAthena party/guild/instance/pet/achievement code and database; RMS WoE/map/quest indexes; iRO Wiki system pages; Fandom discovery followed by source verification | Use the sources to prevent missing a system family; stage each family behind the acceptance and operations gates in v4. |
| SYS-32–SYS-34 | HUD/menus/accessibility, content/localization tools, operations/support | iRO Wiki controls and interface guides; the supplied screenshot as composition reference; rAthena client-interface protocol and content schemas | Translate desktop affordances into original responsive mobile controls, including the requested thumb joystick. Do not reproduce the screenshot's exact panel art, icons or layout. |

## Record-level cross-check: item ID 18180

This sample tests whether raw fields can be compared safely across sources.

| Field | Pinned Renewal source | iW Database | RateMyServer | Reconciliation |
|---|---|---|---|---|
| Identity/type | `AC_B44_OS`, AC-B44-OS, bow | AC-B44-OS [2], bow | AC-B44-OS [2], bow | Identity and type corroborate. |
| Attack and level | ATK 190, weapon level 4, required level 130 | ATK 190, weapon level 4, required level 130 | ATK 190, weapon level 4, required level 130 | Exact agreement for this sample. |
| Weight | Raw `Weight: 600` | Displayed 60 | Displayed 60 | rAthena documents 10 raw units per displayed weight, so 600 → 60. Never compare raw and displayed values without unit conversion. |
| Slots and special effects | 2 slots; script gives MATK +135, ranged damage +5%, refine +7 ASPD +7%, +9 Triangle Shot +15%, +11 ranged damage +10% | Same combat values/effect thresholds | Same combat values/effect thresholds | Scripts must be interpreted, not flattened to the exported scalar columns. |
| NPC prices | `Buy: 20`; `Sell` omitted, so loader default is half buy (10) | Buying price `--`; selling price 0 Z | Buy 20z; sell 10z | **Unresolved source/region/config difference.** The local emulator rule and RMS agree; iW presents different NPC price availability. Preserve both source values and resolve only against the selected live target. Do not average or overwrite. |

Local evidence: [record 18180](../references/rathena/db/re/item_db_equip.yml), [item database field rules](../references/rathena/doc/item_db.txt), and [loader behavior](../references/rathena/src/map/itemdb.cpp). External cross-checks: [iW item page](https://db.irowiki.org/db/item-info/18180/) and [RMS Renewal item page](https://ratemyserver.net/index.php?item_id=18180&page=re_item_db).

## Local snapshot facts and limits

The read-only inventory generated on 2026-09-23 indexes **200 YAML files**, **46 database types**, and **64,219 declared records** across common, Pre-Renewal and Renewal inputs. In the Renewal input alone it reports 29,356 item rows, 2,996 item groups, 2,675 mob rows, 4,821 quest rows, 1,635 skill rows, 175 skill-tree rows and 78 instance rows. These are parser counts, not unique records after imports, active runtime totals, or proof of content parity. See [summary.json](../exports/ragnarok-research/summary.json) for the count semantics and [database-files.csv](../exports/ragnarok-research/database-files.csv) for the indexed inputs.

The existing tool scans YAML and lexical NPC declarations but does not execute the NPC script VM or resolve all active runtime imports/overrides. For complete counts, the next research pass must resolve the active `scripts_athena.conf` include graph and mode-specific database imports, and distinguish definitions from loaded/overridden values. Map IDs must remain stable; client map geometry and art are a separate, rights-controlled dataset.

## Provenance and reuse rules for future conversion

Every candidate record must carry: `product_key`, server/region/build, mode, source record ID, source URL or file plus commit, checked date, raw field/value, source unit, normalized field/value, transformation rule, conflict list, confidence, and rights/provenance status. Keep the source record immutable and write normalized output separately. Never infer a price, drop chance, quest reward or item effect from another edition just because IDs match.

The word “complete” in the plan means all 34 system families have an original equivalent, a named deferral, or a named exclusion. It does not authorize republishing a site's compilation, copying Ragnarok's expressive content, or packaging assets from the installed client. The production path stays free-first and uses original content or assets with an explicit compatible license.

## Next research/engineering slice

1. Resolve the pinned source's active database/NPC load graph and generate per-mode effective indexes with source file, override chain and explicit runtime conversion rules.
2. Extend the existing offline data viewer with source edition and provenance filters; keep it read-only and do not ingest MidgardHub or Fandom bulk content.
3. Convert a deliberately small, rights-reviewed mechanic sample into original game data and compare behavior, not branded catalog text or art.
4. Revisit target server region/build before claiming parity or validating live prices, quest availability and mobile behavior.

