"""Inspect/extract authored Poly Haven Fir Tree 01 data with autoexec disabled.

Source files stay untouched; all candidates require the parent's art gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / ".harness/.cache/free-asset-sources/fir_tree_01"
OUTPUT = ROOT / "assets/models/tree-engine-candidates/polyhaven-fir-tree-01"
SOURCE_MD5 = "a08031ea8ffb49711b294e1c8213a909"


def source_hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            md5.update(block)
            sha.update(block)
    return {"md5": md5.hexdigest(), "sha256": sha.hexdigest()}


def static_triangles(mesh):
    return sum(max(0, len(face.vertices)-2) for face in mesh.polygons)


def inspect():
    source = Path(bpy.data.filepath)
    assert source.resolve() == (CACHE / "fir_tree_01_1k.blend").resolve(), "Unexpected source"
    hashes = source_hashes(source)
    assert hashes["md5"] == SOURCE_MD5, "Official source MD5 mismatch"
    mesh_counts = {mesh.name: static_triangles(mesh) for mesh in bpy.data.meshes}
    collections = []
    for collection in bpy.data.collections:
        objects = list(collection.all_objects)
        record = {"name": collection.name, "children": [child.name for child in collection.children],
                  "object_count": len(objects), "static_mesh_triangles": sum(mesh_counts[obj.data.name] for obj in objects if obj.type == "MESH"),
                  "hidden_viewport": collection.hide_viewport, "hidden_render": collection.hide_render,
                  "objects": [{"name": obj.name, "type": obj.type,
                               "triangles": mesh_counts.get(obj.data.name, None) if obj.type == "MESH" else None,
                               "modifiers": [{"type": mod.type, "name": mod.name, "node_group": mod.node_group.name if mod.type == "NODES" and mod.node_group else None} for mod in obj.modifiers],
                               "instance_collection": obj.instance_collection.name if obj.instance_collection else None}
                              for obj in objects]}
        collections.append(record)
    node_groups = []
    for group in bpy.data.node_groups:
        inputs = []
        if hasattr(group, "interface"):
            for item in group.interface.items_tree:
                if item.item_type == "SOCKET" and item.in_out == "INPUT":
                    value = getattr(item, "default_value", None)
                    if hasattr(value, "name"):
                        value = value.name
                    elif not isinstance(value, (str, int, float, bool, type(None))):
                        value = list(value)
                    inputs.append({"name": item.name, "identifier": item.identifier, "socket": item.socket_type, "default": value})
        node_groups.append({"name": group.name, "type": group.bl_idname, "node_count": len(group.nodes), "inputs": inputs})
    images = [{"name": image.name, "filepath": image.filepath, "packed": bool(image.packed_file),
               "size": list(image.size), "colorspace": image.colorspace_settings.name} for image in bpy.data.images]
    materials = [{"name": mat.name, "node_count": len(mat.node_tree.nodes) if mat.node_tree else 0,
                  "images": [node.image.name for node in mat.node_tree.nodes if node.type == "TEX_IMAGE" and node.image] if mat.node_tree else []}
                 for mat in bpy.data.materials]
    report = {"source": str(source), "source_hashes": hashes, "blender": bpy.app.version_string,
              "autoexec_enabled": bpy.context.preferences.filepaths.use_scripts_auto_execute,
              "collections": collections, "node_groups": node_groups, "images": images, "materials": materials}
    (CACHE / "inspection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SOURCE_HASH", hashes)
    print("COLLECTION_SUMMARY", json.dumps([{k: rec[k] for k in ["name", "object_count", "static_mesh_triangles", "children"]} for rec in collections]))
    print("OBJECT_TRIANGLES", json.dumps([(obj.name, mesh_counts[obj.data.name], [m.type for m in obj.modifiers]) for obj in bpy.data.objects if obj.type == "MESH"]))
    print("GEOMETRY_PARAMETERS", json.dumps([record for record in node_groups if record["type"] == "GeometryNodeTree"]))
    print("INSPECTION", str(CACHE / "inspection.json"))


def main():
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["inspect"], default="inspect")
    parser.parse_args(args)
    inspect()


if __name__ == "__main__":
    main()
