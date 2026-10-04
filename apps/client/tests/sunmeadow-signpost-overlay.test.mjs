import test from'node:test';import assert from'node:assert/strict';import{readFileSync}from'node:fs';import{createHash}from'node:crypto';
import{applySemanticDressingOverlay}from'../src/sunmeadow-dressing.mjs';
const read=p=>JSON.parse(readFileSync(new URL('../../../'+p,import.meta.url),'utf8'));
const overlay=read('planning/levels/sunmeadow-st8-posts-v1.json'),root=read('planning/evidence/blueprint-p1-20261003/st8-root-anchors.json');
test('ST8adds fouractualpolepivotposts atrootexactanchors and replacesoverlappingwellonlyinruntime',()=>{
 const p1=read('planning/levels/sunmeadow-v3-dressing-p1.json'),snapshot=JSON.stringify(p1),runtime=applySemanticDressingOverlay(p1,overlay);
 assert.equal(JSON.stringify(p1),snapshot);assert.deepEqual(overlay.entries.map(e=>[e.x,e.z]),root.items.map(i=>i.xz));
 assert.equal(runtime.entries.filter(e=>e.asset_id==='sm_blueprint_signpost').length,4);assert.ok(overlay.entries.every(e=>e.anchor_at_pivot));
 assert.ok(!runtime.entries.some(e=>e.id==='bp1_ST8_000'));assert.ok(p1.entries.some(e=>e.id==='bp1_ST8_000'));
 assert.equal(runtime.blueprint.items.find(i=>i.id==='ST8').status,'ARROW_BODIES_READY_LABELS_MISSING');
 assert.ok(runtime.blueprint.items.find(i=>i.id==='ST8').remaining_components.some(s=>s.includes('labels')));
});
test('frozenP0/P1/P2datasetsretain sealedhashes',()=>{
 const paths=[['planning/levels/sunmeadow-v3-dressing.json','da6bd4a1b034f9a0a9e201065c9d4d1d3f336c9505d002e32a54caadbb44b6ec'],['planning/levels/sunmeadow-v3-dressing-p1.json','eaad30b6debd8e54af905c9d5e8b516cece1d488be9654f0b548fe34ee742550'],['planning/levels/sunmeadow-v3-dressing-p2.json','b1a1fd25383dd9caa5c80cf9c6cfd56b660bf3220e547a88c5c850c6ee508ee8']];
 for(const[p,h]of paths)assert.equal(createHash('sha256').update(readFileSync(new URL('../../../'+p,import.meta.url))).digest('hex'),h);
});
