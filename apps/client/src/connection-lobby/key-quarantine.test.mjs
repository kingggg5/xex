import test from 'node:test';
import assert from 'node:assert/strict';
import { createLobbyKeyQuarantine } from './key-quarantine.mjs';
const key = (key, code, extras = {}) => ({ key, code, repeat: false, ctrlKey: false, metaKey: false, altKey: false, ...extras });

test('a gameplay key held through the overlay cannot start movement on ready repeats', () => {
	const policy = createLobbyKeyQuarantine(), down = key('w', 'KeyW');
	assert.equal(policy.keyDown(down, true), false);
	assert.equal(policy.keyDown({ ...down, repeat: true }, false), true);
	assert.equal(policy.keyDown({ ...down, repeat: true }, false), true);
	policy.keyUp(down); assert.equal(policy.keyDown({ ...down, repeat: true }, false), false);
});
test('fresh input recovers a missed release and native shortcuts remain available', () => {
	const policy = createLobbyKeyQuarantine(), down = key(' ', 'Space');
	policy.keyDown(down, true);
	assert.equal(policy.keyDown({ ...down, repeat: true, ctrlKey: true }, false), false);
	assert.equal(policy.size(), 1); assert.equal(policy.keyDown(down, false), false); assert.equal(policy.size(), 0);
	for (const event of [key('Tab', 'Tab'), key('Enter', 'Enter'), key('F5', 'F5'), key('w', 'KeyW', { metaKey: true })]) policy.keyDown(event, true);
	assert.equal(policy.size(), 0);
});
test('all held entries are drawn from the bounded gameplay vocabulary and use HUD key normalization', () => {
	const policy = createLobbyKeyQuarantine();
	for (let i = 0; i < 1000; i++) policy.keyDown(key(`Unknown${i}`, `Unknown${i}`), true);
	assert.equal(policy.size(), 0);
	policy.keyDown(key('a', 'KeyQ'), true); assert.equal(policy.keyDown(key('a', 'KeyQ', { repeat: true }), false), true);
	policy.clear(); assert.equal(policy.size(), 0);
});
