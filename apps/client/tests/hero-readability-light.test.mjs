import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';
export {bindHeroReadabilityLight} from './src/hero-readability-light';
`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
test('night fill uses the supplied clock and only the hero meshes; disposing restores scene resources',async()=>{
	const engine=new api.NullEngine(),scene=new api.Scene(engine);
	const body=api.MeshBuilder.CreateBox('hero',{},scene),lod=api.MeshBuilder.CreateBox('hero-lod',{},scene),world=api.MeshBuilder.CreateBox('world',{},scene);
	let daylight=1;
	const before=scene.onBeforeRenderObservable.observers.length;
	const dispose=api.bindHeroReadabilityLight(scene,[body,lod],()=>daylight);
	const light=scene.getLightByName('hero-night-readability');
	assert.equal(light.intensity,0);
	assert.ok(light.canAffectMesh(body));assert.ok(light.canAffectMesh(lod));assert.equal(light.canAffectMesh(world),false);
	daylight=0;scene.onBeforeRenderObservable.notifyObservers(scene);assert.equal(light.intensity,.48);
	daylight=.5;scene.onBeforeRenderObservable.notifyObservers(scene);assert.equal(light.intensity,.24);
	daylight=NaN;scene.onBeforeRenderObservable.notifyObservers(scene);assert.equal(light.intensity,0);
	assert.equal(light.getShadowGenerator(),null);
	dispose();dispose();assert.equal(scene.lights.length,0);
	// Babylon defers physical observer-array removal until the next task.
	await new Promise(resolve=>setTimeout(resolve,0));
	assert.equal(scene.onBeforeRenderObservable.observers.length,before);
	scene.dispose();engine.dispose();
});
test('an empty hero creates no scene-wide fill; scene disposal releases a real fill',()=>{
	const engine=new api.NullEngine(),scene=new api.Scene(engine);
	api.bindHeroReadabilityLight(scene,[])();assert.equal(scene.lights.length,0);
	const body=api.MeshBuilder.CreateBox('hero',{},scene);
	api.bindHeroReadabilityLight(scene,[body],()=>0);scene.dispose();assert.equal(scene.lights.length,0);engine.dispose();
});
