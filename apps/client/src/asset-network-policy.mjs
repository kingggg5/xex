/** Guard the actual resolved destination, including URL rewrites. No query/path is logged. */
export function assertNoBabylonCdn(value,baseHref){
	const url=new URL(value,baseHref);
	if(url.hostname.toLowerCase()==='cdn.babylonjs.com'){
		const error=new Error('Blocked unexpected Babylon CDN request. A local decoder/shader asset is required.');
		error.name='UnexpectedBabylonCdnError';throw error;
	}
	return value;
}

/** Scope is the supplied Babylon URL hook, NOT every browser/network request. */
export function guardAssetUrlHook(previous,baseHref,onBlocked){
	return value=>{
		try{assertNoBabylonCdn(value,baseHref);const resolved=previous(value);assertNoBabylonCdn(resolved,baseHref);return resolved;}
		catch(error){if(error?.name==='UnexpectedBabylonCdnError')onBlocked?.();throw error;}
	};
}

/** Primitive diagnosis from Babylon's actual worker response; no mipmap copies or source pixels. */
export function classifyKtx2Result(decoded){
	if(!decoded || decoded.errors || !Number.isSafeInteger(decoded.transcodedFormat))return null;
	const name=typeof decoded.transcoderName==='string'?decoded.transcoderName.slice(0,96):'unknown';
	const rgba=decoded.transcodedFormat===32856;
	return Object.freeze({format:decoded.transcodedFormat,transcoder:name,
		width:Number.isSafeInteger(decoded.width)?decoded.width:null,height:Number.isSafeInteger(decoded.height)?decoded.height:null,
		uncompressedRgba:rgba,rgbaFallback:rgba&&name!=='UncompressedRGBA32Transcoder',
		// R8/RG8 may deliberately be uncompressed data textures; do not label them RGBA fallback.
	});
}

export function resolveWebGpuCompilerUrls(input,baseHref){
	const base=new URL(baseHref),out={};
	if(!['http:','https:'].includes(base.protocol))throw new Error('Shader compilers require a local HTTP(S) origin.');
	for(const key of ['glslangJs','glslangWasm','twgslJs','twgslWasm']){
		if(typeof input?.[key]!=='string')throw new Error(`Missing local shader compiler: ${key}`);
		const url=new URL(input[key],base),extension=key.endsWith('Js')?'.js':'.wasm';
		if(url.origin!==base.origin || url.username || url.password || !url.pathname.endsWith(extension))throw new Error(`Shader compiler must be same-origin ${extension}: ${key}`);
		out[key]=url.href;
	}
	return {glslangOptions:{jsPath:out.glslangJs,wasmPath:out.glslangWasm},twgslOptions:{jsPath:out.twgslJs,wasmPath:out.twgslWasm}};
}
