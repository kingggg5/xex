import {Matrix,Vector3} from '@babylonjs/core/Maths/math.vector';
import {Ray} from '@babylonjs/core/Culling/ray';
import type {GameScene} from './scene';
import type {CombatActorPresentation} from './ui/combat-model';
export interface CombatUiMonster {id:number;kind:number;x:number;z:number;hp:number;max_hp:number;active:boolean;flags?:number;state?:number;state_ticks?:number;ability?:number}
export interface CombatEnemyPresentation {name:string;level?:number;rank?:'normal'|'elite'|'boss';element?:string;splash_windup_ms:number}
const identity=Matrix.Identity();

/** CSS-pixel anchors from the rendered actor, never a second simulation or a Svelte mesh reference. */
export function projectCombatActors(world:GameScene,monsters:readonly CombatUiMonster[],catalog:ReadonlyMap<number,CombatEnemyPresentation>,lastDamaged:ReadonlyMap<number,number>,nowMs:number):CombatActorPresentation[]{
	const canvas=world.engine.getRenderingCanvas();if(!canvas)return [];
	const rect=canvas.getBoundingClientRect();if(rect.width<=0 || rect.height<=0)return [];
	const viewport=world.camera.viewport.toGlobal(rect.width,rect.height);
	const camera=world.camera.globalPosition;
	const origin=world.localRoot.position;
	const result:CombatActorPresentation[]=[];
	for(const monster of monsters){
		if(!monster.active)continue;
		const view=world.slimes.get(monster.id),def=catalog.get(monster.kind);if(!view || !def)continue;
		view.body.computeWorldMatrix(true);
		const standinBounds=view.standin ? view.body.getHierarchyBoundingVectors(true) : null;
		const bounds=standinBounds ? {minimumWorld:standinBounds.min,maximumWorld:standinBounds.max}
			: (view.body as import('@babylonjs/core/Meshes/mesh').Mesh).getBoundingInfo().boundingBox,head=bounds.maximumWorld;
		const anchor=new Vector3((bounds.minimumWorld.x+head.x)*.5,head.y+.30,(bounds.minimumWorld.z+head.z)*.5);
		const point=Vector3.Project(anchor,identity,world.scene.getTransformMatrix(),viewport);
		const distance=Math.hypot(monster.x-origin.x,monster.z-origin.z);
		let occluded=false;
		// Collision proxies provide bounded coarse occlusion; transparent foliage and the full city mesh are not ray-picked.
		if(distance<=35){
			const direction=anchor.subtract(camera),length=direction.length();
			if(length>0){
				const ray=new Ray(camera,direction.scale(1/length),length);
				occluded=world.collisionBoxes.some(box=>{
					// Babylon's box test treats rays as infinite; clip the box to the camera-to-head segment first.
					const min=new Vector3(Math.max(box.minX,Math.min(camera.x,anchor.x)),Math.max(box.minY,Math.min(camera.y,anchor.y)),Math.max(box.minZ,Math.min(camera.z,anchor.z)));
					const max=new Vector3(Math.min(box.maxX,Math.max(camera.x,anchor.x)),Math.min(box.maxY,Math.max(camera.y,anchor.y)),Math.min(box.maxZ,Math.max(camera.z,anchor.z)));
					return min.x<=max.x&&min.y<=max.y&&min.z<=max.z&&ray.intersectsBoxMinMax(min,max);
				});
			}
		}
		const windup=monster.state===2,remaining=(monster.state_ticks??0)*50;
		result.push({id:monster.id,name:def.name,screenX:rect.left+point.x,screenY:rect.top+point.y,distance,
			onScreen:point.z>=0&&point.z<=1&&point.x>=0&&point.y>=0&&point.x<=rect.width&&point.y<=rect.height,
			occluded,hp:monster.hp,maxHp:monster.max_hp,level:def.level??null,rank:def.rank??null,element:def.element??null,
			targetingMe:monster.flags===undefined?null:(monster.flags&4)!==0,hostile:monster.flags===undefined?null:(monster.flags&2)!==0,
			lastDamagedAtMs:lastDamaged.get(monster.id)??null,
			stateChips:monster.state===4?['recovery']:monster.state===5?['stagger']:[],
			cast:windup&&remaining>0?{label:'Splash Hop',endsAtMs:nowMs+remaining,durationMs:Math.max(remaining,def.splash_windup_ms)}:null});
	}
	return result;
}
