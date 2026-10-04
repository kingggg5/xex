export const LIGHTNING_LIFETIME_MS = 480;
export const LIGHTNING_FLASH_MS = 120;
export const LIGHTNING_PATHS = 4;
export const LIGHTNING_POINTS_PER_PATH = 25;
const MAX_CLOCK_GAP_MS = 4_000;
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const smooth = x => { const t = clamp(x, 0, 1); return t * t * (3 - 2 * t); };
function hash(value) {
	let x = value >>> 0;
	x ^= x >>> 16; x = Math.imul(x, 0x7feb352d);
	x ^= x >>> 15; x = Math.imul(x, 0x846ca68b);
	return (x ^ (x >>> 16)) >>> 0;
}
const LOW = Object.freeze({paths: 2, minimumIntervalMs: 14_000, flashScale: .35});
const MOBILE = Object.freeze({paths: 3, minimumIntervalMs: 8_000, flashScale: .65});
const MEDIUM = Object.freeze({paths: 3, minimumIntervalMs: 8_000, flashScale: 1});
const HIGH = Object.freeze({paths: 4, minimumIntervalMs: 8_000, flashScale: 1});
export function lightningQuality(quality) {
	return quality?.preset === 'low' ? LOW : quality?.formFactor === 'mobile' ? MOBILE
		: quality?.preset === 'high' || quality?.preset === 'ultra' || quality?.preset === 'epic' ? HIGH : MEDIUM;
}

/** One smooth pulse, with no re-strikes or abrupt on/off oscillation. */
export function lightningEnvelope(ageMs) {
	if (!Number.isFinite(ageMs) || ageMs < 0 || ageMs >= LIGHTNING_LIFETIME_MS) return 0;
	return smooth(ageMs / 32) * Math.pow(1 - smooth((ageMs - 55) / 425), 2);
}

export function lightningFlashEnvelope(ageMs) {
	if (!Number.isFinite(ageMs) || ageMs < 0 || ageMs >= LIGHTNING_FLASH_MS) return 0;
	return smooth(ageMs / 20) * (1 - smooth((ageMs - 35) / 85));
}

/** Caller supplies monotonic world milliseconds, never the wrapping NatureClock phase. */
export function createLightningSchedule(seed = 0x584558) {
	if (!Number.isFinite(seed)) throw new TypeError('Lightning seed must be finite.');
	const initialSeed = seed >>> 0;
	let lastMs = NaN, nextMs = NaN, startedAt = -Infinity, sequence = 0, generation = 0, revision;
	let enabledBefore = false, scheduledQuality;
	const frame = {active: false, began: false, eligible: false, ageMs: 0, opacity: 0, flash: 0,
		seed: 0, startedAtMs: 0, nextAtMs: null, generation: 0};
	function clear() {
		nextMs = NaN; startedAt = -Infinity; enabledBefore = false; generation++;
		frame.active = frame.began = frame.eligible = false;
		frame.opacity = frame.flash = 0; frame.nextAtMs = null; frame.generation = generation;
	}
	function schedule(now, quality) {
		const random = hash(initialSeed ^ (++sequence * 0x9e3779b1));
		nextMs = now + quality.minimumIntervalMs + random / 4294967296 * (20_000 - quality.minimumIntervalMs);
	}
	return {
		/** Returned frame is borrowed until the next update; does not allocate per frame. */
		update(worldMs, appearance, options = {}) {
			frame.began = false;
			if (!Number.isFinite(worldMs) || worldMs < 0) {clear(); lastMs = NaN; return frame;}
			if ((Number.isFinite(lastMs) && (worldMs < lastMs || worldMs - lastMs > MAX_CLOCK_GAP_MS))
				|| options.clockRevision !== revision) clear();
			lastMs = worldMs; revision = options.clockRevision;
			const eligible = Number.isFinite(appearance?.rain) && Number.isFinite(appearance?.daylight)
				&& appearance.rain >= .55 && !options.reducedMotion && !options.reducedFlashes;
			if (!eligible) {if (enabledBefore) clear(); frame.eligible = false; return frame;}
			const quality = lightningQuality(options.quality);
			if (!enabledBefore || !Number.isFinite(nextMs) || quality !== scheduledQuality) schedule(worldMs, quality);
			enabledBefore = true; scheduledQuality = quality; frame.eligible = true;
			if (worldMs >= nextMs) {
				// Skip missed flashes after a stalled tab; never emit a catch-up burst.
				if (worldMs - nextMs <= 250) {
					startedAt = nextMs; frame.began = true;
					frame.seed = hash(initialSeed ^ sequence); frame.startedAtMs = startedAt;
				}
				schedule(nextMs, quality);
			}
			frame.ageMs = Math.max(0, worldMs - startedAt);
			frame.opacity = lightningEnvelope(frame.ageMs) * .78;
			frame.active = frame.ageMs < LIGHTNING_LIFETIME_MS;
			frame.flash = lightningFlashEnvelope(frame.ageMs) * quality.flashScale
				* (.055 + .035 * clamp(appearance.daylight, 0, 1));
			frame.nextAtMs = nextMs; frame.generation = generation;
			return frame;
		},
		reset() {clear(); lastMs = NaN; sequence = 0; revision = undefined;},
	};
}

/** Writes sky-only paths into a fixed caller allocation. Branches share exact attachment points. */
export function writeLightningPaths(seed, focus, viewDirection, output) {
	if (!(output instanceof Float32Array) || output.length !== LIGHTNING_PATHS * LIGHTNING_POINTS_PER_PATH * 3)
		throw new RangeError('Lightning path storage has the wrong capacity.');
	if (![focus?.x, focus?.y, focus?.z].every(Number.isFinite)) throw new TypeError('Lightning focus must be finite.');
	let randomSeed = seed >>> 0;
	const random = () => { randomSeed = hash(randomSeed + 0x9e3779b9); return randomSeed / 4294967296; };
	const heading = Number.isFinite(viewDirection?.x) && Number.isFinite(viewDirection?.z)
		&& Math.hypot(viewDirection.x, viewDirection.z) > .0001 ? Math.atan2(viewDirection.x, viewDirection.z) : 0;
	const angle = heading + (random() < .5 ? -1 : 1) * (.36 + random() * .16);
	const distance = 220 + random() * 60;
	const x = focus.x + Math.sin(angle) * distance, z = focus.z + Math.cos(angle) * distance;
	const top = focus.y + 58 + random() * 18, bottom = focus.y + 10 + random() * 4;
	const points = LIGHTNING_POINTS_PER_PATH;
	for (let p = 0; p < points; p++) {
		const t = p / (points - 1), at = p * 3;
		const jitter = Math.sin(t * Math.PI) * 3.8;
		output[at] = x + (random() - .5) * jitter + Math.sin(t * 7) * 2.1;
		output[at + 1] = top + (bottom - top) * t;
		output[at + 2] = z + (random() - .5) * jitter;
	}
	for (let branch = 1; branch < LIGHTNING_PATHS; branch++) {
		const joint = 5 + branch * 3, source = joint * 3;
		const startX = output[source], startY = output[source + 1], startZ = output[source + 2];
		const spread = (branch % 2 ? 1 : -1) * (9 + random() * 6);
		const fall = 6 + random() * 10;
		for (let p = 0; p < points; p++) {
			const t = p / (points - 1), at = (branch * points + p) * 3;
			const jitter = Math.sin(t * Math.PI) * 2.5;
			output[at] = startX + Math.cos(angle) * spread * t + (random() - .5) * jitter;
			output[at + 1] = startY - fall * t;
			output[at + 2] = startZ - Math.sin(angle) * spread * t + (random() - .5) * jitter;
		}
	}
	return {x: output[(points - 1) * 3], y: bottom, z: output[(points - 1) * 3 + 2]};
}
