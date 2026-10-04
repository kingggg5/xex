"""Original detailed sword from owner's approved reference; existing kit craft/UV/paint bake, CPU only.
No Tripo job or reference pixels sampled. Immutable versioned candidate, grip origin, Blender+Z blade axis.
"""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[3]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import sys,math,json,hashlib,time
from pathlib import Path
import bpy
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import weapon_geometry as G
import build_hero_weapons as W
ROOT=HERE.parents[2]
OUT=Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-hero01-sword-r01'))
REF=Path(str(_XEXORIA_ASSET_SOURCE.parent / 'hero/01/ChatGPT Image Oct 1, 2026, 01_15_52 PM.png'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected=sha(REF);started=time.time()
if (OUT/'receipt.json').exists():raise RuntimeError('Version frozen; choose a new revision')
OUT.mkdir(parents=True,exist_ok=True);(OUT/'textures').mkdir(exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.render.threads_mode='FIXED';scene.render.threads=2;scene.cycles.samples=8
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1;scene.view_settings.view_transform='AgX'
W.PALETTE.update(steel='ABB1BA',steel_edge='E4E8EF',steel_dark='5D6572')
parts=[]
# Thick central ridge and bevel rings form the blade; the point stays a real volume from either side.
blade=[(0,1.17),(.105,.94),(.077,.82),(.085,.40),(.113,.31),(.071,.27),(.071,.15),(-.071,.15),(-.071,.27),(-.113,.31),(-.085,.40),(-.077,.82),(-.105,.94)]
parts.append(G.outline('forged_blade',blade,(0,0,0),.046,'steel'))
for side in (-1,1):
 path=[(side*.036,-.026,.25),(side*.030,-.034,.42),(side*.026,-.032,.76),(0,-.019,1.16)]
 parts.append(G.sweep(f'edge_highlight_{side}',path,[.007,.006,.005,.001],[.002,.002,.002,.001],'steel_edge',sides=4))
 # Swept quillons are connected to the guard; broad bevels, carved sockets and raised gold rails.
 guard=[(.045,.13),(.105,.12),(.16,.135),(.215,.20),(.25,.12),(.245,.06),(.235,-.025),(.213,.04),(.16,.073),(.10,.073),(.045,.086)]
 parts.append(G.outline(f'quillon_{side}',[(side*x,z) for x,z in guard],(0,0,0),.075,'gold'))
 parts.append(G.sweep(f'guard_rail_{side}',[(side*.05,-.044,.115),(side*.12,-.044,.107),(side*.17,-.039,.124),(side*.212,-.026,.184)],.009,.006,'gold_light',sides=4))
 parts.append(G.gem(f'guard_tip_{side}',(side*.205,0,.16),.11,.074,.055,'gold_light',4))
parts.append(G.diamond_mount('guard_gem_mount',(0,-.006,.11),.175,.22,.079))
parts.append(G.gem('guard_azure_crystal',(0,-.045,.13),.143,.105,.05,'blue',4))
parts.append(G.gem('guard_back_crystal',(0,.045,.13),.143,.105,.05,'blue',4))
# Gold spine inlay and repeated discrete diamond mounts have credible depth and thickness.
parts.append(G.outline('gold_spine',[(0,.53),(.029,.35),(.046,.20),(0,.15),(-.046,.20),(-.029,.35)],(0,-.028,0),.025,'gold'))
for i in range(3):
 z=.22+i*.088
 parts.append(G.diamond_mount(f'spine_diamond_{i}',(0,-.043,z),.068-.009*i,.086,.019))
# Wrapped leather grip with separate ferrules, alternating raised diagonal seams and faceted pommel.
parts.append(G.rod('leather_grip',(0,0,-.16),(0,0,.045),.036,'leather',10))
for i in range(8):
 z=-.15+i*.024
 path=[(.036*math.cos(a),.036*math.sin(a),z+.02*a/(2*math.pi)) for a in [j*2*math.pi/12 for j in range(13)]]
 parts.append(G.sweep(f'leather_wrap_{i}',path,.003,.003,'wood',sides=4))
for z in (-.165,.042):parts.append(G.collar(f'ferrule_{z}',z,.046,'gold_light',10))
parts.append(G.diamond_mount('pommel_crown',(0,0,-.235),.12,.19,.07))
parts.append(G.gem('pommel_crystal',(0,-.035,-.229),.095,.072,.04,'blue',4))
parts.append(G.gem('pommel_back_crystal',(0,.035,-.229),.095,.072,.04,'blue',4))
for s in (-1,1):parts.append(G.gem('pommel_lobe_'+str(s),(s*.052,0,-.227),.06,.065,.05,'gold_light',4))
assert sum(p.triangles for p in parts)<=2500,'Weapon geometry budget exceeded'
parent=bpy.data.objects.new('weapon_hero01_longsword',None);scene.collection.objects.link(parent)
palette={p.paint:W.make_paint(p.paint) for p in parts};objects=[]
for part in parts:
 obj=W.mesh_part(part);obj.data.materials.append(palette[part.paint]);objects.append(obj)
W.active(objects);bpy.ops.object.join();body=bpy.context.object;body.name='hero01_longsword_body';body.parent=parent
categories=[m.name.removeprefix('paint_') for m in body.data.materials];face_categories=[categories[p.material_index] for p in body.data.polygons]
W.smart_uv(body);atlas=W.bake_atlas(body,OUT/'textures/hero01_sword_albedo.png',1024)
metal=body.data.materials[0];metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.55
steel=W.painted_runtime('weapon_steel',atlas,.6,.3);crystal=W.painted_runtime('weapon_azure',atlas,.12,.22)
body.data.materials.append(steel);body.data.materials.append(crystal)
for polygon,category in zip(body.data.polygons,face_categories):polygon.material_index=2 if category.startswith('steel') else 3 if category=='blue' else polygon.material_index
definitions={'grip_r':(0,0,0),'grip_l':(0,0,-.085),'fx_base':(0,0,.15),'fx_tip':(0,0,1.17),'fx_head':(0,-.045,.13)}
markers=W.markers(parent,definitions);bpy.context.view_layer.update()
bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'hero01_sword_editable.blend'),compress=True)
records=[]
for lod,ratio in [(0,1),(1,.5)]:
 target=body
 if lod:
  target=body.copy();target.data=body.data.copy();scene.collection.objects.link(target);target.parent=parent;target.name='hero01_longsword_lod1';W.active([target]);modifier=target.modifiers.new('bounded_lod','DECIMATE');modifier.ratio=ratio;bpy.ops.object.modifier_apply(modifier=modifier.name);body.hide_render=True;body.hide_set(True)
 W.active([parent,target,*markers]);file=OUT/f'hero01_sword_lod{lod}.glb'
 bpy.ops.export_scene.gltf(filepath=str(file),export_format='GLB',use_selection=True,export_materials='EXPORT',export_image_format='AUTO',export_animations=False,export_cameras=False,export_lights=False,export_extras=True)
 records.append({'lod':lod,'path':str(file),'sha256':sha(file),'bytes':file.stat().st_size,'triangles':W.triangles(target),'uv0':bool(target.data.uv_layers),'materials':len(target.data.materials)})
 if lod:bpy.data.objects.remove(target,do_unlink=True)
assert expected==sha(REF),'Owner reference changed'
receipt={'schema':'xexoria.hero01-sword/1','status':'PROCEDURAL_BLENDER_CANDIDATE_NOT_TRIPO_OR_ADMITTED','source':{'path':str(REF),'sha256':expected},'construction':'Original bevelled blade, forged ridge, swept guards, inset azure gems, raised gold inlay, wrapped grip, ferrules,faceted pommel. Shared1024 painted/AO atlas with metal/steel/leather/gem response.','bounds':W.bounds([body]),'markers':definitions,'outputs':records,'source_blend':str(OUT/'hero01_sword_editable.blend'),'blender':bpy.app.version_string,'bake_device':'CPU','elapsed_s':time.time()-started,'new_tripo_credits':0,'limits':['Not a Tripo result; matching source procedural candidate while browser control unavailable.','Native silhouette, hand grip, clipping and compressed budget not accepted yet.'],'jev':'USED_VERIFIED continuation-r02 receipt reused'}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('H01_SWORD',json.dumps(records),flush=True)
