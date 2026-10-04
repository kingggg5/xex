import { createHudControlLayout } from "../src/hud-control-layout-controller.ts";
import { LAYOUT_STORAGE_KEY, layoutProfile } from "../src/hud-control-layout.mjs";

const caseName = new URLSearchParams(location.search).get("case");
const sizes = { desktop: [1100, 700], landscape: [844, 390], portrait: [390, 844] };
if (!caseName) {
	const frames = new Map(); const completed = new Set(); let failures = 0;
	window.addEventListener("message", event => {
		if (event.origin !== location.origin || ![...frames.values()].includes(event.source)) return;
		const report = event.data;
		if (report?.type !== "hud-layout-dom-contract" || typeof report.name !== "string" || completed.has(report.name)) return;
		completed.add(report.name);
		for (const result of report.results) { const line = document.createElement("li"); line.className = result.ok ? "pass" : "fail"; line.textContent = `${report.name}: ${result.ok ? "PASS" : "FAIL"} — ${result.name}${result.error ? `: ${result.error}` : ""}`; document.getElementById("results").append(line); if (!result.ok) failures++; }
		document.getElementById("summary").textContent = completed.size === 3 ? `${failures ? "FAIL" : "PASS"}: ${completed.size} viewport cases completed; ${failures} failed contracts. Native game/device checks remain separate.` : `${completed.size}/3 viewport cases completed…`;
	});
	for (const [name, [width, height]] of Object.entries(sizes)) {
		const iframe = document.createElement("iframe"); iframe.title = `${name} control layout fixture`; iframe.width = String(width); iframe.height = String(height); iframe.src = `${location.pathname}?case=${name}`; document.body.append(iframe); frames.set(name, iframe.contentWindow);
	}
} else {
	document.body.classList.add("fixture-mode"); document.getElementById("fixture").hidden = false;
	const results = [], writes = [], changes = [], entries = new Map(); let denyWrite = false;
	const storage = { getItem: key => entries.get(key) ?? null, setItem: (key, value) => { if (denyWrite) throw new Error("QuotaExceededError"); writes.push(value); entries.set(key, value); } };
	const step = async () => { await new Promise(resolve => requestAnimationFrame(resolve)); await new Promise(resolve => requestAnimationFrame(resolve)); };
	const assert = (condition, message) => { if (!condition) throw new Error(message); };
	const near = (actual, expected, message) => assert(Math.abs(actual - expected) < .5, `${message}: ${actual} vs ${expected}`);
	const run = async (name, test) => {
		try { await test(); results.push({ name, ok: true }); }
		catch (error) { results.push({ name, ok: false, error: String(error.message ?? error) }); }
		const line = document.createElement("li"); line.textContent = `${results.at(-1).ok ? "PASS" : "FAIL"} ${name}`; document.getElementById("case-results").append(line);
	};
	let controller = createHudControlLayout({ language: "en", storage, onEditingChange: editing => changes.push(editing) });
	const byLabel = label => document.querySelector(`[aria-label="${label}"]`);
	const actualAttack = () => [...document.querySelectorAll('#hud [data-action="attack"]')].find(node => node.getClientRects().length);
	const actualArc = () => [...document.querySelectorAll('#hud [data-action="arc_slash"]')].find(node => node.getClientRects().length);
	const key = (handle, keyValue, shiftKey = false) => { handle.focus(); handle.dispatchEvent(new KeyboardEvent("keydown", { key: keyValue, shiftKey, bubbles: true, cancelable: true })); };
	const openSettings = () => {
		const host = document.getElementById("modal-backdrop"); host.innerHTML = '<section class="game-modal" role="dialog" aria-label="Settings fixture"><button class="modal-close" type="button">Close</button><div class="modal-content"><label for="settings-ui-scale">UI scale</label><input id="settings-ui-scale" type="range"></div></section>';
		host.querySelector(".modal-close").addEventListener("click", () => queueMicrotask(() => host.replaceChildren()));
	};
	await step();
	const baseline = actualAttack().getBoundingClientRect().left;
	let savedLeft = baseline;
	await run("Settings entry works with class-only modal content and close button", async () => {
		openSettings(); await step(); assert(byLabel("Edit controls"), "Edit controls entry absent"); byLabel("Edit controls").click(); await step();
		assert(!document.querySelector(".game-modal"), "Async modal close did not finish"); assert(controller.isEditing(), "Editor did not enter"); assert(byLabel("Move Attack"), "Visible actual Attack has no handle");
	});
	await run("Only visible PC/mobile action is edited; minimum target remains reachable", async () => {
		const active = actualAttack(), handle = byLabel("Move Attack"); assert(active, "Active Attack not found");
		near(handle.getBoundingClientRect().left, active.getBoundingClientRect().left, "Handle and actual control disagree");
		assert([...document.querySelectorAll(".hud-layout-handle")].filter(node => node.getAttribute("aria-label") === "Move Attack").length === 1, "Duplicate Attack handles");
		const arc = actualArc().getBoundingClientRect(); assert(arc.width >= 43.9 && arc.height >= 43.9, "Scaled mobile target is below 44px");
	});
	await run("Arrow positioning translates the real button without moving its neighbours", async () => {
		const left = actualAttack().getBoundingClientRect().left, neighbour = actualArc().getBoundingClientRect().left;
		key(byLabel("Move Attack"), "ArrowLeft", true);
		near(actualAttack().getBoundingClientRect().left, left - 24, "Shift arrow should move 24 CSS pixels");
		near(actualArc().getBoundingClientRect().left, neighbour, "Neighbour shifted in original flow");
	});
	await run("Toolbar chooses an unobstructed location", async () => {
		const bar = document.querySelector(".hud-layout-toolbar").getBoundingClientRect();
		assert(![...document.querySelectorAll(".hud-layout-handle")].some(node => { const r = node.getBoundingClientRect(); return r.right > bar.left && r.left < bar.right && r.bottom > bar.top && r.top < bar.bottom; }), "Toolbar overlaps a control handle");
	});
	await run("Gameplay click/key events are suppressed during editing", async () => {
		let activated = 0, gameKey = 0; const onClick = () => activated++, onKey = () => gameKey++;
		actualAttack().addEventListener("click", onClick); window.addEventListener("keydown", onKey);
		actualAttack().click(); actualAttack().dispatchEvent(new KeyboardEvent("keydown", { key: "f", code: "KeyF", bubbles: true, cancelable: true }));
		actualAttack().removeEventListener("click", onClick); window.removeEventListener("keydown", onKey);
		assert(activated === 0 && gameKey === 0, "Editor allowed gameplay input");
	});
	await run("Save exits editing, writes the current profile, and announces success", async () => {
		byLabel("Save layout").click(); await step(); savedLeft = actualAttack().getBoundingClientRect().left;
		assert(!controller.isEditing(), "Save did not exit"); assert(changes.at(-1) === false, "Save did not release root editing guard");
		const data = JSON.parse(entries.get(LAYOUT_STORAGE_KEY)), profile = layoutProfile(innerWidth, innerHeight, matchMedia("(any-pointer: coarse)").matches);
		assert(data.profiles[profile]?.attack, "Current profile not saved"); assert(!document.querySelector(".hud-layout-receipt").hidden, "Saved confirmation not visible");
	});
	await run("Recreating the controller restores the persisted actual position", async () => {
		controller.dispose(); near(actualAttack().getBoundingClientRect().left, baseline, "Dispose failed to restore original style");
		controller = createHudControlLayout({ language: "en", storage, onEditingChange: editing => changes.push(editing) }); await step();
		near(actualAttack().getBoundingClientRect().left, savedLeft, "Persisted translation not restored");
	});
	await run("Cancel restores saved position without a storage write", async () => {
		const before = writes.length; controller.beginEdit(); await step(); key(byLabel("Move Attack"), "ArrowLeft"); byLabel("Cancel changes").click(); await step();
		near(actualAttack().getBoundingClientRect().left, savedLeft, "Cancel failed to restore saved position"); assert(writes.length === before, "Cancel wrote storage");
	});
	await run("Pointer cancellation rolls back drag and re-neutralizes input (capture stubbed)", async () => {
		controller.beginEdit(); await step(); const handle = byLabel("Move Attack"), captured = new Set();
		handle.setPointerCapture = id => captured.add(id); handle.hasPointerCapture = id => captured.has(id); handle.releasePointerCapture = id => captured.delete(id);
		const rect = handle.getBoundingClientRect(), x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
		const dispatch = (type, dx = 0) => handle.dispatchEvent(new PointerEvent(type, { pointerId: 77, pointerType: "touch", button: 0, clientX: x + dx, clientY: y, bubbles: true, cancelable: true }));
		const callbacks = changes.length; dispatch("pointerdown"); dispatch("pointermove", -30);
		near(actualAttack().getBoundingClientRect().left, savedLeft - 30, "Pointer movement was not applied"); dispatch("pointercancel", -30);
		near(actualAttack().getBoundingClientRect().left, savedLeft, "Cancelled drag was not rolled back"); assert(captured.size === 0 && changes.length > callbacks, "Pointer cancellation did not release/neutralize"); byLabel("Cancel changes").click(); await step();
	});
	await run("Reset remains a draft and Cancel keeps the saved layout", async () => {
		controller.beginEdit(); await step(); byLabel("Reset layout").click(); near(actualAttack().getBoundingClientRect().left, baseline, "Reset did not restore defaults");
		byLabel("Cancel changes").click(); await step(); near(actualAttack().getBoundingClientRect().left, savedLeft, "Cancel failed to undo Reset");
	});
	await run("A storage failure leaves edits open and reports an error", async () => {
		controller.beginEdit(); await step(); key(byLabel("Move Attack"), "ArrowLeft"); denyWrite = true; byLabel("Save layout").click();
		assert(controller.isEditing(), "Failed Save discarded edit session"); assert(document.querySelector(".hud-layout-status").textContent.includes("Could not save"), "Failure message missing");
		assert(document.querySelector(".hud-layout-receipt").hidden, "Earlier success confirmation remained visible during failed Save"); denyWrite = false; byLabel("Cancel changes").click(); await step();
	});
	await run("Reset Save removes only this profile and preserves other orientations", async () => {
		const profile = layoutProfile(innerWidth, innerHeight, matchMedia("(any-pointer: coarse)").matches), other = profile === "desktop" ? "mobile-portrait" : "desktop";
		controller.dispose(); const data = JSON.parse(entries.get(LAYOUT_STORAGE_KEY)); data.profiles[other] = { guard: { x: .3, y: .4 } }; entries.set(LAYOUT_STORAGE_KEY, JSON.stringify(data));
		controller = createHudControlLayout({ language: "en", storage, onEditingChange: editing => changes.push(editing) }); await step(); controller.beginEdit(); await step(); byLabel("Reset layout").click(); byLabel("Save layout").click(); await step();
		const result = JSON.parse(entries.get(LAYOUT_STORAGE_KEY)); assert(!result.profiles[profile], "Reset Save retained this profile"); assert(result.profiles[other].guard.x === .3, "Reset erased another profile");
	});
	await run("Resize cancels unsaved edits and releases the root input guard", async () => {
		controller.beginEdit(); await step(); key(byLabel("Move Attack"), "ArrowLeft"); window.dispatchEvent(new Event("resize")); await step();
		assert(!controller.isEditing() && changes.at(-1) === false, "Resize kept editing/input guard active"); near(actualAttack().getBoundingClientRect().left, baseline, "Resize retained unsaved movement");
	});
	await run("Cancel before asynchronous preparation creates no late handles", async () => {
		controller.beginEdit(); byLabel("Cancel changes").click(); await step(); assert(!controller.isEditing() && document.querySelectorAll(".hud-layout-handle").length === 0, "Cancelled preparation created late handles");
	});
	await run("Reusing a modal for another panel removes the Settings-only entry", async () => {
		openSettings(); await step();
		const slider = document.getElementById('settings-ui-scale');
		const content = slider.closest('.modal-content');
		slider.remove();
		content.querySelector('label')?.remove();
		const menu = document.createElement('p'); menu.textContent = 'Another game panel'; content.append(menu);
		await step();
		assert(!content.querySelector('.hud-layout-settings'), 'Control editor entry leaked into another panel');
	});
	await run("Disposal removes editor hooks and restores original control styles", async () => {
		controller.dispose(); await step(); assert(!document.querySelector(".hud-layout-editor") && !document.querySelector(".hud-layout-settings"), "Disposed editor nodes remain"); near(actualAttack().getBoundingClientRect().left, baseline, "Original button position not restored");
	});
	parent.postMessage({ type: "hud-layout-dom-contract", name: caseName, results }, location.origin);
}
