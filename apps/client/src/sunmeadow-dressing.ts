import { ImportMeshAsync } from '@babylonjs/core/Loading/sceneLoader';
import { createL2BrazierRepairParts, selectL2BrazierEntries } from './l2-brazier-material-repair.mjs';
import { applyPalmDefectOverlay } from './palm-defect-overlay.mjs';
import { configureDressingOrm, dressingMaterialIdentity } from './dressing-material-policy.mjs';
import palmDefectD4 from '../../../planning/levels/sunmeadow-palm-d4-r01.json';
import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { VertexData } from '@babylonjs/core/Meshes/mesh.vertexData';
import { PointLight } from '@babylonjs/core/Lights/pointLight';
import { readWeatherFrame } from './ambient-weather-channel.js';
import '@babylonjs/core/Meshes/thinInstanceMesh';
import { Matrix, Quaternion, Vector3 } from '@babylonjs/core/Maths/math.vector';
import { Color3 } from '@babylonjs/core/Maths/math.color';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
import { Texture } from '@babylonjs/core/Materials/Textures/texture';
import { DitheredTileFadeMaterialPlugin } from '@babylonjs/core/Materials/ditheredTileFadeMaterialPlugin';
import '@babylonjs/core/Shaders/ShadersInclude/bayerDitherFunctions';
import '@babylonjs/core/ShadersWGSL/ShadersInclude/bayerDitherFunctions';
import type { Material } from '@babylonjs/core/Materials/material';
import type { Scene } from '@babylonjs/core/scene';
import type { ShadowGenerator } from '@babylonjs/core/Lights/Shadows/shadowGenerator';
import type { ResolvedGraphicsPreset } from './graphics-quality.mjs';
import { bakeDressingGeometry, dressingAssetId, dressingCellLods, dressingKeep, dressingLodRanges,
  dressingPlan, dressingFocalMinimums, blueprintEntries, blueprintScale, blueprintFloor, applySemanticDressingOverlay, type DressingAsset, type DressingEntry } from './sunmeadow-dressing.mjs';
import{notifyLookV2PoolEmitterChanged}from'./look-v2-pool-events.mjs';
import sourceP0Dressing from '../../../planning/levels/sunmeadow-v3-dressing.json';
import sourceP1Dressing from '../../../planning/levels/sunmeadow-v3-dressing-p1.json';
import sourceP2Dressing from '../../../planning/levels/sunmeadow-v3-dressing-p2.json';
import signpostOverlay from '../../../planning/levels/sunmeadow-st8-posts-v1.json';
import signpostCandidate from '../../../assets/models/props/blueprint-signpost-v1-candidate/r01/candidate-manifest.json';
import waterArtOverlay from '../../../planning/levels/sunmeadow-water-art-pass4b-overlay.json';
import waterArtR02Overlay from '../../../planning/levels/sunmeadow-water-art-pass4b-r02-overlay.json';
import waterArtR03Overlay from '../../../planning/levels/sunmeadow-water-art-pass4b-r03-overlay.json';
import waterArtR03Grotto from './assets/world/water-art-pass4b-r03/grotto-manifest.json';
import waterArtR02Puddles from './assets/world/water-art-pass4b-r02/p4-derived.json';
import{packDressingVertexBuffers}from'./dressing-vertex-packing.mjs';
import{WaterArtMossUpPlugin}from'./water-art-pass4b-materials';
import{installWaterArtScene}from'./water-art-pass4b-scene';
import sourceManifest from '../../../assets/models/sunmeadow-props/manifest.json';
import sourceLayout from '../../../planning/levels/sunmeadow-v2-layout.json';
import bushUrl from './assets/foliage/kenney/plant_bushDetailed.glb?url';
import palmPaletteCandidate from '../../../assets/models/blueprint-cc0/candidates/palm-palette-v2/candidate-asset.json';

const files = import.meta.glob('../../../assets/models/sunmeadow-props/**/runtime/*.{glb,ktx2}',
  { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
Object.assign(files, import.meta.glob('../../../assets/models/sunmeadow-dressing-cc0/runtime/*.glb',
  { eager: true, query: '?url', import: 'default' }));
Object.assign(files, import.meta.glob('../../../assets/models/blueprint-cc0/**/*.glb',
  { eager: true, query: '?url', import: 'default' }));
Object.assign(files, import.meta.glob('../../../assets/models/blueprint-p0-fence/runtime/*.glb',
  { eager: true, query: '?url', import: 'default' }));
Object.assign(files, import.meta.glob('../../../assets/models/blueprint-p2-torch/runtime/*.glb',
  { eager: true, query: '?url', import: 'default' }));
Object.assign(files, import.meta.glob('../../../assets/models/props/blueprint-signpost-v1-candidate/r01/runtime/*.glb',
  { eager: true, query: '?url', import: 'default' }));
Object.assign(files, import.meta.glob('./assets/world/water-art-pass4b-r03/*_lod*.glb',
  { eager: true, query: '?url', import: 'default' }));
import localBlueprint from '../../../assets/models/blueprint-p0-fence/manifest.json';
import tikiBlueprint from '../../../assets/models/blueprint-p2-torch/manifest.json';
const blueprintManifests=import.meta.glob('../../../assets/models/blueprint-cc0/manifest.json',
  {eager:true,import:'default'}) as Record<string,{schema:string;assets:DressingAsset[]}>;
const textures = import.meta.glob('../../../assets/models/sunmeadow-props/**/runtime/textures/*.ktx2',
  { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
Object.assign(textures, import.meta.glob('../../../assets/models/sunmeadow-dressing-cc0/runtime/textures/*.ktx2',
  { eager: true, query: '?url', import: 'default' }));
const localUrl = (file: string) => {
  const key=file.startsWith('apps/client/src/assets/world/water-art-pass4b-r03/')?'./'+file.slice('apps/client/src/'.length):`../../../${file}`;
  const url = files[key];
  if (!url) throw new Error(`Dressing asset missing from build: ${file}`);
  return url;
};

/** Explicit landmarks use real authored modules; their collision contract remains a root acceptance gate. */
function landmarkEntries(): DressingEntry[] {
  const out: DressingEntry[] = [];
  const add = (id: string, asset: string, x: number, z: number, yaw = 0, scale_xyz: [number, number, number] = [1,1,1], surface_y?: number) =>
    out.push({ id, asset_id: asset, x, y: 0, z, yaw, scale: 1, scale_xyz, footprint_r: 12,
      collider: 'solid', landmark: true, shadow: true, surface_y });
  for (const feature of sourceLayout.features) {
    if (!('decks' in feature)) continue;
    for (const deck of feature.decks ?? []) {
      const xs=deck.polygon_xz.map(p=>p[0]), zs=deck.polygon_xz.map(p=>p[1]);
      const x0=Math.min(...xs), x1=Math.max(...xs), z0=Math.min(...zs), z1=Math.max(...zs);
      const segments=Math.ceil((x1-x0)/4), length=(x1-x0)/segments;
      for(let i=0;i<segments;i++) add(`v3_${deck.id}_${i}`, deck.kind==='platform'?'sm_pier_end':'sm_pier_straight',
        x0+(i+.5)*length,(z0+z1)/2,Math.PI/2,[(z1-z0)/2,1,length/4],-.12);
    }
  }
  add('v3_croft_hut','sm_croft_hut',38.6,11.4,Math.PI);
  add('v3_croft_well','sm_croft_well',35.6,4.6);
  add('v3_croft_campfire','sm_croft_campfire',40.4,2.6,0,[.7,.7,.7]);
  add('v3_croft_firewood','sm_croft_firewood',44.7,4,Math.PI/2);
  add('v3_cove_rowboat','sm_cove_rowboat',-42.6,-83.4,2.2);
  add('v3_lotus_column_tall','sm_column_intact',-51.7,6.6,0,[.9,1.13,.9]);
  add('v3_lotus_column_short','sm_column_broken',-48.9,6.9,0,[.84,.91,.84]);
  add('v3_lotus_column_fallen','sm_column_toppled',-51.9,2.7,.35,[.6,.72,.6]);
  add('v3_grotto_mouth','sm_grotto_mouth',-4,-39,4.712);
  add('v3_grotto_tunnel','sm_grotto_tunnel',-1.554,-39,Math.PI/2,[1,1,4.892/4.6]);
  add('v3_grotto_crystals','sm_crystals_03',10.2,-36.1,0,[1.3,1.65,1.3]);
  // The pen remains closed; no speculative interaction or sheep simulation is created here.
  for(let i=0;i<3;i++) add(`v3_pen_north_${i}`,'sm_croft_wall_straight',35.5+i*3,-2.5);
  for(const [side,x] of [['west',34.3],['east',42.7]] as const)
    for(let i=0;i<4;i++) add(`v3_pen_${side}_${i}`,'sm_croft_wall_straight',x,-12.7+i*3,Math.PI/2);
  add('v3_pen_south_w','sm_croft_wall_straight',35.75,-13.9,0,[3.5/3,1,1]);
  add('v3_pen_south_e','sm_croft_wall_straight',41.25,-13.9,0,[3.5/3,1,1]);
  add('v3_pen_gate','sm_croft_wall_gate',38.5,-13.9,0,[2.2/2.99,1,1]);
  return out;
}

interface Slot { entry: DressingEntry; matrix: Float32Array; cell: string; minimumLod: number }
interface Batch { key: string; slots: Slot[]; lod: number; meshes: Mesh[]; matrices: Float32Array; signature: string }

export interface SunmeadowDressingDiagnostics {
  status: 'LOADING'|'READY'|'DISPOSED'; sourceEntries: number; resolvedEntries: number; landmarkEntries: number;
  missing: string[]; approximateAliases: string[]; errors: string[]; visibleInstances: number; draws: number;
  triangles: number; maxCellTriangles: number; maxCellDraws: number; vertexBuffersPerPipeline: number;
  blueprintEnabled:boolean;blueprintWave:'P0'|'P1'|'P2'|'off';blueprintItems:{id:string;wave?:string;status?:string;requested:number;resolved:number;missingAssets:string[];standins:string[];remaining:string[]}[];
  groundingPending:string[];
  ambientAnimals?:{status:string;count:number;triangles:number;physics:string;nativeAdmission:string};
  focalAllocation?:{id:string;cell:string;baseMinimumLod:number;minimumLod:number;worstCellTriangles:number;budget:number}[];
  focalVisibleLods?:{id:string;asset:string;lod:number}[];
  nativeAdmission: 'UNVERIFIED';
}

export async function createSunmeadowDressing(scene: Scene, options: {
  getProfile(): ResolvedGraphicsPreset; getShadows(): ShadowGenerator; shadowsEnabled: boolean;
  getGroundHeight?(x:number,z:number):number|null;
}): Promise<{ stats(): SunmeadowDressingDiagnostics; dispose(): void }> {
  if(sourceManifest.schema !== 'xexoria.props-manifest/1') throw new Error('Unexpected Sunmeadow props schema');
  const assets = new Map<string,DressingAsset>(Object.values(sourceManifest.families).flat().map(a=>[a.id,a as DressingAsset]));
  for(const manifest of Object.values(blueprintManifests)){if(manifest.schema!=='xexoria.blueprint-cc0/1')throw new Error('Invalid licensed blueprint manifest');for(const asset of manifest.assets)assets.set(asset.id,asset);}
  if(localBlueprint.schema!=='xexoria.blueprint-local/1')throw new Error('Invalid authored blueprint manifest');
  for(const asset of localBlueprint.assets)assets.set(asset.id,asset as DressingAsset);
  if(tikiBlueprint.schema!=='xexoria.blueprint-local/1')throw new Error('Invalid tiki manifest');
  for(const asset of tikiBlueprint.assets)assets.set(asset.id,asset as DressingAsset);
  const sign=signpostCandidate.assets[0];assets.set(sign.id,{id:sign.id,family:sign.family,bounds:sign.bounds,textures:{atlas:sign.atlas_family},status:'PROJECT_AUTHORED_CANDIDATE',lods:sign.lods.map((file,lod)=>({file,tris:signpostCandidate.files[('lod'+lod) as 'lod0'|'lod1'|'lod2'].metrics.triangles,sha256:signpostCandidate.files[('lod'+lod) as 'lod0'|'lod1'|'lod2'].sha256}))});
  const palmD4Review=import.meta.env.DEV && new URLSearchParams(location.search).get('palmDefect')==='r01';
  if(import.meta.env.DEV && (new URLSearchParams(location.search).get('blueprintPalm')==='v2'||palmD4Review)) {
    const palm=assets.get('blueprint_cc0_palm');
    if(palm)assets.set(palm.id,{...palm,...palmPaletteCandidate} as DressingAsset);
  }
  const selectedWave=import.meta.env.DEV?new URLSearchParams(location.search).get('blueprintWave'):null;
  const blueprintWave=selectedWave==='p2'?'P2':selectedWave==='p1'?'P1':selectedWave==='off'?'off':'P0';
  const waterArt=import.meta.env.DEV&&new URLSearchParams(location.search).get('waterArt')==='pass4b';
  const waterArtRevision=waterArt&&new URLSearchParams(location.search).get('waterArtRev')==='3'?3:waterArt&&new URLSearchParams(location.search).get('waterArtRev')==='2'?2:1;
  const selectedArtOverlay=waterArtRevision===3?waterArtR03Overlay:waterArtRevision===2?waterArtR02Overlay:waterArtOverlay;
  if(waterArtRevision===3)assets.set(waterArtR03Grotto.id,{id:waterArtR03Grotto.id,family:'stone',bounds:waterArtR03Grotto.bounds,textures:waterArtR03Grotto.textures,status:waterArtR03Grotto.status,lods:waterArtR03Grotto.lods.map(l=>({file:l.file,tris:l.triangles,sha256:l.sha256}))});
  const baseDressing=blueprintWave==='P2'?sourceP2Dressing:blueprintWave==='P1'?sourceP1Dressing:sourceP0Dressing;
  const sourceDressing=(blueprintWave==='P1'||blueprintWave==='P2')&&new URLSearchParams(location.search).get('blueprintST8')!=='off'?applySemanticDressingOverlay(baseDressing,signpostOverlay):baseDressing;
  const artSourceEntriesBase=selectL2BrazierEntries(waterArt?[...sourceDressing.entries.map(e=>{const p=selectedArtOverlay.L1_patches.find(p=>p.id===e.id);return p?{...e,x:p.x,z:p.z,cell:`${Math.floor(p.x/64)},${Math.floor(p.z/64)}`}:e;}),...selectedArtOverlay.entries]:sourceDressing.entries,assets);
  const artSourceEntries=palmD4Review?applyPalmDefectOverlay(artSourceEntriesBase,palmDefectD4):artSourceEntriesBase;
  if(palmD4Review)scene.metadata={...scene.metadata,palmDefectD4:{revision:'r01',existingRoots:10,placementsAdded:0,physicalAdmission:'PENDING_PAIRED_COLLIDER_REQUEST'}};
  if(waterArt)installWaterArtScene(scene,waterArtRevision);
  const rainBodies=waterArtRevision>=2?waterArtR02Puddles.rain_bodies:sourceP2Dressing.p2.rain_bodies;
  if(blueprintWave==='P2')scene.metadata={...scene.metadata,blueprintRainRequest:{bodies:rainBodies,groundAt:options.getGroundHeight??(()=>null)}};
  const blueprintEnabled=blueprintWave!=='off';
  const extraMounds='extra_mounds' in sourceDressing.blueprint?sourceDressing.blueprint.extra_mounds:[];
  const terrainSources=[sourceDressing.blueprint.mound,...extraMounds];
  assets.set('cc0_kenney_bush',{ id:'cc0_kenney_bush',family:'cc0',lods:[{file:'cc0-bush',tris:500}],
    bounds:{min:[-.8,0,-.8],max:[.8,1.2,.8]},status:'EXISTING_CC0'});
  assets.set('cc0_qn_mushroom_common',{id:'cc0_qn_mushroom_common',family:'cc0-mushroom',
    lods:[880,264,123].map((tris,lod)=>({tris,file:`assets/models/sunmeadow-dressing-cc0/runtime/qn_mushroom_common_lod${lod}.glb`})),
    bounds:{min:[-.33336,-.01749,-.44521],max:[.23031,.44603,.3339]},textures:{atlas:'Mushrooms'},status:'TECHNICAL_CANDIDATE'});
  const diagnostics: SunmeadowDressingDiagnostics = { status:'LOADING',sourceEntries:sourceDressing.entries.length,
    resolvedEntries:0,landmarkEntries:0,missing:[],approximateAliases:['fallen_log -> cove driftwood','hay_bale_small -> farm skep',
      'cove_fishing_props -> rod rack / fish goods'],errors:[],visibleInstances:0,draws:0,triangles:0,maxCellTriangles:0,maxCellDraws:0,
    vertexBuffersPerPipeline:8,nativeAdmission:'UNVERIFIED',blueprintEnabled,blueprintWave,blueprintItems:[],groundingPending:[] };
  const entries: DressingEntry[] = [];
  for(const entry of blueprintEntries({...sourceDressing,entries:artSourceEntries},blueprintEnabled)) {
    const id=dressingAssetId(entry,assets);
    if(!id) { diagnostics.missing.push(entry.id); continue; }
    if(entry.blueprint_id&&((entry.z>=8&&!options.getGroundHeight)||(options.getGroundHeight&&options.getGroundHeight(entry.x,entry.z)===null))){diagnostics.groundingPending.push(entry.id);continue;}
    entries.push({...entry,asset_id:id});
  }
  diagnostics.resolvedEntries=entries.length;
  if(blueprintEnabled)for(const item of sourceDressing.blueprint.items){const requested=sourceDressing.entries.filter(e=>e.blueprint_id===item.id);diagnostics.blueprintItems.push({id:item.id,wave:item.pr,status:'status' in item?item.status:'P0_CORE_PARTIAL',requested:requested.length,resolved:entries.filter(e=>e.blueprint_id===item.id).length,missingAssets:[...new Set(requested.filter(e=>!assets.has(e.asset_id)).map(e=>e.asset_id))],standins:requested.filter(e=>e.standin).map(e=>e.asset_id),remaining:item.remaining_components});}
  const landmarks=landmarkEntries().filter(e=>assets.has(e.asset_id)&&(waterArtRevision!==3||!waterArtR03Overlay.replaces_visual_entries.includes(e.id)));
  diagnostics.landmarkEntries=landmarks.length; entries.push(...landmarks);
  const terrainTriangles=new Map<string,number>(),terrainDraws=new Map<string,number>();
  if(blueprintEnabled)for(const m of terrainSources){const key=`${Math.floor(m.centre_xz[0]/64)},${Math.floor(m.centre_xz[1]/64)}`;terrainTriangles.set(key,(terrainTriangles.get(key)??0)+m.indices.length/3);terrainDraws.set(key,(terrainDraws.get(key)??0)+1);}
  if(blueprintWave==='P2')for(const b of rainBodies){const key=`${Math.floor(b.center_xz[0]/64)},${Math.floor(b.center_xz[1]/64)}`;terrainTriangles.set(key,(terrainTriangles.get(key)??0)+b.outline_xz.length);}
  // Coal overlays add at most LOD0+LOD1 (24+18) triangles per repaired brazier.
  for(const entry of entries)if(entry.id==='bp1_L2_000'||entry.id==='bp1_L2_001'){
    const key=`${Math.floor(entry.x/64)},${Math.floor(entry.z/64)}`;
    terrainTriangles.set(key,(terrainTriangles.get(key)??0)+42);
  }
  const cellLods=dressingCellLods(entries,assets,40000,terrainTriangles);
  const focalMinimums=dressingFocalMinimums(entries,assets,cellLods,[...(waterArtRevision===3?['water_art_grotto_organic_r03']:[]),'bp1_L2_000','bp1_L2_001'],40000);
  diagnostics.focalAllocation=[...focalMinimums].map(([id,value])=>({id,...value}));
  diagnostics.maxCellTriangles=Math.max(...[...cellLods.values()].map(v=>v.triangles),...[...focalMinimums.values()].map(v=>v.worstCellTriangles));
  const materials=new Set<Material>(), templates: Mesh[]=[], batches:Batch[]=[], shadowed=new Set<Mesh>();
  const familyMaterials=new Map<string,PBRMaterial>();
  const extras:Mesh[]=[],extraMaterials:PBRMaterial[]=[],lanterns:PointLight[]=[];
  const motionParts=new Map<Mesh,{axis:Vector3;pivot:Vector3;period:number}>();
  const instanceMatrices=new Map<Mesh,Float32Array>();
  if(blueprintEnabled){
    for(const mound of terrainSources){
    const mesh=new Mesh(mound.id==='T1'?'blueprint-T1-Sunrise-Knoll':'blueprint-'+mound.id+'-closed-visual',scene),data=new VertexData();
    data.positions=mound.positions;data.indices=mound.indices;data.colors=mound.colours;data.normals=[];VertexData.ComputeNormals(data.positions,data.indices,data.normals);data.uvs=data.positions.flatMap((v,i)=>i%3===0?[v/6,data.positions![i+2]/6]:[]);data.applyToMesh(mesh);
    const base=scene.getMaterialByName('env-shared-world-grass') as PBRMaterial|null;
    const mat=new PBRMaterial('blueprint-'+mound.id+'-meadow',scene);mat.albedoTexture=base?.albedoTexture??null;mat.bumpTexture=base?.bumpTexture??null;mat.albedoColor=Color3.White();mat.roughness=.96;mat.metallic=0;mesh.material=mat;mesh.receiveShadows=true;mesh.isPickable=false;mesh.metadata={dressingV3:true,blueprintId:'blueprint_id' in mound?mound.blueprint_id:mound.id,physicalSupportY:0,walkable:false};extras.push(mesh);extraMaterials.push(mat);shadowed.add(mesh);if(options.shadowsEnabled)options.getShadows().addShadowCaster(mesh,false);
    }
    for(const entry of entries.filter(e=>e.night_lantern)){const light=new PointLight('blueprint-L1-'+entry.id,new Vector3(entry.x,2.4,entry.z),scene);light.diffuse=Color3.FromHexString('#FFD394');light.range=5;light.intensity=0;light.setEnabled(false);lanterns.push(light);}
  }
  let disposed=false, lastUpdate=-Infinity, lastShadows:ShadowGenerator|null=options.getShadows();
  const dispose=()=>{
    if(disposed)return;disposed=true;diagnostics.status='DISPOSED';
    scene.onBeforeRenderObservable.remove(observer);
    for(const mesh of shadowed) lastShadows?.removeShadowCaster(mesh,false);
    for(const b of batches)for(const m of b.meshes)m.dispose(false,false);
    for(const m of templates)m.dispose(false,false);
    for(const m of materials)m.dispose(false,true);
    for(const m of extras)m.dispose(false,false);for(const m of extraMaterials)m.dispose(false,false);for(const l of lanterns)l.dispose();
    instanceMatrices.clear();motionParts.clear();
    if(import.meta.env.DEV && (window as unknown as {__xexoriaDressing?:unknown}).__xexoriaDressing === handle)
      delete (window as unknown as {__xexoriaDressing?:unknown}).__xexoriaDressing;
  };
  const handle={stats:()=>({...diagnostics,ambientAnimals:scene.metadata?.blueprintSheep?{status:scene.metadata.blueprintSheep.status,count:scene.metadata.blueprintSheep.count,triangles:scene.metadata.blueprintSheep.triangles,physics:scene.metadata.blueprintSheep.physics,nativeAdmission:scene.metadata.blueprintSheep.nativeAdmission}:undefined,missing:[...diagnostics.missing],errors:[...diagnostics.errors],blueprintItems:diagnostics.blueprintItems.map(item=>{const bodies=sourceDressing.blueprint.water_bodies.filter(w=>w.blueprint_id===item.id),waters=bodies.filter(w=>!('rain_only' in w&&w.rain_only)),rainBodies=bodies.filter(w=>'rain_only' in w&&w.rain_only),mounds=terrainSources.filter(m=>('blueprint_id' in m?m.blueprint_id:m.id)===item.id).length,visibleMounds=extras.filter(m=>m.metadata?.blueprintId===item.id).length,rainAccepted=scene.metadata?.naturalWater?.rainPuddles?.accepted??[];return {...item,requested:item.requested+bodies.length+mounds,resolved:item.resolved+(scene.metadata?.naturalWater?.ready?waters.length:0)+rainBodies.filter(w=>rainAccepted.includes(w.id)).length+visibleMounds,remaining:[...item.remaining]};})}),dispose};
  const observer=scene.onBeforeRenderObservable.add(()=>{
    if(disposed || diagnostics.status!=='READY' || !scene.activeCamera)return;
    const now=performance.now();if(now-lastUpdate<100)return;lastUpdate=now;
    const plan=dressingPlan(options.getProfile()), camera=scene.activeCamera.globalPosition;
    const frame=readWeatherFrame(scene),night=frame?Math.max(0,1-frame.appearance.daylight*3):0;
    // Keep the verified P0 light budget when P1 adds two arena braziers.
    const activeLanterns=new Set(night>0?lanterns.filter(l=>Vector3.DistanceSquared(l.position,camera)<10000)
      .sort((a,b)=>Vector3.DistanceSquared(a.position,camera)-Vector3.DistanceSquared(b.position,camera)||a.name.localeCompare(b.name)).slice(0,8):[]);
    for(const light of lanterns){
      const intensity=night*.85,enabled=activeLanterns.has(light);
      if(light.intensity!==intensity)light.intensity=intensity;
      // Babylon Light.setEnabled rescans every scene mesh even when the value has not changed.
      if(light.isEnabled()!==enabled)light.setEnabled(enabled);
    }
    const shadows=options.getShadows();
    if(shadows!==lastShadows) {
      for(const m of shadowed)lastShadows?.removeShadowCaster(m,false);
      lastShadows=shadows;
      if(options.shadowsEnabled)for(const m of shadowed)shadows.addShadowCaster(m,false);
    }
    diagnostics.visibleInstances=extras.length;diagnostics.draws=extras.length;diagnostics.triangles=extras.reduce((n,m)=>n+m.getTotalIndices()/3,0);
    const drawsByCell=new Map(terrainDraws);
    const focalVisibleLods:{id:string;asset:string;lod:number}[]=[];
    for(const batch of batches) {
      const visible=batch.slots.flatMap(slot=>{
        if(!dressingKeep(slot.entry,plan.density))return [];
        const range=dressingLodRanges(Math.hypot(camera.x-slot.entry.x,camera.z-slot.entry.z),slot.entry.landmark?{...plan,end:240,near:36,middle:80}:plan,slot.minimumLod)
          .find(r=>r.lod===batch.lod);
        return range?[{slot,range}]:[];
      });
      for(const {slot}of visible)if(focalMinimums.has(slot.entry.id))focalVisibleLods.push({id:slot.entry.id,asset:slot.entry.asset_id,lod:batch.lod});
      const signature=visible.map(v=>`${v.slot.entry.id}:${v.range.lower.toFixed(3)}:${v.range.upper.toFixed(3)}`).join('|');
      if(signature!==batch.signature) {
        batch.signature=signature;
        visible.forEach(({slot},i)=>batch.matrices.set(slot.matrix,i*16));
        for(const mesh of batch.meshes) {
          const oldPoolAnchors=mesh.metadata.lookV2PoolAnchors;
          mesh.metadata.lookV2PoolAnchors=visible.filter(({slot})=>slot.entry.night_lantern ||
            /lantern|lamp|brazier|campfire|torch|fire_glow|watch-?fire/i.test(slot.entry.asset_id)).map(({slot})=>[
            slot.entry.x,(options.getGroundHeight?.(slot.entry.x,slot.entry.z)??slot.entry.y)+(slot.entry.visual_base_y??0),slot.entry.z]);
          const emitterChanged=(Array.isArray(oldPoolAnchors)&&oldPoolAnchors.length>0)||mesh.metadata.lookV2PoolAnchors.length>0;
          if(!visible.length){mesh.thinInstanceCount=0;mesh.setEnabled(false);if(emitterChanged)notifyLookV2PoolEmitterChanged(mesh);continue;}
          instanceMatrices.get(mesh)!.set(batch.matrices);
          mesh.thinInstanceCount=visible.length;mesh.thinInstanceBufferUpdated('matrix');
          const plugin=DitheredTileFadeMaterialPlugin.GetOrCreate(mesh.material as PBRMaterial);
          visible.forEach(({range},i)=>plugin.setThinInstanceFadeBounds(mesh,i,range.lower,range.upper,false));
          plugin.commitThinInstanceFadeBounds(mesh);mesh.thinInstanceRefreshBoundingInfo(false);mesh.setEnabled(true);if(emitterChanged)notifyLookV2PoolEmitterChanged(mesh);
        }
      }
      if(visible.length&&frame)for(const mesh of batch.meshes){const motion=motionParts.get(mesh);if(!motion)continue;const angle=(frame.worldMs/1000%motion.period)*Math.PI*2/motion.period;
       const rotate=Matrix.Translation(-motion.pivot.x,-motion.pivot.y,-motion.pivot.z).multiply(Matrix.RotationAxis(motion.axis,angle)).multiply(Matrix.Translation(motion.pivot.x,motion.pivot.y,motion.pivot.z));
       const data=instanceMatrices.get(mesh)!;visible.forEach(({slot},i)=>data.set(rotate.multiply(Matrix.FromArray(slot.matrix)).asArray(),i*16));mesh.thinInstanceBufferUpdated('matrix');mesh.thinInstanceRefreshBoundingInfo(false);}
      if(visible.length) {
        diagnostics.visibleInstances+=visible.length;
        diagnostics.draws+=batch.meshes.reduce((n,m)=>n+m.subMeshes.length,0);
        diagnostics.triangles+=visible.length*batch.meshes.reduce((n,m)=>n+m.getTotalIndices()/3,0);
        const cell=batch.slots[0].cell;
        drawsByCell.set(cell,(drawsByCell.get(cell)??0)+batch.meshes.reduce((n,m)=>n+m.subMeshes.length,0));
      }
    }
    diagnostics.focalVisibleLods=focalVisibleLods;
    diagnostics.maxCellDraws=Math.max(0,...drawsByCell.values());
  });
  scene.onDisposeObservable.addOnce(dispose);
  if(import.meta.env.DEV)(window as unknown as {__xexoriaDressing?:unknown}).__xexoriaDressing=handle;
  const materialFor=(asset:DressingAsset)=>{
    const materialKey=dressingMaterialIdentity(asset);
    let material=familyMaterials.get(materialKey);if(material)return material;
    material=new PBRMaterial(`env-v3-${asset.family}-${asset.textures?.atlas??'legacy'}`,scene);material.metallic=0;material.roughness=.92;
    const atlas=asset.textures?.atlas;
    for(const [channel,slot] of [['albedo','albedoTexture'],['normal','bumpTexture'],['orm','metallicTexture']] as const) {
      if(asset.family==='cc0-mushroom'&&channel!=='albedo')continue;
      const hit=Object.entries(textures).find(([path])=>path.includes(`/${atlas}_${channel}-`) ||
        (asset.family==='cc0-mushroom'&&path.toLowerCase().includes('/mushrooms-')));
      if(!hit)throw new Error(`Dressing atlas missing: ${atlas} ${channel}`);
      const texture=new Texture(hit[1],scene,false,false);texture.gammaSpace=channel==='albedo';
      material[slot]=texture;
      if(channel==='orm')configureDressingOrm(material);
    }
    material.invertNormalMapX=!scene.useRightHandedSystem;material.invertNormalMapY=scene.useRightHandedSystem;
    if(asset.family==='flora') {material.albedoTexture!.hasAlpha=true;material.useAlphaFromAlbedoTexture=true;
      material.transparencyMode=PBRMaterial.MATERIAL_ALPHATEST;material.alphaCutOff=.45;material.backFaceCulling=false;}
    material.albedoColor=Color3.White();material.metadata={glow:false};
    if(waterArt&&asset.family==='stone')new WaterArtMossUpPlugin(material);
    DitheredTileFadeMaterialPlugin.GetOrCreate(material);materials.add(material);familyMaterials.set(materialKey,material);return material;
  };
  try {
    const grouped=new Map<string,Slot[]>();
    for(const entry of entries) {
      const asset=assets.get(entry.asset_id)!;
      const xyz=blueprintScale(entry,asset.bounds);
      const aquatic=entry.class==='lily_pad'||entry.class==='lotus';
      const supportY=entry.blueprint_id?(options.getGroundHeight?.(entry.x,entry.z)??entry.y):entry.y;
      const baseY=entry.visual_absolute_base_y??(supportY+(entry.visual_base_y??0));
      const y=entry.surface_y??(aquatic?-.3:baseY-blueprintFloor(entry,asset.bounds,xyz));
      const centreAtBounds=entry.blueprint_id&&!entry.anchor_at_pivot;
      const cx=centreAtBounds?(asset.bounds.min[0]+asset.bounds.max[0])/2*xyz[0]:0,cz=centreAtBounds?(asset.bounds.min[2]+asset.bounds.max[2])/2*xyz[2]:0;
      const matrix=Matrix.Compose(new Vector3(...xyz),Quaternion.RotationYawPitchRoll(entry.yaw,entry.pitch??0,entry.roll??0),new Vector3(entry.x-cx*Math.cos(entry.yaw)-cz*Math.sin(entry.yaw),y,entry.z+cx*Math.sin(entry.yaw)-cz*Math.cos(entry.yaw)));
      const cell=`${Math.floor(entry.x/64)},${Math.floor(entry.z/64)}`,key=`${cell}/${entry.asset_id}`;
      const slots=grouped.get(key)??[];slots.push({entry,matrix:new Float32Array(matrix.asArray()),cell,minimumLod:focalMinimums.get(entry.id)?.minimumLod??cellLods.get(cell)!.minimumLod});
      grouped.set(key,slots);
    }
    for(const id of [...new Set(entries.map(e=>e.asset_id))]) {
      const asset=assets.get(id)!;
      for(let lod=0;lod<3;lod++) {
        const keepMaterials=id==='cc0_kenney_bush'||asset.status==='CC0_STANDIN';
        const loaded=await ImportMeshAsync(id==='cc0_kenney_bush'?bushUrl:localUrl(asset.lods[Math.min(lod,asset.lods.length-1)].file),scene,
          {pluginExtension:'.glb',pluginOptions:{gltf:{skipMaterials:!keepMaterials}}});
        if(disposed){for(const m of loaded.meshes)m.dispose(false,true);return handle;}
        const parts:Mesh[]=[];
        for(const source of loaded.meshes) {
          if(!(source instanceof Mesh)||source.getTotalVertices()===0)continue;
          const moving=asset.motion?.nodeNames.some(name=>source.name.includes(name));
          const transform=source.computeWorldMatrix(true).clone(),motion=moving?{axis:Vector3.TransformNormal(Vector3.FromArray(asset.motion!.axis),transform).normalize(),pivot:Vector3.TransformCoordinates(Vector3.FromArray(asset.motion!.pivot),transform),period:asset.motion!.periodSeconds}:null;
          bakeDressingGeometry(source,{preserveColor:waterArt&&asset.family==='stone'});if(waterArt&&asset.family==='stone')packDressingVertexBuffers(source);source.name=`v3-template-${id}-${lod}`;
          if(motion)motionParts.set(source,motion);
          if(!keepMaterials)source.material=materialFor(asset);
          if(!source.material)throw new Error(`Dressing ${id} has no material`);
          if(id==='blueprint_cc0_palm' && source.material instanceof PBRMaterial && !source.material.backFaceCulling)
            source.material.twoSidedLighting=true;
          materials.add(source.material);source.setEnabled(false);source.isPickable=false;templates.push(source);parts.push(source);
        }
        for(const mesh of loaded.meshes)if(!parts.includes(mesh as Mesh)&&!mesh.isDisposed())mesh.dispose(false,false);
        for(const node of loaded.transformNodes)if(!node.isDisposed())node.dispose(false,false);
        for(const animation of loaded.animationGroups)animation.dispose();
        if(!parts.length)throw new Error(`Dressing ${id} has no geometry`);
        for(const [key,slots] of grouped) {
          if(slots[0].entry.asset_id!==id)continue;
          const batchParts=parts.flatMap(source=>{
            const repair=createL2BrazierRepairParts(source,id,slots.map(slot=>slot.entry.id));
            if(!repair)return [source];
            for(const material of repair.materials)materials.add(material);
            for(const part of repair.parts)templates.push(part);
            scene.metadata={...scene.metadata,l2BrazierRepairs:[...(scene.metadata?.l2BrazierRepairs??[]),{lod,...repair.diagnostics}]};
            return repair.parts;
          });
          const matrices=new Float32Array(slots.length*16);
          slots.forEach((s,i)=>matrices.set(s.matrix,i*16));
          const meshes=batchParts.map((source,part)=>{
            const mesh=source.clone(`v3-dressing-${key}-lod${lod}-${part}`,null,true)!;
            mesh.parent=null;mesh.isVisible=true;mesh.isPickable=false;mesh.receiveShadows=source.metadata?.l2BrazierPart!=='ember';mesh.metadata={...source.metadata,glow:false,dressingV3:true};
            if(slots.some(slot=>slot.entry.night_lantern))mesh.name+='-lantern';
            // Thin-instance/fade vertex bindings live on Geometry; sharing it aliases different cell capacities.
            mesh.makeGeometryUnique();
            if(waterArt&&asset.family==='stone')packDressingVertexBuffers(mesh);
            const ownedMatrices=new Float32Array(matrices);instanceMatrices.set(mesh,ownedMatrices);
            mesh.thinInstanceSetBuffer('matrix',ownedMatrices,16,false);mesh.thinInstanceCount=1;
            const motion=motionParts.get(source);if(motion)motionParts.set(mesh,motion);
            const plugin=DitheredTileFadeMaterialPlugin.GetOrCreate(mesh.material as PBRMaterial);
            plugin.setThinInstanceFadeBounds(mesh,0,0,1);mesh.freezeWorldMatrix();mesh.setEnabled(false);
            if(source.metadata?.l2BrazierPart!=='ember'&&slots.some(s=>s.entry.shadow)&&lod<2){shadowed.add(mesh);if(options.shadowsEnabled)options.getShadows().addShadowCaster(mesh,false);}
            return mesh;
          });
          batches.push({key,slots,lod,meshes,matrices,signature:''});
        }
      }
    }
    // Compile one instanced/dither variant per material before exposing any batch.
    const warmed=new Set<Material>();
    for(const batch of batches)for(const mesh of batch.meshes)if(mesh.material&&!warmed.has(mesh.material)) {
      warmed.add(mesh.material);await mesh.material.forceCompilationAsync(mesh,{useInstances:true});
    }
    if(!disposed)diagnostics.status='READY';
  } catch(error) {
    diagnostics.errors.push(String(error));console.warn('Sunmeadow v3 dressing load failed',error);dispose();
  }
  return handle;
}
