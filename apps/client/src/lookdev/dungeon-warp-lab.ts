import {Scene} from '@babylonjs/core/scene';
import {ArcRotateCamera} from '@babylonjs/core/Cameras/arcRotateCamera';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {Color3,Color4} from '@babylonjs/core/Maths/math.color';
import {HemisphericLight} from '@babylonjs/core/Lights/hemisphericLight';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
import {CreateGround} from '@babylonjs/core/Meshes/Builders/groundBuilder';
import {CreateCapsule} from '@babylonjs/core/Meshes/Builders/capsuleBuilder';
import {createRenderer} from '../renderer-choice';
import {createDungeonWarpHub} from '../dungeon-warp-hub.svelte.js';

/** Small DEV shader/look test, explicitly not a map or authoritative gameplay proof. */
export async function mountDungeonWarpLab(){
	const unusedHud=document.getElementById('hud');if(unusedHud)unusedHud.hidden=true;
	const canvas=document.getElementById('game-canvas') as HTMLCanvasElement;const renderer=await createRenderer(canvas),scene=new Scene(renderer.engine);
	scene.clearColor=new Color4(.018,.036,.06,1);
	const target=new Vector3(40,2,186),camera=new ArcRotateCamera('warp-lab-camera',-Math.PI/2,1.08,16,target,scene);camera.attachControl(canvas,true);
	new HemisphericLight('warp-lab-fill',new Vector3(.2,1,-.3),scene).intensity=.9;
	const ground=CreateGround('warp-lab-neutral-ground',{width:22,height:26},scene);ground.position.set(40,.78,186);
	const stone=new StandardMaterial('warp-lab-neutral-slate',scene);stone.diffuseColor=Color3.FromHexString('#33485c');stone.specularColor=Color3.Black();ground.material=stone;
	const witness=CreateCapsule('warp-lab-scale-witness-1p8m',{height:1.8,radius:.3},scene);witness.position.set(37.1,1.7,185);
	const witnessMaterial=new StandardMaterial('warp-lab-witness-only',scene);witnessMaterial.diffuseColor=Color3.FromHexString('#bea875');witnessMaterial.specularColor=Color3.Black();witness.material=witnessMaterial;
	const hub=createDungeonWarpHub(scene,{y:.8,th:navigator.language.startsWith('th'),mobile:matchMedia('(pointer:coarse)').matches,
		focus:()=>({x:40,y:.8,z:176}),checkTower:async()=>false,enterTower:async()=>false});
	const label=document.createElement('p');label.textContent='DEV FX LAB · 1.8 m scale witness · not a map, server session or FPS test';label.style.cssText='position:fixed;left:16px;top:12px;z-index:99;margin:0;padding:8px 12px;background:#0b1828ed;color:#d8e8f2;border:1px solid #bfa876;font:12px system-ui';document.body.append(label);
	(window as unknown as {__xexoria?:unknown}).__xexoria={scene,engine:renderer.engine};scene.metadata={warpFxLab:true,notMapAcceptance:true};
	const resize=()=>renderer.engine.resize();window.addEventListener('resize',resize);
	renderer.engine.runRenderLoop(()=>scene.render());
	window.addEventListener('pagehide',()=>{hub.dispose();renderer.engine.stopRenderLoop();scene.dispose();renderer.engine.dispose();window.removeEventListener('resize',resize);label.remove();if(unusedHud)unusedHud.hidden=false;},{once:true});
}
