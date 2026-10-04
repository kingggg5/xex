# Plan: Adapting OpenAI Habitat Architecture to Browser MMORPG Online Storage

> **Status:** Draft / Planned — **DO NOT EXECUTE IMPLEMENTATION YET** (Awaiting review and approval).  
> **Target System:** Browser Action MMORPG (`apps/server` Rust backend + Babylon.js client, scaling towards 10k CCU).  
> **Reference Architecture:** OpenAI Habitat (Online Storage Platform for ChatGPT/Codex) & [browser_ragnarok_babylon_rust_10k_plan_v5.md](browser_ragnarok_babylon_rust_10k_plan_v5.md) (V5-12, V5-13, Appendix C).  
> **Licensing & Cost:** 100% Free and Open-Source Software (FOSS — PostgreSQL License & BSD 3-Clause; $0 software license fees, conforming to the 0 THB rule in [delivery-and-asset-playbook.md](delivery-and-asset-playbook.md)).

---

## 1. Executive Summary & Objective

OpenAI's **Habitat** serves 1+ billion users and 70M+ req/sec using a centralized storage abstraction layer, constrained query interfaces, Valkey caching, CDC-driven analytics, and a high-performance Rust core.

While our MMORPG does not require hyperscale multi-region routing, the core problems in game persistence are identical:
1. **Tick Time Invariance:** The 20 Hz / 50 ms game simulation tick must never block on database latency or connection locks.
2. **Exploit & Duplication Resistance:** Currency, loot, and reward transactions must be strictly transactional and idempotent.
3. **Clear Boundary (Decoupling):** Game logic should not know or care whether data lives in PostgreSQL, Valkey, or an append-only ledger.
4. **Separation of OLTP and OLAP:** Real-time gameplay writes must be completely decoupled from telemetry, anti-cheat log audits, and rankings.

This plan details how to adapt Habitat's architectural patterns into the upcoming **V5-12 (Identity)** and **V5-13 (Persistence Worker & Ledger)** phases of the game server.

---

## 2. Database Selection & Architecture Verification (Codebase Audit)

A rigorous audit of the existing codebase (`apps/server/`), traffic model ([capacity-assumptions.json](../planning/capacity-assumptions.json)), and specifications ([browser_ragnarok_babylon_rust_10k_plan_v5.md](browser_ragnarok_babylon_rust_10k_plan_v5.md)) confirms that **PostgreSQL 16+ (Durable Core) + Valkey (In-Memory Cache & Session Lock)** is the verified optimal database architecture.

### 2.1 Audit Findings Against Existing Source Code

| Module / Artifact | Current Code Structure & Requirement | Database Architecture Match |
| :--- | :--- | :--- |
| **[`cold.rs`](../apps/server/src/cold.rs)** | `ClaimMsg` & `UseItemMsg` enforce UUID `op_id` (`valid_op_id`). `BagEntry`, `GrantEntry`, `CharacterStateMsg` have discrete slots and counts. | **PostgreSQL:** Primary key `(principal_id, op_kind, op_id)` guarantees atomic deduplication (`ON CONFLICT DO NOTHING`) to eliminate item duplication exploits. |
| **[`room.rs`](../apps/server/src/room.rs)** | Simulation `World` runs on a dedicated OS thread. Sockets talk via bounded MPSC (`INBOX_BOUND = 1024`, `RELIABLE_BOUND = 64`) with non-blocking `try_send`. | **PostgreSQL Worker:** Async Tokio pool (`sqlx` or `tokio-postgres`) runs in background; 1–5 ms DB query time never blocks the 50 ms (20 Hz) simulation tick. |
| **[`auth.rs`](../apps/server/src/auth.rs)** | In-memory `HashMap` with `const MAX_SESSIONS: usize = 256;` and bounded ticket rings for single node. | **Valkey:** Provides distributed ticket store & session mutex (`principal_id -> active_room`) when scaling to multiple world nodes. |
| **[`capacity-assumptions.json`](../planning/capacity-assumptions.json)** | Peak CCU: `10,000`. Hypothetical node capacity: `1,000 CCU` (requiring ~10 nodes). | **Throughput Sizing:** 20 Hz movement is simulated in RAM. DB only receives checkpoints (every 30-60s) + reward claims. Peak write load is **~500–1,500 TPS**. A single PostgreSQL instance handles **15,000–40,000 TPS**, operating at only ~5–10% capacity. |
| **Appendix C Schema** | Relational schema: `principals`, `characters`, `bag_slots`, `reward_claims`, `item_ledger`, `outbox`. | **PostgreSQL:** Native support for composite PKs, foreign keys, row versioning (`owner_epoch`, `revision`), and transactional outbox. |

### 2.2 Comparison with Alternative Databases

* **Azure Cosmos DB / AWS DynamoDB (OpenAI Habitat choice):**
  * *Verdict:* **Not Recommended for our scale.**
  * *Reason:* Pay-per-request pricing (RU/RCU) becomes expensive quickly, violating the 0 THB rule. Cross-table multi-item atomic transactions (such as trading items between characters) are complex and slower across public cloud APIs compared to local/private network PostgreSQL.
* **ScyllaDB / Apache Cassandra:**
  * *Verdict:* **Not Recommended.**
  * *Reason:* Designed for eventual consistency and millions of independent writes. Implementing multi-row ACID transactions and strict inventory slot constraints requires Paxos Lightweight Transactions (LWT), which are fragile and add unnecessary latency.
* **SQLite (WAL mode):**
  * *Verdict:* **Good for local dev only; unsuitable for 10k CCU.**
  * *Reason:* SQLite uses a single-writer lock. Concurrent write transactions from multiple connections under 10k CCU create lock contention, and SQLite cannot be shared across multiple zone server nodes.
* **PostgreSQL 16+ (Winner):**
  * *Verdict:* **Optimal Choice.** 100% Free Open-Source, bulletproof ACID transactions, rock-solid compile-time Rust driver (`sqlx`), native logical replication (WAL) for CDC, and handles 10x our projected peak volume.

---

## 3. Core Architectural Pillars Adapted from Habitat

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             GAME CLIENTS (Babylon.js)                            │
│                 Browser WebGPU/WebGL2 - Binary Messages (v5)                     │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ WebSocket (ws / wss)
┌────────────────────────────────────────▼─────────────────────────────────────────┐
│                             ZONE RUNTIME (apps/server)                           │
│  ┌───────────────────────────────────┐    ┌───────────────────────────────────┐  │
│  │     Dedicated Zone Sim Thread     │    │       Tokio Async Gateway         │  │
│  │    (20 Hz Tick, Lockless/Pinned)  │    │  (WS Frames, Rate Limit, Auth)    │  │
│  └─────────────────┬─────────────────┘    └─────────────────┬─────────────────┘  │
│                    │                                        │                    │
│                    │ Bounded MPSC Channels                  │ Internal Tickets   │
│                    ▼                                        ▼                    │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │                    HABITAT-INSPIRED STORAGE GATEWAY                        │  │
│  │  - Constrained Storage Trait (CRUD by Key/Revision, No Arbitrary SQL)      │  │
│  │  - In-Memory / Valkey Cache (Tickets, Sessions, Hot Checkpoints)           │  │
│  │  - Optimistic Concurrency Engine (owner_epoch, revision check)             │  │
│  │  - Transactional Outbox & Idempotent Claim Engine (UUIDv7)                 │  │
│  └──────────────────────┬───────────────────────────────────┬─────────────────┘  │
└─────────────────────────┼───────────────────────────────────┼────────────────────┘
                          │ Async Batch Write / Commit        │ CDC Log Stream
                          ▼                                   ▼
        ┌───────────────────────────────────┐   ┌───────────────────────────┐
        │       DURABLE STORAGE (OLTP)      │   │    CDC & TELEMETRY (OLAP) │
        │        PostgreSQL Relational      │   │   - Anti-cheat Audit Log  │
        │  (Principals, Characters, Bag,    │   │   - Market / Drop Metrics │
        │   Ledgers, Idempotent Operations) │   │   - Global Leaderboards   │
        └───────────────────────────────────┘   └───────────────────────────┘
```

### Pillar A: Storage Abstraction Layer (Decoupled Game Engine)
* **Habitat Pattern:** Centralized data access layer hiding underlying storage engines from consumer services.
* **Game Adaptation:**
  * Define a clean Rust trait (`GameStorageGateway`) in `apps/server/src/storage/`.
  * The Zone simulation thread interacts exclusively via bounded, non-blocking MPSC message passing:
    * Zone sends: `StorageCommand::SaveCheckpoint(...)`, `StorageCommand::CommitClaim(...)`.
    * Persistence worker processes asynchronously and responds via `StorageReply`.
  * The game loop never acquires database pool connections or builds raw queries.

### Pillar B: Constrained API (Predictable Latency & Zero Table Scans)
* **Habitat Pattern:** Forbids arbitrary joins and table scans; exposes strictly partition-based key-value and range operations.
* **Game Adaptation:**
  * Enforce strict, single-character partition boundaries. All online queries must resolve by `(principal_id)` or `(character_id, slot_index)`.
  * Forbid cross-entity relational queries within the online tick path.
  * Every transactional mutation requires `(expected_owner_epoch, expected_revision)`. If rows updated = 0, trigger conflict resolution without blocking.

### Pillar C: Caching & Ephemeral State with Valkey (Redis Alternative)
* **Habitat Pattern:** Uses Valkey as the distributed cache layer for hot reads and session governance.
* **Game Adaptation:**
  * **Level 1 (In-Memory Tick State):** Active zone entities remain in dedicated Rust memory structures during active play.
  * **Level 2 (Valkey / Redis Cache):**
    * One-time WebSocket handshake tickets (TTL: 10s).
    * Session lease and active connection mutex (`principal_id -> active_room_id`).
    * Real-time leaderboards using Valkey Sorted Sets (`ZADD`, `ZREVRANGE`).
  * **Level 3 (Cold Durable Store):** PostgreSQL for durable items, bag slots, and currency.

### Pillar D: CDC (Change Data Capture) & Outbox Pattern
* **Habitat Pattern:** Streams storage changes through CDC to Kafka, Rockset, and Databricks for analytics and real-time search without degrading OLTP.
* **Game Adaptation:**
  * Game server writes critical changes to `operation_results`, `item_ledger`, and `outbox` in the same local DB transaction.
  * A background tailing worker (or PostgreSQL Logical Replication / WAL listener) picks up events from `outbox` and delivers them to:
    * Drop rate telemetry & economic inflation monitoring.
    * Leaderboard indices and character public profiles.
    * Audit trail for duplicate item / exploit detection.

### Pillar E: High-Throughput Rust Worker Architecture
* **Habitat Pattern:** Transitioned from Python to Rust, gaining 6x CPU efficiency and 15x memory efficiency.
* **Game Adaptation:**
  * Leverage our existing Rust stack. Keep Tokio I/O runtimes completely separated from dedicated game simulation worker threads (`std::thread` with bounded channels).
  * Zero-copy binary serialization using `zerocopy` or compact binary protocols matching our v5 specification.

---

## 4. Staged Implementation Roadmap

```text
Stage 0 (Current P0 / P1a)    ──► Stage 1 (P1b / V5-12 & V5-13)   ──► Stage 2 (Clustering / 10k CCU)
In-memory HashMap in auth.rs      PostgreSQL Persistence Worker       Valkey Distributed Cache
Mock GameStorageGateway           sqlx compile-time queries           Shared Session Mutex Across Nodes
Zero infrastructure dependency    Outbox & Idempotency Engine         CDC Stream to Telemetry
```

### Phase 1: Storage Gateway Abstraction & Interface Design
- [ ] Define the `GameStorageGateway` trait and error taxonomy (`StorageError::Conflict`, `StorageError::IdempotentReplay`, `StorageError::Unavailable`).
- [ ] Implement a Mock In-Memory Gateway for deterministic unit tests and P1a playtests.
- [ ] Verify non-blocking behavior: ensure channel backpressure policy is explicit (drop low-priority telemetry, pause tick progression if persistence buffer saturates).

### Phase 2: Schema Migration & PostgreSQL Persistence Worker (V5-12 / V5-13)
- [ ] Draft SQL migrations matching Appendix C:
  - `principals`, `characters`, `character_checkpoints`
  - `bag_slots`, `material_pouch`
  - `reward_claims`, `operation_results`
  - `item_ledger`, `exp_ledger`, `outbox`
- [ ] Implement the async persistence worker thread consuming Tokio PostgreSQL pool (`sqlx` with compile-time query verification).
- [ ] Enforce UUIDv7 generation for encounter IDs and ledger sequence tracking.

### Phase 3: Valkey / Cache Layer Integration (Clustering Gate)
- [ ] Introduce optional Valkey/Redis client for distributed session locks and one-time auth tickets.
- [ ] Maintain fallback to local in-memory `HashMap` when running in single-node/dev mode.
- [ ] Add session concurrency protection (refuse duplicate login attempts across tabs/instances).

### Phase 4: Transactional Claim Engine & Crash Resilience Drills
- [ ] Implement Idempotency Guard: `operation_results` check before executing loot grant or quest reward.
- [ ] Add failpoint injection for simulated crashes (§12.4):
  - Crash before DB commit.
  - Crash after DB commit but before WS client reply.
  - Concurrent duplicate claim requests with identical `op_id`.
- [ ] Verify restore drill from clean ledger replay (`pg_dump` and reconciliation script).

### Phase 5: Outbox CDC & Telemetry Stream
- [ ] Build background outbox processor dispatching events to telemetry/logging.
- [ ] Verify zero latency impact on the 20 Hz zone simulation loop during heavy persistence load.

---

## 5. Verification & Acceptance Criteria

| ID | Test Case | Target Metric / Expected Result |
| :--- | :--- | :--- |
| **AC-01** | Tick Isolation Under DB Delay | Injecting 500ms artificial DB latency causes zero frame drops / lag on zone 20 Hz simulation tick. |
| **AC-02** | Idempotent Reward Replay | Sending 10 identical `claim_reward` requests with the same `op_id` grants the item exactly once; 9 requests return cached success. |
| **AC-03** | Optimistic Lock Conflict | Simulating stale revision write updates 0 rows and triggers clean reconcile instead of data overwrite. |
| **AC-04** | Cache Fallback & High Throughput | Ticket validation and session check take < 1 ms via Valkey / local memory cache. |
| **AC-05** | Crash Recovery Invariant | Server hard kill immediately after loot drop preserves both the character bag state and ledger record without corruption. |

---

## 6. Next Actions

> **STOP:** Do not begin coding or modifying server source code until this plan has been reviewed and specific approval is provided by the team. Live status is tracked in [execution-backlog.md](execution-backlog.md#live-status).
