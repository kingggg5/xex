<script lang="ts">
	import { onMount } from "svelte";
	import SkillIcon from "./SkillIcon.svelte";
	import ItemIcon from "./ItemIcon.svelte";
	import EquipmentCopy from "./EquipmentCopy.svelte";
	import "./character-inventory.css";
	import type { InventorySnapshot, UiCommands } from "./types";
	let { model, commands, selectedInstanceId: sharedSelectedId, onselect }: { model: InventorySnapshot; commands: Pick<UiCommands,"inventoryAction"|"moveItemInstance">; selectedInstanceId?: string; onselect?: (instanceId: string) => void } = $props();
	let now = $state(0);
	const th = $derived(model.language === "th");
	const remaining = $derived(Math.max(0, Math.ceil((model.potionReadyAtMs - now) / 1000)));
	let visible = $state(true);
	let localSelectedId = $state("");
	const selectedInstanceId = $derived(sharedSelectedId ?? localSelectedId);
	const selectedInstance = $derived(model.instances.find(row=>row.instanceId===selectedInstanceId)??null);
	const destination = $derived(selectedInstance?.location==="bag" ? selectedInstance.equipSlot : selectedInstance ? "bag" : null);
	function selectCopy(instanceId: string): void { localSelectedId = instanceId; onselect?.(instanceId); }
	function moveInstance():void {
		const selected=selectedInstance,to=destination;
		if(selected&&to&&model.revision!==null&&model.online&&model.instanceMovesSupported)commands.moveItemInstance(selected.instanceId,model.revision,to);
	}
	onMount(() => {
		const changed = () => { visible = !document.hidden; };
		changed();
		document.addEventListener("visibilitychange", changed);
		return () => document.removeEventListener("visibilitychange", changed);
	});
	$effect(() => {
		const readyAt = model.potionReadyAtMs;
		if (!visible) return;
		let timer = 0;
		const refresh = () => {
			const current = performance.now();
			now = current;
			const left = readyAt - current;
			if (left > 0) timer = window.setTimeout(refresh, Math.min(1000, left));
		};
		refresh();
		return () => window.clearTimeout(timer);
	});
</script>

<div class="inventory-view character-inventory" data-ui-component="inventory">
	{#if !model.online}<p class="econ-note">{th ? "ขาดการเชื่อมต่อ · แสดงรายการล่าสุดที่ได้รับ · ใช้งานไม่ได้ชั่วคราว" : "Offline · last received items · actions paused"}</p>{/if}
	{#if model.loading}
		<p role="status">{th ? "กำลังโหลดกระเป๋าจากเซิร์ฟเวอร์…" : "Loading your field bag…"}</p>
	{:else if model.items.length === 0}
		<p class="empty-state">{th ? "กระเป๋ายังว่าง" : "Your field bag is empty."}</p>
	{:else}
		<ul class="inventory-grid" aria-label={th ? "ไอเท็มในกระเป๋า" : "Bag items"}>
			{#each model.items as entry (entry.slot)}
				{@const copies = model.instances.filter(row => row.id === entry.id)}
				<li class="inventory-cell" data-item={entry.id}>
					<div class="inventory-item-head"><span class="inventory-icon" aria-hidden="true">{#if entry.isPotion}<SkillIcon potion />{:else}<ItemIcon kind={copies[0]?.equipSlot ?? (entry.action === "open" ? "box" : "item")} item={entry.id} />{/if}</span><span class="inventory-item-title"><b class="item-name">{entry.label}</b><small>{th ? "รายการ" : "Entry"} {entry.slot + 1}</small></span></div><span class="item-count">{entry.count} ×</span>
					{#if copies.length > 0}<button type="button" class="inventory-copy-shortcut" onclick={() => selectCopy(copies.find(copy => copy.location === "bag")?.instanceId ?? copies[0].instanceId)}>{th ? "เลือกอุปกรณ์ชิ้นนี้" : "Select an equipment copy"}</button>{/if}
					{#if entry.action}
						<button type="button" class="social-action" disabled={!model.online || entry.count <= 0 || (entry.isPotion && (model.potionPending || model.potionUnavailable || remaining > 0))} onclick={() => commands.inventoryAction(entry.id, entry.action!)}>
							{#if entry.isPotion && model.potionPending}{th ? "กำลังใช้…" : "Using…"}
							{:else if entry.isPotion && remaining > 0}{th ? `พักฟื้น ${remaining} วิ` : `Ready in ${remaining}s`}
							{:else if entry.action === "equip"}{th ? "สวม" : "Equip"}
							{:else if entry.action === "open"}{th ? "เปิด" : "Open"}
							{:else}{th ? "ใช้" : "Use"}{/if}
						</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
	{#if !model.loading&&model.instances.length>0}
		<section class="instance-picker" aria-labelledby="inventory-instance-title">
			<h3 id="inventory-instance-title">{th?"อุปกรณ์แต่ละชิ้น":"Individual equipment"}</h3>
			<p class="character-note">{th ? "เลือกชิ้นที่ต้องการสวม หรือเลือกชิ้นที่สวมอยู่เพื่อถอด" : "Select a copy to equip, or an equipped copy to store in your bag."}</p>
			<ul class="equipment-copy-list">{#each model.instances as instance (instance.instanceId)}<li><EquipmentCopy item={instance.id} label={instance.label} instanceId={instance.instanceId} refine={instance.refine} location={instance.location} kind={instance.equipSlot} {th} selected={instance.instanceId === selectedInstance?.instanceId} onselect={() => selectCopy(instance.instanceId)} /></li>{/each}</ul>
			{#if selectedInstance}<div class="equipment-detail"><h4>{selectedInstance.label} +{selectedInstance.refine}</h4><p class="equipment-id">{th ? "รหัสชิ้น" : "Copy ID"}: {selectedInstance.instanceId}</p><button type="button" class="social-action" data-move-item-instance disabled={!destination||model.revision===null||!model.online||!model.instanceMovesSupported} onclick={moveInstance}>{destination==="bag"?(th?"ถอดลงกระเป๋า":"Store in bag"):(th?"สวมชิ้นที่เลือก":"Equip selected copy")}</button>{#if selectedInstance.location==="bag"&&!selectedInstance.equipSlot}<p class="instance-note">{th?"กำลังรอประเภทอุปกรณ์จากข้อมูลเกม":"Waiting for the equipment destination from game data."}</p>{/if}</div>{:else}<p class="character-note">{th ? "ยังไม่ได้เลือกอุปกรณ์" : "No equipment selected"}</p>{/if}
			{#if !model.instanceMovesSupported}<p class="instance-note">{th?"กำลังรอระบบย้ายอุปกรณ์จากเซิร์ฟเวอร์":"Equipment moves await server integration."}</p>{/if}
		</section>
	{/if}
	{#if model.pouch.length > 0}
		<h3>{th ? "วัสดุ" : "Materials"}</h3>
		<dl class="pouch-list">{#each model.pouch as item (item.id)}<div><dt><ItemIcon kind="material" /> {item.label}</dt><dd>{item.count}</dd></div>{/each}</dl>
	{/if}
</div>

<style>
	.inventory-view { display: grid; gap: 14px; }
	.instance-picker { display: grid; gap: 10px; padding-top: 14px; border-top: 1px solid #465b6b; }
	.instance-note { margin: 0; line-height: 1.5; font-size: 13px; color: #c9e2e9; }
	.inventory-grid { margin: 0; padding: 0; list-style: none; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; align-content: start; grid-auto-rows: minmax(142px, auto); }
	.inventory-item-head { display: flex; align-items: center; gap: 10px; }
	.inventory-icon { display: grid; place-items: center; width: 42px; height: 42px; flex: 0 0 42px; border: 1px solid #7c92aa; background: #071221; color: #abdafa; }
	.inventory-icon :global(svg) { width: 34px; height: 34px; }
	.inventory-item-title { display: grid; gap: 3px; min-width: 0; }
	.inventory-item-title small { font-size: 11px; color: #c3cbda; }
	.inventory-cell { min-height: 112px; gap: 6px; padding: 12px; align-content: start; }
	.item-name { color: #f3ddb0; font-size: 14px; line-height: 1.4; overflow-wrap: anywhere; }
	.item-count { color: #d5d8ce; font-size: 13px; font-variant-numeric: tabular-nums; }
	button { min-height: 44px; width: 100%; font-size: 14px; }
	button:focus-visible { outline: 3px solid #f3d993; outline-offset: 3px; }
	.empty-state { padding: 24px 0; color: #d5d8ce; }
	h3 { margin: 8px 0 0; font-size: 16px; color: #f3ddb0; }
	.pouch-list { margin: 0; display: grid; gap: 8px; }
	.pouch-list div { display: flex; gap: 16px; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(230,222,200,.15); }
	dd { margin: 0; font-variant-numeric: tabular-nums; }
	@media (max-width: 767px) { .inventory-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .item-name, button { font-size: 16px; } }
</style>
