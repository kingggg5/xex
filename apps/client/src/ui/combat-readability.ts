import { DEFAULT_COMBAT_READABILITY, normalizeReadability, type CombatReadability } from "./combat-model";
export const COMBAT_READABILITY_KEY = "xexoria_combat_readability_v1";
export function loadCombatReadability(storage: Pick<Storage, "getItem"> | null, legacyShake=true): CombatReadability {
	try { const raw = storage?.getItem(COMBAT_READABILITY_KEY); if (!raw || raw.length > 2048) return { ...DEFAULT_COMBAT_READABILITY,screenShake:legacyShake }; const parsed = JSON.parse(raw); return parsed?.version === 1 ? normalizeReadability({...parsed.value,screenShake:typeof parsed.value?.screenShake==="boolean"?parsed.value.screenShake:legacyShake}) : { ...DEFAULT_COMBAT_READABILITY,screenShake:legacyShake }; }
	catch { return { ...DEFAULT_COMBAT_READABILITY }; }
}
export function saveCombatReadability(storage: Pick<Storage, "setItem"> | null, value: CombatReadability): boolean {
	try { if (!storage) return false; storage.setItem(COMBAT_READABILITY_KEY, JSON.stringify({ version: 1, value: normalizeReadability(value) })); return true; } catch { return false; }
}
