export const NIGHT_MOTE_CAPACITY = 72;
export const NIGHT_MOTE_MAX_CLUSTERS = 24;
const budgets = Object.freeze({low: 12, medium: 24, high: 48, ultra: 72});
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const smooth = (low, high, value) => {
	const t = clamp((value - low) / (high - low), 0, 1);
	return t * t * (3 - 2 * t);
};

/** Uses the existing weather sample. Unknown/non-finite input fails dark. */
export function nightMoteOpacity(appearance) {
	if (!Number.isFinite(appearance?.daylight) || !Number.isFinite(appearance?.rain)) return 0;
	return (1 - smooth(.03, .28, appearance.daylight)) * (1 - smooth(.15, .8, appearance.rain));
}

export function nightMoteBudget(quality) {
	const preset = budgets[quality?.preset] ?? budgets.medium;
	return quality?.formFactor === 'mobile' ? Math.min(24, preset) : preset;
}

/** Validated, fixed author-provided habitats; no random scatter across roads or interiors. */
export function createNightMoteSeeds(clusters) {
	if (!Array.isArray(clusters) || clusters.length > NIGHT_MOTE_MAX_CLUSTERS) {
		throw new RangeError(`Night motes require at most ${NIGHT_MOTE_MAX_CLUSTERS} habitat clusters.`);
	}
	const habitats = clusters.map(cluster => {
		if (![cluster?.x, cluster?.y, cluster?.z, cluster?.radius].every(Number.isFinite)
			|| cluster.radius < .5 || cluster.radius > 8
			|| !['vegetation', 'water'].includes(cluster.kind)) {
			throw new TypeError('Night-mote habitats need finite metre coordinates, radius .5–8 and vegetation/water kind.');
		}
		return {...cluster};
	});
	if (!habitats.length) return [];
	return Array.from({length: NIGHT_MOTE_CAPACITY}, (_, index) => {
		const cluster = habitats[index % habitats.length];
		const seed = ((Math.imul(index + 1, 1664525) + 1013904223) >>> 0) / 4294967296;
		const angle = index * 2.399963229728653;
		const radius = cluster.radius * (.24 + .6 * ((index * .61803398875) % 1));
		return Object.freeze({
			x: cluster.x + Math.cos(angle) * radius,
			y: cluster.y + (cluster.kind === 'water' ? .28 : .48) + ((index * .41421356237) % 1) * .95,
			z: cluster.z + Math.sin(angle) * radius,
			phase: angle + seed * 6.283185307,
			size: .075 + ((index * .38196601125) % 1) * .035,
			cool: cluster.kind === 'water' && index % 5 === 0,
		});
	});
}

/** Writes into the caller's reusable output. At reduced motion, both flight and pulsing stop. */
export function sampleNightMote(seed, naturePhase, reducedMotion, focus, opacity, out) {
	const t = reducedMotion ? 0 : (Number.isFinite(naturePhase) ? naturePhase : 0);
	const drift = reducedMotion ? 0 : .34;
	// NatureClock.phase wraps at 2π. Integer harmonics keep flight and pulses continuous at that wrap.
	out.x = seed.x + Math.sin(t + seed.phase) * drift;
	out.y = seed.y + Math.sin(t * 2 + seed.phase * 1.7) * drift * .55;
	out.z = seed.z + Math.cos(t + seed.phase * 1.3) * drift;
	const distance = Math.hypot(out.x - focus.x, out.y - focus.y, out.z - focus.z);
	const distanceFade = smooth(1.25, 2.5, distance) * (1 - smooth(24, 36, distance));
	const pulse = reducedMotion ? .5 : .22 + .78 * Math.pow(.5 + .5 * Math.sin(t + seed.phase), 3);
	out.alpha = clamp(opacity, 0, 1) * distanceFade * pulse * .72;
	return out;
}
