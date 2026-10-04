"""Build the three origin-anchored branching tree templates and their review.

Run with Blender in background mode and ``--python`` pointing to this file.
Use ``-- --out-dir assets/models/world-v2/trees-v3`` for a separate comparison
kit. The default remains assets/models/world-v2/trees. Source meshes remain at
the origin; separate display clones form the saved review scene and never enter
the geometry-only GLB. Runtime material assignment and Meshopt admission belong
to the caller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "assets" / "models" / "world-v2" / "trees"
HELPER = Path(__file__).with_name("branching_canopy_v2.py")
KIT_SOURCE = ROOT / "assets" / "blender" / "city_r5" / "lib" / "citykit.py"
sys.path[:0] = [str(KIT_SOURCE.parent), str(HELPER.parent)]
import citykit as C  # noqa: E402
from branching_canopy_v2 import build_branching_trees, LEAF_CARD_COUNT, TREE_TRIANGLE_COUNT  # noqa: E402


VARIANTS = (("A", "tree_a", 7.0, 1.2), ("B", "tree_b", 5.6, 1.1), ("C", "tree_c", 8.6, 1.5))
REQUIRED_ATTRIBUTES = {"POSITION", "NORMAL", "TEXCOORD_0", "COLOR_0"}


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path):
    return path.relative_to(ROOT).as_posix()


def _glb_data(path):
    payload = path.read_bytes()
    magic, version, byte_length = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or byte_length != len(payload):
        raise RuntimeError("Invalid geometry-only GLB header")
    document, binary, offset = None, None, 12
    while offset < len(payload):
        length, kind = struct.unpack_from("<II", payload, offset)
        chunk = payload[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        offset += 8 + length
    if document is None or binary is None:
        raise RuntimeError("GLB is missing its JSON or binary chunk")
    return document, binary


def _accessor_values(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dimensions = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    code, byte_size, maximum = {
        5120: ("b", 1, 127), 5121: ("B", 1, 255),
        5122: ("h", 2, 32767), 5123: ("H", 2, 65535),
        5125: ("I", 4, 4294967295), 5126: ("f", 4, None),
    }[accessor["componentType"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", byte_size * dimensions)
    for index in range(accessor["count"]):
        values = struct.unpack_from("<" + code * dimensions, binary, start + index * stride)
        if accessor.get("normalized") and maximum:
            values = tuple(max(-1.0, value / maximum) for value in values)
        yield values


def _audit_low_branches(obj, radius):
    obj.data.calc_loop_triangles()
    measured = 0.0
    for triangle in obj.data.loop_triangles:
        vertices = [obj.data.vertices[index].co for index in triangle.vertices]
        clipped = [point for point in vertices if point.z <= 2.2]
        for first, second in zip(vertices, vertices[1:] + vertices[:1]):
            if (first.z < 2.2 < second.z) or (second.z < 2.2 < first.z):
                clipped.append(first.lerp(second, (2.2 - first.z) / (second.z - first.z)))
        for point in clipped:
            measured = max(measured, math.hypot(point.x, point.y))
    if measured > radius + 1e-5:
        raise RuntimeError(f"Tree branch leaves its existing walking blocker: {obj.name}")
    return measured


def _source_geometry():
    collection = C.collection("SOURCE tree templates - origin anchored")
    objects, records = [], []
    for letter, kind, height, collider_width in VARIANTS:
        prop = {"id": f"tree_{letter}", "kind": kind, "x": 0.0, "z": 0.0,
                "height": height, "scale": 1.0, "yaw": 0.0,
                "collider_size": [collider_width, height, collider_width]}
        variant_objects = build_branching_trees([prop], collection, C)
        low = min(vertex.co.z for obj in variant_objects for vertex in obj.data.vertices)
        high = max(vertex.co.z for obj in variant_objects for vertex in obj.data.vertices)
        vertical_scale = height / (high - low)
        # Bake the slight bounds adjustment into mesh coordinates: all template
        # object transforms stay identity, root bottom is 0 and top is nominal.
        for obj in variant_objects:
            role = "canopy" if "leaf_cards" in obj else "trunk"
            obj.name = obj.data.name = f"tree_{letter}_{role}"
            for vertex in obj.data.vertices:
                vertex.co.z = (vertex.co.z - low) * vertical_scale
            obj.data.update()
            obj.data.calc_loop_triangles()
        trunk = next(obj for obj in variant_objects if obj.name.endswith("_trunk"))
        canopy = next(obj for obj in variant_objects if obj.name.endswith("_canopy"))
        low_radius = _audit_low_branches(trunk, collider_width * 0.32)
        canopy_heights = [vertex.co.z for vertex in canopy.data.vertices]
        card_centers = [sum(vertex.co.z for vertex in canopy.data.vertices[start:start + 9]) / 9.0
                        for start in range(0, len(canopy.data.vertices), 9)]
        canopy_high = max(canopy_heights)
        if len(canopy.data.vertices) != LEAF_CARD_COUNT * 9:
            raise RuntimeError(f"Unexpected source card topology: {canopy.name}")
        if sum(abs(value - canopy_high) < 1e-6 for value in canopy_heights) > 3:
            raise RuntimeError(f"Canopy has a uniform clipped top plane: {canopy.name}")
        records.append({"variant": letter, "source_kind": kind, "nominal_height_m": height,
                        "collider_size_m": prop["collider_size"],
                        "walking_radius_m": collider_width * 0.32,
                        "measured_low_solid_radius_m": round(low_radius, 6),
                        "baked_vertical_scale": round(vertical_scale, 8),
                        "source_bottom_before_adjustment_m": round(low, 8),
                        "leaf_cards": LEAF_CARD_COUNT, "source_triangles": TREE_TRIANGLE_COUNT,
                        "canopy_height_range_m": [round(min(canopy_heights), 6), round(canopy_high, 6)],
                        "card_center_height_range_m": [round(min(card_centers), 6), round(max(card_centers), 6)],
                        "canopy_top_vertex_count": sum(abs(value - canopy_high) < 1e-6 for value in canopy_heights),
                        "nodes": [f"tree_{letter}_trunk", f"tree_{letter}_canopy"],
                        "review_source_materials": ["world_tree_bark", "world_leaf_cards"]})
        objects.extend(variant_objects)
    return collection, objects, records


def _export_geometry(objects, path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_yup=True, export_apply=True, export_materials="NONE",
        export_vertex_color="NAME", export_vertex_color_name="Col",
        export_all_vertex_colors=False, export_active_vertex_color_when_no_material=True,
        export_texcoords=True, export_normals=True, export_tangents=False,
        export_cameras=False, export_lights=False, export_animations=False,
        export_extras=False, export_draco_mesh_compression_enable=False,
    )


def _review_bark_material():
    """Use the dedicated shared bark atlas when available; flag legacy preview."""
    material = C.get_material("world_tree_bark")
    texture_root = ROOT / "apps" / "client" / "src" / "assets" / "world"
    choices = ((Path(C.TEX_DIR) / "world_tree_bark_albedo.png", False),
               (texture_root / "world_tree_bark_albedo.png", False),
               (Path(C.TEX_DIR) / "timber_dark_albedo.png", True))
    choice = next(((path, provisional) for path, provisional in choices if path.is_file()), None)
    if choice is None:
        return {"material": "world_tree_bark", "albedo": None, "provisional": True,
                "limit": "Dedicated bark atlas unavailable; neutral white geometry preview only"}
    path, provisional = choice
    nodes, links = material.node_tree.nodes, material.node_tree.links
    texture = nodes.new("ShaderNodeTexImage")
    texture.name = "Tree bark review albedo"
    texture.image = bpy.data.images.load(str(path), check_existing=True)
    texture.image.colorspace_settings.name = "sRGB"
    uv = next(node for node in nodes if node.type == "UVMAP")
    multiplier = next(node for node in nodes if node.type == "MIX" and node.blend_type == "MULTIPLY")
    links.new(uv.outputs["UV"], texture.inputs["Vector"])
    links.new(texture.outputs["Color"], multiplier.inputs["A"])
    return {"material": "world_tree_bark", "albedo": _relative(path), "provisional": provisional,
            "limit": "Legacy timber striping is a review placeholder; parent supplies original oak bark" if provisional else None}


def _audit_export(path, records):
    document, binary = _glb_data(path)
    expected = {node for record in records for node in record["nodes"]}
    actual = {node["name"] for node in document["nodes"]}
    if actual != expected or len(document["nodes"]) != 6 or len(document["meshes"]) != 6:
        raise RuntimeError("GLB does not contain exactly six named tree template meshes")
    if any(document.get(key) for key in ("materials", "images", "textures", "cameras", "animations", "skins")):
        raise RuntimeError("Geometry-only GLB contains material, image or scene payload")
    triangles = 0
    meshes = []
    for node in document["nodes"]:
        if any(abs(value) > 1e-7 for value in node.get("translation", (0.0, 0.0, 0.0))):
            raise RuntimeError(f"Exported tree mesh has a layout offset: {node['name']}")
        if node.get("scale", [1.0, 1.0, 1.0]) != [1.0, 1.0, 1.0] or "matrix" in node or "rotation" in node:
            raise RuntimeError(f"Exported tree template transform is not identity: {node['name']}")
        mesh = document["meshes"][node["mesh"]]
        if len(mesh["primitives"]) != 1:
            raise RuntimeError(f"Expected one primitive per tree part: {node['name']}")
        primitive = mesh["primitives"][0]
        attributes = primitive["attributes"]
        if set(attributes) != REQUIRED_ATTRIBUTES or primitive.get("mode", 4) != 4:
            raise RuntimeError(f"Exported tree attributes differ from the runtime contract: {node['name']}")
        attribute_counts = [document["accessors"][index]["count"] for index in attributes.values()]
        if len(set(attribute_counts)) != 1:
            raise RuntimeError(f"Tree attribute vertex counts differ: {node['name']}")
        positions = list(_accessor_values(document, binary, attributes["POSITION"]))
        normals = list(_accessor_values(document, binary, attributes["NORMAL"]))
        uvs = list(_accessor_values(document, binary, attributes["TEXCOORD_0"]))
        colors = list(_accessor_values(document, binary, attributes["COLOR_0"]))
        if not all(math.isfinite(value) for point in positions + normals + uvs + colors for value in point):
            raise RuntimeError(f"Nonfinite exported attribute: {node['name']}")
        if not all(abs(sum(value * value for value in normal) - 1.0) < 1e-4 for normal in normals):
            raise RuntimeError(f"Invalid exported normal: {node['name']}")
        if not all(-1e-6 <= value <= 1.0 + 1e-6 for uv in uvs for value in uv):
            raise RuntimeError(f"Exported UV leaves the unit texture domain: {node['name']}")
        if not all(abs(value - 1.0) < 1e-6 for color in colors for value in color):
            raise RuntimeError(f"Exported COLOR_0 is not neutral white: {node['name']}")
        indices = list(_accessor_values(document, binary, primitive["indices"]))
        if len(indices) % 3 or any(index[0] >= len(positions) for index in indices):
            raise RuntimeError(f"Invalid exported triangle indices: {node['name']}")
        count = len(indices) // 3
        triangles += count
        meshes.append({"name": node["name"], "vertices": len(positions), "triangles": count,
                       "attributes": sorted(attributes), "color_source_attribute": "Col",
                       "bounds_yup_m": {"min": [round(min(point[axis] for point in positions), 6) for axis in range(3)],
                                         "max": [round(max(point[axis] for point in positions), 6) for axis in range(3)]}})
    if triangles != TREE_TRIANGLE_COUNT * len(VARIANTS):
        raise RuntimeError(f"Tree kit triangle count changed: {triangles}")
    for record in records:
        parts = [mesh for mesh in meshes if mesh["name"] in record["nodes"]]
        low = min(mesh["bounds_yup_m"]["min"][1] for mesh in parts)
        high = max(mesh["bounds_yup_m"]["max"][1] for mesh in parts)
        if abs(low) > 1e-5 or abs(high - record["nominal_height_m"]) > 1e-5:
            raise RuntimeError(f"Tree variant bounds differ from its requested height: {record['variant']}")
        if sum(mesh["triangles"] for mesh in parts) != record["source_triangles"]:
            raise RuntimeError(f"Tree variant triangle count differs: {record['variant']}")
    return {"status": "PASS", "mesh_count": 6, "triangle_count": triangles,
            "attributes": sorted(REQUIRED_ATTRIBUTES), "color_source_attribute": "Col",
            "origin_anchored": True, "geometry_only": True, "meshes": meshes}


def _review_scene(source_collection, source_objects, path, elevated_path):
    review_collection = C.collection("REVIEW clones - excluded from GLB")
    source_collection.hide_render = True
    source_collection.hide_viewport = True
    offsets = {"A": -8.0, "B": 0.0, "C": 8.0}
    for source in source_objects:
        clone = source.copy()
        clone.name = f"REVIEW {source.name}"
        clone.location.x = offsets[source.name.split("_")[1]]
        review_collection.objects.link(clone)
    C.define_material("tree_kit_review_floor", tile=1.0, color=(0.26, 0.30, 0.245), rough=0.96)
    floor = C.new_object("REVIEW ground", [(-100, -100, -0.015), (100, -100, -0.015),
                        (100, 100, -0.015), (-100, 100, -0.015)], [(0, 1, 2, 3)],
                        "tree_kit_review_floor", review_collection)
    C.uv_box(floor)
    C.ensure_white_vertex_colors(floor)
    C.define_material("tree_kit_review_label", tile=1.0, color=(0.04, 0.065, 0.035), rough=1.0)
    for letter, _, height, _ in VARIANTS:
        data = bpy.data.curves.new(f"REVIEW label {letter}", "FONT")
        data.body = f"{letter}  |  {height:.1f} m"
        data.align_x = "CENTER"
        data.size = 0.5
        data.materials.append(C.get_material("tree_kit_review_label"))
        label = bpy.data.objects.new(data.name, data)
        label.location = (offsets[letter], -4.25, 0.09)
        label.rotation_euler.x = math.pi * 0.5
        review_collection.objects.link(label)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(path)
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("Tree kit soft sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.53, 0.64, 0.77, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.65
    scene.world = world
    light_data = bpy.data.lights.new("Tree kit sun", "SUN")
    light_data.energy = 2.0
    light_data.angle = math.radians(8.0)
    light = bpy.data.objects.new(light_data.name, light_data)
    light.rotation_euler = (math.radians(24), math.radians(-28), math.radians(-30))
    scene.collection.objects.link(light)
    target = Vector((0.0, 0.0, 3.8))
    cameras = []
    for title, elevation, destination in (("player-height", -4.0, path), ("elevated", 42.0, elevated_path)):
        camera_data = bpy.data.cameras.new(f"Tree kit {title} review camera")
        camera_data.type = "PERSP" if title == "player-height" else "ORTHO"
        camera_data.lens = 48.0
        camera_data.ortho_scale = 25.7
        camera_data.clip_end = 150.0
        camera = bpy.data.objects.new(camera_data.name, camera_data)
        angle = math.radians(elevation)
        camera.location = target + Vector((0.0, -34.0 * math.cos(angle), 34.0 * math.sin(angle)))
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(camera)
        scene.camera = camera
        scene.render.filepath = str(destination)
        bpy.ops.render.render(write_still=True)
        cameras.append(camera)
    scene.camera = cameras[0]
    scene.render.filepath = str(path)


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUTPUT), help="Asset-local kit destination under assets/models")
    arguments = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    OUTPUT = Path(arguments.out_dir).resolve()
    if not OUTPUT.is_relative_to((ROOT / "assets" / "models").resolve()):
        raise ValueError("Tree kit output must stay under this project's assets/models directory")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    C.reset_scene()
    C.TEX_DIR = ROOT / "assets" / "models" / "reference-city" / "r5" / "textures"
    source_collection, objects, records = _source_geometry()
    glb_path = OUTPUT / "tree-kit-source.glb"
    master_path = OUTPUT / "tree-kit.blend"
    review_path = OUTPUT / "review.png"
    elevated_review_path = OUTPUT / "review_elevated.png"
    _export_geometry(objects, glb_path)
    validation = _audit_export(glb_path, records)
    bark_review = _review_bark_material()
    _review_scene(source_collection, objects, review_path, elevated_review_path)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(master_path))
    manifest = {"schema": "aetherfield.branching-tree-kit/1", "generator": "Blender " + bpy.app.version_string,
                "geometry_provenance": "Original repository-authored procedural geometry; existing shared textures used only in the editable master and review.",
                "coordinate_system": "glTF Y-up, metres, identity node transforms, grounded origin shared by each trunk/canopy pair",
                "runtime_material_contract": {"trunk": "world_tree_bark: shared parent PBR bark", "canopy": "world_leaf_cards: shared parent two-sided alpha-test leaf material"},
                "source": [{"path": _relative(path), "sha256": _sha256(path)}
                           for path in (Path(__file__).resolve(), HELPER, KIT_SOURCE)],
                "variants": records, "validation": validation,
                "outputs": [{"path": _relative(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
                            for path in (glb_path, master_path, review_path, elevated_review_path)],
                "review": {"path": _relative(review_path), "source_meshes_hidden": True,
                           "layout_clones_excluded_from_glb": True,
                           "player_height_camera_elevation_deg": -4.0,
                           "elevated_camera_elevation_deg": 42.0,
                           "elevated_path": _relative(elevated_review_path),
                           "bark_material": bark_review},
                "admission": {"meshopt": "pending parent integration", "runtime_import": "pending parent integration"}}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("TREE_KIT_BUILD " + json.dumps({"status": "PASS", "triangles": validation["triangle_count"],
                                        "meshes": validation["mesh_count"], "source_helper_sha256": _sha256(HELPER),
                                        "outputs": manifest["outputs"]}), flush=True)


if __name__ == "__main__":
    main()
