"""Builds three stylized meadow tree variants as a GLB kit.

Run headless:
    blender.exe --background --python assets/blender/build_meadow_tree.py -- --out apps/client/src/assets/models/env_meadow_tree.glb

Design notes:
- Origin at the trunk base, 1 unit = 1 m. Variants are named tree_A/B/C and
  laid out along +X so one GLB ships the whole kit; the client instances each.
- Trunks taper and lean slightly; canopies are noise-displaced icospheres with
  a light-from-above vertex gradient. Flat shaded.
"""

import argparse
import math
import random
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--out", default="apps/client/src/assets/models/env_meadow_tree.glb")
args = parser.parse_args(argv)

random.seed(20260927)

COLLECTION = bpy.data.collections.new("MeadowTree")
bpy.context.scene.collection.children.link(COLLECTION)


def link(obj):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    COLLECTION.objects.link(obj)
    return obj


def vertex_colors_gradient(obj, top, bottom, ground_bias=0.15):
    mesh = obj.data
    zs = [v.co.z for v in mesh.vertices]
    low, high = min(zs), max(zs) or 1.0
    colors = []
    for v in mesh.vertices:
        t = (v.co.z - low) / (high - low) if high > low else 1.0
        t = max(0.0, min(1.0, t))
        shade = [bottom[i] + (top[i] - bottom[i]) * t for i in range(3)]
        # Ground-contact darkening on the trunk base.
        if v.co.z < ground_bias:
            k = v.co.z / ground_bias
            shade = [s * (0.55 + 0.45 * k) for s in shade]
        colors.extend((*shade, 1.0))
    mesh.color_attributes.new(name="col", type="FLOAT_COLOR", domain="POINT").data.foreach_set("color", colors)


def noise_displace(obj, amplitude, freq=1.4):
    mesh = obj.data
    seen = set()
    for poly in mesh.polygons:
        for vi in poly.vertices:
            if vi in seen:
                continue
            seen.add(vi)
            v = mesh.vertices[vi]
            n = math.sin(v.co.x * freq) * math.cos(v.co.y * freq * 1.3) + math.sin(v.co.z * freq * 0.9 + v.co.x)
            v.co += v.normal * (n * amplitude)
    mesh.update()


def build_trunk(name, height, base_radius, lean, segments=7, rings=5):
    """Stacked tapered segments with a slight S-lean and a flared base."""
    verts, faces = [], []
    offset = 0.0
    drift = random.uniform(-lean, lean)
    for r in range(rings):
        z0 = height * r / rings
        z1 = height * (r + 1) / rings
        r0 = base_radius * (1.0 - 0.55 * r / rings) * (1.25 if r == 0 else 1.0)
        r1 = base_radius * (1.0 - 0.55 * (r + 1) / rings)
        x0 = offset + drift * (z0 / height) ** 2
        x1 = offset + drift * (z1 / height) ** 2
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            verts += [
                (x0 + r0 * math.cos(a0), r0 * math.sin(a0), z0),
                (x0 + r0 * math.cos(a1), r0 * math.sin(a1), z0),
                (x1 + r1 * math.cos(a1), r1 * math.sin(a1), z1),
                (x1 + r1 * math.cos(a0), r1 * math.sin(a0), z1),
            ]
        for i in range(segments):
            b = r * segments * 4 + i * 4
            faces += [(b, b + 1, b + 2, b + 3)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build_canopy(name, blobs, radius, subdivisions, amplitude):
    verts, faces = [], []
    for index, (bx, by, bz, scale) in enumerate(blobs):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius * scale, location=(0, 0, 0))
        sphere = bpy.context.active_object
        mesh = sphere.data
        offset = len(verts)
        noise_displace(sphere, amplitude, freq=1.2 + index * 0.35)
        for v in mesh.vertices:
            verts.append((v.co.x + bx, v.co.y + by, v.co.z + bz))
        for poly in mesh.polygons:
            faces.append(tuple(vi + offset for vi in poly.vertices))
        bpy.data.objects.remove(sphere)
        bpy.data.meshes.remove(mesh)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


VARIANTS = {
    # name: (height, trunk_radius, canopy blobs, ico subdivisions, spread)
    "tree_A": (7.0, 0.42, [(0, 0, 6.4, 1.0), (1.5, 0.5, 5.4, 0.78), (-1.4, -0.4, 5.2, 0.72), (0.3, -0.9, 7.0, 0.66)], 2, 0.22),
    "tree_B": (5.6, 0.36, [(0, 0, 5.0, 1.0), (1.2, 0.4, 4.2, 0.8), (-1.1, -0.5, 4.0, 0.74)], 2, 0.26),
    "tree_C": (8.6, 0.5, [(0, 0, 7.6, 1.0), (1.9, 0.6, 6.4, 0.8), (-1.7, -0.5, 6.2, 0.76), (0.4, -1.2, 8.4, 0.7), (-0.3, 1.1, 7.0, 0.62)], 1, 0.3),
}

slot = 0.0
for name, (height, trunk_radius, blobs, subdivisions, amplitude) in VARIANTS.items():
    trunk = build_trunk(f"{name}_trunk", height * 0.82, trunk_radius, lean=0.9)
    vertex_colors_gradient(trunk, top=(0.52, 0.36, 0.24, 1.0), bottom=(0.30, 0.20, 0.14, 1.0))
    trunk.location.x = slot
    link(trunk)

    canopy = build_canopy(f"{name}_canopy", blobs, 2.1, subdivisions, amplitude)
    # Light-from-above gradient: pale sunlit tops, deep green undersides.
    vertex_colors_gradient(
        canopy,
        top=(0.62, 0.78, 0.38, 1.0),
        bottom=(0.20, 0.42, 0.22, 1.0),
        ground_bias=0.0,
    )
    canopy.location.x = slot
    link(canopy)
    slot += 6.5

bpy.ops.object.select_all(action="DESELECT")
for obj in COLLECTION.objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = COLLECTION.objects[0]

tris = sum(len(poly.vertices) - 2 for obj in COLLECTION.objects for poly in obj.data.polygons)
print(f"meadow tree kit: {len(COLLECTION.objects)} meshes, ~{tris} triangles")

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
