import type {Scene} from '@babylonjs/core/scene';
import type {Mesh} from '@babylonjs/core/Meshes/mesh';
import type {BaseTexture} from '@babylonjs/core/Materials/Textures/baseTexture';
import type {Texture} from '@babylonjs/core/Materials/Textures/texture';
import type {Observer} from '@babylonjs/core/Misc/observable';
import {geometryReleaseBlocker,textureReleaseBlocker,referencedBytes} from './asset-cache-policy.mjs';

export interface CpuCacheReceipt {
	kind:'texture'|'geometry';released:number;skipped:Record<string,number>;estimatedFreedBytes:number;
	estimateKind:'referenced-source-upper-bound';actualMemoryMeasured:false;
}
function receipt(kind:CpuCacheReceipt['kind']):CpuCacheReceipt{return {kind,released:0,skipped:{},estimatedFreedBytes:0,estimateKind:'referenced-source-upper-bound',actualMemoryMeasured:false};}
const clearedGeometry=new WeakSet<object>();

/** Same operation as scene.cleanCachedTextureBuffer(), restricted to ready binary file textures. */
export function releaseReadyFileTextureBuffers(textures:readonly BaseTexture[]):CpuCacheReceipt {
	const result=receipt('texture'),sources:unknown[]=[];
	for(const base of textures){
		const reason=textureReleaseBlocker(base);
		if(reason){result.skipped[reason]=(result.skipped[reason]??0)+1;continue;}
		const texture=base as Texture;sources.push(texture._buffer);texture._buffer=null;result.released++;
	}
	result.estimatedFreedBytes=referencedBytes(sources);
	return result;
}

/** Call only AFTER loading/upload/shader preparation. Future lazy file textures are checked at onLoad. */
export function installReadyTextureCacheRelease(scene:Scene):()=>void {
	const pending=new Map<Texture,Observer<Texture>|null>();let disposed=false;
	const countedSources=new WeakSet<object>();
	let reports=0;
	const report=(value:CpuCacheReceipt)=>{if(value.released && reports++<16)console.info('[cpu-cache-release-estimate]',value);};
	const release=(textures:readonly BaseTexture[])=>{
		const newSources:unknown[]=[];
		for(const base of textures){
			if(textureReleaseBlocker(base))continue;
			const source=(base as Texture)._buffer as ArrayBuffer|ArrayBufferView;
			const backing=ArrayBuffer.isView(source)?source.buffer:source;
			if(!countedSources.has(backing)){countedSources.add(backing);newSources.push(backing);}
		}
		const result=releaseReadyFileTextureBuffers(textures);
		// Lazy textures may all share the same GLB. Do not add its entire backing size per texture.
		result.estimatedFreedBytes=referencedBytes(newSources);report(result);
	};
	const inspect=(base:BaseTexture)=>{
		if(disposed)return;
		if(base.getClassName()!=='Texture')return;
		const texture=base as Texture;
		if(texture.isReady()){release([texture]);return;}
		if(pending.has(texture))return;
		if(!texture.onLoadObservable)return;
		const load=texture.onLoadObservable.addOnce(()=>{
			pending.delete(texture);if(!disposed)release([texture]);
		});
		pending.set(texture,load);
		texture.onDisposeObservable.addOnce(()=>{texture.onLoadObservable.remove(load);pending.delete(texture);});
	};
	// The initial aggregate counts each GLB backing store once, even if many texture views refer to it.
	release(scene.textures);
	for(const texture of scene.textures)if(!texture.isReady())inspect(texture);
	// BaseTexture announces itself before Texture's own fields initialize.
	const newTexture=scene.onNewTextureAddedObservable.add(texture=>queueMicrotask(()=>inspect(texture)));
	const dispose=()=>{
		if(disposed)return;disposed=true;scene.onNewTextureAddedObservable.remove(newTexture);
		for(const [texture,observer] of pending)texture.onLoadObservable.remove(observer);pending.clear();
	};
	scene.onDisposeObservable.addOnce(dispose);return dispose;
}

/** Geometry remains untouched by default. Owner certifies no future CPU read/merge/clone/update. */
export function releasePreparedStaticGeometry(scene:Scene,auditedMeshes:readonly Mesh[]):CpuCacheReceipt {
	const result=receipt('geometry');
	if(!scene.getEngine().doNotHandleContextLost){result.skipped['restoration-enabled']=auditedMeshes.length;return result;}
	const admitted=new Set(auditedMeshes),seen=new Set(),sources:unknown[]=[];
	for(const mesh of auditedMeshes){
		const geometry=mesh.geometry;if(!geometry || seen.has(geometry))continue;seen.add(geometry);
		if(clearedGeometry.has(geometry)){result.skipped['already-released']=(result.skipped['already-released']??0)+1;continue;}
		// Include ALL sharing meshes, including instances' sources. One picker/actor protects the whole buffer.
		const sharing=geometry.meshes;
		const reasons=sharing.map(owner=>geometryReleaseBlocker(owner,admitted.has(owner)));
		const reason=reasons.find(value=>value!==null)??(sharing.length?'':'no-owner');
		if(reason){result.skipped[reason]=(result.skipped[reason]??0)+1;continue;}
		for(const owner of sharing)owner.computeWorldMatrix(true); // Preserve already-derived bounds.
		sources.push(geometry.getIndices());
		for(const buffer of Object.values(geometry.getVertexBuffers()??{}))sources.push(buffer.getData());
		geometry.clearCachedData();clearedGeometry.add(geometry);result.released++;
	}
	result.estimatedFreedBytes=referencedBytes(sources);
	if(result.released || Object.keys(result.skipped).length)console.info('[cpu-cache-release-estimate]',result);
	return result;
}
