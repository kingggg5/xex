"""P2small timber tiki body; canonical craft atlas, no provider work/flame proxy."""
import sys,json,hashlib
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'assets/blender/nature_props'));sys.path.insert(0,str(ROOT/'assets/blender/tools'))
import np_lib as L
from np_craft_geometry import Craft
from export_helper import export_glb
OUT=ROOT/'assets/models/blueprint-p2-torch';(OUT/'source').mkdir(parents=True,exist_ok=True)
mat=L.pbr_material('bp_tiki_timbers',str(ROOT/'assets/models/sunmeadow-props/craft/textures-source/sm_craft_albedo.png'),vertex_color='Col')
mat.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=0
mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.93
lods=[]
for lod,n in enumerate((12,8,6)):
 c=Craft(202610031856,revision=2,lod=lod)
 c.lathe([(.052,0),(.045,1.8),(.075,1.84)],n=n)
 c.lathe([(.06,1.77),(.16,1.88),(.17,2.09),(.14,2.2)],n=n)
 for z in (1.89,2.07):c.lathe([(.178,z),(.178,z+.025)],n=n)
 ob=c.joined('blueprint_tiki_torch');L.triangulate(ob);ob.data.materials.clear();ob.data.materials.append(mat)
 path=OUT/'source'/f'blueprint_tiki_torch_lod{lod}.glb'
 export_glb([ob],str(path),'prop',asset_id='blueprint_tiki_torch',embed_images=True,vertex_color='NAME',vertex_color_name='Col',tangents=False,copyright_text='Xexoria authored timber tiki body; unchanged craft atlas; no flame/card stand-in')
 ob.data.calc_loop_triangles();lods.append({'file':str(path.relative_to(ROOT)).replace('\\','/'),'tris':len(ob.data.loop_triangles),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 if lod==0:bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'blueprint_tiki_torch.blend'))
 bpy.data.objects.remove(ob,do_unlink=True)
asset={'id':'blueprint_tiki_torch','family':'craft','status':'PROJECT_AUTHORED','licence':'Project authored','recipe':'blueprint.tiki_timber_body/1','seed':202610031856,'bounds':{'min':[-.178,0,-.178],'max':[.178,2.2,.178]},'textures':{'atlas':'sm_craft'},'lods':lods,'collider':{'shape':'none','note':'P2L3nonsolidvisualtorchbody'},'shadowProxy':{'type':'lod2','file':lods[2]['file']},'missing':['flameVFX'],'provenance':'Closedtimberpole andbaskethead/rings; UVmappedexistingwoodatlas; onecanonicalmaterial'}
(OUT/'manifest.json').write_text(json.dumps({'schema':'xexoria.blueprint-local/1','assets':[asset]},indent=2)+'\n',encoding='utf-8')
print('TIKI_SOURCE_READY',json.dumps(lods))
