import { Mesh } from '@babylonjs/core/Meshes/mesh.js';

/** Merge every static glTF primitive in world space, retaining its material slot. */
export function mergeStaticModel(loaded, name) {
  const parts = loaded.meshes.filter(mesh => mesh instanceof Mesh && mesh.getTotalVertices() > 0);
  if (!parts.length) throw new Error(`Static model ${name} has no geometry`);
  if (parts.some(mesh => mesh.skeleton || mesh.morphTargetManager)) {
    throw new Error(`Static model ${name} contains animated geometry`);
  }
  for (const part of parts) part.computeWorldMatrix(true);
  // Babylon's MergeMeshes reverses triangle winding for mirrored (determinant < 0) transforms only
  // when it merges two or more meshes. A lone mirrored glTF part (the importer's handedness root has
  // scaling.z = -1) would keep its winding and render inside-out, inverting twoSidedLighting normals.
  const mirroredSingle = parts.length === 1 && parts[0].getWorldMatrix().determinant() < 0;
  const merged = Mesh.MergeMeshes(parts, true, true, undefined, false, true);
  if (!merged) throw new Error(`Could not merge static model ${name}`);
  if (mirroredSingle) merged.flipFaces(false);
  merged.name = name;
  merged.isVisible = false;
  merged.isPickable = false;
  for (const animation of loaded.animationGroups) animation.dispose();
  // Geometry has been baked into the merged mesh. Discard empty import roots only;
  // materials are shared by the merged submeshes and must stay alive.
  for (const mesh of loaded.meshes) if (!mesh.isDisposed()) mesh.dispose(false, false);
  for (const node of loaded.transformNodes) if (!node.isDisposed()) node.dispose(false, false);
  return merged;
}
