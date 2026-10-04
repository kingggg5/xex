import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {compileRules,grassRulesFromLayout,generateTuftPatch,generatePlantBlock,packInstances,resolveGrassTier,grassBands,presence,prefixFraction,lowerBound,governGrass,sampleGround,buildTuftGeometry,buildFlowerGeometry,buildCloverGeometry,polygonSignedDistance} from '../src/grass-placement.mjs';
const read=path=>JSON.parse(fs.readFileSync(new URL(path,import.meta.url)));
const layout=read('../../../planning/levels/sunmeadow-v2-layout.json'),dressing=read('../../../planning/levels/sunmeadow-v3-dressing.json'),monsters=read('../../../planning/levels/sunmeadow-v2-monsters.json'),water=read('../../../planning/evidence/water-20261002/water-derived.json');
const data=grassRulesFromLayout(layout,dressing,monsters,water),rules=compileRules(data);
test('one seed produces byte-identical packed tuft, flower and clover buffers',()=>{
	for(const [i,j]of [[-1,-1],[1,-3],[-3,-5]])for(const list of [()=>generateTuftPatch(rules,i,j),()=>generatePlantBlock(rules,i,j).flowers,()=>generatePlantBlock(rules,i,j).clover]){
		const a=packInstances(list()),b=packInstances(list());assert.deepEqual(Buffer.from(a.matrices.buffer),Buffer.from(b.matrices.buffer));assert.deepEqual(Buffer.from(a.data.buffer),Buffer.from(b.data.buffer));assert.ok(a.count<=1500);for(let k=1;k<a.r.length;k++)assert.ok(a.r[k]>=a.r[k-1]);
	}
});
test('current layout paths, spawn centres, water, city, six metre quiet combat cores and arena are excluded',()=>{
	for(const path of layout.paths)for(const [x,z]of path.points)assert.equal(sampleGround(rules,x,z).keepGrass,0,path.id);
	for(const row of monsters.spawn_rows){const [x,z]=row.home_xz;assert.equal(sampleGround(rules,x,z).keepGrass,0,`spawn ${row.row}`);}
	for(const c of layout.clearings){const [x,z]=c.center_xz;for(const offset of [-5,0,5])assert.equal(sampleGround(rules,x+offset,z).keepGrass,0,c.id);}
	for(const s of water.stream.samples_1m)assert.equal(sampleGround(rules,s.x,s.z).keepGrass,0,'derived stream');
	assert.equal(sampleGround(rules,0,12).keepGrass,0,'city ownership');assert.equal(sampleGround(rules,0,-68).keepGrass,0,'arena');
	for(const lake of water.lakes)if(lake.outline_xz){const [x,z]=lake.outline_xz[0];assert.equal(sampleGround(rules,x,z).keepGrass,0,lake.id);}
});
test('generated tufts never intrude onto authored path cores or feature footprints',()=>{
	for(const [i,j] of [[-1,-1],[-1,-3],[0,-5],[-3,0]])for(const p of generateTuftPatch(rules,i,j)){
		const s=sampleGround(rules,p.x,p.z);assert.ok(s.keepGrass>0);
		for(const o of data.obstacles)if(o.shape==='polygon')assert.ok(polygonSignedDistance(p.x,p.z,o.polygon)>=o.pad);
	}
});
test('tier density ordering, phone Medium ceiling, continuous presence and conservative prefix',()=>{
	const tiers=['low','medium','high','ultra','epic'].map(preset=>resolveGrassTier({preset}));for(let i=1;i<tiers.length;i++)assert.ok(tiers[i].fTier>=tiers[i-1].fTier);
	const mobile=resolveGrassTier({preset:'medium',formFactor:'mobile'});assert.equal(mobile.fTier,.56*.72);assert.ok(mobile.distance<tiers[1].distance);
	const b=grassBands(tiers[2]);assert.equal(presence(.2,0,b),1);assert.equal(presence(.2,100,b),0);assert.equal(presence(.8,0,b),0);
	let last=1;for(let d=0;d<100;d+=.1){const p=presence(.4,d,b);assert.ok(p<=last+1e-8);last=p;if(p>0)assert.ok(.4<prefixFraction(d,b));}
	assert.equal(lowerBound(new Float32Array([.1,.3,.7]),.5),2);
	for(const t of tiers){const zoom=grassBands(t,120);assert.ok(zoom.near<=zoom.mid&&zoom.mid<=zoom.end);assert.equal(prefixFraction(zoom.end+1,zoom),0);assert.equal(presence(0,zoom.end+1,zoom),0);}
	assert.ok(presence(0,b.end-.01,b)<.001,'lowest thinning key also fades to zero before the terminal boundary');
});
test('governor shrinks on overflow and waits two quiet seconds before restoring',()=>{
	let g=governGrass({factor:1,quiet:0},7001,7000,.25);assert.equal(g.factor,.9);for(let n=0;n<7;n++)g=governGrass(g,1000,7000,.25);assert.equal(g.factor,.9);g=governGrass(g,1000,7000,.25);assert.equal(g.factor,1);
});
test('native geometry is rooted, dome normalled and uses only position, normal, uv before instance buffers',()=>{
	for(const g of [buildTuftGeometry(7,3),buildFlowerGeometry(),buildCloverGeometry()]){assert.equal(g.positions.length,g.normals.length);assert.equal(g.uvs.length,g.vertexCount*2);assert.ok(g.triangleCount>0);assert.ok(Math.max(...g.positions.filter((_,i)=>i%3===1))<=1.001);}
});
test('open-meadow blades stay within the latest 0.35–0.9m target',()=>{
	const open=compileRules({schema:'xexoria.grass-rules/1',domain:[0,16,0,16],seed:99});
	const plants=generateTuftPatch(open,0,0);assert.ok(plants.length>100);for(const p of plants)assert.ok(p.height>=.35&&p.height<=.9);
});
