"""Inspect the CC0 sources (objects, triangles, rigs, actions, images) and render a quick CPU look at each.

    blender -b --factory-startup --python-exit-code 1 --python assets/blender/wildlife/wl_inspect.py -- [--keys deer,sheep]

Writes planning/evidence/wildlife-20261002/reports/source_inspect.json and renders/source/<key>_*.png.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import wl_common as C  # noqa: E402

log = C.Log("wl_inspect")
args = C.script_args()
keys = (C.arg_value(args, "--keys") or "deer,stag,sheep,frog,rabbit,duck").split(",")
OUT = C.RENDERS / "source"
OUT.mkdir(parents=True, exist_ok=True)
report = C.read_json(C.REPORTS / "source_inspect.json", {}) or {}


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def world_bbox(objs):
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    return mn, mx


def load_source(key):
    path, digest = C.verify_source(key)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
    elif path.suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif path.suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    return path, digest


def describe():
    out = {"objects": [], "actions": [], "images": []}
    for o in bpy.data.objects:
        d = {"name": o.name, "type": o.type, "parent": o.parent.name if o.parent else None,
             "loc": list(o.location), "rot": list(o.rotation_euler), "scale": list(o.scale),
             "dims": list(o.dimensions), "in_scene": o.name in bpy.context.scene.objects}
        if o.type == "MESH":
            me = o.data
            d.update(tris=tri_count(me), verts=len(me.vertices), polys=len(me.polygons),
                     materials=[m.name if m else None for m in me.materials],
                     uv=[u.name for u in me.uv_layers], colors=[a.name for a in me.color_attributes],
                     vgroups=len(o.vertex_groups), modifiers=[(m.type, m.name) for m in o.modifiers],
                     shape_keys=[k.name for k in me.shape_keys.key_blocks] if me.shape_keys else [],
                     smooth=sum(1 for p in me.polygons if p.use_smooth))
        if o.type == "ARMATURE":
            a = o.data
            d.update(bones=[(b.name, b.parent.name if b.parent else None, b.use_deform,
                             [round(v, 4) for v in b.head_local], [round(v, 4) for v in b.tail_local]) for b in a.bones],
                     action=o.animation_data.action.name if o.animation_data and o.animation_data.action else None,
                     nla=[t.name for t in o.animation_data.nla_tracks] if o.animation_data else [])
        out["objects"].append(d)
    for a in bpy.data.actions:
        fcs = []
        try:
            for s in a.slots:
                pass
            from bpy_extras import anim_utils
            for s in a.slots:
                cb = anim_utils.action_get_channelbag_for_slot(a, s)
                if cb:
                    fcs += [f.data_path for f in cb.fcurves]
        except Exception as e:  # noqa: BLE001
            fcs = [f"err {e}"]
        out["actions"].append({"name": a.name, "range": list(a.frame_range), "slots": [s.identifier for s in a.slots],
                               "fcurves": len(fcs), "paths_sample": sorted(set(p.split('"]')[0] + '"]' if '"]' in p else p
                                                                         for p in fcs))[:6],
                               "users": a.users})
    for im in bpy.data.images:
        out["images"].append({"name": im.name, "size": list(im.size), "packed": bool(im.packed_file),
                              "filepath": im.filepath, "colorspace": im.colorspace_settings.name})
    return out


def quick_render(key, objs):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 12
    scn.cycles.use_denoising = True
    scn.render.resolution_x = 640
    scn.render.resolution_y = 480
    scn.render.film_transparent = False
    world = bpy.data.worlds.new("insp") if not scn.world else scn.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.5, 0.55, 0.6, 1)
        bg.inputs[1].default_value = 1.0
    scn.world = world
    ld = bpy.data.lights.new("insp_sun", "SUN")
    ld.energy = 3.0
    lo = bpy.data.objects.new("insp_sun", ld)
    lo.rotation_euler = (math.radians(50), 0, math.radians(-30))
    scn.collection.objects.link(lo)
    mn, mx = world_bbox(objs)
    ctr = (mn + mx) / 2
    size = max((mx - mn).length, 0.05)
    cd = bpy.data.cameras.new("insp_cam")
    cd.lens = 50
    cam = bpy.data.objects.new("insp_cam", cd)
    scn.collection.objects.link(cam)
    scn.camera = cam
    paths = []
    for name, dirv in (("front", Vector((0, -1, 0.25))), ("side", Vector((1, 0, 0.2))), ("q34", Vector((0.8, -0.8, 0.5)))):
        dirv.normalize()
        cam.location = ctr + dirv * size * 2.1
        cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
        p = OUT / f"{key}_{name}.png"
        scn.render.filepath = str(p)
        bpy.ops.render.render(write_still=True)
        paths.append(C.rel(p))
    return paths, [list(mn), list(mx)]


for key in keys:
    try:
        path, digest = load_source(key)
        info = describe()
        info["file"] = str(path)
        info["sha256"] = digest
        info["blender_file_version"] = list(bpy.data.version) if hasattr(bpy.data, "version") else None
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render]
        info["renders"], info["bbox"] = quick_render(key, objs)
        report[key] = info
        log(key, "objects", len(info["objects"]), "actions", len(info["actions"]),
            "tris", sum(o.get("tris", 0) for o in info["objects"]), "bbox", info["bbox"])
    except Exception as e:  # noqa: BLE001
        import traceback
        report[key] = {"error": repr(e), "trace": traceback.format_exc()}
        log(key, "ERROR", repr(e))
    C.write_json(C.REPORTS / "source_inspect.json", report)
log("done")
