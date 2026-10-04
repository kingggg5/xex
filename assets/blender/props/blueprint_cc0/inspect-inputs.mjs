import fs from 'node:fs';
import path from 'node:path';
import {createIO,documentFacts} from '../../../../apps/client/scripts/gltf-postprocess.mjs';
const io=await createIO();
for(const file of process.argv.slice(2)){
 const doc=await io.read(path.resolve(file)),facts=documentFacts(doc);
 console.log(JSON.stringify({file,triangles:facts.triangles,bounds:facts.bounds,
  nodes:doc.getRoot().listNodes().map(n=>({name:n.getName(),translation:n.getTranslation(),rotation:n.getRotation(),scale:n.getScale(),mesh:n.getMesh()?.getName()})),
  materials:doc.getRoot().listMaterials().map(m=>({name:m.getName(),color:m.getBaseColorFactor(),texture:m.getBaseColorTexture()?.getName(),size:m.getBaseColorTexture()?.getSize()})),
  primitives:doc.getRoot().listMeshes().flatMap(m=>m.listPrimitives().map(p=>({mesh:m.getName(),attrs:p.listSemantics(),material:p.getMaterial()?.getName()})))
 }));
}
