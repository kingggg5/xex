import test from 'node:test';
import assert from 'node:assert/strict';
import {gunzipSync} from 'node:zlib';
import {compressAssetTransport} from '../scripts/prepare-asset-transport.mjs';

test('transport candidate round-trips source bytes/hash and labels savings as estimate, without touching delivery policy',()=>{
	const bytes=Buffer.from('test-material-data\0'.repeat(4096));
	const first=compressAssetTransport(bytes,'.glb'),second=compressAssetTransport(bytes,'.glb');
	assert.deepEqual(gunzipSync(first.compressed),bytes);assert.equal(first.receipt.sourceBytes,bytes.length);assert.ok(first.receipt.gzipBytes<bytes.length);
	assert.equal(first.receipt.gzipSha256,second.receipt.gzipSha256);assert.equal(first.receipt.actualTransferMeasured,false);assert.match(first.receipt.requires,/never both/);
});

test('transport candidate refuses KTX2, unknown extensions, empty input and nonbinary sources',()=>{
	for(const extension of ['.ktx2','.png','.js','.zip'])assert.throws(()=>compressAssetTransport(Buffer.from('data'),extension),/never recompress/);
	assert.throws(()=>compressAssetTransport(new Uint8Array(),'.hdr'));
	assert.throws(()=>compressAssetTransport('string','.glb'));
});
