<script lang="ts">
	import type { PanelCommands, PanelSnapshot } from "../panel-types";
	import type { PanelResourceState } from "../combat-model";
	import PanelDataGate from "../PanelDataGate.svelte";
	let { model, commands, resource,refreshAvailable=false,refresh=()=>{} }: { model: PanelSnapshot; commands: PanelCommands;resource?:PanelResourceState;refreshAvailable?:boolean;refresh?:()=>void } = $props();
	let th = $derived(model.language === "th");
</script>

<section class="channels-section" aria-labelledby="rooms-heading">
	<h3 id="rooms-heading">{th ? "ช่องทาง · ห้องเกม" : "Channels · Game rooms"}</h3>
	<PanelDataGate states={resource?[resource]:[]} transactions={[]} {th} online={model.online} canRetry={refreshAvailable} retry={refresh}>
	<div class="channel-picker">
		<button type="button" class="channel-row channel-auto" class:is-current={model.rooms.current === null} aria-pressed={model.rooms.current === null} disabled={!model.online} onclick={() => commands.channelPicked(null)}><strong>{th ? "อัตโนมัติ" : "Auto"}</strong><span class="channel-right"><small>{th ? "ให้เซิร์ฟเวอร์เลือกห้อง" : "Let the server choose"}</small></span></button>
		{#if model.rooms.status === "loading"}<p class="channel-picker-note" role="status">{th ? "กำลังโหลดรายชื่อห้อง…" : "Loading rooms…"}</p>
		{:else if model.rooms.status === "unavailable"}<p class="channel-picker-note">{th ? "โหลดรายชื่อห้องไม่ได้ กรุณาตรวจข้อมูลใหม่" : "The room list could not be loaded. Refresh state."}</p>
		{:else if model.rooms.rooms.length === 0}<p class="channel-picker-note">{th ? "โหลดแล้ว · ยังไม่มีห้องในรายการ" : "Loaded · no rooms are listed."}</p>
		{:else}{#each model.rooms.rooms as room}<button type="button" class="channel-row" class:is-current={model.rooms.current === room.channel} aria-pressed={model.rooms.current === room.channel} disabled={!model.online||room.players>=room.capacity} onclick={() => commands.channelPicked(room.channel)}><strong>{th ? `ห้อง ${room.channel + 1}` : `Room ${room.channel + 1}`}</strong><span class="channel-right"><small>{room.players}/{room.capacity}</small>{#if room.players >= room.capacity}<span class="room-full-badge">{th ? "เต็ม" : "FULL"}</span>{/if}</span></button>{/each}{/if}
	</div>
	<p class="econ-note">{th ? "เมื่อเลือกห้อง ระบบจะเชื่อมต่อใหม่เข้าช่องทางนั้นให้" : "Picking a room reconnects you into that channel."}</p>
	</PanelDataGate>
</section>
