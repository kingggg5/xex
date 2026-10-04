"""Isolated, pinned Modular Tree 5.5.2 evaluation for Blender 5.2.

This driver uses the upstream tree/leaf engine, never a local branch algorithm.
Run: blender --background --factory-startup --python this.py -- --mode probe
All outputs are candidates; this script never edits canonical city assets.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import zipfile

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / ".harness/.cache/tree-engines/modular-tree-5.5.2"
OUTPUT = ROOT / "assets/models/tree-engine-candidates/modular-tree-5.5.2"
ARCHIVE_SHA256 = "58aab6e397ae4659f8c4c08e5ac774b249476e681f4023f72a17ea413918897f"
TEXTURES = {
    "pine_twig_cc0.png": ("pine_tree_01", "twig_diff", "a4fa4a55aab9231915a4023ea9841577"),
    "pine_bark_cc0.jpg": ("pine_tree_01", "bark_diff", "7d3a558ed614c7e75594c7be3bf80311"),
    "broadleaf_cluster_cc0.png": ("tree_small_02", "leaves_diff", "2c667193084725e8553062ddbdc73c7d"),
    "broadleaf_bark_cc0.jpg": ("tree_small_02", "branch_diff", "88b531469f5dba2fc44ca85df3776e7c"),
    "pine_twig_alpha_cc0.png": ("pine_tree_01", "twig_alpha", "641911a5a3f543911dad04ebb26e7bca"),
    "broadleaf_alpha_cc0.png": ("tree_small_02", "leaves_alpha", "63199ba87a9e8928424bd8c3b8017bd0"),
    "fir_twig_cc0.png": ("fir_tree_01", "twig_diff", "3791a2e595b63410ed0bd054633373de"),
    "fir_twig_alpha_cc0.png": ("fir_tree_01", "twig_alpha", "02ab808c8b2ff77ad9fdb2f92892db80"),
}
SPECS = {
    "oak": {"preset": "OAK", "seed": 101, "height": 7.8, "radial": 8,
            "leaf_scale": 0.78, "max_radius": 0.10, "densities": [120.0, 30.0],
            "branch_density": 1.05, "split_probability": 0.22,
            "bark_budget": [3000, 650], "texture": "broadleaf_cluster_cc0.png",
            "alpha": "broadleaf_alpha_cc0.png", "bark": "broadleaf_bark_cc0.jpg", "uv": [0.005, 0.415, 0.0, 0.995], "card_width": 0.41},
    "conifer": {"preset": "PINE", "seed": 303, "height": 10.8, "radial": 6,
                "leaf_scale": 1.05, "max_radius": 0.10, "densities": [170.0, 19.0],
                "branch_density": 1.65, "split_probability": 0.10,
                "bark_budget": [2700, 600], "texture": "pine_twig_cc0.png",
                "alpha": "pine_twig_alpha_cc0.png", "bark": "pine_bark_cc0.jpg", "uv": [0.001, 0.205, 0.545, 0.998], "card_width": 0.46},
}
SPECS_V2 = {
    "oak": {"preset": "OAK", "seed": 221, "height": 7.2, "radial": 6,
            "leaf_scale": 0.60, "max_radius": 0.095, "densities": [75.0, 12.0],
            "branch_density": 1.85, "split_probability": 0.12,
            "bark_budget": [1800, 600], "texture": "broadleaf_cluster_cc0.png", "alpha": "broadleaf_alpha_cc0.png",
            "bark": "broadleaf_bark_cc0.jpg", "uv": [0.005, 0.415, 0.0, 0.995], "card_width": 0.41,
            "leaf_mode": "NATIVE_OAK", "leaf_color": [0.32, 0.57, 0.075, 1.0],
            "trunk_params": {"length": 8.0, "start_radius": 0.38, "end_radius": 0.035, "shape": 0.75, "up_attraction": 0.95, "randomness": 0.72},
            "branch_params": {"start": 0.38, "end": 0.98, "length": 4.0, "start_angle": 73.0,
                              "gravity_strength": 2.4, "stiffness": 0.55, "up_attraction": 0.18,
                              "randomness": 0.68, "flatness": 0.42, "start_radius": 0.38,
                              "crown_shape": "Spherical", "crown_base_size": 0.26, "crown_height": 8.0, "crown_angle_variation": -4.0},
            "secondary_params": {"start": 0.24, "end": 0.98, "length": 1.35, "branches_density": 1.35,
                                 "start_angle": 55.0, "gravity_strength": 1.2, "stiffness": 0.45,
                                 "up_attraction": 0.20, "flatness": 0.42, "start_radius": 0.22,
                                 "split_proba": 0.03, "resolution": 1.2, "randomness": 0.55, "crown_shape": "Cylindrical"}},
    "conifer": {"preset": "PINE", "seed": 517, "height": 10.5, "radial": 6,
                "leaf_scale": 1.8, "max_radius": 0.075, "densities": [100.0, 24.0],
                "branch_density": 2.2, "split_probability": 0.02,
                "bark_budget": [2300, 750], "texture": "fir_twig_cc0.png", "alpha": "fir_twig_alpha_cc0.png",
                "bark": "pine_bark_cc0.jpg", "uv": [0.185, 0.455, 0.695, 0.985], "card_width": 0.93,
                "leaf_color": [0.035, 0.32, 0.145, 1.0],
                "trunk_params": {"length": 11.5, "start_radius": 0.31, "end_radius": 0.013, "shape": 1.0, "up_attraction": 0.98, "randomness": 0.70},
                "branch_params": {"start": 0.15, "end": 0.99, "length": 4.8, "start_angle": 82.0,
                                  "gravity_strength": 4.0, "stiffness": 0.45, "up_attraction": 0.04,
                                  "randomness": 0.50, "flatness": 0.85, "start_radius": 0.27,
                                  "crown_shape": "Conical", "crown_base_size": 0.12, "crown_height": 11.5, "crown_angle_variation": -18.0},
                "secondary_params": {"start": 0.18, "end": 0.97, "length": 0.95, "branches_density": 1.5,
                                     "start_angle": 49.0, "gravity_strength": 2.2, "stiffness": 0.4,
                                     "up_attraction": 0.05, "flatness": 0.9, "start_radius": 0.18,
                                     "split_proba": 0.01, "resolution": 1.2, "randomness": 0.48, "crown_shape": "Cylindrical"}},
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_engine():
    archive = CACHE / "modular_tree-5.5.2-windows_x64.zip"
    assert sha256(archive) == ARCHIVE_SHA256, "Pinned archive digest mismatch"
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    wheels = list((CACHE / "extension/wheels").glob(f"m_tree-5.5.2-{py_tag}-{py_tag}-win_amd64.whl"))
    assert len(wheels) == 1, f"No pinned Windows wheel for {py_tag}"
    native = CACHE / f"native-{py_tag}"
    native.mkdir(exist_ok=True)
    with zipfile.ZipFile(wheels[0]) as package:
        for item in package.infolist():
            target = (native / item.filename).resolve()
            assert target.is_relative_to(native.resolve()), "Unsafe wheel member"
        package.extractall(native)
    sys.path.insert(0, str(native))
    spec = importlib.util.spec_from_file_location(
        "modular_tree_isolated", CACHE / "extension/__init__.py",
        submodule_search_locations=[str(CACHE / "extension")],
    )
    addon = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = addon
    spec.loader.exec_module(addon)
    addon.register()
    from m_tree import m_tree as core
    return addon, core, wheels[0]


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def active(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def texture_material(name, filename, alpha_filename=None, leaf_color=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (0.16, 0.24, 0.075, 1) if alpha_filename else (0.22, 0.14, 0.075, 1)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.87
    shader.inputs["Specular IOR Level"].default_value = 0.18
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(OUTPUT / "textures" / filename), check_existing=True)
    if leaf_color is None:
        links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    else:
        # Explicit material color balance, preserving the unedited CC0 atlas.
        shader.inputs["Base Color"].default_value = leaf_color
        shader.inputs["Roughness"].default_value = 0.93
        mat.diffuse_color = leaf_color
    if alpha_filename:
        alpha_tex = nodes.new("ShaderNodeTexImage")
        alpha_tex.image = bpy.data.images.load(str(OUTPUT / "textures" / alpha_filename), check_existing=True)
        alpha_tex.image.colorspace_settings.name = "Non-Color"
        clip = nodes.new("ShaderNodeMath")
        clip.operation = "GREATER_THAN"
        clip.inputs[1].default_value = 0.4
        links.new(alpha_tex.outputs["Color"], clip.inputs[0])
        links.new(clip.outputs[0], shader.inputs["Alpha"])
        mat.surface_render_method = "DITHERED"
        mat.use_backface_culling = False
    return mat


def build_native_branches(core, spec, name):
    # This is the upstream QuickGenerateTree native pipeline, with exposed
    # mesher controls instead of the UI shortcut's hardcoded 32 radial points.
    from modular_tree_isolated.python_classes.presets import apply_preset, apply_trunk_preset, apply_sub_branch_preset, TREE_PRESETS
    from modular_tree_isolated.python_classes.presets.tree_presets import _set_branch_param
    from modular_tree_isolated.python_classes.mesh_utils import create_mesh_from_cpp
    tree = core.Tree()
    trunk = core.TrunkFunction()
    trunk.seed = spec["seed"]
    apply_trunk_preset(trunk, spec["preset"])
    trunk.resolution = 1.5
    for key, value in spec.get("trunk_params", {}).items():
        setattr(trunk, key, value)
    branches = core.BranchFunction()
    branches.seed = spec["seed"] + 1
    apply_preset(branches, spec["preset"])
    branches.resolution = 1.2
    branches.distribution.density = spec["branch_density"]
    branches.split.probability = spec["split_probability"]
    for key, value in spec.get("branch_params", {}).items():
        _set_branch_param(branches, key, value)
    preset = TREE_PRESETS[spec["preset"]]
    if preset.sub_branches or spec.get("secondary_params"):
        secondary = core.BranchFunction()
        secondary.seed = spec["seed"] + 2
        apply_sub_branch_preset(secondary, spec["preset"])
        secondary.resolution = 1.0
        secondary.distribution.density = 1.4
        secondary.split.probability = 0.04
        for key, value in spec.get("secondary_params", {}).items():
            _set_branch_param(secondary, key, value)
        branches.add_child(secondary)
    trunk.add_child(branches)
    tree.set_trunk_function(trunk)
    tree.execute_functions()
    mesher = core.ManifoldMesher()
    mesher.radial_n_points = spec["radial"]
    mesher.smooth_iterations = 1
    mesh = bpy.data.meshes.new(name + "_branches_source")
    create_mesh_from_cpp(mesh, mesher.mesh_tree(tree))
    obj = bpy.data.objects.new(name + "_source", mesh)
    bpy.context.collection.objects.link(obj)
    active(obj)
    print("NATIVE_BRANCHES", name, triangle_count(mesh))
    return obj


def leaf_card(spec, name, material):
    # Use the upstream fallback card mesh and author atlas UVs for the CC0
    # photographed foliage. The branching and distribution remain upstream.
    from modular_tree_isolated.python_classes.resources import node_groups
    leaf = node_groups._create_quad_leaf()
    leaf.name = name + "_photographic_foliage_card"
    if spec.get("leaf_mode") == "NATIVE_OAK":
        from modular_tree_isolated.python_classes.m_tree_wrapper import lazy_m_tree
        from modular_tree_isolated.python_classes.presets.leaf_presets import apply_preset_to_generator
        from modular_tree_isolated.python_classes.mesh_utils import create_leaf_mesh_from_cpp
        generator = lazy_m_tree.LeafShapeGenerator()
        apply_preset_to_generator(generator, "OAK")
        generator.seed = spec["seed"]
        generator.contour_resolution = 12
        generator.enable_venation = False
        generator.midrib_curvature = 0
        generator.cross_curvature = 0
        generator.edge_curl = 0
        generator.vein_displacement = 0
        mesh = bpy.data.meshes.new(name + "_native_oak_leaf")
        create_leaf_mesh_from_cpp(mesh, generator.generate())
        leaf.data = mesh
        active(leaf)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.dissolve_limited(angle_limit=0.002)
        bpy.ops.object.mode_set(mode="OBJECT")
        leaf.data.materials.append(material)
        print("NATIVE_LEAF_TRIANGLES", triangle_count(leaf.data))
        return leaf
    for vertex in leaf.data.vertices:
        vertex.co.x *= spec["card_width"]
    u0, u1, v0, v1 = spec["uv"]
    for loop in leaf.data.uv_layers.active.data:
        u, v = loop.uv
        loop.uv = (u0 + (u1-u0)*u, v0 + (v1-v0)*v)
    leaf.data.materials.append(material)
    return leaf


def set_node_input(modifier, name, value):
    socket = next(item for item in modifier.node_group.interface.items_tree
                  if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name)
    # Official 5.2 API migration; no writes to the pinned upstream source.
    getattr(modifier.properties.inputs, socket.identifier).value = value


def attach_source_leaves(obj, card, spec, density, scale_multiplier=1.0):
    from modular_tree_isolated.python_classes.resources import node_groups
    mod = obj.modifiers.new("MTree_source_leaf_distribution", "NODES")
    mod.node_group = node_groups._get_or_create_leaves_node_group().copy()
    for key, value in {"Leaf Object": card, "Density": density,
                       "Max Radius": spec["max_radius"], "Scale": spec["leaf_scale"] * scale_multiplier,
                       "Seed": spec["seed"], "Enable Normal Transfer": False}.items():
        set_node_input(mod, key, value)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    result = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
    assert result and len(result.polygons) > len(obj.data.polygons), "Source leaf distribution produced no leaves"
    obj.modifiers.remove(mod)
    return result


def decimate_budget(obj, budget):
    active(obj)
    count = triangle_count(obj.data)
    if count > budget:
        dec = obj.modifiers.new("candidate_triangle_budget", "DECIMATE")
        dec.ratio = min(1.0, (budget - 4) / count)
        dec.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=dec.name)
    return triangle_count(obj.data)


def split_material_mesh(obj):
    active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="MATERIAL")
    bpy.ops.object.mode_set(mode="OBJECT")
    return list(bpy.context.selected_objects)


def export_objects(objects, path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True, export_animations=False,
                              export_cameras=False, export_lights=False, export_extras=True)


def read_glb(path):
    import struct
    data = Path(path).read_bytes()
    assert data[:4] == b"glTF"
    length, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A
    return json.loads(data[20:20+length])


def review_scene():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 20
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.55, 0.55, 0.55)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.60, 0.68, 0.73, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7
    bpy.ops.object.light_add(type="AREA", location=(6, -8, 13))
    light = bpy.context.object
    light.data.energy = 2600
    light.data.shape = "DISK"
    light.data.size = 7
    light.rotation_euler = (Vector((0, 0, 4))-light.location).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.object.light_add(type="AREA", location=(-7, 4, 10))
    bpy.context.object.data.energy = 1800
    bpy.context.object.data.size = 8
    bpy.context.object.rotation_euler = (Vector((0, 0, 4))-bpy.context.object.location).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.02))
    ground = bpy.context.object
    ground.name = "review_ground_only"
    mat = bpy.data.materials.new("review_warm_ground")
    mat.diffuse_color = (0.18, 0.20, 0.12, 1)
    ground.data.materials.append(mat)
    bpy.ops.object.camera_add()
    scene.camera = bpy.context.object
    scene.view_settings.view_transform = "Standard"
    return scene


def render_review(scene, spec, name, mode):
    camera = scene.camera
    if mode == "near":
        camera.location = (spec["height"]*1.7, -spec["height"]*2.2, spec["height"]*0.82)
        target = Vector((0, 0, spec["height"]*0.5))
        camera.data.lens = 58
    else:
        camera.location = (spec["height"]*1.18, -spec["height"]*1.45, 1.7)
        target = Vector((0, 0, spec["height"]*0.43))
        camera.data.lens = 36
    camera.rotation_euler = (target-camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(OUTPUT / f"{name}_{mode}.png")
    bpy.ops.render.render(write_still=True)


def generate(addon, core, wheel):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    texture_set = {filename: info for filename, info in TEXTURES.items() if (OUTPUT / "textures" / filename).exists()}
    for filename, (_, _, md5) in texture_set.items():
        assert hashlib.md5((OUTPUT / "textures" / filename).read_bytes()).hexdigest() == md5, "Texture digest mismatch"
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = review_scene()
    report = {"stage": "candidate_only", "blender": bpy.app.version_string, "generator": "Modular Tree 5.5.2",
              "archive_sha256": ARCHIVE_SHA256, "wheel_sha256": sha256(wheel),
              "source_url": "https://github.com/GoodPie/modular_tree/releases/tag/5.5.2",
              "generator_code_license": {"addon": "GPL-3.0-or-later", "core": "MIT"},
              "original_geometry": "Native MTree seeded trunk/branch engine, source-authored leaf distribution",
              "texture_license": "CC0-1.0", "api_repair": "NodesModifier.properties.inputs.<identifier>.value, Blender 5.2",
              "api_source": "https://developer.blender.org/docs/release_notes/5.2/python_api/",
              "textures": [], "assets": []}
    for filename, (slug, channel, md5) in texture_set.items():
        report["textures"].append({"file": "textures/" + filename, "source": f"https://polyhaven.com/a/{slug}",
                                   "channel": channel, "license_source": "https://polyhaven.com/license",
                                   "upstream_md5": md5, "sha256": sha256(OUTPUT / "textures" / filename)})
    for name, spec in SPECS.items():
        bark = texture_material(name + "_CC0_bark", spec["bark"])
        native_leaf = spec.get("leaf_mode") == "NATIVE_OAK"
        foliage = texture_material(name + "_foliage", spec["texture"], alpha_filename=None if native_leaf else spec["alpha"], leaf_color=spec.get("leaf_color"))
        source = build_native_branches(core, spec, name)
        source.data.materials.append(bark)
        source.hide_render = True
        card = leaf_card(spec, name, foliage)
        minz = min(v.co.z for v in source.data.vertices)
        maxz = max(v.co.z for v in source.data.vertices)
        factor = spec["height"] / (maxz-minz)
        lods = []
        for lod in [0, 1]:
            evaluated = attach_source_leaves(source, card, spec, spec["densities"][lod], 1.0 if lod == 0 else 1.14)
            obj = bpy.data.objects.new(f"{name}_LOD{lod}", evaluated)
            bpy.context.collection.objects.link(obj)
            for vertex in obj.data.vertices:
                vertex.co = Vector((vertex.co.x*factor, vertex.co.y*factor, (vertex.co.z-minz)*factor))
            parts = split_material_mesh(obj)
            leaf_budget = (7800 if lod == 0 else 1950) - spec["bark_budget"][lod]
            piece_counts = {}
            # Allocate the remaining budget after standard branch decimation.
            # Some disconnected thin branches cannot collapse all the way.
            parts.sort(key=lambda p: any(p.data.materials[f.material_index] == foliage for f in p.data.polygons))
            actual_branch_count = 0
            for piece in parts:
                material_ids = set(p.material_index for p in piece.data.polygons)
                is_leaf = any(piece.data.materials[i] == foliage for i in material_ids)
                piece.name = f"{name}_LOD{lod}_" + ("foliage" if is_leaf else "branches")
                budget = max(8, (7800 if lod == 0 else 1950)-actual_branch_count) if is_leaf else spec["bark_budget"][lod]
                print("RAW_PIECE", piece.name, triangle_count(piece.data))
                count = decimate_budget(piece, budget)
                if not is_leaf:
                    actual_branch_count += count
                print("PIECE_BUDGET", piece.name, count, "target", budget)
                piece_counts[piece.name] = count
                piece["generator"] = "Modular Tree 5.5.2"
                piece["seed"] = spec["seed"]
                piece["candidate"] = True
            path = OUTPUT / f"{name}_LOD{lod}.glb"
            export_objects(parts, path)
            glb = read_glb(path)
            glb_triangles = sum(glb["accessors"][prim["indices"]]["count"]//3 for mesh in glb["meshes"] for prim in mesh["primitives"])
            budget_pass = glb_triangles <= (8000 if lod == 0 else 2000)
            mask_materials = [m["name"] for m in glb.get("materials", []) if m.get("alphaMode") == "MASK"]
            if not native_leaf:
                assert mask_materials, "GLB has no alpha mask foliage material"
            report["assets"].append({"name": name, "lod": lod, "file": path.name, "sha256": sha256(path),
                                       "triangles": glb_triangles, "budget_pass": budget_pass, "parts": piece_counts, "height_m": spec["height"],
                                       "origin": [0, 0, 0], "config": spec, "alpha_mask_materials": mask_materials,
                                       "material_count": len(glb.get("materials", [])), "uv_layers": [len(p.data.uv_layers) for p in parts]})
            for piece in parts:
                piece.hide_render = lod != 0
            lods.append(parts)
            print("CANDIDATE_EXPORTED", name, lod, glb_triangles, "triangles")
        for mode in ["near", "player"]:
            render_review(scene, spec, name, mode)
        if "-v2" not in OUTPUT.name:
            active(lods[0][0])
            bpy.ops.file.pack_all()
            bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / f"{name}_candidate.blend"))
        for parts in lods:
            for obj in parts:
                obj.hide_render = True
        source.hide_render = True
    (OUTPUT / "provenance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PROVENANCE", str(OUTPUT / "provenance.json"))


def verify():
    # Verify exported bytes through Blender's independent glTF importer.
    report = json.loads((OUTPUT / "provenance.json").read_text(encoding="utf-8"))
    known_files = {asset["file"] for asset in report["assets"]}
    # A native Blender crash cannot execute Python finalizers. Recover facts
    # only for already-exported candidate bytes, then verify them independently.
    for name, spec in SPECS.items():
        for lod in [0, 1]:
            path = OUTPUT / f"{name}_LOD{lod}.glb"
            if path.exists() and path.name not in known_files:
                document = read_glb(path)
                count = sum(document["accessors"][p["indices"]]["count"]//3 for m in document["meshes"] for p in m["primitives"])
                report["assets"].append({"name": name, "lod": lod, "file": path.name,
                                         "sha256": sha256(path), "triangles": count, "config": spec,
                                         "budget_pass": count <= (8000 if lod == 0 else 2000),
                                         "recovered_after_native_crash": True})
    archive = CACHE / "modular_tree-5.5.2-windows_x64.zip"
    assert sha256(archive) == ARCHIVE_SHA256
    checked_sources = 0
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if member.filename.endswith(".py") or member.filename == "blender_manifest.toml":
                assert (CACHE / "extension" / member.filename).read_bytes() == package.read(member), "Upstream source changed"
                checked_sources += 1
    report["upstream_source_integrity"] = {"pass": True, "checked_original_files": checked_sources}
    report["license_files"] = [{"file": str(p.relative_to(OUTPUT)).replace("\\", "/"), "sha256": sha256(p)}
                               for p in sorted((OUTPUT / "licenses").glob("*.md"))]
    report["output_geometry_license"] = "Project-authored output; no public CC0 dedication"
    (OUTPUT / "provenance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    checks = []
    for asset in report["assets"]:
        path = OUTPUT / asset["file"]
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(path))
        objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        positions = [obj.matrix_world @ vertex.co for obj in objects for vertex in obj.data.vertices]
        bounds = [[min(p[i] for p in positions), max(p[i] for p in positions)] for i in range(3)]
        count = sum(triangle_count(obj.data) for obj in objects)
        assert count == asset["triangles"], "Triangle count changed during GLB import"
        assert len(objects) == 2, "Expected separate branch and foliage meshes"
        assert all(math.isfinite(c) for p in positions for c in p), "Nonfinite geometry"
        assert abs(bounds[2][0]) < 0.015, "Base pivot is not at ground level"
        assert all(obj.location.length < 0.00001 for obj in objects), "Mesh origins moved"
        assert all(len(obj.data.uv_layers) == 1 for obj in objects), "Missing UVs"
        glb = read_glb(path)
        assert all("uri" not in image for image in glb.get("images", [])), "External image dependency"
        native_leaf = asset["config"].get("leaf_mode") == "NATIVE_OAK"
        if not native_leaf:
            assert any(m.get("alphaMode") == "MASK" and m.get("doubleSided") for m in glb["materials"]), "Missing double-sided cutout foliage"
        check = {"file": path.name, "roundtrip": "pass", "triangles": count,
                 "budget_pass": count <= (8000 if asset["lod"] == 0 else 2000),
                 "bounds_blender_xyz_m": bounds, "actual_height_m": bounds[2][1]-bounds[2][0],
                 "mesh_count": len(objects), "origin_pass": True, "uv_pass": True,
                 "embedded_textures": len(glb.get("images", [])), "masked_foliage_pass": True, "solid_native_foliage": native_leaf}
        checks.append(check)
        print("ROUNDTRIP", json.dumps(check))
    (OUTPUT / "verification.json").write_text(json.dumps({"blender": bpy.app.version_string, "checks": checks}, indent=2), encoding="utf-8")


def probe(addon, core, wheel):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    result = bpy.ops.mtree.quick_generate(preset="OAK", seed=101, add_leaves=False)
    obj = bpy.context.active_object
    print("BARE_BRANCH", json.dumps({"result": list(result), "triangles": triangle_count(obj.data), "height": obj.dimensions.z}))
    print("LEAF_GENERATOR_API", [name for name in dir(core.LeafShapeGenerator()) if not name.startswith("_")])
    from modular_tree_isolated.python_classes.resources import node_groups
    group = node_groups._get_or_create_leaves_node_group()
    modifier = obj.modifiers.new("leaves_probe", "NODES")
    modifier.node_group = group
    print("MODIFIER_API", [prop.identifier for prop in modifier.bl_rna.properties])
    print("MODIFIER_METHODS", [name for name in dir(modifier) if "input" in name or "propert" in name])
    # Blender 5.2 release notes: modifier.properties.inputs.<identifier>.value.
    getattr(modifier.properties.inputs, "Socket_1").value = 55.0
    print("INPUT_ASSIGNMENT", getattr(modifier.properties.inputs, "Socket_1").value)
    print("GROUP_INPUTS", [(item.name, getattr(item, "identifier", None), getattr(item, "socket_type", None)) for item in group.interface.items_tree])
    print("PINNED_WHEEL", wheel.name, sha256(wheel))
    from modular_tree_isolated.python_classes.presets.leaf_presets import apply_preset_to_generator
    from modular_tree_isolated.python_classes.mesh_utils import create_leaf_mesh_from_cpp
    for species in ["OAK", "PINE"]:
        generator = core.LeafShapeGenerator()
        apply_preset_to_generator(generator, species)
        generator.contour_resolution = 8
        generator.enable_venation = False
        leaf_mesh = bpy.data.meshes.new("probe_leaf_" + species)
        create_leaf_mesh_from_cpp(leaf_mesh, generator.generate())
        print("LOW_RES_LEAF", species, len(leaf_mesh.vertices), triangle_count(leaf_mesh))


def main():
    global OUTPUT, SPECS
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["probe", "generate", "verify", "art-report"], default="probe")
    parser.add_argument("--variant", choices=["v1", "v2"], default="v1")
    parser.add_argument("--iteration", type=int, choices=[1, 2], default=1)
    parser.add_argument("--species", choices=["all", "oak", "conifer"], default="all")
    parsed = parser.parse_args(args)
    if parsed.variant == "v2":
        OUTPUT = ROOT / "assets/models/tree-engine-candidates/modular-tree-5.5.2-v2"
        SPECS = copy.deepcopy(SPECS_V2)
        if parsed.iteration == 2:
            # Final bounded art adjustment: source-authored atlas cards instead
            # of the oversized native leaf trial, without modifying images.
            SPECS["oak"].pop("leaf_mode", None)
            SPECS["oak"].update({"leaf_scale": 0.46, "densities": [285.0, 70.0],
                                 "uv": [0.056, 0.205, 0.853, 0.956], "card_width": 1.43,
                                 "leaf_color": [0.15, 0.32, 0.055, 1.0]})
            SPECS["conifer"].update({"leaf_color": [0.020, 0.19, 0.095, 1.0], "densities": [95.0, 11.0]})
    if parsed.mode == "verify":
        verify()
        return
    if parsed.mode == "art-report":
        records = []
        for folder in [OUTPUT, OUTPUT / "round1-failed"]:
            for path in sorted(folder.glob("*.glb")):
                document = read_glb(path)
                count = sum(document["accessors"][p["indices"]]["count"]//3 for m in document["meshes"] for p in m["primitives"])
                bpy.ops.object.select_all(action="SELECT")
                bpy.ops.object.delete(use_global=False)
                bpy.ops.import_scene.gltf(filepath=str(path))
                imported = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
                coordinates = [obj.matrix_world @ vertex.co for obj in imported for vertex in obj.data.vertices]
                bounds = [[min(p[i] for p in coordinates), max(p[i] for p in coordinates)] for i in range(3)]
                assert sum(triangle_count(obj.data) for obj in imported) == count
                assert all(math.isfinite(c) for p in coordinates for c in p)
                records.append({"file": str(path.relative_to(OUTPUT)), "sha256": sha256(path), "triangles": count,
                                "budget_pass": count <= (8000 if "LOD0" in path.name else 2000),
                                "roundtrip": "pass", "bounds_blender_xyz_m": bounds,
                                "origin_pass": all(obj.location.length < 0.00001 for obj in imported),
                                "uv_pass": all(len(obj.data.uv_layers) == 1 for obj in imported),
                                "materials": [{"name": m.get("name"), "alpha_mode": m.get("alphaMode", "OPAQUE")} for m in document.get("materials", [])]})
        texture_records = [{"file": str(path.relative_to(OUTPUT)), "sha256": sha256(path),
                            "source": f"https://polyhaven.com/a/{TEXTURES[path.name][0]}", "license": "CC0-1.0",
                            "upstream_md5": TEXTURES[path.name][2]}
                           for path in sorted((OUTPUT / "textures").iterdir()) if path.name in TEXTURES]
        summary = {"status": "rejected_art_candidates", "admit": False, "generator": "Modular Tree 5.5.2",
                   "blender": bpy.app.version_string, "archive_sha256": ARCHIVE_SHA256,
                   "art_parameter_iterations": 2, "v1_preserved": True, "final_parameters": SPECS,
                   "best_available": "round1-failed/oak_LOD0.glb",
                   "best_render": "round1-failed/oak_player.png",
                   "best_gap": "Fuller crown, but oversized jagged native leaves miss the rounded lush reference",
                   "round2_oak_gap": "Atlas leaves still expose tiered claw-like limbs and weak upper crown",
                   "conifer_blocker": "Blender EXCEPTION_ACCESS_VIOLATION before branch-generation receipt, also reproduced once in isolated conifer process with unchanged final parameters",
                   "logs": ["generation.log", "conifer_generation.log", "round1-failed/generation.log"],
                   "exported_bytes": records, "cc0_inputs": texture_records,
                   "generator_source": "https://github.com/GoodPie/modular_tree/releases/tag/5.5.2",
                   "source_licenses": {"addon": "GPL-3.0-or-later", "core": "MIT"},
                   "output_geometry": "Project-authored generated output; no public CC0 dedication"}
        (OUTPUT / "art-evaluation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("ART_EVALUATION", str(OUTPUT / "art-evaluation.json"))
        return
    if parsed.mode == "generate" and parsed.variant == "v2":
        raise RuntimeError("V2 art evaluation stopped after two parameter iterations: final conifer parameters crash the pinned native engine. Review archived bytes; do not regenerate or admit these variants.")
    if parsed.species != "all":
        SPECS = {parsed.species: SPECS[parsed.species]}
    addon, core, wheel = load_engine()
    if parsed.mode == "probe":
        probe(addon, core, wheel)
    else:
        generate(addon, core, wheel)


if __name__ == "__main__":
    main()
