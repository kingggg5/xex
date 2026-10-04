# Xexoria cloud migration handoff

Date: 2026-10-05 (Asia/Bangkok). Target environment: **xex**.

## Checkpoint identity

- Repository: `https://github.com/kingggg5/xex` — verified **public**.
- Dedicated branch: `codex/xex-cloud-checkpoint-20261005`.
- Reviewed remote base: `f3ecd63fb6007000ef860a1484d31a2328c97b24` (11 bootstrap commits).
- Exact tested game-code commit: `80b8eb8c305ffef67a33704b22b7ef80199987bc`.
- Original PC source HEAD: `999038d330084ee98cbb3c5d1ec59c9c966b3e81`, branch `master`.
- This is a snapshot of the existing dirty game, not a new implementation. The isolated checkout preserves the target bootstrap history. The private 28-commit PC history is not uploaded or rewritten.
- The PC project at `%USERPROFILE%/Documents/game` remains the fallback. Do not retire it until the exact approved checkpoint builds and passes checks in cloud.
- **No push, deployment, cloud build or cloud memory-capacity verification has occurred.** The owner's estimated 16 GiB is not an observed resource measurement.

## Architecture and working features

The game retains Babylon.js 9.27.1, TypeScript 6.0.2, Svelte 5.57.1, Vite 8.3.0 and the authoritative Rust server. There is no root Node package or root Cargo workspace: use `apps/client` and `apps/server`.

Preserved work includes guest/session entry, room selection, movement/collision authority, combat and rewards, inventory/equipment/refinement, character information and detailed stat allocation, reconnect handling, TH/EN UI, mobile control layout, current maps and asset loaders.

The explicit local Mage trial has two server-validated skills (`h02_basic`, `h02_star_lance`), staff attachment, casting animation and bounded VFX. Existing live vocation/basic/arc-slash contracts remain. The trial needs the server capability plus the DEV review query; it is not a release of the six-class draft catalogue.

Prior PC-native evidence verified actual casts and monster defeat → EXP → Base/Job level-up → stat points → INT allocation, item refinement/equipment and reconnect in a session-only server. Durable SQL and physical-phone acceptance were not established by those runs. Hero texture sharing was visually checked on WebGL2/WebGPU; its measured resource census estimated 13.33 MiB fewer resident texels for the Mage. That is not a process-RAM or FPS measurement.

The minimap uses actual authored terrain/routes/blockers, +Z north-up, a bounded cached chart and a main-map/Tower gate. The current UI and character/inventory functionality are preserved. Arrival HLOD r02 (23,468 triangles, eight materials) and five starter boulder replacements remain explicitly gated DEV candidates, not a completed AAA map.

## Outstanding work and known limitations

1. Build/test this exact checkpoint in `xex`, then verify real HTTP/WebSocket entry and assets. Cloud bootstrap configuration alone does not validate the game.
2. Map materials, uniform grass, distant proxy forms and reference-image fidelity still need work. No “99% match” or full-map completion claim is made.
3. Six-hero assets/skills and several authoring packages remain draft or review-only. Do not silently enable them as live gameplay.
4. Physical iPhone/Safari, thermal behavior, memory limits, High-tier frame-time gates and real 500-player acceptance remain open. Cloud/desktop browser results do not qualify a phone.
5. SQL integration tests require a separately selected disposable database; do not use a player database or run ignored tests blindly.
6. Optional native KTX and browser/Blender authoring workflows need their own tools and source inputs. Core build uses existing art and does not regenerate it.
7. Public raw-asset redistribution scope requires owner review of `CLOUD_ASSET_LICENSES.md`; preserve all notices and do not call owner-generated derivatives CC0 without evidence.

## Toolchain

Locally verified parity versions: **Node 24.15.0, npm 11.12.1, Rust/Cargo 1.96.0, Python 3.12.10**. `.node-version` and `rust-toolchain.toml` record parity pins, not speculative dependency upgrades. The lockfiles remain authoritative.

The locked Vite/plugin Node requirements intersect at `^20.19.0 || ^22.12.0 || >=24`; exact older/transitive Rust MSRV was not independently established. Use the tested Rust pin. Linux also needs a C compiler/linker for native crates. Blender and GPU tools are not core build prerequisites.

Earlier cloud inspection saw Node 24.19.0, npm 11.9.0, Python 3.12.14, Git 2.52.0 and Blender 4.3.2; Rust/Cargo were absent. Those are historical observations, not current readiness. Provision missing toolchains through approved official sources and follow the cloud environment's proxy/CA/network policy.

## Install and regenerate in cloud

Run from the repository root after checking out the exact owner-approved commit:

```sh
git rev-parse HEAD
git lfs install --local
git lfs pull
git lfs fsck
python3 scripts/cloud_doctor.py
python3 scripts/cloud_setup.py --project-dir apps/client --project-dir apps/server
# After reviewing lifecycle scripts and installed toolchain versions:
python3 scripts/cloud_setup.py --install --project-dir apps/client --project-dir apps/server
export CARGO_BUILD_JOBS=2 CARGO_INCREMENTAL=0
export CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0
cargo run --locked --manifest-path apps/server/Cargo.toml --bin build_content -j 2
npm --prefix apps/client run check
npm --prefix apps/client run build
```

Do not copy Windows `node_modules` or Cargo targets into Linux. `npm ci` installs destination-native optional dependencies using the existing lock. The setup helper fetches Rust dependencies but does not install Rust itself.

Three required generated inputs are deliberately excluded from Git and regenerated by existing code: `apps/client/public/content/bundle.json`, `apps/client/public/coordinate-fixture-v1.json`, and `apps/client/src/assets/codecs/ktx2decoder.worker.js`. The canonical content builder produces `content/build`; client prebuild syncs the content/fixture and bundles the codec worker. The verified content hash is `76178777f179d667`.

## Checks

```sh
python3 -m unittest discover -s tests -p 'test_cloud_setup.py' -v
npm --prefix apps/client test -- --test-concurrency=1
cargo check --locked --manifest-path apps/server/Cargo.toml --all-targets -j 2
env -u AETHERFIELD_DATABASE_URL -u AETHERFIELD_TEST_DATABASE_URL -u UPDATE_BINDINGS \
  cargo test --locked --manifest-path apps/server/Cargo.toml --all-targets -j 2 -- --quiet
git lfs fsck
```

The migration fixes the Rust sweep fixture's Windows-home assumption using a unique OS temporary directory. It does not skip those tests or change production sweep gates. Selected sanitized test fixtures and source helpers under `planning/evidence` are included; private capture/session dumps are excluded.

Local checkpoint results (updated before seal):

| Check | Actual result |
|---|---|
| Bootstrap Python unit tests | PASS, 17 tests |
| Locked Node dependency installation | PASS, offline `npm ci --ignore-scripts`, 231 packages |
| Rust content build | PASS, content hash `76178777f179d667`, 1,374,951-byte bundle |
| TypeScript/Svelte check | PASS, 0 errors / 0 warnings |
| Full client tests | PASS: 912 passed, 0 failed, 1 skipped (913 cases); only optional native KTX-Software coverage skipped |
| Client production build | PASS; existing large-chunk warning remains |
| Rust all-target tests | PASS: 310 passed, 0 failed, 7 SQL tests ignored |
| Sweep tooling | 17 unit tests PASS; loopback integration PASS on isolated rerun; `cargo check` PASS. Initial loopback run during concurrent checks failed timing validity and is retained as a failed run, not erased |
| LFS/secret/privacy final audit | PASS: LFS fsck; 704 LFS files, 635,237,859 bytes. Scoped privacy scan: 0 public-blocking findings across 2,143 candidate paths; this is not a full security certification |
| Checkpoint HTTP/session smoke | PASS: session 204, whoami 200, 32-byte join ticket; content hash matches. Wrong localhost Origin was correctly rejected with 403; canonical 127.0.0.1 Origin passed. No credentials logged |
| Staged whitespace review | Existing whitespace warnings in imported source/docs/licence files retained; no mass reformat or licence-byte changes |
| Linux/cloud checks, physical-phone QA | NOT RUN |

## Local/cloud start

Session-only smoke needs no database or OAuth credentials. Use separate terminals from the repository root:

```sh
env -u AETHERFIELD_DATABASE_URL cargo run --locked --manifest-path apps/server/Cargo.toml --bin aetherfield-server -j 2
npm --prefix apps/client run dev
```

The default server is port 3001 and the Vite client is port 5173. Open the local client at `http://127.0.0.1:5173`; the default server Origin contract does not treat `localhost` as the same origin. Cloud preview requires the environment's reviewed port exposure, exact `AETHERFIELD_PUBLIC_ORIGIN`, and same-origin HTTP/WebSocket proxy. Do not disable strict Origin/session/ticket checks or guess a public preview URL. If exposure requires a different Vite bind, select it explicitly through the cloud's supported preview mechanism.

## Environment variables and credentials

`.env.example` contains empty placeholders and non-secret test configuration only. Keep real values in an ignored local environment file or managed cloud Secrets. User permission to use test credentials is not a reason to bake working provider keys into public client assets.

Core names: `AETHERFIELD_DATABASE_URL`, `AETHERFIELD_PORT`, `AETHERFIELD_PUBLIC_ORIGIN`, `AETHERFIELD_WS_PROXY_TARGET`.

Optional OAuth names: `AETHERFIELD_GOOGLE_CLIENT_ID`, `AETHERFIELD_GOOGLE_CLIENT_SECRET`, `AETHERFIELD_DISCORD_CLIENT_ID`, `AETHERFIELD_DISCORD_CLIENT_SECRET`.

Explicit trial/test names: `XEXORIA_MAGE_TRIAL`, `AETHERFIELD_TEST_COMMERCE`, `AETHERFIELD_TEST_ORIGIN`, `AETHERFIELD_TEST_DATABASE_URL`, `AETHERFIELD_FAILPOINT`, `AETHERFIELD_SWEEP_PROFILE`, `AETHERFIELD_SWEEP_SESSIONS`, `AETHERFIELD_SWEEP_SESSION_FILE`, `UPDATE_BINDINGS`. Keep failpoints and binding regeneration absent during ordinary checks.

Optional local tooling names include `XEXORIA_ASSET_SOURCE_ROOT`, `XEXORIA_AGENT_OUTPUT`, `XEX_SCRATCH`, `XEX_GPU_LOCK`, `XEX_PLAYWRIGHT`, `WATER_VIEW_PROBE_DIR`, `TYPESAFE_API_KEY`, `OPENAI_API_KEY`. Tool credentials are not game/browser dependencies. Report an unavailable optional integration honestly rather than inventing a successful run.

## Assets, privacy and bootstrap coordination

Read `docs/CLOUD_ASSETS.json` for the required, generated and separately retained authoring inputs, sizes and hashes; read `docs/CLOUD_ASSET_LICENSES.md` for provenance and unresolved scope. The manifest records 818 required inputs: 815 copied (619.550 MiB) and three regenerated. All 815 copied hashes and 397 copyright notices match their sources. Five required city GLBs are 69–83 MiB each. Disabled DEV imports still require their files during bundling.

Binary art, fonts and codecs use Git LFS. Keep their real objects available; a small pointer text file is not a usable GLB. The first isolated Node run found indirect monster/stone fixtures omitted by static scanning; they were copied exactly from the PC. Five missing Hero02 fixture paths initially triggered skips, then were restored and all five rig/clip/staff tests passed. Final full-suite counts above include those tests. Large optional Blender/source exports remain on the PC and are listed for separate transfer, not silently discarded. No raw theme folder, private browser state, `.env`, private keys, dependency caches, build outputs, generated sweep logs or full local conversation history is intended for upload.

The target's actual committed bootstrap was inspected and merged with existing project instructions. Its default dependency roots were corrected to the real `apps/*` layout. The earlier separate “Configure Xexoria cloud workflow” task stopped with an incomplete untested candidate; those fragments were not blindly adopted, and no notification/resumption of that task is claimed.

This document is sealed in a documentation-only successor to the exact tested game-code commit above; all game/runtime files are identical. The final branch HEAD is the upload checkpoint and must be recorded by `git rev-parse HEAD` in cloud.

Next priority: owner push approval, then materialize/build/test the approved branch HEAD in `xex`. Preserve the PC fallback until cloud acceptance. Resume art/material and gameplay work only after that checkpoint is reproducible.
