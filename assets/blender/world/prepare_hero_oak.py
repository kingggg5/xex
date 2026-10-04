"""Normalize the preserved Tripo oak; export separate geometry-only game LODs."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--lod-only", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
source = Path(args.source).resolve()
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if len(objects) != 1:
    raise RuntimeError("Expected the inspected single-mesh oak source")
oak = objects[0]
world = oak.matrix_world.copy()
oak.parent = None
oak.matrix_world = world
bpy.context.view_layer.objects.active = oak
oak.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
points = [oak.matrix_world @ vertex.co for vertex in oak.data.vertices]
low, high = min(p.z for p in points), max(p.z for p in points)
factor = 8.6 / (high - low)
center = Vector(((min(p.x for p in points) + max(p.x for p in points)) / 2,
                 (min(p.y for p in points) + max(p.y for p in points)) / 2, low))
for vertex, point in zip(oak.data.vertices, points):
    point = (point - center) * factor
    # Preserve the existing server tree footprint for every solid part below
    # the 1.8 m player capsule. The transition is above the walking volume.
    radius = math.hypot(point.x, point.y)
    limit = 0.70 if point.z <= 1.85 else 0.70 + (point.z - 1.85) * 2.5
    if radius > limit:
        point.x *= limit / radius
        point.y *= limit / radius
    vertex.co = point
oak.location = (0, 0, 0)
oak.name = "sunmeadow_hero_oak"


def protect_walking_volume(mesh):
    """Split every crossing face so LOD collapse cannot bridge over the blocker."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
        dist=1e-7, plane_co=(0, 0, 2.2), plane_no=(0, 0, 1),
        clear_inner=False, clear_outer=False)
    for vertex in bm.verts:
        if vertex.co.z <= 2.200001:
            radius = math.hypot(vertex.co.x, vertex.co.y)
            if radius > 0.70:
                vertex.co.x *= 0.70 / radius
                vertex.co.y *= 0.70 / radius
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


protect_walking_volume(oak.data)
for poly in oak.data.polygons:
    poly.use_smooth = True
for image in bpy.data.images:
    if image.source == "FILE":
        image.pack()
if not args.lod_only:
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "hero_oak.blend"))
roster = []
for lod, ratio in enumerate((1.0, 0.40, 0.14)):
    candidate = oak.copy()
    candidate.data = oak.data.copy()
    bpy.context.collection.objects.link(candidate)
    candidate.name = f"hero_oak_lod{lod}"
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    if ratio < 1:
        modifier = candidate.modifiers.new("bounded-game-lod", "DECIMATE")
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    # Decimation can move boundary vertices below the ground or past the
    # authored tree height; keep every representation in the same volume.
    for vertex in candidate.data.vertices:
        vertex.co.z = max(0.0, min(8.6, vertex.co.z))
    protect_walking_volume(candidate.data)
    triangles = sum(len(poly.vertices) - 2 for poly in candidate.data.polygons)
    path = output / f"hero_oak_lod{lod}.geometry.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB",
        use_selection=True, export_yup=True, export_apply=True,
        export_materials="NONE", export_normals=True, export_texcoords=True,
        export_cameras=False, export_lights=False, export_animations=False)
    roster.append({"lod": lod, "triangles": triangles, "path": path.name})
    bpy.data.objects.remove(candidate, do_unlink=True)
(output / "geometry-receipt.json").write_text(json.dumps({
    "height_m": 8.6, "low_solid_radius_m": 0.70,
    "capsule_clearance_height_m": 1.8, "split_plane_height_m": 2.2, "lods": roster,
    "source_unchanged": True,
}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": "PASS", "lods": roster}))
