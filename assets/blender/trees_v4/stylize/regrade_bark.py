"""Regrade the kit's painted bark to the decision-doc bark palette (Route A step 2, trees v4).

System Python: numpy + Pillow (pre-installed; nothing installed). Reads the kit textures READ-ONLY and writes
new files; the kit folder is never written.

  albedo: luminance of Bark_NormalTree.png (painted vertical strokes) -> ramp through the doc palette
          (cavity #2E1F15, bark mid #6B4A32, highlight #9A7350, ridge #B38A62); the stroke detail is kept,
          the kit's warm/red cast (mean #8B5942) is replaced. 2048 -> 1024 px (Lanczos).
  normal: Bark_NormalTree_Normal.png (OpenGL +Y) 2048 -> 1024 px, decoded, renormalised, re-encoded.

Usage:
  python regrade_bark.py --kit <kit glTF dir> --out <dir> [--size 1024]
"""
import argparse
import hashlib
import json
import os

import numpy as np
from PIL import Image

STOPS = [(0.00, "#2E1F15"), (0.30, "#4E3524"), (0.55, "#6B4A32"), (0.82, "#9A7350"), (1.00, "#B38A62")]


def hex2rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float64) / 255.0


def s2l(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def l2s(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=1024)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    src_a = os.path.join(a.kit, "Bark_NormalTree.png")
    src_n = os.path.join(a.kit, "Bark_NormalTree_Normal.png")
    img = Image.open(src_a).convert("RGB")
    rgb = np.asarray(img, np.float64) / 255.0
    lum = s2l(rgb) @ np.array([0.2126, 0.7152, 0.0722])
    lo, hi = np.percentile(lum, 2), np.percentile(lum, 98)
    t = np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1) ** 1.25
    xs = np.array([s[0] for s in STOPS])
    cs = s2l(np.array([hex2rgb(s[1]) for s in STOPS]))
    out = np.stack([np.interp(t, xs, cs[:, c]) for c in range(3)], axis=-1)
    srgb = (l2s(out) * 255 + 0.5).astype(np.uint8)
    alb = Image.fromarray(srgb, "RGB").resize((a.size, a.size), Image.LANCZOS)
    p_alb = os.path.join(a.out, "qn_bark_albedo.png")
    alb.save(p_alb, optimize=True)
    nimg = np.asarray(Image.open(src_n).convert("RGB"), np.float64) / 255.0
    small = np.asarray(Image.fromarray((nimg * 255 + 0.5).astype(np.uint8), "RGB").resize(
        (a.size, a.size), Image.LANCZOS), np.float64) / 255.0
    v = small * 2 - 1
    v /= np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-6)
    p_nrm = os.path.join(a.out, "qn_bark_normal.png")
    Image.fromarray(((v * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8), "RGB").save(p_nrm, optimize=True)
    a_out = np.asarray(alb, np.float64) / 255.0
    report = {"label": "BARK REGRADE (system Python, kit textures read-only)",
              "inputs": {"albedo": src_a, "albedo_sha256": sha(src_a), "normal": src_n, "normal_sha256": sha(src_n),
                         "albedo_mean_srgb": "#%02X%02X%02X" % tuple(int(round(c * 255)) for c in rgb.reshape(-1, 3).mean(0))},
              "palette_stops_srgb": STOPS, "luminance_p2_p98_linear": [round(float(lo), 4), round(float(hi), 4)],
              "outputs": {"albedo": p_alb, "albedo_sha256": sha(p_alb), "normal": p_nrm, "normal_sha256": sha(p_nrm),
                          "size_px": a.size,
                          "albedo_mean_srgb": "#%02X%02X%02X" % tuple(int(round(c * 255)) for c in a_out.reshape(-1, 3).mean(0)),
                          "normal_convention": "OpenGL +Y (unchanged from the kit), renormalised after resize"}}
    with open(os.path.join(a.out, "bark_regrade.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print(json.dumps(report["outputs"]))


if __name__ == "__main__":
    main()
