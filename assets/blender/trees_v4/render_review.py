"""BLENDER REVIEW renders of one Quaternius MegaKit model (Route A step 1, trees v4).

Imports the kit glTF fresh into an empty factory scene (an in-memory COPY; the kit files
are never written), scales the copy so its height above the kit ground plane (object
origin) equals the decision-doc target (broadleaf M 7.5 m, pine M 8 m, bush 1.2 m), and
renders three views with a 1.8 m capsule witness standing beside it:

  player  - game camera: 13 m from a target 1.65 m above the witness's feet, 22.4 deg
            above horizontal (ArcRotate beta 1.18 rad), vertical FOV 1.02 rad;
  close   - 3 m from the canopy edge (2.5 m for bushes), framing the lower canopy edge
            and, where the crown base allows it, the witness's head;
  side    - orthographic side elevation, perpendicular to the player view.

Light: warm sun key #FFE7C2 at 45 deg elevation (from behind the player camera's left)
plus a soft blue sky fill (#A9C9F4, the game's hemisphere colour); camera rays see a
painted-free sky gradient. Cycles on the CPU, 32 samples + OpenImageDenoise, 768x432,
'ACES 1.3' view transform (closest Blender transform to the game's ACES tone mapping).

The kit's own glTF materials are used as imported (base colour x COLOR_0, alpha test at the
kit cutoff 0.2, bark normal map), i.e. what the asset looks like before any stylization.

Usage:
  blender -b --factory-startup --python render_review.py -- --src <glTF dir> --model NAME
      --out <dir> [--views player,close,side] [--samples 32] [--tag pass1] --cycles-device CPU
Writes <out>/<NAME>__<view>.png and <out>/<NAME>__views.json.
"""
import argparse
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

TARGETS = {"CommonTree": ("broadleaf", 7.5), "Pine": ("conifer", 8.0), "Bush": ("bush", 1.2),
           "TwistedTree": ("landmark", 9.5), "DeadTree": ("dead", 7.5)}
RES_X, RES_Y = 768, 432
FOV_Y = 1.02                      # rad, game camera
CAM_RADIUS = 13.0                 # m, game camera
CAM_BETA = 1.18                   # rad from vertical (ArcRotateCamera beta)
TARGET_H = 1.65                   # m above the feet
WITNESS_H, WITNESS_R = 1.8, 0.25
SUN_RGB_SRGB = (0xFF, 0xE7, 0xC2)
FILL_RGB_SRGB = (0xA9, 0xC9, 0xF4)
GROUND_A, GROUND_B = (0x6E, 0x7D, 0x32), (0x8E, 0x9A, 0x42)   # sampled from the target's meadow grass


def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(rgb):
    return tuple(srgb_to_linear(v) for v in rgb)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--views", default="player,close,side")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--tag", default="")
    ap.add_argument("--sun", type=float, default=3.6)
    ap.add_argument("--fill", type=float, default=0.3, help="occluded world-sky strength")
    ap.add_argument("--hemi", type=float, default=1.0, help="x game hemi/sun ratio (0.62/1.65)")
    ap.add_argument("--res", default="768x432", help="render resolution, e.g. 1920x1080 for game pixel density")
    ap.add_argument("--suffix", default="", help="appended to view names in files and sidecar, e.g. _1080")
    ap.add_argument("--mask", action="store_true", help="also render an alpha mask of the tree (ground holdout)")
    args, _unknown = ap.parse_known_args(argv)   # --cycles-device CPU is read by Cycles itself
    return args


def family(name):
    for key in TARGETS:
        if name.startswith(key):
            return key
    raise SystemExit(f"unknown model family: {name}")


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_material(name, rgb_srgb, roughness=0.8):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*lin(rgb_srgb), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def ground_material():
    mat = bpy.data.materials.new("review_meadow_ground")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 1.0
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*lin(GROUND_A), 1)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (*lin(GROUND_B), 1)
    tex = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tex.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def setup_world(fill_strength):
    world = bpy.data.worlds.new("review_sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    fill = nt.nodes.new("ShaderNodeBackground")
    fill.inputs["Color"].default_value = (*lin(FILL_RGB_SRGB), 1)
    fill.inputs["Strength"].default_value = fill_strength
    sky = nt.nodes.new("ShaderNodeBackground")
    sky.inputs["Strength"].default_value = 1.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = -0.05
    rng.inputs["From Max"].default_value = 0.65
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*lin((0xCB, 0xE0, 0xF2)), 1)
    ramp.color_ramp.elements[1].color = (*lin((0x6C, 0xA4, 0xE2)), 1)
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rng.inputs["Value"])
    nt.links.new(rng.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], sky.inputs["Color"])
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(fill.outputs["Background"], mix.inputs[1])
    nt.links.new(sky.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def setup_render(samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    try:
        scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    except Exception:
        pass
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 2
    scene.cycles.transparent_max_bounces = 48
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y   # set from --res before setup_render runs
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "ACES 1.3"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.threads_mode = "AUTO"
    return scene


HEMI_SKY_SRGB = (0xA9, 0xC9, 0xF4)      # game: hemisphere.diffuse (environment.ts)
HEMI_GROUND_SRGB = (0x6A, 0x74, 0x40)   # game: hemisphere.groundColor
GAME_HEMI_OVER_SUN = 0.62 / 1.65        # game: hemisphere.intensity / sun.intensity


def add_hemispheric_fill(mat, strength):
    """Babylon-style HemisphericLight term, which the game does not occlude:
    albedo * lerp(ground, sky, 0.5 + 0.5 * N.z) * strength, added as emission.
    Cycles otherwise occludes all sky light inside a dense card canopy (near-black interiors),
    which the game's renderer never shows. Alpha is applied outside so cut-out texels stay clear."""
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)
    if bsdf is None or out is None:
        return False
    base_link = next((l for l in nt.links if l.to_node == bsdf and l.to_socket.name == "Base Color"), None)
    alpha_link = next((l for l in nt.links if l.to_node == bsdf and l.to_socket.name == "Alpha"), None)
    normal_link = next((l for l in nt.links if l.to_node == bsdf and l.to_socket.name == "Normal"), None)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(normal_link.from_socket if normal_link else geo.outputs["Normal"], sep.inputs["Vector"])
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = -1.0
    rng.inputs["From Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], rng.inputs["Value"])
    hemi = nt.nodes.new("ShaderNodeMix")
    hemi.data_type = "RGBA"
    hemi.inputs["A"].default_value = (*lin(HEMI_GROUND_SRGB), 1)
    hemi.inputs["B"].default_value = (*lin(HEMI_SKY_SRGB), 1)
    nt.links.new(rng.outputs["Result"], hemi.inputs["Factor"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(hemi.outputs["Result"], mul.inputs["A"])
    if base_link:
        nt.links.new(base_link.from_socket, mul.inputs["B"])
    else:
        mul.inputs["B"].default_value = bsdf.inputs["Base Color"].default_value
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = strength
    nt.links.new(mul.outputs["Result"], emit.inputs["Color"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
    nt.links.new(emit.outputs["Emission"], add.inputs[1])
    final = add.outputs["Shader"]
    if alpha_link:
        transp = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(alpha_link.from_socket, mix.inputs["Fac"])
        nt.links.new(transp.outputs["BSDF"], mix.inputs[1])
        nt.links.new(add.outputs["Shader"], mix.inputs[2])
        nt.links.remove(alpha_link)
        bsdf.inputs["Alpha"].default_value = 1.0
        final = mix.outputs["Shader"]
    for l in [l for l in nt.links if l.to_node == out and l.to_socket.name == "Surface"]:
        nt.links.remove(l)
    nt.links.new(final, out.inputs["Surface"])
    return True


def capsule(location):
    bpy.ops.mesh.primitive_cylinder_add(radius=WITNESS_R, depth=WITNESS_H - 2 * WITNESS_R, vertices=24,
                                        location=(location[0], location[1], WITNESS_H / 2))
    body = bpy.context.object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=WITNESS_R, segments=24, ring_count=12,
                                         location=(location[0], location[1], WITNESS_H - WITNESS_R))
    top = bpy.context.object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=WITNESS_R, segments=24, ring_count=12,
                                         location=(location[0], location[1], WITNESS_R))
    bottom = bpy.context.object
    mat = make_material("witness_neutral", (0x94, 0x9A, 0xAB), 0.55)
    for ob in (body, top, bottom):
        ob.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in (body, top, bottom):
        ob.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    body.name = "witness_1p8m"
    for poly in body.data.polygons:
        poly.use_smooth = True
    return body


def projected_bbox(scene, cam, points):
    xs, ys, inside = [], [], 0
    for p in points:
        c = world_to_camera_view(scene, cam, Vector(p))
        if c.z <= 0:
            continue
        xs.append(c.x)
        ys.append(c.y)
        inside += 0.0 <= c.x <= 1.0 and 0.0 <= c.y <= 1.0
    if not xs:
        return None
    # pixel coordinates, origin top-left
    return {"x0": round(min(xs) * RES_X, 1), "x1": round(max(xs) * RES_X, 1),
            "y0": round((1 - max(ys)) * RES_Y, 1), "y1": round((1 - min(ys)) * RES_Y, 1),
            "share_inside": round(inside / len(xs), 4)}


def main():
    global RES_X, RES_Y
    args = parse()
    RES_X, RES_Y = (int(v) for v in args.res.lower().split("x"))
    t_start = time.time()
    fam = family(args.model)
    kind, target_h = TARGETS[fam]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = setup_render(args.samples)
    path = os.path.join(args.src, args.model + ".gltf")
    bpy.ops.import_scene.gltf(filepath=path)
    tree_objs = [ob for ob in bpy.data.objects if ob.type == "MESH"]
    ground_z = 0.0
    # world-space vertices as imported
    pts = []
    for ob in tree_objs:
        mw = np.array(ob.matrix_world)
        co = np.empty(len(ob.data.vertices) * 3, np.float32)
        ob.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        pts.append(co)
    pts = np.concatenate(pts)
    visible_h = float(pts[:, 2].max()) - ground_z
    s = target_h / visible_h
    for ob in tree_objs:
        ob.scale = (s, s, s)
        ob.location = (0, 0, 0)
    bpy.context.view_layer.update()
    pts = pts * s
    # foliage points for the canopy edge
    foliage_pts = []
    mix_modes = {}
    for ob in tree_objs:
        me = ob.data
        fol_idx = {i for i, m in enumerate(me.materials) if m and m.name.startswith(("Leaves", "Leaf", "Flowers"))}
        for m in me.materials:
            for n in m.node_tree.nodes:
                if n.bl_idname == "ShaderNodeMix":
                    mix_modes[m.name] = {"blend_type": n.blend_type, "factor": n.inputs[0].default_value}
        vids = {v for p in me.polygons if p.material_index in fol_idx for v in p.vertices}
        mw = ob.matrix_world
        foliage_pts.extend([tuple(mw @ me.vertices[v].co) for v in vids])
    foliage = np.array(foliage_pts) if foliage_pts else pts
    if not len(foliage):
        foliage = pts
    crown_c = (foliage[:, :2].max(axis=0) + foliage[:, :2].min(axis=0)) / 2
    crown_base = float(np.percentile(foliage[:, 2], 5))
    top = float(pts[:, 2].max())

    def edge_radius(az_deg, z_lo, z_hi, half_width_deg=25):
        d = foliage[:, :2]
        sel = (foliage[:, 2] >= z_lo) & (foliage[:, 2] <= z_hi)
        if not sel.any():
            sel = np.ones(len(foliage), bool)
        rel = d[sel]
        ang = (np.degrees(np.arctan2(rel[:, 0], rel[:, 1])) + 360) % 360
        diff = np.abs((ang - az_deg + 180) % 360 - 180)
        near = rel[diff <= half_width_deg]
        if not len(near):
            near = rel
        return float(np.linalg.norm(near, axis=1).max())

    # --- witness: just outside the drip line, front-left of the trunk (toward the player camera) ---
    wit_az = 205.0
    if kind == "bush":
        r_e = edge_radius(wit_az, 0.0, target_h)
        r_w = r_e + 0.45
    else:
        r_e = edge_radius(wit_az, crown_base, crown_base + 0.45 * (top - crown_base))
        r_w = r_e + 0.4
        # keep >= 3.5 % top margin in the player view: the apex must stay below the frame top
        tan_lim = 0.93 * math.tan(FOV_Y / 2)
        elev = math.pi / 2 - CAM_BETA
        cam_h = TARGET_H + CAM_RADIUS * math.sin(elev)
        alpha_max = math.atan(tan_lim) - elev
        if top > cam_h:
            d_need = (top - cam_h) / math.tan(alpha_max)
            depth_need = d_need - CAM_RADIUS * math.cos(elev)
            r_need = depth_need / abs(math.cos(math.radians(wit_az)))
            r_w = max(r_w, min(r_need, 4.5))
    if kind == "bush":
        wit_az = 270.0   # beside the bush at the same depth, so it never hides the bush
        r_w = edge_radius(wit_az, 0.0, target_h) + 0.45
    wdir = Vector((math.sin(math.radians(wit_az)), math.cos(math.radians(wit_az)), 0))
    wpos = wdir * r_w   # the trunk stands at the kit origin
    if kind == "bush":
        wpos_side = Vector((0.0, -(edge_radius(180.0, 0.0, target_h) + 0.45), 0.0))
    else:
        wpos_side = wpos
    witness = capsule(wpos)
    # --- ground, light, world ---
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, ground_z))
    ground = bpy.context.object
    ground.name = "review_ground"
    ground.data.materials.append(ground_material())
    sun_data = bpy.data.lights.new("sun_key", "SUN")
    sun_data.energy = args.sun
    sun_data.color = lin(SUN_RGB_SRGB)
    sun_data.angle = math.radians(2.0)
    sun = bpy.data.objects.new("sun_key", sun_data)
    scene.collection.objects.link(sun)
    sun_az = 225.0   # toward the sun: behind the player camera, on its left
    to_sun = Vector((math.cos(math.radians(45)) * math.sin(math.radians(sun_az)),
                     math.cos(math.radians(45)) * math.cos(math.radians(sun_az)), math.sin(math.radians(45))))
    sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    setup_world(args.fill)
    hemi_strength = args.sun * GAME_HEMI_OVER_SUN * args.hemi
    # side-view-only ground band: hides the kit's buried skirt in the edge-on elevation
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-20.5, 0.0, -2.0))
    band = bpy.context.object
    band.name = "side_view_ground_band"
    band.scale = (1.0, 120.0, 4.0)
    band.data.materials.append(ground.data.materials[0])
    band.visible_shadow = False
    hemi_done = []
    for mat in bpy.data.materials:
        if mat.node_tree is not None and add_hemispheric_fill(mat, hemi_strength):
            hemi_done.append(mat.name)
    # --- cameras ---
    views = [v for v in args.views.split(",") if v]
    results = {"label": "BLENDER REVIEW (Cycles CPU render; not a Babylon capture)",
               "model": args.model, "kind": kind, "tag": args.tag, "blender": bpy.app.version_string,
               "target_height_m": target_h, "scale_applied_to_copy": round(s, 5),
               "visible_height_imported_m": round(visible_h, 4), "crown_base_p5_m": round(crown_base, 3),
               "top_m": round(top, 3), "witness": {"pos_m": [round(v, 3) for v in wpos], "height_m": WITNESS_H,
                                                   "radius_m": WITNESS_R, "azimuth_deg": wit_az, "dist_from_trunk_m": round(r_w, 3)},
               "light": {"sun_srgb": "#FFE7C2", "sun_strength": args.sun, "sun_elevation_deg": 45, "sun_azimuth_deg": sun_az,
                         "sun_angle_deg": 2.0, "occluded_world_sky_fill_srgb": "#A9C9F4", "occluded_world_sky_strength": args.fill,
                         "hemispheric_fill": {"model": "Babylon HemisphericLight emulation (unoccluded), albedo-weighted emission",
                                              "sky_srgb": "#A9C9F4", "ground_srgb": "#6A7440", "strength": round(hemi_strength, 4),
                                              "ratio_to_sun": round(GAME_HEMI_OVER_SUN * args.hemi, 4), "materials": hemi_done}},
               "render": {"engine": "CYCLES", "device": scene.cycles.device, "samples": args.samples, "denoise": True,
                          "resolution": [RES_X, RES_Y], "view_transform": scene.view_settings.view_transform,
                          "threads": scene.render.threads},
               "material_color0_mix": mix_modes, "views": {}}
    cam_data = bpy.data.cameras.new("review_cam")
    cam = bpy.data.objects.new("review_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    sample_pts = pts[:: max(1, len(pts) // 6000)]
    view_wpos = {}
    for view in views:
        t0 = time.time()
        info = {}
        band.hide_render = view != "side"
        witness.location = (wpos.x, wpos.y, WITNESS_H / 2)
        view_wpos[view] = wpos
        if view == "player":
            cam_data.type = "PERSP"
            cam_data.sensor_fit = "VERTICAL"
            cam_data.angle_y = FOV_Y
            cam_data.clip_start = 0.1
            cam_data.clip_end = 500
            target = wpos + Vector((0, 0, TARGET_H))
            elev = math.pi / 2 - CAM_BETA
            cam.location = target + Vector((0, -math.cos(elev), math.sin(elev))) * CAM_RADIUS
            look_at(cam, target)
            info.update({"camera": "perspective", "target_m": [round(v, 3) for v in target], "radius_m": CAM_RADIUS,
                         "beta_rad": CAM_BETA, "elevation_deg": round(math.degrees(elev), 2), "fov_y_rad": FOV_Y})
        elif view == "close":
            cam_data.type = "PERSP"
            cam_data.sensor_fit = "VERTICAL"
            cam_data.angle_y = FOV_Y
            cam_data.clip_start = 0.05
            cam_data.clip_end = 300
            close_az = 232.0
            cdir = Vector((math.sin(math.radians(close_az)), math.cos(math.radians(close_az)), 0))
            if kind == "bush":
                z_e = 0.6 * target_h
                r_ce = edge_radius(close_az, 0.3 * target_h, target_h)
                dist = 2.5
                cam_z = 1.65
            else:
                z_e = min(crown_base + 0.7, top - 1.0)
                r_ce = edge_radius(close_az, z_e - 0.6, z_e + 0.6)
                dist = 2.6
                cam_z = None
            edge_pt = cdir * r_ce + Vector((0, 0, z_e))
            # The witness stands beside the canopy edge, a little around the crown from the camera's azimuth,
            # so it is in frame (each view is a separate render). Search spots x distances; prefer the
            # shoulders in frame, then at least the head.
            aim, chosen = None, None
            offsets = (-70, 70, -55, 55) if kind == "bush" else (-24, 24, -34, 34, -16, 16)
            radial = (0.4,) if kind == "bush" else (0.35, -0.4, -1.0)
            dists = (2.5,) if kind == "bush" else (2.6, 2.9)
            for tier, probe_h in ((1, 1.45), (2, 1.62)):
                for dist_try in dists:
                    for dr in radial:
                        for off in offsets:
                            w_az = close_az + off
                            wd = Vector((math.sin(math.radians(w_az)), math.cos(math.radians(w_az)), 0))
                            if kind == "bush":
                                w_r = edge_radius(w_az, 0.0, target_h) + dr
                            else:
                                w_r = max(0.9, edge_radius(w_az, crown_base, crown_base + 0.45 * (top - crown_base)) + dr)
                            w_p = wd * w_r
                            probe = w_p + Vector((0, 0, probe_h))
                            cz = cam_z if cam_z is not None else (z_e + 1.45) / 2 + 0.35
                            cam.location = cdir * (r_ce + dist_try) + Vector((0, 0, cz))
                            look_target = (Vector((0, 0, 0.5 * target_h)) if kind == "bush" else edge_pt)
                            for w in [x / 20 for x in range(0, 13)]:   # smallest weight that frames both
                                cand = look_target * (1 - w) + probe * w
                                look_at(cam, cand)
                                bpy.context.view_layer.update()
                                ep = world_to_camera_view(scene, cam, edge_pt)
                                pp = world_to_camera_view(scene, cam, probe)
                                if (0.12 <= ep.y <= 0.9 and 0.05 <= ep.x <= 0.95 and 0.06 <= pp.y <= 0.94
                                        and 0.06 <= pp.x <= 0.94 and pp.z > 0.6
                                        and (cam.location - edge_pt).length <= 3.0):
                                    aim, chosen = cand, (w_p, off, w, dist_try, dr, tier)
                                    break
                            if aim is not None:
                                break
                        if aim is not None:
                            break
                    if aim is not None:
                        break
                if aim is not None:
                    break
            if aim is None:
                w_p = Vector((math.sin(math.radians(close_az - 24)), math.cos(math.radians(close_az - 24)), 0)) * (r_ce + 0.35)
                cam.location = cdir * (r_ce + dist) + Vector((0, 0, z_e - 0.5))
                aim, chosen = edge_pt, (w_p, -24, 0.0, dist, 0.35, 0)
                info["note"] = "crown base too high to frame the canopy edge and the witness together within 3 m"
            info["witness_search"] = {"tier": chosen[5], "camera_dist_from_edge_m": chosen[3], "radial_offset_m": chosen[4]}
            witness.location = (chosen[0].x, chosen[0].y, WITNESS_H / 2)
            view_wpos[view] = chosen[0]
            info["witness_offset_deg"] = chosen[1]
            info["aim_weight_toward_witness"] = chosen[2]
            look_at(cam, aim)
            bpy.context.view_layer.update()
            info.update({"camera": "perspective", "fov_y_rad": FOV_Y, "azimuth_deg": close_az,
                         "canopy_edge_point_m": [round(v, 3) for v in edge_pt],
                         "distance_to_canopy_edge_m": round((cam.location - edge_pt).length, 3),
                         "camera_m": [round(v, 3) for v in cam.location]})
        elif view == "side":
            cam_data.type = "ORTHO"
            cam_data.sensor_fit = "AUTO"
            cam_data.clip_start = 0.1
            cam_data.clip_end = 500
            witness.location = (wpos_side.x, wpos_side.y, WITNESS_H / 2)
            view_wpos[view] = wpos_side
            ys = np.concatenate([pts[:, 1], [wpos_side.y - WITNESS_R, wpos_side.y + WITNESS_R]])
            y_min, y_max = float(ys.min()), float(ys.max())
            height_needed = max(top, WITNESS_H + 0.1) / (0.88 - 0.06)
            width_needed = (y_max - y_min) * 1.18
            ortho = max(width_needed, height_needed * RES_X / RES_Y)
            cam_data.ortho_scale = ortho
            v_extent = ortho * RES_Y / RES_X
            z_c = ground_z + v_extent * (0.88 - 0.5)
            y_c = (y_min + y_max) / 2
            cam.location = Vector((-60.0, y_c, z_c))
            look_at(cam, Vector((0.0, y_c, z_c)))
            px_per_m = RES_X / ortho
            info.update({"camera": "orthographic", "looking": "+X (screen right = -Y)", "ortho_scale_m": round(ortho, 4),
                         "px_per_m": round(px_per_m, 4), "ground_row_px": round(RES_Y / 2 + (z_c - ground_z) * px_per_m, 2),
                         "centre_z_m": round(z_c, 4)})
        else:
            continue
        bpy.context.view_layer.update()
        info["tree_bbox_px"] = projected_bbox(scene, cam, sample_pts)
        head = view_wpos[view] + Vector((0, 0, WITNESS_H))
        feet = view_wpos[view] + Vector((0, 0, 0.02))
        info["witness_pos_m"] = [round(v, 3) for v in view_wpos[view]]
        hp = world_to_camera_view(scene, cam, head)
        fp = world_to_camera_view(scene, cam, feet)
        info["witness_head_px"] = [round(hp.x * RES_X, 1), round((1 - hp.y) * RES_Y, 1)]
        info["witness_feet_px"] = [round(fp.x * RES_X, 1), round((1 - fp.y) * RES_Y, 1)]
        info["witness_in_frame"] = bool(0 <= hp.x <= 1 and 0 <= hp.y <= 1 or 0 <= fp.x <= 1 and 0 <= fp.y <= 1)
        out_png = os.path.join(args.out, f"{args.model}__{view}{args.suffix}.png")
        scene.render.filepath = out_png
        bpy.ops.render.render(write_still=True)
        info["file"] = os.path.basename(out_png)
        info["resolution"] = [RES_X, RES_Y]
        if args.mask:
            t_m = time.time()
            ground.is_holdout = True
            witness.hide_render = True
            band.hide_render = True
            scene.render.film_transparent = True
            scene.render.image_settings.color_mode = "RGBA"
            samples, denoise = scene.cycles.samples, scene.cycles.use_denoising
            scene.cycles.samples, scene.cycles.use_denoising = 8, False
            mask_png = os.path.join(args.out, f"{args.model}__{view}{args.suffix}_mask.png")
            scene.render.filepath = mask_png
            bpy.ops.render.render(write_still=True)
            info["mask_file"] = os.path.basename(mask_png)
            info["mask_seconds"] = round(time.time() - t_m, 2)
            ground.is_holdout = False
            witness.hide_render = False
            scene.render.film_transparent = False
            scene.render.image_settings.color_mode = "RGB"
            scene.cycles.samples, scene.cycles.use_denoising = samples, denoise
        info["seconds"] = round(time.time() - t0, 2)
        results["views"][view + args.suffix] = info
        print("RENDERED", args.model, view + args.suffix, info["seconds"], flush=True)
    results["seconds_total"] = round(time.time() - t_start, 2)
    side_json = os.path.join(args.out, f"{args.model}__views.json")
    if os.path.exists(side_json):
        try:
            old = json.load(open(side_json, encoding="utf-8"))
            old_views = old.get("views", {})
            old_views.update(results["views"])
            results["views"] = old_views
        except Exception:
            pass
    with open(side_json, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    print("WROTE", side_json)


main()
