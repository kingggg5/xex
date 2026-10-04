"""Stage 3: XS1 armature fitted to hero 02, piece-aware skin weights, LOD0/1/2 meshes, per-LOD normal bakes.

Inputs: work/h02_hiclean.blend (stage 1 + 1a), work/meshopt/lod*.indices.u32 (stage 2), work/tex/* (stage 1b),
        source/owner/hero02_mage_p20_smartuv_pbr_rig_animations_4k.glb (Tripo Mixamo rig: joint positions and the
        reference skin weights only; no Tripo clip is used here).
Output: work/h02_rig.blend (armature hero02_XS1, meshes hero02_witch_lod0/1/2, staff-free), reports/rig.json,
        work/tex/hero02_witch_normal_lod{0,1,2}.png.

Weights (rule per garment piece, see the integration doc):
- robe and apron panels: hips at the waist band, then the skirt F/B/L/R chains by azimuth (cos^2 blend) and height
  (no thigh weights, so the robe no longer stretches between the legs);
- bell sleeves: arm bones near the arm axis, sleeve.<s>.01 for the hanging bell (leg weights removed: Tripo had
  weighted the right sleeve tip to the thigh);
- back hair: head -> hair.01..03 by height (+ upper_chest on the lowest part), hat cone: head -> hat.01/.02,
  pendant: hat.03, brim and band rigid on head;
- belt vials and pouches: 70 % hips + 30 % nearest skirt .01;
- everything else: Tripo Mixamo weights merged onto XS1 (fingers merged, twist split along the arm),
  waist band smoothed; <= 4 influences, normalised, weights < 0.01 pruned.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.kdtree import KDTree  # noqa: E402
import h02_common as C  # noqa: E402
import h02_xs1 as X  # noqa: E402

log = C.Log("h02_build_lods_rig")
args = C.script_args()
SKIP_BAKE = "--skip-bake" in args
bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_hiclean.blend"))
scn = bpy.context.scene
hi = bpy.data.objects["hero02_hiclean"]
me = hi.data
REG = ["head", "hat", "hands", "forearm", "upperarm", "torso", "hips", "thigh", "shin", "feet", "other", "face", "hair"]
info = __import__("json").loads((C.REPORTS / "build_highpoly.json").read_text(encoding="utf-8"))
SCALE = info["scale"]
PIVOT = Vector(info["pivot_units"])

# ------------------------------------------------------------------------------------------------ Tripo rig (measuring)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(C.SRC_RIG), merge_vertices=False, import_shading="NORMALS",
                          bone_heuristic="BLENDER", guess_original_bind_pose=True)
rig_objs = [o for o in bpy.data.objects if o not in before]
m_units = Matrix.Diagonal((SCALE, SCALE, SCALE, 1.0)) @ Matrix.Translation(-PIVOT)
for o in rig_objs:
    if o.parent is None:
        o.matrix_world = m_units @ o.matrix_world
bpy.context.view_layer.update()
tarm = next(o for o in rig_objs if o.type == "ARMATURE")
tmesh = next(o for o in rig_objs if o.type == "MESH" and o.vertex_groups)
J = {}
for b in tarm.data.bones:
    J[b.name.replace("mixamorig:", "")] = (tarm.matrix_world @ b.head_local, tarm.matrix_world @ b.tail_local)
log("Tripo joints (m): hips", J["Hips"][0], "head", J["Head"][0], "L hand", J["LeftHand"][0])

# Tripo weights per hi-clean vertex (identical positions, max distance 4e-6 m)
kd = KDTree(len(tmesh.data.vertices))
tmw = tmesh.matrix_world
for i, v in enumerate(tmesh.data.vertices):
    kd.insert(tmw @ v.co, i)
kd.balance()
gnames = [g.name.replace("mixamorig:", "") for g in tmesh.vertex_groups]
nv = len(me.vertices)
tw = [dict() for _ in range(nv)]
maxd = 0.0
for i, v in enumerate(me.vertices):
    _, j, d = kd.find(v.co)
    maxd = max(maxd, d)
    for g in tmesh.data.vertices[j].groups:
        x = X.MIXAMO_TO_XS1.get(gnames[g.group])
        if x and g.weight > 1e-4:
            tw[i][x] = tw[i].get(x, 0.0) + g.weight
log("Tripo weight transfer: max distance", round(maxd, 7))


# ------------------------------------------------------------------------------------------------ geometry facts
co = np.empty(nv * 3)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
pcomp = np.array([me.attributes["xex_comp"].data[i].value for i in range(len(me.polygons))])
pcloth = np.array([me.attributes["xex_cloth"].data[i].value for i in range(len(me.polygons))])
preg = np.array([me.attributes["xex_region"].data[i].value for i in range(len(me.polygons))])
vpiece = np.full(nv, -1)
vcloth = np.zeros(nv, bool)
for p in me.polygons:
    for vi in p.vertices:
        if vpiece[vi] < 0 or p.area > 0:
            vpiece[vi] = pcomp[p.index]
        vcloth[vi] |= bool(pcloth[p.index])
pieces = {}
for pid in np.unique(pcomp):
    fm = pcomp == pid
    vs = np.unique(np.concatenate([list(me.polygons[int(k)].vertices) for k in np.where(fm)[0]]))
    pts = co[vs]
    regs, cnt = np.unique(preg[fm], return_counts=True)
    pieces[int(pid)] = {"verts": vs, "min": pts.min(0), "max": pts.max(0), "cen": pts.mean(0),
                        "cloth": bool(pcloth[fm].any()), "region": REG[int(regs[np.argmax(cnt)])],
                        "faces": int(fm.sum())}


def seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    q = a + np.outer(t, ab)
    return np.linalg.norm(p - q, axis=1), t


def jv(name, k=0):
    return np.array(J[name][k])


leg_segs = []
for side in ("Left", "Right"):
    leg_segs += [(jv(f"{side}UpLeg"), jv(f"{side}Leg")), (jv(f"{side}Leg"), jv(f"{side}Foot")),
                 (jv(f"{side}Foot"), jv(f"{side}ToeBase"))]


def leg_distance(pts):
    return np.min(np.stack([seg_dist(pts, a, b)[0] for a, b in leg_segs]), axis=0)


labels = {}
hat_cone = []
for pid, P in pieces.items():
    lo, hi_, cen = P["min"], P["max"], P["cen"]
    size = hi_ - lo
    diag = float(np.linalg.norm(size))
    reg = P["region"]
    lab = "tripo"
    if reg in ("hat", "head", "hair", "face") and cen[2] > 1.84 and lo[2] > 1.70:
        lab = "hat_cone"
    elif lo[2] > 1.58 and size[0] > 0.40 and hi_[2] < 1.93:
        lab = "hat_brim"
    elif reg == "hat":
        lab = "hat_rigid"
    elif reg in ("head", "hair", "upperarm", "torso") and cen[1] > 0.06 and 1.36 <= cen[2] <= 1.68 and not P["cloth"]:
        lab = "back_hair"
    elif P["cloth"] and abs(cen[0]) > 0.17 and hi_[2] > 1.05 and lo[2] > 0.70:
        lab = "sleeve"
    elif reg in ("upperarm", "forearm") and P["cloth"] and lo[2] >= 1.0:
        lab = "arm_cloth"
    else:
        med_leg = float(np.median(leg_distance(co[P["verts"]])))
        P["median_leg_distance"] = med_leg
        if hi_[2] < 1.33 and cen[2] < 1.02 and reg in ("thigh", "hips", "shin", "torso", "forearm", "upperarm") \
                and med_leg >= 0.075:
            lab = "robe"           # robe panels and every trim/star patch sewn on them (any size)
        elif diag < 0.40 and 0.90 <= cen[2] <= 1.22 and reg in ("hips", "thigh") and med_leg >= 0.07:
            lab = "belt_prop"
    labels[pid] = lab
    if lab == "hat_cone":
        hat_cone.append(pid)
# pendant: small pieces just below the cone tip
cone_pts = co[np.concatenate([pieces[p]["verts"] for p in hat_cone])] if hat_cone else np.zeros((0, 3))
base_c = cone_pts[cone_pts[:, 2] < cone_pts[:, 2].min() + 0.04].mean(0)
tip_i = int(np.argmax(np.linalg.norm(cone_pts - base_c, axis=1)))
tip = cone_pts[tip_i]
for pid, P in pieces.items():
    if P["faces"] < 220 and np.linalg.norm(P["cen"] - tip) < 0.16 and P["cen"][2] < tip[2] + 0.02 and labels[pid] != "hat_cone":
        labels[pid] = "pendant"
counts = {}
for lab in labels.values():
    counts[lab] = counts.get(lab, 0) + 1
log("piece labels", counts)

# cone centreline: base -> bend (highest region) -> tip
top_pts = cone_pts[cone_pts[:, 2] > cone_pts[:, 2].max() - 0.05]
bend = top_pts.mean(0)
pend_pts = [pieces[p]["cen"] for p, l in labels.items() if l == "pendant"]
pend_c = np.mean(pend_pts, 0) if pend_pts else tip + np.array([0, 0, -0.08])

# sleeve tips per side
sleeve_tip = {}
for s, sign in (("L", 1), ("R", -1)):
    vs = np.concatenate([pieces[p]["verts"] for p, l in labels.items() if l == "sleeve" and np.sign(pieces[p]["cen"][0]) == sign])
    pts = co[vs]
    low = pts[pts[:, 2] < pts[:, 2].min() + 0.08]
    sleeve_tip[s] = low.mean(0)
# gold diamond pendants hanging from the sleeve points (concept sheet): rigid on the sleeve joint
for pid, P in pieces.items():
    for s, tipv in sleeve_tip.items():
        if P["faces"] < 200 and labels[pid] not in ("sleeve", "arm_cloth") and \
                np.linalg.norm(P["cen"] - tipv) < 0.14 and P["cen"][2] < tipv[2] + 0.03:
            labels[pid] = f"sleeve_pendant_{s}"
counts = {}
for lab in labels.values():
    counts[lab] = counts.get(lab, 0) + 1
log("piece labels (final)", counts)
log("hat base", base_c.round(3), "bend", bend.round(3), "tip", tip.round(3), "pendant", np.round(pend_c, 3),
    "sleeve tips", {k: v.round(3) for k, v in sleeve_tip.items()})

# ------------------------------------------------------------------------------------------------ XS1 armature
arm_data = bpy.data.armatures.new("hero02_XS1")
arm = bpy.data.objects.new("hero02_XS1", arm_data)
scn.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
for o in scn.objects:
    o.select_set(o is arm)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
V = lambda a: Vector([float(x) for x in a])  # noqa: E731


def hand_frame(side):
    hd = V(J[f"{side}Hand"][0])
    mid = V(J[f"{side}HandMiddle1"][0])
    y = (mid - hd).normalized()
    acr = V(J[f"{side}HandIndex1"][0]) - V(J[f"{side}HandPinky1"][0])
    acr = (acr - y * acr.dot(y)).normalized()
    tipm = V(J[f"{side}HandMiddle4"][0])
    curl = tipm - V(J[f"{side}HandMiddle1"][0])
    palm = curl - y * curl.dot(y) - acr * curl.dot(acr)
    if palm.length < 1e-5:
        palm = y.cross(acr)
    palm.normalize()
    return hd, mid, y, acr, palm


bone_specs = {}
z_hint = {}
bone_specs["root"] = (Vector((0, 0, 0)), Vector((0, 0, 0.25)))
z_hint["root"] = Vector((0, -1, 0))
bone_specs["hips"] = (V(J["Hips"][0]), V(J["Spine"][0]))
bone_specs["spine"] = (V(J["Spine"][0]), V(J["Spine1"][0]))
bone_specs["chest"] = (V(J["Spine1"][0]), V(J["Spine2"][0]))
bone_specs["upper_chest"] = (V(J["Spine2"][0]), V(J["Neck"][0]))
bone_specs["neck"] = (V(J["Neck"][0]), V(J["Head"][0]))
hh = V(J["Head"][0])
bone_specs["head"] = (hh, Vector((hh.x, hh.y - 0.01, C.CROWN_HEIGHT_M)))
for b in ("hips", "spine", "chest", "upper_chest", "neck", "head"):
    z_hint[b] = Vector((0, -1, 0))
grip = {}
for side, s in (("Left", "L"), ("Right", "R")):
    bone_specs[f"shoulder.{s}"] = (V(J[f"{side}Shoulder"][0]), V(J[f"{side}Arm"][0]))
    bone_specs[f"upper_arm.{s}"] = (V(J[f"{side}Arm"][0]), V(J[f"{side}ForeArm"][0]))
    bone_specs[f"forearm.{s}"] = (V(J[f"{side}ForeArm"][0]), V(J[f"{side}Hand"][0]))
    hd, mid, y, acr, palm = hand_frame(side)
    bone_specs[f"hand.{s}"] = (hd, mid)
    bone_specs[f"thumb.01.{s}"] = (V(J[f"{side}HandThumb1"][0]), V(J[f"{side}HandThumb2"][0]))
    bone_specs[f"thumb.02.{s}"] = (V(J[f"{side}HandThumb2"][0]), V(J[f"{side}HandThumb4"][0]))
    bone_specs[f"index.01.{s}"] = (V(J[f"{side}HandIndex1"][0]), V(J[f"{side}HandIndex2"][0]))
    bone_specs[f"index.02.{s}"] = (V(J[f"{side}HandIndex2"][0]), V(J[f"{side}HandIndex4"][0]))
    bone_specs[f"grip.01.{s}"] = (V(J[f"{side}HandMiddle1"][0]), V(J[f"{side}HandMiddle2"][0]))
    bone_specs[f"grip.02.{s}"] = (V(J[f"{side}HandMiddle2"][0]), V(J[f"{side}HandMiddle4"][0]))
    ua0, ua1 = bone_specs[f"upper_arm.{s}"]
    fa0, fa1 = bone_specs[f"forearm.{s}"]
    bone_specs[f"upper_arm_twist.{s}"] = (ua0.lerp(ua1, 0.30), ua0.lerp(ua1, 0.60))
    bone_specs[f"forearm_twist.{s}"] = (fa0.lerp(fa1, 0.60), fa0.lerp(fa1, 0.95))
    sh = V(J[f"{side}Arm"][0])
    out = Vector((1 if s == "L" else -1, 0, 0))
    bone_specs[f"pauldron.{s}"] = (sh + Vector((0, 0, 0.04)), sh + Vector((0, 0, 0.04)) + out * 0.08)
    # grip: across the palm (pinky -> index, tilted 15 deg toward the fingers), 4.2 cm in front of the hand axis,
    # at 72 % of the palm length (proximal phalanges wrap the shaft)
    hand_len = (mid - hd).length
    g_axis = (acr + y * math.tan(math.radians(15))).normalized()
    g_pos = hd + y * (0.72 * hand_len) + palm * 0.042
    grip[s] = (g_pos, g_axis, palm)
    bone_specs[f"socket_weapon_{s}"] = (g_pos, g_pos + g_axis * 0.12)
    for b in (f"hand.{s}", f"thumb.01.{s}", f"thumb.02.{s}", f"index.01.{s}", f"index.02.{s}", f"grip.01.{s}",
              f"grip.02.{s}"):
        z_hint[b] = palm
    z_hint[f"socket_weapon_{s}"] = y
    for b in (f"shoulder.{s}", f"upper_arm.{s}", f"upper_arm_twist.{s}", f"forearm.{s}", f"forearm_twist.{s}",
              f"pauldron.{s}"):
        z_hint[b] = Vector((0, -1, 0))
    bone_specs[f"thigh.{s}"] = (V(J[f"{side}UpLeg"][0]), V(J[f"{side}Leg"][0]))
    bone_specs[f"shin.{s}"] = (V(J[f"{side}Leg"][0]), V(J[f"{side}Foot"][0]))
    bone_specs[f"foot.{s}"] = (V(J[f"{side}Foot"][0]), V(J[f"{side}ToeBase"][0]))
    bone_specs[f"toe.{s}"] = (V(J[f"{side}ToeBase"][0]), V(J[f"{side}Toe_End"][0]))
    for b in (f"thigh.{s}", f"shin.{s}"):
        z_hint[b] = Vector((0, -1, 0))
    z_hint[f"foot.{s}"] = Vector((0, 0, 1))
    z_hint[f"toe.{s}"] = Vector((0, 0, 1))
    bone_specs[f"sleeve.{s}.01"] = (V(J[f"{side}ForeArm"][0]), V(sleeve_tip[s]))
    z_hint[f"sleeve.{s}.01"] = Vector((0, -1, 0))
# robe chains (measured robe extents: waist 1.25 m, hem 0.09-0.30 m)
W0 = 1.16
skirt = {
    "F": ((0.0, -0.12, W0), (0.0, -0.19, 0.72), (0.0, -0.22, 0.26)),
    "B": ((0.0, 0.10, W0), (0.0, 0.19, 0.70), (0.0, 0.27, 0.20)),
    "L": ((0.13, 0.0, W0), (0.27, 0.03, 0.72), (0.38, 0.06, 0.28)),
    "R": ((-0.13, 0.0, W0), (-0.27, 0.03, 0.72), (-0.38, 0.06, 0.28)),
}
for k, (a, b, c) in skirt.items():
    bone_specs[f"skirt.{k}.01"] = (Vector(a), Vector(b))
    bone_specs[f"skirt.{k}.02"] = (Vector(b), Vector(c))
    z_hint[f"skirt.{k}.01"] = z_hint[f"skirt.{k}.02"] = Vector((0, -1, 0)) if k in "LR" else Vector((1, 0, 0))
hb = [Vector((0.0, 0.085, 1.645)), Vector((0.0, 0.135, 1.555)), Vector((0.0, 0.152, 1.47)), Vector((0.0, 0.15, 1.385))]
for i in range(3):
    bone_specs[f"hair.0{i + 1}"] = (hb[i], hb[i + 1])
    z_hint[f"hair.0{i + 1}"] = Vector((1, 0, 0))
bone_specs["hat.01"] = (V(base_c), V(bend))
bone_specs["hat.02"] = (V(bend), V(tip))
bone_specs["hat.03"] = (V(tip), V(pend_c))
for b in ("hat.01", "hat.02", "hat.03"):
    z_hint[b] = Vector((0, -1, 0))

for name in X.JOINTS:
    h, t = bone_specs[name]
    b = eb.new(name)
    b.head = h
    b.tail = t if (t - h).length > 1e-4 else h + Vector((0, 0, 0.05))
for name in X.JOINTS:
    b = eb[name]
    p = X.PARENT[name]
    if p:
        b.parent = eb[p]
        b.use_connect = False
    zh = z_hint.get(name, Vector((0, -1, 0)))
    yv = (b.tail - b.head).normalized()
    if abs(yv.dot(zh.normalized())) > 0.98:
        zh = Vector((0, 0, 1)) if abs(yv.z) < 0.9 else Vector((0, -1, 0))
    b.align_roll(zh)
    b.use_deform = True
bpy.ops.object.mode_set(mode="OBJECT")
log("XS1 armature:", len(arm_data.bones), "joints")

# static nodes (empties parented to joints)
static_pos = {
    "socket_back": (Vector((0, 0.16, 1.42)), "upper_chest"),
    "socket_hip_L": (Vector((0.16, -0.02, 1.08)), "hips"), "socket_hip_R": (Vector((-0.16, -0.02, 1.08)), "hips"),
    "socket_head": (Vector((hh.x, hh.y, C.CROWN_HEIGHT_M + 0.01)), "head"),
    "socket_face": (Vector((hh.x, hh.y - 0.09, 1.725)), "head"),
    "socket_mouth": (Vector((hh.x, hh.y - 0.09, 1.665)), "head"),
    "fx_head": (Vector((hh.x, hh.y, 1.74)), "head"), "fx_chest": (Vector((0, -0.10, 1.42)), "upper_chest"),
    "fx_hand_L": (V(grip["L"][0]), "hand.L"), "fx_hand_R": (V(grip["R"][0]), "hand.R"),
    "fx_feet": (Vector((0, 0, 0.0)), "root"),
}
empties = []
for name, (pos, bone) in static_pos.items():
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = 0.05
    scn.collection.objects.link(e)
    e.parent = arm
    e.parent_type = "BONE"
    e.parent_bone = bone
    bm_ = arm.matrix_world @ arm_data.bones[bone].matrix_local
    # bone-parented children are relative to the bone tail: world = bone_rest @ T(0, length, 0) @ basis
    tail_m = bm_ @ Matrix.Translation(Vector((0, arm_data.bones[bone].length, 0)))
    desired = Matrix.Translation(pos) @ bm_.to_quaternion().to_matrix().to_4x4()
    e.matrix_parent_inverse = Matrix.Identity(4)
    e.matrix_basis = tail_m.inverted() @ desired
    e["xex_socket"] = True
    empties.append(e)

# ------------------------------------------------------------------------------------------------ skin weights (hi)
rest = {b.name: (V(b.head_local), V(b.tail_local)) for b in arm_data.bones}


def smooth(e0, e1, x):
    return C.smoothstep(e0, e1, x)


W = [dict(d) for d in tw]
ARM_BONES = {s: {f"shoulder.{s}", f"upper_arm.{s}", f"forearm.{s}", f"hand.{s}", f"thumb.01.{s}", f"thumb.02.{s}",
                 f"index.01.{s}", f"index.02.{s}", f"grip.01.{s}", f"grip.02.{s}"} for s in ("L", "R")}
LEG_BONES = {f"{b}.{s}" for b in ("thigh", "shin", "foot", "toe") for s in ("L", "R")}
hip_c = np.array([0.0, -0.03])


def skirt_weights(p):
    x, y, z = p
    hips_w = smooth(1.03, 1.21, z)        # waist band rigid on hips, robe body on the chains
    t = smooth(0.84, 0.60, z)            # share of the lower (.02) joints
    phi = math.atan2(x - 0.0, -(y - hip_c[1]))   # 0 front, +90 left
    A = {"F": max(0.0, math.cos(phi)) ** 2, "L": max(0.0, math.sin(phi)) ** 2,
         "B": max(0.0, -math.cos(phi)) ** 2, "R": max(0.0, -math.sin(phi)) ** 2}
    out = {"hips": hips_w}
    for k, a in A.items():
        if a < 1e-4:
            continue
        out[f"skirt.{k}.01"] = (1 - hips_w) * (1 - t) * a
        out[f"skirt.{k}.02"] = (1 - hips_w) * t * a
    return out


for pid, P in pieces.items():
    lab = labels[pid]
    vs = P["verts"]
    if lab == "robe":
        for vi in vs:
            W[vi] = skirt_weights(co[vi])
    elif lab == "belt_prop":
        for vi in vs:
            sw = skirt_weights(np.array([co[vi][0], co[vi][1], 1.0]))
            d = {"hips": 0.7}
            for k, val in sw.items():
                if k.endswith(".01"):
                    d[k] = 0.3 * val / max(1e-6, sum(v for kk, v in sw.items() if kk.endswith(".01")))
            W[vi] = d
    elif lab in ("sleeve", "arm_cloth"):
        s = "L" if P["cen"][0] > 0 else "R"
        ua0, ua1 = rest[f"upper_arm.{s}"]
        fa0, fa1 = rest[f"forearm.{s}"]
        pts = co[vs]
        d_ua, _ = seg_dist(pts, np.array(ua0), np.array(ua1))
        d_fa, t_fa = seg_dist(pts, np.array(fa0), np.array(fa1))
        for k, vi in enumerate(vs):
            arm_w = {b: w for b, w in W[vi].items() if b in ARM_BONES[s] or b.startswith(f"upper_arm") or b.startswith("forearm")}
            arm_w = {b: w for b, w in arm_w.items() if b.endswith(s)}
            if not arm_w:
                arm_w = {f"forearm.{s}": 1.0}
            tot = sum(arm_w.values())
            arm_w = {b: w / tot for b, w in arm_w.items()}
            if lab == "sleeve":
                dmin = min(d_ua[k], d_fa[k])
                below_elbow = smooth(-0.02, 0.10, float((pts[k] - np.array(fa0)) @ (np.array(fa1) - np.array(fa0)) /
                                                           np.linalg.norm(np.array(fa1) - np.array(fa0))))
                ws = 0.9 * smooth(0.05, 0.15, float(dmin)) * max(below_elbow, 0.35)
            else:
                ws = 0.0
            d = {b: w * (1 - ws) for b, w in arm_w.items()}
            if ws > 0:
                d[f"sleeve.{s}.01"] = ws
            W[vi] = d
    elif lab == "back_hair":
        for vi in vs:
            z = co[vi][2]
            t = min(1.0, max(0.0, (1.645 - z) / (1.645 - 1.385)))
            head_w = 1.0 - smooth(0.0, 0.30, t)
            chain = {"hair.01": max(0.0, 1 - abs(t - 0.25) / 0.35), "hair.02": max(0.0, 1 - abs(t - 0.6) / 0.35),
                     "hair.03": max(0.0, 1 - abs(t - 0.95) / 0.35)}
            ct = sum(chain.values()) or 1.0
            body = 0.3 * smooth(0.55, 1.0, t)
            d = {"head": head_w * (1 - body)}
            for k, val in chain.items():
                if val > 0:
                    d[k] = (1 - head_w) * (1 - body) * val / ct
            if body > 0:
                d["upper_chest"] = body
            W[vi] = d
    elif lab == "hat_cone":
        a, b, c = np.array(base_c), np.array(bend), np.array(tip)
        L1 = np.linalg.norm(b - a)
        L2 = np.linalg.norm(c - b)
        for vi in vs:
            p = co[vi]
            d1, t1 = seg_dist(p[None], a, b)
            d2, t2 = seg_dist(p[None], b, c)
            s_ = (t1[0] * L1) / (L1 + L2) if d1[0] <= d2[0] else (L1 + t2[0] * L2) / (L1 + L2)
            head_w = 1.0 - smooth(0.10, 0.40, s_)
            w2 = smooth(0.45, 0.85, s_)
            W[vi] = {"head": head_w, "hat.01": (1 - head_w) * (1 - w2), "hat.02": (1 - head_w) * w2}
    elif lab == "pendant":
        for vi in vs:
            W[vi] = {"hat.03": 1.0}
    elif lab.startswith("sleeve_pendant_"):
        s = lab[-1]
        for vi in vs:
            W[vi] = {f"sleeve.{s}.01": 1.0}
    elif lab in ("hat_brim", "hat_rigid"):
        for vi in vs:
            W[vi] = {"head": 1.0}

# twist split along the arms (all vertices)
for s in ("L", "R"):
    ua0, ua1 = (np.array(v) for v in rest[f"upper_arm.{s}"])
    fa0, fa1 = (np.array(v) for v in rest[f"forearm.{s}"])
    for vi in range(nv):
        d = W[vi]
        if f"upper_arm.{s}" in d:
            t = float(np.clip((co[vi] - ua0) @ (ua1 - ua0) / ((ua1 - ua0) @ (ua1 - ua0)), 0, 1))
            share = 0.6 * (1 - smooth(0.05, 0.75, t))
            w = d.pop(f"upper_arm.{s}")
            d[f"upper_arm.{s}"] = w * (1 - share)
            d[f"upper_arm_twist.{s}"] = d.get(f"upper_arm_twist.{s}", 0) + w * share
        if f"forearm.{s}" in d:
            t = float(np.clip((co[vi] - fa0) @ (fa1 - fa0) / ((fa1 - fa0) @ (fa1 - fa0)), 0, 1))
            share = 0.7 * smooth(0.35, 0.95, t)
            w = d.pop(f"forearm.{s}")
            d[f"forearm.{s}"] = w * (1 - share)
            d[f"forearm_twist.{s}"] = d.get(f"forearm_twist.{s}", 0) + w * share

# waist band smoothing (torso/hips pieces between 1.02 and 1.42 m): widen the hips/spine/chest blend
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
nbrs = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
bm.free()
waist = [vi for vi in range(nv) if 1.02 <= co[vi][2] <= 1.42 and labels.get(int(vpiece[vi])) == "tripo" and
         pieces[int(vpiece[vi])]["region"] in ("torso", "hips")]
SPINE_SET = {"hips", "spine", "chest", "upper_chest"}
for it in range(6):
    new = {}
    for vi in waist:
        ns = [n for n in nbrs[vi] if vpiece[n] == vpiece[vi]]
        if not ns:
            continue
        acc = {}
        for n in ns + [vi]:
            for b, w in W[n].items():
                if b in SPINE_SET:
                    acc[b] = acc.get(b, 0) + w
        tot_sp = sum(acc.values())
        own_sp = sum(w for b, w in W[vi].items() if b in SPINE_SET)
        if tot_sp <= 0 or own_sp <= 0:
            continue
        d = {b: w for b, w in W[vi].items() if b not in SPINE_SET}
        for b, w in acc.items():
            d[b] = 0.5 * W[vi].get(b, 0) + 0.5 * own_sp * w / tot_sp
        new[vi] = d
    for vi, d in new.items():
        W[vi] = d


def finalize(d):
    d = {b: w for b, w in d.items() if w > 1e-6 and b in rest}
    top = sorted(d.items(), key=lambda kv: -kv[1])[:4]
    top = [(b, w) for b, w in top if w >= 0.01] or top[:1]
    tot = sum(w for _, w in top)
    return {b: w / tot for b, w in top}


W = [finalize(d) if d else {"hips": 1.0} for d in W]
unweighted = sum(1 for d in W if not d)
for vg in list(hi.vertex_groups):
    hi.vertex_groups.remove(vg)
groups = {name: hi.vertex_groups.new(name=name) for name in X.JOINTS}
for vi, d in enumerate(W):
    for b, w in d.items():
        groups[b].add([vi], w, "REPLACE")
log("weights: vertices", nv, "unweighted", unweighted)
lab_rows = {str(pid): {"label": labels[pid], "faces": P["faces"], "region": P["region"], "cloth": P["cloth"],
                       "centroid": [round(float(c), 3) for c in P["cen"]]} for pid, P in pieces.items()}

# ------------------------------------------------------------------------------------------------ LOD meshes
mo = C.WORK / "meshopt"
orig = np.fromfile(mo / "orig_vertex.u32", np.uint32)
uvs = np.fromfile(mo / "uvs.f32", np.float32).reshape(-1, 2)
umat = np.fromfile(mo / "material.f32", np.float32).astype(np.int64)
lods = {}
for L in (0, 1, 2):
    idx = np.fromfile(mo / f"lod{L}.indices.u32", np.uint32).reshape(-1, 3)
    ov = orig[idx]
    keep = (ov[:, 0] != ov[:, 1]) & (ov[:, 1] != ov[:, 2]) & (ov[:, 0] != ov[:, 2])
    idx, ov = idx[keep], ov[keep]
    used = np.unique(ov)
    remap = {int(o): k for k, o in enumerate(used)}
    faces = [[remap[int(a)], remap[int(b)], remap[int(c)]] for a, b, c in ov]
    m = bpy.data.meshes.new(f"hero02_witch_lod{L}")
    m.from_pydata([tuple(co[int(o)]) for o in used], [], faces)
    m.update()
    uvl = m.uv_layers.new(name="UV_atlas")
    luv = uvs[idx].reshape(-1, 2)
    uvl.data.foreach_set("uv", luv.ravel())
    m.polygons.foreach_set("material_index", umat[idx[:, 0]].tolist())
    m.shade_smooth()
    o = bpy.data.objects.new(f"hero02_witch_lod{L}", m)
    scn.collection.objects.link(o)
    o.parent = arm
    o.matrix_parent_inverse = Matrix.Identity(4)
    for name in X.JOINTS:
        o.vertex_groups.new(name=name)
    for k, ovi in enumerate(used):
        for b, w in W[int(ovi)].items():
            o.vertex_groups[b].add([k], w, "REPLACE")
    mod = o.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    lods[L] = o
    log(f"LOD{L}: triangles", len(faces), "vertices", len(used), "dropped degenerate", int((~keep).sum()))


# ------------------------------------------------------------------------------------------------ materials + bakes
def load_img(path, colorspace):
    img = bpy.data.images.load(str(path), check_existing=True)
    img.colorspace_settings.name = colorspace
    return img


albedo = load_img(C.WORK / "tex" / "hero02_witch_albedo.png", "sRGB")
orm = load_img(C.WORK / "tex" / "hero02_witch_orm.png", "Non-Color")


def gltf_output_group():
    g = bpy.data.node_groups.get("glTF Material Output")
    if g is None:
        g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        g.interface.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    return g


def build_material(name, normal_img, double_sided):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat["xex_double_sided"] = bool(double_sided)
    mat.use_backface_culling = not double_sided
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    t_alb = nt.nodes.new("ShaderNodeTexImage")
    t_alb.image = albedo
    nt.links.new(t_alb.outputs["Color"], bsdf.inputs["Base Color"])
    t_orm = nt.nodes.new("ShaderNodeTexImage")
    t_orm.image = orm
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(t_orm.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    grp = nt.nodes.new("ShaderNodeGroup")
    grp.node_tree = gltf_output_group()
    nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    if normal_img is not None:
        t_n = nt.nodes.new("ShaderNodeTexImage")
        t_n.image = normal_img
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.uv_map = "UV_atlas"
        nt.links.new(t_n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


NORMAL_SIZE = {0: 2048, 1: 1024, 2: 512}
RAY = {0: (0.012, 0.035), 1: (0.02, 0.06), 2: (0.035, 0.10)}
bake_report = {}
if not SKIP_BAKE:
    # high-poly shading source: Tripo normal map through the Tripo UVs
    src_mat = bpy.data.materials["hero02_tripo_source"]
    nimg = next(i for i in bpy.data.images if "source_normal" in i.name)
    nimg.colorspace_settings.name = "Non-Color"
    hsrc = bpy.data.materials.new("h02_hi_normal_source")
    hsrc.use_nodes = True
    nt = hsrc.node_tree
    nt.nodes.clear()
    o_ = nt.nodes.new("ShaderNodeOutputMaterial")
    b_ = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b_.outputs[0], o_.inputs["Surface"])
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UV_tripo"
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = nimg
    nt.links.new(uvn.outputs["UV"], tn.inputs["Vector"])
    nmn = nt.nodes.new("ShaderNodeNormalMap")
    nmn.uv_map = "UV_tripo"
    nt.links.new(tn.outputs["Color"], nmn.inputs["Color"])
    nt.links.new(nmn.outputs["Normal"], b_.inputs["Normal"])
    saved_mats = list(hi.data.materials)
    for k in range(len(hi.data.materials)):
        hi.data.materials[k] = hsrc
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 8
    scn.cycles.use_denoising = False
    arm.data.pose_position = "REST"
    for L, o in lods.items():
        size = NORMAL_SIZE[L]
        img = bpy.data.images.new(f"hero02_witch_normal_lod{L}", size, size, alpha=False, float_buffer=False)
        img.colorspace_settings.name = "Non-Color"
        tmp = bpy.data.materials.new(f"h02_bake_target_lod{L}")
        tmp.use_nodes = True
        tt = tmp.node_tree.nodes.new("ShaderNodeTexImage")
        tt.image = img
        tmp.node_tree.nodes.active = tt
        o.data.materials.clear()
        o.data.materials.append(tmp)
        o.data.materials.append(tmp)
        for ob in scn.objects:
            ob.select_set(False)
        hi.select_set(True)
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        ext, dist = RAY[L]
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y",
                            normal_b="POS_Z", use_selected_to_active=True, cage_extrusion=ext,
                            max_ray_distance=dist, margin=max(4, size // 128), margin_type="EXTEND", use_clear=True,
                            uv_layer="UV_atlas", target="IMAGE_TEXTURES")
        p = C.WORK / "tex" / f"hero02_witch_normal_lod{L}.png"
        img.filepath_raw = str(p)
        img.file_format = "PNG"
        img.save()
        img.filepath = str(p)
        img.source = "FILE"
        bake_report[L] = {"file": C.rel(p), "size": size, "cage_extrusion_m": ext, "max_ray_m": dist, "samples": 8}
        log("baked normal LOD", L, size)
        bpy.data.materials.remove(tmp)
    for k, m_ in enumerate(saved_mats):
        hi.data.materials[k] = m_
    arm.data.pose_position = "POSE"
for L, o in lods.items():
    p = C.WORK / "tex" / f"hero02_witch_normal_lod{L}.png"
    nimg_l = load_img(p, "Non-Color") if p.exists() else None
    sfx = "" if L == 0 else f"_lod{L}"
    body = build_material(f"hero02_witch_body{sfx}", nimg_l, False)
    clothm = build_material(f"hero02_witch_cloth{sfx}", nimg_l, True)
    o.data.materials.clear()
    o.data.materials.append(body)
    o.data.materials.append(clothm)
    # Clearing temporary bake material slots resets polygon indices in Blender.
    idx = np.fromfile(mo / f"lod{L}.indices.u32", np.uint32).reshape(-1, 3)
    ov = orig[idx]
    keep = (ov[:, 0] != ov[:, 1]) & (ov[:, 1] != ov[:, 2]) & (ov[:, 0] != ov[:, 2])
    o.data.polygons.foreach_set("material_index", umat[idx[keep, 0]].tolist())
    o.data.validate(verbose=False, clean_customdata=False)
    o.data.update()


# drop the Tripo measuring rig from the work file (keep its file untouched)
for o in rig_objs:
    bpy.data.objects.remove(o, do_unlink=True)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
hi.hide_render = True
hi.hide_set(True)
bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK / "h02_rig.blend"), compress=True)
C.write_json(C.REPORTS / "rig.json", {
    "joints": X.JOINTS, "joint_count": len(X.JOINTS), "static_nodes": list(static_pos),
    "bone_heads_m": {n: [round(c, 4) for c in rest[n][0]] for n in X.JOINTS},
    "bone_tails_m": {n: [round(c, 4) for c in rest[n][1]] for n in X.JOINTS},
    "grip": {s: {"pos": [round(c, 4) for c in g[0]], "axis": [round(c, 4) for c in g[1]]} for s, g in grip.items()},
    "piece_label_counts": counts, "pieces": lab_rows, "normal_bakes": bake_report,
    "tripo_weight_transfer_max_distance_m": maxd,
    "lods": {L: {"triangles": len(o.data.polygons), "vertices": len(o.data.vertices)} for L, o in lods.items()}})
log("saved", C.rel(C.WORK / "h02_rig.blend"))
