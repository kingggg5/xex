export type MagePilotId='h02_basic'|'h02_star_lance';
export const MAGE_PILOT_IDS:readonly MagePilotId[];
export interface MageSkillMetadata {skill_id:MagePilotId;available:boolean;range_m:number;windup_ms:number;cooldown_ms:number;recovery_ms:number;sp_cost:number;projectile_speed_m_s:number;power:number}
export interface MageTrialState {capability_enabled:boolean;focus_equipped:boolean;profile:'trailblade'|'mage_trial';epoch:number;skills:readonly MageSkillMetadata[]}
export interface MageCastState {cast_id:string;source_id:number;epoch:number;sequence:number;skill_id:MagePilotId;phase:'started'|'released'|'impact'|'cancelled'|'rejected';reason:string;target_id:number;damage:number;flags:number;server_ms:number;start_ms:number;release_ms:number;impact_ms:number|null;recovery_end_ms:number;cooldown_end_ms:number;origin:readonly number[];target:readonly number[]}
export function parseMageTrialState(value:unknown):Readonly<MageTrialState>|null;
export function parseMageCastState(value:unknown):Readonly<MageCastState>|null;
export interface MageCastIntent {t:'mage_cast';epoch:number;sequence:number;skill_id:MagePilotId;target_id:number}
export type MageRecoveryAction=Readonly<{kind:'retry';intent:Readonly<MageCastIntent>}>|Readonly<{kind:'reconnect'}>;
export class MagePilotClient {constructor(now:()=>number);playerId:number;epoch:number;profile:Readonly<MageTrialState>|null;pending:unknown;lastEvent:Readonly<MageCastState>|null;connect(playerId:number,epoch:number):void;setProfile(value:unknown):boolean;request(skillId:MagePilotId,targetId:number,sp:number):{ok:true;intent:Readonly<MageCastIntent>}|{ok:false;reason:string};notSent(sequence:number):void;pollRecovery():MageRecoveryAction|null;receive(value:unknown):Readonly<MageCastState>|null}
