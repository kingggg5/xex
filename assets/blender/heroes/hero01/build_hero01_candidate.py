"""Fit an H01 XS1 candidate with native heat-cage weights and licensed UAL retargets.

No source writes, rendering, provider calls, add-on installation, or shared pipeline invocation.
Outputs remain external review candidates until native deformation/weapon/gameplay review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[4]
TOOLKIT = ROOT / 'assets/blender/heroes/hero02'
sys.path.insert(0, str(TOOLKIT))
import h02_xs1 as X
import h02_animlib as A

P = argparse.ArgumentParser()
P.add_argument('--source', type=Path, required=True)
P.add_argument('--out', type=Path, required=True)
P.add_argument('--pass-name', default='r01')
args = P.parse_args(sys.argv[sys.argv.index('--') + 1:])
EXPECTED = '6fb5957dcf27e7726d82c78f604a844166f8bfeda4baad7a83e6509287469d65'
UAL = ROOT / 'assets/models/heroes/hero02/source/third-party/ual1-standard-2025-06-10'
UAL_EXPECTED = '0ff075c7ad6855c5c2c37a171592ee8f0d6ab2f58259e2be77a9b63dd8027765'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def select_only(objs, active=None):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]

assert sha(args.source) == EXPECTED, 'Source digest changed; refusing intake'
assert sha(UAL / 'AnimationLibrary_Godot_Standard.gltf') == UAL_EXPECTED, 'UAL provenance changed'
assert args.source.resolve() != args.out.resolve(), 'Output cannot replace source'
assert shutil.disk_usage(args.out.parent).free > 250_000_000, 'Insufficient free disk for bounded candidate'
args.out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.fps = 30
scn.render.fps_base = 1
scn.render.threads_mode = 'FIXED'
scn.render.threads = 4
print('H01_STAGE intake', flush=True)
bpy.ops.import_scene.gltf(filepath=str(args.source.resolve()), merge_vertices=False, import_shading='NORMALS')
meshes = [o for o in scn.objects if o.type == 'MESH']
assert len(meshes) == 1, 'Expected the inspected single H01 material mesh'
body = meshes[0]
body.name = 'hero01_swordsman_source_candidate'
world = body.matrix_world.copy()
co = np.array([tuple(world @ v.co) for v in body.data.vertices], dtype=np.float64)
lo, hi = co.min(0), co.max(0)
pivot = np.array([(lo[0] + hi[0]) / 2, 0, lo[2]])
# Crown position requires native art confirmation; the topknot sits about 4cm above it.
scale = 2.04 / (hi[2] - lo[2])
co = (co - pivot) * scale
body.parent = None
body.matrix_world = Matrix.Identity(4)
body.data.vertices.foreach_set('co', co.ravel())
body.data.update()
body.data.calc_loop_triangles()
source_triangles = len(body.data.loop_triangles)
assert source_triangles == 24121, 'Unexpected source topology'
assert len(body.data.uv_layers) >= 1, 'UV data lost at import'
source_materials = [m.name for m in body.data.materials]
images = []
for mat in body.data.materials:
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image and node.image not in images:
            images.append(node.image)
assert len(images) == 3, 'Expected base, ORM and normal source maps'
for image in images:
    image.scale(2048, 2048)
    image.pack()
for poly in body.data.polygons:
    poly.use_smooth = True

# Fit the established XS1 core names and parent graph to this bulky source, in metres.
# Body forward is Blender -Y, exported glTF/Babylon +Z.
specs = {
    'root': ((0, 0, 0), (0, 0, .22)),
    'hips': ((0, .015, .98), (0, .015, 1.17)),
    'spine': ((0, .015, 1.17), (0, .01, 1.32)),
    'chest': ((0, .01, 1.32), (0, .01, 1.47)),
    'upper_chest': ((0, .01, 1.47), (0, .005, 1.67)),
    'neck': ((0, .005, 1.67), (0, -.015, 1.79)),
    'head': ((0, -.015, 1.79), (0, -.03, 2.00)),
}
for side, sign in [('L', 1), ('R', -1)]:
    shoulder = Vector((sign * .43, .015, 1.60))
    elbow = Vector((sign * .60, -.015, 1.27))
    wrist = Vector((sign * .66, -.01, .98))
    knuckle = Vector((sign * .67, -.045, .88))
    specs.update({
        f'shoulder.{side}': ((sign * .16, .015, 1.60), shoulder),
        f'upper_arm.{side}': (shoulder, elbow),
        f'upper_arm_twist.{side}': (shoulder.lerp(elbow, .3), shoulder.lerp(elbow, .6)),
        f'forearm.{side}': (elbow, wrist),
        f'forearm_twist.{side}': (elbow.lerp(wrist, .6), elbow.lerp(wrist, .95)),
        f'hand.{side}': (wrist, knuckle),
        f'thumb.01.{side}': ((sign * .625, -.06, .94), (sign * .61, -.09, .89)),
        f'thumb.02.{side}': ((sign * .61, -.09, .89), (sign * .615, -.115, .85)),
        f'index.01.{side}': ((sign * .645, -.065, .885), (sign * .635, -.09, .845)),
        f'index.02.{side}': ((sign * .635, -.09, .845), (sign * .635, -.12, .81)),
        f'grip.01.{side}': ((sign * .68, -.035, .88), (sign * .685, -.07, .83)),
        f'grip.02.{side}': ((sign * .685, -.07, .83), (sign * .675, -.11, .79)),
        f'socket_weapon_{side}': ((sign * .65, -.085, .89), (sign * .65, -.085, 1.01)),
        f'pauldron.{side}': ((sign * .43, .015, 1.66), (sign * .53, .015, 1.66)),
        f'thigh.{side}': ((sign * .20, .015, .98), (sign * .275, -.005, .54)),
        f'shin.{side}': ((sign * .275, -.005, .54), (sign * .285, .025, .145)),
        f'foot.{side}': ((sign * .285, .025, .145), (sign * .285, -.145, .055)),
        f'toe.{side}': ((sign * .285, -.145, .055), (sign * .285, -.25, .045)),
    })
SECONDARY = ['tabard.F.01', 'tabard.F.02', 'tabard.B.01', 'tabard.B.02']
parents = {n: X.PARENT[n] for n in X.CORE}
for side, y in [('F', -.20), ('B', .16)]:
    specs[f'tabard.{side}.01'] = ((0, y, .98), (0, y, .70))
    specs[f'tabard.{side}.02'] = ((0, y, .70), (0, y, .44))
    parents[f'tabard.{side}.01'] = 'hips'
    parents[f'tabard.{side}.02'] = f'tabard.{side}.01'
JOINTS = X.CORE + SECONDARY
adata = bpy.data.armatures.new('hero01_XS1')
arm = bpy.data.objects.new('hero01_XS1', adata)
scn.collection.objects.link(arm)
select_only([arm])
bpy.ops.object.mode_set(mode='EDIT')
for name in JOINTS:
    bone = adata.edit_bones.new(name)
    bone.head, bone.tail = specs[name]
    if parents[name]:
        bone.parent = adata.edit_bones[parents[name]]
    hint = Vector((0, 0, 1)) if name.startswith(('foot.', 'toe.')) else Vector((0, -1, 0))
    bone.align_roll(hint)
    bone.use_connect = False
bpy.ops.object.mode_set(mode='OBJECT')
arm.show_in_front = True
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'

# Native heat weighting uses a disposable closed voxel cage, as in the existing Minotaur recipe.
print('H01_STAGE native_heat_cage', flush=True)
proxy = body.copy()
proxy.data = body.data.copy()
proxy.name = 'hero01_disposable_weight_cage'
scn.collection.objects.link(proxy)
select_only([proxy])
proxy.data.remesh_voxel_size = .030
bpy.ops.object.voxel_remesh()
smooth = proxy.modifiers.new('CageSmooth', 'SMOOTH')
smooth.factor = 1
smooth.iterations = 3
bpy.ops.object.modifier_apply(modifier=smooth.name)
heat_names = [n for n in X.CORE if not any(t in n for t in ('root', 'twist', 'socket', 'pauldron', 'thumb', 'index', 'grip'))]
for bone in arm.data.bones:
    bone.use_deform = bone.name in heat_names
select_only([proxy, arm], arm)
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
coverage = sum(bool(v.groups) for v in proxy.data.vertices) / max(1, len(proxy.data.vertices))
assert coverage > .95, f'Native heat cage coverage too low: {coverage}'
for bone in arm.data.bones:
    bone.use_deform = True
for group in proxy.vertex_groups:
    body.vertex_groups.new(name=group.name)
select_only([body])
transfer = body.modifiers.new('NativeWeightTransfer', 'DATA_TRANSFER')
transfer.object = proxy
transfer.use_vert_data = True
transfer.data_types_verts = {'VGROUP_WEIGHTS'}
transfer.vert_mapping = 'POLYINTERP_NEAREST'
transfer.layers_vgroup_select_src = 'ALL'
transfer.layers_vgroup_select_dst = 'NAME'
bpy.ops.object.modifier_apply(modifier=transfer.name)
bpy.data.objects.remove(proxy, do_unlink=True)
body.parent = arm
modifier = body.modifiers.new('Hero01Skin', 'ARMATURE')
modifier.object = arm
modifier.use_deform_preserve_volume = False

def set_weights(obj, index, values):
    for old in list(obj.data.vertices[index].groups):
        obj.vertex_groups[old.group].remove([index])
    values = sorted([(n, float(w)) for n, w in values.items() if w > 1e-7], key=lambda item: -item[1])[:4]
    total = sum(w for _, w in values)
    assert total > 0
    for name, weight in values:
        group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
        group.add([index], weight / total, 'REPLACE')

def normalize_weights(obj):
    fallback = 0
    for vertex in obj.data.vertices:
        values = {obj.vertex_groups[g.group].name: g.weight for g in vertex.groups
                  if obj.vertex_groups[g.group].name in JOINTS}
        if not values:
            name = min(heat_names, key=lambda n: (vertex.co - arm.data.bones[n].head_local).length)
            values = {name: 1}
            fallback += 1
        set_weights(obj, vertex.index, values)
    return fallback

# Seam-aware connected components are assessed before part assignments; never remesh the delivered UV mesh.
adj = [[] for _ in body.data.vertices]
for edge in body.data.edges:
    a, b = edge.vertices
    adj[a].append(b)
    adj[b].append(a)
# Join coincident UV-seam vertices only in the component graph, preserving the actual UV mesh.
coincident = {}
for index, point in enumerate(co):
    key = tuple(np.round(point, 5))
    previous = coincident.get(key)
    if previous is None:
        coincident[key] = index
    else:
        adj[index].append(previous)
        adj[previous].append(index)
seen, components = set(), []
for i in range(len(adj)):
    if i in seen:
        continue
    todo, comp = [i], []
    seen.add(i)
    while todo:
        j = todo.pop()
        comp.append(j)
        for k in adj[j]:
            if k not in seen:
                seen.add(k)
                todo.append(k)
    components.append(comp)
assignments = {}
tabard_ids = set()
for comp in components:
    pts = co[comp]
    cen = pts.mean(0)
    size = pts.max(0) - pts.min(0)
    x, y, z = cen
    side = 'L' if x > 0 else 'R'
    name = None
    if z > 1.75 and abs(x) < .24:
        name = 'head'
    elif 1.45 < z < 1.84 and abs(x) > .34 and size[2] < .35 and len(comp) < 1400:
        name = f'pauldron.{side}'
    elif .98 < z < 1.45 and abs(x) > .48 and size[2] < .30 and len(comp) < 1100:
        name = f'forearm.{side}' if z < 1.24 else f'upper_arm.{side}'
    elif .87 < z < 1.15 and abs(x) < .35 and np.linalg.norm(size) < .26:
        name = 'hips'
    elif z < .21:
        name = f'foot.{side}'
    elif .77 < z < 1.00 and abs(x) > .58 and size[2] < .25:
        name = f'hand.{side}'
    elif .44 < z < .95 and abs(x) < .20 and abs(y) > .14 and size[0] < .42:
        side_fb = 'F' if y < 0 else 'B'
        tabard_ids.update(comp)
        for vi in comp:
            blend = max(0, min(1, (.82 - co[vi, 2]) / .20))
            set_weights(body, vi, {f'tabard.{side_fb}.01': 1 - blend, f'tabard.{side_fb}.02': blend})
        assignments[f'tabard.{side_fb}'] = assignments.get(f'tabard.{side_fb}', 0) + len(comp)
    if name:
        for vi in comp:
            set_weights(body, vi, {name: 1})
        assignments[name] = assignments.get(name, 0) + len(comp)
fallback = normalize_weights(body)
def smooth(a, b, value):
    t = max(0, min(1, (value-a)/(b-a)))
    return t*t*(3-2*t)
def blend_weight(index, bone, weight):
    if weight <= 0:
        return
    v = body.data.vertices[index]
    values = {body.vertex_groups[g.group].name: g.weight * (1-weight) for g in v.groups}
    values[bone] = values.get(bone, 0) + weight
    set_weights(body, index, values)
# Rigid sole/toe shell prevents blended lower-leg weights from sinking the boot below ground.
for vertex in body.data.vertices:
    x, y, z = vertex.co
    if z < .245 and vertex.index not in tabard_ids:
        set_weights(body, vertex.index, {f"foot.{'L' if vertex.co.x > 0 else 'R'}": 1})
    if .70 < z < 1.08 and abs(x) > .55:
        weight = smooth(.55, .65, abs(x)) * (1-smooth(.94, 1.08, z))
        blend_weight(vertex.index, f"hand.{'L' if x > 0 else 'R'}", weight)
base_mesh = body.data.copy()
lods = {}
for lod, target in [(0, 12000), (1, 6000), (2, 2500)]:
    obj = body.copy()
    obj.data = base_mesh.copy()
    obj.name = f'hero01_swordsman_lod{lod}'
    scn.collection.objects.link(obj)
    select_only([obj])
    decimate = obj.modifiers.new('NativeCandidateLOD', 'DECIMATE')
    decimate.ratio = target / source_triangles
    decimate.use_collapse_triangulate = True
    bpy.ops.object.modifier_move_up(modifier=decimate.name)
    bpy.ops.object.modifier_apply(modifier=decimate.name)
    normalize_weights(obj)
    # Collapse may place a few sole points below their original plane; keep the delivered bind floor exact.
    for v in obj.data.vertices:
        if v.co.z < 0:
            v.co.z = 0
    obj.data.update()
    obj.data.calc_loop_triangles()
    assert len(obj.data.loop_triangles) <= target + 25
    lods[lod] = obj
    obj.hide_set(True)
body.hide_set(True)

print('H01_STAGE licensed_retarget', flush=True)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(UAL / 'AnimationLibrary_Godot_Standard.gltf'),
                          bone_heuristic='BLENDER', guess_original_bind_pose=True)
ual_objects = [o for o in bpy.data.objects if o not in before]
ual_arm = next(o for o in ual_objects if o.type == 'ARMATURE')
ual_actions = {a.name: a for a in bpy.data.actions}
sk = A.Skeleton(arm)
hip_scale = sk.rest['thigh.L'].translation.z / (ual_arm.matrix_world @ ual_arm.data.bones['DEF-thigh.L'].head_local).z
idle_reference_action = next(a for name, a in ual_actions.items() if name == 'Idle_Loop' or name.split('|')[-1] == 'Idle_Loop')
idle_reference = A.SourceClip(ual_arm, idle_reference_action, [float(idle_reference_action.frame_range[0])],
                              [b.name for b in ual_arm.data.bones]).frames[0]
clip_specs = [('base.idle', 'Idle_Loop', 76, True), ('base.walk', 'Walk_Loop', 33, True),
              ('base.run', 'Jog_Fwd_Loop', 23, True), ('blade_1h.attack_1', 'Sword_Attack', 13, False),
              ('blade_1h.attack_2', 'Sword_Attack', 13, False)]
clips, frame_sets, retarget_diagnostics = {}, {}, {}
for clip_name, source_name, count, loop in clip_specs:
    src_action = next(action for name, action in ual_actions.items()
                      if name == source_name or name.split('|')[-1] == source_name)
    f0, f1 = src_action.frame_range
    source_frames = [f0 + (f1 - f0) * i / (count - 1) for i in range(count)]
    if source_name == 'Sword_Attack':
        # Detect the fastest wrist motion in the source rather than copying an unrelated fixed hit frame.
        dense = A.SourceClip(ual_arm, src_action, [float(f) for f in range(int(f0), int(f1) + 1)], [b.name for b in ual_arm.data.bones])
        wrist = [row['DEF-hand.R'][1] for row in dense.frames]
        peak = 1 + max(range(len(wrist) - 1), key=lambda k: (wrist[k + 1] - wrist[k]).length)
        source_peak = f0 + peak
        source_frames = [f0 + (source_peak - f0) * i / 3 if i <= 3 else source_peak + (f1 - source_peak) * (i - 3) / 9 for i in range(count)]
    source = A.SourceClip(ual_arm, src_action, source_frames, [b.name for b in ual_arm.data.bones])
    # Calibrate a relaxed source pose to H01's fitted rest. T-pose rest deltas otherwise double
    # the arm lowering and move beard/chest weights in an unrelated initial pose.
    for source_bone in list(source.rest):
        if source_bone in idle_reference:
            rotation, position = idle_reference[source_bone]
            source.rest[source_bone] = (rotation.copy(), position.copy(),
                                        (rotation @ Vector((0, 1, 0))).normalized())
    frames = A.retarget(sk, source, X.UAL_POSE, 'DEF-hips', hip_scale, in_place=True,
                        delta_bones=tuple(X.UAL_POSE.values()))
    retarget_diagnostics[clip_name] = list(A.RETARGET_LOG)
    # Twist follows the parent; rigid pauldrons follow the shoulder; tabard remains independent of the thighs.
    for pose, hips in frames:
        if clip_name.startswith('blade_1h'):
            # UAL Sword_Attack includes a lower-body stance unsuitable for this bulky fit.
            # Retain its fitted upper-body cut over a neutral planted H01 lower body.
            hips.x = hips.y = hips.z = 0
            pose['hips'] = Quaternion()
            for side in ('L', 'R'):
                for name in ('thigh', 'shin', 'foot', 'toe'):
                    pose[f'{name}.{side}'] = Quaternion()
        if clip_name == 'base.run':
            # Heavy plate silhouette needs a smaller arm swing than the reference mannequin.
            for side in ('L', 'R'):
                for name in ('shoulder', 'upper_arm', 'forearm'):
                    bone_name = f'{name}.{side}'
                    pose[bone_name] = Quaternion().slerp(pose.get(bone_name, Quaternion()), .60)
        for side in ('L', 'R'):
            pose[f'upper_arm_twist.{side}'] = Quaternion()
            pose[f'forearm_twist.{side}'] = Quaternion()
            pose[f'pauldron.{side}'] = Quaternion()
        if clip_name.startswith('blade_1h'):
            for side in ('L', 'R'):
                pose[f'grip.01.{side}'] = A.q_axis((1, 0, 0), 30)
                pose[f'grip.02.{side}'] = A.q_axis((1, 0, 0), 35)
        if clip_name == 'blade_1h.attack_2':
            pose['chest'] = A.q_axis((0, 1, 0), 8) @ pose.get('chest', Quaternion())
        # Rest-frame-aware leg IK preserves a stable planted stance for idle/basic attacks.
        # Walk/run keep their horizontal gait but clamp the stance ankle to its measured sole height.
        for side in ('L', 'R'):
            M = sk.fk(pose, hips)
            foot_name = f'foot.{side}'
            rest_ankle = sk.rest[foot_name].translation
            target = rest_ankle.copy() if clip_name == 'base.idle' or clip_name.startswith('blade_1h') else M[foot_name].translation.copy()
            if target.z < rest_ankle.z + .025:
                target.z = rest_ankle.z
            pole = Vector((rest_ankle.x, -.6, .5))
            sk.ik2(pose, hips, f'thigh.{side}', f'shin.{side}', foot_name, target, pole)
            M = sk.fk(pose, hips)
            pose[foot_name] = sk.local_for_world(M, foot_name, sk.rest[foot_name].to_quaternion())
            M = sk.fk(pose, hips)
            toe_name = f'toe.{side}'
            pose[toe_name] = sk.local_for_world(M, toe_name, sk.rest[toe_name].to_quaternion())
    if loop:
        A.close_loop(frames, blend_frames=4)
    action = A.write_action(arm, clip_name, frames, JOINTS, fps=30, loop=loop,
                            markers={'hit': 3, 'trail_on': 2, 'trail_off': 5} if 'attack' in clip_name else None)
    clips[clip_name] = {'source': source_name, 'licence': 'CC0-1.0', 'frames': count,
                        'duration_s': (count - 1) / 30, 'loop': loop, 'release_frame': 3 if 'attack' in clip_name else None,
                        'source_frame_range': [float(f0), float(f1)], 'retarget_kind': 'world-delta fitted XS1, calibrated UAL Idle reference pose',
                        'adaptation': 'Basic clips retain fitted UAL upper body over neutral planted H01 legs. Run arm swing attenuated60% for plate clearance.',
                        'limits': 'Foot locking at actual controller speed and weapon grip unverified.'}
    frame_sets[clip_name] = frames
for obj in ual_objects:
    bpy.data.objects.remove(obj, do_unlink=True)
for action in list(bpy.data.actions):
    if action.name not in clips:
        bpy.data.actions.remove(action)

# Keep canonical socket/fx IDs; each marker is parented to its intended H01 bone.
markers = []
for name, parent in X.STATIC_NODES.items():
    marker = bpy.data.objects.new(name, None)
    scn.collection.objects.link(marker)
    marker.parent = arm
    marker.parent_type = 'BONE'
    marker.parent_bone = parent
    marker.matrix_world = Matrix.Translation(arm.data.bones[parent].head_local)
    markers.append(marker)

# Deformation measurement: sampled geometry, floor contact and edge stretch; no visual PASS claim.
print('H01_STAGE deformation_measurement', flush=True)
obj = lods[0]
obj.hide_set(False)
select_only([obj, arm], arm)
dg = bpy.context.evaluated_depsgraph_get()
bind_co = np.array([tuple(v.co) for v in obj.data.vertices])
edges = np.array([tuple(e.vertices) for e in obj.data.edges], dtype=np.int32)
bind_len = np.linalg.norm(bind_co[edges[:, 0]] - bind_co[edges[:, 1]], axis=1)
valid = bind_len > .002
deformation = {}
for name, frames in frame_sets.items():
    action = bpy.data.actions[name]
    arm.animation_data.action = action
    arm.animation_data.action_slot = action.slots[0]
    samples, minimum = [], 1e9
    sample_frames = sorted(set([0, len(frames) - 1] + [int(i) for i in np.linspace(0, len(frames) - 1, 10)]))
    for frame in sample_frames:
        scn.frame_set(frame)
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(dg)
        mesh = evaluated.to_mesh()
        pts = np.array([tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices])
        evaluated.to_mesh_clear()
        minimum = min(minimum, float(pts[:, 2].min()))
        lens = np.linalg.norm(pts[edges[:, 0]] - pts[edges[:, 1]], axis=1)
        stretch = lens[valid] / bind_len[valid]
        samples.append({'frame': frame, 'floor_min_m': float(pts[:, 2].min()),
                        'height_m': float(pts[:, 2].max() - pts[:, 2].min()),
                        'stretch_p99': float(np.quantile(stretch, .99)),
                        'edges_over_2x': int(np.sum(stretch > 2))})
    # Offset only hips Z once per clip, keeping source movement in place and original foot trajectories.
    offset = max(0, -minimum)
    if offset:
        updated = []
        for pose, hips_loc in frames:
            M = sk.fk(pose, hips_loc)
            world_hips = M['hips'].translation + Vector((0, 0, offset))
            updated.append((pose, sk.hips_loc_for_world(M, world_hips)))
        A.write_action(arm, name, updated, JOINTS, fps=30, loop=clips[name]['loop'],
                       markers={'hit': 3, 'trail_on': 2, 'trail_off': 5} if 'attack' in name else None)
        frame_sets[name] = updated
    deformation[name] = {'pre_floor_offset_m': offset, 'samples_before_offset': samples,
                          'verdict': 'UNVERIFIED_VISUAL; measured rig candidate only'}

arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
scn.frame_set(0)
bpy.context.view_layer.update()
obj.hide_set(True)
out_records = []
for lod, obj in lods.items():
    obj.hide_set(False)
    select_only([obj, arm] + (markers if lod == 0 else []), arm)
    filename = args.out / f'hero01_swordsman_lod{lod}.glb'
    bpy.ops.export_scene.gltf(filepath=str(filename), export_format='GLB', use_selection=True,
                              export_materials='EXPORT', export_image_format='AUTO',
                              export_animations=lod == 0, export_animation_mode='ACTIONS',
                              export_frame_range=False, export_frame_step=1, export_force_sampling=True,
                              export_skins=True, export_influence_nb=4, export_all_influences=False,
                              export_reset_pose_bones=True, export_anim_slide_to_zero=True,
                              export_cameras=False, export_lights=False, export_extras=True)
    obj.data.calc_loop_triangles()
    vals = [sum(g.weight for g in v.groups) for v in obj.data.vertices]
    out_records.append({'lod': lod, 'path': str(filename), 'sha256': sha(filename), 'bytes': filename.stat().st_size,
                        'triangles': len(obj.data.loop_triangles), 'vertices': len(obj.data.vertices),
                        'uv_layers': len(obj.data.uv_layers), 'materials': [m.name for m in obj.data.materials],
                        'max_weight_sum_error': max(abs(v - 1) for v in vals),
                        'max_influences': max(len(v.groups) for v in obj.data.vertices)})
    obj.hide_set(True)
obj = lods[0]
obj.hide_set(False)
select_only([obj, arm], arm)
# Only a lean candidate is saved; no duplicate source mesh or unloaded library retained.
bpy.data.objects.remove(body, do_unlink=True)
if base_mesh.users == 0:
    bpy.data.meshes.remove(base_mesh)
for mesh in list(bpy.data.meshes):
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)
blend = args.out / 'hero01_swordsman_r01.blend'
scn.frame_start, scn.frame_end = 0, 75
scn.render.engine = 'BLENDER_EEVEE'
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
total = sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())
assert total < 200_000_000, f'Output package exceeds disk ceiling: {total}'
assert sha(args.source) == EXPECTED, 'Source mutated during processing'
receipt = {'schema': 'xexoria.hero01-rig-candidate/1', 'status': 'BLENDER_CANDIDATE_NOT_GAME_READY',
           'pass': args.pass_name, 'blender': bpy.app.version_string, 'source': {'path': str(args.source), 'sha256': EXPECTED,
           'bytes': args.source.stat().st_size, 'triangles': source_triangles, 'immutable_rechecked': True},
           'scale': scale, 'pivot_source': pivot.tolist(), 'visible_height_m': 2.04,
           'crown_height_m': 2.0, 'crown_measurement': 'Provisional fitted skull crown; highest topknot 2.04m. Native comparison required.',
           'facing': 'Blender -Y / glTF +Z / Babylon +Z', 'foot_anchor': 'Source sole minimum normalized to Z=0',
           'rig': {'kind': 'Fitted XS1 core / native Blender bone heat cage', 'joints': JOINTS, 'core_joints': len(X.CORE),
                   'secondary_joints': SECONDARY, 'skin_weight_source': 'H01 own geometry; no H02 skin copy',
                   'heat_coverage': coverage, 'fallback_vertices': fallback, 'rigid_assignments_vertices': assignments,
                   'seam_linked_components': len(components)},
           'textures': [{'name': im.name, 'dimensions': list(im.size), 'colorspace': im.colorspace_settings.name} for im in images],
           'outputs': out_records, 'editable_blend': {'path': str(blend), 'bytes': blend.stat().st_size, 'sha256': sha(blend)},
           'total_output_bytes': total, 'clips': clips, 'retarget_diagnostics': retarget_diagnostics, 'deformation': deformation,
           'dependencies': [{'path': str(TOOLKIT / n), 'sha256': sha(TOOLKIT / n)} for n in ('h02_xs1.py', 'h02_animlib.py')],
           'provenance': {'ual': str(UAL / 'provenance.json'), 'licence': 'CC0-1.0', 'provider_job': '60b43240-a897-4839-a445-e0c4fdf284bd'},
           'jev': 'USED_VERIFIED parent receipt 20261004-heroes-six/jev-intake-receipt.json reused',
           'limits': ['No rendering or GPU run in this lane. Root must inspect native deformation before admission.',
                      'Hand/finger/arm fit and rigid plate policy are candidates, not a visual acceptance.',
                      'No sword mesh attached; socket/grip requires the actual weapon during native review.',
                      'Locomotion foot locking at real controller speed unverified.',
                      'Six class skill clips, hit/dodge/death and cloth polish are not finished by this bounded pilot.',
                      'Blender decimation preserves UV/material channels but needs silhouette/texture review.',
                      'No compressed runtime packaging or phone/full-game device gate claimed.']}
write_json(args.out / 'receipt.json', receipt)
print('H01_CANDIDATE', json.dumps({'outputs': out_records, 'package_bytes': total}), flush=True)
