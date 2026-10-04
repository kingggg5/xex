import test from 'node:test';
import assert from 'node:assert/strict';
import {SELECTED_FAMILIES,parseGlb,writeGlb,spliceSelected,verifySplice} from './pack-guardian-selected-forge.mjs';

function ktx(role,marker) {
 const b=Buffer.alloc(96,marker);Buffer.from([0xab,0x4b,0x54,0x58,0x20,0x32,0x30,0xbb,0x0d,0x0a,0x1a,0x0a]).copy(b);
 b.writeUInt32LE(1024,20);b.writeUInt32LE(1024,24);b.writeUInt32LE(11,40);b.writeUInt32LE(64,48);b[76]=role==='albedo'?163:166;b[78]=role==='albedo'?2:1;return b;
}
function fixture(marker) {
 const images=[],bufferViews=[],textures=[],materials=[],pieces=[];let offset=0;
 for(const name of SELECTED_FAMILIES){const ids={};for(const role of ['albedo','normal','orm']){const i=images.length,b=ktx(role,marker);ids[role]=i;images.push({name:`${name}_${role}`,mimeType:'image/ktx2',bufferView:i});bufferViews.push({buffer:0,byteOffset:offset,byteLength:b.length});textures.push({extensions:{KHR_texture_basisu:{source:i}}});pieces.push(b);offset+=b.length;}materials.push({name,pbrMetallicRoughness:{baseColorTexture:{index:ids.albedo,extensions:{KHR_texture_transform:{scale:[2,3]}}},metallicRoughnessTexture:{index:ids.orm},baseColorFactor:[.5,.6,.7,1]},normalTexture:{index:ids.normal,scale:.4},occlusionTexture:{index:ids.orm}});}
 while(images.length<54){const i=images.length,b=Buffer.alloc(96,i);images.push({name:`untouched_${i}`,mimeType:'image/ktx2',bufferView:i});bufferViews.push({buffer:0,byteOffset:offset,byteLength:b.length});textures.push({extensions:{KHR_texture_basisu:{source:i}}});pieces.push(b);offset+=b.length;}
 const tail=Buffer.from([1,2,3,4,5,6,7,8]);bufferViews.push({buffer:1,byteOffset:0,byteLength:12,extensions:{EXT_meshopt_compression:{buffer:0,byteOffset:offset,byteLength:tail.length,count:1,byteStride:12,mode:'ATTRIBUTES'}}});pieces.push(tail);
 const json={asset:{version:'2.0'},images,textures,materials,bufferViews,buffers:[{byteLength:offset+tail.length},{byteLength:12,extensions:{EXT_meshopt_compression:{fallback:true}}}],accessors:[{bufferView:54,count:1,type:'VEC3',componentType:5126}],meshes:[],nodes:[],samplers:[{wrapS:10497,wrapT:10497}]};
 return parseGlb(writeGlb(json,Buffer.concat(pieces)));
}
test('exact fifteen payload replacement preserves UV factors and untouched bytes despite material reordering',()=>{
 const donor=fixture(8),forge=fixture(9);forge.json.materials.reverse();
 const before=JSON.stringify(donor.json),result=spliceSelected(donor,forge),candidate=parseGlb(result.bytes);
 verifySplice(donor,candidate,result);assert.equal(result.images.filter(i=>i.changed).length,15);assert.equal(result.images.filter(i=>!i.changed&&i.donorSha256===i.outputSha256).length,39);assert.deepEqual(candidate.json.materials,donor.json.materials);assert.equal(JSON.stringify(donor.json),before);
});
test('changed compressed tail or material parameter is rejected',()=>{
 const donor=fixture(8),result=spliceSelected(donor,fixture(9)),candidate=parseGlb(result.bytes);
 candidate.bin[candidate.bin.length-1]^=1;assert.throws(()=>verifySplice(donor,candidate,result),/tail changed/);candidate.bin[candidate.bin.length-1]^=1;
 candidate.json.materials[0].normalTexture.scale=.8;assert.throws(()=>verifySplice(donor,candidate,result),/Non-image GLB metadata/);
});
test('shared target texture cannot silently modify another material family',()=>{
 const donor=fixture(8);donor.json.materials.push({name:'unrelated',normalTexture:{index:1}});
 assert.throws(()=>spliceSelected(donor,fixture(9)),/Unsafe shared/);
});
test('nonlinear ORM and mismatched image names fail before packing',()=>{
 const donor=fixture(8),forge=fixture(9),view=forge.json.bufferViews[2];forge.bin[view.byteOffset+78]=2;
 assert.throws(()=>spliceSelected(donor,forge),/role\/dimension\/mip/);
 const renamed=fixture(9);renamed.json.images[1].name='wrong';assert.throws(()=>spliceSelected(donor,renamed),/Image-name roster/);
});
