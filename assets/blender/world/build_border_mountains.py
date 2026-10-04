"""Build a connected mountain backdrop outside the canonical +/-308 m square.

Run with Blender in background mode and --python pointing to this file.
Only assets/models/world-v3/border-mountains is written. Eight square-perimeter
chunks share all corner/side seams. Rock and grass are disjoint face partitions,
not coplanar overlays. The geometry-only GLB stores canonical Y-up world-space
positions at identity node transforms; the review ground/cameras stay excluded.
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
OUTPUT = ROOT / "assets" / "models" / "world-v3" / "border-mountains"
KIT_SOURCE = ROOT / "assets" / "blender" / "city_r5" / "lib" / "citykit.py"
sys.path.insert(0, str(KIT_SOURCE.parent))
import citykit as C  # noqa: E402

WORLD_HALF = 308.0
INNER_HALF = 326.0
DEPTH = 364.0
ALONG_SEGMENTS = 48
RADIAL_SEGMENTS = 28
UV_METRES = 18.0
SEED = 73062491
HEIGHT_SCALE = 1.0
CHUNKS = ("east_north", "north_east", "north_west", "west_north",
          "west_south", "south_west", "south_east", "east_south")
STONE_ROOT = ROOT / "assets" / "models" / "reference-city" / "r5" / "textures"
GRANITE_SOURCE = ROOT / "assets" / "models" / "world-v3" / "textures" / "cliff_granite_albedo_source.png"
STONE_ALBEDO = STONE_ROOT / "stone_foundation_albedo.png"
STONE_NORMAL = STONE_ROOT / "stone_foundation_normal.png"
GRASS_ALBEDO = ROOT / "assets" / "models" / "world-v2" / "textures" / "grass_meadow_v2_source.png"


def _hash_value(x, z, salt):
    value = ((x * 73856093) ^ (z * 19349663) ^ (SEED + salt * 83492791)) & 0xFFFFFFFF
    value ^= value >> 13
    value = (value * 1274126177) & 0xFFFFFFFF
    value ^= value >> 16
    return value / 2147483647.5 - 1.0


def _smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _noise(x, z, scale, salt):
    x, z = x / scale, z / scale
    ix, iz = math.floor(x), math.floor(z)
    u, v = _smooth(x - ix), _smooth(z - iz)
    a = _hash_value(ix, iz, salt) * (1.0 - u) + _hash_value(ix + 1, iz, salt) * u
    b = _hash_value(ix, iz + 1, salt) * (1.0 - u) + _hash_value(ix + 1, iz + 1, salt) * u
    return a * (1.0 - v) + b * v


def _periodic(perimeter, cycles, salt):
    coordinate = (perimeter % 8.0) * cycles / 8.0
    index = math.floor(coordinate)
    fraction = _smooth(coordinate - index)
    return (_hash_value(index % cycles, 0, salt) * (1.0 - fraction)
            + _hash_value((index + 1) % cycles, 0, salt) * fraction)


def _square_direction(perimeter):
    perimeter %= 8.0
    sector = int(perimeter)
    fraction = perimeter - sector
    return ((1.0, fraction), (1.0 - fraction, 1.0), (-fraction, 1.0),
            (-1.0, 1.0 - fraction), (-1.0, -fraction), (fraction - 1.0, -1.0),
            (fraction, -1.0), (1.0, fraction - 1.0))[sector]


def _perimeter_at(x, z):
    radius = max(abs(x), abs(z))
    if abs(x) >= abs(z):
        if x >= 0:
            return z / radius if z >= 0 else 8.0 + z / radius
        return 4.0 - z / radius
    return 2.0 - x / radius if z >= 0 else 6.0 + x / radius


def _inner_radius(perimeter):
    return INNER_HALF + 12.0 * (1.0 + _periodic(perimeter, 17, 2))


def _depth_scale(perimeter):
    return 1.0 + 0.035 * _periodic(perimeter, 9, 4)


def _world_xz(perimeter, depth):
    east, north = _square_direction(perimeter)
    radius = _inner_radius(perimeter) + depth * _depth_scale(perimeter)
    return east * radius, north * radius


def _ridge_parameters(perimeter):
    front_center = 51.0 + 24.0 * _periodic(perimeter, 11, 13) + 12.0 * _periodic(perimeter, 29, 15)
    middle_center = max(front_center + 50.0,
                        122.0 + 34.0 * _periodic(perimeter, 7, 23) + 16.0 * _periodic(perimeter, 19, 25))
    back_center = max(middle_center + 52.0,
                     207.0 + 36.0 * _periodic(perimeter, 5, 33) + 17.0 * _periodic(perimeter, 17, 35))
    front = (50.0 + 14.0 * _periodic(perimeter, 11, 11), front_center,
             36.0 + 12.0 * _periodic(perimeter, 13, 14))
    middle = (77.0 + 14.0 * _periodic(perimeter, 13, 21), middle_center,
              47.0 + 15.0 * _periodic(perimeter, 7, 24))
    back = (97.0 + 16.0 * _periodic(perimeter, 9, 31), back_center,
            63.0 + 18.0 * _periodic(perimeter, 11, 34))
    return front, middle, back


def _soft_max(first, second):
    return (first + second + math.sqrt((first - second) ** 2 + 36.0)) * 0.5


def _height_raw(x, z):
    perimeter = _perimeter_at(x, z)
    depth = (max(abs(x), abs(z)) - _inner_radius(perimeter)) / _depth_scale(perimeter)
    if depth < 0.0 or depth > DEPTH:
        return 0.25
    # The toe obeys the square, while higher ridge courses curve around its
    # corners. This avoids three nested rectangular crests and uniform waves.
    corner_distance = math.hypot(x, z) - max(abs(x), abs(z))
    band_depths = (depth, depth + corner_distance * 0.44, depth + corner_distance * 0.66)
    bands = [amplitude * math.exp(-abs((band_depth - center) / width) ** 1.65)
             for band_depth, (amplitude, center, width) in zip(band_depths, _ridge_parameters(perimeter))]
    ridge = _soft_max(_soft_max(bands[0], bands[1]), bands[2])
    # Winding channels run across the ridge bands. Their perimeter phase warps
    # with depth/world noise instead of repeating uniform radial waves.
    warped = perimeter + depth * 0.00068 + _noise(x, z, 105.0, 51) * 0.045
    channel = max(0.0, 1.0 - abs(_periodic(warped, 53, 52)) / 0.16)
    erosion = channel ** 1.35 * 13.0 * _smooth(ridge / 45.0)
    shoulders = _noise(x, z, 87.0, 61) * 4.0 + _noise(x + z * 0.23, z - x * 0.18, 31.0, 62) * 3.1
    outcrop = max(0.0, _noise(x - z * 0.34, z + x * 0.12, 23.0, 63)) ** 2 * 5.0
    ramp = _smooth(depth / 22.0) * (1.0 - _smooth((depth - 305.0) / (DEPTH - 305.0)))
    return 0.25 + max(0.0, ridge - erosion + shoulders + outcrop) * ramp


def _height(x, z):
    return _height_raw(x, z) * HEIGHT_SCALE


def _normal(x, z):
    step = 1.25
    dx = (_height(x + step, z) - _height(x - step, z)) / (2.0 * step)
    dz = (_height(x, z + step) - _height(x, z - step)) / (2.0 * step)
    return Vector((-dx, dz, 1.0)).normalized()  # Blender Y = -world Z.


def _vertex_color(x, z, height, normal, grass):
    macro = _noise(x, z, 92.0, 71) * 0.055
    exposure = 1.0 - normal.z
    if grass:
        return (0.77 + macro - exposure * 0.10,
                0.87 + macro - height * 0.0008,
                0.72 + macro - exposure * 0.06, 1.0)
    weather = min(1.0, height / 110.0)
    return (0.85 - weather * 0.10 + macro - exposure * 0.055,
            0.85 - weather * 0.075 + macro - exposure * 0.04,
            0.83 - weather * 0.035 + macro - exposure * 0.025, 1.0)


def _texture(nodes, path, colorspace, uv):
    node = nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(path), check_existing=True)
    node.image.colorspace_settings.name = colorspace
    node.extension = "REPEAT"
    nodes.id_data.links.new(uv.outputs["UV"], node.inputs["Vector"])
    return node


def _materials():
    rock_source = GRANITE_SOURCE if GRANITE_SOURCE.is_file() else STONE_ALBEDO
    for name, source, roughness in (("world_border_mountain_rock", rock_source, 0.96),
                                    ("world_border_mountain_grass", GRASS_ALBEDO, 0.98)):
        C.define_material(name, tile=UV_METRES, color=(1.0, 1.0, 1.0), rough=roughness)
        material = C.get_material(name)
        nodes, links = material.node_tree.nodes, material.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        uv = next(node for node in nodes if node.type == "UVMAP")
        multiplier = next(node for node in nodes if node.type == "MIX" and node.blend_type == "MULTIPLY")
        albedo = _texture(nodes, source, "sRGB", uv)
        links.new(albedo.outputs["Color"], multiplier.inputs["A"])
        geometry = nodes.new("ShaderNodeNewGeometry")
        macro = nodes.new("ShaderNodeTexNoise")
        macro.inputs["Scale"].default_value = 0.011
        macro.inputs["Detail"].default_value = 3.0
        links.new(geometry.outputs["Position"], macro.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.43, 0.50, 0.45, 1.0)
        ramp.color_ramp.elements[1].color = (1.0, 0.98, 0.92, 1.0)
        links.new(macro.outputs["Fac"], ramp.inputs["Fac"])
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 0.42
        links.new(multiplier.outputs["Result"], mix.inputs[1])
        links.new(ramp.outputs["Color"], mix.inputs[2])
        links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
        if name.endswith("_rock"):
            normal_texture = _texture(nodes, STONE_NORMAL, "Non-Color", uv)
            normal_map = nodes.new("ShaderNodeNormalMap")
            normal_map.inputs["Strength"].default_value = 0.12
            links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
            grain = nodes.new("ShaderNodeTexNoise")
            grain.inputs["Scale"].default_value = 0.44
            grain.inputs["Detail"].default_value = 2.0
            links.new(geometry.outputs["Position"], grain.inputs["Vector"])
            bump = nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = 0.20
            bump.inputs["Distance"].default_value = 0.18
            links.new(normal_map.outputs["Normal"], bump.inputs["Normal"])
            links.new(grain.outputs["Fac"], bump.inputs["Height"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return {"rock_albedo": rock_source, "rock_normal": STONE_NORMAL, "grass_albedo": GRASS_ALBEDO}


def _mesh_object(name, vertices, normals, faces, grass, collection):
    used = sorted({index for face in faces for index in face})
    remap = {original: index for index, original in enumerate(used)}
    material = "world_border_mountain_grass" if grass else "world_border_mountain_rock"
    obj = C.new_object(name, [vertices[index] for index in used],
                       [tuple(remap[index] for index in face) for face in faces], material, collection)
    mesh = obj.data
    uv = mesh.uv_layers.new(name="UVMap")
    color = mesh.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
    for loop in mesh.loops:
        original = used[loop.vertex_index]
        x, blender_y, height = vertices[original]
        uv.data[loop.index].uv = (x / UV_METRES, -blender_y / UV_METRES)
        color.data[loop.index].color = _vertex_color(x, -blender_y, height, normals[original], grass)
    mesh.color_attributes.active_color = color
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.update()
    mesh.normals_split_custom_set([tuple(normals[used[loop.vertex_index]]) for loop in mesh.loops])
    obj["border_ring_seed"] = SEED
    obj["terrain_role"] = "grass" if grass else "rock"
    return obj


def _geometry():
    global HEIGHT_SCALE
    samples = [_height_raw(*_world_xz(column / ALONG_SEGMENTS, row * DEPTH / RADIAL_SEGMENTS))
               for column in range(len(CHUNKS) * ALONG_SEGMENTS + 1) for row in range(RADIAL_SEGMENTS + 1)]
    HEIGHT_SCALE = min(1.0, 113.5 / max(samples))  # Scale all heights, never clip summit vertices.
    collection = C.collection("SOURCE border mountain ring")
    objects, seams, records = [], [], []
    for chunk_index, cardinal in enumerate(CHUNKS):
        vertices, normals = [], []
        for column in range(ALONG_SEGMENTS + 1):
            perimeter = chunk_index + column / ALONG_SEGMENTS
            for row in range(RADIAL_SEGMENTS + 1):
                x, z = _world_xz(perimeter, row * DEPTH / RADIAL_SEGMENTS)
                vertices.append((x, -z, _height(x, z)))
                normals.append(_normal(x, z))
        rock_faces, grass_faces = [], []
        stride = RADIAL_SEGMENTS + 1
        for column in range(ALONG_SEGMENTS):
            for row in range(RADIAL_SEGMENTS):
                a = column * stride + row
                b, c, d = a + stride, a + stride + 1, a + 1
                triangles = ((a, b, c), (a, c, d)) if (column + row) % 2 == 0 else ((a, b, d), (b, c, d))
                for face in triangles:
                    x = sum(vertices[index][0] for index in face) / 3.0
                    z = -sum(vertices[index][1] for index in face) / 3.0
                    height = sum(vertices[index][2] for index in face) / 3.0
                    normal_z = sum(normals[index].z for index in face) / 3.0
                    grass = height < 28.0 and normal_z > 0.96 and _noise(x, z, 77.0, 82) > 0.30
                    (grass_faces if grass else rock_faces).append(face)
        for role, faces in (("rock", rock_faces), ("grass", grass_faces)):
            if faces:
                objects.append(_mesh_object(f"border_mountains_{cardinal}_{role}", vertices, normals,
                                            faces, role == "grass", collection))
        seams.append(([vertices[index] for index in range(stride)],
                      [vertices[ALONG_SEGMENTS * stride + index] for index in range(stride)],
                      [normals[index] for index in range(stride)],
                      [normals[ALONG_SEGMENTS * stride + index] for index in range(stride)]))
        records.append({"chunk": cardinal, "rock_triangles": len(rock_faces), "grass_triangles": len(grass_faces)})
    maximum_seam_error = 0.0
    for index, seam in enumerate(seams):
        following = seams[(index + 1) % len(seams)]
        for first, second in zip(seam[1], following[0]):
            maximum_seam_error = max(maximum_seam_error, (Vector(first) - Vector(second)).length)
        for first, second in zip(seam[3], following[2]):
            if (first - second).length > 1e-7:
                raise RuntimeError("Mountain chunk normal seam differs")
    if maximum_seam_error > 1e-7:
        raise RuntimeError("Mountain chunk position seam differs")
    return objects, records, maximum_seam_error


def _export(objects, path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
        export_yup=True, export_apply=True, export_materials="NONE", export_vertex_color="NAME",
        export_vertex_color_name="Col", export_texcoords=True, export_normals=True,
        export_cameras=False, export_lights=False, export_animations=False, export_extras=False,
        export_draco_mesh_compression_enable=False)


def _glb(path):
    payload = path.read_bytes()
    magic, version, byte_length = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or byte_length != len(payload):
        raise RuntimeError("Invalid mountain GLB")
    document, binary, offset = None, None, 12
    while offset < len(payload):
        length, kind = struct.unpack_from("<II", payload, offset)
        chunk = payload[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        offset += length + 8
    return document, binary


def _accessor(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    code, size, maximum = {5121: ("B", 1, 255), 5123: ("H", 2, 65535),
                           5125: ("I", 4, 4294967295), 5126: ("f", 4, None)}[accessor["componentType"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", size * components)
    for row in range(accessor["count"]):
        values = struct.unpack_from("<" + code * components, binary, offset + row * stride)
        if accessor.get("normalized") and maximum:
            values = tuple(value / maximum for value in values)
        yield values


def _validate(objects, path, seam_error):
    document, binary = _glb(path)
    if path.stat().st_size > 1_500_000:
        raise RuntimeError("Mountain source GLB exceeds the 1.5 MB budget")
    if any(document.get(key) for key in ("materials", "images", "textures", "cameras", "animations", "skins")):
        raise RuntimeError("Mountain export contains a nongeometry payload")
    expected = {obj.name for obj in objects}
    if {node["name"] for node in document["nodes"]} != expected:
        raise RuntimeError("Mountain export includes review objects or misses source chunks")
    positions, triangle_count, mesh_records = [], 0, []
    for node in document["nodes"]:
        if any(node.get(key) for key in ("matrix", "rotation")) or any(abs(value) > 1e-7 for value in node.get("translation", (0, 0, 0))):
            raise RuntimeError("Mountain chunk transform is not identity")
        if node.get("scale", [1, 1, 1]) != [1, 1, 1]:
            raise RuntimeError("Mountain chunk scale is not identity")
        mesh = document["meshes"][node["mesh"]]
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            if set(attributes) != {"POSITION", "NORMAL", "TEXCOORD_0", "COLOR_0"} or primitive.get("mode", 4) != 4:
                raise RuntimeError("Mountain export attribute contract differs")
            vertices = list(_accessor(document, binary, attributes["POSITION"]))
            normals = list(_accessor(document, binary, attributes["NORMAL"]))
            uvs = list(_accessor(document, binary, attributes["TEXCOORD_0"]))
            colors = list(_accessor(document, binary, attributes["COLOR_0"]))
            indices = list(_accessor(document, binary, primitive["indices"]))
            if len({len(vertices), len(normals), len(uvs), len(colors)}) != 1:
                raise RuntimeError("Mountain attributes have different vertex counts")
            if not all(math.isfinite(value) for values in vertices + normals + uvs + colors for value in values):
                raise RuntimeError("Nonfinite mountain vertex attribute")
            if not all(abs(sum(value * value for value in normal) - 1.0) < 1e-4 for normal in normals):
                raise RuntimeError("Mountain normals are not unit length")
            if any(abs(x) < WORLD_HALF and abs(z) < WORLD_HALF for x, _, z in vertices):
                raise RuntimeError("Mountain vertex intrudes into the playable square")
            if min(max(abs(x), abs(z)) for x, _, z in vertices) < INNER_HALF - 1e-4:
                raise RuntimeError("Mountain toe enters its inner safety boundary")
            if len(indices) % 3 or any(index[0] >= len(vertices) for index in indices):
                raise RuntimeError("Mountain triangle indices are invalid")
            count = len(indices) // 3
            triangle_count += count
            positions.extend(vertices)
            mesh_records.append({"name": node["name"], "vertices": len(vertices), "triangles": count,
                                 "attributes": sorted(attributes)})
    if triangle_count > 24_000 or triangle_count != 8 * ALONG_SEGMENTS * RADIAL_SEGMENTS * 2:
        raise RuntimeError("Mountain triangle budget/count differs")
    for obj in objects:
        obj.data.calc_loop_triangles()
        if any(triangle.area <= 1e-8 for triangle in obj.data.loop_triangles):
            raise RuntimeError("Degenerate mountain triangle")
        # Each entire triangle must occupy one exterior square half-space.
        # This proves the face cannot cut through a square corner, not merely
        # that its vertices happen to lie outside the playable area.
        for triangle in obj.data.loop_triangles:
            points = [obj.data.vertices[index].co for index in triangle.vertices]
            if not any((all(point.x >= INNER_HALF - 1e-4 for point in points),
                        all(point.x <= -INNER_HALF + 1e-4 for point in points),
                        all(point.y >= INNER_HALF - 1e-4 for point in points),
                        all(point.y <= -INNER_HALF + 1e-4 for point in points))):
                raise RuntimeError("Mountain triangle does not lie wholly outside the safety square")
            for weights in ((1/3, 1/3, 1/3), (.5, .5, 0), (.5, 0, .5), (0, .5, .5)):
                point = sum((points[index] * weights[index] for index in range(3)), Vector())
                if max(abs(point.x), abs(point.y)) < INNER_HALF - 1e-4:
                    raise RuntimeError("Mountain triangle interior intrudes into the safety square")
    return {"status": "PASS", "source_triangles": triangle_count, "mesh_count": len(mesh_records),
            "bytes": path.stat().st_size, "inner_square_half_extent_m": INNER_HALF,
            "minimum_vertex_square_radius_m": round(min(max(abs(x), abs(z)) for x, _, z in positions), 6),
            "no_vertices_inside_playable_square": True, "triangle_halfspaces_outside_safety_square": True,
            "sampled_triangle_interiors_outside_safety_square": True,
            "identity_nodes": True, "geometry_only": True, "seam_position_error_m": seam_error,
            "bounds_yup_m": {"min": [round(min(point[axis] for point in positions), 6) for axis in range(3)],
                              "max": [round(max(point[axis] for point in positions), 6) for axis in range(3)]},
            "meshes": mesh_records}


def _review(objects, material_sources):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("Border mountain soft sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.44, 0.57, 0.72, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.42
    scene.world = world
    light_data = bpy.data.lights.new("Border mountain sun", "SUN")
    light_data.energy = 2.25
    light_data.angle = math.radians(5.0)
    light = bpy.data.objects.new(light_data.name, light_data)
    light.rotation_euler = (math.radians(31), math.radians(-22), math.radians(-27))
    scene.collection.objects.link(light)
    context = C.collection("REVIEW ground - excluded from GLB")
    ground = C.new_object("REVIEW canonical map context", [(-INNER_HALF, -INNER_HALF, 0),
              (INNER_HALF, -INNER_HALF, 0), (INNER_HALF, INNER_HALF, 0), (-INNER_HALF, INNER_HALF, 0)],
              [(0, 1, 2, 3)], "world_border_mountain_grass", context)
    C.uv_box(ground, tile_m=UV_METRES)
    C.ensure_white_vertex_colors(ground)
    cameras = []
    sun_data = bpy.data.cameras.new("Sunmeadow-facing mountain review")
    sun_data.lens = 31.0
    sun_data.clip_end = 3000.0
    sun_camera = bpy.data.objects.new(sun_data.name, sun_data)
    sun_camera.location = (-18.0, 102.0, 5.2)  # world X=-18,Z=-102, looking south.
    sun_target = Vector((-12.0, 480.0, 56.0))
    sun_camera.rotation_euler = (sun_target - sun_camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(sun_camera)
    cameras.append((sun_camera, OUTPUT / "review_sunmeadow.png"))
    elevated_data = bpy.data.cameras.new("Elevated mountain ring review")
    elevated_data.type = "ORTHO"
    elevated_data.clip_end = 6000.0
    elevated = bpy.data.objects.new(elevated_data.name, elevated_data)
    elevated.location = (-1120.0, -1350.0, 1390.0)
    elevated.rotation_euler = (Vector((0.0, 0.0, 45.0)) - elevated.location).to_track_quat("-Z", "Y").to_euler()
    camera_rotation = elevated.rotation_euler.to_matrix()
    right, up = camera_rotation @ Vector((1, 0, 0)), camera_rotation @ Vector((0, 1, 0))
    points = [obj.matrix_world @ vertex.co for obj in objects for vertex in obj.data.vertices]
    width = max(point.dot(right) for point in points) - min(point.dot(right) for point in points)
    height = max(point.dot(up) for point in points) - min(point.dot(up) for point in points)
    aspect = scene.render.resolution_x / scene.render.resolution_y
    elevated_data.ortho_scale = max(width, height * aspect) * 1.10
    scene.collection.objects.link(elevated)
    cameras.append((elevated, OUTPUT / "review_elevated.png"))
    for camera, destination in cameras:
        scene.camera = camera
        scene.render.filepath = str(destination)
        bpy.ops.render.render(write_still=True)
    scene.camera = sun_camera
    scene.render.filepath = str(cameras[0][1])
    return [path for _, path in cameras]


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    global SEED
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    arguments = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    SEED = arguments.seed
    OUTPUT.mkdir(parents=True, exist_ok=True)
    C.reset_scene()
    C.TEX_DIR = STONE_ROOT
    material_sources = _materials()
    objects, chunks, seam_error = _geometry()
    glb_path = OUTPUT / "source.glb"
    master_path = OUTPUT / "border-mountains.blend"
    _export(objects, glb_path)
    validation = _validate(objects, glb_path, seam_error)
    print("BORDER_MOUNTAINS_GEOMETRY_AUDIT " + json.dumps({"status": "PASS", "source": str(glb_path),
          "triangles": validation["source_triangles"], "meshes": validation["mesh_count"],
          "bytes": validation["bytes"], "minimum_square_radius_m": validation["minimum_vertex_square_radius_m"],
          "source_sha256": _sha256(glb_path)}), flush=True)
    renders = _review(objects, material_sources)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(master_path))
    sources = [Path(__file__).resolve(), KIT_SOURCE, *material_sources.values()]
    manifest = {"schema": "aetherfield.border-mountains/1", "generator": "Blender " + bpy.app.version_string,
                "seed": SEED, "height_scale": HEIGHT_SCALE,
                "coordinate_system": "canonical world XYZ, glTF Y-up metres, identity node transforms",
                "topology": "8 connected half-side chunks; disjoint rock/grass face partitions; 3 warped broad ridge bands with radial erosion channels",
                "grid": {"along_segments_per_chunk": ALONG_SEGMENTS, "radial_segments": RADIAL_SEGMENTS,
                         "radial_depth_m": DEPTH, "world_uv_metres_per_repeat": UV_METRES},
                "chunks": chunks, "validation": validation,
                "runtime_material_contract": {"_rock": "parent shared PBR granite + world-space macro variation",
                                              "_grass": "parent shared botanical/meadow PBR material",
                                              "COLOR_0": "muted height/slope/macro tint, opaque; source attribute Col"},
                "sources": [{"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)} for path in sources],
                "outputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path), "bytes": path.stat().st_size}
                            for path in [glb_path, master_path, *renders]],
                "review_limits": ["Review ground is context only and excluded from the runtime GLB; the off-map safety buffer still needs parent ground/haze integration.",
                                  "Granite albedo is preferred; legacy stone normal at strength0.12 is provisional microdetail, not a matched granite bake.",
                                  "Blender procedural grain/macro shader is review-only; geometry-only export carries UVs, normals and muted Col tint.",
                                  "Standalone cameras omit runtime fog, clouds and native lighting; parent owns Meshopt, loader and 360-degree native QA."],
                "admission": {"meshopt": "pending parent integration", "native_qa": "pending parent integration"}}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("BORDER_MOUNTAINS_BUILD " + json.dumps({"status": "PASS", "triangles": validation["source_triangles"],
        "meshes": validation["mesh_count"], "bytes": validation["bytes"], "bounds_yup_m": validation["bounds_yup_m"],
        "minimum_square_radius_m": validation["minimum_vertex_square_radius_m"], "source_sha256": _sha256(glb_path)}), flush=True)


if __name__ == "__main__":
    main()
