import {readFileSync,writeFileSync,statSync} from 'node:fs';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {createIO} from '../../../../scripts/gltf-postprocess.mjs';
const repo=path.resolve(process.cwd(),'../..');
const evidence=path.join(repo,'planning/evidence/heroes-six-20261004');
const io=await createIO(),rows=[],textures=new Map();
const hash=file=>createHash('sha256').update(readFileSync(file)).digest('hex');
const arrayHash=array=>createHash('sha256').update(new Uint8Array(array.buffer,array.byteOffset,array.byteLength)).digest('hex');
function signature(doc){const root=doc.getRoot();return {
 joints:root.listSkins().map(s=>s.listJoints().map(n=>({name:n.getName(),parent:n.getParentNode()?.getName()??null}))),
 clips:root.listAnimations().map(a=>({name:a.getName(),channels:a.listChannels().map(c=>({path:c.getTargetPath(),node:c.getTargetNode()?.getName(),
  inputHash:arrayHash(c.getSampler().getInput().getArray()),outputHash:arrayHash(c.getSampler().getOutput().getArray()),interpolation:c.getSampler().getInterpolation()}))})),
 uv:root.listMeshes().flatMap(m=>m.listPrimitives().map(p=>!!p.getAttribute('TEXCOORD_0')))};}
for(let lod=0;lod<3;lod++){
 const job=JSON.parse(readFileSync(path.join(evidence,`hero01-pack-job-lod${lod}.json`),'utf8'));
 const report=JSON.parse(readFileSync(job.report,'utf8'));
 const source=await io.read(job.input),candidate=await io.read(job.output);
 const old=signature(source),fresh=signature(candidate);
 if(JSON.stringify(old.joints)!==JSON.stringify(fresh.joints))throw Error(`LOD${lod} joint order/names/hierarchy changed`);
 if(JSON.stringify(old.clips)!==JSON.stringify(fresh.clips))throw Error(`LOD${lod} clip names/targets changed`);
 if(fresh.uv.some(p=>!p))throw Error(`LOD${lod} UV0 missing`);
 let maxInfluences=0,maxSumError=0;
 for(const mesh of candidate.getRoot().listMeshes())for(const prim of mesh.listPrimitives()){
  if(prim.getAttribute('JOINTS_1')||prim.getAttribute('WEIGHTS_1'))throw Error('Extra influence set');
  const weights=prim.getAttribute('WEIGHTS_0');if(!weights)throw Error('Weights missing');
  for(let i=0;i<weights.getCount();i++){const w=weights.getElement(i,[]);maxInfluences=Math.max(maxInfluences,w.filter(v=>v>0).length);maxSumError=Math.max(maxSumError,Math.abs(w.reduce((a,b)=>a+b,0)-1));}
 }
 if(maxInfluences>4||maxSumError>1e-5)throw Error(`LOD${lod} non-normalized influences: ${maxSumError}`);
 if(hash(job.input)!==job.expectedSourceSha256)throw Error('Source hash changed');
 for(const tex of report.textures)textures.set(tex.sha256,{file:tex.file,bytes:tex.bytes,sha256:tex.sha256,codec:tex.codec,width:tex.width,height:tex.height,gpuBytes:tex.gpu_bytes});
 rows.push({lod,input:job.input,inputSha256:hash(job.input),output:job.output,sha256:hash(job.output),bytes:statSync(job.output).size,
  reportStatus:report.status,triangles:report.metrics.triangles,joints:fresh.joints[0].length,clipNames:fresh.clips.map(c=>c.name),
  maxInfluences,maxWeightSumError:maxSumError,uv0:true,clipInputOutputBytesAndInterpolationUnchanged:true,parity:report.parity,validator:report.validator,
  lossyChanges:report.owner_adaptation.linearOrmResize,encoderCommands:report.owner_adaptation.commands});
}
const sourceTotal=rows.reduce((n,r)=>n+statSync(r.input).size,0),packageBytes=rows.reduce((n,r)=>n+r.bytes,0)+[...textures.values()].reduce((n,t)=>n+t.bytes,0);
const receipt={schema:'xexoria.hero01-art-pack/1',status:'TECHNICAL_PACK_PASS_NATIVE_AB_REQUIRED',createdUtc:new Date().toISOString(),
 sourceImmutable:true,externalCanonical:true,rows,activeTextures:[...textures.values()],activePackageBytes:packageBytes,originalAllLodGlbBytes:sourceTotal,
 combinedTransferReductionPercent:100*(1-packageBytes/sourceTotal),textureGpuMiB:[...textures.values()].reduce((n,t)=>n+t.gpuBytes,0)/1024**2,
 sourceRgba8WithMipsEstimateMiB:64,lossy:'Only linear ORM resized2048→1024; ETC1S colour/UASTC data and meshopt quantization are lossy. Albedo/normal remain2048.',
 limits:['No native GPU/performance/art acceptance claimed. Root must A/B before mounting.',
 'Canonical textures are external; Vite transport/bundling is owned by root. No embedded geometry-budget waiver.',
 'Inherited H01 rig/attack/gait/crown defects and missing six skill/hit/dodge/death clips remain.'],
 jev:'USED_VERIFIED parent current heroes-task receipt reused'};
writeFileSync(path.join(evidence,'hero01-pack-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({status:receipt.status,activePackageBytes:packageBytes,originalAllLodGlbBytes:sourceTotal,transferReduction:receipt.combinedTransferReductionPercent,
 textureGpuMiB:receipt.textureGpuMiB,rows:rows.map(({lod,bytes,sha256,joints,clipNames,maxWeightSumError})=>({lod,bytes,sha256,joints,clipNames,maxWeightSumError}))}));
