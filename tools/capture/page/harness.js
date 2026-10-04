// In-page half of tools/capture/capture.mjs. Injected with addInitScript before any page script runs.
// Config comes from window.__XEX_CAPTURE_CONFIG__ (set by an earlier init script):
//   { clock: "virtual" | "real", stepMs?: number }
//
// Virtual clock: performance.now() returns BASE + frames * STEP. It stays frozen while the page loads,
// then advances exactly one STEP per Babylon frame (engine.onBeginFrameObservable) once startClock() runs.
// Wind phase, cloud drift, water offsets and animation groups integrate engine.getDeltaTime() (measured
// from performance.now in beginFrame, before onBeginFrame fires), so every run reaches an identical
// animation state after the same number of frames. Particles and Math.random stay non-deterministic.
// All harness timing (frame intervals, CPU spans, timeouts) uses the saved real clock.
(() => {
	if (window.__xexCapture) return;
	const config = window.__XEX_CAPTURE_CONFIG__ || {};
	const realNow = performance.now.bind(performance);
	const STEP = Number(config.stepMs) > 0 ? Number(config.stepMs) : 1000 / 60;
	const BASE = 20000;
	const clock = { mode: config.clock === "virtual" ? "frozen" : "real", frames: 0, started: false, observer: null, engine: null };
	if (clock.mode !== "real") {
		const virtualNow = function now() { return BASE + clock.frames * STEP; };
		try { Object.defineProperty(performance, "now", { value: virtualNow, configurable: true, writable: true }); }
		catch { performance.now = virtualNow; }
	}
	const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
	const round = (value, digits = 3) => value === null || value === undefined || !Number.isFinite(value) ? null : Math.round(value * 10 ** digits) / 10 ** digits;
	function summarize(values) {
		const finite = values.filter(Number.isFinite).sort((a, b) => a - b);
		if (!finite.length) return { n: 0, mean: null, p50: null, p90: null, p95: null, p99: null, min: null, max: null };
		const rank = fraction => finite[Math.max(0, Math.ceil(fraction * finite.length) - 1)];
		return { n: finite.length, mean: round(finite.reduce((sum, value) => sum + value, 0) / finite.length), p50: round(rank(.5)), p90: round(rank(.9)),
			p95: round(rank(.95)), p99: round(rank(.99)), min: round(finite[0]), max: round(finite[finite.length - 1]) };
	}
	/** Robust tail: median of the p95 of `parts` consecutive sub-windows (one hitch burst moves one window, not the result). */
	function windowedP95(values, parts = 3) {
		const size = Math.floor(values.length / parts);
		if (size < 20) return null;
		const tails = [];
		for (let part = 0; part < parts; part++) { const p95 = summarize(values.slice(part * size, (part + 1) * size)).p95; if (p95 !== null) tails.push(p95); }
		tails.sort((a, b) => a - b);
		return tails.length ? { p95: tails[Math.floor(tails.length / 2)], windows: tails.length, spread: round(tails[tails.length - 1] - tails[0]) } : null;
	}
	const handle = () => window.__xexoria && window.__xexoria.scene && window.__xexoria.engine ? window.__xexoria : null;
	async function until(predicate, label, timeoutMs) {
		const started = realNow();
		for (;;) {
			let ok = false; try { ok = Boolean(predicate()); } catch { ok = false; }
			if (ok) return realNow() - started;
			if (realNow() - started > timeoutMs) throw new Error(`Timed out after ${Math.round(timeoutMs / 1000)} s waiting for ${label}`);
			await sleep(100);
		}
	}
	function frames(count, timeoutMs = 60000) {
		const { scene } = handle();
		return new Promise((resolve, reject) => {
			let seen = 0;
			const timer = setTimeout(() => { scene.onAfterRenderObservable.remove(observer); reject(new Error(`Only ${seen}/${count} frames rendered in ${timeoutMs / 1000} s`)); }, timeoutMs);
			const observer = scene.onAfterRenderObservable.add(() => { if (++seen >= count) { clearTimeout(timer); scene.onAfterRenderObservable.remove(observer); resolve(seen); } });
		});
	}
	/** Runs the virtual clock for exactly `count` rendered frames, then freezes it again. */
	function advance(count, timeoutMs = 60000) {
		const { scene } = handle();
		return new Promise((resolve, reject) => {
			if (clock.started) clock.mode = "running";
			let seen = 0;
			const timer = setTimeout(() => { scene.onAfterRenderObservable.remove(observer); if (clock.started) clock.mode = "frozen"; reject(new Error(`advance: ${seen}/${count} frames`)); }, timeoutMs);
			const observer = scene.onAfterRenderObservable.add(() => {
				if (++seen < count) return;
				if (clock.started) clock.mode = "frozen";
				clearTimeout(timer); scene.onAfterRenderObservable.remove(observer); resolve(seen);
			});
		});
	}
	function heapMB() {
		const memory = performance.memory;
		return memory && Number.isFinite(memory.usedJSHeapSize) ? round(memory.usedJSHeapSize / 1048576, 1) : null;
	}
	function gpuReader(engine) {
		try {
			if (engine.isWebGPU && engine.gpuTimeInFrameForMainPass && engine.gpuTimeInFrameForMainPass.counter) return { scope: "webgpu-main-pass", counter: () => engine.gpuTimeInFrameForMainPass.counter };
			if (!engine.isWebGPU && engine._captureGPUFrameTime && typeof engine.getGPUFrameTimeCounter === "function") return { scope: "webgl2-frame", counter: () => engine.getGPUFrameTimeCounter() };
		} catch { /* No GPU timer; CPU values are never substituted. */ }
		return null;
	}
	/** Without the lookdev SceneInstrumentation nothing resets engine._drawCalls per frame; install one reset. */
	function ensureDrawReset() {
		const { scene, engine } = handle();
		if (clock.drawReset || window.__xexoriaLookdev || !engine._drawCalls || typeof engine._drawCalls.fetchNewFrame !== "function") return;
		clock.drawReset = scene.onBeforeAnimationsObservable.add(() => engine._drawCalls.fetchNewFrame());
	}
	/** Cumulative compile counters: Babylon effects (both backends) and WebGPU render-pipeline cache misses. */
	function compileCounters(engine) {
		let effects = null, pipelines = null;
		try { effects = Object.keys(engine._compiledEffects || {}).length; } catch { effects = null; }
		try { const cache = engine._cacheRenderPipeline; pipelines = cache ? Object.getPrototypeOf(cache).constructor.NumCacheMiss ?? null : null; } catch { pipelines = null; }
		return { effects, pipelines };
	}
	function loadingScreenVisible() {
		const node = document.querySelector(".scene-loading");
		return !!node && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden";
	}
	/** Stable-frame shutter: N consecutive frames with identical draw/mesh/index/effect/pipeline/pending counts. */
	function settle({ stableFrames = 30, maxFrames = 600, timeoutMs = 60000 } = {}) {
		const { scene, engine } = handle();
		ensureDrawReset();
		return new Promise(resolve => {
			let seen = 0, run = 0, previous = "";
			const finish = settled => { clearTimeout(timer); scene.onAfterRenderObservable.remove(observer); resolve({ settled, frames: seen, stableRun: run, signature: previous }); };
			const timer = setTimeout(() => finish(false), timeoutMs);
			const observer = scene.onAfterRenderObservable.add(() => {
				seen++;
				const counters = compileCounters(engine), pending = typeof scene.getWaitingItemsCount === "function" ? scene.getWaitingItemsCount() : 0;
				const signature = [engine._drawCalls ? engine._drawCalls.current : -1, scene.getActiveMeshes().length, scene.getActiveIndices(), counters.effects, counters.pipelines, pending].join("|");
				run = signature === previous ? run + 1 : 1; previous = signature;
				if (run >= stableFrames && pending === 0) finish(true);
				else if (seen >= maxFrames) finish(false);
			});
		});
	}
	/** Temporal burst with the clock running: per-pixel luma envelope (max-min) and direction reversals
	 * (steps under 4/255 ignored), sampled at `scale` of the drawing buffer inside onEndFrame. */
	function temporalBurst({ frames: count = 24, scale = .5, step = 4 } = {}) {
		const { engine } = handle();
		const source = engine.getRenderingCanvas();
		const width = Math.max(16, Math.round(source.width * scale)), height = Math.max(16, Math.round(source.height * scale)), n = width * height;
		const copy = document.createElement("canvas"); copy.width = width; copy.height = height;
		const context = copy.getContext("2d", { willReadFrequently: true });
		const min = new Uint8Array(n).fill(255), max = new Uint8Array(n), last = new Uint8Array(n), dir = new Int8Array(n), toggles = new Uint8Array(n);
		let captured = 0;
		return new Promise((resolve, reject) => {
			if (clock.started) clock.mode = "running";
			const timer = setTimeout(() => { engine.onEndFrameObservable.remove(observer); if (clock.started) clock.mode = "frozen"; reject(new Error("Temporal burst timed out")); }, 60000);
			const observer = engine.onEndFrameObservable.add(() => {
				try {
					context.drawImage(source, 0, 0, width, height);
					const data = context.getImageData(0, 0, width, height).data;
					for (let i = 0, p = 0; p < n; i += 4, p++) {
						const y = (54 * data[i] + 183 * data[i + 1] + 19 * data[i + 2]) >> 8;
						if (y < min[p]) min[p] = y; if (y > max[p]) max[p] = y;
						if (captured > 0) {
							const delta = y - last[p];
							if (delta >= step || delta <= -step) {
								const sign = delta > 0 ? 1 : -1;
								if (dir[p] !== 0 && sign !== dir[p] && toggles[p] < 255) toggles[p]++;
								dir[p] = sign; last[p] = y;
							}
						} else last[p] = y;
					}
					captured++;
				} catch (error) { clearTimeout(timer); engine.onEndFrameObservable.remove(observer); if (clock.started) clock.mode = "frozen"; reject(error); return; }
				if (captured >= count) {
					if (clock.started) clock.mode = "frozen";
					clearTimeout(timer); engine.onEndFrameObservable.remove(observer);
					const envelope = new Uint8ClampedArray(n * 4), toggleImage = new Uint8ClampedArray(n * 4);
					let sum = 0, over8 = 0, togglers = 0; const histogram = new Uint32Array(256);
					for (let p = 0; p < n; p++) {
						const e = max[p] - min[p]; sum += e; histogram[e]++; if (e > 8) over8++; if (toggles[p] >= 2) togglers++;
						envelope[p * 4] = envelope[p * 4 + 1] = envelope[p * 4 + 2] = e; envelope[p * 4 + 3] = 255;
						toggleImage[p * 4] = toggleImage[p * 4 + 1] = toggleImage[p * 4 + 2] = Math.min(255, toggles[p] * 16); toggleImage[p * 4 + 3] = 255;
					}
					let acc = 0, p99 = 0; for (let v = 0; v < 256; v++) { acc += histogram[v]; if (acc >= .99 * n) { p99 = v; break; } }
					const encode = pixels => { context.putImageData(new ImageData(pixels, width, height), 0, 0); return copy.toDataURL("image/png"); };
					resolve({ frames: captured, width, height, scale, step, meanEnvelope: round(sum / n, 3), p99Envelope: p99, pctEnvelopeOver8: round(over8 * 100 / n, 3),
						pctTogglers: round(togglers * 100 / n, 3), toggleScale: "toggles x16 (2 reversals = 32)", envelopePng: encode(envelope), togglesPng: encode(toggleImage) });
				}
			});
		});
	}
	function info() {
		const { scene, engine } = handle();
		const canvas = engine.getRenderingCanvas();
		let adapter = null; try { adapter = engine.getInfo ? engine.getInfo() : engine.getGlInfo ? engine.getGlInfo() : null; } catch { adapter = null; }
		const lookdev = window.__xexoriaLookdev ? window.__xexoriaLookdev.identity() : null;
		const camera = scene.activeCamera;
		const target = camera && typeof camera.getTarget === "function" ? camera.getTarget() : null;
		const features = engine.isWebGPU && Array.isArray(engine.enabledExtensions) ? engine.enabledExtensions.slice() : null;
		return {
			backend: engine.isWebGPU ? "WebGPU" : `WebGL${engine.webGLVersion || ""}`, adapter,
			features, timestampQuery: features ? features.includes("timestamp-query") : null,
			renderWidth: engine.getRenderWidth(), renderHeight: engine.getRenderHeight(), hardwareScalingLevel: engine.getHardwareScalingLevel(),
			canvasCss: canvas ? { width: canvas.clientWidth, height: canvas.clientHeight } : null, devicePixelRatio: window.devicePixelRatio,
			gameFrameCap: clock.capSaved ? clock.gameMaxFps ?? null : engine.maxFPS ?? null, maxFpsNow: engine.maxFPS ?? null,
			lookdev, camera: camera ? { name: camera.name, alpha: round(camera.alpha, 4), beta: round(camera.beta, 4), radius: round(camera.radius, 3), fov: round(camera.fov, 4),
				target: target ? { x: round(target.x, 3), y: round(target.y, 3), z: round(target.z, 3) } : null } : null,
			meshes: scene.meshes.length, materials: scene.materials.length, textures: scene.textures.length, compile: compileCounters(engine),
			pendingItems: typeof scene.getWaitingItemsCount === "function" ? scene.getWaitingItemsCount() : null, loadingScreen: loadingScreenVisible(),
			visibility: document.visibilityState, focused: document.hasFocus(), userAgent: navigator.userAgent,
			clock: { mode: config.clock === "virtual" ? "virtual" : "real", stepMs: round(STEP, 4), frames: clock.frames },
		};
	}
	async function waitReady({ lookdev = true, fsr = false, timeoutMs = 180000, settleFrames = 30 } = {}) {
		const started = realNow(), waited = {};
		waited.handleMs = round(await until(() => handle(), "window.__xexoria (needs a build with DEV review hooks)", timeoutMs), 0);
		const { scene, engine } = handle();
		if (lookdev) waited.lookdevMs = round(await until(() => window.__xexoriaLookdev, "the lookdev sandbox (world load)", timeoutMs), 0);
		waited.framesMs = round(await until(() => scene.getFrameId() > 30, "30 rendered frames", timeoutMs), 0);
		let sceneReady = true;
		await Promise.race([scene.whenReadyAsync().catch(() => { sceneReady = false; }), sleep(45000).then(() => { sceneReady = false; })]);
		waited.sceneReady = sceneReady;
		waited.pendingMs = round(await until(() => (typeof scene.getWaitingItemsCount === "function" ? scene.getWaitingItemsCount() : 0) === 0, "pending scene loads", 60000).catch(() => -1), 0);
		if (fsr) waited.fsrMs = round(await until(() => !/no fsr param/.test(window.__xexoriaLookdev ? window.__xexoriaLookdev.identity().upscaling : ""), "the FSR render-scaling handle", 30000).catch(() => -1), 0);
		await frames(settleFrames);
		clock.engine = engine;
		waited.totalMs = round(realNow() - started, 0);
		return waited;
	}
	/** Installs the per-frame tick but keeps time frozen; runView() runs it only inside its sample window,
	 * so the Node round-trips between views never add frames of animation. */
	function startClock() {
		const { engine } = handle();
		if (config.clock !== "virtual") return { mode: "real" };
		if (!clock.observer) clock.observer = engine.onBeginFrameObservable.add(() => { if (clock.mode === "running") clock.frames++; });
		clock.started = true;
		return { mode: "virtual", frames: clock.frames };
	}
	function setFrameCap(mode) {
		const { engine } = handle();
		if (!clock.capSaved) { clock.capSaved = true; clock.gameMaxFps = engine.maxFPS; }
		if (mode === "uncapped") engine.maxFPS = undefined;
		else if (mode === "game") engine.maxFPS = clock.gameMaxFps;
		return engine.maxFPS ?? null;
	}
	/** Records `count` frames after `warmup` frames with the real clock; optionally freezes the virtual clock at the end. */
	function sample({ warmup, count, freezeAtEnd, timeoutMs = 180000 }) {
		const { scene, engine } = handle();
		const gpu = gpuReader(engine);
		const columns = { frameMs: [], cpuMs: [], gpuMs: [], drawCalls: [], activeMeshes: [], activeTriangles: [], particles: [] };
		let seen = 0, frameStart = 0, lastEnd = 0, gpuSeen = -1, heapMax = null, heapStart = null, sampleStart = 0, compileStart = null, hiddenFrames = 0;
		const draws = engine._drawCalls;
		ensureDrawReset();
		return new Promise((resolve, reject) => {
			// Same task as the observer registration below: no frame can render between these lines.
			if (freezeAtEnd && clock.started) clock.mode = "running";
			const cleanup = () => { scene.onBeforeAnimationsObservable.remove(before); scene.onAfterRenderObservable.remove(after); clearTimeout(timer); };
			const timer = setTimeout(() => { cleanup(); if (clock.started) clock.mode = "frozen"; reject(new Error(`Sampling timed out: ${seen}/${warmup + count} frames in ${timeoutMs / 1000} s`)); }, timeoutMs);
			const before = scene.onBeforeAnimationsObservable.add(() => { frameStart = realNow(); });
			const after = scene.onAfterRenderObservable.add(() => {
				const end = realNow(); seen++;
				let gpuMs = NaN;
				if (gpu) { try { const counter = gpu.counter(); if (counter && counter.count !== gpuSeen && counter.current > 0) { gpuSeen = counter.count; gpuMs = counter.current / 1e6; } } catch { /* keep NaN */ } }
				if (seen === warmup) { heapStart = heapMB(); sampleStart = end; compileStart = compileCounters(engine); }
				if (seen > warmup) {
					if (document.visibilityState !== "visible") hiddenFrames++;
					columns.frameMs.push(lastEnd ? end - lastEnd : NaN); columns.cpuMs.push(frameStart ? end - frameStart : NaN); columns.gpuMs.push(gpuMs);
					columns.drawCalls.push(draws ? draws.current : NaN); columns.activeMeshes.push(scene.getActiveMeshes().length);
					columns.activeTriangles.push(scene.getActiveIndices() / 3); columns.particles.push(scene.getActiveParticles());
					if ((seen - warmup) % 30 === 0) { const heap = heapMB(); if (heap !== null) heapMax = Math.max(heapMax ?? 0, heap); }
				}
				lastEnd = end;
				if (seen >= warmup + count) {
					if (freezeAtEnd && clock.started) clock.mode = "frozen";
					cleanup();
					const wallMs = end - sampleStart, heapEnd = heapMB(), compileEnd = compileCounters(engine);
					const delta = key => compileStart && compileStart[key] !== null && compileEnd[key] !== null ? compileEnd[key] - compileStart[key] : null;
					resolve({ frames: { warmup, sampled: count }, sampleWallMs: round(wallMs, 1), fps: round(count * 1000 / wallMs, 2),
						hitches50: columns.frameMs.filter(value => value > 50).length, hitches100: columns.frameMs.filter(value => value > 100).length,
						compilesDuringSample: { effects: delta("effects"), pipelines: delta("pipelines") }, hiddenFrames,
						frameMs: summarize(columns.frameMs), cpuMs: summarize(columns.cpuMs), gpuMs: gpu ? summarize(columns.gpuMs) : null, gpuScope: gpu ? gpu.scope : "unavailable",
						robust: { frameP95: windowedP95(columns.frameMs), cpuP95: windowedP95(columns.cpuMs), gpuP95: gpu ? windowedP95(columns.gpuMs.filter(Number.isFinite)) : null },
						drawCalls: summarize(columns.drawCalls), activeMeshes: summarize(columns.activeMeshes), activeTriangles: summarize(columns.activeTriangles), particles: summarize(columns.particles),
						heapMB: { start: heapStart, end: heapEnd, max: heapMax === null ? heapEnd : Math.max(heapMax, heapEnd ?? 0) },
						visibleThroughout: document.visibilityState === "visible", focusedAtEnd: document.hasFocus(), clockFrameAtEnd: clock.frames });
				}
			});
		});
	}
	async function imageStats(dataUrl) {
		const image = new Image(); image.src = dataUrl; await image.decode();
		const canvas = document.createElement("canvas"); canvas.width = 96; canvas.height = 54;
		const context = canvas.getContext("2d", { willReadFrequently: true }); context.drawImage(image, 0, 0, 96, 54);
		const data = context.getImageData(0, 0, 96, 54).data;
		let sum = 0, sum2 = 0, alpha = 0; const n = data.length / 4;
		for (let i = 0; i < data.length; i += 4) { const y = .2126 * data[i] + .7152 * data[i + 1] + .0722 * data[i + 2]; sum += y; sum2 += y * y; alpha += data[i + 3]; }
		const mean = sum / n;
		return { meanLuma: round(mean, 2), stdLuma: round(Math.sqrt(Math.max(0, sum2 / n - mean * mean)), 2), meanAlpha: round(alpha / n, 1) };
	}
	/** Copies the drawing buffer inside onEndFrame (same task as the render, before presentation) over opaque black. */
	function canvasShot() {
		const { engine } = handle();
		const source = engine.getRenderingCanvas();
		return new Promise((resolve, reject) => {
			const timer = setTimeout(() => { engine.onEndFrameObservable.remove(observer); reject(new Error("No frame ended within 15 s")); }, 15000);
			const observer = engine.onEndFrameObservable.addOnce(() => {
				clearTimeout(timer);
				try {
					const copy = document.createElement("canvas"); copy.width = source.width; copy.height = source.height;
					const context = copy.getContext("2d"); context.fillStyle = "#000"; context.fillRect(0, 0, copy.width, copy.height); context.drawImage(source, 0, 0);
					resolve({ dataUrl: copy.toDataURL("image/png"), width: copy.width, height: copy.height });
				} catch (error) { reject(error); }
			});
		});
	}
	const withTimeout = (promise, ms, label) => Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error(`${label} timed out after ${ms / 1000} s`)), ms))]);
	/** Canvas readback first; the lookdev render-target PNG if that is blank. A frame that is blank on every path is
	 * returned flagged blank (BLANK_RENDER) instead of failing the load. */
	async function shot({ method = "canvas", maxSide = 4096, rttTimeoutMs = 25000 } = {}) {
		const attempts = method === "rtt" ? ["rtt"] : method === "canvas-only" ? ["canvas"] : ["canvas", "rtt"];
		const notes = [];
		let blankResult = null;
		for (const attempt of attempts) {
			try {
				let result;
				if (attempt === "canvas") result = await canvasShot();
				else {
					const lookdev = window.__xexoriaLookdev;
					if (!lookdev) { notes.push("rtt: no lookdev sandbox"); continue; }
					if (clock.rttBroken) { notes.push("rtt: skipped (timed out earlier on this page)"); continue; }
					if (lookdev.identity().busy) { notes.push("rtt: sandbox busy"); continue; }
					let rtt;
					try { rtt = await withTimeout(lookdev.renderTargetPng(maxSide), rttTimeoutMs, "render-target screenshot"); }
					catch (error) { clock.rttBroken = true; throw error; }
					result = { dataUrl: `data:image/png;base64,${rtt.png}`, width: rtt.width, height: rtt.height };
				}
				const stats = await imageStats(result.dataUrl);
				if (stats.stdLuma >= 1.0) return { ...result, method: attempt, stats, blank: false, notes };
				notes.push(`${attempt}: blank frame (luma mean ${stats.meanLuma}, std ${stats.stdLuma}, alpha ${stats.meanAlpha})`);
				blankResult ??= { ...result, method: attempt, stats, blank: true };
			} catch (error) { notes.push(`${attempt}: ${String(error && error.message || error).slice(0, 200)}`); }
		}
		if (blankResult) return { ...blankResult, notes };
		throw new Error(`No screenshot method succeeded: ${notes.join("; ")}`);
	}
	async function runView({ view, warmupFrames = 60, sampleFrames = 300, frameCap = "uncapped", shotMethod = "canvas", maxSide = 4096, stableFrames = 30, temporal = null }) {
		const lookdev = window.__xexoriaLookdev;
		if (view !== "page") {
			if (!lookdev) throw new Error("Locked views need the lookdev sandbox (?lookdev=1 in a DEV-hook build)");
			lookdev.selectCamera(view);
			if (lookdev.currentView() !== view) throw new Error(`Lookdev did not select ${view} (busy?)`);
		}
		const cap = setFrameCap(frameCap);
		// The virtual clock runs only during this window and stays frozen through the shot and until the next view.
		const metrics = await sample({ warmup: warmupFrames, count: sampleFrames, freezeAtEnd: config.clock === "virtual" });
		// Clock frozen: wait until the frame itself stops changing (async shader compiles, streaming) before the shutter.
		const settled = await settle({ stableFrames });
		const frameAtShot = clock.frames;
		const image = await shot({ method: shotMethod, maxSide });
		let burst = null;
		if (temporal && image.method === "canvas" && !image.blank) { try { burst = await temporalBurst(temporal); } catch (error) { burst = { error: String(error && error.message || error) }; } }
		else if (temporal) burst = { error: image.blank ? "skipped: blank frame" : "temporal burst needs canvas readback" };
		// Keep the frame sequence identical whether or not the burst ran: advance the clock by the same number of frames.
		if (temporal && (!burst || burst.error) && clock.started) await advance(temporal.frames ?? 24);
		return { view, metrics, settled, frameCapNow: cap, identity: info(), image, temporal: burst, clock: { mode: config.clock === "virtual" ? "virtual" : "real", frameAtShot, framesAfter: clock.frames, stepMs: round(STEP, 4) } };
	}
	/** A view the run does not capture still consumes its frames, so later views keep the baseline's animation phase. */
	async function skipView({ view, frames: count }) {
		const lookdev = window.__xexoriaLookdev;
		if (lookdev && view !== "page") lookdev.selectCamera(view);
		if (config.clock === "virtual" && clock.started) await advance(count);
		return { view, skippedFrames: count, framesAfter: clock.frames };
	}
	window.__xexCapture = { version: 1, realNow, info, waitReady, startClock, setFrameCap, sample, settle, shot, temporalBurst, runView, skipView, frames: count => frames(count),
		clockState: () => ({ ...clock, engine: undefined, observer: undefined }) };
})();
