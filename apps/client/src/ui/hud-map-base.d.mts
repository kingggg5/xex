export interface MapBase { readonly extent:number;readonly meshes:Array<{kind:string;vertices:Float32Array;indices:Uint32Array}>;readonly polygons:Array<{kind:string;points:Float32Array}>;readonly routes:Array<{width:number;points:Float32Array}>;readonly byteLength:number;readonly vertexCount:number;readonly triangleCount:number; }
export const MAP_BASE_LIMITS:Readonly<{rasterSize:number;bytes:number;vertices:number;triangles:number;surfaces:number;polygons:number}>;
export function projectMapPoint(x:number,z:number,centerX:number,centerZ:number,extent:number,size?:number,inset?:number):{x:number;y:number}|null;
export function mapBaseCrop(baseExtent:number,centerX:number,centerZ:number,viewExtent:number,rasterSize?:number,size?:number,inset?:number):{sx:number;sy:number;sw:number;sh:number;dx:number;dy:number;dw:number;dh:number}|null;
export function compileMapBase(bundle:unknown,extent:number):MapBase|null;
export function rasterizeMapBase(model:MapBase,canvas:HTMLCanvasElement):boolean;
export function createMapBaseLoader(fetcher?:typeof fetch,url?:string):{acquire(extent:number):{promise:Promise<MapBase|null>;release():void}};
export const sharedMapBaseLoader:ReturnType<typeof createMapBaseLoader>;
