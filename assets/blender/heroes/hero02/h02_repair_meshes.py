"""Restore body/cloth face assignments lost by bake-slot clearing, and remove invalid duplicate faces."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy,numpy as np
import h02_common as C
mo=C.WORK/'meshopt';orig=np.fromfile(mo/'orig_vertex.u32',np.uint32);umat=np.fromfile(mo/'material.f32',np.float32).astype(np.int64)
rows=[]
for filename in ('h02_rig.blend','h02_anim.blend'):
    bpy.ops.wm.open_mainfile(filepath=str(C.WORK/filename))
    for group in bpy.data.node_groups:
        if group.name=='glTF Material Output':
            names={i.name for i in group.interface.items_tree if i.item_type=='SOCKET' and i.in_out=='INPUT'}
            for name,default in [('Thickness',0.),('Dispersion',0.),('Iridescence Factor',0.),('Iridescence Thickness Minimum',100.)]:
                if name not in names:group.interface.new_socket(name,in_out='INPUT',socket_type='NodeSocketFloat').default_value=default
    for L in (0,1,2):
        ob=bpy.data.objects[f'hero02_witch_lod{L}'];me=ob.data
        idx=np.fromfile(mo/f'lod{L}.indices.u32',np.uint32).reshape(-1,3);ov=orig[idx]
        idx=idx[(ov[:,0]!=ov[:,1])&(ov[:,1]!=ov[:,2])&(ov[:,0]!=ov[:,2])]
        assert len(idx)==len(me.polygons), 'repair expects original pre-validation face order; do not apply twice'
        me.polygons.foreach_set('material_index',umat[idx[:,0]].tolist())
        before=len(me.polygons);changed=me.validate(verbose=False,clean_customdata=False);me.update();me.calc_loop_triangles()
        counts={m.name:sum(p.material_index==k for p in me.polygons) for k,m in enumerate(me.materials)}
        assert all(counts.values()), counts
        rows.append({'blend':filename,'lod':L,'before_triangles':before,'triangles':len(me.loop_triangles),'vertices':len(me.vertices),'validation_changed':changed,'material_faces':counts})
    bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK/filename),compress=True)
rig=json.loads((C.REPORTS/'rig.json').read_text())
for row in rows[:3]:rig['lods'][str(row['lod'])]={'triangles':row['triangles'],'vertices':row['vertices']}
rig['continuation_repair']='Material indices restored after bake-slot clearing; Blender mesh validation removes duplicate/invalid faces; source immutable.'
C.write_json(C.REPORTS/'rig.json',rig);C.write_json(C.REPORTS/'mesh-repair.json',{'status':'PASS','files':rows})
print('material/mesh repair complete',rows)
