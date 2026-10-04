# Aetherfield — 12-Month MMO Program (2026-10 → 2027-09)

Status: proposed delivery forecast · Written 2026-09-29 · Reconciled 2026-09-30 · Horizon 12 months

This is the **program layer** above [browser_ragnarok_babylon_rust_10k_plan_v5.md](browser_ragnarok_babylon_rust_10k_plan_v5.md).
v5 stays the engineering gate ledger (P-phases, V5 items, evidence rules); this document says **what ships each
quarter, in what order, and what number closes it**. Where the two disagree, v5's evidence rules win and this
document is edited.

This program expands the existing AOI, art, device and operations work packages into measurable milestones.
It supplements the engineering ledger; the dates are estimates. The full objective remains comprehensive
Ragnarok-referenced system-family coverage with original expression, selected Genshin exploration/party and
GTA activity/co-op ideas, and **500 players in one logical map**. Later system families remain on the roadmap.

---

## 1. Ground truth rechecked on 2026-09-30

Read from code, not from plans.

| Area | What exists | What is missing |
|---|---|---|
| Server | 20 rooms x 50 players, 20 Hz tick, `MissedTickBehavior::Skip`, overload guard, PostgreSQL worker + outbox, fuzz targets | **No AOI, no spatial grid**, AoS `HashMap` entities, linear collider scan, full snapshot to every connection |
| Protocol | binary v5, 6-byte envelope, fixed layout, caps 50 players / 64 monsters / 64 events, cold path tagged JSON | No delta, no spatial AOI; room cap and per-client visible cap must become separate contracts |
| Client | Babylon 9.27.1, WebGPU with WebGL2 fallback, context-loss recovery, KTX2 + meshopt decoders, manual HLOD swap, gate-triggered cell loading | No thin instances, no `addLODLevel`, no mesh freezing, no device tier, no asset cache, hand-rolled DOM UI |
| Netcode | 50 ms step, prediction/reconcile and adaptive interpolation; motion fixes and local impairment evidence are recorded | Recheck historical findings against [the live backlog](execution-backlog.md#live-status); phone and human acceptance remain open |
| World | 1,024 x 1,024 m design, server clamp ±308 m, two flat 64 m cells with shared-source props and 26 colliders | Most regions unbuilt; no heightfield/navmesh or complete perimeter; a flat route smoke does not qualify the world |
| Art | glTF-Transform → KTX2 → meshopt pipeline, per-asset build gates (cell ≤40k tris / ≤2 MiB, HLOD ≤25k tris / ≤4 MiB) | City runtime is 892,347 tris / 67.7 MB against a 12 MB first-download budget |
| Systems | Quests, inventory, equipment, refine, economy preview, party, rooms, tower, friends/groups, dual EXP and decorative follower preview | Additional vocations, boss/guild/PvP and combat pet/mount families remain phased |
| Process | Local build, client tests, Rust tests and plan/layout verifiers | Dirty worktree, no configured remote/CI found; reproducible release and device qualification remain open |

Nothing in this repository has ever been measured on a phone: no FPS capture, no GPU memory, no texture residency.
Every mobile number in every plan is an assumption.

## 2. What "AAA" means here, honestly

One developer, 0 THB of paid services until P3, no native builds. AAA **scope** is not reachable in 12 months and
pretending otherwise produces a dead project. What is reachable is an **AAA quality bar on a narrow slice**:

- one city and three regions that look composed, not generated;
- one vocation whose combat has weight, telegraphs and readable feedback;
- 60 fps desktop / 30 fps mid phone, held, with numbers captured on real devices;
- a UI that a stranger can use without being told anything;
- a world qualified for **500 players together**, with 250 as an intermediate load rung.

Depth (more vocations, guilds, sieges, pets) is **content added on top of a proven slice**, quarter by quarter, not
promised up front. Ragnarok is the reference for progression and social shape, Genshin for landmark composition and
readability at distance. The full system-family coverage register remains the scope authority; this calendar
does not delete systems that are scheduled after the initial playable slice.

## 3. Inherited constraints (do not renegotiate silently)

From v5 §17 and the backlog decisions: Babylon + TypeScript client, authoritative Rust server, PostgreSQL, WebGPU with
WebGL2 fallback, 20 Hz simulation, binary v5 hot path with tagged-JSON cold path, `op_id` idempotency,
`owner_epoch` + `revision` fencing, Thai + English, landscape-only on phones, native builds deferred per D-12, free-first hosting before P3,
no gacha or paid random boxes, no paid XP or drop boosts, no FOMO streaks, no live LLM in the simulation, and no
Ragnarok Online names, maps, art or client data anywhere in the project.

The user has separately authorized a bounded Tripo prototype using existing account credits. That exception
does not authorize recurring purchases; the current public prototype is export-locked and not in the runtime.

## 4. Five tracks

| Track | Owns | Ships against |
|---|---|---|
| **T-NET** Engine and netcode | tick, AOI, protocol, prediction, capacity | v5 gates, bot swarms |
| **T-WORLD** World and art production | Blender masters, cells, HLOD, collision, navmesh, streaming | [city-art-roadmap.md](city-art-roadmap.md), [world-expansion-500.md](world-expansion-500.md) |
| **T-GAME** Systems and content | vocations, skills, monsters, quests, economy, tower, social | [system-design-catalog.md](system-design-catalog.md) |
| **T-UX** Interface and feel | HUD, input, readability, accessibility, onboarding | [p1-gameplay-contract.md](p1-gameplay-contract.md) |
| **T-OPS** Platform and business | accounts, anti-cheat, telemetry, CI, hosting, support, monetization | new, §8 |

One track is "primary" each month; the others take maintenance only. Parallel tracks are how solo projects stall.

## 5. Quarter plan

Each milestone closes on a **number measured on a committed clean tree**, with a receipt in `planning/evidence/`.
"Feel" milestones close on a human session, recorded, not on a passing test.

### Q1 (Oct–Dec 2026) — Make the ground solid

Primary: T-NET, then T-WORLD.

| ID | Milestone | Exit gate |
|---|---|---|
| **M1.1** | Repository hygiene | git remote configured; working tree committed; `verify.ps1` passes on a fresh clone; CI runs `verify` on every push |
| **M1.2** | Close the deep-review findings R1–R7, R21, R22 | each finding has a failing test first, then a fix; dodge acceptance ≥99% at cooldown edges; a 500 ms uplink stall recovers without disconnect |
| **M1.3** | **AOI + interest management** | 32 m server cells; a client receives only its 9-cell neighbourhood; snapshot size independent of world population; 250 players in one world, tick p99 ≤40 ms, <0.1% missed deadlines |
| **M1.4** | Snapshot delta + quantisation | Downlink ≤30 kbit/s proposed target at 50 visible players on a defined movement/combat workload; current 50-player-only payload is 163.84 kbit/s at 20 Hz before envelope, monsters and events. Include keyframes/resync costs and new golden fixtures |
| **M1.5** | Device tier + measurement harness | tiers Low/Medium/High chosen at boot from a 2-second probe; a script captures fps p50/p95, draw calls, GPU memory and texture residency on one Android and one desktop; first real numbers recorded |
| **M1.6** | Map production standard v1 | §6 adopted; one 64 m cell authored end-to-end in Blender under budget, with collision and a `layout.json` entry |

Q1 does **not** add gameplay systems. If M1.3 slips, everything after it slips — it is the single highest-value item
in the year because it unblocks both player count and phone performance.

### Q2 (Jan–Mar 2027) — Make one place worth being in

Primary: T-WORLD, then T-UX.

| ID | Milestone | Exit gate |
|---|---|---|
| **M2.1** | Aetherhold city final | silhouette review passes at gameplay camera distance; High ≤900k tris / ≤180 draws / ≤160 MB textures, Medium ≤350k / ≤110 / ≤110 MB, Low ≤150k / ≤80 / ≤64 MB |
| **M2.2** | Renderer work: thin instances, LOD levels, mesh freezing, material atlasing | draw calls −50% on the city scene at equal visual result; documented before/after capture |
| **M2.3** | Three regions around the city (meadow, ridge, wetland) | 1,024 x 1,024 m walkable; visual cue every 100–150 m; server clamp raised only after land, collision, navmesh and perimeter cover every walkable cell |
| **M2.4** | Streaming and budget compliance | first-play download ≤12 MB to spawn-ready; remaining world streamed; no hitch >100 ms crossing a cell boundary on Medium |
| **M2.5** | UI pass 1 | HUD, inventory, quest log, map, chat rebuilt to one visual system; ≥44 px targets; safe areas; keyboard and touch both complete; reach-tested at 844x390 and 640x320 on a real phone |
| **M2.6** | Combat feel | telegraph ≥800 ms, unfair hits <5%, hit/dodge/damage feedback in three channels (visual, audio, motion); a human session says it feels responsive at 150 ms RTT |

### Q3 (Apr–Jun 2027) — Make it a game

Primary: T-GAME.

| ID | Milestone | Exit gate |
|---|---|---|
| **M3.1** | Three vocations + skill graph | each has 6 skills, a resource rule and a defining verb; a level-20 character can be built two ways that both work |
| **M3.2** | Monster ecology and one MVP boss | 12 monster families with roles; boss has phases, adds and a telegraphed wipe mechanic; kill takes 6–10 minutes for a prepared party of four |
| **M3.3** | Progression loop to level 40 | base/job EXP curve; gear tiers with refine risk; a 10-hour path with no dead hour, walked end to end by a human |
| **M3.4** | Economy and trade | NPC shop, player-to-player escrow, gold sinks, published loot odds; a closed test with 20 players shows no runaway inflation over a week |
| **M3.5** | Party and guild layer | party finder, guild create/join/rank/storage, shared quest credit |
| **M3.6** | Content tooling | quest/dialogue/spawn editing without hand-writing JSON; a designer edit reaches a running server in under a minute |

### Q4 (Jul–Sep 2027) — Make it survivable

Primary: T-OPS, then T-GAME.

| ID | Milestone | Exit gate |
|---|---|---|
| **M4.1** | Accounts | email-link or passkey sign-in, character binding, recovery, ban path, session revocation; no password storage |
| **M4.2** | Anti-cheat baseline | server authority audit (every client-supplied value re-derived), rate anomaly detection, speed/teleport/reach checks, ledger replay for gold and items, a written threat model |
| **M4.3** | Telemetry and alerting | metrics backend, crash reporting, four dashboards (tick health, wire bytes, client fps by tier, funnel), alert on tick p99 and error rate |
| **M4.4** | Live-ops tooling | GM console (inspect, teleport, grant, mute, rollback), event scheduler, content patch without full redeploy, moderation queue |
| **M4.5** | Scale ladder to 500 | 50 → 100 → 250 → 500 in one world, 3 x 10-minute runs even and hotspot, then a 6-hour soak; tick p99 ≤40 ms throughout |
| **M4.6** | Closed beta | 50 invited players, 2 weeks, retention and crash numbers captured; hosting cost measured against the 2–3k THB/month assumption |

Beyond the 12 months (do not start early): PvP and siege, pets and mounts, housing, seasonal events, monetization
build-out, native wrappers, second region cluster, 2,000+ CCU work.

## 6. Map production line (start here — it is what you are doing now)

The pipeline is already decided in [delivery-and-asset-playbook.md](delivery-and-asset-playbook.md); what follows is
the **map-specific contract** that turns a Blender file into a streamable cell.

**Authoring**
- Blender master per 64 m cell, 1 unit = 1 m, Z-up, origin at the cell's south-west corner, no scene-level transform.
- Name `cell_<sector>_<col>_<row>` for terrain, `prop_*`, `env_*`, `plant_*`, `rock_*` for kit pieces.
- Kit-first: author reusable pieces, place instances. A cell that contains unique geometry other than terrain and
  landmarks is a cell that cannot be instanced later.
- Solid blockers are authored alongside placements. Keep one source for their collision primitives and visual transforms; terrain height comes from the sector height source. A `COL_` bake may be an output, but must not drift from that source.
- Every placement of a kit piece is written to `layout.json` (id, position, rotation, uniform scale, variant) so the
  runtime can instance it and the server can read blockers from the same source.

**Export and bake**
- GLB export Y-up, `+Y up`, apply modifiers, no cameras or lights, one material per kit piece.
- glTF-Transform order: `dedup` → `prune` → `weld` → `resize` → KTX2 (ETC1S colour, UASTC normal/ORM) → `meshopt`
  **last** → `validate`. Meshopt last or `EXT_meshopt_compression` is stripped.
- Texel density ≈256 px/m for environment, 512 for characters; trim sheets and atlases over unique texture space.

**Budgets (build fails, not a review comment)**
| Unit | Triangles | File | Materials |
|---|---|---|---|
| 64 m detail cell | ≤40,000 | ≤2 MiB | ≤6 |
| 256 m macro HLOD | ≤25,000 | ≤4 MiB | ≤8 |
| 512 m proxy ring | ≤8,000 | ≤1.5 MiB | ≤2 |
| Kit piece | 200–3,000 | ≤160 KiB | 1 |
| Landmark | ≤15,000 | ≤3 MiB | ≤4 |

**Acceptance per cell**: opens in the validator with zero errors; meets the budget table; collision mesh present and
walkable end to end; silhouette readable at 60 m; no hitch >100 ms on load at Medium tier; `layout.json` round-trips
through the server's blocker import.

**Three-ring streaming**: 512 m proxy ring (always resident) / 256 m macro HLOD / 64 m detail cells (9-cell
neighbourhood). Art cells and the 32 m server AOI cells stay independent — never tie one to the other.

## 7. Performance program

Budgets by tier, enforced by the measurement harness from M1.5, not by opinion:

| | Low phone | Medium phone | High phone | Desktop High |
|---|---|---|---|---|
| Frame p95 | 33.3 ms | 33.3 ms | 16.7 ms | 16.7 ms |
| Draw calls | 80 | 110 | 180 | 250 |
| Visible triangles | 150k | 350k | 900k | 1.5M |
| Texture memory | 64 MB | 110 MB | 160 MB | 400 MB |
| Process memory | 350 MB | 350 MB | 500 MB | — |
| First-play download | 12 MB | 12 MB | 12 MB | 12 MB |

Ordered work (highest return first, from what the code lacks today): AOI → snapshot delta → thin instances → LOD
levels and mesh freezing → texture streaming and atlasing → simulation LOD (monster AI at 10/3/1 Hz by distance) →
network LOD (update rate by distance) → worker offload for decode. A Rust/WASM client kernel stays off the table
until a profile shows JavaScript is the bottleneck — v5 already decided this and nothing has changed.

## 8. Platform, operations and business (new track)

Session/OAuth and durable storage foundations already exist. Remaining public-test work includes recovery,
anti-cheat qualification, telemetry/alerting, crash reporting, GM tooling, moderation, support, scheduled
backup/restore rehearsals, legal pages and a monetization decision (D-09 is still
undecided — cosmetics-only is the assumption consistent with the exclusions in §3, but it needs a written answer
before Q4 starts). Hosting stays 0 THB until P3 per D-08; the Q4 beta is the first paid month.

## 9. Fix these before the plan starts (week 1)

1. **No configured remote and a large dirty worktree.** Local evidence is not clean-clone/release evidence.
   Preserve all ongoing changes, prepare a reviewed snapshot, configure publishing with the owner, then run
   `verify.ps1` from a fresh checkout. Do not delete unrelated work to obtain a clean status.
2. **[plan.md](online-storage-architecture.md) still says "DO NOT EXECUTE" / Stage 0 in-memory** while PostgreSQL shipped in V5-12/V5-13. Delete it or
   mark it superseded by [online-storage-architecture.md](online-storage-architecture.md), which carries the same stale stamp.
3. **v5 §3 baseline is wrong** (says no version control, 16 players, ±28 m bounds, no persistence). Re-baseline §3.
4. **D-13, D-15, D-16 exist only in the backlog**, and D-14 is used twice — login, rooms, tower, economy and social are
   unrecorded scope. Renumber and record them in v5 §17.
5. **Budget contradiction**: 12 MB first download vs a 67.74 MB city ([city-entry-r5-task.md](../planning/city-entry-r5-task.md)).
   Either the budget is staged (12 MB to spawn-ready, rest streamed — recommended) or the city is cut. Write the answer down.
6. **Ordering violation**: V5-05 (phone reach) is unstarted while combat, rooms, economy, social and equipment shipped.
   Either finish V5-05 or record that the order changed and why.
7. **Portrait leftovers** in v5 §11.4 and [p1-gameplay-contract.md](p1-gameplay-contract.md) contradict D-11 landscape-only.
8. Keep [binary-v5.md](../apps/protocol/binary-v5.md) and the Rust/client golden corpus aligned. The stale 16-player
   prose was corrected to 50 on 2026-09-30; a later protocol revision still needs its own compatibility gate.

## 10. Decisions needed from the owner

| ID | Question | Blocks |
|---|---|---|
| D-17 | Reference Android device to qualify against (D-01 unanswered since P0) | M1.5, every phone number |
| D-18 | Staged download (12 MB + streaming) or a smaller city | M2.1, M2.4 |
| D-19 | Monetization shape — cosmetics-only, or nothing before launch | Q4, legal pages |
| D-20 | 500 concurrent players in one logical map; 250 is an intermediate qualification rung, not a substitute | User request preserved; M1.3, M4.5 |
| D-21 | Name clearance for "Aetherfield" / "Aetherhold" | any public test |
| D-22 | Second pair of hands (art or tools) or strictly solo | Q2 and Q3 scope |

## 11. Cadence

Weekly: one primary track, a `verify.ps1` run on a clean tree, one evidence receipt, one written note of what moved.
Monthly: re-forecast the quarter, close or re-scope anything that slipped twice. Quarterly: a human play session of
at least an hour, recorded, with the verdict written before any new work starts.

A gate that is missed is never weakened — the milestone moves. That rule is inherited from v5 §20 and is the only
reason the evidence in this repository means anything.
