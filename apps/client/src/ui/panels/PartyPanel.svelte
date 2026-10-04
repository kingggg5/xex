<script lang="ts">
	import type { PanelCommands, PanelSnapshot } from "../panel-types";
	import { isValidGroupCode } from "../../social-parse.mjs";
	let { model, commands }: { model: PanelSnapshot; commands: PanelCommands } = $props();
	let code = $state("");
	let invalid = $state(false);
	let th = $derived(model.language === "th");
	function join(event: SubmitEvent): void {
		event.preventDefault();
		invalid = !isValidGroupCode(code);
		if (!invalid && model.online) commands.party({ kind: "join", code });
	}
</script>

{#if !model.online}<p class="econ-note">{th ? "กลุ่มออนไลน์จะแสดงเมื่อเชื่อมต่อห้องเกม" : "Online party controls are available after joining the room."}</p>
{:else if model.party}
	<p class="econ-note">{model.party.members.length}/4 {th ? "สมาชิก" : "members"}{#if model.party.code} · {th ? "รหัส" : "invite"} <strong>{model.party.code}</strong>{/if}</p>
	<ul class="member-list">{#each model.party.members as member}<li><strong>{member.name}</strong>{#if member.id === model.party.leader}<small>{th ? "หัวหน้ากลุ่ม" : "Party leader"}</small>{/if}</li>{/each}</ul>
	<button type="button" class="dialogue-choice" onclick={() => commands.party({ kind: "leave" })}>{th ? "ออกจากกลุ่ม" : "Leave party"}</button>
{:else}
	<button type="button" class="dialogue-choice" onclick={() => commands.party({ kind: "create" })}>{th ? "สร้างกลุ่ม" : "Create party"}</button>
	<form class="social-form" onsubmit={join}><label class="visually-hidden" for="party-code">{th ? "รหัสเชิญกลุ่ม" : "Party invite code"}</label><input id="party-code" value={code} oninput={(event) => { code = event.currentTarget.value.toUpperCase().replace(/[^A-Z0-9]/g, ""); invalid = false; }} maxlength="6" autocomplete="off" spellcheck={false} placeholder={th ? "รหัส 6 ตัว" : "6-character code"} aria-invalid={invalid} /><button type="submit" class="dialogue-choice">{th ? "เข้าร่วม" : "Join"}</button></form>
	{#if invalid}<p class="form-error" role="alert">{th ? "กรอกรหัสเชิญ 6 ตัว" : "Enter a 6-character invite code."}</p>{/if}
{/if}
