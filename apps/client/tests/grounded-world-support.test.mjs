import test from'node:test';import assert from'node:assert/strict';import{readFileSync}from'node:fs';
import{parseCityTraversal,sampleCityHeight,moveGroundedCapsule}from'../src/grounded-city.mjs';
const rect=(id,x0,x1,z0,z1,y)=>({id,kind:'ground',vertices:[[x0,y,z0],[x1,y,z0],[x1,y,z1],[x0,y,z1]],triangles:[[0,1,2],[0,2,3]]});
const fixture=()=>({schema:'xexoria.city-traversal/1',units:'metres',city_bounds:{min_x:-10,max_x:10,min_z:-10,max_z:10},contract:{max_step_m:.36,max_slope_degrees:50,feet_offset_m:.015,query_epsilon_m:.00005,max_movement_substep_m:.1},surfaces:[rect('city-west',-10,-1,-10,10,0),{id:'remote-six-metre-ramp',kind:'ramp',vertices:[[20,0,-40],[22,0,-40],[22,6,-16],[20,6,-16]],triangles:[[0,1,2],[0,2,3]]},rect('remote-six-metre-top',20,22,-16,-14,6)],blockers:[]});
const world=()=>{const input=fixture();input.schema='xexoria.city-traversal/2';input.contract.world_support=true;return input;};
const near=(a,b)=>assert.ok(typeof a==='number'&&Math.abs(a-b)<.0001,`${a} != ${b}`);

test('absent/false flag preserves v1 flat outside support and source JSON without mutation',()=>{
 for(const flag of[undefined,false]){const input=fixture();if(flag!==undefined)input.contract.world_support=flag;const before=JSON.stringify(input),field=parseCityTraversal(input);assert.equal(field.schema,'xexoria.city-traversal/1');assert.equal(field.worldSupport,false);assert.equal(sampleCityHeight(field,21,-15),0);assert.equal(sampleCityHeight(field,0,0),null);assert.equal(JSON.stringify(input),before);}
});
test('schema version and boolean flag fail closed for stale clients and malformed input',()=>{
 const legacy=fixture();legacy.contract.world_support=true;assert.throws(()=>parseCityTraversal(legacy),/schema2/);
 for(const flag of[undefined,false]){const input=fixture();input.schema='xexoria.city-traversal/2';if(flag!==undefined)input.contract.world_support=flag;assert.throws(()=>parseCityTraversal(input),/schema2/);}
 for(const flag of[null,'true','false',0,1,[],{},undefined]){const input=fixture();input.contract.world_support=flag;assert.throws(()=>parseCityTraversal(input),/boolean/);}
 const parsed=parseCityTraversal(world());assert.equal(parsed.schema,'xexoria.city-traversal/2');assert.equal(parsed.worldSupport,true);
});
test('v2 samples explicit remote ramp/top, retains outside fallback and interior null gaps',()=>{
 const field=parseCityTraversal(world());near(sampleCityHeight(field,21,-28),3);near(sampleCityHeight(field,21,-15),6);assert.equal(sampleCityHeight(field,30,-28),0);assert.equal(sampleCityHeight(field,0,0),null);assert.equal(sampleCityHeight(field,NaN,-28),null);
});
test('capsule actually climbs and returns down six metres without a visual Y offset or teleport',()=>{
 const field=parseCityTraversal(world());let p={x:21,y:0,z:-40.25};for(let i=0;i<99;i++)p=moveGroundedCapsule(p,{x:0,z:.25},.35,1.8,[],308,field);near(p.z,-15.5);near(p.y,6);for(let i=0;i<99;i++)p=moveGroundedCapsule(p,{x:0,z:-.25},.35,1.8,[],308,field);near(p.z,-40.25);near(p.y,0);
 const wrong={x:21,y:0,z:-15};assert.deepEqual(moveGroundedCapsule(wrong,{x:0,z:.1},.35,1.8,[],308,field),wrong);const cliff=moveGroundedCapsule({x:21,y:6,z:-14.05},{x:0,z:.3},.35,1.8,[],308,field);assert.ok(cliff.z<=-14);near(cliff.y,6);
});
test('world support does not admit roofs or unsafe remote slopes',()=>{
 const roof=world();roof.surfaces.push({...rect('remote-roof',24,26,-30,-28,5),kind:'roof'});assert.throws(()=>parseCityTraversal(roof),/roof/);
 const steep=world();steep.surfaces.push({id:'unsafe-remote-face',kind:'ramp',vertices:[[24,0,-30],[26,0,-30],[26,6,-29],[24,6,-29]],triangles:[[0,1,2],[0,2,3]]});const field=parseCityTraversal(steep);assert.equal(field.stats.skippedTriangles,2);assert.equal(sampleCityHeight(field,25,-29.5),0);assert.equal(sampleCityHeight(field,0,0),null);
});
test('canonical content remains v1 with world support absent/off',()=>{
 const source=JSON.parse(readFileSync(new URL('../../../content/source/zones.json',import.meta.url)));for(const zone of source.zones.filter(z=>z.city_traversal)){assert.equal(zone.city_traversal.schema,'xexoria.city-traversal/1');assert.ok(zone.city_traversal.contract.world_support===undefined||zone.city_traversal.contract.world_support===false);const field=parseCityTraversal(zone.city_traversal,zone.half_extent);assert.equal(field.worldSupport,false);}
});
