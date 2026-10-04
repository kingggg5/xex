"""Create an original three-piece Sunmeadow starter-village prop kit.

Run from the repository root with Blender 5.2:
    blender --background --factory-startup --python-exit-code 1 \
        --python assets/blender/build_wayfarer_kit.py

The GLB contains three meshes, each at its own ground-center pivot. One shared
vertex-painted PBR material needs no external textures or game-specific lights.
The editable .blend spaces the pieces apart for review *after* the export.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, default=ROOT / "apps/client/src/assets/models/prop_wayfarer_kit.glb")
parser.add_argument("--blend", type=Path, default=ROOT / "assets/models/props/wayfarer_kit.blend")
parser.add_argument("--review", type=Path, default=ROOT / "assets/models/props/review/wayfarer_kit.png")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

STONE = (0.38, 0.43, 0.39)
STONE_LIGHT = (0.56, 0.57, 0.48)
WOOD = (0.33, 0.18, 0.11)
WOOD_LIGHT = (0.55, 0.34, 0.18)
BRASS = (0.74, 0.51, 0.23)
BRASS_LIGHT = (0.93, 0.72, 0.37)
PATINA = (0.19, 0.47, 0.46)
PATINA_DARK = (0.11, 0.31, 0.35)
CLOTH = (0.28, 0.53, 0.53)
CLOTH_EDGE = (0.58, 0.70, 0.57)
SOIL = (0.22, 0.17, 0.13)
LEAF = (0.30, 0.54, 0.29)
FLOWERS = ((0.97, 0.81, 0.48), (0.95, 0.59, 0.59), (0.91, 0.88, 0.71))


class PaintedMesh:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.colors = []

    def face(self, points, color):
        self.faces.append(tuple(points))
        self.colors.append(color)

    def box(self, center, size, color, yaw=0.0):
        cx, cy, cz = center
        hx, hy, hz = (value * 0.5 for value in size)
        c, s = math.cos(yaw), math.sin(yaw)
        start = len(self.vertices)
        for z in (-hz, hz):
            for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
                self.vertices.append((cx + c * x - s * y, cy + s * x + c * y, cz + z))
        for indices, shade in (
            ((3, 2, 1, 0), 0.7), ((4, 5, 6, 7), 1.05),
            ((0, 1, 5, 4), 0.88), ((1, 2, 6, 5), 0.78),
            ((2, 3, 7, 6), 0.72), ((3, 0, 4, 7), 1.0),
        ):
            self.face((start + index for index in indices), tuple(min(1.0, value * shade) for value in color))

    def rings(self, profiles, sides, color, top_color=None, phase=0.0):
        start = len(self.vertices)
        for z, radius in profiles:
            for i in range(sides):
                angle = i * math.tau / sides + phase
                self.vertices.append((math.cos(angle) * radius, math.sin(angle) * radius, z))
        self.face((start + i for i in reversed(range(sides))), color)
        for row in range(len(profiles) - 1):
            for i in range(sides):
                j = (i + 1) % sides
                shade = 0.82 + 0.15 * math.sin(i * math.tau / sides + 0.6)
                self.face((start + row * sides + i, start + row * sides + j,
                           start + (row + 1) * sides + j, start + (row + 1) * sides + i),
                          tuple(value * shade for value in color))
        top = start + (len(profiles) - 1) * sides
        self.face((top + i for i in range(sides)), top_color or color)

    def rod(self, start, end, radius, color, sides=5):
        start, end = Vector(start), Vector(end)
        axis = (end - start).normalized()
        guide = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((0, 1, 0))
        right = axis.cross(guide).normalized()
        up = axis.cross(right).normalized()
        offset = len(self.vertices)
        for point in (start, end):
            for i in range(sides):
                a = i * math.tau / sides
                self.vertices.append(tuple(point + radius * (right * math.cos(a) + up * math.sin(a))))
        self.face((offset + i for i in reversed(range(sides))), color)
        for i in range(sides):
            j = (i + 1) % sides
            self.face((offset + i, offset + j, offset + sides + j, offset + sides + i), color)
        self.face((offset + sides + i for i in range(sides)), color)

    def plate(self, outline, front_y, depth, color, edge_color):
        """Thick, capped front/back silhouette from (x, z) points."""
        start = len(self.vertices)
        for y in (front_y, front_y + depth):
            self.vertices.extend((x, y, z) for x, z in outline)
        n = len(outline)
        self.face((start + i for i in range(n)), color)
        self.face((start + n + i for i in reversed(range(n))), color)
        for i in range(n):
            j = (i + 1) % n
            self.face((start + i, start + j, start + n + j, start + n + i), edge_color)

    def petal(self, root, tip, half_width, color):
        root, tip = Vector(root), Vector(tip)
        middle = (root + tip) * 0.5
        diff = tip - root
        across = Vector((-diff.y, diff.x, 0)).normalized() * half_width
        start = len(self.vertices)
        outline = (root, middle + across, tip, middle - across)
        self.vertices.extend(tuple(point) for point in outline)
        self.vertices.extend(tuple(point - Vector((0, 0, 0.008))) for point in outline)
        self.face((start, start + 1, start + 2, start + 3), color)
        self.face((start + 7, start + 6, start + 5, start + 4), color)
        for i in range(4):
            j = (i + 1) % 4
            self.face((start + i, start + 4 + i, start + 4 + j, start + j), color)

    def object(self, name, material):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        if mesh.validate():
            raise ValueError(f"Invalid geometry for {name}")
        mesh.update()
        attribute = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
        for polygon, color in zip(mesh.polygons, self.colors):
            for loop in polygon.loop_indices:
                attribute.data[loop].color = (*color, 1.0)
        mesh.color_attributes.active_color = attribute
        mesh.materials.append(material)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        return obj


def wayfinder(mesh):
    mesh.rings([(0, 0.19), (0.04, 0.23), (0.12, 0.18)], 8, STONE, STONE_LIGHT, math.pi / 8)
    mesh.rings([(0.10, 0.09), (0.20, 0.09), (1.94, 0.075)], 8, WOOD, WOOD_LIGHT, math.pi / 8)
    for height in (0.18, 0.52, 1.06, 1.92):
        mesh.rings([(height, 0.105), (height + 0.032, 0.105)], 8, BRASS, BRASS_LIGHT, math.pi / 8)
    # Painted arrowboards point in opposite directions, with no misleading text.
    mesh.plate([(-0.84, 1.12), (0.76, 1.12), (0.76, 1.36), (-0.84, 1.36), (-1.06, 1.24)],
               -0.084, 0.055, WOOD_LIGHT, WOOD)
    mesh.plate([(-0.78, 1.49), (0.73, 1.49), (1.02, 1.63), (0.73, 1.77), (-0.78, 1.77)],
               -0.084, 0.055, PATINA, PATINA_DARK)
    for z, color in ((1.24, BRASS_LIGHT), (1.63, BRASS_LIGHT)):
        mesh.rings([(z - 0.042, 0.10), (z + 0.042, 0.10)], 8, color, color, math.pi / 8)
    # Wind-star marks at the tips read without small lettering.
    for x, z in ((-0.30, 1.24), (0.30, 1.63)):
        for dx, dz, xx, zz in ((-0.045, 0, 0, 0.052), (0, 0.052, 0.045, 0),
                               (0.045, 0, 0, -0.052), (0, -0.052, -0.045, 0)):
            mesh.rod((x + dx, -0.101, z + dz), (x + xx, -0.101, z + zz), 0.009, BRASS_LIGHT)
    mesh.rings([(1.94, 0.12), (2.05, 0.14), (2.12, 0.025)], 8, BRASS, BRASS_LIGHT, math.pi / 8)


def banner(mesh):
    mesh.rings([(0, 0.19), (0.05, 0.21), (0.12, 0.15)], 8, STONE, STONE_LIGHT, math.pi / 8)
    mesh.rings([(0.11, 0.088), (1.90, 0.070), (2.16, 0.058)], 8, WOOD, WOOD_LIGHT, math.pi / 8)
    mesh.rings([(0.16, 0.102), (0.20, 0.102)], 8, BRASS, BRASS_LIGHT, math.pi / 8)
    mesh.rings([(2.14, 0.09), (2.19, 0.09), (2.28, 0.014)], 8, BRASS, BRASS_LIGHT, math.pi / 8)
    mesh.rod((-0.12, -0.06, 2.08), (0.89, -0.06, 2.08), 0.045, WOOD_LIGHT, 8)
    mesh.rod((0.13, -0.06, 1.85), (0.34, -0.06, 2.04), 0.032, WOOD_LIGHT)
    # Reinforced two-pronged cloth, fixed in place with a clear silhouette.
    mesh.plate([(0.20, 2.02), (0.80, 2.02), (0.80, 1.02), (0.50, 1.18), (0.20, 1.02)],
               -0.136, 0.020, CLOTH, CLOTH_EDGE)
    mesh.box((0.50, -0.151, 1.94), (0.59, 0.014, 0.065), BRASS_LIGHT)
    for x in (0.235, 0.765):
        mesh.rod((x, -0.153, 1.08), (x, -0.153, 1.88), 0.010, BRASS)
    for (x0, z0), (x1, z1) in zip(
        ((0.50, 1.77), (0.36, 1.59), (0.50, 1.42), (0.64, 1.59)),
        ((0.36, 1.59), (0.50, 1.42), (0.64, 1.59), (0.50, 1.77)),
    ):
        mesh.rod((x0, -0.160, z0), (x1, -0.160, z1), 0.017, BRASS_LIGHT)
    mesh.box((0.50, -0.171, 1.59), (0.058, 0.015, 0.058), PATINA_DARK)


def planter(mesh):
    mesh.box((0, 0, 0.18), (1.22, 0.59, 0.36), WOOD)
    mesh.box((0, 0, 0.37), (1.05, 0.43, 0.035), SOIL)
    for y in (-0.275, 0.275):
        mesh.box((0, y, 0.35), (1.27, 0.075, 0.072), WOOD_LIGHT)
        mesh.box((0, y * 1.02, 0.15), (1.20, 0.025, 0.032), PATINA)
    for x in (-0.59, 0.59):
        mesh.box((x, 0, 0.35), (0.075, 0.60, 0.075), WOOD_LIGHT)
        for y in (-0.28, 0.28):
            mesh.box((x, y, 0.29), (0.08, 0.018, 0.10), BRASS)
    for index, x in enumerate((-0.43, -0.28, -0.13, 0.02, 0.17, 0.32, 0.45)):
        y = 0.115 if index % 2 else -0.105
        z = 0.61 + 0.025 * (index % 3)
        mesh.rod((x, y, 0.38), (x + 0.015, y, z), 0.014, LEAF)
        for sign in (-1, 1):
            mesh.petal((x, y, 0.48), (x + sign * 0.11, y + 0.045, 0.46), 0.035, LEAF)
        for petal in range(5):
            angle = math.tau * petal / 5 + 0.25 * index
            mesh.petal((x + 0.015, y, z),
                       (x + 0.015 + math.cos(angle) * 0.105,
                        y + math.sin(angle) * 0.105, z + 0.038),
                       0.047, FLOWERS[index % len(FLOWERS)])
        # Gold pollen bead, not another draw-call/material.
        mesh.rod((x + 0.015, y, z - 0.005), (x + 0.015, y, z + 0.035), 0.032, BRASS_LIGHT, 6)


def material():
    mat = bpy.data.materials.new("Sunmeadow / painted wayfarer kit")
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    color = mat.node_tree.nodes.new("ShaderNodeVertexColor")
    color.layer_name = "Col"
    shader = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.79
    output = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(color.outputs["Color"], shader.inputs["Base Color"])
    mat.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return mat


def render_review(objects, path):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 760
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    world = bpy.data.worlds.new("Studio sky")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.39, 0.52, 0.54, 1.0)
    background.inputs["Strength"].default_value = 0.8
    scene.world = world
    for name, location, energy in (("Sun key", (2, -4, 5), 550), ("Sky fill", (-3, 1, 4), 330)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.shape = "DISK"
        light.size = 4
        obj = bpy.data.objects.new(name, light)
        bpy.context.collection.objects.link(obj)
        obj.location = location
        obj.rotation_euler = (Vector((0, 0, 1)) - obj.location).to_track_quat("-Z", "Y").to_euler()
    camera_data = bpy.data.cameras.new("Review camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 6.6
    camera = bpy.data.objects.new("Review camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (4.0, -9.0, 4.5)
    camera.rotation_euler = (Vector((0, 0, 1.05)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    for obj, x in zip(objects, (-2.0, 0.0, 2.1)):
        obj.location.x = x
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
shared_material = material()
objects = []
for name, builder in (
    ("prop_wayfinder_sign_01", wayfinder),
    ("prop_village_banner_01", banner),
    ("prop_flower_planter_01", planter),
):
    painted = PaintedMesh()
    builder(painted)
    obj = painted.object(name, shared_material)
    triangles = sum(len(face.vertices) - 2 for face in obj.data.polygons)
    assert 0 < triangles <= 1500, f"{name} exceeds the prop budget: {triangles} triangles"
    assert min(vertex.co.z for vertex in obj.data.vertices) >= 0
    print(f"{name}: {triangles} triangles, height {max(vertex.co.z for vertex in obj.data.vertices):.2f} m")
    objects.append(obj)

args.out.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.export_scene.gltf(
    filepath=str(args.out.resolve()), export_format="GLB", use_selection=True,
    export_yup=True, export_apply=True, export_materials="EXPORT",
    export_vertex_color="MATERIAL", export_animations=False,
    export_cameras=False, export_lights=False, export_extras=False,
)
render_review(objects, args.review.resolve())
args.blend.parent.mkdir(parents=True, exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(args.blend.resolve()))
print(f"Runtime: {args.out}\nMaster: {args.blend}\nReview: {args.review}")
