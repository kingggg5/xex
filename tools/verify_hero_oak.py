"""Check actual LOD triangle surfaces against the shared walking footprint."""
import hashlib
import json
import math
import struct
from pathlib import Path

root = Path(__file__).resolve().parents[1]
results = []
for lod in range(3):
    path = root / f"assets/models/hero-oak/v1/hero_oak_lod{lod}.geometry.glb"
    data = path.read_bytes()
    if data[:4] != b"glTF" or struct.unpack_from("<II", data, 4) != (2, len(data)):
        raise ValueError("Invalid GLB header")
    length = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + length])
    base = 28 + length
    if len(doc.get("meshes", [])) != 1 or len(doc["meshes"][0]["primitives"]) != 1:
        raise ValueError("Expected one oak primitive")
    for node in doc.get("nodes", []):
        if (node.get("translation", [0, 0, 0]) != [0, 0, 0]
                or node.get("rotation", [0, 0, 0, 1]) != [0, 0, 0, 1]
                or node.get("scale", [1, 1, 1]) != [1, 1, 1]
                or "matrix" in node):
            raise ValueError("Footprint validator requires the normalized identity transform")

    def read_accessor(index):
        accessor = doc["accessors"][index]
        view = doc["bufferViews"][accessor["bufferView"]]
        code = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[accessor["componentType"]]
        count = {"VEC3": 3, "SCALAR": 1}[accessor["type"]]
        size = struct.calcsize("<" + code * count)
        stride = view.get("byteStride", size)
        offset = base + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        return [struct.unpack_from("<" + code * count, data, offset + i * stride)
                for i in range(accessor["count"])]

    primitive = doc["meshes"][0]["primitives"][0]
    if primitive.get("mode", 4) != 4 or set(primitive["attributes"]) != {"POSITION", "NORMAL", "TEXCOORD_0"}:
        raise ValueError("Unexpected oak primitive contract")
    positions = read_accessor(primitive["attributes"]["POSITION"])
    indices = [v[0] for v in read_accessor(primitive["indices"])]
    if len(indices) % 3 or any(i >= len(positions) for i in indices):
        raise ValueError("Invalid triangle indices")
    if not all(math.isfinite(v) for point in positions for v in point):
        raise ValueError("Nonfinite oak position")
    max_radius, offending = 0.0, 0
    for offset in range(0, len(indices), 3):
        triangle = [positions[indices[offset + i]] for i in range(3)]
        clipped = [point for point in triangle if point[1] <= 1.8]
        for a, b in zip(triangle, triangle[1:] + triangle[:1]):
            if (a[1] <= 1.8) != (b[1] <= 1.8):
                t = (1.8 - a[1]) / (b[1] - a[1])
                clipped.append(tuple(a[i] + t * (b[i] - a[i]) for i in range(3)))
        radius = max((math.hypot(p[0], p[2]) for p in clipped), default=0)
        max_radius = max(max_radius, radius)
        offending += radius > 0.75 + 1e-6
    height = max(p[1] for p in positions) - min(p[1] for p in positions)
    results.append({"lod": lod, "file": path.name,
        "sha256": hashlib.sha256(data).hexdigest(), "triangles": len(indices) // 3,
        "height_m": height, "max_clipped_radius_m": max_radius,
        "offending_triangles": offending, "pass": offending == 0 and abs(height - 8.6) < 0.01})
report = {"status": "PASS" if all(r["pass"] for r in results) else "FAIL",
    "footprint_radius_m": 0.75, "capsule_height_m": 1.8, "lods": results}
output = root / "planning/evidence/hero-oak-footprint-build-20260930.json"
output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report))
raise SystemExit(0 if report["status"] == "PASS" else 1)
