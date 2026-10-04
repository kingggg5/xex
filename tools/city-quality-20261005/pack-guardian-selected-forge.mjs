/** Scoped texture reuse; never encodes, edits, admits or overwrites a donor. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const DONOR = 'assets/models/reference-city/r5/fountain-guardian-review-v2-candidate/city-runtime.meshopt.glb';
const FORGE = 'assets/models/reference-city/r5/forge-r6-texture-review-candidate/city-runtime.meshopt.glb';
const DONOR_SHA = '8e7668042f044ff175a2d2d3fc45cfedc1eb4fdd6c058be7150271d862d02f05';
const FORGE_SHA = '93910787c74e3655f40df4c8fb73630503d67e540d7fe98286febd0a1907fb61';
const DIRECTORY = 'assets/models/reference-city/r5/guardian-material-r03-candidate';
export const SELECTED_FAMILIES = Object.freeze(['stone_wall_warm', 'stone_foundation', 'stone_trim_carved', 'stone_accent_bluegrey', 'plaster_cream']);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v;
const exact = (a, b, label) => { if (JSON.stringify(canonical(a)) !== JSON.stringify(canonical(b))) throw new Error(`${label} changed`); };
const align4 = n => Math.ceil(n / 4) * 4;
const MEMORY_LIMIT = 1536 * 1024 * 1024;
let maxObservedRss = 0;
function memory(phase) {
 const rss = process.memoryUsage().rss;
 maxObservedRss = Math.max(maxObservedRss, rss);
 if (rss >= MEMORY_LIMIT) throw new Error(`Own-process RSS limit exceeded at ${phase}`);
}

export function parseGlb(bytes) {
 if (bytes.length < 28 || bytes.toString('ascii', 0, 4) !== 'glTF' || bytes.readUInt32LE(4) !== 2 || bytes.readUInt32LE(8) !== bytes.length || bytes.readUInt32LE(16) !== 0x4e4f534a) throw new Error('Invalid GLB header');
 const at = 20 + bytes.readUInt32LE(12);
 if (at + 8 > bytes.length || bytes.readUInt32LE(at + 4) !== 0x004e4942 || at + 8 + bytes.readUInt32LE(at) !== bytes.length) throw new Error('Unexpected GLB chunk layout');
 return { json: JSON.parse(bytes.subarray(20, at).toString('utf8').trim()), bin: bytes.subarray(at + 8) };
}
export function writeGlb(json, bin) {
 const text = Buffer.from(JSON.stringify(json)), jLength = align4(text.length), bLength = align4(bin.length);
 const bytes = Buffer.alloc(28 + jLength + bLength);
 bytes.write('glTF'); bytes.writeUInt32LE(2, 4); bytes.writeUInt32LE(bytes.length, 8);
 bytes.writeUInt32LE(jLength, 12); bytes.writeUInt32LE(0x4e4f534a, 16);
 bytes.fill(0x20, 20, 20 + jLength); text.copy(bytes, 20);
 const at = 20 + jLength; bytes.writeUInt32LE(bLength, at); bytes.writeUInt32LE(0x004e4942, at + 4); bin.copy(bytes, at + 8);
 return bytes;
}
function imageBytes(glb, index) {
 const image = glb.json.images[index], view = glb.json.bufferViews[image?.bufferView];
 const start = view?.byteOffset ?? 0;
 if (!view || image.mimeType !== 'image/ktx2' || view.buffer !== 0 || !Number.isInteger(view.byteLength) || start < 0 || start + view.byteLength > glb.bin.length) throw new Error('Expected bounded embedded KTX2 image');
 return glb.bin.subarray(start, start + view.byteLength);
}
function imageIndex(json, info) {
 const texture = json.textures?.[info?.index], i = texture?.extensions?.KHR_texture_basisu?.source ?? texture?.source;
 if (!Number.isInteger(info?.index) || !Number.isInteger(i) || !json.images[i]) throw new Error('Invalid material image binding');
 return i;
}
export function ktxInfo(bytes, role) {
 const signature = Buffer.from([0xab,0x4b,0x54,0x58,0x20,0x32,0x30,0xbb,0x0d,0x0a,0x1a,0x0a]);
 if (bytes.length < 80 || !bytes.subarray(0,12).equals(signature)) throw new Error('Invalid KTX2 signature');
 const dfd = bytes.readUInt32LE(48);
 if (dfd + 15 > bytes.length) throw new Error('Invalid KTX2 DFD range');
 const result = { width: bytes.readUInt32LE(20), height: bytes.readUInt32LE(24), levels: bytes.readUInt32LE(40), colorModel: bytes[dfd + 12], transfer: bytes[dfd + 14], supercompression: bytes.readUInt32LE(44) };
 if (result.width !== 1024 || result.height !== 1024 || result.levels !== 11 || result.transfer !== (role === 'albedo' ? 2 : 1) || result.colorModel !== (role === 'albedo' ? 163 : 166)) throw new Error(`KTX2 role/dimension/mip contract failed: ${role}`);
 return result;
}
function layout(glb) {
 const j = glb.json, images = j.images;
 if (!Array.isArray(images) || images.length !== 54 || j.buffers?.length !== 2 || !j.buffers[1].extensions?.EXT_meshopt_compression?.fallback) throw new Error('Unexpected donor image/physical/fallback buffer layout');
 if (new Set(images.map(i => i.name)).size !== 54 || new Set(images.map(i => i.bufferView)).size !== 54 || images.some((i, n) => i.bufferView !== n)) throw new Error('Expected unique54 image prefix and names');
 const compressed = j.bufferViews.map((v, i) => ({ v, i })).filter(({v}) => v.extensions?.EXT_meshopt_compression);
 if (!compressed.length || j.bufferViews.length !== compressed.length + 54) throw new Error('Unexpected non-image geometry view');
 const start = Math.min(...compressed.map(({v}) => v.extensions.EXT_meshopt_compression.byteOffset));
 for (let i = 0; i < images.length; i++) {
  const view = j.bufferViews[images[i].bufferView]; imageBytes(glb, i);
  if ((view.byteOffset ?? 0) + view.byteLength > start) throw new Error('Image overlaps geometry tail');
 }
 for (const {v} of compressed) {
  const e = v.extensions.EXT_meshopt_compression;
  if (v.buffer !== 1 || e.buffer !== 0 || !Number.isInteger(e.byteOffset) || e.byteOffset < start || e.byteOffset + e.byteLength > glb.bin.length || e.count * e.byteStride !== v.byteLength || (v.byteOffset ?? 0) + v.byteLength > j.buffers[1].byteLength) throw new Error('Invalid compressed geometry range');
 }
 return { start, compressed };
}
function materialSlots(j, name) {
 const matches = j.materials.filter(m => m.name === name);
 if (matches.length !== 1) throw new Error(`Ambiguous material ${name}`);
 const m = matches[0];
 const result = { albedo: imageIndex(j, m.pbrMetallicRoughness?.baseColorTexture), normal: imageIndex(j, m.normalTexture), orm: imageIndex(j, m.pbrMetallicRoughness?.metallicRoughnessTexture) };
 if (result.orm !== imageIndex(j, m.occlusionTexture)) throw new Error(`${name}: AO and roughness/metal must share ORM`);
 return result;
}
function owners(j) {
 const result = j.images.map(() => new Set());
 for (const m of j.materials) {
  function visit(v, key) {
   if (!v || typeof v !== 'object') return;
   if (Number.isInteger(v.index) && key.toLowerCase().endsWith('texture')) result[imageIndex(j,v)].add(m.name);
   for (const [k, child] of Object.entries(v)) if (child && typeof child === 'object') visit(child,k);
  }
  visit(m,'');
 }
 return result;
}

export function spliceSelected(donor, forge) {
 const donorLayout = layout(donor); layout(forge);
 exact(donor.json.images.map(i => i.name), forge.json.images.map(i => i.name), 'Image-name roster');
 const owner = owners(donor.json), forgeOwner = owners(forge.json), replacements = new Map();
 for (const name of SELECTED_FAMILIES) {
  const d = materialSlots(donor.json,name), f = materialSlots(forge.json,name);
  for (const role of ['albedo','normal','orm']) {
   const di = d[role], fi = f[role], expected = `${name}_${role}`;
   if (donor.json.images[di].name !== expected || forge.json.images[fi].name !== expected || replacements.has(di) || owner[di].size !== 1 || !owner[di].has(name) || forgeOwner[fi].size !== 1 || !forgeOwner[fi].has(name)) throw new Error(`Unsafe shared or mismatched image binding: ${expected}`);
   const bytes = imageBytes(forge,fi);
   replacements.set(di,{name,role,forgeImageIndex:fi,bytes,ktx:ktxInfo(bytes,role)});
  }
 }
 if (replacements.size !== 15) throw new Error('Expected exactly15 selected image payloads');
 const json = structuredClone(donor.json), pieces = [], images = []; let offset = 0;
 for (let i = 0; i < donor.json.images.length; i++) {
  const old = imageBytes(donor,i), replacement = replacements.get(i), bytes = replacement?.bytes ?? old;
  const view = json.bufferViews[json.images[i].bufferView]; view.byteOffset = offset; view.byteLength = bytes.length;
  pieces.push(bytes,Buffer.alloc(align4(bytes.length)-bytes.length)); offset += align4(bytes.length);
  images.push({index:i,name:json.images[i].name,changed:!!replacement,donorSha256:sha(old),outputSha256:sha(bytes),bytes:bytes.length,forgeImageIndex:replacement?.forgeImageIndex ?? null,role:replacement?.role ?? null,ktx:replacement?.ktx ?? null});
 }
 const newStart = offset, tail = donor.bin.subarray(donorLayout.start), delta = newStart - donorLayout.start;
 pieces.push(tail);
 for (const {i} of donorLayout.compressed) json.bufferViews[i].extensions.EXT_meshopt_compression.byteOffset += delta;
 const bin = Buffer.concat(pieces); json.buffers[0].byteLength = bin.length;
 return { bytes:writeGlb(json,bin),images,sourceTailOffset:donorLayout.start,outputTailOffset:newStart,delta };
}

export function verifySplice(donor, candidate, result) {
 const d = layout(donor), c = layout(candidate);
 if (c.start !== result.outputTailOffset || !donor.bin.subarray(d.start).equals(candidate.bin.subarray(c.start))) throw new Error('Immutable geometry tail changed');
 const normalized = structuredClone(candidate.json); normalized.buffers[0].byteLength = donor.json.buffers[0].byteLength;
 for (const image of donor.json.images) normalized.bufferViews[image.bufferView] = structuredClone(donor.json.bufferViews[image.bufferView]);
 for (const {i} of d.compressed) normalized.bufferViews[i].extensions.EXT_meshopt_compression.byteOffset -= result.delta;
 exact(donor.json,normalized,'Non-image GLB metadata (including materials/UVs/colours/nodes/hooks)');
 for (const row of result.images) if (sha(imageBytes(candidate,row.index)) !== row.outputSha256 || (!row.changed && row.outputSha256 !== row.donorSha256)) throw new Error(`Image readback changed ${row.name}`);
 for (const {v,i} of d.compressed) {
  const before = v.extensions.EXT_meshopt_compression, after = candidate.json.bufferViews[i].extensions.EXT_meshopt_compression;
  if (!donor.bin.subarray(before.byteOffset,before.byteOffset+before.byteLength).equals(candidate.bin.subarray(after.byteOffset,after.byteOffset+after.byteLength))) throw new Error(`Compressed geometry stream changed: ${i}`);
 }
 return d;
}
async function verifyDecoded(donor,candidate) {
 const require = createRequire(path.join(root,'apps/client/package.json'));
 const {MeshoptDecoder} = require('meshoptimizer'); await MeshoptDecoder.ready;
 const streams = layout(donor).compressed, rows = []; let decodedBytes = 0;
 for (const {v,i} of streams) {
  memory(`decode-before-${i}`);
  const a = v.extensions.EXT_meshopt_compression, b = candidate.json.bufferViews[i].extensions.EXT_meshopt_compression;
  const left = new Uint8Array(v.byteLength), right = new Uint8Array(v.byteLength);
  MeshoptDecoder.decodeGltfBuffer(left,a.count,a.byteStride,donor.bin.subarray(a.byteOffset,a.byteOffset+a.byteLength),a.mode,a.filter);
  MeshoptDecoder.decodeGltfBuffer(right,b.count,b.byteStride,candidate.bin.subarray(b.byteOffset,b.byteOffset+b.byteLength),b.mode,b.filter);
  const h = sha(left); if (h !== sha(right)) throw new Error(`Decoded geometry stream changed: ${i}`);
  rows.push({bufferView:i,bytes:left.byteLength,sha256:h}); decodedBytes += left.byteLength;
  memory(`decode-after-${i}`);
 }
 const proven = new Set(rows.map(r=>r.bufferView));
 if (donor.json.accessors.some(a => !proven.has(a.bufferView) || a.sparse)) throw new Error('Accessor not fully covered by decoded stream proof');
 return {streams:rows.length,decodedBytes,accessorsCovered:donor.json.accessors.length,roster:rows};
}

async function main() {
 const directory = path.join(root,DIRECTORY), output = path.join(directory,'city-runtime.meshopt.glb');
 try { if ((await fs.readdir(directory)).length) throw new Error('Candidate directory is not empty; preserve existing revision'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
 const realRoot = await fs.realpath(root), realParent = await fs.realpath(path.dirname(directory));
 if (!realParent.startsWith(realRoot+path.sep)) throw new Error('Candidate parent escapes repository');
 memory('start');
 const donorBytes = await fs.readFile(path.join(root,DONOR)), forgeBytes = await fs.readFile(path.join(root,FORGE));
 if (sha(donorBytes)!==DONOR_SHA || sha(forgeBytes)!==FORGE_SHA) throw new Error('Pinned immutable donor/Forge changed');
 const donor=parseGlb(donorBytes),forge=parseGlb(forgeBytes);memory('inputs');
 const forgeReceiptPath='assets/models/reference-city/r5/forge-r6-texture-review-candidate/runtime-pack-receipt.json';
 const forgeReceiptBytes=await fs.readFile(path.join(root,forgeReceiptPath)), forgeReceipt=JSON.parse(forgeReceiptBytes);
 if (forgeReceipt.output.sha256!==FORGE_SHA || forgeReceipt.status!=='PASS_STRUCTURAL_TEXTURE_ONLY_NATIVE_REVIEW_REQUIRED') throw new Error('Forge receipt mismatch');
 const preservedPaths=['apps/client/src/assets/models/env_reference_city.glb','assets/models/reference-city/r5/active-revision.json','content/source/zones.json','assets/models/reference-city/r5/market-repair-candidate/city-traversal-v1.json'];
 const preserved=[]; for(const p of preservedPaths)preserved.push({path:p,sha256:sha(await fs.readFile(path.join(root,p)))});
 const result=spliceSelected(donor,forge); memory('spliced');
 for(const row of result.images.filter(i=>i.changed))if(forgeReceipt.images.find(i=>i.name===row.name)?.outputSha256!==row.outputSha256)throw new Error(`Forge payload receipt mismatch: ${row.name}`);
 const candidate=parseGlb(result.bytes); verifySplice(donor,candidate,result); memory('verified-memory');
 const decoded=await verifyDecoded(donor,candidate);memory('decoded');
 const triangles=donor.json.meshes.reduce((total,m)=>total+m.primitives.reduce((sum,p)=>sum+donor.json.accessors[p.indices].count/3,0),0);
 if (triangles!==915073) throw new Error('Donor triangle identity changed');
 await fs.mkdir(directory,{recursive:true});await fs.writeFile(output,result.bytes,{flag:'wx'});
 const diskBytes=await fs.readFile(output);const disk=parseGlb(diskBytes);verifySplice(donor,disk,result);if(!diskBytes.equals(result.bytes))throw new Error('Packed disk readback differs');memory('disk-readback');
 if (sha(await fs.readFile(path.join(root,DONOR)))!==DONOR_SHA || sha(await fs.readFile(path.join(root,FORGE)))!==FORGE_SHA || sha(await fs.readFile(path.join(root,forgeReceiptPath)))!==sha(forgeReceiptBytes)) throw new Error('Immutable input changed during verification');
 for(const p of preserved)if(sha(await fs.readFile(path.join(root,p.path)))!==p.sha256)throw new Error(`Protected active input changed: ${p.path}`);
 memory('complete');
 const receipt={schema:'xexoria.guardian-selected-forge-candidate/1',status:'PASS_STRUCTURAL_REUSE_ONLY_NATIVE_REVIEW_REQUIRED',createdAt:new Date().toISOString(),
  donor:{path:DONOR,sha256:DONOR_SHA,bytes:donorBytes.length,artStatus:'EXISTING_GEOMETRY_REVIEW_CANDIDATE; no receipt establishes native art approval'},
  forge:{path:FORGE,sha256:FORGE_SHA,receipt:forgeReceiptPath,receiptSha256:sha(forgeReceiptBytes),manifest:forgeReceipt.forgeManifest},
  output:{path:DIRECTORY+'/city-runtime.meshopt.glb',sha256:sha(diskBytes),bytes:diskBytes.length,triangles,meshes:donor.json.meshes.length,primitives:donor.json.meshes.reduce((n,m)=>n+m.primitives.length,0),nodes:donor.json.nodes.length,materials:donor.json.materials.length,images:donor.json.images.length,accessors:donor.json.accessors.length},
  selectedFamilies:SELECTED_FAMILIES,replacedImages:15,unchangedImages:39,
  textureContract:{albedo:'sRGB (KTX DFD transfer2), existing hardware/shader decode chosen by Babylon',normal:'linear OpenGL +Y; no flip',orm:'linear R=AO G=roughness B=metal',dimensions:[1024,1024],mipLevels:11,encoding:'NONE; existing Forge KTX payloads byte-exact',tilePolicy:'Donor UVs, repeat, texture transforms, source vertex colours and material factors remain unchanged'},
  geometry:{strategy:'Immutable donor tail copied; only physical compressed offsets relocated',sourceTailOffset:result.sourceTailOffset,outputTailOffset:result.outputTailOffset,tailBytes:donor.bin.length-result.sourceTailOffset,tailSha256:sha(donor.bin.subarray(result.sourceTailOffset)),compressedStreamsByteExact:decoded.streams,decodedStreamsByteExact:decoded.streams,decodedBytes:decoded.decodedBytes,accessorSourcesExact:decoded.accessorsCovered,decodedStreamRoster:decoded.roster},
  verification:{containerReadbackExact:true,nonImageMetadataExact:true,materialParametersVertexColoursUvTransformsExact:true,all15ChosenForgePayloadsExact:true,all39UntargetedMapsExact:true,allRoofsPavingWoodGrassCliffMapsRetained:true,protectedInputsUnchanged:true,noRuntimeHooksOrCollidersEdited:true,noGeometryOrTextureEncoding:true},
  protectedInputs:preserved,budget:{limitTriangles:900000,actualTriangles:triangles,overBy:triangles-900000,passed:false,waived:false,promoted:false},
  resources:{nodeHeapLimitMiB:512,ownProcessRssLimitMiB:1536,maxObservedOwnRssMiB:maxObservedRss/1048576,measurement:'Own-process RSS sampled at phases and each decoded stream; not system RAM/GPU memory'},
  apiEvidence:{installedMeshoptimizer:JSON.parse(await fs.readFile(path.join(root,'apps/client/node_modules/meshoptimizer/package.json'),'utf8')).version,context7Library:'/zeux/meshoptimizer',source:'https://github.com/zeux/meshoptimizer/blob/master/js/README.md',method:'ready then decodeGltfBuffer(count*byteStride target,count,byteStride,compressed,mode,filter); one view at a time; no workers'},
  images:result.images,limitations:['Not admitted or selected at runtime. No source/gameplay/collider/default changes.','Donor guardian appearance remains subject to matching native review, and its triangle budget still fails.','Source tints/vertex colours still multiply maps; this is not a palette or UV-repeat correction.','Fresh renderer/city/hour A/B required; no FPS, GPU memory or phone qualification.']};
 await fs.writeFile(path.join(directory,'runtime-pack-receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify({status:receipt.status,output:receipt.output,replaced:15,retained:39,decodedStreams:decoded.streams,maxObservedOwnRssMiB:receipt.resources.maxObservedOwnRssMiB,budget:receipt.budget}));
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error(e.message);process.exitCode=1;});
