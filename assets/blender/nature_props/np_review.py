"""BLENDER REVIEW renders for the Sunmeadow prop library (stage 3, Blender).

Per review group (a lineup of assets with a 1.8 m capsule witness), renders:
  front   orthographic, looking +Y (asset front faces -Y in Blender = +Z in glTF)
  side    orthographic, looking -X
  q34     perspective 3/4 from front-left, elevated 25 deg
  game    the player camera: ArcRotate radius 13 m, beta 1.18 rad (22.4 deg above horizontal), vertical FOV
          1.02 rad, target 1.65 m above the feet, looking at the lineup centre
  game_sil the same camera, ground and witness hidden, transparent film: alpha = silhouette (greyscale check)
Light: warm sun #FFE7C2 (elevation 48 deg, from the camera's left), sky-gradient world fill (#A9C9F4 family),
Cycles CPU, OIDN, 'ACES 1.3' view (closest to the game's ACES tone mapping), fallback AgX.

  blender -b --factory-startup --python-exit-code 1 --python np_review.py -- --plan <review_plan.json>

review_plan.json: {"out": dir, "res": [w, h], "samples": n, "threads": n, "groups": [{"name", "blend_sources":
[[blend, [object names]]], "spacing": m, "ground": "meadow"|"sand"|"water", "views": [...],
"materials": {"<object>": {"albedo","normal","orm","alpha_clip","double_sided","vertex_color"}}}]}
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import np_lib as L  # noqa: E402

FOV_Y, CAM_R, CAM_BETA, TARGET_H = 1.02, 13.0, 1.18, 1.65
SUN = (0xFF, 0xE7, 0xC2)
GROUNDS = {"meadow": ((0x6E, 0x7D, 0x32), (0x8E, 0x9A, 0x42)), "sand": ((0xC9, 0xB2, 0x86), (0xDD, 0xC9, 0x9C)),
           "water": ((0x2C, 0x5E, 0x63), (0x3B, 0x76, 0x78)), "dirt": ((0x6B, 0x55, 0x3A), (0x86, 0x6D, 0x4C))}


def lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin3(rgb):
    return tuple(lin(x) for x in rgb)


def setup_render(res, samples, threads):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 2
    sc.cycles.transparent_max_bounces = 24
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.threads_mode = "FIXED"
    sc.render.threads = threads
    for vt in ("ACES 1.3", "AgX", "Standard"):
        try:
            sc.view_settings.view_transform = vt
            break
        except TypeError:
            continue
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    return sc


def setup_world(strength=0.55):
    world = bpy.data.worlds.new("review_sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = -0.05
    rng.inputs["From Max"].default_value = 0.65
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*lin3((0xCB, 0xE0, 0xF2)), 1)
    ramp.color_ramp.elements[1].color = (*lin3((0x6C, 0xA4, 0xE2)), 1)
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rng.inputs["Value"])
    nt.links.new(rng.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_sun(azimuth_deg, elevation_deg=48.0, strength=3.6):
    sd = bpy.data.lights.new("review_sun", "SUN")
    sd.energy = strength
    sd.color = lin3(SUN)
    sd.angle = math.radians(2.5)
    ob = bpy.data.objects.new("review_sun", sd)
    bpy.context.scene.collection.objects.link(ob)
    el, az = math.radians(elevation_deg), math.radians(azimuth_deg)
    d = Vector((math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)))  # towards the sun
    ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return ob


def ground_plane(kind, size, center):
    a, b = GROUNDS[kind]
    me = bpy.data.meshes.new("review_ground")
    s = size / 2
    me.from_pydata([(center[0] - s, center[1] - s, 0), (center[0] + s, center[1] - s, 0),
                    (center[0] + s, center[1] + s, 0), (center[0] - s, center[1] + s, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("review_ground", me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("review_ground_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.95 if kind != "water" else 0.15
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*lin3(a), 1)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (*lin3(b), 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    ob.data.materials.append(mat)
    return ob


def witness(loc):
    r, hgt = 0.25, 1.8
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=hgt - 2 * r, vertices=24, location=(loc[0], loc[1], hgt / 2))
    body = bpy.context.object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=24, ring_count=12, location=(loc[0], loc[1], hgt - r))
    top = bpy.context.object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=24, ring_count=12, location=(loc[0], loc[1], r))
    bot = bpy.context.object
    mat = bpy.data.materials.new("witness_neutral")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*lin3((0x94, 0x9A, 0xAB)), 1)
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.55
    for o in (body, top, bot):
        o.data.materials.append(mat)
    with bpy.context.temp_override(active_object=body, selected_editable_objects=[body, top, bot],
                                   selected_objects=[body, top, bot]):
        bpy.ops.object.join()
    body.name = "witness_1p8m"
    for p in body.data.polygons:
        p.use_smooth = True
    return body


def camera(name, loc, target, ortho_scale=None, fov_y=None):
    cd = bpy.data.cameras.new(name)
    if ortho_scale:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho_scale
    else:
        cd.sensor_fit = "VERTICAL"
        cd.angle_y = fov_y or 0.6
    cd.clip_start, cd.clip_end = 0.05, 500
    ob = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def append_objects(blend, names):
    with bpy.data.libraries.load(str(blend), link=False) as (src, dst):
        dst.objects = [n for n in names if n in src.objects]
    got = []
    for ob in dst.objects:
        if ob is None:
            continue
        bpy.context.scene.collection.objects.link(ob)
        got.append(ob)
    return got


def assign_material(ob, spec):
    mat = L.pbr_material(f"rv_{ob.name}", spec["albedo"], spec.get("normal"), spec.get("orm"),
                         alpha_clip=spec.get("alpha_clip"), vertex_color=spec.get("vertex_color"),
                         double_sided=spec.get("double_sided", False))
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    if not spec.get("double_sided", False):
        _cull_backfaces(mat)
    return mat


def _cull_backfaces(mat):
    """Cycles ignores backface culling; emulate Babylon's culling (backface -> transparent)."""
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    link = next(l for l in nt.links if l.to_node == out and l.to_socket.name == "Surface")
    src = link.from_socket
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Backfacing"], mix.inputs["Fac"])
    nt.links.new(src, mix.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
    nt.links.remove(link)
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def bounds(objs):
    pts = []
    for o in objs:
        mw = np.array(o.matrix_world)
        v = L.verts(o.data) @ mw[:3, :3].T + mw[:3, 3]
        pts.append(v)
    p = np.concatenate(pts)
    return p.min(0), p.max(0)


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = str(path)
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    return round(time.time() - t0, 1)


def run_group(g, plan, out):
    L.reset()
    setup_render(tuple(plan.get("res", [960, 540])), int(plan.get("samples", 24)), int(plan.get("threads", 6)))
    setup_world(float(plan.get("world_strength", 0.55)))
    objs = []
    for blend, names in g["blend_sources"]:
        objs += append_objects(blend, names)
    order = {n: i for i, n in enumerate(sum([s[1] for s in g["blend_sources"]], []))}
    objs.sort(key=lambda o: order.get(o.name, 0))
    mats = g.get("materials", {})
    for o in objs:
        spec = mats.get(o.name)
        if spec:
            assign_material(o, spec)
    # lineup along X with gaps, fronts facing -Y
    spacing = float(g.get("spacing", 0.8))
    x = 0.0
    for o in objs:
        mn, mx = bounds([o])
        w = mx[0] - mn[0]
        o.location = (x - mn[0] + o.location[0], o.location[1] - (mn[1] + mx[1]) / 2, o.location[2])
        x += w + spacing
    wx = x + 0.2
    wit = witness((wx + 0.25, 0.0))
    mn, mx = bounds(objs + [wit])
    cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    width, height = mx[0] - mn[0], max(mx[2], 1.8)
    ground = ground_plane(g.get("ground", "meadow"), max(width, 10) * 3 + 40, (cx, cy))
    add_sun(azimuth_deg=g.get("sun_azimuth", 215.0))
    res = plan.get("res", [960, 540])
    aspect = res[0] / res[1]
    views = g.get("views", ["front", "side", "q34", "game", "game_sil"])
    results = {}
    tag = g["name"]
    for vw in views:
        for c in [o for o in bpy.data.objects if o.type == "CAMERA"]:
            bpy.data.objects.remove(c, do_unlink=True)
        sc = bpy.context.scene
        sc.render.film_transparent = False
        ground.hide_render = False
        wit.hide_render = False
        if vw == "front":
            span = max(width * 1.08, height * 1.25 * aspect)
            cam = camera("cam_front", (cx, cy - 60, height * 0.45), (cx, cy, height * 0.45), ortho_scale=span)
        elif vw == "side":
            depth = mx[1] - mn[1]
            span = max(depth * 1.6, height * 1.3 * aspect)
            cam = camera("cam_side", (mx[0] + 60, cy, height * 0.45), (cx - 1000, cy, height * 0.45),
                         ortho_scale=span)
            cam.rotation_euler = (Vector((-1, 0, 0))).to_track_quat("-Z", "Y").to_euler()
            cam.location = (mx[0] + 60, cy, height * 0.45)
        elif vw == "q34":
            dist = max(width, height * aspect) * 1.0 / math.tan(0.35) * 0.62 + 2
            az = math.radians(-38.0)
            el = math.radians(24.0)
            tgt = (cx, cy, height * 0.4)
            loc = (cx + dist * math.cos(el) * math.sin(az), cy - dist * math.cos(el) * math.cos(az),
                   tgt[2] + dist * math.sin(el))
            cam = camera("cam_q34", loc, tgt, fov_y=0.7)
        else:  # game / game_sil
            elev = math.pi / 2 - CAM_BETA
            tgt = (cx, cy, TARGET_H)
            az = math.radians(g.get("game_azimuth", -20.0))
            loc = (cx + CAM_R * math.cos(elev) * math.sin(az), cy - CAM_R * math.cos(elev) * math.cos(az),
                   TARGET_H + CAM_R * math.sin(elev))
            cam = camera("cam_game", loc, tgt, fov_y=FOV_Y)
            if vw == "game_sil":
                sc.render.film_transparent = True
                ground.hide_render = True
                wit.hide_render = False
        sc.camera = cam
        path = out / f"{tag}__{vw}.png"
        results[vw] = {"file": path.name, "render_s": render(path), "camera": [round(v, 3) for v in cam.location]}
        L.log(f"render {tag} {vw} {results[vw]['render_s']}s")
    return {"group": tag, "objects": [o.name for o in objs], "views": results,
            "witness_height_m": 1.8, "lineup_width_m": round(float(width), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    args = ap.parse_args(L.args_after_dashdash())
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    out = Path(plan["out"])
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for g in plan["groups"]:
        summary.append(run_group(g, plan, out))
    L.write_json(out / f"review_{plan.get('tag', 'run')}.json", {"plan": str(args.plan), "groups": summary})
    L.log("REVIEW OK")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
