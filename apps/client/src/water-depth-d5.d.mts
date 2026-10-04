export const WATER_DEPTH_D5_REVISION:string;
export function clampD5(x:number,a?:number,b?:number):number;
export function smoothD5(a:number,b:number,x:number):number;
export function sampleWaterAtlasD5(bytes:Uint8Array,width:number,height:number,uv:number[]):number[];
export function waterDepthGraphD5(options:{red:number;viewY?:number;day?:number;art?:boolean;revision?:number;blueprint?:boolean;repairCove?:boolean}):{optical:number;body:number[];opacity:number;middleWeight:number;deepWeight:number};
