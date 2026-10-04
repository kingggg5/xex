import { LoadAssetContainerAsync } from '@babylonjs/core/Loading/sceneLoader';
import '@babylonjs/loaders/glTF';
import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { InstancedMesh } from '@babylonjs/core/Meshes/instancedMesh';
import { Texture } from '@babylonjs/core/Materials/Textures/texture';
import type { Scene } from '@babylonjs/core/scene';
import type { AssetContainer } from '@babylonjs/core/assetContainer';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
import type { Observer } from '@babylonjs/core/Misc/observable';
import { createStarterRocksCandidate } from './starter-rocks-candidate';
import { createStarterRockMaterial, STARTER_ROCK_SOURCE, validateStarterRockMaterial,starterRockTextureColorSpace } from './starter-rocks-policy.mjs';
import lod0Url from '../../../assets/models/sunmeadow-props/stone/runtime/sm_boulder_01_lod0.glb?url';
import lod1Url from '../../../assets/models/sunmeadow-props/stone/runtime/sm_boulder_01_lod1.glb?url';
import lod2Url from '../../../assets/models/sunmeadow-props/stone/runtime/sm_boulder_01_lod2.glb?url';
import albedoUrl from '../../../assets/models/sunmeadow-props/stone/runtime/textures/sm_stone_albedo-384298f87985.ktx2?url';
import normalUrl from '../../../assets/models/sunmeadow-props/stone/runtime/textures/sm_stone_normal-5aac6efc0e22.ktx2?url';
import ormUrl from '../../../assets/models/sunmeadow-props/stone/runtime/textures/sm_stone_orm-ffc61f77267c.ktx2?url';

const installs=new WeakMap<Scene,Promise<void>>();
const lodUrls=[lod0Url,lod1Url,lod2Url] as const;
const atlasUrls={albedo:albedoUrl,normal:normalUrl,orm:ormUrl} as const;
type Candidate=ReturnType<typeof createStarterRocksCandidate>;
type AtlasKey=keyof typeof atlasUrls;
type Diagnostic={owner:string;status:string;usage:string;sourceHashes:readonly string[];sourceUrls:readonly string[];
 selectedIds:string[];selectionCamera?:{x:number;y:number;z:number};cell?:string;materialBorrowed?:boolean;
 textureReuse?:Partial<Record<AtlasKey,boolean>>;textureColorSpace?:Partial<Record<AtlasKey,ReturnType<typeof starterRockTextureColorSpace>>>;
 ownedTextureCount?:number;stats?:ReturnType<Candidate['stats']>;error?:string};

/** Root DEV hook only. No camera/quality/collider changes; no new scatter or shadow caster registration. */
export async function installStarterRocksReview(scene:Scene):Promise<void> {
  if(!import.meta.env.DEV||scene.isDisposed)return;
  const existing=installs.get(scene);if(existing)return existing;
  // Preserve idempotence across a hot-import instance while another owned installer is still live.
  if(scene.metadata?.starterRocksReview?.owner==='starter-rocks-review'&&
    ['PREPARING','WARMING','ACTIVE_UNADMITTED'].includes(scene.metadata.starterRocksReview.status))return;
  const pending=install(scene);installs.set(scene,pending);return pending;
}
async function install(scene:Scene):Promise<void> {
  const diagnostic:Diagnostic={owner:'starter-rocks-review',status:'PREPARING',
    usage:'UNADMITTED_DEV_3_TO_5_VISIBLE_EXISTING_DEFAULT_ROCKS_ONE_CELL',
    sourceHashes:STARTER_ROCK_SOURCE.sha256,sourceUrls:lodUrls,selectedIds:[]};
  scene.metadata={...scene.metadata,starterRocksReview:diagnostic};
  const camera=scene.activeCamera;
  if(!camera){diagnostic.status='SKIPPED_NO_CAMERA';return;}
  camera.getViewMatrix(true);
  const at=camera.globalPosition??camera.position,selectionCamera={x:at.x,y:at.y,z:at.z};
  if(!Object.values(selectionCamera).every(Number.isFinite)){diagnostic.status='SKIPPED_INVALID_CAMERA';return;}
  // Snapshot the fixed review camera before any loading wait; never move the camera or replay shared RNG.
  diagnostic.selectionCamera=selectionCamera;
  const groups=new Map<string,{mesh:InstancedMesh;distance:number}[]>();
  for(const mesh of scene.meshes){
    if(!(mesh instanceof InstancedMesh)||mesh.isDisposed()||!mesh.isVisible||!mesh.isEnabled()||
      mesh.isPickable||mesh.checkCollisions||!/^env-rock-\d+$/.test(mesh.name)||mesh.sourceMesh.name!=='env-rock-master')continue;
    const m=mesh.computeWorldMatrix(true).m,x=m[12],y=m[13],z=m[14];
    if(![x,y,z].every(Number.isFinite))continue;
    const cell=Math.floor(x/64)+','+Math.floor(z/64),distance=(x-at.x)**2+(y-at.y)**2+(z-at.z)**2;
    const group=groups.get(cell)??[];group.push({mesh,distance});groups.set(cell,group);
  }
  const eligible=[...groups.entries()].filter(([,group])=>group.length>=3);
  for(const [,group] of eligible)group.sort((a,b)=>a.distance-b.distance||a.mesh.name.localeCompare(b.mesh.name));
  eligible.sort((a,b)=>a[1][0].distance-b[1][0].distance||a[0].localeCompare(b[0]));
  const chosen=eligible[0];
  if(!chosen){diagnostic.status='SKIPPED_NO_THREE_VISIBLE_ROCKS_IN_ONE_CELL';return;}
  const legacy=chosen[1].slice(0,5).map(item=>item.mesh);
  diagnostic.cell=chosen[0];diagnostic.selectedIds=legacy.map(mesh=>mesh.name);

  let stopped=false,candidate:Candidate|undefined,ownedMaterial:PBRMaterial|undefined;
  let renderObserver:Observer<Scene>|null=null,disposeObserver:Observer<Scene>|null=null;
  const containers=new Set<AssetContainer>(),ownedTextures=new Set<Texture>(),cancelWaits=new Set<()=>void>();
  const fail=new Error('Starter rocks review stopped');
  const check=()=>{if(stopped||scene.isDisposed)throw fail;};
  function cleanup(status:string){
    if(stopped)return;stopped=true;diagnostic.status=status;
    for(const cancel of [...cancelWaits])cancel();cancelWaits.clear();
    if(renderObserver){scene.onBeforeRenderObservable.remove(renderObserver);renderObserver=null;}
    candidate?.dispose();if(candidate)diagnostic.stats=candidate.stats();
    for(const container of containers)container.dispose();containers.clear();
    ownedMaterial?.dispose(false,false);
    for(const texture of ownedTextures)texture.dispose();ownedTextures.clear();diagnostic.ownedTextureCount=0;
    if(disposeObserver){scene.onDisposeObservable.remove(disposeObserver);disposeObserver=null;}
  }
  disposeObserver=scene.onDisposeObservable.add(()=>cleanup('DISPOSED'));
  function waitFor<T>(promise:Promise<T>,timeoutMs=15000):Promise<T>{
    return new Promise<T>((resolve,reject)=>{
      let settled=false;
      const finish=(error:unknown,value?:T)=>{
        if(settled)return;settled=true;clearTimeout(timer);cancelWaits.delete(cancel);
        if(error)reject(error);else resolve(value!);
      };
      const cancel=()=>finish(fail);
      const timer=setTimeout(()=>finish(new Error('Starter rock resource deadline exceeded')),timeoutMs);
      cancelWaits.add(cancel);
      promise.then(value=>{try{check();finish(null,value);}catch(error){finish(error);}},error=>finish(error));
    });
  }
  function textureReady(texture:Texture,getFailure?:()=>Error|undefined):Promise<Texture>{
    return new Promise<Texture>((resolve,reject)=>{
      let settled=false,timer:ReturnType<typeof setTimeout>|undefined;const deadline=Date.now()+10000;
      const finish=(error?:unknown)=>{
        if(settled)return;settled=true;if(timer!==undefined)clearTimeout(timer);cancelWaits.delete(cancel);
        if(error)reject(error);else resolve(texture);
      };
      const cancel=()=>finish(fail);
      const tick=()=>{
        if(stopped||scene.isDisposed){finish(fail);return;}
        const failure=getFailure?.();if(failure){finish(failure);return;}
        if(texture.isReady()){finish();return;}
        if(Date.now()>=deadline){finish(new Error('Starter stone atlas did not become ready'));return;}
        timer=setTimeout(tick,25);
      };
      cancelWaits.add(cancel);tick();
    });
  }
  async function atlasTexture(key:AtlasKey):Promise<Texture>{
    const stem=STARTER_ROCK_SOURCE.atlas[key],gamma=key==='albedo';
    const matching=scene.textures.filter(texture=>String(texture.name+' '+('url' in texture?texture.url:'')).includes(stem));
    diagnostic.textureReuse??={};
    const existing=matching.filter(texture=>texture instanceof Texture&&texture.getScene()===scene&&!texture.isCube) as Texture[];
    existing.sort((a,b)=>Number(b.isReady())-Number(a.isReady()));
    for(const texture of existing){
      await textureReady(texture);check();
      if(starterRockTextureColorSpace(texture,key).valid&&(key!=='albedo'||!texture.hasAlpha)){
        diagnostic.textureReuse[key]=true;return texture;
      }
    }
    // Do not repair foreign texture colour-space flags or reuse its engine cache under a new interpretation.
    if(matching.length)throw new Error('Existing '+key+' stone atlas has incompatible ownership/colour-space flags');
    check();diagnostic.textureReuse[key]=false;
    let loadError:Error|undefined;
    const texture=new Texture(atlasUrls[key],scene,false,false,Texture.TRILINEAR_SAMPLINGMODE,undefined,
      message=>{loadError=new Error(message??'Starter stone atlas load failed');});
    ownedTextures.add(texture);
    texture.name=stem+'.ktx2';texture.gammaSpace=gamma;
    // Runtime atlas receipt has opaque RGB albedo, OpenGL+Y normal and R=AO/G=roughness/B=metal.
    await waitFor(textureReady(texture,()=>loadError));check();
    if(loadError)throw loadError;
    return texture;
  }
  try{
    let material:PBRMaterial|undefined;
    const materialCandidates=scene.materials.filter(item=>item instanceof PBRMaterial&&
      ([['albedo',item.albedoTexture],['normal',item.bumpTexture],['orm',item.metallicTexture]] as const).every(([key,texture])=>
        texture instanceof Texture&&String(texture.name+' '+texture.url).includes(STARTER_ROCK_SOURCE.atlas[key]))) as PBRMaterial[];
    for(const item of materialCandidates){
      await Promise.all([item.albedoTexture!,item.bumpTexture!,item.metallicTexture!].map(texture=>textureReady(texture as Texture)));
      check();try{validateStarterRockMaterial(item,scene);material=item;break;}catch{/* No foreign flag repair. */}
    }
    diagnostic.materialBorrowed=!!material;
    if(material){
      await Promise.all([material.albedoTexture,material.bumpTexture,material.metallicTexture].map(texture=>{
        if(!(texture instanceof Texture))throw new Error('Compatible atlas texture is not a loadable Texture');
        return textureReady(texture);
      }));
      diagnostic.textureReuse={albedo:true,normal:true,orm:true};
    }else{
      const [albedo,normal,orm]=await Promise.all((['albedo','normal','orm'] as const).map(atlasTexture));
      check();ownedMaterial=createStarterRockMaterial(scene,{albedo,normal,orm});material=ownedMaterial;
    }
    check();validateStarterRockMaterial(material,scene);diagnostic.ownedTextureCount=ownedTextures.size;
    diagnostic.textureColorSpace={albedo:starterRockTextureColorSpace(material.albedoTexture!,'albedo'),
      normal:starterRockTextureColorSpace(material.bumpTexture!,'normal'),orm:starterRockTextureColorSpace(material.metallicTexture!,'orm')};
    const loaded=await Promise.all(lodUrls.map(url=>waitFor(LoadAssetContainerAsync(url,scene,{
      pluginExtension:'.glb',pluginOptions:{gltf:{skipMaterials:true}},
    }).then(container=>{
      if(stopped||scene.isDisposed){container.dispose();throw fail;}
      containers.add(container);
      for(const mesh of container.meshes)mesh.isVisible=false;
      return container;
    }))));
    check();
    const templates=loaded.map((container,lod)=>{
      const geometry=container.meshes.filter(mesh=>mesh instanceof Mesh&&mesh.getTotalVertices()>0) as Mesh[];
      if(geometry.length!==1||geometry[0].getTotalIndices()/3!==STARTER_ROCK_SOURCE.triangles[lod])
        throw new Error('Pinned starter boulder container has unexpected geometry');
      return geometry[0];
    });
    candidate=createStarterRocksCandidate(scene,{templates,sourceHashes:STARTER_ROCK_SOURCE.sha256,material,legacy});
    // The candidate owns normalized copies; no source container is kept resident.
    for(const container of containers)container.dispose();containers.clear();
    diagnostic.status='WARMING';await candidate.prewarm(5000);check();
    const currentCamera=scene.activeCamera;
    if(!currentCamera||!candidate.activate(currentCamera.globalPosition??currentCamera.position))
      throw new Error('Starter boulder activation rejected; originals retained');
    diagnostic.status='ACTIVE_UNADMITTED';diagnostic.stats=candidate.stats();
    const counts=candidate.batches.map(mesh=>mesh.thinInstanceCount);
    renderObserver=scene.onBeforeRenderObservable.add(()=>{
      if(stopped||scene.isDisposed||!candidate)return;
      const activeCamera=scene.activeCamera;if(!activeCamera)return;
      try{
        candidate.update(activeCamera.globalPosition??activeCamera.position);
        if(candidate.batches.some((mesh,lod)=>mesh.thinInstanceCount!==counts[lod])){
          for(let lod=0;lod<3;lod++)counts[lod]=candidate.batches[lod].thinInstanceCount;
          diagnostic.stats=candidate.stats();
        }
      }catch(error){diagnostic.error=error instanceof Error?error.message:String(error);cleanup('FAILED_RESTORED_LEGACY');}
    });
  }catch(error){
    if(!stopped){diagnostic.error=error instanceof Error?error.message:String(error);cleanup('FAILED_RETAINED_LEGACY');}
  }
}
