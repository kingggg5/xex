export interface GroundedPosition { x: number; y: number; z: number; }
export interface CollisionBox { minX: number; maxX: number; minY: number; maxY: number; minZ: number; maxZ: number; }
/** Opaque immutable field; only parseCityTraversal can create queryable fields. */
export interface CityTraversalField {
	readonly schema: "xexoria.city-traversal/1" | "xexoria.city-traversal/2";
	readonly worldSupport: boolean;
	readonly bounds: Readonly<{ minX: number; maxX: number; minZ: number; maxZ: number }>;
	readonly maxStepM: number;
	readonly maxSlopeDegrees: 50;
	readonly epsilonM: number;
	readonly substepM: number;
	readonly feetOffsetM: number;
	readonly stats: Readonly<{ vertexCount: number; triangleCount: number; skippedTriangles: number; blockerCount: number; indexReferences: number; indexCells: number }>;
}
export function parseCityTraversal(input: unknown, worldExtent?: number): CityTraversalField;
/** Raw support height. Inside city gaps -> null. Outside city -> authored support only with v2/worldSupport, otherwise 0. */
export function sampleCityHeight(field: CityTraversalField | null | undefined, x: number, z: number): number | null;
/** Returned y excludes feetOffsetM. The render layer applies that offset once. */
export function moveGroundedCapsule(position: { x: number; z: number; y?: number }, delta: { x: number; z: number }, radius: number, height: number, boxes: readonly CollisionBox[], worldLimit: number, field?: CityTraversalField | null): GroundedPosition;
