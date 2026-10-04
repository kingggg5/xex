export interface WitchVfxDefinition {id:string;hero:'witch02'|'h02';template:string;name:string;visualOnly:true;telegraphShape:string;palette:{core:string;body:string;edge:string;accent:string};coreHeight:number;peakHoldMs:readonly number[];layers:Readonly<Record<'anticipation'|'core'|'secondaries'|'ground'|'after',readonly string[]>>;captureMs:readonly number[];targets:{screenCoverage:readonly number[];ultimateCoverage:readonly number[];colourfulnessM:number;peakHoldRangeMs:readonly number[];coverageDecision?:string};status:string;draftRules?:Readonly<Record<string,{minTier:'low'|'medium'|'high'|'epic';mediumScale:number;kit:readonly string[]}>>;requiredCore?:readonly string[];draftTiming?:{release_ms:number;clip:string};kitReferences?:readonly string[];renderStatus?:string;decisionStatus?:string}
export const VFX_TIER_BUDGETS:Readonly<Record<'low'|'medium'|'high'|'ultra',{draws:number;particles:number;gpuParticles?:number;cpuP95Ms:number}>>;
export const CORE_VFX_IDS:readonly string[];
export const PHYSICAL_VFX_TEMPLATES:readonly string[];
export const HERO02_DRAFT_INFO:{source:string;sha256:string;plannedKitCount:number;decisions:string;priorArt:readonly unknown[]};
export const WITCH_VFX_DEFINITIONS:readonly WitchVfxDefinition[];
export function resolveVfxDefinition(id:string):WitchVfxDefinition|null;
export function auditDraftKit(available:readonly string[]):{plannedCount:number;skills:{id:string;unknown:string[];missing:string[];renderStatus:string;clip:string;clipStatus:string}[]};
export function resolveVfxTier(value:string):'low'|'medium'|'high'|'ultra';
export function draftLayerRule(definition:WitchVfxDefinition,name:string):{minTier:'low'|'medium'|'high'|'epic';mediumScale:number;kit:readonly string[]}|null;
export function validateVfxDefinition(value:unknown):WitchVfxDefinition;
export function selectVfxLayers(definition:WitchVfxDefinition,tier:string,items:readonly {name:string;active:boolean;draws:number;particles?:number;glowDraws?:number}[]):{selected:string[];draws:number;particles:number;budget:typeof VFX_TIER_BUDGETS.high;essentialMissing:string[]};
export function measureVfxRoi(rgba:Uint8Array|Uint8ClampedArray,background:Uint8Array|Uint8ClampedArray,width:number,height:number,roi:{x:number;y:number;width:number;height:number}):{changedPixels:number;screenCoverage:number;colourfulnessM:number|null;whiteClipFraction:number|null;basis:string};
export const PORTAL_VFX_STATES:Readonly<Record<'dormant'|'awakening'|'active'|'locked',{visibleAt:string;burstMs:number}>>;
