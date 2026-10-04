"""Owned F5 pointed timber module; reuses the unchanged project craft atlas."""
import sys, json, hashlib, math
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'assets/blender/nature_props'))
sys.path.insert(0,str(ROOT/'assets/blender/tools'))
import np_lib as L
from np_craft_geometry import Craft
from export_helper import export_glb
OUT=ROOT/'assets/models/blueprint-p0-fence'
OUT.mkdir(parents=True,exist_ok=True)
source=OUT/'source';source.mkdir(exist_ok=True)
tex=ROOT/'assets/models/sunmeadow-props/craft/textures-source'
mat=L.pbr_material('bp_hunter_stake_wood',str(tex/'sm_craft_albedo.png'),vertex_color='Col')
mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.92
mat.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=0
lods=[]
for lod,sides in enumerate((12,8,6)):
    c=Craft(202610031410,revision=2,lod=lod)
    for i in range(8):
        x=-1.095+i*.313; top=1.5-(i%3)*.045
        c.lathe([(0.155,0),(.155,top-.26),(0,top)],center=(x,0,0),n=sides)
    for z in (.42,1.02):c.box((2.5,.075,.11),(0,.1,z),bevel=0)
    ob=c.joined('blueprint_hunter_stakes');L.triangulate(ob)
    ob.data.materials.clear();ob.data.materials.append(mat)
    path=source/f'blueprint_hunter_stakes_lod{lod}.glb'
    export_glb([ob],str(path),'prop',asset_id='blueprint_hunter_stakes',embed_images=True,
               vertex_color='NAME',vertex_color_name='Col',tangents=False,
               copyright_text='Xexoria project-authored pointed timber geometry; unchanged project craft atlas')
    ob.data.calc_loop_triangles();lods.append({'file':str(path.relative_to(ROOT)).replace('\\','/'),'tris':len(ob.data.loop_triangles),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    if lod==0:bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'blueprint_hunter_stakes.blend'))
    bpy.data.objects.remove(ob,do_unlink=True)
collider={'id':'blueprint_hunter_stakes','shape':'box','center':[0,.75,0],'size':[2.5,1.5,.31],'admission':'UNVERIFIED root required'}
(OUT/'collider.json').write_text(json.dumps(collider,indent=2)+'\n')
asset={'id':'blueprint_hunter_stakes','family':'craft','recipe':'blueprint.pointed_stake_fence/1','seed':202610031410,'status':'PROJECT_AUTHORED','licence':'Project authored','bounds':{'min':[-1.25,0,-.155],'max':[1.25,1.5,.155]},'textures':{'atlas':'sm_craft'},'lods':lods,'collider':collider,'shadowProxy':{'type':'lod2','file':lods[2]['file']},'provenance':'Eight pointed closed timber stakes and two rear rails, canonical unchanged craft atlas, zero provider credits'}
(OUT/'manifest.json').write_text(json.dumps({'schema':'xexoria.blueprint-local/1','assets':[asset]},indent=2)+'\n')
print('F5_SOURCE_READY',json.dumps(lods))
