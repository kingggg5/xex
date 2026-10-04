import test from 'node:test';
import assert from 'node:assert/strict';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { RawTexture } from '@babylonjs/core/Materials/Textures/rawTexture.js';
import { Color3 } from '@babylonjs/core/Maths/math.color.js';
import { Constants } from '@babylonjs/core/Engines/constants.js';
import { repairStandardLightPool } from '../src/night-pool-render-fix.mjs';

test('real StandardMaterial preserves warm pool color and uses grayscale alpha instead of additive texture RGB',()=>{
 const engine=new NullEngine(),scene=new Scene(engine);
 try{
  const material=new StandardMaterial('look-v2-pool-mat',scene);
  const texture=new RawTexture(new Uint8Array([0,0,0,255]),1,1,Constants.TEXTUREFORMAT_RGBA,scene,false,false);
  texture.name='look-v2-pool-falloff';material.emissiveTexture=texture;
  material.emissiveColor=new Color3(.8,.5,.2);material.alphaMode=Constants.ALPHA_ADD;material.alpha=.18;material.disableLighting=true;
  const color=material.emissiveColor.asArray();
  assert.equal(repairStandardLightPool(material),true);
  assert.equal(material.opacityTexture,texture);assert.equal(texture.getAlphaFromRGB,true);
  assert.equal(material.emissiveTexture,null);assert.equal(material.useEmissiveAsIllumination,true);
  assert.deepEqual(material.emissiveColor.asArray(),color);assert.equal(material.alpha,.18);
  assert.equal(material.alphaMode,Constants.ALPHA_ADD);assert.equal(material.disableLighting,true);
  assert.equal(material.needAlphaBlending(),true);assert.equal(repairStandardLightPool(material),false);
 }finally{scene.dispose();engine.dispose();}
});

test('other emissive materials and an already repaired pool are untouched',()=>{
 const foreign={name:'real-torch',emissiveTexture:{name:'torch'}};
 assert.equal(repairStandardLightPool(foreign),false);assert.equal(foreign.opacityTexture,undefined);
 assert.equal(repairStandardLightPool(null),false);
});
