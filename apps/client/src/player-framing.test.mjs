import {test} from 'node:test';import assert from 'node:assert/strict';
import {playerFraming} from './player-framing.mjs';
test('balanced presentation enlarges the avatar projection while retaining orbit distance and ground pivot',()=>{
 const a=playerFraming('?heroFraming=legacy',false,true),b=playerFraming();
 const height=p=>p.avatarScale*Math.sin(p.beta)/(p.radius*Math.tan(p.fov/2));
 assert.ok(height(b)/height(a)>1.5&&height(b)/height(a)<1.8);
 assert.ok(b.radius>=8.5&&b.radius<=24);assert.ok(b.beta<b.upperBeta);
 assert.ok(b.targetHeight<2*b.avatarScale);assert.equal(b.lookAhead,a.lookAhead);
});
test('legacy comparison is DEV-only, and portrait keeps a usable vertical field',()=>{
 assert.deepEqual(playerFraming('?heroFraming=legacy',false,false),playerFraming());
 assert.ok(playerFraming('',true).fov>playerFraming().fov);
 assert.ok(Object.isFrozen(playerFraming()));
});
