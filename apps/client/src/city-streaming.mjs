/** Create a deferred, shared loader for a streamed city LOD. */
export function createLazyLoadOnce(loader) {
	if (typeof loader !== "function") throw new TypeError("City asset loader must be a function.");
	let pending = null;
	return function ensureLoaded() {
		if (pending) return pending;
		pending = Promise.resolve().then(loader).catch((error) => {
			pending = null;
			throw error;
		});
		return pending;
	};
}

/** Prepare offscreen; an explicit covered transition commits the replacement later. */
export function createStagedCityLoader(prepare, activate) {
	/** @type {"idle" | "loading" | "prepared" | "ready" | "failed"} */
	let state = "idle";
	let prepared = false;
	const prepareOnce = createLazyLoadOnce(async () => {
		state = "loading";
		try { await prepare(); prepared = true; state = "prepared"; }
		catch (error) { state = "failed"; throw error; }
	});
	const ensure = () => {
		if (state === "failed" && prepared) state = "prepared";
		return prepareOnce();
	};
	return Object.assign(ensure, {
		getState: () => state,
		reveal() {
			if (state !== "prepared") return;
			try { activate(); state = "ready"; }
			catch (error) { state = "failed"; throw error; }
		},
	});
}

/** Request the detailed city once per gate entry; a 12 m exit buffer rearms it. */
export function createGateTriggeredLoader(gateZ, loader, exitBuffer = 12) {
	let attemptedThisEntry = false;
	return function updatePlayerPosition(z) {
		if (!Number.isFinite(z)) return null;
		if (z < gateZ - exitBuffer) {
			attemptedThisEntry = false;
			return null;
		}
		if (z < gateZ || attemptedThisEntry) return null;
		attemptedThisEntry = true;
		return loader();
	};
}

/** Load the authored southbound detail band shortly before the flat ground seam. */
export function createSouthboundCellLoader(triggerZ, loader) {
	if (!Number.isFinite(triggerZ) || typeof loader !== "function") {
		throw new TypeError("Southbound cell loader needs a finite trigger and loader function.");
	}
	let pending = false;
	let loaded = false;
	return function updatePlayerPosition(z) {
		if (!Number.isFinite(z) || z > triggerZ || pending || loaded) return null;
		pending = true;
		return Promise.resolve().then(loader).then((result) => {
			loaded = true;
			pending = false;
			return result;
		}).catch((error) => {
			pending = false;
			throw error;
		});
	};
}
