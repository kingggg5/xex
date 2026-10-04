"""Read-only source-city ray audit in the runtime city's documented basis."""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

p=argparse.ArgumentParser()
p.add_argument('--source',required=True)
p.add_argument('--output',required=True)
p.add_argument('--append',action='store_true')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a.source)
dg=bpy.context.evaluated_depsgraph_get()
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']

# City loader: Babylon AUTO X reflection, followed by authored Y=pi and
# translation Z=176. Imported Blender coordinates map to(x,z,176+y).
def to_world(co):return [float(co.x),float(co.z),float(176+co.y)]
def to_blender(co):return Vector((co[0],co[2]-176,co[1]))

target=Vector((20,1.5,156))
alpha=-2.3;beta=1.25;radius=7
camera=target+Vector((radius*math.cos(alpha)*math.sin(beta),radius*math.cos(beta),radius*math.sin(alpha)*math.sin(beta)))
points=[(20,156),(float(camera.x),float(camera.z)),(20,148),(16,154),(0,145),(24,150),(0,156)]
query=[];occlusion=[];candidate_bounds=[]
for ob in objects:
    wb=[ob.matrix_world@Vector(c) for c in ob.bound_box]
    lo=Vector(tuple(min(c[i] for c in wb) for i in range(3)))
    hi=Vector(tuple(max(c[i] for c in wb) for i in range(3)))
    # Only geometry overlapping the focal neighborhood is needed.
    if hi.x<0 or lo.x>25 or hi.y<-35 or lo.y>-15:continue
    candidate_bounds.append({'name':ob.name,'min':to_world(lo),'max':to_world(hi),'triangles':sum(len(f.vertices)-2 for f in ob.data.polygons)})
    tree=BVHTree.FromObject(ob,dg)
    inv=ob.matrix_world.inverted()
    for x,z in points:
        point=to_blender((x,500,z))
        if not (lo.x<=point.x<=hi.x and lo.y<=point.y<=hi.y):continue
        origin=inv@point
        direction=(inv.to_3x3()@Vector((0,0,-1))).normalized()
        for hit_number in range(4):
            co,normal,face,distance=tree.ray_cast(origin,direction,1000)
            if co is None:break
            w=ob.matrix_world@co
            query.append({'point_xz':[x,z],'mesh':ob.name,'surface_y':float(w.z),'face':face,'hit_number':hit_number})
            origin=co+direction*.002
    camera_b=to_blender(camera);target_b=to_blender(target)
    origin=inv@camera_b;end=inv@target_b;delta=end-origin
    co,normal,face,distance=tree.ray_cast(origin,delta.normalized(),delta.length)
    if co is not None:
        world=ob.matrix_world@co
        occlusion.append({'mesh':ob.name,'world_hit':to_world(world),'camera_distance_m':float((world-camera_b).length)})

query.sort(key=lambda r:(r['point_xz'][0],r['point_xz'][1],-r['surface_y']))
occlusion.sort(key=lambda r:r['camera_distance_m'])
report={'source':a.source,'blender':bpy.app.version_string,'runtime_basis':'world=(BlenderX,BlenderZ,176+BlenderY), fromcurrentcityloaderAUTOreflection+Ypi','mesh_count':len(objects),'camera_world':list(camera),'target_world':list(target),'vertical_hits':query,'camera_occluders':occlusion,'focal_mesh_bounds':candidate_bounds,'limits':'Static offlinegeometry; source-to-runtimebasisinferredfromloaderandcanonicalplacements. ShaderdisplacementandactualGPUcamera must be checked separately.'}
output=Path(a.output)
if a.append and output.exists():
    primary=json.loads(output.read_text(encoding='utf-8'))
    primary.setdefault('additional_source_audits',[]).append(report)
    output.write_text(json.dumps(primary,indent=2)+'\n',encoding='utf-8')
else:
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('CITY_SURFACE_AUDIT',json.dumps({'mesh_count':len(objects),'camera':list(camera),'occluders':occlusion[:8],'npc_vertical_hits':[r for r in query if r['point_xz']==[20,156]]}))
