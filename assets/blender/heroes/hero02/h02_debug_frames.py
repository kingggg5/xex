"""Debug helper: quick low-sample renders of chosen clip frames + foot/hips trajectories (not review evidence).

blender -b --python h02_debug_frames.py -- --clips base.walk,base.run --frames 0,5,10 --view side
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import h02_common as C  # noqa: E402

args = C.script_args()
clips = args[args.index("--clips") + 1].split(",")
frames = [int(f) for f in args[args.index("--frames") + 1].split(",")] if "--frames" in args else None
view = args[args.index("--view") + 1] if "--view" in args else "side"
blend = args[args.index("--blend") + 1] if "--blend" in args else str(C.WORK / "h02_anim.blend")
out = C.EVIDENCE / "debug"
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=blend)
scn = bpy.context.scene
arm = bpy.data.objects["hero02_XS1"]
for o in scn.objects:
    if o.name.startswith("hero02_witch_lod") and o.name != "hero02_witch_lod0":
        o.hide_render = True
    if o.name == "hero02_hiclean":
        o.hide_render = True
scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.cycles.samples = 6
scn.cycles.use_denoising = True
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.8, 0.8, 1)
scn.world = w
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3
sun.rotation_euler = (0.9, 0, -0.6)
scn.collection.objects.link(sun)
bpy.ops.mesh.primitive_plane_add(size=10)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2.4
scn.collection.objects.link(cam)
scn.camera = cam
loc = {"side": (6, 0, 1.0), "front": (0, -6, 1.0), "back": (0, 6, 1.0), "tq": (4, -4.5, 1.4)}[view]
cam.location = loc
cam.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
scn.render.resolution_x, scn.render.resolution_y = 420, 520
report = {}
for name in clips:
    act = bpy.data.actions[name]
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    tr = []
    for f in range(f0, f1 + 1):
        scn.frame_set(f)
        pb = arm.pose.bones
        tr.append({"f": f, "hips": list(arm.matrix_world @ pb["hips"].head),
                   "footL": list(arm.matrix_world @ pb["foot.L"].head), "toeL": list(arm.matrix_world @ pb["toe.L"].head),
                   "footR": list(arm.matrix_world @ pb["foot.R"].head), "toeR": list(arm.matrix_world @ pb["toe.R"].head),
                   "handR": list(arm.matrix_world @ pb["hand.R"].head), "sockR": list(arm.matrix_world @ pb["socket_weapon_R"].head)})
    report[name] = tr
    for f in (frames or [f0, (f0 + f1) // 2, f1]):
        if f > f1:
            continue
        scn.frame_set(f)
        scn.render.filepath = str(out / f"{name.replace('.', '_')}_{view}_f{f:02d}.png")
        bpy.ops.render.render(write_still=True)
(out / "trajectories.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("debug done")
