import test from 'node:test';
import assert from 'node:assert/strict';
import {ImageProcessingConfiguration} from '@babylonjs/core/Materials/imageProcessingConfiguration.js';
import {applyWeatherImageProcessing} from '../src/weather-image-processing.mjs';

test('night grade settles once instead of repeatedly invalidating real engine image-processing subscribers',()=>{
 const old=new ImageProcessingConfiguration();let legacyEvents=0;
 old.onUpdateParameters.add(()=>legacyEvents++);
 for(let i=0;i<30;i++){old.exposure=1.22;old.exposure=1.15;}
 assert.equal(legacyEvents,60,'reproduce two updates per weather refresh');
 const config=new ImageProcessingConfiguration();let events=0;config.onUpdateParameters.add(()=>events++);
 const grade={exposure:1.15,contrast:1.08};
 applyWeatherImageProcessing(config,0,grade);const settled=events;
 assert.equal(config.exposure,old.exposure);assert.equal(config.contrast,grade.contrast);
 for(let i=0;i<30;i++)applyWeatherImageProcessing(config,0,grade);
 assert.equal(events,settled,'stationary night must cause no more scene invalidation');
 applyWeatherImageProcessing(config,1,{exposure:1,contrast:1.04});
 assert.equal(events,settled+2,'real exposure and contrast changes still propagate');
});

test('legacy weather keeps its exposure curve and leaves user contrast unchanged',()=>{
 const config=new ImageProcessingConfiguration();config.contrast=1.17;
 applyWeatherImageProcessing(config,0,null);assert.equal(config.exposure,1.22);assert.equal(config.contrast,1.17);
 applyWeatherImageProcessing(config,.5,null);assert.equal(config.exposure,1.11);
 applyWeatherImageProcessing(config,1,null);assert.equal(config.exposure,1);assert.equal(config.contrast,1.17);
});
