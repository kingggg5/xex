"""Short CPU-only, fixed-camera Hero02 review pass. No GPU, no source writes."""
import sys,runpy,math,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
tag=args[args.index('--tag')+1] if '--tag' in args else 'pass1'
sys.argv=[sys.argv[0],'--','--tag',tag,'--set','initialize_only','--samples','16']
g=runpy.run_path(str(HERE/'h02_render_review.py'))
bpy=g['bpy'];C=g['C'];Vector=g['Vector'];Matrix=g['Matrix'];scn=g['scn'];cam=g['cam'];cam_d=g['cam_d'];arm=g['arm'];staff=g['staff'];show=g['show_only'];pose=g['set_action'];look=g['look'];render=g['render'];bg=g['bg'];witness=g['witness']
out=C.RENDERS/tag;out.mkdir(exist_ok=True)
rows=[]
def snap(name,w=900,h=1000):
    path=out/f'BLENDER_REVIEW_{name}.png'
    render(path,w,h)
    rows.append({'file':C.rel(path),'camera_position':list(cam.location),'camera_rotation':list(cam.rotation_euler),'resolution':[w,h],'samples':16,'engine':'Cycles CPU','threads':6,'frame':scn.frame_current})
show([0]);pose('base.idle',0);cam_d.type='ORTHO';cam_d.ortho_scale=3.2
for name,loc in [('front',(0.45,-8,1.2)),('side',(8,0,1.2)),('back',(0.45,8,1.2)),('threequarter',(5.2,-5.6,1.8))]:
    if name=='side':
        for w in witness:w.location.x-=1.0;w.location.y+=1.0
    look(cam,loc,(.35,0,1.2));snap(name)
    if name=='side':
        for w in witness:w.location.x+=1.0;w.location.y-=1.0
# Actual deformation witnesses, same side camera and framing at the phase of largest excursion.
for name,frame in [('base.walk',10),('base.run',6),('caster.attack_1',3),('mage.skill_bolt',14),('mage.skill_starfall',27),('base.dodge',6),('base.death',71),('caster.attack_2',3),('base.hit_light',5),('mage.skill_gale',6),('mage.skill_nova',6),('mage.skill_rift',18),('mage.skill_ward',9)]:
    pose(name,frame);look(cam,(5.2,-5.6,1.8),(.2,0,1.2));snap(f'deform_{name.replace(".","_")}_f{frame}',650,760)
pose('base.idle',0);cam_d.type='PERSP';cam_d.sensor_fit='VERTICAL';cam_d.angle_y=1.02
radius=13;beta=1.18;target=Vector((0,0,1.65));look(cam,target+Vector((0,-radius*math.sin(beta),radius*math.cos(beta))),target)
snap('player_day_13m',1920,1080)
day_lights={o.name:(o.data.energy,tuple(o.data.color)) for o in scn.objects if o.type=='LIGHT'}
for o in scn.objects:
    if o.type=='LIGHT':o.data.energy*=.28;o.data.color=(.46,.60,1.)
bg.inputs[0].default_value=(.06,.085,.16,1);bg.inputs[1].default_value=.45
snap('player_night_13m',1920,1080)
for o in scn.objects:
    if o.name in day_lights:o.data.energy,o.data.color=day_lights[o.name]
bg.inputs[0].default_value=(.55,.58,.62,1);bg.inputs[1].default_value=.9
# Two candidate weapons in the shared grip frame, free-standing above the floor.
show([],staff_on=False,witness_on=True)
owner=staff.copy();owner.data=staff.data.copy();scn.collection.objects.link(owner);owner.parent=None;owner.matrix_world=Matrix.Translation((-.65,0,.87));owner.hide_render=False
before=set(bpy.data.objects)
sc3=C.ROOT/'planning/evidence/hero-weapons-20261002/hero-02/r2/reimport-review/hero02_crystal_staff_lod0/hero02_crystal_staff_lod0.runtime.review.glb'
bpy.ops.import_scene.gltf(filepath=str(sc3),merge_vertices=False,import_shading='NORMALS')
imported=[o for o in bpy.data.objects if o not in before]
for o in imported:
    if o.parent is None:o.location+=Vector((.65,0,.87))
cam_d.type='ORTHO';cam_d.ortho_scale=3.0;look(cam,(0,-8,1.2),(0,0,1.2));snap('staff_owner_LEFT_sc3_r2_RIGHT',1200,1200)
cam_d.type='PERSP';cam_d.sensor_fit='VERTICAL';cam_d.angle_y=1.02;look(cam,target+Vector((0,-radius*math.sin(beta),radius*math.cos(beta))),target);snap('staff_compare_13m',1920,1080)
C.write_json(out/'receipt.json',{'label':'BLENDER REVIEW','tag':tag,'staff_comparison':'owner LEFT, SC3 r2 RIGHT; owner-relative shared grip frame','source':'work h02_anim + h02_staff; runtime render proof is separate Babylon captures','views':rows})
print('Hero02 review pass complete',tag,len(rows))
