import type { ShopCatalog, ShopEntry, UiLanguage } from "./types";
import { readUiResource } from "./resource";

const MAX_CATALOG_ROWS = 128;
const MAX_ODDS_ROWS = 64;
const MAX_BUNDLE_BYTES = 2 * 1024 * 1024;
let bundlePromise: Promise<unknown> | null = null;

function record(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function amount(value: unknown, fallback = 0): number {
	return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.min(Number.MAX_SAFE_INTEGER, value) : fallback;
}

function id(value: unknown): string | null {
	return typeof value === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(value) ? value : null;
}

function pretty(value: string): string {
	const tail = value.includes("_") ? value.slice(value.indexOf("_") + 1) : value;
	return tail.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

/** Catalog labels/prices are display data; purchases still send only IDs to the server. */
export function parseShopCatalog(value: unknown, language: UiLanguage): ShopCatalog | null {
	if (!record(value) || !record(value.economy)) return null;
	const economy = value.economy;
	const items = record(value.items) ? value.items : {};
	const translations = record(value.dialogue) ? value.dialogue : {};
	const strings = record(translations[language]) ? translations[language] : record(translations.en) ? translations.en : {};
	const skins = record(economy.skins) ? economy.skins : {};
	const pets = record(economy.pets) ? economy.pets : {};
	const boxes = record(economy.boxes) ? economy.boxes : {};
	const label = (identifier: string): string => {
		const definition = items[identifier];
		const key = record(definition) && typeof definition.name_key === "string" ? definition.name_key : "";
		return typeof strings[key] === "string" ? strings[key].slice(0, 200) : pretty(identifier);
	};
	const color = (value: unknown): string | null => typeof value === "string" && /^#[0-9a-fA-F]{3,8}$/.test(value) ? value : null;
	const entries: ShopEntry[] = [];
	const boxPrices = new Map<string, { price: number; currency: "gold" | "coin" }>();
	const rows = Array.isArray(economy.store) ? economy.store.slice(0, MAX_CATALOG_ROWS) : [];
	for (const row of rows) {
		if (!record(row)) continue;
		const currency = row.currency === "coin" ? "coin" : row.currency === "gold" || row.currency === undefined ? "gold" : null;
		if (!currency) continue;
		const price = amount(row.price);
		const item = id(row.item);
		const cosmetic = id(row.cosmetic);
		if (item) {
			if (record(boxes[item])) boxPrices.set(item, { price, currency });
			else entries.push({ id: item, label: label(item), slot: "item", price, currency, color: null });
		} else if (cosmetic && record(skins[cosmetic])) {
			entries.push({ id: cosmetic, label: pretty(cosmetic), slot: "skin", price, currency, color: color(skins[cosmetic].tunic) });
		} else if (cosmetic && record(pets[cosmetic])) {
			entries.push({ id: cosmetic, label: pretty(cosmetic), slot: "pet", price, currency, color: color(pets[cosmetic].tint) });
		}
	}
	const catalog: ShopCatalog = { entries, boxes: [] };
	for (const [identifier, definition] of Object.entries(boxes).slice(0, 16)) {
		if (!id(identifier) || !record(definition) || !Array.isArray(definition.table)) continue;
		const odds: ShopCatalog["boxes"][number]["odds"] = [];
		for (const outcome of definition.table.slice(0, MAX_ODDS_ROWS)) {
			if (!record(outcome)) continue;
			const weight = amount(outcome.weight);
			if (weight <= 0) continue;
			const minimum = Math.max(1, Math.floor(amount(outcome.min, 1)));
			const maximum = Math.max(minimum, Math.floor(amount(outcome.max, minimum)));
			if (typeof outcome.gold === "number") odds.push({ id: "gold", label: language === "th" ? "ทอง" : "Gold", amount: amount(outcome.gold), weight });
			else if (typeof outcome.coin === "number") odds.push({ id: "coin", label: language === "th" ? "เหรียญ" : "Coin", amount: amount(outcome.coin), weight });
			else if (id(outcome.item)) odds.push({ id: outcome.item as string, label: label(outcome.item as string), amount: maximum, weight });
			else if (id(outcome.cosmetic)) odds.push({ id: outcome.cosmetic as string, label: pretty(outcome.cosmetic as string), amount: 1, weight });
		}
		catalog.boxes.push({ id: identifier, label: label(identifier), ...(boxPrices.get(identifier) ?? { price: 0, currency: "gold" as const }), odds });
	}
	catalog.entries = [...new Map(catalog.entries.map((entry) => [entry.id, entry])).values()];
	return catalog;
}

export async function loadShopCatalog(language: UiLanguage): Promise<ShopCatalog | null> {
	if (!bundlePromise) {
		bundlePromise = readUiResource("/content/bundle.json", MAX_BUNDLE_BYTES).then((bytes) => JSON.parse(new TextDecoder().decode(bytes)) as unknown).catch(() => null);
	}
	return parseShopCatalog(await bundlePromise, language);
}
