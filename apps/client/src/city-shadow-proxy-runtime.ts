import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';
import { createCityShadowProxy } from './city-shadow-proxy.mjs';

/** Root integration: call on the actual post-retirement merged city only. */
export function prepareCityShadowProxy(source: Mesh, runtimeSha256: string, expectedGeometryFingerprint?: string) {
  return createCityShadowProxy(source, {
    expectedSourceName: 'reference-city-merged', runtimeSha256, expectedGeometryFingerprint,
    createMesh: (name,scene) => new Mesh(name,scene),
    createMaterial: (name,scene) => {
      const material = new StandardMaterial(name,scene); material.disableLighting = true;
      return material;
    },
  });
}
