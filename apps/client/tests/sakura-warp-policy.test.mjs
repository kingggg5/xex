import test from 'node:test';
import assert from 'node:assert/strict';
import { SAKURA_PALETTE, SAKURA_TREE_IDS, isSakuraPlacement, sakuraPlacement, sakuraShaderCode } from '../src/sakura-look-policy.mjs';
import { DUNGEON_DESTINATIONS, DUNGEON_WARP_HUB, warpDestinationEnabled, warpProximity } from '../src/dungeon-warp-policy.mjs';

test('Sakura restyles exactly the two existing trees without changing anchors, scale, rotation, collision labels or source input', () => {
	assert.deepEqual(SAKURA_TREE_IDS, ['tree_spot_0', 'tree_spot_1']);
	const originals = [
		{ id: 'tree_spot_0', species: 'qn_broadleaf_m', x: -18, y: 0, z: 5, yaw: 0, scale: .96, cell: 'c7_r8', keep: true, order: 0, collider: 'original-0' },
		{ id: 'tree_spot_1', species: 'qn_broadleaf_l', x: 18, y: 0, z: 7, yaw: 1.3, scale: .9, cell: 'c8_r8', keep: true, order: 1, collider: 'original-1' },
	];
	for (const input of originals) {
		const snapshot = { ...input }; Object.freeze(input);
		assert.equal(isSakuraPlacement(input), true);
		const result = sakuraPlacement(input);
		assert.notEqual(result, input); assert.deepEqual(result, { ...snapshot, species: `sakura-${snapshot.species}` });
		assert.deepEqual(input, snapshot);
	}
	assert.equal(isSakuraPlacement({ id: 'tree_spot_2' }), false);
	assert.equal(isSakuraPlacement({ id: 'sunmeadow_oak_east' }), false);
});
test('unselected trees and conifers cannot enter the Sakura variant', () => {
	assert.throws(() => sakuraPlacement({ id: 'tree_spot_2', species: 'qn_broadleaf_m' }));
	assert.throws(() => sakuraPlacement({ id: 'tree_spot_0', species: 'qn_conifer_m' }));
});
test('both Sakura shader languages preserve alpha and share the same bounded palette', () => {
	for (const colour of Object.values(SAKURA_PALETTE)) for (const component of colour) assert.ok(Number.isFinite(component) && component >= 0 && component <= 1);
	const glsl = sakuraShaderCode(false), wgsl = sakuraShaderCode(true);
	assert.match(glsl, /baseColor\s*=\s*vec4\(/); assert.match(wgsl, /baseColor\s*=\s*vec4f\(/);
	for (const shader of [glsl, wgsl]) {
		assert.match(shader, /baseColor\.a\)/); assert.match(shader, /0\.2126, 0\.7152, 0\.0722/);
		for (const colour of Object.values(SAKURA_PALETTE)) assert.ok(shader.includes(colour.join(', ')));
		assert.doesNotMatch(shader, /emissiveColor\s*=|alpha\s*=\s*1/);
	}
});
test('planned and unknown warp destinations are disabled regardless of connection or busy state', () => {
	for (const connected of [false, true]) for (const busy of [false, true]) {
		for (const destination of DUNGEON_DESTINATIONS.filter(value => value.kind === 'planned')) assert.equal(warpDestinationEnabled(destination.id, { connected, busy }), false);
		for (const id of ['', 'unknown', 'local-teleport']) assert.equal(warpDestinationEnabled(id, { connected, busy }), false);
	}
	assert.equal(warpDestinationEnabled('tower'), false);
	assert.equal(warpDestinationEnabled('tower', { connected: true, busy: false }), true);
	assert.equal(warpDestinationEnabled('tower', { connected: false, busy: false }), false);
	assert.equal(warpDestinationEnabled('tower', { connected: true, busy: true }), false);
});
test('warp proximity distinguishes interaction and effect distances at exact boundaries', () => {
	const { x, z, radius, effectDistance } = DUNGEON_WARP_HUB;
	assert.equal(warpProximity({ x, z }).near, true);
	assert.deepEqual(warpProximity({ x: x + radius, z }), { near: true, effects: true });
	assert.deepEqual(warpProximity({ x: x + radius + 1e-6, z }), { near: false, effects: true });
	assert.deepEqual(warpProximity({ x: x + effectDistance, z }), { near: false, effects: true });
	assert.deepEqual(warpProximity({ x: x + effectDistance + 1e-6, z }), { near: false, effects: false });
	assert.equal(DUNGEON_WARP_HUB.id, 'warp_city_portal_dais');
	assert.deepEqual(DUNGEON_WARP_HUB.cityLocalXZ, [40, 10]);
});
test('invalid player/origin coordinates never show an interaction or effect', () => {
	for (const player of [null, {}, { x: NaN, z: 1 }, { x: Infinity, z: 1 }, { x: '40', z: 186 }]) assert.deepEqual(warpProximity(player), { near: false, effects: false });
	assert.deepEqual(warpProximity({ x: 40, z: 186 }, { ...DUNGEON_WARP_HUB, x: NaN }), { near: false, effects: false });
});
