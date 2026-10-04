import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { compile } from 'svelte/compiler';
import { createBootstrapProgress } from '../bootstrap-progress.mjs';

// Render the actual component with the repository's Svelte compiler; no browser package added.
const result = await build({
	stdin: { contents: "import {render} from 'svelte/server'; import Component from './ConnectionLobby.svelte'; export const draw = (model) => render(Component, {props:{model,refresh(){},select(){},confirm(){},retry(){}}}).body;", resolveDir: fileURLToPath(new URL('.', import.meta.url)), sourcefile: 'lobby-render-entry.js' },
	bundle: true, write: false, format: 'esm', platform: 'node', conditions: ['svelte'], logLevel: 'silent',
	plugins: [{ name: 'svelte-fixture', setup(builder) {
		builder.onLoad({ filter: /\.svelte$/ }, async args => ({ contents: compile(await readFile(args.path, 'utf8'), { filename: args.path, generate: 'server', runes: true }).js.code, loader: 'js' }));
		builder.onLoad({ filter: /\.png$/ }, () => ({ contents: 'export default "/fixture-logo.png";', loader: 'js' }));
		builder.onLoad({ filter: /fonts-v2\.css$/ }, () => ({ contents: '', loader: 'js' }));
	} }],
});
const { draw } = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
function model(overrides = {}) {
	const snapshot = createBootstrapProgress().snapshot();
	return { language: 'en', worldName: 'Verdant Frontier', mode: 'channels', rooms: [], latencyMs: null, autoAvailable: false, selected: null, hasSelection: false, loadingRooms: false, applying: false, error: '', warnings: [], canRetry: false, retrying: false, phases: [...snapshot.phases], recent: [], completed: 0, total: 8, ...overrides };
}

test('actual component renders exact occupancy, disabled full channels, display numbering and escaped names', () => {
	const html = draw(model({ rooms: [{ channel: 0, players: 52, capacity: 50, name: '<unsafe>' }, { channel: 1, players: 12, capacity: 50, name: 'Verdant Frontier' }], selected: 1, hasSelection: true, latencyMs: 38 }));
	const channelIndex = html.indexOf('data-channel="0"');
	assert.ok(channelIndex > 0);
	const fullButton = html.slice(html.lastIndexOf('<button', channelIndex), channelIndex);
	assert.match(fullButton, /class="[^\"]*\bfull\b/); assert.match(fullButton, / disabled/);
	assert.match(html, /class="channel-number[^\"]*">01/); assert.match(html, /52 <em[^>]*>\/ 50/); assert.match(html, /&lt;unsafe>/); assert.doesNotMatch(html, /<unsafe>/);
	assert.match(html, /~38 ms/); assert.match(html, /Shared server round-trip estimate/); assert.match(html, /role="dialog"/);
});

test('Auto is shown only when verified available and empty/full states cannot enter', () => {
	assert.doesNotMatch(draw(model()), /data-channel="auto"/);
	assert.match(draw(model()), /disabled[^>]*data-lobby-confirm/);
	assert.match(draw(model({ autoAvailable: true, hasSelection: true })), /data-channel="auto"/);
	assert.match(draw(model({ autoAvailable: true, hasSelection: true })), /Use automatic selection to continue/);
	assert.doesNotMatch(draw(model({ autoAvailable: true, hasSelection: true })), /No channels are available/);
	assert.match(draw(model({ rooms: [{ channel: 0, players: 50, capacity: 50, name: 'World' }] })), /All listed channels are full/);
});

test('loading counts measured phases, uses indeterminate resource progress and bounds detail history', () => {
	const progress = createBootstrapProgress();
	for (const id of ['content', 'renderer', 'codecs']) progress.update({ id, state: 'complete' });
	progress.update({ id: 'assets', state: 'active', resource: 'world.glb' });
	const snapshot = progress.snapshot();
	const html = draw(model({ mode: 'loading', phases: [...snapshot.phases], recent: [...snapshot.recent], completed: snapshot.completed }));
	assert.match(html, /aria-valuemax="8" aria-valuenow="3"/); assert.match(html, /phases complete/);
	assert.match(html, /<progress class="resource-progress[^>]*aria-label/); assert.doesNotMatch(html, /<progress[^>]*value=/);
	assert.doesNotMatch(html, /\d+%|percent|compressed|compiled/i); assert.match(html, /Preparing shaders/);
});

test('Thai error and retry remain readable and transfer counters belong to the named resource', () => {
	const html = draw(model({ language: 'th', mode: 'loading', error: 'โหลดทรัพยากรไม่ได้', canRetry: true, phases: [{ id: 'assets', state: 'active', resource: 'world.glb', loaded: 1024, total: 2048 }], recent: [{ id: 'assets', state: 'active', resource: 'world.glb', loaded: 1024, total: 2048 }] }));
	assert.match(html, /การเดินทางหยุดชั่วคราว/); assert.match(html, /data-lobby-retry/); assert.match(html, /1.0 KiB \/ 2.0 KiB/); assert.match(html, /value="1024" max="2048"/);
	assert.match(html, /หยุดการเตรียมชั่วคราว/); assert.doesNotMatch(html, /กำลังเตรียมขั้นตอนถัดไป/);
});
