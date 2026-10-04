<script lang="ts">
    import type { DeviceKind } from "../community";
    let {device,thai=false}:{device:DeviceKind;thai?:boolean}=$props();
    let label=$derived(device==="mobile"?(thai?"โทรศัพท์":"Mobile"):device==="desktop"?(thai?"คอมพิวเตอร์":"Computer"):(thai?"ไม่ระบุอุปกรณ์":"Device unknown"));
</script>
{#if device !== "unknown"}<span class="device-icon" role="img" aria-label={label} title={label}><svg viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6">{#if device === "mobile"}<rect x="5.5" y="1.5" width="9" height="17" rx="2"/><path d="M8 15.5h4M8 4h4"/>{:else}<rect x="1.5" y="2.5" width="17" height="11" rx="1.5"/><path d="M10 13.5v4M5 17.5h10"/>{/if}</svg></span>{/if}
<style>.device-icon{display:inline-flex;vertical-align:middle;color:#87d7ef;flex:none;width:16px;height:18px;margin-right:4px}.device-icon svg{width:100%;height:100%}</style>
