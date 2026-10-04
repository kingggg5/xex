"""Repair measured thin-shell weight discontinuities, without changing mesh positions or the skeleton."""
import sys,json,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy,numpy as np
import h02_common as C
bpy.ops.wm.open_mainfile(filepath=str(C.WORK/'h02_anim.blend'))
scn=bpy.context.scene;arm=bpy.data.objects['hero02_XS1'];ob=bpy.data.objects['hero02_witch_lod0'];me=ob.data
edges=[(tuple(e.vertices),(me.vertices[e.vertices[0]].co-me.vertices[e.vertices[1]].co).length) for e in me.edges]
edges=[(v,d) for v,d in edges if .0005<d<.02]
mo=C.WORK/'meshopt'
orig=np.fromfile(mo/'orig_vertex.u32',np.uint32)
def original_ids(lod):
    idx=np.fromfile(mo/f'lod{lod}.indices.u32',np.uint32).reshape(-1,3);ov=orig[idx]
    ov=ov[(ov[:,0]!=ov[:,1])&(ov[:,1]!=ov[:,2])&(ov[:,0]!=ov[:,2])]
    return np.unique(ov)
ids0=original_ids(0)
assert len(ids0)==len(me.vertices), 'LOD0 original vertex-order contract changed'
bad=set();worst=0.
for action in bpy.data.actions:
    arm.animation_data.action=action;arm.animation_data.action_slot=action.slots[0]
    first,last=action.frame_range
    for frac in (0,.25,.5,.75,1):
        scn.frame_set(round(first+(last-first)*frac));eo=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());ev=eo.to_mesh()
        for (i,j),base in edges:
            dist=(ev.vertices[i].co-ev.vertices[j].co).length
            if dist>.08 and dist/base>4:bad.add((i,j));worst=max(worst,dist/base)
        eo.to_mesh_clear()
# Extend only through actual connected thin-shell edges (<=6mm), at most3 rings.
# This includes same-weight shell neighbors so a corrected vertex does not create
# a new discontinuity one edge away. Never use spatial nearest neighbors.
expanded=set(bad)
if "--expand" in C.script_args():
    reached={v for e in bad for v in e}
    short=[(tuple(e.vertices),(me.vertices[e.vertices[0]].co-me.vertices[e.vertices[1]].co).length) for e in me.edges]
    short=[e for e,d in short if d<=.006]
    for _ in range(3):
        new={e for e in short if e[0] in reached or e[1] in reached}
        expanded.update(new);reached.update(v for e in new for v in e)
    bad=expanded
parent={v:v for e in bad for v in e}
def find(v):
    while parent[v]!=v:parent[v]=parent[parent[v]];v=parent[v]
    return v
for i,j in bad:parent[find(i)]=find(j)
clusters=collections.defaultdict(list)
for v in parent:clusters[find(v)].append(v)
assert max(map(len,clusters.values()))<=64,'local seam cluster exceeded64vertices; manual review needed'
fixed={}
for ids in clusters.values():
    weights=collections.defaultdict(float)
    for vi in ids:
        for g in me.vertices[vi].groups:weights[ob.vertex_groups[g.group].name]+=g.weight/len(ids)
    weights=dict(sorted(weights.items(),key=lambda item:item[1],reverse=True)[:4]);total=sum(weights.values());weights={k:v/total for k,v in weights.items()}
    for vi in ids:fixed[int(ids0[vi])]=weights
assert fixed,'no measured seam defect to repair'
rows=[]
for filename in ('h02_rig.blend','h02_anim.blend'):
    bpy.ops.wm.open_mainfile(filepath=str(C.WORK/filename))
    for L in (0,1,2):
        ob=bpy.data.objects[f'hero02_witch_lod{L}'];changed=[];ids=original_ids(L)
        assert len(ids)==len(ob.data.vertices), f'LOD{L} original vertex-order contract changed'
        for vert in ob.data.vertices:
            original_id=int(ids[vert.index]);weights=fixed.get(original_id)
            if weights is None:continue
            for group in list(vert.groups):ob.vertex_groups[group.group].remove([vert.index])
            for name,weight in weights.items():ob.vertex_groups[name].add([vert.index],weight,'REPLACE')
            changed.append({'vertex_id':vert.index,'source_vertex_id':original_id})
        rows.append({'blend':filename,'lod':L,'vertices_reweighted':len(changed),'affected_vertices':changed})
    bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK/filename),compress=True)
C.write_json(C.REPORTS/'weight-seam-repair.json',{'criterion':'measured posed edge>8cm, rest0.5-20mm, stretch>4x across70pose samples; local cluster averages limited to4normalized weights','source_vertex_ids':sorted(fixed),'connected_lod0_edges':[list(e) for e in sorted(bad)],'bad_edges':len(bad),'clusters':len(clusters),'largest_cluster_vertices':max(map(len,clusters.values())),'worst_original_ratio':worst,'rows':rows})
print('weight seam repair',len(bad),'edges',len(clusters),'clusters',rows)
