import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createSnapshotDelivery} from '../src/snapshot-delivery.mjs';

const native = JSON.parse(readFileSync(new URL('../../protocol/golden-v8.json', import.meta.url), 'utf8')).fixtures;
const fixture = name => Uint8Array.from(Buffer.from(native.find(row => row.name === name).hex, 'hex')).buffer;
function setup(extra = {}) {
	const state = {current:true, time:0, applied:[], sent:[], failures:[], resyncs:[], changes:[], closes:0};
	const delivery = createSnapshotDelivery({
		zoneLimit:308, now:() => state.time, isCurrent:() => state.current,
		applyMessage:message => state.applied.push(message), sendPacket:packet => state.sent.push(packet),
		close:() => {state.closes++;}, onReadyChange:ready => state.changes.push(ready),
		onResync:reason => state.resyncs.push(reason),
		onError:(stage, error, messageType) => state.failures.push({stage, error, messageType}),
		...extra,
	});
	return {state, delivery, receive:name => delivery.receive(fixture(name))};
}
const acks = state => state.sent.map(packet => {
	const view = new DataView(packet);
	assert.equal(view.getUint8(3), 5);
	return {epoch:view.getUint32(6,true), tick:view.getBigUint64(10,true), resync:view.getUint8(18)};
});
test('native welcome/full/delta apply complete truth before exactly one ACK per snapshot', () => {
	const h = setup({sendPacket:packet => {
		assert.equal(h.state.applied.at(-1).type, 'snapshot');
		h.state.sent.push(packet);
	}});
	h.receive('interest_welcome');
	assert.equal(h.delivery.ready, false);
	assert.equal(h.state.sent.length, 0);
	h.receive('interest_full');
	assert.equal(h.delivery.ready, true);
	assert.equal(h.state.applied.at(-1).players.length, 2);
	h.receive('interest_delta');
	assert.equal(h.state.applied.at(-1).players[0].x, 1.75);
	assert.deepEqual(acks(h.state), [{epoch:1,tick:42n,resync:0},{epoch:1,tick:43n,resync:0}]);
	assert.deepEqual(h.state.changes, [true]);
});
test('missing baseline holds visible state, limits resync requests to one per second, and Pong cannot recover', () => {
	const h = setup(); h.receive('interest_welcome');
	const before = h.state.applied.slice();
	assert.equal(h.receive('interest_delta'), 'resync');
	h.state.time = 999; h.receive('interest_delta');
	assert.deepEqual(h.state.applied, before);
	assert.deepEqual(acks(h.state), [{epoch:1,tick:0n,resync:1}]);
	h.receive('pong_basic');
	assert.equal(h.delivery.ready, false);
	assert.deepEqual(h.state.changes, []);
	h.state.time = 1000; h.receive('interest_delta');
	assert.equal(h.state.sent.length, 2);
	h.receive('interest_full');
	assert.equal(h.delivery.ready, true);
	h.receive('interest_delta');
	assert.equal(h.state.applied.at(-1).players[1].x, 2.125);
});
test('while recovering a valid delta cannot replace the last accepted visible world', () => {
	const h = setup(); h.receive('interest_welcome'); h.receive('interest_full');
	const visible = h.state.applied.at(-1);
	// Replayed stale delivery asks for a full refresh, but never ACKs it again.
	h.receive('interest_full');
	assert.equal(h.delivery.ready, false);
	h.receive('interest_delta');
	assert.equal(h.state.applied.at(-1), visible);
	h.receive('pong_basic'); assert.equal(h.delivery.ready, false);
	const recovery = fixture('interest_full'); new DataView(recovery).setBigUint64(10,44n,true);
	assert.equal(h.delivery.receive(recovery), 'applied');
	assert.equal(h.delivery.ready, true);
	assert.deepEqual(acks(h.state), [{epoch:1,tick:42n,resync:0},{epoch:1,tick:0n,resync:1},{epoch:1,tick:44n,resync:0}]);
});
test('application failure never ACKs a decoded baseline and closes the socket once', () => {
	const h = setup({applyMessage:message => {
		if (message.type === 'snapshot') throw new Error('world application failed');
		h.state.applied.push(message);
	}});
	h.receive('interest_welcome');
	assert.equal(h.receive('interest_full'), 'closed');
	assert.equal(h.receive('interest_delta'), 'ignored');
	assert.equal(h.delivery.ready, false);
	assert.equal(h.state.sent.length, 0);
	assert.equal(h.state.closes, 1);
	assert.equal(h.state.failures[0].stage, 'handler');
});
test('old socket delivery and callbacks cannot mutate current state or send ACKs', () => {
	const old = setup(); old.receive('interest_welcome'); old.receive('interest_full');
	old.state.current = false;
	const previous = {applied:old.state.applied.length,sent:old.state.sent.length,changes:old.state.changes.length};
	assert.equal(old.receive('interest_delta'), 'ignored');
	assert.equal(old.delivery.receive('not binary'), 'ignored');
	old.delivery.dispose();
	assert.deepEqual(previous, {applied:old.state.applied.length,sent:old.state.sent.length,changes:old.state.changes.length});
	assert.equal(old.state.closes, 0);
	const next = setup(); next.receive('interest_welcome');
	assert.equal(next.receive('interest_delta'), 'resync');
	next.receive('interest_full'); assert.equal(next.delivery.ready, true);
});
test('a socket replaced inside its handler sends no ACK or readiness update', () => {
	const h = setup({applyMessage:message => {
		h.state.applied.push(message);
		if (message.type === 'snapshot') h.state.current = false;
	}});
	h.receive('interest_welcome');
	assert.equal(h.receive('interest_full'), 'ignored');
	assert.equal(h.state.sent.length, 0);
	assert.deepEqual(h.state.changes, []);
});
test('malformed/nonbinary packets fail closed instead of silently keeping a corrupt connection', () => {
	for (const bad of ['text frame', fixture('interest_full').slice(0,-1)]) {
		const h = setup(); h.receive('interest_welcome'); h.receive('interest_full');
		assert.equal(h.delivery.receive(bad), 'closed');
		assert.equal(h.delivery.ready, false);
		assert.deepEqual(h.state.changes, [true,false]);
		assert.equal(h.state.closes, 1);
		assert.equal(h.state.failures[0].stage, 'decode');
		assert.equal(h.state.sent.length, 1);
	}
});
test('ACK send failure closes rather than claiming a synchronized world', () => {
	const h = setup({sendPacket:() => {throw new Error('socket closed during ACK');}});
	h.receive('interest_welcome');
	assert.equal(h.receive('interest_full'), 'closed');
	assert.equal(h.delivery.ready, false);
	assert.equal(h.state.failures[0].stage, 'send');
});
test('a new welcome on the same connection reseeds identity without retaining its old baseline', () => {
	const h = setup(); h.receive('interest_welcome'); h.receive('interest_full');
	h.receive('interest_welcome'); assert.equal(h.delivery.ready, false);
	assert.equal(h.receive('interest_delta'), 'resync');
	h.receive('interest_full'); assert.equal(h.delivery.ready, true);
});
test('a full snapshot older than Welcome is rejected before application or acknowledgement', () => {
	const h = setup(); h.receive('interest_welcome');
	const old = fixture('interest_full'); new DataView(old).setBigUint64(10,41n,true);
	assert.equal(h.delivery.receive(old), 'closed');
	assert.equal(h.state.applied.length, 1);
	assert.equal(h.state.sent.length, 0);
});

test('authority-bearing traffic before Welcome fails closed but native rejection errors reach the UI',()=>{
	for(const name of ['interest_full','interest_delta','pong_basic']){
		const h=setup();assert.equal(h.receive(name),'closed');assert.equal(h.state.applied.length,0);assert.equal(h.state.sent.length,0);assert.equal(h.delivery.ready,false);
	}
	const rejected=setup();assert.equal(rejected.receive('error_room_full'),'applied');assert.equal(rejected.state.applied[0].type,'error');assert.equal(rejected.delivery.ready,false);assert.equal(rejected.state.sent.length,0);
});

test('a content mismatch closing the socket during Welcome cannot apply or ACK the following full snapshot',()=>{
	const h=setup({applyMessage:message=>{h.state.applied.push(message);if(message.type==='welcome')h.state.current=false;}});
	assert.equal(h.receive('interest_welcome'),'ignored');assert.equal(h.receive('interest_full'),'ignored');assert.equal(h.state.applied.length,1);assert.equal(h.state.sent.length,0);assert.equal(h.delivery.ready,false);
});
