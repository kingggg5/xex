import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { capsuleOverlapsBox, moveCapsule, staticColliderBoxes } from '../apps/client/src/coordinate-collision.mjs';

// Candidate-only authoring. No canonical source, bundle, runtime or art is written.
// `--write` creates the three review artifacts; otherwise verifies them read-only.
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sourceFiles = ['content/source/zones.json', 'content/source/npcs.json', 'content/source/quests.json',
  'content/source/enemies.json', 'content/source/manifest.json', 'planning/world-expansion/world-layout-v1.json',
  'apps/protocol/coordinate-fixture-v1.json'];
const read = (path) => JSON.parse(readFileSync(resolve(root, path), 'utf8'));
const sha = (path) => createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex');
const source = read(sourceFiles[0]);
const sourceZone = source.zones.find((zone) => zone.id === 1);
const candidate = structuredClone(source);
const zone = candidate.zones.find((entry) => entry.id === 1);
const npcs = read(sourceFiles[1]);
const quests = read(sourceFiles[2]);
const enemies = read(sourceFiles[3]);
const manifest = read(sourceFiles[4]);
const layout = read(sourceFiles[5]);
const fixture = read(sourceFiles[6]);
const speed = manifest.player.speed;
const radius = fixture.player_capsule.radius;
const height = fixture.player_capsule.height;
const rounded = (value) => Number(value.toFixed(3));
const length = (points) => points.slice(1).reduce((sum, point, index) => sum + Math.hypot(point[0] - points[index][0], point[1] - points[index][1]), 0);
const zoneIndex = candidate.zones.indexOf(zone);
const patches = [];
const replace = (path, before, value) => patches.push({ op: 'test', path, value: before }, { op: 'replace', path, value });

// Keep complete 64m art tiles. Translating by +22m closes the existing empty connector.
for (const [index, cell] of zone.terrain_cells.entries()) {
  const before = structuredClone(cell.bounds_xz);
  cell.bounds_xz[2] += 22;
  cell.bounds_xz[3] += 22;
  replace(`/zones/${zoneIndex}/terrain_cells/${index}/bounds_xz`, before, cell.bounds_xz);
}
for (const [index, prop] of zone.world_props.entries()) {
  const before = prop.z;
  prop.z += 22;
  // Re-anchor the two focal landmarks at the front of the second clearing.
  if (prop.id === 'sunmeadow_windstone') prop.z = -60;
  if (prop.id === 'sunmeadow_broken_cart') prop.z = -70;
  replace(`/zones/${zoneIndex}/world_props/${index}/z`, before, prop.z);
}

// Existing encounter rows retain definition, order and population; only their anchors move.
const spawnPositions = [[-8,6],[0,9],[8,5],[-9,-3],[-3,0],[9,-5],[-7,13],[7,13],[0,17],[11,0],[-7,-60],[8,-66],[0,-73]];
assert.equal(spawnPositions.length, zone.monster_spawns.length);
for (const [index, spawn] of zone.monster_spawns.entries()) {
  const before = structuredClone(spawn);
  [spawn.x, spawn.z] = spawnPositions[index];
  replace(`/zones/${zoneIndex}/monster_spawns/${index}`, before, spawn);
}
for (const [index, poi] of zone.pois.entries()) {
  if (poi.id === 'south_trail_marker') {
    const before = poi.z;
    poi.z = -60;
    replace(`/zones/${zoneIndex}/pois/${index}/z`, before, poi.z);
  }
  if (poi.id === 'hunt_clearing') {
    const before = structuredClone(poi);
    poi.x = 0; poi.z = 5;
    replace(`/zones/${zoneIndex}/pois/${index}`, before, poi);
  }
}
const route = zone.world_routes.find((entry) => entry.id === 'southbound_trail');
const beforeRoute = structuredClone(route.points);
route.points = [[0,-24],[-12,-28],[-18,-36],[-18,-46],[-10,-54],[0,-61],[5,-70],[0,-80]];
replace(`/zones/${zoneIndex}/world_routes/${zone.world_routes.indexOf(route)}/points`, beforeRoute, route.points);

// New cliff is a visual occluder beside a flat route. Its ground footprint is authoritative.
// No elevated walkway, teleport, walkable cliff top or changed player scale is implied.
const bluff = { id: 'sunmeadow_compact_inner_bluff', center: [5,5,-38], size: [24,10,16] };
zone.static_colliders.push(bluff);
patches.push({ op: 'add', path: `/zones/${zoneIndex}/static_colliders/-`, value: bluff });
const derivedColliders = (entry) => [...entry.static_colliders, ...entry.world_props.map((prop) => ({
  id: prop.id, center: [prop.x, prop.collider_size[1] / 2, prop.z], size: [...prop.collider_size],
}))];
const colliders = derivedColliders(zone);
const boxes = staticColliderBoxes(colliders);
const clearings = [
  { id: 'windmark_hunt', center_xz: [0,5], bounds_xz: [-15,16,-10,21], source_spawn_indices: [...Array(10).keys()],
    quest_ids: ['three_windmarks'], poi_ids: ['windmark_1','windmark_2','windmark_3','hunt_clearing'],adjacent_poi_ids:['lookout'],
    purpose: 'Starter quest and first battle; existing ten encounter rows arranged within one focal area.' },
  { id: 'windstone_glade', center_xz: [0,-68], bounds_xz: [-18,18,-86,-48], source_spawn_indices: [10,11,12],
    quest_ids: [], poi_ids: ['south_trail_marker'], source_prop_ids: ['sunmeadow_windstone','sunmeadow_broken_cart'],
    purpose: 'Second battle and short landmark exploration; three existing advanced encounter rows.' },
];
const inBounds = ([x,z], [minX,maxX,minZ,maxZ], margin=0) => x >= minX+margin && x <= maxX-margin && z >= minZ+margin && z <= maxZ-margin;
const groundBounds = [-50,50,-42,58];
const supported = (point) => inBounds(point,groundBounds) || zone.terrain_cells.some((cell) => inBounds(point,cell.bounds_xz));
let samples = 0;
let minimumEdgeClearance = Infinity;
let closestCollider = null;
function edgeClearance(point) {
  for (const collider of colliders) {
    const [cx,cy,cz] = collider.center, [w,h,d] = collider.size;
    if (cy+h/2 <= 0 || cy-h/2 >= height) continue;
    const distance = Math.hypot(Math.max(Math.abs(point[0]-cx)-w/2,0), Math.max(Math.abs(point[1]-cz)-d/2,0)) - radius;
    if (distance < minimumEdgeClearance) { minimumEdgeClearance = distance; closestCollider = collider.id; }
  }
}
function validatePolyline(points, corridorWidth = 0) {
  for (let i=1;i<points.length;i++) {
    const [ax,az]=points[i-1], [bx,bz]=points[i];
    const distance=Math.hypot(bx-ax,bz-az), steps=Math.max(1,Math.ceil(distance/.1));
    const nx=-(bz-az)/distance,nz=(bx-ax)/distance;
    for (let step=0;step<=steps;step++) {
      for (const offset of corridorWidth ? [-corridorWidth/2,0,corridorWidth/2] : [0]) {
        const point=[ax+(bx-ax)*step/steps+nx*offset,az+(bz-az)*step/steps+nz*offset];
        assert.ok(supported(point),`Unsupported ground ${point}`);
        assert.ok(boxes.every((box)=>!capsuleOverlapsBox({x:point[0],z:point[1]},radius,height,box)),`Blocked corridor ${point}`);
        edgeClearance(point); samples++;
      }
    }
  }
}
validatePolyline(route.points,route.width);
const markerBefore=[-7.5,-96.5], markerAfter=[-7.5,-59]; // Outside marker collider, within2.3m of POI.
const cartBefore=[8,-105],cartAfter=[8,-70]; // Outside2.4m cart collider.
const encounterCentroid = (entry) => [10,11,12].reduce((point,index)=>[
  point[0]+entry.monster_spawns[index].x/3,point[1]+entry.monster_spawns[index].z/3],[0,0]);
const measuredRoutes = [
  { id:'entry_to_end_of_authored_trail', label:'Entry to terminal trail bend',
    before:[[0,-24],...beforeRoute], after:route.points },
  { id:'entry_marker_cart', label:'Entry → safe Windstone approach → safe cart approach',
    before:[[0,-24],[0,-40],[.2,-64],[.9,-82],[-.4,-96.5],markerBefore,[0,-96.5],[8,-101],cartBefore],
    after:[...route.points.slice(0,5),markerAfter,[0,-61],[3,-66],cartAfter] },
  { id:'sella_to_second_battle',label:'Sella → second encounter centroid via curved trail',
    before:[[2,-14],[0,-24],[0,-40],[.2,-64],[.9,-82],[-.4,-101],encounterCentroid(sourceZone)],
    after:[[2,-14],...route.points.slice(0,6),encounterCentroid(zone)] },
];
const sourceBoxes=staticColliderBoxes(derivedColliders(sourceZone));
let baselineSamples=0;
for (const item of measuredRoutes) {
  for (let i=1;i<item.before.length;i++) {
    const [ax,az]=item.before[i-1],[bx,bz]=item.before[i],steps=Math.ceil(Math.hypot(bx-ax,bz-az)/.1);
    for (let step=0;step<=steps;step++) {
      const point=[ax+(bx-ax)*step/steps,az+(bz-az)*step/steps];
      assert.ok(inBounds(point,groundBounds) || inBounds(point,[-64,64,-64,-42]) || sourceZone.terrain_cells.some((cell)=>inBounds(point,cell.bounds_xz)),`Unsupported baseline ${point}`);
      assert.ok(sourceBoxes.every((box)=>!capsuleOverlapsBox({x:point[0],z:point[1]},radius,height,box)),`Blocked baseline ${point}`);
      baselineSamples++;
    }
  }
}
for (const item of measuredRoutes) {
  validatePolyline(item.after);
  item.before_m=rounded(length(item.before)); item.after_m=rounded(length(item.after));
  item.before_walk_s=rounded(length(item.before)/speed); item.after_walk_s=rounded(length(item.after)/speed);
  item.saved_walk_s=rounded((length(item.before)-length(item.after))/speed);
  item.reduction_pct=rounded(100*(1-length(item.after)/length(item.before)));
}
// Drive the actual client planar collision helper at20Hz along every candidate lane.
let movementTicks=0;
for (const item of measuredRoutes) {
  let position={x:item.after[0][0],z:item.after[0][1]};
  for (const target of item.after.slice(1)) {
    let attempts=0;
    while (Math.hypot(target[0]-position.x,target[1]-position.z) > .001) {
      assert.ok(++attempts < 3000,`Movement stuck on ${item.id}`);
      const dx=target[0]-position.x,dz=target[1]-position.z,distance=Math.hypot(dx,dz),step=Math.min(speed/manifest.tick_hz,distance);
      const next=moveCapsule(position,{x:dx/distance*step,z:dz/distance*step},radius,height,boxes,zone.half_extent);
      assert.ok(Math.hypot(next.x-position.x,next.z-position.z)>0,`No progress ${item.id}`);
      position=next; movementTicks++;
    }
  }
}
assert.equal(clearings.length,2);
const assigned=clearings.flatMap((clearing)=>clearing.source_spawn_indices);
assert.equal(new Set(assigned).size,zone.monster_spawns.length);
const enemyIds=new Set(enemies.enemies.map((entry)=>entry.id));
for (const [index,spawn] of zone.monster_spawns.entries()) {
  assert.ok(enemyIds.has(spawn.enemy));
  assert.equal(spawn.enemy,sourceZone.monster_spawns[index].enemy);
  assert.equal(clearings.filter((clearing)=>inBounds([spawn.x,spawn.z],clearing.bounds_xz)).length,1);
  assert.ok(boxes.every((box)=>!capsuleOverlapsBox(spawn,radius,height,box)),`Spawn inside collider ${index}`);
}
for (const kind of ['terrain_cells','world_props','pois','world_routes','static_colliders']) {
  const ids=zone[kind].map((entry)=>entry.id); assert.equal(new Set(ids).size,ids.length,`Duplicate ${kind}`);
  ids.forEach((id)=>assert.match(id,/^[a-z][a-z0-9_]*$/));
}
for (const cell of zone.terrain_cells) {
  const [minX,maxX,minZ,maxZ]=cell.bounds_xz;
  assert.equal(maxX-minX,64); assert.equal(maxZ-minZ,64); assert.equal(maxZ,groundBounds[2]);
  assert.equal(cell.surface_y,0); assert.equal(cell.neighbors.north,'starter_field');
}
assert.equal(zone.terrain_cells[0].neighbors.east,zone.terrain_cells[1].id);
assert.equal(zone.terrain_cells[1].neighbors.west,zone.terrain_cells[0].id);
for (const prop of zone.world_props) {
  const cell=zone.terrain_cells.find((entry)=>entry.id===prop.cell);
  assert.ok(cell && inBounds([prop.x,prop.z],cell.bounds_xz));
  const [minX,maxX,minZ,maxZ]=cell.bounds_xz;
  assert.ok(prop.x-prop.collider_size[0]/2>=minX && prop.x+prop.collider_size[0]/2<=maxX);
  assert.ok(prop.z-prop.collider_size[2]/2>=minZ && prop.z+prop.collider_size[2]/2<=maxZ);
  const original=sourceZone.world_props.find((entry)=>entry.id===prop.id);
  for (const key of ['height','scale','yaw','collider_size','cell','kind']) assert.deepEqual(prop[key],original[key]);
}
const quest=quests.quests.find((entry)=>entry.id==='three_windmarks');
assert.ok(quest && npcs.npcs.some((npc)=>npc.id===quest.giver));
assert.equal(zone.monster_spawns.filter((spawn)=>spawn.enemy==='puddlekin').length,3);
for (const id of ['entry','regroup','sella','windmark_1','windmark_2','windmark_3','lookout','city_gate']) {
  assert.deepEqual(zone.pois.find((entry)=>entry.id===id),sourceZone.pois.find((entry)=>entry.id===id));
}
for (const id of ['city_gate','plaza_fountain','magic_castle']) {
  const anchor=layout.poi_anchors.find((entry)=>entry.id===id);
  assert.deepEqual(anchor.world_xz,[0,{city_gate:24,plaza_fountain:176,magic_castle:272}[id]]);
}
function finiteTree(value) {
  if (typeof value==='number') assert.ok(Number.isFinite(value));
  else if (Array.isArray(value)) value.forEach(finiteTree);
  else if (value&&typeof value==='object') Object.values(value).forEach(finiteTree);
}
finiteTree(candidate);
// Validate the concrete guarded patch itself, not only the separately built full payload.
const patched=structuredClone(source);
for (const operation of patches) {
  const segments=operation.path.split('/').slice(1).map((part)=>part.replaceAll('~1','/').replaceAll('~0','~'));
  let parent=patched;
  for (const part of segments.slice(0,-1)) parent=parent[part];
  const key=segments.at(-1);
  if (operation.op==='test') assert.deepEqual(parent[key],operation.value,`Patch guard ${operation.path}`);
  else if (operation.op==='add'&&key==='-') parent.push(structuredClone(operation.value));
  else parent[key]=structuredClone(operation.value);
}
assert.deepEqual(patched,candidate,'RFC6902 patch must reproduce full candidate exactly');

const plan = {
  schema:'xexoria.sunmeadow-compact-candidate/1',status:'candidate-only-not-live',units:'meters',
  activation:{allowed:false,source_loader_status:'BLOCKED_MISSING_VISUAL_PACKAGE',
    required_visual_package:'sunmeadow_compact_inner_bluff',reason:'No render package or measured matching visual/collider bounds exist. Do not activate the new collider as an invisible wall.',
    concurrency:'Static layout is not a player-capacity proof. Existing stage/server 50 cap and 500 goal remain unqualified.'},
  project_id:'project-a6dcbc9c-dcdf-4efe-9428-b88a9b5694bf',run_id:'RUN-20260923-mmorpg-plan-v3',
  source_sha256:Object.fromEntries(sourceFiles.map((path)=>[path,sha(path)])),
  invariants:{zone_id:1,half_extent_m:308,surface_y:0,art_cell_m:64,player_radius_m:radius,player_height_m:height,
    walk_speed_m_s:speed,tick_hz:manifest.tick_hz,sprint_m_s:speed*manifest.player.sprint_mult,
    city_gate_xz:[0,24],plaza_fountain_xz:[0,176],magic_castle_xz:[0,272],character_scale_changed:false,building_scale_changed:false,
    traversal:'Current server/client planar XZ moveCapsule. Heightfield, ramps, cliff-top travel and future Rapier work are unqualified.'},
  clearings,
  terrain_translation_xz:[0,22],starter_ground_bounds_xz:groundBounds,
  removed_empty_connector:{before_bounds_xz:[-64,64,-64,-42],after_bounds_xz:null,length_removed_m:22,
    reason:'Translated complete 64m terrain cells meet the existing starter edge at Z=-42.'},
  source_patch:{format:'RFC6902',target:'content/source/zones.json',operations:patches},candidate_zones_source:candidate,
  dependencies:{
    terrain_cells:zone.terrain_cells.map((cell,index)=>({id:cell.id,asset:cell.asset,before_bounds_xz:sourceZone.terrain_cells[index].bounds_xz,
      after_bounds_xz:cell.bounds_xz,neighbors:cell.neighbors,required:'World-authored GLB ground/props need+22m translation or regeneration; mesh scale stays1.'})),
    props:zone.world_props.map((prop,index)=>({id:prop.id,cell:prop.cell,kind:prop.kind,before_xz:[sourceZone.world_props[index].x,sourceZone.world_props[index].z],after_xz:[prop.x,prop.z],
      unchanged_scale:prop.scale,unchanged_height_m:prop.height,unchanged_collider_size:prop.collider_size,
      action:['sunmeadow_windstone','sunmeadow_broken_cart'].includes(prop.id)?'translate-then-reanchor-focal-landmark':'translate22m'})),
    colliders:colliders.map((collider)=>({id:collider.id,action:collider.id===bluff.id?'add-bluff':sourceZone.static_colliders.some((entry)=>entry.id===collider.id)?'preserve-town-gate':'translate-derived-prop',
      before:derivedColliders(sourceZone).find((entry)=>entry.id===collider.id)??null,after:collider})),
    monsters:zone.monster_spawns.map((spawn,index)=>({source_index:index,enemy:spawn.enemy,before_xz:[sourceZone.monster_spawns[index].x,sourceZone.monster_spawns[index].z],after_xz:[spawn.x,spawn.z],
      clearing_id:clearings.find((clearing)=>clearing.source_spawn_indices.includes(index)).id,
      unchanged_tuning:enemies.enemies.find((entry)=>entry.id===spawn.enemy)})),
    pois:zone.pois.map((poi)=>({id:poi.id,before:sourceZone.pois.find((entry)=>entry.id===poi.id),after:poi,
      action:['hunt_clearing','south_trail_marker'].includes(poi.id)?'reposition':'preserve'})),
    npcs:{action:'preserve',source:'content/source/npcs.json',ids:npcs.npcs.map((npc)=>npc.id),sella_interaction_radius_m:2},
    quests:{action:'preserve',source:'content/source/quests.json',ids:quests.quests.map((entry)=>entry.id),
      verification:'Three unchanged distinct windmark POIs and all three existing puddlekin spawns remain in first clearing; giver Sella unchanged.'},
    routes:[{id:route.id,before_points:beforeRoute,after_points:route.points,width_m:route.width,
      stubbed_future_routes:['starter_to_south_loop'],required:'Preserve planned-not-traversable status; no lava route or portal added.'}],
    world_layout_patch:{target:'planning/world-expansion/world-layout-v1.json',runtime_extension:{surface_y:0,connector_bounds_xz:null,detail_load_trigger_z:-24,
      cells:zone.terrain_cells.map((cell)=>({id:cell.id,asset:cell.asset,bounds_xz:{min_x:cell.bounds_xz[0],max_x:cell.bounds_xz[1],min_z:cell.bounds_xz[2],max_z:cell.bounds_xz[3]},neighbor_seams:cell.neighbors})),
      world_prop_ids:zone.world_props.map((prop)=>prop.id)},poi_anchors:[{id:'south_trail_marker',world_xz:[-9.5,-60]}],
      routes:[{id:route.id,width_m:route.width,world_xz:route.points}],macro_grid_policy:'Preserve world-v1 macro/region64m indexing; retain source IDs as legacy package IDs, add explicit translated runtime bounds rather than pretending grid indices moved.'},
    integration_files:[
      {path:'apps/server/src/content.rs',requirement:'starter_field seam special-case hardcodesmaxZ=-64; derive/check starter edge-42 for this candidate before server validation.'},
      {path:'apps/client/src/environment.ts',requirement:'Remove22m connector, consume candidate curved route, add bluff render geometry matching authoritativeAABB, update translated GLB placement/import; no Y-only visual walking changes.'},
      {path:'apps/client/src/scene.ts',requirement:'Existing createSouthboundCellLoader(-40) trigger; shift to-24 or distance from package policy so translated detail appears before starter seam.'},
      {path:'assets/blender/world/build_sunmeadow_cells.py',requirement:'Translate/rebuild complete 64m ground packages+22m,22 props+22m and re-anchor Windstone/cart to candidateZ=-60/-70; preserve source prop IDs/scales. Required inner-bluff hero package remains absent.'},
      {path:'assets/models/world-v1/manifest.json',requirement:'Regenerate cell manifest/source hashes, review renders and bounds; canonicaleditablemaster remains untouched until candidate promotion.'},
      ...zone.terrain_cells.map((cell)=>({path:`apps/client/src/assets/world/${cell.asset}.meshopt.glb`,requirement:'Regenerate matching candidate ground/prop anchors; old export is stale against candidate.'})),
      {path:'tools/verify_world_layout.py',requirement:'Current verifier hardcodes22m connector and64m indexed blueprint; add explicit compact runtime contract and null connector handling.'},
      {path:'tools/southbound-cell-smoke.mjs',requirement:'Replace hardcodedZ=-86/-94 walking waypoints with compact route points and candidate landmark approaches.'},
      {path:'tools/quest-route-smoke.mjs',requirement:'Existing proof uses bundlePOIs and live monster targets rather than fixed combat anchors. Rerun unchanged activation/defeat/return completion assertions after promotion.'},
    ]},
  visibility_and_streaming:{status:'authoring-contract-not-runtime-qualified',
    inner_bluff:{collider_id:bluff.id,bounds_xz:[-7,17,-46,-30],visual_height_m:10,source_asset_required:true,
      blocks_centerline_between_clearings:true,walkable_top:false,route_around:'west atX=-18',camera_line_of_sight_test_required:true},
    high_detail_packages:[
      {id:'sunmeadow_windmark_focal',bounds_xz:clearings[0].bounds_xz,near_load_distance_m:34,far_retire_distance_m:46,
        assets:'Existing starter quest objects and near foliage; preserve NPC/quest interaction geometry.'},
      {id:'sunmeadow_windstone_focal',bounds_xz:clearings[1].bounds_xz,near_load_distance_m:34,far_retire_distance_m:46,
        assets:'24 existing source props in translated64m packages; windstone/cart are focal details.'},
      {id:'sunmeadow_compact_inner_bluff',bounds_xz:[-7,17,-46,-30],near_load_distance_m:34,far_retire_distance_m:46,
        assets:'Required new cliff screen; coarse silhouette remains available to avoid visibility holes.'}],
    lod_policy:{near_full_m:24,mid_reduced_m:48,far_silhouette_m:90,hysteresis_m:8,physical_colliders:'Retain authoritative collision regardless of visual LOD.',
      caution:'Existing createLazyLoadOnce loads both full cells and does not release them; staged per-focal near packages and disposal are required integration work, not claimed implemented here.'},
    qualification:['Fixed-camera before/after entrance and second-clearing screenshots','LOD swap and look-back seam test','Actual phone frame-time/GPU memory route','No empty or disappearing cliff silhouette']},
  travel:{model:'Planar polyline distance / actual 4.5m/s unbuffed walking speed; timings exclude combat, input/network delays and quest channels.',
    sprint_model:'6.75m/s from existing 1.5 multiplier; not used to inflate walking savings.',routes:measuredRoutes,
    previous_live_receipt:{path:'planning/evidence/sunmeadow-composition-v2-movement-20260930.json',travel_s:27.26,collision_samples:543,
      comparability:'Existing authenticated source layout run, different driving path and endpoint. It is provenance, not a candidate runtime benchmark.'}},
  validation:{result:'PASS-static-candidate',reused_module:'apps/client/src/coordinate-collision.mjs',corridor_sample_step_m:.1,
    capsule_samples:samples,baseline_capsule_samples:baselineSamples,movement_helper_ticks:movementTicks,minimum_capsule_edge_clearance_m:rounded(minimumEdgeClearance),closest_collider_id:closestCollider,
    assertions:['Finite coordinates and unique IDs','13 unchanged enemy rows assigned exactly once to 2 disjoint clearing footprints','24 props remain inside complete 64m cells with unchanged sizes',
      'Reciprocal east/west seam and continuous flat ground at Z=-42','Full 3.8m lane including capsule clearance','Actual 20Hz planar movement helper reaches all candidate route endpoints',
      'RFC6902 guarded patch reproduces full candidate exactly','Source comparison polylines are supported and collision-free',
      'NPC+quest+three required windmarks preserved','Town24/176/272 anchors and308m boundary unchanged'],
    not_run:['Canonical build_content (would overwrite live bundle and currently rejects translated starter seam)','Live authenticated server/client compact route','Mobilevisual/memory/frame-time','Rendered cliff sightlines','Heightfield/Rapier/ramp traversal'],
    runtime_promotion_blocker:'BLOCKED_MISSING_VISUAL_PACKAGE: bluff render package and measured matching collider bounds required before activation. Then update explicit dependencies, regenerate matching art, build one shared server/client bundle and rerun live movement+quest proofs.'},
};
finiteTree(plan);

const metricRows=measuredRoutes.map((entry)=>`| ${entry.label} | ${entry.before_m}m / ${entry.before_walk_s}s | ${entry.after_m}m / ${entry.after_walk_s}s | ${entry.saved_walk_s}s (${entry.reduction_pct}%) |`).join('\n');
const propRows=plan.dependencies.props.map((prop)=>`| ${prop.id} | ${prop.cell} | ${prop.before_xz.join(', ')} | ${prop.after_xz.join(', ')} |`).join('\n');
const monsterRows=plan.dependencies.monsters.map((entry)=>`| ${entry.source_index} | ${entry.enemy} | ${entry.before_xz.join(', ')} | ${entry.after_xz.join(', ')} | ${entry.clearing_id} |`).join('\n');
const doc=`# Sunmeadow compact candidate v1\n\nCandidate only, activation blocked: The candidate SourceLoader gate declares BLOCKED_MISSING_VISUAL_PACKAGE for the required inner-bluff visual and verified collider bounds. Do not introduce its collider as an invisible wall. Stage/server 50 cap and 500 goal remain unqualified. All coordinates and an RFC6902 patch are in [sunmeadow-compact-v1.json](../planning/sunmeadow-compact-v1.json). Run \`node tools/compact-region-candidate.mjs\` for read-only validation; \`--write\` regenerates only this document, that JSON and the SVG. No live content, canonical art or generated bundle is changed.\n\nThe stage has exactly two combat clearings. Windmark Hunt keeps the ten existing starter encounter rows and all three windmarks in a 31×31m footprint around (0,5). Windstone Glade arranges the remaining three rows in a 36×38m footprint around (0,-68), beside the existing Windstone and broken cart. Sella remains at (2,-14); the three_windmarks quest and its three puddlekin targets remain intact. Footprints contain spawn anchors; enemy aggro/leash behavior remains unchanged and can extend beyond those footprints.\n\nTranslate both entire 64m terrain packages and their 24 props by 22m north, then re-anchor Windstone/cart to Z=-60/-70: west(-64..0,-106..-42), east(0..64,-106..-42). Their northern edges meet the existing starter floor at Z=-42. The 22m empty connector disappears. Character, building, tree, prop, collider and terrain-meter scales are preserved. City gate(0,24), fountain(0,176), castle(0,272), the 308m zone boundary and blueprint town are preserved.\n\nThe 3.8m route bends west around a new inner bluff: (0,-24) → (-12,-28) → (-18,-36) → (-18,-46) → (-10,-54) → (0,-61) → (5,-70) → (0,-80). The bluff's XZ footprint is -7..17 by -46..-30; its 10m visual height and matching candidate AABB interrupt the straight view between clearing centers. A new visual cliff package is required before promotion. Actual camera sightlines, turning and LOD visibility still need rendered evidence. Players walk on Y=0 throughout; this does not qualify ramps, cliff-top movement or a future Rapier heightfield.\n\n![Same-scale source and candidate route](../planning/evidence/sunmeadow-compact-route-v1.svg)\n\n| Route | Source distance / walk | Candidate distance / walk | Saving |\n|---|---:|---:|---:|\n${metricRows}\n\nWalking speed is ${speed}m/s from content/source/manifest.json; capsule radius ${radius}m and height ${height}m come from the shared fixture. Distances follow the explicitly recorded polylines and safe landmark approach positions rather than passing through solid marker/cart centers. The terminal trail comparison moves the destination forward; this is the intended shorter stage extent. Combat/channel/input/network time is excluded. Prior 27.26s authenticated source proof is retained as provenance and is not represented as a candidate benchmark.\n\nThe candidate validator imports the existing client planar collision helper. It checks ${samples} capsule samples at 0.1m spacing across the full route width and side branches and drives ${movementTicks} actual 20Hz helper steps to reach every candidate endpoint. Minimum tested capsule-edge gap is ${rounded(minimumEdgeClearance)}m at ${closestCollider}. It verifies all IDs, finite coordinates, prop-cell bounds, seam continuity, quest dependencies and spawn membership. The current server seam special-case still hardcodes Z=-64; therefore the source candidate cannot be promoted merely by copying its JSON.\n\n## Complete dependency ledger\n\nAll 24 source prop IDs preserve their identity: 22 move +22m with their package, while Windstone/cart translate and re-anchor toward the second clearing entrance, and all 24 derived static colliders move with them (including the two independently re-anchored focal landmarks). The two explicit town gate wing colliders are preserved. A new sunmeadow_compact_inner_bluff collider is added. The machine-readable ledger includes before/after centers and full collider sizes for all 27 candidate colliders.\n\n| Prop ID | Cell | Before X,Z | After X,Z |\n|---|---|---:|---:|\n${propRows}\n\n| Source spawn index | Existing enemy | Before X,Z | After X,Z | Clearing |\n|---:|---|---:|---:|---|\n${monsterRows}\n\nOnly hunt_clearing POI moves to(0,5), and south_trail_marker moves from(-9.5,-97.5) to(-9.5,-60). Entry, regroup, Sella, three windmarks, lookout and city_gate remain fixed. NPC and quest source files, enemy tuning, drops, respawns, aggro and leash lengths remain fixed. southbound_trail retains its ID and 3.8m width with the new points above. No lava endpoint or portal is added; starter_to_south_loop stays planned and non-traversable.\n\nBefore integration, update the server starter_field seam check, remove the hardcoded22m client connector, update the route preload trigger, translate/rebuild both world-authored GLBs plus source/meshopt hashes, and update world-v1 runtime_extension cells/route/marker without renumbering macro grid packages. tools/verify_world_layout.py currently assumes the old connector and needs a compact runtime contract. Movement smoke uses fixedZ=-86/-94 targets and needs candidate route waypoints; quest smoke already follows live monster targets and must be rerun. Full exact dependencies are in the JSON.\n\nNear detail contracts are 24m full,48m reduced and90m silhouette with 8m hysteresis. Package prefetch is 34m and  retirement 46m from package bounds. Authoring separates first-clearing, Windstone and bluff packages; matching physical collision remains present across visual LOD. Existing lazy loading loads both full cells once and retains them; per-focal release and replacements need implementation and a phone route before any memory or performance claim.\n\nPromotion requires matching server/client bundle and art hashes, authenticated compact-route and quest completion proofs, cliff/camera/LOD look-back screenshots, and actual phone frame-time and memory results. Heightfield and Rapier traversal remain separate future engine work.\n`;

const sx=(x)=>500+x*4.4,sy=(z)=>190+(30-z)*4.4;
const rect=(bounds,fill,stroke,dash='')=>`<rect x="${sx(bounds[0])}" y="${sy(bounds[3])}" width="${(bounds[1]-bounds[0])*4.4}" height="${(bounds[3]-bounds[2])*4.4}" fill="${fill}" stroke="${stroke}" ${dash?`stroke-dasharray="${dash}"`:''}/>`;
const poly=(points,color,width=3,dash='')=>`<polyline points="${points.map(([x,z])=>`${sx(x)},${sy(z)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="${width}" ${dash?`stroke-dasharray="${dash}"`:''} stroke-linejoin="round" stroke-linecap="round"/>`;
const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1080" viewBox="0 0 1000 1080">
<rect width="1000" height="1080" fill="#101b25"/><g font-family="Arial,sans-serif" fill="#edf5ef"><text x="45" y="47" font-size="28" font-weight="bold">SUNMEADOW · TWO COMPACT CLEARINGS</text><text x="45" y="77" font-size="15">Candidate only · actual meter coordinates · +Z north/up · planar ground Y=0</text>
<text x="45" y="112" font-size="16">Town baseline stays: gate Z=24 → fountain Z=176 (152m) → castle Z=272 (96m)</text><text x="45" y="139" font-size="14" fill="#bdd4cb">Town is outside this route viewport; character, building and prop scales remain unchanged.</text>
${rect([-40,40,-42,28],'#163528','#426b51')}${rect([-40,40,-106,-42],'#1d3b36','#7fba9e')}${rect([-40,40,-128,-64],'none','#647781','7 5')}
${[24,0,-24,-42,-64,-80,-106,-128].map((z)=>`<line x1="270" y1="${sy(z)}" x2="730" y2="${sy(z)}" stroke="#486459" stroke-dasharray="3 5"/><text x="222" y="${sy(z)+5}" font-size="13">${z}</text>`).join('')}
<text x="194" y="190" font-size="13">Z(m)</text><text x="485" y="168" font-size="14">N ↑</text>
${clearings.map((clearing)=>rect(clearing.bounds_xz,'#335746','#7abb93')).join('')}${rect([-7,17,-46,-30],'#8d785c','#d7c4a0')}
${poly([[0,-24],...beforeRoute],'#8697a7',3,'8 5')}${poly(route.points,'#ffe2a0',5)}
${zone.world_props.map((prop)=>`<circle cx="${sx(prop.x)}" cy="${sy(prop.z)}" r="4" fill="${['trail_marker','broken_cart','stone_pillar'].includes(prop.kind)?'#b5c9dc':'#72a16f'}"/>`).join('')}
${zone.monster_spawns.map((spawn)=>`<circle cx="${sx(spawn.x)}" cy="${sy(spawn.z)}" r="6" fill="#f39373" stroke="#301a1c"/>`).join('')}
${zone.pois.filter((poi)=>poi.id.startsWith('windmark')).map((poi)=>`<rect x="${sx(poi.x)-4}" y="${sy(poi.z)-4}" width="8" height="8" fill="#a0d9f4"/>`).join('')}
<circle cx="${sx(2)}" cy="${sy(-14)}" r="5" fill="#dfc5fc"/><text x="${sx(2)+12}" y="${sy(-14)+4}" font-size="13">Sella stays(2,-14)</text>
<text x="${sx(0)+15}" y="${sy(24)-9}" font-size="14">CITY GATE(0,24)</text><text x="592" y="${sy(7)}" font-size="14">FIRST BATTLE</text><text x="592" y="${sy(7)+20}" font-size="12">10 existing spawns</text>
<text x="535" y="${sy(-35)}" font-size="12">10m bluff screen</text><text x="535" y="${sy(-35)+17}" font-size="12">walk around west</text>
<text x="595" y="${sy(-63)}" font-size="14">SECOND BATTLE</text><text x="595" y="${sy(-63)+20}" font-size="12">3 existing spawns</text>
<text x="325" y="${sy(-60)+20}" font-size="12">Windstone</text><text x="557" y="${sy(-70)+18}" font-size="12">Broken cart</text>
<text x="739" y="${sy(-42)+5}" font-size="12">New seam:-42</text><text x="739" y="${sy(-106)+5}" font-size="12">New tile edge:-106</text><text x="739" y="${sy(-128)+5}" font-size="12">Old tile edge:-128</text>
<line x1="300" y1="925" x2="388" y2="925" stroke="#edf5ef" stroke-width="3"/><text x="326" y="948" font-size="13">20m</text>
<text x="45" y="986" font-size="15"><tspan fill="#ffe2a0">— candidate curved path</tspan><tspan dx="28" fill="#8697a7">- - old path</tspan><tspan dx="28" fill="#f39373">● unchanged enemy definitions</tspan></text>
<text x="45" y="1017" font-size="14">Entry-to-trail-end walk: ${measuredRoutes[0].before_walk_s}s → ${measuredRoutes[0].after_walk_s}s at4.5m/s; destination moves forward.</text>
<text x="45" y="1046" font-size="13" fill="#bdd4cb">22 props translate22m;2 focal landmarks re-anchor; full64m tiles preserved. Art, camera/LOD and phone proof still required.</text></g></svg>\n`;

const outputs = [['planning/sunmeadow-compact-v1.json',JSON.stringify(plan,null,2)+'\n'],['docs/sunmeadow-compact-layout.md',doc],['planning/evidence/sunmeadow-compact-route-v1.svg',svg]];
if (process.argv.includes('--write')) {
  for (const [path,value] of outputs) {mkdirSync(dirname(resolve(root,path)),{recursive:true});writeFileSync(resolve(root,path),value);}
} else {
  for (const [path,value] of outputs) assert.equal(readFileSync(resolve(root,path),'utf8'),value,`Stale candidate ${path}; review source changes before --write.`);
}
console.log(JSON.stringify({result:'PASS-static-candidate',written:process.argv.includes('--write'),clearings:clearings.length,monsters:zone.monster_spawns.length,
  props:zone.world_props.length,colliders:colliders.length,capsule_samples:samples,movement_ticks:movementTicks,
  minimum_edge_clearance_m:rounded(minimumEdgeClearance),travel:measuredRoutes.map(({id,before_walk_s,after_walk_s,saved_walk_s})=>({id,before_walk_s,after_walk_s,saved_walk_s})),
  promotion_requires:'Server seam validation, matching art+bundle, live quest/movement and phone/camera/LOD proof.'},null,2));
