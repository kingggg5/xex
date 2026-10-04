"""Restore complete market assemblies and author real gate-bank arrivals.

Writes only a new market-repair candidate. Load canonical .blend with
--factory-startup --disable-autoexec, then use --repair. Export/review operations
must separately load the candidate recorded in its receipt.
"""
from __future__ import annotations
import argparse
from array import array
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/'assets/models/reference-city/r5/reference_city.blend'
EXPECTED='6a12e74fcc5e13e33a50f11159ace36795f750319cbfe32336c33013259a5b3b'
OUT=ROOT/'assets/models/reference-city/r5/market-repair-candidate'
EVIDENCE=ROOT/'planning/evidence'
RECEIPT=EVIDENCE/'city-market-placement-repair-20261001.json'
sys.path.insert(0,str(ROOT/'assets/blender/city_r5/lib'))
import citykit as ck

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def geometry(obj):
    h=hashlib.sha256()
    mesh=obj.data
    for items,attribute,width,code in [(mesh.vertices,'co',3,'f'),(mesh.loops,'vertex_index',1,'i'),(mesh.polygons,'material_index',1,'i')]:
        data=array(code,[0])*(len(items)*width)
        items.foreach_get(attribute,data)
        h.update(data.tobytes())
    for layer in mesh.uv_layers:
        h.update(layer.name.encode())
        data=array('f',[0])*(len(layer.data)*2)
        layer.data.foreach_get('uv',data)
        h.update(data.tobytes())
    for layer in mesh.color_attributes:
        h.update(f'{layer.name}/{layer.domain}/{layer.data_type}'.encode())
        data=array('f',[0])*(len(layer.data)*4)
        layer.data.foreach_get('color',data)
        h.update(data.tobytes())
    h.update('|'.join(m.name for m in mesh.materials if m).encode())
    return h.hexdigest()
def pose(obj): return tuple(round(float(v),7) for row in obj.matrix_world for v in row)
def runtime(p): return [float(p.x),float(p.z),176+float(p.y)]
def bounds(obj):
    points=[runtime(obj.matrix_world@Vector(v)) for v in obj.bound_box]
    return {'min':[min(p[i] for p in points) for i in range(3)],'max':[max(p[i] for p in points) for i in range(3)]}

def apron(tree,side):
    n,m=16,4
    vertices=[]
    for i in range(n+1):
        t=i/n
        runtime_z=8+16*t
        inner=(1-t)*6.85+t*6.90
        outer=(1-t)*13.35+t*13.30
        for j in range(m+1):
            x=side*(inner+(outer-inner)*j/m)
            end_x=side*(6.9+6.4*j/m)
            # Move ray witnesses just inside the existing boundary to avoid
            # precision misses on its outer edge, retaining the edge geometry.
            end_x=math.copysign(min(13.2999,max(6.9001,abs(end_x))),side)
            hit,_,_,_=tree.ray_cast(Vector((end_x,-152,100)),Vector((0,0,-1)),200)
            if hit is None: raise RuntimeError('Existing promenade has no actual attachment surface.')
            height=t*hit.z
            vertices.append((x,runtime_z-176,height))
    # Solid paving: exact graded top, bottom cap and visible edge thickness.
    count=len(vertices)
    faces=[]
    for i in range(n):
        for j in range(m):
            a=i*(m+1)+j
            face=(a,a+1,a+m+2,a+m+1)
            faces.append(face if side>0 else tuple(reversed(face)))
    top_faces=faces[:]
    edges={}
    for face in top_faces:
        for a,b in zip(face,face[1:]+face[:1]): edges.setdefault(tuple(sorted((a,b))),[]).append((a,b))
    vertices += [(x,y,z-.24) for x,y,z in vertices]
    faces += [tuple(v+count for v in reversed(face)) for face in top_faces]
    faces += [(b,a,a+count,b+count) for rows in edges.values() if len(rows)==1 for a,b in rows]
    label='east' if side>0 else 'west'
    obj=ck.new_object(f'traversal / city arrival {label} paving',vertices,faces,'plaza_flagstone')
    ck.uv_box(obj);ck.vertex_paint(obj,ground_z=None,jitter=.01,cavity=.15,edge=.10,seed=0)
    # Physical stone-and-earth bank body beneath the cap. The broad canal
    # remains empty: neither top nor its backing crosses X +/-6.85.
    first=vertices[:m+1]
    last=vertices[n*(m+1):(n+1)*(m+1)]
    footprint=[first[0],first[-1],last[-1],last[0]]
    if side<0: footprint.reverse()
    backing=[(x,y,-1.25) for x,y,z in footprint]+[(x,y,z-.24) for x,y,z in footprint]
    body=ck.new_object(f'city arrival {label} masonry bank backing',backing,
        [(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(3,2,1,0)],'stone_wall_warm')
    ck.uv_box(body);ck.vertex_paint(body,ground_z=None,jitter=.01,cavity=.15,edge=.10,seed=0)
    return {'side':label,'paving_bounds':bounds(obj),'stone_backing_bounds':bounds(body),'canal_clear_half_width_m':6.85,
            'start_runtime_z':8,'end_runtime_z':24,'start_y':0,'end_y_range':[min(p[2] for p in last),max(p[2] for p in last)]}

def repair():
    if Path(bpy.data.filepath).resolve()!=MASTER.resolve() or digest(MASTER)!=EXPECTED:
        raise RuntimeError('Market repair requires the exact promoted traversal master.')
    OUT.mkdir(parents=True,exist_ok=True)
    candidate=OUT/'reference_city_market_gate_repaired.blend'
    if candidate.exists():
        raise RuntimeError('This candidate is already versioned. Use a new output revision for further authored changes.')
    bpy.context.view_layer.update()
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    before_geom={o.name:geometry(o) for o in meshes}
    before_pose={o.name:pose(o) for o in bpy.context.scene.objects}
    before_roots={o.name:pose(o) for o in bpy.context.scene.objects if o.name.startswith('kit_') and o.type=='EMPTY'}
    layout=json.loads((ROOT/'assets/blender/city_r5/layout.json').read_text(encoding='utf-8'))
    spec=next(l for l in layout['landmarks'] if l['id']=='market')
    root=bpy.data.objects['kit_market_square']
    moved=set();rows=[]
    for row_i,row in enumerate(spec['stall_rows']):
        a,b=(Vector(v) for v in row)
        yaw=math.atan2((b-a).y,(b-a).x)-math.pi/2
        for index in range(spec['stalls_per_row']):
            slot=f'{row_i+1}-{index+1}'
            if slot==spec['featured_cart_stall']['slot']: continue
            name=f'market stall {slot}'
            parts=[o for o in meshes if o.name.startswith(name+' ')]
            if len(parts)!=58 or any(o.parent for o in parts):
                raise RuntimeError(f'Complete orphaned stall identity changed: {name}/{len(parts)}')
            point=a.lerp(b,(index+.5)/spec['stalls_per_row'])
            local=point-Vector(spec['center'])
            pivot=bpy.data.objects.new(name+' pivot',None)
            root.users_collection[0].objects.link(pivot)
            pivot.parent=root
            pivot.matrix_parent_inverse=Matrix.Identity(4)
            pivot.location=(local.x,local.y,0)
            pivot.rotation_euler.z=yaw
            for obj in parts:
                original_local=obj.matrix_world.copy()
                obj.parent=pivot
                obj.matrix_parent_inverse=Matrix.Identity(4)
                obj.matrix_basis=original_local
                moved.add(obj.name)
            rows.append({'slot':slot,'objects':len(parts),'pivot':pivot.name,'expected_world_runtime':[point.x,0,176+point.y],
                         'local_yaw_deg':math.degrees(yaw),'members':[o.name for o in parts]})
    gate_rows=[]
    for name,side in [('gate west pier',-1),('gate east pier',1)]:
        obj=bpy.data.objects[name]
        original=bounds(obj)
        matrix=obj.matrix_world.copy();matrix.translation.x+=side*4
        obj.matrix_world=matrix
        moved.add(name)
        gate_rows.append({'object':name,'before':original,'world_x_offset_m':side*4})
    arrival=[]
    for side in (-1,1):
        obj=bpy.data.objects[f'terrain / canal promenade {side:+d}']
        obj.data.calc_loop_triangles()
        tree=BVHTree.FromPolygons([obj.matrix_world@v.co for v in obj.data.vertices],[tuple(t.vertices) for t in obj.data.loop_triangles],all_triangles=True)
        arrival.append(apron(tree,side))
    bpy.context.view_layer.update()
    for item in rows:
        actual=runtime(bpy.data.objects[item['pivot']].matrix_world.translation)
        if max(abs(x-y) for x,y in zip(actual,item['expected_world_runtime']))>.0001:
            raise RuntimeError('Linked market pivot does not evaluate to authored layout.')
        item['actual_origin_runtime']=actual
    for row in gate_rows: row['after']=bounds(bpy.data.objects[row['object']])
    mesh_changed=[name for name,h in before_geom.items() if geometry(bpy.data.objects[name])!=h]
    unrelated_moved=[name for name,p in before_pose.items() if name not in moved and pose(bpy.data.objects[name])!=p]
    if mesh_changed or unrelated_moved:
        raise RuntimeError(f'Unrelated geometry/pose changed: {mesh_changed[:5]}/{unrelated_moved[:5]}')
    if any(pose(bpy.data.objects[name])!=p for name,p in before_roots.items()): raise RuntimeError('An authored kit root moved.')
    triangles=ck.triangle_count([o for o in bpy.context.scene.objects if o.type=='MESH'])
    before_triangles=ck.triangle_count(meshes)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate),check_existing=False,relative_remap=False,copy=True)
    if digest(MASTER)!=EXPECTED: raise RuntimeError('Canonical was changed during candidate repair.')
    report={'schema':'xexoria.city-market-gate-repair/1','status':'CANDIDATE_REQUIRES_EXTRACTION_AND_RUNTIME_REVIEW',
        'source':str(MASTER),'source_sha256':EXPECTED,'candidate':str(candidate),'candidate_sha256':digest(candidate),
        'market_stalls':rows,'market_parts_moved':len(moved)-2,'gate_piers':gate_rows,'arrival_aprons':arrival,
        'source_mesh_geometry_uv_colors_materials_preserved':True,'authored_kit_roots_preserved':len(before_roots),
        'unchanged_object_poses_verified':len(before_pose)-len(moved),'source_triangles_before':before_triangles,
        'candidate_triangles':triangles,'added_triangles':triangles-before_triangles,
        'old_colliders_to_retire_after_exact_replacements_admitted':['town_gate_west_wing','town_gate_east_wing'],
        'limits':['No canonical promotion.','No canal floor was added.','Parent must replace the exact two legacy wing boxes with measured gate polygons and clip the old flat meadow overlays.']}
    RECEIPT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('candidate_sha256','market_parts_moved','added_triangles','authored_kit_roots_preserved')}))

def verify():
    receipt=json.loads(RECEIPT.read_text(encoding='utf-8'))
    candidate=Path(bpy.data.filepath).resolve()
    if candidate!=Path(receipt['candidate']).resolve() or digest(candidate)!=receipt['candidate_sha256']:
        raise RuntimeError('Load the exact separately saved market/gate candidate.')
    return receipt
def reload_textures():
    spec=importlib.util.spec_from_file_location('city_floor_helper',ROOT/'tools/repair-city-walk-geometry.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper.reload_textures_absolute()
def export(mode):
    receipt=verify()
    sys.path.insert(0,str(ROOT/'assets/blender/city_r5'))
    exporter=__import__('export_source_r5' if mode=='source' else 'export_runtime_r5')
    exporter.MASTER=Path(receipt['candidate'])
    exporter.refresh_texture_images=reload_textures
    stats=OUT/f'city-{mode}.stats.json'
    sys.argv=[sys.argv[0],'--','--candidate',str(OUT/f'city-{mode}.glb'),'--stats',str(stats)]
    exporter.main()
    (EVIDENCE/f'city-market-placement-20261001-{mode}.json').write_text(stats.read_text(encoding='utf-8'),encoding='utf-8')
def render():
    verify();reload_textures()
    scene=ck.render_settings(res=(960,640),samples=8,threads=4)
    camera_data=bpy.data.cameras.new('Market/gate review camera')
    camera=bpy.data.objects.new('Market/gate review camera',camera_data)
    scene.collection.objects.link(camera);scene.camera=camera
    camera_data.clip_start=.1;camera_data.clip_end=2000
    views=[('fountain-clear',(17,-20,10),(0,0,6),32),('market-front',(64,-52,11),(66,-22,3),30),
           ('market-side',(97,-23,12),(66,-22,3),34),('gate-arrival',(13,-174,5),(3,-151,7),28),
           ('gate-east-path',(10.1,-168,2),(10.1,-147,2),30)]
    records=[]
    for name,location,target,lens in views:
        camera.location=location;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler();camera_data.lens=lens
        filename=EVIDENCE/f'city-market-placement-20261001-{name}.png';ck.render(filename)
        records.append({'view':name,'image':str(filename),'camera':location,'target':target})
    (EVIDENCE/'city-market-placement-20261001-renders.json').write_text(json.dumps({'source_sha256':digest(Path(bpy.data.filepath)),'source_saved':False,'renderer':'Cycles CPU','samples':8,'views':records},indent=2)+'\n',encoding='utf-8')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair',action='store_true');parser.add_argument('--export-source',action='store_true');parser.add_argument('--export-runtime',action='store_true');parser.add_argument('--render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.repair: repair()
    if args.export_source: export('source')
    if args.export_runtime: export('runtime')
    if args.render: render()
if __name__=='__main__': main()
