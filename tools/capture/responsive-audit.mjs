// Responsive device audit of the real game page (offline preview; the Rust server is never needed).
//   node tools/capture/responsive-audit.mjs (--dist <build dir> | --url <url>) --out <dir> [--devices id,id] [--renderer webgl2|webgpu]
//        [--max-minutes 14] [--lock <path>] [--no-lock] [--resume]
// Touch devices run portrait (boot gate) -> landscape (game boots) -> portrait -> landscape and compare the two landscape layouts.
// Chrome device emulation is not Safari: 100vh/dvh, safe areas, toolbars and rAF throttling differ (see README).
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { DEFAULT_LOCK, REPO, TOOL_DIR, acquireGpuLock, ensureFreeRam, gitState, launchChrome, log, parseArgs, readBuildReceipt, releaseGpuLock, runPython, sleep, startPreview } from "./lib.mjs";

const IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1";
const IPADOS = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15"; // iPadOS asks for desktop sites
const ANDROID = model => `Mozilla/5.0 (Linux; Android 15; ${model}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36`;
// Safe-area insets (CSS px) emulate the Home Screen web app, the worst case. Approximations: iPhone 11 48/34 portrait, 48+48/21 landscape
// (docs/reviews/2026-10-02-iphone11-safari-target.md §5.4, UNVERIFIED); Dynamic Island phones about 62/34 and 62+62/21; iPads 24/20.
const NOTCH_11 = { portrait: { top: 48, bottom: 34 }, landscape: { left: 48, right: 48, bottom: 21 } };
const ISLAND = { portrait: { top: 62, bottom: 34 }, landscape: { left: 62, right: 62, bottom: 21 } };
const IPAD = { portrait: { top: 24, bottom: 20 }, landscape: { top: 24, bottom: 20 } };
export const DEVICES = [
	{ id: "iphone-se", label: "iPhone SE (3rd gen)", w: 375, h: 667, dpr: 2, kind: "phone", ua: IOS, insets: null },
	{ id: "iphone-11", label: "iPhone 11", w: 414, h: 896, dpr: 2, kind: "phone", ua: IOS, insets: NOTCH_11 },
	{ id: "iphone-16-pro", label: "iPhone 16 Pro", w: 393, h: 852, dpr: 3, kind: "phone", ua: IOS, insets: ISLAND },
	{ id: "iphone-16-pro-max", label: "iPhone 16 Pro Max", w: 440, h: 956, dpr: 3, kind: "phone", ua: IOS, insets: ISLAND },
	{ id: "ipad", label: "iPad (10th gen)", w: 820, h: 1180, dpr: 2, kind: "tablet", ua: IPADOS, insets: IPAD },
	{ id: "ipad-mini", label: "iPad mini (6th gen)", w: 744, h: 1133, dpr: 2, kind: "tablet", ua: IPADOS, insets: IPAD },
	{ id: "galaxy-a54", label: "Galaxy A54 / Pixel 7", w: 412, h: 915, dpr: 2.625, kind: "phone", ua: ANDROID("SM-A546B"), insets: null },
	{ id: "android-small", label: "Small Android 360x800", w: 360, h: 800, dpr: 3, kind: "phone", ua: ANDROID("SM-A156B"), insets: null },
	{ id: "z-fold-inner", label: "Galaxy Z Fold (inner)", w: 673, h: 841, dpr: 2.5, kind: "foldable", ua: ANDROID("SM-F956B"), insets: null },
	{ id: "desktop-1366", label: "Desktop 1366x768", w: 1366, h: 768, dpr: 1, kind: "desktop" },
	{ id: "desktop-1080p", label: "Desktop 1920x1080", w: 1920, h: 1080, dpr: 1, kind: "desktop" },
	{ id: "desktop-1440p", label: "Desktop 2560x1440", w: 2560, h: 1440, dpr: 1, kind: "desktop" },
	{ id: "desktop-ultrawide", label: "Ultrawide 3440x1440", w: 3440, h: 1440, dpr: 1, kind: "desktop" },
];
const SEVERITY = { critical: 100, high: 30, medium: 10, low: 3, info: 0 };

const args = parseArgs(process.argv.slice(2), { booleans: ["noLock", "resume"] });
if (!args.out || (!args.dist && !args.url)) { console.error("usage: node tools/capture/responsive-audit.mjs (--dist <dir> | --url <url>) --out <dir> [--devices a,b]"); process.exit(2); }
const out = resolve(args.out), shotsDir = join(out, "screens");
mkdirSync(shotsDir, { recursive: true });
const renderer = args.renderer === "webgpu" ? "webgpu" : "webgl2";
const selected = args.devices ? DEVICES.filter(device => String(args.devices).split(",").includes(device.id)) : DEVICES;
const resultPath = join(out, "issues.json");
const previous = args.resume && existsSync(resultPath) ? JSON.parse(readFileSync(resultPath, "utf8")) : null;
const results = previous?.devices ?? {};
const maxMinutes = Math.min(15, Number(args.maxMinutes ?? 14));

async function waitFor(page, fn, arg, timeoutMs, label) {
	try { await page.waitForFunction(fn, arg, { timeout: timeoutMs, polling: 250 }); return true; }
	catch { log(`    timeout (${timeoutMs / 1000} s) waiting for ${label}`); return false; }
}
async function setInsets(cdp, insets) {
	const value = { top: insets?.top ?? 0, left: insets?.left ?? 0, bottom: insets?.bottom ?? 0, right: insets?.right ?? 0 };
	try { await cdp.send("Emulation.setSafeAreaInsetsOverride", { insets: { ...value, topMax: value.top, leftMax: value.left, bottomMax: value.bottom, rightMax: value.right } }); return true; }
	catch { return false; }
}
function annotateSpec(snapshot, title) {
	const items = [];
	for (const issue of snapshot.issues) {
		const rect = issue.type === "overlap" ? issue.intersection : issue.rect ?? issue.measured;
		if (!rect || !Number.isFinite(rect.x) || !Number.isFinite(rect.w) || issue.severity === "info") continue;
		const color = issue.severity === "critical" || issue.severity === "high" ? "#ff3b30" : issue.severity === "medium" ? "#ffcc00" : "#64d2ff";
		const note = issue.type === "overlap" ? `overlap ${issue.pctOfSmaller}%: ${issue.a} × ${issue.b}` : issue.type === "touch-target" ? `touch target ${issue.measured.w}×${issue.measured.h}: ${issue.selector}`
			: issue.type === "small-text" ? `${issue.measured.fontPx}px text: ${issue.selector}` : issue.type === "safe-area" ? `safe area ${JSON.stringify(issue.intrudesBy)}: ${issue.selector}` : `${issue.type}: ${issue.selector ?? ""}`;
		items.push({ shape: "rect", x: Math.max(0, rect.x), y: Math.max(0, rect.y), w: Math.max(4, rect.w), h: Math.max(4, rect.h), color, note: note.slice(0, 150) });
		if (items.length >= 14) break;
	}
	return { title, units: "px", items };
}

async function auditDevice(browser, base, device) {
	const touch = device.kind !== "desktop";
	const portrait = { width: device.w, height: device.h }, landscape = { width: Math.max(device.w, device.h), height: Math.min(device.w, device.h) };
	const states = touch ? [["portrait-initial", portrait], ["landscape", landscape], ["portrait-rotated", portrait], ["landscape-again", landscape]] : [["landscape", { width: device.w, height: device.h }]];
	const context = await browser.newContext({ viewport: states[0][1], deviceScaleFactor: device.dpr, isMobile: touch, hasTouch: touch, ...(device.ua ? { userAgent: device.ua } : {}) });
	const record = { id: device.id, label: device.label, kind: device.kind, dpr: device.dpr, ua: device.ua ?? null, states: {}, consoleErrors: [], startedAt: new Date().toISOString() };
	try {
		await context.route("**/healthz", route => route.fulfill({ status: 503, contentType: "text/plain", body: "responsive audit: offline preview" }));
		await context.addInitScript({ path: join(TOOL_DIR, "page", "audit.js") });
		const page = await context.newPage();
		page.on("pageerror", error => { if (record.consoleErrors.length < 20) record.consoleErrors.push(String(error).slice(0, 240)); });
		const cdp = await context.newCDPSession(page);
		for (const [index, [name, viewport]] of states.entries()) {
			const orientation = viewport.width > viewport.height ? "landscape" : "portrait";
			const insets = device.insets ? device.insets[orientation] ?? {} : {};
			if (index > 0) await page.setViewportSize(viewport);
			record.safeAreaEmulation = await setInsets(cdp, insets);
			if (index === 0) await page.goto(`${base}/?renderer=${renderer}`, { waitUntil: "load", timeout: 120000 });
			await page.bringToFront();
			let ready;
			if (orientation === "portrait" && touch) ready = await waitFor(page, () => !!document.querySelector(".mobile-web-app-overlay, #rotate-device") && (window.__xexAudit.isVisible(".mobile-web-app-overlay") || window.__xexAudit.isVisible("#rotate-device")), null, 20000, "portrait gate");
			else ready = await waitFor(page, () => window.__xexoria && window.__xexoria.scene && window.__xexoria.scene.getFrameId() > 90 && !window.__xexAudit.isVisible(".scene-loading")
				&& (window.__xexAudit.isVisible("#joystick") || window.__xexAudit.isVisible(".desktop-hotbar")), null, 150000, "game boot + HUD");
			await sleep(1500);
			const snapshot = await page.evaluate(options => window.__xexAudit.snapshot(options), { insets: { top: 0, right: 0, bottom: 0, left: 0, ...insets }, touch, minTarget: 44, minFont: 11, expectControls: touch && orientation === "landscape" });
			const stem = `${device.id}-${name}`;
			await page.screenshot({ path: join(shotsDir, `${stem}.jpg`), type: "jpeg", quality: 82, scale: "css" });
			const spec = annotateSpec(snapshot, `${device.label} · ${name} · ${viewport.width}x${viewport.height} @${device.dpr}`);
			writeFileSync(join(shotsDir, `${stem}.annotations.json`), JSON.stringify(spec, null, 1));
			if (spec.items.length) runPython("annotate.py", ["--image", join(shotsDir, `${stem}.jpg`), "--spec", join(shotsDir, `${stem}.annotations.json`), "--out", join(shotsDir, `${stem}-annotated.jpg`)]);
			record.states[name] = { viewport, orientation, insets, ready, screenshot: `screens/${stem}.jpg`, annotated: spec.items.length ? `screens/${stem}-annotated.jpg` : null, ...snapshot };
			const counts = snapshot.issues.reduce((acc, issue) => ({ ...acc, [issue.type]: (acc[issue.type] ?? 0) + 1 }), {});
			log(`  ${stem.padEnd(36)} ${viewport.width}x${viewport.height} ${ready ? "ready" : "NOT READY"} overlay=${snapshot.overlay?.selector ?? "-"} issues ${JSON.stringify(counts)}`);
		}
		if (touch) {
			const first = record.states.landscape, again = record.states["landscape-again"], diffs = [];
			if (first && again) {
				const before = new Map(first.widgets.map(widget => [widget.selector, widget.rect]));
				const after = new Map(again.widgets.map(widget => [widget.selector, widget.rect]));
				for (const [selector, rect] of before) {
					const other = after.get(selector);
					if (!other) diffs.push({ selector, change: "missing after rotation", before: rect });
					else if (["x", "y", "w", "h"].some(key => Math.abs(rect[key] - other[key]) > 2)) diffs.push({ selector, change: "moved/resized", before: rect, after: other });
				}
				for (const [selector, rect] of after) if (!before.has(selector)) diffs.push({ selector, change: "appeared after rotation", after: rect });
				if (again.scroll.maxScrollX > 0 || again.scroll.maxScrollY > 0) diffs.push({ selector: "document", change: "page scrolls after rotation", after: again.scroll });
			}
			const rotated = record.states["portrait-rotated"];
			if (rotated && !rotated.overlay) diffs.push({ selector: "#rotate-device / .mobile-web-app-overlay", change: "no portrait gate after rotating back" });
			record.orientationChange = { landscapeDiffs: diffs, ok: diffs.length === 0 };
		}
	} catch (error) {
		record.error = String(error?.stack ?? error).slice(0, 1200);
		log(`  ERROR ${device.id}: ${record.error.split("\n")[0]}`);
	} finally {
		record.finishedAt = new Date().toISOString();
		await context.close().catch(() => {});
	}
	return record;
}

function rank(devices) {
	const groups = new Map();
	for (const device of Object.values(devices)) {
		for (const [state, data] of Object.entries(device.states ?? {})) for (const issue of data.issues ?? []) {
			if (issue.severity === "info") continue;
			const key = `${issue.type}|${issue.selector ?? issue.a ?? ""}|${issue.b ?? ""}`;
			const group = groups.get(key) ?? { type: issue.type, severity: issue.severity, selector: issue.selector ?? null, a: issue.a ?? null, b: issue.b ?? null, label: issue.label ?? issue.labels ?? issue.sample ?? null, devices: new Set(), states: [], examples: [] };
			if (SEVERITY[issue.severity] > SEVERITY[group.severity]) group.severity = issue.severity;
			group.devices.add(device.id); group.states.push(`${device.id}:${state}`);
			if (group.examples.length < 3) group.examples.push({ device: device.id, state, viewport: `${data.viewport.width}x${data.viewport.height}@${data.viewport.dpr}`, measured: issue.measured ?? issue.intersection ?? null, extra: issue.intrudesBy ?? issue.outsideBy ?? (issue.pctOfSmaller !== undefined ? { pctOfSmaller: issue.pctOfSmaller } : null) });
			groups.set(key, group);
		}
		for (const diff of device.orientationChange?.landscapeDiffs ?? []) {
			const key = `orientation|${diff.selector}|${diff.change}`;
			const group = groups.get(key) ?? { type: "orientation-change", severity: "high", selector: diff.selector, label: diff.change, devices: new Set(), states: [], examples: [] };
			group.devices.add(device.id); if (group.examples.length < 3) group.examples.push({ device: device.id, before: diff.before ?? null, after: diff.after ?? null });
			groups.set(key, group);
		}
	}
	return [...groups.values()].map(group => ({ ...group, devices: [...group.devices], deviceCount: group.devices.size, score: SEVERITY[group.severity] * group.devices.size }))
		.sort((a, b) => b.score - a.score || b.deviceCount - a.deviceCount);
}

let lock = null, preview = null, chrome = null;
const started = Date.now();
try {
	if (!args.noLock) lock = await acquireGpuLock({ path: args.lock ?? DEFAULT_LOCK, owner: `claude-responsive-audit-pid${process.pid}-${new Date().toISOString()}` });
	const deadline = Date.now() + maxMinutes * 60000;
	await ensureFreeRam(1.5);
	if (args.dist) preview = await startPreview({ dist: resolve(args.dist), port: Number(args.port ?? 4310) });
	const base = preview?.url ?? args.url;
	chrome = await launchChrome({});
	log(`Chrome ${chrome.version}; ${selected.length} devices; renderer ${renderer}`);
	for (const device of selected) {
		if (results[device.id] && !results[device.id].error && args.resume) continue;
		if (Date.now() + 75000 > deadline) { log(`session budget (${maxMinutes} min) reached; rerun with --resume`); break; }
		log(`device ${device.id} (${device.label})`);
		results[device.id] = await auditDevice(chrome.browser, base, device);
		writeFileSync(resultPath, JSON.stringify({ devices: results }, null, 1));
	}
} finally {
	try { await chrome?.browser.close(); } catch { /* closed */ }
	try { await preview?.stop(); } catch (error) { log(`preview stop: ${error.message}`); }
	releaseGpuLock(lock);
}

const ranked = rank(results);
const receipt = args.dist ? readBuildReceipt(resolve(args.dist)) : null;
const report = {
	schema: "xexoria-responsive-audit/1", generatedAt: new Date().toISOString(), url: args.url ?? null, build: receipt ? { hash: receipt.buildHash, devHooks: receipt.devHooks } : null, git: gitState(),
	browser: chrome?.version ?? null, renderer, minutes: Math.round((Date.now() - started) / 6000) / 10,
	notes: ["Chrome device emulation is not Safari or a real phone: 100vh/dvh and toolbar behaviour, safe-area values, text autosizing, rAF throttling (Low Power Mode, 60 Hz cap) and WebGPU availability differ. Confirm on devices.",
		"Safe-area insets are emulated with CDP Emulation.setSafeAreaInsetsOverride when Chrome supports it (safeAreaEmulation per device) and always checked geometrically against the approximate inset bands.",
		"Approximate insets (CSS px, Home Screen web app): iPhone 11 48/34 portrait, 48+48/21 landscape; Dynamic Island iPhones 62/34 and 62+62/21; iPads 24/20; iPhone SE and Android 0.",
		"Offline preview (no game server); /healthz is answered 503 so the HUD boots locally. Screens are CSS-pixel JPEGs; *-annotated.jpg marks the issue boxes."],
	summary: { devices: Object.keys(results).length, errors: Object.values(results).filter(device => device.error).map(device => device.id),
		issueGroups: ranked.length, byType: ranked.reduce((acc, group) => ({ ...acc, [group.type]: (acc[group.type] ?? 0) + 1 }), {}) },
	ranked, devices: results,
};
writeFileSync(resultPath, JSON.stringify(report, null, 1));
const items = [];
for (const device of Object.values(results)) for (const [state, data] of Object.entries(device.states ?? {})) {
	if (state === "portrait-rotated") continue;
	items.push({ path: join(out, data.annotated ?? data.screenshot), label: `${device.label} · ${state}`, sublabel: `${data.viewport.width}x${data.viewport.height} @${device.dpr} · ${data.issues.filter(issue => issue.severity !== "info").length} issues${data.ready ? "" : " · NOT READY"}` });
}
if (items.length) {
	writeFileSync(join(out, "contact-sheet.items.json"), JSON.stringify(items, null, 1));
	runPython("contact_sheet.py", ["--items", join(out, "contact-sheet.items.json"), "--out", join(out, "contact-sheet.png"), "--cols", "4", "--thumb", "420", "--title", `Responsive audit · ${new Date().toISOString().slice(0, 16)} · ${renderer} · Chrome emulation (not Safari)`]);
}
log(`${ranked.length} issue groups; report ${relative(REPO, resultPath)}`);
for (const group of ranked.slice(0, 12)) log(`  [${group.severity}] ${group.type} ${group.selector ?? `${group.a} × ${group.b}`} · ${group.deviceCount} devices`);
