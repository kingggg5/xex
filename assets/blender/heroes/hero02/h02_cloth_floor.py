"""Bake a bounded vertical floor guard on secondary cloth bones, preserving hips/feet and release timing."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from bpy_extras import anim_utils
from mathutils import Vector
import h02_common as C
bpy.ops.wm.open_mainfile(filepath=str(C.WORK/'h02_anim.blend'))
scn=bpy.context.scene;arm=bpy.data.objects['hero02_XS1'];ob=bpy.data.objects['hero02_witch_lod0'];secondary=[b for b in arm.pose.bones if b.name.startswith(('skirt.','sleeve.'))]
rows=[]
for action in bpy.data.actions:
    arm.animation_data.action=action;arm.animation_data.action_slot=action.slots[0]
    first,last=map(round,action.frame_range);locations={b.name:[] for b in secondary};frames=[]
    for f in range(first,last+1):
        scn.frame_set(f)
        for bone in secondary:bone.location=(0,0,0)
        bpy.context.view_layer.update();corrections=[]
        for iteration in range(20):
            eo=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=eo.to_mesh();low=min(mesh.vertices,key=lambda v:v.co.z);z=float(low.co.z);vi=low.index;eo.to_mesh_clear()
            if z>=-.003:break
            eligible=[(ob.vertex_groups[g.group].name,g.weight) for g in ob.data.vertices[vi].groups if ob.vertex_groups[g.group].name.startswith(('skirt.','sleeve.')) and g.weight>.25]
            if not eligible:
                if z>=-.01:
                    corrections.append({'noncloth_tolerance_m':round(-z,5),'vertex':vi});break
                raise RuntimeError(f'{action.name} f{f}: floor penetration is not secondary cloth at vertex{vi} z{z}')
            name,weight=max(eligible,key=lambda item:item[1]);lift=(.002-z)/weight
            if lift>.35:raise RuntimeError(f'{action.name} f{f}: cloth lift {lift} exceeds35cm review limit')
            bone=arm.pose.bones[name];matrix=bone.matrix.copy();matrix.translation.z+=lift;bone.matrix=matrix;bpy.context.view_layer.update();corrections.append({'bone':name,'lift_m':round(lift,5),'vertex':vi})
        else:raise RuntimeError(f'{action.name} f{f}: cloth floor guard did not converge')
        for bone in secondary:locations[bone.name].append(tuple(bone.location))
        if corrections:frames.append({'frame':f,'corrections':corrections,'final_min_z':round(z,5)})
    cb=anim_utils.action_ensure_channelbag_for_slot(action,action.slots[0])
    for name,values in locations.items():
        dp=f'pose.bones["{name}"].location'
        for fc in list(cb.fcurves):
            if fc.data_path==dp:cb.fcurves.remove(fc)
        # Zero curves are intentional: cross-fades must not retain a prior clip's cloth offset.
        for axis in range(3):
            fc=cb.fcurves.new(dp,index=axis,group_name=name);fc.keyframe_points.add(len(values));fc.keyframe_points.foreach_set('co',[v for pair in zip(range(first,last+1),(p[axis] for p in values)) for v in pair]);fc.keyframe_points.foreach_set('interpolation',[1]*len(values));fc.update()
    rows.append({'clip':action.name,'frames_adjusted':len(frames),'frames':frames})
    for bone in secondary:bone.location=(0,0,0)
arm.animation_data.action=None
for bone in secondary:bone.location=(0,0,0)
bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK/'h02_anim.blend'),compress=True)
C.write_json(C.REPORTS/'cloth-floor-guard.json',{'policy':'Only existing skirt/sleeve secondary bone translations; measured body penetration below-3mm lifted to2mm; no hips/root/feet keys changed;35cm bounded correction; noncloth existing penetration up to10mm logged without moving root/hips/feet; all14clips sampled every30fpsframe','clips':rows})
print('cloth floor guard',[(r['clip'],r['frames_adjusted']) for r in rows])
