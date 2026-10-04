/** CPU sources may be released: a restored context is NOT an intact game. */
export function createManualGraphicsReset({onLost,onReload,schedule=setTimeout,cancel=clearTimeout,enableReloadDelayMs=750}){
	let state='healthy',timer=null;
	return {
		lost(reason='graphics-context-lost'){
			if(state!=='healthy')return false;
			state='lost';onLost(reason);
			return true;
		},
		reload(){
			if(state!=='lost')return false;
			state='reloading';onReload();
			// A blocked navigation must leave a usable manual retry, never an automatic loop.
			timer=schedule(()=>{timer=null;if(state==='reloading')state='lost';},enableReloadDelayMs);
			return true;
		},
		state:()=>state,
		dispose(){if(timer!==null)cancel(timer);timer=null;state='disposed';},
	};
}

/** Bounded local reason, without URLs/device identifiers or opaque objects. */
export function rendererFailureReason(error){
	const name=typeof error?.name==='string'?error.name.slice(0,64):'Error';
	const message=typeof error?.message==='string'?error.message:'WebGPU initialization failed';
	return `${name}: ${message.replace(/(?:https?:\/\/|blob:)[^\s]+/gi,'[URL]').replace(/[\u0000-\u001f]/g,' ').slice(0,240)}`;
}
