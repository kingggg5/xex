"""Layout-independent seamless water textures (spec 8.3), project-authored and deterministic.

Every map is built from the periodic (FFT) foundry primitives in assets/blender/city_r5/foundry/fcore.py, so the
tiling ones are seamless by construction (seam_score <= 1.3 is asserted). Seeds come from the map names.

  water_ripple_normal_512.png / _256   fbm(sigma 10 px, 4 oct) + 0.35 ridge(22 px), mean tilt ~9 deg, OpenGL +Y
  water_swell_normal_256.png           fbm(sigma 28 px, 3 oct), mean tilt ~5 deg
  water_foam_noise_256.png / _128      R Voronoi cell edges + fbm, G fine fbm, B streaks (sigma x 2, y 14)
  waterfall_streaks_128x512.png / 64x256  R vertical streaks, G breakup blobs, B foam clumps
  bank_strip_albedo_256x512.png (RGBA, ragged alpha) + bank_strip_normal_256x512.png: zones across U (spec 4.4)
  stream_bed_{albedo,normal,orm}_512.png  sand, pebbles, moss specks; 2 m tile
  river_stone_{albedo,normal}_512.png     painted mottled river stone with lichen; 1 m tile
Data maps (normals, noise) are written without dither; albedos are dithered. A JSON report lists the stats.

Usage: python assets/blender/water/forge_water_textures.py --out assets/textures/sunmeadow-water-v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "assets" / "blender" / "city_r5" / "foundry"))
import fcore as fc  # noqa: E402

F32 = np.float32


def tilt_deg(n):
    return float(np.degrees(np.arccos(np.clip(n[..., 2], -1, 1))).mean())


def normal_with_tilt(h, target_deg, px_m=1.0):
    """Scale a height field so its OpenGL normal map has the requested mean tilt."""
    lo, hi = 0.01, 400.0
    for _ in range(40):
        mid = math.sqrt(lo * hi)
        if tilt_deg(fc.normal_map(h, px_m, mid)) < target_deg:
            lo = mid
        else:
            hi = mid
    n = fc.normal_map(h, px_m, math.sqrt(lo * hi))
    return n, tilt_deg(n)


def encode_normal(n):
    return np.clip(n * 0.5 + 0.5, 0, 1)


def downsample(img, f):
    H, W = img.shape[:2]
    return img.reshape(H // f, f, W // f, f, *img.shape[2:]).mean((1, 3))


def renormalize(enc):
    n = enc * 2 - 1
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    return encode_normal(n)


# ----------------------------------------------------------------------------------------------------------

def ripple(size=512):
    ctx = fc.Ctx("water_ripple_normal", size, 1.0)
    a = fc.fbm(ctx.shape, ctx.key(), 10.0 * size / 512, octaves=4, gain=0.55)
    r = fc.ridge(fc.fbm(ctx.shape, ctx.key(), 22.0 * size / 512, octaves=3))
    h = a + 0.35 * (r - r.mean()) / (r.std() + 1e-9)
    n, t = normal_with_tilt(h, 9.0)
    return encode_normal(n), {"mean_tilt_deg": round(t, 2)}


def swell(size=256):
    ctx = fc.Ctx("water_swell_normal", size, 1.0)
    h = fc.fbm(ctx.shape, ctx.key(), 28.0 * size / 256, octaves=3, gain=0.5)
    n, t = normal_with_tilt(h, 5.0)
    return encode_normal(n), {"mean_tilt_deg": round(t, 2)}


def foam(size=256):
    ctx = fc.Ctx("water_foam_noise", size, 1.0)
    H, W = ctx.shape
    rng = np.random.default_rng(ctx.seed)
    pts = fc.relax_points(rng.uniform(0, [W, H], (int(90 * (size / 256) ** 2), 2)), W, H, iters=2)
    vf = fc.VoronoiField(ctx, pts, k=6, smooth_px=1.2, warp_px=3.0 * size / 256, warp_sigma_px=14.0 * size / 256)
    edge = 1.0 - fc.smoothstep(0.0, 4.5 * size / 256, vf.d)            # 1 on the cell borders (bubble rims)
    fine = fc.to01(fc.fbm(ctx.shape, ctx.key(), 3.0 * size / 256, octaves=3))
    lacy = fc.to01(fc.fbm(ctx.shape, ctx.key(), 11.0 * size / 256, octaves=3))
    R = np.clip(0.55 * edge + 0.30 * lacy + 0.15 * fine, 0, 1)
    # flatten the histogram so coverage scales linearly with the foam mask threshold
    order = np.argsort(R.ravel())
    eq = np.empty_like(R.ravel())
    eq[order] = np.linspace(0, 1, R.size)
    R = eq.reshape(R.shape)
    G = fc.to01(fc.fbm(ctx.shape, ctx.key(), 2.0 * size / 256, octaves=3))
    B = fc.to01(fc.noise(ctx.shape, ctx.key(), 14.0 * size / 256, 2.0 * size / 256))
    return np.stack([R, G, B], -1), {"voronoi_cells": len(pts)}


def streaks(w=128, h=512):
    ctx = fc.Ctx("waterfall_streaks", (h, w), 1.0)
    k = w / 128
    vert = fc.noise(ctx.shape, ctx.key(), 40.0 * k, 1.5 * k)              # sigma_y 40 px (long), sigma_x 1.5 px
    vert2 = fc.noise(ctx.shape, ctx.key(), 18.0 * k, 3.0 * k)
    base = fc.fbm(ctx.shape, ctx.key(), 9.0 * k, octaves=3)
    R = fc.to01(0.62 * vert + 0.28 * vert2 + 0.22 * base)
    R = np.clip((R - 0.18) / 0.72, 0, 1) ** 0.85
    G = fc.to01(fc.fbm(ctx.shape, ctx.key(), 8.0 * k, octaves=3))
    clumps = fc.to01(fc.fbm(ctx.shape, ctx.key(), 5.0 * k, octaves=3, sigma_x=4.0 * k))
    B = fc.smoothstep(0.45, 0.85, clumps)
    return np.stack([R, G, B], -1), {}


def stream_bed(size=512, tile_m=2.0):
    ctx = fc.Ctx("stream_bed", size, tile_m)
    H, W = ctx.shape
    rng = np.random.default_rng(ctx.seed)
    sand = fc.c255(0xB7, 0xA4, 0x7C)
    sand_dk = fc.c255(0x8f, 0x7e, 0x5c)
    peb_lo = fc.c255(0x6F, 0x6A, 0x5E)
    peb_hi = fc.c255(0xA4, 0x9D, 0x8A)
    moss = fc.c255(0x55, 0x64, 0x3A)
    macro = fc.to01(ctx.fbm(0.45, octaves=3))
    ripples = fc.to01(ctx.noise(0.05, 0.25, angle=0.3))
    img = fc.mix(np.broadcast_to(sand, ctx.shape + (3,)).copy(), sand_dk, 0.55 * fc.smoothstep(0.3, 0.8, macro) + 0.15 * ripples)
    # pebbles: two Voronoi scales; a pebble covers its cell interior with a rounded top
    hgt = 0.004 * ripples
    for n_pts, smooth, cover, hmax in ((int(240 * (size / 512) ** 2), 2.0, 0.55, 0.018), (int(900 * (size / 512) ** 2), 1.0, 0.35, 0.008)):
        pts = fc.relax_points(rng.uniform(0, [W, H], (n_pts, 2)), W, H, iters=1)
        vf = fc.VoronoiField(ctx, pts, k=6, smooth_px=smooth, warp_px=2.0, warp_sigma_px=10.0)
        keep = rng.random(n_pts) < cover
        tone = rng.random(n_pts)
        inner = fc.smoothstep(0.8, 6.0 * (size / 512) * (2.4 if hmax > 0.01 else 1.0), vf.d) * keep[vf.eid]
        col = peb_lo[None, None] + (peb_hi - peb_lo)[None, None] * tone[vf.eid][..., None]
        img = fc.mix(img, col, inner)
        hgt = np.maximum(hgt, hmax * np.sqrt(inner))
    specks = fc.smoothstep(0.78, 0.92, fc.to01(ctx.noise(0.012))) * fc.smoothstep(0.35, 0.7, fc.to01(ctx.fbm(0.3, octaves=2)))
    img = fc.mix(img, moss, 0.85 * specks)
    ao = fc.ao_map(hgt, ctx.px, strength=0.6)
    img = img * (0.72 + 0.28 * ao)[..., None]
    img *= (0.90 + 0.20 * macro)[..., None]
    nrm = fc.normal_map(hgt, ctx.px, 1.0)
    rough = np.clip(0.86 + 0.08 * fc.to01(ctx.noise(0.08)) - 0.2 * fc.smoothstep(0.004, 0.018, hgt), 0, 1)
    orm = np.stack([ao, rough, np.zeros_like(ao)], -1)
    lum = fc.luminance(fc.srgb_to_lin(np.clip(img, 0, 1)) if False else np.clip(img, 0, 1))
    k1m = int(ctx.P)                      # luminance std at 1 m scale (spec 4.4: >= 0.12 so the bed reads)
    blocks = lum[: H // k1m * k1m, : W // k1m * k1m].reshape(H // k1m, k1m, W // k1m, k1m)
    std_1m = float(np.mean([blocks[i, :, j, :].std() for i in range(blocks.shape[0]) for j in range(blocks.shape[2])]))
    return np.clip(img, 0, 1), encode_normal(nrm), orm, {"lum_std_1m": round(std_1m, 4), "lum_mean": round(float(lum.mean()), 4)}


def bank_strip(w=256, h=512):
    """U (x, 0..1 across: water -> land) zones from spec 4.4; periodic in V (y). RGBA with a ragged alpha shoulder."""
    ctx = fc.Ctx("bank_strip", (h, w), 1.0)
    rng = np.random.default_rng(ctx.seed)
    yy, xx = fc.grid(h, w)
    U = xx / w
    warp = 0.045 * fc.noise(ctx.shape, ctx.key(), 22.0, 9.0) + 0.02 * fc.noise(ctx.shape, ctx.key(), 6.0)
    Uw = U + warp
    sand = fc.c255(0xB0, 0x9E, 0x78)
    peb_lo = fc.c255(0x6F, 0x6A, 0x5E)
    peb_hi = fc.c255(0x9c, 0x95, 0x82)
    mud = fc.c255(0x4e, 0x40, 0x2e)
    mud_wet = fc.c255(0x3a, 0x30, 0x24)
    soil = fc.c255(0x5b, 0x4a, 0x35)
    moss = fc.c255(0x55, 0x6a, 0x34)
    moss_hi = fc.c255(0x76, 0x8a, 0x44)
    grass = fc.c255(0x60, 0x7a, 0x3a)
    grass_hi = fc.c255(0x86, 0xa0, 0x52)
    img = np.broadcast_to(sand, ctx.shape + (3,)).copy()
    hgt = np.zeros(ctx.shape, F32)
    # pebbles everywhere below the moss line
    pts = fc.relax_points(rng.uniform(0, [w, h], (700, 2)), w, h, iters=1)
    vf = fc.VoronoiField(ctx, pts, k=6, smooth_px=1.0, warp_px=1.5, warp_sigma_px=8.0)
    tone = rng.random(len(pts))
    keep = rng.random(len(pts)) < 0.5
    peb = fc.smoothstep(0.6, 3.5, vf.d) * keep[vf.eid]
    pebcol = peb_lo[None, None] + (peb_hi - peb_lo)[None, None] * tone[vf.eid][..., None]
    zone_wet = fc.smoothstep(0.10, 0.14, Uw)
    zone_moss = fc.smoothstep(0.28, 0.33, Uw)
    zone_grass = fc.smoothstep(0.52, 0.60, Uw)
    img = fc.mix(img, mud, zone_wet * 0.85)
    img = fc.mix(img, pebcol, peb * (1 - zone_moss) * 0.9)
    hgt += 0.010 * peb * (1 - zone_moss)
    # damp line: a thin darker wet band just above the waterline (U ~ 0.13-0.16)
    damp = fc.smoothstep(0.115, 0.13, Uw) * (1 - fc.smoothstep(0.15, 0.185, Uw))
    img = fc.mix(img, mud_wet, 0.75 * damp)
    # wet zone darkening x0.6 (spec), fading up the bank
    wet = (1 - fc.smoothstep(0.24, 0.32, Uw)) * zone_wet
    img = img * (1 - 0.40 * wet)[..., None]
    # moss and root-bound damp soil
    mossy = fc.to01(fc.fbm(ctx.shape, ctx.key(), 7.0, octaves=3))
    mzone = zone_moss * (1 - zone_grass)
    soilmix = fc.mix(np.broadcast_to(soil, ctx.shape + (3,)).copy(), moss, fc.smoothstep(0.35, 0.65, mossy))
    soilmix = fc.mix(soilmix, moss_hi, 0.5 * fc.smoothstep(0.7, 0.9, mossy))
    roots = fc.smoothstep(0.82, 0.95, fc.ridge(fc.noise(ctx.shape, ctx.key(), 18.0, 3.0)))
    soilmix = fc.mix(soilmix, fc.c255(0x3d, 0x30, 0x22), 0.6 * roots)
    img = fc.mix(img, soilmix, mzone)
    hgt += mzone * (0.006 * mossy + 0.004 * roots)
    # grass blending in: clumps with soil showing through, brighter tips
    blades = fc.to01(fc.noise(ctx.shape, ctx.key(), 1.4, 0.5))
    clumps = fc.to01(fc.fbm(ctx.shape, ctx.key(), 9.0, octaves=3))
    gcol = fc.mix(np.broadcast_to(grass, ctx.shape + (3,)).copy(), grass_hi, 0.55 * blades * clumps)
    gcover = zone_grass * fc.smoothstep(0.25, 0.55, clumps * 0.6 + Uw * 0.7)
    img = fc.mix(img, gcol, np.clip(gcover, 0, 1))
    hgt += gcover * 0.008 * blades
    # top-light gradient across the strip and value variation
    img *= (0.92 + 0.10 * fc.to01(fc.fbm(ctx.shape, ctx.key(), 30.0, octaves=2)))[..., None]
    # ragged alpha shoulder 0.85 - 1.0
    edge_noise = 0.06 * fc.noise(ctx.shape, ctx.key(), 10.0, 3.0) + 0.03 * fc.noise(ctx.shape, ctx.key(), 2.5)
    alpha = 1.0 - fc.smoothstep(0.84, 0.98, U + edge_noise * fc.smoothstep(0.7, 0.85, U))
    tufts = fc.smoothstep(0.55, 0.8, blades * clumps)
    alpha = np.clip(alpha + 0.5 * tufts * fc.smoothstep(0.8, 0.95, U) * (1 - fc.smoothstep(0.96, 1.0, U)), 0, 1)
    nrm = fc.normal_map(hgt, 1.85 / w, 1.0)
    rgba = np.concatenate([np.clip(img, 0, 1), alpha[..., None]], -1)
    zones = {f"U{a:.2f}-{b:.2f}": [round(float(v), 3) for v in (np.clip(img, 0, 1)[:, int(a * w):int(b * w)].reshape(-1, 3).mean(0) * 255)]
             for a, b in ((0, 0.12), (0.12, 0.30), (0.30, 0.55), (0.55, 0.85))}
    return rgba, encode_normal(nrm), {"zone_mean_srgb": zones, "alpha_mean_last_15pct": round(float(alpha[:, int(0.85 * w):].mean()), 3)}


def river_stone(size=512, tile_m=1.0):
    ctx = fc.Ctx("river_stone", size, tile_m)
    base = fc.c255(0x92, 0x8a, 0x7c)
    dark = fc.c255(0x5f, 0x5a, 0x52)
    warm = fc.c255(0xa8, 0x98, 0x7c)
    lichen = fc.c255(0xc9, 0xc6, 0x9a)
    lichen2 = fc.c255(0x9a, 0xa5, 0x6a)
    big = fc.to01(ctx.fbm(0.22, octaves=4))
    mid = fc.to01(ctx.fbm(0.06, octaves=3))
    img = fc.mix(np.broadcast_to(base, ctx.shape + (3,)).copy(), dark, 0.55 * fc.smoothstep(0.35, 0.75, big))
    img = fc.mix(img, warm, 0.35 * fc.smoothstep(0.55, 0.85, mid))
    spots = fc.smoothstep(0.80, 0.90, fc.to01(ctx.noise(0.008))) * fc.smoothstep(0.4, 0.7, fc.to01(ctx.fbm(0.15, octaves=2)))
    img = fc.mix(img, lichen, 0.75 * spots)
    spots2 = fc.smoothstep(0.82, 0.93, fc.to01(ctx.noise(0.014))) * fc.smoothstep(0.5, 0.8, fc.to01(ctx.fbm(0.2, octaves=2)))
    img = fc.mix(img, lichen2, 0.65 * spots2)
    pits = fc.smoothstep(0.72, 0.9, fc.ridge(ctx.noise(0.02)))
    hgt = 0.004 * (big - 0.5) + 0.002 * mid - 0.0015 * pits
    ao = fc.ao_map(hgt, ctx.px, strength=0.5)
    img *= (0.80 + 0.20 * ao)[..., None]
    nrm = fc.normal_map(hgt, ctx.px, 1.0)
    # Duplicate the periodic endpoint texel after differentiation. The source
    # FFT height is periodic; this gives the raster a continuous filter border.
    nrm[-1, :] = nrm[0, :]
    nrm[:, -1] = nrm[:, 0]
    return np.clip(img, 0, 1), encode_normal(nrm), {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "assets" / "textures" / "sunmeadow-water-v1"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"schema": "xexoria.water-textures/1", "generator": "assets/blender/water/forge_water_textures.py",
              "licence": "project-authored, procedural (no third-party source)", "files": {}}

    def save(name, arr, dither, seamless=True, stats=None, mode=None):
        path = out / name
        fc.save_png(str(path), arr, mode=mode, dither=dither)
        rec = {"size": [int(arr.shape[1]), int(arr.shape[0])], "channels": int(arr.shape[2]) if arr.ndim == 3 else 1,
               "dither": dither, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
        if seamless:
            score = fc.seam_score(arr[..., :3] if arr.ndim == 3 else arr)
            rec["seam_score"] = round(float(score), 3)
            if score > 1.3:
                raise SystemExit(f"{name}: seam score {score:.3f} > 1.3")
        if stats:
            rec.update(stats)
        report["files"][name] = rec

    n512, st = ripple(512)
    save("water_ripple_normal_512.png", n512, False, stats=st)
    save("water_ripple_normal_256.png", renormalize(downsample(n512, 2)), False)
    sw, st = swell(256)
    save("water_swell_normal_256.png", sw, False, stats=st)
    fo, st = foam(256)
    save("water_foam_noise_256.png", fo, False, stats=st)
    save("water_foam_noise_128.png", downsample(fo, 2), False)
    sk, st = streaks(128, 512)
    save("waterfall_streaks_128x512.png", sk, False, stats=st)
    save("waterfall_streaks_64x256.png", downsample(sk, 2), False)
    alb, nrm, orm, st = stream_bed(512, 2.0)
    save("stream_bed_albedo_512.png", alb, True, stats=st)
    save("stream_bed_normal_512.png", nrm, False)
    save("stream_bed_orm_512.png", orm, False)
    rgba, bnrm, st = bank_strip(256, 512)
    # periodic in V only: check the V seam (rows) and skip the clamped U edges
    v_seam = float(np.abs(rgba[0, :, :3] - rgba[-1, :, :3]).mean() / (np.abs(np.diff(rgba[..., :3], axis=0)).mean() + 1e-9))
    st["v_seam_score"] = round(v_seam, 3)
    if v_seam > 1.3:
        raise SystemExit(f"bank strip V seam {v_seam:.3f} > 1.3")
    save("bank_strip_albedo_256x512.png", rgba, True, seamless=False, stats=st, mode="RGBA")
    save("bank_strip_normal_256x512.png", bnrm, False, seamless=False)
    salb, snrm, st = river_stone(512, 1.0)
    save("river_stone_albedo_512.png", salb, True, stats=st)
    save("river_stone_normal_512.png", snrm, False)
    (out / "textures-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: {kk: v[kk] for kk in v if kk in ("seam_score", "mean_tilt_deg", "lum_std_1m", "v_seam_score")} for k, v in report["files"].items()}, indent=1))


if __name__ == "__main__":
    main()
