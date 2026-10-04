import test from 'node:test';
import assert from 'node:assert/strict';
import {sampleEnvironment} from '../src/world-environment-state.mjs';

test('room time gives deterministic day/night values and wraps one full cycle',()=>{
	const start=sampleEnvironment(0);
	assert.deepEqual(sampleEnvironment(0),start);
	assert.equal(sampleEnvironment(2_700_000).hours,start.hours);
	assert.ok(start.daylight>.9);
	assert.ok(sampleEnvironment(1_350_000).daylight<.1);
	for(const time of [-1,0,1000,Number.NaN,1e12]) {
		const value=sampleEnvironment(time);
		assert.ok(Number.isFinite(value.sunIntensity));
		assert.ok(value.hours>=0&&value.hours<24);
		assert.ok(value.direction[1]<0,'night directional illumination must not light the underside of terrain');
	}
});
test('manual weather and frozen daylight remain independent',()=>{
	const dry=sampleEnvironment(1_350_000,{weather:'clear',cycle:false});
	const wet=sampleEnvironment(1_350_000,{weather:'rain',cycle:false});
	assert.equal(dry.hours,wet.hours);
	assert.equal(wet.hours,13.5);
	assert.equal(wet.rain,1);
	assert.ok(wet.windStrength>dry.windStrength);
	assert.ok(wet.fogDensity>dry.fogDensity);
});
