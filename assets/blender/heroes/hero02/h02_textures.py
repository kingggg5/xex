"""Stage 1b (system Python 3.12 + numpy + Pillow, no Blender): final 2048 atlas maps for hero 02.

Inputs  work/bake/h02_albedo_4096.png  (Tripo 8K base colour transferred into UV_atlas at 4096)
        work/bake/h02_rm_2048.png      (Tripo metal/rough: G roughness, B metallic, transferred at 2048)
        work/bake/h02_ao_{front,back}_2048.png + h02_clothmask_2048.png (AO on the cleaned high mesh, 128 samples,
        0.30 m, for both sides; cloth texels take the brighter side because cloth is double-sided)
Outputs work/tex/hero02_witch_albedo.png  2048, sRGB: base x (1 - 0.35 (1 - AO)), linear-light downsample,
                                          values kept inside sRGB 18..245 (painted-texture rule)
        work/tex/hero02_witch_orm.png     1024, linear: R AO, G roughness, B metallic (glTF ORM)
The tangent-space normal maps are baked per LOD in Blender (h02_build_lods_rig.py), not here.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / "assets" / "models" / "heroes" / "hero02" / "work"
OUT = WORK / "tex"
OUT.mkdir(parents=True, exist_ok=True)
AO_IN_ALBEDO = 0.35


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def load(path, mode="RGB"):
    return np.asarray(Image.open(path).convert(mode), dtype=np.float64) / 255.0


def resize_linear(arr, size):
    """Resize a float image (H, W, C) with Lanczos per channel in float space."""
    chans = []
    for k in range(arr.shape[2]):
        im = Image.fromarray(arr[:, :, k].astype(np.float32), mode="F")
        chans.append(np.asarray(im.resize((size, size), Image.LANCZOS), dtype=np.float64))
    return np.stack(chans, 2)


albedo = load(WORK / "bake" / "h02_albedo_4096.png")
ao_front = load(WORK / "bake" / "h02_ao_front_2048.png", "L")
ao_back = load(WORK / "bake" / "h02_ao_back_2048.png", "L")
cloth_mask = load(WORK / "bake" / "h02_clothmask_2048.png", "L")
# double-sided cloth shows both sides with one texel: use its more open side; body texels use the front side
ao = np.where(cloth_mask > 0.5, np.maximum(ao_front, ao_back), ao_front)[:, :, None]
rm = load(WORK / "bake" / "h02_rm_2048.png")
ao4 = np.clip(resize_linear(ao, albedo.shape[0]), 0, 1)
lin = srgb_to_lin(albedo) * (1.0 - AO_IN_ALBEDO * (1.0 - ao4))
lin2 = np.clip(resize_linear(lin, 2048), 0, 1)
srgb = lin_to_srgb(lin2)
lo, hi = 18 / 255, 245 / 255
srgb = lo + (hi - lo) * srgb          # linear remap keeps the painted gradients, never pure black or white
Image.fromarray(np.round(srgb * 255).astype(np.uint8), "RGB").save(OUT / "hero02_witch_albedo.png", optimize=True)

ao1 = np.clip(resize_linear(ao, 1024), 0, 1)[:, :, 0]
rm1 = np.clip(resize_linear(rm, 1024), 0, 1)
orm = np.stack([ao1, rm1[:, :, 1], rm1[:, :, 2]], 2)
Image.fromarray(np.round(orm * 255).astype(np.uint8), "RGB").save(OUT / "hero02_witch_orm.png", optimize=True)

stats = {
    "albedo": {"file": "work/tex/hero02_witch_albedo.png", "size": 2048, "ao_multiply": AO_IN_ALBEDO,
               "srgb_range": [18, 245], "mean_srgb": [round(float(v), 4) for v in srgb.reshape(-1, 3).mean(0)]},
    "orm": {"file": "work/tex/hero02_witch_orm.png", "size": 1024,
            "mean": [round(float(v), 4) for v in orm.reshape(-1, 3).mean(0)],
            "metallic_fraction_over_0p5": round(float((orm[:, :, 2] > 0.5).mean()), 4)},
    "ao_mean": round(float(ao.mean()), 4),
}
(OUT / "textures.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
print(json.dumps(stats))
