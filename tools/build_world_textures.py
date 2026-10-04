"""Prepare bounded-resolution, reusable ground textures for world cells."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "models" / "reference-city" / "r5" / "textures"
MEADOW_ALBEDO = ROOT / "assets" / "models" / "world-v2" / "textures" / "grass_meadow_v2_source.png"
CANOPY_ALBEDO = ROOT / "assets" / "models" / "world-v2" / "textures" / "leaf_canopy_v2_source.png"
TREE_BARK_ALBEDO = ROOT / "assets" / "models" / "world-v3" / "textures" / "oak_bark_albedo_source.png"
CLIFF_ALBEDO = ROOT / "assets" / "models" / "world-v3" / "textures" / "cliff_granite_albedo_source.png"
RUNTIME = ROOT / "apps" / "client" / "src" / "assets" / "world"
MANIFEST = ROOT / "assets" / "models" / "world-v1" / "texture-manifest.json"
RECIPES = {
    "grass_ground_albedo": (1024, "RGB", "sRGB"),
    "grass_ground_normal": (1024, "RGB", "linear OpenGL +Y"),
    "leaf_canopy_albedo": (512, "RGBA", "sRGB with cutout alpha"),
    "world_tree_bark_albedo": (512, "RGB", "sRGB; runtime mirror wrapping mitigates raw edge discontinuity"),
    "cliff_granite_albedo": (1024, "RGB", "sRGB; runtime mirrored sampler; source not verified seamless"),
    "stone_foundation_albedo": (512, "RGB", "sRGB"),
    "stone_foundation_normal": (512, "RGB", "linear OpenGL +Y"),
    "timber_dark_albedo": (512, "RGB", "sRGB"),
    "timber_dark_normal": (512, "RGB", "linear OpenGL +Y"),
    "cobble_path_albedo": (512, "RGB", "sRGB"),
    "cobble_path_normal": (512, "RGB", "linear OpenGL +Y"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, (size, mode, colorspace) in RECIPES.items():
        source = (MEADOW_ALBEDO if name == "grass_ground_albedo"
                  else CANOPY_ALBEDO if name == "leaf_canopy_albedo"
                  else TREE_BARK_ALBEDO if name == "world_tree_bark_albedo"
                  else CLIFF_ALBEDO if name == "cliff_granite_albedo"
                  else SOURCE / f"{name}.png")
        output = RUNTIME / f"{name}.png"
        if not source.is_file():
            raise FileNotFoundError(f"R5 foundry texture is missing: {source}")
        with Image.open(source) as source_image:
            converted = source_image.convert(mode)
            if converted.size != (size, size):
                converted = converted.resize((size, size), Image.Resampling.LANCZOS)
            adjustments = "none"
            if name == "grass_ground_albedo":
                adjustments = "AI source albedo; resolution resampling only, shader controls tint"
            temporary = None
            try:
                with NamedTemporaryFile(prefix="world-texture-", suffix=".png", dir=RUNTIME, delete=False) as handle:
                    temporary = Path(handle.name)
                converted.save(temporary, format="PNG", optimize=True, compress_level=9)
                os.replace(temporary, output)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
            entries.append({
                "source": source.relative_to(ROOT).as_posix(),
                "source_sha256": sha256(source),
                "runtime": output.relative_to(ROOT).as_posix(),
                "runtime_sha256": sha256(output),
                "pixels": [size, size],
                "channels": mode,
                "colorspace": colorspace,
                "adjustments": adjustments,
                "bytes": output.stat().st_size,
            })
    MANIFEST.write_text(json.dumps({
        "schema": "aetherfield.world-textures/1",
        "source": "Original R5 foundry textures plus workspace AI meadow albedo; grass normal is a low-strength legacy micro-detail approximation, not a matched high-poly bake.",
        "resampling": "Pillow LANCZOS, PNG optimize, compression level 9",
        "textures": entries,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "textures": entries}, indent=2))


if __name__ == "__main__":
    main()
