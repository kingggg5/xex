"""Shared R5 city-kit helpers (Blender 5.2, metric, Z-up).

Every kit module (terrain, buildings, landmarks, props, vegetation) imports
this file so that materials, UV texel density, bevel/shading rules, vertex
colour AO/grime, preview renders and GLB export behave identically.

Conventions (see docs/city-art-roadmap.md, "R5 production contract"):
- 1 Blender unit = 1 m, Z up. Layout origin = fountain centre (layout.json).
- UV0 "UVMap": world-scale tiling. One texture repeat = MATERIALS[name]['tile'] m.
  Walls/ground use box projection; roofs, beams and planks use aligned planar
  projection so shingle rows follow eaves and wood grain follows the beam.
- COLOR_0 "Col": multiplies base colour. Holds baked AO, cavity dirt, edge
  highlights and per-object tint. Always sRGB, default white.
- Foundry textures live in assets/models/reference-city/r5/textures as
  <name>_albedo.png, <name>_normal.png (OpenGL +Y), <name>_orm.png
  (R = AO, G = roughness, B = metallic). A material falls back to its flat
  colour until its foundry maps exist, so kits can be built in parallel.
- Objects whose names start with anim_, fx_, emit_ or light_ are runtime
  hooks: never merged, exported as separately named nodes.
"""
from __future__ import annotations

import bpy
import bmesh
import json
import math
import random
import zlib
from pathlib import Path
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[4]
R5_DIR = ROOT / 'assets' / 'models' / 'reference-city' / 'r5'
TEX_DIR = R5_DIR / 'textures'
REVIEW_DIR = R5_DIR / 'review'
LAYOUT_PATH = ROOT / 'assets' / 'blender' / 'city_r5' / 'layout.json'
RUNTIME_PREFIXES = ('anim_', 'fx_', 'emit_', 'light_')


def load_layout() -> dict:
    return json.loads(LAYOUT_PATH.read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# Material library. Colours are linear-ish fallbacks matched to the reference
# palette; the foundry maps replace them. tile = metres per texture repeat.
# ---------------------------------------------------------------------------
MATERIALS: dict[str, dict] = {
    # Masonry
    'stone_wall_warm':    dict(tile=2.4, color=(0.74, 0.66, 0.55), rough=0.86),
    'stone_trim_carved':  dict(tile=1.6, color=(0.86, 0.80, 0.69), rough=0.80),
    'stone_foundation':   dict(tile=2.4, color=(0.47, 0.46, 0.46), rough=0.88),
    'stone_wall_mossy':   dict(tile=2.4, color=(0.60, 0.60, 0.46), rough=0.90),
    'marble_statue':      dict(tile=1.6, color=(0.86, 0.87, 0.90), rough=0.45),
    # Ground
    'plaza_flagstone':    dict(tile=4.0, color=(0.76, 0.69, 0.58), rough=0.80),
    'paver_surface':      dict(tile=2.0, color=(0.80, 0.74, 0.64), rough=0.78),
    'stone_accent_bluegrey': dict(tile=2.0, color=(0.46, 0.50, 0.58), rough=0.80),
    'cobble_path':        dict(tile=2.6, color=(0.60, 0.55, 0.49), rough=0.86),
    'stone_tiles_dark':   dict(tile=3.0, color=(0.33, 0.35, 0.40), rough=0.82),
    'grass_ground':       dict(tile=6.0, color=(0.33, 0.52, 0.14), rough=0.95),
    'dirt_path':          dict(tile=4.0, color=(0.52, 0.40, 0.27), rough=0.95),
    'cliff_rock':         dict(tile=9.0, color=(0.47, 0.38, 0.29), rough=0.92),
    # Roofs
    'roof_slate_blue':    dict(tile=2.2, color=(0.11, 0.19, 0.55), rough=0.55),
    'roof_slate_navy':    dict(tile=2.2, color=(0.07, 0.11, 0.33), rough=0.55),
    'roof_shingle_green': dict(tile=2.2, color=(0.13, 0.36, 0.24), rough=0.62),
    'roof_tile_red':      dict(tile=2.2, color=(0.58, 0.18, 0.11), rough=0.62),
    # Walls and wood
    'plaster_cream':      dict(tile=3.0, color=(0.89, 0.82, 0.68), rough=0.92),
    'timber_dark':        dict(tile=2.0, color=(0.25, 0.14, 0.07), rough=0.72),
    'wood_planks_dark':   dict(tile=2.0, color=(0.32, 0.19, 0.10), rough=0.78),
    'wood_planks_light':  dict(tile=2.0, color=(0.62, 0.43, 0.25), rough=0.74),
    # Metals
    'metal_iron':         dict(tile=1.0, color=(0.10, 0.10, 0.12), rough=0.48, metal=1.0),
    'metal_gold':         dict(tile=1.0, color=(0.83, 0.58, 0.22), rough=0.32, metal=1.0),
    # Cloth (UV 0..1 per panel for stripes/emblems)
    'cloth_blue':         dict(tile=1.0, color=(0.07, 0.15, 0.55), rough=0.92),
    'cloth_red':          dict(tile=1.0, color=(0.66, 0.11, 0.09), rough=0.92),
    'cloth_cream':        dict(tile=1.0, color=(0.91, 0.84, 0.70), rough=0.92),
    'cloth_green':        dict(tile=1.0, color=(0.16, 0.42, 0.24), rough=0.92),
    'cloth_stripe_red':   dict(tile=1.0, color=(0.80, 0.40, 0.36), rough=0.92, unit_uv=True),
    'cloth_stripe_blue':  dict(tile=1.0, color=(0.42, 0.50, 0.78), rough=0.92, unit_uv=True),
    'banner_emblem':      dict(tile=1.0, color=(0.08, 0.16, 0.56), rough=0.9, unit_uv=True),
    # Emissive and transparent
    'glass_window_warm':  dict(tile=1.0, color=(1.0, 0.62, 0.28), rough=0.2, emission=(1.0, 0.55, 0.22), strength=2.2),
    'glass_window_blue':  dict(tile=1.0, color=(0.45, 0.70, 1.0), rough=0.2, emission=(0.35, 0.65, 1.0), strength=2.0),
    'magic_blue':         dict(tile=1.0, color=(0.30, 0.72, 1.0), rough=0.2, emission=(0.25, 0.65, 1.0), strength=7.0),
    'magic_purple':       dict(tile=1.0, color=(0.68, 0.30, 1.0), rough=0.2, emission=(0.60, 0.22, 1.0), strength=7.0),
    'magic_green':        dict(tile=1.0, color=(0.40, 1.0, 0.45), rough=0.2, emission=(0.30, 1.0, 0.40), strength=6.0),
    'fire_glow':          dict(tile=1.0, color=(1.0, 0.45, 0.10), rough=0.5, emission=(1.0, 0.42, 0.08), strength=9.0),
    'water':              dict(tile=6.0, color=(0.10, 0.48, 0.78), rough=0.06, alpha=0.82),
    'water_foam':         dict(tile=4.0, color=(0.85, 0.95, 1.0), rough=0.3, alpha=0.9),
}


def define_material(name: str, **spec) -> bpy.types.Material:
    """Register a department-local material (same node layout as the library).

    Required: tile (m per repeat) and color. Optional: rough, metal, emission,
    strength, alpha, normal_strength, unit_uv. Foundry maps named
    <name>_albedo/_normal/_orm.png are picked up automatically if present.
    """
    if name in MATERIALS and MATERIALS[name] != spec:
        raise ValueError(f'Material {name!r} already defined differently')
    MATERIALS[name] = spec
    return get_material(name)


def _image(path: Path, colorspace: str):
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = colorspace
    return image


def get_material(name: str) -> bpy.types.Material:
    """Return the shared material, building it from foundry maps if present."""
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    spec = MATERIALS.get(name)
    if spec is None:
        raise KeyError(f'Unknown city material {name!r}; add it to citykit.MATERIALS')
    mat = bpy.data.materials.new(name)
    mat['city_tile_m'] = spec['tile']
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get('Principled BSDF')
    out = nodes.get('Material Output')
    color = (*spec['color'], 1.0)
    mat.diffuse_color = color
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = spec.get('rough', 0.8)
    bsdf.inputs['Metallic'].default_value = spec.get('metal', 0.0)

    # Vertex colour multiplier (AO, cavity dirt, edge highlights, tint).
    vcol = nodes.new('ShaderNodeVertexColor')
    vcol.layer_name = 'Col'
    vcol.location = (-500, 360)
    mix = nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    mix.location = (-220, 300)
    links.new(vcol.outputs['Color'], mix.inputs['B'])

    albedo_path = TEX_DIR / f'{name}_albedo.png'
    normal_path = TEX_DIR / f'{name}_normal.png'
    orm_path = TEX_DIR / f'{name}_orm.png'
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'UVMap'
    uv.location = (-1100, 0)
    if albedo_path.exists():
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = _image(albedo_path, 'sRGB')
        tex.location = (-800, 380)
        links.new(uv.outputs['UV'], tex.inputs['Vector'])
        links.new(tex.outputs['Color'], mix.inputs['A'])
        if spec.get('alpha_from_texture'):
            links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
    else:
        mix.inputs['A'].default_value = color
    links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])

    if orm_path.exists():
        orm = nodes.new('ShaderNodeTexImage')
        orm.image = _image(orm_path, 'Non-Color')
        orm.location = (-800, 60)
        links.new(uv.outputs['UV'], orm.inputs['Vector'])
        sep = nodes.new('ShaderNodeSeparateColor')
        sep.location = (-520, 60)
        links.new(orm.outputs['Color'], sep.inputs['Color'])
        links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
        links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])
        # glTF occlusion (R channel) through the exporter's custom group.
        group = _gltf_output_group()
        gnode = nodes.new('ShaderNodeGroup')
        gnode.node_tree = group
        gnode.location = (200, -300)
        links.new(sep.outputs['Red'], gnode.inputs['Occlusion'])
    if normal_path.exists():
        ntex = nodes.new('ShaderNodeTexImage')
        ntex.image = _image(normal_path, 'Non-Color')
        ntex.location = (-800, -260)
        links.new(uv.outputs['UV'], ntex.inputs['Vector'])
        nmap = nodes.new('ShaderNodeNormalMap')
        nmap.inputs['Strength'].default_value = spec.get('normal_strength', 1.0)
        nmap.location = (-480, -260)
        links.new(ntex.outputs['Color'], nmap.inputs['Color'])
        links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])

    if 'emission' in spec:
        bsdf.inputs['Emission Color'].default_value = (*spec['emission'], 1.0)
        bsdf.inputs['Emission Strength'].default_value = spec['strength']
    if 'alpha' in spec:
        bsdf.inputs['Alpha'].default_value = spec['alpha']
        try:
            mat.surface_render_method = 'BLENDED'
        except AttributeError:
            mat.blend_method = 'BLEND'
    return mat


def _gltf_output_group():
    group = bpy.data.node_groups.get('glTF Material Output')
    if group:
        return group
    group = bpy.data.node_groups.new('glTF Material Output', 'ShaderNodeTree')
    group.interface.new_socket('Occlusion', in_out='INPUT', socket_type='NodeSocketFloat')
    group.interface.new_socket('Thickness', in_out='INPUT', socket_type='NodeSocketFloat')
    group.nodes.new('NodeGroupInput')
    return group


# ---------------------------------------------------------------------------
# Scene and object helpers
# ---------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    return scene


def collection(name: str, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def new_object(name: str, verts, faces, material: str | None = None, col=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    mesh.validate(clean_customdata=False)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    (col or bpy.context.scene.collection).objects.link(obj)
    if material:
        mesh.materials.append(get_material(material))
    return obj


def object_from_bmesh(name: str, bm: bmesh.types.BMesh, material: str | None = None, col=None):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    (col or bpy.context.scene.collection).objects.link(obj)
    if material:
        mesh.materials.append(get_material(material))
    return obj


def set_material(obj, material: str):
    obj.data.materials.clear()
    obj.data.materials.append(get_material(material))
    return obj


def apply_transform(obj):
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    return obj


def bevel(obj, width=0.03, segments=2, angle_deg=40.0, harden=True):
    """Chamfer hard edges so they catch light, then apply the modifier."""
    mod = obj.modifiers.new('bevel', 'BEVEL')
    mod.width = width
    mod.segments = segments
    mod.limit_method = 'ANGLE'
    mod.angle_limit = math.radians(angle_deg)
    mod.harden_normals = harden
    mod.miter_outer = 'MITER_ARC'
    apply_modifiers(obj)
    return obj


def apply_modifiers(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(deps)
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=deps)
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def shade_smooth(obj, angle_deg=35.0):
    mesh = obj.data
    mesh.shade_smooth()
    mesh.set_sharp_from_angle(angle=math.radians(angle_deg))
    return obj


def join(objects, name: str | None = None):
    objects = [o for o in objects if o is not None]
    if not objects:
        return None
    if len(objects) == 1:
        if name:
            objects[0].name = name
        return objects[0]
    ctx = {'active_object': objects[0], 'selected_editable_objects': objects, 'object': objects[0]}
    with bpy.context.temp_override(**ctx):
        bpy.ops.object.join()
    if name:
        objects[0].name = name
    return objects[0]


# ---------------------------------------------------------------------------
# UVs: consistent texel density across the whole city.
# ---------------------------------------------------------------------------
def _uv_layer(mesh):
    return mesh.uv_layers.get('UVMap') or mesh.uv_layers.new(name='UVMap')


def uv_box(obj, tile_m: float | None = None, world=True):
    """Dominant-axis box projection; V always follows world Z on walls."""
    mesh = obj.data
    if tile_m is None:
        mat = mesh.materials[0] if mesh.materials else None
        tile_m = float(mat.get('city_tile_m', 2.0)) if mat else 2.0
    scale = 1.0 / tile_m
    layer = _uv_layer(mesh)
    mw = obj.matrix_world if world else Matrix.Identity(4)
    nmat = mw.to_3x3().inverted().transposed()
    for poly in mesh.polygons:
        n = (nmat @ poly.normal)
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = mw @ mesh.vertices[mesh.loops[li].vertex_index].co
            if ax == 0:
                u, v = co.y * (1 if n.x > 0 else -1), co.z
            elif ax == 1:
                u, v = co.x * (-1 if n.y > 0 else 1), co.z
            else:
                u, v = co.x, co.y
            layer.data[li].uv = (u * scale, v * scale)
    return obj


def uv_planar(obj, origin, u_axis, v_axis, tile_m: float, polygons=None):
    """Aligned planar projection (roofs: u along the eave, v down the slope)."""
    mesh = obj.data
    layer = _uv_layer(mesh)
    o, ua, va = Vector(origin), Vector(u_axis).normalized(), Vector(v_axis).normalized()
    scale = 1.0 / tile_m
    polys = mesh.polygons if polygons is None else [mesh.polygons[i] for i in polygons]
    for poly in polys:
        for li in poly.loop_indices:
            co = obj.matrix_world @ mesh.vertices[mesh.loops[li].vertex_index].co - o
            layer.data[li].uv = (co.dot(ua) * scale, co.dot(va) * scale)
    return obj


def uv_beam(obj, tile_m=2.0):
    """Wood grain follows each face's longest in-plane direction."""
    mesh = obj.data
    layer = _uv_layer(mesh)
    scale = 1.0 / tile_m
    for poly in mesh.polygons:
        verts = [obj.matrix_world @ mesh.vertices[i].co for i in poly.vertices]
        n = poly.normal
        best = None
        for i in range(len(verts)):
            e = verts[(i + 1) % len(verts)] - verts[i]
            if best is None or e.length > best.length:
                best = e
        ua = best.normalized() if best and best.length > 1e-6 else Vector((1, 0, 0))
        va = n.cross(ua).normalized()
        for li in poly.loop_indices:
            co = obj.matrix_world @ mesh.vertices[mesh.loops[li].vertex_index].co
            layer.data[li].uv = (co.dot(ua) * scale, co.dot(va) * scale)
    return obj


def uv_unit(obj):
    """0..1 per quad face (cloth stripes, banners, signs)."""
    mesh = obj.data
    layer = _uv_layer(mesh)
    corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for poly in mesh.polygons:
        for k, li in enumerate(poly.loop_indices):
            layer.data[li].uv = corners[k % 4]
    return obj


# ---------------------------------------------------------------------------
# Vertex colour: AO, cavity dirt, edge highlights and tint (COLOR_0).
# ---------------------------------------------------------------------------
def _color_layer(mesh):
    attr = mesh.color_attributes.get('Col')
    if attr is None:
        attr = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        for d in attr.data:
            d.color = (1.0, 1.0, 1.0, 1.0)
    mesh.color_attributes.active_color = attr
    return attr


def vertex_paint(obj, *, tint=(1.0, 1.0, 1.0), ground_z=None, ground_dark=0.55, ground_fade=1.2,
                 cavity=0.35, edge=0.18, jitter=0.04, seed=0):
    """Stylized 'expert texture' pass painted into COLOR_0.

    - cavity: darkens concave vertices (dirt in joints, under trims)
    - edge: brightens convex vertices (worn, light-catching edges)
    - ground_z: contact darkening within ground_fade metres of the ground
    - jitter: per-object value variation so repeated kit parts differ
    """
    mesh = obj.data
    rnd = random.Random(seed or zlib.crc32(obj.name.encode('utf-8')))
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    curvature = [0.0] * len(bm.verts)
    for v in bm.verts:
        if not v.link_edges:
            continue
        acc = 0.0
        for e in v.link_edges:
            other = e.other_vert(v)
            d = other.co - v.co
            if d.length > 1e-6:
                acc += v.normal.dot(d.normalized())
        curvature[v.index] = acc / len(v.link_edges)  # >0 concave, <0 convex
    bm.free()
    attr = _color_layer(mesh)
    base = 1.0 + rnd.uniform(-jitter, jitter)
    mw = obj.matrix_world
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            c = curvature[vi]
            shade = base
            if c > 0:
                shade *= 1.0 - cavity * min(1.0, c * 2.5)
            else:
                shade *= 1.0 + edge * min(1.0, -c * 2.5)
            if ground_z is not None:
                z = (mw @ mesh.vertices[vi].co).z - ground_z
                if z < ground_fade:
                    t = max(0.0, z) / ground_fade
                    shade *= ground_dark + (1.0 - ground_dark) * (t * t * (3 - 2 * t))
            r, g, b = (min(1.0, max(0.0, tint[i] * shade)) for i in range(3))
            attr.data[li].color = (r, g, b, 1.0)
    return obj


def ensure_white_vertex_colors(obj):
    _color_layer(obj.data)
    return obj


def normalize_imported_gltf_prop_attributes(obj):
    """Keep one material UV set and one COLOR_0 layer for the shared city mesh contract."""
    if obj.type != 'MESH':
        raise TypeError(f'Expected an imported mesh, received {obj.type}.')
    mesh = obj.data
    uv0 = mesh.uv_layers.get('UVMap')
    if uv0 is None and len(mesh.uv_layers):
        uv0 = mesh.uv_layers[0]
        uv0.name = 'UVMap'
    if uv0 is None:
        raise RuntimeError(f'{obj.name} has no UV set for its PBR textures.')
    for layer in list(mesh.uv_layers):
        if layer != uv0:
            mesh.uv_layers.remove(layer)

    color0 = mesh.color_attributes.get('Col') or mesh.color_attributes.get('Color')
    if color0 is None and len(mesh.color_attributes):
        color0 = mesh.color_attributes[0]
    if color0 is None:
        raise RuntimeError(f'{obj.name} has no vertex-color set to map to COLOR_0.')
    for layer in list(mesh.color_attributes):
        if layer != color0:
            mesh.color_attributes.remove(layer)
    color0.name = 'Col'
    mesh.color_attributes.active_color = color0
    return obj


def bake_vertex_ao(objects, samples=24, distance=1.2):
    """Cycles AO bake into COLOR_0, multiplied over existing colour."""
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.cycles.device = 'CPU'
    scene.world = scene.world or bpy.data.worlds.new('World')
    scene.world.light_settings.distance = distance
    for obj in objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        keep = _color_layer(mesh)
        prev = [tuple(d.color) for d in keep.data]
        ao = mesh.color_attributes.new('AO_tmp', 'BYTE_COLOR', 'CORNER')
        mesh.color_attributes.active_color = ao
        with bpy.context.temp_override(active_object=obj, selected_objects=[obj], object=obj):
            bpy.ops.object.bake(type='AO', target='VERTEX_COLORS')
        for i, d in enumerate(ao.data):
            a = d.color[0]
            p = prev[i]
            keep.data[i].color = (p[0] * a, p[1] * a, p[2] * a, 1.0)
        mesh.color_attributes.remove(mesh.color_attributes.get('AO_tmp'))
        mesh.color_attributes.active_color = mesh.color_attributes.get('Col')


# ---------------------------------------------------------------------------
# Basic geometry builders (kits add their own specialised ones).
# ---------------------------------------------------------------------------
def box(name, center, size, material, col=None, rot_z=0.0):
    w, d, h = (s * 0.5 for s in size)
    verts = [(-w, -d, -h), (w, -d, -h), (w, d, -h), (-w, d, -h), (-w, -d, h), (w, -d, h), (w, d, h), (-w, d, h)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    obj = new_object(name, verts, faces, material, col)
    obj.matrix_world = Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot_z, 4, 'Z')
    return obj


def lathe(name, profile, segments=24, material=None, col=None, center=(0, 0, 0), cap_top=True, cap_bottom=True):
    """Revolve a (radius, z) profile around Z. Profiles run bottom to top."""
    verts, faces = [], []
    n = len(profile)
    for s in range(segments):
        a = s * math.tau / segments
        ca, sa = math.cos(a), math.sin(a)
        for r, z in profile:
            verts.append((center[0] + r * ca, center[1] + r * sa, center[2] + z))
    for s in range(segments):
        s2 = (s + 1) % segments
        for i in range(n - 1):
            faces.append((s * n + i, s2 * n + i, s2 * n + i + 1, s * n + i + 1))
    if cap_bottom and profile[0][0] > 1e-5:
        faces.append(tuple(s * n for s in reversed(range(segments))))
    if cap_top and profile[-1][0] > 1e-5:
        faces.append(tuple(s * n + n - 1 for s in range(segments)))
    obj = new_object(name, verts, faces, material, col)
    return obj


def prism(name, polygon2d, z0, z1, material=None, col=None):
    """Extrude a CCW XY polygon from z0 to z1 (closed)."""
    n = len(polygon2d)
    verts = [(x, y, z0) for x, y in polygon2d] + [(x, y, z1) for x, y in polygon2d]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return new_object(name, verts, faces, material, col)


def triangle_count(objects) -> int:
    total = 0
    for obj in objects:
        if obj.type == 'MESH':
            total += sum(len(p.vertices) - 2 for p in obj.data.polygons)
    return total


# ---------------------------------------------------------------------------
# Review renders (Cycles CPU, AgX). Every kit renders a contact sheet so the
# art lead can compare it with the reference panel before integration.
# ---------------------------------------------------------------------------
def setup_review_world(strength=1.0, sun_energy=4.2, sun_rot=(math.radians(50), 0, math.radians(-35))):
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new('Review sky')
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    grad = nt.nodes.new('ShaderNodeTexGradient')
    coord = nt.nodes.new('ShaderNodeTexCoord')
    mapping = nt.nodes.new('ShaderNodeMapping')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    nt.links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    mapping.inputs['Rotation'].default_value = (0, math.radians(-90), 0)
    nt.links.new(mapping.outputs['Vector'], grad.inputs['Vector'])
    nt.links.new(grad.outputs['Fac'], ramp.inputs['Fac'])
    ramp.color_ramp.elements[0].color = (0.78, 0.86, 0.95, 1)
    ramp.color_ramp.elements[1].color = (0.30, 0.52, 0.86, 1)
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = strength
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    sun_data = bpy.data.lights.get('Review sun') or bpy.data.lights.new('Review sun', 'SUN')
    sun_data.energy = sun_energy
    sun_data.color = (1.0, 0.93, 0.82)
    sun_data.angle = math.radians(2.5)
    sun = bpy.data.objects.get('Review sun') or bpy.data.objects.new('Review sun', sun_data)
    if sun.name not in scene.collection.objects:
        scene.collection.objects.link(sun)
    sun.rotation_euler = sun_rot
    return sun


def render_settings(res=(1600, 900), samples=48, threads=4):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = threads
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    try:
        scene.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    scene.render.film_transparent = False
    return scene


def frame_camera(objects, azimuth_deg=-35.0, elevation_deg=28.0, lens=50, margin=1.12, name='Review camera'):
    pts = []
    for obj in objects:
        if obj.type == 'MESH':
            pts.extend(obj.matrix_world @ Vector(c) for c in obj.bound_box)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (lo + hi) * 0.5
    radius = (hi - lo).length * 0.5 * margin
    cam_data = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam_data.lens = lens
    cam = bpy.data.objects.get(name) or bpy.data.objects.new(name, cam_data)
    if cam.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(cam)
    fov = 2 * math.atan(18.0 / lens)
    dist = radius / math.sin(fov * 0.5)
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    direction = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
    cam.location = center + direction * dist
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data.clip_end = dist * 4 + 500
    bpy.context.scene.camera = cam
    return cam


def render(path: Path | str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path


def review_ground(size=400, material='grass_ground', z=0.0, col=None):
    obj = new_object('review ground', [(-size, -size, z), (size, -size, z), (size, size, z), (-size, size, z)],
                     [(0, 1, 2, 3)], material, col)
    uv_box(obj)
    ensure_white_vertex_colors(obj)
    return obj


# ---------------------------------------------------------------------------
# Export: merge static parts by material; keep runtime hooks separate.
# ---------------------------------------------------------------------------
def merge_by_material(objects, prefix='City'):
    static, hooks = [], []
    for obj in objects:
        if obj.type != 'MESH':
            continue
        (hooks if obj.name.startswith(RUNTIME_PREFIXES) else static).append(obj)
    groups: dict[str, list] = {}
    for obj in static:
        if not obj.data.materials:
            raise ValueError(f'{obj.name} has no material')
        ensure_white_vertex_colors(obj)
        _uv_layer(obj.data)
        groups.setdefault(obj.data.materials[0].name, []).append(obj)
    merged = []
    for mat_name, group in groups.items():
        merged.append(join(group, f'{prefix} / {mat_name}'))
    return merged, hooks


def export_glb(objects, path: Path | str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format='GLB', use_selection=True, export_yup=True,
        export_apply=True, export_materials='EXPORT', export_vertex_color='MATERIAL',
        export_animations=False, export_cameras=False, export_lights=False,
        export_extras=True)
    return path
