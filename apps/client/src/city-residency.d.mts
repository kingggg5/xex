export type CityLod = "near" | "mid" | "far";
export type CityPreset = "low" | "medium" | "high" | "ultra";
export interface CityPosition { x: number; z: number; }
export interface CityLodAsset {
	/** Conservative decoded CPU/GPU allocation; never substitute GLB bytes. */
	residentBytes: number;
	[key: string]: unknown;
}
export interface CityResidencyCell {
	id: string;
	bounds: { minX: number; maxX: number; minZ: number; maxZ: number };
	lods: Partial<Record<CityLod, CityLodAsset>>;
}
export interface CityResidencyProfile {
	nearDistance: number;
	midDistance: number;
	farDistance: number;
	hysteresisDistance: number;
	prefetchDistance: number;
	prefetchSeconds: number;
	maxPrefetchSpeed: number;
	teleportDistance: number;
	maxResidentBytes: number;
	maxResidentCells: number;
	maxInflightCells: number;
	preset?: CityPreset;
	formFactor?: string;
}
export interface CityResident { cellId: string; lod: CityLod; residentBytes?: number; }
export interface CityInflight extends CityResident { requestId: string; }
export interface CityResidencyPrevious {
	position?: CityPosition;
	selection?: Array<{ cellId: string; lod: CityLod }>;
}
export interface CityResidencySelection {
	cellId: string;
	lod: CityLod;
	distance: number;
	prefetch: boolean;
	state: "resident" | "loading" | "requested";
}
export interface CityResidencyPlan {
	selection: CityResidencySelection[];
	load: Array<{ cellId: string; lod: CityLod; residentBytes: number; reason: "approach" | "distance" }>;
	evict: Array<{ cellId: string; lod: CityLod; reason: string }>;
	cancel: Array<{ cellId: string; lod: CityLod; requestId: string; reason: string }>;
	retireAfterReady: Array<{ cellId: string; lod: CityLod; replacementLod: CityLod }>;
	rejected: Array<{ cellId: string; wantedLod: CityLod; reason: string }>;
	teleported: boolean;
	keepDistantFallback: true;
	budget: {
		accountedBytes: number; reservedBytes: number; residentCells: number;
		inflightCells: number; maxResidentBytes: number; maxResidentCells: number;
		maxInflightCells: number; withinBudget: boolean;
	};
	next: CityResidencyPrevious;
}
export function resolveCityResidencyProfile(preset?: CityPreset, context?: { formFactor?: "mobile" | "desktop" | "unknown" }): Readonly<CityResidencyProfile>;
export function planCityResidency(input: {
	cells: CityResidencyCell[];
	position: CityPosition;
	velocity?: CityPosition;
	resident?: CityResident[];
	inflight?: CityInflight[];
	previous?: CityResidencyPrevious;
	profile?: CityResidencyProfile;
	reservedBytes?: number;
}): CityResidencyPlan;
