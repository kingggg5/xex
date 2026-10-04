# Existing game migration and validation

## Before importing
- Confirm this is the correct original checkout; save uncommitted work without deleting it.
- Fetch the remote first. This repository now has bootstrap history: do not force-push or discard either history. Integrate on a reviewed migration branch.
- Merge existing AGENTS.md, .gitignore and skills. The imported project's real instructions and manifests need reconciliation.
- Review staged files and Git history for credentials, private keys, personal data and restricted third-party assets. Ignore patterns cannot remove an already tracked secret. Do not publish until the review passes.
- Inventory required GLB, texture, sound and animation files with source/licence and hashes. Use appropriate large-file storage without uploading paid/restricted assets publicly.

## Toolchain and setup
- Run `python3 scripts/cloud_doctor.py` to list actual versions.
- Resolve Node version from the original project's engines/toolchain pins, package manager from packageManager/lockfile, and Rust from rust-toolchain.toml. Never silently replace a pin with latest.
- Install missing tools only through approved official sources. Rust/Cargo were absent in the initial cloud inspection; this kit does not install them automatically.
- Run `python3 -m unittest discover -s tests -p 'test_cloud_setup.py' -v` for bootstrap unit tests. These tests do not exercise the game.
- Review setup planning with `python3 scripts/cloud_setup.py`. Use `--project-dir` for the actual dependency roots; nested workspace members often use a root lockfile.
- After source and toolchains are present, configure the cloud dashboard setup command from CLOUD_SETUP.md. A commit alone does not edit that dashboard or refresh an already running checkout.

## Game acceptance
- Record full commit and build/test output. Install/fetch is not a build or test.
- Guest/login, asset loading error recovery, movement and stop, joystick release/cancel, camera, clickable UI, attacks, rewards, inventory, stats, death, reconnect and mute must be checked in the actual game.
- Use identical camera, lighting and graphics settings for visual comparisons. Record actual browser and device for performance claims.
- Do not publish a demo until deployment is authorized and it has been checked separately.

## Credentials
Store only variable names and placeholders in .env.example. Do not include API keys in client bundles or screenshots. Do not change account security to make automation work.
