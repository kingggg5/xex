import type {DeathStateDTO} from './ui/combat-model';
export function parseDeathNotice(value:unknown):DeathStateDTO|null;
export function parseCombatGain(kind:string,value:unknown):{kind:'heal';amount:number;hp:number;max_hp:number}|{kind:'exp_gain';base:number;job:number;monster_id:number;x:number;z:number}|null;
