/** CPU-only review paths through the selected, already-admitted city field.
 * No navigation/gameplay data or assets are changed by this tool.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
import { selectActiveCityRevision } from '../apps/client/scripts/build-city-asset.mjs';
import { parseCityTraversal, sampleCityHeight, moveGroundedCapsule } from '../apps/client/src/grounded-city.mjs';
import { staticColliderBoxes } from '../apps/client/src/coordinate-collision.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const selection = selectActiveCityRevision(root);
const bundlePath = path.join(root, 'content/build', selection.content_hash, 'bundle.json');
const bytes = readFileSync(bundlePath);
const zone = JSON.parse(bytes.toString('utf8')).zones.find(zone => zone.city_traversal);
const field = parseCityTraversal(zone.city_traversal, zone.half_extent);
const boxes = staticColliderBoxes(zone.static_colliders);
const PLAYER_RADIUS = 0.35, SEARCH_RADIUS = 0.45, HEIGHT = 1.8;
const SAMPLE_M = 0.05, GRID_M = 1, MAX_NODES = 30000, MAX_SMOOTH_TESTS = 2000;
const f = Math.fround;
const metrics = { movement_queries: 0, support_queries: 0 };

function position(point) {
  const x = f(point[0]), z = f(point[1]);
  metrics.support_queries++;
  const y = sampleCityHeight(field, x, z);
  return y === null ? null : { x, y, z };
}
function motion(p, dx, dz, radius) {
  metrics.movement_queries++;
  return moveGroundedCapsule(p, { x: dx, z: dz }, radius, HEIGHT, boxes, zone.half_extent, field);
}
function clearStart(p, radius) {
  if (!p) return false;
  // A zero-length movement cannot expose blocked status. Probe four tiny,
  // reversible moves with the actual controller instead of inventing collision.
  for (const [dx, dz] of [[0.002, 0], [-0.002, 0], [0, 0.002], [0, -0.002]]) {
    const q = motion(p, dx, dz, radius);
    if (q.x !== f(p.x + f(dx)) || q.z !== f(p.z + f(dz))) return false;
  }
  return true;
}
function segment(a, b, radius = SEARCH_RADIUS) {
  let p = position(a);
  if (!clearStart(p, radius)) return { passed: false, samples: 0, failure: { kind: 'blocked-or-unsupported-start', point: a } };
  const target = { x: f(b[0]), z: f(b[1]) };
  const initialDistance = Math.hypot(target.x - p.x, target.z - p.z);
  const cap = Math.ceil(initialDistance / SAMPLE_M) + 16;
  let samples = 0, maxRise = 0, minY = p.y, maxY = p.y;
  for (let index = 0; index < cap; index++) {
    const dx = target.x - p.x, dz = target.z - p.z, distance = Math.hypot(dx, dz);
    if (distance <= 0.00001) return { passed: true, samples, max_rise_m: maxRise, min_y: minY, max_y: maxY, end: p };
    const scale = Math.min(SAMPLE_M, distance) / distance;
    const mx = f(dx * scale), mz = f(dz * scale);
    const wanted = { x: f(p.x + mx), z: f(p.z + mz) };
    const q = motion(p, mx, mz, radius); samples++;
    if (q.x !== wanted.x || q.z !== wanted.z) return { passed: false, samples, failure: { kind: 'controller-rejected-or-slid', from: p, wanted, actual: q } };
    maxRise = Math.max(maxRise, Math.abs(q.y - p.y)); minY = Math.min(minY, q.y); maxY = Math.max(maxY, q.y); p = q;
  }
  return { passed: false, samples, failure: { kind: 'bounded-segment-budget', point: p, target } };
}
function both(a, b) { return segment(a, b).passed && segment(b, a).passed; }

class Heap {
  data = [];
  push(item) { let i = this.data.length; this.data.push(item); while (i) { const parent = (i - 1) >> 1; if (this.data[parent].score <= item.score) break; this.data[i] = this.data[parent]; i = parent; } this.data[i] = item; }
  pop() { const first = this.data[0], last = this.data.pop(); if (this.data.length) { let i = 0; while (i * 2 + 1 < this.data.length) { let child = i * 2 + 1; if (child + 1 < this.data.length && this.data[child + 1].score < this.data[child].score) child++; if (this.data[child].score >= last.score) break; this.data[i] = this.data[child]; i = child; } this.data[i] = last; } return first; }
}

function findConnector(start, end) {
  if (both(start, end)) return { passed: true, points: [start, end], expanded_nodes: 0, discovered_nodes: 0, method: 'verified-direct-corridor' };
  const bounds = { minX: Math.max(-zone.half_extent + 1, Math.min(start[0], end[0]) - 32), maxX: Math.min(zone.half_extent - 1, Math.max(start[0], end[0]) + 32), minZ: Math.max(-zone.half_extent + 1, Math.min(start[1], end[1]) - 32), maxZ: Math.min(zone.half_extent - 1, Math.max(start[1], end[1]) + 32) };
  const key = (x, z) => `${x},${z}`;
  const point = (x, z) => [f(start[0] + x * GRID_M), f(start[1] + z * GRID_M)];
  const first = { ix: 0, iz: 0, point: start, distance: 0, previous: null, closed: false };
  const nodes = new Map([[key(0, 0), first]]), heap = new Heap(), edges = new Map();
  heap.push({ node: first, distance: 0, score: Math.hypot(end[0] - start[0], end[1] - start[1]) });
  let expanded = 0, goal = null, budgetReached = false;
  while (heap.data.length && expanded < MAX_NODES) {
    const item = heap.pop(), node = item.node;
    if (node.closed || item.distance !== node.distance) continue;
    node.closed = true; expanded++;
    if (Math.hypot(end[0] - node.point[0], end[1] - node.point[1]) <= GRID_M * 2.5 && both(node.point, end)) { goal = node; break; }
    for (const [ox, oz] of [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [-1, 1], [1, -1], [1, 1]]) {
      const ix = node.ix + ox, iz = node.iz + oz, id = key(ix, iz), target = point(ix, iz);
      if (target[0] < bounds.minX || target[0] > bounds.maxX || target[1] < bounds.minZ || target[1] > bounds.maxZ) continue;
      let neighbor = nodes.get(id);
      if (neighbor?.closed) continue;
      if (!neighbor && nodes.size >= MAX_NODES) { budgetReached = true; continue; }
      const edgeKey = [key(node.ix, node.iz), id].sort().join('>');
      let clear = edges.get(edgeKey);
      if (clear === undefined) { clear = both(node.point, target); edges.set(edgeKey, clear); }
      if (!clear) continue;
      const distance = node.distance + Math.hypot(target[0] - node.point[0], target[1] - node.point[1]);
      if (!neighbor) { neighbor = { ix, iz, point: target, distance: Infinity, previous: null, closed: false }; nodes.set(id, neighbor); }
      if (distance >= neighbor.distance) continue;
      neighbor.distance = distance; neighbor.previous = node;
      heap.push({ node: neighbor, distance, score: distance + Math.hypot(end[0] - target[0], end[1] - target[1]) });
    }
  }
  if (!goal) return { passed: false, expanded_nodes: expanded, discovered_nodes: nodes.size, failure: budgetReached ? '30000-node-budget' : 'no-controller-valid-grid-corridor', search_bounds: bounds };
  const raw = [end]; for (let node = goal; node; node = node.previous) raw.push(node.point); raw.reverse();
  const points = [raw[0]]; let current = 0, smoothingTests = 0;
  while (current < raw.length - 1) {
    let next = current + 1;
    for (let index = raw.length - 1; index > current + 1 && smoothingTests < MAX_SMOOTH_TESTS; index--) { smoothingTests++; if (both(raw[current], raw[index])) { next = index; break; } }
    points.push(raw[next]); current = next;
  }
  return { passed: true, points, expanded_nodes: expanded, discovered_nodes: nodes.size, raw_nodes: raw.length, smoothing_tests: smoothingTests, method: 'bounded-A-star-then-bidirectional-controller-string-pull' };
}

function verifyPolyline(points, radius) {
  let count = 0, maxRise = 0, minY = Infinity, maxY = -Infinity, length = 0;
  for (let index = 1; index < points.length; index++) {
    const result = segment(points[index - 1], points[index], radius);
    if (!result.passed) return { ...result, passed: false, failed_segment: index - 1 };
    count += result.samples; maxRise = Math.max(maxRise, result.max_rise_m); minY = Math.min(minY, result.min_y); maxY = Math.max(maxY, result.max_y);
    length += Math.hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1]);
  }
  return { passed: true, samples: count, length_m: length, max_adjacent_height_delta_m: maxRise, min_y: minY, max_y: maxY, end: position(points.at(-1)) };
}

const wizardDown = [[-61, 252], [-57.6, 246.5], [-51, 237.2], [-50.4, 236.35]];
const recipes = [
  { id: 'fountain-west-to-castle-avenue-planter-bypass', points: [[-20, 156], [-24, 164], [-24, 206], [0, 216]] },
  { id: 'castle-avenue-to-wizard-approach', connector: [[0, 216], [-50.4, 236.35]] },
  { id: 'wizard-ascent-to-terrace', points: [...wizardDown].reverse() },
  { id: 'wizard-descent-to-windmill-approach', prefix: wizardDown, connector: [[-50.4, 236.35], [44, 226]] },
  { id: 'windmill-approach-to-east-bank-exit', connector: [[44, 226], [10.1, 140]], suffix: [[10.1, -2], [-3, -3]] },
  { id: 'east-bank-reentry-to-plaza', points: [[-3, -3], [10.1, -2], [10.1, 140], [18, 144], [20, 156], [20, 176]] },
];
const routes = [];
for (const recipe of recipes) {
  const started = performance.now();
  const connector = recipe.connector ? findConnector(...recipe.connector) : null;
  if (connector && !connector.passed) { routes.push({ id: recipe.id, ...connector, elapsed_ms: performance.now() - started }); console.log(`${recipe.id}: FAIL (${connector.failure})`); continue; }
  const assembled = recipe.points ?? [...(recipe.prefix ?? []).slice(0, -1), ...connector.points, ...(recipe.suffix ?? [])];
  const points = assembled.map(point => point.map(value => Number(value.toFixed(4))));
  const forward = verifyPolyline(points, PLAYER_RADIUS), reverse = verifyPolyline([...points].reverse(), PLAYER_RADIUS);
  const marginForward = verifyPolyline(points, SEARCH_RADIUS), marginReverse = verifyPolyline([...points].reverse(), SEARCH_RADIUS);
  const passed = forward.passed && reverse.passed && marginForward.passed && marginReverse.passed;
  routes.push({ id: recipe.id, passed, points_xz: points, connector: connector ? { ...connector, points: undefined } : null, player_forward: forward, player_reverse: reverse, clearance_forward: marginForward, clearance_reverse: marginReverse, elapsed_ms: performance.now() - started });
  console.log(`${recipe.id}: ${passed ? 'PASS' : 'FAIL'}; ${points.length} waypoints; ${forward.length_m?.toFixed(2) ?? '?'}m`);
}
const sentinel = clearStart(position([-16.55, 165.4]), PLAYER_RADIUS);
const report = { schema: 'xexoria.city-review-paths/1', status: routes.every(route => route.passed) ? 'PASS' : 'PARTIAL', revision: selection.revision, content_hash: selection.content_hash, content_bundle_sha256: createHash('sha256').update(bytes).digest('hex'), runtime_sha256: selection.files['city-runtime.meshopt.glb'].sha256, field_stats: field.stats, static_box_count: boxes.length, controller: { radius_m: PLAYER_RADIUS, height_m: HEIGHT, margin_radius_m: SEARCH_RADIUS, clearance_margin_m: SEARCH_RADIUS - PLAYER_RADIUS, sample_spacing_m: SAMPLE_M, grid_spacing_m: GRID_M, max_A_star_nodes_per_connector: MAX_NODES }, native_reported_stop: { point: [-16.55, 165.4], current_position_clear: sentinel, note: 'A reported stop position can be outside a barrier; this is not interpreted as proof of initial overlap.' }, routes, metrics, limits: ['CPU controller/support validation only; actual camera/input/browser review remains required.', 'No teleportation, map, gameplay, collision dataset, shader or scene edits.', 'Routes depend on the exact selected runtime and hashed content above.'] };
const output = path.join(root, 'planning/evidence/city-review-paths-20261001.json');
writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`);
console.log(`Review path receipt: ${path.relative(root, output)} (${report.status})`);
if (report.status !== 'PASS') process.exitCode = 1;
