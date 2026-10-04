import type { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import type { ArcRotateCameraPointersInput } from "@babylonjs/core/Cameras/Inputs/arcRotateCameraPointersInput";

type OrbitMedia = Pick<MediaQueryList,"matches"|"addEventListener"|"removeEventListener">;
interface OrbitOptions { touch?: OrbitMedia | null; reducedMotion?: OrbitMedia | null }

/** Configure Babylon's native inputs, rather than introducing another drag/update loop. */
export function configure360Orbit(camera: ArcRotateCamera, canvas: HTMLCanvasElement, options: OrbitOptions = {}): () => void {
	camera.lowerAlphaLimit = null;
	camera.upperAlphaLimit = null;
	camera.allowUpsideDown = false;
	camera.panningSensibility = 0;
	// Arrow keys belong to character movement, not a simultaneous orbit input.
	camera.inputs.removeByType("ArcRotateCameraKeyboardMoveInput");
	const input = camera.movement.input;
	input.inputMap = input.inputMap.filter(entry => entry.source !== "keyboard" && !(entry.source === "pointer" && entry.interaction === "pan"));
	input.addEntry({ source: "pointer", button: 2, interaction: "rotate" });
	const pointers = camera.inputs.attached.pointers as ArcRotateCameraPointersInput | undefined;
	if (pointers) {
		pointers.buttons = [0,2];
		pointers.multiTouchPanning = false;
		pointers.multiTouchPanAndZoom = false;
		pointers.pinchZoom = true;
		pointers.useNaturalPinchZoom = true;
	}
	const media = (query: string) => typeof matchMedia === "function" ? matchMedia(query) : null;
	const touch = options.touch ?? media("(any-pointer: coarse), (max-width: 900px)");
	const reduced = options.reducedMotion ?? media("(prefers-reduced-motion: reduce)");
	const refresh = () => {
		camera.angularSensibilityX = touch?.matches ? 380 : 750;
		camera.angularSensibilityY = touch?.matches ? 900 : 1100;
		camera.inertia = reduced?.matches ? 0 : .82;
	};
	const suppressContextMenu = (event: Event) => event.preventDefault();
	touch?.addEventListener("change",refresh); reduced?.addEventListener("change",refresh);
	canvas.addEventListener("contextmenu",suppressContextMenu);
	refresh();
	let disposed = false;
	return () => {
		if (disposed) return; disposed = true;
		touch?.removeEventListener("change",refresh); reduced?.removeEventListener("change",refresh);
		canvas.removeEventListener("contextmenu",suppressContextMenu);
	};
}
