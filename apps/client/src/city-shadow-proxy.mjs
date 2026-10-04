// Classic Babylon 9.27.1 adapter. No engine/module imports so a frozen-build
// probe can inject the EXISTING scene's constructors without a second engine.
const MAX_VERTICES = 2_000_000, MAX_INDICES = 9_000_000;
function hashGeometry(positions, normals, indices, ranges) {
  let h = 2166136261; const bytes = new DataView(new ArrayBuffer(4));
  const word = value => { h = Math.imul(h ^ value, 16777619) >>> 0; };
  for (const data of [positions, normals]) for (const value of data) {
    bytes.setFloat32(0, value, true); word(bytes.getUint32(0, true));
  }
  for (const value of indices) word(value);
  for (const r of ranges) { word(r.start); word(r.count); word(r.opaque ? 1 : 0); }
  return h.toString(16).padStart(8, '0');
}

/** Snapshot ONLY actual current prepared geometry; never accepts an asset file. */
export function planCityShadowProxy(source) {
  if (source.isDisposed() || source.skeleton || source.morphTargetManager || source.hasThinInstances || source.instances?.length)
    throw new Error('City shadow proxy requires live static non-instanced geometry');
  const positions = source.getVerticesData('position'), normals = source.getVerticesData('normal'), indices = source.getIndices();
  if (!positions || !normals || !indices || !positions.length || positions.length % 3 || normals.length !== positions.length ||
      positions.length / 3 > MAX_VERTICES || !indices.length || indices.length % 3 || indices.length > MAX_INDICES)
    throw new Error('City shadow proxy geometry is missing, malformed or exceeds bounds');
  for (const data of [positions, normals]) for (const value of data) if (!Number.isFinite(value)) throw new Error('Nonfinite city geometry');
  for (const index of indices) if (!Number.isInteger(index) || index < 0 || index >= positions.length / 3) throw new Error('Invalid city vertex index');
  const ranges = source.subMeshes.map(sub => {
    const material = sub.getMaterial();
    if (!material || !Number.isInteger(sub.indexStart) || !Number.isInteger(sub.indexCount) || sub.indexStart < 0 ||
        sub.indexCount < 0 || sub.indexStart % 3 || sub.indexCount % 3 || sub.indexStart + sub.indexCount > indices.length)
      throw new Error('City shadow proxy submesh/material boundary invalid');
    return { sub, start: sub.indexStart, count: sub.indexCount,
      opaque: material.alpha === 1 && !material.needAlphaBlendingForMesh(source) && !material.needAlphaTestingForMesh(source),
      doubleSided: !material.backFaceCulling, sideOrientation: material.sideOrientation };
  });
  const sorted = ranges.filter(r => r.count).slice().sort((a,b) => a.start - b.start);
  let end = 0;
  for (const r of sorted) { if (r.start !== end) throw new Error('City shadow proxy requires exact nonoverlapping index coverage'); end += r.count; }
  if (end !== indices.length) throw new Error('City shadow proxy index coverage is incomplete');
  const opaque = ranges.filter(r => r.opaque && r.count);
  if (!opaque.length) throw new Error('City shadow proxy has no opaque geometry');
  const orientations = new Set(opaque.map(r => r.sideOrientation));
  if (orientations.size > 1) throw new Error('Mixed opaque material side orientations need separate proxies');
  const output = new Uint32Array(opaque.reduce((n,r) => n+r.count,0)); let cursor = 0;
  for (const r of opaque) { for (let i = r.start; i < r.start+r.count; i++) output[cursor++] = indices[i]; }
  return { positions: new Float32Array(positions), normals: new Float32Array(normals), indices: output,
    opaqueSubMeshes: new Set(opaque.map(r => r.sub)), residualSubMeshes: ranges.filter(r => !r.opaque && r.count).map(r => r.sub),
    backFaceCulling: opaque.every(r => !r.doubleSided), sideOrientation: opaque[0].sideOrientation,
    fingerprint: hashGeometry(positions,normals,indices,ranges),
    diagnostics: { sourceVertices: positions.length/3, sourceTriangles: indices.length/3,
      sourceSubMeshes: ranges.length, opaqueSubMeshes: opaque.length, residualSubMeshes: ranges.filter(r=>!r.opaque&&r.count).length,
      proxyTriangles: output.length/3, proxySubMeshes: 1,
      geometryReduction: 0, objectSizeFilter: 'NOT_APPLIED: material merge has no exact object witnesses',
      distanceLod: 'NOT_APPLIED: exact proxy isolates draw dispatch; native cost/art probe required' } };
}

/** Create disabled, then bind only after source reveal and existing shadow readiness.
 * Dependencies are constructors/factories from the SAME existing Babylon scene.
 * Owns its geometry/material only; source geometry, visibility, materials and textures are borrowed read-only.
 */
export function createCityShadowProxy(source, options) {
  if (source.name !== options.expectedSourceName || !/^[a-f0-9]{64}$/i.test(options.runtimeSha256))
    throw new Error('City shadow proxy source identity is unpinned');
  const plan = planCityShadowProxy(source), scene = source.getScene();
  if (options.expectedGeometryFingerprint && options.expectedGeometryFingerprint !== plan.fingerprint)
    throw new Error('Prepared city geometry fingerprint differs');
  const world = source.computeWorldMatrix(true).clone();
  let mesh, material, disposed = false, sourceDisposedObserver;
  const bindings = new Set();
  try {
    mesh = options.createMesh('reference-city-shadow-proxy',scene);
    material = options.createMaterial('reference-city-shadow-proxy-opaque',scene);
    material.alpha = 1; material.backFaceCulling = plan.backFaceCulling;
    material.sideOrientation = plan.sideOrientation;
    mesh.setVerticesData('position',plan.positions,false,3);
    mesh.setVerticesData('normal',plan.normals,false,3); mesh.setIndices(plan.indices);
    mesh.material = material; mesh.layerMask = 0; mesh.isVisible = true; mesh.visibility = 1;
    mesh.isPickable = false; mesh.checkCollisions = false; mesh.receiveShadows = false;
    mesh.freezeWorldMatrix(world); mesh.setEnabled(false);
    mesh.metadata = { cityShadowOnly: true, runtimeSha256: options.runtimeSha256, preparedGeometryFingerprint: plan.fingerprint };
    if (mesh.subMeshes.length !== 1 || material.needAlphaBlendingForMesh(mesh) || material.needAlphaTestingForMesh(mesh))
      throw new Error('City shadow proxy must have one opaque submesh');
  } catch (error) { mesh?.dispose(false,false); material?.dispose(false,false); throw error; }
  const diagnostics = { ...plan.diagnostics, runtimeSha256: options.runtimeSha256,
    sourceName: source.name, preparedGeometryFingerprint: plan.fingerprint, mainCameraLayerMask: 0,
    backend: scene.getEngine().isWebGPU ? 'WebGPU' : 'WebGL/NullEngine', status: 'PREPARED' };
  const dispose = () => {
    if (disposed) return; disposed = true;
    for (const {generator,map,filter,previous,replaced} of bindings) {
      const list = map.renderList;
      if (Array.isArray(list)) for (let i=list.length-1;i>=0;i--) if (list[i] === mesh) {
        if (replaced && !source.isDisposed() && !list.includes(source)) list.splice(i,1,source); else list.splice(i,1);
      }
      if (generator.customAllowRendering === filter) generator.customAllowRendering = previous;
    }
    bindings.clear(); mesh.setEnabled(false); mesh.dispose(false,false); material.dispose(false,false);
    if (sourceDisposedObserver) source.onDisposeObservable.remove(sourceDisposedObserver);
    diagnostics.status = 'DISPOSED';
  };
  sourceDisposedObserver = source.onDisposeObservable.addOnce(dispose);
  return { mesh, material, diagnostics,
    bind(generator) {
      if (disposed || source.isDisposed() || !source.isVisible || !source.isEnabled()) throw new Error('City shadow proxy source must be revealed and live');
      if (planCityShadowProxy(source).fingerprint !== plan.fingerprint || !source.computeWorldMatrix(true).equals(world))
        throw new Error('Prepared city geometry/world changed before shadow binding');
      const map = generator.getShadowMap();
      if (!map || !Array.isArray(map.renderList) || map.forceLayerMaskCheck) throw new Error('City shadow proxy requires explicit unmasked shadow renderList');
      if ([...bindings].some(b=>b.generator===generator&&b.map===map)) return;
      const list = map.renderList, sourceIndex = list.indexOf(source);
      if (sourceIndex < 0 && !list.includes(mesh)) throw new Error('Actual city is not a registered shadow caster');
      if (sourceIndex >= 0 && list.indexOf(source,sourceIndex+1) >= 0) throw new Error('Duplicate city caster');
      const previous = generator.customAllowRendering;
      const filter = sub => (!disposed && sub.getRenderingMesh() === source && plan.opaqueSubMeshes.has(sub)) ? false
        : typeof previous === 'function' ? previous(sub) : true;
      const replaced = plan.residualSubMeshes.length === 0;
      if (replaced) { if (sourceIndex >= 0) list.splice(sourceIndex,1,mesh); }
      else if (!list.includes(mesh)) list.push(mesh);
      generator.customAllowRendering = filter;
      bindings.add({generator,map,filter,previous,replaced}); mesh.setEnabled(true); diagnostics.status = 'BOUND';
    }, dispose };
}
