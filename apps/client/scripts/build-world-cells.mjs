import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const clientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(clientRoot, '../..');
const sourcePath = path.join(root, 'content/source/zones.json');
const blenderScript = path.join(root, 'assets/blender/world/build_sunmeadow_cells.py');
const sourceMaster = path.join(root, 'assets/models/world-v1/sunmeadow_south_cells.blend');
const reviewImage = path.join(root, 'assets/models/world-v1/review/sunmeadow_south_cells.png');
const detailReview = path.join(root, 'assets/models/world-v1/review/sunmeadow_waystone_closeup.png');
const manifestPath = path.join(root, 'assets/models/world-v1/manifest.json');
const textureBuilder = path.join(root, 'tools/build_world_textures.py');
const cli = path.join(clientRoot, 'node_modules/@gltf-transform/cli/bin/cli.js');
const blender = process.env.BLENDER_BIN || 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe';
const python = process.env.PYTHON_BIN || 'python';
const cellTriangleLimit = 40_000;
const cellByteLimit = 2 * 1024 * 1024;

function run(executable, args) {
  const result = spawnSync(executable, args, { cwd: root, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`World-cell build step failed with exit ${result.status}.`);
}

function sha256(pathname) {
  return createHash('sha256').update(readFileSync(pathname)).digest('hex');
}

function inspectGlb(pathname) {
  const bytes = readFileSync(pathname);
  if (bytes.toString('ascii', 0, 4) !== 'glTF' || bytes.readUInt32LE(4) !== 2 || bytes.readUInt32LE(8) !== bytes.length) {
    throw new Error(`Invalid GLB header: ${pathname}`);
  }
  const jsonLength = bytes.readUInt32LE(12);
  const document = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8').trim());
  let triangles = 0;
  const semantics = new Set();
  for (const mesh of document.meshes ?? []) {
    for (const primitive of mesh.primitives ?? []) {
      const accessorIndex = primitive.indices ?? primitive.attributes?.POSITION;
      const accessor = document.accessors?.[accessorIndex];
      if (!accessor) throw new Error(`Unmeasurable triangle accessor in ${pathname}`);
      triangles += Math.floor(accessor.count / 3);
      semantics.add(Object.keys(primitive.attributes ?? {}).sort().join(','));
    }
  }
  return { bytes, document, triangles, semantics: [...semantics] };
}

for (const required of [sourcePath, blenderScript, textureBuilder, cli, blender]) {
  if (!existsSync(required)) throw new Error(`World-cell input is missing: ${required}`);
}

// SKIP_WORLD_TEXTURES=1 reuses the committed runtime textures (deterministic builder) when only geometry changed,
// e.g. while another process holds a texture file open on Windows.
if (process.env.SKIP_WORLD_TEXTURES !== '1') run(python, ['-B', textureBuilder]);
const source = JSON.parse(readFileSync(sourcePath, 'utf8'));
const cells = source.zones?.[0]?.terrain_cells ?? [];
if (cells.length !== 2) throw new Error(`Expected two Sunmeadow detail cells, found ${cells.length}.`);

const temporaryRoot = mkdtempSync(path.join(tmpdir(), 'aetherfield-sunmeadow-cells-'));
try {
  const textureDirectory = path.join(temporaryRoot, 'textures');
  mkdirSync(textureDirectory, { recursive: true });
  const textureAliases = [
    // Review renders use the runtime look: painted meadow ground (tools/paint_meadow_textures.py) and the
    // edge-bled v2 leaf atlas (art pass v1, 2026-10-02).
    ['meadow_grass_painted_albedo.png', 'grass_ground_albedo.png'],
    ['meadow_grass_painted_normal.png', 'grass_ground_normal.png'],
    ['leaf_canopy_albedo_v2.png', 'world_leaf_cards_albedo.png'],
    ['world_tree_bark_albedo.png', 'world_tree_bark_albedo.png'],
    ['stone_painted_albedo.png', 'stone_foundation_albedo.png'],
    ['stone_painted_normal.png', 'stone_foundation_normal.png'],
    ['timber_dark_albedo.png', 'timber_dark_albedo.png'],
    ['timber_dark_normal.png', 'timber_dark_normal.png'],
    ['cobble_path_albedo.png', 'cobble_path_albedo.png'],
    ['cobble_path_normal.png', 'cobble_path_normal.png'],
  ];
  for (const id of ['sunmeadow_pine_west_mid', 'sunmeadow_oak_east']) {
    textureAliases.push(['leaf_canopy_albedo_v2.png', `world_leaf_cards_hero_fallback_${id}_albedo.png`]);
    textureAliases.push(['timber_dark_albedo.png', `timber_dark_hero_fallback_${id}_albedo.png`]);
    textureAliases.push(['timber_dark_normal.png', `timber_dark_hero_fallback_${id}_normal.png`]);
  }
  for (const [sourceName, alias] of textureAliases) {
    copyFileSync(path.join(clientRoot, 'src/assets/world', sourceName), path.join(textureDirectory, alias));
  }
  run(blender, ['--background', '--factory-startup', '--python-exit-code', '1', '--python', blenderScript,
    '--', '--source', sourcePath, '--out-dir', temporaryRoot, '--master', sourceMaster, '--review', reviewImage,
    '--detail-review', detailReview, '--texture-dir', textureDirectory]);

  const built = [];
  for (const cell of cells) {
    const raw = path.join(temporaryRoot, `${cell.asset}.glb`);
    const optimized = path.join(temporaryRoot, `${cell.asset}.meshopt.glb`);
    const candidate = path.join(temporaryRoot, `${cell.asset}.verified.glb`);
    const runtime = path.join(clientRoot, 'src/assets/world', `${cell.asset}.meshopt.glb`);
    if (!existsSync(raw)) throw new Error(`Blender did not export ${cell.id}.`);
    run(process.execPath, [cli, 'meshopt', raw, optimized, '--level', 'medium']);
    run(process.execPath, [cli, 'validate', optimized]);
    const measured = inspectGlb(optimized);
    if (measured.triangles === 0 || measured.triangles > cellTriangleLimit) {
      throw new Error(`${cell.id} triangles ${measured.triangles} exceed the 1..${cellTriangleLimit} cell budget.`);
    }
    if (measured.bytes.length > cellByteLimit) {
      throw new Error(`${cell.id} transfer size ${measured.bytes.length} exceeds ${cellByteLimit} bytes.`);
    }
    if (!measured.document.extensionsUsed?.includes('EXT_meshopt_compression')) {
      throw new Error(`${cell.id} is missing EXT_meshopt_compression.`);
    }
    if ((measured.document.images?.length ?? 0) !== 0) {
      throw new Error(`${cell.id} must use the shared Vite texture files, not duplicate embedded images.`);
    }
    if (measured.semantics.some((set) => !set.includes('POSITION') || !set.includes('NORMAL') || !set.includes('TEXCOORD_0') || !set.includes('COLOR_0'))) {
      throw new Error(`${cell.id} mesh attributes do not match POSITION/NORMAL/TEXCOORD_0/COLOR_0.`);
    }
    copyFileSync(optimized, candidate);
    const final = inspectGlb(candidate);
    if (sha256(candidate) !== sha256(optimized)) throw new Error(`${cell.id} candidate changed during verification.`);
    built.push({
      id: cell.id,
      asset: cell.asset,
      path: path.relative(root, runtime).replaceAll('\\', '/'),
      bytes: final.bytes.length,
      sha256: sha256(candidate),
      triangles: final.triangles,
      materials: final.document.materials?.length ?? 0,
      embeddedImages: final.document.images?.length ?? 0,
      bounds_xz: cell.bounds_xz,
      surface_y: cell.surface_y,
      world_prop_ids: (source.zones[0].world_props ?? [])
        .filter((prop) => prop.cell === cell.id)
        .map((prop) => prop.id),
    });
    renameSync(candidate, runtime);
  }

  const textureManifestPath = path.join(root, 'assets/models/world-v1/texture-manifest.json');
  const manifest = {
    schema: 'aetherfield.world-cell-package/1',
    source: {
      blender_script: path.relative(root, blenderScript).replaceAll('\\', '/'),
      zone_source: path.relative(root, sourcePath).replaceAll('\\', '/'),
      zone_source_sha256: sha256(sourcePath),
      editable_master: path.relative(root, sourceMaster).replaceAll('\\', '/'),
      review_image: path.relative(root, reviewImage).replaceAll('\\', '/'),
      detail_review_image: path.relative(root, detailReview).replaceAll('\\', '/'),
    },
    texture_manifest: path.relative(root, textureManifestPath).replaceAll('\\', '/'),
    limits: { triangles_per_cell: cellTriangleLimit, bytes_per_cell: cellByteLimit },
    cells: built,
    shared_runtime_textures: [
      'apps/client/src/assets/world/meadow_grass_painted_albedo.png',
      'apps/client/src/assets/world/meadow_grass_painted_normal.png',
      'apps/client/src/assets/world/leaf_canopy_albedo_v2.png',
      'apps/client/src/assets/world/world_tree_bark_albedo.png',
      'apps/client/src/assets/world/stone_painted_albedo.png',
      'apps/client/src/assets/world/stone_painted_normal.png',
      'apps/client/src/assets/world/timber_dark_albedo.png',
      'apps/client/src/assets/world/timber_dark_normal.png',
      'apps/client/src/assets/world/meadow_road_painted_albedo.png',
      'apps/client/src/assets/world/meadow_road_painted_normal.png',
    ],
    limitations: [
      'Cell geometry is flat at y=0; terrain elevation and full navmesh enforcement are not implemented.',
      'Cells are loaded before the player enters the southbound band and remain resident for this prototype slice.',
      'No Android/iOS memory or frame-time measurements are included.',
    ],
  };
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify({ status: 'PASS', cells: built }, null, 2));
} finally {
  const resolvedTemp = path.resolve(temporaryRoot);
  const resolvedParent = path.resolve(tmpdir());
  if (path.dirname(resolvedTemp) !== resolvedParent || !path.basename(resolvedTemp).startsWith('aetherfield-sunmeadow-cells-')) {
    throw new Error('Refusing to remove an unexpected temporary world-cell build directory.');
  }
  rmSync(resolvedTemp, { recursive: true, force: true });
}
