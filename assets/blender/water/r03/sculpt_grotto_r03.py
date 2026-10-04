"""One continuous boulder-derived grotto candidate; Blender 5.2.2, CPU only.

Internal source-review checkpoints 1-3 belong to the same candidate, not variants.
World -> Blender = (-worldX,-worldZ,worldY); local pivot is world(-4,0,-39).
Run with Blender --threads 6 --background --factory-startup --python this -- --pass N.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys, time
from pathlib import Path
import bpy, bmesh, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
EVID=ROOT/'planning/evidence/water-art-pass4b-20261003/r03'
OUT=ROOT/'apps/client/src/assets/world/water-art-pass4b-r03'
RAW=HERE/'raw'
sys.path.insert(0,str(ROOT/'assets/blender/nature_props'))
import np_lib as L
PIVOT=Vector((4,39,0))
ID='sm_grotto_organic_r03'
START=time.monotonic()
def guard(label):
    if time.monotonic()-START>570: raise TimeoutError('Bounded Blender deadline '+label)
    print('SCULPT '+label,flush=True)
def W(x,y,z):return Vector((-x,-z,y))-PIVOT
def world(v):return [-float(v.x)-4,float(v.z),-float(v.y)-39]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return Path(p).relative_to(ROOT).as_posix()
def write(p,v):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(v,indent=2),encoding='utf8')
def select(ob):
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
def apply(ob,mod):select(ob);bpy.ops.object.modifier_apply(modifier=mod.name)
def mesh(name,verts,faces):
    me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update()
    ob=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(ob);return ob
def clean(ob):
    bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.remove_doubles(bm,verts=bm.verts,dist=.00002)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.00002)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(ob.data);bm.free();ob.data.update()
def repair_tiny_fins(ob):
    # Exact Boolean can leave a zero-volume triangular fin on a triangulated edge.
    # Remove only the observed topology pattern, with a strict local area/perimeter bound.
    bm=bmesh.new();bm.from_mesh(ob.data)
    fins=[f for f in bm.faces if len(f.verts)==3 and sum(e.is_boundary for e in f.edges)==2
        and any(len(e.link_faces)==3 for e in f.edges) and f.calc_area()<.002
        and sum(e.calc_length() for e in f.edges)<.5]
    if len(fins)>4:bm.free();raise ValueError('Unexpected fin repair extent')
    if fins:
        print('SCULPT bounded triangular fin removal '+str(len(fins))+' '+ob.name,flush=True)
        bmesh.ops.delete(bm,geom=fins,context='FACES')
        bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(ob.data)
    bm.free();ob.data.update()
    return len(fins)
def tri(ob):ob.data.calc_loop_triangles();return len(ob.data.loop_triangles)
def stats(ob):
    bm=bmesh.new();bm.from_mesh(ob.data)
    bad=sum(not e.is_manifold for e in bm.edges);boundary=sum(e.is_boundary for e in bm.edges)
    seen=set();components=[]
    for v in bm.verts:
        if v in seen:continue
        pending=[v];seen.add(v);count=0
        while pending:
            q=pending.pop();count+=1
            for e in q.link_edges:
                t=e.other_vert(q)
                if t not in seen:seen.add(t);pending.append(t)
        components.append(count)
    vol=bm.calc_volume(signed=True);bm.free()
    v=[world(q.co) for q in ob.data.vertices]
    return dict(triangles=tri(ob),vertices=len(v),nonManifoldEdges=bad,boundaryEdges=boundary,
        components=components,signedVolumeM3=vol,boundsWorld={'min':np.min(v,axis=0).tolist(),'max':np.max(v,axis=0).tolist()})
def boolean(ob,cutter,op='DIFFERENCE'):
    guard(op+' '+cutter.name)
    m=ob.modifiers.new('carve_'+cutter.name,'BOOLEAN');m.operation=op;m.solver='EXACT';m.object=cutter
    apply(ob,m);clean(ob)
def prism(name,rows,polys):
    # Cross-section rings in world YZ, swept through X.
    n=len(polys[0]);verts=[W(x,y,z) for x,p in zip(rows,polys) for z,y in p]
    faces=[tuple(range(n-1,-1,-1)),tuple((len(rows)-1)*n+j for j in range(n))]
    for r in range(len(rows)-1):
        for j in range(n):faces.append((r*n+j,r*n+(j+1)%n,(r+1)*n+(j+1)%n,(r+1)*n+j))
    ob=mesh(name,verts,faces);clean(ob);return ob
def box(name,x0,x1,z0,z1,y0,y1):
    return prism(name,[x0,x1],[[(z0,y0),(z1,y0),(z1,y1),(z0,y1)]]*2)
def import_boulder(aid):
    src=ROOT/f'assets/models/sunmeadow-props/stone/source/{aid}_lod0.glb'
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(src))
    objects=list(set(bpy.data.objects)-before);parts=[o for o in objects if o.type=='MESH']
    for ob in parts:
        select(ob);bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    ob=L.join(parts,'source_'+aid)
    ob.data.materials.clear()
    for other in objects:
        if other!=ob and other.name in bpy.data.objects:bpy.data.objects.remove(other,do_unlink=True)
    return ob
def piece(source,name,pose):
    x,z,sx,sz,height,base,yaw=pose
    coords=np.array([v.co[:] for v in source.data.vertices]);mn=coords.min(0);mx=coords.max(0)
    norm=(coords-mn)/(mx-mn);norm[:,0]-=.5;norm[:,1]-=.5
    verts=[];c=math.cos(yaw);s=math.sin(yaw)
    for q in norm:
        dx=q[0]*sx;dz=q[1]*sz
        wx=x+dx*c+dz*s;wz=z-dx*s+dz*c;wy=base+q[2]*height
        # Deliberate broad, gently tilted beds, not fine noise or bubble blobs.
        wx+=.075*math.sin(wy*2.45+wz*.22)
        wz+=.06*math.sin(wy*2.1+wx*.27)
        verts.append(W(wx,wy,wz))
    ob=mesh(name,verts,[tuple(p.vertices) for p in source.data.polygons]);return ob
def opening(passnum):
    rows=[-11,-7.65,-7.42,-7.366668,-7.183333,-6.891667,-6.60,-6.35,-5.4,-4.2,-3.3,-1.7,.88,4]
    polys=[]
    for x in rows:
        t=max(0,min(1,(x+6.8)/7.68));top=7.18+1.17*(t**.60)
        if x<=-7.42:top=7.16
        elif x<=-7.366668:top=7.243147
        elif x<=-6.60:top=7.26
        if passnum>=2:top+=.03*math.sin(t*math.pi)
        lo=-41.51 if x>=-4.25 else -40.74
        hi=-36.49 if x>=-4.25 else -35.98
        if passnum>=2:
            lo-=.13*math.sin(x*.82+.25)**2
            hi+=.16*math.sin(x*.68-.40)**2
        # The full fixed clear box remains below these walls and crown.
        polys.append([(lo,-.6),(hi,-.6),(hi,5.18),(hi-.20,6.25),(hi-.58,top-.18),
            (hi-1.08,top),(lo+1.02,top),(lo+.56,top-.20),(lo+.18,6.24),(lo,5.18)])
    return prism('CUT_passage_variable_crown',rows,polys)
def channel_cut():
    # Rows are the ACTUAL r01 exported film, not manifest anchor Y7.60.
    rows=[-7.55,-7.50,-7.42,-7.366668,-7.183333,-6.891667,-6.60,-6.52]
    top=[7.35,7.38,7.405,7.488147,7.505,7.505,7.505,7.505]
    return prism('CUT_channel_045_below_actual_film',rows,[
        [(-38.90,y),(-37.10,y),(-37.10,13),(-38.90,13)] for y in top])
def channel_solid():
    rows=[-7.50,-7.42,-7.366668,-7.183333,-6.891667,-6.60,-6.52]
    top=[7.38,7.405,7.488147,7.505,7.505,7.505,7.505]
    return prism('SOURCE_exact_channel_245mm_thick',rows,[
        [(-39.02,y-.245),(-36.98,y-.245),(-36.98,y),(-39.02,y)] for y in top])
def channel_underside_cut():
    rows=[-7.52,-7.50,-7.42,-7.366668,-7.183333,-6.891667,-6.60,-6.50]
    top=[7.135,7.135,7.160,7.243147,7.260,7.260,7.260,7.260]
    return prism('CUT_exact_channel_underside',rows,[
        [(-38.94,-.6),(-37.06,-.6),(-37.06,y),(-38.94,y)] for y in top])
def paint(ob,passnum=1):
    me=ob.data;me.update()
    for layer in list(me.uv_layers):me.uv_layers.remove(layer)
    uv=me.uv_layers.new(name='UVMap')
    for attr in list(me.color_attributes):me.color_attributes.remove(attr)
    col=me.color_attributes.new(name='Col',type='BYTE_COLOR',domain='CORNER')
    me.color_attributes.active_color=col
    for face in me.polygons:
        n=face.normal;up=max(0,min(1,(n.z-.60)/.27))
        for li in face.loop_indices:
            q=me.vertices[me.loops[li].vertex_index].co;wx,wy,wz=world(q)
            axis=max(range(3),key=lambda k:abs(n[k]))
            if axis==2:uv.data[li].uv=(-wx/2.5,wz/2.5)
            elif axis==0:uv.data[li].uv=(wz/2.5,wy/2.5)
            else:uv.data[li].uv=(-wx/2.5,wy/2.5)
            broad=.5+.22*math.sin(wx*.77+wz*.27)+.18*math.sin(wz*.66-wx*.11)
            moss=up*max(0,min(.62,(broad-.22)*.90))
            value=.94+.035*math.sin(wy*1.45+wx*.35)-.025*math.cos(wz*.85)
            if passnum>=3:value-=.035*math.cos(wy*1.12+wx*.10)
            neutral=(.98*value,.99*value,1.0*value);green=(.34,.59,.10)
            col.data[li].color=tuple(max(0,min(1,a*(1-moss)+b*moss)) for a,b in zip(neutral,green))+(1,)
    tex=ROOT/'assets/models/sunmeadow-props/stone/textures-source'
    material=bpy.data.materials.get('sm_stone_mat') or L.pbr_material('sm_stone_mat',tex/'sm_stone_albedo.png',tex/'sm_stone_normal.png',tex/'sm_stone_orm.png',vertex_color='Col',normal_strength=.1)
    me.materials.clear();me.materials.append(material)
    # Broad facets carry stratification; smooth interpolation hides useful planes.
    for p in me.polygons:p.use_smooth=False
def source_probe(ob):
    me=ob.data;me.calc_loop_triangles();verts=[Vector(world(v.co)) for v in me.vertices]
    faces=[tuple(t.vertices) for t in me.loop_triangles];tree=BVHTree.FromPolygons(verts,faces,all_triangles=True)
    def ray(a,b):
        a=Vector(a);b=Vector(b);d=b-a;hit,n,i,dist=tree.ray_cast(a,d.normalized(),d.length-.00001)
        return None if hit is None else dict(point=list(hit),distance=dist,triangle=i)
    water=json.loads((ROOT/'planning/evidence/water-art-pass4b-20261003/water-geometry.json').read_text())
    film=water['falls0']['position'];samples=[]
    for p in film:
        primary=(-7.3<=p[0]<=-6.59 and abs(p[1]-7.55)<1e-4) or (abs(p[0]+7.366668)<1e-4 and abs(p[1]-7.533147)<1e-4) or (abs(p[0]+7.42)<1e-4 and abs(p[1]-7.45)<1e-4)
        if primary:
            h=ray([p[0],12,p[2]],[p[0],0,p[2]])
            gap=None if h is None else p[1]-h['point'][1]
            samples.append(dict(point=p,stoneTop=None if h is None else h['point'][1],gap=gap,**{'pass':gap is not None and .025<=gap<=.067}))
    camera=[2.819878161304265,7.452022716769464,-38]
    targets=[('camera-centre',[-9.2,2.5,-38])]
    for t in [.1,.3,.6,.9,1.261]:
        for z in [-.8,0,.8]:targets.append((f'fall-{t}-{z}',[-7.42-1.5*t,7.45-4.905*t*t,-38+z]))
    for dx in [-1,0,1]:
        for dz in [-1,0,1]:targets.append((f'pool-{dx}-{dz}',[-9.6+dx,-.35,-38+dz]))
    rays=[dict(label=label,target=p,clear=(h:=ray(camera,p)) is None,hit=h) for label,p in targets]
    ceiling=[]
    for x in [-4,-3,-2,-1,.892]:
        for z in [-41.4,-40,-39,-38,-36.6]:
            h=ray([x,0,z],[x,12,z]);ceiling.append(dict(x=x,z=z,ceiling=None if h is None else h['point'][1],clear5_1=h is None or h['point'][1]>=5.10-1e-5))
    closest=tree.find_nearest(Vector(camera));nearClear=closest[3]
    cameraNear=[]
    # A conservative 0.1m near-plane sphere and a 0.25m neighbourhood.
    for d in [(.1,0,0),(-.1,0,0),(0,.1,0),(0,-.1,0),(0,0,.1),(0,0,-.1)]:
        q=[camera[i]+d[i] for i in range(3)];cameraNear.append(tree.find_nearest(Vector(q))[3])
    # Foam/lip decorations at Y7.48/7.50 occupy the same XZ as primary Y7.45;
    # their deliberate visual offset is checked for piercing, not channel contact.
    effects=[]
    for p in film:
        if -7.42001<=p[0]<=-6.59 and p[1]>=7.449:
            h=ray([p[0],12,p[2]],[p[0],0,p[2]])
            effects.append(dict(point=p,gap=None if h is None else p[1]-h['point'][1],pierces=h is not None and h['point'][1]>p[1]+.0005))
    curve=[]
    for p in film:
        if -9.4<=p[0]<-7.435 and p[1]>.15 and abs(p[2]+38)<=.81:
            origin=Vector(p);direction=Vector((0,1,0));count=0
            for _ in range(12):
                h,_,_,_=tree.ray_cast(origin,direction,16-origin.y)
                if h is None:break
                count+=1;origin=h+direction*.0002
            curve.append(dict(point=p,insideRock=(count%2)==1))
    return dict(actualFilmSupport=samples,allActualFilmSupport=all(p['pass'] for p in samples),
        allUpperEffectNoPiercing=not any(p['pierces'] for p in effects),allUpperEffectSamples=effects,
        primaryCurveFreefallSamples=curve,allCurveFreefallOutsideRock=not any(p['insideRock'] for p in curve),
        fixedSideCamera=camera,cameraDistanceToRockM=nearClear,nearPlaneRadiusM=.1,
        nearPlaneMinSurfaceDistanceM=min(cameraNear),sideRays=rays,
        requiredLowerFallPoolRaysClear=all(r['clear'] for r in rays if not r['label'].startswith('fall-0.1')),
        nearLipOcclusion=[r for r in rays if not r['clear']],clearBoxSamples=ceiling,
        fullClearBoxSamplesPass=all(p['clear5_1'] for p in ceiling),
        baseline={'included':['new continuous r03 LOD0','exact unchanged actual r01 water film coordinates'],
            'excludedBecauseRev3Removes':['v3_grotto_mouth','v3_grotto_tunnel','water_art_grotto_bluff_000..006'],
            'remainingWholeSceneGeometry':'Parent owns native scene ray baseline; source-only probes do not claim whole-scene clearance'})
def render(ob,passnum):
    guard('review setup')
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=12
    scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=6
    scene.render.resolution_x=640;scene.render.resolution_y=360;scene.render.resolution_percentage=100
    if scene.world is None:scene.world=bpy.data.worlds.new('REVIEW_sky_fill')
    scene.world.use_nodes=True;scene.world.node_tree.nodes.get('Background').inputs[0].default_value=(.47,.60,.73,1)
    scene.world.node_tree.nodes.get('Background').inputs[1].default_value=.7
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=0
    bpy.ops.object.light_add(type='SUN',location=W(2,15,-46));sun=bpy.context.object;sun.data.energy=2.5;sun.data.angle=.08;sun.rotation_euler=(.50,-.55,-.45)
    bpy.ops.mesh.primitive_plane_add(size=70,location=W(-4,-.012,-39));ground=bpy.context.object;ground.name='REVIEW_ground_only'
    mat=bpy.data.materials.new('REVIEW_ground');mat.diffuse_color=(.23,.34,.12,1);ground.data.materials.append(mat)
    # Explicit 1.8m human scale witness, excluded from exported geometry.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,location=W(-7.6,.78,-39.3));person=bpy.context.object
    person.name='REVIEW_1_8m_witness';person.scale=(.24,.18,.75)
    wm=bpy.data.materials.new('REVIEW_witness');wm.diffuse_color=(.67,.21,.10,1);person.data.materials.append(wm)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10,ring_count=6,radius=.18,location=W(-7.6,1.62,-39.3));bpy.context.object.data.materials.append(wm)
    # Actual fixed film mesh is shown with review water material, never exported.
    film=json.loads((ROOT/'planning/evidence/water-art-pass4b-20261003/water-geometry.json').read_text())['falls0']
    idx=film['indices'];waterob=mesh('REVIEW_actual_fixed_water_film',[W(*p) for p in film['position']],[tuple(idx[i:i+3]) for i in range(0,len(idx),3)])
    watermat=bpy.data.materials.new('REVIEW_water');watermat.diffuse_color=(.035,.39,.46,1);watermat.use_nodes=True
    bs=watermat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.035,.39,.46,1);bs.inputs['Roughness'].default_value=.23
    waterob.data.materials.append(watermat)
    def arc(target,alpha,beta,radius):
        return [target[0]+radius*math.cos(alpha)*math.sin(beta),target[1]+radius*math.cos(beta),target[2]+radius*math.sin(alpha)*math.sin(beta)]
    waterTarget=[-17,1.65,-41]
    cams=[('side',[2.819878161304265,7.452022716769464,-38],[-9.2,2.5,-38]),
        ('player',arc(waterTarget,-math.pi/2,1.18,13),waterTarget),
        ('elevated',arc(waterTarget,-1.27,.65,26),waterTarget),
        ('sculpt-detail',[-12.3,12.0,-48.5],[-4.4,4.4,-38.8])]
    for name,position,target in cams:
        guard('BLENDER REVIEW '+name)
        bpy.ops.object.camera_add(location=W(*position));cam=bpy.context.object
        cam.rotation_euler=(W(*target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='PERSP';cam.data.sensor_fit='VERTICAL';cam.data.sensor_height=24;cam.data.lens=24/(2*math.tan(1.02/2))
        cam.data.clip_start=.1;scene.camera=cam
        p=EVID/f'BLENDER-REVIEW/pass{passnum}-{name}.png';p.parent.mkdir(parents=True,exist_ok=True)
        scene.render.filepath=str(p);bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(cam,do_unlink=True)
    guard('review finished')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pass',dest='passnum',type=int,default=1);ap.add_argument('--no-render',action='store_true');ap.add_argument('--render-only',action='store_true');ap.add_argument('--proxy-only',action='store_true');args=ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    for p in [HERE,RAW,EVID,OUT]:p.mkdir(parents=True,exist_ok=True)
    if args.proxy_only:
        bpy.ops.wm.open_mainfile(filepath=str(HERE/'sm_grotto_organic_r03.blend'))
        old=bpy.data.objects.get(ID+'_collider')
        if old:bpy.data.objects.remove(old,do_unlink=True)
        collider=L.copy_object(bpy.data.objects[ID+'_lod2'],ID+'_collider');collider.data.materials.clear()
        L.export_lod(collider,RAW/f'{ID}_collider.glb',profile='prop',budget_class='world_cell',vertex_color='NONE',materials='NONE',asset_id=ID+'_collider',notes=['Geometry-only exact closed LOD2 proxy with negative passage; source/server colliders not changed.'])
        rec=stats(collider)
        if rec['nonManifoldEdges'] or len(rec['components'])!=1:raise ValueError('proxy topology')
        collider.hide_render=True;collider.hide_set(True)
        provenance=json.loads((EVID/'sculpt-source-provenance.json').read_text());provenance['collider']=rec
        provenance['recipeSha256']=sha(HERE/'sculpt_grotto_r03.py');provenance['colliderMethod']='Exact validated closed LOD2 geometry, no hull sealing the passage'
        write(EVID/'sculpt-source-provenance.json',provenance)
        bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'sm_grotto_organic_r03.blend'));guard('proxy-only complete');return
    if args.render_only:
        bpy.ops.wm.open_mainfile(filepath=str(HERE/'sm_grotto_organic_r03.blend'))
        render(bpy.data.objects[ID+'_lod0'],args.passnum);guard('render-only complete');return
    L.reset();bpy.context.scene.render.threads_mode='FIXED';bpy.context.scene.render.threads=6
    guard('verified boulder source import')
    sources=[import_boulder('sm_boulder_03'),import_boulder('sm_boulder_04')]
    # The same source shapes are intentionally overlapped and fused. These are not placed kit props.
    poses=[(-7.42,-42.20,5.8,3.3,8.9,0,.07),(-7.15,-34.60,5.65,3.1,9.0,0,-.08),
        (-5.2,-41.63,3.7,2.0,9.45,0,.12),(-5.0,-36.13,3.4,1.85,9.55,0,-.14),
        (-2.8,-41.73,3.8,1.10,9.5,0,.02),(-2.6,-36.14,3.8,1.20,9.65,0,-.02),
        (-.45,-41.75,2.60,1.10,9.60,0,.02),(-.35,-36.2,2.4,1.18,9.8,0,-.03),
        (-6.45,-38.65,3.3,6.85,2.15,6.40,.07),(-4.55,-39.0,4.5,6.1,2.25,7.10,-.04),
        (-2.35,-39.0,4.30,6.0,2.15,7.72,.025),(-.55,-39.0,2.80,5.95,1.75,8.15,-.03),
        (-8.4,-43.0,3.8,2.8,3.6,0,.20),(-8.55,-33.25,3.8,2.8,3.30,0,-.27)]
    pieces=[piece(sources[i%2],f'boulder_stratum_{i:02d}',p) for i,p in enumerate(poses)]
    # A curved support shelf merged into the solid source volume; channel floor is carved after remesh.
    rows=[-7.44,-7.366668,-7.18,-6.6,-6.35];tops=[7.46,7.56,7.60,7.62,7.85]
    shelf=prism('source_channel_support',rows,[
        [(-41.22,7.05),(-35.78,7.05),(-35.78,y+.5),(-37.1,y),(-38.9,y),(-41.22,y+.40)] for y in tops])
    pieces.append(shelf);mass=L.join(pieces,'SCULPT_master_boulder_union')
    for src in sources:src.hide_render=True;src.hide_set(True)
    guard('single volume voxel remesh .16m')
    L.remesh(mass,.16);clean(mass)
    # Remove below ground and bound to the already occupied original + r02 XZ region.
    groundcut=box('CUT_ground_Y0',-15,5,-50,-25,-4,0);boolean(mass,groundcut)
    envelope=box('BOUND_existing_footprint_AABB',-10.705992,.892,-44.684217,-31.504775,-.01,12)
    boolean(mass,envelope,'INTERSECT')
    cutter=opening(args.passnum);boolean(mass,cutter)
    gutter=channel_cut();boolean(mass,gutter)
    spillcut=box('CUT_curve_clear_beyond_solid_spill_edge',-11,-7.50,-39.1,-36.9,-.1,13)
    if args.passnum>=2:boolean(mass,spillcut)
    repair_tiny_fins(mass)
    # One small seam interruption and a broad undercut introduce stratification without equal bands.
    if args.passnum>=2:
        for v in mass.data.vertices:
            wx,wy,wz=world(v.co)
            if wy<6.5 and (wz<-41.7 or wz>-36.2):
                a=.18*math.sin(wy*2.3+wx*.35)
                v.co.y+=a
                if args.passnum>=3:
                    # Two broad beds, with unequal prominence; no repeated tiny grooves.
                    beds=.19*math.exp(-((wy-(3.00+.045*wx))/.30)**2)+.13*math.exp(-((wy-(5.50-.025*wx))/.33)**2)
                    outward=-1 if wz<-41.7 else 1
                    v.co.y-=outward*beds
        clean(mass)
    mass['source']='Verified original sm_boulder_03/04 LOD0 geometry; overlap/remesh/Boolean sculpt; one candidate'
    mass['negative_passage']='world X[-4,.892],Z[-41.4,-36.6],Y[0,5.1]'
    mass['actual_film']='unchanged r01 geometry; support floor 0.045m below Y7.55 plus curved rows'
    # Keep master and cutters editable. Runtime LODs are evaluated copies.
    guard('LOD construction')
    lods=[];records=[]
    targets=[5600,2200,740] if args.passnum==1 else [5350,1650,320]
    for level,target in enumerate(targets):
        ob=L.decimate_to(mass,target,name=ID+f'_lod{level}',tol=.003,max_iter=3);clean(ob)
        if args.passnum>=2:
            if level>=1:
                exactChannel=channel_solid();boolean(ob,exactChannel,'UNION')
                exactChannel.hide_render=True;exactChannel.hide_set(True)
                undersideCut=channel_underside_cut();boolean(ob,undersideCut)
                undersideCut.hide_render=True;undersideCut.hide_set(True)
            boolean(ob,gutter)
            boolean(ob,spillcut)
            # Boolean intersection preserves closed faces; coordinate clamps can collapse faces.
            exactFoot=box('BOUND_lod_footprint_and_ground',-10.705992,.892,-44.684217,-31.504775,0,12)
            boolean(ob,exactFoot,'INTERSECT');exactFoot.hide_render=True;exactFoot.hide_set(True)
            repair_tiny_fins(ob)
        L.triangulate(ob);paint(ob,args.passnum)
        rec=stats(ob);records.append(rec);lods.append(ob)
        if rec['triangles']>[6000,2400,800][level]:raise ValueError('triangle budget '+str(rec))
        if rec['nonManifoldEdges'] or len(rec['components'])!=1:
            bm=bmesh.new();bm.from_mesh(ob.data)
            edges=[dict(a=world(e.verts[0].co),b=world(e.verts[1].co),faces=len(e.link_faces)) for e in bm.edges if not e.is_manifold]
            bm.free();write(EVID/f'sculpt-pass{args.passnum}-topology-stop.json',dict(level=level,stats=rec,edges=edges))
            raise ValueError('topology '+str(rec))
    probe=source_probe(lods[0]);write(EVID/f'sculpt-pass{args.passnum}-geometry.json',dict(schema='xexoria.sculpt-grotto-source/1',passNumber=args.passnum,source=records,probe=probe,seconds=time.monotonic()-START))
    # Technical receipt does not imply native art acceptance.
    if not probe['fullClearBoxSamplesPass']:raise ValueError('fixed clear box failure')
    guard('raw exports, source remains editable')
    for level,ob in enumerate(lods):
        L.export_lod(ob,RAW/f'{ID}_lod{level}.glb',profile='prop',budget_class='world_cell',texture_dir=RAW/'textures',vertex_color='MATERIAL',asset_id=ID+f'_lod{level}',copyright_text='Xexoria original procedural sm_stone boulders; derived organic grotto candidate r03',notes=['Babylon local = (-BlenderX,BlenderZ,-BlenderY); world pivot(-4,0,-39).','anchor_at_pivot true, do not recenter bounds.','Shared sm_stone atlas 2.5m repeat; COLOR_0 is required; moss only face-up normal > .6.'])
    collider=L.copy_object(lods[2],ID+'_collider');collider.data.materials.clear();clean(collider)
    L.export_lod(collider,RAW/f'{ID}_collider.glb',profile='prop',budget_class='world_cell',vertex_color='NONE',materials='NONE',asset_id=ID+'_collider',notes=['Geometry-only compound negative-space proxy; raw baseline/server colliders not changed.'])
    shadow=L.copy_object(lods[1],ID+'_shadow');shadow.data.materials.clear()
    L.export_lod(shadow,RAW/f'{ID}_shadow.glb',profile='prop',budget_class='world_cell',vertex_color='NONE',materials='NONE',asset_id=ID+'_shadow',notes=['Separate geometry-only shadow proxy; never a visible primitive in main LOD GLBs.'])
    write(EVID/'sculpt-source-provenance.json',dict(schema='xexoria.sculpt-grotto-provenance/1',candidate=ID,
        sourceHashes={rel(ROOT/f'assets/models/sunmeadow-props/stone/source/{a}_lod0.glb'):sha(ROOT/f'assets/models/sunmeadow-props/stone/source/{a}_lod0.glb') for a in ['sm_boulder_03','sm_boulder_04']},
        recipe=rel(HERE/'sculpt_grotto_r03.py'),recipeSha256=sha(HERE/'sculpt_grotto_r03.py'),tool=bpy.app.version_string,
        material='sm_stone_mat',sourceArtImmutable=True,pivotWorld=[-4,0,-39],anchor_at_pivot=True,
        raw=[dict(file=rel(RAW/f'{ID}_lod{i}.glb'),sha256=sha(RAW/f'{ID}_lod{i}.glb')) for i in range(3)],
        lods=records,collider=stats(collider),probe=probe,
        resource=dict(threads=6,renderer='Cycles CPU',samples=12,gpu=False),
        status='SOURCE_CANDIDATE',visual='BLENDER_REVIEW_ONLY',native='UNVERIFIED_PARENT',gameplay='UNVERIFIED_PARENT'))
    for ob in [mass,groundcut,envelope,cutter,gutter,spillcut,collider,shadow]+lods[1:]:ob.hide_render=True;ob.hide_set(True)
    lods[0].hide_set(False);lods[0].hide_render=False
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'sm_grotto_organic_r03.blend'))
    if not args.no_render:render(lods[0],args.passnum)
    guard('complete '+str(round(time.monotonic()-START,2))+'s')
if __name__=='__main__':main()
