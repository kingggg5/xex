# P1 gameplay contract — Aetherfield

**Status:** working gameplay defaults, revised for plan v5, 2026-09-24  
**Baseline:** [plan v5](browser_ragnarok_babylon_rust_10k_plan_v5.md), the detailed game-system study, and existing P0 source. Local implementation remains within the user's continuing authorization; proposed names/balance are not a claim of accepted final content.  
**Purpose:** turn the broad system-parity request into one original, testable first gameplay slice. This contract does not authorize copying Ragnarok's protected names, story, map geography, interface art, icon set, item catalog, or client assets.

## Player promise

A player can enter one compact fantasy field alone or with up to three friends, understand the next objective from the world and HUD, use a small melee kit on touch or keyboard, complete one short quest, and see the server grant a reward exactly once. Target session length is 8–15 minutes. The first P1 objective is fun and comprehension, not a 10,000-player claim.

The full feature-family coverage matrix remains in [the system landscape study](game-system-landscape-study.md). P1 implements only the core loop; later releases must keep a deliberate equivalent, defer, or exclusion for every matrix row.

## P1 scope

**P1a** is a disposable session playtest of the loop and four-player controls; clearly label its reset policy. **P1b** is completed P1 and requires the durable reward, restart/restore and physical-device evidence below. Session-first work may proceed alongside persistence; it cannot substitute for P1b completion.

| Area | P1 contract | Explicitly later |
|---|---|---|
| World | One original field zone with a clear entry/return route, three discoverable landmarks, a safe regroup point, and bounded playable area | Multiple towns, seamless regions, dungeons, weather simulation |
| Character | One original melee vocation, provisional name **Trailblade**; visible HP/level; no class selection screen yet | Job branches, full six-stat allocation, many equipment slots |
| Combat | Basic attack, dodge, two active skills, one readable enemy tell and a counter opportunity; server owns hit, cooldown, damage, and defeat | Large status/element matrix, boss phases, competitive combat |
| Enemy | One original field creature family, provisional name **Puddlekin**, with idle, approach, telegraph, attack, recovery, and respawn states | Three archetypes and a mini-boss arrive with the P2 vertical slice |
| NPC and quest | One original route guide offers and completes one data-defined talk → field objective → return quest | Long branching chains, schedules, ambient crowds, live dialogue generation |
| Party | Up to four players in one closed test session, joined by a server-issued short-lived invite code; a solo player can complete the same objective; party membership and reward eligibility are explicit | Guilds, public matchmaking, cross-zone parties, open world social graph |
| Reward | One guaranteed quest reward and one guaranteed, bounded personal drop; claims are idempotent | Durable inventory progression, trading, refining, marketplace |
| Interface | Existing scene composition and mobile HUD concept; joystick, camera drag, two offensive skill controls, dodge, Guard Stance, interact, objective/map cues, and collapsible secondary panels | Full character, collection, guild, mail, and live-operations screens |
| Store and boxes | No store, random box, paid currency, or paid progression in P1 | P2 or later: direct NPC shop plus an **earnable-only** supply box after the durable ledger gate; publish odds, use original contents, and exclude power-exclusive rewards |

P1 content should use original names and a distinct route layout. The supplied screenshot is a broad composition and control reference only. Use procedural placeholder geometry or free, provenance-recorded assets; the current P0 needs no paid generation.

## First quest loop

1. The player starts at the edge of the field and meets **Sella**, an original trail guide. She explains the route and offers *Three Windmarks*.
2. The player follows three map pins into the field, activates three original wind markers, and defeats Puddlekin using the telegraph/counter loop.
3. A player who accepted the quest receives personal progress from eligible party combat; the UI identifies which actions count. Solo progress follows the same rules.
4. The player returns to Sella. The server checks the quest version and prerequisites, then commits XP and one original item reward under a unique reward key.
5. The client displays the committed result. A reconnect or repeated turn-in returns the prior result without minting another reward.

Quest progress is per character. Treat solo play as a one-member group. Hunt credit requires an accepted quest, the same group and zone, a member who is connected or still inside the resume grace period, and a distance within 30 m when the server resolves the killing blow; freeze membership at that point. Members who are down but in range still receive credit. No damage quota excludes support players. Each player activates their own three distinct windmarks and returns to Sella individually. Field loot is independent of quest acceptance: an eligible defeat grants one `Dew Bead` using a persisted encounter incarnation plus character as its unique origin. In P1, materials go to an uncapped material pouch, so a full bag can never destroy loot. A quest reward that needs a bag slot is refused before anything changes, and the quest stays ready to claim. Quest rewards are a separate once-only entitlement, never a client-owned counter.

Illustrative original content record:

```yaml
quest_id: Q_AETHER_001
version: 1
repeat_policy: once
progress_owner: character
objectives:
  - { kind: interact, target: npc_sella }
  - { kind: activate, target_tag: windmark, count: 3, zone_id: sunmeadow_verge }
  - { kind: defeat, target_tag: puddlekin, count: 3, zone_id: sunmeadow_verge }
  - { kind: return, target: npc_sella }
reward:
  base_exp: 90
  items: [{ item_id: item_gale_seed, count: 1 }]
  entitlement_id: reward_three_windmarks_once
  idempotency: character_entitlement_cycle
```

This example is a behavior contract, not a final balance or copied quest.

## Authority and economy rules

- The client sends bounded movement, interaction, and ability intents; the server validates current zone, range, cooldown, target, quest state, and sequence/connection epoch.
- The server is the only authority for quest progress, combat outcomes, item creation, currency, store purchases, and box opening.
- Before E06 is complete, gameplay tuning may use ephemeral test rewards only and the server remains local/private. Final P1 acceptance requires the versioned wire protocol, session/origin protections, durable inventory/ledger, and crash/retry tests in the backlog; public access is a separate later decision.
- A quest reward is granted once per character and stable reward entitlement/cycle, independent of ordinary quest content revisions. A retry with the same operation key returns the committed outcome; changed contents conflict. Editing text or balance must not reset eligibility.
- A personal defeat drop is keyed by persisted encounter incarnation/event identity and character; a process restart cannot reuse the origin counter. Snapshot replay and reconnect cannot mint another copy.
- If a later earnable box is added, consume the owned box and grant its result in one durable transaction. Show the exact table and odds before opening. No real-money purchase, paid key, time-limited pressure, stat-exclusive reward, or paid XP/drop boost.
- NPC/quest content is declarative and validated at build/load time. Production content cannot execute arbitrary scripts or make outbound AI calls from the simulation loop.

## Mobile and desktop acceptance

Keep the existing left joystick and right action-cluster direction. Give camera look a separate pointer region and pointer identity so movement, camera, and skill presses do not steal each other's input. Interact is contextual and appears only when a nearby valid target is available. Neutralize movement on pointer cancellation, focus loss, disconnect, and tab backgrounding.

P1 device evidence must cover one real iPhone and one midrange Android. Check landscape at 844×390 and 640×320 CSS pixels; check that portrait shows the rotate-device gate (D-11). Then measure thumb reach, safe areas, multitouch, latency, scrolling, readability and sustained frame time on actual devices. Preserve reduced-motion and non-color-only telegraphs. The [HUD concept](ui/mobile-ui-reference-20261001.md#early-mobile-concept) does not prove device acceptance.

Desktop uses keyboard movement and mouse camera orbit. Both layouts expose the same combat and quest rules, and all panels remain reachable by keyboard with visible focus.

## Exit evidence

P1 is accepted only when all of the following are evidenced:

1. Four human clients can join the same test field and complete the loop; solo play remains possible.
2. At least four of five new testers complete the objective without developer coaching and correctly explain the enemy tell.
3. At least three of five new testers keep playing for three minutes or more when offered a chance to stop, and the median answer to "Would you play the next version?" is 4 or higher on a 1–5 scale. The route time is recorded, not padded ([plan v5 §13](browser_ragnarok_babylon_rust_10k_plan_v5.md)).
4. Quest progress and reward eligibility agree between clients and server; stale inputs, invalid zone interactions, and duplicate turn-ins are rejected or safely replayed.
5. The client runs on WebGPU and forced WebGL2; physical phone tests pass the control and scrolling checks above.
6. Type checks, Rust tests, codec fixtures, content validation, transaction/idempotency boundary tests, and a short network-impairment/reconnect route pass.
7. The evidence names the exact build, content version, devices, workload, and limitations. The result is labeled a local/closed P1 prototype; it is not a public-service, security, economy, or scale qualification.

## Build order and relationship to full parity

Follow plan v5's critical path (§6): the world owner, protocol v4, content bundle and motion authority come before NPC, quest and combat work. Durable identity and persistence can overlap the P1a playtests; the two converge at P1b. P1a may test disposable server-owned progress first. Vendor transactions, boxes, player trade and guild storage require the durable ledger and retry/crash invariants.

After P1, P2 adds the original hub/field vertical slice, more enemy types, 3–5 quests, equipment/inventory, storage, a direct NPC shop, and—only after the ledger gate—an earnable box with visible odds. Later phases cover class breadth, dungeons, chat/moderation, guilds, trade, refinement, events, and operations according to the release ladder in plan v3. The study matrix remains the coverage checklist; exact duplication of Ragnarok content remains outside scope.
