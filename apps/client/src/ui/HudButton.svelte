<script lang="ts">
	import { onMount } from "svelte";
	import { touchPress } from "./touch-action";
	import SkillIcon from "./SkillIcon.svelte";
	import type { HudAction, HudAbility } from "./hud-types";
	import { actionDescription } from "../combat-actions.mjs";
	interface Props {
		label: string;
		buttonClass: string;
		keyText: string;
		art?: HudAbility["art"];
		description?: string;
		spCost?: number;
		rangeM?: number;
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
	let { label, buttonClass, keyText, art, description, spCost, rangeM, action, id, countId, potion = false, pending = false,
		disabled = false, readyAtMs, cooldownDurationMs, visible, mobile = false, th, onactivate }: Props = $props();
	let pageVisible = $state(true);
	let now = $state(0);
	let sweepDuration = $state(1);
	let sweepElapsed = $state(0);
	const remaining = $derived(Math.max(0, readyAtMs - now));
	const unavailable = $derived(disabled || pending || remaining > 0);
	const seconds = $derived(Math.ceil(remaining / 1000));
	const progress = $derived(cooldownDurationMs > 0 ? Math.min(1, remaining / cooldownDurationMs) : 0);
	const canonical = $derived(action ? actionDescription(action,th?"th":"en") : null);
	const mageArtwork = $derived(art === "mage-basic-art" || art === "mage-lance-art");
	const actionLabel = $derived(mageArtwork ? label : canonical?.label ?? label);
	const hint = $derived(canonical?.key ?? keyText);
	const accessibleLabel = $derived(pending ? `${actionLabel} · ${th ? "กำลังใช้" : "Pending"}`
		: remaining > 0 ? `${actionLabel} · ${th ? `พร้อมใน ${seconds} วินาที` : `Ready in ${seconds}s`}` : `${actionLabel}${hint?` · ${hint}`:""}${disabled ? ` · ${th ? "ยังใช้ไม่ได้" : "Unavailable"}` : ""}`);
	const tooltip = $derived([
		accessibleLabel,
		typeof description === "string" ? description.trim().slice(0, 320) : "",
		typeof spCost === "number" && Number.isFinite(spCost) && spCost >= 0 ? `${spCost} SP` : "",
		typeof rangeM === "number" && Number.isFinite(rangeM) && rangeM >= 0 ? (th ? `ระยะ ${rangeM} ม.` : `Range ${rangeM} m`) : "",
	].filter(Boolean).join(" · "));
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

<button {id} class={buttonClass} class:cooling={remaining > 0} class:skill-ready={!unavailable} data-action={action} type="button"
	aria-label={tooltip} aria-busy={pending} title={tooltip} disabled={unavailable}
	use:touchPress={{ enabled: !unavailable && visible, capture: mobile }} onclick={onactivate}>
	<span class={`ability-art ${art ?? ""}`}><SkillIcon {action} {art} {potion} /></span>
	{#if remaining > 0}{#key readyAtMs}<span class="cooldown-shade" style={`--cooldown-static:${progress * 100}%;--cd-duration:${sweepDuration}ms;--cd-delay:${-sweepElapsed}ms`} aria-hidden="true"></span>{/key}<span class="cooldown-seconds" aria-hidden="true">{seconds}</span>{/if}
	{#if pending}<span class="pending-mark" aria-hidden="true">…</span>{/if}
	<small id={countId}>{hint}</small>
	<span class="skill-tooltip" role="tooltip">{tooltip}</span>
</button>

<style>
	button { min-width: 44px; min-height: 44px; }
	.ability-art { display: grid; place-items: center; width: 100%; height: 100%; }
	.cooldown-shade { position: absolute; inset: 3px; border-radius: 3px; background: conic-gradient(from -90deg,rgba(3,8,19,.84) var(--hud-cooldown,var(--cooldown-static,100%)),transparent 0); animation: hud-cooldown-sweep var(--cd-duration) linear var(--cd-delay) both; pointer-events: none; }
	.cooldown-seconds, .pending-mark { position: absolute; z-index: 1; inset: 0; display: grid; place-items: center; color: #fff7dd; font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; text-shadow: 0 1px 4px #000; pointer-events: none; }
	button.cooling:disabled { opacity: .8; filter: none; }
	.skill-tooltip { position: absolute; left: 50%; bottom: calc(100% + 14px); transform: translateX(-50%); width: max-content; max-width: 220px; padding: 8px 11px; border: 1px solid #a6dafa; background: #091426f5; color: #eef6ff; font-size: 12px; line-height: 1.5; visibility: hidden; opacity: 0; transition: opacity 160ms; pointer-events: none; z-index: 5; }
	button:is(:hover,:focus-visible) .skill-tooltip { visibility: visible; opacity: 1; }
	@media (max-width: 900px), (any-pointer: coarse) { .skill-tooltip { display: none; } }
	@media (prefers-reduced-motion: reduce) { .cooldown-shade { animation: none; --hud-cooldown: var(--cooldown-static); } .skill-tooltip { transition: none; } }
	@media (max-height: 520px) and (max-width: 900px) { button.mobile-skill { min-width: 58px; min-height: 58px; } }
</style>
