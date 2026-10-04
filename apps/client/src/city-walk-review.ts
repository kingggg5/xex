type Point = readonly [number, number];
const TARGETS: Array<{name:string;point:Point}> = [
	{name:'Gate approach',point:[10.1,-2]}, {name:'Gate entry',point:[10.1,24]},
	{name:'Bridge 1 bank',point:[10.1,64]}, {name:'Bridge 1 west',point:[-14,64]}, {name:'Bridge 1 east',point:[14,64]},
	{name:'Bridge 2 bank',point:[10.1,102]}, {name:'Bridge 2 west',point:[-14,102]}, {name:'Bridge 2 east',point:[14,102]},
	{name:'Plaza approach',point:[18,144]}, {name:'Fountain south',point:[20,156]},
	{name:'Fountain west',point:[-20,156]}, {name:'West paving',point:[-24,164]},
	{name:'West plaza exit',point:[-24,206]}, {name:'Castle avenue',point:[0,216]},
	{name:'Castle landing',point:[0,247]}, {name:'Castle entry',point:[0,252]},
	{name:'Castle descent',point:[0,216]}, {name:'West stair apron',point:[-9,215]},
	{name:'Wizard lane south',point:[-18,229]}, {name:'Wizard lane bend',point:[-18,233]},
	{name:'Wizard lane north',point:[-29,242]}, {name:'Wizard lane west',point:[-39,242]},
	{name:'Wizard approach',point:[-50.4,236.35]}, {name:'Wizard first step',point:[-51,237.2]},
	{name:'Wizard flight',point:[-57.6,246.5]}, {name:'Wizard terrace',point:[-61,252]},
	{name:'Wizard flight return',point:[-57.6,246.5]}, {name:'Wizard first step return',point:[-51,237.2]},
	{name:'Wizard descent',point:[-50.4,236.35]}, {name:'North connector',point:[-29.4,242.35]},
	{name:'West connector',point:[-16.4,231.35]}, {name:'Stair apron return',point:[-9.4,215.35]},
	{name:'East stair apron',point:[21.6,215.35]}, {name:'Windmill approach',point:[44,226]},
	{name:'Windmill path',point:[80,264]}, {name:'Windmill',point:[90,276]},
	{name:'Windmill path return',point:[80,264]}, {name:'Windmill descent',point:[44,226]},
	{name:'East plaza exit',point:[13,150]}, {name:'Canal bank return',point:[10.1,140]},
	{name:'Gate exit',point:[10.1,-2]}, {name:'Outside city',point:[-3,-3]},
	{name:'Gate reentry approach',point:[10.1,-2]}, {name:'Gate reentry',point:[10.1,24]},
	{name:'Canal bank reentry',point:[10.1,140]}, {name:'Plaza reentry',point:[18,144]},
	{name:'Fountain reentry',point:[20,156]},
];

/** Explicit DEV route control. Uses normal input/prediction/acknowledgement paths. */
export function createCityWalkReview(getStatus:()=>{online:boolean;waiting:boolean;x:number;y:number;z:number;correction:number;correctionEvents?:readonly unknown[];connectionEvents?:readonly unknown[]}, onReentry?:()=>void) {
	if (!import.meta.env.DEV || new URLSearchParams(location.search).get('cityWalkReview')!=='1') return undefined;
	let index=0,running=false,continuous=false,pausedUntil=0,lastProgress=performance.now(),lastDistance=Infinity;
	let peakCorrection=0,previous:Point|undefined,interruption='';
	let wasInside=false,hasExited=false;
	const visits:Array<{target:string;actual:[number,number,number];online:boolean;correction:number}>=[];
	const panel=document.createElement('aside');panel.setAttribute('aria-label','City walking review');
	panel.style.cssText='position:fixed;left:12px;bottom:110px;z-index:1100;background:#10212ded;color:#ffe4ad;padding:10px;max-width:330px;font:12px system-ui';
	const start=document.createElement('button'),next=document.createElement('button'),stop=document.createElement('button'),auto=document.createElement('button'),status=document.createElement('output'),history=document.createElement('pre');
	start.textContent='Walk review route';next.textContent='Next waypoint';stop.textContent='Stop review';status.style.cssText='display:block;white-space:pre-wrap;padding-top:8px';
	auto.textContent='Run continuous review';history.setAttribute('aria-label','City route receipts');history.style.cssText='max-height:100px;overflow:auto;font:10px monospace';
	for(const button of [start,next,stop,auto])button.style.cssText='margin:2px;padding:6px;background:#243544;color:#ffe4ad;border:1px solid #7d734a';
	start.onclick=()=>{continuous=false;running=true;interruption='';lastProgress=performance.now();lastDistance=Infinity;};
	auto.onclick=()=>{continuous=true;running=true;interruption='';lastProgress=performance.now();lastDistance=Infinity;};
	next.onclick=()=>{index=(index+1)%TARGETS.length;pausedUntil=0;lastProgress=performance.now();lastDistance=Infinity;};
	stop.onclick=()=>{running=false;continuous=false;};panel.append(start,next,stop,auto,status,history);document.body.append(panel);
	const update=setInterval(()=>{
		const s=getStatus(),target=TARGETS[index];
		if(wasInside&&s.z<8)hasExited=true;
		if(hasExited&&s.z>=8){onReentry?.();hasExited=false;}
		wasInside=s.z>=8;
		status.textContent=`${s.online?'ONLINE':'OFFLINE — not authoritative'} · ${running?'Walking':'Paused'}\n${index+1}/${TARGETS.length}: ${target.name}\nXYZ ${s.x.toFixed(2)}, ${s.y.toFixed(2)}, ${s.z.toFixed(2)}\nCorrection ${s.correction.toFixed(4)}m · peak ${peakCorrection.toFixed(4)}m · visits ${visits.length}${interruption?'\n'+interruption:''}`;
		history.textContent=visits.map(v=>`${v.target}: ${v.actual.map(n=>n.toFixed(2)).join(',')} · ${v.online?'online':'offline'} · correction ${v.correction.toFixed(4)}`).join('\n')+'\nCorrection events: '+JSON.stringify(s.correctionEvents??[])+'\nConnection events: '+JSON.stringify(s.connectionEvents??[]);
	},250);
	return {
		axes():{x:number;z:number}|null {
			// Hold normal movement at zero while a review waypoint is paused.
			// Otherwise held keyboard/touch axes can invalidate a captured arrival.
			if(!running)return {x:0,z:0};const s=getStatus();
			peakCorrection=Math.max(peakCorrection,s.correction);
			if(previous&&Math.hypot(s.x-previous[0],s.z-previous[1])>4){running=false;interruption='Interrupted: position reset/respawn. This segment is not accepted.';previous=[s.x,s.z];return {x:0,z:0};}
			previous=[s.x,s.z];
			if(!s.online||s.waiting||performance.now()<pausedUntil)return {x:0,z:0};
			const target=TARGETS[index],dx=target.point[0]-s.x,dz=target.point[1]-s.z,distance=Math.hypot(dx,dz),now=performance.now();
			if(distance<.15){visits.push({target:target.name,actual:[s.x,s.y,s.z],online:s.online,correction:s.correction});if(continuous&&index<TARGETS.length-1){index++;lastProgress=now;lastDistance=Infinity;}else running=false;return {x:0,z:0};}
			if(distance<lastDistance-.02){lastProgress=now;lastDistance=distance;}
			if(now-lastProgress>12000){running=false;interruption='Blocked: inspect geometry/route before continuing.';return {x:0,z:0};}
			const analog=Math.min(1,distance/.8);
			return {x:dx/distance*analog,z:dz/distance*analog};
		},
		dispose(){clearInterval(update);panel.remove();},visits,
	};
}
