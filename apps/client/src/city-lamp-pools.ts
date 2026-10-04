import type { Scene } from '@babylonjs/core/scene';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder';
import '@babylonjs/core/Meshes/thinInstanceMesh';
import { RawTexture } from '@babylonjs/core/Materials/Textures/rawTexture';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';
import { Color3 } from '@babylonjs/core/Maths/math.color';
import { Constants } from '@babylonjs/core/Engines/constants';
import { readWeatherFrame } from './ambient-weather-channel';
import { poolStrength } from './look-grade-v2.mjs';
import { createLookV2PoolPixels, writeLookV2PoolMatrices, type LookV2PoolAnchor } from './look-v2-pools.mjs';

/** R5 vegetation.py: twelve crystal lamps at radius24, angle i*tau/12+pi/12.
 * Only the unchanged R5 layout (including guardian/material candidates) uses this.
 * The merged material mesh loses individual emitter names, so register the authored
 * footprints once instead of treating the entire city's bounds as one lamp.
 */
export function createCityLampPools(scene: Scene, centerZ: number,
	groundAt: (x:number,z:number)=>number|null,
	readAppearance = () => readWeatherFrame(scene)?.appearance ?? null) {
	const anchors: LookV2PoolAnchor[] = [];
	for(let index=0;index<12;index++) {
		const angle=index*Math.PI/6+Math.PI/12,x=24*Math.cos(angle),z=centerZ+24*Math.sin(angle);
		const samples=[groundAt(x,z), ...Array.from({length:8},(_,i)=>groundAt(x+4.5*Math.cos(i*Math.PI/4),z+4.5*Math.sin(i*Math.PI/4)))];
		if(samples.some(y=>y===null||!Number.isFinite(y)))continue;
		const heights=samples as number[],min=Math.min(...heights),max=Math.max(...heights);
		if(max-min>.25)continue; // Do not float a light card across stairs or unsupported water.
		anchors.push({x,y:max,z,type:'lamp'});
	}
	const pool=MeshBuilder.CreateGround('city-crystal-lamp-pools',{width:1,height:1},scene);
	pool.isPickable=false;pool.receiveShadows=false;
	pool.metadata={glow:false,lookV2Pool:false,cityLampPools:true,source:'R5 authored twelve-lamp ring',anchors};
	const texture=RawTexture.CreateRGBATexture(createLookV2PoolPixels(),64,64,scene,true,false);
	texture.hasAlpha=true;texture.gammaSpace=false;
	const material=new StandardMaterial('city-crystal-lamp-pool-material',scene);
	material.disableLighting=true;material.diffuseColor=Color3.Black();material.specularColor=Color3.Black();
	material.emissiveColor=new Color3(.24,.48,.62);material.opacityTexture=texture;
	material.alphaMode=Constants.ALPHA_ADD;material.disableDepthWrite=true;material.zOffset=-2;
	pool.material=material;
	const matrices=new Float32Array(anchors.length*16);
	writeLookV2PoolMatrices(anchors,matrices);
	if(anchors.length){pool.thinInstanceSetBuffer('matrix',matrices,16,true);pool.thinInstanceCount=anchors.length;pool.thinInstanceRefreshBoundingInfo(false);}
	let nextUpdate=0,disposed=false,revealed=false;
	const update=()=>{
		if(performance.now()<nextUpdate)return;nextUpdate=performance.now()+200;
		const appearance=readAppearance();
		const strength=appearance?poolStrength(appearance.daylight,appearance.rain):0;
		material.alpha=.52*strength;pool.setEnabled(revealed&&anchors.length>0&&strength>.01);
	};
	update();const observer=scene.onBeforeRenderObservable.add(update);
	let cancelReady:(()=>void)|null=null;
	const ready=anchors.length===0?Promise.resolve():new Promise<void>((resolve,reject)=>{
		const deadline=performance.now()+8000;let timer:ReturnType<typeof setTimeout>|undefined,finished=false;
		const finish=(error?:Error)=>{if(finished)return;finished=true;clearTimeout(timer);cancelReady=null;error?reject(error):resolve();};
		cancelReady=()=>finish(new Error('City lamp pool prewarm disposed'));
		const check=()=>{try{
			if(disposed||scene.isDisposed){cancelReady?.();return;}
			if(material.isReadyForSubMesh(pool,pool.subMeshes[0],true)){finish();return;}
			if(performance.now()>=deadline){finish(new Error('City lamp pool prewarm timed out'));return;}
			timer=setTimeout(check,16);
		}catch(error){finish(error instanceof Error?error:new Error('City lamp shader failed'));}};
		check();
	});
	const dispose=()=>{if(disposed)return;disposed=true;cancelReady?.();scene.onBeforeRenderObservable.remove(observer);scene.onDisposeObservable.remove(disposal);pool.dispose(false,false);material.dispose(false,false);texture.dispose();};
	const disposal=scene.onDisposeObservable.addOnce(dispose);
	return {anchors,mesh:pool,ready,reveal(){if(!disposed){revealed=true;nextUpdate=0;update();}},dispose};
}
