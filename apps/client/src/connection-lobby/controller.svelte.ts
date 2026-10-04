import { flushSync, mount, unmount } from 'svelte';
import { createBootstrapProgress, type BootstrapPhaseEvent } from '../bootstrap-progress.mjs';
import type { ChannelSelectionService } from '../connection-service.mjs';
import ConnectionLobby from './ConnectionLobby.svelte';
import { LOBBY_COPY } from './copy';
import { chosenAvailable, lobbyRooms } from './presentation.mjs';
import { createLobbyKeyQuarantine } from './key-quarantine.mjs';
import type { ConnectionLobbyController, ConnectionLobbyView, LobbyLanguage } from './types';

/** Isolated DOM surface: the model contains only bounded primitive presentation data. */
export function createConnectionLobby({ language, worldName, host: suppliedHost }: {
	language: LobbyLanguage; worldName: string; host?: HTMLElement;
}): ConnectionLobbyController {
	const game = document.getElementById('game');
	if (!(game instanceof HTMLElement)) throw new Error('Connection lobby requires #game');
	const host = suppliedHost ?? document.createElement('div');
	if (host.isConnected && host.parentElement !== game) throw new Error('Connection lobby host must be a direct child of #game');
	if (host.dataset.connectionLobbyMounted === 'true') throw new Error('Connection lobby is already mounted');
	const createdHost = !suppliedHost, attachedHost = !host.isConnected, wasHidden = host.hidden;
	if (createdHost) host.id = 'connection-lobby-root';
	if (attachedHost) game.append(host);
	const copy = LOBBY_COPY[language];
	let progress = createBootstrapProgress();
	const initial = progress.snapshot();
	const model = $state<ConnectionLobbyView>({ language, worldName: worldName.trim().slice(0, 96) || 'Verdant Frontier',
		mode: 'channels', rooms: [], latencyMs: null, autoAvailable: false, selected: null, hasSelection: false,
		loadingRooms: false, applying: false, error: '', warnings: [], canRetry: false, retrying: false,
		phases: initial.phases.map(phase => ({ ...phase })), recent: [], completed: 0, total: initial.total });
	let disposed = false, active = true, service: ChannelSelectionService | null = null, request: AbortController | null = null;
	let generation = 0, retryAction: (() => void | Promise<void>) | undefined;
	let choice: Promise<{ channel: number | null }> | null = null;
	let resolveChoice: ((value: { channel: number | null }) => void) | null = null;
	let rejectChoice: ((reason: unknown) => void) | null = null;
	let previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
	const events = new AbortController(), siblingInert = new Map<HTMLElement, boolean>();
	const quarantineEvents = new AbortController(), keyQuarantine = createLobbyKeyQuarantine();
	function ownSiblings() {
		for (const child of game!.children) if (child instanceof HTMLElement && child !== host && !siblingInert.has(child)) {
			siblingInert.set(child, child.inert); if (!child.inert) child.inert = true;
		}
	}
	function restoreSiblings() {
		for (const [node, before] of siblingInert) if (node.inert) node.inert = before;
		siblingInert.clear();
	}
	function focusSurface() {
		if (!active || disposed || game!.inert) return;
		const target = host.querySelector<HTMLElement>('[data-lobby-focus]');
		target?.focus({ preventScroll: true });
	}
	function synchronizeProgress() {
		const snapshot = progress.snapshot();
		model.phases = snapshot.phases.map(phase => ({ ...phase })); model.recent = snapshot.recent.map(phase => ({ ...phase }));
		model.completed = snapshot.completed; model.total = snapshot.total;
	}
	function cancelRequest() { generation++; request?.abort(); request = null; }
	async function bounded<T>(operation: (signal: AbortSignal) => Promise<T>, timeout: number): Promise<T> {
		const controller = new AbortController(); request = controller;
		let timer: ReturnType<typeof setTimeout> | undefined;
		try {
			return await Promise.race([operation(controller.signal), new Promise<never>((_, reject) => {
				timer = setTimeout(() => { controller.abort(); reject(new Error('timeout')); }, timeout);
				controller.signal.addEventListener('abort', () => reject(new DOMException('Connection attempt cancelled', 'AbortError')), { once: true });
			})]);
		} finally { clearTimeout(timer); if (request === controller) request = null; }
	}
	async function refresh() {
		if (disposed || !active || model.mode !== 'channels' || model.loadingRooms || model.applying || !service) return;
		const current = ++generation; model.loadingRooms = true; model.error = ''; model.warnings = [];
		try {
			const result = await bounded(signal => service!.load(signal), 8000);
			if (disposed || current !== generation) return;
			model.rooms = lobbyRooms(result.rooms, model.worldName);
			model.latencyMs = typeof result.latencyMs === 'number' && Number.isFinite(result.latencyMs) && result.latencyMs >= 0 ? result.latencyMs : null;
			model.autoAvailable = result.autoAvailable === true;
			const notices = copy.warningMessages as Readonly<Record<string, string>>;
			model.warnings = [...new Set((result.warnings ?? []).filter(value => typeof value === 'string').slice(0, 3).map(value => Object.hasOwn(notices, value) ? notices[value] : copy.warningGeneric))];
			if (!chosenAvailable(model)) {
				const first = model.rooms.find(room => room.players < room.capacity);
				model.selected = model.autoAvailable ? null : first?.channel ?? null;
				model.hasSelection = model.autoAvailable || !!first;
			}
		} catch {
			if (disposed || current !== generation) return;
			model.rooms = []; model.autoAvailable = false; model.hasSelection = false; model.latencyMs = null; model.error = copy.loadError;
		} finally { if (!disposed && current === generation) model.loadingRooms = false; }
	}
	function select(channel: number | null) {
		if (disposed || model.loadingRooms || model.applying) return;
		if (channel === null ? !model.autoAvailable : !model.rooms.some(room => room.channel === channel && room.players < room.capacity)) return;
		model.selected = channel; model.hasSelection = true; model.error = '';
	}
	async function confirm() {
		if (disposed || model.mode !== 'channels' || !service || model.applying || model.loadingRooms || !chosenAvailable(model)) return;
		const current = ++generation, channel = model.selected; model.applying = true; model.error = '';
		try {
			await bounded(signal => service!.apply(channel, signal), 12000);
			if (disposed || current !== generation) return;
			model.mode = 'loading'; model.applying = false; model.loadingRooms = false;
			resolveChoice?.({ channel }); resolveChoice = null; rejectChoice = null; flushSync(); focusSurface();
		} catch {
			if (!disposed && current === generation) model.error = copy.applyError;
		} finally { if (!disposed && current === generation) model.applying = false; }
	}
	async function retry() {
		if (disposed || model.retrying || !retryAction) return;
		const action = retryAction; model.retrying = true;
		try { await action(); } catch { if (!disposed) model.error = copy.phaseError; }
		finally { if (!disposed) model.retrying = false; }
	}
	host.hidden = false; host.dataset.connectionLobbyMounted = 'true'; ownSiblings();
	const component = mount(ConnectionLobby, { target: host, props: { model, refresh, select, confirm, retry } });
	flushSync(); focusSurface();
	// This small capture guard survives disposal only until a held gameplay key is released.
	window.addEventListener('keydown', event => {
		if (active && game!.inert) return; // The portrait gate owns this state and its releases.
		if (active && event.target !== window && event.target !== document.body && !(event.target instanceof Node && game!.contains(event.target))) return;
		if (keyQuarantine.keyDown(event, active)) { event.preventDefault(); event.stopImmediatePropagation(); }
		if (disposed && !keyQuarantine.size()) quarantineEvents.abort();
	}, { capture: true, signal: quarantineEvents.signal });
	window.addEventListener('keyup', event => {
		keyQuarantine.keyUp(event);
		if (disposed && !keyQuarantine.size()) quarantineEvents.abort();
	}, { capture: true, signal: quarantineEvents.signal });
	window.addEventListener('pagehide', () => { keyQuarantine.clear(); quarantineEvents.abort(); }, { once: true, signal: quarantineEvents.signal });
	// Svelte's delegated controls run at this host before these listeners quarantine HUD events.
	for (const type of ['keydown', 'keyup', 'keypress', 'pointerdown', 'pointerup', 'pointermove', 'pointercancel', 'mousedown', 'mouseup', 'mousemove', 'click', 'dblclick', 'contextmenu', 'touchstart', 'touchmove', 'touchend', 'wheel']) {
		host.addEventListener(type, event => {
			if (!active || game!.inert) return;
			if (event instanceof KeyboardEvent && event.key === 'Tab' && !event.ctrlKey && !event.metaKey && !event.altKey) {
				const nodes = [...host.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],select,input,[tabindex="0"]')]
					.filter(node => node.getClientRects().length > 0 && !node.closest('[hidden],[inert]'));
				const index = nodes.indexOf(document.activeElement as HTMLElement);
				if (!nodes.length) { event.preventDefault(); focusSurface(); }
				else if (event.shiftKey && index <= 0) { event.preventDefault(); nodes.at(-1)!.focus(); }
				else if (!event.shiftKey && (index === nodes.length - 1 || index < 0)) { event.preventDefault(); nodes[0].focus(); }
			}
			event.stopImmediatePropagation();
		}, { signal: events.signal });
	}
	window.addEventListener('keydown', event => {
		if (!active || disposed || game!.inert || (event.target instanceof Node && host.contains(event.target)) || event.ctrlKey || event.metaKey || event.altKey || /^F\d{1,2}$/.test(event.key)) return;
		if (event.target !== document.body && event.target !== game && !(event.target instanceof Node && game!.contains(event.target))) return;
		if (event.key === 'Tab') { event.preventDefault(); focusSurface(); } else event.preventDefault();
		event.stopImmediatePropagation();
	}, { capture: true, signal: events.signal });
	const observer = new MutationObserver(records => {
		if (!active) return;
		ownSiblings();
		if (records.some(record => record.type === 'attributes') && !game!.inert && !host.contains(document.activeElement)) focusSurface();
	});
	observer.observe(game, { childList: true, attributes: true, attributeFilter: ['inert'] });
	function ready() {
		if (disposed || !active) return;
		active = false; cancelRequest(); model.mode = 'ready'; host.hidden = true; restoreSiblings();
		if (previousFocus?.isConnected && !previousFocus.closest('[inert]')) previousFocus.focus({ preventScroll: true });
		previousFocus = null;
	}
	function dispose() {
		if (disposed) return;
		ready(); disposed = true; events.abort(); observer.disconnect();
		if (!keyQuarantine.size()) quarantineEvents.abort();
		rejectChoice?.(new DOMException('Connection lobby closed', 'AbortError')); resolveChoice = null; rejectChoice = null; retryAction = undefined;
		void unmount(component, { outro: false }); delete host.dataset.connectionLobbyMounted;
		if (createdHost || attachedHost) host.remove(); else host.hidden = wasHidden;
	}
	window.addEventListener('pagehide', dispose, { signal: events.signal });
	return {
		chooseChannel(nextService) {
			if (disposed || !active) return Promise.reject(new DOMException('Connection lobby closed', 'AbortError'));
			if (choice) return choice;
			service = nextService; model.mode = 'channels';
			choice = new Promise((resolve, reject) => { resolveChoice = resolve; rejectChoice = reject; });
			void refresh(); return choice;
		},
		beginLoading(phaseIds) {
			if (disposed || !active) return;
			cancelRequest(); progress = createBootstrapProgress(phaseIds); synchronizeProgress(); model.mode = 'loading';
			model.loadingRooms = false; model.applying = false; model.error = ''; model.canRetry = false; retryAction = undefined;
			flushSync(); focusSurface();
		},
		updatePhase(event: BootstrapPhaseEvent) { if (!disposed && active && progress.update(event)) synchronizeProgress(); },
		ready,
		showError(message, action) {
			if (disposed || !active) return;
			model.error = message.trim().slice(0, 480) || copy.phaseError; retryAction = action; model.canRetry = !!action;
			flushSync(); if (action) host.querySelector<HTMLElement>('[data-lobby-retry]')?.focus({ preventScroll: true });
		},
		dispose,
	};
}
