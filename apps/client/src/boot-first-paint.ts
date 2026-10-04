/** Wait for a visible paint opportunity before requesting the renderer module graph. */
export function afterVisibleBootPaint(signal?:AbortSignal):Promise<boolean>{
	if(signal?.aborted)return Promise.resolve(false);
	return new Promise(resolve=>{
		let frame=0,settled=false;
		const finish=(painted:boolean)=>{
			if(settled)return;settled=true;cancelAnimationFrame(frame);
			document.removeEventListener('visibilitychange',schedule);signal?.removeEventListener('abort',abort);
			resolve(painted);
		};
		const abort=()=>finish(false);
		const schedule=()=>{
			cancelAnimationFrame(frame);
			if(settled || document.visibilityState==='hidden')return;
			frame=requestAnimationFrame(()=>{
				if(document.visibilityState==='hidden'){schedule();return;}
				frame=requestAnimationFrame(()=>{
					if(document.visibilityState==='hidden'){schedule();return;}
					finish(true);
				});
			});
		};
		document.addEventListener('visibilitychange',schedule);signal?.addEventListener('abort',abort,{once:true});schedule();
	});
}
