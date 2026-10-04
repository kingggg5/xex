import {LoadAssetContainerAsync} from '@babylonjs/core/Loading/sceneLoader';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode';
import {Mesh} from '@babylonjs/core/Meshes/mesh';
import type {Scene} from '@babylonjs/core/scene';
import type {ShadowGenerator} from '@babylonjs/core/Lights/Shadows/shadowGenerator';
import type {ResolvedGraphicsPreset} from './graphics-quality.mjs';
import {readWeatherFrame} from './ambient-weather-channel';
import {createSheepActor,createSheepVisibilityPolicy} from './blueprint-sheep-policy';
import sheepManifest from '../../../assets/models/blueprint-cc0/candidates/sheep-v1/r03/candidate-manifest.json';

const urls=import.meta.glob('../../../assets/models/blueprint-cc0/candidates/sheep-v1/r03/runtime/*.meshopt.glb',
 {eager:true,query:'?url',import:'default'}) as Record<string,string>;
const placements=[[35.8,-25.7,.3],[39.1,-26.1,-.7],[41.1,-27.6,1.1],
 [35.9,-29.7,-1.2],[39.2,-30.4,.6],[41.1,-32.0,2.2]] as const;

/** Licensed ambient animals retain authored skin/idle clips. They are not baked into static dressing. */
export async function createBlueprintSheep(scene:Scene,options:{profile:ResolvedGraphicsPreset;
 groundAt:(x:number,z:number)=>number|null;shadows:ShadowGenerator;shadowsEnabled:boolean}) {
 const asset=sheepManifest.assets[0];
 // Small mobile silhouettes reserve 1,464 triangles for the whole pen.
 const lod=options.profile.formFactor==='mobile'||options.profile.preset==='low'?2:options.profile.preset==='medium'?1:0;
 const file=asset.lods[lod].file.replaceAll('\\','/'),url=urls['../../../'+file];
 if(!url)throw new Error('Licensed sheep runtime file is missing');
 const container=await LoadAssetContainerAsync(url,scene,{pluginExtension:'.glb'});
 if(scene.isDisposed){container.dispose();return;}
 for(const group of container.animationGroups)group.stop();
 const entries:ReturnType<typeof container.instantiateModelsToScene>[]=[];
 const roots:TransformNode[]=[];
 const actors:ReturnType<typeof createSheepActor>[]=[];
 let disposed=false;
 try{
  placements.forEach(([x,z,yaw],index)=>{
   const ground=options.groundAt(x,z);if(ground===null)throw new Error('Sheep pen has no authoritative ground');
   const entry=container.instantiateModelsToScene(name=>`bp-F1-sheep-${index}-${name}`,false,{doNotInstantiate:true});
   entries.push(entry);
   for(const group of entry.animationGroups)group.stop();
   const root=new TransformNode(`blueprint-F1-sheep-${index}`,scene);roots.push(root);
   root.position.set(x,ground+.015,z);root.rotation.y=yaw;
   root.metadata={blueprintId:'F1',licence:'CC0',standin:true,ambientAnimal:true,serverEntity:false};
   for(const node of entry.rootNodes)node.parent=root;
   const idle=entry.animationGroups.find(group=>group.name.endsWith('Idle'));
   if(!idle)throw new Error('Sheep idle clip is missing');
   idle.start(true);idle.pause();
   for(const mesh of root.getChildMeshes())if(mesh instanceof Mesh && mesh.getTotalVertices()>0){
    mesh.isPickable=false;mesh.receiveShadows=true;mesh.metadata={...root.metadata,glow:false};
    // The whole authored sheep is 1 m high, below the >1.5 m caster threshold.
    // It still receives the scene's existing shadows.
   }
   actors.push(createSheepActor(root,idle,index));
  });
 }catch(error){for(const entry of entries)entry.dispose();for(const root of roots)root.dispose();container.dispose();throw error;}
 const visibility=createSheepVisibilityPolicy(scene,actors);
 // Apply before the first render as well as when the weather clock is unavailable.
 visibility.update(readWeatherFrame(scene)?.worldMs);
 const observer=scene.onBeforeRenderObservable.add(()=>{
  if(!disposed)visibility.update(readWeatherFrame(scene)?.worldMs);
 });
 const diagnostics={status:'READY',count:roots.length,lod,triangles:asset.lods[lod].tris*roots.length,
  skeletons:entries.reduce((n,entry)=>n+entry.skeletons.length,0),sourceClips:6,geometryShared:true,
  nativeAdmission:'UNVERIFIED',physics:'AMBIENT_DECOR_NO_SERVER_ENTITY',shadowCasterCount:0,
  visibility:visibility.stats};
 scene.metadata={...scene.metadata,blueprintSheep:diagnostics};
 const dispose=()=>{
  if(disposed)return;disposed=true;scene.onBeforeRenderObservable.remove(observer);
  for(const entry of entries)entry.dispose();for(const root of roots)root.dispose();container.dispose();
 };
 scene.onDisposeObservable.addOnce(dispose);
 return {stats:()=>({...diagnostics,disposed}),dispose};
}
