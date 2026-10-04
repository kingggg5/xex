import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { compile } from "svelte/compiler";

const result = await build({
	stdin: { contents: "import {render} from 'svelte/server'; import Hud from './Hud.svelte'; import Button from './HudButton.svelte'; import Item from './ItemIcon.svelte'; import {createHudSnapshot} from './hud-types'; export {createHudSnapshot}; export const hud=p=>render(Hud,{props:p}).body; export const button=p=>render(Button,{props:p}).body; export const item=p=>render(Item,{props:p}).body;", resolveDir: fileURLToPath(new URL(".", import.meta.url)), sourcefile: "mage-hud-test.js" },
	bundle: true, write: false, format: "esm", platform: "node", conditions: ["svelte"], logLevel: "silent", loader: { ".svg": "dataurl", ".css": "empty" },
	plugins: [{ name: "actual-svelte", setup(builder) { builder.onLoad({ filter: /\.svelte$/ }, async args => ({ contents: compile(await readFile(args.path, "utf8"), { filename: args.path, generate: "server", runes: true }).js.code, loader: "js" })); } }],
});
const render = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
const button = changes => render.button({ label: "Starmote Bolt", buttonClass: "skill-slot", keyText: "F", action: "attack", art: "mage-basic-art", readyAtMs: 0, cooldownDurationMs: 600, visible: true, th: false, onactivate() {}, ...changes });
const commands = { action() {}, potion() {}, context() {}, openModal() {}, questsCollapsed() {}, movement() {}, fullscreen() {} };

test("defaults retain legacy artwork and optional metadata remains absent", () => {
	const snapshot = render.createHudSnapshot("en");
	assert.equal(snapshot.modeNote, undefined); assert.deepEqual(snapshot.abilities.map(row => row.art), ["slash-art", "arc-art", "dodge-art", "guard-art"]);
	assert.ok(snapshot.abilities.every(row => row.spCost === undefined && row.rangeM === undefined && row.description === undefined));
	const html = button({ art: "slash-art", label: "ignored prototype name" });
	assert.match(html, /Attack · F/); assert.doesNotMatch(html, /data-mage-art|Starmote/);
});

test("Mage art uses supplied labels while canonical actions and keys stay unchanged", () => {
	const basic = button({ spCost: 0, rangeM: 9, description: "A pointed single-target bolt" });
	assert.match(basic, /data-action="attack"/); assert.match(basic, /Starmote Bolt · F/); assert.match(basic, /data-mage-art="mage-basic-art"/); assert.match(basic, /0 SP · Range 9 m/);
	assert.doesNotMatch(basic, /Attack · F/);
	const lance = button({ label: "Star Lance", action: "arc_slash", keyText: "1", art: "mage-lance-art", spCost: 8, rangeM: 11 });
	assert.match(lance, /data-action="arc_slash"/); assert.match(lance, /Star Lance · 1/); assert.match(lance, /data-mage-art="mage-lance-art"/); assert.match(lance, /8 SP · Range 11 m/);
	assert.doesNotMatch(lance, /Arc Slash · 1/);
});

test("cooldown, disabled and pending tooltips retain supplied facts in Thai and English", () => {
	const cooling = button({ readyAtMs: 2000, cooldownDurationMs: 5000, spCost: 8, rangeM: 11 });
	assert.match(cooling, /Ready in 2s/); assert.match(cooling, /8 SP · Range 11 m/); assert.match(cooling, /disabled=""/);
	const disabled = button({ disabled: true, spCost: 0, rangeM: 9 });
	assert.match(disabled, /Unavailable/); assert.match(disabled, /0 SP/);
	const pending = button({ label: "หอกดารา", action: "arc_slash", art: "mage-lance-art", th: true, pending: true, spCost: 8, rangeM: 11 });
	assert.match(pending, /หอกดารา · กำลังใช้/); assert.match(pending, /8 SP · ระยะ 11 ม\./);
	const malformed = button({ description: "<script>bad</script>", rangeM: Infinity, spCost: NaN });
	assert.match(malformed, /&lt;script>/); assert.doesNotMatch(malformed, /<script>bad|Infinity|NaN/);
});

test("desktop and mobile rendering forward both artworks and mode note without overwriting session warning", () => {
	const view = render.createHudSnapshot("en");
	view.sessionNote = "Session progress resets"; view.modeNote = "Mage trial · waiting for server";
	view.abilities[0] = { ...view.abilities[0], label: "Starmote Bolt", art: "mage-basic-art", spCost: 0, rangeM: 9, disabled: true };
	view.abilities[1] = { ...view.abilities[1], label: "Star Lance", art: "mage-lance-art", spCost: 8, rangeM: 11, disabled: true };
	const html = render.hud({ view, commands });
	assert.equal((html.match(/data-mage-art="mage-basic-art"/g) ?? []).length, 2);
	assert.equal((html.match(/data-mage-art="mage-lance-art"/g) ?? []).length, 2);
	assert.match(html, /Session progress resets/); assert.match(html, /hud-mode-note[^]*Mage trial · waiting for server/);
	assert.doesNotMatch(render.hud({ view: render.createHudSnapshot("en"), commands }), /class="hud-mode-note/);
});

test("real arcane focus gets its own staff silhouette and assets contain no script/filter/external images", async () => {
	const focus = render.item({ kind: "weapon", item: "arcane_focus" });
	const blade = render.item({ kind: "weapon", item: "frontier_blade" });
	assert.notEqual(focus, blade); assert.match(focus, /17 42 12-27/);
	for (const name of ["basic", "lance"]) {
		const svg = await readFile(new URL(`../assets/ui/mage-pilot/${name}.svg`, import.meta.url), "utf8");
		assert.match(svg, /viewBox="0 0 48 48"/); assert.doesNotMatch(svg, /<(script|filter|image)|href=|<circle/i);
	}
});
