# Browser action MMORPG — planning and P0 prototype

[Documentation index](docs/README.md): current plans, UI/contracts, active lanes and consolidated history.

The [v5 plan](docs/browser_ragnarok_babylon_rust_10k_plan_v5.md) is the current roadmap, grounded in the local P0 source and the [34-system catalog](docs/system-design-catalog.md). The prototype under `apps/` includes original art, a Babylon.js/TypeScript world, a Svelte 5 HUD and system panels, a Rust WebSocket room, [binary v6 messages](apps/protocol/binary-v6.md), session-bound one-time tickets and shared collision. Cooldown expiry uses room-clock deadlines; UI data stays separate from engine objects. Gameplay breadth, final art, real-device performance and crowded multiplayer remain unqualified.

## Run the prototype

Build the content bundle once from this directory (the server refuses to boot
without exactly one built bundle, and the client syncs its copy on dev/build):

```powershell
cargo run --manifest-path apps/server/Cargo.toml --bin build_content
```

Use two terminals from this directory:

```powershell
cargo run --manifest-path apps/server/Cargo.toml
```

```powershell
npm --prefix apps/client run dev
```

Open `http://127.0.0.1:5173/`. The game opens with a login screen (D-13): **Play as guest** works out of the box, while **Google** and **Discord** sign-in activate only after the owner registers OAuth applications and provides credentials. To add a second player, open the same address in a different browser profile or a private window. Tabs in one profile share the session cookie, so a second tab is refused as "session active". Use WASD/arrows to move, drag the scene to orbit, F for attack, 1 for Arc Slash, and Space for dodge. On a phone-sized viewport, use the left joystick and right action buttons. Append `?renderer=webgl2` to force the WebGL2 fallback; WebGPU is attempted by default.

### Enabling Google / Discord sign-in (owner action, free tiers)

1. Google: create an OAuth client (type "Web application") in Google Cloud Console, with redirect URI `http://127.0.0.1:5173/auth/google/callback`.
2. Discord: create an application under Discord Developer Portal → OAuth2, with redirect URI `http://127.0.0.1:5173/auth/discord/callback`.
3. Start the server with the credentials (never commit them):

```powershell
$env:AETHERFIELD_GOOGLE_CLIENT_ID = "..."
$env:AETHERFIELD_GOOGLE_CLIENT_SECRET = "..."
$env:AETHERFIELD_DISCORD_CLIENT_ID = "..."
$env:AETHERFIELD_DISCORD_CLIENT_SECRET = "..."
# Optional: the browser origin players use (must match the allowed Origin)
$env:AETHERFIELD_PUBLIC_ORIGIN = "http://127.0.0.1:5173"
```

The flow is a confidential-client authorization-code exchange with PKCE and a single-use CSRF `state`; only the provider identity (id + display name) is kept, never tokens. Disabled providers show as "not configured" on the login screen and guest play always works.

To test the browser against delayed or impaired WebSocket frames, start `node tools/delay-loss-proxy.mjs --listen 3002 --target 3001 --delay-ms 50 --jitter-ms 30 --loss-pct 1 --seed 7`, then set `$env:AETHERFIELD_WS_PROXY_TARGET = "ws://127.0.0.1:3002"` before `npm --prefix apps/client run dev`. Session HTTP requests remain on the local Rust server; only `/ws` uses the proxy. Omit the environment variable to use the direct local connection.

All game art in this slice is generated from local Babylon meshes and CSS. Dependencies come from public npm/crates.io packages; no Tripo credits, paid assets, hosted services, or external generation calls are used. The server binds to loopback only and accepts anonymous, volatile browser sessions through an HttpOnly cookie, a short-lived one-use ticket and a strict local Origin check. It has no account identity or durable loot storage and is not qualified for public Internet use or 10,000 players.

Verify with:

```powershell
npm --prefix apps/client run build
npm --prefix apps/client test
cargo test --manifest-path apps/server/Cargo.toml
```

- [Player wiki](wiki/index.html): bilingual (Thai/English) static site generated from the content tables — world map, characters, quest, items, combat stats, economy and published box odds. Rebuild with `python tools/build_wiki.py`.
- [Current plan v5](docs/browser_ragnarok_babylon_rust_10k_plan_v5.md): critical path to P1a/P1b, fifteen work items with acceptance evidence, server/protocol/netcode/persistence designs, playtest protocol, forecast, risks and decisions. Live status is in the [execution backlog](docs/execution-backlog.md#live-status).
- [Plan v4](docs/history/plans-v3-v4.md#plan-v4): superseded; keeps the V4-01/V4-02 closure notes.
- [System design catalog](docs/system-design-catalog.md): 34 tracked systems with detailed NPC, quest, map, item, shop, box, UI and transaction contracts.
- [Long-term plan v3](docs/history/plans-v3-v4.md#plan-v3): historical baseline; retained architecture, workload budgets and capacity arithmetic.
- [Game system landscape study](docs/game-system-landscape-study.md): detailed Ragnarok Online inventory and a free-first comparison with Genshin Impact and GTA Online, with original-game adoption recommendations.
- [P1 gameplay contract](docs/p1-gameplay-contract.md): one original field loop, class, NPC quest, four-player rules, reward invariants, mobile acceptance, and gated shop/box roadmap.
- [Delivery and asset playbook](docs/delivery-and-asset-playbook.md): Harness, Jev, Higgsfield MCP, Blender, relevant skills, and repeatable asset acceptance.
- [Execution backlog](docs/execution-backlog.md): dependencies, ownership, deliverables, acceptance checks, and the first implementation task.
- [Research and capability evidence](docs/research-and-capabilities.md): observed capabilities, source links, limitations, and what remains unverified.
- [Capacity assumptions](planning/capacity-assumptions.json) and [calculator](tools/capacity_model.py): editable scenarios with bandwidth and fleet arithmetic. Outputs are estimates, never benchmark results.
- [Ragnarok reference downloads](references/README.md): pinned rAthena source and the official GNJOY Thailand client installation, with provenance boundaries.
- [Ragnarok source options](docs/ragnarok-source-options.md): what you have, Ragezone findings and the recommended source for the new game.
- [Item browser](exports/rathena-items/index.html): searchable offline view of 29,356 rAthena Renewal item records. [CSV](exports/rathena-items/items.csv), [JSON](exports/rathena-items/items.json), and [converter](tools/rathena_items.py). Run `python tools/rathena_items.py` to regenerate; install optional parser dependency from `tools/requirements-rathena-items.txt` if needed.
- [Harness offline test report](planning/evidence/harness-suite-report.json): result of the local Harness package suite.
- [P0 source](apps): Babylon client, Rust local room, and the temporary protocol contract.
- [Fast Jev / Codex integration](docs/fast-jev-codex-integration.md): installed Codex hooks, data flow, restart requirement and test evidence.

Run from this directory:

```powershell
python tools/capacity_model.py
python tools/verify_plan.py
node '%USERPROFILE%\plugins\harness\bin\harness.js' doctor --project .
```

Planning date: 2026-09-24 (plan v5). Source v2 remains unchanged in Downloads. The P0 prototype is a first playable technical slice; the planned gameplay breadth, production asset pipeline, deployment and 10,000-CCU qualification remain future work.
