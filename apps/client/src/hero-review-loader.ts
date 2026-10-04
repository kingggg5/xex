import {ImportMeshAsync} from '@babylonjs/core/Loading/sceneLoader';
import type {} from '@babylonjs/loaders/glTF/glTFFileLoader';
import type {Scene} from '@babylonjs/core/scene';
import {Mesh} from '@babylonjs/core/Meshes/mesh';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode';
import {ensureAssetLoaders} from './asset-loader-registration';
import {optimizeHeroLodResources} from './hero-lod-resources.mjs';
import lod0 from './assets/characters/heroes-review-r01/hero02_witch_lod0.glb?url';
import lod1 from './assets/characters/heroes-review-r01/hero02_witch_lod1.glb?url';
import lod2 from './assets/characters/heroes-review-r01/hero02_witch_lod2.glb?url';
import staffUrl from './assets/characters/heroes-review-r01/hero02_staff_lod0.glb?url';
import sword0 from './assets/characters/heroes-review-r01/hero01_swordsman_lod0.glb?url';
import sword1 from './assets/characters/heroes-review-r01/hero01_swordsman_lod1.glb?url';
import sword2 from './assets/characters/heroes-review-r01/hero01_swordsman_lod2.glb?url';
import packedSword0 from './assets/characters/hero01-review-r02/transport/hero01_swordsman_lod0.glb?url';
import packedSword1 from './assets/characters/hero01-review-r02/transport/hero01_swordsman_lod1.glb?url';
import packedSword2 from './assets/characters/hero01-review-r02/transport/hero01_swordsman_lod2.glb?url';
import swordWeapon from './assets/characters/hero01-review-r02/hero01_sword_procedural_r01.glb?url';
import swordWithClips from './assets/characters/hero01-review-r03/hero01_swordsman_lod0.transport.glb?url';
import compactSword0 from './assets/characters/hero01-review-r04/hero01_swordsman_lod0.glb?url';
import compactSword1 from './assets/characters/hero01-review-r04/hero01_swordsman_lod1.glb?url';
import compactSword2 from './assets/characters/hero01-review-r04/hero01_swordsman_lod2.glb?url';

export async function loadHeroReview(scene:Scene,id:string,pack:'r01'|'r02'|'r03'|'r04'='r01'){return id==='01'?loadRigReview(scene,'01',pack==='r04'?[compactSword0,compactSword1,compactSword2]:pack==='r03'?[swordWithClips,packedSword1,packedSword2]:pack==='r02'?[packedSword0,packedSword1,packedSword2]:[sword0,sword1,sword2]):loadMageReview(scene);}

/** Keep per-LOD inverse bind matrices, but drive joints from LOD0 by name. */
export async function loadMageReview(scene:Scene){
 return loadRigReview(scene,'02',[lod0,lod1,lod2]);
}
async function loadRigReview(scene:Scene,id:string,urls:readonly string[]){
 ensureAssetLoaders();
 // Per import only: NONE=0. Lower LODs must never play their first clip independently.
 const importCandidate=(url:string)=>ImportMeshAsync(url,scene,{pluginOptions:{gltf:{animationStartMode:0}}});
 const loaded:Awaited<ReturnType<typeof ImportMeshAsync>>[]=[];
 try{
 const base=await importCandidate(urls[0]);
 loaded.push(base);const levels:typeof loaded=[];
 for(const url of urls.slice(1)){const asset=await importCandidate(url);loaded.push(asset);levels.push(asset);}
 const skeleton=base.skeletons[0];if(!skeleton)throw Error('Mage candidate missing skeleton');
 const joints=new Map(skeleton.bones.map(b=>[b.name,b.getTransformNode()]));
 const parts=base.meshes.filter((m):m is Mesh=>m instanceof Mesh&&m.getTotalVertices()>0);
 const materialKey=(mesh:Mesh)=>mesh.material?.name.replace(/_lod[012]/g,'')??'';
 const binding=[];
 for(const [i,level] of levels.entries()){
  for(const rig of level.skeletons)for(const bone of rig.bones){
   const target=joints.get(bone.name);if(!target)throw Error('Missing candidate LOD joint '+bone.name);
   bone.linkTransformNode(target);
  }
  const matched=new Set<Mesh>();
  for(const part of parts){
   const candidates=level.meshes.filter((m):m is Mesh=>m instanceof Mesh&&m.getTotalVertices()>0&&materialKey(m)===materialKey(part));
   const low=candidates.find(m=>!matched.has(m));if(!low)throw Error('Mage candidate LOD material/part mismatch');
   const distance=i===0?5:22;
   matched.add(low);part.addLODLevel(distance,low);binding.push({mesh:part.name,lod:i+1,meshName:low.name,distance});
  }
 }
 for(const part of parts)part.addLODLevel(60,null);
 const socket=joints.get('socket_weapon_R');if(!socket)throw Error('Hero candidate missing right weapon socket');
 const staff=await importCandidate(id==='02'?staffUrl:swordWeapon);
 let weaponOwner:TransformNode|null=null;
 {
 loaded.push(staff as typeof base);
 const wrapper=staff.meshes.find(m=>!m.parent);if(!wrapper)throw Error('Mage staff missing glTF wrapper');
 const top=wrapper.getChildren();for(const node of top)node.parent=socket;
 weaponOwner=top.find((node):node is TransformNode=>node instanceof TransformNode&&node.getDescendants().some(n=>n.name==='fx_head'))??null;
 wrapper.dispose(false,false);
 }
 for(const mesh of [...base.meshes,...levels.flatMap(l=>l.meshes),...staff.meshes]){
  if(mesh.isDisposed())continue;mesh.isPickable=false;mesh.receiveShadows=true;mesh.metadata={...mesh.metadata,heroReview:id,notAdmitted:true};
 }
 const resourceReceipt=await optimizeHeroLodResources(scene,base,levels);
 scene.metadata={...scene.metadata,heroLodResources:resourceReceipt};
 scene.metadata={...scene.metadata,heroReview:{id,status:'ART_CANDIDATE_ONLY',gameplayClassUnchanged:true,joints:skeleton.bones.length,binding,sourceClips:base.animationGroups.map(g=>g.name)}};
 return {...base,weaponOwner,meshes:[...base.meshes,...levels.flatMap(l=>l.meshes),...staff.meshes].filter(m=>!m.isDisposed()),transformNodes:[...base.transformNodes,...levels.flatMap(l=>l.transformNodes),...staff.transformNodes].filter(n=>!n.isDisposed())};
 }catch(error){
  const materials=new Set(loaded.flatMap(a=>a.meshes.map(m=>m.material).filter(m=>m!==null))),textures=new Set([...materials].flatMap(m=>m.getActiveTextures()));
  for(const asset of loaded){asset.animationGroups.forEach(g=>g.dispose());asset.skeletons.forEach(s=>s.dispose());for(const node of [...asset.meshes,...asset.transformNodes])if(!node.isDisposed())node.dispose(false,false);}
  materials.forEach(m=>m.dispose(false,false));textures.forEach(t=>t.dispose());throw error;
 }
}
