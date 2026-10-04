"""Stage 2 (system Python 3.12 + numpy + scipy + Pillow): paint atlases from the baked data maps.

  python np_paint.py --kit rocks [--atlas sm_rock_a,...] [--cache DIR]

Writes <cache>/<kit>/tex/<atlas>_albedo.png (sRGB), _normal.png (OpenGL +Y, from the high-poly bake),
_orm.png (R = AO, G = roughness, B = metallic). The albedo is built in the six llm.txt layers:
  1 base (gradient-map ramp of a paint value), 2 large top-light gradient (world-up normal) and key light,
  3 cavity occlusion (baked AO + broad/fine concavity), 4 edge highlights (fine convexity),
  5 hue/value variation (seeded 3D noise at the baked local position, seamless across UV seams),
  6 story marks (moss on up-facing areas with a damp rim and specks, lichen dots, water streaks, ground-contact
    soil, wet line and algae for stream stones, strata bands and grass tops for cliffs).
Albedo values stay inside [0.035, 0.93] (no pure black or white). Everything is deterministic per asset seed.
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))


import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import np_noise as NZ  # noqa: E402

CACHE = Path(os.environ.get("NP_CACHE", str(_XEXORIA_AGENT_OUTPUT / '20261002-sunmeadow-props/cache')))


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def ramp_stops(spec):
    return np.array([p for p, _ in spec]), np.stack([hexrgb(c) for _, c in spec])


PALETTES = {
    "sun_stone": dict(
        ramp=ramp_stops([(0.00, "#2a2731"), (0.16, "#433e49"), (0.32, "#5f5759"), (0.47, "#7c7166"),
                         (0.62, "#998b77"), (0.76, "#b7a88e"), (0.89, "#d4c7ab"), (1.00, "#eadfc6")]),
        ochre=np.array([1.09, 1.0, 0.84]), blue=np.array([0.91, 0.97, 1.09]), cav=hexrgb("#3b3549"),
        hilite=hexrgb("#efe4cd"), soil=hexrgb("#5a4733")),
    "cliff_stone": dict(
        ramp=ramp_stops([(0.00, "#2b2730"), (0.16, "#463f47"), (0.32, "#635855"), (0.47, "#80705f"),
                         (0.62, "#9d8a71"), (0.76, "#b9a586"), (0.89, "#d2c2a2"), (1.00, "#e8dbbf")]),
        ochre=np.array([1.10, 0.99, 0.82]), blue=np.array([0.90, 0.96, 1.10]), cav=hexrgb("#3a3346"),
        hilite=hexrgb("#ecdfc4"), soil=hexrgb("#584430")),
    "river_stone": dict(
        ramp=ramp_stops([(0.00, "#282a31"), (0.18, "#41454f"), (0.36, "#5d616a"), (0.52, "#7a7b80"),
                         (0.67, "#989690"), (0.81, "#b6b1a5"), (0.92, "#cfc8b9"), (1.00, "#e2dccd")]),
        ochre=np.array([1.07, 1.0, 0.88]), blue=np.array([0.92, 0.98, 1.08]), cav=hexrgb("#353648"),
        hilite=hexrgb("#e9e4d6"), soil=hexrgb("#55473a")),
}
MOSS = ramp_stops([(0.00, "#24301a"), (0.25, "#3a4d21"), (0.48, "#57722a"), (0.68, "#7f9a36"),
                   (0.85, "#a6ba52"), (1.00, "#c9cd74")])
GRASS = ramp_stops([(0.00, "#2c3d17"), (0.3, "#46621f"), (0.55, "#66872a"), (0.78, "#8fae3f"), (1.0, "#b9cf62")])
LICHEN_PALE, LICHEN_ORANGE = hexrgb("#cdc79a"), hexrgb("#c47d3d")
ALGAE = hexrgb("#4f6b3a")


def ramp(v, stops):
    pos, col = stops
    v = np.clip(v, 0.0, 1.0)
    return np.stack([np.interp(v, pos, col[:, c]) for c in range(3)], axis=1)


def lerp(a, b, t):
    t = np.asarray(t)
    if t.ndim == 1:
        t = t[:, None]
    return a + (b - a) * t


def ss(e0, e1, x):
    return NZ.smoothstep(e0, e1, x)


# --------------------------------------------------------------------------------------------- coverage

def rasterize(uv_tris, owner, size):
    """Exact owner map (0 = empty) from UV triangles (Blender UV, v up). Pixel centres; top row first."""
    W = H = size
    out = np.zeros((H, W), dtype=np.int16)
    px = uv_tris[..., 0] * W - 0.5
    py = (1.0 - uv_tris[..., 1]) * H - 0.5
    for t in range(len(uv_tris)):
        x0, x1 = int(math.floor(px[t].min())), int(math.ceil(px[t].max()))
        y0, y1 = int(math.floor(py[t].min())), int(math.ceil(py[t].max()))
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        ax, ay = px[t, 0], py[t, 0]
        bx, by = px[t, 1], py[t, 1]
        cx, cy = px[t, 2], py[t, 2]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / d
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / d
        l3 = 1 - l1 - l2
        e = -0.02
        inside = (l1 >= e) & (l2 >= e) & (l3 >= e)
        out[ys[inside], xs[inside]] = owner[t]
    return out


def grow_owner(owner, px=2):
    """Grow islands by px pixels (nearest owner) so bilinear/mip sampling at island edges stays on the asset."""
    empty = owner == 0
    if not empty.any():
        return owner
    dist, (iy, ix) = ndimage.distance_transform_edt(empty, return_indices=True)
    grown = owner[iy, ix]
    return np.where(dist <= px, grown, owner)


def dilate_fill(img, mask):
    """Fill pixels outside mask with the nearest masked pixel (texture padding for mips)."""
    if mask.all():
        return img
    _, (iy, ix) = ndimage.distance_transform_edt(~mask, return_indices=True)
    return img[iy, ix]


def upsample(a, size):
    if a.shape[0] == size:
        return a.astype(np.float32)
    f = size / a.shape[0]
    if a.ndim == 2:
        return ndimage.zoom(a.astype(np.float32), f, order=1)
    return np.stack([ndimage.zoom(a[..., c].astype(np.float32), f, order=1) for c in range(a.shape[2])], axis=-1)


# --------------------------------------------------------------------------------------------- rock painter

def paint_rock(P, N, AO, Kf, Kb, asset, pal):
    """Per-texel arrays for one asset -> (albedo rgb, roughness, moss mask, wet mask)."""
    s = int(asset["seed"]) % 2147483647
    prm = asset.get("paint", {})
    size = asset["info"]["size_m"]
    h = float(size[2])
    z = P[:, 2]
    z01 = np.clip(z / max(h, 1e-3), 0, 1.2)
    up = N[:, 2]
    Lk = np.array([-0.45, -0.55, 0.70])
    Lk /= np.linalg.norm(Lk)
    lam = np.clip(N @ Lk, -1, 1)
    n_macro = NZ.fbm3(P / 0.85, s + 1, 3)
    n_macro2 = NZ.fbm3(P / 1.6 + 3.3, s + 2, 2)
    n_mid = NZ.fbm3(P / 0.22, s + 3, 3)
    n_fine = NZ.fbm3(P / 0.055, s + 4, 2)
    ang = (s % 360) * math.pi / 180.0
    stretch = np.array([[math.cos(ang), math.sin(ang), 0.0], [-math.sin(ang), math.cos(ang), 0.0], [0, 0, 1.0]])
    Q = P @ stretch.T * np.array([0.28, 1.0, 1.0])
    stroke = NZ.fbm3(Q / 0.10, s + 5, 2)
    cav_ao = np.clip((0.92 - AO) / 0.62, 0, 1) ** 1.15
    cav_b = np.clip((0.5 - Kb) / 0.16, 0, 1)
    cav_f = np.clip((0.47 - Kf) / 0.11, 0, 1)
    cav = np.clip(cav_ao * 0.85 + cav_b * 0.45 + cav_f * 0.55, 0, 1)
    edge = np.clip((Kf - 0.55) / 0.10, 0, 1) * (0.55 + 0.45 * ss(-0.4, 0.8, up))
    edge_b = np.clip((Kb - 0.56) / 0.14, 0, 1)
    # 1 + 2 + 3 + 4: paint value
    V = 0.50 + 0.075 * n_macro + 0.035 * n_mid + 0.022 * n_fine + 0.022 * stroke
    V += 0.21 * ss(-0.15, 0.95, up) - 0.075
    V += 0.06 * lam
    V += 0.05 * (np.clip(z01, 0, 1) - 0.5)
    V -= 0.31 * cav
    V += 0.15 * edge + 0.06 * edge_b
    col = ramp(V, pal["ramp"])
    # 5: hue / value variation
    ochre = ss(0.12, 0.6, n_macro2)
    blue = ss(0.12, 0.6, -n_macro2)
    col = lerp(col, col * pal["ochre"], 0.85 * ochre)
    col = lerp(col, col * pal["blue"], 0.75 * blue)
    col = lerp(col, np.broadcast_to(pal["cav"], col.shape), 0.30 * cav)
    col = lerp(col, np.broadcast_to(pal["hilite"], col.shape), 0.22 * edge)
    rough = 0.84 + 0.05 * n_mid - 0.12 * edge
    # 6: story marks
    if prm.get("strata") or asset["recipe"] == "rock.cliff/1":
        sp = float(asset["params_resolved"].get("strata_spacing", 0.55))
        zz = z + 0.18 * sp * NZ.fbm3(P / 1.4, s + 31, 2)
        band = np.floor(zz / sp).astype(np.int64)
        bh = NZ.hash01(band, s + 12)
        tints = np.stack([hexrgb("#c9a57a") / hexrgb("#b0a08a"), hexrgb("#a7a4a3") / hexrgb("#b0a08a"),
                          hexrgb("#b99a8d") / hexrgb("#b0a08a"), hexrgb("#b6a98c") / hexrgb("#b0a08a")])
        tint = tints[np.minimum((bh * 4).astype(int), 3)]
        col = lerp(col, col * tint, 0.55)
        frac = np.mod(zz / sp, 1.0)
        ledge_top = ss(0.80, 0.97, frac) * ss(0.2, 0.7, up + 0.4)
        ledge_bot = 1 - ss(0.0, 0.10, frac)
        col *= (1 + 0.10 * ledge_top - 0.16 * ledge_bot * (1 - np.clip(up, 0, 1)))[:, None]
    # ground-contact soil
    gd = 1 - ss(0.0, 0.16 + 0.05 * n_mid, z)
    col = lerp(col, np.broadcast_to(pal["soil"], col.shape), 0.45 * gd)
    rough = rough + 0.05 * gd
    # water streaks on steep faces
    streak = ss(0.35, 0.75, NZ.fbm3(P * np.array([3.2, 3.2, 0.45]) / 0.5, s + 6, 3)) * (1 - np.clip(up, -1, 1) ** 2) \
        * ss(0.1, 0.5, z01)
    col *= (1 - 0.11 * streak)[:, None]
    # lichen dots
    lich = float(prm.get("lichen", 0.3))
    if lich > 0:
        f1, _, cid = NZ.worley3(P / 0.07, s + 7, 0.9)
        dots = 1 - ss(0.12, 0.42, f1)
        pick = NZ.hash01(cid.astype(np.int64), s + 13) < lich * 0.33
        lm = dots * pick * ss(-0.3, 0.3, up) * (1 - cav) * ss(0.12, 0.3, z)
        orange = NZ.hash01(cid.astype(np.int64), s + 14) < 0.18
        lc = np.where(orange[:, None], LICHEN_ORANGE, LICHEN_PALE)
        col = lerp(col, lc, 0.72 * lm)
        rough = rough + 0.06 * lm
    # moss on up-facing areas
    moss_amt = float(prm.get("moss", 0.0))
    m = np.zeros(len(P))
    if moss_amt > 0:
        field = up * 1.0 + 0.42 * NZ.fbm3(P / 0.33, s + 8, 3) + 0.18 * NZ.fbm3(P / 0.10, s + 9, 2) \
            + 0.25 * np.clip((0.5 - Kb) / 0.2, 0, 1) * (up > 0.2)
        field += 0.12 * ss(0.4, 1.0, z01)
        th = 1.08 - 0.95 * moss_amt
        m = ss(th - 0.06, th + 0.06, field) * ss(0.06, 0.2, z)
        rim = ss(th - 0.22, th - 0.04, field) * (1 - m)
        col = lerp(col, col * np.array([0.80, 0.86, 0.70]), 0.6 * rim)
        mv = 0.5 + 0.22 * up + 0.2 * NZ.fbm3(P / 0.035, s + 10, 2) - 0.28 * cav + 0.12 * edge
        mcol = ramp(mv, MOSS)
        f1s, _, cids = NZ.worley3(P / 0.025, s + 11, 0.9)
        speck = (1 - ss(0.1, 0.35, f1s)) * ss(th - 0.4, th - 0.12, field) * (NZ.hash01(cids.astype(np.int64), s + 15) < 0.5)
        col = lerp(col, ramp(mv * 0.9, MOSS), 0.8 * speck * (1 - m))
        col = lerp(col, mcol, m)
        rough = lerp(rough[:, None], np.full((len(P), 1), 0.95), m)[:, 0]
    # grass tops on cliffs
    if prm.get("grass_top"):
        g = ss(0.60, 0.80, up + 0.15 * NZ.fbm3(P / 0.5, s + 16, 2)) * ss(0.82, 0.92, z01 + 0.04 * n_mid)
        gv = 0.5 + 0.25 * NZ.fbm3(P * np.array([1.0, 1.0, 0.3]) / 0.03, s + 17, 2) + 0.15 * up - 0.3 * cav
        col = lerp(col, ramp(gv, GRASS), g)
        rough = lerp(rough[:, None], np.full((len(P), 1), 0.95), g)[:, 0]
        m = np.maximum(m, g)
    # wet line and algae (stream stones)
    wet = np.zeros(len(P))
    if prm.get("wet"):
        wl = float(prm.get("water_level_m", 0.0))
        dz = z - wl - 0.012 * NZ.fbm3(P / 0.08, s + 18, 2)
        under = 1 - ss(-0.015, 0.02, dz)
        damp = (1 - ss(0.0, 0.10 + 0.03 * n_mid, dz)) * (1 - under)
        col *= (1 - 0.38 * under - 0.2 * damp)[:, None]
        algae = under * ss(0.03, 0.30, wl - z) * (0.5 + 0.5 * ss(-0.2, 0.4, NZ.fbm3(P / 0.2, s + 19, 2)))
        col = lerp(col, np.broadcast_to(ALGAE, col.shape), 0.38 * algae)
        rough = lerp(rough[:, None], np.full((len(P), 1), 0.32), under)[:, 0]
        rough = lerp(rough[:, None], np.full((len(P), 1), 0.52), damp)[:, 0]
        wet = np.maximum(under, damp)
    col = np.clip(col, 0.035, 0.93)
    return col, np.clip(rough, 0.05, 1.0), m, wet


# --------------------------------------------------------------------------------------------- atlas

def paint_atlas(kit, atlas_id, cache):
    t0 = time.time()
    kdir = cache / kit
    kj = json.loads((kdir / "kit.json").read_text(encoding="utf-8"))
    at = kj["atlases"][atlas_id]
    maps = np.load(kdir / at["maps"])
    A = int(at["albedo_px"])
    D = int(at["data_px"])
    members = [kj["assets"][i] for i in at["members"]]
    owner_d = rasterize(maps["uv_tris"], maps["uv_owner"], D)
    owner_a = rasterize(maps["uv_tris"], maps["uv_owner"], A) if A != D else owner_d
    owner_a = grow_owner(owner_a, 2)
    owner_d = grow_owner(owner_d, 2)
    P = upsample(maps["pos"], A).reshape(-1, 3).astype(np.float64)
    N = upsample(maps["nrm_os"], A).reshape(-1, 3).astype(np.float64)
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    AO = upsample(maps["ao"], A).reshape(-1).astype(np.float64)
    aux = upsample(maps["aux"], A).reshape(-1, 3).astype(np.float64)
    pal = PALETTES[at["palette"]]
    albedo = np.zeros((A * A, 3))
    rough = np.full(A * A, 0.85)
    ow = owner_a.reshape(-1)
    for i, asset in enumerate(members, start=1):
        sel = np.nonzero(ow == i)[0]
        if not len(sel):
            continue
        c, r, _m, _w = paint_rock(P[sel], N[sel], AO[sel], aux[sel, 1], aux[sel, 2], asset, pal)
        albedo[sel] = c
        rough[sel] = r
    mask_a = owner_a > 0
    albedo = dilate_fill(albedo.reshape(A, A, 3), mask_a)
    rough = dilate_fill(rough.reshape(A, A), mask_a)
    # data-size maps: normal + ORM
    nts = maps["nrm_ts"].astype(np.float32)
    mask_d = owner_d > 0
    nts = dilate_fill(nts, mask_d)
    ao_d = dilate_fill(maps["ao"].astype(np.float32), mask_d)
    if A != D:
        rough_d = ndimage.zoom(rough, D / A, order=1)
    else:
        rough_d = rough
    orm = np.stack([0.40 + 0.60 * np.clip(ao_d, 0, 1) ** 0.85, rough_d, np.zeros_like(rough_d)], -1)
    tex = kdir / "tex"
    tex.mkdir(parents=True, exist_ok=True)
    out = {}
    out["albedo"] = tex / f"{atlas_id}_albedo.png"
    Image.fromarray(np.round(np.clip(albedo, 0, 1) * 255).astype(np.uint8), "RGB").save(out["albedo"], optimize=True)
    out["normal"] = tex / f"{atlas_id}_normal.png"
    n8 = np.round(np.clip(nts, 0, 1) * 255).astype(np.uint8)
    Image.fromarray(n8, "RGB").save(out["normal"], optimize=True)
    out["orm"] = tex / f"{atlas_id}_orm.png"
    Image.fromarray(np.round(np.clip(orm, 0, 1) * 255).astype(np.uint8), "RGB").save(out["orm"], optimize=True)
    cov = float(mask_a.mean())
    stats = {"atlas": atlas_id, "albedo_px": A, "data_px": D, "coverage": round(cov, 4),
             "albedo_min": [round(float(x), 3) for x in albedo[mask_a].min(0)],
             "albedo_max": [round(float(x), 3) for x in albedo[mask_a].max(0)],
             "albedo_mean": [round(float(x), 3) for x in albedo[mask_a].mean(0)],
             "seconds": round(time.time() - t0, 1), "files": {k: str(v) for k, v in out.items()}}
    (tex / f"{atlas_id}_paint.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(f"[paint] {atlas_id} {A}px coverage {cov:.2%} {stats['seconds']}s", flush=True)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--atlas", default="")
    ap.add_argument("--cache", default=str(CACHE))
    a = ap.parse_args()
    cache = Path(a.cache)
    kj = json.loads((cache / a.kit / "kit.json").read_text(encoding="utf-8"))
    want = [x for x in a.atlas.split(",") if x] or list(kj["atlases"].keys())
    for at in want:
        paint_atlas(a.kit, at, cache)


if __name__ == "__main__":
    main()
