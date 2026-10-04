// D-14 economy smoke: real session, real WebSocket cold ops against the
// local server. Usage: node tools/economy-smoke.mjs [port]
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { decodeServerMessage, encodeCold } from "../apps/client/src/wire.mjs";
import { connectAuthenticatedClient, createSession, issueJoinTicket, toArrayBuffer } from "./net-driver.mjs";

const port = Number(process.argv[2] ?? 3001);
const origin = "http://127.0.0.1:5173";
const httpBase = new URL(`http://127.0.0.1:${port}`);
const cookie = await createSession(httpBase, origin);
const ticket = await issueJoinTicket(httpBase, origin, cookie);
const client = await connectAuthenticatedClient(httpBase, new URL(`ws://127.0.0.1:${port}/ws`), origin, cookie, ticket);

const states = [];
const results = new Map();
let welcome = null;
client.socket.addEventListener("message", async (event) => {
	let message;
	try {
		message = decodeServerMessage(await toArrayBuffer(event.data));
	} catch {
		return;
	}
	if (message.type === "welcome") welcome = message;
	else if (message.type === "cold") {
		if (message.data.t === "character_state") states.push(message.data);
		else if (message.data.t === "op_result") results.set(message.data.op_id, message.data);
	}
});

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const send = (message) => client.socket.send(encodeCold(message));
const latest = () => states.at(-1);
const sendCold = async (message) => {
	send(message);
	await wait(300);
	return results.get(message.op_id);
};
const findBag = (state, item) => state.bag.find((entry) => entry.item === item)?.count ?? 0;

// connectAuthenticatedClient already joined and holds the Welcome.
assert.ok(client.welcome, "welcome received on connect");
await wait(300);
send({ t: "resync" });
await wait(500);
const first = latest();
assert.ok(first, "no character_state after resync");
assert.equal(first.gold, 250, "starting gold");
assert.equal(first.coin, 10, "starting coin");
const startGold = first.gold;

// Buy a potion: gold 250 -> 225, bag trail_potion 3 -> 4.
const buyPotion = await sendCold({ t: "store_buy", item: "trail_potion", op_id: randomUUID() });
assert.equal(buyPotion?.status, "accepted", JSON.stringify(buyPotion));
assert.equal(latest().gold, startGold - 25);
assert.equal(findBag(latest(), "trail_potion"), 4);

// Replaying the same op_id returns the cached result without a second charge.
const replayGold = latest().gold;
const replay = await sendCold({ t: "store_buy", item: "trail_potion", op_id: buyPotion.op_id });
assert.equal(replay?.status, "accepted", "replay is served from the cache");
assert.equal(latest().gold, replayGold, "replay must not double-charge");

// Buy a skin and equip it.
const buySkin = await sendCold({ t: "store_buy", item: "skin_crimson", op_id: randomUUID() });
assert.equal(buySkin?.status, "accepted", JSON.stringify(buySkin));
assert.ok(latest().owned_cosmetics.includes("skin_crimson"), "skin recorded as owned");
const equipSkin = await sendCold({ t: "cosmetics_equip", slot: "skin", id: "skin_crimson", op_id: randomUUID() });
assert.equal(equipSkin?.status, "accepted", JSON.stringify(equipSkin));
assert.equal(latest().skin, "skin_crimson");

// Buying the skin again is refused without a charge.
const goldBeforeDupe = latest().gold;
const dupe = await sendCold({ t: "store_buy", item: "skin_crimson", op_id: randomUUID() });
assert.equal(dupe?.status, "rejected", "duplicate cosmetic purchase is refused");
assert.equal(dupe?.reason, "already_owned");
assert.equal(latest().gold, goldBeforeDupe, "no charge on refusal");

// Buy a box and open it: exactly one grant family, box consumed.
const buyBox = await sendCold({ t: "store_buy", item: "meadow_box", op_id: randomUUID() });
assert.equal(buyBox?.status, "accepted", JSON.stringify(buyBox));
assert.equal(findBag(latest(), "meadow_box"), 1);
const openBox = await sendCold({ t: "box_open", item: "meadow_box", op_id: randomUUID() });
assert.equal(openBox?.status, "accepted", JSON.stringify(openBox));
assert.equal(openBox.grants.length >= 1, true, "box produced a grant");
assert.equal(findBag(latest(), "meadow_box"), 0, "box consumed");
const afterBoxGold = latest().gold;

// Opening with no box left is refused.
const emptyOpen = await sendCold({ t: "box_open", item: "meadow_box", op_id: randomUUID() });
assert.equal(emptyOpen?.status, "rejected");
assert.equal(emptyOpen?.reason, "not_owned");
assert.equal(latest().gold, afterBoxGold, "no changes on refused open");

// Buying the pet with the remaining wallet is either affordable or refused cleanly.
const petBuy = await sendCold({ t: "store_buy", item: "pet_sprout", op_id: randomUUID() });
if (petBuy?.status === "accepted") {
	const equipPet = await sendCold({ t: "cosmetics_equip", slot: "pet", id: "pet_sprout", op_id: randomUUID() });
	assert.equal(equipPet?.status, "accepted", JSON.stringify(equipPet));
	assert.equal(latest().pet, "pet_sprout");
} else {
	assert.equal(petBuy?.reason, "insufficient_funds");
}

console.log(JSON.stringify({
	ok: true,
	gold: latest().gold,
	coin: latest().coin,
	skin: latest().skin,
	pet: latest().pet,
	owned: latest().owned_cosmetics,
	box_grant: openBox.grants,
}, null, 1));
client.socket.close();
await wait(200);
process.exit(0);
