import test from 'node:test';import assert from 'node:assert/strict';
import {grassCustomCode,GRASS_UNIFORMS} from '../src/grass-field-shaders.mjs';
test('one shader template emits both engine languages with matching hooks and packed attribute',()=>{
	for(const stage of ['vertex','fragment']){const gl=grassCustomCode(stage,false),wg=grassCustomCode(stage,true);assert.deepEqual(Object.keys(gl),Object.keys(wg));const a=Object.values(gl).join('\n'),b=Object.values(wg).join('\n');assert.ok(a.includes('GRASS_FIELD'));assert.ok(b.includes('GRASS_FIELD'));assert.ok(!b.includes('gl_FragCoord'));assert.ok(!b.includes('attribute vec4'));assert.equal((a.match(/^#if/gm)||[]).length,(a.match(/^#endif/gm)||[]).length);assert.equal((b.match(/^#if/gm)||[]).length,(b.match(/^#endif/gm)||[]).length);}
	assert.equal(GRASS_UNIFORMS.length,9);assert.match(grassCustomCode('vertex',true).CUSTOM_VERTEX_DEFINITIONS,/grassInst: vec4f/);
});
