/** A global SubMesh loses its inherited bounds when its draw range is shortened. */
export function applyLegacyPlantDensity(mesh, density, originals) {
 const fraction=Math.min(1,Math.max(0,Number.isFinite(density)?density:0));
 for(const sub of mesh.subMeshes){
  if(!originals.has(sub))originals.set(sub,sub.indexCount);
  const count=Math.floor(originals.get(sub)*fraction/3)*3;
  if(sub.indexCount===count)continue;
  sub.indexCount=count;
  sub.refreshBoundingInfo();
  sub.updateBoundingInfo(mesh.computeWorldMatrix(true));
 }
}
