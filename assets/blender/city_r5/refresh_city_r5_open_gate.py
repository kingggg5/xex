"""Refresh the existing R5 Blender master and GLB without rebuilding the city.

Run from the repository root with Blender 5.2:
  blender --background assets/models/reference-city/r5/reference_city.blend \
      --python-exit-code 1 --python assets/blender/city_r5/refresh_city_r5_open_gate.py

This is an idempotent patch. It removes only old gate-obstruction meshes,
relinks existing image nodes to the final R5 texture files, saves the editable
master, then exports a temporary GLB and atomically replaces city-source.glb.
The full multi-department scene builder is intentionally not invoked.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'lib'))
import citykit as ck  # noqa: E402

R5_DIR = ROOT / 'assets' / 'models' / 'reference-city' / 'r5'
MASTER = R5_DIR / 'reference_city.blend'
GLB = R5_DIR / 'city-source.glb'
MANIFEST = R5_DIR / 'manifest.json'
TEXTURES = R5_DIR / 'textures'
BACKUP_DIR = ROOT / 'target' / 'city-r5-gate-refresh'
MASTER_BACKUP = BACKUP_DIR / 'reference_city_before_open_gate.blend'
GLB_CANDIDATE = BACKUP_DIR / 'city-source.open-gate-candidate.glb'

BLOCKER_NAMES = (
    'gate shadow portal',
    'gate raised portcullis',
    'gate portcullis iron bar',
    'gate portcullis crossbar',
)
RUNTIME_PREFIXES = ('anim_', 'fx_', 'emit_', 'light_')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def texture_fingerprint() -> dict:
    files = sorted(TEXTURES.glob('*.png'))
    rows = []
    digest = hashlib.sha256()
    for path in files:
        item = {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256(path)}
        rows.append(item)
        digest.update(path.name.encode('utf-8'))
        digest.update(bytes.fromhex(item['sha256']))
    return {'files': len(rows), 'sha256': digest.hexdigest(), 'items': rows}


def world_x_bounds(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return min(point.x for point in points), max(point.x for point in points)


def remove_closed_gate_geometry() -> tuple[list[str], float]:
    gate = bpy.data.objects.get('kit_town_gate')
    if gate is None or gate.type != 'EMPTY':
        raise RuntimeError('Expected editable town-gate root `kit_town_gate` in the R5 master.')

    descendants = []
    stack = list(gate.children)
    while stack:
        item = stack.pop()
        descendants.append(item)
        stack.extend(item.children)

    removed = []
    for obj in descendants:
        if any(obj.name == base or obj.name.startswith(base + '.') for base in BLOCKER_NAMES):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.context.view_layer.update()
    west = bpy.data.objects.get('gate west pier')
    east = bpy.data.objects.get('gate east pier')
    if west is None or east is None:
        raise RuntimeError('Both stone gate piers must remain in the master.')
    west_min, west_max = world_x_bounds(west)
    east_min, east_max = world_x_bounds(east)
    clearance = east_min - west_max
    if clearance + 1e-5 < 15.0:
        raise RuntimeError(f'Gate passage is only {clearance:.3f} m wide; expected at least 15 m.')

    # Catch legacy obstructions even if a future Blender-generated suffix was
    # attached to their names. Such geometry must never survive the patch.
    remaining = [obj.name for obj in gate.children_recursive if
                 any(obj.name == base or obj.name.startswith(base + '.') for base in BLOCKER_NAMES)]
    if remaining:
        raise RuntimeError(f'Closed-gate meshes remain: {remaining}')
    return removed, clearance


def refresh_image_nodes() -> dict:
    used_images = {}
    for material in bpy.data.materials:
        if not material.use_nodes or material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                used_images[node.image.name] = node.image

    refreshed = []
    missing = []
    for image in used_images.values():
        filename = image.name
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.exr')):
            filename = image.filepath.replace('\\', '/').rsplit('/', 1)[-1]
        target = TEXTURES / filename
        if not target.is_file():
            missing.append({'image': image.name, 'expected': str(target)})
            continue
        # Keep the .blend portable beside its texture folder while forcing a
        # reload from the finalized maps rather than Blender's cached pixels.
        image.filepath = f'//textures/{filename}'
        image.reload()
        if image.size[0] <= 0 or image.size[1] <= 0:
            raise RuntimeError(f'Blender could not reload texture {target}.')
        refreshed.append({'image': image.name, 'path': target.relative_to(ROOT).as_posix(),
                          'width': int(image.size[0]), 'height': int(image.size[1])})
    if missing:
        raise RuntimeError('Some material image nodes have no final R5 texture: ' + json.dumps(missing))
    return {'node_images': len(used_images), 'refreshed': refreshed}


def main():
    if not MASTER.is_file() or not GLB.is_file():
        raise FileNotFoundError('The existing R5 .blend and GLB are required; refusing to rebuild the city.')
    if Path(bpy.data.filepath).resolve() != MASTER.resolve():
        raise RuntimeError(f'Open the existing master first: {MASTER}')
    if not TEXTURES.is_dir():
        raise FileNotFoundError(f'Final R5 texture directory is missing: {TEXTURES}')

    before_manifest = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {}
    previous_gate_receipt = before_manifest.get('gate_refresh', {})
    previously_removed = previous_gate_receipt.get('removed_obstructions', [])
    before_texture_state = texture_fingerprint()
    if before_texture_state['files'] == 0:
        raise RuntimeError(f'No finalized R5 PNG textures found in {TEXTURES}')

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not MASTER_BACKUP.exists():
        shutil.copy2(MASTER, MASTER_BACKUP)

    removed, clearance = remove_closed_gate_geometry()
    texture_receipt = refresh_image_nodes()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(MASTER))

    # Count the editable source scene before the material merge, so the
    # manifest distinguishes authored geometry from the final export.
    # Most department meshes are linked directly into Scene Collection and
    # reach the department kit only through parenting. Do not use
    # City R5.all_objects here: that would silently drop almost the entire town.
    scene_objects = list(bpy.context.scene.objects)
    presentation = bpy.data.collections.get('Presentation only')
    presentation_objects = set(presentation.all_objects) if presentation else set()
    export_scope = [obj for obj in scene_objects if obj not in presentation_objects]
    source_meshes = [obj for obj in export_scope if obj.type == 'MESH']
    source_triangles = ck.triangle_count(source_meshes)
    static = [obj for obj in source_meshes if not obj.name.startswith(RUNTIME_PREFIXES)]
    hooks = [obj for obj in export_scope if obj.name.startswith(RUNTIME_PREFIXES)]
    bpy.context.view_layer.update()
    for obj in static:
        if obj.parent and obj.parent.type == 'EMPTY':
            world_matrix = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = world_matrix
    bpy.context.view_layer.update()

    merged, _ = ck.merge_by_material(static, 'City')
    if len(merged) != 42 or len(hooks) != 34:
        raise RuntimeError(
            f'Export-set guard failed: expected 42 material merges + 34 hooks, got '
            f'{len(merged)} merges + {len(hooks)} hooks; candidate will not be published.'
        )
    exported_objects = merged + hooks
    if not exported_objects:
        raise RuntimeError('No city geometry or runtime hooks were found for export.')

    # Export beside ignored task artifacts first. Publish only when the texture
    # fingerprint still matches the finalized inputs after Blender has read them.
    GLB_CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    if GLB_CANDIDATE.exists():
        GLB_CANDIDATE.unlink()
    ck.export_glb(exported_objects, GLB_CANDIDATE)
    texture_state_after = texture_fingerprint()
    if texture_state_after['sha256'] != before_texture_state['sha256']:
        raise RuntimeError('R5 textures changed during export; candidate retained and existing GLB preserved.')

    export_meshes = [obj for obj in exported_objects if obj.type == 'MESH']
    export_triangles = ck.triangle_count(export_meshes)
    if export_triangles < 1_000_000 or GLB_CANDIDATE.stat().st_size < 80 * 1024 * 1024:
        raise RuntimeError(
            f'Full-city export guard failed: {export_triangles:,} triangles, '
            f'{GLB_CANDIDATE.stat().st_size:,} bytes. Candidate retained and existing GLB preserved.'
        )
    published_tmp = GLB.with_name(GLB.name + '.gate-refresh.tmp')
    shutil.copy2(GLB_CANDIDATE, published_tmp)
    published_tmp.replace(GLB)

    master_receipt = {
        'path': MASTER.relative_to(ROOT).as_posix(),
        'bytes': MASTER.stat().st_size,
        'sha256': sha256(MASTER),
        'meshes': len(source_meshes),
        'triangles': source_triangles,
    }
    glb_receipt = {
        'path': GLB.relative_to(ROOT).as_posix(),
        'bytes': GLB.stat().st_size,
        'sha256': sha256(GLB),
        'meshes': len(export_meshes),
        'triangles': export_triangles,
    }
    receipt = dict(before_manifest)
    receipt.update({
        'editable_master': master_receipt,
        'merged_meshes': len(merged),
        'hooks': sorted(obj.name for obj in hooks),
        'triangles': export_triangles,
        'glb_bytes': glb_receipt['bytes'],
        'glb_sha256': glb_receipt['sha256'],
        'gate_refresh': {
            'result': 'open',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'removed_obstructions': sorted(set(previously_removed + removed)),
            'removed_this_run': removed,
            'clear_passage_m': round(clearance, 3),
            'source_geometry': {'meshes': len(source_meshes), 'triangles': source_triangles},
            'glb_export': glb_receipt,
            'textures': {'files': before_texture_state['files'], 'sha256': before_texture_state['sha256'],
                         'node_images_refreshed': texture_receipt['node_images']},
            'original_master_backup': str(MASTER_BACKUP.relative_to(ROOT).as_posix()),
        },
    })
    manifest_tmp = MANIFEST.with_name(MANIFEST.name + '.gate-refresh.tmp')
    manifest_tmp.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    manifest_tmp.replace(MANIFEST)

    print(json.dumps({
        'result': 'ok',
        'gate_clearance_m': round(clearance, 3),
        'removed_obstructions': removed,
        'textures': texture_receipt['node_images'],
        'source_master': master_receipt,
        'export': glb_receipt,
        'manifest': MANIFEST.relative_to(ROOT).as_posix(),
        'backup': MASTER_BACKUP.relative_to(ROOT).as_posix(),
    }, indent=2))


if __name__ == '__main__':
    main()
