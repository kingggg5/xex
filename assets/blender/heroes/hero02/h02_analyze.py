"""Analyse the hero 02 high source (read-only on the owner files): scale/pivot facts, per-face exposure classes,
per-region texel density, and Tripo-rig dominant bones mapped onto the 8K source.

Outputs (no runtime asset is written here):
- work/h02_analysis.npz      per-face exposure (front/back escape fractions) and per-vertex nearest rig vertex
- reports/analysis.json      counts and texel density per region and class
- renders/analysis_*.png     ANALYSIS renders (classification colours), labelled in the filename
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

log = C.Log("h02_analyze")
C.verify_sources()

CROWN_UNITS = 0.913           # skull crown in source units (see doc: chin 0.8195, eye line 0.866, rule crown = chin + 2(eye-chin))
SCALE = C.CROWN_HEIGHT_M / CROWN_UNITS
PIVOT_UNITS = Vector((0.0020, -0.0215, 0.0))   # ankle midpoint (Tripo rig LeftFoot/RightFoot heads), on the ground


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


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


clear_scene()
src_objs = import_glb(C.SRC_8K)
to_metres(src_objs)
src = next(o for o in src_objs if o.type == "MESH")
# bake the transform into the mesh data (analysis copy only; the source file is untouched)
src.data = src.data.copy()
mw = src.matrix_world.copy()
src.parent = None
src.matrix_world = Matrix.Identity(4)
src.data.transform(mw)
src.data.update()
me = src.data
log("source in metres: verts", len(me.vertices), "polys", len(me.polygons), "scale", round(SCALE, 5))
co = np.empty(len(me.vertices) * 3, np.float64)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
log("bounds m", co.min(0).round(4), co.max(0).round(4))

# ---------------------------------------------------------------- exposure test
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
bvh = BVHTree.FromBMesh(bm)


def fib_hemisphere(n):
    pts = []
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - (i + 0.5) / n          # cos(theta) from 1 to 0 (hemisphere)
        r = math.sqrt(max(0.0, 1 - z * z))
        a = ga * i
        pts.append(Vector((r * math.cos(a), r * math.sin(a), z)))
    return pts


HEMI = fib_hemisphere(40)
nf = len(bm.faces)
front = np.zeros(nf, np.float32)      # fraction of front-hemisphere rays that escape
back = np.zeros(nf, np.float32)
front_up = np.zeros(nf, np.float32)   # same but only rays with elevation >= -30 deg (game camera can see)
back_up = np.zeros(nf, np.float32)
area = np.zeros(nf, np.float64)
cent = np.zeros((nf, 3), np.float64)
nrm = np.zeros((nf, 3), np.float64)
min_elev = math.sin(math.radians(-30))
for f in bm.faces:
    c = f.calc_center_median()
    n = f.normal.copy()
    area[f.index] = f.calc_area()
    cent[f.index] = c
    nrm[f.index] = n
    if n.length < 0.5:
        continue
    q = n.to_track_quat("Z", "Y")
    for side, arr, arr_up in ((1, front, front_up), (-1, back, back_up)):
        ns = n * side
        qs = q if side == 1 else ns.to_track_quat("Z", "Y")
        esc = esc_up = tot_up = 0
        for d0 in HEMI:
            d = qs @ d0
            hit = bvh.ray_cast(c + ns * 2e-4, d, 20.0)
            free = hit[0] is None
            esc += free
            if d.z >= min_elev:
                tot_up += 1
                esc_up += free
        arr[f.index] = esc / len(HEMI)
        arr_up[f.index] = esc_up / max(1, tot_up)
log("exposure done")

# ---------------------------------------------------------------- texel density per face at 2048
uv = me.uv_layers.active.data
uv_area = np.zeros(nf, np.float64)
for f in bm.faces:
    pass
loops_uv = np.empty(len(me.loops) * 2, np.float64)
uv.foreach_get("uv", loops_uv)
loops_uv = loops_uv.reshape(-1, 2)
for p in me.polygons:
    idx = list(p.loop_indices)
    a = loops_uv[idx[0]]
    s = 0.0
    for k in range(1, len(idx) - 1):
        b, c2 = loops_uv[idx[k]], loops_uv[idx[k + 1]]
        s += abs((b[0] - a[0]) * (c2[1] - a[1]) - (c2[0] - a[0]) * (b[1] - a[1])) * 0.5
    uv_area[p.index] = s
density = np.sqrt(np.where(area > 1e-12, uv_area * (2048.0 ** 2) / np.maximum(area, 1e-12), 0))

# ---------------------------------------------------------------- rig correspondence (dominant Mixamo bone)
rig_objs = import_glb(C.SRC_RIG)
to_metres(rig_objs)
bpy.context.view_layer.update()
rig_mesh = next(o for o in rig_objs if o.type == "MESH" and o.vertex_groups)
arm = next(o for o in rig_objs if o.type == "ARMATURE")
dg = bpy.context.evaluated_depsgraph_get()
rmw = rig_mesh.matrix_world
rverts = [rmw @ v.co for v in rig_mesh.data.vertices]
kd = KDTree(len(rverts))
for i, v in enumerate(rverts):
    kd.insert(v, i)
kd.balance()
gnames = [g.name for g in rig_mesh.vertex_groups]
dom = []
dist = np.zeros(len(me.vertices))
near = np.zeros(len(me.vertices), np.int64)
for i, v in enumerate(me.vertices):
    _, j, d = kd.find(v.co)
    near[i] = j
    dist[i] = d
rv = rig_mesh.data.vertices
dom_v = []
for j in near:
    gs = sorted(((g.weight, gnames[g.group]) for g in rv[j].groups), reverse=True)
    dom_v.append(gs[0][1] if gs else "")
log("nearest rig vertex distance: max", round(float(dist.max()), 6), "p99", round(float(np.percentile(dist, 99)), 6))


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


face_region = []
for p in me.polygons:
    regs = [region_of(dom_v[vi]) for vi in p.vertices]
    face_region.append(max(set(regs), key=regs.count))
face_region = np.array(face_region)
# hat: faces above the brim on the head region whose centroid is above 1.79 m or outside the skull radius
hat = (face_region == "head") & ((cent[:, 2] > 1.80) | ((cent[:, 2] > 1.62) & (np.hypot(cent[:, 0], cent[:, 1] + 0.05) > 0.13)))
face_region = np.where(hat, "hat", face_region)

classes = np.full(nf, "single", dtype=object)
classes[(front == 0) & (back == 0)] = "interior"
classes[(front == 0) & (back > 0)] = "flipped"
classes[(front > 0) & (back_up > 0)] = "two_sided"
summary = {}
for reg in sorted(set(face_region)):
    m = face_region == reg
    row = {"faces": int(m.sum()), "area_m2": round(float(area[m].sum()), 4),
           "density_px_per_m_2048_area_weighted": round(float(np.sqrt((uv_area[m].sum() * 2048 ** 2) / max(area[m].sum(), 1e-9))), 1)}
    for cl in ("single", "two_sided", "flipped", "interior"):
        mm = m & (classes == cl)
        row[cl] = {"faces": int(mm.sum()), "area_m2": round(float(area[mm].sum()), 4)}
    summary[reg] = row
tot = {"faces": nf, "area_m2": round(float(area.sum()), 4), "uv_fill": round(float(uv_area.sum()), 4),
       "density_px_per_m_2048": round(float(np.sqrt(uv_area.sum() * 2048 ** 2 / area.sum())), 1)}
for cl in ("single", "two_sided", "flipped", "interior"):
    mm = classes == cl
    tot[cl] = {"faces": int(mm.sum()), "area_m2": round(float(area[mm].sum()), 4),
               "uv_area": round(float(uv_area[mm].sum()), 4)}
log("totals", tot)
for k, v in summary.items():
    log("region", k, v)
np.savez_compressed(C.WORK / "h02_analysis.npz", front=front, back=back, front_up=front_up, back_up=back_up,
                    area=area, uv_area=uv_area, cent=cent, nrm=nrm, near=near, dist=dist,
                    face_region=face_region.astype("U16"), classes=classes.astype("U16"),
                    dom_v=np.array(dom_v, dtype="U40"), scale=SCALE, pivot=np.array(PIVOT_UNITS))
C.write_json(C.REPORTS / "analysis.json", {"scale": SCALE, "crown_units": CROWN_UNITS,
                                           "pivot_units": list(PIVOT_UNITS), "totals": tot, "regions": summary,
                                           "bounds_m": {"min": co.min(0).tolist(), "max": co.max(0).tolist()},
                                           "hair_top_m": None})

# ---------------------------------------------------------------- classification renders (ANALYSIS, not review)
for o in list(bpy.data.objects):
    if o is not src:
        bpy.data.objects.remove(o, do_unlink=True)
col_attr = me.color_attributes.new("cls", "BYTE_COLOR", "CORNER")
palette = {"single": (0.75, 0.75, 0.75, 1), "two_sided": (0.95, 0.55, 0.1, 1), "flipped": (0.9, 0.1, 0.9, 1),
           "interior": (0.1, 0.4, 1.0, 1)}
for p in me.polygons:
    c4 = palette[classes[p.index]]
    for li in p.loop_indices:
        col_attr.data[li].color = c4
mat = bpy.data.materials.new("cls")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
attr = nt.nodes.new("ShaderNodeVertexColor")
attr.layer_name = "cls"
bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
nt.links.new(attr.outputs["Color"], bsdf.inputs["Color"])
nt.links.new(bsdf.outputs[0], out.inputs[0])
me.materials.clear()
me.materials.append(mat)
scn = bpy.context.scene
scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.cycles.samples = 16
scn.cycles.use_denoising = True
scn.render.resolution_x, scn.render.resolution_y = 700, 1000
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scn.world = world
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 2.1
cam = bpy.data.objects.new("cam", cam_data)
scn.collection.objects.link(cam)
scn.camera = cam
for name, loc in (("front", (0, -6, 1.0)), ("back", (0, 6, 1.0)), ("left", (6, 0, 1.0)), ("below", (0, -4, -1.5))):
    cam.location = loc
    direction = Vector((0, 0, 1.0)) - Vector(loc) if name != "below" else Vector((0, 0, 0.6)) - Vector(loc)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scn.render.filepath = str(C.RENDERS / f"analysis_exposure_{name}.png")
    bpy.ops.render.render(write_still=True)
    log("render", name)
log("done")
