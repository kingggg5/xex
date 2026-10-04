# Xexoria development rules
This repository is being prepared for an existing game. Do not create a replacement game or treat an empty checkout as permission to scaffold one.

Read docs/CLOUD_SETUP.md and the relevant .agents/skills/*/SKILL.md before work. Existing nested instructions and imported project requirements must be reconciled, never overwritten blindly.

Preserve the Babylon.js, TypeScript/Svelte and Rust architecture. Inspect actual manifests and lockfiles before selecting versions or commands. Prefer existing engine systems and licensed assets. Do not upgrade dependencies speculatively.

Do not delegate tasks to other Codex agents without the owner's permission. Make requested changes directly. Do not publish, deploy, force-push, enable paid services, create credentials or change account security without authorization. Never print environment-variable values or commit secrets.

Quality gates: run applicable type checks, tests and builds; inspect the actual game camera, desktop and touch controls. Clearly distinguish PASS, FAIL, BLOCKED and NOT RUN. A generated reference image or Blender render is not evidence of in-engine quality. Never claim mobile performance based on a desktop or cloud browser.

Use a dedicated work branch once the original source has been imported. Preserve uncommitted work. Record the tested commit and remaining blockers in the handoff.
