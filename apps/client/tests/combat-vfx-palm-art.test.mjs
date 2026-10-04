import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
test('versioned Gale palm is an RGBA PNG and the original kit texture remains available',async()=>{
	const texture=await readFile(new URL('../src/assets/vfx/gale-palm-candidate-v2/gale-palm-wave.png',import.meta.url));
	assert.deepEqual([...texture.subarray(0,8)],[137,80,78,71,13,10,26,10]);assert.equal(texture.subarray(12,16).toString(),'IHDR');
	assert.equal(texture.readUInt32BE(16),1254);assert.equal(texture.readUInt32BE(20),1254);assert.equal(texture[25],6,'PNG colour type6 carries true RGBA');
	const old=await readFile(new URL('../src/assets/vfx/kit-v1/vfx_palm_sigil.png',import.meta.url));assert.equal(old.length,423319);
	const kit=await readFile(new URL('../src/combat-vfx-kit.ts',import.meta.url),'utf8');assert.match(kit,/gale-palm-candidate-v2\/gale-palm-wave.png\?url/);
});
