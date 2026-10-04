import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {createIO,documentFacts} from '../../../../apps/client/scripts/gltf-postprocess.mjs';
import {Document} from '../../../../apps/client/node_modules/@gltf-transform/core/dist/index.js';
import {mergeDocuments,cloneDocument,prune,dedup,simplify,meshopt,unpartition,flatten,join} from '../../../../apps/client/node_modules/@gltf-transform/functions/dist/index.js';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../../..');
const out=path.join(root,'assets/models/blueprint-cc0'),e=path.join(root,'planning/evidence/blueprint-p0-20261003/cc0');
const require=createRequire(path.join(root,'apps/client/package.json'));
const {MeshoptSimplifier,MeshoptEncoder}=require('meshoptimizer');
const validator=require('gltf-validator');
await Promise.all([MeshoptSimplifier.ready,MeshoptEncoder.ready]);
const io=await createIO(),assets=[],receipts=[];
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const rel=p=>path.relative(root,p).replaceAll('\\','/');
const linear=h=>h.match(/../g).map(v=>{const n=parseInt(v,16)/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;});
const buff=linear('D9B983'),wood=linear('604A35'),leaf=linear('A4B648');
const nature=n=>path.join(out,'source/kenney-nature-kit/Models/GLTF format',n+'.glb');
const town=n=>path.join(out,'source/kenney-fantasy-town-kit/Models/GLB format',n+'.glb');
const provenance=async(files,source,licence)=>({source,licence,files:await Promise.all(files.map(async p=>({file:rel(p),sha256:sha(await fs.readFile(p))})))});
function restyle(doc){for(const m of doc.getRoot().listMaterials()){
 const n=m.getName().toLowerCase();
 if(n.includes('leaf'))m.setBaseColorFactor([...leaf,1]).setRoughnessFactor(.9).setDoubleSided(true);
 else if(n.includes('wood')||n.includes('bark'))m.setBaseColorFactor([...wood,1]).setRoughnessFactor(.9);
 else if(n.includes('red')||n.includes('marble'))m.setBaseColorFactor([...buff,1]).setRoughnessFactor(.9);
 else if(n==='colormap')m.setBaseColorFactor([1,.96,.87,1]).setRoughnessFactor(.88);
 if(n.includes('magic'))m.setEmissiveFactor([0,0,0]);
 }}
function wrapNormalize(doc,height,id){
 const facts=documentFacts(doc),b=facts.bounds,s=height/(b.max[1]-b.min[1]);
 const scene=doc.getRoot().listScenes()[0],children=[...scene.listChildren()];
 const wrapper=doc.createNode(id+'_root').setScale([s,s,s]).setTranslation([-(b.min[0]+b.max[0])/2*s,-b.min[1]*s,-(b.min[2]+b.max[2])/2*s]);
 for(const n of children){scene.removeChild(n);wrapper.addChild(n);}scene.addChild(wrapper);
 return wrapper;
}
async function finish(id,doc,standinFor,prov,extra={}){
 restyle(doc);await doc.transform(prune(),dedup(),unpartition());
 const base=cloneDocument(doc),lods=[];let bounds;
 for(let lod=0;lod<3;lod++){
  const d=cloneDocument(base);
  if(lod)await d.transform(simplify({simplifier:MeshoptSimplifier,ratio:lod===1?.7:.4,error:.002,lockBorder:true}));
  d.getRoot().setDefaultScene(d.getRoot().listScenes()[0]);
  const raw=path.join(out,'candidates',`${id}_lod${lod}.glb`),file=path.join(out,'runtime',`${id}_lod${lod}.meshopt.glb`);
  await fs.mkdir(path.dirname(raw),{recursive:true});await fs.mkdir(path.dirname(file),{recursive:true});
  const bytes=await io.writeBinary(d);await fs.writeFile(raw,bytes);
  const v=await validator.validateBytes(bytes,{maxIssues:5000,writeTimestamp:false});if(v.issues.numErrors){console.error(JSON.stringify(v.issues.messages.filter(m=>m.severity===0).slice(0,5)));throw Error(`${id}: ${v.issues.numErrors} validator errors`);}
  await d.transform(meshopt({encoder:MeshoptEncoder,level:'medium'}));
  await io.write(file,d);const loaded=await io.read(file),facts=documentFacts(loaded);
  if(lod===0)bounds=facts.bounds;
  lods.push({lod,file:rel(file),tris:facts.triangles,sha256:sha(await fs.readFile(file)),bytes:(await fs.stat(file)).size});
  receipts.push({id,lod,raw:rel(raw),validator_errors:v.issues.numErrors,validator_warnings:v.issues.numWarnings,decoded_triangles:facts.triangles,bounds:facts.bounds,max_attributes:facts.maxAttributes});
 }
 const names=base.getRoot().listMaterials().map(m=>m.getName());
 assets.push({id,status:'CC0_STANDIN',licence:'CC0',source:prov.source,standinFor,lods,bounds,
  materialSlots:names,textures:base.getRoot().listTextures().map(t=>({name:t.getName(),mime:t.getMimeType(),size:t.getSize(),sha256:sha(t.getImage())})),
  provenance:prov,collider:{type:'box',min:[bounds.min[0],0,bounds.min[2]],max:[bounds.max[0],Math.min(1.8,bounds.max[1]),bounds.max[2]],status:'PROXY_ONLY_ROOT_OWNS_ADMISSION'},
  shadowProxy:{file:lods[2].file,tris:lods[2].tris},...extra});
 console.log(JSON.stringify({id,lods:lods.map(l=>l.tris),bounds}));
}
const palm=await io.read(nature('tree_palmDetailedTall'));wrapNormalize(palm,7,'blueprint_cc0_palm');
let ix=0;for(const n of palm.getRoot().listNodes())if(n.getName()==='leafs')n.setName('palm_fronds_'+ix++);
await finish('blueprint_cc0_palm',palm,['PL1'],await provenance([nature('tree_palmDetailedTall'),path.join(out,'source/kenney-nature-kit/License.txt')],'https://kenney.nl/assets/nature-kit','CC0 inside downloaded Nature Kit2.1 zip'),
 {wind:{rootAnchor:[0,0,0],nodeNames:['palm_fronds_0','palm_fronds_1'],maxDisplacementM:.08,frequencyHz:.6,status:'ANCHOR_METADATA_LOADER_REQUIRED'},componentGaps:['Coconuts not present in this licensed stock model.']});
const tent=await io.read(nature('tent_detailedOpen'));wrapNormalize(tent,2.3,'blueprint_cc0_tent');
await finish('blueprint_cc0_tent',tent,['ST3'],await provenance([nature('tent_detailedOpen'),path.join(out,'source/kenney-nature-kit/License.txt')],'https://kenney.nl/assets/nature-kit','CC0 inside Nature Kit zip'));
const cart=await io.read(town('cart-high'));wrapNormalize(cart,1.6,'blueprint_cc0_cart');
await cart.transform(flatten(),join());
await finish('blueprint_cc0_cart',cart,['C2','C3'],await provenance([town('cart-high'),path.join(out,'source/kenney-fantasy-town-kit/License.txt'),path.join(out,'source/kenney-fantasy-town-kit/Models/GLB format/Textures/colormap.png')],'https://kenney.nl/assets/fantasy-town-kit','CC0 extracted original kit licence'),{componentGaps:['Hay/crate loads remain separate loader dressing.']});
// Build an 11m marker from mature licensed wall/roof modules; no new primitives.
const mill=new Document(),scene=mill.createScene('blueprint_cc0_windmill');mill.createBuffer();
async function imported(file){const d=await io.read(file),s=d.getRoot().listScenes()[0],map=mergeDocuments(mill,d),roots=s.listChildren().map(n=>map.get(n));for(const sc of mill.getRoot().listScenes())if(sc!==scene)sc.dispose();return roots[0];}
const wall=await imported(town('wall-curved')),roof=await imported(town('roof-high-corner-round')),sail=await imported(town('windmill'));
function qy(a){return [0,Math.sin(a/2),0,Math.cos(a/2)];}
for(let layer=0;layer<3;layer++)for(let quarter=0;quarter<4;quarter++){
 const pivot=mill.createNode(`mill_wall_${layer}_${quarter}`).setRotation(qy(quarter*Math.PI/2));
 const n=mill.createNode(`licensed_wall_${layer}_${quarter}`).setMesh(wall.getMesh()).setScale([3.8,2.65,3.8]).setTranslation([1.9,layer*2.65,1.9]);pivot.addChild(n);scene.addChild(pivot);
}
for(let quarter=0;quarter<4;quarter++){
 const p=mill.createNode('mill_roof_'+quarter).setRotation(qy(quarter*Math.PI/2));
 p.addChild(mill.createNode('licensed_roof_'+quarter).setMesh(roof.getMesh()).setScale([3.8,2.2,3.8]).setTranslation([1.9,7.9,1.9]));scene.addChild(p);
}
const rotor=mill.createNode('windmill_sails').setTranslation([0,6.9,4.35]);
rotor.addChild(mill.createNode('licensed_sails').setMesh(sail.getMesh()).setScale([2.45,2.45,2.45]).setRotation(qy(-Math.PI/2)));scene.addChild(rotor);
wall.dispose();roof.dispose();sail.dispose();
scene.removeChild(rotor);await mill.transform(flatten({cleanup:false}),join({cleanup:false}));scene.addChild(rotor);
wrapNormalize(mill,11,'blueprint_cc0_windmill');
await finish('blueprint_cc0_windmill',mill,['ST1'],await provenance([town('wall-curved'),town('roof-high-corner-round'),town('windmill'),path.join(out,'source/kenney-fantasy-town-kit/License.txt')],'https://kenney.nl/assets/fantasy-town-kit','CC0 modular assembly'),{motion:{nodeNames:['windmill_sails'],axis:[0,0,1],pivot:[0,0,0],periodSeconds:18,status:'ANIMATION_HOOK_LOADER_REQUIRED'},componentGaps:['Licensed assembled stand-in; authored facade/door detail remains replacement work.']});
// Existing mature CC0 anatomy + owner-authored guardian cloth, kept immutable.
const gbase=path.join(root,'assets/models/reference-city/r5/art-candidates/fountain-guardian-v2/fountain_guardian_lod1.glb');
const guardian=await io.read(gbase);wrapNormalize(guardian,6,'blueprint_cc0_guardian');
await guardian.transform(flatten(),join());
await finish('blueprint_cc0_guardian',guardian,['S1','S2'],await provenance([gbase,path.join(root,'assets/models/reference-city/r5/art-candidates/fountain-guardian-v1/source/LICENSE.ASSETS.md'),path.join(root,'assets/models/reference-city/r5/art-candidates/fountain-guardian-v1/asset-manifest.json')],'MakeHumanCC0 anatomy + existing owner-authored guardianv2 cloth','Pinned source graphical assets CC0; project-authored derivative reused internally'),{componentGaps:['Guardian design remains a stand-in; plinth1.2m is supplied by P0 loader.']});
for(const asset of assets){
 if(asset.id==='blueprint_cc0_palm')asset.collider={type:'cylinder',radius:.25,height:7,rootAnchor:[0,0,0],status:'PROXY_ONLY_ROOT_OWNS_ADMISSION'};
 if(asset.id==='blueprint_cc0_guardian')asset.collider={type:'box',min:[-.85,0,-.6],max:[.85,1.8,.6],status:'TORSO_PROXY_PLINTH_SEPARATE_ROOT_OWNS_ADMISSION'};
 if(asset.id==='blueprint_cc0_windmill')asset.collider={type:'box',min:[-3.7,0,-3.7],max:[3.7,7.8,3.7],status:'TOWER_CORE_PROXY_SAILS_EXCLUDED_ROOT_OWNS_ADMISSION'};
 asset.lodPolicy='Protected silhouettes; equal low triangle counts at multiple LODs do not claim a reduction. Geometry remains compact.';
}
const manifest={schema:'xexoria.blueprint-cc0/1',status:'CC0_STANDINS_READY_NATIVE_UNVERIFIED',region:'sunmeadow',created_utc:new Date().toISOString(),assets,
 missingAssets:[{id:'blueprint_cc0_sheep',standinFor:['F1'],reason:'No licensed sheep model in the on-disk packs or downloaded Nature Kit; no invented animal.'}],
 integrationNotes:['Loader owns exact blueprint anchors and terrain/physics admission.','PL1=8cove palms+2pier palms; mature Kenney source, no homemade/Tripo trees.','ST4 tower uses loader stone kit; no misleading watchtower asset emitted.','Source previews inspected; native render/animation/LOD silhouette acceptance remains pending due foreign live GPU lease.']};
await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
await fs.writeFile(path.join(e,'validation.json'),JSON.stringify({schema:'xexoria.blueprint-cc0-validation/1',result:'STATIC_PASS_NATIVE_PENDING',records:receipts},null,2)+'\n');
