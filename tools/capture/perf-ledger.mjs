// Perf ledger `xexoria.ledger/1`: one JSON row per captured scenario (shot) in planning/perf-ledger.jsonl.
//   node tools/capture/perf-ledger.mjs append <runDir> [--noise <A/A report.json>] [--device-class desktop-gtx1050] [--ledger <path>]
//   node tools/capture/perf-ledger.mjs compare --baseline <run_id> [--candidate <run_id>|latest] [--scenario <substr>] [--backend webgpu|webgl2] [--json <out>]
//   node tools/capture/perf-ledger.mjs noise --aa <A/A report.json>          (prints the per-scenario noise floor)
// Rules (docs/reviews/2026-10-02-repos-oriverse-reuse.md §8.4): rows with preflight.valid=false are refused; a dirty tree is
// recorded and such rows are never picked as "last-clean"; missing values stay null, never 0.
// Regression: p95 wall or CPU worse by more than 10 % or 1.0 ms after subtracting the A/A noise floor; GPU p95 > 10 %; draws > 10 %.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { LEDGER, REPO, appendLedgerRows, log, parseArgs } from "./lib.mjs";

const BUDGET_MS = { desktop: 16.7, phone: 33.3 };
const rel = path => relative(REPO, path).replace(/\\/g, "/");

export function deviceClassOf(run) {
	const adapters = Object.values(run.shots ?? {}).map(shot => shot.adapter ?? "").filter(Boolean);
	for (const text of adapters) {
		const match = /(GeForce\s+)?(GTX|RTX|RX|Arc|Iris|UHD|Radeon|Apple|Mali|Adreno)\s*([A-Za-z]*\s*\d{2,4}[A-Za-z]*)/i.exec(text);
		if (match) return `desktop-${(match[2] + match[3]).toLowerCase().replace(/\s+/g, "")}`;
	}
	return "desktop-unknown";
}
/** Capture-validity verdict per shot (benilla "prove the run before reading it" + our backend/visibility terms). */
export function captureVerdict(shot, detail) {
	const invalid = [], warnings = [];
	if (!shot.image) invalid.push("INCOMPLETE_CAPTURE");
	if (shot.blank) invalid.push("BLANK_RENDER");
	if ((detail?.gpuErrors?.count ?? 0) > 0) invalid.push("GPU_VALIDATION_ERRORS");
	if (detail?.renderer && detail.renderer.requested && (detail.renderer.requested === "webgpu") !== (detail.renderer.actual === "WebGPU")) invalid.push("FALLBACK_BACKEND");
	if (detail?.metrics?.hiddenFrames > 0 || detail?.metrics?.visibleThroughout === false) invalid.push("HIDDEN_OR_UNFOCUSED");
	else if (detail?.metrics?.focusedAtEnd === false) warnings.push("UNFOCUSED_WINDOW");
	if (detail?.identity?.loadingScreen) invalid.push("LOADING_SCREEN");
	if (detail?.waited && (detail.waited.sceneReady === false || detail.waited.pendingMs === -1)) invalid.push("SCENE_NOT_READY");
	if (detail?.settled && detail.settled.settled === false) invalid.push("SCENE_NOT_SETTLED");
	if (detail?.failedRequests?.length) warnings.push("LOAD_DEGRADED");
	const compiles = detail?.metrics?.compilesDuringSample;
	if (compiles && ((compiles.effects ?? 0) > 0 || (compiles.pipelines ?? 0) > 0)) warnings.push("COMPILES_DURING_SAMPLE");
	if (detail?.deterministic === false) warnings.push("NOT_DETERMINISTIC_SCENE");
	return { capture: invalid[0] ?? "OK", valid: invalid.length === 0, invalid, warnings };
}
/** Per-scenario noise floor from a compare.py A/A report: max(|Δ| of this shot, median |Δ| of its backend), never below 0.1 ms. */
export function noiseFloorFrom(reportPath) {
	const report = JSON.parse(readFileSync(reportPath, "utf8"));
	const floors = {}, byBackend = {};
	const absolute = value => Number.isFinite(value) ? Math.abs(value) : null;
	for (const shot of report.shots ?? []) {
		const d = shot.perf?.delta ?? {};
		const entry = { wall_p95_ms: absolute(d.frameP95), cpu_p95_ms: absolute(d.cpuP95), gpu_p95_ms: absolute(d.gpuP95) };
		floors[shot.id] = entry;
		(byBackend[shot.renderer] ??= []).push(entry);
	}
	const median = values => { const finite = values.filter(Number.isFinite).sort((a, b) => a - b); return finite.length ? finite[Math.floor(finite.length / 2)] : null; };
	for (const [id, entry] of Object.entries(floors)) {
		const peers = byBackend[(report.shots.find(shot => shot.id === id) ?? {}).renderer] ?? [];
		for (const key of ["wall_p95_ms", "cpu_p95_ms", "gpu_p95_ms"]) {
			const value = entry[key], peer = median(peers.map(peerEntry => peerEntry[key]));
			entry[key] = value === null && peer === null ? null : Math.max(0.1, value ?? 0, peer ?? 0);
			entry[key] = entry[key] === null ? null : Math.round(entry[key] * 1000) / 1000;
		}
		entry.source = `A/A ${report.before?.label} vs ${report.after?.label}`;
	}
	return floors;
}
export function ledgerRowsFromRun(runDir, { noise = null, deviceClass = null } = {}) {
	const run = JSON.parse(readFileSync(join(runDir, "run.json"), "utf8"));
	const device = deviceClass ?? deviceClassOf(run);
	const rows = [];
	for (const shot of Object.values(run.shots ?? {})) {
		const detailPath = join(runDir, "shots", `${shot.id}.json`);
		const detail = existsSync(detailPath) ? JSON.parse(readFileSync(detailPath, "utf8")) : null;
		const m = detail?.metrics ?? {};
		const load = run.loads?.[shot.load] ?? {};
		const verdict = captureVerdict(shot, detail ? { ...detail, waited: load.waited, failedRequests: load.failedRequests } : null);
		const machineBusy = load.machineBusy ?? !!(load.machineLoad?.blenderRunning || load.machineLoadEnd?.blenderRunning || (load.machineLoad?.cpuBusyPct ?? 0) >= 60);
		if (machineBusy) verdict.warnings.push("MACHINE_BUSY");
		const phone = /iphone|android|pixel|galaxy|@2|@3/.test(shot.viewport ?? "") && !/^1920x1080@1$/.test(shot.viewport ?? "");
		const budget = phone ? BUDGET_MS.phone : BUDGET_MS.desktop;
		const results = [{ id: `wall_p95<=${budget}`, value: shot.frameP95, status: shot.frameP95 === null ? "n/a" : shot.frameP95 <= budget ? "pass" : "fail" },
			{ id: `cpu_p95<=${budget}`, value: shot.cpuP95, status: shot.cpuP95 === null ? "n/a" : shot.cpuP95 <= budget ? "pass" : "fail" }];
		rows.push({
			schema: "xexoria.ledger/1", run_id: run.label, ts: shot.capturedAt ?? run.createdAt,
			build: { git: run.git?.head ?? null, dirty: (run.git?.dirtyFiles ?? 0) + (run.git?.untrackedFiles ?? 0) > 0, dirty_files: run.git?.dirtyFiles ?? null, client_dirty_files: run.git?.clientDirtyFiles ?? null,
				client_hash: run.build?.hash ?? null, source_sha256: run.build?.sourceSha256 ?? null, dev_hooks: run.build?.devHooks ?? null, mode: run.build?.devHooks ? "production+dev-hooks" : "production", server_git: null },
			scenario: shot.id, scene: shot.scene, view: shot.view, time: shot.time, device_class: device, backend: String(shot.renderer).toLowerCase(), viewport: shot.viewport, render: shot.renderSize,
			tier: shot.tier, upscaling: shot.upscaling, browser: run.browser?.version ?? null,
			settings: { vsync: detail?.timing?.vsync ?? null, clock: detail?.clock?.mode ?? null, frame_cap: detail?.timing?.frameCap ?? null, warmup_frames: detail?.timing?.warmupFrames ?? null, sample_frames: detail?.timing?.sampleFrames ?? null },
			preflight: { valid: verdict.valid, invalid: verdict.invalid, warnings: verdict.warnings },
			machine: { busy: machineBusy, atStart: load.machineLoad ?? null, atEnd: load.machineLoadEnd ?? null },
			frames: { n: m.frameMs?.n ?? null, p95_rule: "median of three sub-window p95s", wall_ms: m.frameMs ? { p50: m.frameMs.p50, p95: shot.frameP95, p95_pooled: m.frameMs.p95, p99: m.frameMs.p99 } : null,
				cpu_ms: m.cpuMs ? { p50: m.cpuMs.p50, p95: shot.cpuP95, p95_pooled: m.cpuMs.p95 } : null,
				gpu_ms: m.gpuMs && m.gpuMs.n ? { p50: m.gpuMs.p50, p95: shot.gpuP95, p95_pooled: m.gpuMs.p95, n: m.gpuMs.n, scope: m.gpuScope } : null, hitches50: m.hitches50 ?? null, hitches100: m.hitches100 ?? null, fps: m.fps ?? null },
			counts: { draws: shot.drawCalls, tris: shot.triangles, active_meshes: shot.activeMeshes, particles: shot.particles, tex_mib: null, heap_mib: shot.heapMB },
			noise_floor: noise?.[shot.id] ?? null,
			verdict: { capture: verdict.capture, pass: verdict.valid && results.every(result => result.status !== "fail"), results },
			artifacts: { image: rel(join(runDir, shot.image)), image_sha256: shot.imageSha256, shot_json: rel(detailPath), sheet: run.contactSheet ? rel(join(runDir, run.contactSheet)) : null },
		});
	}
	return rows;
}
export function readLedger(path = LEDGER) {
	if (!existsSync(path)) return [];
	return readFileSync(path, "utf8").split("\n").filter(Boolean).map((line, index) => { try { return JSON.parse(line); } catch { throw new Error(`Ledger line ${index + 1} is not JSON`); } })
		.filter(row => row.schema === "xexoria.ledger/1");
}
export function appendRun(runDir, options = {}) {
	const rows = ledgerRowsFromRun(runDir, options);
	const accepted = rows.filter(row => row.preflight.valid), refused = rows.filter(row => !row.preflight.valid);
	for (const row of refused) log(`ledger refused ${row.scenario}: ${row.preflight.invalid.join(", ")}`);
	if (accepted.length) appendLedgerRows(accepted, options.ledger ?? LEDGER);
	return { accepted: accepted.length, refused: refused.map(row => ({ scenario: row.scenario, invalid: row.preflight.invalid })) };
}
const pct = (delta, base) => Number.isFinite(delta) && Number.isFinite(base) && base > 0 ? delta / base * 100 : null;
/** The task rule: worse by more than 10 % or more than 1 ms, after subtracting the noise floor. */
export function regression(base, candidate, floor) {
	if (!Number.isFinite(base) || !Number.isFinite(candidate)) return { delta: null, beyondNoise: null, flagged: false, status: "n/a" };
	const delta = candidate - base, noise = Number.isFinite(floor) ? floor : 0;
	const beyond = Math.sign(delta) * Math.max(0, Math.abs(delta) - noise);
	const flagged = beyond > 1.0 || (pct(beyond, base) ?? 0) > 10;
	return { delta: Math.round(delta * 1000) / 1000, beyondNoise: Math.round(beyond * 1000) / 1000, flagged, status: flagged ? "REGRESSION" : beyond < -1.0 || (pct(beyond, base) ?? 0) < -10 ? "improved" : "within noise" };
}
export function compareRows(rows, { baseline, candidate = "latest", scenario = null, backend = null } = {}) {
	const runs = [...new Set(rows.map(row => row.run_id))];
	const candidateId = candidate === "latest" ? runs.filter(id => id !== baseline).at(-1) : candidate;
	const baseId = baseline === "last-clean" ? [...rows].reverse().find(row => !row.build.dirty && row.run_id !== candidateId)?.run_id : baseline;
	if (!baseId || !candidateId) throw new Error(`Need a baseline and a candidate run (have: ${runs.join(", ") || "none"})`);
	const pick = id => new Map(rows.filter(row => row.run_id === id && (!scenario || row.scenario.includes(scenario)) && (!backend || row.backend === backend)).map(row => [`${row.scenario}|${row.device_class}|${row.backend}`, row]));
	const base = pick(baseId), cand = pick(candidateId), out = [];
	for (const [key, b] of base) {
		const c = cand.get(key); if (!c) continue;
		const floor = c.noise_floor ?? b.noise_floor ?? {};
		const wall = regression(b.frames.wall_ms?.p95, c.frames.wall_ms?.p95, floor.wall_p95_ms);
		const cpu = regression(b.frames.cpu_ms?.p95, c.frames.cpu_ms?.p95, floor.cpu_p95_ms);
		const gpuDelta = Number.isFinite(b.frames.gpu_ms?.p95) && Number.isFinite(c.frames.gpu_ms?.p95) ? c.frames.gpu_ms.p95 - b.frames.gpu_ms.p95 : null;
		const gpuBeyond = gpuDelta === null ? null : Math.sign(gpuDelta) * Math.max(0, Math.abs(gpuDelta) - (floor.gpu_p95_ms ?? 0));
		const drawsPct = pct((c.counts.draws ?? NaN) - (b.counts.draws ?? NaN), b.counts.draws);
		const raw = [wall.flagged && "wall_p95", cpu.flagged && "cpu_p95", (pct(gpuBeyond, b.frames.gpu_ms?.p95) ?? 0) > 10 && "gpu_p95", (drawsPct ?? 0) > 10 && "draws"].filter(Boolean);
		// Timing taken while another heavy job shared the PC is not evidence; draw-count changes still count.
		const busy = !!(b.machine?.busy || c.machine?.busy);
		const flags = busy ? raw.filter(flag => flag === "draws") : raw;
		out.push({ busy, rawFlags: raw, scenario: b.scenario, backend: b.backend, device_class: b.device_class, wall_p95: [b.frames.wall_ms?.p95 ?? null, c.frames.wall_ms?.p95 ?? null], wall,
			cpu_p95: [b.frames.cpu_ms?.p95 ?? null, c.frames.cpu_ms?.p95 ?? null], cpu, gpu_p95: [b.frames.gpu_ms?.p95 ?? null, c.frames.gpu_ms?.p95 ?? null], gpu_delta: gpuDelta,
			draws: [b.counts.draws, c.counts.draws], draws_pct: drawsPct === null ? null : Math.round(drawsPct * 10) / 10, noise_floor: floor, flags, status: flags.length ? "REGRESSION" : busy ? "unqualified (machine busy)" : wall.status });
	}
	return { baseline: baseId, candidate: candidateId, rows: out, regressions: out.filter(row => row.flags.length).length };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	const [command, ...rest] = process.argv.slice(2);
	const args = parseArgs(rest, { booleans: [] });
	const ledgerPath = resolve(args.ledger ?? LEDGER);
	if (command === "append") {
		const runDir = resolve(args._[0] ?? "");
		if (!existsSync(join(runDir, "run.json"))) { console.error("usage: perf-ledger.mjs append <runDir> [--noise aa-report.json]"); process.exit(2); }
		const noise = args.noise ? noiseFloorFrom(resolve(args.noise)) : null;
		console.log(JSON.stringify(appendRun(runDir, { noise, deviceClass: args.deviceClass ?? null, ledger: ledgerPath }), null, 1));
	} else if (command === "compare") {
		if (!args.baseline) { console.error("usage: perf-ledger.mjs compare --baseline <run_id|last-clean> [--candidate <run_id|latest>]"); process.exit(2); }
		const result = compareRows(readLedger(ledgerPath), { baseline: args.baseline, candidate: args.candidate ?? "latest", scenario: args.scenario ?? null, backend: args.backend ?? null });
		const f = value => value === null || value === undefined ? "  -  " : Number(value).toFixed(2);
		console.log(`baseline ${result.baseline} -> candidate ${result.candidate}`);
		console.log(`${"scenario".padEnd(44)} ${"wall p95".padStart(15)} ${"Δ".padStart(7)} ${"noise".padStart(6)} ${"cpu p95".padStart(15)} ${"gpu p95".padStart(15)} ${"draws".padStart(11)}  status`);
		for (const row of result.rows) console.log(`${row.scenario.padEnd(44)} ${`${f(row.wall_p95[0])}->${f(row.wall_p95[1])}`.padStart(15)} ${f(row.wall.delta).padStart(7)} ${f(row.noise_floor.wall_p95_ms).padStart(6)} ${`${f(row.cpu_p95[0])}->${f(row.cpu_p95[1])}`.padStart(15)} ${`${f(row.gpu_p95[0])}->${f(row.gpu_p95[1])}`.padStart(15)} ${`${row.draws[0] ?? "-"}->${row.draws[1] ?? "-"}`.padStart(11)}  ${row.status}${row.flags.length ? ` (${row.flags.join(", ")})` : ""}`);
		console.log(`${result.rows.length} scenarios, ${result.regressions} flagged`);
		if (args.json) writeFileSync(resolve(args.json), JSON.stringify(result, null, 1));
		process.exitCode = result.regressions ? 1 : 0;
	} else if (command === "noise") {
		console.log(JSON.stringify(noiseFloorFrom(resolve(args.aa)), null, 1));
	} else {
		console.error("commands: append <runDir> [--noise aa.json] | compare --baseline <id> [--candidate <id>] | noise --aa <report.json>");
		process.exit(2);
	}
}
