<script lang="ts">
	import type { PanelSnapshot } from "../panel-types";
	let { model }: { model: PanelSnapshot } = $props();
	let th = $derived(model.language === "th");
</script>

{#if model.online && model.journal}
	<h3>{model.journal.quest}</h3><p class="econ-note">{model.journal.state.replaceAll("_", " ")}</p>
	<dl class="character-details">{#each model.journal.objectives as objective}<div><dt>{objective.label}</dt><dd>{objective.count}</dd></div>{/each}</dl>
{:else}<p class="econ-note">{th ? "ยังไม่มีข้อมูลภารกิจจากเซิร์ฟเวอร์" : "No server quest data is available yet."}</p>{/if}
