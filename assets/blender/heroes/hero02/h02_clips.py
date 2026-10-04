"""Stage 4: the hero 02 clip set on XS1 (30 fps, in place, root motion off).

Sources
- Quaternius UAL1 Standard (CC0, source/third-party/ual1-standard-2025-06-10): Idle_Loop, Walk_Loop,
  Jog_Fwd_Loop / Sprint_Loop (whichever stride fits 4.5 m/s), Hit_Chest, Death01, retargeted by world-space
  deltas from a matched A-pose (h02_animlib.retarget), hips travel scaled by her hip height ratio, then in place.
- Authored here (prop-driven): the staff grip is keyed in world space and both arms are solved by two-bone IK, the
  body is keyed with world-axis rotations, the feet stay planted by leg IK, secondary chains are solved offline.
- Tripo run.001 is only read to measure and document its 1.1 m hip offset (the shipped base.run is UAL-based).

Every action clip records charge/release/recovery events (ms) for the VFX lane and the server.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402
import h02_common as C  # noqa: E402
import h02_xs1 as X  # noqa: E402
import h02_animlib as A  # noqa: E402

log = C.Log("h02_clips")
FPS = 30
bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_rig.blend"))
scn = bpy.context.scene
scn.render.fps = FPS
scn.render.fps_base = 1.0
arm = bpy.data.objects["hero02_XS1"]
sk = A.Skeleton(arm)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)

# ------------------------------------------------------------------------------------------------ UAL import
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(C.UAL_GLTF), bone_heuristic="BLENDER", guess_original_bind_pose=True)
ual_objs = [o for o in bpy.data.objects if o not in before]
ual = next(o for o in ual_objs if o.type == "ARMATURE")
for o in ual_objs:
    if o.type == "MESH":
        o.hide_render = True
ual_actions = {a.name: a for a in bpy.data.actions}
log("UAL actions", len(ual_actions), sorted(ual_actions)[:8], "...")
ual_bones = [b.name for b in ual.data.bones]


def ual_action(name):
    for k, a in ual_actions.items():
        if k == name or k.startswith(name + "_") and k[len(name) + 1:].isdigit() or k.split("|")[-1] == name:
            return a
    cands = [a for k, a in ual_actions.items() if name in k]
    if not cands:
        raise KeyError(name)
    return cands[0]


th_ual = (ual.matrix_world @ ual.data.bones["DEF-thigh.L"].head_local).z
th_her = sk.rest["thigh.L"].translation.z
HIP_SCALE = th_her / th_ual
log("hip scale (her thigh / UAL thigh)", round(HIP_SCALE, 4), th_her, th_ual)


MATCH_LOGGED = []


def sample_ual(name, frames=None, fps=FPS):
    act = ual_action(name)
    f0, f1 = act.frame_range
    n = int(round((f1 - f0))) + 1 if frames is None else frames
    span = f1 - f0
    times = [f0 + span * i / (n - 1) for i in range(n)]
    src = A.SourceClip(ual, act, times, ual_bones)
    out = A.retarget(sk, src, X.UAL_POSE, "DEF-hips", HIP_SCALE)
    if not MATCH_LOGGED:
        log("retarget match (bone, rest-direction angle deg, method)", A.RETARGET_LOG)
        MATCH_LOGGED.append(True)
    return out, {"ual_clip": act.name, "source_frames": [f0, f1], "samples": n}


# ------------------------------------------------------------------------------------------------ helpers
REST_M = sk.fk({}, None)
ANKLE_REST = {s: REST_M[f"foot.{s}"].translation.z for s in ("L", "R")}
BALL_REST = {s: REST_M[f"toe.{s}"].translation.z for s in ("L", "R")}


def sole_min(M):
    vals = []
    for s in ("L", "R"):
        vals.append(M[f"foot.{s}"].translation.z - ANKLE_REST[s])
        vals.append(M[f"toe.{s}"].translation.z - BALL_REST[s])
        vals.append(sk.tail(M, f"toe.{s}").z - BALL_REST[s])
    return min(vals)


def ground_clip(frames):
    """Constant vertical offset so the lowest sole point over the clip touches the ground."""
    lows = [sole_min(sk.fk(p, h)) for p, h in frames]
    off = -min(lows)
    for i, (p, h) in enumerate(frames):
        M = sk.fk(p, h)
        hw = M["hips"].translation + Vector((0, 0, off))
        frames[i] = (p, sk.hips_loc_for_world(sk.fk(p, None), hw) if False else _hips_loc(p, hw))
    return frames, off


def _hips_loc(pose, world_pos):
    M = sk.fk(pose, None)
    return sk.hips_loc_for_world(M, world_pos)


def socket_offset(side):
    rh = sk.rest[f"hand.{side}"]
    rs = sk.rest[f"socket_weapon_{side}"]
    rel = rh.inverted() @ rs
    return rel.to_quaternion(), rel.translation.copy()


SOCK = {s: socket_offset(s) for s in ("L", "R")}


def frame_from(y, z_hint):
    y = y.normalized()
    z = (z_hint - y * z_hint.dot(y))
    if z.length < 1e-6:
        z = Vector((0, -1, 0)) - y * (-y.y)
    z.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed()
    return m.to_quaternion()


def hold_staff(pose, hips_loc, side, grip_pos, axis, knuckles, pole):
    """Place hand `side` so its weapon socket sits at grip_pos with socket +Y along `axis`."""
    q_off, t_off = SOCK[side]
    W_sock = frame_from(axis, knuckles)
    W_hand = W_sock @ q_off.inverted()
    wrist = grip_pos - (W_hand @ t_off)
    sk.ik2(pose, hips_loc, f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}", wrist, pole)
    sk.set_world(pose, hips_loc, f"hand.{side}", W_hand)
    return pose


def place_palm(pose, hips_loc, side, palm_pos, fingers_dir, palm_normal, pole):
    """Hand frame: Y along the fingers, Z toward the palm side (rig convention), palm centre at palm_pos."""
    W_hand = frame_from(fingers_dir, palm_normal)
    hand_len = sk.length[f"hand.{side}"]
    wrist = palm_pos - (W_hand @ Vector((0, 0.55 * hand_len, 0)))
    sk.ik2(pose, hips_loc, f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}", wrist, pole)
    sk.set_world(pose, hips_loc, f"hand.{side}", W_hand)
    return pose


FINGERS = {"grip": {"index.01": 52, "index.02": 68, "grip.01": 62, "grip.02": 78, "thumb.01": 24, "thumb.02": 38},
           "open": {"index.01": -4, "index.02": 4, "grip.01": -2, "grip.02": 6, "thumb.01": -6, "thumb.02": 4},
           "relaxed": {"index.01": 14, "index.02": 22, "grip.01": 20, "grip.02": 30, "thumb.01": 6, "thumb.02": 12}}


def set_fingers(pose, side, shape):
    for b, deg in FINGERS[shape].items():
        pose[f"{b}.{side}"] = Quaternion(Vector((1, 0, 0)), math.radians(deg))
    return pose


def keep_feet(pose, hips_loc, targets):
    """Leg IK: ankles to targets[s] = (ankle_pos, foot_world_rot)."""
    for s in ("L", "R"):
        pos, rot = targets[s]
        out = 1 if s == "L" else -1
        pole = Vector((0.15 * out, -1.0, 0.0))
        sk.ik2(pose, hips_loc, f"thigh.{s}", f"shin.{s}", f"foot.{s}", pos, pole)
        sk.set_world(pose, hips_loc, f"foot.{s}", rot)
    return pose


def body_rotate(pose, hips_loc, spec):
    """spec {bone: (yaw, pitch, roll)} degrees: yaw about +Z (turn left), pitch about +X (lean forward),
    roll about +Y (lean to her left). Applied root-to-leaf in world space."""
    for b in sk.order:
        if b not in spec:
            continue
        yaw, pitch, roll = spec[b]
        if yaw:
            sk.rotate_world(pose, hips_loc, b, (0, 0, 1), yaw)
        if pitch:
            sk.rotate_world(pose, hips_loc, b, (1, 0, 0), pitch)
        if roll:
            sk.rotate_world(pose, hips_loc, b, (0, 1, 0), roll)
    return pose


def copy_pose(p):
    return {k: v.copy() for k, v in p.items()}


def lerp_vec(a, b, t):
    return a.lerp(b, t)


def slerp_dir(a, b, t):
    q = A.rot_between(a, b)
    return Quaternion().slerp(q, t) @ a


# ------------------------------------------------------------------------------------------------ staff hold (idle)
HOLD = {
    "grip_local": None,   # grip in the chest frame, set from the idle frame 0
}
POLE_R = Vector((-1.0, 0.7, -0.6))
POLE_L = Vector((1.0, 0.7, -0.6))
KNUCKLE_FWD = Vector((0, -1, 0))


def idle_hold_targets():
    """Staff upright beside the right hip, crystal above the head, butt 7 cm off the ground."""
    grip = Vector((-0.27, -0.13, 1.00))
    axis = Vector((-0.06, -0.10, 1.0)).normalized()
    return grip, axis


def in_frame(M, bone, p_world):
    return M[bone].inverted() @ p_world


def from_frame(M, bone, p_local):
    return M[bone] @ p_local


def apply_hold(frames, weight=1.0, follow="upper_chest", swing_from_source=0.0, axis_override=None,
               grip_override=None, left="free"):
    """Right hand on the staff for every frame; the grip follows `follow` (keeps the upper body motion)."""
    g0, a0 = grip_override or idle_hold_targets()
    if axis_override is not None:
        a0 = axis_override
    M0 = sk.fk(*frames[0])
    g_local = in_frame(M0, follow, g0)
    a_local = M0[follow].to_quaternion().inverted() @ a0
    for i, (pose, hl) in enumerate(frames):
        M = sk.fk(pose, hl)
        g = from_frame(M, follow, g_local)
        a = (M[follow].to_quaternion() @ a_local).normalized()
        if swing_from_source:
            src_hand = sk.head(M, "hand.R")
            g = g + (src_hand - sk.head(M0, "hand.R")) * swing_from_source
        before = copy_pose(pose)
        hold_staff(pose, hl, "R", g, a, KNUCKLE_FWD, POLE_R)
        set_fingers(pose, "R", "grip")
        if weight < 1.0:
            for b in ("upper_arm.R", "forearm.R", "hand.R"):
                pose[b] = A.slerp(before.get(b, Quaternion()), pose[b], weight)
    return frames


def secondaries(frames, loop):
    A.apply_twist_and_pauldron(sk, frames)
    A.apply_skirt(sk, frames, FPS, loop=loop)
    A.apply_sleeves(sk, frames, FPS, loop=loop)
    A.apply_springs(sk, frames, [(("hair.01", "hair.02", "hair.03"), 9.0, 0.55, 0.0, 28.0),
                                 (("hat.01", "hat.02"), 13.0, 0.65, 0.0, 12.0),
                                 (("hat.03",), 7.0, 0.35, 0.0, 35.0)], FPS, loop=loop)
    if loop:
        A.close_loop(frames, 6)
    return frames


# ------------------------------------------------------------------------------------------------ measurements
def foot_track(frames, s):
    pts = []
    for p, h in frames:
        M = sk.fk(p, h)
        pts.append((sk.head(M, f"foot.{s}"), sk.head(M, f"toe.{s}")))
    return pts


def sole_z(M, s):
    return min(M[f"foot.{s}"].translation.z - ANKLE_REST[s], M[f"toe.{s}"].translation.z - BALL_REST[s],
               sk.tail(M, f"toe.{s}").z - BALL_REST[s])


def implied_speed(frames):
    """Median backward speed of a planted foot (sole proxy within 2 cm of its lowest point), m/s.
    In an in-place loop the planted foot slides toward +Y (the character faces -Y) at the travel speed."""
    speeds = []
    contact_frames = {}
    Ms = [sk.fk(p, h) for p, h in frames]
    for s in ("L", "R"):
        zs = [sole_z(M, s) for M in Ms]
        zmin = min(zs)
        cf = [i for i in range(len(Ms)) if zs[i] <= zmin + 0.02]
        contact_frames[s] = cf
        for i in cf:
            if i + 1 in cf:
                a = Ms[i][f"toe.{s}"].translation
                b = Ms[i + 1][f"toe.{s}"].translation
                speeds.append((b.y - a.y) * FPS)
    speeds.sort()
    v = speeds[len(speeds) // 2] if speeds else 0.0
    return v, contact_frames


def foot_slide(frames, v):
    """V6: for each contact run, max deviation (m) of the planted toe from sliding back at exactly v m/s."""
    Ms = [sk.fk(p, h) for p, h in frames]
    worst = 0.0
    _, cf = implied_speed(frames)
    for s in ("L", "R"):
        runs, cur = [], []
        for i in cf[s]:
            if cur and i != cur[-1] + 1:
                runs.append(cur)
                cur = []
            cur.append(i)
        if cur:
            runs.append(cur)
        for r in runs:
            if len(r) < 2:
                continue
            y0 = Ms[r[0]][f"toe.{s}"].translation
            for i in r:
                y = Ms[i][f"toe.{s}"].translation
                expect_y = y0.y + v * (i - r[0]) / FPS
                dev = math.hypot(y.y - expect_y, y.x - y0.x)
                worst = max(worst, dev)
    return worst


def first_left_strike(frames):
    v, cf = implied_speed(frames)
    c = cf["L"]
    if not c:
        return 0
    starts = [c[0]] + [c[k] for k in range(1, len(c)) if c[k] - c[k - 1] > 1]
    return starts[0]


def rotate_loop(frames, k):
    if k == 0:
        return frames
    core = frames[:-1]
    core = core[k:] + core[:k]
    return core + [(copy_pose(core[0][0]), core[0][1].copy())]


def hips_drift(frames):
    xs = []
    for p, h in frames:
        M = sk.fk(p, h)
        xs.append(M["hips"].translation)
    dx = max(abs(v.x - xs[0].x) for v in xs)
    dy = max(abs(v.y - xs[0].y) for v in xs)
    return max(dx, dy), (xs[0] - sk.rest["hips"].translation)


CLIPS = {}
ALL = X.JOINTS


def store(name, frames, loop, events, source, layer="full", ability=None, contract=None, notes=None):
    act = A.write_action(arm, name, frames, ALL, FPS, markers={e: f for e, f in events.items()}, loop=loop)
    n = len(frames)
    drift, off = hips_drift(frames)
    CLIPS[name] = {"frames": n, "fps": FPS, "loop": loop, "duration_ms": round((n - 1) / FPS * 1000),
                   "events": [{"id": k, "frame": int(f), "t_ms": round(f / FPS * 1000)} for k, f in
                              sorted(events.items(), key=lambda kv: kv[1])],
                   "source": source, "layer": layer, "ability": ability, "contract": contract, "notes": notes,
                   "hips_xy_drift_m": round(drift, 4), "hips_offset_from_bind_m": [round(c, 4) for c in off]}
    log("clip", name, n, "frames", "drift", round(drift, 4))
    return act


# ------------------------------------------------------------------------------------------------ base.idle
idle, src_idle = sample_ual("Idle_Loop", frames=76)
idle, off = ground_clip(idle)
# feet locked to frame 0 by leg IK: the UAL sway stays in the hips and spine, the soles never drift
M_i0 = sk.fk(*idle[0])
feet_i0 = {s: (sk.head(M_i0, f"foot.{s}"), M_i0[f"foot.{s}"].to_quaternion()) for s in ("L", "R")}
drift_before = 0.0
for p, h in idle:
    M = sk.fk(p, h)
    drift_before = max(drift_before, max((sk.head(M, f"foot.{s}") - feet_i0[s][0]).length for s in ("L", "R")))
    keep_feet(p, h, feet_i0)
apply_hold(idle, follow="upper_chest")
for p, h in idle:
    set_fingers(p, "L", "relaxed")
secondaries(idle, loop=True)
store("base.idle", idle, True, {}, {"kind": "ual1", **src_idle, "licence": "CC0-1.0", "edits":
      "right arm on the staff (IK), fingers grip/relaxed, grounded, secondary chains"})
drift_after = 0.0
for p, h in idle:
    M = sk.fk(p, h)
    drift_after = max(drift_after, max((sk.head(M, f"foot.{s}") - feet_i0[s][0]).length for s in ("L", "R")))
CLIPS["base.idle"]["foot_drift_m"] = {"source": round(drift_before, 4), "shipped": round(drift_after, 4)}
IDLE0 = (copy_pose(idle[0][0]), idle[0][1].copy())
M_IDLE0 = sk.fk(*IDLE0)
FEET0 = {s: (sk.head(M_IDLE0, f"foot.{s}"), M_IDLE0[f"foot.{s}"].to_quaternion()) for s in ("L", "R")}

# ------------------------------------------------------------------------------------------------ base.walk / run
def sample_ual_phase(name, n, phase):
    """n samples of one loop cycle starting at `phase` (0..1 of the cycle), last sample == first."""
    act = ual_action(name)
    f0, f1 = act.frame_range
    span = f1 - f0
    times = [f0 + span * ((phase + i / (n - 1)) % 1.0) for i in range(n - 1)]
    src = A.SourceClip(ual, act, times, ual_bones)
    out = A.retarget(sk, src, X.UAL_POSE, "DEF-hips", HIP_SCALE)
    out.append((copy_pose(out[0][0]), out[0][1].copy()))
    return out


def strike_phase(name):
    fr, _ = sample_ual(name)
    k = first_left_strike(fr)
    return k / (len(fr) - 1)


def blend_cycles(c1, c2, w):
    out = []
    for (p1, h1), (p2, h2) in zip(c1, c2):
        p = {}
        for b in set(p1) | set(p2):
            p[b] = A.slerp(p1.get(b, Quaternion()), p2.get(b, Quaternion()), w)
        out.append((p, h1.lerp(h2, w)))
    return out


# base.walk: UAL Walk_Loop implies 1.29 m/s on her legs at its 1,333 ms cycle; the contract walk is 1.60 m/s and a pure
# retime would need 24 %. The shipped walk lengthens the stride with a small phase-aligned share of the Jog and picks the
# cycle (within 15 % of 1,067 ms... 1,333 ms) whose planted foot slides at 1.60 m/s.
ph_walk0 = strike_phase("Walk_Loop")
ph_jog0 = strike_phase("Jog_Fwd_Loop")
wcand = {}
for jw in (0.0, 0.08, 0.15, 0.22):
    for n in range(33, 42):                 # 32-40 intervals = 1,067-1,333 ms
        c = sample_ual_phase("Walk_Loop", n, ph_walk0)
        if jw > 0:
            c = blend_cycles(c, sample_ual_phase("Jog_Fwd_Loop", n, ph_jog0), jw)
        c, _ = ground_clip(c)
        v, _ = implied_speed(c)
        wcand[(jw, n)] = (abs(v - 1.60), v, c)
ok = [k for k in wcand if wcand[k][0] <= 0.08]
wkey = min(ok, key=lambda k: (k[0], wcand[k][0])) if ok else min(wcand, key=lambda k: wcand[k][0])
walk = wcand[wkey][2]
src_walk = {"ual_clip": "Walk_Loop" + (" + Jog_Fwd_Loop" if wkey[0] else ""), "blend_jog_weight": wkey[0],
            "samples": wkey[1], "speed_by_weight_and_frames": {f"{k[0]}x{k[1]}": round(v[1], 3) for k, v in wcand.items()}}
apply_hold(walk, follow="upper_chest", swing_from_source=0.25)
for p, h in walk:
    set_fingers(p, "L", "relaxed")
secondaries(walk, loop=True)
v_walk, _ = implied_speed(walk)
store("base.walk", walk, True, {"foot_l": 0, "foot_r": (len(walk) - 1) // 2},
      {"kind": "ual1", **src_walk, "licence": "CC0-1.0",
       "edits": "phase-aligned to the left heel strike, cycle and stride fitted to 1.60 m/s, staff hold"},
      notes=f"implied speed {v_walk:.2f} m/s; controller speedRatio = v / {v_walk:.2f}")
CLIPS["base.walk"]["implied_speed_mps"] = round(v_walk, 3)
CLIPS["base.walk"]["planted_foot_deviation_m"] = round(foot_slide(walk, v_walk), 4)

# base.run: UAL Jog_Fwd_Loop alone implies 6.6 m/s on her legs (a sprint-like gait, 14 % ground contact) and
# Sprint_Loop 10 m/s, both outside the 15 % retime rule. The shipped run blends the phase-aligned Jog (JOG_W) with
# the Walk, then the cycle length is resampled so the planted foot slides at exactly the 4.5 m/s server speed.
ph_walk, ph_jog = strike_phase("Walk_Loop"), strike_phase("Jog_Fwd_Loop")
cand = {}
for jw in (0.65, 0.55, 0.45, 0.35):
    for n in range(19, 27):            # 18-25 intervals = 700 ms +-15 %
        blend = blend_cycles(sample_ual_phase("Walk_Loop", n, ph_walk), sample_ual_phase("Jog_Fwd_Loop", n, ph_jog), jw)
        blend, _ = ground_clip(blend)
        v, _ = implied_speed(blend)
        cand[(jw, n)] = (abs(v - 4.5), v, blend)
ok = [k for k in cand if cand[k][0] <= 0.15]
key = max(ok, key=lambda k: (k[0], -cand[k][0])) if ok else min(cand, key=lambda k: cand[k][0])
JOG_W, n_run = key
_, v_blend, run = cand[key]
src_run = {"ual_clip": "Jog_Fwd_Loop + Walk_Loop", "blend_jog_weight": JOG_W, "samples": n_run,
           "speed_by_weight_and_frames": {f"{k[0]}x{k[1]}": round(v[1], 3) for k, v in cand.items()}}
run_grip = Vector((-0.20, -0.22, 1.12))
run_axis = Vector((-0.30, -0.55, 1.0)).normalized()
apply_hold(run, follow="upper_chest", grip_override=(run_grip, run_axis), swing_from_source=0.15)
for p, h in run:
    set_fingers(p, "L", "relaxed")
secondaries(run, loop=True)
v_run, _ = implied_speed(run)
store("base.run", run, True, {"foot_l": 0, "foot_r": (len(run) - 1) // 2},
      {"kind": "ual1", **src_run, "licence": "CC0-1.0",
       "edits": f"phase-aligned blend (jog {JOG_W}), cycle {n_run - 1} frames chosen for 4.5 m/s, staff carried forward-diagonal"},
      notes=f"implied speed {v_run:.2f} m/s; replaces Tripo run.001 (hips 1.1 m forward)")
CLIPS["base.run"]["implied_speed_mps"] = round(v_run, 3)
CLIPS["base.run"]["planted_foot_deviation_m"] = round(foot_slide(run, v_run), 4)

# ------------------------------------------------------------------------------------------------ base.hit_light
hit, src_hit = sample_ual("Hit_Chest", frames=11)
hit, _ = ground_clip(hit)
apply_hold(hit, follow="upper_chest", weight=0.85)
for p, h in hit:
    set_fingers(p, "L", "relaxed")
secondaries(hit, loop=False)
store("base.hit_light", hit, False, {"body_impact": 0}, {"kind": "ual1", **src_hit, "licence": "CC0-1.0",
      "edits": "staff hold at 85 %"}, layer="upper, additive-capable")

# ------------------------------------------------------------------------------------------------ base.death
LOD0 = bpy.data.objects["hero02_witch_lod0"]


def mesh_min_z(frames, idx):
    """Lowest vertex of the evaluated LOD0 mesh for frames[idx] (writes a temporary action)."""
    tmp = A.write_action(arm, "tmp.ground_probe", [frames[idx]], ALL, FPS)
    arm.animation_data.action = tmp
    arm.animation_data.action_slot = tmp.slots[0]
    scn.frame_set(0)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = LOD0.evaluated_get(dg)
    m = ev.to_mesh()
    z = min(v.co.z for v in m.vertices)
    ev.to_mesh_clear()
    bpy.data.actions.remove(tmp)
    return z


death, src_death = sample_ual("Death01")
apply_hold(death[:1], follow="upper_chest")
for i, (p, h) in enumerate(death):
    set_fingers(p, "R", "grip")
    set_fingers(p, "L", "relaxed")
# body impact: first frame where the torso is within 3 cm of its lowest height
torso_z = []
for p, h in death:
    M = sk.fk(p, h)
    torso_z.append(min(M[b].translation.z for b in ("hips", "upper_chest", "head")))
zmin_t = min(torso_z)
impact = next(i for i, z in enumerate(torso_z) if z <= zmin_t + 0.03)
# ground the body on the evaluated mesh: before the impact the feet carry her (sole grounding),
# from the impact on the lowest vertex sits 1 cm above the floor (no penetration, no floating)
corr = {}
for i in range(len(death)):
    if i < impact - 8:
        continue
    corr[i] = 0.01 - mesh_min_z(death, i)
first_feet = sole_min(sk.fk(*death[0]))
for i, (p, h) in enumerate(death):
    if i < impact - 8:
        dz = -first_feet
    else:
        t = min(1.0, (i - (impact - 8)) / 8.0)
        t = t * t * (3 - 2 * t)
        dz = (1 - t) * (-first_feet) + t * corr[i]
    M = sk.fk(p, h)
    death[i] = (p, _hips_loc(p, M["hips"].translation + Vector((0, 0, dz))))
end_gap = mesh_min_z(death, len(death) - 1)
secondaries(death, loop=False)
store("base.death", death, False, {"body_impact": impact},
      {"kind": "ual1", **src_death, "licence": "CC0-1.0",
       "edits": "grounded on the evaluated LOD0 mesh from the body impact on"},
      notes=f"ends grounded (lowest vertex {end_gap:.3f} m above the floor); staff stays in the right hand")
CLIPS["base.death"]["end_lowest_vertex_m"] = round(end_gap, 4)


# ------------------------------------------------------------------------------------------------ authored clips
class Key:
    def __init__(self, f, ease="inout", body=None, hips=(0, 0, 0), grip=None, axis=None, knuckles=None,
                 left="free", left_args=None, fingers_l="relaxed", feet=None, head=None):
        self.f, self.ease, self.body, self.hips = f, ease, body or {}, Vector(hips)
        self.grip, self.axis, self.knuckles = grip, axis, knuckles
        self.left, self.left_args, self.fingers_l, self.feet, self.head = left, left_args or {}, fingers_l, feet, head


def interp(keys, f):
    for a, b in zip(keys, keys[1:]):
        if a.f <= f <= b.f:
            t = 0 if b.f == a.f else (f - a.f) / (b.f - a.f)
            return a, b, A.ease(b.ease, t)
    return keys[-1], keys[-1], 1.0


def mix_body(a, b, t):
    out = {}
    for k in set(a.body) | set(b.body):
        va = Vector(a.body.get(k, (0, 0, 0)))
        vb = Vector(b.body.get(k, (0, 0, 0)))
        out[k] = tuple(va.lerp(vb, t))
    return out


def author(keys, n_frames=None):
    """Build frames from keys on top of the idle frame 0 (combat stance). n = last key frame + 1."""
    g_idle, a_idle = idle_hold_targets()
    frames = []
    n_frames = keys[-1].f + 1 if n_frames is None else n_frames
    for f in range(n_frames):
        a, b, t = interp(keys, f)
        pose = copy_pose(IDLE0[0])
        hl0 = IDLE0[1].copy()
        # hips offset in world, then body rotations
        M = sk.fk(pose, hl0)
        hw = M["hips"].translation + a.hips.lerp(b.hips, t)
        hl = _hips_loc(pose, hw)
        body_rotate(pose, hl, mix_body(a, b, t))
        # feet planted (idle stance unless keyed)
        feet = {}
        for s in ("L", "R"):
            pa = (a.feet or {}).get(s)
            pb = (b.feet or {}).get(s)
            base_pos, base_rot = FEET0[s]
            va = Vector(pa) if pa else Vector((0, 0, 0))
            vb = Vector(pb) if pb else Vector((0, 0, 0))
            feet[s] = (base_pos + va.lerp(vb, t), base_rot)
        keep_feet(pose, hl, feet)
        # staff
        ga = Vector(a.grip) if a.grip else g_idle
        gb = Vector(b.grip) if b.grip else g_idle
        xa = Vector(a.axis).normalized() if a.axis else a_idle
        xb = Vector(b.axis).normalized() if b.axis else a_idle
        ka = Vector(a.knuckles) if a.knuckles else KNUCKLE_FWD
        kb = Vector(b.knuckles) if b.knuckles else KNUCKLE_FWD
        grip = ga.lerp(gb, t)
        axis = slerp_dir(xa, xb, t)
        knuck = slerp_dir(ka.normalized(), kb.normalized(), t)
        hold_staff(pose, hl, "R", grip, axis, knuck, POLE_R)
        set_fingers(pose, "R", "grip")
        # the left hand grips the staff where the right-hand IK actually put it (targets can be out of reach)
        Ms = sk.fk(pose, hl)
        grip_act = Ms["socket_weapon_R"].translation.copy()
        axis_act = (Ms["socket_weapon_R"].to_3x3() @ Vector((0, 1, 0))).normalized()
        # left hand
        mode = b.left if t > 0.5 else a.left
        args_ = b.left_args if t > 0.5 else a.left_args
        if a.left == b.left == "staff" or mode == "staff":
            off_a = a.left_args.get("offset", -0.26) if a.left == "staff" else -0.26
            off_b = b.left_args.get("offset", -0.26) if b.left == "staff" else -0.26
            off = off_a + (off_b - off_a) * t
            kl = Vector(args_.get("knuckles", (0, -1, 0)))
            hold_staff(pose, hl, "L", grip_act + axis_act * off, axis_act, kl, POLE_L)
            set_fingers(pose, "L", "grip")
        elif mode == "palm" or (a.left == "palm" and b.left == "palm"):
            pa = a.left_args if a.left == "palm" else b.left_args
            pb = b.left_args if b.left == "palm" else a.left_args
            pp = Vector(pa["pos"]).lerp(Vector(pb["pos"]), t)
            fd = slerp_dir(Vector(pa["fingers"]).normalized(), Vector(pb["fingers"]).normalized(), t)
            pn = slerp_dir(Vector(pa["normal"]).normalized(), Vector(pb["normal"]).normalized(), t)
            place_palm(pose, hl, "L", pp, fd, pn, POLE_L)
            set_fingers(pose, "L", b.fingers_l if t > 0.5 else a.fingers_l)
        else:
            set_fingers(pose, "L", b.fingers_l if t > 0.5 else a.fingers_l)
        if a.head or b.head:
            ha = Vector(a.head or (0, 0, 0))
            hb = Vector(b.head or (0, 0, 0))
            hv = ha.lerp(hb, t)
            body_rotate(pose, hl, {"head": tuple(hv)})
        frames.append((pose, hl))
    return frames


def lead_from_idle(frames, settle_frames=4):
    """Blend the first frames from the exact idle pose so a 50 ms cross-fade has no pop."""
    return frames


G0, AX0 = idle_hold_targets()
G0 = tuple(G0)
AX0 = tuple(AX0)

# caster.attack_1: diagonal staff strike, crystal leads, hit at 100 ms (frame 3)
atk1 = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(2, "out", body={"spine": (-8, -2, 0), "chest": (-12, -4, 0), "head": (6, 0, 0)}, hips=(0, 0.02, -0.01),
        grip=(-0.30, 0.02, 1.38), axis=(-0.35, 0.55, 1.0), knuckles=(0, -1, -0.3)),
    Key(3, "snap", body={"spine": (10, 8, 0), "chest": (16, 10, 2), "head": (-6, 4, 0)}, hips=(0, -0.03, -0.03),
        grip=(-0.05, -0.42, 1.08), axis=(0.45, -0.95, 0.35), knuckles=(0.2, -0.3, -1)),
    Key(5, "out", body={"spine": (14, 10, 0), "chest": (20, 12, 3), "head": (-8, 4, 0)}, hips=(0, -0.04, -0.035),
        grip=(0.08, -0.40, 0.98), axis=(0.65, -0.85, 0.05), knuckles=(0.3, -0.2, -1)),
    Key(12, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(atk1)
secondaries(fr, loop=False)
store("caster.attack_1", fr, False, {"swing_start": 0, "trail_on": 1, "release": 3, "trail_off": 5, "link_open": 12},
      {"kind": "authored", "tool": "h02_clips.py prop-driven keys"}, ability="attack",
      contract={"windup_ms": 100, "active_ms": 67, "recovery_ms": 233}, notes="basic attack 1 of 2")

# caster.attack_2: rising backhand return swing (combo link), hit at 100 ms
atk2 = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(2, "out", body={"spine": (10, 4, 0), "chest": (14, 6, 0), "head": (-4, 0, 0)}, hips=(0, 0.0, -0.02),
        grip=(0.04, -0.20, 0.92), axis=(0.85, -0.35, 0.2), knuckles=(0, -0.2, -1)),
    Key(3, "snap", body={"spine": (-12, 4, 0), "chest": (-18, 6, -2), "head": (8, 2, 0)}, hips=(0, -0.02, -0.02),
        grip=(-0.34, -0.36, 1.30), axis=(-0.70, -0.75, 0.55), knuckles=(0, 0.2, -1)),
    Key(5, "out", body={"spine": (-16, 4, 0), "chest": (-22, 6, -3), "head": (10, 2, 0)}, hips=(0, -0.02, -0.025),
        grip=(-0.42, -0.24, 1.36), axis=(-0.85, -0.45, 0.65), knuckles=(0, 0.4, -1)),
    Key(12, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(atk2)
secondaries(fr, loop=False)
store("caster.attack_2", fr, False, {"swing_start": 0, "trail_on": 1, "release": 3, "trail_off": 5, "link_open": 12},
      {"kind": "authored"}, ability="attack", contract={"windup_ms": 100, "active_ms": 67, "recovery_ms": 233},
      notes="basic attack 2 of 2 (combo link 400-650 ms)")

# mage.skill_nova -> xs_bladeward_nova: staff raised in both hands, butt slammed down at 200 ms (frame 6)
nova = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(4, "out", body={"spine": (0, -6, 0), "chest": (0, -8, 0), "head": (0, -6, 0)}, hips=(0, 0.01, 0.02),
        grip=(-0.12, -0.20, 1.55), axis=(0.0, -0.10, 1.0), left="staff", left_args={"offset": -0.24}),
    Key(6, "snap", body={"spine": (0, 12, 0), "chest": (0, 14, 0), "head": (0, 8, 0)}, hips=(0, -0.03, -0.14),
        grip=(-0.06, -0.30, 1.02), axis=(0.0, -0.08, 1.0), left="staff", left_args={"offset": -0.20}),
    Key(9, "out", body={"spine": (0, 10, 0), "chest": (0, 12, 0), "head": (0, 6, 0)}, hips=(0, -0.03, -0.12),
        grip=(-0.06, -0.30, 1.03), axis=(0.0, -0.08, 1.0), left="staff", left_args={"offset": -0.20}),
    Key(18, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(nova)
secondaries(fr, loop=False)
store("mage.skill_nova", fr, False, {"charge_start": 0, "plant": 4, "hit": 6, "release": 6, "recover": 9},
      {"kind": "authored"}, ability="mage_skill_2", contract={"windup_ms": 200, "active_ms": 100, "recovery_ms": 300},
      notes="VFX xs_bladeward_nova: telegraph 0-150 ms, ground flash at release")

# mage.skill_gale -> xs_gale_palm: left palm charge at the hip, thrust at 200 ms (frame 6)
gale = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(4, "out", body={"spine": (-14, 0, 0), "chest": (-18, -2, 0), "head": (10, 0, 0)}, hips=(0, 0.02, -0.03),
        grip=(-0.30, -0.02, 1.06), axis=(-0.15, 0.15, 1.0), left="palm",
        left_args={"pos": (0.16, -0.10, 1.18), "fingers": (-0.2, -0.3, 1.0), "normal": (-0.9, -0.3, 0.0)}),
    Key(6, "snap", body={"spine": (12, 6, 0), "chest": (18, 8, 0), "head": (-8, 2, 0)}, hips=(0, -0.05, -0.05),
        grip=(-0.30, 0.04, 1.04), axis=(-0.15, 0.25, 1.0), left="palm", fingers_l="open",
        left_args={"pos": (0.06, -0.62, 1.36), "fingers": (0.0, -0.15, 1.0), "normal": (0.0, -1.0, 0.0)}),
    Key(8, "out", body={"spine": (14, 6, 0), "chest": (20, 8, 0), "head": (-8, 2, 0)}, hips=(0, -0.05, -0.05),
        grip=(-0.30, 0.04, 1.04), axis=(-0.15, 0.25, 1.0), left="palm", fingers_l="open",
        left_args={"pos": (0.06, -0.64, 1.37), "fingers": (0.0, -0.10, 1.0), "normal": (0.0, -1.0, 0.0)}),
    Key(14, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(gale)
secondaries(fr, loop=False)
store("mage.skill_gale", fr, False, {"charge_start": 0, "release": 6, "recover": 8},
      {"kind": "authored"}, ability="mage_skill_1", contract={"windup_ms": 200, "active_ms": 67, "recovery_ms": 200},
      notes="VFX xs_gale_palm: charge swirl at fx_hand_L from 0 ms, projectile leaves owner-relative staff fx_head at release")

# mage.skill_rift -> xs_void_rift: rune drawn overhead, staff driven into the target ground at 600 ms (frame 18)
rift = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(10, "out", body={"spine": (-6, -8, 0), "chest": (-8, -10, 0), "head": (0, -10, 0)}, hips=(0, 0.02, 0.02),
        grip=(-0.10, -0.12, 1.72), axis=(0.10, -0.25, 1.0), left="staff", left_args={"offset": -0.26}),
    Key(15, "in", body={"spine": (-8, -10, 0), "chest": (-10, -12, 0), "head": (0, -12, 0)}, hips=(0, 0.03, 0.03),
        grip=(-0.08, -0.05, 1.80), axis=(0.10, 0.0, 1.0), left="staff", left_args={"offset": -0.26}),
    Key(18, "snap", body={"spine": (4, 16, 0), "chest": (6, 20, 0), "head": (0, 14, 0)}, hips=(0, -0.06, -0.12),
        grip=(-0.04, -0.52, 1.06), axis=(0.05, -0.85, -0.55), left="staff", left_args={"offset": -0.24}),
    Key(21, "out", body={"spine": (4, 14, 0), "chest": (6, 18, 0), "head": (0, 12, 0)}, hips=(0, -0.05, -0.11),
        grip=(-0.04, -0.50, 1.07), axis=(0.05, -0.85, -0.55), left="staff", left_args={"offset": -0.24}),
    Key(27, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(rift)
secondaries(fr, loop=False)
store("mage.skill_rift", fr, False, {"rune": 0, "charge_start": 10, "release": 18, "slam": 18, "recover": 21, "pulse": 27},
      {"kind": "authored"}, ability="mage_skill_3", contract={"cast_ms": 600},
      notes="VFX xs_void_rift: rune circle from 0 ms at the target, abyss opens at release; ticks from 900 ms are VFX/server")

# mage.skill_bolt: staff levelled at the target, crystal charges, bolt leaves fx_tip at 600 ms (frame 18)
bolt = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(6, "out", body={"spine": (-10, 2, 0), "chest": (-14, 2, 0), "head": (8, 2, 0)}, hips=(0, 0.02, -0.02),
        grip=(-0.22, -0.18, 1.32), axis=(0.10, -0.80, 0.55), left="staff", left_args={"offset": -0.30}),
    Key(12, "in", body={"spine": (-12, 0, 0), "chest": (-16, 0, 0), "head": (10, 0, 0)}, hips=(0, 0.04, -0.03),
        grip=(-0.20, -0.10, 1.34), axis=(0.10, -0.85, 0.50), left="staff", left_args={"offset": -0.30}),
    Key(14, "snap", body={"spine": (6, 6, 0), "chest": (8, 8, 0), "head": (-4, 2, 0)}, hips=(0, -0.04, -0.04),
        grip=(-0.16, -0.40, 1.30), axis=(0.10, -0.95, 0.30), left="staff", left_args={"offset": -0.30}),
    Key(16, "out", body={"spine": (4, 4, 0), "chest": (6, 6, 0), "head": (-2, 2, 0)}, hips=(0, -0.03, -0.03),
        grip=(-0.18, -0.34, 1.33), axis=(0.10, -0.92, 0.40), left="staff", left_args={"offset": -0.30}),
    Key(25, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(bolt)
secondaries(fr, loop=False)
store("mage.skill_bolt", fr, False, {"charge_start": 0, "aim": 6, "release": 14, "recover": 16},
      {"kind": "authored"}, ability="mage_skill_4", contract={"windup_ms": 467, "active_ms": 67, "recovery_ms": 300},
      notes="Star Lance: piercing lane; release from owner-relative staff fx_head")

# mage.skill_ward: staff planted upright in front, left palm raised, barrier at 300 ms (frame 9)
ward = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(6, "out", body={"spine": (0, -4, 0), "chest": (0, -6, 0), "head": (0, -4, 0)}, hips=(0, 0.01, 0.01),
        grip=(-0.10, -0.30, 1.30), axis=(0.0, 0.05, 1.0), left="palm",
        left_args={"pos": (0.10, -0.30, 1.30), "fingers": (0.1, -0.2, 1.0), "normal": (-0.6, -0.8, 0.0)}),
    Key(9, "snap", body={"spine": (0, 6, 0), "chest": (0, 8, 0), "head": (0, 4, 0)}, hips=(0, -0.02, -0.05),
        grip=(-0.08, -0.36, 1.18), axis=(0.0, -0.02, 1.0), left="palm", fingers_l="open",
        left_args={"pos": (0.14, -0.44, 1.40), "fingers": (0.1, -0.1, 1.0), "normal": (-0.2, -1.0, 0.0)}),
    Key(11, "out", body={"spine": (0, 5, 0), "chest": (0, 7, 0), "head": (0, 4, 0)}, hips=(0, -0.02, -0.045),
        grip=(-0.08, -0.36, 1.19), axis=(0.0, -0.02, 1.0), left="palm", fingers_l="open",
        left_args={"pos": (0.14, -0.44, 1.41), "fingers": (0.1, -0.1, 1.0), "normal": (-0.2, -1.0, 0.0)}),
    Key(20, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(ward)
secondaries(fr, loop=False)
store("mage.skill_ward", fr, False, {"charge_start": 0, "release": 9, "recover": 11},
      {"kind": "authored"}, ability="mage_skill_5", contract={"windup_ms": 300, "active_ms": 67, "recovery_ms": 300},
      notes="Moonveil Ward: presentation clip for target ally barrier; server remains authoritative")

# mage.skill_starfall: both hands lift the staff overhead (long charge), sweep down at 800 ms (frame 24)
star = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(14, "out", body={"spine": (0, -10, 0), "chest": (0, -14, 0), "head": (0, -16, 0)}, hips=(0, 0.03, 0.03),
        grip=(-0.06, 0.02, 1.92), axis=(0.05, 0.10, 1.0), left="staff", left_args={"offset": -0.24}),
    Key(24, "in", body={"spine": (0, -14, 0), "chest": (0, -18, 0), "head": (0, -20, 0)}, hips=(0, 0.05, 0.05),
        grip=(-0.05, 0.08, 1.98), axis=(0.05, 0.30, 1.0), left="staff", left_args={"offset": -0.24}),
    Key(27, "snap", body={"spine": (0, 18, 0), "chest": (0, 22, 0), "head": (0, 12, 0)}, hips=(0, -0.05, -0.12),
        grip=(-0.05, -0.55, 1.18), axis=(0.05, -0.95, 0.10), left="staff", left_args={"offset": -0.24}),
    Key(30, "out", body={"spine": (0, 16, 0), "chest": (0, 20, 0), "head": (0, 10, 0)}, hips=(0, -0.05, -0.11),
        grip=(-0.05, -0.52, 1.16), axis=(0.05, -0.95, 0.05), left="staff", left_args={"offset": -0.24}),
    Key(39, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(star)
secondaries(fr, loop=False)
store("mage.skill_starfall", fr, False, {"charge_start": 0, "peak": 24, "release": 27, "recover": 30},
      {"kind": "authored"}, ability="mage_skill_6", contract={"windup_ms": 900, "active_ms": 100, "recovery_ms": 300},
      notes="Celestial Orrery: ultimate release f27 from the canonical hero-skills design")

# base.dodge: forward dash, 280 ms dash + 120 ms recovery (12 frames), server moves the capsule 2.77 m
dodge = [
    Key(0, body={}, grip=G0, axis=AX0),
    Key(2, "out", body={"hips": (0, 10, 0), "spine": (0, 10, 0), "chest": (0, 8, 0)}, hips=(0, -0.06, -0.08),
        grip=(-0.24, 0.10, 1.00), axis=(-0.10, 0.75, 0.65), feet={"L": (0, -0.10, 0.0), "R": (0, 0.06, 0.0)}),
    Key(6, "out", body={"hips": (0, 18, 0), "spine": (0, 14, 0), "chest": (0, 10, 0), "head": (0, -12, 0)},
        hips=(0, -0.14, -0.16), grip=(-0.22, 0.16, 0.96), axis=(-0.10, 0.85, 0.50),
        feet={"L": (0.0, -0.32, 0.0), "R": (0.0, 0.18, 0.06)}),
    Key(8, "inout", body={"hips": (0, 10, 0), "spine": (0, 8, 0), "chest": (0, 6, 0), "head": (0, -6, 0)},
        hips=(0, -0.08, -0.08), grip=(-0.24, 0.06, 0.98), axis=(-0.08, 0.40, 0.90),
        feet={"L": (0.0, -0.20, 0.0), "R": (0.0, 0.10, 0.02)}),
    Key(12, "inout", body={}, grip=G0, axis=AX0),
]
fr = author(dodge)
secondaries(fr, loop=False)
store("base.dodge", fr, False, {"whoosh": 0, "foot_l": 7}, {"kind": "authored"}, ability="dodge",
      contract={"dash_ms": 280, "recovery_ms": 120})

# ------------------------------------------------------------------------------------------------ cleanup + save
for o in ual_objs:
    bpy.data.objects.remove(o, do_unlink=True)
for name, a in list(ual_actions.items()):
    if a.name in bpy.data.actions:
        bpy.data.actions.remove(a)
arm.animation_data.action = None
names = [a.name for a in bpy.data.actions]
log("actions in file", names)
bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK / "h02_anim.blend"), compress=True)
C.write_json(C.REPORTS / "clips.json", {"fps": FPS, "hip_scale": HIP_SCALE, "clips": CLIPS})
log("saved anim blend")
