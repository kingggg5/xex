import { flushSync, mount, unmount } from "svelte";
import { getChatSnapshot, selectChatTab, submitChatText, subscribeChat } from "../chat";
import ModalHost from "./ModalHost.svelte";
import Chat from "./Chat.svelte";
import Hud from "./Hud.svelte";
import CombatLayer from "./CombatLayer.svelte";
import { emptyCombatView, emptyDeathView, createResourceStates, DEFAULT_COMBAT_READABILITY } from "./combat-model";
import { createHudSnapshot } from "./hud-types";
import type { HudSnapshot } from "./hud-types";
import { createPanelSnapshot } from "./panel-data";
import type { PanelSnapshot } from "./panel-types";
import type { UiSnapshot, UiCommands, InventorySnapshot, ShopSnapshot, UiLanguage } from "./types";

export interface UiDomBridge {
	update(patch: Partial<UiSnapshot>): void;
	updateHud(patch: Partial<HudSnapshot>): void;
	updatePanels(patch: Partial<PanelSnapshot>): void;
	openModal(name: string, title: string): HTMLElement;
	closeModal(): void;
	unmount(): void;
}

function primitiveData(value: unknown, depth = 0): void {
	if (depth > 8) throw new TypeError("UI data exceeds its nesting limit");
	if (value === null || typeof value === "boolean" || typeof value === "string") return;
	if (typeof value === "number" && Number.isFinite(value)) return;
	if (typeof value !== "object" || (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null && !Array.isArray(value))) throw new TypeError("UI bridge accepts plain primitive data only");
	const entries = Object.values(value as object);
	if (entries.length > 256) throw new TypeError("UI collection exceeds its bound");
	for (const entry of entries) primitiveData(entry, depth + 1);
}

export function mountGameUi(hudRoot: HTMLElement, modalRoot: HTMLElement, chatRoot: HTMLElement, language: UiLanguage, commands: Omit<UiCommands, "chatTab" | "chatSend">): UiDomBridge {
	const inventory: InventorySnapshot = { language, online: false, loading: false, revision:null,instances:[],instanceMovesSupported:false,items: [], pouch: [], potionPending: false, potionReadyAtMs: 0, potionUnavailable: false };
	const shop: ShopSnapshot = { language, online: false, status: "loading", catalog: { entries: [], boxes: [] }, wallet: { gold: 0, coin: 0, ownedCosmetics: [], skin: null, pet: null, bagCounts: {} } };
	const state = $state<UiSnapshot>({ language, online: false, combat:emptyCombatView(), death:emptyDeathView(), resources:createResourceStates(), transactions:[], readability:{...DEFAULT_COMBAT_READABILITY}, readabilitySupported:false, resourceRefreshSupported:false, community:null, communityPending:false, modal: null, title: "Xexoria", inventory, shop, chat: getChatSnapshot(), hud: createHudSnapshot(language), panels: createPanelSnapshot(language) });
	const actions: UiCommands = { ...commands, chatTab: selectChatTab, chatSend: submitChatText };
	const signatures = new Map<keyof UiSnapshot, string>();
	let disposed = false;
	let previousFocus: HTMLElement | null = null;
	modalRoot.replaceChildren();
	chatRoot.replaceChildren();
	const baselineReview = import.meta.env.DEV && new URLSearchParams(location.search).get("uiThemeReview") === "baseline";
	const reviewV1 = import.meta.env.DEV && new URLSearchParams(location.search).get("uiThemeReview") === "astral-v1";
	hudRoot.dataset.uiTheme = baselineReview ? "legacy" : "astral";
	hudRoot.dataset.uiPass = reviewV1 ? "v1" : "v2";
	let hud = mount(Hud, { target: hudRoot, props: { view: state.hud, commands: actions.hud, reviewV1 } });
	chatRoot.classList.add("svelte-chat-host", "chat-live");
	const modal = mount(ModalHost, { target: modalRoot, props: { view: state, commands: actions } });
	let chat = mount(Chat, { target: chatRoot, props: { view: state, commands: actions } });
	const combatRoot = document.createElement("div");
	combatRoot.id = "combat-ui-host";
	combatRoot.style.cssText = "position:absolute;inset:0;z-index:5;pointer-events:none";
	(hudRoot.parentElement ?? hudRoot).append(combatRoot);
	const combat = mount(CombatLayer, { target:combatRoot, props:{view:state,commands:actions} });
	flushSync();
	// Dead-code eliminated in production; compare real gameplay at the same origin and camera.
	if (import.meta.env.DEV && baselineReview) void Promise.all([import("./review/LegacyHud.svelte"), import("./review/LegacyChat.svelte")]).then(async ([legacyHud, legacyChat]) => {
		if (disposed) return;
		await Promise.all([unmount(hud),unmount(chat)]);
		if (disposed) return;
		hud = mount(legacyHud.default,{ target:hudRoot,props:{view:state.hud,commands:actions.hud} });
		chat = mount(legacyChat.default,{ target:chatRoot,props:{view:state,commands:actions} });
		flushSync(); hudRoot.dataset.uiReviewReady = "baseline";
	}).catch(() => { if (!disposed) hudRoot.dataset.uiReviewReady = "failed"; });
	const update = (patch: Partial<UiSnapshot>) => {
		if (disposed) return;
		primitiveData(patch);
		for (const [name, value] of Object.entries(patch)) {
			const key = name as keyof UiSnapshot;
			const signature = JSON.stringify(value);
			if (signatures.get(key) === signature) continue;
			signatures.set(key, signature);
			Object.assign(state, { [key]: structuredClone(value) });
		}
	};
	const stopChat = subscribeChat((snapshot) => update({ chat: snapshot }));
	const backdropClick = (event: MouseEvent) => { if (event.target === modalRoot) actions.closeModal(); };
	modalRoot.addEventListener("click", backdropClick);
	const nestedSignatures = new Map<string, string>();
	const updateSection = (section: "hud" | "panels", patch: Partial<HudSnapshot> | Partial<PanelSnapshot>) => {
		if (disposed) return;
		primitiveData(patch);
		for (const [name, value] of Object.entries(patch)) {
			const key = `${section}:${name}`;
			const signature = JSON.stringify(value);
			if (nestedSignatures.get(key) === signature) continue;
			nestedSignatures.set(key, signature);
			Object.assign(state[section], { [name]: structuredClone(value) });
		}
	};
	return {
		update,
		updateHud: (patch) => updateSection("hud", patch),
		updatePanels: (patch) => updateSection("panels", patch),
		openModal(name, title) {
			if (modalRoot.hidden && document.activeElement instanceof HTMLElement) previousFocus = document.activeElement;
			const changed = state.modal !== name || modalRoot.hidden;
			update({ modal: name, title });
			flushSync();
			modalRoot.hidden = false;
			if (changed) modalRoot.querySelector<HTMLButtonElement>("#modal-close")?.focus();
			return modalRoot.querySelector<HTMLElement>("#legacy-panel-content") ?? modalRoot.querySelector<HTMLElement>("#modal-content")!;
		},
		closeModal() {
			if (disposed) return;
			update({ modal: null });
			modalRoot.hidden = true;
			if (previousFocus?.isConnected) previousFocus.focus();
			previousFocus = null;
		},
		unmount() {
			if (disposed) return;
			disposed = true;
			stopChat();
			modalRoot.removeEventListener("click", backdropClick);
			signatures.clear();
			nestedSignatures.clear();
			void unmount(hud);
			void unmount(modal);
			void unmount(chat);
			void unmount(combat).then(()=>combatRoot.remove());
			chatRoot.classList.remove("svelte-chat-host", "chat-live");
			modalRoot.hidden = true;
		},
	};
}
