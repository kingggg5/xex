"""Stone-only build/export chain. Run through run_blender.py, CPU six threads.

Reuses np_rock seeded high meshes; constructed parts stay closed and the grotto
has compound colliders rather than a convex hull that would seal its opening.
No shared state or live map writes. --only enables short, resumable slot runs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import shutil

import bpy
import bmesh
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import np_lib as L
import np_noise as NZ
import np_rock as R
from np_stone_specs import assets

OUT = L.OUT_MODELS / "stone"
EVID = L.EVIDENCE / "stone"
CACHE = L.CACHE / "stone-v2"


def backup_existing(path):
    path=Path(path)
    if path.exists():
        h=L.sha256_file(path);backup=EVID/"backup";backup.mkdir(parents=True,exist_ok=True)
        dest=backup/(path.name+"."+h[:12]+".orig")
        if not dest.exists():
            shutil.copy2(path,dest)
            with open(backup/"SHA256SUMS.txt","a",encoding="utf8") as out:out.write(f"{h}  {path}\n")


def hexlin(value):
    a = np.array([int(value[i:i+2],16)/255 for i in (0,2,4)])
    return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)


def shape_hash(ob):
    L.triangulate(ob)
    v = np.round(L.verts(ob.data),6).astype('<f4')
    f = np.array(L.faces_list(ob.data),dtype='<i4')
    return hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest()


def beveled_box(name,size,center,width=.025):
    ob=L.box_object(name,size,center)
    L.bevel(ob,width,segments=1)
    L.triangulate(ob)
    L.set_smooth(ob,False)
    return ob


def bevel_clipped_hull(ob,width,size):
    """Bevel a convex solid with bounded convex combinations, not fragile miters.

    Insets remain on their original face planes. Their convex hull creates the
    intervening edge and corner facets and cannot explode beyond source bounds.
    """
    v=L.verts(ob.data);points=[]
    for poly in ob.data.polygons:
        face=v[list(poly.vertices)];center=face.mean(0)
        radius=max(float(np.linalg.norm(face-center,axis=1).min()),1e-5)
        inset=min(.24,max(.025,width/radius))
        points.extend(center+(face-center)*(1-inset))
    new=L.convex_hull_object(ob.name+"_beveled",np.asarray(points))
    bm=bmesh.new();bm.from_mesh(new.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=1e-6)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(new.data);bm.free()
    p=L.verts(new.data);mn,mx=p.min(0),p.max(0)
    p=(p-(mn+mx)/2)*np.asarray(size)/(mx-mn)
    p[:,2]-=p[:,2].min();L.set_verts(new.data,p)
    L.delete([ob]);L.triangulate(new)
    return new


def cluster_lod2(obj,spec):
    """Stable closed far proxies retain every pebble/crystal component."""
    v=L.verts(obj.data);adj=[[] for _ in range(len(v))]
    for a,b in L.edges(obj.data):adj[int(a)].append(int(b));adj[int(b)].append(int(a))
    seen=set();parts=[]
    for start in range(len(v)):
        if start in seen:continue
        stack=[start];seen.add(start);ids=[]
        while stack:
            i=stack.pop();ids.append(i)
            for other in adj[i]:
                if other not in seen:seen.add(other);stack.append(other)
        points=v[ids];mn,mx=points.min(0),points.max(0);c=(mn+mx)/2;r=(mx-mn)/2
        if spec["recipe"]=="stone.crystals/2":
            tip=points[np.argmax(points[:,2])]
            proxy=[(mn[0],mn[1],mn[2]),(mx[0],mn[1],mn[2]),(c[0],mx[1],mn[2]),tip]
        else:
            proxy=[c+np.array([r[0],0,0]),c-np.array([r[0],0,0]),
                   c+np.array([0,r[1],0]),c-np.array([0,r[1],0]),
                   c+np.array([0,0,r[2]]),c-np.array([0,0,r[2]])]
        parts.append(L.convex_hull_object(f"{spec['id']}_farpart{len(parts)}",np.asarray(proxy)))
    out=L.join(parts,spec["id"]+"__lod2");L.triangulate(out)
    return out


def wedge(name,r0,r1,a0,a1,z0,depth,axis="Y"):
    # Closed annular segment, with a stable winding and explicit thickness.
    p=[]
    for y in (-depth/2,depth/2):
        for r,a in ((r0,a0),(r0,a1),(r1,a1),(r1,a0)):
            p.append([r*math.cos(a),y,z0+r*math.sin(a)])
    ob=L.mesh_from_arrays(name,np.array(p),[[0,1,2,3],[7,6,5,4],[0,4,5,1],[1,5,6,2],[2,6,7,3],[3,7,4,0]])
    # Hull guarantees face orientation and remains a closed convex wedge.
    fixed=L.convex_hull_object(name+"_closed",L.verts(ob.data)); L.delete([ob])
    L.bevel(fixed,.018,segments=1); L.triangulate(fixed)
    return fixed


def column_part(name,radius,height,z,vertices=10,phase=0):
    pts=[]
    for zi,rr in ((z,radius),(z+height,radius*.985)):
        pts += [(rr*math.cos(phase+i*math.tau/vertices),rr*math.sin(phase+i*math.tau/vertices),zi) for i in range(vertices)]
    o=L.convex_hull_object(name,np.array(pts)); L.bevel(o,.018,segments=1); L.triangulate(o)
    return o


def cliff_loft(spec,revision):
    """Authored stratified planes: no blob union, voxel pitting or rounded bands."""
    w,d,h=spec["params"]["size"];rng=np.random.default_rng(spec["seed"])
    corner="corner" in spec["id"];cap="cap" in spec["id"]
    if corner:
        outline=[(-.46,-.50),(-.08,-.50),(.46,-.48),(.50,-.42),(.50,.02),
                 (.42,.08),(.08,.08),(.08,.42),(.02,.50),(-.42,.50),(-.50,.42),(-.50,-.42)]
    else:
        outline=[(-.44,-.50),(-.13,-.49),(.13,-.47),(.44,-.50),(.50,-.39),(.49,.12),
                 (.44,.48),(.10,.50),(-.20,.47),(-.44,.50),(-.50,.39),(-.49,-.20)]
        if revision>=5:
            outline[:4]=[(-.44,-.46),(-.13,-.62),(.13,-.43),(.44,-.53)]
    base=np.asarray(outline)*[w,d];count=len(base)
    levels=[0,.09,.31,.34,.60,.64,.86,1] if not cap else [0,.16,.78,1]
    profiles=[1.00,.97,.92,1.01,.88,.97,.87,.88] if not cap else [.98,1,.95,.88]
    vertices=[]
    phase=rng.uniform(-math.pi,math.pi)
    for j,(z,scale) in enumerate(zip(levels,profiles)):
        # The front remains a calm broad plane with a few seeded fault offsets.
        drift=(0 if j in (0,len(levels)-1) else rng.uniform(-.024,.024)*w)
        for k,(x,y) in enumerate(base):
            zz=z*h
            local_scale=scale
            if revision>=5:
                local_scale=1+(scale-1)*(.45+.55*math.sin(k*1.17+phase)**2)
                if j>0:zz+=(.038 if j==len(levels)-1 else .085)*h*math.sin(k*.7+phase)
            elif j not in (0,len(levels)-1):zz+=.015*h*math.sin(k*.7+phase)
            vertices.append([x*local_scale+drift,y*local_scale,zz])
    faces=[list(reversed(range(count)))]
    for row in range(len(levels)-1):
        for k in range(count):
            nxt=(k+1)%count
            faces.append([row*count+k,row*count+nxt,(row+1)*count+nxt,(row+1)*count+k])
    faces.append([(len(levels)-1)*count+k for k in range(count)])
    coordinates=np.asarray(vertices)
    if revision>=5:
        mn,mx=coordinates.min(0),coordinates.max(0)
        coordinates=(coordinates-(mn+mx)/2)*np.array([w,d,h])/(mx-mn)
        coordinates[:,2]-=coordinates[:,2].min()
    ob=L.mesh_from_arrays(spec["id"]+"__high",coordinates,faces)
    bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(ob.data);bm.free();L.triangulate(ob);L.set_smooth(ob,False)
    return ob,{"construction":"stratified-loft/2" if revision>=5 else "stratified-loft/1",
               "open_l_plan":corner,"strata_levels":levels,"strata_warp_fraction":.085 if revision>=5 else .015}


def constructed(spec):
    p=spec["params"]; name=spec["id"]; recipe=spec["recipe"]
    rng=np.random.default_rng(spec["seed"]); parts=[]; meta={}
    if recipe in ("stone.arch/2","stone.tunnel/2"):
        width,height=p["opening"]; r=width/2; spring=height-r
        depth=p.get("depth",p.get("length")); thick=p["thickness"]
        for side in (-1,1):
            for j in range(3):
                if p.get("broken") and side==1 and j>0: continue
                parts.append(beveled_box(f"{name}_j{side}_{j}",(thick,depth,spring/3-.016),
                                        (side*(r+thick/2),0,(j+.5)*spring/3),.035))
        for j in range(12):
            if p.get("broken") and j<5: continue
            parts.append(wedge(f"{name}_voussoir{j}",r,r+thick,j*math.pi/12+.004,
                               (j+1)*math.pi/12-.004,spring,depth))
        meta={"opening_width_m":width,"opening_height_m":height,"length_m":depth,
              "collider_note":"Compound closed wedges; central passage must remain empty"}
    elif recipe=="stone.rim/2":
        r=p["radius"]; thick=p["thickness"]
        for j in range(9):
            a0=(j-4.5)*math.pi/18+.001; a1=(j-3.5)*math.pi/18-.001
            h=p["height"]*(.87+.13*rng.random())
            pts=[]
            for z in (0,h):
                for rr,a in ((r,a0),(r,a1),(r+thick,a1),(r+thick,a0)):
                    pts.append((rr*math.sin(a),rr*math.cos(a)-r,z))
            ob=L.convex_hull_object(f"{name}_{j}",np.array(pts)); L.bevel(ob,.04,segments=1)
            parts.append(ob)
        meta={"chamber_inner_radius_m":r,"arc_degrees":90,"open_sky":True}
    elif recipe=="stone.crystals/2":
        for j in range(p["count"]):
            ang=j*2.399963; rad=0 if j==0 else .33+.1*rng.random()
            cx,cy=rad*math.cos(ang),rad*math.sin(ang)
            h=p["height"]*(1 if j==0 else rng.uniform(.42,.82)); radius=.18 if j==0 else .10+.05*rng.random()
            pts=[]
            for z,r in ((0,radius*.85),(h*.77,radius)):
                pts += [(cx+r*math.cos(i*math.pi/3+ang)+z*.1*math.sin(ang),
                         cy+r*math.sin(i*math.pi/3+ang)+z*.1*math.cos(ang),z) for i in range(6)]
            pts.append((cx+h*.12*math.sin(ang),cy+h*.12*math.cos(ang),h))
            parts.append(L.convex_hull_object(f"{name}_{j}",np.array(pts)))
        meta={"glow":True,"emission_strength":1.1,"emission_recipe":"cyan-facet-mask/2"}
    elif recipe=="ruin.column/2":
        h=p["height"]
        parts.append(beveled_box(name+"_plinth",(1.0,1.0,.22),(0,0,.11),.04))
        parts.append(column_part(name+"_base",.47,.14,.225))
        parts.append(column_part(name+"_foot",.36,.15,.368))
        shaft_h=h-.85
        for j in range(3):
            part=column_part(f"{name}_shaft{j}",.29-.014*j,shaft_h/3-.008,.523+j*shaft_h/3,12,.04*j)
            if p["kind"]=="broken" and j==2:
                v=L.verts(part.data); top=v[:,2]>v[:,2].max()-.03
                v[top,2]-=.08+.15*rng.random(np.sum(top)); L.set_verts(part.data,v)
            parts.append(part)
        if p["kind"]!="broken":
            parts.append(column_part(name+"_neck",.37,.12,h-.32))
            parts.append(beveled_box(name+"_capital",(.9,.9,.19),(0,0,h-.095),.035))
        if p["kind"]=="toppled":
            a=math.radians(88)
            rot=np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
            for part in parts:L.set_verts(part.data,L.verts(part.data)@rot.T)
    elif recipe=="ruin.steps/2":
        n=p["steps"]; tread=p["tread"]; rise=p["rise"]
        for j in range(n):
            # Individually supported stair blocks with no buried coplanar faces.
            parts.append(beveled_box(f"{name}_{j}",(p["width"],tread-.008,(j+1)*rise),
                                     (0,(j-(n-1)/2)*tread,(j+1)*rise/2),.021))
        meta={"step_rise_m":rise,"step_tread_m":tread,"walk_surface":"candidate stairs; server support required"}
    elif recipe=="ruin.slab/2":
        w,d,h=p["size"]; c=p["chip"]
        polygon=[(-w/2+c,-d/2),(w/2-.05,-d/2),(w/2,-d/2+.09),(w/2,d/2-c),
                 (w/2-c,d/2),(-w/2+.06,d/2),(-w/2,d/2-.08),(-w/2,-d/2+c)]
        pts=[(x,y,z) for z in (0,h) for x,y in polygon]
        part=L.convex_hull_object(name,np.array(pts));L.bevel(part,.022,segments=1);parts.append(part)
    else:raise ValueError(recipe)
    # Base-centre origin is explicit, with no origin transform in the export.
    verts=np.concatenate([L.verts(o.data) for o in parts]);mn,mx=verts.min(0),verts.max(0)
    shift=np.array([(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,mn[2]])
    for o in parts:L.set_verts(o.data,L.verts(o.data)-shift)
    if recipe=="stone.rim/2":
        meta["chamber_center_local_gltf"]=[0.0,0.0,float(p["radius"]+shift[1])]
        meta["placement_note"]="Rotate around chamber_center_local_gltf to assemble the open-sky ring"
    hulls=[]
    for o in parts:
        hull=L.collider_hull(o,o.name+"_hull",max_tris=32)
        hulls.append(hull)
    return L.join(parts,name+"__high"),hulls,meta


def paint_and_uv(ob,spec,revision):
    me=ob.data;v=L.verts(me);n=L.vnormals(me);e=L.edges(me)
    uv=me.uv_layers.new(name="UVMap") if not me.uv_layers else me.uv_layers[0]
    coords=np.zeros((len(me.loops),2),dtype=np.float32)
    # Dominant-axis projection: uniform metre density, with no giant atlas islands.
    for face in me.polygons:
        axis=int(np.argmax(np.abs(face.normal)))
        axes=(1,2) if axis==0 else (0,2) if axis==1 else (0,1)
        for li in face.loop_indices:
            q=v[me.loops[li].vertex_index]
            coords[li]=q[list(axes)]/2.5
    uv.data.foreach_set("uv",coords.ravel())
    up=NZ.smoothstep(.60,.88,n[:,2]);h=np.clip(v[:,2]/max(v[:,2].max(),.01),0,1)
    curv=L.vertex_curvature(v,e,n,smooth_iters=3)
    cavity=np.clip(-curv*.035,0,1)
    broad=.5+.5*NZ.fbm3(v/.85,spec["seed"]+1,2)
    moss=up*NZ.smoothstep(.30,.62,broad)*spec["paint"]["moss"]*(.45+.55*cavity)
    if revision>=2:
        moss=np.clip(up*NZ.smoothstep(.18,.48,broad)*spec["paint"]["moss"]*(.72+.28*cavity)*1.55,0,.92)
    light=(.94+.06*h) if revision>=2 else (.72+.20*up+.08*h)
    edge=np.clip(curv*.018,0,.13)
    value=np.clip(light+edge-.18*cavity,.45,1.06)
    rgb=np.repeat(value[:,None],3,axis=1)
    rgb*=np.array([.98,.99,1.0]) if revision>=2 else np.array([1.0,.99,.96])
    moss_color=np.array([.45,.69,.19])
    rgb=rgb*(1-moss[:,None])+moss_color*moss[:,None]
    if spec["recipe"]=="stone.crystals/2":rgb*=np.array([.24,.80,.85])
    attr=L.set_corner_color_byte(ob,"Col",np.clip(rgb,0,1))
    if revision>=3 and spec["paint"]["moss"]>0:
        # True face-up mask keeps ledges green even when their corner vertex
        # normals are averaged with vertical walls. Side faces stay stone.
        colors=np.empty((len(me.loops),4),dtype=np.float32)
        attr.data.foreach_get("color",colors.ravel())
        for face in me.polygons:
            face_up=float(NZ.smoothstep(.60,.88,np.array([face.normal.z]))[0])
            for li in face.loop_indices:
                vi=me.loops[li].vertex_index
                coverage=face_up*float(NZ.smoothstep(.18,.48,np.array([broad[vi]]))[0])*spec["paint"]["moss"]
                coverage=min(.84,coverage*1.45)
                neutral=np.array([.98,.99,1.0])*value[vi]
                colors[li,:3]=neutral*(1-coverage)+np.array([.32,.60,.095])*coverage
        attr.data.foreach_set("color",np.clip(colors,0,1).ravel())


def material(atlas,revision,crystal=False):
    tex=OUT/"textures-source"
    mat=L.pbr_material(atlas+("_crystal" if crystal else "")+"_mat",tex/f"{atlas}_albedo.png",
                       tex/f"{atlas}_normal.png",tex/f"{atlas}_orm.png",vertex_color="Col",
                       normal_strength=.38 if revision<2 else .10)
    if crystal:
        nt=mat.node_tree;bs=nt.nodes.get("Principled BSDF")
        tn=nt.nodes.new("ShaderNodeTexImage");tn.image=L.load_image(tex/"sm_stone_emissive.png","sRGB")
        nt.links.new(tn.outputs["Color"],bs.inputs["Emission Color"])
        bs.inputs["Emission Strength"].default_value=1.1
        bs.inputs["Roughness"].default_value=.34
    return mat


def _build_one(spec,args):
    t=time.monotonic();L.reset();L.setup_cycles(samples=16,threads=6)
    hulls=[];meta={}
    if args.revision>=4 and spec["group"]=="cliffs":
        high,meta=cliff_loft(spec,args.revision)
        spec={**spec,"recipe":"stone.cliff-loft/2" if args.revision>=5 else "stone.cliff-loft/1"}
        resolved={**spec["params"],**meta};info={}
    elif spec["recipe"].startswith("rock."):
        build_spec=dict(spec)
        if args.revision>=2 and spec["group"]=="cliffs":
            build_spec["params"]={**spec["params"],"front_flat":.40,"lump_amp":.01,"smooth_coarse":1}
        if args.revision>=3:
            if spec["recipe"]=="rock.boulder/1":
                build_spec["params"]={**spec["params"],"planar_only":True}
            elif spec["group"]=="cliffs":
                build_spec["params"].update(strata=.010,strata_spacing=.80,strata_warp=.35,
                                            chips=7,crack=.10,detail_amp=0,pit_amp=0,lump_amp=.006)
        high,info,resolved=R.build_high(build_spec)
        if resolved.get("planar_only"):
            width=max(.005,min(.035,max(resolved["size"])*.012))
            high=bevel_clipped_hull(high,width,resolved["size"])
            resolved["bevel_width_m"]=width
            resolved["bevel_method"]="convex-face-insets/1"
        # Ground contact is the actual lowest vertex, not an embedded negative skirt.
        v=L.verts(high.data);v[:,2]-=v[:,2].min();L.set_verts(high.data,v)
    else:
        high,hulls,meta=constructed(spec);resolved=dict(spec["params"]);info={}
    target=int(spec["lod0_tris"]*.98)
    lod0=L.decimate_to(high,target,name=spec["id"]+"__lod0",tol=.005)
    if L.tri_count(lod0)>spec["lod0_tris"]:raise ValueError("LOD0 budget breach")
    L.delete([high]);L.set_smooth(lod0,not spec["recipe"].startswith(("stone.","ruin.")) and not resolved.get("planar_only"))
    if not hulls:hulls=[L.collider_hull(lod0,spec["id"]+"__collider",max_tris=48)]
    col=L.join(hulls,spec["id"]+"__collider");L.triangulate(col)
    if args.revision>=2 and spec["recipe"].startswith("rock."):L.weighted_normals(lod0)
    lods=[lod0]
    for level,ratio in ((1,.5),(2,.2)):
        if level==2 and spec["recipe"] in ("rock.pebbles/1","stone.crystals/2"):
            lods.append(cluster_lod2(lod0,spec));resolved["lod2_method"]="closed-per-component-proxies/1"
        else:
            lods.append(L.decimate_to(lod0,max(12,int(L.tri_count(lod0)*ratio)),name=spec["id"]+f"__lod{level}",tol=.02))
    for ob in lods+[col]:
        vertices=L.verts(ob.data)
        vertices[:,2]-=vertices[:,2].min()
        L.set_verts(ob.data,vertices)
    mat=material(spec["atlas"],args.revision,spec["recipe"]=="stone.crystals/2")
    reports={};source=[]
    for i,ob in enumerate(lods):
        paint_and_uv(ob,spec,args.revision);ob.data.materials.clear();ob.data.materials.append(mat)
        if meta.get("glow"):ob["glow"]=True
        report=L.mesh_report(ob);report["geometry_sha256"]=shape_hash(ob)
        report["uv_measured_px_per_m"]=round(L.texel_density(ob,1024),2)
        if report["non_manifold_edges"] or report["zero_area_faces"]:raise ValueError(f"Bad mesh {spec['id']}: {report}")
        dimensions=np.asarray(report["bounds_max"])-np.asarray(report["bounds_min"])
        expected=spec["params"].get("size")
        if not np.isfinite(dimensions).all() or dimensions.max()>100:
            raise ValueError(f"Invalid metre bounds {spec['id']}: {dimensions}")
        if expected and len(expected)==3 and np.any(dimensions>np.asarray(expected)*1.08+.01):
            raise ValueError(f"Recipe dimension overflow {spec['id']}: {dimensions} > {expected}")
        if abs(report["bounds_min"][2])>1e-4:raise ValueError(f"Base pivot not on ground: {spec['id']}")
        reports[f"lod{i}"]=report
        dest=OUT/"source"/f"{spec['id']}_lod{i}.glb"
        if not args.no_export:
            backup_existing(dest);backup_existing(dest.with_suffix(".receipt.json"))
            receipt=L.export_lod(ob,dest,profile="prop",budget_class=spec["budget_class"] if i==0 or spec["budget_class"]=="building_module" else "prop_lod1",
                                 texture_dir=OUT/"source"/"textures",vertex_color="MATERIAL",
                                 notes=f"candidate revision {args.revision}; recipe {spec['recipe']} seed {spec['seed']}; original procedural")
            if receipt.get("status")!="PASS":raise ValueError(f"Export validation failed {dest}: {receipt.get('status')}")
            source.append(str(dest.relative_to(L.REPO)))
    # Compound geometry and per-component hull footprints support opening-aware integration.
    reports["collider"]=L.mesh_report(col)
    collision={"schema":"xexoria.prop-collider/1","class":spec["collider"]["class"],"units":"metres","pivot":[0,0,0],
               "coordinate_space":"glTF +Y up; asset front +Z","bounds_blender":reports["lod0"],
               "compound":spec["recipe"].startswith(("stone.arch","stone.tunnel","stone.rim")),
               "glb":f"{spec['id']}_collider.glb",**meta}
    dest=OUT/"source"/f"{spec['id']}_collider.glb"
    if not args.no_export:
        backup_existing(dest);backup_existing(dest.with_suffix(".receipt.json"))
        L.export_lod(col,dest,profile="prop",budget_class="prop",materials="NONE",vertex_color="NONE",
                     texture_dir=OUT/"source"/"textures",notes="candidate collider; compound where opening present")
        source.append(str(dest.relative_to(L.REPO)))
    backup_existing(OUT/"colliders"/f"{spec['id']}.json")
    L.write_json(OUT/"colliders"/f"{spec['id']}.json",collision)
    for o in lods[1:]+[col]:o.hide_render=True;o.hide_set(True)
    backup_existing(CACHE/f"{spec['id']}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(CACHE/f"{spec['id']}.blend"),compress=True)
    rec={**spec,"params_resolved":resolved,"revision":args.revision,"metadata":meta,"mesh":reports,"source_files":source,
         "toolchain":{"blender":bpy.app.version_string,"shared_lib":L.LIB_VERSION,
                      "source_sha256":{p:L.sha256_file(HERE/p) for p in ("np_stone_build.py","np_stone_specs.py","np_rock.py","np_lib.py","np_stone_texture.py")}},
         "textures":{"atlas":spec["atlas"],"repeat_m":2.5,"source_px_per_m":409.6,"normal_convention":"OpenGL +Y","orm":"R=AO,G=roughness,B=metal"},
         "seconds":round(time.monotonic()-t,2),"status":"SOURCE_VALIDATED" if not args.no_export else "MESH_ONLY"}
    backup_existing(EVID/"receipts"/f"{spec['id']}.json")
    L.write_json(EVID/"receipts"/f"{spec['id']}.json",rec)
    L.log(f"STONE {spec['id']} lods {[reports[f'lod{i}']['triangles'] for i in range(3)]} {rec['seconds']}s")
    return rec


def build_one(spec,args):
    path=EVID/"receipts"/f"{spec['id']}.json"
    backup_existing(path)
    L.write_json(path,{**spec,"revision":args.revision,"status":"BUILDING"})
    try:
        return _build_one(spec,args)
    except Exception as exc:
        L.write_json(path,{**spec,"revision":args.revision,"status":"FAILED",
                           "error":str(exc),"note":"Partial source files must not be postprocessed; prior verified receipt/files are in backup"})
        raise


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--only",default="");ap.add_argument("--group",default="")
    ap.add_argument("--revision",type=int,default=1);ap.add_argument("--no-export",action="store_true")
    args=ap.parse_args(L.args_after_dashdash())
    for d in (OUT/"source",OUT/"colliders",EVID/"receipts",CACHE):d.mkdir(parents=True,exist_ok=True)
    only=set(filter(None,args.only.split(",")));groups=set(filter(None,args.group.split(",")))
    selected=[s for s in assets() if (not only or s["id"] in only) and (not groups or s["group"] in groups)]
    if not selected:raise ValueError("No assets selected")
    for s in selected:build_one(s,args)
    L.log(f"STONE BUILD OK: {len(selected)} assets")


if __name__=="__main__":main()
