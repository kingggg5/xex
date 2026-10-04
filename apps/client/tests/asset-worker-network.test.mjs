import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';

test('compiled decoder blocks actual CDN fetch/importScripts calls and allows local calls without rewriting',async()=>{
	const requests=[],scripts=[],messages=[],scope={URL,location:{href:'https://game.test/assets/worker.js'},postMessage:message=>messages.push(message),fetch:async input=>{requests.push(input);return {ok:true};},importScripts:(...urls)=>scripts.push(...urls)};
	scope.self=scope;vm.createContext(scope);
	vm.runInContext(await readFile(new URL('../src/assets/codecs/ktx2decoder.worker.js',import.meta.url),'utf8'),scope,{timeout:1000});
	await assert.rejects(scope.fetch('https://cdn.babylonjs.com/zstddec.wasm'),/Blocked unexpected/);
	assert.throws(()=>scope.importScripts('https://cdn.babylonjs.com/msc_basis_transcoder.js'),/Blocked unexpected/);
	assert.equal(requests.length,0);assert.equal(scripts.length,0);assert.equal(messages.filter(message=>message.kind==='cdn-blocked').length,2);
	await scope.fetch('https://game.test/assets/zstd-hash.wasm');scope.importScripts('https://game.test/assets/msc-hash.js');
	assert.deepEqual(requests,['https://game.test/assets/zstd-hash.wasm']);assert.deepEqual(scripts,['https://game.test/assets/msc-hash.js']);
});
