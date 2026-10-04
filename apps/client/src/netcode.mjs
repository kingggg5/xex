/**
 * Client-side motion authority helpers (V5-04, plan §10.1).
 *
 * Pure logic, no DOM or renderer: the browser game loop and the node
 * measurement bot share this module. Fixed 50 ms steps mirror the server
 * tick; snapshots acknowledge the last applied input (`ack_seq`) and the
 * client replays unacknowledged inputs on top of the server position.
 *
 * Reconciliation correction is the distance from the old predicted position
 * to the replayed position. The sequence-anchor error and raw lag gap are
 * separate diagnostics; neither alone is the visual correction being applied.
 */
import { moveCapsule } from "./coordinate-collision.mjs";
import { moveGroundedCapsule, sampleCityHeight } from './grounded-city.mjs';

export const STEP_MS = 50;
export const STEP_DT = 0.05;
export const RING_SIZE = 64;
/** Blend bands (plan §10.1): <0.25 m over 100 ms, 0.25–1 m over 200 ms, else snap. */
export const BLEND_NEAR_M = 0.25;
export const BLEND_FAR_M = 1.0;
export const BLEND_NEAR_MS = 100;
export const BLEND_FAR_MS = 200;
/** Remote interpolation delay: starts 100 ms, adapts to 2 ticks + p95 jitter, clamped 75–200 ms. */
export const INTERP_START_MS = 100;
export const INTERP_MIN_MS = 75;
export const INTERP_MAX_MS = 200;
/** Remote extrapolation stops after 100 ms; the entity holds. */
export const EXTRAPOLATE_MAX_MS = 100;
const MAX_CLOCK_CORRECTION_TICKS = 0.1;

export function distance(ax, az, bx, bz) {
	return Math.hypot(ax - bx, az - bz);
}

/** Monotonic estimate of server simulation time at the local render clock. */
export class ServerTickClock {
	constructor() {
		this.reset(0, 0);
	}

	reset(serverTick, nowMs) {
		this.tick = Number.isFinite(serverTick) ? serverTick : 0;
		this.atMs = Number.isFinite(nowMs) ? nowMs : 0;
	}

	estimate(nowMs) {
		if (!Number.isFinite(nowMs)) return this.tick;
		return this.tick + Math.max(0, nowMs - this.atMs) / STEP_MS;
	}

	observe(serverTick, receivedAtMs) {
		if (!Number.isFinite(serverTick) || !Number.isFinite(receivedAtMs)) return this.estimate(receivedAtMs);
		const projected = this.estimate(receivedAtMs);
		const diff = serverTick - projected;
		let correction = 0;
		if (diff > 0) {
			correction = Math.min(MAX_CLOCK_CORRECTION_TICKS, diff);
		} else if (diff < 0) {
			// Slew backwards slowly (max 0.02 ticks per snapshot)
			correction = Math.max(-0.02, diff);
		}
		this.tick = projected + correction;
		this.atMs = receivedAtMs;
		return this.tick;
	}
}

/** Align fixed client input steps with server ticks and cap catch-up after stalls. */
export class InputTickScheduler {
	constructor() {
		this.reset(0);
	}

	reset(serverTick, uplinkMs = 0) {
		const estimate = Number.isFinite(serverTick) ? serverTick : 0;
		this.leadTicks = Math.max(0, Number.isFinite(uplinkMs) ? uplinkMs : 0) / STEP_MS;
		this.nextTick = Math.floor(estimate + this.leadTicks) + 1;
		this.skippedTicks = 0;
	}

	takeDue(serverTick, uplinkMs = 0, maxCatchUp = 4) {
		if (!Number.isFinite(serverTick) || !Number.isInteger(maxCatchUp) || maxCatchUp < 1) return [];
		const targetLead = Math.max(0, Number.isFinite(uplinkMs) ? uplinkMs : 0) / STEP_MS;
		if (targetLead > this.leadTicks) {
			this.leadTicks = Math.min(targetLead, this.leadTicks + 1);
		} else if (targetLead < this.leadTicks) {
			this.leadTicks = Math.max(targetLead, this.leadTicks - 1);
		}
		const targetTick = Math.floor(serverTick + this.leadTicks) + 1;
		if (this.nextTick > targetTick + 1) {
			this.nextTick = targetTick + 1;
		}
		let count = targetTick - this.nextTick + 1;
		if (count <= 0) return [];
		if (count > maxCatchUp) {
			const skipped = count - maxCatchUp;
			this.nextTick += skipped;
			this.skippedTicks += skipped;
			count = maxCatchUp;
		}
		const due = Array.from({ length: count }, (_, index) => this.nextTick + index);
		this.nextTick += count;
		return due;
	}
}

/** @returns {"blend100" | "blend200" | "snap"} */
export function classifyCorrection(meters) {
	if (meters < BLEND_NEAR_M) return "blend100";
	if (meters < BLEND_FAR_M) return "blend200";
	return "snap";
}

export class Predictor {
	/** @param {{radius: number, height: number, boxes: Array, limit: number, speed: number, cityTraversal?: import('./grounded-city').CityTraversalField|null}} physics */
	constructor(physics) {
		this.physics = physics;
		this.x = 0;
		this.z = 0;
		this.y = 0;
		this.prevX = 0;
		this.prevZ = 0;
		this.facing = 0;
		/** seq -> {x, z, facing} position AFTER that step; doubles as replay log. */
		this.ring = new Map();
		/** seq -> {x, z, facing, mult} input used by the step, for replay. */
		this.inputs = new Map();
		this.order = [];
		this.evictedThrough = 0;
	}

	reset(x, z, facing) {
		this.x = x;
		this.z = z;
		this.y = sampleCityHeight(this.physics.cityTraversal, x, z) ?? 0;
		this.prevX = x;
		this.prevZ = z;
		this.facing = facing;
		this.ring.clear();
		// ack_seq is zero until the server applies the first movement input.
		// Keep the Welcome position as the sequence-zero prediction anchor.
		this.ring.set(0, { x, z, facing });
		this.inputs.clear();
		this.order = [];
		this.evictedThrough = 0;
	}

	/** Advance one fixed step. @returns {{x: number, z: number}} */
	step(seq, x, z, facing, speedMult = 1) {
		this.prevX = this.x;
		this.prevZ = this.z;
		const mover = this.physics.cityTraversal ? moveGroundedCapsule : moveCapsule;
		const moved = mover(
			{ x: this.x, y: this.y, z: this.z },
			{ x: x * this.physics.speed * speedMult * STEP_DT, z: z * this.physics.speed * speedMult * STEP_DT },
			this.physics.radius,
			this.physics.height,
			this.physics.boxes,
			this.physics.limit,
			this.physics.cityTraversal,
		);
		this.x = moved.x;
		this.z = moved.z;
		this.y = 'y' in moved ? moved.y : 0;
		this.facing = facing;
		this.ring.set(seq, { x: this.x, z: this.z, facing });
		this.inputs.set(seq, { x, z, facing, mult: speedMult });
		this.order.push(seq);
		while (this.order.length > RING_SIZE) {
			const old = this.order.shift();
			this.evictedThrough = Math.max(this.evictedThrough, old);
			this.ring.delete(old);
			this.inputs.delete(old);
		}
		return { x: this.x, z: this.z };
	}

	/** Sub-step visual render position between previous and current predicted steps. */
	renderPosition(fraction = 1.0) {
		const f = Math.max(0, Math.min(1, fraction));
		return {
			x: this.prevX + (this.x - this.prevX) * f,
			z: this.prevZ + (this.z - this.prevZ) * f,
		};
	}

	/** Undo dodge boost on inputs newer than rejectedSeq and recompute. */
	cancelDodgeBoost(rejectedSeq) {
		let modified = false;
		for (const [seq, input] of this.inputs) {
			if (seq > rejectedSeq && input.mult > 1) {
				input.mult = 1;
				modified = true;
			}
		}
		if (modified) {
			const oldestSeq = this.order.length > 0 ? this.order[0] : 0;
			const anchorSeq = oldestSeq > 0 ? oldestSeq - 1 : 0;
			const anchor = this.ring.get(anchorSeq);
			if (anchor) {
				this.reconcile(anchor, anchorSeq);
			}
		}
	}

	dropAcked(ackSeq) {
		while (this.order.length > 0 && this.order[0] <= ackSeq) {
			const old = this.order.shift();
			this.ring.delete(old);
			this.inputs.delete(old);
		}
	}

	/**
	 * Reconcile with a server snapshot.
	 * @param {{x: number, z: number}} ackPosition server position after ackSeq
	 * @param {number} ackSeq last input sequence the server applied
	 * @param {{x: number, z: number}} [serverPos] current server position, diagnostic only
	 * @returns {{error: number, ackError: number|null, lagGap: number, band: string, known: boolean}}
	 * error = post-replay position correction (gated metric); ackError =
	 * position error at the acknowledged input when that local sample remains;
	 * lagGap = raw
	 * predicted-vs-server distance (diagnostic only); known = false when the
	 * ring evicted unacknowledged input history (replay incomplete → snap).
	 */
	reconcile(ackPosition, ackSeq, serverPos = ackPosition) {
		const predicted = { x: this.x, z: this.z };
		const lagGap = distance(predicted.x, predicted.z, serverPos.x, serverPos.z);
		const anchor = this.ring.get(ackSeq);
		const known = ackSeq >= this.evictedThrough;
		const ackError = anchor ? distance(anchor.x, anchor.z, ackPosition.x, ackPosition.z) : null;
		// Reset to the server's ack anchor, then replay newer inputs.
		this.x = ackPosition.x;
		this.z = ackPosition.z;
		this.y = sampleCityHeight(this.physics.cityTraversal, this.x, this.z) ?? this.y;
		this.prevX = ackPosition.x;
		this.prevZ = ackPosition.z;
		const replay = this.order.filter((seq) => seq > ackSeq);
		for (const seq of replay) {
			const input = this.inputs.get(seq);
			if (!input) continue;
			this.prevX = this.x;
			this.prevZ = this.z;
			const mover = this.physics.cityTraversal ? moveGroundedCapsule : moveCapsule;
			const moved = mover(
				{ x: this.x, y: this.y, z: this.z },
				{ x: input.x * this.physics.speed * input.mult * STEP_DT, z: input.z * this.physics.speed * input.mult * STEP_DT },
				this.physics.radius,
				this.physics.height,
				this.physics.boxes,
				this.physics.limit,
				this.physics.cityTraversal,
			);
			this.x = moved.x;
			this.z = moved.z;
			this.y = 'y' in moved ? moved.y : 0;
			this.facing = input.facing;
			this.ring.set(seq, { x: this.x, z: this.z, facing: this.facing });
		}
		this.dropAcked(ackSeq);
		const error = distance(predicted.x, predicted.z, this.x, this.z);
		return { error, ackError, lagGap, band: known ? classifyCorrection(error) : "snap", known };
	}
}

export class RemoteView {
	constructor() {
		/** id -> Array<{tick: number, x: number, z: number}> ordered by tick. */
		this.tracks = new Map();
		this.delayMs = INTERP_START_MS;
		this.jitterP95Ms = 0;
		this.arrivalJitters = [];
		this.lastArrival = null;
	}

	clear() {
		this.tracks.clear();
		this.delayMs = INTERP_START_MS;
		this.jitterP95Ms = 0;
		this.arrivalJitters = [];
		this.lastArrival = null;
	}

	/** Estimate transport jitter from snapshot inter-arrival time minus server tick time. */
	observeSnapshot(tick, receivedAtMs) {
		if (!Number.isFinite(tick) || !Number.isFinite(receivedAtMs)) return;
		if (this.lastArrival && tick > this.lastArrival.tick && receivedAtMs >= this.lastArrival.at) {
			const expectedMs = (tick - this.lastArrival.tick) * STEP_MS;
			const actualMs = receivedAtMs - this.lastArrival.at;
			this.arrivalJitters.push(Math.abs(actualMs - expectedMs));
			if (this.arrivalJitters.length > 50) this.arrivalJitters.shift();
			const sorted = [...this.arrivalJitters].sort((a, b) => a - b);
			this.jitterP95Ms = percentile(sorted, 0.95);
			this.delayMs = Math.min(INTERP_MAX_MS, Math.max(INTERP_MIN_MS, 2 * STEP_MS + this.jitterP95Ms));
		}
		if (!this.lastArrival || tick > this.lastArrival.tick) {
			this.lastArrival = { tick, at: receivedAtMs };
		}
	}

	push(id, tick, x, z) {
		let track = this.tracks.get(id);
		if (!track) {
			track = [];
			this.tracks.set(id, track);
		}
		const last = track[track.length - 1];
		if (last && tick <= last.tick) return;
		track.push({ tick, x, z });
		while (track.length > 12) track.shift();
	}

	prune(presentIds) {
		for (const id of [...this.tracks.keys()]) {
			if (!presentIds.has(id)) this.tracks.delete(id);
		}
	}

	/**
	 * Render position for a remote entity.
	 * @returns {{x: number, z: number, held: boolean} | null}
	 */
	sample(id, latestTick) {
		const track = this.tracks.get(id);
		if (!track || track.length === 0) return null;
		const targetTick = latestTick - this.delayMs / STEP_MS;
		// A newly seen entity has no history before its first snapshot. Keep it
		// hidden until the delayed render target enters the buffered timeline.
		if (targetTick < track[0].tick) return null;
		if (targetTick === track[0].tick) return { x: track[0].x, z: track[0].z, held: true };
		for (let i = track.length - 1; i >= 1; i--) {
			const b = track[i];
			const a = track[i - 1];
			if (a.tick <= targetTick && targetTick <= b.tick) {
				const span = Math.max(1e-6, b.tick - a.tick);
				const t = (targetTick - a.tick) / span;
				return { x: a.x + (b.x - a.x) * t, z: a.z + (b.z - a.z) * t, held: false };
			}
		}
		// Target is newer than the newest sample: extrapolate briefly, then hold at the limit.
		const newest = track[track.length - 1];
		const aheadTicks = targetTick - newest.tick;
		const aheadMs = aheadTicks * STEP_MS;
		if (track.length < 2) {
			return { x: newest.x, z: newest.z, held: true };
		}
		const prev = track[track.length - 2];
		const span = Math.max(1e-6, newest.tick - prev.tick);
		const vx = (newest.x - prev.x) / span;
		const vz = (newest.z - prev.z) / span;
		const maxAheadTicks = EXTRAPOLATE_MAX_MS / STEP_MS;
		if (aheadMs > EXTRAPOLATE_MAX_MS) {
			return { x: newest.x + vx * maxAheadTicks, z: newest.z + vz * maxAheadTicks, held: true };
		}
		return { x: newest.x + vx * aheadTicks, z: newest.z + vz * aheadTicks, held: false };
	}
}

/** Smooth small reconciliation offsets without delaying normal predicted motion. */
export class CorrectionSmoother {
	constructor() {
		this.reset();
	}

	reset() {
		this.offsetX = 0;
		this.offsetZ = 0;
		this.startedAt = 0;
		this.durationMs = 0;
	}

	/** @returns {{x: number, z: number}} */
	sample(x, z, nowMs) {
		if (this.durationMs <= 0) return { x, z };
		const progress = Math.min(1, Math.max(0, (nowMs - this.startedAt) / this.durationMs));
		if (progress >= 1) {
			this.reset();
			return { x, z };
		}
		const remaining = 1 - progress;
		return { x: x + this.offsetX * remaining, z: z + this.offsetZ * remaining };
	}

	/**
	 * Preserve the currently displayed position when an authoritative correction
	 * changes the prediction. Zero-error snapshots leave an active blend alone.
	 */
	correct(previous, current, errorMeters, band, nowMs) {
		if (band === "snap") {
			this.reset();
			return;
		}
		if (!Number.isFinite(errorMeters) || errorMeters <= 1e-6) return;
		const visible = this.sample(previous.x, previous.z, nowMs);
		this.offsetX = visible.x - current.x;
		this.offsetZ = visible.z - current.z;
		this.startedAt = nowMs;
		this.durationMs = band === "blend100" ? BLEND_NEAR_MS : BLEND_FAR_MS;
	}
}

export function percentile(sorted, pct) {
	if (sorted.length === 0) return 0;
	return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * pct))];
}
