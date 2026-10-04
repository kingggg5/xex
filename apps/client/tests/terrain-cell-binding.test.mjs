// Terrain spec §8.4 test 5: cell GLB slots -> materials (environment.ts substring map + the §5.7 terrain slots).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { TERRAIN_SLOTS, terrainSlotOf } from '../src/terrain-surface-math.mjs';

const src = fileURLToPath(new URL('../src/', import.meta.url));
const environment = readFileSync(`${src}environment.ts`, 'utf8');
// the legacy slot table, parsed from the live source so the test follows environment.ts edits
const table = environment.slice(environment.indexOf('const cellMaterials'), environment.indexOf('];', environment.indexOf('const cellMaterials')));
const LEGACY = [...table.matchAll(/\["([a-z_]+)",/g)].map(m => m[1]);
const CELL_GLBS = ['env_sunmeadow_c7_r6.meshopt.glb', 'env_sunmeadow_c8_r6.meshopt.glb'];

function glbNodeNames(file) {
	const bytes = readFileSync(`${src}assets/world/${file}`);
	assert.equal(bytes.toString('ascii', 0, 4), 'glTF');
	const json = JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString('utf8'));
	return (json.nodes ?? []).map(n => n.name).filter(n => n?.startsWith('Cell '));
}
/** environment.ts H4 resolution order: terrain slots first, then the legacy table (first substring match). */
function resolve(name) {
	const lower = name.toLowerCase();
	const terrain = terrainSlotOf(lower);
	if (terrain) return { kind: TERRAIN_SLOTS[terrain], slot: terrain };
	const legacy = LEGACY.find(key => lower.includes(key));
	return legacy ? { kind: 'legacy', slot: legacy } : { kind: 'fallback-stone', slot: null };
}

test('the legacy slot table was parsed from environment.ts', () => {
	assert.ok(LEGACY.length >= 10, String(LEGACY));
	assert.ok(LEGACY.includes('grass_ground') && LEGACY.includes('stone_foundation'));
});

test('every slot in the live cell GLBs maps to a declared material (no silent stone fallback)', () => {
	for (const file of CELL_GLBS) {
		const names = glbNodeNames(file);
		assert.ok(names.length > 5, file);
		for (const name of names) {
			const r = resolve(name);
			assert.notEqual(r.kind, 'fallback-stone', `${file}: ${name} has no declared material`);
		}
		const ground = names.filter(n => n.endsWith('/ grass_ground'));
		assert.equal(ground.length, 1, `${file} has one grass_ground mesh`);
		assert.deepEqual(resolve(ground[0]), { kind: 'cell', slot: 'grass_ground' }, 'grass_ground is the per-cell splat material');
	}
});

test('no terrain slot falls back to stone, and terrain slots win over legacy keys', () => {
	for (const slot of Object.keys(TERRAIN_SLOTS)) {
		const r = resolve(`Cell sunmeadow_c7_r7 / ${slot}`);
		assert.equal(r.slot, slot);
		assert.notEqual(r.kind, 'fallback-stone');
	}
});

test('no slot name is a substring collision', () => {
	const terrain = Object.keys(TERRAIN_SLOTS);
	for (const t of terrain) {
		for (const k of LEGACY) {
			if (t === k) continue;   // grass_ground is the same slot in both tables
			assert.ok(!t.includes(k) && !k.includes(t), `terrain slot ${t} collides with legacy ${k}`);
		}
		for (const u of terrain) if (u !== t) assert.ok(!u.includes(t), `${t} is a substring of ${u}`);
	}
	// inside the legacy table a shorter prefix must come after every longer key that contains it (first match wins)
	LEGACY.forEach((key, i) => {
		LEGACY.forEach((other, j) => {
			if (i !== j && other.includes(key)) assert.ok(j < i, `${other} must be listed before its prefix ${key}`);
		});
	});
});
