"""Restore annotated hair-piece weight policy where measured seams exposed arm contamination."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy,numpy as np
import h02_common as C
bpy.ops.wm.open_mainfile(filepath=str(C.WORK/'h02_anim.blend'))
hi=bpy.data.objects['hero02_hiclean'].data
rig=json.loads((C.REPORTS/'rig.json').read_text());seams=json.loads((C.REPORTS/'weight-seam-repair.json').read_text())
seeds=set(seams['source_vertex_ids']);pieces=rig['pieces'];triggered=set()
for poly in hi.polygons:
    pid=str(hi.attributes['xex_comp'].data[poly.index].value)
    if pieces.get(pid,{}).get('label')=='back_hair' and seeds.intersection(poly.vertices):triggered.add(pid)
targets=set()
for poly in hi.polygons:
    if str(hi.attributes['xex_comp'].data[poly.index].value) in triggered:targets.update(poly.vertices)
def smooth(a,b,x):
    t=max(0,min(1,(x-a)/(b-a)));return t*t*(3-2*t)
fixed={}
for vid in targets:
    z=hi.vertices[vid].co.z;t=max(0,min(1,(1.645-z)/.260));head=1-smooth(0,.30,t);body=.3*smooth(.55,1,t)
    chain={'hair.01':max(0,1-abs(t-.25)/.35),'hair.02':max(0,1-abs(t-.6)/.35),'hair.03':max(0,1-abs(t-.95)/.35)};ct=sum(chain.values()) or 1
    w={'head':head*(1-body),'upper_chest':body}
    w.update({k:(1-head)*(1-body)*v/ct for k,v in chain.items()})
    w=dict(sorted(((k,v) for k,v in w.items() if v>.001),key=lambda item:item[1],reverse=True)[:4]);total=sum(w.values());fixed[vid]={k:v/total for k,v in w.items()}
mo=C.WORK/'meshopt';orig=np.fromfile(mo/'orig_vertex.u32',np.uint32);rows=[]
for filename in ('h02_rig.blend','h02_anim.blend'):
    bpy.ops.wm.open_mainfile(filepath=str(C.WORK/filename))
    for L in (0,1,2):
        ob=bpy.data.objects[f'hero02_witch_lod{L}'];idx=np.fromfile(mo/f'lod{L}.indices.u32',np.uint32).reshape(-1,3);ov=orig[idx];ov=ov[(ov[:,0]!=ov[:,1])&(ov[:,1]!=ov[:,2])&(ov[:,0]!=ov[:,2])];ids=np.unique(ov)
        assert len(ids)==len(ob.data.vertices)
        changed=[]
        for v in ob.data.vertices:
            w=fixed.get(int(ids[v.index]))
            if w is None:continue
            for g in list(v.groups):ob.vertex_groups[g.group].remove([v.index])
            for name,weight in w.items():ob.vertex_groups[name].add([v.index],weight,'REPLACE')
            changed.append({'vertex_id':v.index,'source_vertex_id':int(ids[v.index])})
        rows.append({'blend':filename,'lod':L,'count':len(changed),'affected_vertices':changed})
    bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK/filename),compress=True)
C.write_json(C.REPORTS/'hair-policy-repair.json',{'policy':'Only source xex_comp pieces already annotated back_hair and intersecting measured connected seam IDs; original height-based head/hair/chest policy restored, no arm weights or geometry weld','source_piece_ids':sorted(triggered),'source_vertex_ids':sorted(targets),'rows':rows})
print('hair policy repaired',len(triggered),'annotated pieces',[(r['lod'],r['count']) for r in rows[:3]])
