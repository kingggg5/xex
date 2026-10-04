"""Render the authoring-only world layout blueprint as a standalone SVG."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = ROOT / "planning" / "world-expansion" / "world-layout-v1.json"
OUTPUT_PATH = ROOT / "planning" / "world-expansion" / "world-layout-v1.svg"
COLORS = {
    "sunmeadow": "#b6c66c",
    "aetherhold": "#bda77d",
    "whispergrove": "#587d56",
    "glassmere": "#72a792",
    "emberfall": "#b87e58",
    "moonfen": "#628881",
    "skyreach": "#96b9d5",
}
DISPLAY = {
    "sunmeadow": "Sunmeadow Verge",
    "aetherhold": "Aetherhold",
    "whispergrove": "Whispergrove",
    "glassmere": "Glassmere Fields",
    "emberfall": "Emberfall Quarry",
    "moonfen": "Moonfen",
    "skyreach": "Skyreach Highlands",
}


def main() -> None:
    data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    bounds = data["target_world"]["bounds_xz"]
    rows = data["region_grid_south_to_north"]
    cell_size = data["target_world"]["art_stream_cell_m"]
    cell_count = len(rows)
    canvas, margin = 920, 90
    side = canvas - margin * 2
    cell_px = side / cell_count

    def point(x: float, z: float) -> tuple[float, float]:
        sx = margin + (x - bounds["min_x"]) / (bounds["max_x"] - bounds["min_x"]) * side
        sy = margin + (bounds["max_z"] - z) / (bounds["max_z"] - bounds["min_z"]) * side
        return sx, sy

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}" role="img" aria-labelledby="title desc">',
        '<title id="title">World expansion blueprint, 1.024 kilometres square</title>',
        '<desc id="desc">Authoring plan only. Solid route is the existing city route. Dashed routes and new regions are planned and are not yet walkable game content.</desc>',
        '<rect width="920" height="920" fill="#18231f"/>',
    ]
    for row_index, row in enumerate(rows):
        for col_index, region_id in enumerate(row):
            x = margin + col_index * cell_px
            y = margin + (cell_count - 1 - row_index) * cell_px
            svg.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell_px:.2f}" height="{cell_px:.2f}" '
                f'fill="{COLORS[region_id]}" fill-opacity="0.82" stroke="#e8e1cb" stroke-opacity="0.25" stroke-width="1"/>'
            )

    # Macro-sector lines; art cells remain the finer 64 m grid above.
    macro_px = cell_px * (data["target_world"]["macro_sector_m"] / cell_size)
    for index in range(5):
        x = margin + index * macro_px
        y = margin + index * macro_px
        svg.append(f'<line x1="{x:.2f}" y1="{margin}" x2="{x:.2f}" y2="{canvas-margin}" stroke="#26332f" stroke-width="2.5"/>')
        svg.append(f'<line x1="{margin}" y1="{y:.2f}" x2="{canvas-margin}" y2="{y:.2f}" stroke="#26332f" stroke-width="2.5"/>')

    # Current server clamp is shown for context and is deliberately not the target playable boundary.
    current = data["current_runtime"]["half_extent_m"]
    x0, y0 = point(-current, current)
    x1, y1 = point(current, -current)
    svg.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1-x0:.2f}" height="{y1-y0:.2f}" fill="none" stroke="#f0d475" stroke-width="2.2" stroke-dasharray="8 6"/>')

    ground = data["current_runtime"]["ground_rectangle_xz"]
    gx0, gy0 = point(ground["min_x"], ground["max_z"])
    gx1, gy1 = point(ground["max_x"], ground["min_z"])
    svg.append(f'<rect x="{gx0:.2f}" y="{gy0:.2f}" width="{gx1-gx0:.2f}" height="{gy1-gy0:.2f}" fill="#a9d5dc" fill-opacity="0.22" stroke="#d1f4e9" stroke-width="2.5"/>')

    island = data["r5_city_anchor"]["world_island_bounds_xz"]
    ix0, iy0 = point(island["min_x"], island["max_z"])
    ix1, iy1 = point(island["max_x"], island["min_z"])
    svg.append(f'<rect x="{ix0:.2f}" y="{iy0:.2f}" width="{ix1-ix0:.2f}" height="{iy1-iy0:.2f}" rx="18" fill="#735d49" fill-opacity="0.35" stroke="#f7e5ae" stroke-width="3"/>')

    for cell in data.get("runtime_extension", {}).get("cells", []):
        b = cell["bounds_xz"]
        cx0, cy0 = point(b["min_x"], b["max_z"])
        cx1, cy1 = point(b["max_x"], b["min_z"])
        svg.append(f'<rect x="{cx0:.2f}" y="{cy0:.2f}" width="{cx1-cx0:.2f}" height="{cy1-cy0:.2f}" fill="#bfe5dc" fill-opacity="0.20" stroke="#e9f4dd" stroke-width="2"/>')
        center_x, center_y = point((b["min_x"] + b["max_x"]) / 2, (b["min_z"] + b["max_z"]) / 2)
        cell_label = html.escape(cell["id"].replace("sunmeadow_", "").replace("_", "/"))
        svg.append(f'<text x="{center_x:.2f}" y="{center_y:.2f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" fill="#172321" stroke="#ecf3d8" stroke-width="2.8" paint-order="stroke">{cell_label}</text>')

    for route in data["routes"]:
        coords = " ".join(f"{point(x,z)[0]:.2f},{point(x,z)[1]:.2f}" for x, z in route["world_xz"])
        if route["status"] == "current-smoke-tested":
            svg.append(f'<polyline points="{coords}" fill="none" stroke="#fff4c6" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
        elif route["status"] == "runtime-flat-route":
            svg.append(f'<polyline points="{coords}" fill="none" stroke="#a9e5e0" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
        else:
            svg.append(f'<polyline points="{coords}" fill="none" stroke="#604c39" stroke-width="5" stroke-dasharray="12 9" stroke-linecap="round" stroke-linejoin="round"/>')

    # Region labels are positioned from authored extents, not guessed cell indices.
    for region in data["regions"]:
        b = region["design_bounds_xz"]
        label_xz = region.get("label_xz", [(b["min_x"] + b["max_x"]) / 2, (b["min_z"] + b["max_z"]) / 2])
        cx, cy = point(*label_xz)
        label = html.escape(region["display_name"])
        svg.append(f'<text x="{cx:.2f}" y="{cy:.2f}" text-anchor="middle" font-family="Georgia,serif" font-size="17" font-weight="600" fill="#101913" stroke="#e9e2ca" stroke-width="3.5" paint-order="stroke">{label}</text>')
        state = "CITY / PARTIAL" if region["id"] == "aetherhold" else ("STARTER / PARTIAL" if region["id"] == "sunmeadow" else "PLANNED")
        svg.append(f'<text x="{cx:.2f}" y="{cy+20:.2f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" fill="#18231f" stroke="#e9e2ca" stroke-width="2.5" paint-order="stroke">{state}</text>')

    for poi in data["poi_anchors"]:
        x, y = point(*poi["world_xz"])
        planned = poi["status"] != "current"
        color = "#f3d771" if not planned else "#6b3b2e"
        dash = ' stroke-dasharray="2 2"' if planned else ""
        svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5.5" fill="{color}" stroke="#fff4d3" stroke-width="1.5"{dash}/>')
        if poi["id"] in {"city_gate", "plaza_fountain", "magic_castle", "whisper_watchtower", "glassmere_windmill", "emberfall_mine", "moonfen_shrine", "skyreach_observatory"}:
            label = html.escape(poi["id"].replace("_", " "))
            label_dx, label_dy = {
                "whisper_watchtower": (10, -10),
                "glassmere_windmill": (10, -12),
                "emberfall_mine": (10, 16),
                "moonfen_shrine": (10, 16),
                "skyreach_observatory": (10, -12),
                "plaza_fountain": (10, -10),
                "magic_castle": (10, -12),
            }.get(poi["id"], (8, -6))
            svg.append(f'<text x="{x+label_dx:.2f}" y="{y+label_dy:.2f}" font-family="Arial,sans-serif" font-size="9.5" fill="#101913" stroke="#eee8d4" stroke-width="2.5" paint-order="stroke">{label}</text>')

    # Title, north arrow, scale and legend.
    svg.extend([
        '<text x="460" y="40" text-anchor="middle" font-family="Georgia,serif" font-size="23" fill="#f3ebd8">Aetherfield · World Layout V1</text>',
        '<text x="460" y="64" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" fill="#c9d2c9">1,024 × 1,024 m · planning blueprint · seven connected regions · 500-player target</text>',
        '<path d="M 855 58 L 845 78 L 855 74 L 865 78 Z" fill="#f3ebd8"/><text x="855" y="52" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" fill="#f3ebd8">N</text>',
        '<line x1="330" y1="844" x2="470" y2="844" stroke="#f3ebd8" stroke-width="4"/><line x1="330" y1="838" x2="330" y2="850" stroke="#f3ebd8" stroke-width="2"/><line x1="470" y1="838" x2="470" y2="850" stroke="#f3ebd8" stroke-width="2"/><text x="400" y="864" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" fill="#f3ebd8">200 m</text>',
        '<line x1="68" y1="884" x2="93" y2="884" stroke="#fff4c6" stroke-width="5"/><text x="100" y="888" font-family="Arial,sans-serif" font-size="10.5" fill="#f3ebd8">tested city route</text>',
        '<line x1="243" y1="884" x2="268" y2="884" stroke="#a9e5e0" stroke-width="4"/><text x="275" y="888" font-family="Arial,sans-serif" font-size="10.5" fill="#f3ebd8">new flat trail</text>',
        '<line x1="390" y1="884" x2="415" y2="884" stroke="#b58b66" stroke-width="5" stroke-dasharray="10 7"/><text x="422" y="888" font-family="Arial,sans-serif" font-size="10.5" fill="#f3ebd8">planned road</text>',
        '<rect x="554" y="876" width="24" height="15" fill="#a9d5dc" fill-opacity="0.45" stroke="#d1f4e9" stroke-width="2"/><text x="585" y="888" font-family="Arial,sans-serif" font-size="10.5" fill="#f3ebd8">existing meadow</text>',
        '<rect x="722" y="876" width="26" height="15" fill="none" stroke="#f0d475" stroke-width="2" stroke-dasharray="6 4"/><text x="755" y="888" font-family="Arial,sans-serif" font-size="10.5" fill="#f3ebd8">server clamp</text>',
        '<text x="460" y="909" text-anchor="middle" font-family="Arial,sans-serif" font-size="10" fill="#b7c0b6">South cells are flat y=0 detail terrain; full heightfield and navmesh remain future work. World bounds stay unchanged.</text>',
        '</svg>'
    ])
    OUTPUT_PATH.write_text("\n".join(svg) + "\n", encoding="utf-8")
    print(f"Rendered {OUTPUT_PATH.relative_to(ROOT)}: {len(svg)} SVG elements, 16 x 16 art cells.")


if __name__ == "__main__":
    main()
