/**
 * World map modal: renders the Verdant Frontier zone from the content bundle
 * POIs as an SVG (same projection spirit as the wiki slice: world x/z scaled
 * into a 340-unit viewBox), with the dashed quest route, the live player
 * marker, group members' current room/tower as text, and the tower badge.
 *
 * Rendering only — GameHud owns the position/bundle state and re-renders this
 * panel with fresh data on open (and while open as the player moves).
 */

import { placementLabel } from "./social-ui";
import type { FriendEntry } from "./social-ui";
import type { WorldRouteDefinition } from "./world-layout";

export interface MapPoint {
	x: number;
	z: number;
}

export interface WorldMapState {
	/** Zone POIs, e.g. from bundle.zones[0].pois (entry, sella, windmark_1…). */
	points: Record<string, MapPoint>;
	/** Authored world trails shared with the terrain-cell contract. */
	routes: WorldRouteDefinition[];
	/** Zone half extent: world coordinates span [-extent, extent]. */
	extent: number;
	/** Live player position (refreshed whenever the panel is rendered). */
	player: MapPoint;
	/** Group members with their presence, listed as text beside the map. */
	members: FriendEntry[];
	inTower: boolean;
	towerFloor: number;
}

const MAP_SIZE = 340;
const SVG_NS = "http://www.w3.org/2000/svg";
/** Quest route: entry → regroup → Sella → windmarks in order → hunt clearing. */
const ROUTE_IDS = ["entry", "regroup", "sella", "windmark_1", "windmark_2", "windmark_3", "hunt_clearing"];

// D-06 convention (rooms-ui / tower-ui): Thai copy when the browser language is Thai.
const THAI = typeof navigator === "undefined" ? false : navigator.language.toLowerCase().startsWith("th");

const POI_LABELS: Record<string, [string, string]> = {
	entry: ["Entry", "จุดเริ่มทาง"],
	regroup: ["Regroup", "จุดรวมพล"],
	sella: ["Sella", "เซลล่า"],
	south_trail_marker: ["South Trail Marker", "เสาหินบอกทางใต้"],
	hunt_clearing: ["Hunt Clearing", "ลานล่า"],
	lookout: ["Lookout", "จุดเฝ้ายาม"],
};

const COPY = {
	ariaLabel: THAI ? "แผนที่ชายแดนเขียวขจี" : "Verdant Frontier world map",
	zoneKicker: THAI ? "ชายแดนเขียวขจี" : "VERDANT FRONTIER",
	legendKicker: THAI ? "คำอธิบาย" : "LEGEND",
	legendSella: THAI ? "เซลล่า (NPC)" : "Sella (NPC)",
	legendWindmark: THAI ? "เครื่องหมายลม" : "Windmark",
	legendHunt: THAI ? "ลานล่า" : "Hunt clearing",
	legendTrail: THAI ? "ทางเดินสำรวจ" : "Exploration trail",
	legendYou: THAI ? "ตัวคุณ" : "You",
	groupKicker: THAI ? "กลุ่มบนแผนที่" : "GROUP ON MAP",
	groupEmpty: THAI ? "ไม่มีสมาชิกกลุ่มให้แสดง" : "No group members to show.",
	towerBadge: (floor: number): string =>
		floor > 0 ? (THAI ? `หอคอย · ชั้น ${floor}` : `TOWER · FLOOR ${floor}`) : THAI ? "หอคอย" : "TOWER",
};

/** Projects a world coordinate onto the map viewBox: [-extent, extent] → [0, 340]. */
export function projectToMap(value: number, extent: number): number {
	const safe = Number.isFinite(extent) && extent > 0 ? extent : 28;
	const clamped = Math.max(-safe, Math.min(safe, Number.isFinite(value) ? value : 0));
	return Math.round((clamped / safe * 0.5 + 0.5) * MAP_SIZE * 10) / 10;
}

/** Renders the full map modal content; safe to call repeatedly. */
export function renderWorldMap(container: HTMLElement, state: WorldMapState): void {
	container.replaceChildren();
	const layout = document.createElement("div");
	layout.className = "world-map-layout";

	const figure = document.createElement("figure");
	figure.className = "world-map-figure";
	const svg = svgEl("svg", { viewBox: `0 0 ${MAP_SIZE} ${MAP_SIZE}`, class: "world-map-svg", role: "img" });
	svg.setAttribute("aria-label", COPY.ariaLabel);
	const title = svgEl("title", {});
	title.textContent = COPY.ariaLabel;
	svg.append(title);
	svg.append(svgEl("rect", {
		x: 1, y: 1, width: MAP_SIZE - 2, height: MAP_SIZE - 2, rx: 10,
		fill: "#0d1a21", stroke: "rgba(224,200,143,.4)", "stroke-width": 1,
	}));
	for (const fraction of [0.25, 0.5, 0.75]) {
		const pos = MAP_SIZE * fraction;
		svg.append(svgEl("line", { x1: pos, y1: 6, x2: pos, y2: MAP_SIZE - 6, stroke: "rgba(210,197,152,.08)" }));
		svg.append(svgEl("line", { x1: 6, y1: pos, x2: MAP_SIZE - 6, y2: pos, stroke: "rgba(210,197,152,.08)" }));
	}

	const routePoints = ROUTE_IDS
		.map((id) => state.points[id])
		.filter(isPoint)
		.map((point) => `${projectToMap(point.x, state.extent)},${projectToMap(-point.z, state.extent)}`)
		.join(" ");
	if (routePoints) {
		svg.append(svgEl("polyline", {
			points: routePoints, fill: "none", stroke: "#d5ad59", "stroke-width": 2,
			"stroke-dasharray": "7 5", opacity: 0.85, "stroke-linejoin": "round",
		}));
	}
	for (const route of state.routes) {
		const points = route.points
			.map(([x, z]) => `${projectToMap(x, state.extent)},${projectToMap(-z, state.extent)}`)
			.join(" ");
		if (points) {
			svg.append(svgEl("polyline", {
				points, fill: "none", stroke: "#9caf91", "stroke-width": 1.6,
				"stroke-dasharray": "3 4", opacity: 0.75, "stroke-linejoin": "round",
			}));
		}
	}

	for (const [id, point] of Object.entries(state.points)) {
		if (!isPoint(point)) continue;
		const cx = projectToMap(point.x, state.extent);
		const cy = projectToMap(-point.z, state.extent);
		const windmark = /^windmark_/.test(id);
		svg.append(svgEl("circle", {
			cx, cy,
			r: id === "sella" ? 5.5 : windmark ? 4 : 3.5,
			fill: poiColor(id), stroke: "#0c1418", "stroke-width": 1.5,
		}));
		const flip = cx > MAP_SIZE - 95;
		const label = svgEl("text", {
			x: flip ? cx - 9 : cx + 9,
			y: cy + 4,
			"text-anchor": flip ? "end" : "start",
			"font-size": 11,
			fill: "#e9e4d7",
			stroke: "#0c1418",
			"stroke-width": 3,
			"paint-order": "stroke",
		});
		label.textContent = poiLabel(id);
		svg.append(label);
	}

	const px = projectToMap(state.player.x, state.extent);
	const py = projectToMap(-state.player.z, state.extent);
	svg.append(svgEl("polygon", {
		points: `${px},${py - 8} ${px + 6},${py + 5} ${px},${py + 2} ${px - 6},${py + 5}`,
		fill: "#ffe198", stroke: "#5c4a1e", "stroke-width": 1,
	}));
	figure.append(svg);
	layout.append(figure);

	const side = document.createElement("div");
	side.className = "map-side";
	side.append(el("p", "panel-kicker", COPY.zoneKicker));
	side.append(el("p", "map-coords", `${state.player.x.toFixed(1)}, ${state.player.z.toFixed(1)}`));
	if (state.inTower) side.append(el("span", "map-tower-badge", COPY.towerBadge(state.towerFloor)));

	side.append(el("p", "panel-kicker", COPY.legendKicker));
	const legend = document.createElement("ul");
	legend.className = "map-legend";
	for (const [color, text] of [
		[poiColor("sella"), COPY.legendSella],
		[poiColor("windmark_1"), COPY.legendWindmark],
		[poiColor("hunt_clearing"), COPY.legendHunt],
		[poiColor("south_trail_marker"), COPY.legendTrail],
		["#ffe198", COPY.legendYou],
	] as const) {
		const item = document.createElement("li");
		const dot = document.createElement("i");
		dot.style.background = color;
		item.append(dot, document.createTextNode(text));
		legend.append(item);
	}
	side.append(legend);

	side.append(el("p", "panel-kicker", COPY.groupKicker));
	const members = el("div", "map-members");
	if (state.members.length === 0) {
		members.append(el("span", "", COPY.groupEmpty));
	} else {
		for (const member of state.members) {
			members.append(el("span", "", `${member.name} · ${placementLabel(member)}`));
		}
	}
	side.append(members);

	layout.append(side);
	container.append(layout);
}

function isPoint(value: unknown): value is MapPoint {
	if (typeof value !== "object" || value === null) return false;
	const point = value as Partial<MapPoint>;
	return Number.isFinite(point.x) && Number.isFinite(point.z);
}

function poiColor(id: string): string {
	if (id === "sella") return "#f4d27d";
	if (/^windmark_/.test(id)) return "#8ee4ee";
	if (id === "hunt_clearing") return "#a9e08c";
	if (id === "south_trail_marker") return "#d2b7e8";
	return "#d9d2b8";
}

function poiLabel(id: string): string {
	const known = POI_LABELS[id];
	if (known) return known[THAI ? 1 : 0];
	const windmark = id.match(/^windmark_(\d+)$/);
	if (windmark) return THAI ? `เครื่องหมายลม ${windmark[1]}` : `Windmark ${windmark[1]}`;
	return id.replaceAll("_", " ");
}

function svgEl(tag: string, attrs: Record<string, string | number>): SVGElement {
	const node = document.createElementNS(SVG_NS, tag);
	for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
	return node;
}

function el(tag: string, className: string, text?: string): HTMLElement {
	const node = document.createElement(tag);
	node.className = className;
	if (text !== undefined) node.textContent = text;
	return node;
}
