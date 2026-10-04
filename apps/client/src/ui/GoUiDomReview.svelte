<script lang="ts">
	import { onMount } from "svelte";
	import CombatUiReview from "./CombatUiReview.svelte";
	import {emptyCombatView,nextCombatView,emptyDeathView,nextDeathView,startTownRequest,applyTownResult,confirmAliveView,type CombatView,type DeathView,type PanelResourceState,type UiTransaction} from "./combat-model";
	let view:CombatView=$state(emptyCombatView()),death:DeathView=$state(emptyDeathView());
	let mode:"combat"|"panel"=$state("combat"),states:PanelResourceState[]=$state([]),transactions:UiTransaction[]=$state([]);
	let requests:string[]=$state([]),language:"en"|"th"=$state("en");
	function crowd(mobile:boolean){
		mode="combat";view=nextCombatView(emptyCombatView(),{nowMs:10000,formFactor:mobile?"mobile":"desktop",selectedTargetId:1,actors:Array.from({length:16},(_,i)=>({id:i+1,name:i===0?"นักรบแห่งทุ่งหญ้า":"Fixture monster",screenX:110+(i%5)*120,screenY:120+Math.floor(i/5)*55,distance:5+i,onScreen:true,occluded:i===0,hp:i===0?100000:70,maxHp:i===0?200000:100,level:i===0?12:null,rank:i===0?"elite":null,element:null,targetingMe:true,lastDamagedAtMs:null,stateChips:i===0?["windup"]:[],cast:null}))})!;
	}
	onMount(()=>crowd(innerWidth<=900));
	function ko(){mode="combat";death={...nextDeathView(emptyDeathView(),{revision:1,down:true,cause:"monster",penalty:{base_exp:0,job_exp:0,gold:0},costs:{return_to_town:0},free_return:true,auto_revive_at_ms:null})!,online:true,canSubmit:true};requests=[];}
	function request(){const id=death.request?.phase==="outcome-unknown"?death.request.opId:crypto.randomUUID();const next=startTownRequest(death,id);if(next?.request){death=next;requests=[...requests,next.request.opId];}}
	function unknown(){if(death.request)death=applyTownResult(death,{opId:death.request.opId,deathRevision:1,state:"outcome-unknown",reason:"synthetic_disconnect"});}
	function receipt(){if(death.request)death=applyTownResult(death,{opId:death.request.opId,deathRevision:1,state:"committed",reason:"returned_to_town"});}
	function resource(status:PanelResourceState["status"],hasData:boolean){mode="panel";states=[{status,hasData,message:null,requestId:null}];transactions=[];}
</script>
<header><strong>SYNTHETIC DOM CONTRACT FIXTURE</strong><p>No renderer, live server, physical touch or performance qualification.</p></header>
<div class="review-stage"><CombatUiReview {mode} {view} {death} {states} {transactions} {language} returnToTown={request} refresh={()=>resource("loading",false)}/></div>
<nav class="review-controls" aria-label="Synthetic test controls">
	<button onclick={()=>crowd(false)}>Desktop crowd</button><button onclick={()=>crowd(true)}>Phone crowd</button><button onclick={()=>language=language==="en"?"th":"en"}>Thai / English</button>
	<button onclick={ko}>Synthetic KO</button><button onclick={unknown}>Unknown reply</button><button onclick={receipt}>Committed reply</button><button onclick={()=>death=confirmAliveView(death)}>Positive HP snapshot</button>
	<button onclick={()=>resource("loading",false)}>Loading</button><button onclick={()=>resource("loaded-empty",true)}>Loaded empty</button><button onclick={()=>resource("stale",true)}>Stale data</button><button onclick={()=>resource("error",false)}>Error</button>
	<button onclick={()=>{resource("loaded-data",true);transactions=[{resource:"wallet",requestId:"fixture-operation",phase:"outcome-unknown",reason:null}];}}>Unknown transaction</button>
	<p role="status">Requests: {requests.length} · Same UUID reused: {requests.length>1&&requests.every(id=>id===requests[0])?"YES":"not tested"} · Visible plates: {view.slots.filter(slot=>slot.visible).length}</p>
</nav>
<style>
	:global(body){margin:0;background:#243746;color:#f5f0df;font:14px "Noto Sans Thai",sans-serif;}header{padding:10px 18px;background:#091828;position:relative;z-index:20;}header p{margin:4px 0;font-size:12px;color:#c7dae5;}.review-stage{position:relative;height:calc(100dvh - 150px);min-height:260px;padding:12px;box-sizing:border-box;}.review-controls{position:fixed;bottom:0;left:0;right:0;display:flex;flex-wrap:wrap;gap:6px;padding:8px;background:#101e2e;z-index:25;}.review-controls button{min-height:36px;padding:5px 10px;color:#fff0d0;background:#31495c;border:1px solid #b49964;font:inherit;}.review-controls p{margin:2px 0;width:100%;font-size:12px;}.review-controls button:focus-visible{outline:3px solid #ffe0a0;outline-offset:2px;}
</style>
