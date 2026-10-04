import {Color4} from '@babylonjs/core/Maths/math.color';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
import {Texture} from '@babylonjs/core/Materials/Textures/texture';
import {ParticleSystem} from '@babylonjs/core/Particles/particleSystem';
import type {Scene} from '@babylonjs/core/scene';
import {rainAmount, rainBudget, rainMask, rainWind, type StormRainQuality} from './ambient-storm-rain-policy';

export interface StormRainSample {
	readonly rain: number;
	readonly windStrength: number;
	/** Supplied by WorldWeather's existing synchronized clock, in milliseconds. */
	readonly worldMs: number;
}
export interface StormRainFocus {readonly x:number; readonly y:number; readonly z:number; readonly sheltered?:boolean;}
export interface StormRainOptions {
	readonly quality?: StormRainQuality;
	readonly particleBudget?: number;
	/** Bounded cached terrain/walk-surface lookup. Return null for water, roofs or unknown support.
	 * Called at most twice per update and 20 times/sec. Never put scene.pick/raycast here. */
	readonly surfaceHeight?: (x:number, z:number) => number | null;
	readonly seed?: number;
}

/** Scene-owned replacement for world-weather's `weather-rain`, not an extra emitter.
 * No own timer/observer, lights, glow, fog or exposure writes. Call update before scene.render().
 * Near drops land at sampled contacts; far streaks are atmospheric only and never spawn contacts. */
export function createStormRain(scene: Scene, options: StormRainOptions = {}) {
	let quality=options.quality ?? 'medium';
	let ceiling=options.particleBudget;
	let budget=rainBudget(quality,ceiling);
	let reducedMotion=false, disposed=false, enabled=false;
	let rng=(options.seed ?? 0x6a19bd) >>> 0;
	const random=()=>{rng=(Math.imul(rng,1664525)+1013904223)>>>0;return rng/4294967296;};
	const focus=new Vector3(), velocity=new Vector3();
	let haveFocus=false, amount=0, worldMs=0, nextGroundMs=-Infinity;
	let groundQueries=0, rejectedGround=0, impactsEmitted=0;
	const anchors=new Float64Array(16*3), valid=new Uint8Array(16);
	let anchorCursor=0;
	const queue=new Float64Array(24*3);
	let queueHead=0, queueCount=0;
	const streak=RawTexture.CreateRGBATexture(rainMask('streak'),16,32,scene,false,false,Texture.BILINEAR_SAMPLINGMODE);
	const contact=RawTexture.CreateRGBATexture(rainMask('contact'),16,32,scene,false,false,Texture.BILINEAR_SAMPLINGMODE);
	streak.name='ambient-storm-rain-streak-mask'; contact.name='ambient-storm-rain-contact-mask';
	for(const texture of [streak,contact]) {texture.hasAlpha=true;texture.wrapU=texture.wrapV=Texture.CLAMP_ADDRESSMODE;}
	let near:ParticleSystem, far:ParticleSystem, impacts:ParticleSystem;

	function configure(name:string, capacity:number, mask:RawTexture) {
		const system=new ParticleSystem(name,Math.max(1,capacity),scene);
		system.particleTexture=mask; system.emitter=Vector3.Zero();
		system.updateSpeed=1/60; system.emitRate=0;
		system.blendMode=ParticleSystem.BLENDMODE_STANDARD;
		system.forceDepthWrite=false; system.applyFog=false;
		system.gravity.setAll(0); system.minEmitPower=system.maxEmitPower=1;
		system.color1=new Color4(.91,.93,.99,.52); system.color2=new Color4(.75,.77,.86,.27);
		system.colorDead=new Color4(.75,.77,.86,0);
		system.disposeOnStop=false;
		return system;
	}
	function buildPools() {
		near=configure('ambient-storm-rain-near',budget.near,streak);
		far=configure('ambient-storm-rain-far',budget.far,streak);
		impacts=configure('ambient-storm-rain-contacts',budget.contacts,contact);
		for(const system of [near,far]) {
			system.billboardMode=ParticleSystem.BILLBOARDMODE_STRETCHED_LOCAL;
			system.minLifeTime=.42;system.maxLifeTime=.78;
			system.minSize=.6;system.maxSize=1;
			system.minScaleX=.028;system.maxScaleX=.044;
			system.minScaleY=.8;system.maxScaleY=1.35;
			system.startDirectionFunction=(_matrix,direction)=>direction.copyFrom(velocity);
		}
		far.minScaleX=.017;far.maxScaleX=.027;far.minScaleY=.45;far.maxScaleY=.8;
		far.color1.a=.22;far.color2.a=.13;
		near.startPositionFunction=(_matrix,position,particle)=>{
			// One cached anchor selected without a raycast or any allocation per drop.
			let selected=-1;
			const first=Math.floor(random()*budget.groundAnchors);
			for(let i=0;i<budget.groundAnchors;i++) {const index=(first+i)%budget.groundAnchors;if(valid[index]) {selected=index;break;}}
			const offset=selected*3;
			const x=selected<0 ? focus.x+(random()-.5)*budget.radius : anchors[offset];
			const y=selected<0 ? focus.y : anchors[offset+1];
			const z=selected<0 ? focus.z+(random()-.5)*budget.radius : anchors[offset+2];
			// Consume each sampled landing only once. Reusing it for many particles would
			// turn natural rainfall into a small number of conspicuous vertical columns.
			if(selected>=0)valid[selected]=0;
			position.set(x-velocity.x*particle.lifeTime,y+.025-velocity.y*particle.lifeTime,z-velocity.z*particle.lifeTime);
			particle.metadata=selected>=0;
		};
		far.startPositionFunction=(_matrix,position,particle)=>{
			const angle=random()*Math.PI*2,radius=budget.radius*(.65+random()*.6);
			position.set(focus.x+Math.cos(angle)*radius-velocity.x*particle.lifeTime,focus.y+2-velocity.y*particle.lifeTime,focus.z+Math.sin(angle)*radius-velocity.z*particle.lifeTime);
		};
		// Babylon clips the final integration step to lifetime before recycling. The captured
		// position is therefore the actual landing point of that drop, not a random ground puff.
		const recycle=near.recycleParticle;
		near.recycleParticle=particle=>{
			if(enabled && particle.metadata===true && budget.contacts>0 && queueCount<budget.contacts && random()<.42
				&& Math.abs(particle.position.y-focus.y)<5) {
				const tail=(queueHead+queueCount)%24,at=tail*3;
				queue[at]=particle.position.x;queue[at+1]=particle.position.y;queue[at+2]=particle.position.z;
				queueCount++; impacts.manualEmitCount=queueCount;
			}
			recycle(particle);
		};
		impacts.manualEmitCount=0;impacts.isBillboardBased=false;
		impacts.minEmitPower=impacts.maxEmitPower=0;
		impacts.minLifeTime=.13;impacts.maxLifeTime=.25;
		impacts.minSize=.11;impacts.maxSize=.23;
		impacts.addSizeGradient(0,.025);impacts.addSizeGradient(.3,.12);impacts.addSizeGradient(1,.23);
		impacts.color1=new Color4(.86,.89,.96,.4);impacts.color2=new Color4(.78,.8,.9,.23);
		impacts.startDirectionFunction=(_matrix,direction)=>direction.set(0,1,0);
		impacts.startPositionFunction=(_matrix,position,particle)=>{
			if(queueCount===0) {particle.lifeTime=0;position.copyFrom(focus);return;}
			const at=queueHead*3;position.set(queue[at],queue[at+1],queue[at+2]);
			queueHead=(queueHead+1)%24;queueCount--;impactsEmitted++;
		};
		// Register the stock shader variants while the caller is still in its warm-up gate.
		for(const system of [near,far,impacts]) system.isReady();
	}
	function clear() {
		enabled=false;queueCount=0;queueHead=0;valid.fill(0);nextGroundMs=-Infinity;
		for(const system of [near,far,impacts]) {system.emitRate=0;system.stop();system.reset();}
		impacts.manualEmitCount=0;
	}
	buildPools();
	const disposal=scene.onDisposeObservable.addOnce(()=>dispose());
	function dispose() {
		if(disposed)return;disposed=true;
		scene.onDisposeObservable.remove(disposal);
		for(const system of [near,far,impacts]) system.dispose(false);
		streak.dispose();contact.dispose();valid.fill(0);queueCount=0;
	}
	return {
		update(sample:StormRainSample,phase:number,nextFocus:StormRainFocus) {
			if(disposed)return;
			const nextAmount=rainAmount(sample.rain,nextFocus.sheltered===true,reducedMotion);
			if(!Number.isFinite(nextFocus.x)||!Number.isFinite(nextFocus.y)||!Number.isFinite(nextFocus.z)||!Number.isFinite(sample.worldMs)) {if(enabled)clear();return;}
			const moved=haveFocus && Math.hypot(nextFocus.x-focus.x,nextFocus.y-focus.y,nextFocus.z-focus.z)>budget.radius*.6;
			if(moved || sample.worldMs<worldMs)clear();
			focus.set(nextFocus.x,nextFocus.y,nextFocus.z);haveFocus=true;worldMs=sample.worldMs;
			amount=nextAmount;
			if(amount===0 || budget.total===0) {if(enabled)clear();return;}
			const wind=rainWind(sample.windStrength,phase);
			velocity.set(wind[0],reducedMotion?-12:-18,wind[1]);
			if(!enabled) {enabled=true;for(const system of [near,far,impacts])system.start();}
			if(options.surfaceHeight && worldMs>=nextGroundMs) {
				nextGroundMs=worldMs+100;
				// Query two landing anchors only; emission never samples the scene.
				for(let query=0;query<2;query++) {
					const index=anchorCursor++%budget.groundAnchors,at=index*3;
					const angle=random()*Math.PI*2,radius=(.22+.75*Math.sqrt(random()))*budget.radius;
					const x=focus.x+Math.cos(angle)*radius,z=focus.z+Math.sin(angle)*radius;
					groundQueries++;
					const y=options.surfaceHeight(x,z);
					valid[index]=y!==null && Number.isFinite(y) && Math.abs(y-focus.y)<=5 ? 1 : 0;
					if(valid[index]) {anchors[at]=x;anchors[at+1]=y!;anchors[at+2]=z;} else rejectedGround++;
				}
			}
			near.emitRate=budget.near*amount*1.6;
			far.emitRate=reducedMotion ? 0 : budget.far*amount*1.5;
		},
		setQuality(value:StormRainQuality,particleBudget?:number) {
			if(disposed)return;
			const next=rainBudget(value,particleBudget);
			if(value===quality && particleBudget===ceiling)return;
			clear();for(const system of [near,far,impacts])system.dispose(false);
			quality=value;ceiling=particleBudget;budget=next;buildPools();
		},
		setReducedMotion(value:boolean) {if(value!==reducedMotion) {reducedMotion=value;if(!disposed)clear();}},
		diagnostics() {
			return {quality,disposed,enabled,reducedMotion,budget,amount,groundQueries,rejectedGround,impactsEmitted,
				activeParticles:disposed?0:near.getActiveCount()+far.getActiveCount()+impacts.getActiveCount(),
				pendingContacts:queueCount,textureBytes:disposed?0:4096,maxDraws:enabled?3:0,
				ready:!disposed && near.isReady() && far.isReady() && impacts.isReady()};
		},
		dispose,
	};
}
