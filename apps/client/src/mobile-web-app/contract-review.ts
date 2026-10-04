import { createMobileWebApp } from './controller.svelte.js';
const result = document.getElementById('contract-results')!, summary = document.getElementById('contract-summary')!;
const game = document.getElementById('game')!, content = document.querySelector<HTMLElement>('.modal-content')!;
const view = () => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
const check = (value: unknown, message: string) => { if (!value) throw new Error(message); };
let failures = 0, completed = 0;
async function run(label: string, task: () => void | Promise<void>) {
	const line = document.createElement('li');
	try { await task(); line.className = 'pass'; line.textContent = `PASS · ${label}`; }
	catch (error) { failures++; line.className = 'fail'; line.textContent = `FAIL · ${label}: ${error instanceof Error ? error.message : String(error)}`; }
	completed++; result.append(line);
}
const controller = createMobileWebApp({language:new URLSearchParams(location.search).get('lang')==='th'?'th':'en'});
if (controller.isBlocked()) {
	summary.textContent = 'Portrait policy is correctly active. Run these DOM contracts in a landscape viewport; test real portrait rotation separately.';
	check(game.inert,'Portrait did not make game inert');
} else {
	const callbacks: boolean[] = [], unsubscribe = controller.onBlockedChange(blocked => callbacks.push(blocked));
	await run('Settings entry appears in its own context',async()=>{
		content.innerHTML='<label for="settings-ui-scale">UI scale</label><input id="settings-ui-scale" type="range">'; await view();
		check(content.querySelector('[data-mobile-web-app-context="settings"]'),'Missing Settings guide entry');
	});
	await run('Guide synchronously blocks the game and dispatches original-target Arrow keyup',async()=>{
		const joystick=document.getElementById('joystick')!, held=new Set<string>();
		joystick.addEventListener('keydown',event=>held.add(event.code)); joystick.addEventListener('keyup',event=>held.delete(event.code)); joystick.focus();
		joystick.dispatchEvent(new KeyboardEvent('keydown',{code:'ArrowUp',key:'ArrowUp',bubbles:true})); check(held.size===1,'Fixture did not hold Arrow');
		controller.openGuide(); check(controller.isBlocked()&&game.inert&&callbacks.at(-1)===true,'Guide did not block synchronously'); check(held.size===0,'Original joystick missed keyup');
		await view(); check(document.querySelectorAll('[data-mobile-web-app-dialog] li').length===6,'Guide must contain exactly six Safari steps');
	});
	await run('Guide close restores inert and removes the Settings entry after reused-modal switch',async()=>{
		(document.querySelector('[data-mobile-web-app-dialog] button') as HTMLButtonElement).click(); await view();
		check(!controller.isBlocked()&&!game.inert&&callbacks.at(-1)===false,'Guide close did not release');
		content.innerHTML='<p>Inventory fixture in the same connected modal container</p>'; await view();
		check(!content.querySelector('[data-mobile-web-app-entry]'),'Settings guide leaked into another panel');
		content.innerHTML='<input id="settings-ui-scale" type="range">'; await view(); check(content.querySelectorAll('[data-mobile-web-app-entry]').length===1,'Settings reentry duplicated/missed guide');
	});
	await run('Dispose preserves root host and releases only owned inert state',async()=>{
		unsubscribe(); controller.openGuide(); controller.dispose(); await view(); check(!game.inert,'Owned inert remained');
		check(document.getElementById('mobile-web-app-root'),'Root-owned host was removed'); check(!document.querySelector('[data-mobile-web-app-entry]'),'Owned entries survived disposal');
		game.inert=true; const second=createMobileWebApp({language:'en'}); second.openGuide(); second.dispose(); await view(); check(game.inert,'Pre-existing inert was overwritten'); game.inert=false;
	});
	summary.textContent=`${failures?'FAIL':'PASS'} · ${completed} DOM contracts · ${failures} failures. Synthetic routing only; physical device checks are not qualified.`;
}
