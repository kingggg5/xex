"""Bounded authored traversal repairs; never overwrites the canonical city.

Load the reviewed .blend with Blender --background --factory-startup
--disable-autoexec --python this-file -- --inspect (or --repair).
All modelling changes remain in the traversal-repair-candidate directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/models/reference-city/r5/traversal-repair-candidate'
EVIDENCE = ROOT / 'planning/evidence'
EXPECTED = '9f7a55a8a0be836a5f2d42a3723253a216becd5cb0017f74ea710d4814c5e933'
sys.path.insert(0, str(ROOT / 'assets/blender/city_r5/lib'))
import citykit as ck

CHANGED = set()


def signature(obj):
    digest = hashlib.sha256()
    digest.update(str(obj.type).encode())
    digest.update(struct.pack('<16f', *(value for row in obj.matrix_world for value in row)))
    if obj.type == 'MESH':
        for vertex in obj.data.vertices:
            digest.update(struct.pack('<3f', *vertex.co))
        for polygon in obj.data.polygons:
            digest.update(struct.pack('<I', len(polygon.vertices)))
            digest.update(struct.pack('<' + 'I' * len(polygon.vertices), *polygon.vertices))
            digest.update(struct.pack('<I', polygon.material_index))
        for layer in obj.data.uv_layers:
            for item in layer.data:
                digest.update(struct.pack('<2f', *item.uv))
        for layer in obj.data.color_attributes:
            for item in layer.data:
                digest.update(struct.pack('<4f', *item.color))
        digest.update('|'.join(m.name for m in obj.data.materials if m).encode())
    return digest.hexdigest()


def remove(obj):
    CHANGED.add(obj.name)
    bpy.data.objects.remove(obj, do_unlink=True)


def ground_tree():
    obj = bpy.data.objects['terrain / grass ground']
    obj.data.calc_loop_triangles()
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return BVHTree.FromPolygons(verts, [tuple(t.vertices) for t in obj.data.loop_triangles], all_triangles=True)


def ground_y(tree, x, y, fallback=None):
    point, _, _, _ = tree.ray_cast(Vector((x, y, 100)), Vector((0, 0, -1)), 200)
    if point is None:
        if fallback is not None:
            return float(fallback)
        raise RuntimeError(f'No authored grass beneath repair witness {x}/{y}')
    return float(point.z)


def decorate(obj, bevel=.025):
    if bevel:
        ck.bevel(obj, bevel, 2, 40)
    ck.uv_box(obj)
    ck.vertex_paint(obj, ground_z=None, cavity=.18, edge=.16, jitter=.015, seed=0)
    return obj


def box(name, x0, x1, y0, y1, z0, z1, material='stone_trim_carved', bevel=.025):
    obj = ck.box(name, ((x0+x1)/2, (y0+y1)/2, (z0+z1)/2), (x1-x0, y1-y0, z1-z0), material)
    return decorate(obj, bevel)


def grand_profile(y):
    """Three real flights, with two flat 2.4 m landings."""
    cursor, level = 40.2, .08
    rise = (9.0-level)/60
    for flight in range(3):
        end = cursor + 20*.45
        if y <= end:
            return level + min(20, max(0, math.ceil((y-cursor)/.45)))*rise
        level += 20*rise
        cursor = end
        if flight < 2:
            if y <= cursor + 2.4:
                return level
            cursor += 2.4
    return 9.0


def rebuild_grand_stairs():
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith(('castle grand stair tread', 'castle stair landing')):
            remove(obj)
    cursor, level = 40.2, .08
    rise = (9.0-level)/60
    for flight in range(3):
        # Real load-bearing stone mass rather than suspended treads.
        y0,y1 = cursor,cursor+9.0
        z0,z1 = level-.10,level+20*rise-.10
        verts = [(-8.55,y0,-.35),(8.55,y0,-.35),(8.55,y1,-.35),(-8.55,y1,-.35),
                 (-8.55,y0,z0),(8.55,y0,z0),(8.55,y1,z1),(-8.55,y1,z1)]
        faces = [(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(3,2,1,0)]
        core = ck.new_object(f'castle grand stair masonry core {flight+1}',verts,faces,'stone_wall_warm')
        decorate(core,0)
        for i in range(20):
            top = level + (i+1)*rise
            box(f'traversal / castle flight {flight+1} tread {i+1:02d}', -8.6, 8.6,
                cursor+i*.45, cursor+(i+1)*.45+.075, max(-.35, top-.30), top)
        level += 20*rise
        cursor += 9.0
        if flight < 2:
            box(f'traversal / castle landing {flight+1}', -10.5, 10.5, cursor, cursor+2.4+.075,
                -.35, level, 'plaza_flagstone', .025)
            cursor += 2.4
    # Existing rail detail follows the repaired real flight rather than the old
    # overlapping steps. Their world UVs change only because these rails move.
    for obj in list(bpy.context.scene.objects):
        if not obj.name.startswith(('castle stair stone handrail', 'castle stair baluster', 'castle stair lamp')):
            continue
        CHANGED.add(obj.name)
        prefix,index = obj.name.rsplit('.',1) if '.' in obj.name else (obj.name,'0')
        index = int(index)
        divisor = 2 if obj.name.startswith('castle stair stone handrail') else 18 if obj.name.startswith('castle stair baluster') else 4
        flight = index//divisor
        old_start = 42.0 + 12*flight
        new_start = 40.2 + 11.4*flight
        bb = bounds(obj)
        old_center_y = (bb['min'][1]+bb['max'][1])/2
        new_center_y = new_start + .75*(old_center_y-old_start)
        offset = None
        if obj.name.startswith('castle stair lamp crystal'):
            offset = grand_profile(new_center_y)+.88-bb['min'][2]
        elif obj.name.startswith(('castle stair lamp foot','castle stair baluster')):
            offset = grand_profile(new_center_y)+.005-bb['min'][2]
        inverse = obj.matrix_world.inverted()
        for vertex in obj.data.vertices:
            p = obj.matrix_world @ vertex.co
            old_y = p.y
            new_y = new_start + .75*(old_y-old_start)
            # Rails follow each shortened flight; pedestals and balusters plant
            # on an actual tread, and every crystal sits above its lamp foot.
            continuous = .08 + (flight+(new_y-new_start)/9)*(9.0-.08)/3
            p.z += offset if offset is not None else continuous - (old_y-42.0)/4
            p.y = new_y
            vertex.co = inverse @ p
        obj.data.update()
        ck.uv_box(obj)
    for flight,y0 in enumerate((49.2,60.6)):
        z = .08+(flight+1)*(9.0-.08)/3
        for side in (-1,1):
            x = side*8.85
            box(f'castle stair stone handrail landing {flight+1} {side:+d}',x-.325,x+.325,y0,y0+2.4,
                z+.51,z+1.09,'stone_trim_carved',.025)


def replace_notched_slab(name, notch_end=78.26, half_width=8.62):
    obj = bpy.data.objects[name]
    old = bounds(obj)
    (x0,y0,z0), (x1,y1,z1) = old['min'], old['max']
    material = obj.data.materials[0].name
    pieces = [box(name + ' repair-left', x0,-half_width,y0,y1,z0,z1,material,.035),
              box(name + ' repair-right',half_width,x1,y0,y1,z0,z1,material,.035),
              box(name + ' repair-back',-half_width,half_width,notch_end,y1,z0,z1,material,.035)]
    remove(obj)
    joined = ck.join(pieces, name)
    CHANGED.add(name)
    return joined


def repair_castle_entry():
    # All three old solid slabs would otherwise cut through the new steps.
    for name in ('castle lower plinth', 'castle plinth moulding', 'castle terrace paving'):
        replace_notched_slab(name)
    start, end = 72.01, 78.27
    count = 10
    rise = (11.26-9.0)/count
    for i in range(count):
        top = 9.0+(i+1)*rise
        box(f'traversal / castle entry tread {i+1:02d}',-8.6,8.6,
            start+(end-start)*i/count,start+(end-start)*(i+1)/count+.075,
            top-.34,top,'plaza_flagstone',.02)


def split_polygon(poly, axis, limit, keep_positive):
    """Clip in 2D stair coordinates while preserving exact world positions."""
    out = []
    def value(p): return p[axis]-limit
    def inside(p): return value(p) >= -1e-7 if keep_positive else value(p) <= 1e-7
    for a,b in zip(poly,poly[1:]+poly[:1]):
        ia, ib = inside(a), inside(b)
        if ia: out.append(a)
        if ia != ib:
            va,vb = value(a),value(b)
            t = va/(va-vb)
            out.append(a+(b-a)*t)
    return out


def cut_wizard_notch():
    obj = bpy.data.objects['terrain / wizard terrace / top']
    CHANGED.add(obj.name)
    a,b = Vector((-51,61.2,0)),Vector((-57.6,70.5,0))
    d = (b-a).normalized()
    side = Vector((-d.y,d.x,0))
    length = (b-a).length
    obj.data.calc_loop_triangles()
    verts,faces = [],[]
    def stair_coords(p):
        q = p-a
        return Vector((q.dot(d),q.dot(side),p.z))
    def world(p): return a+d*p.x+side*p.y+Vector((0,0,p.z))
    # Sequentially separate all parts outside a convex rectangle. Any remainder
    # inside it is discarded, making a genuine terrace opening over the flight.
    constraints = [(0,-.5,True),(0,length+.025,False),(1,-3.03,True),(1,3.03,False)]
    for triangle in obj.data.loop_triangles:
        pending = [stair_coords(obj.matrix_world @ obj.data.vertices[i].co) for i in triangle.vertices]
        outside = []
        for axis,limit,positive in constraints:
            if len(pending) < 3: break
            rejected = split_polygon(pending,axis,limit,not positive)
            if len(rejected) >= 3: outside.append(rejected)
            pending = split_polygon(pending,axis,limit,positive)
        for polygon in outside:
            start = len(verts)
            verts.extend(tuple(world(p)) for p in polygon)
            faces.append(tuple(range(start,start+len(polygon))))
    mesh = bpy.data.meshes.new(obj.name+' stair opening')
    mesh.from_pydata(verts,[],faces)
    mesh.materials.append(obj.data.materials[0])
    old = obj.data
    obj.data = mesh
    obj.matrix_world = Matrix.Identity(4)
    for p in obj.data.polygons:
        if p.normal.z < 0: p.flip()
    ck.uv_box(obj)
    ck.ensure_white_vertex_colors(obj)
    if old.users == 0: bpy.data.meshes.remove(old)
    # Correct clockwise authored top normals on the actual stairs. No hidden
    # ramp is added, and their existing 0.285 m discrete risers remain.
    stairs = bpy.data.objects['terrain / wizard stairs']
    CHANGED.add(stairs.name)
    for polygon in stairs.data.polygons:
        if polygon.normal.z < -.98:
            polygon.flip()
    stairs.data.update()


def repair_wizard_entry():
    tower = bpy.data.objects['observatory tapered tower']
    bb = bounds(tower)
    terrace = bounds(bpy.data.objects['terrain / wizard terrace / top'])
    body_bottom = bb['min'][2]
    terrace_top = terrace['max'][2]
    if abs(body_bottom-terrace_top) > .0001:
        raise RuntimeError('Measured wizard tower no longer contacts its terrace; re-audit before designing its foundation.')
    cx = (bb['min'][0]+bb['max'][0])/2
    cy = (bb['min'][1]+bb['max'][1])/2
    old = [obj for obj in bpy.context.scene.objects if obj.name.startswith('wizard gate stair')]
    if len(old) != 7:
        raise RuntimeError('Wizard entry staircase identity changed.')
    old_steps = [{'name':obj.name,'bounds_blender':bounds(obj)} for obj in old]
    for obj in old: remove(obj)
    start,end = cy-14.55,cy-8.95
    width = 6.8
    rise = .22
    for i in range(7):
        top = terrace_top+(i+1)*rise
        box(f'traversal / wizard entry tread {i+1:02d}',cx-width/2,cx+width/2,
            start+i*.8,start+(i+1)*.8+.075,top-.32,top,'stone_trim_carved',.025)
    # The original gate stairs climbed away from the tower and were suspended.
    # This body supports the true ascending flight without moving the tower.
    base = terrace_top-.35
    verts = [(cx-width/2,start,base),(cx+width/2,start,base),(cx+width/2,end,base),(cx-width/2,end,base),
             (cx-width/2,start,terrace_top-.10),(cx+width/2,start,terrace_top-.10),
             (cx+width/2,end,terrace_top+7*rise-.10),(cx-width/2,end,terrace_top+7*rise-.10)]
    core = ck.new_object('wizard entry masonry stair core',verts,
        [(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(3,2,1,0)],'stone_wall_warm')
    decorate(core,0)
    box('traversal / wizard entry top landing',cx-width/2,cx+width/2,end,end+.40,
        base,terrace_top+7*rise,'plaza_flagstone',.025)
    return {'tower_body_base_m':body_bottom,'terrace_top_m':terrace_top,'measured_tower_gap_m':body_bottom-terrace_top,
            'tower_pose_unchanged':True,'actual_defect':'Seven gate stair boxes rose away from the tower with no supporting core.',
            'old_entry_steps':old_steps,'repaired_entry':{'start_runtime_xz':[cx,176+start],'end_runtime_xz':[cx,176+end],
                'width_m':width,'risers':7,'rise_m':rise,'top_y_m':terrace_top+7*rise}}


def repair_hollow_fountain_caps():
    """Remove only centred closure disks; retain basin floors and wall skins."""
    rows = []
    names = ['fountain mosaic inner lip','fountain second bowl','fountain upper chalice']
    names += [o.name for o in bpy.context.scene.objects if o.name.startswith(('wizard rune ring ','portal luminous rune ring '))]
    for name in names:
        obj = bpy.data.objects[name]
        annulus = name=='fountain mosaic inner lip' or name.startswith(('wizard rune ring ','portal luminous rune ring '))
        caps = []
        for polygon in obj.data.polygons:
            if len(polygon.vertices)<16: continue
            points = [obj.matrix_world @ obj.data.vertices[i].co for i in polygon.vertices]
            normal = (obj.matrix_world.to_3x3().inverted().transposed() @ polygon.normal).normalized()
            horizontal = max(p.z for p in points)-min(p.z for p in points) < .0001 and abs(normal.z)>.999
            if horizontal and (annulus or normal.z>0):
                caps.append({'index':polygon.index,'height_m':sum(p.z for p in points)/len(points),
                             'vertices':len(points),'normal_z':normal.z})
        expected = 2 if annulus else 1
        if len(caps)!=expected:
            raise RuntimeError(f'Exact inappropriate-cap identity changed for {name}: {caps}')
        CHANGED.add(name)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        selected = [bm.faces[c['index']] for c in caps]
        bmesh.ops.delete(bm,geom=selected,context='FACES_ONLY')
        added_inner_faces = 0
        if annulus:
            bm.verts.ensure_lookup_table()
            # citykit.lathe stores four profile points for each angular sector.
            if len(bm.verts)%4:
                raise RuntimeError(f'Annular four-point profile changed: {name}')
            sectors = len(bm.verts)//4
            for s in range(sectors):
                next_s = (s+1)%sectors
                bm.faces.new([bm.verts[s*4+3],bm.verts[next_s*4+3],bm.verts[next_s*4],bm.verts[s*4]])
                added_inner_faces += 1
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()
        if annulus:
            ck.uv_box(obj)
            ck.vertex_paint(obj,ground_z=None,jitter=.015,cavity=.12,edge=.1,seed=0)
        rows.append({'object':name,'removed_center_disk_caps':caps,'annular_inner_wall_quads_added':added_inner_faces,
                     'walls_preserved':True,'basin_bottom_preserved':not annulus})
    lower = bpy.data.objects['fountain carved lower basin']
    floor_caps = [p for p in lower.data.polygons if len(p.vertices)>=16 and p.normal.z>.999]
    if len(floor_caps)!=1:
        raise RuntimeError('Lower basin structural floor identity changed.')
    floor_z = sum((lower.matrix_world @ lower.data.vertices[i].co).z for i in floor_caps[0].vertices)/len(floor_caps[0].vertices)
    return {'repaired':rows,'lower_basin_floor_preserved_y_m':floor_z,
            'fountain_rule':'Keep bowl side skins and bottom support caps; remove only top opening disks.',
            'annulus_rule':'Closed inner wall replaces centred disks; original outside/top/bottom annular faces remain.'}


def repair_bridges(tree):
    roots = [bpy.data.objects[n] for n in ('kit_canal_bridge','kit_ring_bridge')]
    for root in roots:
        deck = [o for o in bpy.context.scene.objects if o.parent == root and o.name.startswith('bridge dressed flagstone')]
        if len(deck) != 16:
            raise RuntimeError('Bridge deck identity changed.')
        b = [bounds(o) for o in deck]
        cx = root.matrix_world.translation.x
        cy = root.matrix_world.translation.y
        # Original boxes overlapped .12 m; use their authored nominal lengths.
        length = 20.0 if root.name == 'kit_canal_bridge' else 18.0
        width = 10.0 if root.name == 'kit_canal_bridge' else 8.0
        # End the solid parapet before the longitudinal bank promenade so a
        # capsule can pass its junction in either direction. These are real
        # capped cuts, not excluded collision geometry.
        for obj in list(bpy.context.scene.objects):
            if obj.parent != root or not obj.name.startswith(('bridge parapet panel','bridge pale coping')):
                continue
            world_bounds = bounds(obj)
            side = -1 if world_bounds['min'][0] < cx-length/2+.70 else 1 if world_bounds['max'][0] > cx+length/2-.70 else None
            if side is None: continue
            CHANGED.add(obj.name)
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.transform(obj.matrix_world)
            result = bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                plane_co=Vector((cx+side*(length/2-.70),0,0)),plane_no=Vector((side,0,0)),
                clear_outer=True,clear_inner=False,dist=.000001)
            border = [edge for edge in result['geom_cut'] if isinstance(edge,bmesh.types.BMEdge) and edge.is_boundary]
            if border: bmesh.ops.holes_fill(bm,edges=border,sides=0)
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
            bm.transform(obj.matrix_world.inverted())
            bm.to_mesh(obj.data)
            bm.free()
            ck.uv_box(obj)
        for obj in deck: remove(obj)
        verts,faces = [],[]
        count = 32
        for i in range(count):
            x0 = cx-length/2+length*i/count
            x1 = cx-length/2+length*(i+1)/count
            z0 = .15 + 2.92*math.sin(math.pi*i/count)
            z1 = .15 + 2.92*math.sin(math.pi*(i+1)/count)
            start = len(verts)
            verts += [(x0,cy-width/2,z0-.68),(x1,cy-width/2,z1-.68),(x1,cy+width/2,z1-.68),(x0,cy+width/2,z0-.68),
                      (x0,cy-width/2,z0),(x1,cy-width/2,z1),(x1,cy+width/2,z1),(x0,cy+width/2,z0)]
            faces += [tuple(start+n for n in f) for f in [(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(3,2,1,0)]]
        obj = ck.new_object(f'traversal / {root.name} continuous stone deck',verts,faces,'plaza_flagstone')
        decorate(obj,0)
        for sign in (-1,1):
            # Four-metre bank apron follows actual ground across its breadth.
            verts,faces = [],[]
            for i in range(9):
                t = i/8
                x = cx+sign*(length/2+4*(1-t))
                for j in range(5):
                    y = cy-width/2+width*j/4
                    ground = ground_y(tree,x,y)
                    height = ground+.055 if i==0 else (1-t)*(ground+.055)+t*.15
                    verts.append((x,y,height))
            for i in range(8):
                for j in range(4):
                    v = i*5+j
                    face = (v,v+5,v+6,v+1)
                    faces.append(face if sign < 0 else tuple(reversed(face)))
            apron = ck.new_object(f'traversal / {root.name} bank apron {sign:+d}',verts,faces,'plaza_flagstone')
            decorate(apron,0)


def repair_paths(tree):
    sys.path.insert(0,str(ROOT / 'assets/blender/city_r5/kits'))
    from terrain import TerrainBuilder
    import numpy as np
    authored = TerrainBuilder(json.loads((ROOT / 'assets/blender/city_r5/layout.json').read_text(encoding='utf-8')),None)
    names = ['terrain / path windmill_path','terrain / path south_ring_road',
             'terrain / canal promenade -1','terrain / canal promenade +1']
    rows = []
    for name in names:
        obj = bpy.data.objects[name]
        CHANGED.add(name)
        before = len(obj.data.polygons)
        if name.endswith('windmill_path'):
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=6,use_grid_fill=True)
            bm.to_mesh(obj.data)
            bm.free()
        inverse = obj.matrix_world.inverted()
        max_move = 0
        analytic_fallbacks = 0
        for vertex in obj.data.vertices:
            p = obj.matrix_world @ vertex.co
            old = p.z
            hit, _, _, _ = tree.ray_cast(Vector((p.x,p.y,100)),Vector((0,0,-1)),200)
            if hit is None:
                # Pond and plaza cut-outs intentionally have no grass triangle.
                # Use the same authored height function at those witnesses.
                p.z = float(authored.h(np.array([p.x]),np.array([p.y]),with_edge=False)[0])+.13
                analytic_fallbacks += 1
            else:
                p.z = hit.z+.13
            max_move = max(max_move,abs(p.z-old))
            vertex.co = inverse @ p
        obj.data.update()
        if name.endswith('windmill_path'):
            # Real paved slab, including underside and edge thickness, over the
            # middle garden pool. The top is the very same graded path surface.
            verts = [tuple(vertex.co) for vertex in obj.data.vertices]
            count = len(verts)
            faces = [tuple(p.vertices) for p in obj.data.polygons]
            edges = {}
            for polygon in faces:
                for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                    key = tuple(sorted((a,b)))
                    edges.setdefault(key,[]).append((a,b))
            verts += [(x,y,z-.24) for x,y,z in verts]
            solid_faces = faces + [tuple(i+count for i in reversed(face)) for face in faces]
            solid_faces += [(b,a,a+count,b+count) for users in edges.values() if len(users)==1 for a,b in users]
            mesh = bpy.data.meshes.new('windmill path exposed solid paving')
            mesh.from_pydata(verts,[],solid_faces)
            mesh.materials.append(obj.data.materials[0])
            old = obj.data
            obj.data = mesh
            ck.uv_box(obj)
            ck.ensure_white_vertex_colors(obj)
            if old.users==0: bpy.data.meshes.remove(old)
        rows.append({'path': name,'polygons_before':before,'polygons_after':len(obj.data.polygons),'max_vertex_adjustment_m':max_move,
                     'analytic_height_fallbacks_for_authored_grass_cutouts':analytic_fallbacks})
        curb = bpy.data.objects.get(name+' curb')
        if curb:
            CHANGED.add(curb.name)
            # All curb vertices inherit the nearest path-bed displacement.
            inverse = curb.matrix_world.inverted()
            for vertex in curb.data.vertices:
                p = curb.matrix_world @ vertex.co
                fallback = float(authored.h(np.array([p.x]),np.array([p.y]),with_edge=False)[0])
                p.z = max(p.z,ground_y(tree,p.x,p.y,fallback=fallback)+.035)
                vertex.co = inverse @ p
            curb.data.update()
    return rows


def move_gate_oak(tree):
    names = ['oak tree trunk.035'] + [f'oak tree branch.{i:03d}' for i in range(140,144)] + [f'oak tree canopy cluster.{i:03d}' for i in range(280,288)]
    parts = [bpy.data.objects[name] for name in names]
    if any(o.parent is None or o.parent.name != 'kit_city_vegetation' for o in parts):
        raise RuntimeError('Gate oak assembly ownership is ambiguous.')
    trunk_bounds = bounds(parts[0])
    x = sum((trunk_bounds['min'][0],trunk_bounds['max'][0]))/2
    y = sum((trunk_bounds['min'][1],trunk_bounds['max'][1]))/2
    if abs(x-10.1)>3 or abs(y+147.7)>3:
        raise RuntimeError('Gate oak trunk no longer matches the collision witness.')
    for obj in parts:
        bb = bounds(obj)
        if not (bb['min'][0] < x+8 and bb['max'][0] > x-8 and bb['min'][1] < y+8 and bb['max'][1] > y-8):
            raise RuntimeError(f'An oak component does not belong to gate tree: {obj.name}')
    target = (25.0,-136.0)
    delta = Vector((target[0]-x,target[1]-y,ground_y(tree,*target)-trunk_bounds['min'][2]))
    for obj in parts:
        CHANGED.add(obj.name)
        matrix = obj.matrix_world.copy()
        matrix.translation += delta
        obj.matrix_world = matrix
    return {'assembly': names,'from_runtime_xz':[x,176+y],'to_runtime_xz':[target[0],176+target[1]],'delta_blender':list(delta)}


def repair(source):
    OUT.mkdir(parents=True,exist_ok=True)
    snapshots = {o.name: signature(o) for o in bpy.context.scene.objects}
    roots = {o.name: list(sum((list(row) for row in o.matrix_world),[])) for o in bpy.context.scene.objects if o.type=='EMPTY' and o.name.startswith('kit_')}
    old_triangles = ck.triangle_count([o for o in bpy.context.scene.objects if o.type=='MESH'])
    tree = ground_tree()
    rebuild_grand_stairs()
    repair_castle_entry()
    cut_wizard_notch()
    wizard_entry = repair_wizard_entry()
    fountain_caps = repair_hollow_fountain_caps()
    repair_bridges(tree)
    paths = repair_paths(tree)
    tree_move = move_gate_oak(tree)
    bpy.context.view_layer.update()
    failures = [name for name,digest in snapshots.items() if name not in CHANGED and
                (bpy.data.objects.get(name) is None or signature(bpy.data.objects[name]) != digest)]
    if failures:
        raise RuntimeError(f'Unrelated geometry, UV, color, material or pose changed: {failures[:10]}')
    roots_after = {o.name: list(sum((list(row) for row in o.matrix_world),[])) for o in bpy.context.scene.objects if o.type=='EMPTY' and o.name.startswith('kit_')}
    if roots_after != roots:
        raise RuntimeError('An authored kit root moved.')
    new_triangles = ck.triangle_count([o for o in bpy.context.scene.objects if o.type=='MESH'])
    if new_triangles-old_triangles > 12000:
        raise RuntimeError('Traversal repair exceeded its 12k triangle delta budget.')
    bpy.context.preferences.filepaths.save_version = 0
    candidate = OUT / 'reference_city_walk_repaired.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate),check_existing=False,relative_remap=False,copy=True)
    if sha(source) != EXPECTED:
        raise RuntimeError('Canonical source was changed during candidate repair.')
    receipt = {'schema':'xexoria.city-floor-alignment/1','status':'CANDIDATE_REQUIRES_ROUTE_AND_VISUAL_REVIEW',
               'source':str(source),'source_sha256':EXPECTED,'candidate':str(candidate),'candidate_sha256':sha(candidate),
               'changed_original_objects':sorted(CHANGED),'unrelated_objects_verified':len(snapshots)-len(CHANGED),
               'kit_root_matrices_preserved':True,'unrelated_mesh_uv_color_material_pose_preserved':True,
               'source_triangles_before':old_triangles,'candidate_triangles':new_triangles,'triangle_delta':new_triangles-old_triangles,
               'paths':paths,'gate_oak':tree_move,'wizard_entry':wizard_entry,'hollow_fountain_caps':fountain_caps,
               'design':['Three real grand stair flights, 60 risers of 0.14867 m and two 2.4 m landings; termination at terrace front.',
                         'Notched lower plinth, moulding and forecourt, with ten visible 0.226 m entry steps.',
                         'Wizard terrace top has a genuine stair opening; existing stair top normals corrected.',
                         'Wizard tower body already contacts terrace exactly; its seven reversed floating gate steps now rise toward the tower on solid masonry.',
                         'Fountain openings retain bowl floors but lose opaque centred cap disks; gold/portal/wizard rings gain true annular inner walls.',
                         'Curved masonry bridge decks with matching textured apron grades replace large discrete box ledges.',
                         'Path vertices follow the authored grass with 0.13 m paving-bed clearance; source texture palettes reused.'],
               'limits':['No canonical source/runtime promotion.', 'Blender structural checks do not establish Babylon GPU art quality.',
                         'Height probes must be followed by capsule and blocker tests.']}
    write('city-floor-alignment-20261001-candidate.json',receipt)
    print(json.dumps({k:receipt[k] for k in ('candidate','candidate_sha256','triangle_delta','unrelated_objects_verified')}))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(obj):
    p = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return {'min': [min(v[i] for v in p) for i in range(3)],
            'max': [max(v[i] for v in p) for i in range(3)]}


def write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def inspect(source):
    rows = []
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and (obj.name.startswith(('castle ', 'bridge ', 'terrain / wizard', 'terrain / castle','observatory tapered tower','wizard gate stair'))
                                    or ('oak ' in obj.name and abs(obj.matrix_world.translation.x - 10.1) < 20
                                        and abs(obj.matrix_world.translation.y + 147.7) < 20)
                                    or obj.name == 'terrain / grass ground'):
            rows.append({'name': obj.name, 'bounds_blender': bounds(obj),
                         'polygons': len(obj.data.polygons), 'parent': obj.parent.name if obj.parent else None,
                         'materials': [m.name for m in obj.data.materials if m]})
    write('city-floor-alignment-20261001-inspect.json', {'source_sha256': sha(source), 'objects': rows})
    print(json.dumps({'objects': len(rows), 'source_sha256': sha(source)}))


def reload_textures_absolute():
    sys.path.insert(0,str(ROOT/'assets/blender/city_r5'))
    import export_runtime_r5 as exporter
    records = []
    used = {n.image.name:n.image for m in bpy.data.materials if m.use_nodes and m.node_tree
            for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image}
    for image in used.values():
        name = image.name if image.name.lower().endswith(('.png','.jpg','.jpeg','.tif','.tiff','.exr')) else Path(image.filepath).name
        base = exporter.QUATERNIUS_TEXTURES if name in exporter.QUATERNIUS_TEXTURE_NAMES else exporter.TEXTURES
        path = base/name
        if not path.is_file(): raise RuntimeError(f'Missing authored texture {path}')
        image.filepath = str(path.resolve())
        image.reload()
        if image.size[0] <=0: raise RuntimeError(f'Texture decode failed {path}')
        records.append({'name':image.name,'path':path.relative_to(ROOT).as_posix(),'width':image.size[0],'height':image.size[1]})
    return records


def export_model(mode):
    receipt = json.loads((EVIDENCE/'city-floor-alignment-20261001-candidate.json').read_text(encoding='utf-8'))
    candidate = Path(bpy.data.filepath).resolve()
    if candidate != Path(receipt['candidate']).resolve() or sha(candidate)!=receipt['candidate_sha256']:
        raise RuntimeError('Export only the exact verified traversal candidate.')
    if sha(Path(receipt['source'])) != EXPECTED:
        raise RuntimeError('Canonical source changed during candidate review.')
    sys.path.insert(0,str(ROOT/'assets/blender/city_r5'))
    if mode=='source':
        import export_source_r5 as exporter
    else:
        import export_runtime_r5 as exporter
    exporter.MASTER = candidate
    exporter.refresh_texture_images = reload_textures_absolute
    stats = OUT/f'city-{mode}.stats.json'
    sys.argv = [sys.argv[0],'--','--candidate',str(OUT/f'city-{mode}.glb'),'--stats',str(stats)]
    exporter.main()
    result = json.loads(stats.read_text(encoding='utf-8'))
    write(f'city-floor-alignment-20261001-{mode}.json',result)


def render_reviews():
    reload_textures_absolute()
    scene = ck.render_settings(res=(960,640),samples=8,threads=4)
    scene.render.image_settings.file_format = 'PNG'
    camera_data = bpy.data.cameras.new('Traversal review camera')
    camera = bpy.data.objects.new('Traversal review camera',camera_data)
    scene.collection.objects.link(camera)
    camera_data.clip_start,camera_data.clip_end = .1,2000
    scene.camera = camera
    views = [('grand-player',(11,31,8),(0,61,5.2),32),
             ('grand-side',(28,58,10),(0,58,4.5),34),
             ('castle-entry-close',(10,70,16),(0,78,10.8),32),
             ('wizard-side',(-39,58,12),(-57,67,4),36),
             ('bridge-side',(15,-89,7),(0,-74,1.3),36),
             ('bridge-player',(-17,-77,3.2),(0,-74,2),30),
             ('windmill-path-close',(44,42,8),(55,61,2.6),35)]
    views += [('fountain-player',(17,-20,10),(0,0,6),32),
              ('fountain-basins-close',(12,-12,13),(0,0,4),38)]
    records = []
    for name,location,target,lens in views:
        camera.location = location
        camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
        camera_data.lens = lens
        path = EVIDENCE/f'city-floor-alignment-20261001-{name}.png'
        ck.render(path)
        records.append({'view':name,'camera_blender':location,'target_blender':target,'lens':lens,'image':str(path)})
    write('city-floor-alignment-20261001-renders.json',{'source':bpy.data.filepath,'source_saved':False,'renderer':'Cycles CPU','samples':8,'views':records,
          'limitation':'Offline authored-geometry review; runtime Babylon camera and materials must be checked separately.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--repair', action='store_true')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--export-source', action='store_true')
    parser.add_argument('--export-runtime', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    source = Path(bpy.data.filepath).resolve()
    if not source.is_relative_to(ROOT) or source.suffix != '.blend':
        raise RuntimeError('Load a reviewed project Blender source.')
    if args.inspect:
        inspect(source)
        return
    if args.repair:
        if sha(source) != EXPECTED:
            raise RuntimeError('Canonical source changed: do not repair an unreviewed input.')
        repair(source)
    if args.render:
        render_reviews()
    if args.export_source:
        export_model('source')
    if args.export_runtime:
        export_model('runtime')


if __name__ == '__main__':
    main()
