import test from "node:test";
import assert from "node:assert/strict";
import {createReconnectScheduler} from "./reconnect-scheduler.mjs";
function fakeTimers() {
	let id = 0; const pending = new Map();
	return {pending,setTimeout(fn,ms){pending.set(++id,{fn,ms});return id;},clearTimeout(id){pending.delete(id);},fire(){const [key,item]=pending.entries().next().value;pending.delete(key);item.fn();return item.ms;}};
}
test("ticket failures actually retry once per backoff and welcome resets the delay", () => {
	const timers=fakeTimers(); let attempts=0;
	const scheduler=createReconnectScheduler(()=>{attempts++;scheduler.schedule();},()=>true,timers);
	scheduler.schedule();scheduler.schedule();assert.equal(timers.pending.size,1);
	assert.equal(timers.fire(),500);assert.equal(attempts,1);
	assert.equal(timers.fire(),1000);assert.equal(timers.fire(),2000);assert.equal(timers.fire(),4000);assert.equal(timers.fire(),5000);assert.equal(timers.fire(),5000);
	scheduler.reset();assert.equal(timers.pending.size,0);
	scheduler.schedule();assert.equal(timers.fire(),500);scheduler.dispose();assert.equal(timers.pending.size,0);
});
test("blocked or disposed sessions cannot retry or leave a live timer", () => {
	const timers=fakeTimers();let allowed=true,attempts=0;
	const scheduler=createReconnectScheduler(()=>attempts++,()=>allowed,timers);
	scheduler.schedule();allowed=false;timers.fire();assert.equal(attempts,0);
	scheduler.schedule();assert.equal(timers.pending.size,0);
	allowed=true;scheduler.schedule();scheduler.dispose();scheduler.schedule();assert.equal(timers.pending.size,0);
});
