"""BLENDER REVIEW renders for hero 02 (Cycles CPU, 1.8 m witness mannequin 1 m to the side).

--set views   front / side / back of LOD0 in the idle stance with the staff in the socket
--set cast    cast pose BEFORE (owner's Tripo rig + Tripo weights, cast_a_spell.001 at its widest frame) and
              AFTER (XS1 rig + new weights + sleeve/skirt rules, the same pose transferred joint-for-joint), plus
              the shipped mage.skill_bolt release frame
--set lineup  LOD0 / LOD1 / LOD2 beside the witness, front, flat light; plus a greyscale silhouette version
--set sheet   one frame per clip (release frame for actions, mid-cycle for loops) as a contact sheet
--set gamecam the game camera (radius 13 m, beta 1.18 rad, FOV 1.02 rad, target 1.65 m up, 2 m ahead)
Raw renders go to renders/raw/; h02_label.py adds the BLENDER REVIEW labels.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402
import h02_common as C  # noqa: E402
import h02_xs1 as X  # noqa: E402
import h02_animlib as A  # noqa: E402

log = C.Log("h02_render_review")
args = C.script_args()
sets = args[args.index("--set") + 1].split(",") if "--set" in args else ["views", "cast", "lineup", "sheet", "gamecam"]
tag = args[args.index("--tag") + 1] if "--tag" in args else "pass1"
SAMPLES = int(args[args.index("--samples") + 1]) if "--samples" in args else 40
RAW = C.RENDERS / "raw"
RAW.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_anim.blend"))
scn = bpy.context.scene
arm = bpy.data.objects["hero02_XS1"]
lods = {L: bpy.data.objects[f"hero02_witch_lod{L}"] for L in (0, 1, 2)}
hi = bpy.data.objects.get("hero02_hiclean")
if hi:
    hi.hide_render = True
for o in scn.objects:
    if o.get("xex_socket"):
        o.hide_render = True
clips = json.loads((C.REPORTS / "clips.json").read_text(encoding="utf-8"))["clips"]

# ------------------------------------------------------------------------------------------------ staff
with bpy.data.libraries.load(str(C.WORK / "h02_staff.blend"), link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n == "hero02_staff_lod0"]
staff = dst.objects[0]
scn.collection.objects.link(staff)
for c in list(staff.children):
    pass
staff.parent = arm
staff.parent_type = "BONE"
staff.parent_bone = "socket_weapon_R"
staff.matrix_parent_inverse = Matrix.Identity(4)
sock_len = arm.data.bones["socket_weapon_R"].length
staff.matrix_basis = Matrix.Translation((0, -sock_len, 0)) @ Matrix.Rotation(math.radians(-90), 4, "X")

# ------------------------------------------------------------------------------------------------ scene setup
scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.render.threads_mode = "FIXED"
scn.render.threads = 6
scn.cycles.samples = SAMPLES
scn.cycles.use_denoising = True
scn.cycles.denoiser = "OPENIMAGEDENOISE"
scn.render.film_transparent = False
scn.view_settings.view_transform = "AgX"
scn.view_settings.look = "AgX - Medium High Contrast"
world = bpy.data.worlds.new("review_world")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.55, 0.58, 0.62, 1)
bg.inputs[1].default_value = 0.9
scn.world = world


def add_light(name, rot, energy, size=2.0, kind="SUN", color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "SUN":
        ld.angle = math.radians(size)
    lo = bpy.data.objects.new(name, ld)
    lo.rotation_euler = [math.radians(a) for a in rot]
    scn.collection.objects.link(lo)
    return lo


add_light("key", (52, 0, -32), 3.2, 3.0, color=(1.0, 0.97, 0.92))
add_light("fill", (70, 0, 145), 0.9, 8.0, color=(0.85, 0.9, 1.0))
add_light("rim", (60, 0, 190), 1.6, 4.0)
# ground
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
ground = bpy.context.active_object
gm = bpy.data.materials.new("ground")
gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.33, 0.34, 1)
gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
ground.data.materials.append(gm)
# 1.8 m witness: capsule body + head, flat grey
wm = bpy.data.materials.new("witness")
wm.use_nodes = True
wm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.62, 0.6, 1)
bpy.ops.mesh.primitive_cylinder_add(radius=0.17, depth=1.46, location=(1.0, 0, 0.73), vertices=32)
w1 = bpy.context.active_object
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(1.0, 0, 1.68), segments=32, ring_count=16)
w2 = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=1.80, location=(1.24, 0, 0.90), vertices=8)
w3 = bpy.context.active_object
for w in (w1, w2, w3):
    w.data.materials.append(wm)
witness = [w1, w2, w3]
cam_d = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_d)
scn.collection.objects.link(cam)
scn.camera = cam


def look(cam_obj, loc, target):
    cam_obj.location = loc
    d = Vector(target) - Vector(loc)
    cam_obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def set_action(name, frame):
    act = bpy.data.actions[name]
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    scn.frame_set(int(frame))


def render(path, w, h):
    scn.render.resolution_x = w
    scn.render.resolution_y = h
    scn.render.resolution_percentage = 100
    scn.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    log("render", C.rel(path))


def show_only(lod_keys, staff_on=True, witness_on=True):
    for L, o in lods.items():
        o.hide_render = L not in lod_keys
    staff.hide_render = not staff_on
    for w in witness:
        w.hide_render = not witness_on


# ------------------------------------------------------------------------------------------------ views
if "views" in sets:
    show_only([0])
    set_action("base.idle", 0)
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 2.6
    for name, loc in (("front", (0.45, -8, 1.05)), ("side", (8, 0.0, 1.05)), ("back", (0.45, 8, 1.05)),
                      ("threequarter", (5.2, -5.6, 1.6))):
        tgt = (0.45 if name in ("front", "back") else 0.0, 0, 1.0)
        if name == "side":
            tgt = (0.0, 0.0, 1.0)
            w1.location.x = w2.location.x = 0.0
            w1.location.y = w2.location.y = 1.0
            w3.location = (0.0, 1.24, 0.90)
        else:
            w1.location = (1.0, 0, 0.73)
            w2.location = (1.0, 0, 1.68)
            w3.location = (1.24, 0, 0.90)
        look(cam, loc, tgt)
        render(RAW / f"{tag}_view_{name}.png", 1000, 1300)
    w1.location = (1.0, 0, 0.73)
    w2.location = (1.0, 0, 1.68)
    w3.location = (1.24, 0, 0.90)

# ------------------------------------------------------------------------------------------------ cast before/after
if "cast" in sets:
    cam_d.type = "PERSP"
    cam_d.lens = 50
    # BEFORE: the owner's Tripo rig with its own weights in cast_a_spell.001
    info = json.loads((C.REPORTS / "build_highpoly.json").read_text(encoding="utf-8"))
    S, piv = info["scale"], Vector(info["pivot_units"])
    before_objs = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(C.SRC_RIG), bone_heuristic="BLENDER", guess_original_bind_pose=True)
    tobjs = [o for o in bpy.data.objects if o not in before_objs]
    tarm = next(o for o in tobjs if o.type == "ARMATURE")
    tmesh = next(o for o in tobjs if o.type == "MESH" and o.vertex_groups)
    for o in tobjs:
        if o.type == "MESH" and not o.vertex_groups:
            o.hide_render = True
        if o.parent is None:
            o.matrix_world = Matrix.Diagonal((S, S, S, 1)) @ Matrix.Translation(-piv) @ o.matrix_world
    cast = next(a for a in bpy.data.actions if a.name.startswith("cast_a_spell"))
    tarm.animation_data.action = cast
    tarm.animation_data.action_slot = cast.slots[0]
    # widest frame: right hand farthest from the body axis
    best_f, best_d = int(cast.frame_range[0]), -1
    for f in range(int(cast.frame_range[0]), int(cast.frame_range[1]) + 1, 2):
        scn.frame_set(f)
        hp = tarm.matrix_world @ tarm.pose.bones["mixamorig:RightHand"].head
        d = math.hypot(hp.x, hp.y) + max(0.0, hp.z - 1.2)
        if d > best_d:
            best_f, best_d = f, d
    scn.frame_set(best_f)
    log("Tripo cast frame", best_f)
    show_only([], staff_on=False, witness_on=True)
    for o in tobjs:
        if o.type == "MESH" and o.vertex_groups:
            o.hide_render = False
    look(cam, (3.6, -4.8, 1.55), (0.0, 0, 1.05))
    render(RAW / f"{tag}_cast_before.png", 1000, 1200)
    # AFTER: the same pose transferred to XS1 (identical joint positions), then our sleeve/skirt rules
    sk = A.Skeleton(arm)
    bnames = [b.name for b in tarm.data.bones]
    src = A.SourceClip(tarm, cast, [best_f], bnames)
    mp = {f"mixamorig:{k}": v for k, v in X.MIXAMO_POSE.items()}
    frames = A.retarget(sk, src, mp, "mixamorig:Hips", 1.0, in_place=False)
    A.apply_twist_and_pauldron(sk, frames)
    A.apply_skirt(sk, frames)
    # sleeves: settle the lag at this frame
    for _ in range(20):
        A.apply_sleeves(sk, frames)
    act = A.write_action(arm, "review.cast_after", frames, X.JOINTS)
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    scn.frame_set(0)
    for o in tobjs:
        o.hide_render = True
    show_only([0], staff_on=False, witness_on=True)
    render(RAW / f"{tag}_cast_after.png", 1000, 1200)
    # shipped skill pose with the staff
    rel = next(e["frame"] for e in clips["mage.skill_bolt"]["events"] if e["id"] == "release")
    set_action("mage.skill_bolt", rel)
    show_only([0], staff_on=True, witness_on=True)
    render(RAW / f"{tag}_cast_skill_bolt_release.png", 1000, 1200)
    for o in tobjs:
        bpy.data.objects.remove(o, do_unlink=True)

# ------------------------------------------------------------------------------------------------ lineup
if "lineup" in sets:
    set_action("base.idle", 0)
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 3.4
    copies = []
    for L in (1, 2):
        lods[L].location.x = 1.0 * L
    staff.hide_render = True
    w1.location = (-1.05, 0, 0.73)
    w2.location = (-1.05, 0, 1.68)
    w3.location = (-1.30, 0, 0.90)
    show_only([0, 1, 2], staff_on=False, witness_on=True)
    for L in (1, 2):
        lods[L].location = (1.0 * L, 0, 0)
    look(cam, (0.5, -9, 1.05), (0.5, 0, 1.0))
    render(RAW / f"{tag}_lineup_lods.png", 1800, 1200)
    # greyscale silhouette (game-distance read): flat dark material, bright background
    saved = {o.name: list(o.data.materials) for o in lods.values()}
    flat = bpy.data.materials.new("flat")
    flat.use_nodes = True
    flat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.05, 0.05, 1)
    for o in lods.values():
        for k in range(len(o.data.materials)):
            o.data.materials[k] = flat
    bg.inputs[0].default_value = (1, 1, 1, 1)
    render(RAW / f"{tag}_lineup_silhouette.png", 1800, 1200)
    for o in lods.values():
        for k, m in enumerate(saved[o.name]):
            o.data.materials[k] = m
    bg.inputs[0].default_value = (0.55, 0.58, 0.62, 1)
    for L in (1, 2):
        lods[L].location = (0, 0, 0)
    w1.location = (1.0, 0, 0.73)
    w2.location = (1.0, 0, 1.68)
    w3.location = (1.24, 0, 0.90)

# ------------------------------------------------------------------------------------------------ clip sheet
if "sheet" in sets:
    show_only([0], staff_on=True, witness_on=False)
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 2.7
    order = ["base.idle", "base.walk", "base.run", "caster.attack_1", "caster.attack_2", "mage.skill_nova",
             "mage.skill_gale", "mage.skill_rift", "mage.skill_bolt", "mage.skill_ward", "mage.skill_starfall",
             "base.hit_light", "base.dodge", "base.death"]
    for name in order:
        c = clips[name]
        ev = {e["id"]: e["frame"] for e in c["events"]}
        frames_ = [ev.get("release", c["frames"] // 2)]
        if "release" in ev:
            frames_ = [max(0, ev["release"] - 2), ev["release"]]
        if name == "base.death":
            frames_ = [c["frames"] - 1]
        for f in frames_:
            set_action(name, f)
            look(cam, (4.2, -6.6, 1.5), (0, 0, 0.98))
            render(RAW / f"{tag}_sheet_{name.replace('.', '_')}_f{f:02d}.png", 600, 760)

# ------------------------------------------------------------------------------------------------ game camera
if "gamecam" in sets:
    show_only([0], staff_on=True, witness_on=True)
    set_action("base.idle", 0)
    cam_d.type = "PERSP"
    cam_d.sensor_fit = "VERTICAL"
    cam_d.angle_y = 1.02
    look(cam, (0, 10.02, 6.60), (0, -2.0, 1.65))
    render(RAW / f"{tag}_gamecam_back.png", 1920, 1080)
    arm.rotation_euler.z = math.radians(135)
    for w in witness:
        pass
    render(RAW / f"{tag}_gamecam_turn135.png", 1920, 1080)
    arm.rotation_euler.z = 0
log("done", sets)
