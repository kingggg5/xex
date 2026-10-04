import {mount,unmount} from 'svelte';
import type {Scene} from '@babylonjs/core/scene';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {createDungeonWarpFx} from './dungeon-warp-fx';
import {DUNGEON_WARP_HUB,warpProximity} from './dungeon-warp-policy.mjs';
import DungeonWarpPanel from './ui/DungeonWarpPanel.svelte';

/** UI stores primitive state only. World meshes remain inside the effect controller. */
export function createDungeonWarpHub(scene:Scene,options:{y:number;th:boolean;mobile:boolean;focus:()=>{x:number;y:number;z:number};
	checkTower:()=>Promise<boolean>;enterTower:()=>Promise<boolean>}){
	const state=$state({near:false,open:false,loading:false,connected:false,busy:false,error:''});
	const origin=new Vector3(DUNGEON_WARP_HUB.x,options.y,DUNGEON_WARP_HUB.z),fx=createDungeonWarpFx(scene,origin,options.mobile);
	const fxPreview=import.meta.env.DEV&&new URLSearchParams(location.search).get('warpFxPreview')==='1';
	let disposed=false,generation=0,previousFocus:HTMLElement|null=null,debugHandle:unknown;
	const target=document.createElement('div');target.dataset.warpHubUi='r01';document.body.append(target);
	const close=()=>{if(state.busy)return;state.open=false;generation++;if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});};
	const open=async()=>{
		if(disposed||state.open)return;previousFocus=document.activeElement instanceof HTMLElement?document.activeElement:null;
		state.open=true;state.loading=true;state.error='';const request=++generation;
		let connected=false;try{connected=await options.checkTower();}catch{}
		if(disposed||request!==generation)return;state.connected=connected;state.loading=false;
	};
	const enter=async()=>{
		if(!state.connected||state.busy||disposed)return;state.busy=true;state.error='';
		let accepted=false;try{accepted=await options.enterTower();}catch{}
		if(disposed)return;state.busy=false;
		if(accepted)close();else state.error=options.th?'ขอห้องไม่สำเร็จ กรุณาลองอีกครั้ง':'Could not enter the instance. Please try again.';
	};
	const component=mount(DungeonWarpPanel,{target,props:{state,th:options.th,onOpen:()=>{void open();},onClose:close,onEnterTower:()=>{void enter();}}});
	const observer=scene.onBeforeRenderObservable.add(()=>{
		const player=options.focus(),visibility=warpProximity(player);
		state.near=visibility.near&&Math.abs(player.y-origin.y)<1.8;
		fx.update(performance.now(),visibility.effects&&!document.hidden,state.connected||fxPreview,state.busy);
	});
	const hide=()=>{if(document.hidden&&!state.busy)close();};document.addEventListener('visibilitychange',hide);
	const dispose=()=>{if(disposed)return;disposed=true;generation++;state.open=false;state.near=false;state.loading=false;state.busy=false;document.removeEventListener('visibilitychange',hide);scene.onBeforeRenderObservable.remove(observer);fx.dispose();void unmount(component);target.remove();
		const win=window as unknown as {__xexoriaWarpHub?:unknown};if(win.__xexoriaWarpHub===debugHandle)delete win.__xexoriaWarpHub;};
	scene.onDisposeObservable.addOnce(dispose);
	if(import.meta.env.DEV){debugHandle={origin:origin.asArray(),stats:()=>({...fx.stats(),...state,fxPreview,destinationsRemainServerGated:true}),open,close};(window as unknown as {__xexoriaWarpHub?:unknown}).__xexoriaWarpHub=debugHandle;}
	return {isOpen:()=>state.open,dispose};
}
