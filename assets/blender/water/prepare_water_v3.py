"""Deterministic v3 water kit, analytical depth/flow/foam atlas and gameplay receipt.

CPU preparation only; the Blender companion exports and reimports the same arrays.
All world coordinates are canonical Babylon metres. No scene depth pass is used.
"""
from pathlib import Path
import hashlib, json, math
import numpy as np
from PIL import Image
import water_layout as W
import water_meshes as M

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "apps/client/src/assets/world/water-v3"
EVIDENCE = REPO / "planning/evidence/water-20261002"

def merge(a, b):
    offset = len(a.pos)
    for key in ("pos", "nrm", "uv0", "uv1", "col"):
        getattr(a, key).extend(getattr(b, key))
    a.tri.extend(tuple(i + offset for i in tri) for tri in b.tri)

def body_outline(body):
    if "outline_xz" in body:
        return np.array(body["outline_xz"], float)
    th = np.linspace(0, math.tau, 24, endpoint=False)
    return np.array(body["center_xz"]) + body["radius_m"] * np.stack([np.cos(th), np.sin(th)], 1)

def lake_fields(body, q):
    poly = body_outline(body)
    sdf = -W.polygon_sdf(q, poly)
    band = float(body.get("shallow_band_m", 2.2))
    deep = float(body["surface_y"] - body["bed_y"])
    depth = deep * W.smoothstep(0, band, sdf)
    flow = np.broadcast_to([0.025, 0.05] if body.get("still") else [0.04, 0.11], q.shape)
    foam = (.15 if body.get("still") else .52) * (1 - W.smoothstep(.03, .65, sdf))
    return depth, flow, foam, np.maximum(0, sdf)

def lake_mesh(body, rect, step=3.8):
    poly = body_outline(body)
    lo, hi = poly.min(0), poly.max(0)
    xs, zs = np.meshgrid(np.arange(lo[0]+step,hi[0],step), np.arange(lo[1]+step,hi[1],step))
    q = np.stack([xs.ravel(),zs.ravel()],1)
    q = q[W.point_in_polygon(q,poly)]
    pts = np.vstack([poly,q])
    # Constrained ear triangulation keeps concave pier notches exact. An
    # unconstrained Delaunay plus midpoint tests can bridge a narrow notch.
    sign=1 if W.polygon_area(poly)>0 else -1
    def cross(a,b,c):return float((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
    def inside(p,a,b,c,strict=False):
        values=[cross(a,b,p)*sign,cross(b,c,p)*sign,cross(c,a,p)*sign]
        return min(values)>(1e-8 if strict else -1e-8)
    remaining=list(range(len(poly)));triangles=[]
    while len(remaining)>3:
        found=False
        for i,b in enumerate(remaining):
            a,c=remaining[i-1],remaining[(i+1)%len(remaining)]
            if cross(pts[a],pts[b],pts[c])*sign<=1e-8:continue
            if any(inside(pts[k],pts[a],pts[b],pts[c]) for k in remaining if k not in (a,b,c)):continue
            triangles.append((a,b,c));remaining.pop(i);found=True;break
        if not found:raise ValueError(f"Cannot constrain water shoreline: {body['id']}")
    triangles.append(tuple(remaining))
    for i in range(len(poly),len(pts)):
        for j,(a,b,c) in enumerate(triangles):
            if inside(pts[i],pts[a],pts[b],pts[c],strict=True):
                triangles.pop(j);triangles.extend([(a,b,i),(b,c,i),(c,a,i)]);break
    mesh = M.MeshData(body["id"])
    x,y,w,h = rect
    for p in pts:
        uv1 = ((x+.5+(p[0]-lo[0])/(hi[0]-lo[0])*(w-1))/1024,
               (y+.5+(p[1]-lo[1])/(hi[1]-lo[1])*(h-1))/128)
        mesh.add_vertex((p[0],body["surface_y"],p[1]),(0,1,0),(p[0],p[1]),uv1)
    for a,b,c in triangles:
        mesh.add_tri(int(a),int(b),int(c),np.array([0,1,0]))
    return mesh

def bake_atlas(model, lakes):
    masks = np.zeros((128,1024,4),np.uint8); masks[...,3]=255
    flow = np.zeros_like(masks); flow[...,:2]=128
    islands={}
    at=model.atlas()
    for kind in ("stream","pool"):
        rec=at[kind]; x,y,w,h=rec["rect_px"]
        s0=rec.get("s_range",rec.get("v_range"))[0]; u0=rec["u_range"][0]
        S,U=np.meshgrid(s0+(np.arange(w)+.5)/W.PX_PER_M,u0+(np.arange(h)+.5)/W.PX_PER_M)
        q=model.sp.frame_point(U.ravel(),S.ravel())
        fields=model.sp.fields(q)
        depth=np.maximum(0,fields["depth"]).reshape(h,w)
        sdf=np.maximum(0,-fields["f"]).reshape(h,w)
        speed=model.sp.speed(np.maximum(0,S))*(1-.65*np.clip((2*U/model.sp.width(np.maximum(0,S)))**2,0,1))
        fx=np.zeros_like(speed); fy=speed
        foam=.38*(1-W.smoothstep(.03,.28,sdf)); turb=np.full_like(speed,.08)
        if kind=="pool":
            dist=np.linalg.norm(q-model.falls.landing[[0,2]],axis=1).reshape(h,w)
            pad=1-W.smoothstep(.5,1.5,dist)
            foam=np.maximum(foam,pad); turb=np.maximum(turb,pad)
            fy*=.35
        for st in model.stones:
            dist=np.linalg.norm(q-[st["x"],st["z"]],axis=1).reshape(h,w)-st["r"]
            if st["top_y"]>=model.sp.water_y-.2:
                local=1-W.smoothstep(0,.28,np.maximum(0,dist))
                foam=np.maximum(foam,local*.8)
                sdf=np.minimum(sdf,np.maximum(0,dist))
                stone_depth=max(0,model.sp.water_y-st["top_y"])
                depth=np.where(dist<0,np.minimum(depth,stone_depth),depth)
        bridge=model.sp.deck_sdf(q).reshape(h,w)<0
        sky=np.where(bridge,.42,.90)
        masks[y:y+h,x:x+w]=np.stack([np.clip(depth/1.2,0,1)*255,sky*255,turb*255,np.full((h,w),255)],-1).round().astype(np.uint8)
        flow[y:y+h,x:x+w]=np.stack([(fx/1.2*.5+.5)*255,(fy/1.2*.5+.5)*255,foam*255,np.clip(sdf,0,1)*255],-1).round().astype(np.uint8)
        islands[kind]=rec
    for body,rect in lakes:
        poly=body_outline(body); lo,hi=poly.min(0),poly.max(0)
        x,y,w,h=rect
        X,Z=np.meshgrid(np.linspace(lo[0],hi[0],w),np.linspace(lo[1],hi[1],h))
        q=np.stack([X.ravel(),Z.ravel()],1)
        dep,fl,fo,sd=lake_fields(body,q)
        masks[y:y+h,x:x+w]=np.stack([np.clip(dep/1.2,0,1)*255,np.full(len(q),.92*255),np.full(len(q),.06*255),np.full(len(q),0 if body.get('mud') else 255)],-1).round().astype(np.uint8).reshape(h,w,4)
        flow[y:y+h,x:x+w]=np.stack([(fl[:,0]/1.2*.5+.5)*255,(fl[:,1]/1.2*.5+.5)*255,fo*255,np.clip(sd,0,1)*255],-1).round().astype(np.uint8).reshape(h,w,4)
        islands[body["id"]]={"rect_px":rect,"bounds_xz":[*lo.tolist(),*hi.tolist()],"depth_method":"analytical shoreline distance; no dynamic depth"}
    # Island gutters clamp to their nearest edge. No cross-island bilinear bleed.
    for rec in islands.values():
        x,y,w,h=rec["rect_px"]
        for field in (masks,flow):
            field[y-2:y,x:x+w]=field[y:y+1,x:x+w];field[y+h:y+h+2,x:x+w]=field[y+h-1:y+h,x:x+w]
            field[y-2:y+h+2,x-2:x]=field[y-2:y+h+2,x:x+1];field[y-2:y+h+2,x+w:x+w+2]=field[y-2:y+h+2,x+w-1:x+w]
    return masks,flow,islands

def main():
    OUT.mkdir(parents=True,exist_ok=True);EVIDENCE.mkdir(parents=True,exist_ok=True)
    model=W.WaterModel()
    dressing=json.loads((REPO/'planning/levels/sunmeadow-v3-dressing.json').read_text(encoding='utf-8'))
    blueprint_water=dressing.get('blueprint',{}).get('water_bodies',[])
    model.layout['water']+=blueprint_water
    lake_bodies=[b for b in model.layout["water"] if b["id"] not in ("sunmeadow_stream","falls_pool","bluff_falls")]
    rects={"grotto_moon_pool":[12,82,64,40],"lotus_mere_pond":[84,82,256,40],"brightwater_cove_lake":[348,82,512,40]}
    rects.update({'blueprint_P1a':[868,82,32,40],'blueprint_P1b':[904,82,32,40],'blueprint_P1c':[940,82,32,40],'blueprint_P2':[976,82,40,40]})
    lakes=[(b,rects[b["id"]]) for b in lake_bodies]
    surface=M.build_surface(model)
    for body,rect in lakes:merge(surface,lake_mesh(body,rect))
    if surface.triangles>1300:raise ValueError(f"Surface over budget: {surface.triangles}")
    meshes={"surface":surface,**{f"falls{n}":M.build_falls(model,n) for n in (0,1,2)}}
    for n,limit in ((0,1400),(1,1050),(2,500)):
        if meshes[f"falls{n}"].triangles>limit:raise ValueError(f"Falls lod{n} over budget")
    masks,flow,islands=bake_atlas(model,lakes)
    for name,arr in (("water_masks",masks),("water_flow",flow)):
        (OUT/(name+".bin")).write_bytes(arr.tobytes())
        Image.fromarray(arr).save(EVIDENCE/(name+"-preview.png"))
        low=np.asarray(Image.fromarray(arr).resize((512,64),Image.Resampling.BOX))
        (OUT/(name+"_low.bin")).write_bytes(low.tobytes())
    geometry={k:{kk:v.tolist() for kk,v in m.arrays().items()} for k,m in meshes.items()}
    geo_bytes=json.dumps(geometry,separators=(",",":"),allow_nan=False).encode()
    (EVIDENCE/"water-geometry.json").write_bytes(geo_bytes)
    # Separate opaque host-floor contract: one bed plus one painted bank draw.
    # The terrain owner cuts existing tops, then admits these visual-only floors.
    bed=M.MeshData("water_channel_bed")
    bed.pos=list(surface.pos);bed.nrm=list(surface.nrm);bed.uv0=[(p[0]/2,p[2]/2) for p in surface.pos];bed.tri=list(surface.tri)
    for i,(x,y,z) in enumerate(bed.pos):
        q=np.array([[x,z]])
        depth=float(model.sp.fields(q)["depth"][0])
        for body,rect in lakes:
            u,v=surface.uv1[i];rx,ry,rw,rh=rect
            if rx/1024<=u<=(rx+rw)/1024 and ry/128<=v<=(ry+rh)/128:
                depth=float(lake_fields(body,q)[0][0]);break
        bed.pos[i]=(x,y-max(.015,depth),z)
    # The contact bake includes these authored stones. Admit their chunky
    # low topology into the bed batch, so there are no foam pads around ghosts
    # and the opaque channel stays at two draws.
    bed.col=[(1.,1.,1.,1.) for _ in bed.pos]
    stones=M.build_stones(model,max_subdiv=1)
    stones.col=[tuple(min(1.,max(0.,v)) for v in colour) for colour in stones.col]
    stones.uv0=[(p[0]/2,p[2]/2) for p in stones.pos]
    merge(bed,stones)
    bank=M.build_bank_strip(model,step=.9)
    for body,rect in lakes:
        poly=body_outline(body)
        centre=poly.mean(0);patch=M.MeshData(body["id"]+"_bank")
        edges=np.roll(poly,-1,axis=0)-poly;edges/=np.linalg.norm(edges,axis=1)[:,None]
        outward=np.stack([edges[:,1],-edges[:,0]],1)*(1 if W.polygon_area(poly)>0 else -1)
        outward+=np.roll(outward,1,axis=0);outward/=np.linalg.norm(outward,axis=1)[:,None]
        distances=(-.15,.6) if body.get('blueprint_id') else (-.15,.15,.6,1.2)
        for p,out in zip(poly,outward):
            for d in distances:
                q=p+out*d;y=body["surface_y"]*(1-W.smoothstep(0,1.2,max(0,d)))+.012
                patch.add_vertex((q[0],y,q[1]),(0,1,0),((d+.25)/1.85,float(np.linalg.norm(p-centre))/4))
        for i in range(len(poly)):
            for j in range(len(distances)-1):
                a=i*len(distances)+j;b=((i+1)%len(poly))*len(distances)+j
                for triangle in ((a,a+1,b+1),(a,b+1,b)):
                    midpoint=np.mean(np.array([patch.pos[k] for k in triangle])[:,[0,2]],axis=0)
                    sdf=float(W.polygon_sdf(midpoint[None],poly)[0])
                    if -.26<=sdf<=1.65:patch.add_tri(*triangle,np.array([0,1,0]))
        merge(bank,patch)
    if bed.triangles>6000 or bank.triangles>2000:raise ValueError("Opaque channel/banks over budget")
    for mesh in (bed,bank):
        positions=np.array(mesh.pos);normals=np.zeros_like(positions)
        for a,b,c in mesh.tri:
            n=-np.cross(positions[b]-positions[a],positions[c]-positions[a]);normals[a]+=n;normals[b]+=n;normals[c]+=n
        norms=np.linalg.norm(normals,axis=1);normals[norms<1e-9]=[0,1,0];normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-9)
        mesh.nrm=normals.tolist()
    support={k:{kk:v.tolist() for kk,v in m.arrays().items()} for k,m in {"bed":bed,"banks":bank}.items()}
    (EVIDENCE/"water-support-geometry.json").write_text(json.dumps(support,separators=(",",":")),encoding="utf-8")
    hazard=model.hazard()
    hazard["polygons"]=[p+[p[0]] for p in hazard["polygons"]]
    # Layout hazard polygons already subtract approved decks/pier, preserve them.
    hazard.update({"schema":"xexoria.water-hazard/1","layout_sha256":model.layout_sha,"support_y":0,
                   "server_verification":"UNVERIFIED root integration required","layout_hazards":[h for h in model.layout.get("hazards",[]) if h["id"]!="city_canal_water_0"],
                   "walkable_shallows":[],"grotto_pool":{"center_xz":[7.4,-41.7],"radius_m":1.3,"non_walkable_proposal":True,"server_verified":False}})
    for row in hazard["layout_hazards"]:
        poly=row.get("polygon_xz")
        if poly and poly[-1]!=poly[0]:row["polygon_xz"]=poly+[poly[0]]
    (EVIDENCE/"water-hazard.json").write_text(json.dumps(hazard,indent=2),encoding="utf-8")
    derived=model.derived();derived["lakes"]=lake_bodies
    (EVIDENCE/"water-derived.json").write_text(json.dumps(derived,indent=2),encoding="utf-8")
    files={p.name:{"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size} for p in sorted(OUT.glob("*")) if p.is_file() and (p.suffix in (".png",".bin") or p.name=="textures-report.json")}
    manifest={"schema":"xexoria.water-bodies.v1","region":"sunmeadow","recipe":"sunmeadow-water-v3/1","seed":model.seed,
              "layout_sha256":model.layout_sha,"axes":"canonical Babylon world x,y,z metres; exporter Blender=(x,-z,y); alignWorldAuthoredGlb",
              "bodies":[b["id"] for b in model.layout["water"]],"anchors":model.anchors(),"atlas":{"width":1024,"height":128,"islands":islands},
              "meshes":{k:{"name":m.name,"vertices":len(m.pos),"triangles":m.triangles,"attributes":list(m.arrays())} for k,m in meshes.items()},
              "geometry_sha256":hashlib.sha256(geo_bytes).hexdigest(),"files":files,"maps":"analytical depth/contact/flow; bridge sky mask is authored approximation, canopy raycast UNVERIFIED",
              "support":{"bed_triangles":bed.triangles,"bank_triangles":bank.triangles,"draws":2,"glb":"env_sunmeadow_water_banks_v3.glb","physical_support_y":0,"host_cut_required":True},
              "lake_atlas_density":"shared spare rows, coarser lakes preserve the 3.3 MiB original budget; shoreline analytical smooth width 0.65m",
              "provenance":"project-authored procedural, no third-party assets","glb":"env_sunmeadow_water_v3.glb"}
    manifest['blueprint']={'source_sha256':dressing.get('blueprint',{}).get('source_sha256'),'bodies':[b['id'] for b in blueprint_water],'original_surface_triangles':1203,'physics_admission':'UNVERIFIED'}
    if (OUT/manifest["glb"]).exists():
        manifest["glb_sha256"]=hashlib.sha256((OUT/manifest["glb"]).read_bytes()).hexdigest()
    for field,file in (("sha256","env_sunmeadow_water_banks_v3.glb"),("runtime_sha256","env_sunmeadow_water_banks_v3.runtime.glb")):
        if (OUT/file).exists():manifest["support"][field]=hashlib.sha256((OUT/file).read_bytes()).hexdigest()
    manifest["support"]["runtime_glb"]="env_sunmeadow_water_banks_v3.runtime.glb"
    (OUT/"water-manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({k:v["triangles"] for k,v in manifest["meshes"].items()}))

if __name__=="__main__":main()
