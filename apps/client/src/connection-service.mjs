const MAX_ROOMS = 64;
const ROOMS_BODY_BYTES = 32_768;
const SESSION_BODY_BYTES = 4_096;
const REQUEST_TIMEOUT_MS = 2_500;

const ERROR_MESSAGES = Object.freeze({
	invalid_channel: "Choose a valid channel.",
	channel_rejected: "That channel is unavailable. Refresh the list and choose again.",
	session_required: "Your session has expired. Sign in again.",
	channel_unavailable: "The server could not save your channel. Try again.",
	invalid_response: "The server returned an unexpected response. Try again.",
	network_error: "The server could not be reached. Check your connection and try again.",
	timeout: "The server took too long to respond. Try again.",
});

/** Only stable, player-safe errors cross the service boundary. */
export class ChannelSelectionError extends Error {
	constructor(code) {
		super(ERROR_MESSAGES[code] ?? ERROR_MESSAGES.network_error);
		this.name = "ChannelSelectionError";
		this.code = code;
	}
}

function aborted() {
	return new DOMException("The channel request was cancelled.", "AbortError");
}

function cleanName(value) {
	if (typeof value !== "string") return null;
	const name = value.trim();
	return name.length > 0 && name.length <= 80 && !/[\u0000-\u001f\u007f]/.test(name) ? name : null;
}

function isChannel(value) {
	return Number.isSafeInteger(value) && value >= 0 && value <= 65535;
}

/** Consume bounded bytes instead of allowing Response.json() to buffer arbitrary data. */
async function readJson(response, maxBytes, signal) {
	const declared = Number(response.headers.get("content-length"));
	if (Number.isFinite(declared) && declared > maxBytes) {
		void response.body?.cancel().catch(() => {});
		throw new ChannelSelectionError("invalid_response");
	}
	if (!response.body) throw new ChannelSelectionError("invalid_response");
	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let bytes = 0;
	let text = "";
	let complete = false;
	const cancel = () => { void reader.cancel().catch(() => {}); };
	signal.addEventListener("abort", cancel, { once: true });
	try {
		while (true) {
			if (signal.aborted) throw aborted();
			const chunk = await reader.read();
			if (chunk.done) { complete = true; break; }
			bytes += chunk.value.byteLength;
			if (bytes > maxBytes) throw new ChannelSelectionError("invalid_response");
			text += decoder.decode(chunk.value, { stream: true });
		}
		if (signal.aborted) throw aborted();
		try { return JSON.parse(text + decoder.decode()); }
		catch { throw new ChannelSelectionError("invalid_response"); }
	} finally {
		signal.removeEventListener("abort", cancel);
		if (!complete) cancel();
		reader.releaseLock();
	}
}

/** Dependencies are injectable for HTTP/cancellation tests; production uses rooms-ui's parser/storage. */
export function createChannelSelectionCore({ worldName, fetchImpl, parseRooms, saveStoredChannel, now = () => performance.now(), timeoutMs = REQUEST_TIMEOUT_MS }) {
	const fallbackName = cleanName(worldName);
	const deadlineMs = Number.isFinite(timeoutMs) && timeoutMs > 0 ? Math.min(timeoutMs, REQUEST_TIMEOUT_MS) : REQUEST_TIMEOUT_MS;
	let activeLoad = null;
	let activeApply = null;

	function begin(kind, externalSignal) {
		(kind === "load" ? activeLoad : activeApply)?.abort();
		const controller = new AbortController();
		if (kind === "load") activeLoad = controller;
		else activeApply = controller;
		const cancel = () => controller.abort();
		externalSignal?.addEventListener("abort", cancel, { once: true });
		if (externalSignal?.aborted) controller.abort();
		return {
			signal: controller.signal,
			finish() {
				externalSignal?.removeEventListener("abort", cancel);
				if (kind === "load" && activeLoad === controller) activeLoad = null;
				if (kind === "apply" && activeApply === controller) activeApply = null;
			},
		};
	}

	async function request(path, operationSignal, maxBytes, init = {}) {
		if (operationSignal.aborted) throw aborted();
		const controller = new AbortController();
		let timedOut = false;
		const cancel = () => controller.abort();
		operationSignal.addEventListener("abort", cancel, { once: true });
		const timer = setTimeout(() => { timedOut = true; controller.abort(); }, deadlineMs);
		let rejectAbort;
		const cancellation = new Promise((_, reject) => { rejectAbort = reject; });
		const onAbort = () => rejectAbort(aborted());
		controller.signal.addEventListener("abort", onAbort, { once: true });
		const started = now();
		try {
			return await Promise.race([
				(async () => {
					const response = await fetchImpl(path, { ...init, cache: "no-store", credentials: "same-origin", signal: controller.signal });
					if (controller.signal.aborted) {
						void response.body?.cancel().catch(() => {});
						throw aborted();
					}
					if (!response.ok) {
						void response.body?.cancel().catch(() => {});
						const code = response.status === 401 ? "session_required"
							: response.status === 400 || response.status === 409 ? "channel_rejected" : "channel_unavailable";
						throw new ChannelSelectionError(code);
					}
					const body = response.status === 204 ? null : await readJson(response, maxBytes, controller.signal);
					const measured = now() - started;
					return { status: response.status, body, latencyMs: Number.isFinite(measured) && measured >= 0 ? Math.round(measured) : null };
				})(),
				cancellation,
			]);
		} catch (error) {
			if (operationSignal.aborted) throw aborted();
			if (timedOut) throw new ChannelSelectionError("timeout");
			throw error instanceof ChannelSelectionError ? error : new ChannelSelectionError("network_error");
		} finally {
			clearTimeout(timer);
			operationSignal.removeEventListener("abort", cancel);
			controller.signal.removeEventListener("abort", onAbort);
			controller.abort();
		}
	}

	function validatedRooms(body) {
		const raw = body?.rooms;
		if (!Array.isArray(raw) || raw.length > MAX_ROOMS) return null;
		const parsed = parseRooms(body);
		if (!parsed || parsed.length !== raw.length || new Set(parsed.map(room => room.channel)).size !== parsed.length) return null;
		return parsed.map((room, index) => ({
			channel: room.channel,
			players: room.players,
			capacity: room.capacity,
			name: cleanName(raw[index]?.name) ?? fallbackName,
		}));
	}

	async function load(signal) {
		const operation = begin("load", signal);
		try {
			let warning = "invalid_response";
			try {
				const response = await request("/rooms", operation.signal, ROOMS_BODY_BYTES);
				const rooms = validatedRooms(response.body);
				if (rooms) {
					if (operation.signal.aborted) throw aborted();
					return { rooms, latencyMs: response.latencyMs, autoAvailable: rooms.some(room => room.players < room.capacity), warnings: [] };
				}
			} catch (error) {
				if (operation.signal.aborted) throw aborted();
				warning = error instanceof ChannelSelectionError ? error.code : "network_error";
			}
			// A missing list does not establish that Auto can join: confirm both session and world health.
			const checks = await Promise.allSettled([
				request("/session/whoami", operation.signal, SESSION_BODY_BYTES),
				request("/healthz", operation.signal, SESSION_BODY_BYTES),
			]);
			if (operation.signal.aborted) throw aborted();
			const identity = checks[0].status === "fulfilled" ? checks[0].value.body?.identity : null;
			const health = checks[1].status === "fulfilled" ? checks[1].value.body : null;
			const signedIn = identity && ["guest", "google", "discord"].includes(identity.provider)
				&& typeof identity.display_name === "string" && identity.display_name.length > 0 && identity.display_name.length <= 64;
			const healthy = health?.status === "ok" && health.world_alive === true;
			return { rooms: [], latencyMs: null, autoAvailable: Boolean(signedIn && healthy), warnings: [warning] };
		} finally { operation.finish(); }
	}

	async function apply(channel, signal) {
		if (channel !== null && !isChannel(channel)) throw new ChannelSelectionError("invalid_channel");
		const operation = begin("apply", signal);
		try {
			const response = await request("/session/channel", operation.signal, SESSION_BODY_BYTES, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ channel }),
			});
			if (response.status !== 204 && (response.status !== 200 || response.body?.channel !== channel)) {
				throw new ChannelSelectionError("invalid_response");
			}
			if (operation.signal.aborted) throw aborted();
			saveStoredChannel(channel);
		} finally { operation.finish(); }
	}

	return Object.freeze({ load, apply });
}
