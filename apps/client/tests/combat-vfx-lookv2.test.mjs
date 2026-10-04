import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {WITCH_VFX_DEFINITIONS,CORE_VFX_IDS,VFX_TIER_BUDGETS,HERO02_DRAFT_INFO,auditDraftKit,draftLayerRule,resolveVfxDefinition,validateVfxDefinition,selectVfxLayers,measureVfxRoi,PORTAL_VFX_STATES} from '../src/combat-vfx-lookv2.mjs';
test('six finite visual-only witch definitions share three templates, eight beats and five layer families',()=>{
 assert.equal(WITCH_VFX_DEFINITIONS.length,6);assert.equal(new Set(WITCH_VFX_DEFINITIONS.map(v=>v.template)).size,6);
 assert.ok(WITCH_VFX_DEFINITIONS.every(v=>v.id.startsWith('h02_')&&v.decisionStatus==='D1_D8_OPEN_NO_GAMEPLAY'));
 for(const def of WITCH_VFX_DEFINITIONS){assert.equal(validateVfxDefinition(def),def);assert.equal(def.visualOnly,true);assert.ok(Object.isFrozen(def.palette));assert.equal(def.captureMs.length,8);assert.deepEqual(Object.keys(def.layers),['anticipation','core','secondaries','ground','after']);}
 const def=structuredClone(WITCH_VFX_DEFINITIONS[0]);assert.throws(()=>validateVfxDefinition({...def,damage:100}),/Gameplay/);assert.throws(()=>validateVfxDefinition({...def,sourceUrl:'https://assets.test'}),/schema/);assert.throws(()=>validateVfxDefinition({...def,coreHeight:NaN}));assert.throws(()=>validateVfxDefinition({...def,peakHoldMs:[0,500]}));
});
test('tier selection prioritises truthful shapes, counts extraction separately and caps optional layers/particles',()=>{
 const def=resolveVfxDefinition('xs_bladeward_nova'),items=[{name:'nova-ring',active:true,draws:1},{name:'nova-blades',active:true,draws:1,glowDraws:1},{name:'nova-cracks',active:true,draws:1},{name:'nova-shards',active:true,draws:1,particles:55},{name:'nova-dust',active:true,draws:1,particles:96},{name:'optional-mist',active:true,draws:1,particles:100}];
 for(const tier of ['low','medium','high','ultra']){const result=selectVfxLayers(def,tier,items);assert.ok(result.draws<=VFX_TIER_BUDGETS[tier].draws);assert.ok(result.particles<=VFX_TIER_BUDGETS[tier].particles);assert.deepEqual(result.essentialMissing,[]);assert.ok(result.selected.includes('nova-ring'));assert.ok(result.selected.includes('nova-blades'));}
 const low=selectVfxLayers(def,'low',items);assert.equal(low.particles,55);assert.ok(!low.selected.includes('nova-dust'));assert.throws(()=>selectVfxLayers(def,'low',[...items,items[0]]),/roster/);
 assert.equal(VFX_TIER_BUDGETS.ultra.particles,400);assert.equal(VFX_TIER_BUDGETS.ultra.gpuParticles,2000);
});
test('draft min tier/medium scale and Ward12percent exception remain proposed, kit roster is51',()=>{
 const ward=resolveVfxDefinition('h02_moonveil_ward');assert.deepEqual(ward.targets.screenCoverage,[.12,.12]);assert.match(ward.targets.coverageDecision,/D4_OPEN/);assert.equal(ward.decisionStatus,'D1_D8_OPEN_NO_GAMEPLAY');
 const frost=resolveVfxDefinition('h02_hoarfrost_gale');assert.equal(draftLayerRule(frost,'gale-streaks').mediumScale,.5);assert.equal(draftLayerRule(frost,'gale-funnel').minTier,'medium');
 const low=selectVfxLayers(frost,'low',[{name:'gale-sigil',active:true,draws:1},{name:'gale-core',active:true,draws:1},{name:'gale-streaks',active:true,draws:1,particles:12},{name:'gale-vortex',active:true,draws:1}]);assert.ok(low.selected.includes('gale-sigil'));assert.ok(low.selected.includes('gale-vortex'));assert.ok(!low.selected.includes('gale-core'));assert.ok(!low.selected.includes('gale-streaks'));
 assert.equal(HERO02_DRAFT_INFO.plannedKitCount,51);const audit=auditDraftKit(['vfx_funnel']);assert.equal(audit.plannedCount,51);assert.ok(audit.skills.every(row=>row.unknown.length===0));assert.ok(audit.skills.find(row=>row.id==='h02_hoarfrost_gale').missing.includes('vfx_hex_sigil'));
});
test('ROI colourfulness excludes unchanged green background and detects changed hue/clipping only inside ROI',()=>{
 const background=new Uint8ClampedArray(4*4*4);for(let i=0;i<background.length;i+=4)background.set([20,180,40,255],i);
 const data=background.slice(),roi={x:1,y:1,width:2,height:2};assert.equal(measureVfxRoi(data,background,4,4,roi).colourfulnessM,null);
 for(const [x,y] of [[1,1],[2,1],[1,2],[2,2]])data.set([220,40,170,255],(y*4+x)*4);
 const stats=measureVfxRoi(data,background,4,4,roi);assert.equal(stats.changedPixels,4);assert.equal(stats.screenCoverage,.25);assert.ok(stats.colourfulnessM>=45);assert.equal(stats.whiteClipFraction,0);
 data.set([255,255,255,255],0);assert.equal(measureVfxRoi(data,background,4,4,roi).whiteClipFraction,0);data.set([255,255,255,255],(1*4+1)*4);assert.equal(measureVfxRoi(data,background,4,4,roi).whiteClipFraction,.25);
 assert.throws(()=>measureVfxRoi(data,background,4,4,{x:4,y:4,width:1,height:1}));
});
test('portal state preparation is data only and the kit delegates loader registration without eager glTF import',async()=>{
 assert.equal(PORTAL_VFX_STATES.locked.visibleAt,'never');assert.equal(PORTAL_VFX_STATES.active.burstMs,600);assert.equal(CORE_VFX_IDS.length,3);
 const kit=await readFile(new URL('../src/combat-vfx-kit.ts',import.meta.url),'utf8');assert.doesNotMatch(kit,/import\s+["']@babylonjs\/loaders\/glTF/);assert.match(kit,/ensureAssetLoaders\(\)/);
});
