"""Re-import decoded copies of the actual meshopt/KTX2 packages; scoped technical gate."""
import argparse, hashlib, json, math, sys, time
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from weapon_geometry import RECIPES
from build_hero_weapons import ROOT,REFERENCES,bounds,triangles,flat_material,area,look_at,label,save_json,review

def clean():
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 for collection in (bpy.data.meshes,bpy.data.materials,bpy.data.images):
  for item in list(collection):
   if item.users==0:collection.remove(item)

def weapon_owner():
 roots=[o for o in bpy.context.scene.objects if o.get('xexoria_role')=='weapon']
 assert len(roots)==1,('weapon owner count',len(roots));return roots[0]

def owned_marker(root,name):
 nodes=[o for o in root.children_recursive if o.get('xexoria_marker',o.name)==name]
 assert len(nodes)==1,('owned marker count',name,len(nodes));return nodes[0]

def inspect(path,definitions,expected_count,expected_bounds):
 clean();bpy.ops.import_scene.gltf(filepath=str(path));bpy.context.view_layer.update()
 meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
 count=sum(triangles(o) for o in meshes)
 assert count==expected_count,(path.name,'triangles',count,expected_count)
 marker_result={};root=weapon_owner()
 if 'fx_head' in definitions:
  # A deliberate rig/weapon name collision: global lookup would resolve the wrong owner.
  actual=owned_marker(root,'fx_head');actual.name='weapon_fx_head_for_owner_test'
  rig=bpy.data.objects.new('unrelated_rig',None);bpy.context.collection.objects.link(rig)
  foreign=bpy.data.objects.new('fx_head',None);bpy.context.collection.objects.link(foreign);foreign.parent=rig;foreign.location=(123,456,789)
  assert bpy.data.objects.get('fx_head') is foreign
 for name,point in definitions.items():
  marker=owned_marker(root,name)
  error=(marker.matrix_world.translation-Vector(point)).length
  assert error<.002,(path.name,'marker error',name,error)
  marker_result[name]={'blender_position':list(marker.matrix_world.translation),'error_m':error}
 measured=bounds(meshes);error=max(abs(measured[key][i]-expected_bounds[key][i]) for key in ['min','max'] for i in range(3))
 assert error<.004,(path.name,'bounds drift',error)
 for obj in meshes:
  for vertex in obj.data.vertices:assert all(math.isfinite(v) for v in vertex.co)
  assert obj.data.uv_layers,(path.name,'missing UVs',obj.name)
  for uv in obj.data.uv_layers.active.data:assert all(math.isfinite(v) and -.002<=v<=1.002 for v in uv.uv)
  for face in obj.data.polygons:assert face.area>1e-14,(path.name,'collapsed triangle',obj.name,face.index)
 return {'file':str(path),'triangles':count,'bounds':measured,'max_bounds_error_m':error,'markers':marker_result,'owner_lookup':'PASS, isolated from foreign rig fx_head' if 'fx_head' in definitions else 'PASS, weapon root only','uvs':'finite/in-range','geometry':'no collapsed polygons'},meshes

def final_view(hero,meshes,evidence,revision,lod,phase='decoded runtime'):
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=20;scene.render.threads_mode='FIXED';scene.render.threads=2
 scene.view_settings.view_transform='AgX';scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.35,.39,.45,1);scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35
 box=bounds(meshes);center=(box['min'][2]+box['max'][2])/2
 bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,box['min'][2]-.008));bpy.context.object.data.materials.append(flat_material('review_floor','D3D6D7'))
 area('soft_key',(-3,-4,5),500,4,(0,0,center));area('cool_fill',(3,-2,2),220,3,(0,0,center));area('soft_back',(1,3,4),350,3,(0,0,center))
 data=bpy.data.cameras.new('ReviewCamera');camera=bpy.data.objects.new('ReviewCamera',data);bpy.context.collection.objects.link(camera);scene.camera=camera;data.type='ORTHO';data.ortho_scale=box['dimensions'][2]*1.18
 camera.location=(-3 if hero=='03' else 3,-4,center+.2);look_at(camera,(0,0,center))
 caption=label('BLENDER REVIEW | '+phase+' | '+lod,(0,0,box['max'][2]+.09),.041);caption.rotation_euler=camera.rotation_euler
 scene.render.resolution_x=768;scene.render.resolution_y=1024;scene.render.resolution_percentage=100;scene.render.filepath=str(evidence/f'{revision}-{lod}-decoded-three-quarter.png');bpy.ops.render.render(write_still=True)
 return scene.render.filepath

def main():
 p=argparse.ArgumentParser();p.add_argument('--hero',choices=list(RECIPES),required=True);p.add_argument('--revision',required=True);args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
 hero=args.hero;revision=args.revision;directory=ROOT/'assets/models/weapons'/('hero-'+hero)/revision;evidence=ROOT/'planning/evidence/hero-weapons-20261002'/('hero-'+hero)/revision
 output=evidence/'reimport-validation.json'
 if output.exists():raise RuntimeError('Validation receipt exists; do not overwrite sealed evidence')
 receipt=json.loads((evidence/'receipt.json').read_text(encoding='utf8'));definitions=receipt['source']['markers'];jobs=[]
 if hero=='03':
  bpy.ops.wm.open_mainfile(filepath=receipt['source_blend']);string=bpy.data.objects.get('bow_string_rest');assert string and string.data.shape_keys
  basis=string.data.shape_keys.key_blocks['Basis'];draw=string.data.shape_keys.key_blocks['DrawBack'];distance=float(string['draw_distance_m'])
  for i in range(len(basis.data)):
   delta=draw.data[i].co-basis.data[i].co
   assert abs(delta.y-(distance if 4<=i<8 else 0))<1e-6 and abs(delta.x)<1e-6 and abs(delta.z)<1e-6
  for side,marker in [(0,'fx_base'),(2,'fx_tip')]:
   mean=sum((basis.data[side*4+j].co for j in range(4)),Vector())/4
   assert (mean-Vector(definitions[marker])).length<1e-6
  if receipt.get('j2'):
   root=weapon_owner();nock=owned_marker(root,'fx_nock')
   for value in [0,.5,1]:
    draw.value=value;bpy.context.scene.frame_set(bpy.context.scene.frame_current);bpy.context.view_layer.update()
    assert abs(nock.location.y-(.034+.306*value))<1e-6,('authoring fx_nock driver',value)
   draw.value=0;bpy.context.scene.frame_set(bpy.context.scene.frame_current);bpy.context.view_layer.update()
 for lod in ['lod0','lod1']:
  stem=f'hero{hero}_{REFERENCES[hero][2]}_{lod}'
  report=json.loads((evidence/(stem+'.postprocess.json')).read_text(encoding='utf8'));assert report['status']=='PASS' and report['budget']['pass']
  runtime=directory/(stem+'.runtime.glb');decoded=ROOT/report['review_copy']['file']
  expected=receipt['source']['triangles'] if lod=='lod0' else receipt['lod1']['triangles']
  # The shared exporter also records the LOD's own bounds, so simplification drift is not misreported as compression drift.
  source_glb=directory/(stem+'.glb');bpy.context.scene.unit_settings.system='METRIC'
  clean();bpy.ops.import_scene.gltf(filepath=str(source_glb));bpy.context.view_layer.update();source_bounds=bounds([o for o in bpy.context.scene.objects if o.type=='MESH'])
  result,meshes=inspect(decoded,definitions,expected,source_bounds)
  result.update(runtime_file=str(runtime),runtime_sha256=hashlib.sha256(runtime.read_bytes()).hexdigest(),runtime_bytes=runtime.stat().st_size,budget=report['budget']['rows'],capture=final_view(hero,meshes,evidence,revision,lod))
  jobs.append(result)
 if hero=='03':
  stem='hero03_bow_string_drawn';report=json.loads((evidence/(stem+'.postprocess.json')).read_text(encoding='utf8'));assert report['status']=='PASS' and report['budget']['pass']
  clean();bpy.ops.import_scene.gltf(filepath=str(ROOT/report['review_copy']['file']));string=[o for o in bpy.context.scene.objects if o.type=='MESH'][0]
  assert triangles(string)==20
  assert abs(max((string.matrix_world@v.co).y for v in string.data.vertices)-.344)<.001
  result={'file':str(directory/(stem+'.runtime.glb')),'triangles':20,'draw_pose':'PASS; centre moves, nocks stay fixed'}
  if receipt.get('j2'):
   root=weapon_owner();result['markers']={}
   for name,point in receipt['j2']['drawn_markers'].items():
    marker=owned_marker(root,name);error=(marker.matrix_world.translation-Vector(point)).length
    assert error<.002,('drawn marker',name,error);result['markers'][name]={'blender_position':list(marker.matrix_world.translation),'error_m':error}
   result['nock_centre']='PASS; fx_nock follows full draw, fx_head remains at the arrow rest'
  jobs.append(result)
 save_json(output,{'schema':'xexoria.weapon-reimport/1','hero':hero,'revision':revision,'status':'PASS','packages':jobs,'native_babylon':'UNVERIFIED; technical asset validation and Blender review only'})
 print(json.dumps({'hero':hero,'revision':revision,'status':'PASS','packages':len(jobs)}))
if __name__=='__main__':main()
