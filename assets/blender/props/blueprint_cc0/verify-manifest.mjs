import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {createIO,documentFacts} from '../../../../apps/client/scripts/gltf-postprocess.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..');
const out=path.join(root,'assets/models/blueprint-cc0'),e=path.join(root,'planning/evidence/blueprint-p0-20261003/cc0');
const m=JSON.parse(await fs.readFile(path.join(out,'manifest.json'),'utf8')),io=await createIO(),records=[];
if(m.schema!=='xexoria.blueprint-cc0/1')throw Error('schema');
for(const a of m.assets){
 if(a.status!=='CC0_STANDIN'||a.licence!=='CC0'||a.lods.length!==3)throw Error(a.id);
 for(const l of a.lods){
  const file=path.resolve(root,l.file);if(!file.startsWith(out+path.sep))throw Error('path escaped');
  const bytes=await fs.readFile(file);if(crypto.createHash('sha256').update(bytes).digest('hex')!==l.sha256)throw Error('hash '+a.id);
  const d=await io.read(file),f=documentFacts(d);if(f.triangles!==l.tris||!f.bounds||f.maxAttributes>8)throw Error('facts');
  if(!Object.values(f.bounds).flat().every(Number.isFinite))throw Error('bounds');
  const names=d.getRoot().listNodes().map(n=>n.getName());
  if(a.id.includes('windmill')&&!names.includes('windmill_sails'))throw Error('motion node');
  records.push({id:a.id,lod:l.lod,triangles:f.triangles,draw_calls:f.drawCalls,materials:f.materialCount,attributes:f.maxAttributes,bounds:f.bounds,bytes:bytes.length});
 }
 for(const p of a.provenance.files){const bytes=await fs.readFile(path.join(root,p.file));if(crypto.createHash('sha256').update(bytes).digest('hex')!==p.sha256)throw Error('source modified');}
}
const r={schema:'xexoria.blueprint-cc0-readback/1',result:'PASS_STATIC_NATIVE_UNVERIFIED',records,
 missing:m.missingAssets,limits:['Readback/foot bounds/licences/hashes only. No native visual, motion, device, collider or shadow admission claim.']};
await fs.writeFile(path.join(e,'readback-final.json'),JSON.stringify(r,null,2)+'\n');
console.log(JSON.stringify({result:r.result,assets:m.assets.length,lod_files:records.length,summary:records.filter(r=>r.lod===0)}));
