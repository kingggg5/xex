import type { Rive } from "@rive-app/canvas";
import { readUiResource } from "./resource";

export interface RiveAdapterOptions {
	artboard?: string;
	stateMachines?: readonly string[];
	onError?(message: string): void;
}
export interface RiveAdapter { setActive(active: boolean): void; dispose(): void }
const MAX_RIV_BYTES = 4 * 1024 * 1024;
const MAX_CANVAS_PIXELS = 512 * 512;
let sdkPromise: Promise<typeof import("@rive-app/canvas")> | null = null;

async function sdk(): Promise<typeof import("@rive-app/canvas")> {
	if (!sdkPromise) sdkPromise = Promise.all([import("@rive-app/canvas"), import("@rive-app/canvas/rive.wasm?url")]).then(([runtime, wasm]) => {
		runtime.RuntimeLoader.setWasmUrl(wasm.default);
		runtime.RuntimeLoader.setWasmFallbackUrl(null);
		return runtime;
	});
	return sdkPromise;
}

/** Dormant until an explicit local .riv asset is supplied and actually visible. */
export function mountOptionalRive(canvas: HTMLCanvasElement, source: string | null, options: RiveAdapterOptions = {}): RiveAdapter {
	if (!source) return { setActive() {}, dispose() {} };
	const url = new URL(source, window.location.href);
	if (url.origin !== window.location.origin || !url.pathname.toLowerCase().endsWith(".riv")) throw new TypeError("Rive UI requires an explicit same-origin .riv asset");
	const lifetime = new AbortController();
	const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
	let disposed = false;
	let active = true;
	let visible = false;
	let loading = false;
	let instance: Rive | null = null;
	let staticFrame = 0;
	const resize = () => {
		const bounds = canvas.getBoundingClientRect();
		let scale = Math.min(1.5, window.devicePixelRatio || 1);
		const pixels = bounds.width * bounds.height * scale * scale;
		if (pixels > MAX_CANVAS_PIXELS) scale *= Math.sqrt(MAX_CANVAS_PIXELS / pixels);
		const width = Math.max(1, Math.min(512, Math.floor(bounds.width * scale)));
		const height = Math.max(1, Math.min(512, Math.floor(bounds.height * scale)));
		if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; instance?.resizeToCanvas(); }
	};
	const sync = () => {
		if (disposed) return;
		const shown = active && visible && !document.hidden;
		if (!instance) { if (shown && !loading) void load(); return; }
		window.cancelAnimationFrame(staticFrame);
		if (!shown) { instance.pause(); instance.stopRendering(); }
		else if (motion.matches) {
			instance.pause(); instance.startRendering();
			staticFrame = window.requestAnimationFrame(() => instance?.stopRendering());
		} else { instance.startRendering(); instance.play(); }
	};
	async function load(): Promise<void> {
		loading = true;
		try {
			const [runtime, buffer] = await Promise.all([sdk(), readUiResource(url.href, MAX_RIV_BYTES, lifetime.signal)]);
			if (disposed) return;
			resize();
			instance = new runtime.Rive({ canvas, buffer, autoplay: false, enableRiveAssetCDN: false,
				artboard: options.artboard?.slice(0, 64), stateMachines: options.stateMachines?.slice(0, 8).map((name) => name.slice(0, 64)),
				onLoad: () => { if (!disposed) { resize(); instance?.resizeToCanvas(); sync(); } },
				onLoadError: () => { if (!disposed) { instance?.cleanup(); instance = null; options.onError?.("Animation could not be loaded."); } },
			});
		} catch { if (!disposed) options.onError?.("Animation could not be loaded."); }
	}
	const observer = new IntersectionObserver((entries) => { visible = entries.some((entry) => entry.target === canvas && entry.isIntersecting); sync(); });
	observer.observe(canvas);
	const resizes = new ResizeObserver(resize);
	resizes.observe(canvas);
	document.addEventListener("visibilitychange", sync, { signal: lifetime.signal });
	motion.addEventListener("change", sync, { signal: lifetime.signal });
	return {
		setActive(value) { active = value; sync(); },
		dispose() {
			if (disposed) return;
			disposed = true; lifetime.abort(); observer.disconnect(); resizes.disconnect();
			window.cancelAnimationFrame(staticFrame); instance?.cleanup(); instance = null;
		},
	};
}
