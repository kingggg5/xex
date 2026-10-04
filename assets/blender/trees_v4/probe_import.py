"""Probe: Blender version, colour-management options and how the glTF importer
builds one Quaternius tree (node tree, colour attributes, normals).

BLENDER REVIEW tooling, Route A step 1 (trees v4). Read-only on the sources.
Usage:
  blender -b --factory-startup --python probe_import.py -- <path/to/model.gltf>
"""
import sys
import json
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
path = argv[0]

scene = bpy.context.scene
vt = scene.view_settings.bl_rna.properties["view_transform"]
looks = scene.view_settings.bl_rna.properties["look"]
info = {
    "blender": bpy.app.version_string,
    "build_hash": bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
    "view_transforms": [i.identifier for i in vt.enum_items],
    "looks": [i.identifier for i in looks.enum_items][:40],
    "default_view_transform": scene.view_settings.view_transform,
}
import addon_utils
for mod in addon_utils.modules():
    if mod.__name__.endswith("io_scene_gltf2"):
        info["gltf_addon_version"] = list(mod.bl_info.get("version", ()))
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
props = bpy.ops.import_scene.gltf.get_rna_type().properties
info["gltf_import_options"] = {p.identifier: getattr(p, "default", None) for p in props if p.identifier not in ("filepath", "files", "filter_glob", "directory")}
bpy.ops.import_scene.gltf(filepath=path)
objs = []
for ob in bpy.data.objects:
    entry = {"name": ob.name, "type": ob.type, "loc": list(ob.location), "rot": list(ob.rotation_euler), "scale": list(ob.scale)}
    if ob.type == "MESH":
        me = ob.data
        entry["color_attributes"] = [(c.name, c.domain, c.data_type) for c in me.color_attributes]
        entry["attributes"] = [(a.name, a.domain, a.data_type) for a in me.attributes]
        entry["uv"] = [u.name for u in me.uv_layers]
        entry["has_custom_normals"] = me.has_custom_normals
        entry["materials"] = []
        for m in me.materials:
            nodes = []
            for n in m.node_tree.nodes:
                d = {"name": n.name, "type": n.bl_idname}
                if n.bl_idname == "ShaderNodeTexImage" and n.image:
                    d["image"] = [n.image.name, list(n.image.size), n.image.colorspace_settings.name]
                if n.bl_idname == "ShaderNodeMath":
                    d["op"] = n.operation
                    d["inputs"] = [i.default_value for i in n.inputs if hasattr(i, "default_value")]
                nodes.append(d)
            links = [(l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name) for l in m.node_tree.links]
            entry["materials"].append({"name": m.name, "nodes": nodes, "links": links,
                                       "surface_render_method": getattr(m, "surface_render_method", None),
                                       "use_backface_culling": m.use_backface_culling})
    objs.append(entry)
info["objects"] = objs
print("PROBE_JSON " + json.dumps(info))
