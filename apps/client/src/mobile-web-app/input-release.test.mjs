import test from 'node:test';
import assert from 'node:assert/strict';
import { createHeldInputLedger } from './policy.mjs';
import { releaseHeldInputs } from './input-release.mjs';
const event = (type, props) => Object.assign(new Event(type), props);
const adapter = { keyUp: record => event('keyup',{code:record.code}), pointerCancel: record => event('pointercancel',{pointerId:record.pointerId}) };
test('releases reset original joystick arrow state and actual pointer capture owner', () => {
	const ledger = createHeldInputLedger(), original = new EventTarget(), captured = new EventTarget();
	const keys = new Set(['ArrowUp']), order = []; let holding = true;
	original.addEventListener('keyup', release => { assert.equal(release.target,original); keys.delete(release.code); order.push('key'); });
	captured.addEventListener('pointercancel', release => { assert.equal(release.target,captured); assert.equal(release.pointerId,7); order.push('cancel'); });
	captured.hasPointerCapture = id => id===7&&holding; captured.releasePointerCapture = id => { assert.equal(id,7); holding=false; order.push('capture'); };
	ledger.keyDown({target:original,code:'ArrowUp',key:'ArrowUp',location:0,ctrlKey:false,altKey:false,shiftKey:false,metaKey:false});
	ledger.pointerDown({target:original,pointerId:7,pointerType:'touch',isPrimary:true,clientX:1,clientY:2}); ledger.pointerCapture(7,captured);
	assert.deepEqual(releaseHeldInputs(ledger,adapter),{keys:1,pointers:1,failures:0}); assert.equal(keys.size,0); assert.equal(holding,false); assert.deepEqual(order,['key','cancel','capture']);
});
test('a target that already released capture during cancellation is not released twice', () => {
	const ledger=createHeldInputLedger(), target=new EventTarget(); let holding=true, released=0;
	target.addEventListener('pointercancel',()=>{holding=false;}); target.hasPointerCapture=()=>holding; target.releasePointerCapture=()=>released++;
	ledger.pointerDown({target,pointerId:4,pointerType:'mouse',isPrimary:true,clientX:0,clientY:0}); releaseHeldInputs(ledger,adapter); assert.equal(released,0);
});
test('one failing release does not strand other keys or pointers', () => {
	const ledger=createHeldInputLedger(), target=new EventTarget(); let cancelled=0;
	target.addEventListener('pointercancel',()=>cancelled++);
	ledger.keyDown({target,code:'KeyW',key:'w',location:0,ctrlKey:false,altKey:false,shiftKey:false,metaKey:false});
	ledger.pointerDown({target,pointerId:4,pointerType:'touch',isPrimary:true,clientX:0,clientY:0});
	const result=releaseHeldInputs(ledger,{...adapter,keyUp(){throw new Error('Unavailable key adapter');}}); assert.equal(result.failures,1); assert.equal(cancelled,1); assert.equal(ledger.size().keys,0);
});
