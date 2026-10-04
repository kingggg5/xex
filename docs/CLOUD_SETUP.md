# Xexoria cloud bootstrap
## Status
Configuration source only. This does not install packages in an already running container, migrate the PC project, configure the cloud dashboard, or host the game. The initial kit was prepared before game source was present. The migration checkpoint now includes the existing game; see `CLOUD_HANDOFF.md` for actual local build/test results and the exact code commit. Cloud checks remain unperformed.

## Dashboard setup command
After importing the existing game and reviewing its dependency scripts, set the environment's setup command to:

    python3 scripts/cloud_setup.py --install

Run from the repository root. The helper checks the root, `apps/client`, `apps/server`, and the legacy client/frontend/server/backend directories. The existing game has its Node manifest in `apps/client` and Rust manifest in `apps/server`; no root package or Rust workspace is required. For a different layout, pass `--project-dir relative/path` for every dependency root; explicit arguments replace the defaults. It does not modify lockfiles, install a Rust toolchain, or guess versions. Configure Node and Rust from actual manifests/lockfiles and any version pins before running. If a pin is absent, report it and choose a reviewed toolchain; do not invent a required version. npm/pnpm/yarn must already be installed at the required version. These are environment prerequisites, not claims of current availability.

With no --install, the helper inventories manifests and tools without running project code. Installation executes package lifecycle scripts: review the repository first. Network access to the required registries may be needed; do not broaden network policy or add credentials without approval.

## Existing-game bootstrap and limits

After source import and dependency review, the repository-relative sequence is:

    python3 scripts/cloud_setup.py
    python3 scripts/cloud_setup.py --install
    cargo run --locked --manifest-path apps/server/Cargo.toml --bin build_content -j 2
    npm --prefix apps/client run check
    npm --prefix apps/client run build

The first command is check-only. Stop on BLOCKED; a valid client lock must not allow partial installation when the server lock is missing. The content builder validates `content/source`, replaces only generated `content/build`, and emits the client public content copy. Run it in the destination checkout. Client prebuild/predev scripts create the codec worker and synchronize content and the coordinate fixture. Existing generated `cold_v4.gen.ts` and binary golden fixtures remain unchanged. Normal build consumes admitted art; do not invoke Blender/KTX asset generation as bootstrap.

Full client tests additionally require their selected sanitized `planning/levels`, asset and `planning/evidence` fixtures. Do not upload private browser/session evidence indiscriminately. This checkpoint replaces the Rust sweep test fixture's Windows-home assumption with a unique OS temporary directory; Linux execution still needs verification in cloud. Database integration tests require separate disposable database authorization. Initial build/check does not need a live database, OAuth credentials, Mage capability activation, deployment, GPU or a public server.

The live prototype uses loopback and strict Origin/session checks. Cloud preview HTTP and WebSocket routing requires an explicit reviewed configuration; dependency setup does not open network ports or qualify gameplay/native rendering. Preserve the original PC checkout and local environment.

## Import existing source safely
This bootstrap may create the remote's initial history. Do NOT force-push an unrelated PC history over it. Fetch the remote, inspect both histories, and integrate these files on a separate migration branch. Preserve existing AGENTS.md and project skills through a reviewed merge. Keep the original game and assets intact. Do not upload .env, private keys, tokens, personal data, dependency caches or build artifacts. .gitignore is not a secret scanner; audit staged changes and history.

## Verification
1. Record commit SHA and actual tool versions.
2. Install with committed lockfiles. A missing manifest is BLOCKED, not success.
3. Run the exact existing lint/typecheck/test/build commands. For Rust, use locked builds/tests after reading the workspace instructions.
4. Test guest flow, movement, input release, camera, combat, quest reward idempotency, reconnect, settings and audio mute.
5. Capture the same player camera before/after. Record browser/device, viewport, graphics settings and frame-time metrics.

## Handoff
Record: source commit, commands and results, asset paths/licences, environment-variable NAMES only, completed work, unfinished work, known failures, and next action. Never include credentials.
