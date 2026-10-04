import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { compile } from "svelte/compiler";

const root = fileURLToPath(new URL(".", import.meta.url));
const bundle = await build({
	stdin: { contents: "import { render } from 'svelte/server'; import Character from './panels/CharacterPanel.svelte'; import Inventory from './Inventory.svelte'; import Copy from './EquipmentCopy.svelte'; import Modal from './ModalHost.svelte'; import * as panel from './panel-data'; export {panel}; export {characterScrollClearance} from './character-inventory-scroll'; export const character=p=>render(Character,{props:p}).body; export const inventory=p=>render(Inventory,{props:p}).body; export const copy=p=>render(Copy,{props:p}).body; export const modal=p=>render(Modal,{props:p}).body;", resolveDir: root, sourcefile: "character-inventory-test.js" },
	bundle: true, write: false, format: "esm", platform: "node", conditions: ["svelte"], logLevel: "silent", loader: { ".svg": "dataurl" },
	plugins: [{ name: "real-svelte-components", setup(builder) {
		builder.onLoad({ filter: /\.svelte$/ }, async args => ({ contents: compile(await readFile(args.path, "utf8"), { filename: args.path, generate: "server", runes: true }).js.code, loader: "js" }));
		builder.onLoad({ filter: /\.css$/ }, () => ({ contents: "", loader: "js" }));
	} }],
});
const view = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);
const weaponId = "f8901e2e-f131-41f2-a6c7-a00000000001", otherId = "f8901e2e-f131-41f2-a6c7-a00000000002";
const stats = { str: 19, agi: 8, vit: 6, int: 7, dex: 13, luk: 4 };
const base = { str: 10, agi: 8, vit: 6, int: 4, dex: 8, luk: 4 }, allocated = { str: 9, agi: 0, vit: 0, int: 3, dex: 5, luk: 0 };
const state = changes => ({ t: "character_state", rev: 8, name: "Traveler", handle: "traveler", level: 2, job_level: 3, atk: 73, def: 9, hp: 150, max_hp: 200, sp: 21, max_sp: 47, exp: 40, base_exp_next: 120, job_exp: 20, job_exp_next: 112, stat_points: 3, stats, gold: 150, equipment: [{ slot: "weapon", item: "frontier_blade" }], refine: { weapon: 4 }, item_instances: [{ instance_id: weaponId, def: "frontier_blade", location: "weapon", refine: 4 }], ...changes });
const character = changes => view.panel.characterPanelData(state(changes), id => id);
const commands = { allocateStat() {}, refineItem() {}, openPanel() {}, closeModal() {}, moveItemInstance() {}, selectInventoryInstance() {} };
const drawCharacter = (section, changes = {}, language = "en") => view.character({ initialSection: section, model: { language, online: true, character: character(changes), selectedInventoryInstanceId: weaponId }, commands });

test("optional server facts stay absent and confirmed totals are never reconstructed", () => {
	const snapshot = character();
	for (const key of ["vocation", "combatProfile", "magicPower", "statsBase", "statsAllocated", "equipmentBonus"]) assert.equal(snapshot[key], undefined);
	assert.equal(snapshot.attack, 73);
	assert.deepEqual(snapshot.stats, stats);
	const html = drawCharacter("status");
	assert.doesNotMatch(html, /Magic Power|MATK|MDEF|CRIT|Accuracy|Attack Speed|Flee/);
	assert.doesNotMatch(html, />Base<|>Allocated</);
	assert.match(html, /No combat effect yet/);
});

test("server breakdown, trial profile and equipment bonus project independently without mutating their source", () => {
	const input = state({ vocation: "trailblade", combat_profile: "mage_trial", magic_power: 32, stats_base: { ...base }, stats_allocated: { ...allocated }, equipment_bonus: { atk: 28, def: 5, max_hp: 20 } });
	const snapshot = view.panel.characterPanelData(input, id => id);
	assert.equal(snapshot.vocation, "trailblade"); assert.equal(snapshot.combatProfile, "mage_trial"); assert.equal(snapshot.magicPower, 32);
	assert.deepEqual(snapshot.equipmentBonus, { attack: 28, defense: 5, maxHp: 20 });
	snapshot.statsBase.str = 99; snapshot.statsAllocated.int = 99;
	assert.equal(input.stats_base.str, 10); assert.equal(input.stats_allocated.int, 3);
	const html = drawCharacter("status", { combat_profile: "mage_trial", magic_power: 32, stats_base: base, stats_allocated: allocated });
	assert.match(html, />Base</); assert.match(html, />Allocated</); assert.match(html, /Magic Power \(trial\)/);
	assert.doesNotMatch(drawCharacter("status", { combat_profile: "trailblade", magic_power: 32 }), /Magic Power \(trial\)/);
});

test("malformed optional facts are omitted instead of becoming plausible zeros", () => {
	const snapshot = character({ vocation: "<mage>", combat_profile: "unconfirmed", magic_power: NaN, stats_base: { ...base, int: Infinity }, stats_allocated: { ...allocated, agi: -1 }, equipment_bonus: { atk: 3, def: 4 } });
	for (const key of ["vocation", "combatProfile", "magicPower", "statsBase", "statsAllocated", "equipmentBonus"]) assert.equal(snapshot[key], undefined);
});

test("equipped actions retain exact physical copy/revision; inconsistent copies fail closed", () => {
	const equipment = character().equipment[0];
	assert.equal(equipment.instanceId, weaponId); assert.equal(equipment.expectedRevision, 8); assert.equal(equipment.canRefine, true);
	for (const item_instances of [[], [{ instance_id: otherId, def: "frontier_blade", location: "bag", refine: 4 }], [{ instance_id: weaponId, def: "frontier_blade", location: "weapon", refine: 3 }], [{ instance_id: "not-a-uuid", def: "frontier_blade", location: "weapon", refine: 4 }]]) {
		const row = character({ item_instances }).equipment[0];
		assert.equal(row.instanceId, undefined); assert.equal(row.canRefine, false);
	}
	assert.equal(character({ item_instances: undefined }).equipment[0].canRefine, true, "legacy snapshot presentation remains compatible");
});

test("four real tab destinations preserve identity/EXP and expose actual equipment only", () => {
	const html = drawCharacter("information", { vocation: "trailblade", combat_profile: "mage_trial" });
	assert.equal((html.match(/role="tab" /g) ?? []).length, 4);
	for (const section of ["information", "status", "equipment", "allocation"]) assert.match(html, new RegExp(`id="character-section-${section}"`));
	assert.match(html, /Base EXP/); assert.match(html, /Job EXP/); assert.match(html, /Trailblade/); assert.match(html, /Mage combat trial active/);
	const gear = drawCharacter("equipment");
	assert.match(gear, new RegExp(weaponId)); assert.match(gear, /Refine this copy/); assert.match(gear, /Store in bag/); assert.match(gear, /Nothing equipped/);
	assert.doesNotMatch(gear, /Helmet|Accessory|Shield slot/);
});

test("allocation is +1, stays disabled without points and keeps honest Thai help", () => {
	const html = drawCharacter("allocation", { stat_points: 0 }, "th");
	assert.equal((html.match(/class="small-action" disabled/g) ?? []).length, 6);
	assert.match(html, /ยังไม่มีผลต่อการต่อสู้/); assert.match(html, /ทุก 5 แต้มที่เพิ่ม/);
	assert.doesNotMatch(html, /คริติคอล|ความแม่นยำ|คืนแต้มได้<|Apply|Cancel/);
});

const bag = changes => ({ language: "en", online: true, loading: false, revision: 8, instanceMovesSupported: true, potionPending: false, potionReadyAtMs: 0, potionUnavailable: false, items: [{ slot: 0, id: "trail_potion", label: "Trail Potion", count: 2, isPotion: true, action: "use" }], pouch: [{ id: "dew_bead", label: "Dew Bead", count: 9 }], instances: [{ instanceId: weaponId, id: "frontier_blade", label: "Frontier Blade", location: "weapon", refine: 4, equipSlot: "weapon" }, { instanceId: otherId, id: "frontier_blade", label: "Frontier Blade", location: "bag", refine: 0, equipSlot: "weapon" }], ...changes });
const bagCommands = { inventoryAction() {}, moveItemInstance() {} };
test("Inventory uses shared exact-copy selection and retains potion, material and equipped states", () => {
	const html = view.inventory({ model: bag(), commands: bagCommands, selectedInstanceId: otherId });
	assert.match(html, /Equipped weapon/); assert.match(html, /Equip selected copy/); assert.match(html, new RegExp(`Copy ID[^]*${otherId}`));
	assert.match(html, /Dew Bead/); assert.match(html, /Trail Potion/); assert.match(html, />Use</);
	assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 1);
	assert.match(view.inventory({ model: bag(), commands: bagCommands, selectedInstanceId: weaponId }), /Store in bag/);
});

test("stale selection and offline actions never target a different copy", () => {
	const stale = view.inventory({ model: bag(), commands: bagCommands, selectedInstanceId: "removed-copy" });
	assert.match(stale, /No equipment selected/); assert.doesNotMatch(stale, /data-move-item-instance/);
	const offline = view.inventory({ model: bag({ online: false }), commands: bagCommands, selectedInstanceId: otherId });
	assert.match(offline.match(/<button\b[^>]*data-move-item-instance[^>]*>/)?.[0] ?? "", /\sdisabled(?:[\s=>])/);
	assert.match(offline.match(/<button\b[^>]*class="social-action[^>]*>/)?.[0] ?? "", /\sdisabled(?:[\s=>])/);
	const staleCharacter = view.character({ initialSection: "equipment", model: { language: "en", online: true, character: character(), selectedInventoryInstanceId: otherId }, commands });
	assert.match(staleCharacter, /Select an equipped copy/); assert.doesNotMatch(staleCharacter, /Refine this copy|Store in bag/);
});

test("Bag shows an unresolved shared Character operation even after same-revision data refresh", () => {
	const loaded = { status: "loaded-data", hasData: true, message: null, requestId: null };
	const model = bag();
	const props = phase => ({ view: { modal: "bag", title: "Field Bag", language: "en", online: true, resourceRefreshSupported: true, inventory: model, panels: { selectedInventoryInstanceId: weaponId }, resources: { character: { ...loaded }, inventory: { ...loaded } }, transactions: [{ resource: "character", requestId: "same-rev-stat", phase, reason: null }] }, commands: { ...bagCommands, panels: commands, closeModal() {}, refreshResource() {} } });
	for (const phase of ["submitting", "outcome-unknown"]) {
		const html = view.modal(props(phase));
		assert.match(html, new RegExp(`data-transaction-state="${phase}"`)); assert.match(html, /<fieldset disabled/);
		assert.match(html, new RegExp(weaponId)); assert.match(html, /Dew Bead/, "cached bag remains readable");
		if (phase === "outcome-unknown") assert.match(html, /Transaction outcome unknown/);
		assert.equal(model.revision, 8, "refresh does not invent a new revision or settle an intent");
	}
	const settled = view.modal(props("committed"));
	assert.match(settled, /Server confirmed the transaction/); assert.doesNotMatch(settled, /<fieldset disabled/);
});

test("shared Bag gate retains cached offline data and the independent potion-pending presentation", () => {
	const ready = { status: "loaded-data", hasData: true, message: null, requestId: null };
	const common = { modal: "bag", title: "Field Bag", language: "en", resourceRefreshSupported: true, panels: {}, transactions: [] };
	const cmd = { ...bagCommands, panels: commands, closeModal() {}, refreshResource() {} };
	const offline = view.modal({ view: { ...common, online: false, inventory: bag({ online: false }), resources: { character: { ...ready, status: "stale" }, inventory: { ...ready, status: "stale" } } }, commands: cmd });
	assert.match(offline, /<fieldset disabled/); assert.match(offline, /Dew Bead/); assert.match(offline, new RegExp(weaponId));
	const pendingPotion = view.modal({ view: { ...common, online: true, inventory: bag({ potionPending: true }), resources: { character: ready, inventory: ready } }, commands: cmd });
	assert.match(pendingPotion, /Using…/); assert.match(pendingPotion, /class="social-action[^>]*disabled/); assert.doesNotMatch(pendingPotion, /<fieldset disabled/);
});

test("sticky clearance follows wrapped tabs and restores parent styles when Character closes", () => {
	const oldObserver = globalThis.ResizeObserver, oldComputed = globalThis.getComputedStyle;
	const values = new Map([["scroll-padding-top", "5px"], ["--character-scroll-pad", "6px"], ["color", "blue"]]);
	const content = { style: { getPropertyValue: key => values.get(key) ?? "", getPropertyPriority: () => "", setProperty: (key, value) => values.set(key, value), removeProperty: key => values.delete(key) } };
	let height = 72, padding = 18, callback, disconnected = false;
	globalThis.getComputedStyle = () => ({ paddingTop: `${padding}px` });
	globalThis.ResizeObserver = class { constructor(fn) { callback = fn; } observe() {} disconnect() { disconnected = true; } };
	try {
		const lifecycle = view.characterScrollClearance({ closest: () => content, getBoundingClientRect: () => ({ height }) });
		assert.ok(parseFloat(values.get("scroll-padding-top")) > height + padding);
		height = 124; padding = 16; callback();
		assert.ok(parseFloat(values.get("scroll-padding-top")) > height + padding, "wrapped tab rows retain a clear scroll destination");
		assert.equal(values.get("--character-scroll-pad"), "16px");
		lifecycle.destroy(); assert.equal(disconnected, true);
		assert.equal(values.get("scroll-padding-top"), "5px"); assert.equal(values.get("--character-scroll-pad"), "6px"); assert.equal(values.get("color"), "blue");
		height = 200; callback(); assert.equal(values.get("scroll-padding-top"), "5px", "queued resize cannot affect the next modal");
	} finally { globalThis.ResizeObserver = oldObserver; globalThis.getComputedStyle = oldComputed; }
});

test("clearance cleanup preserves a parent style changed by another owner", () => {
	const oldObserver = globalThis.ResizeObserver, oldComputed = globalThis.getComputedStyle;
	const values = new Map();
	const content = { style: { getPropertyValue: key => values.get(key) ?? "", getPropertyPriority: () => "", setProperty: (key, value) => values.set(key, value), removeProperty: key => values.delete(key) } };
	globalThis.getComputedStyle = () => ({ paddingTop: "18px" });
	globalThis.ResizeObserver = class { observe() {} disconnect() {} };
	try {
		const lifecycle = view.characterScrollClearance({ closest: () => content, getBoundingClientRect: () => ({ height: 72 }) });
		values.set("scroll-padding-top", "200px"); lifecycle.destroy();
		assert.equal(values.get("scroll-padding-top"), "200px"); assert.equal(values.has("--character-scroll-pad"), false);
	} finally { globalThis.ResizeObserver = oldObserver; globalThis.getComputedStyle = oldComputed; }
});
