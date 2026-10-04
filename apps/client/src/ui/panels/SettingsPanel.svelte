<script lang="ts">
	import { onMount } from "svelte";
	import { observeSettingsPreferences, settingsPanelData } from "../panel-data";
	import type { GraphicsChoice, PanelCommands, PanelSnapshot, SettingsPreferencesSnapshot, UserPreferences, WeatherChoice } from "../panel-types";
	import RoomsPanel from "./RoomsPanel.svelte";
	import { DEFAULT_COMBAT_READABILITY, type CombatReadability, type PanelResourceState } from "../combat-model";
	let { model, commands, readability=DEFAULT_COMBAT_READABILITY, readabilitySupported=false, onReadabilityChanged=()=>{}, roomsResource,roomsRefreshAvailable=false,refreshRooms=()=>{} }: { model: PanelSnapshot; commands: PanelCommands; readability?:CombatReadability; readabilitySupported?:boolean; onReadabilityChanged?:(value:CombatReadability)=>void;roomsResource?:PanelResourceState;roomsRefreshAvailable?:boolean;refreshRooms?:()=>void } = $props();
	let current = $state<SettingsPreferencesSnapshot | null>(null);
	let settings = $derived(current ?? model.settings);
	let th = $derived(model.language === "th");
	const graphicsChoices: Array<{ value: Exclude<GraphicsChoice, null>; label: string }> = [{ value: "low", label: "Low" }, { value: "medium", label: "Medium" }, { value: "high", label: "High" }, { value: "ultra", label: "Ultra" }];
	const weatherChoices: Array<{ value: WeatherChoice; en: string; th: string }> = [{ value: "auto", en: "Automatic", th: "อัตโนมัติ" }, { value: "clear", en: "Clear", th: "ฟ้าโปร่ง" }, { value: "cloudy", en: "Cloudy", th: "เมฆมาก" }, { value: "rain", en: "Rain", th: "ฝน" }, { value: "fog", en: "Fog", th: "หมอก" }];
	onMount(() => observeSettingsPreferences(model.language, (snapshot) => { current = snapshot; }));
	function updatePrefs(change: Partial<UserPreferences>): void {
		const prefs = { ...settings.prefs, ...change };
		current = { ...settings, prefs };
		commands.settingsChanged(prefs);
	}
	function reset(): void { commands.resetSettings(); current = settingsPanelData(model.language); if(readabilitySupported)onReadabilityChanged({...DEFAULT_COMBAT_READABILITY}); }
</script>

<div class="settings-row"><label for="settings-ui-scale">{th ? "ขนาดหน้าจอ UI" : "UI scale"}</label><input id="settings-ui-scale" type="range" min="0.85" max="1.25" step="0.05" value={settings.prefs.uiScale} oninput={(event) => updatePrefs({ uiScale: Number(event.currentTarget.value) })} /><output for="settings-ui-scale" class="settings-value">{Math.round(settings.prefs.uiScale * 100)}%</output></div>
<div class="settings-row"><label for="settings-shake">{th ? "สั่นกล้อง" : "Camera shake"}</label><input id="settings-shake" type="checkbox" checked={readabilitySupported?(readability.screenShake??settings.prefs.shake):settings.prefs.shake} onchange={(event) => {updatePrefs({ shake: event.currentTarget.checked });if(readabilitySupported)onReadabilityChanged({...readability,screenShake:event.currentTarget.checked});}} /></div>
<div class="settings-row"><label for="settings-combat-text">{th?"ขนาดข้อความต่อสู้":"Combat text size"}</label><input id="settings-combat-text" type="range" min="0.8" max="2" step="0.05" value={readability.combatTextScale} disabled={!readabilitySupported} oninput={(event)=>onReadabilityChanged({...readability,combatTextScale:Number(event.currentTarget.value)})}/><output for="settings-combat-text" class="settings-value">{Math.round(readability.combatTextScale*100)}%</output></div>
<div class="settings-row"><label for="settings-low-effects">{th?"ลดเอฟเฟกต์ตกแต่ง":"Reduce decorative effects"}</label><input id="settings-low-effects" type="checkbox" checked={readability.lowEffects} disabled={!readabilitySupported} onchange={(event)=>onReadabilityChanged({...readability,lowEffects:event.currentTarget.checked})}/></div>
<div class="settings-row"><label for="settings-hide-other-effects">{th?"ซ่อนเอฟเฟกต์ตกแต่งของผู้อื่น":"Hide other players' decorative effects"}</label><input id="settings-hide-other-effects" type="checkbox" checked={readability.hideOtherEffects} disabled={!readabilitySupported} onchange={(event)=>onReadabilityChanged({...readability,hideOtherEffects:event.currentTarget.checked})}/></div>
<p class="settings-summary">{th?"วงเตือนอันตราย แถบ HP และสมาชิกปาร์ตี้ต้องยังมองเห็นเสมอ":"Danger warnings, HP plates and party members remain visible."}</p>
{#if !readabilitySupported}<p class="settings-summary">{th?"ตัวเลือกข้อความและเอฟเฟกต์กำลังรอการเชื่อมต่อระบบภาพ":"Combat text and effect controls await renderer integration."}</p>{/if}
<div class="settings-row"><label for="settings-flash">{th ? "แฟลชจอเมื่อได้รับดาเมจ" : "Damage flash"}</label><input id="settings-flash" type="checkbox" checked={settings.prefs.flash} onchange={(event) => updatePrefs({ flash: event.currentTarget.checked })} /></div>
<div class="settings-row"><label for="settings-volume">{th ? "ระดับเสียง" : "Volume"}</label><input id="settings-volume" type="range" min="0" max="1" step="0.05" value={settings.prefs.volume} oninput={(event) => updatePrefs({ volume: Number(event.currentTarget.value) })} /><output for="settings-volume" class="settings-value">{Math.round(settings.prefs.volume * 100)}%</output></div>
<div class="settings-row settings-choice"><label for="settings-graphics">{th ? "คุณภาพภาพ" : "Graphics quality"}</label><select id="settings-graphics" value={settings.graphics ?? "auto"} aria-describedby="settings-graphics-summary" onchange={(event) => commands.graphicsChanged(event.currentTarget.value === "auto" ? null : event.currentTarget.value as Exclude<GraphicsChoice, null>)}><option value="auto">{th ? "อัตโนมัติ (แนะนำ)" : "Auto (recommended)"}</option>{#each graphicsChoices as choice (choice.value)}<option value={choice.value}>{choice.label}</option>{/each}</select></div>
<p id="settings-graphics-summary" class="settings-summary" role="status">{settings.graphicsSummary}</p>
<div class="settings-row settings-choice"><label for="settings-weather">{th ? "สภาพอากาศ" : "Weather"}</label><select id="settings-weather" value={settings.weather} onchange={(event) => commands.environmentChanged({ weather: event.currentTarget.value as WeatherChoice })}>{#each weatherChoices as choice (choice.value)}<option value={choice.value}>{th ? choice.th : choice.en}</option>{/each}</select></div>
<div class="settings-row"><label for="settings-day-night">{th ? "วงจรกลางวันและกลางคืน" : "Day and night cycle"}</label><input id="settings-day-night" type="checkbox" checked={settings.cycle} onchange={(event) => commands.environmentChanged({ cycle: event.currentTarget.checked })} /></div>
<button type="button" class="dialogue-choice settings-reset" onclick={reset}>{th ? "คืนค่าเริ่มต้น" : "Reset to defaults"}</button>
<p class="econ-note">{th ? "การตั้งค่าใช้งานทันทีและบันทึกไว้บนอุปกรณ์นี้เท่านั้น" : "Settings apply immediately and are stored on this device only."}</p>
<RoomsPanel {model} {commands} resource={roomsResource} refreshAvailable={roomsRefreshAvailable} refresh={refreshRooms} />
