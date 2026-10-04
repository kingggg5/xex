import {createPerfCollector,perfRequested,type PerfFrame,type PerfState,type PerfCompact} from "./collector.mjs";

export interface PerfOverlayOptions {
	search?:string;readState?:()=>PerfState;now?:()=>number;language?:"th"|"en";
	build?:string;platformVersion?:string;localGpuName?:string;capacity?:number;warmupFrames?:number;
	onInteraction?:()=>void;
}
export interface PerfOverlay {
	recordFrame(frame:PerfFrame):boolean;contextLost():void;contextRestored():void;reset():void;mark(label:string):boolean;
	snapshot():unknown;history():unknown[];exportJson():string;dispose():void;
}
declare global {interface Window {__xexPerf?:{snapshot():unknown;history():unknown[];reset():void;mark(label:string):boolean};}}
const bounded=(value:unknown,size=128)=>typeof value==="string"?(value.replace(/[\u0000-\u001f\u007f]/g," ").trim().slice(0,size)||null):null;
const ms=(value:number|null|undefined)=>typeof value==="number"&&Number.isFinite(value)?value.toFixed(1):"UNAVAILABLE";
const count=(value:number|null|undefined)=>typeof value==="number"&&Number.isFinite(value)?Math.round(value).toLocaleString():"UNAVAILABLE";

/** Debug overlay only. No renderer loop/requester, hardware fingerprint query or transmission. */
export function installPerfOverlay(options:PerfOverlayOptions={}):PerfOverlay|null {
	if(!perfRequested(options.search??location.search))return null;
	const now=options.now??(()=>performance.now()),th=options.language==="th";
	const collector=createPerfCollector({capacity:options.capacity,warmupFrames:options.warmupFrames,startAtMs:now()});
	let disposed=false,expanded=false,lastPoll=-Infinity;
	const root=document.createElement("section");root.id="xexoria-perf";root.setAttribute("aria-label",th?"ข้อมูลประสิทธิภาพเฉพาะเครื่อง":"Local performance diagnostics");
	root.style.cssText="position:fixed;left:calc(env(safe-area-inset-left) + 4px);top:calc(env(safe-area-inset-top) + 28px);z-index:2000;width:min(340px,calc(100vw - env(safe-area-inset-left) - env(safe-area-inset-right) - 8px));max-height:calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom) - 36px);overflow:auto;background:rgba(8,14,18,.94);color:#edf2e5;font:11px/1.45 ui-monospace,monospace;font-variant-numeric:tabular-nums;box-sizing:border-box;pointer-events:none;-webkit-text-size-adjust:100%";
	const button=(label:string,action:()=>void)=>{const node=document.createElement("button");node.type="button";node.textContent=label;node.style.cssText="min-height:44px;min-width:44px;padding:6px 8px;color:#fff1d2;background:#1c3444;border:1px solid #8e805f;font:inherit;cursor:pointer;pointer-events:auto";node.addEventListener("click",()=>{options.onInteraction?.();action();});return node;};
	const heading=button("PERF · warming",()=>{expanded=!expanded;body.hidden=!expanded;heading.setAttribute("aria-expanded",String(expanded));});heading.style.width="100%";heading.style.textAlign="left";heading.id="perf-toggle";heading.setAttribute("aria-expanded","false");
	const body=document.createElement("div");body.hidden=true;body.style.padding="8px";
	const data=document.createElement("dl");data.style.cssText="margin:0;display:grid;gap:5px;pointer-events:none";
	const fields=new Map<string,HTMLElement>();
	for(const key of ["Renderer","FPS / cap","Frame p50 / p95","CPU scene p50 / p95","GPU","Rendered / output","CSS / DPR","FSR / raw rAF","Draws / tris / particles","Context lost / restored","Visible / focused","Window / elapsed"]){const row=document.createElement("div"),label=document.createElement("dt"),value=document.createElement("dd");label.textContent=key;label.style.color="#b6cbd4";value.style.cssText="margin:0;overflow-wrap:anywhere";row.append(label,value);data.append(row);fields.set(key,value);}
	const controls=document.createElement("div");controls.style.cssText="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;pointer-events:auto";
	const status=document.createElement("p");status.setAttribute("role","status");status.style.cssText="margin:8px 0;color:#d9e8ee";
	const text=document.createElement("textarea");text.readOnly=true;text.hidden=true;text.id="perf-json";text.setAttribute("aria-label",th?"ข้อมูล JSON เฉพาะเครื่อง":"Local JSON capture");text.style.cssText="box-sizing:border-box;width:100%;height:120px;resize:vertical;font:11px monospace;background:#101b24;color:#edf2e5;pointer-events:auto";
	const version=document.createElement("input");version.value=bounded(options.platformVersion)??"";version.maxLength=128;version.placeholder=th?"รุ่น iOS / Safari ที่ทราบ":"Known iOS / Safari version";version.setAttribute("aria-label",version.placeholder);version.style.cssText="width:100%;box-sizing:border-box;min-height:44px;margin-top:8px;background:#142735;color:#edf2e5;border:1px solid #607786;padding:6px;pointer-events:auto;font:inherit";
	const gpuName=document.createElement("input");gpuName.value="";gpuName.maxLength=96;gpuName.placeholder=th?"ชื่อ GPU ที่กรอกเอง (ไม่จำเป็น)":"Manual GPU label (optional)";gpuName.setAttribute("aria-label",gpuName.placeholder);gpuName.style.cssText=version.style.cssText;
	// Even caller-supplied GPU labels are omitted by default; explicit local entry opts in.
	if(options.localGpuName)gpuName.placeholder=th?"กรอกป้าย GPU เฉพาะเครื่องเอง":"Enter optional local GPU label";
	const note=document.createElement("p");note.style.cssText="margin:8px 0;color:#b6cbd4";note.textContent=th?"ข้อมูลเฉพาะเครื่อง · ไม่ส่งออกเครือข่าย · GPU ที่อ่านไม่ได้จะแสดง UNAVAILABLE":"Local only · no network transmission · unavailable GPU timings stay UNAVAILABLE";
	function updateField(key:string,value:string){const node=fields.get(key);if(node&&node.textContent!==value)node.textContent=value;}
	function snapshot(){const result=collector.snapshot(now());return {...result,capturedAt:new Date().toISOString(),build:bounded(options.build),device:{platformVersion:bounded(version.value),localGpuName:bounded(gpuName.value,96),source:"Manual labels only; no UA/unmasked renderer probing"},memory:{status:"UNAVAILABLE",reason:"No JS heap, texture or geometry allocation scan is installed"}};}
	function exportJson(){const json=JSON.stringify(snapshot(),null,2);if(new TextEncoder().encode(json).byteLength>131072)throw new Error("Local JSON exceeds its 128 KiB capture bound");return json;}
	function revealJson(){try{text.value=exportJson();text.hidden=false;expanded=true;body.hidden=false;heading.setAttribute("aria-expanded","true");text.focus();text.select();status.textContent=th?"เลือก JSON ไว้แล้ว คัดลอกได้จากช่องนี้":"JSON selected. Copy it locally from this field.";}catch{status.textContent=th?"สร้าง JSON ไม่สำเร็จ":"Could not create bounded JSON.";}}
	const copy=button(th?"คัดลอก JSON":"Copy JSON",()=>{let json:string;try{json=exportJson();}catch{revealJson();return;}if(!navigator.clipboard?.writeText){revealJson();return;}void navigator.clipboard.writeText(json).then(()=>{if(!disposed)status.textContent=th?"คัดลอกข้อมูลเฉพาะเครื่องแล้ว":"Local JSON copied.";},()=>{if(!disposed)revealJson();});});
	controls.append(copy,button(th?"แสดง JSON":"Show JSON",revealJson),button(th?"ทำเครื่องหมาย":"Mark",()=>{collector.mark("manual",now());status.textContent=th?"เพิ่มเครื่องหมายแล้ว":"Local mark added.";}),button(th?"เริ่มวัดใหม่":"Reset",()=>{collector.reset(now());lastPoll=-Infinity;poll();status.textContent=th?"เริ่มหน้าต่างวัดใหม่":"Measurement window reset.";}));
	body.append(data,controls,version,gpuName,note,status,text);root.append(heading,body);document.body.append(root);
	function show(s:PerfCompact){
		const d=s.display,render=`${count(d.renderWidth)}×${count(d.renderHeight)}`,output=`${count(d.outputWidth)}×${count(d.outputHeight)}`;
		const invalid=d.rendererHealth==='BLANK_RENDER'||d.rendererHealth==='INVALID_RENDER';
		const header=invalid?`${d.rendererHealth} · timings invalid`:`${d.renderer??"UNKNOWN"} ${ms(s.frame.actualFps)}/${count(d.targetFps)} p95 ${ms(s.frame.p95)} · ${render}`;
		if(heading.textContent!==header)heading.textContent=header;
		if(!expanded)return;
		updateField("Renderer",`${d.renderer??"UNAVAILABLE"}${d.fallbackReason?` · ${d.fallbackReason}`:""}`);
		updateField("Output health",d.rendererHealth??'UNVERIFIED');
		updateField("FPS / cap",`${ms(s.frame.actualFps)} rendered (rolling) / ${count(d.targetFps)}`);
		updateField("Frame p50 / p95",`${ms(s.frame.p50)} / ${ms(s.frame.p95)} ms · ${s.frame.status}`);
		updateField("CPU scene p50 / p95",`${ms(s.cpu.p50)} / ${ms(s.cpu.p95)} ms`);
		updateField("GPU",s.gpu.status==="available"?`${ms(s.gpu.p50)} / ${ms(s.gpu.p95)} ms (${s.gpu.scope}, async)`:`UNAVAILABLE · ${s.gpu.status} · ${s.gpu.reason}`);
		updateField("Rendered / output",`${render} / ${output}`);updateField("CSS / DPR",`${count(d.cssWidth)}×${count(d.cssHeight)} / ${ms(d.dpr)}`);
		updateField("FSR / raw rAF",`${d.fsrActive===null||d.fsrActive===undefined?"UNAVAILABLE":d.fsrActive?`on ${ms(d.fsrScale)}`:"off"} / ${ms(d.rafHz)} Hz${d.browserCap30===true?" · browserCap30":""}`);
		updateField("Draws / tris / particles",`${count(s.scene.drawCalls)} / ${count(s.scene.triangles)} submitted / ${count(s.scene.particles)} rendered`);
		updateField("Context lost / restored",`${s.env.contextLost} / ${s.env.contextRestored} (page-local)`);updateField("Visible / focused",`${s.env.visible} / ${s.env.focused}`);
		updateField("Window / elapsed",`${s.frame.n}/${s.windowCapacity} samples · ${Math.floor(s.elapsedMs/1000)}s · warm ${s.warmupRemaining}`);
	}
	function poll(){if(disposed)return;const t=now();if(t-lastPoll<500)return;lastPoll=t;try{const supplied=options.readState?.()??{};collector.updateState({...supplied,dpr:supplied.dpr??devicePixelRatio,cssWidth:supplied.cssWidth??innerWidth,cssHeight:supplied.cssHeight??innerHeight,visible:document.visibilityState==="visible",focused:document.hasFocus()},t);}catch{status.textContent=th?"แหล่งข้อมูลยังไม่พร้อม":"Metric source unavailable.";}show(collector.compact(t));}
	const onVisibility=()=>{collector.visibility(document.visibilityState==="visible",document.hasFocus(),now());lastPoll=-Infinity;poll();};
	const onFocus=()=>{lastPoll=-Infinity;poll();};
	const onInteraction=()=>options.onInteraction?.();
	root.addEventListener("focusin",onInteraction);
	document.addEventListener("visibilitychange",onVisibility);window.addEventListener("focus",onFocus);window.addEventListener("blur",onFocus);
	const interval=window.setInterval(poll,500);
	const priorApi=window.__xexPerf;
	const api={snapshot,history:()=>collector.history(),reset:()=>{collector.reset(now());lastPoll=-Infinity;poll();},mark:(label:string)=>collector.mark(label,now())};window.__xexPerf=api;
	function dispose(){if(disposed)return;disposed=true;window.clearInterval(interval);document.removeEventListener("visibilitychange",onVisibility);window.removeEventListener("focus",onFocus);window.removeEventListener("blur",onFocus);window.removeEventListener("pagehide",dispose);root.removeEventListener("focusin",onInteraction);root.remove();if(window.__xexPerf===api)window.__xexPerf=priorApi;}
	window.addEventListener("pagehide",dispose);poll();
	return {recordFrame:frame=>disposed?false:collector.recordFrame(frame),contextLost(){if(!disposed)collector.context("lost",now());},contextRestored(){if(!disposed)collector.context("restored",now());},snapshot,history:api.history,reset:api.reset,mark:api.mark,exportJson,dispose};
}
