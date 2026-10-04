import type { CharacterStateMessage, DialogueMessage, PartyStateMessage, QuestStateMessage } from "../cold_v4.gen";
import type { FriendEntry, GroupInfo } from "../social-ui";
import type { ChannelState } from "../rooms-ui";
import { isChannelId, isRoomRow } from "../rooms-ui";
import { sanitizeTowerState } from "../tower-ui";
import type { TowerState } from "../tower-ui";
import type { WorldRouteDefinition } from "../world-layout";
import { parseFriendEntries, parseGroupInfo } from "../social-parse.mjs";
import { applyPrefs, DEFAULT_PREFS, loadPrefs, savePrefs } from "../settings";
import { getGraphicsPreference, setGraphicsPreference, subscribeGraphicsPreference, resolveGraphicsPreset } from "../graphics-quality.mjs";
import { getEnvironmentPreference, setEnvironmentPreference, subscribeEnvironmentPreference } from "../world-environment-state.mjs";
import type { UiLanguage } from "./types";
import { parseItemInstances } from "./combat-model";
import type { CharacterPanelSnapshot, DialoguePanelSnapshot, GraphicsChoice, JournalPanelSnapshot, MapPanelSnapshot, PanelSnapshot, PartyPanelSnapshot, PresencePanelEntry, RoomPanelSnapshot, SettingsPreferencesSnapshot, UserPreferences, WeatherChoice } from "./panel-types";

export const MAX_PANEL_ROWS = 80;
export const MAX_PANEL_ROOMS = 64;
const STAT_KEYS = ["str", "agi", "vit", "int", "dex", "luk"] as const;
const QUEST_ROUTE = ["entry", "regroup", "sella", "windmark_1", "windmark_2", "windmark_3", "hunt_clearing"];
const finite = (value: number | undefined, fallback = 0): number => typeof value === "number" && Number.isFinite(value) ? value : fallback;
const amount = (value: number | undefined): number => Math.max(0, Math.trunc(finite(value)));
const text = (value: string | undefined, limit = 200): string => (value ?? "").slice(0, limit);
const optionalUint = (value: unknown): number | undefined => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= 65535 ? value : undefined;
function optionalStats(value: unknown): CharacterPanelSnapshot["statsBase"] {
	if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
	const source = value as Record<string, unknown>;
	if (STAT_KEYS.some(key => optionalUint(source[key]) === undefined)) return undefined;
	return Object.fromEntries(STAT_KEYS.map(key => [key, source[key]])) as NonNullable<CharacterPanelSnapshot["statsBase"]>;
}

export function characterPanelData(state: CharacterStateMessage | null, itemName: (id: string) => string, refinementAvailable = true): CharacterPanelSnapshot | null {
	if (!state) return null;
	const gold = amount(state.gold);
	// These optional facts are delivered by the server. Absence never becomes an invented zero/breakdown.
	const extra = state as CharacterStateMessage & { vocation?: unknown; combat_profile?: unknown; magic_power?: unknown; stats_base?: unknown; stats_allocated?: unknown; equipment_bonus?: unknown };
	const instances = parseItemInstances(state.item_instances, itemName);
	const equipmentBonus = extra.equipment_bonus && typeof extra.equipment_bonus === "object" && !Array.isArray(extra.equipment_bonus) ? extra.equipment_bonus as Record<string, unknown> : null;
	const equipmentAttack = optionalUint(equipmentBonus?.atk), equipmentDefense = optionalUint(equipmentBonus?.def), equipmentHp = optionalUint(equipmentBonus?.max_hp);
	return {
		revision: amount(state.rev),
		...(typeof state.coin === "number" && Number.isSafeInteger(state.coin) && state.coin >= 0 ? { coin: amount(state.coin) } : {}),
		...(typeof extra.vocation === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(extra.vocation) ? { vocation: extra.vocation } : {}),
		...(extra.combat_profile === "trailblade" || extra.combat_profile === "mage_trial" ? { combatProfile: extra.combat_profile } : {}),
		...(optionalUint(extra.magic_power) !== undefined ? { magicPower: optionalUint(extra.magic_power) } : {}),
		...(optionalStats(extra.stats_base) ? { statsBase: optionalStats(extra.stats_base) } : {}),
		...(optionalStats(extra.stats_allocated) ? { statsAllocated: optionalStats(extra.stats_allocated) } : {}),
		...(equipmentAttack !== undefined && equipmentDefense !== undefined && equipmentHp !== undefined ? { equipmentBonus: { attack: equipmentAttack, defense: equipmentDefense, maxHp: equipmentHp } } : {}),
		name: text(state.name, 48), handle: text(state.handle, 32), level: amount(state.level), jobLevel: amount(state.job_level), attack: amount(state.atk), defense: amount(state.def),
		hp: amount(state.hp), maxHp: amount(state.max_hp), sp: state.sp === undefined ? null : amount(state.sp), maxSp: state.max_sp === undefined ? null : amount(state.max_sp),
		baseExp: amount(state.exp), baseExpNext: Math.max(1, amount(state.base_exp_next)), jobExp: amount(state.job_exp), jobExpNext: Math.max(1, amount(state.job_exp_next)),
		statPoints: amount(state.stat_points), stats: Object.fromEntries(STAT_KEYS.map((key) => [key, amount(state.stats?.[key])])) as CharacterPanelSnapshot["stats"], gold,
		equipment: (state.equipment ?? []).slice(0, MAX_PANEL_ROWS).filter((entry) => entry.slot === "weapon" || entry.slot === "armor").map((entry) => {
			const slot = entry.slot as "weapon" | "armor";
			const refine = Math.min(10, amount(state.refine?.[slot]));
			const refineCost = (refine + 1) * 30;
			const copy = instances?.find(instance => instance.location === slot && instance.id === entry.item && instance.refine === refine);
			return { slot, item: text(entry.item), label: text(itemName(entry.item)), refine, refineCost, successPercent: refine < 4 ? 100 : Math.max(20, 110 - refine * 10), canRefine: refinementAvailable && refine < 10 && gold >= refineCost && (state.item_instances === undefined || !!copy), ...(copy && Number.isSafeInteger(state.rev) && state.rev > 0 ? { instanceId: copy.instanceId, expectedRevision: state.rev } : {}) };
		}),
	};
}

export function partyPanelData(state: PartyStateMessage | null): PartyPanelSnapshot | null {
	return state ? { code: text(state.code, 6), leader: amount(state.leader), expiresSeconds: amount(state.expires_s), members: state.members.slice(0, MAX_PANEL_ROWS).map((member) => ({ id: amount(member.id), name: text(member.name, 48) })) } : null;
}

export function dialoguePanelData(message: DialogueMessage, line: string, quest: string, translate: (key: string) => string, language: UiLanguage): DialoguePanelSnapshot {
	return { npc: text(message.npc), token: text(message.token, 512), quest: text(quest), text: text(line, 4000), choices: message.choices.slice(0, MAX_PANEL_ROWS).map((choice) => ({ id: text(choice.id), label: choice.id === "claim" ? (language === "th" ? "รับรางวัล" : "Claim reward") : text(translate(choice.label_key), 400) })) };
}

export function presencePanelData(entries: FriendEntry[]): PresencePanelEntry[] {
	return parseFriendEntries(entries.slice(0, MAX_PANEL_ROWS).map((entry) => ({ ...entry, in_tower: entry.inTower }))).map((entry) => ({ device:entry.device??"unknown", handle: entry.handle, name: entry.name, online: entry.online, channel: entry.channel, tower: entry.tower, inTower: entry.inTower }));
}

export function groupPanelData(group: GroupInfo | null): PanelSnapshot["group"] {
	const parsed = group === null ? null : parseGroupInfo({ ...group, members: group.members.map((member) => ({ ...member, in_tower: member.inTower })) });
	return parsed ? { code: parsed.code, members: presencePanelData(parsed.members) } : null;
}

export function roomPanelData(state: ChannelState, status: RoomPanelSnapshot["status"] = state.rooms === null ? "unavailable" : "ready"): RoomPanelSnapshot {
	return { status, current: isChannelId(state.current) ? state.current : null, rooms: (state.rooms ?? []).filter(isRoomRow).slice(0, MAX_PANEL_ROOMS).map((room) => ({ channel: room.channel, players: room.players, capacity: room.capacity })) };
}

export function journalPanelData(state: QuestStateMessage | null, questName: (id: string) => string): JournalPanelSnapshot | null {
	return state ? { quest: text(questName(state.quest)), state: text(state.state), objectives: Object.entries(state.objectives ?? {}).slice(0, MAX_PANEL_ROWS).map(([id, count]) => ({ id: text(id), label: text(id.replaceAll("_", " ")), count: amount(count) })) } : null;
}

export function presenceLabel(entry: PresencePanelEntry, language: UiLanguage): string {
	const th = language === "th";
	if (entry.inTower || entry.tower !== null) return entry.tower !== null && entry.tower > 0 ? (th ? `หอคอย ชั้น ${entry.tower}` : `Tower F${entry.tower}`) : th ? "หอคอย" : "Tower";
	if (entry.channel !== null) return th ? `ห้อง ${entry.channel + 1}` : `Room ${entry.channel + 1}`;
	return entry.online ? (th ? "ออนไลน์" : "Online") : th ? "ออฟไลน์" : "Offline";
}

export function mapPanelData(points: Record<string, { x: number; z: number }>, extent: number, routes: WorldRouteDefinition[], player: { x: number; z: number }, members: FriendEntry[], tower: TowerState, language: UiLanguage): MapPanelSnapshot {
	const validPoints = Object.entries(points).slice(0, MAX_PANEL_ROWS).filter(([, point]) => Number.isFinite(point.x) && Number.isFinite(point.z));
	return {
		extent: Math.max(1, finite(extent, 28)), player: { x: finite(player.x), z: finite(player.z) },
		points: validPoints.map(([id, point]) => ({ id: text(id), label: poiLabel(id, language), x: point.x, z: point.z, color: poiColor(id), radius: id === "sella" ? 5.5 : /^windmark_/.test(id) ? 4 : 3.5 })),
		routes: routes.slice(0, MAX_PANEL_ROOMS).map((route) => ({ id: text(route.id), points: route.points.slice(0, MAX_PANEL_ROWS).filter(([x, z]) => Number.isFinite(x) && Number.isFinite(z)).map(([x, z]) => ({ x, z })) })),
		questRoute: QUEST_ROUTE.map((id) => points[id]).filter((point) => point && Number.isFinite(point.x) && Number.isFinite(point.z)).map((point) => ({ x: point.x, z: point.z })),
		members: presencePanelData(members), inTower: tower.inTower, towerFloor: amount(tower.floor),
	};
}

export function projectPanelCoordinate(value: number, extent: number): number {
	const safe = Math.max(1, finite(extent, 28));
	return Math.round((Math.max(-safe, Math.min(safe, finite(value))) / safe * 0.5 + 0.5) * 3400) / 10;
}

function poiLabel(id: string, language: UiLanguage): string {
	const names: Record<string, [string, string]> = { entry: ["Entry", "จุดเริ่มทาง"], regroup: ["Regroup", "จุดรวมพล"], sella: ["Sella", "เซลล่า"], south_trail_marker: ["South Trail Marker", "เสาหินบอกทางใต้"], hunt_clearing: ["Hunt Clearing", "ลานล่า"], lookout: ["Lookout", "จุดเฝ้ายาม"] };
	if (names[id]) return names[id][language === "th" ? 1 : 0];
	const windmark = id.match(/^windmark_(\d+)$/);
	return windmark ? (language === "th" ? `เครื่องหมายลม ${windmark[1]}` : `Windmark ${windmark[1]}`) : text(id.replaceAll("_", " "));
}

function poiColor(id: string): string {
	return id === "sella" ? "#f4d27d" : /^windmark_/.test(id) ? "#8ee4ee" : id === "hunt_clearing" ? "#a9e08c" : id === "south_trail_marker" ? "#d2b7e8" : "#d9d2b8";
}

export function settingsPanelData(language: UiLanguage): SettingsPreferencesSnapshot {
	const graphics = getGraphicsPreference();
	const mobile = typeof window !== "undefined" && window.matchMedia("(max-width: 767px), (pointer: coarse) and (max-width: 900px)").matches;
	const active = resolveGraphicsPreset(graphics, { formFactor: mobile ? "mobile" : "desktop", width: typeof window === "undefined" ? 1280 : window.innerWidth, height: typeof window === "undefined" ? 720 : window.innerHeight, devicePixelRatio: typeof window === "undefined" ? 1 : window.devicePixelRatio });
	const th = language === "th";
	const automatic = graphics === null ? (th ? "แนะนำสำหรับหน้าจอนี้: " : "Recommended for this screen: ") : "";
	const environment = getEnvironmentPreference();
	return { prefs: { ...loadPrefs() }, graphics, graphicsSummary: `${automatic}${active.label} · ${th ? `เป้าหมาย ${active.targetFps} FPS` : `${active.targetFps} FPS target`}${mobile ? (th ? " · ปรับรายละเอียดสำหรับมือถือ" : " · Mobile detail limits") : ""}`, weather: environment.weather as WeatherChoice, cycle: environment.cycle };
}

/** One mounted settings component owns these listeners and releases every one. */
export function observeSettingsPreferences(language: UiLanguage, emit: (snapshot: SettingsPreferencesSnapshot) => void): () => void {
	let disposed = false;
	const refresh = (): void => { if (!disposed) emit(settingsPanelData(language)); };
	const stopGraphics = subscribeGraphicsPreference(refresh);
	const stopEnvironment = subscribeEnvironmentPreference(refresh);
	let resizeTimer = 0;
	const resized = (): void => { window.clearTimeout(resizeTimer); resizeTimer = window.setTimeout(refresh, 80); };
	if (typeof window !== "undefined") window.addEventListener("resize", resized, { passive: true });
	refresh();
	return () => { disposed = true; stopGraphics(); stopEnvironment(); if (typeof window !== "undefined") { window.removeEventListener("resize", resized); window.clearTimeout(resizeTimer); } };
}

export function changeSettingsPreferences(prefs: UserPreferences): void { savePrefs(prefs); applyPrefs(prefs); }
export function changeGraphicsPreference(choice: GraphicsChoice): void { setGraphicsPreference(choice); }
export function changeEnvironmentPreference(change: { weather?: WeatherChoice; cycle?: boolean }): void { setEnvironmentPreference(change); }
export function resetPanelSettings(): void { changeSettingsPreferences({ ...DEFAULT_PREFS }); setGraphicsPreference(null); setEnvironmentPreference({ weather: "auto", cycle: true }); }

export function createPanelSnapshot(language: UiLanguage = "en"): PanelSnapshot {
	const tower = sanitizeTowerState({ inTower: false, floor: 0, bestFloor: 0 });
	return { language, online: false, character: null, party: null, dialogue: null, friends: [], group: null, tower, settings: settingsPanelData(language), rooms: roomPanelData({ current: null, rooms: null }), map: mapPanelData({}, 28, [], { x: 0, z: 0 }, [], tower, language), journal: null };
}
