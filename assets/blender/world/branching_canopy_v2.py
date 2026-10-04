"""Deterministic, open-crowned Sunmeadow trees for the shared foundry kit.

Call ``build_branching_trees(props, collection, citykit)`` from the cell builder.
Geometry is authored in metres and transformed from source X/Z/yaw once. Each
tree has two curved main forks, eight secondary branches at varied heights,
sixteen rising/drooping terminal twigs and 126 bent leaf cards. Sprays follow
those paths through several crown levels; no closed mesh fills the crown.
The two comparison trees
keep their existing ``_hero_fallback_<prop id>`` material names.

The current profile costs 1,950 source triangles per tree: 942 for the trunk,
roots and branches, and 1,008 for foliage. Cards rely on the runtime's existing
two-sided alpha-test material. Review at the actual oblique gameplay camera:
an overhead silhouette alone cannot reveal edge-on cards or open branch gaps.
"""

from __future__ import annotations

import math
import random
import zlib
from pathlib import Path

import bpy
from mathutils import Vector


_HERO_FALLBACK_IDS = {"sunmeadow_pine_west_mid", "sunmeadow_oak_east"}
_UP = Vector((0.0, 0.0, 1.0))
_WALK_HEIGHT = 2.2
_SAFE_RING_HEIGHT = 2.45
LEAF_CARD_COUNT = 126
WOOD_TRIANGLE_COUNT = 942
LEAF_TRIANGLE_COUNT = LEAF_CARD_COUNT * 8
TREE_TRIANGLE_COUNT = WOOD_TRIANGLE_COUNT + LEAF_TRIANGLE_COUNT


class _Mesh:
    def __init__(self):
        self.verts = []
        self.faces = []
        self.uvs = []

    def face(self, indices, uvs):
        self.faces.append(tuple(indices))
        self.uvs.extend(uvs)


def _polar(angle, radius, height=0.0):
    return Vector((math.cos(angle) * radius, math.sin(angle) * radius, height))


def _wood_point(point, blocker_radius):
    """Keep low solid geometry strictly inside the existing walking blocker."""
    point = point.copy()
    point.z = max(0.005, point.z)
    if point.z <= _SAFE_RING_HEIGHT:
        radial = math.hypot(point.x, point.y)
        limit = blocker_radius * 0.985
        if radial > limit:
            point.x *= limit / radial
            point.y *= limit / radial
    return point


def _tube(mesh, points, radii, sides, blocker_radius, phase):
    """A tapered, lightly fluted tube with transported rings and unit UVs."""
    points = [Vector(point) for point in points]
    distances = [0.0]
    for first, second in zip(points, points[1:]):
        distances.append(distances[-1] + (second - first).length)
    total = max(distances[-1], 0.001)
    first_vertex = len(mesh.verts)
    right = None
    for index, (point, radius) in enumerate(zip(points, radii)):
        tangent = (points[min(index + 1, len(points) - 1)]
                   - points[max(0, index - 1)]).normalized()
        if right is not None:
            right = right - tangent * right.dot(tangent)
        if right is None or right.length < 0.001:
            reference = Vector((1.0, 0.0, 0.0)) if abs(tangent.z) > 0.9 else _UP
            right = tangent.cross(reference)
        right.normalize()
        across = tangent.cross(right).normalized()
        for side in range(sides):
            angle = side * math.tau / sides
            flute = 1.0 + 0.045 * math.cos(angle * 3.0 + phase)
            offset = (right * math.cos(angle) + across * math.sin(angle)) * radius * flute
            mesh.verts.append(tuple(_wood_point(point + offset, blocker_radius)))

    for ring in range(len(points) - 1):
        low = first_vertex + ring * sides
        high = low + sides
        v0, v1 = distances[ring] / total, distances[ring + 1] / total
        for side in range(sides):
            after = (side + 1) % sides
            u0, u1 = side / sides, (side + 1) / sides
            mesh.face((low + side, low + after, high + after, high + side),
                      ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
    for ring, reverse in ((0, True), (len(points) - 1, False)):
        order = list(range(sides))
        if reverse:
            order.reverse()
        mesh.face([first_vertex + ring * sides + side for side in order],
                  [(0.5 + 0.5 * math.cos(side * math.tau / sides),
                    0.5 + 0.5 * math.sin(side * math.tau / sides)) for side in order])


def _sample_path(points, fraction):
    position = max(0.0, min(1.0, fraction)) * (len(points) - 1)
    index = min(int(position), len(points) - 2)
    return points[index].lerp(points[index + 1], position - index)


def _bent_card(mesh, center, heading, width, length, tilt, roll, bend, height):
    """A nine-vertex folded spray, retaining the alpha texture's complete UVs."""
    direction = _polar(heading, 1.0)
    along = direction * math.cos(tilt) + _UP * math.sin(tilt)
    right = direction.cross(_UP).normalized()
    normal = right.cross(along).normalized()
    right = (right * math.cos(roll) + normal * math.sin(roll)).normalized()
    normal = right.cross(along).normalized()
    offsets = []
    for row in range(3):
        v = row * 0.5
        # Taper the two ends and lift the central vein; the transparent leaf
        # edge, rather than a solid polygon boundary, defines the silhouette.
        end_taper = (0.84, 1.0, 0.78)[row]
        for column in range(3):
            u = column * 0.5
            lateral = (u - 0.5) * width * end_taper
            longitudinal = (v - 0.5) * length
            fold = bend * width * (1.0 - abs(u * 2.0 - 1.0))
            fold -= width * 0.025 * abs(v * 2.0 - 1.0)
            offsets.append(right * lateral + along * longitudinal + normal * fold)
    # Fit the complete folded card by translation (and, only if necessary,
    # uniform reduction). Never flatten individual vertices against a top or
    # bottom plane. Slightly different ceilings keep the upper edge uneven.
    floor = _WALK_HEIGHT + 0.45
    roof = height * (0.976 + 0.018 * (0.5 + 0.5 * math.sin(heading * 1.73 + roll * 2.4)))
    low, high = min(point.z for point in offsets), max(point.z for point in offsets)
    available = roof - floor
    if high - low > available:
        reduction = available * 0.98 / (high - low)
        offsets = [point * reduction for point in offsets]
        low, high = min(point.z for point in offsets), max(point.z for point in offsets)
    center = center.copy()
    center.z = max(floor - low, min(roof - high, center.z))
    first_vertex = len(mesh.verts)
    mesh.verts.extend(tuple(center + point) for point in offsets)
    for row in range(2):
        for column in range(2):
            base = first_vertex + row * 3 + column
            u0, u1 = column * 0.5, (column + 1) * 0.5
            v0, v1 = row * 0.5, (row + 1) * 0.5
            mesh.face((base, base + 1, base + 4, base + 3),
                      ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))


def _spray(mesh, path, height, rng, size_factor=1.0, card_count=6):
    """Five or six small sprays follow one rising or drooping terminal twig."""
    direction = path[-1] - path[0]
    heading = math.atan2(direction.y, direction.x)
    side = _polar(heading + math.pi * 0.5, 1.0)
    fractions = (0.16, 0.33, 0.49, 0.65, 0.81, 1.0) if card_count == 6 else (0.16, 0.37, 0.58, 0.80, 1.0)
    for index, fraction in enumerate(fractions):
        center = _sample_path(path, fraction)
        width = height * rng.uniform(0.125, 0.17) * size_factor
        width *= (1.10, 0.91, 1.06, 0.95, 1.08, 0.83)[index]
        center += side * width * ((-0.23 if index % 2 == 0 else 0.23) + rng.uniform(-0.09, 0.09))
        center.z += height * (-0.045, 0.03, 0.06, -0.025, 0.04, -0.01)[index]
        _bent_card(mesh, center,
                   heading + (-0.40, 0.70, -0.80, 0.25, 0.90, -0.55)[index] + rng.uniform(-0.25, 0.25),
                   width, width * rng.uniform(0.82, 1.10),
                   (1.08, -0.68, 0.52, 1.34, -0.94, 0.24)[index] + rng.uniform(-0.14, 0.14),
                   rng.uniform(-0.80, 0.80), rng.uniform(0.075, 0.13), height)


def _crown_layers(mesh, secondary_paths, primary_paths, height, rng):
    """Interleave inner sprays through the curved forks and secondary paths."""
    for path, heading, secondary_index, scaffold_index in secondary_paths:
        side = _polar(heading + math.pi * 0.5, 1.0)
        mass = (1.04 if scaffold_index == 0 else 0.95) * (0.97, 1.05, 0.96, 1.02)[secondary_index]
        for index, fraction in enumerate((0.24, 0.51, 0.77)):
            center = _sample_path(path, fraction)
            center += side * height * rng.uniform(-0.022, 0.022)
            center.z += height * (0.035, 0.08, -0.02)[index]
            width = height * rng.uniform(0.155, 0.195) * mass
            _bent_card(mesh, center,
                       heading + (-0.55, 0.62, -0.26)[index] + rng.uniform(-0.20, 0.20),
                       width, width * rng.uniform(0.88, 1.12),
                       (0.45, 1.15, -0.70)[index] + rng.uniform(-0.13, 0.13),
                       rng.uniform(-0.70, 0.70), rng.uniform(0.08, 0.14), height)
    for path, heading, scaffold_index in primary_paths:
        for index, fraction in enumerate((0.52, 0.67, 0.81, 0.91, 0.99)):
            center = _sample_path(path, fraction)
            # Inner growth closes the upper gap between the two scaffolds,
            # while lower secondary sprays retain readable branch openings.
            inward = (0.95, 0.40, 0.60, 0.30, 0.78)[index]
            center.x = path[0].x + (center.x - path[0].x) * inward
            center.y = path[0].y + (center.y - path[0].y) * inward
            center.z += height * (0.06, 0.09, 0.06, 0.025, -0.03)[index]
            center += _polar(heading + math.pi * 0.5, height * rng.uniform(-0.018, 0.018))
            width = height * rng.uniform(0.17, 0.21) * (1.07 if scaffold_index == 0 else 0.95)
            _bent_card(mesh, center, heading + (-0.60, 0.46, -0.22, 0.75, -0.42)[index],
                       width, width * rng.uniform(0.93, 1.08),
                       (-0.75, 1.05, 0.40, -0.95, 0.68)[index] + rng.uniform(-0.14, 0.14),
                       rng.uniform(-0.65, 0.65), rng.uniform(0.08, 0.13), height)


def _shared_leaf_material(kit):
    if "world_leaf_cards" not in kit.MATERIALS:
        kit.define_material("world_leaf_cards", tile=1.0, color=(1.0, 1.0, 1.0),
                            rough=0.94, alpha_from_texture=True)
    material = kit.get_material("world_leaf_cards")
    material.use_backface_culling = False
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf.inputs["Alpha"].is_linked:
        return material

    # The foundry names textures by material; the world builder's existing
    # shared cutout is called leaf_canopy_albedo instead. Bind that same image
    # for Blender review without generating, copying or exporting a texture.
    root = Path(__file__).resolve().parents[3]
    candidates = (Path(kit.TEX_DIR) / "leaf_canopy_albedo.png",
                  root / "apps" / "client" / "src" / "assets" / "world" / "leaf_canopy_albedo.png")
    texture_path = next((path for path in candidates if path.is_file()), None)
    if texture_path is None:
        raise FileNotFoundError("The shared leaf_canopy_albedo.png cutout is required for tree review")
    texture = nodes.new("ShaderNodeTexImage")
    texture.name = "Shared world leaf cutout"
    texture.image = bpy.data.images.load(str(texture_path), check_existing=True)
    texture.image.colorspace_settings.name = "sRGB"
    texture.extension = "CLIP"
    uv = next((node for node in nodes if node.type == "UVMAP"), None)
    if uv is None:
        uv = nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
    links.new(uv.outputs["UV"], texture.inputs["Vector"])
    multiplier = next((node for node in nodes
                       if node.type == "MIX" and node.blend_type == "MULTIPLY"), None)
    color_input = multiplier.inputs["A"] if multiplier else bsdf.inputs["Base Color"]
    links.new(texture.outputs["Color"], color_input)
    links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
    return material


def _shared_bark_material(kit):
    """Keep tree bark separate from cart timber while sharing one white shader."""
    if "world_tree_bark" not in kit.MATERIALS:
        kit.define_material("world_tree_bark", tile=1.0, color=(1.0, 1.0, 1.0), rough=0.95)
    return kit.get_material("world_tree_bark")


def _fallback_material(kit, base_name, prop_id):
    name = f"{base_name}_hero_fallback_{prop_id}"
    # Copy the shared node graph so fallback review retains albedo/alpha maps;
    # exact material names still become independently hideable runtime meshes.
    if bpy.data.materials.get(name) is None:
        material = kit.get_material(base_name).copy()
        material.name = name
    kit.MATERIALS.setdefault(name, dict(kit.MATERIALS[base_name]))
    return name


def _finish_mesh(name, mesh, material, prop, collection, kit):
    yaw = float(prop["yaw"])
    cosine, sine = math.cos(yaw), math.sin(yaw)
    x, world_z = float(prop["x"]), float(prop["z"])
    # Local Blender XY rotates by -yaw; the source north coordinate maps to -Y.
    verts = [(x + cosine * u + sine * v, -world_z - sine * u + cosine * v, height)
             for u, v, height in mesh.verts]
    obj = kit.new_object(name, verts, mesh.faces, material, collection)
    uv = obj.data.uv_layers.get("UVMap") or obj.data.uv_layers.new(name="UVMap")
    if len(obj.data.loops) != len(mesh.uvs):
        raise RuntimeError(f"Tree mesh validation changed UV topology: {name}")
    for index, coordinate in enumerate(mesh.uvs):
        uv.data[index].uv = coordinate
    kit.ensure_white_vertex_colors(obj)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.data.update()
    obj["world_prop_id"] = prop["id"]
    obj["canopy_profile"] = "branching_canopy_v3"
    return obj


def build_branching_trees(props, collection, kit):
    """Create source-driven tree meshes; return the new objects for callers.

    Pass the existing foundry ``citykit`` module as ``kit``. The caller owns
    scene reset, material batching, export and cameras. No scene-wide operators,
    collider changes, asset writes, or paid/provider calls occur here.
    """
    created = []
    tree_props = [prop for prop in props if str(prop.get("kind", "")).startswith("tree_")]
    if not tree_props:
        return created
    _shared_bark_material(kit)
    _shared_leaf_material(kit)
    for prop in tree_props:
        prop_id = str(prop["id"])
        rng = random.Random(zlib.crc32(prop_id.encode("utf-8")) ^ 0xB2A6C417)
        height = float(prop["height"]) * float(prop["scale"])
        blocker_radius = min(float(prop["collider_size"][0]), float(prop["collider_size"][2])) * 0.32
        if height < 4.5 or blocker_radius <= 0.0:
            raise ValueError(f"Branching tree {prop_id} needs height >= 4.5 m and a positive blocker")
        wood, leaves = _Mesh(), _Mesh()
        secondary_layers, primary_layers = [], []
        phase = rng.uniform(0.0, math.tau)
        spread = height * {"tree_a": 0.245, "tree_b": 0.225, "tree_c": 0.27}.get(prop["kind"], 0.245)
        fork_height = max(2.72, height * 0.37)
        lean = _polar(phase, blocker_radius * 0.18)
        fork = Vector((lean.x, lean.y, fork_height))
        trunk = [Vector((0.0, 0.0, 0.02)), Vector((0.0, 0.0, 0.20)),
                 Vector((lean.x * -0.35, lean.y * 0.30, 1.10)),
                 Vector((lean.x * 0.35, lean.y * 0.65, 2.35)),
                 Vector((lean.x * 0.80, lean.y * 0.90, fork_height - 0.16)), fork]
        _tube(wood, trunk, [blocker_radius * factor for factor in (0.81, 0.73, 0.66, 0.57, 0.50, 0.47)],
              10, blocker_radius, phase)
        for index in range(5):
            angle = phase + index * math.tau / 5.0 + rng.uniform(-0.15, 0.15)
            root = [_polar(angle, blocker_radius * 0.12, blocker_radius * 0.25),
                    _polar(angle + 0.08, blocker_radius * 0.53, blocker_radius * 0.20),
                    _polar(angle - 0.04, blocker_radius * 0.90, 0.02)]
            _tube(wood, root, [blocker_radius * factor for factor in (0.20, 0.12, 0.022)],
                  5, blocker_radius, phase + index)

        first_heading = rng.uniform(-0.42, 0.42)
        headings = (first_heading, first_heading + math.radians(rng.uniform(125.0, 157.0)))
        for scaffold_index, heading in enumerate(headings):
            reach = spread * (0.44 if scaffold_index == 0 else 0.60)
            tip = _polar(heading, reach, height * (0.89 if scaffold_index == 0 else 0.77))
            side = _polar(heading + math.pi * 0.5, 1.0)
            if scaffold_index == 0:
                tip += side * spread * 0.10
                primary = [fork, fork.lerp(tip, 0.36) - side * spread * 0.09,
                           fork.lerp(tip, 0.70) + side * spread * 0.10, tip]
            else:
                primary = [fork, fork.lerp(tip, 0.30) + side * spread * 0.13 + _UP * height * 0.025,
                           fork.lerp(tip, 0.72) + side * spread * 0.17 - _UP * height * 0.012, tip]
            primary_layers.append((primary, heading, scaffold_index))
            _tube(wood, primary, [blocker_radius * factor for factor in (0.50, 0.34, 0.22, 0.11)],
                  8, blocker_radius, phase + scaffold_index * 0.8)
            offsets = (-76.0, -20.0, 36.0, 92.0) if scaffold_index == 0 else (-55.0, 14.0, 68.0, 116.0)
            attaches = (0.24, 0.49, 0.78, 0.67) if scaffold_index == 0 else (0.37, 0.71, 0.86, 0.56)
            levels = (0.58, 0.74, 0.86, 0.68) if scaffold_index == 0 else (0.63, 0.80, 0.73, 0.56)
            reaches = (0.90, 0.76, 0.72, 1.02) if scaffold_index == 0 else (0.92, 0.72, 0.86, 0.99)
            for secondary_index, offset in enumerate(offsets):
                attach = _sample_path(primary, attaches[secondary_index] + rng.uniform(-0.025, 0.025))
                angle = heading + math.radians(offset + rng.uniform(-9.0, 9.0))
                reach = spread * reaches[secondary_index] * rng.uniform(0.91, 1.09)
                endpoint = _polar(angle, reach, max(2.65, height * (levels[secondary_index] + rng.uniform(-0.025, 0.025))))
                bend = _polar(angle + math.pi * 0.5, spread * rng.uniform(-0.08, 0.08),
                              height * (0.025 if secondary_index % 2 == 0 else -0.015))
                secondary = [attach, attach.lerp(endpoint, 0.54) + bend, endpoint]
                secondary_layers.append((secondary, angle, secondary_index, scaffold_index))
                _tube(wood, secondary, [blocker_radius * factor for factor in (0.24, 0.14, 0.055)],
                      6, blocker_radius, phase + secondary_index)
                for twig_index, sign in enumerate((-1.0, 1.0)):
                    twig_angle = angle + sign * rng.uniform(0.40, 0.86)
                    twig_length = spread * rng.uniform(0.30, 0.48) * (0.91 if twig_index == 1 else 1.0)
                    rise = height * (rng.uniform(0.055, 0.10) if twig_index == 0 else rng.uniform(-0.07, -0.015))
                    end = endpoint + _polar(twig_angle, twig_length, rise)
                    end.z = max(2.58, min(height * rng.uniform(0.91, 0.935), end.z))
                    curl = _polar(twig_angle + math.pi * 0.5, spread * 0.025,
                                  height * (0.025 if twig_index == 0 else -0.008))
                    twig = [endpoint, endpoint.lerp(end, 0.52) + curl, end]
                    _tube(wood, twig, [blocker_radius * factor for factor in (0.085, 0.048, 0.014)],
                          4, blocker_radius, phase + secondary_index + twig_index * 0.3)
                    card_count = 5 if twig_index == 1 and secondary_index in (0, 3) else 6
                    _spray(leaves, twig, height, rng, card_count=card_count)

        # A separate stream keeps all trunk/branch geometry stable as foliage
        # layering changes, including trees authored at new coordinates/scales.
        layer_rng = random.Random(zlib.crc32(prop_id.encode("utf-8")) ^ 0x21F43BC1)
        _crown_layers(leaves, secondary_layers, primary_layers, height, layer_rng)
        if len(leaves.verts) != LEAF_CARD_COUNT * 9:
            raise RuntimeError(f"Unexpected foliage card count for {prop_id}")

        suffix = f"_hero_fallback_{prop_id}" if prop_id in _HERO_FALLBACK_IDS else ""
        timber_material, leaf_material = "world_tree_bark", "world_leaf_cards"
        if suffix:
            timber_material = _fallback_material(kit, timber_material, prop_id)
            leaf_material = _fallback_material(kit, leaf_material, prop_id)
        trunk_obj = _finish_mesh(f"{prop_id}_branching_{timber_material}", wood, timber_material,
                                 prop, collection, kit)
        leaf_obj = _finish_mesh(f"{prop_id}_branching_{leaf_material}", leaves, leaf_material,
                                prop, collection, kit)
        trunk_obj["walking_radius_m"] = blocker_radius
        leaf_obj["leaf_cards"] = LEAF_CARD_COUNT
        created.extend((trunk_obj, leaf_obj))
    return created
