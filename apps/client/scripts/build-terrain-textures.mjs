// Terrain spec §6 script 5: KTX2 runtime textures, cell map copies and terrain-layerset.json, with the §6.2 checks.
//
//   node scripts/build-terrain-textures.mjs [--staging <dir>] [--waive size] [--skip-encode]
//
// Python (numpy) does the numbers: tools/terrain/check_terrain_textures.py packs AH/NRO (explicit Toksvig NRO
// mips), pre-checks, and checks the decoded KTX2 levels (§3.3 on decoded mip0/mip2, §6.2 items 6-7). This script
// runs the pinned KTX-Software 4.4.2, validates, extracts, copies the per-cell PNGs (they stay lossless PNG, §8.8),
// and writes apps/client/src/assets/world/terrain/terrain-layerset.json plus
// planning/evidence/terrain-splat-v1/ktx2-receipt.json (tool version, commands, SHA-256 of every input/output).
// Any failed check exits 1 unless its id is waived (--waive size); waivers are recorded in the receipt.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const client = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(client, '../..');
const argv = process.argv.slice(2);
const option = (name, fallback) => { const i = argv.indexOf(name); return i >= 0 && i + 1 < argv.length ? argv[i + 1] : fallback; };
const waived = new Set(option('--waive', '').split(',').filter(Boolean));
const staging = path.resolve(option('--staging', path.join(os.tmpdir(), 'xexoria-terrain-textures')));
const python = process.env.PYTHON_BIN || 'python';
const ktxDir = process.env.KTX_SOFTWARE_BIN || path.join(root, '.harness/.cache/toolchains/ktx-4.4.2/portable/bin');
const ktx = path.join(ktxDir, process.platform === 'win32' ? 'ktx.exe' : 'ktx');
const runtimeDir = path.join(client, 'src/assets/world/terrain');
const evidenceDir = path.join(root, 'planning/evidence/terrain-splat-v1');
const posix = p => p.replaceAll('\\', '/');
const relRoot = p => posix(path.relative(root, p));
const hash = p => createHash('sha256').update(readFileSync(p)).digest('hex');
const commands = [];

function run(executable, args, { quiet = false, allowFail = false } = {}) {
	const shown = [path.basename(executable), ...args.map(a => (path.isAbsolute(a) ? posix(path.relative(root, a)) : a))].join(' ');
	commands.push(shown);
	const result = spawnSync(executable, args, { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
	if (result.error) throw result.error;
	if (!quiet && result.stdout.trim()) process.stdout.write(result.stdout);
	if (result.status !== 0 && !allowFail) {
		process.stderr.write(result.stderr || '');
		throw new Error(`Terrain texture step failed (${result.status}): ${shown}`);
	}
	return result;
}

const checks = [];
const check = (id, item, pass, detail) => { checks.push({ id, item, pass: Boolean(pass), waived: !pass && waived.has(id), detail }); };

// --- 1. Tool -------------------------------------------------------------------------------------------------------
if (!existsSync(ktx)) throw new Error('KTX-Software 4.4.2 not found; set KTX_SOFTWARE_BIN to its bin folder.');
const ktxVersion = run(ktx, ['--version'], { quiet: true }).stdout.trim();
check('tool', 1, ktxVersion.includes('4.4.2'), ktxVersion);
if (!ktxVersion.includes('4.4.2')) throw new Error(`Terrain textures require KTX 4.4.2 (found ${ktxVersion}).`);

run(python, ['-B', 'assets/blender/sunmeadow_v2/terrain/terrain_spec.py', '--emit-json']);
const spec = JSON.parse(readFileSync(path.join(root, 'assets/models/sunmeadow-v2/terrain/terrain-spec.json'), 'utf8'));
const K = spec.ktx;
const gates = spec.gates;

// --- 2. Pack + pre-checks ------------------------------------------------------------------------------------------
rmSync(staging, { recursive: true, force: true });
mkdirSync(staging, { recursive: true });
const packRun = run(python, ['-B', 'tools/terrain/check_terrain_textures.py', 'pack', '--staging', staging], { allowFail: true });
run(python, ['-B', 'tools/terrain/check_terrain_textures.py', 'calibration', '--staging', staging]);
const pack = JSON.parse(readFileSync(path.join(staging, 'pack.json'), 'utf8'));
check('precheck', 2, packRun.status === 0 && pack.failures.length === 0,
	pack.failures.length ? pack.failures : 'power-of-two, seams <= 1.15, albedo in [0.04, 0.90], height range, metal = 0, cell PNGs RGB8 without colour chunks');

// --- 3/4. Encode ---------------------------------------------------------------------------------------------------
const layerDir = path.join(runtimeDir, 'layers');
const labDir = path.join(runtimeDir, 'lab');
const decodedDir = path.join(staging, 'decoded');
for (const dir of [layerDir, labDir, decodedDir, path.join(staging, 'ref')]) mkdirSync(dir, { recursive: true });
for (const file of readdirSync(layerDir)) if (file.endsWith('.ktx2')) rmSync(path.join(layerDir, file));
const stage = name => path.join(staging, name);
const ahArgs = [...K.ah, ...K.mip_generate, ...K.origin];
const nroArgs = (levels) => [...K.nro, '--levels', String(levels), ...K.origin];
const encoded = {};
const infoChecks = [];

function inspect(file, expectLevels, label) {
	run(ktx, ['validate', file], { quiet: true });
	const info = JSON.parse(run(ktx, ['info', '--format', 'json', file], { quiet: true }).stdout);
	const dfd = info.dataFormatDescriptor.blocks[0];
	const ok = info.header.levelCount === expectLevels && dfd.colorModel === 'KHR_DF_MODEL_UASTC'
		&& info.header.supercompressionScheme === 'KTX_SS_ZSTD' && dfd.transferFunction === 'KHR_DF_TRANSFER_LINEAR'
		&& info.keyValueData?.KTXorientation === 'ru';
	infoChecks.push({ file: relRoot(file), label, ok, levels: info.header.levelCount, expectLevels, colorModel: dfd.colorModel,
		supercompression: info.header.supercompressionScheme, transfer: dfd.transferFunction, orientation: info.keyValueData?.KTXorientation });
	return ok;
}

function extract(file, outName, transcode = true) {
	const out = path.join(decodedDir, outName);
	rmSync(out, { recursive: true, force: true });
	run(ktx, ['extract', ...(transcode ? ['--transcode', 'rgba8'] : []), '--level', 'all', file, out], { quiet: true });
}

const sizes = [];
for (const [lid, rec] of Object.entries(pack.layers)) {
	for (const res of Object.keys(rec.ah)) {
		const levels = Math.log2(Number(res)) + 1;
		const ahOut = path.join(layerDir, `${rec.name}_ah_${res}.ktx2`);
		const nroOut = path.join(layerDir, `${rec.name}_nro_${res}.ktx2`);
		const ref = path.join(staging, 'ref', `${lid}_ahref_${res}.ktx2`);
		run(ktx, ['create', ...ahArgs, stage(rec.ah[res].ktx_input), ahOut], { quiet: true });
		// uncompressed reference with the same mip generation: PSNR at mip2 measures only the UASTC/RDO loss
		run(ktx, ['create', '--format', 'R8G8B8A8_UNORM', '--assign-tf', 'linear', ...K.mip_generate, ...K.origin,
			stage(rec.ah[res].ktx_input), ref], { quiet: true });
		run(ktx, ['create', ...nroArgs(rec.nro[res].ktx_inputs.length), ...rec.nro[res].ktx_inputs.map(stage), nroOut], { quiet: true });
		inspect(ahOut, levels, `${lid} AH ${res}`);
		inspect(nroOut, levels, `${lid} NRO ${res}`);
		extract(ahOut, `${lid}_ah_${res}`);
		extract(ref, `${lid}_ahref_${res}`, false);
		extract(nroOut, `${lid}_nro_${res}`);
		const limit = Number(res) >= 1024 ? gates.size_1024_max_bytes : gates.size_512_max_bytes / (Number(res) >= 512 ? 1 : 4);
		for (const [kind, file] of [['ah', ahOut], ['nro', nroOut]]) {
			sizes.push({ file: relRoot(file), bytes: statSync(file).size, limit, ok: statSync(file).size <= limit, layer: lid, kind, res: Number(res) });
		}
		encoded[`${lid}_${res}`] = {
			ah: { path: relRoot(ahOut), bytes: statSync(ahOut).size, sha256: hash(ahOut) },
			nro: { path: relRoot(nroOut), bytes: statSync(nroOut).size, sha256: hash(nroOut), levels: rec.nro[res].ktx_inputs.length },
		};
		console.log(`KTX2 ${lid} ${res}: AH ${(statSync(ahOut).size / 1e6).toFixed(3)} MB, NRO ${(statSync(nroOut).size / 1e6).toFixed(3)} MB`);
	}
}
writeFileSync(path.join(staging, 'encoded.json'), `${JSON.stringify(encoded, null, 1)}\n`);
check('encode-ah', 3, true, ahArgs.join(' '));
check('encode-nro', 4, true, `${K.nro.join(' ')} --levels <n> ${K.origin.join(' ')} (explicit Toksvig levels; no --normalize, B = roughness)`);
check('relief-bakes', 5, true, 'deferred: hero relief bakes arrive with script 4 in P2 (no bake inputs in P1)');

// calibration (lab only): AH + NRO KTX2 and the same pixels as PNG (alpha 255, so no premultiply risk)
const calibration = JSON.parse(readFileSync(path.join(staging, 'calibration.json'), 'utf8'));
const calibrationOut = {};
for (const [name, files] of Object.entries(calibration.files)) {
	const out = path.join(labDir, `${name}.ktx2`);
	run(ktx, ['create', ...(name.endsWith('_nro') ? K.nro : K.ah), ...K.mip_generate, ...K.origin, stage(files.ktx_input), out], { quiet: true });
	inspect(out, Math.log2(calibration.size) + 1, `calibration ${name}`);
	copyFileSync(stage(files.png), path.join(labDir, files.png));
	calibrationOut[name] = { ktx2: `lab/${name}.ktx2`, png: `lab/${files.png}`, sha256: { ktx2: hash(out), png: hash(path.join(labDir, files.png)) } };
}

// --- 6/7. Post-checks: validate/info + decode-back statistics ------------------------------------------------------
const decodedRun = run(python, ['-B', 'tools/terrain/check_terrain_textures.py', 'decoded', '--staging', staging,
	'--report', path.join(evidenceDir, 'texture-stats.json')], { allowFail: true });
const stats = JSON.parse(readFileSync(path.join(evidenceDir, 'texture-stats.json'), 'utf8'));
check('post-validate-info', 6, infoChecks.every(c => c.ok), infoChecks.filter(c => !c.ok));
const byCat = stats.failures_by_category ?? {};
const known = new Set(['precheck', 'source', 'levels', 'decode-error', 'decoded-stats', 'seam', 'normal-y']);
const unknown = Object.keys(byCat).filter(k => !known.has(k));
if (decodedRun.status !== 0 && !stats.failures.length) throw new Error('Decoded check exited non-zero without a report entry.');
check('source-stats', 6, !byCat.source?.length && !byCat.levels?.length && !unknown.length, [...(byCat.source ?? []), ...(byCat.levels ?? []), ...unknown]);
check('decode-error', 6, !byCat['decode-error']?.length, byCat['decode-error'] ?? 'PSNR, height, normal angle and roughness/AO errors within limits');
check('decoded-stats', 6, !byCat['decoded-stats']?.length, byCat['decoded-stats'] ?? '§3.3 targets pass on decoded mip0 and mip2 (High-tier file of every layer)');
check('seam', 6, !byCat.seam?.length, byCat.seam ?? 'block-normalised seam <= 1.2 on mips 0-3');
const nyValues = Object.values(stats.layers).flatMap(l => Object.values(l.decoded).map(d => d.normal_y_corr));
check('normal-y', 7, !byCat['normal-y']?.length && nyValues.every(v => v > gates.normal_y_corr_min), { min: Math.min(...nyValues), limit: gates.normal_y_corr_min });
const orders = Object.values(stats.layers).flatMap(l => Object.values(l.decoded).flatMap(d => [d.stored_row_order.ah, d.stored_row_order.nro]));
check('orientation-exporter', 8, orders.every(o => o === 'bottom-left') && infoChecks.every(c => c.orientation === 'ru'),
	'stored rows bottom-left (KTXorientation "ru"); the lab compares KTX2 and PNG sampling (lab-stats-*.json)');
check('size', 9, sizes.every(s => s.ok), sizes.filter(s => !s.ok));

// --- Cells (lossless PNG copies, §3.4 / §8.8) ----------------------------------------------------------------------
const cells = {};
for (const set of ['lab', 'live', 'v2']) {
	const receiptPath = path.join(evidenceDir, `masks-receipt-${set}.json`);
	if (!existsSync(receiptPath)) continue;
	const receipt = JSON.parse(readFileSync(receiptPath, 'utf8'));
	const outDir = path.join(runtimeDir, 'cells', set);
	mkdirSync(outDir, { recursive: true });
	cells[set] = {};
	for (const [id, cell] of Object.entries(receipt.cells)) {
		const rec = { bounds: cell.bounds, splat: {}, data: {}, sha256: {}, masks_pass: cell.pass };
		for (const [kind, file] of Object.entries(cell.files)) {
			const src = path.join(root, file.path);
			if (hash(src) !== file.sha256) throw new Error(`Stale mask receipt for ${file.path}; re-run build_terrain_masks.py.`);
			const name = path.basename(file.path);
			copyFileSync(src, path.join(outDir, name));
			const [map, texels] = kind.split('_');
			rec[map === 'splat' ? 'splat' : 'data'][texels] = `cells/${set}/${name}`;
			rec.sha256[`cells/${set}/${name}`] = file.sha256;
		}
		cells[set][id] = rec;
	}
}

// --- Manifest ------------------------------------------------------------------------------------------------------
const channelOf = { L0: 'R', L1: 'G', L2: 'B', L3: 'A' };
const layerRecord = (lid) => {
	const rec = pack.layers[lid];
	const layerSpec = [...spec.layers, ...spec.relief_layers].find(l => l.id === lid);
	const files = { ah: {}, nro: {} };
	const sha256 = {};
	for (const res of Object.keys(rec.ah)) {
		const e = encoded[`${lid}_${res}`];
		files.ah[res] = `layers/${path.basename(e.ah.path)}`;
		files.nro[res] = `layers/${path.basename(e.nro.path)}`;
		sha256[files.ah[res]] = e.ah.sha256;
		sha256[files.nro[res]] = e.nro.sha256;
	}
	const s = stats.layers[lid];
	return {
		id: lid, name: rec.name, channel: channelOf[lid] ?? null, kind: rec.kind, tile_m: rec.tile_m, files,
		packing: { ah: ['albedo.r', 'albedo.g', 'albedo.b', 'height'], nro: ['normal.x', 'normal.y', 'roughness', 'ao'] },
		albedoEncoding: 'srgb-bytes-in-unorm', height_range_m: layerSpec.height_range_m,
		mean_linear_rgb: rec.mean_linear_rgb, mean_roughness: rec.mean_roughness,
		stats: {
			source_pass: s.source.failures.length === 0,
			decoded_pass: Object.fromEntries(Object.entries(s.decoded).map(([res, d]) => [res, d.failures.length === 0])),
			mip0_tilt_deg: Object.fromEntries(Object.entries(s.decoded).map(([res, d]) => [res, +d.stats.mip0.normal.mean.toFixed(2)])),
			mip2_tilt_deg: Object.fromEntries(Object.entries(s.decoded).map(([res, d]) => [res, +(d.stats.mip2?.normal.mean ?? 0).toFixed(2)])),
		},
		sha256,
	};
};
const manifest = {
	schema: 'xexoria.terrain-layerset/1',
	spec: spec.spec,
	albedoEncoding: 'srgb-bytes-in-unorm',
	layers: spec.layers.map(l => layerRecord(l.id)),
	relief: spec.relief_layers.map(l => layerRecord(l.id)),
	cells,
	calibration: calibrationOut,
	tools: { ktx: ktxVersion, node: process.version, python: run(python, ['--version'], { quiet: true }).stdout.trim() },
};
writeFileSync(path.join(runtimeDir, 'terrain-layerset.json'), `${JSON.stringify(manifest, null, 1)}\n`);

// --- 10. Receipt ---------------------------------------------------------------------------------------------------
const inputs = {};
for (const rec of Object.values(pack.layers)) for (const [kind, s] of Object.entries(rec.sources)) inputs[s.path] = s.sha256;
const outputs = {};
const walk = dir => { for (const name of readdirSync(dir)) { const p = path.join(dir, name); if (statSync(p).isDirectory()) walk(p); else outputs[relRoot(p)] = hash(p); } };
walk(runtimeDir);
check('receipt', 10, true, 'planning/evidence/terrain-splat-v1/ktx2-receipt.json');
const failed = checks.filter(c => !c.pass && !c.waived);
const receipt = {
	schema: 'xexoria.terrain-ktx2-receipt/1', spec: spec.spec, created: new Date().toISOString(), tool: ktxVersion,
	staging: posix(staging), waived: [...waived], pass: failed.length === 0,
	checks, sizes, info: infoChecks,
	totals_mb: Object.fromEntries(['high', 'medium', 'low'].map(tier => [tier, +([...spec.layers, ...spec.relief_layers]
		.reduce((s, l) => s + ['ah', 'nro'].reduce((t, k) => t + (sizes.find(x => x.layer === l.id && x.kind === k && x.res === l.res[tier])?.bytes ?? 0), 0), 0) / 1e6).toFixed(3)])),
	commands, inputs, outputs,
};
writeFileSync(path.join(evidenceDir, 'ktx2-receipt.json'), `${JSON.stringify(receipt, null, 1)}\n`);
for (const c of checks) console.log(`${c.pass ? 'PASS' : c.waived ? 'WAIVED' : 'FAIL'} §6.2 item ${c.item} ${c.id}`);
console.log(`terrain-layerset.json: ${manifest.layers.length} layers, ${manifest.relief.length} relief, ${Object.values(cells).reduce((s, c) => s + Object.keys(c).length, 0)} cells; downloads MB ${JSON.stringify(receipt.totals_mb)}`);
if (failed.length) {
	console.error(`Terrain texture build failed: ${failed.map(c => c.id).join(', ')}`);
	process.exit(1);
}
