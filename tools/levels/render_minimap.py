"""Deterministic unframed north-up Sunmeadow minimap assets (PLAN, not engine proof)."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PALETTE = {"meadow": "#8dba72", "forest": "#427758", "path": "#d2b789", "water": "#438d98",
           "sand": "#e0cca0", "rock": "#9f9d8d", "buildings": "#805d47", "arena": "#b9ad7a"}
CLASSES = {name: n for n, name in enumerate(PALETTE)}


def affine(bounds):
    x0, x1, z0, z1 = bounds
    return [[1 / (x1 - x0), 0, -x0 / (x1 - x0)], [0, -1 / (z1 - z0), z1 / (z1 - z0)]]


def world_uv(x, z, transform):
    return [transform[0][0] * x + transform[0][1] * z + transform[0][2],
            transform[1][0] * x + transform[1][1] * z + transform[1][2]]


def render(layout, size=2048):
    bounds = layout["bounds_xz"]["stage"]
    transform = affine(bounds)
    x0, x1, z0, z1 = bounds
    image = Image.new("L", (size, size), CLASSES["meadow"])
    d = ImageDraw.Draw(image)
    def p(q):
        u, v = world_uv(*q, transform)
        return round(u * (size - 1)), round(v * (size - 1))
    def polygon(points, kind):
        d.polygon([p(q) for q in points], fill=CLASSES[kind])
    def rect(b, kind):
        polygon([[b[0], b[2]], [b[1], b[2]], [b[1], b[3]], [b[0], b[3]]], kind)
    def circle(center, radius, kind):
        x, z = center
        d.ellipse([p([x - radius, z + radius]), p([x + radius, z - radius])], fill=CLASSES[kind])
    def line(points, width, kind):
        # Polygon strips use independent x/z scales, so the map's affine remains exact.
        for a, b in zip(points, points[1:]):
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dz)
            if not length:
                continue
            ox, oz = -dz / length * width / 2, dx / length * width / 2
            polygon([[a[0]+ox,a[1]+oz],[b[0]+ox,b[1]+oz],[b[0]-ox,b[1]-oz],[a[0]-ox,a[1]-oz]],kind)
            circle(a, width / 2, kind)
            circle(b, width / 2, kind)
    # Forest masses first. No fabricated individual tree placements.
    for zone in layout["vegetation_zones"]:
        if "polygon_xz" in zone:
            polygon(zone["polygon_xz"], "forest")
    for relief in layout["relief"]:
        if "footprint_xz" in relief:
            rect(relief["footprint_xz"], "rock")
        elif "polyline_xz" in relief:
            pts = relief["polyline_xz"]
            kind = "forest" if relief["kind"] == "forest_wall" else "rock"
            gap = relief.get("gap", {}).get("between_z")
            for a, b in zip(pts, pts[1:]):
                cuts = [0.0, 1.0]
                if gap and a[1] != b[1]:
                    cuts += [(z - a[1]) / (b[1] - a[1]) for z in gap if 0 < (z-a[1])/(b[1]-a[1]) < 1]
                cuts.sort()
                for t0, t1 in zip(cuts, cuts[1:]):
                    middle_z = a[1] + (b[1] - a[1]) * (t0 + t1) / 2
                    if gap and min(gap) < middle_z < max(gap):
                        continue
                    segment = [[a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t] for t in [t0,t1]]
                    line(segment, 3 if kind == "forest" else 5, kind)
    for feature in layout["features"]:
        geometry = feature.get("geometry", {})
        if "beach_polygon_xz" in geometry:
            polygon(geometry["beach_polygon_xz"], "sand")
        carve = feature.get("carve", {})
        for key in ["ledge_notch_polygon_xz", "tunnel_polygon_xz"]:
            if key in carve:
                polygon(carve[key], "path")
        if "chamber" in carve:
            polygon(carve["chamber"]["polygon_xz"], "path")
    for water in layout["water"]:
        if water["kind"] == "lake":
            polygon(water["outline_xz"], "water")
        elif water["kind"] == "pool":
            circle(water["center_xz"], water["radius_m"], "water")
        elif water["kind"] == "stream":
            keys = water.get("centreline_keys")
            if keys:
                for a, b in zip(keys, keys[1:]):
                    line([a["xz"], b["xz"]], (a["width_m"]+b["width_m"])/2, "water")
            else:
                line(water["points"], max(water["width_m"]), "water")
    for clearing in layout["clearings"]:
        if clearing["id"] == "windstone_glade":
            circle(clearing["center_xz"], 12, "arena")
    # Restore dry terraces over the pond, then routes and walk decks over water.
    for feature in layout["features"]:
        if "terrace_polygon_xz" in feature.get("geometry", {}):
            polygon(feature["geometry"]["terrace_polygon_xz"], "rock")
    for walk in layout["walk_network"]["items"]:
        if "points" in walk:
            line(walk["points"], walk["width_m"], "path")
        elif walk["class"] == "deck":
            polygon(walk["polygon_xz"], "buildings")
    for feature in layout["features"]:
        for building in feature.get("buildings", []):
            if "diameter_m" in building:
                circle(building["center_xz"], building["diameter_m"]/2, "buildings")
            elif "bounds_xz" in building:
                b=building["bounds_xz"]
                line([[b[0],b[2]],[b[1],b[2]],[b[1],b[3]],[b[0],b[3]],[b[0],b[2]]],.6,"buildings")
    camp = next(q for q in layout["landmarks"] if q["id"] == "hunter_camp")
    rect(camp["bounds_xz"], "buildings")
    indices = np.asarray(image)
    palette = np.asarray([tuple(bytes.fromhex(col[1:])) for col in PALETTE.values()], dtype=np.uint8)
    base = Image.fromarray(palette[indices])
    edge = np.zeros((size, size), dtype=np.uint8)
    edge[:,1:] |= (indices[:,1:] != indices[:,:-1]).astype(np.uint8)*255
    edge[1:,:] |= (indices[1:,:] != indices[:-1,:]).astype(np.uint8)*255
    icons=[]
    selected={"feature","warp","arena","fishing_spot","discovery_chest","npc_slot","rest_shrine"}
    for anchor in layout["anchor_index"]:
        if anchor["kind"] in selected or anchor["id"] == "hunter_camp":
            icons.append({"id": anchor["id"], "kind": anchor["kind"], "world_xz": anchor["xz"],
                          "uv": world_uv(*anchor["xz"], transform)})
    icons.insert(0,{"id":"player_spawn","kind":"spawn","world_xz":[-3,-3],"uv":world_uv(-3,-3,transform)})
    if not any(q["id"]=="hunter_camp" for q in icons):
        b=camp["bounds_xz"];xz=[(b[0]+b[1])/2,(b[2]+b[3])/2]
        icons.append({"id":"hunter_camp","kind":"camp","world_xz":xz,"uv":world_uv(*xz,transform)})
    meta={"schema":"xexoria.minimap/1","classification":"PLAN","region":"sunmeadow","layout_version":layout["version"],
          "size_px":[size,size],"bounds_xz":bounds,"north_up":True,"uv_origin":"top-left",
          "world_xz_to_uv_affine":transform,"uv_to_world_xz_affine":[[x1-x0,0,x0],[0,-(z1-z0),z1]],
          "palette":PALETTE,"class_ids":CLASSES,"icon_anchors":icons,
          "presentation":{"shape":"rounded-rectangle","desktop_css_px":[160,160],"phone_css_px":[132,132],
                          "border_radius_css_px":12,"zoom_levels":[1,2],"icons_baked":False,"frame_baked":False}}
    return base, Image.fromarray(edge), image, meta


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout",default=str(ROOT/"planning/levels/sunmeadow-v2-layout.json"))
    parser.add_argument("--out",default=str(ROOT/"planning/evidence/sunmeadow-v3-features/minimap"))
    args=parser.parse_args(); source=Path(args.layout);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    base,edges,classes,meta=render(json.loads(source.read_text(encoding="utf8")))
    for img,name in [(base,"minimap_base_2048.png"),(edges,"minimap_edges.png"),(classes,"minimap_classes.png")]:
        img.save(out/name)
    base.resize((160,160),Image.Resampling.LANCZOS).save(out/"PLAN-minimap-preview-160.png")
    meta["source_sha256"]=hashlib.sha256(source.read_bytes()).hexdigest()
    meta["output_sha256"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.png"))}
    (out/"minimap_meta.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf8")
    print(f"minimap: {out}; 2048 px; {len(meta['icon_anchors'])} separate anchors")


if __name__=="__main__":
    main()
