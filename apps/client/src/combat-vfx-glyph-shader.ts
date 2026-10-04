import { ShaderMaterial } from "@babylonjs/core/Materials/shaderMaterial";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import { Constants } from "@babylonjs/core/Engines/constants";
import type { Scene } from "@babylonjs/core/scene";
import "@babylonjs/core/Shaders/ShadersInclude/instancesDeclaration";
import "@babylonjs/core/ShadersWGSL/ShadersInclude/instancesDeclaration";

export const COMBAT_TEXT_ATTRIBUTES = ["ctAnchorType","ctTime","ctGlyph","ctLayout","ctFill","ctLine"] as const;
// All motion is analytic on the GPU. Anchor and layout buffers change only on spawn/expiry.
const GLSL_VERTEX = `precision highp float;
attribute vec3 position; attribute vec2 uv;
#include<instancesDeclaration>
attribute vec4 ctAnchorType,ctTime,ctGlyph,ctLayout,ctFill,ctLine;
uniform mat4 viewProjection; uniform float ctNow,ctScale,ctReduced; uniform vec2 ctViewport;
varying vec2 vUv; varying vec4 vFill,vLine; varying float vAlpha;
void main(){
 float age=max(0.0,ctNow-ctTime.x),life=max(.001,ctTime.y-ctTime.x),t=clamp(age/life,0.0,1.0);
 float crit=step(.5,ctAnchorType.w)*(1.0-step(1.5,ctAnchorType.w));
 float burst=step(8.5,ctAnchorType.w),word=step(2.5,ctAnchorType.w)*(1.0-step(3.5,ctAnchorType.w));
 float pop=1.0;
 if(crit>.5)pop=age<.08?mix(.5,1.65,1.0-pow(1.0-age/.08,3.0)):age<.22?mix(1.65,1.25,(age-.08)/.14):mix(1.25,1.10,clamp((age-.22)/.98,0.0,1.0));
 else if(word<.5)pop=age<.07?mix(.55,1.18,1.0-pow(1.0-age/.07,3.0)):mix(1.18,1.0,clamp((age-.07)/.08,0.0,1.0));
 else pop=mix(.9,1.0,clamp(age/.08,0.0,1.0));
 float rise=word>.5?1.1*t:1.7*(1.0-pow(1.0-clamp(age/.55,0.0,1.0),3.0))-.23*pow(max(0.0,(age-.55)/.35),2.0);
 float drift=ctTime.w*.92*(1.0-pow(1.0-t,2.0));
 if(ctReduced>.5){pop=1.0;rise=.35*t;drift=0.0;}
 float alpha=1.0-pow(clamp((t-.667)/.333,0.0,1.0),2.0);
 if(burst>.5){pop=mix(.6,1.35,clamp(age/.16,0.0,1.0));alpha=.9*(1.0-clamp(age/.28,0.0,1.0));rise=0.0;drift=0.0;}
 vec4 clip=viewProjection*vec4(ctAnchorType.xyz,1.0);
 if(ctLine.w>ctTime.x+.0001)pop*=mix(1.1,1.0,clamp((ctNow-ctLine.w)/.08,0.0,1.0));
 float px=ctLayout.w*ctScale;vec2 local=(position.xy*ctLayout.yz+vec2(ctLayout.x+ctTime.z*.62+drift,rise))*px*pop;
 clip.xy+=local*vec2(2.0)/ctViewport*clip.w;clip.z=0.0;
 gl_Position=clip;
 vUv=mix(ctGlyph.xy,ctGlyph.zw,uv);vFill=ctFill;vLine=ctLine;
 vAlpha=alpha*ctFill.a*step(age,life)*step(.001,clip.w);
}`;
const GLSL_FRAGMENT=`precision highp float;
uniform sampler2D ctAtlas;varying vec2 vUv;varying vec4 vFill,vLine;varying float vAlpha;
void main(){vec4 tex=texture2D(ctAtlas,vUv);float fill=tex.r,outline=tex.g,shadow=tex.b*.4;float coverage=max(fill,max(outline,shadow));vec3 rgb=mix(vec3(.025),vLine.rgb,outline/max(coverage,.001));rgb=mix(rgb,vFill.rgb,fill/max(coverage,.001));gl_FragColor=vec4(rgb,coverage*vAlpha);}`;
const WGSL_VERTEX=`attribute position:vec3f;attribute uv:vec2f;
#include<instancesDeclaration>
attribute ctAnchorType:vec4f;attribute ctTime:vec4f;attribute ctGlyph:vec4f;attribute ctLayout:vec4f;attribute ctFill:vec4f;attribute ctLine:vec4f;
uniform viewProjection:mat4x4f;uniform ctNow:f32;uniform ctScale:f32;uniform ctReduced:f32;uniform ctViewport:vec2f;
varying vUv:vec2f;varying vFill:vec4f;varying vLine:vec4f;varying vAlpha:f32;
@vertex fn main(input:VertexInputs)->FragmentInputs {
 let age=max(0.0,uniforms.ctNow-vertexInputs.ctTime.x);let life=max(.001,vertexInputs.ctTime.y-vertexInputs.ctTime.x);let t=clamp(age/life,0.0,1.0);
 let kind=vertexInputs.ctAnchorType.w;let crit=kind>.5&&kind<1.5;let word=kind>2.5&&kind<3.5;let burst=kind>8.5;
 var pop=1.0;
 if(crit){if(age<.08){pop=mix(.5,1.65,1.0-pow(1.0-age/.08,3.0));}else if(age<.22){pop=mix(1.65,1.25,(age-.08)/.14);}else{pop=mix(1.25,1.10,clamp((age-.22)/.98,0.0,1.0));}}
 else if(!word){if(age<.07){pop=mix(.55,1.18,1.0-pow(1.0-age/.07,3.0));}else{pop=mix(1.18,1.0,clamp((age-.07)/.08,0.0,1.0));}}
 else{pop=mix(.9,1.0,clamp(age/.08,0.0,1.0));}
 var rise=1.7*(1.0-pow(1.0-clamp(age/.55,0.0,1.0),3.0))-.23*pow(max(0.0,(age-.55)/.35),2.0);if(word){rise=1.1*t;}
 var drift=vertexInputs.ctTime.w*.92*(1.0-pow(1.0-t,2.0));
 if(uniforms.ctReduced>.5){pop=1.0;rise=.35*t;drift=0.0;}
 var alpha=1.0-pow(clamp((t-.667)/.333,0.0,1.0),2.0);
 if(burst){pop=mix(.6,1.35,clamp(age/.16,0.0,1.0));alpha=.9*(1.0-clamp(age/.28,0.0,1.0));rise=0.0;drift=0.0;}
 var clip=uniforms.viewProjection*vec4f(vertexInputs.ctAnchorType.xyz,1.0);
 if(vertexInputs.ctLine.w>vertexInputs.ctTime.x+.0001){pop*=mix(1.1,1.0,clamp((uniforms.ctNow-vertexInputs.ctLine.w)/.08,0.0,1.0));}
 let px=vertexInputs.ctLayout.w*uniforms.ctScale;let local=(vertexInputs.position.xy*vertexInputs.ctLayout.yz+vec2f(vertexInputs.ctLayout.x+vertexInputs.ctTime.z*.62+drift,rise))*px*pop;
 clip=vec4f(clip.xy+local*vec2f(2.0)/uniforms.ctViewport*clip.w,0.0,clip.w);vertexOutputs.position=clip;
 vertexOutputs.vUv=mix(vertexInputs.ctGlyph.xy,vertexInputs.ctGlyph.zw,vertexInputs.uv);vertexOutputs.vFill=vertexInputs.ctFill;vertexOutputs.vLine=vertexInputs.ctLine;
 vertexOutputs.vAlpha=alpha*vertexInputs.ctFill.a*step(age,life)*step(.001,clip.w);
}`;
const WGSL_FRAGMENT=`var ctAtlasSampler:sampler;var ctAtlas:texture_2d<f32>;varying vUv:vec2f;varying vFill:vec4f;varying vLine:vec4f;varying vAlpha:f32;
@fragment fn main(input:FragmentInputs)->FragmentOutputs {let tex=textureSample(ctAtlas,ctAtlasSampler,fragmentInputs.vUv);let fill=tex.r;let outline=tex.g;let shadow=tex.b*.4;let coverage=max(fill,max(outline,shadow));var rgb=mix(vec3f(.025),fragmentInputs.vLine.rgb,outline/max(coverage,.001));rgb=mix(rgb,fragmentInputs.vFill.rgb,fill/max(coverage,.001));fragmentOutputs.color=vec4f(rgb,coverage*fragmentInputs.vAlpha);}`;
/** The exact sources selected at runtime, exposed for CPU contract checks; this is not shader compilation. */
export const COMBAT_GLYPH_SHADERS=Object.freeze({glsl:Object.freeze({vertex:GLSL_VERTEX,fragment:GLSL_FRAGMENT}),wgsl:Object.freeze({vertex:WGSL_VERTEX,fragment:WGSL_FRAGMENT})});
export function createGlyphMaterial(scene:Scene,burst=false):ShaderMaterial {
	const wgsl=scene.getEngine().isWebGPU;
	const material=new ShaderMaterial(burst?"combat-text-burst":"combat-text-glyph",scene,{vertexSource:wgsl?WGSL_VERTEX:GLSL_VERTEX,fragmentSource:wgsl?WGSL_FRAGMENT:GLSL_FRAGMENT},{attributes:["position","uv",...COMBAT_TEXT_ATTRIBUTES],uniforms:["world","viewProjection","ctNow","ctViewport","ctScale","ctReduced"],samplers:["ctAtlas"],needAlphaBlending:true,shaderLanguage:wgsl?ShaderLanguage.WGSL:ShaderLanguage.GLSL});
	material.disableDepthWrite=true;material.depthFunction=Constants.ALWAYS;material.backFaceCulling=false;material.alphaMode=burst?Constants.ALPHA_ADD:Constants.ALPHA_COMBINE;
	return material;
}
