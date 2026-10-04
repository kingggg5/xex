"""Export fitted Rigify actions as deform-only, sampled 30fps runtime GLBs."""
import argparse,json,sys
from pathlib import Path
import bpy
p=argparse.ArgumentParser();p.add_argument('--blend',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.blend.resolve()))
body=bpy.data.objects['Minotaur_BovineShaman'];rig=bpy.data.objects['Minotaur_Rigify']
rig.animation_data.action=None;rig.animation_data.use_nla=False
for pb in rig.pose.bones:pb.matrix_basis.identity()
bpy.context.scene.frame_set(0);bpy.context.view_layer.update()
original_mesh=body.data.copy()
material=body.data.materials[0]
texture_node=next(n for n in material.node_tree.nodes if n.type=='TEX_IMAGE')
original_image=texture_node.image
entries=[]
for level,ratio,size in [(0,1.,4096),(1,.50,2048),(2,.22,1024)]:
    body.data=original_mesh.copy()
    if level:
        mod=body.modifiers.new('NativeLOD_Decimate','DECIMATE');mod.ratio=ratio;mod.use_collapse_triangulate=True
        # Skin is preserved at bind pose; apply the topology modifier before armature.
        bpy.ops.object.select_all(action='DESELECT');body.select_set(True);bpy.context.view_layer.objects.active=body
        bpy.ops.object.modifier_move_up(modifier=mod.name)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    image=original_image.copy();image.name=f'minotaur_albedo_{size}'
    image.scale(size,size);image.file_format='JPEG';image.filepath_raw=str((a.out/f'minotaur_albedo_{size}.jpg').resolve())
    image.save()
    fresh=bpy.data.images.load(image.filepath_raw,check_existing=False)
    bpy.data.images.remove(image);image=fresh;texture_node.image=image
    bpy.ops.object.select_all(action='DESELECT');body.select_set(True);rig.select_set(True)
    bpy.context.view_layer.objects.active=rig
    filename=f'minotaur_lod{level}.glb'
    bpy.ops.export_scene.gltf(filepath=str((a.out/filename).resolve()),export_format='GLB',use_selection=True,
        export_materials='EXPORT',export_image_format='JPEG',export_animations=True,export_animation_mode='ACTIONS',
        export_frame_range=False,export_frame_step=1,export_force_sampling=True,export_def_bones=True,
        export_skins=True,export_influence_nb=4,export_all_influences=False,export_reset_pose_bones=True,
        export_anim_slide_to_zero=True,export_cameras=False,export_lights=False,export_extras=False)
    body.data.calc_loop_triangles()
    entries.append({'lod':level,'file':filename,'triangles':len(body.data.loop_triangles),
                    'texture_dimensions':[size,size],'bytes':(a.out/filename).stat().st_size})
    bpy.data.images.remove(image)
(a.out/'lod-export.json').write_text(json.dumps({'blender':bpy.app.version_string,'lods':entries,
    'export':'Deform-only bones; Rigify constraints sampled at30fps into8actions; source UVs preserved'},indent=2)+'\n',encoding='utf-8')
print('LOD_EXPORT',json.dumps(entries))
