# Xexoria Rust network sweep (A30 / SC1)

Standalone, loopback-only Rust CLI. Defaults sweep **10, 50, 100, 250, 500** bots
on **one selected channel**, running idle, wander, party combat and zone change.
One bot owns one socket, bounded baseline cache and rate-limited command stream.
No client/server source changes, no auth bypass, no production benchmark claim.

## Build and verify from the repository root

```powershell
cargo fmt --manifest-path tools/sweep/Cargo.toml --check
cargo test --locked --offline --manifest-path tools/sweep/Cargo.toml
cargo clippy --locked --offline --manifest-path tools/sweep/Cargo.toml --all-targets -- -D warnings
cargo build --release --locked --offline --manifest-path tools/sweep/Cargo.toml
```

`cargo deny` was not installed during this delivery; no package was installed.
When it is available, run it against this manifest and review its findings.
The standalone `[workspace]` and `Cargo.lock` avoid editing the game's workspaces.
Dependencies use the already-cached versions from the server lock.

## Run against an isolated game server

The server must be started by its owner on an unused local port, without
production persistence. This tool does not start, stop or reconfigure servers.
The Origin must match that server's allowed browser origin.

```powershell
tools/sweep/target/release/xexoria-sweep.exe --server http://127.0.0.1:3921 --origin http://127.0.0.1:5173 --counts 10 --scenarios idle,wander --duration 15 --warmup 3 --label pre-a32
```

For the full sweep with **root-provided disposable test sessions**:

```powershell
tools/sweep/target/release/xexoria-sweep.exe --server http://127.0.0.1:3921 --origin http://127.0.0.1:5173 --sessions-file tools/sweep/evidence/private/test-sessions.json --counts 10,50,100,250,500 --scenarios idle,wander,party-combat,zone-change --duration 15 --warmup 3 --channel 0 --ramp-ms 250 --label a32-candidate
```

With the proposed server hook integrated, add `--profile-path /__sweep/profile`.
See [the root-only patch handoff](patches/README.md). The module patch has not
been applied; handler and room-owner wiring require root's integration. Before
that, CPU/wall/GPU ledger columns stay **null**, not RTT or guessed tick times.

Default admission currently limits fresh sessions to **20/minute** and the auth
manager to **256 live sessions**. A normal auth setup cannot validate 500 bots.
SC1 changes none of these limits. A test fixture/seeded-session route is root's
responsibility; an exported file alone does not bypass the manager's capacity.
On the first provisioning/join failure this runner stops admission attempts for
the remainder of the sweep, keeps existing bots alive and records all later
partial runs as **CAPACITY_LIMIT**. It does not repeatedly hammer a 429 endpoint.

Session file shape: a JSON array of objects with one `cookie` string each,
containing `aetherfield_session=<64 hex>` and optionally
`aetherfield_principal=<64 hex>`. Use **distinct, disposable test sessions**.
No browser cookies, API keys or credentials are discovered automatically.
Cookies, join tickets, party codes and cold-message contents are not logged.
Keep the file private and out of source control; `evidence/` is ignored.

## Scenarios and protocol

| Scenario | Behavior and proof |
|---|---|
| idle | zero-axis input at 20 Hz, application ping at 0.5 Hz; snapshot traffic observed |
| wander | deterministic varied steering, boundary steering near the original training-room bounds; authoritative displacement required |
| party-combat | actual `party_create`/`party_join`, groups of up to four; approach visible active monsters, basic attack at at most 2 Hz; party formation, targets and accepted attacks required |
| zone-change | existing `/tower/enter` then ticket/reconnect; observe a different zone and snapshots, then `/tower/leave` and reconnect; both transitions required |

Zone changes exercise **existing private tower routing**, not the future A35 warp
protocol. At most 16 transfers run concurrently. `--duration` is the hold time;
the measured window also includes entry/return time. Rejoin keeps session identity.
Live bots persist across scenarios and increasing counts to avoid session churn
and the server's 30-second disconnected-player grace contaminating occupancy.
The tool closes its sockets and removes its own pending tower assignments on
completion/cancellation. It does not delete characters or restore combat rewards.
Use only a disposable environment. Idle bots may be attacked by the real world.

Protocol v8 is the default. `--protocol auto` permits one retry only after an
explicit protocol mismatch announcing v7/v8; it uses a fresh ticket. Explicit
`--protocol 7` or `8` disables negotiation. v8 privately owned players, relative
coordinates, target overlays, deadlines, delta removals and 32 acknowledged
baselines are reconstructed transactionally. Missing baselines request bounded
resync and remain visible as errors. Reserved pets fail loudly on schema drift.
Malformed/truncated/oversized frames cannot partially update the baseline.
Transport message/frame cap: 16 KiB; outbound cold JSON: 512 bytes.

## Reports and ledger

Every requested count/scenario produces `tools/sweep/evidence/<run-id>.json`
and one append-only `xexoria.ledger/1` row in `planning/perf-ledger.jsonl`.
`--out` and `--ledger` override those paths. Validation tests write **only**
inside this crate's ignored evidence directory, not the shared ledger.
Serialize shared ledger writers externally: this CLI uses one row-sized append
but does not provide a cross-process filesystem lock. A truncated existing
ledger tail is rejected rather than repaired or overwritten.

Reported per connection: messages, application bytes, snapshot Hz, estimated
WebSocket frame bytes, full/delta counts, peak visible entity counts, RTT and
snapshot-gap p50/p95/p99, estimated snapshot age, actions/errors, movement and
zone samples. Window lengths are recorded per connection; summary rates use
the sweep's wall span. Start/freeze control is acknowledged sequentially, so
the connection windows have slight skew. They are not lockstep load generators.
The receive estimate excludes TCP/IP, HTTP, fragmentation and control-frame
overhead. It cannot establish total wire bandwidth.

Snapshot age uses the Pong room tick extrapolated with half the observed RTT,
then compares the received snapshot tick. It is **an estimate**, with network
asymmetry and 50ms tick-quantization uncertainty. Negative estimates are clamped
and counted. Actual one-way packet delay is unavailable without server send
timestamps. RTT, receive gaps, driver lag and server tick-work are separate.
Finite samples cap at 8192 per bot/metric and record dropped counts. Aggregate
percentiles combine retained samples from every admitted connection.

`preflight.valid` means the requested headless scenario actually ran. A JSON
ledger row is not a performance pass: without a verified exact-window server
profile, `verdict.pass` remains false and frame budgets are unverified. The
profile proposal measures elapsed room-owner work, not OS CPU consumption,
and normal-channel timing does not include private tower-instance work.
No GPU, rendering, iPhone memory, packet-loss, or MMO capacity claims follow
from this headless network tool. The synthetic fixture is not the MMO server.

Exit codes: **0** all headless scenarios valid, **2** partial/invalid scenario,
**1** fatal configuration, transport setup, output or cancellation failure.
Per-run reports distinguish capacity, codec, transport and scenario-coverage
failures. Warmup/setup data are excluded from the measured metrics.

## Isolation and tool evidence

Only plain loopback HTTP/WS URLs are accepted; redirects and HTTP proxies are
disabled. A known shared capture lock (or `XEX_GPU_LOCK`) refuses a sweep by
default. `--allow-gpu-lock` is an explicit operator override; don't use it against
the game during visual measurements. Fixture tests use the override on their
own dynamically allocated port and only four clients.

Harness pin/identity read, shared state untouched; local deterministic tests
used. Context7 verified tokio-tungstenite and reqwest API usage against primary
docs; actual cached 0.29/0.12 APIs compiled. Two new bounded read-only audit
workers supplied protocol/ledger findings; primary owns implementation and
integration. Jev: **UNVERIFIED** here because parent-thread data-sharing approval
does not authorize private project transmission from this side chat. Fallback:
local source inspection, repository goldens, tests and fixture evidence. No Jev
call, cache hit, token saving, new install or remote paid job is claimed.

## Delivery status

Implemented: all four scenarios; bounded v7/v8 codec; receive/error metrics;
per-run JSON and schema-compatible ledger append; capacity/failure visibility;
cleanup; exact-window tick-profile proposal and validation.

Verified locally: unit/golden/truncation tests, four-bot fixture across all four
scenarios, refused 6-bot admission recorded as 4/6, session reuse, delta ACKs,
actions, dungeon round trips, profile sequence/loss checks, fmt and clippy.

**A30's 500-bot + server tick p95 gate remains unverified.** The shared capture
lock was active; no load was sent to the main server. Root must integrate the
profile hook, provide an isolated auth fixture for 500 disposable sessions,
run baseline/A32 at the same server revision/settings and inspect the ledger.
