import { connect, createServer } from "node:net";
import {pathToFileURL} from "node:url";

// Seeded V5-04 impairment proxy. Delay is one-way (base RTT ≈ 2× delay), with
// uniform ±jitter in each direction. FIFO scheduling preserves TCP order.
// Loss drops whole WebSocket data frames at the application layer; because the
// game uses TCP, this does not simulate IP loss followed by TCP retransmission.
// Example: node tools/delay-loss-proxy.mjs --delay-ms 50 --jitter-ms 30 --loss-pct 1 --seed 7
// Directional example: --c2s-delay-ms 1000 --s2c-delay-ms 0

const MAX_FRAME_BYTES = 16 * 1024;
const MAX_QUEUED_BYTES = 1024 * 1024;
const MAX_QUEUED_FRAMES = 4096;

function parseArgs() {
	const args = process.argv.slice(2);
	const get = (name, fallback) => {
		const index = args.indexOf(`--${name}`);
		return index >= 0 ? Number(args[index + 1]) : fallback;
	};
	const options = {
		listen: get("listen", 3002),
		target: get("target", 3001),
		delayMs: get("delay-ms", 0),
		c2sDelayMs: get("c2s-delay-ms", get("delay-ms", 0)),
		s2cDelayMs: get("s2c-delay-ms", get("delay-ms", 0)),
		jitterMs: get("jitter-ms", 0),
		lossPct: get("loss-pct", 0),
		seed: get("seed", 1),
	};
	if (!Number.isInteger(options.listen) || options.listen < 1 || options.listen > 65535
		|| !Number.isInteger(options.target) || options.target < 1 || options.target > 65535
		|| !Number.isFinite(options.c2sDelayMs) || options.c2sDelayMs < 0 || options.c2sDelayMs > 5000
		|| !Number.isFinite(options.s2cDelayMs) || options.s2cDelayMs < 0 || options.s2cDelayMs > 5000
		|| !Number.isFinite(options.jitterMs) || options.jitterMs < 0 || options.jitterMs > 1000
		|| !Number.isFinite(options.lossPct) || options.lossPct < 0 || options.lossPct > 100
		|| !Number.isInteger(options.seed)) {
		throw new Error("invalid proxy options (ports, 0–5000 ms delay, 0–1000 ms jitter, 0–100% loss, integer seed)");
	}
	return options;
}

function mulberry32(seed) {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

export class FramePipe {
	constructor(random, delayMs, jitterMs, lossPct, send, label, closePair) {
		this.random = random;
		this.delayMs = delayMs;
		this.jitterMs = jitterMs;
		this.lossProb = lossPct / 100;
		this.send = send;
		this.label = label;
		this.closePair = closePair;
		this.buffer = Buffer.alloc(0);
		this.upgraded = false;
		this.passthrough = false;
		this.forwarded = 0;
		this.dataFrames = 0;
		this.dropped = 0;
		this.queuedBytes = 0;
		this.queuedBytesPeak = 0;
		this.queuedFrames = 0;
		this.nextSendAt = 0;
		this.queue = [];
		this.timer = null;
		this.overflowed = false;
	}

	enqueue(bytes, delayMs) {
		if (this.overflowed) return false;
		if (this.queuedBytes + bytes.length > MAX_QUEUED_BYTES || this.queuedFrames >= MAX_QUEUED_FRAMES) {
			this.overflowed = true;
			this.closePair();
			return false;
		}
		const now = performance.now();
		const dueAt = Math.max(now + delayMs, this.nextSendAt + 0.01);
		this.nextSendAt = dueAt;
		this.queuedBytes += bytes.length;
		this.queuedFrames++;
		this.queuedBytesPeak = Math.max(this.queuedBytesPeak, this.queuedBytes);
		// One timer drains insertion order. Independent sub-ms timers can fire
		// out of order after rounding despite monotonic dueAt values.
		this.queue.push({bytes,dueAt});
		if(this.timer===null)this.schedule();
		return true;
	}

	schedule() {
		if(this.queue.length===0)return;
		this.timer=setTimeout(()=>{
			this.timer=null;
			while(this.queue.length>0&&this.queue[0].dueAt<=performance.now()){
				const next=this.queue.shift();this.queuedBytes-=next.bytes.length;this.queuedFrames--;this.send(next.bytes);
			}
			if(this.queue.length)this.schedule();
		},Math.max(1,Math.ceil(this.queue[0].dueAt-performance.now())));
	}

	receive(chunk) {
		if (this.passthrough) {
			const bytes = Buffer.from(chunk);
			this.forwarded++;
			this.enqueue(bytes, this.delayMs);
			return;
		}
		if (!this.upgraded) {
			this.buffer = Buffer.concat([this.buffer, chunk]);
			if (this.buffer.length > MAX_FRAME_BYTES + 18) {
				this.overflowed = true;
				this.closePair();
				return;
			}
			const end = this.buffer.indexOf("\r\n\r\n");
			if (end < 0) return;
			const head = Buffer.from(this.buffer.subarray(0, end + 4));
			const headText = head.toString("latin1");
			this.buffer = this.buffer.subarray(end + 4);
			if (/upgrade:\s*websocket/i.test(headText)) {
				this.upgraded = true;
				this.forwarded++;
				this.enqueue(head, 0);
			} else {
				this.passthrough = true;
				this.forwarded++;
				this.enqueue(head, this.delayMs);
				if (this.buffer.length > 0) {
					const rest = this.buffer;
					this.buffer = Buffer.alloc(0);
					this.receive(rest);
				}
				return;
			}
		} else {
			if (this.buffer.length + chunk.length > MAX_QUEUED_BYTES) {
				this.overflowed = true;
				this.closePair();
				return;
			}
			this.buffer = Buffer.concat([this.buffer, chunk]);
		}
		if (this.upgraded) this.pump();
	}

	pump() {
		while (this.buffer.length >= 2) {
			const first = this.buffer[0];
			const second = this.buffer[1];
			const opcode = first & 0x0f;
			const masked = (second & 0x80) !== 0;
			let length = second & 0x7f;
			let offset = 2;
			if (length === 126) {
				if (this.buffer.length < 4) return;
				length = this.buffer.readUInt16BE(2);
				offset = 4;
			} else if (length === 127) {
				if (this.buffer.length < 10) return;
				const length64 = this.buffer.readBigUInt64BE(2);
				if (length64 > BigInt(MAX_FRAME_BYTES)) {
					this.overflowed = true;
					this.closePair();
					return;
				}
				length = Number(length64);
				offset = 10;
			}
			if (length > MAX_FRAME_BYTES) {
				this.overflowed = true;
				this.closePair();
				return;
			}
			const maskBytes = masked ? 4 : 0;
			if (this.buffer.length < offset + maskBytes + length) return;
			const frameLength = offset + maskBytes + length;
			const frame = Buffer.from(this.buffer.subarray(0, frameLength));
			this.buffer = this.buffer.subarray(frameLength);
			if (opcode === 0x2 || opcode === 0x0) {
				this.dataFrames++;
				if (this.random() < this.lossProb) {
					this.dropped++;
					continue;
				}
			}
			const jitter = (this.random() * 2 - 1) * this.jitterMs;
			this.forwarded++;
			this.enqueue(frame, Math.max(0, this.delayMs + jitter));
		}
	}
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href) {
const options = parseArgs();
const random = mulberry32(options.seed);
console.log(JSON.stringify({ proxy: "up", ...options, loss_layer: "websocket_data_frame" }));

const server = createServer((client) => {
	const upstream = connect({ host: "127.0.0.1", port: options.target });
	const closePair = () => {
		if (!client.destroyed) client.destroy();
		if (!upstream.destroyed) upstream.destroy();
	};
	const toUpstream = new FramePipe(random, options.c2sDelayMs, options.jitterMs, options.lossPct, (bytes) => {
		if (!upstream.destroyed) upstream.write(bytes);
	}, "c2s", closePair);
	const toClient = new FramePipe(random, options.s2cDelayMs, options.jitterMs, options.lossPct, (bytes) => {
		if (!client.destroyed) client.write(bytes);
	}, "s2c", closePair);
	client.on("data", (chunk) => toUpstream.receive(chunk));
	upstream.on("data", (chunk) => toClient.receive(chunk));
	const report = (side) => () => {
		console.log(JSON.stringify({
			proxy: "close",
			side,
			forwarded: toUpstream.forwarded + toClient.forwarded,
			data_frames: toUpstream.dataFrames + toClient.dataFrames,
			dropped: toUpstream.dropped + toClient.dropped,
			observed_loss_pct: Number((100 * (toUpstream.dropped + toClient.dropped)
				/ Math.max(1, toUpstream.dataFrames + toClient.dataFrames)).toFixed(3)),
			queued_bytes_peak: Math.max(toUpstream.queuedBytesPeak, toClient.queuedBytesPeak),
			queue_overflow: toUpstream.overflowed || toClient.overflowed,
		}));
	};
	client.on("close", report("client"));
	upstream.on("close", report("upstream"));
	client.on("error", () => {});
	upstream.on("error", () => {});
});

server.listen(options.listen, "127.0.0.1", () => {
	console.log(JSON.stringify({ proxy: "listening", port: options.listen }));
});

}
