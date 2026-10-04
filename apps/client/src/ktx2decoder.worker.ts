import * as KTX2Decoder from "@babylonjs/ktx2decoder";
import { workerFunction } from "@babylonjs/core/Misc/khronosTextureContainer2Worker";
import { MSCTranscoder } from "@babylonjs/ktx2decoder/Transcoders/mscTranscoder";
import { resolveCodecUrlManifest } from "./codec-url-manifest.mjs";
import {assertNoBabylonCdn} from './asset-network-policy.mjs';

// Guard the decoder's actual network entry points, in addition to validating the nine-resource manifest.
const network=globalThis as typeof globalThis & {importScripts?:(...urls:string[])=>void};
const nativeFetch=network.fetch.bind(network);
const check=(url:string)=>{
	try{assertNoBabylonCdn(url,globalThis.location.href);}
	catch(error){globalThis.postMessage({action:'codec-diagnostic',kind:'cdn-blocked'});throw error;}
};
network.fetch=(input,init)=>{
	try{check(typeof input==='string'?input:input instanceof URL?input.href:input.url);}
	catch(error){return Promise.reject(error);}
	return nativeFetch(input,init);
};
if(network.importScripts){const nativeImportScripts=network.importScripts.bind(network);network.importScripts=(...urls)=>{urls.forEach(check);nativeImportScripts(...urls);};}

type DecoderWorkerGlobal = typeof globalThis & { KTX2DECODER: typeof KTX2Decoder };
(globalThis as DecoderWorkerGlobal).KTX2DECODER = KTX2Decoder;
MSCTranscoder.UseFromWorkerThread = true;
workerFunction(KTX2Decoder);
// Validate before Babylon applies its complete nine-resource config. Missing paths fail closed.
const handler=globalThis.onmessage as unknown as (event:MessageEvent)=>void;
globalThis.onmessage=(event:MessageEvent)=>{
	if(event.data?.action==="init")event.data.urls=resolveCodecUrlManifest(event.data.urls,globalThis.location.href);
	handler(event);
};
