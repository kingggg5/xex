import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';

const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {createStormRain} from './src/ambient-storm-rain';
export {rainBudget,rainAmount,rainWind,rainMask} from './src/ambient-storm-rain-policy';
`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));

function fixture(options={}) {
	const engine=new api.NullEngine({renderWidth:896,renderHeight:414,textureSize:32});
	const scene=new api.Scene(engine),rain=api.createStormRain(scene,options);
	let time=0;
	return {engine,scene,rain,
		step(frames=1,{amount=1,wind=1,focus={x:0,y:2,z:0},phase=.5}={}) {
			for(let i=0;i<frames;i++) {
				time+=1000/60;rain.update({rain:amount,windStrength:wind,worldMs:time},phase,focus);
				for(const system of scene.particleSystems)system.animate(true);
			}
		},
		close(){rain.dispose();scene.dispose();engine.dispose();},
	};
}

test('contact particles count against every preset and injected shared budget',()=>{
	for(const [quality,expected] of [['low',24],['medium',64],['high',144],['ultra',288]]) {
		const budget=api.rainBudget(quality);assert.equal(budget.total,expected);
		assert.equal(budget.near+budget.far+budget.contacts,expected);
		assert.equal(api.rainBudget(quality,19).total,19);
	}
	assert.equal(api.rainBudget('medium',NaN).total,0);
	assert.equal(api.rainAmount(1,true,false),0);assert.equal(api.rainAmount(NaN,false,false),0);
	assert.equal(api.rainAmount(1,false,true),.45);
});
test('wind is continuous across the existing phase wrap, with finite bounded inputs',()=>{
	const a=api.rainWind(1,0),b=api.rainWind(1,Math.PI*2);
	assert.ok(a.every((v,i)=>Math.abs(v-b[i])<1e-10));
	assert.deepEqual(api.rainWind(NaN,NaN),[0,0]);
});
test('two tiny masks are bounded, transparent at their edges and readable in the centre',()=>{
	const streak=api.rainMask('streak'),ring=api.rainMask('contact');
	assert.equal(streak.byteLength+ring.byteLength,4096);
	assert.equal(streak[3],0);assert.ok(streak[(16*16+8)*4+3]>200);
	assert.ok(ring.some((v,i)=>i%4===3 && v>150));
});
test('real Babylon pools stay within preset caps and dispose all owned systems and textures',()=>{
	for(const quality of ['low','medium','high','ultra']) {
		const f=fixture({quality,surfaceHeight:()=>2});
		try {
			f.step(180);
			const d=f.rain.diagnostics();assert.ok(d.activeParticles>0);assert.ok(d.activeParticles<=d.budget.total);
			assert.equal(f.scene.particleSystems.length,3);assert.equal(d.textureBytes,4096);
			f.rain.dispose();f.rain.dispose();assert.equal(f.scene.particleSystems.length,0);assert.equal(f.scene.textures.length,0);
			f.step(1);assert.equal(f.rain.diagnostics().activeParticles,0);
		} finally {f.close();}
	}
});
test('ground contact rings come from the retiring rain drop on supplied support, without per-drop queries',()=>{
	let queries=0;const f=fixture({quality:'high',surfaceHeight:()=>{queries++;return 2;}});
	try {
		const near=f.scene.particleSystems.find(x=>x.name.endsWith('-near'));
		const impacts=f.scene.particleSystems.find(x=>x.name.endsWith('-contacts'));
		let observedContacts=0;
		for(let i=0;i<180;i++) {
			f.step(1);
			for(const p of impacts.particles) {observedContacts++;assert.ok(Math.abs(p.position.y-2.025)<1e-5);}
		}
		assert.ok(f.rain.diagnostics().impactsEmitted>0);
		assert.ok(f.rain.diagnostics().impactsEmitted<=queries,'each sampled landing supports at most one impact');
		assert.ok(queries<=60,'two surface probes per 100ms rather than one ray per drop');
		// Inspect real CPU particle state only in this test: no fake renderer or particle pool.
		assert.ok(observedContacts>0);
		for(const p of near.particles)assert.ok(p.position.y>=2.025-1e-4);
		assert.equal(impacts.isBillboardBased,false,'rings lie on the ground instead of facing the camera');
		assert.equal(impacts.minEmitPower,0,'ring vertices do not fly upward');
	} finally {f.close();}
});
test('unknown ground emits no contact rings, even after the rain pool fills',()=>{
	const f=fixture({quality:'medium',surfaceHeight:()=>null});
	try {f.step(180);assert.equal(f.rain.diagnostics().impactsEmitted,0);assert.ok(f.rain.diagnostics().rejectedGround>0);} finally {f.close();}
});
test('rain zero, shelter, invalid focus and rewind cancel stale particles and contacts',()=>{
	const f=fixture({surfaceHeight:()=>2});
	try {
		f.step(100);f.step(1,{amount:0});assert.equal(f.rain.diagnostics().activeParticles,0);
		f.step(100);f.step(1,{focus:{x:0,y:2,z:0,sheltered:true}});assert.equal(f.rain.diagnostics().activeParticles,0);
		f.step(100);f.step(1,{focus:{x:NaN,y:2,z:0}});assert.equal(f.rain.diagnostics().activeParticles,0);
		f.step(100);f.rain.update({rain:1,windStrength:1,worldMs:0},0,{x:0,y:2,z:0});assert.equal(f.rain.diagnostics().activeParticles,0);
	} finally {f.close();}
});
test('quality switches rebuild only owned pools; reduced motion disables the far streak layer',()=>{
	const f=fixture({quality:'ultra',surfaceHeight:()=>2});
	try {
		f.step(100);f.rain.setQuality('low',12);f.step(100);
		assert.equal(f.scene.particleSystems.length,3);assert.equal(f.rain.diagnostics().budget.total,12);
		assert.ok(f.rain.diagnostics().activeParticles<=12);
		f.rain.setReducedMotion(true);f.step(100);
		assert.equal(f.scene.particleSystems.find(x=>x.name.endsWith('-far')).getActiveCount(),0);
		assert.equal(f.rain.diagnostics().reducedMotion,true);
		f.scene.dispose();assert.equal(f.rain.diagnostics().disposed,true);
	} finally {f.close();}
});
