// A versioned character candidate; preserve immutable bake sources and all rig/map bytes.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const root=process.cwd(),requireClient=createRequire(path.join(root,'apps/client/package.json'));
const load=name=>import(pathToFileURL(requireClient.resolve(name)).href);
const {NodeIO}=await load('@gltf-transform/core'),{ALL_EXTENSIONS}=await load('@gltf-transform/extensions');
const {weld,simplify}=await load('@gltf-transform/functions');
const {MeshoptSimplifier,MeshoptEncoder,MeshoptDecoder}=await load('meshoptimizer');
await Promise.all([MeshoptSimplifier.ready,MeshoptEncoder.ready,MeshoptDecoder.ready]);
const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.decoder':MeshoptDecoder,'meshopt.encoder':MeshoptEncoder});
const source=path.join(root,'apps/client/src/assets/characters/hero01-review-r03/hero01_swordsman_lod0.transport.glb');
const sourceBytes=fs.readFileSync(source),hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const baseline=await io.read(source),signature=doc=>({joints:doc.getRoot().listSkins().map(s=>s.listJoints().map(n=>n.getName())),clips:doc.getRoot().listAnimations().map(a=>a.getName()),maps:doc.getRoot().listTextures().map(t=>hash(t.getImage()))});
const expected=JSON.stringify(signature(baseline)),folder=path.join(root,'apps/client/src/assets/characters/hero01-review-r04');fs.mkdirSync(folder,{recursive:true});
const totals=doc=>doc.getRoot().listMeshes().flatMap(m=>m.listPrimitives()).reduce((r,p)=>({triangles:r.triangles+p.getIndices().getCount()/3,vertices:r.vertices+p.getAttribute('POSITION').getCount()}),{triangles:0,vertices:0});
const report={schema:'xexoria.hero01-compact/1',source,sourceSha256:hash(sourceBytes),sourceCounts:totals(baseline),method:'Meshopt welded simplification retaining vertex attributes; no permissive seam collapse; rig, animation and texture bytes retained. Native pose/art acceptance required.',lods:[]};
for(const [level,ratio] of [.44,.25,.10].entries()){
 const doc=await io.read(source);await doc.transform(weld(),simplify({simplifier:MeshoptSimplifier,ratio,error:.025,lockBorder:false}));
 const counts=totals(doc);if(counts.vertices>5000||counts.triangles>5500)throw Error('Actual candidate budget failed: '+JSON.stringify(counts));
 let invalidWeights=0,invalidIndices=0,nonFinite=0;
 for(const mesh of doc.getRoot().listMeshes())for(const p of mesh.listPrimitives()){
  const position=p.getAttribute('POSITION'),weights=p.getAttribute('WEIGHTS_0'),joints=p.getAttribute('JOINTS_0');
  if(!weights||!joints||!p.getAttribute('TEXCOORD_0'))throw Error('Missing skin/UV attributes');
  for(const value of position.getArray())if(!Number.isFinite(value))nonFinite++;
  for(const value of p.getIndices().getArray())if(value>=position.getCount())invalidIndices++;
  for(let i=0;i<weights.getCount();i++){const w=weights.getElement(i,[]);if(w.some(x=>!Number.isFinite(x)||x<0)||Math.abs(w.reduce((a,b)=>a+b,0)-1)>.002)invalidWeights++;}
 }
 if(invalidWeights||invalidIndices||nonFinite)throw Error('Invalid actual attributes');
 const file=path.join(folder,`hero01_swordsman_lod${level}.glb`);await io.write(file,doc);const checked=await io.read(file);
 if(JSON.stringify(signature(checked))!==expected)throw Error('Rig/clip/map signature changed');
 report.lods.push({level,...totals(checked),file,bytes:fs.statSync(file).size,sha256:hash(fs.readFileSync(file)),joints:47,clips:14,invalidWeights,invalidIndices,nonFinite});
}
if(!sourceBytes.equals(fs.readFileSync(source)))throw Error('Immutable source changed');report.sourceUnchanged=true;
fs.writeFileSync('planning/evidence/heroes-six-20261004/continuation/hero01-compact-r04.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report.lods));
