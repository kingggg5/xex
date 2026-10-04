<script lang="ts">
	import { presenceLabel, projectPanelCoordinate } from "../panel-data";
	import type { MapPanelSnapshot, PanelSnapshot } from "../panel-types";
	let { model }: { model: PanelSnapshot } = $props();
	let map = $derived(model.map);
	let th = $derived(model.language === "th");
	let px = $derived(projectPanelCoordinate(map.player.x, map.extent));
	let py = $derived(projectPanelCoordinate(-map.player.z, map.extent));
	function path(points: MapPanelSnapshot["questRoute"]): string { return points.map((point) => `${projectPanelCoordinate(point.x, map.extent)},${projectPanelCoordinate(-point.z, map.extent)}`).join(" "); }
	let legend = $derived([{ color: "#f4d27d", label: th ? "เซลล่า (NPC)" : "Sella (NPC)" }, { color: "#8ee4ee", label: th ? "เครื่องหมายลม" : "Windmark" }, { color: "#a9e08c", label: th ? "ลานล่า" : "Hunt clearing" }, { color: "#9caf91", label: th ? "ทางเดินสำรวจ" : "Exploration trail" }, { color: "#ffe198", label: th ? "ตัวคุณ" : "You" }]);
</script>

<div class="world-map-layout">
	<figure class="world-map-figure"><svg viewBox="0 0 340 340" class="world-map-svg" role="img" aria-label={th ? "แผนที่ชายแดนเขียวขจี" : "Verdant Frontier world map"}>
		<title>{th ? "แผนที่ชายแดนเขียวขจี" : "Verdant Frontier world map"}</title>
		<rect x="1" y="1" width="338" height="338" rx="10" fill="#0d1a21" stroke="rgba(224,200,143,.4)" />
		{#each [85, 170, 255] as position}<line x1={position} y1="6" x2={position} y2="334" stroke="rgba(210,197,152,.08)" /><line x1="6" y1={position} x2="334" y2={position} stroke="rgba(210,197,152,.08)" />{/each}
		{#if map.questRoute.length > 0}<polyline points={path(map.questRoute)} fill="none" stroke="#d5ad59" stroke-width="2" stroke-dasharray="7 5" opacity="0.85" stroke-linejoin="round" />{/if}
		{#each map.routes as route}{#if route.points.length > 0}<polyline points={path(route.points)} fill="none" stroke="#9caf91" stroke-width="1.6" stroke-dasharray="3 4" opacity="0.75" stroke-linejoin="round" />{/if}{/each}
		{#each map.points as point}
			{@const cx = projectPanelCoordinate(point.x, map.extent)}{@const cy = projectPanelCoordinate(-point.z, map.extent)}
			<circle {cx} {cy} r={point.radius} fill={point.color} stroke="#0c1418" stroke-width="1.5" />
			<text x={cx > 245 ? cx - 9 : cx + 9} y={cy + 4} text-anchor={cx > 245 ? "end" : "start"} font-size="11" fill="#e9e4d7" stroke="#0c1418" stroke-width="3" paint-order="stroke">{point.label}</text>
		{/each}
		<polygon points={`${px},${py - 8} ${px + 6},${py + 5} ${px},${py + 2} ${px - 6},${py + 5}`} fill="#ffe198" stroke="#5c4a1e" stroke-width="1" />
	</svg></figure>
	<div class="map-side"><p class="panel-kicker">{th ? "ชายแดนเขียวขจี" : "VERDANT FRONTIER"}</p><p class="map-coords">{map.player.x.toFixed(1)}, {map.player.z.toFixed(1)}</p>
		{#if map.inTower}<span class="map-tower-badge">{map.towerFloor > 0 ? (th ? `หอคอย · ชั้น ${map.towerFloor}` : `TOWER · FLOOR ${map.towerFloor}`) : th ? "หอคอย" : "TOWER"}</span>{/if}
		<h3>{th ? "คำอธิบาย" : "Legend"}</h3><ul class="map-legend">{#each legend as entry}<li><i style:background={entry.color} aria-hidden="true"></i>{entry.label}</li>{/each}</ul>
		<h3>{th ? "กลุ่มบนแผนที่" : "Group on map"}</h3><div class="map-members">{#each map.members as member}<span>{member.name} · {presenceLabel(member, model.language)}</span>{:else}<span>{th ? "ไม่มีสมาชิกกลุ่มให้แสดง" : "No group members to show."}</span>{/each}</div>
	</div>
</div>
