"""Verify the world expansion blueprint without changing runtime content."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = ROOT / "planning" / "world-expansion" / "world-layout-v1.json"
CITY_PATH = ROOT / "assets" / "blender" / "city_r5" / "layout.json"
ZONES_PATH = ROOT / "content" / "source" / "zones.json"


def close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > 1e-6:
        raise ValueError(f"{label}: expected {expected}, got {actual}")


def main() -> None:
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    city = json.loads(CITY_PATH.read_text(encoding="utf-8"))
    zones = json.loads(ZONES_PATH.read_text(encoding="utf-8"))["zones"]

    world = layout["target_world"]
    bounds = world["bounds_xz"]
    width = bounds["max_x"] - bounds["min_x"]
    depth = bounds["max_z"] - bounds["min_z"]
    cell_size = world["art_stream_cell_m"]
    if width != depth or width % cell_size:
        raise ValueError("Target world bounds must be a square divisible by art cell size.")
    expected_count = int(width / cell_size)
    if world["art_grid"] != {"columns": expected_count, "rows": expected_count}:
        raise ValueError("Art grid dimensions do not match world bounds and cell size.")

    aoi_size = world["server_aoi_cell_m"]
    if cell_size % aoi_size:
        raise ValueError("AOI cells must divide art cells exactly, without sharing identity.")
    expected_aoi_count = int(width / aoi_size)
    if world["server_aoi_grid"] != {"columns": expected_aoi_count, "rows": expected_aoi_count}:
        raise ValueError("AOI grid dimensions do not match target bounds and cell size.")
    if world["art_stream_cell_m"] == world["server_aoi_cell_m"]:
        raise ValueError("Art streaming and server AOI grids must remain separate.")

    regions = {region["id"] for region in layout["regions"]}
    rows = layout["region_grid_south_to_north"]
    if len(rows) != expected_count:
        raise ValueError(f"Expected {expected_count} art rows, got {len(rows)}.")
    for row_index, row in enumerate(rows):
        if len(row) != expected_count:
            raise ValueError(f"Art row {row_index} has {len(row)} cells, expected {expected_count}.")
        unknown = set(row) - regions
        if unknown:
            raise ValueError(f"Art row {row_index} references unknown regions: {sorted(unknown)}")

    runtime_half_extent = layout["current_runtime"]["half_extent_m"]
    source_half_extent = zones[0]["half_extent"]
    close(runtime_half_extent, source_half_extent, "Current server boundary")
    anchor = layout["r5_city_anchor"]
    origin_x, origin_z = anchor["world_origin_xz"]
    local_gate_x, local_gate_y = anchor["local_gate_xy"]
    local_plaza_x, local_plaza_y = anchor["local_plaza_xy"]
    close(-local_gate_x + origin_x, anchor["world_gate_xz"][0], "R5 gate X")
    close(origin_z + local_gate_y, anchor["world_gate_xz"][1], "R5 gate Z")
    close(-local_plaza_x + origin_x, anchor["world_plaza_xz"][0], "R5 plaza X")
    close(origin_z + local_plaza_y, anchor["world_plaza_xz"][1], "R5 plaza Z")

    island = city["island"]
    transformed = {
        "min_x": -island["x_max"],
        "max_x": -island["x_min"],
        "min_z": origin_z + island["y_min"],
        "max_z": origin_z + island["y_max"],
    }
    expected_island = anchor["world_island_bounds_xz"]
    for key, value in transformed.items():
        close(value, expected_island[key], f"R5 island {key}")
        if value < bounds["min_x"] or value > bounds["max_x"]:
            raise ValueError(f"R5 island falls outside target world bounds: {key}={value}")

    cell_min = bounds["min_x"]
    col_min = int((transformed["min_x"] - cell_min) // cell_size)
    col_max = int((transformed["max_x"] - cell_min - 1e-6) // cell_size)
    row_min = int((transformed["min_z"] - bounds["min_z"]) // cell_size)
    row_max = int((transformed["max_z"] - bounds["min_z"] - 1e-6) // cell_size)
    if [col_min, col_max] != anchor["art_cells_columns"]:
        raise ValueError("R5 island column coverage no longer matches the declared layout.")
    if [row_min, row_max] != anchor["art_cells_rows"]:
        raise ValueError("R5 island row coverage no longer matches the declared layout.")
    if any(rows[row][col] != "aetherhold" for row in range(row_min, row_max + 1) for col in range(col_min, col_max + 1)):
        raise ValueError("R5 island overlaps an art cell not assigned to Aetherhold.")

    for route in layout["routes"]:
        if len(route["world_xz"]) < 2:
            raise ValueError(f"Route {route['id']} needs at least two points.")
        for x, z in route["world_xz"]:
            if not (bounds["min_x"] <= x <= bounds["max_x"] and bounds["min_z"] <= z <= bounds["max_z"]):
                raise ValueError(f"Route {route['id']} point {(x, z)} is outside the target world.")

    extension = layout["runtime_extension"]
    zone = next((item for item in zones if item["id"] == extension["zone_id"]), None)
    if zone is None:
        raise ValueError("Runtime cell contract references a missing source zone.")
    source_cells = {cell["id"]: cell for cell in zone.get("terrain_cells", [])}
    planned_cells = {cell["id"]: cell for cell in extension["cells"]}
    if set(source_cells) != set(planned_cells):
        raise ValueError("World-layout runtime cells do not match content/source/zones.json.")
    for cell_id, source_cell in source_cells.items():
        planned_cell = planned_cells[cell_id]
        source_bounds = source_cell["bounds_xz"]
        planned_bounds = planned_cell["bounds_xz"]
        source_by_name = dict(zip(("min_x", "max_x", "min_z", "max_z"), source_bounds, strict=True))
        if source_by_name != planned_bounds or source_cell["asset"] != planned_cell["asset"]:
            raise ValueError(f"Runtime cell {cell_id} bounds/asset differ from the blueprint.")
        if source_cell["surface_y"] != extension["surface_y"] or not source_cell["walkable"]:
            raise ValueError(f"Runtime cell {cell_id} is not a walkable seam at the declared height.")
        if (planned_bounds["max_x"] - planned_bounds["min_x"] != 64
                or planned_bounds["max_z"] - planned_bounds["min_z"] != 64):
            raise ValueError(f"Runtime cell {cell_id} is not one 64 m art cell.")
    if source_cells["sunmeadow_c7_r6"]["neighbors"]["east"] != "sunmeadow_c8_r6":
        raise ValueError("West/east Sunmeadow cell seam is not connected.")
    if source_cells["sunmeadow_c8_r6"]["neighbors"]["west"] != "sunmeadow_c7_r6":
        raise ValueError("East/west Sunmeadow cell seam is not reciprocal.")
    if (extension["connector_bounds_xz"]["max_z"] != extension["cells"][0]["bounds_xz"]["max_z"] + 22
            or extension["connector_bounds_xz"]["min_z"] != extension["cells"][0]["bounds_xz"]["max_z"]):
        raise ValueError("Starter-field connector does not exactly bridge the 22 m ground gap.")

    props = {prop["id"]: prop for prop in zone.get("world_props", [])}
    if set(props) != set(extension["world_prop_ids"]):
        raise ValueError("World prop placement/collider list differs from the runtime layout.")
    for prop in props.values():
        cell = source_cells[prop["cell"]]
        min_x, max_x, min_z, max_z = cell["bounds_xz"]
        if not (min_x <= prop["x"] <= max_x and min_z <= prop["z"] <= max_z):
            raise ValueError(f"World prop {prop['id']} lies outside its Blender cell.")
    world_route = next((route for route in zone.get("world_routes", []) if route["id"] == "southbound_trail"), None)
    planned_route = next((route for route in layout["routes"] if route["id"] == "southbound_trail"), None)
    if not world_route or not planned_route or world_route["points"] != planned_route["world_xz"]:
        raise ValueError("Southbound map route is not shared by the world blueprint and runtime content.")

    manifest_path = ROOT / "assets" / "models" / "world-v1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["source"]["zone_source_sha256"] != hashlib.sha256(ZONES_PATH.read_bytes()).hexdigest():
        raise ValueError("Built cell assets are stale relative to content/source/zones.json.")
    texture_manifest_path = ROOT / manifest["texture_manifest"]
    texture_manifest = json.loads(texture_manifest_path.read_text(encoding="utf-8"))
    for texture in texture_manifest["textures"]:
        texture_path = ROOT / texture["runtime"]
        if not texture_path.is_file() or hashlib.sha256(texture_path.read_bytes()).hexdigest() != texture["runtime_sha256"]:
            raise ValueError(f"Shared world texture is missing or changed: {texture['runtime']}")
    built_cells = {cell["id"]: cell for cell in manifest["cells"]}
    for cell_id, source_cell in source_cells.items():
        built = built_cells.get(cell_id)
        if not built or built["asset"] != source_cell["asset"] or built["bounds_xz"] != source_cell["bounds_xz"]:
            raise ValueError(f"Built GLB manifest does not match cell {cell_id} source coordinates.")
        expected_props = sorted(prop["id"] for prop in props.values() if prop["cell"] == cell_id)
        if sorted(built["world_prop_ids"]) != expected_props:
            raise ValueError(f"Built cell {cell_id} props differ from runtime content.")
        asset_path = ROOT / built["path"]
        if not asset_path.is_file() or asset_path.stat().st_size != built["bytes"]:
            raise ValueError(f"Built GLB for {cell_id} is missing or has changed size.")
        digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if digest != built["sha256"]:
            raise ValueError(f"Built GLB for {cell_id} does not match its source hash.")

    print(
        "World layout PASS: 1024x1024 m target plus two built 64 m flat cells, "
        f"{expected_count}x{expected_count} art cells, "
        f"{expected_aoi_count}x{expected_aoi_count} AOI cells, "
        "R5 gate/plaza/island transform preserved, with cell and texture hashes verified. Runtime bounds unchanged."
    )


if __name__ == "__main__":
    main()
