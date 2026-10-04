import type {Scene} from '@babylonjs/core/scene';
import type {ResolvedGraphicsPreset} from './graphics-quality.mjs';
import {Color3} from '@babylonjs/core/Maths/math.color';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
import {readWeatherFrame} from './ambient-weather-channel';
import {createNightMotes,type NightMoteCluster} from './ambient-night-motes';
import {createStormRain} from './ambient-storm-rain';
import {createStormLightning} from './ambient-storm-lightning';
import {nightMoteBudget} from './ambient-night-motes-policy.mjs';

interface AtmosphereOptions {
 quality:ResolvedGraphicsPreset;
 focus:()=>{readonly x:number;readonly y:number;readonly z:number};
 groundAt:(x:number,z:number)=>number|null;
 clusters:readonly NightMoteCluster[];
}
/** Drives built-in pooled effects from the sole WorldWeather reader. Review opt-in is owned by the caller. */
export function createAmbientAtmosphere(scene:Scene,options:AtmosphereOptions) {
 let quality=options.quality;
 const motion=matchMedia('(prefers-reduced-motion: reduce)');
 const motes=createNightMotes(scene,{clusters:options.clusters,quality,reducedMotion:motion.matches});
 const rain=createStormRain(scene,{quality:quality.preset,
  particleBudget:Math.max(0,quality.weatherParticleBudget-nightMoteBudget(quality)),surfaceHeight:options.groundAt});
 const cloud=scene.getMaterialByName('ambient-cloud-sprites');
 const cloudBase=cloud instanceof StandardMaterial?cloud.emissiveColor.clone():null;
 const flashWhite=Color3.FromHexString('#f2f0ff');
 let wasFlashing=false;
 const lightning=createStormLightning(scene,{quality,reducedMotion:motion.matches,reducedFlashes:motion.matches,
  onFlash(strength){
   if(!(cloud instanceof StandardMaterial)||!cloudBase)return;
   if(strength>0){if(!wasFlashing)cloudBase.copyFrom(cloud.emissiveColor);Color3.LerpToRef(cloudBase,flashWhite,strength,cloud.emissiveColor);wasFlashing=true;}
   else if(wasFlashing){cloud.emissiveColor.copyFrom(cloudBase);wasFlashing=false;}
  }});
 rain.setReducedMotion(motion.matches);
 const changeMotion=()=>{motes.setReducedMotion(motion.matches);rain.setReducedMotion(motion.matches);lightning.setAccessibility({reducedMotion:motion.matches,reducedFlashes:motion.matches});};
 motion.addEventListener('change',changeMotion);
 const direction=new Vector3();
 const forward=Vector3.Forward(scene.useRightHandedSystem);
 const rainSample={rain:0,windStrength:0,worldMs:0};
 const controls={viewDirection:direction,clockRevision:0};
 const observer=scene.onBeforeRenderObservable.add(()=>{
  const frame=readWeatherFrame(scene);if(!frame)return;
  const focus=options.focus();
  motes.update(frame.appearance,frame.phase,focus);
  rainSample.rain=frame.appearance.rain;rainSample.windStrength=frame.appearance.windStrength;rainSample.worldMs=frame.worldMs;
  rain.update(rainSample,frame.phase,focus);
  const camera=scene.activeCamera;
  if(camera){camera.getDirectionToRef(forward,direction);direction.normalize();}
  controls.clockRevision=frame.clockRevision;
  lightning.update(frame.appearance,frame.worldMs,focus,controls);
 });
 let disposed=false;
 const dispose=()=>{
  if(disposed)return;disposed=true;
  scene.onBeforeRenderObservable.remove(observer);motion.removeEventListener('change',changeMotion);
  motes.dispose();rain.dispose();lightning.dispose();
 };
 scene.onDisposeObservable.addOnce(dispose);
 return {setQuality(next:ResolvedGraphicsPreset){
  quality=next;motes.setQuality(next);lightning.setQuality(next);
  rain.setQuality(next.preset,Math.max(0,next.weatherParticleBudget-nightMoteBudget(next)));
 },diagnostics(){return{motes:motes.diagnostics(),rain:rain.diagnostics(),lightning:lightning.diagnostics()};},
 async prewarm(){motes.prewarm();await lightning.prewarm();},dispose};
}
