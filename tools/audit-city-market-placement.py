"""Read-only source market/fountain overlap and gate-entry geometry audit."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/'assets/models/reference-city/r5/reference_city.blend'
EXPECTED='6a12e74fcc5e13e33a50f11159ace36795f750319cbfe32336c33013259a5b3b'
OUT=ROOT/'planning/evidence/city-market-placement-audit-20261001.json'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def runtime(p): return [round(float(p.x),5),round(float(p.z),5),round(176+float(p.y),5)]
def matrix(m): return [[round(float(v),6) for v in row] for row in m]
def bounds(obj):
    pts=[runtime(obj.matrix_world@Vector(v)) for v in obj.bound_box]
    return {'min':[min(p[i] for p in pts) for i in range(3)],'max':[max(p[i] for p in pts) for i in range(3)]}
def chain(obj):
    rows=[]
    while obj:
        rows.append({'name':obj.name,'type':obj.type,'world_origin_runtime':runtime(obj.matrix_world.translation),
                     'location_local':list(obj.location),'matrix_basis':matrix(obj.matrix_basis),
                     'matrix_parent_inverse':matrix(obj.matrix_parent_inverse)})
        obj=obj.parent
    return rows
def row(obj,geometry=False):
    r={'name':obj.name,'materials':[m.name for m in obj.data.materials if m],
       'bounds_runtime':bounds(obj),'origin_runtime':runtime(obj.matrix_world.translation),'parent_chain':chain(obj),
       'triangles':sum(len(p.vertices)-2 for p in obj.data.polygons)}
    if geometry:
        points=[runtime(obj.matrix_world@v.co) for v in obj.data.vertices]
        r['footprint_xz']=convex_hull([(p[0],p[2]) for p in points])
    return r
def convex_hull(points):
    points=sorted(set(points))
    def cross(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    low=[]
    for p in points:
        while len(low)>1 and cross(low[-2],low[-1],p)<=0: low.pop()
        low.append(p)
    high=[]
    for p in reversed(points):
        while len(high)>1 and cross(high[-2],high[-1],p)<=0: high.pop()
        high.append(p)
    return low[:-1]+high[:-1]

def main():
    source=Path(bpy.data.filepath).resolve()
    if source!=MASTER.resolve() or digest(source)!=EXPECTED: raise RuntimeError('Audit requires the exact promoted city source.')
    bpy.context.view_layer.update()
    layout=json.loads((ROOT/'assets/blender/city_r5/layout.json').read_text(encoding='utf-8'))
    market=next(l for l in layout['landmarks'] if l['id']=='market')
    relevant=[]
    overlap=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH': continue
        names=[m.name for m in obj.data.materials if m]
        target='market stall' in obj.name or 'canopy' in obj.name or any(n.startswith(('cloth_','MI_Banner','MI_Trim_Cloth')) for n in names)
        if not target: continue
        record=row(obj)
        relevant.append(record)
        b=record['bounds_runtime']
        if b['min'][0]<6 and b['max'][0]>-6 and b['min'][2]<182 and b['max'][2]>170 and b['min'][1]<8 and b['max'][1]>0:
            overlap.append(record)
    gate=bpy.data.objects['kit_town_gate']
    gate_parts=[row(o,True) for o in gate.children_recursive if o.type=='MESH']
    important=[r for r in gate_parts if r['name'].startswith(('gate west pier','gate east pier','town gate round tower','gate curtain wall block','gate arch lintel','gate lion plinth'))]
    west=next(r for r in important if r['name']=='gate west pier')['bounds_runtime']
    east=next(r for r in important if r['name']=='gate east pier')['bounds_runtime']
    opening=[west['max'][0],east['min'][0]]
    rows=[]
    for i,segment in enumerate(market['stall_rows']):
        for index in range(market['stalls_per_row']):
            t=(index+.5)/market['stalls_per_row']
            x=segment[0][0]+(segment[1][0]-segment[0][0])*t
            y=segment[0][1]+(segment[1][1]-segment[0][1])*t
            rows.append({'slot':f'{i+1}-{index+1}','expected_origin_runtime':[x,0,176+y]})
    report={'schema':'xexoria.city-market-gate-readonly-audit/1','source_sha256':EXPECTED,'source_saved':False,
            'market_layout':market,'expected_stall_origins':rows,'market_fountain_overlap_objects':overlap,
            'relevant_market_objects':relevant,'gate_root_origin_runtime':runtime(gate.matrix_world.translation),
            'actual_gate_clear_span_x':opening,'actual_gate_primary_parts':important,'all_gate_parts':gate_parts,
            'entry_constraints':{'water_hazard_half_width_m':6.4,'promenade_support_inner_x_m':6.9,'capsule_radius_m':.45,
                'remaining_dry_span_under_existing_arch_m':east['min'][0]-6.9,
                'minimum_gate_inner_edge_for_x10_1_with_capsule_m':10.1+.45,
                'limits':'Measured mesh bounds and precise convex silhouettes; no collision exemptions or source mutation.'}}
    report['diagnosis']={'procedural_stall_meshes_overlapping_fountain':len(overlap),
        'affected_slots':sorted({r['name'].split(' ')[2] for r in overlap}),
        'existing_procedural_stall_pivots':[obj.name for obj in bpy.data.objects if obj.name.startswith('market stall ') and obj.type=='EMPTY'],
        'unparented_affected_meshes':sum(len(r['parent_chain'])==1 for r in overlap),
        'linked_featured_cart_correctly_placed':any(r['name']=='market stall 1-1 Quaternius CC0 stall cart' and r['origin_runtime']==[54.25,0.0,168.0] for r in relevant),
        'source_generator_defect':'kits/buildings.py::_market_stall creates an EMPTY pivot but never links it into a scene collection. The seven saved assemblies lost their pivot parenting and remain in local space at the fountain origin.',
        'source_fix':'Link each new stall pivot to root.users_collection[0] (or the supplied kit collection) before parenting child meshes.',
        'repair_rule':'Restore the complete 58-mesh assembly for each affected slot under a linked pivot at its authored row origin and -90 degree local yaw; leave the correctly placed featured CC0 cart unchanged.'}
    if digest(source)!=EXPECTED: raise RuntimeError('Source changed during read-only audit.')
    OUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'source_sha256':EXPECTED,'near_fountain_meshes':len(overlap),
                      'near_fountain':[{'name':r['name'],'materials':r['materials'],'bounds':r['bounds_runtime'],'origin':r['origin_runtime']} for r in overlap],
                      'gate_clear_span':opening,'gate_primary_parts':len(important),'dry_span':east['min'][0]-6.9}))

if __name__=='__main__': main()
