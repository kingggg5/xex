import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {postprocessGlb,createIO,documentFacts} from '../../../../apps/client/scripts/gltf-postprocess.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..');
const out=path.join(root,'assets/models/blueprint-cc0'),e=path.join(root,'planning/evidence/blueprint-p0-20261003/cc0');
const manifest=JSON.parse(await fs.readFile(path.join(out,'manifest.json'),'utf8'));
const io=await createIO(),reports=[];
for(const asset of manifest.assets){
 for(const lod of asset.lods){
  if(!['blueprint_cc0_cart','blueprint_cc0_windmill'].includes(asset.id))continue;
  const output=path.join(root,lod.file),input=path.join(out,'candidates',`${asset.id}_lod${lod.lod}.glb`);
  const report=await postprocessGlb({input,output,className:asset.id.includes('windmill')?'building_module':'prop',embedTextures:true,textureOut:path.join(out,'runtime/textures'),io});
  reports.push(report);if(report.status!=='PASS')throw Error(report.status);
  const bytes=await fs.readFile(output),facts=documentFacts(await io.read(output));
  Object.assign(lod,{sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,tris:facts.triangles});
 }
 const doc=await io.read(path.join(root,asset.lods[0].file));
 asset.textures=doc.getRoot().listTextures().map(t=>({name:t.getName(),mime:t.getMimeType(),size:t.getSize(),sha256:crypto.createHash('sha256').update(t.getImage()).digest('hex')}));
 asset.shadowProxy={file:asset.lods[2].file,tris:asset.lods[2].tris};
}
await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
await fs.writeFile(path.join(e,'palette-postprocess.json'),JSON.stringify({result:'PASS',reports},null,2)+'\n');
console.log(JSON.stringify({result:'PASS',packed:reports.length}));
