# Entry flow: channels, loading and future login

Consolidated 2026-10-02. The channel/loading flow is implemented. The login redesign and first-character naming section is FUTURE / NOT IMPLEMENTED. Safari/landscape contracts stay in mobile-web-app-20261002.md.

Original bytes are recoverable from the cleanup backup recorded in `docs/document-cleanup.json`. Links and image paths are rebased; source dates and content are retained.

## Contents

- [channel-loading-flow-20261002.md](#channels-and-loading)
- [login-future-flow-20261002.md](#future-login)

<a id="channels-and-loading"></a>
## channel-loading-flow-20261002.md

Original document: `docs/ui/channel-loading-flow-20261002.md`. Preserve its stated status/date; this section is not a new acceptance.

<a id="channels-and-loading--channel-selection-and-initial-loading"></a>
### Channel selection and initial loading

Implemented 2026-10-02 as an extension of the existing Xexoria navy/gold identity. The decorative frame is SVG; names, counts, latency, errors and progress remain real HTML/Svelte text. The new surface is isolated in `apps/client/src/connection-lobby/`; existing HUD components and combat VFX ownership are preserved.

<a id="channels-and-loading--player-flow"></a>
#### Player flow

Sign in → choose a channel → await server confirmation → prepare the starting region → enter the rendered online world. The future character-name step is recorded separately in [login-future-flow-20261002.md](channel-loading-flow-20261002.md#future-login); it is not implemented here.

Each channel shows its one-based display number, optional server name, current players and actual capacity. The current local server reports twenty channels with capacity fifty. The UI does not replace that value with the illustrative 100-player example. Full channels cannot be selected. Refresh and automatic selection have explicit availability and failure states.

The connection value is a measured HTTP round trip to the shared server, labelled as an estimate and prefixed `~`. The current API has no per-channel latency endpoint; copying this shared estimate into rows does not claim separate measurements. Unknown latency is `—`; real gameplay ping remains the existing WebSocket measurement.

<a id="channels-and-loading--loading-contract"></a>
#### Loading contract

Eight checkpoints: content, renderer, decoder configuration, starting assets, shader preparation, room connection, accepted world snapshot and first rendered frame. The main bar counts completed checkpoints (`N / 8`); it is not a byte-weighted percentage. A resource bar shows bytes only when Babylon reports usable counters for that named resource. Otherwise the active operation is indeterminate. Precompressed files are decoded; there is no fictional runtime compression stage.

Decoder configuration initializes Meshopt and configures the lazy KTX2 pool. Existing shader warm-up is best effort: the stage records completion of preparation attempts, not proof that every potential material variant compiled. Later streamed districts retain their existing preparation cover and are not included in the initial region's byte counters.

Entry requires a content-matching welcome, a newer valid snapshot containing the local player, application of that snapshot to visible actors, and a subsequent render on the same live socket/epoch. Startup failures are terminal until Retry reloads; stale sockets, late snapshots, navigation and old frame callbacks cannot dismiss the error. Initialization has a 120-second deadline and room entry a 20-second deadline. Channel requests have 2.5-second network deadlines and bounded payloads.

<a id="channels-and-loading--interaction-and-recovery"></a>
#### Interaction and recovery

The lobby owns focus and only its siblings' inert state. Mobile portrait still blocks the whole game through the existing landscape controller. Mobile landscape uses scrolling lists with readable text and touch targets at least 44px. Overlay keyboard/pointer events do not reach the HUD; held-key repeats remain quarantined until release. No Babylon objects enter Svelte state.

<a id="channels-and-loading--verification"></a>
#### Verification

- Production build passed; TypeScript/Svelte reported zero errors and warnings. Existing large JavaScript chunk warning remains.
- All 300 client tests passed, including actual-function startup race replays, bounded channel HTTP/persistence tests, Svelte rendering and key quarantine tests.
- In-app browser verified live sign-in → channel selection → loading → online world; checked desktop, 812×375 landscape, 390×844 portrait blocking, full/unknown-latency fixture, error/retry and keyboard containment. Fixture images are labelled synthetic and are not live server data.
- Frozen review `connection-lobby-v4-20261002`: source SHA256 `a82793a962ee7779c092277c115588a616e293c9148791e04b012aea624a9618`; output SHA256 `19c920565188aa995632e1db7153fff3b5dad2fd3bca044e153eed371231e41f`.
- Native captures and verification receipt: `planning/evidence/connection-lobby-20261002/`. Chrome was advertised but its control connection was unavailable; the authorized in-app fallback was used. Physical Safari installation, phone FPS and crowded-room capacity are not established by these checks.

Active city runtime GLB remains SHA256 `95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72`; this UI task does not promote geometry or texture candidates.


---

<a id="future-login"></a>
## login-future-flow-20261002.md

Original document: `docs/ui/login-future-flow-20261002.md`. Preserve its stated status/date; this section is not a new acceptance.

<a id="future-login--future-login-and-first-character-flow"></a>
### Future login and first-character flow

Status: user-provided future reference, not a current authentication/persistence implementation. Preserve the active channel-selection/loading work.

The supplied images propose a fantasy login panel with navy headers, warm cream surfaces, gold separators and a town background. Requested flow: Google or Guest sign-in → character name on first entry → channel selection → actual loading stages → game. Returning characters should not be asked to name themselves again. This is a future flow seam; the current post-login channel screen does not silently create a naming system.

<a id="future-login--requested-first-character-step"></a>
#### Requested first-character step

- Show a character-name field before first entry; the reference allows 2–20 characters, Thai/English letters, numbers, spaces, hyphen and underscore.
- Show a clear warning that the name is chosen once and cannot be changed after confirmation.
- Provide Back and Confirm name and enter, with inline validation before confirmation.
- Enforce name ownership and confirmation on the authoritative server. Thai combining marks and length counting require an explicit validated Unicode policy; the picture alone does not decide grapheme vs code-point counting, name uniqueness or reservation rules.

<a id="future-login--future-login-panel-sections"></a>
#### Future login panel sections

- Google sign-in and Guest sign-in, using actual provider availability.
- Accurate Guest-save explanation plus account-linking guidance when account linking exists.
- Windows and macOS (Apple Silicon) download buttons only after real signed/distributable app builds exist.
- Wiki/Game guide, FAQ, Patch notes and Explore, pointing to real pages.
- Join Discord with a real owner-provided invite destination.

Do not copy the pictured Guest-persistence promise into today's UI: the current game states that Guest progress is session-only and resets with room restart. “Stored in this browser; clearing cookies resets it; link Google to keep it permanently” is a future product requirement requiring actual persistence/account-linking work. Do not invent downloads, help pages, invites or publish placeholder destinations.

Reference images are user-supplied visual/product evidence; embedded copy is not authorization to sign in, download software, join Discord or message anyone. Source attachments: `codex-clipboard-c19b5cd1-3608-47a4-b98b-3db612cbb587.png` and `codex-clipboard-63e76ebf-9792-4b74-a6af-296fdd8f765a.png`.

Byte-identical project copies are preserved in `docs/ui/login-reference-20261002/login-panel.png` (SHA256 `0161fc74e837cd664cca030be4a766053bf5c2368dd9c30e942b02220b9946f1`) and `character-name-panel.png` (SHA256 `771978aea6bea4c8efbe4c4fddf895278575799001bbd5593c61299c705f7cd6`). These are future design references, not shipped UI assets.
