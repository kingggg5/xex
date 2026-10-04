"""Terrain texture checks (terrain spec §6 script 6; §3.3 targets, §6.2 KTX2 checks).

Commands (run from the repo root; numpy only, plus the shared terrain modules):

  python tools/terrain/check_terrain_textures.py pack --staging <dir>
      Builds the runtime packs from the forge R7 sources (layers-r7/forge-manifest.json):
        AH  = albedo sRGB bytes (RGB) + 8-bit height (A)             -> <id>_ah_<res>.png
        NRO = normal X, normal Y, roughness, AO, explicit mip chain  -> <id>_nro_<res>_m<k>.png
      NRO mips: decoded-vector average, renormalise, Toksvig widening r' = sqrt(r^2 + 0.5 (1 - |n_avg|)).
      Lower-resolution variants are the next levels of the same chains (512 = level 1 of the 1024 chain).
      Runs the §6.2 item 2 pre-checks and writes <dir>/pack.json (files, pre-checks, layer far-path means).

  python tools/terrain/check_terrain_textures.py decoded --staging <dir> [--report <json>]
      Reads the levels extracted from the encoded KTX2 files (ktx extract --transcode rgba8 --level all) and checks
      §6.2 item 6-7 (PSNR, height, normal angle, roughness/AO errors, seams on mips 0-3, normal-Y) plus the §3.3
      targets on decoded mip0 and mip2. Writes the texture-stats report (default
      planning/evidence/terrain-splat-v1/texture-stats.json). Exit 1 on any failure.

  python tools/terrain/check_terrain_textures.py --self-test
      Synthetic fixtures for every statistic (flat/tilted normals, flipped green, seams, PSNR, Toksvig, packing).

Orientation: KTX2 files are written with --convert-texcoord-origin bottom-left (Babylon uploads KTX2 rows as stored and
ignores invertY; PNGs load with invertY = true). The decoded check detects the stored row order, records it, and
un-flips before comparing with the PNG packs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'assets' / 'blender' / 'sunmeadow_v2' / 'terrain'))
import terrain_png as TP  # noqa: E402
import terrain_spec as TS  # noqa: E402
import terrain_stats as ST  # noqa: E402

EVIDENCE = ROOT / TS.EVIDENCE_DIR
REPORT = EVIDENCE / 'texture-stats.json'
LAYER_DIR = ROOT / TS.LAYER_SOURCE_DIR
CELL_DIR = ROOT / TS.CELL_SOURCE_DIR
GATES = TS.GATES


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def read_rgb01(path: Path) -> np.ndarray:
    a = TP.read_png(path)
    if a.ndim == 2:
        a = a[..., None]
    scale = 65535.0 if a.dtype == np.uint16 else 255.0
    return a.astype(np.float64) / scale


# ----------------------------------------------------------------------------
# Packing (AH / NRO) and the NRO mip chain
# ----------------------------------------------------------------------------

def nro_chain(normal: np.ndarray, rough: np.ndarray, ao: np.ndarray, levels: int) -> list:
    """Explicit NRO mips: level 0 is the source; each next level averages the decoded vectors, renormalises, and
    widens roughness by Toksvig (sqrt(r^2 + 0.5 (1 - |n_avg|))); AO is box-averaged."""
    chain = [(normal, rough, ao)]
    n, r, a = normal, rough, ao
    for _ in range(1, levels):
        n, length = ST.normal_mip(n)
        r = np.sqrt(ST.box_down(r, 2) ** 2 + 0.5 * (1.0 - np.clip(length, 0.0, 1.0)))
        r = np.clip(r, 0.0, 1.0)
        a = ST.box_down(a, 2)
        chain.append((n, r, a))
    return chain


def encode_nro(n: np.ndarray, r: np.ndarray, a: np.ndarray) -> np.ndarray:
    xy = np.clip(np.rint((n[..., :2] * 0.5 + 0.5) * 255.0), 0, 255)
    return np.concatenate([xy, np.clip(np.rint(r * 255.0), 0, 255)[..., None], np.clip(np.rint(a * 255.0), 0, 255)[..., None]],
                          -1).astype(np.uint8)


def ah_level(albedo_srgb: np.ndarray, height01: np.ndarray, factor: int) -> np.ndarray:
    """AH at 1/factor resolution: albedo averaged in linear light and re-encoded as sRGB bytes; height box-averaged."""
    lin = ST.box_down(srgb_to_linear(albedo_srgb), factor)
    h = ST.box_down(height01, factor)
    rgb = np.clip(np.rint(linear_to_srgb(lin) * 255.0), 0, 255)
    return np.concatenate([rgb, np.clip(np.rint(h * 255.0), 0, 255)[..., None]], -1).astype(np.uint8)


def layer_sources(layer: dict) -> dict:
    name = layer['name']
    return {k: LAYER_DIR / f'{name}_{k}.png' for k in ('albedo', 'normal', 'orm', 'height')}


def precheck_layer(layer: dict, src: dict) -> tuple[dict, list]:
    fails = []
    alb = read_rgb01(src['albedo'])[..., :3]
    nrm = TP.read_png(src['normal'])
    orm = TP.read_png(src['orm'])
    h = read_rgb01(src['height'])[..., 0]
    size = alb.shape[0]
    out = dict(size=size)
    if size & (size - 1) or alb.shape[0] != alb.shape[1]:
        fails.append(f'{layer["id"]}: not a power-of-two square ({alb.shape[:2]})')
    seams = {k: round(ST.seam_score(v.astype(np.float64)), 4) for k, v in
             (('albedo', alb), ('normal', nrm), ('orm', orm), ('height', h))}
    out['seams'] = seams
    for k, s in seams.items():
        if s > GATES['seam_max']:
            fails.append(f'{layer["id"]}: source seam {k} {s} > {GATES["seam_max"]}')
    flat = alb.reshape(-1, 3)
    p01 = [float(np.percentile(flat[:, c], 0.1)) for c in range(3)]
    p999 = [float(np.percentile(flat[:, c], 99.9)) for c in range(3)]
    out['albedo_p01'], out['albedo_p999'] = p01, p999
    if min(p01) < GATES['albedo_channel_p01_min'] or max(p999) > GATES['albedo_channel_p999_max']:
        fails.append(f'{layer["id"]}: albedo outside [0.04, 0.90] (p0.1 {min(p01):.3f}, p99.9 {max(p999):.3f})')
    hp1, hp99 = float(np.percentile(h, 1)), float(np.percentile(h, 99))
    out['height_p1'], out['height_p99'] = hp1, hp99
    if hp1 > GATES['height_p1_max'] or hp99 < GATES['height_p99_min']:
        fails.append(f'{layer["id"]}: height range unused (p1 {hp1:.3f}, p99 {hp99:.3f})')
    metal_max = int(orm[..., 2].max())
    out['orm_metal_max'] = metal_max
    if metal_max != 0:
        fails.append(f'{layer["id"]}: source ORM B (metal) max {metal_max}, must be exactly 0')
    return out, fails


def precheck_cells() -> tuple[dict, list]:
    """Per-cell data PNGs: RGB8, no colour chunks (spec §3.4, §6.2 item 2)."""
    fails, out = [], {}
    for path in sorted(CELL_DIR.glob('*/*.png')):
        if 'mask-preview' in path.name:
            continue
        data = path.read_bytes()
        ihdr = data[16:29]
        bits, ctype = ihdr[8], ihdr[9]
        chunks = TP.chunks(path)
        bad = [c for c in chunks if c in TS.FORBIDDEN_PNG_CHUNKS]
        ok = bits == 8 and ctype == 2 and not bad
        out[rel(path)] = dict(bits=bits, colour_type=ctype, chunks=chunks, ok=ok)
        if not ok:
            fails.append(f'{rel(path)}: must be RGB8 without {TS.FORBIDDEN_PNG_CHUNKS} (bits {bits}, type {ctype}, bad {bad})')
    return out, fails


def cmd_pack(staging: Path) -> int:
    staging.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((LAYER_DIR / 'forge-manifest.json').read_text(encoding='utf-8'))['layers']
    pack = dict(schema='xexoria.terrain-pack/1', created=time.strftime('%Y-%m-%dT%H:%M:%S'), layers={}, failures=[])
    for layer in TS.ALL_LAYERS:
        lid = layer['id']
        if lid not in manifest:
            pack['failures'].append(f'{lid}: missing from forge-manifest.json')
            continue
        src = layer_sources(layer)
        pre, fails = precheck_layer(layer, src)
        pack['failures'] += fails
        size = pre['size']
        resolutions = sorted({int(v) for v in layer['res'].values()}, reverse=True)
        albedo = read_rgb01(src['albedo'])[..., :3]
        height = read_rgb01(src['height'])[..., 0]
        normal = ST.decode_normal(TP.read_png(src['normal']))
        orm = read_rgb01(src['orm'])
        levels0 = int(math.log2(size)) + 1
        chain = nro_chain(normal, orm[..., 1], orm[..., 0], levels0)
        rec = dict(id=lid, name=layer['name'], kind=layer['kind'], tile_m=layer['tile_m'], source_px=size, precheck=pre,
                   sources={k: dict(path=rel(p), sha256=sha(p)) for k, p in src.items()}, ah={}, nro={})
        for res in resolutions:
            if res > size:
                pack['failures'].append(f'{lid}: requested {res} above the {size} source')
                continue
            factor = size // res
            first = int(math.log2(factor))
            ah = ah_level(albedo, height, factor)
            ah_path = staging / f'{lid}_ah_{res}.png'
            TP.write_png(ah_path, ah)
            # KTX inputs are written bottom row first and tagged --assign-texcoord-origin bottom-left: Babylon uploads
            # KTX2 rows as stored and ignores invertY, so this samples like the PNG with invertY = true. (KTX 4.4.2
            # --convert-texcoord-origin segfaults with many explicit levels, so the flip happens here.)
            TP.write_png(staging / f'k_{ah_path.name}', ah[::-1])
            rec['ah'][str(res)] = dict(png=ah_path.name, ktx_input=f'k_{ah_path.name}', levels=int(math.log2(res)) + 1)
            files = []
            for k, (n, r, a) in enumerate(chain[first:]):
                p = staging / f'{lid}_nro_{res}_m{k}.png'
                level = encode_nro(n, r, a)
                TP.write_png(p, level)
                TP.write_png(staging / f'k_{p.name}', level[::-1])
                files.append(p.name)
            rec['nro'][str(res)] = dict(levels=files, ktx_inputs=[f'k_{f}' for f in files])
        # far-path means from the lowest mip (spec §3.6 far LOD): linear albedo, roughness
        lin_mean = srgb_to_linear(albedo).reshape(-1, 3).mean(0)
        rec['mean_linear_rgb'] = [round(float(v), 5) for v in lin_mean]
        rec['mean_roughness'] = round(float(chain[-1][1].mean()), 5)
        pack['layers'][lid] = rec
    cells, cell_fails = precheck_cells()
    pack['cells_precheck'] = cells
    pack['failures'] += cell_fails
    (staging / 'pack.json').write_text(json.dumps(pack, indent=1) + '\n', encoding='utf-8')
    print(f'PACK: {len(pack["layers"])} layers, {len(cells)} cell PNGs pre-checked, {len(pack["failures"])} failure(s)')
    for f in pack['failures']:
        print('   FAIL', f)
    return 1 if pack['failures'] else 0


def cmd_calibration(staging: Path) -> int:
    """Lab-only orientation calibration (spec §6.2 item 8, §8.5 probes): 256^2 AH and NRO, alpha = 255 everywhere.

    AH: sRGB 128 grey card (linear 0.216 after the shader decode) with a red arrow pointing to image top (= +Z when the
    PNG loads with invertY = true) and an asymmetric flag on its right (mirror check). NRO: one hemispherical bump in
    the lower-left quadrant (lit from the sun side when Y is not flipped), roughness 0.5, AO 1."""
    n = 256
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    ah = np.zeros((n, n, 4), np.uint8)
    ah[..., :3] = 128
    ah[..., 3] = 255
    shaft = (np.abs(xx - 128) < 10) & (yy > 70) & (yy < 220)
    head = (yy >= 24) & (yy <= 80) & (np.abs(xx - 128) < (yy - 24) * 0.75)
    flag = (xx > 138) & (xx < 190) & (yy > 96) & (yy < 124)
    for mask, colour in ((shaft | head, (200, 40, 32)), (flag, (40, 90, 200))):
        ah[mask, 0], ah[mask, 1], ah[mask, 2] = colour
    cx, cy, rad = 64.0, 192.0, 40.0
    dx, dy = (xx - cx) / rad, -(yy - cy) / rad          # dy > 0 = image up (OpenGL +Y)
    rr = dx * dx + dy * dy
    inside = rr < 1
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    nrm = np.zeros((n, n, 3))
    nrm[..., 2] = 1
    nrm[inside, 0], nrm[inside, 1], nrm[inside, 2] = dx[inside], dy[inside], np.maximum(nz[inside], 0.05)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    nro = encode_nro(nrm, np.full((n, n), 0.5), np.ones((n, n)))
    files = {}
    for name, arr in (('terrain_calibration_ah', ah), ('terrain_calibration_nro', nro)):
        TP.write_png(staging / f'{name}.png', arr)
        TP.write_png(staging / f'k_{name}.png', arr[::-1])
        files[name] = dict(png=f'{name}.png', ktx_input=f'k_{name}.png')
    (staging / 'calibration.json').write_text(json.dumps(dict(size=n, files=files, grey_card_srgb=128,
                                                                grey_card_linear=round(float(srgb_to_linear(128 / 255)), 4),
                                                                arrow='image top = +Z', bump_centre_px=[cx, cy]), indent=1) + '\n',
                                              encoding='utf-8')
    print('CALIBRATION: wrote terrain_calibration_{ah,nro}.png (+ bottom-left KTX inputs)')
    return 0


# ----------------------------------------------------------------------------
# Decoded-KTX2 checks
# ----------------------------------------------------------------------------

def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if mse <= 1e-12 else 10 * math.log10(255.0 ** 2 / mse)


def angle_err_deg(xy_a: np.ndarray, xy_b: np.ndarray) -> np.ndarray:
    na, nb = ST.decode_normal_xy(xy_a), ST.decode_normal_xy(xy_b)
    return np.degrees(np.arccos(np.clip((na * nb).sum(-1), -1.0, 1.0)))


def load_levels(folder: Path) -> list:
    """Extracted levels (ktx extract --level all writes one PNG per level); sorted by size, largest first."""
    from PIL import Image  # system Python only: ktx extract writes palette PNGs for small levels (colour type 3)
    files = sorted(folder.glob('*.png'))
    arrays = [np.asarray(Image.open(p).convert('RGBA')) for p in files]
    order = sorted(range(len(arrays)), key=lambda i: -arrays[i].shape[0])
    return [arrays[i] for i in order]


def orient(decoded: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, str]:
    """Return the decoded level in PNG row order and the stored order ('bottom-left' = rows reversed)."""
    d = decoded.astype(np.float64)
    r = reference.astype(np.float64)
    direct = np.abs(d - r).mean()
    flipped = np.abs(d[::-1] - r).mean()
    return (decoded[::-1], 'bottom-left') if flipped < direct else (decoded, 'top-left')


def stats_at(layer: dict, ah: np.ndarray, nro: np.ndarray, label: str, mip: int) -> tuple[dict, list]:
    albedo = ah[..., :3] / 255.0
    h01 = ah[..., 3] / 255.0
    normal = ST.decode_normal_xy(nro[..., :2])
    rough, ao = nro[..., 2] / 255.0, nro[..., 3] / 255.0
    stats, all_fails = ST.layer_report(layer, GATES, albedo, normal, rough, ao, h01, label=label)
    if mip == 0:
        return stats, all_fails
    # mip2: the §3.3 "mean tilt at mip2" minimum plus the resolution-independent gates (albedo range and means,
    # roughness mean, normal-Y). Tilt band, flat fraction, roughness adjacency (one mip2 texel spans 4 px, so
    # adjacent deltas grow ~4x by construction) and normal/height agreement (Toksvig vector average vs lanczos
    # height) are mip0 gates; their mip2 values are reported in `stats`.
    keep = ('albedo p0.1', 'albedo p99.9', 'lum mean', 'sat', 'rough mean', 'normal-Y')
    fails = [f for f in all_fails if any(k in f for k in keep)]
    tilt = stats['normal']['mean']
    if tilt < layer['targets']['normal']['mip2_mean_min']:
        fails.append(f'{layer["id"]} {label}: decoded mip2 mean tilt {tilt:.2f} < {layer["targets"]["normal"]["mip2_mean_min"]}')
    return stats, fails


def seam_block(img: np.ndarray) -> float:
    """Tile-edge discontinuity relative to the interior 4x4 block boundaries of the same level.

    The forge seam metric divides the edge pair by the mean gradient over all pairs; after UASTC the edge pair always
    straddles a block boundary while 3/4 of the interior pairs do not, so the raw metric rises from <= 1.15 to 1.2-1.5
    at mip0 with no mip filtering involved. Normalising by interior block-boundary pairs isolates a real wrap seam
    (e.g. clamp-generated mips), which is what §6.2 item 6 guards."""
    a = img.astype(np.float64)
    if a.ndim == 2:
        a = a[..., None]
    h, w = a.shape[:2]
    if h < 8 or w < 8:
        return 1.0
    edge = max(np.abs(a[:, 0] - a[:, -1]).mean(), np.abs(a[0] - a[-1]).mean())
    cols = [np.abs(a[:, k - 1] - a[:, k]).mean() for k in range(4, w, 4)]
    rows = [np.abs(a[k - 1] - a[k]).mean() for k in range(4, h, 4)]
    return float(edge / max(1e-9, (np.mean(cols) + np.mean(rows)) / 2))


def cmd_decoded(staging: Path, report: Path) -> int:
    pack = json.loads((staging / 'pack.json').read_text(encoding='utf-8'))
    encoded = json.loads((staging / 'encoded.json').read_text(encoding='utf-8'))
    out = dict(schema='xexoria.terrain-texture-stats/1', spec=TS.SPEC_DOC, created=time.strftime('%Y-%m-%dT%H:%M:%S'),
               method=dict(normals='rgb/127.5 - 1, renormalised (NRO: Z reconstructed from XY); tilt from +Z; flat <= 1 deg',
                           roughness='ORM G / NRO B; never-noisy = adjacent |dr| p95', albedo='sRGB bytes; Rec.709 luma on sRGB values',
                           decoded='ktx extract --transcode rgba8 --level all; rows un-flipped from the stored bottom-left origin',
                           mip2='§3.3 mip2 tilt minimum + resolution-independent gates (albedo range/means, roughness mean and '
                                'adjacency, normal-Y, normal/height); tilt band and flat fraction are mip0 targets'),
               gates=GATES, layers={}, failures=list(pack.get('failures', [])),
               failures_by_category={'precheck': list(pack.get('failures', []))} if pack.get('failures') else {})
    by_id = TS.LAYER_BY_ID
    for lid, rec in pack['layers'].items():
        layer = by_id[lid]
        lrep = dict(id=lid, name=rec['name'], source=dict(precheck=rec['precheck']), decoded={})
        # §3.3 on the runtime-resolution source PNG (forge output) - the composite already gated it; re-measured here
        src = layer_sources(layer)
        s_stats, s_fails = ST.layer_report(layer, GATES, read_rgb01(src['albedo'])[..., :3],
                                           ST.decode_normal(TP.read_png(src['normal'])), read_rgb01(src['orm'])[..., 1],
                                           read_rgb01(src['orm'])[..., 0], read_rgb01(src['height'])[..., 0], label='png')
        lrep['source'].update(stats=s_stats, failures=s_fails)
        out['failures'] += s_fails
        if s_fails:
            out['failures_by_category'].setdefault('source', []).extend(s_fails)
        for res in rec['ah']:
            key = f'{lid}_{res}'
            enc = encoded.get(key)
            if not enc:
                out['failures'].append(f'{key}: not encoded')
                continue
            ah_ref0 = TP.read_png(staging / rec['ah'][res]['png'])
            ah_dec = load_levels(staging / 'decoded' / f'{lid}_ah_{res}')
            ah_refl = load_levels(staging / 'decoded' / f'{lid}_ahref_{res}')
            nro_ref = [TP.read_png(staging / f) for f in rec['nro'][res]['levels']]
            nro_dec = load_levels(staging / 'decoded' / f'{lid}_nro_{res}')
            fails = []          # (category, message); categories map to the §6.2 receipt items
            high = res == str(layer['res']['high'])
            if len(ah_dec) != len(nro_ref) or len(nro_dec) != len(nro_ref):
                fails.append(('levels', f'{key}: level count AH {len(ah_dec)} NRO {len(nro_dec)} expected {len(nro_ref)}'))
            ah0, order_ah = orient(ah_dec[0], ah_ref0)
            nro0, order_nro = orient(nro_dec[0], nro_ref[0])
            flip = lambda a, o: a[::-1] if o == 'bottom-left' else a  # noqa: E731
            ah_dec = [flip(a, order_ah) for a in ah_dec]
            ah_refl = [flip(a, order_ah) for a in ah_refl]
            nro_dec = [flip(a, order_nro) for a in nro_dec]
            errors = {}
            for mip in (0, 2):
                if mip >= len(ah_dec):
                    continue
                ref_ah = ah_ref0 if mip == 0 else ah_refl[mip]
                p = psnr(ah_dec[mip][..., :3], ref_ah[..., :3])
                hd = np.abs(ah_dec[mip][..., 3].astype(np.int32) - ref_ah[..., 3].astype(np.int32))
                ang = angle_err_deg(nro_dec[mip][..., :2], nro_ref[mip][..., :2])
                rd = np.abs(nro_dec[mip][..., 2:].astype(np.int32) - nro_ref[mip][..., 2:].astype(np.int32))
                e = dict(ah_psnr_db=round(p, 2), height_err_max=int(hd.max()), height_err_mean=round(float(hd.mean()), 3),
                         normal_err_mean_deg=round(float(ang.mean()), 3), normal_err_p99_deg=round(float(np.percentile(ang, 99)), 3),
                         rough_ao_err_p99=float(np.percentile(rd, 99)))
                errors[f'mip{mip}'] = e
                lim_psnr = GATES['ah_psnr_mip0_min'] if mip == 0 else GATES['ah_psnr_mip2_min']
                if p < lim_psnr:
                    fails.append(('decode-error', f'{key} mip{mip}: AH PSNR {p:.2f} < {lim_psnr}'))
                if mip == 0:
                    if e['height_err_max'] > GATES['height_err_max'] or e['height_err_mean'] > GATES['height_err_mean_max']:
                        fails.append(('decode-error', f'{key} mip0: height error max {e["height_err_max"]} mean {e["height_err_mean"]}'))
                    if e['normal_err_mean_deg'] > GATES['normal_err_mean_max_deg'] or e['normal_err_p99_deg'] > GATES['normal_err_p99_max_deg']:
                        fails.append(('decode-error', f'{key} mip0: normal angle error mean {e["normal_err_mean_deg"]} p99 {e["normal_err_p99_deg"]}'))
                    if e['rough_ao_err_p99'] > GATES['rough_ao_err_p99_max']:
                        fails.append(('decode-error', f'{key} mip0: roughness/AO error p99 {e["rough_ao_err_p99"]}'))
            stats, lower_tier = {}, []
            for mip in (0, 2):
                if mip < len(ah_dec):
                    st, sf = stats_at(layer, ah_dec[mip], nro_dec[mip], f'decoded {res} mip{mip}', mip)
                    stats[f'mip{mip}'] = st
                    # §3.3 targets are defined on each layer's runtime-resolution (High-tier) file; lower-tier variants
                    # (the next levels of the same chains) are reported, not gated
                    if high:
                        fails += [('decoded-stats', f'{key}: {f}') for f in sf]
                    else:
                        lower_tier += sf
            seams, seams_raw = {}, {}
            for mip in range(min(4, len(ah_dec))):
                maps = (ah_dec[mip][..., :3], ah_dec[mip][..., 3], nro_dec[mip])
                seams_raw[f'mip{mip}'] = round(max(ST.seam_score(m.astype(np.float64)) for m in maps), 4)
                sc = max(seam_block(m) for m in maps)
                seams[f'mip{mip}'] = round(sc, 4)
                if sc > GATES['seam_mips_max']:
                    fails.append(('seam', f'{key} mip{mip}: decoded seam (block-normalised) {sc:.3f} > {GATES["seam_mips_max"]}'))
            ny = ST.normal_y_check(ST.decode_normal_xy(nro_dec[0][..., :2]), ah_dec[0][..., 3] / 255.0)
            if ny <= GATES['normal_y_corr_min']:
                fails.append(('normal-y', f'{key}: normal-Y corr {ny:.3f} <= {GATES["normal_y_corr_min"]} (flipped green?)'))
            lrep['decoded'][res] = dict(tier_file='high' if high else 'lower', stored_row_order=dict(ah=order_ah, nro=order_nro),
                                        levels=len(ah_dec), errors=errors, stats=stats, seams_mips_0_3=seams,
                                        seams_mips_0_3_raw=seams_raw, normal_y_corr=round(ny, 4),
                                        failures=[m for _, m in fails], lower_tier_notes=lower_tier, files=enc)
            for cat, msg in fails:
                out['failures'].append(msg)
                out['failures_by_category'].setdefault(cat, []).append(msg)
        out['layers'][lid] = lrep
    out['pass'] = not out['failures']
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print(f'DECODED: {len(out["layers"])} layers, {"PASS" if out["pass"] else "FAIL"} ({len(out["failures"])} failure(s)); report {rel(report)}')
    for f in out['failures']:
        print('   FAIL', f)
    return 0 if out['pass'] else 1


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------

def self_test() -> int:
    import unittest

    class T(unittest.TestCase):
        def test_flat_and_tilt(self):
            n = np.zeros((16, 16, 3))
            n[..., 2] = 1
            s = ST.normal_stats(n)
            self.assertEqual(s['flat'], 1.0)
            t = math.radians(10)
            n2 = np.zeros((16, 16, 3))
            n2[..., 0], n2[..., 2] = math.sin(t), math.cos(t)
            self.assertAlmostEqual(ST.normal_stats(n2)['mean'], 10.0, places=5)

        def test_normal_y_flip_detected(self):
            v = np.linspace(0, 1, 64)
            h = np.tile(np.sin(v * 2 * np.pi * 3)[:, None], (1, 64))  # varies along rows
            n = ST.normal_from_height(h * 0.05, 0.01)
            self.assertGreater(ST.normal_y_check(n, h), 0.9)
            flipped = n.copy()
            flipped[..., 1] *= -1
            self.assertLess(ST.normal_y_check(flipped, h), -0.9)

        def test_seam(self):
            # isotropic periodic noise is seamless (edge pair ~ interior gradient); a ramp has a hard wrap seam
            a = ST.gaussian_periodic(np.random.default_rng(3).normal(size=(128, 128)), 2.0).astype(np.float64)
            self.assertLess(ST.seam_score(a), 1.2)
            b = np.tile(np.linspace(0, 1, 64)[None, :], (64, 1)) + np.linspace(0, 1, 64)[:, None]
            self.assertGreater(ST.seam_score(b), 10)

        def test_psnr_and_angle(self):
            a = np.full((8, 8, 3), 100, np.uint8)
            self.assertEqual(psnr(a, a), 99.0)
            b = a.copy()
            b[0, 0, 0] = 110
            self.assertGreater(psnr(a, b), 38)
            xy = np.full((4, 4, 2), 128, np.uint8)
            self.assertLess(float(angle_err_deg(xy, xy).max()), 1e-6)

        def test_toksvig_widens_and_renormalises(self):
            rng = np.random.default_rng(1)
            n = rng.normal(0, 0.3, (32, 32, 3))
            n[..., 2] = 1
            n /= np.linalg.norm(n, axis=-1, keepdims=True)
            r = np.full((32, 32), 0.5)
            chain = nro_chain(n, r, np.ones((32, 32)), 6)
            self.assertEqual([c[0].shape[0] for c in chain], [32, 16, 8, 4, 2, 1])
            self.assertTrue(np.allclose(np.linalg.norm(chain[2][0], axis=-1), 1.0))
            self.assertGreater(float(chain[1][1].mean()), 0.5)          # widened
            self.assertTrue(np.all(np.diff([float(c[1].mean()) for c in chain]) >= -1e-9))

        def test_pack_encodings(self):
            n = np.zeros((4, 4, 3))
            n[..., 2] = 1
            e = encode_nro(n, np.full((4, 4), 0.5), np.ones((4, 4)))
            self.assertTrue(np.all(e[..., 0] == 128) and np.all(e[..., 2] == 128) and np.all(e[..., 3] == 255))
            alb = np.full((4, 4, 3), 0.5)
            ah = ah_level(alb, np.full((4, 4), 0.25), 2)
            self.assertEqual(ah.shape, (2, 2, 4))
            self.assertEqual(int(ah[0, 0, 0]), 128)                     # sRGB 0.5 survives the linear average
            self.assertEqual(int(ah[0, 0, 3]), 64)

        def test_orientation_detection(self):
            ref = np.arange(64, dtype=np.uint8).reshape(8, 8)
            got, order = orient(ref[::-1].copy(), ref)
            self.assertEqual(order, 'bottom-left')
            self.assertTrue(np.array_equal(got, ref))

    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    return 0 if result.wasSuccessful() else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--self-test' in argv:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('command', choices=('pack', 'calibration', 'decoded'))
    ap.add_argument('--staging', required=True)
    ap.add_argument('--report', default=str(REPORT))
    args = ap.parse_args(argv)
    staging = Path(args.staging)
    staging.mkdir(parents=True, exist_ok=True)
    if args.command == 'pack':
        return cmd_pack(staging)
    if args.command == 'calibration':
        return cmd_calibration(staging)
    return cmd_decoded(staging, Path(args.report))


if __name__ == '__main__':
    raise SystemExit(main())
