"""Read-only, offline checks for the two audited local asset experiments.

No upstream module, model or dependency package is imported by this tool. It
reads installed distribution metadata and pinned review files, and optionally
queries nvidia-smi. JSON is written to stdout only; use shell redirection to save
a receipt. This is a readiness check, not an installer or inference launcher.
"""

from __future__ import annotations

import argparse
import base64
import csv
import ctypes
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys

IMAGE_COMMIT = "5ed8e9850d23515c424abc62fbca498e6da52f27"
UNIMATE_COMMIT = "2c5b384715aa63d8639b1ed7eb74bfe614570c7a"
MODEL_COMMIT = "92710b30abc0a7708c9f280f38fd7e65448c4f95"
PHOTO_PAINT_SHA256 = "a64f11ee0616f3d0457574037979d0d9faf0970814e86c9a69f9ca70c88bc562"
WARRIOR_SHA256 = "2bab905ce12d279e1d099c2a8de0b1ef31c9f5e8d1959b41d24470b4f4181add"
WARRIOR_RUNTIME_SHA256 = "63e53eb4f042996cf0331534ec9980eac5da2c305b20a083546596a9a2958080"
WARRIOR_LICENSE_SHA256 = "83d8959f9fc56353ed571fbe2dc52e4bcd64508e2399501cd45ac2ce3df0bf8c"
MAX_FILE_BYTES = 32 * 1024 * 1024
RECEIPTS = {
    "image-to-3dlab": {
        "SOURCE_MANIFEST.json": "0069ad01767bb6214268ce6fa6b90612506ab9c18ec3c3caefd9e74ed1ec5b06",
        "EXTRA_SOURCE_MANIFEST.json": "68a3f14bbd6f55d1ebbf79a1d555c43534062408bcccbd5f0da016fbaaacedf8",
        "BAKE_SOURCE_MANIFEST.json": "691335492964b60d8073d3a2c7d0166ab62b51da982f30e67b96ee8e1d0e8b6c",
    },
    "UniMate": {
        "source-receipt.json": "97a2537fbcb8876f5e02c3e11d4c3146226a86f17c7e7adf8370f278b74d3a62",
        "additional-source-receipt.json": "ecfd95eabaf3ea0ab80d24b044d9fc678a2b79fd640cbc318a8b6041d9d56b77",
    },
}


def read_bounded(path: Path) -> bytes:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file exceeds the 32 MiB inspection bound")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file exceeds the 32 MiB inspection bound")
    return data


def verified_bytes(path: Path, expected_sha256: str) -> bytes:
    data = read_bounded(path)
    if hashlib.sha256(data).hexdigest() != expected_sha256.lower():
        raise ValueError("source SHA-256 mismatch")
    return data


def verify_source(root: Path, name: str) -> dict:
    """Check anchored receipts, then every recorded local file. Never execute it."""
    directory = root / ".harness/.cache/ai-tool-review" / name
    failures, unavailable, files = [], [], {}
    for receipt, expected in RECEIPTS[name].items():
        try:
            record = json.loads(verified_bytes(directory / receipt, expected))
            rows = record if isinstance(record, list) else record.get("files", [record])
            if len(rows) > 128:
                raise ValueError("too many receipt entries")
            for row in rows:
                if "sha256" not in row and "error" in row:
                    unavailable.append({"path": row["path"], "status": "not_in_review_snapshot"})
                    continue
                relative = Path(row["path"])
                target = (directory / relative).resolve()
                if relative.is_absolute() or not target.is_relative_to(directory.resolve()):
                    raise ValueError("receipt path escapes reviewed source directory")
                try:
                    data = verified_bytes(target, row["sha256"])
                    files[row["path"]] = {"sha256": row["sha256"].lower(), "bytes": len(data)}
                except (OSError, ValueError) as error:
                    failures.append({"path": row["path"], "reason": str(error)})
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append({"path": receipt, "reason": str(error)})
    return {
        "commit": IMAGE_COMMIT if name == "image-to-3dlab" else UNIMATE_COMMIT,
        "status": "verified_review_snapshot" if not failures else "rejected",
        "snapshot_is_complete_installation": False,
        "checked_files": len(files), "files": files, "failures": failures,
        "unavailable_review_entries": unavailable,
    }


def dependency_metadata() -> dict:
    result = {}
    for name in ("numpy", "Pillow", "torch", "scipy", "transformers", "tyro", "loguru", "torchdiffeq"):
        try:
            result[name] = {"installed": True, "version": importlib.metadata.version(name)}
        except importlib.metadata.PackageNotFoundError:
            result[name] = {"installed": False, "version": None}
    return result


def parse_gpu_query(output: str) -> list[dict]:
    rows = list(csv.reader(io.StringIO(output)))
    if len(rows) > 16:
        raise ValueError("GPU query returned too many devices")
    devices = []
    for row in rows:
        if not row:
            continue
        if len(row) != 3:
            raise ValueError("invalid GPU query row")
        name, memory, driver = (value.strip() for value in row)
        devices.append({"name": name[:128], "vram_mib": int(memory), "driver": driver[:32]})
    return devices


def observed_hardware(query_gpu: bool = True) -> dict:
    result = {"gpus": [], "gpu_query": "not_requested", "ram_gib": None}
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in (
                    "total_phys", "avail_phys", "total_page", "avail_page",
                    "total_virtual", "avail_virtual", "avail_extended")]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            result["ram_gib"] = round(status.total_phys / 2**30, 2)
    executable = shutil.which("nvidia-smi") if query_gpu else None
    if executable:
        try:
            completed = subprocess.run(
                [executable, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            if len(completed.stdout) > 8192:
                raise ValueError("GPU query output exceeds inspection bound")
            result["gpus"] = parse_gpu_query(completed.stdout)
            result["gpu_query"] = "observed"
        except (OSError, ValueError, subprocess.SubprocessError):
            result["gpu_query"] = "unavailable"
    elif query_gpu:
        result["gpu_query"] = "unavailable"
    return result


def hardware_eligibility(hardware: dict) -> dict:
    decisions = []
    for gpu in hardware.get("gpus", []):
        try:
            version = tuple(int(part) for part in gpu["driver"].split("."))
            driver_supported = version >= (575,)
        except (KeyError, ValueError):
            driver_supported = False
        low_vram = gpu.get("vram_mib", 0) <= 2048
        decisions.append({
            "gpu": gpu.get("name"), "pixal3d_windows_driver_supported": driver_supported,
            "pixal3d_status": "blocked" if not driver_supported or low_vram else "unverified_vram_and_backend",
            "reasons": (["driver below audited Windows prebuilt minimum 575"] if not driver_supported else [])
            + (["2 GiB-class VRAM is not validated for generation; no inference allowed by this preflight"] if low_vram else []),
        })
    return {
        "pixel_match_cpu": "hardware_eligible_dependency_checks_separate",
        "pixal3d": decisions or [{"pixal3d_status": "unverified_no_gpu_observation"}],
        "unimate_cpu": "candidate_only_speed_and_peak_ram_unverified",
        "unimate_cpu_requirements": {"sampling.device": "cpu", "CUDA_VISIBLE_DEVICES": "", "batch_size": 1},
        "generation_authorized_by_preflight": False,
    }


def decode_accessor(doc: dict, buffers: list[bytes], index: int) -> list[tuple]:
    accessor = doc["accessors"][index]
    view = doc["bufferViews"][accessor["bufferView"]]
    if "sparse" in accessor or "EXT_meshopt_compression" in view.get("extensions", {}):
        raise ValueError("sparse/compressed accessor requires a separate reviewed decoder")
    component = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[accessor["componentType"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    layout = struct.Struct("<" + component * width)
    count = accessor["count"]
    if not isinstance(count, int) or not 0 <= count <= 200000:
        raise ValueError("accessor count exceeds inspection bound")
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", layout.size)
    end = offset + (count - 1) * stride + layout.size if count else offset
    data = buffers[view["buffer"]]
    if offset < 0 or stride < layout.size or end > len(data) or end > view.get("byteOffset", 0) + view["byteLength"]:
        raise ValueError("accessor outside buffer view")
    values = [layout.unpack_from(data, offset + i * stride) for i in range(count)]
    if component == "f" and not all(math.isfinite(v) for row in values for v in row):
        raise ValueError("nonfinite accessor data")
    return values


def primitive_metadata(doc: dict) -> list[dict]:
    """Counts/hierarchy only; safe for both native and compressed runtime data."""
    parents = {child: index for index, node in enumerate(doc.get("nodes", [])) for child in node.get("children", [])}
    result = []
    for mesh_index, mesh in enumerate(doc["meshes"]):
        instances = [
            {"node": i, "name": node.get("name"), "skin": node.get("skin"),
             "parent_name": doc["nodes"][parents[i]].get("name") if i in parents else None}
            for i, node in enumerate(doc.get("nodes", [])) if node.get("mesh") == mesh_index
        ]
        for primitive_index, primitive in enumerate(mesh["primitives"]):
            attributes = primitive["attributes"]
            indices = doc["accessors"][primitive["indices"]]["count"] if "indices" in primitive else None
            mode = primitive.get("mode", 4)
            material = primitive.get("material")
            result.append({
                "mesh": mesh_index, "mesh_name": mesh.get("name"), "primitive": primitive_index,
                "vertices": doc["accessors"][attributes["POSITION"]]["count"],
                "indices": indices, "triangles": indices // 3 if mode == 4 and indices is not None else None,
                "mode": mode, "material": material,
                "material_name": doc.get("materials", [])[material].get("name") if material is not None else None,
                "attributes": sorted(attributes), "has_skin_weights": "JOINTS_0" in attributes and "WEIGHTS_0" in attributes,
                "instances": instances,
            })
    return result


def inspect_warrior(root: Path) -> dict:
    """Inspect native source data; runtime GLB metadata needs no Meshopt decoding."""
    directory = root / "assets/characters/quaternius-rpg"
    source = verified_bytes(directory / "Warrior.gltf", WARRIOR_SHA256)
    doc = json.loads(source)
    license_bytes = verified_bytes(directory / "License.txt", WARRIOR_LICENSE_SHA256)
    if b"CC0 1.0 Universal" not in license_bytes:
        raise ValueError("unexpected configured character license")
    buffers = []
    for buffer in doc["buffers"]:
        uri = buffer["uri"]
        if not uri.startswith("data:application/octet-stream;base64,"):
            raise ValueError("only embedded source buffers allowed; external files are not followed")
        data = base64.b64decode(uri.split(",", 1)[1], validate=True)
        if len(data) != buffer["byteLength"]:
            raise ValueError("buffer length mismatch")
        buffers.append(data)
    nodes = doc["nodes"]
    parents = {child: index for index, node in enumerate(nodes) for child in node.get("children", [])}
    joints = set(j for skin in doc["skins"] for j in skin["joints"])
    roots = sorted(j for j in joints if parents.get(j) not in joints)
    animations = []
    for animation in doc.get("animations", []):
        times = [[v[0] for v in decode_accessor(doc, buffers, s["input"])] for s in animation["samplers"]]
        if any(not t or any(b <= a for a, b in zip(t, t[1:])) for t in times):
            raise ValueError("animation timestamps must be nonempty and strictly increasing")
        deltas = [b - a for t in times for a, b in zip(t, t[1:])]
        rate = round(1 / (sum(deltas) / len(deltas)), 4) if deltas else None
        root_channels = []
        for channel in animation["channels"]:
            target = channel["target"]
            sampler = animation["samplers"][channel["sampler"]]
            values = decode_accessor(doc, buffers, sampler["output"])
            width = {"translation": 3, "rotation": 4, "scale": 3}.get(target["path"])
            if target["node"] not in joints or width is None or sampler.get("interpolation", "LINEAR") != "LINEAR":
                raise ValueError("unsupported animation channel")
            if len(values) != len(times[channel["sampler"]]) or any(len(v) != width for v in values):
                raise ValueError("animation output shape mismatch")
            if target["node"] not in roots:
                continue
            entry = {"node": target["node"], "name": nodes[target["node"]].get("name"), "path": target["path"], "interpolation": sampler.get("interpolation", "LINEAR")}
            if target["path"] == "translation":
                entry.update({"first": values[0], "last": values[-1], "end_minus_start": [round(b - a, 8) for a, b in zip(values[0], values[-1])], "axis_range": [round(max(v[i] for v in values) - min(v[i] for v in values), 8) for i in range(3)]})
            root_channels.append(entry)
        animations.append({
            "name": animation.get("name"), "duration_seconds": round(max(max(t) for t in times) - min(min(t) for t in times), 8),
            "channels": len(animation["channels"]), "source_sample_rate_hz": rate,
            "finite_values_and_channel_shapes_valid": True,
            "resample_to_30_fps_required": rate != 30.0,
            "root_channels": root_channels,
        })
    runtime = verified_bytes(root / "apps/client/src/assets/characters/quaternius-warrior.meshopt-etc1s.glb", WARRIOR_RUNTIME_SHA256)
    magic, version, length, json_length, chunk_type = struct.unpack_from("<IIIII", runtime)
    if (magic, version, length, chunk_type) != (0x46546C67, 2, len(runtime), 0x4E4F534A):
        raise ValueError("unexpected runtime GLB header")
    runtime_doc = json.loads(runtime[20:20 + json_length])
    runtime_names = [a.get("name") for a in runtime_doc.get("animations", [])]
    runtime_joint_count = len(set(j for s in runtime_doc.get("skins", []) for j in s["joints"]))
    runtime_primitive_count = sum(len(m["primitives"]) for m in runtime_doc["meshes"])
    selected = next((a for a in animations if a["name"] == "Idle_Weapon"), None)
    return {
        "schema": "xexoria.warrior-motion-readiness/1", "source_license": "CC0-1.0",
        "source": {"path": "assets/characters/quaternius-rpg/Warrior.gltf", "sha256": WARRIOR_SHA256, "bytes": len(source)},
        "runtime": {"path": "apps/client/src/assets/characters/quaternius-warrior.meshopt-etc1s.glb", "sha256": WARRIOR_RUNTIME_SHA256, "bytes": len(runtime), "primitive_count": runtime_primitive_count, "primitives": primitive_metadata(runtime_doc), "skin_joint_count": runtime_joint_count, "animation_names": runtime_names, "compressed_accessor_values_inspected": False},
        "source_primitive_count": sum(len(m["primitives"]) for m in doc["meshes"]),
        "source_primitives": primitive_metadata(doc),
        "skin_joint_count": len(joints), "skin_joint_names": [nodes[j].get("name") for j in sorted(joints)],
        "root_joints": [{"node": j, "name": nodes[j].get("name"), "parent_name": nodes[parents[j]].get("name") if j in parents else None} for j in roots],
        "animations": animations,
        "selected_clip": selected["name"] if selected else None,
        "generic_v2": {"model_card_joint_range": [5, 70], "checkpoint_padding_width": 71, "within_joint_range": 5 <= len(joints) <= 70, "valid_existing_clip_present": selected is not None, "input_status": "structural_candidate_requires_30fps_preprocessing_and_conditioning", "inference_ready": False},
        "runtime_and_source_clip_names_match": runtime_names == [a["name"] for a in animations],
        "limits": ["Root channel ranges are local joint data, not a world-space contact or locomotion assessment.", "No rig alteration, preprocessing, weights, inference, export or gameplay admission was performed.", "UniMate's official new-rig inference workflow remains unverified for this character."],
    }


def collect(root: Path, query_gpu: bool = True) -> dict:
    sources = {name: verify_source(root, name) for name in RECEIPTS}
    dependencies = dependency_metadata()
    hardware = observed_hardware(query_gpu)
    try:
        character = inspect_warrior(root)
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        character = {"status": "rejected", "reason": str(error)}
    return {
        "schema": "xexoria.local-ai-asset-preflight/1",
        "read_only": True, "network_used": False, "upstream_code_executed": False,
        "sources": sources, "dependencies": dependencies,
        "blender": {"on_path": shutil.which("blender") is not None, "bridge_compatibility_verified": False},
        "configured_licenses": {"pixel_match_code": "Apache-2.0", "unimate_code": "MIT", "unimate_generic_v2_weights": "MIT", "warrior_source": "CC0-1.0", "pixal3d_backend_and_encoders": "separate_route_review_required"},
        "license_scope": "Declared licenses for these exact reviewed routes; backend/encoder and dataset licenses are independent. Source integrity is reported separately.",
        "hardware": hardware, "eligibility": hardware_eligibility(hardware),
        "pixel_match_dependencies_available": all(dependencies[n]["installed"] for n in ("numpy", "Pillow")),
        "unimate_dependencies_report_is_exhaustive": False,
        "unimate_missing_inspected_dependencies": [n for n in ("torch", "scipy", "transformers", "tyro", "loguru", "torchdiffeq") if not dependencies[n]["installed"]],
        "full_image_to_3dlab_environment_validated": False,
        "note": "The fixture can use installed NumPy 2.x; the full upstream environment requests numpy<2 and is not installed or validated here.",
        "model_weights": {"downloaded_by_tool": False, "generic_v2_checkpoint_bytes": 1185827848, "flan_t5_base_bytes": 990345061, "total_weight_gib": round((1185827848 + 990345061) / 2**30, 3), "model_revision": MODEL_COMMIT, "weights_present_or_authenticity_verified": False},
        "warrior": character,
        "game_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-gpu-query", action="store_true", help="skip the bounded read-only nvidia-smi query")
    parser.add_argument("--warrior-only", action="store_true", help="inspect native source animation data and runtime GLB metadata")
    args = parser.parse_args(argv)
    if args.warrior_only:
        try:
            report = inspect_warrior(args.root.resolve())
        except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
            print(json.dumps({"status": "rejected", "reason": str(error)}))
            return 2
    else:
        report = collect(args.root.resolve(), not args.no_gpu_query)
    print(json.dumps(report, indent=2))
    rejected = not args.warrior_only and (any(s["status"] == "rejected" for s in report["sources"].values()) or report["warrior"].get("status") == "rejected")
    return 2 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
