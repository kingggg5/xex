<script lang="ts">
	import DeviceIcon from "../DeviceIcon.svelte";
	import { isValidGroupCode } from "../../social-parse.mjs";
	import { presenceLabel } from "../panel-data";
	import type { PanelCommands, PanelSnapshot } from "../panel-types";
	let { model, commands }: { model: PanelSnapshot; commands: PanelCommands } = $props();
	let code = $state("");
	let invalid = $state(false);
	let th = $derived(model.language === "th");
	function join(event: SubmitEvent): void { event.preventDefault(); invalid = !isValidGroupCode(code); if (!invalid && model.online) commands.groupJoin(code); }
</script>

{#if !model.group}
	<p class="econ-note">{th ? "ขณะนี้คุณยังไม่ได้อยู่ในกลุ่ม" : "You are not in a group right now."}</p>
	<button type="button" class="social-action" disabled={!model.online} onclick={commands.groupCreate}>{th ? "สร้างกลุ่ม" : "Create group"}</button>
	<form class="social-form" onsubmit={join}><label class="visually-hidden" for="group-code">{th ? "รหัสเชิญกลุ่ม" : "Group invite code"}</label><input id="group-code" value={code} oninput={(event) => { code = event.currentTarget.value.toUpperCase().replace(/[^A-Z0-9]/g, ""); invalid = false; }} maxlength="6" autocomplete="off" spellcheck={false} placeholder={th ? "รหัส 6 ตัว" : "6-character code"} aria-invalid={invalid} /><button type="submit" class="social-action" disabled={!model.online}>{th ? "เข้าร่วม" : "Join"}</button></form>
	{#if invalid}<p class="form-error" role="alert">{th ? "กรอกรหัสเชิญ 6 ตัว" : "Enter a 6-character invite code."}</p>{/if}
{:else}
	<p class="group-code">{th ? "รหัสเชิญ" : "Invite code"} <strong>{model.group.code || "······"}</strong></p>
	{#if model.group.members.length === 0}<p class="econ-note">{th ? "ยังไม่มีสมาชิกคนอื่น — แชร์รหัสเชิญของคุณได้เลย" : "No other members yet — share your invite code."}</p>
	{:else}<p class="econ-note">{th ? `สมาชิก ${model.group.members.length} คน` : `${model.group.members.length} ${model.group.members.length === 1 ? "member" : "members"}`}</p>
		<div class="social-rows">{#each model.group.members as member}<div class="social-row" class:is-online={member.online} class:is-offline={!member.online}><span class="social-dot" aria-hidden="true"></span><div class="social-label"><strong><DeviceIcon device={member.device} thai={th}/>{member.name}</strong>{#if member.handle && member.handle !== member.name}<small>@{member.handle}</small>{/if}</div><span class="social-where">{presenceLabel(member, model.language)}</span></div>{/each}</div>
	{/if}
	<button type="button" class="social-leave" disabled={!model.online} onclick={commands.groupLeave}>{th ? "ออกจากกลุ่ม" : "Leave group"}</button>
{/if}
<p class="econ-note">{th ? "แชทกลุ่มอยู่ที่แท็บกลุ่ม (Party) ของหน้าแชท" : "Group chat lives in the Party tab of the chat panel."}</p>
