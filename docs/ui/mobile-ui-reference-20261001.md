# Player interface: reference, minimap and editable controls

Consolidated 2026-10-02. Implemented controls/theme and dated checks are separate from reference concepts. Device qualification is only what the original receipts establish.

Current ownership is defined by [the map hand-off](../reviews/2026-10-02-root-handoff-maps-to-claude.md) and `llm.txt` LANES. Any earlier root geometry/lighting role stated inside a dated source section is historical.

Original bytes are recoverable from the cleanup backup recorded in `docs/document-cleanup.json`. Links and image paths are rebased; source dates and content are retained.

## Contents

- [mobile-ui-reference-20261001.md](#mobile-reference)
- [mobile-hud-reference.md](#early-mobile-concept)
- [minimap-design-20261001.md](#minimap)
- [hud-control-layout-20261001.md](#control-layout)
- [2026-10-01-mmo-ui-v2-report.md](#ui-v2-implementation)

<a id="mobile-reference"></a>
## mobile-ui-reference-20261001.md

Original document: `docs/ui/mobile-ui-reference-20261001.md`. Preserve its stated status/date; this section is not a new acceptance.

<a id="mobile-reference--mobile-hud-direction--user-reference-2026-10-01"></a>
### Mobile HUD direction — user reference, 2026-10-01

The user supplied a landscape Ragnarok mobile screenshot during the city review. This is a layout/art reference, not evidence that those systems exist in Xexoria or a request to add every pictured feature. Product HUD implementation remains with the user-designated UI owner. Root continues geometry, traversal and water.

<a id="mobile-reference--keep-from-the-reference"></a>
#### Keep from the reference

- Compact portrait/status block at the upper left: HP/SP first, Base/Job progress secondary. Blue panels, restrained gold borders, readable colorful skill icons.
- Rounded square minimap at the upper right, with a compact channel label and a clear player arrow. Quest details can collapse beneath it.
- Left-thumb joystick; primary attack and supporting skill buttons in a right-thumb arc. Separate touch targets with clear pressed/cooldown/disabled states.
- Compact chat above the movement area, with an explicit expand control. Preserve Thai text shaping in the DOM/Svelte layer.
- A useful amount of open world remains visible around the character and combat warnings.

<a id="mobile-reference--adapt-for-xexoria"></a>
#### Adapt for Xexoria

The earlier user request places **FPS and ping at the top left**. Keep that placement; the sample's bottom-left telemetry does not override it. Respect the device's safe-area insets and keep telemetry clear of portrait/status.

Use existing actions first: basic attack, Arc Slash, Guard, Dodge and Potion. Group system navigation behind the existing Menu on compact screens. The sample's Bot, Premium and extra skills are not authorization to introduce game systems or inactive buttons.

Starting size targets for implementation/review: status width 180–208 CSS px; minimap 132–156px; joystick 104–124px; attack 58–68px; supporting touch controls at least 44px with spacing. These are design starting points, not measured device acceptance. Reduce occupied space using collapse/overflow before shrinking touch targets.

Keep chat collapsed to a few lines during combat. Opening chat or a fullscreen system panel must release movement input; keyboard opening, pointer cancellation, lost focus and closing panels must not leave a held joystick/skill input. Inventory/shop/system panels use fullscreen mobile layouts and floating PC windows as already requested.

<a id="mobile-reference--ui-owner-verification"></a>
#### UI-owner verification

Review landscape and portrait transitions, safe-area/notch behavior, Thai labels, two-thumb movement plus attack, cooldown readability, low-health warnings, chat keyboard and panel transitions. Use a real iPhone XS/11 Pro class device for acceptance; desktop emulation and this screenshot do not establish phone performance. Keep the player, target and attack-warning region unobscured. Do not fabricate online population, party membership or progress values from the screenshot.

Native city/model review remains a separate gate. A polished mobile HUD cannot qualify stairs, collisions, model form, water or 500-player capacity.


---

<a id="early-mobile-concept"></a>
## mobile-hud-reference.md

Original document: `docs/mobile-hud-reference.md`. Preserve its stated status/date; this section is not a new acceptance.

<a id="early-mobile-concept--mobile-hud-reference--v1"></a>
### Mobile HUD reference — v1

Date: 2026-09-23. User-requested edit of the supplied fantasy action-game screenshot. This is a visual concept, not an implemented or device-tested game UI.

![Landscape mobile touch HUD](../../assets/references/mobile-touch-hud-v1.png)

<a id="early-mobile-concept--changes-in-the-sample"></a>
#### Changes in the sample

- Lower-left translucent movement joystick with a separate thumb disc.
- Lower-right large attack button, four skill buttons, dodge, jump and potion.
- Collapsed chat strip above the joystick; bag/menu above the action cluster.
- Removed desktop keyboard labels and bottom-center hotbar; retained the scene, party HUD, minimap and quest panel as closely as generation permits.

<a id="early-mobile-concept--implementation-acceptance"></a>
#### Implementation acceptance

Map UI dimensions to CSS pixels and actual viewport safe areas rather than copying image pixels. Joystick and buttons need real-phone reach tests; this image alone establishes neither ergonomic size nor touch performance. Support simultaneous movement, camera drag and skill input using distinct pointer ownership; release/cancel/blur must reset the stick to neutral. Keep camera gestures out of occupied control hit regions. Offer movable/scalable controls, adjustable opacity and a left-handed layout when the core controls work.

Test on the reference iPhone and Android devices at the smallest supported landscape viewport. Verify notch/home-indicator clearance, no browser scroll/zoom caused by gameplay gestures, readable cooldowns, no accidental activation while dragging, and no lost pointer causing stuck movement. Collapse quests/party details further if the physical display is crowded. Preserve critical enemy telegraphs above visual detail.

The supplied image contains named-game references; its use here is design discussion, not a production asset-rights decision. Production naming/art follows the main plan's original-world or explicitly licensed direction.

<a id="early-mobile-concept--generation-record"></a>
#### Generation record

- Method: built-in image_gen edit, one output; not Higgsfield generation.
- Input: user-supplied `ChatGPT Image Sep 23, 2026, 03_39_23 PM.png` in Downloads.
- Saved output: `assets/references/mobile-touch-hud-v1.png`.
- Exact final prompt: [mobile-touch-hud-v1.prompt.txt](../../assets/references/mobile-touch-hud-v1.prompt.txt).
- Visual inspection: joystick/action layout present, central combat scene preserved closely. No runtime, accessibility, collision or FPS validation is implied.


---

<a id="minimap"></a>
## minimap-design-20261001.md

Original document: `docs/ui/minimap-design-20261001.md`. Preserve its stated status/date; this section is not a new acceptance.

<a id="minimap--xexoria-minimap-refinement--2026-10-01"></a>
### Xexoria minimap refinement — 2026-10-01

The minimap is a live rounded rectangular chart in a warm gunmetal and brass frame. Its position marker, authored routes and points of interest come from the existing HUD data bridge. Code draws the functional map; image generation is unnecessary for this interface.

<a id="minimap--visual-and-interaction-decisions"></a>
#### Visual and interaction decisions

- Area name above the chart, a restrained north indicator, mint player glyph, ivory trails, brass NPC diamonds, blue windmarks and soft red combat points.
- The player stays centered. Default half-range is the lesser of the actual region extent and 72 metres. Zoom cycles through 1×, 2× and 4×; the full world map button retains the complete region view.
- Existing world-map X/Z projection is preserved. The player glyph indicates position; the current HUD contract does not provide camera or character heading.
- The old fixed decorative castle, river and trees were removed because they did not follow the actual world layout. The chart currently contains route and POI data, not a terrain screenshot. Detailed city lanes and building footprints must be supplied as real map data before they can be drawn accurately.
- Preview party dots remain preview-only and carry a visible preview label at larger sizes. They are never presented as live multiplayer positions.
- Both controls use native buttons with localized names, keyboard focus and at least 44×44 pixel touch targets. The zoom control is a sibling of the world-map button, never a nested button.

<a id="minimap--responsive-sizing"></a>
#### Responsive sizing

| View | Frame width | Treatment |
| --- | ---: | --- |
| Desktop >1200px | 204px | Area title, key hint, scale, coordinates and player legend |
| Desktop ≤1200px | 172px | Same chart and controls |
| ≤900px | 142px | Key hint and preview caption omitted |
| ≤540px | 116px | Compact header, coordinates, no redundant player legend |
| Landscape ≤900px wide / ≤420px high | 98px | Coordinates omitted; floating 44px zoom leaves center marker visible |
| Landscape ≤360px high | 96px | Header and compass captions omitted |

The local component overrides legacy circular `#minimap` and `.map-panel` styles only when its own card is present. On mobile the rail starts beneath the toolbar. Parent HUD integration still needs to place the compact quest tracker away from skill buttons and avoid the existing location/player-card overlap; this refinement does not rewrite the whole HUD.

<a id="minimap--resource-and-state-boundary"></a>
#### Resource and state boundary

- `HudMinimap` remains plain data. Optional `language` and `locationName` props supply presentation text. No Babylon objects enter Svelte state.
- One 256×256 Canvas2D bitmap, drawn by a Svelte effect when map inputs change. No animation loop, observer, timer, external image, extra WebGL context or added dependency.
- Routes are capped at 64 with 80 vertices each; POIs are capped at 80. Nonfinite route coordinates break that segment, and nonfinite POIs are skipped.
- Player updates are already throttled to 100ms in `GameHud.setPosition`. The effect has no ongoing resource requiring disposal; every canvas save is paired with restore.
- The scale bar occupies 56 logical canvas pixels, corresponding to half the visible extent. It scales with the viewport rather than using a misleading fixed CSS length.

<a id="minimap--verification-and-limitations"></a>
#### Verification and limitations

- `npm run check`: TypeScript clean; Svelte **0 errors and 0 warnings**.
- Impeccable mechanical detector: `[]`.
- Chrome / WebGL2 desktop and landscape 844×390 plus iPhone XS-size 812×375 inspected in the actual game.
- Zoom 1×→2×→4×→1× verified through the native buttons. Opening and closing the full map preserved the modal behavior and correctly blocked touch movement while open.
- At 812×375 the chart measures 86×86 and the zoom target measures 44×44. Actual phone performance, Safari behavior and engine frame rate are not certified by these layout checks.
- Screenshots: `planning/evidence/minimap-20261001-desktop.png` and `planning/evidence/minimap-20261001-mobile.png`. The wider HUD/world work was concurrent; those screenshots must not be treated as acceptance of city art or engine performance.

API evidence: Svelte's current official documentation retrieved through Context7 for `$props`, `bind:this` and canvas `$effect` behavior. The minimap design inherits Xexoria's established HUD and the user's supplied rounded-frame reference.


---

<a id="control-layout"></a>
## hud-control-layout-20261001.md

Original document: `docs/ui/hud-control-layout-20261001.md`. Preserve its stated status/date; this section is not a new acceptance.

<a id="control-layout--player-control-layouts--2026-10-01"></a>
### Player control layouts — 2026-10-01

Players open **Settings → Edit controls**, move an existing control, then choose **Save layout**, **Cancel changes**, or **Reset layout**. Reset changes only the draft until Save. Keyboard users can focus a control handle and use arrows (4 CSS pixels) or Shift + arrow (24 pixels). Escape cancels. Game input is paused while editing.

The layout belongs to this browser/device. Desktop, mobile landscape and mobile portrait have separate profiles. Saving one profile and resetting it preserves the others. There is no account/cloud synchronization or new gameplay action.

<a id="control-layout--integration"></a>
#### Integration

`apps/client/src/hud-control-layout-controller.ts` exports `createHudControlLayout({ language, onEditingChange, storage? })`. It returns `isEditing()`, `beginEdit()`, and `dispose()`.

The root integration must independently guard gameplay actions and movement while `isEditing()` is true. The controller also blocks game pointer/click/key events while editing and emits the existing blur reset path on entry, cancellation and interrupted drags. The optional storage adapter is for an isolated test/embed boundary; production defaults to browser localStorage.

The controller uses the incumbent HUD controls: `#joystick`, visible `[data-action]` combat controls, PC/mobile potion controls, Bag, Menu, Fullscreen, Interact and existing desktop navigation buttons. FPS/ping and other read-only HUD information remain fixed. Settings injection accepts both `#modal-content` and `.modal-content`; close is scoped to that dialog. Control measurement waits for a render frame after modal close.

Individual CSS `translate` preserves original DOM ownership, flex flow and existing transforms. Positions are normalized viewport centers, clamped to the visible viewport and safe-area insets. Small scaled touch controls receive a 44 CSS pixel minimum. Editor toolbar placement searches gaps around controls. There is no game-world/Babylon object in layout state.

Storage key: `xexoria_control_layout_v1`. Parsing admits only known control IDs, known profiles, version 1 and finite normalized coordinates. Corrupt or oversized data falls back to defaults. A failed Save keeps the draft open and displays an error; it never displays a current successful-save receipt. Resize/orientation interruption cancels unsaved edits.

<a id="control-layout--verification"></a>
#### Verification

- Eight Node tests pass: profile separation, validation/bounds, unavailable storage, bad writer inputs, Cancel/Reset, viewport/safe-area clamping, pointer interruption and data-reference isolation.
- TypeScript passes after the integration audit.
- `/tests/hud-control-layout-dom-review.html` is an isolated browser fixture using the production controller and in-memory storage. All 48 contracts (16 in each of 1100×700, 844×390, 390×844 iframe viewports) passed in Chrome; evidence is `planning/evidence/hud-layout-dom-20261002.{png,txt}`.
- The fixture exercises class-only modal markup, asynchronous close, real CSS geometry, flow-preserving movement, toolbar overlap, input interception, Save/recreation/Cancel/Reset/profile preservation, storage failure, resize, pending-frame cancellation and disposal. Pointer events are synthetic and pointer capture is stubbed, explicitly labelled in the results.

Native Chrome game checks passed desktop mouse dragging, keyboard reposition, Save/full reload, Cancel rollback and Reset. An 812×375 landscape viewport passed Save/reload, profile separation and Reset, with the viewport restored afterward. Receipts: `planning/evidence/hud-layout-native-20261002.json` and `hud-layout-mobile-native-20261002.json`. Physical touch, hardware safe areas, two-thumb gameplay and iPhone performance remain unqualified. A missed first Save was rejected as evidence; hidden older notices were not treated as current success.

The UI-owner files, global theme, scene, gameplay code and VFX were not changed by this workstream.


---

<a id="ui-v2-implementation"></a>
## 2026-10-01-mmo-ui-v2-report.md

Original document: `docs/reviews/2026-10-01-mmo-ui-v2-report.md`. Preserve its stated status/date; this section is not a new acceptance.

<a id="ui-v2-implementation--in-game-ui--second-visual-pass"></a>
### In-game UI — second visual pass

Started 2026-10-01; native review completed 2026-10-02. Scope: the supervisor's six UI priorities. Scene, lighting, city, 3D models and Blender assets were not edited for this visual pass. Commerce/server work is documented separately in [2026-10-01-community-systems-report.md](../reviews/historical-implementation-reports.md#community-systems).

<a id="ui-v2-implementation--changes-delivered"></a>
#### Changes delivered

1. One original 192×192 SVG bronze/slate casting, 48 px nine-slice, with a broad bevel, recessed inner edge, outer highlight, corner leaves and sapphire inlays. Panels reuse the existing original 512×512 foundation-stone texture at low contrast. No new bitmap, paid generation job or font download.
2. Larger HP/SP bars, gradient fills, outlined values, round Base/Job medallions and an ornate portrait frame. Damage ghost and low-health pulse remain event-driven; reduced motion disables them. The portrait currently contains a name initial, not final character portrait art.
3. 56 px desktop skill slots with shaded original SVG icons; conic cooldown sweep, seconds and corner key labels retained. A subtle static glow appears only on ready slots; there is no constant shimmer. Native Guard Stance displayed a server-authoritative 6 s cooldown. Arc Slash without a target correctly returned `no_target` rather than inventing a cooldown.
4. Functional rounded minimap with N/E/S/W, bilingual zone banner and a 44 px mobile zoom control outside the chart. Map projection, routes and player marker are preserved.
5. Metal tabs, readable chat text and actual desktop collapse; mobile chat becomes a focus-trapped fullscreen panel and disables combat input. Added fourth-tab Home/End/arrow-key navigation. Gold objective markers and collapsible quests; mobile landscape can show quests in the free center area without touching joystick, skills or chat.
6. Login Marcellus headers and existing OFL Noto Sans Thai body fonts, with text shadows. 1280×720 avoids the previous bottom-navigation/hotbar collision by using the existing top menu for shortcuts. Megaphone label sizing was corrected at that breakpoint.

<a id="ui-v2-implementation--files-changed-for-this-visual-pass"></a>
#### Files changed for this visual pass

- `apps/client/src/ui/astral-v2.css`, imported after the first theme in `apps/client/src/style.css`.
- `ui/PortraitMedallion.svelte`, `HudVitals.svelte`, `HudButton.svelte`, `SkillIcon.svelte`, `HudMinimap.svelte`, `Chat.svelte`.
- `ui/Hud.svelte`, `ui/bridge.svelte.ts`: development-only first-pass material comparison flag. `?uiThemeReview=astral-v1` uses the V1 material/layout tokens and shield portrait while retaining the current gameplay/commerce implementation. It is a controlled material comparison, not a restored historical application build. The query is ignored in production.
- `src/assets/ui/astral-v1/panel-frame-v2.svg`, `provenance-v2.json`.

Current gameplay and economic DTOs remain primitive values; no Babylon object is stored in Svelte state. This pass adds no per-frame DOM or JavaScript animation loop. Existing cooldown numerals update at second boundaries; CSS owns the sweep.

<a id="ui-v2-implementation--native-captures-and-verification"></a>
#### Native captures and verification

All eight formal images are real game captures from the same default follow-camera profile and settled player coordinates **0 / -20**. The server now settles this spawn there; the older September/first-pass evidence at -3/-3 is not used as a pixel-equivalence claim. Current before/after material captures are paired at the same location, viewport, hour and weather.

Camera source values unchanged: alpha −π/2, beta 1.18, radius 13, landscape FOV 1.02. No camera orbit or player-movement input was used for these pairs. Hour 14 or 22, clear weather. Other owners may update world art; this review judges UI, not scene-art equivalence.

Directory: `planning/evidence/mmo-ui-v2-20261001/`

| View | V1 material baseline | V2 candidate |
|---|---|---|
| 1920×1080 day | `before-v2-desktop-day.jpg` | `after-v2-desktop-day.jpg` |
| 1920×1080 night | `before-v2-desktop-night.jpg` | `after-v2-desktop-night.jpg` |
| 844×390 day | `before-v2-mobile-day.jpg` | `after-v2-mobile-day.jpg` |
| 844×390 night | `before-v2-mobile-night.jpg` | `after-v2-mobile-night.jpg` |

Each image has a JSON companion with actual viewport, ONLINE status, location, hour, visible panel bounds and overlap checks. Sealing validates decoded JPEG dimensions, so a transient stale browser resize capture cannot pass. An earlier unmatched interim image is named `interim-material-desktop-unmatched.jpg` and excluded from the pairs.

V2 formal captures: **0 overlaps** among visible vitals, world status, top buttons, minimap, quests, chat, hotbar/navigation or touch-control regions. Initial desktop status/minimap and mobile status/quest overlaps were found and corrected before sealing. 1280×720 has its own spacing capture. Native chat collapse, four-tab keyboard navigation, visible focus, real Guard cooldown, mobile fullscreen chat and expanded mobile quests were exercised. Economic panels and device icons have additional screenshots in `planning/evidence/community-20261001/`.

Svelte/TypeScript: **0 errors, 0 warnings**. Client tests: **179 passed** at this checkpoint. Production build succeeded into `%USERPROFILE%/Downloads/community-ui-client-build-sealed-20261002`; the existing large main-chunk warning remains. Build size and screenshot FPS are not a performance benchmark or phone qualification.

<a id="ui-v2-implementation--remaining-review"></a>
#### Remaining review

- Await Claude's visual review. This is a more detailed candidate, not an AAA-quality approval.
- Replace the initial in the portrait with approved artwork from the actual selected character. Shaded vector skill icons can later receive painted class-specific artwork.
- Physical iPhone XS/11 Pro and Android touch/performance checks are not established by viewport emulation.
- Night/world lighting and unfinished city/character art remain with their existing owners; this UI pass did not brighten or replace that scene.
- Previously completed VFX has its own [2026-10-01-codex-vfx-report.md](../reviews/historical-implementation-reports.md#vfx-implementation). Its native Babylon review remains separate; no duplicate VFX rewrite or promotion was performed for this UI review.

No commit or public deployment. Isolated preview: `http://127.0.0.2:5174/` against its own loopback test server. The main service at 3001 was left running.
