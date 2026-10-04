import { MaterialPluginBase } from '@babylonjs/core/Materials/materialPluginBase';
import type { MaterialDefines } from '@babylonjs/core/Materials/materialDefines';
import { ShaderLanguage } from '@babylonjs/core/Materials/shaderLanguage';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
import type { UniformBuffer } from '@babylonjs/core/Materials/uniformBuffer';
import { Texture } from '@babylonjs/core/Materials/Textures/texture';
import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { VertexData } from '@babylonjs/core/Meshes/mesh.vertexData';
import { BoundingInfo } from '@babylonjs/core/Culling/boundingInfo';
import { Vector3 } from '@babylonjs/core/Maths/math.vector';
import type { AbstractMesh } from '@babylonjs/core/Meshes/abstractMesh';
import type { Scene } from '@babylonjs/core/scene';
import type { Observer } from '@babylonjs/core/Misc/observable';
import type { GlowLayer } from '@babylonjs/core/Layers/glowLayer';
import type { ResolvedGraphicsPreset } from './graphics-quality.mjs';
import { readWeatherFrame } from './ambient-weather-channel';
import type { NatureClock } from './nature-motion';
import { createWaterTerrainSampler } from './nature-water.mjs';
import { grassCustomCode, GRASS_UNIFORMS, GRASS_ATTRIBUTE, GRASS_SAMPLER, GRASS_GLSL_UNIFORMS } from './grass-field-shaders.mjs';
import { compileRules, grassRulesFromLayout, grassCellAllowance, generateTuftPatch, generatePlantBlock, packInstances, patchRange, buildTuftGeometry, buildFlowerGeometry, buildCloverGeometry, resolveGrassTier, grassBands, scaleBands, aabbDistance, prefixFraction, lowerBound, governGrass, REGION_CAP, stableHash, type GrassInstance, type PackedGrass, type GrassTier, type GrassBands } from './grass-placement.mjs';
import layout from '../../../planning/levels/sunmeadow-v2-layout.json';
import dressing from '../../../planning/levels/sunmeadow-v3-dressing.json';
import monsters from '../../../planning/levels/sunmeadow-v2-monsters.json';
import waterDerived from '../../../planning/evidence/water-20261002/water-derived.json';
import blueprint from '../../../planning/levels/sunmeadow-blueprint-v1.json';
import atlasManifest from './assets/world/grass-v1/grass_atlas_v1.json';
import atlasFull from './assets/world/grass-v1/grass_atlas_v1_albedo.ktx2?url';
import atlasHalf from './assets/world/grass-v1/grass_atlas_v1_1024_albedo.ktx2?url';
import '@babylonjs/core/Meshes/thinInstanceMesh';
import {bayerDitherFunctions} from '@babylonjs/core/Shaders/ShadersInclude/bayerDitherFunctions';
import {bayerDitherFunctionsWGSL} from '@babylonjs/core/ShadersWGSL/ShadersInclude/bayerDitherFunctions';

interface FieldState {tier:GrassTier;bands:GrassBands;phase:number;wind:number;day:number;ground:PBRMaterial;atlas:Texture;}
class GrassFieldPlugin extends MaterialPluginBase {
	constructor(material:PBRMaterial,private readonly state:FieldState,private readonly sparse:boolean){
		super(material,'GrassField',190,{GRASS_FIELD:true,GRASS_GROUND_TEX:true,GRASS_DEBUG:0},true,false);
		this.registerForExtraEvents=true;this._enable(true);
	}
	isCompatible(language:ShaderLanguage){return language===ShaderLanguage.GLSL||language===ShaderLanguage.WGSL;}
	prepareDefines(defines:MaterialDefines){defines.GRASS_FIELD=true;defines.GRASS_GROUND_TEX=true;defines.GRASS_DEBUG=0;}
	getAttributes(attributes:string[]){attributes.push(GRASS_ATTRIBUTE);}
	getSamplers(samplers:string[]){samplers.push(GRASS_SAMPLER);}
	getUniforms(language=ShaderLanguage.GLSL){return {ubo:GRASS_UNIFORMS.map(name=>({name,size:4,type:'vec4'})),vertex:language===ShaderLanguage.GLSL?GRASS_GLSL_UNIFORMS:'',fragment:language===ShaderLanguage.GLSL?GRASS_GLSL_UNIFORMS:''};}
	hardBindForSubMesh(buffer:UniformBuffer){
		const s=this.state,b=this.sparse?scaleBands(s.bands,s.tier.plantDistance):s.bands;
		buffer.updateFloat4('grassBand',b.near,b.mid,b.end,b.far);
		buffer.updateFloat4('grassTier',b.fTier,b.window,.6,0);
		buffer.updateFloat4('grassWind',s.phase,.14*s.wind,0,0);
		buffer.updateFloat4('grassBender',0,0,0,0);
		buffer.updateFloat4('grassAtlas',8,4,5,0); // Native KTX2 mips already preserve alpha coverage.
		buffer.updateFloat4('grassGround',s.ground.albedoColor.r,s.ground.albedoColor.g,s.ground.albedoColor.b,1/6);
		buffer.updateFloat4('grassGroundFlip',0,0,0,0);
		buffer.updateFloat4('grassNight',(1-s.day)*.55,.38,.88,.75);
		buffer.updateFloat4('grassLook',.025,.24,.15,.35);
		if(s.ground.albedoTexture)buffer.setTexture(GRASS_SAMPLER,s.ground.albedoTexture);
	}
	getCustomCode(stage:string,language=ShaderLanguage.GLSL):Record<string,string>|null{
		const wgsl=language===ShaderLanguage.WGSL,code=grassCustomCode(stage,wgsl);if(!code)return null;
		// Material plugins inject after the include pass. Expand the engine's own helper at this boundary.
		return Object.fromEntries(Object.entries(code).map(([key,value])=>[key,(value as string).replace('#include<bayerDitherFunctions>',wgsl?bayerDitherFunctionsWGSL.shader:bayerDitherFunctions.shader).replaceAll('bayerDither','grassBayerDither').replaceAll('#ifdef GRASS_FIELD','#if defined(GRASS_FIELD) && defined(INSTANCES)')]));
	}
}

export interface GrassFieldOptions {terrainMaterial:PBRMaterial;natureClock:NatureClock;glow:GlowLayer|null;profile:()=>ResolvedGraphicsPreset;}
export interface GrassFieldController {readonly ready:Promise<void>;applyProfile(profile:ResolvedGraphicsPreset):void;diagnostics():Record<string,unknown>;adoptTerrainCells(meshes:readonly AbstractMesh[]):void;dispose():void;}
const fields=new WeakMap<Scene,GrassFieldController>();
export const getGrassField=(scene:Scene)=>fields.get(scene)??null;

/** Native PBR + one packed thin-instance attribute: position/normal/uv + world0..3 + grassInst = 8 buffers. */
export function createGrassField(scene:Scene,options:GrassFieldOptions):GrassFieldController {
	if(fields.has(scene))throw new Error('Scene already owns a grass field');
	if(atlasManifest.schema!=='xexoria.grass-atlas/1')throw new Error('Unsupported grass atlas contract');
	const reviewHidden=import.meta.env.DEV&&new URLSearchParams(location.search).get('grassHidden')==='1';
	const query=new URLSearchParams(location.search),blueprintEnabled=query.get('dressing')==='v3'&&query.get('blueprintWave')!=='off';
	const activeWater=blueprintEnabled?waterDerived:{...waterDerived,lakes:waterDerived.lakes.filter(body=>!('blueprint_id' in body)&&!body.id.startsWith('blueprint_'))};
	const rulesData=grassRulesFromLayout(layout,dressing,monsters,activeWater,blueprintEnabled?blueprint:null),rules=compileRules(rulesData);
	const terrainSample=createWaterTerrainSampler(activeWater);
	const tier=resolveGrassTier(options.profile());
	const textureReady:Promise<void>[]=[];
	const loadTexture=(url:string)=>{let resolve!:()=>void,reject!:(error:Error)=>void;textureReady.push(new Promise<void>((a,b)=>{resolve=a;reject=b;}));return new Texture(url,scene,false,false,Texture.TRILINEAR_SAMPLINGMODE,resolve,(message)=>reject(new Error(message??'Grass atlas unavailable')));};
	const textures=[loadTexture(atlasFull),loadTexture(atlasHalf)];
	for(const tex of textures){tex.name='env-grass-atlas';tex.hasAlpha=true;tex.gammaSpace=true;tex.wrapU=tex.wrapV=Texture.CLAMP_ADDRESSMODE;tex.anisotropicFilteringLevel=4;}
	const state:FieldState={tier,bands:grassBands(tier),phase:options.natureClock.phase,wind:1,day:1,ground:options.terrainMaterial,atlas:textures[tier.atlas==='half'?1:0]};
	const materials=[false,true].map(sparse=>{const m=new PBRMaterial(`env-grass-${sparse?'plants':'tufts'}`,scene);m.albedoTexture=state.atlas;m.useAlphaFromAlbedoTexture=true;m.transparencyMode=PBRMaterial.PBRMATERIAL_ALPHATEST;m.alphaCutOff=.02;m.metallic=0;m.roughness=.94;m.backFaceCulling=false;m.twoSidedLighting=false;m.maxSimultaneousLights=4;m.directIntensity=options.terrainMaterial.directIntensity;new GrassFieldPlugin(m,state,sparse);return m;});
	const geometry=[buildTuftGeometry(7,blueprintEnabled?6:3),buildFlowerGeometry(),buildCloverGeometry()];
	const masters=geometry.map((g,i)=>{const m=new Mesh(`env-grass-master-${i}`,scene),v=new VertexData();v.positions=g.positions;v.normals=g.normals;v.uvs=g.uvs;v.indices=g.indices;v.applyToMesh(m);m.setEnabled(false);return m;});
	const cellKeys=(min:number[],max:number[])=>{const keys:string[]=[];for(let i=Math.max(Math.floor(rules.domain[0]/64),Math.floor(min[0]/64));i<=Math.min(Math.floor((rules.domain[1]-.001)/64),Math.floor(max[0]/64));i++)for(let j=Math.max(Math.floor(rules.domain[2]/64),Math.floor(min[2]/64));j<=Math.min(Math.floor((rules.domain[3]-.001)/64),Math.floor(max[2]/64));j++)keys.push(`${i},${j}`);return keys;};
	interface Patch {mesh:Mesh;packed:PackedGrass;kind:number;distance:number;cells:string[];}
	const patches:Patch[]=[];
	const hidden=new Map<AbstractMesh,boolean>();
	let disposed=false,ready=false,error:string|null=null,generated=0,submitted=0,draws=0,governor={factor:1,quiet:0},lodElapsed=1,cpuLastMs=0,disposeObserver:Observer<Scene>|null=null;
	let cellBudgetReadback:{cell:string;baseTriangles:number;grassTriangles:number;limit:number}[]=[];
	const inDomain=(it:GrassInstance)=>it.x>=rules.domain[0]&&it.x<rules.domain[1]&&it.z>=rules.domain[2]&&it.z<rules.domain[3]&&!terrainSample(it.x,it.z);
	const add=(list:GrassInstance[],kind:number,id:string)=>{
		const kept=list.filter(inDomain).slice(0,Math.max(0,REGION_CAP-generated));if(!kept.length)return;
		const packed=packInstances(kept),mesh=new Mesh(`env-grass-${kind}-${id}`,scene);
		masters[kind].geometry!.applyToMesh(mesh);mesh.makeGeometryUnique();mesh.material=materials[kind===0?0:1];mesh.isPickable=false;mesh.receiveShadows=['high','ultra','epic'].includes(state.tier.preset);
		mesh.thinInstanceSetBuffer('matrix',packed.matrices,16,true);mesh.thinInstanceSetBuffer(GRASS_ATTRIBUTE,packed.data,4,true);
		const bounds=packed.bounds!;mesh.setBoundingInfo(new BoundingInfo(Vector3.FromArray(bounds.min),Vector3.FromArray(bounds.max)));
		mesh.freezeWorldMatrix();mesh.setEnabled(false);options.glow?.addExcludedMesh(mesh);patches.push({mesh,packed,kind,distance:Infinity,cells:cellKeys(bounds.min,bounds.max)});generated+=kept.length;
	};
	const adoptTerrainCells=(meshes:readonly AbstractMesh[])=>{
		if(disposed||!ready||!state.tier.enabled)return;
		for(const mesh of meshes){
			if(hidden.has(mesh)||mesh.isDisposed())continue;
			if(!(/^env-(blade-|grass-|flower-)/.test(mesh.name)&&!mesh.name.startsWith('env-grass-'))&&!(/^Cell /.test(mesh.name)&&/world_cell_grass|world_cell_flower/.test(mesh.name)))continue;
			hidden.set(mesh,mesh.isEnabled(false));mesh.setEnabled(false);
		}
	};
	const restoreLegacy=()=>{for(const [mesh,was] of hidden)if(!mesh.isDisposed())mesh.setEnabled(was);hidden.clear();};
	const applyProfile=(profile:ResolvedGraphicsPreset)=>{
		if(disposed)return;
		state.tier=resolveGrassTier(profile);state.atlas=textures[state.tier.atlas==='half'?1:0];
		for(const m of materials)m.albedoTexture=state.atlas;
		for(const p of patches)p.mesh.receiveShadows=['high','ultra','epic'].includes(state.tier.preset);
		if(!state.tier.enabled)restoreLegacy();else adoptTerrainCells(scene.meshes);lodElapsed=1;
	};
	const refreshLod=(dt:number)=>{
		const camera=scene.activeCamera;if(!camera)return;
		const e=camera.globalPosition,eye=[e.x,e.y,e.z];
		const radius=(camera as unknown as {radius?:number}).radius??13;
		state.bands=scaleBands(grassBands(state.tier,radius),governor.factor);
		for(const p of patches)p.distance=aabbDistance(eye,p.packed.bounds!);
		patches.sort((a,b)=>a.distance-b.distance||a.kind-b.kind);
		const cap=state.tier.mobile?2000:({low:0,medium:3000,high:7000,ultra:12000,epic:15000}[state.tier.preset]??7000);
		const drawCap=state.tier.mobile?10:({low:0,medium:16,high:24,ultra:32,epic:36}[state.tier.preset]??24);
		let requested=0;submitted=0;draws=0;
		const cellLimit=state.tier.mobile?40000:120000,baseCosts=new Map<string,number>(),grassCosts=new Map<string,number>();
		if(blueprintEnabled){const relevant=new Set(patches.flatMap(p=>p.cells));const active=scene.getActiveMeshes();const observed=active.length?active.data.slice(0,active.length):scene.meshes;for(let i=0;i<observed.length;i++){const mesh=observed[i];if(!mesh||mesh.isDisposed()||!mesh.isEnabled()||!mesh.isVisible||mesh.name.startsWith('env-grass-')||mesh.getTotalVertices()===0||mesh instanceof Mesh&&mesh.infiniteDistance)continue;const bounds=mesh.getBoundingInfo().boundingBox;const triangles=(mesh.subMeshes??[]).reduce((sum,s)=>sum+s.indexCount/3,0)*Math.max(1,mesh instanceof Mesh?mesh.thinInstanceCount:0);for(const cell of cellKeys(bounds.minimumWorld.asArray(),bounds.maximumWorld.asArray()))if(relevant.has(cell))baseCosts.set(cell,(baseCosts.get(cell)??0)+triangles);}}
		for(const p of patches){
			if(scene.frustumPlanes?.length===6&&!p.mesh.isInFrustum(scene.frustumPlanes)){p.mesh.setEnabled(false);continue;}
			const b=p.kind?scaleBands(state.bands,state.tier.plantDistance):state.bands;
			const n=state.tier.enabled&&(p.kind===0||state.tier.plants)?lowerBound(p.packed.r,prefixFraction(p.distance,b)):0;
			requested+=n;let count=draws>=drawCap?0:Math.min(n,Math.max(0,cap-submitted));
			if(blueprintEnabled){const tris=geometry[p.kind].triangleCount;for(const cell of p.cells)count=Math.min(count,grassCellAllowance(baseCosts.get(cell)??0,grassCosts.get(cell)??0,tris,cellLimit));for(const cell of p.cells)grassCosts.set(cell,(grassCosts.get(cell)??0)+count*tris);}
			if(count>0){p.mesh.thinInstanceCount=count;p.mesh.setEnabled(ready&&!reviewHidden);submitted+=count;draws++;}else p.mesh.setEnabled(false);
		}
		governor=governGrass(governor,requested,cap,dt);
		cellBudgetReadback=blueprintEnabled?[...new Set([...baseCosts.keys(),...grassCosts.keys()])].map(cell=>({cell,baseTriangles:baseCosts.get(cell)??0,grassTriangles:grassCosts.get(cell)??0,limit:cellLimit})):[];
	};
	const observer=scene.onBeforeRenderObservable.add(()=>{
		if(disposed||!ready)return;const start=performance.now();
		const profile=options.profile();if(profile.preset!==state.tier.preset||profile.formFactor==='mobile'!==state.tier.mobile)applyProfile(profile);
		const weather=readWeatherFrame(scene);state.phase=weather?.phase??options.natureClock.phase;state.wind=weather?.appearance.windStrength??options.natureClock.strength??1;state.day=weather?.appearance.daylight??1;
		for(const m of materials){m.roughness=options.terrainMaterial.roughness;m.directIntensity=options.terrainMaterial.directIntensity;}
		const dt=Math.min(.1,scene.getEngine().getDeltaTime()/1000);lodElapsed+=dt;
		if(lodElapsed>=.25){refreshLod(lodElapsed);lodElapsed=0;}
		cpuLastMs=performance.now()-start;
	});
	const controller:GrassFieldController={
		ready:Promise.resolve(),applyProfile,adoptTerrainCells,
		diagnostics:()=>({ready,error,generated,submitted:reviewHidden?0:submitted,draws:reviewHidden?0:draws,activeDraws:scene.getActiveMeshes().data.slice(0,scene.getActiveMeshes().length).filter(m=>m?.name.startsWith('env-grass-')&&!m.name.includes('master')).length,patches:patches.length,tier:state.tier.preset,mobile:state.tier.mobile,governorFactor:governor.factor,clockPhase:state.phase,clockRevision:readWeatherFrame(scene)?.clockRevision??null,vertexBuffers:8,shadowDraws:0,glowDraws:0,bufferBytes:patches.reduce((sum,p)=>sum+p.packed.matrices.byteLength+p.packed.data.byteLength,0),cpuLastMs,rulesHash:stableHash(rulesData),blueprintEnabled,blueprint:rulesData.blueprint??null,fanCount:geometry[0].fanCount,trianglesPerTuft:geometry[0].triangleCount,cellBudgetMode:blueprintEnabled?'conservative-active-bounds-64m':null,cellBudgets:cellBudgetReadback,cellBudgetBlocked:cellBudgetReadback.filter(c=>c.baseTriangles>=c.limit).length,atlas:`${state.tier.atlas}-ktx2`,legacyHidden:hidden.size,hiddenForCost:reviewHidden}),
		dispose(){if(disposed)return;disposed=true;scene.onBeforeRenderObservable.remove(observer);if(disposeObserver)scene.onDisposeObservable.remove(disposeObserver);restoreLegacy();for(const p of patches){options.glow?.removeExcludedMesh(p.mesh);p.mesh.dispose();}for(const m of masters)m.dispose();for(const m of materials)m.dispose();for(const t of textures)t.dispose();fields.delete(scene);if(scene.metadata)delete scene.metadata.grassField;}
	};
	const build=async()=>{
		await Promise.all(textureReady);
		const range=patchRange(rules.domain);
		for(let j=range.j0;j<=range.j1;j++)for(let i=range.i0;i<=range.i1;i++){
			if(disposed)return;add(generateTuftPatch(rules,i,j),0,`${i}-${j}`);await new Promise<void>(resolve=>setTimeout(resolve,0));
		}
		const plants=patchRange(rules.domain,32);
		for(let j=plants.j0;j<=plants.j1;j++)for(let i=plants.i0;i<=plants.i1;i++){if(disposed)return;const list=generatePlantBlock(rules,i,j);add(list.flowers,1,`${i}-${j}`);add(list.clover,2,`${i}-${j}`);await new Promise<void>(resolve=>setTimeout(resolve,0));}
		for(const kind of [0,1,2]){const mesh=patches.find(p=>p.kind===kind)?.mesh;if(mesh)await Promise.race([materials[kind===0?0:1].forceCompilationAsync(mesh,{useInstances:true}),new Promise<never>((_,reject)=>setTimeout(()=>reject(new Error(`Grass prewarm timed out for layer ${kind}`)),12000))]);}
		if(disposed)return;ready=true;applyProfile(options.profile());adoptTerrainCells(scene.meshes);refreshLod(.25);
	};
	Object.defineProperty(controller,'ready',{value:build().catch(e=>{error=String(e);controller.dispose();throw e;})});
	fields.set(scene,controller);scene.metadata??={};Object.defineProperty(scene.metadata,'grassField',{configurable:true,get:()=>controller.diagnostics()});disposeObserver=scene.onDisposeObservable.addOnce(()=>controller.dispose());return controller;
}
