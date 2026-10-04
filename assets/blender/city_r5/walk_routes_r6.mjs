// CPU route walk of the S01-S05 city loop on a traversal field, with the shared client controller.
// gate -> ring/canal bridges -> fountain loop -> west houses + ring road + east market -> castle door,
// plus wizard and windmill spurs. Every route both directions, player radius 0.35 m and margin 0.45 m.
//   node assets/blender/city_r5/walk_routes_r6.mjs --traversal <city-traversal-v1.json> --out <report.json> [--label r6]
// This is candidate evidence only: root must still verify Rust server movement and native walking.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const { parseCityTraversal, sampleCityHeight, moveGroundedCapsule } = await import(new URL('file:///' + path.join(root, 'apps/client/src/grounded-city.mjs').replace(/\\/g, '/')));
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? [...a, [v.slice(2), all[i + 1]]] : a), []));
const bytes = readFileSync(args.traversal);
const data = JSON.parse(bytes);
const field = parseCityTraversal(data, 4096);
const HEIGHT = 1.8, STEP = 0.05;
const routes = {
  'S01 gate to bridges': [[10.1, 8], [10.1, 24], [10.1, 64], [-10.1, 64], [-10.1, 102], [10.1, 102], [10.1, 133], [10.1, 141]],
  'S02 plaza entry and fountain loop': [[10.1, 141], [12.5, 150], [21, 160], [22, 176], [15.6, 191.6], [0, 198], [-15.6, 191.6], [-22, 176], [-15.6, 160.4], [0, 154], [15.6, 160.4]],
  'S03 west houses, ring road and market': [[-22, 176], [-52, 167], [-58, 179.5], [-88, 177.5], [-98, 164], [-98, 146], [-114.5, 129], [-110, 114], [-110.5, 102], [-100, 90], [-60, 72], [0, 64], [60, 72], [100, 91], [82, 102], [80, 120], [84, 134], [75, 135], [66, 138], [64, 148], [60, 154], [50, 157], [40, 160], [22, 170]],
  'S04 castle stairs to door': [[0, 198], [0, 216], [0, 245], [0, 258]],
  'S05a wizard spur': [[-12, 190.5], [-27.4, 209.1], [-42, 226.8], [-48, 234], [-50.4, 236.35], [-51, 237.2], [-57.6, 246.5], [-61, 252]],
  'S05b windmill spur': [[13.2, 191], [29, 208.9], [44, 226], [80, 264], [90, 276]],
};
function walk(points, radius) {
  let p = { x: points[0][0], z: points[0][1], y: sampleCityHeight(field, points[0][0], points[0][1]) };
  if (p.y === null) return { passed: false, failure: { kind: 'no-support-at-start', at: points[0] } };
  let samples = 0, maxStep = 0, length = 0;
  for (let s = 1; s < points.length; s++) {
    const [ax, az] = [p.x, p.z], [bx, bz] = points[s];
    const L = Math.hypot(bx - ax, bz - az);
    length += L;
    const n = Math.max(1, Math.ceil(L / STEP));
    for (let i = 1; i <= n; i++) {
      const tx = ax + (bx - ax) * i / n, tz = az + (bz - az) * i / n;
      const q = moveGroundedCapsule(p, { x: tx - p.x, z: tz - p.z }, radius, HEIGHT, [], 4096, field);
      samples++;
      const gap = Math.hypot(q.x - tx, q.z - tz);
      if (gap > 0.002) return { passed: false, samples, segment: s - 1, failure: { kind: 'blocked-or-unsupported', wanted: [tx, tz], actual: [q.x, q.y, q.z], support_y: sampleCityHeight(field, tx, tz) } };
      maxStep = Math.max(maxStep, Math.abs(q.y - p.y));
      p = q;
    }
  }
  return { passed: true, samples, length_m: Number(length.toFixed(2)), max_step_m: Number(maxStep.toFixed(4)), end: [p.x, p.y, p.z] };
}
const results = [];
for (const [id, pts] of Object.entries(routes)) {
  for (const dir of ['forward', 'reverse']) {
    const seq = dir === 'forward' ? pts : [...pts].reverse();
    for (const radius of [0.35, 0.45]) results.push({ id, direction: dir, radius_m: radius, ...walk(seq, radius) });
  }
}
const report = { schema: 'xexoria.city-route-walk/1', label: args.label || '', passed: results.every(r => r.passed), traversal: path.relative(root, args.traversal),
  traversal_sha256: createHash('sha256').update(bytes).digest('hex'), source_master_sha256: data.source?.master_sha256, field_stats: field.stats,
  controller: { height_m: HEIGHT, probe_step_m: STEP, radii_m: [0.35, 0.45], static_boxes: 'none (city blockers are inside the field)' },
  routes, results, limits: ['Client CPU controller only; Rust server parity, native camera walking and snapback checks remain with root.'] };
writeFileSync(args.out, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ passed: report.passed, field: field.stats, failures: results.filter(r => !r.passed).map(r => ({ id: r.id, dir: r.direction, r: r.radius_m, f: r.failure })) }, null, 0));
