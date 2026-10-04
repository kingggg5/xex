"""Shared image helpers for tools/capture (numpy + PIL only; scipy where noted)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

FONT_CANDIDATES = ("C:/Windows/Fonts/LeelawUI.ttf", "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


@lru_cache(maxsize=16)
def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A Thai-capable TrueType font when available (Leelawadee UI / Tahoma on Windows)."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def load_rgb(path: str | Path) -> np.ndarray:
    """uint8 HxWx3; alpha is composited over black (the game canvas is opaque in practice)."""
    with Image.open(path) as image:
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
            return np.asarray(Image.alpha_composite(background, rgba).convert("RGB"))
        return np.asarray(image.convert("RGB"))


def load_alpha(path: str | Path) -> np.ndarray | None:
    with Image.open(path) as image:
        if "A" in image.getbands():
            return np.asarray(image.getchannel("A"))
    return None


def luma(rgb: np.ndarray) -> np.ndarray:
    """Rec. 709 luma Y' of gamma-encoded sRGB, float 0..1 (perceived brightness, not linear luminance)."""
    value = rgb.astype(np.float32) / 255.0
    return value[..., 0] * 0.2126 + value[..., 1] * 0.7152 + value[..., 2] * 0.0722


def resize_max(image: Image.Image, max_side: int) -> Image.Image:
    scale = min(1.0, max_side / max(image.size))
    if scale >= 1.0:
        return image.copy()
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)


def save_jpeg(rgb: np.ndarray | Image.Image, path: Path, max_side: int = 1280, quality: int = 86) -> Path:
    image = rgb if isinstance(rgb, Image.Image) else Image.fromarray(rgb)
    path.parent.mkdir(parents=True, exist_ok=True)
    resize_max(image.convert("RGB"), max_side).save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    return path


# ---------- colour science ----------
def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """uint8 (...,3) sRGB -> CIELAB (D65), float32."""
    c = rgb.astype(np.float32) / 255.0
    linear = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]], dtype=np.float32)
    xyz = linear @ m.T
    xyz /= np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    lab = np.asarray(lab, dtype=np.float32)
    fy = (lab[..., 0] + 16) / 116
    fx, fz = fy + lab[..., 1] / 500, fy - lab[..., 2] / 200
    eps, kappa = 216 / 24389, 24389 / 27
    def inv(t):
        return np.where(t ** 3 > eps, t ** 3, (116 * t - 16) / kappa)
    xyz = np.stack([inv(fx), np.where(lab[..., 0] > kappa * eps, fy ** 3, lab[..., 0] / kappa), inv(fz)], axis=-1) * np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    m = np.array([[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560], [0.0556434, -0.2040259, 1.0572252]], dtype=np.float32)
    linear = np.clip(xyz @ m.T, 0, 1)
    c = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - 0.055)
    return np.clip(np.round(c * 255), 0, 255).astype(np.uint8)


def delta_e2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 (Sharma et al. 2005), broadcasting over leading axes."""
    l1, a1, b1 = np.moveaxis(np.asarray(lab1, dtype=np.float64), -1, 0)
    l2, a2, b2 = np.moveaxis(np.asarray(lab2, dtype=np.float64), -1, 0)
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - np.sqrt(c_bar ** 7 / (c_bar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dl, dc = l2 - l1, c2p - c1p
    dh = h2p - h1p
    dh = np.where(c1p * c2p == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dH = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh) / 2)
    l_bar, c_bar_p = (l1 + l2) / 2, (c1p + c2p) / 2
    h_sum = h1p + h2p
    h_bar = np.where(c1p * c2p == 0, h_sum, np.where(np.abs(h1p - h2p) <= 180, h_sum / 2, np.where(h_sum < 360, (h_sum + 360) / 2, (h_sum - 360) / 2)))
    t = 1 - 0.17 * np.cos(np.radians(h_bar - 30)) + 0.24 * np.cos(np.radians(2 * h_bar)) + 0.32 * np.cos(np.radians(3 * h_bar + 6)) - 0.20 * np.cos(np.radians(4 * h_bar - 63))
    d_theta = 30 * np.exp(-(((h_bar - 275) / 25) ** 2))
    r_c = 2 * np.sqrt(c_bar_p ** 7 / (c_bar_p ** 7 + 25 ** 7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / np.sqrt(20 + (l_bar - 50) ** 2)
    s_c, s_h = 1 + 0.045 * c_bar_p, 1 + 0.015 * c_bar_p * t
    r_t = -np.sin(np.radians(2 * d_theta)) * r_c
    return np.sqrt((dl / s_l) ** 2 + (dc / s_c) ** 2 + (dH / s_h) ** 2 + r_t * (dc / s_c) * (dH / s_h))


# ---------- structure of a change mask (benilla `shape` / `hotspot` ideas, re-implemented) ----------
def mask_shape(mask: np.ndarray, min_size: int = 16, hotspots: int = 5) -> dict:
    """4-connected components of a boolean mask.

    coherence = largest component / all masked pixels. Reading rule: a few pixels at one spot is a tie flip;
    many small runs (low coherence) is shimmer, z-fighting or particles; one large solid run is a visibility,
    culling, LOD or content change.
    """
    from scipy import ndimage

    total = int(mask.sum())
    if total == 0:
        return {"pixels": 0, "components": 0, "largest": 0, "coherence": None, "kind": "none", "hotspots": []}
    labels, count = ndimage.label(mask, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    sizes = np.bincount(labels.ravel())[1:]
    big = np.flatnonzero(sizes >= min_size) + 1
    largest = int(sizes.max())
    coherence = largest / total
    if total < 64:
        kind = "tie-flip"
    elif coherence >= 0.6:
        kind = "solid"
    elif coherence < 0.25 and count >= 20:
        kind = "scattered"
    else:
        kind = "mixed"
    boxes = []
    if len(big):
        objects = ndimage.find_objects(labels)
        for label_id in big[np.argsort(sizes[big - 1])[::-1][:hotspots]]:
            region = objects[label_id - 1]
            boxes.append({"x": int(region[1].start), "y": int(region[0].start), "w": int(region[1].stop - region[1].start),
                          "h": int(region[0].stop - region[0].start), "pixels": int(sizes[label_id - 1])})
    return {"pixels": total, "components": int(count), "componentsOverMin": int(len(big)), "largest": largest,
            "coherence": round(coherence, 3), "kind": kind, "hotspots": boxes}


# ---------- heatmap ----------
_ANCHORS = np.array([[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]], dtype=np.float32)


def inferno_lut() -> np.ndarray:
    positions = np.linspace(0, 1, len(_ANCHORS))
    x = np.linspace(0, 1, 256)
    return np.stack([np.interp(x, positions, _ANCHORS[:, channel]) for channel in range(3)], axis=-1).astype(np.uint8)
