<script lang="ts">
	import DeviceIcon from "../DeviceIcon.svelte";
	import { sanitizeHandle } from "../../social-parse.mjs";
	import { presenceLabel } from "../panel-data";
	import type { PanelCommands, PanelSnapshot } from "../panel-types";
	let { model, commands }: { model: PanelSnapshot; commands: PanelCommands } = $props();
	let handle = $state("");
	let invalid = $state(false);
	let th = $derived(model.language === "th");
	function add(event: SubmitEvent): void {
		event.preventDefault();
		const clean = sanitizeHandle(handle);
		invalid = !clean;
		if (clean && model.online) { commands.friendAdd(clean); handle = ""; }
	}
</script>

<form class="social-form" onsubmit={add}><label class="visually-hidden" for="friend-handle">{th ? "ไอดีเพื่อน" : "Friend handle"}</label><input id="friend-handle" bind:value={handle} maxlength="24" autocomplete="off" spellcheck={false} placeholder={th ? "ไอดี เช่น abcdef12" : "handle · e.g. abcdef12"} aria-invalid={invalid} /><button type="submit" class="social-action" disabled={!model.online}>{th ? "เพิ่ม" : "Add"}</button></form>
{#if invalid}<p class="form-error" role="alert">{th ? "ไอดีใช้ตัวอักษร ตัวเลข - หรือ _ จำนวน 2–24 ตัว" : "Handles use 2–24 letters, digits, - or _."}</p>{/if}
<p class="econ-note">{th ? "เพิ่มเพื่อนด้วยไอดีของเขา" : "Add a friend by their handle."}</p>
{#if !model.online}<p class="econ-note">{th ? "เชื่อมต่อห้องเกมเพื่อจัดการเพื่อน" : "Join a game room to manage friends."}</p>{/if}
{#if model.friends.length === 0}<p class="econ-note">{th ? "ยังไม่มีเพื่อน — เพิ่มเพื่อนด้วยไอดีได้เลย" : "No friends yet — add someone by handle."}</p>
{:else}<p class="econ-note">{th ? `สมาชิก ${model.friends.length} คน` : `${model.friends.length} ${model.friends.length === 1 ? "member" : "members"}`}</p>
	<div class="social-rows">{#each model.friends as friend}
		<div class="social-row" class:is-online={friend.online} class:is-offline={!friend.online}><span class="social-dot" aria-hidden="true"></span><div class="social-label"><strong><DeviceIcon device={friend.device} thai={th}/>{friend.name}</strong>{#if friend.handle && friend.handle !== friend.name}<small>@{friend.handle}</small>{/if}</div><span class="social-where">{presenceLabel(friend, model.language)}</span><button type="button" class="social-remove" aria-label={th ? `ลบ ${friend.name}` : `Remove ${friend.name}`} disabled={!model.online || !friend.handle} onclick={() => commands.friendRemove(friend.handle)}>×</button></div>
	{/each}</div>
{/if}
<p class="econ-note">{th ? "เพื่อนที่ออนไลน์จะแสดงห้องที่กำลังเล่น หรือชั้นของหอคอย" : "Online friends show the room they play in, or their tower floor."}</p>
