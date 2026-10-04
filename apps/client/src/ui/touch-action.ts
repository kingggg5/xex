import type { Action } from "svelte/action";

interface JoystickOptions {
	enabled: boolean;
	resetVersion: number;
	move(x: number, z: number): void;
}

/** The held vector and pointer capture are imperative input, never per-frame reactive state. */
export const movementJoystick: Action<HTMLElement, JoystickOptions> = (node, initial) => {
	let options = initial;
	const knob = node.querySelector<HTMLElement>(".joystick-knob");
	const events = new AbortController();
	let pointerId: number | null = null;
	let centerX = 0;
	let centerY = 0;
	let radius = 1;
	const arrowKeys = new Set<string>();
	const reset = () => {
		const captured = pointerId;
		const active = captured !== null || arrowKeys.size > 0;
		pointerId = null;
		arrowKeys.clear();
		if (active) options.move(0, 0);
		if (knob) knob.style.transform = "translate(0px, 0px)";
		if (captured !== null && node.hasPointerCapture(captured)) node.releasePointerCapture(captured);
	};
	const move = (event: PointerEvent) => {
		let x = (event.clientX - centerX) / radius;
		let y = (event.clientY - centerY) / radius;
		const length = Math.hypot(x, y);
		if (length > 1) { x /= length; y /= length; }
		options.move(x, -y);
		if (knob) knob.style.transform = `translate(${x * radius}px, ${y * radius}px)`;
	};
	node.addEventListener("pointerdown", (event) => {
		if (!options.enabled || pointerId !== null || (event.pointerType === "mouse" && event.button !== 0)) return;
		const rect = node.getBoundingClientRect();
		centerX = rect.left + rect.width / 2;
		centerY = rect.top + rect.height / 2;
		radius = Math.max(1, rect.width * .31);
		pointerId = event.pointerId;
		node.setPointerCapture(event.pointerId);
		move(event);
		event.preventDefault();
	}, { signal: events.signal });
	node.addEventListener("pointermove", (event) => {
		if (options.enabled && event.pointerId === pointerId) { move(event); event.preventDefault(); }
	}, { signal: events.signal });
	for (const eventName of ["pointerup", "pointercancel", "lostpointercapture"] as const) {
		node.addEventListener(eventName, (event) => { if (event.pointerId === pointerId) reset(); }, { signal: events.signal });
	}
	const keyboardMove = () => {
		let x = Number(arrowKeys.has("ArrowRight")) - Number(arrowKeys.has("ArrowLeft"));
		let z = Number(arrowKeys.has("ArrowUp")) - Number(arrowKeys.has("ArrowDown"));
		const length = Math.hypot(x, z);
		if (length > 1) { x /= length; z /= length; }
		options.move(x, z);
		if (knob) knob.style.transform = `translate(${x * node.clientWidth * .31}px, ${-z * node.clientWidth * .31}px)`;
	};
	node.addEventListener("keydown", (event) => {
		if (!options.enabled || !event.key.startsWith("Arrow")) return;
		arrowKeys.add(event.key);
		keyboardMove();
		event.preventDefault();
		event.stopPropagation();
	}, { signal: events.signal });
	node.addEventListener("keyup", (event) => {
		if (!event.key.startsWith("Arrow")) return;
		arrowKeys.delete(event.key);
		keyboardMove();
		event.preventDefault();
		event.stopPropagation();
	}, { signal: events.signal });
	node.addEventListener("blur", reset, { signal: events.signal });
	window.addEventListener("blur", reset, { signal: events.signal });
	window.addEventListener("resize", reset, { passive: true, signal: events.signal });
	window.addEventListener("aetherfield:renderer-lost", reset, { signal: events.signal });
	document.addEventListener("visibilitychange", () => { if (document.hidden) reset(); }, { signal: events.signal });
	return {
		update(next) {
			const changed = next.resetVersion !== options.resetVersion;
			options = next;
			if (!next.enabled || changed) reset();
		},
		destroy() { reset(); events.abort(); },
	};
};

interface PressOptions { enabled: boolean; capture: boolean }

/** Own capture for touch buttons, but retain the native click/keyboard activation path. */
export const touchPress: Action<HTMLButtonElement, PressOptions> = (node, initial) => {
	let options = initial;
	const events = new AbortController();
	let pointerId: number | null = null;
	let cancelled = false;
	const release = (cancel: boolean) => {
		const captured = pointerId;
		pointerId = null;
		if (cancel && captured !== null) cancelled = true;
		if (captured !== null && node.hasPointerCapture(captured)) node.releasePointerCapture(captured);
	};
	node.addEventListener("pointerdown", (event) => {
		if (!options.enabled || !options.capture || pointerId !== null || event.button !== 0) return;
		cancelled = false;
		pointerId = event.pointerId;
		node.setPointerCapture(event.pointerId);
	}, { signal: events.signal });
	node.addEventListener("pointerup", (event) => {
		if (event.pointerId !== pointerId) return;
		const rect = node.getBoundingClientRect();
		const outside = event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
		release(outside);
	}, { signal: events.signal });
	for (const eventName of ["pointercancel", "lostpointercapture"] as const) {
		node.addEventListener(eventName, (event) => { if (event.pointerId === pointerId) release(true); }, { signal: events.signal });
	}
	node.addEventListener("click", (event) => {
		if (event.detail !== 0 && cancelled) { event.preventDefault(); event.stopImmediatePropagation(); }
		cancelled = false;
	}, { capture: true, signal: events.signal });
	window.addEventListener("blur", () => release(true), { signal: events.signal });
	document.addEventListener("visibilitychange", () => { if (document.hidden) release(true); }, { signal: events.signal });
	return {
		update(next) { options = next; if (!next.enabled || !next.capture) release(true); },
		destroy() { release(true); events.abort(); },
	};
};
