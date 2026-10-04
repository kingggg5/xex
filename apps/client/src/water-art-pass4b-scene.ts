import type{Scene}from'@babylonjs/core/scene';
import{Mesh}from'@babylonjs/core/Meshes/mesh';
import{SubMesh}from'@babylonjs/core/Meshes/subMesh';
import{Vector3}from'@babylonjs/core/Maths/math.vector';
import{PBRMaterial}from'@babylonjs/core/Materials/PBR/pbrMaterial';
import{WaterArtRainGrassClip}from'./water-art-pass4b-materials';
import r01Overlay from'../../../planning/levels/sunmeadow-water-art-pass4b-overlay.json';
import r02Overlay from'../../../planning/levels/sunmeadow-water-art-pass4b-r02-overlay.json';
import r03Overlay from'../../../planning/levels/sunmeadow-water-art-pass4b-r03-overlay.json';

export function installWaterArtScene(scene:Scene,revision=1){
 const overlay=revision===3?r03Overlay:revision===2?r02Overlay:r01Overlay;
 const retirements=revision===3?r03Overlay.legacy_float_retirements:[overlay.legacy_float_patch];
 const status={candidate:revision===3?'water-art-pass4b-r03':revision===2?'water-art-pass4b-r02':'water-art-pass4b',legacyFloat:{sourceId:overlay.legacy_float_patch.source_id,sourceIds:retirements.map(r=>r.source_id),state:'PENDING',removedTriangles:0,observedIndices:null as number|null,remainingIndices:null as number|null},grassClipMaterials:[] as string[]};
 scene.metadata={...scene.metadata,waterArt:status};const installed=new Set<string>();let patched=false,nextScan=0,meshDirty=true,mismatchAttempts=0;
 const added=scene.onNewMeshAddedObservable.add(()=>{if(!patched)meshDirty=true;});
 const observer=scene.onBeforeRenderObservable.add(()=>{
  const now=performance.now();if(now<nextScan)return;nextScan=now+200;
  for(const name of['env-grass-tufts','env-grass-plants'])if(!installed.has(name)){const m=scene.getMaterialByName(name);if(m instanceof PBRMaterial){new WaterArtRainGrassClip(m,scene,revision);installed.add(name);status.grassClipMaterials.push(name);}}
  if(patched||!meshDirty)return;meshDirty=false;
  for(const mesh of scene.meshes){
   if(!(mesh instanceof Mesh))continue;
   if(revision>=2?mesh.name!=='Cell sunmeadow_c7_r6 / stone_foundation':(!mesh.name.includes(overlay.legacy_float_patch.cell)||!mesh.material?.name.includes(overlay.legacy_float_patch.material)))continue;
   const indices=mesh.getIndices(),positions=mesh.getVerticesData('position');if(!indices||!positions||indices.length<600)continue;
   status.legacyFloat.observedIndices=indices.length;
   if(revision>=2&&indices.length!==10308){status.legacyFloat.state='INDEX_COUNT_MISMATCH_NO_PATCH';mismatchAttempts++;meshDirty=mismatchAttempts<5;continue;}
   mesh.computeWorldMatrix(true);const world=mesh.getWorldMatrix();let valid=true;
   if(positions.length%3!==0||Array.from(positions).some(v=>!Number.isFinite(v))||Array.from(indices).some(i=>!Number.isInteger(i)||i<0||i*3+2>=positions.length)||Array.from(world.m).some(v=>!Number.isFinite(v))){status.legacyFloat.state='INVALID_GEOMETRY_NO_PATCH';mismatchAttempts++;meshDirty=mismatchAttempts<5;continue;}
   for(const retirement of retirements){const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(let k=retirement.triangle_ordinals[0]*3;k<retirement.triangle_ordinals[1]*3;k++){const p=Vector3.TransformCoordinates(Vector3.FromArray(positions,indices[k]*3),world).asArray();if(p.some(v=>!Number.isFinite(v))){valid=false;break;}for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[j]);hi[j]=Math.max(hi[j],p[j]);}}const expected=retirement.world_aabb;if(!valid||lo.some((v,i)=>Math.abs(v-expected.min[i])>.012)||hi.some((v,i)=>Math.abs(v-expected.max[i])>.012)){valid=false;break;}}
   if(!valid){status.legacyFloat.state='BBOX_MISMATCH_NO_PATCH';mismatchAttempts++;meshDirty=mismatchAttempts<5;continue;}
   const keep=Array.from(indices).filter((_,i)=>!retirements.some(r=>i>=r.triangle_ordinals[0]*3&&i<r.triangle_ordinals[1]*3));
   const removedTriangles=retirements.reduce((n,r)=>n+r.triangle_ordinals[1]-r.triangle_ordinals[0],0);
   if(revision===3&&(removedTriangles!==60||keep.length!==10128)){status.legacyFloat.state='FILTER_COUNT_MISMATCH_NO_PATCH';continue;}
   mesh.makeGeometryUnique();mesh.setIndices(keep);mesh.releaseSubMeshes();SubMesh.CreateFromIndices(0,0,keep.length,mesh);mesh.refreshBoundingInfo();
   status.legacyFloat={...status.legacyFloat,state:revision===3?'LOCAL60_TRIANGLE_PATCH_APPLIED':'LOCAL20_TRIANGLE_PATCH_APPLIED',removedTriangles,remainingIndices:keep.length};patched=true;break;
  }
 });
 scene.onDisposeObservable.addOnce(()=>{scene.onBeforeRenderObservable.remove(observer);scene.onNewMeshAddedObservable.remove(added);});return status;
}
