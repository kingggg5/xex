"""Sunmeadow v2 blockout: explicit glTF export, re-import validation, collider-on-visual check (Blender 5.2).

Export rules (docs/reviews/2026-10-02-blender-asset-official-docs.md E1/E6/X4/X5/P7):
- every exporter option is passed explicitly: the operator's full RNA property set is read, defaults are filled
  and the overrides below are applied; unknown override names abort the export;
- COLOR_0 is deliberately NOT exported (export_vertex_color='NONE'): the blockout has no vertex colours, and a
  VEC4 COLOR_0 makes Babylon set hasVertexAlpha (GAP-3);
- meshopt and Draco stay off; meshopt is a later glTF-Transform step and only EXT_meshopt_compression is allowed
  (Babylon 9.27.1 has no KHR_meshopt_compression loader);
- each GLB is validated by re-importing it and comparing triangles, materials and bounds with the source.
"""
from __future__ import annotations

import json
import math
import re
import struct
import time
from pathlib import Path

import bpy
from mathutils import Vector

import sm2_geom as G

GLTF_OVERRIDES = {
    'check_existing': False,
    'export_format': 'GLB',
    'export_copyright': 'Xexoria - Sunmeadow v2 BLOCKOUT proxies (not final art)',
    'export_import_convert_lighting_mode': 'SPEC',
    'export_use_gltfpack': False,
    'export_image_format': 'NONE',             # the blockout has no textures
    'export_image_add_webp': False,
    'export_image_webp_fallback': False,
    'export_keep_originals': False,
    'export_texcoords': True,                  # ground/path UV = world XZ / 6 (llm.txt meadow rule)
    'export_normals': True,
    'export_tangents': False,                  # no baked normal maps in the blockout
    'export_gn_mesh': False,
    'export_meshopt_compression_enable': False,
    'export_meshopt_extension': 'EXT_meshopt_compression',   # never KHR (X4/GAP-9); compression itself is off
    'export_draco_mesh_compression_enable': False,
    'export_materials': 'EXPORT',
    'export_unused_images': False,
    'export_unused_textures': False,
    'export_vertex_color': 'NONE',             # deliberate: no COLOR_0 (see module doc)
    'export_all_vertex_colors': False,
    'export_active_vertex_color_when_no_material': False,
    'export_attributes': False,
    'use_mesh_edges': False,
    'use_mesh_vertices': False,
    'export_cameras': False,
    'export_lights': False,
    'use_selection': True,
    'use_visible': False,
    'use_renderable': False,
    'use_active_collection': False,
    'use_active_collection_with_nested': False,
    'use_active_scene': False,
    'collection': '',
    'at_collection_center': False,
    'export_extras': True,                     # node extras carry cell / layer / material_key
    'export_yup': True,
    'export_apply': False,                     # no modifiers in the blockout
    'export_shared_accessors': False,
    'export_animations': False,
    'export_skins': False,
    'export_morph': False,
    'export_gpu_instances': False,
    'export_hierarchy_flatten_objs': False,
    'export_hierarchy_full_collections': False,
    'export_original_specular': False,
    'will_save_settings': False,
}
SKIP_PROPS = {'filepath', 'filter_glob', 'files', 'directory', 'ui_tab', 'gltf_export_id'}


def _defaults(op):
    out = {}
    for p in op.get_rna_type().properties:
        if p.identifier in SKIP_PROPS or p.identifier == 'rna_type' or p.type in ('COLLECTION', 'POINTER'):
            continue
        if p.type == 'ENUM':
            if p.is_enum_flag:
                out[p.identifier] = set(p.default_flag)
            elif p.default:
                out[p.identifier] = p.default
            elif len(p.enum_items):
                out[p.identifier] = p.enum_items[0].identifier
        elif getattr(p, 'array_length', 0):
            out[p.identifier] = tuple(p.default_array)
        else:
            out[p.identifier] = p.default
    return out


def export_kwargs():
    base = _defaults(bpy.ops.export_scene.gltf)
    ids = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    unknown = [k for k in GLTF_OVERRIDES if k not in ids]
    if unknown:
        raise RuntimeError(f'unknown glTF export options for this Blender: {unknown}')
    base.update(GLTF_OVERRIDES)
    return base


def import_kwargs():
    base = _defaults(bpy.ops.import_scene.gltf)
    for k, v in (('merge_vertices', False), ('import_shading', 'NORMALS'), ('export_import_convert_lighting_mode', 'SPEC')):
        if k in base:
            base[k] = v
    return base


def addon_version():
    try:
        import addon_utils
        for m in addon_utils.modules():
            if m.__name__ == 'io_scene_gltf2':
                return '.'.join(str(v) for v in m.bl_info.get('version', ()))
    except Exception:
        pass
    return None


def glb_inspect(path: Path):
    data = path.read_bytes()
    jlen, _ = struct.unpack_from('<II', data, 12)
    gltf = json.loads(data[20:20 + jlen].decode('utf-8'))
    tris, prims, attrs, color0 = 0, 0, set(), 0
    for m in gltf.get('meshes', []):
        for p in m['primitives']:
            prims += 1
            attrs.update(p['attributes'].keys())
            color0 += 'COLOR_0' in p['attributes']
            if p.get('mode', 4) != 4:
                continue
            acc = gltf['accessors'][p['indices']] if 'indices' in p else gltf['accessors'][p['attributes']['POSITION']]
            tris += acc['count'] // 3
    return {'triangles': tris, 'primitives': prims, 'meshes': len(gltf.get('meshes', [])), 'nodes': len(gltf.get('nodes', [])),
            'materials': sorted(m.get('name', '') for m in gltf.get('materials', [])),
            'attributes': sorted(attrs), 'primitives_with_COLOR_0': color0,
            'extensionsUsed': gltf.get('extensionsUsed', []), 'extensionsRequired': gltf.get('extensionsRequired', []),
            'generator': gltf.get('asset', {}).get('generator'), 'copyright': gltf.get('asset', {}).get('copyright')}


def _tri_count(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def _bbox(objs):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for ob in objs:
        if ob.type != 'MESH':
            continue
        mw = ob.matrix_world
        for v in ob.data.vertices:
            w = mw @ v.co
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo, hi


def export_cells(objs, out: Path, per_cell, sha, rel, log, export_layers):
    kw = export_kwargs()
    results = {}
    cells = sorted({ob['cell'] for ob in objs if ob['cell'] != 'none'})
    for cell in cells:
        sel = [ob for ob in objs if ob['cell'] == cell and ob['layer'] in export_layers]
        root = bpy.data.objects.new(f'sunmeadow_v2_{cell}', None)
        st = bpy.data.objects.new(f'{cell}__structure', None)
        vg = bpy.data.objects.new(f'{cell}__vegetation_proxies', None)
        for e in (root, st, vg):
            bpy.context.scene.collection.objects.link(e)
        st.parent = root
        vg.parent = root
        root['cell'], root['schema'] = cell, 'xexoria.sunmeadow-v2.blockout-cell/1'
        for ob in sel:
            ob.parent = vg if ob['layer'] == 'veg' else st
        bpy.ops.object.select_all(action='DESELECT')
        for ob in sel + [root, st, vg]:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = root
        path = out / f'sunmeadow_v2_{cell}.glb'
        t = time.time()
        bpy.ops.export_scene.gltf(filepath=str(path), **kw)
        ins = glb_inspect(path)
        struct_tris = sum(_tri_count(ob) for ob in sel if ob['layer'] != 'veg')
        veg_tris = sum(_tri_count(ob) for ob in sel if ob['layer'] == 'veg')
        lo, hi = _bbox(sel)
        results[cell] = {'glb': rel(path), 'bytes': path.stat().st_size, 'sha256': sha(path),
                         'export_s': round(time.time() - t, 2), 'glb_inspect': ins,
                         'blender_triangles_structure': struct_tris, 'blender_triangles_vegetation': veg_tris,
                         'source_objects': len(sel), 'source_bbox_blender': [lo, hi],
                         'source_materials': sorted({ob.active_material.name for ob in sel if ob.active_material}),
                         **per_cell.get(cell, {})}
        for ob in sel:
            ob.parent = None
        for e in (vg, st, root):
            bpy.data.objects.remove(e, do_unlink=True)
        log(f'GLB {cell}: {ins["triangles"]} tris ({struct_tris} structure + {veg_tris} vegetation proxies), '
            f'{ins["primitives"]} primitives, attrs {ins["attributes"]}, ext {ins["extensionsUsed"]}')
    record = {k: (sorted(v) if isinstance(v, set) else v) for k, v in kw.items()}
    return results, record


def reimport_validate(results, root: Path, log):
    """Import every exported GLB into a scratch scene and compare with the source."""
    kw = import_kwargs()
    base_scene = bpy.context.window.scene if bpy.context.window else bpy.context.scene
    report = {}
    for cell, r in results.items():
        scn = bpy.data.scenes.new(f'reimport_{cell}')
        if bpy.context.window:
            bpy.context.window.scene = scn
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(root / r['glb']), **kw)
        new = [ob for ob in bpy.data.objects if ob not in before]
        meshes = [ob for ob in new if ob.type == 'MESH']
        tris = sum(_tri_count(ob) for ob in meshes)
        lo, hi = _bbox(meshes)
        slo, shi = r['source_bbox_blender']
        dev = max(max(abs(a - b) for a, b in zip(lo, slo)), max(abs(a - b) for a, b in zip(hi, shi)))
        mats = sorted({re.sub(r'\.\d{3}$', '', s.material.name) for ob in meshes for s in ob.material_slots if s.material})
        src_tris = r['blender_triangles_structure'] + r['blender_triangles_vegetation']
        ins = r['glb_inspect']
        ok = (tris == src_tris == ins['triangles'] and dev < 2e-3 and set(mats) == set(r['source_materials'])
              and ins['primitives_with_COLOR_0'] == 0 and 'KHR_meshopt_compression' not in ins['extensionsUsed'])
        report[cell] = {'objects': len(new), 'mesh_objects': len(meshes), 'triangles': tris, 'source_triangles': src_tris,
                        'glb_index_triangles': ins['triangles'], 'bbox_max_deviation_m': round(dev, 6),
                        'materials_match': set(mats) == set(r['source_materials']), 'materials': len(mats),
                        'color0_primitives': ins['primitives_with_COLOR_0'], 'pass': ok}
        for ob in new:
            bpy.data.objects.remove(ob, do_unlink=True)
        for blk in (bpy.data.meshes, bpy.data.materials):
            for d in list(blk):
                if d.users == 0:
                    blk.remove(d)
        if bpy.context.window:
            bpy.context.window.scene = base_scene
        bpy.data.scenes.remove(scn)
        log(f'REIMPORT {cell}: {tris} tris vs source {src_tris} / glb {ins["triangles"]}, bbox dev {dev:.2e} m, '
            f'materials {len(mats)} match={report[cell]["materials_match"]} -> {"PASS" if ok else "FAIL"}')
    return {'import_options': {k: (sorted(v) if isinstance(v, set) else v) for k, v in kw.items()}, 'cells': report,
            'pass': all(v['pass'] for v in report.values())}


# ----------------------------------------------------------------------------
# Collider-on-visual check (no invisible walls)
# ----------------------------------------------------------------------------

def _ray_poly_entry(o, d, poly):
    """Distance along the 2D ray o + t d to the first crossing of a convex polygon boundary (None if missed)."""
    best = None
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        e = (b[0] - a[0], b[1] - a[1])
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            continue
        w = (a[0] - o[0], a[1] - o[1])
        t = (w[0] * e[1] - w[1] * e[0]) / den
        u = (w[0] * d[1] - w[1] * d[0]) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best):
            best = t
    return best


def _ray_circle_entry(o, d, c, r):
    f = (o[0] - c[0], o[1] - c[1])
    b = f[0] * d[0] + f[1] * d[1]
    cc = f[0] ** 2 + f[1] ** 2 - r * r
    disc = b * b - cc
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t > 0 else None


def collider_visual_check(colliders, log, skip_collections=('SM2_colliders', 'SM2_annotation', 'SM2_witness')):
    """Horizontal rays at body height toward each collider; the first visible surface must sit on its boundary.

    offset = hit distance - collider boundary distance along the ray (Babylon metres):
      > 0  the visual surface is inside the collider (an invisible margin of that size),
      < 0  the visual protrudes beyond the collider.
    Water bands are probed with vertical rays: the first surface must be water or the carved bank (Y < -0.05).
    """
    vl = bpy.context.view_layer
    excluded = []
    for lc in vl.layer_collection.children:
        if lc.name in skip_collections and not lc.exclude:
            lc.exclude = True
            excluded.append(lc)
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene

    # Footprints of every collider: horizontal probes only count when they start in open (walkable) space.
    foot = []
    for c in colliders:
        if c['shape'] == 'capsule':
            cx, cz, r = c['center'][0], c['center'][2], c['radius']
            foot.append(((cx - r, cx + r, cz - r, cz + r), ('c', cx, cz, r)))
        else:
            poly = [tuple(q) for q in c['polygon_xz']]
            xs, zs = [q[0] for q in poly], [q[1] for q in poly]
            foot.append(((min(xs), max(xs), min(zs), max(zs)), ('p', poly)))

    def in_any_collider(p):
        for (x0, x1, z0, z1), f in foot:
            if x0 <= p[0] <= x1 and z0 <= p[1] <= z1:
                if f[0] == 'c':
                    if math.hypot(p[0] - f[1], p[1] - f[2]) <= f[3]:
                        return True
                elif G.point_in_polygon(p, f[1]):
                    return True
        return False

    def first_visual(origin_b, dir_b, dist, skip_layers=()):
        o = Vector(G.bl(origin_b[0], origin_b[2], origin_b[1]))
        dv = Vector(G.bl(dir_b[0], dir_b[2], dir_b[1])).normalized()
        travelled = 0.0
        for _ in range(12):
            hit, loc, nrm, idx, ob, mtx = scene.ray_cast(dg, o, dv, distance=max(0.01, dist - travelled))
            if not hit:
                return None
            layer = ob.get('layer') if ob else None
            if layer in ('annotation', 'witness') or layer in skip_layers or (ob and ob.name.startswith(('COL_', 'W_'))):
                step = (loc - o).length + 0.01
                o = loc + dv * 0.01
                travelled += step
                continue
            return (travelled + (loc - o).length, layer, ob.name if ob else None, loc)
        return None

    def under_terrain(p, hy):
        """True when relief/context terrain lies above p (the origin is inside or under a hill/cliff sheet)."""
        o = Vector(G.bl(p[0], p[1], hy))
        up = Vector((0.0, 0.0, 1.0))
        for _ in range(12):
            hit, loc, nrm, idx, ob, mtx = scene.ray_cast(dg, o, up, distance=80.0)
            if not hit:
                return False
            if ob is not None and ob.get('layer') in ('relief', 'context') and not ob.name.startswith('COL_'):
                return True
            o = loc + up * 0.01
        return False

    rows, flagged = [], []
    for c in colliders:
        cat = c['category']
        if cat == 'existing_city_hazard':
            rows.append({'id': c['id'], 'category': cat, 'status': 'live_city_owned'})
            continue
        if c['shape'] == 'capsule':
            cx, cz, r = c['center'][0], c['center'][2], c['radius']
            ext = r
            entry = lambda o, d: _ray_circle_entry(o, d, (cx, cz), r)   # noqa: E731
            poly = None
        else:
            poly = G.ccw([tuple(q) for q in c['polygon_xz']])
            cx = sum(q[0] for q in poly) / len(poly)
            cz = sum(q[1] for q in poly) / len(poly)
            ext = max(math.hypot(q[0] - cx, q[1] - cz) for q in poly)
            entry = lambda o, d, poly=poly: _ray_poly_entry(o, d, poly)   # noqa: E731
        if cat == 'water':
            samples = [(cx, cz)] + [(q[0] + 0.3 * (cx - q[0]), q[1] + 0.3 * (cz - q[1])) for q in poly]
            ok_n, layers = 0, {}
            for (x, z) in samples:
                h = first_visual((x, 1.5, z), (0.0, -1.0, 0.0), 4.0, skip_layers=('veg',))
                if h:
                    y = h[3].z
                    good = h[1] in ('water', 'rock', 'bridge') or (h[1] in ('ground', 'context') and y < -0.05)
                    ok_n += good
                    layers[h[1]] = layers.get(h[1], 0) + 1
            row = {'id': c['id'], 'category': cat, 'probe': 'vertical', 'samples': len(samples),
                   'over_water_or_bank': ok_n, 'hit_layers': layers, 'status': 'ok' if ok_n >= 0.6 * len(samples) else 'FLAG'}
            rows.append(row)
            if row['status'] != 'ok':
                flagged.append(row)
            continue
        heights = [h for h in (0.2, 1.0) if c['y_min'] + 0.05 < h < c['y_max'] - 0.02] or [max(0.05, min(0.2, c['y_max'] - 0.05))]
        offs, layers, missed, closed = [], {}, 0, 0
        for k in range(16):
            a = math.tau * k / 16
            d_out = (math.cos(a), math.sin(a))
            o = (cx + d_out[0] * (ext + 1.5), cz + d_out[1] * (ext + 1.5))
            d_in = (-d_out[0], -d_out[1])
            tb = entry(o, d_in)
            if tb is None:
                continue
            if in_any_collider(o) or under_terrain(o, heights[0]):
                closed += 1            # probe origin is not walkable space (behind a cliff, under a hill sheet, ...)
                continue
            for hy in heights:
                h = first_visual((o[0], hy, o[1]), (d_in[0], 0.0, d_in[1]), tb + 2 * ext + 1.0)
                if h is None or h[1] in ('ground', 'path'):
                    missed += 1
                    continue
                off = h[0] - tb
                if off < -0.75:            # another object in front: not this collider's visual, ignore
                    continue
                offs.append(off)
                layers[h[1]] = layers.get(h[1], 0) + 1
        offs.sort()
        med = offs[len(offs) // 2] if offs else None
        # invisible margin: how far inside the collider the nearest visible surface is, in the best-covered half
        good = [o for o in offs if o <= 0.35]
        row = {'id': c['id'], 'category': cat, 'probe': 'horizontal', 'heights_m': heights, 'rays_valid': len(offs),
               'rays_missed': missed, 'rays_from_closed_space': closed,
               'median_offset_m': round(med, 3) if med is not None else None,
               'max_offset_m': round(offs[-1], 3) if offs else None, 'share_within_0_35m': round(len(good) / len(offs), 2) if offs else 0.0,
               'hit_layers': layers, 'visual': c.get('visual')}
        if offs:
            row['status'] = 'ok' if len(good) >= 0.5 * len(offs) else 'FLAG'
        else:
            row['status'] = 'enclosed' if closed and not missed else 'FLAG'
        rows.append(row)
        if row['status'] != 'ok':
            flagged.append(row)
    for lc in excluded:
        lc.exclude = False
    cats = {}
    for r in rows:
        cs = cats.setdefault(r['category'], {'n': 0, 'flagged': 0, 'median_offsets': []})
        cs['n'] += 1
        cs['flagged'] += r.get('status') == 'FLAG'
        if r.get('median_offset_m') is not None:
            cs['median_offsets'].append(r['median_offset_m'])
    for cs in cats.values():
        mo = sorted(cs.pop('median_offsets'))
        cs['median_of_median_offset_m'] = mo[len(mo) // 2] if mo else None
        cs['worst_median_offset_m'] = mo[-1] if mo else None
    log(f'COLLIDER-VISUAL: {len(rows)} colliders, {len(flagged)} flagged; by category {json.dumps(cats)}')
    return {'method': collider_visual_check.__doc__.strip(), 'count': len(rows), 'flagged': flagged,
            'by_category': cats, 'rows': rows, 'pass': not flagged}
