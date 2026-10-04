<script lang="ts">
	import type { PanelCommands, PanelSnapshot } from "../panel-types";
	let { model, commands }: { model: PanelSnapshot; commands: PanelCommands } = $props();
	let th = $derived(model.language === "th");
	function select(id: string): void {
		const dialogue = model.dialogue;
		if (!dialogue) return;
		if (id === "claim") commands.claim(dialogue.quest);
		else commands.choose(dialogue.npc, dialogue.token, id);
		commands.closeModal();
	}
</script>

{#if model.dialogue}
	<p class="dialogue-line">{model.dialogue.text}</p>
	<div class="dialogue-choices">{#each model.dialogue.choices as choice}<button type="button" class="dialogue-choice" onclick={() => select(choice.id)}>{choice.label}</button>{/each}
		{#if model.dialogue.choices.length === 0}<button type="button" class="dialogue-choice" onclick={commands.closeModal}>{th ? "ปิด" : "Close"}</button>{/if}
	</div>
{/if}
