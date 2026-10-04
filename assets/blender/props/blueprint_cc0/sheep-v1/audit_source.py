
# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[5]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import bpy,json
from pathlib import Path
from mathutils import Vector
E=Path(str(_XEXORIA_REPO / 'planning/evidence/blueprint-p0-20261003/cc0/sheep-v1'))
scene=bpy.context.scene;scene.render.threads_mode='FIXED';scene.render.threads=6
meshes=[]
for ob in bpy.data.objects:
 if ob.type!='MESH':continue
 ob.data.calc_loop_triangles();pts=[ob.matrix_world@Vector(v) for v in ob.bound_box]
 meshes.append({'name':ob.name,'vertices':len(ob.data.vertices),'triangles':len(ob.data.loop_triangles),'bounds':{'min':[min(p[i] for p in pts) for i in range(3)],'max':[max(p[i] for p in pts) for i in range(3)]},'scale':list(ob.scale),'matrix_local':[list(r) for r in ob.matrix_local],'matrix_world':[list(r) for r in ob.matrix_world],'parent_inverse':[list(r) for r in ob.matrix_parent_inverse],'parent':ob.parent.name if ob.parent else None,'modifiers':[{'name':m.name,'type':m.type,'object':m.object.name if m.type=='ARMATURE' and m.object else None} for m in ob.modifiers],'vertex_groups':[g.name for g in ob.vertex_groups],'materials':[m.name if m else None for m in ob.data.materials],'uv_layers':[u.name for u in ob.data.uv_layers]})
rigs=[{'name':o.name,'bones':[{'name':b.name,'deform':b.use_deform,'parent':b.parent.name if b.parent else None} for b in o.data.bones],'constraints':[(p.name,[c.type for c in p.constraints]) for p in o.pose.bones if p.constraints],'action':o.animation_data.action.name if o.animation_data and o.animation_data.action else None,'nla':[(t.name,[s.name for s in t.strips]) for t in o.animation_data.nla_tracks] if o.animation_data else []} for o in bpy.data.objects if o.type=='ARMATURE']
actions=[{'name':a.name,'frames':list(a.frame_range),'users':a.users,'slots':[s.identifier for s in a.slots]} for a in bpy.data.actions]
materials=[{'name':m.name,'diffuse':list(m.diffuse_color),'use_nodes':m.use_nodes,'nodes':[n.type for n in m.node_tree.nodes] if m.use_nodes else []} for m in bpy.data.materials]
report={'source':bpy.data.filepath,'blender':bpy.app.version_string,'autoexec_enabled':bpy.context.preferences.filepaths.use_scripts_auto_execute,'fps':scene.render.fps,'frames':[scene.frame_start,scene.frame_end],'meshes':meshes,'rigs':rigs,'armature_transforms':[(o.name,[list(r) for r in o.matrix_world],list(o.scale)) for o in bpy.data.objects if o.type=='ARMATURE'],'actions':actions,'materials':materials,'texts':[t.name for t in bpy.data.texts],'drivers':[(o.name,len(o.animation_data.drivers)) for o in bpy.data.objects if o.animation_data and o.animation_data.drivers]}
if len(rigs)!=1 or not meshes or not actions:raise RuntimeError('Licensedsheep lacks expectedrig/mesh/actions')
E.mkdir(parents=True,exist_ok=True);(E/'source-rig-audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({'meshTris':sum(m['triangles'] for m in meshes),'rigs':[(r['name'],len(r['bones'])) for r in rigs],'actions':actions,'bounds':[(m['name'],m['bounds']) for m in meshes]}))
