"""Debug: largest per-vertex displacements of LOD0 between rest and a clip frame, with their skin weights."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import h02_common as C  # noqa: E402

args = C.script_args()
clip = args[args.index("--clip") + 1] if "--clip" in args else "base.idle"
frame = int(args[args.index("--frame") + 1]) if "--frame" in args else 0
bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_anim.blend"))
scn = bpy.context.scene
arm = bpy.data.objects["hero02_XS1"]
o = bpy.data.objects["hero02_witch_lod0"]
arm.data.pose_position = "REST"
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
rest = np.array([v.co[:] for v in o.evaluated_get(dg).to_mesh().vertices])
o.evaluated_get(dg).to_mesh_clear()
arm.data.pose_position = "POSE"
act = bpy.data.actions[clip]
arm.animation_data.action = act
arm.animation_data.action_slot = act.slots[0]
scn.frame_set(frame)
dg = bpy.context.evaluated_depsgraph_get()
pose = np.array([v.co[:] for v in o.evaluated_get(dg).to_mesh().vertices])
o.evaluated_get(dg).to_mesh_clear()
d = np.linalg.norm(pose - rest, axis=1)
order = np.argsort(-d)
gn = [g.name for g in o.vertex_groups]
rows = []
for i in order[:40]:
    ws = sorted(((g.weight, gn[g.group]) for g in o.data.vertices[int(i)].groups), reverse=True)
    rows.append({"v": int(i), "disp_m": round(float(d[i]), 3), "rest": [round(c, 3) for c in rest[i]],
                 "pose": [round(c, 3) for c in pose[i]], "weights": [(n, round(w, 3)) for w, n in ws]})
# per-bone pose angle (degrees from rest) at this frame
ang = {pb.name: round(float(np.degrees(pb.rotation_quaternion.angle)), 1) for pb in arm.pose.bones}
big = {k: v for k, v in sorted(ang.items(), key=lambda kv: -kv[1])[:20]}
print(json.dumps({"clip": clip, "frame": frame, "max_disp": float(d.max()), "p99": float(np.percentile(d, 99)),
                  "top": rows[:25], "largest_bone_angles": big}, indent=1))
