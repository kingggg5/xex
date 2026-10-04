import assert from "node:assert/strict";
import { test } from "node:test";
import { decideLoginGate, loginErrorText, parseIdentity, parseStoredChannel } from "../src/login-gate.mjs";

test("an unreachable server boots the offline preview with no gate", () => {
	assert.equal(decideLoginGate({ serverAlive: false, signedIn: false, providers: null, urlError: null }), "offline");
});

test("a live session enters directly, both with and without provider data", () => {
	assert.equal(
		decideLoginGate({ serverAlive: true, signedIn: true, providers: { google: true, discord: false }, urlError: null }),
		"enter",
	);
});

test("a signed-in player with a login error in the URL still sees the gate", () => {
	assert.equal(
		decideLoginGate({ serverAlive: true, signedIn: true, providers: { google: false, discord: false }, urlError: "state" }),
		"show",
	);
});

test("a server without provider data cannot show the gate", () => {
	assert.equal(decideLoginGate({ serverAlive: true, signedIn: false, providers: null, urlError: null }), "offline");
});

test("an anonymous player on a live server sees the login screen", () => {
	assert.equal(
		decideLoginGate({ serverAlive: true, signedIn: false, providers: { google: false, discord: false }, urlError: null }),
		"show",
	);
});

test("login errors map to player-facing copy with a safe fallback", () => {
	assert.match(loginErrorText("denied", "en"), /cancelled/i);
	assert.match(loginErrorText("denied", "th"), /ยกเลิก/);
	assert.match(loginErrorText("state", "en"), /try again/i);
	assert.match(loginErrorText("provider_disabled", "en"), /isn't configured/i);
	assert.equal(loginErrorText("totally_unknown", "en"), null);
	assert.equal(loginErrorText(null, "en"), null);
});

test("stored channel choices parse defensively and fall back to auto", () => {
	assert.equal(parseStoredChannel(7), 7);
	assert.equal(parseStoredChannel(0), 0);
	assert.equal(parseStoredChannel("12"), 12);
	assert.equal(parseStoredChannel(null), null);
	assert.equal(parseStoredChannel(undefined), null);
	assert.equal(parseStoredChannel(-1), null);
	assert.equal(parseStoredChannel(1.5), null);
	assert.equal(parseStoredChannel(65536), null);
	assert.equal(parseStoredChannel("abc"), null);
	assert.equal(parseStoredChannel({ channel: 7 }), null);
});

test("whoami payloads parse strictly and never break the boot path", () => {
	assert.deepEqual(
		parseIdentity({ identity: { provider: "google", display_name: "Ada", subject: "1" } }),
		{ provider: "google", name: "Ada" },
	);
	assert.deepEqual(parseIdentity({ identity: { provider: "guest", display_name: "Traveler" } }), {
		provider: "guest",
		name: "Traveler",
	});
	assert.deepEqual(parseIdentity({ identity: { provider: "discord", display_name: "" } }), {
		provider: "discord",
		name: "Traveler",
	});
	// Malformed payloads fall back instead of throwing.
	assert.deepEqual(parseIdentity(null), { provider: "guest", name: "Traveler" });
	assert.deepEqual(parseIdentity({}), { provider: "guest", name: "Traveler" });
	assert.deepEqual(parseIdentity({ identity: "guest" }), { provider: "guest", name: "Traveler" });
	assert.deepEqual(parseIdentity({ identity: { provider: "evil-provider", display_name: 42 } }), {
		provider: "guest",
		name: "Traveler",
	});
});
