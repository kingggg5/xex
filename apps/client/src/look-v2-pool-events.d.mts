import type { Scene } from '@babylonjs/core/scene';
import type { AbstractMesh } from '@babylonjs/core/Meshes/abstractMesh';
export function markLookV2DressingReady(scene: Scene): void;
export function notifyLookV2PoolEmitterChanged(mesh: AbstractMesh): void;
export function subscribeLookV2PoolEvents(scene: Scene, listener: (mesh: AbstractMesh | null) => void): () => void;
