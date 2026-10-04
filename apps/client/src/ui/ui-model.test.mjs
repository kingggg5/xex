import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const scriptUrl = (source) => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const compile = async (name) => ts.transpileModule(await readFile(new URL(name, import.meta.url), "utf8"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const resourceUrl = scriptUrl(await compile("./resource.ts"));
const resource = await import(resourceUrl);
const catalog = await import(scriptUrl((await compile("./store-data.ts")).replace('from "./resource"', `from "${resourceUrl}"`)));
const communityUrl = scriptUrl(await compile("../community.ts"));
const chat = await import(scriptUrl((await compile("../chat.ts")).replace('from "./community"', `from "${communityUrl}"`).replace('from "./social-parse.mjs"', `from "${new URL("../social-parse.mjs", import.meta.url).href}"`)));
const rive = await import(scriptUrl((await compile("./rive-adapter.ts")).replace('from "./resource"', `from "${resourceUrl}"`)));

test("chat keeps server echo authoritative, locks group/system sending and bounds its primitive buffer", () => {
	const snapshots = [];
	const sent = [];
	const notices = [];
	const hud = { showToast: (text) => notices.push(text) };
	const stop = chat.subscribeChat((snapshot) => snapshots.push(snapshot));
	chat.initChat(hud, (channel, text) => sent.push({ channel, text }));
	chat.selectChatTab("room");
	const beforeSend = chat.getChatSnapshot().lines.length;
	assert.equal(chat.submitChatText(" hello "), true);
	assert.deepEqual(sent, [{ channel: "room", text: "hello" }]);
	assert.equal(chat.getChatSnapshot().lines.length, beforeSend);
	chat.selectChatTab("system");
	assert.equal(chat.submitChatText("not a server notice"), false);
	chat.selectChatTab("group");
	assert.equal(chat.submitChatText("locked"), false);
	assert.equal(notices.length, 1);
	chat.setChatGroupAvailable(true);
	assert.equal(chat.submitChatText("party"), true);
	assert.deepEqual(sent.at(-1), { channel: "group", text: "party" });
	chat.selectChatTab("megaphone");
	assert.equal(chat.submitChatText("announcement"), true);
	assert.deepEqual(sent.at(-1), {channel:"megaphone",text:"announcement"});
	chat.onChatMessage({t:"chat",channel:"megaphone",from:"Mage",text:"hello",device:"mobile"});
	assert.equal(chat.getChatSnapshot().lines.at(-1).device,"mobile");
	chat.onChatMessage({ t: "chat", channel: "room", from: "Traveler", text: "<img src=x onerror=alert(1)>" });
	assert.equal(chat.getChatSnapshot().lines.at(-1).text, "<img src=x onerror=alert(1)>");
	for (let i = 0; i < 80; i++) chat.onSystemLine(`notice ${i}`);
	const snapshot = chat.getChatSnapshot();
	assert.equal(snapshot.lines.length, 60);
	assert.equal(snapshot.lines[0].text, "notice 20");
	assert.ok(Object.isFrozen(snapshot) && Object.isFrozen(snapshot.lines));
	assert.equal(JSON.parse(JSON.stringify(snapshot)).lines.length, 60);
	assert.ok(snapshots.length > 0);
	stop();
	const previous = snapshots.length;
	chat.onSystemLine("after unsubscribe");
	assert.equal(snapshots.length, previous);
	chat.releaseChat(hud);
});

test("shop preserves authored prices and exact weighted rewards with bounded lists", async () => {
	const authored = JSON.parse(await readFile(new URL("../../public/content/bundle.json", import.meta.url), "utf8"));
	const view = catalog.parseShopCatalog(authored, "en");
	assert.ok(view);
	const box = view.boxes.find((entry) => entry.id === "meadow_box");
	assert.ok(box);
	const price = authored.economy.store.find((entry) => entry.item === "meadow_box");
	assert.equal(box.price, price.price);
	assert.equal(box.currency, price.currency);
	assert.deepEqual(box.odds.map((entry) => entry.weight), authored.economy.boxes.meadow_box.table.map((entry) => entry.weight));
	assert.ok(view.entries.every((entry) => typeof entry.label === "string" && Number.isFinite(entry.price)));
	const huge = { economy: { store: Array.from({ length: 300 }, (_, i) => ({ item: `item_${i}`, price: i, currency: "gold" })), boxes: {} } };
	assert.equal(catalog.parseShopCatalog(huge, "en").entries.length, 128);
	assert.equal(catalog.parseShopCatalog(null, "en"), null);
});

test("UI resource reader cancels an oversized chunked body", async () => {
	const original = globalThis.fetch;
	let canceled = false;
	globalThis.fetch = async () => new Response(new ReadableStream({
		start(controller) { controller.enqueue(new Uint8Array(4)); controller.enqueue(new Uint8Array(4)); },
		cancel() { canceled = true; },
	}));
	try { await assert.rejects(resource.readUiResource("/bounded", 5), /byte budget/); assert.equal(canceled, true); }
	finally { globalThis.fetch = original; }
});

test("Rive remains dormant with no asset, without requiring a browser or importing SDK", () => {
	const control = rive.mountOptionalRive({}, null);
	control.setActive(true);
	control.dispose();
	control.dispose();
});
