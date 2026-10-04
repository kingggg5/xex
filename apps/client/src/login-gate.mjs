// Pure login-gate logic (D-13), kept here so node --test can exercise it
// without a DOM; login.ts owns the markup and fetch calls.
//
// The gate has three outcomes:
// - "offline": the server is unreachable, so today's offline preview boots
//   exactly as before (no gate).
// - "enter": a live session already exists (returning player or OAuth
//   return), the game boots immediately.
// - "show": the player picks guest, Google or Discord on the login screen.

/**
 * @typedef {"guest" | "google" | "discord"} LoginProvider
 * @typedef {{ provider: LoginProvider, name: string }} LoginIdentity
 * @typedef {{ google: boolean, discord: boolean }} ProviderAvailability
 *
 * @param {{ serverAlive: boolean, signedIn: boolean, providers: ProviderAvailability | null, urlError: string | null }} input
 * @returns {"offline" | "enter" | "show"}
 */
export function decideLoginGate({ serverAlive, signedIn, providers, urlError }) {
	if (!serverAlive) return "offline";
	if (signedIn && !urlError) return "enter";
	if (!providers) return "offline";
	return "show";
}

/**
 * Bilingual copy for the fixed `?login=<reason>` values the server appends on
 * failure (kept here so the mapping is unit-testable).
 */
const ERROR_COPY = {
	denied: { en: "Sign-in was cancelled.", th: "ยกเลิกการเข้าสู่ระบบแล้ว" },
	state: { en: "Sign-in failed. Please try again.", th: "เข้าสู่ระบบไม่สำเร็จ กรุณาลองอีกครั้ง" },
	exchange: { en: "Sign-in failed. Please try again.", th: "เข้าสู่ระบบไม่สำเร็จ กรุณาลองอีกครั้ง" },
	provider: { en: "Sign-in failed. Please try again.", th: "เข้าสู่ระบบไม่สำเร็จ กรุณาลองอีกครั้ง" },
	unknown_provider: { en: "Sign-in failed. Please try again.", th: "เข้าสู่ระบบไม่สำเร็จ กรุณาลองอีกครั้ง" },
	provider_disabled: { en: "Sign-in isn't configured on this server yet.", th: "เซิร์ฟเวอร์นี้ยังไม่เปิดใช้การเข้าสู่ระบบ" },
	unavailable: { en: "Sign-in isn't configured on this server yet.", th: "เซิร์ฟเวอร์นี้ยังไม่เปิดใช้การเข้าสู่ระบบ" },
	rate_limited: { en: "Too many attempts — wait a moment.", th: "พยายามหลายครั้งเกินไป กรุณารอสักครู่" },
	capacity: { en: "The room is full right now — try again shortly.", th: "ห้องเต็มชั่วคราว กรุณาลองอีกครั้ง" },
	failed: { en: "Sign-in failed. Please try again.", th: "เข้าสู่ระบบไม่สำเร็จ กรุณาลองอีกครั้ง" },
};

/**
 * Player-facing line for a login failure reason; null when there is nothing
 * to show (unknown or missing reasons never break the gate).
 *
 * @param {string | null} reason
 * @param {"th" | "en"} lang
 * @returns {string | null}
 */
export function loginErrorText(reason, lang) {
	return ERROR_COPY[reason ?? ""]?.[lang] ?? null;
}

/**
 * Channel/room slice: validates a stored channel choice (localStorage
 * "aetherfield_channel") so the guest flow can pass it through to
 * POST /session/channel. An integer channel id (0-65535) is valid; null (or
 * anything malformed — including values written by other apps or older
 * builds) means "auto", so a bad stored value can never block the gate.
 *
 * @param {unknown} value
 * @returns {number | null}
 */
export function parseStoredChannel(value) {
	if (typeof value === "number") {
		return Number.isSafeInteger(value) && value >= 0 && value <= 65535 ? value : null;
	}
	if (typeof value === "string" && /^[0-9]{1,5}$/.test(value)) {
		const parsed = Number(value);
		return Number.isSafeInteger(parsed) ? parsed : null;
	}
	return null;
}

/**
 * Validates the /session/whoami body. Anything malformed is treated as a
 * guest identity so a bad payload can never break the boot path.
 *
 * @param {unknown} body
 * @returns {LoginIdentity}
 */
export function parseIdentity(body) {
	const fallback = { provider: "guest", name: "Traveler" };
	if (typeof body !== "object" || body === null) return fallback;
	const identity = /** @type {{ identity?: unknown }} */ (body).identity;
	if (typeof identity !== "object" || identity === null) return fallback;
	const record = /** @type {{ provider?: unknown, display_name?: unknown }} */ (identity);
	const provider = record.provider === "google" || record.provider === "discord" ? record.provider : "guest";
	if (typeof record.display_name !== "string" || record.display_name.length === 0 || record.display_name.length > 64) {
		return { provider, name: "Traveler" };
	}
	return { provider, name: record.display_name };
}
