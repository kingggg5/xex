import test from 'node:test';
import assert from 'node:assert/strict';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer.js';
import '@babylonjs/core/Buffers/buffer.align.js'; // Same registration as the installed classic WebGPUEngine.
import { Matrix } from '@babylonjs/core/Maths/math.vector.js';
import '@babylonjs/core/Meshes/thinInstanceMesh.js';
import { WebGPUCacheRenderPipeline } from '@babylonjs/core/Engines/WebGPU/webgpuCacheRenderPipeline.js';
import { packDressingVertexBuffers } from '../src/dressing-vertex-packing.mjs';

const kinds = ['position', 'normal', 'uv', 'color'];
function fixture(run) {
  const engine = new NullEngine(), scene = new Scene(engine), released = new Map();
  // NullEngine uses the real classic reference-count release path, with a no-op native delete.
  const deleteBuffer = engine._deleteBuffer.bind(engine);
  engine._deleteBuffer = buffer => { released.set(buffer, (released.get(buffer) ?? 0) + 1); deleteBuffer(buffer); };
  try { run(scene, released); } finally { scene.dispose(); engine.dispose(); }
}
function mesh(scene, colorSize = 3, uv = true) {
  const m = new Mesh('dressing', scene);
  m.setVerticesData('position', new Float32Array([0,0,0, 1,0,0, 1,1,0, 0,1,0]), false, 3);
  m.setVerticesData('normal', new Float32Array([0,0,1, .25,.5,.75, 1,0,0, 0,2,0]), false, 3);
  if (uv) m.setVerticesData('uv', new Float32Array([0,0, 1,0, 1,1, 0,1]), false, 2);
  m.setVerticesData('color', new Float32Array(Array.from({ length: 4 * colorSize }, (_, i) => (i % 5) * .125)), false, colorSize);
  m.setIndices([0,1,2,0,2,3]); m.hasVertexAlpha = colorSize === 4;
  return m;
}
const values = m => Object.fromEntries(kinds.filter(k => m.getVertexBuffer(k)).map(k => [k, Array.from(m.getVerticesData(k))]));
const identities = n => { const data = new Float32Array(n * 16); for (let i=0;i<n;i++) Matrix.Identity().copyToArray(data,i*16); return data; };

test('actual Mesh RGB/RGBA packing preserves every value, count, alpha flag and owning reference', () => fixture((scene, released) => {
  for (const size of [3,4]) {
    const m=mesh(scene,size), before=values(m), old=kinds.map(k=>m.getVertexBuffer(k).getBuffer());
    const report=packDressingVertexBuffers(m), wrapper=m.getVertexBuffer('normal').getWrapperBuffer(), allocation=wrapper.getBuffer();
    assert.equal(report.colorSize,size); assert.equal(report.strideFloats,8+size); assert.equal(m.getTotalVertices(),4);
    assert.deepEqual(values(m),before); assert.equal(m.hasVertexAlpha,size===4);
    for(const kind of kinds) assert.equal(m.getVertexBuffer(kind).getWrapperBuffer(),wrapper);
    assert.equal(allocation.references,4); for(const buffer of old){assert.equal(buffer.references,0);assert.equal(released.get(buffer),1);}
    m.dispose(); assert.equal(allocation.references,0); assert.equal(released.get(allocation),1); assert.equal(wrapper.isDisposed,true);
  }
}));

test('normalized interleaved Uint8/Uint16 RGB/RGBA preserves semantic float readback and ownership', () => fixture((scene,released) => {
  for(const [ArrayType,type,max] of [[Uint8Array,VertexBuffer.UNSIGNED_BYTE,255],[Uint16Array,VertexBuffer.UNSIGNED_SHORT,65535]]) for(const colorSize of [3,4]) {
    const m=mesh(scene,colorSize), elementStride=2+colorSize+1, data=new ArrayType(4*elementStride).fill(17);
    const pattern=[0,max,Math.floor(max*.5),Math.floor(max*.25)], expected=[];
    for(let vertex=0;vertex<4;vertex++) for(let component=0;component<colorSize;component++) {
      const value=pattern[(vertex+component)%pattern.length];data[vertex*elementStride+2+component]=value;
      expected.push(Math.fround(value/max));
    }
    m.setVerticesBuffer(new VertexBuffer(scene.getEngine(),data,'color',{
      type,normalized:true,size:colorSize,useBytes:true,
      stride:elementStride*ArrayType.BYTES_PER_ELEMENT,offset:2*ArrayType.BYTES_PER_ELEMENT,
      takeBufferOwnership:true,
    }));
    const before=values(m), old=m.getVertexBuffer('color').getBuffer(), rawCopy=Array.from(data), alpha=m.hasVertexAlpha;
    assert.deepEqual(before.color,expected);
    const report=packDressingVertexBuffers(m), allocation=m.getVertexBuffer('color').getBuffer();
    assert.equal(report.colorSize,colorSize);assert.equal(m.getTotalVertices(),4);assert.equal(m.hasVertexAlpha,alpha);
    assert.deepEqual(values(m),before);assert.deepEqual(Array.from(data),rawCopy);
    assert.equal(m.getVertexBuffer('color').type,VertexBuffer.FLOAT);assert.equal(m.getVertexBuffer('color').normalized,false);
    assert.equal(allocation,m.getVertexBuffer('normal').getBuffer());assert.equal(allocation.references,4);
    assert.equal(old.references,0);assert.equal(released.get(old),1);
    m.dispose();assert.equal(allocation.references,0);assert.equal(released.get(allocation),1);
  }
}));

test('Geometry.copy deinterleaves; unique clone repacking and distinct instance capacities remain isolated', () => fixture((scene,released) => {
  const source=mesh(scene,4), expected=values(source); packDressingVertexBuffers(source);
  const sourceAllocation=source.getVertexBuffer('normal').getBuffer(), a=source.clone('a'), b=source.clone('b');
  assert.throws(()=>packDressingVertexBuffers(a),/makeGeometryUnique/);
  a.makeGeometryUnique(); b.makeGeometryUnique();
  assert.notEqual(a.getVertexBuffer('normal').getBuffer(),a.getVertexBuffer('color').getBuffer());
  packDressingVertexBuffers(a); packDressingVertexBuffers(b);
  const aa=a.getVertexBuffer('normal').getBuffer(),ba=b.getVertexBuffer('normal').getBuffer();
  assert.notEqual(aa,ba); assert.notEqual(aa,sourceAllocation);
  a.thinInstanceSetBuffer('matrix',identities(2),16,true); b.thinInstanceSetBuffer('matrix',identities(5),16,true);
  a.thinInstanceSetBuffer('tileFade',new Float32Array(2).fill(1),1,true); b.thinInstanceSetBuffer('tileFade',new Float32Array(5).fill(.5),1,true);
  const aMatrix=a.getVertexBuffer('world0').getBuffer(), bMatrix=b.getVertexBuffer('world0').getBuffer();
  assert.notEqual(aMatrix,bMatrix); assert.equal(a.thinInstanceCount,2); assert.equal(b.thinInstanceCount,5);
  a.dispose(); assert.equal(aa.references,0); assert.equal(released.get(aa),1); assert.equal(aMatrix.references,0);
  assert.equal(ba.references,4); assert.equal(bMatrix.references,1); assert.equal(sourceAllocation.references,4);
  assert.deepEqual(values(b),expected); assert.deepEqual(values(source),expected); assert.equal(b.thinInstanceCount,5);
  b.dispose(); source.dispose(); assert.equal(ba.references,0); assert.equal(sourceAllocation.references,0);
  assert.equal(released.get(ba),1); assert.equal(released.get(sourceAllocation),1);
}));

test('repacking releases the prior owned allocation exactly once and optional UV remains absent', () => fixture((scene,released) => {
  const m=mesh(scene,3,false), expected=values(m); packDressingVertexBuffers(m);
  const previous=m.getVertexBuffer('color').getWrapperBuffer(), old=previous.getBuffer();
  assert.equal(old.references,3); const report=packDressingVertexBuffers(m);
  assert.equal(report.strideFloats,9); assert.deepEqual(report.attributes,['position','normal','color']);
  assert.equal(previous.isDisposed,true); assert.equal(old.references,0); assert.equal(released.get(old),1);
  assert.deepEqual(values(m),expected); assert.equal(m.getVertexBuffer('uv'),undefined);
}));

test('empty/no-colour cases skip; malformed sizes/counts/nonfinite values reject before replacing buffers', () => fixture(scene => {
  const empty=new Mesh('empty',scene); assert.deepEqual(packDressingVertexBuffers(empty),{packed:false,reason:'empty-mesh',vertexCount:0});
  const plain=mesh(scene); plain.removeVerticesData('color'); const normal=plain.getVertexBuffer('normal');
  assert.equal(packDressingVertexBuffers(plain).reason,'no-color'); assert.equal(plain.getVertexBuffer('normal'),normal);
  for(const [kind,data,size,error] of [
    ['color',new Float32Array(8),2,/RGB3 or RGBA4/],
    ['color',new Float32Array(9),3,/count mismatch/],
    ['color',new Float32Array(0),3,/count mismatch/],
    ['normal',new Float32Array(9),3,/count mismatch/],
    ['normal',new Float32Array(15),3,/count mismatch/],
    ['normal',new Float32Array([NaN,...Array(11).fill(0)]),3,/Non-finite/],
    ['color',new Float32Array([Infinity,...Array(11).fill(0)]),3,/Non-finite/],
    ['uv',new Float32Array(6),2,/count mismatch/],
  ]) {
    const m=mesh(scene); m.setVerticesData(kind,data,false,size); const before=kinds.map(k=>m.getVertexBuffer(k));
    assert.throws(()=>packDressingVertexBuffers(m),error); assert.deepEqual(kinds.map(k=>m.getVertexBuffer(k)),before);
  }
  const missing=mesh(scene); missing.removeVerticesData('normal'); assert.throws(()=>packDressingVertexBuffers(missing),/normal attribute/);
}));

// The installed classic WebGPU cache is exercised on CPU. Distinct stand-in native
// resource identities avoid NullEngine's shared null underlyingResource; no GPU is created.
function descriptors(m, names) {
  const buffers=Object.fromEntries(m.getVerticesDataKinds().map(k=>[k,m.getVertexBuffer(k)]));
  for(const buffer of Object.values(buffers)) {
    const allocation=buffer.getBuffer();
    if(!Object.hasOwn(allocation,'underlyingResource'))Object.defineProperty(allocation,'underlyingResource',{value:{id:allocation.uniqueId}});
    buffer._validOffsetRange=buffer.byteOffset+buffer.getSize(true)<=buffer.byteStride;
  }
  const cache=Object.create(WebGPUCacheRenderPipeline.prototype);cache._vertexBuffers=buffers;
  const effect={_pipelineContext:{shaderProcessingContext:{attributeNamesFromEffect:names,attributeLocationsFromEffect:names.map((_,i)=>i)}}};
  return cache._getVertexInputDescriptor(effect);
}

test('installed classic cache counts actual bindings separately from attributes across normal/UV/colour order', () => fixture(scene => {
  const m=mesh(scene);m.thinInstanceSetBuffer('matrix',identities(3),16,true);m.thinInstanceSetBuffer('tileFade',new Float32Array(3).fill(1),1,true);
  const names=['position','normal','uv','color','world0','world1','world2','world3','tileFade'];
  assert.equal(names.length,9);assert.equal(descriptors(m,names).length,6);
  packDressingVertexBuffers(m);const packed=descriptors(m,names);
  assert.equal(packed.length,3);assert.equal(packed[0].attributes.length,4);assert.equal(packed[1].attributes.length,4);
  const copy=m.clone('deinterleaved');copy.makeGeometryUnique();assert.equal(descriptors(copy,names).length,9);
  packDressingVertexBuffers(copy);assert.equal(descriptors(copy,names).length,6);
  assert.ok(descriptors(copy,['position','normal','color','uv','world0','world1','world2','world3','tileFade']).length<=8);
}));
