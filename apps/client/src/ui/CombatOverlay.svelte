<script lang="ts">
	/* THESIS: combat facts stay readable without covering play. OWN-WORLD: Xexoria navy,
	   ivory and aged gold. STORY: identify a threat, read its cast, recover from a KO.
	   FIRST VIEWPORT: fixed plate pool over actors, compact centre target, safe-area KO action.
	   FORM: extension of the incumbent HUD; no replacement art or fabricated server values. */
	import CombatCastBar from "./CombatCastBar.svelte";
	import { canReturnToTown, healthRatio, type CombatView, type DeathView } from "./combat-model";
	import { trapDialogKey } from "./floating-panel";
	let { view, death, language, returnToTown, worldSuspended = false }: { view: CombatView; death: DeathView; language: "en" | "th"; returnToTown(): void; worldSuspended?: boolean } = $props();
	let dialog: HTMLDivElement | undefined = $state();
	let focusGeneration = 0;
	const th = $derived(language === "th"), target = $derived(view.target), pending = $derived(death.request?.phase);
	const chip = (value: string) => ({ passive:th?"ไม่ก้าวร้าว":"Passive", aggro:th?"กำลังโจมตี":"Attacking", windup:th?"เตรียมท่า":"Preparing", punish:th?"เปิดช่อง":"Vulnerable", down:th?"ล้ม":"Down", normal:th?"ทั่วไป":"Normal", elite:th?"ชั้นยอด":"Elite", boss:th?"บอส":"Boss" } as Record<string,string>)[value] ?? value;
	const numbers = (hp: number | null, max: number | null) => `${hp===null?"—":hp.toLocaleString(language)} / ${max===null?"—":max.toLocaleString(language)}`;
	$effect(() => {
		if (!death.down) return;
		const previous = document.activeElement, generation = ++focusGeneration;
		queueMicrotask(() => { if (generation === focusGeneration && death.down) (dialog?.querySelector<HTMLButtonElement>("button:not(:disabled)") ?? dialog)?.focus(); });
		return () => { focusGeneration++; if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
	});
	function key(event: KeyboardEvent): void { if (event.ctrlKey || event.metaKey) return; event.stopPropagation(); if (dialog) trapDialogKey(event, dialog, () => {}); }
</script>

<div class="combat-presentation" class:mobile={view.mobile} data-ui-component="combat-presentation">
	<div class="plate-layer" hidden={worldSuspended} aria-hidden={worldSuspended} aria-label={th ? "สถานะมอนสเตอร์" : "Monster status"}>
		{#each view.slots as slot (slot.slot)}
			<div class="combat-plate" class:shown={slot.visible} class:occluded={slot.actor?.occluded} class:selected={slot.actor?.id===target?.id} class:other={slot.actor?.id!==target?.id} data-plate-slot={slot.slot} data-actor-id={slot.actor?.id ?? ""} aria-hidden={worldSuspended || !slot.visible} style:--plate-x={`${slot.actor?.screenX ?? 0}px`} style:--plate-y={`${slot.actor?.screenY ?? 0}px`}>
				{#if slot.actor}
					<p class="plate-name">{#if slot.actor.level!==null}<span class="plate-level">{slot.actor.level}</span>{/if}{slot.actor.name}{#if slot.actor.rank==="elite"||slot.actor.rank==="boss"}<span class="rank">{chip(slot.actor.rank)}</span>{/if}</p>
					<div class="plate-health" role="progressbar" aria-label={th ? `พลังชีวิต ${slot.actor.name}` : `${slot.actor.name} health`} aria-valuemin="0" aria-valuemax={slot.actor.maxHp ?? undefined} aria-valuenow={healthRatio(slot.actor)===null?undefined:slot.actor.hp??undefined} aria-valuetext={numbers(slot.actor.hp,slot.actor.maxHp)} class:unknown={healthRatio(slot.actor)===null}><i style:transform={`scaleX(${healthRatio(slot.actor) ?? 0})`}></i></div>
				{/if}
			</div>
		{/each}
	</div>
	{#if target && !death.down && !worldSuspended}
		<aside class="target-frame" aria-label={th ? "เป้าหมายที่เลือก" : "Selected target"} data-target-id={target.id}>
			<div class="target-heading"><strong>{target.name}</strong><span>{target.level===null?"—":`Lv. ${target.level}`}</span></div>
			<div class="target-health" role="progressbar" aria-label={th?"พลังชีวิตเป้าหมาย":"Target health"} aria-valuemin="0" aria-valuemax={target.maxHp??undefined} aria-valuenow={healthRatio(target)===null?undefined:target.hp??undefined} aria-valuetext={numbers(target.hp,target.maxHp)}><i style:transform={`scaleX(${healthRatio(target)??0})`}></i><span>{numbers(target.hp,target.maxHp)}</span></div>
			<div class="target-chips">{#if target.rank}<span>{chip(target.rank)}</span>{/if}{#if target.element}<span>{target.element}</span>{/if}{#each target.stateChips as state}<span>{chip(state)}</span>{/each}</div>
			{#if target.cast}{#key `${target.id}:${target.cast.endsAtMs}:${target.cast.durationMs}`}<CombatCastBar cast={target.cast} nowMs={view.nowMs} {th}/>{/key}{/if}
		</aside>
	{/if}
	{#if death.down}
		<div class="death-cover" data-death-revision={death.revision??"unknown"}>
			<div class="death-panel" role="dialog" aria-modal="true" aria-labelledby="death-title" tabindex="-1" bind:this={dialog} onkeydown={key}>
				<div class="death-mark" aria-hidden="true">✦</div><h2 id="death-title">{th?"คุณล้มลงแล้ว":"You have fallen"}</h2>
				<p class="death-cause">{death.cause==="monster"?(th?"พ่ายแพ้ในการต่อสู้กับมอนสเตอร์":"Defeated in monster combat"):death.cause==="none"?(th?"เซิร์ฟเวอร์ไม่ได้ระบุผู้โจมตี":"No attacker was reported"):th?"กำลังรอสาเหตุจากเซิร์ฟเวอร์":"Waiting for the server's cause of death"}</p>
				<dl class="death-details"><div><dt>{th?"บทลงโทษ":"Penalty"}</dt><dd>{#if death.penalty}<span>Base EXP −{death.penalty.base_exp}</span><span>Job EXP −{death.penalty.job_exp}</span><span>{th?"ทอง":"Gold"} −{death.penalty.gold}</span>{:else}{th?"ยังไม่มีข้อมูล":"Not reported"}{/if}</dd></div><div><dt>{th?"กลับเมือง":"Return to town"}</dt><dd>{death.free_return===true&&death.costs?.return_to_town===0?(th?"ฟรี · ไม่ใช้ทอง":"Free · no gold required"):death.costs?`${death.costs.return_to_town} ${th?"ทอง":"gold"}`:th?"กำลังรอยืนยันค่าใช้จ่าย":"Awaiting confirmed cost"}</dd></div></dl>
				{#if !death.online}<p class="recovery-status" role="status">{th?"ขาดการเชื่อมต่อ กำลังรอสถานะเซิร์ฟเวอร์":"Disconnected. Waiting for server state."}</p>
				{:else if pending==="submitting"}<p class="recovery-status" role="status">{th?"กำลังขอกลับเมือง…":"Requesting return to town…"}</p>
				{:else if pending==="committed"}<p class="recovery-status" role="status">{th?"เซิร์ฟเวอร์ตอบรับแล้ว กำลังรอสถานะตัวละคร":"Accepted. Waiting for authoritative character state."}</p>
				{:else if pending==="outcome-unknown"}<p class="recovery-status" role="status">{th?"ยังไม่ทราบผล ลองใหม่ด้วยคำขอเดิมได้เมื่อเชื่อมต่อ":"Outcome unknown. Retry uses the same request."}</p>
				{:else if pending==="rejected"}<p class="recovery-status" role="alert">{th?"คำขอถูกปฏิเสธ ตรวจสถานะแล้วลองใหม่":"Request rejected. Check your state and try again."}</p>{/if}
				<button type="button" class="return-town" data-return-to-town disabled={!canReturnToTown(death)} onclick={returnToTown}>{pending==="outcome-unknown"?(th?"ลองกลับเมืองอีกครั้ง":"Retry return to town"):(th?"กลับเมือง":"Return to town")}</button>
				{#if death.revision===null||!death.canSubmit}<p class="recovery-status">{th?"กำลังรอตัวเลือกฟื้นคืนชีพจากเซิร์ฟเวอร์":"Waiting for server recovery options."}</p>{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.plate-layer[hidden] { display: none; }
	.combat-presentation { position:absolute; inset:0; pointer-events:none; font-family:"Noto Sans Thai",sans-serif; color:#f5f1e6; }
	.plate-layer { position:absolute; inset:0; overflow:hidden; }
	.combat-plate { position:absolute; left:0; top:0; transform:translate(var(--plate-x),var(--plate-y)) translate(-50%,-100%); opacity:0; transition:opacity 250ms ease-out; text-align:center; width:max-content; max-width:220px; }
	.combat-plate.shown { opacity:1; transition-duration:120ms; }.combat-plate.shown.occluded { opacity:.4; }
	.plate-name { margin:0 0 4px; font-size:18px; font-weight:650; line-height:1.45; color:#fff5dc; text-shadow:0 2px 3px #000,-1px -1px 0 #17202c,1px 1px 0 #17202c; overflow-wrap:anywhere; }
	.plate-level { display:inline-block; margin-right:5px; font-size:12px; color:#d9e9f0; }.rank { margin-left:5px; font-size:11px; color:#ffdf9f; }
	.plate-health { width:96px; height:8px; margin:auto; background:#16222c; box-shadow:0 1px 3px #000c; border:1px solid #252f3b; box-sizing:border-box; overflow:hidden; }.plate-health i { display:block; height:100%; background:#c6504d; transform-origin:left; }.selected .plate-health { outline:1px solid #e7c381; outline-offset:1px; }.plate-health.unknown { background:#35414b; }
	.target-frame { position:absolute; top:calc(env(safe-area-inset-top) + 70px); left:50%; transform:translateX(-50%); width:min(290px,calc(100vw - 40px)); padding:10px 12px; background:#101c2bf2; border:1px solid #b5945c; box-shadow:0 3px 8px #0008; }
	.target-heading { display:flex; justify-content:space-between; gap:10px; align-items:baseline; margin-bottom:7px; }.target-heading strong { font-size:16px; overflow-wrap:anywhere; }.target-heading>span { color:#d9cbaa; font-size:12px; flex:none; }
	.target-health { position:relative; height:20px; background:#18252e; overflow:hidden; }.target-health i { position:absolute; inset:0; transform-origin:left; background:#993e3c; }.target-health span { position:relative; display:block; text-align:center; line-height:20px; font-size:12px; font-variant-numeric:tabular-nums; text-shadow:0 1px 2px #000; }
	.target-chips { display:flex; gap:5px; flex-wrap:wrap; margin:6px 0; }.target-chips span { padding:2px 6px; font-size:11px; color:#eadcbd; background:#273240; border:1px solid #596579; }
	.death-cover { position:absolute; inset:0; display:grid; place-items:center; padding:max(14px,env(safe-area-inset-top)) max(14px,env(safe-area-inset-right)) max(14px,env(safe-area-inset-bottom)) max(14px,env(safe-area-inset-left)); background:#071322b8; pointer-events:auto; z-index:12; }
	.death-panel { width:min(430px,100%); max-height:100%; overflow:auto; box-sizing:border-box; padding:22px 24px; background:#101d2d; border:1px solid #c7a668; box-shadow:0 8px 28px #0009; text-align:center; }
	.death-mark { color:#e2c78e; font-size:30px; }.death-panel h2 { margin:5px 0 8px; color:#ffe2a6; font-size:25px; }.death-cause { margin:0 0 18px; line-height:1.5; font-size:14px; color:#dce8ec; }.death-details { margin:0; font-size:13px; }.death-details>div { display:flex; justify-content:space-between; gap:16px; padding:9px 0; border-bottom:1px solid #3e5263; text-align:left; }.death-details dt { color:#ccbd9b; }.death-details dd { margin:0; text-align:right; }.death-details dd span { display:block; }.recovery-status { font-size:13px; line-height:1.5; color:#d1e7ef; margin:12px 0; }.return-town { min-height:48px; width:100%; margin-top:18px; border:1px solid #d2ae63; color:#fff1d2; background:#345163; font:650 16px "Noto Sans Thai",sans-serif; cursor:pointer; }.return-town:hover:not(:disabled) { background:#426b80; }.return-town:disabled { opacity:.55; cursor:default; }.return-town:focus-visible,.death-panel:focus-visible { outline:3px solid #f4d891; outline-offset:4px; }
	.mobile .plate-name { font-size:15px; }.mobile .plate-health { width:88px; }.mobile .other .plate-name { display:none; }.mobile .other .plate-health { width:64px; height:6px; }.mobile .target-frame { top:calc(env(safe-area-inset-top) + 60px); width:218px; padding:7px 9px; }.mobile .target-heading strong { font-size:14px; }.mobile .target-chips span { font-size:10px; }
	@media(max-height:450px) { .death-panel { padding:14px 20px; width:min(470px,100%); }.death-mark { display:none; }.death-panel h2 { font-size:21px; }.death-cause { margin-bottom:8px; }.death-details>div { padding:6px 0; }.return-town { margin-top:10px; }.recovery-status { margin:8px 0; } }
	@media(prefers-reduced-motion:reduce) { .combat-plate { transition:none; } }
</style>
