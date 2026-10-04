"""Fixed-camera BLENDER REVIEW scenes; not gameplay or renderer acceptance."""
from __future__ import annotations
import argparse
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import np_lib as L
import np_review as R
from np_craft_build import CACHE,EVID

LAYOUT={
 'smoke':[('sm_croft_hut',(0,2,0),0),('sm_bridge_deck',(-5,-1,0),0),('sm_market_stall_a',(4,-1,0),0)],
 'flora':[('sm_lilypad_01',(-1.1,-.8,.015),0),('sm_lilypad_02',(-.5,-.7,.015),0),('sm_lilypad_03',(.2,-.8,.015),0),('sm_lilypad_04',(.9,-.6,.015),0),
          ('sm_lotus_open',(-.7,-.1,.015),0),('sm_lotus_half',(.1,.15,.015),0),('sm_lotus_bud',(.8,.15,.015),0),
          ('sm_reeds_01',(-1.3,1.2,0),0),('sm_reeds_02',(0,1.5,0),0),('sm_reeds_03',(1.2,1.4,0),0)],
 'croft':[('sm_croft_hut',(0,2.8,0),0),('sm_croft_well',(-3,-1,0),0),('sm_croft_wall_straight',(3,0,0),.3),
          ('sm_croft_wall_corner',(4,1,0),0),('sm_croft_wall_gate',(4,3,0),math.pi/2),('sm_croft_skep_1',(2.2,-1.3,0),0),
          ('sm_croft_skep_2',(2.7,-.55,0),0),('sm_croft_campfire',(-.3,-2.4,0),0),('sm_croft_fence',(-3.9,1,0),math.pi/2),
          ('sm_croft_firewood',(-2,0,0),0),('sm_croft_trough',(3.8,-2,0),.4)],
 'pier':[('sm_pier_straight',(0,-2,0),0),('sm_pier_end',(0,2,0),0),('sm_pier_post',(1.2,3.7,0),0),('sm_pier_ladder',(-1.1,2,0),0),
         ('sm_pier_bollard',(.7,3,.12),0),('sm_cove_rowboat',(-2.3,1,0),-.15),('sm_cove_rod_rack',(1.9,-2.1,0),.5),
         ('sm_cove_driftwood_1',(-2.1,-3,0),.5),('sm_cove_driftwood_2',(2.4,1,0),.7),('sm_cove_driftwood_3',(3,2.7,0),-.2)],
 'threshold':[('sm_bridge_deck',(0,-1,0),0),('sm_threshold_gate',(0,2,0),0),('sm_brazier_pillar',(-2.3,.8,0),0),
              ('sm_brazier_tripod',(2.4,.7,0),0),('sm_brazier_cresset',(-2.0,1.29,1.45),0)],
 'market':[('sm_market_stall_a',(-2.7,1.1,0),.25),('sm_market_stall_b',(1.2,2.0,0),-.18),('sm_market_stall_c',(3.8,-1.7,0),-.5),
           ('sm_market_goods_apples',(-2.5,-.45,0),0),('sm_market_goods_carrots',(-1.75,-.35,0),.1),('sm_market_goods_bread',(.9,.6,0),0),
           ('sm_market_goods_jars',(1.75,.7,0),0),('sm_market_goods_fish',(2.6,-1.2,0),0)],
 'skiff':[('sm_cove_sailing_skiff',(0,0,-.20),.2)]}

def review(group,revision,views='game,close',res=(960,600),available=False,decoded=False):
    L.reset();R.setup_render(res,16,6);R.setup_world(.36);objects=[];used=[]
    for aid,pos,rot in LAYOUT[group]:
        family='flora' if aid.startswith(('sm_lilypad','sm_lotus','sm_reeds')) else 'craft'
        path=EVID/'decoded-review'/family/f'{aid}_lod0.review.glb' if decoded else CACHE/f'{aid}.blend'
        if not path.exists():
            if available:continue
            raise FileNotFoundError(path)
        if decoded:
            before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path))
            obs=[o for o in bpy.data.objects if o not in before and o.type=='MESH']
        else:obs=R.append_objects(path,[aid+'__lod0'])
        if len(obs)!=1:raise ValueError(aid)
        ob=obs[0]
        if decoded:
            # Quantized glTF stores dequantization offsets/scales on the mesh node.
            # Bake the imported world transform before applying the review placement.
            bpy.context.view_layer.update();world=ob.matrix_world.copy();ob.parent=None;ob.matrix_world=world;L.apply_transform(ob)
        ob.rotation_mode='XYZ';ob.location=pos;ob.rotation_euler.z=rot;ob.hide_render=False;ob.hide_set(False);objects.append(ob);used.append(aid)
    if not objects:raise ValueError('No review objects')
    ground='water' if group in ('flora','skiff') else 'sand' if group=='pier' else 'meadow'
    g=R.ground_plane(ground,80,(0,0));g.location.z=-.02
    witness=R.witness(((-2.8,1.7) if revision>=2 else (-2.0,-1.8)) if group=='flora' else (-2.0,-2.6))
    sun=R.add_sun(225,48,3.0);sun.data.angle=math.radians(1.1)
    out=EVID/f'review-pass{revision}';out.mkdir(parents=True,exist_ok=True);records=[]
    for view in views.split(','):
        night=view=='night';sun.data.energy=(.38 if revision>=3 else .16) if night else 3.0;sun.data.color=R.lin3((135,162,227) if night else R.SUN)
        for n in bpy.context.scene.world.node_tree.nodes:
            if n.bl_idname=='ShaderNodeBackground':n.inputs['Strength'].default_value=(.34 if revision>=3 else .14) if night else .36
        lamps=[]
        if night and group!='flora':
            for x in (-2.0,2.0):
                data=bpy.data.lights.new('review_only_lantern','AREA');data.energy=70 if revision>=3 else 90;data.color=R.lin3((255,184,112));data.shape='DISK';data.size=1.4
                lamp=bpy.data.objects.new('review_only_lantern',data);bpy.context.scene.collection.objects.link(lamp);lamp.location=(x,-1.5,2.8) if revision>=3 else (x,-.1,2.0);lamps.append(lamp)
        if view in ('game','night'):
            target=(0,.4,1.65);el=math.pi/2-1.18;az=math.radians(-15)
            loc=(13*math.cos(el)*math.sin(az),.4-13*math.cos(el)*math.cos(az),1.65+13*math.sin(el));cam=R.camera(view,loc,target,fov_y=1.02)
        elif view=='close':
            target=(0,0,.22) if group=='flora' else (0,1.0,1.2);loc=(-2.2,-3.0,2) if group=='flora' else (-4.5,-4.8,3.8)
            cam=R.camera(view,loc,target,fov_y=.88)
        else:
            target=(0,1,1.5);loc=(22,1,4) if view=='side' else (0,-20,10)
            cam=R.camera(view,loc,target,ortho_scale=7 if group=='flora' else 14)
        bpy.context.scene.camera=cam;path=out/f'BLENDER_REVIEW_{group}_{view}.png';seconds=R.render(path)
        records.append({'file':str(path.relative_to(L.REPO)),'view':view,'location':list(cam.location),'target':list(target),'seconds':seconds,
                        'label':'BLENDER REVIEW','witness_m':1.8,'renderer':'Blender5.2.2 Cycles CPU','threads':6,'samples':16,'resolution':list(res),
                        'device':'CPU on GTX1050 workstation; GPU unused','game_tier':'N/A source candidate','artificial_review_lights':bool(lamps)})
        L.delete([cam]+lamps);L.log('CRAFT REVIEW',group,view,seconds)
    L.write_json(out/f'{group}.json',{'label':'BLENDER REVIEW','revision':revision,'assets':used,'source_kind':'decoded compressed runtime' if decoded else 'source blend','views':records})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--group',default='flora');ap.add_argument('--revision',type=int,default=1);ap.add_argument('--views',default='game,close');ap.add_argument('--available',action='store_true');ap.add_argument('--decoded',action='store_true')
    a=ap.parse_args(L.args_after_dashdash())
    for g in a.group.split(','):review(g,a.revision,a.views,available=a.available,decoded=a.decoded)

if __name__=='__main__':main()
