<script lang="ts">
	import { untrack } from "svelte";
	import { mountOptionalRive } from "./rive-adapter";
	import type { RiveAdapter } from "./rive-adapter";
	let { src = null, label, active = true, artboard, stateMachines }: { src?: string | null; label: string; active?: boolean; artboard?: string; stateMachines?: string[] } = $props();
	let canvas: HTMLCanvasElement | undefined = $state();
	let failure = $state("");
	let adapter: RiveAdapter | null = null;
	$effect(() => {
		if (!canvas || !src) return;
		failure = "";
		try {
			const current = mountOptionalRive(canvas, src, { artboard, stateMachines: stateMachines ? [...stateMachines] : undefined, onError: (message) => { failure = message; } });
			adapter = current;
			current.setActive(untrack(() => active));
			return () => { current.dispose(); if (adapter === current) adapter = null; };
		} catch { failure = "Animation could not be loaded."; }
	});
	$effect(() => { adapter?.setActive(active); });
</script>

{#if src}
	<div role="img" aria-label={label}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
	{#if failure}<span class="rive-fallback" role="status">{failure}</span>{/if}
{/if}

<style>
	canvas { display: block; width: 256px; max-width: 100%; height: 160px; }
	.rive-fallback { color: #d5d8ce; font-size: 13px; }
</style>
