import type { Mesh } from '@babylonjs/core/Meshes/mesh.js';
export type DressingVertexPackingResult =
  | { readonly packed: false; readonly reason: 'empty-mesh' | 'no-color'; readonly vertexCount: number }
  | { readonly packed: true; readonly vertexCount: number; readonly colorSize: 3 | 4;
      readonly strideFloats: number; readonly attributes: readonly string[]; readonly allocationCount: 1 };
/** Call after vertex authoring/colour restore and after every makeGeometryUnique(). Tangent/UV2 remain caller-owned. */
export function packDressingVertexBuffers(mesh: Mesh): DressingVertexPackingResult;
