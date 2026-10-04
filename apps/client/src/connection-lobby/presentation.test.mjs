import test from 'node:test';
import assert from 'node:assert/strict';
import { lobbyRooms, displayChannel, displayLatency, transferText, chosenAvailable } from './presentation.mjs';

test('channel presentation preserves exact counts and safely projects bounded DTOs', () => {
	const rooms = lobbyRooms([
		{ channel: 3, players: 52, capacity: 50, name: ' West Grove ', privateSession: {} },
		{ channel: 0, players: 0, capacity: 50, name: null },
		{ channel: 3, players: 10, capacity: 50 },
		{ channel: 1, players: -1, capacity: 50 },
		{ channel: 2, players: 1, capacity: 0 },
	], 'Verdant Frontier');
	assert.deepEqual(rooms, [{ channel: 0, players: 0, capacity: 50, name: 'Verdant Frontier' }, { channel: 3, players: 52, capacity: 50, name: 'West Grove' }]);
	assert.equal(lobbyRooms(Array.from({ length: 300 }, (_, channel) => ({ channel, players: 1, capacity: 50 })), 'World').length, 256);
});

test('channel numbering is display-only and latency stays one estimate or unknown', () => {
	assert.equal(displayChannel(0), '01'); assert.equal(displayChannel(19), '20');
	assert.equal(displayLatency(37.7), '~38 ms'); assert.equal(displayLatency(0), '~0 ms');
	for (const value of [null, undefined, NaN, Infinity, -1]) assert.equal(displayLatency(value), '—');
});

test('transfer counters require actual valid counters for one named resource', () => {
	assert.equal(transferText({ resource: 'world.glb', loaded: 1048576, total: 2097152 }), '1.0 MiB / 2.0 MiB');
	assert.equal(transferText({ resource: 'world.glb', loaded: 0, total: 1024 }), '0 B / 1.0 KiB');
	for (const event of [{}, { loaded: 1, total: 2 }, { resource: 'world.glb' }, { resource: 'world.glb', loaded: 3, total: 2 }]) assert.equal(transferText(event), null);
});

test('entry is allowed only for verified Auto or a nonfull selected channel', () => {
	const model = { hasSelection: true, selected: null, autoAvailable: false, rooms: [{ channel: 0, players: 50, capacity: 50 }, { channel: 1, players: 49, capacity: 50 }] };
	assert.equal(chosenAvailable(model), false); model.autoAvailable = true; assert.equal(chosenAvailable(model), true);
	model.selected = 0; assert.equal(chosenAvailable(model), false); model.selected = 1; assert.equal(chosenAvailable(model), true);
	model.selected = 2; assert.equal(chosenAvailable(model), false); model.selected = 1; model.hasSelection = false; assert.equal(chosenAvailable(model), false);
});
