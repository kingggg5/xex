/**
 * Social slice pure helpers: chat text sanitizing plus defensive parsers for
 * the friends/group wire payloads. DOM-free so node --test can exercise them
 * directly (same pattern as login-gate.mjs).
 *
 * Contract (server, built in parallel):
 * - Client→server cold: {"t":"chat","channel":"room"|"group","text":"..."}
 *   (text ≤ 160), {"t":"friend_add"|"friend_remove","handle":...},
 *   {"t":"group_create"}, {"t":"group_join","code":"A1B2C3"}, {"t":"group_leave"}.
 * - Server→client cold: {"t":"chat","channel","from","text"},
 *   {"t":"friends","entries":[...]}, {"t":"group","group":{...}|null}.
 * - HTTP: GET /friends → {"friends":[entries]}; GET /group → {"group":...|null};
 *   GET /presence → {"players":[...]} (presence is not consumed here yet).
 * - Friend/group entries carry {"handle","name","online","channel"|"tower",
 *   "in_tower"}; every field is optional-tolerant here so an older server
 *   degrades to a plainer row instead of throwing.
 */

/** Hard cap on a single chat message, matching the server contract. */
export const CHAT_MAX_LENGTH = 160;

/** Maximum friends/group rows accepted from one payload (defensive ceiling). */
const MAX_ENTRIES = 100;

const CONTROL_CHARS = /[\u0000-\u001f\u007f-\u009f]/g;

/**
 * @typedef {{handle: string, name: string, online: boolean, channel: number|null, tower: number|null, inTower: boolean, device?: "desktop"|"mobile"}} FriendEntry
 * @typedef {{code: string, members: FriendEntry[]}} GroupInfo
 */

/**
 * Cleans free-typed chat text: strips control characters, collapses
 * whitespace, trims, and clamps to `max` code points (never splitting
 * surrogate pairs). Returns "" when nothing sendable remains.
 * @param {unknown} raw
 * @param {number} [max]
 * @returns {string}
 */
export function sanitizeChatText(raw, max = CHAT_MAX_LENGTH) {
	if (typeof raw !== "string") return "";
	const limit = Number.isSafeInteger(max) && max > 0 ? max : CHAT_MAX_LENGTH;
	const cleaned = raw.replace(CONTROL_CHARS, " ").replace(/\s+/g, " ").trim();
	if (!cleaned) return "";
	return [...cleaned].slice(0, limit).join("");
}

/**
 * Cleans a display/player name: strips control characters and clamps without
 * collapsing interior whitespace (names may contain spaces).
 * @param {unknown} raw
 * @param {number} [max]
 * @returns {string}
 */
export function sanitizeDisplayName(raw, max = 48) {
	if (typeof raw !== "string") return "";
	const limit = Number.isSafeInteger(max) && max > 0 ? max : 48;
	const cleaned = raw.replace(CONTROL_CHARS, "").trim();
	if (!cleaned) return "";
	return [...cleaned].slice(0, limit).join("");
}

/**
 * Validates a friend handle as typed by the user (2–24 letters, digits, dash
 * or underscore). Returns the trimmed handle, or "" when invalid. Case is
 * preserved — the server owns normalization.
 * @param {unknown} raw
 * @returns {string}
 */
export function sanitizeHandle(raw) {
	if (typeof raw !== "string") return "";
	const trimmed = raw.trim();
	return /^[A-Za-z0-9_-]{2,24}$/.test(trimmed) ? trimmed : "";
}

/** A group invite code is six uppercase alphanumerics ("A1B2C3"). */
export function isValidGroupCode(value) {
	return typeof value === "string" && /^[A-Z0-9]{6}$/.test(value);
}

/**
 * Validates a cold chat message; null when the shape is wrong. `from` falls
 * back to "?" and the text is sanitized before display.
 * @param {unknown} value
 * @returns {{channel: "room"|"group"|"megaphone", from: string, text: string}|null}
 */
export function parseChatMessage(value) {
	if (typeof value !== "object" || value === null) return null;
	const message = /** @type {Record<string, unknown>} */ (value);
	if (message.t !== "chat") return null;
	if (message.channel !== "room" && message.channel !== "group" && message.channel !== "megaphone") return null;
	const text = sanitizeChatText(message.text, CHAT_MAX_LENGTH);
	if (!text) return null;
	const from = sanitizeDisplayName(message.from, 48) || "?";
	return { channel: message.channel, from, text };
}

/** @param {unknown} value @returns {number|null} */
function safeChannel(value) {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= 65535 ? value : null;
}

/** @param {unknown} value @returns {number|null} */
function safeFloor(value) {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= 100000 ? value : null;
}

/**
 * Normalizes one friend/group-member row. Returns null only when neither a
 * name nor a handle is present; every other field degrades to a default.
 * @param {unknown} value
 * @returns {FriendEntry|null}
 */
export function parseFriendEntry(value) {
	if (typeof value !== "object" || value === null) return null;
	const row = /** @type {Record<string, unknown>} */ (value);
	const handle = typeof row.handle === "string" ? row.handle.replace(CONTROL_CHARS, "").trim().slice(0, 32) : "";
	const name = sanitizeDisplayName(row.name, 48) || handle;
	if (!name) return null;
	const tower = safeFloor(row.tower);
	return {
		...(row.device==="desktop"||row.device==="mobile"?{device:row.device}:{}),
		handle,
		name,
		online: row.online === true,
		channel: safeChannel(row.channel),
		tower,
		inTower: row.in_tower === true || tower !== null,
	};
}

/**
 * Parses an entries array, dropping malformed rows and capping the list.
 * @param {unknown} value
 * @returns {FriendEntry[]}
 */
export function parseFriendEntries(value) {
	if (!Array.isArray(value)) return [];
	/** @type {FriendEntry[]} */
	const out = [];
	for (const row of value) {
		const entry = parseFriendEntry(row);
		if (entry) out.push(entry);
		if (out.length >= MAX_ENTRIES) break;
	}
	return out;
}

/**
 * Validates a GET /friends body ({"friends":[...]}) or the cold
 * {"t":"friends","entries":[...]} message; null when neither array exists.
 * An empty array is valid (it clears the panel).
 * @param {unknown} body
 * @returns {FriendEntry[]|null}
 */
export function parseFriendsBody(body) {
	if (typeof body !== "object" || body === null) return null;
	const source = /** @type {Record<string, unknown>} */ (body);
	const rows = source.friends ?? source.entries;
	if (!Array.isArray(rows)) return null;
	return parseFriendEntries(rows);
}

/**
 * Parses one group object {"code","members"}; null when it carries neither a
 * code nor members (an empty group is indistinguishable from "no group").
 * @param {unknown} value
 * @returns {GroupInfo|null}
 */
export function parseGroupInfo(value) {
	if (typeof value !== "object" || value === null) return null;
	const raw = /** @type {Record<string, unknown>} */ (value);
	const code = typeof raw.code === "string" && /^[A-Z0-9]{0,6}$/.test(raw.code) ? raw.code : "";
	const members = Array.isArray(raw.members) ? parseFriendEntries(raw.members).slice(0, 16) : [];
	if (!code && members.length === 0) return null;
	return { code, members };
}

/**
 * Validates a GET /group body or the cold {"t":"group"} message. Returns
 * {"group": GroupInfo|null} so an explicit null ("left the group") is
 * distinguishable from a malformed payload (null return = ignore).
 * @param {unknown} body
 * @returns {{group: GroupInfo|null}|null}
 */
export function parseGroupBody(body) {
	if (typeof body !== "object" || body === null) return null;
	const source = /** @type {Record<string, unknown>} */ (body);
	if (!("group" in source)) return null;
	return { group: source.group === null ? null : parseGroupInfo(source.group) };
}
