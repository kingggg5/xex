/**
 * @typedef {import("./protocol").ActionKind} ActionKind
 * @typedef {import("./protocol").ServerMessage} ServerMessage
 * @typedef {import("./protocol").PlayerSnapshot} PlayerSnapshot
 * @typedef {import("./protocol").MonsterSnapshot} MonsterSnapshot
 * @typedef {import("./protocol").CombatEvent} CombatEvent
 */

export const PROTOCOL_VERSION = 8;
import {PLAYER_ACTION_IDS, ACTION_NAMES} from './combat-actions.mjs';
export const HEADER_BYTES = 6;
export const MAX_CLIENT_PACKET_BYTES = 4096;
export const MAX_SERVER_PACKET_BYTES = 16 * 1024;

/**
 * FNV-1a-64 over raw bytes. The client hashes the fetched bundle bytes and
 * compares with `Welcome.content_hash`; the server hashes the same file.
 * @param {Uint8Array} bytes
 * @returns {bigint}
 */
export function fnv1a64(bytes) {
	let hash = 14695981039346656037n;
	const prime = 1099511628211n;
	const mask = (1n << 64n) - 1n;
	for (const byte of bytes) hash = ((hash ^ BigInt(byte)) * prime) & mask;
	return hash;
}

const MAGIC = 0xa731;
const MAX_U32 = 0xffff_ffff;
const MAX_U64 = 0xffff_ffff_ffff_ffffn;
const ZONE_LIMIT = 28;
const PROTOCOL_HARD_LIMIT = 4096;
// Worst-case snapshot: 24-byte header + 50*20B players + 64*36B monsters +
// 64*30B events = 5248B payload, well inside MAX_SERVER_PACKET_BYTES.
const MAX_PLAYERS = 50;
const MAX_MONSTERS = 64;
const MAX_EVENTS = 64;
const MAX_COLD_CLIENT_BYTES = 512;
const MAX_COLD_SERVER_BYTES = 4096;
const TAU = Math.PI * 2;

const TYPE = Object.freeze({
	join: 0x01,
	input: 0x02,
	action: 0x03,
	ping: 0x04,
	coldClient: 0x10,
	welcome: 0x81,
	snapshot: 0x82,
	error: 0x83,
	actionResult: 0x84,
	pong: 0x85,
	coldServer: 0x90,
});

const REASON_NAME = new Map([
	[0, "none"],
	[1, "cooldown"],
	[2, "out_of_range"],
	[3, "no_target"],
	[4, "dead"],
	[5, "busy"],
	[6, "not_allowed"],
	[7, "rate_limited"],
]);
const ERROR_NAME = new Map([
	[1, "protocol_mismatch"],
	[2, "malformed_packet"],
	[3, "room_full"],
	[4, "session_active"],
	[5, "session_expired"],
	[6, "invalid_join"],
	[7, "rate_limited"],
]);

function requireU32(value, name) {
	if (!Number.isInteger(value) || value <= 0 || value > MAX_U32) throw new RangeError(`${name} must be a nonzero u32`);
}

function requireCoordinate(value, name, zoneLimit = ZONE_LIMIT) {
	if (!Number.isFinite(value) || Math.abs(value) > zoneLimit) throw new RangeError(`${name} is outside the zone`);
}

function quantizeAxis(value) {
	if (!Number.isFinite(value)) throw new RangeError("movement axis must be finite");
	return Math.round(Math.max(-1, Math.min(1, value)) * 32767);
}

/** @param {number} radians */
export function quantizeFacing(radians) {
	if (!Number.isFinite(radians)) throw new RangeError("facing must be finite");
	const normalized = ((radians % TAU) + TAU) % TAU / TAU;
	return Math.round(normalized * 65535) & 0xffff;
}

/** @param {number} quantized */
export function dequantizeFacing(quantized) {
	if (!Number.isInteger(quantized) || quantized < 0 || quantized > 0xffff) throw new RangeError("quantized facing is out of range");
	return quantized / 65535 * TAU;
}

function makePacket(type, payloadBytes, writePayload) {
	if (!Number.isInteger(payloadBytes) || payloadBytes < 0 || payloadBytes > 0xffff) throw new RangeError("payload is too large");
	const totalBytes = HEADER_BYTES + payloadBytes;
	if (totalBytes > MAX_CLIENT_PACKET_BYTES) throw new RangeError("client packet exceeds limit");
	const buffer = new ArrayBuffer(totalBytes);
	const view = new DataView(buffer);
	view.setUint16(0, MAGIC, true);
	view.setUint8(2, PROTOCOL_VERSION);
	view.setUint8(3, type);
	view.setUint16(4, payloadBytes, true);
	writePayload(view);
	return buffer;
}

/** @param {Uint8Array} ticket */
export function encodeJoin(ticket) {
	if (!(ticket instanceof Uint8Array) || ticket.byteLength !== 32) throw new RangeError("join ticket must contain 32 bytes");
	if (ticket.every((byte) => byte === 0)) throw new RangeError("join ticket cannot be zero");
	return makePacket(TYPE.join, 32, (view) => {
		new Uint8Array(view.buffer, HEADER_BYTES, 32).set(ticket);
	});
}

/** @param {number} epoch @param {number} sequence @param {number} x @param {number} z @param {number} facing */
export function encodeInput(epoch, sequence, x, z, facing) {
	requireU32(epoch, "epoch");
	requireU32(sequence, "sequence");
	const qx = quantizeAxis(x);
	const qz = quantizeAxis(z);
	const qf = quantizeFacing(facing);
	return makePacket(TYPE.input, 14, (view) => {
		view.setUint32(HEADER_BYTES, epoch, true);
		view.setUint32(HEADER_BYTES + 4, sequence, true);
		view.setInt16(HEADER_BYTES + 8, qx, true);
		view.setInt16(HEADER_BYTES + 10, qz, true);
		view.setUint16(HEADER_BYTES + 12, qf, true);
	});
}

/** @param {number} epoch @param {number} sequence @param {ActionKind} action @param {number} aim @param {number} targetId @param {number} viewTick */
export function encodeAction(epoch, sequence, action, aim, targetId, viewTick) {
	requireU32(epoch, "epoch");
	requireU32(sequence, "sequence");
	const actionId = PLAYER_ACTION_IDS[action];
	if (!actionId) throw new RangeError("unsupported action");
	const aimQ = quantizeFacing(aim);
	if (!Number.isInteger(targetId) || targetId < 0 || targetId > MAX_U32) throw new RangeError("target id must be a u32");
	if (!Number.isInteger(viewTick) || viewTick < 0 || viewTick > MAX_U32) throw new RangeError("view tick must be a u32");
	return makePacket(TYPE.action, 19, (view) => {
		view.setUint32(HEADER_BYTES, epoch, true);
		view.setUint32(HEADER_BYTES + 4, sequence, true);
		view.setUint8(HEADER_BYTES + 8, actionId);
		view.setUint16(HEADER_BYTES + 9, aimQ, true);
		view.setUint32(HEADER_BYTES + 11, targetId, true);
		view.setUint32(HEADER_BYTES + 15, viewTick, true);
	});
}

/** @param {number} nonce @param {number} clientMs */
export function encodePing(nonce, clientMs) {
	if (!Number.isInteger(nonce) || nonce < 0 || nonce > MAX_U32) throw new RangeError("ping nonce must be a u32");
	if (!Number.isInteger(clientMs) || clientMs < 0 || clientMs > MAX_U32) throw new RangeError("ping client_ms must be a u32");
	return makePacket(TYPE.ping, 8, (view) => {
		view.setUint32(HEADER_BYTES, nonce, true);
		view.setUint32(HEADER_BYTES + 4, clientMs, true);
	});
}

/** @param {unknown} message */
export function encodeCold(message) {
	if (typeof message !== "object" || message === null) throw new TypeError("cold message must be an object");
	const tag = /** @type {Record<string, unknown>} */ (message).t;
	if (typeof tag !== "string" || tag.length === 0) throw new TypeError("cold message needs a string tag");
	const bytes = new TextEncoder().encode(JSON.stringify(message));
	if (bytes.length > MAX_COLD_CLIENT_BYTES) throw new RangeError("cold client payload exceeds 512 bytes");
	const buffer = new ArrayBuffer(HEADER_BYTES + bytes.length);
	const view = new DataView(buffer);
	view.setUint16(0, MAGIC, true);
	view.setUint8(2, PROTOCOL_VERSION);
	view.setUint8(3, TYPE.coldClient);
	view.setUint16(4, bytes.length, true);
	new Uint8Array(buffer, HEADER_BYTES, bytes.length).set(bytes);
	return buffer;
}

/** @param {unknown} data @param {number} [zoneLimit] zone half-extent from the content bundle (R9) @returns {ServerMessage} */
export function decodeServerMessage(data, zoneLimit = ZONE_LIMIT) {
	if (!(data instanceof ArrayBuffer)) throw new TypeError("binary WebSocket message must be an ArrayBuffer");
	if (data.byteLength < HEADER_BYTES) throw new RangeError("packet header is truncated");
	if (data.byteLength > MAX_SERVER_PACKET_BYTES) throw new RangeError("server packet exceeds limit");
	const view = new DataView(data);
	if (view.getUint16(0, true) !== MAGIC) throw new TypeError("packet magic is invalid");
	if (view.getUint8(2) !== PROTOCOL_VERSION) throw new TypeError("protocol version mismatch");
	const type = view.getUint8(3);
	const payloadBytes = view.getUint16(4, true);
	const end = HEADER_BYTES + payloadBytes;
	if (end !== data.byteLength) throw new RangeError("packet length does not match envelope");
	let offset = HEADER_BYTES;
	const need = (count) => {
		if (!Number.isInteger(count) || count < 0 || offset + count > end) throw new RangeError("packet field is truncated");
	};
	const readU8 = () => { need(1); return view.getUint8(offset++); };
	const readU16 = () => { need(2); const v = view.getUint16(offset, true); offset += 2; return v; };
	const readU32 = () => { need(4); const v = view.getUint32(offset, true); offset += 4; return v; };
	const readU64 = () => { need(8); const v = view.getBigUint64(offset, true); offset += 8; return v; };
	const readF32 = () => {
		need(4);
		const value = view.getFloat32(offset, true);
		offset += 4;
		if (!Number.isFinite(value) || Math.abs(value) > PROTOCOL_HARD_LIMIT) throw new TypeError("wire coordinate is invalid");
		requireCoordinate(value, "snapshot coordinate", zoneLimit);
		return value;
	};
	const readBoolean = () => {
		const value = readU8();
		if (value > 1) throw new TypeError("boolean field must be zero or one");
		return value === 1;
	};
	const finish = () => {
		if (offset !== end) throw new RangeError("packet has trailing bytes");
	};

	if (type === TYPE.welcome) {
		if (payloadBytes !== 35) throw new RangeError("welcome has invalid payload length");
		const playerId = readU32();
		const epoch = readU32();
		const tick = readU64();
		const x = readF32();
		const z = readF32();
		const zoneId = readU16();
		const contentHash = readU64();
		const tickHz = readU8();
		finish();
		if (playerId === 0 || epoch === 0 || playerId > MAX_U32 || epoch > MAX_U32) throw new TypeError("welcome contains invalid identifiers");
		if (tick > MAX_U64) throw new TypeError("welcome tick is invalid");
		return { type: "welcome", player_id: playerId, epoch, tick, x, z, zone_id: zoneId, content_hash: contentHash, tick_hz: tickHz };
	}

	if (type === TYPE.snapshot) {
		if (payloadBytes < 24) throw new RangeError("snapshot header is truncated");
		const tick = readU64();
		const ackSeq = readU32();
		const ownFlags = readU8();
		const ackX = readF32();
		const ackZ = readF32();
		const playerCount = readU8();
		const monsterCount = readU8();
		const eventCount = readU8();
		if (playerCount > MAX_PLAYERS || monsterCount > MAX_MONSTERS || eventCount > MAX_EVENTS) {
			throw new TypeError("snapshot counts are invalid");
		}
		const expectedBytes = 24 + playerCount * 20 + monsterCount * 36 + eventCount * 30;
		if (payloadBytes !== expectedBytes) throw new RangeError("snapshot record counts do not match payload length");
		/** @type {PlayerSnapshot[]} */
		const players = [];
		for (let i = 0; i < playerCount; i++) {
			const id = readU32();
			const x = readF32();
			const z = readF32();
			const facing = dequantizeFacing(readU16());
			const hp = readU16();
			const max_hp = readU16();
			const flags = readU8();
			const anim = readU8();
			if (id === 0 || hp > max_hp) throw new TypeError("player record is invalid");
			players.push({ id, x, z, facing, hp, max_hp, connected: (flags & 1) !== 0, flags, anim });
		}
		/** @type {MonsterSnapshot[]} */
		const monsters = [];
		const monsterIds = new Set();
		for (let i = 0; i < monsterCount; i++) {
			const id = readU32();
			const kind = readU8();
			const x = readF32();
			const z = readF32();
			const facing = dequantizeFacing(readU16());
			const hp = readU32();
			const max_hp = readU32();
			const flags = readU8();
			const state = readU8();
			const ability = readU8();
			const stateTicks = readU16();
			const targetX = readF32();
			const targetZ = readF32();
			if (id === 0 || kind === 0 || hp > max_hp || max_hp === 0 || (flags & ~7) !== 0 || monsterIds.has(id)) throw new TypeError("monster record is invalid");
			monsterIds.add(id);
			monsters.push({
				id,
				kind,
				x,
				z,
				facing,
				hp,
				max_hp,
				active: (flags & 1) !== 0,
				flags,
				state,
				ability,
				state_ticks: stateTicks,
				target_x: targetX,
				target_z: targetZ,
			});
		}
		/** @type {CombatEvent[]} */
		const events = [];
		for (let i = 0; i < eventCount; i++) {
			const id = readU64();
			const sourceKind = readU8();
			const sourceId = readU32();
			const targetKind = readU8();
			const targetId = readU32();
			const actionId = readU8();
			const action = ACTION_NAMES.get(actionId);
			const amount = readU16();
			const flags = readU8();
			const world_x = readF32();
			const world_z = readF32();
			if (id === 0n || sourceKind > 1 || targetKind > 1 || !action || sourceId === 0 || targetId === 0) throw new TypeError("combat event is invalid");
			if ((flags & ~127) !== 0 || ((flags & 64) !== 0 && (amount !== 0 || (flags & 33) !== 0)) || ((flags & 32) !== 0 && amount === 0)) throw new TypeError('combat flags contradict the outcome');
			events.push({ id, source_kind: sourceKind, source_id: sourceId, target_kind: targetKind, target_id: targetId, action, amount, flags, world_x, world_z });
		}
		finish();
		return { type: "snapshot", tick, ack_seq: ackSeq, own_flags: ownFlags, ack_x: ackX, ack_z: ackZ, players, monsters, events };
	}

	if (type === TYPE.error) {
		if (payloadBytes !== 2) throw new RangeError("error has invalid payload length");
		const code = ERROR_NAME.get(readU16());
		finish();
		if (!code) throw new TypeError("unknown server error code");
		return { type: "error", code };
	}

	if (type === TYPE.actionResult) {
		if (payloadBytes !== 14) throw new RangeError("action_result has invalid payload length");
		const seq = readU32();
		const accepted = readBoolean();
		const reason = REASON_NAME.get(readU8());
		const endsAtMs = readU64();
		finish();
		if (seq === 0 || !reason) throw new TypeError("action_result is invalid");
		return { type: "action_result", seq, accepted, reason, ends_at_ms: endsAtMs };
	}

	if (type === TYPE.pong) {
		if (payloadBytes !== 16) throw new RangeError("pong has invalid payload length");
		const nonce = readU32();
		const clientMs = readU32();
		const serverTick = readU64();
		finish();
		return { type: "pong", nonce, client_ms: clientMs, server_tick: serverTick };
	}

	if (type === TYPE.coldServer) {
		if (payloadBytes > MAX_COLD_SERVER_BYTES) throw new RangeError("cold server payload exceeds 4 KiB");
		need(payloadBytes);
		const bytes = new Uint8Array(data, offset, payloadBytes);
		offset += payloadBytes;
		finish();
		let message;
		try {
			message = JSON.parse(new TextDecoder().decode(bytes));
		} catch {
			throw new TypeError("cold server payload is not JSON");
		}
		if (typeof message !== "object" || message === null || typeof message.t !== "string") {
			throw new TypeError("cold server message needs a string tag");
		}
		return { type: "cold", tag: message.t, data: message };
	}

	throw new TypeError("unexpected server message type");
}

export {createSnapshotDecoder, encodeSnapshotAck, ResyncRequired} from "./wire-v8.mjs";
