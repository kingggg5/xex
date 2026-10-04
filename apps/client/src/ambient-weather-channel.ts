import type {Scene} from '@babylonjs/core/scene';
import type {EnvironmentSample} from './world-environment-state.mjs';
export interface WeatherFrame {
 appearance:EnvironmentSample; worldMs:number; phase:number; clockRevision:number;
}
const readers=new WeakMap<Scene,()=>WeatherFrame>();
/** Scene-local borrowed DTO. Babylon objects never enter the UI state. */
export function registerWeatherReader(scene:Scene,read:()=>WeatherFrame) {
 if(readers.has(scene))throw new Error('Scene already owns a weather clock');
 readers.set(scene,read);
 return ()=>{if(readers.get(scene)===read)readers.delete(scene);};
}
export function readWeatherFrame(scene:Scene):WeatherFrame|null {return readers.get(scene)?.()??null;}
