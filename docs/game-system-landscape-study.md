# Game system study: Ragnarok Online, Genshin Impact, and GTA Online

> Source study retained for reference. [Plan v4](history/plans-v3-v4.md#plan-v4) and the [system catalog](system-design-catalog.md) supersede proposed release timing, P1 sequencing and reward-identity examples below. The study is not evidence that its features are implemented.

**Date:** 2026-09-23  
**Purpose:** Translate the systems the user likes into a free-first, original browser MMORPG design.  
**Decision status:** Research and recommendations; nothing in this report authorizes copying game assets, names, maps, story, code, or UI artwork.

> The follow-up [Ragnarok multi-source audit](ragnarok-multi-source-audit.md) cross-checks the 34-system catalog against RateMyServer, iRO Wiki/iW DB, MidgardHub Zero, Ragnarök Wiki and the pinned local server snapshot. It records edition boundaries and source-reuse limits.

## Recommendation

Use **Ragnarok Online's character-building, job identity, monster drops, party play, NPC services, and guild/social loop as the game's spine**. Borrow **Genshin Impact's environmental discovery, short traversal puzzles, readable skill combinations, and four-person party scale**. Borrow **GTA Online's map-to-activity navigation, contact/board-led mission flow, and multi-stage co-op operations**. Keep the world, characters, quest text, map geometry, item names, icons, sound, and visual style original.

For the current free-first plan, the next meaningful game work is not a huge seamless world. It is one hub, one adjoining field, three clearly different enemy patterns, a short quest/reward loop, and a four-player party rule that new players can understand. Add shops, storage, class training, map markers, and a small number of purposeful NPCs to that loop. Leave the shop economy, guild wars, vehicles, user-created missions, gacha, and large regions for later or out of scope.

The scope here is **Ragnarok Online 1 PC/Renewal**, matching the pinned rAthena checkout and the previous downloads; it does not treat Ragnarok Origin or Ragnarok Online 2 as the same system. The local rAthena checkout is pinned at `e985006171d2eb320ee512a653f4c83aea3d81b6` and is GPL-3.0. Its database and NPC scripts are useful for seeing how an emulator structures mechanics; they are not a license to copy the commercial game's art, dialogue, maps, or live-service design. [Local rAthena license](../references/rathena/LICENSE)

### What “100% the same” can mean for this project

I can help reach **feature-family parity** against a defined RO1 PC/Renewal baseline: every major category below gets a deliberate equivalent, is deliberately deferred, or is deliberately excluded. I will not make a 1:1 recreation of RO's map geography, screen composition/skin, named NPCs, dialogue, item descriptions/icons, exact catalog, store boxes, rates, or branded art. Those are expressive content, and exact reproduction can create copyright/trademark risk. The U.S. Copyright Office distinguishes game ideas/methods from their particular expression, but that is not a Thailand-specific legal opinion; any licensed remake needs a lawyer to confirm the license scope. [Copyright Office: Games](https://www.copyright.gov/register/tx-games.html), [Copyright Office: protected works](https://www.copyright.gov/help/faq/faq-protect.html)

The coverage baseline is the pinned rAthena server/schema snapshot plus public official RO system guides. It is **not every feature ever released on every official regional server**, nor every one of the tens of thousands of item records or quest texts. That is the useful way to build a comprehensive remake plan without turning it into a copied content dump.

| RO system family | Feature-equivalent target for Aetherfield | Stage / boundary |
|---|---|---|
| Character creation and appearance | Original face/hair/body choices and a small set of readable silhouettes | P1 prototype; original presets/art |
| Base progression and stat growth | Base level plus bounded STR/AGI/VIT/INT/DEX/LUK-like roles and server-derived stats | P1: one meaningful stat choice; formulas/caps differ |
| Job progression | One original vocation first, then branch choices and higher tiers | P1 one job; P2 second; later tiers after balance tests |
| Skill trees | Prerequisite graph, ranks, passive/active choices, respec policy | P1 two active skills and one passive choice; no copied names/icons/tree artwork |
| Combat and damage | Basic attacks, accuracy/crit/evasion role, statuses, telegraphs, counters, cooldowns | P1 simplified and readable; original formulas and VFX |
| Monster taxonomy | Distinct families, size/range/defense/element-like tags and map habitats | P1 one enemy; P2 a few archetypes; tags remain data-driven |
| Drops and boss rewards | Per-monster loot tables, quest drops, rare-boss reward and contribution credit | P1 bounded drops; later boss/party attribution; no copied drop rates/catalog |
| Quest catalog | Story, job/tutorial, hunt, collect, delivery, timed, instance, repeatable/event patterns | P1 three short quest types; later branch chains; original stories/rewards |
| NPC interaction | Talk, select, prerequisites, service action, availability/quest markers | P1 wayfinder/captain/vendor; later schedules and state reactions |
| Hub services | Save/return, storage, transit, repair, trainer, shop, event board equivalents | P1 two services; add when needed; original NPC identity and costs |
| World map structure | Hub, fields, dungeons, event areas, instanced content, connection/portal rules | P1 field, P2 hub + field + first instance; original route geometry |
| Map behavior flags | Safe/social, combat/PvP, no-teleport, event-only, visibility and interaction rules | P1 safe hub/field rules; enable modes only after security review |
| Travel and waypoint UX | Discoverable exits, return points, party regroup, a route pin and filtered POI markers | P1: map/exit/quest pins; no copyrighted Kafra wording or icon art |
| Items and inventory | Equipment/weapon/armor/accessory/consumable/material/cosmetic categories, stack and bind rules | P1 small earned catalog; original names, descriptions, icons and stats |
| Cards, sockets and refinement | Slotted modifiers, upgrade risk/reward, collection/set synergies | P2 deterministic rune-like modifiers first; no random paid upgrades |
| Weight, carts and storage | Carry capacity trade-off, personal storage, shared guild vault later | Later, after usability and durable inventory work |
| Shops and vending | NPC buy/sell; possibly player stalls or direct trade | NPC store P1/P2; player trade only after anti-duplication, fraud, moderation, and audit tests |
| Shop boxes / premium boxes | A store can expose earned supplies and cosmetic/reward boxes with visible odds | **Free-only adaptation:** earnable currency only, nonessential cosmetics/supplies, disclose odds; do not copy Kafra boxes, exact contents, prices, or real-money boosts |
| Pets, companions, hirelings | Optional bond/follow/support roles with bounded combat impact | P3+ only if it adds play choices without pay-to-win or crowding mobile combat |
| Party | Invite, membership, level/zone eligibility, XP and loot-sharing policy, reconnect | P1/P2 four-player target; reward rules explicit and server-owned |
| Guild | Membership, roles, message board, shared progression, later guild space | P3; permission/audit rules before shared funds or item vault |
| Castle siege / competitive modes | Scheduled group objectives and controlled contested zones | Much later; defer siege/PvP until fairness, anti-cheat, moderation, and load gates pass |
| Social features | Chat, friends, emotes, block/report, mail or offline messages | Basic moderation and block/report before scaling social traffic |
| Character customization | Hair/skin/costume slots and earned cosmetic rewards | Original cosmetics only; avoid paid random pulls |
| Events and turn-ins | Rotating field challenges, limited-time encounters, hunts, scoreboards | Optional events with long claim windows; no streak/FOMO penalty |
| User interface | Status, party, map, quests, chat/loot feed, inventory/skills, hotbar | Keep the information jobs from the reference; redesign layout, icons, wording, touch behavior, and navigation |
| Live operations and support | Configurable event schedules, reports, safe support tools and audit trail | Production phase, never run arbitrary copied NPC scripts as production code |

This matrix is intentionally comprehensive at the **system** level. It does not mean every category ships in P1. “100% feature-family coverage” means each row gets a scoped decision and eventual original equivalent; the release gates in plan v3 still determine order.

Official iRO/WarpPortal pages are useful descriptions of the system, but they are regional and some guides are old. Treat them as evidence of recurring RO design patterns, not a specification for the current GNJOY Thailand service. For Genshin and GTA, this study uses official feature/support pages and draws design inferences from those features; it does not assume the two games share an architecture or business model with our browser prototype.

## What Ragnarok contributes

| System | What the references show | What is valuable for our game |
|---|---|---|
| Character identity | A Novice progresses into a first job and then more advanced jobs; status points shape a build. The six familiar attributes cover different jobs such as damage, attack tempo, defense/HP, magic, accuracy/cast time, and critical/evasion. | Players can explain their build in a sentence. Preserve Base/Job-style progression and a few real trade-offs, but cap formulas and make the outcome visible. Start with one well-tested vocation before adding several. [RO job changes](https://renewal.playragnarok.com/gameguide/howtoplay_basicsystem04.aspx), [RO status guide](https://renewal.playragnarok.com/gameguide/howtoplay_basicsystem03.aspx) |
| Combat and builds | Skill trees, weapon/equipment slots, element/race/size distinctions, cards, upgrades, and pets give monsters and items distinct roles. The official feature page calls out cards, upgrading, attributes, pets, guilds, PvP, and War of Emperium. | A monster can be memorable because of its attack tell, habitat, drop, and counterplay—not only its health. Make equipment modifiers deterministic enough to balance. A card-like socket system is a later content multiplier, not a launch requirement. [RO features](https://renewal.playragnarok.com/gameguide/features.aspx) |
| Quest and NPC structure | The pinned `quest_db.yml` models quest IDs, titles, time limits, kill targets, counts, target filters, map location/name, and quest-item drops. rAthena documentation also exposes quest-log state commands and conditional quest markers for NPCs/minimaps. The checkout has 88 quest script files; a first-class tutorial shows dialogue branching by job and tutorial progress. | Keep dialogue, quest offers, objective progress, and reward grants separate. Represent common objectives as data; reserve scripts for special events. Show a quest marker only when the NPC can advance a quest for that player. [Quest DB](../references/rathena/db/re/quest_db.yml), [quest commands](../references/rathena/doc/script_commands.txt), [first-class NPC example](../references/rathena/npc/quests/first_class/tu_sword.txt) |
| Map and travel rules | RO is organized as named maps connected by warps/services. `map_index.txt` provides stable map IDs; map flags define restrictions such as safe/PvP/GvG behavior, teleport and warp rules, night mode, and other local policies. Kafra functions combine services such as save point, storage, teleport, cart rental, and guild storage. | Make each zone's rules legible: where combat is allowed, where a party can regroup, which exits/waypoints connect it, and what service an NPC provides. Keep the prototype as compact zones with explicit transitions rather than promising a single giant world. [Map index](../references/rathena/db/map_index.txt), [map flags](../references/rathena/doc/mapflags.txt), [Kafra service logic](../references/rathena/npc/kafras/functions_kafras.txt) |
| Loot, equipment, and economy | Item definitions include type, equipment locations, required level/job, stats, slots, refine/grade behavior, trade/storage flags, and stack rules. Official guides describe item and Zeny trading; party setup offers different experience and item-sharing policies. RO's official feature page presents cards and upgrading as build systems. | Make each reward's source and use understandable. For co-op, decide before play whether drops are individual, shared, or assigned; do not let a client decide item creation or currency. Start with a small, non-tradable test reward, then add durable inventory and transactions before open trade. [Item DB](../references/rathena/db/re/item_db_equip.yml), [RO party play](https://renewal.playragnarok.com/gameguide/howtoplay_gameplay05.aspx), [RO trading guide](https://renewal.playragnarok.com/gameguide/howtoplay_gameplay04.aspx) |
| Social systems | Parties, chat, direct trades, guilds, castle ownership and PvP give a reason to return to town and organize with other players. RO's experience guide documents both contribution and party-sharing policies, including same-map/level conditions in that guide's rules. | Treat the hub as a social space, not just a menu. Ship parties and moderated chat before direct trade; add guild progression only after reward and item ownership are durable. The exact legacy XP formula is a reference, not a balance recommendation. [RO party play](https://renewal.playragnarok.com/gameguide/howtoplay_gameplay05.aspx), [RO features](https://renewal.playragnarok.com/gameguide/features.aspx) |
| HUD and interface | The guide exposes status, job change, basic interface skins, camera controls, trading, leveling, and party play as separate teachable topics. The user's reference screen combines player/party status, minimap, active quests, chat/loot, skill bar, and mobile controls. | Keep those information jobs, but let them collapse on phones. Prioritize HP, current objective, nearby threat, and the two most useful actions; put inventory, character, skill, and settings screens in accessible DOM menus. Do not reproduce the RO skin, icon art, type, or exact layout assets. [RO basic interface](https://renewal.playragnarok.com/gameguide/howtoplay_interface01.aspx), [RO beginner guide](https://renewal.playragnarok.com/gameguide/helpfulstartguide.aspx) |
| Visual assets | rAthena's map cache is server-side map/collision data built from GRF or data-directory inputs; it is not a library of browser-ready scenery. The actual visual client assets have separate provenance and rights. | Treat server schemas, map collision, Blender source files, and runtime GLB art as separate deliverables. Use the existing procedural art for P0; for later art, keep an editable master, a validated export, a collision asset, and rights/source metadata. [Map cache documentation](../references/rathena/doc/map_cache.txt) |

The current official Kafra Shop is a paid-points storefront, and the official VIP guide describes higher XP/drop rates and convenience benefits. Those are useful warnings for a project that must stay free-first: **do not introduce paid progression boosts, gacha boxes, paid convenience warps, or loot that competes with earned items**. We can use a fictional, non-paid quartermaster/storage NPC as a service pattern without copying the Kafra brand or charging real money. [Kafra Shop guide](https://renewal.playragnarok.com/kafrashop/kafrashopguide.aspx), [VIP service guide](https://renewal.playragnarok.com/gameguide/premiumservice.aspx)

### A distinction about maps and art

The local server source stores map names, indices, flags, NPC placement/scripts, and cached cell data. Its map-cache documentation says the builder consumes maps from GRF files or a data directory. Therefore a server checkout is not a free supply of the original game's buildings, terrain, textures, sprites, or audio. We do not copy or package anything from the official GNJOY client. The screenshot informs broad composition—town beyond field, clear combat target, compact HUD—only.

## What Genshin Impact contributes

The official game feature summary emphasizes open-world exploration, a party of four with distinct abilities, elemental interactions, environmental puzzles, and co-op play. [Genshin game features](https://www.xbox.com/en-US/games/genshin-impact)

The most transferable patterns are:

1. **Exploration pays off locally.** A side path should reveal one thing: a clover patch, a short encounter, a vista, a puzzle, or a useful NPC. The map should invite a detour without requiring a giant continent.
2. **Skill combinations are readable.** Start with at most two or three original combat tags and one or two interactions. Telegraph the effect in the world and in the UI. Do not build all seven Genshin elements or an exhaustive reaction graph for P1.
3. **Party composition creates support moments.** Plan for four human players eventually, but make one class fun alone first. Skills should enable positioning, defense, and teammate follow-ups instead of assigning one mandatory role to each slot.
4. **World interactions should share the same verbs as combat.** A lever, wind current, damaged bridge, or elemental object can use the same interact/skill targeting affordances as the field. This helps the world feel coherent.

One co-op warning is useful: HoYoverse support documents quest stages that temporarily prevent joining co-op. For our design, keep personal story progress and shared field instances separate. A player's story cutscene should not trap their entire party outside the session; if a quest must isolate someone, explain why and offer a clear resume/rejoin path. [Co-op access support](https://support.hoyoverse.com/hc/en-us/articles/50333905596953-Unable-to-Access-Co-op-Mode)

What not to copy: Genshin's named regions, character designs, exact puzzle motifs, UI, gacha or daily reward pressure. The source game is a polished, very large content product; our first mobile browser slice should be a small route with a few authored discoveries and one repeatable loop.

## What GTA Online contributes

GTA Online's official Free Mode guide describes a free-roam map with mission providers, business/social locations, properties, destination markers, and session-wide dynamic events. Its official Heists description details multi-stage four-player missions, preparation missions, roles, invitations, coordination, and replay. The current Rockstar site continues to organize content around businesses, contracts, activities, and community-created missions. [Free Mode guide (localized Rockstar page)](https://www.rockstargames.com/jp/gta-online/guides/7772?section=3785), [Heists overview](https://support.rockstargames.com/articles/6hBJdQCmQ3YR7nqHIq9AGS/gtav-title-update-1-21-ps3-xbox-360-1-07-ps4-xbox-one), [GTA Online businesses and activities](https://www.rockstargames.com/gta-online?trk=public_profile_project-button), [Mission Creator](https://www.rockstargames.com/newswire/article/39a3412379o79o/play-thrilling-new-gta-online-experiences-built-by-the?pubDate=20260430)

Patterns that fit our game:

- **Make the map an activity launcher.** Let a player pin a quest giver, field exit, boss instance, or social event and show one readable route. Provide marker filters and a short “why this matters” label instead of covering the map with every system at once.
- **Give co-op missions a beginning, middle, and finale.** A future dungeon can use a briefing at the hub, one or two role-sensitive preparation choices, a boss encounter, and a reward distribution screen. Each preparation step must be fun and pay contributors; don't reproduce a GTA robbery or its crime theme.
- **Use shared spaces to connect systems.** A guild hall or expedition lodge can later host party assembly, crafting, a job board, and event schedules. Ownership/property systems come only after inventory, access control, and persistence are reliable.
- **Consider creator tools much later.** A curated quest creator can extend content, but it requires an approved vocabulary, resource limits, content validation, moderation, versioning, and a reporting/removal path. It is not a P0/P1 feature.

What not to copy: criminal activity, weapons, cars, wanted levels, real-estate empire, mission names, city layout, logos, or in-game phone imagery. Vehicle physics, traffic, law enforcement, and a full city simulation would also consume time better spent on readable combat, quests, and mobile performance.

## Recommended system contract for Aetherfield

The table converts those patterns into the current plan's release ladder. These are recommendations, not approved content assets.

| Priority | System | Recommended first implementation | Acceptance signal |
|---|---|---|---|
| P1 | Character progression | One original melee vocation; separate base progression and job-skill choices; preserve six stat *roles* only if each has a bounded, explainable effect. | New players can describe one meaningful build choice, and the server computes the result. |
| P1 | Combat | Basic combo, dodge, two active skills, one telegraphed slime pattern, one counter window. Add at most one readable elemental/status interaction after the baseline works. | 4/5 new testers understand the tell and can use the intended counter without coaching, per the v3 playtest gate. |
| P1 | NPC + quest | Field guide offers a three-step quest: talk → defeat/collect → return. One vendor or service NPC; one optional secret route. Objective definitions live in data and server progress is authoritative. | Quest state survives reconnect; an acknowledged reward cannot duplicate on retry. |
| P1 | Map | One small original hub edge, one field, a short route, one safe regroup point, three named POIs, one exit/waypoint. Use a mini-map with only current/nearby quest, exit, party, and discovered POI layers. | Tester finds the quest giver, field exit, and return point without a developer pointing them out. |
| P1 | Rewards/economy | Monster drop plus quest reward; visible source and use; no paid or random purchase. Begin with account-bound prototype loot; don't expose free trade until ledger/inventory invariants exist. | Server grants once; party reward rules are visible before the fight. |
| P1 | HUD and touch | Keep player HP/MP/party, current objective, minimap, chat/loot feed, skill cluster, and left joystick. Collapse party/chat/secondary quest rows at phone size; menus remain keyboard/screen-reader accessible. | Two-thumb movement + camera + skill are possible on real phones without page scrolling; that device test is still outstanding. |
| P2 | Hub life | Add a small number of event-driven schedules: one guard patrol, one vendor availability change, and one field event announcer. Use timers/state changes, not continuously simulated crowds. | Players notice a world change and understand when/where it happens. |
| P2 | Party instance | Four-player co-op, shared objective state, disconnect/rejoin, clear loot policy; avoid blocking co-op for unrelated story progress. | A party finishes the objective and receives no duplicate/lost rewards when one member reconnects. |
| P3+ | Guild / operations | Guild roles, guild lodge, and a multi-step co-op operation with explicit prep/finale/reward rules. Siege and open trading are separate gates. | Audit, moderation, economy, and server capacity gates pass first. |
| Later / optional | User-made content | Bounded mission templates and an approval/moderation pipeline, only after stable content schemas and live operations. | Quarantine, validation, author attribution, rollback, reports, and safe removal work before public publishing. |

### NPC roster for the first slice

Keep the roles distinct so the player can identify the next action from the NPC's place and label:

1. **Wayfinder:** explains the route, points to one active field objective, and handles the return/party regroup flow.
2. **Field captain:** owns the first short quest chain and one follow-up after the player returns.
3. **Quartermaster:** sells inexpensive earned supplies and later supports storage; never hides mandatory progression behind paid convenience.
4. **Ambient guard/merchant:** optional P2 schedule example; changes a small interaction or line at a known time, with a visible “available now/later” cue.

For each authored NPC record an ID, original name, zone/position, interaction radius, schedule/state, service type, quest prerequisites, dialogue ID, localization key, and fallback behavior. Do not execute arbitrary unreviewed scripts from production content; constrain content actions to a small validated command set.

### Quest and reward data

Use a versioned objective graph or ordered list with explicit dependencies, rather than a one-off script per quest:

```yaml
quest_id: Q_FIELD_001
version: 1
repeat_policy: once
prerequisites: []
stages:
  - objective: interact
    target: npc_wayfinder
  - objective: defeat
    target_tag: meadow_slime
    count: 3
    zone_id: western_meadow
  - objective: return
    target: npc_field_captain
rewards:
  base_exp: 90
  items: [{ item_id: item_clover_gel, count: 1 }]
```

The data is illustrative, not production balance. Define whether each objective counts per player, party, or instance; how late joiners and reconnects are handled; whether kills count only in a map or level band; what happens when objectives are repeated; and how reward IDs are made idempotent. The local rAthena quest DB is useful because it models target count, map, mob filters, time limits, and quest-item drops separately, while NPC script commands can set/complete quest states and show conditional quest/minimap icons. Use this as a schema lesson only, not as imported quest text or balance. [rAthena quest DB schema](../references/rathena/doc/yaml/db/quest_db.yml), [quest script commands](../references/rathena/doc/script_commands.txt)

### Map and asset records

Each original zone should carry: stable `zone_id`, display name, bounds, spawn points, safe/combat/travel flags, entrances/exits, POI marker categories, enemy tables, collision/navmesh version, time/weather profile, and a content-bundle hash. The client sees only the assets and zones needed for the next route; the server owns spawn/combat rules and validates transitions. rAthena's `map_index` and map flags illustrate separating a stable map identity from per-map behavior, and its map-cache guide documents that visuals come from external GRF/data inputs while the server cache holds map data. Do not treat that cache or the official GNJOY client as a free art pack. [rAthena map index](../references/rathena/db/map_index.txt), [map flags](../references/rathena/doc/mapflags.txt), [map cache guide](../references/rathena/doc/map_cache.txt)

For later production assets, require an asset record with a unique ID, gameplay purpose, cleared source/reference, editable master, runtime GLB, original license/rights source, dimensions/pivot, rig/animation expectations, collision shape, LOD/material/texture budget, and review status. Blender can normalize authoring/export. The current P0 scene stays procedural; no Tripo or other paid generation is required. Generated/reference artwork is a candidate, not proof of rights or mobile readiness.

## Build order and deliberate exclusions

The just-built P0 is a technical prototype: local Rust room, sequence/epoch checks, simple movement/damage, responsive HUD, and procedural placeholder scene. It does **not** satisfy all of E01–E05: JSON is a temporary protocol, authentication and durable reward storage are absent, there is no collision/navmesh qualification, no bot driver, and no real phone test. Keep those gaps explicit in [the backlog](execution-backlog.md) and [P0 smoke evidence](../planning/evidence/p0-browser-smoke.json).

Recommended next game-design gates are: (1) approve the P1 loop and exact role/loot rules; (2) write original enemy/NPC/quest briefs; (3) define map exits and safe/field rules; (4) finalize touch/UI states; (5) run binary-protocol and persistent-reward work before adding trade or a public economy. A large open world, 10+ jobs, elemental reaction matrix, market, guild siege, cars, a full NPC city simulation, UGC creator, live LLM dialogue, gacha, paid XP/drop boosts, and FOMO daily streaks remain deferred or rejected.

## Evidence and source limits

Local evidence is pinned rAthena source/schema plus the existing item export; research is read-only and no rAthena records were imported into the prototype. The official iRO guide is an older/region-specific Renewal description and may not match current GNJOY Thailand behavior. Genshin's product feature summary is a platform listing rather than a complete developer design document. GTA Online feature pages describe a different theme and live-service economy. Recommendations above are design inferences from those documented patterns, not claims that the games use the same architecture.

No client assets, quest text, maps, icons, models, audio, or branded UI from RO/Genshin/GTA were copied. Any future use of third-party content requires a per-asset rights review, and any real-money feature needs a separate user decision and economy/safety review.
