/** CPU-only local pipeline. Preserve COLOR_0, use a texture-free shared material slot. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../../..');
const out=path.join(root,'apps/client/src/assets/world/water-art-pass4b-r03');
const evid=path.join(root,'planning/evidence/water-art-pass4b-20261003/r03');
const raw=path.join(here,'raw'),stage=path.join(here,'geometry-stage'),id='sm_grotto_organic_r03';
const {parseGlb,packGlb,postprocessGlb,createIO,documentFacts}=await import(pathToFileURL(path.join(root,'apps/client/scripts/gltf-postprocess.mjs')).href);
const requireClient=createRequire(path.join(root,'apps/client/package.json'));
const {validateBytes}=await import(pathToFileURL(requireClient.resolve('gltf-validator')).href);
const esm=name=>pathToFileURL(requireClient.resolve(name).replace(/\.cjs$/,'.js')).href;
const {EXTMeshoptCompression}=await import(esm('@gltf-transform/extensions'));
const {dedup,prune,weld,reorder,quantize}=await import(esm('@gltf-transform/functions'));
const {MeshoptEncoder}=await import(pathToFileURL(requireClient.resolve('meshoptimizer')).href);await MeshoptEncoder.ready;
const rel=p=>path.relative(root,p).split(path.sep).join('/');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
await Promise.all([out,stage,evid].map(p=>fs.mkdir(p,{recursive:true})));
const records=[];
for(const suffix of ['lod0','lod1','lod2','collider','shadow']){
 const src=path.join(raw,`${id}_${suffix}.glb`),bytes=await fs.readFile(src),{json,bin}=parseGlb(bytes);
 const visible=suffix.startsWith('lod');
 delete json.images;delete json.textures;delete json.samplers;
 json.extensionsUsed=(json.extensionsUsed??[]).filter(x=>!x.startsWith('KHR_materials_')&&x!=='KHR_texture_transform'&&x!=='KHR_texture_basisu');
 json.extensionsRequired=(json.extensionsRequired??[]).filter(x=>!x.startsWith('KHR_materials_')&&x!=='KHR_texture_transform'&&x!=='KHR_texture_basisu');
 if(visible){json.materials=[{name:'sm_stone_mat',pbrMetallicRoughness:{baseColorFactor:[1,1,1,1],metallicFactor:0,roughnessFactor:1},doubleSided:false}];}
 else delete json.materials;
 for(const mesh of json.meshes??[]){mesh.name=`${id}_${suffix}`;for(const p of mesh.primitives){if(visible)p.material=0;else delete p.material;}}
 for(const node of json.nodes??[])if(node.mesh!==undefined)node.name=`${id}_${suffix}`;
 const input=path.join(stage,`${id}_${suffix}.glb`),output=path.join(out,`${id}_${suffix}.glb`);
 await fs.writeFile(input,packGlb(json,bin));
 // Existing pipeline primitives, with POSITION explicitly kept Float32. The standard
 // whole-mesh 14-bit quantization collapsed tiny Boolean triangles in this small asset.
 const floatIO=await createIO(),floatDoc=await floatIO.read(input);
 for(const mesh of floatDoc.getRoot().listMeshes())for(const p of mesh.listPrimitives()){
  // Texture-free material slot: Babylon derives tangent basis after the parent assigns normal PBR.
  p.setAttribute('TANGENT',null);
  const color=p.getAttribute('COLOR_0');if(!color)continue;
  const rgb=new Uint8Array(color.getCount()*3),el=[];
  for(let i=0;i<color.getCount();i++){color.getElement(i,el);for(let k=0;k<3;k++)rgb[i*3+k]=Math.round(Math.max(0,Math.min(1,el[k]))*255);}
  const a=floatDoc.createAccessor('COLOR_0_RGB').setType('VEC3').setArray(rgb).setNormalized(true).setBuffer(color.getBuffer());p.setAttribute('COLOR_0',a);
 }
 await floatDoc.transform(dedup({keepUniqueNames:true}),prune({keepAttributes:true,keepLeaves:true,keepExtras:true}),weld(),reorder({encoder:MeshoptEncoder,target:'size'}));
 floatDoc.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({method:EXTMeshoptCompression.EncoderMethod.QUANTIZE});
 await floatIO.write(output,floatDoc);
 const report={schema:'xexoria.grotto-lossless-position-postprocess/1',status:'PASS',input:rel(input),output:rel(output),
  pipeline:'Existing createIO/parse/pack, glTF-Transform dedup/prune/weld/reorder, RGB8 COLOR_0, lossless EXT_meshopt compression; Float32 POSITION/NORMAL/UV retained',
  reason:'Measured whole-mesh POSITION quantization collapsed small Boolean triangles; exact positions required for topology and dense channel support.',positionFormat:'FLOAT32',textures:[],samplers:[],COLOR_0:'normalized RGB8'};
 const runtime=await fs.readFile(output),parsed=parseGlb(runtime);
 if((parsed.json.images??[]).length||(parsed.json.textures??[]).length||(parsed.json.samplers??[]).length)throw new Error('Runtime texture policy '+suffix);
 const io=await createIO(),doc=await io.read(output),facts=documentFacts(doc);
 const geometry=[];
 for(const node of doc.getRoot().listNodes()){
  const mesh=node.getMesh();if(!mesh)continue;const m=node.getWorldMatrix();
  for(const p of mesh.listPrimitives()){
   if(visible&&!p.getAttribute('COLOR_0'))throw new Error('COLOR_0 stripped '+suffix);
   const pos=p.getAttribute('POSITION'),el=[],verts=[];
   for(let i=0;i<pos.getCount();i++){
    pos.getElement(i,el);const gx=m[0]*el[0]+m[4]*el[1]+m[8]*el[2]+m[12],gy=m[1]*el[0]+m[5]*el[1]+m[9]*el[2]+m[13],gz=m[2]*el[0]+m[6]*el[1]+m[10]*el[2]+m[14];
    verts.push([-gx-4,gy,gz-39]);
   }
   const idx=p.getIndices()?.getArray()??Array.from({length:verts.length},(_,i)=>i);
   const attributeReceipt={};
   for(const name of p.listSemantics()){
    const a=p.getAttribute(name),array=a.getArray(),type=a.getType(),finite=Array.from(array).every(Number.isFinite);
    attributeReceipt[name]={count:a.getCount(),type,componentType:a.getComponentType(),normalized:a.getNormalized(),finite};
    if(name==='NORMAL'){
     const lengths=[];for(let i=0;i<a.getCount();i++){a.getElement(i,el);lengths.push(Math.hypot(...el));}
     attributeReceipt[name].minLength=Math.min(...lengths);attributeReceipt[name].maxLength=Math.max(...lengths);
    }
    if(name==='COLOR_0'){
     attributeReceipt[name].minimumComponent=Math.min(...array);attributeReceipt[name].maximumComponent=Math.max(...array);
    }
   }
   geometry.push({positions:verts,indices:Array.from(idx),attributes:p.listSemantics(),attributeReceipt});
  }
 }
 await fs.writeFile(path.join(evid,`sculpt-${suffix}-runtime-geometry.json`),JSON.stringify({schema:'xexoria.runtime-decoded-grotto/1',file:rel(output),sha256:sha(runtime),worldPivot:[-4,0,-39],geometry}));
 const validation=await validateBytes(new Uint8Array(runtime),{maxIssues:50});
 if(validation.issues.numErrors)throw new Error('Khronos errors '+suffix+' '+JSON.stringify(validation.issues.messages.slice(0,4)));
 const tris=geometry.reduce((n,p)=>n+p.indices.length/3,0),budget={lod0:6000,lod1:2400,lod2:800}[suffix];
 if(budget&&tris>budget)throw new Error('Runtime triangle budget '+suffix);
 report.metrics={triangles:tris,draw_calls:geometry.length,intended_visible_draw_calls:visible?geometry.length:0,materials:doc.getRoot().listMaterials().length,glb_bytes:runtime.length,texture_mib:0};
 report.validator={errors:validation.issues.numErrors,warnings:validation.issues.numWarnings};
 await fs.writeFile(path.join(evid,`sculpt-${suffix}-postprocess-float.json`),JSON.stringify(report,null,2));
 const points=geometry.flatMap(p=>p.positions),mn=[0,1,2].map(k=>Math.min(...points.map(p=>p[k]))),mx=[0,1,2].map(k=>Math.max(...points.map(p=>p[k])));
 records.push({suffix,file:rel(output),sha256:sha(runtime),bytes:runtime.length,triangles:tris,draw_calls:geometry.length,intended_visible_draw_calls:visible?geometry.length:0,materials:doc.getRoot().listMaterials().length,
  vertex_attributes:geometry.map(p=>p.attributes),attributeReceipts:geometry.map(p=>p.attributeReceipt),boundsWorld:{min:mn,max:mx},boundsBabylonLocal:{min:[mn[0]+4,mn[1],mn[2]+39],max:[mx[0]+4,mx[1],mx[2]+39]},
  khronos:{errors:validation.issues.numErrors,warnings:validation.issues.numWarnings},textureFree:true,postprocessStatus:report.status});
 console.log(`${suffix}: ${tris}tri ${runtime.length}B COLOR=${visible} ${report.status}`);
}
const shared=JSON.parse(await fs.readFile(path.join(root,'assets/models/sunmeadow-props/manifest.json'),'utf8')).families.stone.find(x=>x.id==='sm_boulder_03');
const source=JSON.parse(await fs.readFile(path.join(evid,'sculpt-source-provenance.json'),'utf8'));
const manifest={schema:'xexoria.water-art-grotto-manifest/1',id,candidate:'water-art-pass4b-r03',revision:3,status:'SOURCE_CANDIDATE_NATIVE_UNVERIFIED',family:'stone',recipe:'sculpt.boulder-volume-negative-passage/1',
 material_slot:'sm_stone_mat',runtime_material:'Parent assigns existing shared sm_stone PBR and canonical KTX2 atlas; GLBs have no texture/sampler references.',
 pivot:[0,0,0],anchor_at_pivot:true,placement:{x:-4,y:0,z:-39,yaw:0,scale:1},
 coordinate_contract:'Blender local (-worldX-4,-worldZ-39,worldY) -> glTF (bx,bz,-by) -> default Babylon X-reflection -> local(worldX+4,worldY,worldZ+39). Do not remove the default X reflection, rotate, recenter or ground by bounds.',
 bounds:records[0].boundsBabylonLocal,lods:records.filter(x=>x.suffix.startsWith('lod')),collider:records.find(x=>x.suffix==='collider'),shadow:records.find(x=>x.suffix==='shadow'),
 textures:shared.textures,metadata:{opening_width_m:4.8,opening_height_m:5.1,floor_world_y:0,inner_east_crown_m:8.35,source_film_immutable:true,
  collider_note:'Separate geometry-only proxy preserves negative passage. Baseline raw/server collider admission is outside this source candidate.',
  visual_remove_ids:['v3_grotto_mouth','v3_grotto_tunnel','water_art_grotto_bluff_000','water_art_grotto_bluff_001','water_art_grotto_bluff_002','water_art_grotto_bluff_003','water_art_grotto_bluff_004','water_art_grotto_bluff_005','water_art_grotto_bluff_006']},
 provenance:{source_receipt:rel(path.join(evid,'sculpt-source-provenance.json')),editable_source:rel(path.join(here,'sm_grotto_organic_r03.blend')),recipe:rel(path.join(here,'sculpt_grotto_r03.py')),postpack:rel(fileURLToPath(import.meta.url)),sourceHashes:source.sourceHashes},
 verdicts:{technical:'Source probes plus exported/redecoded parity recorded separately',visual:'BLENDER REVIEW only; parent native review pending',gameplay:'UNVERIFIED',device:'UNVERIFIED'}};
await fs.writeFile(path.join(out,'grotto-manifest.json'),JSON.stringify(manifest,null,2));
await fs.writeFile(path.join(evid,'sculpt-runtime-receipt.json'),JSON.stringify({schema:'xexoria.sculpt-grotto-runtime/1',records,manifest:rel(path.join(out,'grotto-manifest.json')),recipeSha256:sha(await fs.readFile(path.join(here,'sculpt_grotto_r03.py'))),sourceBlendSha256:sha(await fs.readFile(path.join(here,'sm_grotto_organic_r03.blend')))},null,2));
