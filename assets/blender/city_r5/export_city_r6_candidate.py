"""Export the R6 dressing candidate (source GLB + decimated runtime GLB) with the existing R5 exporters.

Uses export_runtime_r5.py unchanged (module constants pointed at the candidate) and the same
detach -> merge-by-material -> export recipe as export_source_r5.py. Writes only into
assets/models/reference-city/r6-candidate/. Never saves the loaded candidate .blend.

  blender -b --factory-startup --disable-autoexec \
    assets/models/reference-city/r6-candidate/reference_city_r6_candidate.blend --python-exit-code 1 \
    --python assets/blender/city_r5/export_city_r6_candidate.py -- --mode source|runtime
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'lib'))
sys.path.insert(0, str(HERE))
import citykit as ck  # noqa: E402
sys.path.insert(0, str(ROOT / 'assets/blender/tools'))
import export_helper as eh  # noqa: E402

OUT = ROOT / 'assets/models/reference-city/r6-candidate'
CANDIDATE = OUT / 'reference_city_r6_candidate.blend'
R5_SOURCE = ROOT / 'assets/models/reference-city/r5/city-source.glb'
TEX = ROOT / 'assets/models/reference-city/r5/textures'
QTEX = ROOT / 'assets/third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF'
PREFIXES = ('anim_', 'fx_', 'emit_', 'light_')


def candidate_export_glb(objects, path):
    """R6-only shared export policy with tangent, RGB colour and re-import proof."""
    path = Path(path)
    # Imported legacy props left the old Occlusion-only settings group in this
    # master. Blender 5.2's importer reuses that group and expects newer sockets.
    # Complete its non-art metadata in memory; never save or alter source maps.
    group = bpy.data.node_groups.get('glTF Material Output')
    normalized = []
    if group:
        sockets = {s.name for s in group.interface.items_tree if s.item_type == 'SOCKET'}
        for name, default in [('Thickness', 0.0), ('Dispersion', 0.0),
                              ('Iridescence Factor', 0.0), ('Iridescence Thickness Minimum', 100.0)]:
            if name not in sockets:
                socket = group.interface.new_socket(name, in_out='INPUT', socket_type='NodeSocketFloat')
                socket.default_value = default
                normalized.append(name)
    # Blender's tangent solver rejects n-gons in these merged legacy city
    # meshes. Triangulate only the export evaluation, after runtime decimation;
    # the editable master and traversal geometry are never saved or altered.
    for obj in objects:
        if obj.type == 'MESH':
            modifier = obj.modifiers.new('R6 export tangent triangulation', 'TRIANGULATE')
            modifier.quad_method = 'FIXED'
            modifier.ngon_method = 'CLIP'
    # Preserve the candidate's authored culling choices while applying the
    # shared format contract. This does not patch citykit or the R5 exporter.
    mats = {m for o in objects if o.type == 'MESH' for m in o.data.materials if m}
    double_sided = sorted(m.name for m in mats if not m.use_backface_culling)
    receipt_path = OUT / (path.stem.replace('.candidate', '').replace('.pending', '') + '.export-helper.receipt.json')
    eh.export_glb(objects, path, 'static_world', receipt_path=receipt_path,
                  embed_images=True, vertex_color='MATERIAL',
                  double_sided_materials=double_sided, reimport='scratch',
                  inputs=[CANDIDATE, HERE / 'layout-r6-candidate.json'],
                  notes=['R6 candidate only; R5 source/runtime/master immutable.',
                         'Export evaluation triangulated for the Blender tangent solver; no master save.',
                         {'legacy_gltf_settings_sockets_added_in_memory': normalized}])
    return path


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def reload_textures_absolute():
    records = []
    used = {n.image.name: n.image for m in bpy.data.materials if m.use_nodes and m.node_tree
            for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
    for image in used.values():
        raw = image.filepath.replace(chr(92), '/') if image.filepath else ''
        name = raw.rsplit('/', 1)[-1] if raw else image.name
        src = (TEX / name) if (TEX / name).is_file() else (QTEX / name)
        if not src.is_file():
            raise RuntimeError(f'Missing texture {name}')
        image.filepath = str(src.resolve())
        image.reload()
        if image.size[0] <= 0:
            raise RuntimeError(f'Texture decode failed {src}')
        records.append({'name': image.name, 'path': src.relative_to(ROOT).as_posix(), 'width': image.size[0], 'height': image.size[1]})
    return records


def glb_triangles(path):
    with open(path, 'rb') as f:
        head = f.read(20)
        jlen = struct.unpack_from('<I', head, 12)[0]
        doc = json.loads(f.read(jlen).decode('utf-8').rstrip('\0 '))
    tris = sum(doc['accessors'][p.get('indices', p['attributes']['POSITION'])]['count'] // 3
               for m in doc['meshes'] for p in m['primitives'])
    return tris, doc


def export_source(receipt):
    tex = reload_textures_absolute()
    pres = bpy.data.collections.get('Presentation only')
    excluded = set(pres.all_objects) if pres else set()
    objs = [o for o in bpy.context.scene.objects if o not in excluded]
    meshes = [o for o in objs if o.type == 'MESH']
    hooks = [o for o in objs if o.name.startswith(PREFIXES)]
    static = [o for o in meshes if not o.name.startswith(PREFIXES)]
    cart = bpy.data.objects.get('market stall 1-1 Quaternius CC0 stall cart')
    if cart is not None:
        ck.normalize_imported_gltf_prop_attributes(cart)
    bpy.context.view_layer.update()
    before = {o.name: o.matrix_world.copy() for o in static}
    for o in static:
        if o.parent and o.parent.type == 'EMPTY':
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
    bpy.context.view_layer.update()
    err = max(abs(before[o.name][r][c] - o.matrix_world[r][c]) for o in static for r in range(4) for c in range(4))
    if err > 1e-4:
        raise RuntimeError(f'World placement changed during detachment: {err}')
    src_tris = ck.triangle_count(meshes)
    merged, _ = ck.merge_by_material(static, 'City')
    out = OUT / 'city-source.glb'
    r5_before = sha(R5_SOURCE)
    candidate_export_glb(merged + hooks, out)
    tris, doc = glb_triangles(out)
    if tris != src_tris:
        raise RuntimeError(f'Source triangle count changed on export: {tris} != {src_tris}')
    if sha(R5_SOURCE) != r5_before:
        raise RuntimeError('R5 source GLB changed during the candidate export.')
    stats = {'schema': 'xexoria.city-source-candidate/1', 'created_utc': datetime.now(timezone.utc).isoformat(),
             'master': {'path': CANDIDATE.relative_to(ROOT).as_posix(), 'sha256': sha(CANDIDATE)},
             'candidate': {'path': out.relative_to(ROOT).as_posix(), 'sha256': sha(out), 'bytes': out.stat().st_size,
                           'triangles': tris, 'meshes': len(doc['meshes']), 'materials': len(doc['materials']),
                           'images': len(doc.get('images', [])), 'static_material_groups': len(merged), 'runtime_hooks': len(hooks)},
             'textures_reloaded': len(tex)}
    (OUT / 'city-source.stats.json').write_text(json.dumps(stats, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(stats['candidate']))


def export_runtime(receipt):
    import export_runtime_r5 as rt
    rt.MASTER = CANDIDATE
    rt.FULL_GLB = R5_SOURCE  # protected file whose hash must stay unchanged
    rt.refresh_texture_images = reload_textures_absolute
    # export_runtime_r5 uses citykit as its dependency; replace only the method
    # in this short-lived R6 process and restore it after the call.
    legacy_export = rt.ck.export_glb
    pres = bpy.data.collections.get('Presentation only')
    excluded = set(pres.all_objects) if pres else set()
    objs = [o for o in bpy.context.scene.objects if o not in excluded]
    static = [o for o in objs if o.type == 'MESH' and not o.name.startswith(PREFIXES)]
    groups = {o.data.materials[0].name for o in static if o.data.materials}
    rt.EXPECTED_STATIC_MATERIAL_GROUPS = len(groups)
    rt.EXPECTED_RUNTIME_HOOKS = len([o for o in objs if o.name.startswith(PREFIXES)])
    sys.argv = [sys.argv[0], '--', '--candidate', str(OUT / 'city-runtime.glb'), '--stats', str(OUT / 'city-runtime.stats.json')]
    try:
        rt.ck.export_glb = candidate_export_glb
        rt.main()
    finally:
        rt.ck.export_glb = legacy_export


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['source', 'runtime'], required=True)
    a = ap.parse_args(argv)
    if Path(bpy.data.filepath).resolve() != CANDIDATE.resolve():
        raise RuntimeError('Load the R6 candidate master.')
    latest = max(OUT.glob('derivation-receipt*.json'), key=lambda q: q.stat().st_mtime)
    receipt = json.loads(latest.read_text(encoding='utf-8'))
    if receipt['candidate']['sha256'] != sha(CANDIDATE):
        raise RuntimeError('Candidate master does not match its derivation receipt.')
    export_source(receipt) if a.mode == 'source' else export_runtime(receipt)


if __name__ == '__main__':
    main()
