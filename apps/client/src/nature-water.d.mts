export interface WaterTier{readonly lod:number;readonly draws:number;readonly fetches:number;readonly normalStart:number;readonly normalEnd:number;readonly exponent:number;readonly glint:number;readonly gpuMs:number;readonly cpuMs:number;}
export const WATER_TIERS:Readonly<Record<string,WaterTier>>;
export function waterTier(value:string):WaterTier;
export function flowCycle(phase:number):{a:number;b:number;weightB:number};
export function fallsTrajectory(t:number):{x:number;y:number;z:number};
export function depthOpacity(depth:number,viewY?:number):number;
export function decodeFlow(r:number,g:number):number[];
export function varianceExponent(exponent:number,dx:number,dy:number):number;
export function validateWaterManifest<T>(m:T):T;
export interface WaterTerrainSample{body:string;heightY:number;surfaceY:number;depthM:number;distanceToShoreM:number;}
export function createWaterTerrainSampler(derived:unknown):(x:number,z:number)=>WaterTerrainSample|null;
export function rainPuddleVisibility(state:{ready:boolean;revealed:boolean;culled:boolean;rain:number}):boolean;
export function supportedRainPuddles<T extends{id:string;center_xz:number[];outline_xz:number[][];surface_y:number}>(bodies:T[],groundAt:(x:number,z:number)=>number|null,options?:{maxOutlineVertices:32|48}):{accepted:T[];pending:string[]};
export function rainPuddleAtlasUV(point:number[],centre:number[],rx:number,rz:number,organic?:boolean):[number,number];
