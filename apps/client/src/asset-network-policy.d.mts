export function assertNoBabylonCdn(value:string,baseHref:string):string;
export function guardAssetUrlHook(previous:(url:string)=>string,baseHref:string,onBlocked?:()=>void):(url:string)=>string;
export interface Ktx2Diagnosis {format:number;transcoder:string;width:number|null;height:number|null;uncompressedRgba:boolean;rgbaFallback:boolean}
export function classifyKtx2Result(decoded:unknown):Readonly<Ktx2Diagnosis>|null;
export function resolveWebGpuCompilerUrls(input:unknown,baseHref:string):{glslangOptions:{jsPath:string;wasmPath:string};twgslOptions:{jsPath:string;wasmPath:string}};
