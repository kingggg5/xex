export const KTX2_ASSET_KEYS=Object.freeze(['wasmUASTCToASTC','wasmUASTCToBC7','wasmUASTCToRGBA_UNORM','wasmUASTCToRGBA_SRGB','wasmUASTCToR8_UNORM','wasmUASTCToRG8_UNORM','jsMSCTranscoder','wasmMSCTranscoder','wasmZSTDDecoder']);
/** Resolve before postMessage: relative asset paths must never inherit the worker asset directory. */
export function resolveCodecUrlManifest(input,baseHref){
	const base=new URL(baseHref);
	if(!['http:','https:'].includes(base.protocol))throw new Error('Local decoder assets require an HTTP(S) origin.');
	const urls={};
	for(const key of KTX2_ASSET_KEYS){
		if(typeof input?.[key]!=='string'||!input[key])throw new Error(`Missing local decoder asset: ${key}`);
		const value=new URL(input[key],base);
		const extension=key==='jsMSCTranscoder'?'.js':'.wasm';
		if(value.origin!==base.origin||value.username||value.password||!value.pathname.endsWith(extension))throw new Error(`Decoder asset must be same-origin ${extension}: ${key}`);
		urls[key]=value.href;
	}
	return Object.freeze(urls);
}
