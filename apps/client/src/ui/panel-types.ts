import type { UiLanguage } from "./types";

export type StatKey = "str" | "agi" | "vit" | "int" | "dex" | "luk";
export type EquipmentSlot = "weapon" | "armor";
export type PanelName = "character" | "skills" | "party" | "dialogue" | "friends" | "group" | "tower" | "settings" | "map" | "menu" | "collection" | "trade" | "battlepass" | "topup" | "bag" | "store";
export type GraphicsChoice = "low" | "medium" | "high" | "ultra" | null;
export type WeatherChoice = "auto" | "clear" | "cloudy" | "rain" | "fog";

export interface CharacterPanelSnapshot {
	revision?: number;
	vocation?: string;
	combatProfile?: "trailblade" | "mage_trial";
	magicPower?: number;
	statsBase?: Record<StatKey, number>;
	statsAllocated?: Record<StatKey, number>;
	equipmentBonus?: { attack: number; defense: number; maxHp: number };
	name: string;
	handle: string;
	level: number;
	jobLevel: number;
	attack: number;
	defense: number;
	hp: number;
	maxHp: number;
	sp: number | null;
	maxSp: number | null;
	baseExp: number;
	baseExpNext: number;
	jobExp: number;
	jobExpNext: number;
	statPoints: number;
	stats: Record<StatKey, number>;
	gold: number;
	coin?: number;
	equipment: Array<{ slot: EquipmentSlot; item: string; label: string; refine: number; refineCost: number; successPercent: number; canRefine: boolean; instanceId?: string; expectedRevision?: number }>;
}

export interface PartyPanelSnapshot {
	code: string;
	leader: number;
	expiresSeconds: number;
	members: Array<{ id: number; name: string }>;
}

export interface DialoguePanelSnapshot {
	npc: string;
	token: string;
	quest: string;
	text: string;
	choices: Array<{ id: string; label: string }>;
}

export interface PresencePanelEntry {
	device:import("../community").DeviceKind;
	handle: string;
	name: string;
	online: boolean;
	channel: number | null;
	tower: number | null;
	inTower: boolean;
}

export interface GroupPanelSnapshot {
	code: string;
	members: PresencePanelEntry[];
}

export interface TowerPanelSnapshot {
	inTower: boolean;
	floor: number;
	bestFloor: number;
}

export interface UserPreferences {
	uiScale: number;
	shake: boolean;
	flash: boolean;
	volume: number;
}

export interface SettingsPreferencesSnapshot {
	prefs: UserPreferences;
	graphics: GraphicsChoice;
	graphicsSummary: string;
	weather: WeatherChoice;
	cycle: boolean;
}

export interface RoomPanelSnapshot {
	status: "loading" | "ready" | "unavailable";
	current: number | null;
	rooms: Array<{ channel: number; players: number; capacity: number }>;
}

export interface MapPanelSnapshot {
	extent: number;
	player: { x: number; z: number };
	points: Array<{ id: string; label: string; x: number; z: number; color: string; radius: number }>;
	routes: Array<{ id: string; points: Array<{ x: number; z: number }> }>;
	questRoute: Array<{ x: number; z: number }>;
	members: PresencePanelEntry[];
	inTower: boolean;
	towerFloor: number;
}

export interface JournalPanelSnapshot {
	quest: string;
	state: string;
	objectives: Array<{ id: string; label: string; count: number }>;
}

/** Values copied from the game boundary; no live scene, DOM or callback references. */
export interface PanelSnapshot {
	selectedInventoryInstanceId?: string;
	language: UiLanguage;
	online: boolean;
	character: CharacterPanelSnapshot | null;
	party: PartyPanelSnapshot | null;
	dialogue: DialoguePanelSnapshot | null;
	friends: PresencePanelEntry[];
	group: GroupPanelSnapshot | null;
	tower: TowerPanelSnapshot;
	settings: SettingsPreferencesSnapshot;
	rooms: RoomPanelSnapshot;
	map: MapPanelSnapshot;
	journal: JournalPanelSnapshot | null;
}

/** UI intent callbacks are kept separate from snapshot values. */
export interface PanelCommands {
	openPanel(name: PanelName): void;
	closeModal(): void;
	allocateStat(stat: StatKey): void;
	refineItem(slot: EquipmentSlot, instanceId?: string, expectedRevision?: number): void;
	moveItemInstance?(instanceId: string, expectedRevision: number, to: "bag" | EquipmentSlot): void;
	selectInventoryInstance?(instanceId: string): void;
	party(action: { kind: "create" | "join" | "leave"; code?: string }): void;
	choose(npc: string, token: string, choice: string): void;
	claim(quest: string): void;
	friendAdd(handle: string): void;
	friendRemove(handle: string): void;
	groupCreate(): void;
	groupJoin(code: string): void;
	groupLeave(): void;
	towerEnter(): void;
	towerLeave(): void;
	channelPicked(channel: number | null): void;
	settingsChanged(prefs: UserPreferences): void;
	resetSettings(): void;
	graphicsChanged(choice: GraphicsChoice): void;
	environmentChanged(change: { weather?: WeatherChoice; cycle?: boolean }): void;
}
