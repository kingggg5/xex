<script lang="ts">
	import type { PanelCommands, PanelSnapshot, StatKey } from "../panel-types";
	import EquipmentCopy from "../EquipmentCopy.svelte";
	import PortraitMedallion from "../PortraitMedallion.svelte";
	import "../character-inventory.css";
	import { characterScrollClearance } from "../character-inventory-scroll";
	type Section = "information" | "status" | "equipment" | "allocation";
	let { model, commands, initialSection = "information" }: { model: PanelSnapshot; commands: PanelCommands; initialSection?: Section } = $props();
	const initialTab = () => initialSection;
	let section = $state<Section>(initialTab());
	let selectedSlot = $state<"weapon" | "armor" | null>(null);
	const sections: Array<{ id: Section; en: string; th: string }> = [
		{ id: "information", en: "Character information", th: "ข้อมูลตัวละคร" },
		{ id: "status", en: "Status details", th: "ค่าสเตตัส" },
		{ id: "equipment", en: "Equipped items", th: "อุปกรณ์ที่สวม" },
		{ id: "allocation", en: "Allocate points", th: "เพิ่มค่าสเตตัส" },
	];
	const attributes: Array<{ key: StatKey; name: string; en: string; th: string }> = [
		{ key: "str", name: "STR", en: "+2 ATK per point", th: "+2 ATK ต่อแต้ม" },
		{ key: "agi", name: "AGI", en: "No combat effect yet", th: "ยังไม่มีผลต่อการต่อสู้" },
		{ key: "vit", name: "VIT", en: "+10 max HP per point; +1 DEF per 2 total VIT", th: "+10 HP สูงสุดต่อแต้ม; +1 DEF ทุก 2 VIT รวม" },
		{ key: "int", name: "INT", en: "+5 max SP per allocated point; higher allocations improve SP recovery", th: "+5 SP สูงสุดต่อแต้มที่เพิ่ม; เพิ่มมากขึ้นช่วยฟื้นฟู SP" },
		{ key: "dex", name: "DEX", en: "+1 ATK per 5 allocated points", th: "+1 ATK ทุก 5 แต้มที่เพิ่ม" },
		{ key: "luk", name: "LUK", en: "+1 ATK per 5 allocated points", th: "+1 ATK ทุก 5 แต้มที่เพิ่ม" },
	];
	let th = $derived(model.language === "th");
	let character = $derived(model.character);
	const breakdown = $derived(!!character?.statsBase && !!character?.statsAllocated);
	const selectedEquipment = $derived(model.selectedInventoryInstanceId ? character?.equipment.find(row => row.instanceId === model.selectedInventoryInstanceId) ?? null : character?.equipment.find(row => row.slot === selectedSlot) ?? character?.equipment[0] ?? null);
	const trialMagic = $derived(character?.combatProfile === "mage_trial" && character.magicPower !== undefined);
	function attributeHelp(key: StatKey, en: string, thai: string): string {
		const base = th ? thai : en;
		if (!trialMagic || (key !== "int" && key !== "dex")) return base;
		return base + (key === "int" ? (th ? "; +2 พลังเวทต่อแต้มที่เพิ่ม" : "; +2 Magic Power per allocated point") : (th ? "; +1 พลังเวททุก 5 แต้มที่เพิ่ม" : "; +1 Magic Power per 5 allocated points"));
	}
	function selectTab(next: Section, origin: HTMLElement): void {
		section = next;
		const content = origin.closest<HTMLElement>(".modal-content");
		if (content) content.scrollTop = 0;
	}
	function tabKey(event: KeyboardEvent, current: Section): void {
		if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
		event.preventDefault(); event.stopPropagation();
		const index = sections.findIndex(row => row.id === current);
		const next = event.key === "Home" ? 0 : event.key === "End" ? sections.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + sections.length) % sections.length;
		const button = event.currentTarget as HTMLButtonElement;
		selectTab(sections[next].id, button);
		button.parentElement?.querySelector<HTMLButtonElement>(`[data-character-tab="${section}"]`)?.focus();
	}
	function chooseEquipment(slot: "weapon" | "armor", instanceId?: string): void {
		selectedSlot = slot;
		if (instanceId) commands.selectInventoryInstance?.(instanceId);
	}
	function openBag(): void {
		if (selectedEquipment?.instanceId) commands.selectInventoryInstance?.(selectedEquipment.instanceId);
		commands.openPanel("bag");
	}
</script>

<div class="character-inventory" data-ui-component="character">
	{#if !character}<p class="character-note">{th ? "กำลังรอข้อมูลตัวละครจากเซิร์ฟเวอร์" : "Waiting for character data"}</p>
	{:else}
		<div class="character-tabs" role="tablist" use:characterScrollClearance aria-label={th ? "หมวดข้อมูลตัวละคร" : "Character sections"}>
			{#each sections as tab (tab.id)}<button type="button" class="character-tab" role="tab" id={`character-tab-${tab.id}`} data-character-tab={tab.id} aria-selected={section === tab.id} aria-controls={`character-section-${tab.id}`} tabindex={section === tab.id ? 0 : -1} onclick={event => selectTab(tab.id, event.currentTarget)} onkeydown={event => tabKey(event, tab.id)}>{th ? tab.th : tab.en}</button>{/each}
		</div>
		{#each sections.filter(tab => tab.id !== section) as tab (tab.id)}<div role="tabpanel" id={`character-section-${tab.id}`} aria-labelledby={`character-tab-${tab.id}`} hidden></div>{/each}
		<div class="character-section" role="tabpanel" id={`character-section-${section}`} aria-labelledby={`character-tab-${section}`} tabindex="0">
			{#if section === "information"}
				<div class="character-summary"><div class="character-portrait" aria-hidden="true"><PortraitMedallion initial={character.name.slice(0, 1).toLocaleUpperCase(model.language)} /></div><div><h3 class="character-name">{character.name}</h3>{#if character.handle}<p class="character-subtitle">@{character.handle}</p>{/if}{#if character.vocation}<p class="character-subtitle">{th ? "อาชีพ" : "Class"}: {character.vocation === "trailblade" ? (th ? "นักดาบทุ่ง" : "Trailblade") : character.vocation}</p>{/if}{#if character.combatProfile === "mage_trial"}<p class="character-trial">{th ? "เปิดการทดลองต่อสู้แบบ Mage" : "Mage combat trial active"}</p>{/if}</div></div>
				<dl class="character-values"><div><dt>{th ? "เลเวลพื้นฐาน" : "Base level"}</dt><dd>{character.level}</dd></div><div><dt>{th ? "เลเวลอาชีพ" : "Job level"}</dt><dd>{character.jobLevel}</dd></div><div><dt>{th ? "พลังชีวิต" : "HP"}</dt><dd>{character.hp} / {character.maxHp}</dd></div>{#if character.sp !== null && character.maxSp !== null}<div><dt>SP</dt><dd>{character.sp} / {character.maxSp}</dd></div>{/if}</dl>
				<div class="character-exp"><div><div class="character-exp-label"><span>{th ? "EXP พื้นฐาน" : "Base EXP"}</span><span>{character.baseExp} / {character.baseExpNext}</span></div><progress value={character.baseExp} max={character.baseExpNext} aria-label={th ? "EXP พื้นฐาน" : "Base EXP"}></progress></div><div class="job-exp"><div class="character-exp-label"><span>{th ? "EXP อาชีพ" : "Job EXP"}</span><span>{character.jobExp} / {character.jobExpNext}</span></div><progress value={character.jobExp} max={character.jobExpNext} aria-label={th ? "EXP อาชีพ" : "Job EXP"}></progress></div></div>
			{:else if section === "status"}
				<h3>{th ? "ค่าสเตตัสและพลังต่อสู้" : "Attributes and combat values"}</h3>
				<table class="character-stat-table"><thead><tr><th scope="col">{th ? "ค่าสเตตัส" : "Attribute"}</th>{#if breakdown}<th scope="col">{th ? "พื้นฐาน" : "Base"}</th><th scope="col">{th ? "เพิ่มแล้ว" : "Allocated"}</th>{/if}<th scope="col">{th ? "รวม" : "Total"}</th></tr></thead><tbody>{#each attributes as attribute (attribute.key)}<tr><th scope="row">{attribute.name}<span class="stat-help">{attributeHelp(attribute.key, attribute.en, attribute.th)}</span></th>{#if breakdown}<td>{character.statsBase?.[attribute.key]}</td><td>{character.statsAllocated?.[attribute.key]}</td>{/if}<td>{character.stats[attribute.key]}</td></tr>{/each}</tbody></table>
				<dl class="character-values"><div><dt>{th ? "โจมตี" : "ATK"}</dt><dd>{character.attack}</dd></div><div><dt>{th ? "ป้องกัน" : "DEF"}</dt><dd>{character.defense}</dd></div><div><dt>{th ? "HP สูงสุด" : "Max HP"}</dt><dd>{character.maxHp}</dd></div>{#if character.maxSp !== null}<div><dt>{th ? "SP สูงสุด" : "Max SP"}</dt><dd>{character.maxSp}</dd></div>{/if}{#if trialMagic}<div><dt>{th ? "พลังเวท (ทดลอง)" : "Magic Power (trial)"}</dt><dd>{character.magicPower}</dd></div>{/if}</dl>
				{#if character.equipmentBonus}<h4>{th ? "พลังจากอุปกรณ์และการตีบวก" : "Equipment and refinement contributions"}</h4><dl class="character-values"><div><dt>ATK</dt><dd>+{character.equipmentBonus.attack}</dd></div><div><dt>DEF</dt><dd>+{character.equipmentBonus.defense}</dd></div><div><dt>{th ? "HP สูงสุด" : "Max HP"}</dt><dd>+{character.equipmentBonus.maxHp}</dd></div></dl>{/if}
			{:else if section === "equipment"}
				<h3>{th ? "อุปกรณ์ที่สวม" : "Equipped items"}</h3>
				<dl class="character-values"><div><dt>{th ? "ทอง" : "Gold"}</dt><dd>{character.gold}</dd></div>{#if character.coin !== undefined}<div><dt>{th ? "เหรียญ" : "Coins"}</dt><dd>{character.coin}</dd></div>{/if}</dl>
				<div class="character-equipment-layout">
				<ul class="equipment-copy-list">{#each ["weapon", "armor"] as slot}{@const equipment = character.equipment.find(row => row.slot === slot)}<li>{#if equipment}<EquipmentCopy item={equipment.item} label={equipment.label} instanceId={equipment.instanceId} refine={equipment.refine} location={equipment.slot} kind={equipment.slot} {th} selected={selectedEquipment?.slot === equipment.slot} onselect={() => chooseEquipment(equipment.slot, equipment.instanceId)} />{:else}<div class="empty-slot"><strong>{slot === "weapon" ? (th ? "อาวุธ" : "Weapon") : (th ? "เกราะ" : "Armor")}</strong><span>{th ? "ยังไม่ได้สวม" : "Nothing equipped"}</span></div>{/if}</li>{/each}</ul>
				{#if selectedEquipment}<div class="equipment-detail"><h4>{selectedEquipment.label} +{selectedEquipment.refine}</h4>{#if selectedEquipment.refine < 10}<p class="character-note">{th ? "ค่าตีบวก" : "Refine cost"}: {selectedEquipment.refineCost} {th ? "ทอง" : "gold"} · {th ? "โอกาสสำเร็จ" : "Success chance"}: {selectedEquipment.successPercent}%</p>{:else}<p class="character-note">{th ? "ตีบวกสูงสุดแล้ว" : "Maximum refinement reached"}</p>{/if}{#if selectedEquipment.refine >= 4 && selectedEquipment.refine < 10}<p class="character-note">{th ? "หลัง +4 หากตีบวกล้มเหลวจะเสียทองและลดลง 1 ระดับ แต่ไม่ต่ำกว่า +4" : "After +4, failure spends gold and loses one refinement level, down to +4."}</p>{/if}<div class="equipment-actions"><button class="dialogue-choice" type="button" disabled={!model.online || !selectedEquipment.canRefine} onclick={() => commands.refineItem(selectedEquipment.slot, selectedEquipment.instanceId, selectedEquipment.expectedRevision)}>{th ? "ตีบวกชิ้นนี้" : "Refine this copy"}</button><button class="social-action" type="button" disabled={!model.online || !commands.moveItemInstance || !selectedEquipment.instanceId || selectedEquipment.expectedRevision === undefined} onclick={() => { if (selectedEquipment?.instanceId && selectedEquipment.expectedRevision !== undefined) commands.moveItemInstance?.(selectedEquipment.instanceId, selectedEquipment.expectedRevision, "bag"); }}>{th ? "ถอดลงกระเป๋า" : "Store in bag"}</button></div>{#if selectedEquipment.instanceId}<p class="equipment-id">{th ? "รหัสชิ้น" : "Copy ID"}: {selectedEquipment.instanceId}</p>{/if}</div>{/if}
				{#if !selectedEquipment && character.equipment.length > 0}<p class="character-note">{th ? "เลือกอุปกรณ์ที่สวมเพื่อดูรายละเอียดและจัดการ" : "Select an equipped copy to view its details and actions."}</p>{/if}
				</div>
				<button class="dialogue-choice" type="button" onclick={openBag}>{th ? "เลือกอุปกรณ์ในกระเป๋า (B)" : "Choose equipment from your bag (B)"}</button>
			{:else}
				<h3>{th ? "เพิ่มค่าสเตตัส" : "Allocate stat points"}</h3><p class="allocation-points">{th ? "แต้มคงเหลือ" : "Available points"}: <strong>{character.statPoints}</strong></p><p class="character-note">{th ? "แต่ละครั้งใช้ 1 แต้ม รอผลยืนยันก่อนเพิ่มครั้งต่อไป เมื่อยืนยันแล้วจะคืนแต้มไม่ได้" : "Each increase spends 1 point. Wait for confirmation before the next increase. Confirmed allocations cannot be undone."}</p>
				<div class="allocation-list">{#each attributes as attribute (attribute.key)}<div class="allocation-row"><div><strong>{attribute.name} · {character.stats[attribute.key]}</strong><small>{attributeHelp(attribute.key, attribute.en, attribute.th)}</small></div><button type="button" class="small-action" disabled={!model.online || character.statPoints < 1} aria-label={th ? `เพิ่ม ${attribute.name} 1 แต้ม` : `Allocate 1 point into ${attribute.name}`} onclick={() => commands.allocateStat(attribute.key)}>+</button></div>{/each}</div>
			{/if}
		</div>
	{/if}
</div>
