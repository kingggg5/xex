/**
 * Social UI: the Friends panel (add-by-handle, presence rows, remove) and the
 * Group panel (create, join-by-code, member rows, leave).
 *
 * Contract (server, built in parallel):
 * - Client→server cold: {"t":"friend_add","handle":...},
 *   {"t":"friend_remove","handle":...}, {"t":"group_create"},
 *   {"t":"group_join","code":"A1B2C3"}, {"t":"group_leave"}.
 * - Entries arrive as {"handle","name","online","channel"|"tower","in_tower"}
 *   (see social-parse.mjs for the tolerant decoding).
 *
 * Rendering only — every action flows through the `actions` callbacks supplied
 * by GameHud (the integrator encodes the cold messages). Rejections (group
 * full, unknown group, bad handle) are surfaced by the integrator as toasts.
 */

import { isValidGroupCode, parseFriendEntries, parseGroupInfo, sanitizeHandle } from "./social-parse.mjs";

/** One friend or group-member row, normalized by parseFriendEntry(). */
export interface FriendEntry {
	handle: string;
	name: string;
	online: boolean;
	channel: number | null;
	tower: number | null;
	inTower: boolean;
}

export interface FriendActions {
	add(handle: string): void;
	remove(handle: string): void;
}

export interface GroupInfo {
	code: string;
	members: FriendEntry[];
}

export interface GroupActions {
	create(): void;
	join(code: string): void;
	leave(): void;
}

// D-06 convention (rooms-ui / tower-ui): Thai copy when the browser language is Thai.
const THAI = typeof navigator === "undefined" ? false : navigator.language.toLowerCase().startsWith("th");

interface CopyTable {
	friendsKicker: string;
	addLabel: string;
	handleAria: string;
	handlePlaceholder: string;
	handleHint: string;
	handleInvalid: string;
	friendsEmpty: string;
	removeAria(name: string): string;
	online: string;
	offline: string;
	roomLabel(channel: number): string;
	towerLabel(floor: number | null): string;
	groupKicker: string;
	groupNone: string;
	create: string;
	joinLabel: string;
	codeAria: string;
	codePlaceholder: string;
	codeLabel(code: string): string;
	membersLabel(count: number): string;
	groupEmptyMembers: string;
	leave: string;
	friendsNote: string;
	groupNote: string;
}

const EN: CopyTable = {
	friendsKicker: "FRIENDS",
	addLabel: "Add",
	handleAria: "Friend handle",
	handlePlaceholder: "handle · e.g. abcdef12",
	handleHint: "Add a friend by their handle.",
	handleInvalid: "Handles use 2–24 letters, digits, - or _.",
	friendsEmpty: "No friends yet — add someone by handle.",
	removeAria: (name) => `Remove ${name}`,
	online: "Online",
	offline: "Offline",
	roomLabel: (channel) => `Room ${channel + 1}`,
	towerLabel: (floor) => floor !== null && floor > 0 ? `Tower F${floor}` : "Tower",
	groupKicker: "GROUP",
	groupNone: "You are not in a group right now.",
	create: "Create group",
	joinLabel: "Join",
	codeAria: "Group invite code",
	codePlaceholder: "6-character code",
	codeLabel: (code) => `Invite code ${code}`,
	membersLabel: (count) => `${count} ${count === 1 ? "member" : "members"}`,
	groupEmptyMembers: "No other members yet — share your invite code.",
	leave: "Leave group",
	friendsNote: "Online friends show the room they play in, or their tower floor.",
	groupNote: "Group chat lives in the Party tab of the chat panel.",
};

const TH: CopyTable = {
	friendsKicker: "เพื่อน",
	addLabel: "เพิ่ม",
	handleAria: "ไอดีเพื่อน",
	handlePlaceholder: "ไอดี เช่น abcdef12",
	handleHint: "เพิ่มเพื่อนด้วยไอดีของเขา",
	handleInvalid: "ไอดีใช้ตัวอักษร ตัวเลข - หรือ _ จำนวน 2–24 ตัว",
	friendsEmpty: "ยังไม่มีเพื่อน — เพิ่มเพื่อนด้วยไอดีได้เลย",
	removeAria: (name) => `ลบ ${name}`,
	online: "ออนไลน์",
	offline: "ออฟไลน์",
	roomLabel: (channel) => `ห้อง ${channel + 1}`,
	towerLabel: (floor) => floor !== null && floor > 0 ? `หอคอย ชั้น ${floor}` : "หอคอย",
	groupKicker: "กลุ่ม",
	groupNone: "ขณะนี้คุณยังไม่ได้อยู่ในกลุ่ม",
	create: "สร้างกลุ่ม",
	joinLabel: "เข้าร่วม",
	codeAria: "รหัสเชิญกลุ่ม",
	codePlaceholder: "รหัส 6 ตัว",
	codeLabel: (code) => `รหัสเชิญ ${code}`,
	membersLabel: (count) => `สมาชิก ${count} คน`,
	groupEmptyMembers: "ยังไม่มีสมาชิกคนอื่น — แชร์รหัสเชิญของคุณได้เลย",
	leave: "ออกจากกลุ่ม",
	friendsNote: "เพื่อนที่ออนไลน์จะแสดงห้องที่กำลังเล่น หรือชั้นของหอคอย",
	groupNote: "แชทกลุ่มอยู่ที่แท็บกลุ่ม (Party) ของหน้าแชท",
};

const COPY: CopyTable = THAI ? TH : EN;

/** Human label for where a player currently is (rooms, tower, or presence). */
export function placementLabel(entry: { online: boolean; channel: number | null; tower: number | null; inTower: boolean }): string {
	if (entry.inTower || entry.tower !== null) return COPY.towerLabel(entry.tower);
	if (entry.channel !== null) return COPY.roomLabel(entry.channel);
	return entry.online ? COPY.online : COPY.offline;
}

/**
 * Renders the Friends panel: an add-by-handle form, then one row per friend
 * (green dot + room/tower when online, gray when offline) with a remove
 * button. Safe to call repeatedly; each call replaces the content.
 */
export function renderFriendsPanel(container: HTMLElement, entries: FriendEntry[], actions: FriendActions): void {
	const list = parseFriendEntries(entries);
	container.replaceChildren();
	const panel = el("div", "social-panel");

	panel.append(el("p", "panel-kicker", COPY.friendsKicker));

	const error = el("small", "social-error", "");
	error.hidden = true;
	const input = document.createElement("input");
	input.maxLength = 24;
	input.autocomplete = "off";
	input.spellcheck = false;
	input.placeholder = COPY.handlePlaceholder;
	input.setAttribute("aria-label", COPY.handleAria);
	const add = document.createElement("button");
	add.type = "submit";
	add.className = "social-action";
	add.textContent = COPY.addLabel;
	const form = document.createElement("form");
	form.className = "social-form";
	form.addEventListener("submit", (event) => {
		event.preventDefault();
		const handle = sanitizeHandle(input.value);
		if (!handle) {
			error.textContent = COPY.handleInvalid;
			error.hidden = false;
			return;
		}
		error.hidden = true;
		input.value = "";
		actions.add(handle);
	});
	form.append(input, add);
	panel.append(form, error, el("p", "econ-note", COPY.handleHint));

	if (list.length === 0) {
		panel.append(el("p", "econ-note", COPY.friendsEmpty));
	} else {
		panel.append(el("p", "panel-kicker", COPY.membersLabel(list.length)));
		const rows = el("div", "social-rows");
		for (const entry of list) rows.append(friendRow(entry, actions));
		panel.append(rows);
	}

	panel.append(el("p", "econ-note", COPY.friendsNote));
	container.append(panel);
}

/**
 * Renders the Group panel. With no group: a create button plus a join-by-code
 * form. With a group: the invite code, member rows, and a leave button.
 * A null `group` renders the "no group" state.
 */
export function renderGroupPanel(container: HTMLElement, group: GroupInfo | null, actions: GroupActions): void {
	const info = group ? parseGroupInfo(group) : null;
	const active = info !== null;
	container.replaceChildren();
	const panel = el("div", "social-panel");
	panel.append(el("p", "panel-kicker", COPY.groupKicker));

	if (!active || info === null) {
		panel.append(el("p", "econ-note", COPY.groupNone));
		panel.append(actionButton(COPY.create, "social-action", () => actions.create()));
		const code = document.createElement("input");
		code.maxLength = 6;
		code.autocomplete = "off";
		code.spellcheck = false;
		code.placeholder = COPY.codePlaceholder;
		code.setAttribute("aria-label", COPY.codeAria);
		code.addEventListener("input", () => {
			code.value = code.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
		});
		const join = document.createElement("button");
		join.type = "submit";
		join.className = "social-action";
		join.textContent = COPY.joinLabel;
		const form = document.createElement("form");
		form.className = "social-form";
		form.addEventListener("submit", (event) => {
			event.preventDefault();
			if (isValidGroupCode(code.value)) actions.join(code.value);
		});
		form.append(code, join);
		panel.append(form);
	} else {
		panel.append(el("p", "group-code", COPY.codeLabel(info.code || "······")));
		if (info.members.length === 0) {
			panel.append(el("p", "econ-note", COPY.groupEmptyMembers));
		} else {
			panel.append(el("p", "panel-kicker", COPY.membersLabel(info.members.length)));
			const rows = el("div", "social-rows");
			for (const member of parseFriendEntries(info.members)) rows.append(memberRow(member));
			panel.append(rows);
		}
		panel.append(actionButton(COPY.leave, "social-leave", () => actions.leave()));
	}

	panel.append(el("p", "econ-note", COPY.groupNote));
	container.append(panel);
}

function friendRow(entry: FriendEntry, actions: FriendActions): HTMLElement {
	const row = memberRow(entry);
	const remove = document.createElement("button");
	remove.type = "button";
	remove.className = "social-remove";
	remove.textContent = "×";
	remove.setAttribute("aria-label", COPY.removeAria(entry.name));
	if (!entry.handle) remove.disabled = true;
	else remove.addEventListener("click", () => actions.remove(entry.handle));
	row.append(remove);
	return row;
}

function memberRow(entry: FriendEntry): HTMLElement {
	const row = el("div", `social-row ${entry.online ? "is-online" : "is-offline"}`);
	const dot = el("span", "social-dot");
	dot.setAttribute("aria-hidden", "true");
	const label = el("div", "social-label");
	label.append(el("b", "", entry.name));
	if (entry.handle && entry.handle !== entry.name) label.append(el("small", "", `@${entry.handle}`));
	row.append(dot, label, el("span", "social-where", placementLabel(entry)));
	return row;
}

function actionButton(label: string, className: string, onClick: () => void): HTMLButtonElement {
	const button = document.createElement("button");
	button.type = "button";
	button.className = className;
	button.textContent = label;
	button.addEventListener("click", onClick);
	return button;
}

function el(tag: string, className: string, text?: string): HTMLElement {
	const node = document.createElement(tag);
	node.className = className;
	if (text !== undefined) node.textContent = text;
	return node;
}
