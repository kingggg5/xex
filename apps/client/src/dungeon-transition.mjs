/** Pure D0 coordinator. Effects describe work; the caller owns I/O and resources. */
export const STATES = Object.freeze({
	explore: "Explore", prepare: "Prepare", ready: "Ready", commit: "Commit",
	enter: "Enter", failure: "Failure", recover: "Recover",
});

function positive(value, name) {
	if (!Number.isSafeInteger(value) || value <= 0) throw new RangeError(`${name} must be a positive safe integer`);
	return value;
}

function identity(value, name) {
	if (typeof value !== "string" || value.length < 1 || value.length > 128) throw new RangeError(`${name} must contain 1–128 characters`);
	return value;
}

export class DungeonTransition {
	#clock;
	#prepareMs;
	#commitMs;
	#lastTime = -Infinity;
	#state = STATES.explore;
	#generation = 0;
	#transfer = null;
	#deadline = null;
	#reason = null;

	constructor({ clock = () => performance.now(), prepareMs = 30_000, commitMs = 10_000 } = {}) {
		if (typeof clock !== "function") throw new TypeError("clock must be a function");
		this.#clock = clock;
		this.#prepareMs = positive(prepareMs, "prepareMs");
		this.#commitMs = positive(commitMs, "commitMs");
	}

	get snapshot() {
		return Object.freeze({ state: this.#state, generation: this.#generation, deadline: this.#deadline,
			reason: this.#reason, transfer: this.#transfer ? Object.freeze({ ...this.#transfer }) : null });
	}

	#now() {
		const now = this.#clock();
		if (!Number.isFinite(now) || now < this.#lastTime) throw new RangeError("clock must be finite and monotonic");
		this.#lastTime = now;
		return now;
	}

	#effect(type, extra = {}) {
		return { type, generation: this.#generation, transferId: this.#transfer?.transferId,
			reservationId: this.#transfer?.reservationId ?? null, ...extra };
	}

	#fail(reason, effects) {
		effects.push(this.#effect("release"), this.#effect("dispose_staging"));
		this.#generation++;
		this.#state = STATES.failure;
		this.#deadline = null;
		this.#reason = reason;
	}

	#recover(reason, now, effects) {
		effects.push(this.#effect("dispose_staging"));
		this.#generation++;
		this.#transfer.assetsReady = false;
		this.#transfer.destinationReady = false;
		this.#state = STATES.recover;
		this.#reason = reason;
		this.#deadline = now + this.#commitMs;
		effects.push(this.#effect("query_status"));
	}

	#enter(effects) {
		if (this.#transfer.committed && this.#transfer.assetsReady && this.#transfer.destinationReady) {
			this.#state = STATES.enter;
			this.#deadline = null;
			this.#reason = null;
			effects.push(this.#effect("reveal"));
		}
	}

	/** Every asynchronous event carries the generation and transfer ID captured at dispatch. */
	dispatch(event) {
		const effects = [];
		const now = this.#now();
		let accepted = false;
		const result = () => ({ accepted, snapshot: this.snapshot, effects });
		if (event.type === "resume") {
			if (![STATES.explore, STATES.failure].includes(this.#state)) return result();
			const transferId = identity(event.transferId, "transferId");
			const dungeonId = identity(event.dungeonId, "dungeonId");
			const reservationId = identity(event.reservationId, "reservationId");
			const contentVersion = identity(event.contentVersion, "contentVersion");
			this.#generation++;
			this.#transfer = { transferId, dungeonId, reservationId, contentVersion, expiresAt: null,
				assetsReady: false, destinationReady: false, committed: false };
			this.#state = STATES.recover;
			this.#reason = "resume";
			this.#deadline = now + this.#commitMs;
			effects.push(this.#effect("query_status"));
			accepted = true;
			return result();
		}
		if (event.type === "begin") {
			if (![STATES.explore, STATES.failure].includes(this.#state)) return result();
			const transferId = identity(event.transferId, "transferId");
			const dungeonId = identity(event.dungeonId, "dungeonId");
			this.#generation++;
			this.#transfer = { transferId, dungeonId, reservationId: null, contentVersion: null,
				expiresAt: null, assetsReady: false, destinationReady: false, committed: false };
			this.#state = STATES.prepare;
			this.#reason = null;
			this.#deadline = now + this.#prepareMs;
			effects.push(this.#effect("prepare", { dungeonId }));
			accepted = true;
			return result();
		}
		if (!this.#transfer) return result();
		if (event.type === "tick") {
			if (this.#deadline !== null && now >= this.#deadline) {
				accepted = true;
				if ([STATES.prepare, STATES.ready].includes(this.#state)) this.#fail("timeout", effects);
				else if (this.#state === STATES.commit) this.#recover("commit_timeout", now, effects);
				else if (this.#state === STATES.recover) {
					this.#deadline = null; // No unbounded automatic retry loop.
					this.#reason = "status_timeout";
					effects.push(this.#effect("recovery_timeout"));
				}
			}
			return result();
		}
		if (event.type === "cancel") {
			if ([STATES.prepare, STATES.ready].includes(this.#state)) {
				accepted = true;
				this.#fail("cancelled", effects);
			}
			return result();
		}
		if (event.type === "reconnect") {
			if ([STATES.commit, STATES.enter, STATES.recover].includes(this.#state)) {
				accepted = true;
				this.#recover("reconnect", now, effects);
			} else if ([STATES.prepare, STATES.ready].includes(this.#state)) {
				accepted = true;
				this.#fail("disconnected_before_commit", effects);
			}
			return result();
		}
		if (event.type === "request_commit") {
			if (this.#state !== STATES.ready) return result();
			accepted = true;
			if (now >= this.#deadline) {
				this.#fail(now >= this.#transfer.expiresAt ? "reservation_expired" : "timeout", effects);
			}
			else {
				this.#state = STATES.commit; // From here the server may have committed.
				this.#deadline = now + this.#commitMs;
				effects.push(this.#effect("confirm_and_commit", { contentVersion: this.#transfer.contentVersion }));
			}
			return result();
		}
		if (event.type === "finish") {
			if (this.#state !== STATES.enter) return result();
			this.#generation++;
			this.#state = STATES.explore;
			this.#transfer = null;
			accepted = true;
			return result();
		}
		if (event.generation !== this.#generation || event.transferId !== this.#transfer.transferId) {
			if (event.type === "assets_ready") effects.push({ type: "dispose_stale", generation: event.generation, transferId: event.transferId });
			return result();
		}
		switch (event.type) {
			case "reserved": {
				if (this.#state !== STATES.prepare || this.#transfer.reservationId !== null) break;
				if (now >= this.#deadline) {
					this.#fail("timeout", effects);
					accepted = true;
					break;
				}
				identity(event.reservationId, "reservationId");
				identity(event.contentVersion, "contentVersion");
				if (!Number.isFinite(event.expiresAt) || event.expiresAt <= now) {
					this.#fail("reservation_expired", effects);
					accepted = true;
					break;
				}
				this.#transfer.reservationId = event.reservationId;
				this.#transfer.contentVersion = event.contentVersion;
				this.#transfer.expiresAt = event.expiresAt;
				this.#deadline = Math.min(this.#deadline, event.expiresAt);
				effects.push(this.#effect("stage_assets", { contentVersion: event.contentVersion }));
				accepted = true;
				break;
			}
			case "assets_ready": {
				if (![STATES.prepare, STATES.commit].includes(this.#state) || this.#transfer.assetsReady) break;
				if (this.#transfer.reservationId === null || event.contentVersion !== this.#transfer.contentVersion) break;
				if (this.#state === STATES.prepare && now >= this.#deadline) {
					this.#fail("timeout", effects);
					break;
				}
				this.#transfer.assetsReady = true;
				accepted = true;
				if (this.#state === STATES.prepare) this.#state = STATES.ready;
				else this.#enter(effects);
				break;
			}
			case "rejected":
				// In Commit/Recover this event must certify that no commit occurred.
				if ([STATES.prepare, STATES.ready].includes(this.#state)
					|| ([STATES.commit, STATES.recover].includes(this.#state) && event.uncommitted === true && !this.#transfer.committed)) {
					accepted = true;
					this.#fail(identity(event.reason, "reason"), effects);
				}
				break;
			case "load_failed":
				if ([STATES.prepare, STATES.ready].includes(this.#state)) {
					accepted = true;
					this.#fail(identity(event.reason, "reason"), effects);
				} else if (this.#state === STATES.commit) {
					accepted = true;
					this.#recover("load_failed_after_commit_request", now, effects);
				}
				break;
			case "committed":
			case "status_committed": {
				if (event.reservationId !== this.#transfer.reservationId || event.contentVersion !== this.#transfer.contentVersion) break;
				if (event.type === "status_committed") {
					if (this.#state !== STATES.recover) break;
					this.#state = STATES.commit;
					this.#deadline = now + this.#commitMs;
					this.#reason = null;
					effects.push(this.#effect("stage_assets", { contentVersion: event.contentVersion }), this.#effect("request_destination"));
				} else if (this.#state !== STATES.commit || this.#transfer.committed) break;
				this.#transfer.committed = true;
				accepted = true;
				this.#enter(effects);
				break;
			}
			case "destination_ready":
				if (this.#state === STATES.commit && event.reservationId === this.#transfer.reservationId
					&& event.contentVersion === this.#transfer.contentVersion && !this.#transfer.destinationReady) {
					this.#transfer.destinationReady = true;
					accepted = true;
					this.#enter(effects);
				}
				break;
		}
		return result();
	}
}
