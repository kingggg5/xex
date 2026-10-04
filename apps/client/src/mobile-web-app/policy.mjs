/** Primitive-only policy. One portrait result drives the overlay, inert state and gameplay guard. */
export function mobileWebAppPolicy(input) {
	const valid = Number.isFinite(input.width) && Number.isFinite(input.height) && input.width > 0 && input.height > 0;
	const viewportPortrait = !valid || input.height >= input.width;
	const mobilePhysicalContext = input.coarse === true || input.maxTouchPoints > 0;
	const type = typeof input.orientationType === 'string' ? input.orientationType : '';
	const angle = input.legacyAngle;
	const legacyPortrait = Number.isFinite(angle) && ((angle % 180) + 180) % 180 === 0;
	const modernKnown = type.startsWith('portrait') || type.startsWith('landscape');
	const physicalPortrait = mobilePhysicalContext && (modernKnown ? type.startsWith('portrait') : legacyPortrait);
	const portrait = viewportPortrait || physicalPortrait;
	const standalone = input.displayStandalone === true || input.navigatorStandalone === true;
	const guideOpen = input.guideOpen === true;
	return { viewportPortrait, physicalPortrait, portrait, standalone, guideOpen, blocked: portrait || guideOpen };
}
export const GAMEPLAY_CODES = Object.freeze(new Set([
	'KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space',
	'KeyF','KeyG','KeyE','Digit1','Digit2','Digit3','Digit4','Digit5','Digit6',
	'KeyB','KeyC','KeyK','KeyP','KeyM','KeyJ','KeyN','Escape',
]));
export function keepGuideEntry(kind, connected, isCurrentContext) { return connected === true && isCurrentContext === true && (kind === 'login' || kind === 'settings'); }
/** Opaque targets stay imperative; they are never placed in Svelte state or a serialized snapshot. */
export function createHeldInputLedger() {
	const keys = new Map(), pointers = new Map(), quarantined = new Set();
	return {
		keyDown(record) { if (GAMEPLAY_CODES.has(record.code) && !quarantined.has(record.code) && !keys.has(record.code)) keys.set(record.code, { ...record }); },
		keyUp(code, ownedRelease = false) { keys.delete(code); if (!ownedRelease) quarantined.delete(code); },
		isKeyQuarantined(code) { return quarantined.has(code); },
		pointerDown(record) { if (Number.isInteger(record.pointerId) && pointers.size < 32) pointers.set(record.pointerId, { ...record }); },
		pointerCapture(pointerId, target) { const pointer = pointers.get(pointerId); if (pointer) pointer.target = target; },
		pointerEnd(pointerId) { pointers.delete(pointerId); },
		drain() {
			const result = { keys: [...keys.values()], pointers: [...pointers.values()] };
			for (const key of keys.keys()) quarantined.add(key);
			keys.clear(); pointers.clear(); return result;
		},
		clear() { keys.clear(); pointers.clear(); quarantined.clear(); },
		size() { return { keys: keys.size, pointers: pointers.size, quarantined: quarantined.size }; },
	};
}
