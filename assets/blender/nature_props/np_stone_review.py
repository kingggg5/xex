"""Bounded stone BLENDER REVIEW; source .blend loads, never game evidence."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import np_lib as L
import np_review as R
from np_stone_specs import assets
from np_stone_build import CACHE,EVID


def arrange(ids,mode,runtime=False):
    objs=[]
    if mode=="sample":
        poses=[(-2.5,-.3),(-.2,.1),(3.6,2.6)]
    else:
        poses=[];x=0.;row=0
        for aid in ids:
            rec=json.loads((EVID/"receipts"/f"{aid}.json").read_text(encoding="utf8"))
            b=rec["mesh"]["lod0"];w=b["bounds_max"][0]-b["bounds_min"][0]
            if x+w>19:x=0;row+=1
            poses.append((x+w/2,row*6.5));x+=w+.7
    for aid,xy in zip(ids,poses):
        if runtime:
            before=set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(CACHE/"decoded-review"/f"{aid}_lod0.review.glb"))
            bpy.context.view_layer.update()
            got=[o for o in bpy.data.objects if o not in before and o.type=="MESH"]
            for o in got:
                if o.parent:
                    matrix=o.matrix_world.copy();o.parent=None;o.matrix_world=matrix
                L.apply_transform(o)
            expected=json.loads((EVID/"receipts"/f"{aid}.json").read_text(encoding="utf8"))["mesh"]["lod0"]
            actual=np.concatenate([L.verts(o.data) for o in got])
            dev=max(float(np.max(np.abs(actual.min(0)-expected["bounds_min"]))),float(np.max(np.abs(actual.max(0)-expected["bounds_max"]))))
            tolerance=max(.0015,float(np.ptp(actual,axis=0).max())/4096)
            if dev>tolerance:raise ValueError(f"Decoded runtime transform drift {aid}: {dev}m > {tolerance}m")
            for o in got:o["review_bounds_deviation_m"]=dev
        else:
            got=R.append_objects(CACHE/f"{aid}.blend",[aid+"__lod0"])
        if len(got)!=1:raise ValueError(f"Missing review object {aid}")
        ob=got[0];ob.location=(xy[0],xy[1],0);ob.hide_render=False;ob.hide_set(False);objs.append(ob)
    return objs


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--revision",type=int,required=True)
    ap.add_argument("--group",default="sample");ap.add_argument("--views",default="game,close")
    ap.add_argument("--runtime",action="store_true")
    args=ap.parse_args(L.args_after_dashdash());out=EVID/(f"review-pass{args.revision}"+("-ktx2" if args.runtime else ""));out.mkdir(parents=True,exist_ok=True)
    specs=assets();ids=[s["id"] for s in specs if s["group"]==args.group]
    if args.group=="sample":ids=["sm_medium_03","sm_boulder_02","sm_cliff_wall_01"]
    if args.group=="crystals":ids=[s["id"] for s in specs if s["recipe"]=="stone.crystals/2"]
    L.reset();R.setup_render((1120,700),16,6);R.setup_world(.36)
    objs=arrange(ids,args.group,args.runtime)
    if args.group!="sample":bpy.context.view_layer.update()
    mn,mx=R.bounds(objs);cx,cy=(mn[0]+mx[0])/2,(mn[1]+mx[1])/2
    wx=cx+1.5 if args.group=="sample" and args.revision>=3 else cx-1.2
    if args.group=="crystals":wx=mx[0]+.8
    wit=R.witness((wx,mn[1]-1.0));ground=R.ground_plane("meadow",80,(cx,cy))
    sun=R.add_sun(azimuth_deg=225,elevation_deg=48,strength=3.0)
    results=[]
    for view in args.views.split(","):
        sc=bpy.context.scene;night=view=="night"
        sun.data.energy=(.8 if args.revision>=6 else .13) if night else 3.0
        sun.data.color=R.lin3((123,158,227) if night else R.SUN)
        sc.view_settings.exposure=.22 if night and args.revision>=6 else 0
        for n in sc.world.node_tree.nodes:
            if n.bl_idname=="ShaderNodeBackground":n.inputs["Strength"].default_value=(.32 if args.revision>=6 else .1) if night else .36
        if view in ("game","night"):
            target=(cx,cy,1.65);elev=math.pi/2-1.18;az=math.radians(-20)
            loc=(cx+13*math.cos(elev)*math.sin(az),cy-13*math.cos(elev)*math.cos(az),1.65+13*math.sin(elev))
            cam=R.camera(view,loc,target,fov_y=1.02)
        elif view=="close":
            target=(-.2,.1,.95) if args.group=="sample" else (cx,cy,max(1,float(mx[2]/2)))
            loc=(target[0]-3.9,target[1]-5.2,target[2]+2.7);cam=R.camera(view,loc,target,fov_y=.8)
        elif view=="lineup":
            width=max(mx[0]-mn[0]+3,(mx[1]-mn[1]+mx[2]+4)*1.45)
            target=(cx,cy,mx[2]*.3);loc=(cx-4,cy-30,mx[2]*.3+29)
            cam=R.camera(view,loc,target,ortho_scale=width)
        else:
            bpy.context.view_layer.update()
            om,ox=R.bounds(objs+[wit]);oc=(om+ox)/2
            width=max(ox[0]-om[0]+3,(ox[2]+2)*1.6)
            if view=="side":loc=(oc[0]+40,oc[1],ox[2]/2+.5);target=(oc[0],oc[1],ox[2]/2);width=max((ox[1]-om[1])*1.5,(ox[2]+2)*1.6)
            else:loc=(oc[0],oc[1]-40,ox[2]/2+7);target=(oc[0],oc[1],ox[2]/2)
            cam=R.camera(view,loc,target,ortho_scale=width)
        sc.camera=cam;path=out/f"BLENDER_REVIEW_{args.group}_{view}.png"
        elapsed=R.render(path)
        results.append({"file":str(path.relative_to(L.REPO)),"view":view,"camera":list(cam.location),"seconds":elapsed,
                        "witness_height_m":1.8,"witness_location":[float(wx),float(mn[1]-1.0),0],
                        "renderer":"Blender5.2.2 Cycles CPU","threads":6,"samples":16,"resolution":[1120,700],
                        "device":"workstation CPU (GTX1050 GPU unused)","game_tier":"N/A source candidate","night":night})
        results[-1].update({"sun_strength":sun.data.energy,"exposure":sc.view_settings.exposure,
                           "composition_fix":"updated evaluated transforms for complete kit framing" if args.group!="sample" else "frozen sample camera",
                           "night_review_note":"brighter moon/fill and +.22 exposure for inspection; not an engine night acceptance" if night and args.revision>=6 else None})
        bpy.data.objects.remove(cam,do_unlink=True);L.log(f"STONE REVIEW {view} {elapsed}s")
    L.write_json(out/f"{args.group}.json",{"label":"BLENDER REVIEW","revision":args.revision,"ids":ids,"views":results,
                                       "source":"decoded runtime meshopt/KTX2 GLBs" if args.runtime else "source blend",
                                       "runtime_bounds_max_deviation_m":max(float(o.get("review_bounds_deviation_m",0)) for o in objs) if args.runtime else None})


if __name__=="__main__":main()
