// Terrain spec §8.4 test 1: generated GLSL/WGSL plugin code (TerrainSurfacePlugin, RockSurfacePlugin).
import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const bundled = await build({ stdin: { contents: `
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial';
export {ShaderLanguage} from '@babylonjs/core/Materials/shaderLanguage';
export * from './src/terrain-surface';
export * from './src/terrain-rock-surface';`, resolveDir: root, loader: 'ts' }, bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent', loader: { '.png': 'empty', '.ktx2': 'empty' } });
const api = await import('data:text/javascript;base64,' + Buffer.from(bundled.outputFiles[0].text).toString('base64'));
const { ShaderLanguage } = api;
const GLSL = api.terrainFragmentCode(ShaderLanguage.GLSL), WGSL = api.terrainFragmentCode(ShaderLanguage.WGSL);
const RGLSL = api.rockFragmentCode(ShaderLanguage.GLSL), RWGSL = api.rockFragmentCode(ShaderLanguage.WGSL);
const HOOKS = ['CUSTOM_FRAGMENT_DEFINITIONS', 'CUSTOM_FRAGMENT_BEFORE_LIGHTS', 'CUSTOM_FRAGMENT_UPDATE_METALLICROUGHNESS'];
const all = code => Object.values(code).join('\n');

/** Strip `#ifdef NAME ... #endif` blocks (nesting-aware) - what the preprocessor leaves when NAME is undefined. */
function without(code, name) {
	const out = [];
	let depth = 0, skipping = 0;
	for (const line of code.split('\n')) {
		const t = line.trim();
		if (/^#if/.test(t)) {
			depth++;
			if (!skipping && (t === `#ifdef ${name}` || t.startsWith(`#if ${name} `) || t.startsWith(`#if defined(${name})`))) skipping = depth;
			if (skipping) continue;
		} else if (t === '#endif') {
			const closing = depth--;
			if (skipping && closing === skipping) { skipping = 0; continue; }
			if (skipping) continue;
		} else if (skipping) continue;
		out.push(line);
	}
	return out.join('\n');
}

test('both plugins emit the three PBR hooks in GLSL and WGSL and declare both languages compatible', () => {
	for (const code of [GLSL, WGSL, RGLSL, RWGSL]) for (const hook of HOOKS) assert.ok(code[hook]?.trim().length > 0, hook);
	assert.ok(GLSL.CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR && WGSL.CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR, 'debug views write at BEFORE_FRAGCOLOR');
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	try {
		const material = new api.PBRMaterial('t', scene);
		const plugin = new api.TerrainSurfacePlugin(material, { mode: 'cell', tier: 2, debug: 0, solo: -1, layerTextures: () => [], cellTextures: () => [], cell: null, tiles: [6, 5, 4, 3], means: [], legacy: null, look: { normalStrength: 1, edgeBreakup: 0.9, cellAO: 0.75 } });
		assert.equal(plugin.isCompatible(ShaderLanguage.GLSL), true);
		assert.equal(plugin.isCompatible(ShaderLanguage.WGSL), true);
		// regression: without registerForExtraEvents Babylon never calls hardBindForSubMesh (all uniforms zero)
		assert.equal(plugin.registerForExtraEvents, true);
		const rock = new api.RockSurfacePlugin(new api.PBRMaterial('r', scene), { rockAH: null, rockNRO: null, mossAH: null, mossNRO: null, rockTile: 4, mossTile: 3, style: 'granite' });
		assert.equal(rock.isCompatible(ShaderLanguage.WGSL), true);
		assert.equal(rock.registerForExtraEvents, true);
	} finally { scene.dispose(); engine.dispose(); }
});

test('no cross-language tokens', () => {
	for (const [name, code] of [['terrain WGSL', all(WGSL)], ['rock WGSL', all(RWGSL)]]) {
		for (const token of ['vec2(', 'vec3(', 'vec4(', 'texture2D(', 'textureGrad(', 'uniform sampler2D', 'float ', 'dFdx(', 'dFdy(', 'toLinearSpace(']) {
			assert.ok(!code.includes(token), `${name} contains GLSL token ${token}`);
		}
	}
	for (const [name, code] of [['terrain GLSL', all(GLSL)], ['rock GLSL', all(RGLSL)]]) {
		for (const token of ['vec2f', 'vec3f', 'vec4f', 'let ', 'var ', 'fn ', 'textureSampleGrad', 'uniforms.', 'fragmentInputs.', 'dpdx(', 'toLinearSpaceVec3']) {
			assert.ok(!code.includes(token), `${name} contains WGSL token ${token}`);
		}
	}
});

test('WGSL samples only with explicit gradients and takes derivatives in uniform control flow', () => {
	for (const [name, code] of [['terrain', all(WGSL)], ['rock', all(RWGSL)]]) {
		assert.ok(!/textureSample\(|textureSampleBias\(/.test(code), `${name}: implicit-derivative sample`);
		assert.ok(/textureSampleGrad\(/.test(code), `${name}: grad sampling present`);
	}
	// every dpdx/dpdy runs in uniform control flow: outside every block of its body (cell / far / rock); the cell body
	// takes the SDF / rut derivatives after its near block, where control flow has reconverged
	const terrain = WGSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS;
	const [cell, far] = terrain.split('#ifdef TERRAIN_FAR');
	for (const [name, body] of [['cell', cell], ['far', far], ['rock', RWGSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS]]) {
		assert.ok(/\bif \(/.test(body), `${name} has branches`);
		for (const m of body.matchAll(/dpdx\(|dpdy\(/g)) assert.deepEqual(enclosingIfs(body, m.index), [], `${name}: derivative inside a block`);
	}
	// same rule in GLSL (portable behaviour; GLSL tolerates it but mips would be wrong at branch edges)
	const [gcell] = GLSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS.split('#ifdef TERRAIN_FAR');
	for (const m of gcell.matchAll(/dFdx\(|dFdy\(/g)) assert.deepEqual(enclosingIfs(gcell, m.index), []);
	assert.ok(!/\btexture\(/.test(all(GLSL)) && !/\btexture\(/.test(all(RGLSL)), 'GLSL uses textureGrad only');
});

test('WGSL never assigns to a multi-component swizzle (recheck 21.3)', () => {
	for (const code of [all(WGSL), all(RWGSL)]) {
		assert.ok(!/\.(rgb|rgba|xyz|xyzw|xy|zw|yz|rg|gb|ba)\s*=[^=]/.test(code), 'multi-component swizzle assignment');
	}
});

test('sampler names match getSamplers(), within the 13 / 16 budget', () => {
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	try {
		const state = mode => ({ mode, tier: 2, debug: 0, solo: -1, layerTextures: () => [], cellTextures: () => [], cell: null, tiles: [6, 5, 4, 3], means: [], legacy: null, look: { normalStrength: 1, edgeBreakup: 0.9, cellAO: 0.75 } });
		const cellPlugin = new api.TerrainSurfacePlugin(new api.PBRMaterial('c', scene), state('cell'));
		const farPlugin = new api.TerrainSurfacePlugin(new api.PBRMaterial('f', scene), state('far'));
		const cellSamplers = [], farSamplers = [];
		cellPlugin.getSamplers(cellSamplers);
		farPlugin.getSamplers(farSamplers);
		assert.equal(cellSamplers.length, 10, 'cell: 8 layer + splat + data');
		assert.equal(farSamplers.length, 2);
		assert.ok(cellSamplers.length + 3 <= 13 && 13 <= 16, 'cell material total 13 with the 3 base PBR samplers');
		const defs = WGSL.CUSTOM_FRAGMENT_DEFINITIONS, gdefs = GLSL.CUSTOM_FRAGMENT_DEFINITIONS;
		const cellDefs = defs.split('#ifdef TERRAIN_SPLAT')[1].split('#endif')[0], gCellDefs = gdefs.split('#ifdef TERRAIN_SPLAT')[1].split('#endif')[0];
		const wgslTextures = [...cellDefs.matchAll(/var (\w+): texture_2d<f32>;/g)].map(m => m[1]);
		const wgslSamplers = [...cellDefs.matchAll(/var (\w+)Sampler: sampler;/g)].map(m => m[1]);
		const glslSamplers = [...gCellDefs.matchAll(/uniform sampler2D (\w+);/g)].map(m => m[1]);
		assert.deepEqual(wgslTextures, cellSamplers);
		assert.deepEqual(wgslSamplers, cellSamplers);
		assert.deepEqual(glslSamplers, cellSamplers);
		const farDefs = defs.split('#ifdef TERRAIN_FAR')[1].split('#endif')[0];
		assert.deepEqual([...farDefs.matchAll(/var (\w+): texture_2d<f32>;/g)].map(m => m[1]), farSamplers);
		const rock = new api.RockSurfacePlugin(new api.PBRMaterial('r', scene), { rockTile: 4, mossTile: 3, style: 'granite' });
		const rockSamplers = [];
		rock.getSamplers(rockSamplers);
		assert.equal(rockSamplers.length, 4, 'generic rock: 4 custom (7 with base PBR)');
		assert.deepEqual([...RWGSL.CUSTOM_FRAGMENT_DEFINITIONS.matchAll(/var (\w+): texture_2d<f32>;/g)].map(m => m[1]), rockSamplers);
		assert.deepEqual([...RGLSL.CUSTOM_FRAGMENT_DEFINITIONS.matchAll(/uniform sampler2D (\w+);/g)].map(m => m[1]), rockSamplers);
	} finally { scene.dispose(); engine.dispose(); }
});

test('GLSL uniform declarations match the UBO list and cover every uniform the code reads', () => {
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	try {
		const plugin = new api.TerrainSurfacePlugin(new api.PBRMaterial('u', scene), { mode: 'cell', tier: 2, debug: 0, solo: -1, layerTextures: () => [], cellTextures: () => [], cell: null, tiles: [6, 5, 4, 3], means: [], legacy: null, look: { normalStrength: 1, edgeBreakup: 0.9, cellAO: 0.75 } });
		const u = plugin.getUniforms(ShaderLanguage.GLSL);
		const declared = [...u.fragment.matchAll(/uniform vec4 (\w+);/g)].map(m => m[1]);
		assert.deepEqual(declared, u.ubo.map(e => e.name));
		assert.deepEqual(declared, [...api.TERRAIN_UNIFORMS]);
		assert.equal(plugin.getUniforms(ShaderLanguage.WGSL).fragment, '', 'WGSL reads uniforms.<name> from the UBO');
		const used = new Set([...all(GLSL).matchAll(/\b(terrain(?:Cell|CellRes|Tile|HScale|HBias|Blend|Rut|Weather|Mean[0-3]|Look))\b/g)].map(m => m[1]));
		for (const name of used) assert.ok(declared.includes(name), `undeclared uniform ${name}`);
		const usedWgsl = new Set([...all(WGSL).matchAll(/uniforms\.(\w+)/g)].map(m => m[1]));
		for (const name of usedWgsl) assert.ok(declared.includes(name), `WGSL reads undeclared uniforms.${name}`);
		const rock = new api.RockSurfacePlugin(new api.PBRMaterial('ru', scene), { rockTile: 4, mossTile: 3, style: 'sandstone' });
		const ru = rock.getUniforms(ShaderLanguage.GLSL);
		const rdeclared = [...ru.fragment.matchAll(/uniform vec4 (\w+);/g)].map(m => m[1]);
		for (const name of new Set([...all(RWGSL).matchAll(/uniforms\.(\w+)/g)].map(m => m[1]))) assert.ok(rdeclared.includes(name), name);
	} finally { scene.dispose(); engine.dispose(); }
});

test('debug code is compiled out without TERRAIN_DEBUG; solo is DEV-only define-guarded', () => {
	for (const code of [GLSL, WGSL]) {
		const body = without(code.CUSTOM_FRAGMENT_BEFORE_LIGHTS, 'TERRAIN_DEBUG');
		assert.ok(!/terrainDebugOut\s*=/.test(body), 'debug assignment outside #ifdef TERRAIN_DEBUG');
		assert.ok(!/finalColor\s*=/.test(without(code.CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR, 'TERRAIN_DEBUG')), 'finalColor write outside #ifdef TERRAIN_DEBUG');
		const noSolo = without(code.CUSTOM_FRAGMENT_BEFORE_LIGHTS, 'TERRAIN_SOLO');
		assert.equal((noSolo.match(/^\s*tW = /gm) ?? []).length, 0, 'tW is only reassigned by the solo block');
	}
	// tier 0 NRO threshold is a variable in both languages (WGSL has no macro substitution)
	assert.ok(!/#define TERRAIN_NRO_MIN/.test(all(WGSL)) && /tNroMin/.test(all(WGSL)));
	assert.match(WGSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS, /var tNroMin: f32 = 0\.150;/);
	assert.match(GLSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS, /float tNroMin = 0\.004;/);
});

test('debug modes map to distinct define values and the documented order', () => {
	assert.deepEqual([...api.TERRAIN_DEBUG_MODES].slice(0, 10), ['off', 'weights', 'height', 'normal', 'rough', 'ao', 'sdf', 'tiling', 'mip', 'fetches']);
	for (let i = 1; i < api.TERRAIN_DEBUG_MODES.length; i++) assert.match(GLSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS, new RegExp(`TERRAIN_DEBUG == ${i}\\b`));
});

// ---- GPU cost study (P1 report §10): noise placement, exact layer cull, baked-field define, DEV probes ----

/** Opening lines of the `if (...) {` blocks enclosing `index` (brace depth over the generated code). */
function enclosingIfs(code, index) {
	const stack = [];
	let line = '';
	for (let i = 0; i < index; i++) {
		const ch = code[i];
		if (ch === '\n') { line = ''; continue; }
		line += ch;
		if (ch === '{') stack.push(line.trim());
		else if (ch === '}') stack.pop();
	}
	return stack;
}

test('production cell body: no value noise in uniform flow; macro and anti-tiling mask come from the cell maps', () => {
	for (const [lang, code] of [['WGSL', WGSL], ['GLSL', GLSL]]) {
		const [cellRaw] = code.CUSTOM_FRAGMENT_BEFORE_LIGHTS.split('#ifdef TERRAIN_FAR');
		const baked = cellRaw.split('#ifdef TERRAIN_NOISE_MAPS')[1].split('#else')[0];
		assert.match(baked, /tM2[^\n]*= tSplat\.a;/, `${lang}: macro from splat alpha`);
		assert.match(baked, /tMaskN[^\n]*= tData\.a;/, `${lang}: anti-tiling mask from data alpha`);
		const cell = without(cellRaw, 'TERRAIN_NOISE_MAPS');
		assert.ok(!/terrainVNx\(/.test(cell), `${lang}: exact-hash noise only in the unbaked fallback`);
		const calls = [...cell.matchAll(/terrainVN\(/g)];
		assert.equal(calls.length, 3, `${lang}: two edge octaves and the rut wander`);
		for (const m of calls) {
			const ifs = enclosingIfs(cell, m.index);
			assert.ok(ifs.some(s => s.startsWith('if (tBand > 0.0)') || s.startsWith('if (tRutV < 254.5')), `${lang}: noise outside its branch: ${ifs.join(' | ')}`);
		}
		// the far path (layer means) only where the far fade has started
		assert.match(cell, /if \(tFar > 0\.0\) \{[^}]*terrainMean0[^}]*\}/);
	}
	// the far material evaluates the same exact-hash fields per pixel, so a baked cell meets it without a seam
	const far = WGSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS.split('#ifdef TERRAIN_FAR')[1];
	assert.match(far, /terrainVNx\(tXZ \* \(1\.0 \/ 31\.0\)\)/);
	assert.match(far, /terrainVNx\(tXZ \* \(1\.0 \/ 7\.3\)\)/);
});

test('exact layer cull (DEV probe, measured not to pay): only layers whose best case can win the blend are fetched', () => {
	// production keeps the P1 fetch rule: every layer with w > 0.004, dirt also inside the edge band
	for (const code of [WGSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS, GLSL.CUSTOM_FRAGMENT_BEFORE_LIGHTS]) {
		assert.ok(!/tC0|tVhi|tKeep/.test(code), 'no cull in the production code');
		assert.match(code, /if \(tW\.z > 0\.004 \|\| tBand > 0\.0\) \{/);
	}
	for (const lang of [ShaderLanguage.WGSL, ShaderLanguage.GLSL]) {
		const code = api.terrainFragmentCode(lang, { cull: 'early' }).CUSTOM_FRAGMENT_BEFORE_LIGHTS;
		const keep = code.indexOf('tC0 = ');
		assert.ok(keep > 0 && keep < code.indexOf('terrainLushAH, '), 'cull before the first layer fetch');
		// best case: height 1 (max of hScale + hBias, hBias); worst case of the others: height 0 (min); minus delta
		assert.match(code, /tVhi[^\n]*= tW \+ [^\n]*terrainBlend\.x \* max\([^\n]*terrainHScale \+ [^\n]*terrainHBias, [^\n]*terrainHBias\) \* smoothstep/);
		assert.match(code, /tVlo[^\n]*= tW \+ [^\n]*terrainBlend\.x \* min\(/);
		assert.match(code, /tVoth[^\n]*- [^\n]*\([^\n]*terrainBlend\.y \+ 1e-4\)/);
		for (let i = 0; i < 4; i++) assert.match(code, new RegExp(`tC${i} = tBand > 0\\.0 \\|\\| tVhi\\.${'xyzw'[i]} > tVoth\\.${'xyzw'[i]};`));
		for (const [i, c] of [[0, 'x'], [1, 'y'], [3, 'w']]) assert.match(code, new RegExp(`if \\(tW\\.${c} > 0\\.004 && tC${i}\\) \\{`));
		assert.match(code, /if \(tBand > 0\.0 \|\| \(tW\.z > 0\.004 && tC2\)\) \{/, 'dirt: always in the edge band');
	}
	// CPU proof on the lab cell's weight distribution: a culled layer can never get b > 0, whatever the heights
	const lam = 0.6, delta = 0.12, hs = [1, 1, 1, 0.5];
	const ss = w => { const t = Math.min(1, Math.max(0, w / 0.3)); return t * t * (3 - 2 * t); };
	for (let k = 0; k < 5000; k++) {
		const raw = [Math.random(), Math.random() ** 3, Math.random() ** 4, Math.random() ** 6], sum = raw.reduce((a, b) => a + b, 0);
		const w = raw.map(v => v / sum), h = w.map(() => Math.random());
		const hi = w.map((v, i) => v + lam * hs[i] * ss(v)), lo = w.map(v => v);
		const keepLayer = w.map((_, i) => hi[i] > Math.max(...lo.filter((_, j) => j !== i)) - delta - 1e-4);
		const v = w.map((x, i) => x + lam * h[i] * hs[i] * ss(x)), m = Math.max(...v) - delta;
		for (let i = 0; i < 4; i++) if (!keepLayer[i]) assert.equal(Math.max(v[i] - m, 0), 0, `culled layer ${i} would contribute`);
	}
});

test('TERRAIN_NOISE_MAPS follows the cell plugin state; DEV probes get their own define value', () => {
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	try {
		const state = (mode, extra = {}) => ({ mode, tier: 2, debug: 0, solo: -1, layerTextures: () => [], cellTextures: () => [], cell: null, tiles: [6, 5, 4, 3], means: [], legacy: null, look: { normalStrength: 1, edgeBreakup: 0.9, cellAO: 0.75 }, ...extra });
		const defines = plugin => { const d = {}; plugin.prepareDefines(d); return d; };
		assert.equal(defines(new api.TerrainSurfacePlugin(new api.PBRMaterial('a', scene), state('cell', { noiseMaps: true }))).TERRAIN_NOISE_MAPS, true);
		assert.equal(defines(new api.TerrainSurfacePlugin(new api.PBRMaterial('b', scene), state('cell'))).TERRAIN_NOISE_MAPS, false);
		assert.equal(defines(new api.TerrainSurfacePlugin(new api.PBRMaterial('c', scene), state('far', { noiseMaps: true }))).TERRAIN_NOISE_MAPS, false);
		assert.equal(defines(new api.TerrainSurfacePlugin(new api.PBRMaterial('d', scene), state('cell'))).TERRAIN_PROBE, false, 'production: no probe define');
		const probed = defines(new api.TerrainSurfacePlugin(new api.PBRMaterial('e', scene), state('cell', { probe: { noNro: true } }))).TERRAIN_PROBE;
		assert.ok(Number.isInteger(probed) && probed > 0);
		assert.equal(api.terrainProbeId({ noNro: true }), probed, 'stable id per probe');
		assert.notEqual(api.terrainProbeId({ noAnti: true }), probed);
		assert.equal(api.terrainProbeId(null), 0);
	} finally { scene.dispose(); engine.dispose(); }
	// probes never leak into the production code
	assert.notDeepEqual(api.terrainFragmentCode(ShaderLanguage.WGSL, { noNro: true }), WGSL);
	assert.equal(api.terrainFragmentCode(ShaderLanguage.WGSL, null), WGSL);
	assert.ok(!/textureSampleLevel|terrainLod/.test(all(WGSL)) && !/textureLod|terrainLod/.test(all(GLSL)));
});
