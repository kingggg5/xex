import { GAMEPLAY_CODES } from '../mobile-web-app/policy.mjs';

/** Bounded primitive key policy: held overlay inputs require a release or a fresh press. */
export function createLobbyKeyQuarantine() {
	const held = new Set();
	function codeOf(event) {
		const key = typeof event.key === 'string' ? event.key.toLowerCase() : '';
		return /^[a-z]$/.test(key) ? `Key${key.toUpperCase()}` : key === ' ' ? 'Space' : /^[0-9]$/.test(key) ? `Digit${key}` : event.code || event.key;
	}
	return {
		keyDown(event, active) {
			if (event.ctrlKey || event.metaKey || event.altKey) return false;
			const code = codeOf(event);
			if (!GAMEPLAY_CODES.has(code)) return false;
			if (active) { held.add(code); return false; }
			if (!held.has(code)) return false;
			if (event.repeat) return true;
			held.delete(code); return false;
		},
		keyUp(event) { held.delete(codeOf(event)); },
		size() { return held.size; },
		clear() { held.clear(); },
	};
}
