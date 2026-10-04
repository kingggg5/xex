import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
/** Explicit build artifact only. Does NOT change loader URLs, HTTP headers, content or client codecs. */
export function compressAssetTransport(bytes,extension){
	if(!['.glb','.hdr'].includes(extension))throw new Error('Transport preparation admits only GLB/HDR; never recompress KTX2.');
	if(!(bytes instanceof Uint8Array) || bytes.byteLength===0 || bytes.byteLength>256*1024*1024)throw new Error('Asset must be 1 byte–256 MiB.');
	const compressed=gzipSync(bytes,{level:6});
	return {compressed,receipt:{schema:'xexoria-asset-gzip-candidate-v1',sourceSha256:hash(bytes),gzipSha256:hash(compressed),sourceBytes:bytes.byteLength,gzipBytes:compressed.byteLength,
		transferSavingsEstimate:1-compressed.byteLength/bytes.byteLength,actualTransferMeasured:false,requires:'Explicit .gz URL + DecompressionStream(gzip) OR server Content-Encoding:gzip, never both'}};
}

export async function prepareAssetTransport(input,outputDirectory){
	const source=path.resolve(input),directory=path.resolve(outputDirectory),info=await stat(source);
	if(!info.isFile() || info.size===0 || info.size>256*1024*1024)throw new Error('Input must be a regular asset file up to 256 MiB.');
	const extension=path.extname(source).toLowerCase();
	const {compressed,receipt}=compressAssetTransport(await readFile(source),extension);
	const filename=`${path.basename(source,extension)}.${receipt.gzipSha256.slice(0,16)}${extension}.gz`;
	await mkdir(directory,{recursive:true});
	const artifact=path.join(directory,filename),receiptPath=`${artifact}.json`;
	await writeFile(artifact,compressed,{flag:'wx'});
	await writeFile(receiptPath,JSON.stringify({...receipt,source,artifact},null,2)+'\n',{flag:'wx'});
	return {artifact,receiptPath,...receipt};
}

if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
	const [input,outputDirectory,...extra]=process.argv.slice(2);
	if(!input || !outputDirectory || extra.length)throw new Error('Usage: node prepare-asset-transport.mjs <asset.glb|asset.hdr> <candidate-output-directory>');
	console.log(JSON.stringify(await prepareAssetTransport(input,outputDirectory),null,2));
}
