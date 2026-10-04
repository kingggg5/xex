<script lang="ts">
	import type { Snippet } from "svelte";
	import type { PanelResourceState, UiTransaction } from "./combat-model";
	let { states, transactions, th, retry, canRetry=false, online=true, children }: { states: PanelResourceState[]; transactions: UiTransaction[]; th: boolean; retry():void; canRetry?:boolean; online?:boolean; children: Snippet } = $props();
	const offlineEmpty = $derived(!online&&states.length>0&&states.every(s=>!s.hasData));
	const waiting = $derived(states.some(s=>s.status==="loading"&&!s.hasData));
	const refreshing = $derived(states.some(s=>s.status==="loading"));
	const error = $derived(states.find(s=>s.status==="error"));
	const stale = $derived(states.some(s=>s.status==="stale"));
	const missing = $derived(states.some(s=>(s.status==="stale"||s.status==="error")&&!s.hasData));
	const empty = $derived(states.length>0&&states.every(s=>s.status==="loaded-empty"));
	const busy = $derived(transactions.some(t=>t.phase==="submitting"));
	const unknown = $derived(transactions.some(t=>t.phase==="outcome-unknown"));
	const latestTerminal = $derived(transactions.filter(t=>t.phase==="rejected"||t.phase==="committed").at(-1));
	const rejected = $derived(latestTerminal?.phase==="rejected" ? latestTerminal : null);
	const committed = $derived(latestTerminal?.phase==="committed");
</script>
<div class="panel-data-gate" aria-busy={(online&&refreshing)||busy} data-resource-state={offlineEmpty?"stale":refreshing?"loading":error?"error":stale?"stale":empty?"loaded-empty":"loaded-data"} data-transaction-state={unknown?"outcome-unknown":busy?"submitting":rejected?"rejected":committed?"committed":"preview"}>
	{#if offlineEmpty}<p class="data-status" role="status">{th?"เชื่อมต่อเพื่อโหลดข้อมูลจากเซิร์ฟเวอร์":"Connect to load server data."}</p>
	{:else if waiting}<p class="data-status" role="status">{th?"กำลังโหลดข้อมูลจากเซิร์ฟเวอร์…":"Loading server data…"}</p>
	{:else if refreshing}<p class="data-status" role="status">{th?"กำลังตรวจข้อมูลใหม่ · แสดงค่าล่าสุดที่ได้รับ":"Refreshing server data · last received values"}</p>
	{:else if error}<p class="data-status data-error" role="alert">{error.message??(th?"โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่":"Could not load this data. Try again.")}</p>
	{:else if stale}<p class="data-status" role="status">{th?"ข้อมูลล่าสุดที่เคยได้รับ · กำลังรอยืนยันจากเซิร์ฟเวอร์":"Last received data · waiting for server confirmation"}</p>
	{:else if empty}<p class="data-status" role="status">{th?"โหลดแล้ว · ยังไม่มีรายการ":"Loaded · no entries yet"}</p>{/if}
	{#if unknown}<p class="transaction-status" role="status">{th?"ยังไม่ทราบผลรายการ ตรวจสถานะก่อนส่งซ้ำ":"Transaction outcome unknown. Check server state before retrying."}</p>
	{:else if busy}<p class="transaction-status" role="status">{th?"กำลังส่งรายการ รอคำตอบจากเซิร์ฟเวอร์…":"Submitting. Waiting for the server…"}</p>
	{:else if rejected}<p class="transaction-status data-error" role="alert">{rejected.reason??(th?"รายการถูกปฏิเสธ":"Transaction rejected")}</p>
	{:else if committed}<p class="transaction-status" role="status">{th?"เซิร์ฟเวอร์ยืนยันรายการแล้ว":"Server confirmed the transaction"}</p>{/if}
	{#if canRetry&&(error||stale||unknown)}<button class="data-refresh" type="button" disabled={busy} onclick={retry}>{th?"ตรวจข้อมูลใหม่":"Refresh state"}</button>{/if}
	{#if !offlineEmpty&&!waiting&&!missing}<fieldset disabled={busy||unknown||refreshing||stale||!!error||(!online&&states.length>0)}>{@render children()}</fieldset>{/if}
</div>
<style>
	.panel-data-gate { min-width:0; }.panel-data-gate fieldset { min-width:0; margin:0; padding:0; border:0; }.data-status,.transaction-status { margin:0 0 14px; padding:12px 0; color:#cde5ee; font-size:14px; line-height:1.6; border-bottom:1px solid #425666; }.data-error { color:#ffc7b5; }.data-refresh { min-height:44px; padding:8px 16px; margin-bottom:14px; color:#f6dfb1; background:#253c4b; border:1px solid #ad8d50; font:inherit; cursor:pointer; }.data-refresh:focus-visible { outline:3px solid #f4d891; outline-offset:3px; }
</style>
