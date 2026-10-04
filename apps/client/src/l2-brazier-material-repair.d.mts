import type { Mesh } from '@babylonjs/core/Meshes/mesh';
import type { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
export const L2_TRIPOD_PINS: readonly string[];
export function selectL2BrazierEntries<T extends { id: string; asset_id: string; target_height?: number; anchor_at_pivot?: boolean }>(entries: readonly T[], assets: ReadonlyMap<string, { id: string; bounds: { min: number[]; max: number[] }; lods: { tris: number; sha256?: string }[] }>): T[];
export function createL2BrazierRepairParts(source: Mesh, assetId: string, entryIds: readonly string[]): null | {
  parts: Mesh[]; materials: PBRMaterial[]; diagnostics: { assetId: string; entryIds: string[]; coalTriangles: number; extraTextures: 0; extraLights: 0; extraAnchors: 0; emission: number[]; animatedFlame: false; coalLift: number; rimY: number; raisedCoalTop: number; bodyTriangles: number; bodyFacesRemoved: 0 }; dispose(): void;
};
