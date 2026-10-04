<script lang="ts">
	import CombatOverlay from "./CombatOverlay.svelte";
	import type { UiSnapshot, UiCommands } from "./types";
	let { view, commands }: { view: UiSnapshot; commands: UiCommands } = $props();
</script>
<CombatOverlay view={view.combat} death={view.death} language={view.language} returnToTown={commands.returnToTown} worldSuspended={view.modal != null}/>
