# Xexoria documentation

Start here. `llm.txt` and `AGENTS.md` hold the working rules; `.harness/STATE.json` is the run-state authority. Date-labelled reviews are evidence or scoped contracts, not automatic completion claims.

## Current plan and execution

- [Current roadmap v5](browser_ragnarok_babylon_rust_10k_plan_v5.md)
- [Execution backlog](execution-backlog.md) and [P1 gameplay contract](p1-gameplay-contract.md)
- [System design catalog](system-design-catalog.md)
- [Delivery/asset playbook](delivery-and-asset-playbook.md) and [quality standard](production-quality-standard.md)
- [Current file ownership and map hand-off](reviews/2026-10-02-root-handoff-maps-to-claude.md)

## Player interface

- [HUD/theme, minimap and editable controls](ui/mobile-ui-reference-20261001.md)
- [Channels/loading and future login naming](ui/channel-loading-flow-20261002.md) — future naming is explicitly not implemented
- [Safari/Home Screen and landscape/input contract](ui/mobile-web-app-20261002.md)
- [Svelte/Babylon architecture](ui-runtime-architecture.md)
- [Rust chat filter integration and limitations](../apps/server/vendor/xexoria-chat-filter/README.md): room/group/Megaphone, Unicode boundary fix, shared quotas and verification.

## Art and combat

- [Tree/free-asset decision](reviews/2026-10-02-trees-free-assets-decision.md)
- [Free asset scout, 2026-10-02](reviews/2026-10-02-free-asset-scout.md): CC0 models, hand-painted textures, skies, VFX and SFX downloaded with provenance; Quaternius QAL licence change; RaGEZONE verdict
- [VFX quality gate and observed failures](reviews/2026-10-02-vfx-quality-bar-handoff.md), [sample spec](reviews/2026-10-02-vfx-sample-set-v1.md) and [combo table](reviews/2026-10-02-combo-input-window-table-v1.md)
- [Visual discovery program](reviews/2026-10-01-visual-quality-program.md), [engine selection](reviews/2026-10-01-engine-selection.md) and [Blender/Tripo workflow](blender-python-tripo-workflow.md)
- Current map/hero/monster topic specs stay separate in `reviews/`: they are active, specialised work, not duplicates to delete by age.

## World delivery and scale

- [Region/dungeon delivery](region-loading-and-dungeons.md), [transaction design](dungeon-transition-design.md) and [D0 implementation record](reviews/2026-10-01-codex-dungeon-d0-report.md)
- [City district streaming](city-district-streaming.md)
- [500-player logical map](world-expansion-500.md) and [10k fleet scale](scale-to-10k-plan.md) — distinct milestones, neither is a qualified capacity claim
- [Long-term programme](mmo-master-plan-2027.md), [open-world production](open-world-production-plan.md) and [storage draft](online-storage-architecture.md)

## Historical originals

- [v3/v4 plans and initial discussion](history/plans-v3-v4.md) — retained budgets and closure notes
- [Deep/visual reviews](reviews/historical-visual-reviews.md)
- [Implementation reports](reviews/historical-implementation-reports.md)
- [Environment integration and earlier root hand-off](reviews/environment-integration-history.md)
- Original source bytes, renamed-file map, checks and recovery archive: [cleanup receipt](document-cleanup.json)

Historical source dates/test counts/hashes stay intact. Check current state and receipts before treating an old instruction as active. Source code, art, asset licences, protocol versions and pinned Harness skills were not removed by this cleanup.
