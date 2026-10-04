import test from'node:test';import assert from'node:assert/strict';import{readFileSync}from'node:fs';
import{dressingCellLods,dressingFocalMinimums,dressingLodRanges}from'../src/sunmeadow-dressing.mjs';
const read=p=>JSON.parse(readFileSync(new URL('../../../'+p,import.meta.url),'utf8'));
test('captured grotto cell reserves the full focal0/1 handover within40k while surrounding detail remainsLOD2',()=>{
 const probe=read('planning/evidence/water-art-pass4b-20261003/r03/lod-allocation-probe.json'),g=read('apps/client/src/assets/world/water-art-pass4b-r03/grotto-manifest.json'),id='water_art_grotto_organic_r03';
 const assets=new Map([['surroundings',{id:'surroundings',lods:probe.sourceLodTriangles.map((tris,l)=>({tris:tris-g.lods[l].triangles}))}],[g.id,{id:g.id,lods:g.lods.map(l=>({tris:l.triangles}))}]]),entries=[{id:'surroundings',asset_id:'surroundings',x:-4,z:-39},{id,asset_id:g.id,x:-4,z:-39}],reserve=new Map([['-1,-1',probe.fixedReserve]]);
 const base=dressingCellLods(entries,assets,40000,reserve);assert.equal(base.get('-1,-1').minimumLod,2);assert.equal(base.get('-1,-1').triangles,25862);
 const focal=dressingFocalMinimums(entries,assets,base,[id],40000);assert.equal(focal.get(id).minimumLod,0);assert.equal(focal.get(id).worstCellTriangles,32664);assert.equal(focal.has('surroundings'),false);assert.equal(base.get('-1,-1').minimumLod,2);
 const ranges=dressingLodRanges(36,{near:36,middle:80,end:240,fade:4},focal.get(id).minimumLod);assert.deepEqual(ranges.map(r=>r.lod),[0,1]);
 assert.equal(probe.sourceLodTriangles[2]-g.lods[2].triangles+probe.fixedReserve+g.lods[0].triangles,30744);
});
test('focal upgrade falls back toLOD1 orLOD2 when the full reservation cannot fit',()=>{
 const id='focal',entries=[{id:'background',asset_id:'background',x:-1,z:-1},{id,asset_id:id,x:-1,z:-1}];
 for(const[background,expected,total]of[[33500,1,36166],[39250,2,39828]]){const assets=new Map([['background',{id:'background',lods:[100000,60000,background].map(tris=>({tris}))}],[id,{id,lods:[5460,1920,578].map(tris=>({tris}))}]]),reserve=new Map([['-1,-1',background===33500?168:0]]),base=dressingCellLods(entries,assets,40000,reserve),focal=dressingFocalMinimums(entries,assets,base,[id]);assert.equal(focal.get(id).minimumLod,expected);assert.equal(focal.get(id).worstCellTriangles,total);assert.ok(total<=40000);}
});
test('disabled focal selection preserves original cell allocation',()=>{const assets=new Map([['one',{id:'one',lods:[100,50,20].map(tris=>({tris}))}]]),entries=[{id:'one',asset_id:'one',x:0,z:0}],base=dressingCellLods(entries,assets);assert.equal(dressingFocalMinimums(entries,assets,base,[]).size,0);assert.equal(base.get('0,0').minimumLod,0);});
test('actual grotto and corrected L2 tripod reserve both detailed handovers and coal within the same40k cell',()=>{
 const probe=read('planning/evidence/water-art-pass4b-20261003/r03/lod-allocation-probe.json'),g=read('apps/client/src/assets/world/water-art-pass4b-r03/grotto-manifest.json');
 const craft=read('assets/models/sunmeadow-props/manifest.json').families.craft,old=craft.find(a=>a.id==='sm_brazier_cresset'),tripod=craft.find(a=>a.id==='sm_brazier_tripod');
 const background={id:'background',lods:probe.sourceLodTriangles.map((tris,lod)=>({tris:tris-g.lods[lod].triangles-old.lods[lod].tris}))};
 const assets=new Map([[background.id,background],[g.id,{id:g.id,lods:g.lods.map(l=>({tris:l.triangles}))}],[tripod.id,tripod]]);
 const entries=[{id:'background',asset_id:background.id,x:-4,z:-39},{id:'water_art_grotto_organic_r03',asset_id:g.id,x:-4,z:-39},{id:'bp1_L2_000',asset_id:tripod.id,x:-3.75,z:-54}];
 const reserve=new Map([['-1,-1',probe.fixedReserve+24+18]]),base=dressingCellLods(entries,assets,40000,reserve);
 assert.equal(base.get('-1,-1').minimumLod,2);assert.equal(base.get('-1,-1').triangles,25916);
 const focal=dressingFocalMinimums(entries,assets,base,['water_art_grotto_organic_r03','bp1_L2_000'],40000);
 assert.equal(focal.get('water_art_grotto_organic_r03').minimumLod,0);assert.equal(focal.get('bp1_L2_000').minimumLod,0);
 assert.equal(focal.get('bp1_L2_000').worstCellTriangles,33066);assert.ok(focal.get('bp1_L2_000').worstCellTriangles<=40000);
});
