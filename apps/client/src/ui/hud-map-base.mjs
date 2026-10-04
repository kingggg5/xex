// Public world content is the sole cartographic source. No synthetic land fill.
export const MAP_BASE_LIMITS = Object.freeze({ rasterSize: 1024, bytes: 1024 * 1024, vertices: 40000, triangles: 40000, surfaces: 512, polygons: 512 });
const finite = Number.isFinite;
const positive = n => finite(n) && n > 0;

/** +X east/right, +Z north/up, with the live player at the chart centre. */
export function projectMapPoint(x, z, centerX, centerZ, extent, size = 256, inset = 16) {
  if (![x, z, centerX, centerZ, inset].every(finite) || !positive(extent) || !positive(size) || inset < 0 || inset >= size / 2) return null;
  const scale = (size / 2 - inset) / extent;
  return { x: size / 2 + (x - centerX) * scale, y: size / 2 - (z - centerZ) * scale };
}

/** Clip atlas source AND destination proportionally, never stretching edge pixels. */
export function mapBaseCrop(baseExtent, centerX, centerZ, viewExtent, rasterSize = 1024, size = 256, inset = 16) {
  if (![centerX, centerZ, inset].every(finite) || ![baseExtent, viewExtent, rasterSize, size].every(positive) || inset < 0 || inset >= size / 2) return null;
  const width = rasterSize * viewExtent / baseExtent * size / (size - 2 * inset);
  const left = rasterSize / 2 + centerX * rasterSize / (2 * baseExtent) - width / 2;
  const top = rasterSize / 2 - centerZ * rasterSize / (2 * baseExtent) - width / 2;
  const sx = Math.max(0, left), sy = Math.max(0, top);
  const sw = Math.min(rasterSize, left + width) - sx, sh = Math.min(rasterSize, top + width) - sy;
  if (sw <= 0 || sh <= 0) return null;
  return { sx, sy, sw, sh, dx: (sx - left) / width * size, dy: (sy - top) / width * size, dw: sw / width * size, dh: sh / width * size };
}

/** Copy only bounded X/Z coordinates and indices; release the full bundle afterward. */
export function compileMapBase(bundle, extent) {
  if (!positive(extent) || !Array.isArray(bundle?.zones)) return null;
  const matches = bundle.zones.filter(z => positive(z?.half_extent) && Math.abs(z.half_extent - extent) < .01);
  // The current HUD supplies extent, not zone ID. Ambiguous extents must stay blank.
  if (matches.length !== 1) return null;
  const zone = matches[0];
  const meshes = [], polygons = [], routes = [];
  let bytes = 0, vertexCount = 0, triangleCount = 0;
  const reserve = count => { bytes += count; if (bytes > MAP_BASE_LIMITS.bytes) throw new RangeError("Map geometry budget"); };
  const point = p => Array.isArray(p) && p.length >= 2 && finite(p[0]) && finite(p[1]) && Math.abs(p[0]) <= extent && Math.abs(p[1]) <= extent;
  const polygon = (kind, points) => {
    if (!Array.isArray(points) || points.length < 3 || points.length > 256 || !points.every(point)) return;
    if (polygons.length >= MAP_BASE_LIMITS.polygons) throw new RangeError("Map polygon budget");
    reserve(points.length * 8); polygons.push({ kind, points: new Float32Array(points.flatMap(p => [p[0], p[1]])) });
  };
  try {
    const surfaces = zone.city_traversal?.surfaces ?? [];
    if (!Array.isArray(surfaces) || surfaces.length > MAP_BASE_LIMITS.surfaces) return null;
    const allowed = new Set(["ground", "path", "plaza", "plaza_base", "terrace", "ramp", "stairs", "castle_forecourt", "bridge"]);
    for (const surface of surfaces) {
      if (!allowed.has(surface?.kind) || !Array.isArray(surface.vertices) || !Array.isArray(surface.triangles)) continue;
      const vertices = surface.vertices, triangles = surface.triangles;
      if (!vertices.every(v => Array.isArray(v) && v.length >= 3 && v.every(finite) && Math.abs(v[0]) <= extent && Math.abs(v[2]) <= extent)) continue;
      if (!triangles.every(t => Array.isArray(t) && t.length === 3 && t.every(i => Number.isInteger(i) && i >= 0 && i < vertices.length))) continue;
      vertexCount += vertices.length; triangleCount += triangles.length;
      if (vertexCount > MAP_BASE_LIMITS.vertices || triangleCount > MAP_BASE_LIMITS.triangles) return null;
      reserve(vertices.length * 8 + triangles.length * 12);
      meshes.push({ kind: surface.kind, vertices: new Float32Array(vertices.flatMap(v => [v[0], v[2]])), indices: new Uint32Array(triangles.flat()) });
    }
    for (const cell of (zone.terrain_cells ?? []).slice(0, 128)) {
      const b = cell?.bounds_xz;
      if (!Array.isArray(b) || b.length !== 4 || !b.every(finite) || b[0] >= b[1] || b[2] >= b[3]) continue;
      polygon("ground", [[b[0], b[2]], [b[1], b[2]], [b[1], b[3]], [b[0], b[3]]]);
    }
    for (const blocker of (zone.city_traversal?.blockers ?? []).slice(0, 512)) {
      if (["water_hazard", "solid_structure", "wall"].includes(blocker?.kind)) polygon(blocker.kind, blocker.polygon_xz);
    }
    for (const route of (zone.world_routes ?? []).slice(0, 64)) {
      if (!positive(route?.width) || route.width > 20 || !Array.isArray(route.points) || route.points.length < 2 || route.points.length > 80 || !route.points.every(point)) continue;
      reserve(route.points.length * 8); routes.push({ width: route.width, points: new Float32Array(route.points.flat()) });
    }
    if (!meshes.length && !polygons.length) return null;
    return Object.freeze({ extent, meshes, polygons, routes, byteLength: bytes, vertexCount, triangleCount });
  } catch { return null; }
}

/** One 2D atlas per mounted chart; never an engine texture or render pass. */
export function rasterizeMapBase(model, canvas) {
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) return false;
  canvas.width = canvas.height = MAP_BASE_LIMITS.rasterSize;
  const size = canvas.width, scale = size / (2 * model.extent);
  const px = x => size / 2 + x * scale, py = z => size / 2 - z * scale;
  ctx.fillStyle = "#101d2b"; ctx.fillRect(0, 0, size, size);
  const colors = { ground: "#435947", water_hazard: "#2b6576", solid_structure: "#263746", wall: "#68716c", path: "#a89d7f", plaza: "#b0a38b", plaza_base: "#918773", terrace: "#7d866f", ramp: "#baad90", stairs: "#b0a68f", castle_forecourt: "#a89d88", bridge: "#c3b492" };
  const mesh = m => {
    ctx.beginPath();
    for (let i = 0; i < m.indices.length; i += 3) {
      const a = m.indices[i] * 2, b = m.indices[i + 1] * 2, c = m.indices[i + 2] * 2;
      ctx.moveTo(px(m.vertices[a]), py(m.vertices[a + 1])); ctx.lineTo(px(m.vertices[b]), py(m.vertices[b + 1])); ctx.lineTo(px(m.vertices[c]), py(m.vertices[c + 1])); ctx.closePath();
    }
    ctx.fillStyle = colors[m.kind]; ctx.fill();
  };
  const poly = p => {
    ctx.beginPath(); ctx.moveTo(px(p.points[0]), py(p.points[1]));
    for (let i = 2; i < p.points.length; i += 2) ctx.lineTo(px(p.points[i]), py(p.points[i + 1]));
    ctx.closePath(); ctx.fillStyle = colors[p.kind]; ctx.fill();
  };
  model.meshes.filter(m => m.kind === "ground").forEach(mesh);
  model.polygons.filter(p => p.kind === "ground").forEach(poly);
  model.polygons.filter(p => p.kind === "water_hazard").forEach(poly);
  model.meshes.filter(m => m.kind !== "ground").forEach(mesh);
  model.polygons.filter(p => p.kind !== "ground" && p.kind !== "water_hazard").forEach(poly);
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (const route of model.routes) {
    ctx.beginPath(); ctx.moveTo(px(route.points[0]), py(route.points[1]));
    for (let i = 2; i < route.points.length; i += 2) ctx.lineTo(px(route.points[i]), py(route.points[i + 1]));
    ctx.strokeStyle = "#b7aa8b"; ctx.lineWidth = route.width * scale; ctx.stroke();
  }
  return true;
}

/** Reference-count an in-flight public request. Keep only one compact completed map. */
export function createMapBaseLoader(fetcher = (...args) => fetch(...args), url = "/content/bundle.json") {
  let entry = null;
  return {
    acquire(extent) {
      if (!positive(extent)) return { promise: Promise.resolve(null), release() {} };
      if (entry && entry.extent !== extent && entry.refs > 0) return { promise: Promise.resolve(null), release() {} };
      if (!entry || entry.extent !== extent) {
        const current = { extent, refs: 0, complete: false, controller: new AbortController(), promise: null };
        entry = current;
        current.promise = Promise.resolve().then(() => fetcher(url, { signal: current.controller.signal, credentials: "omit" }))
          .then(response => response.ok ? response.json() : null).then(bundle => current.controller.signal.aborted ? null : compileMapBase(bundle, extent))
          .catch(() => null).then(model => { current.complete = true; if (!model && entry === current) entry = null; return model; });
      }
      const current = entry; current.refs++;
      let released = false;
      return { promise: current.promise, release() {
        if (released) return; released = true; current.refs--;
        if (current.refs === 0 && !current.complete) { current.controller.abort(); if (entry === current) entry = null; }
      } };
    }
  };
}

export const sharedMapBaseLoader = createMapBaseLoader();
