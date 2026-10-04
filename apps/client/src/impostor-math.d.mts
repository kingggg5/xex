export interface ImpostorGridParams {
	azimuth: number;
	elevation: number;
	elMin: number;
	elStep: number;
	az0: number;
	azSign: number;
}
export interface ImpostorFrameCoordinates { a0: number; a1: number; wa: number; e0: number; e1: number; we: number }
export interface ImpostorPageLike { cols: number; rows: number }
export interface ImpostorObjectLike { col: number; row: number; center_from_origin: [number, number, number] }

export function gridParams(manifest: { grid: { azimuth: number; elevation: number; el_min_deg: number; el_max_deg: number; az0_angle_rad: number; az_sign: number } }): ImpostorGridParams;
export function frameDirection(params: ImpostorGridParams, az: number, el: number): [number, number, number];
export function frameCoordinates(params: ImpostorGridParams, x: number, y: number, z: number): ImpostorFrameCoordinates;
export function toLocalDirection(yaw: number, x: number, y: number, z: number): [number, number, number];
export function cellRect(page: ImpostorPageLike, object: ImpostorObjectLike, az: number, el: number): [number, number, number, number];
export function cardCentre(object: ImpostorObjectLike, x: number, y: number, z: number, yaw?: number, scale?: number): [number, number, number];
export function crossFade(distance: number, swap: number, band: number): number;
export function viewLightCompensation(a: number, b: number, view: [number, number, number], light: [number, number, number], min?: number, max?: number): number;

export interface TreeLodProfile { shadowDistance?: number; renderPixelCount?: number | null; preset?: string; vegetationDensity?: number }
/** A type alias (not an interface) so it stays assignable to plain-data metadata records (lookdev evidence). */
export type TreeLodPlan = { lod1Coverage: number; lod1Band: number; swap: number; band: number; end: number; density: number; force: "lod0" | "lod1" | "impostor" | "none" | null };
export interface TreeLodState { lod0: [number, number] | null; lod1: [number, number] | null; card: [number, number] | null }
export const TREE_DETAIL_DISTANCE: Readonly<Record<"low" | "medium" | "high" | "ultra" | "epic", number>>;
export const TREE_LOD1_COVERAGE: number;
export const TREE_LOD1_BAND: number;
export const TREE_SWAP_BAND: number;
export function coverageScale(renderPixels: number | null | undefined): number;
export function coverageDistance(radius: number, coverage: number, fov: number, aspect: number): number;
export function treeLodPlan(profile: TreeLodProfile, overrides?: { swap?: number; force?: "lod0" | "lod1" | "impostor" | "none" | null }): TreeLodPlan;
export function treeLod1Distance(plan: TreeLodPlan, radius: number, fov: number, aspect: number): number;
export function treeLodState(distance: number, plan: TreeLodPlan, lod1Distance: number, hasCard?: boolean): TreeLodState;
export function densityKeeps(index: number, density: number): boolean;
