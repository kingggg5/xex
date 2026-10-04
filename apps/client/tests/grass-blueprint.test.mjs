import test from'node:test';import assert from'node:assert/strict';import fs from'node:fs';import{createHash}from'node:crypto';
import{grassRulesFromLayout,compileRules,generateTuftPatch,generatePlantBlock,packInstances,patchRange,sampleGround,polygonSignedDistance,buildTuftGeometry,grassCellAllowance,REGION_CAP}from'../src/grass-placement.mjs';
const read=p=>JSON.parse(fs.readFileSync(new URL(p,import.meta.url))),layout=read('../../../planning/levels/sunmeadow-v2-layout.json'),dressing=read('../../../planning/levels/sunmeadow-v3-dressing.json'),monsters=read('../../../planning/levels/sunmeadow-v2-monsters.json'),water=read('../../../planning/evidence/water-20261002/water-derived.json'),blueprint=read('../../../planning/levels/sunmeadow-blueprint-v1.json');
const data=grassRulesFromLayout(layout,dressing,monsters,water,blueprint),rules=compileRules(data),inside=p=>p.x>=data.domain[0]&&p.x<data.domain[1]&&p.z>=data.domain[2]&&p.z<data.domain[3];
const range=patchRange(data.domain),tufts=[];for(let j=range.j0;j<=range.j1;j++)for(let i=range.i0;i<=range.i1;i++)tufts.push(...generateTuftPatch(rules,i,j).filter(inside));
const blocks=patchRange(data.domain,32),flowers=[];for(let j=blocks.j0;j<=blocks.j1;j++)for(let i=blocks.i0;i<=blocks.i1;i++)flowers.push(...generatePlantBlock(rules,i,j).flowers.filter(inside));
test('G1 geometry has six curved two-segment fans and all three height families are generated',()=>{
 const geometry=buildTuftGeometry(7,6);assert.equal(geometry.fanCount,6);assert.equal(geometry.segmentsPerFan,2);assert.equal(geometry.quads,12);assert.equal(geometry.triangleCount,24);assert.ok(tufts.length>1000&&tufts.length<=REGION_CAP);for(const c of['S','M','T'])assert.ok(tufts.some(p=>p.heightClass===c),c);
});
test('G2 four explicit drifts derive their source regions and retain all intended flower families',()=>{
 assert.equal(data.flowerSites.length,4);for(const site of data.flowerSites){assert.equal(sampleGround(rules,site.x,site.z).zone,site.zoneId);assert.ok(sampleGround(rules,site.x,site.z).keepPlants>0);assert.ok(flowers.some(p=>sampleGround(rules,p.x,p.z).zone===site.zoneId),site.id);}
 for(const col of[0,1,2,3,7])assert.ok(flowers.some(p=>p.col===col),`family ${col}`);
});
test('all generated roots respect footprint, water, paths, spawn, quiet cores, arena and unsupported T1 exclusions',()=>{
 const hill=blueprint.items.find(x=>x.id==='T1');let conflicts=0;
 for(const p of[...tufts,...flowers]){const sample=sampleGround(rules,p.x,p.z);if(p.kind==='tuft'?sample.keepGrass<=0:sample.keepPlants<=0)conflicts++;assert.equal(p.y,0);assert.ok(polygonSignedDistance(p.x,p.z,hill.poly)>=.6);assert.ok(Math.hypot(p.x-blueprint.boss.at[0],p.z-blueprint.boss.at[1])>=12.1);}
 assert.equal(conflicts,0);for(const c of layout.clearings)for(const a of[0,1,2,3,4,5])assert.equal(sampleGround(rules,c.center_xz[0]+a,c.center_xz[1]).keepGrass,0);
 for(const body of water.lakes.filter(b=>b.blueprint_id)){assert.equal(sampleGround(rules,...body.center_xz).keepGrass,0);for(const [x,z]of body.outline_xz)assert.equal(sampleGround(rules,x,z).keepGrass,0);}
});
test('G3 dry supported ring, G4 reeds and G5 short quiet rules are present without elevated roots',()=>{
 assert.ok(data.zones.some(z=>z.id==='G3-east-supported-toe'&&z.spec.tipHex==='#b59a4e'&&z.spec.maxHeight<=.45));assert.ok(tufts.some(p=>p.heightClass==='R'));assert.ok(data.zones.some(z=>z.id==='G5-hunter-short'&&z.spec.maxHeight<=.25));
 assert.ok(tufts.some(p=>sampleGround(rules,p.x,p.z).zone==='G2-knoll-supported-bank-drift'));
});
test('blueprint buffers remain byte deterministic and cell admission cannot add triangles over either limit',()=>{
 for(const [i,j]of [[0,-1],[1,-3],[-2,-5]]){const a=packInstances(generateTuftPatch(rules,i,j)),b=packInstances(generateTuftPatch(rules,i,j));assert.deepEqual(Buffer.from(a.matrices.buffer),Buffer.from(b.matrices.buffer));assert.deepEqual(Buffer.from(a.data.buffer),Buffer.from(b.data.buffer));}
 for(const limit of[40000,120000])for(const base of[0,2000,39000,110000,125000])for(const used of[0,240,6000]){const n=grassCellAllowance(base,used,24,limit);assert.ok(n>=0);if(base+used<=limit)assert.ok(base+used+n*24<=limit);else assert.equal(n,0);}
});
test('blueprint off reproduces original golden packed baseline and ignores blueprint water bodies',()=>{
 const legacy={...water,lakes:water.lakes.filter(b=>!b.blueprint_id&&!b.id.startsWith('blueprint_'))};assert.deepEqual(grassRulesFromLayout(layout,dressing,monsters,water),grassRulesFromLayout(layout,dressing,monsters,legacy));
 const fixture={version:'v3-features',features:[],landmarks:[],clearings:[],vegetation_zones:[],paths:[]},baseline=grassRulesFromLayout(fixture),packed=packInstances(generateTuftPatch(compileRules(baseline),0,-1));assert.equal(packed.count,1179);
 assert.equal(createHash('sha256').update(Buffer.from(packed.matrices.buffer)).digest('hex'),'51081187fd461997bdeb1d20b9cb0e77f1705eb1bdb62ac3724fbca508b90891');assert.equal(createHash('sha256').update(Buffer.from(packed.data.buffer)).digest('hex'),'5e4a46696c430d711b14950f36c445b47d20329421332199ecec1da9b80a7df2');
});
