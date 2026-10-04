import type {Scene} from '@babylonjs/core/scene';
import {Mesh} from '@babylonjs/core/Meshes/mesh';
import {CreateDisc} from '@babylonjs/core/Meshes/Builders/discBuilder';
import {CreatePlane} from '@babylonjs/core/Meshes/Builders/planeBuilder';
import {ShaderMaterial} from '@babylonjs/core/Materials/shaderMaterial';
import {ShaderLanguage} from '@babylonjs/core/Materials/shaderLanguage';
import {ParticleSystem} from '@babylonjs/core/Particles/particleSystem';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
import {Constants} from '@babylonjs/core/Engines/constants';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {Color4} from '@babylonjs/core/Maths/math.color';

const vertexGL='precision highp float;attribute vec3 position;attribute vec2 uv;uniform mat4 worldViewProjection;varying vec2 vUV;void main(){vUV=uv;gl_Position=worldViewProjection*vec4(position,1.0);}';
const vertexWG='attribute position:vec3f;attribute uv:vec2f;uniform worldViewProjection:mat4x4f;varying vUV:vec2f;@vertex fn main(input:VertexInputs)->FragmentInputs{vertexOutputs.vUV=vertexInputs.uv;vertexOutputs.position=uniforms.worldViewProjection*vec4f(vertexInputs.position,1.0);}';
function fragment(wgsl:boolean){
	if(wgsl)return `varying vUV:vec2f;uniform warpTime:f32;uniform warpMode:f32;uniform warpColour:vec4f;@fragment fn main(input:FragmentInputs)->FragmentOutputs{
	let p=fragmentInputs.vUV*2.0-vec2f(1.0);let r=length(p);let angle=atan2(p.y,p.x);var alpha:f32;
	if(uniforms.warpMode<0.5){let outer=1.0-smoothstep(0.015,0.043,abs(r-.81));let inner=1.0-smoothstep(.009,.024,abs(r-.56));let runes=step(.90,cos(angle*12.0+uniforms.warpTime*.08))*(1.0-smoothstep(.02,.09,abs(r-.69)));alpha=(outer*.80+inner*.34+runes*.60)*(1.0-smoothstep(.93,1.0,r));}
	else{let ellipse=length(p*vec2f(1.0,.88));let rim=1.0-smoothstep(.008,.037,abs(ellipse-.87));let swirl=.5+.5*sin(angle*3.0+r*14.0-uniforms.warpTime*.8);alpha=(1.0-smoothstep(.82,.94,ellipse))*(.06+.17*swirl)+rim*.80;}
	fragmentOutputs.color=vec4f(uniforms.warpColour.rgb,clamp(alpha*uniforms.warpColour.a,0.0,.78));}`;
	return `precision highp float;varying vec2 vUV;uniform float warpTime;uniform float warpMode;uniform vec4 warpColour;void main(){vec2 p=vUV*2.0-vec2(1.0);float r=length(p);float angle=atan(p.y,p.x);float alpha;
	if(warpMode<.5){float outer=1.0-smoothstep(.015,.043,abs(r-.81));float inner=1.0-smoothstep(.009,.024,abs(r-.56));float runes=step(.90,cos(angle*12.0+warpTime*.08))*(1.0-smoothstep(.02,.09,abs(r-.69)));alpha=(outer*.80+inner*.34+runes*.60)*(1.0-smoothstep(.93,1.0,r));}
	else{float ellipse=length(p*vec2(1.0,.88));float rim=1.0-smoothstep(.008,.037,abs(ellipse-.87));float swirl=.5+.5*sin(angle*3.0+r*14.0-warpTime*.8);alpha=(1.0-smoothstep(.82,.94,ellipse))*(.06+.17*swirl)+rim*.80;}
	gl_FragColor=vec4(warpColour.rgb,clamp(alpha*warpColour.a,0.0,.78));}`;
}
export function createDungeonWarpFx(scene:Scene,origin:Vector3,mobile=false){
	const wgsl=scene.getEngine().isWebGPU,materials:ShaderMaterial[]=[];
	const material=(name:string,mode:number)=>{const m=new ShaderMaterial(name,scene,{vertexSource:wgsl?vertexWG:vertexGL,fragmentSource:fragment(wgsl)},
		{attributes:['position','uv'],uniforms:['worldViewProjection','warpTime','warpMode','warpColour'],needAlphaBlending:true,shaderLanguage:wgsl?ShaderLanguage.WGSL:ShaderLanguage.GLSL});
		m.backFaceCulling=false;m.disableDepthWrite=true;m.setFloat('warpMode',mode);m.setFloat('warpTime',0);m.setColor4('warpColour',new Color4(.28,.65,.92,.55));materials.push(m);return m;};
	const ground=CreateDisc('dungeon-warp-rune-ground',{radius:2.6,tessellation:48},scene);ground.rotation.x=Math.PI/2;ground.position.copyFrom(origin);ground.position.y+=.025;ground.material=material('dungeon-warp-ground-mat',0);
	const veil=CreatePlane('dungeon-warp-aperture',{width:4.4,height:4.8},scene);veil.position.copyFrom(origin);veil.position.y+=2.42;veil.billboardMode=Mesh.BILLBOARDMODE_Y;veil.material=material('dungeon-warp-aperture-mat',1);
	for(const mesh of [ground,veil]){mesh.isPickable=false;mesh.receiveShadows=false;mesh.metadata={glow:true,warpFx:true};mesh.setEnabled(false);}
	const texels=new Uint8Array(32*32*4);for(let y=0;y<32;y++)for(let x=0;x<32;x++){const i=(y*32+x)*4,r=Math.hypot((x+.5)/16-1,(y+.5)/16-1);texels.set([255,255,255,Math.round(Math.max(0,1-r)**2*255)],i);}
	const texture=new RawTexture(texels,32,32,Constants.TEXTUREFORMAT_RGBA,scene,false,false);texture.hasAlpha=true;
	const particles=new ParticleSystem('dungeon-warp-motes',mobile?24:64,scene);particles.particleTexture=texture;particles.emitter=new Vector3(origin.x,origin.y+.15,origin.z);
	particles.minEmitBox=new Vector3(-1.8,0,-.4);particles.maxEmitBox=new Vector3(1.8,.2,.4);particles.direction1=new Vector3(-.06,.5,-.06);particles.direction2=new Vector3(.06,.9,.06);
	particles.minSize=.05;particles.maxSize=.15;particles.minLifeTime=.8;particles.maxLifeTime=1.8;particles.emitRate=mobile?10:26;
	particles.color1=new Color4(.35,.72,.96,.6);particles.color2=new Color4(.86,.51,.73,.45);particles.colorDead=new Color4(.25,.42,.68,0);
	particles.minEmitPower=.5;particles.maxEmitPower=1;particles.updateSpeed=.015;particles.blendMode=ParticleSystem.BLENDMODE_STANDARD;
	let visible=false,emitting=false,disposed=false,warmReady=false,warmError='';
	void Promise.all([materials[0].forceCompilationAsync(ground),materials[1].forceCompilationAsync(veil)]).then(()=>{
		if(!disposed){particles.isReady();warmReady=true;}
	},error=>{if(!disposed)warmError=String(error);});
	const dispose=()=>{if(disposed)return;disposed=true;visible=false;emitting=false;particles.dispose(false);texture.dispose();for(const mesh of [ground,veil])mesh.dispose(false,false);for(const m of materials)m.dispose(false,false);};
	scene.onDisposeObservable.addOnce(dispose);
	return {update(timeMs:number,active:boolean,ready:boolean,busy=false){if(disposed)return;
		active=active&&warmReady;
		if(visible!==active){visible=active;ground.setEnabled(active);veil.setEnabled(active);}
		const emit=active&&ready&&!busy;if(emit!==emitting){emitting=emit;if(emit)particles.start();else{particles.stop();particles.reset();}}
		if(!active)return;const colour=busy?new Color4(.73,.47,.91,.8):ready?new Color4(.35,.76,.95,.95):new Color4(.46,.40,.60,.42);
		for(const m of materials){m.setFloat('warpTime',timeMs/1000);m.setColor4('warpColour',colour);}},
		stats:()=>({visible,emitting,warmReady,warmError,meshDraws:visible?2:0,particleCapacity:mobile?24:64,particleDraws:emitting?1:0,triangles:ground.getTotalIndices()/3+veil.getTotalIndices()/3,newRenderTargets:0,newDynamicLights:0}),dispose};
}
