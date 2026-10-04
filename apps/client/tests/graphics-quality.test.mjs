import test from 'node:test';
import assert from 'node:assert/strict';

let importCounter = 0;
const importFresh = () => import(`../src/graphics-quality.mjs?graphics-test=${importCounter++}`);

function withLocalStorage(storage, run) {
	const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
	Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
	return Promise.resolve().then(run).finally(() => {
		if (previous) Object.defineProperty(globalThis, 'localStorage', previous);
		else delete globalThis.localStorage;
	});
}

function memoryStorage(initial = {}) {
	const values = new Map(Object.entries(initial));
	return {
		values,
		getItem(key) { return values.has(key) ? values.get(key) : null; },
		setItem(key, value) { values.set(key, String(value)); },
		removeItem(key) { values.delete(key); },
	};
}

test('immutable preset specs recommend a 30 fps mobile starting point and 60 fps desktop starting point', async () => {
	const quality = await importFresh();
	assert.ok(Object.isFrozen(quality.GRAPHICS_PRESETS));
	for (const preset of quality.GRAPHICS_PRESET_NAMES) assert.ok(Object.isFrozen(quality.GRAPHICS_PRESETS[preset]));
	assert.equal(quality.resolveGraphicsPreset(null, { formFactor: 'mobile', width: 390, height: 844, devicePixelRatio: 3 }).preset, 'medium');
	assert.equal(quality.resolveGraphicsPreset(null, { formFactor: 'mobile' }).targetFps, 30);
	assert.equal(quality.resolveGraphicsPreset(null, { formFactor: 'desktop' }).preset, 'high');
	assert.equal(quality.resolveGraphicsPreset(null, { formFactor: 'desktop' }).targetFps, 60);
	assert.equal(quality.resolveGraphicsPreset(null, {}).preset, 'medium');
	assert.deepEqual(quality.GRAPHICS_PRESET_NAMES.map(name => quality.GRAPHICS_PRESETS[name].maxDpr), [1, 1.25, 1.5, 2]);
});

test('invalid, malformed, and old-version storage safely fall back to Auto', async () => {
	const key = 'aetherfield_graphics_quality_v1';
	for (const raw of ['{bad json', JSON.stringify({ version: 0, preference: 'high' }), JSON.stringify({ version: 1, preference: 'maximum' })]) {
		await withLocalStorage(memoryStorage({ [key]: raw }), async () => {
			const quality = await importFresh();
			assert.equal(quality.getGraphicsPreference(), null);
			assert.equal(quality.resolveGraphicsPreset(quality.getGraphicsPreference(), { formFactor: 'desktop' }).preset, 'high');
		});
	}
});

test('preference validates enums, persists versioned data, emits primitive changes, and unsubscribes', async () => {
	const storage = memoryStorage();
	await withLocalStorage(storage, async () => {
		const quality = await importFresh();
		const changes = [];
		const unsubscribe = quality.subscribeGraphicsPreference(change => changes.push(change));
		assert.throws(() => quality.setGraphicsPreference('maximum'), RangeError);
		assert.equal(quality.getGraphicsPreference(), null);
		assert.equal(quality.setGraphicsPreference('ultra'), 'ultra');
		assert.equal(quality.getGraphicsPreference(), 'ultra');
		assert.deepEqual(JSON.parse(storage.getItem(quality.GRAPHICS_PREFERENCE_STORAGE_KEY)), { version: 1, preference: 'ultra' });
		assert.deepEqual(changes, [{ preference: 'ultra' }]);
		unsubscribe();
		assert.equal(quality.setGraphicsPreference(null), null);
		assert.equal(quality.getGraphicsPreference(), null);
		assert.equal(storage.getItem(quality.GRAPHICS_PREFERENCE_STORAGE_KEY), null);
		assert.deepEqual(changes, [{ preference: 'ultra' }]);
	});
});

test('storage access failures keep preference session-only and do not break subscribers', async () => {
	const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
	Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('storage blocked'); } });
	try {
		const quality = await importFresh();
		const changes = [];
		quality.subscribeGraphicsPreference(change => changes.push(change));
		assert.equal(quality.getGraphicsPreference(), null);
		assert.equal(quality.setGraphicsPreference('low'), 'low');
		assert.equal(quality.getGraphicsPreference(), 'low');
		assert.deepEqual(changes, [{ preference: 'low' }]);
	} finally {
		if (previous) Object.defineProperty(globalThis, 'localStorage', previous);
		else delete globalThis.localStorage;
	}
});

test('Auto remains persisted when a storage adapter rejects removeItem but allows writes', async () => {
	const storage = memoryStorage();
	storage.removeItem = () => { throw new Error('remove blocked'); };
	await withLocalStorage(storage, async () => {
		const quality = await importFresh();
		quality.setGraphicsPreference('high');
		quality.setGraphicsPreference(null);
		assert.deepEqual(JSON.parse(storage.getItem(quality.GRAPHICS_PREFERENCE_STORAGE_KEY)), { version: 1, preference: null });
	});
});

test('effective render dimensions remain under every preset pixel ceiling', async () => {
	const quality = await importFresh();
	const viewports = [
		{ formFactor: 'mobile', width: 390, height: 844, devicePixelRatio: 3 },
		{ formFactor: 'mobile', width: 430, height: 932, devicePixelRatio: 3.5 },
		{ formFactor: 'desktop', width: 1920, height: 1080, devicePixelRatio: 2 },
		{ formFactor: 'desktop', width: 3840, height: 2160, devicePixelRatio: 2 },
		{ formFactor: 'desktop', width: 7680, height: 4320, devicePixelRatio: 3 },
	];
	for (const preset of quality.GRAPHICS_PRESET_NAMES) {
		for (const viewport of viewports) {
			const result = quality.resolveGraphicsPreset(preset, viewport);
			assert.ok(result.renderPixelCount <= result.maxRenderPixels, `${preset}: ${result.renderPixelCount} > ${result.maxRenderPixels}`);
			assert.ok(result.effectiveDpr <= result.maxDpr * result.resolutionScale + Number.EPSILON);
			assert.ok(Math.abs(result.hardwareScalingLevel - 1 / result.effectiveDpr) < 1e-12);
			assert.equal(result.renderPixelCount, result.renderWidth * result.renderHeight);
		}
	}
	assert.throws(() => quality.resolveGraphicsPreset('high', { formFactor: 'desktop', width: 65_537, height: 1 }), RangeError);
	assert.equal(quality.resolveGraphicsPreset('high', null).formFactor, 'unknown');
});

test('mobile ceilings keep Ultra bounded while retaining quality-tier differences', async () => {
	const quality = await importFresh();
	for (const preset of quality.GRAPHICS_PRESET_NAMES) {
		const result = quality.resolveGraphicsPreset(preset, { formFactor: 'mobile', width: 430, height: 932, devicePixelRatio: 3 });
		assert.ok(result.maxDpr <= 1.5);
		assert.ok(result.maxRenderPixels <= 3_000_000);
		assert.ok(result.targetFps <= 30);
		assert.ok(result.shadowMapSize <= 1024);
		assert.ok(result.cascades <= 2);
		assert.ok(result.renderPixelCount <= 3_000_000);
	}
	const low = quality.resolveGraphicsPreset('low', { formFactor: 'mobile', width: 430, height: 932, devicePixelRatio: 3 });
	const medium = quality.resolveGraphicsPreset('medium', { formFactor: 'mobile', width: 430, height: 932, devicePixelRatio: 3 });
	const high = quality.resolveGraphicsPreset('high', { formFactor: 'mobile', width: 430, height: 932, devicePixelRatio: 3 });
	const ultra = quality.resolveGraphicsPreset('ultra', { formFactor: 'mobile', width: 430, height: 932, devicePixelRatio: 3 });
	assert.equal(low.maxDpr, 1);
	assert.equal(medium.maxDpr, 1.25);
	assert.equal(ultra.maxDpr, 1.5);
	assert.equal(high.cascades, 2);
	assert.equal(ultra.cascades, 2);
	assert.notEqual(high.resolutionScale, ultra.resolutionScale);
	assert.ok(ultra.effectiveDpr > high.effectiveDpr);
	assert.ok(ultra.vegetationDensity > high.vegetationDensity);
	assert.ok(ultra.vegetationDistanceFactor > high.vegetationDistanceFactor);
	assert.ok(ultra.weatherParticleBudget > high.weatherParticleBudget);
	assert.ok(ultra.waterDetail > high.waterDetail);
});

test('desktop Ultra retains its full preset budget', async () => {
	const quality = await importFresh();
	const desktopUltra = quality.resolveGraphicsPreset('ultra', { formFactor: 'desktop', width: 1920, height: 1080, devicePixelRatio: 2 });
	assert.equal(desktopUltra.maxDpr, 2);
	assert.equal(desktopUltra.maxRenderPixels, 11_059_200);
	assert.equal(desktopUltra.targetFps, 60);
	assert.equal(desktopUltra.shadowMapSize, 4096);
	assert.equal(desktopUltra.cascades, 4);
	assert.equal(desktopUltra.resolutionScale, 1);
	assert.equal(desktopUltra.effectiveDpr, 2);
});

test('Auto ceilings preserve budget tiers and bounded phone opt-ins without changing the base FPS', async () => {
	const quality = await importFresh();
	for (const preset of ['low', 'medium']) {
		for (const formFactor of ['desktop', 'mobile']) {
			const resolved = quality.resolveGraphicsPreset(preset, { formFactor });
			assert.equal(resolved.targetFps, 30);
			assert.equal(resolved.autoCeilingFps, 30);
		}
	}
	for (const preset of ['high', 'ultra']) {
		const desktop = quality.resolveGraphicsPreset(preset, { formFactor: 'desktop' });
		const phone = quality.resolveGraphicsPreset(preset, { formFactor: 'mobile' });
		assert.equal(desktop.targetFps, 60); assert.equal(desktop.autoCeilingFps, 0);
		assert.equal(phone.targetFps, 30); assert.equal(phone.autoCeilingFps, 60);
	}
});
