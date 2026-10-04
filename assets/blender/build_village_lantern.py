"""Build an original, painted 1.2 m Sunmeadow lantern for the game.

From the repository root (Blender 5.2):
    blender --background --factory-startup --python-exit-code 1 \
        --python assets/blender/build_village_lantern.py

One mesh / one material / no textures. The material reads the Col vertex color
attribute, so the GLB keeps its painted wood, linen and patinated brass colors.
The pivot is at the base center; Blender Z-up exports as glTF Y-up. The preview
stage is not included in the GLB. The Blender master includes its camera/lights.
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
parser.add_argument("--out", type=Path, default=ROOT / "apps/client/src/assets/models/prop_village_lantern_01.glb")
parser.add_argument("--blend", type=Path, default=ROOT / "assets/models/props/village_lantern_01.blend")
parser.add_argument("--review", type=Path, default=ROOT / "assets/models/props/review/village_lantern_01.png")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

# Face colors are linear values; the glTF exporter encodes COLOR_0 for the game.
STONE = (0.38, 0.43, 0.39)
STONE_EDGE = (0.57, 0.57, 0.47)
WOOD = (0.32, 0.18, 0.11)
WOOD_LIGHT = (0.55, 0.34, 0.18)
WOOD_SHADE = (0.21, 0.13, 0.09)
BRASS = (0.73, 0.51, 0.24)
BRASS_LIGHT = (0.93, 0.73, 0.38)
PATINA = (0.22, 0.48, 0.46)
PATINA_DARK = (0.12, 0.31, 0.35)
LINEN_BOTTOM = (0.98, 0.66, 0.29)
LINEN_MIDDLE = (1.0, 0.83, 0.48)
LINEN_TOP = (0.99, 0.93, 0.68)


class PaintedMesh:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.colors = []

    def face(self, indices, color):
        self.faces.append(tuple(indices))
        self.colors.append(color)

    def box(self, center, size, color, yaw=0.0):
        cx, cy, cz = center
        hx, hy, hz = (value * 0.5 for value in size)
        angle = math.cos(yaw), math.sin(yaw)
        start = len(self.vertices)
        for z in (-hz, hz):
            for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)):
                self.vertices.append((cx + angle[0] * x - angle[1] * y,
                                      cy + angle[1] * x + angle[0] * y, cz + z))
        for indices, tint in (
            ((3, 2, 1, 0), 0.62), ((4, 5, 6, 7), 1.12),
            ((0, 1, 5, 4), 0.91), ((1, 2, 6, 5), 0.79),
            ((2, 3, 7, 6), 0.74), ((3, 0, 4, 7), 1.0),
        ):
            self.face((start + index for index in indices), tuple(min(1.0, value * tint) for value in color))

    def rings(self, profiles, sides, color, top_color=None, phase=0.0):
        """Join concentric ring profiles (z, radius) with flat-shaded sides."""
        start = len(self.vertices)
        for z, radius in profiles:
            for i in range(sides):
                angle = math.tau * i / sides + phase
                self.vertices.append((math.cos(angle) * radius, math.sin(angle) * radius, z))
        self.face((start + i for i in reversed(range(sides))), color)
        for row in range(len(profiles) - 1):
            for i in range(sides):
                j = (i + 1) % sides
                shade = 0.82 + 0.16 * math.sin(math.tau * i / sides + 0.7)
                self.face((start + row * sides + i, start + row * sides + j,
                           start + (row + 1) * sides + j, start + (row + 1) * sides + i),
                          tuple(value * shade for value in color))
        top = start + (len(profiles) - 1) * sides
        self.face((top + i for i in range(sides)), top_color or color)

    def rod(self, start, end, radius, color, sides=6):
        """Short attached reinforcement or inlaid motif, capped at both ends."""
        start, end = Vector(start), Vector(end)
        axis = (end - start).normalized()
        guide = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((0, 1, 0))
        right = axis.cross(guide).normalized()
        up = axis.cross(right).normalized()
        offset = len(self.vertices)
        for point in (start, end):
            for i in range(sides):
                angle = math.tau * i / sides
                self.vertices.append(tuple(point + radius * (right * math.cos(angle) + up * math.sin(angle))))
        self.face((offset + i for i in reversed(range(sides))), color)
        for i in range(sides):
            j = (i + 1) % sides
            self.face((offset + i, offset + j, offset + sides + j, offset + sides + i), color)
        self.face((offset + sides + i for i in range(sides)), color)

    def make_object(self):
        mesh = bpy.data.meshes.new("Lantern / painted mesh")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.validate()
        mesh.update()
        colors = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
        for polygon, color in zip(mesh.polygons, self.colors):
            for index in polygon.loop_indices:
                colors.data[index].color = (*color, 1.0)
        mesh.color_attributes.active_color = colors
        obj = bpy.data.objects.new("prop_village_lantern_01", mesh)
        bpy.context.collection.objects.link(obj)
        return obj


def build_lantern():
    mesh = PaintedMesh()
    # Broad faceted stone shoe gives the narrow timber post a stable base.
    mesh.rings([(0, 0.22), (0.04, 0.255), (0.095, 0.22), (0.125, 0.17)], 8, STONE, STONE_EDGE, math.pi / 8)
    mesh.rings([(0.115, 0.105), (0.16, 0.105)], 8, BRASS, BRASS_LIGHT, math.pi / 8)
    mesh.rings([(0.145, 0.108), (0.26, 0.082), (0.65, 0.071), (0.74, 0.097)], 8, WOOD, WOOD_LIGHT, math.pi / 8)
    for height in (0.24, 0.57, 0.70):
        mesh.rings([(height, 0.096), (height + 0.025, 0.096)], 8, BRASS, BRASS_LIGHT, math.pi / 8)
    for side in (-1, 1):
        mesh.rod((side * 0.06, -0.04, 0.62), (side * 0.17, -0.10, 0.77), 0.025, WOOD_LIGHT)
        mesh.rod((side * 0.06, 0.04, 0.62), (side * 0.17, 0.10, 0.77), 0.025, WOOD_LIGHT)

    # Four warm linen panes. Broad wood rails protect the corners and keep the
    # panels readable at gameplay distance; the motif is inlaid, not dangling.
    mesh.rings([(0.71, 0.229), (0.765, 0.229)], 4, PATINA_DARK, BRASS_LIGHT, math.pi / 4)
    for direction in range(4):
        yaw = direction * math.pi / 2
        c, s = math.cos(yaw), math.sin(yaw)

        def on_face(x, y, z):
            return (c * x - s * y, s * x + c * y, z)

        for z, color in ((0.824, LINEN_BOTTOM), (0.899, LINEN_MIDDLE), (0.974, LINEN_TOP)):
            mesh.box(on_face(0, -0.204, z), (0.327, 0.018, 0.076), color, yaw)
        for x in (-0.189, 0.189):
            mesh.box(on_face(x, -0.203, 0.9), (0.036, 0.042, 0.306), WOOD_LIGHT, yaw)
        for z in (0.752, 1.046):
            mesh.box(on_face(0, -0.207, z), (0.402, 0.048, 0.036), BRASS, yaw)
        # An original four-point wind-star motif, echoed on every face.
        corners = [(-0.062, 0.899), (0, 0.968), (0.062, 0.899), (0, 0.830)]
        for (x0, z0), (x1, z1) in zip(corners, corners[1:] + corners[:1]):
            mesh.rod(on_face(x0, -0.231, z0), on_face(x1, -0.231, z1), 0.008, PATINA_DARK, 5)
        mesh.box(on_face(0, -0.238, 0.9), (0.026, 0.01, 0.026), BRASS_LIGHT, yaw)

    # Dark pagoda-like eaves and a small integral finial finish at 1.20 m.
    mesh.rings([(1.053, 0.265), (1.085, 0.31), (1.16, 0.12)], 4, PATINA, PATINA_DARK, math.pi / 4)
    mesh.rings([(1.158, 0.087), (1.176, 0.09), (1.20, 0.018)], 8, BRASS, BRASS_LIGHT, math.pi / 8)
    return mesh.make_object()


def make_material():
    material = bpy.data.materials.new("Sunmeadow / painted lantern")
    material.use_nodes = True
    material.diffuse_color = (*WOOD, 1.0)
    material.node_tree.nodes.clear()
    painted = material.node_tree.nodes.new("ShaderNodeVertexColor")
    painted.layer_name = "Col"
    shader = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Metallic"].default_value = 0.0
    shader.inputs["Roughness"].default_value = 0.78
    output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(painted.outputs["Color"], shader.inputs["Base Color"])
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def render_review(obj, path):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("Studio sky")
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.44, 0.56, 0.58, 1.0)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.8
    scene.world = world

    def area_light(name, location, energy, size):
        light = bpy.data.lights.new(name, type="AREA")
        light.energy = energy
        light.shape = "DISK"
        light.size = size
        target = bpy.data.objects.new(name, light)
        bpy.context.collection.objects.link(target)
        target.location = location
        target.rotation_euler = (Vector((0, 0, 0.7)) - target.location).to_track_quat("-Z", "Y").to_euler()

    area_light("Warm key", (2.1, -2.8, 3.0), 300, 3.0)
    area_light("Cool fill", (-2.0, 1.6, 2.4), 220, 2.8)
    camera_data = bpy.data.cameras.new("Review camera")
    camera = bpy.data.objects.new("Review camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (2.0, -3.1, 1.8)
    camera.rotation_euler = (Vector((0, 0, 0.61)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 1.72
    scene.camera = camera
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
lantern = build_lantern()
lantern.data.materials.append(make_material())
triangles = sum(len(polygon.vertices) - 2 for polygon in lantern.data.polygons)
assert 0 < triangles <= 1500, f"Lantern exceeds the prop budget: {triangles} triangles"
assert min(vertex.co.z for vertex in lantern.data.vertices) >= 0.0
assert max(vertex.co.z for vertex in lantern.data.vertices) <= 1.201
print(f"Village lantern: {triangles} triangles, 1 mesh, 1 material, 1.20 m")

args.out.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="DESELECT")
lantern.select_set(True)
bpy.context.view_layer.objects.active = lantern
bpy.ops.export_scene.gltf(
    filepath=str(args.out.resolve()), export_format="GLB", use_selection=True,
    export_yup=True, export_apply=True, export_materials="EXPORT",
    export_vertex_color="MATERIAL", export_animations=False,
    export_cameras=False, export_lights=False, export_extras=False,
)
render_review(lantern, args.review.resolve())
args.blend.parent.mkdir(parents=True, exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(args.blend.resolve()))
print(f"Runtime: {args.out}\nMaster: {args.blend}\nReview: {args.review}")
