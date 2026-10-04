import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { EventEmitter } from "node:events";
import { request as httpRequest } from "node:http";
import { createSnapshotDecoder, encodeSnapshotAck, encodeJoin, ResyncRequired } from "../apps/client/src/wire.mjs";

export const websocketGuid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
export const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function toArrayBuffer(data) {
	if (data instanceof ArrayBuffer) return data;
	if (data instanceof Blob) return data.arrayBuffer();
	if (ArrayBuffer.isView(data)) return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
	throw new TypeError("server frame was not binary");
}

const socketStates = new WeakMap();
function socketState(socket) {
    let state=socketStates.get(socket);
    if(!state){state={decoder:createSnapshotDecoder(),messages:new WeakMap(),epoch:0,lastResyncAt:0};socketStates.set(socket,state);}
    return state;
}
export function decodeSocketMessage(socket,data,zoneLimit) {
    const state=socketState(socket);const bounds=zoneLimit??state.zoneLimit??28;state.zoneLimit=bounds;const cached=state.messages.get(data);if(cached)return cached;
    const pending=toArrayBuffer(data).then(bytes=>{
        try {
            const message=state.decoder.decode(bytes,bounds);
            if(message.type==='welcome')state.epoch=message.epoch;
            if(message.type==='snapshot'&&message.epoch)socket.send(encodeSnapshotAck(message.epoch,message.tick));
            return message;
        } catch(error) {
            if(error instanceof ResyncRequired&&state.epoch&&Date.now()-state.lastResyncAt>=500){state.lastResyncAt=Date.now();socket.send(encodeSnapshotAck(state.epoch,0n,true));}
            throw error;
        }
    });state.messages.set(data,pending);return pending;
}

export function waitForMessage(socket, accept, timeoutMs = 3000, zoneLimit) {
	return new Promise((resolve, reject) => {
		const timer = setTimeout(() => {
			socket.removeEventListener("message", onMessage);
			reject(new Error("Timed out waiting for a game-server message."));
		}, timeoutMs);
		const onMessage = async (event) => {
			let message;
			try {
				message = await decodeSocketMessage(socket,event.data,zoneLimit);
			} catch (error) {
				clearTimeout(timer);
				socket.removeEventListener("message", onMessage);
				reject(error);
				return;
			}
			if (!accept(message)) return;
			clearTimeout(timer);
			socket.removeEventListener("message", onMessage);
			resolve(message);
		};
		socket.addEventListener("message", onMessage);
	});
}

export class LocalWebSocket {
	constructor(socket, head) {
		this.socket = socket;
		this.events = new EventEmitter();
		this.buffer = Buffer.alloc(0);
		this.closed = false;
		this.closeSent = false;
		socket.on("data", (chunk) => this.consume(chunk));
		socket.on("error", (error) => {
			if (this.events.listenerCount("error") > 0) this.events.emit("error", error);
			this.markClosed();
		});
		socket.on("close", () => this.markClosed());
		if (head.length > 0) this.consume(head);
	}

	get readyState() {
		return this.closed ? 3 : 1;
	}

	addEventListener(name, listener, options = {}) {
		if (options.once) this.events.once(name, listener);
		else this.events.on(name, listener);
	}

	removeEventListener(name, listener) {
		this.events.removeListener(name, listener);
	}

	send(data) {
		let payload;
		if (data instanceof ArrayBuffer) payload = Buffer.from(data);
		else if (ArrayBuffer.isView(data)) payload = Buffer.from(data.buffer, data.byteOffset, data.byteLength);
		else throw new TypeError("client packet was not binary");
		this.sendFrame(0x2, payload);
	}

	sendFrame(opcode, payload) {
		if (this.closed) return;
		const length = payload.length;
		const extendedLengthBytes = length < 126 ? 0 : length <= 0xffff ? 2 : 8;
		const maskOffset = 2 + extendedLengthBytes;
		const frame = Buffer.alloc(maskOffset + 4 + length);
		frame[0] = 0x80 | opcode;
		if (extendedLengthBytes === 0) {
			frame[1] = 0x80 | length;
		} else if (extendedLengthBytes === 2) {
			frame[1] = 0x80 | 126;
			frame.writeUInt16BE(length, 2);
		} else {
			frame[1] = 0x80 | 127;
			frame.writeBigUInt64BE(BigInt(length), 2);
		}
		const mask = randomBytes(4);
		mask.copy(frame, maskOffset);
		for (let index = 0; index < length; index++) {
			frame[maskOffset + 4 + index] = payload[index] ^ mask[index & 3];
		}
		this.socket.write(frame);
	}

	consume(chunk) {
		this.buffer = Buffer.concat([this.buffer, chunk]);
		while (this.buffer.length >= 2) {
			const first = this.buffer[0];
			const second = this.buffer[1];
			if ((first & 0x80) === 0 || (second & 0x80) !== 0) {
				this.fail(new Error("server sent a fragmented or masked WebSocket frame"));
				return;
			}
			const opcode = first & 0x0f;
			let payloadLength = second & 0x7f;
			let offset = 2;
			if (payloadLength === 126) {
				if (this.buffer.length < 4) return;
				payloadLength = this.buffer.readUInt16BE(2);
				offset = 4;
			} else if (payloadLength === 127) {
				if (this.buffer.length < 10) return;
				const length64 = this.buffer.readBigUInt64BE(2);
				if (length64 > 16n * 1024n) {
					this.fail(new Error("server frame exceeds the smoke-client limit"));
					return;
				}
				payloadLength = Number(length64);
				offset = 10;
			}
			if (payloadLength > 16 * 1024) {
				this.fail(new Error("server frame exceeds the smoke-client limit"));
				return;
			}
			if (this.buffer.length < offset + payloadLength) return;
			const payload = this.buffer.subarray(offset, offset + payloadLength);
			this.buffer = this.buffer.subarray(offset + payloadLength);
			if (opcode === 0x2) {
				this.events.emit("message", { data: Uint8Array.from(payload) });
			} else if (opcode === 0x9) {
				this.sendFrame(0x0a, payload);
			} else if (opcode === 0x8) {
				if (!this.closeSent) {
					this.closeSent = true;
					this.sendFrame(0x8, payload);
				}
				this.socket.end();
				this.markClosed();
				return;
			} else if (opcode !== 0x0a) {
				this.fail(new Error("server sent an unsupported WebSocket frame"));
				return;
			}
		}
	}

	fail(error) {
		if (this.events.listenerCount("error") > 0) this.events.emit("error", error);
		this.socket.destroy();
		this.markClosed();
	}

	markClosed() {
		if (this.closed) return;
		this.closed = true;
		this.events.emit("close");
	}

	close(timeoutMs = 1500) {
		if (this.closed) return Promise.resolve();
		return new Promise((resolve) => {
			const timer = setTimeout(() => {
				this.socket.destroy();
				this.markClosed();
			}, timeoutMs);
			this.addEventListener("close", () => {
				clearTimeout(timer);
				resolve();
			}, { once: true });
			this.closeSent = true;
			this.sendFrame(0x8, Buffer.alloc(0));
		});
	}
}

export async function createSession(httpBase, allowedOrigin) {
	const response = await fetch(new URL("/session", httpBase), {
		method: "POST",
		headers: { Origin: allowedOrigin },
		cache: "no-store",
	});
	assert.equal(response.status, 204, "session creation must succeed for the local game origin");
	const setCookie = response.headers.get("set-cookie");
	assert.ok(setCookie?.startsWith("aetherfield_session="), "server must set an opaque session cookie");
	return setCookie.split(";")[0];
}

export async function issueJoinTicket(httpBase, allowedOrigin, cookie) {
	const response = await fetch(new URL("/session/ticket", httpBase), {
		method: "POST",
		headers: { Origin: allowedOrigin, Cookie: cookie },
		cache: "no-store",
	});
	assert.equal(response.status, 200, "ticket issuance must succeed for the owning cookie");
	const body = await response.json();
	assert.match(body.ticket, /^[0-9a-f]{64}$/, "ticket must contain 32 random bytes");
	return Uint8Array.from(Buffer.from(body.ticket, "hex"));
}

function upgradeHeaders(cookie, origin) {
	const key = randomBytes(16).toString("base64");
	const headers = {
		Connection: "Upgrade",
		Upgrade: "websocket",
		"Sec-WebSocket-Version": "13",
		"Sec-WebSocket-Key": key,
	};
	if (cookie) headers.Cookie = cookie;
	if (origin !== null) headers.Origin = origin;
	return { key, headers };
}

export function rejectedHandshakeStatus(websocketUrl, cookie, origin) {
	const { headers } = upgradeHeaders(cookie, origin);
	return new Promise((resolve, reject) => {
		const request = httpRequest({
			hostname: websocketUrl.hostname,
			port: Number(websocketUrl.port || 80),
			path: websocketUrl.pathname + websocketUrl.search,
			method: "GET",
			headers,
		});
		request.setTimeout(3000, () => request.destroy(new Error("WebSocket rejection timed out")));
		request.on("response", (response) => {
			response.resume();
			resolve(response.statusCode);
		});
		request.on("upgrade", (_response, socket) => {
			socket.destroy();
			reject(new Error("an invalid WebSocket handshake was accepted"));
		});
		request.on("error", reject);
		request.end();
	});
}

export function openAuthenticatedSocket(websocketUrl, allowedOrigin, cookie) {
	const { key, headers } = upgradeHeaders(cookie, allowedOrigin);
	return new Promise((resolve, reject) => {
		const request = httpRequest({
			hostname: websocketUrl.hostname,
			port: Number(websocketUrl.port || 80),
			path: websocketUrl.pathname + websocketUrl.search,
			method: "GET",
			headers,
		});
		request.setTimeout(3000, () => request.destroy(new Error("WebSocket upgrade timed out")));
		request.on("upgrade", (response, socket, head) => {
			const expectedAccept = createHash("sha1").update(key + websocketGuid).digest("base64");
			if (response.statusCode !== 101 || response.headers["sec-websocket-accept"] !== expectedAccept) {
				socket.destroy();
				reject(new Error("local WebSocket upgrade response was invalid"));
				return;
			}
			resolve(new LocalWebSocket(socket, head));
		});
		request.on("response", (response) => {
			response.resume();
			reject(new Error("local WebSocket upgrade was denied with HTTP " + response.statusCode));
		});
		request.on("error", reject);
		request.end();
	});
}

export async function connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, cookie, ticket, zoneLimit = 28) {
	const socket = await openAuthenticatedSocket(websocketUrl, allowedOrigin, cookie);
	socket.addEventListener("message",event=>{decodeSocketMessage(socket,event.data,zoneLimit).catch(()=>{});});
	const welcomePromise = waitForMessage(socket, (message) => message.type === "welcome" || message.type === "error", 3000, zoneLimit);
	socket.send(encodeJoin(ticket));
	const welcome = await welcomePromise;
	return { socket, welcome, sequence: 0, sessionCookie: cookie };
}

export function waitForSocketClose(socket, timeoutMs = 3000) {
	return new Promise((resolve, reject) => {
		const timer = setTimeout(() => {
			socket.removeEventListener("close", onClose);
			reject(new Error("Timed out waiting for a game socket to close."));
		}, timeoutMs);
		const onClose = () => {
			clearTimeout(timer);
			resolve();
		};
		socket.addEventListener("close", onClose, { once: true });
	});
}
