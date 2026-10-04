import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import { Color3 } from '@babylonjs/core/Maths/math.color.js';

const IDS = new Set(['bp1_L2_000', 'bp1_L2_001']);
const TEXTURE_SLOTS = ['albedoTexture', 'bumpTexture', 'metallicTexture'];
export const L2_TRIPOD_PINS = Object.freeze([
  'b7b4c0d6b7a6f652436a7ca946bd2818d866d7f74e0af96c1bebbc4af20bfae3',
  '08f5f35c68eff05dce2483bd6a6aae558d36612d9591058ac127d4ed285d0dae',
  '6349c273b5e3c7415e1644352700975313b8faed9d3fed546c174d655fe58a67',
]);

/** Runtime candidate only: frozen P1/P2 records and all other entries remain unchanged. */
export function selectL2BrazierEntries(entries, assets) {
  const selected = entries.filter(entry => IDS.has(entry.id));
  if (!selected.length) return [...entries];
  if (selected.length !== 2 || new Set(selected.map(entry => entry.id)).size !== 2) throw new Error('Exact two L2 entries required');
  const asset = assets.get('sm_brazier_tripod');
  if (!asset || asset.lods.length !== 3 || asset.lods.some((lod, i) => lod.sha256 !== L2_TRIPOD_PINS[i] || lod.tris !== [284, 220, 156][i])) throw new Error('Pinned existing tripod required');
  if (asset.bounds.min.some((v, i) => Math.abs(v - [-.3599, -.0062, -.3599][i]) > 1e-5) || asset.bounds.max.some((v, i) => Math.abs(v - [.3766, 1.1, .3599][i]) > 1e-5)) throw new Error('Tripod bounds changed');
  return entries.map(entry => IDS.has(entry.id) ? { ...entry, asset_id: asset.id, target_height: 1.6, anchor_at_pivot: true } : entry);
}

/** Call on a baked template for an exact L2 batch, before assigning its instance buffers. */
export function createL2BrazierRepairParts(source, assetId, entryIds) {
  if (assetId !== 'sm_brazier_tripod' || !entryIds.length || entryIds.length > 2 || entryIds.some(id => !IDS.has(id))) return null;
  if (!(source instanceof Mesh) || !(source.material instanceof PBRMaterial)) throw new TypeError('L2 requires a baked PBR mesh');
  const uv = source.getVerticesData('uv'), positions = source.getVerticesData('position'), indices = source.getIndices();
  if (!uv || !positions || !indices || uv.length !== positions.length / 3 * 2) throw new TypeError('L2 source position/atlas UV mismatch');
  const coal = [];
  for (let k = 0; k < indices.length; k += 3) {
    const tri = [indices[k], indices[k + 1], indices[k + 2]];
    if (tri.some(i => !Number.isInteger(i) || i < 0 || i * 3 + 2 >= positions.length)) throw new TypeError('L2 source index out of range');
    if (tri.every(i => uv[i * 2] > .25 && uv[i * 2] < .5 && uv[i * 2 + 1] > .5 && uv[i * 2 + 1] < .75)) coal.push(...tri);
  }
  if (![72, 54, 36].includes(coal.length)) throw new Error('L2 expected the authored 24/18/12-triangle coal cap');
  if (![852, 660, 468].includes(indices.length) || Array.from(positions).some(value => !Number.isFinite(value))) throw new Error('Pinned tripod geometry required');
  const coalTop = Math.max(...coal.map(index => positions[index * 3 + 1]));
  const coalBottom = Math.min(...coal.map(index => positions[index * 3 + 1]));
  const coalRadius = Math.max(...coal.map(index => Math.hypot(positions[index * 3], positions[index * 3 + 2])));
  const rimY = Math.max(...Array.from(positions).filter((_, index) => index % 3 === 1));
  if (Math.abs(coalTop - .938) > .003 || Math.abs(coalBottom - .93) > .003 || Math.abs(coalRadius - .2275) > .003 || Math.abs(rimY - 1.1) > .003) throw new Error('Tripod coal/rim geometry mismatch');
  const coalLift = rimY - .025 - coalTop;
  const scene = source.getScene(), original = source.material;
  const bodyMaterial = new PBRMaterial('l2-readable-iron', scene);
  // Independent material; atlas objects stay with the existing craft owner.
  for (const slot of TEXTURE_SLOTS) bodyMaterial[slot] = original[slot];
  bodyMaterial.albedoColor = new Color3(3.2, 3.2, 2.9);
  bodyMaterial.metallic = 0; bodyMaterial.roughness = .82;
  bodyMaterial.directIntensity = original.directIntensity;
  bodyMaterial.environmentIntensity = original.environmentIntensity;
  bodyMaterial.useAmbientOcclusionFromMetallicTextureRed = original.useAmbientOcclusionFromMetallicTextureRed;
  bodyMaterial.useRoughnessFromMetallicTextureGreen = original.useRoughnessFromMetallicTextureGreen;
  bodyMaterial.useMetallnessFromMetallicTextureBlue = original.useMetallnessFromMetallicTextureBlue;
  bodyMaterial.invertNormalMapX = original.invertNormalMapX; bodyMaterial.invertNormalMapY = original.invertNormalMapY;
  bodyMaterial.metadata = { glow: false, l2BrazierRepair: true, borrowedCraftAtlas: true };
  const originalDispose = bodyMaterial.dispose.bind(bodyMaterial); let materialDisposed = false;
  bodyMaterial.dispose = (forceEffect = false) => {
    if (materialDisposed) return; materialDisposed = true;
    for (const slot of TEXTURE_SLOTS) bodyMaterial[slot] = null;
    originalDispose(forceEffect, false);
  };
  const body = source.clone(source.name + '-l2-readable', null, true);
  body.makeGeometryUnique(); body.material = bodyMaterial; body.receiveShadows = true; body.isPickable = false;
  body.metadata = { ...body.metadata, glow: false, l2BrazierPart: 'body' }; body.setEnabled(false);
  const emberMaterial = new PBRMaterial('l2-brazier-ember-core', scene);
  emberMaterial.unlit = true; emberMaterial.albedoColor = Color3.Black();
  emberMaterial.backFaceCulling = false;
  emberMaterial.emissiveColor = new Color3(.72, .12, .015);
  emberMaterial.metallic = 0; emberMaterial.roughness = 1;
  emberMaterial.metadata = { glow: false, l2BrazierRepair: true, emitterAnchorAdded: false };
  const ember = new Mesh(source.name + '-l2-ember-core', scene), lifted = Float32Array.from(positions);
  for (let k = 1; k < lifted.length; k += 3) lifted[k] += coalLift;
  ember.setVerticesData('position', lifted, false, 3); ember.setIndices(coal);
  const normals = source.getVerticesData('normal');
  if (normals) ember.setVerticesData('normal', Float32Array.from(normals), false, 3);
  ember.material = emberMaterial; ember.isPickable = false; ember.receiveShadows = false;
  ember.metadata = { glow: false, l2BrazierPart: 'ember' }; ember.setEnabled(false);
  const diagnostics = { assetId, entryIds: [...entryIds], coalTriangles: coal.length / 3, extraTextures: 0,
    extraLights: 0, extraAnchors: 0, emission: [.72, .12, .015], animatedFlame: false,
    coalLift, rimY, raisedCoalTop: rimY - .025, bodyTriangles: indices.length / 3, bodyFacesRemoved: 0 };
  return { parts: [body, ember], materials: [bodyMaterial, emberMaterial], diagnostics,
    dispose() { body.dispose(false, false); ember.dispose(false, false); bodyMaterial.dispose(); emberMaterial.dispose(false, false); } };
}
