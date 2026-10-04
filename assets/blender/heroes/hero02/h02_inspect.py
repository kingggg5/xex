"""Inspect the owner's hero 02 sources (read-only): mesh components, open edges, materials, rig joints and clips.

Writes planning/evidence/hero02-witch-20261002/reports/inspect_sources.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402
import h02_common as C  # noqa: E402

log = C.Log("h02_inspect")
C.verify_sources()


def import_glb(path, scene_name):
    scn = bpy.data.scenes.new(scene_name)
    bpy.context.window.scene = scn
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=False, import_shading="NORMALS",
                              bone_heuristic="BLENDER", guess_original_bind_pose=True)
    return [o for o in bpy.data.objects if o not in before]


def mesh_facts(o):
    me = o.data
    me.calc_loop_triangles()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    # connected components by linked faces (topological)
    seen = set()
    comps = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        seen.add(f.index)
        faces = []
        while stack:
            cur = stack.pop()
            faces.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        seen.add(nf.index)
                        stack.append(nf)
        vs = {v for ff in faces for v in ff.verts}
        lo = Vector((min(v.co.x for v in vs), min(v.co.y for v in vs), min(v.co.z for v in vs)))
        hi = Vector((max(v.co.x for v in vs), max(v.co.y for v in vs), max(v.co.z for v in vs)))
        tris = sum(len(ff.verts) - 2 for ff in faces)
        bnd = sum(1 for ff in faces for e in ff.edges if e.is_boundary)
        comps.append({"tris": tris, "verts": len(vs), "boundary_edges": bnd,
                      "min": [round(c, 4) for c in lo], "max": [round(c, 4) for c in hi]})
    comps.sort(key=lambda c: -c["tris"])
    bm.free()
    mw = o.matrix_world
    ws = [mw @ v.co for v in me.vertices]
    lo = [min(v[i] for v in ws) for i in range(3)]
    hi = [max(v[i] for v in ws) for i in range(3)]
    return {"object": o.name, "verts": len(me.vertices), "tris": len(me.loop_triangles), "faces": len(me.polygons),
            "uv_layers": [u.name for u in me.uv_layers], "materials": [m.name for m in me.materials if m],
            "boundary_edges": boundary, "non_manifold_edges": nonman, "components": len(comps),
            "largest_components": comps[:40], "world_min": lo, "world_max": hi,
            "matrix_world": [list(r) for r in mw], "vertex_groups": len(o.vertex_groups),
            "shape_keys": bool(me.shape_keys)}


report = {"sources": {}}

objs = import_glb(C.SRC_8K, "src8k")
log("8K source objects:", [(o.name, o.type) for o in objs])
for o in objs:
    if o.type == "MESH":
        f = mesh_facts(o)
        log("mesh", f["object"], "verts", f["verts"], "tris", f["tris"], "components", f["components"],
            "boundary", f["boundary_edges"], "nonmanifold", f["non_manifold_edges"])
        report["sources"]["src8k_mesh"] = f
for img in bpy.data.images:
    log("image", img.name, tuple(img.size), img.colorspace_settings.name, img.file_format)
report["images_8k"] = [{"name": i.name, "size": list(i.size), "colorspace": i.colorspace_settings.name,
                        "format": i.file_format} for i in bpy.data.images]
mats = {}
for m in bpy.data.materials:
    if m.node_tree:
        mats[m.name] = [(n.type, n.name, getattr(getattr(n, "image", None), "name", None)) for n in m.node_tree.nodes]
report["materials_8k"] = mats

objs2 = import_glb(C.SRC_RIG, "rig4k")
log("rig objects:", [(o.name, o.type) for o in objs2])
arm = next(o for o in objs2 if o.type == "ARMATURE")
bones = {}
for b in arm.data.bones:
    bones[b.name] = {"head": [round(c, 5) for c in arm.matrix_world @ b.head_local],
                     "tail": [round(c, 5) for c in arm.matrix_world @ b.tail_local],
                     "parent": b.parent.name if b.parent else None, "roll_axis_z": [round(c, 4) for c in
                                                                                   (arm.matrix_world.to_3x3() @ b.matrix_local.to_3x3()).col[2]]}
report["rig_armature"] = {"name": arm.name, "matrix_world": [list(r) for r in arm.matrix_world], "bones": bones}
for o in objs2:
    if o.type == "MESH":
        f = mesh_facts(o)
        report["sources"]["rig_mesh"] = f
        log("rig mesh", f["object"], "verts", f["verts"], "tris", f["tris"], "vgroups", f["vertex_groups"],
            "parent", o.parent.name if o.parent else None)
acts = {}
for a in bpy.data.actions:
    fr = a.frame_range
    acts[a.name] = {"frame_range": [fr[0], fr[1]], "users": a.users}
report["actions"] = acts
log("actions", acts)
# hips location per action (pose space) sampled
scn = bpy.context.scene
ad = arm.animation_data
hips = arm.pose.bones.get("mixamorig:Hips") or next(pb for pb in arm.pose.bones if pb.name.endswith("Hips"))
hip_samples = {}
for a in bpy.data.actions:
    if ad is None:
        break
    ad.action = a
    if a.slots:
        ad.action_slot = a.slots[0]
    f0, f1 = int(a.frame_range[0]), int(a.frame_range[1])
    pts = []
    for fr in range(f0, f1 + 1, max(1, (f1 - f0) // 12 or 1)):
        scn.frame_set(fr)
        p = arm.matrix_world @ hips.head
        pts.append([round(c, 4) for c in p])
    hip_samples[a.name] = pts
report["hips_world_samples"] = hip_samples
for k, v in hip_samples.items():
    log("hips", k, v[0], v[-1])
C.write_json(C.REPORTS / "inspect_sources.json", report)
log("wrote", C.rel(C.REPORTS / "inspect_sources.json"))
