"""Stage 1: build the cleaned high-poly bake source of hero 02 and its 2048 atlas maps.

Input (read-only, hash-verified copies of the owner's files): source/owner/hero02_mage_p20_smartuv_pbr_source.glb
(Tripo P2.0, 50,679 tris, 8192 base colour, 4096 normal + metal/rough) and the Tripo rig GLB (only for the
dominant-bone region of each vertex).

Steps
 1. import, scale uniformly to a 1.80 m skull crown (hat and hair excluded), pivot on the ground between the ankles,
    character facing Blender -Y; merge coincident vertices (UV seams become loop seams), smooth normals;
 2. per-face exposure test (96 rays per side) -> per-component class: CLOTH (open sheets whose back side is visible
    from outside: robe panels, sleeves, capelet, apron; double-sided material) or BODY (single-sided);
 3. flip faces whose front is never visible but whose back is (inverted Tripo shells);
 4. delete interior faces (never visible from outside) in rigid regions only (head, hat, torso, hands, feet, shins);
 5. save work/h02_hiclean.blend. The 2048 atlas, the texture transfer bakes and the meshopt arrays are made by
    h02_atlas_bake.py.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from mathutils.kdtree import KDTree  # noqa: E402
import h02_common as C  # noqa: E402

log = C.Log("h02_build_highpoly")
hashes = C.verify_sources()
args = C.script_args()

CROWN_UNITS = 0.913
SCALE = C.CROWN_HEIGHT_M / CROWN_UNITS
PIVOT_UNITS = Vector((0.0020, -0.0215, 0.0))
RIGID_REGIONS = {"head", "hat", "torso", "hands", "feet", "shin"}

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=False, import_shading="NORMALS",
                              bone_heuristic="BLENDER", guess_original_bind_pose=True)
    return [o for o in bpy.data.objects if o not in before]


def to_metres(objs):
    m = Matrix.Diagonal((SCALE, SCALE, SCALE, 1.0)) @ Matrix.Translation(-PIVOT_UNITS)
    for o in objs:
        if o.parent is None:
            o.matrix_world = m @ o.matrix_world
    bpy.context.view_layer.update()


def bake_mesh_transform(o):
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = Matrix.Identity(4)
    o.data.transform(mw)
    o.data.update()


# ------------------------------------------------------------------------------------------------ 1. import
src_objs = import_glb(C.SRC_8K)
to_metres(src_objs)
hi = next(o for o in src_objs if o.type == "MESH")
bake_mesh_transform(hi)
for o in src_objs:
    if o is not hi:
        bpy.data.objects.remove(o, do_unlink=True)
hi.name = "hero02_hiclean"
hi.data.name = "hero02_hiclean"
me = hi.data
src_mat = me.materials[0]
src_mat.name = "hero02_tripo_source"
for img in bpy.data.images:          # keep the bake-source maps in the saved work blend
    if img.packed_file is None and img.source == "FILE":
        img.pack()
    img.use_fake_user = True
# drop the importer's custom normals; merge coincident vertices so seams share normals
bpy.context.view_layer.objects.active = hi
hi.select_set(True)
with bpy.context.temp_override(object=hi, active_object=hi, selected_objects=[hi]):
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
# original Tripo pieces (linked faces before welding): the cloth/body decision is made per piece
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
comp0 = [-1] * len(bm.faces)
n_pieces = 0
for f in bm.faces:
    if comp0[f.index] >= 0:
        continue
    comp0[f.index] = n_pieces
    stack = [f]
    while stack:
        cur = stack.pop()
        for e in cur.edges:
            for of in e.link_faces:
                if comp0[of.index] < 0:
                    comp0[of.index] = n_pieces
                    stack.append(of)
    n_pieces += 1
bm.free()
a_comp = me.attributes.new("xex_comp", "INT", "FACE")
a_comp.data.foreach_set("value", comp0)
log("original Tripo pieces", n_pieces)
bm = bmesh.new()
bm.from_mesh(me)
nv0 = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=5e-6)
bm.to_mesh(me)
bm.free()
me.shade_smooth()
me.update()
log("merged vertices", nv0, "->", len(me.vertices), "faces", len(me.polygons))
uv_names = [u.name for u in me.uv_layers]
assert len(uv_names) == 1, uv_names
me.uv_layers[0].name = "UV_tripo"

# ------------------------------------------------------------------------------------------------ regions (rig)
rig_objs = import_glb(C.SRC_RIG)
to_metres(rig_objs)
rig_mesh = next(o for o in rig_objs if o.type == "MESH" and o.vertex_groups)
rmw = rig_mesh.matrix_world
kd = KDTree(len(rig_mesh.data.vertices))
for i, v in enumerate(rig_mesh.data.vertices):
    kd.insert(rmw @ v.co, i)
kd.balance()
gnames = [g.name for g in rig_mesh.vertex_groups]
rv = rig_mesh.data.vertices


def region_of(bone):
    b = bone.replace("mixamorig:", "")
    if b.startswith(("Head", "Neck")):
        return "head"
    if "Hand" in b:
        return "hands"
    if b.endswith("ForeArm"):
        return "forearm"
    if b.endswith("Arm") or b.endswith("Shoulder"):
        return "upperarm"
    if b.startswith("Spine"):
        return "torso"
    if b == "Hips":
        return "hips"
    if b.endswith("UpLeg"):
        return "thigh"
    if b.endswith("Leg"):
        return "shin"
    if "Foot" in b or "Toe" in b:
        return "feet"
    return "other"


vregion = []
maxd = 0.0
for v in me.vertices:
    _, j, d = kd.find(v.co)
    maxd = max(maxd, d)
    gs = sorted(((g.weight, gnames[g.group]) for g in rv[j].groups), reverse=True)
    vregion.append(region_of(gs[0][1]) if gs else "other")
log("rig correspondence max distance (m)", round(maxd, 7))
for o in rig_objs:
    bpy.data.objects.remove(o, do_unlink=True)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
log("images after purge", [(i.name, tuple(i.size)) for i in bpy.data.images])

# ------------------------------------------------------------------------------------------------ 2. exposure test
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
bm.verts.ensure_lookup_table()
bvh = BVHTree.FromBMesh(bm)


def fib_hemisphere(n):
    ga = math.pi * (3 - math.sqrt(5))
    out = []
    for i in range(n):
        z = 1 - (i + 0.5) / n
        r = math.sqrt(max(0.0, 1 - z * z))
        out.append(Vector((r * math.cos(ga * i), r * math.sin(ga * i), z)))
    return out


HEMI = fib_hemisphere(96)
nf = len(bm.faces)
front = np.zeros(nf, np.float32)
back = np.zeros(nf, np.float32)
back_up = np.zeros(nf, np.float32)
min_elev = math.sin(math.radians(-30))
for f in bm.faces:
    c = f.calc_center_median()
    n = f.normal
    if n.length < 0.5:
        continue
    for side in (1, -1):
        ns = n * side
        q = ns.to_track_quat("Z", "Y")
        esc = esc_up = tot_up = 0
        origin = c + ns * 2e-4
        for d0 in HEMI:
            d = q @ d0
            free = bvh.ray_cast(origin, d, 30.0)[0] is None
            esc += free
            if d.z >= min_elev:
                tot_up += 1
                esc_up += free
        if side == 1:
            front[f.index] = esc / len(HEMI)
        else:
            back[f.index] = esc / len(HEMI)
            back_up[f.index] = esc_up / max(1, tot_up)
log("exposure test done", nf, "faces")

# face region = majority of its vertices
fregion = []
for f in bm.faces:
    regs = [vregion[v.index] for v in f.verts]
    fregion.append(max(set(regs), key=regs.count))
fregion = np.array(fregion, dtype=object)

# components = the original Tripo pieces (welding joined touching pieces, so they are taken from before the weld)
lay_comp0 = bm.faces.layers.int["xex_comp"]
comp = np.array([f[lay_comp0] for f in bm.faces], np.int64)
ncomp = int(comp.max()) + 1
area = np.array([f.calc_area() for f in bm.faces])
# open edges of each piece: an edge is a piece border when only one face of that piece uses it
boundary_faces = np.zeros(nf, np.int64)
for f in bm.faces:
    c0 = comp[f.index]
    for e in f.edges:
        if sum(1 for lf in e.link_faces if comp[lf.index] == c0) == 1:
            boundary_faces[f.index] += 1
two = (front > 0) & (back_up > 0)
flipped = (front == 0) & (back > 0.05)
interior = (front == 0) & (back == 0)
comp_cloth = np.zeros(ncomp, bool)
comp_rows = []
for ci in range(ncomp):
    m = comp == ci
    a = area[m].sum()
    two_frac = area[m & two].sum() / max(a, 1e-12)
    flip_frac = area[m & flipped].sum() / max(a, 1e-12)
    nb = int(boundary_faces[m].sum())
    cloth = (two_frac >= 0.08 and nb > 0) or (flip_frac >= 0.10 and nb >= 16)
    comp_cloth[ci] = cloth
    comp_rows.append({"comp": ci, "faces": int(m.sum()), "area_m2": round(float(a), 5), "two_frac": round(float(two_frac), 3),
                      "flip_frac": round(float(flip_frac), 3), "boundary_edges": nb, "cloth": bool(cloth)})
face_cloth = comp_cloth[comp]
log("components", ncomp, "cloth components", int(comp_cloth.sum()), "cloth faces", int(face_cloth.sum()),
    "cloth area m2", round(float(area[face_cloth].sum()), 3), "of", round(float(area.sum()), 3))

# face component = largest component in the head region whose faces point forward on average
head_comps = {}
for ci in np.unique(comp[fregion == "head"]):
    m = comp == ci
    head_comps[int(ci)] = int(m.sum())
face_comp = max(head_comps, key=lambda c: head_comps[c])
# hair = second largest head component; record both for island scaling
hair_comps = sorted(head_comps, key=lambda c: -head_comps[c])[1:3]
log("face component", face_comp, head_comps[face_comp], "hair components", hair_comps)

# ------------------------------------------------------------------------------------------------ 3/4. flip + delete
# per-face attributes first (adding layers can invalidate element references), then flip and delete by index
lay_cls = bm.faces.layers.int.new("xex_cloth")
lay_reg = bm.faces.layers.int.new("xex_region")
REG_ID = {r: i for i, r in enumerate(["head", "hat", "hands", "forearm", "upperarm", "torso", "hips", "thigh", "shin",
                                      "feet", "other", "face", "hair"])}
bm.faces.ensure_lookup_table()
for f in bm.faces:
    reg = fregion[f.index]
    if comp[f.index] == face_comp:
        reg = "face"
    elif comp[f.index] in hair_comps:
        reg = "hair"
    f[lay_cls] = int(face_cloth[f.index])
    f[lay_reg] = REG_ID[reg]
flip_idx = np.where(flipped & ~face_cloth)[0]
bm.faces.ensure_lookup_table()
bmesh.ops.reverse_faces(bm, faces=[bm.faces[int(i)] for i in flip_idx])
del_mask = interior & ~face_cloth & np.isin(fregion, list(RIGID_REGIONS))
bm.faces.ensure_lookup_table()
to_flip = list(flip_idx)
to_del = [bm.faces[int(i)] for i in np.where(del_mask)[0]]
log("flip faces", len(to_flip), "delete interior faces", len(to_del), "area", round(float(area[del_mask].sum()), 4))
bmesh.ops.delete(bm, geom=to_del, context="FACES")
loose = [v for v in bm.verts if not v.link_faces]
bmesh.ops.delete(bm, geom=loose, context="VERTS")
bm.to_mesh(me)
bm.free()
me.update()
log("after cleanup: verts", len(me.vertices), "faces", len(me.polygons))

# materials: slot 0 body (single-sided), slot 1 cloth (double-sided)
body = bpy.data.materials.new("hero02_witch_body")
cloth = bpy.data.materials.new("hero02_witch_cloth")
body["xex_double_sided"] = False
cloth["xex_double_sided"] = True
me.materials.clear()
me.materials.append(body)
me.materials.append(cloth)
me.materials.append(src_mat)       # slot 2 only holds the source material for baking; never exported
cls_attr = me.attributes["xex_cloth"].data
mat_idx = [int(cls_attr[i].value) for i in range(len(me.polygons))]
me.polygons.foreach_set("material_index", mat_idx)

bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK / "h02_hiclean.blend"), compress=True)
C.write_json(C.REPORTS / "build_highpoly.json", {
    "source_sha256": hashes, "scale": SCALE, "crown_units": CROWN_UNITS, "pivot_units": list(PIVOT_UNITS),
    "merged_vertices": [nv0, len(me.vertices)], "faces_after_cleanup": len(me.polygons), "flipped_faces": len(to_flip),
    "deleted_interior_faces": len(to_del), "pieces": int(ncomp), "cloth_pieces": int(comp_cloth.sum()),
    "cloth_faces": int(sum(mat_idx)), "rigid_regions_for_interior_removal": sorted(RIGID_REGIONS),
    "region_ids": REG_ID, "face_piece": int(face_comp), "hair_pieces": [int(c) for c in hair_comps],
    "pieces_detail": comp_rows})
log("saved", C.rel(C.WORK / "h02_hiclean.blend"))
