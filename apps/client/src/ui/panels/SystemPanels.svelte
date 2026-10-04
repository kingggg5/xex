<script lang="ts">
	import CharacterPanel from "./CharacterPanel.svelte";
	import SkillsPanel from "./SkillsPanel.svelte";
	import PartyPanel from "./PartyPanel.svelte";
	import NpcDialogue from "./NpcDialogue.svelte";
	import FriendsPanel from "./FriendsPanel.svelte";
	import GroupPanel from "./GroupPanel.svelte";
	import TowerPanel from "./TowerPanel.svelte";
	import SettingsPanel from "./SettingsPanel.svelte";
	import WorldMapPanel from "./WorldMapPanel.svelte";
	import AdventureMenu from "./AdventureMenu.svelte";
	import JournalPanel from "./JournalPanel.svelte";
	import UnavailablePanel from "./UnavailablePanel.svelte";
	import type { PanelCommands, PanelSnapshot } from "../panel-types";
	import { DEFAULT_COMBAT_READABILITY, type CombatReadability, type PanelResourceState } from "../combat-model";
	let { name, model, commands, readability=DEFAULT_COMBAT_READABILITY, readabilitySupported=false, onReadabilityChanged=()=>{}, roomsResource,roomsRefreshAvailable=false,refreshRooms=()=>{} }: { name: string; model: PanelSnapshot; commands: PanelCommands; readability?:CombatReadability; readabilitySupported?:boolean; onReadabilityChanged?:(value:CombatReadability)=>void;roomsResource?:PanelResourceState;roomsRefreshAvailable?:boolean;refreshRooms?:()=>void } = $props();
</script>

<div class="system-panel">
	{#if name === "character"}<CharacterPanel {model} {commands} />
	{:else if name === "skills"}<SkillsPanel {model} />
	{:else if name === "party"}<PartyPanel {model} {commands} />
	{:else if name === "dialogue"}<NpcDialogue {model} {commands} />
	{:else if name === "friends"}<FriendsPanel {model} {commands} />
	{:else if name === "group"}<GroupPanel {model} {commands} />
	{:else if name === "tower"}<TowerPanel {model} {commands} />
	{:else if name === "settings"}<SettingsPanel {model} {commands} {readability} {readabilitySupported} {onReadabilityChanged} {roomsResource} {roomsRefreshAvailable} {refreshRooms} />
	{:else if name === "map"}<WorldMapPanel {model} />
	{:else if name === "menu"}<AdventureMenu {model} {commands} />
	{:else if name === "collection"}<JournalPanel {model} />
	{:else}<UnavailablePanel {model} {name} />{/if}
</div>

<style>
	/* Preserve the established field-window palette; task state stays easy to scan. */
	.system-panel { display: grid; gap: 12px; min-width: 0; color: #eee9da; line-height: 1.5; }
	.system-panel :global(p), .system-panel :global(dl), .system-panel :global(ul) { margin: 0; }
	.system-panel :global(h3) { margin: 8px 0 0; color: #f3ddb0; font-size: 16px; font-weight: 650; }
	.system-panel :global(button), .system-panel :global(input), .system-panel :global(select) { font: inherit; }
	.system-panel :global(button) { min-height: 44px; border: 1px solid rgba(239,213,158,.4); border-radius: 6px; padding: 8px 12px; color: #f3ddb0; background: #203139; cursor: pointer; }
	.system-panel :global(button:hover:enabled) { background: #30434a; border-color: #d5b36b; }
	.system-panel :global(button:disabled) { cursor: default; opacity: .5; }
	.system-panel :global(button:focus-visible), .system-panel :global(input:focus-visible), .system-panel :global(select:focus-visible) { outline: 3px solid #f3d993; outline-offset: 3px; }
	.system-panel :global(input:not([type="range"]):not([type="checkbox"])), .system-panel :global(select) { min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid rgba(239,213,158,.45); border-radius: 6px; color: #eee9da; background: #17242a; }
	.system-panel :global(input::placeholder) { color: #b8bcb4; }
	.system-panel :global(small), .system-panel :global(.econ-note) { color: #c6cec5; font-size: 13px; }
	.system-panel :global(.dialogue-choices), .system-panel :global(.social-rows) { display: grid; gap: 8px; }
	.system-panel :global(.dialogue-line) { white-space: pre-line; overflow-wrap: anywhere; }
	.system-panel :global(.social-form) { display: flex; gap: 8px; }
	.system-panel :global(.social-form input) { flex: 1; }
	.system-panel :global(.social-row) { display: flex; align-items: center; gap: 9px; padding: 8px 0; border-bottom: 1px solid rgba(239,213,158,.12); }
	.system-panel :global(.social-label) { display: grid; flex: 1; min-width: 0; overflow-wrap: anywhere; }
	.system-panel :global(.social-where) { color: #c6cec5; font-size: 13px; }
	.system-panel :global(.social-dot) { width: 8px; height: 8px; border-radius: 50%; background: #8b969a; flex: 0 0 8px; }
	.system-panel :global(.is-online .social-dot) { background: #a8d99b; }
	.system-panel :global(.social-remove) { min-width: 44px; padding: 0; font-size: 22px; }
	.system-panel :global(.form-error) { color: #f5b4a2; font-size: 13px; }
	.system-panel :global(.visually-hidden) { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
	.system-panel :global(.character-identity) { display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px; }
	.system-panel :global(.character-identity strong) { font-size: 20px; }
	.system-panel :global(.character-details) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px 20px; }
	.system-panel :global(.character-details > div), .system-panel :global(.skill-list > div) { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 5px 10px; }
	.system-panel :global(dt) { color: #c6cec5; }
	.system-panel :global(dd) { margin: 0; font-variant-numeric: tabular-nums; }
	.system-panel :global(.attribute-grid) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 12px; }
	.system-panel :global(.attribute-row) { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px; background: #1d2b31; border-radius: 6px; }
	.system-panel :global(.attribute-row small), .system-panel :global(.equipment-row small) { display: block; }
	.system-panel :global(.small-action) { min-width: 44px; padding: 4px; }
	.system-panel :global(.available-points) { color: #f3d993; font-weight: 650; }
	.system-panel :global(.equipment-row) { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(239,213,158,.12); }
	.system-panel :global(.equipment-row > div) { min-width: 0; overflow-wrap: anywhere; }
	.system-panel :global(.skill-list), .system-panel :global(.member-list) { display: grid; gap: 10px; padding: 0; list-style: none; }
	.system-panel :global(.member-list li) { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
	.system-panel :global(kbd) { padding: 2px 7px; border: 1px solid #8a8067; border-radius: 4px; color: #f3ddb0; font: inherit; }
	.system-panel :global(.settings-row) { display: flex; align-items: center; gap: 12px; min-height: 44px; }
	.system-panel :global(.settings-row label) { flex: 1; min-width: 0; }
	.system-panel :global(.settings-row input[type="range"]) { width: min(160px, 32%); accent-color: #dbbb70; }
	.system-panel :global(.settings-row input[type="checkbox"]) { width: 20px; height: 20px; accent-color: #dbbb70; }
	.system-panel :global(.settings-row:has(input[type="checkbox"]) label) { display: flex; align-items: center; min-height: 44px; cursor: pointer; }
	.system-panel :global(.settings-value) { width: 42px; font-size: 13px; text-align: right; font-variant-numeric: tabular-nums; }
	.system-panel :global(.settings-summary) { color: #c6cec5; font-size: 13px; }
	.system-panel :global(.channels-section) { display: grid; gap: 12px; margin-top: 8px; border-top: 1px solid rgba(239,213,158,.25); padding-top: 12px; }
	.system-panel :global(.channel-picker) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
	.system-panel :global(.channel-row) { display: flex; align-items: center; justify-content: space-between; gap: 8px; text-align: left; }
	.system-panel :global(.channel-auto), .system-panel :global(.channel-picker-note) { grid-column: 1 / -1; }
	.system-panel :global(.channel-right) { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 4px; }
	.system-panel :global(.room-full-badge) { color: #f5b4a2; font-size: 10px; }
	.system-panel :global(.is-current) { border-color: #dfc482; background: #304038; }
	.system-panel :global(.tower-stats) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
	.system-panel :global(.tower-stat) { padding: 12px; background: #1d2b31; border-radius: 6px; }
	.system-panel :global(.tower-stat dd) { font-size: 22px; color: #f3ddb0; }
	.system-panel :global(.tower-stat dt) { font-size: 13px; }
	.system-panel :global(.adventure-menu-grid) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
	.system-panel :global(.menu-shortcut) { text-align: left; }
	.system-panel :global(.world-map-layout) { display: grid; grid-template-columns: minmax(0, 1fr) minmax(140px, .45fr); gap: 18px; }
	.system-panel :global(.world-map-figure) { margin: 0; min-width: 0; }
	.system-panel :global(.world-map-svg) { width: 100%; height: auto; display: block; }
	.system-panel :global(.map-side), .system-panel :global(.map-members) { display: grid; align-content: start; gap: 8px; }
	.system-panel :global(.map-side h3) { margin-top: 12px; }
	.system-panel :global(.map-members) { font-size: 13px; color: #c6cec5; overflow-wrap: anywhere; }
	.system-panel :global(.map-legend) { display: grid; gap: 6px; list-style: none; padding: 0; font-size: 13px; }
	.system-panel :global(.map-legend li) { display: flex; align-items: center; gap: 8px; }
	.system-panel :global(.map-legend i) { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
	.system-panel :global(.map-tower-badge) { color: #f3d993; font-size: 13px; }
	@media (max-width: 480px) {
		.system-panel :global(.attribute-grid), .system-panel :global(.character-details), .system-panel :global(.world-map-layout) { grid-template-columns: 1fr; }
		.system-panel :global(.settings-row select) { max-width: 52%; }
		.system-panel :global(.social-row) { flex-wrap: wrap; }
		.system-panel :global(.social-where) { max-width: 45%; }
	}
</style>
