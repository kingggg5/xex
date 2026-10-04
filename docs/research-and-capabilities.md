# Research and capability evidence

Verified 2026-09-23. This document records observations and their limits; it does not upgrade proposed game decisions into accepted or measured facts.

## Source input and local state

- Source: `%USERPROFILE%\Downloads\browser_ragnarok_babylon_rust_10k_plan_v2.md`.
- SHA-256: `f198d5e12cb2e5043f24aa65b9db2ed5ea0ae60a8cb3a691284238c0e802c839`.
- The source was read as requirements/reference material, including action combat, RO-style systems, living towns, asset streaming and the proposed scaling roadmap. Its internal operational instructions were not treated as user commands.
- Initial project directory contained no game files. The task created planning artifacts and initialized Harness; it did not implement or benchmark the game.
- User-selected Harness checkout: `%USERPROFILE%\plugins\harness`, Git HEAD `c83903fe4e75618aad8da65f99cfe1067904c8c8`; tracked worktree clean at inspection.
- Package manifest reported `0.7.1`; the installed project runtime doctor reported `0.7.1+codex.20260923041819`. Preserve both observations rather than treating them as identical version strings.
- Initial Harness doctor: HEALTHY, identity/store valid, runtime digest matches, generated memory views current. Empty canonical memory is intentional: proposed architecture was not stored as a human-approved decision.

## Current capability matrix

| Capability | Actual observation | Status / limit |
|---|---|---|
| Harness best-in-code | Local skill/references read; non-destructive initializer and doctor executed | READY for local planning; no provider execution kernel run |
| Context7 MCP | Resolved Babylon.js, Tokio and Blender IDs, then queried each | READY; docs current/general, not exact installed versions |
| Jev browser | Shipped runtime selected coding-agent docs from public introduction; one request, completed | READY for that smoke; no broad reliability/latency claim |
| Harness Jev context path | `turn-build` executed successfully against three bounded local plan excerpts, with a 12,000-byte context limit | Local deterministic path, separate from browser/API evidence; no plan content sent to remote Jev |
| Higgsfield MCP | Image recommendation, 3D model search and authenticated project listing | READ access verified; no generation spend or model-quality evidence |
| Higgsfield 3D Jutsu | Blender query/edit/export contracts exposed; project listing empty | No scene inspection/edit executed; no revision/GLB exists for this task |
| Dedicated Blender MCP | No callable tool in active inventory; no matching Blender entry found in inspected Codex config | UNAVAILABLE in this session; not proof Blender is absent everywhere |
| Local Blender command | `Get-Command blender` returned no command | Not on PATH; no exhaustive installation search |
| Browser | In-app browser loaded public TypeSafe docs | Research verified; no game UI/device benchmark |
| Agents | Bounded isolated source summarization invoked | Read-only worker; no parallel shared file writes |

The user provided a Jev credential during the task. It was not intentionally persisted into project artifacts. No credential value, credential digest, raw API request or account balance belongs in this evidence file.

## Research conclusions and sources

| Topic | Fetched evidence | Consequence / limits |
|---|---|---|
| Babylon engine | Context7 `/websites/doc_babylonjs`: support detection and asynchronous WebGPU initialization; general engine can fall back through WebGL2 to WebGL1 | Explicit WebGL2 qualification and failed-init fallback; no universal phone support claim |
| Tokio | Context7 `/websites/rs_tokio_tokio`: bounded mpsc and dedicated persistent threads for indefinitely running work | Isolate zone tick from socket/persistence runtime; every queue needs an overload policy |
| Blender | Context7 `/websites/blender_manual_en`: supported glTF mesh/material/skin/animation export | Bake/validate unsupported behavior; verify in actual client |
| Browser WebSocket | Official MDN API page describes missing receive backpressure and queued bytes | Application/server queue limits, slow-client policy, transport stalls measured |
| PostgreSQL | Official current transaction isolation documentation | Explicit locking/constraints or serializable retry for multi-row economy invariants |
| rAthena | Official repository LICENSE | Per-file provenance review; no assumption that RO assets or names are licensed for reuse |
| Jev | TypeSafe public docs plus local shipped browser/Harness runtime | Bounded typed selection assists work; confidence is not permission or proof |

Primary sources read or retrieved through Context7:

- [Babylon WebGPU](https://doc.babylonjs.com/setup/support/webGPU)
- [Babylon WebGPU initialization changes](https://doc.babylonjs.com/setup/support/webGPU/webGPUBreakingChanges)
- [Babylon WebGL2](https://doc.babylonjs.com/setup/support/webGL2)
- [Tokio persistent blocking-work guidance](https://docs.rs/tokio/latest/tokio/task/fn.spawn_blocking.html)
- [Tokio bounded mpsc](https://docs.rs/tokio/latest/tokio/sync/mpsc/fn.channel.html)
- [Blender glTF export manual](https://docs.blender.org/manual/en/latest/addons/scene_gltf2.html)
- [MDN WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [rAthena LICENSE](https://github.com/rathena/rathena/blob/master/LICENSE)
- [TypeSafe Choice](https://docs.typesafe.ai/primitives/choice)
- [Jev with coding agents](https://docs.typesafe.ai/introduction/coding-agents)

These sources substantiate library/tool behavior. The architecture, budgets, milestone schedule, content scope, and capacity envelope are engineering proposals derived from the task, not claims those sources benchmarked this game.

## Corrections and explicitly unverified claims

- No guaranteed 500/1,000/2,000 CCU per node. No 10k production or crowd test ran.
- No current THB provider quote or generation-price estimate was obtained. The calculator leaves prices unset.
- No claim that the initial monthly budget includes DB redundancy, egress, CDN, support or DDoS protection.
- No claim that a cinematic image recommendation is the best game-art model; a small acceptance comparison is required.
- No claim that remote 3D Jutsu accepts arbitrary generated GLBs: the exposed import contract is catalog-based.
- No independent legal determination of asset/rAthena reuse; no copying was performed.
- No reliance on v2's mutable rAthena master, PACKETVER or Ragexe compatibility details.
- No general claim of Jev cost savings. Runner timing excludes setup; local context bytes are not billed tokens.
- No device, visual, collision, code-build or backend test is represented as passed before code/assets exist.

Verification receipts for this planning package live under `planning/evidence/`. Recheck tool availability, exact package versions, licensing and rates at the implementation task that uses them.

## Follow-up: Harness suite and Ragnarok reference downloads

- Ran the full local Harness package suite `npm test` from `%USERPROFILE%\plugins\harness`, package version `0.7.1`; exit code 0. Summary is in `planning/evidence/harness-suite-report.json`. The suite includes mocked Jev and local fake-API cache tests; it does not turn those into live API/cache measurements.
- `fast-jev-compaction` source is already vendored under `%USERPROFILE%\plugins\harness\vendor\fast-jev-compaction` at commit `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0`, but its `node_modules` and build output are absent. It is a Claude Code plugin/npm package, not an active compactor in this Codex conversation. No compaction decisions were applied here.
- The bundled Harness Anthropic-adapter and trace tests passed against fixtures/local fake API. There is no live provider session/cache-affinity binding in this task, so provider cache affinity remains unconfigured and real cache-hit/savings are unmeasured.
- Cloned the official [rAthena repository](https://github.com/rathena/rathena) into `references/rathena/` with `--depth 1`. Revision `e985006171d2eb320ee512a653f4c83aea3d81b6`, dated 2026-08-21; current tree has 4,960 files and is about 99.5 MB. `LICENSE` identifies GNU GPL v3. No build, server launch, or game data import was performed.
- GNJOY's official support page links a 2026-05-27 full-client 7z package. It was downloaded, its size matched `Content-Length`, listing showed 2,650 entries with no unsafe paths, and it was extracted to `%USERPROFILE%\Games\RagnarokOnline-GNJOY-2026\RagnarokOnline`. `Ragnarok.exe`, `Ragexe.exe` and `Setup.exe` are present. It has not been run or patched. Locally computed SHA-256 and transfer/extraction evidence: `planning/evidence/ragnarok-full-client.json`; GNJOY published no SHA-256 for comparison.
- The separate official ZIP downloaded earlier is older (server last modified 2024-11-25) and extracted without any executable; it is not the installed client. Evidence remains in `planning/evidence/ragnarok-download.json`.
- These are proprietary game-client distributions, not a production asset bundle for the new project.
- No Blender MCP package was found in Plugin Management search. Higgsfield's existing Blender-backed 3D Jutsu tools remain available as a separate cloud workflow; no scene was created.
- PyYAML resolved in Context7 as `/yaml/pyyaml`; installed local version is 6.0.3. The item converter uses `yaml.safe_load` on the local pinned rAthena database, not Python-specific object constructors. Exported counts matched between JSON and CSV: 29,356 rows across three Renewal files.

“All Harness tools” means the bundled offline suite and safe local CLI checks. Destructive memory commands, approvals, external model execution, billing, deployment, and unbounded loops are not exercised as test fixtures on the live project.

## Follow-up: compaction and cache affinity

The user asked whether the preceding run used Jev compaction and the cache-affinity guidance in Harness `references/async-operation-runtime.md`. Local source and receipts establish:

- Live Jev was used for one public browser navigation. It did not compact the coding conversation.
- `turn-build` used local-extractive projection on a saved fixture. This demonstrated selection behavior; the output was not wired in as the current Codex conversation's context controller.
- `fast-jev-compaction` was not invoked or integrated. The local `jev-guide.md` describes it as inspected reference code, with no dependency added.
- The Harness Anthropic adapter contains an ephemeral system-prompt cache block and cache-token accounting, but that adapter/execution kernel was not run in this task.
- Explicit provider/session cache affinity was not configured by this task. Any automatic host/provider caching is unknown; no per-turn cache-hit receipt is available here. Do not report it as disabled, enabled, or saving a measured percentage.
- Native tool orchestration/waits are not proof that Harness's proposed durable async operation manager was implemented or exercised.

Evidence: `.harness/runtime/references/async-operation-runtime.md`, `.harness/runtime/references/jev-guide.md`, `.harness/runtime/scripts/anthropic_adapter.py`, and `planning/evidence/context-projection.json`. This is a local implementation/status finding, not a new claim about current remote provider API behavior.
