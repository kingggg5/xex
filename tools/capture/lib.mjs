// Shared helpers for tools/capture: GPU lock, RAM check, preview server, Chrome, git/build identity, ledger.
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, statSync, unlinkSync, writeSync, appendFileSync } from "node:fs";
import { createRequire } from "node:module";
import { cpus, freemem, tmpdir, totalmem, release, platform } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const TOOL_DIR = dirname(fileURLToPath(import.meta.url));
export const REPO = resolve(TOOL_DIR, "..", "..");
export const CLIENT = join(REPO, "apps", "client");
// Capture scratch is configurable; the default GPU lock is shared across tools on this host.
export const SCRATCH = resolve(process.env.XEX_SCRATCH ?? (process.env.XEXORIA_AGENT_OUTPUT
	? join(process.env.XEXORIA_AGENT_OUTPUT, "capture") : join(tmpdir(), "xexoria-capture")));
export const DEFAULT_LOCK = process.env.XEX_GPU_LOCK ?? join(tmpdir(), "xexoria-gpu-measure.lock");
export const PLAYWRIGHT = process.env.XEX_PLAYWRIGHT ?? "playwright";
export const LEDGER = join(REPO, "planning", "perf-ledger.jsonl");

export const sleep = ms => new Promise(done => setTimeout(done, ms));
export function log(...parts) { console.log(new Date().toLocaleTimeString("en-GB", { hour12: false }), ...parts); }
export const slug = value => String(value).replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 120);

/** Minimal `--key value` / `--flag` parser. Repeated keys become arrays. */
export function parseArgs(argv, { booleans = [] } = {}) {
	const out = { _: [] };
	for (let i = 0; i < argv.length; i++) {
		const arg = argv[i];
		if (!arg.startsWith("--")) { out._.push(arg); continue; }
		const [rawKey, inline] = arg.slice(2).split(/=(.*)/s, 2);
		const key = rawKey.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
		const value = inline !== undefined ? inline : booleans.includes(key) || argv[i + 1] === undefined || argv[i + 1].startsWith("--") ? true : argv[++i];
		out[key] = out[key] === undefined ? value : [].concat(out[key], value);
	}
	return out;
}

// ---------- GPU lock ----------
export async function acquireGpuLock({ path = DEFAULT_LOCK, owner, retryMs = 30000, maxWaitMs = 90 * 60000 } = {}) {
	const started = Date.now();
	let announced = "";
	for (;;) {
		try {
			const fd = openSync(path, "wx");
			try { writeSync(fd, `${owner}\n`); } finally { closeSync(fd); }
			if (!readFileSync(path, "utf8").startsWith(owner)) throw new Error("GPU lock content mismatch after create");
			log(`GPU lock acquired (${path}) after ${Math.round((Date.now() - started) / 1000)} s`);
			return { path, owner, acquiredAt: new Date().toISOString(), waitedMs: Date.now() - started };
		} catch (error) {
			if (error.code !== "EEXIST") throw error;
			let holder = "?", ageMin = null;
			try { holder = readFileSync(path, "utf8").trim(); ageMin = Math.round((Date.now() - statSync(path).mtimeMs) / 60000); } catch { /* vanished between calls */ }
			if (Date.now() - started > maxWaitMs) throw new Error(`GPU lock still held by "${holder}" after ${Math.round(maxWaitMs / 60000)} min`);
			const note = `${holder}|${ageMin}`;
			if (note !== announced) { log(`GPU lock held by "${holder}" (age ${ageMin ?? "?"} min); retrying every ${retryMs / 1000} s`); announced = note; }
			await sleep(retryMs);
		}
	}
}
export function releaseGpuLock(lock) {
	if (!lock) return true;
	let holder;
	try { holder = readFileSync(lock.path, "utf8"); }
	catch (error) { if (error.code === "ENOENT") { log("GPU lock already absent"); return true; } throw error; }
	if (!holder.startsWith(lock.owner)) { log(`GPU lock now belongs to "${holder.trim()}"; not deleting it`); return false; }
	unlinkSync(lock.path);
	if (existsSync(lock.path)) throw new Error(`GPU lock delete did not take effect: ${lock.path}`);
	log("GPU lock released (delete verified)");
	return true;
}

// ---------- machine ----------
export async function ensureFreeRam(minGB = 1.5, { waitMs = 5 * 60000 } = {}) {
	const started = Date.now();
	for (;;) {
		const free = freemem() / 1024 ** 3;
		if (free >= minGB) return Math.round(free * 100) / 100;
		if (Date.now() - started > waitMs) throw new Error(`Only ${free.toFixed(2)} GB RAM free (< ${minGB} GB); not starting a browser`);
		log(`Only ${free.toFixed(2)} GB RAM free; waiting for ${minGB} GB`);
		await sleep(30000);
	}
}
/** Whole-machine CPU busy % over `ms`, plus whether Blender runs: context for frame-time noise on a shared PC. */
export async function machineLoad(ms = 1000) {
	const sample = () => cpus().reduce((acc, cpu) => { const t = cpu.times; acc.idle += t.idle; acc.total += t.user + t.nice + t.sys + t.idle + t.irq; return acc; }, { idle: 0, total: 0 });
	const a = sample(); await sleep(ms); const b = sample();
	const busy = b.total - a.total > 0 ? Math.round((1 - (b.idle - a.idle) / (b.total - a.total)) * 1000) / 10 : null;
	let blender = null;
	if (platform() === "win32") { const list = spawnSync("tasklist", ["/FI", "IMAGENAME eq blender.exe", "/NH"], { encoding: "utf8", windowsHide: true }); blender = /blender\.exe/i.test(list.stdout ?? ""); }
	return { cpuBusyPct: busy, blenderRunning: blender, freeRamGB: Math.round(freemem() / 1024 ** 3 * 100) / 100 };
}
export function machineInfo() {
	const cpu = cpus();
	return { os: `${platform()} ${release()}`, cpu: cpu[0]?.model?.trim() ?? null, logicalCores: cpu.length, totalRamGB: Math.round(totalmem() / 1024 ** 3 * 10) / 10, freeRamGB: Math.round(freemem() / 1024 ** 3 * 10) / 10 };
}

// ---------- preview server ----------
async function httpOk(url, timeoutMs = 1500) {
	try { const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) }); return response.ok; } catch { return false; }
}
export async function startPreview({ dist, port = 4310 }) {
	if (!existsSync(join(dist, "index.html"))) throw new Error(`No production build at ${dist} (index.html missing); run tools/capture/build.mjs first`);
	const url = `http://127.0.0.1:${port}`;
	if (await httpOk(url)) throw new Error(`Port ${port} is already serving; stop that server or pass --url`);
	const viteBin = join(CLIENT, "node_modules", "vite", "bin", "vite.js");
	const child = spawn(process.execPath, [viteBin, "preview", "--outDir", dist, "--port", String(port), "--strictPort", "--host", "127.0.0.1"], { cwd: CLIENT, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
	let output = ""; child.stdout.on("data", chunk => { output += chunk; }); child.stderr.on("data", chunk => { output += chunk; });
	let exited = null; child.on("exit", code => { exited = code; });
	const started = Date.now();
	while (!(await httpOk(url))) {
		if (exited !== null) throw new Error(`vite preview exited (${exited}): ${output.slice(-600)}`);
		if (Date.now() - started > 30000) { stopPid(child.pid); throw new Error(`vite preview did not answer on ${url}: ${output.slice(-600)}`); }
		await sleep(300);
	}
	log(`vite preview PID ${child.pid} serving ${dist} at ${url}`);
	return { pid: child.pid, url, async stop() {
		if (exited !== null) return;
		stopPid(child.pid);
		const deadline = Date.now() + 8000;
		while (exited === null && Date.now() < deadline) await sleep(150);
		if (await httpOk(url)) throw new Error(`Port ${port} still answers after stopping PID ${child.pid}`);
		log(`vite preview PID ${child.pid} stopped`);
	} };
}
/** Stops one process tree that this tool started, by PID. */
export function stopPid(pid) {
	if (!pid) return;
	if (platform() === "win32") spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
	else { try { process.kill(pid, "SIGTERM"); } catch { /* already gone */ } }
}

// ---------- browser ----------
export function loadPlaywright() {
	// Resolve installed project dependencies, or an explicitly supplied module/path. Never use a private npm-cache default.
	try { return createRequire(join(CLIENT, "package.json"))(PLAYWRIGHT); }
	catch (cause) { throw new Error("Project Playwright is unavailable; install the project dependency or set XEX_PLAYWRIGHT explicitly.", { cause }); }
}
export async function launchChrome({ vsync = "on", extraArgs = [] } = {}) {
	const { chromium } = loadPlaywright();
	const args = ["--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
		"--enable-precise-memory-info", "--window-position=0,0", "--window-size=1940,1200",
		...(vsync === "off" ? ["--disable-gpu-vsync", "--disable-frame-rate-limit"] : []), ...extraArgs];
	const browser = await chromium.launch({ channel: "chrome", headless: false, args });
	return { browser, args, version: browser.version() };
}

// ---------- identity ----------
function git(args) { const result = spawnSync("git", ["-C", REPO, ...args], { encoding: "utf8", windowsHide: true, maxBuffer: 64 * 1024 * 1024 }); return result.status === 0 ? result.stdout : null; }
export function gitState() {
	const head = git(["rev-parse", "HEAD"])?.trim() ?? null;
	const branch = git(["rev-parse", "--abbrev-ref", "HEAD"])?.trim() ?? null;
	const lines = (git(["status", "--porcelain"]) ?? "").split("\n").filter(Boolean);
	const client = lines.filter(line => line.slice(3).replace(/^"|"$/g, "").startsWith("apps/client/"));
	return { head, branch, dirtyFiles: lines.filter(line => !line.startsWith("??")).length, untrackedFiles: lines.filter(line => line.startsWith("??")).length,
		clientDirtyFiles: client.length, statusSha256: createHash("sha256").update(lines.join("\n")).digest("hex").slice(0, 16) };
}
export function sha256File(path) { return createHash("sha256").update(readFileSync(path)).digest("hex"); }
export function walkFiles(root, { skip = () => false } = {}) {
	const files = [];
	const visit = dir => {
		for (const name of readdirSync(dir)) {
			const path = join(dir, name);
			if (skip(path, name)) continue;
			const stat = statSync(path);
			if (stat.isDirectory()) visit(path); else files.push({ path, rel: relative(root, path).replace(/\\/g, "/"), size: stat.size });
		}
	};
	visit(root);
	return files.sort((a, b) => a.rel < b.rel ? -1 : a.rel > b.rel ? 1 : 0);
}
/** Content hash over every file (path + sha256), so two builds with equal hashes served identical bytes. */
export function treeHash(root, options) {
	const files = walkFiles(root, options), hash = createHash("sha256");
	let bytes = 0;
	for (const file of files) { hash.update(`${file.rel}\0${sha256File(file.path)}\n`); bytes += file.size; }
	return { sha256: hash.digest("hex"), files: files.length, bytes };
}
export function readBuildReceipt(dist) {
	const path = join(dist, "capture-build.json");
	return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : null;
}

// ---------- outputs ----------
/** Append-only JSONL (`xexoria.ledger/1` rows; one row per captured scenario). */
export function appendLedgerRows(rows, path = LEDGER) {
	mkdirSync(dirname(path), { recursive: true });
	appendFileSync(path, rows.map(row => `${JSON.stringify(row)}\n`).join(""));
	log(`perf ledger += ${rows.length} rows (${[...new Set(rows.map(row => row.run_id))].join(", ")}) -> ${relative(REPO, path)}`);
}
export function runPython(script, args) {
	const result = spawnSync("python", [join(TOOL_DIR, script), ...args], { encoding: "utf8", windowsHide: true, maxBuffer: 64 * 1024 * 1024 });
	if (result.status !== 0) throw new Error(`python ${script} failed (${result.status}): ${(result.stderr || result.stdout).slice(-1500)}`);
	return result.stdout;
}
export function decodeDataUrl(dataUrl) {
	const match = /^data:image\/png;base64,(.*)$/s.exec(dataUrl);
	if (!match) throw new Error("Expected a PNG data URL");
	return Buffer.from(match[1], "base64");
}
