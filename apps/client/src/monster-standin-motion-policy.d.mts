export type MonsterStandinPhase='windup'|'leap'|'impact'|'recovery'|'idle';
export const MONSTER_STANDIN_SPECIES:Readonly<Record<number,string>>;
export function sampleMonsterStandinPose(kind:number,phase?:MonsterStandinPhase,elapsedMs?:number,seed?:number,reduceMotion?:boolean):{scale:number[];y:number;pitch:number;roll:number};
