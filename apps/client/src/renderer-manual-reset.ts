import type {AbstractEngine} from '@babylonjs/core/Engines/abstractEngine';
import type {WebGPUEngine} from '@babylonjs/core/Engines/webgpuEngine';
import {createManualGraphicsReset} from './renderer-reset-policy.mjs';
const resetRequired=new WeakSet<AbstractEngine>();
export function isRendererResetRequired(engine:AbstractEngine):boolean{return resetRequired.has(engine);}

/** Explicit loss detection: Babylon disables its recovery notifications with A22's engine option. */
export function installManualRendererReset(engine:AbstractEngine):()=>void {
	const canvas=engine.getRenderingCanvas();
	const panel=document.getElementById('renderer-recovery');
	const status=document.getElementById('renderer-recovery-status');
	const reload=document.getElementById('renderer-reload') as HTMLButtonElement|null;
	const thai=document.documentElement.lang.toLowerCase().startsWith('th');
	let disposed=false;
	const controller=createManualGraphicsReset({
		onLost(reason){
			resetRequired.add(engine);
			engine.stopRenderLoop();
			console.error('[graphics-reset]',{reason,automaticRestore:false,requiresReload:true});
			window.dispatchEvent(new Event('aetherfield:renderer-lost'));
			if(panel){panel.hidden=false;panel.setAttribute('role','alert');}
			if(status)status.textContent=thai?'ระบบภาพถูกรีเซ็ต กรุณาโหลดเกมใหม่เพื่อเชื่อมต่อและรับสถานะล่าสุด':'Graphics reset. Reload to reconnect and receive the latest game state.';
			if(reload){reload.hidden=false;reload.disabled=false;reload.textContent=thai?'โหลดเกมและเชื่อมต่อใหม่':'Reload and reconnect';reload.focus({preventScroll:true});}
		},
		onReload(){location.reload();},
	});
	const lose=()=>{if(!disposed && !engine.isDisposed)controller.lost();};
	const onDomLoss=(event:Event)=>{
		// preventDefault opts into a browser-restorable context; this lane deliberately reloads instead.
		if(event.type==='webglcontextlost')lose();
	};
	const onReload=(event:Event)=>{event.preventDefault();controller.reload();};
	canvas?.addEventListener('webglcontextlost',onDomLoss);
	const lostObserver=engine.onContextLostObservable.add(lose);
	// SDK 9.27.1 declares _device, but has no public device-loss accessor. This isolated adapter
	// reads the already-created device only; it does not request an adapter or fingerprint it.
	const device=engine.isWebGPU?(engine as WebGPUEngine)._device:null;
	if(device?.lost)void device.lost.then(info=>{
		if(disposed || engine.isDisposed || info.reason==='destroyed')return;
		controller.lost('webgpu-device-lost');
	});
	reload?.addEventListener('click',onReload);
	const dispose=()=>{
		if(disposed)return;disposed=true;controller.dispose();
		canvas?.removeEventListener('webglcontextlost',onDomLoss);
		engine.onContextLostObservable.remove(lostObserver);
		reload?.removeEventListener('click',onReload);
	};
	engine.onDisposeObservable.addOnce(dispose);
	return dispose;
}
