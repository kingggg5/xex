"""Paint the shared leaf-cluster atlas from the Blender forge data passes (Route A step 2, trees v4).

System Python: numpy + scipy + OpenCV (16-bit PNG read) + Pillow (pre-installed; nothing installed).
Input: forge_leaf_atlas.py passes (normal/aox/part at 2048 px, linear) + layout.json.
Output (1024 x 1024, RGBA, sRGB colour + straight alpha):
  <out>/qn_leaf_atlas_albedo.png
  <out>/atlas_report.json         palette stops, per-cell leaf counts, coverage per mip (box filter), bleed check
  <preview>/atlas_preview_*.png   BLENDER REVIEW previews (over grey / checker, 2x cell zooms)

Painted layers (llm.txt albedo layering): base ramp per part class -> large top-light gradient (cluster +V is up;
the stylize script rotates each card's UVs so +V points up in the world) -> painted cavity (AO pass + crisp
occlusion lines where a higher leaf overlaps) -> crisp light edges on light-facing leaf edges -> per-leaf hue and
value variation. Alpha is a signed-distance ramp crossing the 0.45 cutoff exactly at the leaf silhouette, so
box-filtered mips keep the alpha-tested coverage; RGB is bled into every transparent texel (nearest opaque colour).

Usage:
  python paint_leaf_atlas.py --passes <dir> --out <dir> --preview <dir> [--gain 1.0]
"""
import argparse
import colorsys
import json
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

CUTOFF = 0.45
SDF_RAMP_PX = 6.0          # 1024-px units: alpha goes 0 -> 1 over 6 px, crossing 0.45 at the silhouette
FONT = r"C:\Windows\Fonts\segoeui.ttf"

PALETTES = {   # tone 0..1 -> sRGB (albedo, never pure black / white)
    "broadleaf": [(0.00, "#1D3012"), (0.25, "#33501B"), (0.50, "#5E7A26"), (0.72, "#94A436"), (0.90, "#C4C24A"),
                  (1.00, "#DCD85A")],
    "bush": [(0.00, "#10220F"), (0.35, "#1F3D1C"), (0.60, "#36602C"), (0.85, "#6A8C3A"), (1.00, "#9AB04A")],
    "conifer": [(0.00, "#14261A"), (0.30, "#23402B"), (0.55, "#3F5E33"), (0.80, "#7E9446"), (1.00, "#B4B859")],
    "twig": [(0.00, "#33241A"), (0.50, "#5E412C"), (1.00, "#8E6A48")],
    "petal": [(0.00, "#7C1612"), (0.45, "#C02A20"), (0.80, "#E8553C"), (1.00, "#F2865C")],
    "centre": [(0.00, "#9A5A10"), (0.55, "#E8A820"), (1.00, "#F6D45A")],
    "berry": [(0.00, "#5E0C0C"), (0.55, "#A81A16"), (0.85, "#D8362A"), (1.00, "#F0B4A0")],
}
RIM = {"broadleaf": "#E2DC78", "bush": "#A8BC58", "conifer": "#C8C86A"}


def hex2rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float64) / 255.0


def ramp(t, stops):
    t = np.clip(t, 0.0, 1.0)
    xs = np.array([s[0] for s in stops])
    cs = np.array([hex2rgb(s[1]) for s in stops])
    out = np.empty(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, xs, cs[:, c])
    return out


def read16(path):
    a = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)   # unicode-safe path
    if a is None or a.dtype != np.uint16:
        raise SystemExit(f"expected a 16-bit RGBA PNG: {path}")
    return a[..., [2, 1, 0, 3]].astype(np.float64) / 65535.0


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def hue_shift(rgb, dh, ds):
    """Per-pixel HSV shift (vectorised through OpenCV, float32)."""
    hsv = cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2HSV)      # H in degrees 0..360
    hsv[..., 0] = (hsv[..., 0] + dh * 360.0) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + ds), 0, 1)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).astype(np.float64)


def edge_toward(ids, direction, width, cover):
    """Pixels of each part within `width` px of its boundary on the side `direction` (dy, dx) points to,
    where the neighbour is another part or background. Returns falloff 1 (at edge) -> 0 and the neighbour id."""
    h, w = ids.shape
    out = np.zeros((h, w))
    dy, dx = direction
    for k in range(1, width + 1):
        sh = np.full_like(ids, -1)
        ys0, ys1 = max(0, -dy * k), h - max(0, dy * k)
        xs0, xs1 = max(0, -dx * k), w - max(0, dx * k)
        sh[ys0:ys1, xs0:xs1] = ids[ys0 + dy * k:ys1 + dy * k, xs0 + dx * k:xs1 + dx * k]
        hit = cover & (sh != ids) & (out == 0)
        out[hit] = 1.0 - (k - 1) / width
    return out


def cast_shadow(zl, ids, cover, to_light, steps, eps):
    """Painted drop shadow: a pixel is shaded when a higher part lies toward the light within `steps` px."""
    out = np.zeros(zl.shape)
    dy, dx = to_light
    for k in range(1, steps + 1):
        oy, ox = int(round(k * dy)), int(round(k * dx))
        zq = np.roll(np.roll(zl, -oy, 0), -ox, 1)
        iq = np.roll(np.roll(ids, -oy, 0), -ox, 1)
        hit = cover & (iq >= 0) & (iq != ids) & (zq > zl + eps)
        out = np.maximum(out, hit * (1.0 - (k - 1) / steps))
    return ndimage.gaussian_filter(out, 1.5) * cover


TONE = {"leaf_contrast": 1.45, "leaf_var": 0.16, "leaflet_contrast": 1.35, "leaflet_var": 0.12}


def soft_clip(x, knee=0.6, top=0.86):
    return np.where(x <= knee, x, knee + (top - knee) * (1 - np.exp(-(x - knee) / (top - knee))))


def apply_calibration(calib):
    """Render-calibrated palettes (BLENDER REVIEW pass metrics vs target swatches): each stop is scaled in linear
    light by a gain that runs from gain_lo (tone 0) to gain_hi (tone 1), red and blue are scaled by r / b
    (warm-cool shift), then soft-clipped below 0.86 linear so highlights keep their hue."""
    for key, c in calib.items():
        if key in TONE:
            TONE[key] = float(c)
            continue
        if key not in PALETTES:
            continue
        stops = []
        for t, hx in PALETTES[key]:
            lin = srgb_to_lin(hex2rgb(hx))
            g = c.get("gain_lo", 1.0) + (c.get("gain_hi", 1.0) - c.get("gain_lo", 1.0)) * t
            r_ = c.get("r_lo", c.get("r", 1.0)) + (c.get("r_hi", c.get("r", 1.0)) - c.get("r_lo", c.get("r", 1.0))) * t
            b_ = c.get("b_lo", c.get("b", 1.0)) + (c.get("b_hi", c.get("b", 1.0)) - c.get("b_lo", c.get("b", 1.0))) * t
            lin = lin * g * np.array([r_, 1.0, b_])
            out = lin_to_srgb(soft_clip(lin))
            stops.append((t, "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in np.clip(out, 0, 1))))
        PALETTES[key] = stops
        if key in RIM:
            lin = srgb_to_lin(hex2rgb(RIM[key])) * c.get("gain_hi", 1.0) * np.array(
                [c.get("r_hi", c.get("r", 1.0)), 1.0, c.get("b_hi", c.get("b", 1.0))])
            RIM[key] = "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in np.clip(lin_to_srgb(soft_clip(lin)), 0, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", required=True)
    ap.add_argument("--gain", type=float, default=1.0, help="global albedo value gain (linear) for calibration")
    ap.add_argument("--name", default="qn_leaf_atlas")
    ap.add_argument("--calib", default="", help="JSON: per palette {gain_lo, gain_hi, r, b} (linear, tone 0 -> 1) "
                                                "+ optional leaf_contrast / leaf_var / leaflet_contrast")
    args = ap.parse_args()
    calib = json.load(open(args.calib, encoding="utf-8")) if args.calib else {}
    apply_calibration(calib)
    layout = json.load(open(os.path.join(args.passes, "layout.json"), encoding="utf-8"))
    nrm = read16(os.path.join(args.passes, "normal.png"))
    aox = read16(os.path.join(args.passes, "aox.png"))
    prt = read16(os.path.join(args.passes, "part.png"))
    H, W = nrm.shape[:2]
    cover = nrm[..., 3] > 0.5
    N = nrm[..., :3] * 2.0 - 1.0
    N /= np.maximum(np.linalg.norm(N, axis=2, keepdims=True), 1e-6)
    AO, ZL, RND = aox[..., 0], aox[..., 1], aox[..., 2]
    CLS, LT, LS = prt[..., 0], prt[..., 1], prt[..., 2] * 2 - 1
    cls_id = np.rint(CLS * 10).astype(int)          # 1 twig, 3 leaf, 5 leaflet, 7 petal, 8 centre, 9 berry
    ids = np.where(cover, np.rint(RND * 65535).astype(np.int64) * 16 + cls_id, -1)
    rng_hash = (np.sin(RND * 12.9898 * 43758.5453) * 0.5 + 0.5) % 1.0     # second per-part random
    yy, xx = np.mgrid[0:H, 0:W]
    v_img = 1.0 - (yy + 0.5) / H          # UV v (up)
    u_img = (xx + 0.5) / W
    albedo = np.zeros((H, W, 3))
    report_cells = {}
    L_broad = np.array([-0.35, 0.80, 0.50])
    L_broad /= np.linalg.norm(L_broad)
    L_con = np.array([-0.25, 0.35, 0.90])
    L_con /= np.linalg.norm(L_con)
    rim_dirs = [(-1, 0), (-1, -1), (0, -1)]       # image (dy, dx): up, up-left, left -> faces the painted light
    occl_dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for name, cell in layout["cells"].items():
        u0, v0, u1, v1 = cell["uv_rect"]
        sel_cell = (u_img >= u0) & (u_img <= u1) & (v_img >= v0) & (v_img <= v1)
        m = sel_cell & cover
        if not m.any():
            continue
        kind = cell["kind"]
        ys, xs = np.nonzero(m)
        y0, y1 = ys.min(), ys.max()
        vy = np.zeros((H, W))
        vy[m] = 1.0 - (yy[m] - y0) / max(1, (y1 - y0))          # 0 bottom of the cluster -> 1 top
        zl = np.zeros((H, W))
        zmin, zmax = ZL[m].min(), ZL[m].max()
        zl[m] = (ZL[m] - zmin) / max(1e-6, zmax - zmin)
        # sub-window for the edge operations
        sl = (slice(max(0, y0 - 8), min(H, y1 + 9)), slice(max(0, xs.min() - 8), min(W, xs.max() + 9)))
        idw, cw = ids[sl], cover[sl] & sel_cell[sl]
        zw = ZL[sl]
        rim = np.zeros(idw.shape)
        h_, w_ = idw.shape
        for d in rim_dirs:                     # light edges: neighbour toward the light is background or a lower part
            dy, dx = d
            for k in range(1, 6):
                shid = np.roll(np.roll(idw, -dy * k, 0), -dx * k, 1)
                shz = np.roll(np.roll(zw, -dy * k, 0), -dx * k, 1)
                hit = cw & (shid != idw) & ((shid < 0) | (shz < zw - 0.02)) & (rim == 0)
                rim[hit] = 1.0 - (k - 1) / 5.0
        to_light = np.array([-0.80, -0.35])
        to_light /= np.linalg.norm(to_light)
        occ = cast_shadow(zw, idw, cw, to_light, 16, 0.02)
        rim_full = np.zeros((H, W))
        occ_full = np.zeros((H, W))
        rim_full[sl] = rim
        occ_full[sl] = occ
        rim_full = rim_full * (1.0 - np.clip(occ_full * 2, 0, 1))
        for cid, cls_name in ((1, "twig"), (3, "leaf"), (5, "leaflet"), (7, "petal"), (8, "centre"), (9, "berry")):
            mm = m & (cls_id == cid)
            if not mm.any():
                continue
            n = N[mm]
            ao = AO[mm]
            if cls_name in ("leaf",):
                pal = "bush" if kind in ("bush", "blossom") else "broadleaf"
                lam = np.clip((n @ L_broad + 0.35) / 1.35, 0, 1)
                t = 0.30 * lam + 0.36 * vy[mm] + 0.12 * zl[mm] + 0.14 * LT[mm] + 0.04
                t *= 0.45 + 0.55 * np.clip(ao, 0, 1) ** 1.5
                t += (RND[mm] - 0.5) * TONE["leaf_var"]
                t *= 1.0 - 0.42 * occ_full[mm]
                t = 0.5 + (t - 0.46) * TONE["leaf_contrast"]             # value contrast: dark cavities, bright tops
                t = t + 0.3 * (np.round(t * 5) / 5 - t)                 # light posterisation: painted value steps
                vein = (np.abs(LS[mm]) < 0.07) & (LT[mm] > 0.1) & (LT[mm] < 0.75)
                t[vein] += 0.04
                col = ramp(t, PALETTES[pal])
                rimc = hex2rgb(RIM[pal])
                r = rim_full[mm][:, None] * np.clip(lam[:, None] * 1.2, 0, 1) * 0.6
                col = col * (1 - r) + rimc * r
                dh = (rng_hash[mm] - 0.5) * 0.05
                ds = (RND[mm] - 0.5) * 0.12
                col = hue_shift(col[None], dh[None], ds[None])[0]
            elif cls_name == "leaflet":
                lam = np.clip((n @ L_con + 0.3) / 1.3, 0, 1)
                vf = np.clip((v_img[mm] - v0) / (v1 - v0), 0, 1)             # frond stem (0) -> tip (1)
                t = 0.26 * lam + 0.22 * vf + 0.36 * LT[mm] ** 1.6 + 0.08 * zl[mm] - 0.02
                t *= 0.42 + 0.58 * np.clip(ao, 0, 1) ** 1.4
                t += (RND[mm] - 0.5) * TONE["leaflet_var"]
                t *= 1.0 - 0.4 * occ_full[mm]
                t = 0.5 + (t - 0.42) * TONE["leaflet_contrast"]
                t = t + 0.25 * (np.round(t * 5) / 5 - t)
                col = ramp(t, PALETTES["conifer"])
                tips = np.clip((LT[mm] - 0.6) / 0.4, 0, 1)
                r = (0.5 * tips * rim_full[mm] + 0.3 * tips ** 2)[:, None]
                r = np.clip(r, 0, 0.75)
                col = col * (1 - r) + hex2rgb(RIM["conifer"]) * r
                dh = (rng_hash[mm] - 0.5) * 0.035
                col = hue_shift(col[None], dh[None], np.zeros_like(dh)[None])[0]
            elif cls_name == "twig":
                lam = np.clip((n @ L_broad + 0.4) / 1.4, 0, 1)
                t = (0.55 * lam + 0.25) * (0.6 + 0.4 * np.clip(ao, 0, 1))
                col = ramp(t, PALETTES["twig"])
            elif cls_name == "petal":
                lam = np.clip((n @ L_broad + 0.4) / 1.4, 0, 1)
                t = (0.5 * lam + 0.3 * LT[mm] + 0.2) * (0.6 + 0.4 * np.clip(ao, 0, 1))
                t *= 1.0 - 0.3 * occ_full[mm]
                col = ramp(t, PALETTES["petal"])
                r = rim_full[mm][:, None] * 0.4
                col = col * (1 - r) + hex2rgb("#F6A07A") * r
            elif cls_name == "centre":
                lam = np.clip((n @ L_broad + 0.3) / 1.3, 0, 1)
                col = ramp(0.25 + 0.75 * lam * np.clip(ao, 0.3, 1), PALETTES["centre"])
            else:   # berry
                lam = np.clip(n @ L_broad, 0, 1)
                t = (0.2 + 0.7 * lam) * (0.55 + 0.45 * np.clip(ao, 0, 1))
                spec = np.clip((lam - 0.93) / 0.07, 0, 1) ** 2
                col = ramp(np.clip(t * 0.88 + 0.12 * spec * 8, 0, 1), PALETTES["berry"])
            albedo[mm] = col
        report_cells[name] = {"kind": kind, "parts": cell["parts"],
                              "leaves": cell["parts"].get("leaf", 0) + cell["parts"].get("leaflet", 0)}
    # global value gain (linear) for calibration against the target swatches, clamped away from black/white
    lin = srgb_to_lin(albedo) * args.gain
    albedo = lin_to_srgb(np.clip(lin, 0.0025, 0.86))
    # ---- signed-distance alpha at 2048, then 2x2 downsample to 1024 ----
    d_in = ndimage.distance_transform_edt(cover)
    d_out = ndimage.distance_transform_edt(~cover)
    sdf2048 = np.where(cover, d_in - 0.5, -(d_out - 0.5))
    alpha2048 = np.clip(CUTOFF + (sdf2048 / 2.0) / SDF_RAMP_PX, 0.0, 1.0)
    alpha = alpha2048.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3))
    cw = cover.reshape(H // 2, 2, W // 2, 2).astype(np.float64)
    wsum = cw.sum(axis=(1, 3))
    rgb = (albedo.reshape(H // 2, 2, W // 2, 2, 3) * cw[..., None]).sum(axis=(1, 3)) / np.maximum(wsum, 1e-9)[..., None]
    has = wsum > 0
    # bleed: every texel without coverage takes the colour of the nearest covered texel
    _, (iy, ix) = ndimage.distance_transform_edt(~has, return_indices=True)
    rgb = rgb[iy, ix]
    out_rgba = np.dstack([np.clip(rgb, 0, 1), alpha])
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.preview, exist_ok=True)
    out_path = os.path.join(args.out, f"{args.name}_albedo.png")
    Image.fromarray(np.rint(out_rgba * 255).astype(np.uint8), "RGBA").save(out_path, optimize=True)
    # ---- coverage per mip (box filter, as runtime mip generation does) ----
    a8 = np.rint(alpha * 255) / 255.0
    lvl = [a8]
    while lvl[-1].shape[0] > 1:
        p = lvl[-1]
        lvl.append(p.reshape(p.shape[0] // 2, 2, p.shape[1] // 2, 2).mean(axis=(1, 3)))
    mips = []
    for i, p in enumerate(lvl):
        row = {"level": i, "size": p.shape[0], "coverage_all": round(float((p >= CUTOFF).mean()), 4), "cells": {}}
        for name, cell in layout["cells"].items():
            u0, v0, u1, v1 = cell["uv_rect"]
            s = p.shape[0]
            x0, x1 = int(np.floor(u0 * s)), int(np.ceil(u1 * s))
            ya, yb = int(np.floor((1 - v1) * s)), int(np.ceil((1 - v0) * s))
            sub = p[ya:yb, x0:x1]
            row["cells"][name] = round(float((sub >= CUTOFF).mean()), 4) if sub.size else None
        mips.append(row)
    base = mips[0]
    for row in mips:
        row["ratio_to_mip0"] = {k: (round(v / base["cells"][k], 3) if v is not None and base["cells"][k] else None)
                                for k, v in row["cells"].items()}
    # bleed check: no transparent texel keeps a near-black colour
    tr = alpha < 0.02
    dark_transparent = float((rgb[tr].max(axis=1) < 0.03).mean()) if tr.any() else 0.0
    # palette of the painted albedo per kind (opaque texels; luminance p10/p50/p90)
    pal_report = {}
    for kind in ("broadleaf", "bush", "conifer", "blossom"):
        msk = np.zeros((H // 2, W // 2), bool)
        for name, cell in layout["cells"].items():
            if cell["kind"] != kind:
                continue
            u0, v0, u1, v1 = cell["uv_rect"]
            x0, x1 = int(u0 * 1024), int(u1 * 1024)
            ya, yb = int((1 - v1) * 1024), int((1 - v0) * 1024)
            msk[ya:yb, x0:x1] = True
        msk &= alpha >= CUTOFF
        px = rgb[msk]
        lum = px @ np.array([0.2126, 0.7152, 0.0722])
        o = np.argsort(lum)
        res = {}
        for nm, q in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9)):
            i0, i1 = int(len(o) * max(0, q - 0.04)), int(len(o) * min(1, q + 0.04))
            c = np.median(px[o[i0:max(i1, i0 + 1)]], axis=0)
            res[nm] = "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in c)
        pal_report[kind] = res
    report = {"label": "LEAF ATLAS (Claude forge: Blender geometry passes + numpy painting)",
              "file": os.path.basename(out_path), "size_px": [1024, 1024], "colour_space": "sRGB, straight alpha",
              "alpha": {"cutoff": CUTOFF, "encoding": f"signed distance ramp {SDF_RAMP_PX} px (1024 units), "
                                                       "crosses the cutoff at the silhouette"},
              "bleed": {"method": "nearest opaque texel colour into every transparent texel (scipy EDT indices)",
                        "share_transparent_texels_near_black": round(dark_transparent, 5)},
              "gain_linear": args.gain, "calibration": calib, "tone": TONE, "palettes_srgb": PALETTES, "rim_srgb": RIM,
              "painted_albedo_lum_p10_p50_p90": pal_report,
              "cells": report_cells, "layout": layout["cells"],
              "mip_coverage_box_filter": mips}
    with open(os.path.join(args.out, "atlas_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    # ---- previews ----
    img = Image.open(out_path).convert("RGBA")
    for bgname, bg in (("grey", Image.new("RGBA", img.size, (120, 124, 130, 255))),
                       ("checker", None)):
        if bg is None:
            c = ((np.indices((1024, 1024)) // 32).sum(0) % 2) * 60 + 150
            bg = Image.fromarray(np.dstack([c, c, c, np.full_like(c, 255)]).astype(np.uint8), "RGBA")
        comp = bg.copy()
        comp.alpha_composite(img)
        # alpha-tested look (what the runtime shows): hard cutoff
        if bgname == "grey":
            at = np.asarray(img).copy()
            at[..., 3] = np.where(at[..., 3] >= int(CUTOFF * 255), 255, 0)
            comp2 = bg.copy()
            comp2.alpha_composite(Image.fromarray(at, "RGBA"))
            d = ImageDraw.Draw(comp2)
            f = ImageFont.truetype(FONT, 16) if os.path.exists(FONT) else None
            for name, cell in layout["cells"].items():
                x, y = cell["px_rect_top_left"][:2]
                d.text((x + 4, y + 2), name, fill=(255, 255, 255), font=f)
            d.text((8, 1004), "BLENDER REVIEW  qn_leaf_atlas_albedo (alpha-tested at 0.45)", fill=(255, 220, 120), font=f)
            comp2.convert("RGB").save(os.path.join(args.preview, "atlas_preview_alphatest.png"))
        comp.convert("RGB").save(os.path.join(args.preview, f"atlas_preview_{bgname}.png"))
    # 2x zoom of three cells
    zoom = Image.new("RGB", (3 * 640 + 20, 640), (40, 40, 40))
    bg = Image.new("RGBA", (320, 320), (120, 124, 130, 255))
    for i, name in enumerate(("B1_rosette", "C1_frond", "BB_blossom")):
        x, y, s, _ = layout["cells"][name]["px_rect_top_left"]
        cell = img.crop((x, y, x + s, y + s))
        c2 = bg.copy()
        c2.alpha_composite(cell)
        zoom.paste(c2.convert("RGB").resize((640, 640), Image.NEAREST), (i * 650, 0))
    zoom.save(os.path.join(args.preview, "atlas_preview_zoom.png"))
    print("WROTE", out_path, json.dumps(pal_report))
    print("MIP coverage ratios", [(r["level"], r["size"], r["coverage_all"]) for r in mips[:8]])


if __name__ == "__main__":
    main()
