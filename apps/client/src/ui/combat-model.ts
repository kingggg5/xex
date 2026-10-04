/** Primitive presentation boundary. Runtime owns projection, occlusion and server truth. */
export type CombatRank = "normal" | "elite" | "boss";
export interface CombatCast { label: string | null; endsAtMs: number; durationMs: number; }
export interface CombatActorPresentation {
	id: number; name: string; screenX: number; screenY: number; distance: number;
	onScreen: boolean; occluded: boolean; hp: number | null; maxHp: number | null;
	level: number | null; rank: CombatRank | null; element: string | null;
	targetingMe: boolean | null; hostile?: boolean | null; lastDamagedAtMs: number | null;
	stateChips: string[]; cast: CombatCast | null;
}
export interface CombatPresentation {
	nowMs: number; formFactor: "desktop" | "mobile"; selectedTargetId: number | null;
	actors: CombatActorPresentation[];
}
export interface CombatPlateSlot { slot: number; actor: CombatActorPresentation | null; visible: boolean; expiresAtMs: number; }
export interface CombatView {
	nowMs: number; mobile: boolean; target: CombatActorPresentation | null;
	slots: CombatPlateSlot[];
}
export interface DeathStateDTO {
	revision: number | null; down: boolean; cause: "monster" | "none" | null;
	penalty: { base_exp: number; job_exp: number; gold: number } | null;
	costs: { return_to_town: number } | null; free_return: boolean | null;
	auto_revive_at_ms: number | null;
}
export type TransactionPhase = "preview" | "submitting" | "committed" | "rejected" | "outcome-unknown";
export interface ReturnToTownResult { opId: string; deathRevision: number; state: "committed" | "rejected" | "outcome-unknown"; reason: string | null; }
export interface DeathView extends DeathStateDTO {
	confirmedRevision: number | null; confirmedDown: boolean;
	request: { opId: string; deathRevision: number; phase: TransactionPhase; reason: string | null } | null;
	online: boolean; canSubmit: boolean;
}
export const RESOURCE_KEYS = ["character", "inventory", "wallet", "shop", "friends", "group", "party", "journal", "tower", "rooms", "community"] as const;
export type ResourceKey = typeof RESOURCE_KEYS[number];
export type PanelResourceStatus = "loading" | "loaded-empty" | "loaded-data" | "stale" | "error";
export interface PanelResourceState { status: PanelResourceStatus; hasData: boolean; message: string | null; requestId: string | null; }
export type PanelResourceMap = Record<ResourceKey, PanelResourceState>;
export interface UiTransaction { resource: ResourceKey; requestId: string; phase: TransactionPhase; reason: string | null; }
export interface InventoryInstanceEntry { instanceId:string; id:string; label:string; location:"bag"|"weapon"|"armor"; refine:number; equipSlot:"weapon"|"armor"|null; }
export interface ItemMoveIntent { opId:string; instanceId:string; expectedRevision:number; to:"bag"|"weapon"|"armor"; }
export interface CombatReadability { combatTextScale: number; lowEffects: boolean; hideOtherEffects: boolean; screenShake?: boolean; }
export const DEFAULT_COMBAT_READABILITY: Readonly<CombatReadability> = Object.freeze({ combatTextScale: 1, lowEffects: false, hideOtherEffects: false, screenShake:true });

const plain = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const uint = (value: unknown, max = 0xffff_ffff): value is number => finite(value) && Number.isSafeInteger(value) && value >= 0 && value <= max;
const text = (value: unknown, maximum = 120): string | null => typeof value === "string" ? value.replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, maximum) : null;
export const validRequestId = (value: unknown): value is string => typeof value === "string" && /^[a-zA-Z0-9_-]{1,64}$/.test(value);

function actor(value: unknown): CombatActorPresentation | null {
	if (!plain(value) || !uint(value.id) || value.id === 0 || !finite(value.screenX) || !finite(value.screenY) || !finite(value.distance) || value.distance < 0 || Math.abs(value.screenX) > 32768 || Math.abs(value.screenY) > 32768) return null;
	const name = text(value.name); if (!name) return null;
	const maximum = uint(value.maxHp) && value.maxHp > 0 ? value.maxHp : null;
	const hp = uint(value.hp) && (maximum === null || value.hp <= maximum) ? value.hp : null;
	const cast = plain(value.cast) && finite(value.cast.endsAtMs) && finite(value.cast.durationMs) && value.cast.durationMs > 0 && value.cast.durationMs <= 120_000
		? { label: text(value.cast.label, 80), endsAtMs: value.cast.endsAtMs, durationMs: value.cast.durationMs } : null;
	return { id: value.id, name, screenX: value.screenX, screenY: value.screenY, distance: value.distance,
		onScreen: value.onScreen === true, occluded: value.occluded === true, hp, maxHp: maximum,
		level: uint(value.level, 9999) && value.level > 0 ? value.level : null,
		rank: ["normal", "elite", "boss"].includes(String(value.rank)) ? value.rank as CombatRank : null,
		element: text(value.element, 32), targetingMe: typeof value.targetingMe === "boolean" ? value.targetingMe : null,
		hostile: typeof value.hostile === "boolean" ? value.hostile : null,
		lastDamagedAtMs: finite(value.lastDamagedAtMs) ? value.lastDamagedAtMs : null,
		stateChips: Array.isArray(value.stateChips) ? value.stateChips.slice(0, 4).map(v => text(v, 32)).filter((v): v is string => !!v) : [], cast };
}

export function emptyCombatView(): CombatView {
	return { nowMs: 0, mobile: false, target: null, slots: Array.from({ length: 10 }, (_, slot) => ({ slot, actor: null, visible: false, expiresAtMs: 0 })) };
}

/** Ten fixed slots: never allocate DOM plates per snapshot actor or per frame. */
export function nextCombatView(previous: CombatView, raw: unknown): CombatView | null {
	if (!plain(raw) || !finite(raw.nowMs) || raw.nowMs < 0 || !Array.isArray(raw.actors) || raw.actors.length > 64 || !["desktop", "mobile"].includes(String(raw.formFactor))) return null;
	const actors: CombatActorPresentation[] = [], seen = new Set<number>();
	for (const row of raw.actors) { const parsed = actor(row); if (parsed && !seen.has(parsed.id)) { seen.add(parsed.id); actors.push(parsed); } }
	const mobile = raw.formFactor === "mobile", cap = mobile ? 6 : 10, now = raw.nowMs;
	const selected = uint(raw.selectedTargetId) ? raw.selectedTargetId : null;
	const priority = (row: CombatActorPresentation): number => row.id === selected ? 0 : row.targetingMe === true ? 1
		: row.lastDamagedAtMs !== null && now >= row.lastDamagedAtMs && now - row.lastDamagedAtMs <= 8000 ? 2
		: (row.rank === "elite" || row.rank === "boss") && row.distance <= 35 ? 3 : !mobile && row.hostile === true && row.distance <= 10 ? 4 : 99;
	const wanted = actors.filter(row => row.onScreen && priority(row) < 99).sort((a, b) => priority(a) - priority(b) || a.distance - b.distance || a.id - b.id).slice(0, cap);
	const byId = new Map(wanted.map(row => [row.id, row]));
	const slots = previous.slots.map((slot, index): CombatPlateSlot => {
		if (index >= cap) return { slot: index, actor: null, visible: false, expiresAtMs: 0 };
		const match = slot.actor && byId.get(slot.actor.id);
		if (match) { byId.delete(match.id); return { slot: index, actor: match, visible: true, expiresAtMs: 0 }; }
		if (!slot.actor || (!slot.visible && now >= slot.expiresAtMs)) return { slot: index, actor: null, visible: false, expiresAtMs: 0 };
		return { ...slot, visible: false, expiresAtMs: slot.visible ? now + 250 : slot.expiresAtMs };
	});
	for (const candidate of byId.values()) {
		const free = slots.findIndex(slot => slot.slot < cap && slot.actor === null);
		const evict = free >= 0 ? free : slots.findIndex(slot => slot.slot < cap && !slot.visible);
		if (evict >= 0) slots[evict] = { slot: evict, actor: candidate, visible: true, expiresAtMs: 0 };
	}
	return { nowMs: now, mobile, target: actors.find(row => row.id === selected) ?? null, slots };
}

export function healthRatio(row: Pick<CombatActorPresentation, "hp" | "maxHp">): number | null {
	return row.hp === null || row.maxHp === null || row.maxHp <= 0 ? null : Math.max(0, Math.min(1, row.hp / row.maxHp));
}
export function castRemaining(cast: CombatCast, nowMs: number): number { return Math.max(0, Math.min(cast.durationMs, cast.endsAtMs - nowMs)); }

export function emptyDeathView(): DeathView {
	return { revision: null, down: false, cause: null, penalty: null, costs: null, free_return: null, auto_revive_at_ms: null, confirmedRevision:null, confirmedDown:false, request: null, online: false, canSubmit: false };
}
export function nextDeathView(previous: DeathView, raw: unknown): DeathView | null {
	if (!plain(raw) || typeof raw.down !== "boolean" || (raw.revision !== null && !uint(raw.revision))) return null;
	if(raw.revision===null) {
		if(!raw.down)return previous.down?null:previous;
		if(previous.down)return previous;
		return {...previous,revision:null,down:true,cause:null,penalty:null,costs:null,free_return:null,auto_revive_at_ms:null,request:null};
	}
	if(previous.confirmedRevision!==null&&(raw.revision<previous.confirmedRevision||(raw.revision===previous.confirmedRevision&&!previous.confirmedDown&&raw.down)))return null;
	const revision = raw.revision as number | null;
	const penalty = plain(raw.penalty) && uint(raw.penalty.base_exp) && uint(raw.penalty.job_exp) && uint(raw.penalty.gold)
		? { base_exp: raw.penalty.base_exp, job_exp: raw.penalty.job_exp, gold: raw.penalty.gold } : null;
	const costs = plain(raw.costs) && uint(raw.costs.return_to_town) ? { return_to_town: raw.costs.return_to_town } : null;
	return { ...previous, revision, down: raw.down, confirmedRevision:revision,confirmedDown:raw.down,cause: raw.cause === "monster" || raw.cause === "none" ? raw.cause : null, penalty, costs,
		free_return: typeof raw.free_return === "boolean" ? raw.free_return : null,
		auto_revive_at_ms: finite(raw.auto_revive_at_ms) ? raw.auto_revive_at_ms : null,
		request: !raw.down || revision !== previous.revision ? null : previous.request };
}
export function canReturnToTown(view: DeathView): boolean {
	return view.down && view.online && view.canSubmit && view.revision !== null && view.free_return === true && view.costs?.return_to_town === 0
		&& view.request?.phase !== "submitting" && view.request?.phase !== "committed";
}
/** Runtime may call only for a validated current local-player snapshot with HP > 0. */
export function confirmAliveView(previous: DeathView): DeathView {
	return {...previous,down:false,revision:previous.confirmedRevision,confirmedDown:false,request:null,cause:null,penalty:null,costs:null,free_return:null,auto_revive_at_ms:null};
}
export function startTownRequest(view: DeathView, requestId: string): DeathView | null {
	if (!canReturnToTown(view) || !/^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$/.test(requestId)) return null;
	const reuse = view.request?.phase === "outcome-unknown" && view.request.deathRevision === view.revision ? view.request.opId : requestId;
	return { ...view, request: { opId: reuse, deathRevision: view.revision!, phase: "submitting", reason: null } };
}
export function applyTownResult(view: DeathView, result: ReturnToTownResult): DeathView {
	if (!view.request || result.opId !== view.request.opId || result.deathRevision !== view.revision || result.deathRevision !== view.request.deathRevision || !["committed", "rejected", "outcome-unknown"].includes(result.state)) return view;
	if (view.request.phase === "committed") return view;
	return { ...view, request: { ...view.request, phase: result.state, reason: text(result.reason, 160) } };
}

export function createResourceStates(): PanelResourceMap {
	return Object.fromEntries(RESOURCE_KEYS.map(key => [key, { status: "loading", hasData: false, message: null, requestId: null }])) as PanelResourceMap;
}
export function updateResource(previous: PanelResourceState, raw: unknown): PanelResourceState | null {
	if (!plain(raw) || !["loading", "loaded-empty", "loaded-data", "stale", "error"].includes(String(raw.status))) return null;
	if(raw.requestId!==null&&raw.requestId!==undefined&&!validRequestId(raw.requestId))return null;
	const requestId = raw.requestId === null || raw.requestId === undefined ? null : validRequestId(raw.requestId) ? raw.requestId : null;
	// Replies carrying another request id cannot complete a newer request.
	if (previous.requestId && (["loaded-empty","loaded-data"].includes(String(raw.status)) || (raw.status==="error"&&requestId!==null)) && requestId !== previous.requestId) return null;
	const hasData = raw.status === "loaded-empty" || raw.status === "loaded-data" ? true : typeof raw.hasData === "boolean" ? raw.hasData : previous.hasData;
	return { status: raw.status as PanelResourceStatus, hasData, message: text(raw.message, 300), requestId };
}
export function resourceKeysForPanel(panel: string | null): ResourceKey[] {
	const keys: Record<string, ResourceKey[]> = { bag: ["inventory"], store: ["shop", "wallet"], character: ["character"], skills: ["character"], party: ["party"], friends: ["friends"], group: ["group"], tower: ["tower"], collection: ["journal"], trade: ["community"], battlepass: ["community"], topup: ["community"] };
	return panel ? [...(keys[panel] ?? [])] : [];
}
export function nextTransactions(previous: UiTransaction[], raw: unknown): UiTransaction[] | null {
	if (!plain(raw) || !RESOURCE_KEYS.includes(raw.resource as ResourceKey) || !validRequestId(raw.requestId) || !["preview", "submitting", "committed", "rejected", "outcome-unknown"].includes(String(raw.phase))) return null;
	const existing = previous.find(row => row.requestId === raw.requestId);
	if (existing && (existing.resource !== raw.resource || ["committed", "rejected"].includes(existing.phase))) return previous;
	const next = { resource: raw.resource as ResourceKey, requestId: raw.requestId, phase: raw.phase as TransactionPhase, reason: text(raw.reason, 300) };
	const rows = previous.filter(row => row.requestId !== raw.requestId);
	if (rows.length >= 16) {
		const terminal = rows.findIndex(row => row.phase === "committed" || row.phase === "rejected" || row.phase === "preview");
		if (terminal < 0) return null;
		rows.splice(terminal, 1);
	}
	return [...rows, next];
}
export function normalizeReadability(value: unknown): CombatReadability {
	return plain(value) ? { combatTextScale: finite(value.combatTextScale) ? Math.min(2, Math.max(.8, Math.round(value.combatTextScale * 20) / 20)) : 1, lowEffects: value.lowEffects === true, hideOtherEffects: value.hideOtherEffects === true, screenShake:value.screenShake!==false } : { ...DEFAULT_COMBAT_READABILITY };
}
export function parseItemInstances(value:unknown, name:(def:string)=>string, slot?:(def:string)=>"weapon"|"armor"|null):InventoryInstanceEntry[]|null {
	if(value===undefined)return [];
	if(!Array.isArray(value)||value.length>64)return null;
	const rows:InventoryInstanceEntry[]=[], seen=new Set<string>(), equipped=new Set<string>();
	for(const raw of value) {
		if(!plain(raw)||typeof raw.instance_id!=="string"||! /^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$/.test(raw.instance_id)||typeof raw.def!=="string"||!/^[a-zA-Z0-9_-]{1,64}$/.test(raw.def)||!["bag","weapon","armor"].includes(String(raw.location))||!uint(raw.refine,255)||seen.has(raw.instance_id.toLowerCase()))return null;
		if(raw.location!=="bag"&&equipped.has(String(raw.location)))return null;
		if(raw.location!=="bag")equipped.add(String(raw.location));
		let label:string|null, equipment:"weapon"|"armor"|null=null;
		try {label=text(name(raw.def),200); const candidate=slot?.(raw.def); if(candidate==="weapon"||candidate==="armor")equipment=candidate;} catch {return null;}
		seen.add(raw.instance_id.toLowerCase());rows.push({instanceId:raw.instance_id,id:raw.def,label:label??raw.def,location:raw.location as InventoryInstanceEntry["location"],refine:raw.refine,equipSlot:equipment});
	}
	return rows;
}
