import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createIO,documentFacts} from '../../../../apps/client/scripts/gltf-postprocess.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..'),io=await createIO();
const paths=['assets/models/blueprint-cc0/source/kenney-nature-kit/Models/GLTF format/tree_palmDetailedTall.glb','assets/models/blueprint-cc0/runtime/blueprint_cc0_palm_lod0.meshopt.glb'];
const records=[];
for(const file of paths){
 const d=await io.read(path.join(root,file));let minDot=1,maxDot=-1,zero=0,total=0;
 for(const mesh of d.getRoot().listMeshes())for(const p of mesh.listPrimitives()){
  const normal=p.getAttribute('NORMAL');if(!normal)continue;
  const v=[];for(let i=0;i<normal.getCount();i++){normal.getElement(i,v);const L=Math.hypot(...v);if(!L)zero++;total++;minDot=Math.min(minDot,v[1]);maxDot=Math.max(maxDot,v[1]);}
 }
 records.push({file,facts:documentFacts(d),materials:d.getRoot().listMaterials().map(m=>({name:m.getName(),baseColorFactor:m.getBaseColorFactor(),metallic:m.getMetallicFactor(),roughness:m.getRoughnessFactor(),doubleSided:m.getDoubleSided(),alphaMode:m.getAlphaMode(),emissive:m.getEmissiveFactor(),normalTexture:m.getNormalTexture()?.getName()})),normal_statistics:{total,zero,minY:minDot,maxY:maxDot}});
}
const e=path.join(root,'planning/evidence/blueprint-p0-20261003/cc0/palm-v2');await fs.mkdir(e,{recursive:true});
await fs.writeFile(path.join(e,'material-intake.json'),JSON.stringify({records},null,2)+'\n');
console.log(JSON.stringify(records.map(r=>({file:r.file,materials:r.materials,normal_statistics:r.normal_statistics}))));
