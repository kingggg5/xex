/**
 * Room/channel picker: GET /rooms list rendering, the /session/channel switch
 * helper, and localStorage persistence for the login gate.
 *
 * Contract (server, built in parallel):
 * - GET /rooms → {"rooms":[{"channel":0,"players":12,"capacity":50}, … 20
 *   entries]} (404/503 are possible while the server is still booting).
 * - POST /session/channel {"channel":7} or {"channel":null} (auto) → 204, or
 *   400 "unknown_channel". The choice persists on the session server-side.
 *
 * Every payload is parsed defensively: a missing or malformed room list
 * degrades to an Auto-only picker instead of breaking the login gate or the
 * settings panel. Rendering only — applying a pick in-game flows through the
 * GameHud onChannelPicked hook (the integrator POSTs + reconnects); the login
 * gate and switchChannel() talk to /session/channel directly.
 */

import { parseStoredChannel } from "./login-gate.mjs";

export interface RoomRow {
	channel: number;
	players: number;
	capacity: number;
}

/** Room list + current channel, as GameHud.setChannelState() stores it. */
export interface ChannelState {
	rooms: RoomRow[] | null;
	current: number | null;
}

export type ChannelPickListener = (channel: number | null) => void;

export const CHANNEL_STORAGE_KEY = "aetherfield_channel";

const MAX_CHANNEL_ID = 65535;
const MAX_ROOMS = 64;

// D-06 convention (login.ts / settings.ts): Thai copy when the browser language is Thai.
const THAI = typeof navigator === "undefined" ? false : navigator.language.toLowerCase().startsWith("th");

interface CopyTable {
	auto: string;
	autoNote: string;
	roomLabel(channel: number): string;
	full: string;
	loading: string;
	unavailable: string;
	empty: string;
	pickNote: string;
}

const EN: CopyTable = {
	auto: "Auto",
	autoNote: "Let the server choose",
	roomLabel: (channel) => `Room ${channel + 1}`,
	full: "FULL",
	loading: "Loading rooms…",
	unavailable: "The room list is unavailable right now — Auto still works.",
	empty: "No rooms are open right now — Auto still works.",
	pickNote: "Picking a room reconnects you into that channel.",
};

const TH: CopyTable = {
	auto: "อัตโนมัติ",
	autoNote: "ให้เซิร์ฟเวอร์เลือกห้อง",
	roomLabel: (channel) => `ห้อง ${channel + 1}`,
	full: "เต็ม",
	loading: "กำลังโหลดรายชื่อห้อง…",
	unavailable: "ยังดูรายชื่อห้องไม่ได้ แต่เลือกแบบอัตโนมัติได้ตามปกติ",
	empty: "ขณะนี้ยังไม่มีห้องเปิด แต่เลือกแบบอัตโนมัติได้ตามปกติ",
	pickNote: "เมื่อเลือกห้อง ระบบจะเชื่อมต่อใหม่เข้าช่องทางนั้นให้",
};

const COPY = THAI ? TH : EN;

/** GET /rooms, parsed defensively; null when the server is unreachable or booting. */
export async function fetchRooms(): Promise<RoomRow[] | null> {
	const response = await fetch("/rooms", { cache: "no-store", credentials: "same-origin" }).catch(() => null);
	if (!response?.ok) return null;
	const body: unknown = await response.json().catch(() => null);
	return parseRooms(body);
}

/** Validates a /rooms body; null when the shape is wrong (never throws). */
export function parseRooms(body: unknown): RoomRow[] | null {
	if (typeof body !== "object" || body === null) return null;
	const rooms = (body as { rooms?: unknown }).rooms;
	if (!Array.isArray(rooms)) return null;
	return rooms.filter(isRoomRow).slice(0, MAX_ROOMS);
}

export function isRoomRow(value: unknown): value is RoomRow {
	if (typeof value !== "object" || value === null) return false;
	const row = value as { channel?: unknown; players?: unknown; capacity?: unknown };
	const players = row.players;
	const capacity = row.capacity;
	return isChannelId(row.channel)
		&& typeof players === "number" && Number.isSafeInteger(players) && players >= 0
		&& typeof capacity === "number" && Number.isSafeInteger(capacity) && capacity > 0;
}

export function isChannelId(value: unknown): value is number {
	return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= MAX_CHANNEL_ID;
}

/**
 * Compact Auto + room grid. `current` (null = auto) is highlighted; picks are
 * reported through `onPick` (nothing is sent to the server here).
 *
 * When `rooms` is omitted the picker renders Auto-first and fills itself in
 * from GET /rooms once; a slow or failing /rooms then just leaves the Auto
 * option plus a status note. Passing null explicitly renders the Auto-only
 * "unavailable" state without fetching.
 */
export function renderChannelPicker(
	container: HTMLElement,
	current: number | null,
	onPick: ChannelPickListener,
	rooms?: RoomRow[] | null,
	language?: "en" | "th",
): void {
	const copy = language === "th" ? TH : language === "en" ? EN : COPY;
	if (rooms === undefined) {
		renderPicker(container, current, onPick, null, "loading", copy);
		void fetchRooms().then((rows) => {
			if (!container.isConnected) return;
			renderPicker(container, current, onPick, rows, rows === null ? "unavailable" : "ready", copy);
		});
		return;
	}
	renderPicker(container, current, onPick, rooms, rooms === null ? "unavailable" : "ready", copy);
}

/** Bilingual one-liner describing what picking a room does (Settings note). */
export function channelPickerNote(): string {
	return COPY.pickNote;
}

type PickerStatus = "ready" | "loading" | "unavailable";

function renderPicker(
	container: HTMLElement,
	current: number | null,
	onPick: ChannelPickListener,
	rooms: RoomRow[] | null,
	status: PickerStatus,
	copy: CopyTable,
): void {
	container.replaceChildren();
	const grid = document.createElement("div");
	grid.className = "channel-picker";
	const active = isChannelId(current) ? current : null;
	grid.append(channelButton(null, active, onPick, null, copy));
	if (status !== "ready") {
		grid.append(pickerNote(status === "loading" ? copy.loading : copy.unavailable));
	} else if (rooms !== null && rooms.length === 0) {
		grid.append(pickerNote(copy.empty));
	} else if (rooms !== null) {
		for (const room of rooms) grid.append(channelButton(room.channel, active, onPick, room, copy));
	}
	container.append(grid);
}

function channelButton(
	channel: number | null,
	current: number | null,
	onPick: ChannelPickListener,
	room: RoomRow | null,
	copy: CopyTable,
): HTMLButtonElement {
	const button = document.createElement("button");
	button.type = "button";
	const isCurrent = channel === current;
	button.className = `channel-row${channel === null ? " channel-auto" : ""}${isCurrent ? " is-current" : ""}`;
	button.setAttribute("aria-pressed", isCurrent ? "true" : "false");
	const name = document.createElement("b");
	name.textContent = channel === null ? copy.auto : copy.roomLabel(channel);
	const right = document.createElement("span");
	right.className = "channel-right";
	if (room === null) {
		const note = document.createElement("small");
		note.textContent = copy.autoNote;
		right.append(note);
	} else {
		const count = document.createElement("small");
		count.textContent = `${room.players}/${room.capacity}`;
		right.append(count);
		if (room.players >= room.capacity) {
			const badge = document.createElement("span");
			badge.className = "room-full-badge";
			badge.textContent = copy.full;
			right.append(badge);
		}
	}
	button.append(name, right);
	button.addEventListener("click", () => onPick(channel));
	return button;
}

function pickerNote(text: string): HTMLElement {
	const note = document.createElement("p");
	note.className = "channel-picker-note";
	note.textContent = text;
	return note;
}

/** Last stored channel choice (localStorage "aetherfield_channel"); null = auto. */
export function loadStoredChannel(): number | null {
	const storage = safeStorage();
	if (!storage) return null;
	const raw = storage.getItem(CHANNEL_STORAGE_KEY);
	if (raw === null) return null;
	try {
		return parseStoredChannel(JSON.parse(raw));
	} catch {
		return parseStoredChannel(raw);
	}
}

/** Persists the channel choice (null = auto); session-only if storage is blocked. */
export function saveStoredChannel(channel: number | null): void {
	const storage = safeStorage();
	if (!storage) return;
	try {
		storage.setItem(CHANNEL_STORAGE_KEY, JSON.stringify(isChannelId(channel) ? channel : null));
	} catch {
		// Storage may be unavailable (private browsing); the choice stays session-only.
	}
}

/**
 * INTEGRATOR HELPER: applies a channel to the live session and reloads the
 * page — the session cookie survives, so the boot flow rejoins on the new
 * channel. Returns false (without reloading) when the request failed.
 */
export async function switchChannel(channel: number | null): Promise<boolean> {
	const response = await postChannel(channel).catch(() => null);
	if (!response?.ok) return false;
	saveStoredChannel(channel);
	window.location.reload();
	return true;
}

/** Shared POST /session/channel for the login gate and switchChannel(). */
export async function postChannel(channel: number | null): Promise<Response> {
	return fetch("/session/channel", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ channel: isChannelId(channel) ? channel : null }),
		cache: "no-store",
		credentials: "same-origin",
	});
}

function safeStorage(): Storage | null {
	try {
		return typeof window === "undefined" ? null : window.localStorage;
	} catch {
		return null;
	}
}
