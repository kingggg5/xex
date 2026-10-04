export const MONSTER_STANDIN_SPECIES = Object.freeze({1:'puddlekin',2:'mossling',3:'thistle_boar',4:'glade_wisp'});
const phases = new Set(['windup','leap','impact','recovery','idle']);
/** Local cosmetic transform only. Call with the scene's shared clock; no timer or server position. */
export function sampleMonsterStandinPose(kind, phase='idle', elapsedMs=0, seed=0, reduceMotion=false) {
	if (!MONSTER_STANDIN_SPECIES[kind]) throw new RangeError(`No CC0 interim model for monster kind ${kind}`);
	if (!phases.has(phase)) throw new TypeError(`Unknown monster phase ${phase}`);
	if (!Number.isFinite(elapsedMs) || !Number.isSafeInteger(seed)) throw new TypeError('Invalid shared animation clock or identity');
	const t=elapsedMs*.001+seed*.37;
	const scale=[1,1,1];let y=kind===4?.35:0,pitch=0,roll=0;
	if(kind===1) {
		if(phase==='windup'){scale.splice(0,3,1.15,.78,1.1);}
		else if(phase==='leap'){scale.splice(0,3,.9,1.12,.9);y=.9;}
		else if(phase==='impact'){scale.splice(0,3,1.2,.72,1.14);}
		else if(phase==='recovery'){scale.splice(0,3,1.07,.9,1.04);}
		else if(!reduceMotion){scale[1]=1+Math.sin(t*2.2)*.018;}
	} else {
		// Preserve animal/treant anatomy: never apply the old slime's extreme squash to them.
		if(phase==='windup')pitch=kind===3?-.12:.1;
		else if(phase==='leap'){y+=kind===4?.35:.55;pitch=-.08;}
		else if(phase==='impact')pitch=.08;
		else if(phase==='recovery')pitch=.035;
		if(phase==='idle'&&!reduceMotion){if(kind===4)y+=Math.sin(t*1.7)*.055;else roll=Math.sin(t*1.2)*.012;}
	}
	if(reduceMotion){roll=0;if(phase==='idle')y=kind===4?.35:0;}
	return {scale,y,pitch,roll};
}
