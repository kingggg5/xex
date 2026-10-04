# tools/capture: before/after capture, compare, reference match, responsive audit

Babylon captures of the real game (production bundle) with frame metrics, a pixel and metric compare, a perf ledger,
a reference-match mode for the gauntlet loop, and a responsive device audit. No installs: Node, the cached Playwright,
headed Chrome, and Python with numpy, PIL and scipy.

## One command: before/after

```powershell
node tools/capture/ab.mjs --label 2026-10-03-my-change            # build current tree, capture, compare to 2026-10-02-A
# report: planning/evidence/captures/compare-2026-10-02-A-vs-2026-10-03-my-change/report.html
```
`--only city-noon` limits the shots; `--baseline <label>` picks another baseline. The A/A noise floor in
`planning/evidence/capture-baseline-20261002/compare-A-vs-A-rerun/report.json` is applied automatically.

## Pieces

| Step | Command |
|---|---|
| Build | `node tools/capture/build.mjs --label L` → `<scratchpad>/dist-capture-L` plus `capture-build.json` (dist and source hashes, git state) |
| Capture | `node tools/capture/capture.mjs --label L --shots tools/capture/shots/baseline.json --dist <dir> --out <runs dir>` (or `--url http://…`) |
| Compare | `python tools/capture/compare.py --before <run> --after <run> --out <dir> [--noise <A/A report.json>] [--aa]` |
| Ledger | `node tools/capture/perf-ledger.mjs append <run> [--noise …]` · `compare --baseline A [--candidate B]` · `noise --aa <report.json>` |
| Reference match | `python tools/capture/refmatch.py --reference ref.jpg --capture shot.png --out <dir> [--exclude-ref x0,y0,x1,y1 …]` |
| Fix requests | `python tools/capture/annotate.py --image shot.png --spec issues.json --out annotated.png` |
| Responsive | `node tools/capture/responsive-audit.mjs --dist <dir> --out <dir> [--devices iphone-11,ipad]` |

Flags: `--dry-run` lists the expanded shots; `--resume` continues a run after a session budget stop; `--views`,
`--warmup`, `--samples`, `--vsync off`, `--clock real`, `--no-temporal` and `--no-ledger` are also available.

- **`--views` keeps animation phase.** Views you leave out still consume their frames (`skipView`), so a subset run
  lands on the same animation frame as the full baseline. `compare.py` checks `frameAtShot` on both sides and reports
  "phase mismatch" instead of "changed" when they differ.
- **Keep counts equal.** `--warmup`, `--samples` and `--no-temporal` change the frame count. Use the baseline's values
  when you want a visual compare.

## Build: production with the DEV review hooks

`build.mjs` runs the client prebuild scripts, then `vite build` with `apps/client/vite.config.ts` in production mode
(minified, `NODE_ENV=production`, production Svelte). The only change from a plain `vite build` is that `import.meta.env.DEV`
is defined `true`. The lookdev sandbox, the locked cameras and `window.__xexoria` are DEV-gated, so a plain build cannot
produce locked views. Each DEV hook acts only when its URL parameter is present. `--plain` builds without the define.

## Shot lists (`shots/*.json`)

`scenes` (lookdev presets: `city` → `?lookdev=1&set=city`, `sunmeadow` → `set=terrain`; `spawn` is the offline preview with
the follow camera), `times` (dawn 6, noon 12, dusk 18, night 0), `defaults`, and `groups`. Array values in a group expand
as a cartesian product over `scene`, `time`, `renderer` (`webgpu` | `webgl2`), `weather`, `tier` (`lookdevTier`),
`fsr` (`?fsr=`), `viewport` (`{width,height,dpr,mobile,touch,userAgent}`) and `lodDistance` (40 | 120).
One page load captures all `views` of a group. `baseline.json` is the master-plan proof set (32 shots); `extras.json`
holds dawn/dusk, FSR, tiers, a phone viewport, LOD, weather and spawn. Party and dense-combat scenes need the game
server and are not listed.

## How a shot is taken (determinism)

- **Virtual clock** (`page/harness.js`, `clock: "virtual"`). `performance.now()` is frozen while the page loads, then it
  advances exactly 1/60 s per Babylon frame, and only inside each view's sample window. Wind, water, clouds and
  animation groups integrate `getDeltaTime()`, so every run reaches the same state after the same number of frames.
  Particles and `Math.random` stay non-deterministic, and the A/A floor absorbs them. All timing uses the real clock.
- **Per view:** select the locked camera, 60 warm-up frames, then 450 measured frames (real-clock frame interval,
  CPU `scene.render` span, GPU timer where available, draw calls, active meshes and triangles, JS heap, hitches over
  50 and 100 ms, compiles during the window). The headline p95 is the **median of three 150-frame sub-window p95s**,
  so one hitch burst cannot move it. The pooled p95 is kept beside it. The first A/A with a pooled p95 over 300 frames
  flagged 7 of 32 identical shots, with deltas up to 5.1 ms. Then the clock freezes, and a **settle shutter** waits for 30 frames with
  identical draw, mesh, index, effect, pipeline and pending-load counts. The shutter copies the drawing buffer inside
  `onEndFrame` (canvas readback, works on WebGPU and WebGL2, HUD excluded); a blank frame falls back to the lookdev
  render-target PNG. A **temporal burst** follows: 24 frames at half resolution give a per-pixel luma envelope and
  direction-reversal counts, which catch shimmer, grass or water crawl and LOD pops.
- Frame metrics are **uncapped** (`engine.maxFPS` unset during sampling; the game caps at 60), so they show headroom.
  With vsync on, intervals cannot go below the display period (5.6 ms at 180 Hz). Keep vsync on: with `--vsync off`
  the GPU queue fills, and city p95 doubles (27–36 ms against 16–19 ms) while CPU p95 balloons.
- **WebGPU shots are blank today, and the harness says so.** Every WebGPU frame's command buffer is invalid
  (`Vertex buffer count (9) exceeds the maximum number of vertex buffers (8)` on the main-pass pipeline, plus a WGSL
  error), so nothing is drawn. These shots are marked `BLANK_RENDER` + `GPU_VALIDATION_ERRORS`, the root errors are
  recorded, and the ledger refuses them. WebGPU frame times then measure CPU submission only.
- **Verdicts per shot:** `OK`, `BLANK_RENDER`, `GPU_VALIDATION_ERRORS`, `FALLBACK_BACKEND`, `HIDDEN_OR_UNFOCUSED`,
  `LOADING_SCREEN`, `SCENE_NOT_READY`, `SCENE_NOT_SETTLED`, plus warnings (`LOAD_DEGRADED`, `COMPILES_DURING_SAMPLE`,
  `UNFOCUSED_WINDOW`). Invalid shots are refused by the ledger.
- **Render-target fallback:** the lookdev render-target PNG now uses its own canvas encoder. Babylon's DumpTools
  compiles a "pass" shader that production bundles do not ship (it fetched `index.html` and never resolved), which also
  broke the sandbox's "Capture baseline" buttons outside the dev server.

## Compare

Per shot: SSIM (luma, Gaussian window), PSNR, MAE and RMSE, max Δ, changed area (Δ > 16/255) and strong area (Δ > 48),
an amplified heatmap with hotspot boxes, and the change shape. A tie flip is a few pixels; scattered is shimmer or
particles; solid is a content, LOD or culling change. Metric deltas and the temporal-burst delta follow.
- **Visual verdicts:** identical, within noise, minor change, changed. With `--noise`, the thresholds rise to 1.5× the
  shot's A/A value.
- **Perf flag:** frame p95 worse by more than 10 % or more than 1 ms, after subtracting the A/A floor.
  - Never raised on an invalid capture (blank or GPU-invalid).
  - Downgraded to **unqualified** when either load ran on a busy PC: Blender running at the start or end, or the
    CPU at least 60 % busy before our page opened. `capture.mjs` records machine load per load.
  - On 2026-10-02, Blender jobs from another agent moved identical-build p95 by −2.6 to +3.2 ms. Pause Blender while
    a measurement holds the GPU lock if you need qualified perf deltas.
- `report.html` holds a before/after slider, the heatmap and the deltas per shot, and works on a phone.
- Run an A/A self-compare (`--aa`) after any harness change; its `report.json` is the noise floor.

## Ledger (`planning/perf-ledger.jsonl`, schema `xexoria.ledger/1`)

- One row per shot: build hash, git head and dirty count, scenario, device class, backend, settings, preflight,
  frames (wall, CPU and GPU p50 and p95, hitches), counts and the noise floor.
- The verdict checks the master-plan p95 budget (16.7 ms desktop High, 33.3 ms phone).
- `compare` prints the deltas with the noise subtracted. Rows from a dirty tree are never picked as `last-clean`.

## Reference match (gauntlet loop Stage C)

Gates come from `docs/plans/2026-10-02-reference-gauntlet-loop.md`:
- mean luma ±0.05;
- contrast (p90−p10) ±0.05;
- histogram EMD ≤ 0.06;
- saturation ±0.06;
- palette ΔE00 ≤ 8 (6 k-means colours matched with the Hungarian method);
- silhouette IoU ≥ 0.85 when masks or alpha exist.

Use `--exclude-ref` and `--exclude-cap` boxes to drop HUD or UI regions. The art rubric stays manual.

## Responsive audit

- **Devices:** the matrix in `responsive-audit.mjs` (iPhone SE, 11, 16 Pro and Pro Max, iPad, iPad mini, Galaxy A54 /
  Pixel 7, a small Android phone, Z Fold inner, and desktops from 1366 to 3440).
- **Sequence:** touch devices go portrait (boot gate) → landscape (game boots) → portrait → landscape. Desktops are
  landscape only.
- **Checks:** page scroll, canvas fill, off-viewport and safe-area intrusions, overlapping HUD widgets, touch targets
  under 44×44, text under 11 px, touch controls present, and layout drift after rotation.
- **Outputs:** CSS-pixel screenshots, annotated issue screenshots, `issues.json` (exact selectors, viewport and measured
  values, ranked groups) and a contact sheet.
- **Chrome emulation is not Safari.** 100vh/dvh and toolbars, safe-area values, text autosizing, rAF throttling (Low
  Power Mode, the 60 Hz cap) and WebGPU availability all differ. Confirm on devices.

## Rules the tools enforce

- **GPU lock:** created exclusively, retried every 30 s, deleted and checked afterwards. Sessions stop at 14 min by
  default (hard maximum 15); resume with `--resume`.
- **Resources:** at least 1.5 GB of free RAM before Chrome starts.
- **Processes:** `vite preview` on port 4310 is started and stopped by PID.
- **No server:** `/healthz` is answered with 503, so nothing depends on the Rust server.
