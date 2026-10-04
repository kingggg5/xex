// Before/after capture harness: locked-view PNGs + frame metrics per shot, a contact sheet and a perf-ledger line.
//   node tools/capture/capture.mjs --label <label> --shots <shots.json> (--dist <build dir> | --url <http://...>)
//        [--out <dir>] [--only a,b] [--resume] [--max-minutes 14] [--vsync on|off] [--clock virtual|real]
//        [--warmup N] [--samples N] [--shot-method canvas|rtt] [--lock <path>] [--no-lock] [--no-ledger] [--dry-run]
// See tools/capture/README.md.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { DEFAULT_LOCK, LEDGER, REPO, TOOL_DIR, acquireGpuLock, decodeDataUrl, ensureFreeRam, gitState, launchChrome, log, machineInfo, machineLoad,
	parseArgs, readBuildReceipt, releaseGpuLock, runPython, slug, startPreview, treeHash } from "./lib.mjs";
import { appendRun, captureVerdict } from "./perf-ledger.mjs";

const HARNESS = join(TOOL_DIR, "page", "harness.js");
const AXES = ["scene", "time", "renderer", "weather", "tier", "fsr", "viewport", "lodDistance"];
const args = parseArgs(process.argv.slice(2), { booleans: ["resume", "noLock", "noLedger", "ledgerPartial", "dryRun", "noTemporal"] });
if (!args.label || !args.shots || (!args.dist && !args.url && !args.dryRun)) {
	console.error("usage: node tools/capture/capture.mjs --label <label> --shots <shots.json> (--dist <dir> | --url <url>) [--out <dir>] [--only a,b] [--resume] [--dry-run]");
	process.exit(2);
}
const label = slug(args.label);
const shotsPath = resolve(args.shots);
const shotList = JSON.parse(readFileSync(shotsPath, "utf8"));
const outRoot = resolve(args.out ?? join(REPO, "planning", "evidence", "captures"));
const runDir = join(outRoot, label), shotsDir = join(runDir, "shots");
const maxMinutes = Math.min(15, Number(args.maxMinutes ?? 14));
const vsync = args.vsync === "off" ? "off" : "on";

// ---------- shot list ----------
const viewportId = vp => vp.name ?? `${vp.width}x${vp.height}@${vp.dpr ?? 1}${vp.touch ? "t" : ""}`;
function cartesian(axes) {
	return axes.reduce((combos, [axis, values]) => combos.flatMap(combo => values.map(value => ({ ...combo, [axis]: value }))), [{}]);
}
function expand(list) {
	const defaults = { viewport: { width: 1920, height: 1080, dpr: 1 }, weather: "clear", tier: null, fsr: null, lodDistance: null, renderer: "webgpu", time: "noon",
		warmupFrames: 60, sampleFrames: 300, frameCap: "uncapped", clock: "virtual", shotMethod: "canvas", maxSide: 4096, stableFrames: 30, temporal: null,
		views: ["player", "side", "close", "elevated"], ...list.defaults };
	const loads = [], seen = new Set();
	for (const group of list.groups ?? []) {
		const merged = { ...defaults, ...group };
		for (const combo of cartesian(AXES.map(axis => [axis, Array.isArray(merged[axis]) ? merged[axis] : [merged[axis]]]))) {
			const scene = list.scenes?.[combo.scene];
			if (!scene) throw new Error(`Unknown scene "${combo.scene}" in group ${group.name}`);
			const hour = typeof combo.time === "number" ? combo.time : list.times?.[combo.time];
			if (!Number.isFinite(hour)) throw new Error(`Unknown time "${combo.time}" in group ${group.name}`);
			const kind = scene.kind ?? "lookdev";
			// `allViews` keeps the shot list's order: skipped views still consume their frames (same animation phase).
			const allViews = kind === "page" ? ["page"] : merged.views;
			const views = kind === "page" ? ["page"] : args.views ? allViews.filter(view => String(args.views).split(",").map(part => part.trim()).includes(view)) : allViews;
			if (!views.length) continue;
			const load = { group: group.name, ...combo, hour, kind, views, allViews, deterministic: scene.deterministic !== false,
				warmupFrames: Number(args.warmup ?? merged.warmupFrames), sampleFrames: Number(args.samples ?? merged.sampleFrames), frameCap: merged.frameCap,
				clock: args.clock ?? merged.clock, shotMethod: args.shotMethod ?? merged.shotMethod, maxSide: merged.maxSide, fsrAuto: !!merged.fsrAuto,
				stableFrames: Number(merged.stableFrames), temporal: args.noTemporal ? null : merged.temporal,
				query: { ...scene.query, ...merged.query }, sceneLabel: scene.label ?? combo.scene };
			const parts = [load.scene, load.time, load.renderer];
			if (load.tier) parts.push(`tier-${load.tier}`);
			if (load.fsr) parts.push(`fsr${load.fsr}${load.fsrAuto ? "a" : ""}`);
			if (load.weather !== "clear") parts.push(load.weather);
			if (load.lodDistance) parts.push(`lod${load.lodDistance}`);
			if (viewportId(load.viewport) !== "1920x1080@1") parts.push(viewportId(load.viewport));
			load.id = slug(parts.join("-"));
			if (seen.has(load.id)) throw new Error(`Duplicate load ${load.id}`);
			seen.add(load.id); loads.push(load);
		}
	}
	return loads;
}
const shotId = (load, view) => `${load.id}-${view}`;
function loadUrl(base, load) {
	const query = new URLSearchParams(load.query);
	query.set("envHour", String(load.hour)); query.set("envWeather", load.weather); query.set("renderer", load.renderer);
	if (load.tier) query.set("lookdevTier", load.tier);
	if (load.fsr) { query.set("fsr", String(load.fsr)); if (load.fsrAuto) query.set("auto", "1"); }
	if (load.lodDistance) query.set("lodDistance", String(load.lodDistance));
	return `${base.replace(/\/$/, "")}/?${query}`;
}

const only = args.only ? String(args.only).split(",").map(part => part.trim()).filter(Boolean) : null;
const loads = expand(shotList).filter(load => !only || only.some(part => load.id.includes(part)));
if (!loads.length) throw new Error("The shot list (after --only) selects no loads");
if (args.dryRun) {
	for (const load of loads) console.log(load.id.padEnd(48), load.views.join(","), loadUrl(args.url ?? "http://127.0.0.1:4310", load));
	console.log(`${loads.length} loads, ${loads.reduce((sum, load) => sum + load.views.length, 0)} shots`);
	process.exit(0);
}

// ---------- run record ----------
mkdirSync(shotsDir, { recursive: true });
const runPath = join(runDir, "run.json");
let run = existsSync(runPath) ? JSON.parse(readFileSync(runPath, "utf8")) : null;
if (run && !args.resume) throw new Error(`Run ${label} already exists at ${runDir}; pass --resume to continue it or choose a new label`);
const dist = args.dist ? resolve(args.dist) : null;
const receipt = dist ? readBuildReceipt(dist) : null;
const build = receipt
	? { hash: receipt.buildHash, distSha256: receipt.distSha256, sourceSha256: receipt.sourceSha256, devHooks: receipt.devHooks, builtAt: receipt.builtAt, vite: receipt.vite, dist, gitAtBuild: receipt.git }
	: dist ? (() => { const tree = treeHash(dist); return { hash: tree.sha256.slice(0, 16), distSha256: tree.sha256, sourceSha256: null, devHooks: null, dist }; })()
	: { hash: null, url: args.url, note: "served by an external URL; build identity unknown" };
run ??= { schema: "xexoria-capture-run/1", label, createdAt: new Date().toISOString(), shotList: { path: relative(REPO, shotsPath).replace(/\\/g, "/"), name: shotList.name ?? null,
	sha256: createHash("sha256").update(readFileSync(shotsPath)).digest("hex").slice(0, 16) }, build, git: gitState(), machine: machineInfo(), sessions: [], loads: {}, shots: {} };
if (run.build?.hash && build.hash && run.build.hash !== build.hash) throw new Error(`Resume refused: run ${label} was captured on build ${run.build.hash}, not ${build.hash}`);
const save = () => writeFileSync(runPath, JSON.stringify(run, null, 1));
const pending = loads.filter(load => !load.views.every(view => run.shots[shotId(load, view)]?.image));
log(`${label}: ${loads.length} loads selected, ${pending.length} pending; run dir ${relative(REPO, runDir)}`);

function shotSummary(shot) {
	const m = shot.metrics, id = shot.identity;
	return { id: shot.id, load: shot.load, scene: shot.scene, view: shot.view, time: shot.time, hour: shot.hour, weather: shot.weather, renderer: shot.renderer.actual,
		tier: shot.tier.actual, fsr: shot.fsr.requested, upscaling: shot.fsr.upscaling, viewport: viewportId(shot.viewport), image: shot.image.file, imageSha256: shot.image.sha256,
		method: shot.image.method, width: shot.image.width, height: shot.image.height, blank: shot.image.blank,
		// Headline p95 = median of three sub-window p95s (robust to one hitch burst); pooled p95 kept beside it.
		frameP50: m.frameMs.p50, frameP95: m.robust?.frameP95?.p95 ?? m.frameMs.p95, frameP95Pooled: m.frameMs.p95, frameP95Spread: m.robust?.frameP95?.spread ?? null, frameP99: m.frameMs.p99,
		cpuP50: m.cpuMs.p50, cpuP95: m.robust?.cpuP95?.p95 ?? m.cpuMs.p95, cpuP95Pooled: m.cpuMs.p95,
		gpuP50: m.gpuMs?.p50 ?? null, gpuP95: m.robust?.gpuP95?.p95 ?? m.gpuMs?.p95 ?? null, gpuP95Pooled: m.gpuMs?.p95 ?? null, gpuN: m.gpuMs?.n ?? 0, gpuScope: m.gpuScope, fps: m.fps,
		drawCalls: m.drawCalls.p50, activeMeshes: m.activeMeshes.p50, triangles: m.activeTriangles.p50, particles: m.particles.p50, heapMB: m.heapMB.end,
		renderSize: `${id.renderWidth}x${id.renderHeight}`, sceneSize: id.lookdev ? `${id.lookdev.sceneWidth}x${id.lookdev.sceneHeight}` : null, dpr: id.devicePixelRatio,
		adapter: id.adapter ? `${id.adapter.vendor} · ${id.adapter.renderer}` : null, frameAtShot: shot.clock.frameAtShot, capturedAt: shot.capturedAt };
}

async function captureLoad(browser, base, load) {
	const vp = load.viewport, url = loadUrl(base, load), started = Date.now();
	const record = { id: load.id, url, startedAt: new Date().toISOString(), views: load.views, deterministic: load.deterministic, machineLoad: await machineLoad(800) };
	const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.dpr ?? 1, isMobile: !!vp.mobile, hasTouch: !!vp.touch,
		...(vp.userAgent ? { userAgent: vp.userAgent } : {}) });
	const errors = [];
	try {
		// Captures never depend on the Rust server: lookdev skips the login gate and /healthz fails fast.
		await context.route("**/healthz", route => route.fulfill({ status: 503, contentType: "text/plain", body: "capture harness: server intentionally absent" }));
		await context.addInitScript(config => { window.__XEX_CAPTURE_CONFIG__ = config; }, { clock: load.clock });
		await context.addInitScript({ path: HARNESS });
		const page = await context.newPage();
		record.failedRequests = [];
		record.gpuErrors = { count: 0, roots: [] };
		page.on("console", message => {
			const text = message.text();
			if (/WebGPU uncaptured error|Invalid CommandBuffer|invalid due to a previous error|Error while parsing WGSL|exceeds the maximum|GPUValidationError/.test(text)) {
				record.gpuErrors.count++;
				const root = text.replace(/^BJS - \[[^\]]*\]: (\[Frame \d+\] )?/, "").replace(/WebGPU uncaptured error( \(\d+\))?: \[object GPUValidationError\] - /, "").slice(0, 400);
				if (!/invalid due to a previous error|too many warnings/.test(root) && record.gpuErrors.roots.length < 6 && !record.gpuErrors.roots.some(known => known.slice(0, 120) === root.slice(0, 120))) record.gpuErrors.roots.push(root);
				return;
			}
			if (message.type() === "error" && errors.length < 40 && !/healthz|503/.test(text)) errors.push(text.slice(0, 300));
		});
		page.on("pageerror", error => { if (errors.length < 40) errors.push(`pageerror: ${String(error).slice(0, 300)}`); });
		page.on("requestfailed", request => { if (!/\/healthz/.test(request.url()) && record.failedRequests.length < 40) record.failedRequests.push(`${request.failure()?.errorText ?? "failed"} ${request.url().slice(0, 200)}`); });
		page.on("response", response => { if (response.status() >= 400 && !/\/healthz/.test(response.url()) && record.failedRequests.length < 40) record.failedRequests.push(`${response.status()} ${response.url().slice(0, 200)}`); });
		await page.goto(url, { waitUntil: "load", timeout: 120000 });
		await page.bringToFront();
		record.waited = await page.evaluate(options => window.__xexCapture.waitReady(options), { lookdev: load.kind === "lookdev", fsr: !!load.fsr, timeoutMs: 180000 });
		const identity = await page.evaluate(() => window.__xexCapture.info());
		record.backend = identity.backend; record.adapter = identity.adapter; record.timestampQuery = identity.timestampQuery;
		if ((load.renderer === "webgpu") !== (identity.backend === "WebGPU")) { record.verdict = "FALLBACK_BACKEND"; throw new Error(`FALLBACK_BACKEND: requested ${load.renderer} but the page runs ${identity.backend}`); }
		if (identity.visibility !== "visible") { record.verdict = "HIDDEN_OR_UNFOCUSED"; throw new Error("HIDDEN_OR_UNFOCUSED: the page is not visible"); }
		await page.evaluate(() => window.__xexCapture.startClock());
		for (const view of load.allViews) {
			if (!load.views.includes(view)) {
				const frames = load.warmupFrames + load.sampleFrames + (load.temporal ? Number(load.temporal.frames ?? 24) : 0);
				await page.evaluate(options => window.__xexCapture.skipView(options), { view, frames });
				continue;
			}
			const id = shotId(load, view), viewStarted = Date.now();
			const result = await page.evaluate(options => window.__xexCapture.runView(options),
				{ view, warmupFrames: load.warmupFrames, sampleFrames: load.sampleFrames, frameCap: load.frameCap, shotMethod: load.shotMethod, maxSide: load.maxSide,
					stableFrames: load.stableFrames, temporal: load.temporal });
			const png = decodeDataUrl(result.image.dataUrl);
			writeFileSync(join(shotsDir, `${id}.png`), png);
			let temporal = null;
			if (result.temporal && !result.temporal.error) {
				const { envelopePng, togglesPng, ...summary } = result.temporal;
				writeFileSync(join(shotsDir, `${id}.envelope.png`), decodeDataUrl(envelopePng));
				writeFileSync(join(shotsDir, `${id}.toggles.png`), decodeDataUrl(togglesPng));
				temporal = { ...summary, envelopeFile: `shots/${id}.envelope.png`, togglesFile: `shots/${id}.toggles.png` };
			} else if (result.temporal) temporal = result.temporal;
			const shot = { schema: "xexoria-capture-shot/1", id, label, load: load.id, group: load.group, scene: load.scene, sceneLabel: load.sceneLabel, view, time: load.time, hour: load.hour,
				weather: load.weather, renderer: { requested: load.renderer, actual: result.identity.backend }, tier: { requested: load.tier, actual: result.identity.lookdev?.settings?.tier ?? null },
				fsr: { requested: load.fsr, upscaling: result.identity.lookdev?.upscaling ?? null }, lodDistance: load.lodDistance, viewport: vp, url, deterministic: load.deterministic,
				image: { file: `shots/${id}.png`, width: result.image.width, height: result.image.height, method: result.image.method, sha256: createHash("sha256").update(png).digest("hex"),
					bytes: png.length, stats: result.image.stats, blank: result.image.blank, notes: result.image.notes },
				metrics: result.metrics, settled: result.settled, temporal, identity: result.identity, clock: result.clock,
				timing: { vsync, frameCap: load.frameCap, maxFpsDuringSample: result.frameCapNow, gameFrameCap: result.identity.gameFrameCap, warmupFrames: load.warmupFrames, sampleFrames: load.sampleFrames },
				capturedAt: new Date().toISOString(), wallMs: Date.now() - viewStarted };
			shot.gpuErrors = { count: record.gpuErrors.count, roots: record.gpuErrors.roots.slice() };
			shot.verdict = captureVerdict({ image: shot.image.file, blank: shot.image.blank }, { ...shot, waited: record.waited, failedRequests: record.failedRequests });
			writeFileSync(join(shotsDir, `${id}.json`), JSON.stringify(shot, null, 2));
			run.shots[id] = { ...shotSummary(shot), verdict: shot.verdict.capture, invalid: shot.verdict.invalid, warnings: shot.verdict.warnings, flicker: temporal?.pctTogglers ?? null, gpuErrors: shot.gpuErrors.count, machineAtLoadStart: record.machineLoad }; save();
			const m = result.metrics;
			log(`  ${id.padEnd(46)} frame ${m.frameMs.p50}/${m.robust?.frameP95?.p95 ?? m.frameMs.p95} ms (pooled p95 ${m.frameMs.p95}) · cpu ${m.cpuMs.p50}/${m.cpuMs.p95} · gpu ${m.gpuMs?.p50 ?? "-"}/${m.gpuMs?.p95 ?? "-"} · dc ${m.drawCalls.p50} · ${result.image.method} ${result.image.width}x${result.image.height}${result.image.blank ? " BLANK" : ""} · ${shot.verdict.capture}${shot.verdict.warnings.length ? ` (${shot.verdict.warnings.join(",")})` : ""}${temporal?.pctTogglers !== undefined ? ` · flicker ${temporal.pctTogglers} %` : ""}`);
		}
	} catch (error) {
		record.error = String(error?.stack ?? error).slice(0, 1500);
		log(`  ERROR ${load.id}: ${record.error.split("\n")[0]}`);
	} finally {
		record.consoleErrors = errors; record.finishedAt = new Date().toISOString(); record.wallMs = Date.now() - started;
		await context.close().catch(() => {});
		record.machineLoadEnd = await machineLoad(500);
		// Busy = another heavy job shares this PC (Blender at either end, or >= 60 % CPU before our page existed): frame times are unqualified.
		record.machineBusy = !!(record.machineLoad?.blenderRunning || record.machineLoadEnd?.blenderRunning || (record.machineLoad?.cpuBusyPct ?? 0) >= 60);
		run.loads[load.id] = record; save();
	}
	return record;
}

// ---------- session ----------
let lock = null, preview = null, chrome = null;
const session = { startedAt: new Date().toISOString(), vsync, maxMinutes, loadsAttempted: [], stoppedFor: null };
run.sessions.push(session); save();
const shutdown = async () => {
	try { await chrome?.browser.close(); } catch { /* already closed */ }
	try { await preview?.stop(); } catch (error) { log(`preview stop: ${error.message}`); }
	try { releaseGpuLock(lock); lock = null; } catch (error) { log(`lock release: ${error.message}`); }
};
process.on("SIGINT", () => { void shutdown().finally(() => process.exit(130)); });
try {
	if (pending.length) {
		if (!args.noLock) lock = await acquireGpuLock({ path: args.lock ?? DEFAULT_LOCK, owner: `claude-capture-${label}-pid${process.pid}-${new Date().toISOString()}` });
		session.lockAcquiredAt = new Date().toISOString();
		const deadline = Date.now() + maxMinutes * 60000;
		session.freeRamGB = await ensureFreeRam(1.5);
		if (dist) preview = await startPreview({ dist, port: Number(args.port ?? 4310) });
		const base = preview?.url ?? args.url;
		chrome = await launchChrome({ vsync });
		run.browser = { name: "Google Chrome (headed)", version: chrome.version, args: chrome.args, driver: "playwright 1.64.0-alpha (npx cache)" }; save();
		log(`Chrome ${chrome.version} (vsync ${vsync}); session budget ${maxMinutes} min`);
		const durations = [];
		for (const load of pending) {
			const estimate = durations.length ? Math.max(...durations) * 1.15 : 120000;
			if (Date.now() + estimate > deadline) { session.stoppedFor = `session budget (${maxMinutes} min); resume with --resume`; log(session.stoppedFor); break; }
			log(`load ${load.id} (${load.views.length} views)`);
			const record = await captureLoad(chrome.browser, base, load);
			durations.push(record.wallMs); session.loadsAttempted.push(load.id);
		}
	}
} finally {
	await shutdown();
	session.finishedAt = new Date().toISOString(); save();
}

// ---------- outputs ----------
const ordered = loads.flatMap(load => load.views.map(view => run.shots[shotId(load, view)]).filter(Boolean));
const complete = ordered.length === loads.reduce((sum, load) => sum + load.views.length, 0);
run.complete = complete;
if (ordered.length) {
	const items = ordered.map(shot => ({ path: join(runDir, shot.image), label: `${shot.scene} · ${shot.view}`,
		sublabel: `${shot.time} · ${shot.renderer}${shot.tier ? ` · ${shot.tier}` : ""}${shot.fsr ? ` · FSR ${shot.fsr}` : ""} · p95 ${shot.frameP95 ?? "-"} ms · ${shot.drawCalls ?? "-"} dc`,
		badge: shot.blank ? "BLANK" : null }));
	const itemsPath = join(runDir, "contact-sheet.items.json");
	writeFileSync(itemsPath, JSON.stringify(items, null, 1));
	runPython("contact_sheet.py", ["--items", itemsPath, "--out", join(runDir, "contact-sheet.png"), "--cols", "4", "--thumb", "480",
		"--title", `${label} · ${ordered.length} shots · build ${run.build?.hash ?? "?"} · ${run.browser?.version ?? ""} · vsync ${vsync}`]);
	run.contactSheet = "contact-sheet.png";
}
run.verdict = !ordered.length ? "NO_SHOTS" : !complete ? "INCOMPLETE_CAPTURE" : ordered.every(shot => shot.verdict === "OK") ? "OK" : "SOME_SHOTS_INVALID";
save();
const ledgerPath = resolve(args.ledger ?? LEDGER);
if (!args.noLedger && ordered.length && (complete || args.ledgerPartial) && !run.ledgerAppended) {
	run.ledger = appendRun(runDir, { ledger: ledgerPath, deviceClass: args.deviceClass ?? null });
	run.ledgerAppended = relative(REPO, ledgerPath).replace(/\\/g, "/");
}
save();
const failed = Object.values(run.loads).filter(record => record.error).map(record => record.id);
log(`${label}: ${ordered.length} shots in ${relative(REPO, runDir)}${complete ? " (complete)" : " (partial)"}${failed.length ? `; failed loads: ${failed.join(", ")}` : ""}`);
process.exitCode = failed.length ? 1 : 0;
