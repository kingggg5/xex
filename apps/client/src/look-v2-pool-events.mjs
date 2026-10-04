// Dressing publishes only emitter changes after metadata, matrices and enabled state agree.
// Readiness is remembered because the DEV look module can load after dressing finishes.
const channels = new WeakMap();
function channel(scene) {
	let value = channels.get(scene);
	if (!value) { value = { ready: false, listeners: new Set() }; channels.set(scene, value); }
	return value;
}
export function markLookV2DressingReady(scene) {
	const value = channel(scene);
	if (value.ready) return;
	value.ready = true;
	for (const listener of value.listeners) listener(null);
}
export function notifyLookV2PoolEmitterChanged(mesh) {
	const value = channels.get(mesh.getScene());
	if (value) for (const listener of value.listeners) listener(mesh);
}
export function subscribeLookV2PoolEvents(scene, listener) {
	const value = channel(scene);
	value.listeners.add(listener);
	if (value.ready) listener(null);
	return () => value.listeners.delete(listener);
}
