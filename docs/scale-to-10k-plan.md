# Scaling to 10,000 concurrent players

Status: proposed, awaiting owner approval · Written 2026-09-29 · All numbers below are **derived estimates, not
benchmarks**, in the same sense as `tools/capacity_model.py`. Every one of them is replaced by a measurement at the
matching rung of the ladder in §8.

Companion to [mmo-master-plan-2027.md](mmo-master-plan-2027.md). The 10k target itself is inherited from
[browser_ragnarok_babylon_rust_10k_plan_v5.md](browser_ragnarok_babylon_rust_10k_plan_v5.md) §16, which already fixes
the rule that matters: **10,000 concurrent means a fleet, never one battle.**

## 1. Where the ceiling is today

| Limit | Value | Where |
|---|---|---|
| Rooms | 20, fixed at boot | `apps/server/src/main.rs` `ROOM_COUNT` |
| Players per room | 50 | `apps/server/src/world.rs` `MAX_PLAYERS` |
| Sockets per process | 1,000 | `apps/server/src/main.rs` `MAX_CONNECTIONS` |
| Live sessions per process | 256; new sessions capped at 20/minute | `apps/server/src/auth.rs` |
| Room command drain | 512 commands per 50 ms tick | `apps/server/src/room.rs` |
| Snapshot | full state, every tick, to every connection | `apps/server/src/wire.rs` |
| Snapshot caps | 50 players / 64 monsters / 64 events | `apps/server/src/wire.rs` |
| Interest management | none | no grid, no AOI |
| Transport | WebSocket only | `/ws` route |

These are **1,000 configured room/socket slots across twenty separate worlds of fifty**, with a tighter
256-session admission limit. The strongest recorded local load result is ten bots for ten minutes; configured
slots do not prove capacity. The existing target remains **500 concurrent players in one logical map**.
The 250-player rung is intermediate, and the 10k fleet design does not replace that target.

## 2. The arithmetic that decides everything

Snapshot cost per client per tick, using the current layout: 24 B payload prefix, 20 B per player,
32 B per monster, 30 B per event, plus a separate 6 B application envelope. The table omits events
and transport overhead; all throughput uses 20 Hz and decimal kbit/Mbit units.

| Configuration | Bytes/snapshot | Per client | Verdict |
|---|---|---|---|
| Today, 50-player room, 20 monsters | 1,664 payload + 6 envelope | 267.2 kbit/s | 50 clients = **13.36 Mbps per room** |
| 200-player room, 64 monsters, no AOI | 6,072 payload + 6 envelope | 972.48 kbit/s | Hypothetical: current player-count gate rejects it |
| 200-player room, AOI (40 players, 24 monsters visible) | 1,592 payload + 6 envelope | 255.68 kbit/s | Still over the proposed byte target |
| Delta + quantisation | Workload-dependent | To measure | Record entity churn, keyframes, acknowledgements and resyncs |
| Delta plus near/mid/far update rates | Workload-dependent | **≤30 kbit/s proposed target** | Unproven until a replayable movement/combat workload passes |

At an assumed 30 kbit/s per client: 10,000 concurrent = **300 Mbps payload egress peak**, or 360 Mbps
with an assumed 20% overhead. At 3,500 average clients for 30 days, that is **34.02 TB payload/month**,
or **40.824 TB with that overhead**. This is a conditional scenario inside the capacity model's
600 Mbps / 68.04 TB envelope, not a measured reduction. The current 50-player/20-monster table scaled
to 10,000 clients would use **2.672 Gbps of application traffic**, before transport overhead.

The order is therefore not negotiable: **AOI → delta + bitpacking → network LOD → more rooms.** Adding rooms first
just multiplies a per-client cost that is already wrong.

## 3. The 50-room sample, worked out

10,000 ÷ 50 = **200 players per room** in this optional fleet scenario. A fleet with 500-player worlds
would instead need twenty full worlds before reserve. Select the deployment mix after the single-world
500-player gate passes; room count alone does not qualify it. Requirements for the 200-player example:

| Concern | Requirement |
|---|---|
| Snapshot caps | visible-set cap per client (~48 players, 32 monsters), not a room cap; counts become u16 |
| Protocol | v6: varint entity ids, delta records, per-record change flags, quantized local-cell positions |
| Tick | 20 Hz; qualify distributed players and crowded combat independently |
| CPU per room | Measure simulation, AOI selection, per-client encoding and queue drains separately; no sub-millisecond estimate is accepted as capacity evidence |
| Memory per room | Measure entities, per-connection delta baselines, socket queues and allocator overhead at the target occupancy |
| Bandwidth per room | 200 × 30 kbit/s ≈ 6 Mbps |
| Sockets | `MAX_CONNECTIONS` from 1,000 to per-node capacity; raise file-descriptor limits; TLS terminated at the edge |

Fleet shape for 10,000, two honest readings:

- **Tight scenario**: 8 world nodes × 6–7 rooms × 200 = 9,600–11,200 configured slots. Six rooms per node are insufficient for 10k. Traffic is 36–42 Mbps payload/node at the 30 kbit/s assumption; CPU sizing remains unmeasured.
- **Conservative** (what the capacity model assumes today): 16 nodes including failure reserve.

Start from the conservative number and let measurement earn the tight one. A node loss must cost one node's players a
reconnect, never the fleet.

## 4. Rooms are channels, and 10k is a social problem

Fifty rooms of the same world is the channel model that this genre has used for twenty years, and it works — provided
the social layer is **global, not per room**:

- friends, guilds, parties, whispers, market and mail live outside the world process;
- a party joins a channel together, and "go to my friend's channel" is one click with a queue when it is full;
- town channels overflow automatically: channel 1 fills, channel 2 opens, and the player never chooses a number;
- instanced content (dungeons, the tower) spawns per party from a pool and does not consume world capacity.

Without that, 10,000 players is 50 lonely villages of 200.

## 5. Hotspots — the case AOI does not solve

AOI keeps a client from paying for a world it cannot see. It does nothing when 200 players stand in one plaza, which
is exactly what happens at an event or a boss. Three mechanisms, all needed:

1. **Visible-set cap with correctness priorities**: self, relevant combatants and telegraphs, party, then nearby
   social actors. If mandatory combat relevance exceeds the cap, use a documented crowd/admission policy;
   never silently hide an attacker that can damage the player. Enter/leave and event relevance must be tested.
2. **Crowd aggregation**: past the cap, send a count per cell so the client can render a crowd impression rather than
   nothing — density without entity cost.
3. **Client density preset**: the render tier caps drawn characters independently of what arrives; Low draws fewer.

Plus the ordinary tools: per-channel population caps with a queue, spawn spreading, and event instancing.

## 6. What must change in the server

- **Spatial grid + AOI** (32 m cells, 9-cell neighbourhood), one grid shared by simulation, visibility and networking.
- **Shared cell records plus personalized assembly**: cache immutable entity records once where useful;
  retain connection-specific acknowledgements, relevance priorities, delta baselines and packet limits.
  Measure shared work and per-client work separately before claiming encode savings.
- **Delta state per connection**: last-acknowledged tick, changed-entity set, full resync on gap.
- **Entity storage**: `HashMap<u32, Player>` and `Vec<Monster>` become dense arrays with generational ids, so the
  snapshot pass is a linear scan of contiguous memory.
- **Room lifecycle**: rooms created and retired on demand instead of 20 fixed at boot, with a registry the gateway
  reads.
- **Gateway**: session tickets, room assignment, capacity reporting, channel switch, graceful drain for deploys.
- **Backpressure everywhere**: the existing overload guard extends to per-node admission, and a full fleet answers
  "queue", not "error".

## 7. What must change around the server

- **Stateless services split out**: auth, presence, chat fanout, market, mail, social graph. Chat to 10,000 is a
  fanout problem for Valkey pub/sub with per-channel rate limits, not something a world process should do.
- **Database**: per-node connection pools, batched writes through the existing storage worker, outbox for anything
  asynchronous, and read replicas only if measurement demands them.
- **Deploys**: rolling, drain a room to a sibling channel, players reconnect into the same world position.
- **Observability before scale**: tick p99, snapshot bytes per second per node, AOI set sizes, queue depths, socket
  churn, and cost per 1,000 CCU on one dashboard. Scaling without this is guessing with money.

## 8. The ladder

Each rung is 3 × 10-minute runs, even spread and one deliberate hotspot, then the next rung. A rung that misses its
gate is fixed before the next one starts — never averaged away.

| Rung | Players | Shape | Gate |
|---|---|---|---|
| L0 | 50 → 100 | 1 room | Protocol, admission, AOI entry/leave and overload gates pass before higher loads |
| L1 | 250 | 1 room | tick p99 ≤40 ms, <0.1% missed ticks, ≤35 kbit/s per client |
| L2 | 500 | 1 room + hotspot of 200 in one plaza | same, plus visible-set cap proven |
| L3 | 1,000 | 5 rooms, 1 node | node CPU <60%, egress measured |
| L4 | 2,500 | 13 rooms with 200-player capacity, 2 nodes | channel switch and party-follow work under load |
| L5 | 5,000 | 25 rooms, 4 nodes | node loss drill: one node killed, players back in ≤30 s |
| L6 | 10,000 | 50 rooms, 8–16 nodes | 6-hour soak, cost per 1,000 CCU recorded |

Bots for L4 and above cost real machines to generate; budget the load generator as part of the rung, and reuse
`tools/swarm-smoke.mjs` and `tools/netcode-bot.mjs` rather than writing a new harness.

## 9. Transport

WebSocket stays the baseline; it is what works everywhere today and the current protocol assumes it. WebTransport
(datagrams for movement, streams for everything else) removes head-of-line blocking and is worth a measured
experiment at L3 — but only as an additive path with WebSocket fallback, and only after delta encoding exists, since
delta is the bigger win and WebTransport changes reliability semantics for it.

## 10. Cost discipline

Hosting stays 0 THB until P3. From there, the number that matters is **cost per 1,000 CCU per month**, recorded at
every rung. Egress dominates: halving bytes per client halves the fleet bill, which is why §2's ordering is also the
cheapest path. A 10k launch that costs more per player than the game earns is a failure with a nice graph.

## 11. Decisions needed

| ID | Question | Blocks |
|---|---|---|
| D-28 | Room size: 200 (50 rooms) or 500 (20 rooms) at 10k | §3, protocol caps, node sizing |
| D-29 | Protocol v6 now, or extend v5 in place | §6, client and golden fixtures |
| D-30 | Channels of one world, or several distinct worlds with separate economies | §4, social layer, market design |
| D-31 | Hosting shape at P3: fixed nodes or autoscaling | §3, cost model |
| D-32 | Whether 10k is a 2027 goal at all, or 2,500 proven and 10k designed for | the whole ladder |

The proposed calendar forecast is 2,500 qualified during 2027 with 10,000 retained on the roadmap.
That forecast does not reduce the user's full objective or prove that later rungs need no architecture changes.
Replace dates and fleet estimates with measured results as each rung passes.
