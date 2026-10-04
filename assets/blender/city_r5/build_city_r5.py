"""R5 city assembly (PM / D11). Reads layout.json, builds terrain and every
department kit that is ready, renders matched review shots and exports the
source GLB.

Run from the repo root:
  blender --background --factory-startup --python-exit-code 1 \
      --python assets/blender/city_r5/build_city_r5.py -- [--only terrain] [--shots top,hero_front]
      [--res 1600x900] [--samples 48] [--no-export]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'lib'))
sys.path.insert(0, str(HERE / 'kits'))
import citykit as ck  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument('--only', default='')
ap.add_argument('--shots', default='top,hero_front')
ap.add_argument('--res', default='1600x900')
ap.add_argument('--samples', type=int, default=48)
ap.add_argument('--threads', type=int, default=6)
ap.add_argument('--no-export', action='store_true')
ap.add_argument('--tag', default='')
args = ap.parse_args(argv)
only = {s for s in args.only.split(',') if s}
T0 = time.time()
log_lines: list[str] = []


def log(msg):
    line = f'[{time.time() - T0:7.1f}s] {msg}'
    log_lines.append(line)
    print(line, flush=True)


ck.reset_scene()
layout = ck.load_layout()
city = ck.collection('City R5')
built: dict[str, list] = {}
hooks: list = []


def want(name):
    return not only or name in only


# ---------------------------------------------------------------------------
# Terrain (D3)
# ---------------------------------------------------------------------------
terrain = None
if want('terrain'):
    import terrain as terrain_kit
    col = ck.collection('terrain', city)
    terrain = terrain_kit.build_terrain(layout, col)
    built['terrain'] = terrain.objects
    hooks += terrain.hooks
    log(f'terrain: {len(terrain.objects)} objects, {ck.triangle_count(terrain.objects)} tris, {len(terrain.hooks)} hooks')


# ---------------------------------------------------------------------------
# Department kits (loaded when ready; failures are logged, not fatal)
# ---------------------------------------------------------------------------
def place_root(root, lm, level_z):
    """Rotate/translate a kit root (local front = -Y) to the layout spot."""
    if 'center' in lm:
        cx, cy = lm['center']
    elif 'from' in lm and 'to' in lm:
        cx = (lm['from'][0] + lm['to'][0]) * 0.5
        cy = (lm['from'][1] + lm['to'][1]) * 0.5
    elif 'spans' in lm:
        points = [p for span in lm['spans'] for p in span]
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
    else:
        cx, cy = 0.0, 0.0
    if 'face_toward' in lm:
        tx, ty = lm['face_toward']
        yaw = math.atan2(ty - cy, tx - cx)  # direction the front should face
    else:
        yaw = math.radians(lm.get('facing_deg', 270))
    # local front is -Y (angle -90deg); rotate so -Y points along yaw
    root.rotation_euler = (0, 0, yaw + math.pi / 2)
    root.location = (cx, cy, level_z)


def kit_call(module_name, func_name, *a, **kw):
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        log(f'{module_name}: not available yet')
        return None
    fn = getattr(mod, func_name, None)
    if fn is None:
        log(f'{module_name}.{func_name}: missing')
        return None
    try:
        return fn(*a, **kw)
    except Exception:  # keep assembling; the report lists the failure
        log(f'{module_name}.{func_name} FAILED:\n' + traceback.format_exc(limit=4))
        return None


def descendants(root):
    out = []
    stack = [root]
    while stack:
        o = stack.pop()
        out.append(o)
        stack.extend(o.children)
    return out


levels = layout['levels']
by_id = {lm['id']: lm for lm in layout['landmarks']}

if want('buildings'):
    col = ck.collection('buildings', city)
    fns = {'blacksmith': 'build_blacksmith', 'guild_hall': 'build_guild_hall', 'tavern': 'build_tavern',
           'potion_shop': 'build_potion_shop', 'house_large': 'build_house', 'gazebo': 'build_gazebo',
           'market_square': 'build_market'}
    for lm in layout['landmarks']:
        fn = fns.get(lm['kind'])
        if lm['kind'] == 'house_small_group':
            for i, c in enumerate(lm['centers']):
                spec = dict(lm, center=c, id=f"{lm['id']}_{i + 1}")
                root = kit_call('buildings', 'build_house', spec, col, 31 + i)
                if root:
                    place_root(root, spec, levels.get(spec.get('level', 'plaza'), 0.0))
                    built.setdefault('buildings', []).extend(descendants(root))
            continue
        if not fn:
            continue
        args_ = (lm, col, 7) if fn == 'build_house' else (lm, col)
        root = kit_call('buildings', fn, *args_)
        if root:
            place_root(root, lm, levels.get(lm.get('level', 'plaza'), 0.0))
            built.setdefault('buildings', []).extend(descendants(root))
    log(f"buildings: {len(built.get('buildings', []))} objects")

if want('castle'):
    col = ck.collection('castle', city)
    for fn, lid in (('build_castle', 'magic_castle'), ('build_grand_stairs', 'grand_stairs'),
                    ('build_north_arcades', 'north_arcades')):
        root = kit_call('castle', fn, by_id[lid], col)
        if root:
            place_root(root, by_id[lid], levels.get(by_id[lid].get('level', 'plaza'), 0.0))
            built.setdefault('castle', []).extend(descendants(root))
    log(f"castle: {len(built.get('castle', []))} objects")

if want('landmarks'):
    col = ck.collection('landmarks', city)
    calls = [('build_wizard_tower', by_id['wizard_tower']), ('build_windmill', by_id['windmill']),
             ('build_fountain', layout['fountain']), ('build_portal', layout['portal']),
             ('build_town_gate', by_id['town_gate']), ('build_bridge', by_id['canal_bridge']),
             ('build_bridge', by_id['ring_bridge'])]
    for fn, spec in calls:
        root = kit_call('landmarks', fn, spec, col)
        if root:
            place_root(root, spec, levels.get(spec.get('level', 'plaza'), 0.0))
            built.setdefault('landmarks', []).extend(descendants(root))
    log(f"landmarks: {len(built.get('landmarks', []))} objects")

if want('vegetation'):
    col = ck.collection('vegetation', city)
    root = kit_call('vegetation', 'build_vegetation', layout, col)
    if root:
        built['vegetation'] = descendants(root)
    log(f"vegetation: {len(built.get('vegetation', []))} objects")

# Collect hooks from kits (runtime-prefixed names) and realise mesh lists.
all_objs = [o for objs in built.values() for o in objs]
for o in list(all_objs):
    if o.name.startswith(ck.RUNTIME_PREFIXES) and o not in hooks:
        hooks.append(o)
bpy.context.view_layer.update()


# ---------------------------------------------------------------------------
# Review shots (presentation-only sky and cloud sea; never exported)
# ---------------------------------------------------------------------------
def presentation_context():
    pres = ck.collection('Presentation only')
    sea = ck.new_object('presentation cloud sea', [(-2000, -2000, -95), (2000, -2000, -95), (2000, 2000, -95),
                                                   (-2000, 2000, -95)], [(0, 1, 2, 3)], None, pres)
    mat = bpy.data.materials.new('presentation clouds')
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes.get('Principled BSDF')
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 0.02
    noise.inputs['Detail'].default_value = 6
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.62, 0.72, 0.86, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
    coord = nt.nodes.new('ShaderNodeTexCoord')
    nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
    nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 1.0
    sea.data.materials.append(mat)
    return pres


def shot(name, res, samples):
    cam_spec = layout['review_cameras'][name]
    cam_data = bpy.data.cameras.new(f'cam {name}')
    cam = bpy.data.objects.new(f'cam {name}', cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = Vector(cam_spec['location'])
    target = Vector(cam_spec['target'])
    if name == 'top':
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = 310
        cam.location = Vector((target.x, target.y, 420))
        cam.rotation_euler = (0, 0, 0)
    else:
        cam_data.lens = cam_spec.get('lens_mm', 50)
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data.clip_start = 0.5
    cam_data.clip_end = 5000
    bpy.context.scene.camera = cam
    w, h = res
    if name == 'top':
        w, h = int(h * 240 / 288 * 1.08), h
    ck.render_settings((w, h), samples, args.threads)
    out = ck.REVIEW_DIR / f'r5{args.tag}_{name}.png'
    ck.render(out)
    log(f'shot {name} -> {out.name}')
    return out


shots = [s for s in args.shots.split(',') if s]
if shots:
    presentation_context()
    ck.setup_review_world(strength=1.0, sun_energy=4.0, sun_rot=(math.radians(48), 0, math.radians(-28)))
    w, h = (int(v) for v in args.res.lower().split('x'))
    for s in shots:
        shot(s, (w, h), args.samples)

# Preserve the authored object kits before the runtime export merges static
# meshes by material. This is the editable Blender master for the exact R5 run.
master_path = ck.R5_DIR / 'reference_city.blend'
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(master_path))
log(f'editable master -> {master_path.name} ({master_path.stat().st_size} bytes)')


# ---------------------------------------------------------------------------
# Export (merge static by material; hooks stay separate)
# ---------------------------------------------------------------------------
if not args.no_export:
    meshes = [o for objs in built.values() for o in objs if o.type == 'MESH']
    static = [o for o in meshes if not o.name.startswith(ck.RUNTIME_PREFIXES)]
    bpy.context.view_layer.update()
    for o in static:
        if o.parent and o.parent.type == 'EMPTY':
            world_matrix = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = world_matrix
    bpy.context.view_layer.update()
    merged, _ = ck.merge_by_material(static, 'City')
    hook_objs = [o for o in hooks if o.name in bpy.data.objects]
    out = ck.R5_DIR / 'city-source.glb'
    ck.export_glb(merged + hook_objs, out)
    tris = ck.triangle_count(merged + [o for o in hook_objs if o.type == 'MESH'])
    receipt = {
        'asset': 'reference-city', 'revision': 'r5', 'blender': bpy.app.version_string,
        'layout': 'assets/blender/city_r5/layout.json',
        'layout_sha256': hashlib.sha256(ck.LAYOUT_PATH.read_bytes()).hexdigest(),
        'editable_master': {
            'path': master_path.relative_to(ck.ROOT).as_posix(),
            'bytes': master_path.stat().st_size,
            'sha256': hashlib.sha256(master_path.read_bytes()).hexdigest(),
        },
        'kits_built': sorted(built), 'merged_meshes': len(merged), 'hooks': sorted(o.name for o in hook_objs),
        'triangles': tris, 'glb_bytes': out.stat().st_size,
        'glb_sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
        'log': log_lines,
    }
    (ck.R5_DIR / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    log(f'export: {len(merged)} merged meshes, {len(hook_objs)} hooks, {tris} tris, {out.stat().st_size} bytes')
log('done')
