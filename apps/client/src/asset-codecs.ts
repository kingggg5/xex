import { KhronosTextureContainer2 } from "@babylonjs/core/Misc/khronosTextureContainer2";
import { MeshoptCompression } from "@babylonjs/core/Meshes/Compression/meshoptCompression";
import { AutoReleaseWorkerPool } from "@babylonjs/core/Misc/workerPool";
import {Tools} from '@babylonjs/core/Misc/tools';
import ktx2WorkerUrl from "./assets/codecs/ktx2decoder.worker.js?url&no-inline";
import mscTranscoderScriptUrl from "@babylonjs/ktx2decoder/wasm/msc_basis_transcoder.js?url&no-inline";
import mscTranscoderWasmUrl from "@babylonjs/ktx2decoder/wasm/msc_basis_transcoder.wasm?url&no-inline";
import astcUrl from "@babylonjs/ktx2decoder/wasm/uastc_astc.wasm?url&no-inline";
import bc7Url from "@babylonjs/ktx2decoder/wasm/uastc_bc7.wasm?url&no-inline";
import rgbaUnormUrl from "@babylonjs/ktx2decoder/wasm/uastc_rgba8_unorm_v2.wasm?url&no-inline";
import rgbaSrgbUrl from "@babylonjs/ktx2decoder/wasm/uastc_rgba8_srgb_v2.wasm?url&no-inline";
import r8Url from "@babylonjs/ktx2decoder/wasm/uastc_r8_unorm.wasm?url&no-inline";
import rg8Url from "@babylonjs/ktx2decoder/wasm/uastc_rg8_unorm.wasm?url&no-inline";
import zstdUrl from "@babylonjs/ktx2decoder/wasm/zstddec.wasm?url&no-inline";
import meshoptRegisterScriptUrl from "./assets/codecs/meshopt-register.js?url&no-inline";
import glslangJsUrl from '@babylonjs/core/assets/glslang/glslang.js?url&no-inline';
import glslangWasmUrl from '@babylonjs/core/assets/glslang/glslang.wasm?url&no-inline';
import twgslJsUrl from '@babylonjs/core/assets/twgsl/twgsl.js?url&no-inline';
import twgslWasmUrl from '@babylonjs/core/assets/twgsl/twgsl.wasm?url&no-inline';
import { resolveCodecUrlManifest } from "./codec-url-manifest.mjs";
import {guardAssetUrlHook,classifyKtx2Result,resolveWebGpuCompilerUrls,type Ktx2Diagnosis} from './asset-network-policy.mjs';

let configuration: Promise<void> | undefined;
let guardsInstalled=false;
const codecDiagnostics={decoded:0,rgbaFallbacks:0,blockedCdnRequests:0,recent:[] as Readonly<Ktx2Diagnosis>[]};
export function getAssetCodecDiagnostics(){return {...codecDiagnostics,recent:codecDiagnostics.recent.slice(),guardScope:'Babylon file/script hooks and local KTX2 worker fetch/importScripts',networkCaptureVerified:false as const};}
function blockedCdn(){
	if(codecDiagnostics.blockedCdnRequests++<8)console.error('[asset-cdn-blocked] Unexpected remote decoder/shader request was blocked.');
}
export function installAssetNetworkGuards():void {
	if(guardsInstalled)return;guardsInstalled=true;
	Tools.PreprocessUrl=guardAssetUrlHook(Tools.PreprocessUrl,window.location.href,blockedCdn);
	Tools.ScriptPreprocessUrl=guardAssetUrlHook(Tools.ScriptPreprocessUrl,window.location.href,blockedCdn);
}
export function getWebGpuCompilerOptions(baseHref=window.location.href){
	return resolveWebGpuCompilerUrls({glslangJs:glslangJsUrl,glslangWasm:glslangWasmUrl,twgslJs:twgslJsUrl,twgslWasm:twgslWasmUrl},baseHref);
}
export function getAssetCodecUrls(baseHref=window.location.href){
	return resolveCodecUrlManifest({wasmUASTCToASTC:astcUrl,wasmUASTCToBC7:bc7Url,wasmUASTCToRGBA_UNORM:rgbaUnormUrl,wasmUASTCToRGBA_SRGB:rgbaSrgbUrl,wasmUASTCToR8_UNORM:r8Url,wasmUASTCToRG8_UNORM:rg8Url,jsMSCTranscoder:mscTranscoderScriptUrl,wasmMSCTranscoder:mscTranscoderWasmUrl,wasmZSTDDecoder:zstdUrl},baseHref);
}

/** Configure same-origin, build-hashed decoders before the first glTF import. */
export function configureAssetCodecs(): Promise<void> {
	if (!configuration) {
		installAssetNetworkGuards();
		MeshoptCompression.Configuration = { decoder: { url: meshoptRegisterScriptUrl } };
		// The module itself is bundled into the worker; every lazily requested binary is local.
		Object.assign(KhronosTextureContainer2.URLConfig,getAssetCodecUrls());
		const hardwareConcurrency = typeof navigator === "undefined" ? 2 : navigator.hardwareConcurrency || 2;
		const workerCount = Math.max(1, Math.min(2, Math.floor(hardwareConcurrency / 2)));
		KhronosTextureContainer2.WorkerPool = new AutoReleaseWorkerPool(
			workerCount,
			createKtx2DecoderWorkerAsync,
		);
		configuration = import("meshoptimizer/decoder").then(async ({ MeshoptDecoder }) => {
			(globalThis as typeof globalThis & { MeshoptDecoder: typeof MeshoptDecoder }).MeshoptDecoder = MeshoptDecoder;
			await MeshoptDecoder.ready;
		});
	}
	return configuration;
}

async function createKtx2DecoderWorkerAsync(): Promise<Worker> {
	const workerUrl = new URL(ktx2WorkerUrl, window.location.href);
	const urls=getAssetCodecUrls();
	const worker = new Worker(workerUrl);
	worker.addEventListener('message',event=>{
		if(event.data?.action==='codec-diagnostic' && event.data.kind==='cdn-blocked'){blockedCdn();return;}
		if(event.data?.action!=='decoded' || !event.data.success)return;
		const diagnosis=classifyKtx2Result(event.data.decodedData);if(!diagnosis)return;
		codecDiagnostics.decoded++;codecDiagnostics.recent.push(diagnosis);if(codecDiagnostics.recent.length>16)codecDiagnostics.recent.shift();
		if(diagnosis.rgbaFallback && codecDiagnostics.rgbaFallbacks++<8)console.warn('[ktx2-rgba-fallback]',diagnosis);
	});
	try {
		await new Promise<void>((resolve, reject) => {
			const timeout = window.setTimeout(() => finish(new Error("Timed out initializing the local KTX2 decoder worker.")), 15000);
			const cleanup = () => {
				window.clearTimeout(timeout);
				worker.removeEventListener("message", onMessage);
				worker.removeEventListener("error", onError);
			};
			const finish = (error?: Error) => {
				cleanup();
				if (error) reject(error);
				else resolve();
			};
			const onMessage = (event: MessageEvent<{ action?: string }>) => {
				if (event.data?.action === "init") finish();
			};
			const onError = (event: ErrorEvent) => finish(new Error(event.message || "KTX2 decoder worker failed to initialize."));
			worker.addEventListener("message", onMessage);
			worker.addEventListener("error", onError);
			worker.postMessage({ action: "init",urls });
		});
		return worker;
	} catch (error) {
		worker.terminate();
		throw error;
	}
}
