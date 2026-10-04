import {createHash} from 'node:crypto';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

/** A names/visual-preview projection, never an executable combat catalog. */
export function projectHeroSkillPreview(input,sourceSha256){
 if(input?.schema!=='xexoria.hero-skills/1'||!String(input.status).startsWith('DESIGN DRAFT'))throw new TypeError('Expected the inactive hero-skills design draft.');
 if(!/^[a-f0-9]{64}$/.test(sourceSha256))throw new TypeError('Expected source SHA-256.');
 if(!Array.isArray(input.heroes)||input.heroes.length!==6||!Array.isArray(input.skills)||input.skills.length!==42)throw new TypeError('Expected six heroes and 42 skill entries.');
 const heroIds=new Set(input.heroes.map(h=>h.id)),ids=new Set(),slots=new Set();
 if(heroIds.size!==6)throw new TypeError('Duplicate hero IDs.');
 const names=value=>{
  if(!value||typeof value.en!=='string'||typeof value.th!=='string'||!value.en.trim()||!value.th.trim()||value.en.length>160||value.th.length>160)throw new TypeError('Expected bounded Thai and English placeholder names.');
  return {en:value.en,th:value.th};
 };
 const entries=input.skills.map(skill=>{
  const key=`${skill.hero}:${skill.slot}`;
  if(typeof skill.id!=='string'||!/^h0[1-6]_[a-z0-9_]{1,64}$/.test(skill.id)||ids.has(skill.id)||!heroIds.has(skill.hero)||!Number.isInteger(skill.slot)||skill.slot<0||skill.slot>6||slots.has(key))throw new TypeError('Invalid or duplicate skill identity/slot.');
  ids.add(skill.id);slots.add(key);
  const timing=skill.timing;
  if(!timing||timing.fps!==30||!Number.isSafeInteger(timing.windup_ms)||timing.windup_ms<0||timing.windup_ms>60000||timing.release_ms!==timing.windup_ms||timing.release_frame!==Math.round(timing.windup_ms*.03))throw new TypeError('Invalid visual release timing.');
  if(!Number.isSafeInteger(skill.cooldown_ms)||skill.cooldown_ms<0||skill.cooldown_ms>600000||!skill.vfx||typeof skill.vfx.preset!=='string'||!Number.isFinite(skill.vfx.peak_coverage_pct)||skill.vfx.peak_coverage_pct<0||skill.vfx.peak_coverage_pct>100)throw new TypeError('Invalid visual preview metadata.');
  return {id:skill.id,hero:skill.hero,slot:skill.slot,name:names(skill.name),execution:'preview-only',visualPreset:skill.vfx.preset,proposedCooldownMs:skill.cooldown_ms,releaseMs:timing.release_ms,releaseFrame30:timing.release_frame,proposedPeakCoveragePct:skill.vfx.peak_coverage_pct};
 });
 return {schema:'xexoria.hero-skills-preview/1',sourceSchema:input.schema,sourceVersion:input.version,sourceSha256,status:'DESIGN_DRAFT_PREVIEW_ONLY',namesArePlaceholders:true,ownerDecisionsOpen:['D1','D2','D3','D4','D5','D6','D7','D8'],cooldownAuthority:'Server endsAt notices; proposed values here are preview labels only.',heroes:input.heroes.map(h=>({id:h.id,name:names(h.name)})),skills:entries};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const output=process.argv[2];
 if(!output)throw new TypeError('Pass an explicit output JSON path.');
 const inputUrl=new URL('../planning/assets/hero-skills.json',import.meta.url),bytes=await readFile(inputUrl);
 if(bytes.length>1048576)throw new RangeError('Draft catalog exceeds one MiB.');
 const sourceSha256=createHash('sha256').update(bytes).digest('hex');
 const projected=projectHeroSkillPreview(JSON.parse(bytes),sourceSha256),encoded=JSON.stringify(projected,null,2)+'\n';
 if(!bytes.equals(await readFile(inputUrl)))throw new Error('Draft source changed during projection; retry from a stable revision.');
 await mkdir(dirname(resolve(output)),{recursive:true});
 await writeFile(output,encoded);
 console.log(JSON.stringify({status:'DRAFT_PREVIEW_ONLY',entries:projected.skills.length,sourceBytes:bytes.length,projectedBytes:Buffer.byteLength(encoded),sourceSha256,outputSha256:createHash('sha256').update(encoded).digest('hex')}));
}
