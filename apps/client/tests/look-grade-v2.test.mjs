import assert from 'node:assert/strict';
import {test} from 'node:test';
import {sampleLookGrade, skyCanvasFraction, poolStrength, clusterAnchors, LOOK_POOL} from '../src/look-grade-v2.mjs';
import {lightningFlashEnvelope} from '../src/ambient-storm-lightning-policy.mjs';
const hex=rgb=>'#'+rgb.map(x=>Math.round(x*255).toString(16).padStart(2,'0')).join('');
const luma=([r,g,b])=>.2126*r+.7152*g+.0722*b;
const sat=c=>(Math.max(...c)-Math.min(...c))/Math.max(...c);
test('noon and storm obey the measured palette, with a distinct horizon',()=>{
 const day=sampleLookGrade({hours:12,daylight:1,rain:0});
 assert.equal(hex(day.zenith),'#a5cbfb');
 assert.equal(hex(day.horizon),'#aed3f0','D8 owner horizon colour');
 assert.ok(luma(day.horizon)>luma(day.zenith),'blue horizon remains lighter than zenith');
 assert.ok(sat(day.horizon)>=.25&&sat(day.horizon)<=.30,'horizon retains the specified blue saturation');
 assert.ok(day.fog[2]/day.fog[0]>=1.15&&sat(day.fog)>=.10&&sat(day.fog)<=.30,'blue far fog');
 const storm=sampleLookGrade({hours:12,daylight:1,rain:1});
 assert.equal(hex(storm.zenith),'#2a2438');assert.equal(hex(storm.fog),'#4a4658');
 assert.ok(storm.sunIntensity<day.sunIntensity);
 const dusk=sampleLookGrade({hours:18.5,daylight:.2,rain:0});assert.equal(hex(dusk.zenith),'#bf92ed');
 const night=sampleLookGrade({hours:0,daylight:0,rain:0});assert.ok(sat(night.zenith)>=.35,'night sky reads blue');
});
test('D8 clear-day distance fog preserves far contrast while night and rain remain bounded',()=>{
 const day=sampleLookGrade({hours:12,daylight:1,rain:0}),night=sampleLookGrade({hours:22,daylight:0,rain:0});
 assert.equal(day.fogDensity,.0018);assert.equal(night.fogDensity,.0024);
 const transmission=(density,metres)=>Math.exp(-((density*metres)**2));
 assert.ok(transmission(day.fogDensity,300)>.74,'300m backdrop remains at least74% direct colour');
 assert.ok(transmission(.0034,300)<.36,'old density washed out over64% at300m');
 assert.ok(transmission(day.fogDensity,40)>.99,'near path contrast remains intact');
 assert.ok(sampleLookGrade({hours:12,daylight:1,rain:1}).fogDensity>day.fogDensity,'storm still carries denser fog');
});
test('grade is continuous at midnight and bounded through a complete day/weather cycle',()=>{
 const end=sampleLookGrade({hours:24,daylight:0,rain:0}),start=sampleLookGrade({hours:0,daylight:0,rain:0});
 assert.deepEqual(end,start);
 for(let h=0;h<24;h+=.1)for(const rain of [0,.5,1]){
  const grade=sampleLookGrade({hours:h,daylight:Math.max(0,Math.sin((h-6)*Math.PI/12)),rain});
  for(const key of ['zenith','horizon','fog','sun','fill','ground'])assert.ok(grade[key].every(x=>Number.isFinite(x)&&x>=0&&x<=1));
  assert.ok(grade.exposure<=1.22&&grade.fogDensity>0&&grade.fogDensity<.006);
 }
});
test('sky remap puts the whole gradient in the first 10 degrees and stays monotonic',()=>{
 assert.equal(skyCanvasFraction(90),0);assert.equal(skyCanvasFraction(0),.76);assert.equal(skyCanvasFraction(-90),1);
 assert.ok(Math.abs(skyCanvasFraction(10)-.48)<1e-9);
 for(let e=-90;e<90;e+=1)assert.ok(skyCanvasFraction(e)>=skyCanvasFraction(e+1));
});
test('pools are off by day, full at night, and clusters merge one emitter',()=>{
 assert.equal(poolStrength(1),0);assert.equal(poolStrength(0),1);assert.ok(poolStrength(.2)>0&&poolStrength(.2)<1);
 const anchors=clusterAnchors([[10,1.2,5],[10.3,2.4,5.2],[30,0,0]]);
 assert.equal(anchors.length,2);assert.equal(anchors[0].y,1.2);
 assert.equal(clusterAnchors([[10.2,0,5]],LOOK_POOL.cell,anchors).length,0,'no duplicate pool near an existing one');
 assert.ok(LOOK_POOL.emitterPattern.test('prop-village-lantern-01')&&!LOOK_POOL.emitterPattern.test('env-sky-dome'));
});
test('lightning illumination ends within120ms while the bolt may dissipate longer',()=>{
 assert.ok(lightningFlashEnvelope(35)>.9);
 assert.equal(lightningFlashEnvelope(120),0);assert.equal(lightningFlashEnvelope(200),0);
});
