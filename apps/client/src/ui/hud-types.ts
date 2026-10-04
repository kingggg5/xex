/** The HUD boundary is JSON-shaped data. Engine, DOM and callback objects stay outside it. */
export type HudLanguage = "en" | "th";
export type HudAction = "attack" | "arc_slash" | "dodge" | "guard";

export interface HudAbility {
	action: HudAction;
	label: string;
	key: string;
	art: "slash-art" | "arc-art" | "dodge-art" | "guard-art" | "mage-basic-art" | "mage-lance-art";
	description?: string;
	spCost?: number;
	rangeM?: number;
	/** A deadline in the client's performance.now() timebase, never a server timestamp. */
	readyAtMs: number;
	cooldownDurationMs: number;
	disabled: boolean;
}

export interface HudPlayer {
	name: string;
	levelText: string;
	baseLevel: number | null;
	jobLevel: number | null;
	hp: number;
	hpMaximum: number;
	/** Null means the server has supplied no SP stat; display an unavailable value. */
	sp: number | null;
	spMaximum: number | null;
	expText: string;
	expRatio: number;
	jobExpText: string;
	jobExpRatio: number;
	footerLevel: string;
	footerJob: string;
	footerExp: string;
}

export interface HudPartyMember {
	id: number;
	name: string;
	role: string;
	face: "rose" | "blue" | "sand";
	/** Optional preview-only stats; leave null when the online party payload has no stats. */
	hpRatio: number | null;
	level: number | null;
}

export interface HudQuest {
	id: string;
	title: string;
	description: string;
	progress: string;
	progressId: string | null;
}

export interface HudMinimap {
	/** False for Tower/other zones; omitted by legacy main-world previews. */
	mainMap?: boolean;
	playerX: number;
	playerZ: number;
	extent: number;
	showPreviewParty: boolean;
	points: Array<{ id: string; x: number; z: number }>;
	routes: Array<{ id: string; points: Array<[number, number]> }>;
}

export interface HudToast {
	id: number;
	message: string;
	expiresAtMs: number;
}

export interface HudSnapshot {
	language: HudLanguage;
	online: boolean;
	/** Modal, chat or renderer recovery blocks touch input. */
	inputBlocked: boolean;
	/** Increment when the controller neutralizes movement, even without a modal change. */
	inputResetVersion: number;
	player: HudPlayer;
	fps: number | null;
	pingMs: number | null;
	rendererLabel: string;
	locationName: string;
	connectionLabel: string;
	connectionMessage: string | null;
	sessionNote: string | null;
	/** Explicit server-confirmed trial or waiting state; independent of the session warning. */
	modeNote?: string | null;
	timeLabel: string;
	loadingMessage: string | null;
	party: { members: HudPartyMember[]; inviteText: string | null; preview: boolean };
	quests: { collapsed: boolean | null; loadingText: string | null; items: HudQuest[] };
	minimap: HudMinimap;
	abilities: HudAbility[];
	potion: { count: number; pending: boolean; unavailable: boolean; readyAtMs: number; cooldownDurationMs: number };
	contextLabel: string | null;
	toasts: HudToast[];
	fullscreenAvailable: boolean;
	fullscreenActive: boolean;
	rotateTitle: string;
	rotateCopy: string;
}

/** These are deliberately separate from all reactive snapshot values. */
export interface HudCommands {
	action(action: HudAction): void;
	potion(): void;
	context(): void;
	openModal(name: string): void;
	questsCollapsed(collapsed: boolean): void;
	movement(x: number, z: number): void;
	fullscreen(): void;
}

export function createHudSnapshot(language: HudLanguage): HudSnapshot {
	const th = language === "th";
	return {
		language, online: false, inputBlocked: false, inputResetVersion: 0,
		player: { name: "Eira", levelText: "Lv. 01", baseLevel: 1, jobLevel: 1, hp: 100, hpMaximum: 100, sp: 30, spMaximum: 30,
			expText: "0%", expRatio: 0, jobExpText: "Job 0%", jobExpRatio: 0,
			footerLevel: th ? "เลเวลพื้นฐาน 1" : "Base Lv. 01", footerJob: th ? "อาชีพ 1" : "Job Lv. 01", footerExp: "0%" },
		fps: null, pingMs: null, rendererLabel: "STARTING GRAPHICS", locationName: "Verdant Frontier",
		connectionLabel: "LOCAL ROOM · CONNECTING", connectionMessage: "Starting local Rust room…", sessionNote: null, timeLabel: "15:24", loadingMessage: null,
		party: { members: [
			{ id: -1, name: "Lyra", role: "", face: "rose", hpRatio: .92, level: 18 },
			{ id: -2, name: "Jory", role: "", face: "blue", hpRatio: .74, level: 17 },
			{ id: -3, name: "Sola", role: "", face: "sand", hpRatio: 1, level: 18 },
		], inviteText: null, preview: true },
		quests: { collapsed: null, loadingText: null, items: [
			{ id: "signal", title: "Signal on the Ridge", description: "Speak with the field captain", progress: "0 / 1", progressId: null },
			{ id: "slimes", title: "Mossbound Slimes", description: "Defeat meadow slimes", progress: "0 / 3", progressId: "quest-slimes" },
			{ id: "clover", title: "Forager’s Request", description: "Collect wild clover", progress: "0 / 5", progressId: "quest-clover" },
		] },
		minimap: { playerX: 0, playerZ: 0, extent: 28, showPreviewParty: true, points: [], routes: [] },
		abilities: [
			{ action: "attack", label: th ? "โจมตีปกติ" : "Basic attack", key: "F", art: "slash-art", readyAtMs: 0, cooldownDurationMs: 0, disabled: false },
			{ action: "arc_slash", label: th ? "ฟันโค้ง" : "Arc slash", key: "1", art: "arc-art", readyAtMs: 0, cooldownDurationMs: 0, disabled: false },
			{ action: "dodge", label: th ? "หลบหลีก" : "Dodge", key: "Space", art: "dodge-art", readyAtMs: 0, cooldownDurationMs: 0, disabled: false },
			{ action: "guard", label: th ? "ตั้งรับ" : "Guard Stance", key: "G", art: "guard-art", readyAtMs: 0, cooldownDurationMs: 0, disabled: false },
		],
		potion: { count: 3, pending: false, unavailable: false, readyAtMs: 0, cooldownDurationMs: 0 }, contextLabel: null, toasts: [],
		fullscreenAvailable: false, fullscreenActive: false,
		rotateTitle: th ? "หมุนอุปกรณ์เป็นแนวนอน" : "Turn your device sideways",
		rotateCopy: th ? "Xexoria ออกแบบสำหรับการเล่นในแนวนอน" : "Xexoria is designed for landscape play.",
	};
}
