/**
 * D-14 session-economy UI: wallet badges, store rows, the Meadow Box card
 * with its full published odds table, and the owned-cosmetics wardrobe strip.
 *
 * Rendering only — every purchase, box opening and equip flows through the
 * `actions` callbacks supplied by GameHud (the integrator wires them to the
 * server cold messages store_buy / box_open / cosmetics_equip).
 *
 * The store reads the `economy` table from /content/bundle.json (fetched once
 * and cached at module level). The table is parsed defensively: missing or
 * malformed entries are dropped, so an older bundle degrades to a notice
 * instead of throwing.
 */

export interface EconomyWalletState {
	gold: number;
	coin: number;
	ownedCosmetics: string[];
	skin: string | null;
	pet: string | null;
	bagCounts: Record<string, number>;
}

export type CosmeticSlot = "skin" | "pet";

export interface EconomyActions {
	buy(itemOrCosmeticId: string): void;
	openBox(boxId: string): void;
	equip(slot: CosmeticSlot, id: string): void;
}

export interface EconomyEntry {
	id: string;
	nameKey: string | null;
	price: number;
	currency: string;
	color: string | null;
}

export interface EconomyOddsRow {
	id: string;
	nameKey: string | null;
	weight: number;
	amount: number;
}

export interface EconomyBox {
	id: string;
	nameKey: string | null;
	price: number;
	currency: string;
	odds: EconomyOddsRow[];
}

export interface EconomyView {
	economy: { items: EconomyEntry[]; skins: EconomyEntry[]; pets: EconomyEntry[]; boxes: EconomyBox[] };
	translate(key: string): string;
	itemName(id: string): string | null;
}

interface CopyTable {
	loading: string;
	unavailable: string;
	storeKicker: string;
	storeEmpty: string;
	buy: string;
	equip: string;
	equipped: string;
	owned: string;
	needMore(cost: number, have: number, glyph: string): string;
	boxKicker: string;
	boxEmpty: string;
	inBag(count: number): string;
	open: string;
	noneInBag: string;
	oddsCaption: string;
	oddsReward: string;
	oddsAmount: string;
	oddsChance: string;
	oddsMissing: string;
	oddsNote: string;
	wardrobeKicker: string;
	wardrobeEmpty: string;
}

// D-06 convention (main.ts): Thai copy when the browser language is Thai.
const THAI = typeof navigator === "undefined" ? false : navigator.language.toLowerCase().startsWith("th");

const EN: CopyTable = {
	loading: "Loading store…",
	unavailable: "Store content could not be loaded.",
	storeKicker: "STORE",
	storeEmpty: "The store is restocking — nothing is on sale right now.",
	buy: "Buy",
	equip: "Equip",
	equipped: "Equipped",
	owned: "Owned",
	needMore: (cost, have, glyph) => `Need ${cost} ${glyph} · you have ${have} ${glyph}`,
	boxKicker: "MEADOW BOX",
	boxEmpty: "No box is available right now.",
	inBag: (count) => `In bag: ${count}`,
	open: "Open",
	noneInBag: "No box in your bag — buy one first.",
	oddsCaption: "CONTENTS · EXACT ODDS",
	oddsReward: "Reward",
	oddsAmount: "Amount",
	oddsChance: "Chance",
	oddsMissing: "The odds table for this box is unavailable.",
	oddsNote: "Odds are exact and published before opening. Boxes are bought with in-game gold only — no real money is involved.",
	wardrobeKicker: "OWNED COSMETICS",
	wardrobeEmpty: "Cosmetics you own will appear here.",
};

const TH: CopyTable = {
	loading: "กำลังโหลดร้านค้า…",
	unavailable: "ไม่สามารถโหลดข้อมูลร้านค้าได้",
	storeKicker: "ร้านค้า",
	storeEmpty: "ร้านค้ากำลังเติมสินค้า ขณะนี้ยังไม่มีรายการขาย",
	buy: "ซื้อ",
	equip: "สวมใส่",
	equipped: "สวมอยู่",
	owned: "เป็นเจ้าของแล้ว",
	needMore: (cost, have, glyph) => `ต้องการ ${cost} ${glyph} · มีอยู่ ${have} ${glyph}`,
	boxKicker: "กล่องทุ่งหญ้า",
	boxEmpty: "ขณะนี้ยังไม่มีกล่องให้เปิด",
	inBag: (count) => `ในกระเป๋า: ${count}`,
	open: "เปิด",
	noneInBag: "ไม่มีกล่องในกระเป๋า โปรดซื้อก่อน",
	oddsCaption: "เนื้อหา · อัตราได้รางวัลตรงตามจริง",
	oddsReward: "รางวัล",
	oddsAmount: "จำนวน",
	oddsChance: "โอกาส",
	oddsMissing: "ยังไม่มีตารางอัตรารางวัลของกล่องนี้",
	oddsNote: "อัตราได้รางวัลระบุตรงตามจริงก่อนเปิดกล่อง กล่องซื้อด้วยทองในเกมเท่านั้น ไม่มีการใช้เงินจริง",
	wardrobeKicker: "คอสมิกที่เป็นเจ้าของ",
	wardrobeEmpty: "คอสมิกที่คุณเป็นเจ้าของจะแสดงที่นี่",
};

const COPY: CopyTable = THAI ? TH : EN;

const MEADOW_BOX_ID = "meadow_box";

let bundleView: EconomyView | null = null;
let bundlePromise: Promise<EconomyView | null> | null = null;

/**
 * Renders the store panel into `container`. Safe to call repeatedly: each call
 * replaces the panel content, and the bundle fetch happens at most once.
 */
export function renderStorePanel(container: HTMLElement, state: EconomyWalletState, actions: EconomyActions): void {
	if (bundleView) {
		renderStoreInto(container, state, actions, bundleView);
		return;
	}
	const skeleton = el("p", "econ-note", COPY.loading);
	container.replaceChildren(skeleton);
	void ensureEconomyView().then((view) => {
		// Skip if the panel was closed or re-rendered (e.g. newer wallet state) meanwhile.
		if (!container.isConnected || container.firstElementChild !== skeleton) return;
		if (!view) {
			container.replaceChildren(el("p", "econ-note", COPY.unavailable));
			return;
		}
		renderStoreInto(container, state, actions, view);
	});
}

function renderStoreInto(container: HTMLElement, state: EconomyWalletState, actions: EconomyActions, view: EconomyView): void {
	container.replaceChildren();
	container.append(walletBar(state));

	container.append(el("div", "panel-kicker", COPY.storeKicker));
	const list = el("div", "store-list");
	const rows: Array<{ entry: EconomyEntry; slot: CosmeticSlot | "item" }> = [
		...view.economy.items.map((entry) => ({ entry, slot: "item" as const })),
		...view.economy.skins.map((entry) => ({ entry, slot: "skin" as const })),
		...view.economy.pets.map((entry) => ({ entry, slot: "pet" as const })),
	];
	if (rows.length === 0) list.append(el("p", "econ-note", COPY.storeEmpty));
	for (const row of rows) list.append(storeRow(row.entry, row.slot, state, actions, view));
	container.append(list);

	container.append(el("div", "panel-kicker", COPY.boxKicker));
	const box = view.economy.boxes.find((candidate) => candidate.id === MEADOW_BOX_ID) ?? view.economy.boxes[0] ?? null;
	if (box === null) container.append(el("p", "econ-note", COPY.boxEmpty));
	else container.append(boxCard(box, state, actions, view));

	container.append(el("div", "panel-kicker", COPY.wardrobeKicker));
	if (state.ownedCosmetics.length === 0) {
		container.append(el("p", "econ-note", COPY.wardrobeEmpty));
	} else {
		const strip = el("div", "cosmetic-strip");
		for (const id of state.ownedCosmetics) strip.append(cosmeticChip(id, state, actions, view));
		container.append(strip);
	}
}

function walletBar(state: EconomyWalletState): HTMLElement {
	const bar = el("div", "wallet-bar");
	bar.append(walletBadge("gold", state.gold), walletBadge("coin", state.coin));
	return bar;
}

function walletBadge(currency: "gold" | "coin", amount: number): HTMLElement {
	const badge = el("span", `wallet-badge wallet-${currency}`);
	badge.append(
		el("span", "wallet-icon", currencyGlyph(currency)),
		el("b", "", String(Math.max(0, Math.floor(amount)))),
	);
	return badge;
}

function storeRow(entry: EconomyEntry, slot: CosmeticSlot | "item", state: EconomyWalletState, actions: EconomyActions, view: EconomyView): HTMLElement {
	const wrapper = el("div", "store-entry");
	const row = el("div", "store-row");
	const owned = slot !== "item" && state.ownedCosmetics.includes(entry.id);
	const targetSlot: CosmeticSlot = slot === "pet" ? "pet" : "skin";
	const equipped = state.skin === entry.id || state.pet === entry.id;
	if (slot === "skin") row.append(swatch(entry.color));
	const label = el("div", "store-label");
	label.append(el("b", "", displayName(entry, view)));
	if (owned) label.append(el("small", "", COPY.owned));
	row.append(label);
	row.append(el("span", "store-price", `${entry.price} ${currencyGlyph(entry.currency)}`));
	const action = document.createElement("button");
	action.type = "button";
	action.className = "store-action";
	if (owned) {
		if (equipped) {
			action.textContent = COPY.equipped;
			action.disabled = true;
		} else {
			action.textContent = COPY.equip;
			action.addEventListener("click", () => actions.equip(targetSlot, entry.id));
		}
	} else {
		action.textContent = COPY.buy;
		const balance = entry.currency === "coin" ? state.coin : state.gold;
		if (entry.price > balance) {
			action.disabled = true;
			const reason = COPY.needMore(entry.price, balance, currencyGlyph(entry.currency));
			action.title = reason;
			action.setAttribute("aria-label", reason);
			wrapper.append(row, el("small", "store-hint", reason));
			return wrapper;
		}
		action.addEventListener("click", () => actions.buy(entry.id));
	}
	row.append(action);
	wrapper.append(row);
	return wrapper;
}

function boxCard(box: EconomyBox, state: EconomyWalletState, actions: EconomyActions, view: EconomyView): HTMLElement {
	const card = el("div", "box-card");
	const inBag = Math.max(0, Math.floor(state.bagCounts[box.id] ?? 0));

	const head = el("div", "box-head");
	const nameWrap = el("div", "store-label");
	nameWrap.append(el("b", "", displayName(box, view)), el("small", "box-bag", COPY.inBag(inBag)));
	head.append(nameWrap);
	if (box.price > 0) head.append(el("span", "store-price", `${box.price} ${currencyGlyph(box.currency)}`));
	card.append(head);

	const buttons = el("div", "box-actions");
	if (box.price > 0) {
		const buy = document.createElement("button");
		buy.type = "button";
		buy.className = "store-action";
		buy.textContent = COPY.buy;
		const balance = box.currency === "coin" ? state.coin : state.gold;
		if (box.price > balance) {
			buy.disabled = true;
			const reason = COPY.needMore(box.price, balance, currencyGlyph(box.currency));
			buy.title = reason;
			buy.setAttribute("aria-label", reason);
			buttons.append(buy, el("small", "store-hint", reason));
		} else {
			buy.addEventListener("click", () => actions.buy(box.id));
			buttons.append(buy);
		}
	}
	const open = document.createElement("button");
	open.type = "button";
	open.className = "store-action";
	open.textContent = inBag > 0 ? `${COPY.open} (${inBag})` : COPY.open;
	if (inBag <= 0) {
		open.disabled = true;
		open.title = COPY.noneInBag;
		open.setAttribute("aria-label", COPY.noneInBag);
	} else {
		open.addEventListener("click", () => actions.openBox(box.id));
	}
	buttons.append(open);
	card.append(buttons);

	if (box.odds.length === 0) card.append(el("p", "econ-note", COPY.oddsMissing));
	else card.append(oddsTable(box, view));
	card.append(el("p", "odds-note", COPY.oddsNote));
	return card;
}

function oddsTable(box: EconomyBox, view: EconomyView): HTMLElement {
	const table = document.createElement("table");
	table.className = "odds-table";
	const caption = document.createElement("caption");
	caption.textContent = COPY.oddsCaption;
	table.append(caption);
	const thead = document.createElement("thead");
	const headRow = document.createElement("tr");
	for (const heading of [COPY.oddsReward, COPY.oddsAmount, COPY.oddsChance]) headRow.append(el("th", "", heading));
	thead.append(headRow);
	table.append(thead);
	const tbody = document.createElement("tbody");
	const total = box.odds.reduce((sum, row) => sum + row.weight, 0);
	for (const row of box.odds) {
		const tr = document.createElement("tr");
		tr.append(el("td", "", displayName(row, view)));
		tr.append(el("td", "", `×${row.amount}`));
		const chance = document.createElement("td");
		chance.className = "num";
		chance.append(el("span", "odds-pct", formatPercent(total > 0 ? (row.weight / total) * 100 : 0)));
		const bar = el("span", "odds-bar");
		const fill = document.createElement("i");
		fill.style.setProperty("--w", total > 0 ? String(row.weight / total) : "0");
		bar.append(fill);
		chance.append(bar);
		tr.append(chance);
		tbody.append(tr);
	}
	table.append(tbody);
	return table;
}

function cosmeticChip(id: string, state: EconomyWalletState, actions: EconomyActions, view: EconomyView): HTMLElement {
	const chip = el("div", "cosmetic-chip");
	let slot: CosmeticSlot = "skin";
	if (view.economy.pets.some((entry) => entry.id === id)) slot = "pet";
	else if (!view.economy.skins.some((entry) => entry.id === id) && id.startsWith("pet")) slot = "pet";
	const def = findCosmetic(id, view);
	chip.append(swatch(def?.color ?? null));
	chip.append(el("b", "", def !== null ? displayName(def, view) : id.replaceAll("_", " ")));
	const action = document.createElement("button");
	action.type = "button";
	action.className = "store-action";
	if (state.skin === id || state.pet === id) {
		action.textContent = COPY.equipped;
		action.disabled = true;
	} else {
		action.textContent = COPY.equip;
		action.addEventListener("click", () => actions.equip(slot, id));
	}
	chip.append(action);
	return chip;
}

function displayName(def: { id: string; nameKey: string | null }, view: EconomyView): string {
	if (def.nameKey) {
		const translated = view.translate(def.nameKey);
		if (translated !== def.nameKey) return translated;
	}
	return view.itemName(def.id) ?? def.id.replaceAll("_", " ");
}

function findCosmetic(id: string, view: EconomyView): EconomyEntry | null {
	return view.economy.skins.find((entry) => entry.id === id) ?? view.economy.pets.find((entry) => entry.id === id) ?? null;
}

function swatch(color: string | null): HTMLElement {
	const node = el("span", "skin-swatch");
	if (color) node.style.setProperty("--swatch", color);
	return node;
}

export function currencyGlyph(currency: string): string {
	if (currency === "gold") return "◉";
	if (currency === "coin") return "✦";
	return "◆";
}

function formatPercent(value: number): string {
	const rounded = Math.round(value * 10) / 10;
	return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
}

function ensureEconomyView(): Promise<EconomyView | null> {
	if (!bundlePromise) {
		bundlePromise = fetch("/content/bundle.json")
			.then((response) => (response.ok ? response.json() : null))
			.then((json: unknown) => {
				bundleView = buildEconomyView(json);
				return bundleView;
			})
			.catch(() => {
				bundleView = null;
				return null;
			});
	}
	return bundlePromise;
}

function buildEconomyView(json: unknown): EconomyView | null {
	if (typeof json !== "object" || json === null) return null;
	const root = json as Record<string, unknown>;
	const dialogue = typeof root.dialogue === "object" && root.dialogue !== null ? (root.dialogue as Record<string, unknown>) : {};
	const strings = (dialogue[THAI ? "th" : "en"] ?? dialogue.en ?? {}) as Record<string, unknown>;
	const itemsTable = typeof root.items === "object" && root.items !== null ? (root.items as Record<string, unknown>) : {};
	const economyRaw = typeof root.economy === "object" && root.economy !== null ? (root.economy as Record<string, unknown>) : {};
	return {
		economy: economyFromAuthored(economyRaw, strings, itemsTable),
		translate(key: string): string {
			const value = strings[key];
			return typeof value === "string" && value ? value : key;
		},
		itemName(id: string): string | null {
			const def = itemsTable[id];
			if (typeof def !== "object" || def === null) return null;
			const nameKey = (def as Record<string, unknown>).name_key;
			if (typeof nameKey !== "string" || !nameKey) return null;
			const translated = strings[nameKey];
			return typeof translated === "string" && translated ? translated : null;
		},
	};
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Adapts the authored content economy shape (store rows keyed item/cosmetic,
 * skins/pets as id->color maps, boxes with weighted outcome tables) into the
 * view model. Cosmetic and wallet labels pass their display text through
 * nameKey, which translate() returns unchanged when no dialogue key matches.
 */
function economyFromAuthored(
	economyRaw: Record<string, unknown>,
	strings: Record<string, unknown>,
	itemsTable: Record<string, unknown>,
): EconomyView["economy"] {
	const rows = Array.isArray(economyRaw.store) ? economyRaw.store.filter(isRecord) : [];
	const skins = isRecord(economyRaw.skins) ? economyRaw.skins : {};
	const pets = isRecord(economyRaw.pets) ? economyRaw.pets : {};
	const boxes = isRecord(economyRaw.boxes) ? economyRaw.boxes : {};
	const hex = (value: unknown): string | null =>
		typeof value === "string" && /^#[0-9a-fA-F]{3,8}$/.test(value) ? value : null;

	const items: EconomyEntry[] = [];
	const skinEntries: EconomyEntry[] = [];
	const petEntries: EconomyEntry[] = [];
	const boxPrices = new Map<string, { price: number; currency: string }>();
	for (const row of rows) {
		const price = finiteNumber(row.price, 0);
		const currency = pickString(row, "currency") ?? "gold";
		const itemId = pickString(row, "item");
		const cosmeticId = pickString(row, "cosmetic");
		if (itemId) {
			if (isRecord(boxes[itemId])) {
				boxPrices.set(itemId, { price, currency });
				continue;
			}
			const def = isRecord(itemsTable[itemId]) ? itemsTable[itemId] : {};
			items.push({ id: itemId, nameKey: pickString(def, "name_key"), price, currency, color: null });
		} else if (cosmeticId && isRecord(skins[cosmeticId])) {
			skinEntries.push({
				id: cosmeticId,
				nameKey: prettyId(cosmeticId),
				price,
				currency,
				color: hex(skins[cosmeticId].tunic),
			});
		} else if (cosmeticId && isRecord(pets[cosmeticId])) {
			petEntries.push({
				id: cosmeticId,
				nameKey: prettyId(cosmeticId),
				price,
				currency,
				color: hex(pets[cosmeticId].tint),
			});
		}
	}

	const boxesOut: EconomyBox[] = [];
	for (const [id, raw] of Object.entries(boxes)) {
		if (!isRecord(raw) || !Array.isArray(raw.table)) continue;
		const table = raw.table.filter(isRecord);
		const odds: EconomyOddsRow[] = [];
		for (const roll of table) {
			const weight = finiteNumber(roll.weight, 0);
			if (weight <= 0) continue;
			const min = Math.max(1, Math.floor(finiteNumber(roll.min, 1)));
			const max = Math.max(min, Math.floor(finiteNumber(roll.max, min)));
			if (typeof roll.gold === "number") {
				odds.push({ id: "gold", nameKey: THAI ? "ทอง" : "Gold", weight, amount: roll.gold });
			} else if (typeof roll.coin === "number") {
				odds.push({ id: "coin", nameKey: THAI ? "เหรียญ" : "Coin", weight, amount: roll.coin });
			} else if (typeof roll.item === "string") {
				odds.push({ id: roll.item, nameKey: itemLabel(roll.item, itemsTable, strings), weight, amount: max });
			} else if (typeof roll.cosmetic === "string") {
				odds.push({ id: roll.cosmetic, nameKey: prettyId(roll.cosmetic), weight, amount: 1 });
			}
		}
		const price = boxPrices.get(id) ?? { price: 0, currency: "gold" };
		boxesOut.push({
			id,
			nameKey: itemLabel(id, itemsTable, strings),
			price: price.price,
			currency: price.currency,
			odds,
		});
	}
	return { items, skins: skinEntries, pets: petEntries, boxes: boxesOut };
}

/** "skin_crimson" -> "Crimson" — cosmetic ids carry no dialogue keys yet. */
function prettyId(id: string): string {
	const tail = id.includes("_") ? id.slice(id.indexOf("_") + 1) : id;
	return tail.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}

function itemLabel(id: string, itemsTable: Record<string, unknown>, strings: Record<string, unknown>): string {
	const def = itemsTable[id];
	if (isRecord(def)) {
		const key = pickString(def, "name_key");
		if (key && typeof strings[key] === "string" && strings[key]) return strings[key];
	}
	return prettyId(id);
}

function pickString(record: Record<string, unknown>, ...keys: string[]): string | null {
	for (const key of keys) {
		const value = record[key];
		if (typeof value === "string" && value) return value;
	}
	return null;
}

function finiteNumber(value: unknown, fallback: number): number {
	return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function el(tag: string, className: string, text?: string): HTMLElement {
	const node = document.createElement(tag);
	node.className = className;
	if (text !== undefined) node.textContent = text;
	return node;
}
