const CONTENT_MISMATCH_RELOAD_KEY = "aetherfield-content-mismatch-reload-once";

/** @param {{ getItem(key: string): string | null, setItem(key: string, value: string): void } | null} storage @param {string | bigint} clientHash */
export function shouldReloadContentMismatch(storage, clientHash) {
	try {
		if (!storage) return false;
		const hash = String(clientHash);
		if (storage.getItem(CONTENT_MISMATCH_RELOAD_KEY) === hash) return false;
		storage.setItem(CONTENT_MISMATCH_RELOAD_KEY, hash);
		return true;
	} catch {
		// If storage is unavailable, prefer a visible mismatch error to a reload loop.
		return false;
	}
}

/** @param {{ removeItem(key: string): void } | null} storage */
export function clearContentMismatchReload(storage) {
	try {
		storage?.removeItem(CONTENT_MISMATCH_RELOAD_KEY);
	} catch {
		// Clearing is best-effort; it must never block a correctly matched boot.
	}
}
