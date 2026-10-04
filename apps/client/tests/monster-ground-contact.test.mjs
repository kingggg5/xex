import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {AssetContainer} from '@babylonjs/core/assetContainer.js';
import {LoadAssetContainerAsync} from '@babylonjs/core/Loading/sceneLoader.js';
import '@babylonjs/loaders/glTF/index.js';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode.js';
import {Mesh} from '@babylonjs/core/Meshes/mesh.js';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';
import {Quaternion,Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {createMonsterGroundContact,MAX_MONSTER_CONTACT_VERTICES,MONSTER_ROOT_FLOOR_CLEARANCE_M} from '../src/monster-ground-contact.mjs';
import {sampleMonsterStandinPose} from '../src/monster-standin-motion-policy.mjs';

const here=path.dirname(fileURLToPath(import.meta.url)),require=createRequire(path.join(here,'../package.json'));
const SPECIES=['puddlekin','mossling','thistle_boar','glade_wisp'];
async function actualGlb(name){
	const bytes=await fs.readFile(path.join(here,'../src/assets/models/monster-standins-r01',name+'.glb'));
	const jsonBytes=bytes.readUInt32LE(12),document=JSON.parse(bytes.subarray(20,20+jsonBytes).toString());
	const binary=bytes.subarray(28+jsonBytes,28+jsonBytes+bytes.readUInt32LE(20+jsonBytes));
	return {bytes,document,accessor(index){
		const a=document.accessors[index],v=document.bufferViews[a.bufferView];assert.equal(v.extensions,undefined);
		const size={SCALAR:1,VEC3:3}[a.type],format={5126:['readFloatLE',4],5123:['readUInt16LE',2],5125:['readUInt32LE',4]}[a.componentType];
		assert.ok(size&&format);const offset=(v.byteOffset??0)+(a.byteOffset??0),stride=v.byteStride??size*format[1];
		return Array.from({length:a.count*size},(_,i)=>binary[format[0]](offset+Math.floor(i/size)*stride+i%size*format[1]));
	}};
}
async function actualLoadedTemplate(scene,name){
	const glb=await actualGlb(name),container=await LoadAssetContainerAsync(glb.bytes,scene,{pluginExtension:'.glb',name:name+'.glb',pluginOptions:{gltf:{skipMaterials:true}}});
	// Geometry/importer transforms use the actual loader; only CPU-only test materials
	// replace skipped source materials, so no image decode or GPU job is started.
	for(const mesh of container.meshes)if(mesh.getTotalVertices()>0){mesh.material=new StandardMaterial('cpu-'+mesh.name,scene);container.materials.push(mesh.material);}
	container.removeAllFromScene();return container;
}
async function rendererFactory(){
	let source=await fs.readFile(path.join(here,'../src/monster-standin-renderer.ts'),'utf8');
	source=source.replace(/import (\w+) from '\.\/assets\/[^']+\?url';/g,(_,name)=>`const ${name}='unused-cpu-url';`);
	source=source.replace(/from '(@babylonjs\/core\/[^']+)'/g,(_,name)=>`from '${pathToFileURL(path.join(here,'../node_modules',name+'.js')).href}'`);
	source=source.replace(/from '\.\/(monster-standin-motion-policy|monster-ground-contact)\.mjs'/g,(_,name)=>`from '${pathToFileURL(path.join(here,'../src',name+'.mjs')).href}'`);
	const compiled=require('typescript').transpileModule(source,{compilerOptions:{target:99,module:99}}).outputText;
	return (await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'))).createMonsterStandinFactory;
}
function templateFromGlb(scene,glb){
	const container=new AssetContainer(scene),importRoot=new TransformNode('__root__',scene);
	// Babylon's default glTF LH importer root: rotation pi aboutY, negativeZ scale.
	importRoot.rotationQuaternion=new Quaternion(0,1,0,0);importRoot.scaling.set(1,1,-1);
	const nodes=glb.document.nodes.map((node,i)=>{
		const result=new TransformNode(node.name??`node-${i}`,scene);
		if(node.translation)result.position.copyFromFloats(...node.translation);
		if(node.scale)result.scaling.copyFromFloats(...node.scale);
		if(node.rotation)result.rotationQuaternion=Quaternion.FromArray(node.rotation);
		assert.equal(node.matrix,undefined,'current assets have no matrix node');
		container.transformNodes.push(result);return result;
	});
	for(let i=0;i<nodes.length;i++)for(const child of glb.document.nodes[i].children??[])nodes[child].parent=nodes[i];
	for(let i=0;i<nodes.length;i++){
		if(!nodes[i].parent)nodes[i].parent=importRoot;
		const meshIndex=glb.document.nodes[i].mesh;if(meshIndex===undefined)continue;
		for(const [index,primitive] of glb.document.meshes[meshIndex].primitives.entries()){
			const mesh=new Mesh(`actual-${i}-${index}`,scene),data=new VertexData();mesh.parent=nodes[i];
			data.positions=glb.accessor(primitive.attributes.POSITION);data.normals=glb.accessor(primitive.attributes.NORMAL);data.indices=glb.accessor(primitive.indices);data.applyToMesh(mesh);
			mesh.material=new StandardMaterial(`actual-material-${i}-${index}`,scene);container.materials.push(mesh.material);container.meshes.push(mesh);
		}
	}
	container.transformNodes.push(importRoot);container.rootNodes.push(importRoot);container.removeAllFromScene();return container;
}
function meshWorldMinimumY(body){
	let min=Infinity;
	for(const mesh of body.getChildMeshes()){
		const positions=mesh.getVerticesData('position');if(!positions)continue;const matrix=mesh.computeWorldMatrix(true);
		for(let i=0;i<positions.length;i+=3)min=Math.min(min,Vector3.TransformCoordinates(Vector3.FromArray(positions,i),matrix).y);
	}
	return min;
}

test('actual GLB phase endpoints correct boar contact and preserve air/hover/idle envelopes',async()=>{
	const profiles=[];
	for(let i=0;i<SPECIES.length;i++){
		const kind=i+1,glb=await actualGlb(SPECIES[i]);assert.equal(glb.document.skins?.length??0,0);assert.equal(glb.document.animations?.length??0,0);
		const positions=glb.document.meshes.flatMap(mesh=>mesh.primitives.flatMap(p=>glb.accessor(p.attributes.POSITION)));
		const profile=createMonsterGroundContact(kind,positions);profiles.push(profile);
		assert.ok(profile.idleMinimumY+MONSTER_ROOT_FLOOR_CLEARANCE_M>=-1e-6);
		for(const phase of ['windup','impact','recovery'])assert.ok(profile.phases[phase].minimumY+profile.phases[phase].supportOffset+MONSTER_ROOT_FLOOR_CLEARANCE_M>=-1e-6);
		assert.equal(profile.phases.leap.supportOffset,0);assert.equal(profile.phases.idle.supportOffset,0);
		if(kind!==3)for(const entry of Object.values(profile.phases))assert.equal(entry.supportOffset,0);
	}
	assert.ok(Math.abs(profiles[2].phases.windup.supportOffset-.083902)<1e-6);
	assert.ok(Math.abs(profiles[2].phases.impact.supportOffset-.020828)<1e-6);
	assert.ok(Math.abs(profiles[2].phases.recovery.supportOffset-.000688)<1e-6);
	assert.equal(Object.isFrozen(profiles[2].phases),true);
});

test('factory uses actual ancestor-transformed points once per species and tick does no scans',async()=>{
	const createFactory=await rendererFactory(),engine=new NullEngine(),scene=new Scene(engine),templates=new Map();
	for(let i=0;i<SPECIES.length;i++)templates.set(i+1,await actualLoadedTemplate(scene,SPECIES[i]));
	const factory=createFactory(scene,templates),views=[];
	try{
		for(const kind of [1,2,3,4]){
			const id=100+kind,view=factory.create(kind,id);views.push(view);view.root.position.set(4,7+MONSTER_ROOT_FLOOR_CLEARANCE_M,-28);view.root.rotation.y=.7;
			const meshes=view.body.getChildMeshes(),original=meshes.map(m=>m.getVerticesData);let scans=0;
			meshes.forEach((mesh,i)=>{mesh.getVerticesData=function(...args){scans++;return original[i].apply(this,args);};});
			for(const phase of ['idle','windup','leap','impact','recovery']){
				view.setPhase(phase);view.tick(20000,true);assert.equal(scans,0);
				assert.deepEqual(view.root.position.asArray(),[4,7.015,-28]);assert.equal(view.root.rotation.y,.7);
				const pose=sampleMonsterStandinPose(kind,phase,20000,id,true);assert.deepEqual(view.body.scaling.asArray(),pose.scale);
				if(phase==='leap'||kind===4)assert.equal(view.body.position.y,pose.y);
				meshes.forEach((mesh,i)=>mesh.getVerticesData=original[i]);
				assert.ok(meshWorldMinimumY(view.body)>=7-1e-6,`kind${kind}/${phase} below world floor`);
				meshes.forEach((mesh,i)=>{mesh.getVerticesData=function(...args){scans++;return original[i].apply(this,args);};});
			}
			meshes.forEach((mesh,i)=>mesh.getVerticesData=original[i]);
			for(let step=0;step<100;step++){view.setPhase('idle');view.tick(step*53,false);assert.ok(meshWorldMinimumY(view.body)>=7-1e-6);}
		}
		assert.equal(factory.contactSpeciesCount,4);const peer=factory.create(3,203);views.push(peer);assert.equal(factory.contactSpeciesCount,4);
		factory.dispose();assert.equal(factory.contactSpeciesCount,0);assert.equal(factory.size,0);
	}finally{factory.dispose();scene.dispose();engine.dispose();}
});

test('body-local import transform, including negative determinant and nested node scale, is preserved',async()=>{
	const createFactory=await rendererFactory(),engine=new NullEngine(),scene=new Scene(engine);
	const glb=await actualGlb('thistle_boar'),template=templateFromGlb(scene,glb);
	const authored=template.transformNodes[0];authored.scaling.set(1.3,.75,1.1);authored.position.y=.03;
	const source=template.meshes.flatMap(mesh=>{
		const positions=mesh.getVerticesData('position'),matrix=mesh.computeWorldMatrix(true),out=[];
		for(let i=0;i<positions.length;i+=3)out.push(...Vector3.TransformCoordinates(Vector3.FromArray(positions,i),matrix).asArray());return out;
	});
	const expected=createMonsterGroundContact(3,source),factory=createFactory(scene,new Map([[3,template]]));
	try{
		const view=factory.create(3,501);view.setPhase('windup');view.tick(0,true);
		assert.ok(Math.abs(view.body.position.y-expected.phases.windup.supportOffset)<1e-8);
		assert.ok(Math.abs(meshWorldMinimumY(view.body)+MONSTER_ROOT_FLOOR_CLEARANCE_M)<1e-6);
	}finally{factory.dispose();scene.dispose();engine.dispose();}
});

test('missing or invalid CPU positions fail honestly and failed clones release materials',async()=>{
	assert.throws(()=>createMonsterGroundContact(3,[]),/actual CPU positions/);
	assert.throws(()=>createMonsterGroundContact(3,[0,NaN,0]),/nonfinite/);
	assert.throws(()=>createMonsterGroundContact(3,new Float32Array((MAX_MONSTER_CONTACT_VERTICES+1)*3)),/bounded actual/);
	assert.throws(()=>createMonsterGroundContact(99,[0,0,0]),/Unknown/);
	const createFactory=await rendererFactory(),engine=new NullEngine(),scene=new Scene(engine),template=templateFromGlb(scene,await actualGlb('thistle_boar'));
	const factory=createFactory(scene,new Map([[3,template]])),before={materials:scene.materials.length,meshes:scene.meshes.length,nodes:scene.transformNodes.length};
	const original=Mesh.prototype.getVerticesData;
	try{
		Mesh.prototype.getVerticesData=function(kind,...args){return kind==='position'&&this.name.startsWith('monster-601')?null:original.call(this,kind,...args);};
		assert.throws(()=>factory.create(3,601),/CPU positions unavailable/);assert.equal(factory.contactSpeciesCount,0);assert.equal(factory.size,0);
		assert.deepEqual({materials:scene.materials.length,meshes:scene.meshes.length,nodes:scene.transformNodes.length},before);
	}finally{Mesh.prototype.getVerticesData=original;factory.dispose();scene.dispose();engine.dispose();}
});
