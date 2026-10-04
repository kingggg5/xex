import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { readGateTreeGeometry } from '../../../planning/evidence/p1-review-20261004/gate-tree/audit-runtime.mjs';
import { GATE_CITY_TREE, GATE_CITY_TREE_PARTS, planGateCityTreeCandidate } from '../src/gate-city-tree-candidate.mjs';
const project = fileURLToPath(new URL('../../../', import.meta.url));
const decoded = readGateTreeGeometry(project+'apps/client/src/assets/models/env_reference_city.glb',true);
const inputs = decoded.primitives.map(p=>({name:p.nodeName,material:p.material,indices:p.indices,gltfPositionAt:i=>p.positions.slice(i*3,i*3+3)}));
const bundle=await build({stdin:{contents:`export {NullEngine} from '@babylonjs/core/Engines/nullEngine';export {Scene} from '@babylonjs/core/scene';export {Mesh} from '@babylonjs/core/Meshes/mesh';export {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData';export {Quaternion} from '@babylonjs/core/Maths/math.vector';export {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';export {prepareGateCityTreeCandidate} from './src/gate-city-tree-runtime';`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));

test('actual active Meshopt primitives remove exactly one tree while preserving all other indices and vertex data',()=>{
	assert.equal(decoded.sha256,GATE_CITY_TREE.runtimeSha256);
	const plan=planGateCityTreeCandidate(inputs,decoded.sha256);
	assert.equal(plan.removedTriangles,1564);assert.equal(plan.patches.length,4);
	for(const patch of plan.patches){const original=inputs.find(p=>p.material===patch.material),spec=GATE_CITY_TREE_PARTS.find(p=>p.material===patch.material);
		const kept=original.indices.filter((_,i)=>!spec.ranges.some(([a,b])=>i>=a&&i<b));
		assert.deepEqual(Array.from(patch.indices),kept);assert.equal(patch.originalIndices,original.indices);
	}
	assert.equal(plan.patches.reduce((s,p)=>s+p.removedTriangles,0),1564);
});
test('hash/count/selected index/AABB/ambiguous material mismatches fail closed before any buffer is changed',()=>{
	const before=inputs.map(p=>p.indices.slice());
	assert.throws(()=>planGateCityTreeCandidate(inputs,'stale-source'),/SHA256/);
	assert.throws(()=>planGateCityTreeCandidate([...inputs,inputs[0]],decoded.sha256),/unique/);
	assert.throws(()=>planGateCityTreeCandidate(inputs.map((p,i)=>i===3?{...p,indices:p.indices.slice(3)}:p),decoded.sha256),/count/);
	assert.throws(()=>planGateCityTreeCandidate(inputs.map((p,i)=>i===0?{...p,gltfPositionAt:k=>{const v=p.gltfPositionAt(k);return [v[0]+1,v[1],v[2]];}}:p),decoded.sha256),/AABB/);
	assert.throws(()=>planGateCityTreeCandidate(inputs.map((p,i)=>i===3?{...p,indices:p.indices.map((v,k)=>k===35190?v+1:v)}:p),decoded.sha256),/hash/);
	inputs.forEach((p,i)=>assert.deepEqual(p.indices,before[i]));
});
test('real NullEngine LH loader orientation passes before merge; a relocated last primitive leaves every mesh intact',()=>{
	const engine=new api.NullEngine(),scene=new api.Scene(engine);
	try{
		const root=new api.Mesh('__root__',scene);root.rotationQuaternion=new api.Quaternion(0,1,0,0);root.scaling.set(1,1,-1);
		const meshes=decoded.primitives.map(p=>{const mesh=new api.Mesh(p.nodeName,scene),data=new api.VertexData();data.positions=p.positions;data.indices=p.indices;data.applyToMesh(mesh);mesh.material=new api.StandardMaterial(p.material,scene);mesh.parent=root;return mesh;});
		const original=meshes.map(m=>Array.from(m.getIndices()));meshes[3].position.x=1;
		assert.throws(()=>api.prepareGateCityTreeCandidate({meshes},decoded.sha256),/AABB/);
		meshes.forEach((m,i)=>assert.deepEqual(Array.from(m.getIndices()),original[i]));meshes[3].position.x=0;
		const result=api.prepareGateCityTreeCandidate({meshes},decoded.sha256);assert.equal(result.removedTriangles,1564);
		assert.equal(meshes.reduce((s,m)=>s+m.getTotalIndices(),0),original.reduce((s,a)=>s+a.length,0)-4692);
		assert.deepEqual(result.placement,GATE_CITY_TREE.placement);
	}finally{scene.dispose();engine.dispose();}
});
test('admitted CC0 conifer fits all ten unchanged collider halfspaces throughout the complete walking body band',()=>{
	const traversal=JSON.parse(fs.readFileSync(project+'assets/models/reference-city/r5/market-repair-candidate/city-traversal-v1.json'));
	const collider=traversal.blockers.find(b=>b.id===GATE_CITY_TREE.id),poly=collider.polygon_xz,p=GATE_CITY_TREE.placement;
	const kit=readGateTreeGeometry(project+'apps/client/src/assets/models/sunmeadow-trees-v4/'+p.species+'_lod0.glb',true,null),bark=kit.primitives.find(p=>p.material.endsWith('_bark'));
	const sign=poly.reduce((s,a,i)=>{const b=poly[(i+1)%poly.length];return s+a[0]*b[1]-b[0]*a[1];},0)>0?1:-1;
	let margin=Infinity,witnesses=0;
	const check=v=>{const x=-v[0]*p.scale+p.x,z=v[2]*p.scale+p.z;for(let i=0;i<poly.length;i++){const a=poly[i],b=poly[(i+1)%poly.length],dx=b[0]-a[0],dz=b[1]-a[1];margin=Math.min(margin,sign*(dx*(z-a[1])-dz*(x-a[0]))/Math.hypot(dx,dz));}witnesses++;};
	for(let i=0;i<bark.indices.length;i+=3){const tri=bark.indices.slice(i,i+3).map(k=>bark.positions.slice(k*3,k*3+3));for(const v of tri)if(v[1]*p.scale>=.05&&v[1]*p.scale<=1.8)check(v);for(let e=0;e<3;e++){const a=tri[e],b=tri[(e+1)%3];for(const y of [.05/p.scale,1.8/p.scale])if((a[1]-y)*(b[1]-y)<0){const w=(y-a[1])/(b[1]-a[1]);check(a.map((v,j)=>v+w*(b[j]-v)));}}}
	assert.equal(witnesses,1536);assert.ok(margin>.012&&margin<.013);
	const top=Math.max(...kit.primitives.flatMap(p=>p.positions.filter((_,i)=>i%3===1)))*p.scale;
	assert.equal(top,8.64);assert.ok(top<GATE_CITY_TREE.oldHeight,'height reduction is explicit');
	assert.equal(collider.y_min,0);assert.equal(collider.y_max,5.86995);
});
