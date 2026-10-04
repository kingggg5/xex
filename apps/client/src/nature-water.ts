import {NodeMaterial} from '@babylonjs/core/Materials/Node/nodeMaterial';
import {InputBlock} from '@babylonjs/core/Materials/Node/Blocks/Input/inputBlock';
import {TransformBlock} from '@babylonjs/core/Materials/Node/Blocks/transformBlock';
import {VertexOutputBlock} from '@babylonjs/core/Materials/Node/Blocks/Vertex/vertexOutputBlock';
import {FragmentOutputBlock} from '@babylonjs/core/Materials/Node/Blocks/Fragment/fragmentOutputBlock';
import {FogBlock} from '@babylonjs/core/Materials/Node/Blocks/Dual/fogBlock';
import {ImageProcessingBlock} from '@babylonjs/core/Materials/Node/Blocks/Fragment/imageProcessingBlock';
import {TextureBlock} from '@babylonjs/core/Materials/Node/Blocks/Dual/textureBlock';
import {LightBlock} from '@babylonjs/core/Materials/Node/Blocks/Dual/lightBlock';
import {PerturbNormalBlock} from '@babylonjs/core/Materials/Node/Blocks/Fragment/perturbNormalBlock';
import {DerivativeBlock} from '@babylonjs/core/Materials/Node/Blocks/Fragment/derivativeBlock';
import {FresnelBlock} from '@babylonjs/core/Materials/Node/Blocks/fresnelBlock';
import {ViewDirectionBlock} from '@babylonjs/core/Materials/Node/Blocks/viewDirectionBlock';
import {ReflectBlock} from '@babylonjs/core/Materials/Node/Blocks/reflectBlock';
import {AddBlock} from '@babylonjs/core/Materials/Node/Blocks/addBlock';
import {MultiplyBlock} from '@babylonjs/core/Materials/Node/Blocks/multiplyBlock';
import {SubtractBlock} from '@babylonjs/core/Materials/Node/Blocks/subtractBlock';
import {DivideBlock} from '@babylonjs/core/Materials/Node/Blocks/divideBlock';
import {LerpBlock} from '@babylonjs/core/Materials/Node/Blocks/lerpBlock';
import {SmoothStepBlock} from '@babylonjs/core/Materials/Node/Blocks/smoothStepBlock';
import {ClampBlock} from '@babylonjs/core/Materials/Node/Blocks/clampBlock';
import {DotBlock} from '@babylonjs/core/Materials/Node/Blocks/dotBlock';
import {DistanceBlock} from '@babylonjs/core/Materials/Node/Blocks/distanceBlock';
import {VectorMergerBlock} from '@babylonjs/core/Materials/Node/Blocks/vectorMergerBlock';
import {VectorSplitterBlock} from '@babylonjs/core/Materials/Node/Blocks/vectorSplitterBlock';
import {TrigonometryBlock,TrigonometryBlockOperations as Trig} from '@babylonjs/core/Materials/Node/Blocks/trigonometryBlock';
import {NodeMaterialSystemValues as System} from '@babylonjs/core/Materials/Node/Enums/nodeMaterialSystemValues';
import {NodeMaterialBlockTargets as Target} from '@babylonjs/core/Materials/Node/Enums/nodeMaterialBlockTargets';
import {NodeMaterialBlockConnectionPointTypes as Type} from '@babylonjs/core/Materials/Node/Enums/nodeMaterialBlockConnectionPointTypes';
import type {NodeMaterialConnectionPoint as Port} from '@babylonjs/core/Materials/Node/nodeMaterialBlockConnectionPoint';
import {ShaderLanguage} from '@babylonjs/core/Materials/shaderLanguage';
import {Texture} from '@babylonjs/core/Materials/Textures/texture';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
import {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial';
import {SceneLoader} from '@babylonjs/core/Loading/sceneLoader';
import type {AssetContainer} from '@babylonjs/core/assetContainer';
import {Mesh} from '@babylonjs/core/Meshes/mesh';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData';
import {Color3} from '@babylonjs/core/Maths/math.color';
import {Vector2} from '@babylonjs/core/Maths/math.vector';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {Color4} from '@babylonjs/core/Maths/math.color';
import {ParticleSystem} from '@babylonjs/core/Particles/particleSystem';
import {CustomParticleEmitter} from '@babylonjs/core/Particles/EmitterTypes/customParticleEmitter';
import '@babylonjs/core/Particles/particleSystemComponent';
import {NodeMaterialModes} from '@babylonjs/core/Materials/Node/Enums/nodeMaterialModes';
import {LengthBlock} from '@babylonjs/core/Materials/Node/Blocks/lengthBlock';
import type {Scene} from '@babylonjs/core/scene';
import type {HemisphericLight} from '@babylonjs/core/Lights/hemisphericLight';
import type {GlowLayer} from '@babylonjs/core/Layers/glowLayer';
import type {ResolvedGraphicsPreset} from './graphics-quality.mjs';
import {CityWaterViewInput} from './city-water-view-input';
import {alignWorldAuthoredGlb} from './world-asset-coordinates.mjs';
import {readWeatherFrame} from './ambient-weather-channel';
import {waterTier,validateWaterManifest,rainPuddleVisibility,supportedRainPuddles,rainPuddleAtlasUV,type WaterTier} from './nature-water.mjs';
import baseManifest from './assets/world/water-v3/water-manifest.json';
import baseDerived from '../../../planning/evidence/water-20261002/water-derived.json';
import artManifest from './assets/world/water-art-pass4b/water-manifest.json';
import artDerived from '../../../planning/evidence/water-art-pass4b-20261003/water-derived.json';
import{WaterArtBankEdgePlugin}from'./water-art-pass4b-materials';
import{releaseWaterFloorAssets,projectWaterBankUV,createOwnedWaterFloorMaterial,adoptWaterBankGround}from'./water-art-pass4b-ownership.mjs';
import{addMeadowSurface}from'./meadow-surface';
const ART=typeof location!=='undefined'&&!!import.meta.env?.DEV&&new URLSearchParams(location.search).get('waterArt')==='pass4b';
const ART_REV=ART?Number(new URLSearchParams(location.search).get('waterArtRev')??1):0;
const ART_R02=ART&&(ART_REV===2||ART_REV===3),ART_R03=ART&&ART_REV===3;
const manifest=ART?artManifest:baseManifest,derived=ART?artDerived:baseDerived;

const urls=import.meta.glob('./assets/world/water-v3/*',{query:'?url',import:'default',eager:true}) as Record<string,string>;
const artUrls=import.meta.glob('./assets/world/water-art-pass4b/*',{query:'?url',import:'default',eager:true}) as Record<string,string>;
const asset=(name:string)=>{const url=(ART?artUrls[`./assets/world/water-art-pass4b/${name}`]:null)??urls[`./assets/world/water-v3/${name}`];if(!url)throw new Error(`Missing natural water asset: ${name}`);return url;};
interface Maps {masks:Texture;flow:Texture;ripple:Texture;swell:Texture;foam:Texture;streak:Texture;owned:Texture[];}
interface Graph {material:NodeMaterial;phaseA:InputBlock;phaseB:InputBlock;weight:InputBlock;phase:InputBlock;ambient:InputBlock;day:InputBlock;zenith:InputBlock;horizon:InputBlock;exponent:InputBlock;glint:InputBlock;wet:InputBlock;coverage?:InputBlock;}
export interface RainPuddleBody {id:string;center_xz:number[];outline_xz:number[][];surface_y:number;depth_m:number;}
export interface NatureWaterController {
 readonly ready:Promise<void>;
 reveal():void;hide():void;dispose():void;
 anchors():typeof manifest.anchors;
 configureRainPuddles(bodies:readonly RainPuddleBody[],groundAt:(x:number,z:number)=>number|null):Promise<void>;
 stats():{ready:boolean;revealed:boolean;culled:boolean;tier:string;waterDraws:number;surfaceTriangles:number;fallsTriangles:number;vertexBuffers:number;samplers:number;reflectionScenePasses:0;clockRevision:number|null;error:string|null};
}
const controllers=new WeakMap<Scene,NatureWaterController>();
export const getNatureWater=(scene:Scene)=>controllers.get(scene)??null;

function input(name:string,data:number|Vector2|Color3):InputBlock {
 const kind=typeof data==='number'?Type.Float:data instanceof Vector2?Type.Vector2:Type.Color3;
 const block=new InputBlock(name,Target.Neutral,kind);block.value=data;return block;
}
/** Built-in Babylon graph nodes only. The engine emits both native languages. */
export function buildNatureWaterGraph(scene:Scene,maps:Maps,tier:WaterTier,falls=false,rainPuddle=false):Graph {
 const material=new NodeMaterial(falls?'natural-water-falls':'natural-water-surface',scene,{emitComments:false,shaderLanguage:scene.getEngine().isWebGPU?ShaderLanguage.WGSL:ShaderLanguage.GLSL});
 // This family receives the shared sky fill and sun/moon key. Bound the
 // native all-light variant so unrelated scene lights do not expand its work.
 material.maxSimultaneousLights=2;
 let index=0;const label=(name:string)=>`${name}${index++}`;
 const c=(v:number)=>{const block=input(label('constant'),v);block.isConstant=true;return block.output;};
 const colour=(hex:string)=>{const block=input(label('colour'),Color3.FromHexString(hex).toLinearSpace());block.isConstant=true;return block.output;};
 const binary=(Ctor:typeof AddBlock|typeof MultiplyBlock|typeof SubtractBlock|typeof DivideBlock,a:Port,b:Port)=>{const n=new Ctor(label('arithmetic'));a.connectTo(n.left);b.connectTo(n.right);return n.output;};
 const add=(a:Port,b:Port)=>binary(AddBlock,a,b),mul=(a:Port,b:Port)=>binary(MultiplyBlock,a,b),sub=(a:Port,b:Port)=>binary(SubtractBlock,a,b),div=(a:Port,b:Port)=>binary(DivideBlock,a,b);
 const lerp=(a:Port,b:Port,t:Port)=>{const n=new LerpBlock(label('mix'));a.connectTo(n.left);b.connectTo(n.right);t.connectTo(n.gradient);return n.output;};
 const smooth=(a:number,b:number,p:Port)=>{const n=new SmoothStepBlock(label('smooth'));c(a).connectTo(n.edge0);c(b).connectTo(n.edge1);p.connectTo(n.value);return n.output;};
 const clamp=(p:Port,lo=0,hi=1)=>{const n=new ClampBlock(label('clamp'));n.minimum=lo;n.maximum=hi;p.connectTo(n.value);return n.output;};
 const trig=(p:Port,op:Trig)=>{const n=new TrigonometryBlock(label('trig'));n.operation=op;p.connectTo(n.input);return n.output;};
 const dot=(a:Port,b:Port)=>{const n=new DotBlock(label('dot'));a.connectTo(n.left);b.connectTo(n.right);return n.output;};
 const split=(p:Port)=>{const n=new VectorSplitterBlock(label('split'));p.connectTo(p.type===Type.Vector4?n.xyzw:n.xyzIn);return n;};
 const xy=(x:Port,y:Port)=>{const n=new VectorMergerBlock(label('vec2'));x.connectTo(n.x);y.connectTo(n.y);return n.xyOut;};
 const rgb=(x:Port,y:Port,z:Port)=>{const n=new VectorMergerBlock(label('vec3'));x.connectTo(n.x);y.connectTo(n.y);z.connectTo(n.z);return n.xyzOut;};
 const tex=(texture:Texture,uv:Port)=>{const n=new TextureBlock(label('texture'));n.texture=texture;n.convertToGammaSpace=false;n.convertToLinearSpace=false;uv.connectTo(n.uv);return n;};
 const position=new InputBlock('position').setAsAttribute('position'),normal=new InputBlock('normal').setAsAttribute('normal');
 const uv=new InputBlock('uv').setAsAttribute('uv'),world=new InputBlock('world').setAsSystemValue(System.World);
 const vp=new InputBlock('viewProjection').setAsSystemValue(System.ViewProjection),view=new CityWaterViewInput();
 const camera=new InputBlock('camera').setAsSystemValue(System.CameraPosition);
 const wp=new TransformBlock('worldPosition'),wn=new TransformBlock('worldNormal');wn.transformAsDirection=true;
 position.output.connectTo(wp.vector);world.output.connectTo(wp.transform);normal.output.connectTo(wn.vector);world.output.connectTo(wn.transform);
 const clip=new TransformBlock('clip');wp.output.connectTo(clip.vector);vp.output.connectTo(clip.transform);
 const vertex=new VertexOutputBlock('vertex');clip.output.connectTo(vertex.vector);material.addOutputNode(vertex);
 const direction=new ViewDirectionBlock('viewDirection');wp.output.connectTo(direction.worldPosition);camera.output.connectTo(direction.cameraPosition);
 const phaseA=input('flowPhaseA',0),phaseB=input('flowPhaseB',.5),weight=input('flowWeightB',1),phase=input('worldPhase',0);
 const ambient=input('ambientFill',new Color3(.2,.25,.28)),day=input('dayWeight',1),wet=input('rainNormalGain',1);
 const zenith=input('sharedSkyZenith',new Color3(.2,.34,.5)),horizon=input('sharedSkyHorizon',new Color3(.5,.65,.7));
 const exponent=input('sunExponent',tier.exponent),glint=input('maximumGlint',tier.glint);
 const coverage=rainPuddle?input('sharedRainCoverage',0):undefined;
 const distance=new DistanceBlock('cameraDistance');wp.xyz.connectTo(distance.left);camera.output.connectTo(distance.right);
 const fade=mul(c(.7),smooth(tier.normalStart,tier.normalEnd,distance.output));
 let normalPort:Port=wn.output,foam:Port,opacity:Port,body:Port,reflected:Port|null=null;
 let streak:TextureBlock|null=null;
 if(falls){
  const colourAttribute=new InputBlock('layerData').setAsAttribute('color');const data=new VectorSplitterBlock('layerSplit');colourAttribute.output.connectTo(data.xyzw);
  const uvSplit=new VectorSplitterBlock('fallUv');uv.output.connectTo(uvSplit.xyIn);
  const scroll=mul(mul(data.x,c(64)),div(phase.output,c(Math.PI*2)));
  streak=tex(maps.streak,xy(mul(uvSplit.x,c(.9)),sub(mul(uvSplit.y,c(1/.34907)),scroll)));
  const across=trig(uvSplit.x,Trig.Abs);
  const edge=sub(c(1),smooth(.72,1.04,add(across,mul(sub(streak.g,c(.5)),c(.12)))));
  const worldY=split(wp.output).y;
  const bottom=smooth(-.35,0,worldY);
  // Splash/lip rows have horizontal normals; their foam stays visible at water Y.
  const up=clamp(mul(split(wn.output).y,c(2)));
  opacity=mul(mul(mul(add(c(.35),mul(streak.r,c(.6))),data.y),edge),lerp(bottom,c(1),up));
  const ring=sub(c(1),smooth(.1,.6,trig(sub(mul(data.x,c(64)),c(24)),Trig.Abs)));
  const radial=mul(uvSplit.y,c(.6));
  const padFade=mul(smooth(.30,.48,radial),sub(c(1),smooth(.82,1.30,radial)));
  const padMask=mul(ring,up);
  const softPadAlpha=mul(mul(mul(data.y,c(.18)),padFade),smooth(.40,.85,streak.b));
  opacity=lerp(opacity,softPadAlpha,padMask);
  body=mul(lerp(colour('#8db9b4'),colour('#e3eee9'),streak.r),mul(data.z,c(1.1)));
  foam=streak.b;
 }else{
  const atlasUv=new InputBlock('uv2').setAsAttribute('uv2');
  const fields=tex(maps.masks,atlasUv.output),flow=tex(maps.flow,atlasUv.output);
  const velocity=xy(mul(sub(mul(flow.r,c(2)),c(1)),c(1.2*1.745)),mul(sub(mul(flow.g,c(2)),c(1)),c(1.2*1.745)));
  const tiled=mul(uv.output,input('rippleMetreScale',new Vector2(1/1.35,1/2.10)).output);
  const drift=mul(velocity,input('rippleFlowScale',new Vector2(1/1.35,1/2.10)).output);
  const ua=sub(tiled,mul(drift,phaseA.output));const ub=add(sub(tiled,mul(drift,phaseB.output)),input('halfCycleOffset',new Vector2(.37,.61)).output);
  const ra=tex(maps.ripple,ua),rb=tex(maps.ripple,ub);
  let detail=lerp(ra.rgb,rb.rgb,weight.output);
  if(tier.fetches===8){
   const sa=tex(maps.swell,mul(sub(uv.output,mul(velocity,phaseA.output)),c(1/6.5)));
   const sb=tex(maps.swell,add(mul(sub(uv.output,mul(velocity,phaseB.output)),c(1/6.5)),input('swellOffset',new Vector2(.37,.61)).output));
   detail=lerp(detail,lerp(sa.rgb,sb.rgb,weight.output),c(.24));
  }
  const perturb=new PerturbNormalBlock('twoScaleFlowNormals');wp.output.connectTo(perturb.worldPosition);wn.output.connectTo(perturb.worldNormal);uv.output.connectTo(perturb.uv);
  detail.connectTo(perturb.normalMapColor);direction.output.connectTo(perturb.viewDirection);
  mul(mul(mul(c(.30),add(c(1),mul(fields.b,c(1.5)))),wet.output),sub(c(1),fade)).connectTo(perturb.strength);normalPort=perturb.output;
  const fna=tex(maps.foam,mul(sub(uv.output,mul(velocity,phaseA.output)),c(1/1.1)));
  const fnb=tex(maps.foam,add(mul(sub(uv.output,mul(velocity,phaseB.output)),c(1/1.1)),input('foamOffset',new Vector2(.37,.61)).output));
  const noise=lerp(fna.r,fnb.r,weight.output);
  const mask=clamp(add(mul(flow.b,c(.75)),mul(c(.25),sub(c(1),smooth(.03,.28,flow.a)))));
  // Sparse, feathered bubble rims: contact coverage must not become a white
  // sheet as the baked mask approaches one at stones or the falls impact.
  foam=mul(smooth(.58,.90,noise),rainPuddle?c(0):mask);
  const vy=clamp(split(direction.output).y,.25,1);
  const optical=mul(mul(fields.r,c(1.2)),add(c(1),mul(c(.35),sub(div(c(1),vy),c(1)))));
  opacity=add(c(.16),mul(c(.78),sub(c(1),trig(mul(optical,c(-2.6)),Trig.Exp))));
  const blueprintLook=typeof location==='undefined'||new URLSearchParams(location.search).get('blueprintWave')!=='off';
  body=lerp(colour(blueprintLook?'#7cbbb1':'#6f9387'),colour(blueprintLook?'#38a9b8':'#386268'),smooth(.05,.75,optical));
  if(!ART&&blueprintLook&&!rainPuddle){
   // D5: the base cove reached the cyan endpoint and then lost all deeper
   // variation. Its exported UV2/depth samples are valid. Select only that
   // immutable atlas island and reuse the reviewed art pass's deep endpoint.
   const cove=manifest.atlas.islands.brightwater_cove_lake.rect_px;
   const island=new VectorSplitterBlock('coveAtlasUV');atlasUv.output.connectTo(island.xyIn);const w=manifest.atlas.width,h=manifest.atlas.height;
   const inside=(p:Port,lo:number,hi:number)=>mul(smooth(lo-.00001,lo,p),sub(c(1),smooth(hi,hi+.00001,p)));
   const coveWeight=mul(inside(island.x,(cove[0]+.5)/w,(cove[0]+cove[2]-.5)/w),inside(island.y,(cove[1]+.5)/h,(cove[1]+cove[3]-.5)/h));
   body=lerp(body,lerp(body,colour('#1b637b'),smooth(.38,1.15,optical)),coveWeight);
  }
  if(ART){const shallow=ART_R02?lerp(colour('#77bdb1'),colour('#719887'),day.output):colour('#77bdb1'),middle=ART_R02?lerp(colour('#38a9b8'),colour('#347c82'),day.output):colour('#38a9b8');body=lerp(lerp(shallow,middle,smooth(.03,.42,optical)),colour('#1b637b'),smooth(.38,1.15,optical));}
  const muddy=sub(c(1),fields.a);body=lerp(body,colour('#927653'),muddy);
  opacity=lerp(opacity,c(.65),muddy);
  if(ART&&rainPuddle){body=ART_R03?lerp(colour('#8a8264'),colour('#7f9d96'),smooth(.10,.80,flow.a)):colour(ART_R02?'#7d8f79':'#4e5545');opacity=c(ART_R03?.52:ART_R02?.30:.82);}
  // Reflection samples the same sky's two endpoint colours, no scene render pass.
  const reflect=new ReflectBlock('skyReflectionDirection');mul(direction.output,c(-1)).connectTo(reflect.incident);split(normalPort).xyzOut.connectTo(reflect.normal);
  const reflectY=clamp(split(reflect.output).y);
  const sky=lerp(horizon.output,zenith.output,trig(reflectY,Trig.Sqrt));
  const fresnel=new FresnelBlock('waterFresnel');normalPort.connectTo(fresnel.worldNormal);direction.output.connectTo(fresnel.viewDirection);c(.02).connectTo(fresnel.bias);c(5).connectTo(fresnel.power);
  const reflection=mul(clamp(fresnel.fresnel,0,.6),lerp(c(.8),c(.5),day.output));
  reflected=mul(sky,mul(reflection,fields.g));
  opacity=mul(add(opacity,mul(reflection,sub(c(1),opacity))),smooth(ART_R02&&rainPuddle?.02:0,ART_R02&&rainPuddle?.48:.10,flow.a));
 }
 // Native all-light path supplies Babylon's GLSL local view alias for CSM.
 // WGSL keeps the canonical uniforms.view binding from CityWaterViewInput.
 const light=new LightBlock('sharedSunMoon');
 wp.output.connectTo(light.worldPosition);normalPort.connectTo(light.worldNormal);camera.output.connectTo(light.cameraPosition);view.output.connectTo(light.view);
 const deriv=new DerivativeBlock('normalVariance');split(normalPort).xyzOut.connectTo(deriv.input);
 const variance=mul(c(.3),add(dot(deriv.dx,deriv.dx),dot(deriv.dy,deriv.dy)));
 const gloss=lerp(c(56),exponent.output,day.output);
 div(mul(gloss,sub(c(1),fade)),add(c(1),mul(gloss,variance))).connectTo(light.glossPower);c(1).connectTo(light.glossiness);
 lerp(colour('#7397e8'),colour('#fff7e6'),day.output).connectTo(light.specularColor);
 // Calibrated to the actual v2 sky fill: scattering stays multiplied by the
 // real scene light, never an emissive floor or separate scene grade.
 const scatterGain=lerp(c(falls?(ART_R03?2.4:1.8):ART?2.1:3.0),c(falls?1.85:ART?1.25:2.0),day.output);
 const fillWeight=falls&&ART_R03?lerp(c(.85),c(.35),day.output):c(falls?.35:ART_R02&&rainPuddle?.45:0);
 const sceneIrradiance=add(light.diffuseOutput,mul(ambient.output,fillWeight));
 const illumination=mul(sceneIrradiance,scatterGain);
 // Foam receives scene light once; volume scattering belongs to the body.
 const lit=mul(body,illumination);let foamLit=mul(colour('#b8c8c1'),mul(sceneIrradiance,c(.65)));
 if(ART&&!falls){const fc=split(foamLit);foamLit=rgb(clamp(fc.x,0,.44),clamp(fc.y,0,.44),clamp(fc.z,0,.44));}
 const spec=split(light.specularOutput);
 const bounded=rgb(clamp(spec.x,0,tier.glint),clamp(spec.y,0,tier.glint),clamp(spec.z,0,tier.glint));
 const specWeight=mul(sub(c(1),foam),lerp(c(.30),c(.8),day.output));
 let shaded=add(lerp(lit,foamLit,mul(foam,c(falls?.35:.55))),mul(bounded,specWeight));
 if(reflected)shaded=add(shaded,mul(reflected,sub(c(1),foam)));
 const components=split(shaded),limit=lerp(c(.22),c(1.2),day.output);
 const cap=(value:Port)=>{const ratio=clamp(div(value,limit));return mul(ratio,limit);};
 shaded=rgb(cap(components.x),cap(components.y),cap(components.z));
 const fog=new FogBlock('worldFog');wp.output.connectTo(fog.worldPosition);view.output.connectTo(fog.view);shaded.connectTo(fog.input);
 const process=new ImageProcessingBlock('worldGrade');fog.output.connectTo(process.color);
 const fragment=new FragmentOutputBlock('fragment');process.rgb.connectTo(fragment.rgb);const finalAlpha=clamp(add(opacity,mul(foam,c(falls?0:.10))));(coverage?mul(finalAlpha,coverage.output):finalAlpha).connectTo(fragment.a);material.addOutputNode(fragment);
 material.backFaceCulling=false;material.forceAlphaBlending=true;material.disableDepthWrite=true;
 return {material,phaseA,phaseB,weight,phase,ambient,day,zenith,horizon,exponent,glint,wet,coverage};
}

function build(graph:NodeMaterial):Promise<void>{return new Promise((resolve,reject)=>{
 let settled=false;const finish=(error?:Error)=>{if(settled)return;settled=true;clearTimeout(timer);graph.onBuildObservable.remove(ok);graph.onBuildErrorObservable.remove(bad);graph.onDisposeObservable.remove(dead);error?reject(error):resolve();};
 const ok=graph.onBuildObservable.addOnce(()=>finish()),bad=graph.onBuildErrorObservable.addOnce(e=>finish(new Error(e))),dead=graph.onDisposeObservable.addOnce(()=>finish(new Error('Water disposed before build')));
 const timer=setTimeout(()=>finish(new Error('Water shader build timeout')),10000);
 try{graph.build(false,true,true);}catch(e){finish(e instanceof Error?e:new Error(String(e)));}
});}
async function loadMaps(scene:Scene,low:boolean):Promise<Maps>{
 const owned:Texture[]=[];let cancelled=false;
 const raw=async(name:string)=>{const response=await fetch(asset(name));if(!response.ok)throw new Error(`Water map failed: ${name}`);const bytes=new Uint8Array(await response.arrayBuffer());const w=low?512:1024,h=low?64:128;
  if(bytes.length!==w*h*4)throw new Error(`Invalid water data bytes: ${name}`);
  if(cancelled||scene.isDisposed)throw new Error('Water loading cancelled');
  const texture=RawTexture.CreateRGBATexture(bytes,w,h,scene,false,false,Texture.BILINEAR_SAMPLINGMODE);texture.name=name;texture.gammaSpace=false;texture.wrapU=texture.wrapV=Texture.CLAMP_ADDRESSMODE;owned.push(texture);return texture;};
 const png=(name:string)=>new Promise<Texture>((resolve,reject)=>{const texture=new Texture(asset(name),scene,false,false,Texture.TRILINEAR_SAMPLINGMODE,()=>{if(cancelled||scene.isDisposed){texture.dispose();reject(new Error('Water loading cancelled'));}else resolve(texture);},()=>reject(new Error(`Water texture failed: ${name}`)));texture.gammaSpace=false;texture.wrapU=texture.wrapV=Texture.WRAP_ADDRESSMODE;texture.anisotropicFilteringLevel=low?2:4;owned.push(texture);});
 try{const [masks,flow,ripple,swell,foam,streak]=await Promise.all([raw(`water_masks${low?'_low':''}.bin`),raw(`water_flow${low?'_low':''}.bin`),png(`water_ripple_normal_${low?256:512}.png`),low?Promise.resolve(null):png('water_swell_normal_256.png'),png(`water_foam_noise_${low?128:256}.png`),png(`waterfall_streaks_${low?'64x256':'128x512'}.png`)]);return {masks,flow,ripple,swell:swell??ripple,foam,streak,owned};}
 catch(e){cancelled=true;for(const t of owned)t.dispose();throw e;}
}
export function buildNatureWaterParticleGraph(scene:Scene){
 const material=new NodeMaterial('natural-water-native-mist-spray',scene,{emitComments:false,shaderLanguage:scene.getEngine().isWebGPU?ShaderLanguage.WGSL:ShaderLanguage.GLSL});material.mode=NodeMaterialModes.Particle;
 const uv=new InputBlock('particleUV').setAsAttribute('particle_uv'),colour=new InputBlock('particleColour').setAsAttribute('particle_color');
 const center=new SubtractBlock('particleCenter');uv.output.connectTo(center.left);input('centerUV',new Vector2(.5,.5)).output.connectTo(center.right);
 const radius=new LengthBlock('softParticleRadius');center.output.connectTo(radius.value);
 const edge=new SmoothStepBlock('softMistEdge');radius.output.connectTo(edge.value);input('innerRadius',.13).output.connectTo(edge.edge0);input('outerRadius',.5).output.connectTo(edge.edge1);
 const inverse=new SubtractBlock('softAlpha');input('one',1).output.connectTo(inverse.left);edge.output.connectTo(inverse.right);
 const data=new VectorSplitterBlock('particleChannels');colour.output.connectTo(data.xyzw);
 const light=input('sceneParticleLight',new Color3(.5,.5,.5)),rgb=new MultiplyBlock('litMistColour');data.xyzOut.connectTo(rgb.left);light.output.connectTo(rgb.right);
 const alpha=new MultiplyBlock('particleLifeAlpha');data.w.connectTo(alpha.left);inverse.output.connectTo(alpha.right);
 const processing=new ImageProcessingBlock('worldParticleGrade');rgb.output.connectTo(processing.color);
 const output=new FragmentOutputBlock('particleFragment');processing.rgb.connectTo(output.rgb);alpha.output.connectTo(output.a);material.addOutputNode(output);
 return {material,light};
}
export function makeNatureWaterParticles(scene:Scene,name:string,capacity:number,white:Texture,mist:boolean){
 const system=new ParticleSystem(name,capacity,scene);system.emitter=Vector3.Zero();system.particleTexture=white;
 system.blendMode=ParticleSystem.BLENDMODE_STANDARD;system.renderingGroupId=1;system.preventAutoStart=true;system.disposeOnStop=false;
 system.minEmitPower=system.maxEmitPower=1;system.emitRate=0;system.paused=true;
 system.minLifeTime=mist?2.4:.45;system.maxLifeTime=mist?3.4:.75;
 system.minSize=mist?.9:.035;system.maxSize=mist?1.4:.08;system.gravity.set(0,mist?0:-9.81,0);
 const emitter=new CustomParticleEmitter();
 const landing=manifest.anchors.anchor_sm_falls_landing.position;
 emitter.particlePositionGenerator=(_i,_particle,p)=>{const angle=Math.random()*Math.PI*2,radius=Math.sqrt(Math.random())*.9;p.set(landing[0]+Math.cos(angle)*radius,landing[1]+.15,landing[2]+Math.sin(angle)*radius);};
 emitter.particleDirectionGenerator=(_i,_particle,d)=>{const angle=Math.random()*Math.PI*2;d.set(mist?-.25+Math.cos(angle)*.15:Math.cos(angle)*.9,mist?.45:2.1,mist?Math.sin(angle)*.15:Math.sin(angle)*.9);};
 system.particleEmitterType=emitter;
 system.addColorGradient(0,new Color4(.72,.80,.79,0));system.addColorGradient(.3,new Color4(.72,.80,.79,mist?.16:.55));system.addColorGradient(1,new Color4(.72,.80,.79,0));
 if(mist){system.addSizeGradient(0,1);system.addSizeGradient(1,1.9);}
 return system;
}

/** Opt-in scene-local visual water. The shared weather channel is its sole clock. */
export function createNatureWater(scene:Scene,getProfile:()=>ResolvedGraphicsPreset,glow?:GlowLayer|null,options:{support?:boolean;particles?:boolean}={}):NatureWaterController {
 validateWaterManifest(manifest);
 let disposed=false,revealed=false,ready=false,culled=false,error:string|null=null,clockRevision:number|null=null;
 let container:AssetContainer|null=null,maps:Maps|null=null,graphs:Graph[]=[];let waterMeshes:Mesh[]=[];
 let support:AssetContainer|null=null;const floorMaterials:PBRMaterial[]=[],floorTextures:Texture[]=[],borrowedFloorTextures=new Set<Texture>();let floorMeshes:Mesh[]=[];
 let fx:ReturnType<typeof buildNatureWaterParticleGraph>|null=null,white:Texture|null=null,systems:ParticleSystem[]=[];
 let particlesActive=false;
 let puddleMesh:Mesh|null=null,puddleMasks:Texture|null=null,puddleFlow:Texture|null=null;
 const rainPuddles={ready:false,requested:0,accepted:[] as string[],groundingPending:[] as string[],visible:false,rain:0,triangles:0,draws:0,clockRevision:null as number|null,physicalSupportY:0,hostCut:false};
 let selectedFalls:Mesh|null=null;
 const status={ready:false,revealed:false,error:null as string|null,stage:'textures',rainPuddles,bankEdge:null as null|{mode:string;albedoTexture:string;borrowed:boolean;ownedSamplerCount:number;positionsChanged:boolean;opaque:boolean}};
 scene.metadata={...scene.metadata,naturalWater:status};
 let tierName=getProfile().preset,selected=waterTier(tierName),lastSkyMs=-Infinity,switching=false;
 const hemi=scene.getLightByName('env-sky-fill') as HemisphericLight|null;
 const applyPuddleVisibility=()=>{const enabled=!!puddleMesh&&rainPuddleVisibility({ready:ready&&rainPuddles.ready,revealed,culled,rain:rainPuddles.rain});if(puddleMesh&&puddleMesh.isEnabled()!==enabled)puddleMesh.setEnabled(enabled);rainPuddles.visible=enabled;rainPuddles.draws=enabled?1:0;};
 const applyVisibility=()=>{for(const mesh of floorMeshes)mesh.setEnabled(ready&&!culled);for(const mesh of waterMeshes)mesh.setEnabled(ready&&revealed&&!culled&&(mesh.name==='fx_water_sm_surface'||mesh.name===`fx_waterfall_sm_lod${selected.lod}`));applyPuddleVisibility();};
 const stopParticles=()=>{if(!particlesActive)return;for(const system of systems){system.emitRate=0;system.paused=true;system.stop();system.reset();}particlesActive=false;};
 const refresh=()=>{
  if(disposed||!ready)return;
  const frame=readWeatherFrame(scene);if(!frame)return;clockRevision=frame.clockRevision;rainPuddles.rain=frame.appearance.rain;rainPuddles.clockRevision=frame.clockRevision;
  const profile=getProfile();if(profile.preset!==tierName&&!switching){void replaceTier(profile.preset);return;}
  const phase=frame.phase,cycle=((phase/(Math.PI*2)*8)%1+1)%1;
  const daylight=Math.min(1,Math.max(0,frame.appearance.daylight));
  for(const g of graphs){g.phaseA.value=cycle;g.phaseB.value=(cycle+.5)%1;g.weight.value=Math.abs(2*cycle-1);g.phase.value=phase;g.day.value=daylight;
   g.exponent.value=selected.exponent;g.glint.value=selected.glint;g.wet.value=1+frame.appearance.rain*.35;
   if(g.coverage)g.coverage.value=frame.appearance.rain;
   if(hemi){const fill=g.ambient.value as Color3;hemi.diffuse.scaleToRef(hemi.intensity,fill);}
  }
  if(frame.worldMs-lastSkyMs>2000||frame.worldMs<lastSkyMs){lastSkyMs=frame.worldMs;
   const sky=scene.getTextureByName('env-sky-texture') as Texture&{getContext?():CanvasRenderingContext2D};
   const context=sky?.getContext?.();if(context){try{const z=context.getImageData(0,0,1,1).data,h=context.getImageData(0,195,1,1).data;
    for(const g of graphs){(g.zenith.value as Color3).set(z[0]/255,z[1]/255,z[2]/255).toLinearSpaceToRef(g.zenith.value as Color3);(g.horizon.value as Color3).set(h[0]/255,h[1]/255,h[2]/255).toLinearSpaceToRef(g.horizon.value as Color3);}
   }catch{/* A tainted sky uses existing bounded fallback colours. */}}
  }
  const camera=scene.activeCamera;if(camera){const dx=camera.position.x+34,dz=camera.position.z+40;const next=dx*dx+dz*dz>220*220;if(next!==culled){culled=next;applyVisibility();}}
  if(puddleMesh)applyPuddleVisibility();
  if(fx&&hemi){const light=fx.light.value as Color3;hemi.diffuse.scaleToRef(Math.min(1,hemi.intensity*(3-2*daylight)+daylight*.6),light);}
  const landing=manifest.anchors.anchor_sm_falls_landing.position;
  const fxNear=camera&&((camera.position.x-landing[0])**2+(camera.position.z-landing[2])**2<90*90);
  // Scene's planes are populated during the first active-mesh evaluation,
  // after onBeforeRender. Warmup/first update must not index an absent array.
  const planes=scene.frustumPlanes;
  const fxVisible=ready&&revealed&&!culled&&fxNear&&planes?.length===6&&selectedFalls?.isInFrustum(planes);
  if(!fxVisible)stopParticles();else if(!particlesActive){for(let i=0;i<systems.length;i++){systems[i].paused=false;systems[i].emitRate=i===0?5:45;systems[i].start();}particlesActive=true;}
 };
 async function replaceTier(next:string){
  switching=true;ready=false;status.ready=false;status.stage='tier-warmup';stopParticles();applyVisibility();const priorMaps=maps,priorGraphs=graphs;
  let nextMaps:Maps|null=null,nextGraphs:Graph[]=[];
  try{
   const nextTier=waterTier(next);nextMaps=await loadMaps(scene,next==='low');if(disposed){for(const t of nextMaps.owned)t.dispose();return;}
   nextGraphs=[buildNatureWaterGraph(scene,nextMaps,nextTier),buildNatureWaterGraph(scene,nextMaps,nextTier,true)];
   if(puddleMesh&&puddleMasks&&puddleFlow)nextGraphs.push(buildNatureWaterGraph(scene,{...nextMaps,masks:puddleMasks,flow:puddleFlow},nextTier,false,true));
   await Promise.all(nextGraphs.map(g=>build(g.material)));if(disposed){for(const g of nextGraphs)g.material.dispose(false,false);for(const t of nextMaps.owned)t.dispose();return;}
   for(const mesh of waterMeshes)mesh.material=nextGraphs[mesh.name==='fx_water_sm_surface'?0:1].material;
   if(puddleMesh)puddleMesh.material=nextGraphs[2].material;
   await Promise.all(waterMeshes.map(mesh=>mesh.material!.forceCompilationAsync(mesh)));
   if(puddleMesh)await puddleMesh.material!.forceCompilationAsync(puddleMesh);
   if(disposed){for(const g of nextGraphs)g.material.dispose(false,false);for(const t of nextMaps.owned)t.dispose();return;}
   await repoolParticles(next);
   maps=nextMaps;graphs=nextGraphs;tierName=next as typeof tierName;selected=nextTier;
   selectedFalls=waterMeshes.find(m=>m.name===`fx_waterfall_sm_lod${selected.lod}`)??null;
   for(const g of priorGraphs)g.material.dispose(false,false);for(const t of priorMaps?.owned??[])t.dispose();
   lastSkyMs=-Infinity;ready=true;status.ready=true;status.stage='ready';refresh();applyVisibility();
  }catch(e){for(const g of nextGraphs)g.material.dispose(false,false);for(const t of nextMaps?.owned??[])t.dispose();error=e instanceof Error?e.message:String(e);
   // Failed warmup is a review failure. Hide and release the whole controller
   // rather than retaining an over-budget tier after a requested downgrade.
   status.error=error;status.stage='tier-failed';dispose();
  }finally{switching=false;}
 }
 async function repoolParticles(name:string=tierName){
  if(!fx||!white||disposed)return;stopParticles();
  const caps=name==='low'?[8,12]:name==='medium'?[12,24]:name==='high'?[16,40]:[20,56];
  const candidate=[makeNatureWaterParticles(scene,'natural-water-base-mist',caps[0],white,true),makeNatureWaterParticles(scene,'natural-water-impact-spray',caps[1],white,false)];
  try{await Promise.all(candidate.map(system=>new Promise<void>((resolve,reject)=>{
   fx!.material.createEffectForParticles(system);
   const effect=system.getCustomEffect(ParticleSystem.BLENDMODE_ONEONE);
   if(!effect){reject(new Error('Native water particle effect missing'));return;}
   // NME supplies additive/multiply variants; bind the same alpha shader for
   // STANDARD blending. executeWhenCompiled also covers an already cached effect.
   system.setCustomEffect(effect,ParticleSystem.BLENDMODE_STANDARD);
   let settled=false;const finish=(error?:Error)=>{if(settled)return;settled=true;clearTimeout(timer);effect.onErrorObservable.remove(failed);error?reject(error):resolve();};
   const timer=setTimeout(()=>finish(new Error('Water particle warmup timed out')),10000);
   const failed=effect.onErrorObservable.addOnce(()=>finish(new Error(effect.getCompilationError())));
   effect.executeWhenCompiled(()=>finish());
  })));
   if(disposed){for(const system of candidate)system.dispose(false);return;}
   for(const system of systems)system.dispose(false);systems=candidate;
  }catch(e){for(const system of candidate)system.dispose(false);throw e;}
 }
 const observer=scene.onBeforeRenderObservable.add(()=>{try{refresh();}catch(e){error=e instanceof Error?e.message:String(e);status.error=error;status.stage='refresh-failed';console.error('[natural-water-refresh]',e instanceof Error?e.stack:String(e));dispose();}});
 const dispose=()=>{if(disposed)return;disposed=true;ready=false;revealed=false;status.ready=false;status.revealed=false;controllers.delete(scene);stopParticles();scene.onBeforeRenderObservable.remove(observer);scene.onDisposeObservable.remove(disposal);
  if(puddleMesh){glow?.removeExcludedMesh(puddleMesh);puddleMesh.dispose(false,false);}puddleMasks?.dispose();puddleFlow?.dispose();rainPuddles.ready=false;rainPuddles.visible=false;rainPuddles.draws=0;
  for(const system of systems)system.dispose(false);fx?.material.dispose(false,false);white?.dispose();systems=[];
  releaseWaterFloorAssets(support,floorMaterials,floorTextures,borrowedFloorTextures);floorMeshes=[];
  for(const mesh of waterMeshes)glow?.removeExcludedMesh(mesh);container?.dispose();for(const g of graphs)g.material.dispose(false,false);for(const texture of maps?.owned??[])texture.dispose();graphs=[];waterMeshes=[];};
 const disposal=scene.onDisposeObservable.addOnce(dispose);
 const promise=(async()=>{
  maps=await loadMaps(scene,tierName==='low');if(disposed){for(const t of maps.owned)t.dispose();return;}
  status.stage='geometry';container=await SceneLoader.LoadAssetContainerAsync('',asset(manifest.glb),scene);if(disposed){container.dispose();return;}
  if(options.support!==false){
   support=await SceneLoader.LoadAssetContainerAsync('',asset(manifest.support.runtime_glb),scene);if(disposed){support.dispose();return;}
   alignWorldAuthoredGlb(support,scene);
   const floorMap=(name:string,gamma:boolean)=>{const t=new Texture(asset(name),scene,false,false);t.gammaSpace=gamma;floorTextures.push(t);return t;};
   const bed=createOwnedWaterFloorMaterial('natural-water-painted-bed',scene,floorMaterials);bed.albedoTexture=floorMap('stream_bed_albedo_512.png',true);bed.bumpTexture=floorMap('stream_bed_normal_512.png',false);bed.roughness=.88;bed.metallic=0;if(ART_R02)bed.albedoColor=new Color3(.76,.84,.68);
   const bank=createOwnedWaterFloorMaterial('natural-water-painted-bank',scene,floorMaterials);bank.albedoTexture=floorMap('bank_strip_albedo_256x512.png',true);bank.bumpTexture=floorMap('bank_strip_normal_256x512.png',false);bank.albedoTexture.wrapU=Texture.CLAMP_ADDRESSMODE;bank.roughness=.85;bank.metallic=0;bank.transparencyMode=ART?PBRMaterial.PBRMATERIAL_ALPHABLEND:PBRMaterial.PBRMATERIAL_ALPHATEST;bank.alphaCutOff=ART?0:.5;bank.zOffset=-1;if(ART){bank.albedoTexture.hasAlpha=true;bank.useAlphaFromAlbedoTexture=true;bank.albedoColor=Color3.FromHexString('#bbc58e');bank.disableDepthWrite=true;}
   if(ART_R02){bank.transparencyMode=PBRMaterial.PBRMATERIAL_OPAQUE;bank.useAlphaFromAlbedoTexture=false;bank.albedoTexture.hasAlpha=false;bank.disableDepthWrite=false;new WaterArtBankEdgePlugin(bank,ART_R03?3:2);}
   if(ART_R03){const land=adoptWaterBankGround(scene,bank,borrowedFloorTextures);addMeadowSurface(bank);status.bankEdge={mode:'SHARED_GROUND_WORLD_UV',albedoTexture:land.albedoTexture!.name,borrowed:true,ownedSamplerCount:2,positionsChanged:false,opaque:true};}
   floorMeshes=support.meshes.filter((m):m is Mesh=>m instanceof Mesh&&m.getTotalVertices()>0);
   for(const mesh of floorMeshes){mesh.material=mesh.name.includes('channel_bed')?bed:bank;if(ART_R03&&mesh.material===bank)projectWaterBankUV(mesh);mesh.receiveShadows=true;mesh.isPickable=false;mesh.metadata={...mesh.metadata,glow:false};mesh.setEnabled(false);}
   support.addAllToScene();
  }
  alignWorldAuthoredGlb(container,scene);
  waterMeshes=container.meshes.filter((m):m is Mesh=>m instanceof Mesh&&m.getTotalVertices()>0);
  if(import.meta.env.DEV&&new URLSearchParams(location.search).get('blueprintWave')==='off'){
   const surface=waterMeshes.find(m=>m.name==='fx_water_sm_surface');
   if(surface&&manifest.blueprint)surface.setIndices(Array.from(surface.getIndices()!).slice(0,manifest.blueprint.original_surface_triangles*3));
   const bodies=(derived.lakes as {id:string;outline_xz?:number[][]}[]).filter(b=>b.id.startsWith('blueprint_'));
   for(const mesh of floorMeshes){const p=mesh.getVerticesData('position')!,indices=mesh.getIndices()!,keep:number[]=[],m=mesh.computeWorldMatrix(true).asArray();
    for(let i=0;i<indices.length;i+=3){const cx=(p[indices[i]*3]+p[indices[i+1]*3]+p[indices[i+2]*3])/3,cy=(p[indices[i]*3+1]+p[indices[i+1]*3+1]+p[indices[i+2]*3+1])/3,cz=(p[indices[i]*3+2]+p[indices[i+1]*3+2]+p[indices[i+2]*3+2])/3,x=cx*m[0]+cy*m[4]+cz*m[8]+m[12],z=cx*m[2]+cy*m[6]+cz*m[10]+m[14];
     if(!bodies.some(b=>{const xs=b.outline_xz?.map(q=>q[0])??[],zs=b.outline_xz?.map(q=>q[1])??[];return x>=Math.min(...xs)-.7&&x<=Math.max(...xs)+.7&&z>=Math.min(...zs)-.7&&z<=Math.max(...zs)+.7;}))keep.push(indices[i],indices[i+1],indices[i+2]);}
    mesh.setIndices(keep);
   }
  }
  selectedFalls=waterMeshes.find(m=>m.name===`fx_waterfall_sm_lod${selected.lod}`)??null;
  graphs=[buildNatureWaterGraph(scene,maps,selected),buildNatureWaterGraph(scene,maps,selected,true)];
  for(const mesh of waterMeshes){mesh.material=graphs[mesh.name==='fx_water_sm_surface'?0:1].material;mesh.isPickable=false;mesh.receiveShadows=true;mesh.alphaIndex=mesh.name==='fx_water_sm_surface'?10:11;mesh.metadata={...mesh.metadata,glow:false,natureWater:true};mesh.setEnabled(false);glow?.addExcludedMesh(mesh);}
  status.stage='graph-build';container.addAllToScene();await Promise.all(graphs.map(g=>build(g.material)));
  status.stage='mesh-warmup';
  await Promise.all(waterMeshes.map(mesh=>mesh.material!.forceCompilationAsync(mesh)));
  await Promise.all(floorMeshes.map(mesh=>mesh.material!.forceCompilationAsync(mesh)));
  if(options.particles!==false){
   white=RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene,false,false,Texture.NEAREST_SAMPLINGMODE);white.gammaSpace=false;
   fx=buildNatureWaterParticleGraph(scene);await build(fx.material);if(disposed){fx.material.dispose(false,false);white.dispose();return;}
   scene.setRenderingAutoClearDepthStencil(1,false);
   status.stage='particle-warmup';await repoolParticles();
  }
  ready=true;status.ready=true;status.stage='ready';refresh();applyVisibility();
  const request=scene.metadata?.blueprintRainRequest as {bodies:RainPuddleBody[];groundAt:(x:number,z:number)=>number|null}|undefined;
  if(request){status.stage='rain-puddle-warmup';await configureRainPuddles(request.bodies,request.groundAt);status.stage='ready';}
 })().catch(e=>{error=e instanceof Error?e.message:String(e);status.error=error;console.error('[natural-water]',status.stage,error);dispose();throw e;});
 async function configureRainPuddles(bodies:readonly RainPuddleBody[],groundAt:(x:number,z:number)=>number|null){
  if(!ready)await promise;if(disposed||!maps||puddleMesh)return;rainPuddles.requested=bodies.length;
  const support=supportedRainPuddles([...bodies],groundAt,{maxOutlineVertices:ART_R02?48:32}),valid=support.accepted;rainPuddles.groundingPending.push(...support.pending);
  if(!valid.length){rainPuddles.ready=true;return;}switching=true;
  const size=16,mask=new Uint8Array(size*size*4),flow=new Uint8Array(size*size*4);
  for(let y=0;y<size;y++)for(let x=0;x<size;x++){const k=(y*size+x)*4,qx=(x+.5)/size-.5,qy=(y+.5)/size-.5,d=Math.hypot(qx,qy),a=Math.atan2(qy,qx),noise=ART?.022*Math.sin(a*5+.7)+.014*Math.sin(a*9+1.9):0,edge=Math.max(0,Math.min(1,ART_R02?(.46-d)/.16:(.49+noise-d)/.09));mask.set([Math.round(4*edge),255,0,255],k);flow.set([128,128,0,Math.round(255*edge)],k);}
  puddleMasks=RawTexture.CreateRGBATexture(mask,size,size,scene,false,false,Texture.BILINEAR_SAMPLINGMODE);puddleFlow=RawTexture.CreateRGBATexture(flow,size,size,scene,false,false,Texture.BILINEAR_SAMPLINGMODE);
  for(const t of [puddleMasks,puddleFlow]){t.gammaSpace=false;t.wrapU=Texture.CLAMP_ADDRESSMODE;t.wrapV=Texture.CLAMP_ADDRESSMODE;}
  const positions:number[]=[],indices:number[]=[],uvs:number[]=[],uv2s:number[]=[];
  for(const b of valid){const start=positions.length/3,c=b.center_xz,rx=Math.max(...b.outline_xz.map(p=>Math.abs(p[0]-c[0]))),rz=Math.max(...b.outline_xz.map(p=>Math.abs(p[1]-c[1])));positions.push(c[0],b.surface_y,c[1]);uvs.push(c[0],c[1]);uv2s.push(.5,.5);
   for(const p of b.outline_xz){positions.push(p[0],b.surface_y,p[1]);uvs.push(p[0],p[1]);uv2s.push(...rainPuddleAtlasUV(p,c,rx,rz,ART_R02));}
   for(let k=0;k<b.outline_xz.length;k++)indices.push(start,start+k+1,start+(k+1)%b.outline_xz.length+1);
  }
  puddleMesh=new Mesh('fx_water_blueprint_P4_rain_only',scene);const data=new VertexData();data.positions=positions;data.indices=indices;data.uvs=uvs;data.uvs2=uv2s;data.normals=[];VertexData.ComputeNormals(positions,indices,data.normals);data.applyToMesh(puddleMesh);puddleMesh.setEnabled(false);puddleMesh.isPickable=false;puddleMesh.metadata={natureWater:true,blueprintId:'P4',rainOnly:true,physicalSupportY:0,hostCut:false,glow:false};glow?.addExcludedMesh(puddleMesh);
  const graph=buildNatureWaterGraph(scene,{...maps,masks:puddleMasks,flow:puddleFlow},selected,false,true);graph.material.name='natural-water-rain-puddles';puddleMesh.material=graph.material;puddleMesh.alphaIndex=12;
  try{await build(graph.material);await graph.material.forceCompilationAsync(puddleMesh);if(disposed){graph.material.dispose(false,false);return;}graphs.push(graph);rainPuddles.accepted=valid.map(b=>b.id);rainPuddles.triangles=indices.length/3;rainPuddles.ready=true;refresh();applyVisibility();}catch(e){graph.material.dispose(false,false);status.error=String(e);dispose();throw e;}finally{switching=false;}
 }
 const controller:NatureWaterController={ready:promise,reveal(){revealed=true;status.revealed=true;applyVisibility();},hide(){revealed=false;status.revealed=false;applyVisibility();stopParticles();},dispose,anchors:()=>manifest.anchors,configureRainPuddles,
  stats:()=>({ready,revealed,culled,tier:tierName,waterDraws:(ready&&revealed&&!culled?2:0)+rainPuddles.draws,surfaceTriangles:manifest.meshes.surface.triangles+rainPuddles.triangles,fallsTriangles:manifest.meshes[`falls${selected.lod}` as 'falls0'].triangles,vertexBuffers:4,samplers:selected.fetches,reflectionScenePasses:0,clockRevision,error})};
 controllers.set(scene,controller);return controller;
}
