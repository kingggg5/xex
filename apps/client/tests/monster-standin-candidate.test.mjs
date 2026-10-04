import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {sampleMonsterStandinPose} from '../src/monster-standin-motion-policy.mjs';

const here=path.dirname(fileURLToPath(import.meta.url)),project=path.resolve(here,'../../..');
const candidate=path.join(project,'assets/models/monster-standins-candidate/r01');
const require=createRequire(path.join(here,'../package.json'));
const validator=require('gltf-validator');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');

test('four CC0 source creatures validate, match admitted hashes, and remain within interim budgets',async()=>{
	const receipt=JSON.parse(await fs.readFile(path.join(candidate,'monster-standin-receipt.json'),'utf8'));
	assert.deepEqual(receipt.species.map(s=>s.kind),[1,2,3,4]);
	assert.deepEqual(receipt.species.map(s=>s.model),['Slime','Tree','Pig','Ghost']);
	const geometryHashes=[];
	for(const spec of receipt.species){
		const bytes=await fs.readFile(path.join(candidate,spec.runtime));
		const report=await validator.validateBytes(new Uint8Array(bytes),{maxIssues:12});
		assert.equal(report.issues.numErrors,0,JSON.stringify(report.issues.messages));
		assert.equal(sha(bytes),spec.runtimeSha256);
		assert.equal(sha(await fs.readFile(path.join(project,'apps/client/src/assets/models/monster-standins-r01',spec.species+'.glb'))),spec.runtimeSha256);
		assert.equal(sha(await fs.readFile(path.join(candidate,spec.source))),spec.sourceObjSha256);
		assert.ok(spec.triangles<=1600);assert.ok(spec.draws<=2);assert.ok(spec.bytes<300000);
		assert.equal(spec.normalizedBounds.min[1],0);assert.ok(Math.abs(spec.normalizedBounds.max[1]-spec.heightM)<1e-6);
		assert.equal(spec.runtimeFacing,'+Z');geometryHashes.push(spec.sourceObjSha256);
		if(spec.licenceFile){const text=await fs.readFile(path.join(candidate,spec.licenceFile),'utf8');assert.match(text,/CC0 1\.0 Universal/);}
		else assert.equal(spec.insideLicenceFile,'ABSENT');
	}
	assert.equal(new Set(geometryHashes).size,4,'species cannot be recoloured copies');
	const archive=await fs.readFile(path.join(candidate,'source/author-monsters-2020/cute_animated_monsters_-_aug_2020.zip'));
	assert.equal(sha(archive),'844824c04936a9af954ee82011f98ad8c14ba291a20a0dd0b83c172764ba0eb2');
	const page=await fs.readFile(path.join(candidate,'source/author-monsters-2020/primary-author-page.html'),'utf8');
	assert.match(page,/dcterms\.creator" content="quaternius"/);assert.match(page,/creativecommons\.org\/publicdomain\/zero\/1\.0/);assert.match(page,/cute_animated_monsters_-_aug_2020\.zip/);
});

test('shared-clock cosmetic motion preserves quadruped proportions and inputs',()=>{
	const snapshot={id:101,kind:3,x:4,z:-28,hp:130,max_hp:130};const before=structuredClone(snapshot);
	for(const kind of [1,2,3,4])for(const phase of ['idle','windup','leap','impact','recovery']){
		const pose=sampleMonsterStandinPose(kind,phase,20000,snapshot.id);
		assert.ok(pose.y>=0);assert.ok(pose.scale.every(n=>Number.isFinite(n)&&n>0));
		if(kind!==1)assert.deepEqual(pose.scale,[1,1,1]);
	}
	assert.deepEqual(snapshot,before);assert.throws(()=>sampleMonsterStandinPose(999),/No CC0 interim/);
	assert.throws(()=>sampleMonsterStandinPose(1,'none'),/Unknown monster phase/);
	assert.equal(sampleMonsterStandinPose(4,'idle',9000,1,true).y,.35);
	assert.deepEqual(sampleMonsterStandinPose(3,'idle',9000,1,true),{scale:[1,1,1],y:0,pitch:0,roll:0});
});

test('synchronous factory clones actor materials, shares geometry, and disposes without harming peers',async()=>{
	const ts=require('typescript');let source=await fs.readFile(path.join(here,'../src/monster-standin-renderer.ts'),'utf8');
	source=source.replace(/import (\w+) from '\.\/assets\/[^']+\?url';/g,(_,name)=>`const ${name}='not-loaded-in-cpu-test';`);
	source=source.replace(/from '(@babylonjs\/core\/[^']+)'/g,(_,name)=>`from '${pathToFileURL(path.join(here,'../node_modules',name+'.js')).href}'`);
	source=source.replace("from './monster-standin-motion-policy.mjs'",`from '${pathToFileURL(path.join(here,'../src/monster-standin-motion-policy.mjs')).href}'`);
	source=source.replace("from './monster-ground-contact.mjs'",`from '${pathToFileURL(path.join(here,'../src/monster-ground-contact.mjs')).href}'`);
	const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
	const {createMonsterStandinFactory}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
	const {NullEngine}=await import('@babylonjs/core/Engines/nullEngine.js');
	const {Scene}=await import('@babylonjs/core/scene.js');const {AssetContainer}=await import('@babylonjs/core/assetContainer.js');
	const {Mesh}=await import('@babylonjs/core/Meshes/mesh.js');const {VertexData}=await import('@babylonjs/core/Meshes/mesh.vertexData.js');
	const {StandardMaterial}=await import('@babylonjs/core/Materials/standardMaterial.js');
	const {MultiMaterial}=await import('@babylonjs/core/Materials/multiMaterial.js');
	const engine=new NullEngine();const scene=new Scene(engine);const template=new AssetContainer(scene);
	const mesh=new Mesh('author-template',scene),data=new VertexData();data.positions=[0,0,0,1,0,0,0,1,0];data.indices=[0,1,2];data.normals=[0,0,1,0,0,1,0,0,1];data.applyToMesh(mesh);
	const authorBody=new StandardMaterial('author-body',scene),authorEyes=new StandardMaterial('author-eyes',scene),multi=new MultiMaterial('author-multi',scene);multi.subMaterials.push(authorBody,authorEyes);mesh.material=multi;template.meshes.push(mesh);template.materials.push(authorBody,authorEyes);template.multiMaterials.push(multi);template.rootNodes.push(mesh);template.removeAllFromScene();
	const factory=createMonsterStandinFactory(scene,new Map([[3,template]]));
	const first=factory.create(3,101),second=factory.create(3,102);
	assert.equal(factory.size,2);assert.notEqual(first.material,second.material);assert.notEqual(first.material,mesh.material);
	assert.equal(first.materials.length,2);assert.equal(second.materials.length,2);const secondMulti=second.body.getChildMeshes()[0].material;
	assert.equal(first.body.getChildMeshes()[0].geometry,second.body.getChildMeshes()[0].geometry);
	first.root.position.set(4,7,-28);first.setPhase('leap');first.tick(20000);assert.equal(first.root.position.y,7);assert.equal(first.body.position.y,.55);
	assert.throws(()=>factory.create(99,103),/No preloaded CC0/);
	first.dispose();first.dispose();assert.equal(factory.size,1);assert.equal(second.root.isDisposed(),false);assert.equal(scene.materials.includes(second.material),true);
	factory.dispose();factory.dispose();assert.equal(second.root.isDisposed(),true);assert.equal(scene.multiMaterials.includes(secondMulti),false);assert.equal(factory.size,0);assert.throws(()=>factory.create(3,104),/disposed/);
	scene.dispose();engine.dispose();
});
