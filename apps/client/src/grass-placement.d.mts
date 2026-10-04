export interface GrassInstance {kind:'tuft'|'flower'|'clover';heightClass?:string;x:number;y:number;z:number;yaw:number;height:number;width:number;col:number;mirror:number;opt:number;r:number;tint:number[];ground:number[];ao:number;wind:number;}
export interface GrassRulesData {schema:string;id?:string;seed?:number;domain:number[];[key:string]:unknown;}
export interface GrassRules {id:string;seed:number;domain:number[];ground:{kind:string;color?:number[];tint?:number[]};data:GrassRulesData;}
export interface GrassTier {preset:string;mobile:boolean;enabled:boolean;fTier:number;distance:number;far:number;benders:number;atlas:string;ground:string;plants:boolean;plantDistance:number;}
export interface GrassBands {near:number;mid:number;end:number;far:number;fTier:number;window:number;}
export interface GrassBounds {min:number[];max:number[];}
export interface PackedGrass {count:number;matrices:Float32Array;data:Float32Array;r:Float32Array;bounds:GrassBounds|null;}
export interface GrassGeometry {positions:Float32Array;normals:Float32Array;uvs:Float32Array;indices:Uint16Array;quads:number;vertexCount:number;triangleCount:number;radius:number;fanCount?:number;segmentsPerFan?:number;}
export const PATCH_M:number,PLANT_BLOCK_M:number,PATCH_CAP:number,REGION_CAP:number;
export function compileRules(data:GrassRulesData):GrassRules;
export function grassRulesFromLayout(layout:unknown,dressing?:unknown,monsters?:unknown,derived?:unknown,blueprint?:unknown):GrassRulesData;
export function grassCellAllowance(baseTriangles:number,usedGrassTriangles:number,trianglesPerInstance:number,cellLimit:number):number;
export function generateTuftPatch(rules:GrassRules,i:number,j:number,opts?:{cap?:number}):GrassInstance[];
export function generatePlantBlock(rules:GrassRules,i:number,j:number,opts?:{cap?:number}):{flowers:GrassInstance[];clover:GrassInstance[]};
export function packInstances(list:GrassInstance[]):PackedGrass;
export function patchRange(domain:number[],size?:number):{i0:number;i1:number;j0:number;j1:number};
export function buildTuftGeometry(seed?:number,count?:number):GrassGeometry;
export function buildFlowerGeometry(tips?:unknown,seed?:number):GrassGeometry;
export function buildCloverGeometry(seed?:number):GrassGeometry;
export function resolveGrassTier(profile:unknown):GrassTier;
export function grassBands(tier:GrassTier,cameraRadius?:number):GrassBands;
export function scaleBands(bands:GrassBands,factor:number):GrassBands;
export function prefixFraction(d:number,bands:GrassBands):number;
export function lowerBound(sorted:Float32Array,value:number):number;
export function aabbDistance(eye:number[],bounds:GrassBounds):number;
export function linearFromHex(hex:string):number[];
export function stableHash(value:unknown):string;
export function governGrass(state:{factor:number;quiet:number},submitted:number,cap:number,deltaSeconds:number):{factor:number;quiet:number};
