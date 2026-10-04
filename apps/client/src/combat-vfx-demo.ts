import { Mesh } from "@babylonjs/core/Meshes/mesh";
import type { Scene } from "@babylonjs/core/scene";
import type { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import "@babylonjs/core/Particles/particleSystemComponent";
import { loadVfxKit } from "./combat-vfx-kit";
import { createCombatVfx, sceneVfxCounts, SKILLS } from "./combat-vfx-skills";
import { SceneInstrumentation } from "@babylonjs/core/Instrumentation/sceneInstrumentation";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import {Matrix,Vector3} from '@babylonjs/core/Maths/math.vector';
import {CORE_VFX_IDS,WITCH_VFX_DEFINITIONS} from './combat-vfx-lookv2.mjs';
import {measureDraftVfxPixels} from './combat-vfx-perceptual.mjs';

export const CAPTURE_TIMES: Record<string, number[]> = {
 xs_bladeward_nova: [0.06,0.13,0.19,0.26,0.42,0.78,1.15,2.2],
 xs_gale_palm: [0.1,0.2,0.36,0.58,0.78,0.92,1.25,2.0],
 xs_void_rift: [0.3,0.62,0.95,1.27,2.0,2.92,3.12,3.9],
};
for(const definition of WITCH_VFX_DEFINITIONS)if(!Object.hasOwn(CAPTURE_TIMES,definition.id))CAPTURE_TIMES[definition.id]=definition.captureMs.map(ms=>ms/1000);
export const vfxCaptureBatch=(search:string)=>{const query=new URLSearchParams(search);return query.get('vfxbatch')==='witch-new'?['h02_star_lance','h02_moonveil_ward','h02_celestial_orrery']:query.get('vfxdraft')==='1'?['h02_rimeshard_nova','h02_hoarfrost_gale','h02_starless_hollow']:CORE_VFX_IDS.slice();};
function effectRoi(scene:Scene,camera:ArcRotateCamera,width:number,height:number){
 let minX=width,minY=height,maxX=0,maxY=0,count=0;const identity=Matrix.Identity(),viewport=camera.viewport.toGlobal(width,height);
 for(const mesh of scene.meshes){if(!/^(nova|gale|rift|h02-source)-/.test(mesh.name)||!mesh.isEnabled()||!mesh.isVisible)continue;mesh.computeWorldMatrix(true);
  for(const corner of mesh.getBoundingInfo().boundingBox.vectorsWorld){const p=Vector3.Project(corner,identity,scene.getTransformMatrix(),viewport);if(p.z<0||p.z>1)continue;minX=Math.min(minX,p.x);minY=Math.min(minY,p.y);maxX=Math.max(maxX,p.x);maxY=Math.max(maxY,p.y);count++;}
 }
 if(!count)return null;const x=Math.max(0,Math.floor(minX-24)),y=Math.max(0,Math.floor(minY-24)),right=Math.min(width,Math.ceil(maxX+24)),bottom=Math.min(height,Math.ceil(maxY+24));return right>x&&bottom>y?{x,y,width:right-x,height:bottom-y}:null;
}
const MAX_NATIVE_RESULTS=3,MAX_NATIVE_PNG_BYTES=5*1024*1024,MAX_NATIVE_PROBE_CHARS=256*1024;
type RenderTargetScreenshot=typeof import("@babylonjs/core/Misc/screenshotTools").CreateScreenshotUsingRenderTarget;
/** Existing Babylon resolved RTT path: same camera post-processes, no multisampled swapchain read. */
export async function captureResolvedWebGpuVfxFrame(engine:AbstractEngine,camera:ArcRotateCamera,width:number,height:number,screenshotOverride?:RenderTargetScreenshot):Promise<string>{
 if(!engine.isWebGPU||!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0||width*height>4096*2160)throw new Error("Invalid resolved WebGPU VFX capture shape");
 const screenshot=screenshotOverride??(await import("@babylonjs/core/Misc/screenshotTools")).CreateScreenshotUsingRenderTarget;
 const scene=camera.getScene(),animated=scene.animationsEnabled;
 const particles=scene.particleSystems.map(system=>({system,speed:system.updateSpeed}));
 scene.animationsEnabled=false;for(const entry of particles)entry.system.updateSpeed=0;
 // The host loops are stopped. Flush exactly the utility's offscreen render after its scene stack restores.
 const afterRender=scene.onAfterRenderObservable.addOnce(()=>queueMicrotask(()=>engine.endFrame()));
 try{
  engine.beginFrame();
  return await new Promise<string>((resolve,reject)=>{
   screenshot(engine,camera,{width,height},data=>typeof data==="string"&&data.startsWith("data:image/png;base64,")?resolve(data):reject(new Error("Resolved WebGPU screenshot returned no PNG")),"image/png",1,false,undefined,scene.spritesEnabled,true,true,undefined,
    texture=>{texture.useCameraPostProcesses=true;},undefined,15000,()=>reject(new Error("Resolved WebGPU VFX capture timed out before a readable target")));
  });
 }catch(error){throw new Error(`Resolved WebGPU VFX frame failed: ${error instanceof Error?error.message:String(error)}`);}
 finally{scene.onAfterRenderObservable.remove(afterRender);scene.animationsEnabled=animated;for(const entry of particles)entry.system.updateSpeed=entry.speed;}
}
export function validateResolvedVfxPixels(data:Uint8ClampedArray,width:number,height:number):void {
 if(data.length!==width*height*4)throw new Error("Resolved WebGPU screenshot dimensions did not match the native capture");
 let visible=false;for(let i=0;i<data.length;i+=4)if(data[i+3]>0&&(data[i]>0||data[i+1]>0||data[i+2]>0)){visible=true;break;}
 if(!visible)throw new Error("Resolved WebGPU readback was blank; refusing an empty VFX contact sheet");
}
export const isVfxDomExport=(search:string)=>new URLSearchParams(search).get("vfxexport")==="dom";
/** Explicit DEV evidence route. Non-executable text, no downloads or third-party upload. */
export function createNativeVfxResultExport(host:Document){
 const old=host.getElementById("vfx-native-results");old?.remove();
 const node=host.createElement("script");node.id="vfx-native-results";node.type="application/json";node.hidden=true;node.inert=true;node.setAttribute("aria-hidden","true");host.body.append(node);
 const results:Array<{skillId:string;png:string;probe:unknown}>=[];
 const publish=(state:string)=>{node.textContent=JSON.stringify({results});node.dataset.count=String(results.length);node.dataset.state=state;};
 publish("capturing");
 return {
  add(result:{skillId:string;png:string;probe:unknown}){
   if(results.length>=MAX_NATIVE_RESULTS||results.some(value=>value.skillId===result.skillId)||!Object.hasOwn(CAPTURE_TIMES,result.skillId))throw new Error("Native VFX result count or identity exceeded bound");
   const prefix="data:image/png;base64,";
   if(!result.png.startsWith(prefix))throw new Error("Native VFX result must be a PNG data URL");
   const bytes=result.png.slice(prefix.length),padding=bytes.endsWith("==")?2:bytes.endsWith("=")?1:0;
   if(bytes.length%4!==0||!/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(bytes)||bytes.length*3/4-padding>MAX_NATIVE_PNG_BYTES)throw new Error("Native VFX PNG exceeds 5 MiB or has invalid encoding");
   const probe=JSON.stringify(result.probe);if(probe===undefined||probe.length>MAX_NATIVE_PROBE_CHARS)throw new Error("Native VFX probe exceeds metadata bound");
   results.push({skillId:result.skillId,png:result.png,probe:JSON.parse(probe)});publish("capturing");
  },
  complete(){publish("complete");},fail(){publish("error");},get count(){return results.length;},
 };
}

/** DEV import gate belongs to the host. No ability, network or target reaction is installed here. */
export async function installCombatVfxDemo(options: { scene: Scene; player: TransformNode; camera: ArcRotateCamera; groundAt(x: number,z: number): number | null; preset(): string;castOrigin?():Readonly<{x:number;y:number;z:number}>|null }) {
 const { scene, player, camera } = options, engine = scene.getEngine();
 const id = new URLSearchParams(location.search).get("vfxdemo");
 if (!id || !Object.hasOwn(SKILLS,id) || scene.isDisposed) return;
 const hero02Draft=new URLSearchParams(location.search).get('vfxdraft')==='1';
 const baseline = sceneVfxCounts(scene), kit = await loadVfxKit(scene,{hero02Draft});
 if (scene.isDisposed) { kit.dispose(); return; }
 const lookVersion=new URLSearchParams(location.search).get('vfxlook')==='2'||!CORE_VFX_IDS.includes(id)?2:1;
 let runtime = createCombatVfx(scene,kit,{ groundAt: options.groundAt, preset: options.preset, ownKit: true,lookVersion,hero02Draft,castOrigin:options.castOrigin });
 let readiness: ReturnType<typeof setInterval> | undefined;
 let disposed = false, capturing = false, warmupMs = 0, timer: ReturnType<typeof setInterval> | undefined;
 const cast = () => runtime.cast(id,player.position,player.rotation.y);
 async function warm() {
  const started = performance.now();
  const variants = new Set<string>();
  for (const mesh of scene.meshes) {
   if (!(mesh instanceof Mesh) || !mesh.material) continue;
   if (!mesh.material.pluginManager?.getPlugin("VfxSurface") && (!mesh.isEnabled() || !mesh.isVisible)) continue;
   const useInstances=mesh.instances.length>0||mesh.hasThinInstances;
   const key=`${mesh.material.uniqueId}:${mesh.useVertexColors}:${mesh.skeleton?.bones.length??0}:${useInstances}`;
   if(variants.has(key))continue;variants.add(key);
   await mesh.material.forceCompilationAsync(mesh,{useInstances});
  }
  const systems = scene.particleSystems.filter(s => /^(nova|gale|rift|prior)-/.test(s.name));
  const deadline = performance.now()+15000;
  while (!systems.every(s => s.isReady())) {
   if (disposed || scene.isDisposed) throw new Error("VFX scene disposed during warm-up");
   if (performance.now()>deadline) throw new Error("VFX particles did not compile within 15 seconds");
   await new Promise(resolve => setTimeout(resolve,16));
  }
  warmupMs = performance.now()-started;
 }
 const domExport=isVfxDomExport(location.search);
 const panel = document.createElement("section"); panel.id="combat-vfx-preview";
 panel.style.cssText="position:fixed;right:12px;bottom:150px;z-index:1200;padding:8px;background:#111c;color:#eee;font:12px monospace";
 const status=document.createElement("span");status.id="vfx-native-status";status.setAttribute("role","status");status.textContent="VFX warming";panel.append(status);
 document.body.append(panel);
 const controller = {
  get runtime() { return runtime; }, scene, camera, player, baseline,
  get warmupMs() { return warmupMs; },
  get renderer() { return engine.isWebGPU ? "WebGPU" : "WebGL2"; },
  cast,
  async probeLeaks(skillId: string) {
   capturing=true;runtime.dispose();
   await new Promise(resolve=>setTimeout(resolve,0));
   const before=sceneVfxCounts(scene);
   const probeKit=await loadVfxKit(scene,{hero02Draft});
   const probeRuntime=createCombatVfx(scene,probeKit,{groundAt:options.groundAt,preset:options.preset,ownKit:true,lookVersion,hero02Draft,castOrigin:options.castOrigin});
   probeRuntime.setManual(true);const pooled=sceneVfxCounts(scene);
   for(let i=0;i<10;i++){
    const handle=probeRuntime.cast(skillId,player.position,player.rotation.y);
    if(!handle)throw new Error("Leak probe cast has no supported ground");
    probeRuntime.step(.3);probeRuntime.step(handle.duration);
   }
   const afterCasts=sceneVfxCounts(scene);probeRuntime.dispose();
   await new Promise(resolve=>setTimeout(resolve,0));
   const after=sceneVfxCounts(scene);
   const fresh=await loadVfxKit(scene,{hero02Draft});runtime=createCombatVfx(scene,fresh,{groundAt:options.groundAt,preset:options.preset,ownKit:true,lookVersion,hero02Draft,castOrigin:options.castOrigin});
   await warm();capturing=false;
   return {casts:10,before,pooled,afterCasts,after,delta:Object.fromEntries(Object.keys(before).map(k=>[k,after[k as keyof typeof after]-before[k as keyof typeof before]]))};
  },
  async capture(skillId = id!) {
   if (capturing || disposed || !CAPTURE_TIMES[skillId]) throw new Error("Invalid or concurrent VFX capture");
   const readiness=runtime.previewReadiness(skillId);if(!readiness.ready)throw new Error(`ITERATE draft VFX not ready: ${readiness.missing.join(', ')}`);
   capturing = true;
   const loops = engine.activeRenderLoops.slice(); engine.stopRenderLoop();
   const playerPose=player.position.clone();
   if(new URLSearchParams(location.search).get("lookdev")==="1") {
    const height=options.groundAt(0,-92);if(height===null)throw new Error("Sunmeadow review ground unavailable");
    player.position.set(0,height+0.015,-92);
   }
   const pose={alpha:camera.alpha,radius:camera.radius,beta:camera.beta,fov:camera.fov,target:camera.target.clone()};
   const reviewZoom=new URLSearchParams(location.search).get("vfxzoom");
   const reviewRadius=reviewZoom==="max"?(camera.upperRadiusLimit??26.5):13;
   const instrumentation=new SceneInstrumentation(scene);
   const baselineCpu:number[]=[],nativeCpu:number[]=[],nativeDraws:number[]=[];
   let baselineDraws=0,lastFrameCpu=0,lastFrameDraws=0,castCpuMs=0;
   const cameraObserver=scene.onBeforeRenderObservable.add(()=>{
    camera.alpha=-Math.PI/2;camera.radius=reviewRadius;camera.beta=1.18;camera.fov=1.02;
    camera.setTarget(player.position.clone().addInPlaceFromFloats(0,1.65,2),false,false,true);
   });
   const constant = scene.useConstantAnimationDeltaTime; scene.useConstantAnimationDeltaTime = true;
   runtime.setManual(true); runtime.clear();
   const canvas = engine.getRenderingCanvas()!;
   const sheet = document.createElement("canvas"), frame = document.createElement("canvas");
   const cellW=640,cellH=360,label=22,header=52;
   sheet.width=cellW*4;sheet.height=header+(cellH+label)*2;
   frame.width=canvas.width;frame.height=canvas.height;
   const g=sheet.getContext("2d")!, fg=frame.getContext("2d")!;
   const readNativeFrame=async():Promise<Uint8ClampedArray<ArrayBuffer>>=>{
    if(engine.isWebGPU){const png=await captureResolvedWebGpuVfxFrame(engine,camera,canvas.width,canvas.height),image=new Image();await new Promise<void>((resolve,reject)=>{image.onload=()=>resolve();image.onerror=()=>reject(new Error('Resolved WebGPU PNG could not be decoded'));image.src=png;});if(image.naturalWidth!==canvas.width||image.naturalHeight!==canvas.height)throw new Error('Resolved WebGPU screenshot changed native dimensions');fg.clearRect(0,0,canvas.width,canvas.height);fg.drawImage(image,0,0);const data=fg.getImageData(0,0,canvas.width,canvas.height).data;validateResolvedVfxPixels(data,canvas.width,canvas.height);return data;}
    const read=await engine.readPixels(0,0,canvas.width,canvas.height,true,true);return new Uint8ClampedArray(read.buffer,read.byteOffset,canvas.width*canvas.height*4).slice();
   };
   g.fillStyle="#11161c";g.fillRect(0,0,sheet.width,sheet.height);
   let peakDc=0,peakParticles=0,peakLights=0,maxWhiteArea=0;
   const frames: unknown[]=[];
   try {
    // Preserve the real game framing and metre scale; center the local player as the witness.
    camera.alpha=-Math.PI/2;camera.radius=reviewRadius;camera.beta=1.18;camera.fov=1.02;
    camera.setTarget(player.position.clone().addInPlaceFromFloats(0,1.65,2),false,false,true);
    // Measure the same camera/world without active VFX before resetting the effect's manual clock.
    for(let i=0;i<30;i++){const start=performance.now();engine.beginFrame();scene.render();engine.endFrame();if(i>=6)baselineCpu.push(performance.now()-start);}
    baselineDraws=instrumentation.drawCallsCounter.current;
    const baselineMedian=baselineCpu.slice().sort((a,b)=>a-b)[Math.floor(baselineCpu.length*.5)]??0;
    const baselinePixels=lookVersion===2?await readNativeFrame():null;
    const castStarted=performance.now();
    const handle=runtime.cast(skillId,player.position,player.rotation.y);
    castCpuMs=performance.now()-castStarted;
    if (!handle) throw new Error("No supported ground for VFX cast");
    g.fillStyle="#f2c76e";g.font="bold 17px Consolas,monospace";
    g.fillText(`${skillId} | ${controller.renderer} | ${canvas.width}x${canvas.height} | ${options.preset()} | ${reviewRadius} m | Look v${lookVersion} | BABYLON CAPTURE`,10,21);
    g.fillStyle="#c9d4dc";g.font="13px Consolas,monospace";g.fillText(handle.contract,10,42);
    for (let i=0;i<CAPTURE_TIMES[skillId].length;i++) {
     const time=CAPTURE_TIMES[skillId][i];
     while (handle.time+1/120<time) {
      const start=performance.now();runtime.step(1/60);engine.beginFrame();scene.render();engine.endFrame();
      lastFrameCpu=performance.now()-start;lastFrameDraws=instrumentation.drawCallsCounter.current;
      nativeCpu.push(lastFrameCpu);nativeDraws.push(Math.max(0,lastFrameDraws-baselineDraws));
      const s=runtime.stats();peakDc=Math.max(peakDc,s.dc);peakParticles=Math.max(peakParticles,s.pt);peakLights=Math.max(peakLights,s.lights);
     }
     let data:Uint8ClampedArray<ArrayBuffer>;
     if(engine.isWebGPU){
      const png=await captureResolvedWebGpuVfxFrame(engine,camera,canvas.width,canvas.height);
      const image=new Image();await new Promise<void>((resolve,reject)=>{image.onload=()=>resolve();image.onerror=()=>reject(new Error("Resolved WebGPU PNG could not be decoded"));image.src=png;});
      if(image.naturalWidth!==canvas.width||image.naturalHeight!==canvas.height)throw new Error("Resolved WebGPU screenshot changed native dimensions");
      fg.clearRect(0,0,canvas.width,canvas.height);fg.drawImage(image,0,0);data=fg.getImageData(0,0,canvas.width,canvas.height).data;
      validateResolvedVfxPixels(data,canvas.width,canvas.height);
     }else{
      const read=await engine.readPixels(0,0,canvas.width,canvas.height,true,true);
      data=new Uint8ClampedArray(read.buffer,read.byteOffset,canvas.width*canvas.height*4).slice();
     }
     let white=0;for(let k=0;k<data.length;k+=4) if(data[k]>=250&&data[k+1]>=250&&data[k+2]>=250)white++;
     const whiteArea=white/(canvas.width*canvas.height);maxWhiteArea=Math.max(maxWhiteArea,whiteArea);
     const roi=lookVersion===2?effectRoi(scene,camera,canvas.width,canvas.height):null;
     const readRoi=roi&&!engine.isWebGPU?{...roi,y:canvas.height-roi.y-roi.height}:roi;
     const lookMetrics=baselinePixels&&readRoi?{roi,...measureDraftVfxPixels(data,baselinePixels,canvas.width,canvas.height,readRoi)}:null;
     fg.putImageData(new ImageData(data,canvas.width,canvas.height),0,0);
     const x=i%4*cellW,y=header+Math.floor(i/4)*(cellH+label),s=runtime.stats();
     g.save();if(!engine.isWebGPU){g.translate(0,y+label+cellH);g.scale(1,-1);g.drawImage(frame,x,0,cellW,cellH);}else g.drawImage(frame,x,y+label,cellW,cellH);g.restore();
     g.fillStyle="#d6e2ea";g.font="13px Consolas,monospace";
     g.fillText(`t=${time.toFixed(2)}s Δdc ${Math.max(0,lastFrameDraws-baselineDraws)} pt ${s.pt} CPUΔ ${(Math.max(0,lastFrameCpu-baselineMedian)).toFixed(2)}ms upd ${s.cpu.toFixed(2)}ms`,x+8,y+15);
     frames.push({time,...s,lookMetrics,updateCpuMs:s.cpu,fullFrameCpuMs:lastFrameCpu,baselineFrameCpuMs:baselineMedian,frameCpuDeltaMs:Math.max(0,lastFrameCpu-baselineMedian),nativeSceneDraws:lastFrameDraws,nativeDrawDelta:Math.max(0,lastFrameDraws-baselineDraws),whiteArea,geometry:runtime.geometry()});
    }
    const stats=runtime.stats();
    const nativeSorted=nativeCpu.slice().sort((a,b)=>a-b),nativeP95=nativeSorted[Math.floor(nativeSorted.length*.95)]??0;
    return {png:sheet.toDataURL("image/png"),probe:{skillId,renderer:controller.renderer,warmupMs,castCpuMs,captureMethod:engine.isWebGPU?"Babylon resolved RTT, 1 sample, camera post-processes, utility PNG to sRGB canvas; capture render excluded from timings":"Original WebGL2 backbuffer RGBA readPixels",resolution:[canvas.width,canvas.height],preset:options.preset(),camera:{radius:camera.radius,beta:camera.beta,fov:camera.fov,target:camera.target.asArray()},player:player.position.asArray(),facing:player.rotation.y,worldExposure:scene.imageProcessingConfiguration.exposure,peakDc,peakParticles,peakLights,baselineSceneDraws:baselineDraws,peakNativeDrawDelta:Math.max(0,...nativeDraws),baselineFrameCpuMedianMs:baselineMedian,fullFrameCpuP95Ms:nativeP95,frameCpuDeltaP95Ms:Math.max(0,nativeP95-baselineMedian),cpuMetricScope:"CPUΔ = full synchronous frame minus same-camera baseline median; diagnostic estimate, not isolated VFX cost. cpuP95 below is update-only. Readback/capture excluded.",cpuP50:stats.cpuP50,cpuP95:stats.cpuP95,samples:stats.samples,maxWhiteArea,frames}};
   } finally {instrumentation.dispose();scene.onBeforeRenderObservable.remove(cameraObserver);camera.alpha=pose.alpha;camera.radius=pose.radius;camera.beta=pose.beta;camera.fov=pose.fov;camera.setTarget(pose.target,false,false,true);player.position.copyFrom(playerPose);runtime.clear();runtime.setManual(false);scene.useConstantAnimationDeltaTime=constant;capturing=false;for(const loop of loops)engine.runRenderLoop(loop);}
  },
  dispose() {
   if(disposed)return null;disposed=true;if(timer)clearInterval(timer);if(readiness)clearInterval(readiness);panel.remove();document.getElementById("vfx-native-results")?.remove();runtime.dispose();
   const counts=sceneVfxCounts(scene);return {baseline,counts,delta:Object.fromEntries(Object.keys(baseline).map(k=>[k,counts[k as keyof typeof counts]-baseline[k as keyof typeof baseline]]))};
  },
 };
 scene.onDisposeObservable.addOnce(()=>controller.dispose());
 try {await warm();if(disposed||scene.isDisposed)return;
  scene.onAfterRenderObservable.addOnce(()=>{if(disposed)return;cast();timer=setInterval(()=>{if(!capturing&&!disposed)cast();},4000);});
  (window as unknown as {combatVfxDemo:typeof controller}).combatVfxDemo=controller;
  status.textContent=`${controller.renderer} VFX warm ${warmupMs.toFixed(0)} ms`;
  const captureButton=document.createElement("button");captureButton.id="vfx-native-capture";captureButton.type="button";captureButton.textContent="Capture VFX sheets";panel.append(captureButton);
  if(new URLSearchParams(location.search).get("lookdev")==="1") {
   captureButton.disabled=true;status.textContent="VFX warm; waiting for terrain lookdev";
   readiness=setInterval(()=>{if(document.getElementById("lookdev-panel")){captureButton.disabled=false;status.textContent=`${controller.renderer} VFX warm ${warmupMs.toFixed(0)} ms`;clearInterval(readiness);}},100);
  }
  captureButton.onclick=async()=>{
   captureButton.disabled=true;
   const nativeExport=domExport?createNativeVfxResultExport(document):null;
   const pass=new URLSearchParams(location.search).get("vfxpass")??"final";
   const tod=Number(new URLSearchParams(location.search).get("envHour"))===0?"night":"day";
   try {
    for(const skillId of vfxCaptureBatch(location.search)) {
     status.textContent=`Capturing ${skillId}`;
     const result=await controller.capture(skillId);
     const name=`${pass}-${skillId}-${tod}-${controller.renderer.toLowerCase()}`;
     const leaks=await controller.probeLeaks(skillId);
     Object.assign(result.probe,{leaks});
     if(nativeExport){nativeExport.add({skillId,png:result.png,probe:result.probe});status.textContent=`VFX native results ${nativeExport.count}/3`;continue;}
     for(const [extension,body] of [["png",result.png.split(",")[1]],["json",JSON.stringify(result.probe)]] as const) {
      const response=await fetch(`/__vfx_evidence/${name}.${extension}`,{method:"POST",body});
      if(!response.ok)throw new Error(`Evidence receiver failed ${response.status}`);
     }
    }
    nativeExport?.complete();status.textContent=nativeExport?`VFX native results ready: ${nativeExport.count}/3`:"VFX sheets saved";
   }catch(error){nativeExport?.fail();status.textContent=String(error);}finally{captureButton.disabled=false;}
  };
  console.info("[combat-vfx-demo] warm-up",{warmupMs,renderer:controller.renderer,slots:6});
 } catch(error) {controller.dispose();throw error;}
 return controller;
}
