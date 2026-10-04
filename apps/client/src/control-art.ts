import manifest from './assets/ui/control-sets-r01/manifest.json';
import frostglass from './assets/ui/control-sets-r01/a02-frostglass.png';
import wildwood from './assets/ui/control-sets-r01/a04-wildwood-jade.png';
import astral from './assets/ui/control-sets-r01/a05-astral-orbit.png';
import dawn from './assets/ui/control-sets-r01/a08-dawn-petal.png';
import dragonbone from './assets/ui/control-sets-r01/a10-dragonbone.png';
import floating from './assets/ui/control-sets-r01/b04-floating-thumbstick.png';
import crystal from './assets/ui/control-sets-r01/b09-crystal-silver.png';
import celestial from './assets/ui/control-sets-r01/b13-celestial-rune.png';
import { controlSpriteGeometry, type AtlasPart, type SpriteGeometry } from './control-art-geometry.mjs';
import type { ControlArtId } from './control-set.mjs';

const urls: Record<string, string> = { 'a02-frostglass': frostglass, 'a04-wildwood-jade': wildwood, 'a05-astral-orbit': astral, 'a08-dawn-petal': dawn, 'a10-dragonbone': dragonbone, 'b04-floating-thumbstick': floating, 'b09-crystal-silver': crystal, 'b13-celestial-rune': celestial };
export const controlArtOptions = [{ id: 'native' as ControlArtId, name: 'Original', thai: 'แบบเดิม' }, ...manifest.styles.map(style => ({ id: style.id as ControlArtId, name: style.name, thai: style.name }))];
const artStyle = (id: ControlArtId) => manifest.styles.find(style => style.id === id);
function sprite(node: HTMLElement, url: string, part: AtlasPart, width: number): SpriteGeometry {
	const geometry = controlSpriteGeometry(part, width);
	node.style.width = `${geometry.width}px`; node.style.height = `${geometry.height}px`;
	node.style.backgroundImage = `url("${url}")`; node.style.backgroundSize = geometry.backgroundSize;
	node.style.backgroundPosition = geometry.backgroundPosition; node.style.backgroundRepeat = 'no-repeat';
	return geometry;
}
/** Only presentation changes. The existing Svelte joystick retains pointer ownership and commands. */
export function createControlArtStyler() {
	const before = new Map<HTMLElement, Map<string, { value: string; priority: string }>>();
	let marked: HTMLElement | null = null, marker: string | null = null;
	let last = '', lastRing: HTMLElement | null = null, lastKnob: HTMLElement | null = null;
	const set = (node: HTMLElement, key: string, value: string) => {
		let values = before.get(node); if (!values) { values = new Map(); before.set(node, values); }
		if (!values.has(key)) values.set(key, { value: node.style.getPropertyValue(key), priority: node.style.getPropertyPriority(key) });
		node.style.setProperty(key, value);
	};
	function restore() {
		for (const [node, values] of before) for (const [key, prior] of values) {
			if (prior.value) node.style.setProperty(key, prior.value, prior.priority); else node.style.removeProperty(key);
		}
		before.clear();
		if (marked) { if (marker === null) marked.removeAttribute('data-control-art'); else marked.setAttribute('data-control-art', marker); }
		marked = null; marker = null; last = ''; lastRing = null; lastKnob = null;
	}
	function apply(id: ControlArtId) {
		const node = document.querySelector<HTMLElement>('#hud #joystick'), style = artStyle(id);
		const ring = node?.querySelector<HTMLElement>('.joystick-ring'), knob = node?.querySelector<HTMLElement>('.joystick-knob');
		if (!style || !node || !ring || !knob || !node.clientWidth || !node.clientHeight) { restore(); return; }
		const key = `${id}:${node.clientWidth}:${node.clientHeight}`;
		if (key === last && ring === lastRing && knob === lastKnob) return;
		restore(); marked = node; marker = node.getAttribute('data-control-art'); node.setAttribute('data-control-art', id);
		const base = style.components.base, thumb = style.components.thumb;
		const scale = Math.min(node.clientWidth / base.rect_xywh[2], node.clientHeight / base.rect_xywh[3]);
		const baseWidth = base.rect_xywh[2] * scale, baseGeometry = controlSpriteGeometry(base, baseWidth);
		for (const child of [ring, knob]) for (const property of ['border', 'border-radius', 'background', 'box-shadow', 'position', 'display', 'margin', 'padding', 'width', 'height', 'background-image', 'background-size', 'background-position', 'background-repeat']) set(child, property, child.style.getPropertyValue(property));
		for (const child of [ring, knob]) for (const [property, value] of Object.entries({ border: '0', 'border-radius': '0', background: 'none', 'box-shadow': 'none', position: 'absolute', display: 'block', margin: '0', padding: '0' })) set(child, property, value);
		sprite(ring, urls[id], base, baseWidth);
		set(ring, 'inset', 'auto'); set(ring, 'left', `${node.clientWidth / 2 - baseGeometry.pivot.x}px`); set(ring, 'top', `${node.clientHeight / 2 - baseGeometry.pivot.y}px`);
		// Scale the visual translation, while preserving the native joystick's full analog input radius.
		const travel = style.suggestedTravelRadiusCssPx * baseWidth / 200;
		const travelScale = Math.max(.05, Math.min(1, travel / (node.clientWidth * .31)));
		const thumbWidth = node.clientWidth * .42 / travelScale;
		const geometry = sprite(knob, urls[id], thumb, thumbWidth);
		set(knob, 'left', `${baseGeometry.pivot.x - geometry.pivot.x}px`); set(knob, 'top', `${baseGeometry.pivot.y - geometry.pivot.y}px`);
		set(knob, 'scale', `${travelScale}`); set(knob, 'transform-origin', `${geometry.pivot.x}px ${geometry.pivot.y}px`);
		last = key; lastRing = ring; lastKnob = knob;
	}
	return { apply, dispose: restore };
}
/** Sit is deliberately shown as labelled artwork only; no unsupported game action is introduced. */
export function renderControlArtPreview(host: HTMLElement, id: ControlArtId, th: boolean) {
	host.replaceChildren();
	const style = artStyle(id);
	if (!style) { host.textContent = th ? 'จอยและปุ่มเกมใช้แบบเดิม' : 'The original joystick and game buttons are preserved.'; return; }
	for (const [part, label] of [['base', th ? 'ฐานจอย' : 'Base'], ['thumb', th ? 'หัวจอย' : 'Thumb'], ['sit', th ? 'นั่ง · ตัวอย่างภาพ' : 'Sit · artwork only']] as const) {
		const figure = document.createElement('figure'), art = document.createElement('span'), caption = document.createElement('figcaption');
		figure.className = 'hud-layout-art-part'; art.className = 'hud-layout-art-sprite'; art.setAttribute('aria-hidden', 'true');
		sprite(art, urls[id], style.components[part], part === 'base' ? 82 : 44); caption.textContent = label;
		figure.append(art, caption); host.append(figure);
	}
}
