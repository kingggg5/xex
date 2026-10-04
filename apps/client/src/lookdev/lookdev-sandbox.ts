import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { CreateScreenshotUsingRenderTargetAsync } from "@babylonjs/core/Misc/screenshotTools";
import type { Scene } from "@babylonjs/core/scene";
import { createLookdevMetrics, type LookdevMetricsSnapshot } from "./lookdev-metrics";
import { createLookdevCameraLock } from "./lookdev-camera";
import { getRenderScaling } from "../render-scaling";
import { LOOKDEV_VIEWS, clonePrimitiveMetadata, compareLookdevPacks, createEvidenceZip, evidenceSlug, lockedCamera,
	type LockedCamera, type LookdevPoint, type LookdevView } from "./lookdev-data.mjs";

type Primitive = string | number | boolean | null;
export type LookdevMetadata = { [key: string]: Primitive | Primitive[] | LookdevMetadata };
export interface LookdevSettings { tier: "low" | "medium" | "high" | "ultra"; hours: number | null; weather: string; upscaling?: string }
export interface LookdevHypothesis { change: string; predictedGain: string; predictedCost: string; falsification: string }
export interface LookdevCapture {
	view: LookdevView; camera: LockedCamera; metrics: LookdevMetricsSnapshot;
	baselineWallTimeMs: number; sampleTimeoutMs: number;
	renderIdentity: { backend: string; width: number; height: number; hardwareScalingLevel: number; gpuScope: string; visible: boolean; focused: boolean; devicePixelRatio: number;
		/** 3D scene size before FSR upscaling; equals width/height when render scaling is off. */
		sceneWidth: number; sceneHeight: number; upscaling: string };
	imageSize: { width: number; height: number }; image: string; sha256: string | null; bytes: number;
}
export interface LookdevCaptureManifest {
	schema: "xexoria-lookdev-v0"; pillar: string; cycle: string; variant: "A" | "B";
	capturedAt: string; settings: LookdevSettings; metadata: LookdevMetadata; lodDistance: 40 | 120 | null;
	capturePhaseFrozen: boolean; metricsWindowDescription: string; captureDescription: string;
	hypothesis: LookdevHypothesis; captures: LookdevCapture[];
	gpuMemoryEstimate: { bytes: number | null; basis: string };
}
export interface LookdevOptions {
	scene: Scene; target: LookdevPoint; camera?: ArcRotateCamera; cameraTargets?: Partial<Record<LookdevView, LookdevPoint>>;
	pillar: string; cycle?: string; variant?: "A" | "B"; lodDistance?: 40 | 120 | null;
	getSettings(): LookdevSettings;
	applySettings?(change: Partial<LookdevSettings>): void | Promise<void>;
	supportedWeathers?: readonly string[];
	metadata?: LookdevMetadata | (() => LookdevMetadata);
	ready?(): Promise<void>;
	/** Reset/freeze the existing shared clock for the screenshot, then return its release function. */
	freezeForCapture?(view: LookdevView): (() => void) | Promise<() => void>;
	gpuMemoryEstimate?(): { bytes: number | null; basis: string };
	hypothesis?: Partial<LookdevHypothesis>; sampleCapacity?: number; samplesPerCamera?: number; requireFocus?: boolean;
	/** Actual render sampling can wait longer for slow debug scenes; never changes sample counts or cadence. */
	sampleTimeoutMs?: number;
	onSnapshot?(snapshot: LookdevMetricsSnapshot): void;
	onCapture?(manifest: LookdevCaptureManifest): void;
}
/** Automation handle for tools/capture. Exists only while a DEV lookdev sandbox is installed; adds no per-frame work. */
export interface LookdevHarnessHandle {
	readonly version: 1;
	readonly views: readonly LookdevView[];
	selectCamera(view: LookdevView): void;
	currentView(): LookdevView;
	camera(view?: LookdevView): LockedCamera;
	snapshot(): LookdevMetricsSnapshot;
	identity(): { pillar: string; cycle: string; view: LookdevView; lodDistance: 40 | 120 | null; settings: LookdevSettings; backend: string; renderWidth: number; renderHeight: number;
		hardwareScalingLevel: number; devicePixelRatio: number; sceneWidth: number; sceneHeight: number; upscaling: string; busy: boolean };
	/** Same render-target PNG as captureAll (camera post-processes, no HUD) for the current view; sampling pauses while it renders. */
	renderTargetPng(maxSide?: number): Promise<{ png: string; width: number; height: number; view: LookdevView }>;
}
declare global { interface Window { __xexoriaLookdev?: LookdevHarnessHandle } }

const css = `
#lookdev-panel{position:fixed;left:12px;top:max(12px,env(safe-area-inset-top));z-index:1100;width:min(390px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;padding:12px;background:#0b1d30f5;color:#e5e9ef;border:1px solid #baa276;border-radius:7px;font:12px/1.5 system-ui;pointer-events:auto}
#lookdev-panel h2{font-size:16px;margin:0 0 6px;color:#f1dcaa}#lookdev-panel p{margin:6px 0}#lookdev-panel label{display:flex;align-items:center;gap:8px;margin:6px 0;justify-content:space-between}#lookdev-panel button,#lookdev-panel select{min-height:36px;border:1px solid #a98b56;border-radius:4px;background:#19334e;color:#f3e5c4;padding:6px 9px;font:inherit}#lookdev-panel button:disabled,#lookdev-panel select:disabled{opacity:.55}#lookdev-panel input,#lookdev-panel textarea{min-height:36px;min-width:0;width:100%;border:1px solid #6f8fba;background:#102b46;color:#f4ecd8;font:inherit;padding:6px;resize:vertical}#lookdev-panel .lookdev-row{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}#lookdev-panel pre{margin:8px 0;white-space:pre-wrap;font:11px/1.5 ui-monospace,monospace}#lookdev-panel details{border-top:1px solid #a48a5880;padding-top:7px;margin-top:8px}#lookdev-panel summary{cursor:pointer;color:#f1dcaa}#lookdev-panel .lookdev-limits{font-size:11px;color:#c2d0df}#lookdev-panel :focus-visible{outline:3px solid #b8dcff;outline-offset:2px}@media(any-pointer:coarse){#lookdev-panel button,#lookdev-panel select{min-height:44px}}
`;

/** DEV measuring instrument. The host owns loading, follow/auth suppression and all visual settings. */
export function installLookdevSandbox(options: LookdevOptions) {
	const { scene } = options, engine = scene.getEngine();
	const sampleTimeoutMs = Number.isFinite(options.sampleTimeoutMs)
		? Math.max(15_000, Math.min(120_000, Math.floor(options.sampleTimeoutMs!))) : 15_000;
	const originalCamera = scene.activeCamera;
	const productionCamera = options.camera ?? (originalCamera instanceof ArcRotateCamera ? originalCamera : null);
	if (!productionCamera) throw new Error("Lookdev requires the production ArcRotateCamera to preserve its actual post-process pipeline");
	const camera: ArcRotateCamera = productionCamera;
	const metrics = createLookdevMetrics(scene, { capacity: options.sampleCapacity, requireFocus: options.requireFocus });
	const events = new AbortController();
	const style = document.createElement("style"); style.textContent = css; document.head.append(style);
	const panel = document.createElement("section"); panel.id = "lookdev-panel"; panel.setAttribute("aria-label", "Lookdev sandbox");
	const title = document.createElement("h2"); title.textContent = `Lookdev · ${evidenceSlug(options.pillar, "water")}`;
	const status = document.createElement("p"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
	const readout = document.createElement("pre"); readout.setAttribute("aria-label", "Lookdev render metrics");
	const limits = document.createElement("p"); limits.className = "lookdev-limits";
	limits.textContent = "Production scene, locked review cameras. Short static baselines do not qualify combat, phones or 500 players. GPU memory values are estimates.";
	if (sampleTimeoutMs > 15_000) limits.textContent += ` Slow-debug sampling can wait ${sampleTimeoutMs / 1000} s per camera; the exported wall time and actual frame intervals remain unqualified performance observations.`;
	let view: LookdevView = "player", lodDistance = options.lodDistance ?? null;
	let busy = false, disposed = false, lastPublished = 0;
	let lastArchiveUrl: string | null = null;
	let baseline: LookdevCaptureManifest | null = null, candidate: LookdevCaptureManifest | null = null;
	const hypothesis: LookdevHypothesis = { change: options.hypothesis?.change ?? "", predictedGain: options.hypothesis?.predictedGain ?? "", predictedCost: options.hypothesis?.predictedCost ?? "", falsification: options.hypothesis?.falsification ?? "" };
	const controls: Array<HTMLButtonElement | HTMLSelectElement> = [];
	function message(text: string) { if (!disposed) status.textContent = text; }
	/** `?fsr=` render scaling as installed by scene.ts; absent means native rendering. */
	function upscaling() {
		const stats = getRenderScaling(scene)?.stats();
		const label = !stats ? "native (no fsr param)" : stats.active
			? `FSR1 x${stats.scaleFactor} sharp ${stats.sharpnessStops} MSAA ${stats.samples}${stats.adaptive ? " adaptive" : ""}`
			: stats.mode === "off" ? "native (fsr=off)" : `native (FSR inactive: ${stats.reason})`;
		return { label, sceneWidth: stats?.renderWidth ?? engine.getRenderWidth(true), sceneHeight: stats?.renderHeight ?? engine.getRenderHeight(true) };
	}
	const button = (label: string, action: () => unknown | Promise<unknown>) => {
		const node = document.createElement("button"); node.type = "button"; node.textContent = label; node.setAttribute("aria-label", label);
		node.addEventListener("click", () => { void Promise.resolve(action()).catch(error => message(`Review failed: ${error instanceof Error ? error.message : "unknown error"}`)); }, { signal: events.signal }); controls.push(node); return node;
	};
	const cameraRow = document.createElement("div"); cameraRow.className = "lookdev-row";
	for (const key of LOOKDEV_VIEWS) {
		const node = button(key === "player" ? "Player · 13 m" : key[0].toUpperCase() + key.slice(1), () => selectCamera(key)); node.dataset.view = key; cameraRow.append(node);
	}
	function select(label: string, choices: Array<{ value: string; label: string; disabled?: boolean }>, initial: string, action: (value: string) => void | Promise<void>, disabled = false) {
		const row = document.createElement("label"); row.append(document.createTextNode(label));
		const node = document.createElement("select"); node.setAttribute("aria-label", label);
		for (const choice of choices) { const item = new Option(choice.label, choice.value); item.disabled = !!choice.disabled; node.append(item); }
		node.value = initial; node.disabled = disabled; node.dataset.hostDisabled = String(disabled);
		node.addEventListener("change", () => { void Promise.resolve(action(node.value)).catch(error => message(`Setting was not changed: ${error instanceof Error ? error.message : "unknown error"}`)); }, { signal: events.signal }); controls.push(node); row.append(node); return row;
	}
	const settings = options.getSettings();
	const settingsBox = document.createElement("details"), settingsTitle = document.createElement("summary"); settingsTitle.textContent = "Quality, time and weather"; settingsBox.append(settingsTitle);
	async function changeSettings(change: Partial<LookdevSettings>) { if (!options.applySettings) return; await options.applySettings(change); metrics.reset(); message("Settings changed; warming a new baseline."); }
	settingsBox.append(select("Quality tier", ["low", "medium", "high", "ultra"].map(value => ({ value, label: value[0].toUpperCase() + value.slice(1) })), settings.tier, value => changeSettings({ tier: value as LookdevSettings["tier"] }), !options.applySettings));
	const times = [{ value: "6", label: "Dawn · 06:00" }, { value: "12", label: "Noon · 12:00" }, { value: "18", label: "Dusk · 18:00" }, { value: "0", label: "Night · 00:00" }, { value: "", label: "Current host clock" }];
	if (settings.hours !== null && ![0, 6, 12, 18].includes(settings.hours)) times.push({ value: String(settings.hours), label: `Host time · ${settings.hours.toFixed(2)}` });
	settingsBox.append(select("Time of day", times, settings.hours === null ? "" : String(settings.hours), value => { if (value !== "") return changeSettings({ hours: Number(value) }); }, !options.applySettings));
	const weathers = options.supportedWeathers ?? ["clear", "cloudy", "rain", "fog"];
	settingsBox.append(select("Weather", ["clear", "cloudy", "rain", "snow", "fog"].map(value => ({ value, label: `${value === "cloudy" ? "Overcast" : value[0].toUpperCase() + value.slice(1)}${weathers.includes(value) ? "" : " · unavailable"}`, disabled: !weathers.includes(value) })), settings.weather, value => changeSettings({ weather: value }), !options.applySettings));
	const query = new URLSearchParams(location.search), fsrValues = ["off", "1.3", "1.5", "1.7", "2"];
	const reloadWith = (key: string, value: string) => { const url = new URL(location.href); url.searchParams.set(key, value); location.assign(url); };
	settingsBox.append(select("Upscaling (FSR 1)", [{ value: "off", label: "Native · no upscaling" }, { value: "1.3", label: "FSR 1.3 · Ultra Quality" }, { value: "1.5", label: "FSR 1.5 · Quality" },
		{ value: "1.7", label: "FSR 1.7 · Balanced" }, { value: "2", label: "FSR 2.0 · Performance" }], fsrValues.includes(query.get("fsr") ?? "") ? query.get("fsr")! : "off", value => reloadWith("fsr", value)));
	settingsBox.append(select("Render scale", [{ value: "0", label: "Fixed" }, { value: "1", label: "Adaptive (FSR only)" }], query.get("auto") === "1" ? "1" : "0", value => reloadWith("auto", value)));
	settingsBox.append(select("LOD review distance", [{ value: "", label: "Normal four cameras" }, { value: "40", label: "40 m · LOD review" }, { value: "120", label: "120 m · distant HLOD review" }], lodDistance === null ? "" : String(lodDistance), value => { lodDistance = value === "40" ? 40 : value === "120" ? 120 : null; selectCamera(view); }));
	const exportRow = document.createElement("div"); exportRow.className = "lookdev-row";
	exportRow.append(button("Capture baseline A · four views", () => captureAll("A")), button("Capture candidate B · four views", () => captureAll("B")));
	const discovery = document.createElement("details"), discoveryTitle = document.createElement("summary"); discoveryTitle.textContent = "One-hypothesis cycle"; discovery.append(discoveryTitle);
	for (const [key, label] of [["change", "Single change"], ["predictedGain", "Predicted visual gain"], ["predictedCost", "Predicted cost"], ["falsification", "What would falsify it?"]] as const) {
		const field = document.createElement("textarea"); field.rows = 2; field.maxLength = 800; field.value = hypothesis[key]; field.setAttribute("aria-label", label);
		field.addEventListener("input", () => { hypothesis[key] = field.value.slice(0, 800); }, { signal: events.signal });
		const row = document.createElement("label"); row.style.display = "block"; row.textContent = label; row.append(field); discovery.append(row);
	}
	let decision = "ITERATE"; let rationale = "";
	discovery.append(select("Decision", ["ADOPT", "ITERATE", "DROP", "BLOCKED"].map(value => ({ value, label: value })), decision, value => { decision = value; }));
	const reason = document.createElement("textarea"); reason.rows = 2; reason.maxLength = 800; reason.placeholder = "Evidence and remaining limits"; reason.setAttribute("aria-label", "Decision evidence and limits");
	reason.addEventListener("input", () => { rationale = reason.value.slice(0, 800); }, { signal: events.signal }); discovery.append(reason);
	discovery.append(button("Export cycle decision", () => {
		const comparison = compareLookdevPacks(baseline, candidate);
		const report = { schema: "xexoria-lookdev-cycle-v0", pillar: evidenceSlug(options.pillar), cycle: evidenceSlug(options.cycle), hypothesis: { ...hypothesis }, decision,
			rationale, baseline: baseline ? `${baseline.variant}-manifest.json` : null, candidate: candidate ? `${candidate.variant}-manifest.json` : null, comparison,
			integration: decision === "ADOPT" ? "Review decision only. Claude visual approval and root integration remain required." : "No live integration was performed." };
		download(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }), `${evidenceSlug(options.pillar)}-${evidenceSlug(options.cycle)}-decision.json`);
		message(comparison.comparable ? "Decision exported with matched A/B metric deltas." : `Decision exported; A/B is not comparable: ${comparison.mismatches.join("; ")}`);
	}));
	panel.append(title, cameraRow, readout, status, exportRow, settingsBox, discovery, limits); document.body.append(panel);
	function cameraContract(key = view): LockedCamera { return lockedCamera(key, options.cameraTargets?.[key] ?? options.target, lodDistance); }
	const cameraLock = createLookdevCameraLock(scene, camera, cameraContract);
	function selectCamera(key: LookdevView) {
		if (disposed || busy) return; view = key; const spec = cameraContract(key);
		cameraLock.apply(); metrics.reset();
		for (const node of cameraRow.querySelectorAll("button")) {
			node.setAttribute("aria-pressed", String(node.dataset.view === key));
			if (node.dataset.view === "player") { const label = lodDistance === null ? "Player · 13 m" : `Player · ${lodDistance} m · LOD review`; node.textContent = label; node.setAttribute("aria-label", label); }
		}
		message(`${key} camera locked at ${spec.radius} m. Warming frame samples.`);
	}
	function memoryEstimate() {
		try {
			const estimate = options.gpuMemoryEstimate?.();
			if (estimate && Number.isFinite(estimate.bytes) && estimate.bytes! >= 0) return { bytes: estimate.bytes, basis: String(estimate.basis).slice(0, 500) };
		} catch { return { bytes: null, basis: "Host GPU-memory estimate failed; no measured allocation value is substituted." }; }
		return { bytes: null, basis: "No GPU allocation measurement is exposed; the host did not provide a bounded estimate." };
	}
	function publish() {
		if (disposed) return; const time = performance.now(); if (time - lastPublished < 1000) return; lastPublished = time;
		const snapshot = metrics.snapshot(), estimate = memoryEstimate(), w = snapshot.window, actualSettings = options.getSettings(), scaled = upscaling();
		const ms = (value: number | null) => value === null ? "warming" : `${value.toFixed(1)} ms`;
		readout.textContent = `${snapshot.backend} · ${snapshot.renderWidth}×${snapshot.renderHeight} · ${view} ${camera.radius} m\n`
			+ `${actualSettings.tier} · ${actualSettings.hours === null ? "host clock" : `${actualSettings.hours.toFixed(2)} h`} · ${actualSettings.weather}\n`
			+ `Frames retained ${w.retained}/${w.capacity} · warmup ${snapshot.warmupRemaining}\nFrame p50/p95 ${ms(w.frameIntervalMs.p50)} / ${ms(w.frameIntervalMs.p95)}\n`
			+ `CPU scene p50/p95 ${ms(w.cpuSceneMs.p50)} / ${ms(w.cpuSceneMs.p95)}\nGPU ${snapshot.gpuStatus === "unavailable" ? "Unavailable" : snapshot.gpuStatus === "stale" ? `Stale · last update ${Math.round((snapshot.gpuFreshAgeMs ?? 0) / 1000)} s ago` : `${snapshot.gpuScope} p50/p95 ${ms(w.gpuMs.p50)} / ${ms(w.gpuMs.p95)} · n=${w.gpuMs.n}`}\n`
			+ `Draw submissions ${snapshot.current?.drawCalls ?? "—"} · active scene meshes ${snapshot.current?.activeMeshes ?? "—"}\nSubmitted indices/3 ${snapshot.current?.activeTriangles ?? "—"} · particle render count ${snapshot.current?.particles ?? "—"}\n`
			+ `GPU memory estimate ${estimate.bytes === null ? "Unavailable" : `~${Math.round(estimate.bytes / 1048576)} MiB`}\nVisible ${snapshot.visible} · focused ${snapshot.focused}`;
		readout.textContent += `\nWindow focus ${w.focus.focusedFrames} focused / ${w.focus.unfocusedFrames} unfocused · ${snapshot.focusPolicy}`;
		readout.textContent += `\nUpscale ${scaled.label} · scene ${scaled.sceneWidth}×${scaled.sceneHeight} → output ${snapshot.renderWidth}×${snapshot.renderHeight}`;
		readout.dataset.metrics = JSON.stringify(snapshot);
		try { options.onSnapshot?.(snapshot); } catch { message("Host snapshot callback failed; the render counters remain active."); }
	}
	const publishObserver = scene.onAfterRenderObservable.add(publish);
	function download(blob: Blob, filename: string) {
		if (lastArchiveUrl) URL.revokeObjectURL(lastArchiveUrl); lastArchiveUrl = URL.createObjectURL(blob);
		const link = document.createElement("a"); link.href = lastArchiveUrl; link.download = filename; document.body.append(link); link.click(); link.remove();
	}
	/** PNG encoder for the render-target pixels. Babylon's default DumpTools encoder compiles a "pass" shader that
	 * production bundles do not ship (the request returns index.html), so the capture never resolved there. */
	function encodePng(width: number, height: number, data: ArrayBufferView, success?: (data: string | ArrayBuffer) => void, mimeType = "image/png", _fileName?: string, invertY = false) {
		const source = new Uint8ClampedArray(data.buffer, data.byteOffset, width * height * 4);
		const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
		const context = canvas.getContext("2d"); if (!context) throw new Error("No 2D canvas for the screenshot encoder");
		const image = context.createImageData(width, height), row = width * 4;
		if (invertY) for (let y = 0; y < height; y++) image.data.set(source.subarray((height - 1 - y) * row, (height - y) * row), y * row);
		else image.data.set(source);
		context.putImageData(image, 0, 0);
		success?.(canvas.toDataURL(mimeType));
	}
	/** Base64 PNG payload of one render-target screenshot through the production camera's post-processes. */
	async function screenshotPayload(imageSize: { width: number; height: number }): Promise<string> {
		const data = await CreateScreenshotUsingRenderTargetAsync(engine, camera, imageSize, "image/png", 1, false, undefined, true, true, true, undefined, texture => { texture.useCameraPostProcesses = true; }, encodePng);
		if (disposed) throw new Error("Review disposed during screenshot");
		const prefix = "data:image/png;base64,"; if (!data.startsWith(prefix) || data.length > 14 * 1024 * 1024) throw new Error("Unexpected/oversized screenshot data");
		return data.slice(prefix.length);
	}
	async function waitForSamples(): Promise<number> {
		const requested = Number.isFinite(options.samplesPerCamera) ? Math.floor(options.samplesPerCamera!) : 60;
		const minimum = Math.max(30, Math.min(metrics.snapshot().window.capacity, requested));
		const start = performance.now();
		while (metrics.snapshot().window.retained < minimum) {
			if (disposed || events.signal.aborted) throw new Error("Review disposed");
			if (performance.now() - start > sampleTimeoutMs) throw new Error(`Baseline timed out after ${sampleTimeoutMs / 1000} s; keep this browser tab visible${options.requireFocus ? " and focused" : ""} and the scene rendering`);
			await new Promise(resolve => window.setTimeout(resolve, 100));
		}
		return performance.now() - start;
	}
	async function captureAll(variant: "A" | "B" = options.variant ?? "A"): Promise<LookdevCaptureManifest> {
		if (busy || disposed) throw new Error("A capture is already running or the review is disposed");
		if (variant !== "A" && variant !== "B") throw new Error("Capture variant must be A or B");
		busy = true; for (const control of controls) control.disabled = true;
		const savedView = view, captures: LookdevCapture[] = [], files: Array<{ name: string; bytes: Uint8Array }> = [];
		const root = `lookdev/${evidenceSlug(options.pillar, "water")}/${evidenceSlug(options.cycle)}`;
		let completedMessage: string | null = null;
		try {
			await options.ready?.(); await scene.whenReadyAsync();
			const metadataValue = typeof options.metadata === "function" ? options.metadata() : options.metadata ?? {};
			const metadata = clonePrimitiveMetadata(metadataValue) as LookdevMetadata;
			const manifest: LookdevCaptureManifest = { schema: "xexoria-lookdev-v0", pillar: evidenceSlug(options.pillar, "water"), cycle: evidenceSlug(options.cycle), variant,
				capturedAt: new Date().toISOString(), settings: { ...options.getSettings(), upscaling: upscaling().label }, metadata, lodDistance,
				capturePhaseFrozen: !!options.freezeForCapture, metricsWindowDescription: `Per camera: 30 warmup renders, then a bounded ${options.requireFocus ? "visible-and-focused" : "visible-only; focus exposure recorded"} sample window. Maximum actual-render wait is ${sampleTimeoutMs / 1000} s; per-camera wall time is recorded. A longer debug wait does not change sample counts, synthesize renders or establish gameplay FPS. Screenshot/offscreen render frames are excluded. GPU values are fresh asynchronous updates, not paired with each CPU frame. Submitted indices / 3 includes counted passes/instances, not unique visible triangles. Short static lookdev baselines are not gameplay or device qualification.`,
				captureDescription: "Sequential Babylon render-target PNGs from the production scene and its existing camera post-processes. Browser HUD is excluded. Asset hashes/device/phase seed are host-provided identities, not independently inferred.",
				hypothesis: { ...hypothesis }, captures, gpuMemoryEstimate: memoryEstimate() };
			for (const key of LOOKDEV_VIEWS) {
				busy = false; selectCamera(key); busy = true;
				message(`Capturing ${variant} · ${key}: collecting actual renders, up to ${sampleTimeoutMs / 1000} s. This debug capture does not qualify gameplay performance.`);
				const baselineWallTimeMs = await waitForSamples();
				const measured = metrics.snapshot();
				if (!measured.visible) throw new Error("Tab was hidden before the screenshot; keep the review visible and retry");
				metrics.setPaused(true);
				let release: (() => void) | undefined;
				try {
					release = await options.freezeForCapture?.(key);
					const scale = Math.min(1, 1920 / Math.max(measured.renderWidth, measured.renderHeight));
					const imageSize = { width: Math.max(1, Math.round(measured.renderWidth * scale)), height: Math.max(1, Math.round(measured.renderHeight * scale)) };
					const binary = atob(await screenshotPayload(imageSize)), bytes = Uint8Array.from(binary, value => value.charCodeAt(0));
					const digest = crypto.subtle ? Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))).map(value => value.toString(16).padStart(2, "0")).join("") : null;
					const image = `${variant}-${key}.png`, scaled = upscaling(); files.push({ name: `${root}/${image}`, bytes });
					captures.push({ view: key, camera: cameraContract(key), metrics: measured, baselineWallTimeMs, sampleTimeoutMs,
						renderIdentity: { backend: measured.backend, width: measured.renderWidth, height: measured.renderHeight, hardwareScalingLevel: measured.hardwareScalingLevel, gpuScope: measured.gpuScope,
							visible: measured.visible, focused: measured.focused, devicePixelRatio: window.devicePixelRatio,
							sceneWidth: scaled.sceneWidth, sceneHeight: scaled.sceneHeight, upscaling: scaled.label }, imageSize, image, sha256: digest, bytes: bytes.length });
				} finally { try { release?.(); } finally { metrics.setPaused(false); } }
			}
			files.push({ name: `${root}/${variant}-manifest.json`, bytes: new TextEncoder().encode(JSON.stringify(manifest, null, 2)) });
			const zip = createEvidenceZip(files);
			download(new Blob([zip as Uint8Array<ArrayBuffer>], { type: "application/zip" }), `lookdev-${manifest.pillar}-${manifest.cycle}-${variant}.zip`);
			if (variant === "A") baseline = manifest; else candidate = manifest;
			completedMessage = `Four ${variant} views and manifest exported. Browser chooses the download folder; import the ZIP into planning/evidence locally.`;
			try { options.onCapture?.(manifest); } catch { completedMessage += " Host capture callback failed; the exported ZIP is still available."; }
			return manifest;
		} finally {
			busy = false; for (const control of controls) control.disabled = control.dataset.hostDisabled === "true";
			if (!disposed) selectCamera(savedView);
			if (completedMessage) message(completedMessage);
		}
	}
	const harness: LookdevHarnessHandle = {
		version: 1, views: LOOKDEV_VIEWS,
		selectCamera(key) { if (!LOOKDEV_VIEWS.includes(key)) throw new Error(`Unknown lookdev view ${String(key)}`); selectCamera(key); },
		currentView: () => view,
		camera: (key = view) => cameraContract(key),
		snapshot: metrics.snapshot,
		identity() {
			const scaled = upscaling();
			return { pillar: evidenceSlug(options.pillar, "water"), cycle: evidenceSlug(options.cycle), view, lodDistance, settings: { ...options.getSettings() },
				backend: metrics.snapshot().backend, renderWidth: engine.getRenderWidth(), renderHeight: engine.getRenderHeight(), hardwareScalingLevel: engine.getHardwareScalingLevel(),
				devicePixelRatio: window.devicePixelRatio, sceneWidth: scaled.sceneWidth, sceneHeight: scaled.sceneHeight, upscaling: scaled.label, busy };
		},
		async renderTargetPng(maxSide = 1920) {
			if (busy || disposed) throw new Error("A capture is already running or the review is disposed");
			busy = true; metrics.setPaused(true);
			let release: (() => void) | undefined;
			try {
				release = await options.freezeForCapture?.(view);
				const width = engine.getRenderWidth(), height = engine.getRenderHeight();
				const scale = Math.min(1, Math.max(1, Math.floor(maxSide)) / Math.max(width, height));
				const imageSize = { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
				return { png: await screenshotPayload(imageSize), ...imageSize, view };
			} finally { try { release?.(); } finally { metrics.setPaused(false); busy = false; } }
		},
	};
	function dispose() {
		if (disposed) return; disposed = true; events.abort(); scene.onAfterRenderObservable.remove(publishObserver); scene.onDisposeObservable.remove(disposalObserver); metrics.dispose(); cameraLock.dispose();
		panel.remove(); style.remove(); if (lastArchiveUrl) URL.revokeObjectURL(lastArchiveUrl); lastArchiveUrl = null;
		if (window.__xexoriaLookdev === harness) delete window.__xexoriaLookdev;
	}
	const disposalObserver = scene.onDisposeObservable.addOnce(dispose);
	selectCamera("player"); publish();
	window.__xexoriaLookdev = harness;
	return { selectCamera, snapshot: metrics.snapshot, captureAll, dispose };
}
