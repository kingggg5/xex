<script lang="ts">
	import type { MobileWebAppView } from './types';
	let { model, openGuide, closeGuide }: { model: MobileWebAppView; openGuide(): void; closeGuide(): void } = $props();
	const steps = [
		{ en: 'Open this website in Safari.', th: 'เปิดเว็บไซต์นี้ด้วย Safari' },
		{ en: 'Tap Share.', th: 'แตะปุ่มแชร์ (Share)' },
		{ en: 'Choose Add to Home Screen.', th: 'เลือกเพิ่มไปยังหน้าจอโฮม (Add to Home Screen)' },
		{ en: 'Turn on Open as Web App, if that option is available.', th: 'เปิดตัวเลือก Open as Web App หากมีตัวเลือกนี้' },
		{ en: 'Tap Add.', th: 'แตะเพิ่ม (Add)' },
		{ en: 'Launch Xexoria from its Home Screen icon.', th: 'เปิด Xexoria จากไอคอนบนหน้าจอโฮม' },
	];
</script>

{#if model.portrait || model.guideOpen}
	<div class="mobile-web-app-overlay" role="dialog" aria-modal="true" aria-labelledby="mobile-web-app-title" tabindex="-1" data-mobile-web-app-dialog>
		<div class="mobile-web-app-card" class:guide={model.guideOpen}>
			<img class="app-mark" src="/app-icons/apple-touch-icon180.png" alt="Xexoria" width="100" height="100" />
			<p class="brand-name" aria-hidden="true">XEXORIA</p>
			{#if model.guideOpen}
				<h1 id="mobile-web-app-title">{model.language === 'th' ? 'เพิ่ม Xexoria บนหน้าจอโฮม' : 'Add Xexoria to your Home Screen'}</h1>
				<p class="mobile-web-app-subtitle">{model.language === 'th' ? 'คู่มือสำหรับ iPhone และ iPad · ทำตามขั้นตอนใน Safari' : 'iPhone and iPad guide · follow these steps in Safari'}</p>
				<ol>
					{#each steps as step}<li><span>{model.language === 'th' ? step.th : step.en}</span>{#if model.language === 'th'}<small lang="en">{step.en}</small>{/if}</li>{/each}
				</ol>
				<p>{model.language === 'th' ? 'หลังเปิดจากไอคอน ให้หมุนเครื่องเป็นแนวนอนเพื่อเล่น' : 'After launching from the icon, rotate your device to landscape to play.'}</p>
				<button type="button" onclick={closeGuide} data-mobile-web-app-focus>{model.language === 'th' ? 'ปิดคู่มือ' : 'Close guide'}</button>
			{:else}
				<svg class="rotate-symbol" viewBox="0 0 120 80" fill="none" aria-hidden="true"><rect x="29" y="21" width="62" height="39" rx="7" stroke="currentColor" stroke-width="2.5" /><path d="M37 30v20M17 39C17 21 31 9 49 9m-7-6 7 6-7 6M103 41c0 18-14 30-32 30m7-6-7 6 7 6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
				<h1 id="mobile-web-app-title">{model.language === 'th' ? 'หมุนเครื่องเป็นแนวนอน' : 'Rotate to landscape'}</h1>
				<p class="lead">{model.language === 'th' ? 'แล้วเริ่มการผจญภัยใน Xexoria' : 'Your adventure begins in landscape mode.'}</p>
				{#if model.language === 'th'}<p lang="en" class="mobile-web-app-subtitle">Rotate your device to landscape to play.</p>{/if}
				{#if !model.standalone}<button type="button" class="guide-button" onclick={openGuide} data-mobile-web-app-focus>{model.language === 'th' ? 'วิธีเพิ่มเกมบนหน้าจอโฮม' : 'Home Screen setup'}</button>{/if}
				<p class="desktop-note">{model.language === 'th' ? 'บนคอมพิวเตอร์: ปรับหน้าต่างให้กว้างกว่าสูง' : 'On a computer, make the window wider than it is tall.'}</p>
			{/if}
		</div>
	</div>
{/if}

<style>
	@font-face { font-family: "Xexoria Gate UI"; font-style: normal; font-weight: 400 700; font-display: swap; src: url("../assets/ui/astral-v1/noto-sans-thai-variable.woff2") format("woff2"); unicode-range: U+02D7,U+0303,U+0331,U+0E01-0E5B,U+200C-200D,U+25CC; }
	@font-face { font-family: "Xexoria Gate UI"; font-style: normal; font-weight: 400 700; font-display: swap; src: url("../assets/ui/astral-v1/noto-sans-thai-latin-variable.woff2") format("woff2"); unicode-range: U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD; }
	.mobile-web-app-overlay { --gate-font: "Xexoria Gate UI", -apple-system, BlinkMacSystemFont, "Segoe UI", Tahoma, sans-serif; position: fixed; inset: 0; z-index: 5000; display: grid; place-items: center; overflow: auto; overscroll-behavior: contain; padding: max(32px,env(safe-area-inset-top)) max(24px,env(safe-area-inset-right)) max(32px,env(safe-area-inset-bottom)) max(24px,env(safe-area-inset-left)); background: #080e16; color: #e7edf4; pointer-events: auto; font: 500 17px/1.65 var(--gate-font); text-shadow: none; font-synthesis: none; }
	.mobile-web-app-overlay { color-scheme: dark; scrollbar-color: #4b5f73 #080e16; scrollbar-width: thin; }
	.mobile-web-app-card { width: min(440px,100%); text-align: center; margin: auto; }
	h1,p,li,small,button { font-family: var(--gate-font); text-shadow: none; }
	.app-mark { display: block; width: 100px; height: 100px; border-radius: 22px; margin: 0 auto; background: #000; }
	.brand-name { margin: 14px 0 26px; font-size: 16px; font-weight: 700; letter-spacing: .14em; color: #f0d59c; }
	.rotate-symbol { display: block; width: 120px; height: 80px; margin: 0 auto 24px; color: #a9c9e6; }
	h1 { font-size: clamp(26px,6vw,32px); font-weight: 700; line-height: 1.4; margin: 0 0 10px; color: #fff; text-wrap: balance; letter-spacing: normal; }
	p { margin: 0; } .lead { font-size: 18px; font-weight: 500; color: #d4e1ee; }
	.mobile-web-app-subtitle { margin-top: 8px; font-size: 16px; font-weight: 500; color: #aebfd1; line-height: 1.6; text-wrap: balance; }
	.desktop-note { margin: 22px auto 0; font-size: 16px; font-weight: 500; line-height: 1.65; color: #aebfd1; max-width: 28ch; text-wrap: balance; }
	ol { text-align: left; margin: 26px 0; padding-left: 28px; } li { padding-left: 7px; margin: 17px 0; font-size: 17px; font-weight: 500; line-height: 1.65; } li::marker { color: #f0d59c; font-weight: 700; }
	small { display: block; color: #aebfd1; font-size: 16px; font-weight: 500; line-height: 1.6; margin-top: 4px; }
	button { min-height: 52px; min-width: 44px; max-width: 100%; margin-top: 24px; padding: 12px 22px; border: 1px solid #6488aa; border-radius: 12px; color: #edf6ff; background: #18334e; font-size: 17px; font-weight: 650; line-height: 1.5; cursor: pointer; }
	.guide-button { width: min(320px,100%); margin-top: 30px; } button:hover { background: #214664; } button:active { background: #10283e; } button:focus-visible { outline: 3px solid #a9d6ff; outline-offset: 4px; }
	.guide .brand-name { margin-bottom: 22px; }
	:global([data-mobile-web-app-entry]) { display: block; min-height: 48px; padding: 10px 13px; margin: 12px 0 0; border: 1px solid #6488aa; border-radius: 10px; background: #18334e; color: #edf6ff; font: 600 16px/1.5 "Xexoria Gate UI", system-ui, sans-serif; text-shadow: none; cursor: pointer; }
	:global([data-mobile-web-app-entry]:focus-visible) { outline: 3px solid #a9d6ff; outline-offset: 4px; }
	@media (max-height: 650px) { .mobile-web-app-overlay { align-items: start; } .app-mark { width: 76px; height: 76px; } .brand-name { margin-bottom: 18px; } .rotate-symbol { width: 96px; height: 64px; margin-bottom: 18px; } h1 { font-size: 26px; } }
	@media (prefers-reduced-motion: reduce) { .mobile-web-app-overlay { scroll-behavior: auto; } }
</style>
