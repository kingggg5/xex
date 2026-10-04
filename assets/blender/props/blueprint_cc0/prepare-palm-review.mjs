import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createIO,documentFacts} from '../../../../apps/client/scripts/gltf-postprocess.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..'),io=await createIO();
const E=path.join(root,'planning/evidence/blueprint-p0-20261003/cc0/palm-v2');
for(const [name,file] of [['v1','assets/models/blueprint-cc0/runtime/blueprint_cc0_palm_lod0.meshopt.glb'],['v2','assets/models/blueprint-cc0/candidates/palm-palette-v2/blueprint_cc0_palm_palette_v2_lod0.meshopt.glb']]){
 const d=await io.read(path.join(root,file)),before=documentFacts(d);
 for(const ext of d.getRoot().listExtensionsUsed())if(ext.extensionName==='EXT_meshopt_compression')ext.dispose();
 const bytes=await io.writeBinary(d);await fs.writeFile(path.join(E,`review-${name}.glb`),bytes);
 const after=documentFacts(await io.readBinary(bytes));if(after.triangles!==before.triangles||JSON.stringify(after.bounds)!==JSON.stringify(before.bounds))throw Error('Review decode mismatch');
}
console.log('Review copies decoded; source and candidate runtime remain unchanged.');
