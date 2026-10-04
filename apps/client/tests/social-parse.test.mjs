import assert from "node:assert/strict";
import test from "node:test";
import {
	CHAT_MAX_LENGTH,
	isValidGroupCode,
	parseChatMessage,
	parseFriendEntries,
	parseFriendEntry,
	parseFriendsBody,
	parseGroupBody,
	parseGroupInfo,
	sanitizeChatText,
	sanitizeDisplayName,
	sanitizeHandle,
} from "../src/social-parse.mjs";

test("chat text sanitize strips control characters and collapses whitespace", () => {
	assert.equal(sanitizeChatText("  hello   world  "), "hello world");
	assert.equal(sanitizeChatText("a\u0000b\u0007c\u001fd\u007fe"), "a b c d e");
	assert.equal(sanitizeChatText("line\nbreak\ttab"), "line break tab");
	assert.equal(sanitizeChatText("   \n\t  "), "");
	assert.equal(sanitizeChatText(42), "");
	assert.equal(sanitizeChatText(null), "");
	assert.equal(sanitizeChatText(undefined), "");
});

test("chat text sanitize clamps to 160 code points without splitting surrogates", () => {
	assert.equal(sanitizeChatText("x".repeat(200)).length, CHAT_MAX_LENGTH);
	const clamped = sanitizeChatText("a".repeat(159) + "🎯🎯🎯");
	assert.equal([...clamped].length, CHAT_MAX_LENGTH);
	assert.ok(clamped.endsWith("🎯"), "emoji must survive the clamp intact");
	assert.equal(sanitizeChatText("ok", 4), "ok");
});

test("display name sanitize keeps interior spaces and Thai text", () => {
	assert.equal(sanitizeDisplayName("  Eira Windrunner  "), "Eira Windrunner");
	assert.equal(sanitizeDisplayName("ผู้เดินทาง"), "ผู้เดินทาง");
	assert.equal(sanitizeDisplayName("bad\u0000name"), "badname");
	assert.equal(sanitizeDisplayName("x".repeat(60)).length, 48);
	assert.equal(sanitizeDisplayName("///"), "///");
});

test("handle sanitize accepts contract-style handles and rejects the rest", () => {
	assert.equal(sanitizeHandle(" abcdef12 "), "abcdef12");
	assert.equal(sanitizeHandle("Wind_Runner-7"), "Wind_Runner-7");
	assert.equal(sanitizeHandle("A"), "");
	assert.equal(sanitizeHandle("has space"), "");
	assert.equal(sanitizeHandle("ตัวเอก"), "");
	assert.equal(sanitizeHandle("x".repeat(30)), "");
	assert.equal(sanitizeHandle(123), "");
});

test("chat cold messages parse and reject malformed payloads", () => {
	assert.deepEqual(parseChatMessage({ t: "chat", channel: "room", from: "Miro", text: " hi " }), {
		channel: "room",
		from: "Miro",
		text: "hi",
	});
	assert.deepEqual(parseChatMessage({ t: "chat", channel: "group", from: "", text: "hello" }), {
		channel: "group",
		from: "?",
		text: "hello",
	});
	assert.equal(parseChatMessage({ t: "chat", channel: "world", from: "M", text: "hi" }), null);
	assert.equal(parseChatMessage({ t: "notice", channel: "room", from: "M", text: "hi" }), null);
	assert.equal(parseChatMessage({ t: "chat", channel: "room", from: "M", text: "   " }), null);
	assert.equal(parseChatMessage({ t: "chat", channel: "room", text: "no sender" }).from, "?");
	assert.equal(parseChatMessage(null), null);
	assert.equal(parseChatMessage("chat"), null);
});

test("friend entries parse leniently across channel/tower shapes", () => {
	assert.deepEqual(parseFriendEntry({ handle: "abcdef12", name: "Miro", online: true, channel: 3, in_tower: false }), {
		handle: "abcdef12",
		name: "Miro",
		online: true,
		channel: 3,
		tower: null,
		inTower: false,
	});
	const towerRow = parseFriendEntry({ handle: "ff0099", name: "Sola", online: true, in_tower: true });
	assert.equal(towerRow.inTower, true);
	assert.equal(towerRow.channel, null);
	const floorRow = parseFriendEntry({ name: "Jory", online: true, tower: 7 });
	assert.equal(floorRow.inTower, true);
	assert.equal(floorRow.tower, 7);
	assert.equal(parseFriendEntry({ handle: "abcdef12", name: "Jory", channel: "three" }).channel, null);
	assert.equal(parseFriendEntry({ name: "" }), null, "neither name nor handle");
	assert.equal(parseFriendEntry({ handle: "abcdef12", name: "" }).name, "abcdef12", "handle fills in for a missing name");
	assert.equal(parseFriendEntry(null), null);
	assert.deepEqual(parseFriendEntries(["bad", { handle: "a", name: "B" }]), [
		{ handle: "a", name: "B", online: false, channel: null, tower: null, inTower: false },
	]);
	assert.deepEqual(parseFriendEntries("nope"), []);
});

test("friends body accepts both HTTP and cold shapes", () => {
	const row = { handle: "abcdef12", name: "Miro", online: true, channel: 0, in_tower: false };
	assert.deepEqual(parseFriendsBody({ friends: [row] }), parseFriendEntries([row]));
	assert.deepEqual(parseFriendsBody({ t: "friends", entries: [row] }), parseFriendEntries([row]));
	assert.deepEqual(parseFriendsBody({ friends: [] }), []);
	assert.equal(parseFriendsBody({ friends: "no" }), null);
	assert.equal(parseFriendsBody({ entries: null }), null);
	assert.equal(parseFriendsBody(null), null);
});

test("group bodies distinguish explicit null from malformed", () => {
	const group = { code: "A1B2C3", members: [{ handle: "abcdef12", name: "Miro", online: true }] };
	assert.deepEqual(parseGroupBody({ group }), { group: parseGroupInfo(group) });
	assert.deepEqual(parseGroupBody({ t: "group", group: null }), { group: null });
	assert.deepEqual(parseGroupBody({ group: {} }), { group: null }, "empty group degrades to none");
	assert.equal(parseGroupBody({ nope: 1 }), null);
	assert.equal(parseGroupBody("x"), null);
	assert.equal(parseGroupInfo({ code: "a1b2c3", members: [] }), null, "bad code with no members");
	assert.equal(parseGroupInfo({ code: "A1B2C3" }).code, "A1B2C3");
	assert.equal(parseGroupInfo({ code: "A1B2C3" }).members.length, 0);
});

test("group codes are six uppercase alphanumerics", () => {
	assert.equal(isValidGroupCode("A1B2C3"), true);
	assert.equal(isValidGroupCode("a1b2c3"), false);
	assert.equal(isValidGroupCode("A1B2C"), false);
	assert.equal(isValidGroupCode("A1B2C3D"), false);
	assert.equal(isValidGroupCode(null), false);
});
