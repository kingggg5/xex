import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
const root=fileURLToPath(new URL('..',import.meta.url));
const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {TransformNode} from '@babylonjs/core/Meshes/transformNode';
export {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
export {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial';
export {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
export {ShaderLanguage} from '@babylonjs/core/Materials/shaderLanguage';
export {VertexBuffer} from '@babylonjs/core/Buffers/buffer';
export {createActorFeedback} from './src/combat-vfx-feedback';
export {createVfxMaterial} from './src/combat-vfx-surface';
export {COMBAT_GLYPH_SHADERS} from './src/combat-vfx-glyph-shader';
export {createWorldCombatLabels} from './src/world-combat-labels';`,resolveDir:root,loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
const illegalSwizzle=/\.[xyzwrgba]{2,4}\s*(?:=(?!=)|[+*\/-]=)/;
function fixture(run){const engine=new api.NullEngine(),scene=new api.Scene(engine);try{return run({engine,scene});}finally{scene.dispose();engine.dispose();}}
test('effective Standard/PBR feedback WGSL writes a whole mutable vec4 preserving alpha; GLSL stays distinct',()=>fixture(({scene})=>{
	for(const [Material,variable] of [[api.StandardMaterial,'color'],[api.PBRMaterial,'finalColor']]){
		const material=new Material('feedback-'+variable,scene),visual=new api.TransformNode('cosmetic-'+variable,scene),feedback=api.createActorFeedback(scene,visual,[material]);
		const plugin=material.pluginManager.getPlugin('CombatActorFeedback');
		const wgsl=plugin.getCustomCode('fragment',api.ShaderLanguage.WGSL).CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR;
		assert.doesNotMatch(wgsl,illegalSwizzle);assert.ok(wgsl.includes(`${variable}=vec4f(mix(${variable}.rgb,`));assert.ok(wgsl.includes(`,${variable}.a)`));
		const glsl=plugin.getCustomCode('fragment',api.ShaderLanguage.GLSL).CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR;assert.ok(glsl.includes(`${variable}.rgb=mix`));feedback.dispose();material.dispose();visual.dispose();
	}
}));
test('installed WGSL fragment sources have the same mutable output variables and hook',async()=>{
	const standard=await readFile(new URL('../node_modules/@babylonjs/core/ShadersWGSL/default.fragment.js',import.meta.url),'utf8');
	const pbr=await readFile(new URL('../node_modules/@babylonjs/core/ShadersWGSL/pbr.fragment.js',import.meta.url),'utf8');
	const composition=await readFile(new URL('../node_modules/@babylonjs/core/ShadersWGSL/ShadersInclude/pbrBlockFinalColorComposition.js',import.meta.url),'utf8');
	assert.match(standard,/var color\s*:\s*vec4/);assert.match(standard,/#define CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR/);
	assert.match(composition,/var finalColor\s*:\s*vec4/);assert.match(pbr,/#define CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR/);
});
test('all effective owned glyph and VFX surface WGSL snippets avoid multi-component lvalue writes',()=>fixture(({scene})=>{
	for(const shader of Object.values(api.COMBAT_GLYPH_SHADERS.wgsl))assert.doesNotMatch(shader,illegalSwizzle);
	const texture=api.RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene,false,false);
	const {material,fx}=api.createVfxMaterial(scene,'owned-shader-review',{map:texture,noise:texture,core:'#ffffff',mid:'#0099ff',edge:'#004477'});
	for(const stage of ['vertex','fragment'])for(const code of Object.values(fx.getCustomCode(stage,api.ShaderLanguage.WGSL)))assert.doesNotMatch(code,illegalSwizzle);
	material.dispose();texture.dispose();
}));
test('NullEngine glyph layout stores finite UVs within the atlas and signed lane offsets, without a GPU',()=>{
	const oldCanvas=globalThis.OffscreenCanvas;
	globalThis.OffscreenCanvas=class{constructor(width,height){this.width=width;this.height=height;}getContext(){return new Proxy({}, {get:()=>()=>{},set:()=>true});}};
	try{fixture(({scene})=>{
		let now=0;const labels=api.createWorldCombatLabels(scene,[],{groundAt:()=>0,now:()=>now,mobile:true,locale:'th'});
		labels.showWord(1,2,'parry',2.2,{targetId:1});labels.showDamage(2,2,9999999,'crit',2.2,{targetId:2});labels.showDamage(3,2,12,'heal',2.2,{targetId:3});
		now=80;scene.onBeforeRenderObservable.notifyObservers(scene);
		// getVerticesData is sized to the four base-quad vertices, not the instance count.
		const mesh=scene.getMeshByName('combat-text-glyph-instances'),uv=mesh.getVertexBuffer('ctGlyph').getFloatData(mesh.thinInstanceCount,true),layout=mesh.getVertexBuffer('ctLayout').getFloatData(mesh.thinInstanceCount,true),time=mesh.getVertexBuffer('ctTime').getFloatData(mesh.thinInstanceCount,true);
		assert.equal(mesh.thinInstanceCount,256);assert.ok(uv.every(v=>Number.isFinite(v)&&v>=0&&v<=1));assert.ok(layout.every(Number.isFinite));
		assert.ok(time.includes(-1));assert.ok(time.includes(1),JSON.stringify({firstTimeFloats:time.slice(0,24),slots:labels.diagnostics().slots}));assert.ok(labels.diagnostics().slots.some(s=>s.text==='ปัดป้อง!'));
		assert.ok(uv[1]<uv[3],'stored V min/max are ordered after canvas upload inversion');labels.dispose();
	});}finally{globalThis.OffscreenCanvas=oldCanvas;}
});
