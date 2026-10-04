"""Staff maps (system Python + numpy + Pillow). The staff keeps its Tripo UVs, so the maps are plain downsamples.

Inputs : source/owner/hero02_staff_p20_smartuv_pbr_source_4k.glb (4096 base colour JPEG, 4096 metal/rough PNG)
         work/tex/hero02_staff_ao_1024.png (AO baked in Blender by h02_staff.py --phase prep)
Outputs: work/tex/hero02_staff_albedo.png   1024 sRGB, x (1 - 0.30 (1 - AO)), kept inside sRGB 18..245
         work/tex/hero02_staff_orm.png      1024 linear: R AO, G roughness, B metallic
         work/tex/hero02_staff_emissive.png 512 sRGB: the blue crystal only (hue 200-245 deg, saturation > 0.45),
                                            0.85 x albedo, so bloom never clips the crystal to white
"""
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = ROOT / "assets/models/heroes/hero02/source/owner/hero02_staff_p20_smartuv_pbr_source_4k.glb"
TEX = ROOT / "assets/models/heroes/hero02/work/tex"
Image.MAX_IMAGE_PIXELS = None


def glb_images(path):
    b = path.read_bytes()
    off, js, bin_ = 12, None, None
    while off < len(b):
        ln, ty = struct.unpack_from("<II", b, off)
        ch = b[off + 8: off + 8 + ln]
        if ty == 0x4E4F534A:
            js = json.loads(ch)
        elif ty == 0x004E4942:
            bin_ = ch
        off += 8 + ln
    out = {}
    mat = js["materials"][0]
    roles = {"base": mat["pbrMetallicRoughness"]["baseColorTexture"]["index"],
             "rm": mat["pbrMetallicRoughness"]["metallicRoughnessTexture"]["index"],
             "normal": mat["normalTexture"]["index"]}
    for role, ti in roles.items():
        img = js["images"][js["textures"][ti]["source"]]
        bv = js["bufferViews"][img["bufferView"]]
        out[role] = Image.open(io.BytesIO(bin_[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]))
    return out


def s2l(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def l2s(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def rs(arr, size):
    return np.stack([np.asarray(Image.fromarray(arr[:, :, k].astype(np.float32), "F").resize((size, size), Image.LANCZOS))
                     for k in range(arr.shape[2])], 2)


imgs = glb_images(SRC)
base = np.asarray(imgs["base"].convert("RGB"), np.float64) / 255
rm = np.asarray(imgs["rm"].convert("RGB"), np.float64) / 255
ao = np.asarray(Image.open(TEX / "hero02_staff_ao_1024.png").convert("L"), np.float64) / 255
lin = np.clip(rs(s2l(base), 1024), 0, 1)
alb = l2s(lin * (1 - 0.30 * (1 - ao[:, :, None])))
alb = 18 / 255 + (245 - 18) / 255 * alb
Image.fromarray(np.round(alb * 255).astype(np.uint8), "RGB").save(TEX / "hero02_staff_albedo.png", optimize=True)
rm1 = np.clip(rs(rm, 1024), 0, 1)
orm = np.stack([ao, rm1[:, :, 1], rm1[:, :, 2]], 2)
Image.fromarray(np.round(orm * 255).astype(np.uint8), "RGB").save(TEX / "hero02_staff_orm.png", optimize=True)
# crystal mask from the base colour (HSV)
b512 = np.clip(rs(base, 512), 0, 1)
mx, mn = b512.max(2), b512.min(2)
sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
r, g, bb = b512[:, :, 0], b512[:, :, 1], b512[:, :, 2]
hue = (np.degrees(np.arctan2(np.sqrt(3) * (g - bb), 2 * r - g - bb)) + 360) % 360
mask = ((hue > 200) & (hue < 245) & (sat > 0.45) & (mx > 0.30)).astype(np.float64)
mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(__import__("PIL.ImageFilter", fromlist=["x"]).GaussianBlur(1.2)), np.float64) / 255
emi = b512 * 0.85 * mask[:, :, None]
Image.fromarray(np.round(np.clip(emi, 0, 1) * 255).astype(np.uint8), "RGB").save(TEX / "hero02_staff_emissive.png", optimize=True)
stats = {"albedo_mean": alb.reshape(-1, 3).mean(0).round(4).tolist(), "crystal_mask_fraction": round(float(mask.mean()), 4),
         "emissive_max": round(float(emi.max()), 4), "orm_mean": orm.reshape(-1, 3).mean(0).round(4).tolist()}
(TEX / "staff_textures.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
print(json.dumps(stats))
