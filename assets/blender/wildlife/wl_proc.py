"""Procedural toolkit for the wildlife pipeline: seeded geometry, rigs, skin weights, clips, parametric paint.

Geometry is built in Python (lofted bodies + alpha cards) with per-loop UVs, so every texel has a known
parametric meaning (angle around the body, position along it). Small creatures are painted in that parametric
space with numpy (no bake), which keeps every pattern a pure function of (recipe, seed, params).

Conventions (match the XS1 contract where it applies, docs/reviews/2026-10-02-heroes-rig-and-animation.md §3.1):
- metres; Blender +Z up; the creature faces Blender -Y (= Babylon +Z, facing 0); its left side is Blender +X;
- flyers and swimmers pivot at the body centre; walkers pivot at the ground contact between the feet;
- root bone at the origin is never animated (root motion off); only the body bone carries translation keys;
- clips are baked at 30 fps with one key per frame, quaternion rotations, no scale keys;
- at most 4 influences per vertex, normalised, pruned below 0.01.
"""
from __future__ import annotations

import math
from pathlib import Path

import bmesh  # noqa: F401  (kept for recipes that post-edit meshes)
import bpy
import numpy as np
from bpy_extras import anim_utils
from mathutils import Matrix, Quaternion, Vector

import wl_common as C

UP = Vector((0.0, 0.0, 1.0))
FWD = Vector((0.0, -1.0, 0.0))
LEFT = Vector((1.0, 0.0, 0.0))


# ================================================================================================ scene helpers
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.fps = C.FPS
    scn.render.fps_base = 1.0
    return scn


def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def activate(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ================================================================================================ mesh builder
class MeshBuilder:
    """Accumulates vertices, faces, per-loop UVs, a per-vertex part id and per-face regions."""

    def __init__(self, name):
        self.name = name
        self.verts = []
        self.part = []
        self.faces = []
        self.uvs = []
        self.region = []
        self.meta = {}  # part name -> dict (uv rect, kind, extra) for painters and weights

    # ------------------------------------------------------------------ primitives
    def vert(self, co, part):
        self.verts.append(Vector(co))
        self.part.append(part)
        return len(self.verts) - 1

    def face(self, idx, uv, region=0):
        assert len(idx) == len(uv) and len(idx) >= 3
        self.faces.append(tuple(idx))
        self.uvs.append(tuple(tuple(map(float, t)) for t in uv))
        self.region.append(region)

    # ------------------------------------------------------------------ lofted body
    def loft(self, part, centers, rx, rz, n, uv_rect, *, up=UP, cap_start="point", cap_end="point",
             sq=2.0, region=0, start_angle=0.0, tip_start=None, tip_end=None, info=None):
        """Loft rings along `centers` (Vectors). Ring k starts at the top (+up) and runs toward +side.

        uv: u = ring angle / 2pi across uv_rect (u0..u1), v = arc length along the centres (v0..v1).
        Caps: 'point' (a tip vertex, given by tip_start/tip_end or the end centre), or None (open).
        Returns (rings, tips) as vertex indices.
        """
        m = len(centers)
        assert m >= 2 and len(rx) == m and len(rz) == m
        u0, v0, u1, v1 = uv_rect
        # arc length for v
        acc = [0.0]
        for i in range(1, m):
            acc.append(acc[-1] + (centers[i] - centers[i - 1]).length)
        total = acc[-1] or 1.0
        rings = []
        frames = []
        for i in range(m):
            if i == 0:
                t = centers[1] - centers[0]
            elif i == m - 1:
                t = centers[-1] - centers[-2]
            else:
                t = centers[i + 1] - centers[i - 1]
            t.normalize()
            side = t.cross(up)
            if side.length < 1e-6:
                side = t.cross(Vector((0, 1, 0)))
            side.normalize()
            upv = side.cross(t).normalized()
            frames.append((t, side, upv))
            ring = []
            for k in range(n):
                a = start_angle + 2.0 * math.pi * k / n
                ca, sa = math.cos(a), math.sin(a)
                e = 2.0 / sq
                cx = math.copysign(abs(sa) ** e, sa)   # side component (k grows toward +side)
                cz = math.copysign(abs(ca) ** e, ca)   # up component (k=0 at the top)
                p = centers[i] + side * (rx[i] * cx) + upv * (rz[i] * cz)
                ring.append(self.vert(p, part))
            rings.append(ring)
        for i in range(m - 1):
            va, vb = v0 + (v1 - v0) * acc[i] / total, v0 + (v1 - v0) * acc[i + 1] / total
            for k in range(n):
                k2 = (k + 1) % n
                ua = u0 + (u1 - u0) * k / n
                ub = u0 + (u1 - u0) * (k + 1) / n
                # winding: outward normals (ring runs top -> +side; forward is +t)
                self.face((rings[i][k], rings[i + 1][k], rings[i + 1][k2], rings[i][k2]),
                          ((ua, va), (ua, vb), (ub, vb), (ub, va)), region)
        tips = [None, None]
        if cap_start == "point":
            tp = tip_start if tip_start is not None else centers[0] - frames[0][0] * 0.0
            ti = self.vert(tp, part)
            tips[0] = ti
            for k in range(n):
                k2 = (k + 1) % n
                ua = u0 + (u1 - u0) * k / n
                ub = u0 + (u1 - u0) * (k + 1) / n
                self.face((ti, rings[0][k], rings[0][k2]), (((ua + ub) / 2, v0), (ua, v0), (ub, v0)), region)
        if cap_end == "point":
            tp = tip_end if tip_end is not None else centers[-1]
            ti = self.vert(tp, part)
            tips[1] = ti
            for k in range(n):
                k2 = (k + 1) % n
                ua = u0 + (u1 - u0) * k / n
                ub = u0 + (u1 - u0) * (k + 1) / n
                self.face((ti, rings[-1][k2], rings[-1][k]), (((ua + ub) / 2, v1), (ub, v1), (ua, v1)), region)
        self.meta[part] = dict(kind="loft", uv=uv_rect, n=n, m=m, info=info or {})
        return rings, tips

    # ------------------------------------------------------------------ cards (alpha-tested, double-sided)
    def card(self, part, p00, p10, p11, p01, uv_rect, *, nu=1, nv=1, region=1, bend=None, flip_u=False, info=None):
        """Bilinear patch p00 (u0,v0) .. p11 (u1,v1), subdivided nu x nv. `bend(u,v)->Vector` offsets interior points."""
        u0, v0, u1, v1 = uv_rect
        if flip_u:
            u0, u1 = u1, u0
        grid = []
        for j in range(nv + 1):
            row = []
            fv = j / nv
            for i in range(nu + 1):
                fu = i / nu
                p = (p00 * (1 - fu) * (1 - fv) + p10 * fu * (1 - fv) + p11 * fu * fv + p01 * (1 - fu) * fv)
                if bend is not None:
                    p = p + bend(fu, fv)
                row.append(self.vert(p, part))
            grid.append(row)
        for j in range(nv):
            for i in range(nu):
                a, b, c, d = grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]
                uvs = []
                for (ii, jj) in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                    uvs.append((u0 + (u1 - u0) * ii / nu, v0 + (v1 - v0) * jj / nv))
                self.face((a, b, c, d), uvs, region)
        self.meta.setdefault(part, dict(kind="card", uv=uv_rect, info=info or {}))
        return grid

    # ------------------------------------------------------------------ cone (beaks)
    def cone(self, part, base_center, tip, radius, n, uv_rect, *, up=UP, region=0, rz=None):
        t = (tip - base_center).normalized()
        side = t.cross(up)
        if side.length < 1e-6:
            side = t.cross(Vector((0, 1, 0)))
        side.normalize()
        upv = side.cross(t).normalized()
        u0, v0, u1, v1 = uv_rect
        ring = []
        for k in range(n):
            a = 2 * math.pi * k / n
            p = base_center + side * (radius * math.sin(a)) + upv * ((rz or radius) * math.cos(a))
            ring.append(self.vert(p, part))
        ti = self.vert(tip, part)
        for k in range(n):
            k2 = (k + 1) % n
            ua = u0 + (u1 - u0) * k / n
            ub = u0 + (u1 - u0) * (k + 1) / n
            self.face((ring[k], ti, ring[k2]), ((ua, v0), ((ua + ub) / 2, v1), (ub, v0)), region)
        self.meta.setdefault(part, dict(kind="cone", uv=uv_rect, info={}))
        return ring, ti

    # ------------------------------------------------------------------ to Blender
    def build(self, smooth=True):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        me.update(calc_edges=True)
        uvl = me.uv_layers.new(name="UVMap")
        flat = []
        for poly, uv in zip(me.polygons, self.uvs):
            assert len(uv) == poly.loop_total
            for t in uv:
                flat.extend(t)
        uvl.data.foreach_set("uv", flat)
        me.polygons.foreach_set("use_smooth", [bool(smooth)] * len(me.polygons))
        attr = me.attributes.new("xex_part", "INT", "POINT")
        attr.data.foreach_set("value", [int(p) for p in self.part])
        reg = me.attributes.new("xex_region", "INT", "FACE")
        reg.data.foreach_set("value", [int(r) for r in self.region])
        me.validate(clean_customdata=False)
        obj = bpy.data.objects.new(self.name, me)
        link(obj)
        return obj


# ================================================================================================ armature
def make_armature(name, bones):
    """bones: list of dicts {name, head, tail, parent, roll(deg)=0, deform=True}. Returns the armature object."""
    arm = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm)
    link(obj)
    activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for b in bones:
        e = arm.edit_bones.new(b["name"])
        e.head = Vector(b["head"])
        e.tail = Vector(b["tail"])
        e.roll = math.radians(b.get("roll", 0.0))
        e.use_deform = b.get("deform", True)
        eb[b["name"]] = e
    for b in bones:
        if b.get("parent"):
            eb[b["name"]].parent = eb[b["parent"]]
            eb[b["name"]].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in obj.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return obj


def bind(mesh_obj, arm_obj, weights):
    """weights: list (per vertex) of dict bone->w. Normalises, prunes < 0.01, keeps the top 4."""
    groups = {b.name: mesh_obj.vertex_groups.new(name=b.name) for b in arm_obj.data.bones if b.use_deform}
    for vi, wd in enumerate(weights):
        items = sorted(((w, b) for b, w in wd.items() if w > 0 and b in groups), reverse=True)[:4]
        s = sum(w for w, _ in items)
        if s <= 0:
            raise RuntimeError(f"{mesh_obj.name}: vertex {vi} has no weight")
        items = [(w / s, b) for w, b in items]
        items = [(w, b) for w, b in items if w >= 0.01]
        s = sum(w for w, _ in items)
        for w, b in items:
            groups[b].add([vi], w / s, "REPLACE")
    mesh_obj.parent = arm_obj
    mesh_obj.matrix_parent_inverse = Matrix.Identity(4)
    mod = mesh_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm_obj
    return mesh_obj


def seg_param(p, a, b):
    ab = b - a
    L2 = ab.length_squared or 1e-12
    t = max(0.0, min(1.0, (p - a).dot(ab) / L2))
    return t, (a + ab * t - p).length


def nearest_weights(p, bone_segs, names, power=4.0, eps=0.004):
    """Inverse-distance weights to bone segments (names subset of bone_segs)."""
    ws = {}
    for n in names:
        a, b = bone_segs[n]
        _, d = seg_param(p, a, b)
        ws[n] = 1.0 / (d + eps) ** power
    s = sum(ws.values())
    return {k: v / s for k, v in ws.items()}


def chain_weights(coord, stations):
    """Linear blend along a 1-D coordinate. stations: list of (coord, bone) sorted by coord."""
    if coord <= stations[0][0]:
        return {stations[0][1]: 1.0}
    if coord >= stations[-1][0]:
        return {stations[-1][1]: 1.0}
    for (c0, b0), (c1, b1) in zip(stations, stations[1:]):
        if c0 <= coord <= c1:
            t = (coord - c0) / ((c1 - c0) or 1e-9)
            t = t * t * (3 - 2 * t)
            if b0 == b1:
                return {b0: 1.0}
            return {b0: 1.0 - t, b1: t}
    return {stations[-1][1]: 1.0}


def bone_segments(arm_obj):
    return {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm_obj.data.bones}


# ================================================================================================ animation
def q_arm(arm_obj, bone_name, axis, angle_rad):
    """Rotation about an armature-space axis, expressed in the bone's local (rest) frame."""
    rest = arm_obj.data.bones[bone_name].matrix_local.to_quaternion()
    qa = Quaternion(Vector(axis).normalized(), angle_rad)
    return rest.inverted() @ qa @ rest


def v_arm(arm_obj, bone_name, vec):
    """Armature-space translation expressed in the bone's local frame (for location keys)."""
    rest = arm_obj.data.bones[bone_name].matrix_local.to_3x3()
    return rest.inverted() @ Vector(vec)


def write_clip(arm_obj, name, nframes, pose_fn, *, loop=True, markers=None, meta=None):
    """Bake a clip: pose_fn(frame_index, t01) -> (rot: {bone: Quaternion local}, loc: {bone: Vector local}).

    Loops store nframes+1 keys (the last equals the first) so a skeletal AnimationGroup loops seamlessly; the
    VAT bake uses frames 0..nframes-1. One-shots store nframes keys (0..nframes-1).
    """
    if name in bpy.data.actions:
        bpy.data.actions.remove(bpy.data.actions[name])
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new(id_type="OBJECT", name=arm_obj.name)
    ad = arm_obj.animation_data or arm_obj.animation_data_create()
    ad.action = act
    ad.action_slot = slot
    cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)
    nkeys = nframes + 1 if loop else nframes
    rot_tracks, loc_tracks = {}, {}
    for f in range(nkeys):
        ff = f % nframes if loop else f
        t01 = ff / nframes if loop else (ff / max(1, nframes - 1))
        rot, loc = pose_fn(ff, t01)
        for b, q in rot.items():
            rot_tracks.setdefault(b, []).append(q.normalized())
        for b, v in (loc or {}).items():
            loc_tracks.setdefault(b, []).append(Vector(v))
    xs = [float(i) for i in range(nkeys)]
    for b, qs in rot_tracks.items():
        assert len(qs) == nkeys, (name, b, len(qs), nkeys)
        for i in range(1, len(qs)):          # hemisphere continuity
            if qs[i].dot(qs[i - 1]) < 0:
                qs[i] = -qs[i]
        dp = f'pose.bones["{b}"].rotation_quaternion'
        for i in range(4):
            fc = cb.fcurves.new(dp, index=i, group_name=b)
            fc.keyframe_points.add(nkeys)
            fc.keyframe_points.foreach_set("co", [v for pair in zip(xs, [q[i] for q in qs]) for v in pair])
            fc.keyframe_points.foreach_set("interpolation", [1] * nkeys)
            fc.update()
    for b, vs in loc_tracks.items():
        dp = f'pose.bones["{b}"].location'
        for i in range(3):
            fc = cb.fcurves.new(dp, index=i, group_name=b)
            fc.keyframe_points.add(nkeys)
            fc.keyframe_points.foreach_set("co", [v for pair in zip(xs, [p[i] for p in vs]) for v in pair])
            fc.keyframe_points.foreach_set("interpolation", [1] * nkeys)
            fc.update()
    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = nkeys - 1
    act.use_cyclic = bool(loop)
    events = []
    for mk, frame in (markers or {}).items():
        try:
            m = act.pose_markers.new(mk)
            m.frame = int(frame)
        except Exception:  # noqa: BLE001 - markers are optional; the sidecar keeps the events
            pass
        events.append({"id": mk, "frame": int(frame), "t_ms": round(int(frame) / C.FPS * 1000)})
    info = {"loop": bool(loop), "frames": nframes, "keys": nkeys,
            "duration_ms": round((nframes if loop else nframes - 1) / C.FPS * 1000),
            "events": events, "bones": sorted(set(rot_tracks) | set(loc_tracks))}
    info.update(meta or {})
    act["xex_clip"] = str(info)
    return act, info


def wave(t, phase=0.0):
    return math.sin(2 * math.pi * (t - phase))


def skew_wave(t, k=0.35):
    """Periodic wave with a faster first part (downstroke): fraction k of the cycle goes +1 -> -1."""
    t = t % 1.0
    if t < k:
        return math.cos(math.pi * t / k)
    return -math.cos(math.pi * (t - k) / (1 - k))


# ================================================================================================ numpy painting
class Canvas:
    """RGBA float canvas in sRGB-encoded values (what an 8-bit sRGB PNG stores)."""

    def __init__(self, w, h, fill=(0.5, 0.5, 0.5, 0.0)):
        self.w, self.h = w, h
        self.a = np.zeros((h, w, 4), dtype=np.float32)
        self.a[:] = fill

    def rect_px(self, uv_rect):
        u0, v0, u1, v1 = uv_rect
        x0, x1 = int(round(min(u0, u1) * self.w)), int(round(max(u0, u1) * self.w))
        y0, y1 = int(round(min(v0, v1) * self.h)), int(round(max(v0, v1) * self.h))
        return x0, y0, x1, y1

    def region_coords(self, uv_rect):
        """Pixel-centre parametric coords (fu, fv in 0..1) for a uv rect; v up (Blender UV origin bottom-left)."""
        x0, y0, x1, y1 = self.rect_px(uv_rect)
        xs = (np.arange(x0, x1) + 0.5) / self.w
        ys = (np.arange(y0, y1) + 0.5) / self.h
        u0, v0, u1, v1 = uv_rect
        fu = (xs - u0) / (u1 - u0)
        fv = (ys - v0) / (v1 - v0)
        FU, FV = np.meshgrid(fu, fv)
        return (x0, y0, x1, y1), FU, FV

    def put(self, box, rgba):
        x0, y0, x1, y1 = box
        self.a[y0:y1, x0:x1] = rgba

    def to_image(self, name, colorspace="sRGB"):
        img = bpy.data.images.get(name)
        if img:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, self.w, self.h, alpha=True, float_buffer=False)
        img.colorspace_settings.name = colorspace
        img.alpha_mode = "STRAIGHT"
        img.pixels.foreach_set(np.clip(self.a, 0, 1).astype(np.float32).ravel())
        return img


def save_image(img, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    return path


def value_noise(FU, FV, seed, freq_u, freq_v, wrap_u=False, octaves=3, gain=0.5):
    """Smooth value noise (fBm) in parametric space; wrap_u makes it periodic around a loft."""
    rng = np.random.default_rng(seed)
    out = np.zeros_like(FU)
    amp, norm = 1.0, 0.0
    fu_, fv_ = freq_u, freq_v
    for _ in range(octaves):
        nu, nv = max(1, int(round(fu_))), max(1, int(round(fv_)))
        grid = rng.random((nv + 2, nu + 2)).astype(np.float32)
        if wrap_u:
            grid[:, nu] = grid[:, 0]
            grid[:, nu + 1] = grid[:, 1]
        x = (FU % 1.0 if wrap_u else np.clip(FU, 0, 1)) * nu
        y = np.clip(FV, 0, 1) * nv
        xi, yi = np.floor(x).astype(int), np.floor(y).astype(int)
        xf, yf = x - xi, y - yi
        xf = xf * xf * (3 - 2 * xf)
        yf = yf * yf * (3 - 2 * yf)
        xi = np.clip(xi, 0, nu)
        yi = np.clip(yi, 0, nv)
        a = grid[yi, xi]
        b = grid[yi, xi + 1]
        c = grid[yi + 1, xi]
        d = grid[yi + 1, xi + 1]
        out += amp * ((a * (1 - xf) + b * xf) * (1 - yf) + (c * (1 - xf) + d * xf) * yf)
        norm += amp
        amp *= gain
        fu_ *= 2.0
        fv_ *= 2.0
    return out / norm


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


def srgb(h):
    return np.array(C.hex_to_srgb(h), dtype=np.float32)


def ring_angle(FU, start_angle=0.0):
    """Parametric u -> ring angle; 0 = top of the body, 0.5 turn = belly."""
    return (FU * 2 * math.pi + start_angle) % (2 * math.pi)


def topness(FU):
    """1 at the top of a loft ring, 0 at the belly (cosine of the ring angle mapped to 0..1)."""
    return 0.5 + 0.5 * np.cos(FU * 2 * math.pi)


def dilate_alpha_rgb(arr, iterations=6):
    """Bleed RGB of opaque texels into transparent ones so mips never pull in the fill colour."""
    rgb = arr[..., :3].copy()
    a = arr[..., 3] > 0.01
    filled = a.copy()
    for _ in range(iterations):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(a.shape, dtype=np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh_f = np.roll(filled, (dy, dx), axis=(0, 1))
            sh_c = np.roll(rgb, (dy, dx), axis=(0, 1))
            acc += sh_c * sh_f[..., None]
            cnt += sh_f
        grow = (~filled) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][..., None]
        filled = filled | grow
    arr[..., :3] = rgb
    return arr


# ================================================================================================ materials
def gltf_output_group():
    g = bpy.data.node_groups.get("glTF Material Output")
    if g is None:
        g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        g.interface.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    return g


def runtime_material(name, albedo, orm=None, normal=None, cutoff=None, double_sided=False, emissive=None,
                     emissive_strength=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    t_alb = nt.nodes.new("ShaderNodeTexImage")
    t_alb.image = albedo
    t_alb.interpolation = "Linear"
    nt.links.new(t_alb.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    if orm is not None:
        t_orm = nt.nodes.new("ShaderNodeTexImage")
        t_orm.image = orm
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(t_orm.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = gltf_output_group()
        nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.8
        bsdf.inputs["Metallic"].default_value = 0.0
    if normal is not None:
        t_n = nt.nodes.new("ShaderNodeTexImage")
        t_n.image = normal
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.space = "TANGENT"
        nm.uv_map = "UVMap"
        nt.links.new(t_n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if cutoff is not None:
        lt = nt.nodes.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        nt.links.new(t_alb.outputs["Alpha"], lt.inputs[0])
        lt.inputs[1].default_value = cutoff
        sub = nt.nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[0].default_value = 1.0
        nt.links.new(lt.outputs["Value"], sub.inputs[1])
        nt.links.new(sub.outputs["Value"], bsdf.inputs["Alpha"])
    if emissive is not None:
        t_e = nt.nodes.new("ShaderNodeTexImage")
        t_e.image = emissive
        nt.links.new(t_e.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emissive_strength
    mat.use_backface_culling = not double_sided
    mat["xex_double_sided"] = bool(double_sided)
    return mat


def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
