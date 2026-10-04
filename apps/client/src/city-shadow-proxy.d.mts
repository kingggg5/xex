import type { Mesh } from '@babylonjs/core/Meshes/mesh';
import type { Material } from '@babylonjs/core/Materials/material';
import type { Scene } from '@babylonjs/core/scene';
import type { ShadowGenerator } from '@babylonjs/core/Lights/Shadows/shadowGenerator';
import type { SubMesh } from '@babylonjs/core/Meshes/subMesh';
export interface CityShadowProxyOptions {
  expectedSourceName: string; runtimeSha256: string; expectedGeometryFingerprint?: string;
  createMesh(name: string, scene: Scene): Mesh;
  createMaterial(name: string, scene: Scene): Material;
}
export interface CityShadowProxyDiagnostics {
  sourceVertices: number; sourceTriangles: number; sourceSubMeshes: number;
  opaqueSubMeshes: number; residualSubMeshes: number; proxyTriangles: number; proxySubMeshes: number;
  geometryReduction: number; objectSizeFilter: string; distanceLod: string;
  runtimeSha256: string; sourceName: string; preparedGeometryFingerprint: string;
  mainCameraLayerMask: number; backend: string; status: string;
}
export function planCityShadowProxy(source: Mesh): {
  positions: Float32Array; normals: Float32Array; indices: Uint32Array;
  opaqueSubMeshes: Set<SubMesh>; residualSubMeshes: SubMesh[];
  backFaceCulling: boolean; sideOrientation: number | null; fingerprint: string;
  diagnostics: Omit<CityShadowProxyDiagnostics,'runtimeSha256'|'sourceName'|'preparedGeometryFingerprint'|'mainCameraLayerMask'|'backend'|'status'>;
};
export function createCityShadowProxy(source: Mesh, options: CityShadowProxyOptions): {
  mesh: Mesh; material: Material; diagnostics: CityShadowProxyDiagnostics;
  bind(generator: ShadowGenerator): void; dispose(): void;
};
