/** A bounded presentation/input adapter. Rust owns resources, hits, rewards and profile access. */
export const MAGE_PILOT_IDS=Object.freeze(['h02_basic','h02_star_lance']);
const uint=(n,min=0,max=0xffffffff)=>Number.isSafeInteger(n)&&n>=min&&n<=max;
const finite=(n,min,max)=>typeof n==='number'&&Number.isFinite(n)&&n>=min&&n<=max;
const point=p=>Array.isArray(p)&&p.length===3&&p.every(n=>finite(n,-10000,10000));
const phases=new Set(['started','released','impact','cancelled','rejected']);
const recoveryIntervalMs=1000,unknownWindowMs=4500,maxRetries=3;
const validRecovery=message=>message.release_ms>=message.start_ms&&message.release_ms-message.start_ms<=5000&&message.recovery_end_ms>=message.release_ms&&message.recovery_end_ms-message.release_ms<=5000;
const validCooldown=message=>message.cooldown_end_ms>=message.start_ms&&message.cooldown_end_ms-message.start_ms<=60000;
export function parseMageTrialState(value){
 if(!value||value.t!=='mage_trial_state'||typeof value.capability_enabled!=='boolean'||typeof value.focus_equipped!=='boolean'||!['trailblade','mage_trial'].includes(value.profile)||!uint(value.epoch)||!Array.isArray(value.skills)||value.skills.length>2)return null;
 const skills=[];for(const s of value.skills){
  if(!s||!MAGE_PILOT_IDS.includes(s.skill_id)||skills.some(p=>p.skill_id===s.skill_id)||typeof s.available!=='boolean'||!finite(s.range_m,.1,40)||!uint(s.windup_ms,1,5000)||!uint(s.cooldown_ms,1,60000)||!uint(s.recovery_ms,0,5000)||!uint(s.sp_cost,0,1000)||!finite(s.projectile_speed_m_s,1,100)||!uint(s.power,1,65535))return null;
  skills.push(Object.freeze({skill_id:s.skill_id,available:s.available,range_m:s.range_m,windup_ms:s.windup_ms,cooldown_ms:s.cooldown_ms,recovery_ms:s.recovery_ms,sp_cost:s.sp_cost,projectile_speed_m_s:s.projectile_speed_m_s,power:s.power}));
 }
 return Object.freeze({capability_enabled:value.capability_enabled,focus_equipped:value.focus_equipped,profile:value.profile,epoch:value.epoch,skills:Object.freeze(skills)});
}
export function parseMageCastState(value){
 if(!value||value.t!=='mage_cast_state'||!uint(value.source_id,1)||!uint(value.epoch)||!uint(value.sequence,1)||!MAGE_PILOT_IDS.includes(value.skill_id)||!phases.has(value.phase)||typeof value.reason!=='string'||value.reason.length>96||!uint(value.target_id,1)||!point(value.origin)||!point(value.target)||!uint(value.damage,0,65535)||!uint(value.flags,0,255))return null;
 if(value.cast_id!==`${value.source_id}:${value.epoch}:${value.sequence}`)return null;
 const times=['server_ms','start_ms','release_ms','recovery_end_ms','cooldown_end_ms'];if(!times.every(k=>Number.isSafeInteger(value[k])&&value[k]>=0))return null;
 if(value.impact_ms!==null&&(!Number.isSafeInteger(value.impact_ms)||value.impact_ms<0))return null;
 if(['released','impact'].includes(value.phase)&&value.impact_ms===null)return null;
 if(value.phase!=='rejected'&&(value.release_ms<value.start_ms||(value.impact_ms!==null&&(value.impact_ms<value.release_ms||value.impact_ms-value.start_ms>10000))||value.recovery_end_ms<value.release_ms||value.cooldown_end_ms<value.start_ms))return null;
 if(value.phase!=='impact'&&value.damage!==0)return null;
 return Object.freeze(Object.fromEntries(['cast_id','source_id','epoch','sequence','skill_id','phase','reason','target_id','damage','flags','impact_ms',...times].map(k=>[k,value[k]]).concat([['origin',Object.freeze([...value.origin])],['target',Object.freeze([...value.target])]])));
}
export class MagePilotClient {
 constructor(now){this.now=now;this.connect(0,0);}
 connect(playerId,epoch){this.playerId=playerId;this.epoch=epoch;this.sequence=0;this.profile=null;this.pending=null;this.cooldowns=new Map();this.busyUntil=0;this.lastEvent=null;}
 setProfile(raw){const next=parseMageTrialState(raw);if(!next||next.epoch!==this.epoch)return false;this.profile=next;return true;}
 request(skillId,targetId,sp){
  const s=this.profile?.skills.find(s=>s.skill_id===skillId),now=this.now();
  if(!this.playerId||!this.profile?.capability_enabled||this.profile.profile!=='mage_trial'||!this.profile.focus_equipped||!s?.available)return{ok:false,reason:'not_allowed'};
  if(this.pending||now<this.busyUntil)return{ok:false,reason:'busy'};
  if(now<(this.cooldowns.get(skillId)??0))return{ok:false,reason:'cooldown'};
  if(!finite(sp,0,0xffffffff)||sp<s.sp_cost)return{ok:false,reason:'insufficient_sp'};
  if(!uint(targetId,1))return{ok:false,reason:'no_target'};
  if(this.sequence===0xffffffff)return{ok:false,reason:'sequence_exhausted'};
  const sequence=++this.sequence,intent=Object.freeze({t:'mage_cast',epoch:this.epoch,sequence,skill_id:skillId,target_id:targetId});
  this.pending={intent,phase:-1,retries:0,nextRetryAt:now+recoveryIntervalMs,reconnectAt:now+unknownWindowMs,reconnectIssued:false,rangeFlightMs:Math.min(10000,Math.ceil(s.range_m/s.projectile_speed_m_s*1000))};return{ok:true,intent};
 }
 notSent(sequence){if(this.pending?.intent.sequence===sequence)this.pending=null;}
 pollRecovery(){
  const pending=this.pending,now=this.now();
  if(!pending||pending.reconnectIssued||!Number.isFinite(now)||now<0)return null;
  if(now>=pending.reconnectAt){pending.reconnectIssued=true;return Object.freeze({kind:'reconnect'});}
  if(pending.retries>=maxRetries||now<pending.nextRetryAt)return null;
  pending.retries++;
  // A resumed/backgrounded frame must not burst several overdue retries into one server tick.
  pending.nextRetryAt=now+recoveryIntervalMs;
  return Object.freeze({kind:'retry',intent:pending.intent});
 }
 receive(raw){
  const message=parseMageCastState(raw),pending=this.pending;
  if(!message||message.source_id!==this.playerId||message.epoch!==this.epoch||!pending||message.sequence!==pending.intent.sequence||message.skill_id!==pending.intent.skill_id||message.target_id!==pending.intent.target_id)return null;
  const rank={started:0,released:1,impact:2,cancelled:2,rejected:2}[message.phase];if(rank<=pending.phase)return null;pending.phase=rank;
  if(message.phase!=='rejected'){
   if(validCooldown(message))this.cooldowns.set(message.skill_id,message.cooldown_end_ms);
   if(validRecovery(message))this.busyUntil=message.recovery_end_ms;
  }else if(message.reason==='cooldown'&&validCooldown(message)){
   this.cooldowns.set(message.skill_id,message.cooldown_end_ms);
   // Rust rejection recovery describes the attempted cast, not an accepted action.
   // Keep the prior accepted recovery; never install a hypothetical busy deadline.
  }
  if(rank<2){
   const now=this.now();
   if(Number.isFinite(now)&&now>=0){
    // This predicts only when to ask for transport recovery, never a hit or a visual phase.
    const terminalAt=Math.max(message.release_ms,message.impact_ms??message.release_ms+pending.rangeFlightMs,validRecovery(message)?message.recovery_end_ms:message.release_ms);
    const base=now+Math.min(10000,Math.max(0,terminalAt-now));
    pending.nextRetryAt=base+recoveryIntervalMs;pending.reconnectAt=base+unknownWindowMs;
   }
  }
  if(rank===2)this.pending=null;this.lastEvent=message;return message;
 }
}
