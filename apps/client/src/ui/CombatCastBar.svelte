<script lang="ts">
	import { untrack } from "svelte";
	import { castRemaining, type CombatCast } from "./combat-model";
	let { cast, nowMs, th }: { cast: CombatCast; nowMs: number; th: boolean } = $props();
	// Parent keys this component by target/deadline. CSS owns the clock between samples.
	const timing = untrack(() => ({ duration: cast.durationMs, elapsed: cast.durationMs - castRemaining(cast, nowMs) }));
	const fraction = $derived(castRemaining(cast, nowMs) / cast.durationMs);
</script>
<div class="cast" role="progressbar" aria-label={cast.label ?? (th ? "กำลังเตรียมท่า" : "Preparing an attack")} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(fraction * 100)}>
	<i style:animation-duration={`${timing.duration}ms`} style:animation-delay={`${-timing.elapsed}ms`}></i><span>{cast.label ?? (th ? "กำลังเตรียมท่า" : "Preparing an attack")}</span>
</div>
<style>
	.cast { position:relative; height:22px; overflow:hidden; background:#111824; border:1px solid #a17d42; }
	.cast i { position:absolute; inset:0; transform-origin:left; background:#aa7937; animation:cast-drain linear both; }
	.cast span { position:relative; display:block; text-align:center; font-size:12px; color:#fff4d8; line-height:22px; text-shadow:0 1px 2px #000; }
	@keyframes cast-drain { from { transform:scaleX(1); } to { transform:scaleX(0); } }
	@media(prefers-reduced-motion:reduce) { .cast i { animation-timing-function:steps(12); } }
</style>
