import { createConnectionLobby } from './controller.svelte';
import { BOOTSTRAP_PHASE_IDS } from '../bootstrap-progress.mjs';
import type { ChannelSelectionService } from '../connection-service.mjs';

/** Explicit synthetic data for visual and input-isolation review; no world/server requests. */
const query = new URLSearchParams(location.search);
const language = query.get('lang') === 'th' ? 'th' : 'en';
const scenario = query.get('scenario') ?? 'channels';
const lobby = createConnectionLobby({ language, worldName: 'Verdant Frontier' });
function delay(ms: number, signal?: AbortSignal): Promise<void> {
	return new Promise((resolve, reject) => {
		if (signal?.aborted) { reject(new DOMException('Cancelled', 'AbortError')); return; }
		const timer = setTimeout(resolve, ms);
		signal?.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); }, { once: true });
	});
}
const service: ChannelSelectionService = {
	async load(signal) {
		await delay(scenario === 'slow' ? 10000 : 180, signal);
		if (scenario === 'load-error') throw new Error('Synthetic fixture failure');
		const rooms = scenario === 'empty' ? [] : Array.from({ length: 20 }, (_, channel) => ({ channel, name: channel === 0 ? 'East Grove' : 'Verdant Frontier', players: scenario === 'full' || channel === 3 ? 50 : [14, 31, 4, 50, 22, 9, 43, 18][channel % 8], capacity: 50 }));
		return { rooms, latencyMs: query.has('unknown-ping') ? null : 38, autoAvailable: scenario !== 'empty' && scenario !== 'full' };
	},
	async apply(_channel, signal) { await delay(300, signal); if (scenario === 'apply-error') throw new Error('Synthetic fixture rejection'); },
};
function staticLoading(error = false) {
	lobby.beginLoading();
	for (const id of BOOTSTRAP_PHASE_IDS.slice(0, 3)) { lobby.updatePhase({ id, state: 'active' }); lobby.updatePhase({ id, state: 'complete' }); }
	lobby.updatePhase({ id: 'assets', state: 'active', resource: 'verdant-city.glb', loaded: 3460300, total: 7340032 });
	if (error) {
		lobby.updatePhase({ id: 'assets', state: 'error', errorCode: 'asset_failed' });
		lobby.showError(language === 'th' ? 'โหลดทรัพยากรโลกไม่ได้ โปรดลองอีกครั้ง' : 'World assets could not be loaded. Try again.', () => staticLoading());
	}
}
if (scenario === 'loading' || scenario === 'error') staticLoading(scenario === 'error');
else void lobby.chooseChannel(service).then(() => staticLoading()).catch(() => {});
let keyLeaks = 0, pointerLeaks = 0;
window.addEventListener('keydown', () => { document.body.dataset.keyLeaks = String(++keyLeaks); });
window.addEventListener('pointerdown', () => { document.body.dataset.pointerLeaks = String(++pointerLeaks); });
(window as Window & { connectionLobbyFixture?: typeof lobby }).connectionLobbyFixture = lobby;
if (import.meta.hot) import.meta.hot.dispose(() => lobby.dispose());
