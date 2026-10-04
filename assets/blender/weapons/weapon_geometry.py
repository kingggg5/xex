"""Metre-scale weapon recipes. Pure geometry can be audited without starting Blender."""
from dataclasses import dataclass
from math import sin, cos, pi, sqrt

@dataclass
class Part:
    name: str
    vertices: list
    faces: list
    paint: str
    @property
    def triangles(self):
        return sum(max(0, len(face)-2) for face in self.faces)

def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,s): return tuple(x*s for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unit(a):
    length=sqrt(dot(a,a)); return mul(a,1/max(length,1e-12))

def sweep(name,path,width,depth,paint,sides=8,closed=False,roll=0):
    vertices=[];faces=[];previous=(1,0,0)
    rectangle=[(-1,-1),(1,-1),(1,1),(-1,1)]
    for i,p in enumerate(path):
        before=path[(i-1)%len(path)] if closed else path[max(0,i-1)]
        after=path[(i+1)%len(path)] if closed else path[min(len(path)-1,i+1)]
        tangent=unit(sub(after,before))
        n=sub(previous,mul(tangent,dot(previous,tangent)))
        if dot(n,n)<1e-8: n=cross(tangent,(0,1,0))
        n=unit(n);b=unit(cross(tangent,n));previous=n
        r=roll*i/max(1,len(path)-1);n,b=add(mul(n,cos(r)),mul(b,sin(r))),add(mul(b,cos(r)),mul(n,-sin(r)))
        w=width[i] if isinstance(width,list) else width
        d=depth[i] if isinstance(depth,list) else depth
        for j in range(sides):
            x,y=rectangle[j] if sides==4 else (cos(2*pi*j/sides),sin(2*pi*j/sides))
            vertices.append(add(p,add(mul(n,x*w),mul(b,y*d))))
    segments=len(path) if closed else len(path)-1
    for i in range(segments):
        k=(i+1)%len(path)
        for j in range(sides):faces.append((i*sides+j,i*sides+(j+1)%sides,k*sides+(j+1)%sides,k*sides+j))
    if not closed:
        faces.append(tuple(reversed(range(sides))));faces.append(tuple((len(path)-1)*sides+j for j in range(sides)))
    return Part(name,vertices,faces,paint)

def rod(name,a,b,radius,paint,sides=8): return sweep(name,[a,b],radius,radius,paint,sides)

def gem(name,center,height,width,depth,paint='blue',sides=6):
    cx,cy,cz=center;vertices=[(cx,cy,cz-height*.5)];faces=[]
    for z,scale in [(-.22,.82),(.17,1.0)]:
        for j in range(sides):
            angle=2*pi*j/sides+pi/4
            vertices.append((cx+cos(angle)*width*.5*scale,cy+sin(angle)*depth*.5*scale,cz+z*height))
    vertices.append((cx,cy,cz+height*.5));top=len(vertices)-1
    for j in range(sides):
        n=(j+1)%sides;faces.extend([(0,1+n,1+j),(1+j,1+n,1+sides+n,1+sides+j),(top,1+sides+j,1+sides+n)])
    return Part(name,vertices,faces,paint)

def outline(name,points,center,thickness,paint='gold'):
    """Bevelled extruded profile; broad bevels are geometry, fine wear belongs in albedo."""
    cx,cy,cz=center;vertices=[];faces=[];n=len(points)
    for y,scale in [(-thickness*.5,.82),(-thickness*.25,1),(thickness*.25,1),(thickness*.5,.82)]:
        vertices.extend((cx+x*scale,cy+y,cz+z*scale) for x,z in points)
    for layer in range(3):
        for j in range(n):faces.append((layer*n+j,layer*n+(j+1)%n,(layer+1)*n+(j+1)%n,(layer+1)*n+j))
    faces.append(tuple(reversed(range(n))));faces.append(tuple(3*n+j for j in range(n)))
    return Part(name,vertices,faces,paint)

def diamond_mount(name,center,width,height,depth=.035):
    return outline(name,[(0,-height*.5),(width*.5,0),(0,height*.5),(-width*.5,0)],center,depth)

def collar(name,z,radius,paint='gold',sides=8):
    return sweep(name,[(0,0,z-.022),(0,0,z-.012),(0,0,z+.012),(0,0,z+.022)],
                 [radius*.78,radius,radius,radius*.78],[radius*.78,radius,radius,radius*.78],paint,sides)

def ring(name,center,radius,width,depth,paint='gold',segments=24):
    cx,cy,cz=center
    # Path is in XZ, with a compact octagonal cross-section and no duplicated end caps.
    path=[(cx+radius*cos(2*pi*i/segments),cy,cz+radius*sin(2*pi*i/segments)) for i in range(segments)]
    return sweep(name,path,width,depth,paint,8,True)

def crystal_staff():
    parts=[]
    path=[(0,0,-.72+i*.116) for i in range(11)]
    radii=[.024+.007*i/10 for i in range(11)]
    parts.append(sweep('staff_fluted_wood',path,radii,radii,'wood',8,roll=pi*.8))
    # Two continuous raised wooden flutes, not dozens of separate rings.
    for strand in range(2):
        path=[(.030*cos(i*.39+strand*pi),.030*sin(i*.39+strand*pi),-.7+i*.064) for i in range(18)]
        parts.append(sweep('wood_flute_'+str(strand),path,.007,.004,'wood_light',4))
    for i,z in enumerate([-.72,-.45,.23,.43]):
        parts.append(collar('staff_gold_collar_'+str(i),z,.045))
    parts.extend([gem('staff_main_crystal',(0,0,.94),.76,.29,.22,'blue',8),
                  gem('staff_blue_neck',(0,0,.47),.18,.085,.07,'cyan')])
    # Broad crossing bands physically grip the lower crystal and spread into a crown.
    for strand in range(2):
        path=[]
        for i in range(19):
            t=i/18;theta=-pi*.7+t*pi*2.0+strand*pi;radius=.075+.125*t
            path.append((radius*cos(theta),radius*sin(theta),.36+t*.52))
        parts.append(sweep('crossing_gold_band_'+str(strand),path,.028,.009,'gold',8))
    for side in [-1,1]:
        path=[(side*.055,0,.57),(side*.17,0,.70),(side*.25,0,.84),(side*.245,0,.99),(side*.21,0,1.04)]
        parts.append(sweep('staff_crown_hook_'+str(side),path,[.025,.035,.03,.02,.003],[.015]*5,'gold',4))
        parts.append(rod('pendant_mount_'+str(side),(side*.21,-.01,.82),(side*.23,-.01,.71),.009,'gold',6))
        parts.append(gem('pendant_crystal_'+str(side),(side*.23,-.01,.62),.22,.095,.075,'blue'))
    for i,z in enumerate([-.44,.23,.51]):
        parts.append(diamond_mount('staff_gem_bezel_'+str(i),(0,-.037,z),.092,.125,.025))
        parts.append(gem('staff_set_gem_'+str(i),(0,-.054,z),.07,.043,.025,'blue',4))
    parts.append(gem('staff_upper_gold_cap',(0,0,1.35),.13,.065,.065,'gold',4))
    parts.append(gem('staff_ground_finial',(0,0,-.785),.14,.048,.048,'gold',6))
    return parts,{'fx_base':(0,0,.25),'fx_tip':(0,0,1.4),'grip_r':(0,0,0),'grip_l':(0,0,-.23)}

def recurve_bow():
    parts=[]
    path=[]
    for i in range(37):
        z=-.73+i*1.46/36;t=abs(z)/.73
        y=-.17*sin(pi*t)+.075*t**5
        path.append((0,y,z))
    widths=[.040-.018*abs(p[2])/.73 for p in path]
    parts.append(sweep('bow_laminated_wood',path,widths,[w*.82 for w in widths],'wood',8))
    for face in [-1,1]:
        inset_path=path[::2];inset_widths=widths[::2]
        parts.append(sweep('bow_teal_inset_'+str(face),[(face*.036,p[1]-.005,p[2]) for p in inset_path],
                           [.009]*len(inset_path),[w*.70 for w in inset_widths],'teal',4))
    for side in [-1,1]:
        # Gold structural seam strips retain the limb curvature.
        edge=[(-.034,p[1]+side*.028,p[2]) for p in path[3:-3:2]]
        parts.append(sweep('bow_gold_edge_'+str(side),edge,.009,.006,'gold',4))
        horn=[(0,.070,side*.69),(0,.090,side*.75),(0,.070,side*.805),(0,.034,side*.83)]
        parts.append(sweep('bow_horn_tip_'+str(side),horn,[.034,.031,.022,.002],[.028,.025,.015,.002],'ivory',6))
        parts.append(sweep('bow_tip_socket_'+str(side),[(0,.03,side*.65),(0,.074,side*.70)],.04,.032,'gold',8))
    parts.append(sweep('bow_grip_leather',[(0,-.007,z) for z in [-.095,-.08,.08,.095]],
                       [.037,.045,.045,.037],[.035]*4,'leather',8))
    for side in [-1,1]:
        for j,z in enumerate([.18,.40,.61]):
            center=(0,-.17*sin(pi*z/.73)+.075*(z/.73)**5,side*z)
            # Rotate profile plates into the bow's YZ plane.
            profile=[(-.032,-.075),(.025,-.085),(.072,-.051),(.028,-.036),(.021,.049),(.058,.087),(.013,.110),(-.033,.069)]
            # Paired thin face plates hug the laminate rather than turning it into a solid gold block.
            for face in [-1,1]:
                part=outline('bow_gold_brace_'+str(side)+'_'+str(j)+'_'+str(face),[(x,z*side) for x,z in profile],(0,face*.044,0),.022)
                part.vertices=[(y,center[1]+x,center[2]+zz) for x,y,zz in part.vertices]
                parts.append(part)
    for i,z in enumerate([-.10,.10]):
        parts.append(rod('bow_grip_binding_'+str(i),(-.041,-.016,z),(.041,-.016,z),.012,'gold',6))
    string=sweep('bow_string_rest',[(0,.034,-.83),(0,.034,0),(0,.034,.83)],.004,.004,'string',4)
    parts.append(string)
    return parts,{'fx_base':(0,.034,-.83),'fx_tip':(0,.034,.83),'grip_l':(0,0,0),
                  'grip_r':(0,.34,0),'string_pull':(0,.34,0),'muzzle':(0,-.06,0)}

def sun_sceptre():
    parts=[]
    parts.append(sweep('sceptre_wood',[(0,0,-.76),(0,0,-.3),(0,0,.10),(0,0,.43)],
                       [.026,.03,.032,.032],[.025,.028,.028,.028],'wood',8))
    parts.append(sweep('sceptre_leather_grip',[(0,0,-.10),(0,0,.16)],.036,.033,'leather',8,roll=.8))
    for i,z in enumerate([-.76,-.49,-.13,.18,.31,.42]):parts.append(collar('sceptre_collar_'+str(i),z,.045))
    center=(0,0,.77);radius=.265
    parts.append(ring('sun_ring_structural',center,radius,.034,.022))
    # Front/back rims make real depth readable in side view; one shared atlas/material.
    for side in [-1,1]:
        parts.append(ring('sun_ring_rail_'+str(side),(0,side*.018,.77),radius,.020,.009,'gold_light',16))
    for i in range(8):
        theta=2*pi*i/8;length=.125 if i%2==0 else .09
        points=[(0,-.035),(.043,.01),(0,length),(-.043,.01)]
        rotated=[(x*cos(theta)+z*sin(theta),-x*sin(theta)+z*cos(theta)) for x,z in points]
        parts.append(outline('sun_compass_point_'+str(i),rotated,(sin(theta)*radius,0,.77+cos(theta)*radius),.040))
    parts.append(gem('sceptre_cyan_core',(0,-.005,.77),.36,.21,.105,'cyan',8))
    for side in [-1,1]:
        parts.append(rod('core_support_'+str(side),(0,0,.77+side*.18),(0,0,.77+side*.23),.014,'gold',6))
        parts.append(diamond_mount('core_clasp_'+str(side),(0,-.048,.77+side*.15),.062,.105,.025))
    parts.append(diamond_mount('sceptre_stem_shield',(0,-.006,.36),.18,.21,.07))
    parts.append(gem('sceptre_stem_cyan',(0,-.050,.36),.092,.055,.035,'cyan',4))
    for i,z in enumerate([-.49,-.13]):
        parts.append(diamond_mount('sceptre_set_bezel_'+str(i),(0,-.032,z),.092,.12,.026))
        parts.append(gem('sceptre_set_cyan_'+str(i),(0,-.051,z),.062,.037,.022,'cyan',4))
    parts.append(gem('sceptre_ground_finial',(0,0,-.815),.14,.055,.055,'gold',6))
    return parts,{'fx_base':(0,0,.18),'fx_tip':(0,0,1.16),'grip_r':(0,0,0),'grip_l':(0,0,-.22)}

RECIPES={'02':crystal_staff,'03':recurve_bow,'04':sun_sceptre}
