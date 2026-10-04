"""Render four review views of the preserved hero oak without saving the blend."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[3]
SOURCE_BLEND = REPO_ROOT / "assets" / "models" / "hero-oak" / "v1" / "hero_oak.blend"
OUTPUT_DIR = REPO_ROOT / "assets" / "models" / "hero-oak" / "v1" / "review"
OUTPUT_NAMES = ("player.png", "side.png", "bark.png", "crown.png")

CAMERAS = (
    {"name": "player", "location": (12.0, -17.0, 3.2), "target": (0.0, 0.0, 3.8), "lens_mm": 50.0},
    {"name": "side", "location": (14.0, 2.0, 4.0), "target": (0.0, 0.0, 4.3), "lens_mm": 38.0},
    {"name": "bark", "location": (1.8, -3.4, 1.4), "target": (0.0, 0.0, 1.6), "lens_mm": 50.0},
    {"name": "crown", "location": (11.0, -12.0, 13.0), "target": (0.0, 0.0, 5.5), "lens_mm": 50.0},
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Output is not a PNG: {path}")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def track_to(obj, target) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_area_light(name, location, target, energy, color, size):
    light_data = bpy.data.lights.new(name=name, type="AREA")
    light_data.energy = energy
    light_data.color = color
    light_data.shape = "DISK"
    light_data.size = size
    light_data.use_shadow = True
    if hasattr(light_data, "use_shadow_jitter"):
        light_data.use_shadow_jitter = True
    light_obj = bpy.data.objects.new(name, light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.location = location
    track_to(light_obj, target)
    return light_obj


def add_review_studio():
    scene = bpy.context.scene

    # A restrained, untextured floor exists only in this unsaved render session.
    floor_material = bpy.data.materials.new("ReviewStudio_Floor")
    floor_material.use_nodes = True
    floor_bsdf = next(node for node in floor_material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    floor_bsdf.inputs["Base Color"].default_value = (0.16, 0.175, 0.19, 1.0)
    floor_bsdf.inputs["Roughness"].default_value = 0.88
    bpy.ops.mesh.primitive_plane_add(size=200.0, location=(0.0, 0.0, -0.025))
    floor = bpy.context.object
    floor.name = "ReviewStudio_Floor"
    floor.data.materials.append(floor_material)

    studio_world = bpy.data.worlds.new("ReviewStudio_NeutralWorld")
    studio_world.use_nodes = True
    background = next(node for node in studio_world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.22, 0.24, 0.27, 1.0)
    background.inputs["Strength"].default_value = 0.45
    scene.world = studio_world

    light_target = (0.0, 0.0, 4.0)
    add_area_light("Review_WarmKey", (-5.0, -7.0, 11.0), light_target, 1700.0, (1.0, 0.86, 0.70), 6.0)
    add_area_light("Review_CoolFill", (7.0, -5.0, 6.0), light_target, 850.0, (0.72, 0.83, 1.0), 7.0)
    add_area_light("Review_SoftRim", (-1.0, 5.0, 10.0), light_target, 1900.0, (0.88, 0.94, 1.0), 5.0)


def create_camera(config):
    camera_data = bpy.data.cameras.new(f"ReviewCamera_{config['name']}")
    camera_data.lens = config["lens_mm"]
    camera_data.dof.use_dof = False
    camera_obj = bpy.data.objects.new(camera_data.name, camera_data)
    bpy.context.scene.collection.objects.link(camera_obj)
    camera_obj.location = config["location"]
    track_to(camera_obj, config["target"])
    return camera_obj


def camera_record(config, camera_obj):
    bpy.context.view_layer.update()
    return {
        "name": config["name"],
        "location": [round(float(v), 6) for v in camera_obj.location],
        "target": list(config["target"]),
        "lens_mm": config["lens_mm"],
        "matrix_world": [[round(float(camera_obj.matrix_world[row][col]), 9) for col in range(4)] for row in range(4)],
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    expected_blend = SOURCE_BLEND.resolve()
    loaded_blend = Path(bpy.data.filepath).resolve()
    if loaded_blend != expected_blend:
        raise RuntimeError(f"Loaded blend does not match frozen baseline: {loaded_blend}")
    if not SOURCE_BLEND.is_file():
        raise FileNotFoundError(SOURCE_BLEND)

    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(mesh_objects) != 1 or mesh_objects[0].name != "sunmeadow_hero_oak":
        raise RuntimeError(f"Expected the preserved single oak mesh, got {[obj.name for obj in mesh_objects]}")
    oak = mesh_objects[0]
    if tuple(round(float(v), 3) for v in oak.dimensions) != (9.349, 5.065, 8.6):
        raise RuntimeError(f"Unexpected baseline bounds: {tuple(oak.dimensions)}")

    texture_nodes = []
    for material in oak.data.materials:
        if not material or not material.use_nodes or not material.node_tree:
            continue
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                texture_nodes.append({
                    "material": material.name,
                    "image": node.image.name,
                    "dimensions": list(node.image.size[:]),
                    "packed": bool(node.image.packed_file),
                })
    source_sha = sha256_file(SOURCE_BLEND)

    engine_items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    engine_ids = {item.identifier for item in engine_items}
    if "BLENDER_EEVEE" in engine_ids:
        engine = "BLENDER_EEVEE"
    elif "CYCLES" in engine_ids:
        engine = "CYCLES"
    else:
        raise RuntimeError(f"No supported Eevee or Cycles engine in this Blender: {sorted(engine_ids)}")

    scene = bpy.context.scene
    scene.render.engine = engine
    if engine == "BLENDER_EEVEE":
        eevee = getattr(scene, "eevee", None)
        if eevee and hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 32
    else:
        scene.cycles.device = "CPU"
        scene.cycles.samples = 16
        scene.cycles.max_bounces = 4

    scene.render.resolution_x = 1000
    scene.render.resolution_y = 750
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 6
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_mode = "RGB"
    if hasattr(scene.view_settings, "view_transform"):
        try:
            scene.view_settings.view_transform = "AgX"
        except TypeError:
            pass
    if hasattr(scene.view_settings, "look"):
        try:
            scene.view_settings.look = "Medium High Contrast"
        except TypeError:
            pass
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0

    add_review_studio()
    manifest = {
        "status": "RUNNING",
        "source": {
            "blend": str(SOURCE_BLEND.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256_before": source_sha,
            "mesh": oak.name,
            "dimensions_m": [round(float(v), 6) for v in oak.dimensions],
            "preserved_texture_images": texture_nodes,
            "surface_note": "The existing albedo image is preserved; its supplied pixels contain baked detail. No normal map, procedural texture noise, or replacement geometry was added.",
        },
        "render": {
            "blender_version": bpy.app.version_string,
            "blender_build_hash": bpy.app.build_hash.decode("utf-8", "replace") if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
            "engine": "EEVEE" if engine == "BLENDER_EEVEE" else "Cycles CPU",
            "resolution": [1000, 750],
            "samples": 32 if engine == "BLENDER_EEVEE" else 16,
            "command_argv": sys.argv,
            "command_display": subprocess.list2cmdline(sys.argv),
            "wall_clock_seconds": None,
            "errors": [],
        },
        "views": [],
        "outputs": [],
        "baseline_sha256_after": None,
    }

    started = time.monotonic()
    try:
        for config in CAMERAS:
            camera = create_camera(config)
            scene.camera = camera
            record = camera_record(config, camera)
            output_path = OUTPUT_DIR / f"{config['name']}.png"
            scene.render.filepath = str(output_path)
            view_started = time.monotonic()
            bpy.ops.render.render(write_still=True)
            record["render_seconds"] = round(time.monotonic() - view_started, 3)
            record["output"] = output_path.relative_to(REPO_ROOT).as_posix()
            manifest["views"].append(record)
            width, height = png_dimensions(output_path)
            manifest["outputs"].append({
                "path": output_path.relative_to(REPO_ROOT).as_posix(),
                "width": width,
                "height": height,
                "bytes": output_path.stat().st_size,
                "sha256": sha256_file(output_path),
            })
            print(f"REVIEW_RENDER_OK {config['name']} {width}x{height} {record['render_seconds']}s", flush=True)
        if [Path(item["path"]).name for item in manifest["outputs"]] != list(OUTPUT_NAMES):
            raise RuntimeError("Output roster mismatch")
        manifest["status"] = "PASS"
    except Exception:
        manifest["status"] = "FAIL"
        manifest["render"]["errors"].append(traceback.format_exc())
        raise
    finally:
        manifest["render"]["wall_clock_seconds"] = round(time.monotonic() - started, 3)
        manifest["baseline_sha256_after"] = sha256_file(SOURCE_BLEND)
        manifest["baseline_unchanged"] = manifest["baseline_sha256_after"] == source_sha
        manifest_path = OUTPUT_DIR / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"REVIEW_MANIFEST {manifest_path}", flush=True)


main()
