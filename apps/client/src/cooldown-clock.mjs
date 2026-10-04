/** Protocol v6 deadlines use room simulation milliseconds, not UTC or browser uptime. */
export function localCooldownDeadline(endsAtMs, estimatedServerTick, nowMs, maxDurationMs = 65_000) {
	const deadline = Number(endsAtMs);
	if (!Number.isSafeInteger(deadline) || deadline <= 0 || !Number.isFinite(estimatedServerTick)
		|| estimatedServerTick < 0 || !Number.isFinite(nowMs) || !Number.isFinite(maxDurationMs) || maxDurationMs < 0) return 0;
	const remaining = Math.max(0, Math.min(maxDurationMs, deadline - estimatedServerTick * 50));
	return remaining > 0 ? nowMs + remaining : 0;
}

/** An old acknowledgment must never overwrite a later prediction for that action. */
export class ActionResultOrder {
	constructor() { this.latest = new Map(); }
	register(action, sequence) { this.latest.set(action, sequence); }
	isLatest(action, sequence) { return this.latest.get(action) === sequence; }
	reset() { this.latest.clear(); }
}
