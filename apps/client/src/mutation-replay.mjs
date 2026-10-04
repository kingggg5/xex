const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
/** Uncertain mutations belong to a character, never merely to a WebSocket or a refreshed cookie. */
export function createMutationReplayLedger(maximum=128){
	if(!Number.isInteger(maximum)||maximum<1||maximum>128)throw new RangeError('invalid replay cap');
	let authority=null,awaiting=true;const entries=new Map();
	return {
		get ready(){return !awaiting&&authority!==null;},
		beginReconnect(){awaiting=true;},
		bind(characterId){
			if(!uuid(characterId))throw new TypeError('invalid character authority');
			characterId=characterId.toLowerCase();
			const changed=authority!==null&&authority!==characterId,discarded=[],replay=[];
			for(const [opId,entry]of entries){
				if(entry.characterId!==characterId){discarded.push({opId,resource:entry.resource});entries.delete(opId);}
				else if(awaiting)replay.push({opId,resource:entry.resource,packet:entry.packet.slice(0)});
			}
			authority=characterId;awaiting=false;return {changed,discarded,replay};
		},
		register(opId,packet,resource){
			if(awaiting||!authority||!uuid(opId)||!(packet instanceof ArrayBuffer)||packet.byteLength>518)return false;
			const previous=entries.get(opId);
			if(previous){const a=new Uint8Array(previous.packet),b=new Uint8Array(packet);return previous.resource===resource&&a.length===b.length&&a.every((v,i)=>v===b[i]);}
			if(entries.size>=maximum)return false;
			entries.set(opId,{packet:packet.slice(0),resource,characterId:authority});return true;
		},
		settle(opId){const row=entries.get(opId);entries.delete(opId);return row?{resource:row.resource}:undefined;},
		pending(){return [...entries].map(([opId,row])=>({opId,resource:row.resource}));},
		clear(){entries.clear();authority=null;awaiting=true;},
	};
}
