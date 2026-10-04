export interface NightMoteCluster {readonly x:number;readonly y:number;readonly z:number;readonly radius:number;readonly kind:'vegetation'|'water';}
export interface NightMoteSeed {readonly x:number;readonly y:number;readonly z:number;readonly phase:number;readonly size:number;readonly cool:boolean;}
export interface NightMoteSample {x:number;y:number;z:number;alpha:number;}
export const NIGHT_MOTE_CAPACITY:72;
export const NIGHT_MOTE_MAX_CLUSTERS:24;
export function nightMoteOpacity(appearance:{readonly daylight:number;readonly rain:number}):number;
export function nightMoteBudget(quality?:{readonly preset?:string;readonly formFactor?:string}):number;
export function createNightMoteSeeds(clusters:readonly NightMoteCluster[]):readonly NightMoteSeed[];
export function sampleNightMote(seed:NightMoteSeed,naturePhase:number,reducedMotion:boolean,focus:{readonly x:number;readonly y:number;readonly z:number},opacity:number,out:NightMoteSample):NightMoteSample;
