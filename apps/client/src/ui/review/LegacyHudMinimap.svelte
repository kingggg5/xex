<!-- Incumbent UI preserved for DEV-only screenshot review; live world/server data unchanged. -->
<!--
THESIS: A rounded rectangular field chart; live route data leads the frame.
OWN-WORLD: Warm gunmetal, brass edge, moss field, ivory trails and mint player.
STORY: Locate yourself, inspect the nearby route, zoom, then open the world map.
FIRST VIEWPORT: Area name above the chart, north inside, coordinates below.
FORM: Local HUD refinement; the supplied MMO reference pins the frame geometry.
-->
<script lang="ts">
	import type { HudLanguage, HudMinimap } from ".././hud-types";
	let { model, preview, label, onopen, language = "en", locationName = "" }: {
		model: HudMinimap; preview: boolean; label: string; onopen(): void;
		language?: HudLanguage; locationName?: string;
	} = $props();
	let canvas = $state<HTMLCanvasElement>();
	let zoom = $state(1);
	const th = $derived(language === "th");
	const safeExtent = $derived(Number.isFinite(model.extent) && model.extent > 0 ? Math.max(1, model.extent) : 28);
	const playerX = $derived(Number.isFinite(model.playerX) ? model.playerX : 0);
	const playerZ = $derived(Number.isFinite(model.playerZ) ? model.playerZ : 0);
	// The world map owns the full region. The minimap is a local navigation view.
	const viewExtent = $derived(Math.min(safeExtent, 72) / zoom);
	const areaName = $derived(locationName || (th ? "แผนที่พื้นที่" : "Area map"));
	const scaleLabel = $derived(`${Number((viewExtent / 2).toFixed(viewExtent < 2 ? 2 : 1))} m`);
	function coordinate(value: number, center: number, extent: number): number {
		return 128 + (value - center) / extent * 112;
	}
	function dot(ctx: CanvasRenderingContext2D, x: number, y: number, color: string, radius = 3.5): void {
		ctx.fillStyle = color; ctx.strokeStyle = "#16201c"; ctx.lineWidth = 2;
		ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
	}
	$effect(() => {
		const map = model;
		const context = canvas?.getContext("2d");
		if (!context || !canvas) return;
		const extent = viewExtent;
		// Preserve the world-map X/Z projection and keep the live player centered.
		const centerX = playerX, centerZ = playerZ;
		const projectX = (x: number) => coordinate(x, centerX, extent);
		const projectZ = (z: number) => coordinate(z, centerZ, extent);
		context.clearRect(0, 0, 256, 256); context.save();
		context.beginPath(); context.roundRect(2, 2, 252, 252, 12); context.clip();
		context.fillStyle = "#2b3c2e"; context.fillRect(0, 0, 256, 256);
		// Chart field only: do not invent buildings, rivers or terrain silhouettes.
		context.strokeStyle = "rgba(217,222,186,.075)"; context.lineWidth = 1;
		for (let i = 1; i < 8; i++) {
			const pos = i * 32;
			context.beginPath(); context.moveTo(pos, 0); context.lineTo(pos, 256);
			context.moveTo(0, pos); context.lineTo(256, pos); context.stroke();
		}
		const shade = context.createRadialGradient(128, 108, 30, 128, 128, 170);
		shade.addColorStop(0, "rgba(49,74,44,.12)"); shade.addColorStop(1, "rgba(8,16,12,.5)");
		context.fillStyle = shade; context.fillRect(0, 0, 256, 256);
		context.lineCap = "round"; context.lineJoin = "round";
		for (const route of map.routes.slice(0, 64)) {
			if (route.points.length < 2) continue;
			context.beginPath(); let connected = false;
			for (const [x, z] of route.points.slice(0, 80)) {
				if (!Number.isFinite(x) || !Number.isFinite(z)) { connected = false; continue; }
				if (connected) context.lineTo(projectX(x), projectZ(z)); else context.moveTo(projectX(x), projectZ(z));
				connected = true;
			}
			context.strokeStyle = "#16251b"; context.lineWidth = 8; context.stroke();
			context.strokeStyle = "#b6ad82"; context.lineWidth = 4; context.stroke();
			context.strokeStyle = "#d4c9a0"; context.lineWidth = 1; context.stroke();
		}
		for (const point of map.points.slice(0, 80)) {
			if (!Number.isFinite(point.x) || !Number.isFinite(point.z)) continue;
			const x = projectX(point.x), y = projectZ(point.z);
			if (x < 7 || x > 249 || y < 7 || y > 249) continue;
			if (point.id === "sella" || /(?:ruun|merchant|blacksmith|healer|shaman|npc)/.test(point.id)) {
				context.fillStyle = "#f3d788"; context.strokeStyle = "#342914"; context.lineWidth = 2;
				context.beginPath(); context.moveTo(x, y - 6); context.lineTo(x + 5, y);
				context.lineTo(x, y + 6); context.lineTo(x - 5, y); context.closePath(); context.fill(); context.stroke();
			} else dot(context, x, y, /^windmark_/.test(point.id) ? "#b0e5ec" : point.id === "south_trail_marker" ? "#d9b8ed" : /(?:hunt|combat)/.test(point.id) ? "#eba99a" : "#d6d9b6");
		}
		const px = Math.max(11, Math.min(245, projectX(playerX))), py = Math.max(11, Math.min(245, projectZ(playerZ)));
		if (preview && map.showPreviewParty) for (const [dx, dz] of [[11, -5], [-16, 7], [19, 16]]) dot(context, px + dx, py + dz, "#e0a2b4", 3);
		context.strokeStyle = "rgba(187,243,201,.55)"; context.lineWidth = 1.5;
		context.beginPath(); context.arc(px, py, 12, 0, Math.PI * 2); context.stroke();
		context.fillStyle = "#b5f4c5"; context.strokeStyle = "#102f20"; context.lineWidth = 2;
		context.beginPath(); context.moveTo(px, py - 9); context.lineTo(px + 6, py + 6);
		context.lineTo(px, py + 3); context.lineTo(px - 6, py + 6); context.closePath(); context.fill(); context.stroke();
		context.restore();
	});
</script>

<div class="minimap-card" data-map-shape="rounded-rectangle">
	<div class="minimap-heading">
		<svg viewBox="0 0 18 18" aria-hidden="true"><path d="m9 1 3 5 5 3-5 3-3 5-3-5-5-3 5-3Z"/><path d="M9 5v8M5 9h8"/></svg>
		<span title={areaName}>{areaName}</span><kbd aria-hidden="true">M</kbd>
	</div>
	<div class="minimap-viewport">
		<button type="button" class="minimap-open" aria-label={label} title={label} onclick={onopen}>
			<canvas bind:this={canvas} id="minimap" class="minimap-chart" width="256" height="256" aria-hidden="true"></canvas>
			<span class="minimap-north" aria-hidden="true"><i></i>N</span>
			<span class="minimap-scale" aria-hidden="true"><i></i>{scaleLabel}</span>
			{#if preview && model.showPreviewParty}<span class="minimap-preview">{th ? "ตัวอย่าง" : "Preview"}</span>{/if}
		</button>
		<button type="button" class="minimap-zoom" aria-label={th ? `ระดับซูม ${zoom} เท่า กดเพื่อเปลี่ยนระดับ` : `Zoom ${zoom} times; change map scale`} title={th ? "เปลี่ยนระดับซูม" : "Change map scale"} onclick={() => zoom = zoom === 4 ? 1 : zoom * 2}>
			<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8" cy="8" r="5"/><path d="m12 12 5 5M8 5v6M5 8h6"/></svg><span>{zoom}×</span>
		</button>
	</div>
	<div class="minimap-footer">
		<span class="minimap-position"><i aria-hidden="true"></i>{th ? "ตัวคุณ" : "You"}</span>
		<span id="map-coords" class="minimap-coordinates" aria-label={th ? "ตำแหน่ง X และ Z" : "X and Z coordinates"}>{playerX.toFixed(0)}<span aria-hidden="true"> / </span>{playerZ.toFixed(0)}</span>
	</div>
</div>

<style>
	:global(.map-panel:has(.minimap-card)) { width: 204px; padding: 0; border: 0; border-radius: 14px; background: transparent; box-shadow: none; backdrop-filter: none; }
	.minimap-card { color: #ead9b2; padding: 6px; border: 1px solid #8b754d; border-radius: 14px; background: #24231f; box-shadow: 0 4px 12px #090c0b70, inset 0 1px 0 #c6b28159, inset 0 -1px 0 #090c0b; }
	.minimap-heading { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 3px 4px 7px; }
	.minimap-heading > svg { flex: 0 0 14px; width: 14px; height: 14px; fill: none; stroke: #c4a267; stroke-width: 1; }
	.minimap-heading > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; line-height: 1.5; font-weight: 600; }
	.minimap-heading kbd { flex: 0 0 auto; margin-left: auto; color: #d3c198; font: inherit; font-size: 9px; border: 1px solid #88724d; border-radius: 3px; padding: 0 3px; }
	.minimap-viewport { position: relative; border-radius: 9px; overflow: hidden; border: 1px solid #b1935f; }
	.minimap-open { display: block; width: 100%; aspect-ratio: 1; min-width: 44px; min-height: 44px; padding: 0; margin: 0; border: 0; border-radius: 8px; background: #2b3c2e; cursor: pointer; touch-action: manipulation; }
	#minimap.minimap-chart { display: block; width: 100%; height: auto; margin: 0; border: 0; border-radius: 8px; background: #2b3c2e; }
	.minimap-open:hover { filter: brightness(1.08); }
	.minimap-open:focus-visible { outline: 3px solid #ffdc82; outline-offset: -4px; }
	.minimap-north { position: absolute; top: 6px; left: 50%; transform: translateX(-50%); display: grid; justify-items: center; gap: 2px; font-size: 10px; font-weight: 700; color: #f6e5b8; text-shadow: 0 1px 2px #162016; pointer-events: none; }
	.minimap-north i { width: 0; height: 0; border-left: 3px solid transparent; border-right: 3px solid transparent; border-bottom: 5px solid #d5bc82; }
	.minimap-scale { position: absolute; left: 8px; bottom: 8px; width: 21.875%; display: grid; gap: 3px; font-size: 9px; line-height: 1; font-variant-numeric: tabular-nums; color: #eee4c8; text-shadow: 0 1px 2px #102019; pointer-events: none; }
	.minimap-scale i { width: 100%; height: 4px; border: 1px solid #ddd1af; border-top: 0; }
	.minimap-preview { position: absolute; left: 8px; top: 8px; color: #dfd7ba; font-size: 9px; text-shadow: 0 1px 2px #0d1911; pointer-events: none; }
	.minimap-zoom { position: absolute; right: 0; bottom: 0; min-width: 44px; min-height: 44px; display: flex; justify-content: center; align-items: center; gap: 3px; padding: 2px 4px; border: 0; border-top: 1px solid #9e895264; border-left: 1px solid #9e895264; border-radius: 8px 0 0 0; background: #1b251fe8; color: #ecdfbc; cursor: pointer; touch-action: manipulation; }
	.minimap-zoom:hover { background: #354035; }
	.minimap-zoom:focus-visible { outline: 2px solid #ffdc82; outline-offset: -3px; }
	.minimap-zoom svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.5; }
	.minimap-zoom span { font-size: 10px; font-variant-numeric: tabular-nums; }
	.minimap-footer { display: flex; justify-content: space-between; align-items: center; gap: 5px; padding: 7px 4px 2px; color: #e3d3af; font-size: 10px; line-height: 1.3; }
	.minimap-position { display: flex; align-items: center; gap: 4px; }
	.minimap-position i { width: 0; height: 0; border-left: 3px solid transparent; border-right: 3px solid transparent; border-bottom: 6px solid #b5f4c5; }
	.minimap-coordinates { white-space: nowrap; font-variant-numeric: tabular-nums; }
	.minimap-coordinates > span { color: #b8a784; }
	@media (max-width: 1200px) { :global(.map-panel:has(.minimap-card)) { width: 172px; } }
	@media (max-width: 900px) {
		:global(.right-rail:has(.minimap-card)) { top: max(82px, calc(env(safe-area-inset-top) + 72px)); }
		:global(.map-panel:has(.minimap-card)) { width: 142px; }
		.minimap-heading { gap: 4px; padding-bottom: 5px; }
		.minimap-heading > span, .minimap-footer { font-size: 9px; }
		.minimap-heading kbd, .minimap-preview { display: none; }
		.minimap-north { top: 4px; font-size: 9px; }
		.minimap-zoom svg { display: none; }
	}
	@media (max-width: 540px), (max-width: 900px) and (max-height: 420px) {
		:global(.map-panel:has(.minimap-card)) { width: 116px; }
		.minimap-card { padding: 4px; border-radius: 11px; }
		.minimap-heading > svg, .minimap-position { display: none; }
		.minimap-heading { padding: 2px 3px 4px; }
		.minimap-footer { justify-content: center; padding: 5px 2px 1px; }
		.minimap-scale { left: 5px; bottom: 5px; font-size: 8px; }
	}
	@media (max-width: 900px) and (max-height: 420px) {
		:global(.map-panel:has(.minimap-card)) { width: 98px; }
		.minimap-viewport { overflow: visible; }
		.minimap-zoom { right: -8px; bottom: -9px; border: 1px solid #9e8952; border-radius: 7px; }
		.minimap-footer { display: none; }
	}
	@media (max-width: 900px) and (max-height: 360px) {
		:global(.map-panel:has(.minimap-card)) { width: 96px; }
		.minimap-heading, .minimap-footer, .minimap-north, .minimap-scale { display: none; }
	}
</style>
