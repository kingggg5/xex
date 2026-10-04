<script lang="ts">
	import type { PanelSnapshot } from "../panel-types";
	import { COMBAT_ACTIONS } from "../../combat-actions.mjs";
	let { model }: { model: PanelSnapshot } = $props();
	let th = $derived(model.language === "th");
	const skills = COMBAT_ACTIONS.filter(row=>row.player);
</script>

<p class="econ-note">{th ? "สกิลต่อสู้ที่ใช้งานได้ · ปิดหน้าต่างแล้วใช้ปุ่มลัดหรือปุ่มต่อสู้บนหน้าจอ" : "Available combat skills · close this window to use the keyboard shortcuts or combat buttons."}</p>
<dl class="skill-list">{#each skills as skill (skill.key)}<div><dt>{th ? skill.th : skill.en}</dt><dd><kbd>{skill.key}</kbd></dd></div>{/each}</dl>
<p class="econ-note">{th ? "การอัปเกรดสกิลยังไม่เปิดให้ใช้งาน" : "Skill upgrades are not available yet."}</p>
