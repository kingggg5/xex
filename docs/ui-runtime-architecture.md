# Xexoria UI runtime architecture

Verified checkpoint: 2026-10-01. Sunmeadow remains the first region to finish.

## Ownership

- Svelte 5 owns the HUD, health/SP/EXP display, party/quest tracker, minimap, hotbar, mobile joystick/buttons, chat and game modal contents. `src/ui/panels/` contains character, skills, party, NPC dialogue, friends, group, tower, settings/rooms, map, journal and menu components. Inventory and Shop remain their own components.
- `GameHud` is the compatibility controller for validated server snapshots and player intent. It does not construct window contents or project damage text into DOM. Existing networking and content translation hooks are retained.
- `bridge.svelte.ts` accepts bounded, finite, JSON-shaped data and copies it into reactive state. Callbacks are a separate command interface. Babylon objects, DOM elements, collections such as Map, and class instances are rejected as snapshot data. HUD and panel field signatures skip unchanged assignments; map position publication is capped at 10 Hz.
- Babylon 9.27.1 owns the world, models, lighting, movement presentation and scene-owned enemy labels/damage. Existing server collision and combat validation remain authoritative. The client still supports WebGPU and WebGL2 fallback.
- Optional Rive is a separate, lazy, same-origin asset adapter. It pauses playback and rendering when hidden, inactive or offscreen, handles reduced motion, bounds asset/canvas size and cleans up listeners/resources. No `.riv` animation has been supplied or mounted; there is no finished animated portrait or box-opening effect.

## Cooldown contract

Binary protocol **v6** replaces relative action cooldown replies with `ends_at_ms: u64`; the JS decoder preserves it as bigint. Cold potion results contain the same expiry field as a safe JSON number. These are milliseconds of the originating **room simulation clock**, not UTC. Welcome/Snapshot ticks and the existing monotonic client clock map that deadline to `performance.now()` once per reply.

The server sends an action result once per action, and an item result once per operation or idempotent replay. It does not send per-frame cooldown progress. Visible cooling buttons update locally at at most 10 Hz; hidden components release their clock timers. Newer action sequences supersede delayed replies, room joins reset action prediction/order, and potion results require the matching pending operation. A replay retains its original expiry, so it cannot renew the UI countdown. Historical stored operation results remain replayable with deadline zero.

Room timestamps do not have a global clock identity. The normal UI clears pending potion operations on disconnect and does not carry countdowns across rooms. A future cross-room operation retry feature must add clock identity or a shared clock contract before exposing cached expiry to its UI.

## Rendering and input lifecycle

PC modals can move by dragging the title handle or using arrow keys; Home centers them. Mobile modals fill the viewport and scroll internally. Modal/chat expansion, blur, hidden pages and renderer loss neutralize held movement; returning to visibility republishes input availability. Close, Escape and direct backdrop clicks restore focus. Thai text uses browser HTML layout.

Combat numbers reuse **24 meshes**, a single digit atlas and three shared materials. Overflow recycles the oldest number; each number supports up to six digits and expires after 850 ms. Enemy names share one atlas and health-bar materials. Depth testing remains active and distant labels are disabled. Scene disposal releases owned meshes, atlases, materials and observer. This is a bounded local implementation, not a 500-player draw-budget qualification.

## Evidence and limits

- Client 91 tests passed, including a 1,000-hit burst with stable mesh/material/texture counts and complete cleanup; Svelte/TypeScript diagnostics and production build pass.
- Server library 159 passed, 5 existing ignored. Live authenticated quest route passed accept, exploration, combat, claim, replay and conflict checks using the active content extent.
- Chrome verified server character/SP/EXP, Guard and potion cooldowns, full-screen 667×375 mobile inventory, settings changes/restoration, 24-pixel desktop window movement and live map. Temporary viewport and graphics test preference were restored.
- The historical unit-cube/doorway smoke is incompatible with current Sunmeadow collider content: it still asserts a cube at [0,1]×[0,1], which is absent from the active zone. It failed that assertion and has not been reported as a gameplay pass. Current Rust collision tests and prior authenticated Sunmeadow traversal evidence remain separate.
- Trade and skill upgrades have no implemented server service and remain explicitly unavailable. Auth/login and opt-in diagnostics still have dedicated legacy controllers. Full world art, real iPhone benchmarks, Rive art, persistent production infrastructure and crowded multiplayer remain pending.
- Production entry remains approximately 2.29 MB minified / 589 KB gzip. This migration does not qualify the large city package for mobile streaming or establish reference-level visual quality.
