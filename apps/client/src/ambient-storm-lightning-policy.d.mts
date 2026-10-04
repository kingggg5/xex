export interface LightningPoint {readonly x:number;readonly y:number;readonly z:number;}
export interface LightningQuality {readonly preset?:string;readonly formFactor?:string;}
export interface LightningAppearance {readonly rain:number;readonly daylight:number;}
export interface LightningScheduleOptions {
	readonly quality?:LightningQuality;
	readonly reducedMotion?:boolean;
	readonly reducedFlashes?:boolean;
	readonly clockRevision?:string|number;
}
export interface LightningFrame {
	active:boolean;began:boolean;eligible:boolean;ageMs:number;opacity:number;flash:number;
	seed:number;startedAtMs:number;nextAtMs:number|null;generation:number;
}
export const LIGHTNING_LIFETIME_MS:480;
export const LIGHTNING_FLASH_MS:120;
export const LIGHTNING_PATHS:4;
export const LIGHTNING_POINTS_PER_PATH:25;
export function lightningQuality(quality?:LightningQuality):{paths:number;minimumIntervalMs:number;flashScale:number};
export function lightningEnvelope(ageMs:number):number;
export function lightningFlashEnvelope(ageMs:number):number;
export function createLightningSchedule(seed?:number):{
	update(worldMs:number,appearance:LightningAppearance,options?:LightningScheduleOptions):LightningFrame;
	reset():void;
};
export function writeLightningPaths(seed:number,focus:LightningPoint,viewDirection:LightningPoint|undefined,output:Float32Array):LightningPoint;
