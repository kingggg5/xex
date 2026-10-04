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
OUT = ROOT / 'assets/models/reference-city/r4'
RUNTIME = OUT / 'city-source.glb'
CITY_SCALE = 1.6
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
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = 'AgX'
scene.world.color = (0.32, 0.38, 0.48)
scene.world.use_nodes = True
world_background = scene.world.node_tree.nodes.get('Background')
world_background.inputs['Color'].default_value = (0.55, 0.68, 0.82, 1)
world_background.inputs['Strength'].default_value = 0.65

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
ROOF_COPPER = material('Copper roof', (0.38, 0.24, 0.15), 0.12)
GOLD = material('Antique brass', (0.72, 0.43, 0.10), 0.65)
BLUE = material('Royal blue cloth', (0.045, 0.18, 0.48))
RED = material('Terracotta cloth', (0.57, 0.12, 0.07))
GLASS = material('Amber windows', (1, 0.50, 0.12), emission=0.4)
WATER = material('Fountain blue', (0.06, 0.39, 0.58), 0.2)
CRYSTAL = material('Arcane azure', (0.03, 0.58, 1), 0.25, 1.2)
LEAF = material('Garden canopy', (0.13, 0.32, 0.075))
LEAF2 = material('Sunlit leaves', (0.28, 0.46, 0.10))
GRASS = material('Garden moss', (0.31, 0.48, 0.15))
FLOWER = material('Garden flowers', (0.70, 0.32, 0.48))
PAVING = material('Hand-laid city cobble', (0.50, 0.53, 0.52))
CLIFF = material('Layered weathered cliff', (0.52, 0.48, 0.39))


def textured_material(mat, image_name, normal_name, uv_scale):
    """Attach packed, authored repeat textures and record their UV scale."""
    mat['reference_city_uv_scale'] = uv_scale
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    uv = nodes.new('ShaderNodeTexCoord')
    uv.name = f'{mat.name} UV coordinates'
    image = bpy.data.images.load(str(OUT / 'textures' / image_name), check_existing=True)
    image.pack()
    color = nodes.new('ShaderNodeTexImage')
    color.name = f'{mat.name} tiled color'
    color.image = image
    color.extension = 'REPEAT'
    links.new(uv.outputs['UV'], color.inputs['Vector'])
    links.new(color.outputs['Color'], shader.inputs['Base Color'])
    normal_image = bpy.data.images.load(str(OUT / 'textures' / normal_name), check_existing=True)
    normal_image.colorspace_settings.name = 'Non-Color'
    normal_image.pack()
    normal_texture = nodes.new('ShaderNodeTexImage')
    normal_texture.name = f'{mat.name} subtle normal map'
    normal_texture.image = normal_image
    normal_texture.extension = 'REPEAT'
    links.new(uv.outputs['UV'], normal_texture.inputs['Vector'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = 0.24
    links.new(normal_texture.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], shader.inputs['Normal'])


def pbr_material(mat, albedo_name, normal_name, roughness_name, uv_scale, normal_strength=0.52):
    """Use packed CC0 albedo/normal/roughness maps on the static town surfaces."""
    mat['reference_city_uv_scale'] = uv_scale
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    uv = nodes.new('ShaderNodeTexCoord')
    uv.name = f'{mat.name} UV coordinates'
    def image_node(name, colorspace, label):
        image = bpy.data.images.load(str(OUT / 'textures' / name), check_existing=True)
        image.colorspace_settings.name = colorspace
        image.pack()
        node = nodes.new('ShaderNodeTexImage')
        node.name = f'{mat.name} {label}'
        node.image = image
        node.extension = 'REPEAT'
        links.new(uv.outputs['UV'], node.inputs['Vector'])
        return node
    albedo = image_node(albedo_name, 'sRGB', 'weathered color')
    links.new(albedo.outputs['Color'], shader.inputs['Base Color'])
    roughness = image_node(roughness_name, 'Non-Color', 'measured roughness')
    links.new(roughness.outputs['Color'], shader.inputs['Roughness'])
    normal_tex = image_node(normal_name, 'Non-Color', 'surface relief')
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = normal_strength
    links.new(normal_tex.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], shader.inputs['Normal'])


pbr_material(STONE, 'stone_limestone.png', 'stone_normal.png', 'stone_roughness.jpg', 0.62)
pbr_material(TRIM, 'stone_trim.png', 'stone_normal.png', 'stone_roughness.jpg', 0.62, 0.38)
pbr_material(PLASTER, 'plaster_warm.png', 'plaster_normal.png', 'plaster_roughness.jpg', 0.54, 0.40)
pbr_material(WOOD, 'wood_oak.png', 'wood_normal.png', 'wood_roughness.jpg', 0.76, 0.40)
pbr_material(ROOF, 'roof_slate.png', 'roof_normal.png', 'roof_roughness.jpg', 0.68)
pbr_material(ROOF2, 'roof_slate_light.png', 'roof_normal.png', 'roof_roughness.jpg', 0.68)
pbr_material(ROOF_TERRA, 'roof_terracotta.png', 'roof_normal.png', 'roof_roughness.jpg', 0.68)
pbr_material(ROOF_TEAL, 'roof_teal.png', 'roof_normal.png', 'roof_roughness.jpg', 0.68)
pbr_material(ROOF_COPPER, 'roof_copper.png', 'roof_normal.png', 'roof_roughness.jpg', 0.68)
pbr_material(PAVING, 'street_cobble.png', 'cobble_normal.png', 'cobble_roughness.jpg', 0.58)
pbr_material(CLIFF, 'cliff_side.png', 'cliff_normal.png', 'cliff_roughness.jpg', 0.40)
textured_material(GRASS, 'grass_field.png', 'grass_field_normal.png', 0.24)
textured_material(WATER, 'water_soft.png', 'water_soft_normal.png', 0.22)
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
    # Weathered overlapping tiles, worn edges and subtle moss live in the
    # authored 1K PBR albedo/normal maps, keeping the repeated roof kit light.
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
    # Deep eaves, porch supports, shutters and planted sills break the box outline.
    roof(name+' porch',x,y-d/2-0.9,2.65,w*0.72,2.3,0.8,roofmat,accent)
    for side in [-1,1]:
        box(name+' porch post',(x+side*w*0.32,y-d/2-1.7,1.35),(0.16,0.16,2.7),WOOD)
        for z in [1.8,4.15]:
            xx=x+side*w*0.29
            box(name+' shutter',(xx+side*0.66,y-d/2-0.2,z),(0.29,0.12,1.18),roofmat)
        box(name+' flowerbox',(x+side*w*0.29,y-d/2-0.42,3.49),(1.15,0.45,0.3),WOOD)
        for j in range(3):
            cone(name+' sill blossom',(x+side*w*0.29+(j-1)*0.32,y-d/2-0.45,3.77),0.18,0.08,0.22,FLOWER,6)
    # Enlarge streets/spacing, not every resident's doorway. Model transform is
    # applied before the city-wide scale; residential door height stays 2.13 m.
    bpy.context.view_layer.update()
    shrink=Matrix.Translation(Vector((x,y,0))) @ Matrix.Scale(1/CITY_SCALE,4) @ Matrix.Translation(Vector((-x,-y,0)))
    for obj in parts[first_part:]: obj.matrix_world=shrink @ obj.matrix_world
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
    for i in range(9):
        a=i*2.399
        dx,dy=math.cos(a)*1.0,math.sin(a)*0.85
        dz=2.8+(i%3)*0.44
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=(0.74+(i%2)*0.2)*size,location=(x+dx*size,y+dy*size,dz*size))
        canopy=finish(bpy.context.object,'garden canopy',LEAF if i%3 else LEAF2)
        for polygon in canopy.data.polygons: polygon.use_smooth=True

def city_island(cx=0,cy=CITY_CENTER_Y,rx=48,ry=44,count=80):
    """Irregular green city plateau with a deep, broken limestone cliff edge."""
    outline=[]
    for i in range(count):
        a=i*math.tau/count
        wobble=1+0.027*math.sin(5*a+0.4)+0.018*math.sin(11*a-0.7)+0.009*math.cos(17*a)
        outline.append((cx+rx*wobble*math.copysign(abs(math.cos(a))**0.65,math.cos(a)),cy+ry*wobble*math.copysign(abs(math.sin(a))**0.65,math.sin(a))))
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
        # lower_verts stores [mid, bottom], so its two rings are 0..count-1
        # and count..2*count-1. The former 2*count offset made invalid faces.
        lower_faces.append((i,j,count+j,count+i))
    mesh('upper stratified limestone cliff',upper_verts,upper_faces,CLIFF)
    mesh('lower dark bedrock',lower_verts,lower_faces,JOINT)
    for i in range(0,count,2):
        x,y=outline[i]
        a=i*math.tau/count
        size=random.uniform(1.1,2.5)
        rock=box('broken cliff block',(x,y,-3.0+random.uniform(-0.5,0.5)),(size,size*0.76,random.uniform(1.0,2.5)),CLIFF if i%4 else TRIM,0.12)
        rock.rotation_euler.z=a
    # One continuous oval moat follows the expanded cliff and avoids seams.
    water_outline=[(58*math.cos(i*math.tau/count),cy+54*math.sin(i*math.tau/count),-2.20) for i in range(count)]
    water_verts=[(cx,cy,-2.20)]+water_outline
    water_faces=[(0,1+i,1+(i+1)%count) for i in range(count)]
    mesh('continuous oval city moat',water_verts,water_faces,WATER)
    for side in [-1,1]:
        for y in [5,24,45,66]:
            fall=box('cliff waterfall',(side*48.5,y,-3.3),(0.55,1.25,3.0),WATER,0.03)
            fall.rotation_euler.z=random.uniform(-0.12,0.12)

city_island(cx=0,cy=CITY_CENTER_Y,rx=48,ry=44)
for x in [-34,34]: box('garden verge',(x,CITY_CENTER_Y,0.035),(18.0,78.0,0.06),GRASS,0)
cone('plaza outer step',(0,PLAZA_Y,0.20),8.0,8.0,0.30,TRIM,64)
cone('plaza paving',(0,PLAZA_Y,0.37),7.7,7.7,0.08,STONE,64)
pavers=[]
for rad in [4.7,6.3,7.5]:
    count=int(rad*8)
    for i in range(count):
        a=i*math.tau/count
        pavers.append(((rad*math.cos(a),PLAZA_Y+rad*math.sin(a),0.435),(0.57,0.47,0.07),TRIM if i%3==0 else STONE,0,a))
for radius in [11,22,33]:
    verts=[]
    for i in range(129):
        a=i*math.tau/128
        for rad in [radius-1.15,radius+1.15]: verts.append((rad*math.cos(a),PLAZA_Y+rad*math.sin(a),0.095))
    mesh('continuous district street',verts,[(i*2,i*2+1,i*2+3,i*2+2) for i in range(128)],PAVING)
    count=int(math.tau*radius/1.25)
    for i in range(count):
        a=i*math.tau/count
        pavers.append(((radius*math.cos(a),PLAZA_Y+radius*math.sin(a),0.14),(0.94,1.10,0.16),TRIM if i%7==0 else PAVING,0,a+math.pi/2))
for y in range(-22,77):
    for x in range(-4,5):
        if (x*0.82)**2+(y-PLAZA_Y)**2<8**2: continue
        pavers.append(((x*0.82+(y%2)*0.10,y,0.13),(0.78,0.94,0.16),TRIM if (x+y)%5==0 else PAVING,0,0))
batch_boxes('city paving network',pavers)

# Gate wing masonry and continuous arch, actual aperture 6 m wide.
gate_ashlar=[]
for side in [-1,1]:
    box('gate wall',(side*21,0,1.8),(34.2,2.1,3.6),STONE,0.10)
    for x in range(5,40,2): box('gate crenel',(side*x,0,4.05),(0.90,2.25,0.9),TRIM)
    for row in range(3):
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
# The old perimeter was a square curtain behind a single wall. This rounded D
# follows the cliff, lets the town fill the skyline, and keeps the south gate
# chord joined to the side towers.
perimeter_right=[(38.1,0),(42,6),(44,18),(45,34),(44,50),(41,64),(35,74),(26,81),(14,84),(0,84)]
wall_boxes=[]; wall_crest=[]
for side in [-1,1]:
    points=perimeter_right if side==1 else [(-x,y) for x,y in perimeter_right]
    for segment,(a,b) in enumerate(zip(points,points[1:])):
        dx=b[0]-a[0]; dy=b[1]-a[1]
        length=math.hypot(dx,dy)
        tangent=math.atan2(dy,dx)
        subdivisions=max(1,math.ceil(length/5.0))
        for index in range(subdivisions):
            t=(index+0.5)/subdivisions
            x=a[0]+dx*t; y=a[1]+dy*t
            segment_length=length/subdivisions
            wall_boxes.append(((x,y,2.72),(segment_length+0.18,1.35,5.35),STONE,0,tangent))
        crenel_count=max(1,math.floor(length/1.65))
        for index in range(crenel_count):
            t=(index+0.5)/crenel_count
            x=a[0]+dx*t; y=a[1]+dy*t
            wall_crest.append(((x,y,5.78),(0.92,1.55,0.82),TRIM,0,tangent))
    for index,height in [(2,9.5),(4,11.0),(6,12.0),(8,10.5)]:
        x,y=points[index]
        tower('rounded perimeter watchtower',x,y,height,1.65 if index<7 else 1.85)
batch_boxes('rounded city perimeter / textured curtain',wall_boxes)
batch_boxes('rounded city perimeter / crenels',wall_crest)
tower('rear crown tower',0,84,13.0,2.0)

# Foreground bridge is a mesh kit extension, flat at the gameplay plane.
box('bridge deck',(0,-11,-0.08),(7.4,22,0.45),PAVING)
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
    ('guild hall',-24,20,12,10,10,ROOF),
    ('potion shop',27,18,9,9,7,ROOF_TEAL),
    ('traveler inn',-30,31,11,9,8,ROOF),
    ('blacksmith',-28,44,11,10,8,ROOF_COPPER),
    ('chapel house',-18,52,7,7,8,ROOF2),
    ('tailor',25,51,6,6,6,ROOF),
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
for ring_index,(radius,count,phase) in enumerate([(16,16,0.12),(27,22,0.04),(36,28,0.10),(44,32,0.07)]):
    for i in range(count):
        angle=phase+i*math.tau/count
        x,y=radius*math.cos(angle),PLAZA_Y+radius*math.sin(angle)
        if abs(x)<10 or y<8 or y>73 or (x/40)**2+((y-39)/38)**2>0.96: continue
        if any(math.hypot(x-px,y-py)<9 for px,py in [(-30,62),(31,66),(13,43)]): continue
        if math.hypot(x-29,y-37)<10: continue  # reserve the east market square
        if math.hypot(x,y-70)<11: continue     # clear the castle approach
        if any(math.hypot(x-px,y-py)<5.8 for px,py in placed): continue
        width=5.2+(i%3)*0.45
        depth=5.0+((i+1)%3)*0.45
        height=4.9+(i%4)*0.45
        house(f'district rowhouse {rowhouse_index+1:02d}',x,y,width,depth,height,
              roof_palette[0 if i%4 else 1],facing=angle-math.pi/2)
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
for x,h,y in [(-12,19,32),(-7.5,26,38),(7.5,28,38),(12,20,32)]:
    tower('castle turret',x,y,h,2.6 if abs(x)>9 else 2.3)
tower('castle high spire',0,39,33,3.4)
for side in [-1,1]:
    box('castle residential wing',(side*14,36,6),(10,13,12),STONE,0.12)
    roof('castle wing roof',side*14,36,12,11,14,4,ROOF)
    for xx in [10.5,14,17.5]:
        for zz in [4,8.5]:
            box('wing window recess',(side*xx,29.43,zz),(1.25,0.16,2.6),JOINT)
            box('wing stained window',(side*xx,29.30,zz),(0.83,0.08,2.13),GLASS)
castle_front=34-6
box('castle door recess',(0,castle_front-0.10,3.0),(6.0,0.16,6.0),JOINT,0.025)
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
for obj in parts[castle_part_start:]:
    obj.location.y += CASTLE_SHIFT_Y
    obj.location.z += 3.0
box('raised castle precinct',(0,70,1.45),(40,20,2.9),CLIFF,0.1)
for i in range(18): box('grand avenue stair',(0,49+i*0.62,0.09+i*0.083),(8,0.66,0.18+i*0.166),TRIM)

# Gothic portal frontage and rose tracery produce one connected keep silhouette.
for side in [-1,1]:
    beam('pointed portal hood',(side*4.1,63.5,11),(0,63.5,16),0.36,TRIM)
    banner('avenue pennant',side*6.1,60,7.5,1.5,3.8)
ring('rose window stone',(0,63.6,17),1.9,0.20,TRIM,(math.pi/2,0,0))
ring('rose window gold',(0,63.4,17),1.5,0.06,GOLD,(math.pi/2,0,0))
for i in range(8):
    a=i*math.tau/8
    beam('rose window tracery',(0,63.35,17),(1.5*math.cos(a),63.35,17+1.5*math.sin(a)),0.055,GOLD)

# Astrolabe tower and windmill: distinct landmarks from the concept sheet.
wizard_start=len(parts)
tower('observatory',16,33,15,2.0,False)
cone('observatory dome',(16,33,15.9),2.35,0.8,1.8,ROOF)
for tilt in [0,math.pi/2]: ring('observatory astrolabe',(16,33,18.1),1.8,0.085,GOLD,(math.pi/2,tilt,0.4))
crystal('observatory core',16,33,18.1,0.48,2.1)
for obj in parts[wizard_start:]: obj.location += Vector((-46,29,0))
VIOLET=material('Wizard amethyst glow',(0.46,0.035,0.9),0.2,2.0)
for z in [12,19,25]:
    ring('wizard spell orbit',(-30,62,z),3.6,0.075,VIOLET)
    for i in range(8):
        a=i*math.tau/8
        cone('wizard orbit rune',(-30+3.6*math.cos(a),62+3.6*math.sin(a),z),0.12,0.03,0.48,VIOLET,4)
tower('wizard upper lantern',-30,62,25,1.6)
windmill_start=len(parts)
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
for obj in parts[windmill_start:]: obj.location += Vector((49,34,0))

# Reference: portal east/north of the central fountain; markets farther east.
cone('portal stone dais',(13,43,0.3),4.4,4.4,0.4,PAVING,40)
for r in [2.5,3.4,4.0]: ring('portal concentric rune',(13,43,0.53),r,0.06,CRYSTAL)
for i in range(12):
    a=i*math.tau/12
    x,y=13+3.85*math.cos(a),43+3.85*math.sin(a)
    beam('portal radial rune',(x,y,0.52),(13+3.2*math.cos(a),43+3.2*math.sin(a),0.52),0.07,CRYSTAL)
for x,y in [(9.5,43),(16.5,43),(13,46.5)]:
    cone('portal carved pedestal',(x,y,0.7),0.42,0.28,1.4,TRIM,8)
    crystal('portal floating shard',x,y,2.6,0.26,1.5)

# Original fountain sculpture: a robed guardian and two carved wings.
cone('guardian draped robe',(0,PLAZA_Y,5),0.82,0.29,2.7,TRIM,12)
cone('guardian head',(0,PLAZA_Y,6.77),0.30,0.26,0.54,TRIM,12)
for side in [-1,1]:
    beam('guardian raised arm',(side*0.32,PLAZA_Y,5.9),(side*0.7,PLAZA_Y,7.15),0.19,TRIM)
    for feather in range(6):
        beam('guardian stone wing',(side*0.5,PLAZA_Y+0.12,5.3),(side*(1.1+feather*0.12),PLAZA_Y+0.20,7.4-feather*0.21),0.13,TRIM)
crystal('guardian crown crystal',0,PLAZA_Y,8.2,0.52,2.0)

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

for i in range(26):
    a=i*math.tau/26
    x,y=39*math.cos(a),39+34*math.sin(a)
    if y<7 or abs(x)<10 or any(math.hypot(x-px,y-py)<4.2 for px,py in placed): continue
    tree(x,y,1.15+(i%3)*0.17)
for i in range(12):
    a=i*math.tau/12
    x,y=10.3*math.cos(a),PLAZA_Y+10.3*math.sin(a)
    if abs(x)<4: continue
    lamp(x,y)
    cone('plaza flower urn',(x+0.9,y,0.45),0.52,0.68,0.85,TRIM,10)
    for j in range(5):
        b=j*math.tau/5
        cone('urn flowers',(x+0.9+0.40*math.cos(b),y+0.40*math.sin(b),1.03),0.24,0.1,0.40,FLOWER if j%2 else LEAF2,6)

# Authored meshes grouped by material on export to keep static draw count bounded.
authored_parts = len(parts)


def assign_surface_uv(o, city_scale=1.0):
    mat=o.data.materials[0] if o.data.materials else None
    if not mat:
        return
    scale=float(mat.get('reference_city_uv_scale',1.0))*city_scale
    layer=o.data.uv_layers.get('UVMap') or o.data.uv_layers.new(name='UVMap')
    for poly in o.data.polygons:
        normal=poly.normal
        dominant=max(range(3),key=lambda axis: abs(normal[axis]))
        axes=((1,2),(0,2),(0,1))[dominant]
        for loop_index in range(poly.loop_start,poly.loop_start+poly.loop_total):
            vertex_index=o.data.loops[loop_index].vertex_index
            if vertex_index >= len(o.data.vertices):
                raise RuntimeError(f'Invalid mesh loop: {o.name} / {o.data.name}, polygon {poly.index}, loop {loop_index}, vertex {vertex_index}, vertex count {len(o.data.vertices)}, loop count {len(o.data.loops)}')
            co=o.data.vertices[vertex_index].co
            layer.data[loop_index].uv=(co[axes[0]]*scale,co[axes[1]]*scale)


for o in parts:
    o.location *= CITY_SCALE
    o.scale *= CITY_SCALE
for o in parts:
    if o.type == 'MESH':
        assign_surface_uv(o,CITY_SCALE)


# Context used only for the Blender review render. The game already supplies
# its own meadow, trees, sky and distant ridges, so these meshes never export.
presentation = bpy.data.collections.new('Presentation only / arrival landscape')
scene.collection.children.link(presentation)
preview_ground = material('Presentation only / meadow', (0.27, 0.39, 0.17))
preview_dirt = material('Presentation only / approach road', (0.34, 0.22, 0.12))
preview_tree_bark = material('Presentation only / tree bark', (0.24, 0.15, 0.09))
preview_tree_leaf = material('Presentation only / tree canopy', (0.13, 0.32, 0.12))
preview_tree_sun = material('Presentation only / sunlit canopy', (0.25, 0.43, 0.18))
preview_ridge = material('Presentation only / distant ridge', (0.40, 0.54, 0.65))
textured_material(preview_ground, 'grass_field.png', 'grass_field_normal.png', 0.24)
textured_material(preview_dirt, 'dirt_path.png', 'dirt_path_normal.png', 0.42)


def presentation_mesh(name, vertices, faces, mat):
    vertices=[tuple(component*CITY_SCALE for component in vertex) for vertex in vertices]
    data=bpy.data.meshes.new(name)
    data.from_pydata(vertices,[],faces)
    data.update()
    obj=bpy.data.objects.new(name,data)
    presentation.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def move_to_presentation(obj):
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    presentation.objects.link(obj)
    return obj


presentation_mesh('outskirts grass / render only',
    [(-130,-170,-0.14),(130,-170,-0.14),(130,-22,-0.14),(-130,-22,-0.14)],[(0,1,2,3)],preview_ground)
presentation_mesh('arrival trail / render only',
    [(-3.6,-170,-0.05),(3.6,-170,-0.05),(3.6,-21.75,-0.05),(-3.6,-21.75,-0.05)],[(0,1,2,3)],preview_dirt)


def preview_tree(x,y,size):
    bpy.ops.mesh.primitive_cone_add(vertices=7,radius1=0.28*size,radius2=0.11*size,depth=3.4*size,location=(x,y,1.7*size))
    trunk=bpy.context.object; trunk.name='outskirts tree trunk / render only'; trunk.data.materials.append(preview_tree_bark); move_to_presentation(trunk)
    for dx,dy,dz,r,mat in [(-0.8,0,3.2,1.6,preview_tree_leaf),(0.7,0.2,3.8,1.8,preview_tree_sun),(0,-0.5,4.8,1.55,preview_tree_leaf)]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=r*size,location=(x+dx*size,y+dy*size,dz*size))
        canopy=bpy.context.object; canopy.name='outskirts canopy / render only'; canopy.scale=(1.0,0.9,1.05); canopy.data.materials.append(mat); move_to_presentation(canopy)


for x,y,size in [(-28,-36,0.78),(29,-43,0.84),(-39,-57,0.96),(41,-66,1.0),(-24,-82,0.84),(27,-97,0.92)]:
    preview_tree(x*CITY_SCALE,y*CITY_SCALE,size*CITY_SCALE)


for ridge_index,(y,base_z,peaks) in enumerate([
    (116,-5,[(-155,27,23),(-92,20,30),(-29,30,25),(34,19,18),(96,25,29),(158,27,23)]),
    (138,-4,[(-160,35,30),(-102,30,35),(-40,46,34),(27,34,29),(102,43,35),(164,34,25)]),
]):
    xs=list(range(-180,181,4))
    tops=[]
    for i,x in enumerate(xs):
        height=base_z+sum(amplitude*math.exp(-((x-center)/width)**2) for center,amplitude,width in peaks)
        height+=0.7*math.sin(i*0.37+ridge_index)
        tops.append((x,y,height))
    bottom=[(x,y+2,base_z) for x in xs]
    vertices=tops+bottom
    faces=[]
    for index in range(len(xs)-1):
        faces.extend([(index,index+1,len(xs)+index+1),(index,len(xs)+index+1,len(xs)+index)])
    ridge=presentation_mesh(f'far mountains / render only {ridge_index}',vertices,faces,preview_ridge)
    for polygon in ridge.data.polygons: polygon.use_smooth=True

for obj in presentation.objects:
    if obj.type=='MESH': assign_surface_uv(obj)

# Save the editable master with the individual authored pieces and a low,
# player-height arrival camera. The runtime GLB is joined by material after this save.
bpy.ops.object.light_add(type='AREA',location=(-22*CITY_SCALE,-10*CITY_SCALE,48*CITY_SCALE))
bpy.context.object.name='Preview softbox'
bpy.context.object.data.energy=36000
bpy.context.object.data.shape='DISK'
bpy.context.object.data.size=48*CITY_SCALE
bpy.ops.object.light_add(type='SUN',location=(0,0,30))
bpy.context.object.rotation_euler=(0.45,-0.5,-0.4)
bpy.context.object.data.energy=2.0
bpy.context.object.data.angle=0.18
bpy.ops.object.camera_add(location=(24*CITY_SCALE,-113*CITY_SCALE,107*CITY_SCALE))
camera=bpy.context.object
camera.name='City reference composition / elevated overview'
camera.rotation_euler=(Vector((0,35*CITY_SCALE,7*CITY_SCALE))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='PERSP'
camera.data.lens=36
scene.camera=camera
scene.render.filepath=str(OUT/'overview.png')
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'reference_city.blend'))
for mat in list(bpy.data.materials):
    group=[o for o in scene.objects if o.type=='MESH' and o in parts and o.data.materials[0]==mat]
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

city_meshes=[o for o in scene.objects if o.type=='MESH' and o.name.startswith('City / ')]
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
receipt={'asset':'reference-city','revision':'r4','blender':bpy.app.version_string,'authoring':'Original geometry with Poly Haven CC0 PBR textures; see provenance.json; no reference pixels embedded','reference':'docs/ui/city-layout-target-20260928.png','units':'meters; Blender Z up; glTF Y up','city_scale':CITY_SCALE,'landmark_positions_blender_m':{'castle':[0,112,4.8],'wizard_tower':[-48,99.2,0],'windmill':[49.6,105.6,0],'fountain':[0,54.4,0],'portal':[20.8,68.8,0],'guild_hall':[-38.4,32,0],'potion_shop':[43.2,28.8,0],'gate':[0,0,0]},'authored_parts':authored_parts,'district_rowhouses':rowhouse_index,'export_meshes':len(city_meshes),'triangles_before_export':triangles,'materials':len(city_meshes),'textures':len({node.image.name for o in city_meshes for mat in o.data.materials for node in mat.node_tree.nodes if node.type=='TEX_IMAGE' and node.image}),'glb':str(RUNTIME.relative_to(ROOT)),'glb_bytes':RUNTIME.stat().st_size,'glb_sha256':sha(RUNTIME),'source_sha256':sha(Path(__file__)),'blend_sha256':sha(OUT/'reference_city.blend'),'scope':'Visual city kit; collisions, interiors, NPCs and city gameplay not implemented by this asset.'}
(OUT/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print('CITY_RECEIPT '+json.dumps(receipt))
bpy.ops.render.render(write_still=True)


