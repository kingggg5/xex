import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { CreateSphere } from '@babylonjs/core/Meshes/Builders/sphereBuilder.js';
import { DynamicTexture } from '@babylonjs/core/Materials/Textures/dynamicTexture.js';
import { Color3 } from '@babylonjs/core/Maths/math.color.js';
import { skyPaletteStops } from '../src/sky-palette-stops.mjs';

// Execute the real appearance method without constructing birds/clouds or a GPU renderer.
const source = readFileSync(new URL('../src/ambient-world.ts', import.meta.url), 'utf8');
const javascript = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  .replace(/(["'])(@babylonjs\/[^"']+)\1/g, (_, quote, spec) => `${quote}${import.meta.resolve(`${spec}.js`)}${quote}`)
  .replace('"./sky-palette-stops.mjs"', JSON.stringify(new URL('../src/sky-palette-stops.mjs', import.meta.url).href));
const { AmbientWorld } = await import(`data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`);
const palette = { zenith: [.1, .2, .3], horizon: [.8, .7, .6] };
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);

function painter() {
  const gradients = [], uploads = [];
  const context = { createLinearGradient() { const stops = []; gradients.push(stops); return { addColorStop(offset, color) { stops.push({ offset, color }); } }; }, fillRect() {} };
  const owner = {
    disposed: false, skyKey: '', zenith: new Color3(), horizon: new Color3(), tint: new Color3(),
    nightZenith: new Color3(.02, .04, .08), middayZenith: new Color3(.2, .4, .6), duskZenith: new Color3(.3, .2, .1),
    nightHorizon: new Color3(.05, .08, .1), middayHorizon: new Color3(.6, .7, .8), warmHorizon: new Color3(.8, .6, .3), duskHorizon: new Color3(.5, .3, .2),
    sky: { getContext: () => context, getSize: () => ({ width: 16, height: 256 }), update: invertY => uploads.push(invertY) },
    cloudMaterial: { emissiveColor: new Color3() }, scene: {}, sun: { position: { set() {} }, setEnabled() {} },
  };
  return { owner, gradients, uploads, paint: sample => AmbientWorld.prototype.appearance.call(owner, { hours: 12, daylight: 1, dawn: 0, cloud: 0, direction: [0, -1, 0], ...sample }) };
}

test('exact R1 stock-UV stops preserve input and blend RGB without changing the grade', () => {
  const before = JSON.stringify(palette), stops = skyPaletteStops(palette.zenith, palette.horizon);
  assert.deepEqual(stops.map(s => s.offset), [0, .39, .444, .483, .5, 1]);
  for (const [index, amount] of [[0, 0], [1, 0], [2, .45], [3, .85], [4, 1], [5, 1]]) {
    stops[index].color.forEach((value, channel) => near(value, palette.zenith[channel] + (palette.horizon[channel] - palette.zenith[channel]) * amount));
  }
  stops[0].color[0] = 99;
  assert.equal(JSON.stringify(palette), before);
});

test('real ambient painter uses new stops, repaints same-hour palette changes and caches identical input', () => {
  const p = painter(); p.paint({ skyPalette: palette });
  assert.deepEqual(p.gradients[0].map(s => s.offset), [0, .39, .444, .483, .5, 1]);
  assert.equal(p.gradients[0][0].color, new Color3(...palette.zenith).toHexString());
  assert.equal(p.gradients[0][4].color, new Color3(...palette.horizon).toHexString());
  assert.notEqual(p.gradients[0][2].color, p.gradients[0][0].color);
  p.paint({ skyPalette: palette }); assert.equal(p.gradients.length, 1);
  p.paint({ skyPalette: { ...palette, horizon: [.9, .8, .7] } }); assert.equal(p.gradients.length, 2);
  assert.deepEqual(p.uploads, [false, false]);
});

test('real ambient painter without a palette retains exact legacy stops and colours', () => {
  const p = painter(); p.paint({});
  assert.deepEqual(p.gradients[0], [
    { offset: 0, color: p.owner.middayZenith.toHexString() }, { offset: .48, color: p.owner.middayZenith.toHexString() },
    { offset: .76, color: p.owner.middayHorizon.toHexString() }, { offset: 1, color: p.owner.middayHorizon.toHexString() },
  ]);
  assert.deepEqual(p.uploads, [false]);
});

test('installed Babylon NullEngine proves backside sphere top V0/horizon V.5 and <=3-degree look rings', () => {
  const engine = new NullEngine(), scene = new Scene(engine);
  try {
    for (const segments of [16, 64]) {
      const sphere = CreateSphere('env-sky-dome', { diameter: 2, segments, sideOrientation: Mesh.BACKSIDE }, scene);
      const positions = sphere.getVerticesData('position'), uvs = sphere.getVerticesData('uv'), rings = new Set();
      for (let i = 0; i < positions.length / 3; i++) {
        const v = uvs[i * 2 + 1]; rings.add(v);
        near(positions[i * 3 + 1], Math.cos(v * Math.PI));
      }
      near(uvs[1], 0); near(positions[1], 1);
      assert.ok([...rings].some(v => Math.abs(v - .5) < 1e-6));
      assert.equal(rings.size, segments + 3);
      if (segments === 64) assert.ok(180 / (rings.size - 1) <= 3);
      sphere.dispose();
    }
    const canvas = { width: 16, height: 256, getContext: () => ({}) };
    const texture = new DynamicTexture('env-sky-texture', canvas, scene, false), uploads = [];
    engine.updateDynamicTexture = (_texture, source, invertY) => uploads.push({ source, invertY });
    texture.update(false); assert.equal(uploads[0].source, canvas); assert.equal(uploads[0].invertY, false);
    texture.dispose();
  } finally { scene.dispose(); engine.dispose(); }
});
