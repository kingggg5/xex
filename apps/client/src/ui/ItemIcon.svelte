<script lang="ts">
	let { kind = "item", item = "" }: { kind?: "weapon" | "armor" | "potion" | "box" | "material" | "item"; item?: string } = $props();
</script>

<svg class="item-symbol" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
	{#if kind === "weapon" && item === "arcane_focus"}
		<path d="m17 42 12-27m-7-7 6-5 7 4 1 8-7 5-7-4Z"/><path d="m28 3 4 8-3 9-3-10Z" fill="#aeb4d5" fill-opacity=".5"/><path d="m20 15 3 7m13-7-1 7m-20 15 5 2m3-10 4 2"/>
	{:else if kind === "weapon" && item.includes("staff")}
		<path d="m16 41 13-28m-6-6 6-4 6 4-1 7-6 4-6-4Z"/><path d="m29 4 3 7-4 6-3-7Z" fill="currentColor" fill-opacity=".28"/><path d="m14 38 5 2m1-10 5 2"/>
	{:else if kind === "weapon"}
		<path d="m18 28 14-18 8-3-2 9-16 16Zm-5-5 15 13m-13-7-8 9 4 4 8-9"/><path d="m20 27 15-15" stroke-opacity=".55"/>
	{:else if kind === "armor"}
		<path d="m17 8 7 4 7-4 10 11-7 5-2-4v20H16V20l-2 4-7-5Z"/><path d="m17 8 7 9 7-9M24 17v23m-8-11h16m-16 7h16" stroke-opacity=".55"/>
	{:else if kind === "potion"}
		<path d="M19 7h10v5H19Zm2 5v8L12 31v8c4 4 20 4 24 0v-8l-9-11v-8"/><path d="M14 31c7 4 13-3 20 0v7c-4 3-16 3-20 0Z" fill="currentColor" fill-opacity=".25"/>
	{:else if kind === "box"}
		<path d="m8 17 16-8 16 8v21H8Zm0 0h32M24 9v29m-16-7h32"/><path d="M20 23h8v9h-8Z" fill="currentColor" fill-opacity=".25"/>
	{:else if kind === "material"}
		<path d="m24 6 13 12-4 19-9 6-9-6-4-19Zm0 0v37M11 18h26m-13-6-9 19m9-19 9 19"/><path d="m24 7 8 11-8 20-8-20Z" fill="currentColor" fill-opacity=".18"/>
	{:else}
		<path d="m14 11 10-4 10 4 5 15-5 14H14L9 26Zm0 0 10 12 10-12M9 26h30M24 23v17"/>
	{/if}
</svg>
