<script lang="ts">
	import ItemIcon from "./ItemIcon.svelte";
	import type { EquipmentSlot } from "./panel-types";
	let { item, label, instanceId, refine, location, kind, th, selected = false, onselect }: {
		item: string; label: string; instanceId?: string; refine: number;
		location: "bag" | EquipmentSlot; kind?: EquipmentSlot | null; th: boolean;
		selected?: boolean; onselect?: () => void;
	} = $props();
	const locationLabel = $derived(location === "bag" ? (th ? "ในกระเป๋า" : "In bag") : location === "weapon" ? (th ? "อาวุธที่สวม" : "Equipped weapon") : (th ? "เกราะที่สวม" : "Equipped armor"));
</script>

<button type="button" class="equipment-copy" class:is-selected={selected} class:is-equipped={location !== "bag"} aria-pressed={selected} disabled={!onselect} onclick={onselect} data-instance-id={instanceId}>
	<span class="equipment-copy-icon"><ItemIcon kind={kind ?? (location === "bag" ? "item" : location)} {item} /></span>
	<span class="equipment-copy-text"><strong>{label} <span class="equipment-refine">+{refine}</span></strong><span class="equipment-location">{locationLabel}</span>{#if instanceId}<small title={instanceId}>{th ? "ชิ้น" : "Copy"} · {instanceId.slice(-8)}</small>{/if}</span>
	{#if selected}<span class="equipment-selected"><svg class="equipment-selected-mark" viewBox="0 0 16 16" aria-hidden="true"><path d="m3 8 3 3 7-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg><span class="equipment-selected-label">{th ? "เลือกแล้ว" : "Selected"}</span></span>{/if}
</button>
