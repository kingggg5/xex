import type { Scene } from '@babylonjs/core/scene';
import type { AbstractMesh } from '@babylonjs/core/Meshes/abstractMesh';
export type LookV2PoolType = 'lamp' | 'brazier' | 'fire';
export interface LookV2PoolAnchor { x: number; y: number; z: number; type: LookV2PoolType }
export const MAX_LOOK_V2_POOLS: 64;
export const LOOK_V2_POOL_RADII: Readonly<Record<LookV2PoolType, number>>;
export const LOOK_V2_POOL_DIAMETERS: Readonly<Record<LookV2PoolType, number>>;
export function lookV2PoolAlpha(u: number, v: number): number;
export function createLookV2PoolPixels(size?: number): Uint8ClampedArray;
export function writeLookV2PoolMatrices(anchors: readonly LookV2PoolAnchor[], target: Float32Array): number;
export function createLookV2PoolRegistry(scene: Scene, excludedMesh?: AbstractMesh | null): {
	snapshot(): LookV2PoolAnchor[];
	dispose(): void;
	stats(): { fullScans: number; evaluations: number; boundsReads: number; emitters: number; pending: number; anchors: number };
};
