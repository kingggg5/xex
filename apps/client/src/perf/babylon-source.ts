import { SceneInstrumentation } from "@babylonjs/core/Instrumentation/sceneInstrumentation";
import type { Scene } from "@babylonjs/core/scene";
import type { PerfFrame, PerfState } from "./collector.mjs";

interface Counter {current:number;count:number;}
interface TimingSurface {isWebGPU?:boolean;webGLVersion?:number;enabledExtensions?:readonly string[];gpuTimeInFrameForMainPass?:{counter:Counter};getGPUFrameTimeCounter?:()=>Counter;}

/**
 * Root calls readFrame AFTER a real scene.render. Only CPU capture flags are owned.
 * GPU timing is read from an already-enabled public counter; no shared timer is toggled.
 * Docs: Context7 /websites/doc_babylonjs optimize_your_scene; installed 9.27.1 types
 * supply WebGPU main-pass counters (Babylon Lite APIs are deliberately not used).
 */
export function createBabylonPerfSource(scene:Scene) {
	const instrument = new SceneInstrumentation(scene);
	instrument.captureFrameTime=true;
	const engine=scene.getEngine(),timing=engine as unknown as TimingSurface;
	let disposed=false;
	let scope:PerfFrame["gpuScope"]="unavailable",reason="No backend GPU timer available";
	let counter:Counter|undefined;
	try {
		if(timing.isWebGPU&&timing.enabledExtensions?.includes("timestamp-query")) {
			counter=timing.gpuTimeInFrameForMainPass?.counter;
			if(counter){scope="main-pass";reason="Existing asynchronous WebGPU main-pass counter; excludes other passes";}
		} else if(!timing.isWebGPU&&engine.getCaps().timerQuery&&typeof timing.getGPUFrameTimeCounter==="function") {
			counter=timing.getGPUFrameTimeCounter();scope="frame";reason="Existing asynchronous WebGL timer; overlay does not enable shared capture";
		}
	} catch {counter=undefined;scope="unavailable";reason="Public GPU counter is unavailable";}
	// Fence a pre-existing old result. Only a subsequent counter update is sampled.
	let seen=counter?.count??-1;
	const frame:PerfFrame={timeMs:0,frameId:0,cpuSceneMs:null,gpuMs:null,gpuSequence:null,gpuScope:scope,gpuReason:reason,drawCalls:null,triangles:null,particles:null,activeMeshes:null,visible:true,focused:true};
	function readFrame(timeMs:number):PerfFrame {
		frame.timeMs=timeMs;frame.frameId=scene.getFrameId();frame.visible=document.visibilityState==="visible";frame.focused=document.hasFocus();
		frame.cpuSceneMs=disposed?null:instrument.frameTimeCounter.current;
		frame.drawCalls=disposed?null:instrument.drawCallsCounter.current;
		frame.triangles=disposed?null:scene.getActiveIndices()/3;frame.particles=disposed?null:scene.getActiveParticles();frame.activeMeshes=disposed?null:scene.getActiveMeshes().length;
		frame.gpuMs=null;frame.gpuSequence=null;
		try {
			if(!disposed&&counter&&counter.count!==seen){seen=counter.count;if(counter.current>0&&Number.isFinite(counter.current)){frame.gpuMs=counter.current/1_000_000;frame.gpuSequence=seen;}}
		} catch {frame.gpuScope="unavailable";frame.gpuReason="GPU counter read failed; CPU remains separate";}
		return frame;
	}
	function readState():PerfState {
		return {renderer:engine.isWebGPU?"WebGPU":timing.webGLVersion===2?"WebGL2":timing.webGLVersion===1?"WebGL1":engine.getClassName(),outputWidth:engine.getRenderWidth(true),outputHeight:engine.getRenderHeight(true),hardwareScaling:engine.getHardwareScalingLevel()};
	}
	function resetGpuFence(){seen=counter?.count??-1;}
	function dispose(){if(disposed)return;disposed=true;instrument.dispose();scene.onDisposeObservable.remove(disposal);}
	const disposal=scene.onDisposeObservable.addOnce(dispose);
	return {readFrame,readState,resetGpuFence,dispose};
}
