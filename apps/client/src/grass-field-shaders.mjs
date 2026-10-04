/**
 * Grass field shader code (grass-v1) for the PBR MaterialPluginBase in grass-field.ts. GLSL and WGSL are generated
 * from one template, so the two renderers run the same maths (tests/grass-field-shaders.test.mjs checks token hygiene,
 * hook names, balanced preprocessor blocks and that every varying is declared in both stages).
 *
 * Vertex (per instance, thin instances; the patch mesh sits at the origin so world3.xyz is the instance root):
 * - LOD presence p = saturate(1 + (fTier * f(d) - r) / window) from the eye distance (spec §6.2); hidden instances and
 *   switched-off optional parts collapse to the root (zero-area triangles, no fragments); fading instances sink
 *   (height x mix(0.3, 1, p), width x mix(0.7, 1, p)); far survivors widen (coverage compensation).
 * - Atlas UV decode (grass-placement.mjs ATLAS encoding): uv in atlas units, u < 0 = instance column, v >= 4 =
 *   optional part, instance mirror flips u inside the cell.
 * - Wind: the nature-motion.ts sway formula on the shared NatureClock (phase, strength), per-instance spatial phase
 *   like nature-motion's "uv2" mode so a tuft moves as one piece and gust waves cross grass and trees together;
 *   amplitude scales with the instance height; arc correction keeps blades from stretching; player bend.
 * - Root colour: the ground's own chain at the root (vertex tint x terrain albedoColor x the meadow-surface macro,
 *   same noise code as meadow-surface.ts) in texture mode, or a per-instance ground colour in mean mode.
 * Fragment:
 * - mip-coverage alpha test (alpha x (1 + lod k)), per-instance screen-door dither for the LOD fade;
 * - root band = the ground texture sampled at the fragment (texture mode) x the root chain x contact AO, blending to
 *   the atlas x tip tint; night tint toward blue-teal with lighter tips (driven by the sun/moon colour).
 */

/** Meadow macro constants, verbatim from meadow-surface.ts (tests compare them to that file). */
export const MEADOW_MACRO = Object.freeze({
	hash: [127.1, 311.7, 43758.5453],
	broad: { scale: 0.055, offset: [4.8, -1.7] },
	fine: { scale: 0.19, offset: [-2.3, 3.1] },
	soil: { edges: [0.52, 0.86], weights: [0.72, 0.28], color: [0.16, 0.13, 0.065], amount: 0.4 },
	tint: { low: [0.8, 0.93, 0.77], high: [1.11, 1.07, 0.87] },
});

/** nature-motion.ts sway constants (tests compare them to that file). */
export const NATURE_SWAY = Object.freeze({
	spatial: [0.11, 0.075], gust: [0.65, 0.35, 0.4], terms: [[2, 0.65, 0.35], [3, 0.25, 0.6], [11, 0.1, 1]], zRatio: 0.37,
	flutterZ: 0.21, flutterXZ: [2.3, 1.7],
});

export const GRASS_UNIFORMS = Object.freeze(["grassBand", "grassTier", "grassWind", "grassBender", "grassAtlas", "grassGround", "grassGroundFlip", "grassNight", "grassLook"]);
export const GRASS_ATTRIBUTE = "grassInst";
export const GRASS_SAMPLER = "grassGroundSampler";
/** DEV debug views (GRASS_DEBUG values). */
export const GRASS_DEBUG_MODES = Object.freeze({ off: 0, presence: 1, cells: 2, ground: 3, wind: 4, bands: 5, h: 6 });

const f = (n) => (Number.isInteger(n) ? n.toFixed(1) : String(n));

function lang(wgsl) {
	return wgsl ? {
		wgsl, F: "f32", V2: "vec2f", V3: "vec3f", V4: "vec4f",
		u: (n) => `uniforms.${n}`, attr: (n) => `vertexInputs.${n}`, out: (n) => `vertexOutputs.${n}`, inp: (n) => `fragmentInputs.${n}`,
		let: (n, t, e) => `var ${n}: ${t} = ${e};`,
		eye: "scene.vEyePosition.xyz", frag: "fragmentInputs.position.xy", posW: "fragmentInputs.vPositionW",
		dx: (e) => `dpdx(${e})`, dy: (e) => `dpdy(${e})`, mod: (a, b) => `((${a}) % (${b}))`,
		sel: (a, b, c) => `select(${b}, ${a}, ${c})`,
		lin: (e) => `toLinearSpaceVec3(${e})`,
		grad: (t, uv, dx, dy) => `textureSampleGrad(${t}, ${t}Sampler, ${uv}, ${dx}, ${dy})`,
		discard: "discard;",
	} : {
		wgsl, F: "float", V2: "vec2", V3: "vec3", V4: "vec4",
		u: (n) => n, attr: (n) => n, out: (n) => n, inp: (n) => n,
		let: (n, t, e) => `${t} ${n} = ${e};`,
		eye: "vEyePosition.xyz", frag: "gl_FragCoord.xy", posW: "vPositionW",
		dx: (e) => `dFdx(${e})`, dy: (e) => `dFdy(${e})`, mod: (a, b) => `mod(${a}, ${b})`,
		sel: (a, b, c) => `((${c}) ? (${a}) : (${b}))`,
		lin: (e) => `toLinearSpace(${e})`,
		grad: (t, uv, dx, dy) => `textureGrad(${t}, ${uv}, ${dx}, ${dy})`,
		discard: "discard;",
	};
}

/** Unpack a 24-bit float into three bytes / 255 (grass-placement.mjs pack3). */
function unpackFn(L) {
	return L.wgsl
		? `fn grassUnpack(v: f32) -> vec3f {
	let a = v - 256.0 * floor(v / 256.0);
	let rest = floor(v / 256.0);
	let b = rest - 256.0 * floor(rest / 256.0);
	let c = floor(v / 65536.0);
	return vec3f(a, b, c) / 255.0;
}`
		: `vec3 grassUnpack(float v) {
	float a = v - 256.0 * floor(v / 256.0);
	float rest = floor(v / 256.0);
	float b = rest - 256.0 * floor(rest / 256.0);
	float c = floor(v / 65536.0);
	return vec3(a, b, c) / 255.0;
}`;
}

/** The meadow-surface.ts value noise, renamed (identical maths). */
function meadowFns(L) {
	const [kx, kz, km] = MEADOW_MACRO.hash;
	return L.wgsl
		? `fn grassMeadowHash(p: vec2f) -> f32 { return fract(sin(dot(p, vec2f(${f(kx)}, ${f(kz)}))) * ${f(km)}); }
fn grassMeadowNoise(p: vec2f) -> f32 {
	let i = floor(p); let fr = fract(p); let w = fr * fr * (vec2f(3.0) - 2.0 * fr);
	return mix(mix(grassMeadowHash(i), grassMeadowHash(i + vec2f(1.0, 0.0)), w.x),
		mix(grassMeadowHash(i + vec2f(0.0, 1.0)), grassMeadowHash(i + vec2f(1.0, 1.0)), w.x), w.y);
}`
		: `float grassMeadowHash(vec2 p) { return fract(sin(dot(p, vec2(${f(kx)}, ${f(kz)}))) * ${f(km)}); }
float grassMeadowNoise(vec2 p) {
	vec2 i = floor(p); vec2 fr = fract(p); vec2 w = fr * fr * (3.0 - 2.0 * fr);
	return mix(mix(grassMeadowHash(i), grassMeadowHash(i + vec2(1.0, 0.0)), w.x),
		mix(grassMeadowHash(i + vec2(0.0, 1.0)), grassMeadowHash(i + vec2(1.0, 1.0)), w.x), w.y);
}`;
}

function vertexDefinitions(L) {
	const varyings = L.wgsl
		? `attribute ${"grassInst"}: vec4f;
varying vGrassA: vec4f;
varying vGrassTint: vec3f;
varying vGrassGround: vec4f;
varying vGrassAtlasUV: vec2f;
varying vGrassDebug: vec4f;`
		: `attribute vec4 grassInst;
varying vec4 vGrassA;
varying vec3 vGrassTint;
varying vec4 vGrassGround;
varying vec2 vGrassAtlasUV;
varying vec4 vGrassDebug;`;
	return `#ifdef GRASS_FIELD
${varyings}
${unpackFn(L)}
${meadowFns(L)}
#endif`;
}

function vertexUpdatePosition(L) {
	const { u, attr, F, V2, V3, V4 } = L;
	const d = L.let;
	const M = MEADOW_MACRO;
	return `#ifdef GRASS_FIELD
${d("gRoot", V3, `${attr("world3")}.xyz`)}
${d("gHeight", F, `length(${attr("world1")}.xyz)`)}
${d("gDist", F, `length(${L.eye} - gRoot)`)}
${d("gB", V4, u("grassBand"))}
${d("gT", V4, u("grassTier"))}
${d("gProfile", F, `1.0`)}
if (gDist > gB.x) { gProfile = mix(1.0, gB.w, clamp((gDist - gB.x) / max(gB.y - gB.x, 0.001), 0.0, 1.0)); }
if (gDist > gB.y) { gProfile = mix(gB.w, 0.0, clamp((gDist - gB.y) / max(gB.z - gB.y, 0.001), 0.0, 1.0)); }
${d("gIdx", F, `floor(${attr("grassInst")}.x)`)}
${d("gR", F, `fract(${attr("grassInst")}.x) / 0.998`)}
${d("gMirror", F, L.mod("gIdx", "2.0"))}
${d("gCol", F, `floor(gIdx * 0.5)`)}
${d("gPresence", F, `clamp(1.0 + (gT.x * gProfile - gR) / max(gT.y, 0.0001), 0.0, 1.0)`)}
gPresence = gPresence * (1.0 - smoothstep(gB.z - min(6.0, (gB.z - gB.y) / 3.0), gB.z, gDist));
if (gDist >= gB.z) { gPresence = 0.0; }
if (gR >= gT.x) { gPresence = 0.0; }
${d("gMisc", V3, `grassUnpack(${attr("grassInst")}.w)`)}
${d("gV", F, `${attr("uv")}.y`)}
${d("gOptional", F, `step(4.0, gV)`)}
gV = gV - 4.0 * gOptional;
${d("gShow", F, `gPresence * mix(1.0, step(0.5, gMisc.z), gOptional)`)}
${d("gSinkH", F, `mix(0.3, 1.0, gPresence) * (1.0 + 0.1 * (1.0 - gProfile))`)}
${d("gSinkW", F, `mix(0.7, 1.0, gPresence) * (1.0 + 0.25 * (1.0 - gProfile))`)}
positionUpdated = ${V3}(positionUpdated.x * gSinkW, positionUpdated.y * gSinkH, positionUpdated.z * gSinkW) * step(0.0001, gShow);
${d("gU", F, `${attr("uv")}.x`)}
${d("gVariable", F, `step(gU, 0.0)`)}
${d("gUnits", F, `abs(gU)`)}
${d("gCell", F, `floor(gUnits)`)}
${d("gLocal", F, `gUnits - gCell`)}
gLocal = mix(gLocal, 1.0 - gLocal, gMirror);
gCell = gCell + gVariable * gCol;
uvUpdated = ${V2}((gCell + gLocal) / ${u("grassAtlas")}.x, gV / ${u("grassAtlas")}.y);
${L.out("vGrassAtlasUV")} = uvUpdated;
${d("gH", F, `clamp(${attr("position")}.y, 0.0, 1.0)`)}
${L.out("vGrassA")} = ${V4}(gH, gPresence, fract(gR * 7.31 + gCol * 0.137 + gMirror * 0.29), gMisc.x);
${L.out("vGrassTint")} = grassUnpack(${attr("grassInst")}.y) * 2.0;
${d("gGroundRaw", V3, `grassUnpack(${attr("grassInst")}.z)`)}
gGroundRaw = gGroundRaw * gGroundRaw;
#ifdef GRASS_GROUND_TEX
${d("gBroad", F, `grassMeadowNoise(gRoot.xz * ${f(M.broad.scale)} + ${V2}(${f(M.broad.offset[0])}, ${f(M.broad.offset[1])}))`)}
${d("gFine", F, `grassMeadowNoise(gRoot.xz * ${f(M.fine.scale)} + ${V2}(${f(M.fine.offset[0])}, ${f(M.fine.offset[1])}))`)}
${d("gSoil", F, `smoothstep(${f(M.soil.edges[0])}, ${f(M.soil.edges[1])}, gBroad * ${f(M.soil.weights[0])} + gFine * ${f(M.soil.weights[1])})`)}
${L.out("vGrassGround")} = ${V4}(gGroundRaw * ${u("grassGround")}.rgb * mix(${V3}(${M.tint.low.map(f).join(", ")}), ${V3}(${M.tint.high.map(f).join(", ")}), gBroad), gSoil * ${f(M.soil.amount)});
#else
${L.out("vGrassGround")} = ${V4}(gGroundRaw, 0.0);
#endif
${L.out("vGrassDebug")} = ${V4}(gProfile, gCol, gR, 0.0);
#endif`;
}

function vertexUpdateWorldPos(L) {
	const { u, F, V2, V4 } = L;
	const d = L.let;
	const N = NATURE_SWAY;
	return `#ifdef GRASS_FIELD
${d("gW", V4, u("grassWind"))}
${d("gWeight", F, `pow(gH, 1.5) * step(0.0001, gShow)`)}
${d("gSpatial", F, `gRoot.x * ${f(N.spatial[0])} + gRoot.z * ${f(N.spatial[1])}`)}
${d("gClump", F, `fract(gR * 3.17 + gCol * 0.23) * 6.2831853`)}
${d("gGust", F, `${f(N.gust[0])} + ${f(N.gust[1])} * sin(gW.x + gSpatial * ${f(N.gust[2])})`)}
${d("gSway", F, `sin(gW.x * 2.0 + gSpatial + gClump * 0.35) * 0.65 + sin(gW.x * 3.0 + worldPos.z * ${f(N.flutterZ)} + gClump * 0.6) * 0.25 + sin(gW.x * 11.0 + worldPos.x * ${f(N.flutterXZ[0])} + worldPos.z * ${f(N.flutterXZ[1])} + gClump) * 0.1`)}
${d("gFarWind", F, `mix(1.0, gT.z, smoothstep(gB.x, gB.y, gDist))`)}
${d("gAmp", F, `gW.y * gHeight * gMisc.y * 2.0 * gFarWind * mix(0.3, 1.0, gPresence)`)}
${d("gDelta", V2, `${V2}(1.0, ${f(N.zRatio)}) * (gSway * gGust * gWeight * gAmp)`)}
${d("gBend", V4, u("grassBender"))}
${d("gToB", V2, `gRoot.xz - gBend.xy`)}
${d("gBd", F, `length(gToB)`)}
${d("gBk", F, `clamp(1.0 - gBd / max(gBend.z, 0.001), 0.0, 1.0)`)}
${d("gBf", F, `gBend.w * gBk * gBk`)}
${d("gBdir", V2, L.sel(`gToB / max(gBd, 0.0001)`, `${V2}(1.0, 0.0)`, `gBd > 0.05`))}
gDelta = gDelta + gBdir * (gBf * 0.5 * gHeight * gWeight);
${d("gLen", F, `length(gDelta)`)}
${d("gCap", F, `0.45 * gHeight`)}
if (gLen > gCap) { gDelta = gDelta * (gCap / gLen); }
${d("gDrop", F, `0.5 * dot(gDelta, gDelta) / max(gHeight, 0.05) + gBf * 0.35 * gHeight * gWeight`)}
worldPos = ${V4}(worldPos.x + gDelta.x, worldPos.y - gDrop, worldPos.z + gDelta.y, worldPos.w);
${L.out("vPositionW")} = worldPos.xyz;
${L.out("vGrassDebug")} = ${V4}(gProfile, gCol, gR, gWeight * gGust);
#endif`;
}

function fragmentDefinitions(L) {
	const varyings = L.wgsl
		? `varying vGrassA: vec4f;
varying vGrassTint: vec3f;
varying vGrassGround: vec4f;
varying vGrassAtlasUV: vec2f;
varying vGrassDebug: vec4f;
var<private> grassLodG: f32 = 0.0;
var<private> grassGdx: vec2f = vec2f(0.0);
var<private> grassGdy: vec2f = vec2f(0.0);
var<private> grassDebugOut: vec3f = vec3f(0.0);`
		: `varying vec4 vGrassA;
varying vec3 vGrassTint;
varying vec4 vGrassGround;
varying vec2 vGrassAtlasUV;
varying vec4 vGrassDebug;
float grassLodG = 0.0;
vec2 grassGdx = vec2(0.0);
vec2 grassGdy = vec2(0.0);
vec3 grassDebugOut = vec3(0.0);`;
	const sampler = L.wgsl ? "var grassGroundSamplerSampler: sampler;\nvar grassGroundSampler: texture_2d<f32>;" : "uniform sampler2D grassGroundSampler;";
	return `#ifdef GRASS_FIELD
#include<bayerDitherFunctions>
${varyings}
#ifdef GRASS_GROUND_TEX
${sampler}
#endif
#endif`;
}

function fragmentMainBegin(L) {
	const { u, inp, V2 } = L;
	const d = L.let;
	// Derivatives in uniform control flow (WGSL uniformity rule); the ground texture is then fetched with explicit
	// gradients inside the root-band branch only.
	return `#ifdef GRASS_FIELD
${d("gAtlasPx", V2, `${inp("vGrassAtlasUV")} * ${V2}(${u("grassAtlas")}.x, ${u("grassAtlas")}.y) * 256.0`)}
${d("gAdx", V2, L.dx("gAtlasPx"))}
${d("gAdy", V2, L.dy("gAtlasPx"))}
grassLodG = clamp(0.5 * log2(max(max(dot(gAdx, gAdx), dot(gAdy, gAdy)), 0.00000001)), 0.0, ${u("grassAtlas")}.z);
#ifdef GRASS_GROUND_TEX
grassGdx = ${L.dx(`${L.posW}.xz`)};
grassGdy = ${L.dy(`${L.posW}.xz`)};
#endif
#endif`;
}

function fragmentUpdateAlpha(L) {
	const { u, inp, F, V2, V3 } = L;
	const d = L.let;
	const soil = MEADOW_MACRO.soil.color.map(f).join(", ");
	return `#ifdef GRASS_FIELD
${d("gA", F, `albedoTexture.a * (1.0 + grassLodG * ${u("grassAtlas")}.w)`)}
${d("gDither", F, `fract(bayerDither8(floor(${L.frag})) / 64.0 + ${inp("vGrassA")}.z)`)}
if (gA < 0.5 || gDither >= ${inp("vGrassA")}.y) { ${L.discard} }
${d("gHf", F, `${inp("vGrassA")}.x`)}
${d("gLook", L.V4, u("grassLook"))}
${d("gTip", V3, `surfaceAlbedo * ${inp("vGrassTint")}`)}
${d("gGroundC", V3, `${inp("vGrassGround")}.rgb`)}
#ifdef GRASS_GROUND_TEX
if (gHf < gLook.y) {
	${d("gFlip", F, `1.0`)}
	${d("gFR", L.V4, u("grassGroundFlip"))}
	if (${L.posW}.x >= gFR.x && ${L.posW}.x <= gFR.y && ${L.posW}.z >= gFR.z && ${L.posW}.z <= gFR.w) { gFlip = -1.0; }
	${d("gGuv", V2, `${V2}(${L.posW}.x, ${L.posW}.z * gFlip) * ${u("grassGround")}.w`)}
	${d("gGtex", V3, L.lin(`${L.grad("grassGroundSampler", "gGuv", `grassGdx * ${V2}(1.0, gFlip) * ${u("grassGround")}.w`, `grassGdy * ${V2}(1.0, gFlip) * ${u("grassGround")}.w`)}.rgb`))}
	gGroundC = mix(gGtex * ${inp("vGrassGround")}.rgb, ${V3}(${soil}), ${inp("vGrassGround")}.w);
}
#endif
${d("gAO", F, `mix(${inp("vGrassA")}.w, 1.0, smoothstep(0.0, 0.24, gHf))`)}
surfaceAlbedo = mix(gGroundC * gAO, gTip, smoothstep(gLook.x, gLook.y, gHf));
${d("gN", L.V4, u("grassNight"))}
${d("gLum", F, `dot(surfaceAlbedo, ${V3}(0.2126, 0.7152, 0.0722))`)}
${d("gNightCol", V3, `gN.yzw * gLum * (1.0 + gLook.w * gHf * gHf) + gN.yzw * gLook.z * gHf * gHf * 0.04`)}
surfaceAlbedo = mix(surfaceAlbedo, gNightCol, gN.x * smoothstep(0.02, 0.3, gHf));
surfaceAlbedo = clamp(surfaceAlbedo, ${V3}(0.004), ${V3}(0.82));
#if GRASS_DEBUG == 1
grassDebugOut = mix(${V3}(0.9, 0.1, 0.1), ${V3}(0.1, 0.9, 0.2), ${inp("vGrassA")}.y);
#elif GRASS_DEBUG == 2
grassDebugOut = fract(${V3}(${inp("vGrassDebug")}.y * 0.37 + 0.1, ${inp("vGrassDebug")}.y * 0.61 + 0.3, ${inp("vGrassDebug")}.y * 0.13 + 0.6));
#elif GRASS_DEBUG == 3
grassDebugOut = gGroundC;
#elif GRASS_DEBUG == 4
grassDebugOut = ${V3}(clamp(${inp("vGrassDebug")}.w, 0.0, 1.0), 0.2, 1.0 - clamp(${inp("vGrassDebug")}.w, 0.0, 1.0));
#elif GRASS_DEBUG == 5
grassDebugOut = ${V3}(${inp("vGrassDebug")}.x, ${inp("vGrassDebug")}.z, 0.15);
#elif GRASS_DEBUG == 6
grassDebugOut = ${V3}(gHf);
#endif
#endif`;
}

function fragmentBeforeFragColor(L) {
	return `#ifdef GRASS_FIELD
#if GRASS_DEBUG > 0
finalColor = ${L.V4}(grassDebugOut, 1.0);
#endif
#endif`;
}

const CACHE = new Map();

/**
 * Custom code for a stage ("vertex" | "fragment") and language. Stateless (MaterialPluginBase calls getCustomCode
 * from its constructor before subclass fields exist); variants are selected by defines.
 */
export function grassCustomCode(stage, wgsl) {
	const key = `${stage}:${wgsl ? "wgsl" : "glsl"}`;
	let code = CACHE.get(key);
	if (code) return code;
	const L = lang(wgsl);
	if (stage === "vertex") {
		code = {
			CUSTOM_VERTEX_DEFINITIONS: vertexDefinitions(L),
			CUSTOM_VERTEX_UPDATE_POSITION: vertexUpdatePosition(L),
			CUSTOM_VERTEX_UPDATE_WORLDPOS: vertexUpdateWorldPos(L),
		};
	} else if (stage === "fragment") {
		code = {
			CUSTOM_FRAGMENT_DEFINITIONS: fragmentDefinitions(L),
			CUSTOM_FRAGMENT_MAIN_BEGIN: fragmentMainBegin(L),
			CUSTOM_FRAGMENT_UPDATE_ALPHA: fragmentUpdateAlpha(L),
			CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR: fragmentBeforeFragColor(L),
		};
	} else return null;
	CACHE.set(key, code);
	return code;
}

/** GLSL uniform declarations (used when the engine has no UBOs; WGSL declares them through the UBO list). */
export const GRASS_GLSL_UNIFORMS = GRASS_UNIFORMS.map((name) => `uniform vec4 ${name};`).join("\n");
