export type GraphicsPreset = "low" | "medium" | "high" | "ultra";
export type GraphicsFormFactor = "mobile" | "desktop" | "unknown";

export interface GraphicsPreferenceChange {
	readonly preference: GraphicsPreset | null;
}

export interface GraphicsDeviceContext {
	/** Supplied by the host from interaction/display context; never inferred from user-agent strings. */
	formFactor?: GraphicsFormFactor;
	/** CSS-pixel canvas size used to enforce the preset's output-pixel ceiling. */
	width?: number;
	height?: number;
	devicePixelRatio?: number;
}

export interface GraphicsPresetSpec {
	readonly label: string;
	readonly maxDpr: number;
	readonly resolutionScale: number;
	readonly targetFps: number;
	/** Highest cap Auto may probe; 0 follows the detected refresh rate. Fixed opt-ins use the frame-rate policy. */
	readonly autoCeilingFps: number;
	readonly shadowMapSize: number;
	/** One means a single shadow map; 2–4 are cascaded shadow maps. */
	readonly cascades: number;
	readonly shadowDistance: number;
	readonly glowEnabled: boolean;
	readonly vegetationDensity: number;
	readonly vegetationDistanceFactor: number;
	readonly weatherParticleBudget: number;
	readonly waterDetail: number;
	readonly maxRenderPixels: number;
}

export interface ResolvedGraphicsPreset extends GraphicsPresetSpec {
	/** Values after device-form-factor ceilings have been applied. */
	readonly preset: GraphicsPreset;
	/** Null means Auto/recommended is selected. */
	readonly preference: GraphicsPreset | null;
	readonly recommendedPreset: GraphicsPreset;
	readonly formFactor: GraphicsFormFactor;
	readonly devicePixelRatio: number;
	readonly cssWidth: number | null;
	readonly cssHeight: number | null;
	readonly effectiveDpr: number;
	/** Babylon.js hardware scaling level: the reciprocal of effectiveDpr. */
	readonly hardwareScalingLevel: number;
	readonly renderWidth: number | null;
	readonly renderHeight: number | null;
	readonly renderPixelCount: number | null;
	readonly pixelBudgetLimited: boolean;
}

export const GRAPHICS_PRESET_NAMES: readonly GraphicsPreset[];
export const GRAPHICS_PRESETS: Readonly<Record<GraphicsPreset, GraphicsPresetSpec>>;
export const GRAPHICS_PREFERENCE_STORAGE_KEY: string;
export const GRAPHICS_PREFERENCE_EVENT: "aetherfield:graphics-preference-change";

/** Returns the explicit local preference, or null for Auto/recommended. */
export function getGraphicsPreference(): GraphicsPreset | null;
/** Persists a preset, or null to reset to Auto/recommended. */
export function setGraphicsPreference(preset: GraphicsPreset | null): GraphicsPreset | null;
/** Subscribes to changes and returns an unsubscribe function; no initial event is sent. */
export function subscribeGraphicsPreference(listener: (change: GraphicsPreferenceChange) => void): () => void;
/** Resolves a preset and a pixel-bounded Babylon hardware scaling level from plain device context. */
export function resolveGraphicsPreset(preset: GraphicsPreset | null, deviceContext?: GraphicsDeviceContext): ResolvedGraphicsPreset;
