import test from 'node:test';
import assert from 'node:assert/strict';
import {rgbToLab,deltaE00,measureDraftVfxPixels} from '../src/combat-vfx-perceptual.mjs';
test('CIEDE2000 matches published Sharma/Wu/Dalal reference pairs and achromatic edge case',()=>{
 const pairs=[[[50,2.6772,-79.7751],[50,0,-82.7485],2.0425],[[50,0,0],[50,-1,2],2.3669],[[50,2.5,0],[50,0,-2.5],4.3065],[[50,2.5,0],[73,25,-18],27.1492]];
 for(const [a,b,value]of pairs){assert.ok(Math.abs(deltaE00(a,b)-value)<.0001);assert.ok(Math.abs(deltaE00(b,a)-value)<.0001);}
 assert.equal(deltaE00([50,0,0],[50,0,0]),0);assert.ok(Math.abs(rgbToLab(255,255,255)[0]-100)<.001);assert.deepEqual(rgbToLab(0,0,0),[0,0,0]);
});
test('full-frame deltaE00 coverage includes light spill outside ROI, while ROI M excludes green background',()=>{
 const background=new Uint8ClampedArray(64);for(let i=0;i<64;i+=4)background.set([20,180,40,255],i);const data=background.slice(),roi={x:1,y:1,width:2,height:2};
 assert.equal(measureDraftVfxPixels(data,background,4,4,roi).colourfulnessM,null);data.set([220,40,170,255],20);data.set([250,100,20,255],0);
 const value=measureDraftVfxPixels(data,background,4,4,roi);assert.equal(value.changedPixels,2);assert.equal(value.roiChangedPixels,1);assert.equal(value.screenCoverage,2/16);assert.ok(value.colourfulnessM>45);assert.match(value.basis,/CIEDE2000/);
 assert.throws(()=>measureDraftVfxPixels(data,background,4,4,{x:-1,y:0,width:1,height:1}));
});
