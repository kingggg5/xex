# Execution backlog

Current sequencing follows [plan v5](browser_ragnarok_babylon_rust_10k_plan_v5.md), work items V5-00–V5-14. E/T IDs below remain engineering work packages; P1a permits disposable session playtests, while completed P1b requires durable rewards and real-device evidence.

Status: this file holds the only live status table for plan work items ([Live status](#live-status)); other documents link here instead of restating status. V4-01–03 and V5-00–06 have local evidence; the P1 gameplay packages remain incomplete. Roles below are responsibilities and can be held by the same person. Sequence gates take precedence over calendar estimates. See the main plan for exact workload/quality targets.

The current client/server prototype covers browser boot, WebGPU/WebGL2 render paths, bounded local input, authoritative movement and combat events, runtime capsule collision, protocol v5 movement authority, local session/Origin checks, and revisioned session-owned character/quest snapshots. R5 city entry is reachable and a 21,400-triangle/205,644-byte meadow HLOD loads before the full city; the 892,347-triangle, 67,744,128-byte detailed city is requested only on gate entry and now includes one Quaternius CC0 market cart. Visual density/landmark readability, device memory/frame time, P1 human/device acceptance, playtests, and production-scale qualification remain open. Existing user instructions authorize local prototype implementation; gameplay tuning defaults are documented in [P1](p1-gameplay-contract.md), not a blanket extra permission gate.

## Live status

Update a row when an item starts, closes or is blocked, and link its evidence file. Definitions and acceptance criteria are in [plan v5 §7](browser_ragnarok_babylon_rust_10k_plan_v5.md).

| Item | Maps to | Status | Evidence | Updated |
|---|---|---|---|---|
| V4-01 Spawn slots and wall pressure | T03 | Closed | [v4-01](../planning/evidence/v4-01-spawn-collision.json) | 2026-09-23 |
| V4-02 Codec corpus | T04 | Closed (recorded on v2; v3 keeps the same checks) | [v4-02](../planning/evidence/v4-02-protocol.json) | 2026-09-23 |
| V4-03 Session identity and Origin | T05 | Closed | [v4-03](../planning/evidence/v4-03-session.json) | 2026-09-24 |
| V5-00 Repository and baseline hygiene | T01 | Closed | [v5-00](../planning/evidence/v5-00-baseline.json) | 2026-09-24 |
| V5-01 World owner and per-player channels | T06 | Closed | [v5-01](../planning/evidence/v5-01-world-owner.json) | 2026-09-24 |
| V5-02 Protocol v4 | E02 | Closed | [v5-02](../planning/evidence/v5-02-protocol.json) | 2026-09-24 |
| V5-03 Content bundle v0 and validator | E07 (part) | Closed | [v5-03](../planning/evidence/v5-03-content.json) | 2026-09-24 |
| V5-04 Motion authority | T07 | Superseded by V5-04b | [v5-04](../planning/evidence/v5-04-motion-authority.json) | 2026-09-25 |
| V5-04b Motion authority fixes | T07 | Closed | [v5-04b](../planning/evidence/v5-04b-motion-authority.json) | 2026-09-25 |
| V5-05a Tunnel-safe hardening | T05, T10 | In progress; 300/500/1000 ms C→S delays, missing-content refusal and 90-minute same-character resume soak pass; live mismatch/interface-switch/device/tunnel gates remain | [delay sweep](../planning/evidence/v5-05a-local-delay-sweep.json), [missing-content refusal](../planning/evidence/v5-05a-missing-content-refusal.json), [session soak](../planning/evidence/v5-05a-session-soak.json) | 2026-09-28 |
| E08 Technical art — reference city R5 | E01 coordinate fixture, brief review | In progress; R5 full runtime is 892,347 triangles/67.74 MB with 54 KTX2 textures and one detailed Quaternius CC0 cart; 21,400-triangle/205,644-byte meadow HLOD streams before it. Server gate route passes. Visual density/landmark parity and in-city Low/mobile budgets remain open. | [CC0 cart integration](../planning/evidence/quaternius-market-cart-r5.json); [city entry and HLOD](../planning/evidence/city-meadow-hlod-r5.json); [city entry smoke](../planning/evidence/city-entry-r5-smoke.json); [city visual r3](../planning/evidence/e08-city-visual-r3.json) | 2026-09-29 |
| V5-08a Combat feel spike | E04 (part) | Implementation and packet RTT gate pass; human feel check pending | [v5-08a](../planning/evidence/v5-08a-combat-feel.json), [v5-08](../planning/evidence/v5-08-combat.json) | 2026-09-25 |
| V5-05 Phone reach and device boot | T02, T10 | Not started; needs V5-05a; Android model pending; D-02 is decided | — | 2026-09-25 |
| V5-06 Server-owned state and real HUD | E05 (part) | Closed | [v5-06](../planning/evidence/v5-06-server-state.json) | 2026-09-25 |
| V5-07 Sella quest path | E04, E05 (part) | Closed | [v5-07](../planning/evidence/v5-07-quest-route.json) | 2026-09-25 |
| V5-08 Combat v1 | E04 | Packet RTT bot gate and room snapshot-slot event replay pass; human feel check pending | [v5-08](../planning/evidence/v5-08-combat.json) | 2026-09-25 |
| V5-09 Party and touch route | E05 | In progress; server-authoritative 4-member party, 6-char/10-minute invite, roster names, leave and nearby hunt credit are implemented and tested. Touch controls clear on modal/focus loss/pointer cancel; coarse-pointer menu and renderer-loss reload fallback added. Local 4-client protocol smoke passes. Physical device and human-route acceptance remain open. | [V5-09 progress](../planning/evidence/v5-09-party-touch-progress.json), [4-client party smoke](../planning/evidence/party-route-smoke.json) | 2026-09-29 |
| V5-10 P1a playtest rounds | G2 | Not started; needs D-03 | — | — |
| V5-11 Bot driver | T09 | Closed for local regression: seeded 10-bot / 600 s run passes with a Sella quest step, same-cookie reconnect, 99 visibility checks, zero protocol/socket errors, room cleanup, and bounded Node/Rust RSS. A separate 10-bot 100 ms RTT + jitter proxy smoke also passes. This is not phone or scale qualification. | [10-minute run](../planning/evidence/v5-11-swarm-10-600s-seed-20260929.json); [impaired smoke](../planning/evidence/v5-11-swarm-proxy-smoke.json); [driver](../tools/swarm-smoke.mjs) | 2026-09-29 |
| V5-12 Durable character identity | E06 (part) | Closed: PostgreSQL storage worker, principal cookie (30-day hashed), owner-epoch join fencing, coalesced saves, OAuth subject link, durable best floor; restart drill PASS | [v5-12](../planning/evidence/v5-12-durable-identity.json), [restart drill](../tools/persistence-restart-drill.mjs) | 2026-09-26 |
| V5-13 Durable quest, inventory and ledger | E06 | Closed: Appendix C normalized tables, transactional cold ops (op_results+ledger+outbox in one txn), op-cache hydration replay, degraded mode, failpoints; crash drill + restore-reconcile drill PASS | [v5-13](../planning/evidence/v5-13-durable-ledger.json), [crash drill](../tools/persistence-crash-drill.mjs), [restore drill](../tools/persistence-restore-reconcile.mjs) | 2026-09-26 |
| V5-14 P1b review packet | T10, G3 subset | Not started | — | — |
| T08 Spatial relevance (AOI) | — | Deferred to P2/P3, before the 50/100-bot step | — | 2026-09-24 |
| WORLD-S01 Sunmeadow south approach | E08, T08 prerequisites | Local two-cell route verified with 24 authored props and 26 colliders; grass, flowers, ferns and stone posts render. Desktop cloud glow repaired. Flat terrain, full art fidelity, phone budgets, navmesh and world perimeter remain open. | [Latest route](../planning/evidence/southbound-meadow-dressing-20260929.json), [desktop review](../planning/evidence/meadow-visual-verification-20260930.json), [cell manifest](../assets/models/world-v1/manifest.json) | 2026-09-30 |

## Owner decisions (recorded 2026-09-24)

| ID | Decision | Status |
|---|---|---|
| D-01 | Reference iPhone: iPhone X (owner's device). Reference Android: still open — needs a 4–6 GB RAM, Mali-G5x/G6x or Adreno 6xx-class device | Partial; user has a qualifying Android phone and will provide model; blocks device qualification |
| D-02 | Playtest mode: remote tunnel (single-port Rust server behind a free TLS tunnel, opened only during sessions) | Decided |
| D-03 | Testers: friends + Thai Ragnarok communities (5 new + 1 four-player co-op group) | Decided; recruiting starts before V5-10 |
| D-10 | Graphics quality presets Low / Medium / High / Ultra (formalizes §11.3 resolution cap + §14 lighting profiles; in-game switch, persisted locally). The web client aims for 30–60 fps with a 30/60 frame cap; details in plan §11.6 | Agreed 2026-09-24; frame-rate focus added 2026-09-25; part of V5-05 device boot, tuned before V5-08 |
| D-11 | Orientation: landscape-only for P1 (supersedes plan §11.4 portrait compatibility). Portrait shows a rotate-device gate, never a broken layout. V5-09 checks landscape 844×390 and 640×320 only | Agreed 2026-09-24; part of V5-09 |
| D-12 | Native desktop builds (.exe/.dmg): not before a stable public server (D-08). They would need a launcher or auto-updater and code signing. Desktop players use the installable web app meanwhile (plan §11.5) | Noted 2026-09-25; revisit at P3 or later |
| D-06 | P1 display languages: Thai + English keys, default from browser language | Decided 2026-09-24; implemented in V5-03 bundle + client |
| D-14 | Systems-first: ทำระบบเกมเพลย์/เน็ตเวิร์กให้เสร็จก่อน (V5-04b → V5-08a → V5-07 → V5-08 → V5-09); โมเดล 3D, อาร์ต/คอนเทนต์ไอเท็ม และ UI visual รอแก้ทีหลัง ไม่เป็น blocker งานระบบ | Agreed 2026-09-25; art track stays post-P1a, UI work limited to functional server-driven HUD |
| D-13 | Login page: guest (default), plus Google and Discord OAuth when the owner registers the apps (free tiers; client id/secret via `AETHERFIELD_*_CLIENT_ID/SECRET` env). Sessions gain a provider identity; the OAuth callback upgrades the browser's existing session. Session cookie moves SameSite Strict→Lax so the provider's top-level return navigation keeps it (deviation from plan §12.3, OAuth-specific). Durable provider-linked identity still lands with V5-12 | Owner requested 2026-09-25; implemented and committed (guest verified end to end; OAuth round trip awaits owner credentials) |
| D-14 | Social/economy systems requested 2026-09-26, sequenced against the plan's gates. **Now (session preview, in-memory per §12.1/P1-contract "ephemeral test rewards"):** gold + coin wallet, content-defined store, earnable loot box with published odds (never paid randomness, D-09), outfit/skin cosmetics, decorative follower pet, settings panel (UI scale/shake/flash/volume). **After V5-09 party:** player-to-player trade (needs roster/invite + two-client flows; escrow-confirm design). **After V5-12 durable identity:** clans (membership must survive restarts). **P2 multi-zone (E11 groundwork):** choose-map. **P5, with its own qualification:** combat pets. All wallet/grant operations carry `op_id` idempotency and content-defined values; full-bag refusals apply before consumption | Owner requested 2026-09-26; session preview in progress |

| D-15 | Rooms + tower requested 2026-09-26: 20 independent room instances x capacity 50 (per-session channel routing, auto = least-occupied, GET /rooms picker on the login gate and Settings), and a 100-floor tower (per-session private world instances, content-defined difficulty curve tower.json — hp x1+0.12/floor, count 3->11, exp x10.9, gold 5->~124 per floor, box every 10 floors, final 500g+100c+5 boxes) with auto-advance and notices; shared CharacterStore across all instances so rooms/tower never reset session progress (the V5-12 PostgreSQL seam). Honest limits: enemy attacks on players arrive with combat v1 (V5-08) so tower difficulty is hp/count/exp attrition until then; 50-player snapshots ~190 kbit/s peak per client until AOI (T08) | Owner requested 2026-09-26; implemented and committed, live-verified end to end (enter -> floor 1 instance -> panel state) |

| D-16 | Social layer requested 2026-09-26: player names (seeded Traveler-XXXX per session, shown in chat/HUD), room-scoped chat + cross-instance group chat (cold messages, cold budget enforced), friends (one-directional contact list, handles, presence from the rooms registry), and groups (party-like, max 4, 6-char code, shared across instances) — full-screen world map renders the zone POIs client-side. Clans wait for durable identity (V5-12) per D-14; friendship is one-directional in P1 | Owner requested 2026-09-26; in progress |

## Dependency spine

```text
E00 decisions/conventions
  -> E01 scaffold/device boot -> E02 codec/auth/input -> E03 authoritative movement
  -> E04 combat/touch -> E05 reconnect/playtest
  -> E06 durable inventory -> E07 progression/content validation
  -> E08 asset acceptance -> E09 hub/field slice
  -> E10 load qualification -> E11 multi-zone ownership
  -> E12 social/economy -> E13 operations/public beta -> E14 fleet qualification
```

After E00, an art-reference researcher may work alongside technical P0, but accepted production meshes depend on the coordinate/export fixture. Performance instrumentation begins in E01; E10 is the formal qualification, not the first measurement. Economy invariants are designed before UI or trade content.

## Work packages

| ID | Owner | Depends on | Deliverable | Exit evidence |
|---|---|---|---|---|
| E00 | Product + architect | v3 review | Confirm devices, scope, role allocation, original IP direction, first-phase budget; ADRs for topology/units | Explicit defaults or accepted choices, no hidden benchmark claims |
| E01 | Client + backend | E00 | Toolchain locks, Babylon boot/fallback, Rust health endpoint, build/CI, metrics skeleton | Desktop and phone render; forced WebGL2; clean startup/shutdown |
| E02 | Network | E01 | Versioned binary envelope, TS/Rust codec fixtures, WS authentication, limits/epoch | Invalid lengths/NaN/unknown version rejected; session-bound actor |
| E03 | Simulation | E02 | 20 Hz zone owner, capsule collision, authoritative motion, AOI seam | Two clients; replay/stale-input tests; 10 active bots; one-meter fixture |
| E04 | Game design + client/sim | E03 | Dodge, basic combo, two offensive skills, Guard Stance, enemy telegraph, touch layout | Hit/telegraph timing agrees; thumb controls usable; server damage authority |
| E05 | Network + QA | E04 | Grace/reconnect/resync, network impairment route, P1 playtest | Four-human loop; background/network switch recovery; no duplicate session |
| E06 | Data | E03, persistence contract | Inventory instances, ledger, durable reward, idempotency/outbox | Crash-before/after-commit matrix; duplicate/changed-payload rejection; restore |
| E07 | Game design + data | E04, E06 | CLOSED (2026-09-26): Base/Job dual EXP (content curves+caps), derived stats (golden ATK/MAXHP/DEF), per-slot equipment + equip_item op, store gear, client Job bar + Character modal + bag Equip | [e07](../planning/evidence/e07-progression-equipment.json), [equip smoke](../tools/e07-equip-smoke.mjs) |
| E08 | Technical art | E01 coordinate fixture, brief review | One prop, doorway kit, one rig pipeline; admitted packages | Provenance, Blender/export results, runtime clips, server collision and phone budgets |
| E09 | Content + client | E05, E07, E08 | Hub + field, 3 enemies, mini-boss, shop/storage, 3–5 quests | P2 loop; new-user objective completion; low-quality combat readability |
| E10 | Performance + QA | E03 onward; P2 for final workload | Active bots, AOI edge cases, hotspot profile, 3 repeated runs, safe overload | Qualified cap with hardware/content/workload receipt; no economy corruption |
| E11 | Backend + operations | E06, E10 | Two zones, portal handoff, fencing epochs, recovery/runbooks | Node-kill boundary cases preserve single owner and items |
| E12 | Game/data + moderation | E09, E11 | Parties, chat, guild membership, direct trade; later refine/market | Authorization/concurrency tests, block/report tools, logged support actions |
| E13 | Operations + QA | E10–E12 | Canary/rollback, migration compatibility, backups/PITR, alerting and incident drills | Fresh restore and rollback evidence; G6 checklist and on-call owner |
| E14 | Backend + operations | G6 and real demand | 2k/5k/10k qualified fleet scenarios, spare capacity, hotzones, traffic quotes | G7 workload report and cost range, 24-hour soak, failure during load |

## First ten implementation tickets

These are small reviewable slices, not ten concurrent agents.

1. **T01 — Pin versions and boot:** choose exact supported Babylon major/patch and Rust toolchain using current docs; add lockfiles, scripts and minimal build. Done when a fresh checkout starts reproducibly.
2. **T02 — Render fallback:** choose WebGPU when usable; handle initialization failure; verify WebGL2 explicitly; show a clear unsupported-device state. Done on desktop and one real phone with backend evidence.
3. **T03 — Coordinate fixture:** one-meter cube, capsule, doorway and slope with declared axes. Done when exported geometry and server collision agree.
4. **T04 — Wire contract:** minimum Hello/Welcome/Input/Snapshot/Error messages, endianness, bounds, version and connection epoch. Done with Rust↔TS golden fixtures and negative cases.
5. **T05 — Session gate:** authenticated connection, origin validation, input rate/size caps and reconnect identity. Done when a client cannot select another character by editing a payload.
6. **T06 — Tick owner:** dedicated world thread, monotonic 20 Hz clock, bounded command queues and telemetry. Done when tick work and lateness are separate metrics and overload is bounded.
7. **T07 — Motion authority:** local prediction, server ack, reconciliation and remote interpolation. Done with two clients and invalid speed/replay tests.
8. **T08 — Spatial relevance:** simple grid plus enter/leave events, hysteresis and teleport/cell-edge cases. Done when off-AOI entities disappear correctly without losing threats.
9. **T09 — Bot smoke:** separate protocol client exercising session/spawn/move/reconnect, fixed seed and 10-minute report. Done with 10 active clients and no leaked connections.
10. **T10 — P0 evidence:** short device route, forced fallback, two-client behavior, errors and budget report. Done when G0/G1 gaps are explicit; no claim that load smoke proves phone rendering.

**T03 progress:** `apps/protocol/coordinate-fixture-v1.json` now supplies one meter, handedness, axes, cube, player capsule, doorway, and ramp to both Babylon and Rust. Client prediction uses Babylon-derived bounds; Rust movement blocks the cube and doorway posts while allowing passage through the opening. Babylon geometry/collision tests, authoritative movement tests, and a two-client local browser smoke pass. Exported-asset parity remains open because no Blender MCP or local Blender CLI is exposed in the current session; the current field uses original procedural meshes.

**T04 progress:** T04 first delivered `apps/protocol/binary-v2.md` and its golden corpus. V4-02 added the full player/monster/event fixture and exhaustive byte-prefix checks; V4-03 supersedes v2 for live joins with `apps/protocol/binary-v3.md`, session-bound one-use tickets and a credential-free Welcome. `tools/protocol-size-comparison.mjs` compares JSON v1, fixed v3, and a manual Protobuf wire-size candidate; no generated schema library was installed or benchmarked.

**T05 progress:** delivered by V4-03: a random 256-bit HttpOnly session cookie, a one-use 15-second join ticket bound to that session, an exact Origin check, and rate, idle and join-deadline limits ([binary-v3.md](../apps/protocol/binary-v3.md)). Unit tests pass; the network-smoke evidence record is part of V5-00.

## Task handoff template

```text
Outcome:
Scope / owned paths:
Dependencies and exact versions:
Accepted inputs / contracts:
Excluded work:
Checks and workload:
Measured baseline / unknowns:
Resource and iteration limits:
Artifacts and evidence paths:
Recovery / rollback:
Next action:
```

## Change control

Changing a game target needs a reason and an affected-gate review. A failed target is not repaired by silently weakening it. Reprioritize new content against playtest evidence and accepted asset throughput. When scope grows, update the plan/backlog and workload together; keep old benchmark receipts immutable.

Pricing, dependency patches and model catalogs expire quickly. Recheck at the task that uses them. Revalidate the Harness runtime pin before upgrades rather than mixing files from different versions. Keep a stable protocol/content compatibility window during live rollouts.

## P1 contract checkpoint

The selected P1 slice follows plan v3: one original field, one melee vocation, two offensive skills plus dodge and Guard Stance, one quest/reward loop, and four human players. NPC shop and earnable box mechanics are explicitly staged after durable inventory/ledger and retry/crash checks; paid currency and real-money boxes remain excluded. P1 acceptance requires server-authoritative rewards, mobile device evidence, and new-player playtests. See [the full contract](p1-gameplay-contract.md).

## Next execution step

> See [Live status](#live-status).

Keep the full feature-family matrix phased through P2–P5; do not deploy or claim 10,000 CCU from local tests.
