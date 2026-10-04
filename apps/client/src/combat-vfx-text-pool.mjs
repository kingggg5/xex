export const TEXT_TYPES = Object.freeze({ normal: 0, crit: 1, hurt: 2, word: 3, heal: 4, exp: 5, counter: 6, tick: 7 });
export const TEXT_LIFE_MS = Object.freeze([900,1200,1000,800,1100,1400,1100,450]);
export function compactCombatAmount(value) {
	const n = Math.min(4_294_967_295, Math.max(0, Math.round(value)));
	return n >= 10_000_000 ? `${Math.round(n / 1_000_000)}M` : n >= 100_000 ? `${Math.round(n / 1000)}K` : String(n);
}
/** Fixed storage: matching, expiry and overload decisions never allocate render resources. */
export function createCombatTextPool(mobile = false) {
	const slots = Array.from({length:48},(_,index)=>({index,active:false,target:'',source:'',relation:'mine',type:0,amount:0,text:'',x:0,y:0,z:0,born:0,lastHit:0,expires:0,lane:0,side:1,dirty:false}));
	let sequence=0;
	const cap=()=>mobile?20:32;
	const priority=s=>s.relation==='other'?0:s.type===5?1:s.relation==='party'?2:s.type===0?3:s.type===1||s.type===6?4:5;
	function expire(now){for(const s of slots)if(s.active&&now>=s.expires){s.active=false;s.dirty=true;}}
	return {slots, get cap(){return cap();},setMobile(value){mobile=!!value;const live=slots.filter(s=>s.active).sort((a,b)=>priority(a)-priority(b)||a.born-b.born);while(live.length>cap()){const s=live.shift();s.active=false;s.dirty=true;}},expire,
		spawn(event,now){
			expire(now);
			if(![event.x,event.y,event.z,now,event.amount??0].every(Number.isFinite)||!Number.isInteger(event.type)||event.type<0||event.type>7)return null;
			const target=String(event.targetId??`${event.x.toFixed(3)},${event.z.toFixed(3)}`),source=String(event.sourceId??'local');
			const relation=event.relation??'mine';
			const same=slots.find(s=>s.active&&s.target===target&&s.source===source&&s.type===event.type&&now-s.lastHit<=120&&event.amount>0&&s.amount>0);
			if(same){same.amount=Math.min(4_294_967_295,same.amount+event.amount);same.text=compactCombatAmount(same.amount);same.lastHit=now;same.expires=Math.max(same.expires,now+TEXT_LIFE_MS[same.type]*.6);same.dirty=true;return same;}
			const live=slots.filter(s=>s.active),targetLive=live.filter(s=>s.target===target),targetCap=event.type===2?6:4;
			let reuse;
			if(targetLive.length>=targetCap)reuse=targetLive.filter(s=>s.type!==2).sort((a,b)=>priority(a)-priority(b)||a.born-b.born)[0];
			if(!reuse&&live.length>=cap())reuse=live.filter(s=>s.type!==2).sort((a,b)=>priority(a)-priority(b)||a.born-b.born)[0];
			if((targetLive.length>=targetCap||live.length>=cap())&&!reuse)return null;
			const slot=reuse??slots.find(s=>!s.active);if(!slot)return null;
			Object.assign(slot,{active:true,target,source,relation,type:event.type,amount:event.amount??0,text:event.text??compactCombatAmount(event.amount??0),x:event.x,y:event.y,z:event.z,born:now,lastHit:now,expires:now+TEXT_LIFE_MS[event.type],lane:sequence%3-1,side:sequence++%2?1:-1,dirty:true});
			return slot;
		},clear(){for(const s of slots){s.active=false;s.dirty=true;}},active(){return slots.filter(s=>s.active);}
	};
}
