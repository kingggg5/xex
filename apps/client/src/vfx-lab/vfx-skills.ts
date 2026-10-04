import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { TrailMesh } from "@babylonjs/core/Meshes/trailMesh";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import "@babylonjs/core/Layers/glowLayer";
import type { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import type { Particle } from "@babylonjs/core/Particles/particle";
import type { PointLight } from "@babylonjs/core/Lights/pointLight";
import type { Scene } from "@babylonjs/core/scene";
import { VFX_INSTANCE_KIND, createVfxMaterial } from "./vfx-material";
import {
	PALETTE, beams, billboard, clamp01, decal, easeInCubic, easeInQuad, easeOutBack, easeOutCubic, easeOutQuad, envelope,
	hash01, instanced, lerp, meshLayer, particles, type LightPool, type ParticleLayer, type VfxKit, type VfxLayer,
} from "./vfx-kit";

export interface VfxTarget {
	readonly root: TransformNode;
	readonly material: StandardMaterial;
	readonly home: Vector3;
	readonly baseEmissive: Color3;
}

export interface VfxContext {
	readonly scene: Scene;
	readonly kit: VfxKit;
	readonly lights: LightPool;
	readonly targets: readonly VfxTarget[];
	shake(amplitude: number, seconds: number): void;
	eye(): Vector3;
}

export interface SkillInstance {
	readonly id: string;
	readonly duration: number;
	readonly contract: string;
	update(t: number): void;
	layers(): VfxLayer[];
	dispose(): void;
}

export type SkillFactory = (ctx: VfxContext, origin: Vector3, facing: number) => SkillInstance;

const hdr = (hex: string, gain: number, alpha = 1) => { const c = Color3.FromHexString(hex); return new Color4(c.r * gain, c.g * gain, c.b * gain, alpha); };
const v3 = (x: number, y: number, z: number) => new Vector3(x, y, z);
const forwardOf = (facing: number) => v3(Math.sin(facing), 0, Math.cos(facing));
const rightOf = (facing: number) => v3(Math.cos(facing), 0, -Math.sin(facing));

/** Per-particle custom state for analytic motion (spirals, pulls) layered over Babylon's default update. */
const motion = new WeakMap<Particle, { a: number; r: number; y: number; speed: number; seed: number; origin: Vector3 }>();

function lightUp(light: PointLight | null, at: Vector3, color: string, intensity: number, range: number): void {
	if (!light) return;
	light.position.copyFrom(at);
	light.diffuse.copyFrom(Color3.FromHexString(color));
	light.intensity = intensity;
	light.range = range;
}

/** Let the scene's env-glow GlowLayer bloom this mesh with its own (VFX) material. */
function glowWith(scene: Scene, mesh: Mesh): void {
	const glow = scene.getGlowLayerByName("env-glow");
	glow?.referenceMeshToUseItsOwnMaterial(mesh);
}

/** Hit reaction shared by all skills: emissive flash on the target plus an optional displacement. */
function hitReact(target: VfxTarget, color: string, flash: number, offset: Vector3): void {
	const c = Color3.FromHexString(color);
	target.material.emissiveColor.set(
		target.baseEmissive.r + c.r * flash, target.baseEmissive.g + c.g * flash, target.baseEmissive.b + c.b * flash);
	target.root.position.copyFrom(target.home).addInPlace(offset);
}

// =================================================================================================
// 3.1 xs_bladeward_nova — swordsman self-AoE, r = 4.0 m, cast 150 ms, hit at 200 ms
// =================================================================================================

export const bladewardNova: SkillFactory = (ctx, origin) => {
	const { kit } = ctx;
	const P = PALETTE.blade;
	const RADIUS = 4.0;
	const BLADES = 20;
	const layers: VfxLayer[] = [];
	const keep = <T extends VfxLayer>(layer: T) => { layers.push(layer); return layer; };

	const ring = keep(decal(kit, "nova-ring", "runeBlade", "blade", { intensity: 1.55, opacity: 0.95, valueScale: 0.88 }));
	ring.mesh.position.set(origin.x, origin.y + 0.03, origin.z);
	ring.mesh.scaling.setAll((RADIUS / 0.93) * 2);

	const flash = keep(decal(kit, "nova-flash", "star", "blade", { intensity: 1.15, midAt: 0.72, valueScale: 0.9 }));
	flash.mesh.position.set(origin.x, origin.y + 0.05, origin.z);

	const shock = keep(decal(kit, "nova-shock", "shock", "blade", { intensity: 1.15, midAt: 0.72 }));
	shock.mesh.position.set(origin.x, origin.y + 0.04, origin.z);

	const wall = keep(meshLayer(kit, "nova-wall", kit.ringWall, "streak", "blade", { intensity: 1.3, opacity: 1, fog: true, valueScale: 1.25 }));
	wall.mesh.position.copyFrom(origin);
	wall.fx.addFade = 7;

	const blades = keep(instanced(kit, "nova-blades", kit.blade, "streak", "blade", BLADES,
		{ fresnel: 2.6, erodeAlongV: true, intensity: 0.8, doubleSided: false, midAt: 0.74 }));
	glowWith(ctx.scene, blades.mesh);
	blades.fx.erosionEdge = 0.08;
	const cracks = keep(instanced(kit, "nova-cracks", "decal", "cracks", "blade", BLADES,
		{ scorch: P.dark, blend: "blend", intensity: 2.0 }));

	const bladeData = Array.from({ length: BLADES }, (_, i) => {
		const inner = i >= 12;
		const k = inner ? i - 12 : i;
		const a = inner ? ((k + 0.5) / 8) * Math.PI * 2 + (hash01(i + 3) - 0.5) * 0.2 : (k / 12) * Math.PI * 2 + (hash01(i + 3) - 0.5) * 0.12;
		const r = inner ? 1.75 : k % 2 ? 3.5 : 2.9;
		return {
			a, r,
			base: v3(origin.x + Math.sin(a) * r, origin.y, origin.z + Math.cos(a) * r),
			delay: inner ? 0.19 + k * 0.01 : 0.15 + k * 0.008,
			tilt: ((inner ? 18 : 10) + hash01(i + 11) * 12) * Math.PI / 180,
			yaw: (hash01(i + 23) - 0.5) * 0.28,
			scale: inner ? 0.75 + hash01(i + 37) * 0.2 : 1.2 + hash01(i + 37) * 0.35,
			erodeAt: (inner ? 0.62 : 0.7) + k * 0.02 + hash01(i + 41) * 0.05,
		};
	});
	blades.instances.forEach((inst, i) => {
		const d = bladeData[i];
		inst.rotation.set(0, d.a + d.yaw, 0);
		inst.scaling.setAll(d.scale);
	});
	cracks.instances.forEach((inst, i) => {
		const d = bladeData[i];
		inst.position.set(d.base.x, origin.y + 0.02 + i * 0.0005, d.base.z);
		inst.rotation.y = hash01(i + 53) * Math.PI * 2;
		inst.scaling.setAll(1.6 + hash01(i + 59) * 0.5);
	});

	const motes = keep(particles(kit, "nova-motes", { capacity: 24, texture: "disc", color: hdr(P.core, 3.0), color2: hdr(P.mid, 2.6), size: [0.24, 0.34], life: [0.15, 0.15] }));
	const dust = keep(particles(kit, "nova-dust", { capacity: 96, texture: "dust", sheet: { cols: 8, rows: 8, cell: 64 }, blend: "standard",
		color: new Color4(0.55, 0.70, 0.86, 0.26), dead: new Color4(0.55, 0.70, 0.86, 0), size: [0.9, 1.6], life: [0.7, 1.0], gravity: v3(0, 0.35, 0) }));
	const shards = keep(particles(kit, "nova-shards", { capacity: 96, texture: "shards", sheet: { cols: 4, rows: 4, cell: 16, random: true }, color: hdr(P.mid, 1.4), dead: hdr(P.edge, 1.0, 0),
		size: [0.12, 0.3], life: [0.55, 0.9], gravity: v3(0, -9, 0) }));
	shards.system.spriteCellChangeSpeed = 0;
	shards.system.minAngularSpeed = -9; shards.system.maxAngularSpeed = 9;
	const mist = keep(particles(kit, "nova-mist", { capacity: 48, texture: "dust", sheet: { cols: 8, rows: 8, cell: 64 }, blend: "add",
		color: hdr(P.mid, 0.35, 0.22), dead: hdr(P.edge, 0.2, 0), size: [1.6, 2.6], life: [1.1, 1.5] }));
	const impacts = keep(particles(kit, "nova-impacts", { capacity: 8, texture: "impact", sheet: { cols: 4, rows: 4, cell: 16 }, color: hdr(P.mid, 1.7), size: [1.7, 1.9], life: [0.28, 0.28] }));
	const arcs = keep(beams(kit, "nova-arcs", "blade", 6, { intensity: 2.2 }));
	glowWith(ctx.scene, ring.mesh);
	for (const layer of [motes, dust, shards, mist, impacts] as ParticleLayer[]) layer.system.start();

	// One emission queue per system, consumed by its start functions in emission order.
	type Job = { at: Vector3; out: Vector3; speed: number; up: number };
	const emitFrom = (layer: ParticleLayer) => {
		const queue: Job[] = [];
		layer.system.startPositionFunction = (_m, pos) => pos.copyFrom(queue[0]?.at ?? origin);
		layer.system.startDirectionFunction = (_m, dir) => {
			const job = queue.shift();
			if (!job) { dir.set(0, 0, 0); return; }
			const spread = 0.6;
			dir.set(job.out.x * job.speed + (Math.random() - 0.5) * spread, job.up * (0.6 + Math.random() * 0.8), job.out.z * job.speed + (Math.random() - 0.5) * spread);
		};
		return (job: Job) => { queue.push(job); layer.system.manualEmitCount = Math.max(0, layer.system.manualEmitCount) + 1; };
	};
	const emitDust = emitFrom(dust), emitShard = emitFrom(shards), emitMist = emitFrom(mist);
	// Motes converge on the hilt along a quarter-turn spiral.
	const hilt = v3(origin.x, origin.y + 1.25, origin.z);
	let moteIndex = 0;
	motes.system.startPositionFunction = (_m, pos, particle) => {
		const k = moteIndex++;
		const a = (k / 16) * Math.PI * 2;
		motion.set(particle, { a, r: RADIUS, y: 0.15, speed: 1, seed: k, origin });
		pos.set(origin.x + Math.sin(a) * RADIUS, origin.y + 0.15, origin.z + Math.cos(a) * RADIUS);
	};
	const baseMotesUpdate = motes.system.updateFunction;
	motes.system.updateFunction = (list) => {
		baseMotesUpdate(list);
		for (const p of list) {
			const s = motion.get(p);
			if (!s) continue;
			const u = easeInQuad(p.age / p.lifeTime);
			const a = s.a + u * 1.6;
			const r = lerp(s.r, 0.15, u);
			p.position.set(origin.x + Math.sin(a) * r, lerp(s.y, hilt.y, u), origin.z + Math.cos(a) * r);
		}
	};

	let emitted = { motes: false, bursts: new Set<number>(), mistUntil: 0, impacts: false };
	const light = ctx.lights.acquire(layers);
	const hit = new Set<VfxTarget>();
	const eyeTmp = new Vector3();
	const arcState = Array.from({ length: 6 }, () => ({ from: 0, born: -1, life: 0, cell: 0 }));

	return {
		id: "xs_bladeward_nova", duration: 2.8,
		contract: "self AoE r 4.0 m · cast 0.15s · hit 1×0.20s",
		layers: () => layers,
		update(t) {
			// L1 telegraph ring: radial wipe 0-150 ms, hold, fade 300-500 ms.
			ring.mesh.setEnabled(t < 0.5);
			ring.fx.wipe = easeOutQuad(t / 0.15);
			ring.fx.opacity = 0.95 * (1 - easeInQuad((t - 0.3) / 0.2));
			ring.mesh.rotation.y = t * 0.6;
			// L2 charge motes spiral into the hilt.
			if (!emitted.motes) { motes.system.manualEmitCount = 16; emitted.motes = true; }
			// L3 ground flash.
			flash.mesh.setEnabled(t >= 0.15 && t < 0.31);
			const f = clamp01((t - 0.15) / 0.15);
			flash.mesh.scaling.setAll(0.8 + 2.4 * easeOutCubic(f));
			flash.fx.opacity = 0.75 * (1 - easeInQuad(f));
			flash.mesh.rotation.y = 0.4 + f * 0.5;
			// L4 shock ring + wall.
			const s = clamp01((t - 0.15) / 0.27);
			shock.mesh.setEnabled(t >= 0.15 && t < 0.42);
			wall.mesh.setEnabled(t >= 0.15 && t < 0.42);
			const shockR = lerp(0.5, 4.6, easeOutCubic(s));
			shock.mesh.scaling.setAll((shockR / 0.93) * 2);
			shock.fx.opacity = 0.85 * (1 - easeInQuad(s));
			wall.mesh.scaling.set(shockR, lerp(0.95, 0.2, s), shockR);
			wall.fx.opacity = 0.9 * (1 - easeInQuad(s));
			wall.fx.scrollV = -t * 2.5;
			// L5 blades rise with overshoot, hum, then erode tip-first.
			blades.instances.forEach((inst, i) => {
				const d = bladeData[i];
				const rise = (t - d.delay) / 0.11;
				const on = rise > 0 && t < d.erodeAt + 0.45;
				inst.setEnabled(on);
				if (!on) return;
				const y = lerp(-1.95, 0.25, easeOutBack(rise, 2.2));
				const out = d.tilt;
				inst.position.set(d.base.x, origin.y + y, d.base.z);
				inst.rotation.set(out, d.a + d.yaw, 0);
				const hum = 1 + 0.12 * Math.sin(t * 38 + i * 1.7) * envelope(t, 0.26, 0.3, 0.7, 0.9);
				const erosion = clamp01((t - d.erodeAt) / 0.4);
				(inst.instancedBuffers[VFX_INSTANCE_KIND] as { x: number; y: number; z: number; w: number }).x = hum * (1 + 0.6 * envelope(t, d.delay, d.delay + 0.04, d.delay + 0.06, d.delay + 0.2));
				(inst.instancedBuffers[VFX_INSTANCE_KIND] as { y: number }).y = erosion * 1.05;
			});
			blades.fx.scrollV = -t * 1.8;
			// L6 cracks: hot seams cool to scorch, then fade.
			cracks.instances.forEach((inst, i) => {
				const d = bladeData[i];
				inst.setEnabled(t >= d.delay && t < 2.65);
				const age = t - d.delay;
				const buffer = inst.instancedBuffers[VFX_INSTANCE_KIND] as { x: number; y: number; z: number; w: number };
				buffer.w = 1 - easeOutQuad(age / 2.3);
				buffer.z = clamp01(age / 0.05) * (1 - easeInQuad((t - 2.1) / 0.55));
				buffer.y = clamp01((t - 2.1) / 0.55) * 0.9;
			});
			// L7 dust + shards at each blade base when it erupts.
			bladeData.forEach((d, i) => {
				if (t >= d.delay + 0.03 && !emitted.bursts.has(i)) {
					emitted.bursts.add(i);
					const out = v3(Math.sin(d.a), 0, Math.cos(d.a));
					for (let k = 0; k < (i >= 12 ? 2 : 4); k++) emitDust({ at: d.base.clone(), out, speed: 0.9, up: 0.5 });
					for (let k = 0; k < (i >= 12 ? 2 : 5); k++) emitShard({ at: d.base.add(v3(0, 0.2, 0)), out, speed: 2.6, up: 5.0 });
				}
			});
			// L11 frost mist drifting out.
			if (t >= 0.26 && t < 0.9 && t >= emitted.mistUntil) {
				emitted.mistUntil = t + 0.06;
				const a = hash01(Math.floor(t * 100)) * Math.PI * 2;
				const r = 1.5 + hash01(Math.floor(t * 100) + 7) * 2.2;
				emitMist({ at: v3(origin.x + Math.sin(a) * r, origin.y + 0.15, origin.z + Math.cos(a) * r), out: v3(Math.sin(a), 0, Math.cos(a)), speed: 0.5, up: 0.05 });
			}
			// L8 lightning between neighbouring blades.
			ctx.eye().subtractToRef(Vector3.ZeroReadOnly, eyeTmp);
			arcState.forEach((arc, k) => {
				const active = t >= 0.26 && t < 0.7;
				if (!active) { arcs.hide(k); return; }
				if (arc.born < 0 || t - arc.born > arc.life) {
					const seed = Math.floor(t * 60) * 7 + k * 13;
					arc.from = Math.floor(hash01(seed) * 12);
					arc.born = t;
					arc.life = 0.06 + hash01(seed + 1) * 0.03;
					arc.cell = Math.floor(hash01(seed + 2) * 16);
				}
				const a = blades.instances[arc.from].position;
				const b = blades.instances[(arc.from + 1) % 12].position;
				const h = 0.45 + 0.5 * hash01(arc.cell + k);
				arcs.set(k, a.add(v3(0, h, 0)), b.add(v3(0, h * 0.8, 0)), 0.5, arc.cell, 1 - (t - arc.born) / arc.life * 0.5);
			});
			arcs.commit(eyeTmp);
			// L9 light flash.
			lightUp(light, v3(origin.x, origin.y + 1.6, origin.z), "#8FD0FF", 2.6 * envelope(t, 0.15, 0.19, 0.22, 0.6) + 0.5 * envelope(t, 0.0, 0.1, 0.12, 0.2), 7.5);
			// L10 hit at 200 ms: impact bursts, flash, knock-up, shake.
			if (t >= 0.2 && !emitted.impacts) {
				emitted.impacts = true;
				ctx.shake(0.10, 0.14);
				for (const target of ctx.targets) {
					if (Vector3.Distance(target.home, origin) <= RADIUS + 0.5) hit.add(target);
				}
				impacts.system.manualEmitCount = hit.size;
				const list = [...hit];
				let n = 0;
				impacts.system.startPositionFunction = (_m, pos) => { const tg = list[n++ % Math.max(1, list.length)]; pos.copyFrom(tg ? tg.home : origin).addInPlaceFromFloats(0, 0.8, 0); };
			}
			for (const target of hit) {
				const age = t - 0.2;
				const lift = age > 0 ? Math.sin(Math.PI * clamp01(age / 0.36)) * 0.42 : 0;
				hitReact(target, "#2B6CFF", 0.42 * (1 - clamp01(age / 0.14)), v3(0, lift, 0));
			}
		},
		dispose() {
			ctx.lights.release(light);
			for (const target of hit) hitReact(target, "#000000", 0, Vector3.ZeroReadOnly as Vector3);
			for (const layer of layers) layer.dispose();
		},
	};
};

// =================================================================================================
// 3.2 xs_gale_palm — projectile 16 m/s from the hand, impact AoE r 2.2 m, knockback 1.5 m
// =================================================================================================

export const galePalm: SkillFactory = (ctx, origin, facing) => {
	const { kit, scene } = ctx;
	const P = PALETTE.gale;
	const layers: VfxLayer[] = [];
	const keep = <T extends VfxLayer>(layer: T) => { layers.push(layer); return layer; };
	const fwd = forwardOf(facing);
	const right = rightOf(facing);
	const hand = origin.add(fwd.scale(0.55)).add(right.scale(0.18)).addInPlaceFromFloats(0, 1.25, 0);
	const target = ctx.targets.reduce<VfxTarget | null>((best, tg) => {
		const d = tg.home.subtract(origin);
		const along = Vector3.Dot(d, fwd);
		if (along < 1 || along > 10) return best;
		return !best || along < Vector3.Dot(best.home.subtract(origin), fwd) ? tg : best;
	}, null);
	const travel = target ? Math.max(1, Vector3.Dot(target.home.subtract(hand), fwd) - 0.4) : 10;
	const RELEASE = 0.2;
	const HIT = RELEASE + travel / 16;
	const impactAt = target ? target.home.add(v3(0, 0.75, 0)) : hand.add(fwd.scale(travel));
	const impactGround = v3(impactAt.x, origin.y, impactAt.z);

	const charge = keep(particles(kit, "gale-charge", { capacity: 4, texture: "swirl", color: hdr(P.mid, 1.9), size: [0.5, 0.5], life: [0.22, 0.22] }));
	const sparks = keep(particles(kit, "gale-sparks", { capacity: 48, texture: "disc", color: hdr(P.core, 2.6), color2: hdr(P.mid, 2.2), size: [0.09, 0.15], life: [0.16, 0.22], billboard: "stretched" }));
	const cone = keep(meshLayer(kit, "gale-cone", kit.cone, "streak", "gale", { intensity: 1.6, opacity: 1, valueScale: 1.3 }));
	cone.fx.addFade = 7;
	const sigil = keep(billboard(kit, "gale-sigil", "palm", "gale", { intensity: 1.6, valueScale: 0.86 }));
	glowWith(ctx.scene, sigil.mesh);
	const core = keep(billboard(kit, "gale-core", "disc", "gale", { intensity: 1.8, valueScale: 0.9 }));
	const streaks = keep(particles(kit, "gale-streaks", { capacity: 96, texture: "disc", color: hdr(P.mid, 2.2), dead: hdr(P.edge, 1, 0), size: [0.1, 0.16], life: [0.24, 0.34], billboard: "stretched" }));
	const groundFlash = keep(decal(kit, "gale-ground-flash", "star", "gale", { intensity: 2.2 }));
	const vortex = keep(decal(kit, "gale-vortex", "swirl", "gale", { intensity: 1.35, valueScale: 0.78 }));
	const vortex2 = keep(decal(kit, "gale-vortex-outer", "swirl", "gale", { intensity: 0.9, valueScale: 0.62, opacity: 0.8 }));
	const ringBurst = keep(decal(kit, "gale-ring-burst", "shock", "gale", { intensity: 1.2, valueScale: 0.85 }));
	const funnel = keep(meshLayer(kit, "gale-funnel", kit.funnel, "streak", "gale", { intensity: 1.5, opacity: 1, valueScale: 1.3 }));
	funnel.fx.addFade = 7;
	funnel.fx.tiling = 1;
	const debris = keep(particles(kit, "gale-debris", { capacity: 48, texture: "shards", sheet: { cols: 4, rows: 4, cell: 16, random: true }, color: hdr(P.mid, 1.5), dead: hdr(P.edge, 1, 0), size: [0.08, 0.18], life: [0.7, 0.9] }));
	debris.system.spriteCellChangeSpeed = 0;
	const dust = keep(particles(kit, "gale-dust", { capacity: 24, texture: "dust", sheet: { cols: 8, rows: 8, cell: 64 }, blend: "standard", color: new Color4(0.6, 0.72, 0.7, 0.42), dead: new Color4(0.6, 0.72, 0.7, 0), size: [0.6, 1.1], life: [0.7, 1.0] }));
	const impactBurst = keep(particles(kit, "gale-impact", { capacity: 2, texture: "impact", sheet: { cols: 4, rows: 4, cell: 16 }, color: hdr(P.mid, 2.1), size: [2.6, 2.6], life: [0.3, 0.3] }));
	for (const l of [charge, sparks, streaks, debris, dust, impactBurst] as ParticleLayer[]) l.system.start();

	// Helix trail: three generators orbit the projectile path; TrailMesh ribbons follow them.
	const trailMat = createVfxMaterial(scene, "gale-trail-mat", { map: kit.tex.streak, noise: kit.tex.noise, core: P.core, mid: P.mid, edge: P.edge, intensity: 2.4, opacity: 1, doubleSided: true });
	trailMat.fx.addFade = 7;
	trailMat.fx.valueScale = 1.35;
	const generators = [0, 1].map(i => new TransformNode(`gale-helix-${i}`, scene));
	const trails: TrailMesh[] = [];
	const trailLayer: VfxLayer = {
		name: "gale-trails",
		drawCalls: () => trails.filter(tr => tr.isEnabled()).length,
		particles: () => 0,
		dispose: () => { trails.forEach(tr => tr.dispose()); generators.forEach(g => g.dispose()); trailMat.material.dispose(); },
	};
	keep(trailLayer);
	generators.forEach((g, i) => {
		g.position.copyFrom(hand);
		const trail = new TrailMesh(`gale-trail-${i}`, g, scene, { diameter: 0.32, length: 44, segments: 44, sections: 4, autoStart: false });
		trail.material = trailMat.material;
		trail.isPickable = false;
		trail.setEnabled(false);
		trails.push(trail);
	});
	let trailsStarted = false;

	const light = ctx.lights.acquire(layers);
	let state = { charge: false, release: false, hit: false, debrisFrom: 0, streakUntil: 0, sparksDone: false };
	const pos = new Vector3();

	let chargeIndex = 0;
	charge.system.startPositionFunction = (_m, p, particle) => { p.copyFrom(hand); motion.set(particle, { a: 0, r: 0, y: 0, speed: chargeIndex++ % 2 ? -1 : 1, seed: 0, origin: hand }); };
	const baseCharge = charge.system.updateFunction;
	charge.system.updateFunction = (list) => {
		baseCharge(list);
		for (const p of list) {
			const s = motion.get(p);
			if (!s) continue;
			p.position.copyFrom(hand);
			p.angle = s.speed * p.age * 11;
			p.size = lerp(0.6, 1.9, easeOutCubic(p.age / 0.2)) * (s.speed > 0 ? 1 : 0.7);
			p.color.a = 1 - easeInQuad((p.age - 0.15) / 0.07);
		}
	};
	sparks.system.startPositionFunction = (_m, p, particle) => {
		const a = Math.random() * Math.PI * 2, e = (Math.random() - 0.3) * 1.2, r = 1.1 + Math.random() * 0.5;
		p.set(hand.x + Math.cos(e) * Math.sin(a) * r, hand.y + Math.sin(e) * r, hand.z + Math.cos(e) * Math.cos(a) * r);
		motion.set(particle, { a, r, y: e, speed: 0, seed: 0, origin: hand });
	};
	sparks.system.startDirectionFunction = (_m, dir, particle) => {
		const s = motion.get(particle);
		const p = s ? v3(Math.cos(s.y) * Math.sin(s.a) * s.r, Math.sin(s.y) * s.r, Math.cos(s.y) * Math.cos(s.a) * s.r) : Vector3.Zero();
		dir.copyFrom(p.scale(-1 / 0.18));
	};
	streaks.system.startPositionFunction = (_m, p) => p.copyFrom(pos).addInPlaceFromFloats((Math.random() - 0.5) * 0.5, (Math.random() - 0.5) * 0.5, (Math.random() - 0.5) * 0.5);
	streaks.system.startDirectionFunction = (_m, dir) => dir.copyFrom(fwd.scale(-2.5)).addInPlaceFromFloats((Math.random() - 0.5) * 0.8, (Math.random() - 0.3) * 0.8, (Math.random() - 0.5) * 0.8);
	impactBurst.system.startPositionFunction = (_m, p) => p.copyFrom(impactAt);
	dust.system.startPositionFunction = (_m, p) => p.copyFrom(state.hit ? impactGround : origin).addInPlaceFromFloats(0, 0.1, 0);
	dust.system.startDirectionFunction = (_m, dir) => { const a = Math.random() * Math.PI * 2; dir.set(Math.sin(a) * 1.6, 0.25, Math.cos(a) * 1.6); };
	debris.system.startPositionFunction = (_m, p, particle) => {
		const a = Math.random() * Math.PI * 2, r = 0.4 + Math.random() * 1.6;
		motion.set(particle, { a, r, y: 0.1, speed: 3 + Math.random() * 3, seed: Math.random(), origin: impactGround });
		p.set(impactGround.x + Math.sin(a) * r, impactGround.y + 0.1, impactGround.z + Math.cos(a) * r);
	};
	const baseDebris = debris.system.updateFunction;
	debris.system.updateFunction = (list) => {
		baseDebris(list);
		for (const p of list) {
			const s = motion.get(p);
			if (!s) continue;
			const u = p.age / p.lifeTime;
			const a = s.a + s.speed * p.age;
			const r = s.r * (1 - 0.55 * u);
			p.position.set(s.origin.x + Math.sin(a) * r, s.origin.y + 0.1 + easeOutQuad(u) * (1.6 + s.seed * 1.2), s.origin.z + Math.cos(a) * r);
		}
	};

	return {
		id: "xs_gale_palm", duration: HIT + 1.6,
		contract: `projectile 16 m/s · cast 0.2s · hit 1×${HIT.toFixed(2)}s · AoE r 2.2 m`,
		layers: () => layers,
		update(t) {
			// L1 charge swirl + converging sparks.
			if (!state.charge) { charge.system.manualEmitCount = 2; state.charge = true; }
			if (t < RELEASE && !state.sparksDone) { sparks.system.manualEmitCount = 12; state.sparksDone = true; }
			// L2 release cone + dust ring under the caster.
			cone.mesh.setEnabled(t >= RELEASE && t < RELEASE + 0.14);
			const c = clamp01((t - RELEASE) / 0.12);
			cone.mesh.position.copyFrom(hand);
			cone.mesh.rotation.y = facing;
			cone.mesh.scaling.setAll(lerp(0.3, 1.5, easeOutCubic(c)));
			cone.fx.opacity = 0.85 * (1 - easeInQuad(c));
			cone.fx.scrollV = -t * 6;
			if (t >= RELEASE && !state.release) { state.release = true; dust.system.manualEmitCount = 8; }
			// L3-L5 projectile: sigil, core glow, helix trails, shed streaks.
			const flight = clamp01((t - RELEASE) / (HIT - RELEASE));
			const flying = t >= RELEASE && t < HIT;
			pos.copyFrom(hand).addInPlace(fwd.scale(travel * flight));
			sigil.mesh.setEnabled(flying || (t >= HIT && t < HIT + 0.06));
			core.mesh.setEnabled(t < RELEASE + 0.05);
			sigil.mesh.position.copyFrom(pos);
			core.mesh.position.copyFrom(t < RELEASE ? hand : pos);
			const grow = easeOutBack(clamp01((t - RELEASE) / 0.1));
			sigil.mesh.scaling.setAll(2.9 * grow * (t >= HIT ? 1 + (t - HIT) * 4 : 1));
			sigil.fx.rotation = Math.sin(t * Math.PI * 2 * 9) * 0.1;
			sigil.fx.opacity = t >= HIT ? 0.6 * (1 - (t - HIT) / 0.06) : 1;
			core.mesh.scaling.setAll((t < RELEASE ? lerp(0.3, 1.2, easeOutCubic(t / RELEASE)) : 1.7) + 0.15 * Math.sin(t * 50));
			generators.forEach((g, i) => {
				const turns = (travel * flight) * 2 * Math.PI * 2 + i * Math.PI;
				const r = 0.35 * (0.6 + 0.4 * Math.min(1, flight * 4));
				g.position.copyFrom(pos).addInPlace(right.scale(Math.cos(turns) * r)).addInPlaceFromFloats(0, Math.sin(turns) * r, 0);
			});
			if (flying && !trailsStarted) {
				trailsStarted = true;
				for (const trail of trails) { trail.reset(); trail.start(); }
			}
			trailMat.fx.opacity = 0.9 * (t < HIT ? 1 : 1 - clamp01((t - HIT) / 0.25));
			trailMat.fx.scrollV = t * 3;
			for (const trail of trails) trail.setEnabled(trailsStarted && t < HIT + 0.25);
			if (flying && t >= state.streakUntil) { state.streakUntil = t + 1 / 60; streaks.system.manualEmitCount += 1; }
			// L6-L9 impact: flash, vortex decal, wind funnel, lifted debris.
			if (t >= HIT && !state.hit) {
				state.hit = true;
				impactBurst.system.manualEmitCount = 1;
				debris.system.manualEmitCount = 24;
				dust.system.manualEmitCount = 8;
				ctx.shake(0.06, 0.12);
			}
			const h = t - HIT;
			groundFlash.mesh.setEnabled(h >= 0 && h < 0.2);
			groundFlash.mesh.position.set(impactGround.x, impactGround.y + 0.05, impactGround.z);
			groundFlash.mesh.scaling.setAll(lerp(1, 3.2, easeOutCubic(h / 0.2)));
			groundFlash.fx.opacity = 1 - easeInQuad(h / 0.2);
			vortex.mesh.setEnabled(h >= 0 && h < 1.45);
			vortex.mesh.position.set(impactGround.x, impactGround.y + 0.04, impactGround.z);
			vortex.mesh.scaling.setAll(Math.max(0.01, 5.2 * easeOutBack(h / 0.25, 1.4)));
			vortex.mesh.rotation.y = -(2.4 * h - 0.9 * h * h * 0.5);
			vortex.fx.opacity = 1 - easeInQuad((h - 0.6) / 0.8);
			vortex2.mesh.setEnabled(h >= 0.03 && h < 1.5);
			vortex2.mesh.position.set(impactGround.x, impactGround.y + 0.035, impactGround.z);
			vortex2.mesh.scaling.setAll(Math.max(0.01, 7.4 * easeOutBack((h - 0.03) / 0.32, 1.2)));
			vortex2.mesh.rotation.y = 0.7 + 1.6 * h;
			vortex2.fx.opacity = 0.8 * (1 - easeInQuad((h - 0.5) / 1.0));
			ringBurst.mesh.setEnabled(h >= 0 && h < 0.4);
			ringBurst.mesh.position.set(impactGround.x, impactGround.y + 0.05, impactGround.z);
			ringBurst.mesh.scaling.setAll((lerp(0.4, 3.0, easeOutCubic(h / 0.4)) / 0.93) * 2);
			ringBurst.fx.opacity = 1 - easeInQuad(h / 0.4);
			funnel.mesh.setEnabled(h >= 0 && h < 0.82);
			funnel.mesh.position.set(impactGround.x, impactGround.y + 2.6, impactGround.z);
			const fz = clamp01(h / 0.8);
			funnel.mesh.scaling.set(lerp(0.8, 2.0, easeOutCubic(fz)), 2.8, lerp(0.8, 2.0, easeOutCubic(fz)));
			funnel.mesh.rotation.y = -h * 9;
			funnel.fx.scrollV = -h * 3.5;
			funnel.fx.opacity = (1 - easeInQuad(fz)) * clamp01(h / 0.05);
			// L10 light: charge, travel, impact flash.
			const at = t < HIT ? (t < RELEASE ? hand : pos) : impactAt;
			lightUp(light, at, "#7DFFD9", 2 * envelope(t, 0, RELEASE, HIT, HIT + 0.01) + 5 * envelope(h, 0, 0.03, 0.06, 0.3), 7);
			// L11 hit reaction: knockback 1.5 m over 180 ms.
			if (target) {
				const k = h >= 0 ? easeOutCubic(h / 0.18) : 0;
				hitReact(target, "#5FF2C8", h >= 0 ? 0.55 * (1 - clamp01(h / 0.15)) : 0, fwd.scale(1.5 * k).addInPlaceFromFloats(0, Math.sin(Math.PI * clamp01(h / 0.3)) * 0.3, 0));
			}
		},
		dispose() {
			ctx.lights.release(light);
			if (target) hitReact(target, "#000000", 0, Vector3.ZeroReadOnly as Vector3);
			for (const layer of layers) layer.dispose();
		},
	};
};

// =================================================================================================
// 3.3 xs_void_rift — ground AoE r 4.5 m, cast 0.6 s, 6 ticks every 0.35 s from 0.9 s, pull 1.2 m/s
// =================================================================================================

export const voidRift: SkillFactory = (ctx, origin, facing) => {
	const { kit } = ctx;
	const P = PALETTE.void;
	const R = PALETTE.rim;
	const RADIUS = 4.5;
	const layers: VfxLayer[] = [];
	const keep = <T extends VfxLayer>(layer: T) => { layers.push(layer); return layer; };
	const centre = origin.add(forwardOf(facing).scale(8));
	const ground = (y = 0) => v3(centre.x, centre.y + y, centre.z);
	const TICKS = Array.from({ length: 6 }, (_, i) => 0.9 + i * 0.35);

	const outer = keep(decal(kit, "rift-outer", "runeOuter", "void", { intensity: 0.88, opacity: 1, valueScale: 0.78, midAt: 0.72 }));
	glowWith(ctx.scene, outer.mesh);
	outer.mesh.position.copyFrom(ground(0.03));
	outer.mesh.scaling.setAll((RADIUS / 0.955) * 2);
	const inner = keep(decal(kit, "rift-inner", "runeInner", "void", { intensity: 0.95, opacity: 0.9, valueScale: 0.78, midAt: 0.7 }));
	inner.mesh.position.copyFrom(ground(0.035));
	inner.mesh.scaling.setAll((3.0 / 0.93) * 2);
	const bed = keep(decal(kit, "rift-energy-bed", "disc", "void", { blend: "blend", intensity: 1, opacity: 0.94 }));
	bed.fx.setPalette("#4A1A9E", "#2A0D66", "#140533", 0.5);
	bed.mesh.position.copyFrom(ground(0.038));
	const abyss = keep(decal(kit, "rift-abyss", "disc", "void", { blend: "blend", intensity: 1, opacity: 0.9 }));
	abyss.fx.setPalette(P.dark, P.dark, P.dark);
	abyss.mesh.position.copyFrom(ground(0.04));
	const swirl = keep(decal(kit, "rift-swirl", "swirl", "void", { intensity: 1.1, valueScale: 0.62, midAt: 0.76 }));
	swirl.mesh.position.copyFrom(ground(0.045));
	const swirl2 = keep(decal(kit, "rift-swirl-outer", "swirl", "void", { intensity: 1.0, valueScale: 0.6, midAt: 0.72, opacity: 0.9 }));
	swirl2.mesh.position.copyFrom(ground(0.042));
	const rim = keep(decal(kit, "rift-rim", "shock", "rim", { intensity: 0.85, valueScale: 0.8 }));
	rim.mesh.position.copyFrom(ground(0.05));
	const curtain = keep(meshLayer(kit, "rift-curtain", kit.ringWall, "streak", "void", { intensity: 1.1, opacity: 1, valueScale: 1.25 }));
	curtain.fx.addFade = 6;
	curtain.mesh.position.copyFrom(ground(0));
	curtain.fx.tiling = 1;
	const implosion = keep(decal(kit, "rift-implosion", "star", "void", { intensity: 1.4, valueScale: 0.85 }));
	implosion.mesh.position.copyFrom(ground(0.06));
	const burstRing = keep(decal(kit, "rift-burst-ring", "shock", "void", { intensity: 1.2, valueScale: 0.85 }));
	burstRing.mesh.position.copyFrom(ground(0.05));
	const scorch = keep(decal(kit, "rift-scorch", "scorch", "void", { blend: "blend", intensity: 1.8 }));
	scorch.fx.setPalette(P.core, P.mid, P.dark, 0.5);
	scorch.mesh.position.copyFrom(ground(0.025));
	scorch.mesh.scaling.setAll(7);
	const arcs = keep(beams(kit, "rift-arcs", "void", 10, { intensity: 2.3 }));
	const motes = keep(particles(kit, "rift-motes", { capacity: 96, texture: "disc", color: hdr(P.mid, 2.6), color2: hdr(P.core, 2.2), dead: hdr(P.edge, 1.4, 0), size: [0.16, 0.28], life: [0.9, 1.3] }));
	const rimMotes = keep(particles(kit, "rift-rim-motes", { capacity: 32, texture: "disc", color: hdr(R.mid, 1.6), dead: hdr(R.edge, 1, 0), size: [0.06, 0.12], life: [0.5, 0.8], gravity: v3(0, 1.2, 0) }));
	const impacts = keep(particles(kit, "rift-impacts", { capacity: 12, texture: "impact", sheet: { cols: 4, rows: 4, cell: 16 }, color: hdr(P.core, 2.2), size: [1.4, 1.6], life: [0.26, 0.26] }));
	const debris = keep(particles(kit, "rift-debris", { capacity: 32, texture: "shards", sheet: { cols: 4, rows: 4, cell: 16, random: true }, color: hdr(P.mid, 1.6), dead: hdr(P.edge, 1, 0), size: [0.1, 0.24], life: [0.5, 0.8], gravity: v3(0, -9, 0) }));
	debris.system.spriteCellChangeSpeed = 0;
	for (const l of [motes, rimMotes, impacts, debris] as ParticleLayer[]) l.system.start();

	motes.system.startPositionFunction = (_m, p, particle) => {
		const a = Math.random() * Math.PI * 2;
		motion.set(particle, { a, r: RADIUS * (0.85 + Math.random() * 0.15), y: 0.2 + Math.random() * 0.6, speed: 1.4 + Math.random() * 0.8, seed: Math.random(), origin: centre });
		p.set(centre.x + Math.sin(a) * RADIUS, centre.y + 0.3, centre.z + Math.cos(a) * RADIUS);
	};
	const baseMotes = motes.system.updateFunction;
	motes.system.updateFunction = (list) => {
		baseMotes(list);
		for (const p of list) {
			const s = motion.get(p);
			if (!s) continue;
			const u = easeInQuad(p.age / p.lifeTime);
			const a = s.a - s.speed * p.age * (1 + u * 2.5);
			const r = s.r * (1 - u);
			p.position.set(centre.x + Math.sin(a) * r, centre.y + lerp(s.y, -0.25, u), centre.z + Math.cos(a) * r);
		}
	};
	rimMotes.system.startPositionFunction = (_m, p) => { const a = Math.random() * Math.PI * 2; p.set(centre.x + Math.sin(a) * RADIUS, centre.y + 0.05, centre.z + Math.cos(a) * RADIUS); };
	let impactQueue: Vector3[] = [];
	impacts.system.startPositionFunction = (_m, p) => p.copyFrom(impactQueue.shift() ?? ground(0.8));
	debris.system.startPositionFunction = (_m, p) => p.copyFrom(ground(0.2));
	debris.system.startDirectionFunction = (_m, dir) => { const a = Math.random() * Math.PI * 2; const s = 3 + Math.random() * 4; dir.set(Math.sin(a) * s, 3 + Math.random() * 4, Math.cos(a) * s); };

	const light = ctx.lights.acquire(layers);
	const fired = new Set<number>();
	let moteClock = 0, rimClock = 0, burst = false;
	const arcState = Array.from({ length: 10 }, () => ({ born: -1, life: 0, a: 0, cell: 0 }));
	const eyeTmp = new Vector3();

	return {
		id: "xs_void_rift", duration: 4.6,
		contract: "ground AoE r 4.5 m · pull · cast 0.6s · hits 6×0.35s",
		layers: () => layers,
		update(t) {
			const live = envelope(t, 0, 0.45, 3.0, 3.4);
			// L1/L2 rune circles: draw in, counter-rotate, fade with the collapse.
			outer.mesh.setEnabled(t < 3.4);
			outer.fx.wipe = easeOutQuad(t / 0.45);
			outer.fx.opacity = 0.8 * (t < 0.45 ? 1 : live);
			outer.mesh.rotation.y = (10 * Math.PI / 180) * t;
			inner.mesh.setEnabled(t >= 0.15 && t < 3.4);
			inner.fx.opacity = 0.7 * envelope(t, 0.15, 0.45, 3.0, 3.4);
			inner.mesh.rotation.y = -(20 * Math.PI / 180) * t;
			// L4 abyss + swirl: opens 0.6-0.9 s with overshoot, spins up, contracts 2.7-3.05 s.
			const open = easeOutBack((t - 0.6) / 0.3, 1.3);
			const collapse = 1 - easeInCubic((t - 2.7) / 0.35);
			const size = Math.max(0.01, open * collapse);
			const spin = 1.2 * (t - 0.6) + 0.4 * Math.max(0, t - 0.6) ** 2 * 0.5;
			for (const layer of [bed, abyss, swirl, swirl2]) layer.mesh.setEnabled(t >= 0.6 && t < 3.05);
			swirl2.mesh.scaling.setAll(8.2 * size);
			swirl2.mesh.rotation.y = 0.9 - spin * 0.55;
			bed.mesh.scaling.setAll(9.6 * size);
			abyss.mesh.scaling.setAll(2.6 * size);
			swirl.mesh.scaling.setAll(7.4 * size);
			swirl.mesh.rotation.y = -spin;
			swirl.fx.intensity = 1.1 * (1 + 0.4 * TICKS.reduce((acc, at) => acc + envelope(t, at, at + 0.03, at + 0.05, at + 0.2), 0));
			// L6 rim + curtain with tick pulses.
			const pulse = TICKS.reduce((acc, at) => acc + envelope(t, at, at + 0.03, at + 0.06, at + 0.12), 0);
			rim.mesh.setEnabled(t >= 0.6 && t < 3.1);
			rim.mesh.scaling.setAll((3.55 / 0.93) * 2 * (1 + 0.03 * pulse) * Math.max(0.01, easeOutCubic((t - 0.6) / 0.25)) * (t > 2.9 ? collapse * 0.3 + 0.7 : 1));
			rim.fx.intensity = 0.85 * (1 + 1.6 * pulse);
			rim.fx.opacity = 0.9 * envelope(t, 0.6, 0.75, 2.8, 3.1);
			curtain.mesh.setEnabled(t >= 0.65 && t < 3.05);
			curtain.mesh.scaling.set(3.55, lerp(0.4, 1.5, easeOutCubic((t - 0.65) / 0.4)) * (1 + 0.25 * pulse), 3.55);
			curtain.fx.opacity = 0.75 * envelope(t, 0.65, 0.9, 2.7, 3.05) * (1 + 0.5 * pulse);
			curtain.fx.scrollV = -t * 1.6;
			curtain.mesh.rotation.y = -t * 0.4;
			// L3 telegraph crackle along the ring, then L10 radial burst after the implosion.
			ctx.eye().subtractToRef(Vector3.ZeroReadOnly, eyeTmp);
			arcState.forEach((arc, k) => {
				const crackle = t >= 0.1 && t < 0.6 && k < 3;
				const radial = t >= 3.05 && t < 3.4;
				const sustain = t >= 1.0 && t < 2.7 && k < 2;
				if (!crackle && !radial && !sustain) { arcs.hide(k); return; }
				if (arc.born < 0 || t - arc.born > arc.life) {
					const seed = Math.floor(t * 60) * 5 + k * 17;
					arc.born = t; arc.life = 0.07 + hash01(seed) * 0.05; arc.a = hash01(seed + 3) * Math.PI * 2; arc.cell = Math.floor(hash01(seed + 5) * 16);
				}
				let a: Vector3, b: Vector3;
				if (radial) {
					const ang = (k / 10) * Math.PI * 2 + hash01(k) * 0.4;
					const reach = lerp(1.5, 6, easeOutCubic((t - 3.05) / 0.3));
					a = ground(0.3);
					b = v3(centre.x + Math.sin(ang) * reach, centre.y + 0.15, centre.z + Math.cos(ang) * reach);
				} else if (sustain) {
					a = v3(centre.x + Math.sin(arc.a) * RADIUS * 0.95, centre.y + 0.25, centre.z + Math.cos(arc.a) * RADIUS * 0.95);
					b = ground(0.1);
				} else {
					const span = 0.55;
					a = v3(centre.x + Math.sin(arc.a) * RADIUS, centre.y + 0.12, centre.z + Math.cos(arc.a) * RADIUS);
					b = v3(centre.x + Math.sin(arc.a + span) * RADIUS, centre.y + 0.12, centre.z + Math.cos(arc.a + span) * RADIUS);
				}
				arcs.set(k, a, b, radial ? 0.7 : 0.45, arc.cell, 1 - (t - arc.born) / arc.life * 0.6);
			});
			arcs.commit(eyeTmp);
			// L7 pull motes and rising rim motes.
			if (t >= 0.75 && t < 2.7 && t >= moteClock) { moteClock = t + 1 / 45; motes.system.manualEmitCount += 1; }
			if (t >= 0.1 && t < 0.6 && t >= rimClock) { rimClock = t + 1 / 40; rimMotes.system.manualEmitCount += 1; }
			// L8 ticks: inward shock ring, impact bursts, purple flash, pull.
			let tickAge = -1;
			TICKS.forEach((at, i) => {
				if (t >= at && t < at + 0.2) tickAge = t - at;
				if (t >= at && !fired.has(i)) {
					fired.add(i);
					ctx.shake(0.04, 0.08);
					impactQueue = ctx.targets.filter(tg => Vector3.Distance(tg.root.position, centre) <= RADIUS + 0.3).map(tg => tg.root.position.add(v3(0, 0.8, 0)));
					impacts.system.manualEmitCount += impactQueue.length;
				}
			});
			void tickAge;
			// L9 collapse flash and L10 outward burst ring + debris.
			const ic = t - 3.05;
			implosion.mesh.setEnabled(ic >= 0 && ic < 0.25);
			implosion.mesh.scaling.setAll(lerp(5, 1.2, easeOutCubic(ic / 0.08)) + lerp(0, 3.5, easeOutCubic((ic - 0.08) / 0.17)));
			implosion.fx.opacity = 1 - easeInQuad(ic / 0.25);
			burstRing.mesh.setEnabled(ic >= 0 && ic < 0.35);
			burstRing.mesh.scaling.setAll((lerp(0.3, 5, easeOutCubic(ic / 0.35)) / 0.93) * 2);
			burstRing.fx.opacity = 1 - easeInQuad(ic / 0.35);
			if (ic >= 0 && !burst) { burst = true; debris.system.manualEmitCount = 24; ctx.shake(0.09, 0.16); }
			// L11 scorch.
			scorch.mesh.setEnabled(ic >= 0 && t < 4.6);
			scorch.fx.opacity = envelope(t, 3.05, 3.15, 3.8, 4.6);
			scorch.fx.heat = 1 - clamp01(ic / 1.2);
			scorch.fx.intensity = 1.8 * (0.3 + 0.7 * (1 - clamp01(ic / 1.2)));
			// L12 light.
			lightUp(light, ground(1.2), "#B07CFF", 4 * envelope(t, 0.6, 0.85, 2.7, 3.0) + 2 * pulse + 8 * envelope(ic, 0, 0.02, 0.05, 0.35), 10);
			// Pull targets in and flash them on ticks.
			for (const target of ctx.targets) {
				const d = Vector3.Distance(target.home, centre);
				if (d > RADIUS + 0.3) continue;
				const pulled = Math.min(d - 0.8, 1.2 * clamp01((t - 0.9) / 1.8) * 1.8);
				const dir = centre.subtract(target.home).normalize();
				const flashAmount = TICKS.reduce((acc, at) => acc + (1 - clamp01((t - at) / 0.12)) * (t >= at ? 1 : 0), 0);
				hitReact(target, "#B07CFF", 0.35 * Math.min(1, flashAmount), dir.scale(Math.max(0, pulled) * (t < 3.05 ? 1 : 1)));
			}
		},
		dispose() {
			ctx.lights.release(light);
			for (const target of ctx.targets) hitReact(target, "#000000", 0, Vector3.ZeroReadOnly as Vector3);
			for (const layer of layers) layer.dispose();
		},
	};
};

export const SKILLS: Record<string, SkillFactory> = {
	xs_bladeward_nova: bladewardNova,
	xs_gale_palm: galePalm,
	xs_void_rift: voidRift,
};

export type { Mesh };
