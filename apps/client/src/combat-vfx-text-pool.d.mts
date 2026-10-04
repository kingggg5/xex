export const TEXT_TYPES: Readonly<{normal:0;crit:1;hurt:2;word:3;heal:4;exp:5;counter:6;tick:7}>;
export const TEXT_LIFE_MS: readonly number[];
export interface CombatTextSlot {index:number;active:boolean;target:string;source:string;relation:string;type:number;amount:number;text:string;x:number;y:number;z:number;born:number;lastHit:number;expires:number;lane:number;side:number;dirty:boolean}
export interface CombatTextEvent {x:number;y:number;z:number;type:number;amount?:number;text?:string;targetId?:string|number;sourceId?:string|number;relation?:'mine'|'party'|'other'}
export function compactCombatAmount(value:number):string;
export function createCombatTextPool(mobile?:boolean):{slots:CombatTextSlot[];readonly cap:number;setMobile(value:boolean):void;expire(now:number):void;spawn(event:CombatTextEvent,now:number):CombatTextSlot|null;clear():void;active():CombatTextSlot[]};
