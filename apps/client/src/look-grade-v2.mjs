// C-LOOK-V2 (lane look-grade): pure grade maths for ?look=v2 (DEV, default off).
// Targets: docs/reviews/2026-10-03-reference-look-target-v2.md §3 and §5 #1 #2 #7. world-weather.ts samples
// sampleLookGrade() from the one world clock; look-grade-v2.ts uses the sky remap, the pool maths and fogDensity.
const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
const lerp = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
const mix = (a, b, t) => a + (b - a) * t;
const clamp01 = v => Math.max(0, Math.min(1, v));
// Owner D8 palette: blue zenith/horizon; distance fog remains a separate shared-clock grade.
const stops = [
 [0, '#1d3866', '#3d5b86', '#2b4366'],
 [5, '#24406e', '#5a7398', '#4a6286'],
 [6.5, '#dbadc6', '#f1d6c4', '#a9b3cb'],
 [9, '#a5cbfb', '#aed3f0', '#b6cbe6'],
 [15.5, '#a5cbfb', '#aed3f0', '#b6cbe6'],
 [17.5, '#ffbca1', '#fee0a1', '#c4b8b4'],
 [18.5, '#bf92ed', '#ffbeff', '#9c9ccc'],
 [20, '#1d3866', '#3d5b86', '#2b4366'],
 [24, '#1d3866', '#3d5b86', '#2b4366'],
].map(([hour, zenith, horizon, fog]) => ({hour, zenith:rgb(zenith), horizon:rgb(horizon), fog:rgb(fog)}));
const storm = {zenith:rgb('#2a2438'), horizon:rgb('#5a5566'), fog:rgb('#4a4658')};
/** Pure grade of the existing synchronized sample; never advances a second clock. */
export function sampleLookGrade(state) {
 const hours = Number.isFinite(state?.hours) ? ((state.hours % 24) + 24) % 24 : 12;
 const day = clamp01(Number.isFinite(state?.daylight) ? state.daylight : 1);
 const rain = clamp01(Number.isFinite(state?.rain) ? state.rain : 0);
 let index = 0; while (index < stops.length - 2 && hours > stops[index + 1].hour) index++;
 const a=stops[index], b=stops[index+1], t=(hours-a.hour)/(b.hour-a.hour);
 const sky = {};
 for (const key of ['zenith','horizon','fog']) sky[key]=lerp(lerp(a[key],b[key],t),storm[key],rain);
 return {...sky,
   // Warm key by day, cool moon by night; sky-coloured fill (never grey) and a teal-blue night bounce.
   sun:lerp(rgb('#8fb0ea'),rgb('#ffe2b6'),day), fill:lerp(rgb('#6fa5c0'),rgb('#9ec2f2'),day),
   ground:lerp(rgb('#24384a'),rgb('#5a5f3e'),day),
   sunIntensity:mix(.42,2.0,day)*(1-rain*.64), fillIntensity:mix(.34,.30,day)-rain*.08,
   exposure:mix(1.15,1.0,day), contrast:mix(1.22,1.30,day),
   saturation:mix(-4,18,day)-rain*10,
   fogDensity:mix(.0024,.0018,day)+rain*.0012};
}
/**
 * Sky dome remap: canvas fraction (0 = zenith row, 1 = bottom row of env-sky-texture) for a dome vertex at
 * `elevationDeg`. The painter keeps zenith colour on 0..0.48 and horizon colour on 0.76..1, so the whole
 * gradient is placed in the first 10 deg above the horizon, the band the 13 m camera actually sees.
 */
export function skyCanvasFraction(elevationDeg) {
 const e = Math.max(-90, Math.min(90, elevationDeg));
 if (e >= 10) return .48 * (1 - (e - 10) / 80);
 if (e >= 0) return mix(.76, .48, e / 10);
 return mix(.76, 1, -e / 90);
}
/** Night light-pool strength from daylight: off by day, full by night (on near 18:30, full near 19:30). */
export function poolStrength(daylight, rain = 0) {
 const night = clamp01((.38 - clamp01(daylight)) / .3);
 return night * night * (3 - 2 * night) * (1 - clamp01(rain) * .25);
}
export const LOOK_POOL = Object.freeze({radius: 5, color: Object.freeze([1, .72, .44]), cell: 2.5,
 emitterPattern: /lantern|lamp|brazier|campfire|torch|fire_glow|fire core|watch-?fire/i});
/** Groups emitter vertices (world [x,y,z]) into pool anchors on a `cell` m grid; y = lowest point (the base). */
export function clusterAnchors(points, cell = LOOK_POOL.cell, existing = []) {
 const bins = new Map();
 for (const [x, y, z] of points) {
  const key = Math.round(x / cell) + ':' + Math.round(z / cell);
  const bin = bins.get(key) ?? {x:0, z:0, n:0, y:Infinity};
  bin.x += x; bin.z += z; bin.n++; bin.y = Math.min(bin.y, y); bins.set(key, bin);
 }
 const out = [...existing];
 for (const bin of bins.values()) {
  const anchor = {x: bin.x / bin.n, y: bin.y, z: bin.z / bin.n};
  if (!out.some(o => Math.hypot(o.x - anchor.x, o.z - anchor.z) < cell)) out.push(anchor);
 }
 return out.slice(existing.length);
}
