"""R6 dressing helpers: world-space construction recipes on top of citykit.

Every new part is built directly in world space, then parented to its owner with
matrix_parent_inverse = owner.matrix_world.inverted(), so no part can ever be left
at kit-local coordinates (the R5 orphan-finial bug). All recipes keep the city
contracts: metre scale, existing city materials only, citykit UVs and COLOR_0.
Coordinates are Blender (x, y, z); runtime = (x, z, 176 + y).
"""
from __future__ import annotations

import math
import random
import re
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'lib'))
import citykit as ck  # noqa: E402

QDIR = HERE / 'props_r6' / 'quaternius'
NEW: list = []          # every object created by R6 recipes
COL = None


def collection():
    global COL
    if COL is None or COL.name not in bpy.data.collections:
        COL = ck.collection('r6 dressing', bpy.data.collections.get('City R5'))
    return COL


def own(obj, parent=None, *, bevel=0.0, uv=True, tint=(1, 1, 1), seed=0, ground=None, paint=True):
    if bevel:
        ck.bevel(obj, width=bevel, segments=2, angle_deg=32)
    if uv:
        ck.uv_box(obj)
    if paint:
        ck.vertex_paint(obj, tint=tint, ground_z=ground, seed=seed, cavity=0.24, edge=0.14, jitter=0.03)
    else:
        ck.ensure_white_vertex_colors(obj)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection().objects.link(obj)
    if parent is not None:
        mw = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
        obj.matrix_world = mw
    NEW.append(obj)
    return obj


def box(name, center, size, mat, parent=None, rot_z=0.0, bevel=0.03, **kw):
    o = ck.box(name, center, size, mat, rot_z=rot_z)
    return own(o, parent, bevel=bevel if min(size) > 0.08 else 0.0, **kw)


def lathe(name, profile, center, mat, parent=None, segments=16, **kw):
    o = ck.lathe(name, profile, segments=segments, material=mat, center=center)
    return own(o, parent, **kw)


def mesh(name, verts, faces, mat, parent=None, **kw):
    o = ck.new_object(name, verts, faces, mat)
    for p in o.data.polygons:
        pass
    return own(o, parent, **kw)


def beam(name, a, b, width, mat, parent=None, depth=None, **kw):
    a, b = Vector(a), Vector(b)
    axis = b - a
    if axis.length < 1e-5:
        return None
    axis.normalize()
    side = axis.cross(Vector((0, 0, 1)))
    if side.length < 1e-5:
        side = Vector((1, 0, 0))
    side.normalize()
    nrm = axis.cross(side).normalized()
    dy = width if depth is None else depth
    u, v = side * width * 0.5, nrm * dy * 0.5
    verts = []
    for p in (a, b):
        verts.extend([tuple(p - u - v), tuple(p + u - v), tuple(p + u + v), tuple(p - u + v)])
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = ck.new_object(name, verts, faces, mat)
    return own(o, parent, **kw)


def ico(name, center, radius, mat, parent=None, scale=(1, 1, 1), subdiv=1, **kw):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + Vector(center)
    o = ck.object_from_bmesh(name, bm, mat)
    for p in o.data.polygons:
        p.use_smooth = False
    return own(o, parent, **kw)



def deco(name):
    """Sub-part names never carry the street_object blocker family (only the planter/hedge body blocks)."""
    return name.replace('garden stone planter', 'planted').replace('plaza bench', 'bench')

# ---------------------------------------------------------------------------
# Ground
# ---------------------------------------------------------------------------
_WALK = re.compile(r'^(terrain / (grass ground|plaza |avenue |path |canal promenade|castle terrace / top|wizard terrace / top|'
                   r'wizard stairs$|cliff grass lip)|traversal / |castle terrace paving|castle grand stair tread|bridge dressed flagstone)')


class Ground:
    def __init__(self):
        self.rebuild()

    def rebuild(self):
        verts, polys, self.owner = [], [], []
        for o in bpy.context.scene.objects:
            if o.type != 'MESH' or not _WALK.search(o.name) or ' curb' in o.name:
                continue
            mw = o.matrix_world
            base = len(verts)
            verts.extend(mw @ v.co for v in o.data.vertices)
            for p in o.data.polygons:
                polys.append(tuple(base + i for i in p.vertices))
                self.owner.append(o.name)
        self.tree = BVHTree.FromPolygons(verts, polys)

    def z(self, x, y, z_from=150.0):
        hit = self.tree.ray_cast(Vector((x, y, z_from)), Vector((0, 0, -1)), 400.0)
        return (hit[0].z, self.owner[hit[2]]) if hit[0] is not None else (None, None)

    def footprint_min(self, cx, cy, length, depth, yaw_deg=0.0):
        """Lowest ground under a rectangular footprint (9 samples) so flat bases never show a gap downhill."""
        a = math.radians(yaw_deg)
        ux, uy, vx, vy = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
        zs = []
        for su in (-0.5, 0.0, 0.5):
            for sv in (-0.5, 0.0, 0.5):
                z, _ = self.z(cx + ux * su * length + vx * sv * depth, cy + uy * su * length + vy * sv * depth)
                if z is not None:
                    zs.append(z)
        return min(zs) if zs else None

    def under(self, x, y, z):
        """Ground directly under a point (within 1.5 m above it)."""
        hit = self.tree.ray_cast(Vector((x, y, z + 1.5)), Vector((0, 0, -1)), 400.0)
        return (hit[0].z, self.owner[hit[2]]) if hit[0] is not None else (None, None)


# ---------------------------------------------------------------------------
# Quaternius CC0 props (vendored, existing trim-sheet textures only)
# ---------------------------------------------------------------------------
_TEMPLATES: dict = {}


def _remap_imported(objs):
    for o in objs:
        if o.type != 'MESH':
            continue
        for slot in o.material_slots:
            m = slot.material
            if m is None:
                continue
            base = re.sub(r'\.\d{3}$', '', m.name)
            ex = bpy.data.materials.get(base)
            if ex is not None and ex is not m:
                slot.material = ex
            elif m.use_nodes:
                for n in m.node_tree.nodes:
                    if n.type == 'TEX_IMAGE' and n.image is not None:
                        ib = re.sub(r'\.\d{3}$', '', n.image.name)
                        exi = bpy.data.images.get(ib)
                        if exi is not None and exi is not n.image:
                            n.image = exi


def q_template(kind):
    if kind in _TEMPLATES:
        return _TEMPLATES[kind]
    path = QDIR / f'{kind}.gltf'
    if not path.is_file() and kind == 'Stall_Cart_Empty':
        path = HERE.parents[2] / 'assets/third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF/Stall_Cart_Empty.gltf'
    before = set(bpy.data.objects)
    mats_before, imgs_before = set(bpy.data.materials), set(bpy.data.images)
    bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=False)
    imported = [o for o in bpy.data.objects if o not in before]
    # rigged props bring armatures and bone display shapes: keep only real, material-bearing meshes
    meshes = [o for o in imported if o.type == 'MESH' and any(s.material for s in o.material_slots)]
    for o in meshes:
        for mod in list(o.modifiers):
            o.modifiers.remove(mod)
    bpy.context.view_layer.update()
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
    for o in imported:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    _remap_imported(meshes)
    tpl = ck.join(meshes, f'r6 template {kind}') if len(meshes) > 1 else meshes[0]
    tpl.name = f'r6 template {kind}'
    me = tpl.data
    if not me.color_attributes:
        ck.ensure_white_vertex_colors(tpl)
    ck.normalize_imported_gltf_prop_attributes(tpl)
    for c in list(tpl.users_collection):
        c.objects.unlink(tpl)
    for m in set(bpy.data.materials) - mats_before:
        if m.users == 0:
            bpy.data.materials.remove(m)
    for im in set(bpy.data.images) - imgs_before:
        if im.users == 0:
            bpy.data.images.remove(im)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    _TEMPLATES[kind] = (tpl, co.min(axis=0), co.max(axis=0))
    return _TEMPLATES[kind]


def q_prop(kind, name, loc, yaw_deg=0.0, scale=1.0, parent=None, ground=None, sink=0.01):
    """Place a vendored Quaternius prop with its base on the ground (or at loc z when ground is None)."""
    tpl, lo, hi = q_template(kind)
    o = bpy.data.objects.new(name, tpl.data.copy())
    x, y = loc[0], loc[1]
    z = loc[2] if len(loc) > 2 and loc[2] is not None else None
    if z is None and ground is not None:
        ext = (hi - lo) * scale
        if max(ext[0], ext[1]) > 0.9:
            z = ground.footprint_min(x, y, ext[0], ext[1], yaw_deg)
        else:
            z, _ = ground.z(x, y)
        z = 0.0 if z is None else z
    z = (z or 0.0) - sink - lo[2] * scale
    o.matrix_world = Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(yaw_deg), 4, 'Z') @ Matrix.Diagonal((scale, scale, scale, 1))
    collection().objects.link(o)
    if parent is not None:
        mw = o.matrix_world.copy()
        o.parent = parent
        o.matrix_parent_inverse = parent.matrix_world.inverted()
        o.matrix_world = mw
    NEW.append(o)
    return o


def q_footprint(kind, scale=1.0):
    _tpl, lo, hi = q_template(kind)
    return (hi - lo) * scale


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------
def crystal_lamp(name, x, y, z, parent=None, s=1.0, seed=0, arm_yaw=None, banner=False):
    """The plaza crystal lamp family: stone foot, gilded column, blue crystal, slate crown, finial.
    Optional cross arm with a hanging blue crest banner (all parts overlap; nothing floats)."""
    parts = []
    parts.append(lathe(f'{name} stone foot', [(0.44 * s, 0), (0.58 * s, 0.22 * s), (0.40 * s, 0.50 * s), (0.0, 0.50 * s)],
                       (x, y, z - 0.02), 'stone_trim_carved', parent, 12, seed=seed, ground=z))
    parts.append(lathe(f'{name} gilded column', [(0.17 * s, 0), (0.13 * s, 2.5 * s), (0.23 * s, 2.78 * s), (0.0, 2.78 * s)],
                       (x, y, z + 0.44 * s), 'metal_gold', parent, 12, seed=seed))
    parts.append(lathe(f'{name} blue crystal', [(0.0, 0), (0.30 * s, 0.10 * s), (0.25 * s, 1.0 * s), (0.0, 1.24 * s)],
                       (x, y, z + 3.12 * s), 'magic_blue', parent, 8, seed=seed, paint=False))
    parts.append(lathe(f'{name} slate crown', [(0.46 * s, 0), (0.52 * s, 0.18 * s), (0.10 * s, 0.62 * s), (0.0, 0.66 * s)],
                       (x, y, z + 4.10 * s), 'roof_slate_blue', parent, 8, seed=seed))
    parts.append(lathe(f'{name} gold finial', [(0.10 * s, 0), (0.05 * s, 0.30 * s), (0.0, 0.55 * s)],
                       (x, y, z + 4.68 * s), 'metal_gold', parent, 8, seed=seed))
    if arm_yaw is not None:
        a = math.radians(arm_yaw)
        dx, dy = math.cos(a), math.sin(a)
        zc = z + 2.55 * s
        parts.append(beam(f'{name} banner arm', (x - dx * 0.05, y - dy * 0.05, zc), (x + dx * 1.15 * s, y + dy * 1.15 * s, zc),
                          0.09 * s, 'metal_gold', parent))
        if banner:
            parts += crest_banner(f'{name} banner', x + dx * 0.75 * s, y + dy * 0.75 * s, zc - 0.04, 0.62 * s, 1.55 * s,
                                  arm_yaw + 90.0, parent)
    return parts


def crest_banner(name, x, y, z_top, width, height, yaw_deg, parent=None):
    """Blue crest banner hanging from a gold rod; the gold crest is inset into the cloth (no hover)."""
    a = math.radians(yaw_deg)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    hw = width * 0.5
    v = [(x - ux * hw, y - uy * hw, z_top), (x + ux * hw, y + uy * hw, z_top),
         (x + ux * hw, y + uy * hw, z_top - height), (x, y, z_top - height + width * 0.45),
         (x - ux * hw, y - uy * hw, z_top - height)]
    # two-sided cloth with 2 cm thickness so it never z-fights its own back
    t = 0.02
    front = [(p[0] + nx * t, p[1] + ny * t, p[2]) for p in v]
    back = [(p[0] - nx * t, p[1] - ny * t, p[2]) for p in v]
    verts = front + back
    faces = [(0, 1, 2, 3, 4), (9, 8, 7, 6, 5)] + [(i, (i + 1) % 5, (i + 1) % 5 + 5, i + 5) for i in range(5)]
    cloth = ck.new_object(f'{name} cloth', verts, faces, 'banner_emblem')
    ck.uv_unit(cloth)
    own(cloth, parent, uv=False, paint=False)
    rod = beam(f'{name} rod', (x - ux * (hw + 0.08), y - uy * (hw + 0.08), z_top + 0.03),
               (x + ux * (hw + 0.08), y + uy * (hw + 0.08), z_top + 0.03), 0.07, 'metal_gold', parent)
    crest = box(f'{name} sun crest', (x + nx * 0.012, y + ny * 0.012, z_top - height * 0.45), (width * 0.42, 0.05, width * 0.46),
                'metal_gold', parent, rot_z=a, bevel=0.0)
    return [cloth, rod, crest]


def flower_cluster(name, cx, cy, z, radius, rng, parent=None, mounds=5, palette=None):
    """Low foliage mounds with blossom heads seated on them (nothing hovers above the soil)."""
    palette = palette or ['flower_ivory', 'flower_lilac', 'flower_gold', 'foliage_blossom']
    parts = []
    for i in range(mounds):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(0, radius * 0.75)
        mx, my = cx + math.cos(a) * r, cy + math.sin(a) * r
        mr = rng.uniform(0.38, 0.52) * min(1.0, radius / 0.8 + 0.45)
        mz = z + mr * 0.38
        parts.append(ico(f'{name} leaf mound', (mx, my, mz), mr, rng.choice(['foliage_mid', 'foliage_sun', 'foliage_mid']), parent,
                         scale=(1.0, rng.uniform(0.85, 1.15), 0.74), seed=i))
        bloom = palette[(i + rng.randint(0, 3)) % len(palette)]
        for k in range(rng.randint(6, 9)):
            b = rng.uniform(0, math.tau)
            br = rng.uniform(0.1, 0.8) * mr
            bz = mz + math.sqrt(max(0.0, 1 - (br / mr) ** 2)) * mr * 0.74 - 0.03
            colour = bloom if k % 3 else palette[(i + k) % len(palette)]
            parts.append(ico(f'{name} blossom', (mx + math.cos(b) * br, my + math.sin(b) * br, bz), rng.uniform(0.11, 0.16),
                             colour, parent, subdiv=1, paint=False))
    return parts


def planter_box(name, cx, cy, z, length, depth, yaw_deg, rng, parent=None, height=0.55, mat='stone_trim_carved', ground=None):
    a = math.radians(yaw_deg)
    if ground is not None:
        zm = ground.footprint_min(cx, cy, length, depth, yaw_deg)
        if zm is not None:
            height += max(0.0, z - zm)
            z = zm
    parts = [box(f'{name} planter', (cx, cy, z + height * 0.5 - 0.03), (length, depth, height), mat, parent, rot_z=a, bevel=0.05, ground=z),
             box(f'{deco(name)} soil', (cx, cy, z + height - 0.04), (length - 0.16, depth - 0.16, 0.06), 'dirt_path', parent, rot_z=a, bevel=0.0)]
    ux, uy = math.cos(a), math.sin(a)
    n = max(2, int(length / 0.75))
    for i in range(n):
        t = (i + 0.5) / n - 0.5
        parts += flower_cluster(f'{deco(name)} flowers', cx + ux * t * (length - 0.4), cy + uy * t * (length - 0.4), z + height - 0.02,
                                min(0.42, depth * 0.38), rng, parent, mounds=1)
    return parts


def hedge(name, a, b, parent=None, height=1.0, width=0.85, z=0.0, seed=0, ground=None):
    a, b = Vector((a[0], a[1], 0)), Vector((b[0], b[1], 0))
    mid = (a + b) * 0.5
    d = b - a
    ang = math.atan2(d.y, d.x)
    if ground is not None:
        zm = ground.footprint_min(mid.x, mid.y, d.length, width, math.degrees(ang))
        zt, _ = ground.z(mid.x, mid.y)
        if zm is not None:
            height += max(0.0, (zt if zt is not None else zm) - zm)
            z = zm
    o = box(f'{name} hedge', (mid.x, mid.y, z + height * 0.5 - 0.04), (d.length, width, height), 'foliage_deep', parent,
            rot_z=ang, bevel=0.18, tint=(0.95 + 0.1 * random.Random(seed).random(), 1.0, 0.95), seed=seed, ground=z)
    parts = [o]
    rng = random.Random(seed * 7 + 3)
    n = max(2, int(d.length / 1.25))
    ux, uy = math.cos(ang), math.sin(ang)
    for k in range(n):
        t = (k + 0.5) / n - 0.5
        r = width * rng.uniform(0.5, 0.62)
        cx, cy = mid.x + ux * t * (d.length - width * 0.6), mid.y + uy * t * (d.length - width * 0.6)
        parts.append(ico(f'{deco(name)} hedge crown', (cx, cy, z + height - 0.06), r, rng.choice(['foliage_deep', 'foliage_mid']), parent,
                         scale=(1.25, 0.95, 0.62), seed=seed + k))
    return parts


def arc_planter(name, r0, r1, a0, a1, z, rng, parent=None, height=0.5, seg=10):
    """Curved stone planter on a ring (fountain base beds)."""
    verts, faces = [], []
    for i in range(seg + 1):
        a = a0 + (a1 - a0) * i / seg
        for r in (r0, r1):
            for zz in (z - 0.04, z + height):
                verts.append((r * math.cos(a), r * math.sin(a), zz))
    for i in range(seg):
        b = i * 4
        n = b + 4
        faces += [(b + 1, n + 1, n + 3, b + 3), (b, b + 2, n + 2, n), (b, n, n + 1, b + 1), (b + 2, b + 3, n + 3, n + 2)]
    faces += [(0, 1, 3, 2), (seg * 4, seg * 4 + 2, seg * 4 + 3, seg * 4 + 1)]
    o = ck.new_object(f'{name} curved planter', verts, faces, 'stone_trim_carved')
    for p in o.data.polygons:
        if (p.center.to_2d().length - (r0 + r1) * 0.5) * 0 == 0:
            pass
    o.data.update()
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    parts = [own(o, parent, bevel=0.04, ground=z)]
    # soil
    sv, sf = [], []
    for i in range(seg + 1):
        a = a0 + (a1 - a0) * i / seg
        for r in (r0 + 0.1, r1 - 0.1):
            sv.append((r * math.cos(a), r * math.sin(a), z + height - 0.03))
    for i in range(seg):
        sf.append((i * 2, i * 2 + 2, i * 2 + 3, i * 2 + 1))
    s = ck.new_object(f'{deco(name)} soil', sv, sf, 'dirt_path')
    parts.append(own(s, parent))
    rm = (r0 + r1) * 0.5
    n = max(2, int((a1 - a0) * rm / 0.8))
    for i in range(n):
        a = a0 + (a1 - a0) * (i + 0.5) / n
        parts += flower_cluster(f'{deco(name)} flowers', rm * math.cos(a), rm * math.sin(a), z + height - 0.03, (r1 - r0) * 0.42,
                                rng, parent, mounds=1)
    return parts


def draped_area(name, poly, mat, ground_h, lift=0.06, cell=2.0, parent=None):
    """Fill a convex/concave polygon with a grid draped on the terrain height function."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    nx, ny = max(2, int((x1 - x0) / cell) + 1), max(2, int((y1 - y0) / cell) + 1)

    def inside(x, y):
        c = False
        j = len(poly) - 1
        for i in range(len(poly)):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
                c = not c
            j = i
        return c

    bm = bmesh.new()
    grid = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            x = x0 + (x1 - x0) * i / nx
            y = y0 + (y1 - y0) * j / ny
            grid[(i, j)] = (x, y)
    vmap = {}
    for i in range(nx):
        for j in range(ny):
            cx = x0 + (x1 - x0) * (i + 0.5) / nx
            cy = y0 + (y1 - y0) * (j + 0.5) / ny
            if not inside(cx, cy):
                continue
            quad = []
            for key in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                if key not in vmap:
                    x, y = grid[key]
                    vmap[key] = bm.verts.new((x, y, ground_h(x, y) + lift))
                quad.append(vmap[key])
            bm.faces.new(quad)
    o = ck.object_from_bmesh(name, bm, mat)
    return own(o, parent, paint=False)


def market_cross(name, x, y, z, parent=None):
    """Market cross: two octagonal steps, carved shaft, gold collar and a blue crystal finial."""
    parts = [lathe(f'{name} lower step', [(2.1, 0), (2.1, 0.30), (1.95, 0.34), (0.0, 0.34)], (x, y, z - 0.04), 'stone_foundation', parent, 8, ground=z),
             lathe(f'{deco(name)} upper step', [(1.5, 0), (1.5, 0.30), (1.38, 0.34), (0.0, 0.34)], (x, y, z + 0.27), 'stone_trim_carved', parent, 8),
             lathe(f'{deco(name)} shaft', [(0.62, 0), (0.48, 0.4), (0.36, 3.4), (0.48, 3.7), (0.0, 3.75)], (x, y, z + 0.58), 'stone_trim_carved', parent, 8),
             lathe(f'{deco(name)} gold collar', [(0.55, 0), (0.62, 0.12), (0.5, 0.3), (0.0, 0.3)], (x, y, z + 4.25), 'metal_gold', parent, 12),
             lathe(f'{deco(name)} crystal', [(0.0, 0), (0.34, 0.22), (0.28, 1.2), (0.0, 1.6)], (x, y, z + 4.5), 'magic_blue', parent, 8, paint=False)]
    return parts
