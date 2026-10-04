import test from 'node:test';
import assert from 'node:assert/strict';
import {fnv1a64Halves} from '../src/boot-content-hash.mjs';
import {fnv1a64} from '../src/wire.mjs';
import {createManualGraphicsReset,rendererFailureReason} from '../src/renderer-reset-policy.mjs';
import {assertNoBabylonCdn,guardAssetUrlHook,classifyKtx2Result,resolveWebGpuCompilerUrls} from '../src/asset-network-policy.mjs';
import {geometryReleaseBlocker,textureReleaseBlocker,referencedBytes} from '../src/asset-cache-policy.mjs';
import {rendererBootPolicy} from '../src/renderer-boot-policy.mjs';

test('halves preserve FNV-1a-64 empty, known ASCII, Thai, every byte, carry-heavy and deterministic fixtures',()=>{
	assert.equal(fnv1a64Halves(new Uint8Array()),0xcbf29ce484222325n);
	assert.equal(fnv1a64Halves(new TextEncoder().encode('hello')),0xa430d84680aabd0bn);
	const fixtures=[new TextEncoder().encode('เมือง Xexoria 🌳'),Uint8Array.from({length:256},(_,i)=>i),new Uint8Array(32768).fill(255)];
	let seed=0xdeadbeef;const bytes=new Uint8Array(8192);for(let i=0;i<bytes.length;i++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;bytes[i]=seed>>>24;}fixtures.push(bytes);
	for(const fixture of fixtures)assert.equal(fnv1a64Halves(fixture),fnv1a64(fixture));
	assert.throws(()=>fnv1a64Halves([1,2]),TypeError);
});

test('both engines disable automatic restoration while preserving nine-feature maximum-limits policy',()=>{
	for(const mobile of [false,true]){const policy=rendererBootPolicy(mobile);assert.equal(policy.doNotHandleContextLost,true);assert.equal(policy.webGpuOptions.doNotHandleContextLost,true);assert.equal(policy.webGpuOptions.setMaximumLimits,true);assert.equal(policy.webGpuOptions.deviceDescriptor.requiredFeatures.length,9);}
});

test('manual reset deduplicates multiple loss routes and reload clicks; never auto-restores',()=>{
	const calls=[];let timer;
	const control=createManualGraphicsReset({onLost:reason=>calls.push(reason),onReload:()=>calls.push('reload'),schedule:fn=>{timer=fn;return 1;},cancel:()=>{}});
	assert.equal(control.reload(),false);assert.equal(control.lost('webgpu-device-lost'),true);assert.equal(control.lost(),false);
	assert.equal(control.reload(),true);assert.equal(control.reload(),false);assert.deepEqual(calls,['webgpu-device-lost','reload']);
	timer();assert.equal(control.state(),'lost');assert.equal(control.reload(),true);control.dispose();timer();assert.equal(control.state(),'disposed');assert.equal(control.lost(),false);
});

test('fallback reason is bounded, redacts URLs and does not probe the adapter',()=>{
	const reason=rendererFailureReason(new Error('GPU failed https://example.test/?token=secret\n'+ 'x'.repeat(500)));
	assert.ok(reason.length<=306);assert.ok(!reason.includes('secret'));assert.ok(!reason.includes('\n'));assert.match(reason,/\[URL\]/);
});

test('actual CDN destination checks reject direct and rewritten URLs, not local files or lookalike hosts',()=>{
	for(const url of ['https://cdn.babylonjs.com/a.wasm','//CDN.BABYLONJS.COM/a.js','https://cdn.babylonjs.com:443/a'])assert.throws(()=>assertNoBabylonCdn(url,'https://game.test/play'),/Blocked unexpected/);
	for(const url of ['/assets/a.wasm','blob:https://game.test/id','https://cdn.babylonjs.com.evil.test/a'])assert.equal(assertNoBabylonCdn(url,'https://game.test/play'),url);
	let blocked=0;const hook=guardAssetUrlHook(()=> 'https://cdn.babylonjs.com/a.wasm','https://game.test/',()=>blocked++);
	assert.throws(()=>hook('/assets/a.wasm'));assert.equal(blocked,1);
});

test('diagnostics identify decoded RGBA fallback separately from native RGBA and deliberate R8/RG8',()=>{
	const result=classifyKtx2Result({transcodedFormat:32856,transcoderName:'UniversalTranscoder_UASTC_RGBA_UNORM',width:1024,height:1024});
	assert.equal(result.rgbaFallback,true);assert.equal(result.uncompressedRgba,true);assert.ok(Object.isFrozen(result));
	assert.equal(classifyKtx2Result({transcodedFormat:32856,transcoderName:'UncompressedRGBA32Transcoder'}).rgbaFallback,false);
	for(const format of [33321,33323,36492,37808])assert.equal(classifyKtx2Result({transcodedFormat:format}).rgbaFallback,false);
	assert.equal(classifyKtx2Result({transcodedFormat:NaN}),null);
	assert.equal(classifyKtx2Result({transcodedFormat:32856,errors:'transcoding failed'}),null);
});

test('WebGPU custom-shader compilers use complete same-origin hashed URLs; missing/CDN/wrong-extension fails closed',()=>{
	const files={glslangJs:'/assets/glslang-aa.js',glslangWasm:'/assets/glslang-bb.wasm',twgslJs:'/assets/twgsl-cc.js',twgslWasm:'/assets/twgsl-dd.wasm'};
	const result=resolveWebGpuCompilerUrls(files,'https://game.test/play');assert.equal(result.glslangOptions.jsPath,'https://game.test/assets/glslang-aa.js');assert.equal(result.twgslOptions.wasmPath,'https://game.test/assets/twgsl-dd.wasm');
	for(const changed of [{twgslWasm:undefined},{glslangJs:'https://cdn.babylonjs.com/a.js'},{glslangWasm:'/assets/wrong.js'}])assert.throws(()=>resolveWebGpuCompilerUrls({...files,...changed},'https://game.test/'));
});

const mesh=()=>({metadata:{cpuCacheRelease:'render-only-static'},geometry:{isReady:()=>true,getVertexBuffers:()=>({position:{isUpdatable:()=>false}})},isPickable:false,checkCollisions:false});
test('static geometry defaults deny and independently protects actor, picker, physics, skin, morph and updated sources',()=>{
	assert.equal(geometryReleaseBlocker(mesh(),false),'not-audited');assert.equal(geometryReleaseBlocker({...mesh(),metadata:{}},true),'missing-owner-certificate');assert.equal(geometryReleaseBlocker(mesh(),true),null);
	for(const [property,value,expected] of [['isPickable',true,'picking'],['checkCollisions',true,'collision-or-physics'],['physicsBody',{},'collision-or-physics'],['skeleton',{},'skin-or-morph'],['morphTargetManager',{},'skin-or-morph'],['hasThinInstances',true,'thin-instances-retained'],['animations',[{}],'animated']])assert.equal(geometryReleaseBlocker({...mesh(),[property]:value},true),expected);
	assert.equal(geometryReleaseBlocker({...mesh(),geometry:{isReady:()=>true,getVertexBuffers:()=>({position:{isUpdatable:()=>true}})}},true),'updatable-buffer');
	assert.equal(geometryReleaseBlocker({...mesh(),metadata:{cpuCacheRelease:'render-only-static',monsterId:1}},true),'dynamic-or-interactive');
	assert.equal(geometryReleaseBlocker({...mesh(),instances:[{isPickable:false,metadata:{}}]},true),'unaudited-instance');
});

test('texture cache waits for upload-ready binary file sources and leaves atlases/dynamic sources alone',()=>{
	const texture={getClassName:()=> 'Texture',isReady:()=>true,_buffer:new Uint8Array(12)};
	assert.equal(textureReleaseBlocker(texture),null);assert.equal(textureReleaseBlocker({...texture,isReady:()=>false}),'not-ready');
	assert.equal(textureReleaseBlocker({...texture,getClassName:()=> 'DynamicTexture'}),'not-file-texture');
	assert.equal(textureReleaseBlocker({...texture,metadata:{uiAtlas:true}}),'retained-source');
	assert.equal(textureReleaseBlocker({...texture,_buffer:{}}),'not-binary-source');
	const backing=new ArrayBuffer(64);assert.equal(referencedBytes([new Uint8Array(backing,0,8),new Uint8Array(backing,8,8),backing]),64);
});
