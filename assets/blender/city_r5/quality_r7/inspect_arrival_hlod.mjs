// CPU-only baseline inspection. Never invokes Blender or writes existing source assets.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..');
const source=path.join(root,'apps/client/src/assets/models/env_reference_city_hlod.glb');
const out=path.join(root,'assets/models/reference-city/r5/arrival-hlod-r01');
const {MeshoptDecoder}=await import(pathToFileURL(path.join(root,'apps/client/node_modules/meshoptimizer/meshopt_decoder.mjs')).href);
await MeshoptDecoder.ready;
const bytes=fs.readFileSync(source),hash=b=>createHash('sha256').update(b).digest('hex');
if(bytes.readUInt32LE(0)!==0x46546c67||bytes.readUInt32LE(4)!==2||bytes.readUInt32LE(8)!==bytes.length)throw Error('Invalid baseline GLB');
let doc,bin;
for(let offset=12;offset<bytes.length;){const size=bytes.readUInt32LE(offset),type=bytes.readUInt32LE(offset+4),data=bytes.subarray(offset+8,offset+8+size);if(type===0x4e4f534a)doc=JSON.parse(data.toString('utf8').trim());if(type===0x004e4942)bin=data;offset+=8+size;}
if(!doc||!bin||bytes.length>4194304)throw Error('Missing/big baseline');
const decoded=doc.bufferViews.map(v=>{const e=v.extensions?.EXT_meshopt_compression;if(!e)return bin.subarray(v.byteOffset??0,(v.byteOffset??0)+v.byteLength);if(e.count*e.byteStride>4194304)throw Error('Decoded view exceeds CPU budget');const target=new Uint8Array(e.count*e.byteStride);MeshoptDecoder.decodeGltfBuffer(target,e.count,e.byteStride,bin.subarray(e.byteOffset,e.byteOffset+e.byteLength),e.mode,e.filter);return Buffer.from(target);});
const widths={5120:1,5121:1,5122:2,5123:2,5125:4,5126:4},dims={SCALAR:1,VEC2:2,VEC3:3,VEC4:4,MAT4:16};
function accessor(index){const a=doc.accessors[index],v=doc.bufferViews[a.bufferView],data=decoded[a.bufferView],n=dims[a.type],w=widths[a.componentType],stride=v.byteStride??n*w,result=[];if(a.sparse)throw Error('Sparse baseline not supported');for(let i=0;i<a.count;i++){const row=[];for(let j=0;j<n;j++){const p=(a.byteOffset??0)+i*stride+j*w;let value=a.componentType===5126?data.readFloatLE(p):a.componentType===5125?data.readUInt32LE(p):a.componentType===5123?data.readUInt16LE(p):a.componentType===5122?data.readInt16LE(p):a.componentType===5121?data.readUInt8(p):data.readInt8(p);if(a.normalized&&a.componentType!==5126)value=a.componentType===5122?Math.max(-1,value/32767):a.componentType===5123?value/65535:a.componentType===5120?Math.max(-1,value/127):value/255;if(!Number.isFinite(value))throw Error('Nonfinite accessor');row.push(value);}result.push(row);}return result;}
const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
function multiply(a,b){return Array.from({length:16},(_,i)=>{const r=i%4,c=Math.floor(i/4);return a[r]*b[c*4]+a[r+4]*b[c*4+1]+a[r+8]*b[c*4+2]+a[r+12]*b[c*4+3];});}
function matrix(n){if(n.matrix)return n.matrix;const [x,y,z,w]=n.rotation??[0,0,0,1],s=n.scale??[1,1,1],t=n.translation??[0,0,0];return[(1-2*y*y-2*z*z)*s[0],(2*x*y+2*z*w)*s[0],(2*x*z-2*y*w)*s[0],0,(2*x*y-2*z*w)*s[1],(1-2*x*x-2*z*z)*s[1],(2*y*z+2*x*w)*s[1],0,(2*x*z+2*y*w)*s[2],(2*y*z-2*x*w)*s[2],(1-2*x*x-2*y*y)*s[2],0,...t,1];}
function point(p,m){return[0,1,2].map(r=>m[r]*p[0]+m[r+4]*p[1]+m[r+8]*p[2]+m[r+12]);}
const instances=[];function walk(index,parent){const n=doc.nodes[index],m=multiply(parent,matrix(n));if(n.mesh!==undefined)instances.push({node:index,mesh:n.mesh,matrix:m});for(const child of n.children??[])walk(child,m);}
for(const index of doc.scenes[doc.scene??0].nodes)walk(index,identity);
const components=[],primitives=[];let triangleTotal=0;
for(const instance of instances){for(const [pi,p]of doc.meshes[instance.mesh].primitives.entries()){
 if((p.mode??4)!==4)throw Error('Nontri baseline');const positions=accessor(p.attributes.POSITION).map(v=>point(v,instance.matrix));const indices=p.indices!==undefined?accessor(p.indices).map(v=>v[0]):positions.map((_,i)=>i);if(indices.length%3)throw Error('Bad triangle count');triangleTotal+=indices.length/3;
 const parent=positions.map((_,i)=>i);const find=i=>{while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i];}return i;};const union=(a,b)=>{parent[find(a)]=find(b);};const weld=new Map();positions.forEach((v,i)=>{const key=v.map(x=>Math.round(x*1e6)).join(':');if(weld.has(key))union(i,weld.get(key));else weld.set(key,i);});
 for(let i=0;i<indices.length;i+=3){const [a,b,c]=indices.slice(i,i+3);if([a,b,c].some(v=>!Number.isInteger(v)||v<0||v>=positions.length))throw Error('Invalid index');union(a,b);union(a,c);}
 const groups=new Map();for(let i=0;i<indices.length;i+=3){const key=find(indices[i]);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(i/3);}
 const material=doc.materials[p.material]?.name??'none';
 for(const triangles of groups.values()){const used=new Set(triangles.flatMap(t=>indices.slice(t*3,t*3+3))),lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(const i of used)for(let a=0;a<3;a++){lo[a]=Math.min(lo[a],positions[i][a]);hi[a]=Math.max(hi[a],positions[i][a]);}components.push({id:`m${instance.mesh}-p${pi}-c${components.length}`,mesh:instance.mesh,primitive:pi,node:instance.node,material,triangles:triangles.length,triangleOrdinals:triangles,boundsGltf:{min:lo,max:hi},boundsBlender:{min:[lo[0],-hi[2],lo[1]],max:[hi[0],-lo[2],hi[1]]}});}
 primitives.push({mesh:instance.mesh,primitive:pi,material,triangles:indices.length/3,vertices:positions.length,attributes:Object.keys(p.attributes)});
}}
if(triangleTotal!==21400||doc.materials.length!==8||(doc.images??[]).length)throw Error('Pinned baseline budget mismatch');
const raw=structuredClone(doc),chunks=[];let offset=0;raw.bufferViews=raw.bufferViews.map((v,i)=>{const data=decoded[i],pad=Buffer.alloc((4-data.length%4)%4);const next={...v,buffer:0,byteOffset:offset,byteLength:data.length};delete next.extensions;chunks.push(data,pad);offset+=data.length+pad.length;return next;});raw.buffers=[{byteLength:offset}];raw.extensionsUsed=(raw.extensionsUsed??[]).filter(x=>x!=='EXT_meshopt_compression');raw.extensionsRequired=(raw.extensionsRequired??[]).filter(x=>x!=='EXT_meshopt_compression');
function glb(document,binary){let json=Buffer.from(JSON.stringify(document));json=Buffer.concat([json,Buffer.alloc((4-json.length%4)%4,32)]);const head=Buffer.alloc(20),bh=Buffer.alloc(8);head.writeUInt32LE(0x46546c67);head.writeUInt32LE(2,4);head.writeUInt32LE(28+json.length+binary.length,8);head.writeUInt32LE(json.length,12);head.writeUInt32LE(0x4e4f534a,16);bh.writeUInt32LE(binary.length);bh.writeUInt32LE(0x004e4942,4);return Buffer.concat([head,json,bh,binary]);}
fs.mkdirSync(out,{recursive:true});const rawBytes=glb(raw,Buffer.concat(chunks));if(rawBytes.length>4194304)throw Error('Decoded baseline exceeds4MiB');
const rawPath=path.join(out,'baseline-decoded-inspection.glb');if(fs.existsSync(rawPath))throw Error('Create-only baseline output already exists');fs.writeFileSync(rawPath,rawBytes);
const report={schema:'xexoria.arrival-hlod.cpu-inspect/1',status:'CPU_DECODED_NOT_NEW_ART_OR_BLENDER',source:{path:source,sha256:hash(bytes),bytes:bytes.length},decoded:{path:rawPath,sha256:hash(rawBytes),bytes:rawBytes.length},triangles:triangleTotal,materials:doc.materials,primitives,components,protectedBaselineUnchanged:hash(fs.readFileSync(source))===hash(bytes)};
fs.writeFileSync(path.join(out,'cpu-inspection.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({triangles:triangleTotal,materials:doc.materials.length,components:components.length,decodedBytes:rawBytes.length,sourceSHA:hash(bytes),focal:components.filter(c=>c.boundsBlender.min[1]<-130&&c.material==='HLOD_Stone').map(({triangleOrdinals,...c})=>c)}));
