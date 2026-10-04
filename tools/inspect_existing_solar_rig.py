"""Read-only Blender check of a copied Solar Scorpion GLB; no provider calls."""
import argparse
import json
from pathlib import Path
import sys
import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True, type=Path)
parser.add_argument("--report", required=True, type=Path)
opts = parser.parse_args(args)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(opts.source.resolve()))
rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
record = {"source": str(opts.source.resolve()), "blender": bpy.app.version_string,
          "import_scene_fps": bpy.context.scene.render.fps,
          "armatures": [{"name": rig.name, "bones": len(rig.data.bones)} for rig in rigs],
          "meshes": [{"name": mesh.name, "vertices": len(mesh.data.vertices),
                      "skin_modifiers": sum(mod.type == "ARMATURE" for mod in mesh.modifiers),
                      "vertex_groups": len(mesh.vertex_groups)} for mesh in meshes], "clips": []}
for rig in rigs:
    if not rig.animation_data:
        raise RuntimeError("Imported skeleton has no animation data")
    rig.animation_data.use_nla = False
    for action in list(bpy.data.actions):
        if not action.slots:
            continue
        rig.animation_data.action = action
        rig.animation_data.action_slot = action.slots[0]
        first, last = action.frame_range
        poses = []
        for frame in [first, (first + last) / 2, last]:
            bpy.context.scene.frame_set(int(frame), subframe=frame - int(frame))
            bpy.context.view_layer.update()
            poses.append({bone.name: [float(v) for row in bone.matrix for v in row] for bone in rig.pose.bones})
        delta = max(abs(a - b) for name in poses[0]
                    for a, b in zip(poses[0][name], poses[1][name]))
        record["clips"].append({"name": action.name, "frame_range": [float(first), float(last)],
                                "sampled_pose_delta": delta, "moving": delta > 1e-6})
record["result"] = "PASS" if (len(rigs) == 1 and len(rigs[0].data.bones) == 57
                                 and len(record["clips"]) == 7 and all(c["moving"] for c in record["clips"])) else "FAIL"
record["limits"] = "Read-only imported bone-motion check; no GPU FPS, contact, artistic, or live game qualification."
opts.report.parent.mkdir(parents=True, exist_ok=True)
opts.report.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"result": record["result"], "bones": record["armatures"], "clips": record["clips"]}))
if record["result"] != "PASS":
    raise RuntimeError("Existing Solar export failed structural motion checks")
