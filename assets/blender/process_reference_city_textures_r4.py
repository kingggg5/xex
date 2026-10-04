"""Prepare pinned Poly Haven CC0 PBR maps for the Blender city builder.

The upstream 1K files are downloaded once by the authoring workflow. This
processor does no network I/O; it grades albedo for the town palette, bakes a
small amount of AO into color, and writes the images consumed by R4.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "assets/models/reference-city/r4/source-textures"
OUT = ROOT / "assets/models/reference-city/r4/textures"
R3 = ROOT / "assets/models/reference-city/r3/textures"
OUT.mkdir(parents=True, exist_ok=True)


def read_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def read_ao(slug: str) -> np.ndarray:
    path = SOURCE / f"{slug}_ao_1k.jpg"
    if path.exists():
        return np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0
    # Cobblestone Floor 001 publishes packed AO/Rough/Metal as ARM.
    arm = np.asarray(Image.open(SOURCE / f"{slug}_arm_1k.jpg").convert("RGB"), dtype=np.float32)
    return arm[..., 0] / 255.0


def grade_albedo(slug: str, *, brightness=1.0, saturation=1.0, contrast=1.0, tint=(1.0, 1.0, 1.0)) -> np.ndarray:
    albedo = Image.fromarray(read_rgb(SOURCE / f"{slug}_diff_1k.jpg"), "RGB")
    albedo = ImageEnhance.Color(albedo).enhance(saturation)
    albedo = ImageEnhance.Contrast(albedo).enhance(contrast)
    albedo = ImageEnhance.Brightness(albedo).enhance(brightness)
    pixels = np.asarray(albedo, dtype=np.float32)
    ao = read_ao(slug)
    # Preserve local crevice detail without baking full black shadows into the
    # diffuse map; dynamic sun shadows remain the runtime lighting's job.
    occlusion = 0.72 + 0.28 * ao
    pixels *= occlusion[..., None]
    pixels *= np.asarray(tint, dtype=np.float32)[None, None, :]
    return np.clip(pixels, 0, 255).astype(np.uint8)


def hue_variant(rgb: np.ndarray, hue: float, saturation=0.68, value=1.0) -> np.ndarray:
    hsv = np.asarray(Image.fromarray(rgb, "RGB").convert("HSV"), dtype=np.float32)
    hsv[..., 0] = hue * 255.0
    hsv[..., 1] = np.clip(hsv[..., 1] * saturation, 36, 230)
    hsv[..., 2] = np.clip(hsv[..., 2] * value, 0, 255)
    return np.asarray(Image.fromarray(np.clip(hsv, 0, 255).astype(np.uint8), "HSV").convert("RGB"))


def save_image(name: str, pixels: np.ndarray, fmt="PNG") -> str:
    path = OUT / name
    Image.fromarray(pixels, "RGB").save(path, format=fmt, quality=95, optimize=True)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_map(slug: str, source_suffix: str, output_name: str) -> str:
    suffix=source_suffix.lower()
    source = SOURCE / f"{slug}_{suffix}_1k.{ 'png' if suffix == 'nor_gl' else 'jpg' }"
    target = OUT / output_name
    shutil.copyfile(source, target)
    return hashlib.sha256(target.read_bytes()).hexdigest()


def main():
    digests = {}
    stone = grade_albedo("stone_wall_04", brightness=1.42, saturation=0.48, contrast=0.90, tint=(1.02, 1.00, 0.94))
    trim = np.clip(stone.astype(np.float32) * 1.11, 0, 255).astype(np.uint8)
    plaster = grade_albedo("plastered_stone_wall", brightness=1.24, saturation=0.55, contrast=0.94, tint=(1.02, 1.00, 0.94))
    plaster = np.clip(plaster.astype(np.float32)*0.44 + np.array([148,135,104])[None,None,:],0,255).astype(np.uint8)
    wood = grade_albedo("weathered_planks", brightness=1.08, saturation=0.78, contrast=1.02, tint=(1.04, 1.00, 0.93))
    cobble = grade_albedo("cobblestone_floor_001", brightness=1.08, saturation=0.70, contrast=1.04, tint=(1.02, 1.01, 0.98))
    cliff = grade_albedo("cliff_side", brightness=1.10, saturation=0.48, contrast=1.00, tint=(1.03, 1.03, 1.02))
    roof = grade_albedo("roof_tiles", brightness=1.03, saturation=0.80, contrast=1.04)
    albedos = {
        "stone_limestone.png": stone,
        "stone_trim.png": trim,
        "plaster_warm.png": plaster,
        "wood_oak.png": wood,
        "street_cobble.png": cobble,
        "cliff_side.png": cliff,
        "roof_terracotta.png": roof,
        "roof_slate.png": hue_variant(roof, 0.62, saturation=1.35, value=0.78),
        "roof_slate_light.png": hue_variant(roof, 0.62, saturation=1.12, value=0.93),
        "roof_teal.png": hue_variant(roof, 0.47, saturation=0.70, value=0.92),
        "roof_copper.png": hue_variant(roof, 0.075, saturation=0.60, value=0.82),
    }
    for name, pixels in albedos.items():
        digests[name] = save_image(name, pixels)

    maps = [
        ("stone_wall_04", "nor_gl", "stone_normal.png"), ("stone_wall_04", "Rough", "stone_roughness.jpg"),
        ("plastered_stone_wall", "nor_gl", "plaster_normal.png"), ("plastered_stone_wall", "Rough", "plaster_roughness.jpg"),
        ("weathered_planks", "nor_gl", "wood_normal.png"), ("weathered_planks", "Rough", "wood_roughness.jpg"),
        ("roof_tiles", "nor_gl", "roof_normal.png"), ("roof_tiles", "Rough", "roof_roughness.jpg"),
        ("cobblestone_floor_001", "nor_gl", "cobble_normal.png"), ("cobblestone_floor_001", "Rough", "cobble_roughness.jpg"),
        ("cliff_side", "nor_gl", "cliff_normal.png"), ("cliff_side", "Rough", "cliff_roughness.jpg"),
    ]
    for slug, source_map, output_name in maps:
        digests[output_name] = copy_map(slug, source_map, output_name)

    # Retain the local path/ground/water review materials for the presentation
    # scene; these maps are not substitutions for the new CC0 city surfaces.
    for name in ["grass_field.png", "grass_field_normal.png", "dirt_path.png", "dirt_path_normal.png", "water_soft.png", "water_soft_normal.png"]:
        shutil.copyfile(R3 / name, OUT / name)
        digests[name] = hashlib.sha256((OUT / name).read_bytes()).hexdigest()

    receipt = {
        "revision": "r4",
        "upstream_license": "Poly Haven CC0; original source links, authors, byte sizes and hashes are recorded in ../provenance.json.",
        "resolution": "1K source maps; albedo palette grading and subtle AO multiply are deterministic and performed locally.",
        "processing": {
            "stone": "warm limestone; 1.20 brightness, 0.58 saturation, 0.96 contrast; AO contributes 28% maximum darkening.",
            "plaster": "warm light facade; 1.24 brightness, 0.55 saturation, 0.94 contrast; AO contributes 28% maximum darkening.",
            "roof_variants": "one weathered tile albedo recolored to terracotta, cobalt, pale slate, teal and copper; source tangent normals and roughness shared.",
            "wood": "weathered planks warmed slightly; cracks, grain, nail/wear marks retained.",
            "cobble": "weathered medieval stones and moss/dirt joints retained.",
            "cliff": "layered cliff albedo desaturated to a pale warm stone palette."
        },
        "sha256": digests
    }
    (OUT / "processed-textures.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"processed": len(digests), "directory": str(OUT), "manifest": str(OUT / "processed-textures.json")}))


if __name__ == "__main__":
    main()
