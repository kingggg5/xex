"""Headless, CPU-only weapon craft/export/review. Does not promote assets into the client."""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import argparse, hashlib, json, math, sys, time
from pathlib import Path
import bpy, bmesh
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from weapon_geometry import RECIPES

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'assets/blender/tools'))
from export_helper import export_glb
REFERENCES={
 '02':('01_15_58','01_14_27','crystal_staff'),
 '03':('01_16_20','01_14_18','recurve_bow'),
 '04':('01_16_04','01_14_07','sun_sceptre'),
}
PALETTE={'gold':'C6903A','gold_light':'F0C579','gold_dark':'94602F','wood':'5D351F','wood_light':'A57446',
 'leather':'493025','blue':'2869D7','cyan':'63CDD8','ivory':'E7D3B3','teal':'4B8789','string':'B6A88C'}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save_json(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def linear(hex):
 values=[int(hex[i:i+2],16)/255 for i in (0,2,4)]
 return tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values)
def active(objects):
 bpy.ops.object.select_all(action='DESELECT')
 for obj in objects:obj.select_set(True)
 if objects:bpy.context.view_layer.objects.active=objects[0]
def mesh_part(part):
 mesh=bpy.data.meshes.new(part.name);mesh.from_pydata(part.vertices,[],part.faces);mesh.update()
 bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
 obj=bpy.data.objects.new(part.name,mesh);bpy.context.collection.objects.link(obj)
 # Per-part normalized height survives joining and becomes a painted crystal gradient.
 height=mesh.attributes.new('paint_height','FLOAT','POINT')
 low=min(v.co.z for v in mesh.vertices);span=max(v.co.z for v in mesh.vertices)-low
 for value,vertex in zip(height.data,mesh.vertices):value.value=(vertex.co.z-low)/max(span,1e-6)
 if part.paint in ('wood','wood_light','leather','ivory'):
  for face in mesh.polygons:face.use_smooth=len(face.vertices)==4
 obj['paint_category']=part.paint;return obj
def triangles(obj):obj.data.calc_loop_triangles();return len(obj.data.loop_triangles)
def make_paint(key):
 mat=bpy.data.materials.new('paint_'+key);mat.use_nodes=True;n=mat.node_tree.nodes;l=mat.node_tree.links;n.clear()
 out=n.new('ShaderNodeOutputMaterial');emit=n.new('ShaderNodeEmission');emit.inputs['Strength'].default_value=1
 base=linear(PALETTE[key]);geo=n.new('ShaderNodeNewGeometry')
 facing=n.new('ShaderNodeVectorMath');facing.operation='DOT_PRODUCT';facing.inputs[1].default_value=(.25,-.55,.78);l.new(geo.outputs['Normal'],facing.inputs[0])
 light=n.new('ShaderNodeMapRange');light.clamp=True;light.inputs['From Min'].default_value=-1;light.inputs['From Max'].default_value=1
 light.inputs['To Min'].default_value=.43 if key.startswith('gold') else .60
 light.inputs['To Max'].default_value=1.48 if key.startswith('gold') else 1.22;l.new(facing.outputs['Value'],light.inputs['Value'])
 ao=n.new('ShaderNodeAmbientOcclusion');ao.inputs['Distance'].default_value=.11;ao.samples=8;ao.only_local=True
 ao_scale=n.new('ShaderNodeMath');ao_scale.operation='MULTIPLY_ADD';ao_scale.inputs[1].default_value=.24;ao_scale.inputs[2].default_value=.76;l.new(ao.outputs['AO'],ao_scale.inputs[0])
 mult=n.new('ShaderNodeMath');mult.operation='MULTIPLY';l.new(light.outputs['Result'],mult.inputs[0]);l.new(ao_scale.outputs[0],mult.inputs[1])
 tex=n.new('ShaderNodeTexNoise');tex.noise_dimensions='3D';tex.inputs['Scale'].default_value=17;tex.inputs['Detail'].default_value=1.5
 if key.startswith('wood') or key=='leather':
  grain=n.new('ShaderNodeVectorMath');grain.operation='MULTIPLY';grain.inputs[1].default_value=(3.2,3.2,.20)
  l.new(geo.outputs['Position'],grain.inputs[0]);l.new(grain.outputs[0],tex.inputs['Vector'])
 else:l.new(geo.outputs['Position'],tex.inputs['Vector'])
 tone=n.new('ShaderNodeMapRange');tone.inputs['To Min'].default_value=.80 if key.startswith('wood') else .93;tone.inputs['To Max'].default_value=1.16 if key.startswith('wood') else 1.05;l.new(tex.outputs['Fac'],tone.inputs['Value'])
 variation=n.new('ShaderNodeMath');variation.operation='MULTIPLY';l.new(mult.outputs[0],variation.inputs[0]);l.new(tone.outputs['Result'],variation.inputs[1])
 if key=='leather':
  wrap_axis=n.new('ShaderNodeVectorMath');wrap_axis.operation='DOT_PRODUCT';wrap_axis.inputs[1].default_value=(.6,.45,1);l.new(geo.outputs['Position'],wrap_axis.inputs[0])
  wrap_scale=n.new('ShaderNodeMath');wrap_scale.operation='MULTIPLY';wrap_scale.inputs[1].default_value=46;l.new(wrap_axis.outputs['Value'],wrap_scale.inputs[0])
  repeat=n.new('ShaderNodeMath');repeat.operation='PINGPONG';repeat.inputs[1].default_value=1;l.new(wrap_scale.outputs[0],repeat.inputs[0])
  seam=n.new('ShaderNodeMapRange');seam.clamp=True;seam.inputs['From Min'].default_value=.08;seam.inputs['From Max'].default_value=.20;seam.inputs['To Min'].default_value=.44;seam.inputs['To Max'].default_value=1.04;l.new(repeat.outputs[0],seam.inputs['Value'])
  wrap=n.new('ShaderNodeMath');wrap.operation='MULTIPLY';l.new(variation.outputs[0],wrap.inputs[0]);l.new(seam.outputs[0],wrap.inputs[1])
 colour=n.new('ShaderNodeMixRGB');colour.blend_type='MULTIPLY';colour.inputs[0].default_value=1;colour.inputs[1].default_value=(*base,1)
 l.new(wrap.outputs[0] if key=='leather' else variation.outputs[0],colour.inputs[2])
 if key.startswith('gold'):
  attr=n.new('ShaderNodeAttribute');attr.attribute_name='paint_height'
  ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.interpolation='EASE';cr=ramp.color_ramp
  cr.elements[0].position=0;cr.elements[0].color=(*linear('835022'),1);cr.elements[1].position=1;cr.elements[1].color=(*linear('F2C779'),1)
  for at,hexcode in [(.18,'BE812E'),(.48,PALETTE[key]),(.77,'DEB25F')]:cr.elements.new(at).color=(*linear(hexcode),1)
  l.new(attr.outputs['Fac'],ramp.inputs['Fac']);l.new(ramp.outputs['Color'],colour.inputs[1])
 if key in ('blue','cyan'):
  attr=n.new('ShaderNodeAttribute');attr.attribute_name='paint_height'
  ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.interpolation='EASE'
  stops=[(0,'073B9A'),(.22,'005AC5'),(.43,'2DEAF0'),(.57,'0D9EDF'),(.78,'073ED0'),(1,'7DCDFF')] if key=='blue' else [(0,'136A8C'),(.33,'2AB7D0'),(.53,'8BF9F1'),(.80,'25B1D1'),(1,'BAFFF8')]
  cr=ramp.color_ramp;cr.elements.remove(cr.elements[1]);cr.elements[0].position=stops[0][0];cr.elements[0].color=(*linear(stops[0][1]),1)
  for at,hexcode in stops[1:]:cr.elements.new(at).color=(*linear(hexcode),1)
  l.new(attr.outputs['Fac'],ramp.inputs['Fac']);l.new(ramp.outputs['Color'],colour.inputs[1])
  # Fine facet seams are baked pigment, never additional runtime line geometry.
  wire=n.new('ShaderNodeWireframe');wire.use_pixel_size=False;wire.inputs['Size'].default_value=.0012
  seam=n.new('ShaderNodeMixRGB');seam.inputs[2].default_value=(*linear('8CDAFA' if key=='blue' else 'B6FFEC'),1)
  l.new(wire.outputs['Fac'],seam.inputs[0]);l.new(colour.outputs[0],seam.inputs[1]);l.new(seam.outputs[0],emit.inputs['Color'])
 else:l.new(colour.outputs[0],emit.inputs['Color'])
 l.new(emit.outputs[0],out.inputs['Surface'])
 return mat
def painted_runtime(name,atlas,metallic,roughness):
 mat=bpy.data.materials.new(name);mat.use_nodes=True;n=mat.node_tree.nodes;l=mat.node_tree.links
 bsdf=n.get('Principled BSDF');bsdf.inputs['Metallic'].default_value=metallic;bsdf.inputs['Roughness'].default_value=roughness
 tex=n.new('ShaderNodeTexImage');tex.image=atlas;tex.interpolation='Linear';l.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
 return mat
def flat_material(name,colour,roughness=.65):
 mat=bpy.data.materials.new(name);mat.use_nodes=True;bsdf=mat.node_tree.nodes.get('Principled BSDF')
 bsdf.inputs['Base Color'].default_value=(*linear(colour),1);bsdf.inputs['Roughness'].default_value=roughness;return mat
def smart_uv(obj):
 active([obj]);bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
 bpy.ops.uv.smart_project(angle_limit=math.radians(62),margin_method='FRACTION',island_margin=.012,area_weight=.2,correct_aspect=True,scale_to_bounds=True)
 bpy.ops.object.mode_set(mode='OBJECT')
def bake_atlas(body,path,size):
 atlas=bpy.data.images.new(body.name+'_painted_albedo',width=size,height=size,alpha=False);atlas.colorspace_settings.name='sRGB'
 for slot in body.material_slots:
  node=slot.material.node_tree.nodes.new('ShaderNodeTexImage');node.image=atlas;node.select=True;slot.material.node_tree.nodes.active=node
 active([body]);bpy.context.scene.cycles.samples=8
 bpy.ops.object.bake(type='EMIT',target='IMAGE_TEXTURES',margin=10,margin_type='EXTEND',use_clear=True,use_selected_to_active=False)
 atlas.filepath_raw=str(path);atlas.file_format='PNG';atlas.save()
 # Two physically different materials share exactly one image: matte paint/wood and restrained metal.
 gold=painted_runtime('weapon_gold',atlas,.25,.38);paint=painted_runtime('weapon_paint',atlas,0,.58)
 old_categories=[slot.material.name.removeprefix('paint_') for slot in body.material_slots]
 indices=[0 if old_categories[p.material_index].startswith('gold') else 1 for p in body.data.polygons]
 body.data.materials.clear();body.data.materials.append(gold);body.data.materials.append(paint)
 for polygon,index in zip(body.data.polygons,indices):polygon.material_index=index
 return atlas
def markers(parent,definitions):
 objects=[]
 for name,position in definitions.items():
  obj=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(obj);obj.parent=parent;obj.location=position
  obj.empty_display_type='PLAIN_AXES';obj.empty_display_size=.06
  obj['xexoria_role']='trail_marker' if name.startswith('fx_') else 'attachment';obj['units']='m';objects.append(obj)
 return objects
def bounds(objects):
 coords=[obj.matrix_world@Vector(corner) for obj in objects if obj.type=='MESH' for corner in obj.bound_box]
 low=[min(p[a] for p in coords) for a in range(3)];high=[max(p[a] for p in coords) for a in range(3)]
 return {'min':low,'max':high,'dimensions':[b-a for a,b in zip(low,high)]}
def copy_lod(body,string,root):
 clone=body.copy();clone.data=body.data.copy();bpy.context.collection.objects.link(clone);clone.name=body.name+'_lod1';clone.parent=root
 active([clone]);mod=clone.modifiers.new('LOD1_half','DECIMATE')
 string_count=triangles(string) if string else 0;body_count=triangles(body)
 # Keep the nocks/string intact while targeting half of the whole weapon, not just the body.
 mod.ratio=max(0,(int((body_count+string_count)*.5)-string_count)/body_count);mod.use_collapse_triangulate=True
 bpy.ops.object.modifier_apply(modifier=mod.name)
 other=None
 if string:
  other=string.copy();other.data=string.data.copy();bpy.context.collection.objects.link(other);other.name=string.name+'_lod1';other.parent=root
 return clone,other
def look_at(obj,target):obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
def area(name,location,energy,size,target):
 data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='DISK';data.size=size
 obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=location;look_at(obj,target)
def reference_plane(path,location,width,height,normal_axis='Y'):
 image=bpy.data.images.load(str(path),check_existing=True)
 width=height*image.size[0]/max(image.size[1],1)
 mat=bpy.data.materials.new('hero_reference');mat.use_nodes=True;n=mat.node_tree.nodes;l=mat.node_tree.links;n.clear()
 tex=n.new('ShaderNodeTexImage');tex.image=image;emit=n.new('ShaderNodeEmission');out=n.new('ShaderNodeOutputMaterial');emit.inputs['Strength'].default_value=.75
 l.new(tex.outputs['Color'],emit.inputs['Color']);l.new(emit.outputs[0],out.inputs['Surface'])
 bpy.ops.mesh.primitive_plane_add(size=2,location=location);obj=bpy.context.object;obj.name='HERO_IMAGE_REFERENCE'
 obj.rotation_euler=(pi_over_2(),0,0) if normal_axis=='Y' else (0,pi_over_2(),0);obj.scale=(width*.5,height*.5,1);obj.data.materials.append(mat);return obj
def pi_over_2():return math.pi*.5
def label(text,position,size=.065,normal_axis='Y'):
 data=bpy.data.curves.new('label','FONT');data.body=text;data.align_x='CENTER';data.size=size;data.extrude=0
 obj=bpy.data.objects.new('REVIEW_LABEL',data);bpy.context.collection.objects.link(obj);obj.location=position
 obj.rotation_euler=(pi_over_2(),0,0) if normal_axis=='Y' else (pi_over_2(),0,pi_over_2())
 material=flat_material('label_ink','19222E');bsdf=material.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Emission Color'].default_value=(.4,.4,.4,1);bsdf.inputs['Emission Strength'].default_value=.6
 data.materials.append(material);return obj
def witness(location):
 root=bpy.data.objects.new('SCALE_WITNESS_1_8M',None);bpy.context.collection.objects.link(root);root.location=location
 mat=flat_material('witness_grey','6F7982');objects=[]
 # This is an explicitly labelled scale silhouette, not a replacement hero.
 for name,pos,scale in [('head',(0,0,1.68),(.12,.115,.12)),('torso',(0,0,1.28),(.20,.12,.32)),('hips',(0,0,.88),(.16,.115,.14)),
 ('leg_l',(-.08,0,.45),(.055,.065,.43)),('leg_r',(.08,0,.45),(.055,.065,.43)),('foot_l',(-.08,-.035,.045),(.065,.10,.045)),('foot_r',(.08,-.035,.045),(.065,.10,.045)),('arm_l',(-.24,0,1.19),(.045,.055,.27)),('arm_r',(.24,0,1.19),(.045,.055,.27))]:
  bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8);obj=bpy.context.object;obj.name='witness_'+name;obj.parent=root;obj.location=pos;obj.scale=scale;obj.data.materials.append(mat);objects.append(obj)
 return root,objects
def review(hero,asset_objects,root,hero_reference,evidence,revision):
 scene=bpy.context.scene;scene.cycles.samples=24;scene.render.resolution_x=768;scene.render.resolution_y=1024;scene.render.resolution_percentage=100
 bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-1.0));floor=bpy.context.object;floor.name='REVIEW_FLOOR';floor.data.materials.append(flat_material('review_floor','D3D6D7'))
 camera_data=bpy.data.cameras.new('ReviewCamera');camera=bpy.data.objects.new('ReviewCamera',camera_data);bpy.context.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO'
 asset_bounds=bounds(asset_objects);center=(asset_bounds['min'][2]+asset_bounds['max'][2])*.5;floor.location.z=asset_bounds['min'][2]-.008
 area('soft_key',(-3,-4,5),500,4,(0,0,center));area('cool_fill',(3,-2,2),220,3,(0,0,center));area('soft_back',(1,3,4),350,3,(0,0,center))
 front=(-4,0,center) if hero=='03' else (0,-4,center)
 views={'front':front,'side':(0,-4,center) if hero=='03' else (4,0,center),'three-quarter':(-3 if hero=='03' else 3,-4,center+.2)}
 camera_data.ortho_scale=asset_bounds['dimensions'][2]*1.18
 captures=[]
 for name,position in views.items():
  camera.location=position;look_at(camera,(0,0,center))
  caption=label('BLENDER REVIEW | HERO '+hero+' | '+name,(0,0,asset_bounds['max'][2]+.09),.041);caption.rotation_euler=camera.rotation_euler
  scene.render.filepath=str(evidence/f'{revision}-{name}.png');bpy.ops.render.render(write_still=True);captures.append(scene.render.filepath);bpy.data.objects.remove(caption,do_unlink=True)
 # Compare the weapon at metre scale to the approved front image and an exact 1.8 m witness.
 root.location.z=-asset_bounds['min'][2]+.02;bpy.context.view_layer.update();floor.location.z=0
 ref_axis='Y';reference_plane(hero_reference,(-.90,.34,.94),1.05,1.80,ref_axis)
 witness_root,witness_meshes=witness((.80,0,0));label('HERO IMAGE',(-.90,-.03,-.13));label('1.8 m WITNESS',(.80,-.03,-.13))
 label('BLENDER REVIEW | '+REFERENCES[hero][2].upper(),(0,-.03,2.54),.06)
 camera_data.ortho_scale=3.15;camera.location=(-3.4 if hero=='03' else 3.4,-6,2.30);look_at(camera,(-.05,0,1.17));scene.render.filepath=str(evidence/f'{revision}-hero-witness.png');bpy.ops.render.render(write_still=True);captures.append(scene.render.filepath)
 # Matched project distance/FOV, explicitly a Blender size check rather than runtime acceptance.
 camera_data.type='PERSP';camera_data.sensor_fit='VERTICAL';camera_data.lens=camera_data.sensor_height/(2*math.tan(1.02*.5))
 target=Vector((0,0,1.65));camera.location=target+Vector((0,-math.sin(1.18)*13,math.cos(1.18)*13));look_at(camera,target)
 scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.cycles.samples=12
 scene.render.filepath=str(evidence/f'{revision}-13m-scale.png');bpy.ops.render.render(write_still=True);captures.append(scene.render.filepath)
 root.location=(0,0,0);bpy.context.view_layer.update()
 return captures
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--hero',choices=list(RECIPES),required=True);parser.add_argument('--revision',default='r1');parser.add_argument('--texture-size',type=int,choices=[512,1024],default=1024);parser.add_argument('--no-renders',action='store_true');args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
 hero=args.hero;revision=args.revision;started=time.time();out=ROOT/'assets/models/weapons'/('hero-'+hero)/revision;evidence=ROOT/'planning/evidence/hero-weapons-20261002'/('hero-'+hero)/revision
 if out.exists() or evidence.exists():raise RuntimeError('Version exists; select a fresh revision. Source and prior evidence are immutable.')
 out.mkdir(parents=True);evidence.mkdir(parents=True);(out/'textures').mkdir()
 snapshots=out/'source';snapshots.mkdir()
 for filename in ['build_hero_weapons.py','weapon_geometry.py']:
  (snapshots/filename).write_bytes(Path(__file__).with_name(filename).read_bytes())
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.render.threads_mode='FIXED';scene.render.threads=2
 scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.35,.39,.45,1);scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1;scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0
 specs,definitions=RECIPES[hero]();root=bpy.data.objects.new('weapon_'+REFERENCES[hero][2],None);bpy.context.collection.objects.link(root);root['xexoria_role']='weapon';root['grip_pivot']='origin';root['units']='m'
 source_mats={key:make_paint(key) for key in {p.paint for p in specs if p.paint!='string'}}
 solids=[];string=None
 for part in specs:
  obj=mesh_part(part)
  if part.paint=='string':string=obj;obj.data.materials.append(flat_material('bow_string','C2B296'));continue
  obj.data.materials.append(source_mats[part.paint]);solids.append(obj)
 active(solids);bpy.ops.object.join();body=bpy.context.object;body.name=REFERENCES[hero][2]+'_body';body.parent=root
 smart_uv(body);atlas_path=out/'textures'/f'{REFERENCES[hero][2]}_albedo.png';atlas=bake_atlas(body,atlas_path,args.texture_size)
 if string:
  string.parent=root;basis=string.shape_key_add(name='Basis');draw=string.shape_key_add(name='DrawBack')
  # Three centre-line rings: move the middle ring only. Endpoints stay at the horn sockets.
  for i in range(4,8):draw.data[i].co.y+=.306
  draw.value=0;string.active_shape_key_index=0;string.show_only_shape_key=False
  string['draw_pose']='DrawBack';string['draw_distance_m']=.306;smart_uv(string)
 marker_objects=markers(root,definitions);asset_objects=[body]+([string] if string else [])
 bpy.context.view_layer.update()
 blend=out/f'{REFERENCES[hero][2]}-editable.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
 if string:
  editable_string=string;rest=[v.co.copy() for v in string.data.shape_keys.key_blocks['Basis'].data]
  string=editable_string.copy();string.data=editable_string.data.copy();bpy.context.collection.objects.link(string)
  active([string]);bpy.ops.object.shape_key_remove(all=True,apply_mix=False)
  for vertex,co in zip(string.data.vertices,rest):vertex.co=co
  editable_string.name='bow_string_editable_source';editable_string.hide_render=True;editable_string.hide_viewport=True
  string.name='bow_string_rest';string.data.update();asset_objects=[body,string]
 bpy.context.view_layer.update();source_facts={'triangles':sum(triangles(o) for o in asset_objects),'bounds':bounds(asset_objects),'texture_count':1,'texture_size':args.texture_size,'markers':definitions}
 if source_facts['triangles']>2500:raise RuntimeError('LOD0 triangle cap breached')
 base=out/f'hero{hero}_{REFERENCES[hero][2]}_lod0.glb'
 export_glb([root,*asset_objects,*marker_objects],base,'prop',texture_dir=out/'textures',asset_id=f'hero{hero}_{REFERENCES[hero][2]}',inputs=[__file__,str(Path(__file__).with_name('weapon_geometry.py'))],notes=['One painted albedo atlas with baked AO/top-light; no reference pixels sampled.','Sockets/trails exported as named nodes.','Bow morph remains editable source; static drawn pose exported separately.'])
 lod_body,lod_string=copy_lod(body,string,root);lod_objects=[lod_body]+([lod_string] if lod_string else [])
 lod_triangles=sum(triangles(o) for o in lod_objects)
 if not .47<=lod_triangles/source_facts['triangles']<=.53 or lod_triangles>1250:raise RuntimeError('LOD1 must preserve 47–53 percent of LOD0 and stay <=1250 triangles')
 export_glb([root,*lod_objects,*marker_objects],out/f'hero{hero}_{REFERENCES[hero][2]}_lod1.glb','prop',texture_dir=out/'textures',asset_id=f'hero{hero}_{REFERENCES[hero][2]}_lod1')
 for obj in lod_objects:obj.hide_render=True;obj.hide_viewport=True
 if string:
  drawn=string.copy();drawn.data=string.data.copy();bpy.context.collection.objects.link(drawn);drawn.name='bow_string_drawn';drawn.parent=root
  # Explicit static pose coordinates also avoid dependence on glTF morph export policy.
  for i in range(4,8):drawn.data.vertices[i].co.y=string.data.vertices[i].co.y+.306
  export_glb([root,drawn],out/'hero03_bow_string_drawn.glb','prop',texture_dir=out/'textures',asset_id='hero03_bow_string_drawn')
  drawn.hide_render=True;drawn.hide_viewport=True
  save_json(out/'bow-string-poses.json',{'mesh':'bow_string_rest','coordinate_frame':'Blender metres: +Z long axis, +Y draw. Export maps to glTF +Y long axis, -Z draw.','draw_back_m':.306,'moving_vertex_indices':list(range(4,8)),'base_positions':[list(v.co) for v in string.data.vertices],'drawn_positions':[list(v.co) for v in drawn.data.vertices],'runtime_task':'Interpolate string vertices or bind a bow rig; no client code changed.'})
 weapon_time,hero_time,_=REFERENCES[hero];source_dir=Path(str(_XEXORIA_ASSET_SOURCE.parent / 'hero'))/hero
 weapon_ref=source_dir/f'ChatGPT Image Oct 1, 2026, {weapon_time} PM.png';hero_ref=source_dir/f'ChatGPT Image Oct 1, 2026, {hero_time} PM.png'
 captures=[] if args.no_renders else review(hero,asset_objects,root,hero_ref,evidence,revision)
 receipt={'schema':'xexoria.hero-weapon/1','hero':hero,'revision':revision,'status':'BLENDER_CANDIDATE','source':source_facts,'lod1':{'triangles':lod_triangles,'ratio':lod_triangles/source_facts['triangles']},'references':{str(p):digest(p) for p in [weapon_ref,hero_ref]},'source_blend':str(blend),'source_glb':str(base),'captures':captures,'runtime_acceptance':'UNVERIFIED: no client/server edits or native Babylon capture in this lane.','texture':{'path':str(atlas_path),'sha256':digest(atlas_path)},'elapsed_s':round(time.time()-started,2),'blender':bpy.app.version_string,'render_device':'CPU','render_threads':2}
 save_json(evidence/'receipt.json',receipt);print(json.dumps({'hero':hero,'revision':revision,'triangles':source_facts['triangles'],'lod1':lod_triangles,'elapsed_s':receipt['elapsed_s']}))
if __name__=='__main__':main()
