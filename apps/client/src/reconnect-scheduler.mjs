/** One owned retry timer; failure loops back off without duplicating connection attempts. */
export function createReconnectScheduler(retry, allowed, timers = globalThis) {
	let timer = null, attempt = 0, disposed = false;
	const cancel = () => { if (timer !== null) timers.clearTimeout(timer); timer = null; };
	return {
		schedule() {
			if (disposed || !allowed() || timer !== null) return;
			const wait = Math.min(500 * 2 ** attempt, 5000);
			attempt = Math.min(attempt + 1, 4);
			timer = timers.setTimeout(() => { timer = null; if (!disposed && allowed()) void retry(); }, wait);
		},
		reset() { cancel(); attempt = 0; },
		dispose() { disposed = true; cancel(); },
	};
}
