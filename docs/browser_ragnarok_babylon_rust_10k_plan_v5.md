# Browser Action MMORPG — Plan v5

**Date:** 2026-09-24 · **Status:** current working plan; supersedes [v4](history/plans-v3-v4.md#plan-v4) · **Owner:** primary integrator (solo until staffing changes)  
**Goal:** an original browser and mobile action MMORPG with Ragnarok-style system depth (builds, drops, town services, party and guild), fun exploration and co-op, grown only as fast as evidence allows.  
**Tooling budget:** 0 THB for API generation, asset purchases and new cloud services until hosting decision D-08.  
**Live status:** [execution backlog → Live status](execution-backlog.md#live-status). This plan defines the work; the backlog tracks it.

**Amended 2026-09-25:** D-10 graphics presets and frame cap (§11.6); D-12 native desktop builds and the installable web app (§11.5); fixed playtest hostname (§11.1); telegraph aim point, telegraph timeline, combat-event delivery and an early feel check (§10.3, V5-08); device-loss recovery (V5-09); an off-machine copy of the repository (risk 10); asset budgets, flat-gameplay maps and a free-first asset pipeline with animation and effects (§14, playbook §5); V5-04 adds the last-applied-input position anchor and its protocol v5 wire revision after impairment testing found that the current position already includes repeated ticks.

## 0. Summary

**Where the project stands (verified from source, 2026-09-24)**

- A P0 technical slice runs locally: Babylon.js client with WebGPU and WebGL2 fallback, a 20 Hz Rust room, shared cube/doorway collision, binary protocol v3, and an anonymous session cookie with one-use join tickets and a strict Origin check. 33 Rust tests and 7 client tests pass.
- V4-01 (spawn/collision) and V4-02 (codec) are closed with evidence. V4-03 (session/Origin) is implemented; recording its evidence is the first task in V5-00.
- Still missing for P1: messages addressed to one player, movement reconciliation, enemy attacks and telegraphs, NPC/quest/party services, server-owned progression, durable state, real-phone runs and playtests.

**What v5 changes**

1. The reliability work gameplay depends on comes first: a world owner with per-player channels (V5-01), one protocol revision covering the whole P1 message set (V5-02), and movement reconciliation (V5-04). v4 ran these "alongside" gameplay; the code shows gameplay can't be built well without them.
2. The P1a gate measures fun as well as comprehension, and has a stop-and-rethink rule (§13).
3. New work items fill gaps v4 had no task for: phone access over HTTPS (V5-05), a durable character identity (V5-12), a bot driver (V5-11), and fuzzing (inside V5-02).
4. Concrete designs replace open questions: server threading, the v4 P1 message set plus the v5 movement-anchor extension, netcode, a latency budget for telegraphs, combat seed values, persistence tables and a playtest script.
5. Status lives in one place (the backlog). Agent and tool rules moved out of the plan.

**Next actions and open decisions:** see the backlog's [live status](execution-backlog.md#live-status) and [owner decisions](execution-backlog.md#owner-decisions-recorded-2026-09-24).

## 1. Document set and update rules

| Document | Role | Changes when |
|---|---|---|
| This plan | Strategy, order of work, work item definitions, gates, designs | A new version when strategy changes |
| [Execution backlog](execution-backlog.md) | Live status of every V5, E and T item, with evidence links | Whenever an item changes state |
| [System design catalog](system-design-catalog.md) | 34 system families and their coverage status | When a family changes status |
| [P1 gameplay contract](p1-gameplay-contract.md) | Player-facing P1 rules | When a P1 rule changes; this plan links rather than repeats |
| [Delivery and asset playbook](delivery-and-asset-playbook.md) | Tools, AI workflows, asset admission | When tools change |
| [Online storage architecture](online-storage-architecture.md) | Reference architecture adapting OpenAI Habitat for V5-12/V5-13 | When storage design changes |
| [MMO master program](mmo-master-plan-2027.md) | Proposed milestone forecast preserving all system families and the one-map 500-player target | Reforecast after measured gates |
| [Open-world production](open-world-production-plan.md) | Terrain, instance, streaming and art-budget contracts | With verified production changes |
| [Fleet scale plan](scale-to-10k-plan.md) | Conditional 10k fleet design and capacity ladder | With capacity measurements |
| [Plan reconciliation](reviews/2026-09-30-plan-reconciliation.md) | Source-grounded corrections to the supplied proposals | When reviewed assumptions change |
| [Sunmeadow asset research](reviews/2026-09-30-assets-lod-texture-research.md) | Current documentation, failed visual gates and bounded LOD/texture evidence | After candidate/device review |
| [Sunmeadow prop prompts](asset-prompts/sunmeadow-props-v1.md) | Twelve standalone English references with fixed fantasy style and reuse families | User generation and candidate selection |
| [Region loading and dungeons](region-loading-and-dungeons.md) | Outdoor streaming plus authoritative instance transition proposal | Before region/instance implementation |
| [Plan v3](history/plans-v3-v4.md#plan-v3) | Reference for G0–G7 definitions, performance budgets, load ladder, capacity arithmetic and zone handoff | Frozen |
| [Plan v4](history/plans-v3-v4.md#plan-v4) | Superseded; keeps the V4-01 and V4-02 closure notes | Frozen |
| `apps/protocol/*.md` | Source of truth for the wire format | With each protocol version |
| Content bundle (from V5-03) | Source of truth for tuning values | With each content revision |

Rules:

1. Status words (done, next, blocked) appear only in the backlog's live table. Other documents link to it.
2. An item closes only with an evidence file `planning/evidence/<id>.json` (fields in §15).
3. Appendix A stops being authoritative when the content bundle lands (V5-03), Appendix B when `binary-v4.md` lands (V5-02), and Appendix C when the first migration lands (V5-12).
4. IDs: P0–P5 product phases · G0–G7 evidence gates (v3 §10) · V5-xx work items · E00–E14 and T01–T10 engineering packages (backlog) · SYS-01–34 systems (catalog) · D-xx decisions (§17).

## 2. What changed from v4

| v4 problem | v5 change | Where |
|---|---|---|
| Status went stale within hours; the plan, the backlog and the Harness state still named V4-03 as next after it was built | One live status table in the backlog; the plan holds definitions only | §1, backlog |
| Gameplay items would be built on a world mutex with no way to send a message to one player | World owner and per-player channels (T06) become V5-01, ahead of every gameplay item | §6, §8 |
| No reconciliation; client and server cooldowns disagree; rejected actions vanish silently | Motion authority (T07) is V5-04; shared ability data; typed action results | §9, §10 |
| P1a measured only whether testers understood the loop | Fun thresholds and a pivot rule | §13 |
| No task made the game reachable from a phone; over plain http on a LAN, phones can't use WebGPU | V5-05 serving modes with HTTPS | §11 |
| P1b needed rewards to survive restarts, but nothing created a durable character | V5-12 durable identity | §12.3 |
| Every new feature needed a hand-written message codec in two languages | Protocol v4 designed once, split into hot and cold paths | §9, Appendix B |
| The scale ladder ignored hard caps in the code | Caps listed with what lifts each one | §3.3, §16 |
| Fuzzing was listed in the baseline, then dropped | Part of V5-02 acceptance | §7, §15 |
| Art steps were not in the schedule | Art track scheduled; CC0 baseline | §14, §18 |
| Agent permission and tool notes sat inside the product plan | Moved to AGENTS.md and the playbook | §20 |

## 3. Baseline snapshot (verified 2026-09-24)

A dated snapshot for context. For current status, use the backlog.

### 3.1 What exists and what P1 still needs

| Area | Exists | Still needed for P1 |
|---|---|---|
| Client rendering | Babylon.js 9.27.1; WebGPU first, WebGL2 fallback (`?renderer=webgl2`); procedural scene; DOM HUD; virtual joystick | Renders at full device pixel ratio (`adaptToDeviceRatio: true`), which is expensive on phones; no in-game performance report; never run on a real phone |
| Server loop | Axum and Tokio; 20 Hz `tick_loop` on the async pool; world behind `Arc<Mutex<World>>`; the same full snapshot broadcast to every client | A way to message one player; a dedicated simulation thread; tick metrics |
| Movement | Server integrates each player's latest input; shared capsule collision; stable spawn slots | Input acknowledgement and replay. Today the local player is only pulled 45% toward the server each snapshot, and remote players are lerped with no buffer. Ramps are test-only |
| Combat | Attack (3.25 m, 28 damage, 360 ms), Arc Slash (nearest target within 7 m, 60 damage, 5 s), Dodge (280 ms, 900 ms cooldown); 3 static "Meadow Slime" (90 HP, 9 s respawn) | Enemies never attack; no telegraphs, player damage or death; no facing or hit shapes; client cooldowns differ (180, 850, 420 ms); rejected actions are dropped without telling the client |
| Protocol | Binary v3: Join (ticket), Input, Action, Welcome, Snapshot, Error; golden bytes; truncation tests for every prefix | Acknowledged input sequence, facing, monster state, action results, per-player messages; fuzzing |
| Session | Random 256-bit HttpOnly SameSite=Strict cookie (1 h idle), one-use 15 s ticket, exact Origin `http://127.0.0.1:5173`, rate/idle/deadline limits | Memory only, so lost on restart; loopback only; no durable identity |
| HUD and progression | HP comes from the server | XP, quest counters, bag, potions, party roster, minimap party dots and chat are client-side placeholders |
| Persistence | None | E06 |
| Tests | 33 Rust, 7 client (`node --test`), a Node network smoke over raw sockets | Browser smoke on WebKit, real devices, network impairment, bots |
| Repository | No version control | V5-00 |

Evidence so far: [V4-01](../planning/evidence/v4-01-spawn-collision.json), [V4-02](../planning/evidence/v4-02-protocol.json) (recorded against v2; v3 kept the same checks). V4-03 is implemented in [auth.rs](../apps/server/src/auth.rs), [main.rs](../apps/server/src/main.rs) and [binary-v3.md](../apps/protocol/binary-v3.md); recording its evidence is part of V5-00.

### 3.2 Known defects and the item that fixes each

| Defect | Where | Fixed in |
|---|---|---|
| Held keys aren't cleared on window blur or tab switch, so a character can keep walking | [ui.ts](../apps/client/src/ui.ts) key handlers | V5-09 |
| Opening a modal doesn't neutralize combat input | ui.ts `openModal` | V5-09 |
| The minimap draws decorative party dots around the player; the HTML has a fixed roster (Lyra, Jory, Sola) and fake chat lines | ui.ts `drawMinimap`, `index.html` | V5-06 |
| Client cooldowns disagree with the server's; rejections are silent | [main.ts](../apps/client/src/main.ts) `onAction`; `handle_command` in main.rs ignores the result of `apply_action` | V5-02, V5-03, V5-08 |
| The enemy is "Meadow Slime" in code but "Puddlekin" in the contract; the HUD quest is slimes and clover instead of *Three Windmarks* | [world.rs](../apps/server/src/world.rs), ui.ts | V5-03, V5-07 |
| Combat event IDs restart at 1 when the process restarts | world.rs `next_event_id` | V5-13 uses persisted encounter IDs for rewards |
| The README said to open a second tab for a second player, but tabs share the session cookie, so the second tab is refused with `session_active` | README | Fixed with this revision |

### 3.3 Hard limits in code today

| Limit | Value | Where | What lifts it |
|---|---|---|---|
| Players per room | 16 | world.rs `MAX_PLAYERS` | AOI (T08) and protocol caps, P2–P3 |
| WebSocket connections | 16 | main.rs `MAX_CONNECTIONS` | Same |
| Snapshot records | 16 players, 64 monsters, 64 events | wire.rs, wire.mjs | AOI and a protocol revision, P3 |
| New sessions | 20 per minute for the whole server; 256 live | auth.rs | Per-client limits (V5-05) |
| Join tickets | 8 per minute per session; 15 s lifetime | auth.rs | — |
| Messages per socket | 60 per second; more closes the socket | main.rs | Per-type budgets (V5-02) |
| Session lifetime | 1 h idle, in memory | auth.rs | V5-12 |
| Resume grace | 30 s | world.rs `RESUME_GRACE` | — |
| World bounds | ±28 m | Hard-coded in world.rs, wire.rs, wire.mjs and main.ts | Zone bounds from content data (V5-02, V5-03) |
| Allowed Origin | Exactly `http://127.0.0.1:5173` | main.rs `ALLOWED_ORIGIN` | Configuration (V5-05) |

## 4. Vision, pillars and scope guardrails

**Pillars:** vocations with clear roles → combat you can read → exploration that pays off → a town where you change your build, trade and meet people → harder co-op content with friends.

| Inspiration | Principle we take | Our version |
|---|---|---|
| Ragnarok Online | Base/Job progression, builds, drops, sockets, town services, party and guild | Original world, names, story, art and balance; systems tracked in the catalog |
| Genshin Impact | Routes that reward exploration, visible landmarks, skills that interact with the world | P1 has one optional detour; P2 adds short puzzles; no big world until the route is fun |
| GTA Online | Map tied to activities, contacts who offer work, missions in stages | Expedition board → preparation → encounter → reward; event-driven town schedules |

**Coverage** means every SYS-ID gets an original equivalent, a named deferral or a named exclusion (see the [audit](ragnarok-multi-source-audit.md)). The reference is the pinned rAthena Renewal snapshot, and it defines only which systems to cover; balance and content stay original.

**Scope guardrails**

| Category | Items | Rule |
|---|---|---|
| Rejected | Gacha or paid random boxes; paid XP or drop boosts; FOMO daily streaks; live LLM dialogue in the simulation; vehicles; full NPC city simulation; any RO names, maps, art or client data | Reopened only by an explicit product decision |
| Deferred to P4 | Market and vending, refine, enchant and crafting, guild vault, more regions | After the economy gates |
| Deferred to P5 expansion | Siege and PvP, pets and mounts, user-made content, large open world, 10+ jobs, elemental reaction matrix | Each needs its own qualification |
| Research freeze | New RO data or website research | Resumes only when a P2+ design needs a specific family; write the question down first |

## 5. Release ladder and gates

| Phase | Player experience | Content ceiling | Exit evidence | Gates (v3) |
|---|---|---|---|---|
| P0 foundation | Join, move, collide, hit, disconnect and return | 1 field, 1 enemy type, 2 clients | V4-01–03, V5-00–V5-04, 10-bot smoke (V5-11) | G0, G1 |
| P1a session playtest | Talk to Sella → three windmarks → hunt with telegraphs → claim a session reward | 1 vocation (attack, dodge, Arc Slash, Guard Stance), 1 enemy type, 1 NPC, 1 quest, up to 4 players | §13 thresholds, including fun; controls pass on real phones; reset policy shown in game | G2 except the full phone budget |
| P1b complete P1 | The same loop; character and rewards survive reconnects and server restarts | Same as P1a | V5-12–V5-14; crash/restore matrix; iPhone, Android and desktop; four humans | G2 phone budget, G3 subset |
| P2 vertical slice | Hub and field, shop and storage, a build choice, a mini-boss | 3 enemy roles, 1 mini-boss, 3–5 quests, 5–10 NPCs, 12–20 items, 1 earned supply pack | Full player journey, budgets, content validator, transaction gates | G3 |
| P3 closed alpha | 2 vocations, party dungeon, moderated chat, rune trial | 1 instance, 1 co-op operation, 1 reusable event | Durable state, measured zone cap, 6-hour soak, support and report tools | G3, G4 |
| P4 closed beta | Connected zones, guild, trade, refine | 3–4 vocations; one new region per accepted content cycle | Zone handoff, economy concurrency and failure tests, moderation, rollback | G5 |
| P5 service | Content cadence, market, advanced roles; siege or pets if justified | Driven by measured content throughput | Service gate; 2k, 5k and 10k only with demand, budget and workload evidence | G6, G7 |

Rules: P1a never counts as P1b. A reduced scope never takes the next phase's name. P0 and P1a overlap on purpose, but the prerequisites in §6 are hard.

## 6. Critical path

```text
V5-00 → V5-01 → V5-02 → V5-03 → V5-04 → V5-04b → V5-08a feel spike → V5-07 → V5-08 → V5-09 → V5-10   (P1a gate)
                  ↘ V5-11 bot driver, in parallel from V5-02
V5-06 continues in parallel; V5-05a hardening before any tunnel; V5-05 needs V5-05a
V5-05 phone reach: any time after V5-00; must be finished before V5-08 tuning starts
V5-12 identity → V5-13 persistence → V5-14   (P1b gate; can start once V5-07 is done)
People (start now): D-01 phones · D-02 playtest mode · D-03 testers
```

Why this order:

- **V5-01 first.** Quest state, bag contents, NPC replies and action results each go to one player. Today the server can only broadcast one snapshot to everyone. Building the per-player path once costs less than inventing one per feature and redoing them all later.
- **V5-02 once.** P1 needs about twenty new message kinds. Designing them together avoids a separate protocol bump, codec pair and golden-fixture set for each feature.
- **V5-04 before V5-08.** Combat tuned on top of rubber-banding movement ends up compensating for netcode.
- **V5-05 before V5-08 tuning.** Tune combat on the phones the fun test will use.
- **Persistence after P1a is safe** because P1a uses disposable state. V5-12 and V5-13 can overlap V5-09 and V5-10 while you wait for testers.

## 7. Work queue

Sizes are for forecasting only: **S** ≈ 1–2 focused days, **M** ≈ 3–6, **L** ≈ 7–12, for one person working with full focus. Record actual start and finish dates in the backlog and reforecast after Block 2 (§18).

| ID | Deliverable | Acceptance evidence | Depends on | Size |
|---|---|---|---|---|
| V5-00 | Repository and baseline hygiene. `git init`. `.gitignore` adds `references/rathena/`, the generated `exports/` data, and `**/node_modules/`, `**/dist/`, `**/target/`. First commit; an optional private remote. One `verify` script (rustfmt, clippy, cargo test, tsc, node tests, `verify_plan.py`). Rerun the network smoke on v3 and write `v4-03-session.json`. Set up the backlog live table. | `git status` is clean after a build; `verify` passes; the V4-03 evidence names the commit | — | S |
| V5-01 | World owner and per-player channels (T06). The world runs on a dedicated thread with a bounded command inbox. Each connection gets a latest-snapshot slot plus a bounded reliable queue (64 messages). Slow readers are resynced or closed. Tick work and lateness are measured separately. New joins stop when overloaded. No socket task ever locks the world. | A per-player message reaches only its owner; a paused reader can't push memory past the caps and gets closed or resynced; inbox overflow stays bounded; metrics separate work from lateness; existing tests and the smoke still pass | V5-00 | M |
| V5-02 | Protocol v4 with the whole P1 message set (§9, Appendix B). The hot path stays fixed binary; the cold path uses one envelope type carrying tagged, size-capped JSON. TypeScript types are generated from the Rust types. Zone bounds come from content, Welcome carries the content hash, rate budgets are set per message type, and v3 packets are rejected. | Golden bytes for every hot message and canonical JSON for every cold message; truncation and negative tests; randomized decoder tests in the normal suite; cargo-fuzz targets run at least 10 min each on Linux or WSL; `binary-v4.md` written | V5-00; integrates after V5-01 | M |
| V5-03 | Content bundle v0 and validator. `content/source/` (manifest, zones, abilities, enemies, NPCs, `dialogue/{th,en}`, quests, items) builds to `content/build/<hash>/`. Rust and the client load the same bundle. The validator follows [catalog §2](system-design-catalog.md), including localization keys. The server refuses a mismatched hash. | Invalid bundles fail (duplicate ID, dangling reference, NaN, cycle, missing th or en key); no hard-coded cooldowns remain in client or server; Meadow Slime becomes Puddlekin through data | V5-02 | M |
| V5-04 | Motion authority (T07). Fixed 50 ms steps on both sides; the server applies one queued input per tick, repeats the last input for at most 5 ticks, then stops. A snapshot carries both `ack_seq` and the server position immediately after that input was applied; the client resets to this anchor and replays newer inputs without counting repeat movement twice. Adds per-frame remote interpolation, app-level Ping/Pong and a seeded delay/loss proxy. | Over 45 s per correction profile, with proxy-added base RTT 0/100/200 ms (one-way delay 0/50/100 ms), uniform ±30 ms one-way jitter and 1% WebSocket data-frame loss: post-replay correction p95 ≤0.15/0.25/0.40 m; no correction snap >1 m; record measured Ping/Pong RTT. At 100 ms base RTT, two clients for 45 s: observer samples at least 30 Hz, remote step p95 ≤0.15 m and max ≤0.20 m; delay stays 75–200 ms; no protocol/socket errors. | V5-01, V5-02 | M |
| V5-04b | Motion authority fixes. The local player is drawn between predicted steps, not in 20 Hz jumps. Quickstep and cooldowns ride the input timeline: the boost applies to the N inputs after the action's sequence (N from content), predicted identically on the client; cooldowns counted in ticks; a rejected dodge is undone. The scheduling lead uses a filtered RTT and moves by at most one tick per update. The client's server-tick estimate slews both ways. Remote extrapolation holds at its limit. At most 2 catch-up ticks, with skipped ticks counted. Queue-depth control. FIFO-correct impairment proxy. Offline preview starts at (0, −2). | Scenario gate: seeded wander with stops, turns, a dodge every 1.5 s and at the cooldown edge, wall sliding; 16 ms and 33 ms frame cadence; 0/100/200 ms profiles plus one real-TCP loss profile. Correction p95 ≤0.15/0.25/0.40 m, p99 ≤2× the p95 limit, no snap >1 m, snapshots corrected by >1 cm ≤2%; cooldown-edge dodges accepted ≥99%; remote interpolation error p95 ≤0.05 m and ≤1% held frames; a 60-minute simulated-time run with ±100 ppm clock offset and one skipped tick per 5 minutes keeps held frames ≤1%; one late Pong of 1.5 s does not stop input; the real client in Playwright at 60 fps moves the local player every frame; no socket closes or errors over any run. Evidence written by script from a committed tree. | V5-04 | S–M |
| V5-05a | Tunnel-safe hardening. Token-bucket budgets that close only on sustained excess and send Error first; epoch-correct fencing, reader/writer linkage and a client snapshot watchdog; a new Join takes over its session (or idle timeout ≤10 s); content loads before the port opens and /healthz reports the world thread; non-blocking logging; session refresh during play; reload-once guard; wire bounds from zone content. | 300/500/1000 ms uplink stalls don't close the socket; dropped outputs and join timeouts leave no ghost; a network switch rejoins within 5 s; missing content refuses to start; a 90-minute session reconnects to the same character; a content mismatch reloads once, then shows an error. | V5-04b | S |
| V5-08a | Combat feel spike. Puddlekin Splash Hop with a ground telegraph drawn from the newest snapshot, Quickstep, attack and hit feedback (hit-stop, flash, damage number, sound) with CC0 placeholders. No quest or HUD work. | An informal feel check by 2–3 people outside the P1a pool, on desktop and the iPhone X over a tunnel: notes on whether they dodge the telegraph on purpose and want to keep playing; if it feels flat, apply the §13.4 levers before V5-07. | V5-04b, V5-05a | S |
| V5-05 | Phone reach and device boot (T02, T10). Configurable bind address and Origin allowlist; a non-loopback bind is refused without an allowlist. In playtest mode, Rust serves the built client on one origin. HTTPS through a free tunnel or mkcert, and a `Secure` cookie under HTTPS. Per-client session and connection limits. An in-game performance report. Graphics presets, each with its own internal-resolution cap, and a 30/60 fps cap (D-10, §11.6). A web app manifest so the game installs as an app (§11.5). | The reference Android boots over HTTPS on WebGPU and on forced WebGL2; the reference iPhone X (iOS 16, no WebGPU) boots over HTTPS on WebGL2; performance report, including preset and frame cap, captured on a 10-minute route; the chosen preset survives a reload; the game installs from desktop Chrome or Edge and from the iOS home screen; foreign Origins still rejected; the Vite dev server is never exposed | V5-00, V5-05a, D-01, D-02 | S–M |
| V5-06 | Server-owned character state and a real HUD. P1a starts at level 1 / 0 EXP with content-defined HP, a 12-slot bag containing three content-defined Trail Potions, an uncapped material pouch and a per-character `three_windmarks` quest record. The world owner emits revisioned character and quest snapshots on resync, and potion use returns an operation result plus the new character revision. Potion healing and cooldown come from content; duplicate `op_id` retries are bounded and idempotent in memory. Reconnects resync. Online mode hides the preview roster/chat/party dots and uses only server state; offline preview stays labeled and separate. | With a 2,500 ms one-way WebSocket frame delay, the connected HUD remains in its loading state until cold state arrives; hot snapshots may still show server-owned HP. Local smoke confirms character/quest resync and reconnect. A full-HP potion is rejected end to end; Rust unit tests cover successful healing, cooldown, duplicate retry, payload conflict and retained session state. Position remains in the Welcome/snapshot path. State resets on server restart; quest interaction, objective progress and reward claim land in V5-07/08. | V5-01, V5-02, V5-03 | M |
| V5-07 | Sella → windmarks → hunt → return. NPC interaction state machine with choice tokens ([catalog §3](system-design-catalog.md)). Windmark activation takes a 1 s channel within 2 m, interrupted by damage or movement. Per-character objectives and the hunt credit rule (§12.2). Claims carry an `op_id` (kept in memory for P1a). Quest markers, and a minimap drawn from zone data. | Out-of-range, wrong-order, duplicate and stale-choice actions are rejected; a repeated `op_id` returns the stored result; a changed payload conflicts; four players each get the right credit; each route step is timestamped | V5-06 | M |
| V5-08 | Combat v1. Puddlekin AI: idle, approach, windup, active, recovery, respawn; aggro 8 m, leash 16 m. A ground telegraph with shape, timer and sound, drawn from the newest snapshot (§10.3). The current Monster record has no aim point, but Splash Hop's circle sits on the target, so V5-08 adds one (a protocol revision with new golden bytes); the content bundle defines the circle by its radius. Combat events survive a skipped snapshot: each connection's slot keeps only the latest snapshot and each event rides in one snapshot, so events repeat for a short window and are deduplicated by ID, or move to the reliable queue. Enemies deal damage; players die and respawn at the regroup point. Arc Slash becomes a 120° cleave hitting up to 3 targets. Guard Stance with a perfect-guard counter. Rejections shown with typed reasons. Hit feedback (§10.4). Timings come from content data and fit the latency budget (§10.3). | Telegraph start, impact and recovery agree between client and server within one tick; at 150 ms round trip, a dodge inside the window avoids damage in at least 95% of scripted bot trials; with a paused writer, no combat event is lost; rejection reasons are visible; unfair hits are counted; an informal feel check by 2–3 people outside the P1a new-tester pool, on desktop and a phone, and if it feels flat, adjustments with the §13.4 levers before V5-09 | V5-03, V5-04, V5-06; tuning after V5-05 | L |
| V5-09 | Party and touch route. Create a party with a 6-character invite code valid for 10 minutes; join, leave, and a roster from the server. Separate pointer ownership for stick, camera and buttons. Input is neutralized on blur, hidden tab, modal open and pointer cancel. Rendering recovers from a lost WebGPU device or WebGL context, or reloads and rejoins. Safe areas, 44 px targets, a rotate-device gate in portrait (D-11), and audio started on the first gesture. Notes from the first new-user session. | Four players, at least two on phones, finish the route; no stuck movement or lost rendering after an app switch, notification or call; a forced device or context loss (`device.destroy()`, `WEBGL_lose_context`) recovers or reloads cleanly; no page scroll or zoom from gameplay; landscape 844×390 and 640×320 checked, and portrait shows the rotate gate (D-11) | V5-05, V5-07, V5-08 | M |
| V5-10 | P1a playtest rounds (§13): five new testers plus one four-player session; iterate and record results. | §13 thresholds met, or the pivot review held | V5-09, D-03 | M, needs people |
| V5-11 | Bot driver and regression (T09). Turn the Node smoke into a seeded protocol bot (join, move, attack, quest steps, reconnect) with impairment options; V5-04 and V5-08 use it. | 10 bots for 10 minutes with no leaked connections or tasks, bounded memory and no protocol errors; the report includes the seed | V5-02 | M |
| V5-12 | Durable character identity. PostgreSQL with migrations; principal and character tables. A long-lived HttpOnly cookie with a 30-day sliding lifetime, stored hashed. Owner-epoch fencing. A restart restores the character. | After a server kill and restart, players rejoin as the same character; two tabs or devices on one cookie still leave one live owner; the database rejects writes from a stale epoch | V5-01; can start after V5-07 | M |
| V5-13 | Durable quest, inventory and ledger (E06). Tables and constraints as in Appendix C. A persistence worker outside the world thread. Claims, loot and potion use are transactional. Encounter IDs are UUIDv7. An outbox, failpoints for crash tests, and a backup and restore drill. | The failure matrix (§12.4) passes with failpoints; a concurrent duplicate claim grants once; a changed payload conflicts; a full bag is refused before any change; a DB outage shows pending and stops valuable writes; a fresh restore reconciles the ledger | V5-06, V5-07, V5-12 | L |
| V5-14 | P1b review packet. The four-player route on desktop, iPhone and Android with durable state, including a restart mid-session. Evidence names the build, content hash, devices, network and limits, and includes a visual comparison with the reference crop. | All §12.4 cases; a two-tester sanity rerun of §13; device budgets recorded | V5-05, V5-10, V5-11, V5-13 | M |

T08 (area of interest) isn't needed in P1: there's one small field and at most 16 players. It's scheduled before the 50- and 100-bot step (§16).

## 8. Server architecture for P1 (V5-01)

```text
socket task (one per connection) ── try_send ──► world inbox (bounded)
                                                    │
     world thread: drain up to N commands per connection → simulate 50 ms → build outputs
                                                    │
            ┌────────────── per connection ─────────┴────────────┐
            ▼                                                     ▼
 latest-snapshot slot (overwritten, never queued)   reliable queue (bounded 64: results, state updates)
            └──────────────────► writer task (one per connection) ◄┘

world thread ── bounded ──► persistence worker (V5-13) ── results come back through the inbox
```

- The world thread never waits on I/O or on a full channel. A failed `try_send` marks that connection for resync or close and increments a counter.
- Every command carries the connection ID, player ID and epoch; the world checks the epoch.
- Each tick drains at most 4 inputs, 2 actions and 2 cold messages per connection. Anything beyond that is dropped and counted; repeated excess closes the connection.
- Each connection gets its own snapshot: its own record (with the acknowledged input and private flags) plus other entities. That means everyone until AOI exists.
- Metrics (logged every 10 s in development): tick work p50/p95/p99, lateness, inbox high-water mark, dropped commands, resyncs and closes, snapshot bytes per connection per second, reliable-queue high-water mark.
- Budgets from v3: work p99 at or below 40 ms at 20 Hz; fewer than 0.1% missed deadlines; catch up at most 2 ticks; stop admitting players while behind.
- Qualify timing on the Linux host you'll deploy to, because Windows development timers behave differently.

Tokio's `watch` channel suits the latest-snapshot slot and a bounded `mpsc` suits the reliable queue. Confirm the current APIs with Context7 when implementing.

## 9. Protocol v4 base and v5 motion anchor (V5-02, V5-04)

- **V4 base**: V5-02 delivered the full P1 message set and cold path in protocol v4; its fixtures remain archived in `apps/protocol/golden-v4.json`.
- **V5 motion anchor**: V5-04 increments the envelope to version 5. A snapshot adds `ack_x` and `ack_z`, the authoritative position immediately after applying `ack_seq`. This is required because the current server position can include up to five repeated movement ticks after that sequence. V5 clients reject v3 and v4 packets.
- **Envelope**: the six-byte magic/version/type/length framing and v4 validation limits remain unchanged.
- **Hot path**, fixed binary: Input, Action, Snapshot, ActionResult, Ping and Pong. These go out every tick or every input, so byte-level tuning pays off.
- **Cold path**: one envelope type per direction (`0x10` client to server, `0x90` server to client) carrying UTF-8 JSON tagged by `"t"`.
  - Capped at 512 bytes from the client and 4 KiB from the server.
  - The Rust types, with unknown fields denied, are the schema; TypeScript types are generated from them (for example with ts-rs or typeshare).
  - These messages change often during P1–P2 and are sent a few times a minute, so a hand-written binary codec for each would cost more time than it saves.
- **Rate budgets per message type** replace the single 60-message limit: Input ≤25/s, Action ≤10/s, cold messages ≤5/s, Ping ≤2/s, measured over 1 s windows. Sustained excess closes the connection with an error.
- **Bounds** come from the zone in the content manifest, with a protocol hard maximum of ±4,096 m.
- **Compatibility**: Welcome carries the content hash (FNV-1a-64 of the canonical bundle, which covers every manifest field) and the tick rate. The client refuses a mismatch and reloads.
- **Idempotency**: every value-changing cold request (claim, item use) carries an `op_id` UUID. The server stores (principal, operation kind, `op_id`) with a payload digest and the result.
- **Size check**: a P1 snapshot with 4 players, 8 monsters and 2 events is about 358 bytes after the 8-byte v5 ack-position anchor. At 20 Hz that's roughly 58.3 kbit/s per client before WebSocket framing. Deltas and AOI come later.
- **Later review**: revisit the cold-path encoding at P3 if measured bandwidth says so.

## 10. Netcode and combat feel (V5-04, V5-08)

### 10.1 Movement

- Client and server both simulate fixed 50 ms steps with the same capsule rules. The client uses its JavaScript port today; a Rust/WASM kernel is justified only by measured drift.
- The client samples input once per step, sends Input (sequence, movement, facing), predicts locally, and keeps unacknowledged inputs in a ring buffer of up to 64.
- The server queues up to 3 inputs per player and applies one per tick. If none has arrived, it repeats the last one for up to 5 ticks, then stops the player. Snapshots acknowledge the last applied sequence.
- On each snapshot, the client resets to `(ack_x, ack_z)` and replays inputs newer than `ack_seq`. The current player position is diagnostic; using it as the replay base would count repeated server ticks twice. Correction distance is the old predicted current position to the post-replay position. Corrections under 0.25 m blend in over 100 ms, 0.25–1 m over 200 ms, and anything over 1 m snaps. Every correction distance is included in bounded session metrics.
- Remote entities render at server time minus an interpolation delay. The delay starts at 100 ms, adapts to two ticks plus p95 jitter, and stays within 75–200 ms. Extrapolation stops after 100 ms and the entity holds position. Telegraphs are the exception (§10.3).
- Round-trip time comes from an app-level Ping/Pong every 2 s, because browsers don't expose WebSocket pings. It shows in the debug HUD and the performance report.
- Movement-affecting actions (Quickstep) ride the input timeline: the server applies the boost to the N applied inputs after the action's sequence, and the client predicts the same N steps. No wall-clock timer affects movement. Cooldowns are counted in ticks on both sides.
- The client's server-tick estimate never jumps backward but slews both ways (at most 0.02 tick per snapshot backward), so clock drift and skipped server ticks can't push remote rendering past the buffer.

### 10.2 Actions

- An Action carries the sequence number, ability, aim direction, an optional target, and `view_tick`: the tick of the newest snapshot, which is the timeline telegraphs are drawn on (§10.3).
- The server checks state, cooldown, cost, range and shape in server time, then returns an ActionResult to that player only: accepted or rejected, the reason, and the remaining cooldown.
- The client plays the swing immediately. Impact effects (spark, damage number, hit-stop) wait for the server's event.
- Each rejection reason has a cue. Cooldown flashes the time left on the button; out of range pulses a range ring. The other reasons are no target, dead, busy, not allowed here, and rate limited.

### 10.3 Latency budget for telegraphs

Telegraphs are drawn from the newest snapshot, not through the interpolation buffer. As soon as a snapshot shows a windup, the client draws the shape at the monster's aim point and fills it from `state_ticks_left`. The monster's body stays on the interpolated timeline, so its squash pose may trail the circle slightly; the circle is what players react to. This keeps the 75–200 ms interpolation delay out of the budget.

```text
time lost before the player can react ≈ round trip + one tick (50 ms)
minimum fair windup ≈ time lost + human reaction (about 250 ms) + margin
```

| Network profile | Round trip | Time lost | Minimum windup | P1 target |
|---|---:|---:|---:|---:|
| Home Wi-Fi | 40 ms | ≈90 ms | ≈340 ms | ≥800 ms |
| Typical mobile | 100 ms | ≈150 ms | ≈400 ms | ≥800 ms |
| Poor mobile | 200 ms | ≈250 ms | ≈500 ms | ≥800 ms |

Drawn through the interpolation buffer instead, each row would lose another 100–150 ms, and poor mobile would need about 650 ms, which leaves the 800 ms target borderline.

Policy: resolve dodges in server time first, as v3 recommends, and count **unfair hits**. An unfair hit is one where the player sent the dodge while their screen (per `view_tick`) still showed the windup, and the dodge would have avoided the hit at that moment. If unfair hits exceed 5% of hits on the typical-mobile profile in playtests, add a bounded rewind for dodges only: at most 150 ms, and never across geometry changes.

### 10.4 Hit feedback (part of V5-08)

| Moment | Feedback |
|---|---|
| Attack pressed | Swing trail and sound immediately |
| Hit confirmed by the server | 60–80 ms hit-stop (presentation only), 80 ms white flash on the target, 0.3 m knockback (server-owned for enemies), damage number, impact sound |
| Player hurt | Red edge flash and a small camera shake (off with reduced motion), hurt sound |
| Enemy windup | Ground shape filling over the windup, rising sound, squash pose |
| Perfect guard | Distinct sound, short freeze, "Counter!" prompt |
| Enemy defeated | Pop effect, drop sparkle, sound |

Audio comes from a CC0 pack (§14) and starts after the first user gesture, which mobile browsers require.

## 11. Devices, reachability and mobile (V5-05, V5-09)

### 11.1 Serving modes

| Mode | For | How | Origin allowlist |
|---|---|---|---|
| Local development | Daily coding | Vite dev server with proxy (today) | `http://127.0.0.1:5173` |
| LAN playtest | Testers in the same room | Rust serves `apps/client/dist`, the API and the WebSocket on one port, over HTTPS with an mkcert certificate trusted on each test phone | `https://<lan-host>:<port>` |
| Remote playtest | Testers elsewhere | The same single-port server behind a free TLS tunnel, for example a Cloudflare quick tunnel | `https://<tunnel-host>` |

- **Never tunnel the Vite dev server.**
- The server refuses a non-loopback bind unless an allowlist is configured.
- Cookies are `Secure` under HTTPS.
- Session and connection limits apply per client. Trust a tunnel's client-IP header only when the connection comes from the local tunnel process.
- Record the serving mode in the evidence.
- HTTPS is required. Over plain http on a LAN IP the page isn't a secure context, `navigator.gpu` is missing, and phones would only ever test WebGL2.
- Opening any endpoint reachable from the Internet, even a short-lived tunnel, is an owner decision (D-02).
- A quick tunnel gets a new random hostname on every run. Cookies belong to a hostname, so V5-12 characters and the Origin allowlist reset whenever the tunnel restarts. If testers return across days (P1b), use a fixed hostname: a named Cloudflare tunnel on a domain you own (a domain costs money, so it's an owner decision) or a free fixed-name service such as Tailscale Funnel.

### 11.2 Reference devices (D-01)

| Slot | Criteria | Examples (the owner picks) |
|---|---|---|
| iPhone | The oldest model you intend to support, on the newest iOS it can run. The iPhone X stops at iOS 16 and has no WebGPU; it is the WebGL2 floor device | iPhone X (owner device, D-01) |
| Mid-range Android | 4–6 GB RAM; Mali-G5x/G6x or Adreno 6xx-class GPU; current Chrome | Samsung Galaxy A series, Redmi Note series |
| Desktop | Mid-range PC; Chrome or Edge plus one other browser | The development machine counts |

For each run, record the model, OS and browser version, render backend, internal resolution, and thermal or battery state.

### 11.3 Rendering budgets (from v3)

- Frame time p95: at or below 33.3 ms on the reference phones and 16.7 ms on desktop, over a 10–20-minute route.
- Cap internal resolution on phones at about 720p, the Medium preset (§11.6). Today's code renders at the full device pixel ratio.
- Download size: at most 12 MB compressed through P1 and 25 MB in P2. In P2, first control within 15 s at 20 Mbps and 80 ms round trip.
- Memory: an investigation target of 350 MB or less on phones. On iOS, a tab killed for memory is the likeliest first failure, so watch texture memory.
- Safari's Web Inspector for iOS normally needs a Mac, so the in-game performance report is the main evidence tool. It records backend, pixel ratio, internal resolution, frame-time percentiles, and memory where available.

### 11.4 Mobile control contract

- Controls: left stick, camera drag on the right, and attack, dodge, two offensive skills, Guard Stance and interact.
  - Each control has its own pointer ownership; touch targets are at least 44 CSS px.
  - Respect safe areas. Settings for scale, opacity, text size, and reduced shake and flash.
  - A left-handed layout comes once the core controls pass.
- Movement is neutralized on pointer cancel, lost pointer capture, window blur, hidden tab, modal open and disconnect.
- Landscape checks at 844×390 and 640×320; portrait shows the rotate-device gate (D-11).
- iPhone Safari has historically lacked element fullscreen and orientation lock. If landscape matters, also qualify home-screen (installed web app) mode on your target iOS version.
- For early WebKit coverage on Windows, run the browser smoke in Playwright's WebKit. It doesn't replace a real iPhone.

### 11.5 Installable web app and native desktop builds (D-12)

- The client ships a web app manifest (name, icons, `display: standalone`). Chrome and Edge then offer to install the game on Windows and macOS, Safari offers Add to Dock, and iOS gets home-screen mode (§11.4). The installed app loads from the same origin, so cookies and the Origin allowlist don't change, and it updates like the web page.
- Any service worker fetches client files network-first. A cache-first client would make the content-hash reload (§9) loop on an old build.
- Native .exe and .dmg builds are D-12, not a P1 or P2 deliverable. They need:
  - a stable public server (D-08). While the server runs only during playtests, a downloaded client has nothing to join.
  - a launcher or auto-updater. The client reloads on any protocol or content-hash mismatch, and an installed build can't get a new client by reloading.
  - a signing budget. Unsigned, macOS Gatekeeper blocks the app until the player allows it under System Settings → Privacy & Security, and Windows shows a SmartScreen warning. The Apple Developer Program costs US$99 a year; Windows code-signing certificates also cost money every year.
  - the publishing decision (§20) and the risk 9 name review, if builds go on a public GitHub repository. Testers can't download releases from a private one.
- A wrapper (Tauri or Electron) runs the same web client, so it doesn't raise the frame rate or the graphics ceiling. Loading the server's URL keeps cookies working. Bundling the client makes requests come from an app origin such as `tauri://localhost`, where the SameSite=Strict cookie isn't sent, so sign-in would need a token.
- Tauri fits the Rust stack and keeps downloads small but uses each OS's own web engine. Electron ships Chromium, so both builds behave like Chrome, at roughly 100 MB per download.

### 11.6 Frame rate and graphics presets (D-10)

- **Frame rate:** the web client aims for 30–60 fps. The §11.3 budgets require at least 30 fps on the reference phones and 60 on desktop. A frame cap offers 30 and 60; phones start at 30 and desktops at 60. There's no uncapped mode: on 120–144 Hz screens it costs battery and heat for little gain.
- **Presets:** Low, Medium, High and Ultra, switched in game and saved locally. Phones start on Medium, desktops on High. Presets change presentation only; gameplay, collision, telegraphs and hit signals are the same in every preset (§14 readability rule).
- Seed values, tuned with the performance report before V5-08:

| Preset | Meant for | Internal resolution | Shadows | Effects and foliage |
|---|---|---|---|---|
| Low | Older phones, battery saving | About 540p | Off | Reduced |
| Medium | Reference phones | About 720p (§11.3) | Simple | Standard |
| High | Desktop | About 1080p | Real-time | Standard |
| Ultra | Strong desktops | Full device pixel ratio | Real-time, higher quality | Full |

- Budgets (§11.3) are qualified on each device's starting preset. The performance report records the preset, the frame cap and the internal resolution.
- The procedural P1 scene gives High and Ultra little to add beyond resolution and shadows. The effect and foliage differences arrive with the art kit and lighting profiles after P1a (§14).

## 12. Game rules, state and persistence

### 12.1 Character state (P1)

| State | P1a (memory) | P1b (durable) |
|---|---|---|
| Character identity | Per session | Durable (V5-12) |
| Level, base EXP | Memory | Committed with the reward transaction |
| HP, position, zone | Memory | Checkpoint every 15 s and on disconnect. After a restart, resume at the checkpoint or the regroup point |
| Bag (12 slots) and material pouch | Memory | Transactional |
| Potions | Memory | Transactional on use |
| Quest progress | Memory | Written on each objective change, asynchronously; a crash loses at most the latest step |
| Cooldowns, combat state | Memory | Never stored |

P1a reset policy: characters reset when the server restarts and before each playtest round, and the join screen says so.

### 12.2 Party, credit and loot (amends v4 §6; the P1 contract is updated to match)

- **Party** size is at most 4; a solo player is a party of one. Creating a party gives a 6-character invite code valid for 10 minutes. Joining requires being in the same zone.
- **Hunt credit.** When enemy E is defeated, credit goes to every member of the killer's party who, at the killing blow:
  - has the quest active,
  - is in the same zone,
  - is connected or still inside the resume grace period, and
  - is within 30 m of E.

  Membership is frozen at the killing blow. Members who are down but in range still get credit, and supporters don't need to deal damage. Kills stop counting once the objective's cap is reached.
- **Field loot:** each eligible character (the same rules without the quest condition) gets one Dew Bead per defeat, keyed by (encounter ID, character ID). In P1, materials go to an uncapped material pouch, so a full bag can never destroy loot.
- **Quest reward** needs a bag slot. With a full bag, the claim is refused before anything changes and the quest stays ReadyToClaim.
- **Windmarks** are personal: each character activates three different windmarks.
- **Kill tagging**: P2 revisits first-hit tagging so one party can't take another party's kills.

### 12.3 Identity for P1b (V5-12)

- `POST /session`: a valid principal cookie refreshes the session; otherwise the server creates a principal and a character.
  - The cookie is a random 256-bit value, stored as its SHA-256 hash in the database.
  - It is HttpOnly, `Secure` under HTTPS and SameSite=Strict, with a 30-day sliding lifetime.
- One live owner per character: joining increments `owner_epoch` with a conditional update, and every durable write includes the current epoch in its `WHERE` clause.
- Known limitation: clearing cookies or switching devices creates a new character until real accounts arrive in P3 (passkeys or an email link, with account linking).

### 12.4 Transactions and failure matrix

Reward identity is `character_id + reward_definition_id + entitlement_cycle_id` (v4 §9), and a content edit never creates a new entitlement. Transaction order: check owner and revision → lock rows or update conditionally, in a fixed order → consume → grant → store the result and outbox entry → commit → notify. No network calls happen inside a transaction.

| Failure | Required outcome | Test |
|---|---|---|
| Crash before commit | Nothing granted; retrying the same `op_id` succeeds once | Failpoint `before_commit`, then restart |
| Crash after commit, before the reply | Lookup returns the committed result; no second grant | Failpoint `after_commit_before_notify` |
| Double tap or retry | One grant; the second request gets the stored result | Concurrent requests sharing one `op_id` |
| Same `op_id`, changed payload | Conflict error, no grant | Unit and integration |
| Two tabs or a stale epoch | Only the current owner can write | Two sockets on one cookie |
| Full bag | Refused before consumption; quest stays ready | Fixture |
| Database down | UI shows pending or unavailable; valuable writes stop; retries are bounded | Stop PostgreSQL mid-session |
| Content changed mid-operation | Resolved against the recorded version | Bundle swap test |
| Reconnect missed an event | Durable state and the operation result repair the UI | Drop the connection right after a commit |
| Restore | A fresh database restored from backup reconciles with the ledger | `pg_dump`, restore, reconcile script |

Counters stay finite, queues bounded, locks scoped, and metric labels low-cardinality.

## 13. P1a playtest protocol (V5-10)

### 13.1 Setup

- Record the build tag, content hash and serving mode, and show the reset policy in game.
- **Testers**: five people who have never seen the game, at least two of them on phones, mixing Ragnarok players and non-players. Add one four-player co-op session; it can include people who have played before.
- **Briefing**: say only "This is an early prototype. Play however you like, and think aloud if you're comfortable." Give no control briefing beyond what the game shows.
- **Observer**: note confusion with timestamps. Give no hints unless a tester is stuck for more than 3 minutes, and count each hint as coaching.

### 13.2 Telemetry

The server writes one JSON Lines file per session, with no personal data:
- **Progress**: join, first move, first attack, NPC interaction, quest accept, each windmark, each kill, claim.
- **Trouble**: first damage taken, deaths, rejected actions with reason, reconnects.
- **Engagement**: the "keep playing" choice, quit.

The client adds its performance summary (with preset and frame cap), correction distances, round-trip times, uncaught errors, and any lost WebGPU device or WebGL context.

### 13.3 Pass thresholds

| Signal | Threshold | Purpose |
|---|---|---|
| Finishes the route without coaching | ≥4 of 5 | Comprehension (v4, G2) |
| Can explain the Puddlekin telegraph and the counter | ≥4 of 5 | Contract |
| Keeps playing for 3 minutes or more when offered a chance to stop | ≥3 of 5 | Fun; restores v3's "voluntarily repeat" |
| "Would you play the next version?" on a 1–5 scale | Median ≥4 | Fun |
| Phone controls | Move, camera and skill at once; no accidental scroll or zoom | Touch usability |
| Route time | Median recorded against the 8–15-minute hypothesis | Pacing; never pad the route to hit it |
| Netcode | Correction p95 within V5-04 limits in real conditions; unfair hits under 5% | Feel |

### 13.4 Decisions after each round

- **Pass:** start P1b work (V5-12 to V5-14) and P2 planning.
- **Comprehension fails:** fix onboarding and markers, then retest with new testers. A person counts as "new" only once.
- **Fun fails:** change one or two levers (enemy behavior, skill feel and feedback, pacing, reward timing, camera) and retest.
- **Fun fails twice in a row:** hold a pivot review. Stop feature work and reconsider the combat model, camera or loop before any P2 content or art.

## 14. Visual, audio and asset plan

- **Before P1a**: block out the P1 field (entry and refuge, Sella, three windmarks along a readable route, the hunt clearing, an optional lookout and a regroup point). Lock the camera angle and compare it with the reference crop. Make sure telegraphs read in light, in shadow and under effects.
- **Placeholder baseline that can ship**:
  - Pick one CC0 family so the style stays consistent, for example Kenney (environment, UI, audio) with Quaternius or KayKit (rigged, animated characters and monsters).
  - Check each pack's license file and record provenance per asset, as in the [playbook](delivery-and-asset-playbook.md).
  - Add `@babylonjs/loaders`, pinned to the engine version, to load glTF.
- **After P1a passes**:
  1. An art bible: palette, materials, proportions, UI style, effects priority, and a glossary of original names.
  2. A hero trial: one rigged character, one enemy and a gate kit, with idle, run, attack, hit and death animations and a one-meter doorway.
  3. An environment kit: 8–12 building pieces, 10–15 props and a foliage atlas, with visuals and collision from one authored source.
  4. Lighting and effect profiles for the four graphics presets (D-10, §11.6).
- **Readability rule**: every telegraph has a shape, a timer and a sound, never color alone. Under load, cut shadows and foliage before hit signals.
- **Admission path (unchanged from v4)**: hand-made, procedural, CC0 or licensed source → editable master → GLB and collider → validator → device route. Record provenance, hashes, units, bounds, collision, textures, animation clips, LOD and a budget report. Never pull bulk data or assets from a game client.
- **How assets are made**: free tools and sources, steps for each asset type (characters and monsters, animation, kits and props, maps, items and icons, effects), AI use and export are in [playbook §5](delivery-and-asset-playbook.md#5-production-pipeline-by-asset-type).
- **Maps keep gameplay flat**: the protocol carries only x and z, so each zone has one walkable layer. Gentle hills can be visual if the client places characters on the rendered ground height, but bridges, overlapping floors and walkable cliffs wait until the server has height.
- **AI inputs are original**: own sketches or concepts only. Never Ragnarok Online's or any other game's images or names, and no "in the style of" prompts.
- **Zero spend**: no paid generation and no asset purchases; every asset type has a free route (playbook §5.1), and it's the default. Higgsfield credits count as spend, so each batch needs an owner decision (§20). Tripo, Meshy, Leonardo and Higgsfield stay optional and are never dependencies.

**Asset budgets** (seed values, tuned with the performance report before V5-08; frame budgets are in §11.3 and §11.6):

| Asset class | Triangles at LOD0 | Materials | Textures | Rig and extras |
|---|---:|---|---|---|
| Player character | 4,000–8,000 | 1–2 | 1024 px (512 on Low) | Shared humanoid skeleton, 50–70 bones, at most 4 influences per vertex |
| NPC | 3,000–6,000 | 1–2 | 512–1024 px | Same skeleton |
| Small monster (Puddlekin) | 1,000–3,000 | 1 | 512 px | Up to 30 bones |
| Mini-boss (P2) | 8,000–15,000 | 1–2 | 1024–2048 px | Own skeleton |
| Kit piece | 200–3,000 | Biome atlas | Shared 1024–2048 px atlas | Snaps to the grid; `COL_` collision proxies |
| Prop | 100–1,500 | Biome atlas | Atlas, or 512 px | Two cheaper LODs if seen from far |
| Weapon or headgear (P2) | 300–1,500 | Shared atlas | 256–512 px | Modeled on its socket |
| Item icon | — | — | 128 px in an atlas | One icon rig for every item |
| Animation set | — | — | — | Humanoid 11 clips, monster 9 (playbook §5.4); 30 fps, in place |
| Effect | — | Shared effects material | One 1024 px effects atlas | Up to 100 particles per burst at Medium, half on Low |

Scene totals at the Medium preset on the reference phones: at most 100 draw calls, 150,000 triangles on screen, 128 MB of compressed textures and 300 live particles. Desktop at High: 250 draw calls, 500,000 triangles and 2,000 live particles.

## 15. Testing and evidence

| Layer | Covers | When |
|---|---|---|
| Unit (Rust, TypeScript) | World rules, codecs, validators | Every change, via `verify` |
| Randomized decoder tests | Random and mutated packets never panic and stay bounded | Every change |
| Fuzzing | cargo-fuzz on the binary and cold decoders | Each protocol change; regenerate the seed corpus in the new protocol version first; at least 10 min per target on Linux or WSL (cargo-fuzz needs nightly Rust) |
| Integration | World thread, persistence worker, PostgreSQL (from V5-12) | Changes that touch them |
| Network smoke and bots | Seeded Node protocol bots with the delay/loss proxy | Each item; 10 bots for 10 minutes at V5-11 |
| Browser smoke | Playwright Chromium and WebKit, both renderers where available | UI and rendering changes |
| Real devices | Reference phones, via the performance report | V5-05, V5-08 tuning, V5-09, V5-14 |
| Human playtests | §13 | V5-10, V5-14 |
| Load | 50, 100 and more bots | P2–P3, after the prerequisites in §16 |

Each evidence file records:
- the item ID and date
- the source commit and content hash
- toolchain versions
- commands run and their results
- the workload seed and duration
- the hardware, network and device profile
- observed results
- limitations and unknowns

Evidence files share one schema with camelCase keys. Gates run by script against a committed, clean tree; the script writes the evidence file (commit, dirty flag, toolchain, content hash, seed). Each gate names its scenario (player behavior, frame cadence, network profile), not only thresholds. Before an item closes, a second agent reviews the change and tries to break the gate; findings are fixed or recorded as limitations.

v4's evidence rules still apply:
- A wall test keeps pushing after contact and checks every snapshot.
- A combat smoke decodes monster and event records and checks server HP, cooldown rejection and quest state after a reconnect.
- A count of passing tests is never evidence of fun or completeness.

## 16. Scale and operating cost

- **Ladder:** 2 clients → 4 humans → 10 bots (V5-11) → 50 and 100 bots → a measured zone cap (P3) → fleet steps of 2k, 5k and 10k (P5 and G7, only with demand, budget and workload evidence). The 10,000 CCU goal is spread across the fleet; it never means one battle.
- **Before 50 and 100 bots:** the world thread (V5-01), area of interest with enter/leave hysteresis (T08), protocol record caps raised to match, per-client instead of server-wide session limits, and bots running from more than one host.
- **Capacity arithmetic (v3 §11):** 10k peak CCU, 35% average, 50 kbit/s per player and 1.2 overhead give 600 Mbps at peak and 68.04 TB of real-time traffic per month. The illustrative fleet is 16 nodes.
- **Traffic cost:** it probably dominates, so once quotes are collected, compare providers that include transfer with ones that meter it. Prices stay empty in [capacity-assumptions.json](../planning/capacity-assumptions.json) until measured.
- **Hosting:** zero spend through P1b (local machine plus free tunnels). The first paid hosting decision (D-08) comes at P3, within v3's intended 2,000–3,000 THB per month, after a zone cap is measured.

## 17. Decisions

| ID | Decision | Default if undecided | Needed by |
|---|---|---|---|
| D-01 | Reference iPhone and Android models | None; blocks V5-05 | Before V5-05 |
| D-02 | Playtest mode: in-person LAN or remote tunnel | Remote tunnel, opened only during sessions | Before V5-05 |
| D-03 | Testers: five new people plus a group of four for co-op | Friends and Thai Ragnarok communities | Start now; needed at V5-10 |
| D-04 | P1b identity | Anonymous durable character tied to an HttpOnly cookie; accounts in P3 | Before V5-12 |
| D-05 | Cold-path encoding | JSON inside the envelope, with TypeScript types generated from Rust | At the start of V5-02 |
| D-06 | P1 display languages | Thai and English keys; default from the browser language | V5-03 |
| D-07 | CC0 art and audio family | Choose per §14 | Before the blockout |
| D-08 | First paid hosting | None until P3 | P3 |
| D-09 | Monetization | Undecided; the prototype never has paid randomness | A later product decision |
| D-10 | Graphics presets and frame rate | Low, Medium, High and Ultra, switched in game and saved locally; a 30/60 fps cap (§11.6) | V5-05 |
| D-11 | P1 orientation | Landscape only; portrait shows a rotate-device gate. Supersedes the portrait compatibility in §11.4 | V5-09 |
| D-12 | Native desktop builds (.exe, .dmg) | None; desktop players use the installable web app. Revisit with a stable public server, a signing budget and a need the browser can't meet, such as a Steam release (§11.5) | Not before D-08 |

Already decided:
- browser and mobile
- Ragnarok-style system depth with original IP
- free-first tooling
- PvE and co-op first
- Babylon.js and TypeScript client
- authoritative Rust server
- PostgreSQL for durable state
- WebGPU with WebGL2 fallback
- landscape only in P1, with a rotate-device gate in portrait (D-11)
- a Rust/WASM movement kernel only if measured drift justifies it
- no rewrite of the client in Rust

## 18. Schedule and forecast

Indicative only. Assumes one person working with full focus and keeps 30–40% of the time in reserve for integration, debugging and review. AI-assisted coding may shorten implementation, but not device tests, playtests or integration.

| Block | Items | Focused days | Calendar with reserve | Reviewable result |
|---|---|---:|---:|---|
| 1 | V5-00, V5-01 | 5–8 | 1.5–2.5 weeks | Repository, V4-03 evidence, world owner with per-player channels |
| 2 | V5-02, V5-03 | 8–11 | 2.5–3.5 weeks | Protocol v4 and content bundle, fuzzed; no hard-coded tuning |
| 3 | V5-04, V5-05, V5-11 | 9–13 | 3–4 weeks | Smooth movement under impairment; phones boot over HTTPS; 10-bot smoke |
| 4 | V5-06, V5-07 | 7–11 | 2–3.5 weeks | Real HUD; Sella's quest end to end |
| 5 | V5-08, V5-09 | 11–17 | 3.5–5 weeks | Telegraphed combat with feedback; party and touch controls |
| 6 | V5-10 | 3–6, plus tester time | 1–2 weeks | P1a gate decision |
| 7 | V5-12, V5-13, V5-14 | 14–22 | 4.5–7 weeks | P1b packet |

That puts P1a at about 13–20 weeks, and P1b at about 4–6.5 months of full-time solo work. Part-time work scales proportionally. The art track (blockout and CC0 kit choice) adds about 3–5 days across Blocks 3–5.

- **Reforecast after Block 2**, using actual dates. If Blocks 1–2 take more than 1.5× the estimate, cut P1a scope rather than evidence: drop Guard Stance, or use two windmarks instead of three.
- **Reforecast 2026-09-25.** V5-00 to V5-03 (Blocks 1–2, estimated at 13–19 focused days) were committed on the evening of 2026-09-24, and V5-04 followed the next day. Implementation is no longer the constraint; devices, testers and feel checks are. Dates now drive the schedule: record the Android model (D-01), book 2–3 people for the V5-08a feel check, start tester recruiting (D-03), and set the first tunnel session date.
- **v3's 12-week P2 candidate** assumed 2–3 engineers plus art and QA; it isn't a solo target.
- **Six-week content cycles** begin only after two cycles have shown the throughput is sustainable.

## 19. Risks

| # | Risk | Early signal | Mitigation or trigger |
|---|---|---|---|
| 1 | One person can't carry the scope | Blocks 1–2 take more than 1.5× the estimate | Cut P1a scope, keep the gates, reforecast |
| 2 | Combat isn't fun on touch | The V5-08 feel check falls flat; P1a fun thresholds missed | The §13 levers; a pivot review after two failures |
| 3 | Movement feels bad on phones | Correction p95 over the limits; unfair hits | V5-04 before tuning; bounded dodge rewind |
| 4 | iOS Safari limits: memory, backgrounding, no fullscreen | Tab reloads, stuck input, cramped landscape | V5-05 early; resolution cap; performance report; home-screen mode |
| 5 | Protocol churn | Frequent codec edits | Design the whole set in V5-02; JSON cold path |
| 6 | Duplicated or lost rewards | Failpoint tests fail | Database constraints (Appendix C); `op_id` idempotency |
| 7 | Art throughput | Blockout art still in place at P2 | CC0 baseline; hero trial after P1a |
| 8 | Documents drift and process eats build time | Documents disagree; more time goes to docs than code | One status table; evidence per item; research freeze |
| 9 | IP and licensing | RO names or assets creep in; GPL code gets copied | Originality rules; `references/rathena/` and `exports/` kept out of the repository; no client data; name review before any public URL |
| 10 | Losing work | No copy of the repository off this machine | V5-00 version control, plus a push to a private remote after each closed item |
| 11 | Abuse during an Internet playtest | Unknown traffic on a tunnel | V4-03 controls, per-client limits, tunnels open only during sessions, never the dev server |
| 12 | A gate passes the easy case | p95 exactly 0; a metric that equals a sampling constant | Scenario-based gates (§15); an adversarial review before an item closes |
| 13 | Long sessions degrade | Remote held frames rise after 20+ minutes | Two-way clock slew; a 60-minute simulated-time run in the gate |
| 14 | The Windows host stalls the room | Console QuickEdit, sleep or updates during a playtest | Non-blocking logs; run the server detached with logs to a file; set a power plan and pause updates for sessions |

## 20. Working agreements and change control

- Local implementation, tests and refactors within this plan's scope go ahead without extra approval.
- Spending money, opening any endpoint reachable from the Internet, publishing, and claiming that humans accepted a gate each need an explicit owner decision.
- Agent and tool operating rules live in [AGENTS.md](../AGENTS.md) and the [playbook](delivery-and-asset-playbook.md), not in this plan.
- Changing a gate needs a stated reason and a review of the gates it affects. A missed target is never fixed by weakening it.
- Evidence files are immutable; a new run gets a new file.
- Finishing this document doesn't mean the game is finished.

## Appendix A — P1 seed tuning

Starting values for the content bundle, to be tuned in playtests. Once V5-03 lands, the bundle is the source of truth.

**Trailblade** (player vocation): 100 HP, moves at 4.5 m/s.

| Ability | Input | Shape and range | Windup / active / recovery | Cooldown | Effect |
|---|---|---|---|---:|---|
| Basic attack | F or ATK | 90° cone, 3.0 m, 1 target | 100 / 60 / 200 ms | 400 ms | 25 damage |
| Quickstep (dodge) | Space or ↗ | Dash in the movement or facing direction | 280 ms invulnerable | 900 ms | 2.2× speed for 280 ms |
| Arc Slash | 1 | 120° cone, 4.0 m, up to 3 targets | 250 / 100 / 350 ms | 5 s | 45 damage to each |
| Guard Stance | 2 (hold) | Front 120° | Up to 1.5 s | 6 s | −70% frontal damage. A block in the first 300 ms is a perfect guard: for the next 1.0 s a basic attack does double damage and staggers |
| Trail Potion | Potion | Self | Instant | 10 s | +40 HP; carry 3 |

Today's code has Attack at 3.25 m for 28 damage every 360 ms. Its Arc Slash hits the single nearest target within 7 m for 60 damage. These seed values turn Arc Slash into the planned cleave.

**Puddlekin** (enemy): 90 HP, moves at 3.0 m/s, aggro radius 8 m, leash 16 m from home, respawns after 15 s.

| Behavior | Detail |
|---|---|
| Splash Hop | 900 ms windup: squash pose, a 2.5 m circle filling on the target's position, rising sound. Then 18 damage inside the circle. Then 700 ms of recovery: dazed and taking 50% more damage, which is the counter opening. 3 s cooldown |
| Idle and approach | Wanders within 4 m of home; closes to 2 m once aggroed |
| Stagger | A perfect-guard counter staggers it for 1.0 s |
| Rewards | 9 base EXP; one Dew Bead per eligible character |

**Death:** at 0 HP the player is down for 5 s, then respawns at the regroup point with half HP. There is no EXP loss in P1.

**Progression:** level 2 needs 100 base EXP. Three hunt kills (27 EXP) plus the quest reward (90 EXP and a Gale Seed, per the contract) reach level 2 by turn-in, which is the intended reward moment.

**Field:** zone `sunmeadow_verge`, starting at about 96 × 96 m; today's hard-coded 56 × 56 m limit moves into zone data. The route runs entry → Sella → windmark 1 → windmark 2 near the hunt clearing → windmark 3, with an optional lookout detour → back to Sella. Set final distances by real walking time and sightlines ([catalog §5](system-design-catalog.md)).

## Appendix B — Protocol v4 message catalog

This is design intent; `apps/protocol/binary-v4.md` becomes the source of truth in V5-02. All numbers are little-endian.

**Hot path (binary)**

| Type | Direction | Payload | Bytes |
|---|---|---|---:|
| `0x01` Join | Client → server | `ticket[32]` | 32 |
| `0x02` Input | Client → server | `epoch u32, seq u32, move_x i16, move_z i16, facing u16` | 14 |
| `0x03` Action | Client → server | `epoch u32, seq u32, ability u8, aim u16, target_id u32, view_tick u32` | 19 |
| `0x04` Ping | Client → server | `nonce u32, client_ms u32` | 8 |
| `0x81` Welcome | Server → client | `player_id u32, epoch u32, tick u64, x f32, z f32, zone_id u16, content_hash u64, tick_hz u8` | 35 |
| `0x82` Snapshot | Server → client | 24-byte v5 header (`tick u64, ack_seq u32, own_flags u8, ack_x f32, ack_z f32`, then three `u8` counts: players, monsters, events), then the records below | Variable, capped |
| `0x83` Error | Server → client | `code u16` | 2 |
| `0x84` ActionResult | Server → client | `seq u32, result u8, reason u8, cooldown_ms u16` | 8 |
| `0x85` Pong | Server → client | `nonce u32, client_ms u32, server_tick u64` | 16 |

Snapshot records:

| Record | Fields | Bytes |
|---|---|---:|
| Player | `id u32, x f32, z f32, facing u16, hp u16, max_hp u16, flags u8 (connected, down, dodging, guarding), anim u8` | 20 |
| Monster | `id u32, kind u8, x f32, z f32, facing u16, hp u16, max_hp u16, flags u8, state u8, ability u8, state_ticks_left u16` | 24 |
| Event | `id u64, source_kind u8, source_id u32, target_kind u8, target_id u32, ability u8, amount u16, flags u8 (defeated, blocked, perfect, dodged, heal), x f32, z f32` | 30 |

**Cold path (JSON tagged by `"t"`)**

| Direction | Messages |
|---|---|
| Client → server (`0x10`, ≤512 B) | `interact{npc}`, `choose{npc, token, choice}`, `claim{quest, op_id}`, `use_item{item, op_id}`, `party_create{}`, `party_join{code}`, `party_leave{}`, `resync{}` |
| Server → client (`0x90`, ≤4 KiB) | `character_state{rev, level, exp, hp, max_hp, bag, pouch}`, `quest_state{rev, quest, state, objectives, step_ticks}`, `dialogue{npc, token, text_key, choices}`, `dialogue_closed{npc, reason}`, `op_result{op_id, status, reason, cooldown_ms, grants}`, `party_state{rev, members, leader, code, expires_s}`, `notice{key, params}` |

## Appendix C — Persistence sketch

This is design intent for V5-12 and V5-13; the migrations become the source of truth. See [online-storage-architecture.md](online-storage-architecture.md) for the detailed Habitat-inspired storage gateway, caching tiers, and outbox CDC design.

| Table | Key columns and constraints |
|---|---|
| `principals` | `id uuid` primary key; `token_hash bytea` unique; `created_at`, `last_seen_at` |
| `characters` | `id uuid` primary key; `principal_id` foreign key, unique in P1; `name`, `vocation`; `level ≥ 1`; `base_exp ≥ 0`; `owner_epoch`; `revision` |
| `character_checkpoints` | `character_id` primary key; `zone_id, x, z, hp`; `revision`; `updated_at` |
| `bag_slots` | Primary key `(character_id, slot_index)`; `slot_index` 0–11; `item_def_id`; `count` 1–99 |
| `material_pouch` | Primary key `(character_id, item_def_id)`; `count ≥ 0` |
| `quest_progress` | Primary key `(character_id, quest_id)`; `state`; `objective_counts jsonb`; `revision` |
| `reward_claims` | Primary key `(character_id, entitlement_id, cycle_id)`; `op_id`; `content_revision` |
| `loot_origins` | Primary key `(character_id, encounter_id)` |
| `operation_results` | Primary key `(principal_id, op_kind, op_id)`; `payload_digest`; `result jsonb` |
| `item_ledger`, `exp_ledger` | Append-only: `character_id, delta, reason, source_key, created_at` |
| `outbox` | `id bigserial`; `character_id`; `kind`; `payload`; `delivered_at` |
| `content_versions` | `hash` primary key; `schema_version`; `loaded_at` |

Every write to character, inventory or quest rows checks the expected `owner_epoch` and `revision`. Zero affected rows means reload and reconcile, never overwrite. Equipment, as item instances with unique IDs, arrives in P2.
