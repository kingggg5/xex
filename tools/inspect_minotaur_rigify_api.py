import bpy, json, sys
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module='rigify')
ops = [n for n in dir(bpy.ops.object) if 'metarig' in n]
print('METARIG_OPS', json.dumps(ops))
bpy.ops.object.armature_basic_human_metarig_add()
obj=bpy.context.object
print('BONES', json.dumps([{ 'name':b.name, 'head':list(b.head_local), 'tail':list(b.tail_local), 'type':obj.pose.bones[b.name].rigify_type} for b in obj.data.bones]))
print('GLTF_ARGS', json.dumps({p.identifier: {'type':p.type,'default':str(getattr(p,'default','')),'items':[i.identifier for i in p.enum_items] if p.type=='ENUM' else []} for p in bpy.ops.export_scene.gltf.get_rna_type().properties if 'anim' in p.identifier or 'skin' in p.identifier or 'influence' in p.identifier or 'nla' in p.identifier or 'deform' in p.identifier}))
bpy.ops.pose.rigify_generate()
rig=bpy.context.object
print('RIG_CONTROLS', json.dumps([{ 'name':p.name,'deform':p.bone.use_deform,'props':dict(p.items()),'head':list(p.head),'tail':list(p.tail)} for p in rig.pose.bones if not p.name.startswith(('ORG-','MCH-','DEF-'))]))
