// Versioned material-only repair. Frozen manifest, source and existing GLBs stay immutable.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {createIO,parseGlb,packGlb,documentFacts} from '../../../../apps/client/scripts/gltf-postprocess.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..');
const base=path.join(root,'assets/models/blueprint-cc0'),out=path.join(base,'candidates/palm-palette-v2');
const e=path.join(root,'planning/evidence/blueprint-p0-20261003/cc0/palm-v2');
await Promise.all([fs.mkdir(out,{recursive:true}),fs.mkdir(e,{recursive:true})]);
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const rel=p=>path.relative(root,p).replaceAll('\\','/');
const srgbToLinear=h=>h.match(/../g).map(v=>{const x=parseInt(v,16)/255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;});
const manifestPath=path.join(base,'manifest.json'),manifestBytes=await fs.readFile(manifestPath);
const asset=JSON.parse(manifestBytes).assets.find(a=>a.id==='blueprint_cc0_palm'),candidate=structuredClone(asset),io=await createIO(),records=[];
candidate.candidateVersion='palm-palette-v2';candidate.admission='NOT_ADMITTED_ROOT_COMPARISON_REQUIRED';
candidate.lods=[];
for(const lod of asset.lods){
 const input=path.join(root,lod.file),bytes=await fs.readFile(input),parsed=parseGlb(bytes);
 const geometryJson=structuredClone(parsed.json);delete geometryJson.materials;
 const before=structuredClone(parsed.json.materials);
 for(const m of parsed.json.materials){
  m.pbrMetallicRoughness??={};m.pbrMetallicRoughness.metallicFactor=0;
  m.emissiveFactor=[0,0,0];delete m.emissiveTexture;
  if(m.name==='leafsGreen'){
   m.pbrMetallicRoughness.baseColorFactor=[...srgbToLinear('B4C45A'),1];
   m.pbrMetallicRoughness.roughnessFactor=.82;m.doubleSided=true;
  }else if(m.name==='woodBark'){
   m.pbrMetallicRoughness.baseColorFactor=[...srgbToLinear('A38A64'),1];
   m.pbrMetallicRoughness.roughnessFactor=.94;m.doubleSided=false;
  }else throw Error('Unexpected palm material '+m.name);
 }
 const file=path.join(out,`blueprint_cc0_palm_palette_v2_lod${lod.lod}.meshopt.glb`),result=packGlb(parsed.json,parsed.bin);
 await fs.writeFile(file,result);const reread=parseGlb(result),otherJson=structuredClone(reread.json);delete otherJson.materials;
 if(!reread.bin.equals(parsed.bin)||JSON.stringify(otherJson)!==JSON.stringify(geometryJson))throw Error('Geometry/pivot/hierarchy changed');
 const d=await io.read(file),facts=documentFacts(d);if(facts.triangles!==lod.tris)throw Error('Triangle count');
 if(JSON.stringify(facts.bounds)!==JSON.stringify(asset.bounds))throw Error('Bounds changed');
 candidate.lods.push({...lod,file:rel(file),sha256:hash(result),bytes:result.length});
 records.push({lod:lod.lod,input:lod.file,input_sha256:hash(bytes),output:rel(file),output_sha256:hash(result),binary_sha256:hash(parsed.bin),
  binary_geometry_unchanged:true,all_non_material_json_unchanged:true,triangles:facts.triangles,bounds:facts.bounds,
  before_materials:before,after_materials:reread.json.materials,
  source_material_contract:'metallic0; rough diffuse foliage/bark; emissive0; leafdoubleSided maps in Babylon loader to backFaceCullingfalse/twoSidedLightingtrue.'});
}
candidate.shadowProxy={...candidate.shadowProxy,file:candidate.lods[2].file};
candidate.palette={leaf_srgb:'#B4C45A',bark_srgb:'#A38A64',storage:'linear glTF baseColorFactor',metallic:0,emissive:[0,0,0]};
candidate.verdict={original_native:'ART_FAIL: almostblack/rigidslabs, preserved',palette:'STATIC_VALIDATED_NATIVE_PENDING',shape:'ITERATE: licensed stock geometry remains rigid slabs; no invented tree or shape approval.'};
await fs.writeFile(path.join(out,'candidate-asset.json'),JSON.stringify(candidate,null,2)+'\n');
if(!Buffer.from(await fs.readFile(manifestPath)).equals(manifestBytes))throw Error('Frozen manifest changed');
for(const r of records)if(hash(await fs.readFile(path.join(root,r.input)))!==r.input_sha256)throw Error('Frozen GLB changed');
await fs.writeFile(path.join(e,'palette-repair-receipt.json'),JSON.stringify({schema:'xexoria.palm-palette-repair/1',created_utc:new Date().toISOString(),
 result:'MATERIAL_ONLY_CANDIDATE_READY_NATIVE_PENDING',frozen_manifest_sha256:hash(manifestBytes),candidate:rel(path.join(out,'candidate-asset.json')),
 original_art_verdict:'ART_FAIL preserved',shape_verdict:'ITERATE',records,
 limits:['No map-wide grade, geometry, normal, winding, UV, pivot, collider, source or current manifest changes.','No glow/emissive workaround.','Native comparison only after workerrelease/freshGPUlease; root owns admission.']},null,2)+'\n');
console.log(JSON.stringify({result:'CANDIDATE_READY',candidate:rel(path.join(out,'candidate-asset.json')),lods:candidate.lods.map(l=>({lod:l.lod,tris:l.tris,sha256:l.sha256})),shape:'ITERATE'}));
