import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const compile=async name=>{
	const result=await build({entryPoints:[fileURLToPath(new URL(`../src/${name}.ts`,import.meta.url))],bundle:true,write:false,format:'esm',platform:'node',logLevel:'silent'});
	return import('data:text/javascript;base64,'+Buffer.from(result.outputFiles[0].text).toString('base64'));
};
const cache=await compile('asset-runtime-cache');
const reset=await compile('renderer-manual-reset');
const paint=await compile('boot-first-paint');
class Observable {
	listeners=new Map();
	add(fn){const key={};this.listeners.set(key,{fn,once:false});return key;}
	addOnce(fn){const key=this.add(fn);this.listeners.get(key).once=true;return key;}
	remove(key){this.listeners.delete(key);}
	emit(value){for(const [key,{fn,once}] of [...this.listeners]){if(once)this.listeners.delete(key);fn(value);}}
}
test('late-renderer paint gate waits two visible frames and aborts/cancels without loading in a hidden tab',async()=>{
	const originals={document:globalThis.document,requestAnimationFrame:globalThis.requestAnimationFrame,cancelAnimationFrame:globalThis.cancelAnimationFrame};
	const document=new EventTarget();document.visibilityState='hidden';const callbacks=new Map();let next=1;
	globalThis.document=document;globalThis.requestAnimationFrame=fn=>{const id=next++;callbacks.set(id,fn);return id;};globalThis.cancelAnimationFrame=id=>callbacks.delete(id);
	const tick=()=>{const entries=[...callbacks.values()];callbacks.clear();for(const fn of entries)fn();};
	try{
		let resolved=false;const pending=paint.afterVisibleBootPaint().then(value=>{resolved=value;return value;});assert.equal(callbacks.size,0);
		document.visibilityState='visible';document.dispatchEvent(new Event('visibilitychange'));assert.equal(callbacks.size,1);tick();await Promise.resolve();assert.equal(resolved,false);tick();assert.equal(await pending,true);
		const abort=new AbortController();const cancelled=paint.afterVisibleBootPaint(abort.signal);assert.equal(callbacks.size,1);abort.abort();assert.equal(await cancelled,false);assert.equal(callbacks.size,0);
	}finally{Object.assign(globalThis,originals);}
});
const texture=(ready=false)=>({getClassName:()=> 'Texture',isReady:()=>ready,onLoadObservable:new Observable(),onDisposeObservable:new Observable(),_buffer:new Uint8Array(24)});

test('ready-only texture release also handles delayed initialization and scene disposal without per-frame work',async()=>{
	const first=texture(true),loading=texture(false);const scene={textures:[first,loading],onNewTextureAddedObservable:new Observable(),onDisposeObservable:new Observable()};
	const dispose=cache.installReadyTextureCacheRelease(scene);assert.equal(first._buffer,null);assert.ok(loading._buffer);
	loading.isReady=()=>true;loading.onLoadObservable.emit(loading);assert.equal(loading._buffer,null);
	const delayed={getClassName:()=> 'Texture',isReady:()=>false};scene.onNewTextureAddedObservable.emit(delayed);
	Object.assign(delayed,texture(true));await new Promise(resolve=>queueMicrotask(resolve));assert.equal(delayed._buffer,null);
	const last=texture(false);scene.onNewTextureAddedObservable.emit(last);await new Promise(resolve=>queueMicrotask(resolve));assert.equal(last.onLoadObservable.listeners.size,1);
	dispose();assert.equal(last.onLoadObservable.listeners.size,0);assert.equal(scene.onNewTextureAddedObservable.listeners.size,0);
	last.isReady=()=>true;last.onLoadObservable.emit(last);assert.ok(last._buffer);dispose();
});

test('static cache release rejects an unaudited geometry sharing owner; clears once after every owner is certified',()=>{
	let clears=0;const shared=new ArrayBuffer(64),geometry={isReady:()=>true,getVertexBuffers:()=>({position:{isUpdatable:()=>false,getData:()=>new Float32Array(shared)}}),getIndices:()=>new Uint16Array(6),clearCachedData:()=>clears++};
	const make=()=>({metadata:{cpuCacheRelease:'render-only-static'},geometry,isPickable:false,computeWorldMatrix:()=>{}});const a=make(),b=make();geometry.meshes=[a,b];
	const scene={getEngine:()=>({doNotHandleContextLost:true})};
	assert.equal(cache.releasePreparedStaticGeometry(scene,[a]).released,0);assert.equal(clears,0);
	const result=cache.releasePreparedStaticGeometry(scene,[a,b]);assert.equal(result.released,1);assert.equal(result.estimatedFreedBytes,76);assert.equal(result.actualMemoryMeasured,false);assert.equal(clears,1);
	assert.equal(cache.releasePreparedStaticGeometry(scene,[a,b]).released,0);assert.equal(clears,1);
});

test('manual DOM, engine and WebGPU loss routes deduplicate; restoration does not resume released graphics',async()=>{
	const originals={window:globalThis.window,document:globalThis.document,location:globalThis.location};
	const canvas=new EventTarget(),button=new EventTarget();Object.assign(button,{hidden:true,disabled:false,focus(){}});
	const panel={hidden:true,setAttribute(){}},status={textContent:''},windowTarget=new EventTarget();let reloads=0,stops=0,lost=0,resolveLoss;
	globalThis.window=windowTarget;windowTarget.addEventListener('aetherfield:renderer-lost',()=>lost++);
	globalThis.document={documentElement:{lang:'en'},getElementById:id=>({'renderer-recovery':panel,'renderer-recovery-status':status,'renderer-reload':button}[id])};globalThis.location={reload:()=>reloads++};
	const engine={isDisposed:false,isWebGPU:true,_device:{lost:new Promise(resolve=>resolveLoss=resolve)},getRenderingCanvas:()=>canvas,stopRenderLoop:()=>stops++,onContextLostObservable:new Observable(),onDisposeObservable:new Observable()};
	try{
		const dispose=reset.installManualRendererReset(engine);canvas.dispatchEvent(new Event('webglcontextlost'));engine.onContextLostObservable.emit(engine);resolveLoss({reason:'unknown'});await Promise.resolve();
		assert.equal(stops,1);assert.equal(lost,1);assert.equal(panel.hidden,false);assert.equal(button.hidden,false);assert.match(status.textContent,/Reload/);assert.equal(reset.isRendererResetRequired(engine),true);
		canvas.dispatchEvent(new Event('webglcontextrestored'));assert.equal(panel.hidden,false);assert.equal(reset.isRendererResetRequired(engine),true);
		button.dispatchEvent(new Event('click'));button.dispatchEvent(new Event('click'));assert.equal(reloads,1);
		dispose();assert.equal(engine.onContextLostObservable.listeners.size,0);canvas.dispatchEvent(new Event('webglcontextlost'));assert.equal(stops,1);
	}finally{Object.assign(globalThis,originals);}
});
