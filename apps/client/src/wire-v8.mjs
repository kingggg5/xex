import {decodeServerMessage, PROTOCOL_VERSION, dequantizeFacing} from './wire.mjs';
import {ACTION_NAMES} from './combat-actions.mjs';

export const V8_BASELINE_LIMIT = 32;
export const V8_VISIBLE_LIMIT = 64;
export class ResyncRequired extends Error {
	constructor(reason) { super(`snapshot resync required: ${reason}`); this.name='ResyncRequired'; this.reason=reason; }
}

/** A decoder belongs to exactly one socket. Baselines hold peers only; current
 * private self data is merged into each returned full visible list. */
export function createSnapshotDecoder() {
	let epoch=0, ownId=0, lastTick=0n;
	const baselines=new Map();
	const reset=()=>{epoch=0;ownId=0;lastTick=0n;baselines.clear();};
	function decode(data,zoneLimit=28) {
		if (!(data instanceof ArrayBuffer)) throw new TypeError('binary WebSocket message must be an ArrayBuffer');
		const v=new DataView(data);
		if(data.byteLength<6||v.getUint8(3)!==0x86) {
			const result=decodeServerMessage(data,zoneLimit);
			if(result.type==='welcome'){reset();epoch=result.epoch;ownId=result.player_id;}
			return result;
		}
		if(data.byteLength>16384||v.getUint16(0,true)!==0xa731||v.getUint8(2)!==PROTOCOL_VERSION||v.getUint16(4,true)+6!==data.byteLength)throw new TypeError('interest snapshot envelope is invalid');
		let offset=6;
		const need=n=>{if(offset+n>data.byteLength)throw new RangeError('interest snapshot is truncated');};
		const u8=()=>{need(1);return v.getUint8(offset++);};
		const i8=()=>{need(1);return v.getInt8(offset++);};
		const u16=()=>{need(2);const x=v.getUint16(offset,true);offset+=2;return x;};
		const u32=()=>{need(4);const x=v.getUint32(offset,true);offset+=4;return x;};
		const u64=()=>{need(8);const x=v.getBigUint64(offset,true);offset+=8;return x;};
		const f32=(bounded=true)=>{need(4);const x=v.getFloat32(offset,true);offset+=4;if(!Number.isFinite(x)||Math.abs(x)>(bounded?Math.min(zoneLimit,4096):4096))throw new TypeError('interest coordinate is invalid');return x;};
		const streamEpoch=u32(),tick=u64(),baselineTick=u64(),ackSeq=u32(),ownFlags=u8(),ackX=f32(),ackZ=f32();
		if(!epoch||streamEpoch!==epoch)throw new ResyncRequired('wrong_epoch');
		if(tick<=lastTick)throw new ResyncRequired('stale_tick');
		if(baselineTick>=tick)throw new ResyncRequired('future_baseline');
		const self={id:u32(),x:f32(),z:f32(),facing:dequantizeFacing(u16()),hp:u16(),max_hp:u16(),flags:u8(),anim:u8(),y:f32(false)};
		if(self.id!==ownId||self.hp>self.max_hp||(self.flags&~15)!==0)throw new TypeError('private self record is invalid');
		self.connected=(self.flags&1)!==0;
		const targetCount=u8();if(targetCount>64)throw new TypeError('target overlay count exceeds limit');
		const targeting=new Set();for(let i=0;i<targetCount;i++){const id=u32();if(id===0||targeting.has(id))throw new TypeError('target overlay identity is invalid');targeting.add(id);}
		const old=baselineTick===0n?null:baselines.get(baselineTick);
		if(baselineTick!==0n&&!old)throw new ResyncRequired('missing_baseline');
		const next={players:new Map(old?.players),monsters:new Map(old?.monsters),pets:new Map(old?.pets)};
		for(const [name,fullMask] of [['players',63],['monsters',127],['pets',7]]) {
			const changed=u8(),removed=u8();if(changed>64||removed>64||(baselineTick===0n&&removed!==0))throw new TypeError('interest counts exceed limit');
			const seen=new Set();
			for(let i=0;i<changed;i++) {
				const id=u32(),mask=u8(),prior=next[name].get(id);
				if(id===0||id===ownId&&name==='players'||seen.has(id)||(mask&fullMask)===0||(mask&~(fullMask|128))!==0||(mask&128)!==0&&((mask&1)===0||!prior))throw new TypeError('interest patch is invalid');
				if(!prior&&(mask&fullMask)!==fullMask)throw new ResyncRequired('unknown_patch');
				seen.add(id);const r={...prior,id};
				if(mask&1){if(mask&128){r.x=Math.fround(prior.x+i8()/128);r.z=Math.fround(prior.z+i8()/128);if(Math.abs(r.x)>Math.min(zoneLimit,4096)||Math.abs(r.z)>Math.min(zoneLimit,4096))throw new TypeError('relative coordinate is invalid');}else{r.x=f32();r.z=f32();}}
				if(name==='pets') {if(mask&2)r.kind=u8();if(mask&4)r.flags=u8();if(!r.kind||(r.flags&~1)!==0)throw new TypeError('pet record is invalid');r.owner_id=id;}
				else {
					if(mask&2)r.facing=dequantizeFacing(u16());
					if(mask&4){r.hp=name==='players'?u16():u32();r.max_hp=name==='players'?u16():u32();}
					if(mask&8)r.flags=u8();
					if(name==='players'){if(mask&16)r.anim=u8();if(mask&32)r.y=f32(false);r.connected=(r.flags&1)!==0;if((r.flags&~15)!==0)throw new TypeError('player flags are invalid');}
					else {if(mask&16){r.state=u8();r.ability=u8();r.state_ends_tick=u64();}if(mask&32){r.target_x=f32();r.target_z=f32();}if(mask&64)r.kind=u8();r.active=(r.flags&1)!==0;if(!r.kind||(r.flags&~3)!==0||r.state_ends_tick>tick+65535n)throw new TypeError('shared monster flags or deadline are invalid');}
					if(r.hp>r.max_hp||r.max_hp===0)throw new TypeError('interest health is invalid');
				}
				next[name].set(id,r);
			}
			for(let i=0;i<removed;i++){const id=u32();if(seen.has(id)||!next[name].delete(id))throw new ResyncRequired('unknown_remove');seen.add(id);}
			if(next[name].size>(name==='players'?63:64))throw new TypeError('reconstructed interest exceeds limit');
		}
		if(next.pets.size!==0)throw new TypeError('reserved pet collection must be empty');
		for(const id of targeting)if(!next.monsters.has(id))throw new ResyncRequired('unknown_target_overlay');
		const eventCount=u8();if(eventCount>64)throw new TypeError('event count exceeds limit');
		const events=[],eventIds=new Set();
		for(let i=0;i<eventCount;i++){
			const id=u64(),source_kind=u8(),source_id=u32(),target_kind=u8(),target_id=u32(),action=ACTION_NAMES.get(u8()),amount=u16(),flags=u8(),world_x=f32(),world_z=f32();
			if(id===0n||eventIds.has(id)||source_kind>1||target_kind>1||!source_id||!target_id||!action||(flags&~127)!==0||((flags&64)!==0&&(amount!==0||(flags&33)!==0))||((flags&32)!==0&&amount===0))throw new TypeError('interest event is invalid');
			eventIds.add(id);events.push({id,source_kind,source_id,target_kind,target_id,action,amount,flags,world_x,world_z});
		}
		if(offset!==data.byteLength)throw new RangeError('interest snapshot has trailing bytes');
		// Commit only after every field/operation validates. Returned objects cannot
		// mutate the retained baseline; overlays live exclusively in the result.
		baselines.set(tick,next);while(baselines.size>V8_BASELINE_LIMIT)baselines.delete(baselines.keys().next().value);lastTick=tick;
		const players=[self,...Array.from(next.players.values(),r=>({...r}))];
		const monsters=Array.from(next.monsters.values(),r=>({...r,state_ticks:Number(r.state_ends_tick>tick?r.state_ends_tick-tick:0n),flags:r.flags|(targeting.has(r.id)?6:0)}));
		return {type:'snapshot',epoch,tick,baseline_tick:baselineTick,full:baselineTick===0n,ack_seq:ackSeq,own_flags:ownFlags,ack_x:ackX,ack_z:ackZ,players,monsters,events};
	}
	return {decode,reset,snapshotAck:()=>epoch&&lastTick?{epoch,tick:lastTick}:null,retainedBaselines:()=>baselines.size};
}

export function encodeSnapshotAck(epoch,tick,resync=false) {
	if(!Number.isInteger(epoch)||epoch<=0||epoch>0xffffffff||typeof tick!=='bigint'||tick<0n||tick>0xffffffffffffffffn||tick===0n&&!resync||typeof resync!=='boolean')throw new RangeError('snapshot acknowledgement is invalid');
	const b=new ArrayBuffer(19),v=new DataView(b);v.setUint16(0,0xa731,true);v.setUint8(2,PROTOCOL_VERSION);v.setUint8(3,5);v.setUint16(4,13,true);v.setUint32(6,epoch,true);v.setBigUint64(10,tick,true);v.setUint8(18,resync?1:0);return b;
}
