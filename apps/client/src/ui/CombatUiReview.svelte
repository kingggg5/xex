<script lang="ts">
	import CombatOverlay from "./CombatOverlay.svelte";
	import PanelDataGate from "./PanelDataGate.svelte";
	import Inventory from "./Inventory.svelte";
	import type {InventorySnapshot} from "./types";
	import type { CombatView, DeathView, PanelResourceState, UiTransaction } from "./combat-model";
	let { mode="combat",view,death,states=[],transactions=[],language="en",online=true,returnToTown=()=>{},refresh=()=>{},inventory }: { mode?:"combat"|"panel"|"inventory"; view:CombatView; death:DeathView;states?:PanelResourceState[];transactions?:UiTransaction[];language?:"th"|"en";online?:boolean;returnToTown?:()=>void;refresh?:()=>void;inventory?:InventorySnapshot }=$props();
</script>
{#if mode==="panel"}
	<PanelDataGate {states} {transactions} th={language==="th"} {online} retry={refresh} canRetry={true}>
		<p data-fixture-content>Server-provided fixture value: 0</p><button type="button" data-fixture-mutation>Fixture mutation</button>
	</PanelDataGate>
{:else if mode==="inventory"&&inventory}<Inventory model={inventory} commands={{inventoryAction(){},moveItemInstance(){}}}/>
{:else}<CombatOverlay {view} {death} {language} {returnToTown}/>{/if}
