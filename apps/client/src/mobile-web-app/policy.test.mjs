import test from 'node:test';
import assert from 'node:assert/strict';
import { mobileWebAppPolicy, createHeldInputLedger, keepGuideEntry } from './policy.mjs';

test('portrait and square viewports block every input type and desktop size', () => {
	for (const input of [{ width:390,height:844 }, { width:1200,height:1500,coarse:false,maxTouchPoints:0 }, { width:900,height:900 }, { width:0,height:0 }]) {
		const state = mobileWebAppPolicy(input); assert.equal(state.portrait,true); assert.equal(state.blocked,true);
	}
	assert.equal(mobileWebAppPolicy({width:1200,height:800,coarse:false,maxTouchPoints:0}).blocked,false);
});
test('keyboard-shortened portrait phones remain blocked by physical orientation', () => {
	assert.equal(mobileWebAppPolicy({width:390,height:300,coarse:true,orientationType:'portrait-primary'}).blocked,true);
	assert.equal(mobileWebAppPolicy({width:390,height:250,maxTouchPoints:5,legacyAngle:0}).blocked,true);
	assert.equal(mobileWebAppPolicy({width:390,height:250,maxTouchPoints:5,legacyAngle:180}).blocked,true);
	assert.equal(mobileWebAppPolicy({width:844,height:390,coarse:true,orientationType:'landscape-primary',legacyAngle:90}).blocked,false);
	assert.equal(mobileWebAppPolicy({width:1024,height:768,maxTouchPoints:5,coarse:true,orientationType:'landscape-primary',legacyAngle:0}).blocked,false);
	assert.equal(mobileWebAppPolicy({width:1400,height:800,coarse:false,maxTouchPoints:0,orientationType:'portrait-primary',legacyAngle:0}).blocked,false);
});
test('manual guide blocks landscape and closing it cannot unblock portrait', () => {
	assert.equal(mobileWebAppPolicy({width:844,height:390,guideOpen:true}).blocked,true);
	assert.equal(mobileWebAppPolicy({width:844,height:390,guideOpen:false}).blocked,false);
	assert.equal(mobileWebAppPolicy({width:390,height:844,guideOpen:false}).blocked,true);
});
test('standalone detects either display mode or Safari navigator state', () => {
	assert.equal(mobileWebAppPolicy({width:844,height:390,displayStandalone:true}).standalone,true);
	assert.equal(mobileWebAppPolicy({width:844,height:390,navigatorStandalone:true}).standalone,true);
	assert.equal(mobileWebAppPolicy({width:844,height:390}).standalone,false);
});
test('a reused modal container cannot retain the Settings install entry after a panel switch', () => {
	assert.equal(keepGuideEntry('settings',true,true),true);
	assert.equal(keepGuideEntry('settings',true,false),false); // Same connected .modal-content, but Settings input disappeared.
	assert.equal(keepGuideEntry('login',true,true),true);
	assert.equal(keepGuideEntry('settings',false,true),false);
});
const key = (code,target) => ({code,key:code,location:0,ctrlKey:false,altKey:false,shiftKey:false,metaKey:false,target});
test('held keyboard releases retain each original element, not only window', () => {
	const ledger = createHeldInputLedger(), joystick = new EventTarget(), canvas = new EventTarget();
	ledger.keyDown(key('ArrowUp',joystick)); ledger.keyDown(key('KeyW',canvas));
	ledger.keyDown(key('ArrowUp',canvas)); // Repeats must not replace the original joystick target.
	const released = ledger.drain(); assert.equal(released.keys.length,2); assert.equal(released.keys[0].target,joystick); assert.equal(released.keys[1].target,canvas);
	assert.equal(ledger.size().keys,0); assert.equal(ledger.isKeyQuarantined('ArrowUp'),true);
	ledger.keyUp('ArrowUp',true); assert.equal(ledger.isKeyQuarantined('ArrowUp'),true); // Own cancellation is not a physical release.
	ledger.keyDown(key('ArrowUp',joystick)); assert.equal(ledger.size().keys,0);
	ledger.keyUp('ArrowUp'); ledger.keyDown(key('ArrowUp',joystick)); assert.equal(ledger.size().keys,1);
});
test('pointer cancellation uses the actual capture owner, with bounded held state', () => {
	const ledger = createHeldInputLedger(), child = new EventTarget(), joystick = new EventTarget();
	ledger.pointerDown({target:child,pointerId:7,pointerType:'touch',isPrimary:true,clientX:10,clientY:20});
	ledger.pointerCapture(7,joystick); const released = ledger.drain(); assert.equal(released.pointers[0].target,joystick); assert.equal(released.pointers[0].pointerId,7);
	ledger.pointerEnd(7); assert.equal(ledger.size().pointers,0);
	for(let pointerId=0;pointerId<100;pointerId++) ledger.pointerDown({target:child,pointerId,pointerType:'touch',isPrimary:false,clientX:0,clientY:0});
	assert.equal(ledger.size().pointers,32); ledger.clear(); assert.deepEqual(ledger.size(),{keys:0,pointers:0,quarantined:0});
});
test('unrecognised/editor text keys are never manufactured into gameplay releases', () => {
	const ledger = createHeldInputLedger(); ledger.keyDown(key('KeyZ',new EventTarget())); assert.equal(ledger.drain().keys.length,0);
});
