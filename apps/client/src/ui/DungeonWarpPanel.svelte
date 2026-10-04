<script lang="ts">
	import {tick} from 'svelte';
	import MenuIcon from './MenuIcon.svelte';
	import {DUNGEON_DESTINATIONS,warpDestinationEnabled} from '../dungeon-warp-policy.mjs';
	interface State {near:boolean;open:boolean;loading:boolean;connected:boolean;busy:boolean;error:string}
	let {state:view,th,onOpen,onClose,onEnterTower}:{state:State;th:boolean;onOpen:()=>void;onClose:()=>void;onEnterTower:()=>void}=$props();
	let dialog=$state<HTMLElement>(),closeButton=$state<HTMLButtonElement>();
	$effect(()=>{if(view.open)void tick().then(()=>{if(view.open&&closeButton?.isConnected)closeButton.focus();});});
	function key(event:KeyboardEvent){
		if(event.key==='Escape'){event.preventDefault();onClose();return;}
		if(event.key!=='Tab'||!dialog)return;
		const buttons=[...dialog.querySelectorAll<HTMLElement>('button:not(:disabled),[tabindex="0"]')];
		const first=buttons[0],last=buttons.at(-1);
		if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
		else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
	}
</script>
{#if view.near&&!view.open}
	<button class="warp-open" data-warp-hub-open onclick={onOpen}><span aria-hidden="true">✧</span>{th?'จุดวาร์ป · เลือกดันเจียน':'Warp gate · choose destination'}</button>
{/if}
{#if view.open}
	<div class="warp-backdrop">
		<div class="warp-panel" role="dialog" aria-modal="true" aria-labelledby="warp-title" tabindex="-1" bind:this={dialog} onkeydown={key}>
			<header><div><small>XEXORIA · WAYGATE</small><h2 id="warp-title">{th?'เส้นทางสู่ดันเจียน':'Dungeon waygate'}</h2></div><button bind:this={closeButton} aria-label={th?'ปิดจุดวาร์ป':'Close warp gate'} onclick={onClose}>×</button></header>
			<p class="warp-copy">{th?'เลือกปลายทางที่พร้อมใช้งาน ระบบจะให้เซิร์ฟเวอร์ย้ายคุณไปยังห้องที่ถูกต้อง':'Choose a ready destination. The server assigns your destination instance.'}</p>
			{#if view.loading}<p role="status">{th?'กำลังตรวจสอบปลายทาง…':'Checking destinations…'}</p>{/if}
			{#each DUNGEON_DESTINATIONS as destination}
				{@const enabled=warpDestinationEnabled(destination.id,{connected:view.connected,busy:view.busy})}
				<button class="destination" disabled={!enabled||view.loading} onclick={onEnterTower} data-warp-destination={destination.id}>
					<span class="destination-rune" aria-hidden="true"><MenuIcon name={destination.kind==='live-tower'?'tower':'map'} /></span><span><b>{th?destination.thai:destination.name}</b><small>{th?destination.thaiDescription:destination.description}</small></span>
					<span class="destination-state">{destination.kind==='planned'?(th?'ยังไม่เปิด':'Coming soon'):view.connected?(th?'พร้อมเข้า':'Ready'):(th?'ต้องเชื่อมต่อ':'Connect first')}</span>
				</button>
			{/each}
			{#if view.busy}<p role="status">{th?'กำลังขอห้องจากเซิร์ฟเวอร์…':'Requesting a server instance…'}</p>{/if}
			{#if view.error}<p class="warp-error" role="alert">{view.error}</p>{/if}
			<footer>{th?'แมพที่กำลังพัฒนาจะเปิดเมื่อฉากและเส้นทางกลับพร้อมแล้ว':'Future destinations unlock when their scene and return route are ready.'}</footer>
		</div>
	</div>
{/if}
<style>
	.warp-open{position:fixed;left:50%;bottom:170px;transform:translateX(-50%);z-index:16;min-height:44px;padding:10px 18px;border:1px solid #d0b578;border-radius:12px;background:#102437ef;color:#f2e5c3;font:inherit;cursor:pointer}.warp-open span{color:#85d2e9;margin-right:10px}
	.warp-backdrop{position:fixed;inset:0;z-index:80;background:#071421b8;display:grid;place-items:center;padding:16px}.warp-panel{width:min(580px,100%);max-height:calc(100dvh - 32px);overflow:auto;border:1px solid #b9a36d;border-radius:16px;padding:22px;background:linear-gradient(145deg,#183349,#0b1828);color:#e5edf1;box-shadow:0 18px 60px #0008;font:inherit}.warp-panel header{display:flex;justify-content:space-between;gap:16px;align-items:center}.warp-panel header small{color:#bcd7e2;letter-spacing:.12em;font-size:11px}.warp-panel h2{margin:4px 0;font-size:24px;color:#e3c991}.warp-panel header button{width:44px;height:44px;border:1px solid #bba476;border-radius:9px;background:#193248;color:#f0e2c4;font-size:24px;cursor:pointer}.warp-copy{line-height:1.6;font-size:14px}.destination{display:flex;align-items:center;gap:14px;width:100%;padding:15px;margin:12px 0;border:1px solid #91835d;border-radius:12px;background:#12283b;color:#f1e5c8;text-align:left;font:inherit;cursor:pointer}.destination:disabled{color:#a2b2bc;border-color:#50616e;background:#132331;cursor:default}.destination-rune{width:32px;min-width:32px;height:32px;display:grid;place-items:center;color:#99d2e9}.destination-rune :global(svg){width:32px;height:32px}.destination b{display:block;font-size:16px}.destination small{display:block;margin-top:5px;font-size:12px;color:#bdcdd7}.destination-state{margin-left:auto;font-size:12px;white-space:nowrap}.warp-panel footer{font-size:12px;line-height:1.6;color:#b5c8d5}.warp-error{color:#f8ad9e;font-size:14px}.warp-panel button:focus-visible,.warp-open:focus-visible{outline:3px solid #b2e1f3;outline-offset:3px}
	@media(max-height:520px){.warp-panel{padding:14px 18px;max-height:calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom) - 20px)}.warp-panel h2{font-size:20px}.destination{padding:10px;margin:8px 0}.warp-open{bottom:125px;font-size:12px}}
</style>
