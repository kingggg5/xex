"""Hero03 local form CANDIDATE from immutable Tripo geometry.

Root owns the CPU slot. This file does not launch Blender or providers.
Run diagnose first. An apply run uses a NEW run directory and remains art/rig
UNVERIFIED until actual same-camera review. No UV, texture, rig or runtime edits.
Uses existing mesh/BMesh proportional edits, native curve bevels and UV spheres;
no global voxel remesh, global welding, automatic boundary filling or shader masks.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

SOURCE_SHA = "bdce6f6c664d552ad71624622f6d70921e8b782bcfc1cc7c627b2a72da4d11e2"
SOURCE_VERTICES = 5538
SOURCE_TRIANGLES = 10828
EXPECTED_COMPONENTS = [5114, 268, 40, 38, 21, 21, 18, 18]
SOURCE_LIMIT_TRIANGLES = 11750  # approximate11k bake-source, never runtime acceptance
OUTPUT_ROOT_NAME = "20261004-hero03-form-r01"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smooth_band(value, low, high, fade):
    if value <= low or value >= high:
        return 0.0
    t = min(1.0, (value-low)/fade, (high-value)/fade)
    return t*t*(3.0-2.0*t)


def component_sets(bm):
    bm.verts.ensure_lookup_table()
    seen, parts = set(), []
    for vertex in bm.verts:
        if vertex.index in seen:
            continue
        todo, part = [vertex], []
        seen.add(vertex.index)
        while todo:
            current = todo.pop()
            part.append(current)
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    todo.append(other)
        parts.append(part)
    return sorted(parts, key=len, reverse=True)


def bounds(vertices):
    return {"min": [min(v.co[k] for v in vertices) for k in range(3)],
            "max": [max(v.co[k] for v in vertices) for k in range(3)]}


def topology(bm):
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    parts = component_sets(bm)
    part_of = {v.index: i for i, part in enumerate(parts) for v in part}
    extras = [e for e in bm.edges if not e.is_manifold and not e.is_boundary]
    return {"vertices":len(bm.verts), "triangles":sum(len(f.verts)-2 for f in bm.faces),
            "components": [{"vertices":len(part), **bounds(part)} for part in parts],
            "boundary_edges":sum(e.is_boundary for e in bm.edges),
            "non_manifold_edges_including_boundaries":sum(not e.is_manifold for e in bm.edges),
            "additional_nonmanifold":len(extras),
            "zero_area_faces":sum(f.calc_area()<1e-10 for f in bm.faces),
            "additional_nonmanifold_witnesses":[
                {"edge":e.index, "component":part_of[e.verts[0].index],
                 "linked_faces":len(e.link_faces), "ends":[list(v.co) for v in e.verts]}
                for e in extras],
            "boundary_policy":"Preserve intentional open cloth/ornaments; never blanket-fill"}


def projected_front_surface(bm, x, z):
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    hit, normal, face, distance = BVHTree.FromBMesh(bm).ray_cast(Vector((x,-1.0,z)), Vector((0,1,0)), 2.0)
    if hit is None or not (-.16 < hit.y < .015):
        raise RuntimeError(f"No guarded frontal face hit at{(x,z)}")
    return {"point":list(hit), "normal":list(normal), "face":face, "distance":distance}


def plan_regions(bm):
    parts = component_sets(bm)
    if sorted([len(p) for p in parts],reverse=True) != EXPECTED_COMPONENTS:
        raise RuntimeError("Source component roster differs from the pinned review")
    main, tail = parts[:2]
    tb = bounds(tail)
    if not (abs(tb["min"][0]+.0651855543)<2e-6 and abs(tb["max"][2]-.6171875)<2e-6):
        raise RuntimeError("Tail island bounds do not match the exact268-vertex witness")
    # Source review uses BlenderZ-up with front-Y. Fitted rear torso repair is
    # restricted to the source main island; separate pouches/tail stay untouched.
    rear = [v for v in main if abs(v.co.x)<.15 and .525<v.co.z<.725 and v.co.y>.012]
    if not 30 <= len(rear) <= 800:
        raise RuntimeError(f"Rear torso region count{len(rear)} is not plausible")
    eyes = [projected_front_surface(bm, sign*.041, .855) for sign in [-1,1]]
    mouth = projected_front_surface(bm, 0, .774)
    protected = [v for v in bm.verts if v.co.z<.12 or (abs(v.co.x)>.18 and .40<v.co.z<.68)]
    return {"main":main, "tail":tail, "rear":rear, "eyes":eyes, "mouth":mouth,
            "protected":{v.index:tuple(v.co) for v in protected}}


def repair_existing_geometry(bm, plan):
    # Convert the poncho slab's outer rear surface into a fitted torso surface.
    # It remains existing geometry, with a visible seam/lace layer added later.
    changed_rear = 0
    for v in plan["rear"]:
        x,y,z = v.co
        weight = smooth_band(z,.525,.725,.024)
        half_width = .087 + .024*max(0.0,min(1.0,(z-.545)/.155))
        radius = max(0.0, 1.0-(x/.15)**2)
        fitted_y = .039 + .012*math.sqrt(radius)
        shrink = min(1.0, half_width/max(abs(x),half_width))
        v.co.x = x*(1.0-weight+weight*shrink)
        v.co.y = y*(1.0-weight)+fitted_y*weight
        changed_rear += weight>0
    # Layer the existing tail silhouette instead of adding a second tail or
    # noisy hair. Each of five fur tiers moves the existing edge vertices only.
    changed_tail = 0
    for v in plan["tail"]:
        x,y,z = v.co
        taper = smooth_band(z,.165,.606,.045)
        edge = max(0.0,min(1.0,(abs(x)-.020)/.036))
        bands = sum(math.exp(-((z-level)/.020)**2) for level in [.235,.310,.390,.475,.550])
        displacement = .0075*edge*bands*taper
        if abs(x)>1e-7:
            v.co.x += math.copysign(displacement,x)
        v.co.y += .0020*bands*taper
        changed_tail += displacement>1e-6
    # Sculpt small orbital depressions in existing frontal skin vertices.
    # A ray-hit-relative depth gate prevents the operation affecting rear hair.
    eye_counts = []
    for eye in plan["eyes"]:
        cx,cy,cz = eye["point"]
        selected = 0
        for v in plan["main"]:
            r=((v.co.x-cx)/.025)**2+((v.co.z-cz)/.016)**2
            if r<1 and abs(v.co.y-cy)<.023:
                v.co.y += .0095*(1-r)**2
                selected += 1
        eye_counts.append(selected)
    if min(eye_counts)<4:
        raise RuntimeError(f"Orbital skin vertex coverage too low:{eye_counts}")
    for v in bm.verts:
        if v.index in plan["protected"] and tuple(v.co)!=plan["protected"][v.index]:
            raise RuntimeError("A protected paw/hand/thumb vertex changed")
    bm.normal_update()
    return {"rear_surface_vertices":changed_rear,"tail_edge_vertices":changed_tail,
            "orbital_vertices":eye_counts,"protected_vertices_unchanged":len(plan["protected"])}


def curve_mesh(name, points, radius, collection):
    import bpy
    curve = bpy.data.curves.new(name,"CURVE")
    curve.dimensions="3D";curve.resolution_u=1
    curve.bevel_depth=radius;curve.bevel_resolution=0;curve.resolution_u=1
    curve.use_fill_caps=True
    spline=curve.splines.new("POLY");spline.points.add(len(points)-1)
    for item,point in zip(spline.points,points):item.co=(*point,1.0)
    obj=bpy.data.objects.new(name,curve);collection.objects.link(obj)
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=bpy.data.meshes.new_from_object(evaluated)
    replacement=bpy.data.objects.new(name+"-geometry",mesh);collection.objects.link(replacement)
    bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.curves.remove(curve)
    return replacement


def add_relief(plan, collection):
    import bpy
    generated=[]
    for eye_index,eye in enumerate(plan["eyes"]):
        x,y,z=eye["point"]
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,location=(x,y+.002,z))
        eyeball=bpy.context.object;eyeball.name=f"hero03-eye-{eye_index}-form"
        eyeball.scale=(.017,.008,.009)
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        generated.append(eyeball)
        for upper,phase in [(True,0),(False,math.pi)]:
            pts=[]
            for index in range(7):
                angle=phase+index*math.pi/6
                pts.append((x+.021*math.cos(angle),y-.0015,z+.011*math.sin(angle)))
            generated.append(curve_mesh(f"hero03-eyelid-{eye_index}-{'upper' if upper else 'lower'}",pts,.0018,collection))
    x,y,z=plan["mouth"]["point"]
    # Source canine muzzle: modest curved mouth relief, not a human smile line.
    lip=[(x-.021,y+.003,z-.002),(x-.011,y-.001,z-.005),(x,y-.002,z-.004),
         (x+.011,y-.001,z-.005),(x+.021,y+.003,z-.002)]
    generated.append(curve_mesh("hero03-mouth-relief",lip,.0014,collection))
    # Physical crossing lace seams communicate the newly fitted exposed rear
    # vest. They are silhouette-neutral detail, not a replacement cape shell.
    for index in range(4):
        z=.562+index*.024
        generated.append(curve_mesh(f"hero03-rear-lace-{index}",
            [(-.031,.054,z),(.031,.054,z+.018)],.0011,collection))
    return generated


def configure_review(objects):
    import bpy
    from mathutils import Vector
    scene=bpy.context.scene
    # Match the original11-view CPU review's scale/pivot/camera recipes.
    points=[obj.matrix_world@v.co for obj in objects for v in obj.data.vertices]
    low=Vector([min(p[k] for p in points) for k in range(3)])
    high=Vector([max(p[k] for p in points) for k in range(3)])
    scale=1.85/(high.z-low.z);pivot=Vector(((low.x+high.x)/2,(low.y+high.y)/2,low.z))
    for obj in objects:
        world=obj.matrix_world.copy();obj.parent=None
        for v in obj.data.vertices:v.co=(world@v.co-pivot)*scale
        obj.matrix_world.identity();obj.data.update()
        material=bpy.data.materials.new(obj.name+"-clay");material.diffuse_color=(.55,.53,.48,1)
        material.use_nodes=True
        bsdf=material.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value=(.55,.53,.48,1)
        bsdf.inputs["Roughness"].default_value=.65
        obj.data.materials.clear();obj.data.materials.append(material)
        for polygon in obj.data.polygons:polygon.use_smooth=True
    scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=8
    scene.cycles.max_bounces=2;scene.cycles.diffuse_bounces=1;scene.cycles.glossy_bounces=1
    scene.render.threads_mode="FIXED";scene.render.threads=2
    scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.world=bpy.data.worlds.new("hero03-form-review-world")
    scene.world.use_nodes=True
    background=scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value=(.16,.18,.21,1)
    background.inputs["Strength"].default_value=.6
    for name,position,power,size in [("key",(-3,-4,5),450,4),("fill",(3,-1,3),200,3),("back",(0,3,4),350,3)]:
        data=bpy.data.lights.new(name,"AREA");data.energy=power;data.shape="DISK";data.size=size
        light=bpy.data.objects.new(name,data);scene.collection.objects.link(light);light.location=position
        light.rotation_euler=(Vector((0,0,.925))-light.location).to_track_quat('-Z','Y').to_euler()
    camera_data=bpy.data.cameras.new("hero03-form-review-camera")
    camera=bpy.data.objects.new("hero03-form-review-camera",camera_data);scene.collection.objects.link(camera);scene.camera=camera
    return scene,camera,camera_data,scale


def capture(objects, output):
    from mathutils import Vector
    import bpy
    scene,camera,camera_data,scale=configure_review(objects)
    shots=[];ratio=1.85/2.05;centre=Vector((0,0,.925))
    def shoot(name,direction,target=centre,ortho=2.35*ratio):
        direction=Vector(direction).normalized();camera.location=target+direction*6
        camera.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()
        camera_data.type="ORTHO";camera_data.ortho_scale=ortho;camera_data.clip_end=30
        scene.render.filepath=str(output/f"BLENDER_CPU_{name}.png")
        bpy.ops.render.render(write_still=True)
        shots.append({"view":name,"file":scene.render.filepath,"target":list(target),"direction":list(direction),"ortho_scale":ortho})
    for name,d in [("front",(0,-1,.05)),("back",(0,1,.05)),("left",(1,0,.05)),("right",(-1,0,.05)),
                   ("threequarter",(.65,-1,.2)),("back_threequarter",(-.65,1,.25))]:shoot(name,d)
    shoot("head",(0,-1,.05),Vector((0,0,1.85*ratio)),.65*ratio)
    points=[v.co.copy() for obj in objects for v in obj.data.vertices]
    for side,sign in [("L",1),("R",-1)]:
        hand_pts=[p for p in points if .65*ratio<p.z<1.32*ratio and p.x*sign>.30*ratio]
        furthest=max(hand_pts,key=lambda p:p.x*sign)
        target=Vector((furthest.x-sign*.075*ratio,furthest.y,.99*ratio))
        shoot(f"hand_{side}_front",(0,-1,.1),target,.50*ratio)
        shoot(f"hand_{side}_side",(sign,0,.1),target,.50*ratio)
    return shots,scale


def main():
    import bpy
    import bmesh
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--run",required=True)
    parser.add_argument("--mode",choices=["diagnose","apply"],default="diagnose")
    parser.add_argument("--render",action="store_true")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    source=args.source.resolve();out=args.out.resolve()
    if out.name!=OUTPUT_ROOT_NAME or not args.run.replace('-','').replace('_','').isalnum():
        raise RuntimeError("Use the exact authorized output root and a bounded new run name")
    if digest(source)!=SOURCE_SHA:raise RuntimeError("Immutable Hero03 source hash differs")
    run=out/args.run
    if run.exists():raise RuntimeError("Output run exists; preserve it and choose a new run name")
    run.mkdir(parents=True)
    report={"schema":"xexoria.hero03.form-repair/1","mode":args.mode,"source":str(source),"source_sha256":SOURCE_SHA,
            "status":"STARTED","paid_jobs":0,"source_immutable":True,"future_review_role":"SELF_REVIEW",
            "UV_texture_rig_runtime":"UNVERIFIED_NOT_PERFORMED","renders":[]}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(source),merge_vertices=False,import_shading="NORMALS")
        meshes=[obj for obj in bpy.context.scene.objects if obj.type=="MESH"]
        if len(meshes)!=1:raise RuntimeError("Pinned Hero03 must import as one mesh")
        obj=meshes[0]
        bm=bmesh.new();bm.from_mesh(obj.data)
        report["before"]=topology(bm)
        if (report["before"]["vertices"],report["before"]["triangles"])!=(SOURCE_VERTICES,SOURCE_TRIANGLES):
            raise RuntimeError("Source mesh counts differ")
        plan=plan_regions(bm)
        report["plan"]={"rear_region_vertices":len(plan["rear"]),"rear_region_bounds":bounds(plan["rear"]),
                        "tail_vertices":len(plan["tail"]),"tail_bounds":bounds(plan["tail"]),
                        "eyes":plan["eyes"],"mouth":plan["mouth"],"protected_vertex_count":len(plan["protected"])}
        if args.mode=="apply":
            report["edits"]=repair_existing_geometry(bm,plan)
            zero=[f for f in bm.faces if f.calc_area()<1e-10]
            bmesh.ops.delete(bm,geom=zero,context="FACES_ONLY")
            report["deleted_zero_area_faces"]=len(zero)
            report["after_existing_mesh"]=topology(bm)
            bm.to_mesh(obj.data);obj.data.update();bm.free()
            generated=add_relief(plan,bpy.context.scene.collection);objects=[obj,*generated]
            total=0
            for item in objects:item.data.calc_loop_triangles();total+=len(item.data.loop_triangles)
            if total>SOURCE_LIMIT_TRIANGLES:raise RuntimeError(f"Bake-source candidate{total}tris exceeds{SOURCE_LIMIT_TRIANGLES}")
            report["candidate_source_triangles"]=total
            report["additional_nonmanifold_status"]="CLASSIFIED_UNRESOLVED; do not blanket-weld/fill"
            report["candidate_objects"]=[]
            for item in objects:
                report["candidate_objects"].append({"name":item.name,"vertices":len(item.data.vertices),"triangles":len(item.data.loop_triangles)})
            bpy.ops.object.select_all(action="DESELECT")
            for item in objects:item.select_set(True)
            bpy.context.view_layer.objects.active=obj
            blend=run/"hero03.form-candidate.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(blend))
            glb=run/"hero03.form-candidate.glb"
            bpy.ops.export_scene.gltf(filepath=str(glb),export_format="GLB",use_selection=True,export_materials="NONE",
                                      export_animations=False,export_cameras=False,export_lights=False)
            report["outputs"]={str(path):{"sha256":digest(path),"bytes":path.stat().st_size} for path in [blend,glb]}
            if args.render:
                report["renders"],report["review_scale_factor"]=capture(objects,run)
                report["review_full_bounding_height_m"]=1.85
            report["status"]="LOCAL_FORM_CANDIDATE_REVIEW_REQUIRED"
        else:
            bm.free();report["status"]="DIAGNOSED_NO_FORM_CHANGES"
        if digest(source)!=SOURCE_SHA:raise RuntimeError("Immutable source changed")
    except Exception as error:
        report["status"]="FAILED";report["error"]=str(error)
        (run/"receipt.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        raise
    (run/"receipt.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("H03_FORM_REPAIR",json.dumps({"status":report["status"],"run":str(run),"renders":len(report["renders"])}),flush=True)


if __name__=="__main__":main()
