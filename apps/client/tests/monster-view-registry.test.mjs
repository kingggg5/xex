import test from 'node:test';
import assert from 'node:assert/strict';
import {createMonsterViewRegistry} from '../src/monster-view-registry.mjs';
function fixture(){
	const live=new Map(),retired=[];let created=0;
	const registry=createMonsterViewRegistry({create:s=>{const v={id:s.id,kind:s.kind,serial:++created};live.set(s.id,v);return v;},update:(v,s)=>Object.assign(v,s),dispose:(v,id)=>{retired.push(v);live.delete(id);}});
	return {registry,live,retired,created:()=>created};
}
test('40 tower IDs beyond the old 32-row atlas are created by snapshot identity',()=>{
	const f=fixture(),rows=Array.from({length:40},(_,i)=>({id:2000+i,kind:i%3+1,active:true,hp:90}));
	f.registry.synchronize(rows);assert.equal(f.registry.size(),40);
	f.registry.synchronize(rows.map(s=>({...s,hp:40})));assert.equal(f.created(),40);
	assert.equal(f.registry.get(2039).hp,40);
});
test('floor change disposes absent actors and replaces a reused ID when its species changes',()=>{
	const f=fixture();f.registry.synchronize([{id:101,kind:1},{id:102,kind:1}]);const old=f.registry.get(101);
	f.registry.synchronize([{id:101,kind:2},{id:999,kind:3}]);assert.equal(f.registry.size(),2);
	assert.notEqual(f.registry.get(101),old);assert.equal(f.registry.get(101).kind,2);assert.equal(f.retired.length,2);
	f.registry.dispose();f.registry.dispose();assert.equal(f.registry.size(),0);assert.equal(f.live.size,0);assert.equal(f.retired.length,4);
});
test('invalid snapshot is refused atomically before despawning the current floor',()=>{
	const f=fixture();f.registry.synchronize([{id:101,kind:1}]);
	for(const bad of [[{id:2,kind:1},{id:2,kind:3}],Array.from({length:65},(_,i)=>({id:i+1,kind:1})),[{id:0,kind:1}]])assert.throws(()=>f.registry.synchronize(bad));
	assert.equal(f.registry.size(),1);assert.equal(f.created(),1);assert.equal(f.retired.length,0);
});
