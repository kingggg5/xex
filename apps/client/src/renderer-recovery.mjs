/** Show the engine's automatic restore state and expose a clean reload fallback. */
export function createRendererRecoveryController({
	onLost,
	onRestored,
	onReloadAvailable,
	schedule = setTimeout,
	cancel = clearTimeout,
	delayMs = 8_000,
}) {
	let timer = null;
	return {
		contextLost() {
			onLost();
			if (timer !== null) cancel(timer);
			timer = schedule(() => {
				timer = null;
				onReloadAvailable();
			}, delayMs);
		},
		contextRestored() {
			if (timer !== null) cancel(timer);
			timer = null;
			onRestored();
		},
	};
}
