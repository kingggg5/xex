import{MaterialPluginBase}from'@babylonjs/core/Materials/materialPluginBase';
import{ShaderLanguage}from'@babylonjs/core/Materials/shaderLanguage';
import type{PBRMaterial}from'@babylonjs/core/Materials/PBR/pbrMaterial';
import type{MaterialDefines}from'@babylonjs/core/Materials/materialDefines';
import type{UniformBuffer}from'@babylonjs/core/Materials/uniformBuffer';
import type{Scene}from'@babylonjs/core/scene';
export class WaterArtMossUpPlugin extends MaterialPluginBase{
 constructor(material:PBRMaterial){super(material,'WaterArtMossUp',220,{WATER_ART_MOSS_UP:true},true,false);this._enable(true);}
 isCompatible(language:ShaderLanguage){return language===ShaderLanguage.GLSL||language===ShaderLanguage.WGSL;}
 prepareDefines(d:MaterialDefines){d.WATER_ART_MOSS_UP=true;}
 getCustomCode(stage:string,language=ShaderLanguage.GLSL){if(stage!=='fragment')return null;const wg=language===ShaderLanguage.WGSL,c=wg?'fragmentInputs.vColor.rgb':'vColor.rgb',V=wg?'vec3f':'vec3';return{CUSTOM_FRAGMENT_BEFORE_LIGHTS:`
 #if defined(WATER_ART_MOSS_UP) && defined(VERTEXCOLOR)
 if(normalW.y<=0.6 && ${c}.g>${c}.r*1.12 && ${c}.g>${c}.b*1.4){surfaceAlbedo*= ${V}(max(max(${c}.r,${c}.g),${c}.b))/max(${c},${V}(0.01));}
 #endif`};}
}
/** Candidate-only vegetation clip: retain the existing Y0ground under the wet film. */
export class WaterArtRainGrassClip extends MaterialPluginBase{
 constructor(material:PBRMaterial,private sceneRef:Scene,private revision=1){super(material,'WaterArtRainGrassClip',240,{WATER_ART_RAIN_GRASS:true},true,false);this._enable(true);}
 isCompatible(language:ShaderLanguage){return language===ShaderLanguage.GLSL||language===ShaderLanguage.WGSL;}
 prepareDefines(d:MaterialDefines){d.WATER_ART_RAIN_GRASS=true;}
 getUniforms(language=ShaderLanguage.GLSL){return{ubo:[{name:'waterArtRain',size:4,type:'vec4'}],fragment:language===ShaderLanguage.GLSL?'uniform vec4 waterArtRain;':''};}
 bindForSubMesh(buffer:UniformBuffer){const puddles=this.sceneRef.metadata?.naturalWater?.rainPuddles;buffer.updateFloat4('waterArtRain',puddles?.ready&&puddles.visible?puddles.rain:0,0,0,0);}
 getCustomCode(stage:string,language=ShaderLanguage.GLSL):Record<string,string>|null{if(stage!=='fragment')return null;const wg=language===ShaderLanguage.WGSL,p=wg?'fragmentInputs.vPositionW.xz':'vPositionW.xz',r=wg?'uniforms.waterArtRain.x':'waterArtRain.x',V=wg?'vec2f':'vec2',F=wg?'let':'vec2';const bodies=[[-14,-27,1.2,.65],[-15.4,-25.5,.85,.45],[-15.5,-28.6,.7,.38]];
 if(this.revision>=2){const D=wg?'let':'float',A=wg?'atan2':'atan',C=wg?'vec3f':'vec3';return{CUSTOM_FRAGMENT_BEFORE_LIGHTS:`#ifdef WATER_ART_RAIN_GRASS
 if(${r}>0.05){${bodies.map((b,i)=>`${F} waQ${i}=(${p}-${V}(${b[0]},${b[1]}))/${V}(${b[2]},${b[3]});${D} waA${i}=${A}(waQ${i}.y,waQ${i}.x);${D} waR${i}=0.91+0.05*sin(3.0*waA${i}+${(i*.7).toFixed(1)})+0.03*sin(5.0*waA${i}+1.1)+0.01*sin(7.0*waA${i}+2.2);${D} waWet${i}=(1.0-smoothstep(0.70*waR${i},waR${i},length(waQ${i})))*${r};${this.revision===3?`surfaceAlbedo=mix(surfaceAlbedo,surfaceAlbedo*${C}(0.68,0.73,0.60)+${C}(0.03,0.026,0.012),waWet${i});`:`surfaceAlbedo*=mix(${C}(1.0),${C}(0.78,0.83,0.76),waWet${i});`}`).join('')}}
 #endif`};}
 return{CUSTOM_FRAGMENT_UPDATE_ALPHA:`#ifdef WATER_ART_RAIN_GRASS
 if(${r}>0.05){${bodies.map((b,i)=>`${F} waQ${i}=(${p}-${V}(${b[0]},${b[1]}))/${V}(${b[2]},${b[3]});if(dot(waQ${i},waQ${i})<0.86){discard;}`).join('')}}
 #endif`};}
}

/** Opaque wet-sand to grass tint: no extra sampler or newly exposed host hole. */
export class WaterArtBankEdgePlugin extends MaterialPluginBase{
 constructor(material:PBRMaterial,private revision=2){super(material,'WaterArtBankEdge',225,{WATER_ART_BANK_EDGE:true},true,false);this._enable(true);}
 isCompatible(language:ShaderLanguage){return language===ShaderLanguage.GLSL||language===ShaderLanguage.WGSL;}
 prepareDefines(d:MaterialDefines){d.WATER_ART_BANK_EDGE=true;}
 getCustomCode(stage:string,language=ShaderLanguage.GLSL){if(stage!=='fragment')return null;const wg=language===ShaderLanguage.WGSL,uv=this.revision===3?(wg?'fragmentInputs.vMainUV2':'vMainUV2'):(wg?'fragmentInputs.vAlbedoUV':'vAlbedoUV'),V=wg?'vec3f':'vec3',F=wg?'let':'float';if(this.revision===3)return{CUSTOM_FRAGMENT_BEFORE_LIGHTS:`
 #if defined(WATER_ART_BANK_EDGE) && defined(ALBEDO) && defined(UV2)
 ${F} waBankU=clamp(${uv}.x,0.0,1.0);
 ${F} waBankVariation=0.88+0.18*dot(albedoTexture.rgb,${V}(0.2126,0.7152,0.0722));
 surfaceAlbedo=mix(surfaceAlbedo,${V}(0.20,0.22,0.13)*waBankVariation,(1.0-smoothstep(0.16,0.68,waBankU))*0.58);
 #endif`};return{CUSTOM_FRAGMENT_BEFORE_LIGHTS:`
 #if defined(WATER_ART_BANK_EDGE) && defined(ALBEDO)
 ${F} waBankU=clamp(${uv}.x,0.0,1.0);
 ${F} waBankVariation=0.82+0.22*dot(albedoTexture.rgb,${V}(0.2126,0.7152,0.0722));
 surfaceAlbedo=mix(surfaceAlbedo,mix(${V}(0.22,0.29,0.18),${V}(0.16,0.25,0.055),smoothstep(0.12,0.86,waBankU))*waBankVariation,0.72);
 #endif`};}
}
