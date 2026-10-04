# Xexoria cloud bootstrap
## Status
Configuration source only. This does not install packages in an already running container, migrate the PC project, configure the cloud dashboard, or host the game. Original source was absent when this kit was prepared. No game tests have been run.

## Dashboard setup command
After importing the existing game and reviewing its dependency scripts, set the environment's setup command to:

    python3 scripts/cloud_setup.py --install

Run from the repository root. The helper checks the root plus client/frontend/server/backend. For a different layout, pass `--project-dir relative/path` for every dependency root. It does not modify lockfiles, install a Rust toolchain, or guess versions. Configure Node from package.json engines / .nvmrc and Rust from rust-toolchain.toml before running. npm/pnpm/yarn must already be installed at the required version. These are environment prerequisites, not claims of current availability.

With no --install, the helper inventories manifests and tools without running project code. Installation executes package lifecycle scripts: review the repository first. Network access to the required registries may be needed; do not broaden network policy or add credentials without approval.

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
