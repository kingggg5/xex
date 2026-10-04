import assert from "node:assert/strict";
import { test } from "node:test";
import { clearContentMismatchReload, shouldReloadContentMismatch } from "../src/content-reload.mjs";

function memoryStorage() {
	const values = new Map();
	return {
		getItem: (key) => values.get(key) ?? null,
		setItem: (key, value) => values.set(key, value),
		removeItem: (key) => values.delete(key),
	};
}

test("content mismatch permits one refresh per tab and then stops", () => {
	const storage = memoryStorage();
	assert.equal(shouldReloadContentMismatch(storage, 0x1234n), true);
	assert.equal(shouldReloadContentMismatch(storage, 0x1234n), false);
	clearContentMismatchReload(storage);
	assert.equal(shouldReloadContentMismatch(storage, 0x1234n), true);
});

test("content mismatch fails visibly when session storage is unavailable", () => {
	const unavailable = {
		getItem() { throw new Error("blocked"); },
		setItem() { throw new Error("blocked"); },
	};
	assert.equal(shouldReloadContentMismatch(unavailable, "bundle-hash"), false);
});
