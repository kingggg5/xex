"""Measure skin edge stretch and ground contact; diagnostic evidence, not an art pass."""
import sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
import h02_common as C
bpy.ops.wm.open_mainfile(filepath=str(C.WORK/'h02_anim.blend'))
scn=bpy.context.scene;arm=bpy.data.objects['hero02_XS1'];ob=bpy.data.objects['hero02_witch_lod0'];me=ob.data
edges=[(tuple(e.vertices),(me.vertices[e.vertices[0]].co-me.vertices[e.vertices[1]].co).length) for e in me.edges]
rows=[]
for action in bpy.data.actions:
    arm.animation_data.action=action;arm.animation_data.action_slot=action.slots[0]
    first,last=action.frame_range
    for fraction in (0,.25,.5,.75,1):
        f=round(first+(last-first)*fraction);scn.frame_set(f);dg=bpy.context.evaluated_depsgraph_get();eo=ob.evaluated_get(dg);ev=eo.to_mesh()
        out=[]
        for (i,j),base in edges:
            dist=(ev.vertices[i].co-ev.vertices[j].co).length
            if base>.001 and dist>.08 and dist/base>4:
                out.append({'vertices':[i,j],'rest_length':round(base,5),'posed_length':round(dist,5),'ratio':round(dist/base,2),
                            'rest_mid':list((me.vertices[i].co+me.vertices[j].co)*.5),
                            'groups':[[[ob.vertex_groups[g.group].name,round(g.weight,4)] for g in me.vertices[k].groups] for k in (i,j)]})
        out.sort(key=lambda v:v['ratio'],reverse=True)
        low=min(ev.vertices,key=lambda v:v.co.z)
        rows.append({'clip':action.name,'frame':f,'floor_vertex':low.index,'floor_groups':[[ob.vertex_groups[g.group].name,round(g.weight,4)] for g in me.vertices[low.index].groups],'floor_min_z':round(low.co.z,4),'stretched_edges':len(out),'worst':out[:8]})
        eo.to_mesh_clear()
C.write_json(C.REPORTS/'deformation-audit.json',{'diagnostic_only':True,'threshold':'edge length>8cm, rest>1mm, ratio>4','rows':rows})
print('deformation audit samples',len(rows),'flagged',sum(r['stretched_edges'] for r in rows))
