// Staff-only non-pruning LOD recipe. Preserve all components while collapsing UV seams with attributes.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {MeshoptSimplifier as S} from '../../../../apps/client/node_modules/meshoptimizer/meshopt_simplifier.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..');
const dir=path.join(root,'assets/models/heroes/hero02/work/staff_meshopt');
const read=(name,T)=>{const b=fs.readFileSync(path.join(dir,name));return new T(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));};
await S.ready;
const p=read('positions.f32',Float32Array),n=read('normals.f32',Float32Array),uv=read('uvs.f32',Float32Array),ix=read('indices.u32',Uint32Array);
const attributes=new Float32Array(p.length/3*5);
for(let v=0;v<p.length/3;v++)attributes.set([...n.slice(v*3,v*3+3),...uv.slice(v*2,v*2+2)],v*5);
const weights=[.4,.4,.4,.6,.6],flags=['RegularizeLight','Permissive'],rows=[];
for(const [lod,target]of [[0,1990],[1,990]]){
 const[out,error]=S.simplifyWithAttributes(ix,p,3,attributes,5,weights,null,target*3,.2,flags);
 if(!out.length||out.length/3>target||error>.2)throw Error(`staff LOD${lod} failed: ${out.length/3} tris, error ${error}`);
 fs.writeFileSync(path.join(dir,`lod${lod}.indices.u32`),Buffer.from(out.buffer,out.byteOffset,out.byteLength));
 rows.push({lod,target,triangles:out.length/3,errorRelative:error,errorMetresAt2_270m:error*2.27,flags});
}
fs.writeFileSync(path.join(dir,'simplify-report.json'),JSON.stringify({source:{triangles:ix.length/3,vertices:p.length/3},recipe:'non-pruning attribute-aware collapse; no component deletion',weights,lods:rows},null,2)+'\n');
console.log(JSON.stringify(rows));
