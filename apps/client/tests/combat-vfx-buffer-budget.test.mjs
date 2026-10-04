import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url));
const bundled=await build({stdin:{contents:`
import '@babylonjs/core/Buffers/buffer.align';
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {WebGPUCacheRenderPipeline} from '@babylonjs/core/Engines/WebGPU/webgpuCacheRenderPipeline';
export {PushAttributesForInstances} from '@babylonjs/core/Materials/materialHelper.functions';
export {Buffer as BabylonBuffer} from '@babylonjs/core/Buffers/buffer';
export {COMBAT_TEXT_ATTRIBUTES,COMBAT_GLYPH_SHADERS} from './src/combat-vfx-glyph-shader';
export {createWorldCombatLabels} from './src/world-combat-labels';`,resolveDir:root,loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
function fixture(run){
	const old=globalThis.OffscreenCanvas;
	globalThis.OffscreenCanvas=class{constructor(w,h){this.width=w;this.height=h;}getContext(){return new Proxy({}, {get:()=>()=>{},set:()=>true});}};
	const engine=new api.NullEngine(),scene=new api.Scene(engine);let now=100;
	const labels=api.createWorldCombatLabels(scene,[],{groundAt:()=>0,now:()=>now});
	try{return run({engine,scene,labels,tick(time){now=time;scene.onBeforeRenderObservable.notifyObservers(scene);}});}
	finally{labels.dispose();scene.dispose();engine.dispose();globalThis.OffscreenCanvas=old;}
}
function descriptorFor(mesh,vertexBuffers=mesh.geometry.getVertexBuffers()){
	// NullEngine has real DataBuffer identities but no GPU resource. Give each identity
	// a distinct inert token, then run Babylon's actual WebGPU grouping functions.
	for(const vb of Object.values(vertexBuffers)){
		const data=vb.getBuffer();
		if(data&&!data.underlyingResource)Object.defineProperty(data,'underlyingResource',{value:{nullEngineBufferId:data.uniqueId},configurable:true});
	}
	// This is the installed ShaderMaterial's attribute-list construction path;
	// no pretend shader compile or GPU device is involved.
	const attributes=[...mesh.material.options.attributes];api.PushAttributesForInstances(attributes,false);
	const effect={_pipelineContext:{shaderProcessingContext:{attributeNamesFromEffect:attributes,attributeLocationsFromEffect:attributes.map((_,i)=>i)}}};
	const cache=Object.create(api.WebGPUCacheRenderPipeline.prototype);
	Object.assign(cache,{_vertexBuffers:vertexBuffers,_overrideVertexBuffers:null,_states:[],_statesLength:0,_kMaxVertexBufferStride:2048,_stateDirtyLowestIndex:Infinity,vertexBuffers:[]});
	cache._setVertexState(effect);
	return {attributes,descriptors:cache._getVertexInputDescriptor(effect),boundBuffers:cache.vertexBuffers};
}
test('both text meshes use one shared six-vec4 allocation and four actual WebGPU bindings on an eight-buffer device',()=>fixture(({scene})=>{
	for(const name of ['combat-text-glyph-instances','combat-text-burst-instances']){
		const mesh=scene.getMeshByName(name),views=api.COMBAT_TEXT_ATTRIBUTES.map(key=>mesh.getVertexBuffer(key));
		assert.equal(new Set(views.map(view=>view.getBuffer())).size,1,'renaming separate allocations would fail this check');
		views.forEach((view,i)=>{assert.equal(view.byteStride,96);assert.equal(view.byteOffset,i*16);assert.equal(view.getSize(),4);assert.equal(view.getIsInstanced(),true);});
		const actual=descriptorFor(mesh);
		assert.equal(actual.descriptors.length,4);assert.equal(actual.boundBuffers.length,4);assert.ok(actual.descriptors.length<=8);
		const packed=actual.descriptors.find(d=>d.arrayStride===96);
		assert.equal(packed.stepMode,'instance');assert.equal(packed.attributes.length,6);
		assert.deepEqual(packed.attributes.map(a=>a.offset),[0,16,32,48,64,80]);
		const legacyBuffers=[],legacyViews={...mesh.geometry.getVertexBuffers()};
		try{
			for(const key of api.COMBAT_TEXT_ATTRIBUTES){const buffer=new api.BabylonBuffer(mesh.getScene().getEngine(),new Float32Array(mesh.thinInstanceCount*4),true,4,false,true);legacyBuffers.push(buffer);legacyViews[key]=buffer.createVertexBuffer(key,0,4,4,true);}
			assert.equal(descriptorFor(mesh,legacyViews).descriptors.length,9,'the previous allocation layout reproduces the device-limit violation');
		}finally{for(const buffer of legacyBuffers)buffer.dispose();}
		for(const backend of ['glsl','wgsl'])for(const key of api.COMBAT_TEXT_ATTRIBUTES)assert.ok(api.COMBAT_GLYPH_SHADERS[backend].vertex.includes(key));
	}
}));
test('packing preserves target position, colours, time, atlas UVs and expiration through the same WebGL vertex views',()=>fixture(({scene,labels,tick})=>{
	labels.showDamage(12,34,12345,'crit',4.2,{targetId:73,relation:'mine'});tick(180);
	const mesh=scene.getMeshByName('combat-text-glyph-instances'),count=mesh.thinInstanceCount;
	const read=key=>mesh.getVertexBuffer(key).getFloatData(count,true);
	assert.deepEqual(Array.from(read('ctAnchorType').slice(0,4)),[12,Math.fround(4.2),34,1]);
	assert.deepEqual(Array.from(read('ctFill').slice(0,4)),[1,Math.fround(.835),Math.fround(.29),1]);
	assert.equal(read('ctTime')[0],0);assert.equal(read('ctTime')[1],Math.fround(1.2));
	assert.ok(read('ctGlyph').every(v=>v>=0&&v<=1));assert.equal(labels.diagnostics().slots[0].target,'73');
	labels.configure({mobile:true});tick(181);assert.equal(mesh.thinInstanceCount,256);
	tick(1500);assert.equal(labels.diagnostics().active,0);assert.equal(read('ctFill')[3],0);
	const shared=mesh.getVertexBuffer('ctFill').getWrapperBuffer();labels.dispose();assert.equal(shared.isDisposed,true);
}));
