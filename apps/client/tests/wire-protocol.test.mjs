import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
	PROTOCOL_VERSION,
	decodeServerMessage,
	dequantizeFacing,
	encodeAction,
	encodeCold,
	encodeInput,
	encodeJoin,
	encodePing,
	quantizeFacing,
} from "../src/wire.mjs";

const goldenFile = JSON.parse(readFileSync(new URL("../../protocol/golden-v8.json", import.meta.url), "utf8"));
const golden = new Map(goldenFile.fixtures.map((fixture) => [fixture.name, fixture.hex]));
const hex = (packet) => Buffer.from(packet).toString("hex");
const joinTicket = Uint8Array.from({ length: 32 }, (_, index) => 0xa0 + index);

test("client encoders match shared TypeScript/Rust golden packets", () => {
	assert.equal(hex(encodeJoin(joinTicket)), golden.get("join_ticket"));
	assert.equal(hex(encodeInput(1, 2, 1, -1, 0)), golden.get("input_full_axes"));
	assert.equal(hex(encodeAction(1, 3, "arc_slash", 0, 0, 41)), golden.get("action_arc_slash"));
	assert.equal(hex(encodePing(7, 123456)), golden.get("ping_basic"));
	assert.equal(hex(encodeCold({ t: "resync" })), golden.get("cold_resync"));
	assert.throws(() => encodeJoin(new Uint8Array(32)));
	assert.throws(() => encodeJoin(new Uint8Array(31)));
	assert.throws(() => encodeAction(1, 3, "arc_slash", Number.NaN, 0, 0));
	assert.throws(() => encodeCold({ t: "resync", pad: "x".repeat(600) }));
});

test("facing quantization round-trips on the circle", () => {
	assert.equal(quantizeFacing(0), 0);
	assert.throws(() => quantizeFacing(Number.NaN));
	for (const radians of [0, 1, -1, Math.PI, Math.PI * 3.25]) {
		const back = dequantizeFacing(quantizeFacing(radians));
		const expected = ((radians % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
		const distance = Math.min(Math.abs(back - expected), Math.PI * 2 - Math.abs(back - expected));
		assert.ok(distance < 0.001, `facing ${radians} lost precision`);
	}
});

test("server golden packets decode into bounded typed messages", () => {
	const welcomeBytes = Uint8Array.from(Buffer.from(golden.get("welcome_basic"), "hex"));
	const welcome = decodeServerMessage(welcomeBytes.buffer);
	// Admitted geometry/content revision; any content edit regenerates the golden welcome.
	assert.deepEqual(welcome, {
		type: "welcome",
		player_id: 2,
		epoch: 1,
		tick: 42n,
		x: 1.5,
		z: -2.25,
		zone_id: 1,
		content_hash: BigInt(`0x${goldenFile.contentHash}`),
		tick_hz: 20,
	});

	const snapshotBytes = Uint8Array.from(Buffer.from(golden.get("snapshot_one_player"), "hex"));
	const snapshot = decodeServerMessage(snapshotBytes.buffer);
	assert.deepEqual(snapshot, {
		type: "snapshot",
		tick: 42n,
		ack_seq: 7,
		own_flags: 0,
		ack_x: 1.5,
		ack_z: -2.25,
		players: [{ id: 2, x: 1.5, z: -2.25, facing: 0, hp: 80, max_hp: 100, connected: true, flags: 1, anim: 0 }],
		monsters: [],
		events: [],
	});

	const worldStateBytes = Uint8Array.from(Buffer.from(golden.get("snapshot_player_monster_event_u64"), "hex"));
	assert.deepEqual(decodeServerMessage(worldStateBytes.buffer), {
		type: "snapshot",
		tick: 42n,
		ack_seq: 7,
		own_flags: 0,
		ack_x: 1.5,
		ack_z: -2.25,
		players: [{ id: 2, x: 1.5, z: -2.25, facing: 0, hp: 80, max_hp: 100, connected: true, flags: 1, anim: 0 }],
		monsters: [{ id: 101, kind: 1, x: 3.5, z: 4, facing: 0, hp: 90, max_hp: 90, active: true, flags: 1, state: 0, ability: 0, state_ticks: 0, target_x: 3.5, target_z: 4 }],
		events: [{
			id: 9007199254740993n,
			source_kind: 0,
			source_id: 2,
			target_kind: 0,
			target_id: 101,
			action: "attack",
			amount: 28,
			flags: 1,
			world_x: 3.5,
			world_z: 4,
		}],
	});
	assert.deepEqual(decodeServerMessage(Uint8Array.from(Buffer.from(golden.get("error_room_full"), "hex")).buffer), {
		type: "error",
		code: "room_full",
	});
	assert.deepEqual(decodeServerMessage(Uint8Array.from(Buffer.from(golden.get("error_rate_limited"), "hex")).buffer), {
		type: "error",
		code: "rate_limited",
	});
	assert.deepEqual(decodeServerMessage(Uint8Array.from(Buffer.from(golden.get("action_result_accepted"), "hex")).buffer), {
		type: "action_result",
		seq: 9,
		accepted: true,
		reason: "none",
		ends_at_ms: 2460n,
	});
	assert.deepEqual(decodeServerMessage(Uint8Array.from(Buffer.from(golden.get("action_result_rejected"), "hex")).buffer), {
		type: "action_result",
		seq: 10,
		accepted: false,
		reason: "cooldown",
		ends_at_ms: 2312n,
	});
	assert.deepEqual(decodeServerMessage(Uint8Array.from(Buffer.from(golden.get("pong_basic"), "hex")).buffer), {
		type: "pong",
		nonce: 7,
		client_ms: 123456,
		server_tick: 420n,
	});
});

test("cold golden JSON parses and rejections hold", () => {
	for (const entry of goldenFile.cold_client) {
		const parsed = JSON.parse(entry.json);
		assert.equal(typeof parsed.t, "string");
		assert.equal(JSON.stringify(parsed), entry.json, `cold client ${entry.name} is not canonical`);
	}
	for (const entry of goldenFile.cold_server) {
		const parsed = JSON.parse(entry.json);
		assert.equal(typeof parsed.t, "string");
		assert.equal(JSON.stringify(parsed), entry.json, `cold server ${entry.name} is not canonical`);
	}
	assert.throws(() => encodeCold({}));
	assert.throws(() => encodeCold({ t: 42 }));
});

test("server decoder rejects malformed framing, oversized arrays, and invalid flags", () => {
	assert.throws(() => decodeServerMessage(new ArrayBuffer(5)));
	const welcome = Uint8Array.from(Buffer.from(golden.get("welcome_basic"), "hex"));
	assert.throws(() => decodeServerMessage(welcome.slice(0, -1).buffer));
	const wrongVersion = welcome.slice();
	wrongVersion[2] = 3;
	assert.throws(() => decodeServerMessage(wrongVersion.buffer));
	const v4Version = welcome.slice();
	v4Version[2] = 4;
	assert.throws(() => decodeServerMessage(v4Version.buffer));
	const v5Version = welcome.slice();
	v5Version[2] = 5;
	assert.throws(() => decodeServerMessage(v5Version.buffer));
	const wrongType = welcome.slice();
	wrongType[3] = 0x99;
	assert.throws(() => decodeServerMessage(wrongType.buffer));

	const snapshot = Uint8Array.from(Buffer.from(golden.get("snapshot_one_player"), "hex"));
	snapshot[27] = 51; // player_count exceeds the bounded zone limit
	assert.throws(() => decodeServerMessage(snapshot.buffer));
	assert.throws(() => decodeServerMessage(Uint8Array.from(Buffer.from(golden.get("snapshot_one_player"), "hex")).buffer.slice(0, 20)));

	const badResult = Uint8Array.from(Buffer.from(golden.get("action_result_accepted"), "hex"));
	badResult[11] = 9; // unknown reason code
	assert.throws(() => decodeServerMessage(badResult.buffer));
});

test("snapshot player cap is 50: a full room decodes, cap+1 is rejected", () => {
	const build = (count) => {
		const payload = new ArrayBuffer(24 + count * 20);
		const payloadView = new DataView(payload);
		payloadView.setBigUint64(0, 42n, true); // tick
		payloadView.setUint32(8, 7, true); // ack_seq
		payloadView.setUint8(12, 0); // own_flags
		payloadView.setFloat32(13, 0, true); // ack_x
		payloadView.setFloat32(17, 0, true); // ack_z
		payloadView.setUint8(21, count); // player_count
		payloadView.setUint8(22, 0); // monster_count
		payloadView.setUint8(23, 0); // event_count
		for (let i = 0; i < count; i++) {
			const base = 24 + i * 20;
			payloadView.setUint32(base, i + 1, true); // id
			payloadView.setFloat32(base + 4, 0, true); // x
			payloadView.setFloat32(base + 8, 0, true); // z
			payloadView.setUint16(base + 12, 0, true); // facing
			payloadView.setUint16(base + 14, 100, true); // hp
			payloadView.setUint16(base + 16, 100, true); // max_hp
			payloadView.setUint8(base + 18, 1); // flags: connected
			payloadView.setUint8(base + 19, 0); // anim
		}
		const packet = new ArrayBuffer(6 + payload.byteLength);
		const packetView = new DataView(packet);
		packetView.setUint16(0, 0xa731, true);
		packetView.setUint8(2, PROTOCOL_VERSION);
		packetView.setUint8(3, 0x82);
		packetView.setUint16(4, payload.byteLength, true);
		new Uint8Array(packet, 6).set(new Uint8Array(payload));
		return packet;
	};

	const full = decodeServerMessage(build(50));
	assert.equal(full.players.length, 50);
	assert.equal(full.players[49].id, 50);
	assert.equal(full.players[0].connected, true);
	assert.throws(() => decodeServerMessage(build(51)));
});

test("server decoder rejects every truncation of every valid golden packet", () => {
	for (const fixture of goldenFile.fixtures.filter((entry) => entry.direction === "server_to_client")) {
		const bytes = Uint8Array.from(Buffer.from(fixture.hex, "hex"));
		for (let length = 0; length < bytes.length; length++) {
			assert.throws(
				() => decodeServerMessage(bytes.slice(0, length).buffer),
				`${fixture.name} truncation at ${length}/${bytes.length} bytes`,
			);
		}
	}
});

test("server decoder rejects non-finite coordinates and invalid snapshot records", () => {
	const valid = Uint8Array.from(Buffer.from(golden.get("snapshot_player_monster_event_u64"), "hex"));
	const mutate = (edit) => {
		const bytes = valid.slice();
		edit(new DataView(bytes.buffer));
		return bytes.buffer;
	};

	assert.throws(() => decodeServerMessage(mutate((view) => view.setFloat32(19, Number.NaN, true))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setFloat32(23, Number.POSITIVE_INFINITY, true))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setFloat32(34, 29, true))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setUint16(44, 101, true))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setUint8(27, 51))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setUint8(54, 0))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setFloat32(78, 29, true))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setBigUint64(86, 0n, true))));
	assert.throws(() => decodeServerMessage(mutate((view) => view.setUint8(104, 255))));
});

// Room-clock deadlines use the full u64 wire width and stay fixed after decoding.
test("action results preserve absolute u64 deadlines and reject the old relative shape", () => {
	const bytes = Uint8Array.from(Buffer.from(golden.get("action_result_accepted"), "hex"));
	const view = new DataView(bytes.buffer);
	view.setBigUint64(12, 9007199254740993n, true);
	assert.equal(decodeServerMessage(bytes.buffer).ends_at_ms, 9007199254740993n);
	view.setBigUint64(12, 0n, true);
	const result = decodeServerMessage(bytes.buffer);
	assert.equal(result.ends_at_ms, 0n);
	assert.equal(Object.hasOwn(result, "cooldown_ms"), false);
	const oldShape = bytes.slice(0, 14);
	new DataView(oldShape.buffer).setUint16(4, 8, true);
	assert.throws(() => decodeServerMessage(oldShape.buffer), /payload length/);
});
