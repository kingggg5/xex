"""Xexoria shared glTF export helper for every Blender 5.2 headless pipeline.

One call per runtime GLB:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[N] / "assets" / "blender" / "tools"))  # N = depth to repo root
    from export_helper import export_glb

    receipt = export_glb([lod0], out / "qn_broadleaf_m_lod0.glb", "foliage",
                         receipt_path=out / "qn_broadleaf_m_lod0.receipt.json",
                         texture_dir=out / "textures-shared")

What it guarantees (contract: docs/reviews/2026-10-02-export-helper.md; sources: the 2026-10-02 official-docs,
community-practice and headless-automation reviews, master plan P10 GAP-3/GAP-4):
- every option of the installed io_scene_gltf2 exporter is passed explicitly; the full set is checked against the
  exporter's RNA at call time (unknown, missing or out-of-range options raise) and recorded in the receipt;
- tangents are exported when an exported material uses a normal map (profile policy "auto");
- COLOR_0 is RGB (VEC3) unless the profile allows alpha; a VEC4 written by the exporter is rewritten to VEC3 (GAP-3);
- opaque materials are single-sided; only alpha-tested/blended cards (foliage, impostor cards) or materials the
  builder tags explicitly (cloth) are double-sided (GAP-4);
- images are written as external files into a shared texture folder, deduplicated by SHA-256 (file name carries the
  hash), never embedded unless the call or profile asks;
- +Y up; no cameras or lights; animation/skins/morphs only for the skinned profile; modifiers applied except on the
  skinned profile, where only the Armature modifier may remain (shape keys survive);
- compression is never done here: meshopt (EXT only, never KHR) and KTX2 run in apps/client/scripts/gltf-postprocess.mjs;
- the written GLB is parsed, then re-imported into a clean scratch scene and compared with the source
  (triangles, bounds, materials, attribute set, COLOR_0 type, double-sidedness);
- a receipt JSON (options, counts per mesh/material, sizes, SHA-256, validation) is written even on failure.

CLI (one Blender process at a time; check `Get-Process blender` and >= 1.5 GB free RAM first):

    & $env:BLENDER_BIN --background --factory-startup --python-exit-code 1 `
        --python assets/blender/tools/export_helper.py -- introspect --out rna.json
    & $env:BLENDER_BIN --background --factory-startup --python-exit-code 1 `
        --python assets/blender/tools/export_helper.py -- reexport --jobs jobs.json

Exit codes: 0 = PASS, 1 = Python exception (via --python-exit-code 1), 2 = bad arguments, 3 = validation FAIL.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import math
import os
import re
import struct
import sys
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

try:  # the GLB/receipt utilities also run under system Python; the export path needs Blender
    import bpy
except ImportError:  # pragma: no cover - only outside Blender
    bpy = None

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy ships with Blender
    np = None

HELPER_VERSION = "1.0.0"
SCHEMA = "xexoria.export-receipt/1"
MIN_BLENDER = (5, 2, 0)
EXIT_OK, EXIT_EXCEPTION, EXIT_ARGS, EXIT_VALIDATION = 0, 1, 2, 3
ROOT = Path(__file__).resolve().parents[3]

# Extensions Babylon.js 9.27.1 loads (pinned loader; official-docs review §3.6).
BABYLON_LOADABLE = frozenset({
    "KHR_materials_unlit", "KHR_materials_emissive_strength", "KHR_texture_transform", "KHR_materials_variants",
    "KHR_materials_clearcoat", "KHR_materials_sheen", "KHR_materials_specular", "KHR_materials_ior",
    "KHR_materials_anisotropy", "KHR_materials_transmission", "KHR_materials_volume", "KHR_materials_dispersion",
    "KHR_materials_iridescence", "EXT_mesh_gpu_instancing", "EXT_meshopt_compression", "KHR_draco_mesh_compression",
    "KHR_mesh_quantization", "KHR_texture_basisu", "KHR_animation_pointer", "MSFT_lod", "KHR_lights_punctual",
    "EXT_texture_webp",
})
# Never in a runtime asset: reason per extension.
FORBIDDEN_EXTENSIONS = {
    "KHR_meshopt_compression": "Babylon 9.27.1 has no KHR_meshopt_compression loader (GAP-9); EXT only",
    "KHR_draco_mesh_compression": "Draco stays off: extra CDN decoder, no gain over meshopt (official-docs X5)",
    "KHR_lights_punctual": "runtime assets carry no lights",
    "EXT_texture_webp": "WebP is not GPU-compressed; textures go PNG -> KTX2 in the post-process",
}
# Allowed but expensive on GTX 1050 / phones (official-docs M12): warn.
EXPENSIVE_MATERIAL_EXTENSIONS = frozenset({
    "KHR_materials_clearcoat", "KHR_materials_transmission", "KHR_materials_volume", "KHR_materials_sheen",
    "KHR_materials_specular", "KHR_materials_ior", "KHR_materials_anisotropy", "KHR_materials_iridescence",
    "KHR_materials_dispersion",
})
# Vertex attributes Babylon 9.27.1 reads (glTFLoader.pure.js:989-1005).
BABYLON_ATTRIBUTES = frozenset({"POSITION", "NORMAL", "TANGENT", "TEXCOORD_0", "TEXCOORD_1", "TEXCOORD_2",
                                "TEXCOORD_3", "TEXCOORD_4", "TEXCOORD_5", "COLOR_0", "JOINTS_0", "JOINTS_1",
                                "WEIGHTS_0", "WEIGHTS_1"})

# ---------------------------------------------------------------------------------------------- exporter options
# Exporter options NOT passed, each with the reason. Everything else in the installed RNA must be set below.
DEFAULTED_ON_PURPOSE = {
    "ui_tab": "export-dialog tab selector; no effect on the written file",
    "filter_glob": "file-browser filter (HIDDEN); no effect on the written file",
    "gltf_export_id": "id used by File > Export All Collections exporters; unused for operator calls",
}
# Set per call by export_glb() from the profile policy and arguments (always present in the final dict).
PER_CALL_OPTIONS = ("filepath", "collection", "export_format", "export_texture_dir", "export_copyright",
                    "export_tangents", "export_materials", "export_vertex_color", "export_vertex_color_name",
                    "export_active_vertex_color_when_no_material", "export_extras")

BASE_OPTIONS = {
    # scope: export exactly the objects handed to export_glb (temporary collection), active scene only
    # export_loglevel must stay -1 in add-on 5.2.40: any value >= 0 skips setting export_settings["loglevel"] and the
    # operator raises KeyError (io_scene_gltf2/__init__.py:1141-1143 vs :1388). -1 = level from bpy.app.debug_value.
    "check_existing": False, "will_save_settings": False, "export_loglevel": -1,
    "use_selection": False, "use_visible": False, "use_renderable": False, "use_active_collection": False,
    "use_active_collection_with_nested": False, "use_active_scene": True, "at_collection_center": False,
    "export_hierarchy_full_collections": False, "export_hierarchy_flatten_objs": False,
    # transform: glTF +Y up, metres (official-docs E3)
    "export_yup": True,
    # mesh data (E5, E8, E9, E10, X2, X3)
    "export_apply": True, "export_texcoords": True, "export_normals": True, "export_tangents": False,
    "export_gn_mesh": False, "export_attributes": False, "use_mesh_edges": False, "use_mesh_vertices": False,
    "export_shared_accessors": False, "export_gpu_instances": False,
    # vertex colour (E6, GAP-3): only colour layers a material multiplies into Base Color; never "all"
    "export_vertex_color": "MATERIAL", "export_vertex_color_name": "Color", "export_all_vertex_colors": False,
    "export_active_vertex_color_when_no_material": False,
    # materials and images (M1-M12, T1, T2, GAP-7): lossless intermediates, KTX2 later
    "export_materials": "EXPORT", "export_image_format": "AUTO", "export_image_add_webp": False,
    "export_image_webp_fallback": False, "export_image_quality": 100, "export_jpeg_quality": 100,
    "export_keep_originals": False, "export_unused_images": False, "export_unused_textures": False,
    "export_original_specular": False,
    # scene objects
    "export_cameras": False, "export_lights": False, "export_import_convert_lighting_mode": "SPEC",
    "export_extras": True, "export_copyright": "",
    # compression stays off in Blender (X4, X5, GAP-9); EXT named so a stray enable can never pick KHR
    "export_meshopt_compression_enable": False, "export_meshopt_extension": "EXT_meshopt_compression",
    "export_draco_mesh_compression_enable": False, "export_draco_mesh_compression_level": 6,
    "export_draco_position_quantization": 14, "export_draco_normal_quantization": 10,
    "export_draco_texcoord_quantization": 12, "export_draco_color_quantization": 10,
    "export_draco_generic_quantization": 12,
    "export_use_gltfpack": False, "export_gltfpack_tc": True, "export_gltfpack_tq": 8, "export_gltfpack_si": 1.0,
    "export_gltfpack_sa": False, "export_gltfpack_slb": False, "export_gltfpack_vp": 14, "export_gltfpack_vt": 12,
    "export_gltfpack_vn": 8, "export_gltfpack_vc": 8, "export_gltfpack_vpi": "Integer", "export_gltfpack_noq": True,
    "export_gltfpack_kn": False,
    # animation (A1-A7): inert unless a profile sets export_animations
    "export_animations": False, "export_animation_mode": "ACTIONS", "export_nla_strips": True,
    "export_nla_strips_merged_animation_name": "Animation", "export_merge_animation": "ACTION",
    "export_force_sampling": True, "export_frame_range": False, "export_frame_step": 1,
    "export_sampling_interpolation_fallback": "LINEAR", "export_pointer_animation": False,
    "export_convert_animation_pointer": False, "export_extra_animations": False,
    "export_optimize_animation_size": True, "export_optimize_animation_keep_anim_armature": True,
    "export_optimize_animation_keep_anim_object": False, "export_optimize_disable_viewport": False,
    "export_negative_frame": "SLIDE", "export_anim_slide_to_zero": True, "export_bake_animation": False,
    "export_anim_single_armature": True, "export_reset_pose_bones": True, "export_current_frame": False,
    "export_rest_position_armature": True, "export_anim_scene_split_object": True, "export_action_filter": False,
    # armature / skin / morph (S1-S5): inert unless a profile sets export_skins / export_morph
    "export_skins": False, "export_def_bones": False, "export_hierarchy_flatten_bones": False,
    "export_armature_object_remove": False, "export_leaf_bone": False, "export_influence_nb": 4,
    "export_all_influences": False, "export_morph": False, "export_morph_normal": True, "export_morph_tangent": False,
    "export_morph_animation": True, "export_morph_reset_sk_data": True, "export_try_sparse_sk": True,
    "export_try_omit_sparse_sk": False,
}

IMPORT_DEFAULTED_ON_PURPOSE = {
    "filter_glob": "file-browser filter (HIDDEN)",
    "directory": "file-browser multi-file directory; filepath is used",
    "files": "file-browser multi-file list; filepath is used",
}
IMPORT_OPTIONS = {
    "export_import_convert_lighting_mode": "SPEC", "loglevel": logging.WARNING, "import_pack_images": False,
    "merge_vertices": False, "import_shading": "NORMALS", "bone_heuristic": "BLENDER", "disable_bone_shape": True,
    "bone_shape_scale_factor": 1.0, "guess_original_bind_pose": True, "import_webp_texture": False,
    "import_unused_materials": False, "import_select_created_objects": False, "import_scene_extras": True,
    "import_scene_as_collection": True, "import_merge_material_slots": True, "import_point_as_pointcloud": False,
}


@dataclass(frozen=True)
class Profile:
    name: str
    summary: str
    gltf: dict                     # exporter overrides on top of BASE_OPTIONS
    double_sided: str              # "explicit": only tagged materials; "alpha": MASK/BLEND cards + tagged
    tangents: str = "auto"         # "auto": on when an exported material uses a normal map
    color0: str = "RGB"            # "RGB": COLOR_0 must be VEC3; "RGBA": alpha kept
    max_uv_sets: int = 2
    max_vertex_attributes: int = 8  # WebGPU vertex-buffer limit (babylon community practice §3.2)
    discouraged_attributes: tuple = ()
    skinned: bool = False
    embed_images: bool = False
    budget_class: str = ""
    identity_skinned_mesh: bool = False


PROFILES = {
    "static_world": Profile(
        "static_world", "World cells, terrain, relief, buildings, rocks: opaque and single-sided; thin geometry is "
        "modelled double-faced by the builder", {}, "explicit", budget_class="world_cell"),
    "foliage": Profile(
        "foliage", "Trees, bushes, grass and flower cards: alpha-tested cards double-sided, bark single-sided, "
        "TEXCOORD_1 wind data and COLOR_0 shading kept", {}, "alpha", budget_class="tree_lod0"),
    "character_skinned": Profile(
        "character_skinned", "Heroes, monsters, NPCs, pets: skins, morphs and NLA clips; modifiers other than "
        "Armature must be applied by the recipe (shape keys survive); cloth is tagged double-sided",
        {"export_apply": False, "export_animations": True, "export_skins": True, "export_def_bones": True,
         "export_morph": True}, "explicit", discouraged_attributes=("COLOR_0", "TEXCOORD_1"), skinned=True,
        budget_class="hero_lod0", identity_skinned_mesh=True),
    "prop": Profile(
        "prop", "Placed props (cart, barrel, crate, lamp): opaque single-sided, shared trim/atlas textures", {},
        "explicit", budget_class="prop"),
    "impostor_card": Profile(
        "impostor_card", "Far LOD cards and crossed cards: alpha-tested double-sided, normal atlas -> tangents", {},
        "alpha", budget_class="impostor_card"),
}


class ExportValidationError(RuntimeError):
    """Raised by export_glb() after the receipt is written, when validation failed."""

    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


# ---------------------------------------------------------------------------------------------- small utilities
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_json_atomic(path: Path, payload: dict) -> None:
    text = json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True, default=_json_default) + "\n"
    write_bytes_atomic(Path(path), text.encode("utf-8"))


def _json_default(value):
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return value.as_posix()
    if np is not None and isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "to_list"):
        return value.to_list()
    return str(value)


def _r(v, nd=5):
    return None if v is None else round(float(v), nd)


def addon_version() -> str | None:
    try:
        import addon_utils
        for mod in addon_utils.modules():
            if mod.__name__ == "io_scene_gltf2":
                return ".".join(str(v) for v in mod.bl_info.get("version", ()))
    except Exception:  # noqa: BLE001 - diagnostic only
        return None
    return None


def safe_stem(name: str) -> str:
    """Khronos RTACG R2 file names: a-z, 0-9, '_' and '-', starting with a letter."""
    s = re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_-") or "image"
    return s if s[0].isalpha() else f"img_{s}"


def image_info(data: bytes) -> dict:
    """mime type and size from the file header (PNG IHDR, JPEG SOF, WebP VP8/VP8L/VP8X)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        color_type = data[25]
        return {"mime": "image/png", "ext": "png", "width": w, "height": h,
                "has_alpha_channel": color_type in (4, 6), "bit_depth": data[24]}
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return {"mime": "image/jpeg", "ext": "jpg", "width": w, "height": h, "has_alpha_channel": False}
            i += 2 + seg
        return {"mime": "image/jpeg", "ext": "jpg", "width": None, "height": None, "has_alpha_channel": False}
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return {"mime": "image/webp", "ext": "webp", "width": None, "height": None, "has_alpha_channel": None}
    if data[:12] == b"\xabKTX 20\xbb\r\n\x1a\n":
        w, h = struct.unpack("<II", data[20:28])
        return {"mime": "image/ktx2", "ext": "ktx2", "width": w, "height": h, "has_alpha_channel": None}
    return {"mime": "application/octet-stream", "ext": "bin", "width": None, "height": None, "has_alpha_channel": None}


# ---------------------------------------------------------------------------------------------- GLB container
GLB_MAGIC, CHUNK_JSON, CHUNK_BIN = b"glTF", 0x4E4F534A, 0x004E4942
COMPONENT = {5120: ("BYTE", 1, "i1"), 5121: ("UNSIGNED_BYTE", 1, "u1"), 5122: ("SHORT", 2, "<i2"),
             5123: ("UNSIGNED_SHORT", 2, "<u2"), 5125: ("UNSIGNED_INT", 4, "<u4"), 5126: ("FLOAT", 4, "<f4")}
TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def read_glb(path_or_bytes) -> tuple[dict, bytes]:
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else Path(path_or_bytes).read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC or version != 2 or length != len(data):
        raise ValueError("not a valid GLB 2.0 container (magic/version/length)")
    jlen, jtype = struct.unpack_from("<II", data, 12)
    if jtype != CHUNK_JSON:
        raise ValueError("first GLB chunk is not JSON")
    gltf = json.loads(bytes(data[20:20 + jlen]).decode("utf-8"))
    binary = b""
    off = 20 + jlen
    if off + 8 <= len(data):
        blen, btype = struct.unpack_from("<II", data, off)
        if btype == CHUNK_BIN:
            binary = bytes(data[off + 8:off + 8 + blen])
    return gltf, binary


def pack_glb(gltf: dict, binary: bytes) -> bytes:
    js = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = [struct.pack("<II", len(js), CHUNK_JSON), js]
    if binary:
        b = bytes(binary) + b"\0" * (-len(binary) % 4)
        out += [struct.pack("<II", len(b), CHUNK_BIN), b]
    body = b"".join(out)
    return struct.pack("<4sII", GLB_MAGIC, 2, 12 + len(body)) + body


def read_accessor(gltf: dict, binary: bytes, index: int):
    """Accessor data as float64 (count, n) with normalisation decoded. Plain (non-sparse) accessors only."""
    acc = gltf["accessors"][index]
    if "sparse" in acc:
        raise ValueError(f"accessor {index} is sparse")
    _, csize, dtype = COMPONENT[acc["componentType"]]
    n = TYPE_SIZE[acc["type"]]
    count = acc["count"]
    if "bufferView" not in acc:
        return np.zeros((count, n), np.float64)
    view = gltf["bufferViews"][acc["bufferView"]]
    if view.get("buffer", 0) != 0 or "extensions" in view:
        raise ValueError(f"accessor {index}: buffer view is external or compressed")
    stride = view.get("byteStride") or csize * n
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    raw = np.frombuffer(binary, dtype=np.uint8, count=stride * (count - 1) + csize * n, offset=start) if count else \
        np.zeros(0, np.uint8)
    if stride == csize * n:
        arr = raw.view(dtype).reshape(count, n).astype(np.float64)
    else:
        rows = np.lib.stride_tricks.as_strided(raw, shape=(count, csize * n), strides=(stride, 1))
        arr = np.ascontiguousarray(rows).view(dtype).reshape(count, n).astype(np.float64)
    if acc.get("normalized"):
        name = COMPONENT[acc["componentType"]][0]
        div = {"UNSIGNED_BYTE": 255.0, "UNSIGNED_SHORT": 65535.0, "BYTE": 127.0, "SHORT": 32767.0}[name]
        arr = np.maximum(arr / div, -1.0)
    return arr


def compact_buffer_views(gltf: dict, binary: bytes) -> bytes:
    """Drop unreferenced buffer views and repack buffer 0 with 4-byte alignment."""
    views = gltf.get("bufferViews", [])
    refs = []  # (container, key) pairs pointing at a buffer view index
    for acc in gltf.get("accessors", []):
        if "bufferView" in acc:
            refs.append((acc, "bufferView"))
        sp = acc.get("sparse")
        if sp:
            refs.append((sp["indices"], "bufferView"))
            refs.append((sp["values"], "bufferView"))
    for img in gltf.get("images", []):
        if "bufferView" in img:
            refs.append((img, "bufferView"))
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            draco = prim.get("extensions", {}).get("KHR_draco_mesh_compression")
            if draco:
                refs.append((draco, "bufferView"))
    used = sorted({c[k] for c, k in refs})
    out = bytearray()
    new_views, remap = [], {}
    for old in used:
        v = dict(views[old])
        if v.get("buffer", 0) != 0:
            raise ValueError("compact_buffer_views supports a single buffer")
        start = v.get("byteOffset", 0)
        chunk = binary[start:start + v["byteLength"]]
        out += b"\0" * (-len(out) % 4)
        v["byteOffset"] = len(out)
        out += chunk
        remap[old] = len(new_views)
        new_views.append(v)
    for container, key in refs:
        container[key] = remap[container[key]]
    gltf["bufferViews"] = new_views
    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = len(out)
    return bytes(out)


def color0_to_rgb(gltf: dict, binary: bytes) -> tuple[bytes, list]:
    """Rewrite every VEC4 COLOR_0 accessor as FLOAT VEC3 (alpha dropped). GAP-3: Babylon sets hasVertexAlpha on VEC4."""
    converted, done = [], {}
    out = bytearray(binary)
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            idx = prim.get("attributes", {}).get("COLOR_0")
            if idx is None or gltf["accessors"][idx]["type"] != "VEC4" or idx in done:
                continue
            acc = gltf["accessors"][idx]
            data = read_accessor(gltf, bytes(out), idx)
            rgb = np.ascontiguousarray(np.clip(data[:, :3], 0.0, 1.0), dtype="<f4")
            out += b"\0" * (-len(out) % 4)
            gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(out), "byteLength": rgb.nbytes, "target": 34962})
            out += rgb.tobytes()
            before = f"VEC4/{COMPONENT[acc['componentType']][0]}{'/normalized' if acc.get('normalized') else ''}"
            alpha = data[:, 3] if len(data) else np.ones(1)
            for k in ("normalized", "min", "max", "byteOffset"):
                acc.pop(k, None)
            acc.update(bufferView=len(gltf["bufferViews"]) - 1, componentType=5126, type="VEC3")
            done[idx] = True
            converted.append({"accessor": idx, "mesh": mesh.get("name"), "from": before, "to": "VEC3/FLOAT",
                              "count": int(acc["count"]), "alpha_min": _r(alpha.min(), 4), "alpha_max": _r(alpha.max(), 4)})
    if converted:
        if gltf.get("buffers"):
            gltf["buffers"][0]["byteLength"] = len(out)
        return compact_buffer_views(gltf, bytes(out)), converted
    return binary, converted


def _quat_to_mat3(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def node_local_matrix(node: dict):
    if "matrix" in node:
        m = node["matrix"]  # column-major
        return np.array(m, np.float64).reshape(4, 4).T
    t = node.get("translation", [0, 0, 0])
    r = node.get("rotation", [0, 0, 0, 1])
    s = node.get("scale", [1, 1, 1])
    m = np.eye(4)
    m[:3, :3] = np.array(_quat_to_mat3(r)) * np.array(s)[None, :]
    m[:3, 3] = t
    return m


def node_world_matrices(gltf: dict) -> dict:
    nodes = gltf.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    cache = {}

    def world(i):
        if i not in cache:
            local = node_local_matrix(nodes[i])
            cache[i] = world(parent[i]) @ local if i in parent else local
        return cache[i]

    return {i: world(i) for i in range(len(nodes))}


def glb_facts(gltf: dict, binary: bytes = b"", base_dir: Path | None = None) -> dict:
    """Counts, attributes, materials, images, extensions and world bounds (glTF space) of a parsed GLB."""
    accessors = gltf.get("accessors", [])
    materials = gltf.get("materials", [])
    worlds = node_world_matrices(gltf) if gltf.get("nodes") else {}
    meshes_out, tri_total, vert_total = [], 0, 0
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    mesh_nodes = {}
    for ni, node in enumerate(gltf.get("nodes", [])):
        if "mesh" in node:
            mesh_nodes.setdefault(node["mesh"], []).append(ni)
    mat_usage = {}
    for mi, mesh in enumerate(gltf.get("meshes", [])):
        prims = []
        for prim in mesh.get("primitives", []):
            mode = prim.get("mode", 4)
            acc_i = prim.get("indices", prim["attributes"]["POSITION"])
            count = accessors[acc_i]["count"]
            tris = count // 3 if mode == 4 else 0
            verts = accessors[prim["attributes"]["POSITION"]]["count"]
            attrs = {}
            for sem, ai in sorted(prim.get("attributes", {}).items()):
                a = accessors[ai]
                attrs[sem] = f"{a['type']}/{COMPONENT[a['componentType']][0]}{'/normalized' if a.get('normalized') else ''}"
            m = prim.get("material")
            c0_mean = None
            if binary and np is not None and "COLOR_0" in prim.get("attributes", {}):
                try:
                    c0 = read_accessor(gltf, binary, prim["attributes"]["COLOR_0"])
                    # Match the source's per-corner mean. Shared indexed vertices occur once per
                    # triangle corner, not once per unique vertex; split seams otherwise bias this gate.
                    if "indices" in prim and mode == 4:
                        indices = read_accessor(gltf, binary, prim["indices"]).reshape(-1)
                        if len(indices) and (indices.min() < 0 or indices.max() >= len(c0)):
                            raise ValueError("COLOR_0 primitive index outside accessor")
                        c0 = c0[indices.astype(np.int64)]
                    c0_mean = [round(float(v), 4) for v in c0[:, :3].mean(0)] if len(c0) else None
                except ValueError:
                    c0_mean = None
            prims.append({"material": materials[m].get("name") if m is not None and m < len(materials) else None,
                          "material_index": m,
                          "requires_normal_tangent": bool(m is not None and 0 <= m < len(materials)
                                                          and "normalTexture" in materials[m]),
                          "mode": mode, "triangles": tris, "vertices": verts, "attributes": attrs,
                          "targets": len(prim.get("targets", [])), "color0_mean": c0_mean})
            if m is not None:
                u = mat_usage.setdefault(m, {"primitives": 0, "triangles": 0})
                u["primitives"] += 1
                u["triangles"] += tris
            nodes_using = mesh_nodes.get(mi, [])
            pos_i = prim["attributes"]["POSITION"]
            pos = None
            if binary and np is not None:
                try:
                    pos = read_accessor(gltf, binary, pos_i)
                except ValueError:
                    pos = None
            if pos is None:
                a = accessors[pos_i]
                if "min" in a and "max" in a:
                    mn, mx = a["min"], a["max"]
                    pos = np.array([[x, y, z] for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])])
            if pos is not None and len(pos):
                for ni in nodes_using:
                    w = worlds[ni] if "skin" not in gltf["nodes"][ni] else np.eye(4)
                    p = pos[:, :3] @ w[:3, :3].T + w[:3, 3]
                    lo = np.minimum(lo, p.min(0))
                    hi = np.maximum(hi, p.max(0))
            inst = max(1, len(nodes_using))
            tri_total += tris * inst
            vert_total += verts * inst
        meshes_out.append({"name": mesh.get("name"), "nodes": [gltf["nodes"][n].get("name") for n in mesh_nodes.get(mi, [])],
                           "primitives": prims, "triangles": sum(p["triangles"] for p in prims),
                           "vertices": sum(p["vertices"] for p in prims)})
    mats_out = []
    for i, m in enumerate(materials):
        pbr = m.get("pbrMetallicRoughness", {})
        tex = {}
        for slot, holder in (("baseColorTexture", pbr), ("metallicRoughnessTexture", pbr), ("normalTexture", m),
                             ("occlusionTexture", m), ("emissiveTexture", m)):
            if slot in holder:
                ti = holder[slot]["index"]
                t = gltf.get("textures", [])[ti]
                src = t.get("source", t.get("extensions", {}).get("KHR_texture_basisu", {}).get("source"))
                tex[slot] = {"texture": ti, "image": src, "texCoord": holder[slot].get("texCoord", 0)}
        use = mat_usage.get(i, {"primitives": 0, "triangles": 0})
        mats_out.append({"name": m.get("name"), "alphaMode": m.get("alphaMode", "OPAQUE"),
                         "alphaCutoff": m.get("alphaCutoff") if m.get("alphaMode") == "MASK" else None,
                         "doubleSided": bool(m.get("doubleSided", False)), "textures": tex,
                         "extensions": sorted(m.get("extensions", {}).keys()), **use})
    images_out = []
    for i, img in enumerate(gltf.get("images", [])):
        entry = {"index": i, "name": img.get("name"), "mimeType": img.get("mimeType"),
                 "uri": img.get("uri"), "embedded": "bufferView" in img}
        if base_dir is not None and img.get("uri") and not img["uri"].startswith("data:"):
            f = (Path(base_dir) / unquote(img["uri"])).resolve()
            entry["file_exists"] = f.is_file()
            if f.is_file():
                entry["bytes"] = f.stat().st_size
        images_out.append(entry)
    bounds = None if not np.isfinite(lo).all() else {"min": [_r(v) for v in lo], "max": [_r(v) for v in hi]}
    return {
        "asset": gltf.get("asset", {}), "extensionsUsed": sorted(gltf.get("extensionsUsed", [])),
        "extensionsRequired": sorted(gltf.get("extensionsRequired", [])), "nodes": len(gltf.get("nodes", [])),
        "meshes": meshes_out, "mesh_count": len(meshes_out),
        "primitives": sum(len(m["primitives"]) for m in meshes_out), "triangles": tri_total, "vertices": vert_total,
        "materials": mats_out, "material_count": len(mats_out), "images": images_out,
        "textures": len(gltf.get("textures", [])), "animations": [
            {"name": a.get("name"), "channels": len(a.get("channels", [])), "samplers": len(a.get("samplers", []))}
            for a in gltf.get("animations", [])],
        "skins": [{"name": s.get("name"), "joints": len(s.get("joints", []))} for s in gltf.get("skins", [])],
        "cameras": len(gltf.get("cameras", [])),
        "lights": len(gltf.get("extensions", {}).get("KHR_lights_punctual", {}).get("lights", [])),
        "bounds_gltf": bounds, "binary_bytes": len(binary),
    }


# ---------------------------------------------------------------------------------------------- RNA introspection
def _rna_props(op) -> dict:
    return {p.identifier: p for p in op.get_rna_type().properties if p.identifier != "rna_type"}


def exporter_rna() -> dict:
    return _rna_props(bpy.ops.export_scene.gltf)


def importer_rna() -> dict:
    return _rna_props(bpy.ops.import_scene.gltf)


def describe_rna(props: dict) -> list:
    out = []
    for ident, p in sorted(props.items()):
        d = {"id": ident, "type": p.type, "name": p.name}
        if p.type == "ENUM":
            d["items"] = [i.identifier for i in p.enum_items]
            if not d["items"]:  # dynamic enum (export_format): reading .default only logs an RNA warning
                d["default"] = None
                d["items"] = sorted(_format_items()) if ident == "export_format" else []
                out.append(d)
                continue
            d["default"] = sorted(p.default_flag) if p.is_enum_flag else p.default
        elif p.type in ("BOOLEAN", "INT", "FLOAT", "STRING"):
            d["default"] = list(p.default_array) if getattr(p, "array_length", 0) else p.default
        out.append(d)
    return out


def rna_signature(props: dict) -> str:
    return sha256_bytes(json.dumps(describe_rna(props), sort_keys=True, default=str).encode("utf-8"))


def _format_items() -> set:
    try:
        from io_scene_gltf2 import get_format_items
        return {i[0] for i in get_format_items(None, bpy.context)}
    except Exception:  # noqa: BLE001
        return {"GLB", "GLTF_SEPARATE"}


def check_options(options: dict, props: dict, defaulted: dict) -> list:
    """Problems with an option dict against the installed RNA: unknown, missing, wrong type or out of range."""
    problems = []
    for key in sorted(set(options) - set(props)):
        problems.append(f"unknown option {key!r} (not in the installed exporter/importer)")
    for key in sorted(set(props) - set(options) - set(defaulted)):
        problems.append(f"option {key!r} is neither set nor listed as defaulted on purpose")
    for key in sorted(set(defaulted) - set(props)):
        problems.append(f"defaulted-on-purpose option {key!r} no longer exists")
    for key, value in options.items():
        p = props.get(key)
        if p is None:
            continue
        if p.type == "BOOLEAN" and not isinstance(value, bool):
            problems.append(f"{key}: expected bool, got {value!r}")
        elif p.type == "INT":
            if not isinstance(value, int) or isinstance(value, bool) or not (p.hard_min <= value <= p.hard_max):
                problems.append(f"{key}: int {value!r} outside [{p.hard_min}, {p.hard_max}]")
        elif p.type == "FLOAT":
            if not isinstance(value, (int, float)) or not (p.hard_min <= float(value) <= p.hard_max):
                problems.append(f"{key}: float {value!r} outside [{p.hard_min}, {p.hard_max}]")
        elif p.type == "STRING" and not isinstance(value, str):
            problems.append(f"{key}: expected str, got {value!r}")
        elif p.type == "ENUM":
            items = {i.identifier for i in p.enum_items} or (_format_items() if key == "export_format" else set())
            if items and value not in items:
                problems.append(f"{key}: {value!r} not in {sorted(items)}")
    return problems


def resolve_export_options(profile: str | Profile, **per_call) -> dict:
    """The complete explicit exporter option dict for a profile; per_call keys must be PER_CALL_OPTIONS."""
    prof = PROFILES[profile] if isinstance(profile, str) else profile
    opts = dict(BASE_OPTIONS)
    opts.update(prof.gltf)
    opts.update({"filepath": "", "collection": "", "export_format": "GLB", "export_texture_dir": ""})
    bad = sorted(set(per_call) - set(PER_CALL_OPTIONS))
    if bad:
        raise ValueError(f"not per-call options: {bad}")
    opts.update(per_call)
    return opts


def classification_report() -> dict:
    """Which installed exporter/importer options the helper sets, defaults on purpose, or misses (used by tests)."""
    exp, imp = exporter_rna(), importer_rna()
    per_profile = {}
    for name in PROFILES:
        opts = resolve_export_options(name)
        per_profile[name] = check_options(opts, exp, DEFAULTED_ON_PURPOSE)
    imp_opts = dict(IMPORT_OPTIONS, filepath="")
    return {"exporter_options": len(exp), "importer_options": len(imp),
            "exporter_rna_sha256": rna_signature(exp), "importer_rna_sha256": rna_signature(imp),
            "set_explicitly": sorted(set(resolve_export_options("static_world")) & set(exp)),
            "defaulted_on_purpose": DEFAULTED_ON_PURPOSE, "problems_by_profile": per_profile,
            "import_problems": check_options(imp_opts, imp, IMPORT_DEFAULTED_ON_PURPOSE)}


# ---------------------------------------------------------------------------------------------- Blender-side policy
def _bsdf_nodes(mat):
    nt = getattr(mat, "node_tree", None)
    return [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"] if nt else []


def material_uses_alpha(mat) -> bool:
    for bsdf in _bsdf_nodes(mat):
        a = bsdf.inputs.get("Alpha")
        if a is not None and (a.is_linked or a.default_value < 0.999):
            return True
    return False


def material_normal_map_images(mat) -> list:
    """Images feeding a tangent-space Normal Map node that is linked into the shader (exporter normalTexture)."""
    nt = getattr(mat, "node_tree", None)
    out = []
    if not nt:
        return out
    for n in nt.nodes:
        if n.type == "NORMAL_MAP" and n.inputs["Color"].is_linked and n.outputs["Normal"].is_linked:
            src = n.inputs["Color"].links[0].from_node
            if src.type == "TEX_IMAGE" and src.image is not None:
                out.append(src.image)
    return out


def material_color_images(mat) -> list:
    """Images reaching Base Color / Emission (should be sRGB)."""
    nt = getattr(mat, "node_tree", None)
    out = []
    if not nt:
        return out
    for bsdf in _bsdf_nodes(mat):
        for sock_name in ("Base Color", "Emission Color"):
            sock = bsdf.inputs.get(sock_name)
            stack = [sock.links[0].from_node] if sock is not None and sock.is_linked else []
            seen = set()
            while stack:
                node = stack.pop()
                if node.name in seen:
                    continue
                seen.add(node.name)
                if node.type == "TEX_IMAGE" and node.image is not None:
                    out.append(node.image)
                    continue
                for inp in node.inputs:
                    if inp.is_linked:
                        stack.append(inp.links[0].from_node)
    return out


def decide_double_sided(mat, prof: Profile, explicit_double, explicit_single) -> tuple[bool, str]:
    if mat.name in explicit_single:
        return False, "export_glb(single_sided_materials=...)"
    if mat.name in explicit_double:
        return True, "export_glb(double_sided_materials=...)"
    tag = mat.get("xex_double_sided") if hasattr(mat, "get") else None
    if tag is not None:
        return bool(tag), 'material["xex_double_sided"]'
    if prof.double_sided == "alpha" and material_uses_alpha(mat):
        return True, f"profile {prof.name}: alpha-tested/blended card"
    return False, f"profile {prof.name}: opaque material single-sided (GAP-4)"


def _mesh_objects(objects):
    return [o for o in objects if o.type == "MESH"]


def _materials_of(objects) -> list:
    seen, out = set(), []
    for o in _mesh_objects(objects):
        for slot in o.material_slots:
            m = slot.material
            if m is not None and m.name not in seen:
                seen.add(m.name)
                out.append(m)
    return out


def _world_bounds_blender(objects, depsgraph, evaluated: bool):
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for o in _mesh_objects(objects):
        if evaluated:
            eo = o.evaluated_get(depsgraph)
            me = eo.to_mesh()
        else:
            eo, me = None, o.data
        try:
            n = len(me.vertices)
            if n:
                co = np.empty(n * 3, np.float32)
                me.vertices.foreach_get("co", co)
                m = np.array(o.matrix_world, np.float64)
                p = co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
                lo = np.minimum(lo, p.min(0))
                hi = np.maximum(hi, p.max(0))
        finally:
            if eo is not None:
                eo.to_mesh_clear()
    return (lo, hi) if np.isfinite(lo).all() else (None, None)


def _blender_to_gltf_bounds(lo, hi):
    # glTF +Y up: (x, y, z)_gltf = (x, z, -y)_blender
    return [lo[0], lo[2], -hi[1]], [hi[0], hi[2], -lo[1]]


def source_facts(objects, prof: Profile, apply_modifiers: bool) -> dict:
    dg = bpy.context.evaluated_depsgraph_get()
    meshes = []
    for o in _mesh_objects(objects):
        if apply_modifiers:
            eo = o.evaluated_get(dg)
            me = eo.to_mesh()
        else:
            eo, me = None, o.data
        try:
            me.calc_loop_triangles()
            meshes.append({
                "object": o.name, "triangles": len(me.loop_triangles), "vertices": len(me.vertices),
                "polygons": len(me.polygons), "uv_layers": [uv.name for uv in me.uv_layers],
                "color_attributes": [{"name": c.name, "domain": c.domain, "data_type": c.data_type}
                                     for c in me.color_attributes],
                "color_mean_by_material": _color_means_by_material(o, me),
                "color_alpha_min": _color_alpha_min(me),
                "materials": [s.material.name if s.material else None for s in o.material_slots],
                "shape_keys": len(o.data.shape_keys.key_blocks) if o.data.shape_keys else 0,
                "modifiers": [{"name": m.name, "type": m.type, "viewport": m.show_viewport, "render": m.show_render}
                              for m in o.modifiers],
            })
        finally:
            if eo is not None:
                eo.to_mesh_clear()
    lo, hi = _world_bounds_blender(objects, dg, apply_modifiers)
    return {"meshes": meshes, "triangles": sum(m["triangles"] for m in meshes),
            "bounds_blender": None if lo is None else {"min": [_r(v) for v in lo], "max": [_r(v) for v in hi]}}


def preflight(objects, prof: Profile, apply_modifiers: bool) -> tuple[list, list, dict]:
    """Checks before export. Returns (failures, warnings, facts)."""
    failures, warnings = [], []
    meshes = _mesh_objects(objects)
    if not meshes:
        failures.append("no mesh objects to export")
    names = {o.name for o in objects}
    for o in meshes:
        loc, rot, scale = o.matrix_world.decompose()
        det = o.matrix_world.to_3x3().determinant()
        if det < 0:
            warnings.append(f"{o.name}: negative scale (winding flips in glTF)")
        uv_n = len(o.data.uv_layers)
        if uv_n > prof.max_uv_sets:
            failures.append(f"{o.name}: {uv_n} UV layers > profile {prof.name} limit {prof.max_uv_sets} "
                            "(extra TEXCOORD_n cost a vertex buffer each)")
        if apply_modifiers:
            if o.data.shape_keys:
                warnings.append(f"{o.name}: shape keys are dropped by export_apply=True (official-docs E2)")
            for m in o.modifiers:
                if m.show_render and not m.show_viewport:
                    warnings.append(f"{o.name}: modifier {m.name!r} is render-only; the exporter evaluates the "
                                    "viewport depsgraph and skips it")
        else:
            for m in o.modifiers:
                if m.type != "ARMATURE" and m.show_viewport:
                    failures.append(f"{o.name}: modifier {m.name!r} ({m.type}) must be applied in the recipe "
                                    f"(profile {prof.name} exports with export_apply=False to keep shape keys)")
                if m.type == "ARMATURE" and m.object is not None and m.object.name not in names:
                    failures.append(f"{o.name}: armature {m.object.name!r} is not in the export set")
        if prof.identity_skinned_mesh and any(m.type == "ARMATURE" for m in o.modifiers):
            if (loc.length > 1e-5 or rot.angle > 1e-5 or any(abs(s - 1.0) > 1e-5 for s in scale)):
                failures.append(f"{o.name}: skinned mesh object transform must be identity (glTF ignores it; "
                                "official-docs S4)")
        if prof.skinned and o.vertex_groups:
            over = 0
            for v in o.data.vertices:
                if sum(1 for g in v.groups if g.weight > 1e-6) > 4:
                    over += 1
            if over:
                warnings.append(f"{o.name}: {over} vertices have > 4 influences; the exporter keeps the 4 largest")
    images = {}
    for mat in _materials_of(objects):
        for img in material_normal_map_images(mat):
            images.setdefault(img.name, {"image": img, "roles": set()})["roles"].add("normal")
        for img in material_color_images(mat):
            images.setdefault(img.name, {"image": img, "roles": set()})["roles"].add("color")
    image_facts = []
    for name, rec in sorted(images.items()):
        img = rec["image"]
        w, h = img.size[:]
        cs = img.colorspace_settings.name
        if "normal" in rec["roles"] and cs not in ("Non-Color", "Raw", "Linear Rec.709", "Generic Data"):
            warnings.append(f"image {name!r}: normal map tagged {cs!r}, expected Non-Color")
        if "color" in rec["roles"] and "normal" not in rec["roles"] and cs not in ("sRGB",):
            warnings.append(f"image {name!r}: colour image tagged {cs!r}, expected sRGB")
        if w and h and (w % 4 or h % 4):
            warnings.append(f"image {name!r}: {w}x{h} is not a multiple of 4 (KTX2 needs it; official-docs B2)")
        elif w and h and (w & (w - 1) or h & (h - 1)):
            warnings.append(f"image {name!r}: {w}x{h} is not a power of two (official-docs B2)")
        if img.file_format == "JPEG":
            warnings.append(f"image {name!r}: JPEG source stacks two lossy codecs before KTX2 (GAP-7)")
        image_facts.append({"name": name, "roles": sorted(rec["roles"]), "size": [w, h], "colorspace": cs,
                            "source": img.source, "packed": img.packed_file is not None, "file_format": img.file_format})
    return failures, warnings, {"images": image_facts}


@contextlib.contextmanager
def _capture_exporter_log():
    records = []

    class _H(logging.Handler):
        def emit(self, record):
            records.append(f"{record.levelname}: {record.getMessage()}")

    handler = _H(level=logging.WARNING)
    # the add-on logs export warnings to "glTFImporter" and errors to "glTFImporter_errors" (io/com/debug.py)
    loggers = [logging.getLogger("glTFImporter"), logging.getLogger("glTFImporter_errors")]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield records
    finally:
        for logger in loggers:
            logger.removeHandler(handler)


@contextlib.contextmanager
def _export_collection(objects, name):
    scene = bpy.context.scene
    col = bpy.data.collections.new(name)
    scene.collection.children.link(col)
    try:
        for o in objects:
            if col not in o.users_collection:
                col.objects.link(o)
        bpy.context.view_layer.update()
        yield col
    finally:
        for o in list(col.objects):
            col.objects.unlink(o)
        scene.collection.children.unlink(col)
        bpy.data.collections.remove(col)


@contextlib.contextmanager
def _vertex_alpha_policy(materials, prof: Profile, records: list):
    """COLOR_0 RGB policy: detach links from a colour attribute's Alpha output for the export, restore afterwards.

    Why: the exporter keys COLOR_0 per material by (colour layer, alpha layer). When one material of a mesh uses the
    vertex alpha and another does not (Blender's glTF importer wires COLOR_0 alpha into MASK materials only), the
    exporter warns "multiple materials with different Vertex Color" and writes white COLOR_0 for one primitive.
    Under the RGB policy vertex alpha is never exported anyway (GAP-3), so the link carries nothing to the runtime."""
    removed = []
    try:
        if prof.color0 == "RGB":
            for mat in materials:
                nt = getattr(mat, "node_tree", None)
                if not nt:
                    continue
                for link in list(nt.links):
                    node = link.from_node
                    if node.type == "VERTEX_COLOR" and link.from_socket.identifier == "Alpha":
                        to_socket = link.to_socket
                        # The freed input must read 1.0 (vertex alpha == 1, the meaning of an RGB COLOR_0); a Math
                        # node's default 0.5 would otherwise be folded into baseColorFactor alpha by the exporter.
                        old = getattr(to_socket, "default_value", None)
                        removed.append((mat, link.from_socket, to_socket, old))
                        records.append({"material": mat.name, "from": f"{node.name}.{link.from_socket.identifier}",
                                        "to": f"{link.to_node.name}.{to_socket.identifier}", "replaced_with": 1.0})
                        nt.links.remove(link)
                        if isinstance(old, float):
                            to_socket.default_value = 1.0
        yield
    finally:
        for mat, from_socket, to_socket, old in removed:
            if isinstance(old, float):
                to_socket.default_value = old
            mat.node_tree.links.new(from_socket, to_socket)


def _color_means_by_material(obj, me) -> dict:
    """Mean linear RGB of the render colour attribute per material slot (what COLOR_0 should carry)."""
    if not me.color_attributes or np is None:
        return {}
    idx = me.color_attributes.render_color_index
    col = me.color_attributes[idx if idx >= 0 else 0]
    n_loops, n_polys = len(me.loops), len(me.polygons)
    if not n_loops or not n_polys:
        return {}
    if col.domain == "CORNER":
        rgba = np.empty(n_loops * 4, np.float32)
        col.data.foreach_get("color", rgba)
        per_loop = rgba.reshape(-1, 4)[:, :3]
    elif col.domain == "POINT":
        rgba = np.empty(len(me.vertices) * 4, np.float32)
        col.data.foreach_get("color", rgba)
        vidx = np.empty(n_loops, np.int32)
        me.loops.foreach_get("vertex_index", vidx)
        per_loop = rgba.reshape(-1, 4)[vidx, :3]
    else:
        return {}
    # glTF draws triangles. Quad/n-gon triangulation repeats some polygon
    # corners, so the source mean must use those same drawn triangle corners.
    me.calc_loop_triangles()
    n_triangles = len(me.loop_triangles)
    triangle_loops = np.empty(n_triangles * 3, np.int32)
    triangle_materials = np.empty(n_triangles, np.int32)
    me.loop_triangles.foreach_get("loops", triangle_loops)
    me.loop_triangles.foreach_get("material_index", triangle_materials)
    per_corner = per_loop[triangle_loops]
    loop_mat = np.repeat(triangle_materials, 3)
    out = {}
    for mi, slot in enumerate(obj.material_slots):
        if slot.material is None:
            continue
        sel = loop_mat == mi
        if sel.any():
            out[slot.material.name] = [round(float(v), 4) for v in per_corner[sel].mean(0)]
    return out


def _color_alpha_min(me) -> float:
    if not me.color_attributes or np is None:
        return 1.0
    idx = me.color_attributes.render_color_index
    col = me.color_attributes[idx if idx >= 0 else 0]
    n = len(col.data)
    if not n:
        return 1.0
    rgba = np.empty(n * 4, np.float32)
    col.data.foreach_get("color", rgba)
    return round(float(rgba[3::4].min()), 4)


@contextlib.contextmanager
def _culling_policy(decisions: dict):
    """Temporarily set use_backface_culling (= not doubleSided) per material; restored afterwards."""
    saved = {}
    try:
        for mat, (double, _reason) in decisions.items():
            saved[mat] = mat.use_backface_culling
            mat.use_backface_culling = not double
        yield
    finally:
        for mat, value in saved.items():
            mat.use_backface_culling = value


def store_texture(data: bytes, image_name: str, texture_dir: Path) -> tuple[Path, str, bool]:
    """Write an image into the shared folder once per content hash. Returns (file, sha256, reused)."""
    texture_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(data)
    ext = image_info(data)["ext"]
    tag = f"-{digest[:12]}.{ext}"
    for existing in sorted(texture_dir.glob(f"*{tag}")):
        if existing.is_file() and sha256_file(existing) == digest:
            return existing, digest, True
    target = texture_dir / f"{safe_stem(image_name)}{tag}"
    write_bytes_atomic(target, data)
    return target, digest, False


def _externalise_images(gltf: dict, src_dir: Path, glb_path: Path, texture_dir: Path, uri_prefix: str | None) -> list:
    out = []
    for img in gltf.get("images", []):
        uri = img.get("uri")
        if not uri or uri.startswith("data:"):
            raise RuntimeError(f"image {img.get('name')!r} has no file uri in the separate export")
        data = (src_dir / unquote(uri)).read_bytes()
        target, digest, reused = store_texture(data, img.get("name") or Path(uri).stem, texture_dir)
        if uri_prefix:
            new_uri = uri_prefix.rstrip("/") + "/" + quote(target.name)
        else:
            try:
                new_uri = quote(Path(os.path.relpath(target, glb_path.parent)).as_posix())
            except ValueError as exc:  # different drive on Windows
                raise RuntimeError(f"texture_dir {texture_dir} has no relative path from {glb_path.parent}; "
                                   "pass texture_uri_prefix") from exc
        info = image_info(data)
        img["uri"] = new_uri
        img["mimeType"] = info["mime"]
        out.append({"name": img.get("name"), "uri": new_uri, "file": rel(target), "sha256": digest,
                    "bytes": len(data), "width": info["width"], "height": info["height"], "mime": info["mime"],
                    "has_alpha_channel": info["has_alpha_channel"], "dedup": "reused" if reused else "new"})
    return out


def _embedded_image_facts(gltf: dict, binary: bytes) -> list:
    out = []
    for img in gltf.get("images", []):
        view = gltf["bufferViews"][img["bufferView"]]
        data = binary[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
        info = image_info(data)
        out.append({"name": img.get("name"), "uri": None, "file": None, "sha256": sha256_bytes(data),
                    "bytes": len(data), "width": info["width"], "height": info["height"], "mime": info["mime"],
                    "has_alpha_channel": info["has_alpha_channel"], "dedup": "embedded"})
    return out


# ---------------------------------------------------------------------------------------------- re-import validation
def _strip_suffix(name: str, expected: set) -> str:
    base = re.sub(r"\.\d{3}$", "", name)
    return base if base in expected and name not in expected else name


def reimport_facts(glb_path: Path, expected_materials: set, mode: str = "scratch") -> dict:
    """Import the written GLB into a clean scene and measure it. mode 'scratch' keeps the caller's session
    (new empty scene, every created datablock removed afterwards); 'reset' starts from read_factory_settings."""
    t0 = time.time()
    kinds = ("objects", "meshes", "materials", "images", "textures", "node_groups", "armatures", "actions",
             "collections", "cameras", "lights", "curves", "worlds")
    window = bpy.context.window
    if mode == "reset":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        window = bpy.context.window
    before = {k: set(getattr(bpy.data, k)) for k in kinds}
    prev_scene = window.scene if window else bpy.context.scene
    scn = bpy.data.scenes.new(f"xex_reimport_{uuid.uuid4().hex[:8]}")
    opts = dict(IMPORT_OPTIONS, filepath=str(glb_path))
    try:
        if window:
            window.scene = scn
            bpy.ops.import_scene.gltf(**opts)
        else:  # pragma: no cover - background Blender 5.2 provides wm.windows[0]
            with bpy.context.temp_override(scene=scn):
                bpy.ops.import_scene.gltf(**opts)
        new_objects = [o for o in bpy.data.objects if o not in before["objects"]]
        meshes = [o for o in new_objects if o.type == "MESH"]
        tris = 0
        per_mesh = []
        for o in meshes:
            me = o.data
            me.calc_loop_triangles()
            tris += len(me.loop_triangles)
            per_mesh.append({"object": o.name, "triangles": len(me.loop_triangles),
                             "uv_layers": len(me.uv_layers),
                             "color_attributes": [{"name": c.name, "domain": c.domain, "data_type": c.data_type}
                                                  for c in me.color_attributes]})
        lo, hi = _world_bounds_blender(meshes, None, False)
        mats = {}
        for o in meshes:
            for s in o.material_slots:
                if s.material is not None:
                    mats[_strip_suffix(s.material.name, expected_materials)] = {
                        "use_backface_culling": bool(s.material.use_backface_culling),
                        "blend_method": getattr(s.material, "surface_render_method", None)}
        return {"mode": mode, "objects": len(new_objects), "mesh_objects": len(meshes), "triangles": tris,
                "meshes": per_mesh, "materials": mats,
                "bounds_blender": None if lo is None else {"min": [_r(v) for v in lo], "max": [_r(v) for v in hi]},
                "armatures": sum(1 for o in new_objects if o.type == "ARMATURE"),
                "cameras": sum(1 for o in new_objects if o.type == "CAMERA"),
                "lights": sum(1 for o in new_objects if o.type == "LIGHT"),
                "actions_created": len(set(bpy.data.actions) - before["actions"]),
                "seconds": round(time.time() - t0, 2)}
    finally:
        created = []
        for k in kinds:
            created += [i for i in getattr(bpy.data, k) if i not in before[k]]
        if window:
            window.scene = prev_scene
        bpy.data.scenes.remove(scn)
        if created:
            bpy.data.batch_remove(created)


def _bounds_dev(a, b) -> float | None:
    if not a or not b:
        return None
    return max(max(abs(x - y) for x, y in zip(a["min"], b["min"])), max(abs(x - y) for x, y in zip(a["max"], b["max"])))


def validate_export(prof: Profile, src: dict, facts: dict, reimp: dict | None, decided_all: dict, tangents: bool,
                    embed: bool, images: list) -> tuple[list, list, list]:
    """Compare source, GLB and re-import. decided_all = {material name: (double_sided, reason)}.
    Returns (checks, failures, warnings)."""
    checks, failures, warnings = [], [], []

    def check(name, ok, detail, severity="fail"):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            (failures if severity == "fail" else warnings).append(f"{name}: {detail}")

    used, req = set(facts["extensionsUsed"]), set(facts["extensionsRequired"])
    forbidden = sorted(e for e in used | req if e in FORBIDDEN_EXTENSIONS)
    check("no_forbidden_extensions", not forbidden, {e: FORBIDDEN_EXTENSIONS[e] for e in forbidden} or "none")
    check("extensions_required_subset_used", req <= used, {"required": sorted(req), "used": sorted(used)})
    check("extensions_babylon_loadable", used <= BABYLON_LOADABLE, sorted(used - BABYLON_LOADABLE) or "all loadable")
    pricey = sorted({e for m in facts["materials"] for e in m["extensions"]} & EXPENSIVE_MATERIAL_EXTENSIONS)
    check("no_expensive_material_extensions", not pricey, pricey or "none", "warn")
    check("triangles_source_eq_glb", src["triangles"] == facts["triangles"],
          {"source": src["triangles"], "glb": facts["triangles"]})
    if reimp is not None:
        check("triangles_glb_eq_reimport", facts["triangles"] == reimp["triangles"],
              {"glb": facts["triangles"], "reimport": reimp["triangles"]})
    sb = src.get("bounds_blender")
    if sb:
        extent = max(b - a for a, b in zip(sb["min"], sb["max"]))
        tol = max(1e-4, 1e-5 * extent)
        glo, ghi = _blender_to_gltf_bounds(sb["min"], sb["max"])
        dev = _bounds_dev({"min": glo, "max": ghi}, facts.get("bounds_gltf"))
        sev = "warn" if prof.skinned else "fail"
        check("bounds_source_eq_glb_yup", dev is not None and dev <= tol,
              {"max_dev_m": _r(dev, 7), "tolerance_m": _r(tol, 7), "glb_bounds_gltf": facts.get("bounds_gltf"),
               "source_bounds_as_gltf": {"min": [_r(v) for v in glo], "max": [_r(v) for v in ghi]}}, sev)
        if reimp is not None:
            dev2 = _bounds_dev(sb, reimp.get("bounds_blender"))
            check("bounds_source_eq_reimport", dev2 is not None and dev2 <= tol,
                  {"max_dev_m": _r(dev2, 7), "tolerance_m": _r(tol, 7)}, sev)
    want = set(decided_all)
    got = {m["name"] for m in facts["materials"]}
    check("materials_match", want == got, {"source": sorted(want), "glb": sorted(got)})
    if reimp is not None:
        # the Blender importer adds "DefaultMaterial" to primitives that have COLOR_0 but no material
        no_mat = any(p["material"] is None for m in facts["meshes"] for p in m["primitives"])
        re_mats = set(reimp["materials"]) - ({"DefaultMaterial"} if no_mat else set())
        check("materials_reimport_match", re_mats == got, {"reimport": sorted(re_mats), "glb": sorted(got)})
    decided = {n: d for n, (d, _reason) in decided_all.items()}
    wrong = sorted(m["name"] for m in facts["materials"] if m["name"] in decided and m["doubleSided"] != decided[m["name"]])
    check("double_sided_policy", not wrong, wrong or "every material matches its policy decision")
    # A card decided double-sided by the alpha rule must really be exported MASK/BLEND (else an opaque two-sided mesh).
    opaque_double = sorted(m["name"] for m in facts["materials"]
                           if m["doubleSided"] and m["alphaMode"] == "OPAQUE"
                           and decided_all.get(m["name"], (False, ""))[1].startswith("profile"))
    check("double_sided_only_on_cards", not opaque_double, opaque_double or "no opaque material is double-sided by rule",
          "warn")
    if reimp is not None:
        mism = sorted(n for n, r in reimp["materials"].items() if n in decided and r["use_backface_culling"] == decided[n])
        check("double_sided_reimport", not mism, mism or "re-imported backface culling matches doubleSided")
    attr_sets = [(m["name"], p) for m in facts["meshes"] for p in m["primitives"]]
    over = [f"{n}/{p['material']}: {len(p['attributes'])}" for n, p in attr_sets
            if len(p["attributes"]) > prof.max_vertex_attributes]
    check("vertex_attributes_within_limit", not over, over or f"<= {prof.max_vertex_attributes} per primitive")
    unknown = sorted({s for _, p in attr_sets for s in p["attributes"]} - BABYLON_ATTRIBUTES)
    check("attributes_babylon_readable", not unknown, unknown or "all attributes are read by Babylon", "warn")
    disc = sorted({s for _, p in attr_sets for s in p["attributes"]} & set(prof.discouraged_attributes))
    check("discouraged_attributes_absent", not disc, disc or "none", "warn")
    vec4 = sorted({n for n, p in attr_sets if p["attributes"].get("COLOR_0", "").startswith("VEC4")})
    if prof.color0 == "RGB":
        check("color0_rgb", not vec4, vec4 or "COLOR_0 is VEC3 or absent (GAP-3)")
    tan_missing = sorted({n for n, p in attr_sets
                          if tangents and p["requires_normal_tangent"] and "TANGENT" not in p["attributes"]})
    tan_extra = sorted({n for n, p in attr_sets if not tangents and "TANGENT" in p["attributes"]})
    check("tangents_policy", not tan_missing and not tan_extra,
          {"tangents": tangents, "missing": tan_missing, "unexpected": tan_extra})
    joints1 = sorted({n for n, p in attr_sets if "JOINTS_1" in p["attributes"] or "WEIGHTS_1" in p["attributes"]})
    check("max_four_influences", not joints1, joints1 or "no JOINTS_1/WEIGHTS_1 (official-docs S2)")
    by_obj = {m["object"]: m for m in src["meshes"]}
    uv_lost = []
    for m in facts["meshes"]:
        for node in m["nodes"]:
            s = by_obj.get(node)
            if s:
                n_tex = max((sum(1 for k in p["attributes"] if k.startswith("TEXCOORD_")) for p in m["primitives"]),
                            default=0)
                if n_tex < len(s["uv_layers"]):
                    uv_lost.append(f"{node}: {len(s['uv_layers'])} UV layers -> {n_tex} TEXCOORD sets")
    check("uv_layers_exported", not uv_lost, uv_lost or "every source UV layer is a TEXCOORD set")
    # COLOR_0 must carry the source colour, not a white placeholder (exporter fallback when materials disagree)
    c0_bad, c0_rows = [], []
    for m in facts["meshes"]:
        for node in m["nodes"]:
            means = (by_obj.get(node) or {}).get("color_mean_by_material") or {}
            for p in m["primitives"]:
                want, got_mean = means.get(p["material"]), p.get("color0_mean")
                if want is None or got_mean is None:
                    continue
                dev = max(abs(a - b) for a, b in zip(want, got_mean))
                c0_rows.append({"node": node, "material": p["material"], "source_mean": want, "glb_mean": got_mean,
                                "max_dev": round(dev, 4)})
                if dev > 0.03:
                    c0_bad.append(f"{node}/{p['material']}: source mean {want} vs COLOR_0 mean {got_mean}")
    check("color0_values_match_source", not c0_bad, c0_bad or (c0_rows[:12] if c0_rows else "no COLOR_0 to compare"))
    if reimp is not None:
        uv_re = [f"{r['object']}: {r['uv_layers']}" for r in reimp["meshes"] if r["uv_layers"] > prof.max_uv_sets]
        check("reimport_uv_sets", not uv_re, uv_re or f"<= {prof.max_uv_sets} UV sets after re-import")
    check("no_cameras_or_lights", facts["cameras"] == 0 and facts["lights"] == 0,
          {"cameras": facts["cameras"], "lights": facts["lights"]})
    if not prof.skinned:
        check("no_animation_or_skin", not facts["animations"] and not facts["skins"],
              {"animations": len(facts["animations"]), "skins": len(facts["skins"])})
    embedded = [i["name"] for i in facts["images"] if i["embedded"]]
    if not embed:
        check("images_external", not embedded, embedded or "no embedded images")
        missing = [i["uri"] for i in facts["images"] if not i["embedded"] and not i.get("file_exists", False)]
        check("image_files_exist", not missing, missing or "every image uri resolves to a file")
    bad_mime = [i["name"] for i in images if i["mime"] not in ("image/png", "image/jpeg")]
    check("images_png_or_jpeg", not bad_mime, bad_mime or "PNG/JPEG intermediates for KTX2")
    return checks, failures, warnings


# ---------------------------------------------------------------------------------------------- main entry point
def export_glb(objects, path, profile, receipt_path=None, *, texture_dir=None, texture_uri_prefix=None,
               embed_images=None, asset_id=None, budget_class=None, materials="EXPORT", vertex_color="MATERIAL",
               vertex_color_name="Color", vertex_color_when_no_material=False, double_sided_materials=(),
               single_sided_materials=(), tangents=None, copyright_text="", extras=True, reimport="scratch",
               fail_on_validation=True, inputs=None, notes=None) -> dict:
    """Export `objects` (a list of objects or a Collection) to one GLB with the named profile.

    path              output .glb (written atomically)
    profile           one of PROFILES: static_world, foliage, character_skinned, prop, impostor_card
    receipt_path      receipt JSON (default: <path>.receipt.json)
    texture_dir       shared texture folder (default: <path.parent>/textures); images deduplicated by SHA-256
    texture_uri_prefix  write image URIs as <prefix>/<file> instead of a path relative to the GLB
    embed_images      embed images in the GLB instead (default: profile.embed_images, False everywhere)
    materials         exporter export_materials: EXPORT | PLACEHOLDER | NONE
    vertex_color      exporter export_vertex_color: MATERIAL (default) | ACTIVE | NAME | NONE
    vertex_color_name colour layer for vertex_color='NAME'
    vertex_color_when_no_material  export the active colour layer on material-less meshes (VEC4 -> rewritten RGB)
    double_sided_materials / single_sided_materials  explicit per-material overrides (names)
    tangents          None = profile policy (auto: on when a normal map is exported); True/False forces
    copyright_text    glTF asset.copyright (provenance / licence line)
    reimport          'scratch' (default; keeps the session), 'reset' (read_factory_settings first: only for
                      one-shot scripts, it ends the caller's session) or False
    fail_on_validation  raise ExportValidationError after writing the receipt when a check fails
    inputs            extra input files to hash into the receipt ({path} or paths)
    Returns the receipt dict.
    """
    if bpy is None:
        raise RuntimeError("export_glb needs Blender (bpy)")
    t0 = time.time()
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose one of {sorted(PROFILES)}")
    prof = PROFILES[profile]
    path = Path(path).resolve()
    if path.suffix.lower() != ".glb":
        raise ValueError(f"{path.name}: output must be a .glb")
    receipt_path = Path(receipt_path).resolve() if receipt_path else path.with_suffix(".receipt.json")
    texture_dir = Path(texture_dir).resolve() if texture_dir else path.parent / "textures"
    embed = prof.embed_images if embed_images is None else bool(embed_images)
    if hasattr(objects, "all_objects"):
        objects = list(objects.all_objects)
    objects = sorted({o for o in objects}, key=lambda o: o.name)
    explicit_double, explicit_single = set(double_sided_materials), set(single_sided_materials)
    receipt = {
        "schema": SCHEMA, "status": "RUNNING", "helper": rel(Path(__file__)), "helper_version": HELPER_VERSION,
        "helper_sha256": sha256_file(Path(__file__)), "blender": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode("ascii", "replace") if isinstance(bpy.app.build_hash, bytes)
        else str(bpy.app.build_hash), "gltf_addon": addon_version(), "profile": prof.name,
        "profile_summary": prof.summary, "asset_id": asset_id or path.stem,
        "budget_class": budget_class or prof.budget_class, "output": rel(path), "receipt": rel(receipt_path),
        "texture_dir": None if embed else rel(texture_dir), "embed_images": embed,
        "objects": [{"name": o.name, "type": o.type} for o in objects], "notes": notes,
        "inputs": [], "outputs": [], "warnings": [], "failures": [],
    }
    for p in (inputs or []):
        p = Path(p)
        receipt["inputs"].append({"path": rel(p), "bytes": p.stat().st_size, "sha256": sha256_file(p)})
    code_failures = []
    try:
        if bpy.app.version < MIN_BLENDER:
            raise RuntimeError(f"needs Blender >= {MIN_BLENDER}, got {bpy.app.version_string}")
        apply_modifiers = bool(resolve_export_options(prof)["export_apply"])
        failures, warnings, pre = preflight(objects, prof, apply_modifiers)
        receipt["preflight"] = pre
        receipt["warnings"] += warnings
        mats = _materials_of(objects) if materials == "EXPORT" else []
        decisions = {m: decide_double_sided(m, prof, explicit_double, explicit_single) for m in mats}
        decided_all = {m.name: dr for m, dr in decisions.items()}  # plain data: survives a 'reset' re-import
        normal_mats = sorted(m.name for m in mats if material_normal_map_images(m))
        use_tangents = (bool(normal_mats) if prof.tangents == "auto" else prof.tangents == "on") \
            if tangents is None else bool(tangents)
        receipt["policy"] = {
            "tangents": {"exported": use_tangents, "rule": prof.tangents if tangents is None else "forced",
                         "materials_with_normal_maps": normal_mats},
            "double_sided": {m.name: {"double_sided": d, "reason": r} for m, (d, r) in sorted(
                decisions.items(), key=lambda kv: kv[0].name)},
            "color0": prof.color0, "apply_modifiers": apply_modifiers, "animations": prof.skinned,
            "images": "embedded" if embed else "external shared folder, deduplicated by SHA-256",
            "y_up": True, "cameras_lights": "never",
        }
        src = source_facts(objects, prof, apply_modifiers)
        receipt["source"] = src
        if failures:
            receipt["failures"] = [f"preflight: {f}" for f in failures]
            raise ExportValidationError("preflight failed: " + "; ".join(failures), receipt)
        workdir = Path(tempfile.mkdtemp(prefix="xex-export-"))
        try:
            fmt = "GLB" if embed else "GLTF_SEPARATE"
            tmp_main = workdir / (f"{path.stem}.glb" if embed else f"{path.stem}.gltf")
            col_name = f"xex_export__{path.stem}"
            opts = resolve_export_options(
                prof, filepath=str(tmp_main), collection=col_name, export_format=fmt,
                export_texture_dir="" if embed else "tex", export_copyright=copyright_text or "",
                export_tangents=use_tangents, export_materials=materials, export_vertex_color=vertex_color,
                export_vertex_color_name=vertex_color_name,
                export_active_vertex_color_when_no_material=bool(vertex_color_when_no_material),
                export_extras=bool(extras))
            props = exporter_rna()
            problems = check_options(opts, props, DEFAULTED_ON_PURPOSE)
            if problems:
                raise RuntimeError("exporter options do not match the installed add-on: " + "; ".join(problems))
            receipt["exporter_options"] = {k: v for k, v in sorted(opts.items()) if k != "filepath"}
            receipt["exporter_options_defaulted_on_purpose"] = {
                k: {"reason": v, "default": getattr(props[k], "default", None)}
                for k, v in DEFAULTED_ON_PURPOSE.items() if k in props}
            receipt["exporter_rna_sha256"] = rna_signature(props)
            t_exp = time.time()
            alpha_links = []
            with _export_collection(objects, col_name) as col, _culling_policy(decisions), \
                    _vertex_alpha_policy(mats, prof, alpha_links), _capture_exporter_log() as log_records:
                opts["collection"] = col.name
                result = bpy.ops.export_scene.gltf(**opts)
            receipt["exporter_messages"] = log_records
            receipt["policy"]["vertex_alpha_links_detached"] = alpha_links
            low_alpha = [m["object"] for m in src["meshes"] if m.get("color_alpha_min", 1.0) < 0.999]
            if alpha_links and low_alpha:
                receipt["warnings"].append(f"vertex alpha < 1 on {low_alpha} is not exported under the RGB COLOR_0 "
                                           "policy; use a profile with color0='RGBA' if the alpha is needed")
            receipt["export_seconds"] = round(time.time() - t_exp, 2)
            if result != {"FINISHED"} or not tmp_main.is_file():
                raise RuntimeError(f"glTF export failed: {result}")
            if embed:
                gltf, binary = read_glb(tmp_main)
                image_records = _embedded_image_facts(gltf, binary)
            else:
                gltf = json.loads(tmp_main.read_text(encoding="utf-8"))
                bufs = gltf.get("buffers", [])
                if len(bufs) != 1 or "uri" not in bufs[0]:
                    raise RuntimeError(f"expected one external buffer in the separate export, got {bufs}")
                binary = (workdir / unquote(bufs[0]["uri"])).read_bytes()
                gltf["buffers"] = [{"byteLength": len(binary)}]
                image_records = _externalise_images(gltf, workdir, path, texture_dir, texture_uri_prefix)
            if gltf.get("scenes"):
                gltf["scenes"][gltf.get("scene", 0)]["name"] = asset_id or path.stem
            # Lets gltf-postprocess.mjs pick the policy and budget class without a side channel.
            gltf.setdefault("asset", {}).setdefault("extras", {}).update({
                "xex_export_helper": HELPER_VERSION, "xex_profile": prof.name,
                "xex_budget_class": budget_class or prof.budget_class, "xex_color0": prof.color0,
                "xex_double_sided": prof.double_sided})
            conversions = []
            if prof.color0 == "RGB":
                binary, conversions = color0_to_rgb(gltf, binary)
            receipt["color0_conversions"] = conversions
            for c in conversions:
                if c["alpha_min"] is not None and c["alpha_min"] < 0.999:
                    receipt["warnings"].append(f"COLOR_0 of {c['mesh']}: alpha {c['alpha_min']}..{c['alpha_max']} "
                                               "dropped by the RGB policy")
            glb_bytes = pack_glb(gltf, binary)
            write_bytes_atomic(path, glb_bytes)
        finally:
            for f in sorted(workdir.rglob("*"), reverse=True):
                f.unlink() if f.is_file() else f.rmdir()
            workdir.rmdir()
        gltf2, binary2 = read_glb(path)
        facts = glb_facts(gltf2, binary2, path.parent)
        receipt["glb"] = facts
        receipt["images"] = image_records
        receipt["outputs"].append({"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path),
                                   "kind": "glb"})
        for rec in image_records:
            if rec["file"] and rec["dedup"] == "new":
                receipt["outputs"].append({"path": rec["file"], "bytes": rec["bytes"], "sha256": rec["sha256"],
                                           "kind": "texture"})
        receipt["sizes"] = {"glb_bytes": path.stat().st_size, "binary_chunk_bytes": len(binary2),
                            "referenced_texture_bytes": sum(r["bytes"] for r in image_records),
                            "unique_texture_files": len({r["sha256"] for r in image_records})}
        reimp = None
        if reimport:
            reimp = reimport_facts(path, {m["name"] for m in facts["materials"]}, mode=reimport)
            receipt["reimport"] = reimp
        checks, failures, warns = validate_export(prof, src, facts, reimp, decided_all, use_tangents, embed,
                                                  image_records)
        receipt["validation"] = checks
        receipt["warnings"] += warns
        code_failures = failures
        receipt["failures"] = failures
        receipt["status"] = "PASS" if not failures else "FAIL"
        receipt["postprocess_command"] = (
            f"node apps/client/scripts/gltf-postprocess.mjs {rel(path)} --class {receipt['budget_class']} "
            f"--out <runtime>.glb --texture-out <runtime textures dir>")
    except ExportValidationError as exc:
        receipt["status"] = "FAIL"
        receipt["failures"] = receipt.get("failures") or [str(exc)]
        code_failures = receipt["failures"]
    except Exception:
        receipt["status"] = "ERROR"
        receipt["traceback"] = traceback.format_exc()
        receipt["seconds"] = round(time.time() - t0, 2)
        write_json_atomic(receipt_path, receipt)
        raise
    receipt["seconds"] = round(time.time() - t0, 2)
    write_json_atomic(receipt_path, receipt)
    print(f"EXPORT {receipt['status']} {rel(path)} profile={prof.name} tris={receipt.get('glb', {}).get('triangles')} "
          f"bytes={receipt.get('sizes', {}).get('glb_bytes')} receipt={rel(receipt_path)}", flush=True)
    if code_failures and fail_on_validation:
        raise ExportValidationError(f"{path.name}: " + "; ".join(code_failures), receipt)
    return receipt


# ---------------------------------------------------------------------------------------------- CLI
def _import_glb_clean(src: Path) -> list:
    """Fresh factory scene, import a GLB, return its objects (used by `reexport`)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(**dict(IMPORT_OPTIONS, filepath=str(src)))
    return sorted((o for o in bpy.data.objects if o not in before), key=lambda o: o.name)


def _cli_reexport(job: dict) -> dict:
    """Re-export an existing GLB through the helper (migration and proof tool)."""
    src = Path(job["src"]).resolve()
    gltf, _ = read_glb(src)
    objects = _import_glb_clean(src)
    return export_glb(
        objects, job["out"], job["profile"], receipt_path=job.get("receipt"), texture_dir=job.get("texture_dir"),
        texture_uri_prefix=job.get("texture_uri_prefix"), embed_images=job.get("embed_images"),
        asset_id=job.get("asset_id"), budget_class=job.get("budget_class"),
        double_sided_materials=job.get("double_sided_materials", ()),
        single_sided_materials=job.get("single_sided_materials", ()),
        copyright_text=job.get("copyright", gltf.get("asset", {}).get("copyright", "")),
        reimport=job.get("reimport", "scratch"), fail_on_validation=False, inputs=[src],
        notes=job.get("notes", f"re-exported from {rel(src)} (imported into a factory-empty scene)"))


def main(argv=None) -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if argv is None and "--" in sys.argv else (argv or [])
    ap = argparse.ArgumentParser(prog="export_helper.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_int = sub.add_parser("introspect", help="dump the installed exporter/importer RNA and the classification")
    p_int.add_argument("--out", required=True, type=Path)
    p_re = sub.add_parser("reexport", help="import GLB(s) and re-export them through export_glb")
    p_re.add_argument("--jobs", type=Path, help="JSON list of {src, out, profile, receipt, texture_dir, ...}")
    p_re.add_argument("--src", type=Path)
    p_re.add_argument("--out", type=Path)
    p_re.add_argument("--profile", choices=sorted(PROFILES))
    p_re.add_argument("--receipt", type=Path)
    p_re.add_argument("--texture-dir", type=Path)
    p_re.add_argument("--budget-class")
    p_re.add_argument("--cycles-device", default=None)  # accepted and ignored (driver convenience)
    args = ap.parse_args(argv)
    if args.cmd == "introspect":
        rep = classification_report()
        rep["exporter_rna"] = describe_rna(exporter_rna())
        rep["importer_rna"] = describe_rna(importer_rna())
        rep["resolved_by_profile"] = {name: resolve_export_options(name) for name in PROFILES}
        rep["profiles"] = {name: {k: v for k, v in vars(p).items() if k != "gltf"} for name, p in PROFILES.items()}
        rep["import_options"] = IMPORT_OPTIONS
        rep["blender"] = bpy.app.version_string
        rep["gltf_addon"] = addon_version()
        write_json_atomic(args.out, rep)
        bad = [p for v in rep["problems_by_profile"].values() for p in v] + rep["import_problems"]
        print(f"INTROSPECT exporter={rep['exporter_options']} importer={rep['importer_options']} problems={len(bad)}",
              flush=True)
        return EXIT_OK if not bad else EXIT_VALIDATION
    if args.jobs:
        jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    elif args.src and args.out and args.profile:
        jobs = [{"src": str(args.src), "out": str(args.out), "profile": args.profile,
                 "receipt": str(args.receipt) if args.receipt else None,
                 "texture_dir": str(args.texture_dir) if args.texture_dir else None,
                 "budget_class": args.budget_class}]
    else:
        ap.error("reexport needs --jobs or --src/--out/--profile")
        return EXIT_ARGS
    statuses = []
    for job in jobs:
        r = _cli_reexport(job)
        statuses.append(r["status"])
    print("REEXPORT", json.dumps(statuses), flush=True)
    return EXIT_OK if all(s == "PASS" for s in statuses) else EXIT_VALIDATION


if __name__ == "__main__":
    sys.exit(main())
