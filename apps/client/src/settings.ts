/**
 * D-14 settings panel: UI scale, camera shake, damage flash and volume
 * preferences, persisted in localStorage under "aetherfield_settings".
 *
 * - uiScale drives the --ui-scale CSS variable on <html> (see style.css).
 * - shake/flash are persisted flags; the integrator reads them via getPrefs().
 * - volume: audio.ts (CombatAudio) currently exposes only setMuted/toggleMuted
 *   — there is no master volume API yet, so applyVolume() is a deliberately
 *   empty INTEGRATOR hook (marked below) to wire once one exists.
 */

import { getGraphicsPreference, setGraphicsPreference, subscribeGraphicsPreference, resolveGraphicsPreset, GRAPHICS_PRESET_NAMES, GRAPHICS_PRESETS } from "./graphics-quality.mjs";
import type { GraphicsPreset } from "./graphics-quality.mjs";
import { getEnvironmentPreference, setEnvironmentPreference, subscribeEnvironmentPreference } from "./world-environment-state.mjs";
import type { WeatherMode } from "./world-environment-state.mjs";

export interface Prefs {
	uiScale: number;
	shake: boolean;
	flash: boolean;
	volume: number;
}

export const DEFAULT_PREFS: Readonly<Prefs> = { uiScale: 1, shake: true, flash: true, volume: 0.8 };

const MIN_UI_SCALE = 0.85;
const MAX_UI_SCALE = 1.25;
const SETTINGS_KEY = "aetherfield_settings";

let appliedPrefs: Prefs | null = null;

// D-06 convention (main.ts): Thai copy when the browser language is Thai.
const THAI = typeof navigator === "undefined" ? false : navigator.language.toLowerCase().startsWith("th");

const COPY = THAI
	? {
		uiScale: "ขนาดหน้าจอ UI",
		shake: "สั่นกล้อง",
		flash: "แฟลชจอเมื่อได้รับดาเมจ",
		volume: "ระดับเสียง",
		reset: "คืนค่าเริ่มต้น",
		note: "การตั้งค่าใช้งานทันทีและบันทึกไว้บนอุปกรณ์นี้เท่านั้น",
	}
	: {
		uiScale: "UI scale",
		shake: "Camera shake",
		flash: "Damage flash",
		volume: "Volume",
		reset: "Reset to defaults",
		note: "Settings apply immediately and are stored on this device only.",
	};

export function loadPrefs(): Prefs {
	const storage = safeStorage();
	if (!storage) return { ...DEFAULT_PREFS };
	const raw = storage.getItem(SETTINGS_KEY);
	if (!raw) return { ...DEFAULT_PREFS };
	try {
		const parsed: unknown = JSON.parse(raw);
		if (typeof parsed !== "object" || parsed === null) return { ...DEFAULT_PREFS };
		return normalizePrefs(parsed);
	} catch {
		return { ...DEFAULT_PREFS };
	}
}

export function savePrefs(prefs: Prefs): void {
	const next = normalizePrefs(prefs);
	appliedPrefs = next;
	const storage = safeStorage();
	if (!storage) return;
	try {
		storage.setItem(SETTINGS_KEY, JSON.stringify(next));
	} catch {
		// Storage may be unavailable (private browsing); prefs stay session-only.
	}
}

/** Latest applied preferences, for the integrator (shake/flash gating etc.). */
export function getPrefs(): Prefs {
	if (appliedPrefs === null) appliedPrefs = loadPrefs();
	return { ...appliedPrefs };
}

/** Applies uiScale to the document and forwards volume to applyVolume(). */
export function applyPrefs(prefs: Prefs): void {
	const next = normalizePrefs(prefs);
	appliedPrefs = next;
	if (typeof document !== "undefined") {
		document.documentElement.style.setProperty("--ui-scale", next.uiScale.toFixed(2));
	}
	applyVolume(next);
}

/**
 * INTEGRATOR HOOK (not wired yet): CombatAudio in audio.ts has no master
 * volume API today (only setMuted/toggleMuted with a hardcoded gain). Once
 * one exists (e.g. sound.setVolume(prefs.volume)), call it from here.
 * Called by applyPrefs() on load and on every settings change.
 */
export function applyVolume(prefs: Prefs): void {
	void prefs;
}

/**
 * Renders the settings panel into `container`. Changes call onSave immediately
 * (persist + apply) so the live preview survives closing the modal.
 */
export function renderSettingsPanel(container: HTMLElement, prefs: Prefs, onSave: (next: Prefs) => void): () => void {
	let releaseControls = (): void => {};
	let disposed = false;
	const draw = (next: Prefs): void => {
		if (disposed) return;
		releaseControls();
		const working = normalizePrefs(next);
		container.replaceChildren();
		const commit = (): void => onSave({ ...working });
		container.append(rangeRow(COPY.uiScale, "settings-ui-scale", working.uiScale, MIN_UI_SCALE, MAX_UI_SCALE, 0.05,
			(value) => { working.uiScale = value; }, () => `${Math.round(working.uiScale * 100)}%`, commit));
		container.append(toggleRow(COPY.shake, "settings-shake", working.shake, (value) => { working.shake = value; commit(); }));
		container.append(toggleRow(COPY.flash, "settings-flash", working.flash, (value) => { working.flash = value; commit(); }));
		container.append(rangeRow(COPY.volume, "settings-volume", working.volume, 0, 1, 0.05,
			(value) => { working.volume = value; }, () => `${Math.round(working.volume * 100)}%`, commit));
		releaseControls = renderEnvironmentControls(container);
		const reset = document.createElement("button");
		reset.type = "button";
		reset.className = "dialogue-choice settings-reset";
		reset.textContent = COPY.reset;
		reset.addEventListener("click", () => {
			const defaults = { ...DEFAULT_PREFS };
			onSave(defaults);
			setGraphicsPreference(null);
			setEnvironmentPreference({ weather: "auto", cycle: true });
			draw(defaults);
		});
		container.append(reset, el("p", "econ-note", COPY.note));
	};
	draw(prefs);
	return () => { disposed = true; releaseControls(); };
}

function renderEnvironmentControls(container: HTMLElement): () => void {
	const graphics = document.createElement("select");
	graphics.id = "settings-graphics";
	graphics.append(new Option(THAI ? "อัตโนมัติ (แนะนำ)" : "Auto (recommended)", "auto"));
	for (const preset of GRAPHICS_PRESET_NAMES) graphics.append(new Option(GRAPHICS_PRESETS[preset].label, preset));
	const graphicsRow = selectRow(THAI ? "คุณภาพภาพ" : "Graphics quality", graphics);
	const summary = el("p", "settings-summary");
	summary.id = "settings-graphics-summary";
	summary.setAttribute("role", "status");
	graphics.setAttribute("aria-describedby", summary.id);
	const weather = document.createElement("select");
	weather.id = "settings-weather";
	for (const [value, english, thai] of [
		["auto", "Automatic", "อัตโนมัติ"], ["clear", "Clear", "ฟ้าโปร่ง"], ["cloudy", "Cloudy", "เมฆมาก"],
		["rain", "Rain", "ฝน"], ["fog", "Fog", "หมอก"],
	]) weather.append(new Option(THAI ? thai : english, value));
	const weatherRow = selectRow(THAI ? "สภาพอากาศ" : "Weather", weather);
	const cycleRow = toggleRow(THAI ? "วงจรกลางวันและกลางคืน" : "Day and night cycle", "settings-day-night", getEnvironmentPreference().cycle,
		(value) => setEnvironmentPreference({ cycle: value }));
	const cycle = cycleRow.querySelector<HTMLInputElement>("input")!;
	const refreshGraphics = (): void => {
		const preference = getGraphicsPreference();
		graphics.value = preference ?? "auto";
		const mobile = window.matchMedia("(max-width: 767px), (pointer: coarse) and (max-width: 900px)").matches;
		const active = resolveGraphicsPreset(preference, { formFactor: mobile ? "mobile" : "desktop", width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio });
		const target = THAI ? `เป้าหมาย ${active.targetFps} FPS` : `${active.targetFps} FPS target`;
		const automatic = preference === null ? (THAI ? "แนะนำสำหรับหน้าจอนี้: " : "Recommended for this screen: ") : "";
		summary.textContent = `${automatic}${active.label} · ${target}${mobile ? (THAI ? " · ปรับรายละเอียดสำหรับมือถือ" : " · Mobile detail limits") : ""}`;
	};
	const refreshEnvironment = (): void => {
		const preference = getEnvironmentPreference();
		weather.value = preference.weather;
		cycle.checked = preference.cycle;
	};
	graphics.addEventListener("change", () => setGraphicsPreference(graphics.value === "auto" ? null : graphics.value as GraphicsPreset));
	weather.addEventListener("change", () => setEnvironmentPreference({ weather: weather.value as WeatherMode }));
	const stopGraphics = subscribeGraphicsPreference(refreshGraphics);
	const stopEnvironment = subscribeEnvironmentPreference(refreshEnvironment);
	let resizeTimer = 0;
	const resized = (): void => { window.clearTimeout(resizeTimer); resizeTimer = window.setTimeout(refreshGraphics, 80); };
	window.addEventListener("resize", resized, { passive: true });
	refreshGraphics(); refreshEnvironment();
	container.append(graphicsRow, summary, weatherRow, cycleRow);
	return () => { stopGraphics(); stopEnvironment(); window.removeEventListener("resize", resized); window.clearTimeout(resizeTimer); };
}

function selectRow(label: string, select: HTMLSelectElement): HTMLElement {
	const row = el("div", "settings-row settings-choice");
	const labelNode = document.createElement("label");
	labelNode.htmlFor = select.id;
	labelNode.textContent = label;
	row.append(labelNode, select);
	return row;
}

function rangeRow(
	label: string,
	id: string,
	initial: number,
	min: number,
	max: number,
	step: number,
	apply: (value: number) => void,
	format: () => string,
	commit: () => void,
): HTMLElement {
	const row = el("div", "settings-row");
	const labelNode = document.createElement("label");
	labelNode.htmlFor = id;
	labelNode.textContent = label;
	const input = document.createElement("input");
	input.type = "range";
	input.id = id;
	input.min = String(min);
	input.max = String(max);
	input.step = String(step);
	input.value = String(initial);
	const value = document.createElement("output");
	value.className = "settings-value";
	value.textContent = format();
	input.addEventListener("input", () => {
		apply(Number(input.value));
		value.textContent = format();
		commit();
	});
	row.append(labelNode, input, value);
	return row;
}

function toggleRow(label: string, id: string, initial: boolean, apply: (value: boolean) => void): HTMLElement {
	const row = el("div", "settings-row");
	const labelNode = document.createElement("label");
	labelNode.htmlFor = id;
	labelNode.textContent = label;
	const input = document.createElement("input");
	input.type = "checkbox";
	input.id = id;
	input.checked = initial;
	input.addEventListener("change", () => apply(input.checked));
	row.append(labelNode, input);
	return row;
}

function normalizePrefs(value: unknown): Prefs {
	const source = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
	return {
		uiScale: clamp(finiteNumber(source.uiScale, DEFAULT_PREFS.uiScale), MIN_UI_SCALE, MAX_UI_SCALE),
		shake: typeof source.shake === "boolean" ? source.shake : DEFAULT_PREFS.shake,
		flash: typeof source.flash === "boolean" ? source.flash : DEFAULT_PREFS.flash,
		volume: clamp(finiteNumber(source.volume, DEFAULT_PREFS.volume), 0, 1),
	};
}

function safeStorage(): Storage | null {
	try {
		return typeof window === "undefined" ? null : window.localStorage;
	} catch {
		return null;
	}
}

function finiteNumber(value: unknown, fallback: number): number {
	return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, min: number, max: number): number {
	return Math.min(max, Math.max(min, value));
}

function el(tag: string, className: string, text?: string): HTMLElement {
	const node = document.createElement(tag);
	node.className = className;
	if (text !== undefined) node.textContent = text;
	return node;
}
