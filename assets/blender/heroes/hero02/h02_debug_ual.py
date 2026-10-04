"""Debug: render the UAL mannequin itself at chosen clip frames (side view) + knee/hip angles."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import h02_common as C  # noqa: E402

args = C.script_args()
clips = args[args.index("--clips") + 1].split(",")
view = args[args.index("--view") + 1] if "--view" in args else "side"
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.fps = 30
bpy.ops.import_scene.gltf(filepath=str(C.UAL_GLTF), bone_heuristic="BLENDER", guess_original_bind_pose=True)
arm = next(o for o in scn.objects if o.type == "ARMATURE")
out = C.EVIDENCE / "debug"
scn.render.engine = "CYCLES"
scn.cycles.samples = 4
w = bpy.data.worlds.new("w")
w.use_nodes = True
scn.world = w
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3
sun.rotation_euler = (0.9, 0, -0.6)
scn.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2.4
scn.collection.objects.link(cam)
scn.camera = cam
loc = {"side": (6, 0, 1.0), "front": (0, -6, 1.0)}[view]
cam.location = loc
cam.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
scn.render.resolution_x, scn.render.resolution_y = 300, 420
rep = {}
for name in clips:
    act = next(a for a in bpy.data.actions if a.name == name or a.name.startswith(name))
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    f0, f1 = act.frame_range
    rows = []
    for k, f in enumerate((f0, (f0 + f1) / 2)):
        scn.frame_set(int(f))
        pb = arm.pose.bones
        def d(b):
            return (pb[b].tail - pb[b].head).normalized()
        knee = {s: round(math.degrees(d(f"DEF-thigh.{s}").angle(d(f"DEF-shin.{s}"))), 1) for s in ("L", "R")}
        rows.append({"frame": f, "knee_deg": knee, "hips_z": round((arm.matrix_world @ pb["DEF-hips"].head).z, 3),
                     "ankles": {s: [round(c, 3) for c in arm.matrix_world @ pb[f"DEF-foot.{s}"].head] for s in ("L", "R")}})
        scn.render.filepath = str(out / f"ual_{name}_{view}_{k}.png")
        bpy.ops.render.render(write_still=True)
    rep[name] = rows
print(json.dumps(rep, indent=1))
