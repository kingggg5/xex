<!-- Incumbent UI preserved for DEV-only screenshot review; live world/server data unchanged. -->
<script lang="ts">
	import { onMount, tick } from "svelte";
	import { floatingPanel, trapDialogKey } from ".././floating-panel";
	import type { ChatTab } from "../../chat";
	import type { UiSnapshot, UiCommands } from ".././types";
	let { view, commands }: { view: UiSnapshot; commands: UiCommands } = $props();
	let draft = $state("");
	let expanded = $state(false);
	let mobile = $state(false);
	let handle: HTMLButtonElement | undefined = $state();
	let root: HTMLDivElement | undefined = $state();
	let input: HTMLInputElement;
	let log: HTMLDivElement;
	const th = $derived(view.language === "th");
	const full = $derived(mobile && expanded);
	const locked = $derived(view.chat.activeTab === "system" || (view.chat.activeTab === "group" && !view.chat.groupAvailable));
	const tabs: ChatTab[] = ["room", "group", "system"];
	const label = (tab: ChatTab) => tab === "room" ? (th ? "โลก" : "World") : tab === "group" ? (th ? "กลุ่ม" : "Party") : (th ? "ระบบ" : "System");
	const close = () => { expanded = false; };
	onMount(() => {
		const media = window.matchMedia("(max-width: 767px), (pointer: coarse) and (max-width: 900px)");
		const changed = () => { mobile = media.matches; };
		changed(); media.addEventListener("change", changed);
		return () => media.removeEventListener("change", changed);
	});
	$effect(() => { commands.chatExpanded(full); return () => commands.chatExpanded(false); });
	$effect(() => { if (view.modal !== null) expanded = false; });
	$effect(() => {
		view.chat.revision;
		void tick().then(() => { if (log?.isConnected) log.scrollTop = log.scrollHeight; });
	});
	$effect(() => { if (full) void tick().then(() => input?.focus()); });
	function submit(event: SubmitEvent) { event.preventDefault(); if (draft.length <= 160 && commands.chatSend(draft)) draft = ""; }
	function tabKey(event: KeyboardEvent) {
		if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
		event.preventDefault(); event.stopPropagation();
		const current = tabs.indexOf(view.chat.activeTab);
		const next = event.key === "Home" ? 0 : event.key === "End" ? 2 : (current + (event.key === "ArrowRight" ? 1 : 2)) % 3;
		commands.chatTab(tabs[next]);
		root?.querySelector<HTMLButtonElement>(`[data-channel="${tabs[next]}"]`)?.focus();
	}
</script>

<div class="chat-ui" class:is-fullscreen={full} class:is-expanded={expanded} role={full ? "dialog" : "region"} aria-modal={full ? "true" : undefined} aria-labelledby="chat-heading" tabindex="-1" bind:this={root} use:floatingPanel={{ handle, target: root?.parentElement ?? undefined }} onkeydown={(event) => { if (full && root) trapDialogKey(event, root, close); }}>
	<header class="chat-heading"><button bind:this={handle} type="button" class="chat-move" aria-label={th ? "เลื่อนหน้าต่างแชต" : "Move chat window"}><span id="chat-heading">{th ? "แชต" : "Chat"}</span></button><button class="chat-expand" type="button" onclick={() => expanded = !expanded} aria-label={expanded ? (th ? "ย่อแชต" : "Collapse chat") : (th ? "ขยายแชต" : "Expand chat")}>{expanded ? "−" : "+"}</button></header>
	<div class="chat-tabs" role="tablist" aria-label={th ? "ช่องแชต" : "Chat channels"}>
		{#each tabs as tab}<button type="button" role="tab" data-channel={tab} class:selected={view.chat.activeTab === tab} class:is-locked={tab === "group" && !view.chat.groupAvailable} aria-selected={view.chat.activeTab === tab} aria-controls="chat-lines" tabindex={view.chat.activeTab === tab ? 0 : -1} onclick={() => commands.chatTab(tab)} onkeydown={tabKey}>{label(tab)}</button>{/each}
	</div>
	<div id="chat-lines" role="log" aria-live="polite" aria-relevant="additions" data-filter={view.chat.activeTab} bind:this={log}>
		{#each view.chat.lines.filter((line) => line.kind === view.chat.activeTab) as line (line.id)}<p data-kind={line.kind}><b class:chat-world={line.kind === "room"} class:chat-party={line.kind === "group"} class:chat-system={line.system || line.kind === "system"}>{line.label}</b> {line.text}</p>{:else}<p class="chat-empty-note">{th ? "ยังไม่มีข้อความในช่องนี้" : "No messages in this channel yet."}</p>{/each}
	</div>
	<form id="chat-form" onsubmit={submit}><label class="sr-only" for="chat-input">{th ? "ส่งข้อความแชต" : "Send a chat message"}</label><input id="chat-input" bind:this={input} bind:value={draft} maxlength="160" autocomplete="off" disabled={locked} placeholder={view.chat.activeTab === "system" ? (th ? "ระบบแจ้งเตือนเท่านั้น" : "System notices only") : locked ? (th ? "เข้าร่วมกลุ่มก่อนเพื่อแชต" : "Join a group to chat here") : (th ? "พูดอะไรสักอย่าง…" : "Say something…")} /><button type="submit" disabled={locked}>{th ? "ส่ง" : "Send"}</button></form>
</div>

<style>
	:global(.chat.svelte-chat-host) { width: min(380px, calc(100vw - 32px)); transform: translate(var(--svelte-offset-x, 0px), var(--svelte-offset-y, 0px)); }
	.chat-ui { display: grid; gap: 6px; }
	.chat-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
	.chat-move, .chat-expand { min-height: 32px; color: #f3ddb0; background: transparent; border: 0; font-size: 13px; }
	.chat-move { cursor: grab; text-align: left; flex: 1; touch-action: none; }
	.chat-expand { min-width: 44px; font-size: 20px; }
	.chat-tabs button { min-height: 36px; min-width: 70px; font-size: 13px; }
	#chat-lines { height: 120px; max-height: 30dvh; }
	#chat-lines p { font-size: 13px; line-height: 1.45; }
	#chat-input { height: 44px; font-size: 14px; }
	#chat-form button { min-height: 44px; min-width: 60px; font-size: 14px; }
	.is-expanded #chat-lines { height: 250px; max-height: 40dvh; }
	button:focus-visible, input:focus-visible { outline: 3px solid #f3d993; outline-offset: 2px; }
	@media (max-width: 767px), (pointer: coarse) and (max-width: 900px) {
		:global(.chat.svelte-chat-host:has(.is-fullscreen)) { position: static; transform: none; backdrop-filter: none; padding: 0; border: 0; background: transparent; }
		.chat-heading button { min-height: 44px; }
		.chat-tabs button { min-height: 44px; font-size: 14px; }
		#chat-lines p, #chat-input, #chat-form button { font-size: 16px; }
		.is-fullscreen { position: fixed; inset: 0; z-index: 30; width: 100vw; height: 100dvh; box-sizing: border-box; display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; padding: max(12px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left)); background: #111a1f; }
		.is-fullscreen #chat-lines { height: auto; max-height: none; }
		.is-fullscreen #chat-lines p { display: block; }
	}
</style>
