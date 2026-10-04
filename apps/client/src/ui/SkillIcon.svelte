<script lang="ts">
  import type { HudAction, HudAbility } from "./hud-types";
  import mageBasic from "../assets/ui/mage-pilot/basic.svg";
  import mageLance from "../assets/ui/mage-pilot/lance.svg";
  let { action, art, potion = false }: { action?: HudAction; art?: HudAbility["art"]; potion?: boolean } = $props();
</script>
{#if !potion && (art === "mage-basic-art" || art === "mage-lance-art")}
<img class="ability-icon" src={art === "mage-basic-art" ? mageBasic : mageLance} alt="" aria-hidden="true" draggable="false" data-mage-art={art} />
{:else}
<svg class="ability-icon" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <defs><linearGradient id="skill-steel" x2=".6" y2="1"><stop stop-color="#ecf8ff"/><stop offset=".35" stop-color="#a2d1e8"/><stop offset=".55" stop-color="#447299"/><stop offset="1" stop-color="#82b7d5"/></linearGradient><linearGradient id="skill-arc" x2=".5" y2="1"><stop stop-color="#effcff"/><stop offset=".35" stop-color="#82ddff"/><stop offset="1" stop-color="#32689c"/></linearGradient></defs>
  {#if potion}<path fill="url(#skill-arc)" d="M20 15h8v5l8 12v6c-5 5-19 5-24 0v-6l8-12Z"/><path d="M20 15h8v5l8 12v6c-5 5-19 5-24 0v-6l8-12ZM18 11h12v4H18Z"/><path d="M15 30c8 4 12-3 18 0M19 33v4"/>
  {:else if action === "guard"}<path fill="url(#skill-steel)" d="M24 6 39 12v13c-2 9-9 14-15 18-6-4-13-9-15-18V12Z"/><path d="M24 6 39 12v13c-2 9-9 14-15 18-6-4-13-9-15-18V12Z"/><path d="m24 13 6 10-6 12-6-12ZM24 13v22"/>
  {:else if action === "dodge"}<path d="M7 15h17l-6-6m6 6-6 6M5 27h23l-6-6m6 6-6 6M14 39h24l-6-6m6 6-6 6"/><path d="m29 9 10 10-7 14" stroke-opacity=".45"/>
  {:else if action === "arc_slash"}<path d="M7 37C9 12 29 5 42 8 23 15 16 25 7 37Z" fill="url(#skill-arc)"/><path d="M8 41C17 29 26 24 38 22M7 37C9 12 29 5 42 8 23 15 16 25 7 37Z"/><path d="m30 32 4 5m-1-9 4 5M14 14l-4-4" stroke-opacity=".5"/>
  {:else}<path d="m16 28 15-18 9-3-3 9-17 16Z" fill="url(#skill-steel)"/><path d="m16 28 15-18 9-3-3 9-17 16ZM24 31l-7-7m3 10-5-5-7 8 4 4Z"/><path d="M22 26 34 14m-26 27 4-4"/>{/if}
</svg>
{/if}
<style>.ability-icon { width: 80%; height: 80%; color: #a1ddff; filter: drop-shadow(0 2px 2px #040a18); pointer-events: none; }</style>
