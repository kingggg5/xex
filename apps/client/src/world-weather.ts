import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { ParticleSystem } from "@babylonjs/core/Particles/particleSystem";
import type { Scene } from "@babylonjs/core/scene";
import type { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import type { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import type { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import type { ResolvedGraphicsPreset } from "./graphics-quality.mjs";
import type { NatureClock } from "./nature-motion";
import {getEnvironmentPreference, sampleEnvironment, subscribeEnvironmentPreference} from "./world-environment-state.mjs";
import {createCelestialSky} from "./world-celestial";
import {updateAmbientAppearance} from "./ambient-world";
import {sampleLookGrade} from './look-grade-v2.mjs';
import {registerWeatherReader} from './ambient-weather-channel';
import {applyWeatherImageProcessing} from './weather-image-processing.mjs';

/** Scene-owned visual weather; UI receives only the small appearance DTO. */
export function createWorldWeather(scene: Scene, sun: DirectionalLight, fill: HemisphericLight,
	ground: PBRMaterial, clock: NatureClock) {
	let prefs = getEnvironmentPreference();
	let baseMs = 0;
	let anchor = performance.now();
	let lastTick = -1;
	let published = "";
	let lastUpdate = 0;
	let budget = 64;
	let waterDetail = .6;
	let wet = 0;
	let clockRevision=0;
	let currentAppearance=sampleEnvironment(0,prefs);
	let externalRain=false;
	let fogDensityOverride: ((appearance: ReturnType<typeof sampleEnvironment>) => number | null) | null = null;
	const frame={appearance:currentAppearance,worldMs:0,phase:0,clockRevision:0};
	const unregisterReader=registerWeatherReader(scene,()=>{
		frame.appearance=currentAppearance;frame.worldMs=baseMs+performance.now()-anchor;
		frame.phase=clock.phase;frame.clockRevision=clockRevision;return frame;
	});
	let rain: ParticleSystem | null = null;
	let texture: DynamicTexture | null = null;
	const debug = new URLSearchParams(location.search);
	const hourPreview = import.meta.env.DEV && debug.has("envHour") ? Number(debug.get("envHour")) : NaN;
	const weatherPreview = import.meta.env.DEV ? debug.get("envWeather") : null;
	const lookV2=import.meta.env.DEV&&debug.get('look')==='v2';
	const emitter = new Vector3();
	const sky = scene.getMaterialByName("env-sky-material") as StandardMaterial | null;
	const cloud = scene.getMaterialByName("cloud-white") as StandardMaterial | null;
	const warm = new Color3(1, .9, .74);
	const moon = new Color3(.45, .59, .91);
	const sunColor = new Color3();
	const dayFog = Color3.FromHexString("#b8d2e6");
	const nightFog = Color3.FromHexString("#182a43");
	const fog = new Color3();
	const leafFill = new WeakMap<StandardMaterial, Color3>();
	const unsubscribe = subscribeEnvironmentPreference(value => { prefs = value; });
	const celestial = createCelestialSky(scene);
	function ensureRain() {
		if (rain) return rain;
		texture = new DynamicTexture("weather-rain-streak", {width:4,height:32}, scene, false);
		const ctx = texture.getContext() as CanvasRenderingContext2D;
		ctx.clearRect(0,0,4,32);
		const gradient = ctx.createLinearGradient(0,0,0,32);
		gradient.addColorStop(0,"rgba(220,240,255,0)");
		gradient.addColorStop(.7,"rgba(220,240,255,.65)");
		gradient.addColorStop(1,"rgba(220,240,255,0)");
		ctx.fillStyle=gradient; ctx.fillRect(1,0,2,32); texture.hasAlpha=true; texture.update();
		rain = new ParticleSystem("weather-rain", 512, scene);
		rain.updateSpeed=1/60;
		rain.particleTexture=texture; rain.emitter=emitter;
		rain.minEmitBox=new Vector3(-12,8,-12); rain.maxEmitBox=new Vector3(12,16,12);
		rain.direction1=new Vector3(-.4,-1,.1); rain.direction2=new Vector3(-.2,-1,.2);
		rain.minEmitPower=14; rain.maxEmitPower=19;
		rain.minLifeTime=.55; rain.maxLifeTime=.9;
		rain.minSize=.10; rain.maxSize=.18;
		rain.minScaleX=rain.maxScaleX=.12; rain.minScaleY=rain.maxScaleY=2.6;
		rain.color1=new Color4(.75,.87,1,.4); rain.color2=new Color4(.65,.78,.9,.3);
		rain.colorDead=new Color4(.65,.78,.9,0);
		rain.gravity=new Vector3(0,-3,0); rain.emitRate=0; rain.start();
		return rain;
	}
	const observer = scene.onBeforeRenderObservable.add(() => {
		const now=performance.now();
		if(now-lastUpdate<200)return;
		const dt=Math.min(1,(now-lastUpdate)/1000); lastUpdate=now;
		const previewElapsed = Number.isFinite(hourPreview)
			? (((hourPreview % 24 + 24) % 24 - 13.5 + 24) % 24) / 24 * 2_700_000 : baseMs+now-anchor;
		const appearancePrefs = weatherPreview && ["clear","cloudy","rain","fog"].includes(weatherPreview)
			? {...prefs, weather: weatherPreview as "clear"|"cloudy"|"rain"|"fog"} : prefs;
		const state=sampleEnvironment(previewElapsed,Number.isFinite(hourPreview) ? {...appearancePrefs,cycle:true}:appearancePrefs);
		currentAppearance=state;
		const look=lookV2?sampleLookGrade(state):null;
		celestial.update(state);
		const ambientOwnsSky=updateAmbientAppearance(scene,look?{...state,skyPalette:look}:state);
		wet+=(state.rain-wet)*(1-Math.exp(-dt*.20));
		sun.intensity=state.sunIntensity;
		sun.direction.copyFromFloats(state.direction[0],state.direction[1],state.direction[2]);
		Color3.LerpToRef(moon,warm,state.daylight,sunColor); sun.diffuse.copyFrom(sunColor);
		fill.intensity=state.hemisphereIntensity;
		applyWeatherImageProcessing(scene.imageProcessingConfiguration,state.daylight,look);
		// Art pass v1: moonlit grade - cooler and less saturated at night; the day keeps the +16 saturation grade.
		const grade=scene.imageProcessingConfiguration.colorCurves;
		if(grade){const night=1-state.daylight;grade.globalSaturation=16-night*40;grade.shadowsHue=225;grade.shadowsDensity=night*45;grade.midtonesHue=215;grade.midtonesDensity=night*22;}
		Color3.LerpToRef(nightFog,dayFog,state.daylight,fog); scene.fogColor.copyFrom(fog);
		const fogOverride=fogDensityOverride?.(state);
		const targetFog=typeof fogOverride==='number'&&Number.isFinite(fogOverride)&&fogOverride>=0&&fogOverride<=.08
			?fogOverride:(look?.fogDensity??state.fogDensity);
		scene.fogDensity += (targetFog-scene.fogDensity)*(1-Math.exp(-dt*.15));
		if(sky?.emissiveTexture)sky.emissiveTexture.level=ambientOwnsSky?1:state.skyBrightness;
		if(cloud) {cloud.alpha=.65+state.cloud*.28; cloud.emissiveColor.set(.10+state.daylight*.15,.12+state.daylight*.15,.17+state.daylight*.11);}
		for(const material of scene.materials){
			if(!(material instanceof StandardMaterial)||!/leaf-cards|foliage/.test(material.name))continue;
			if(!leafFill.has(material))leafFill.set(material,material.emissiveColor.clone());
			leafFill.get(material)?.scaleToRef(.24+state.daylight*.76,material.emissiveColor);
		}
		ground.roughness=.94-wet*.22;
		ground.albedoColor.set(.91-wet*.10,.94-wet*.08,.86-wet*.08);
		clock.strength=state.windStrength;
		clock.waterStrength=(.5+waterDetail*.5)*(1+wet*.35);
		if(look){
			sun.diffuse.set(...look.sun as [number,number,number]);sun.intensity=look.sunIntensity;
			fill.diffuse.set(...look.fill as [number,number,number]);fill.groundColor.set(...look.ground as [number,number,number]);fill.intensity=look.fillIntensity;
			scene.fogColor.set(...look.fog as [number,number,number]);
			if(grade)grade.globalSaturation=look.saturation;
		}
		if(!externalRain&&(state.rain>0||wet>.03)){
			const system=ensureRain(); emitter.copyFrom(scene.activeCamera?.position ?? Vector3.Zero());
			system.emitRate=Math.round(budget*wet);
			if(!system.isStarted())system.start();
		} else if(rain?.isStarted()) {rain.emitRate=0;rain.stop();}
		const key=`${state.clockText}:${state.weather}`;
		if(key!==published){
			published=key;
			window.dispatchEvent(new CustomEvent("aetherfield:environment-state",{detail:{clockText:state.clockText,weather:state.weather,hours:state.hours}}));
		}
	});
	scene.onDisposeObservable.addOnce(()=>{
		unsubscribe();unregisterReader();scene.onBeforeRenderObservable.remove(observer);rain?.dispose(false);texture?.dispose();
	});
	return {
		/** One density owner: the caller may supply a palette resolver without another frame loop. */
		setFogDensityOverride(provider: typeof fogDensityOverride){fogDensityOverride=provider;},
		setWorldTick(tick:number){
			if(!Number.isFinite(tick)||tick<0)return;
			if(tick>=lastTick||tick<lastTick-100){if(tick<lastTick-100)clockRevision++;baseMs=tick*50;anchor=performance.now();lastTick=tick;}
		},
		useExternalRain(){externalRain=true;rain?.dispose(false);texture?.dispose();rain=null;texture=null;},
		setQuality(profile:ResolvedGraphicsPreset){budget=Math.min(512,profile.weatherParticleBudget);waterDetail=profile.waterDetail;},
	};
}
