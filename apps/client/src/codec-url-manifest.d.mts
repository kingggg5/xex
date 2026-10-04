export const KTX2_ASSET_KEYS:readonly ['wasmUASTCToASTC','wasmUASTCToBC7','wasmUASTCToRGBA_UNORM','wasmUASTCToRGBA_SRGB','wasmUASTCToR8_UNORM','wasmUASTCToRG8_UNORM','jsMSCTranscoder','wasmMSCTranscoder','wasmZSTDDecoder'];
export type LocalKtx2Urls=Readonly<Record<typeof KTX2_ASSET_KEYS[number],string>>;
export function resolveCodecUrlManifest(input:unknown,baseHref:string):LocalKtx2Urls;
