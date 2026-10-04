"""J2: versioned node-only repair from validated sources. No geometry/material authoring."""
from __future__ import annotations
import argparse,hashlib,json,shutil,struct,sys,time
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_hero_weapons import ROOT,REFERENCES,active,bounds,triangles,save_json,digest,export_glb
from validate_weapon_packages import final_view

JOBS={'02':('r2','r3'),'03':('r4','r5'),'04':('r1','r2')}
HEADS={'02':(0,0,.94),'03':(0,-.06,0),'04':(0,-.005,.77)}

def glb_document(path):
 data=Path(path).read_bytes();size=struct.unpack_from('<I',data,12)[0];return json.loads(data[20:20+size])

def root_in_scene():
 roots=[o for o in bpy.context.scene.objects if o.get('xexoria_role')=='weapon']
 assert len(roots)==1,('weapon owner roots',len(roots));return roots[0]

def owned(root,name):
 found=[o for o in root.children_recursive if o.get('xexoria_marker',o.name)==name]
 assert len(found)<=1,('duplicate owned node',name)
 return found[0] if found else None

def put_node(root,name,position,role):
 obj=owned(root,name)
 if obj is None:obj=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(obj);obj.parent=root
 obj.location=position;obj.empty_display_type='PLAIN_AXES';obj.empty_display_size=.04
 obj['xexoria_marker']=name;obj['xexoria_role']=role;obj['units']='m';return obj

def update_nodes(root,hero,definitions,string=None):
 definitions=dict(definitions);definitions['fx_head']=HEADS[hero];definitions.pop('muzzle',None)
 old_muzzle=owned(root,'muzzle')
 if old_muzzle:old_muzzle.name='fx_head';old_muzzle['xexoria_marker']='fx_head'
 for name,point in definitions.items():put_node(root,name,point,'cast_origin' if name=='fx_head' else 'trail_marker' if name.startswith('fx_') else 'attachment')
 if hero=='03':
  definitions['fx_nock']=(0,.034,0);nock=put_node(root,'fx_nock',definitions['fx_nock'],'arrow_nock')
  if string and string.data.shape_keys:
   driver=nock.driver_add('location',1).driver;driver.type='SCRIPTED';driver.expression='0.034 + 0.306 * draw'
   var=driver.variables.new();var.name='draw';var.type='SINGLE_PROP';var.targets[0].id_type='KEY';var.targets[0].id=string.data.shape_keys;var.targets[0].data_path='key_blocks["DrawBack"].value'
 return definitions

def mesh_facts(meshes):
 entries=[]
 for obj in meshes:
  data=obj.data;data.calc_loop_triangles()
  payload={'positions':[list(v.co) for v in data.vertices],'faces':[list(p.vertices) for p in data.polygons],
   'material_indices':[p.material_index for p in data.polygons],'uvs':[[list(v.uv) for v in layer.data]for layer in data.uv_layers],
   'transform':[list(row) for row in obj.matrix_world]}
  entries.append({'name':obj.name,'triangles':triangles(obj),'fingerprint':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()})
 return entries

def static_string(source,pose='Basis'):
 coordinates=[point.co.copy() for point in source.data.shape_keys.key_blocks[pose].data]
 clone=source.copy();clone.data=source.data.copy();bpy.context.collection.objects.link(clone)
 active([clone]);bpy.ops.object.shape_key_remove(all=True,apply_mix=False)
 for vertex,co in zip(clone.data.vertices,coordinates):vertex.co=co
 clone.data.update();return clone

def set_draw(string,value):
 string.data.shape_keys.key_blocks['DrawBack'].value=value
 bpy.context.scene.frame_set(bpy.context.scene.frame_current);bpy.context.view_layer.update()

def copy_atlas(old_receipt,directory):
 source=Path(old_receipt['texture']['path']);target=directory/'textures'/source.name;shutil.copy2(source,target)
 assert digest(source)==digest(target)
 for image in bpy.data.images:
  if image.source=='FILE' and image.filepath:
   filepath=Path(bpy.path.abspath(image.filepath))
   if filepath.is_file() and digest(filepath)==old_receipt['texture']['sha256']:image.filepath=str(target)
 return target

def process(hero):
 previous,revision=JOBS[hero];started=time.time();source_directory=ROOT/'assets/models/weapons'/('hero-'+hero)/previous
 directory=source_directory.parent/revision;evidence=ROOT/'planning/evidence/hero-weapons-20261002'/('hero-'+hero)/revision
 if directory.exists() or evidence.exists():raise RuntimeError('Candidate version exists; no overwrite')
 old_evidence=evidence.parent/previous;old=json.loads((old_evidence/'receipt.json').read_text(encoding='utf8'))
 old_sources={str(p):digest(p) for p in source_directory.rglob('*')if p.is_file()}
 directory.mkdir(parents=True);(directory/'textures').mkdir();(directory/'source').mkdir();evidence.mkdir(parents=True)
 shutil.copy2(__file__,directory/'source'/Path(__file__).name)
 baseline=glb_document(old['source_glb']);save_json(evidence/'pass1-baseline.json',{'status':'MISSING_REQUIRED_MARKERS','source':old['source_glb'],'nodes':[n.get('name')for n in baseline['nodes']],
   'captures':old['captures'],'defect':'Required cast-origin/nock markers missing; bow legacy muzzle name; no mesh/material defect in J2 scope.'})
 bpy.ops.wm.open_mainfile(filepath=old['source_blend']);scene=bpy.context.scene;scene.render.threads_mode='FIXED';scene.render.threads=2;scene.cycles.device='CPU'
 root=root_in_scene();meshes=[o for o in root.children_recursive if o.type=='MESH'];before=mesh_facts(meshes)
 source_string=next((o for o in meshes if o.name=='bow_string_rest'),None)
 definitions=update_nodes(root,hero,old['source']['markers'],source_string)
 pose_checks=[]
 if hero=='03':
  for value in [0,.5,1]:
   set_draw(source_string,value);actual=owned(root,'fx_nock').location.y;expected=.034+.306*value
   assert abs(actual-expected)<1e-6,('nock driver',value,actual,expected)
   pose_checks.append({'draw':value,'nock_blender':[0,actual,0]})
  set_draw(source_string,0)
 bpy.context.view_layer.update();assert before==mesh_facts(meshes),'Marker repair changed mesh/UV/transform'
 atlas=copy_atlas(old,directory)
 blend=directory/(REFERENCES[hero][2]+'-editable.blend');bpy.ops.wm.save_as_mainfile(filepath=str(blend))
 string=None
 if source_string:
  string=static_string(source_string);source_string.name='bow_string_editable_source';source_string.hide_render=True;source_string.hide_viewport=True;string.name='bow_string_rest'
 body=[o for o in meshes if o is not source_string];asset_objects=body+([string]if string else [])
 markers=[owned(root,name)for name in definitions]
 source_facts={**old['source'],'markers':definitions,'triangles':sum(triangles(o)for o in asset_objects)}
 base=directory/f'hero{hero}_{REFERENCES[hero][2]}_lod0.glb'
 export_glb([root,*asset_objects,*markers],base,'prop',texture_dir=directory/'textures',asset_id=f'hero{hero}_{REFERENCES[hero][2]}',inputs=[__file__,old['source_blend']],notes=['J2: node-only repair; geometry/UV/atlas retained.','Resolve fx_* relative to the weapon owner root.'])
 capture0=final_view(hero,asset_objects,evidence,revision,'authoring-lod0',phase='marker authoring')
 if hero=='03':
  drawn=static_string(source_string,'DrawBack');drawn.name='bow_string_drawn';set_draw(source_string,1)
  drawn_defs=dict(definitions);drawn_defs['fx_nock']=(0,.340,0)
  export_glb([root,drawn,*markers],directory/'hero03_bow_string_drawn.glb','prop',texture_dir=directory/'textures',asset_id='hero03_bow_string_drawn',inputs=[__file__,old['source_blend']],notes=['Drawn accessory pose; fx_nock at the actual drawn string centre.'])
  set_draw(source_string,0)
  poses=json.loads((source_directory/'bow-string-poses.json').read_text(encoding='utf8'));poses['markers']={'rest':definitions,'drawn':drawn_defs};poses['runtime_task']='Drive weapon-root fx_nock with the interpolated string centre; never resolve fx_head globally.'
  save_json(directory/'bow-string-poses.json',poses)
 else:drawn_defs=None
 # Import the already validated LOD1 into a clean scene; do not simplify it again.
 bpy.ops.wm.read_factory_settings(use_empty=False);bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 source_lod=source_directory/f'hero{hero}_{REFERENCES[hero][2]}_lod1.glb';bpy.ops.import_scene.gltf(filepath=str(source_lod))
 root=root_in_scene();lod_meshes=[o for o in root.children_recursive if o.type=='MESH'];lod_before=mesh_facts(lod_meshes)
 update_nodes(root,hero,definitions);copy_atlas(old,directory);bpy.context.view_layer.update()
 assert lod_before==mesh_facts(lod_meshes),'LOD1 node repair changed mesh/UV/transform'
 export_glb([root,*lod_meshes,*[owned(root,name)for name in definitions]],directory/f'hero{hero}_{REFERENCES[hero][2]}_lod1.glb','prop',texture_dir=directory/'textures',asset_id=f'hero{hero}_{REFERENCES[hero][2]}_lod1',inputs=[__file__,str(source_lod)])
 capture1=final_view(hero,lod_meshes,evidence,revision,'authoring-lod1',phase='marker authoring')
 assert old_sources=={str(p):digest(p)for p in source_directory.rglob('*')if p.is_file()},'Prior candidate changed'
 j2={'task':'J2','baseline_revision':previous,'scope':'fx nodes only','mesh_uv_transform_unchanged':True,'prior_candidate_hashes_unchanged':True,
   'lod0_mesh_fingerprints':before,'lod1_mesh_fingerprints':lod_before,'nock_driver_checks':pose_checks,'drawn_markers':drawn_defs,
   'source_hashes':old_sources,'source_captures':old['captures'],'native_babylon':'UNVERIFIED; J3/root integration, WebGPU blocked pending J1.'}
 receipt={**old,'hero':hero,'revision':revision,'status':'BLENDER_CANDIDATE','source':source_facts,'source_blend':str(blend),'source_glb':str(base),
   'texture':{'path':str(atlas),'sha256':digest(atlas)},'captures':[capture0,capture1],'j2':j2,'elapsed_s':round(time.time()-started,2)}
 save_json(evidence/'receipt.json',receipt);save_json(evidence/'pass2-authoring-export.json',j2)
 print(json.dumps({'hero':hero,'revision':revision,'status':'AUTHORING_EXPORT_PASS','markers':list(definitions)}))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--heroes',default='02,03,04');args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
 for hero in args.heroes.split(','):process(hero)
if __name__=='__main__':main()
