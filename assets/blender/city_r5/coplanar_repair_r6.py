"""Seed-free, bounded source geometry repair for visible R6 overlap families.

Only moves vertices of polygons participating in the named overlaps. The lower
surface is recessed 8 mm into its own solid. No meshes, materials, faces or
triangles are added/deleted. Adjacent faces follow their shared vertices, so the
closed kit remains closed. Fresh traversal extraction is mandatory after use.
"""
from collections import defaultdict
import numpy as np
import bpy
import lint_placement as lint


def loser(names):
    a, b = names
    if any(n.startswith('town gate round tower') for n in names):
        for n in names:
            if n in ('gate west pier', 'gate east pier'): return n
    if set(names) == {'castle rear cloister', 'castle terrace paving'}:
        return 'castle rear cloister'
    if any(n.startswith('terrain / channel coping') for n in names):
        for n in names:
            if n.startswith('terrain / channel wall'): return n
    if 'terrain / grass ground' in names and any(n.startswith(('terrain / path market square', 'terrain / avenue west_smithy')) for n in names):
        return 'terrain / grass ground'
    if set(names) == {'terrain / avenue southeast_potion', 'terrain / path market square'}:
        return 'terrain / avenue southeast_potion'
    return None


def repair(delta_m=0.008):
    if not 0.004 <= delta_m <= 0.012:
        raise ValueError('Bounded inset must be 4–12 mm')
    profile = lint.PROFILES['city']
    objs = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not profile['skip'].search(o.name) and len(o.data.polygons)]
    parts = [lint.Part(o, i) for i, o in enumerate(objs)]
    detail = []
    lint.coplanar_overlaps(parts, lambda *_:None, detail=detail)
    selected = defaultdict(set)
    pairs = defaultdict(float)
    for (oa, ob), (ta, tb), area in detail:
        names = (parts[oa].name, parts[ob].name)
        target = loser(names)
        if target is None: continue
        oi, ti = (oa, ta) if parts[oa].name == target else (ob, tb)
        selected[oi].add(parts[oi].obj.data.loop_triangles[ti].polygon_index)
        pairs[' x '.join(names)] += area
    records = []
    for oi in sorted(selected, key=lambda i: parts[i].name):
        p = parts[oi]
        o = p.obj
        if o.data.users > 1: o.data = o.data.copy()
        me = o.data
        normals = defaultdict(list)
        for pi in sorted(selected[oi]):
            polygon = me.polygons[pi]
            points = p.verts[list(polygon.vertices)]
            n = np.cross(points[1]-points[0],points[2]-points[0])
            length = np.linalg.norm(n)
            if length < 1e-12: raise RuntimeError(f'Degenerate selected face: {o.name}:{pi}')
            n /= length
            for vi in polygon.vertices: normals[vi].append(n)
        w = p.verts.copy()
        max_move = 0.0
        for vi, ns in sorted(normals.items()):
            # Averaging shared edge normals preserves watertight joins; its
            # projected separation remains above the 2 mm overlap tolerance.
            move = -np.mean(ns,axis=0)*delta_m
            w[vi] += move
            max_move = max(max_move,float(np.linalg.norm(move)))
        inv = np.array(o.matrix_world.inverted())
        local = w @ inv[:3,:3].T + inv[:3,3]
        me.vertices.foreach_set('co',local.reshape(-1))
        me.update()
        records.append({'object':o.name,'polygons':len(selected[oi]),'vertices':len(normals),'max_move_m':round(max_move,6)})
    bpy.context.view_layer.update()
    return {'delta_m':delta_m,'objects':records,'pairs_before':[{ 'pair':k,'area_m2':round(v,6)} for k,v in sorted(pairs.items())],
            'note':'Named visible overlap families only; topology/material count preserved; source support geometry changes exported with fresh matching traversal.'}
