import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {writeFile,realpath} from 'node:fs/promises';
import {join,resolve,relative,isAbsolute,sep} from 'node:path';
import {homedir} from 'node:os';
const root=fileURLToPath(new URL('..',import.meta.url));
const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';
export {Vector3,Matrix} from '@babylonjs/core/Maths/math.vector';
export {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
export {GetEnvironmentBRDFTexture} from '@babylonjs/core/Misc/brdfTextureTools';
export {ShaderLanguage} from '@babylonjs/core/Materials/shaderLanguage';
export {ShaderStore} from '@babylonjs/core/Engines/shaderStore';
export {Initialize,Process,Finalize,_FunctionContainer} from '@babylonjs/core/Engines/Processors/shaderProcessor';
export {WebGPUShaderProcessorWGSL} from '@babylonjs/core/Engines/WebGPU/webgpuShaderProcessorsWGSL';
export {WebGPUShaderProcessingContext} from '@babylonjs/core/Engines/WebGPU/webgpuShaderProcessingContext';
export {createCityWaterEngine} from './src/city-water-engine';`,resolveDir:root,loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent',plugins:[{name:'inert-cpu-url',setup(b){b.onResolve({filter:/\?url$/},a=>({path:a.path,namespace:'inert-cpu-url'}));b.onLoad({filter:/.*/,namespace:'inert-cpu-url'},()=>({contents:'export default "not-loaded-cpu-fixture";',loader:'js'}));}}]});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
async function fixture(wgsl,run){
	const engine=new api.NullEngine();engine._isWebGPU=wgsl;
	// Both production backends use the UBO branch; NullEngine defaults to WebGL1.
	Object.defineProperty(engine,'supportsUniformBuffers',{value:true});
	const scene=new api.Scene(engine),camera=new api.FreeCamera('camera',new api.Vector3(2,3,-8),scene);
	camera.setTarget(api.Vector3.Zero());scene.activeCamera=camera;scene.updateTransformMatrix(true);
	const normal=api.RawTexture.CreateRGBATexture(new Uint8Array([128,128,255,255]),1,1,scene,false,false);
	// Babylon retains one BRDF/context-restore observer for the whole scene.
	api.GetEnvironmentBRDFTexture(scene);
	const counts={before:scene.onBeforeRenderObservable.observers.length,dispose:scene.onDisposeObservable.observers.length};
	const water=api.createCityWaterEngine(scene,17,{phase:0},{normalTexture:normal});
	try{await water.ready;return await run({engine,scene,camera,water,counts});}
	finally{water.dispose();normal.dispose();scene.dispose();engine.dispose();}
}
async function processedGraph(material,engine,wgsl){
	api._FunctionContainer.loadFile=(url)=>{throw new Error('CPU fixture missing shader include: '+url);};
	const options={defines:['#define LIGHT1','#define SHADOWS','#define SHADOW1','#define SHADOWCSM1','#define SHADOWCSMNUM_CASCADES1 2','#define SHADOWLOWQUALITY1'],indexParameters:{maxSimultaneousLights:4,maxSimultaneousMorphTargets:0},isFragment:false,shouldUseHighPrecisionShader:true,supportsUniformBuffers:engine.supportsUniformBuffers,shadersRepository:'',includesShadersStore:wgsl?api.ShaderStore.IncludesShadersStoreWGSL:api.ShaderStore.IncludesShadersStore,processor:wgsl?new api.WebGPUShaderProcessorWGSL():null,version:'300',platformName:wgsl?'WEBGPU':'WEBGL2',processingContext:wgsl?new api.WebGPUShaderProcessingContext(api.ShaderLanguage.WGSL):null,isNDCHalfZRange:wgsl,useReverseDepthBuffer:false};
	api.Initialize(options);
	const processShader=(code,isFragment)=>new Promise(resolve=>api.Process(code,{...options,isFragment},resolve,engine));
	const vertex=await processShader(material._vertexCompilationState._builtCompilationString,false);
	const fragment=await processShader(material._fragmentCompilationState._builtCompilationString,true);
	const output={options,...api.Finalize(vertex,fragment,options)};
	if(process.env.WATER_VIEW_PROBE_DIR){
		const assetRoot=resolve(process.env.XEXORIA_ASSET_SOURCE_ROOT||join(homedir(),'Downloads','Xexoria-Game'));
		const allowed=await realpath(resolve(process.env.XEXORIA_AGENT_OUTPUT||join(assetRoot,'agent-output')));
		const directory=await realpath(resolve(process.env.WATER_VIEW_PROBE_DIR)),within=relative(allowed,directory);
		assert.ok(!isAbsolute(within)&&within!=='..'&&!within.startsWith('..'+sep),'CPU shader evidence must stay under the configured agent-output root');
		// Exclusive creation also rejects an existing output-file symlink or accidental overwrite.
		await writeFile(join(directory,`water-csm-light1.${wgsl?'wgsl':'glsl'}`),output.vertexCode,{flag:'wx'});
	}
	return output;
}
test('actual water WGSL graph processes CSM light 1 with a matching LeftOver view matrix member',()=>fixture(true,async({water,engine})=>{
	const m=water.materials[0],out=await processedGraph(m,engine,true);
	assert.match(out.vertexCode,/vPositionFromCamera1\s*=\s*uniforms\.view\s*\*/);
	assert.match(out.vertexCode,/struct LeftOver[\s\S]*?\bview\s*:\s*mat4x4/);
	assert.ok(out.options.processingContext.leftOverUniforms.some(u=>u.name==='view'&&/mat4/.test(u.type)));
	assert.equal(m._vertexCompilationState.uniforms.includes('u_view'),false);
	assert.doesNotMatch(out.vertexCode,/#include<|\{X\}/);
	assert.equal(water.meshes.every(mesh=>mesh.receiveShadows),true);
}));
test('actual water GLSL graph keeps u_view and the SDK local view alias for CSM light 1',()=>fixture(false,async({water,engine})=>{
	const out=await processedGraph(water.materials[0],engine,false);
	assert.match(out.vertexCode,/uniform\s+mat4\s+u_view\s*;/);
	assert.match(out.vertexCode,/mat4\s+view\s*=\s*u_view\s*;/);
	assert.match(out.vertexCode,/vPositionFromCamera1\s*=\s*view\s*\*/);
	assert.doesNotMatch(out.vertexCode,/uniform\s+mat4\s+view\s*;/);
}));
test('SDK InputBlock binding transmits the current camera view after movement in both languages, and disposal removes observers',async()=>{
	for(const wgsl of [false,true])await fixture(wgsl,async({scene,camera,water,counts})=>{
		const material=water.materials[0],input=material.getInputBlockByPredicate(b=>b.name==='view'),calls=[];
		const effect={setMatrix(name,matrix){calls.push({name,matrix:matrix.asArray().slice()});}};
		input._transmit(effect,scene,material);const before=scene.getViewMatrix().asArray().slice();
		camera.position.x+=7;camera.setTarget(new api.Vector3(1,0,2));scene.updateTransformMatrix(true);
		input._transmit(effect,scene,material);
		assert.equal(calls[0].name,wgsl?'view':'u_view');assert.equal(calls[1].name,calls[0].name);
		assert.deepEqual(calls[0].matrix,before);assert.deepEqual(calls[1].matrix,scene.getViewMatrix().asArray());assert.notDeepEqual(calls[1].matrix,calls[0].matrix);
		assert.equal(material.name,'city-water-engine-pbr');assert.deepEqual(water.meshes.map(mesh=>mesh.position.z),[17,17,17]);
		water.dispose();await new Promise(resolve=>setTimeout(resolve,0));
		assert.equal(scene.onBeforeRenderObservable.observers.length,counts.before);assert.equal(scene.onDisposeObservable.observers.length,counts.dispose,scene.onDisposeObservable.observers.map(o=>String(o.callback)).join('\n'));
	});
});
