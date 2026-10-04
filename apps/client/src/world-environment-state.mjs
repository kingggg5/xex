const KEY = 'aetherfield_environment_v1';
const WEATHER = ['auto', 'clear', 'cloudy', 'rain', 'fog'];
const listeners = new Set();
let preference;

function normalized(value) {
	return Object.freeze({weather: WEATHER.includes(value?.weather) ? value.weather : 'auto', cycle: typeof value?.cycle === 'boolean' ? value.cycle : true});
}
export function getEnvironmentPreference() {
	if (!preference) {
		try { preference = normalized(JSON.parse(globalThis.localStorage?.getItem(KEY) ?? 'null')); }
		catch { preference = normalized(null); }
	}
	return preference;
}
export function setEnvironmentPreference(partial) {
	if (!partial || typeof partial !== 'object') throw new TypeError('Environment preference must be an object.');
	if ('weather' in partial && !WEATHER.includes(partial.weather)) throw new RangeError('Unknown weather mode.');
	if ('cycle' in partial && typeof partial.cycle !== 'boolean') throw new TypeError('Cycle must be boolean.');
	preference = normalized({...getEnvironmentPreference(), ...partial});
	try { globalThis.localStorage?.setItem(KEY, JSON.stringify(preference)); } catch { /* Session-only preference. */ }
	for (const listener of [...listeners]) listener(preference);
	return preference;
}
export function subscribeEnvironmentPreference(listener) {
	listeners.add(listener);
	return () => listeners.delete(listener);
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const smooth = (lo, hi, x) => { const t = clamp((x - lo) / (hi - lo), 0, 1); return t * t * (3 - 2 * t); };
/** Deterministic appearance sampled from room/server elapsed time, never UI objects. */
export function sampleEnvironment(elapsedMs, prefs = {weather:'auto',cycle:true}) {
	const elapsed = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
	const hours = prefs.cycle ? (13.5 + elapsed / 2_700_000 * 24) % 24 : 13.5;
	const altitude = Math.sin((hours - 6) / 24 * Math.PI * 2);
	const daylight = smooth(-0.14, 0.32, altitude);
	const dawn = 1 - smooth(0.10, 0.56, Math.abs(altitude));
	const slot = Math.floor(elapsed / 300_000);
	const hash = ((Math.imul(slot + 1, 1_103_515_245) + 12_345) >>> 0) / 4_294_967_296;
	const auto = hash < .58 ? 'clear' : hash < .80 ? 'cloudy' : hash < .95 ? 'rain' : 'fog';
	const weather = prefs.weather === 'auto' ? auto : prefs.weather;
	const rain = weather === 'rain' ? 1 : 0;
	const cloud = weather === 'clear' ? .15 : weather === 'fog' ? .65 : 1;
	return Object.freeze({hours, daylight, dawn, weather, rain, cloud,
		// Art pass v1 (2026-10-02): stronger warm key, lower cool fill -> readable form and real shadows;
		// lighter clear-day haze keeps aerial depth without washing the meadow out.
		sunIntensity: (.25 + 1.62 * daylight) * (1 - cloud * .28),
		hemisphereIntensity: .24 + .26 * daylight,
		fogDensity: weather === 'fog' ? .005 : weather === 'rain' ? .0028 : .00095,
		windStrength: rain ? 1.7 : weather === 'cloudy' ? 1.3 : 1,
		skyBrightness: .10 + .90 * daylight,
		direction: [Math.cos(hours / 24 * Math.PI * 2) * .55, -Math.max(.28, Math.abs(altitude)), .35],
		clockText: `${String(Math.floor(hours)).padStart(2,'0')}:${String(Math.floor(hours % 1 * 60)).padStart(2,'0')}`,
	});
}
