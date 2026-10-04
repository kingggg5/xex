/** Transaction revision fences durable fields; live HP/SP use the current ordered socket stream. */
export function characterSnapshotDecision(previous,next){
 if(!next||!Number.isSafeInteger(next.rev)||next.rev<1)return'invalid';
 if(!previous||previous.character_id!==next.character_id)return'advance';
 if(next.rev<previous.rev)return'stale';if(next.rev>previous.rev)return'advance';
 // Character DTOs come from one deterministic server serializer. Only resource balances may
 // change without the transaction revision; inventory/stats/EXP/equipment must never do so.
 const stable=value=>JSON.stringify({...value,hp:undefined,sp:undefined});
 try{if(stable(previous)!==stable(next))return'conflict';}catch{return'invalid';}
 return next.hp===previous.hp&&next.sp===previous.sp?'duplicate':'resources';
}
