// Candidate-only CPU splice: original terrain/tree/water/other geometry buffers stay exact.
import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..'),out=path.join(root,'assets/models/reference-city/r5/arrival-hlod-r01');
const hash=b=>createHash('sha256').update(b).digest('hex');
function parse(file){const b=fs.readFileSync(file);if(b.readUInt32LE(0)!==0x46546c67||b.readUInt32LE(8)!==b.length)throw Error('Bad GLB '+file);let doc,bin;for(let i=12;i<b.length;){const n=b.readUInt32LE(i),t=b.readUInt32LE(i+4);if(t===0x4e4f534a)doc=JSON.parse(b.subarray(i+8,i+8+n).toString().trim());if(t===0x004e4942)bin=b.subarray(i+8,i+8+n);i+=8+n;}return{doc,bin,bytes:b};}
const baselinePath=path.join(root,'apps/client/src/assets/models/env_reference_city_hlod.glb');const baselineBytes=fs.readFileSync(baselinePath);
if(hash(baselineBytes)!=='771fdf2bc450c3df2cc937f231176145d9d27bfae7772b616298a0dd063038b5')throw Error('Pinned source changed');
const inspection=JSON.parse(fs.readFileSync(path.join(out,'cpu-inspection.json'))),archReceipt=JSON.parse(fs.readFileSync(path.join(out,'architecture-receipt.json')));
const base=parse(path.join(out,'baseline-decoded-inspection.glb')),arch=parse(path.join(out,'architecture-only.glb'));
const doc=structuredClone(base.doc),segments=[base.bin];let binLength=base.bin.length;
function append(data){const aligned=Buffer.alloc((4-binLength%4)%4);segments.push(aligned);binLength+=aligned.length;const start=binLength;segments.push(data);binLength+=data.length;return start;}
function bufferAccessor(data,format,type,count,target=34962,min,max){const view=doc.bufferViews.length;doc.bufferViews.push({buffer:0,byteOffset:append(data),byteLength:data.length,target});const id=doc.accessors.length;doc.accessors.push({bufferView:view,componentType:format,type,count,...(min?{min}:{}),...(max?{max}:{})});return id;}
function bytesFor(g,a){const x=g.doc.accessors[a],v=g.doc.bufferViews[x.bufferView];return g.bin.subarray((v.byteOffset??0)+(x.byteOffset??0),(v.byteOffset??0)+v.byteLength);}
function indexValues(g,id){const a=g.doc.accessors[id],data=bytesFor(g,id),w=a.componentType===5125?4:2;if(![5123,5125].includes(a.componentType))throw Error('Unexpected index format');return Array.from({length:a.count},(_,i)=>w===4?data.readUInt32LE(i*w):data.readUInt16LE(i*w));}
const removal=new Map();for(const id of archReceipt.selected_ids){const c=inspection.components.find(c=>c.id===id);if(!c)throw Error('Unknown selected component');const k=c.mesh+':'+c.primitive;if(!removal.has(k))removal.set(k,new Set());for(const triangle of c.triangleOrdinals){if(removal.get(k).has(triangle))throw Error('Duplicate retirement');removal.get(k).add(triangle);}}
let removed=0;const preservation=[];
for(let mi=0;mi<doc.meshes.length;mi++)for(let pi=0;pi<doc.meshes[mi].primitives.length;pi++){
 const p=doc.meshes[mi].primitives[pi],source=base.doc.meshes[mi].primitives[pi],set=removal.get(mi+':'+pi),indices=indexValues(base,source.indices);const kept=[];
 for(let t=0;t<indices.length/3;t++){if(set?.has(t)){removed++;continue;}kept.push(...indices.slice(t*3,t*3+3));}
 if(set){const data=Buffer.alloc(kept.length*2);kept.forEach((value,i)=>data.writeUInt16LE(value,i*2));p.indices=bufferAccessor(data,5123,'SCALAR',kept.length,34963,[Math.min(...kept)],[Math.max(...kept)]);}
 preservation.push({mesh:mi,primitive:pi,originalTriangles:indices.length/3,retired:set?.size??0,retained:kept.length/3,retainedIndexSHA:hash(Buffer.from(new Uint32Array(kept).buffer)),positionAccessorUnchanged:p.attributes.POSITION===source.attributes.POSITION,normalAccessorUnchanged:p.attributes.NORMAL===source.attributes.NORMAL});
 // Neutral attributes let the existing static merger accept one consistent layout. No world texture mapping.
 const n=doc.accessors[p.attributes.POSITION].count;
 p.attributes.COLOR_0=bufferAccessor(Buffer.alloc(n*4,255),5121,'VEC4',n);doc.accessors[p.attributes.COLOR_0].normalized=true;
 p.attributes.TEXCOORD_0=bufferAccessor(Buffer.alloc(n*8),5126,'VEC2',n);
}
if(removed!==100)throw Error('Retirement differs from exact selected100triangles');
const archBinOffset=append(arch.bin),viewOffset=doc.bufferViews.length,accessorOffset=doc.accessors.length,meshOffset=doc.meshes.length,nodeOffset=doc.nodes.length;
for(const v of arch.doc.bufferViews)doc.bufferViews.push({...v,buffer:0,byteOffset:(v.byteOffset??0)+archBinOffset});
for(const a of arch.doc.accessors)doc.accessors.push({...a,bufferView:a.bufferView+viewOffset});
const materialMap=arch.doc.materials.map(m=>{const id=doc.materials.findIndex(b=>b.name===m.name);if(id<0)throw Error('New material '+m.name);return id;});
for(const mesh of arch.doc.meshes)doc.meshes.push({...mesh,primitives:mesh.primitives.map(p=>{if(!p.attributes.COLOR_0||!p.attributes.TEXCOORD_0)throw Error('Architecture lacks planned color/UV attributes');return{...p,attributes:Object.fromEntries(Object.entries(p.attributes).map(([k,v])=>[k,v+accessorOffset])),indices:p.indices+accessorOffset,material:materialMap[p.material]};})});
for(const n of arch.doc.nodes)doc.nodes.push({...n,...(n.mesh!==undefined?{mesh:n.mesh+meshOffset}:{}),...(n.children?{children:n.children.map(c=>c+nodeOffset)}:{})});
doc.scenes[doc.scene??0].nodes.push(...arch.doc.scenes[arch.doc.scene??0].nodes.map(n=>n+nodeOffset));
doc.extensionsUsed=[...new Set([...(doc.extensionsUsed??[]),...(arch.doc.extensionsUsed??[])])];doc.extensionsRequired=[...new Set([...(doc.extensionsRequired??[]),...(arch.doc.extensionsRequired??[])])];doc.buffers=[{byteLength:binLength}];
const binary=Buffer.concat(segments),gltf={doc,bin:binary};let triangles=0;
for(const mesh of doc.meshes)for(const p of mesh.primitives){const indices=indexValues(gltf,p.indices);triangles+=indices.length/3;const positions=doc.accessors[p.attributes.POSITION];if(indices.some(i=>i>=positions.count))throw Error('Invalid candidate index');if(Object.keys(p.attributes).length+4>8)throw Error('Vertex binding cap');}
if(triangles!==22864||triangles>25000||doc.materials.length!==8||(doc.images??[]).length)throw Error('Candidate cap/count mismatch');
// The original buffer segment is copied byte-for-byte, including every terrain/tree/water POSITION/NORMAL value.
if(!binary.subarray(0,base.bin.length).equals(base.bin))throw Error('Protected base attribute bytes changed');
let json=Buffer.from(JSON.stringify(doc));json=Buffer.concat([json,Buffer.alloc((4-json.length%4)%4,32)]);const pad=Buffer.alloc((4-binary.length%4)%4);const packed=Buffer.concat([binary,pad]);const header=Buffer.alloc(20),bh=Buffer.alloc(8);header.writeUInt32LE(0x46546c67);header.writeUInt32LE(2,4);header.writeUInt32LE(28+json.length+packed.length,8);header.writeUInt32LE(json.length,12);header.writeUInt32LE(0x4e4f534a,16);bh.writeUInt32LE(packed.length);bh.writeUInt32LE(0x004e4942,4);const candidate=Buffer.concat([header,json,bh,packed]);
if(candidate.length>4194304)throw Error('Candidate exceeds4MiB');const output=path.join(out,'arrival-hlod-r01.glb');if(fs.existsSync(output))throw Error('Create-only candidate exists');fs.writeFileSync(output,candidate);
const receipt={schema:'xexoria.arrival-hlod.splice/1',status:'CPU_ASSEMBLED_NATIVE_A_B_REQUIRED',sourceSHA:hash(baselineBytes),candidate:{path:output,sha256:hash(candidate),bytes:candidate.length,triangles,materials:8,images:0,meshCount:doc.meshes.length,vertexAttributes:['POSITION','NORMAL','COLOR_0','TEXCOORD_0'],sharedTextureResidencyAdded:0},retiredComponents:archReceipt.selected_ids,retiredTriangles:removed,addedArchitectureTriangles:1564,baseGeometryBufferSHA:hash(base.bin),baseGeometryBufferCopiedExactly:true,preservation,terrainTreesWaterBuffersUnchanged:true,neutralBaselineAttributes:'whiteRGBA + zeroUV; no texture assigned or world remapping',colliderOrPlacementFilesChanged:0,blenderRenders:0,native:'UNVERIFIED'};
if(hash(fs.readFileSync(baselinePath))!==hash(baselineBytes))throw Error('Protected runtime mutated');fs.writeFileSync(path.join(out,'splice-receipt.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt.candidate));
