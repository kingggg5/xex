<script lang="ts">
	import { onMount } from "svelte";
	import type { HudToast } from "./hud-types";
	let { entries }: { entries: HudToast[] } = $props();
	let now = $state(0);
	let pageVisible = $state(true);
	const shown = $derived(entries.filter((entry) => entry.expiresAtMs > now));
	onMount(() => {
		const changed = () => { pageVisible = !document.hidden; };
		changed();
		document.addEventListener("visibilitychange", changed);
		return () => document.removeEventListener("visibilitychange", changed);
	});
	$effect(() => {
		const queue = entries;
		if (!pageVisible) return;
		let timer = 0;
		const refresh = () => {
			const current = performance.now();
			now = current;
			const next = Math.min(...queue.filter((entry) => entry.expiresAtMs > current).map((entry) => entry.expiresAtMs));
			if (Number.isFinite(next)) timer = window.setTimeout(refresh, Math.max(1, next - current));
		};
		refresh();
		return () => window.clearTimeout(timer);
	});
</script>

<div id="toast-stack" aria-live="polite" aria-atomic="false">
	{#each shown as entry (entry.id)}<div class="toast">{entry.message}</div>{/each}
</div>
