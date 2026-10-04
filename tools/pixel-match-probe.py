"""Reproduce the pinned Pixel Match planar control and known occlusion limit.

Only synthetic arrays are used. No model/image/game asset is read or written;
only the SHA-verified standalone photo_paint.py module is executed. No weights,
CUDA, Blender, downloads, installers or upstream patches are involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import types

SOURCE_COMMIT = "5ed8e9850d23515c424abc62fbca498e6da52f27"
SOURCE_SHA256 = "a64f11ee0616f3d0457574037979d0d9faf0970814e86c9a69f9ca70c88bc562"
MAX_SOURCE_BYTES = 128 * 1024


def load_audited_module(path: Path):
    """Reject changed source before compiling/importing anything from it."""
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("source exceeds the 128 KiB bound")
    with path.open("rb") as stream:
        source = stream.read(MAX_SOURCE_BYTES + 1)
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("source SHA-256 mismatch; only the audited module can execute")
    name = "_xexoria_audited_photo_paint"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    previous = sys.modules.get(name)
    sys.modules[name] = module  # dataclasses needs a registered module during execution
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


def planar_fixture(np, divisions: int):
    if divisions not in (1, 50):
        raise ValueError("fixture supports only 2 or 5,000 triangles")
    uv = np.array([(x / divisions, y / divisions) for y in range(divisions + 1) for x in range(divisions + 1)])
    positions = np.column_stack((2 * uv[:, 0] - 1, 1 - 2 * uv[:, 1], np.full(len(uv), -2.0)))
    faces = []
    for y in range(divisions):
        for x in range(divisions):
            a = y * (divisions + 1) + x
            b, c, d = a + 1, a + divisions + 1, a + divisions + 2
            faces.extend(((a, b, d), (a, d, c)))
    return positions, uv, np.asarray(faces, dtype=np.int64)


def run_probe(source: Path) -> dict:
    module = load_audited_module(source)
    np = module.np
    size = 64
    y, x = np.indices((size, size))
    image = np.stack((x * 4, y * 4, (x + y) * 2, np.full_like(x, 255)), axis=-1).astype(np.uint8)
    texture = np.zeros_like(image)
    texture[:, :, 3] = 255
    view = module.View(image, np.eye(4), 2 * np.arctan(0.5), "synthetic_coordinate_grid")
    settings = module.Settings(match_colour=False, edge_px=1, gutter_px=0)
    runs, outputs = [], []
    for divisions in (1, 50):
        positions, uv, faces = planar_fixture(np, divisions)
        start = time.perf_counter()
        output, weight = module.paint_texture(texture, positions, uv, faces, [view], frame=((0, 1, 2), (1, 1, 1)), settings=settings)
        seconds = time.perf_counter() - start
        trusted = weight >= 0.999999
        error = np.abs(output[:, :, :3].astype(np.int16) - image[:, :, :3].astype(np.int16))
        outputs.append(output)
        runs.append({"triangles": len(faces), "vertices": len(positions), "trusted_texels": int(trusted.sum()), "total_texels": size**2, "mean_rgb_error_trusted": float(error[trusted].mean()) if trusted.any() else None, "max_rgb_error_trusted": int(error[trusted].max()) if trusted.any() else None, "output_sha256": hashlib.sha256(output.tobytes()).hexdigest(), "seconds": seconds})
    # One sample in two overlapping projected triangles. At the sample all
    # barycentric weights are 1/3. Perspective front depth is 1.5 but affine
    # screen-space depth is 5/3; a flat rear triangle at 1.6 wrongly wins.
    xy = np.array([[[0., 0.], [1.5, 0.], [0., 1.5]]] * 2)
    depths = np.array([[1., 2., 2.], [1.6, 1.6, 1.6]])
    winner, bary = module.rasterize(xy, depths, (1, 1))
    sample_bary = np.array([1/3, 1/3, 1/3])
    front_depth = float(1 / np.sum(sample_bary / depths[0]))
    affine_depth = float(np.dot(sample_bary, depths[0]))
    known_limit = int(winner[0, 0]) == 1 and front_depth < 1.6 < affine_depth
    planar_pass = all(r["trusted_texels"] == size**2 and r["max_rgb_error_trusted"] == 0 for r in runs) and np.array_equal(*outputs)
    return {
        "schema": "xexoria.pixel-match-cpu-probe/2", "source_commit": SOURCE_COMMIT, "source_sha256": SOURCE_SHA256,
        "fixture": "Synthetic RGBA coordinate grid; no user artwork or runtime asset modified",
        "execution": {"device": "cpu", "numpy": np.__version__, "source_patched": False, "weights_downloaded": False, "images_or_assets_written": False},
        "projection": {"result": "PASS_CONTROLLED_PLANAR_CASE" if planar_pass else "FAILED_CONTROL", "settings": {"match_colour": False, "edge_px": 1, "gutter_px": 0}, "runs": runs, "two_triangle_and_5000_triangle_outputs_equal": bool(np.array_equal(*outputs))},
        "occlusion": {"result": "KNOWN_LIMIT_REPRODUCED" if known_limit else "EXPECTED_LIMIT_NOT_REPRODUCED", "expected_visible_triangle": 0, "actual_visible_triangle": int(winner[0, 0]), "correct_perspective_depth": front_depth, "back_surface_depth": 1.6, "affine_front_depth": affine_depth, "winner_barycentric": bary[0, 0].tolist()},
        "game_ready": False,
        "limits": ["A controlled planar fixture does not prove universal pixel-perfect projection.", "The known affine-depth occlusion error is intentionally recorded, not patched.", "No 3D inference, retopology, skinning, camera calibration, user image editing or gameplay validation was run."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / ".harness/.cache/ai-tool-review/image-to-3dlab/image_to_3dlab/photo_paint.py")
    args = parser.parse_args(argv)
    try:
        report = run_probe(args.source)
    except (OSError, ValueError, ImportError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["projection"]["result"] == "PASS_CONTROLLED_PLANAR_CASE" and report["occlusion"]["result"] == "KNOWN_LIMIT_REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
