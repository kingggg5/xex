// Bounded adapter only: existing postprocess pipeline, in-memory linear ORM resize, one ktx process/two threads.
import {readFileSync,writeFileSync,statfsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {freemem} from 'node:os';
import path from 'node:path';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
import sharp from 'sharp';
import {listTextureSlots} from '@gltf-transform/functions';
import {createIO,postprocessGlb} from '../../../../scripts/gltf-postprocess.mjs';

const job=JSON.parse(readFileSync(process.argv[2],'utf8'));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const disk=statfsSync(job.outputDirectory,{bigint:true});
if(freemem()<3*1024**3||disk.bavail*disk.bsize<100000000n)throw Error('Resource gate: freeRAM<3GiB or freeC<100MB');
if(hash(readFileSync(job.input))!==job.expectedSourceSha256)throw Error('Immutable input hash mismatch');
const nativeSpawn=childProcess.spawn;
const commands=[];
childProcess.spawn=function(command,args,options){
 if(command==='ktx'&&args?.[0]==='create'){
  args=[...args.slice(0,-2),'--threads','2',...args.slice(-2)];commands.push({command,args});
  options={...options,windowsHide:true};
 }
 return nativeSpawn(command,args,options);
};
syncBuiltinESMExports();
const io=await createIO();
const doc=await io.read(job.input);
const resize=[];
for(const texture of doc.getRoot().listTextures()){
 const slots=listTextureSlots(texture);
 if(!slots.some(slot=>slot==='metallicRoughnessTexture'||slot==='occlusionTexture'))continue;
 const old=Buffer.from(texture.getImage()),raw=await sharp(old).raw().toBuffer({resolveWithObject:true});
 const resized=await sharp(raw.data,{raw:{width:raw.info.width,height:raw.info.height,channels:raw.info.channels}})
  .resize(1024,1024,{kernel:'lanczos3'}).png().toBuffer();
 texture.setImage(new Uint8Array(resized)).setMimeType('image/png');
 resize.push({name:texture.getName(),slots,from:[raw.info.width,raw.info.height],to:[1024,1024],
  sourceImageSha256:hash(old),candidateImageSha256:hash(resized),method:'Raw linear data values interpolated; no gamma/colour conversion'});
}
let firstRead=true;
const adapter={read:async file=>{if(path.resolve(file)===path.resolve(job.input)&&firstRead){firstRead=false;return doc;}return io.read(file);},
 writeBinary:io.writeBinary.bind(io),writeJSON:io.writeJSON.bind(io)};
try{
 const report=await postprocessGlb({input:job.input,output:job.output,className:job.class,
  textureOut:job.textureOut,ktxBin:job.ktxBin,ktx:{jobs:1},io:adapter});
 report.owner_adaptation={linearOrmResize:resize,encoderProcessConcurrency:1,threadsPerEncoder:2,
  commands,sourceHashUnchanged:hash(readFileSync(job.input))===job.expectedSourceSha256,
  outputSha256:hash(readFileSync(job.output)),scope:'External canonical candidate; source rig and files immutable'};
 writeFileSync(job.report,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({status:report.status,output:job.output,sha256:report.owner_adaptation.outputSha256,
  bytes:report.sizes.glb.raw,texturesBytes:report.sizes.external_texture_bytes,textureGpuMiB:report.metrics.texture_mib,
  triangles:report.metrics.triangles,parity:report.parity,failures:report.failures,budget:report.budget.breaches}));
 if(report.status!=='PASS')process.exitCode=report.status==='FAIL_BUDGET'?2:3;
}finally{childProcess.spawn=nativeSpawn;syncBuiltinESMExports();}
