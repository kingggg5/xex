// Art-only H04 review subset selected solely from the unchanged actual-byte gates.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..');
const assetRoot=process.env.XEXORIA_ASSET_SOURCE_ROOT??path.join(os.homedir(),'Downloads','Xexoria-Game');
const agentOutput=process.env.XEXORIA_AGENT_OUTPUT??path.join(assetRoot,'agent-output');
const base=path.join(agentOutput,'20261004-heroes04-06-compact-r01');
const auditPath=path.join(root,'planning/evidence/heroes-six-20261004/continuation/heroes04-06-rig-audit-h04-r03-240hz.json');
const audit=JSON.parse(fs.readFileSync(auditPath,'utf8'));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const bytes=fs.readFileSync(audit.file);if(hash(bytes)!==audit.sha256)throw Error('Staged source changed');
const jsonLength=bytes.readUInt32LE(12);const doc=JSON.parse(bytes.toString('utf8',20,20+jsonLength));
const safe=new Set(audit.actual_exported_skinning.filter(c=>c.floor_candidate_gate&&c.deformation_candidate_gate&&c.max_root_drift_m<=1e-6).map(c=>c.name));
const excluded=doc.animations.filter(a=>!safe.has(a.name)).map(a=>a.name);
doc.animations=doc.animations.filter(a=>safe.has(a.name));
doc.asset.extras={...(doc.asset.extras??{}),xex_status:'ART_ONLY_PARTIAL_SAFE_POSE_REVIEW_NOT_GAME_READY',xex_excluded_unsafe_clips:excluded};
const encoded=Buffer.from(JSON.stringify(doc));const json=Buffer.alloc(Math.ceil(encoded.length/4)*4,0x20);encoded.copy(json);
const tail=bytes.subarray(20+jsonLength);const output=Buffer.alloc(20+json.length+tail.length);
output.write('glTF',0);output.writeUInt32LE(2,4);output.writeUInt32LE(output.length,8);output.writeUInt32LE(json.length,12);output.writeUInt32LE(0x4e4f534a,16);json.copy(output,20);tail.copy(output,20+json.length);
const out=path.join(base,'budget-r03/04/art-review');fs.mkdirSync(out,{recursive:true});
const file=path.join(out,'hero04_acolyte_lod0-safe-art-review.glb');if(fs.existsSync(file))throw Error('Immutable safe review already exists');
fs.writeFileSync(file,output);
const require=createRequire(path.join(root,'apps/client/package.json'));const validator=require('gltf-validator');
const result=await validator.validateBytes(new Uint8Array(output),{uri:path.basename(file),maxIssues:30});
if(result.issues.numErrors)throw Error('GLB schema validation failed');
const receipt={schema:'xexoria.compact-safe-art-subset/1',hero:'04',status:'ART_ONLY_PARTIAL_SAFE_POSE_REVIEW_NOT_GAME_READY',
 input:{file:audit.file,sha256:audit.sha256},audit:{file:auditPath,sha256:hash(fs.readFileSync(auditPath))},
 output:{file,bytes:output.length,sha256:hash(output)},included_clips:[...safe],excluded_unsafe_clips:excluded,
 selection_rule:'Original240Hz actual-exported skinning:floor>=-1mm,p99edge-stretch<=2,rootdrift<=1µm; thresholds unchanged',
 source_binary_chunk_preserved:true,geometry_uv_weights_joints_material_texture_bytes_preserved:true,
 khronos:{errors:result.issues.numErrors,warnings:result.issues.numWarnings,infos:result.issues.numInfos,messages:result.issues.messages},
 limits:['Art review only. No native appearance, weapon, gameplay or phone acceptance.','No playable attack/run is supplied in this subset; all8clip staged source is preserved and rejected.','H06R03did not export after RAM watchdog; H06R02remains unsafe.','Unused animation accessors remain in the preserved binary; this is not a final optimized package.']};
const evidence=path.join(root,'planning/evidence/heroes-six-20261004/continuation/heroes04-06-rig-safe-art-h04-r03.json');
if(fs.existsSync(evidence))throw Error('Immutable subset receipt exists');fs.writeFileSync(evidence,JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({output:receipt.output,included:receipt.included_clips,excluded,errors:receipt.khronos.errors,warnings:receipt.khronos.warnings}));
