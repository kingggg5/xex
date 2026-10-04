"""Animation toolkit for hero 02 (runs inside Blender 5.2; mathutils only, no constraints, no add-ons).

Poses are dicts {bone: Quaternion} of local rotations relative to the rest pose (= pose_bone.rotation_quaternion)
plus an optional hips translation in bone space. Everything else (FK, world-space edits, IK, retarget, secondary
chains, procedural twist) is plain math on the rest matrices, so it is deterministic and fast.
"""
from __future__ import annotations

import math

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix, Quaternion, Vector

UP = Vector((0, 0, 1))
DOWN = Vector((0, 0, -1))
FWD = Vector((0, -1, 0))     # the character faces Blender -Y
LEFT = Vector((1, 0, 0))     # character's left = Blender +X


def q_axis(axis, deg):
    return Quaternion(Vector(axis).normalized(), math.radians(deg))


def rot_between(a: Vector, b: Vector) -> Quaternion:
    a = a.normalized()
    b = b.normalized()
    return a.rotation_difference(b)


def swing_twist(q: Quaternion, axis: Vector):
    """Split q into swing * twist with twist about `axis` (unit). Returns (swing, twist, twist_angle_rad)."""
    a = axis.normalized()
    p = Vector((q.x, q.y, q.z)).dot(a)
    tw = Quaternion((q.w, a.x * p, a.y * p, a.z * p))
    if tw.magnitude < 1e-9:
        tw = Quaternion()
    else:
        tw.normalize()
    sw = q @ tw.inverted()
    ang = 2 * math.atan2(p, q.w)
    if ang > math.pi:
        ang -= 2 * math.pi
    if ang < -math.pi:
        ang += 2 * math.pi
    return sw, tw, ang


def slerp(a: Quaternion, b: Quaternion, t: float) -> Quaternion:
    if a.dot(b) < 0:
        b = -b
    return a.slerp(b, t)


def ease(kind: str, t: float) -> float:
    t = min(1.0, max(0.0, t))
    if kind == "linear":
        return t
    if kind == "in":          # slow start (wind-up)
        return t * t * t
    if kind == "out":         # fast start, slow end (release / recovery)
        return 1 - (1 - t) ** 3
    if kind == "inout":
        return 3 * t * t - 2 * t * t * t
    if kind == "snap":        # very fast then settle (strike)
        return 1 - (1 - t) ** 5
    if kind == "back":        # overshoot past the target then settle
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
    raise ValueError(kind)


class Skeleton:
    def __init__(self, arm_obj):
        self.obj = arm_obj
        bones = arm_obj.data.bones
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.rest = {b.name: arm_obj.matrix_world @ b.matrix_local for b in bones}
        self.rest_rel = {}
        for b in bones:
            p = self.parent[b.name]
            self.rest_rel[b.name] = (self.rest[p].inverted() @ self.rest[b.name]) if p else self.rest[b.name].copy()
        order, seen = [], set()

        def visit(n):
            if n in seen:
                return
            p = self.parent[n]
            if p:
                visit(p)
            seen.add(n)
            order.append(n)
        for b in bones:
            visit(b.name)
        self.order = order
        self.length = {b.name: b.length for b in bones}
        self.names = set(self.parent)

    # ------------------------------------------------------------------ forward kinematics
    def fk(self, pose: dict, hips_loc: Vector | None = None, only=None) -> dict:
        M = {}
        for n in self.order:
            p = self.parent[n]
            base = (M[p] if p else Matrix.Identity(4)) @ self.rest_rel[n]
            q = pose.get(n)
            if n == "hips" and hips_loc is not None:
                base = base @ Matrix.Translation(hips_loc)
            M[n] = base @ (q.to_matrix().to_4x4() if q is not None else Matrix.Identity(4))
        return M

    def world_rot(self, M, n) -> Quaternion:
        return M[n].to_quaternion()

    def local_for_world(self, M, n, W: Quaternion, hips_loc=None) -> Quaternion:
        p = self.parent[n]
        base = (M[p] if p else Matrix.Identity(4)) @ self.rest_rel[n]
        return (base.to_quaternion().inverted() @ W).normalized()

    def hips_loc_for_world(self, M, P: Vector) -> Vector:
        base = M["root"] @ self.rest_rel["hips"]
        return base.inverted() @ P

    # ------------------------------------------------------------------ pose edits (world space)
    def rotate_world(self, pose, hips_loc, n, axis, deg):
        """Rotate bone n about a world axis through its head; its children follow."""
        M = self.fk(pose, hips_loc)
        W = q_axis(axis, deg) @ M[n].to_quaternion()
        pose[n] = self.local_for_world(M, n, W)
        return pose

    def set_world(self, pose, hips_loc, n, W: Quaternion):
        M = self.fk(pose, hips_loc)
        pose[n] = self.local_for_world(M, n, W)
        return pose

    def aim(self, pose, hips_loc, n, direction: Vector, weight=1.0):
        """Rotate bone n minimally so its Y axis points along `direction` (world)."""
        M = self.fk(pose, hips_loc)
        cur = M[n].to_quaternion()
        y = cur @ Vector((0, 1, 0))
        d = rot_between(y, direction)
        if weight < 1.0:
            d = Quaternion().slerp(d, weight)
        pose[n] = self.local_for_world(M, n, d @ cur)
        return pose

    def head(self, M, n) -> Vector:
        return M[n].translation.copy()

    def tail(self, M, n) -> Vector:
        return (M[n] @ Vector((0, self.length[n], 0)))

    def ik2(self, pose, hips_loc, upper, lower, end, target: Vector, pole: Vector):
        """Analytic two-bone IK: place the head of `end` at `target`, elbow/knee bending toward `pole` (world)."""
        M = self.fk(pose, hips_loc)
        a = self.head(M, upper)
        b = self.head(M, lower)
        c = self.head(M, end)
        l1 = (b - a).length
        l2 = (c - b).length
        t = target - a
        dist = min(max(t.length, 1e-4), (l1 + l2) * 0.9995)
        tdir = t.normalized()
        # elbow position: law of cosines
        cos_a = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
        cos_a = max(-1.0, min(1.0, cos_a))
        ang = math.acos(cos_a)
        pole_dir = (pole - tdir * pole.dot(tdir))
        if pole_dir.length < 1e-6:
            pole_dir = Vector((0, 0, -1)) - tdir * (-tdir.z)
        pole_dir.normalize()
        elbow = a + (tdir * math.cos(ang) + pole_dir * math.sin(ang)) * l1
        # upper: aim from a to elbow, keep twist by minimal rotation of its current orientation
        W_up = M[upper].to_quaternion()
        y_up = W_up @ Vector((0, 1, 0))
        W_up = rot_between(y_up, elbow - a) @ W_up
        pose[upper] = self.local_for_world(M, upper, W_up)
        M = self.fk(pose, hips_loc)
        W_lo = M[lower].to_quaternion()
        y_lo = W_lo @ Vector((0, 1, 0))
        reach = a + tdir * dist
        W_lo = rot_between(y_lo, reach - self.head(M, lower)) @ W_lo
        pose[lower] = self.local_for_world(M, lower, W_lo)
        return pose


# ---------------------------------------------------------------------- retargeting
class SourceClip:
    """World-space bone rotations and hips positions of a source armature, sampled per frame."""

    def __init__(self, arm_obj, action, frames, bone_names):
        scn = bpy.context.scene
        ad = arm_obj.animation_data or arm_obj.animation_data_create()
        ad.action = action
        if action.slots:
            ad.action_slot = action.slots[0]
        self.frames = []
        mw = arm_obj.matrix_world
        for f in frames:
            if isinstance(f, float):
                scn.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
            else:
                scn.frame_set(f)
            row = {}
            for n in bone_names:
                pb = arm_obj.pose.bones.get(n)
                if pb is None:
                    continue
                m = mw @ pb.matrix
                row[n] = (m.to_quaternion(), m.translation.copy())
            self.frames.append(row)
        self.rest = {}
        for n in bone_names:
            b = arm_obj.data.bones.get(n)
            if b is not None:
                m = mw @ b.matrix_local
                self.rest[n] = (m.to_quaternion(), m.translation.copy(), (m.to_3x3() @ Vector((0, 1, 0))).normalized())


RETARGET_LOG = []


def retarget(sk: Skeleton, src: SourceClip, mapping: dict, hips_src: str, hip_scale: float,
             match_overrides: dict | None = None, in_place=True, delta_bones=("hips",)):
    """World-delta retarget: W_t(f) = S(f) * S_match^-1 * T_rest, with S_match = R(dir_S -> dir_T) * S_rest.

    Limb bones copy the source's world directions (the T-pose -> A-pose difference is absorbed by the direction
    match). `delta_bones` (the pelvis by default) and any pair whose rest directions are more than 100 degrees apart
    (for example a pelvis bone pointing down in the source and up in XS1) use the plain world delta from rest
    instead, because a 180 degree direction match has no defined axis and would flip the pelvis.
    Returns a list of (pose, hips_loc) per frame."""
    match = {}
    RETARGET_LOG.clear()
    for s_name, t_name in mapping.items():
        if s_name not in src.rest or t_name not in sk.names:
            continue
        s_rot, _, s_dir = src.rest[s_name]
        t_rest = sk.rest[t_name]
        t_dir = (t_rest.to_3x3() @ Vector((0, 1, 0))).normalized()
        ang = math.degrees(s_dir.angle(t_dir))
        if t_name in delta_bones or ang > 100.0:
            A = Quaternion()
            RETARGET_LOG.append((t_name, round(ang, 1), "delta"))
        else:
            A = rot_between(s_dir, t_dir)
            RETARGET_LOG.append((t_name, round(ang, 1), "direction"))
        if match_overrides and t_name in match_overrides:
            A = match_overrides[t_name] @ A
        match[t_name] = (s_name, (A @ s_rot), t_rest.to_quaternion())
    order = [n for n in sk.order if n in match]
    p_src_rest = src.rest[hips_src][1]
    p_t_rest = sk.rest["hips"].translation.copy()
    out = []
    first = None
    for row in src.frames:
        pose = {}
        hips_world = p_t_rest + (row[hips_src][1] - p_src_rest) * hip_scale
        if first is None:
            first = hips_world.copy()
        if in_place:
            hips_world = Vector((p_t_rest.x, p_t_rest.y, hips_world.z))
        M = sk.fk(pose, None)
        hips_loc = sk.hips_loc_for_world(M, hips_world)
        for t_name in order:
            s_name, s_match, t_rest_rot = match[t_name]
            S = row[s_name][0]
            W = S @ s_match.inverted() @ t_rest_rot
            M = sk.fk(pose, hips_loc)
            pose[t_name] = sk.local_for_world(M, t_name, W)
        out.append((pose, hips_loc))
    return out


def continuity(frames):
    """Keep quaternion signs continuous across frames (avoids long-way interpolation)."""
    prev = {}
    for pose, _ in frames:
        for n, q in pose.items():
            p = prev.get(n)
            if p is not None and p.dot(q) < 0:
                pose[n] = -q
            prev[n] = pose[n]
    return frames


# ---------------------------------------------------------------------- procedural channels
def apply_twist_and_pauldron(sk: Skeleton, frames):
    for pose, hips_loc in frames:
        for s in ("L", "R"):
            ua = pose.get(f"upper_arm.{s}", Quaternion())
            _, _, tw = swing_twist(ua, Vector((0, 1, 0)))
            pose[f"upper_arm_twist.{s}"] = Quaternion(Vector((0, 1, 0)), -0.5 * tw)
            hd = pose.get(f"hand.{s}", Quaternion())
            _, _, tw2 = swing_twist(hd, Vector((0, 1, 0)))
            pose[f"forearm_twist.{s}"] = Quaternion(Vector((0, 1, 0)), 0.6 * tw2)
            # pauldron follows 40 % of the upper-arm swing (world space), clamped to 50 degrees
            M = sk.fk(pose, hips_loc)
            sh = M[f"shoulder.{s}"]
            rest_ua = sh @ sk.rest_rel[f"upper_arm.{s}"]
            d_rest = (rest_ua.to_3x3() @ Vector((0, 1, 0))).normalized()
            d_now = (M[f"upper_arm.{s}"].to_3x3() @ Vector((0, 1, 0))).normalized()
            sw = rot_between(d_rest, d_now)
            ang = math.degrees(sw.angle)
            k = 0.4 if ang * 0.4 <= 50 else 50 / max(ang, 1e-6)
            W_pd_rest = (sh @ sk.rest_rel[f"pauldron.{s}"]).to_quaternion()
            pose[f"pauldron.{s}"] = sk.local_for_world(M, f"pauldron.{s}", Quaternion().slerp(sw, k) @ W_pd_rest)
    return frames


def _thigh_angles(sk, M, s):
    """Flexion (+forward) and abduction (+outward) of the thigh relative to the hips, degrees."""
    hips = M["hips"]
    rest_th = hips @ sk.rest_rel[f"thigh.{s}"]
    d_rest = (rest_th.to_3x3() @ Vector((0, 1, 0))).normalized()
    d_now = (M[f"thigh.{s}"].to_3x3() @ Vector((0, 1, 0))).normalized()
    hq = hips.to_quaternion()
    fwd = hq @ (sk.rest["hips"].to_quaternion().inverted() @ FWD)
    lat = hq @ (sk.rest["hips"].to_quaternion().inverted() @ LEFT)
    if s == "R":
        lat = -lat
    flex = math.degrees(math.atan2(d_now.dot(fwd), -d_now.dot(hq @ (sk.rest["hips"].to_quaternion().inverted() @ UP)))) \
        - math.degrees(math.atan2(d_rest.dot(fwd), -d_rest.dot(hq @ (sk.rest["hips"].to_quaternion().inverted() @ UP))))
    abd = math.degrees(math.asin(max(-1, min(1, d_now.dot(lat))))) - math.degrees(math.asin(max(-1, min(1, d_rest.dot(lat)))))
    return flex, abd


def apply_skirt(sk: Skeleton, frames, fps=30, gain=1.0, loop=False):
    """Driven robe chains (rig doc 3.5): F follows the larger thigh flexion, B the larger extension, L/R the abduction
    plus some flexion of their own thigh; the .02 joints take half of the parent's swing with a critically damped lag."""
    lag_state = {}
    omega = 18.0
    dt = 1.0 / fps
    passes = 2 if loop else 1
    result = None
    for p in range(passes):
        for fi, (pose, hips_loc) in enumerate(frames):
            M = sk.fk(pose, hips_loc)
            fl, al = _thigh_angles(sk, M, "L")
            fr, ar = _thigh_angles(sk, M, "R")
            hq = M["hips"].to_quaternion()
            hr = sk.rest["hips"].to_quaternion().inverted()
            lat = hq @ (hr @ LEFT)
            fwd = hq @ (hr @ FWD)
            targets = {
                "skirt.F.01": (lat, -min(75, max(0.0, 0.62 * max(fl, fr))) * gain),
                "skirt.B.01": (lat, min(75, max(0.0, 0.62 * max(-fl, -fr))) * gain),
                "skirt.L.01": (fwd, -min(75, max(0.0, 0.7 * al + 0.3 * max(0, fl))) * gain),
                "skirt.R.01": (fwd, min(75, max(0.0, 0.7 * ar + 0.3 * max(0, fr))) * gain),
            }
            for name, (axis, deg) in targets.items():
                # x-axis sign: rotating about +lateral by negative angle swings the bone forward (toward -Y)
                W_rest = (M["hips"] @ sk.rest_rel[name]).to_quaternion()
                if name in ("skirt.L.01", "skirt.R.01"):
                    pass
                pose[name] = sk.local_for_world(M, name, q_axis(axis, deg) @ W_rest)
                child = name.replace(".01", ".02")
                st = lag_state.get(child, (0.0, 0.0))
                want = 0.5 * deg
                x, v = st
                # critically damped spring toward want
                a = omega * omega * (want - x) - 2 * omega * v
                v += a * dt
                x += v * dt
                lag_state[child] = (x, v)
                M2 = sk.fk(pose, hips_loc)
                W_c_rest = (M2[name] @ sk.rest_rel[child]).to_quaternion()
                pose[child] = sk.local_for_world(M2, child, q_axis(axis, x + 0.0) @ W_c_rest)
    return frames


def apply_sleeves(sk: Skeleton, frames, fps=30, influence=0.7, max_deg=70.0, loop=False):
    omega = 14.0
    dt = 1.0 / fps
    state = {}
    passes = 2 if loop else 1
    for _ in range(passes):
        for pose, hips_loc in frames:
            for s in ("L", "R"):
                name = f"sleeve.{s}.01"
                M = sk.fk(pose, hips_loc)
                W_rigid = (M[f"forearm.{s}"] @ sk.rest_rel[name]).to_quaternion()
                d_rigid = (W_rigid @ Vector((0, 1, 0))).normalized()
                full = rot_between(d_rigid, DOWN)
                ang = math.degrees(full.angle) * influence
                ang = min(ang, max_deg)
                frac = 0.0 if full.angle < 1e-6 else math.radians(ang) / full.angle
                target = Quaternion().slerp(full, frac)
                # lag on the target rotation (exponential smoothing with a critically damped feel)
                prev = state.get(s)
                if prev is None:
                    cur = target
                else:
                    k = 1 - math.exp(-omega * dt)
                    cur = slerp(prev, target, k)
                state[s] = cur
                pose[name] = sk.local_for_world(M, name, cur @ W_rigid)
    return frames


def apply_springs(sk: Skeleton, frames, chains, fps=30, loop=False, substeps=4):
    """Damped-spring tails for hair/hat chains. chains = [(bone names...), omega, zeta, gravity, max_deg]."""
    dt = 1.0 / fps / substeps
    passes = 3 if loop else 1
    states = {}
    for pass_i in range(passes):
        for fi, (pose, hips_loc) in enumerate(frames):
            for names, omega, zeta, grav, max_deg in chains:
                for n in names:
                    M = sk.fk(pose, hips_loc)
                    p = sk.parent[n]
                    W_rigid = (M[p] @ sk.rest_rel[n])
                    head = W_rigid.translation
                    tail_rigid = W_rigid @ Vector((0, sk.length[n], 0))
                    st = states.get(n)
                    if st is None:
                        st = [tail_rigid.copy(), Vector((0, 0, 0))]
                    pos, vel = st
                    for _ in range(substeps):
                        acc = (tail_rigid - pos) * (omega * omega) - vel * (2 * zeta * omega) + Vector((0, 0, -grav))
                        vel = vel + acc * dt
                        pos = pos + vel * dt
                    # keep bone length
                    d = pos - head
                    if d.length < 1e-6:
                        d = tail_rigid - head
                    pos = head + d.normalized() * sk.length[n]
                    states[n] = [pos, vel]
                    d_rigid = (tail_rigid - head).normalized()
                    rot = rot_between(d_rigid, (pos - head).normalized())
                    if math.degrees(rot.angle) > max_deg:
                        rot = Quaternion().slerp(rot, max_deg / math.degrees(rot.angle))
                    pose[n] = sk.local_for_world(M, n, rot @ W_rigid.to_quaternion())
    return frames


def close_loop(frames, blend_frames=6, names=None):
    """Blend the last frames toward frame 0 so a loop closes exactly (secondary channels after simulation)."""
    n = len(frames)
    if n < 3:
        return frames
    first_pose, first_loc = frames[0]
    for k in range(1, blend_frames + 1):
        i = n - 1 - blend_frames + k
        if i <= 0:
            continue
        t = k / blend_frames
        t = t * t * (3 - 2 * t)
        pose, loc = frames[i]
        for b in (names or list(pose.keys())):
            if b in first_pose and b in pose:
                pose[b] = slerp(pose[b], first_pose[b], t)
        if loc is not None and first_loc is not None:
            frames[i] = (pose, loc.lerp(first_loc, t))
    frames[-1] = ({b: q.copy() for b, q in first_pose.items()}, first_loc.copy() if first_loc is not None else None)
    return frames


# ---------------------------------------------------------------------- writing actions (Blender 5 channelbags)
def write_action(arm_obj, name, frames, bone_names, fps=30, markers=None, loop=False):
    if name in bpy.data.actions:
        bpy.data.actions.remove(bpy.data.actions[name])
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new(id_type="OBJECT", name=arm_obj.name)
    ad = arm_obj.animation_data or arm_obj.animation_data_create()
    ad.action = act
    ad.action_slot = slot
    cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)
    n = len(frames)
    xs = [float(i) for i in range(n)]
    continuity(frames)
    for b in bone_names:
        dp = f'pose.bones["{b}"].rotation_quaternion'
        for i in range(4):
            fc = cb.fcurves.new(dp, index=i, group_name=b)
            vals = [(frames[k][0].get(b) or Quaternion())[i] for k in range(n)]
            fc.keyframe_points.add(n)
            fc.keyframe_points.foreach_set("co", [v for pair in zip(xs, vals) for v in pair])
            fc.keyframe_points.foreach_set("interpolation", [1] * n)  # LINEAR
            fc.update()
    for i in range(3):
        fc = cb.fcurves.new('pose.bones["hips"].location', index=i, group_name="hips")
        vals = [(frames[k][1] if frames[k][1] is not None else Vector())[i] for k in range(n)]
        fc.keyframe_points.add(n)
        fc.keyframe_points.foreach_set("co", [v for pair in zip(xs, vals) for v in pair])
        fc.keyframe_points.foreach_set("interpolation", [1] * n)
        fc.update()
    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = n - 1
    act.use_cyclic = bool(loop)
    events = []
    for mk_name, frame in (markers or {}).items():
        try:
            m = act.pose_markers.new(mk_name)
            m.frame = int(frame)
        except Exception:  # pose markers are optional; the sidecar keeps the events
            pass
        events.append({"id": mk_name, "frame": int(frame), "t_ms": round(int(frame) / fps * 1000)})
    act["xex_events"] = __import__("json").dumps(events)   # exported as glTF animation extras
    act["xex_fps"] = fps
    return act
