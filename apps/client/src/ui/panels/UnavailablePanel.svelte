<script lang="ts">
	import type { PanelSnapshot } from "../panel-types";
	let { model, name }: { model: PanelSnapshot; name: string } = $props();
	let th = $derived(model.language === "th");
</script>

<p class="econ-note">{name === "trade" ? (th ? "ระบบแลกเปลี่ยนยังไม่เปิดให้ใช้งาน เซิร์ฟเวอร์ยังไม่รองรับรายการแลกเปลี่ยน" : "Trading is unavailable. The server does not provide trade operations yet.") : th ? "หน้าต่างนี้ยังไม่เปิดให้ใช้งาน" : "This panel is not available yet."}</p>
