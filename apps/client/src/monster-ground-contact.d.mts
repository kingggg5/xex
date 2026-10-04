import type {MonsterStandinPhase} from './monster-standin-motion-policy.mjs';
export const MAX_MONSTER_CONTACT_VERTICES: number;
export const MONSTER_ROOT_FLOOR_CLEARANCE_M: number;
export interface MonsterGroundContactProfile {
	readonly kind:number;
	readonly vertexCount:number;
	readonly phases:Readonly<Record<MonsterStandinPhase,Readonly<{minimumY:number;supportOffset:number}>>>;
	readonly idleMinimumY:number;
}
export function createMonsterGroundContact(kind:number,positions:ArrayLike<number>):MonsterGroundContactProfile;
