/** Rain uses part of the weather budget, including contacts; never a second budget. */
export type StormRainQuality = 'low' | 'medium' | 'high' | 'ultra';
export interface StormRainBudget {
	readonly near: number; readonly far: number; readonly contacts: number;
	readonly total: number; readonly groundAnchors: number; readonly radius: number;
}
const totals: Record<StormRainQuality, number> = {low:24, medium:64, high:144, ultra:288};
export function rainBudget(quality: StormRainQuality, ceiling = totals[quality]): StormRainBudget {
	const total = Math.max(0, Math.min(totals[quality], Math.floor(Number.isFinite(ceiling) ? ceiling : 0)));
	const contacts = total < 8 ? 0 : Math.max(2, Math.floor(total / 12));
	const far = Math.floor((total - contacts) * .32);
	return {near:total - contacts - far, far, contacts, total, groundAnchors:quality === 'low' ? 6 : quality === 'medium' ? 10 : 16, radius:quality === 'low' ? 8 : quality === 'medium' ? 11 : 15};
}
export function rainAmount(rain: number, sheltered: boolean, reducedMotion: boolean): number {
	return sheltered || !Number.isFinite(rain) ? 0 : Math.max(0, Math.min(1, rain)) * (reducedMotion ? .45 : 1);
}
/** NatureClock.phase is radians and wraps. Integer harmonics stay continuous at 2π. */
export function rainWind(windStrength: number, phase: number): readonly [number, number] {
	const strength = Number.isFinite(windStrength) ? Math.max(0, Math.min(2, windStrength)) : 0;
	const angle = Number.isFinite(phase) ? phase : 0;
	return [strength * (1.8 + .35 * Math.sin(angle)), strength * (.65 + .22 * Math.cos(angle * 2))];
}
/** Two 16×32 RGBA masks: 4 KiB total, no canvas, browser globals or artwork request. */
export function rainMask(kind: 'streak' | 'contact'): Uint8Array {
	const pixels = new Uint8Array(16 * 32 * 4);
	for (let y=0; y<32; y++) for (let x=0; x<16; x++) {
		const u=(x+.5)/16*2-1, v=(y+.5)/32*2-1;
		const radius=Math.hypot(u,v);
		const alpha=kind === 'streak'
			? Math.exp(-u*u*25)*Math.pow(Math.max(0,1-v*v),1.7)
			: Math.max(0,1-Math.abs(radius-.63)/.14) * .8 + Math.exp(-(u*u+v*v)*38)*.24;
		const i=(y*16+x)*4;
		// Subtle violet at the feathered edge; most of the streak remains neutral white.
		pixels[i]=236; pixels[i+1]=kind==='streak' && Math.abs(u)>.25 ? 226 : 239; pixels[i+2]=248;
		pixels[i+3]=Math.round(Math.min(1,alpha)*255);
	}
	return pixels;
}
