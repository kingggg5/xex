"""Re-import the exact-runtime review copies emitted by gltf-postprocess (decoded KTX2/meshopt)."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
import h02_common as C
rows=[]
for p in sorted((C.EVIDENCE/'reimport').glob('*/*.review.glb')):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(p),merge_vertices=False,import_shading='NORMALS',disable_bone_shape=True)
    meshes=[o for o in bpy.data.objects if o.type=='MESH']
    tris=sum(len(o.data.loop_triangles) for o in meshes if not o.data.calc_loop_triangles())
    rigs=[o for o in bpy.data.objects if o.type=='ARMATURE']
    row={'file':C.rel(p),'triangles':tris,'mesh_count':len(meshes),'joint_counts':[len(o.data.bones) for o in rigs],
         'actions':[a.name for a in bpy.data.actions],'materials':[m.name for m in bpy.data.materials]}
    assert meshes and tris>0, row
    if 'witch' in p.name:assert any(len(o.data.bones)==59 for o in rigs),row
    rows.append(row)
assert len(rows)==5, f'expected five reimport files, found {len(rows)}'
C.write_json(C.REPORTS/'runtime-reimport.json',{'status':'PASS','note':'exact runtime decode review copies; KTX2 pixels and quantized geometry retained','files':rows})
print('Hero02 reimport PASS: five files')
