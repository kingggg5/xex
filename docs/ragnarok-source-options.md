# Ragnarok source inventory and recommendation

Checked 2026-09-23 at the user's request. “Ragnarok source” can mean three different things:

| Artifact | What it contains | Local status |
|---|---|---|
| Official RO PC download | Client executables, data and scripts distributed for the player client | Current GNJOY `.7z` extracted to `%USERPROFILE%\Games\RagnarokOnline-GNJOY-2026\RagnarokOnline`; not launched |
| rAthena | Community-written server emulator and game-rule/data references | Full tree for pinned revision in `references/rathena/`; GPL-3.0 |
| Official original RO source code | Proprietary game/server/client implementation source from Gravity | Not present in this workspace |

## Ragezone search

The RaGEZONE thread “What is the best emulator for Ragnarok right now?” is dated February 2025 and has one reply with one reaction; the reply recommends rAthena for current content up to fourth jobs and mentions Hercules for pre-renewal/renewal. That is too little review evidence to call either a universally “best” package.

A March 2026 portable-server thread bundles an emulator, web panel, database stack and `Client.exe`; the forum's rAthena tag index showed 32 replies, which measures discussion, not verified positive reviews. Its author says the updater's origin is unknown. It is a convenience repack with a larger supply-chain and provenance surface; its client/data redistribution rights are not established by the forum post. I did not download or install it.

RaGEZONE's highly active “Source Code Ragnarok Origin [Full]” thread is for **Ragnarok Origin**, not RO1. A 2026 resource-summary post reports older 20 GB and newer 98 GB source bundles, says that many upstream links are dead, and describes the author still learning to build the source. Those post counts and bundle sizes do not establish that the source is complete, safe, licensed for reuse or compatible with this RO1 Renewal project.

RaGEZONE's Releases section explicitly mixes member-uploaded emulator source, compiled binaries, database dumps, full packs, client files, GRFs and patchers across historical versions. Release labels and popularity do not establish ownership, redistribution permission, integrity or safe execution.

## Recommendation for this project

Use the already downloaded official [rAthena repository](https://github.com/rathena/rathena) as a **read-only rules/data reference** because the plan uses Renewal and fourth-job era systems. The forum recommendation is consistent with that narrow choice. Pin the revision; keep the new Rust server, browser protocol, maps, client code and assets original. Review each file's license before importing code or data.

To inspect item definitions, run `python tools/rathena_items.py`. This exports CSV/JSON and a searchable offline HTML viewer from `db/re/item_db*.yml`; the current output is in `exports/rathena-items/`. Use `--source references/rathena/db/pre-re` for pre-renewal data. Nested item scripts are rendered as text and never executed. The exporter uses PyYAML `safe_load`, and exports include source-file hashes, commit ID and a GPL license notice.

Do not use Ragnarok client executables or extracted GRF content as development assets. The GNJOY ZIP is kept only as a downloaded game client for the user. It does not provide original source code.

GNJOY's official support page links the 2026 full-client archive and says to extract current files when the client is incomplete. The previously downloaded ZIP had no executable; the separate `.7z` package contains `Ragnarok.exe`, `Ragexe.exe` and `Setup.exe`. See the [client receipt](../planning/evidence/ragnarok-full-client.json). The archive is extracted for the user; no login, launcher update or patch operation has been started.

## Item-data conversion

`tools/rathena_items.py` reads only the local rAthena `db/re/item_db*.yml` files and produces CSV, JSON and an offline searchable HTML viewer. Current run: 29,356 items, zero duplicate item IDs, source revision `e985006171d2eb320ee512a653f4c83aea3d81b6`; receipt: `planning/evidence/item-export.json`. It displays source script fields as text and never executes them. It does not extract client GRF assets or sprites. The dataset derives from GPL-3.0 rAthena; the export folder carries a license notice.

## Harness installation inventory

- Core Harness `0.7.1` is already present at `%USERPROFILE%\plugins\harness`; it has no npm runtime dependencies and its full `npm test` suite passed.
- The vendored `fast-jev-compaction` checkout is optional and is specifically a Claude Code plugin/npm package, not a native Codex compaction setting. It is not installed or connected to this conversation.
- Its checked files currently disagree on version: `package.json` says `0.2.0`, the lockfile root says `0.1.0`, and `.claude-plugin/plugin.json` says `0.3.0`. Its `node_modules` and build output are also absent. This package should be reconciled and reviewed before installing or enabling its hook.
- Cache affinity is implemented per provider adapter, not as a universal Harness installer. The Anthropic adapter tests use a local fake API; this task has no live provider cache-affinity session or measured cache hit.
- No standalone Blender MCP plugin surfaced in the Plugin Management search. Higgsfield's Blender-backed 3D Jutsu MCP tools remain a separate available workflow.

## Sources

- [RaGEZONE emulator discussion (2025)](https://forum.ragezone.com/threads/what-is-the-best-emulator-for-ragnarok-right-now.1241009/)
- [RaGEZONE portable-server pack thread (2026)](https://forum.ragezone.com/threads/create-your-ragnarok-server-portable-no-installation-needed-work-online-and-offline.1261703/)
- [RaGEZONE Releases index](https://forum.ragezone.com/community/ragnarok-releases.576/)
- [Official rAthena source and GPL license](https://github.com/rathena/rathena)
- [Official GNJOY Thailand PC catalog](https://gnjoy.in.th/Game/GamePC)
