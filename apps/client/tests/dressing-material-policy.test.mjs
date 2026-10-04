import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import {PBRMaterialDefines} from '@babylonjs/core/Materials/PBR/pbrBaseMaterial.js';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture.js';
import {Constants} from '@babylonjs/core/Engines/constants.js';
import {CreateBox} from '@babylonjs/core/Meshes/Builders/boxBuilder.js';
import {dressingMaterialIdentity,configureDressingOrm} from '../src/dressing-material-policy.mjs';

test('actual manifest stone/ruin atlas identity no longer aliases, while same-atlas props share',async()=>{
	const manifest=JSON.parse(await readFile(new URL('../../../assets/models/sunmeadow-props/manifest.json',import.meta.url),'utf8'));
	const assets=Object.values(manifest.families).flat();
	const stone=assets.find(asset=>asset.textures?.atlas==='sm_stone');
	const ruins=assets.filter(asset=>asset.textures?.atlas==='sm_ruin');
	assert.ok(stone);assert.equal(ruins.length,9);
	for(const ruin of ruins){assert.equal(ruin.family,stone.family);assert.notEqual(dressingMaterialIdentity(ruin),dressingMaterialIdentity(stone));}
	assert.equal(new Set(ruins.map(dressingMaterialIdentity)).size,1);
});

test('missing atlas is rejected except for the explicit legacy CC0 mushroom lookup',()=>{
	assert.throws(()=>dressingMaterialIdentity({family:'stone'}),/atlas required/);
	assert.doesNotThrow(()=>dressingMaterialIdentity({family:'cc0-mushroom'}));
	assert.notEqual(dressingMaterialIdentity({family:'a/b',textures:{atlas:'c'}}),dressingMaterialIdentity({family:'a',textures:{atlas:'b/c'}}));
});

test('real Babylon PBR shader selects ORM green rather than opaque alpha',async()=>{
	const engine=new NullEngine(),scene=new Scene(engine);
	try{
		const mesh=CreateBox('orm-probe',{},scene),material=new PBRMaterial('authored-orm',scene);
		material.metallic=0;material.roughness=.92;
		const texture=new RawTexture(new Uint8Array([170,204,0,255]),1,1,Constants.TEXTUREFORMAT_RGBA,scene,false,false);
		texture.gammaSpace=false;material.metallicTexture=texture;mesh.material=material;
		assert.equal(material.useRoughnessFromMetallicTextureAlpha,true,'installed engine default explains regression');
		configureDressingOrm(material);
		// NullEngine has no native texture readiness; exercise the installed
		// PBR define preparation directly instead of claiming GPU compilation.
		const defines=new PBRMaterialDefines();
		material._prepareDefines(mesh,mesh,defines);
		assert.equal(defines.ROUGHNESSSTOREINMETALMAPALPHA,false);
		assert.equal(defines.ROUGHNESSSTOREINMETALMAPGREEN,true);
		assert.equal(defines.AOSTOREINMETALMAPRED,true);
		assert.equal(defines.METALLNESSSTOREINMETALMAPBLUE,true);
		assert.equal(material.roughness,.92);assert.equal(material.metallic,0);
		assert.equal(material.metallicTexture,texture);assert.equal(texture.gammaSpace,false);
	}finally{scene.dispose();engine.dispose();}
});
