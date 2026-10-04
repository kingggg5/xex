"""Original reference-led city kit. Blender Z-up/metres, south entrance at Y=0.

Run from repo root with Blender --background --factory-startup --python this.py.
No external downloads, paid services, or embedded reference pixels.
"""
import bpy
import math
import random
import json
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/models/reference-city/r1'
RUNTIME = OUT / 'city-source.glb'
OUT.mkdir(parents=True, exist_ok=True)
RUNTIME.parent.mkdir(parents=True, exist_ok=True)
random.seed(927)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'CYCLES'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.resolution_x = 1400
scene.render.resolution_y = 1100
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = 'AgX'
scene.world.color = (0.32, 0.38, 0.48)

def material(name, color, metallic=0, emission=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = 0.76 if metallic == 0 else 0.32
    b.inputs['Metallic'].default_value = metallic
    if emission:
        b.inputs['Emission Color'].default_value = (*color, 1)
        b.inputs['Emission Strength'].default_value = emission
    return m

STONE = material('Ivory limestone', (0.64, 0.60, 0.48))
TRIM = material('Sunlit carved stone', (0.88, 0.80, 0.61))
JOINT = material('Recessed masonry', (0.26, 0.31, 0.31))
PLASTER = material('Warm plaster', (0.81, 0.71, 0.51))
WOOD = material('Walnut beams', (0.19, 0.085, 0.036))
ROOF = material('Cobalt glazed slate', (0.045, 0.13, 0.30))
ROOF2 = material('Slate highlights', (0.10, 0.24, 0.43))
GOLD = material('Antique brass', (0.72, 0.43, 0.10), 0.65)
BLUE = material('Royal blue cloth', (0.045, 0.18, 0.48))
RED = material('Terracotta cloth', (0.57, 0.12, 0.07))
GLASS = material('Amber windows', (1, 0.50, 0.12), emission=0.4)
WATER = material('Fountain blue', (0.06, 0.48, 0.64), 0.2)
CRYSTAL = material('Arcane azure', (0.03, 0.58, 1), 0.25, 1.2)
LEAF = material('Garden canopy', (0.13, 0.32, 0.075))
LEAF2 = material('Sunlit leaves', (0.28, 0.46, 0.10))
GRASS = material('Garden moss', (0.22, 0.31, 0.09))
FLOWER = material('Garden flowers', (0.70, 0.32, 0.48))
parts = []

def finish(o, name, mat, bevel=0):
    o.name = name
    o.data.materials.clear()
    o.data.materials.append(mat)
    if bevel:
        mod = o.modifiers.new('Carved edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)
    parts.append(o)
    return o

def mesh(name, verts, faces, mat):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    o = bpy.data.objects.new(name, data)
    scene.collection.objects.link(o)
    return finish(o, name, mat)

def box(name, loc, size, mat, bevel=0.035):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.dimensions = size  # X width, Y depth, Z height; always centered.
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o, name, mat, bevel)

def cone(name, loc, r1, r2, depth, mat, vertices=16):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=depth, location=loc)
    return finish(bpy.context.object, name, mat)

def beam(name, a, b, width, mat):
    a, b = Vector(a), Vector(b)
    o = box(name, (a+b)*0.5, (width, width, (b-a).length), mat, 0.012)
    o.rotation_euler = (b-a).to_track_quat('Z', 'Y').to_euler()
    return o

def ring(name, loc, radius, tube, mat, rotation=(0,0,0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=tube, major_segments=32, minor_segments=6, location=loc, rotation=rotation)
    return finish(bpy.context.object, name, mat)

def crystal(name, x, y, z, radius, height):
    verts=[(x,y,z-height*0.5),(x,y,z+height*0.5)]
    verts += [(x+radius*math.cos(i*math.tau/6), y+radius*math.sin(i*math.tau/6), z) for i in range(6)]
    faces=[]
    for i in range(6):
        j=2+(i+1)%6
        faces += [(0,j,2+i),(1,2+i,j)]
    return mesh(name,verts,faces,CRYSTAL)

def arch(name, x, y, spring, inner, outer, depth, mat):
    # Wedge masonry: a real open arch; no opaque plane across its passage.
    for i in range(15):
        a=i*math.pi/15+0.009; b=(i+1)*math.pi/15-0.009
        verts=[]
        for yy in [y-depth/2,y+depth/2]:
            verts += [(x+r*math.cos(t), yy, spring+r*math.sin(t)) for r,t in [(inner,a),(outer,a),(outer,b),(inner,b)]]
        mesh(f'{name} stone {i}',verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat)

def banner(name, x,y,z, w=1.1,h=2.5):
    mesh(name,[(x-w/2,y,z),(x+w/2,y,z),(x+w/2,y,z-h),(x,y-0.12,z-h+0.4),(x-w/2,y,z-h)],[(0,1,2,3,4),(4,3,2,1,0)],BLUE)
    beam(name+' pole',(x-w/2-0.15,y,z+0.1),(x+w/2+0.15,y,z+0.1),0.09,GOLD)
    # An original diamond/sun emblem, distinct from reference logos.
    o=box(name+' emblem',(x,y-0.035,z-h*0.45),(w*0.33,0.055,w*0.33),GOLD,0)
    o.rotation_euler.y=math.pi/4
    for side in [-1,1]:
        beam(name+' gold hem',(x+side*(w/2-0.08),y-0.02,z-0.1),(x+side*(w/2-0.08),y-0.02,z-h+0.12),0.045,GOLD)

def roof(name,x,y,z,w,d,h):
    verts=[(x-w/2,y-d/2,z),(x+w/2,y-d/2,z),(x,y-d/2,z+h),(x-w/2,y+d/2,z),(x+w/2,y+d/2,z),(x,y+d/2,z+h)]
    mesh(name,verts,[(0,1,2),(3,5,4),(0,2,5,3),(1,4,5,2),(0,3,4,1)],ROOF)
    # Individual overlapping tiles stay in the file, never built on player CPU.
    for side in [-1,1]:
        for row in range(6):
            t=(row+0.5)/6
            xx=x+side*w/2*(1-t)
            zz=z+h*t+0.06
            for col in range(9):
                yy=y-d/2+(col+0.5)*d/9
                o=box(name+f' tile {side} {row} {col}',(xx,yy,zz),(math.hypot(w/2,h)/6+0.08,d/9-0.025,0.065),ROOF2 if (col+row)%4==0 else ROOF,0)
                o.rotation_euler.y=side*math.atan2(h,w/2)
    beam(name+' ridge',(x,y-d/2-0.12,z+h+0.12),(x,y+d/2+0.12,z+h+0.12),0.16,GOLD)
    for yy in [y-d/2-0.035,y+d/2+0.035]:
        for side in [-1,1]: beam(name+' verge',(x+side*w/2,yy,z),(x,yy,z+h),0.18,WOOD)

def house(name,x,y,w=5,d=5,h=5):
    box(name+' foundation',(x,y,0.25),(w+0.4,d+0.4,0.5),STONE)
    box(name+' plaster',(x,y,h/2+0.5),(w,d,h),PLASTER)
    for xx in [x-w/2-0.02,x,x+w/2+0.02]: box(name+' front timber',(xx,y-d/2-0.04,h/2+0.5),(0.20,0.18,h),WOOD)
    for zz in [0.75,2.8,h+0.45]: box(name+' timber course',(x,y-d/2-0.06,zz),(w+0.22,0.20,0.17),WOOD)
    for xx in [x-w/2,x+w/2]:
        box(name+' side beam',(xx,y,h/2+0.5),(0.20,d+0.1,0.20),WOOD)
        for yy in [y-d/2,y+d/2]: box(name+' corner',(xx,yy,h/2+0.5),(0.23,0.23,h),WOOD)
    box(name+' door frame',(x,y-d/2-0.13,1.65),(1.45,0.22,2.35),TRIM)
    box(name+' door',(x,y-d/2-0.26,1.60),(1.12,0.13,2.13),WOOD)
    for xx in [x-w*0.29,x+w*0.29]:
        for zz in [1.8,4.15]:
            box(name+' window casing',(xx,y-d/2-0.14,zz),(1.03,0.22,1.22),WOOD)
            box(name+' window glass',(xx,y-d/2-0.27,zz),(0.79,0.05,0.94),GLASS)
            box(name+' mullion',(xx,y-d/2-0.31,zz),(0.07,0.06,1.0),GOLD,0)
            box(name+' sill',(xx,y-d/2-0.26,zz-0.61),(1.20,0.40,0.12),TRIM)
    roof(name+' roof',x,y,h+0.55,w+0.8,d+0.8,2.65)
    box(name+' chimney',(x+w*0.30,y+d*0.24,h+2.4),(0.65,0.75,2.1),STONE)
    box(name+' chimney lip',(x+w*0.30,y+d*0.24,h+3.47),(0.85,0.95,0.18),TRIM)
    for side in [-1,1]: beam(name+' gable timber',(x+side*w/2,y-d/2-0.05,h+0.65),(x,y-d/2-0.05,h+3),0.18,WOOD)

def tower(name,x,y,h,r=2,spire=True):
    cone(name+' shaft',(x,y,h/2),r,r*0.93,h,STONE)
    for z in [0.3,h*0.42,h-0.4,h]:
        cone(name+' stone collar',(x,y,z),r+0.18,r+0.18,0.32,TRIM)
    for z in [h*0.3,h*0.63]:
        for a in [-math.pi/2,0,math.pi/2,math.pi]:
            xx=x+math.cos(a)*(r+0.015); yy=y+math.sin(a)*(r+0.015)
            o=box(name+' slit',(xx,yy,z),(0.32,0.08,1.10),JOINT,0.04); o.rotation_euler.z=a+math.pi/2
    for i in range(10):
        a=i*math.tau/10
        box(name+' battlement',(x+r*math.cos(a),y+r*math.sin(a),h+0.45),(0.6,0.6,0.9),TRIM)
    if spire:
        for i in range(6):
            t=i/6
            cone(name+' slate tier',(x,y,h+0.9+i*0.56),r*1.25*(1-t)+0.05,r*1.25*(1-(i+1)/6)+0.05,0.65,ROOF2 if i%3==0 else ROOF)
        cone(name+' finial',(x,y,h+4.6),0.16,0,1.25,GOLD,8)
    banner(name+' banner',x,y-r-0.13,h*0.75,1.0,2.8)

def lamp(x,y):
    cone('lamp plinth',(x,y,0.28),0.42,0.34,0.56,TRIM,8)
    cone('lamp post',(x,y,1.6),0.09,0.075,2.4,GOLD,8)
    crystal('lamp crystal',x,y,3.02,0.23,0.70)
    cone('lamp cap',(x,y,3.47),0.34,0,0.42,ROOF,8)
    ring('lamp rim',(x,y,2.69),0.24,0.045,GOLD)

def tree(x,y,size=1):
    cone('garden trunk',(x,y,1.3*size),0.18*size,0.10*size,2.6*size,WOOD,7)
    for dx,dy,dz,r in [(-0.7,0,2.8,1.2),(0.6,0.25,3.2,1.25),(0,-0.4,3.8,1.12)]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=r*size,location=(x+dx*size,y+dy*size,dz*size))
        finish(bpy.context.object,'garden canopy',LEAF if dx<0 else LEAF2)

# Foundation, two garden avenues and circular plaza. Entrance is at (0,0).
box('city foundation',(0,18,-0.65),(43,43,1.25),JOINT,0.2)
box('city paving',(0,18,0.015),(42.8,42.8,0.08),STONE,0)
for x in [-13.5,13.5]: box('garden verge',(x,18,0.12),(13.0,34,0.12),GRASS)
cone('plaza outer step',(0,17,0.20),8.0,8.0,0.30,TRIM,64)
cone('plaza paving',(0,17,0.37),7.7,7.7,0.08,STONE,64)
for rad in [4.7,6.3,7.5]:
    count=int(rad*8)
    for i in range(count):
        a=i*math.tau/count
        o=box('plaza radial paver',(rad*math.cos(a),17+rad*math.sin(a),0.435),(0.57,0.47,0.07),TRIM if i%3==0 else STONE,0.018)
        o.rotation_euler.z=a
for y in range(-10,36):
    for x in range(-3,4):
        if (x*x+(y-17)**2)<8**2: continue
        box('avenue cobble',(x*0.69+(y%2)*0.12,y*0.92,0.13),(0.65,0.86,0.16),TRIM if (x+y)%4==0 else STONE,0.025)

# Gate wing masonry and continuous arch, actual aperture 6 m wide.
for side in [-1,1]:
    box('gate wall',(side*12,0,3),(18,1.8,6),STONE)
    for x in range(5,21,2): box('gate crenel',(side*x,0,6.4),(0.85,2.0,0.8),TRIM)
    for row in range(6):
        for col in range(12):
            x=side*(3.8+col*1.44+(row%2)*0.3)
            if abs(x)>20.5: continue
            box('gate ashlar',(x,-0.95,0.6+row*0.9),(1.34,0.18,0.78),TRIM if (col+row)%5==0 else STONE,0.035)
    tower('entrance tower',side*5.15,0,8.0,1.75)
    box('gate jamb',(side*3.48,0,1.4),(0.90,2.3,2.8),TRIM)
arch('entrance archivolt',0,0,2.8,3.0,3.9,2.2,TRIM)
box('gate crown',(0,0,7.03),(7.4,2,0.5),STONE)
banner('entrance left cloth',-9,-1.12,5.1,1.4,3.6)
banner('entrance right cloth',9,-1.12,5.1,1.4,3.6)
for side in [-1,1]:
    box('city sidewall',(side*21,18,1.4),(0.9,37,2.8),STONE)
    for yy in range(1,38,3): box('sidewall cap',(side*21,yy,3.0),(1.1,1.25,0.45),TRIM)

# Foreground bridge is a mesh kit extension, flat at the gameplay plane.
box('bridge deck',(0,-6,-0.08),(6.3,10,0.45),STONE)
for side in [-1,1]:
    box('bridge parapet',(side*3.3,-6,0.75),(0.48,10,1.4),STONE)
    box('bridge coping',(side*3.3,-6,1.48),(0.64,10,0.18),TRIM)
    for yy in [-10.7,-6,-1.5]:
        box('bridge pier',(side*3.3,yy,0.8),(0.85,0.85,1.6),TRIM)
        lamp(side*3.3,yy)

# Central three-tier fountain with an original floating crystal.
for z,r,h in [(0.6,3.7,0.35),(1.0,3.35,0.5),(2.35,2.25,0.32),(3.6,1.3,0.28)]:
    cone('fountain basin',(0,17,z),r,r,h,TRIM,40)
    cone('fountain water',(0,17,z+h/2+0.025),r-0.22,r-0.22,0.04,WATER,40)
    ring('fountain carved lip',(0,17,z+h/2),r-0.07,0.12,TRIM)
cone('fountain stem',(0,17,2.3),0.78,0.48,3.2,STONE)
crystal('plaza crystal',0,17,5.5,0.72,3.1)
for tilt in [0.25,-0.40]: ring('crystal orbit',(0,17,5.4),1.2,0.035,GOLD,(tilt,tilt,0))
for i in range(8):
    a=i*math.tau/8
    x,y=2.02*math.cos(a),17+2.02*math.sin(a)
    beam('water cascade',(x,y,2.48),(x*1.13,17+(y-17)*1.13,1.26),0.08,WATER)

# Lived-in street: timber guild hall, shopfronts, forge and market stalls.
for name,x,y,w,d,h in [('guild hall',-12,25,7,6,6),('potion shop',12,24,5.5,5.5,5),('inn',-12,13,6,6,5.5),('blacksmith',12,13,6,6,5),('cottage',-14,5,5,4,4.5)]:
    house(name,x,y,w,d,h)
for x,y in [(8,5),(13,5),(17,19)]:
    for dx in [-1.5,1.5]:
        for dy in [-1,1]: box('market pole',(x+dx,y+dy,1.7),(0.10,0.10,3.4),WOOD)
    box('market counter',(x,y-0.75,1.0),(3.3,0.8,0.8),WOOD)
    for i in range(6):
        xx=x-1.5+(i+0.5)*0.5
        mesh('striped market canopy',[(xx-0.25,y-1.4,2.8),(xx+0.25,y-1.4,2.8),(xx+0.25,y,3.45),(xx-0.25,y,3.45),(xx-0.25,y+1.1,3.0),(xx+0.25,y+1.1,3.0)],[(0,1,2,3),(3,2,5,4),(3,2,1,0),(4,5,2,3)],RED if i%2 else TRIM)
    for dx in [-0.85,0,0.85]:
        box('market crate',(x+dx,y-0.8,1.5),(0.70,0.6,0.32),PLASTER)
        for j in range(3): cone('market goods',(x+dx+(j-1)*0.16,y-0.8,1.72),0.10,0.08,0.18,LEAF2,6)

# Raised castle and unequal skyline, leaving a central approach visible.
box('castle terrace',(0,33,0.7),(18,10,1.4),JOINT)
for i in range(6): box('castle stair',(0,26.5+i*0.40,0.12+i*0.12),(5.8,0.6,0.24+i*0.24),TRIM)
box('castle hall',(0,34,7),(11,8,11.5),STONE)
roof('castle nave',0,34,12.85,11.8,8.8,5.2)
for x,h in [(-7.5,13),(7.5,14),(-4,18),(4,20)]: tower('castle turret',x,34 if abs(x)>5 else 38,h,1.65 if abs(x)>5 else 1.4)
tower('castle high spire',0,38,24,1.7)
box('castle door recess',(0,29.93,4.1),(2.9,0.16,4.8),JOINT)
for side in [-1,1]: box('castle portal jamb',(side*1.75,29.8,3.8),(0.45,0.45,5.2),TRIM)
arch('castle portal',0,29.8,6.0,1.52,2.02,0.42,TRIM)
crystal('castle oculus',0,29.69,9.3,0.65,2.1)
for x in [-3.5,3.5]: banner('castle standard',x,29.7,10.8,1.5,5)

# Astrolabe tower and windmill: distinct landmarks from the concept sheet.
tower('observatory',16,33,15,2.0,False)
cone('observatory dome',(16,33,15.9),2.35,0.8,1.8,ROOF)
for tilt in [0,math.pi/2]: ring('observatory astrolabe',(16,33,18.1),1.8,0.085,GOLD,(math.pi/2,tilt,0.4))
crystal('observatory core',16,33,18.1,0.48,2.1)
cone('windmill stone tower',(-18,32,4),2.1,1.35,8,PLASTER)
cone('windmill roof',(-18,32,9),1.8,0,2.8,ROOF)
for i in range(4):
    a=math.pi/4+i*math.pi/2
    start=(-18,30.45,7.2)
    end=(-18+4.5*math.cos(a),30.45,7.2+4.5*math.sin(a))
    beam('windmill spar',start,end,0.15,WOOD)
    for j in range(4):
        r=1.5+j*0.65
        xx=-18+r*math.cos(a); zz=7.2+r*math.sin(a)
        o=box('windmill sail',(xx,30.39,zz),(0.55,0.08,0.9),TRIM,0)
        o.rotation_euler.y=math.pi/2-a

for x,y in [(-19,6),(-19,18),(-8,8),(-8,22),(19,8),(19,25),(8,28),(-10,36)]: tree(x,y,1.0 if y<20 else 1.2)
for side in [-1,1]:
    for y in [5,10,23,27]: lamp(side*4.9,y)
    for y in [8,22]:
        box('garden bed',(side*7.5,y,0.27),(2.0,3.0,0.45),TRIM)
        box('garden soil',(side*7.5,y,0.52),(1.8,2.8,0.12),GRASS)
        for i in range(12):
            xx=side*7.5+random.uniform(-0.7,0.7); yy=y+random.uniform(-1.1,1.1)
            cone('flower clump',(xx,yy,0.77),0.15,0.07,0.40,LEAF,6)
            cone('flower blossom',(xx,yy,0.99),0.19,0.03,0.10,FLOWER if i%3 else TRIM,6)

# Authored meshes grouped by material on export to keep static draw count bounded.
authored_parts = len(parts)
for o in parts:
    if o.type == 'MESH' and len(o.data.uv_layers) == 0:
        uv = o.data.uv_layers.new(name='UVMap')
        for loop in o.data.loops:
            uv.data[loop.index].uv = (0.5, 0.5)

# Save the editable master with the individual authored pieces and a useful
# review camera. The runtime GLB is joined by material after this save.
bpy.ops.object.light_add(type='AREA',location=(-22,-10,48))
bpy.context.object.name='Preview softbox'
bpy.context.object.data.energy=16000
bpy.context.object.data.shape='DISK'
bpy.context.object.data.size=30
bpy.ops.object.light_add(type='SUN',location=(0,0,30))
bpy.context.object.rotation_euler=(0.45,-0.5,-0.4)
bpy.context.object.data.energy=2.0
bpy.context.object.data.angle=0.18
bpy.ops.object.camera_add(location=(56,-67,65))
camera=bpy.context.object
camera.name='Reference city overview'
camera.rotation_euler=(Vector((0,17,5))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO'
camera.data.ortho_scale=78
scene.camera=camera
scene.render.filepath=str(OUT/'overview.png')
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'reference_city.blend'))
for mat in list(bpy.data.materials):
    group=[o for o in scene.objects if o.type=='MESH' and o.data.materials[0]==mat]
    if not group: continue
    bpy.ops.object.select_all(action='DESELECT')
    for o in group: o.select_set(True)
    bpy.context.view_layer.objects.active=group[0]
    bpy.ops.object.join()
    group[0].name='City / '+mat.name
    # Recalculate normals after joining all independently authored pieces.
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

city_meshes=[o for o in scene.objects if o.type=='MESH']
triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in city_meshes)
assert triangles < 100000, f'City exceeds authoring budget: {triangles}'
for o in city_meshes:
    assert all(math.isfinite(c) for v in o.data.vertices for c in v.co)

# The render previews the editable master from the saved presentation camera.
bpy.ops.object.select_all(action='DESELECT')
for o in city_meshes: o.select_set(True)
bpy.context.view_layer.objects.active=city_meshes[0]
bpy.ops.export_scene.gltf(filepath=str(RUNTIME),export_format='GLB',use_selection=True,export_yup=True,export_apply=True,export_materials='EXPORT',export_animations=False,export_cameras=False,export_lights=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt={'asset':'reference-city','revision':'r1','blender':bpy.app.version_string,'authoring':'Original scripted geometry; user supplied ChatGPT reference images; no image pixels embedded','reference':'docs/ui/ChatGPT Image Sep 27, 2026, 08_38_17 PM-1.png','units':'meters; Blender Z up; glTF Y up','authored_parts':authored_parts,'export_meshes':len(city_meshes),'triangles_before_export':triangles,'materials':len(city_meshes),'textures':0,'glb':str(RUNTIME.relative_to(ROOT)),'glb_bytes':RUNTIME.stat().st_size,'glb_sha256':sha(RUNTIME),'source_sha256':sha(Path(__file__)),'blend_sha256':sha(OUT/'reference_city.blend'),'scope':'Visual city kit; collisions, interiors, NPCs and city gameplay not implemented by this asset.'}
(OUT/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print('CITY_RECEIPT '+json.dumps(receipt))
bpy.ops.render.render(write_still=True)
