# Harness Index

- Schema version: 2
- Project ID: project-a6dcbc9c-dcdf-4efe-9428-b88a9b5694bf
- Memory store: `MEMORY.json`
- Active run ID: RUN-20260923-mmorpg-plan-v3
- Active state: INTEGRATE
- Active workflow: `WORKFLOW.md`
- State authority: `STATE.json`
- Last verified: 2026-10-04

## Load order

1. Applicable platform, user, and repository instructions.
2. This index, `CONFIG.md`, `IDENTITY.json`, and `STATE.json`.
3. Active `WORKFLOW.md` and its current-turn overrides.
4. Query-selected, verified records from authoritative `MEMORY.json`, then an authorized global `MEMORY.json`.
5. Only optional annexes activated below.

`CONTEXT.md`, `PREFERENCES.md`, and `DECISIONS.md` are readable projections. Never use a stale projection instead of `MEMORY.json`, and never edit generated record rows directly.

## Files

| File | Purpose | Authority/load condition |
|---|---|---|
| `IDENTITY.json` | Stable Project ID and sanitized repository fingerprint | Identity authority; always |
| `CONFIG.md` | Portable routing, gate and memory defaults | Always at intake/resume/recall |
| `MEMORY.json` | Durable facts, preferences, decisions, commands and tombstones | Durable-memory authority; query-selected |
| `STATE.json` | Run state and exactly one next action | Run-state authority; always |
| `WORKFLOW.md` | Current request, overrides, gates, role/evidence summaries | Active run |
| `CONTEXT.md` | Generated fact/command/contract/risk view | Human inspection only |
| `PREFERENCES.md` | Generated project-preference view | Human inspection only |
| `DECISIONS.md` | Generated decision view | Human inspection only |
| `PROJECT-MAP.md` | Source-grounded topology, glossary, ownership and flows | Only when activated below and relevant sources are current |
| `TASK-GRAPH.json` | Current run jobs, artifact dependencies, ownership, limits and human edges | Only when activated below for the exact Project ID and Run ID |
| `DESIGN.md` | Approved UI/design contract | UI lane only |
| `EVIDENCE.md` | Detailed bug/performance/security/UI/audit evidence | Activated lane only |
| `EVALUATION.md` | Harness/model benchmark evidence | Benchmark only |

## Active optional annexes

- TASK-GRAPH.json: validated static program dependency annex, adopted 2026-10-02. No graph-run ledger started; shared dirty checkout is not an isolated runtime baseline.

## Archives

- Last archived workflow:
- Last compacted:
