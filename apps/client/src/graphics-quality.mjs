/**
 * Pure graphics-quality policy. Keep this module independent of Babylon so
 * settings UI can persist a small preference and the renderer can resolve it
 * into engine values at startup or after a settings change.
 *
 * The mobile recommendation is a conservative 30 fps starting point for an
 * older mobile-class device. It is not a per-model benchmark or FPS guarantee.
 * Callers supply form factor explicitly; this module does not infer hardware
 * from user-agent strings.
 */

export const GRAPHICS_PRESET_NAMES = Object.freeze(["low", "medium", "high", "ultra"]);
export const GRAPHICS_PREFERENCE_STORAGE_KEY = "aetherfield_graphics_quality_v1";
export const GRAPHICS_PREFERENCE_EVENT = "aetherfield:graphics-preference-change";

const STORAGE_VERSION = 1;
const MAX_CSS_DIMENSION = 32_768;
// These are explicit safety ceilings for mobile-class contexts, not device
// certification. The host supplies formFactor; model names are not detected.
const MOBILE_MAX_DPR = 1.5;
const MOBILE_MAX_RENDER_PIXELS = 3_000_000;
const MOBILE_MAX_SHADOW_MAP_SIZE = 1024;
const MOBILE_MAX_CASCADES = 2;
const MOBILE_TARGET_FPS = 30;
const MOBILE_AUTO_CEILING_FPS = 60;
const MOBILE_RESOLUTION_SCALES = Object.freeze({ low: 0.88, medium: 0.94, high: 0.94, ultra: 1 });
const subscribers = new Set();
let sessionPreference;

/** @type {Readonly<Record<GraphicsPreset, Readonly<GraphicsPresetSpec>>>} */
export const GRAPHICS_PRESETS = Object.freeze({
	low: Object.freeze({
		label: "Low",
		maxDpr: 1,
		resolutionScale: 0.88,
		targetFps: 30,
		autoCeilingFps: 30,
		shadowMapSize: 512,
		cascades: 1,
		shadowDistance: 55,
		glowEnabled: false,
		vegetationDensity: 0.45,
		vegetationDistanceFactor: 0.5,
		weatherParticleBudget: 24,
		waterDetail: 0.3,
		maxRenderPixels: 1_310_720,
	}),
	medium: Object.freeze({
		label: "Medium",
		maxDpr: 1.25,
		resolutionScale: 0.94,
		targetFps: 30,
		autoCeilingFps: 30,
		shadowMapSize: 1024,
		cascades: 2,
		shadowDistance: 85,
		glowEnabled: true,
		vegetationDensity: 0.7,
		vegetationDistanceFactor: 0.75,
		weatherParticleBudget: 64,
		waterDetail: 0.6,
		maxRenderPixels: 2_621_440,
	}),
	high: Object.freeze({
		label: "High",
		maxDpr: 1.5,
		resolutionScale: 1,
		targetFps: 60,
		autoCeilingFps: 0,
		shadowMapSize: 2048,
		cascades: 3,
		shadowDistance: 130,
		glowEnabled: true,
		vegetationDensity: 1,
		vegetationDistanceFactor: 1,
		weatherParticleBudget: 144,
		waterDetail: 1,
		maxRenderPixels: 5_529_600,
	}),
	ultra: Object.freeze({
		label: "Ultra",
		maxDpr: 2,
		resolutionScale: 1,
		targetFps: 60,
		autoCeilingFps: 0,
		shadowMapSize: 4096,
		cascades: 4,
		shadowDistance: 190,
		glowEnabled: true,
		vegetationDensity: 1.25,
		vegetationDistanceFactor: 1.25,
		weatherParticleBudget: 288,
		waterDetail: 1.5,
		maxRenderPixels: 11_059_200,
	}),
});

/**
 * Returns the user's explicit preset, or null when Auto/recommended is active.
 * Malformed, old-version, and inaccessible storage safely behave as Auto.
 * @returns {GraphicsPreset | null}
 */
export function getGraphicsPreference() {
	if (sessionPreference !== undefined) return sessionPreference;
	sessionPreference = readStoredPreference();
	return sessionPreference;
}

/**
 * Persists a preset or null for Auto, while retaining the choice for this
 * session if localStorage is blocked or quota-limited.
 * @param {GraphicsPreset | null} preset
 * @returns {GraphicsPreset | null}
 */
export function setGraphicsPreference(preset) {
	assertPreference(preset);
	const previous = getGraphicsPreference();
	sessionPreference = preset;
	writeStoredPreference(preset);
	if (previous !== preset) emitPreferenceChange(preset);
	return preset;
}

/**
 * Subscribes to same-page preference changes. The callback receives only a
 * primitive DTO and is not invoked immediately. Call the returned function to
 * unsubscribe.
 * @param {(change: GraphicsPreferenceChange) => void} listener
 * @returns {() => void}
 */
export function subscribeGraphicsPreference(listener) {
	if (typeof listener !== "function") throw new TypeError("Graphics preference listener must be a function.");
	subscribers.add(listener);
	let subscribed = true;
	return () => {
		if (!subscribed) return;
		subscribed = false;
		subscribers.delete(listener);
	};
}

/**
 * Resolves Auto or a requested preset using caller-provided device context.
 * `width` and `height` are CSS-pixel canvas dimensions. The returned
 * `hardwareScalingLevel` follows Babylon's convention: smaller values render
 * more pixels; the value is the reciprocal of effective DPR.
 *
 * @param {GraphicsPreset | null} preset
 * @param {GraphicsDeviceContext} [deviceContext]
 * @returns {ResolvedGraphicsPreset}
 */
export function resolveGraphicsPreset(preset, deviceContext = {}) {
	assertPreference(preset);
	const context = typeof deviceContext === "object" && deviceContext !== null ? deviceContext : {};
	const formFactor = normalizeFormFactor(context.formFactor);
	const recommendedPreset = recommendPreset(formFactor);
	const selectedPreset = preset ?? recommendedPreset;
	const spec = applyPlatformCeilings(GRAPHICS_PRESETS[selectedPreset], selectedPreset, formFactor);
	const devicePixelRatio = positiveFinite(context.devicePixelRatio, 1);
	const requestedDpr = Math.min(devicePixelRatio, spec.maxDpr) * spec.resolutionScale;
	const width = dimension(context.width);
	const height = dimension(context.height);
	let effectiveDpr = requestedDpr;
	if (width !== null && height !== null) {
		const budgetDpr = Math.sqrt(spec.maxRenderPixels / (width * height));
		effectiveDpr = Math.min(effectiveDpr, budgetDpr);
	}
	// Both inputs are positive, and the per-tier pixel budget is positive.
	effectiveDpr = Math.max(Number.EPSILON, effectiveDpr);
	const renderWidth = width === null || height === null ? null : Math.max(1, Math.floor(width * effectiveDpr));
	const renderHeight = width === null || height === null ? null : Math.max(1, Math.floor(height * effectiveDpr));
	const renderPixelCount = renderWidth === null || renderHeight === null ? null : renderWidth * renderHeight;

	return Object.freeze({
		...spec,
		preset: selectedPreset,
		preference: preset,
		recommendedPreset,
		formFactor,
		devicePixelRatio,
		cssWidth: width,
		cssHeight: height,
		effectiveDpr,
		hardwareScalingLevel: 1 / effectiveDpr,
		renderWidth,
		renderHeight,
		renderPixelCount,
		pixelBudgetLimited: effectiveDpr < requestedDpr,
	});
}

/** @param {Readonly<GraphicsPresetSpec>} spec @param {GraphicsPreset} preset @param {GraphicsFormFactor} formFactor */
function applyPlatformCeilings(spec, preset, formFactor) {
	if (formFactor !== "mobile") return spec;
	return Object.freeze({
		...spec,
		maxDpr: Math.min(spec.maxDpr, MOBILE_MAX_DPR),
		resolutionScale: Math.min(spec.resolutionScale, MOBILE_RESOLUTION_SCALES[preset]),
		targetFps: Math.min(spec.targetFps, MOBILE_TARGET_FPS),
		autoCeilingFps: Math.min(spec.autoCeilingFps || Infinity, MOBILE_AUTO_CEILING_FPS),
		shadowMapSize: Math.min(spec.shadowMapSize, MOBILE_MAX_SHADOW_MAP_SIZE),
		cascades: Math.min(spec.cascades, MOBILE_MAX_CASCADES),
		maxRenderPixels: Math.min(spec.maxRenderPixels, MOBILE_MAX_RENDER_PIXELS),
	});
}

/** @param {unknown} value */
function assertPreference(value) {
	if (value !== null && !isGraphicsPreset(value)) {
		throw new RangeError(`Unknown graphics preset: ${String(value)}`);
	}
}

/** @param {unknown} value @returns {value is GraphicsPreset} */
function isGraphicsPreset(value) {
	return typeof value === "string" && Object.hasOwn(GRAPHICS_PRESETS, value);
}

/** @param {unknown} value @returns {GraphicsFormFactor} */
function normalizeFormFactor(value) {
	return value === "mobile" || value === "desktop" ? value : "unknown";
}

/** @param {GraphicsFormFactor} formFactor @returns {GraphicsPreset} */
function recommendPreset(formFactor) {
	if (formFactor === "mobile") return "medium";
	if (formFactor === "desktop") return "high";
	return "medium";
}

/** @param {unknown} value @returns {number} */
function positiveFinite(value, fallback) {
	return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback;
}

/** @param {unknown} value @returns {number | null} */
function dimension(value) {
	if (typeof value !== "number" || !Number.isFinite(value) || value < 1) return null;
	if (value > MAX_CSS_DIMENSION) throw new RangeError(`Canvas dimension exceeds ${MAX_CSS_DIMENSION} CSS pixels.`);
	return Math.floor(value);
}

function readStoredPreference() {
	const storage = safeStorage();
	if (!storage) return null;
	try {
		const raw = storage.getItem(GRAPHICS_PREFERENCE_STORAGE_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw);
		if (typeof parsed !== "object" || parsed === null || parsed.version !== STORAGE_VERSION) return null;
		return parsed.preference === null || isGraphicsPreset(parsed.preference) ? parsed.preference : null;
	} catch {
		return null;
	}
}

/** @param {GraphicsPreset | null} preference */
function writeStoredPreference(preference) {
	const storage = safeStorage();
	if (!storage) return;
	try {
		if (preference === null && typeof storage.removeItem === "function") {
			try {
				storage.removeItem(GRAPHICS_PREFERENCE_STORAGE_KEY);
				return;
			} catch {
				// Some storage adapters permit writes but reject removals; persist Auto explicitly.
			}
		}
		storage.setItem(GRAPHICS_PREFERENCE_STORAGE_KEY, JSON.stringify({ version: STORAGE_VERSION, preference }));
	} catch {
		// The in-memory preference remains active when storage is unavailable.
	}
}

function safeStorage() {
	try {
		const storage = globalThis.localStorage;
		return storage && typeof storage.getItem === "function" && typeof storage.setItem === "function" ? storage : null;
	} catch {
		return null;
	}
}

/** @param {GraphicsPreset | null} preference */
function emitPreferenceChange(preference) {
	const detail = Object.freeze({ preference });
	for (const listener of [...subscribers]) {
		if (!subscribers.has(listener)) continue;
		try {
			listener(detail);
		} catch (error) {
			try {
				if (typeof globalThis.reportError === "function") globalThis.reportError(error);
			} catch {
				// Listener failures cannot prevent the remaining subscribers from updating.
			}
		}
	}
	try {
		if (typeof window !== "undefined" && typeof CustomEvent === "function") {
			window.dispatchEvent(new CustomEvent(GRAPHICS_PREFERENCE_EVENT, { detail }));
		}
	} catch {
		// Preference persistence and local listeners do not depend on a DOM.
	}
}

/** @typedef {"low" | "medium" | "high" | "ultra"} GraphicsPreset */
/** @typedef {"mobile" | "desktop" | "unknown"} GraphicsFormFactor */
/** @typedef {{ preference: GraphicsPreset | null }} GraphicsPreferenceChange */
/** @typedef {{ formFactor?: GraphicsFormFactor, width?: number, height?: number, devicePixelRatio?: number }} GraphicsDeviceContext */
/** @typedef {Readonly<{label: string, maxDpr: number, resolutionScale: number, targetFps: number, autoCeilingFps: number, shadowMapSize: number, cascades: number, shadowDistance: number, glowEnabled: boolean, vegetationDensity: number, vegetationDistanceFactor: number, weatherParticleBudget: number, waterDetail: number, maxRenderPixels: number}> & {preset: GraphicsPreset, preference: GraphicsPreset | null, recommendedPreset: GraphicsPreset, formFactor: GraphicsFormFactor, devicePixelRatio: number, cssWidth: number | null, cssHeight: number | null, effectiveDpr: number, hardwareScalingLevel: number, renderWidth: number | null, renderHeight: number | null, renderPixelCount: number | null, pixelBudgetLimited: boolean}> ResolvedGraphicsPreset */
