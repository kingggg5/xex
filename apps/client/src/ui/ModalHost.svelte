<script lang="ts">
	import CommunityPanel from "./CommunityPanel.svelte";
	import Inventory from "./Inventory.svelte";
	import Shop from "./Shop.svelte";
	import SystemPanels from "./panels/SystemPanels.svelte";
	import { floatingPanel, trapDialogKey } from "./floating-panel";
	import type { UiSnapshot, UiCommands } from "./types";
	import PanelDataGate from "./PanelDataGate.svelte";
	import { resourceKeysForPanel } from "./combat-model";
	import type { ResourceKey } from "./combat-model";
	let { view, commands }: { view: UiSnapshot; commands: UiCommands } = $props();
	let dialog: HTMLElement;
	let handle: HTMLButtonElement | undefined = $state();
	const resourceKeys: ResourceKey[] = $derived(view.modal === "character" || view.modal === "bag" ? ["character", "inventory"] : resourceKeysForPanel(view.modal));
</script>

<div class="game-modal panel svelte-modal" class:is-map={view.modal === "map"} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1" bind:this={dialog} use:floatingPanel={{ handle, resetKey: view.modal }} onkeydown={(event) => trapDialogKey(event, dialog, commands.closeModal)}>
	<header class="modal-header">
		<button bind:this={handle} class="move-window" type="button" aria-label={view.language === "th" ? "เลื่อนหน้าต่างด้วยการลากหรือปุ่มลูกศร" : "Move window by dragging or using arrow keys"} title={view.language === "th" ? "ลากเพื่อย้าย · Home เพื่อคืนตำแหน่ง" : "Drag to move · Home to center"}><span aria-hidden="true">⠿</span></button>
		<div class="modal-heading"><p class="panel-kicker">XEXORIA · FRONTIER</p><h2 id="modal-title">{view.title}</h2></div>
		<button class="modal-close" id="modal-close" type="button" aria-label={view.language === "th" ? "ปิดหน้าต่าง" : "Close dialog"} onclick={commands.closeModal}>×</button>
	</header>
	<div class="modal-content" id="modal-content">
		<PanelDataGate states={resourceKeys.map(key=>view.resources[key])} transactions={view.transactions.filter(row=>resourceKeys.includes(row.resource))} th={view.language==="th"} online={view.online} canRetry={view.resourceRefreshSupported||resourceKeys.includes("shop")||resourceKeys.includes("community")} retry={()=>resourceKeys.forEach(key=>commands.refreshResource(key))}>
		{#if view.modal === "bag"}<Inventory model={view.inventory} {commands} selectedInstanceId={view.panels.selectedInventoryInstanceId} onselect={commands.panels.selectInventoryInstance} />
		{:else if view.modal === "store"}<Shop model={view.shop} {commands} />
		{:else if ["trade","battlepass","topup"].includes(view.modal??" ")}<CommunityPanel {view} {commands}/>
		{:else if view.modal}<SystemPanels name={view.modal} model={view.panels} commands={commands.panels} readability={view.readability} readabilitySupported={view.readabilitySupported} onReadabilityChanged={commands.readabilityChanged} roomsResource={view.resources.rooms} roomsRefreshAvailable={view.resourceRefreshSupported} refreshRooms={()=>commands.refreshResource("rooms")} />{/if}
		</PanelDataGate>
	</div>
</div>

<style>
	.game-modal.svelte-modal { display: grid; grid-template-rows: auto minmax(0, 1fr); width: min(640px, calc(100vw - 32px)); max-height: min(86dvh, 760px); padding: 0; overflow: hidden; background: rgba(17,26,31,.98); transform: translate(var(--svelte-offset-x, 0px), var(--svelte-offset-y, 0px)); }
	.game-modal.svelte-modal.is-map { width: min(900px, calc(100vw - 32px)); }
	.modal-header { display: flex; align-items: center; gap: 10px; padding: 16px 18px; border-bottom: 1px solid rgba(239,213,158,.25); }
	.modal-heading { flex: 1; min-width: 0; }
	.modal-heading .panel-kicker { margin: 0 0 3px; }
	.modal-heading h2 { margin: 0; font-size: 25px; overflow-wrap: anywhere; }
	.move-window { min-width: 44px; min-height: 44px; border: 0; color: #d8c99e; background: transparent; font-size: 24px; cursor: grab; touch-action: none; }
	.move-window:active { cursor: grabbing; }
	.modal-close { position: static; flex: 0 0 44px; width: 44px; height: 44px; }
	.modal-content { padding: 18px; overflow: auto; overscroll-behavior: contain; scrollbar-width: thin; }
	button:focus-visible { outline: 3px solid #f3d993; outline-offset: 3px; }
	:global(.svelte-modal .settings-choice select) { min-width: 160px; min-height: 44px; padding: 8px 10px; border: 1px solid rgba(239,213,158,.45); border-radius: 7px; color: #f3ddb0; background: #17242a; font: inherit; }
	:global(.svelte-modal .settings-summary) { margin: 0; color: #d5d8ce; font-size: 13px; line-height: 1.5; }
	:global(.svelte-modal .settings-row:has(input[type="checkbox"]) label) { display: flex; align-items: center; min-height: 44px; flex: 1; cursor: pointer; }
	@media (max-width: 767px), (pointer: coarse) and (max-width: 900px) {
		.game-modal.svelte-modal, .game-modal.svelte-modal.is-map { position: fixed; inset: 0; width: 100vw; height: 100dvh; max-height: 100dvh; border-radius: 0; transform: none; }
		.modal-header { padding: max(12px, env(safe-area-inset-top)) max(14px, env(safe-area-inset-right)) 12px max(14px, env(safe-area-inset-left)); }
		.move-window { display: none; }
		.modal-content { padding: 16px max(16px, env(safe-area-inset-right)) max(20px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left)); font-size: 16px; }
		:global(.svelte-modal .dialogue-choice), :global(.svelte-modal .social-action), :global(.svelte-modal .settings-row select) { min-height: 44px; }
	}
</style>
