import hero02Draft from './assets/vfx/hero02-draft-v1/draft-visuals.json' with {type:'json'};
const deepFreeze=value=>{if(value&&typeof value==='object'){Object.values(value).forEach(deepFreeze);Object.freeze(value);}return value;};
export const VFX_TIER_BUDGETS=deepFreeze({low:{draws:5,particles:60,cpuP95Ms:2},medium:{draws:8,particles:120,cpuP95Ms:3},high:{draws:10,particles:250,cpuP95Ms:5},ultra:{draws:16,particles:400,gpuParticles:2000,cpuP95Ms:5}});
export const CORE_VFX_IDS=Object.freeze(['xs_bladeward_nova','xs_gale_palm','xs_void_rift']);
const layers={xs_bladeward_nova:{anticipation:['nova-ring'],core:['nova-blades'],secondaries:['nova-shards'],ground:['nova-cracks'],after:['nova-dust']},xs_gale_palm:{anticipation:['gale-core'],core:['gale-sigil'],secondaries:['gale-streaks'],ground:['gale-vortex'],after:['gale-dust']},xs_void_rift:{anticipation:['rift-outer','rift-inner'],core:['rift-curtain'],secondaries:['rift-motes'],ground:['rift-abyss','rift-rim'],after:['rift-scorch']}};
function define(id,template,name,shape,palette,coreHeight,holdStart,holdEnd){const family=Object.fromEntries(Object.entries(layers[template]).map(([key,names])=>[key,names.slice()]));if(shape==='double-ring')family.anticipation.push('nova-shock');if(shape==='star')family.anticipation.push('gale-ground-flash');return {id,hero:'witch02',template,name,visualOnly:true,telegraphShape:shape,palette,coreHeight,peakHoldMs:[holdStart,holdEnd],layers:family,captureMs:template===CORE_VFX_IDS[0]?[60,130,190,260,420,780,1150,2200]:template===CORE_VFX_IDS[1]?[100,200,360,580,780,920,1250,2000]:[300,620,950,1270,2000,2920,3120,3900],targets:{screenCoverage:[.15,.35],ultimateCoverage:[.35,.50],colourfulnessM:45,peakHoldRangeMs:[120,250]},status:'VISUAL_PROTOTYPE_NATIVE_REVIEW_REQUIRED'};}
/** Six visual mappings, three physical template families. No cooldown, damage or reward fields. */
const LEGACY_SAMPLE_DEFINITIONS=deepFreeze([
 define(CORE_VFX_IDS[0],CORE_VFX_IDS[0],'Bladeward Nova','circle',{core:'#73CFFF',body:'#295BCB',edge:'#172562',accent:'#ED67D2'},4.6,200,380),
 define(CORE_VFX_IDS[1],CORE_VFX_IDS[1],'Gale Palm','forward-wave',{core:'#67EDBD',body:'#168EAF',edge:'#083E64',accent:'#FFBB55'},6.2,200,380),
 define(CORE_VFX_IDS[2],CORE_VFX_IDS[2],'Void Rift','rune-circle',{core:'#9E6BE4',body:'#56228E',edge:'#190A36',accent:'#35DCCF'},2.7,900,1080),
]);
const draftTemplates={h02_rimeshard_nova:'xs_bladeward_nova@crystal',h02_hoarfrost_gale:'xs_gale_palm@frost',h02_starless_hollow:CORE_VFX_IDS[2],h02_star_lance:'hero02_prior_lance',h02_moonveil_ward:'hero02_prior_aegis',h02_celestial_orrery:'hero02_prior_orrery'};
export const PHYSICAL_VFX_TEMPLATES=Object.freeze([...CORE_VFX_IDS,'xs_bladeward_nova@crystal','xs_gale_palm@frost','hero02_prior_lance','hero02_prior_aegis','hero02_prior_orrery']);
const priorFamilies={anticipation:['prior-anticipation'],core:['prior-core'],secondaries:['prior-secondary'],ground:['prior-ground'],after:['prior-after']};
export const WITCH_VFX_DEFINITIONS=deepFreeze(hero02Draft.skills.map(skill=>{
 const template=draftTemplates[skill.id],coreHeight={h02_rimeshard_nova:2.6,h02_hoarfrost_gale:1.6,h02_starless_hollow:2.7,h02_star_lance:2.6,h02_moonveil_ward:2.4,h02_celestial_orrery:6}[skill.id];
 const family=layers[template.split('@')[0]]??priorFamilies,roleName={anticipation:'anticipation',core:'core',secondary:'secondaries',ground:'ground',after:'after',light:'light',distortion:'distortion'};
 const draftRules=Object.fromEntries(skill.vfx.layers.map(layer=>[roleName[layer.role],{minTier:layer.min_tier,mediumScale:layer.medium_scale??(layer.role==='secondary'?.5:1),kit:layer.kit.slice()}]));
 const requiredCore={h02_rimeshard_nova:['vfx_crystal_shard'],h02_hoarfrost_gale:['vfx_hex_sigil'],h02_starless_hollow:[],h02_star_lance:[],h02_moonveil_ward:[],h02_celestial_orrery:[]}[skill.id];
 return {id:skill.id,hero:'h02',template,name:skill.name.en,visualOnly:true,telegraphShape:skill.telegraph.kind,palette:skill.palette,coreHeight,peakHoldMs:[skill.timing.release_ms,skill.timing.release_ms+180],layers:family,captureMs:skill.captureMs,
 targets:{screenCoverage:[skill.vfx.peak_coverage_pct/100,skill.vfx.peak_coverage_pct/100],ultimateCoverage:[.35,.5],colourfulnessM:45,peakHoldRangeMs:[120,250],coverageDecision:skill.id==='h02_moonveil_ward'?'D4_OPEN_12_PERCENT_PROPOSAL':'DESIGN_TARGET_PENDING_NATIVE'},draftRules,requiredCore,
 draftTiming:skill.timing,kitReferences:[...new Set(skill.vfx.layers.flatMap(layer=>layer.kit))],renderStatus:requiredCore.length?'ITERATE_MISSING_EXACT_CORE':'ITERATE_PRIOR_OR_TEMPLATE_PREVIEW',decisionStatus:'D1_D8_OPEN_NO_GAMEPLAY',status:'DESIGN_DRAFT_VISUAL_ONLY'};
}));
export const HERO02_DRAFT_INFO=deepFreeze({source:hero02Draft.source,sha256:hero02Draft.source_sha256,plannedKitCount:hero02Draft.kit_count,decisions:'D1_D8_OPEN',priorArt:hero02Draft.prior_art});
export function resolveVfxDefinition(id){return WITCH_VFX_DEFINITIONS.find(value=>value.id===id)??LEGACY_SAMPLE_DEFINITIONS.find(value=>value.id===id)??null;}
export function auditDraftKit(available){const known=new Set(hero02Draft.kit.map(row=>row.id)),ready=new Set(available);return {plannedCount:known.size,skills:WITCH_VFX_DEFINITIONS.map(def=>({id:def.id,unknown:def.kitReferences.filter(id=>!known.has(id)),missing:def.kitReferences.filter(id=>!ready.has(id)),renderStatus:def.renderStatus,clip:def.draftTiming.clip,clipStatus:'ITERATE_MAGE_CLIP_NOT_ADMITTED'}))};}
export function resolveVfxTier(value){return value==='low'?'low':value==='medium'?'medium':value==='ultra'||value==='epic'?'ultra':'high';}
export function draftLayerRule(definition,name){
 const declared=Object.entries(definition.layers).find(([,names])=>names.includes(name))?.[0];let role=declared;
 if(!role){if(name.startsWith('prior-'))role=name.slice(6)==='secondary'?'secondaries':name.slice(6);
 else if(/^nova-/.test(name))role=/motes|ring$/.test(name)?'anticipation':/blades/.test(name)?'core':/arcs|shards|dust|impacts/.test(name)?'secondaries':/mist/.test(name)?'after':'ground';
 else if(/^gale-/.test(name))role=/charge|sparks|core/.test(name)?'anticipation':/sigil|cone/.test(name)?'core':/trails|streaks/.test(name)?'secondaries':/vortex|flash|ring-burst/.test(name)?'ground':'after';
 else if(/^rift-/.test(name))role=/outer|inner|rim-motes/.test(name)?'anticipation':/motes|impacts/.test(name)?'secondaries':/scorch|implosion|burst|arcs/.test(name)?'ground':/debris/.test(name)?'after':'core';}
 return definition.draftRules?.[role]??null;
}
export function validateVfxDefinition(value){
 if(!value||typeof value!=='object'||!resolveVfxDefinition(value.id)||!PHYSICAL_VFX_TEMPLATES.includes(value.template)||value.visualOnly!==true)throw new TypeError('Unknown or non-visual effect definition');
 if(['damage','cooldown','reward','cost','buff','hitCount'].some(key=>key in value))throw new TypeError('Gameplay fields cannot enter visual definitions');
 const fields=['id','hero','template','name','visualOnly','telegraphShape','palette','coreHeight','peakHoldMs','layers','captureMs','targets','status','draftRules','requiredCore','draftTiming','kitReferences','renderStatus','decisionStatus'];if(Object.keys(value).some(key=>!fields.includes(key))||!['h02','witch02'].includes(value.hero)||!['circle','forward-wave','rune-circle','double-ring','star','six-segment-ring','AREA_CIRCLE','AREA_LANE','SAFE_BRACKET','HEAVY_CIRCLE'].includes(value.telegraphShape))throw new TypeError('Unknown visual schema field or shape');
 if(!Number.isFinite(value.coreHeight)||value.coreHeight<=0||value.coreHeight>8||!Array.isArray(value.peakHoldMs)||value.peakHoldMs.length!==2||value.peakHoldMs[1]-value.peakHoldMs[0]<120||value.peakHoldMs[1]-value.peakHoldMs[0]>250)throw new TypeError('Invalid core size or peak hold');
 if(!value.palette||Object.values(value.palette).some(colour=>typeof colour!=='string'||!/^#[0-9a-f]{6}$/i.test(colour)))throw new TypeError('Invalid bounded effect palette');
 for(const key of ['anticipation','core','secondaries','ground','after'])if(!Array.isArray(value.layers?.[key])||value.layers[key].length<1||value.layers[key].length>4)throw new TypeError('Missing or unbounded effect layer family');
 if(!Array.isArray(value.captureMs)||value.captureMs.length!==8||value.captureMs.some((ms,index)=>!Number.isInteger(ms)||ms<0||ms>6000||index>0&&ms<=value.captureMs[index-1]))throw new TypeError('Invalid eight-frame timeline');
 return value;
}
/** Conservative submission estimate includes explicit glow extraction; native counters still decide acceptance. */
export function selectVfxLayers(definition,tier,items){
 validateVfxDefinition(definition);const budget=VFX_TIER_BUDGETS[resolveVfxTier(tier)];
 if(!Array.isArray(items)||items.length>32||new Set(items.map(item=>item.name)).size!==items.length||items.some(item=>typeof item.active!=='boolean'||!Number.isInteger(item.draws)||item.draws<0||item.draws>16||!Number.isFinite(item.particles??0)||(item.particles??0)<0))throw new RangeError('Invalid bounded VFX layer roster');
 const essential=new Set([...definition.layers.anticipation,...definition.layers.core,...definition.layers.ground]);
 const priority=item=>essential.has(item.name)?0:definition.layers.secondaries.includes(item.name)?1:definition.layers.after.includes(item.name)?2:3;
 const selected=[];let draws=0,particles=0;
 for(const item of items.slice().sort((a,b)=>priority(a)-priority(b))){if(!item.active)continue;const d=item.draws+(tier==='low'?0:item.glowDraws??0),p=item.particles??0;
  const rule=draftLayerRule(definition,item.name);const levels={low:0,medium:1,high:2,epic:3,ultra:3};if(rule&&levels[resolveVfxTier(tier)]<levels[rule.minTier])continue;
  if(draws+d<=budget.draws&&particles+p<=budget.particles){selected.push(item.name);draws+=d;particles+=p;}
 }
 return {selected,draws,particles,budget,essentialMissing:items.filter(item=>{const rule=draftLayerRule(definition,item.name);return item.active&&essential.has(item.name)&&!selected.includes(item.name)&&(!rule||rule.minTier==='low');}).map(item=>item.name)};
}
/** Matched-background changed-pixel mask inside a supplied ROI; never reports background-green colourfulness as FX. */
export function measureVfxRoi(rgba,background,width,height,roi){
 if(!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0||width*height>4096*2160||rgba.length!==width*height*4||background.length!==rgba.length)throw new RangeError('Invalid paired FX raster');
 if(!roi||![roi.x,roi.y,roi.width,roi.height].every(Number.isInteger)||roi.width<=0||roi.height<=0||roi.x<0||roi.y<0||roi.x+roi.width>width||roi.y+roi.height>height)throw new RangeError('Invalid FX ROI');
 let count=0,rg=0,yb=0,rg2=0,yb2=0,white=0;
 for(let y=roi.y;y<roi.y+roi.height;y++)for(let x=roi.x;x<roi.x+roi.width;x++){const i=(y*width+x)*4;if(rgba[i+3]<16||Math.abs(rgba[i]-background[i])+Math.abs(rgba[i+1]-background[i+1])+Math.abs(rgba[i+2]-background[i+2])<32)continue;
  const r=rgba[i]-rgba[i+1],b=(rgba[i]+rgba[i+1])*.5-rgba[i+2];rg+=r;yb+=b;rg2+=r*r;yb2+=b*b;count++;if(Math.min(rgba[i],rgba[i+1],rgba[i+2])>=250)white++;
 }
 const m=count?Math.sqrt(Math.max(0,rg2/count-(rg/count)**2)+Math.max(0,yb2/count-(yb/count)**2))+.3*Math.hypot(rg/count,yb/count):null;
 return {changedPixels:count,screenCoverage:count/(width*height),colourfulnessM:m,whiteClipFraction:count?white/count:null,basis:'Paired-baseline difference in supplied ROI; moving scenery may contaminate, not object-ID isolation'};
}
export const PORTAL_VFX_STATES=deepFreeze({dormant:{visibleAt:'night',burstMs:0},awakening:{visibleAt:'engaged-nearby',burstMs:0},active:{visibleAt:'always',burstMs:600},locked:{visibleAt:'never',burstMs:0}});
