const u32=value=>Number.isSafeInteger(value)&&value>=0&&value<=0xffff_ffff;
const record=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
export function parseDeathNotice(value){
	if(!record(value)||!u32(value.revision)||typeof value.down!=='boolean'||!['monster','none'].includes(value.cause)||!record(value.penalty)||!record(value.costs)||!['base_exp','job_exp','gold'].every(key=>u32(value.penalty[key]))||!u32(value.costs.return_to_town)||typeof value.free_return!=='boolean'||value.auto_revive_at_ms!==null&&!u32(value.auto_revive_at_ms))return null;
	return {revision:value.revision,down:value.down,cause:value.cause,penalty:{base_exp:value.penalty.base_exp,job_exp:value.penalty.job_exp,gold:value.penalty.gold},costs:{return_to_town:value.costs.return_to_town},free_return:value.free_return,auto_revive_at_ms:value.auto_revive_at_ms};
}
export function parseCombatGain(kind,value){
	if(!record(value))return null;
	if(kind==='heal'&&u32(value.amount)&&u32(value.hp)&&u32(value.max_hp)&&value.hp<=value.max_hp&&value.source==='trail_potion')return {kind,amount:value.amount,hp:value.hp,max_hp:value.max_hp};
	if(kind==='exp_gain'&&u32(value.base)&&u32(value.job)&&u32(value.monster_id)&&u32(value.kind)&&Number.isFinite(value.x)&&Number.isFinite(value.z)&&Math.abs(value.x)<=4096&&Math.abs(value.z)<=4096&&typeof value.level_up==='boolean'&&typeof value.job_level_up==='boolean')return {kind,base:value.base,job:value.job,monster_id:value.monster_id,x:value.x,z:value.z};
	return null;
}
