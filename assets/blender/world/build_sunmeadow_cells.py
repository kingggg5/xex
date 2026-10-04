"""Build the first pair of authored 64 m Sunmeadow terrain-detail cells.

The flat ground collision seam is represented in content/source/zones.json.
This script reads that same source for cell bounds, routes and static props,
then writes geometry-only GLBs; shared foundry textures are loaded by the
client once and reused across the starter field and both cells.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[3]
CITYKIT_DIR = ROOT / "assets" / "blender" / "city_r5" / "lib"
sys.path.insert(0, str(CITYKIT_DIR))
import citykit as C  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from branching_canopy_v2 import build_branching_trees  # noqa: E402


PARSER = argparse.ArgumentParser()
PARSER.add_argument("--source", required=True)
PARSER.add_argument("--out-dir", required=True)
PARSER.add_argument("--master", required=True)
PARSER.add_argument("--review", required=True)
PARSER.add_argument("--detail-review", required=True)
PARSER.add_argument("--texture-dir", required=True)
ARGS = PARSER.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])

SOURCE_PATH = Path(ARGS.source).resolve()
OUT_DIR = Path(ARGS.out_dir).resolve()
MASTER_PATH = Path(ARGS.master).resolve()
REVIEW_PATH = Path(ARGS.review).resolve()
DETAIL_REVIEW_PATH = Path(ARGS.detail_review).resolve()
C.TEX_DIR = Path(ARGS.texture_dir).resolve()
CELL_OUTPUTS: list[dict[str, object]] = []


def move_to_collection(obj, collection):
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def mesh_object(name: str, verts, faces, material: str, collection):
    obj = C.new_object(name, verts, faces, material, collection)
    C.ensure_white_vertex_colors(obj)
    return obj


def tune_mesh(obj, tile_m: float = 2.0, *, tint=(1.0, 1.0, 1.0), ground_z=None, seed=0):
    C.uv_box(obj, tile_m=tile_m)
    C.vertex_paint(obj, tint=tint, ground_z=ground_z, cavity=0.28, edge=0.12, jitter=0.025, seed=seed)
    return obj


def add_box(name, collection, x, z, base_y, width, depth, height, material, yaw=0.0, bevel=0.035):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, -z, base_y + height * 0.5))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (width, depth, height)
    obj.rotation_euler.z = -yaw
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if bevel > 0:
        C.bevel(obj, width=bevel, segments=2, angle_deg=32)
    obj.data.materials.append(C.get_material(material))
    move_to_collection(obj, collection)
    tune_mesh(obj, C.MATERIALS[material].get("tile", 2.0), tint=(0.97, 0.95, 0.90), ground_z=0.0)
    return obj


def add_cylinder(name, collection, x, z, base_y, radius, height, material, vertices=12, axis="up", yaw=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=height,
                                        location=(x, -z, base_y + height * 0.5))
    obj = bpy.context.object
    obj.name = name
    if axis == "x":
        obj.rotation_euler.y = math.pi * 0.5
    obj.rotation_euler.z += -yaw
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.data.materials.append(C.get_material(material))
    move_to_collection(obj, collection)
    tune_mesh(obj, C.MATERIALS[material].get("tile", 2.0), tint=(0.94, 0.92, 0.86), ground_z=0.0)
    return obj


def offset_xz(x, z, u, v, yaw):
    """Rotate a local east/north offset into the authored world X/Z plane."""
    return x + math.cos(yaw) * u - math.sin(yaw) * v, z + math.sin(yaw) * u + math.cos(yaw) * v


def add_octahedron(name, collection, x, z, bottom_y, width, depth, height, material):
    verts = [
        (x, -z, bottom_y),
        (x - width * 0.5, -z, bottom_y + height * 0.5),
        (x, -z - depth * 0.5, bottom_y + height * 0.5),
        (x + width * 0.5, -z, bottom_y + height * 0.5),
        (x, -z + depth * 0.5, bottom_y + height * 0.5),
        (x, -z, bottom_y + height),
    ]
    faces = [
        (0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 1, 4),
        (5, 1, 2), (5, 2, 3), (5, 3, 4), (5, 4, 1),
    ]
    obj = mesh_object(name, verts, faces, material, collection)
    C.uv_box(obj, tile_m=1.0)
    C.vertex_paint(obj, tint=(0.85, 0.92, 1.0), jitter=0.015, seed=13)
    return obj


def route_x_at_z(points, z):
    """Interpolate the authored route in world X/Z, including its end points."""
    for (x0, z0), (x1, z1) in zip(points, points[1:]):
        if min(z0, z1) <= z <= max(z0, z1):
            fraction = (z - z0) / (z1 - z0)
            return x0 + (x1 - x0) * fraction
    return min(points, key=lambda point: abs(point[1] - z))[0]


def clearing_influence(x, z, landmarks):
    """Soft, ground-color-only wear around the authored waystone and cart."""
    wear = 0.0
    for prop in landmarks:
        radius = 4.5 if prop["kind"] == "trail_marker" else 3.5
        distance = math.hypot(x - prop["x"], z - prop["z"])
        wear = max(wear, max(0.0, 1.0 - distance / radius) ** 2)
    return wear


def world_uv_and_color(obj, cell, route_points=(), landmarks=()):
    mesh = obj.data
    uv = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    color = mesh.color_attributes.get("Col") or mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    for loop in mesh.loops:
        co = mesh.vertices[loop.vertex_index].co
        world_x = co.x
        world_z = -co.y
        uv.data[loop.index].uv = (world_x / 6.0, world_z / 6.0)
        variation = max(0.0, min(1.0,
            0.55
            + 0.14 * math.sin(world_x * 0.17 + 1.7) * math.cos(world_z * 0.15)
            + 0.08 * math.sin(world_x * 0.36 - world_z * 0.26 + 3.1)
            + 0.03 * math.cos(world_x * 0.68 + world_z * 0.52)
        ))
        red = 0.82 + 0.16 * variation
        green = 0.84 + 0.15 * variation
        blue = 0.79 + 0.14 * variation
        if route_points:
            # Thin irregular verge, not a raised embankment or new collision surface.
            shoulder = abs(world_x - route_x_at_z(route_points, world_z))
            edge = max(0.0, 1.0 - abs(shoulder - 4.3) / 3.3)
            edge *= min(1.0, max(0.0, (-world_z - 64.0) / 9.0))
            wear = max(edge * 0.28, clearing_influence(world_x, world_z, landmarks) * 0.35)
            red = min(1.0, red + 0.10 * wear)
            green *= 1.0 - 0.30 * wear
            blue *= 1.0 - 0.20 * wear
        color.data[loop.index].color = (red, green, blue, 1.0)
    mesh.color_attributes.active_color = color


def make_ground(cell, collection, route_points, landmarks):
    min_x, max_x, min_z, max_z = cell["bounds_xz"]
    segments = 24
    verts = []
    for row in range(segments + 1):
        world_z = min_z + (max_z - min_z) * row / segments
        for column in range(segments + 1):
            world_x = min_x + (max_x - min_x) * column / segments
            verts.append((world_x, -world_z, cell["surface_y"]))
    faces = []
    stride = segments + 1
    for row in range(segments):
        for column in range(segments):
            p0 = row * stride + column
            p1 = (row + 1) * stride + column
            p2 = p1 + 1
            p3 = p0 + 1
            faces.append((p0, p1, p2, p3))
    obj = mesh_object(f"terrain_ground_{cell['id']}", verts, faces, "grass_ground", collection)
    world_uv_and_color(obj, cell, route_points, landmarks)
    return obj


def add_cell_flora(cell, collection, seed, route_points, landmarks):
    rng = random.Random(seed)
    min_x, max_x, min_z, max_z = cell["bounds_xz"]
    grass_verts, grass_faces = [], []
    flower_materials = ("world_cell_flower", "world_cell_flower_cream", "world_cell_flower_rose")
    flower_verts = {name: [] for name in flower_materials}
    flower_faces = {name: [] for name in flower_materials}
    center_verts, center_faces = [], []
    leaf_verts, leaf_faces = [], []
    patch_centers = [
        (route_x_at_z(route_points, z) + (-1 if max_x <= 0 else 1) * offset, z)
        for z, offset in ((-82.0, 5.8), (-99.0, 6.6), (-116.0, 5.5))
    ]
    for index in range(1100):
        z = rng.uniform(min_z + 1.5, max_z - 1.5)
        if index < 650:
            patch_x, patch_z = patch_centers[index % len(patch_centers)]
            x = patch_x + rng.gauss(0.0, 1.65)
            z = patch_z + rng.gauss(0.0, 2.6)
        else:
            x = rng.uniform(min_x + 1.5, max_x - 1.5)
        shoulder = abs(x - route_x_at_z(route_points, z))
        if not (min_x + 0.5 < x < max_x - 0.5 and min_z + 0.5 < z < max_z - 0.5):
            continue
        if shoulder < 2.6 or any(math.hypot(x - prop["x"], z - prop["z"]) < 2.3 for prop in landmarks):
            continue
        for blade in range(rng.choice((3, 4, 4, 5))):
            angle = rng.random() * math.tau
            width = rng.uniform(0.055, 0.115)
            height = rng.uniform(0.35, 0.94)
            dx = math.cos(angle) * width
            dy = math.sin(angle) * width
            base_x = x + rng.uniform(-0.16, 0.16)
            base_z = z + rng.uniform(-0.16, 0.16)
            i = len(grass_verts)
            grass_verts.extend([
                (base_x - dx, -base_z + dy, 0.02),
                (base_x + dx, -base_z - dy, 0.02),
                (base_x + dx * 0.18 + math.cos(angle + 0.5) * 0.05,
                 -base_z - dy * 0.18 + math.sin(angle + 0.5) * 0.05, height),
            ])
            grass_faces.extend([(i, i + 1, i + 2), (i + 2, i + 1, i)])
        roadside = shoulder < 10.5
        if index % 2 == 0 or (roadside and index % 3 == 0):
            material = flower_materials[index % len(flower_materials)]
            angle_offset = rng.random() * math.tau
            petals = rng.choice((5, 6))
            for petal in range(petals):
                angle = angle_offset + petal * math.tau / petals
                dx, dy = math.cos(angle), math.sin(angle)
                i = len(flower_verts[material])
                center_x = x + dx * 0.10
                center_y = -z - dy * 0.10
                flower_verts[material].extend([
                    (center_x - dy * 0.065, center_y + dx * 0.065, 0.35),
                    (center_x + dy * 0.065, center_y - dx * 0.065, 0.35),
                    (x + dx * 0.22 - dy * 0.055, -z - dy * 0.22 + dx * 0.055, 0.43),
                    (x + dx * 0.31, -z - dy * 0.31, 0.39),
                ])
                flower_faces[material].extend([(i, i + 1, i + 2), (i + 2, i + 3, i),
                                               (i + 2, i + 1, i), (i, i + 3, i + 2)])
            center_index = len(center_verts)
            center_verts.append((x, -z, 0.405))
            ring_start = len(center_verts)
            for point in range(6):
                angle = angle_offset + point * math.tau / 6
                center_verts.append((x + math.cos(angle) * 0.072, -z - math.sin(angle) * 0.072, 0.405))
            for point in range(6):
                first = ring_start + point
                second = ring_start + ((point + 1) % 6)
                center_faces.extend([(center_index, first, second), (center_index, second, first)])
            for side in (-1, 1):
                blade = len(leaf_verts)
                leaf_verts.extend([
                    (x, -z, 0.06),
                    (x + side * 0.18, -z - 0.04, 0.19),
                    (x + side * 0.28, -z - 0.09, 0.10),
                ])
                leaf_faces.extend([(blade, blade + 1, blade + 2), (blade + 2, blade + 1, blade)])

    if grass_verts:
        grass = mesh_object(f"terrain_flora_{cell['id']}", grass_verts, grass_faces, "world_cell_grass", collection)
        C.vertex_paint(grass, tint=(0.96, 1.0, 0.86), jitter=0.065, seed=seed)
    for flower_index, material in enumerate(flower_materials):
        if flower_faces[material]:
            flowers = mesh_object(f"terrain_flowers_{cell['id']}_{flower_index}", flower_verts[material], flower_faces[material], material, collection)
            C.vertex_paint(flowers, tint=(1.0, 0.98, 0.93), jitter=0.035, seed=seed + flower_index + 3)
    if center_faces:
        centers = mesh_object(f"terrain_flower_centers_{cell['id']}", center_verts, center_faces, "world_cell_flower_center", collection)
        C.vertex_paint(centers, tint=(1.0, 0.96, 0.80), jitter=0.025, seed=seed + 7)
    if leaf_faces:
        leaves = mesh_object(f"terrain_flower_leaves_{cell['id']}", leaf_verts, leaf_faces, "world_leaf_green", collection)
        C.vertex_paint(leaves, tint=(0.76, 0.94, 0.64), jitter=0.04, seed=seed + 11)


def add_fern_patches(cell, collection, seed, route_points, props):
    """Batch walk-through understory into one mesh, clear of the route and colliders."""
    rng = random.Random(seed ^ 0xF31A)
    min_x, max_x, min_z, max_z = cell["bounds_xz"]
    verts, faces = [], []
    placed = 0
    for _ in range(320):
        if placed == 85:
            break
        x = rng.uniform(min_x + 2.0, max_x - 2.0)
        z = rng.uniform(min_z + 2.0, max_z - 2.0)
        if abs(x - route_x_at_z(route_points, z)) < 5.5:
            continue
        if any(math.hypot(x - prop["x"], z - prop["z"]) < 2.0 for prop in props):
            continue
        placed += 1
        rotation = rng.uniform(0.0, math.tau)
        for frond in range(5):
            angle = rotation + frond * math.tau / 5
            dx, dz = math.cos(angle), math.sin(angle)
            spread = rng.uniform(0.26, 0.46)
            height = rng.uniform(0.32, 0.64)
            base = len(verts)
            verts.extend([
                (x, -z, 0.035),
                (x + dx * spread * 0.45 - dz * 0.12, -z - dz * spread * 0.45 - dx * 0.12, height * 0.7),
                (x + dx * spread, -z - dz * spread, height),
                (x + dx * spread * 0.45 + dz * 0.12, -z - dz * spread * 0.45 + dx * 0.12, height * 0.7),
            ])
            faces.extend([(base, base + 1, base + 2), (base, base + 2, base + 3),
                          (base + 2, base + 1, base), (base + 3, base + 2, base)])
    if verts:
        fern = mesh_object(f"terrain_ferns_{cell['id']}", verts, faces, "world_leaf_green", collection)
        C.vertex_paint(fern, tint=(0.72, 0.88, 0.63), jitter=0.06, seed=seed + 31)


def add_landmark_floor(props, collection, route_points):
    """Ground-flush stone tells for POIs; tall pieces remain the authored colliders."""
    for prop in props:
        if prop["kind"] != "trail_marker":
            continue
        x, z = prop["x"], prop["z"]
        verts = [(x, -z, 0.022)]
        for index in range(12):
            angle = index * math.tau / 12
            radius = 1.9 if index % 2 == 0 else 1.75
            verts.append((x + radius * math.cos(angle), -z - radius * math.sin(angle), 0.022))
        faces = [(0, (index + 1) % 12 + 1, index + 1) for index in range(12)]
        pad = mesh_object(f"{prop['id']}_floor", verts, faces, "stone_foundation", collection)
        tune_mesh(pad, 2.0, tint=(0.82, 0.85, 0.77))
        # Ground-flush inlaid compass ring: visual detail, not a new obstacle.
        ring_verts, ring_faces = [], []
        for index in range(24):
            angle = index * math.tau / 24
            for radius in (1.43, 1.67):
                ring_verts.append((x + radius * math.cos(angle), -z - radius * math.sin(angle), 0.028))
        for index in range(24):
            a, b = 2 * index, 2 * ((index + 1) % 24)
            ring_faces.append((a, b, b + 1, a + 1))
        ring = mesh_object(f"{prop['id']}_floor_compass", ring_verts, ring_faces, "stone_foundation", collection)
        C.uv_box(ring, tile_m=1.4)
        C.vertex_paint(ring, tint=(0.93, 0.92, 0.78), jitter=0.02, seed=211)
        # Low stepping stones lead from the existing marker toward the trail.
        for step in range(5):
            fraction = (step + 1) / 6
            target_x = x + (route_x_at_z(route_points, z) - x) * fraction
            add_box(f"{prop['id']}_step_{step}", collection, target_x, z, 0.015,
                    0.75, 0.45, 0.035, "stone_foundation", yaw=prop["yaw"], bevel=0.0)


def add_small_stones(cell, collection, seed):
    rng = random.Random(seed ^ 0x51A7)
    min_x, max_x, min_z, max_z = cell["bounds_xz"]
    for index in range(15):
        x = rng.choice([rng.uniform(min_x + 2, min_x + 12), rng.uniform(max_x - 12, max_x - 2)])
        z = rng.uniform(min_z + 2, max_z - 2)
        radius = rng.uniform(0.12, 0.34)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=radius, location=(x, -z, radius * 0.62))
        obj = bpy.context.object
        obj.name = f"terrain_edge_stone_{cell['id']}_{index:02d}"
        obj.scale = (rng.uniform(0.8, 1.6), rng.uniform(0.7, 1.5), rng.uniform(0.35, 0.9))
        obj.rotation_euler = (rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(0, math.tau))
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        obj.data.materials.append(C.get_material("stone_foundation"))
        move_to_collection(obj, collection)
        C.uv_box(obj, tile_m=2.4)
        C.vertex_paint(obj, tint=(0.82, 0.86, 0.84), ground_z=0.0, seed=seed + index)


# Segmental voussoir arch over the southbound trail (art pass v1, 2026-10-02).
ARCH_SPRING_Y = 2.58        # top of the impost caps added on the 2.36 m post crowns
ARCH_INNER_HALF_SPAN = 6.0  # intrados springing point |x| (posts stand at |x| = 6.4)
ARCH_RISE = 2.3             # intrados rise above the springing line (apex 4.88 m)
ARCH_RING = 0.62            # radial thickness of a voussoir
ARCH_DEPTH = 0.72           # thickness along the trail
ARCH_BLOCKS = 13            # odd: the keystone sits on x = 0 (built once, by the east cell)
ARCH_JOINT = 0.012          # mortar joint (m)


def _arch_block(name, collection, side, z0, a0, a1, r_in, r_out, centre_y, depth, flat_bed_y=None, seed=0):
    """One wedge-shaped voussoir between radial joints a0..a1 (radians from the vertical)."""
    import bmesh
    bm = bmesh.new()
    verts = []
    for a in (a0, a1):
        for r in (r_in, r_out):
            x = side * r * math.sin(a)
            y = centre_y + r * math.cos(a)
            if flat_bed_y is not None and a == a1:
                y = flat_bed_y  # the springer's lower face beds flat on the impost
            for zz in (z0 - depth * 0.5, z0 + depth * 0.5):
                verts.append(bm.verts.new((x, -zz, y)))
    v = lambda ai, ri, zi: verts[ai * 4 + ri * 2 + zi]
    for quad in (
        (v(0, 0, 0), v(1, 0, 0), v(1, 0, 1), v(0, 0, 1)),  # intrados
        (v(0, 1, 0), v(0, 1, 1), v(1, 1, 1), v(1, 1, 0)),  # extrados
        (v(0, 0, 0), v(0, 0, 1), v(0, 1, 1), v(0, 1, 0)),  # joint a0
        (v(1, 0, 0), v(1, 1, 0), v(1, 1, 1), v(1, 0, 1)),  # joint a1 / bed
        (v(0, 0, 0), v(0, 1, 0), v(1, 1, 0), v(1, 0, 0)),  # back face
        (v(0, 0, 1), v(1, 0, 1), v(1, 1, 1), v(0, 1, 1)),  # front face
    ):
        bm.faces.new(quad)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = C.object_from_bmesh(name, bm, "stone_foundation", collection)
    C.ensure_white_vertex_colors(obj)
    C.bevel(obj, width=0.05, segments=2, angle_deg=30)
    C.uv_box(obj, tile_m=C.MATERIALS["stone_foundation"].get("tile", 2.0))
    C.vertex_paint(obj, tint=(0.97, 0.95, 0.90), ground_z=0.0, cavity=0.28, edge=0.14, jitter=0.05, seed=seed)
    return obj


def add_waystone_arches(cell, collection, props):
    """Each cell owns half of a segmental voussoir arch springing from impost caps on its stone posts.

    The previous chain of axis-aligned boxes floated 0.46 m above the post crowns with open gaps between
    the blocks. Wedge-shaped voussoirs now meet along radial joints, the springer beds flat on a wider
    impost cap, and the keystone (one stone, owned by the east cell) projects above and below the ring.
    All new stonework stays above 2.36 m, clear of the player capsule.
    """
    r_in = (ARCH_INNER_HALF_SPAN ** 2 + ARCH_RISE ** 2) / (2 * ARCH_RISE)
    half_angle = math.asin(ARCH_INNER_HALF_SPAN / r_in)
    centre_y = ARCH_SPRING_Y + ARCH_RISE - r_in
    step = 2 * half_angle / ARCH_BLOCKS
    joint = ARCH_JOINT / r_in
    for prop in props:
        if prop["kind"] != "stone_pillar":
            continue
        side = -1 if prop["x"] < 0 else 1
        rng = random.Random(f"{prop['id']}-arch")
        z0 = prop["z"]
        add_box(f"{prop['id']}_arch_impost", collection, prop["x"], z0, 2.36, 1.02, 0.92, 0.22,
                "stone_foundation", prop.get("yaw", 0.0), bevel=0.05)
        half = (ARCH_BLOCKS - 1) // 2
        for k in range(half + 1):
            if k == 0:  # keystone (owned by the east cell, one stone across x = 0): projects 0.08 below, 0.14 above
                if side < 0:
                    continue
                a0, a1 = -(step * 0.5 - joint), step * 0.5 - joint
                inner, outer, depth = r_in - 0.08, r_in + ARCH_RING + 0.14, ARCH_DEPTH + 0.12
            else:
                a0 = step * (k - 0.5) + joint
                a1 = half_angle if k == half else step * (k + 0.5) - joint
                inner = r_in
                outer = r_in + ARCH_RING + rng.uniform(-0.035, 0.04)
                depth = ARCH_DEPTH + rng.uniform(-0.05, 0.02)
            _arch_block(f"{prop['id']}_arch_{k}", collection, side, z0 + (rng.uniform(-0.015, 0.015) if k else 0.0),
                        a0, a1, inner, outer, centre_y, depth,
                        flat_bed_y=ARCH_SPRING_Y if k == half else None, seed=rng.randrange(1 << 30))
        # A rune crystal hangs under the ring on each side (magic, intentionally free-floating).
        gem_x = 2.4
        intrados_y = centre_y + math.sqrt(r_in ** 2 - gem_x ** 2)
        add_octahedron(f"{prop['id']}_arch_rune", collection, side * gem_x, z0, intrados_y - 0.58,
                       0.24, 0.24, 0.40, "magic_blue")


def add_rocky_cell_skirt(cell, collection, seed):
    """Rock fascia drops below flat walkable ground, giving the perimeter a rooted silhouette."""
    rng = random.Random(seed + 992)
    min_x, max_x, min_z, max_z = cell["bounds_xz"]
    edges = [((min_x, min_z), (max_x, min_z))]
    edges.append(((min_x, max_z), (min_x, min_z)) if max_x <= 0 else ((max_x, min_z), (max_x, max_z)))
    verts, faces = [], []
    for start, end in edges:
        for segment in range(16):
            t0, t1 = segment / 16, (segment + 1) / 16
            x0, z0 = start[0] + (end[0]-start[0])*t0, start[1] + (end[1]-start[1])*t0
            x1, z1 = start[0] + (end[0]-start[0])*t1, start[1] + (end[1]-start[1])*t1
            depth = rng.uniform(3.5, 7.0)
            base = len(verts)
            verts.extend([(x0,-z0,-0.02),(x1,-z1,-0.02),(x1,-z1,-depth),(x0,-z0,-depth*0.86)])
            faces.extend([(base,base+1,base+2),(base,base+2,base+3)])
    obj = mesh_object(f"terrain_rock_fascia_{cell['id']}", verts, faces, "stone_foundation", collection)
    C.uv_box(obj, tile_m=3.4)
    C.vertex_paint(obj, tint=(0.73,0.78,0.65), cavity=0.15, edge=0.06, jitter=0.08, seed=seed)


def add_review_ground(bounds_xz, name, collection):
    cell = {"bounds_xz": bounds_xz, "surface_y": 0.0}
    min_x, max_x, min_z, max_z = bounds_xz
    verts = [(min_x, -min_z, 0), (min_x, -max_z, 0), (max_x, -max_z, 0), (max_x, -min_z, 0)]
    obj = mesh_object(name, verts, [(0, 1, 2, 3)], "grass_ground", collection)
    world_uv_and_color(obj, cell)
    return obj


def add_review_trail(route, collection):
    points = route["points"]
    half_width = route["width"] * 0.5
    rows = []
    cumulative = 0.0
    for index, (x, z) in enumerate(points):
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        dx, dz = after[0] - before[0], after[1] - before[1]
        length = max(0.001, math.hypot(dx, dz))
        nx, nz = -dz / length, dx / length
        if index > 0:
            cumulative += math.hypot(x - points[index - 1][0], z - points[index - 1][1])
        left = (x + nx * half_width, z + nz * half_width)
        right = (x - nx * half_width, z - nz * half_width)
        rows.append((left, right, cumulative))
    verts, faces = [], []
    for left, right, _ in rows:
        verts.extend([(left[0], -left[1], 0.045), (right[0], -right[1], 0.045)])
    for index in range(len(rows) - 1):
        base = index * 2
        faces.append((base, base + 1, base + 3, base + 2))
    obj = mesh_object("review_southbound_trail", verts, faces, "cobble_path", collection)
    C.uv_box(obj, tile_m=2.6)
    C.vertex_paint(obj, tint=(0.98, 0.95, 0.86), ground_z=0.0, jitter=0.02)
    return obj


def add_tree_props_to_cell(props, collection):
    """Branching original tree silhouettes, grounded at the same server blockers."""
    leaf_batches = {}
    def branch(name, start, end, bottom_radius, top_radius, material="timber_dark"):
        vector = Vector(end) - Vector(start)
        bpy.ops.mesh.primitive_cone_add(vertices=9, radius1=bottom_radius, radius2=top_radius,
                                       depth=vector.length, location=(Vector(start) + Vector(end)) * 0.5)
        obj = bpy.context.object
        obj.name = name
        obj.rotation_euler = vector.to_track_quat("Z", "Y").to_euler()
        obj.data.materials.append(C.get_material(material))
        move_to_collection(obj, collection)
        C.uv_box(obj, tile_m=1.0)
        C.vertex_paint(obj, tint=(0.88, 0.81, 0.66), ground_z=0.0, jitter=0.025, seed=17)
        C.shade_smooth(obj)
        return obj

    for prop in props:
        if not prop["kind"].startswith("tree_"):
            continue
        # Keep an authored fallback until a candidate passes the visual gate.
        # Separate two groups let the development-only comparison hide them.
        hero_fallback = prop["id"] in {"sunmeadow_pine_west_mid", "sunmeadow_oak_east"}
        suffix = f"_hero_fallback_{prop['id']}" if hero_fallback else ""
        timber_material = "timber_dark" + suffix
        leaf_material = "world_leaf_cards" + suffix
        if hero_fallback:
            C.define_material(timber_material, tile=1.0, color=(0.28, 0.20, 0.13), rough=0.86)
            C.define_material(leaf_material, tile=1.0, color=(1.0, 1.0, 1.0), rough=0.94, alpha_from_texture=True)
        leaf_verts, leaf_faces, leaf_uvs = leaf_batches.setdefault(leaf_material, ([], [], []))
        rng = random.Random(sum(map(ord, prop["id"])) + 407)
        x, z = prop["x"], prop["z"]
        height = prop["height"] * prop["scale"]
        trunk_radius = min(prop["collider_size"][0], prop["collider_size"][2]) * 0.32
        lean = rng.uniform(-0.18, 0.18)
        branch(f"{prop['id']}_root_trunk", (x, -z, 0), (x + lean, -z, height * 0.64), trunk_radius, trunk_radius * 0.34, timber_material)
        for crown in range(9):
            angle = crown * 2.39996 + prop["yaw"]
            ring_radius = height * (0.20 if crown < 6 else 0.11)
            dx, dy = math.cos(angle) * ring_radius, math.sin(angle) * ring_radius
            level = height * (0.57 + crown * 0.043)
            if crown < 6:
                branch(f"{prop['id']}_branch_{crown}", (x + lean * 0.6, -z, height * 0.39),
                       (x + dx, -z + dy, level), trunk_radius * 0.36, trunk_radius * 0.09, timber_material)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0,
                                                location=(x + dx, -z + dy, level))
            obj = bpy.context.object
            obj.name = f"{prop['id']}_canopy_{crown}"
            spread = height * rng.uniform(0.17, 0.22)
            obj.scale = (spread * 1.22, spread, spread * rng.uniform(0.70, 1.02))
            obj.rotation_euler.z = angle
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            obj.data.materials.append(C.get_material("world_leaf_green"))
            move_to_collection(obj, collection)
            C.uv_box(obj, tile_m=1.4)
            tint = (0.69, 0.84, 0.55) if prop["kind"] == "tree_c" else (0.82, 0.95, 0.68)
            C.vertex_paint(obj, tint=tint, ground_z=0, cavity=0.18, edge=0.1,
                           jitter=0.055, seed=crown + sum(map(ord, prop["id"])))
            C.shade_smooth(obj)
            for card in range(14):
                direction = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.25, 1))).normalized()
                center = Vector((x + dx, -z + dy, level)) + direction * spread * 1.02
                right = direction.cross(Vector((0, 0, 1)))
                if right.length < 0.01:
                    right = Vector((1, 0, 0))
                right.normalize()
                up = right.cross(direction).normalized()
                size = spread * rng.uniform(0.52, 0.78)
                base = len(leaf_verts)
                for u, v in ((-1,-1),(1,-1),(1,1),(-1,1)):
                    point = center + right * u * size + up * v * size
                    leaf_verts.append(tuple(point))
                leaf_faces.append((base,base+1,base+2,base+3))
                leaf_uvs.extend(((0,0),(1,0),(1,1),(0,1)))
            # The foliage cards own the final silhouette; do not ship smooth green blobs behind them.
            bpy.data.objects.remove(obj, do_unlink=True)
    for leaf_material, (leaf_verts, leaf_faces, leaf_uvs) in leaf_batches.items():
        leaves = mesh_object(f"canopy_leaf_cards_{collection.name}_{leaf_material}", leaf_verts, leaf_faces, leaf_material, collection)
        uv = leaves.data.uv_layers.new(name="UVMap")
        for loop in leaves.data.loops:
            uv.data[loop.index].uv = leaf_uvs[loop.vertex_index]
        C.vertex_paint(leaves, tint=(0.94, 1.0, 0.89), cavity=0, edge=0, jitter=0.02, seed=64)


def add_bush_props_to_cell(props, collection):
    bush_kit = ROOT / "apps" / "client" / "src" / "assets" / "foliage" / "kenney" / "plant_bushDetailed.glb"
    for prop in props:
        if prop["kind"] != "bush":
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(bush_kit))
        imported = list(set(bpy.data.objects) - before)
        for source in imported:
            if source.type != "MESH":
                continue
            obj = source.copy()
            obj.data = source.data.copy()
            obj.name = prop["id"]
            obj.parent = None
            obj.matrix_world = source.matrix_world.copy()
            obj.matrix_world.translation = Vector((prop["x"], -prop["z"], 0.0))
            obj.scale = (prop["scale"], prop["scale"], prop["scale"])
            obj.rotation_euler.z = -prop["yaw"]
            obj.data.materials.clear()
            obj.data.materials.append(C.get_material("world_leaf_green"))
            move_to_collection(obj, collection)
            C.uv_box(obj, tile_m=1.6)
            C.ensure_white_vertex_colors(obj)
        for source in imported:
            bpy.data.objects.remove(source, do_unlink=True)


def add_waystone(prop, collection):
    """Readable shrine silhouette and recessed-looking runes inside its authored AABB."""
    x, z, yaw, name = prop["x"], prop["z"], prop["yaw"], prop["id"]
    add_box(f"{name}_plinth", collection, x, z, 0.0, 1.10, 0.96, 0.19, "stone_foundation", yaw, bevel=0.045)
    add_box(f"{name}_plinth_step", collection, x, z, 0.19, 0.95, 0.82, 0.10, "stone_foundation", yaw, bevel=0.025)
    add_box(f"{name}_shaft", collection, x, z, 0.27, 0.72, 0.56, 1.47, "stone_foundation", yaw, bevel=0.035)
    for height in (0.40, 1.52):
        add_box(f"{name}_carved_band_{height}", collection, x, z, height,
                0.81, 0.65, 0.095, "stone_foundation", yaw, bevel=0.015)
    add_box(f"{name}_capital", collection, x, z, 1.73, 0.95, 0.79, 0.20, "stone_foundation", yaw)
    add_box(f"{name}_crystal_socket", collection, x, z, 1.93, 0.51, 0.50, 0.08, "metal_iron", yaw, bevel=0.018)
    for u in (-0.28, 0.28):
        for v in (-0.25, 0.25):
            px, pz = offset_xz(x, z, u, v, yaw)
            add_box(f"{name}_crystal_prong_{u}_{v}", collection, px, pz, 1.94,
                    0.065, 0.065, 0.33, "metal_iron", yaw, bevel=0.012)
    add_octahedron(f"{name}_beacon", collection, x, z, 2.01, 0.40, 0.40, 0.49, "magic_blue")

    # Two engraved faces let the waystone read from either approach. Keep the
    # glowing lines just above the bevelled shaft, not outside the collider.
    strokes = [((-0.22, 1.12), (0.0, 1.40)), ((0.0, 1.40), (0.22, 1.12)),
               ((0.22, 1.12), (0.0, 0.82)), ((0.0, 0.82), (-0.22, 1.12)),
               ((0.0, 1.31), (0.0, 0.93)), ((-0.28, 0.67), (-0.08, 0.67)),
               ((0.08, 0.67), (0.28, 0.67)), ((-0.25, 0.58), (-0.13, 0.58)),
               ((0.13, 0.58), (0.25, 0.58))]
    verts, faces = [], []
    for face_side in (-1, 1):
        for (u0, h0), (u1, h1) in strokes:
            du, dh = u1 - u0, h1 - h0
            length = math.hypot(du, dh)
            width_u, width_h = -dh / length * 0.018, du / length * 0.018
            corners = ((u0 + width_u, h0 + width_h), (u0 - width_u, h0 - width_h),
                       (u1 - width_u, h1 - width_h), (u1 + width_u, h1 + width_h))
            base = len(verts)
            for u, h in corners:
                px, pz = offset_xz(x, z, u, face_side * 0.287, yaw)
                verts.append((px, -pz, h))
            faces.extend(((base, base + 1, base + 2), (base, base + 2, base + 3),
                          (base + 2, base + 1, base), (base + 3, base + 2, base)))
    runes = mesh_object(f"{name}_runes", verts, faces, "magic_blue", collection)
    C.uv_box(runes, tile_m=1.0)
    C.vertex_paint(runes, tint=(0.48, 0.72, 0.90), jitter=0.0)

    # Only the upright shrine participates in this check; its paving is flush
    # and intentionally wider than the server's solid waystone collider.
    width, height, depth = prop["collider_size"]
    half_x, half_z = width * 0.5, depth * 0.5
    for obj in collection.objects:
        if not obj.name.startswith(f"{name}_") or obj.name.startswith((f"{name}_floor", f"{name}_step_")):
            continue
        for corner in obj.bound_box:
            px, blender_y, up = obj.matrix_world @ Vector(corner)
            if abs(px - x) > half_x + 0.01 or abs(-blender_y - z) > half_z + 0.01 or up < -0.01 or up > height + 0.01:
                raise RuntimeError(f"Waystone mesh {obj.name} at {(px, -blender_y, up)} "
                                   f"exceeds authored collider {prop['collider_size']} around {(x, z)}.")


def add_world_prop(prop, collection):
    x, z, yaw = prop["x"], prop["z"], prop["yaw"]
    if prop["kind"] == "trail_marker":
        add_waystone(prop, collection)
    elif prop["kind"] == "broken_cart":
        add_box(f"{prop['id']}_bed", collection, x, z, 0.56, 1.25, 1.8, 0.16, "timber_dark", yaw)
        for side in [-1, 1]:
            add_box(f"{prop['id']}_rail_{side}", collection, x + side * 0.55, z, 0.68, 0.16, 1.8, 0.38, "timber_dark", yaw, bevel=0.025)
            add_cylinder(f"{prop['id']}_wheel_{side}", collection, x + side * 0.79, z, 0.08, 0.45, 0.14, "timber_dark", vertices=12, axis="x", yaw=yaw)
        add_box(f"{prop['id']}_broken_board", collection, x - 0.18, z + 0.2, 1.0, 0.15, 1.1, 0.10, "timber_dark", yaw - 0.25, bevel=0.015)
        add_box(f"{prop['id']}_crate", collection, x + 0.20, z - 0.3, 0.75, 0.55, 0.55, 0.45, "timber_dark", yaw + 0.4, bevel=0.025)
    elif prop["kind"] == "stone_pillar":
        scale = prop["scale"]
        # Keep the solid plinth inside the shared 0.9 m collision footprint.
        add_cylinder(f"{prop['id']}_foot", collection, x, z, 0.0, 0.44 * scale, 0.22, "stone_foundation", vertices=10, yaw=yaw)
        add_box(f"{prop['id']}_shaft", collection, x, z, 0.18, 0.46 * scale, 0.46 * scale, 1.65, "stone_foundation", yaw, bevel=0.055)
        add_cylinder(f"{prop['id']}_carved_band", collection, x, z, 1.55, 0.30 * scale, 0.10, "stone_foundation", vertices=10, yaw=yaw)
        add_box(f"{prop['id']}_capital", collection, x, z, 1.82, 0.68 * scale, 0.68 * scale, 0.30, "stone_foundation", yaw, bevel=0.06)
        add_box(f"{prop['id']}_crown", collection, x, z, 2.12, 0.48 * scale, 0.48 * scale, 0.24, "stone_foundation", yaw + 0.18, bevel=0.04)
        add_octahedron(f"{prop['id']}_rune_crystal", collection, x, z, 2.34, 0.20 * scale, 0.20 * scale, 0.26, "magic_blue")


def export_geometry_only(objects, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_materials="NONE",
        export_vertex_color="NAME",
        export_vertex_color_name="Col",
        export_texcoords=True,
        export_normals=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_extras=False,
    )


def main():
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    zone = source["zones"][0]
    cells = zone.get("terrain_cells", [])
    props = zone.get("world_props", [])
    south_route = next(route for route in zone["world_routes"] if route["id"] == "southbound_trail")
    route_points = south_route["points"]
    if len(cells) != 2 or len(props) != 24:
        raise RuntimeError("Expected two adjacent Sunmeadow cells and twenty-four authored props.")
    C.reset_scene()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    world = bpy.data.worlds.new("Sunmeadow late-morning sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.43, 0.58, 0.74, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
    scene.world = world
    light_data = bpy.data.lights.new("Sunmeadow sun", "SUN")
    light = bpy.data.objects.new("Sunmeadow sun", light_data)
    scene.collection.objects.link(light)
    light.rotation_euler = (math.radians(25), math.radians(-30), math.radians(-32))
    light_data.energy = 2.0

    for material_name, spec in [
        ("world_leaf_green", dict(tile=1.6, color=(0.30, 0.48, 0.18), rough=0.94)),
        ("world_leaf_cards", dict(tile=1.0, color=(1.0, 1.0, 1.0), rough=0.94, alpha_from_texture=True)),
        ("world_cell_grass", dict(tile=1.0, color=(0.30, 0.48, 0.18), rough=0.94)),
        ("world_cell_flower", dict(tile=1.0, color=(0.98, 0.83, 0.54), rough=0.86)),
        ("world_cell_flower_cream", dict(tile=1.0, color=(0.97, 0.92, 0.79), rough=0.86)),
        ("world_cell_flower_rose", dict(tile=1.0, color=(0.78, 0.30, 0.36), rough=0.86)),
        ("world_cell_flower_center", dict(tile=1.0, color=(0.98, 0.70, 0.18), rough=0.78)),
    ]:
        if material_name not in C.MATERIALS:
            C.define_material(material_name, **spec)

    export_lists: dict[str, list] = {}
    all_render_meshes = []
    for cell in cells:
        cell_id = cell["id"]
        collection = C.collection(f"cell_{cell_id}")
        cell_props = [prop for prop in props if prop["cell"] == cell_id]
        objects = []
        landmarks = [prop for prop in cell_props if prop["kind"] in {"trail_marker", "broken_cart"}]
        seed = sum(ord(char) for char in cell_id)
        ground = make_ground(cell, collection, route_points, landmarks)
        objects.append(ground)
        add_cell_flora(cell, collection, seed, route_points, landmarks)
        add_fern_patches(cell, collection, seed, route_points, cell_props)
        add_small_stones(cell, collection, seed)
        add_waystone_arches(cell, collection, cell_props)
        add_rocky_cell_skirt(cell, collection, seed)
        add_landmark_floor(landmarks, collection, route_points)
        build_branching_trees(cell_props, collection, C)
        add_bush_props_to_cell(cell_props, collection)
        for prop in cell_props:
            if prop["kind"] not in {"tree_a", "tree_b", "tree_c", "bush"}:
                add_world_prop(prop, collection)
        objects = list(collection.objects)
        export_lists[cell_id] = objects
        all_render_meshes.extend(objects)

    review_context = C.collection("sunmeadow_review_context")
    all_render_meshes.append(add_review_ground([-50, 50, -42, 58], "review_existing_meadow", review_context))
    connector = add_review_ground([-64, 64, -64, -42], "review_south_connector", review_context)
    trail = add_review_trail(south_route, review_context)
    all_render_meshes.extend((connector, trail))
    # Frame the built cells and seam, not the large empty starter-field context.
    overview_camera = C.frame_camera([*export_lists[cells[0]["id"]], *export_lists[cells[1]["id"]], connector, trail],
                                     azimuth_deg=-36, elevation_deg=42, lens=48, margin=1.2,
                                     name="Sunmeadow cell review camera")
    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(REVIEW_PATH)
    bpy.ops.render.render(write_still=True)

    waystone_prop = next(prop for prop in props if prop["kind"] == "trail_marker")
    detail_target = Vector((waystone_prop["x"], -waystone_prop["z"], 1.35))
    detail_camera_data = bpy.data.cameras.new("Sunmeadow waystone close-up")
    detail_camera_data.lens = 55
    detail_camera = bpy.data.objects.new("Sunmeadow waystone close-up", detail_camera_data)
    scene.collection.objects.link(detail_camera)
    detail_camera.location = detail_target + Vector((7.0, 12.0, 4.2))
    detail_camera.rotation_euler = (detail_target - detail_camera.location).to_track_quat("-Z", "Y").to_euler()
    detail_camera_data.clip_end = 500
    scene.camera = detail_camera
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    DETAIL_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(DETAIL_REVIEW_PATH)
    bpy.ops.render.render(write_still=True)
    scene.camera = overview_camera
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1100
    scene.render.filepath = str(REVIEW_PATH)
    MASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(MASTER_PATH))

    for cell in cells:
        cell_id = cell["id"]
        merged, hooks = C.merge_by_material(export_lists[cell_id], prefix=f"Cell {cell_id}")
        if hooks:
            raise RuntimeError(f"Unexpected runtime hooks in static terrain cell {cell_id}.")
        output = OUT_DIR / f"{cell['asset']}.glb"
        export_geometry_only(merged, output)
        triangles = sum(len(poly.vertices) - 2 for obj in merged for poly in obj.data.polygons)
        if triangles > 40_000:
            raise RuntimeError(f"Cell {cell_id} exceeds 40k source triangles: {triangles}.")
        print(f"CELL {cell_id} triangles={triangles} materials={len(merged)} output={output}", flush=True)


if __name__ == "__main__":
    main()
