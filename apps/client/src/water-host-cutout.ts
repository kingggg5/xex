import {MaterialPluginBase} from '@babylonjs/core/Materials/materialPluginBase';
import {ShaderLanguage} from '@babylonjs/core/Materials/shaderLanguage';
import {Texture} from '@babylonjs/core/Materials/Textures/texture';
import {Material} from '@babylonjs/core/Materials/material';
import type {MaterialDefines} from '@babylonjs/core/Materials/materialDefines';
import type {UniformBuffer} from '@babylonjs/core/Materials/uniformBuffer';
import type {Scene} from '@babylonjs/core/scene';
import maskUrl from './assets/world/water-host-v3/land-cutout-v3.png?url';
import receipt from './assets/world/water-host-v3/land-cutout-v3.json';

class WaterLandCutout extends MaterialPluginBase {
 private active=false;
 private decksActive=false;
 private p0Active=false;
 constructor(material:Material,private readonly mask:Texture){
  super(material,'WaterLandCutout',180,{WATER_LAND_CUTOUT:false,DECK_LAND_CUTOUT:false,WATER_P0_CUTOUT:false},true,false);this._enable(true);
 }
 setEnabled(value:boolean){if(this.active!==value){this.active=value;this._material.markAsDirty(Material.AllDirtyFlag);}}
 setDecksEnabled(value:boolean){if(this.decksActive!==value){this.decksActive=value;this._material.markAsDirty(Material.AllDirtyFlag);}}
 setP0Enabled(value:boolean){if(this.p0Active!==value){this.p0Active=value;this._material.markAsDirty(Material.AllDirtyFlag);}}
 prepareDefines(defines:MaterialDefines){Object.assign(defines,{WATER_LAND_CUTOUT:this.active,DECK_LAND_CUTOUT:this.decksActive,WATER_P0_CUTOUT:this.p0Active});}
 isCompatible(language:ShaderLanguage){return language===ShaderLanguage.GLSL||language===ShaderLanguage.WGSL;}
 getSamplers(samplers:string[]){samplers.push('waterLandMask');}
 isReadyForSubMesh(){return !(this.active||this.decksActive||this.p0Active)||this.mask.isReady();}
 bindForSubMesh(buffer:UniformBuffer){buffer.setTexture('waterLandMask',this.mask);}
 getCustomCode(stage:string,language=ShaderLanguage.GLSL){
  if(stage!=='fragment')return null;
  const wgsl=language===ShaderLanguage.WGSL;
  const pos=wgsl?'fragmentInputs.vPositionW':'vPositionW';
  const uv=`(${pos}.xz - ${wgsl?'vec2f':'vec2'}(-76.0,-108.0)) / ${wgsl?'vec2f':'vec2'}(128.0,132.0)`;
  return {CUSTOM_FRAGMENT_DEFINITIONS:wgsl?'var waterLandMaskSampler: sampler; var waterLandMask: texture_2d<f32>;':'uniform sampler2D waterLandMask;',
   CUSTOM_FRAGMENT_MAIN_BEGIN:wgsl?`
    #if defined(WATER_LAND_CUTOUT) || defined(DECK_LAND_CUTOUT) || defined(WATER_P0_CUTOUT)
    let waterLandUV=${uv};
    if(all(waterLandUV>=vec2f(0.0))&&all(waterLandUV<=vec2f(1.0))){
      let waterLandCut=textureSampleLevel(waterLandMask,waterLandMaskSampler,waterLandUV,0.0);
      #ifdef WATER_LAND_CUTOUT
      if(waterLandCut.r>0.5){discard;}
      #endif
      #ifdef DECK_LAND_CUTOUT
      if(waterLandCut.g>0.5){discard;}
      #endif
      #ifdef WATER_P0_CUTOUT
      if(waterLandCut.b>0.5){discard;}
      #endif
    }
    #endif`:`
    #if defined(WATER_LAND_CUTOUT) || defined(DECK_LAND_CUTOUT) || defined(WATER_P0_CUTOUT)
    vec2 waterLandUV=${uv};
    if(all(greaterThanEqual(waterLandUV,vec2(0.0)))&&all(lessThanEqual(waterLandUV,vec2(1.0)))){
      vec4 waterLandCut=texture2D(waterLandMask,waterLandUV);
      #ifdef WATER_LAND_CUTOUT
      if(waterLandCut.r>0.5){discard;}
      #endif
      #ifdef DECK_LAND_CUTOUT
      if(waterLandCut.g>0.5){discard;}
      #endif
      #ifdef WATER_P0_CUTOUT
      if(waterLandCut.b>0.5){discard;}
      #endif
    }
    #endif`};
 }
}

/** Removes flat host land over the authoritative derived water/bank footprint.
 * Visual review only: the separate hazard contract must be admitted on the server before live use. */
export function installWaterLandCutout(scene:Scene,materials:readonly Material[],candidate?:{
 textureUrl:string;receipt:typeof receipt;
}){
 const selectedReceipt=candidate?.receipt??receipt;
 if(selectedReceipt.schema!==receipt.schema || selectedReceipt.size!==receipt.size ||
    selectedReceipt.channels!==receipt.channels || selectedReceipt.gpuRgba8Bytes!==receipt.gpuRgba8Bytes ||
    selectedReceipt.boundsXZ.length!==receipt.boundsXZ.length ||
    selectedReceipt.boundsXZ.some((value,index)=>value!==receipt.boundsXZ[index]))
  throw new Error('Water host candidate must preserve mask bounds, channels and resolution');
 const texture=new Texture(candidate?.textureUrl??maskUrl,scene,true,false,Texture.NEAREST_SAMPLINGMODE);
 texture.name='water-host-land-mask';texture.gammaSpace=false;
 texture.wrapU=texture.wrapV=Texture.CLAMP_ADDRESSMODE;
 const plugins=[...new Set(materials)].map(material=>new WaterLandCutout(material,texture));
 const seen=new Set(materials);let active=false,decksActive=false,p0Active=false;
 scene.onDisposeObservable.addOnce(()=>texture.dispose());
 return {setEnabled(value:boolean){active=value;for(const plugin of plugins)plugin.setEnabled(value);},
  setDecksEnabled(value:boolean){decksActive=value;for(const plugin of plugins)plugin.setDecksEnabled(value);},
  setP0Enabled(value:boolean){p0Active=value;for(const plugin of plugins)plugin.setP0Enabled(value);},
  adoptMaterial(material:Material|null){if(!material||seen.has(material))return;seen.add(material);const plugin=new WaterLandCutout(material,texture);plugin.setEnabled(active);plugin.setDecksEnabled(decksActive);plugin.setP0Enabled(p0Active);plugins.push(plugin);},
  stats:()=>({visualOnly:true,maskSha256:selectedReceipt.maskSha256,derivedSha256:selectedReceipt.derivedSha256,
   maskGpuBytes:selectedReceipt.gpuRgba8Bytes,maskTransferBytes:selectedReceipt.fileBytes,cutTexels:selectedReceipt.cutTexels,materialCount:plugins.length,physicalHazardsAdmitted:false})};
}
