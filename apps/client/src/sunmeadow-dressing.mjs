/** Deterministic dressing policy. No browser, renderer, random state or I/O. */
export const DRESSING_ALIASES = Object.freeze({
  rock_S: ['sm_small_01', 'sm_small_02', 'sm_small_03', 'sm_small_04'],
  rock_M: ['sm_medium_01', 'sm_medium_02', 'sm_medium_03', 'sm_medium_04'],
  rock_L: ['sm_boulder_01', 'sm_boulder_02', 'sm_boulder_03'],
  boulder: ['sm_boulder_02', 'sm_boulder_03', 'sm_boulder_04'],
  stepping_stone: ['sm_stepstone_01', 'sm_stepstone_02', 'sm_stepstone_03'],
  cliff_piece: ['sm_cliff_wall_01', 'sm_cliff_wall_02', 'sm_cliff_corner_04', 'sm_cliff_cap_06'],
  bush_round: ['cc0_kenney_bush'],
  mushroom_ring_set: ['cc0_qn_mushroom_common'],
  fallen_log: ['sm_cove_driftwood_1', 'sm_cove_driftwood_2', 'sm_cove_driftwood_3'],
  reed_clump: ['sm_reeds_01', 'sm_reeds_02', 'sm_reeds_03'],
  lily_pad: ['sm_lilypad_01', 'sm_lilypad_02', 'sm_lilypad_03'],
  lotus_flower: ['sm_lotus_half', 'sm_lotus_open'],
  cove_driftwood: ['sm_cove_driftwood_1', 'sm_cove_driftwood_2', 'sm_cove_driftwood_3'],
  hay_skep: ['sm_croft_skep_1'],
  hay_bale_small: ['sm_croft_skep_1', 'sm_croft_skep_2'],
  fence_run_post_rail: ['sm_croft_fence'],
  cove_fishing_props: ['sm_cove_rod_rack', 'sm_market_goods_fish'],
});

export function dressingHash(id) {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return h >>> 0;
}

export function dressingAssetId(entry, assets) {
  if (assets.has(entry.asset_id)) return entry.asset_id;
  const ids = DRESSING_ALIASES[entry.asset_id];
  if (!ids?.length) return null;
  const id = ids[((Math.max(1, entry.variant ?? 1) - 1) | 0) % ids.length];
  return assets.has(id) ? id : null;
}

export function dressingPlan(profile) {
  const mobile = profile.formFactor === 'mobile';
  return { density: Math.max(0, Math.min(1, profile.vegetationDensity ?? 1)),
    near: mobile ? 18 : 24, middle: mobile ? 36 : 48, end: mobile ? 64 : 90,
    fade: 4, triangleBudget: 40000 };
}

export function dressingKeep(entry, density) {
  return entry.collider === 'solid' || entry.landmark || dressingHash(entry.id) / 4294967296 < density;
}

/** Complementary Bayer intervals: an object never draws more than one layer per pixel. */
export function dressingLodRanges(distance, plan, minimumLod = 0) {
  if (!Number.isFinite(distance) || distance < 0 || distance >= plan.end) return [];
  const weights = [0, 0, 0];
  const mix = (boundary) => Math.max(0, Math.min(1, (distance - boundary + plan.fade / 2) / plan.fade));
  const first = mix(plan.near), second = mix(plan.middle);
  weights[0] = 1 - first; weights[1] = first * (1 - second); weights[2] = second;
  for (let lod = 0; lod < minimumLod; lod++) { weights[minimumLod] += weights[lod]; weights[lod] = 0; }
  const far = Math.max(0, Math.min(1, (plan.end - distance) / plan.fade));
  let lower = 0;
  const result = [];
  for (let lod = 0; lod < 3; lod++) {
    const upper = lower + weights[lod] * far;
    if (upper > lower) result.push({ lod, lower, upper });
    lower = upper;
  }
  return result;
}

export function validateDressing(entries) {
  if (!Array.isArray(entries) || entries.length > 2000) throw new Error('Invalid or oversized Sunmeadow dressing');
  const ids = new Set();
  for (const e of entries) {
    if (!e || typeof e.id !== 'string' || typeof e.asset_id !== 'string' || ids.has(e.id) ||
      !['none', 'soft', 'solid'].includes(e.collider) ||
      ![e.x, e.y, e.z, e.yaw, e.scale, e.footprint_r].every(Number.isFinite) ||
      e.scale <= 0 || e.scale > 8 || e.footprint_r <= 0 || e.footprint_r > 15 ||
      (e.target_height!==undefined&&(!Number.isFinite(e.target_height)||e.target_height<=0||e.target_height>20)) ||
      (e.target_size_xyz!==undefined&&(!Array.isArray(e.target_size_xyz)||e.target_size_xyz.length!==3||e.target_size_xyz.some(v=>!Number.isFinite(v)||v<=0||v>30)))) throw new Error(`Invalid dressing entry ${e?.id}`);
    ids.add(e.id);
  }
  return entries;
}

/** Keep visuals inside the planned circular avoidance footprint, including off-centre pivots. */
export function dressingScale(entry, bounds) {
  const radius = Math.hypot(Math.max(Math.abs(bounds.min[0]), Math.abs(bounds.max[0])),
    Math.max(Math.abs(bounds.min[2]), Math.abs(bounds.max[2])));
  return Math.min(entry.scale, radius > 0 ? entry.footprint_r / radius : entry.scale);
}

/** Explicit dimensions use measured model bounds. Phase/weather controls remain independent. */
export function blueprintScale(entry, bounds) {
  const dims=bounds.max.map((v,i)=>v-bounds.min[i]);
  if(dims.some(v=>!Number.isFinite(v)||v<=0))throw new Error(`Invalid model bounds ${entry.asset_id}`);
  if(entry.target_size_xyz)return entry.target_size_xyz.map((v,i)=>v/dims[i]);
  if(entry.target_height){const s=entry.target_height/dims[1];return [s,s,s];}
  const s=entry.landmark?entry.scale:dressingScale(entry,bounds);return entry.scale_xyz??[s,s,s];
}

/** P1 overturned/leaned kits ground their rotated bottom; frozen P0 transforms stay unchanged. */
export function blueprintFloor(entry, bounds, scale) {
  if(entry.blueprint_wave!=='P1'||!(entry.pitch||entry.roll))return bounds.min[1]*scale[1];
  const cp=Math.cos(entry.pitch??0),sp=Math.sin(entry.pitch??0),cr=Math.cos(entry.roll??0),sr=Math.sin(entry.roll??0);
  let y=Infinity;
  for(const x of [bounds.min[0],bounds.max[0]])for(const yy of [bounds.min[1],bounds.max[1]])for(const z of [bounds.min[2],bounds.max[2]])
    y=Math.min(y,x*scale[0]*sr*cp+yy*scale[1]*cr*cp-z*scale[2]*sp);
  return y;
}

export function blueprintEntries(dressing, enabled=true) {
  return validateDressing(enabled?dressing.entries:(dressing.baseline_entries??dressing.entries));
}
export function applySemanticDressingOverlay(dressing,overlay){
 if(overlay?.schema!=='xexoria.semantic-dressing-overlay/1'||overlay.entries?.length!==4)throw new TypeError('Four approvedsignpostoverlay required');
 const replace=new Set(overlay.replaces_visual_entries),entries=dressing.entries.filter(e=>!replace.has(e.id)).concat(overlay.entries);
 validateDressing(entries);
 return {...dressing,entries,blueprint:{...dressing.blueprint,items:dressing.blueprint.items.map(i=>i.id===overlay.item_patch.id?{...i,...overlay.item_patch}:i)},semantic_overlay:overlay.id};
}

/** Quantized glTF nodes and importer handedness roots must be baked together before parent removal. */
export function bakeDressingGeometry(mesh,{preserveColor=false}={}) {
  const originalColor=preserveColor?mesh.getVerticesData('color')?.slice():null;
  const originalColorSize=preserveColor?mesh.getVertexBuffer('color')?.getSize():undefined;
  mesh.computeWorldMatrix(true);
  const normalMatrix = mesh.getWorldMatrix().clone().invert().transpose().asArray();
  const originalNormals = mesh.getVerticesData('normal')?.slice();
  mesh.bakeCurrentTransformIntoVertices(true, true);
  mesh.parent = null;
  mesh.position.setAll(0); mesh.scaling.setAll(1); mesh.rotation.setAll(0);
  if (mesh.rotationQuaternion) mesh.rotationQuaternion.set(0, 0, 0, 1);
  // Babylon already repairs mirrored winding. Use inverse-transpose normals for nonuniform dequantization scales.
  if (originalNormals) {
    for (let i = 0; i < originalNormals.length; i += 3) {
      const x=originalNormals[i],y=originalNormals[i+1],z=originalNormals[i+2];
      const nx=x*normalMatrix[0]+y*normalMatrix[4]+z*normalMatrix[8];
      const ny=x*normalMatrix[1]+y*normalMatrix[5]+z*normalMatrix[9];
      const nz=x*normalMatrix[2]+y*normalMatrix[6]+z*normalMatrix[10];
      const length=Math.hypot(nx,ny,nz)||1;
      originalNormals[i]=nx/length;originalNormals[i+1]=ny/length;originalNormals[i+2]=nz/length;
    }
    mesh.setVerticesData('normal',originalNormals,false);
  }
  // Derivative normal mapping avoids a tangent buffer: 3 geometry + 4 matrix + 1 fade = 8.
  for (const kind of ['tangent', ...(preserveColor?[]:['color']), 'uv2']) mesh.removeVerticesData(kind);
  if(originalColor&&originalColorSize)mesh.setVerticesData('color',originalColor,false,originalColorSize);
  mesh.computeWorldMatrix(true);
  return mesh;
}

/** Choose a conservative source LOD per cell; preserve every collider and landmark. */
export function dressingCellLods(entries, assets, budget = 40000, reservedTriangles = new Map()) {
  const totals = new Map();
  for (const e of entries) {
    const a = assets.get(e.asset_id);
    if (!a) continue;
    const key = `${Math.floor(e.x / 64)},${Math.floor(e.z / 64)}`;
    const t = totals.get(key) ?? [0, 0, 0];
    for (let lod = 0; lod < 3; lod++) t[lod] += a.lods[Math.min(lod, a.lods.length - 1)].tris;
    totals.set(key, t);
  }
  return new Map([...totals].map(([key, counts]) => {
    // Both representations submit geometry inside a Bayer band, even though their pixels complement.
    const reserve=reservedTriangles.get(key)??0;
    const handoverCounts = counts.map((n,lod) => n + (lod < 2 ? counts[lod+1] : 0)+reserve);
    const lod = handoverCounts.findIndex(n => n <= budget);
    if (lod < 0) throw new Error(`Dressing cell ${key} exceeds ${budget} triangles even at LOD2`);
    return [key, { minimumLod: lod, triangles: handoverCounts[lod], lod0Triangles: counts[0]+reserve }];
  }));
}

/** Reserve a focal asset's worst complete handover while surrounding detail keeps its cell LOD. */
export function dressingFocalMinimums(entries,assets,cellLods,focalIds,budget=40000){
 if(!Array.isArray(focalIds)||focalIds.length>8||!Number.isInteger(budget)||budget<=0)throw new TypeError('BoundedfocalLODcontractrequired');
 const wanted=new Set(focalIds),totals=new Map([...cellLods].map(([key,value])=>[key,value.triangles])),result=new Map();
 const cost=(asset,minimum)=>{const t=Array.from({length:3},(_,lod)=>asset.lods[Math.min(lod,asset.lods.length-1)].tris);if(t.some(v=>!Number.isInteger(v)||v<0))throw new TypeError('Finitefocaltrianglecountsrequired');return Math.max(...t.slice(minimum).map((v,i)=>v+(minimum+i<2?t[minimum+i+1]:0)));};
 for(const entry of entries){if(!wanted.has(entry.id))continue;const asset=assets.get(entry.asset_id),cell=`${Math.floor(entry.x/64)},${Math.floor(entry.z/64)}`,base=cellLods.get(cell);if(!asset||!base)continue;let minimum=base.minimumLod,total=totals.get(cell),old=cost(asset,minimum);for(let candidate=0;candidate<base.minimumLod;candidate++){const proposed=total-old+cost(asset,candidate);if(proposed<=budget){minimum=candidate;total=proposed;break;}}totals.set(cell,total);result.set(entry.id,{cell,baseMinimumLod:base.minimumLod,minimumLod:minimum,worstCellTriangles:total,budget});}
 return result;
}
