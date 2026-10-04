export type WeatherMode = 'auto'|'clear'|'cloudy'|'rain'|'fog';
export interface EnvironmentPreference {readonly weather:WeatherMode;readonly cycle:boolean;}
export interface EnvironmentSample {
	readonly hours:number;readonly daylight:number;readonly dawn:number;readonly weather:Exclude<WeatherMode,'auto'>;
	readonly rain:number;readonly cloud:number;readonly sunIntensity:number;readonly hemisphereIntensity:number;
	readonly fogDensity:number;readonly windStrength:number;readonly skyBrightness:number;
	readonly direction:readonly number[];readonly clockText:string;
}
export function getEnvironmentPreference():EnvironmentPreference;
export function setEnvironmentPreference(partial:Partial<EnvironmentPreference>):EnvironmentPreference;
export function subscribeEnvironmentPreference(listener:(preference:EnvironmentPreference)=>void):()=>void;
export function sampleEnvironment(elapsedMs:number,prefs?:EnvironmentPreference):EnvironmentSample;
