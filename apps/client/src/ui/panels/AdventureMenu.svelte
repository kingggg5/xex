<script lang="ts">
	import type { PanelCommands, PanelName, PanelSnapshot } from "../panel-types";
	let { model, commands }: { model: PanelSnapshot; commands: PanelCommands } = $props();
	let th = $derived(model.language === "th");
	const entries: Array<{ id: PanelName; en: string; th: string }> = [{ id: "character", en: "Character", th: "ตัวละคร" }, { id: "bag", en: "Bag", th: "กระเป๋า" }, { id: "skills", en: "Skills", th: "สกิล" }, { id: "party", en: "Party", th: "ปาร์ตี้" }, { id: "friends", en: "Friends", th: "เพื่อน" }, { id: "group", en: "Group chat", th: "กลุ่มแชต" }, { id: "map", en: "World map", th: "แผนที่โลก" }, { id: "collection", en: "Field journal", th: "บันทึกการเดินทาง" }, { id:"trade",en:"Trade & players",th:"แลกเปลี่ยน / ผู้เล่น" }, {id:"battlepass",en:"Battle Pass",th:"แบตเทิลพาส"}, {id:"topup",en:"Test Top-up",th:"เติมเงินทดสอบ"}, { id: "store", en: "Store", th: "ร้านค้า" }, { id: "settings", en: "Settings", th: "ตั้งค่า" }, { id: "tower", en: "Tower", th: "หอคอย" }];
</script>

<nav class="adventure-menu-grid" aria-label={th ? "ทางลัดเมนูเกม" : "Game menu shortcuts"}>{#each entries as entry (entry.id)}<button type="button" class="dialogue-choice menu-shortcut" onclick={() => commands.openPanel(entry.id)}>{th ? entry.th : entry.en}</button>{/each}</nav>
