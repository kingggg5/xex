import {Matrix,Quaternion,Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {sampleMonsterStandinPose,MONSTER_STANDIN_SPECIES} from './monster-standin-motion-policy.mjs';

// Existing stand-ins admit at most 1,600 triangles (at most 4,800 unique vertices).
export const MAX_MONSTER_CONTACT_VERTICES=4800;
export const MONSTER_ROOT_FLOOR_CLEARANCE_M=.015;
const PHASES=Object.freeze(['idle','windup','leap','impact','recovery']);

/** Actual body-local positions, evaluated once. No AABB corners or frame-time scans. */
export function createMonsterGroundContact(kind,positions) {
	if(!MONSTER_STANDIN_SPECIES[kind])throw new RangeError(`Unknown ground-contact species ${kind}`);
	if(!positions||!Number.isSafeInteger(positions.length)||positions.length===0||positions.length%3!==0||positions.length/3>MAX_MONSTER_CONTACT_VERTICES)
		throw new Error('Ground contact requires bounded actual CPU positions');
	for(let i=0;i<positions.length;i++)if(!Number.isFinite(positions[i]))throw new Error('Ground contact has a nonfinite vertex');
	const vertex=new Vector3(),transformed=new Vector3();
	const minimumY=pose=>{
		const matrix=Matrix.Compose(Vector3.FromArray(pose.scale),Quaternion.RotationYawPitchRoll(0,pose.pitch,pose.roll),new Vector3(0,pose.y,0));
		let min=Infinity;
		for(let i=0;i<positions.length;i+=3){
			vertex.set(positions[i],positions[i+1],positions[i+2]);
			Vector3.TransformCoordinatesToRef(vertex,matrix,transformed);min=Math.min(min,transformed.y);
		}
		return min;
	};
	const phases={};
	for(const phase of PHASES){
		const min=minimumY(sampleMonsterStandinPose(kind,phase,0,0,true));
		// Preserve intentional air/hover motion. Only grounded endpoints may receive a lift.
		const supportOffset=kind===4||phase==='idle'||phase==='leap'?0:Math.max(0,-min-MONSTER_ROOT_FLOOR_CLEARANCE_M);
		phases[phase]=Object.freeze({minimumY:min,supportOffset});
	}
	const idle=sampleMonsterStandinPose(kind,'idle',0,0,true);
	let idleMinimumY=phases.idle.minimumY;
	if(kind===2||kind===3)for(const roll of [-.012,.012])idleMinimumY=Math.min(idleMinimumY,minimumY({...idle,roll}));
	if(kind===1)for(const y of [.982,1.018])idleMinimumY=Math.min(idleMinimumY,minimumY({...idle,scale:[1,y,1]}));
	if(kind===4)idleMinimumY=Math.min(idleMinimumY,minimumY({...idle,y:idle.y-.055}));
	if(idleMinimumY+MONSTER_ROOT_FLOOR_CLEARANCE_M< -1e-6)throw new Error(`Species ${kind} idle exceeds root floor clearance`);
	return Object.freeze({kind,vertexCount:positions.length/3,phases:Object.freeze(phases),idleMinimumY});
}
