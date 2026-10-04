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
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
CITY_CENTER_Y = 39.0
PLAZA_Y = CITY_CENTER_Y - 5.0
OUT = ROOT / 'assets/models/reference-city/r2'
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
scene.cycles.samples = 16
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
ROOF_TERRA = material('Old terracotta', (0.48, 0.15, 0.07))
ROOF_TEAL = material('Oxidized teal slate', (0.025, 0.28, 0.27))
ROOF_COPPER = material('Copper roof', (0.20, 0.30, 0.20), 0.35)
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

def append_box(vertices, faces, center, size, rotation_y=0, rotation_z=0):
    """Append one centered box directly to a batched mesh without bpy.ops."""
    w,d,h=size
    hx,hy,hz=w*0.5,d*0.5,h*0.5
    local=[(-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
           (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz)]
    cy,sy=math.cos(rotation_y),math.sin(rotation_y)
    cz,sz=math.cos(rotation_z),math.sin(rotation_z)
    cx,cy0,cz0=center
    base=len(vertices)
    for x,y,z in local:
        x,y0,z1=x*cy+z*sy,y,-x*sy+z*cy
        vertices.append((cx+x*cz-y0*sz,cy0+x*sz+y0*cz,cz0+z1))
    faces.extend(tuple(base+i for i in face) for face in [
        (0,3,2,1),(4,5,6,7),(0,1,5,4),
        (1,2,6,5),(2,3,7,6),(3,0,4,7),
    ])

def batch_boxes(name, boxes):
    """Combine repeated box details by material to keep Blender authoring quick."""
    groups={}
    for center,size,mat,rotation_y,rotation_z in boxes:
        verts,faces=groups.setdefault(mat,([],[]))
        append_box(verts,faces,center,size,rotation_y,rotation_z)
    for mat,(verts,faces) in groups.items():
        mesh(f'{name} / {mat.name}',verts,faces,mat)

def box(name, loc, size, mat, bevel=0):
    # Direct mesh construction avoids thousands of context-sensitive Blender
    # operators while keeping the cube centered at its authored transform.
    w,d,h=size
    hx,hy,hz=w*0.5,d*0.5,h*0.5
    verts=[(-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
           (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),
           (2,3,7,6),(3,0,4,7)]
    data=bpy.data.meshes.new(name)
    data.from_pydata(verts,[],faces)
    data.update()
    o=bpy.data.objects.new(name,data)
    scene.collection.objects.link(o)
    o.location=loc
    return finish(o,name,mat,bevel)

def cone(name, loc, r1, r2, depth, mat, vertices=16):
    z0,z1=-depth*0.5,depth*0.5
    verts=[]
    for i in range(vertices):
        a=i*math.tau/vertices
        verts.append((r1*math.cos(a),r1*math.sin(a),z0))
    for i in range(vertices):
        a=i*math.tau/vertices
        verts.append((r2*math.cos(a),r2*math.sin(a),z1))
    faces=[]
    for i in range(vertices):
        j=(i+1)%vertices
        faces.append((i,j,vertices+j,vertices+i))
    faces.append(tuple(reversed(range(vertices))))
    faces.append(tuple(range(vertices,vertices*2)))
    data=bpy.data.meshes.new(name)
    data.from_pydata(verts,[],faces)
    data.update()
    o=bpy.data.objects.new(name,data)
    scene.collection.objects.link(o)
    o.location=loc
    return finish(o,name,mat)

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

def roof(name,x,y,z,w,d,h,base=ROOF,accent=ROOF2):
    verts=[(x-w/2,y-d/2,z),(x+w/2,y-d/2,z),(x,y-d/2,z+h),(x-w/2,y+d/2,z),(x+w/2,y+d/2,z),(x,y+d/2,z+h)]
    mesh(name,verts,[(0,1,2),(3,5,4),(0,2,5,3),(1,4,5,2),(0,3,4,1)],base)
    # Tile geometry is batched by material while staying editable as a roof mesh.
    tiles=[]
    for side in [-1,1]:
        for row in range(6):
            t=(row+0.5)/6
            xx=x+side*w/2*(1-t)
            zz=z+h*t+0.06
            for col in range(9):
                yy=y-d/2+(col+0.5)*d/9
                tiles.append(((xx,yy,zz),(math.hypot(w/2,h)/6+0.08,d/9-0.025,0.065),
                              accent if (col+row)%7==0 else base,side*math.atan2(h,w/2),0))
    batch_boxes(name+' shingle field',tiles)
    beam(name+' ridge',(x,y-d/2-0.12,z+h+0.12),(x,y+d/2+0.12,z+h+0.12),0.16,GOLD)
    for yy in [y-d/2-0.035,y+d/2+0.035]:
        for side in [-1,1]: beam(name+' verge',(x+side*w/2,yy,z),(x,yy,z+h),0.18,WOOD)

def house(name,x,y,w=5,d=5,h=5,roofmat=ROOF,wallmat=PLASTER,facing=0):
    first_part=len(parts)
    box(name+' foundation',(x,y,0.25),(w+0.4,d+0.4,0.5),STONE,0.10)
    box(name+' plaster',(x,y,h/2+0.5),(w,d,h),wallmat,0.07)
    for xx in [x-w/2-0.02,x,x+w/2+0.02]: box(name+' front timber',(xx,y-d/2-0.04,h/2+0.5),(0.20,0.18,h),WOOD)
    for zz in [0.75,2.8,h+0.45]: box(name+' timber course',(x,y-d/2-0.06,zz),(w+0.22,0.20,0.17),WOOD)
    for xx in [x-w/2,x+w/2]:
        box(name+' side beam',(xx,y,h/2+0.5),(0.20,d+0.1,0.20),WOOD)
        for yy in [y-d/2,y+d/2]: box(name+' corner',(xx,yy,h/2+0.5),(0.23,0.23,h),WOOD)
    box(name+' door frame',(x,y-d/2-0.13,1.65),(1.45,0.22,2.35),TRIM)
    box(name+' door',(x,y-d/2-0.26,1.60),(1.12,0.13,2.13),WOOD)
    for xx in [x-w*0.29,x+w*0.29]:
        for zz in [1.8,4.15]:
            box(name+' window casing',(xx,y-d/2-0.14,zz),(1.03,0.22,1.22),WOOD,0.045)
            box(name+' window glass',(xx,y-d/2-0.27,zz),(0.79,0.05,0.94),GLASS,0.02)
            box(name+' mullion',(xx,y-d/2-0.31,zz),(0.07,0.06,1.0),GOLD,0)
            box(name+' sill',(xx,y-d/2-0.26,zz-0.61),(1.20,0.40,0.12),TRIM)
    accent=ROOF2 if roofmat==ROOF else ROOF_COPPER if roofmat==ROOF_TERRA else ROOF_TERRA if roofmat==ROOF_COPPER else ROOF
    roof(name+' roof',x,y,h+0.55,w+0.8,d+0.8,2.65,roofmat,accent)
    box(name+' chimney',(x+w*0.30,y+d*0.24,h+2.4),(0.65,0.75,2.1),STONE)
    box(name+' chimney lip',(x+w*0.30,y+d*0.24,h+3.47),(0.85,0.95,0.18),TRIM)
    for side in [-1,1]: beam(name+' gable timber',(x+side*w/2,y-d/2-0.05,h+0.65),(x,y-d/2-0.05,h+3),0.18,WOOD)
    box(name+' shop sign',(x,y-d/2-0.27,h+0.15),(1.6,0.12,0.52),GOLD,0.035)
    box(name+' sign inset',(x,y-d/2-0.35,h+0.15),(1.18,0.07,0.26),ROOF,0.02)
    if facing:
        turn=Matrix.Translation(Vector((x,y,0))) @ Matrix.Rotation(facing,4,'Z') @ Matrix.Translation(Vector((-x,-y,0)))
        for obj in parts[first_part:]: obj.matrix_world=turn @ obj.matrix_world

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

def city_island(cx=0,cy=CITY_CENTER_Y,rx=42,ry=39,count=64):
    """Irregular green city plateau with a deep, broken limestone cliff edge."""
    outline=[]
    for i in range(count):
        a=i*math.tau/count
        wobble=1+0.027*math.sin(5*a+0.4)+0.018*math.sin(11*a-0.7)+0.009*math.cos(17*a)
        outline.append((cx+rx*wobble*math.cos(a),cy+ry*wobble*math.sin(a)))
    top=[(x,y,-0.04) for x,y in outline]
    top_verts=top+[(cx,cy,-0.04)]
    top_faces=[(count,i,(i+1)%count) for i in range(count)]
    mesh('irregular city green',top_verts,top_faces,GRASS)
    mid=[]; bottom=[]
    for i,(x,y) in enumerate(outline):
        a=i*math.tau/count
        mid.append((cx+(x-cx)*1.015,cy+(y-cy)*1.015,-2.3+0.32*math.sin(3*a)))
        bottom.append((cx+(x-cx)*0.94,cy+(y-cy)*0.94,-6.3+0.42*math.sin(4*a+0.2)))
    upper_verts=top+mid
    lower_verts=mid+bottom
    upper_faces=[]; lower_faces=[]
    for i in range(count):
        j=(i+1)%count
        upper_faces.append((i,j,count+j,count+i))
        lower_faces.append((count+i,count+j,2*count+j,2*count+i))
    mesh('upper stratified limestone cliff',upper_verts,upper_faces,STONE)
    mesh('lower dark bedrock',lower_verts,lower_faces,JOINT)
    for i in range(0,count,2):
        x,y=outline[i]
        a=i*math.tau/count
        size=random.uniform(1.1,2.5)
        rock=box('broken cliff block',(x,y,-3.0+random.uniform(-0.5,0.5)),(size,size*0.76,random.uniform(1.0,2.5)),STONE if i%4 else TRIM,0.12)
        rock.rotation_euler.z=a
    # One continuous oval moat avoids seams between rectangular water strips.
    water_outline=[(51*math.cos(i*math.tau/count),cy+48*math.sin(i*math.tau/count),-2.20) for i in range(count)]
    water_verts=[(cx,cy,-2.20)]+water_outline
    water_faces=[(0,1+i,1+(i+1)%count) for i in range(count)]
    mesh('continuous oval city moat',water_verts,water_faces,WATER)
    for side in [-1,1]:
        for y in [2,21,42,61]:
            fall=box('cliff waterfall',(side*42.2,y,-3.3),(0.55,1.25,3.0),WATER,0.03)
            fall.rotation_euler.z=random.uniform(-0.12,0.12)

city_island(cx=0,cy=CITY_CENTER_Y,rx=42,ry=39)
for x in [-29,29]: box('garden verge',(x,CITY_CENTER_Y,0.035),(16.0,72.0,0.06),GRASS,0)
cone('plaza outer step',(0,PLAZA_Y,0.20),8.0,8.0,0.30,TRIM,64)
cone('plaza paving',(0,PLAZA_Y,0.37),7.7,7.7,0.08,STONE,64)
pavers=[]
for rad in [4.7,6.3,7.5]:
    count=int(rad*8)
    for i in range(count):
        a=i*math.tau/count
        pavers.append(((rad*math.cos(a),PLAZA_Y+rad*math.sin(a),0.435),(0.57,0.47,0.07),TRIM if i%3==0 else STONE,0,a))
for radius in [11,22,33]:
    count=int(math.tau*radius/1.25)
    for i in range(count):
        a=i*math.tau/count
        pavers.append(((radius*math.cos(a),PLAZA_Y+radius*math.sin(a),0.14),(0.94,1.10,0.16),TRIM if i%7==0 else STONE,0,a+math.pi/2))
for y in range(-22,77):
    for x in range(-4,5):
        if (x*0.82)**2+(y-PLAZA_Y)**2<8**2: continue
        pavers.append(((x*0.82+(y%2)*0.10,y,0.13),(0.78,0.94,0.16),TRIM if (x+y)%5==0 else STONE,0,0))
batch_boxes('city paving network',pavers)

# Gate wing masonry and continuous arch, actual aperture 6 m wide.
gate_ashlar=[]
for side in [-1,1]:
    box('gate wall',(side*21,0,5.1),(34.2,2.1,10.2),STONE,0.10)
    for x in range(5,40,2): box('gate crenel',(side*x,0,10.65),(0.90,2.25,1.1),TRIM)
    for row in range(6):
        for col in range(22):
            x=side*(4.1+col*1.55+(row%2)*0.32)
            if abs(x)>39.0: continue
            gate_ashlar.append(((x,-0.95,0.6+row*0.9),(1.34,0.18,0.78),TRIM if (col+row)%5==0 else STONE,0,0))
    tower('entrance tower',side*5.15,0,12.0,2.25)
    box('gate jamb',(side*3.48,0,1.4),(0.90,2.3,2.8),TRIM)
batch_boxes('gate ashlar courses',gate_ashlar)
arch('entrance archivolt',0,0,2.8,3.0,3.9,2.2,TRIM)
box('gate crown',(0,0,7.03),(7.4,2,0.5),STONE)
banner('entrance left cloth',-9,-1.12,5.1,1.4,3.6)
banner('entrance right cloth',9,-1.12,5.1,1.4,3.6)
for side in [-1,1]:
    box('city sidewall',(side*40,CITY_CENTER_Y,2.0),(1.2,76,4.0),STONE,0.08)
    for yy in range(1,78,3): box('sidewall cap',(side*40,yy,4.25),(1.35,1.45,0.55),TRIM)
    for yy,h in [(1,10),(20,12),(39,10),(58,13),(76,11)]: tower('outer wall watchtower',side*39.2,yy,h,1.45)
box('rear curtain wall',(0,78,2.0),(80,1.2,4.0),STONE)
for xx in range(-38,39,3): box('rear crenel',(xx,78,4.35),(1.35,1.45,0.65),TRIM)

# Foreground bridge is a mesh kit extension, flat at the gameplay plane.
box('bridge deck',(0,-11,-0.08),(7.4,22,0.45),STONE)
for side in [-1,1]:
    box('bridge parapet',(side*3.8,-11,0.75),(0.55,22,1.4),STONE)
    box('bridge coping',(side*3.8,-11,1.48),(0.72,22,0.18),TRIM)
    for yy in [-19,-11,-3]:
        box('bridge pier',(side*3.3,yy,0.8),(0.85,0.85,1.6),TRIM)
        lamp(side*3.3,yy)

# Central three-tier fountain with an original floating crystal.
for z,r,h in [(0.6,3.7,0.35),(1.0,3.35,0.5),(2.35,2.25,0.32),(3.6,1.3,0.28)]:
    cone('fountain basin',(0,PLAZA_Y,z),r,r,h,TRIM,40)
    cone('fountain water',(0,PLAZA_Y,z+h/2+0.025),r-0.22,r-0.22,0.04,WATER,40)
    ring('fountain carved lip',(0,PLAZA_Y,z+h/2),r-0.07,0.12,TRIM)
cone('fountain stem',(0,PLAZA_Y,2.3),0.78,0.48,3.2,STONE)
crystal('plaza crystal',0,PLAZA_Y,5.5,0.72,3.1)
for tilt in [0.25,-0.40]: ring('crystal orbit',(0,PLAZA_Y,5.4),1.2,0.035,GOLD,(tilt,tilt,0))
for i in range(8):
    a=i*math.tau/8
    x,y=2.02*math.cos(a),PLAZA_Y+2.02*math.sin(a)
    beam('water cascade',(x,y,2.48),(x*1.13,PLAZA_Y+(y-PLAZA_Y)*1.13,1.26),0.08,WATER)

# Lived-in street: timber guild hall, shopfronts, forge and market stalls.
landmark_houses=[
    ('guild hall',-23,39,9,8,10,ROOF),
    ('potion shop',19,52,7,7,6,ROOF_TEAL),
    ('traveler inn',-23,20,7,7,6,ROOF_TERRA),
    ('blacksmith',23,20,7,7,6,ROOF_COPPER),
    ('chapel house',-12,44,7,7,8,ROOF2),
    ('tailor',12,43,6,6,6,ROOF_TERRA),
    ('apothecary',12,32,6,6,6,ROOF_TEAL),
    ('southwest townhouse',-13,16,6,6,5,ROOF),
    ('southeast townhouse',13,16,6,6,5,ROOF2),
]
for name,x,y,w,d,h,roofmat in landmark_houses:
    house(name,x,y,w,d,h,roofmat)

# Dense radial housing blocks sit between the three paved ring roads. Houses
# turn toward the plaza and leave the gate-to-castle avenue open.
placed=[(x,y) for _,x,y,_,_,_,_ in landmark_houses]
roof_palette=[ROOF,ROOF_TEAL,ROOF_TERRA,ROOF2,ROOF_COPPER]
rowhouse_index=0
for ring_index,(radius,count,phase) in enumerate([(16,12,0.12),(27,16,0.04),(36,20,0.10)]):
    for i in range(count):
        angle=phase+i*math.tau/count
        x,y=radius*math.cos(angle),PLAZA_Y+radius*math.sin(angle)
        if abs(x)<9 or y<4 or y>73: continue
        if math.hypot(x-29,y-37)<10: continue  # reserve the east market square
        if math.hypot(x,y-70)<11: continue     # clear the castle approach
        if any(math.hypot(x-px,y-py)<8 for px,py in placed): continue
        width=5.2+(i%3)*0.45
        depth=5.0+((i+1)%3)*0.45
        height=4.9+(i%4)*0.45
        house(f'district rowhouse {rowhouse_index+1:02d}',x,y,width,depth,height,
              roof_palette[(i+ring_index)%len(roof_palette)],facing=angle-math.pi/2)
        placed.append((x,y)); rowhouse_index+=1

# A market square uses repeated stalls, produce baskets, striped canopies and signs.
for x,y in [(22,30),(29,30),(36,30),(22,42),(29,42),(36,42)]:
    for dx in [-1.5,1.5]:
        for dy in [-1,1]: box('market pole',(x+dx,y+dy,1.7),(0.10,0.10,3.4),WOOD)
    box('market counter',(x,y-0.75,1.0),(3.3,0.8,0.8),WOOD)
    for i in range(6):
        xx=x-1.5+(i+0.5)*0.5
        mesh('striped market canopy',[(xx-0.25,y-1.4,2.8),(xx+0.25,y-1.4,2.8),(xx+0.25,y,3.45),(xx-0.25,y,3.45),(xx-0.25,y+1.1,3.0),(xx+0.25,y+1.1,3.0)],[(0,1,2,3),(3,2,5,4),(3,2,1,0),(4,5,2,3)],RED if i%3==0 else BLUE if i%3==1 else TRIM)
    for dx in [-0.85,0,0.85]:
        box('market crate',(x+dx,y-0.8,1.5),(0.70,0.6,0.32),PLASTER)
        for j in range(3): cone('market goods',(x+dx+(j-1)*0.16,y-0.8,1.72),0.10,0.08,0.18,LEAF2,6)

# Raised castle and unequal skyline, leaving a central approach visible.
castle_part_start=len(parts)
CASTLE_SHIFT_Y=36.0
box('castle terrace',(0,33,0.7),(28,15,1.4),JOINT)
for i in range(9): box('castle stair',(0,24.5+i*0.46,0.12+i*0.12),(7.2,0.72,0.24+i*0.24),TRIM)
box('castle hall',(0,34,9.0),(18,12,16),STONE)
roof('castle nave',0,34,17.0,19.2,13.2,7.0,ROOF,ROOF2)
for x,h,y in [(-12,28,32),(-7.5,34,38),(7.5,36,38),(12,29,32)]:
    tower('castle turret',x,y,h,2.2 if abs(x)>9 else 1.9)
tower('castle high spire',0,39,42,2.2)
castle_front=34-6
box('castle door recess',(0,castle_front+1.25,3.0),(6.0,0.16,6.0),JOINT,0.025)
for side in [-1,1]: box('castle portal jamb',(side*3.55,castle_front,3.5),(0.5,0.65,6.5),TRIM)
arch('castle portal',0,castle_front,2.9,3.1,3.85,0.65,TRIM)
crystal('castle oculus',0,castle_front-0.15,10.5,1.0,3.8)
for x in [-9.2,-4.5,4.5,9.2]:
    box('castle facade buttress',(x,castle_front-0.28,8.0),(0.56,0.48,15.2),TRIM,0.08)
    box('castle buttress capital',(x,castle_front-0.38,15.4),(1.05,0.72,0.52),GOLD,0.035)
for z in [7.1,15.8]:
    box('castle carved frieze',(0,castle_front-0.24,z),(17.5,0.36,0.25),TRIM,0.04)
for side in [-1,1]:
    banner('castle standard',side*5.8,castle_front-0.12,17.0,1.8,6.8)
    # Tall stained-glass lancets make the central keep read as a cathedral.
    for panel in range(3):
        x=side*(6.0+panel*1.45)
        box('castle window surround',(x,castle_front-0.15,12.3),(1.02,0.24,5.0),TRIM,0.06)
        box('castle stained glass',(x,castle_front-0.31,12.3),(0.72,0.08,4.5),CRYSTAL if panel==1 else GLASS,0.025)
        box('castle window mullion',(x,castle_front-0.38,12.3),(0.08,0.06,4.5),GOLD,0.01)
        box('castle window crossbar',(x,castle_front-0.39,12.3),(0.72,0.06,0.12),GOLD,0.01)
# Keep the Blender coordinates authored around the gate at Y=0; shift only the
# rear castle cluster deeper into the city behind its market and fountain.
for obj in parts[castle_part_start:]: obj.location.y += CASTLE_SHIFT_Y

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

tree_sites=[(-36,16),(-36,34),(-36,54),(-28,70),(36,16),(36,34),(36,54),(28,70),(-8,58),(8,58),(-8,15),(8,15)]
for x,y in tree_sites:
    if any(math.hypot(x-px,y-py)<7.2 for px,py in placed): continue
    tree(x,y,1.0 if y<20 else 1.2)
for side in [-1,1]:
    for y in [16,21,34,38]: lamp(side*4.9,y)
    for y in [19,34]:
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
bpy.ops.object.camera_add(location=(82,-96,90))
camera=bpy.context.object
camera.name='Reference city overview'
camera.rotation_euler=(Vector((0,CITY_CENTER_Y,8))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO'
camera.data.ortho_scale=132
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
assert triangles < 145000, f'City exceeds the 150k scene triangle ceiling with safety margin: {triangles}'
for o in city_meshes:
    assert all(math.isfinite(c) for v in o.data.vertices for c in v.co)

# The render previews the editable master from the saved presentation camera.
bpy.ops.object.select_all(action='DESELECT')
for o in city_meshes: o.select_set(True)
bpy.context.view_layer.objects.active=city_meshes[0]
bpy.ops.export_scene.gltf(filepath=str(RUNTIME),export_format='GLB',use_selection=True,export_yup=True,export_apply=True,export_materials='EXPORT',export_animations=False,export_cameras=False,export_lights=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt={'asset':'reference-city','revision':'r2','blender':bpy.app.version_string,'authoring':'Original scripted geometry; user supplied ChatGPT reference images; no image pixels embedded','reference':'docs/ui/ChatGPT Image Sep 27, 2026, 08_38_17 PM-1.png','units':'meters; Blender Z up; glTF Y up','authored_parts':authored_parts,'district_rowhouses':rowhouse_index,'export_meshes':len(city_meshes),'triangles_before_export':triangles,'materials':len(city_meshes),'textures':0,'glb':str(RUNTIME.relative_to(ROOT)),'glb_bytes':RUNTIME.stat().st_size,'glb_sha256':sha(RUNTIME),'source_sha256':sha(Path(__file__)),'blend_sha256':sha(OUT/'reference_city.blend'),'scope':'Visual city kit; collisions, interiors, NPCs and city gameplay not implemented by this asset.'}
(OUT/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print('CITY_RECEIPT '+json.dumps(receipt))
bpy.ops.render.render(write_still=True)


