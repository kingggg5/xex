"""Builds the Frontier Keep (castle) as a stylized low-poly GLB.

Run headless:
    blender.exe --background --python assets/blender/build_frontier_keep.py -- --out apps/client/src/assets/models/env_frontier_keep.glb

Design notes (owner references: stylized anime-fantasy castle):
- 1 Blender unit = 1 m, origin at the wall's center on the ground.
- Silhouette first: tapered towers, crenellations, gatehouse arch, banners.
- Edges beveled and vertices jittered slightly so flat shading reads as stone.
- Vertex colors carry a height-based fake AO (darker toward the ground); the
  client multiplies them over the base color.
"""

import argparse
import math
import random
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--out", default="apps/client/src/assets/models/env_frontier_keep.glb")
args = parser.parse_args(argv)

random.seed(20260926)

COLLECTION = bpy.data.collections.new("FrontierKeep")
bpy.context.scene.collection.children.link(COLLECTION)


def link(obj):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    COLLECTION.objects.link(obj)
    return obj


def finish(obj, name, color, jitter=0.05, bevel=0.05, shade_smooth=False, ao_strength=0.45):
    obj.name = name
    mesh = obj.data
    mesh.polygons.foreach_set("use_smooth", [shade_smooth] * len(mesh.polygons))
    mesh.update()
    # Slight jitter so flat shading reads as hand-built stone, not CAD.
    if jitter > 0:
        for vertex in mesh.vertices:
            if abs(vertex.co.z) > 0.02:  # keep the ground contact clean
                vertex.co.x += random.uniform(-jitter, jitter)
                vertex.co.y += random.uniform(-jitter, jitter)
                vertex.co.z += random.uniform(-jitter * 0.4, jitter * 0.4)
    if bevel > 0:
        modifier = obj.modifiers.new("bevel", "BEVEL")
        modifier.width = bevel
        modifier.segments = 1
        modifier.limit_method = "ANGLE"
        modifier.angle_limit = math.radians(50)
        with bpy.context.temp_override(object=obj):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    # Fake baked AO: darken vertices near the ground.
    height = max(v.co.z for v in mesh.vertices) or 1.0
    colors = []
    for vertex in mesh.vertices:
        shade = ao_strength + (1.0 - ao_strength) * min(1.0, vertex.co.z / (height * 0.8))
        colors.extend((shade, shade, shade, 1.0))
    mesh.color_attributes.new(name="col", type="FLOAT_COLOR", domain="POINT").data.foreach_set("color", colors)
    link(obj)
    return obj


def add_mesh(name, verts, faces, color, **kwargs):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, name, color, **kwargs)


def box(name, size, location, color, **kwargs):
    w, h, d = size
    hx, hy = w / 2, d / 2
    verts = [
        (-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0),
        (-hx, -hy, h), (hx, -hy, h), (hx, hy, h), (-hx, hy, h),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
        (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    obj = add_mesh(name, verts, faces, color, **kwargs)
    obj.location = location
    return obj


def tapered_cylinder(name, radius_bottom, radius_top, height, location, segments, color, **kwargs):
    verts, faces = [], []
    for i in range(segments):
        a0 = 2 * math.pi * i / segments
        a1 = 2 * math.pi * (i + 1) / segments
        verts += [
            (radius_bottom * math.cos(a0), radius_bottom * math.sin(a0), 0),
            (radius_bottom * math.cos(a1), radius_bottom * math.sin(a1), 0),
            (radius_top * math.cos(a1), radius_top * math.sin(a1), height),
            (radius_top * math.cos(a0), radius_top * math.sin(a0), height),
        ]
    for i in range(segments):
        b0 = i * 4
        faces += [(b0, b0 + 1, b0 + 2, b0 + 3)]
    center_bottom = len(verts)
    verts.append((0, 0, 0))
    for i in range(segments):
        faces.append((i * 4 + 1, i * 4, center_bottom))
    center_top = len(verts)
    verts.append((0, 0, height))
    for i in range(segments):
        faces.append((i * 4 + 2, i * 4 + 3, center_top))
    obj = add_mesh(name, verts, faces, color, shade_smooth=False, **kwargs)
    obj.location = location
    return obj


def cone_roof(name, radius, height, location, segments, color, overhang=0.12):
    return tapered_cylinder(name, radius + overhang, 0.06, height, location, segments, color)


def merlon_ring(name, radius, count, z, color, width=0.55, height=0.85, center=(0, 0)):
    objs = []
    cx, cy = center
    for i in range(count):
        angle = 2 * math.pi * i / count
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        obj = box(
            f"{name}-{i}",
            (width, width, height),
            (x, y, z),
            color,
            jitter=0.03,
            bevel=0.04,
        )
        obj.rotation_euler.z = -angle
        objs.append(obj)
    return objs


STONE = (0.63, 0.61, 0.52, 1.0)
STONE_LIGHT = (0.76, 0.74, 0.64, 1.0)
ROOF = (0.25, 0.39, 0.60, 1.0)
WOOD = (0.42, 0.29, 0.20, 1.0)
METAL = (0.85, 0.72, 0.42, 1.0)

objects = []

# ---- Curtain wall: two wings with a crenellated top, gate at the center.
WALL_LEN, WALL_H, WALL_T = 38.0, 7.0, 2.4
for side in (-1, 1):
    wall = box(
        f"wall-{side}",
        (13.5, WALL_T, WALL_H),
        (side * 12.3, 0, 0),
        STONE,
        jitter=0.07,
        bevel=0.06,
    )
    objects.append(wall)
    for i in range(4):
        x = side * (8.2 + i * 2.9)
        merlon = box(f"merlon-wall-{side}-{i}", (1.35, 2.5, 1.25), (x, 0, WALL_H), STONE_LIGHT, jitter=0.04, bevel=0.05)
        objects.append(merlon)

# ---- Gatehouse: twin towers, arch frame, wooden gate, portcullis hint.
for side in (-1, 1):
    tower = tapered_cylinder(
        f"gate-tower-{side}", 3.1, 2.7, 12.0, (side * 6.4, 0, 0), 10, STONE, jitter=0.06, bevel=0.06
    )
    objects.append(tower)
    objects += merlon_ring(f"gate-merlon-{side}", 2.6, 7, 12.0, STONE_LIGHT, center=(side * 6.4, 0))
    roof = cone_roof(f"gate-roof-{side}", 3.0, 4.2, (side * 6.4, 0, 12.0), 10, ROOF)
    objects.append(roof)
    cap = tapered_cylinder(f"gate-finial-{side}", 0.16, 0.0, 0.7, (side * 6.4, 0, 16.2), 8, METAL, jitter=0.0, bevel=0.0)
    objects.append(cap)

# Carved open arch. The passage stays clear so the keep remains visible beyond it.
for side in (-1, 1):
    jamb = box(f"gate-jamb-{side}", (1.05, 1.2, 1.25), (side * 4.75, -0.15, 0), STONE_LIGHT, jitter=0.04, bevel=0.05)
    objects.append(jamb)
ARCH_SEGMENTS = 14
ARCH_SPRING = 1.25
ARCH_RADIUS_OUT = 5.25
ARCH_RADIUS_IN = 4.22
ARCH_MID_RADIUS = (ARCH_RADIUS_OUT + ARCH_RADIUS_IN) * 0.5
for index in range(ARCH_SEGMENTS):
    angle = math.pi - (index + 0.5) * math.pi / ARCH_SEGMENTS
    block = box(
        f"gate-arch-stone-{index}",
        (1.35, 1.2, ARCH_RADIUS_OUT - ARCH_RADIUS_IN),
        (math.cos(angle) * ARCH_MID_RADIUS, -0.15, ARCH_SPRING + math.sin(angle) * ARCH_MID_RADIUS),
        STONE_LIGHT if index in (5, 6, 7, 8) else STONE,
        jitter=0.035,
        bevel=0.045,
    )
    block.rotation_euler.y = math.pi * 0.5 - angle
    objects.append(block)

# ---- Corner towers with cone roofs.
for index, (x, height) in enumerate([(-18, 15), (-10, 11), (10, 12), (18, 15)]):
    tower = tapered_cylinder(
        f"tower-{index}", 2.7, 2.3, height, (x, -0.4, 0), 9, STONE, jitter=0.06, bevel=0.06
    )
    objects.append(tower)
    objects += merlon_ring(f"tower-merlon-{index}", 2.2, 6, height, STONE_LIGHT, center=(x, -0.4))
    objects.append(cone_roof(f"tower-roof-{index}", 2.6, 3.8, (x, -0.4, height), 9, ROOF))
    objects.append(tapered_cylinder(f"tower-finial-{index}", 0.14, 0.0, 0.6, (x, -0.4, height + 3.8), 8, METAL, jitter=0.0, bevel=0.0))
    for wy in (3.2, 6.4, 9.2):
        if wy >= height - 1.2:
            continue
        window = box(f"tower-window-{index}-{wy}", (0.5, 0.3, 1.2), (x, -2.55, wy), METAL, jitter=0.0, bevel=0.02, ao_strength=0.1)
        objects.append(window)

# ---- Keep behind the wall with four turrets.
keep = box("keep", (15, 10, 10), (0, 15, 0), STONE, jitter=0.07, bevel=0.07)
objects.append(keep)
keep_roof = box("keep-roof", (15.6, 10.6, 0.8), (0, 15, 10), ROOF, jitter=0.04, bevel=0.05)
objects.append(keep_roof)
for index, x in enumerate((-6, -2, 2, 6)):
    turret = tapered_cylinder(
        f"keep-turret-{index}", 1.5, 1.3, 6.5 + (index % 2) * 1.6, (x, 12.5, 10), 8, STONE_LIGHT, jitter=0.05, bevel=0.05
    )
    objects.append(turret)
    objects.append(cone_roof(f"keep-turret-roof-{index}", 1.45, 2.6, (x, 12.5, 10 + 6.5 + (index % 2) * 1.6), 8, ROOF))
    window = box(f"keep-window-{index}", (0.5, 0.3, 1.0), (x, 9.95, 13.4), METAL, jitter=0.0, bevel=0.02, ao_strength=0.1)
    objects.append(window)

# ---- Banners by the gate.
for side in (-1, 1):
    pole = tapered_cylinder(f"banner-pole-{side}", 0.09, 0.06, 6.8, (side * 8.6, -1.5, 0), 6, WOOD, jitter=0.0, bevel=0.0)
    objects.append(pole)
    banner = box(f"banner-{side}", (1.6, 0.1, 3.6), (side * 8.6 - side * 0.8, -1.5, 3.0), ROOF, jitter=0.02, bevel=0.02, ao_strength=0.2)
    objects.append(banner)
    tip = tapered_cylinder(f"banner-tip-{side}", 0.14, 0.0, 0.4, (side * 8.6, -1.5, 6.8), 6, METAL, jitter=0.0, bevel=0.0)
    objects.append(tip)

# ---- Export only the authored collection (exclude factory-startup's default Cube).
bpy.ops.object.select_all(action="DESELECT")
for obj in COLLECTION.objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = COLLECTION.objects[0]

tris = sum(
    len(poly.vertices) - 2
    for obj in COLLECTION.objects
    for poly in obj.data.polygons
)
print(f"frontier keep: {len(COLLECTION.objects)} parts, ~{tris} triangles")

bpy.ops.export_scene.gltf(
    filepath=bpy.path.abspath(args.out),
    export_format="GLB",
    use_selection=True,
    export_yup=True,
    export_apply=True,
    export_materials="NONE",
    export_extras=False,
)
print(f"exported {args.out}")
