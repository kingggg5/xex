import { readFileSync } from "node:fs";
import { encodeInput } from "../apps/client/src/wire.mjs";

function varint(value) {
	let remaining = BigInt(value);
	const bytes = [];
	while (remaining > 0x7fn) {
		bytes.push(Number((remaining & 0x7fn) | 0x80n));
		remaining >>= 7n;
	}
	bytes.push(Number(remaining));
	return bytes;
}

function protobufField(fieldNumber, wireType, valueBytes) {
	return [...varint((fieldNumber << 3) | wireType), ...valueBytes];
}

function protobufVarint(fieldNumber, value) {
	return protobufField(fieldNumber, 0, varint(value));
}

function protobufSInt32(fieldNumber, value) {
	const zigZag = value >= 0 ? value * 2 : -value * 2 - 1;
	return protobufVarint(fieldNumber, zigZag);
}

function protobufFixed32(fieldNumber, value) {
	const data = new ArrayBuffer(4);
	new DataView(data).setFloat32(0, value, true);
	return protobufField(fieldNumber, 5, [...new Uint8Array(data)]);
}

const protobufInputPayload = [
	...protobufVarint(1, 1),
	...protobufVarint(2, 2),
	...protobufSInt32(3, 32767),
	...protobufSInt32(4, -32767),
];
const protobufInputPacket = [3, 2, ...protobufInputPayload]; // version + message type; WS frame supplies message length.

const protobufPlayer = [
	...protobufVarint(1, 2),
	...protobufFixed32(2, 1.5),
	...protobufFixed32(3, -2.25),
	...protobufVarint(4, 80),
	...protobufVarint(5, 100),
	...protobufVarint(6, 1),
];
const protobufSnapshot = [
	...protobufVarint(1, 42),
	...protobufField(2, 2, [...varint(protobufPlayer.length), ...protobufPlayer]),
];
const protobufSnapshotPacket = [3, 0x82, ...protobufSnapshot]; // version + message type.

const golden = JSON.parse(readFileSync(new URL("../apps/protocol/golden-v3.json", import.meta.url), "utf8"));
const snapshotHex = golden.fixtures.find((fixture) => fixture.name === "snapshot_one_player")?.hex;
if (!snapshotHex) throw new Error("snapshot golden fixture is missing");
const oldJsonInput = JSON.stringify({ type: "input", protocol: 1, epoch: 1, sequence: 2, x: 1, z: -1 });
const oldJsonSnapshot = JSON.stringify({
	type: "snapshot",
	protocol: 1,
	tick: 42,
	players: [{ id: 2, x: 1.5, z: -2.25, hp: 80, max_hp: 100, connected: true }],
	monsters: [],
	events: [],
});

const results = {
	method: "application message bytes; excludes WebSocket, TLS, and network framing",
	protobuf_candidate: "manual byte-count prototype for documented proto3 field layout; no protobuf runtime/code generator installed",
	input: {
		json_v1: Buffer.byteLength(oldJsonInput, "utf8"),
		fixed_v3: encodeInput(1, 2, 1, -1).byteLength,
		protobuf_schema_candidate: protobufInputPacket.length,
	},
	snapshot_one_player: {
		json_v1: Buffer.byteLength(oldJsonSnapshot, "utf8"),
		fixed_v3: Buffer.from(snapshotHex, "hex").length,
		protobuf_schema_candidate: protobufSnapshotPacket.length,
	},
};

process.stdout.write(JSON.stringify(results, null, 2) + "\n");
