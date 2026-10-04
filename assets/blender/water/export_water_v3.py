"""Blender lossless export/reimport of the prepared canonical v3 water kit."""
from pathlib import Path
import sys, json, hashlib, math
import bpy
from mathutils import Vector
REPO=Path(__file__).resolve().parents[3]
OUT=REPO/"apps/client/src/assets/world/water-v3"
EV=REPO/"planning/evidence/water-20261002"
sys.path.insert(0,str(REPO/"assets/blender/tools"))
from export_helper import export_glb

def mesh_obj(name,data):
    me=bpy.data.meshes.new(name)
    # Rotation from canonical glTF world to Blender. Reverse LH recipe faces
    # to Blender's CCW convention; the runtime restores canonical CW facing.
    me.from_pydata([(x,-z,y) for x,y,z in data["position"]],[],[tuple(reversed(t)) for t in zip(*[iter(data["indices"])]*3)])
    me.update()
    obj=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(obj)
    for key,n in (("uv0","UVMap"),("uv1","WaterAtlas")):
        if key not in data:continue
        uv=me.uv_layers.new(name=n)
        for loop in me.loops:
            u,v=data[key][loop.vertex_index];uv.data[loop.index].uv=(u,1-v)
    normals=[(x,-z,y) for x,y,z in data["normal"]]
    me.normals_split_custom_set_from_vertices(normals)
    for p in me.polygons:p.use_smooth=True
    if "color" in data:
        color=me.color_attributes.new(name="Color",type="FLOAT_COLOR",domain="POINT")
        for item,rgba in zip(color.data,data["color"]):item.color=rgba
        me.color_attributes.active_color=color
    mat=bpy.data.materials.new(name+"-placeholder");mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value=(.06,.2,.24,1)
    bsdf.inputs["Roughness"].default_value=.3
    me.materials.append(mat)
    return obj

def main():
    data=json.loads((EV/"water-geometry.json").read_text())
    bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
    names={"surface":"fx_water_sm_surface",**{f"falls{i}":f"fx_waterfall_sm_lod{i}" for i in (0,1,2)}}
    objects=[mesh_obj(names[k],v) for k,v in data.items()]
    manifest=json.loads((OUT/"water-manifest.json").read_text())
    for name,rec in manifest["anchors"].items():
        obj=bpy.data.objects.new(name,None);x,y,z=rec["position"];obj.location=(x,-z,y)
        bpy.context.collection.objects.link(obj);objects.append(obj)
    receipt=export_glb(objects,OUT/manifest["glb"],"prop",vertex_color="ACTIVE",tangents=False,
        inputs=[REPO/"planning/levels/sunmeadow-v2-layout.json",EV/"water-geometry.json",Path(__file__)],
        copyright_text="Xexoria original seeded procedural water; no third-party assets",notes=["No quantization/meshopt: metre UV0 and atlas UV1 are shader data.","Canonical world GLB uses alignWorldAuthoredGlb."])
    support=json.loads((EV/"water-support-geometry.json").read_text())
    support_objects=[mesh_obj("water_channel_bed" if k=="bed" else "water_bank_strip",v) for k,v in support.items()]
    for obj in support_objects:obj.hide_render=True
    export_glb(support_objects,OUT/manifest["support"]["glb"],"prop",vertex_color="ACTIVE",tangents=False,
        inputs=[EV/"water-support-geometry.json"],notes=["Visual floor/banks only. Terrain owner must cut host tops; physical support stays Y=0."])
    manifest["support"]["sha256"]=hashlib.sha256((OUT/manifest["support"]["glb"]).read_bytes()).hexdigest()
    manifest["glb_sha256"]=hashlib.sha256((OUT/manifest["glb"]).read_bytes()).hexdigest()
    manifest["export_status"]=receipt.get("status")
    (OUT/"water-manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    if "--export-only" in sys.argv:
        print(json.dumps({"export_status":receipt.get("status"),"glb_sha256":manifest["glb_sha256"],"support_sha256":manifest["support"]["sha256"]}));return
    bpy.context.scene.render.engine="CYCLES";bpy.context.scene.cycles.device="CPU"
    bpy.context.scene.render.threads_mode="FIXED";bpy.context.scene.render.threads=6
    bpy.context.scene.cycles.samples=16;bpy.context.scene.cycles.use_denoising=True
    bpy.context.scene.render.resolution_x=960;bpy.context.scene.render.resolution_y=540;bpy.context.scene.render.resolution_percentage=100
    # This review is construction evidence, not a substitute for native shading.
    for obj in objects:
        if obj.type=="MESH" and "lod" in obj.name:obj.hide_render="lod0" not in obj.name
    for name,loc,scale in (("review-bank",(-10,38,-.7),(4,4,.3)),("review-cliff",(-5,38,3),(1.5,4,4))):
        bpy.ops.mesh.primitive_cube_add(size=2,location=loc);o=bpy.context.object;o.name=name;o.scale=scale
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=.3,location=(-15,40,.9))
    witness=bpy.context.object;witness.name="review-witness-1.8m";witness.scale=(.8,.8,3)
    bpy.ops.object.light_add(type="AREA",location=(-20,35,18));bpy.context.object.data.energy=2200;bpy.context.object.data.size=12
    bpy.context.scene.world.color=(.18,.22,.3)
    bpy.ops.object.camera_add(location=(-28,45,7));cam=bpy.context.object
    direction=Vector((-9.6,38,2.8))-cam.location;cam.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
    cam.data.lens=35;bpy.context.scene.camera=cam
    bpy.context.scene.render.filepath=str(EV/"BLENDER-REVIEW-water-v3-construction.png")
    bpy.ops.render.render(write_still=True)
    print(json.dumps({"export_status":receipt.get("status"),"glb_sha256":manifest["glb_sha256"],"cpu_threads":6}))

if __name__=="__main__":main()
