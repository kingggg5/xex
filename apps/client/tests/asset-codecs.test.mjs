import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {KTX2_ASSET_KEYS,resolveCodecUrlManifest} from '../src/codec-url-manifest.mjs';
const source=new URL('../src/asset-codecs.ts',import.meta.url),workerSource=new URL('../src/ktx2decoder.worker.ts',import.meta.url);
const manifest=()=>Object.fromEntries(KTX2_ASSET_KEYS.map(key=>[key,`/assets/${key}-012345.${key==='jsMSCTranscoder'?'js':'wasm'}`]));
test('all nine resources resolve against the page origin before worker init',()=>{
	const urls=resolveCodecUrlManifest(manifest(),'http://127.0.0.1:5173/nested/game?x=1');
	assert.equal(Object.keys(urls).length,9);assert.ok(Object.isFrozen(urls));assert.ok(Object.values(urls).every(url=>url.startsWith('http://127.0.0.1:5173/assets/')));
});
test('missing binaries, external origins, inline assets and wrong extensions fail closed',()=>{
	for(const key of KTX2_ASSET_KEYS){const urls=manifest();delete urls[key];assert.throws(()=>resolveCodecUrlManifest(urls,'https://game.test/play'),/Missing local decoder/);}
	for(const bad of ['https://cdn.babylonjs.com/zstddec.wasm','data:application/wasm;base64,AAAA','blob:https://game.test/a','/assets/fake.js','https://user:pass@game.test/zstddec.wasm'])assert.throws(()=>resolveCodecUrlManifest({...manifest(),wasmZSTDDecoder:bad},'https://game.test/play'));
});
test('installed wasm package has exactly the full admitted transcoder roster; URL imports cannot inline',async()=>{
	const code=await readFile(source,'utf8'),worker=await readFile(workerSource,'utf8');
	const imports=[...code.matchAll(/@babylonjs\/ktx2decoder\/wasm\/([^"?]+)\?url&no-inline/g)].map(match=>match[1]);
	assert.deepEqual(imports.slice().sort(),['msc_basis_transcoder.js','msc_basis_transcoder.wasm','uastc_astc.wasm','uastc_bc7.wasm','uastc_r8_unorm.wasm','uastc_rg8_unorm.wasm','uastc_rgba8_srgb_v2.wasm','uastc_rgba8_unorm_v2.wasm','zstddec.wasm'].sort());
	for(const file of imports)assert.ok((await readFile(new URL(`../node_modules/@babylonjs/ktx2decoder/wasm/${file}`,import.meta.url))).length>0);
	assert.match(code,/postMessage\(\{ action: "init",urls \}\)/);assert.match(worker,/resolveCodecUrlManifest\(event.data.urls/);assert.match(worker,/workerFunction\(KTX2Decoder\)/);assert.doesNotMatch(code+worker,/https?:\/\/|msc-js|msc-wasm/);
});
test('compiled worker applies every URL before decoding, without network during initialization',async()=>{
	const messages=[],requests=[],scope={URL,location:{href:'http://127.0.0.1:5173/assets/worker-ab12.js'},postMessage:value=>messages.push(value),fetch:url=>{requests.push(url);throw new Error('No network allowed in init');}};
	scope.self=scope;vm.createContext(scope);
	vm.runInContext(await readFile(new URL('../src/assets/codecs/ktx2decoder.worker.js',import.meta.url),'utf8'),scope,{timeout:1000});
	const urls=resolveCodecUrlManifest(manifest(),'http://127.0.0.1:5173/play');scope.onmessage({data:{action:'init',urls}});
	assert.equal(messages[0]?.action,'init');assert.equal(requests.length,0);
	const types={wasmUASTCToASTC:'LiteTranscoder_UASTC_ASTC',wasmUASTCToBC7:'LiteTranscoder_UASTC_BC7',wasmUASTCToRGBA_UNORM:'LiteTranscoder_UASTC_RGBA_UNORM',wasmUASTCToRGBA_SRGB:'LiteTranscoder_UASTC_RGBA_SRGB',wasmUASTCToR8_UNORM:'LiteTranscoder_UASTC_R8_UNORM',wasmUASTCToRG8_UNORM:'LiteTranscoder_UASTC_RG8_UNORM',wasmMSCTranscoder:'MSCTranscoder',wasmZSTDDecoder:'ZSTDDecoder'};
	for(const [key,type] of Object.entries(types))assert.equal(scope.KTX2DECODER[type].WasmModuleURL,urls[key]);
	assert.equal(scope.KTX2DECODER.MSCTranscoder.JSModuleURL,urls.jsMSCTranscoder);assert.equal(scope.KTX2DECODER.MSCTranscoder.UseFromWorkerThread,true);
	assert.throws(()=>scope.onmessage({data:{action:'init',urls:{...urls,wasmUASTCToASTC:'https://cdn.babylonjs.com/uastc_astc.wasm'}}}),/same-origin/);
});
