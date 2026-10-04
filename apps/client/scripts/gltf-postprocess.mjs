#!/usr/bin/env node
/**
 * Xexoria runtime GLB post-process (pairs with assets/blender/tools/export_helper.py).
 *
 *   dedup -> prune -> attribute policy -> weld -> meshopt (reorder for vertex cache/fetch + KHR_mesh_quantization +
 *   EXT_meshopt_compression, never KHR) -> KTX2 (ETC1S colour / UASTC data, KTX-Software 4.4.2 through the
 *   glTF-Transform toktx transform, cached by content hash in a shared folder) -> write (textures stay external)
 *   -> verify (re-read, Khronos validator, parity) -> budget check (tools/asset-budgets.json) -> size/decode report.
 *
 * Same tooling as build-city-asset.mjs / build-world-cells.mjs: glTF Transform 4.5.0 (`meshopt --level medium`
 * is reorder + quantize + EXT_meshopt_compression), the repo's meshoptimizer devDependency, and the
 * `uastc --level 2 --rdo --rdo-lambda 2 --zstd 9` / `etc1s --quality 180` city texture recipe.
 *
 * Usage (from apps/client):
 *   node scripts/gltf-postprocess.mjs <in.glb> --out <out.glb> [--class tree_lod0] [--tier high]
 *        [--texture-out <dir>] [--texture-uri-prefix <url>] [--embed-textures] [--no-ktx]
 *        [--report <report.json>] [--review-out <dir>] [--budgets <asset-budgets.json>] [--ktx-bin <dir>]
 *        [--compare-input]   (also brotli/gzip the input GLB for a before/after size table; slow on large inputs)
 *   node scripts/gltf-postprocess.mjs --jobs jobs.json [--report <summary.json>]
 * Exit codes: 0 PASS, 1 unexpected error, 2 budget breach, 3 policy/validation failure, 4 bad arguments.
 */
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';
import { performance } from 'node:perf_hooks';
import { Format, Logger, NodeIO, Primitive, PropertyType } from '@gltf-transform/core';
import { ALL_EXTENSIONS, KHRTextureBasisu } from '@gltf-transform/extensions';
import { dedup, getTextureChannelMask, getTextureColorSpace, listTextureSlots, meshopt, prune, weld } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';
import { read as readKtx, KHR_DF_MODEL_ETC1S, KHR_DF_MODEL_UASTC, KHR_DF_TRANSFER_SRGB, KHR_SUPERCOMPRESSION_ZSTD, KHR_SUPERCOMPRESSION_BASISLZ } from 'ktx-parse';

export const POSTPROCESS_VERSION = '1.0.0';
const clientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(clientRoot, '../..');
export const DEFAULT_BUDGETS = path.join(repoRoot, 'tools/asset-budgets.json');
const DEFAULT_KTX_BIN = path.join(repoRoot, '.harness/.cache/toolchains/ktx-4.4.2/portable/bin');
const KTX_VERSION_PIN = '4.4.2';
export const EXIT = { OK: 0, ERROR: 1, BUDGET: 2, POLICY: 3, USAGE: 4 };

/** Never in a runtime asset (docs/reviews/2026-10-02-blender-asset-official-docs.md GAP-9, X5). */
export const FORBIDDEN_EXTENSIONS = {
  KHR_meshopt_compression: 'Babylon 9.27.1 has no KHR_meshopt_compression loader (GAP-9); EXT only',
  KHR_draco_mesh_compression: 'Draco stays off (official-docs X5)',
  KHR_lights_punctual: 'runtime assets carry no lights',
  EXT_texture_webp: 'WebP is not GPU-compressed; use KTX2',
};
/** Babylon 9.27.1 loader extensions (official-docs §3.6). */
export const BABYLON_LOADABLE = new Set(['KHR_materials_unlit', 'KHR_materials_emissive_strength', 'KHR_texture_transform',
  'KHR_materials_variants', 'KHR_materials_clearcoat', 'KHR_materials_sheen', 'KHR_materials_specular', 'KHR_materials_ior',
  'KHR_materials_anisotropy', 'KHR_materials_transmission', 'KHR_materials_volume', 'KHR_materials_dispersion',
  'KHR_materials_iridescence', 'EXT_mesh_gpu_instancing', 'EXT_meshopt_compression', 'KHR_draco_mesh_compression',
  'KHR_mesh_quantization', 'KHR_texture_basisu', 'KHR_animation_pointer', 'MSFT_lod', 'KHR_lights_punctual', 'EXT_texture_webp']);
/** City recipe (build-city-asset.mjs:212-215). */
export const KTX_DEFAULTS = { uastc: { level: 2, rdo: true, rdoLambda: 2, zstd: 9 }, etc1s: { quality: 180 }, jobs: 2 };
const COLOR_SLOT = /^(baseColorTexture|emissiveTexture|diffuseTexture|sheenColorTexture|specularColorTexture)$/;

export class PostprocessError extends Error {
  constructor(message, exitCode, report) { super(message); this.exitCode = exitCode; this.report = report; }
}

const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const posix = (p) => p.split(path.sep).join('/');
const relRepo = (p) => { const r = path.relative(repoRoot, p); return r.startsWith('..') || path.isAbsolute(r) ? posix(p) : posix(r); };
const mib = (bytes) => bytes / (1024 * 1024);
const round = (v, d = 3) => (v === null || v === undefined ? v : Math.round(v * 10 ** d) / 10 ** d);

function writeAtomic(file, bytes) {
  mkdirSync(path.dirname(file), { recursive: true });
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`);
  try { writeFileSync(tmp, bytes); renameSync(tmp, file); } finally { rmSync(tmp, { force: true }); }
}

function silentLogger() { return new Logger(Logger.Verbosity.WARN); }

export async function createIO() {
  await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready]);
  return new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
    'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder,
  }).setLogger(silentLogger());
}

// ------------------------------------------------------------------------------------------------ GLB container
export function parseGlb(bytes) {
  const buf = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (buf.toString('ascii', 0, 4) !== 'glTF' || buf.readUInt32LE(4) !== 2 || buf.readUInt32LE(8) !== buf.length) throw new Error('Invalid GLB header.');
  const jlen = buf.readUInt32LE(12);
  if (buf.readUInt32LE(16) !== 0x4e4f534a) throw new Error('First GLB chunk is not JSON.');
  const json = JSON.parse(buf.subarray(20, 20 + jlen).toString('utf8'));
  let bin = Buffer.alloc(0);
  const off = 20 + jlen;
  if (off + 8 <= buf.length && buf.readUInt32LE(off + 4) === 0x004e4942) bin = buf.subarray(off + 8, off + 8 + buf.readUInt32LE(off));
  return { json, bin };
}

export function packGlb(json, bin) {
  let js = Buffer.from(JSON.stringify(json), 'utf8');
  if (js.length % 4) js = Buffer.concat([js, Buffer.alloc(4 - (js.length % 4), 0x20)]);
  const parts = [u32pair(js.length, 0x4e4f534a), js];
  if (bin && bin.length) {
    let b = Buffer.from(bin.buffer, bin.byteOffset, bin.byteLength);
    if (b.length % 4) b = Buffer.concat([b, Buffer.alloc(4 - (b.length % 4))]);
    parts.push(u32pair(b.length, 0x004e4942), b);
  }
  const body = Buffer.concat(parts);
  const header = Buffer.alloc(12);
  header.write('glTF', 0, 'ascii'); header.writeUInt32LE(2, 4); header.writeUInt32LE(12 + body.length, 8);
  return Buffer.concat([header, body]);
}
function u32pair(a, b) { const x = Buffer.alloc(8); x.writeUInt32LE(a, 0); x.writeUInt32LE(b, 4); return x; }

/** GLB whose images stay external (uri), with the binary buffer in the BIN chunk. glTF Transform embeds images in
 * GLB output, so the document is written as .gltf JSON and re-packed. */
export async function writeGlbExternalImages(io, doc, outFile) {
  const { json, resources } = await io.writeJSON(doc, { format: Format.GLTF, basename: path.parse(outFile).name });
  const withData = (json.buffers ?? []).map((b, i) => [b, i]).filter(([b]) => b.uri !== undefined);
  if (withData.length > 1 || (withData.length === 1 && withData[0][1] !== 0)) throw new Error(`Expected one data buffer at index 0, got ${JSON.stringify(json.buffers)}`);
  let bin = Buffer.alloc(0);
  if (withData.length) { bin = Buffer.from(resources[json.buffers[0].uri]); delete json.buffers[0].uri; }
  for (const image of json.images ?? []) {
    if (!image.uri || image.uri.startsWith('data:')) throw new Error(`Image ${image.name ?? ''} has no external uri.`);
    delete image.bufferView;
  }
  return packGlb(json, bin);
}

// ------------------------------------------------------------------------------------------------ facts
const IDENTITY_MATRIX = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

/** Rest-pose world matrices, including POSITION dequantization folded into skin IBMs. */
function skinWorldMatrices(skin) {
  const joints = skin.listJoints();
  const inverseBind = skin.getInverseBindMatrices();
  if (!joints.length || (inverseBind && inverseBind.getCount() !== joints.length)) {
    throw new PostprocessError('Invalid skin joint/inverse-bind count', EXIT.POLICY);
  }
  return joints.map((joint, index) => {
    const a = joint.getWorldMatrix();
    const b = inverseBind ? inverseBind.getElement(index, []) : IDENTITY_MATRIX;
    const out = new Array(16).fill(0);
    for (let col = 0; col < 4; col++) {
      for (let row = 0; row < 4; row++) {
        for (let k = 0; k < 4; k++) out[col * 4 + row] += a[k * 4 + row] * b[col * 4 + k];
      }
    }
    if (!out.every(Number.isFinite)) throw new PostprocessError('Non-finite skin matrix', EXIT.POLICY);
    return out;
  });
}

export function documentFacts(doc) {
  const root = doc.getRoot();
  let triangles = 0; let drawCalls = 0; let maxAttributes = 0; let vertexBytes = 0; let indexBytes = 0;
  const lo = [Infinity, Infinity, Infinity]; const hi = [-Infinity, -Infinity, -Infinity];
  const primitives = []; const seenAcc = new Set(); const el = [0, 0, 0]; const w = [0, 0, 0];
  for (const node of root.listNodes()) {
    const mesh = node.getMesh(); if (!mesh) continue;
    const skin = node.getSkin();
    const m = node.getWorldMatrix();
    const skinMatrices = skin ? skinWorldMatrices(skin) : null;
    for (const prim of mesh.listPrimitives()) {
      const pos = prim.getAttribute('POSITION'); const idx = prim.getIndices();
      if (!pos) throw new PostprocessError(`${mesh.getName()}: missing POSITION`, EXIT.POLICY);
      const influences = [];
      if (skinMatrices) {
        for (const set of [0, 1]) {
          const joints = prim.getAttribute(`JOINTS_${set}`);
          const weights = prim.getAttribute(`WEIGHTS_${set}`);
          if (!joints && !weights) continue;
          if (!joints || !weights || joints.getType() !== 'VEC4' || weights.getType() !== 'VEC4'
              || joints.getCount() !== pos.getCount() || weights.getCount() !== pos.getCount()) {
            throw new PostprocessError(`${mesh.getName()}: invalid skin influence attributes`, EXIT.POLICY);
          }
          influences.push({ joints, weights, jointValues: [], weightValues: [] });
        }
        if (!influences.length) throw new PostprocessError(`${mesh.getName()}: skin has no influences`, EXIT.POLICY);
      }
      const count = idx ? idx.getCount() : pos.getCount();
      const tris = prim.getMode() === Primitive.Mode.TRIANGLES ? Math.floor(count / 3) : 0;
      triangles += tris; drawCalls += 1;
      const attrs = {};
      for (const sem of prim.listSemantics().sort()) {
        const a = prim.getAttribute(sem);
        attrs[sem] = `${a.getType()}/${a.getComponentType()}${a.getNormalized() ? '/n' : ''}`;
        if (!seenAcc.has(a)) { seenAcc.add(a); vertexBytes += a.getByteLength(); }
      }
      if (idx && !seenAcc.has(idx)) { seenAcc.add(idx); indexBytes += idx.getByteLength(); }
      maxAttributes = Math.max(maxAttributes, prim.listSemantics().length);
      primitives.push({ mesh: mesh.getName(), node: node.getName(), material: prim.getMaterial()?.getName() ?? null, triangles: tris, vertices: pos.getCount(), attributes: attrs });
      for (let i = 0, n = pos.getCount(); i < n; i++) {
        pos.getElement(i, el);
        if (skinMatrices) {
          w.fill(0);
          let weightSum = 0;
          for (const influence of influences) {
            const jointValues = influence.joints.getElement(i, influence.jointValues);
            const weightValues = influence.weights.getElement(i, influence.weightValues);
            for (let j = 0; j < 4; j++) {
              const weight = weightValues[j];
              if (!Number.isFinite(weight) || weight < 0) throw new PostprocessError(`${mesh.getName()}: invalid skin weight`, EXIT.POLICY);
              if (weight === 0) continue;
              const joint = jointValues[j];
              if (!Number.isInteger(joint) || !skinMatrices[joint]) throw new PostprocessError(`${mesh.getName()}: invalid skin joint index`, EXIT.POLICY);
              const matrix = skinMatrices[joint];
              for (let k = 0; k < 3; k++) {
                w[k] += weight * (matrix[k] * el[0] + matrix[4 + k] * el[1] + matrix[8 + k] * el[2] + matrix[12 + k]);
              }
              weightSum += weight;
            }
          }
          if (!(weightSum > 0)) throw new PostprocessError(`${mesh.getName()}: zero skin weight sum`, EXIT.POLICY);
          // glTF weights sum to one; account for normalized integer rounding after quantization.
          for (let k = 0; k < 3; k++) w[k] /= weightSum;
        } else {
          w[0] = m[0] * el[0] + m[4] * el[1] + m[8] * el[2] + m[12];
          w[1] = m[1] * el[0] + m[5] * el[1] + m[9] * el[2] + m[13];
          w[2] = m[2] * el[0] + m[6] * el[1] + m[10] * el[2] + m[14];
        }
        if (!w.every(Number.isFinite)) throw new PostprocessError(`${mesh.getName()}: non-finite world position`, EXIT.POLICY);
        for (let k = 0; k < 3; k++) { if (w[k] < lo[k]) lo[k] = w[k]; if (w[k] > hi[k]) hi[k] = w[k]; }
      }
    }
  }
  const materials = root.listMaterials().map((mat) => ({ name: mat.getName(), alphaMode: mat.getAlphaMode(), doubleSided: mat.getDoubleSided(), normalTexture: !!mat.getNormalTexture() }));
  return {
    triangles, drawCalls, primitives, maxAttributes, vertexBytes, indexBytes,
    materials, materialCount: materials.length, meshes: root.listMeshes().length, nodes: root.listNodes().length,
    textures: root.listTextures().length,
    bounds: Number.isFinite(lo[0]) ? { min: lo.map((v) => round(v, 5)), max: hi.map((v) => round(v, 5)) } : null,
    extensionsUsed: doc.getRoot().listExtensionsUsed().map((e) => e.extensionName).sort(),
    extensionsRequired: doc.getRoot().listExtensionsRequired().map((e) => e.extensionName).sort(),
    animations: root.listAnimations().length, skins: root.listSkins().length, cameras: root.listCameras().length,
  };
}

/** GPU bytes of one texture, with the full mip chain. */
export function textureGpuEstimate(texture) {
  const mime = texture.getMimeType(); const image = texture.getImage();
  if (mime === 'image/ktx2' && image) {
    const c = readKtx(image); const dfd = c.dataFormatDescriptor[0];
    const model = dfd.colorModel; const levels = Math.max(1, c.levels.length);
    const W = c.pixelWidth; const H = Math.max(1, c.pixelHeight);
    const alpha = model === KHR_DF_MODEL_ETC1S ? dfd.samples.length > 1 : model === KHR_DF_MODEL_UASTC ? [3, 5].includes(dfd.samples[0]?.channelType) : true;
    const codec = model === KHR_DF_MODEL_ETC1S ? 'ETC1S' : model === KHR_DF_MODEL_UASTC ? 'UASTC' : `model${model}`;
    const blockBytes = codec === 'ETC1S' && !alpha ? 8 : 16; // ETC2 RGB / BC1 = 4 bpp; ETC2 RGBA, BC3, BC7, ASTC 4x4 = 8 bpp
    let gpu = 0; let rgba = 0;
    for (let l = 0; l < levels; l++) {
      const w = Math.max(1, W >> l); const h = Math.max(1, H >> l);
      gpu += Math.ceil(w / 4) * Math.ceil(h / 4) * blockBytes; rgba += w * h * 4;
    }
    const target = codec === 'UASTC' ? 'ASTC 4x4 / BC7 (8 bpp)' : alpha ? 'ETC2 RGBA / BC3 (8 bpp)' : 'ETC2 RGB / BC1 (4 bpp)';
    return { codec, width: W, height: H, levels, alpha, srgb: dfd.transferFunction === KHR_DF_TRANSFER_SRGB,
      supercompression: c.supercompressionScheme === KHR_SUPERCOMPRESSION_ZSTD ? 'zstd' : c.supercompressionScheme === KHR_SUPERCOMPRESSION_BASISLZ ? 'BasisLZ' : String(c.supercompressionScheme),
      gpu_bytes: gpu, gpu_target: target, rgba8_fallback_bytes: rgba };
  }
  const size = texture.getSize() ?? [0, 0];
  let rgba = 0; for (let w = size[0], h = size[1]; ; w = Math.max(1, w >> 1), h = Math.max(1, h >> 1)) { rgba += w * h * 4; if (w === 1 && h === 1) break; }
  return { codec: mime, width: size[0], height: size[1], levels: null, alpha: null, gpu_bytes: rgba, gpu_target: 'RGBA8 (uncompressed, 32 bpp)', rgba8_fallback_bytes: rgba };
}

// ------------------------------------------------------------------------------------------------ budgets
export function loadBudgets(file = DEFAULT_BUDGETS) { return JSON.parse(readFileSync(file, 'utf8')); }

export function resolveBudget(budgets, className, tier = 'high') {
  const cls = budgets.classes?.[className];
  if (!cls) throw new PostprocessError(`Unknown budget class "${className}". Known: ${Object.keys(budgets.classes ?? {}).join(', ')}`, EXIT.USAGE);
  const limits = { ...cls.limits, ...(tier !== 'high' ? cls.tiers?.[tier] ?? {} : {}) };
  delete limits.provisional;
  const provisional = new Set([...(cls.provisional ?? []), ...(tier !== 'high' && cls.tiers?.[tier] ? Object.keys(cls.tiers[tier]).filter((k) => k !== 'provisional') : [])]);
  return { className, tier, limits, provisional: [...provisional].sort(), policy: { ...(budgets.defaults?.policy ?? {}), ...(cls.policy ?? {}) }, ktx: { ...KTX_DEFAULTS, ...(budgets.defaults?.ktx ?? {}), ...(cls.ktx ?? {}) }, source: cls.source, profile: cls.profile };
}

const LABEL = { triangles: 'triangles', triangles_min: 'triangles (minimum)', draw_calls: 'draw calls (primitives x mesh nodes)', materials: 'materials', texture_mib: 'texture GPU MiB (block-compressed, mips)', glb_kib: 'GLB transfer KiB (excl. external textures)', transfer_kib: 'transfer KiB (GLB + referenced textures)', vertex_attributes: 'vertex attributes per primitive (WebGPU limit 8)', vertex_mib: 'vertex + index buffer MiB' };

export function checkBudget(metrics, budget) {
  const breaches = []; const rows = [];
  for (const [key, limit] of Object.entries(budget.limits)) {
    if (typeof limit !== 'number') continue;
    const metricKey = key === 'triangles_min' ? 'triangles' : key;
    const value = metrics[metricKey];
    if (value === undefined) continue;
    const ok = key === 'triangles_min' ? value >= limit : value <= limit;
    const row = { metric: key, label: LABEL[key] ?? key, value: round(value, 3), limit, pass: ok, provisional: budget.provisional.includes(key) };
    rows.push(row);
    if (!ok) breaches.push(`${budget.className} (tier ${budget.tier}): ${row.label} ${round(value, 3)} ${key === 'triangles_min' ? '<' : '>'} ${limit}${row.provisional ? ' [provisional limit]' : ''}`);
  }
  return { rows, breaches, pass: breaches.length === 0 };
}

// ------------------------------------------------------------------------------------------------ KTX2
function ktxBinary(ktxBin) {
  const dir = ktxBin || process.env.KTX_SOFTWARE_BIN || DEFAULT_KTX_BIN;
  const exe = path.join(dir, process.platform === 'win32' ? 'ktx.exe' : 'ktx');
  if (!existsSync(exe)) throw new PostprocessError(`KTX-Software not found at ${exe}. Set KTX_SOFTWARE_BIN to the KTX-Software ${KTX_VERSION_PIN} bin directory (repo pin: build-hero-oak.mjs).`, EXIT.USAGE);
  const v = spawnSync(exe, ['--version'], { encoding: 'utf8' });
  const text = `${v.stdout ?? ''}${v.stderr ?? ''}`;
  if (v.status !== 0 || !text.includes(KTX_VERSION_PIN)) throw new PostprocessError(`The texture recipe is pinned to KTX-Software ${KTX_VERSION_PIN}; found: ${text.trim()}`, EXIT.USAGE);
  return { dir, exe, version: text.trim() };
}

function cacheIndexPath(dir) { return path.join(dir, 'ktx2-cache.json'); }
function readCacheIndex(dir) { try { return JSON.parse(readFileSync(cacheIndexPath(dir), 'utf8')); } catch { return { schema: 'xexoria.ktx2-cache/1', entries: {} }; } }
function safeStem(name) { const s = (name || 'texture').toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^[_-]+|[_-]+$/g, '') || 'texture'; return /^[a-z]/.test(s) ? s : `tex_${s}`; }

/** Encode every PNG/JPEG texture to KTX2 (ETC1S colour, UASTC data) with the cache in `textureOut`. */
export async function encodeTextures(doc, { textureOut, ktx, ktxBin, report }) {
  const root = doc.getRoot();
  const textures = root.listTextures().filter((t) => ['image/png', 'image/jpeg'].includes(t.getMimeType()) && t.getImage());
  if (!textures.length) return;
  const tSetup = performance.now();
  const tool = ktxBinary(ktxBin);
  const { toktx, Mode } = await import('@gltf-transform/cli');
  let sharp; try { sharp = (await import('sharp')).default; } catch { sharp = undefined; }
  report.timings.ktx_setup_ms = round(performance.now() - tSetup, 1);
  mkdirSync(textureOut, { recursive: true });
  const index = readCacheIndex(textureOut);
  const plan = [];
  for (const [i, texture] of textures.entries()) {
    const slots = listTextureSlots(texture);
    const colorSlots = slots.filter((s) => COLOR_SLOT.test(s));
    const mode = colorSlots.length && colorSlots.length === slots.length ? 'etc1s' : 'uastc';
    if (colorSlots.length && colorSlots.length !== slots.length) report.warnings.push(`texture ${texture.getName()}: used as colour and data (${slots.join(', ')}); encoded UASTC`);
    const src = texture.getImage();
    const settings = mode === 'etc1s' ? ktx.etc1s : ktx.uastc;
    const key = sha256(JSON.stringify({ src: sha256(src), mode, settings, slots: [...slots].sort(), channels: getTextureChannelMask(texture), color: getTextureColorSpace(texture), ktx: KTX_VERSION_PIN, tool: 'gltf-transform-toktx-4.5.0' }));
    plan.push({ i, texture, slots, mode, key, srcSha: sha256(src), srcBytes: src.byteLength, name: texture.getName(), uri: texture.getURI() });
  }
  const pending = [];
  for (const p of plan) {
    const hit = index.entries[p.key];
    const file = hit && path.join(textureOut, hit.file);
    if (hit && existsSync(file) && sha256(readFileSync(file)) === hit.sha256) {
      p.texture.setImage(new Uint8Array(readFileSync(file))).setMimeType('image/ktx2');
      p.cache = 'hit'; p.file = file;
    } else { pending.push(p); }
  }
  if (pending.length) {
    const prevPath = process.env.PATH;
    process.env.PATH = [tool.dir, prevPath ?? ''].join(path.delimiter);
    const names = new Map();
    try {
      for (const p of pending) { names.set(p.texture, p.texture.getName()); p.texture.setName(`__xex_tex_${p.i}__`); }
      for (const mode of ['etc1s', 'uastc']) {
        const subset = pending.filter((p) => p.mode === mode);
        if (!subset.length) continue;
        const pattern = new RegExp(`^(${subset.map((p) => `__xex_tex_${p.i}__`).join('|')})$`);
        const t0 = performance.now();
        const opts = mode === 'etc1s'
          ? { mode: Mode.ETC1S, quality: ktx.etc1s.quality, pattern, slots: null, jobs: ktx.jobs, encoder: sharp }
          : { mode: Mode.UASTC, level: ktx.uastc.level, rdo: ktx.uastc.rdo, rdoLambda: ktx.uastc.rdoLambda, zstd: ktx.uastc.zstd, pattern, slots: null, jobs: ktx.jobs, encoder: sharp };
        await doc.transform(toktx(opts));
        report.timings[`ktx_${mode}_ms`] = round(performance.now() - t0, 1);
      }
    } finally {
      for (const [texture, name] of names) texture.setName(name);
      process.env.PATH = prevPath;
    }
    for (const p of pending) {
      if (p.texture.getMimeType() !== 'image/ktx2') throw new PostprocessError(`KTX2 encoding failed for texture ${p.name || p.i} (see ktx output).`, EXIT.POLICY);
      const bytes = Buffer.from(p.texture.getImage());
      const file = path.join(textureOut, `${safeStem(p.name || path.parse(p.uri || 'texture').name)}-${sha256(bytes).slice(0, 12)}.ktx2`);
      if (!existsSync(file) || sha256(readFileSync(file)) !== sha256(bytes)) writeAtomic(file, bytes);
      index.entries[p.key] = { file: path.basename(file), sha256: sha256(bytes), bytes: bytes.length, source_sha256: p.srcSha, mode: p.mode, settings: p.mode === 'etc1s' ? ktx.etc1s : ktx.uastc, slots: p.slots, ktx: tool.version };
      p.cache = 'miss'; p.file = file;
    }
    writeAtomic(cacheIndexPath(textureOut), Buffer.from(JSON.stringify(index, null, 1) + '\n'));
  }
  // toktx registers KHR_texture_basisu only when it encodes something; with an all-hit cache it never runs, and a
  // KTX2 image without the extension would be written as a core texture source (invalid glTF, unreadable by Babylon).
  if (root.listTextures().some((t) => t.getMimeType() === 'image/ktx2')) doc.createExtension(KHRTextureBasisu).setRequired(true);
  for (const p of plan) {
    const bytes = Buffer.from(p.texture.getImage());
    report.textures.push({ name: p.name, slots: p.slots, mode: p.mode.toUpperCase(), cache: p.cache, source_bytes: p.srcBytes, source_sha256: p.srcSha, file: relRepo(p.file), bytes: bytes.length, sha256: sha256(bytes), ...textureGpuEstimate(p.texture) });
  }
  report.ktx = { tool: tool.version, recipe: ktx };
}

// ------------------------------------------------------------------------------------------------ attribute policy
function convertColor0ToRgb(doc, prim, log) {
  const c = prim.getAttribute('COLOR_0');
  if (!c || c.getType() !== 'VEC4') return;
  const n = c.getCount(); const out = new Float32Array(n * 3); const el = [0, 0, 0, 0];
  let amin = 1; for (let i = 0; i < n; i++) { c.getElement(i, el); out[i * 3] = el[0]; out[i * 3 + 1] = el[1]; out[i * 3 + 2] = el[2]; amin = Math.min(amin, el[3]); }
  const rgb = doc.createAccessor(c.getName()).setType('VEC3').setArray(out).setBuffer(c.getBuffer());
  prim.setAttribute('COLOR_0', rgb);
  log.push({ primitive: prim.getName() || null, action: 'COLOR_0 VEC4 -> VEC3', alpha_min: round(amin, 4) });
}

export function applyAttributePolicy(doc, policy, report) {
  const stripped = [];
  for (const mesh of doc.getRoot().listMeshes()) {
    for (const prim of mesh.listPrimitives()) {
      const material = prim.getMaterial();
      for (const sem of prim.listSemantics()) {
        const m = /^(COLOR|TEXCOORD)_(\d+)$/.exec(sem);
        if (m && m[1] === 'COLOR' && Number(m[2]) > 0) { prim.setAttribute(sem, null); stripped.push({ mesh: mesh.getName(), attribute: sem, reason: 'Babylon 9.27.1 reads COLOR_0 only' }); }
        if (m && m[1] === 'TEXCOORD' && Number(m[2]) >= (policy.max_uv_sets ?? 2)) { prim.setAttribute(sem, null); stripped.push({ mesh: mesh.getName(), attribute: sem, reason: `class allows ${policy.max_uv_sets ?? 2} UV sets` }); }
      }
      if (policy.strip_unused_tangents !== false && prim.getAttribute('TANGENT') && !material?.getNormalTexture()) {
        prim.setAttribute('TANGENT', null);
        stripped.push({ mesh: mesh.getName(), material: material?.getName() ?? null, attribute: 'TANGENT', reason: 'material has no normal map (exporter tangents are per file)' });
      }
      if ((policy.color0 ?? 'RGB') === 'RGB') convertColor0ToRgb(doc, prim, report.color0_conversions);
    }
  }
  report.stripped_attributes = stripped;
}

// ------------------------------------------------------------------------------------------------ policy checks
export function policyChecks(facts, budget, json) {
  const fails = []; const warns = [];
  const used = new Set([...(json.extensionsUsed ?? []), ...(json.extensionsRequired ?? [])]);
  for (const ext of used) if (FORBIDDEN_EXTENSIONS[ext]) fails.push(`forbidden extension ${ext}: ${FORBIDDEN_EXTENSIONS[ext]}`);
  for (const ext of used) if (!BABYLON_LOADABLE.has(ext)) fails.push(`extension ${ext} is not loadable by Babylon 9.27.1`);
  if (facts.triangles > 0 && !(json.extensionsUsed ?? []).includes('EXT_meshopt_compression')) fails.push('EXT_meshopt_compression missing from extensionsUsed');
  if (facts.triangles > 0 && !(json.extensionsRequired ?? []).includes('EXT_meshopt_compression')) fails.push('EXT_meshopt_compression missing from extensionsRequired');
  if (facts.triangles > 0 && !(json.extensionsUsed ?? []).includes('KHR_mesh_quantization')) warns.push('KHR_mesh_quantization not used (no attribute was quantized)');
  const policy = budget.policy;
  for (const p of facts.primitives) {
    if ((policy.color0 ?? 'RGB') === 'RGB' && p.attributes.COLOR_0?.startsWith('VEC4')) fails.push(`${p.mesh}/${p.material}: COLOR_0 is VEC4 (GAP-3: Babylon sets hasVertexAlpha)`);
    if (p.attributes.JOINTS_1 || p.attributes.WEIGHTS_1) fails.push(`${p.mesh}: JOINTS_1/WEIGHTS_1 present (> 4 influences doubles skinning cost)`);
    for (const a of policy.discouraged_attributes ?? []) if (p.attributes[a]) warns.push(`${p.mesh}: ${a} on a ${budget.className} primitive (WebGPU 8-buffer rule; drop if unused)`);
  }
  const ds = policy.double_sided ?? 'explicit';
  for (const m of facts.materials) {
    if (!m.doubleSided) continue;
    if (m.alphaMode === 'OPAQUE' && ds !== 'any') (policy.double_sided_opaque_fails ? fails : warns).push(`material ${m.name}: opaque and double-sided (GAP-4: only foliage and cloth stay double-sided)`);
  }
  return { fails, warns };
}

// ------------------------------------------------------------------------------------------------ decode timing
export function meshoptDecodeTiming(glbBytes, runs = 5) {
  const { json, bin } = parseGlb(glbBytes);
  const views = (json.bufferViews ?? []).filter((v) => v.extensions?.EXT_meshopt_compression);
  if (!views.length) return { buffer_views: 0, decoded_bytes: 0, median_ms: 0 };
  let decoded = 0; const times = [];
  for (let r = 0; r < runs; r++) {
    const t0 = performance.now(); decoded = 0;
    for (const v of views) {
      const e = v.extensions.EXT_meshopt_compression;
      const src = new Uint8Array(bin.buffer, bin.byteOffset + (e.byteOffset ?? 0), e.byteLength);
      const target = new Uint8Array(e.count * e.byteStride);
      MeshoptDecoder.decodeGltfBuffer(target, e.count, e.byteStride, src, e.mode, e.filter ?? 'NONE');
      decoded += target.byteLength;
    }
    times.push(performance.now() - t0);
  }
  times.sort((a, b) => a - b);
  return { buffer_views: views.length, decoded_bytes: decoded, median_ms: round(times[Math.floor(runs / 2)], 3), runs, note: 'Node/V8 desktop proxy; device decode UNMEASURED' };
}

function compressionSizes(bytes) {
  const br = zlib.brotliCompressSync(bytes, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: bytes.length } });
  const br5 = zlib.brotliCompressSync(bytes, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 } });
  const gz = zlib.gzipSync(bytes, { level: 9 });
  return { raw: bytes.length, brotli_q11: br.length, brotli_q5: br5.length, gzip_9: gz.length };
}

async function khronosValidate(glbBytes, baseDir) {
  const validator = (await import('gltf-validator')).default;
  const res = await validator.validateBytes(new Uint8Array(glbBytes), {
    maxIssues: 50, writeTimestamp: false,
    externalResourceFunction: (uri) => new Promise((resolve, reject) => {
      try { resolve(new Uint8Array(readFileSync(path.resolve(baseDir, decodeURIComponent(uri))))); } catch (e) { reject(e); }
    }),
  });
  return { errors: res.issues.numErrors, warnings: res.issues.numWarnings, infos: res.issues.numInfos, hints: res.issues.numHints, truncated: res.issues.truncated, messages: res.issues.messages.filter((m) => m.severity <= 1).slice(0, 25).map((m) => `${['ERROR', 'WARNING', 'INFO', 'HINT'][m.severity]} ${m.code}: ${m.message}${m.pointer ? ` (${m.pointer})` : ''}`) };
}

// ------------------------------------------------------------------------------------------------ main pipeline
export async function postprocessGlb(options) {
  const t0 = performance.now();
  const input = path.resolve(options.input);
  const output = path.resolve(options.output);
  const embed = !!options.embedTextures;
  const textureOut = path.resolve(options.textureOut ?? path.join(path.dirname(output), 'textures'));
  const budgets = options.budgets ?? loadBudgets(options.budgetsFile);
  const io = options.io ?? await createIO();
  const report = { schema: 'xexoria.gltf-postprocess-report/1', tool: `gltf-postprocess.mjs ${POSTPROCESS_VERSION}`, gltf_transform: '4.5.0', meshoptimizer: readPkgVersion('meshoptimizer'), input: relRepo(input), output: relRepo(output), status: 'RUNNING', steps: [], timings: {}, textures: [], warnings: [], failures: [], stripped_attributes: [], color0_conversions: [] };
  const inputBytes = readFileSync(input);
  const inParsed = parseGlb(inputBytes);
  const forbiddenIn = [...new Set([...(inParsed.json.extensionsUsed ?? []), ...(inParsed.json.extensionsRequired ?? [])])].filter((e) => FORBIDDEN_EXTENSIONS[e]);
  if (forbiddenIn.length) throw new PostprocessError(`${path.basename(input)} uses forbidden extension(s): ${forbiddenIn.map((e) => `${e} (${FORBIDDEN_EXTENSIONS[e]})`).join('; ')}`, EXIT.POLICY, report);
  const className = options.className ?? inParsed.json.asset?.extras?.xex_budget_class;
  if (!className) throw new PostprocessError('No budget class: pass --class or export with export_helper.py (asset.extras.xex_budget_class).', EXIT.USAGE, report);
  const budget = resolveBudget(budgets, className, options.tier ?? 'high');
  if (options.ktx) Object.assign(budget.ktx, options.ktx);
  report.budget_class = className; report.tier = budget.tier; report.budget_source = budget.source;
  const inExternal = (inParsed.json.images ?? []).filter((i) => i.uri).map((i) => path.resolve(path.dirname(input), decodeURIComponent(i.uri)));
  report.input_bytes = { glb: inputBytes.length, external_images: inExternal.reduce((n, f) => n + statSync(f).size, 0), external_image_files: inExternal.map(relRepo) };
  if (options.compareInput) report.input_bytes.compression = compressionSizes(inputBytes);  // slow on multi-MB inputs

  const doc = await io.read(input);
  const before = documentFacts(doc);
  report.before = summarizeFacts(before);
  const step = async (name, fn) => { const s = performance.now(); await fn(); report.steps.push({ step: name, ms: round(performance.now() - s, 1) }); };

  await step('dedup (accessors, textures by content)', () => doc.transform(dedup({ propertyTypes: [PropertyType.ACCESSOR, PropertyType.TEXTURE], keepUniqueNames: false })));
  await step('dedup (materials, meshes; names kept)', () => doc.transform(dedup({ propertyTypes: [PropertyType.MATERIAL, PropertyType.MESH, PropertyType.SKIN], keepUniqueNames: true })));
  await step('prune (keep leaves, attributes, extras, solid textures)', () => doc.transform(prune({ keepLeaves: true, keepAttributes: true, keepSolidTextures: true, keepExtras: true })));
  await step('attribute policy', () => applyAttributePolicy(doc, { ...budget.policy }, report));
  if (budget.policy.weld !== false) await step('weld (bitwise-identical vertices only)', () => doc.transform(weld()));
  await step('meshopt level medium (reorder vertex cache+fetch, quantize, EXT_meshopt_compression)', async () => {
    await doc.transform(meshopt({ encoder: MeshoptEncoder, level: 'medium' }));
    for (const node of doc.getRoot().listNodes()) {   // quantize() can move a mesh to a new unnamed child node
      if (node.getMesh() && !node.getName()) {
        const parent = node.getParentNode();
        if (parent?.getName()) { node.setName(parent.getName()); report.warnings.push(`quantization moved mesh of node "${parent.getName()}" to a child node (named the same)`); }
      }
    }
  });
  if (!options.noKtx) await step('KTX2 (ETC1S colour, UASTC data)', () => encodeTextures(doc, { textureOut, ktx: budget.ktx, ktxBin: options.ktxBin, report }));

  // texture URIs: shared folder, relative to the output GLB (or a runtime prefix)
  for (const texture of doc.getRoot().listTextures()) {
    if (embed) { texture.setURI(''); continue; }
    const entry = report.textures.find((t) => t.sha256 === sha256(Buffer.from(texture.getImage())));
    let file = entry ? path.resolve(repoRoot, entry.file) : null;
    if (!file) {   // --no-ktx: keep the original external file, or write the image into the shared folder
      const bytes = Buffer.from(texture.getImage());
      const ext = texture.getMimeType() === 'image/jpeg' ? 'jpg' : texture.getMimeType() === 'image/ktx2' ? 'ktx2' : 'png';
      file = path.join(textureOut, `${safeStem(texture.getName())}-${sha256(bytes).slice(0, 12)}.${ext}`);
      if (!existsSync(file)) writeAtomic(file, bytes);
      report.textures.push({ name: texture.getName(), mode: 'none', file: relRepo(file), bytes: bytes.length, sha256: sha256(bytes), ...textureGpuEstimate(texture) });
    }
    texture.setURI(options.textureUriPrefix ? `${options.textureUriPrefix.replace(/\/$/, '')}/${encodeURIComponent(path.basename(file))}` : posix(path.relative(path.dirname(output), file)).split('/').map(encodeURIComponent).join('/'));
  }

  let outBytes;
  await step('write GLB', async () => { outBytes = embed ? Buffer.from(await io.writeBinary(doc)) : await writeGlbExternalImages(io, doc, output); });
  writeAtomic(output, outBytes);

  // verify: re-read what was written (meshopt decode), Khronos validator, parity
  const verifyDoc = await io.read(output);
  const after = documentFacts(verifyDoc);
  const outParsed = parseGlb(outBytes);
  report.after = summarizeFacts(after);
  report.validator = await khronosValidate(outBytes, path.dirname(output));
  const parity = [];
  const strippedSet = new Set(report.stripped_attributes.map((s) => s.attribute));
  parity.push({ check: 'triangles_equal', pass: before.triangles === after.triangles, before: before.triangles, after: after.triangles });
  const semBefore = new Set(before.primitives.flatMap((p) => Object.keys(p.attributes)));
  const semAfter = new Set(after.primitives.flatMap((p) => Object.keys(p.attributes)));
  const lost = [...semBefore].filter((s) => !semAfter.has(s) && !strippedSet.has(s));
  parity.push({ check: 'attribute_semantics_kept', pass: lost.length === 0, before: [...semBefore].sort(), after: [...semAfter].sort(), stripped_by_policy: [...strippedSet].sort(), lost });
  if (before.bounds && after.bounds) {
    const ext = Math.max(...before.bounds.max.map((v, i) => v - before.bounds.min[i]));
    const tol = Math.max(1e-4, ext * 2 ** -12);
    const dev = Math.max(...before.bounds.min.map((v, i) => Math.abs(v - after.bounds.min[i])), ...before.bounds.max.map((v, i) => Math.abs(v - after.bounds.max[i])));
    parity.push({ check: 'bounds_within_quantization', pass: dev <= tol, max_dev_m: round(dev, 6), tolerance_m: round(tol, 6) });
  }
  parity.push({ check: 'material_count_equal', pass: before.materialCount === after.materialCount, before: before.materialCount, after: after.materialCount });
  report.parity = parity;

  const extFiles = [...new Set((outParsed.json.images ?? []).filter((i) => i.uri).map((i) => path.resolve(path.dirname(output), decodeURIComponent(i.uri))))];
  const missing = extFiles.filter((f) => !existsSync(f));
  const texBytes = extFiles.filter((f) => existsSync(f)).reduce((n, f) => n + statSync(f).size, 0);
  const gpuBytes = report.textures.reduce((n, t) => n + (t.gpu_bytes ?? 0), 0);
  const metrics = {
    triangles: after.triangles, draw_calls: after.drawCalls, materials: after.materialCount, texture_mib: mib(gpuBytes),
    glb_kib: outBytes.length / 1024, transfer_kib: (outBytes.length + texBytes) / 1024, vertex_attributes: after.maxAttributes,
    vertex_mib: mib(after.vertexBytes + after.indexBytes),
  };
  report.metrics = Object.fromEntries(Object.entries(metrics).map(([k, v]) => [k, round(v, 3)]));
  report.sizes = { glb: compressionSizes(outBytes), external_textures: extFiles.map((f) => ({ file: relRepo(f), bytes: existsSync(f) ? statSync(f).size : null })), external_texture_bytes: texBytes, texture_gpu_bytes: gpuBytes, texture_rgba8_fallback_bytes: report.textures.reduce((n, t) => n + (t.rgba8_fallback_bytes ?? 0), 0), note: 'KTX2 files are already supercompressed (BasisLZ/zstd): serve them without HTTP compression' };
  report.decode = { meshopt: meshoptDecodeTiming(outBytes), read_back_ms: undefined };
  { const s = performance.now(); await io.read(output); report.decode.read_back_ms = round(performance.now() - s, 1); }

  const pol = policyChecks(after, budget, outParsed.json);
  report.policy = pol;
  report.warnings.push(...pol.warns);
  const failures = [...pol.fails];
  if (report.validator.errors > 0) failures.push(`Khronos validator: ${report.validator.errors} error(s): ${report.validator.messages.filter((m) => m.startsWith('ERROR')).join(' | ')}`);
  for (const p of parity) if (!p.pass) failures.push(`parity ${p.check} failed: ${JSON.stringify(p)}`);
  if (missing.length) failures.push(`external image files missing: ${missing.map(relRepo).join(', ')}`);
  report.failures = failures;
  report.budget = checkBudget(metrics, budget);
  report.timings.total_ms = round(performance.now() - t0, 1);
  report.status = failures.length ? 'FAIL_POLICY' : report.budget.pass ? 'PASS' : 'FAIL_BUDGET';
  if (options.reviewOut) report.review_copy = await writeReviewCopy(io, output, path.resolve(options.reviewOut), options.ktxBin);
  return report;
}

function summarizeFacts(f) {
  const attributeSets = [...new Set(f.primitives.map((p) => Object.entries(p.attributes).map(([k, v]) => `${k}:${v}`).join(',')))];
  return { triangles: f.triangles, draw_calls: f.drawCalls, materials: f.materialCount, meshes: f.meshes, nodes: f.nodes, textures: f.textures, max_attributes: f.maxAttributes, vertex_bytes: f.vertexBytes, index_bytes: f.indexBytes, bounds: f.bounds, extensionsUsed: f.extensionsUsed, extensionsRequired: f.extensionsRequired, attribute_sets: attributeSets, double_sided: f.materials.filter((m) => m.doubleSided).map((m) => m.name), animations: f.animations, skins: f.skins };
}

function readPkgVersion(name) { try { return JSON.parse(readFileSync(path.join(clientRoot, 'node_modules', name, 'package.json'), 'utf8')).version; } catch { return null; } }

/** Blender-importable copy: KTX2 decoded back to PNG (ktx extract --transcode rgba8), embedded; meshopt decoded,
 * quantization kept. For BLENDER REVIEW renders of the exact runtime pixels and geometry. */
export async function writeReviewCopy(io, runtimeGlb, reviewDir, ktxBin) {
  const doc = await io.read(runtimeGlb);
  const tool = doc.getRoot().listTextures().some((t) => t.getMimeType() === 'image/ktx2') ? ktxBinary(ktxBin) : null;
  const tmp = mkdtempSync(path.join(tmpdir(), 'xex-review-'));
  try {
    for (const [i, texture] of doc.getRoot().listTextures().entries()) {
      if (texture.getMimeType() !== 'image/ktx2') continue;
      const src = path.join(tmp, `t${i}.ktx2`); const dst = path.join(tmp, `t${i}.png`);
      writeFileSync(src, texture.getImage());
      const r = spawnSync(tool.exe, ['extract', '--transcode', 'rgba8', src, dst], { encoding: 'utf8' });
      if (r.status !== 0) throw new Error(`ktx extract failed: ${r.stderr}`);
      texture.setImage(new Uint8Array(readFileSync(dst))).setMimeType('image/png').setURI('');
    }
  } finally { rmSync(tmp, { recursive: true, force: true }); }
  doc.getRoot().listExtensionsUsed().filter((e) => ['KHR_texture_basisu', 'EXT_meshopt_compression'].includes(e.extensionName)).forEach((e) => e.dispose());
  const file = path.join(reviewDir, `${path.parse(runtimeGlb).name}.review.glb`);
  writeAtomic(file, Buffer.from(await io.writeBinary(doc)));
  return { file: relRepo(file), note: 'REVIEW ONLY: KTX2 decoded to PNG (rgba8), meshopt decoded, quantized geometry kept; not a runtime file' };
}

// ------------------------------------------------------------------------------------------------ CLI
function parseArgs(argv) {
  const out = { inputs: [] };
  const flags = { '--out': 'output', '--class': 'className', '--tier': 'tier', '--texture-out': 'textureOut', '--texture-uri-prefix': 'textureUriPrefix', '--report': 'report', '--review-out': 'reviewOut', '--budgets': 'budgetsFile', '--ktx-bin': 'ktxBin', '--jobs': 'jobs' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (flags[a]) { if (i + 1 >= argv.length) throw new PostprocessError(`${a} needs a value`, EXIT.USAGE); out[flags[a]] = argv[++i]; }
    else if (a === '--embed-textures') out.embedTextures = true;
    else if (a === '--no-ktx') out.noKtx = true;
    else if (a === '--compare-input') out.compareInput = true;
    else if (a === '--help' || a === '-h') out.help = true;
    else if (a.startsWith('--')) throw new PostprocessError(`Unknown option ${a}`, EXIT.USAGE);
    else out.inputs.push(a);
  }
  return out;
}

export async function main(argv = process.argv.slice(2)) {
  let args;
  try { args = parseArgs(argv); } catch (e) { console.error(e.message); return EXIT.USAGE; }
  if (args.help) { console.log(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 22).join('\n')); return EXIT.OK; }
  let jobs;
  if (args.jobs) jobs = JSON.parse(readFileSync(args.jobs, 'utf8'));
  else if (args.inputs.length === 1 && args.output) jobs = [{ input: args.inputs[0], output: args.output }];
  else { console.error('Usage: gltf-postprocess.mjs <in.glb> --out <out.glb> [--class <budget class>] ... | --jobs jobs.json'); return EXIT.USAGE; }
  const io = await createIO();
  const budgets = loadBudgets(args.budgetsFile ?? DEFAULT_BUDGETS);
  const reports = []; let code = EXIT.OK;
  for (const job of jobs) {
    const opts = { ...args, ...job, className: job.class ?? job.className ?? args.className, io, budgets };
    try {
      const rep = await postprocessGlb(opts);
      reports.push(rep);
      const reportFile = job.report ?? (jobs.length === 1 && args.report ? args.report : `${path.resolve(opts.output)}.report.json`);
      writeAtomic(path.resolve(reportFile), Buffer.from(JSON.stringify(rep, null, 1) + '\n'));
      const m = rep.metrics;
      console.log(`${rep.status} ${rep.output} class=${rep.budget_class}/${rep.tier} tris=${m.triangles} draws=${m.draw_calls} mats=${m.materials} glb=${rep.sizes.glb.raw}B br=${rep.sizes.glb.brotli_q11}B tex=${rep.sizes.external_texture_bytes}B texGPU=${round(m.texture_mib, 2)}MiB`);
      for (const b of rep.budget.breaches) console.error(`BUDGET FAIL ${b}`);
      for (const f of rep.failures) console.error(`POLICY FAIL ${f}`);
      if (rep.status === 'FAIL_POLICY') code = Math.max(code, EXIT.POLICY);
      else if (rep.status === 'FAIL_BUDGET' && code !== EXIT.POLICY) code = EXIT.BUDGET;
    } catch (e) {
      console.error(`ERROR ${job.input}: ${e.message}`);
      code = Math.max(code, e instanceof PostprocessError ? e.exitCode : EXIT.ERROR);
    }
  }
  if (jobs.length > 1 && args.report) writeAtomic(path.resolve(args.report), Buffer.from(JSON.stringify({ schema: 'xexoria.gltf-postprocess-summary/1', reports }, null, 1) + '\n'));
  return code;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((code) => { process.exitCode = code; }, (e) => { console.error(e.stack ?? e); process.exitCode = EXIT.ERROR; });
}
