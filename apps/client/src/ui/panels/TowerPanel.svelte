<script lang="ts">
	import type { PanelCommands, PanelSnapshot } from "../panel-types";
	let { model, commands }: { model: PanelSnapshot; commands: PanelCommands } = $props();
	let th = $derived(model.language === "th");
</script>

<p class="panel-kicker">{th ? "หอคอย · 100 ชั้น" : "TOWER · 100 FLOORS"}</p>
<dl class="tower-stats"><div class="tower-stat" class:is-inside={model.tower.inTower}><dt>{th ? "ชั้นปัจจุบัน" : "Current floor"}</dt><dd>{model.tower.inTower ? (th ? `ชั้น ${model.tower.floor}` : `Floor ${model.tower.floor}`) : th ? "อยู่นอกหอคอย" : "Outside"}</dd></div><div class="tower-stat"><dt>{th ? "ชั้นสูงสุด" : "Best floor"}</dt><dd>{th ? `ชั้น ${model.tower.bestFloor}` : `Floor ${model.tower.bestFloor}`}</dd></div></dl>
<button type="button" class="tower-enter" disabled={!model.online} onclick={commands.towerEnter}>{th ? "เข้าสู่หอคอย" : "Enter the Tower"}</button>
<small class="tower-hint">{model.tower.inTower ? (th ? "คุณอยู่ในหอคอย — การออกจะพาคุณกลับสู่ฟรอนเทียร์" : "You are inside the tower — leaving returns you to the frontier.") : th ? "เริ่มปีนที่ชั้น 1" : "Enter at floor 1"}</small>
{#if model.tower.inTower}<button type="button" class="tower-leave" disabled={!model.online} onclick={commands.towerLeave}>{th ? "ออกจากหอคอย" : "Leave the Tower"}</button>{/if}
<p class="econ-note">{th ? "รางวัลตามชั้นจะเข้ากระเป๋าเงินโดยอัตโนมัติ ส่วนการโจมตีของศัตรูในหอคอยจะมาพร้อมไมล์สโตนระบบต่อสู้ถัดไป" : "Floor rewards feed your wallet automatically. Enemy attacks inside the tower arrive with the next combat milestone."}</p>
