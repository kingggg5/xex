"""One original F26 A candidate; versioned sources only. Blender5.2 CPU6."""
from pathlib import Path
import argparse,json,math,sys,time,hashlib
import bpy,bmesh,numpy as np
from mathutils import Vector
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
sys.path.insert(0,str(REPO/'assets/blender/nature_props'))
import np_lib as L
import np_review as R
OUT=REPO/'assets/models/props/market-hero-v2-candidate';EVID=REPO/'planning/evidence/market-hero-20261003'
TILES={'wood':(.018,.52),'apple':(.535,.035),'bread':(.765,.035),'clay':(.535,.265),'basket':(.765,.265),'iron':(.535,.535)}

class Builder:
    def __init__(self,lod,revision):self.parts=[];self.lod=lod;self.revision=revision
    def finish(self,ob,tile='wood',bevel=.012):
        bpy.context.view_layer.update()
        L.apply_transform(ob)
        if bevel and self.lod<=0:
            mod=ob.modifiers.new('authored edge bevel','BEVEL');mod.width=bevel;mod.segments=5 if self.lod<0 else 1;mod.affect='EDGES';L.apply_modifiers(ob)
        bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()
        if bevel and self.lod<=0:
            for face in ob.data.polygons:face.use_smooth=True
            mod=ob.modifiers.new('area weighted craft normals','WEIGHTED_NORMAL');mod.keep_sharp=True;mod.weight=40;L.apply_modifiers(ob)
        self.assign_uv(ob,tile)
        ob['partRole']=tile;ob.data.materials.clear();ob.data.materials.append(MATS[1 if tile=='cloth' else 0]);self.parts.append(ob);return ob
    def assign_uv(self,ob,tile):
        while ob.data.uv_layers:ob.data.uv_layers.remove(ob.data.uv_layers[0])
        uv=ob.data.uv_layers.new(name='UVMap');vertices=L.verts(ob.data);mn=vertices.min(0);span=np.ptp(vertices,axis=0)
        for face in ob.data.polygons:
            axis=int(np.argmax(np.abs(face.normal)));axes=list((1,2) if axis==0 else (0,2) if axis==1 else (0,1))
            if span[axes[0]]<span[axes[1]]:axes.reverse()
            direction=Vector((1 if axes[0]==0 else 0,1 if axes[0]==1 else 0,1 if axes[0]==2 else 0));basis_u=(direction-face.normal*direction.dot(face.normal)).normalized();basis_v=face.normal.cross(basis_u).normalized()
            projected=[(Vector(vertices[ob.data.loops[li].vertex_index]).dot(basis_u),Vector(vertices[ob.data.loops[li].vertex_index]).dot(basis_v)) for li in face.loop_indices];minimum=np.min(projected,axis=0)
            for pi,li in enumerate(face.loop_indices):
                q=vertices[ob.data.loops[li].vertex_index]-mn
                if tile=='cloth' and abs(face.normal.z)>.3:coords=(vertices[ob.data.loops[li].vertex_index][0]+1.35,vertices[ob.data.loops[li].vertex_index][1]+.982);off=(.006,.006)
                else:coords=np.array(projected[pi])-minimum;off=(.006,.006) if tile=='cloth' else TILES[tile]
                uv.data[li].uv=(off[0]+coords[0]*360/2048,off[1]+coords[1]*360/2048)
    def box(self,name,size,center,tile='wood',bevel=.012):return self.finish(L.box_object(name,size,center),tile,bevel)
    def beam(self,name,a,b,width=.10,tile='wood',bevel=.009):
        a,b=Vector(a),Vector(b);o=L.box_object(name,(width,width,(b-a).length),(0,0,0));o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();o.location=(a+b)/2;return self.finish(o,tile,bevel=bevel)
    def lathe(self,name,profile,center,tile,n=10):
        n=max(5,n//2) if self.lod>=2 else max(6,n-2) if self.lod==1 else n;vs=[];rings=[];fs=[]
        for radius,z in profile:
            if radius==0:rings.append([len(vs)]);vs.append((center[0],center[1],center[2]+z));continue
            ring=[]
            for k in range(n):a=math.tau*k/n;ring.append(len(vs));vs.append((center[0]+radius*math.cos(a),center[1]+radius*math.sin(a),center[2]+z))
            rings.append(ring)
        for a,b in zip(rings,rings[1:]):
            for k in range(n):j=(k+1)%n;fs.append([a[0],b[j],b[k]] if len(a)==1 else [a[k],a[j],b[0]] if len(b)==1 else [a[k],a[j],b[j],b[k]])
        if len(rings[0])>1:fs.append(rings[0][::-1])
        if len(rings[-1])>1:fs.append(rings[-1])
        ob=self.finish(L.mesh_from_arrays(name,vs,fs),tile,0)
        for face in ob.data.polygons:face.use_smooth=True
        return ob
    def canopy(self):
        nx,ny=(36,14) if self.lod<0 else (18,5) if self.lod==0 else (9,3) if self.lod==1 else (6,2)
        xs=[-1.35+2.7*i/nx for i in range(nx+1)];ys=[-.96+1.92*j/ny for j in range(ny+1)]
        if self.revision>=4:
            if self.lod==0:xs=[-1.35,-1.13,-.95,-.76,-.57,-.38,-.19,0,.19,.38,.57,.76,.95,1.13,1.35];ys=[-.96,-.65,-.30,0,.30,.65,.96]
            elif self.lod==1:xs=sorted(set(xs+[-1.13,1.13]));ys=[-.96,-.65,0,.65,.96]
            elif self.lod>=2:xs=[-1.35,-1.13,-.56,0,.56,1.13,1.35];ys=[-.96,-.65,.65,.96]
            else:xs=sorted(set(xs+[-1.13,1.13]));ys=sorted(set(ys+[-.65,.65]))
            nx,ny=len(xs)-1,len(ys)-1
        vs=[];fs=[]
        for dz in (0,-.025):
            for j in range(ny+1):
                y=ys[j]
                for i in range(nx+1):
                    x=xs[i]
                    if self.revision>=4:
                        bay_x=max(0,math.sin(math.pi*(x+1.13)/2.26)) if abs(x)<1.13 else 0
                        bay_y=max(0,math.sin(math.pi*(y+.65)/1.30)) if abs(y)<.65 else 0
                        z=2.58+.125*y/.96-.073*bay_x*bay_y
                    else:
                        z=2.58+.125*y/.96-.055*math.sin(math.pi*i/nx)*math.sin(math.pi*j/ny)
                        if self.revision>=2:z-=.018*math.sin(math.pi*i/nx)**2
                    vs.append((x,y,z+dz))
        count=(nx+1)*(ny+1)
        for off in (0,count):
            for j in range(ny):
                for i in range(nx):a=off+j*(nx+1)+i;q=[a,a+1,a+nx+2,a+nx+1];fs.append(q if off==0 else q[::-1])
        border=list(range(nx+1))+[j*(nx+1)+nx for j in range(1,ny+1)]+list(range(count-2,count-nx-2,-1))+[j*(nx+1) for j in range(ny-1,0,-1)]
        for a,b in zip(border,border[1:]+border[:1]):fs.append([a,b,b+count,a+count])
        self.finish(L.mesh_from_arrays('supported_sag_canopy',vs,fs),'cloth',0)
        # A sewn closed valance: chunky scallops, low-frequency form; stitches stay in maps.
        n=(72 if self.lod<0 else 45) if self.revision>=4 and self.lod<1 else 27 if self.lod<1 else 27 if self.revision>=4 and self.lod==1 else 18 if self.lod==1 else 9;vs=[];fs=[]
        for y in (-.982,-.967):
            for bottom in (False,True):
                for i in range(n+1):
                    x=-1.35+2.7*i/n;z=2.455-.018*math.sin(math.pi*i/n)**2
                    if bottom:z-=.14+.028*(.5+.5*math.cos(x*math.tau/.3))
                    vs.append((x,y,z))
        N=n+1
        for i in range(n):
            fs.extend([[i,i+1,N+i+1,N+i],[2*N+i,3*N+i,3*N+i+1,2*N+i+1],[i,2*N+i,2*N+i+1,i+1],[N+i,N+i+1,3*N+i+1,3*N+i]])
        fs.extend([[0,N,3*N,2*N],[n,2*N+n,3*N+n,N+n]])
        val=self.finish(L.mesh_from_arrays('scalloped_sewn_valance',vs,fs),'cloth',0)
        for face in val.data.polygons:
            if abs(face.normal.y)>.3:
                for li in face.loop_indices:
                    v=val.data.vertices[val.data.loops[li].vertex_index].co;val.data.uv_layers[0].data[li].uv=(.006+(v.x+1.35)*360/2048,.014+(2.455-v.z)*360/2048)
    def construct(self):
        for x in (-1.13,1.13):
            for y in (-.65,.65):
                height=2.47 if y<0 else 2.64
                if self.lod<=0:
                    # Exact extruded half-lap profile avoids Boolean coplanar slivers.
                    sign=math.copysign(1,y);inner=y-sign*.07;outer=y+sign*.07;recess=inner+sign*.075
                    section=[(outer,0),(inner,0),(inner,height-.16),(recess,height-.16),(recess,height),(outer,height)]
                    verts=[(xx,yy,zz) for xx in (x-.07,x+.07) for yy,zz in section]
                    faces=[list(range(5,-1,-1)),list(range(6,12))]+[[i,(i+1)%6,(i+1)%6+6,i+6] for i in range(6)]
                    post=L.mesh_from_arrays('grounded_half_lap_post',verts,faces)
                else:post=L.box_object('grounded_joined_post',(.14,.14,height),(x,y,height/2))
                self.finish(post,bevel=.014)
                if self.lod<2:
                    self.box('post_foot_shoe',(.165,.165,.14),(x,y,.07),'iron',.008)
                    # Broad knee brace, attached into frame, no tiny raised hardware.
                    self.beam('square_knee_brace',(x,y,1.98),(x-math.copysign(.34,x),y,height-.10),.085)
        for y,z in ((-.65,2.38),(.65,2.555)):
            self.box('half_lap_header',(2.40,.15,.16),(0,y,z),bevel=.018)
        for x in (-1.13,1.13):self.beam('canopy_side_rafter',(x,-.96,2.387),(x,.96,2.635),.09)
        if self.lod<2:
            for x in (-1.13,1.13):
                for y,z in ((-.726,2.34),(.726,2.505)):self.box('joint_strap',(.09,.018,.27),(x,y,z),'iron',.008)
        planks=6 if self.lod<1 else 4 if self.lod==1 else 1
        for i in range(planks):
            w=2.4/planks;self.box('counter_plank',(w-.012 if planks>1 else w,1.1,.09),(-1.2+(i+.5)*w,0,.905),bevel=.015 if self.lod<2 else 0)
        for x in (-1.04,1.04):self.box('counter_bearer',(.12,.94,.15),(x,0,.81),bevel=.012)
        count=7 if self.lod<1 else 4 if self.lod==1 else 1
        for i in range(count):
            w=2.26/count;self.box('front_apron_board',(w-.012 if count>1 else w,.065,.54),(-1.13+(i+.5)*w,-.515,.56),bevel=.012 if self.lod<2 else 0)
        for z in (.30,.81):self.box('apron_crossrail',(2.27,.075,.09),(0,-.548,z),bevel=.012 if self.lod<2 else 0)
        self.canopy()
        # One purposefully grouped goods arrangement; all remains within original footprint.
        cx,cy=-.65,-.23
        self.box('crate_floor',(.60,.40,.035),(cx,cy,.968),bevel=.006 if self.lod<2 else 0)
        if self.lod<2:
            for x in (cx-.285,cx+.285):
                self.box('joined_crate_end',(.03,.40,.25),(x,cy,1.10),bevel=.006)
                for y in (cy-.18,cy+.18):self.box('crate_corner_post',(.035,.035,.28),(x,y,1.09),bevel=.006)
            for y in (cy-.185,cy+.185):
                for z in (1.055,1.145 if self.revision>=5 else 1.20):self.box('slatted_crate_side',(.60,.03,.105),(cx,y,z),bevel=.006)
        else:
            for y in (cy-.185,cy+.185):self.box('crate_silhouette',(.6,.03,.27),(cx,y,1.10),bevel=0)
        apples=6 if self.lod<1 else 4 if self.lod==1 else 2
        for i in range(apples):
            x=cx+((i%3)-1)*.16;y=cy+.03*(i//3);base=1.0+.105*(i//3)
            self.lathe('apple_with_crown',[(0,0),(.06,.015),(.082,.065),(.071,.115),(.03,.135),(0,.125)],(x,y,base),'apple',8)
        b=self.lathe('woven_bread_basket',[(0,0),(.18,.01),(.28,.19),(.29,.23),(.25,.245),(.23,.19),(.15,.05),(0,.05)],(.50,-.10,.95),'basket',12)
        if self.lod<2:
            for i in range(8 if self.lod==0 else 5):
                a=math.pi*i/(8 if self.lod==0 else 5);b=math.pi*(i+1)/(8 if self.lod==0 else 5)
                self.beam('basket_handle',(.50+.265*math.cos(a),-.10,1.195+.23*math.sin(a)),(.50+.265*math.cos(b),-.10,1.195+.23*math.sin(b)),.025,tile='basket',bevel=0)
        for i in range(3 if self.lod<1 else 2):
            bread_z=1.0 if self.revision>=5 else 1.08
            o=self.lathe('scored_oval_loaf',[(0,0),(.085,.025),(.09,.075),(.067,.12),(0,.145)],(.37+i*.13,-.10,bread_z),'bread',8)
            # Broad bread oval, not a pointed cone; actual cross-section and sculpted crown.
            for v in o.data.vertices:
                v.co.y=-.10+(v.co.y+.10)*(2.0 if self.revision>=5 else 1.6)
                if self.revision>=5:v.co.z=bread_z+(v.co.z-bread_z)*2.2
            o.data.update();self.assign_uv(o,'bread')
        self.lathe('lip_and_neck_jar',[(0,0),(.10,.01),(.135,.10),(.12,.23),(.06,.30),(.075,.32),(.075,.35),(.048,.35),(.045,.305),(0,.295)],(.92,-.36 if self.revision>=5 else .22,.95),'clay',10)
        part_reports=[]
        for part in self.parts:
            L.triangulate(part);report=L.mesh_report(part);part_reports.append({'name':part.name,'role':part.get('partRole'),**report})
        dest=EVID/f'r{self.revision:02d}';dest.mkdir(parents=True,exist_ok=True);L.write_json(dest/f'parts-lod{self.lod}.json',part_reports)
        return L.join(self.parts,'sm_market_stall_a_hero')

def materials(tex):
    return [L.pbr_material('sm_craft_timber',tex/'market_hero_albedo.png',tex/'market_hero_normal.png',tex/'market_hero_orm.png',normal_strength=.65),L.pbr_material('sm_craft_cloth',tex/'market_hero_albedo.png',tex/'market_hero_normal.png',tex/'market_hero_orm.png',normal_strength=.35,double_sided=True)]

def bake_trim(tex,revision):
    """Genuine selected-to-active shared-trim source bake, not an asset-unique AO bake."""
    L.setup_cycles(4,6)
    low=L.mesh_from_arrays('trim_bake_receiver',[(-1.35,-1.35,0),(1.35,-1.35,0),(1.35,1.35,0),(-1.35,1.35,0)],[[0,1,2,3]])
    uv=low.data.uv_layers.new(name='UVMap')
    for i,co in enumerate(((.018,.52),(.4926,.52),(.4926,.9946),(.018,.9946))):uv.data[i].uv=co
    target=L.bake_target_material('shared_trim_bake_target');low.data.materials.append(target)
    high=L.box_object('high_bevel_timber_trim',(2.7,2.7,.10),(0,0,-.042));L.bevel(high,.025,segments=5);L.apply_modifiers(high)
    mat=L.diffuse_material('high_timber_micrograin');nt=mat.node_tree;bs=nt.nodes.get('Principled BSDF');tc=nt.nodes.new('ShaderNodeTexCoord');wave=nt.nodes.new('ShaderNodeTexWave');wave.wave_type='BANDS';wave.bands_direction='Y';wave.inputs['Scale'].default_value=140;wave.inputs['Distortion'].default_value=2
    bump=nt.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.32;bump.inputs['Distance'].default_value=.002;nt.links.new(tc.outputs['Generated'],wave.inputs['Vector']);nt.links.new(wave.outputs['Color'],bump.inputs['Height']);nt.links.new(bump.outputs['Normal'],bs.inputs['Normal']);high.data.materials.append(mat)
    records=[]
    for kind,color,name in [('NORMAL',(.5,.5,1,1),'normal'),('AO',(1,1,1,1),'ao')]:
        image=L.float_image('market_trim_'+name,1024,color);start=time.monotonic();L.bake_selected_to_active(low,[high],image,kind,cage=.04,max_dist=.10,margin=8,samples=4)
        image.filepath_raw=str(tex/f'baked_trim_{name}.png');image.file_format='PNG';image.save();records.append({'type':kind,'seconds':round(time.monotonic()-start,2),'size':1024,'normal_g':'POS_Y','high_triangles':L.tri_count(high),'scope':'shared representative timber trim, not full asset AO'})
    geo=nt.nodes.new('ShaderNodeNewGeometry');emit=nt.nodes.new('ShaderNodeEmission');nt.links.new(geo.outputs['Pointiness'],emit.inputs['Color']);nt.links.new(emit.outputs[0],nt.nodes.get('Material Output').inputs['Surface'])
    image=L.float_image('market_trim_curvature',1024,(.5,.5,.5,1));L.bake_selected_to_active(low,[high],image,'EMIT',cage=.04,max_dist=.10,margin=8,samples=1);image.filepath_raw=str(tex/'baked_trim_curvature.png');image.file_format='PNG';image.save();records.append({'type':'curvature_pointiness_EMIT','size':1024,'scope':'high trim bevel curvature'})
    # Replace just the shared timber region with the real normal/AO bake. Preserve cloth/goods painter maps.
    normal=L.load_image(tex/'market_hero_normal.png','Non-Color');data=L.image_array(normal);baked=L.image_array(bpy.data.images['market_trim_normal']);mask=np.zeros((1024,1024),bool);mask[6:492,18:504]=True;data[mask,:3]=baked[mask,:3];normal.pixels.foreach_set(data[::-1].astype(np.float32).ravel());normal.filepath_raw=str(tex/'market_hero_normal.png');normal.file_format='PNG';normal.save()
    orm=L.load_image(tex/'market_hero_orm.png','Non-Color');data=L.image_array(orm);ao=L.image_array(bpy.data.images['market_trim_ao']);data[mask,0]=np.maximum(.72,ao[mask,0]);orm.pixels.foreach_set(data[::-1].astype(np.float32).ravel());orm.filepath_raw=str(tex/'market_hero_orm.png');orm.file_format='PNG';orm.save()
    # Baked high-source curvature drives restrained painted edge wear on the shared trim.
    albedo=L.load_image(tex/'market_hero_albedo.png','Non-Color');data=L.image_array(albedo);curv=L.image_array(image)[:,:,0];curv=np.repeat(np.repeat(curv,2,axis=0),2,axis=1);bigmask=np.repeat(np.repeat(mask,2,axis=0),2,axis=1)
    wear=np.clip((curv-.5)*1.5,-.12,.16);data[bigmask,:3]=np.clip(data[bigmask,:3]+wear[bigmask,None]*np.array([.20,.15,.08]),.105,.95);albedo.pixels.foreach_set(data[::-1].astype(np.float32).ravel());albedo.filepath_raw=str(tex/'market_hero_albedo.png');albedo.file_format='PNG';albedo.save();albedo.colorspace_settings.name='sRGB'
    L.delete([low,high]);return records

def review(ob,path,revision):
    R.setup_render((1200,800),24,6);R.setup_world(.48);sun=R.add_sun(225,48,3.0);ground=R.ground_plane('sand',20,(0,0));ground.location.z=-.001;w=R.witness((-2.2,-.30));records=[]
    for view,loc,target,fov in [('game',(-4,-11.3,6.7),(0,0,1.65),1.02),('close',(-3.8,-4.1,3.0),(0,0,1.35),.8),('side',(5,-.2,2.8),(0,0,1.4),.88),('elevated',(-4,-5,6),(0,0,1.1),.88)]:
        cam=R.camera(view,loc,target,fov_y=fov);bpy.context.scene.camera=cam;dest=path/f'BLENDER_REVIEW_stall_{view}.png';seconds=R.render(dest);records.append({'view':view,'file':str(dest.relative_to(REPO)),'seconds':seconds,'label':'BLENDER REVIEW','witness_m':1.8,'threads':6,'samples':24,'resolution':[1200,800]});L.delete([cam])
    L.write_json(path/'review.json',{'revision':revision,'views':records});L.delete([sun,ground,w])

def main():
    global MATS
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--bake',action='store_true');ap.add_argument('--proof',action='store_true');ap.add_argument('--review-only',action='store_true');ap.add_argument('--export-saved',action='store_true');a=ap.parse_args(L.args_after_dashdash());rev=f'r{a.revision:02d}';out=OUT/rev;tex=out/'textures-source';ev=EVID/rev
    if a.export_saved:
        blend=HERE/'sources'/f'sm_market_stall_a_{rev}.blend';bpy.ops.wm.open_mainfile(filepath=str(blend));source=out/'source';source.mkdir(parents=True,exist_ok=True)
        if (source/'sm_market_stall_a_hero_lod0.glb').exists():raise ValueError('Immutable exports already exist')
        for i in range(3):
            ob=bpy.data.objects[f'sm_market_stall_a_hero_lod{i}'];ob.hide_set(False);ob.hide_render=False;L.export_lod(ob,source/f'{ob.name}.glb',budget_class='building_module',texture_dir=source/'textures',vertex_color='NONE',double_sided=['sm_craft_cloth'],notes=f'original F26A market hero candidate, revision={a.revision}, shared trim 360px/m, no live promotion')
        for name,file in [('sm_market_stall_a_hero_collider','sm_market_stall_a_hero_collider.glb'),('shadow_canopy','sm_market_stall_a_shadow_proxy.glb')]:
            ob=bpy.data.objects[name];ob.hide_set(False);ob.hide_render=False;L.export_lod(ob,source/file,materials='NONE',vertex_color='NONE')
        print('MARKET APPROVED SOURCE EXPORT',rev,flush=True);return
    if a.proof:
        L.reset();L.setup_cycles(4,6);MATS=materials(tex);ob=Builder(0,a.revision).construct();ob.name='sm_market_stall_a_hero_lod0';L.triangulate(ob)
        dest=ev/'determinism-rebuild'/f'{ob.name}.glb';dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():raise ValueError('Immutable proof already exists')
        L.export_lod(ob,dest,budget_class='building_module',texture_dir=dest.parent/'textures',vertex_color='NONE',double_sided=['sm_craft_cloth'],notes=f'original F26A market hero candidate, revision={a.revision}, shared trim 360px/m, no live promotion')
        original=out/'source'/f'{ob.name}.glb';first=hashlib.sha256(original.read_bytes()).hexdigest();second=hashlib.sha256(dest.read_bytes()).hexdigest();L.write_json(ev/'determinism-rebuild.json',{'source_sha256':first,'rebuilt_sha256':second,'byte_identical':first==second,'seed':2026100326,'revision':a.revision,'scope':'fresh Blender process geometry/material/source export rebuild, same saved texture inputs'});print('MARKET FRESH REBUILD',first==second);return
    for p in (out/'source',ev,HERE/'sources'):p.mkdir(parents=True,exist_ok=True)
    if (out/'source/sm_market_stall_a_hero_lod0.glb').exists():raise ValueError('Immutable version exists; use a fresh revision')
    L.reset();L.setup_cycles(8,6);bakes=bake_trim(tex,a.revision) if a.bake else []
    MATS=materials(tex);high=Builder(-1,a.revision).construct();high.name='sm_market_stall_a_high_source';high.hide_render=True;high.hide_set(True)
    lods=[Builder(i,a.revision).construct() for i in range(3)];reports={};ceilings=[4000,1800,700]
    for i,ob in enumerate(lods):
        ob.name=f'sm_market_stall_a_hero_lod{i}';L.triangulate(ob);report=L.mesh_report(ob)
        if report['triangles']>ceilings[i]:raise ValueError(f'LOD{i} exceeds {ceilings[i]}: {report["triangles"]}')
        if report['zero_area_faces'] or report['non_manifold_edges']:raise ValueError(f'Invalid LOD{i}: {report}')
        reports[f'lod{i}']=report
    for i,ob in enumerate(lods):
        if not a.review_only:
            dest=out/'source'/f'{ob.name}.glb';rec=L.export_lod(ob,dest,budget_class='building_module',texture_dir=out/'source/textures',vertex_color='NONE',double_sided=['sm_craft_cloth'],notes=f'original F26A market hero candidate, revision={a.revision}, shared trim 360px/m, no live promotion')
            if rec['status']!='PASS':raise ValueError('Export failed')
        ob.hide_render=i>0;ob.hide_set(i>0)
    collider=[]
    for x in (-1.13,1.13):
        for y in (-.65,.65):collider.append(L.box_object('collider_post',(.16,.16,2.45),(x,y,1.225)))
    collider.append(L.box_object('collider_counter',(2.4,1.1,.12),(0,0,.89)));collider.append(L.box_object('collider_apron',(2.27,.08,.63),(0,-.52,.54)))
    col=L.join(collider,'sm_market_stall_a_hero_collider')
    if not a.review_only:L.export_lod(col,out/'source'/f'{col.name}.glb',materials='NONE',vertex_color='NONE')
    col.hide_render=True;col.hide_set(True)
    shadow=L.box_object('shadow_canopy',(2.7,1.92,.045),(0,0,2.51))
    if not a.review_only:L.export_lod(shadow,out/'source/sm_market_stall_a_shadow_proxy.glb',materials='NONE',vertex_color='NONE')
    shadow.hide_render=True;shadow.hide_set(True)
    metadata={'recipe':'market_hero_v2/2','revision':a.revision,'seed':2026100326,'body_m':[2.4,1.6,2.6],'pivot':[0,0,0],'front':'Blender -Y / Babylon +Z','counterTop':.95,'materialSlots':['sm_craft_timber','sm_craft_cloth'],'atlasFamily':'market_hero_v2','authoringTexelDensity':360,'highTriangles':L.tri_count(high),'lods':reports,'bakes':bakes,'collider':'compound posts/counter/apron; open service aperture above0.95m; no whole-stall hull','shadowProxy':'canopy only candidate; native shadow cost pending','anchors':{'awningCentre':[0,0,2.58],'counterCentre':[0,0,.95]},'status':'SOURCE_CANDIDATE_NOT_PROMOTED'}
    L.write_json(out/'candidate.json',metadata);L.write_json(ev/'build-receipt.json',metadata);bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'sources'/f'sm_market_stall_a_{rev}.blend'),compress=True);review(lods[0],ev,a.revision);print('MARKET SOURCE PASS',rev,[reports[f'lod{i}']['triangles'] for i in range(3)],flush=True)

if __name__=='__main__':main()
