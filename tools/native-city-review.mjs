/** Frozen local QA build. No HMR, product source writes or deployment. */
import fs from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, preview, loadConfigFromFile } from '../apps/client/node_modules/vite/dist/node/index.js';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const clientRoot = path.join(projectRoot, 'apps/client');
const configFile = path.join(clientRoot, 'vite.config.ts');
const cacheRoot = path.join(projectRoot, '.harness/.cache/city-native-review');
const mode = 'city-native-review';

export function parseReviewArguments(argv) {
	const args = [...argv], command = args.shift() ?? 'help';
	let id = 'baseline-v1', port = 4173, go = false, serverOrigin = null;
	while (args.length) {
		const option = args.shift();
		if (option === '--id') id = args.shift() ?? '';
		else if (option === '--port') port = Number(args.shift());
		else if (option === '--go') go = true;
		else if (option === '--server-origin') serverOrigin = parseServerOrigin(args.shift() ?? '');
		else throw new Error(`Unknown option: ${option}`);
	}
	if (!['help', 'plan', 'build', 'verify', 'serve'].includes(command)) throw new Error('Use plan, build, verify or serve.');
	if (!/^[a-z][a-z0-9-]{0,63}$/.test(id)) throw new Error('Review ID must be a short lowercase name.');
	if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Review port must be 1024–65535.');
	return { command, id, port, go, serverOrigin };
}

function parseServerOrigin(value) {
	let url;
	try { url = new URL(value); } catch { throw new Error('Server origin must be an absolute local HTTP(S) origin.'); }
	if (!['http:', 'https:'].includes(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('Server origin must be a credential-free local HTTP(S) origin without a path/query.');
	return url.origin;
}

function safeOutput(id) {
	const outDir = path.resolve(cacheRoot, id);
	if (path.dirname(outDir) !== path.resolve(cacheRoot) || !outDir.startsWith(projectRoot + path.sep)) throw new Error('Review output must remain inside the designated project cache.');
	return outDir;
}

async function verifyCacheContainment(outDir) {
	const realProject = await fs.realpath(projectRoot);
	const realParent = await fs.realpath(path.dirname(cacheRoot));
	const relative = path.relative(realProject, realParent);
	if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Resolved cache parent is outside the intended project.');
	for (const directory of [cacheRoot, outDir]) {
		try { if ((await fs.lstat(directory)).isSymbolicLink()) throw new Error('Review cache/output must not be a symlink.'); }
		catch (error) { if (error.code !== 'ENOENT') throw error; }
	}
}

async function digestFile(file) {
	const stat = await fs.lstat(file);
	if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`Snapshot input is not a regular file: ${file}`);
	const hash = createHash('sha256');
	for await (const chunk of createReadStream(file)) hash.update(chunk);
	return { path: path.relative(projectRoot, file).replaceAll('\\', '/'), bytes: stat.size, sha256: hash.digest('hex') };
}

async function walkFiles(directory) {
	const result = [];
	for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
		const file = path.join(directory, entry.name);
		if (entry.isSymbolicLink()) throw new Error(`Snapshot directory contains a symlink: ${file}`);
		if (entry.isDirectory()) result.push(...await walkFiles(file));
		else if (entry.isFile()) result.push(file);
	}
	return result.sort();
}

async function sourceRoster() {
	const files = [...await walkFiles(path.join(clientRoot, 'src')), ...await walkFiles(path.join(clientRoot, 'public'))];
	for (const name of ['index.html', 'package.json', 'package-lock.json', 'vite.config.ts']) {
		const file = path.join(clientRoot, name);
		try { await fs.access(file); files.push(file); } catch { /* Optional lock file only. */ }
	}
	// Hash .env inputs without recording or printing their contents.
	for (const name of await fs.readdir(clientRoot)) if (/^\.env(?:\.|$)/.test(name)) files.push(path.join(clientRoot, name));
	const roster = [];
	for (const file of [...new Set(files)].sort()) roster.push(await digestFile(file));
	return roster;
}

function rosterDigest(roster) { return createHash('sha256').update(JSON.stringify(roster)).digest('hex'); }

export function resolveReviewProxy(proxy = {}, serverOrigin = null) {
	const result = {};
	const override = serverOrigin === null ? null : new URL(parseServerOrigin(serverOrigin));
	for (const [route, value] of Object.entries(proxy)) {
		if (typeof value !== 'string' && (value === null || typeof value !== 'object')) throw new Error(`Cannot seal proxy configuration for ${route}.`);
		const plain = typeof value === 'string' ? value : { ...value };
		if (typeof plain === 'object' && Object.values(plain).some(item => typeof item === 'function')) throw new Error(`Review proxy callbacks must not be serialized: ${route}.`);
		const target = typeof plain === 'string' ? plain : plain.target;
		if (typeof target !== 'string') throw new Error(`Review proxy requires a string target: ${route}.`);
		const url = new URL(target);
		if (url.username || url.password || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) throw new Error('Frozen review proxies must use credential-free local targets.');
		if (!override) { result[route] = plain; continue; }
		if (override) {
			const websocket = ['ws:', 'wss:'].includes(url.protocol) || (typeof plain === 'object' && plain.ws === true);
			url.protocol = websocket ? (override.protocol === 'https:' ? 'wss:' : 'ws:') : override.protocol;
			url.host = override.host;
		}
		result[route] = typeof plain === 'string' ? url.href.replace(/\/$/, '') : { ...plain, target: url.href.replace(/\/$/, '') };
	}
	return result;
}

async function originalConfig(command) {
	// Runner loads the original TS config without writing a bundled temporary
	// config into the product's node_modules/.vite-temp directory.
	const loaded = await loadConfigFromFile({ command, mode, isPreview: command === 'serve', isSsrBuild: false }, configFile, clientRoot, 'warn', undefined, 'runner');
	if (!loaded) throw new Error('The original client Vite config could not be loaded.');
	return loaded;
}

function inlineConfig(outDir) {
	return {
		root: clientRoot, configFile, configLoader: 'runner', mode,
		cacheDir: path.join(cacheRoot, 'vite-cache'),
		define: { 'import.meta.env.DEV': 'true', 'import.meta.env.PROD': 'false' },
		build: { outDir, emptyOutDir: false, copyPublicDir: true, watch: null },
		logLevel: 'warn',
	};
}

async function outputRoster(outDir) {
	const roster = [];
	for (const file of await walkFiles(outDir)) {
		const item = await digestFile(file);
		roster.push({ ...item, path: path.relative(outDir, file).replaceAll('\\', '/') });
	}
	return roster;
}

async function buildSnapshot(options) {
	if (!options.go) throw new Error('Build is intentionally held. Use --go only after the parent explicitly sends GO.');
	const outDir = safeOutput(options.id), receiptFile = path.join(cacheRoot, `${options.id}.receipt.json`);
	await verifyCacheContainment(outDir);
	try { await fs.access(receiptFile); throw new Error('A receipt already exists; choose a new review ID to preserve the frozen build.'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
	try { if ((await fs.readdir(outDir)).length) throw new Error('Review output is non-empty; choose a new review ID.'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
	const before = await sourceRoster(), loaded = await originalConfig('build'), proxy = resolveReviewProxy(loaded.config.server?.proxy, options.serverOrigin);
	const actualInputs = new Map();
	const inputAudit = {
		name: 'frozen-city-review-input-read-set', apply: 'build', enforce: 'pre',
		async load(id) {
			const file = id.split('?')[0];
			if (!path.isAbsolute(file) || file.includes(`${path.sep}node_modules${path.sep}`) || file.includes('/node_modules/')) return;
			try { actualInputs.set(file, await digestFile(file)); } catch (error) { if (error.code !== 'ENOENT') throw error; }
		},
	};
	await fs.mkdir(cacheRoot, { recursive: true });
	await build({ ...inlineConfig(outDir), plugins: [inputAudit] });
	const after = await sourceRoster();
	const changedSource = rosterDigest(before) !== rosterDigest(after);
	const changedReads = [];
	for (const [file, captured] of actualInputs) {
		try { if ((await digestFile(file)).sha256 !== captured.sha256) changedReads.push(captured.path); }
		catch { changedReads.push(captured.path); }
	}
	const outputs = await outputRoster(outDir);
	const index = await fs.readFile(path.join(outDir, 'index.html'), 'utf8');
	const hasHmrClient = index.includes('/@vite/client');
	const versions = {};
	for (const name of ['vite', '@babylonjs/core', '@babylonjs/loaders', 'svelte', '@sveltejs/vite-plugin-svelte']) versions[name] = JSON.parse(await fs.readFile(path.join(clientRoot, 'node_modules', name, 'package.json'), 'utf8')).version;
	const sealed = !changedSource && changedReads.length === 0 && !hasHmrClient;
	const receipt = {
		schema_version: 1, review_id: options.id, status: sealed ? 'SEALED_LOCAL_QA_BUILD' : 'UNSEALED_INPUT_CHANGED', built_at_utc: new Date().toISOString(),
		out_dir: path.relative(projectRoot, outDir).replaceAll('\\', '/'), config_file: 'apps/client/vite.config.ts', mode,
		define: { 'import.meta.env.DEV': true, 'import.meta.env.PROD': false }, versions, node_version: process.version,
		source_roster_before: before, source_roster_sha256: rosterDigest(before), source_unchanged_during_build: !changedSource,
		actual_input_read_set: [...actualInputs.values()].sort((a, b) => a.path.localeCompare(b.path)), changed_read_set_paths: changedReads,
		output_hash_roster: outputs, output_roster_sha256: rosterDigest(outputs),
		javascript_files: outputs.filter(file => /\.(?:m?js)$/.test(file.path)), glb_files: outputs.filter(file => /\.glb$/.test(file.path)),
		preview: { host: '127.0.0.1', port: options.port, strict_port: true, proxy, server_origin_override: options.serverOrigin, hmr: false },
		index_has_hmr_client: hasHmrClient,
		limitations: ['Local QA build deliberately retains authored DEV controls; it is not a production release.', 'The existing localhost Rust/backend process is proxied, not frozen by this tool. Record backend/content identity separately.', 'Native browser walking, rendering, server state and performance must be reviewed through browser tools; this tool makes no game-UI HTTP calls.', 'Do not edit sealed output files. Use a new review ID for any rebuild.'],
	};
	await fs.writeFile(receiptFile, JSON.stringify(receipt, null, 2) + '\n');
	if (!sealed) throw new Error('Build is unsealed because source inputs changed or an HMR client remained; receipt preserved, serving refused.');
	console.log(JSON.stringify({ status: receipt.status, review_id: options.id, out_dir: receipt.out_dir, source_sha256: receipt.source_roster_sha256, output_sha256: receipt.output_roster_sha256, files: outputs.length, js_files: receipt.javascript_files.length, glb_files: receipt.glb_files.length, total_bytes: outputs.reduce((sum, item) => sum + item.bytes, 0), receipt: path.relative(projectRoot, receiptFile).replaceAll('\\', '/') }));
}

async function verifySnapshot(options) {
	const outDir = safeOutput(options.id), receiptFile = path.join(cacheRoot, `${options.id}.receipt.json`);
	await verifyCacheContainment(outDir);
	const receipt = JSON.parse(await fs.readFile(receiptFile, 'utf8'));
	if (receipt.status !== 'SEALED_LOCAL_QA_BUILD' || receipt.review_id !== options.id) throw new Error('Review receipt is not sealed for the requested ID.');
	if (path.resolve(projectRoot, receipt.out_dir) !== outDir) throw new Error('Receipt output path does not match its designated review directory.');
	const current = await outputRoster(outDir);
	if (rosterDigest(current) !== receipt.output_roster_sha256 || JSON.stringify(current) !== JSON.stringify(receipt.output_hash_roster)) throw new Error('Frozen review output bytes changed; serving refused.');
	return { receipt, outDir };
}

async function serveSnapshot(options) {
	const { receipt, outDir } = await verifySnapshot(options);
	const serverOrigin = options.serverOrigin ?? receipt.preview.server_origin_override ?? null;
	const proxy = resolveReviewProxy(receipt.preview.proxy, serverOrigin);
	const server = await preview({ ...inlineConfig(outDir), preview: { host: '127.0.0.1', port: options.port, strictPort: true, open: false, proxy } });
	const started = new Date().toISOString();
	const serveReceipt = { schema_version: 1, status: 'SERVING_SEALED_LOCAL_QA_BUILD', review_id: options.id, started_at_utc: started, url: `http://127.0.0.1:${options.port}/`, output_roster_sha256: receipt.output_roster_sha256, server_origin_override: serverOrigin, proxy, hmr: false };
	const serveReceiptFile = path.join(cacheRoot, `${options.id}.serve-${started.replace(/\D/g, '')}.json`);
	try { await fs.writeFile(serveReceiptFile, JSON.stringify(serveReceipt, null, 2) + '\n', { flag: 'wx' }); }
	catch (error) { await server.close(); throw error; }
	console.log(JSON.stringify({ ...serveReceipt, proxy: undefined, proxy_routes: Object.keys(proxy), receipt: path.relative(projectRoot, serveReceiptFile).replaceAll('\\', '/') }));
	const stop = async () => { await server.close(); process.exitCode = 0; };
	process.once('SIGINT', stop); process.once('SIGTERM', stop);
}

async function main() {
	const options = parseReviewArguments(process.argv.slice(2));
	if (options.command === 'help') {
		console.log('Local frozen QA: plan | build --go | verify | serve [--id baseline-v1] [--port 4173] [--server-origin http://127.0.0.1:3917]. Build waits for parent GO. Each rebuild uses a fresh ID.');
	} else if (options.command === 'plan') {
		const loaded = await originalConfig('build');
		console.log(JSON.stringify({ status: 'PREPARED_NOT_BUILT', review_id: options.id, out_dir: path.relative(projectRoot, safeOutput(options.id)).replaceAll('\\', '/'), config_file: 'apps/client/vite.config.ts', define_dev: true, host: '127.0.0.1', port: options.port, server_origin_override: options.serverOrigin, proxy: resolveReviewProxy(loaded.config.server?.proxy, options.serverOrigin), destructive_cleanup: false, product_dist_write: false, requires_parent_go: true }));
	} else if (options.command === 'build') await buildSnapshot(options);
	else if (options.command === 'serve') await serveSnapshot(options);
	else {
		const { receipt } = await verifySnapshot(options);
		console.log(JSON.stringify({ status: 'VERIFIED_SEALED_LOCAL_QA_BUILD', review_id: options.id, output_sha256: receipt.output_roster_sha256, files: receipt.output_hash_roster.length }));
	}
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(error => { console.error(error.message); process.exitCode = 1; });
