<!-- Incumbent UI preserved for DEV-only screenshot review; live world/server data unchanged. -->
<script lang="ts">
	import { onMount } from "svelte";
	import { touchPress } from ".././touch-action";
	import type { HudAction } from ".././hud-types";
	interface Props {
		label: string;
		buttonClass: string;
		keyText: string;
		art?: string;
		action?: HudAction;
		id?: string;
		countId?: string;
		potion?: boolean;
		pending?: boolean;
		disabled?: boolean;
		readyAtMs: number;
		cooldownDurationMs: number;
		visible: boolean;
		mobile?: boolean;
		th: boolean;
		onactivate(): void;
	}
	let { label, buttonClass, keyText, art = "", action, id, countId, potion = false, pending = false,
		disabled = false, readyAtMs, cooldownDurationMs, visible, mobile = false, th, onactivate }: Props = $props();
	let pageVisible = $state(true);
	let now = $state(0);
	let sweepDuration = $state(1);
	let sweepElapsed = $state(0);
	const remaining = $derived(Math.max(0, readyAtMs - now));
	const unavailable = $derived(disabled || pending || remaining > 0);
	const seconds = $derived(Math.ceil(remaining / 1000));
	const progress = $derived(cooldownDurationMs > 0 ? Math.min(1, remaining / cooldownDurationMs) : 0);
	const accessibleLabel = $derived(pending ? `${label} · ${th ? "กำลังใช้" : "Pending"}`
		: remaining > 0 ? `${label} · ${th ? `พร้อมใน ${seconds} วินาที` : `Ready in ${seconds}s`}` : label);
	onMount(() => {
		const changed = () => { pageVisible = !document.hidden; };
		changed();
		document.addEventListener("visibilitychange", changed);
		return () => document.removeEventListener("visibilitychange", changed);
	});
	$effect(() => {
		const deadline = readyAtMs;
		const duration = cooldownDurationMs;
		if (!visible || !pageVisible) return;
		const initial = performance.now();
		sweepDuration = Math.max(1, duration, deadline - initial);
		sweepElapsed = Math.max(0, sweepDuration - Math.max(0, deadline - initial));
		let timer = 0;
		const refresh = () => {
			const current = performance.now();
			now = current;
			const left = deadline - current;
			// CSS owns the sweep. Only change numeric/accessible countdowns at second boundaries.
			if (left > 0) timer = window.setTimeout(refresh, Math.max(16, left - (Math.ceil(left / 1000) - 1) * 1000 + 2));
		};
		refresh();
		return () => window.clearTimeout(timer);
	});
</script>

<button {id} class={buttonClass} class:cooling={remaining > 0} data-action={action} type="button"
	aria-label={accessibleLabel} aria-busy={pending} title={accessibleLabel} disabled={unavailable}
	use:touchPress={{ enabled: !unavailable && visible, capture: mobile }} onclick={onactivate}>
	{#if potion}<span class="potion-bottle" aria-hidden="true"></span>{:else}<span class={`skill-art ${art}`} aria-hidden="true"></span>{/if}
	{#if remaining > 0}{#key readyAtMs}<span class="cooldown-shade" style={`--cooldown-static:${progress * 100}%;--cd-duration:${sweepDuration}ms;--cd-delay:${-sweepElapsed}ms`} aria-hidden="true"></span>{/key}<span class="cooldown-seconds" aria-hidden="true">{seconds}</span>{/if}
	{#if pending}<span class="pending-mark" aria-hidden="true">…</span>{/if}
	<small id={countId}>{keyText}</small>
	
</button>

<style>
button { min-width:44px; min-height:44px; }
.cooldown-shade { position:absolute; inset:0; border-radius:inherit; background:conic-gradient(rgba(8,13,20,.72) var(--hud-cooldown),transparent 0); animation:hud-cooldown-sweep var(--cd-duration) linear var(--cd-delay) both; pointer-events:none; }
.cooldown-seconds,.pending-mark { position:absolute; z-index:1; inset:0; display:grid; place-items:center; color:#fff7dd; font-size:17px; font-weight:800; pointer-events:none; }
button.cooling:disabled { opacity:.8; filter:none; }
@media(max-height:520px) and (max-width:900px){button.mobile-skill{min-width:58px;min-height:58px;}}
</style>
