export interface DressingEntry {
  id: string; asset_id: string; variant?: number; class?: string; x: number; y: number; z: number;
  yaw: number; scale: number; footprint_r: number; collider: 'none'|'soft'|'solid'; shadow?: boolean;
  landmark?: boolean; scale_xyz?: [number,number,number]; surface_y?: number;
  blueprint_id?: string; target_height?: number; target_size_xyz?: [number,number,number];
  visual_base_y?: number; visual_absolute_base_y?:number; blueprint_wave?:string; anchor_at_pivot?:boolean; pitch?: number; roll?: number; standin?: boolean; night_lantern?: boolean;
}
export interface DressingAsset {
  id: string; family: string; lods: { file: string; tris: number; sha256?: string }[];
  bounds: { min: number[]; max: number[] }; textures?: { atlas?: string }; status?: string;
  motion?:{nodeNames:string[];axis:number[];pivot:number[];periodSeconds:number};
}
export interface DressingPlan { density: number; near: number; middle: number; end: number; fade: number; triangleBudget: number }
export const DRESSING_ALIASES: Readonly<Record<string, readonly string[]>>;
export function dressingHash(id: string): number;
export function dressingAssetId(entry: DressingEntry, assets: ReadonlyMap<string,DressingAsset>): string|null;
export function dressingPlan(profile: { formFactor?: string; vegetationDensity?: number }): DressingPlan;
export function dressingFocalMinimums(entries:DressingEntry[],assets:ReadonlyMap<string,DressingAsset>,cellLods:ReadonlyMap<string,{minimumLod:number;triangles:number;lod0Triangles:number}>,focalIds:string[],budget?:number):Map<string,{cell:string;baseMinimumLod:number;minimumLod:number;worstCellTriangles:number;budget:number}>;
export function dressingKeep(entry: DressingEntry, density: number): boolean;
export function dressingLodRanges(distance: number, plan: DressingPlan, minimumLod?: number): { lod:number; lower:number; upper:number }[];
export function validateDressing(entries: unknown): DressingEntry[];
export function dressingScale(entry: DressingEntry, bounds: DressingAsset['bounds']): number;
export function blueprintScale(entry: DressingEntry,bounds:DressingAsset['bounds']): [number,number,number];
export function blueprintFloor(entry:DressingEntry,bounds:DressingAsset['bounds'],scale:readonly number[]):number;
export function blueprintEntries(dressing:{entries:unknown;baseline_entries?:unknown},enabled?:boolean):DressingEntry[];
export function applySemanticDressingOverlay<T>(dressing:T,overlay:unknown):T;
export function bakeDressingGeometry<T>(mesh: T,options?:{preserveColor?:boolean}): T;
export function dressingCellLods(entries: readonly DressingEntry[], assets: ReadonlyMap<string,DressingAsset>, budget?:number,reservedTriangles?:ReadonlyMap<string,number>): Map<string,{minimumLod:number;triangles:number;lod0Triangles:number}>;
