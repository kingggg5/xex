import {createRequire} from 'node:module';import {readFile,writeFile,mkdir} from 'node:fs/promises';import {createHash} from 'node:crypto';import path from 'node:path';import {pathToFileURL,fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),requireClient=createRequire(path.join(root,'apps/client/package.json')),load=name=>import(pathToFileURL(requireClient.resolve(name)).href);
const {NodeIO}=await load('@gltf-transform/core'),{ALL_EXTENSIONS}=await load('@gltf-transform/extensions'),{MeshoptEncoder,MeshoptDecoder}=await load('meshoptimizer');await Promise.all([MeshoptEncoder.ready,MeshoptDecoder.ready]);
const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.encoder':MeshoptEncoder,'meshopt.decoder':MeshoptDecoder}),hash=b=>createHash('sha256').update(b).digest('hex');
const folder=path.join(root,'apps/client/src/assets/characters/hero01-review-r02'),out=path.join(folder,'transport');await mkdir(out,{recursive:true});const receipts=[];
for(let level=0;level<3;level++){
 const name=`hero01_swordsman_lod${level}.glb`,source=path.join(folder,name),bytes=await readFile(source),doc=await io.read(source),joints=doc.getRoot().listSkins().map(s=>s.listJoints().map(n=>n.getName())),textures=doc.getRoot().listTextures().map(t=>hash(t.getImage()));
 const transport=await io.writeBinary(doc),target=path.join(out,name);await writeFile(target,transport);const checked=await io.read(target);
 if(JSON.stringify(checked.getRoot().listSkins().map(s=>s.listJoints().map(n=>n.getName())))!==JSON.stringify(joints)||JSON.stringify(checked.getRoot().listTextures().map(t=>hash(t.getImage())))!==JSON.stringify(textures))throw Error('Transport changed joints or KTX bytes');
 if(!bytes.equals(await readFile(source)))throw Error('Canonical source changed');
 receipts.push({source:path.relative(root,source).replaceAll('\\','/'),sourceSha256:hash(bytes),transport:path.relative(root,target).replaceAll('\\','/'),sha256:hash(transport),bytes:transport.length,joints:joints[0].length,clips:checked.getRoot().listAnimations().map(a=>a.getName()),textureHashes:textures,budgetScope:'Canonical external GLB and active texture files are gated separately; this is whole-download transport, not geometry KiB.'});
}
await writeFile(path.join(root,'planning/evidence/heroes-six-20261004/hero01-transport.json'),JSON.stringify(receipts,null,2)+'\n');console.log(JSON.stringify(receipts.map(r=>({bytes:r.bytes,joints:r.joints,clips:r.clips.length,sha256:r.sha256}))));
