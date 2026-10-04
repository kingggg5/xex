import test from 'node:test';
import assert from 'node:assert/strict';
import {rendererBootPolicy,WEBGPU_FEATURES} from '../src/renderer-boot-policy.mjs';
test('phone defaults to WebGL2, no MSAA and default power; explicit GPU comparison remains possible',()=>{
	const phone=rendererBootPolicy(true);assert.equal(phone.preferWebGpu,false);assert.equal(phone.antialias,false);assert.equal(phone.powerPreference,'default');
	assert.equal(rendererBootPolicy(true,'webgpu').preferWebGpu,true);
	assert.equal(rendererBootPolicy(false,'webgl2').preferWebGpu,false);
	assert.equal(rendererBootPolicy(false).preferWebGpu,true);assert.equal(rendererBootPolicy(false).powerPreference,'high-performance');
});
test('WebGPU requests every reviewed compression/timing feature and maximum supported limits',()=>{
	const first=rendererBootPolicy(false).webGpuOptions;
	assert.equal(first.setMaximumLimits,true);assert.deepEqual(first.deviceDescriptor.requiredFeatures,WEBGPU_FEATURES);
	// Babylon filters a descriptor in-place; that must not alter a future fallback/retry descriptor.
	first.deviceDescriptor.requiredFeatures.pop();assert.equal(rendererBootPolicy(false).webGpuOptions.deviceDescriptor.requiredFeatures.length,9);
});
