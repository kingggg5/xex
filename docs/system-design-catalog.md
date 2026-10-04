# Aetherfield — system design catalog

**Revision:** 1 · 2026-09-23 · **Owner:** primary integrator  
Baseline: [v4 execution plan](history/plans-v3-v4.md#plan-v4), [RO/Genshin/GTA study](game-system-landscape-study.md). Entries specify original implementations; balance numbers and release ceilings are proposals. This catalog defines feature coverage, not completion.

Source edition, effective value and reuse provenance are cross-referenced in the [multi-source Ragnarok audit](ragnarok-multi-source-audit.md). Renewal, Pre-Renewal, iRO and Zero values stay separate; this catalog does not authorize copying a community database or client assets.

## 1. Coverage register

Status: **partial** = some source exists but acceptance is incomplete; **planned** = no accepted runtime implementation; **deferred** = retained in long-term scope after prerequisites. Closed means every named acceptance case has evidence, not simply that a panel exists.

| ID | System | Minimum feature coverage / edge case | Target | Status |
|---|---|---|---|---|
| SYS-01 | Account/session/character | Own-character selection, admission, resume, logout, one live owner; reject guessed identity | P0/P1b | Partial temporary session |
| SYS-02 | Character appearance | Original presets, visible gear, stable appearance IDs, fallback missing visual | P2 | Planned |
| SYS-03 | Base/Job progression | Separate curves, capped levels, unlocked choices, overflow/respec policy | P1b/P2 | Partial UI only |
| SYS-04 | Attributes/derived stats | Six build roles, HP/SP/attack/defense, modifier order/caps, preview before spend | P2 | Planned |
| SYS-05 | Vocation/job paths | One vocation, branch prerequisites, role identity; persist choice | P1→P4 | Planned |
| SYS-06 | Skill graph | Active/passive ranks, prerequisites, cost/cooldown, reset and locked UI | P1→P3 | Partial actions |
| SYS-07 | Action combat | Intent validation, hit shape/line of sight, combo, dodge, interrupt, death/revive | P1 | Partial damage/movement |
| SYS-08 | Enemy AI/status | Aggro/leash, telegraph, recovery, respawn; bounded status stacking/resists | P1→P2 | Partial static enemies |
| SYS-09 | Elite/boss/MVP equivalent | Contribution, phase change, arena reset, personal reward; reconnect mid-fight | P2/P3 | Planned |
| SYS-10 | Loot and ownership | Deterministic reward origin, personal/party eligibility, claim retry/full bag | P1b | Partial UI only |
| SYS-11 | Quest journal | Prerequisites, hunt/collect/talk/activate/return, timed/repeatable, tracking/abandon | P1→P3 | Partial counters only |
| SYS-12 | NPC/dialogue | Offer/choice/service, quest markers, localization, range/state checks | P1/P2 | Planned |
| SYS-13 | NPC town services | Save/return, storage, transport, trainer, repair/refine, vendor, event board | P2 onward | Planned |
| SYS-14 | Zones/world map | Stable zones, exits, POIs, discovered layers, boundaries, content versions | P1→P4 | Partial one field |
| SYS-15 | Map flags/travel | Safe/combat/PvP/instance/no-return rules, portal checks, owner handoff | P2/P4 | Planned |
| SYS-16 | Asset/animation pipeline | Source/rights, rig/clip, LOD, collision, export/import, packaging | P0→P2 | Partial procedural fixture |
| SYS-17 | Inventory/equipment | Stack/instance, equip/unequip, capacity, bind, use, compare, trash confirmation | P1b/P2 | Partial sample bag |
| SYS-18 | Personal/guild storage | Deposit/withdraw, access, revision conflict; vault roles/audit | P2/P4 | Planned |
| SYS-19 | NPC shop | Buy/sell, quote revision, quantity/stock/capacity, receipt, retry | P2 | Planned |
| SYS-20 | Reward box/store | Earned boxes, contents/odds preview, atomic consume/grant, duplicate result recovery | P2 after ledger | Planned |
| SYS-21 | Cards/sockets/set effects | Original rune modifiers, compatible slots, extraction/bind/stack limits | P3 | Planned |
| SYS-22 | Refine/enchant/crafting | Recipe/cost/chance, failure consequence, preview, one transaction | P4 | Deferred after economy |
| SYS-23 | Trade/vending/market/mail | Escrow/atomic exchange, price/expiry, offline delivery, tax, fraud reports | P4/P5 | Deferred after ledger/moderation |
| SYS-24 | Party | Invite/accept/leave/kick, leader, range/XP/loot rules, disconnect/rejoin | P1/P3 | Partial shared room only |
| SYS-25 | Guild | Membership/ranks, permissions, announcements, shared progression/vault | P4 | Planned |
| SYS-26 | PvP/arena/siege | Opt-in zone, schedule/team rules, objective/score, fairness, capped density | P5 expansion | Deferred; own qualification |
| SYS-27 | Pets/companions/mounts | Follow/path, bond/feed, capture/acquire, storage and bounded bonuses | P5 expansion | Deferred |
| SYS-28 | Chat/friends/social | Party/local channels, mute/block/report, presence, rate and retention limits | P3 | Partial local DOM chat |
| SYS-29 | Events/daily/achievements | Server schedule, eligibility/claim windows, unique event entitlement, reconnect | P3 onward | Planned |
| SYS-30 | Exploration/living world | POI discovery, puzzle/shortcut, small NPC schedules, event reaction | P1/P2 | Planned |
| SYS-31 | Co-op operations/instances | Briefing, preparation, role-sensitive encounter, finale and reward | P3 | Planned |
| SYS-32 | HUD/menus/accessibility | Health/resource, party/map/quest/chat, bag/stats/skills/settings, touch/focus/errors | P1→P3 | Partial placeholder HUD |
| SYS-33 | Content/localization tools | Validated data editor/import, ID/reference diff, Thai/English fallback, safe preview | P1→P3 | Planned; item viewer is research only |
| SYS-34 | Operations/support | Roles, logged grants, backup/restore, canary/rollback, reports, moderation | P3→P5 | Planned |

P2 intentionally has a small catalog; it does not delete later RO-like systems. For research, enumerate records from the pinned source and record counts separately from production coverage. The existing 29,356-record item export is a reference dataset, not a shipped inventory catalog.

## 2. Content structure and import boundary

```text
content/source/
  manifest.json               schema version, content revision, minimum protocol
  zones/*.json                boundaries, travel graph, flags and POIs
  npcs/*.json                 role, placement, interaction and dialogue references
  dialogue/{th,en}/*.json     original text and localization keys
  quests/*.json               objectives, prerequisites and entitlement definitions
  items/*.json                definitions, slots, stacks and use effects
  shops/*.json                offers, currencies, price/stock revisions
  boxes/*.json                deterministic or weighted contents and policy
  abilities/*.json            timelines, costs, shapes and VFX references
  enemies/*.json              behavior, habitat, drops and respawn
  progression/*.json          level curves, stat caps and modifier ordering
content/build/<hash>/         generated client presentation + server rules
```

This tree is proposed, not present today. Research exports stay under `references/` and `exports/`; convert only reviewed definitions into original production data. A research converter emits source ID/commit, field mapping, validation warnings, unresolved references and a diff report. It must not silently treat GRF/client art or arbitrary NPC script execution as a production asset/data pipeline.

Build validation: unique IDs; valid references; finite bounded numbers; no cyclic mandatory quest/skill prerequisites; reachable zone exits; valid slot masks/stacks; reward limits; nonempty eligible box outcomes; matching hashes/schema; required localization keys. Reject unknown executable commands. A bundle failing validation never reaches the runtime manifest.

## 3. NPC and dialogue contract — SYS-12/13

Required NPC fields: stable ID, display-name key, role, zone/position/facing, collider/interaction radius, schedule, quest offers, service IDs, dialogue graph ID, asset ID, content revision. Start with Sella (guide/quest); later add quartermaster (shop/storage), trainer and transit keeper. These are separate services even if one NPC exposes several.

Runtime flow: `Unavailable → Nearby → Interacting → ChoicePending → Result → Closed`. Server validates proximity, zone, life state and prerequisites at each action, including after the menu has opened. The client cannot turn any NPC into a vendor by changing a service ID. Dialogue graph uses approved verbs: show text, offer/advance quest, open service, set bounded flag, close; no eval, shell or network call.

States to render: no offer, available offer, active objective, ready turn-in, unavailable schedule, service pending, expired choice, inventory full, error/retry. Marker priority is ready turn-in → available quest → service → ambient; include shape/text, not just color. Leaving range invalidates the choice token. Repeated response reuses the original operation.

Acceptance: cannot claim another NPC's reward, interact through forbidden wall, skip a prerequisite or reuse stale dialogue choice; 4/5 new testers identify the guide and next action without help. Localization may change text without changing logic or reward identity.

## 4. Quest and reward contract — SYS-10/11

Separate four identities: `quest_definition_id`, `content_revision`, `quest_run_id`, and `reward_entitlement_id`. A once-only quest retains one entitlement across text/balance revisions. Repeatable quests require explicit cycle/rotation identity; abandoned/reaccepted quests do not mint a new entitlement by default.

State machine: `NotAvailable → Available → Active → ReadyToClaim → Claimed`; optional `Failed/Abandoned` has a defined restart policy. P1 supports talk, activate, defeat and return. P2 adds collect/delivery/tutorial chains; later timed/instance/repeatable events use the same validated primitives.

Objective record: ID, kind, target ID/tag, count cap, zone, prerequisites, per-character/party attribution, distinct-target policy and expiry. Three windmarks require three distinct object IDs. Count eligible kills only after accept. Collection counts inventory ownership or consumption according to the objective, never a chat line; specify whether selling an item reduces progress before claim.

Rewards: source/eligible recipients fixed at resolution; durable operation includes entitlement, payload digest, owner epoch, inventory revision, granted items/currency/XP and result. Mission UI displays preview, pending, committed or recoverable failure. Never print “obtained” before the grant commits in P1b.

Cases: kill before accept, repeated marker, party join during encounter, support participant, dead/out-of-range participant, disconnect exactly at kill, abandoned quest, full bag, claim twice concurrently, response lost after commit, revision changed, restart and restore. Each has a specified outcome and acceptance evidence.

## 5. Maps, travel and discovery — SYS-14/15/30

Zone record: stable ID/name key, unit/axis convention, authored bounds, safe/combat volumes, spawn slots, portals/destinations, POIs, enemy habitats, NPC anchors, encounter volumes, navmesh/collision/asset hashes and time/weather presentation. Runtime zone ownership is separate from the visual scene identifier.

P1 layout: entry/refuge → Sella → three windmarks along a legible route → hunt clearing → optional lookout → return. Use relative adjacency first; choose final distances by real walking time and camera sightlines. P2 adds the civic hub and mini-boss loop; original landmark geometry is authored after blockout testing.

Spawn selection uses bounded unoccupied valid positions, never lifetime player ID multiplied into an unbounded row. Portals validate destination availability and quest/party/level flags; reserve target capacity before migration. Failure returns the player to the last valid source state with a message, never creates two owners.

Map UX: player position/heading, nearby exit, tracked objective, discovered POIs, real party members. Filters default to the current journey; show route destination and purpose. Coordinates for minimap markers must come from world data, not decorative dots moving with the camera. Implement safe zone and no-return rules before adding PvP flags.

Acceptance: walk boundaries/door/slope with identical client/server geometry; continuous pressure cannot penetrate; rejected portal preserves inventory/location/ownership; disconnect during loading recovers; player finds exit/return unaided.

## 6. Items, equipment and storage — SYS-17/18/21/22

Item definition: ID/name/description keys, type, icon/mesh, stack cap, bind/trade/storage flags, weight, use/equip requirements, slot tags, base modifiers, socket capacity, upgrade policy, drop/sell restrictions and content revision. Item instance: instance ID, owner, location/slot, definition/revision, count/durability/socket rolls, acquisition origin and optimistic revision.

P1b catalog: one earned material, one consumable, one quest reward. P2 ceiling: 12–20 authored items spanning weapon/armor/accessory/material/consumable/quest/cosmetic. Add modifiers only when a player can see their benefit. Keep Base/Job EXP separate; show change before spending points.

Inventory flow: select → inspect/compare → use/equip/move → pending → authoritative revision. Full bag never silently deletes loot. Storage transfer is an atomic location change, not copy-then-delete. Personal and guild storage have different access scopes. Split/merge stacks cannot exceed caps or combine incompatible instance metadata.

Rune trial: deterministic original modifier, slot compatibility, bounded stacking, reversible test reset. Refinement later states cost, success/failure outcome and maximum rank explicitly; consume materials and produce result atomically. Disabled/unavailable actions show the reason.

Acceptance: concurrent equip/use/withdraw, stale revision, split/merge at caps, negative/overflow amounts, forged ownership, full destination, trade-bound items, disconnect after consume and restart recovery all preserve ownership and quantities.

## 7. NPC shop and player economy — SYS-19/23

Offer definition: shop/offer ID, item definition, integer unit price, currency, buy/sell policy, stock/quota, unlock condition, quote revision and expiration. Never trust a client-supplied price, total or item definition beyond selecting an offer.

Buy flow: list → inspect → quantity → server quote → confirm intent → validate funds/capacity/stock/session → single transaction → receipt + inventory/balance revisions. Sell validates instance ownership/bind status and quantity; quest-critical items can be unsellable. Price changes invalidate old quotes with a clear refresh; duplicate confirm returns its original result.

P2 uses earned currency and direct NPC offers. Player vending/direct trade/market wait for escrow and moderation: dual-party confirm over immutable offer revision, cancel/timeout release, atomic ownership swap, listing expiry, fee/tax ledger and a report/support route. An offline mailbox delivery shares the same durable item origin and cannot duplicate via claim/delete races.

Acceptance: two buyers race last stock, stale quote, overflow total, insufficient funds, full bag, repeated buy/sell, disconnect after commit, failed listing cancellation and two-tab trade. Verify the ledger, not only toast text.

## 8. Boxes and store UX — SYS-20

P2 first supports a deterministic earned supply pack so consumption and delivery can be verified. If weighted boxes add a useful collection choice, enable one original weighted table only after the deterministic path passes. No paid API or paid purchase is needed for either feature. Future monetization is not decided by this plan.

Box definition: ID/version, consumed instance type, complete outcomes, positive integer weights, quantity, eligibility constraints, duplicate policy, binding rules and capacity requirement. Display exact normalized odds and contents before open; show guaranteed components separately. Freeze eligible outcome set when the durable operation begins. If eligibility changes the odds, display that player's effective table.

One transaction consumes the box, records the chosen outcome and credits it. The server selects randomness and persists the result; reloading a screen never rerolls. If no valid outcome exists, fail without consuming. Deterministic packs display “guaranteed” rather than odds. Open animation runs after the committed result and can be skipped; it never decides the result.

No pity counter in the first release. If later introduced, model it as durable per-box-series state; test reset/increment atomically with the roll. Avoid layered rare-roll tables that cannot be explained in the UI.

Acceptance: click twice, concurrent opens of one instance, replay a request with changed box ID, bag full, revision mismatch, disconnect during reveal, restart between commit and notification. In all successful retries the same consumed source and outcome are returned.

## 9. UI/UX inventory — SYS-32

| Screen/component | Must show | Critical states |
|---|---|---|
| Session/character entry | Actual character/session, invite target, connection status | Joining, rejected, expired, reconnecting |
| Combat HUD | HP/SP, target, server cooldown/resource, threat and interaction | Hit, damage, unavailable action, death/revive |
| Party panel | Real roster, leader, zone/distance, connection state | Invite pending, removed, disconnected |
| Minimap/world map | Discovered destinations and tracked route | Undiscovered, unavailable portal, loading |
| Quest tracker/journal | Current stage, bounded progress, reward, return NPC | Available, active, ready, committed, abandoned |
| NPC dialogue | Speaker, original localized choices, service prerequisites | Out of range, expired choice, locked branch |
| Bag/equipment | Owned quantities/slots, binding, compare, action cost | Empty, full, pending, stale revision |
| Shop/storage/box | Quote/balance/capacity, source/contents/odds, receipt | Insufficient funds, full, stock changed, retry |
| Character/skills | Base/Job levels, derived stats, prerequisite/rank and spend preview | Locked, maxed, respec |
| Chat/social | Actual channel/participants, mute/report | Rate-limited, blocked, unavailable |
| Settings/accessibility | Quality, resolution, audio, touch scale/remap, language, reduced effects | Applied/pending/reverted |

All online screens project server state; fixture/demo data is explicitly labeled offline. DOM panels have keyboard focus, escape/back behavior and focus restoration. Opening a modal neutralizes combat input. Phone layouts prioritize combat cues; secondary logs collapse. A persistent reward must survive refresh, not just look correct in a screenshot.

## 10. Research and completion tracking

Before calling a family complete, link its source/content paths, tests, a player-facing route and limitations beside the SYS-ID. Subdivide large entries rather than closing “quests” after one quest exists. Record baseline rules for region/version-dependent RO systems before selecting equivalents; review forum popularity separately from code license, maintainability and source provenance.

The local item converter can be extended with independent read-only NPC/quest/map summaries: source ID, category, relationships, counts, unsupported scripts and unresolved asset references. Keep server collision/map flags separate from renderable maps. Never claim that an emulator repository supplies a complete commercial client asset library.

For each content cycle: define user journey → author bounded data → validate → run server negative cases → play on desktop/phone → record first-time comprehension → adjust → admit final package. Keep the full coverage register active across releases; a narrower prototype is evidence toward the goal, not its completion.
