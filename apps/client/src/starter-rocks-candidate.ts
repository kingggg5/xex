import { InstancedMesh } from '@babylonjs/core/Meshes/instancedMesh';
import '@babylonjs/core/Meshes/thinInstanceMesh';
import type { Mesh } from '@babylonjs/core/Meshes/mesh';
import type { Scene } from '@babylonjs/core/scene';
import type { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
import { normalizeStarterRockGeometry, STARTER_ROCK_SOURCE, validateStarterRockMaterial } from './starter-rocks-policy.mjs';

type Position = Readonly<{x:number;y:number;z:number}>;
export interface StarterRocksCandidateOptions {
  /** Already loaded, unplaced source meshes. Caller may dispose their containers after this copy. */
  templates:readonly Mesh[];
  /** Exact recorded file hashes; this is a caller asset-loader pin, not a browser byte hash. */
  sourceHashes:readonly string[];
  /** Borrowed compatible sm_stone PBR material. Caller owns material/textures. */
  material:PBRMaterial;
  /** Root selects 1–5 actual existing eggs in one64m cell; initial native comparison selects3–5. */
  legacy:readonly InstancedMesh[];
  lodDistances?:readonly [number,number];
}

/**
 * UNADMITTED, opt-in presentation prototype. No loading, scatter, RNG, physics, lights or shadow registration.
 * Root loads the three pinned existing GLBs (skipMaterials), borrows/acquires the one shared atlas material,
 * then calls prewarm(), activate(camera), update(camera). Disposal restores selected visibility.
 * Normalization fits all source LODs in the old1.1m nominal sphere before copying exact legacy world matrices.
 * The affine rotations/scales/centres remain unchanged; no new collider is created or enlarged.
 */
export function createStarterRocksCandidate(scene:Scene,options:StarterRocksCandidateOptions) {
  if(scene.isDisposed)throw new TypeError('Live scene required');
  const legacy=[...options.legacy],distances=options.lodDistances??[18,40];
  if(legacy.length<1||legacy.length>5||new Set(legacy).size!==legacy.length||
    !distances.every(value=>Number.isFinite(value)&&value>0)||distances[1]<=distances[0])
    throw new TypeError('Bounded unique anchors and ordered LOD distances required');
  const snapshot=legacy.map(mesh=>{
    if(!(mesh instanceof InstancedMesh)||mesh.isDisposed()||mesh.getScene()!==scene||
      !/^env-rock-\d+$/.test(mesh.name)||mesh.sourceMesh.name!=='env-rock-master'||
      !mesh.isVisible||!mesh.isEnabled()||mesh.isPickable||mesh.checkCollisions)
      throw new TypeError('Only visible existing decorative default rock instances allowed');
    const matrix=new Float32Array(mesh.computeWorldMatrix(true).m);
    if(matrix.some(value=>!Number.isFinite(value))||matrix[3]!==0||matrix[7]!==0||matrix[11]!==0||matrix[15]!==1)
      throw new TypeError('Finite affine legacy rock transform required');
    return {mesh,matrix,visible:mesh.isVisible};
  });
  const cell=snapshot.map(({matrix})=>Math.floor(matrix[12]/64)+','+Math.floor(matrix[14]/64));
  if(new Set(cell).size!==1)throw new TypeError('One cell per candidate required');
  const material=validateStarterRockMaterial(options.material,scene);
  const normalized=normalizeStarterRockGeometry(scene,options.templates,options.sourceHashes),batches=normalized.meshes;
  const capacity=legacy.length,matrices=batches.map(()=>new Float32Array(capacity*16));
  const memberships=new Int8Array(capacity).fill(-1),counts=new Uint8Array(3);
  let active=false,ready=false,disposed=false,timer:ReturnType<typeof setTimeout>|undefined;
  let warming:Promise<void>|null=null,rejectWarm:((error:Error)=>void)|undefined;
  try { for(let lod=0;lod<3;lod++){
    const mesh=batches[lod];mesh.material=material;mesh.receiveShadows=true;
    mesh.metadata={owner:'starter-rocks-candidate',usage:'UNADMITTED_DEV_EXISTING_DEFAULT_ROCKS_ONLY',
      starterRocksCandidate:true,sourceId:STARTER_ROCK_SOURCE.id,sourceFileHash:options.sourceHashes[lod],
      sourceProof:'CALLER_FILE_PIN',cell:cell[0],collider:'UNCHANGED',estimatedDraws:1};
    matrices[lod].set(snapshot[0].matrix);
    // Matrices are fixed but membership moves between LODs. Allocate once; upload only on membership changes.
    mesh.thinInstanceSetBuffer('matrix',matrices[lod],16,false);mesh.thinInstanceCount=1;
  }} catch(error) {for(const mesh of batches)mesh.dispose(false,false);throw error;}
  const validCamera=(camera:Position)=>Number.isFinite(camera.x)&&Number.isFinite(camera.y)&&Number.isFinite(camera.z);
  function update(camera:Position) {
    if(disposed||!active)return;
    if(!validCamera(camera))throw new TypeError('Finite camera required');
    let changed=false;
    for(let index=0;index<capacity;index++){
      const matrix=snapshot[index].matrix,distance=Math.hypot(camera.x-matrix[12],camera.y-matrix[13],camera.z-matrix[14]);
      const lod=distance<distances[0]?0:distance<distances[1]?1:2;
      if(memberships[index]!==lod){memberships[index]=lod;changed=true;}
    }
    if(!changed)return;
    counts.fill(0);
    for(let index=0;index<capacity;index++){
      const lod=memberships[index],offset=counts[lod]++*16;
      matrices[lod].set(snapshot[index].matrix,offset);
    }
    for(let lod=0;lod<3;lod++){
      const mesh=batches[lod];mesh.thinInstanceCount=counts[lod];
      if(counts[lod]){mesh.thinInstanceBufferUpdated('matrix');mesh.thinInstanceRefreshBoundingInfo(true);}
      mesh.isVisible=counts[lod]>0;mesh.setEnabled(counts[lod]>0);
    }
  }
  function restore() {
    if(!active)return;
    active=false;memberships.fill(-1);counts.fill(0);
    for(const mesh of batches){mesh.isVisible=false;mesh.setEnabled(false);}
    for(const original of snapshot)if(!original.mesh.isDisposed())original.mesh.isVisible=original.visible;
  }
  function prewarm(timeoutMs=5000) {
    if(disposed)return Promise.reject(new Error('Candidate disposed'));
    if(ready)return Promise.resolve();
    if(warming)return warming;
    if(!Number.isFinite(timeoutMs)||timeoutMs<50||timeoutMs>10000)return Promise.reject(new TypeError('Bounded warmup deadline required'));
    warming=new Promise<void>((resolve,reject)=>{
      rejectWarm=reject;const deadline=Date.now()+timeoutMs;
      const finish=(error?:Error)=>{
        if(timer!==undefined){clearTimeout(timer);timer=undefined;}rejectWarm=undefined;
        if(error)reject(error);else{ready=true;resolve();}
      };
      const tick=()=>{
        if(disposed||scene.isDisposed){finish(new Error('Candidate disposed'));return;}
        try {
          if(batches.every(mesh=>mesh.subMeshes.every(sub=>material.isReadyForSubMesh(mesh,sub,true)))){finish();return;}
        }catch(error){finish(error instanceof Error?error:new Error(String(error)));return;}
        if(Date.now()>=deadline){finish(new Error('Starter rock material warmup timed out'));return;}
        timer=setTimeout(tick,16);
      };tick();
    });
    return warming;
  }
  function activate(camera:Position) {
    if(disposed||!ready||!validCamera(camera))return false;
    for(const original of snapshot){
      if(original.mesh.isDisposed())return false;
      const current=original.mesh.computeWorldMatrix(true).m;
      if(current.some((value,index)=>Math.abs(value-original.matrix[index])>1e-6))return false;
    }
    if(active){update(camera);return true;}
    // There is no visible swap until the compatible material has warmed.
    active=true;memberships.fill(-1);update(camera);
    for(const original of snapshot)original.mesh.isVisible=false;
    return true;
  }
  function stats() {
    return {status:disposed?'DISPOSED':active?'ACTIVE_UNADMITTED':ready?'READY_UNADMITTED':'PREPARED_UNADMITTED',
      sourceId:STARTER_ROCK_SOURCE.id,cell:cell[0],anchors:snapshot.map(item=>item.mesh.name),
      lodCounts:Array.from(counts),estimatedDraws:active?Array.from(counts).filter(Boolean).length:0,
      triangles:active?Array.from(counts).reduce((sum,count,lod)=>sum+count*STARTER_ROCK_SOURCE.triangles[lod],0):0,
      geometryCopies:3,materialsCreated:0,texturesCreated:0,colliderChanges:0,
      maximumAttributeLocations:normalized.maximumAttributeLocations,matrixCapacityBytes:capacity*16*4*3,
      uniformSourceScale:normalized.scale,sourceCentre:normalized.centre,nominalLegacyDiameter:STARTER_ROCK_SOURCE.diameter,
      textureDensity:'UV resized with source geometry; inherited legacy nonuniform scale changes world density',
      nativeVisual:'UNVERIFIED',addedFrameCost:'UNVERIFIED'};
  }
  function dispose() {
    if(disposed)return;restore();disposed=true;
    if(timer!==undefined){clearTimeout(timer);timer=undefined;}
    rejectWarm?.(new Error('Candidate disposed'));rejectWarm=undefined;
    for(const mesh of batches)mesh.dispose(false,false);
  }
  return {batches,prewarm,activate,update,restore,dispose,stats};
}
