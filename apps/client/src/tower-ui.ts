/**
 * Tower UI: the 100-floor climb panel (current/best floor, enter/leave) plus
 * the defensive GET /tower parser.
 *
 * Contract (server, built in parallel):
 * - GET /tower → {"in_tower":false,"floor":0,"best_floor":12}
 * - POST /tower/enter → 204 (the server marks the session; the client then
 *   closes the websocket and reconnects — the join lands in the player's
 *   tower instance) or 503 "tower_full". 401 without a session.
 * - POST /tower/leave → 204 (the client then reconnects to the normal field).
 * - In-tower cold notices: {"t":"notice","key":"tower_floor","params":
 *   {"floor":7}} on each floor spawn and {"key":"tower_complete"} at floor
 *   100, after which the server clears the assignment.
 *
 * Rendering only — entering/leaving flows through the `actions` callbacks
 * supplied by GameHud (the integrator POSTs and reconnects).
 */

export interface TowerState {
	inTower: boolean;
	floor: number;
	bestFloor: number;
}

export interface TowerActions {
	enter(): void;
	leave(): void;
}

/** Generous defensive ceiling; the tower itself is 100 floors. */
const FLOOR_LIMIT = 1000;

// D-06 convention (login.ts / settings.ts): Thai copy when the browser language is Thai.
const THAI = typeof navigator === "undefined" ? false : navigator.language.toLowerCase().startsWith("th");

interface CopyTable {
	kicker: string;
	currentLabel: string;
	currentOutside: string;
	bestLabel: string;
	floorValue(floor: number): string;
	enter: string;
	enterHint: string;
	insideHint: string;
	leave: string;
	note: string;
}

const EN: CopyTable = {
	kicker: "TOWER · 100 FLOORS",
	currentLabel: "Current floor",
	currentOutside: "Outside",
	bestLabel: "Best floor",
	floorValue: (floor) => `Floor ${floor}`,
	enter: "Enter the Tower",
	enterHint: "Enter at floor 1",
	insideHint: "You are inside the tower — leaving returns you to the frontier.",
	leave: "Leave the Tower",
	note: "Floor rewards feed your wallet automatically. Enemy attacks inside the tower arrive with the next combat milestone.",
};

const TH: CopyTable = {
	kicker: "หอคอย · 100 ชั้น",
	currentLabel: "ชั้นปัจจุบัน",
	currentOutside: "อยู่นอกหอคอย",
	bestLabel: "ชั้นสูงสุด",
	floorValue: (floor) => `ชั้น ${floor}`,
	enter: "เข้าสู่หอคอย",
	enterHint: "เริ่มปีนที่ชั้น 1",
	insideHint: "คุณอยู่ในหอคอย — การออกจะพาคุณกลับสู่ฟรอนเทียร์",
	leave: "ออกจากหอคอย",
	note: "รางวัลตามชั้นจะเข้ากระเป๋าเงินโดยอัตโนมัติ ส่วนการโจมตีของศัตรูในหอคอยจะมาพร้อมไมล์สโตนระบบต่อสู้ถัดไป",
};

const COPY = THAI ? TH : EN;

/** GET /tower, parsed defensively; null when the server is unreachable or booting. */
export async function fetchTowerState(): Promise<TowerState | null> {
	const response = await fetch("/tower", { cache: "no-store", credentials: "same-origin" }).catch(() => null);
	if (!response?.ok) return null;
	const body: unknown = await response.json().catch(() => null);
	return parseTowerState(body);
}

/** Validates a GET /tower body (snake_case wire format); null when malformed. */
export function parseTowerState(body: unknown): TowerState | null {
	if (typeof body !== "object" || body === null) return null;
	const source = body as { in_tower?: unknown; floor?: unknown; best_floor?: unknown };
	if (typeof source.in_tower !== "boolean") return null;
	const floor = source.floor;
	const bestFloor = source.best_floor;
	if (typeof floor !== "number" || typeof bestFloor !== "number") return null;
	if (!Number.isSafeInteger(floor) || !Number.isSafeInteger(bestFloor)) return null;
	return {
		inTower: source.in_tower,
		floor: source.in_tower ? clampFloor(floor) : 0,
		bestFloor: clampFloor(bestFloor),
	};
}

/**
 * Coerces an already-decoded TowerState (e.g. from setTowerState) into a
 * safe one: bad numbers clamp/fall back, and floor is 0 while outside.
 */
export function sanitizeTowerState(state: TowerState): TowerState {
	return {
		inTower: state.inTower === true,
		floor: state.inTower === true && Number.isSafeInteger(state.floor) ? clampFloor(state.floor) : 0,
		bestFloor: Number.isSafeInteger(state.bestFloor) ? clampFloor(state.bestFloor) : 0,
	};
}

/**
 * Renders the tower panel: current/best floor, a themed Enter button, a Leave
 * button while inside, and an honest note about what is (not) implemented yet.
 */
export function renderTowerPanel(container: HTMLElement, state: TowerState, actions: TowerActions): void {
	const view = sanitizeTowerState(state);
	container.replaceChildren();
	const panel = document.createElement("div");
	panel.className = "tower-panel";

	const kicker = document.createElement("p");
	kicker.className = "panel-kicker";
	kicker.textContent = COPY.kicker;
	panel.append(kicker);

	const stats = document.createElement("div");
	stats.className = "tower-stats";
	stats.append(
		towerStat(COPY.currentLabel, view.inTower ? COPY.floorValue(view.floor) : COPY.currentOutside, view.inTower),
		towerStat(COPY.bestLabel, COPY.floorValue(view.bestFloor), false),
	);
	panel.append(stats);

	const enter = document.createElement("button");
	enter.type = "button";
	enter.className = "tower-enter";
	enter.textContent = COPY.enter;
	enter.addEventListener("click", () => actions.enter());
	panel.append(enter);

	const hint = document.createElement("small");
	hint.className = "tower-hint";
	hint.textContent = view.inTower ? COPY.insideHint : COPY.enterHint;
	panel.append(hint);

	if (view.inTower) {
		const leave = document.createElement("button");
		leave.type = "button";
		leave.className = "tower-leave";
		leave.textContent = COPY.leave;
		leave.addEventListener("click", () => actions.leave());
		panel.append(leave);
	}

	const note = document.createElement("p");
	note.className = "econ-note";
	note.textContent = COPY.note;
	panel.append(note);

	container.append(panel);
}

function towerStat(label: string, value: string, highlight: boolean): HTMLElement {
	const stat = document.createElement("div");
	stat.className = `tower-stat${highlight ? " is-inside" : ""}`;
	const small = document.createElement("small");
	small.textContent = label;
	const strong = document.createElement("b");
	strong.textContent = value;
	stat.append(small, strong);
	return stat;
}

function clampFloor(value: number): number {
	return Math.max(0, Math.min(FLOOR_LIMIT, value));
}
