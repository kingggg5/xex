import {deviceKind} from "./community";
import type {DeviceKind} from "./community";
/**
 * Live chat wiring for the EXISTING .chat panel (World / Party / System tabs).
 * GameHud calls initChat() once during construction; the integrator forwards
 * server chat into onChatMessage() and system notices into onSystemLine().
 *
 * Contract (server, built in parallel):
 * - Client→server cold: {"t":"chat","channel":"room"|"group","text":"..."}
 *   (text ≤ 160) — sending flows through the `sendChat` callback GameHud
 *   builds from its onChatSend hook; this module never touches the socket.
 * - Server→client cold: {"t":"chat","channel":"room"|"group","from":"<name>",
 *   "text":"..."} — the room channel renders as [World], the group channel as
 *   [Party] (bilingual labels).
 *
 * Tabs: World = room channel, Party = group channel (locked with a notice
 * while the player has no group), System = server notices. All lines share one
 * bounded buffer (≤ 60 lines, oldest dropped); tabs switch which kinds are
 * visible. The sender's own messages are NOT echoed locally — the server
 * broadcasts chat back to the whole room, sender included.
 */

import { CHAT_MAX_LENGTH, parseChatMessage, sanitizeChatText } from "./social-parse.mjs";

export type ChatChannel = "room" | "group" | "megaphone";

export interface ChatMessage {
	channel: ChatChannel;
	from: string;
	text: string;
}

/** Structural view of GameHud — passed directly as `hud` by the constructor. */
export interface ChatHud {
	showToast(message: string): void;
}

export type SendChat = (channel: ChatChannel, text: string) => void;

const MAX_LINES = 60;
const SYSTEM_MAX = 200;

// D-06 convention (rooms-ui / tower-ui): Thai copy when the browser language is Thai.
const THAI = typeof navigator === "undefined" ? false : navigator.language.toLowerCase().startsWith("th");

const LABEL_ROOM = THAI ? "[โลก]" : "[World]";
const LABEL_GROUP = THAI ? "[กลุ่ม]" : "[Party]";
const LABEL_SYSTEM = THAI ? "[ระบบ]" : "[System]";
const TAB_TEXT: Record<ChatChannel | "system", string> = {
	megaphone: THAI ? "โทรโข่ง" : "Megaphone",
	room: THAI ? "โลก" : "World",
	group: THAI ? "กลุ่ม" : "Party",
	system: THAI ? "ระบบ" : "System",
};
const WELCOME_LINE = THAI ? "ยินดีต้อนรับสู่แชทแฟรอนเทียร์" : "Welcome to frontier chat.";
const NOTICE_NO_GROUP = THAI
	? "คุณยังไม่ได้อยู่ในกลุ่ม — สร้างหรือเข้าร่วมกลุ่มจากแผงกลุ่มก่อน"
	: "You are not in a group yet — create or join one from the Group panel.";
const PLACEHOLDER_ROOM = THAI ? "พูดอะไรสักอย่าง…" : "Say something…";
const PLACEHOLDER_GROUP = THAI ? "แชทกลุ่ม…" : "Party chat…";
const PLACEHOLDER_LOCKED = THAI ? "เข้าร่วมกลุ่มก่อนเพื่อแชท" : "Join a group to chat here";
const PLACEHOLDER_SYSTEM = THAI ? "ระบบแจ้งเตือนเท่านั้น" : "System notices only";
const EMPTY_NOTES: Record<ChatChannel | "system", string> = {
	megaphone: THAI ? "ประกาศทุกห้องจะแสดงที่นี่" : "Server-wide announcements appear here.",
	room: THAI ? "ยังไม่มีข้อความ — ทักทายได้เลย" : "No messages yet — say hello.",
	group: THAI ? "ข้อความแชทกลุ่มจะแสดงที่นี่" : "Group chat messages will appear here.",
	system: THAI ? "การแจ้งเตือนจากระบบจะแสดงที่นี่" : "Server notices will appear here.",
};

export type ChatTab = ChatChannel | "system";
type TabKind = ChatTab;

export interface ChatLine {
	readonly device: DeviceKind;
	readonly id: number;
	readonly kind: ChatTab;
	readonly label: string;
	readonly text: string;
	readonly system: boolean;
}

export interface ChatSnapshot {
	readonly revision: number;
	readonly activeTab: ChatTab;
	readonly groupAvailable: boolean;
	readonly lines: readonly ChatLine[];
}

const subscribers = new Set<(snapshot: ChatSnapshot) => void>();
const buffer: ChatLine[] = [];
let revision = 0;
let lineId = 0;
let initialized = false;
let legacyEvents: AbortController | null = null;

export function getChatSnapshot(): ChatSnapshot {
	return Object.freeze({ revision, activeTab, groupAvailable, lines: Object.freeze([...buffer]) });
}

/** One primitive stream; a mounted Svelte consumer becomes the sole DOM writer. */
export function subscribeChat(listener: (snapshot: ChatSnapshot) => void): () => void {
	legacyEvents?.abort();
	legacyEvents = null;
	bound = false;
	inputEl = null;
	subscribers.add(listener);
	return () => subscribers.delete(listener);
}

function publish(): void {
	revision += 1;
	const snapshot = getChatSnapshot();
	for (const listener of subscribers) listener(snapshot);
}

export function selectChatTab(kind: ChatTab): void {
	if (kind !== "room" && kind !== "group" && kind !== "megaphone" && kind !== "system") return;
	selectTab(kind);
}

export function submitChatText(value: string): boolean {
	if (activeTab === "system" || value.length > CHAT_MAX_LENGTH) return false;
	const text = sanitizeChatText(value, CHAT_MAX_LENGTH);
	if (!text) return false;
	if (activeTab === "group" && !groupAvailable) {
		hud?.showToast(NOTICE_NO_GROUP);
		return false;
	}
	send(activeTab === "megaphone" ? "megaphone" : activeTab === "group" ? "group" : "room", text);
	return true;
}

/** Local preview/notices share the same bounded buffer; online sends never echo here. */
export function appendLocalChat(text: string, kind: ChatTab, from = "Eira"): void {
	const clean = sanitizeChatText(text, kind === "system" ? SYSTEM_MAX : CHAT_MAX_LENGTH);
	if (!clean) return;
	appendLine({ kind, label: kind === "system" ? LABEL_SYSTEM : `${kind === "room" ? LABEL_ROOM : LABEL_GROUP} ${sanitizeChatText(from, 64)}:`, text: clean, system: kind === "system" });
}

export function releaseChat(chatHud: ChatHud): void {
	if (hud !== chatHud) return;
	hud = null;
	send = () => {};
	legacyEvents?.abort();
	legacyEvents = null;
	inputEl = null;
	bound = false;
}

let hud: ChatHud | null = null;
let send: SendChat = () => {};
let bound = false;
let activeTab: TabKind = "room";
let groupAvailable = false;
let groupNoticeShown = false;
let inputEl: HTMLInputElement | null = null;

/**
 * Wires the existing chat DOM (form, tabs, line buffer). Idempotent: a second
 * call only refreshes the callback/handle. Safe when the panel markup is
 * missing — the wiring degrades to no-ops instead of throwing.
 */
export function initChat(chatHud: ChatHud, sendChat: SendChat): void {
	hud = chatHud;
	send = sendChat;
	if (!initialized) {
		initialized = true;
		onSystemLine(WELCOME_LINE);
	}
	if (subscribers.size > 0 || typeof document === "undefined") return;
	const form = document.getElementById("chat-form");
	const input = document.getElementById("chat-input");
	const lines = document.getElementById("chat-lines");
	if (!(form instanceof HTMLFormElement) || !(input instanceof HTMLInputElement) || !(lines instanceof HTMLElement)) return;
	if (bound) {
		refreshTabs();
		refreshInput();
		return;
	}
	bound = true;
	legacyEvents = new AbortController();
	const signal = legacyEvents.signal;
	inputEl = input;
	input.maxLength = CHAT_MAX_LENGTH;
	lines.dataset.filter = "room";
	lines.replaceChildren(); // drop the static placeholder lines
	form.addEventListener("submit", (event) => {
		event.preventDefault();
		submitCurrent();
	}, { signal });
	document.querySelectorAll<HTMLButtonElement>(".chat-tabs button").forEach((tab, index) => {
		const kind: TabKind = tab.dataset.channel === "room" || tab.dataset.channel === "group" || tab.dataset.channel === "system"
			? tab.dataset.channel
			: index === 0 ? "room" : index === 1 ? "group" : "system";
		tab.dataset.channel = kind;
		tab.textContent = TAB_TEXT[kind];
		tab.addEventListener("click", () => selectTab(kind), { signal });
	});
	for (const line of buffer) appendLegacyLine(line);
	refreshTabs();
	refreshInput();
}

/** Appends one server chat line: "[World] Name: text" / "[Party] Name: text". */
export function onChatMessage(message: unknown): void {
	const parsed = parseChatMessage(message);
	if (!parsed) return;
	appendLine({
		device: deviceKind((message as Record<string,unknown>).device),
		kind: parsed.channel,
		label: `${parsed.channel === "megaphone" ? (THAI?"[โทรโข่ง]":"[Megaphone]") : parsed.channel === "room" ? LABEL_ROOM : LABEL_GROUP} ${parsed.from}:`,
		text: parsed.text,
	});
}

/** Appends a "[System]" line (server notices, local warnings). */
export function onSystemLine(text: string): void {
	const clean = sanitizeChatText(text, SYSTEM_MAX);
	if (!clean) return;
	appendLine({ kind: "system", label: LABEL_SYSTEM, text: clean, system: true });
}

/** GameHud.setGroup() syncs the Party tab lock with group membership. */
export function setChatGroupAvailable(hasGroup: boolean): void {
	if (groupAvailable === hasGroup) return;
	groupAvailable = hasGroup;
	if (hasGroup) groupNoticeShown = false;
	if (!hasGroup && activeTab === "group") showGroupNotice();
	refreshTabs();
	refreshInput();
	publish();
}

function submitCurrent(): void {
	const input = inputEl;
	if (!input) return;
	if (input.value.length > CHAT_MAX_LENGTH) return; // over-length input is ignored
	const text = input.value;
	input.value = "";
	submitChatText(text);
}

function selectTab(kind: TabKind): void {
	activeTab = kind;
	if (kind === "group" && !groupAvailable) showGroupNotice();
	refreshTabs();
	refreshInput();
	publish();
}

function showGroupNotice(): void {
	if (groupNoticeShown) return;
	groupNoticeShown = true;
	appendLine({ kind: "group", label: LABEL_SYSTEM, text: NOTICE_NO_GROUP, system: true });
}

function refreshTabs(): void {
	if (subscribers.size > 0 || typeof document === "undefined") return;
	const lines = document.getElementById("chat-lines");
	if (lines) lines.dataset.filter = activeTab;
	document.querySelectorAll<HTMLButtonElement>(".chat-tabs button").forEach((tab) => {
		const kind = tab.dataset.channel as TabKind | undefined;
		const selected = kind === activeTab;
		tab.classList.toggle("selected", selected);
		tab.setAttribute("aria-selected", selected ? "true" : "false");
		if (kind === "group") tab.classList.toggle("is-locked", !groupAvailable);
	});
}

function refreshInput(): void {
	if (subscribers.size > 0 || typeof document === "undefined") return;
	const input = inputEl;
	if (!input) return;
	const form = document.getElementById("chat-form")?.querySelector<HTMLButtonElement>("button[type='submit'], button:not([type])");
	const locked = activeTab === "system" || (activeTab === "group" && !groupAvailable);
	input.disabled = locked;
	if (form) form.disabled = locked;
	input.placeholder = activeTab === "system"
		? PLACEHOLDER_SYSTEM
		: activeTab === "group"
			? (groupAvailable ? PLACEHOLDER_GROUP : PLACEHOLDER_LOCKED)
			: PLACEHOLDER_ROOM;
}

interface LineSpec {
	device?:DeviceKind;
	kind: TabKind;
	label: string;
	text: string;
	system?: boolean;
}

function appendLine(spec: LineSpec): void {
	const line = Object.freeze({ device:spec.device??"unknown", id: ++lineId, kind: spec.kind, label: spec.label, text: spec.text, system: spec.system === true });
	buffer.push(line);
	if (buffer.length > MAX_LINES) buffer.splice(0, buffer.length - MAX_LINES);
	publish();
	if (subscribers.size > 0 || typeof document === "undefined") return;
	appendLegacyLine(line);
}

function appendLegacyLine(spec: LineSpec): void {
	const host = document.getElementById("chat-lines");
	if (!host) return;
	const line = document.createElement("p");
	line.dataset.kind = spec.kind;
	const label = document.createElement("b");
	label.className = spec.kind === "room" ? "chat-world" : spec.kind === "group" ? "chat-party" : "chat-system";
	label.textContent = spec.label;
	line.append(label, document.createTextNode(` ${spec.text}`));
	host.append(line);
	while (host.children.length > MAX_LINES) host.firstElementChild?.remove();
	updateEmptyNote(host);
	host.scrollTop = host.scrollHeight;
}

function updateEmptyNote(host: HTMLElement): void {
	host.querySelectorAll(".chat-empty-note").forEach((node) => node.remove());
	const filter = host.dataset.filter;
	if (!filter) return;
	const visible = host.querySelectorAll(`p[data-kind="${filter}"]:not(.chat-empty-note)`).length;
	if (visible > 0) return;
	const note = document.createElement("p");
	note.className = "chat-empty-note";
	note.dataset.kind = filter;
	note.textContent = EMPTY_NOTES[filter as TabKind] ?? EMPTY_NOTES.room;
	host.append(note);
}
