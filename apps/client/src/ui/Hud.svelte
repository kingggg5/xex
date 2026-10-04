<script lang="ts">
	import { onMount } from "svelte";
	import HudButton from "./HudButton.svelte";
	import HudMinimap from "./HudMinimap.svelte";
	import HudToasts from "./HudToasts.svelte";
	import HudVitals from "./HudVitals.svelte";
	import MenuIcon from "./MenuIcon.svelte";
	import { movementJoystick } from "./touch-action";
	import type { HudAction, HudCommands, HudSnapshot } from "./hud-types";
	let { view, commands,reviewV1=false }: { view: HudSnapshot; commands: HudCommands;reviewV1?:boolean } = $props();
	let mobile = $state(false);
	let compactQuests = $state(false);
	let hudHost: HTMLElement | null = null;
	let hurt = $state(false);
	let hurtTimer = 0;
	const th = $derived(view.language === "th");
	const night = $derived(Number.parseInt(view.timeLabel, 10) >= 18 || Number.parseInt(view.timeLabel, 10) < 6);
	const collapsed = $derived(view.quests.collapsed ?? compactQuests);
	const potionLabel = $derived(th ? `ใช้ยา เหลือ ${view.potion.count}` : `Use potion, ${view.potion.count} available`);
	const mobileOrder: HudAction[] = ["arc_slash", "guard", "dodge", "attack"];
	const menuItems = [
		{ name: "character", label: "Character", thai: "ตัวละคร", icon: "character-icon", key: "C", glyph: "" },
		{ name: "bag", label: "Bag", thai: "กระเป๋า", icon: "bag-icon", key: "B", glyph: "" },
		{ name: "skills", label: "Skills", thai: "ทักษะ", icon: "skill-icon", key: "K", glyph: "" },
		{ name: "friends", label: "Friends", thai: "เพื่อน", icon: "book-icon", key: "J", glyph: "" },
		{ name: "group", label: "Group", thai: "กลุ่ม", icon: "party-icon", key: "P", glyph: "" },
		{ name: "map", label: "Map", thai: "แผนที่", icon: "nav-glyph", key: "M", glyph: "🗺" },
		{ name: "store", label: "Store", thai: "ร้านค้า", icon: "nav-glyph", key: "", glyph: "◉" },
		{ name: "tower", label: "Tower / หอคอย", thai: "หอคอย", icon: "nav-glyph", key: "", glyph: "🗼" },
		{ name: "settings", label: "Settings", thai: "ตั้งค่า", icon: "nav-glyph", key: "", glyph: "⚙" },
	];
	const ratio = (value: number, maximum = 1) => maximum > 0 ? Math.max(0, Math.min(1, value / maximum)) : 0;
	$effect(() => { const online = view.online; hudHost?.classList.toggle("is-online", online); });
	onMount(() => {
		const hurtFlash = () => { hurt = true; window.clearTimeout(hurtTimer); hurtTimer = window.setTimeout(() => { hurt = false; }, 220); };
		window.addEventListener("xexoria:hurt", hurtFlash);
		hudHost = document.getElementById("hud");
		hudHost?.classList.toggle("is-online", view.online);
		const width = window.matchMedia("(max-width: 900px)");
		const touch = window.matchMedia("(any-pointer: coarse)");
		const compact = window.matchMedia("(max-width: 900px) and (max-height: 520px)");
		const changed = () => { mobile = width.matches || touch.matches; compactQuests = compact.matches; };
		changed();
		for (const query of [width, touch, compact]) query.addEventListener("change", changed);
		return () => {
			window.removeEventListener("xexoria:hurt", hurtFlash); window.clearTimeout(hurtTimer);
			for (const query of [width, touch, compact]) query.removeEventListener("change", changed);
			hudHost?.classList.remove("is-online");
			hudHost = null;
		};
	});
</script>

<div id="screen-hurt" class:active={hurt} aria-hidden="true"></div>
{#if view.loadingMessage}<section class="scene-loading" role="status" aria-live="polite"><div class="panel"><span class="loading-sigil" aria-hidden="true">✦</span><p>{view.loadingMessage}</p><small>{th ? "กำลังเตรียมโมเดลและแสงเงา" : "Preparing models and lighting"}</small></div></section>{/if}
<div id="performance-stats" aria-label={th ? "ประสิทธิภาพเกม" : "Game performance"} data-ui-component="hud">
	<span>FPS <b id="performance-fps">{view.fps !== null && view.fps > 0 ? Math.round(view.fps) : "—"}</b></span>
	<span>Ping <b id="performance-ping">{view.pingMs !== null && view.pingMs >= 0 ? `${Math.round(view.pingMs)} ms` : "—"}</b></span>
</div>
<HudVitals player={view.player} {th} {reviewV1}/>

<section class="party panel" class:has-party={!view.party.preview && view.party.members.length > 0}
	class:is-empty={view.party.members.length === 0 || (view.online && view.party.preview)} aria-label={th ? "สมาชิกกลุ่ม" : "Party members"}>
	<div class="panel-kicker">{th ? "กลุ่ม" : view.party.preview ? "FIELD PARTY" : "PARTY"}<span>{view.party.members.length} / 4</span></div>
	{#each view.party.members as member (member.id)}
		<div class="party-member"><span class={`party-face face-${member.face}`}>{member.name.slice(0, 1).toUpperCase()}</span>
			<span class="party-detail"><b>{member.name}</b>
				{#if !view.online && member.hpRatio !== null}<i><em style={`width:${ratio(member.hpRatio) * 100}%`}></em></i>
				{:else if member.role}<small>{member.role}</small>{/if}
			</span>{#if !view.online && member.level !== null}<small>{member.level}</small>{/if}
		</div>
	{/each}
	{#if view.party.inviteText}<small class="party-invite">{view.party.inviteText}</small>{/if}
</section>
<button class="compact-party-trigger panel" type="button"
    hidden={view.party.members.length === 0 || (view.online && view.party.preview)}
    aria-label={th ? `เปิดปาร์ตี้ สมาชิก ${view.party.members.length} คน` : `Open party, ${view.party.members.length} members`}
    onclick={() => commands.openModal("party")}>
    <span>{th ? "ปาร์ตี้" : "Party"}</span><b>{view.party.members.length} / 4</b>
</button>

<section class="world-info" aria-label={th ? "สถานะโลก" : "World status"}>
	<div class="location"><span class="location-mark" aria-hidden="true"></span><span><b>{view.locationName}</b>
		<small id="connection-label" class:is-offline={!view.online}>{view.connectionLabel}</small>
		<small id="session-note" hidden={view.sessionNote === null}>{view.sessionNote ?? ""}</small></span></div>
	{#if view.modeNote}<small class="hud-mode-note" role="status">{view.modeNote}</small>{/if}
	<div class="world-clock"><span id="weather-icon" class="sun-icon" class:night-icon={night} aria-hidden="true"></span><span id="world-time">{view.timeLabel}</span></div>
</section>

<div class="top-actions">
	<button class="icon-button panel" id="bag-button" type="button" aria-label={th ? "เปิดกระเป๋า" : "Open bag"} title={th ? "กระเป๋า (B)" : "Bag (B)"} onclick={() => commands.openModal("bag")}><span class="bag-icon" aria-hidden="true"></span><small>{th ? "กระเป๋า" : "Bag"}</small></button>
	<button class="icon-button panel" id="menu-button" type="button" aria-label={th ? "เปิดเมนู" : "Open menu"} title={th ? "เมนู (Esc)" : "Menu (Esc)"} onclick={() => commands.openModal("menu")}><span class="menu-icon" aria-hidden="true"></span><small>{th ? "เมนู" : "Menu"}</small></button>
	<button class="icon-button panel fullscreen-button" id="fullscreen-button" type="button" hidden={!view.fullscreenAvailable} aria-pressed={view.fullscreenActive} aria-label={th ? view.fullscreenActive ? "ออกจากเต็มหน้าจอ" : "เล่นเต็มหน้าจอ" : view.fullscreenActive ? "Exit fullscreen" : "Play fullscreen"} onclick={() => commands.fullscreen()}><span class="fullscreen-icon" aria-hidden="true">⛶</span><small>{th ? "เต็มจอ" : "Full"}</small></button>
</div>

<aside class="right-rail" aria-label={th ? "แผนที่และภารกิจ" : "Map and quests"}>
    <button class="compact-quests-trigger panel" type="button"
        aria-label={th ? "เปิดบันทึกภารกิจ" : "Open quest journal"}
        onclick={() => commands.openModal("collection")}>
        <span>{th ? "ภารกิจ" : "Quests"}</span><b>{view.quests.loadingText ? "—" : view.quests.items.length}</b>
    </button>
	<section class="map-panel panel" aria-label={th ? "แผนที่พื้นที่" : "Area map"}>
		<HudMinimap model={view.minimap} preview={!view.online} language={view.language} locationName={view.locationName} label={th ? "เปิดแผนที่โลก" : "Open world map"} onopen={() => commands.openModal("map")} />
	</section>
	<section class="quests panel" class:is-collapsed={collapsed} aria-label={th ? "ติดตามภารกิจ" : "Quest tracker"}>
		<div class="quest-header"><span>{th ? "ภารกิจปัจจุบัน" : "ACTIVE QUESTS"}</span><button id="quest-toggle" type="button" aria-controls="quest-list" aria-expanded={!collapsed} aria-label={th ? collapsed ? "ขยายภารกิจ" : "ย่อภารกิจ" : collapsed ? "Expand quests" : "Collapse quests"} onclick={() => commands.questsCollapsed(!collapsed)}>{collapsed ? "+" : "−"}</button></div>
		<div id="quest-list">
			{#if view.quests.loadingText}<p class="quest-loading" role="status">{view.quests.loadingText}</p>
			{:else}{#each view.quests.items as quest (quest.id)}<article class="quest"><span class="quest-gem" aria-hidden="true"></span><div><b>{quest.title}</b><small>{quest.description}</small></div><strong id={quest.progressId ?? undefined}>{quest.progress}</strong></article>{/each}{/if}
		</div>
	</section>
</aside>
<button id="context-action" class="context-action panel" type="button" hidden={view.contextLabel === null} disabled={view.inputBlocked} aria-label={view.contextLabel ? `${view.contextLabel} (E)` : th ? "โต้ตอบ" : "Interact"} onclick={() => commands.context()}>{view.contextLabel ? `${view.contextLabel} · E` : ""}</button>

<HudToasts entries={view.toasts} />
<section id="rotate-device" role="status" aria-live="polite">
	<span class="rotate-device-icon" aria-hidden="true"></span><b id="rotate-device-title">{view.rotateTitle}</b><p id="rotate-device-copy">{view.rotateCopy}</p>
	{#if view.fullscreenAvailable && !view.fullscreenActive}<button type="button" class="rotate-fullscreen" onclick={() => commands.fullscreen()}>{th ? "เล่นเต็มหน้าจอ" : "Play fullscreen"}</button>{/if}
</section>

<section class="desktop-hotbar panel" aria-label={th ? "ทักษะต่อสู้" : "Combat skills"}>
	<div class="weapon-wheel" aria-hidden="true"><span>✦</span></div>
	{#each view.abilities as ability (ability.action)}<HudButton label={ability.label} buttonClass={`skill-slot${ability.action === "attack" ? " primary" : ""}`} keyText={ability.key} art={ability.art} action={ability.action} description={ability.description} spCost={ability.spCost} rangeM={ability.rangeM}
		readyAtMs={ability.readyAtMs} cooldownDurationMs={ability.cooldownDurationMs} disabled={view.inputBlocked || ability.disabled} visible={!mobile} {th} onactivate={() => commands.action(ability.action)} />{/each}
	<div class="hotbar-divider"></div>
	<HudButton label={potionLabel} buttonClass="potion-slot" keyText={String(view.potion.count)} id="potion-button" countId="potion-count" potion pending={view.potion.pending} disabled={view.inputBlocked || view.potion.unavailable || view.potion.count <= 0} readyAtMs={view.potion.readyAtMs} cooldownDurationMs={view.potion.cooldownDurationMs} visible={!mobile} {th} onactivate={() => commands.potion()} />
	<span class="hotbar-hint">{th ? "WASD เคลื่อนที่ · ลากเพื่อหมุนมุมมอง" : "WASD MOVE · DRAG TO ORBIT"}</span>
</section>

<section class="mobile-controls" aria-label={th ? "ปุ่มควบคุมสัมผัส" : "Touch controls"}>
	<button class="joystick" id="joystick" type="button" aria-label={th ? "จอยเสมือนสำหรับเคลื่อนที่ ใช้ปุ่มลูกศรได้" : "Virtual movement joystick, arrow keys supported"} disabled={view.inputBlocked}
		use:movementJoystick={{ enabled: mobile && !view.inputBlocked, resetVersion: view.inputResetVersion, move: (x, z) => commands.movement(x, z) }}>
		<span class="joystick-ring"><span class="joystick-knob" id="joystick-knob"></span></span>
	</button>
	<div class="mobile-actions">
		{#each mobileOrder as action (action)}{@const ability = view.abilities.find((entry) => entry.action === action)}
			{#if ability}<HudButton label={ability.label} buttonClass={`mobile-skill ${action === "attack" ? "attack-large" : "skill-mini"}`} keyText={action === "attack" ? "ATK" : action === "dodge" ? "↗" : ability.key} art={ability.art} action={ability.action} description={ability.description} spCost={ability.spCost} rangeM={ability.rangeM} readyAtMs={ability.readyAtMs} cooldownDurationMs={ability.cooldownDurationMs} disabled={view.inputBlocked || ability.disabled} visible={mobile} mobile {th} onactivate={() => commands.action(ability.action)} />{/if}
		{/each}
		<HudButton label={potionLabel} buttonClass="mobile-skill potion-mini" keyText={String(view.potion.count)} id="mobile-potion" countId="mobile-potion-count" potion pending={view.potion.pending} disabled={view.inputBlocked || view.potion.unavailable || view.potion.count <= 0} readyAtMs={view.potion.readyAtMs} cooldownDurationMs={view.potion.cooldownDurationMs} visible={mobile} mobile {th} onactivate={() => commands.potion()} />
	</div>
</section>

<div class="bottom-nav panel" aria-label={th ? "เมนูเกม" : "Game menu"}>
	{#each menuItems as item (item.name)}<button type="button" data-modal={item.name} onclick={() => commands.openModal(item.name)}><span class="nav-symbol"><MenuIcon name={item.name} /></span><small>{th ? item.thai : item.label}</small>{#if item.key}<kbd>{item.key}</kbd>{/if}</button>{/each}
</div>
<div class="progress-footer"><span id="footer-level">{view.player.footerLevel}</span><span id="footer-job">{view.player.footerJob}</span><b id="footer-xp">{view.player.footerExp}</b><i><em id="footer-xp-fill" style={`--progress:${ratio(view.player.expRatio)}`}></em></i><span id="renderer-label">{view.rendererLabel}</span></div>
<div id="connection-toast" class="connection-toast" class:is-hidden={view.connectionMessage === null} role="status">{view.connectionMessage ?? ""}</div>

<style>
	.scene-loading { position: absolute; inset: 0; z-index: 18; display: grid; place-items: center; background: #12232bf5; pointer-events: auto; }
	.scene-loading > div { padding: 26px 36px; max-width: calc(100vw - 32px); text-align: center; color: #f3ddb0; }
	.loading-sigil { display: block; font-size: 38px; }
	.scene-loading p { font-size: 18px; margin: 12px 0 8px; }
	.world-info { right: 220px; }
	.hud-mode-note { display: block; max-width: 170px; padding: 3px 7px; border: 1px solid #597b9c; border-radius: 2px; color: #c6e8f6; background: #132d43; font-size: 11px; line-height: 1.45; white-space: normal; }
	.joystick { padding: 0; border: 0; border-radius: 50%; background: transparent; cursor: move; }
	.party-detail { min-width: 0; }
	.party-detail b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.quest-header button { min-width: 44px; min-height: 44px; }
	.quest-loading { margin: 10px 0; color: #d7d4c8; font-size: 11px; line-height: 1.4; }
	.fullscreen-icon { font-size: 25px; line-height: 19px; color: #dfcf9f; }
	.rotate-fullscreen { min-width: 144px; min-height: 44px; padding: 8px 15px; border: 1px solid #d6bd7c; border-radius: 7px; background: #292e2e; color: #fff1c7; cursor: pointer; }
	@media (max-width: 700px) {
		.world-info { right: auto; left: 50%; max-width: calc(100vw - 320px); }
		.location { min-width: 0; }
		.location > span:last-child { min-width: 0; }
		.location b, .location small { overflow: hidden; text-overflow: ellipsis; }
		.world-clock { display: none; }
	}
	@media (max-width: 540px) {
		.world-info { left: max(10px, env(safe-area-inset-left)); right: 155px; max-width: none; transform: none; }
		.player-card { top: calc(env(safe-area-inset-top) + 64px); }
	}
	@media (max-height: 520px) and (max-width: 900px) {
		.quests { max-height: 54px; }
		.quests:not(.is-collapsed) { max-height: 135px; }
	}
</style>
