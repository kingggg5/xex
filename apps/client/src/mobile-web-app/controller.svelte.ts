import { flushSync, mount, unmount } from 'svelte';
import MobileWebAppOverlay from './MobileWebAppOverlay.svelte';
import { createHeldInputLedger, keepGuideEntry, mobileWebAppPolicy, type HeldKey, type HeldPointer } from './policy.mjs';
import { releaseHeldInputs } from './input-release.mjs';
import type { MobileWebAppController, MobileWebAppView } from './types';

/** Boot-safe DOM overlay. No renderer, game state, private HUD methods or service worker. */
export function createMobileWebApp({ language }: { language: 'th' | 'en' }): MobileWebAppController {
	const gameElement = document.getElementById('game');
	if (!(gameElement instanceof HTMLElement)) throw new Error('Mobile web-app gate requires #game');
	const game: HTMLElement = gameElement;
	const providedHost = document.getElementById('mobile-web-app-root');
	const host = providedHost ?? document.createElement('div');
	if (game.contains(host)) throw new Error('Mobile web-app host must be outside #game');
	if (host.dataset.mobileWebAppMounted === 'true') throw new Error('Mobile web-app gate is already mounted');
	const hostWasHidden = host.hidden;
	if (!providedHost) { host.id = 'mobile-web-app-root'; document.body.append(host); }
	host.hidden = false; host.dataset.mobileWebAppMounted = 'true';
	const events = new AbortController(), listeners = new Set<(blocked: boolean) => void>();
	const held = createHeldInputLedger();
	const standaloneQuery = window.matchMedia('(display-mode: standalone)'), coarseQuery = window.matchMedia('(any-pointer: coarse)');
	const model = $state<MobileWebAppView>({ language, portrait: false, standalone: false, guideOpen: false });
	let blocked = false, disposed = false, ownRelease = false, previousInert = game.inert, inertOwned = false;
	let previousFocus: HTMLElement | null = null, frame = 0, lockOwned = false;
	const entryNodes = new Map<HTMLElement, HTMLButtonElement>();
	const orientation = window.screen.orientation as (ScreenOrientation & { lock?: (type: 'landscape') => Promise<void> }) | undefined;
	function readPolicy() {
		return mobileWebAppPolicy({ width: window.innerWidth, height: window.innerHeight, coarse: coarseQuery.matches, maxTouchPoints: navigator.maxTouchPoints,
			orientationType: orientation?.type, legacyAngle: (window as Window & { orientation?: number }).orientation,
			displayStandalone: standaloneQuery.matches, navigatorStandalone: (navigator as Navigator & { standalone?: boolean }).standalone, guideOpen: model.guideOpen });
	}
	function ownsTarget(target: EventTarget | null) { return target instanceof Node && host.contains(target); }
	function releaseInputs() {
		ownRelease = true;
		try {
			releaseHeldInputs(held, {
				keyUp: record => new KeyboardEvent('keyup', { ...record, bubbles: true, cancelable: true, repeat: false }),
				pointerCancel: record => typeof PointerEvent === 'undefined' ? null : new PointerEvent('pointercancel', { ...record, bubbles: true, cancelable: true, buttons: 0 }),
				isDisconnected: target => target instanceof Node && !target.isConnected,
				globalKeyUp: record => window.dispatchEvent(new KeyboardEvent('keyup', { ...record, bubbles: true, cancelable: true, repeat: false })),
			});
		} finally { ownRelease = false; }
	}
	function focusOverlay() {
		if (!blocked || disposed) return;
		const dialog = host.querySelector<HTMLElement>('[data-mobile-web-app-dialog]');
		(dialog?.querySelector<HTMLElement>('[data-mobile-web-app-focus]') ?? dialog)?.focus({ preventScroll: true });
	}
	function restoreFocus() {
		if (previousFocus?.isConnected && !previousFocus.closest('[inert]')) previousFocus.focus({ preventScroll: true });
		previousFocus = null;
	}
	function publishBlock(next: boolean) {
		if (next === blocked) return;
		blocked = next;
		if (next) {
			previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
			releaseInputs(); previousInert = game.inert; game.inert = true; inertOwned = true;
		} else if (inertOwned) { game.inert = previousInert; inertOwned = false; }
		host.dataset.mobileWebAppBlocked = String(next);
		for (const listener of [...listeners]) { try { listener(next); } catch (error) { console.error('Mobile web-app block callback failed', error); } }
	}
	function synchronize() {
		if (disposed) return;
		const beforeGuide = model.guideOpen, beforePortrait = model.portrait, policy = readPolicy();
		model.portrait = policy.portrait; model.standalone = policy.standalone;
		if (model.standalone) model.guideOpen = false;
		const wasBlocked = blocked; publishBlock(model.portrait || model.guideOpen);
		flushSync(); updateEntries();
		if (blocked && (!wasBlocked || beforeGuide !== model.guideOpen || beforePortrait !== model.portrait)) focusOverlay();
		else if (wasBlocked && !blocked) restoreFocus();
	}
	function openGuide() { if (disposed || model.standalone) return; model.guideOpen = true; synchronize(); focusOverlay(); }
	function closeGuide() { if (disposed) return; model.guideOpen = false; synchronize(); if (blocked) focusOverlay(); }
	const component = mount(MobileWebAppOverlay, { target: host, props: { model, openGuide, closeGuide } });
	function addEntry(container: HTMLElement, context: 'login' | 'settings') {
		let node = entryNodes.get(container);
		if (!node || !node.isConnected) {
			node?.removeEventListener('click', openGuide);
			node = document.createElement('button'); node.type = 'button'; node.dataset.mobileWebAppEntry = 'true'; node.dataset.mobileWebAppContext = context;
			node.textContent = language === 'th' ? 'คู่มือ iPhone / iPad: เพิ่มบนหน้าจอโฮม' : 'iPhone / iPad: Home Screen guide';
			node.addEventListener('click', openGuide); container.append(node); entryNodes.set(container, node);
		}
		return node;
	}
	function updateEntries() {
		const installEntryVisible = !model.standalone && !model.portrait;
		const login = document.getElementById('login-screen');
		const loginTarget = login instanceof HTMLElement ? login.querySelector<HTMLElement>('.login-card') ?? login : null;
		const settings = document.getElementById('settings-ui-scale')?.closest<HTMLElement>('#modal-content, .modal-content') ?? null;
		for (const [container, node] of entryNodes) {
			const kind = node.dataset.mobileWebAppContext ?? '';
			if (!keepGuideEntry(kind, container.isConnected, kind === 'settings' ? container === settings : container === loginTarget)) {
				node.removeEventListener('click', openGuide); node.remove(); entryNodes.delete(container);
			}
		}
		if (login instanceof HTMLElement && !login.hidden && login.getClientRects().length > 0) {
			const entry = addEntry(loginTarget!, 'login'); if (entry.hidden !== !installEntryVisible) entry.hidden = !installEntryVisible;
		}
		if (settings) { const entry = addEntry(settings, 'settings'); if (entry.hidden !== !installEntryVisible) entry.hidden = !installEntryVisible; }
		if (!installEntryVisible) for (const entry of entryNodes.values()) if (!entry.hidden) entry.hidden = true;
	}
	function scheduleEntries() { if (!frame && !disposed) frame = requestAnimationFrame(() => { frame = 0; if (!disposed) updateEntries(); }); }
	const observer = new MutationObserver(records => {
		if (records.some(record => record.type === 'attributes' || [...record.addedNodes, ...record.removedNodes].some(node => node instanceof Element))) scheduleEntries();
	});
	for (const node of [document.getElementById('login-screen'), document.getElementById('modal-backdrop')]) if (node) observer.observe(node, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden','class'] });
	window.addEventListener('keydown', event => {
		if (ownsTarget(event.target)) return;
		if (held.isKeyQuarantined(event.code)) {
			if (event.repeat || blocked) { event.preventDefault(); event.stopImmediatePropagation(); return; }
			held.keyUp(event.code); // A fresh press can recover from an OS keyup lost while hidden.
		}
		if (blocked) return;
		if (event.target instanceof Element && event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
		if (!event.ctrlKey && !event.metaKey) held.keyDown({ target: event.target ?? window, code: event.code, key: event.key, location: event.location,
			ctrlKey: event.ctrlKey, altKey: event.altKey, shiftKey: event.shiftKey, metaKey: event.metaKey } satisfies HeldKey);
	}, { capture: true, signal: events.signal });
	window.addEventListener('keyup', event => { held.keyUp(event.code, ownRelease); }, { capture: true, signal: events.signal });
	window.addEventListener('pointerdown', event => {
		if (blocked || ownsTarget(event.target)) return;
		held.pointerDown({ target: event.target ?? window, pointerId: event.pointerId, pointerType: event.pointerType, isPrimary: event.isPrimary, clientX: event.clientX, clientY: event.clientY } satisfies HeldPointer);
	}, { capture: true, signal: events.signal });
	window.addEventListener('gotpointercapture', event => { if (event.target) held.pointerCapture(event.pointerId, event.target); }, { capture: true, signal: events.signal });
	for (const type of ['pointerup','pointercancel','lostpointercapture'] as const) window.addEventListener(type, event => { held.pointerEnd(event.pointerId); }, { capture: true, signal: events.signal });
	function blockActivation(event: Event) {
		if (!blocked) return;
		if (event instanceof KeyboardEvent && event.key === 'Escape' && model.guideOpen) { event.preventDefault(); event.stopImmediatePropagation(); closeGuide(); return; }
		if (ownsTarget(event.target)) return;
		if (event instanceof KeyboardEvent && (event.ctrlKey || event.metaKey)) return; // Browser shortcuts retain their native behavior.
		event.preventDefault(); event.stopImmediatePropagation();
	}
	for (const type of ['keydown','pointerdown','pointermove','mousedown','mousemove','touchstart','touchmove','click','dblclick','contextmenu','wheel']) window.addEventListener(type, blockActivation, { capture: true, passive: false, signal: events.signal });
	window.addEventListener('keydown', event => {
		if (!blocked) return;
		if (event.key === 'Escape' && model.guideOpen) { event.preventDefault(); event.stopImmediatePropagation(); closeGuide(); return; }
		if (event.key !== 'Tab') {
			// Guide keyboard defaults may work; gameplay listeners on window must never see them.
			if (ownsTarget(event.target) && !event.ctrlKey && !event.metaKey) event.stopImmediatePropagation();
			return;
		}
		event.preventDefault(); event.stopImmediatePropagation();
		const dialog = host.querySelector<HTMLElement>('[data-mobile-web-app-dialog]');
		const nodes = [...(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],[tabindex="0"]') ?? [])].filter(node => node.getClientRects().length > 0);
		if (!nodes.length) { dialog?.focus({ preventScroll: true }); return; }
		const index = nodes.indexOf(document.activeElement as HTMLElement), step = event.shiftKey ? -1 : 1;
		nodes[(index + step + nodes.length) % nodes.length].focus({ preventScroll: true });
	}, { capture: true, signal: events.signal });
	window.addEventListener('resize', synchronize, { passive: true, signal: events.signal });
	window.addEventListener('orientationchange', synchronize, { passive: true, signal: events.signal });
	window.visualViewport?.addEventListener('resize', synchronize, { passive: true, signal: events.signal });
	orientation?.addEventListener('change', synchronize, { signal: events.signal });
	for (const query of [standaloneQuery, coarseQuery]) query.addEventListener('change', synchronize, { signal: events.signal });
	document.addEventListener('visibilitychange', () => { if (document.hidden) releaseInputs(); else synchronize(); }, { signal: events.signal });
	document.addEventListener('fullscreenchange', () => {
		if (document.fullscreenElement && typeof orientation?.lock === 'function') {
			void orientation.lock('landscape').then(() => { lockOwned = true; if (disposed) { orientation.unlock(); lockOwned = false; } }).catch(() => { /* Manual rotation remains the supported path. */ });
		}
		synchronize();
	}, { signal: events.signal });
	function dispose() {
		if (disposed) return; releaseInputs(); disposed = true; events.abort(); observer.disconnect(); cancelAnimationFrame(frame);
		if (inertOwned) { game.inert = previousInert; inertOwned = false; }
		if (lockOwned) { try { orientation?.unlock(); } catch { /* Already released by the browser. */ } lockOwned = false; }
		for (const entry of entryNodes.values()) { entry.removeEventListener('click', openGuide); entry.remove(); } entryNodes.clear(); held.clear(); listeners.clear();
		void unmount(component, { outro: false }); delete host.dataset.mobileWebAppMounted; delete host.dataset.mobileWebAppBlocked;
		if (!providedHost) host.remove(); else host.hidden = hostWasHidden;
		if (!document.hidden) restoreFocus();
	}
	window.addEventListener('pagehide', dispose, { signal: events.signal });
	synchronize();
	return { isBlocked: () => !disposed && blocked, openGuide,
		onBlockedChange(callback) { if (disposed) return () => {}; listeners.add(callback); callback(blocked); return () => listeners.delete(callback); }, dispose };
}
