const shareSlots=Object.freeze({albedoTexture:'albedo',metallicTexture:'orm',ambientTexture:'orm'});
const otherSlots=['bumpTexture','opacityTexture','reflectionTexture','emissiveTexture','reflectivityTexture','metallicReflectanceTexture','microSurfaceTexture','lightmapTexture','refractionTexture'];
const configurations=['clearCoat','sheen','subSurface','anisotropy','iridescence','detailMap','decalMap'];
const configSlots=['texture','textureRoughness','bumpTexture','tintTexture','thicknessTexture','refractionTexture','translucencyIntensityTexture','translucencyColorTexture'];
const numericProperties=['level','coordinatesIndex','coordinatesMode','wrapU','wrapV','wrapR','anisotropicFilteringLevel','samplingMode','uOffset','vOffset','uScale','vScale','uAng','vAng','wAng','uRotationCenter','vRotationCenter','wRotationCenter'];

function materialSet(inputs){
 const result=new Set();const visit=material=>{if(!material||result.has(material))return;result.add(material);for(const child of material.subMaterials??[])visit(child);};
 for(const material of inputs)visit(material);return result;
}
function materialOf(assets){return materialSet(assets.flatMap(asset=>asset.meshes.map(mesh=>mesh.material)));}
function sourceBytes(texture){
 const source=texture._buffer;
 if(source instanceof ArrayBuffer)return new Uint8Array(source);
 if(ArrayBuffer.isView(source)&&source.buffer instanceof ArrayBuffer)return new Uint8Array(source.buffer,source.byteOffset,source.byteLength);
 return null;
}
function textureSignature(texture,bucket){
 const internal=texture.getInternalTexture?.();
 if(texture.getClassName?.()!=='Texture'||!texture.isReady?.()||!internal||texture.isRenderTarget||texture.isCube||texture.is3D||texture.is2DArray)return null;
 if(texture.animations?.length||texture.metadata?.dynamicFx||texture.metadata?.retainCpuSource||texture.metadata?.uiAtlas)return null;
 const values=numericProperties.map(key=>texture[key]);
 if(values.some(value=>typeof value!=='number'||!Number.isFinite(value)))return null;
 const matrix=Array.from(texture.getTextureMatrix?.().asArray()??[]);
 if(matrix.length!==16||matrix.some(value=>!Number.isFinite(value)))return null;
 const size=texture.getSize();
 return JSON.stringify({bucket,class:texture.getClassName(),values,matrix,width:size.width,height:size.height,
  gammaSpace:texture.gammaSpace,useSRGBBuffer:internal._useSRGBBuffer??null,invertY:texture.invertY,
  hasAlpha:texture.hasAlpha,getAlphaFromRGB:texture.getAlphaFromRGB,homogeneousRotationInUVTransform:texture.homogeneousRotationInUVTransform,
  format:internal.format,type:internal.type,compression:internal._compression??null,deviceFormat:internal._hardwareTexture?.format??null,
  mipmaps:internal.generateMipMaps,premultipliedAlpha:internal._premulAlpha??null});
}
async function imageHash(bytes){
 if(!globalThis.crypto?.subtle)return null;
 const hash=await globalThis.crypto.subtle.digest('SHA-256',bytes);
 return Array.from(new Uint8Array(hash),byte=>byte.toString(16).padStart(2,'0')).join('');
}
function references(materials,texture){
 const supported=[],unknown=[];
 for(const material of materials){
  if(material.getClassName?.()==='MultiMaterial')continue;
  const active=material.getActiveTextures?.()??[];
  if(!active.includes(texture))continue;
  if(material.getClassName?.()!=='PBRMaterial'){unknown.push(material.name);continue;}
  const bindings=Object.keys(shareSlots).filter(slot=>material[slot]===texture);
  const unsupported=otherSlots.some(slot=>material[slot]===texture)||configurations.some(key=>configSlots.some(slot=>material[key]?.[slot]===texture));
  // Classic PBR reports each direct/extension slot. Extra active occurrences are
  // unhandled plugin owners; preserve them rather than disposing their resource.
  if(unsupported||active.filter(value=>value===texture).length>bindings.length||!bindings.length){unknown.push(material.name);continue;}
  for(const slot of bindings)supported.push({material,slot});
 }
 return {supported,unknown};
}
function resourceCount(materials){
 const textures=new Set([...materials].flatMap(material=>material.getActiveTextures?.()??[]));
 const internals=new Set([...textures].map(texture=>texture.getInternalTexture?.()).filter(Boolean));
 return {baseTextures:textures.size,uniqueInternalTextures:internals.size};
}

/** Hash encoded image views, match runtime settings, rebind ALL owners, then dispose redundant wrappers. */
export async function optimizeHeroLodResources(scene,base,levels){
 const owned=materialOf([base,...levels]);let all=materialSet([...scene.materials,...owned]);
 const receipt={schema:'xexoria.hero-lod-resources/1',status:'CANDIDATE_C1',scope:'character-base-and-lower-materials; all scene material owners checked',before:resourceCount(owned),after:null,
  texturesDisposed:0,lowerGroupsDisposed:0,bindingsReplaced:0,shared:[],skipped:{},hardwareMemoryMeasured:false};
 const skip=reason=>{receipt.skipped[reason]=(receipt.skipped[reason]??0)+1;};
 const canonical=new Map(),plans=new Map(),hashes=new WeakMap();
 for(const material of owned){
  if(material.getClassName?.()!=='PBRMaterial')continue;
  for(const [slot,bucket] of Object.entries(shareSlots)){
   const texture=material[slot];if(!texture)continue;
   const signature=textureSignature(texture,bucket),bytes=sourceBytes(texture);
   if(!signature){skip('unsupported-settings-or-readiness');continue;}
   if(!bytes){skip('encoded-image-unavailable');continue;}
   let hash=hashes.get(texture);
   if(!hash){hash=await imageHash(bytes);if(!hash){skip('sha256-unavailable');continue;}hashes.set(texture,hash);}
   if(scene.isDisposed)throw new Error('Scene disposed during hero resource proof');
   const key=hash+':'+signature,first=canonical.get(key);
   if(!first){canonical.set(key,texture);continue;}
   if(first===texture||plans.has(texture))continue;
   const owners=references(all,texture);
   if(owners.unknown.length||scene.environmentTexture===texture){skip('unhandled-texture-owner');continue;}
   // A texture cannot migrate across semantic buckets, even if identical bytes
   // happen to be used for unrelated channels in another material.
   if(owners.supported.some(owner=>shareSlots[owner.slot]!==bucket)){skip('mixed-semantic-owner');continue;}
   plans.set(texture,{canonical:first,owners:owners.supported,hash,signature,bucket});
  }
 }
 // Crypto proof awaits. Recheck current settings and every owner at the commit
 // boundary so a loading callback cannot leave a newly added owner dangling.
 all=materialSet([...scene.materials,...owned]);
 for(const [texture,plan] of plans){
  const owners=references(all,texture);
  if(scene.environmentTexture===texture||owners.unknown.length||owners.supported.some(owner=>shareSlots[owner.slot]!==plan.bucket)){
   skip('ownership-changed-during-proof');plans.delete(texture);continue;
  }
  if(textureSignature(texture,plan.bucket)!==plan.signature||textureSignature(plan.canonical,plan.bucket)!==plan.signature){
   skip('settings-changed-during-proof');plans.delete(texture);continue;
  }
  plan.owners=owners.supported;
 }
 // Complete the transaction before ANY dispose; roll back if a setter fails.
 const rebound=[];
 try{
  for(const [texture,plan] of plans)for(const owner of plan.owners){
   if(owner.material[owner.slot]!==texture)throw new Error('Hero texture ownership changed during proof');
   owner.material[owner.slot]=plan.canonical;rebound.push({owner,texture});
  }
  for(const [texture] of plans)if([...all].some(material=>(material.getActiveTextures?.()??[]).includes(texture)))throw new Error('Hero duplicate still has a material owner');
 }catch(error){for(const {owner,texture} of rebound.reverse())owner.material[owner.slot]=texture;throw error;}
 receipt.bindingsReplaced=rebound.length;
 for(const [texture,plan] of plans){
  texture.dispose();receipt.texturesDisposed++;
  receipt.shared.push({imageSha256:plan.hash,settings:JSON.parse(plan.signature),semantic:plan.bucket,owners:plan.owners.map(owner=>({material:owner.material.name,slot:owner.slot}))});
 }
 const protectedGroups=new Set(base.animationGroups),removed=new Set();
 for(const level of levels)for(const group of level.animationGroups){
  if(protectedGroups.has(group)||removed.has(group))continue;
  if(group.isStarted||group.isPlaying){skip('playing-lower-animation-group');continue;}
  group.dispose();removed.add(group);receipt.lowerGroupsDisposed++;
 }
 receipt.after=resourceCount(owned);
 return receipt;
}
