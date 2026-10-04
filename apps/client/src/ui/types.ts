import type { CommunityState,CommunityAction } from "../community";
import type { ChatSnapshot, ChatTab } from "../chat";
import type { HudSnapshot, HudCommands } from "./hud-types";
import type { PanelSnapshot, PanelCommands } from "./panel-types";
import type { CombatView, DeathView, PanelResourceMap, ResourceKey, UiTransaction, CombatReadability, InventoryInstanceEntry } from "./combat-model";

export type UiLanguage = "en" | "th";
export type InventoryAction = "equip" | "use" | "open";
export type CosmeticSlot = "skin" | "pet";

export interface InventoryEntry {
	slot: number;
	id: string;
	label: string;
	count: number;
	action: InventoryAction | null;
	isPotion: boolean;
}

export interface InventorySnapshot {
	revision:number|null;
	instances:InventoryInstanceEntry[];
	instanceMovesSupported:boolean;
	language: UiLanguage;
	online: boolean;
	loading: boolean;
	items: InventoryEntry[];
	pouch: Array<{ id: string; label: string; count: number }>;
	potionPending: boolean;
	potionReadyAtMs: number;
	potionUnavailable: boolean;
}

export interface ShopEntry {
	id: string;
	label: string;
	slot: "item" | CosmeticSlot;
	price: number;
	currency: "gold" | "coin";
	color: string | null;
}

export interface ShopBox {
	id: string;
	label: string;
	price: number;
	currency: "gold" | "coin";
	odds: Array<{ id: string; label: string; amount: number; weight: number }>;
}

export interface ShopCatalog {
	entries: ShopEntry[];
	boxes: ShopBox[];
}

export interface ShopSnapshot {
	language: UiLanguage;
	online: boolean;
	status: "loading" | "ready" | "unavailable";
	catalog: ShopCatalog;
	wallet: { gold: number; coin: number; ownedCosmetics: string[]; skin: string | null; pet: string | null; bagCounts: Record<string, number> };
}

/** This boundary deliberately contains only JSON-shaped values, never engine objects. */
export interface UiSnapshot {
	combat: CombatView;
	death: DeathView;
	resources: PanelResourceMap;
	transactions: UiTransaction[];
	readability: CombatReadability;
	readabilitySupported: boolean;
	resourceRefreshSupported: boolean;
	community: CommunityState | null;
	communityPending: boolean;
	language: UiLanguage;
	online: boolean;
	modal: string | null;
	title: string;
	inventory: InventorySnapshot;
	shop: ShopSnapshot;
	chat: ChatSnapshot;
	hud: HudSnapshot;
	panels: PanelSnapshot;
}

/** Commands are separate from reactive data and retain the existing GameHud hooks. */
export interface UiCommands {
	moveItemInstance(instanceId:string,expectedRevision:number,to:"bag"|"weapon"|"armor"):void;
	returnToTown(): void;
	refreshResource(key: ResourceKey): void;
	readabilityChanged(value: CombatReadability): void;
	community(action:CommunityAction):void;
	closeModal(): void;
	inventoryAction(id: string, action: InventoryAction): void;
	buy(id: string): void;
	openBox(id: string): void;
	equip(slot: CosmeticSlot, id: string): void;
	chatTab(tab: ChatTab): void;
	chatSend(text: string): boolean;
	chatExpanded(expanded: boolean): void;
	hud: HudCommands;
	panels: PanelCommands;
}
